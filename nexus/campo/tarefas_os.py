"""Publica as tarefas das OS do Fracttal no banco (18/10/2026): `nexus_os · fato_tarefa_os` (o fato e as regras:
`nexus/dados/fato_tarefa_os.py`).

Levi, 18/10/2026, ao pôr a manutenção na Visão do responsável: "pegando tudo do Fracttal ou Nexus, sem fontes
externas!". As telas do PCM liam as tarefas do `gestao_pcm.json` que o robô do PCM regrava no GitHub dele; aqui o
próprio Nexus lê o REST do Fracttal (só GET, a credencial do Nexus) e grava o fato que qualquer tela liga por ID.

O que lê: as tarefas das OS em processo (1) e em verificação (2), todas e de todo tipo; e as do tipo Zeladoria
finalizadas (3), da data de fim mais nova até 90 dias atrás (a "última zeladoria feita"). A ordem do REST é só
aproximada: a leitura das finalizadas para quando uma página INTEIRA passou do piso, não no 1º registro velho.

Leitura incompleta não grava ("número pela metade não vai para a tela"): página recusada pelo limite da empresa
(200 pedidos por minuto, dividido com o App de Campo) espera 1 min e tenta de novo; recusada três vezes, ou passou do
teto de páginas, a volta inteira para e o livro fica como estava. A falha fica no `estado()`, que a Visão mostra, e no
log. Fora da carga de hora em hora de propósito (aquela não toca no Fracttal), como os chamados
(`chamados_acompanhamento.py`): grava a máquina que chegar primeiro, se a última gravação tiver mais de 50 min;
`NEXUS_OS_PUBLICAR=0` desliga numa máquina.
"""
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from ..dados import equipamento as E
from ..dados import fato_tarefa_os as F
from ..dados import fatos as D
from ..dados import livros
from . import fracttal

INTERVALO_MIN = 50
PRIMEIRA_S = 120            # a 1ª volta depois de subir (o boot já lê o banco para as telas)
MINUTO_DA_HORA = 10         # longe do sync do App (:25), da carga de dados (:40) e dos chamados (:50)
PAGINAS_MAX = 150           # status 1 + 2 medidos em ~85 páginas (o 2 sozinho, 55 a 62): passou disso, algo mudou
PAUSA_S = 1.0               # 1 pedido por segundo, como as outras leituras do Fracttal do Nexus
ESPERA_RECUSA_S = 60        # a cota do Fracttal é uma janela de 1 minuto da empresa (App v236)
TENTATIVAS = 3
DIAS_ZELADORIA = 90
TIPO_ZELADORIA_REST = "Zeladoria"   # a grafia do tipo no REST: o ensaio (ferramentas/ensaio_tarefas_os.py) confere
_BRT = timezone(timedelta(hours=-3))
_LACO = {"thread": None, "parar": threading.Event(), "ultimo": None, "quando": None}
log = logging.getLogger("nexus.campo")


class LeituraIncompleta(RuntimeError):
    """A leitura do Fracttal não veio inteira: nada se grava."""


def _base(config) -> str:
    from ..cadastro.ligacoes import BASE_API
    return (config.get("GRIDCO_DB_API") or BASE_API).rstrip("/")


def _pagina(ler, path):
    for n in range(TENTATIVAS):
        try:
            return ler(path)
        except fracttal.Recusado:
            if n == TENTATIVAS - 1:
                raise LeituraIncompleta(f"o Fracttal recusou a mesma página {TENTATIVAS} vezes ({path})") from None
            time.sleep(ESPERA_RECUSA_S)


def _paginas(ler, path_base: str, para=None) -> list:
    out, inicio = [], 0
    for n in range(PAGINAS_MAX):
        if n:
            time.sleep(PAUSA_S)
        r = _pagina(ler, f"{path_base}&limit=100&start={inicio}")
        pagina = (r.get("data") if isinstance(r, dict) else r) or []
        out += pagina
        if len(pagina) < 100 or (para and para(pagina)):
            return out
        inicio += 100
    raise LeituraIncompleta(f"passou de {PAGINAS_MAX} páginas ({path_base}): o teto não corta calado")


def ler_fracttal(ler, hoje) -> list[dict]:
    """As linhas do REST que entram no fato (a separação fina é do `fato_tarefa_os`)."""
    rows = []
    for st in (1, 2):
        rows += _paginas(ler, f"work_orders?id_status_work_order={st}&sort=creation_date:desc")
    piso = (hoje - timedelta(days=DIAS_ZELADORIA)).isoformat()

    def passou(pagina):
        datas = [str(w.get("final_date"))[:10] for w in pagina if w.get("final_date")]
        return not datas or max(datas) < piso
    zel = _paginas(ler, f"work_orders?id_status_work_order=3&tasks_log_task_type_main={quote(TIPO_ZELADORIA_REST)}"
                        f"&sort=final_date:desc", passou)
    return rows + [w for w in zel if str(w.get("final_date") or "")[:10] >= piso]


def _ultima(base, sessao) -> datetime | None:
    v = livros.atualizado_em(base, sessao, F.LIVRO)
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00")) if v else None
    except ValueError:
        return None
    return d if d is None or d.tzinfo else d.replace(tzinfo=timezone.utc)


def _backoffice_hmac(config) -> set[str] | None:
    """Os `nome_hmac` da lista vigente do backoffice do PCM (a última decisão de cada nome, a regra do
    `motivos.backoffice`), sem decifrar: o fato só compara códigos. None = o livro dos motivos não abriu."""
    from ..pcm import motivos
    est = motivos.ler(config)
    if est.get("erro") and not est.get("lido_em"):
        return None
    ult = {}
    for x in sorted(est.get("backoffice") or [], key=lambda x: D._txt(x.get("decidida_em"))):
        ult[D._txt(x.get("nome_hmac"))] = x
    return {nh for nh, x in ult.items() if nh and D._sim(x.get("na_lista"))}


def publicar(config, sessao=None, *, ler=None, agora=None, forcar=False) -> dict:
    """Uma volta: lê o Fracttal inteiro, liga ao cadastro e grava o livro (conferido depois de gravar,
    `livros.publicar`). Devolve o relatório (só contagens)."""
    import requests
    s = sessao or requests.Session()
    base = _base(config)
    agora = agora or datetime.now(_BRT)
    if not forcar:
        u = _ultima(base, s)
        if u and agora - u < timedelta(minutes=INTERVALO_MIN):
            return {"pulou": f"a última gravação é de {u.astimezone(_BRT).isoformat(timespec='minutes')}"}
    if not config.get("GRIDCO_SQL_TOKEN"):
        return {"erro": "sem GRIDCO_SQL_TOKEN: não grava"}
    ler = ler or fracttal.ler
    paginas = [0]

    def ler_contando(path):
        paginas[0] += 1
        return ler(path)
    try:
        rows = ler_fracttal(ler_contando, agora.astimezone(_BRT).date())
    except LeituraIncompleta as e:
        return {"erro": f"LeituraIncompleta: {e}"[:300], "paginas": paginas[0]}
    lido_em = datetime.now(_BRT).isoformat(timespec="seconds")
    cad = {aba: livros.ler(base, s, "cadastro_nexus", aba) for aba in ("usinas", "de_para", "equipes")}
    lig = D.Ligador(cad["usinas"], cad["de_para"], cad["equipes"], {})
    idx = E.indice(livros.ler(base, s, "nexus_equipamentos", "dim_equipamento"))
    bo = _backoffice_hmac(config)
    lin, rf = F.linhas(rows, lig, idx, bo or set(), config.get("NEXUS_PESSOA_HMAC") if bo is not None else None)
    F.conferir_grao(lin)
    i_st = F.CAB_TAREFA_OS.index("status_os")
    rel = {"lidas": rf["lidas"], "linhas": len(lin), "paginas": paginas[0], "sem_usina": rf["sem_usina"],
           "abertas": sum(1 for r in lin if r[i_st] in ("em_processo", "em_verificacao"))}
    if not lin:
        atuais = livros.ler(base, s, F.LIVRO, F.ABA)
        if atuais:
            return dict(rel, recusou=f"o Fracttal devolveu 0 tarefas e o banco tem {len(atuais)}: o livro fica como está")
    q = F.linha_qualidade(lin, dict(rf, paginas=paginas[0]), lido_em, agora.isoformat(timespec="seconds"))
    rel["gravado"] = livros.publicar(F.LIVRO, F.NOME_LIVRO,
                                     {F.ABA: (F.CAB_TAREFA_OS, lin), "qualidade": (D.CAB_QUALIDADE, [q])},
                                     base=base, token=config["GRIDCO_SQL_TOKEN"], sessao=s)
    return rel


def estado() -> dict:
    """O resultado da última volta deste processo e quando foi (a Visão diz quando a leitura falhou)."""
    return {"ultimo": _LACO["ultimo"], "quando": _LACO["quando"]}


def _espera_s(agora=None) -> float:
    agora = agora or datetime.now(_BRT)
    alvo = agora.replace(minute=MINUTO_DA_HORA, second=0, microsecond=0)
    if alvo <= agora:
        alvo += timedelta(hours=1)
    return (alvo - agora).total_seconds()


def ligar(app):
    """O laço: a 1ª volta 2 min depois de subir, depois aos :10 de cada hora. Quem chama é o `campo.instalar` (app.py e
    servir.py), nunca o create_app: teste não fala com a rede."""
    if _LACO["thread"] is not None or str(app.config.get("NEXUS_OS_PUBLICAR", "1")).strip() == "0":
        return

    def laco():
        espera = PRIMEIRA_S
        while not _LACO["parar"].wait(espera):
            with app.app_context():
                try:
                    _LACO["ultimo"] = publicar(app.config)
                    log.info("tarefas das OS no banco: %s", {k: v for k, v in _LACO["ultimo"].items() if k != "gravado"})
                except Exception as e:      # noqa: BLE001 — o laço não morre por uma volta
                    _LACO["ultimo"] = {"erro": f"{type(e).__name__}: {e}"[:300]}
                    log.exception("tarefas das OS no banco")
                _LACO["quando"] = datetime.now(_BRT).isoformat(timespec="minutes")
            espera = _espera_s()

    _LACO["thread"] = threading.Thread(target=laco, name="nexus-tarefas-os-banco", daemon=True)
    _LACO["thread"].start()

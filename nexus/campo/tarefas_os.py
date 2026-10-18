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
teto de páginas, a volta inteira para e o livro fica como estava. Desde a revisão de 18/10/2026 a leitura de cada
status começa pelo total que o REST informa (`limit=1`, como a fila do App): a página que vem sem a lista ou com
`success: false`, a que repete a anterior e a leitura que termina abaixo do total também param a volta. A sonda de
18/10 mostrou que a página DEPOIS da última vem com `data: None`: é o fim, e o total é quem diz que não foi corte. A OS
que muda de status durante a leitura (~1 min por status) pula as linhas dela numa borda de página; até 1% do total passa,
medido no `faltaram` da qualidade.

Também não grava o que sairia chutado: sem a `NEXUS_PESSOA_HMAC` ou sem a lista do backoffice do PCM, o `do_backoffice`
ia 0 para todas e a Visão cobrava do supervisor as OS do backoffice; sem a usina ou o de-para do cadastro, ou com a
usina ligada abaixo de 90% das tarefas (o 1º ensaio ligou 98,6%), a tela perderia as OS da maioria das usinas. Nesses
casos o relatório diz `recusou`, o livro fica como está, e o Fracttal nem é lido quando dá para saber antes.

A falha fica no `estado()`, que a Visão mostra, e no log. Fora da carga de hora em hora de propósito (aquela não toca
no Fracttal), como os chamados (`chamados_acompanhamento.py`): grava a máquina que chegar primeiro, se a última gravação
tiver mais de 50 min, conferido de novo logo antes de gravar (a leitura leva ~2 min); cada máquina acorda num minuto
seu entre :10 e :20 (revisão de 18/10/2026: no mesmo :10, PC e servidor liam o Fracttal juntos e os dois gravavam).
`NEXUS_OS_PUBLICAR=0` desliga numa máquina.
"""
import logging
import random
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
DESENCONTRO_MAX_S = 600     # cada processo sorteia o seu atraso de 0 a 10 min sobre o :10 (ainda antes do :25)
PAGINAS_MAX = 150           # status 1 + 2 medidos em ~85 páginas (o 2 sozinho, 55 a 62): passou disso, algo mudou
FOLGA_MOVIMENTO = 0.01      # até 1% do total do status pode faltar: a OS que mudou de status durante a leitura
PISO_USINA = 90.0           # % das tarefas ligadas a uma usina abaixo do qual o cadastro quebrou (1º ensaio: 98,6%)
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


def _resposta(r, path):
    if not isinstance(r, dict) or r.get("success") is False:
        raise LeituraIncompleta(f"o Fracttal respondeu com erro ({path})")
    return r


def _total(ler, path_base: str) -> int:
    r = _resposta(_pagina(ler, f"{path_base}&limit=1"), path_base)
    if r.get("total") is None:
        raise LeituraIncompleta(f"o Fracttal não informou o total ({path_base})")
    return int(r["total"])


def _chave(w, i):
    t = w.get("id_work_orders_tasks")
    return t if t not in (None, "") else ("sem tarefa", i)


def _paginas(ler, path_base: str, para=None, medida=None) -> list:
    """As linhas de um filtro, página a página, até a página curta (ou até `para`, que para antes por desenho), conferidas
    contra o total que o REST informa. `medida["faltaram"]` soma o que faltou dentro da folga."""
    total = _total(ler, path_base)
    out, vistas, inicio = [], set(), 0
    for _ in range(PAGINAS_MAX):
        time.sleep(PAUSA_S)
        path = f"{path_base}&limit=100&start={inicio}"
        dados = _resposta(_pagina(ler, path), path).get("data")
        if dados is not None and not isinstance(dados, list):
            raise LeituraIncompleta(f"o Fracttal respondeu sem a lista de dados ({path})")
        pagina = dados or []
        chaves = {_chave(w, inicio + i) for i, w in enumerate(pagina)}
        if len(pagina) == 100 and not chaves - vistas:
            raise LeituraIncompleta(f"a página {inicio} repetiu as anteriores ({path_base})")
        vistas |= chaves
        out += pagina
        if para and para(pagina):
            return out
        if len(pagina) < 100:
            falta = total - len(vistas)
            if falta > total * FOLGA_MOVIMENTO:
                raise LeituraIncompleta(f"vieram {len(vistas)} de {total} tarefas ({path_base})")
            if medida is not None:
                medida["faltaram"] = medida.get("faltaram", 0) + max(falta, 0)
            return out
        inicio += 100
    raise LeituraIncompleta(f"passou de {PAGINAS_MAX} páginas ({path_base}): o teto não corta calado")


def ler_fracttal(ler, hoje, medida=None) -> list[dict]:
    """As linhas do REST que entram no fato (a separação fina é do `fato_tarefa_os`)."""
    rows = []
    for st in (1, 2):
        rows += _paginas(ler, f"work_orders?id_status_work_order={st}&sort=creation_date:desc", medida=medida)
    piso = (hoje - timedelta(days=DIAS_ZELADORIA)).isoformat()

    def passou(pagina):
        datas = [str(w.get("final_date"))[:10] for w in pagina if w.get("final_date")]
        return not datas or max(datas) < piso
    zel = _paginas(ler, f"work_orders?id_status_work_order=3&tasks_log_task_type_main={quote(TIPO_ZELADORIA_REST)}"
                        f"&sort=final_date:desc", passou, medida)
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

    def gravou_ha_pouco():
        u = None if forcar else _ultima(base, s)
        if u and agora - u < timedelta(minutes=INTERVALO_MIN):
            return f"a última gravação é de {u.astimezone(_BRT).isoformat(timespec='minutes')}"
    if pulou := gravou_ha_pouco():
        return {"pulou": pulou}
    if not config.get("GRIDCO_SQL_TOKEN"):
        return {"erro": "sem GRIDCO_SQL_TOKEN: não grava"}
    chave = config.get("NEXUS_PESSOA_HMAC")
    if not chave:
        return {"recusou": "sem a NEXUS_PESSOA_HMAC não dá para saber quais OS são do backoffice: o livro fica como está"}
    # o banco ANTES do Fracttal (ensaio de 18/10/2026: 89 páginas lidas, 2 min da cota da empresa, e a volta caiu no
    # cadastro com o tempo esgotado): o Fracttal só é lido quando o resto da volta pode terminar
    cad = {aba: livros.ler(base, s, "cadastro_nexus", aba) for aba in ("usinas", "de_para", "equipes")}
    if vazias := [aba for aba in ("usinas", "de_para") if not cad[aba]]:
        return {"recusou": f"o cadastro veio sem {' e '.join(vazias)}: nenhuma tarefa ligaria à usina; o livro fica como está"}
    lig = D.Ligador(cad["usinas"], cad["de_para"], cad["equipes"], {})
    idx = E.indice(livros.ler(base, s, "nexus_equipamentos", "dim_equipamento"))
    bo = _backoffice_hmac(config)
    if bo is None:
        return {"recusou": "a lista do backoffice do PCM não abriu: o do_backoffice sairia chutado; o livro fica como está"}
    ler = ler or fracttal.ler
    paginas, medida = [0], {"faltaram": 0}

    def ler_contando(path):
        paginas[0] += 1
        return ler(path)
    try:
        rows = ler_fracttal(ler_contando, agora.astimezone(_BRT).date(), medida)
    except LeituraIncompleta as e:
        return {"erro": f"LeituraIncompleta: {e}"[:300], "paginas": paginas[0]}
    lido_em = datetime.now(_BRT).isoformat(timespec="seconds")
    lin, rf = F.linhas(rows, lig, idx, bo, chave)
    F.conferir_grao(lin)
    i_st = F.CAB_TAREFA_OS.index("status_os")
    rel = {"lidas": rf["lidas"], "linhas": len(lin), "paginas": paginas[0], "sem_usina": rf["sem_usina"],
           "faltaram": medida["faltaram"], "abertas": sum(1 for r in lin if r[i_st] in ("em_processo", "em_verificacao"))}
    if not lin:
        atuais = livros.ler(base, s, F.LIVRO, F.ABA)
        if atuais:
            return dict(rel, recusou=f"o Fracttal devolveu 0 tarefas e o banco tem {len(atuais)}: o livro fica como está")
    pct = 100.0 * (len(lin) - rf["sem_usina"]) / len(lin) if lin else 100.0
    if pct < PISO_USINA:
        return dict(rel, recusou=f"só {pct:.1f}% das tarefas ligaram a uma usina (o piso é {PISO_USINA:.0f}%): o de-para "
                                 f"ou o cadastro quebrou; o livro fica como está".replace(".", ",", 1))
    if pulou := gravou_ha_pouco():          # outra máquina gravou enquanto esta lia o Fracttal
        return dict(rel, pulou=pulou)
    q = F.linha_qualidade(lin, dict(rf, paginas=paginas[0], faltaram=medida["faltaram"]), lido_em,
                          agora.isoformat(timespec="seconds"))
    rel["gravado"] = livros.publicar(F.LIVRO, F.NOME_LIVRO,
                                     {F.ABA: (F.CAB_TAREFA_OS, lin), "qualidade": (D.CAB_QUALIDADE, [q])},
                                     base=base, token=config["GRIDCO_SQL_TOKEN"], sessao=s)
    return rel


def estado() -> dict:
    """O resultado da última volta deste processo e quando foi (a Visão diz quando a leitura falhou)."""
    return {"ultimo": _LACO["ultimo"], "quando": _LACO["quando"]}


def _espera_s(agora=None, desencontro_s: float = 0.0) -> float:
    agora = agora or datetime.now(_BRT)
    alvo = agora.replace(minute=MINUTO_DA_HORA, second=0, microsecond=0) + timedelta(seconds=desencontro_s)
    if alvo <= agora:
        alvo += timedelta(hours=1)
    return (alvo - agora).total_seconds()


def _desencontro_s() -> float:
    return random.uniform(0, DESENCONTRO_MAX_S)


def ligar(app):
    """O laço: a 1ª volta 2 min depois de subir, depois a cada hora, no :10 mais o atraso que este processo sorteou.
    Quem chama é o `campo.instalar` (app.py e servir.py), nunca o create_app: teste não fala com a rede."""
    if _LACO["thread"] is not None or str(app.config.get("NEXUS_OS_PUBLICAR", "1")).strip() == "0":
        return
    desencontro = _desencontro_s()

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
            espera = _espera_s(desencontro_s=desencontro)

    _LACO["thread"] = threading.Thread(target=laco, name="nexus-tarefas-os-banco", daemon=True)
    _LACO["thread"].start()

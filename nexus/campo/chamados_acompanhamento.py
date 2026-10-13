"""Publica os chamados de garantia no banco (12/10/2026): as OS de acompanhamento de chamado do Fracttal no livro
`nexus_chamados · fato_chamado` (o fato e as regras: `nexus/dados/fato_chamado.py`).

Levi, 12/10/2026: "O nexus é um ambiente centralizado e precisamos ter os dados se conversando!". O quadro
Acompanhamento de chamados do OS Creator lê o Fracttal ao vivo, com a sessão de quem entrou (é nele que a analista de
chamados escreve o ticket e finaliza); quem só CONTA chamados (a Visão do responsável, e o que vier) lê este fato.

Fora da carga de hora em hora de propósito: aquela só lê o banco e o PCM e não toca no Fracttal
(`nexus/dados/carga.py`). Aqui: a API REST do Fracttal, só GET (`campo.fracttal.ler`, a credencial do Nexus, com o
ritmo da fila de lá), a tarefa Administrativa em processo e em verificação, e as concluídas pela data de fim até 90 dias
atrás: medido em 12/10/2026, 5 páginas de 100 nas abertas e 17 OS de acompanhamento em processo.

Duas máquinas com o Nexus no ar não gravam em dobro (regra 11): grava a que chegar primeiro na hora, se a última gravação
do livro tiver mais de 50 min (a hora que a API do banco dá ao livro). `NEXUS_CHAMADOS_PUBLICAR=0` desliga numa
máquina. O Fracttal que devolve 0 chamados com o livro cheio não apaga o livro (leitura ruim não vira "nenhum chamado").
"""
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from ..dados import fato_chamado as F
from ..dados import fatos as D
from ..dados import livros

INTERVALO_MIN = 50
PRIMEIRA_S = 120            # a 1ª volta depois de subir (o boot já lê o banco para as telas)
MINUTO_DA_HORA = 50         # depois da carga de dados (:40)
PAGINAS_MAX = 40
PAUSA_S = 1.0               # 1 pedido por segundo, como as outras leituras do Fracttal do Nexus
_BRT = timezone(timedelta(hours=-3))
_LACO = {"thread": None, "parar": threading.Event(), "ultimo": None}
log = logging.getLogger("nexus.campo")


def _base(config) -> str:
    from ..cadastro.ligacoes import BASE_API
    return (config.get("GRIDCO_DB_API") or BASE_API).rstrip("/")


def _paginas(ler, path_base: str, para=None) -> list:
    out, inicio = [], 0
    for n in range(PAGINAS_MAX):
        if n:
            time.sleep(PAUSA_S)
        r = ler(f"{path_base}&limit=100&start={inicio}")
        pagina = (r.get("data") if isinstance(r, dict) else r) or []
        out += pagina
        if len(pagina) < 100 or (para and para(pagina)):
            break
        inicio += 100
    return out


def ler_fracttal(ler, hoje) -> list[dict]:
    """As linhas do REST que podem ser OS de acompanhamento: a tarefa Administrativa em processo (1) e em verificação
    (2), todas; a concluída (3), da data de fim mais nova até 90 dias atrás. Quem separa a OS 3 é `fato_chamado`."""
    base = f"work_orders?tasks_log_task_type_main={quote(F.TIPO_TAREFA)}"
    rows = []
    for st in (1, 2):
        rows += _paginas(ler, f"{base}&id_status_work_order={st}&sort=creation_date:desc")
    piso = (hoje - timedelta(days=F.DIAS_CONCLUIDOS)).isoformat()

    def passou(pagina):
        return any(str(w.get("final_date") or "")[:10] < piso for w in pagina if w.get("final_date"))
    rows += _paginas(ler, f"{base}&id_status_work_order=3&sort=final_date:desc", passou)
    return rows


def _ultima(base, sessao) -> datetime | None:
    v = livros.atualizado_em(base, sessao, F.LIVRO)
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00")) if v else None
    except ValueError:
        return None
    return d if d is None or d.tzinfo else d.replace(tzinfo=timezone.utc)


def publicar(config, sessao=None, *, ler=None, agora=None, forcar=False) -> dict:
    """Uma volta: lê o Fracttal, liga ao cadastro e grava o livro (conferido depois de gravar, `livros.publicar`).
    Devolve o relatório (só contagens)."""
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
    if ler is None:
        from . import fracttal
        ler = fracttal.ler
    hoje = agora.astimezone(_BRT).date()
    rows = ler_fracttal(ler, hoje)
    cad = {aba: livros.ler(base, s, "cadastro_nexus", aba) for aba in ("usinas", "de_para", "equipes")}
    lig = D.Ligador(cad["usinas"], cad["de_para"], cad["equipes"], {})
    equip = {D._txt(r.get("codigo")): D._id(r.get("equipamento_id"))
             for r in livros.ler(base, s, "nexus_equipamentos", "dim_equipamento")
             if D._txt(r.get("codigo")) and D._id(r.get("equipamento_id"))}
    lin = F.linhas(rows, lig, equip, hoje)
    rel = {"lidas": len(rows), "linhas": len(lin), "abertas": sum(1 for r in lin if r[9] == "aberto"),
           "sem_usina": sum(1 for r in lin if not r[3])}
    if not lin:
        atuais = livros.ler(base, s, F.LIVRO, F.ABA)
        if atuais:
            return dict(rel, recusou=f"o Fracttal devolveu 0 chamados e o banco tem {len(atuais)}: o livro fica como está")
    rel["gravado"] = livros.publicar(F.LIVRO, F.NOME_LIVRO, {F.ABA: (F.CAB_CHAMADO, lin)}, base=base,
                                     token=config["GRIDCO_SQL_TOKEN"], sessao=s)
    return rel


def _espera_s(agora=None) -> float:
    agora = agora or datetime.now(_BRT)
    alvo = agora.replace(minute=MINUTO_DA_HORA, second=0, microsecond=0)
    if alvo <= agora:
        alvo += timedelta(hours=1)
    return (alvo - agora).total_seconds()


def ligar(app):
    """O laço: a 1ª volta 2 min depois de subir, depois aos :50 de cada hora. Quem chama é o `campo.instalar` (app.py e
    servir.py), nunca o create_app: teste não fala com a rede."""
    if _LACO["thread"] is not None or str(app.config.get("NEXUS_CHAMADOS_PUBLICAR", "1")).strip() == "0":
        return

    def laco():
        espera = PRIMEIRA_S
        while not _LACO["parar"].wait(espera):
            with app.app_context():
                try:
                    _LACO["ultimo"] = publicar(app.config)
                    log.info("chamados no banco: %s", {k: v for k, v in _LACO["ultimo"].items() if k != "gravado"})
                except Exception as e:      # noqa: BLE001 — o laço não morre por uma volta
                    _LACO["ultimo"] = {"erro": f"{type(e).__name__}: {e}"[:300]}
                    log.exception("chamados no banco")
            espera = _espera_s()

    _LACO["thread"] = threading.Thread(target=laco, name="nexus-chamados-banco", daemon=True)
    _LACO["thread"].start()

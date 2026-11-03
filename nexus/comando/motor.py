"""O motor de insights (Fase 1, 03/11/2026): lê as fontes que o Nexus JÁ lê para as telas, roda as regras
(`regras.py`) e guarda o resultado.

Nenhuma fonte nova e nenhuma chamada ao Fracttal, à SunOp ou à PV Operation: as OS e os chamados vêm dos livros que o
Nexus publica no banco de hora em hora; o COS, do Andamento (a mesma chave das telas do COS); o PCM, do banco do robô.

A conta inteira é cara (várias fontes): fica numa cópia de 5 minutos pelo `visao._ler` (a vencida volta NA HORA e se
refaz em segundo plano). O sino do topo lê só a cópia (`do_cache`) e nunca espera uma fonte. Fonte que falha não derruba
as outras regras: vira o aviso daquela regra (`regras_status[id]["erro"]`).
"""
import logging
import threading
from datetime import datetime, timedelta, timezone

from flask import current_app

from . import regras as R

log = logging.getLogger("nexus.comando")
CHAVE = ("comando_insights",)
_BRT = timezone(timedelta(hours=-3))
_AQUECENDO = {"thread": None}


def _agora() -> datetime:
    return datetime.now(_BRT)


def _nomes():
    """usina_id -> nome, do cadastro do Nexus (sem o cadastro, o nome fica vazio e a regra usa o código)."""
    from ..campo import visao
    from ..dados import fatos as D
    try:
        por_id = visao._Base().por_id
    except Exception:            # noqa: BLE001 — o cadastro fora: as regras seguem com o código da usina
        por_id = {}
    return lambda uid: str((por_id.get(D._id(uid)) or {}).get("nome") or "")


# ── as fontes, uma por regra (cada uma pode falhar sozinha) ──────────────────────────────────────────────────────────
def _r03(cfg, nome_usina, agora):
    from ..cos import andamento as AND
    from ..cos import religamentos as RE
    if not AND.fonte(cfg).ligada:
        raise RuntimeError("a fonte do Andamento não está ligada neste servidor")
    clientes, erro = AND.clientes(cfg)
    if erro and not clientes:
        raise RuntimeError(erro)
    equips = []
    for c in clientes:
        p = RE.painel(AND.ler_ocorrencias(cfg, c, RE.DIAS_PADRAO), "todos")
        for e in (p.itens if p else []):
            equips.append({"cliente": c, "usina": e.usina, "rotulo": e.rotulo, "tag": e.tag, "total": e.total,
                           "os": e.os, "ultima": e.ultima})
    return R.r03_religamentos(equips)


def _r05(cfg, nome_usina, agora):
    from ..campo import visao
    from ..cos import normalizacoes_banco as NB
    return R.r05_sem_comunicacao(visao._livro(NB.LIVRO, NB.ABA_ABERTAS), nome_usina)


def _r06(cfg, nome_usina, agora):
    from ..campo import visao
    from ..dados import fato_chamado as FC
    from ..dados import fato_tarefa_os as FT
    return R.r06_falha_com_chamado(visao._livro(FT.LIVRO, FT.ABA), visao._livro(FC.LIVRO, FC.ABA), nome_usina,
                                   agora.date())


def _r07(cfg, nome_usina, agora):
    from ..hseq import decisoes as DEC
    from ..hseq import extintores as EXT
    lei = EXT.extintores()
    if lei.erro:
        raise RuntimeError(lei.erro)
    d = lei.dados
    todas, _seguem, _excluidos = DEC.separar(d.get("extintores") or [], d.get("nao_reconhecidos") or [], DEC.ler(cfg))
    return R.r07_extintores(EXT.por_usina(todas))


def _r09(cfg, nome_usina, agora):
    from ..pcm import fonte as PF
    lei = PF.ler(cfg)
    if not lei.dados:
        raise RuntimeError(lei.erro or "o banco do PCM não foi lido")
    bd = lei.dados
    ativa = str(bd.get("semana_ativa") or "")
    w = next((x for x in bd.get("semanas") or [] if x.get("week") == ativa), None)
    return R.r09_capacidade((w or {}).get("resumo") or {}, ativa[-3:] if ativa else "")


def _r11(cfg, nome_usina, agora):
    from ..campo import visao
    lei = visao.rondas()
    if lei.erro:
        raise RuntimeError(lei.erro)
    return R.r11_sem_ronda(lei.dados.get("cobertura") or [])


def _r13(cfg, nome_usina, agora):
    from ..campo import responsaveis as RS
    por, _info = RS.chamados(agora.date())
    return R.r13_chamado_parado(por, nome_usina)


def _n01(cfg, nome_usina, agora):
    from ..cos import andamento as AND
    from ..cos import normalizacoes as NO
    if not AND.fonte(cfg).ligada:
        raise RuntimeError("a fonte do Andamento não está ligada neste servidor")
    lei = NO.ler(cfg, agora)
    if not lei.dados:
        raise RuntimeError(lei.erro or "as normalizações não foram lidas")
    return R.n01_normalizadas([NO._item(n, agora) for n in lei.dados.get("itens") or []])


FONTES = {"R03": _r03, "R05": _r05, "R06": _r06, "R07": _r07, "R09": _r09, "R11": _r11, "R13": _r13, "N01": _n01}


def calcular() -> dict:
    """Roda as regras. {"insights": [...], "regras": {id: {"n", "erro"}}, "gerado_em"}."""
    cfg, agora = current_app.config, _agora()
    nome_usina = _nomes()
    insights, status = [], {}
    for rid, ler in FONTES.items():
        try:
            achou = ler(cfg, nome_usina, agora)
            insights += achou
            status[rid] = {"n": len(achou), "erro": ""}
        except Exception as ex:  # noqa: BLE001 — uma fonte fora não derruba as outras regras
            log.warning("insights: a regra %s não leu a fonte (%s: %s)", rid, type(ex).__name__, ex)
            status[rid] = {"n": 0, "erro": f"{type(ex).__name__}: {str(ex)[:140]}"}
    return {"insights": R.ordenar(insights), "regras": status, "gerado_em": agora}


def ler():
    """A leitura do motor (`campo.leitura.Leitura`): a cópia de 5 min, renovada por trás."""
    from ..campo import visao
    return visao._ler(CHAVE, calcular)


def do_cache():
    """Só a cópia, sem calcular nada na hora (o sino de toda página). Sem cópia, começa a conta por trás e devolve
    None: a página abre sem o número em vez de esperar as fontes."""
    from ..campo import visao
    g = visao._CACHE.get(CHAVE)
    if g is None and not current_app.config.get("TESTING"):
        _aquecer()
    return g


def _aquecer() -> None:
    t = _AQUECENDO["thread"]
    if t is not None and t.is_alive():
        return
    app = current_app._get_current_object()

    def rodar():
        with app.app_context():
            try:
                ler()
            except Exception:    # noqa: BLE001 — o sino só não aparece
                log.exception("insights: a conta por trás falhou")
    t = threading.Thread(target=rodar, name="nexus-insights", daemon=True)
    _AQUECENDO["thread"] = t
    t.start()


def das_torres(insights: list[dict], torres: set | None) -> list[dict]:
    """Os insights das torres que a pessoa vê (None = todas: o administrador)."""
    return list(insights) if torres is None else [i for i in insights if i["torre"] in torres]


def torres_da_pessoa() -> set | None:
    """As torres que o setor da pessoa vê (Base → Acessos); None = todas (o administrador, ou o portão desligado)."""
    from ..auth import setor_telas
    a = setor_telas.acesso()
    return None if a["tudo"] else {t.split("/", 1)[0] for t in a["telas"]}

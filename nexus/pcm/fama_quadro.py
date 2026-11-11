"""As OS da FAMA no Quadro da semana (fase 1, SOMBRA; 11/11/2026).

Levi, 11/11/2026: o cliente cria a OS na FAMA e ela aparece para o programador; as retroativas abertas também entram ("a
ideia é não ficarmos criando e editando e sim acompanhando"). Na fase 1 o Quadro só MOSTRA: as OS da FAMA não passam pelo
motor (ocupariam as horas das equipes e mudariam a semana oficial do Fracttal mesmo sem publicar), não se reprogramam e
não contam nas tarefas nem nas horas do dia. A fase 2 (`NEXUS_FAMA_PROGRAMA=1`, `fama_motor.py`) as põe na programação.

O que entra na semana (da segunda ao domingo):
- as ABERTAS (criada, planejada, pausada), no dia da `data_id_prevista`; a aberta com a previsão antes da segunda vai na
  segunda, marcada "Atrasada";
- as EM ANDAMENTO (em mobilização, em execução), pela mesma regra do dia, marcadas "Em andamento";
- a previsão depois do domingo é de outra semana; as outras situações (em revisão, executada, aprovada, fechada) não são
  trabalho a programar;
- a OS sem `usina_id` (ou com a usina fora do cadastro) não vira cartão: entra no aviso "N OS da FAMA sem usina ligada
  (Base → Ligações)"; a sem data prevista, no aviso dela;
- só na semana que não acabou: a situação da FAMA é a de agora, e aplicada a uma semana passada diria o que não houve.

Os filtros do Quadro valem para elas pela mesma conta (`quadro.filtrar` e `quadro.opcoes`): a equipe, o responsável e o
cliente da usina vêm das tarefas do Fracttal dela na semana (os mesmos valores dos outros cartões) e, sem tarefa, do
cadastro; o tipo é o da FAMA em português; a situação, a do Fracttal que cada uma é (`fama_os.ESTADO_DA_TAREFA`); o turno
é "Sem horário"; a busca acha o número FAMA-<id> e o título.

A possível repetição: a preventiva do Fracttal (MPA, MPS, MPM, MPQ, MPT, MPW, Preventiva) da usina em que a FAMA tem
preventiva (Preventive/Predictive) na mesma semana ganha a etiqueta "a FAMA também tem preventiva desta usina nesta
semana": só informação, para o PCM conferir antes da fase 2 (lá a preventiva das usinas da FAMA passa a ser a da FAMA).
"""
import logging
import time
from collections import Counter
from datetime import timedelta

from . import fama_os as F
from . import historico_banco as HB
from . import quadro as Q
from .semana import _norm

log = logging.getLogger("nexus.pcm")
COPIA_S = 120            # as OS e o cadastro valem 2 min em memória (o livro da FAMA muda de hora em hora)
FALHA_S = 60             # a leitura que falhou não se refaz a cada visita (o Quadro abriria devagar com o banco fora)
_LIDAS: dict = {}

SEV_ORDEM = {"critical": 0, "urgent": 1, "routine": 2, "non-urgent": 3}
SEV_TOM = {"critical": "critico", "urgent": "severo"}                       # rotina e não urgente: neutro
TIPO_COR = {"corrective": "corretiva", "preventive/predictive": "preventiva", "vegetation control": "zeladoria",
            "modules cleaning": "zeladoria", "equipments and materials movement": "outro"}
STATUS_COR = {"paused": "pausada", "under mobilization": "andamento", "under execution": "andamento"}   # o resto: "nao"
PREVENTIVAS_DO_FRACTTAL = ("mpa", "mps", "preventiva")     # as classes do `quadro.classe_tipo` que são preventiva


def ler(cfg) -> tuple[list[dict], dict]:
    """(as OS da FAMA, o cadastro das usinas), pela porta única (`fama_os._linhas_fama`). O cadastro só é lido quando há
    OS: sem a parte A nesta máquina, o Quadro não paga nada. Fora do teste, a cópia de 2 min."""
    if cfg.get("TESTING"):
        linhas = F._linhas_fama(cfg)
        return linhas, (F.cadastro_das_usinas(cfg) if linhas else {})
    agora = time.time()
    g = _LIDAS.get("ok")
    if g and agora - g[0] < COPIA_S:
        return g[1], g[2]
    f = _LIDAS.get("falha")
    if f and agora - f[0] < FALHA_S:
        raise f[1]
    try:
        linhas = F._linhas_fama(cfg)
        cad = F.cadastro_das_usinas(cfg) if linhas else {}
    except Exception as ex:      # noqa: BLE001 — quem chama diz na tela
        _LIDAS["falha"] = (agora, ex)
        raise
    _LIDAS.pop("falha", None)
    _LIDAS["ok"] = (agora, linhas, cad)
    return linhas, cad


def _vazio(ativa=False, erro=None) -> dict:
    return {"ativa": ativa, "linhas": [], "sem_usina": 0, "sem_data": 0, "preventivas": set(), "erro": erro}


def para_o_quadro(cfg, sem: dict, dia) -> dict:
    """As OS da FAMA da semana do Quadro (`da_semana`). Nunca derruba o Quadro: a leitura que falha volta como `erro` (o
    nome do erro, nunca a mensagem, que pode trazer endereço), e o Quadro sai sem elas, com o aviso."""
    if dia > HB.segunda(sem["week"]) + timedelta(days=6):
        return _vazio()
    try:
        linhas, cad = ler(cfg)
        return da_semana(linhas, sem, cad, dia) if linhas else _vazio()
    except Exception as ex:      # noqa: BLE001 — a FAMA fora do ar não derruba o Quadro
        log.warning("Quadro: as OS da FAMA não abriram (%s)", type(ex).__name__)
        return _vazio(True, type(ex).__name__)


def _moda(valores) -> str:
    c = Counter(v for v in (str(x or "").strip() for x in valores) if v)
    return c.most_common(1)[0][0] if c else ""


def da_semana(linhas: list[dict], sem: dict, cadastro: dict, hoje) -> dict:
    """{"ativa", "linhas": uma linha por OS da FAMA que vira cartão, nas chaves das linhas da semana (as que os filtros
    leem) e com o cartão em "fama", "sem_usina", "sem_data", "preventivas": os nomes (normalizados) das usinas com
    preventiva da FAMA na semana}. As regras estão no docstring do módulo."""
    seg = HB.segunda(sem["week"])
    dom = seg + timedelta(days=6)
    out = _vazio(hoje <= dom)
    if not out["ativa"]:
        return out
    # as tarefas do Fracttal de cada usina na semana (agenda e pendentes), pelo nome do Fracttal
    por_nome: dict[str, list[dict]] = {}
    for r in (sem.get("rows") or []) + (sem.get("pendentes") or []):
        por_nome.setdefault(_norm(r.get("usina")), []).append(r)
    for l in linhas:
        sit = F.situacao(l.get("status"))
        prev = F.data_de(l.get("data_id_prevista"))
        if sit is None or (prev is not None and prev > dom):
            continue
        uid = F.inteiro(l.get("usina_id"))
        cad = cadastro.get(uid) if uid else None
        if cad is None:
            out["sem_usina"] += 1
            continue
        if prev is None:
            out["sem_data"] += 1
            continue
        nomes = list(cad.get("nomes") or [])
        daqui = [r for n in nomes for r in por_nome.get(_norm(n), [])]
        nome = _moda(r.get("usina") for r in daqui) or (nomes[0] if nomes else "") or cad.get("nome") or f"Usina {uid}"
        s, t, v = _norm(l.get("status")), _norm(l.get("tipo")), _norm(l.get("severidade"))
        tipo = F.TIPO_PT.get(t) or str(l.get("tipo") or "").strip()
        atrasada = sit == "aberta" and prev < seg
        cartao = {"num": F.numero(l.get("fama_os_id")), "st": F.STATUS_PT.get(s) or str(l.get("status") or ""),
                  "stc": STATUS_COR.get(s, "nao"), "tp": tipo, "tc": TIPO_COR.get(t, "outro"),
                  "sev": F.SEVERIDADE_PT.get(v) or str(l.get("severidade") or "").strip(), "sevt": SEV_TOM.get(v, "neutro"),
                  "uc": Q.usina_curta(nome), "t": " ".join(str(l.get("titulo") or "").split()),
                  "prev": prev.strftime("%d/%m"),
                  "marca": "Atrasada" if atrasada else ("Em andamento" if sit == "andamento" else ""),
                  "marcat": "critico" if atrasada else ("alerta" if sit == "andamento" else "")}
        out["linhas"].append({
            "os_id": cartao["num"], "usina": nome, "codigo": "", "h_ini": "", "tarefa": cartao["t"], "tipo": tipo,
            "cliente": _moda(r.get("cliente") for r in daqui) or cad.get("cliente") or "",
            "cluster": _moda(r.get("cluster") for r in daqui) or cad.get("equipe") or "",
            "responsavel": _moda(r.get("responsavel") for r in daqui),
            "status": F.ESTADO_DA_TAREFA[s], "dia": "seg" if prev < seg else Q.DIAS[(prev - seg).days],
            "ordem": (prev, SEV_ORDEM.get(v, 9), F.inteiro(l.get("fama_os_id")) or 0), "fama": cartao})
        if t == F.PREVENTIVA:
            out["preventivas"].update(_norm(n) for n in nomes + [nome])
    return out


def marcar_repeticao(sem: dict, fama: dict) -> dict:
    """A semana com `fama_rep` nas preventivas do Fracttal das usinas em que a FAMA tem preventiva na semana (o
    `quadro.montar` leva a marca ao cartão e à janela). Devolve outra semana: a que entrou é a cópia em memória do arquivo
    do App (ou da planilha da rodada) e não muda."""
    nomes = fama.get("preventivas") or set()
    if not nomes:
        return sem
    rows, mudou = [], False
    for r in sem.get("rows") or []:
        if Q.classe_tipo(r.get("tipo")) in PREVENTIVAS_DO_FRACTTAL and _norm(r.get("usina")) in nomes:
            r, mudou = dict(r, fama_rep=True), True
        rows.append(r)
    return dict(sem, rows=rows) if mudou else sem


def no_quadro(q: dict, sem: dict, fama: dict, filtros: dict) -> None:
    """Põe no quadro montado (`quadro.montar`) os cartões da FAMA de cada dia, filtrados como os outros, e o resumo em
    `q["fama"]` (None quando a semana não tem nada da FAMA: a tela fica como era). O dia que só a FAMA tem (o sábado da
    OS prevista para ele) ganha a coluna, como os dias que a semana tem; as contas de tarefas e horas não mudam."""
    q["fama"] = None
    linhas = fama.get("linhas") or []
    if not fama.get("ativa") or not (linhas or fama.get("sem_usina") or fama.get("sem_data") or fama.get("erro")):
        return
    sel = Q.filtrar(linhas, filtros)
    por_dia: dict[str, list[dict]] = {}
    for r in sorted(sel, key=lambda r: r["ordem"]):
        por_dia.setdefault(r["dia"], []).append(r["fama"])
    seg = HB.segunda(sem["week"])
    colunas = {c["id"]: c for c in q["colunas"]}
    dias_da_fama = {r["dia"] for r in linhas}
    novas = []
    for i, d in enumerate(Q.DIAS):
        c = colunas.get(d)
        if c is None and d in dias_da_fama:
            c = {"id": d, "nome": Q.NOMES_DIA[d], "n": 0, "horas": Q._horas(0), "carga": 0.0, "pico": False,
                 "data": (sem.get("dates") or {}).get(d) or (seg + timedelta(days=i)).strftime("%d/%m"),
                 "novas": 0 if q.get("tem_criacao") else None, "cartoes": [], "ocultos": 0}
        if c is not None:
            c["fama"] = por_dia.get(d, [])
            novas.append(c)
    q["colunas"] = novas
    q["fama"] = {"total": len(sel), "total_semana": len(linhas), "sem_usina": fama.get("sem_usina", 0),
                 "sem_data": fama.get("sem_data", 0), "erro": fama.get("erro"),
                 "mostra": bool(linhas or fama.get("sem_usina") or fama.get("sem_data"))}

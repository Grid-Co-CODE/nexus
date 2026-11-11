"""As OS da FAMA no Quadro da semana (fase 1, SOMBRA; 11/11/2026).

Levi, 11/11/2026: o cliente cria a OS na FAMA e ela aparece para o programador; as retroativas abertas também entram ("a
ideia é não ficarmos criando e editando e sim acompanhando"). Na fase 1 o Quadro só MOSTRA: as OS da FAMA não passam pelo
motor (ocupariam as horas das equipes e mudariam a semana oficial do Fracttal mesmo sem publicar), não se reprogramam e
não contam nas tarefas nem nas horas do dia. A fase 2 (`NEXUS_FAMA_PROGRAMA=1`, `fama_motor.py`) as põe na programação.

O que entra na semana (da segunda ao domingo):
- as ABERTAS (criada, planejada, pausada), no dia da `data_id_prevista`; a aberta com a previsão antes da segunda vai
  num bloco recolhido da segunda ("N OS da FAMA atrasadas");
- as EM ANDAMENTO (em mobilização, em execução), pela mesma regra do dia, marcadas "Em andamento";
- a previsão depois do domingo é de outra semana; as outras situações (em revisão, executada, aprovada, fechada) não são
  trabalho a programar;
- a OS sem `usina_id` (ou com a usina fora do cadastro) não vira cartão: entra no aviso "N OS da FAMA sem usina ligada
  (Base → Ligações)"; a sem data prevista, no aviso dela;
- só na semana que não acabou: a situação da FAMA é a de agora, e aplicada a uma semana passada diria o que não houve.
Os cartões da FAMA vêm DEPOIS das tarefas oficiais da coluna, com o mesmo teto (`quadro.TETO_CARTOES`) e o "+N"
(revisão de 11/11/2026: no alto da coluna, 30 atrasadas empurravam a programação para fora da vista).

Os filtros do Quadro valem para elas pela mesma conta (`quadro.filtrar` e `quadro.opcoes`), e as listas contam as OS da
FAMA à parte das tarefas: a equipe, o responsável e o cliente da usina vêm das tarefas do Fracttal dela na semana (os
mesmos valores dos outros cartões) e, sem tarefa, do cadastro (o responsável é o gestor de contrato da ficha, escrito como
a semana escreve o mesmo nome: o gestor que entra filtrado não perde a OS da usina sem tarefa); o tipo é o da FAMA em
português; a situação, a do Fracttal que cada uma é (`fama_os.ESTADO_DA_TAREFA`); o turno é "Sem horário"; a busca acha
o número FAMA-<id> e o título.

A velocidade (revisão de 11/11/2026, item 1): o pedido da tela NUNCA lê o banco. As OS e o cadastro ficam numa cópia em
memória, servida na hora; vencida (`COPIA_S`), a visita seguinte a renova por trás, uma renovação de cada vez (o voo
único, como o `_renovar` da `campo/visao.py`), e recebe a cópia de antes. A renovação confere antes o `updated_at` do livro
(a listagem do banco): se não mudou, a cópia fica e nenhuma página é relida. Sem cópia nenhuma (a 1ª visita depois de
subir), o Quadro abre sem a FAMA, com o aviso `LENDO`. A falha não trava: com a cópia boa, ela fica; sem cópia, o aviso
de erro, e a próxima tentativa só depois de `FALHA_S`.

O frescor: o batimento da carga (`fama_os.Lido.gerado_em`) vira "OS da FAMA lidas em DD/MM HH:MM"; com mais de
`fama_os.FRESCOR_H`, o aviso "a leitura da FAMA parou: o que aparece pode estar velho".

A possível repetição: a preventiva do Fracttal (MPA, MPS, MPM, MPQ, MPT, MPW, Preventiva) da usina em que a FAMA tem
preventiva (Preventive/Predictive) na mesma semana ganha a etiqueta "a FAMA também tem preventiva desta usina nesta
semana": só informação, para o PCM conferir antes da fase 2 (lá a preventiva das usinas da FAMA passa a ser a da FAMA).
"""
import logging
import threading
import time
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta

from flask import current_app

from . import fama_os as F
from . import historico_banco as HB
from . import quadro as Q
from .semana import _norm

log = logging.getLogger("nexus.pcm")
COPIA_S = 120            # a cópia vale 2 min: vencida, a visita seguinte a renova por trás e recebe a de antes na hora
COMPLETA_S = 3600        # mesmo com o livro igual, de hora em hora a cópia é relida inteira (o cadastro muda: o de-para,
                         # o gestor; o batimento diário do livro sozinho deixaria o cadastro um dia sem renovar)
FALHA_S = 60             # a renovação que falhou não se repete antes disso: o banco fora não vira laço
LENDO = "Lendo as OS da FAMA: recarregue em alguns segundos."

SEV_ORDEM = {"critical": 0, "urgent": 1, "routine": 2, "non-urgent": 3}
SEV_TOM = {"critical": "critico", "urgent": "severo"}                       # rotina e não urgente: neutro
TIPO_COR = {"corrective": "corretiva", "preventive/predictive": "preventiva", "vegetation control": "zeladoria",
            "modules cleaning": "zeladoria", "equipments and materials movement": "outro"}
STATUS_COR = {"paused": "pausada", "under mobilization": "andamento", "under execution": "andamento"}   # o resto: "nao"
PREVENTIVAS_DO_FRACTTAL = ("mpa", "mps", "preventiva")     # as classes do `quadro.classe_tipo` que são preventiva


# ── a cópia em memória e a renovação por trás ────────────────────────────────────────────────────────────────────
@dataclass
class _Copia:
    linhas: list
    cadastro: dict
    gerado_em: str | None
    versao: str | None           # o `updated_at` do livro quando foi lido
    conferida_em: float          # a última conferência (o livro igual também conta)
    lida_em: float               # a última leitura inteira


_TRAVA = threading.Lock()
_ESTADO: dict = {"copia": None, "erro": None, "erro_em": 0.0, "fio": None, "voltas": 0}


def limpar() -> None:
    with _TRAVA:
        _ESTADO.update(copia=None, erro=None, erro_em=0.0, fio=None, voltas=0)


def voltas() -> int:
    """Quantas renovações começaram desde o `limpar` (o voo único, nos testes)."""
    return _ESTADO["voltas"]


def esperar(timeout: float) -> bool:
    """Espera a renovação em andamento (os testes e a ferramenta de prova). True quando não há nenhuma rodando."""
    fio = _ESTADO["fio"]
    if fio is not None:
        fio.join(timeout)
        return not fio.is_alive()
    return True


def _renovar(cfg, app) -> bool:
    """Uma renovação de cada vez, por trás; a que falhou só se repete depois de `FALHA_S`. True = esta chamada a começou."""
    with _TRAVA:
        fio = _ESTADO["fio"]
        if fio is not None and fio.is_alive():
            return False
        if _ESTADO["erro"] and time.time() - _ESTADO["erro_em"] < FALHA_S:
            return False
        fio = threading.Thread(target=_rodar, args=(cfg, app), daemon=True, name="nexus-pcm-fama")
        _ESTADO["fio"] = fio
        _ESTADO["voltas"] += 1
    fio.start()
    return True


def _rodar(cfg, app) -> None:
    try:
        with app.app_context():
            from ..dados import conexao, livros
            from ..dados import fato_os_fama as FOF
            agora = time.time()
            base, sessao = conexao.banco_de(cfg)
            versao = livros.atualizado_em(base, sessao, FOF.LIVRO)
            c = _ESTADO["copia"]
            if c is not None and versao and versao == c.versao and agora - c.lida_em < COMPLETA_S:
                c.conferida_em = agora           # o livro não mudou: a cópia fica, sem reler as páginas
            else:
                lido = F._linhas_fama(cfg)
                usinas = {F.inteiro(l.get("usina_id")) for l in lido.linhas} - {None}
                cad = F.cadastro_das_usinas(cfg, gestores_de=usinas) if lido.linhas else {}
                _ESTADO["copia"] = _Copia(lido.linhas, cad, lido.gerado_em, versao, agora, agora)
        _ESTADO["erro"] = None
    except Exception as ex:      # noqa: BLE001 — o nome do erro, nunca a mensagem (pode trazer endereço)
        log.warning("Quadro: as OS da FAMA não abriram (%s)", type(ex).__name__)
        _ESTADO["erro"], _ESTADO["erro_em"] = type(ex).__name__, time.time()


def ler(cfg, app=None) -> dict:
    """{"estado": "ok" | "lendo" | "erro", "linhas", "cadastro", "gerado_em", "erro"}, sem ler o banco: a cópia na hora e,
    vencida, a renovação por trás (o docstring do módulo). No teste (TESTING), a porta direto: ela devolve as linhas da
    configuração e não vai ao banco."""
    if cfg.get("TESTING"):
        lido = F._linhas_fama(cfg)
        return {"estado": "ok", "linhas": lido.linhas, "gerado_em": lido.gerado_em, "erro": None,
                "cadastro": F.cadastro_das_usinas(cfg) if lido.linhas else {}}
    c = _ESTADO["copia"]
    comecou = False
    if c is None or time.time() - c.conferida_em >= COPIA_S:
        comecou = _renovar(cfg, app or current_app._get_current_object())
    if c is None:
        # a leitura que esta visita começou está em andamento (mesmo que já tenha falhado, o que esta visita diz é "lendo");
        # sem leitura nova (a que falhou há menos de FALHA_S), o erro dela
        erro = None if comecou else _ESTADO["erro"]
        return {"estado": "erro" if erro else "lendo", "linhas": [], "cadastro": {}, "gerado_em": None, "erro": erro}
    return {"estado": "ok", "linhas": c.linhas, "cadastro": c.cadastro, "gerado_em": c.gerado_em, "erro": None}


# ── as OS da semana ──────────────────────────────────────────────────────────────────────────────────────────────
def _vazio(ativa=False, erro=None, lendo=False) -> dict:
    return {"ativa": ativa, "linhas": [], "sem_usina": 0, "sem_data": 0, "preventivas": set(), "erro": erro,
            "lendo": lendo, "lidas_em": "", "velho": False}


def para_o_quadro(cfg, sem: dict, dia) -> dict:
    """As OS da FAMA da semana do Quadro (`da_semana`). Nunca derruba o Quadro nem o faz esperar: a 1ª leitura em
    andamento volta como `lendo`, a que falhou como `erro` (o nome do erro, nunca a mensagem), e o Quadro sai sem elas,
    com o aviso."""
    if dia > HB.segunda(sem["week"]) + timedelta(days=6):
        return _vazio()
    try:
        r = ler(cfg)
        if r["estado"] != "ok":
            return _vazio(True, erro=r["erro"], lendo=r["estado"] == "lendo")
        return da_semana(r["linhas"], sem, r["cadastro"], dia, gerado_em=r["gerado_em"]) if r["linhas"] else _vazio()
    except Exception as ex:      # noqa: BLE001 — a FAMA fora do ar não derruba o Quadro
        log.warning("Quadro: as OS da FAMA não abriram (%s)", type(ex).__name__)
        return _vazio(True, type(ex).__name__)


def _moda(valores) -> str:
    c = Counter(v for v in (str(x or "").strip() for x in valores) if v)
    return c.most_common(1)[0][0] if c else ""


def _como_na_semana(nome, da_semana: set) -> str:
    """O nome do cadastro escrito como a semana o escreve (o filtro compara o texto): o mesmo sem acento, caixa e espaço
    a mais, ou o primeiro e o último nome iguais (a regra do `telas._gestor_da_sessao`); sem par, como veio."""
    alvo = _norm(nome).split()
    if not alvo:
        return ""
    for r in sorted(da_semana):
        n = _norm(r).split()
        if n == alvo or (len(alvo) >= 2 and len(n) >= 2 and n[0] == alvo[0] and n[-1] == alvo[-1]):
            return r
    return " ".join(str(nome).split())


def da_semana(linhas: list[dict], sem: dict, cadastro: dict, hoje, gerado_em=None, agora=None) -> dict:
    """{"ativa", "linhas": uma linha por OS da FAMA que vira cartão, nas chaves das linhas da semana (as que os filtros
    leem) e com o cartão em "fama", "sem_usina", "sem_data", "preventivas": os nomes (normalizados) das usinas com
    preventiva da FAMA na semana, "lidas_em" e "velho": o frescor do batimento}. As regras estão no docstring do módulo."""
    seg = HB.segunda(sem["week"])
    dom = seg + timedelta(days=6)
    out = _vazio(hoje <= dom)
    if not out["ativa"]:
        return out
    out.update(lidas_em=F.quando(gerado_em), velho=F.velho(gerado_em, agora))
    # as tarefas do Fracttal de cada usina na semana (agenda e pendentes), pelo nome do Fracttal
    por_nome: dict[str, list[dict]] = {}
    for r in (sem.get("rows") or []) + (sem.get("pendentes") or []):
        por_nome.setdefault(_norm(r.get("usina")), []).append(r)
    responsaveis = {str(r.get("responsavel") or "").strip() for r in sem.get("rows") or []} - {""}
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
                  "prev": prev.strftime("%d/%m"), "atrasada": atrasada,
                  "marca": "Atrasada" if atrasada else ("Em andamento" if sit == "andamento" else ""),
                  "marcat": "critico" if atrasada else ("alerta" if sit == "andamento" else "")}
        out["linhas"].append({
            "os_id": cartao["num"], "usina": nome, "codigo": "", "h_ini": "", "tarefa": cartao["t"], "tipo": tipo,
            "cliente": _moda(r.get("cliente") for r in daqui) or cad.get("cliente") or "",
            "cluster": _moda(r.get("cluster") for r in daqui) or cad.get("equipe") or "",
            "responsavel": (_moda(r.get("responsavel") for r in daqui)
                            or _como_na_semana(cad.get("responsavel"), responsaveis)),
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


def no_quadro(q: dict, sem: dict, fama: dict, filtros: dict, todos: bool = False) -> None:
    """Põe no quadro montado (`quadro.montar`) os cartões da FAMA de cada dia, filtrados como os outros, e o resumo em
    `q["fama"]` (None quando a semana não tem nada da FAMA: a tela fica como era). Em cada coluna, a FAMA vem depois das
    tarefas, com o mesmo teto (`quadro.TETO_CARTOES`; `todos` = sem teto) e o que passou dele contado; as atrasadas, no
    bloco recolhido da segunda. O dia que só a FAMA tem (o sábado da OS prevista para ele) ganha a coluna, como os dias
    que a semana tem; as contas de tarefas e horas não mudam."""
    q["fama"] = None
    linhas = fama.get("linhas") or []
    if not fama.get("ativa") or not (linhas or fama.get("sem_usina") or fama.get("sem_data") or fama.get("erro")
                                     or fama.get("lendo") or fama.get("velho")):
        return
    sel = Q.filtrar(linhas, filtros)
    teto = None if todos else Q.TETO_CARTOES
    do_dia: dict[str, list[dict]] = {}
    atrasadas: dict[str, list[dict]] = {}
    for r in sorted(sel, key=lambda r: r["ordem"]):
        (atrasadas if r["fama"]["atrasada"] else do_dia).setdefault(r["dia"], []).append(r["fama"])
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
        if c is None:
            continue
        fs, at = do_dia.get(d, []), atrasadas.get(d, [])
        c.update(fama=fs[:teto], fama_ocultos=len(fs) - len(fs[:teto]), fama_atrasadas=at[:teto],
                 fama_atrasadas_n=len(at), fama_atrasadas_ocultas=len(at) - len(at[:teto]), fama_n=len(fs) + len(at))
        novas.append(c)
    q["colunas"] = novas
    q["fama"] = {"total": len(sel), "total_semana": len(linhas), "sem_usina": fama.get("sem_usina", 0),
                 "sem_data": fama.get("sem_data", 0), "erro": fama.get("erro"), "lendo": fama.get("lendo", False),
                 "lidas_em": fama.get("lidas_em", ""), "velho": fama.get("velho", False),
                 "mostra": bool(linhas or fama.get("sem_usina") or fama.get("sem_data"))}

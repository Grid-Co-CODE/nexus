"""O que foi feito em cada usina em cada mês, guardado depois que as fontes esquecem (18/11/2026).

Levi, 18/11/2026: "O insights e todo o prontuário deve funcionar por mês! Começando por outubro [...] o que foi feito no
ativo". O prontuário do mês fechado lê as rondas, as tarefas executadas, a zeladoria, as PT e os chamados das fontes, e
elas guardam 90 dias: outubro sumiria delas em janeiro de 2027. À proposta de guardar o fechamento de cada mês, ele deu
o "Ok" e depois: "faça funcionar".

- **Grão:** 1 linha = 1 usina × 1 mês × 1 tipo de atividade. Foto periódica.
- **De onde vem:** dos fatos que a carga já monta ou que já estão no banco (regra 12: só o que as duas máquinas leem
  igual): `fato_fechamento` (as tarefas executadas, pelo tipo da OS; a devolvida não conta), `fato_ronda` (pelo tipo da
  ronda), `fato_pt` (a 1ª linha de cada PT), `fato_tarefa_os` (a zeladoria finalizada, contada em dias) e `fato_chamado`
  (os abertos no mês e os finalizados no mês).
- **O mês congela:** a cada carga, só os meses ABERTOS são recalculados (`meses_abertos`: o dia 1º do mês está a até
  `JANELA_DIAS` dias, com folga sobre os 90 das fontes, então o mês inteiro ainda está nelas). O mês que saiu da janela
  fica como foi gravado, para sempre (`mesclar`). O mês que já estava incompleto nas fontes na 1ª carga nunca entra: não
  se guarda mês pela metade.
- **O fato não encolhe:** a linha de um mês aberto que está no banco e sumiu da conta (a tarefa que foi devolvida) fica,
  com zero. O livro declara `so_cresce` no catálogo, e a trava do `livros.publicar` recusa a gravação que encolheria.
- **Sem nome, sem texto livre:** só IDs e contagens (regra 8).
"""
from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import defaultdict
from datetime import date, timedelta

from . import fatos
from .fato_ronda import conferir_grao
from .fatos import _pct as pct

LIVRO, ABA = "nexus_atividade_mes", "fato_atividade_usina_mes"
NOME_LIVRO = "Nexus · o que foi feito em cada usina em cada mês (rondas, tarefas, zeladoria, PT e chamados)"
FATO, TIPO = "atividade_usina_mes", "snapshot_periodico"
GRAO = "1 linha = 1 usina × 1 mês × 1 tipo de atividade (ronda, tarefa executada, zeladoria, PT, chamado de garantia)"
CHAVE = ("atividade_id",)
FONTES = (("nexus_fatos", "fato_fechamento"), ("nexus_fatos", "fato_ronda"), ("nexus_fatos", "fato_pt"),
          ("nexus_os", "fato_tarefa_os"), ("nexus_chamados", "fato_chamado"))
LIVRO_ORIGEM = "nexus_fatos + nexus_os + nexus_chamados"
JANELA_ORIGEM = "90 dias (as fontes); este fato guarda o mês depois que ele sai delas"
JANELA_DIAS = 85                 # o mês é recalculado enquanto o dia 1º dele está a até 85 dias (as fontes guardam 90)
LIGADA_POR = "fato de origem"    # a usina já vem ligada no fato de onde a linha saiu

CAB = ["atividade_id", "data_id_mes", "usina_id", "usina_ligada_por", "atividade", "eventos_qtd", "os_qtd",
       "calculado_em"]
# (coluna, unidade, soma). Os eventos somam (entre tipos, usinas e meses). As OS não somam entre meses: a mesma OS pode
# ter tarefa fechada em dois meses.
MEDIDAS = (("eventos_qtd", "qtd", "aditiva"), ("os_qtd", "qtd", "nao"))
CAB_ATUALIZACAO = ["gerado_em", "maquina", "duracao_s", "linhas", "sha_linhas", "meses_recalculados",
                   "meses_guardados", "como_ler"]
COMO_LER = ("1 linha = 1 usina × 1 mês × 1 atividade; data_id_mes = o dia 1º do mês (AAAAMM01); atividade: ronda_<tipo>, "
            "tarefa_<tipo da OS>, zeladoria (eventos = dias), pt, chamado_aberto, chamado_finalizado; o mês fora da janela "
            "das fontes fica como foi gravado")
_I = {c: i for i, c in enumerate(CAB)}
_INTEIRAS = ("data_id_mes", "usina_id", "eventos_qtd", "os_qtd")


# ── os meses ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def meses_abertos(hoje: date, janela_dias: int = JANELA_DIAS) -> list[int]:
    """[AAAAMM] dos meses que ainda cabem INTEIROS nas fontes, do mais antigo ao vigente: o dia 1º do mês está a até
    `janela_dias` dias de hoje. São os recalculados nesta carga; os outros ficam como estão no banco."""
    limite = hoje - timedelta(days=janela_dias)
    out, a, m = [], hoje.year, hoje.month
    while date(a, m, 1) >= limite:
        out.append(a * 100 + m)
        a, m = (a, m - 1) if m > 1 else (a - 1, 12)
    return sorted(out)


def _int(v) -> int | None:
    """O inteiro de um valor que o banco pode devolver como número, texto ("20261005", "20261005.0") ou vazio."""
    if v is None or isinstance(v, bool):
        return None
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return None


def _mes(data_id) -> int | None:
    d = _int(data_id)
    return d // 100 if d and 19000101 <= d <= 99991231 else None


def _um(v) -> bool:
    return str(v).strip() in ("1", "1.0", "True", "true")


def _slug(v) -> str:
    t = unicodedata.normalize("NFKD", str(v or "")).encode("ascii", "ignore").decode().lower()
    return "_".join("".join(c if c.isalnum() else " " for c in t).split())


def _dicts(tabela) -> list[dict]:
    """As linhas como dicionários: aceita a aba em memória da carga, (cabeçalho, linhas), e a lida do banco (dicts)."""
    if isinstance(tabela, tuple) and len(tabela) == 2:
        cab, linhas = tabela
        return [dict(zip(cab, l)) for l in linhas]
    return list(tabela or [])


# ── a conta ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def montar(fechamento, ronda, pt, tarefas, chamados, abertos, agora_iso: str) -> list[list]:
    """As linhas dos meses ABERTOS, contadas das cinco fontes (cada uma: a aba em memória ou as linhas do banco).
    Linha sem usina ou sem data não entra (não se chuta: regra 4); mês que não é aberto não é contado."""
    abertos = set(abertos)
    cont: dict = defaultdict(lambda: {"n": 0, "os": set(), "dias": set()})

    def soma(usina, data_id, atividade, os_=None, dia=None):
        uid, mes = _int(usina), _mes(data_id)
        if uid is None or mes is None or mes not in abertos:
            return
        c = cont[(uid, mes, atividade)]
        c["n"] += 1
        o = fatos.os_do_fato(os_)
        if o is not None:
            c["os"].add(o)
        if dia is not None:
            c["dias"].add(_int(dia))

    for x in _dicts(fechamento):
        if not _um(x.get("devolvida")):
            soma(x.get("usina_id"), x.get("data_id"), "tarefa_" + (_slug(x.get("tipo_os")) or "sem_tipo"), x.get("os"))
    for x in _dicts(ronda):
        soma(x.get("usina_id"), x.get("data_id"), "ronda_" + (_slug(x.get("tipo_ronda")) or "sem_tipo"), x.get("os"))
    for x in _dicts(pt):
        if _um(x.get("primeira_linha_da_pt")):
            soma(x.get("usina_id"), x.get("data_id_criacao"), "pt", x.get("os"))
    for x in _dicts(tarefas):
        if str(x.get("tipo_tarefa") or "") == "zeladoria" and str(x.get("estado_tarefa") or "") == "finalizada":
            soma(x.get("usina_id"), x.get("data_id_fim"), "zeladoria", x.get("os"), dia=x.get("data_id_fim"))
    for x in _dicts(chamados):
        soma(x.get("usina_id"), x.get("data_id_abertura"), "chamado_aberto", x.get("os"))
        if str(x.get("situacao") or "") == "concluido":
            soma(x.get("usina_id"), x.get("data_id_fim"), "chamado_finalizado", x.get("os"))
    out = []
    for (uid, mes, atividade), c in cont.items():
        # a zeladoria conta os DIAS em que foi feita (a página do mês mostra as datas), não as tarefas
        eventos = len(c["dias"]) if atividade == "zeladoria" else c["n"]
        out.append([id_da_linha(uid, mes, atividade), mes * 100 + 1, uid, LIGADA_POR, atividade, eventos, len(c["os"]),
                    agora_iso])
    out.sort(key=lambda l: (l[_I["data_id_mes"]], l[_I["usina_id"]], l[_I["atividade"]]))
    conferir_grao(out, CAB, "atividade_id")
    return out


def id_da_linha(usina_id: int, mes: int, atividade: str) -> str:
    return hashlib.sha1(f"atv|{usina_id}|{mes}|{atividade}".encode("utf-8")).hexdigest()[:16]


# ── a mescla com o que está no banco (o mês que congela) ─────────────────────────────────────────────────────────────
def _linha_tipada(l) -> list:
    lin = [l.get(c) for c in CAB] if isinstance(l, dict) else list(l)
    return [(_int(v) if c in _INTEIRAS else (None if v is None else str(v))) for c, v in zip(CAB, lin)]


def mesclar(no_banco, novas: list, abertos, agora_iso: str) -> list[list]:
    """O fato que vai para o banco: as linhas dos meses FECHADOS como estão lá, mais as dos meses abertos recalculadas.
    A linha de mês aberto que está no banco e sumiu da conta fica, com zero (o fato não encolhe). A linha que não mudou
    guarda o `calculado_em` que já tinha: a API guarda o histórico de cada linha que muda, e a hora da conta não é
    mudança."""
    abertos = set(abertos)
    antes = {}
    for l in no_banco or []:
        lin = _linha_tipada(l)
        if lin[_I["atividade_id"]]:
            antes[lin[_I["atividade_id"]]] = lin
    calculadas = {l[_I["atividade_id"]]: list(l) for l in novas}
    out = []
    for aid, lin in antes.items():
        mes = (lin[_I["data_id_mes"]] or 0) // 100
        if mes not in abertos:
            out.append(lin)                                   # o mês congelado: intocado
        elif aid not in calculadas:
            calculadas[aid] = lin[:_I["eventos_qtd"]] + [0, 0, agora_iso]
    i_c = _I["calculado_em"]
    for aid, lin in calculadas.items():
        a = antes.get(aid)
        if a is not None and a[i_c] and a[:i_c] == lin[:i_c]:
            lin = lin[:i_c] + [a[i_c]]
        out.append(lin)
    out.sort(key=lambda l: (l[_I["data_id_mes"]] or 0, l[_I["usina_id"]] or 0, l[_I["atividade"]] or ""))
    conferir_grao(out, CAB, "atividade_id")
    return out


def sha_linhas(linhas: list) -> str:
    """A impressão digital do fato sem o `calculado_em`: a carga grava só quando uma contagem mudou."""
    i = _I["calculado_em"]
    h = hashlib.sha1()
    for l in sorted([str(v) for v in x[:i]] for x in linhas):
        h.update("\x1f".join(l).encode("utf-8"))
        h.update(b"\x1e")
    return h.hexdigest()


def meses_das_linhas(linhas: list) -> list[int]:
    return sorted({(l[_I["data_id_mes"]] or 0) // 100 for l in linhas if l[_I["data_id_mes"]]})


def qualidade(linhas: list, agora_iso: str, extra: dict | None = None) -> dict:
    """A linha da aba `qualidade` (`fatos.CAB_QUALIDADE`): este fato nasce de fatos já ligados, então a usina e a data
    têm de estar em 100%; a equipe, a pessoa e o equipamento não são dimensões dele (vazio, não 0%)."""
    n = len(linhas)
    com_data = sum(1 for l in linhas if l[_I["data_id_mes"]] is not None)
    com_usina = sum(1 for l in linhas if l[_I["usina_id"]] is not None)
    q = dict.fromkeys(fatos.CAB_QUALIDADE)
    q.update(fato=FATO, livro_origem=LIVRO_ORIGEM, linhas=n, com_data=com_data, com_usina=com_usina,
             pct_data=pct(com_data, n), pct_usina=pct(com_usina, n), gerado_em=agora_iso,
             extra=json.dumps(extra or {}, ensure_ascii=False, sort_keys=True))
    return q


def tabelas(linhas: list, iso: str, maquina: str, recalculados, extra: dict | None = None) -> dict:
    """As três abas do livro: o fato, a qualidade e a atualização (com o sha das linhas, para a carga não regravar o que
    não mudou)."""
    q = qualidade(linhas, iso, extra)
    meses = meses_das_linhas(linhas)
    rec = sorted(set(recalculados) & set(meses))
    return {ABA: (CAB, linhas),
            "qualidade": (fatos.CAB_QUALIDADE, [[q.get(c) for c in fatos.CAB_QUALIDADE]]),
            "atualizacao": (CAB_ATUALIZACAO, [[iso, maquina, None, len(linhas), sha_linhas(linhas),
                                               ", ".join(str(m) for m in rec),
                                               ", ".join(str(m) for m in meses if m not in rec), COMO_LER]])}


# ── a leitura (o prontuário do mês que já saiu das fontes) ───────────────────────────────────────────────────────────
def do_mes(linhas, usina_id: int, mes: int) -> dict[str, tuple[int, int]]:
    """{atividade: (eventos, OS)} da usina no mês (AAAAMM), das linhas lidas do banco. Vazio: o fato não tem aquele mês
    daquela usina (não quer dizer zero: quer dizer que não foi guardado)."""
    out = {}
    for l in linhas or []:
        lin = _linha_tipada(l)
        if lin[_I["usina_id"]] == int(usina_id) and (lin[_I["data_id_mes"]] or 0) // 100 == int(mes):
            out[lin[_I["atividade"]]] = (lin[_I["eventos_qtd"]] or 0, lin[_I["os_qtd"]] or 0)
    return out


def rondas_por_mes(linhas) -> tuple[dict, set]:
    """({(usina_id, AAAAMM): rondas feitas}, {os meses AAAAMM que o fato tem}), numa passada só (a Visão gerencial pede
    as rondas das 144 usinas de cada mês fechado: `do_mes` usina a usina relia o fato inteiro 144 vezes)."""
    rondas, meses = {}, set()
    for l in linhas or []:
        lin = _linha_tipada(l)
        mes = (lin[_I["data_id_mes"]] or 0) // 100
        meses.add(mes)
        if str(lin[_I["atividade"]] or "").startswith("ronda_"):
            chave = (lin[_I["usina_id"]], mes)
            rondas[chave] = rondas.get(chave, 0) + (lin[_I["eventos_qtd"]] or 0)
    return rondas, meses


def rondas_do_mes(rondas: dict, meses: set, usina_id: int, mes: int):
    """As rondas da usina no mês (AAAAMM). O mês que o fato tem é a conta de verdade: a usina sem linha de ronda (ou sem
    atividade nenhuma, que não ganha linha) fez ZERO ronda. O mês que o fato não tem não foi guardado: None, nunca zero."""
    return rondas.get((int(usina_id), int(mes)), 0) if int(mes) in meses else None

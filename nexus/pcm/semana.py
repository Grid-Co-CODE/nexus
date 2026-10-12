"""Regras puras da programação da semana (formato do banco_dados.json do painel do PCM), usadas pelas telas Tarefas e
OS, Quadro da semana e Gerar a semana. A tela Semana (o resumo e as horas por equipe e dia) saiu em 12/10/2026 com o
código dela (Levi: "pode excluir essa seção e o código dela").

Uma linha do arquivo é UMA tarefa programada. A equipe é o `cluster` (o nome da aba da planilha do PCM, "SP Leste 02"),
o dia vem por extenso ("Terça-feira") e o status é o do Fracttal ("Finalizados", "Não Iniciada", "Em progresso",
"pausado").
"""
import unicodedata
from collections import Counter

DIAS = ("seg", "ter", "qua", "qui", "sex")
NOMES_DIA = {"seg": "Segunda", "ter": "Terça", "qua": "Quarta", "qui": "Quinta", "sex": "Sexta"}
# A MPA roda na janela da noite (15:30 → 01:30; o gerador trunca o dia às 15:30): não é tarefa fora do horário.
TIPO_NOITE = "mpa"
# A jornada do gerador é 07:00–17:00. Tarefa que começa fora disso (sem contar a MPA, que tem janela própria, e a
# zeladoria, que é terceirizada) é sinal de cascata ou pino que empurrou a tarefa para a madrugada: na semana 40
# foram 264 de 1.373 (a maioria MPM). Pode haver turno noturno pedido pelo PCM no meio — a tela mostra, o PCM julga.
JORNADA = ("07:00", "17:00")


def fora_do_horario(linha) -> bool:
    h = str(linha.get("h_ini") or "")
    if not h or _norm(linha.get("tipo")) == TIPO_NOITE or _norm(linha.get("paralelo")) == "sim":
        return False
    return h < JORNADA[0] or h >= JORNADA[1]
FEITA = "finalizados"
ANDAMENTO = ("em progresso", "pausado")
NAO_INICIADA = "nao iniciada"


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower().strip()
    return " ".join(s.split())


def dia_curto(dia) -> str:
    """ "Terça-feira (29/09) [NOTURNO]" -> "ter". Vazio se não for dia útil da semana."""
    n = _norm(dia)
    return next((d for d in DIAS if n.startswith(d)), "")


def situacao(linha) -> str:
    """feita / andamento / nao_iniciada / outra — o status do Fracttal em três baldes."""
    st = _norm(linha.get("status") or linha.get("status_bd"))
    if st == FEITA:
        return "feita"
    if st in ANDAMENTO:
        return "andamento"
    if st == NAO_INICIADA:
        return "nao_iniciada"
    return "outra"


def semanas(dados) -> list[dict]:
    ativa = (dados or {}).get("semana_ativa")
    L = [{"week": s.get("week"), "num": s.get("num"), "label": s.get("label") or s.get("week"),
          "geradaEm": s.get("geradaEm"), "ativa": s.get("week") == ativa}
         for s in (dados or {}).get("semanas") or [] if s.get("week")]
    return sorted(L, key=lambda s: str(s["week"]), reverse=True)


def achar(dados, week: str | None = None) -> dict | None:
    """A semana pedida; sem pedir, a ativa (a que o App mostra) ou, na falta dela, a mais nova."""
    todas = [s for s in (dados or {}).get("semanas") or [] if s.get("week")]
    if week:
        return next((s for s in todas if s["week"] == week), None)
    ativa = (dados or {}).get("semana_ativa")
    return next((s for s in todas if s["week"] == ativa), None) or \
        (max(todas, key=lambda s: str(s["week"])) if todas else None)


def facetas(sem, filtros: dict) -> dict:
    """{filtro: Counter(valor -> tarefas)} de equipe, dia, status e tipo, cada um contado com os OUTROS filtros
    aplicados (Levi, 09/10/2026: "Os filtros tem que se auto filtrar também"): escolhida a equipe, o Tipo só lista os
    tipos dela. O filtro não conta a si mesmo, para dar para trocar de equipe sem limpar o resto."""
    valor_de = {"equipe": lambda r: str(r.get("cluster") or ""), "dia": lambda r: dia_curto(r.get("dia")),
                "status": situacao, "tipo": lambda r: str(r.get("tipo") or "")}
    out = {}
    for campo, de in valor_de.items():
        outros = {k: v for k, v in filtros.items() if k != campo}
        conta = Counter(de(r) for r in tarefas(sem, **outros))
        conta.pop("", None)
        out[campo] = conta
    return out


def tarefas(sem, equipe=None, dia=None, status=None, tipo=None, busca=None, horario=None) -> list[dict]:
    termo = _norm(busca)
    out = []
    for r in sem.get("rows") or []:
        if horario == "fora" and not fora_do_horario(r):
            continue
        if equipe and str(r.get("cluster") or "") != equipe:
            continue
        if dia and dia_curto(r.get("dia")) != dia:
            continue
        if status and situacao(r) != status:
            continue
        if tipo and str(r.get("tipo") or "") != tipo:
            continue
        if termo and termo not in _norm(" ".join(str(r.get(c) or "") for c in ("usina", "os_id", "tarefa", "cluster"))):
            continue
        out.append(r)
    ordem = {d: i for i, d in enumerate(DIAS)}
    return sorted(out, key=lambda r: (str(r.get("cluster") or ""), ordem.get(dia_curto(r.get("dia")), 9),
                                      str(r.get("h_ini") or "")))

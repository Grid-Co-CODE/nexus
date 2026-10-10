"""Regras puras da tela da semana: a programação (formato do banco_dados.json do painel do PCM) por equipe e dia.

Uma linha do arquivo é UMA tarefa programada. A equipe é o `cluster` (o nome da aba da planilha do PCM, "SP Leste 02"),
o dia vem por extenso ("Terça-feira") e o status é o do Fracttal ("Finalizados", "Não Iniciada", "Em progresso",
"pausado").
"""
import unicodedata
from collections import Counter, defaultdict

DIAS = ("seg", "ter", "qua", "qui", "sex")
NOMES_DIA = {"seg": "Segunda", "ter": "Terça", "qua": "Quarta", "qui": "Quinta", "sex": "Sexta"}
# O que cabe num dia de equipe: 80% das 8,8 h líquidas (07:00–17:00 menos o almoço), a mesma conta do gerador.
CAPACIDADE_H = 7.0
# A MPA roda na janela da noite (15:30 → 01:30; o gerador trunca o dia às 15:30) e não disputa as 7 h do dia.
# Medido na semana 40: com ela na conta, 93 de 193 dias de equipe "passavam" de 7 h; sem ela, 46.
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


def _pct(parte, todo) -> int:
    return int(round(100.0 * parte / todo)) if todo else 0


def resumo(sem) -> dict:
    rows = sem.get("rows") or []
    sit = Counter(situacao(r) for r in rows)
    return {
        "linhas": len(rows),
        "os": len({r.get("os_id") for r in rows if r.get("os_id")}),
        "usinas": len({r.get("usina") for r in rows if r.get("usina")}),
        "equipes": len({r.get("cluster") for r in rows if r.get("cluster")}),
        "feitas": sit["feita"], "em_andamento": sit["andamento"], "nao_iniciadas": sit["nao_iniciada"],
        "aderencia": _pct(sit["feita"], len(rows)),
        "horas": round(sum(float(r.get("duracao") or 0) for r in rows), 2),
        "pendentes": len(sem.get("pendentes") or []),
        "reprogramadas": sum(1 for r in rows if _norm(r.get("reprog")) == "sim"),
        "novas": sum(1 for r in rows if _norm(r.get("nova_os")).startswith("sim")),
        "fora_horario": sum(1 for r in rows if fora_do_horario(r)),
        "por_tipo": Counter(str(r.get("tipo") or "Sem tipo") for r in rows).most_common(),
    }


def por_equipe(sem) -> list[dict]:
    grupos = defaultdict(list)
    for r in sem.get("rows") or []:
        grupos[str(r.get("cluster") or "Sem equipe")].append(r)
    pend = Counter(str(p.get("cluster") or "Sem equipe") for p in sem.get("pendentes") or [])
    out = []
    for eq in sorted(set(grupos) | set(pend)):
        rows = grupos.get(eq, [])
        horas = {d: 0.0 for d in DIAS}
        noite = {d: 0.0 for d in DIAS}
        for r in rows:
            d = dia_curto(r.get("dia"))
            # a zeladoria é terceirizada e roda em paralelo: não gasta hora da equipe
            if not d or _norm(r.get("paralelo")) == "sim":
                continue
            (noite if _norm(r.get("tipo")) == TIPO_NOITE else horas)[d] += float(r.get("duracao") or 0)
        feitas = sum(1 for r in rows if situacao(r) == "feita")
        out.append({
            "equipe": eq, "linhas": len(rows), "feitas": feitas, "aderencia": _pct(feitas, len(rows)),
            "usinas": len({r.get("usina") for r in rows if r.get("usina")}),
            "horas_dia": {d: round(h, 2) for d, h in horas.items()},
            "horas_noite": {d: round(h, 2) for d, h in noite.items()},
            "estourou": [d for d in DIAS if horas[d] > CAPACIDADE_H + 1e-9],
            "pendentes": pend.get(eq, 0),
        })
    return out


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

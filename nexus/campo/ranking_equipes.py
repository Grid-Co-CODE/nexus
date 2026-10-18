"""Ranking das equipes na Visão do responsável (18/10/2026).

Levi, 18/10/2026: o ranking responde "qual equipe cobrar", e a posição vai "de acordo com as regras do ranking do app de
campo". O App tem duas réguas de ranking (function_app.py, v283): o placar do ciclo, por TÉCNICO e mês (o que o campo
reconhece, com prêmio, mas sem nenhuma conta por equipe), e o Ranking por região do painel do App (`_ranking_regioes`,
nota composta = 60% qualidade + 40% cobertura, por cluster), a única conta por equipe que existe no App. É esta a régua,
sobre o dado do Nexus:
- qualidade = a média simples de todas as notas do período, cada uma com o mesmo peso: a "Nota do painel" de cada TAREFA
  fechada pelo App (`fato_fechamento.nota_pts`; o qlog do App tem uma linha por tarefa) e a "Nota da ronda" de cada ronda
  do App (`fato_ronda.nota_pts`); nota vazia não entra;
- cobertura = usinas da equipe com ronda no período ÷ usinas da equipe;
- nota = 0,6 × qualidade + 0,4 × cobertura, arredondada como o App arredonda (`int(round(x))`).
Diferenças contra o painel do App, que a tela diz: a equipe da usina vem do cadastro do Nexus (no App, a OS vai ao cluster
da tarefa na programação do PCM ou ao da usina no catálogo dele, e a ronda ao da usina no catálogo); a base da cobertura
são as usinas mobilizadas do cadastro; o dia é o de Brasília do registro (`data_id`); a ronda avulsa do Nexus conta na
cobertura e não tem nota. A cor é a escala do painel do App (`qcor`), não uma régua oficial da nota: não há corte decidido
para a composta.

Puro: recebe as linhas e devolve números; quem lê o banco é `responsaveis.ranking_fonte`.
Desenho: docs/superpowers/specs/2026-10-18-visao-responsavel-ranking-equipes-design.md.
"""
from datetime import date, timedelta

from ..dados import fatos as D
from . import visao

# "Últimos 30 dias", o padrão da barra do painel do App (PER='30'): o App não tem janela oficial, e o Levi escolheu 30
JANELA_DIAS = 30
# a escala de cor do painel do App (qcor no gestao.html): 85 ou mais verde, 70 ou mais âmbar, abaixo vermelho
COR_VERDE, COR_AMBAR = 85, 70


def periodos(hoje: date) -> dict:
    """O período atual (de hoje − 29 a hoje, o "Últimos 30 dias" do painel do App) e o anterior, do mesmo tamanho."""
    ini = hoje - timedelta(days=JANELA_DIAS - 1)
    return {"atual": (ini, hoje), "anterior": (ini - timedelta(days=JANELA_DIAS), ini - timedelta(days=1))}


def _vazio() -> dict:
    return {"q_soma": 0, "q_n": 0, "n_os": 0, "n_ronda": 0, "rondada": False}


def _dia_do_id(v) -> date | None:
    i = D._id(v)
    try:
        return date(i // 10000, i // 100 % 100, i % 100) if i else None
    except ValueError:
        return None


def _dia_iso(v) -> date | None:
    try:
        return date.fromisoformat(str(v or "")[:10])
    except ValueError:
        return None


def _periodo_do_dia(per: dict, dia: date | None) -> str | None:
    for nome, (ini, fim) in per.items():
        if dia and ini <= dia <= fim:
            return nome
    return None


def agregar(fechamentos: list[dict], rondas: list[dict], mobilizadas, hoje: date) -> dict:
    """{usina_id: {"atual": AGG, "anterior": AGG}} de toda usina mobilizada, AGG = {"q_soma", "q_n", "n_os", "n_ronda",
    "rondada"}. A tarefa fechada pelo App conta com a nota dela (sem nota, não conta em nada); a ronda do App conta como
    ronda e, com nota, na qualidade; a avulsa do Nexus só deixa a usina com ronda (cobertura). Linha de usina que não é
    mobilizada, ou de fora dos dois períodos, fica de fora. A API pode devolver tudo como texto: passa por `D._id`/`D._int`."""
    per = periodos(hoje)
    out = {uid: {"atual": _vazio(), "anterior": _vazio()} for uid in mobilizadas}
    for x in fechamentos:
        uid, nota = D._id(x.get("usina_id")), D._int(x.get("nota_pts"))
        p = _periodo_do_dia(per, _dia_do_id(x.get("data_id")))
        if uid not in out or nota is None or not p:
            continue
        a = out[uid][p]
        a["q_soma"] += nota
        a["q_n"] += 1
        a["n_os"] += 1
    for r in rondas:
        uid = D._id(r.get("usina_id"))
        p = _periodo_do_dia(per, _dia_iso(r.get("data")))
        if uid not in out or not p:
            continue
        a = out[uid][p]
        a["rondada"] = True
        if r.get("avulsa"):
            continue
        a["n_ronda"] += 1
        nota = D._int(r.get("nota"))
        if nota is not None:
            a["q_soma"] += nota
            a["q_n"] += 1
    return out


def nota_da_equipe(aggs: list[dict]) -> dict:
    """A conta do `_ranking_regioes` do App sobre os agregados das usinas de uma equipe (de um período): qualidade = soma
    das notas ÷ quantas; cobertura = usinas com ronda ÷ usinas; nota = 0,6 × qualidade + 0,4 × cobertura. Sem nenhuma
    nota, a equipe fica sem nota (o App a deixa fora do ranking)."""
    q_soma = sum(a["q_soma"] for a in aggs)
    q_n = sum(a["q_n"] for a in aggs)
    rondadas = sum(1 for a in aggs if a["rondada"])
    usinas = len(aggs)
    qualidade = int(round(q_soma / float(q_n))) if q_n else None
    cobertura = int(round(100.0 * rondadas / usinas)) if usinas else None
    nota = (int(round(visao.PESO_QUALIDADE * qualidade + visao.PESO_COBERTURA * (cobertura or 0)))
            if qualidade is not None else None)
    return {"qualidade": qualidade, "cobertura": cobertura, "nota": nota, "n_notas": q_n,
            "n_os": sum(a["n_os"] for a in aggs), "n_ronda": sum(a["n_ronda"] for a in aggs), "rondadas": rondadas,
            "usinas": usinas}


def cor(nota) -> str:
    """A cor da nota na escala do painel do App (o mesmo `cn-t-*` das outras telas)."""
    if nota is None:
        return "neutro"
    return "ok" if nota >= COR_VERDE else ("alerta" if nota >= COR_AMBAR else "critico")


def posicoes(notas: dict) -> dict:
    """{equipe: posição}, 1 = a melhor, só das equipes com nota. O App ordena só pela nota e, no empate (medido em
    18/10/2026: 41 das 52 equipes com nota dividiam 10 notas), fica a ordem em que leu as tabelas; aqui o empate vai para
    a maior qualidade, a maior cobertura, o maior volume (o ciclo do App desempata pelas tarefas contadas) e o nome."""
    com = [e for e, n in notas.items() if n.get("nota") is not None]
    com.sort(key=lambda e: (-notas[e]["nota"], -(notas[e].get("qualidade") or 0), -(notas[e].get("cobertura") or 0),
                            -(notas[e].get("n_notas") or 0), e))
    return {e: i for i, e in enumerate(com, 1)}


def seta(atual, antes) -> dict:
    """A posição contra a do período anterior: "sobe" ou "desce" quantas, "igual", ou "sem" quando falta uma das duas."""
    if atual is None or antes is None:
        return {"tipo": "sem", "n": 0}
    d = antes - atual
    return {"tipo": "sobe" if d > 0 else ("desce" if d < 0 else "igual"), "n": abs(d)}


# ── Os cartões: a posição é só a nota do App; o resto da Visão diz em quê cobrar ─────────────────────────────────────
MAX_ETIQUETAS = 4       # o cartão v2 aprovado: até 4 etiquetas e "e mais N"


def _pl(n, um, varios) -> str:
    return f"{n} {um if n == 1 else varios}"


def etiquetas(s: dict, usinas: list[dict], limite: int) -> list[dict]:
    """Em quê cobrar a equipe: os números da Visão (`responsaveis.soma` do grupo e as linhas das usinas), cada um na régua
    da tela dona (a mesma do bloco em que ele aparece na Visão), o crítico primeiro e, dentro do nível, a ordem fixa:
    parada aberta, atrasadas, PT, ronda, limpeza, extintores, meta, disponibilidade, zeladoria, semana, chamados, tarefas
    paradas. Eles NÃO mudam a posição (decisão do Levi, 18/10/2026: "só aparecem ao lado"). Na meta conta usinas abaixo de
    97%, e não a meta somada do grupo: medido em 18/10/2026, uma usina com produção de 10,7 GWh contra meta de 149 MWh no
    Gerencial punha a equipe em 2.207%."""
    from .manutencao import META_SEMANA
    from .responsaveis import DISP_CRITICO, DISP_OK, META_ATENCAO, META_NA_META, _virgula
    us, out = usinas or [], []

    def add(cls, txt):
        out.append({"cls": cls, "txt": txt})
    if s.get("paradas_abertas"):
        add("critico", _pl(s["paradas_abertas"], "OS de parada aberta", "OS de parada abertas"))
    if s.get("atrasadas"):
        n = s["atrasadas"]
        maior = max(((u.get("manutencao") or {}).get("maior_atraso") or 0 for u in us), default=0)
        add("critico" if maior > limite else "alerta",
            f"{n} tarefas atrasadas, a mais antiga há {maior} d" if n > 1 else f"1 tarefa atrasada, há {maior} d")
    if s.get("paradas"):
        add("critico", _pl(s["paradas"], "PT parada", "PT paradas"))
    pedem = [t for t in ((u.get("ronda") or {}).get("tipo") for u in us) if t in ("nunca", "sem_ronda", "longa_pendente")]
    if pedem:
        add("critico" if any(t != "longa_pendente" for t in pedem) else "alerta",
            f"{len(pedem)} usinas pedem ronda" if len(pedem) > 1 else "1 usina pede ronda")
    limpeza = [(((u.get("acomp") or {}).get("valores") or {}).get("limpeza") or {}).get("cls") for u in us]
    if "critico" in limpeza:
        add("critico", f"limpeza crítica em {_pl(limpeza.count('critico'), 'usina', 'usinas')}")
    elif "alerta" in limpeza:
        add("alerta", f"limpeza em atenção em {_pl(limpeza.count('alerta'), 'usina', 'usinas')}")
    if s.get("ext_vencidos"):
        add("critico", _pl(s["ext_vencidos"], "extintor vencido", "extintores vencidos"))
    abaixo = [a for a in ((u.get("meta") or {}).get("atingimento") for u in us) if a is not None and a < META_NA_META]
    if abaixo:
        add("critico" if any(a < META_ATENCAO for a in abaixo) else "alerta",
            _pl(len(abaixo), "usina abaixo da meta", "usinas abaixo da meta"))
    disp = s.get("disp")
    if disp is not None and disp < DISP_OK:
        add("critico" if disp < DISP_CRITICO else "alerta", f"disp. {_virgula(disp)}%")
    zel = sum(1 for u in us if (u.get("manutencao") or {}).get("zeladoria_vencida"))
    if zel:
        add("alerta", f"zeladoria vencida em {_pl(zel, 'usina', 'usinas')}")
    pct = s.get("semana_pct")
    if pct is not None and pct < META_SEMANA:
        add("alerta", f"semana passada {_virgula(pct, 0)}%")
    if s.get("chamados"):
        add("alerta", _pl(s["chamados"], "chamado com o fabricante", "chamados com o fabricante"))
    if s.get("tarefas_paradas"):
        add("alerta", _pl(s["tarefas_paradas"], "tarefa fora da programação", "tarefas fora da programação"))
    out.sort(key=lambda e: e["cls"] != "critico")       # estável: o crítico primeiro, a ordem fixa dentro do nível
    return out


def cartoes(usinas: list[dict], por_usina: dict, tecnicos: dict, limite: int) -> dict:
    """Um cartão por equipe das usinas que passaram pelos filtros da tela (as usinas já com o bloco Manutenção no limite
    de quem olha): a nota e a posição pela régua do App (refeitas só sobre essas usinas), a posição de antes (a MESMA
    lista de equipes no período anterior) e a seta, o semáforo dos três blocos (`responsaveis.soma`) e as etiquetas.
    A ordem é a de quem cobra: as sem nota primeiro (sem OS nem ronda do App no período: o App as deixa fora, mas é o
    pior caso para quem cobra), depois as ranqueadas da última posição para a 1ª, e a "Sem equipe" no fim, sem posição
    (o conserto é no cadastro)."""
    from .responsaveis import soma
    grupos: dict[str, list] = {}
    for u in usinas:
        grupos.setdefault(u.get("equipe") or visao.SEM_EQUIPE, []).append(u)

    def nota(us, per):
        return nota_da_equipe([(por_usina.get(u.get("usina_id")) or {}).get(per) or _vazio() for u in us])
    atual = {e: nota(us, "atual") for e, us in grupos.items()}
    antes = {e: nota(us, "anterior") for e, us in grupos.items()}
    reais = [e for e in grupos if e != visao.SEM_EQUIPE]
    pos = posicoes({e: atual[e] for e in reais})
    pos_antes = posicoes({e: antes[e] for e in reais})
    out = []
    for e, us in grupos.items():
        n, s, sem = atual[e], soma(e, us), e == visao.SEM_EQUIPE
        etq = etiquetas(s, us, limite)
        p, pa = pos.get(e), pos_antes.get(e)
        out.append({"equipe": e, "sem_equipe": sem, "usinas": len(us), "tecnicos": tecnicos.get(e, 0),
                    "regiao_campo": next((u["regiao_campo"] for u in us if u.get("regiao_campo")), ""),
                    "base_pequena": len(us) < visao.BASE_PEQUENA, "posicao": p, "nota": n["nota"],
                    "qualidade": n["qualidade"], "cobertura": n["cobertura"], "n_os": n["n_os"], "n_ronda": n["n_ronda"],
                    "cor": "neutro" if sem else cor(n["nota"]), "antes": {"nota": antes[e]["nota"], "posicao": pa},
                    "seta": seta(p, pa), "tri": {q: s[q] for q in ("perf", "acomp", "manut")},
                    "etiquetas": etq[:MAX_ETIQUETAS], "mais": max(0, len(etq) - MAX_ETIQUETAS)})
    out.sort(key=lambda c: (2 if c["sem_equipe"] else (0 if c["posicao"] is None else 1), -(c["posicao"] or 0),
                            c["equipe"]))
    equipes = [c for c in out if not c["sem_equipe"]]
    rk = sorted((c for c in equipes if c["posicao"] is not None), key=lambda c: c["posicao"])
    melhor, menor = (rk[0], rk[-1]) if rk else (None, None)
    return {"cartoes": out, "total": len(rk),
            "kpis": {"equipes": len(equipes), "tecnicos": sum(c["tecnicos"] for c in equipes),
                     "melhor": {"nota": melhor["nota"], "equipe": melhor["equipe"]} if melhor else None,
                     "menor": {"nota": menor["nota"], "equipe": menor["equipe"]} if menor else None,
                     "amplitude": melhor["nota"] - menor["nota"] if rk else None}}

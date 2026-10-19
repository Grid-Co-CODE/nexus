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
import collections
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


def agregar(fechamentos: list[dict], rondas: list[dict], mobilizadas, hoje: date, desde: dict | None = None) -> dict:
    """{usina_id: {"atual": AGG, "anterior": AGG | None}} de toda usina mobilizada, AGG = {"q_soma", "q_n", "n_os",
    "n_ronda", "rondada"}. A tarefa fechada pelo App conta com a nota dela (sem nota, não conta em nada); a ronda do App
    conta como ronda e, com nota, na qualidade; a avulsa do Nexus só deixa a usina com ronda (cobertura). Linha de usina
    que não é mobilizada, ou de fora dos dois períodos, fica de fora. A API pode devolver tudo como texto: passa por
    `D._id`/`D._int`. `desde` = {usina_id: "AAAA-MM-DD" da mobilização}: a usina mobilizada depois do fim do período
    anterior não era da operação nele, e fica fora dele (`anterior` = None). Revisão de 18/10/2026: ela contava como "sem
    ronda" de antes, a cobertura de antes caía e a seta "subia" sem a equipe ter melhorado."""
    per = periodos(hoje)
    fim_anterior = per["anterior"][1].isoformat()
    out = {uid: {"atual": _vazio(),
                 "anterior": None if str((desde or {}).get(uid) or "")[:10] > fim_anterior else _vazio()}
           for uid in mobilizadas}
    for x in fechamentos:
        uid, nota = D._id(x.get("usina_id")), D._int(x.get("nota_pts"))
        p = _periodo_do_dia(per, _dia_do_id(x.get("data_id")))
        if uid not in out or nota is None or not p or out[uid][p] is None:
            continue
        a = out[uid][p]
        a["q_soma"] += nota
        a["q_n"] += 1
        a["n_os"] += 1
    for r in rondas:
        uid = D._id(r.get("usina_id"))
        p = _periodo_do_dia(per, _dia_iso(r.get("data")))
        if uid not in out or not p or out[uid][p] is None:
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


# a ordem fixa das áreas dentro do mesmo nível (as áreas das `REGUAS` da Visão)
ORDEM_DAS_AREAS = ("parada", "atrasadas", "pt", "ronda", "limpeza", "extintores", "ativos", "meta", "disp", "zeladoria",
                   "semana", "chamados", "paradas")


def _texto(area: str, s: dict, us: list[dict], crit: int, todas: int) -> str:
    """O texto da etiqueta de uma área: o número do grupo quando a Visão tem (`responsaveis.soma`), senão quantas usinas.
    `crit` = usinas com o alerta da área em crítico; `todas` = usinas com o alerta da área."""
    from .manutencao import META_SEMANA
    from .responsaveis import META_NA_META, _virgula

    def usinas(n):
        return _pl(n, "usina", "usinas")
    if area == "parada":
        return _pl(s.get("paradas_abertas") or todas, "OS de parada aberta", "OS de parada abertas")
    if area == "atrasadas":
        n = s.get("atrasadas") or 0
        maior = max(((u.get("manutencao") or {}).get("maior_atraso") or 0 for u in us), default=0)
        return f"{n} tarefas atrasadas, a mais antiga há {maior} d" if n > 1 else f"1 tarefa atrasada, há {maior} d"
    if area == "pt":
        if crit and s.get("paradas"):
            return _pl(s["paradas"], "PT parada", "PT paradas")
        return _pl(s.get("pts") or todas, "PT esperando o De acordo", "PT esperando o De acordo")
    if area == "ronda":
        return f"{todas} usinas pedem ronda" if todas > 1 else "1 usina pede ronda"
    if area == "limpeza":
        return f"limpeza crítica em {usinas(crit)}" if crit else f"limpeza em atenção em {usinas(todas)}"
    if area == "extintores":
        if crit and s.get("ext_vencidos"):
            return _pl(s["ext_vencidos"], "extintor vencido", "extintores vencidos")
        return f"extintores a vencer ou sem conferência em {usinas(todas)}"
    if area == "ativos":
        nivel = "critico" if crit else "atencao"
        n = sum(1 for u in us for x in ((u.get("ativos") or {}).get("lista") or ()) if x.get("nivel") == nivel) or todas
        return _pl(n, "ativo em crítico", "ativos em crítico") if crit else _pl(n, "ativo pedindo atenção",
                                                                             "ativos pedindo atenção")
    if area == "meta":
        abaixo = sum(1 for u in us if ((u.get("meta") or {}).get("atingimento") is not None
                                       and u["meta"]["atingimento"] < META_NA_META))
        if abaixo:
            return _pl(abaixo, "usina abaixo da meta", "usinas abaixo da meta")
        return _pl(todas, "usina com PR abaixo do previsto", "usinas com PR abaixo do previsto")
    if area == "disp":
        return f"disp. abaixo de 80% em {usinas(crit)}" if crit else f"disp. abaixo de 99% em {usinas(todas)}"
    if area == "zeladoria":
        return f"zeladoria vencida em {usinas(todas)}"
    if area == "semana":
        pct = s.get("semana_pct")
        if pct is not None and pct < META_SEMANA:
            return f"semana passada {_virgula(pct, 0)}%"
        return f"semana passada abaixo de 85% em {usinas(todas)}"
    if area == "chamados":
        return _pl(s.get("chamados") or todas, "chamado com o fabricante", "chamados com o fabricante")
    if area == "paradas":
        return _pl(s.get("tarefas_paradas") or todas, "tarefa fora da programação", "tarefas fora da programação")
    from .responsaveis import ROTULO_AREA
    return f"{ROTULO_AREA.get(area, area)} em {usinas(todas)}"


def etiquetas(s: dict, usinas: list[dict]) -> list[dict]:
    """Em quê cobrar a equipe. Cada etiqueta é uma ÁREA com alerta em alguma usina da equipe, no nível do pior alerta dela,
    tirada dos MESMOS alertas que fazem o semáforo do cartão (`perf`, `acomp` e `manut` de cada usina, as réguas das
    telas donas e o limite das atrasadas de quem olha, `com_manutencao`): nada a cobrar só quando o semáforo está todo em
    dia. Revisão de 18/10/2026: as etiquetas saíam de 12 números à parte, e uma equipe só com um ativo em crítico
    mostrava "Performance 1 · 0 · 0" e, embaixo, "nada a cobrar nos três blocos". O crítico primeiro e, no mesmo nível, a
    ordem de `ORDEM_DAS_AREAS`. Elas NÃO mudam a posição (decisão do Levi, 18/10/2026: "só aparecem ao lado"). Na meta
    conta usinas abaixo de 97%, e não a meta somada do grupo: medido em 18/10/2026, uma usina com produção de 10,7 GWh
    contra meta de 149 MWh no Gerencial punha a equipe em 2.207%; na disponibilidade, as usinas, e não a média do grupo
    pela potência, que escondia uma usina abaixo de 80%."""
    us = usinas or []
    areas: dict[str, dict] = {}
    for u in us:
        for b in ("perf", "acomp", "manut"):
            for a in (u.get(b) or {}).get("alertas") or ():
                x = areas.setdefault(a["area"], {"crit": set(), "todas": set()})
                x["todas"].add(u.get("usina_id"))
                if a["nivel"] in ("agora", "critico"):
                    x["crit"].add(u.get("usina_id"))
    ordem = [a for a in ORDEM_DAS_AREAS if a in areas] + sorted(a for a in areas if a not in ORDEM_DAS_AREAS)
    out = [{"cls": "critico" if areas[a]["crit"] else "alerta",
            "txt": _texto(a, s, us, len(areas[a]["crit"]), len(areas[a]["todas"]))} for a in ordem]
    out.sort(key=lambda e: e["cls"] != "critico")       # estável: o crítico primeiro, a ordem fixa dentro do nível
    return out


def _grupos(usinas: list[dict]) -> dict:
    g: dict[str, list] = {}
    for u in usinas:
        g.setdefault(u.get("equipe") or visao.SEM_EQUIPE, []).append(u)
    return g


def _nota_do_grupo(us: list[dict], por_usina: dict, per: str) -> dict:
    """A nota do período `per` sobre as usinas `us`. A usina fora do período (mobilizada depois dele: `anterior` =
    None) não entra na conta dele."""
    aggs = []
    for u in us:
        p = por_usina.get(u.get("usina_id"))
        a = _vazio() if p is None else p.get(per)
        if a is not None:
            aggs.append(a)
    return nota_da_equipe(aggs)


def classificar(usinas: list[dict], por_usina: dict) -> dict:
    """A régua sobre TODAS as equipes das usinas dadas (as mobilizadas da Visão, antes de qualquer filtro): a nota de cada
    equipe nos dois períodos, as posições e quantas têm posição. A "Sem equipe" fica fora (não é equipe: o conserto é no
    cadastro). Levi, 18/10/2026: "O ranking das equipes tem que permancer mesmo filtrados, o que está acontecendo agora é
    que se eu filtro [um responsável] vai contar de 1 a 11": a nota é a da equipe inteira, a posição é a do ranking de
    todas, e o filtro da tela só escolhe quais cartões aparecem."""
    grupos = {e: us for e, us in _grupos(usinas).items() if e != visao.SEM_EQUIPE}
    atual = {e: _nota_do_grupo(us, por_usina, "atual") for e, us in grupos.items()}
    antes = {e: _nota_do_grupo(us, por_usina, "anterior") for e, us in grupos.items()}
    pos = posicoes(atual)
    return {"grupos": grupos, "atual": atual, "antes": antes, "pos": pos, "pos_antes": posicoes(antes),
            "total": len(pos)}


def cartoes(usinas: list[dict], por_usina: dict, tecnicos: dict, filtradas: list[dict] | None = None) -> dict:
    """Um cartão por equipe das usinas que passaram pelos filtros da tela (`filtradas`; sem ela, todas). `usinas` são
    TODAS as mobilizadas, já com o bloco Manutenção no limite de quem olha (`com_manutencao`: o limite está nos alertas,
    e daí no semáforo e nas etiquetas). O cartão é o da equipe inteira, com ou sem filtro (`classificar`): a nota e a
    posição pela régua do App, a posição de antes e a seta, o semáforo dos três blocos (`responsaveis.soma`) e as
    etiquetas. Só o "Sem equipe" fica com as usinas do filtro: não é equipe, é a lista do conserto no cadastro. Os
    números de cima (`kpis`) são os dos cartões que aparecem; o "de N" (`total`) é o ranking inteiro.
    A ordem é a de quem cobra: as sem nota primeiro (sem OS nem ronda do App no período: o App as deixa fora, mas é o
    pior caso para quem cobra), depois as ranqueadas da última posição para a 1ª, e a "Sem equipe" no fim, sem posição
    (o conserto é no cadastro)."""
    from .responsaveis import soma
    cl = classificar(usinas, por_usina)
    vistas = usinas if filtradas is None else filtradas
    out = []
    for e, filtro in _grupos(vistas).items():
        sem = e == visao.SEM_EQUIPE
        us = filtro if sem else (cl["grupos"].get(e) or filtro)
        n = cl["atual"].get(e) or _nota_do_grupo(us, por_usina, "atual")
        na = cl["antes"].get(e) or _nota_do_grupo(us, por_usina, "anterior")
        s = soma(e, us)
        etq = etiquetas(s, us)
        p, pa = cl["pos"].get(e), cl["pos_antes"].get(e)
        out.append({"equipe": e, "sem_equipe": sem, "usinas": len(us), "tecnicos": tecnicos.get(e, 0),
                    "regiao_campo": next((u["regiao_campo"] for u in us if u.get("regiao_campo")), ""),
                    "base_pequena": len(us) < visao.BASE_PEQUENA, "posicao": p, "nota": n["nota"],
                    "qualidade": n["qualidade"], "cobertura": n["cobertura"], "n_os": n["n_os"], "n_ronda": n["n_ronda"],
                    "n_notas": n["n_notas"], "cor": "neutro" if sem else cor(n["nota"]),
                    "antes": {"nota": na["nota"], "posicao": pa},
                    "seta": seta(p, pa), "tri": {q: s[q] for q in ("perf", "acomp", "manut")},
                    "etiquetas": etq[:MAX_ETIQUETAS], "mais": max(0, len(etq) - MAX_ETIQUETAS)})
    out.sort(key=lambda c: (2 if c["sem_equipe"] else (0 if c["posicao"] is None else 1), -(c["posicao"] or 0),
                            c["equipe"]))
    equipes = [c for c in out if not c["sem_equipe"]]
    rk = sorted((c for c in equipes if c["posicao"] is not None), key=lambda c: c["posicao"])
    melhor, menor = (rk[0], rk[-1]) if rk else (None, None)
    return {"cartoes": out, "total": cl["total"],
            "kpis": {"equipes": len(equipes), "tecnicos": sum(c["tecnicos"] for c in equipes),
                     "melhor": {"nota": melhor["nota"], "equipe": melhor["equipe"]} if melhor else None,
                     "menor": {"nota": menor["nota"], "equipe": menor["equipe"]} if menor else None,
                     "amplitude": melhor["nota"] - menor["nota"] if rk else None}}


# ── O motivo da nota (Levi, 18/10/2026: "Clicando na equipe deve dar um breve resumo do motivo da pontuação da equipe
# estar abaixo para que o supervisor possa cobrar a equipe") ────────────────────────────────────────────────────────
PARTE_RONDAS = "Rondas"
PARTE_SEM_COMPOSICAO = "Sem a composição da nota"
MAX_PIORES, MAX_TECNICOS, MAX_SEM_RONDA = 5, 6, 8


def _repartir(total: int, partes: list[float]) -> list[int]:
    """Inteiros proporcionais a `partes` que somam `total`, pelo maior resto: a janela mostra pontos inteiros, e a soma
    das partes tem de ser a perda que a frase de cima diz (no empate do resto, a parte que vem antes)."""
    soma_p = sum(partes)
    if total <= 0 or soma_p <= 0:
        return [0] * len(partes)
    exatos = [total * x / soma_p for x in partes]
    base = [int(x) for x in exatos]
    for i in sorted(range(len(partes)), key=lambda i: (-(exatos[i] - base[i]), i))[:total - sum(base)]:
        base[i] += 1
    return base


def _perdeu(it: dict) -> float:
    try:
        return float(it.get("peso") or 0) - float(it.get("pts") or 0)
    except (TypeError, ValueError):
        return 0.0


def _falhas(texto) -> list[str]:
    return [f.strip() for f in str(texto or "").split(";") if f.strip()]


def motivos(n: dict, det: dict, usinas: list[dict], por_usina: dict) -> dict:
    """O porquê da nota da equipe, para quem cobra. A nota perde 100 − nota pontos: a qualidade tira 0,6 × (100 −
    qualidade) e a cobertura o resto (as duas já arredondadas, como o App faz a nota). A parte da qualidade vai às rondas,
    pelos pontos que elas perderam, e a cada critério da nota do App, pelos pontos que as tarefas perderam nele (a
    "Composição da nota": seis critérios com peso e pontos, que somam a nota; medido em 18/10/2026, fecha em 3.790 de
    3.790 tarefas), sobre as MESMAS notas da média; o inteiro na tela é repartido pelo maior resto (`_repartir`). Depois,
    as notas mais baixas (com o que faltou, para cobrar), a média por técnico e as usinas sem ronda.
    `n` = `nota_da_equipe` do período atual; `det` = `responsaveis.ranking_detalhe` (as tarefas e as rondas com nota);
    `usinas` = as da equipe; `por_usina` = `responsaveis.ranking_fonte` (quem teve ronda, a avulsa inclusive)."""
    nome = {u.get("usina_id"): u.get("usina") or "" for u in usinas}
    sem_ronda = sorted(nm for uid, nm in nome.items()
                       if not ((por_usina.get(uid) or {}).get("atual") or {}).get("rondada"))
    cob = {"valor": n.get("cobertura"), "com": len(nome) - len(sem_ronda), "usinas": len(nome),
           "sem_ronda": sem_ronda[:MAX_SEM_RONDA], "mais_sem_ronda": max(0, len(sem_ronda) - MAX_SEM_RONDA)}
    tarefas, rondas = det.get("tarefas") or [], det.get("rondas") or []
    if n.get("nota") is None:
        return {"perde": None, "qualidade": {"valor": None, "n": 0, "perde": None, "partes": []},
                "cobertura": {**cob, "perde": None}, "piores": [], "mais_piores": 0, "tecnicos": [], "mais_tecnicos": 0}
    perde = 100 - n["nota"]
    perde_q = min(perde, max(0, int(round(visao.PESO_QUALIDADE * (100 - n["qualidade"])))))
    # as partes da qualidade, em pontos perdidos pelas notas (a proporção é o que importa: `_repartir`)
    partes = []
    baixas = [r for r in rondas if r["nota"] < 100]
    if baixas:
        cont = collections.Counter(f for r in baixas for f in _falhas(r.get("falhas")))
        txt = f"{len(baixas)} de {_pl(len(rondas), 'ronda', 'rondas')} abaixo de 100"
        if cont:
            txt += "; falhas: " + ", ".join(f"{f} ({k})" for f, k in cont.most_common(3))
        partes.append({"rot": PARTE_RONDAS, "exato": float(sum(100 - r["nota"] for r in baixas)), "ordem": -1,
                       "det": txt})
    crit, sem_comp = {}, []
    for t in tarefas:
        itens = t.get("itens") or []
        if not itens:
            if t["nota"] < 100:
                sem_comp.append(t)
            continue
        for i, it in enumerate(itens):
            c = crit.setdefault(str(it.get("rot") or "?"), {"soma": 0.0, "n": 0, "ordem": i})
            if _perdeu(it) > 0.05:
                c["soma"] += _perdeu(it)
                c["n"] += 1
    for rot, c in crit.items():
        if c["soma"] > 0:
            partes.append({"rot": rot, "exato": c["soma"], "ordem": c["ordem"],
                           "det": f"em {c['n']} de {_pl(len(tarefas), 'tarefa', 'tarefas')}"})
    if sem_comp:
        partes.append({"rot": PARTE_SEM_COMPOSICAO, "exato": float(sum(100 - t["nota"] for t in sem_comp)), "ordem": 99,
                       "det": f"{_pl(len(sem_comp), 'tarefa', 'tarefas')} sem o detalhe da nota no livro do App"})
    partes.sort(key=lambda x: (-x["exato"], x["ordem"]))
    for x, v in zip(partes, _repartir(perde_q, [x["exato"] for x in partes])):
        x["perde"] = v
    partes = [{k: x[k] for k in ("rot", "perde", "det")} for x in partes if x["perde"] > 0]
    # as notas mais baixas: a menor primeiro e, na mesma nota, a mais nova
    regs = [{"nota": t["nota"], "dia": t.get("dia") or "", "usina": nome.get(t.get("usina_id"), ""),
             "tecnico": t.get("tecnico") or "",
             "o_que": " · ".join(x for x in (f"OS {t['os']}" if t.get("os") else "", t.get("tarefa") or "") if x)
             or "Tarefa",
             "faltou": "; ".join(f"{it.get('rot')}: {it.get('det')}" if it.get("det") else str(it.get("rot"))
                                 for it in t.get("itens") or () if _perdeu(it) > 0.05)}
            for t in tarefas if t["nota"] < 100]
    regs += [{"nota": r["nota"], "dia": r.get("dia") or "", "usina": nome.get(r.get("usina_id"), ""),
              "tecnico": r.get("tecnico") or "", "o_que": f"Ronda · OS {r['os']}" if r.get("os") else "Ronda sem OS",
              "faltou": "; ".join(_falhas(r.get("falhas")))} for r in baixas]
    # as tarefas iguais da mesma OS (a mesma nota, o mesmo dia, o mesmo que faltou) viram uma linha só, com quantas:
    # medido em 18/10/2026, uma OS de verificação de tracker com 4 tarefas iguais ocupava 4 das 5 linhas
    juntas: dict[tuple, dict] = {}
    for x in regs:
        k = (x["nota"], x["dia"], x["o_que"], x["usina"], x["tecnico"], x["faltou"])
        if k in juntas:
            juntas[k]["vezes"] += 1
        else:
            juntas[k] = {**x, "vezes": 1, "cor": cor(x["nota"])}
    regs = sorted(juntas.values(), key=lambda x: x["dia"], reverse=True)
    regs.sort(key=lambda x: x["nota"])
    # a média por técnico, sobre as mesmas notas
    por_tec: dict[str, list] = {}
    for x in [*tarefas, *rondas]:
        a = por_tec.setdefault(x.get("tecnico") or "", [0, 0])
        a[0] += x["nota"]
        a[1] += 1
    tecs = [{"nome": k or "sem nome no cadastro do App", "n": q, "media": int(round(s / q))}
            for k, (s, q) in por_tec.items()]
    tecs.sort(key=lambda t: (t["media"], -t["n"], t["nome"]))
    for t in tecs:
        t["cor"] = cor(t["media"])
    return {"perde": perde, "qualidade": {"valor": n["qualidade"], "n": n.get("n_notas", 0), "perde": perde_q,
                                          "partes": partes},
            "cobertura": {**cob, "perde": perde - perde_q}, "piores": regs[:MAX_PIORES],
            "mais_piores": sum(x["vezes"] for x in regs[MAX_PIORES:]), "tecnicos": tecs[:MAX_TECNICOS],
            "mais_tecnicos": max(0, len(tecs) - MAX_TECNICOS)}

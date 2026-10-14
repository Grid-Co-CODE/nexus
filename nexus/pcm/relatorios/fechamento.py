"""Fechamento da semana: aderência, tendência, reincidentes, religamentos, o que não coube e a engenharia, 2 páginas (cópia
do `fechamento_semana` do `relatorios_semana.py` do PCM). Automático na sexta a partir das 17:00, sobre a semana ativa,
uma vez por semana e sem recuperar no sábado (`agenda.py`), como no PCM.
"""
import collections
import re
from datetime import datetime, timedelta

from .regras import (CAT_SEMANA, DIAS_PT, META, ORIGEM, TIPOS_NAO_PROG, cel, ds, f0, f1, fin, h, logo_html, n, p0,
                     pagina, pct, semana_key, semana_seg, sufixo_recorte, tabela, tarefa_curta, usina_curta)


def gerar(dados, week, gerado: datetime, recorte=None):
    """{"html", "titulo", "resumo"} da semana `week` ("AAAA-Wnn"), ou None quando o banco não tem a semana."""
    bd, g, ger, eng = dados["bd"], dados["gestao"], dados["gerencial"], dados["engenharia"]
    W = {w["week"]: w for w in bd.get("semanas", [])}
    w = W.get(week)
    if not w:
        return None
    MON = semana_seg(week)
    SUN = MON + timedelta(6)
    plan = [x for x in w["rows"] if not x.get("foraDoPlano")]
    fora = [x for x in w["rows"] if x.get("foraDoPlano")]
    prog, feitas = len(plan), sum(map(fin, plan))
    ader = pct(feitas, prog)
    rol = sum(1 for x in plan if x.get("reprog") == "Sim")
    dias = [(d[:3], len([x for x in plan if x["dia"] == d]), sum(1 for x in plan if x["dia"] == d and fin(x)))
            for d in DIAS_PT[:5]]

    def bloco(k, top=8, minimo=1):
        c = collections.defaultdict(lambda: [0, 0, 0])
        for x in plan:
            kk = x.get(k) or "—"
            c[kk][0] += 1
            c[kk][1] += fin(x)
            c[kk][2] += (x.get("reprog") == "Sim")
        return [(kk, *v) for kk, v in sorted(c.items(), key=lambda kv: -kv[1][0]) if v[0] >= minimo][:top]
    cli = bloco("cliente")
    resp = bloco("responsavel", 8)
    piores = sorted(bloco("cluster", 60, 10), key=lambda r: pct(r[2], r[1]))[:6]

    T = g.get("tarefas", [])
    tend = []
    for i in range(3, -1, -1):
        wk = semana_key(MON - timedelta(weeks=i))
        if wk not in W:
            continue
        mon = semana_seg(wk)
        sun = mon + timedelta(6)
        r = [x for x in W[wk]["rows"] if not x.get("foraDoPlano")]
        npw = sum(1 for t in T if t.get("tipo") in TIPOS_NAO_PROG and ds(t.get("criacao")) and mon <= ds(t["criacao"]) <= sun)
        rw = [e for e in ger.get("eventos", []) if ds(e.get("ini")) and mon <= ds(e["ini"]) <= sun]
        tend.append((wk[-2:], len(r), sum(map(fin, r)), sum(1 for x in r if x.get("reprog") == "Sim"), npw, len(rw),
                     sum((e.get("hDia") or 0) * (e.get("peso") or 1) for e in rw)))
    grp = collections.defaultdict(list)
    for x in plan:
        if (x.get("vezes") or 1) >= 4 and not fin(x):
            grp[x["os_id"]].append(x)
    reinc = sorted(grp.items(), key=lambda kv: -max(t.get("vezes") or 1 for t in kv[1]))
    npg = [t for t in T if t.get("tipo") in TIPOS_NAO_PROG and ds(t.get("criacao")) and MON <= ds(t["criacao"]) <= SUN]
    U = ger.get("usinas", [])
    usina_de = lambda e: U[e["u"]] if 0 <= e.get("u", -1) < len(U) else {}   # noqa: E731
    ev = [e for e in ger.get("eventos", []) if ds(e.get("ini")) and MON <= ds(e["ini"]) <= SUN]
    hrel = sum((e.get("hDia") or 0) * (e.get("peso") or 1) for e in ev)
    reg = collections.Counter(usina_de(e).get("regiao", "—") for e in ev)
    cat = collections.Counter(e.get("cat") for e in ev)
    hp = collections.Counter()
    for e in ev:
        hp[usina_de(e).get("usina", e.get("ativo", "—"))] += (e.get("hDia") or 0)
    causas = collections.Counter()
    for p in w.get("pendentes", []):
        m = re.sub(r"^\[\+\d+d em andamento\]\s*", "", p.get("motivo", ""))
        causas["MPA noturna sem dia definido" if "defina o dia" in m else "usina sem dia na semana" if "não recebeu dia" in m
               else "deslocada por OS grande" if "Deslocada por OS" in m else "rolagem sem capacidade" if "Rolagem" in m
               else "sem capacidade nos dias da usina"] += 1
    crit = [(a.get("nome"), a.get("usina"), a.get("nFalha")) for a in eng.get("ativos", []) if a.get("nivel") == "critico"]
    aten = sum(1 for a in eng.get("ativos", []) if a.get("nivel") == "atencao")
    kpi = eng.get("kpi") or {}

    t_ader = [pct(f, p) for _, p, f, *_ in tend]
    seguidas = 0
    for i in range(len(t_ader) - 1, 0, -1):
        if t_ader[i] < t_ader[i - 1]:
            seguidas += 1
        else:
            break
    tendencia = ("caindo" if seguidas >= 2 else
                 ("subindo" if len(t_ader) >= 3 and t_ader[-1] > t_ader[-2] > t_ader[-3] else "oscilando"))
    pior_dia = min(dias, key=lambda d: pct(d[2], d[1])) if prog else ("—", 0, 0)
    resp_ok = [r for r in resp if r[0] not in ("—", "TBD")]
    ins = []
    if prog:
        seq = " → ".join(f"{p0(x)}%" for x in t_ader)
        ins.append(f"<b>Aderência de {p0(ader)}% na semana</b> — {n(feitas)} das {n(prog)} tarefas programadas finalizadas, "
                   f"{'acima' if ader >= META else 'abaixo'} da meta de {p0(META)}%. "
                   + (f"É a {['', 'segunda', 'terceira', 'quarta'][min(seguidas, 3)]} semana seguida em queda: {seq}."
                      if tendencia == "caindo" else f"Últimas semanas: {seq}."))
        ins.append(f"<b>{n(rol)} tarefas rolaram</b> ({p0(pct(rol, prog))}% da programação). {n(len(reinc))} OS já rolaram "
                   f"4 vezes ou mais e seguem abertas — são o tema crítico nº 1: cada uma dessas está há mais de um mês "
                   f"sendo empurrada.")
        if cli and resp_ok:
            ins.append(f"<b>{h(pior_dia[0])} foi o pior dia</b> ({p0(pct(pior_dia[2], pior_dia[1]))}% de "
                       f"{n(pior_dia[1])}). Por cliente, {h(min(cli, key=lambda r: pct(r[2], r[1]))[0])} teve a menor "
                       f"aderência; por supervisor, {h(min(resp_ok, key=lambda r: pct(r[2], r[1]))[0])}.")
    else:
        ins.append("<b>Semana sem programação carregada</b> no banco de dados — só o que entrou e os religamentos.")
    ant = tend[-2][4] if len(tend) >= 2 else None
    tipos_np = " · ".join(f"{n(c)} {h(t)}" for t, c in collections.Counter(t["tipo"] for t in npg).most_common()) or "nenhuma"
    ins.append(f"<b>{n(len(npg))} OS não programadas entraram</b> ({tipos_np})"
               + (f", {'mais' if len(npg) > ant else 'menos'} que na semana anterior ({n(ant)})." if ant is not None else ".")
               + " Isso consumiu HH que estava reservado ao plano.")
    if ev:
        top = hp.most_common(1)[0]
        ins.append(f"<b>{n(len(ev))} religamentos</b> somaram {f0(hrel)} h ponderadas de indisponibilidade. {h(top[0])} "
                   f"sozinha respondeu por {f0(top[1])} h — vale abrir análise de causa raiz.")
    if fora:
        ins.append(f"<b>Fora do plano, a equipe executou {n(len(fora))} tarefas</b> que não estavam programadas. É trabalho "
                   f"real, mas invisível na aderência — e sinal de que o plano não reflete o que o campo faz.")
    if causas:
        ins.append(f"<b>{n(sum(causas.values()))} tarefas não couberam na semana</b>: "
                   f"{n(causas['MPA noturna sem dia definido'])} MPA noturnas esperam um dia nas observações e "
                   f"{n(causas['usina sem dia na semana'])} são de usinas que não receberam dia. Essas duas causas "
                   f"dependem do PCM, não do campo.")

    mx = max([p for _, p, _ in dias] or [1]) or 1
    barras = "".join(f'<div class="bar"><div class="col"><i style="height:{100*p/mx:.0f}%"></i><b style="height:{100*f/mx:.0f}%"></b></div><span>{d}<small>{n(f)}/{n(p)}</small></span></div>' for d, p, f in dias)
    label = w.get("label") or f"Semana {week[-2:]}"
    corpo = f"""
<div class="pg">
<div class="top">{logo_html()}<div class="t"><h1>Fechamento da semana</h1><div class="s">Grid Co. · aderência, temas críticos e o que fica para a próxima semana{sufixo_recorte(recorte)}</div></div>
  <div class="d"><b>{h(label)}</b>fechado {DIAS_PT[gerado.weekday()][:3].lower()} {gerado:%d/%m} às {gerado:%H:%M} · uso interno</div></div>
<div class="kpis" style="grid-template-columns:repeat(6,1fr)">
  <div class="kpi {'g' if ader >= META else 'r'}"><div class="v">{f'{p0(ader)}%' if prog else '—'}</div><div class="n">Aderência da semana</div><div class="m">{n(feitas)} de {n(prog)} · meta {p0(META)}%</div></div>
  <div class="kpi r"><div class="v">{n(rol)}</div><div class="n">Tarefas que rolaram</div><div class="m">{p0(pct(rol, prog))}% da programação</div></div>
  <div class="kpi"><div class="v">{n(len(fora))}</div><div class="n">Fora do plano</div><div class="m">executadas sem estar programadas</div></div>
  <div class="kpi r"><div class="v">{n(len(npg))}</div><div class="n">Não programadas</div><div class="m">corretivas e religamentos criados</div></div>
  <div class="kpi"><div class="v">{n(len(ev))}</div><div class="n">Religamentos</div><div class="m">{f0(hrel)} h ponderadas de parada</div></div>
  <div class="kpi r"><div class="v">{n(g.get('totalAtrasadas', 0))}</div><div class="n">Backlog atrasado</div><div class="m">de {n(g.get('totalAbertas', 0))} abertas no fechamento</div></div>
</div>
<div class="g2">
  <div><div class="sec">Aderência por dia — programadas × finalizadas</div><div class="bars">{barras}</div></div>
  <div><div class="sec">Quatro semanas — tendência</div>
    <table><thead><tr><th>Semana</th><th class="r">Prog.</th><th class="r">Aderência</th><th class="r">Rolaram</th><th class="r">Não prog.</th><th class="r">Relig.</th><th class="r">h parada</th></tr></thead><tbody>
    {''.join(f'<tr><td>S{s}</td><td class="r">{n(p)}</td><td class="r">{cel(pct(f,p))}</td><td class="r">{n(r)}</td><td class="r">{n(np_)}</td><td class="r">{n(rl)}</td><td class="r">{f0(hh_)}</td></tr>' for s,p,f,r,np_,rl,hh_ in tend)}
    </tbody></table></div>
</div>
<div class="g2">
  <div><div class="sec">Por cliente</div>{tabela([(h(k), n(p), n(f), n(r), cel(pct(f,p))) for k,p,f,r in cli], [("Cliente",""),("Prog.","r"),("Final.","r"),("Rolaram","r"),("Aderência","r")], ["","r","r","r","r"], "sem programação")}</div>
  <div><div class="sec">Por supervisor (Responsável O&amp;M)</div>{tabela([(h(k if k != "—" else "sem responsável no BD"), n(p), n(f), n(r), cel(pct(f,p))) for k,p,f,r in resp], [("Supervisor",""),("Prog.","r"),("Final.","r"),("Rolaram","r"),("Aderência","r")], ["","r","r","r","r"], "sem programação")}</div>
</div>
<div class="sec">Temas críticos da semana</div>
<ul class="ins">{''.join(f'<li>{x}</li>' for x in ins)}</ul>
<div class="pe"><span>Página 1 de 2 · {ORIGEM}</span><span>Aderência = finalizadas ÷ programadas (linhas do plano; fora do plano contadas à parte). Meta {p0(META)}%.</span></div>
</div>
<div class="pg">
<div class="top">{logo_html()}<div class="t"><h1>Detalhe da semana</h1><div class="s">reincidentes, religamentos, o que não coube e a engenharia</div></div><div class="d"><b>{h(label)}</b>página 2 de 2</div></div>
<div class="sec">Reincidentes — OS com 4 rolagens ou mais que seguem abertas ({n(len(reinc))})</div>
{tabela([(f'#{h(k)}', h(usina_curta(L[0].get("usina"))[:24]), h(tarefa_curta(L[0].get("tarefa"))[:40]), h(L[0].get("tipo")), h(L[0].get("responsavel") or "—"), f'<span class="al">{max(t.get("vezes") or 1 for t in L)}ª</span>') for k,L in reinc[:10]],
        [("OS",""),("Usina",""),("Tarefa",""),("Tipo",""),("Responsável",""),("Rolagem","r")], ["mono","","","","","r"], "nenhuma OS com 4 rolagens ou mais em aberto")}
<div class="nota">Cada rolagem é uma semana perdida. Acima de 4, a causa raramente é capacidade: é peça, acesso, escopo ou a OS não cabe no dia. Vale decidir uma a uma na reunião de programação.</div>
<div class="g3">
  <div><div class="sec">Clusters com pior aderência (≥10 tarefas)</div>{tabela([(h(k), n(p), n(f), cel(pct(f,p))) for k,p,f,r in piores], [("Cluster",""),("Prog.","r"),("Final.","r"),("Ader.","r")], ["","r","r","r"])}</div>
  <div><div class="sec">Religamentos por região</div>{tabela([(h(k), n(v), f'{p0(pct(v, len(ev)))}%') for k,v in reg.most_common()], [("Região",""),("Eventos","r"),("Parte","r")], ["","r","r"], "nenhum religamento")}
    {f'<div class="nota">{" · ".join(f"<b>{n(v)}</b> {CAT_SEMANA.get(k,k)}" for k,v in cat.most_common())}</div>' if cat else ''}</div>
  <div><div class="sec">Usinas com mais horas de parada</div>{tabela([(h(str(k)[:24]), f'{f0(v)} h') for k,v in hp.most_common(6)], [("Usina",""),("Diurnas","r")], ["","r"], "—")}</div>
</div>
<div class="g2">
  <div><div class="sec">Não programadas da semana — por cliente</div>{tabela([(h(k or "—"), n(v), f'{p0(pct(v, len(npg)))}%') for k,v in collections.Counter(t.get("cliente") for t in npg).most_common(6)], [("Cliente",""),("OS","r"),("Parte","r")], ["","r","r"], "nenhuma")}</div>
  <div><div class="sec">O que não coube na semana — por causa</div>{tabela([(h(k), n(v)) for k,v in causas.most_common()], [("Causa",""),("Tarefas","r")], ["","r"], "tudo coube")}
    <div class="nota">"MPA noturna sem dia" e "usina sem dia" dependem do PCM: defina o dia nas Observações da Semana e a próxima programação absorve.</div></div>
</div>
<div class="sec">Engenharia — Confiabilidade no fechamento</div>
<ul class="ins">
  <li><b>{n(kpi.get('ativosSinal', 0))} ativos com sinal de recorrência</b>, {n(len(crit))} crítico(s) e {n(aten)} em atenção. Crítico: {'; '.join(f'{h(a)} ({h(u)}, {f} falhas em 30 dias)' for a,u,f in crit) or 'nenhum'}.</li>
  <li><b>MTTR de {f1(kpi.get('mttr', 0))} h</b> e MTBF de {n(kpi.get('mtbf', 0))} h na frota monitorada. {n(kpi.get('abaixo85', 0))} ativos abaixo de 85% de disponibilidade.</li>
</ul>
<div class="pe"><span>Página 2 de 2 · o cliente não recebe este relatório — ele vê o resultado, não o processo</span><span>Fontes: Programação Semanal, Gestão PCM, Gerencial e Confiabilidade (Fracttal via robô)</span></div>
</div>"""
    return {
        "html": pagina(f"Fechamento da semana · {label}", "", corpo),
        "titulo": f"Fechamento da semana · {label}",
        "resumo": {"prog": prog, "fin": feitas, "aderencia": round(ader, 1), "rolaram": rol, "reincidentes": len(reinc),
                   "naoProg": len(npg), "relig": len(ev), "foraPlano": len(fora)},
        "avisos": [],
    }

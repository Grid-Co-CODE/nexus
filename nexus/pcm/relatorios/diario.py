"""Relatório diário de manutenção: o que aconteceu num dia, 2 páginas (cópia do `relatorio_diario.py` do PCM: `calcular`,
`analise` e `montar_html`). Automático às 06:00, sobre o dia anterior (`agenda.py`).

Fontes, as mesmas do PCM: a programação da semana (banco_dados.json: programadas × finalizadas do dia), a Gestão PCM
(gestao_pcm.json: não programadas criadas no dia, backlog, criadas × finalizadas), a Gerencial (gerencial.json:
religamentos do dia e dos 7 anteriores) e a Confiabilidade (engenharia.json: ativos com sinal e críticos). Nada vai ao
Fracttal.
"""
import collections
import re
from datetime import date, datetime, timedelta

from .regras import (CAT_DIARIO, DIAS_KEY, DIAS_PT, META, ORIGEM, TIPOS_NAO_PROG, cor, f0, f1, h, logo_html, n, p0,
                     pct, sufixo_recorte, tabela)


def semana_do_dia(bd, dia: date):
    alvo = f"{dia.isocalendar()[0]}-W{dia.isocalendar()[1]:02d}"
    for w in bd.get("semanas", []):
        if w.get("week") == alvo:
            return w
    return None


def calcular(dados, dia: date) -> dict:
    bd, g, ger, eng = dados["bd"], dados["gestao"], dados["gerencial"], dados["engenharia"]
    D = {"dia": dia.isoformat(), "avisos": [], "foraPlano": 0}

    # programação do dia (Programação Semanal)
    w = semana_do_dia(bd, dia)
    nome_dia = DIAS_PT[dia.weekday()]
    rows = []
    if w:
        esperado = dia.strftime("%d/%m")
        if w.get("dates", {}).get(DIAS_KEY[dia.weekday()], esperado) != esperado:
            D["avisos"].append(f"a semana {w['week']} do banco_dados não bate com a data {esperado}")
        todos = [r for r in w.get("rows", []) if str(r.get("dia", "")).lower().startswith(nome_dia[:3].lower())]
        rows = [r for r in todos if not r.get("foraDoPlano")]          # só o que estava no plano
        D["foraPlano"] = len(todos) - len(rows)                          # executadas fora do plano
    else:
        D["avisos"].append(f"banco_dados.json não tem a semana de {dia:%d/%m} — aderência fica sem dado")
    D["semanaLabel"] = (w or {}).get("label", "") or f"Semana {dia.isocalendar()[1]}"
    D["semanaNum"] = dia.isocalendar()[1]
    fin = lambda r: r.get("status") == "Finalizados"                       # noqa: E731
    andando = lambda r: r.get("status") in ("Em progresso", "pausado")    # noqa: E731
    D["prog"], D["fin"] = len(rows), sum(1 for r in rows if fin(r))
    D["andamento"] = sum(1 for r in rows if andando(r))
    D["naoIniciada"] = D["prog"] - D["fin"] - D["andamento"]
    D["reprog"] = sum(1 for r in rows if r.get("reprog") == "Sim")

    def bloco(chave):
        o = collections.defaultdict(lambda: [0, 0, 0, 0])
        for r in rows:
            k = chave(r) or "—"
            o[k][0] += 1
            o[k][1] += fin(r)
            o[k][2] += andando(r)
            o[k][3] += r.get("reprog") == "Sim"
        return sorted([(k, *v) for k, v in o.items()], key=lambda x: -x[1])
    D["cli"] = bloco(lambda r: r.get("cliente"))
    D["resp"] = bloco(lambda r: r.get("responsavel"))
    D["naoFeitas"] = [(r.get("os_id"), r.get("tarefa", ""), r.get("cliente"), r.get("cluster"), r.get("status"))
                      for r in rows if not fin(r)]

    # semana até aqui (dias úteis da semana da data)
    D["semana"] = []
    if w:
        for i, d in enumerate(DIAS_PT[:5]):
            rs = [r for r in w.get("rows", []) if r.get("dia") == d and not r.get("foraDoPlano")]
            D["semana"].append((d[:3], len(rs), sum(1 for r in rs if fin(r)), i > dia.weekday()))

    # não programadas e backlog (Gestão PCM)
    T = g.get("tarefas", [])
    ds = dia.isoformat()
    cri = [t for t in T if (t.get("criacao") or "")[:10] == ds and t.get("tipo") in TIPOS_NAO_PROG]
    D["naoProg"] = {
        "n": len(cri),
        "tipos": collections.Counter(t["tipo"] for t in cri).most_common(),
        "clientes": collections.Counter(t.get("cliente") or "—" for t in cri).most_common(5),
        "lista": [(t.get("os"), t.get("tipo"), t.get("usina"), t.get("tarefa", ""), t.get("cluster")) for t in cri],
    }
    D["criadasTotal"] = sum(1 for t in T if (t.get("criacao") or "")[:10] == ds)
    D["finGestao"] = sum(1 for t in T if (t.get("dataFinal") or "")[:10] == ds)
    if dados.get("recorte"):
        # com recorte, o backlog é o das tarefas do recorte (como o painel); o total do arquivo é da empresa toda
        D["backlog"] = {"abertas": sum(1 for t in T if t.get("aberta")),
                        "atrasadas": sum(1 for t in T if t.get("aberta") and t.get("atrasado"))}
    else:
        D["backlog"] = {"abertas": g.get("totalAbertas", sum(1 for t in T if t.get("aberta"))),
                        "atrasadas": g.get("totalAtrasadas", sum(1 for t in T if t.get("aberta") and t.get("atrasado")))}

    # religamentos (Gerencial)
    U = ger.get("usinas", [])
    ev = ger.get("eventos", [])
    usina = lambda e: U[e["u"]] if isinstance(U, list) and 0 <= e.get("u", -1) < len(U) else {}   # noqa: E731
    hoje = [e for e in ev if (e.get("ini") or "")[:10] == ds]
    D["relig"] = [(e.get("os"), e.get("cat"), usina(e).get("usina", e.get("ativo", "")), usina(e).get("regiao", ""),
                   e.get("hDia"), e.get("url")) for e in hoje]
    D["relig7"] = [sum(1 for x in ev if (x.get("ini") or "")[:10] == (dia - timedelta(days=i)).isoformat())
                   for i in range(7, 0, -1)]

    # confiabilidade
    D["criticos"] = [(a.get("nome"), a.get("usina"), a.get("nFalha")) for a in eng.get("ativos", [])
                     if a.get("nivel") == "critico"]
    D["sinal"] = (eng.get("kpi") or {}).get("ativosSinal", 0)
    return D


# ── análise (regras fixas, auditáveis) ────────────────────────────────────
def analise(D):
    prog, fin = D["prog"], D["fin"]
    ader = pct(fin, prog)
    np_, relig = D["naoProg"], D["relig"]
    hrel = sum((r[4] or 0) for r in relig)
    med7 = sum(D["relig7"]) / 7
    ins = []
    if prog:
        ins.append(f"<b>Aderência de {p0(ader)}% no dia</b> — {n(fin)} das {n(prog)} OS programadas finalizadas, "
                   f"{'acima' if ader >= META else 'abaixo'} da meta de {p0(META)}%. "
                   f"{n(D['naoIniciada'])} não iniciadas e {n(D['andamento'])} em andamento passam para hoje."
                   + (f" Fora do plano, a equipe ainda fechou {n(D['foraPlano'])} tarefas que não estavam programadas."
                      if D["foraPlano"] else ""))
    else:
        ins.append("<b>Sem OS programadas para o dia</b> na Programação Semanal — o relatório traz só o que entrou e os "
                   "religamentos.")
    tipos = " · ".join(f"<b>{n(c)}</b> {h(t)}" for t, c in np_["tipos"]) or "nenhuma"
    if np_["n"]:
        cl = np_["clientes"][0]
        ins.append(f"<b>{n(np_['n'])} OS não programadas entraram</b> ({tipos}). {h(cl[0])} concentra {n(cl[1])} delas. "
                   f"Cada uma compete com a programação de hoje pelo mesmo HH.")
    else:
        ins.append("<b>Nenhuma OS não programada entrou</b> no dia.")
    if relig or med7:
        tom = ("Dia mais calmo que a semana." if len(relig) < med7 * 0.7 else
               "Dia acima do padrão da semana." if len(relig) > med7 * 1.3 else "Dentro do padrão da semana.")
        ins.append(f"<b>Religamentos: {n(len(relig))} no dia</b> ({f1(hrel)} h diurnas de parada), contra média de "
                   f"{f0(med7)}/dia nos 7 dias anteriores. {tom}")
    cl_ok = [(k, p, f) for k, p, f, a, rp in D["cli"] if p >= 10]
    rs_ok = [(k, p, f) for k, p, f, a, rp in D["resp"] if p >= 10 and k != "—"]
    if cl_ok:
        pc = min(cl_ok, key=lambda x: pct(x[2], x[1]))
        frase = f"<b>{h(pc[0])} teve a menor aderência entre os clientes</b> ({p0(pct(pc[2], pc[1]))}% de {n(pc[1])})"
        if rs_ok:
            pr = min(rs_ok, key=lambda x: pct(x[2], x[1]))
            frase += f"; por supervisor, {h(pr[0])} ({p0(pct(pr[2], pr[1]))}% de {n(pr[1])})"
        ins.append(frase + ".")
    saldo = D["criadasTotal"] - D["finGestao"]
    ins.append(f"<b>Backlog segue em {n(D['backlog']['atrasadas'])} tarefas atrasadas</b> de {n(D['backlog']['abertas'])} "
               f"abertas. No dia o Gestão PCM registrou {n(D['criadasTotal'])} tarefas criadas e {n(D['finGestao'])} "
               f"finalizadas — saldo {'+' if saldo > 0 else ''}{n(saldo)}.")
    crit = "; ".join(f"{h(a)} ({h(u)}, {f} falhas)" for a, u, f in D["criticos"][:2])
    ins.append(f"<b>{n(D['sinal'])} ativos com sinal de recorrência</b>, {n(len(D['criticos']))} crítico(s)"
               + (f": {crit}" if crit else "") + ". Estão em Engenharia → Confiabilidade, com ticket.")
    return ins


def montar_html(D, dia: date, gerado: datetime, recorte=None) -> str:
    prog, fin, and_, nao = D["prog"], D["fin"], D["andamento"], D["naoIniciada"]
    ader = pct(fin, prog)
    np_, relig = D["naoProg"], D["relig"]
    hrel = sum((r[4] or 0) for r in relig)
    med7 = sum(D["relig7"]) / 7
    ins = analise(D)
    logo = logo_html()
    titulo_dia = f"{DIAS_PT[dia.weekday()]}, {dia:%d/%m/%Y}"
    # o automático é sempre de ontem; sob demanda, de qualquer dia (como o painel: "no dia")
    quando = "ontem" if dia == gerado.date() - timedelta(days=1) else "no dia"

    cli = [(h(k), n(p), n(f), n(a), n(p - f - a), f'<span class="cel {cor(pct(f, p))}">{p0(pct(f, p))}%</span>')
           for k, p, f, a, rp in D["cli"][:8]]
    resp = [(h(k if k != "—" else "sem responsável no BD"), n(p), n(f), n(rp),
             f'<span class="cel {cor(pct(f, p))}">{p0(pct(f, p))}%</span>')
            for k, p, f, a, rp in D["resp"][:7]]
    tipos_np = " · ".join(f"<b>{n(c)}</b> {h(t)}" for t, c in np_["tipos"]) or "nenhuma no dia"
    usc = lambda u: re.sub(r"^[^-]+ - ", "", (u or "")).rsplit(" - ", 1)[0]   # noqa: E731
    lista_np = [(f'#{h(o)}', h((t or "").replace("Religamento Remoto", "Relig. remoto")), h(usc(u)[:22]),
                 h(re.sub(r"^\[.*?\]\s*-?\s*", "", ta or "")[:30]), h(c)) for o, t, u, ta, c in np_["lista"][:8]]
    lista_rel = [(f'#{h(o)}', h(CAT_DIARIO.get(c, c)), h((u or "")[:18]) + f' <span class="cinza">· {h(r)}</span>',
                  ("<i>aberta</i>" if hd is None else f"{f1(hd)} h")) for o, c, u, r, hd, url in relig[:8]]
    sem = D["semana"]
    mx = max([p for _, p, _, _ in sem] or [1]) or 1
    barras = "".join(
        f'<div class="bar{" fut" if fut else ""}"><div class="col"><i style="height:{100*p/mx:.0f}%"></i>'
        f'<b style="height:{100*f/mx:.0f}%"></b></div>'
        f'<span>{d}<small>{n(f)}/{n(p)}</small></span></div>' for d, p, f, fut in sem)
    nao_feitas = [(f'#{h(o)}', h(t[:44]), h(c), h(cl), h(st)) for o, t, c, cl, st in D["naoFeitas"][:8]]
    tot_sem = sum(p for _, p, _, _ in sem)
    nota_sem = ""
    if sem and tot_sem:
        d, p, f, _ = max(sem, key=lambda x: x[1])
        if pct(p, tot_sem) >= 35:
            nota_sem = (f'<div class="nota">{h(d)} concentra {n(p)} programadas — {p0(pct(p, tot_sem))}% da semana num '
                        f'só dia. Vale nivelar na próxima programação.</div>')
    mais_np = (f' <span class="cinza">(+{n(len(np_["lista"]) - 8)} no Nexus)</span>'
               if len(np_["lista"]) > 8 else "")
    mais_rel = f' <span class="cinza">(+{n(len(relig) - 8)} no Nexus)</span>' if len(relig) > 8 else ""
    mais_nf = (f' <span class="cinza">(+{n(len(D["naoFeitas"]) - 8)} no Nexus)</span>'
               if len(D["naoFeitas"]) > 8 else "")
    saldo = D["criadasTotal"] - D["finGestao"]
    avisos = ("".join(f'<div class="nota aviso">{h(a)}</div>' for a in D["avisos"]))

    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Relatório diário de manutenção · {dia:%d/%m/%Y}</title>
<style>
@page{{size:A4;margin:12mm 12mm 14mm}}
*{{box-sizing:border-box}} body{{margin:0;font-family:"Segoe UI",Arial,sans-serif;font-size:9.5pt;color:#191528;line-height:1.3;background:#fff}}
.pg{{page-break-after:always}} .pg:last-child{{page-break-after:auto}}
.top{{display:flex;align-items:flex-start;gap:14px;border-bottom:3px solid #A9DB21;padding-bottom:8px;margin-bottom:10px}}
.top .logo{{height:20px;width:auto;display:block;margin-top:4px}} .logo-txt{{font-weight:800;font-size:14pt;color:#191528}} .top .t{{flex:1}} .top h1{{margin:0;font-size:15pt;font-weight:800;white-space:nowrap}} .top .s{{font-size:9.5pt;color:#68667d}}
.top .d{{text-align:right;font-size:9pt;color:#3a3550}} .top .d b{{display:block;font-size:12pt;color:#191528}}
.kpis{{display:grid;grid-template-columns:repeat(6,1fr);gap:6px;margin:8px 0 10px}}
.kpi{{border:1px solid #e4e4ef;border-left:3px solid #cbcbdd;border-radius:6px;padding:5px 8px}} .kpi.g{{border-left-color:#A9DB21}} .kpi.r{{border-left-color:#c2410c}}
.kpi .v{{font-size:14pt;font-weight:800;line-height:1.05}} .kpi .n{{font-size:8pt;color:#68667d;text-transform:uppercase;letter-spacing:.04em;margin-top:2px}} .kpi .m{{font-size:8pt;color:#68667d}}
.sec{{margin:9px 0 5px;font-size:8.5pt;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:#68667d;display:flex;align-items:center;gap:8px}} .sec::after{{content:"";flex:1;height:1px;background:#e4e4ef}}
table{{width:100%;border-collapse:collapse;font-size:8.6pt}} td,th{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:220px}} th{{text-align:left;font-size:7.5pt;text-transform:uppercase;letter-spacing:.04em;color:#68667d;padding:4px 6px;border-bottom:1px solid #cbcbdd;background:#f6f7fa}}
td{{padding:3px 6px;border-bottom:1px solid #eceef4;vertical-align:top}} .r{{text-align:right}} th.r{{text-align:right}} .mono{{font-family:Consolas,monospace;font-size:9pt}}
.cel{{display:inline-block;min-width:38px;text-align:center;padding:1px 5px;border-radius:4px;font-weight:700}} .cel.ok{{background:#e3f6ea;color:#1f7a4d}} .cel.mid{{background:#fdf0d5;color:#a04408}} .cel.mal{{background:#fde2e2;color:#b02525}}
.g2{{display:grid;grid-template-columns:1.25fr 1fr;gap:12px}} .g2b{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.ins{{margin:0;padding-left:16px}} .ins li{{margin:3px 0;font-size:9.2pt}} .ins b{{color:#191528}}
.chips{{font-size:9.5pt;color:#3a3550;margin:2px 0 6px}} .cinza{{color:#68667d}} .vazio{{color:#68667d;font-size:9pt;padding:6px 2px}}
.bars{{display:flex;gap:10px;align-items:flex-end;height:90px;padding:4px 6px 0}} .bar{{flex:1;display:flex;flex-direction:column;align-items:center;gap:3px;height:100%}} .bar .col{{flex:1;width:100%;display:flex;gap:2px;align-items:flex-end;justify-content:center}}
.bar .col i,.bar .col b{{display:block;width:14px;border-radius:2px 2px 0 0}} .bar .col i{{background:#cbcbdd}} .bar .col b{{background:#191528}} .bar span{{font-size:8.5pt;font-weight:700}} .bar small{{display:block;font-weight:400;color:#68667d;font-size:7.5pt}} .bar.fut{{opacity:.45}}
.nota{{background:#fbfbe8;border-left:3px solid #A9DB21;padding:6px 9px;font-size:9pt;color:#3a3550;margin-top:6px}} .nota.aviso{{background:#fde2e2;border-left-color:#b02525}}
.pe{{margin-top:10px;border-top:1px solid #e4e4ef;padding-top:6px;font-size:7.8pt;color:#68667d;display:flex;justify-content:space-between;gap:10px}}
i{{font-style:normal;color:#b02525;font-weight:700;font-size:8pt}}
</style></head><body>

<div class="pg">
  <div class="top">{logo}<div class="t"><h1>Relatório diário de manutenção</h1><div class="s">Grid Co. · Operação de Ativos · o que aconteceu {quando}{sufixo_recorte(recorte)}</div></div>
    <div class="d"><b>{titulo_dia}</b>gerado {gerado:%d/%m} às {gerado:%H:%M} · uso interno (PCM e engenharia)</div></div>
  {avisos}
  <div class="kpis">
    <div class="kpi g"><div class="v">{f"{p0(ader)}%" if prog else "—"}</div><div class="n">Aderência do dia</div><div class="m">{n(fin)} de {n(prog)} programadas · +{n(D["foraPlano"])} fora do plano</div></div>
    <div class="kpi"><div class="v">{n(nao + and_)}</div><div class="n">Passam para hoje</div><div class="m">{n(nao)} não iniciadas · {n(and_)} em andamento</div></div>
    <div class="kpi r"><div class="v">{n(np_['n'])}</div><div class="n">Não programadas geradas</div><div class="m">corretivas e religamentos</div></div>
    <div class="kpi"><div class="v">{n(len(relig))}</div><div class="n">Religamentos</div><div class="m">{f1(hrel)} h diurnas · média 7 d: {f0(med7)}/dia</div></div>
    <div class="kpi r"><div class="v">{n(D['backlog']['atrasadas'])}</div><div class="n">Backlog atrasado</div><div class="m">de {n(D['backlog']['abertas'])} abertas · saldo do dia {'+' if saldo > 0 else ''}{n(saldo)}</div></div>
    <div class="kpi"><div class="v">{n(D['sinal'])}</div><div class="n">Ativos com sinal</div><div class="m">{n(len(D['criticos']))} crítico(s) no Confiabilidade</div></div>
  </div>

  <div class="sec">Programação do dia — por cliente</div>
  {tabela(cli, [("Cliente",""),("Programadas","r"),("Finalizadas","r"),("Em andamento","r"),("Não iniciadas","r"),("Aderência","r")], ["","r","r","r","r","r"], "sem OS programadas para este dia")}

  <div class="g2">
    <div>
      <div class="sec">Não programadas geradas no dia{mais_np}</div>
      <div class="chips">{tipos_np}</div>
      {tabela(lista_np, [("OS",""),("Tipo",""),("Usina",""),("Tarefa",""),("Cluster","")], ["mono","","","",""], "nenhuma OS não programada criada no dia")}
    </div>
    <div>
      <div class="sec">Religamentos do dia{mais_rel}</div>
      {tabela(lista_rel, [("OS",""),("Como resolveu",""),("Usina · região",""),("Parada","r")], ["mono","","","r"], "nenhum religamento no dia")}
      <div class="nota">Parada = horas diurnas (6h–18h) entre o incidente e o fim da tarefa. "aberta" = ainda sem data final na geração.</div>
    </div>
  </div>

  <div class="sec">Análise gerencial do dia</div>
  <ul class="ins">{''.join(f'<li>{x}</li>' for x in ins)}</ul>
  <div class="pe"><span>Página 1 de 2 · {ORIGEM}</span><span>Fontes: Programação Semanal S{D['semanaNum']}, Gestão PCM, Confiabilidade e Gerencial (Fracttal via robô)</span></div>
</div>

<div class="pg">
  <div class="top">{logo}<div class="t"><h1>Detalhe do dia</h1><div class="s">por supervisor, semana até aqui e o que ficou para hoje</div></div><div class="d"><b>{titulo_dia}</b>página 2 de 2</div></div>

  <div class="g2b">
    <div>
      <div class="sec">Por supervisor (Responsável O&amp;M)</div>
      {tabela(resp, [("Supervisor",""),("Prog.","r"),("Final.","r"),("Reprog.","r"),("Aderência","r")], ["","r","r","r","r"], "sem OS programadas para este dia")}
      {'<div class="nota">"sem responsável no BD" são OS cujo cluster não tem Responsável O&amp;M preenchido no BD_Operacoes — cadastro, não execução.</div>' if any(k == "—" for k, *_ in D["resp"]) else ""}
    </div>
    <div>
      <div class="sec">{h(D['semanaLabel'])} — programadas × finalizadas</div>
      <div class="bars">{barras or '<div class="vazio">semana sem programação carregada</div>'}</div>
      {nota_sem}
    </div>
  </div>

  <div class="sec">O que ficou para hoje — programadas do dia não finalizadas ({n(prog - fin)}){mais_nf}</div>
  {tabela(nao_feitas, [("OS",""),("Tarefa",""),("Cliente",""),("Cluster",""),("Estado","")], ["mono","","","",""], "tudo que estava programado foi finalizado")}
  <div class="nota">Lista completa e o motivo de cada rolagem no Nexus → PCM → Tarefas e OS, filtro não finalizadas. O cliente não recebe este relatório — ele vê o resultado, não o processo.</div>

  <div class="sec">Ativos críticos no Confiabilidade</div>
  <ul class="ins">{''.join(f"<li><b>{h(a)}</b> — {h(u)} · {f} falhas em 30 dias · ver ticket em Engenharia → Confiabilidade</li>" for a, u, f in D['criticos']) or '<li>nenhum crítico hoje</li>'}</ul>

  <div class="pe"><span>Página 2 de 2 · Assuma tickets e justifique rolagens no Nexus.</span><span>Aderência = finalizadas ÷ programadas do dia. Não programadas = OS criadas no dia dos tipos Corretiva, Corretiva Emergencial, Religamento e Religamento Remoto.</span></div>
</div>
</body></html>"""


def gerar(dados, dia: date, gerado: datetime, recorte=None) -> dict:
    """{"html", "titulo", "resumo"} da folha do dia."""
    D = calcular(dados, dia)
    return {"html": montar_html(D, dia, gerado, recorte), "titulo": f"Relatório diário de manutenção · {dia:%d/%m/%Y}",
            "resumo": {"prog": D["prog"], "fin": D["fin"], "naoProg": D["naoProg"]["n"], "relig": len(D["relig"])},
            "avisos": D["avisos"]}

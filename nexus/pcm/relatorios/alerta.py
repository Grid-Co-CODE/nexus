"""Alerta da programação: 17 checagens sobre a semana recém-publicada (capacidade, dado ruim, decisões pendentes e
viabilidade de campo), antes de ir para o campo (cópia do `alerta_programacao` do `relatorios_semana.py` do PCM).
Automático quando o banco_dados.json traz uma semana MAIS NOVA que a ativa (a semana seguinte foi publicada, pelo
Publicar no App do Nexus ou pelo PC do PCM) e de novo quando essa semana é republicada (o `geradaEm` dela muda):
`agenda.py`. Só regras fixas, nada de IA (aprovado no PCM em 10/09/2026, mockups S36 e S37).
"""
import collections
import re
from datetime import datetime, timedelta

from .regras import (DIAS_PT, HH_DIA, ORIGEM, f0, f1, h, hh, janela_ok, logo_html, mins, n, norm, p0, pagina, pct,
                     semana_seg, sufixo_recorte, tabela, tarefa_curta, usina_curta)


def semana_nova(bd) -> tuple[str | None, str]:
    """(week, geradaEm) da semana mais nova que a ativa no banco_dados, ou (None, '')."""
    ativa = bd.get("semana_ativa") or ""
    novas = sorted([w for w in bd.get("semanas", []) if (w.get("week") or "") > ativa], key=lambda w: w["week"])
    if not novas:
        return None, ""
    return novas[-1]["week"], novas[-1].get("geradaEm") or ""


def gerar(dados, week, gerado: datetime, recorte=None):
    """{"html", "titulo", "resumo"} das checagens da semana `week`, ou None quando o banco não tem a semana."""
    bd, op, feriados = dados["bd"], dados.get("operacoes") or {}, dados.get("feriados") or []
    W = {w["week"]: w for w in bd.get("semanas", [])}
    w = W.get(week)
    if not w:
        return None
    MON = semana_seg(week)
    rows = [x for x in w["rows"] if not x.get("foraDoPlano")]
    resumo = w.get("resumo") or {}
    P = w.get("pendentes", [])
    A = []

    # ── dado e capacidade ──
    imp = collections.defaultdict(list)
    for x in rows:
        if (x.get("duracao") or 0) > 8 or not janela_ok(x):
            imp[x["os_id"]].append(x)
    A.append(("alta", f"Duração implausível ou janela impossível — {n(len(imp))} OS, {n(sum(len(L) for L in imp.values()))} tarefas",
              "Tarefa com mais de 8 h numa janela, ou fim depois da meia-noite. Distorce o HH do cluster e empurra as outras. Corrigir a duração no plano de manutenção do Fracttal.",
              [(f'#{h(k)}', h(usina_curta(L[0].get("usina"))[:22]), h(tarefa_curta(L[0].get("tarefa"))[:30]), f'{f1(L[0].get("duracao") or 0)} h', h(L[0].get("h_ini")), h(L[0].get("h_fim")), n(len(L)))
               for k, L in sorted(imp.items(), key=lambda kv: -(kv[1][0].get("duracao") or 0))[:4]],
              [("OS", ""), ("Usina", ""), ("Tarefa", ""), ("Duração", "r"), ("Início", ""), ("Fim", ""), ("Linhas", "r")], ["mono", "", "", "r", "mono", "mono", "r"]))
    cap = sorted([(k, v["hh_util"], v["hh_disp"], v.get("pend", 0)) for k, v in resumo.items() if v.get("hh_disp") and v["hh_util"] > v["hh_disp"]], key=lambda t: -t[1] / max(t[2], 1))
    A.append(("alta", f"Clusters acima da capacidade semanal — {n(len(cap))} de {n(len(resumo))}",
              "HH programado maior que as horas da semana do cluster. Vai rolar por construção. Ou tira tarefa, ou muda a capacidade no BD de Operações.",
              [(h(k), f"{f0(u)} h", f"{d} h", f'<span class="cel {"mal" if u/d > 1.5 else "mid"}">{p0(pct(u, d))}%</span>', n(p)) for k, u, d, p in cap[:5]],
              [("Cluster", ""), ("Programado", "r"), ("Capacidade", "r"), ("Uso", "r"), ("Ficou fora", "r")], ["", "r", "r", "r", "r"]))
    dc = collections.defaultdict(float)
    for x in rows:
        if janela_ok(x):
            dc[(x["dia"], x.get("cluster") or "—")] += hh(x)
    over = sorted([(k, v) for k, v in dc.items() if v > HH_DIA], key=lambda kv: -kv[1])
    A.append(("media", f"Dias com mais de {f1(HH_DIA)} h num cluster — {n(len(over))} de {n(len(dc))} combinações dia × cluster",
              "Mais horas num dia do que uma pessoa executa. O programador aceita porque a capacidade é semanal; o campo não. Redistribuir entre os dias.",
              [(h(k[0][:3]), h(k[1]), f"{f0(v)} h", f'<span class="cel {"mal" if v > 2*HH_DIA else "mid"}">{f1(v/HH_DIA)}×</span>') for k, v in over[:5]],
              [("Dia", ""), ("Cluster", ""), ("Programado", "r"), ("Vs. 1 pessoa", "r")], ["", "", "r", "r"]))
    pd_ = collections.Counter(x["dia"] for x in rows)
    dias = [(d[:3], pd_.get(d, 0)) for d in DIAS_PT[:6] if pd_.get(d, 0)]
    if dias:
        mx, mn = max(v for _, v in dias), min(v for _, v in dias)
        A.append(("media" if pct(mx, len(rows)) >= 35 else "baixa", f"Semana desbalanceada — {h(max(dias, key=lambda t: t[1])[0])} tem {n(mx)} tarefas, {h(min(dias, key=lambda t: t[1])[0])} tem {n(mn)}",
                  f"{p0(pct(mx, len(rows)))}% da semana num só dia. Um dia de chuva ou uma corretiva grande derruba a aderência da semana inteira.",
                  [tuple(f"<b>{h(d)}</b> {n(v)}" for d, v in dias)], [(d, "") for d, _ in dias], [""] * len(dias)))
    byk = collections.defaultdict(list)
    for x in rows:
        if janela_ok(x) and x.get("h_ini") and x.get("h_fim"):
            byk[(x["dia"], x.get("cluster"))].append((mins(x["h_ini"]), mins(x["h_fim"]), x["os_id"], x.get("usina")))
    sob = []
    for k, L in byk.items():
        L.sort(key=lambda t: (t[0] or 0, t[1] or 0))
        for i in range(1, len(L)):
            if L[i][0] is not None and L[i - 1][1] is not None and L[i][0] < L[i - 1][1] and L[i][2] != L[i - 1][2]:
                sob.append((k[0][:3], k[1], L[i - 1][2], L[i][2], L[i - 1][3] != L[i][3]))
    A.append(("media", f"Janelas sobrepostas no mesmo cluster e dia — {n(len(sob))} pares",
              "Duas OS diferentes ocupando a mesma hora da mesma equipe. Se são usinas diferentes, uma delas vai rolar.",
              [(h(d), h(c), f'#{h(a)} × #{h(b)}', "usinas diferentes" if dif else "mesma usina") for d, c, a, b, dif in sob[:4]],
              [("Dia", ""), ("Cluster", ""), ("OS", ""), ("Onde", "")], ["", "", "mono", ""]))
    v5 = collections.defaultdict(list)
    for x in rows:
        if (x.get("vezes") or 1) >= 5:
            v5[x["os_id"]].append(x)
    A.append(("media", f"OS com 5 rolagens ou mais programadas de novo — {n(len(v5))} OS",
              "Já rolaram cinco vezes ou mais e voltaram para a semana sem nada mudar. A chance de rolar de novo é alta. Decidir: peça, acesso, escopo ou tirar do plano.",
              [(f'#{h(k)}', h(usina_curta(L[0].get("usina"))[:22]), h(tarefa_curta(L[0].get("tarefa"))[:34]), h(L[0].get("responsavel") or "—"), f'<b class="al">{max(t.get("vezes") or 1 for t in L)}ª</b>')
               for k, L in sorted(v5.items(), key=lambda kv: -max(t.get("vezes") or 1 for t in kv[1]))[:5]],
              [("OS", ""), ("Usina", ""), ("Tarefa", ""), ("Responsável", ""), ("Rolagem", "r")], ["mono", "", "", "", "r"]))
    tbd = [x for x in rows if (x.get("responsavel") or "TBD") == "TBD"]
    A.append(("baixa", f"Tarefas sem responsável definido — {n(len(tbd))} (TBD)",
              "O cluster não tem Responsável O&M no BD de Operações. Ninguém recebe o alerta do dia dessas tarefas.",
              [(h(c or "—"), n(v)) for c, v in collections.Counter(x.get("cluster") for x in tbd).most_common(6)], [("Cluster", ""), ("Tarefas", "r")], ["", "r"]))
    mpa = collections.defaultdict(list)
    semdia = collections.Counter()
    desloc = collections.Counter()
    for p in P:
        m = re.sub(r"^\[\+\d+d em andamento\]\s*", "", p.get("motivo", ""))
        if "defina o dia" in m:
            mpa[p["os_id"]].append(p)
        elif "não recebeu dia" in m:
            mm = re.search(r'Usina "([^"]+)"', m)
            semdia[mm.group(1) if mm else "?"] += 1
        elif "Deslocada por OS" in m:
            mm = re.search(r"OS #(\d+)", m)
            desloc[mm.group(1) if mm else "?"] += 1
    A.append(("alta" if (mpa or semdia) else "baixa", f"Ficou fora da semana por decisão pendente — {n(len(mpa))} OS de MPA noturna e {n(len(semdia))} usinas sem dia",
              "O programador não decide sozinho: MPA noturna precisa de um dia nas Observações da Semana; usina sem dia precisa entrar na distribuição do cluster. Enquanto isso, essas tarefas envelhecem no backlog.",
              [x for x in [("MPA noturna sem dia", ", ".join(f"#{k}" for k in sorted(mpa)[:10]) + (f" +{len(mpa)-10}" if len(mpa) > 10 else "")) if mpa else None,
                           ("Usinas sem dia na semana", ", ".join(usina_curta(u) for u, _ in semdia.most_common(6)) + (f" +{len(semdia)-6}" if len(semdia) > 6 else "")) if semdia else None,
                           ("Deslocadas por OS grande", " · ".join(f"#{k} empurrou {n(v)}" for k, v in desloc.most_common(4))) if desloc else None] if x],
              [("Situação", ""), ("Quem", "")], ["", "quebra"]))
    fl = []
    for _t, uf, d, nome in feriados:
        if not (MON <= d <= MON + timedelta(5)):
            continue
        prog_dia = sum(1 for x in rows if x["dia"] == DIAS_PT[d.weekday()] and (uf == "TODOS" or (x.get("usina") or "").rsplit(" - ", 1)[-1].strip()[:2] == uf))
        fl.append((h(DIAS_PT[d.weekday()][:3] + d.strftime(" %d/%m")), h(nome), h(uf), n(prog_dia), prog_dia))
    A.append(("alta" if any(l[4] for l in fl) else "baixa", f"Feriados na semana — {n(len(fl))}",
              "Tarefa programada em feriado da UF da usina só roda se a equipe trabalhar no feriado. Confirmar ou mover.",
              [l[:4] for l in fl], [("Data", ""), ("Feriado", ""), ("UF", ""), ("Tarefas no dia", "r")], ["", "", "", "r"], ))
    qa = [q for q in w.get("qualidade", []) if q.get("tipo") != "REMOVIDA"]
    A.append(("baixa", f"Avisos de cadastro — {n(len(qa))} · {n(len(w.get('qualidade', [])) - len(qa))} linhas de teste removidas",
              "Erros de nome no Fracttal que fazem a distribuição de dias contar errado.",
              [(h(q.get("item", "")[:34]), h(q.get("detalhe", "")[:60]), h(q.get("acao", "")[:40])) for q in qa], [("Item", ""), ("Problema", ""), ("Ação", "")], ["", "", ""]))

    # ── viabilidade de campo ──
    cid = {norm(u_.get("usina")): (u_.get("cidade") or "").strip() for u_ in op.get("usinas", [])}

    def cidade(us):
        c = cid.get(norm(usina_curta(us)))
        if not c:  # recuo: cidade pelo nome da usina sem o sufixo numérico, senão a UF
            base = re.sub(r"\s*\d+\s*(\(.*\))?$", "", usina_curta(us))
            c = cid.get(norm(base)) or ("UF " + (us or "").rsplit(" - ", 1)[-1].strip()[:2])
        return c
    gd = collections.defaultdict(list)
    for x in rows:
        if janela_ok(x):
            gd[(x["dia"], x.get("cluster") or "—")].append(x)
    multi = []
    for k, L in gd.items():
        cids = collections.Counter(cidade(t.get("usina")) for t in L)
        if len(cids) >= 2:
            multi.append((k, cids, sum(t.get("desloc") or 0 for t in L), len(L)))
    multi.sort(key=lambda t: (-len(t[1]), -t[2]))
    A.append(("alta" if any(len(m[1]) >= 3 for m in multi) else "media" if multi else "baixa",
              f"Equipe em mais de uma cidade no mesmo dia — {n(len(multi))} de {n(len(gd))} dias × cluster ({n(sum(1 for m in multi if len(m[1]) >= 3))} com 3 ou mais)",
              "A mesma equipe programada em usinas de cidades diferentes no mesmo dia. Duas pode ser rotina; três ou mais raramente cabe com deslocamento, almoço e apontamento.",
              [(h(k[0][:3]), h(k[1]), n(len(c)), h(" · ".join(f"{ci} ({v})" for ci, v in c.most_common(4))[:58]), f"{f1(d)} h", n(nt)) for k, c, d, nt in multi[:6]],
              [("Dia", ""), ("Cluster", ""), ("Cidades", "r"), ("Onde (tarefas)", ""), ("Desloc.", "r"), ("Tarefas", "r")], ["", "", "r", "", "r", "r"]))
    dsl = sorted([(k, sum(t.get("desloc") or 0 for t in L), len({cidade(t.get("usina")) for t in L})) for k, L in gd.items() if sum(t.get("desloc") or 0 for t in L) > 3], key=lambda t: -t[1])
    A.append(("media" if dsl else "baixa", f"Mais de 3 h de deslocamento num dia — {n(len(dsl))} dias × cluster",
              "Deslocamento somado das tarefas do dia. Acima de 3 h, sobra menos de 6 h de execução real.",
              [(h(k[0][:3]), h(k[1]), f"{f1(d)} h", n(c)) for k, d, c in dsl[:5]], [("Dia", ""), ("Cluster", ""), ("Deslocamento", "r"), ("Cidades", "r")], ["", "", "r", "r"]))
    seq = []
    for k, L in gd.items():
        Ls = sorted(L, key=lambda t: mins(t.get("h_ini")) or 0)
        for i in range(1, len(Ls)):
            a_, b_ = Ls[i - 1], Ls[i]
            if a_.get("usina") != b_.get("usina") and mins(b_.get("h_ini")) is not None and mins(a_.get("h_fim")) is not None:
                gap = mins(b_["h_ini"]) - mins(a_["h_fim"])
                need = (b_.get("desloc") or 0) * 60
                if gap < 0 or gap < need - 5:
                    seq.append((k[0][:3], k[1], a_["os_id"], b_["os_id"], gap, need, cidade(a_.get("usina")), cidade(b_.get("usina"))))
    A.append(("media" if seq else "baixa", f"Troca de usina sem tempo de deslocamento — {n(len(seq))} casos",
              "A tarefa seguinte começa em outra usina antes de a anterior terminar, ou sem o tempo de estrada que o próprio plano calcula.",
              [(h(d), h(c), f"#{h(a)} → #{h(b)}", h(f"{ca} → {cb}"[:30]), f"{g_} min", f"{f0(nd)} min") for d, c, a, b, g_, nd, ca, cb in seq[:5]],
              [("Dia", ""), ("Cluster", ""), ("OS", ""), ("Trajeto", ""), ("Folga", "r"), ("Precisa", "r")], ["", "", "mono", "", "r", "r"]))
    fh = collections.defaultdict(list)
    for x in rows:
        if janela_ok(x) and "NOTURNO" not in x["dia"].upper() and (x.get("tipo") or "") != "MPA" and mins(x.get("h_ini")) is not None \
                and (mins(x["h_ini"]) < 6 * 60 or (mins(x.get("h_fim")) or 0) > 19 * 60):
            fh[x["os_id"]].append(x)
    A.append(("media" if fh else "baixa", f"Fora do horário de campo (06:00–19:00) — {n(len(fh))} OS, {n(sum(len(L) for L in fh.values()))} tarefas",
              "Diurna programada antes das 6 h ou terminando depois das 19 h. MPA noturna e janelas marcadas NOTURNO ficam fora desta checagem.",
              [(f'#{h(k)}', h(usina_curta(L[0].get("usina"))[:22]), h(tarefa_curta(L[0].get("tarefa"))[:30]), h(L[0].get("tipo")), h(L[0].get("h_ini")), h(L[0].get("h_fim"))) for k, L in list(fh.items())[:5]],
              [("OS", ""), ("Usina", ""), ("Tarefa", ""), ("Tipo", ""), ("Início", ""), ("Fim", "")], ["mono", "", "", "", "mono", "mono"]))
    cnt = sorted([(k, len(L), len({t["os_id"] for t in L})) for k, L in gd.items() if len(L) > 12], key=lambda t: -t[1])
    A.append(("media" if cnt else "baixa", f"Mais de 12 tarefas para uma equipe num dia — {n(len(cnt))} dias × cluster",
              "Mesmo que o HH feche, cada tarefa tem abertura, execução, foto e fechamento no Fracttal. Acima de 12 por dia o apontamento não acompanha.",
              [(h(k[0][:3]), h(k[1]), n(c), n(o_)) for k, c, o_ in cnt[:5]], [("Dia", ""), ("Cluster", ""), ("Tarefas", "r"), ("OS", "r")], ["", "", "r", "r"]))
    fds = [x for x in rows if x["dia"].startswith(("Sáb", "Dom"))]
    A.append(("baixa", f"Programação em fim de semana — {n(len(fds))} tarefas", "Só vale se a equipe trabalha no sábado. Senão, rola por construção.",
              [(h(c or "—"), n(v)) for c, v in collections.Counter(x.get("cluster") for x in fds).most_common(4)], [("Cluster", ""), ("Tarefas", "r")], ["", "r"]))
    pes = {c.get("cluster"): c.get("pessoas", 0) for c in op.get("clusters", [])}
    sp = collections.Counter(x.get("cluster") for x in rows if pes.get(x.get("cluster"), 1) == 0)
    A.append(("alta" if sp else "baixa", f"Cluster com programação mas sem pessoa no BD de Operações — {n(len(sp))}",
              "A capacidade da semana vem de zero pessoas. Ou o colaborador não está na Relação Geral, ou o cluster está com o nome diferente.",
              [(h(c), n(v)) for c, v in sp.most_common(5)], [("Cluster", ""), ("Tarefas", "r")], ["", "r"]))

    ORD = {"alta": 0, "media": 1, "baixa": 2}
    SEV = {"alta": ("Alta", "mal"), "media": ("Média", "mid"), "baixa": ("Baixa", "ok")}
    A.sort(key=lambda a: ORD[a[0]])
    cont = collections.Counter(a[0] for a in A)
    hh_tot = sum(hh(x) for x in rows if janela_ok(x))
    cap_tot = sum(v.get("hh_disp", 0) for v in resumo.values())
    blocos = "".join(f'<div class="al-bloco"><div class="al-cab"><span class="sev {SEV[s][1]}">{SEV[s][0]}</span><b>{t}</b></div>'
                     f'<div class="al-txt">{r}</div>{tabela(l, cab, cols)}</div>' for s, t, r, l, cab, cols in A)
    label = w.get("label") or f"Semana {week[-2:]}"
    corpo = f"""
<div class="top" style="border-bottom-color:#a04408">{logo_html()}<div class="t"><h1>Alerta da programação</h1><div class="s">Grid Co. · checagem da programação recém-gerada, antes de ir para o campo{sufixo_recorte(recorte)}</div></div>
  <div class="d"><b>{h(label)}</b>gerado {DIAS_PT[gerado.weekday()][:3].lower()} {gerado:%d/%m} às {gerado:%H:%M} · uso interno (PCM)</div></div>
<div class="kpis" style="grid-template-columns:repeat(5,1fr)">
  <div class="kpi"><div class="v">{n(len(rows))}</div><div class="n">Tarefas programadas</div><div class="m">em {n(len({x['os_id'] for x in rows}))} OS · {n(len(resumo))} clusters</div></div>
  <div class="kpi {'r' if hh_tot > cap_tot else 'g'}"><div class="v">{p0(pct(hh_tot, cap_tot))}%</div><div class="n">HH ÷ capacidade</div><div class="m">{f0(hh_tot)} h de {n(cap_tot)} h na semana</div></div>
  <div class="kpi r"><div class="v">{n(cont['alta'])}</div><div class="n">Severidade alta</div><div class="m">resolver antes de segunda</div></div>
  <div class="kpi m"><div class="v">{n(cont['media'])}</div><div class="n">Severidade média</div><div class="m">vão virar rolagem</div></div>
  <div class="kpi m"><div class="v">{n(len(multi))}</div><div class="n">Dias em 2+ cidades</div><div class="m">mesma equipe · {n(len(P))} tarefas não couberam</div></div>
</div>
{blocos}
<div class="pe"><span>{ORIGEM} · o cliente não recebe este relatório</span><span>Fonte: Programação Semanal publicada (banco_dados.json) e BD de Operações. Corrija na planilha ou nas Observações e rode o programador de novo.</span></div>"""
    return {
        "html": pagina(f"Alerta da programação · {label}", "", corpo, "10mm 11mm 10mm"),
        "titulo": f"Alerta da programação · {label}",
        "resumo": {"tarefas": len(rows), "hhPct": round(pct(hh_tot, cap_tot)), "alta": cont["alta"], "media": cont["media"],
                   "baixa": cont["baixa"], "multiCidade": len(multi)},
        "avisos": [],
    }

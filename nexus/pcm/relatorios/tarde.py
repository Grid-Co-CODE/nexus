"""Recuperação da tarde: o programado para a MANHÃ de hoje que ainda não fechou, 1 página (cópia do `relatorio_diario.py`
do PCM: `calcular_matinal`, `analise_matinal` e `montar_html_matinal`; lá a pasta é "matinal"). Automático às 13:00 de
dia útil (`agenda.py`): o corte é a hora da emissão. Feriado não pula, como no PCM.
"""
import collections
import re
from datetime import date, datetime

from .diario import semana_do_dia
from .regras import (DIAS_PT, HORA_CORTE_MANHA, LIN_MATINAL, ORIGEM, TIPOS_NAO_PROG, f0, f1, h, logo_html, n, p0, pct,
                     sufixo_recorte, tabela)


def _hora_ini(r):
    """Hora programada de início. 99 quando o campo não é utilizável."""
    v = (r.get("h_ini") or "")[:2]
    return int(v) if v.isdigit() else 99


def _janela_ok(r):
    """Descarta janela impossível (fim depois da meia-noite) da conta de HH."""
    v = (r.get("h_fim") or "")[:2]
    return v.isdigit() and int(v) < 24


def _hh(L):
    return sum(((r.get("duracao") or 0) + (r.get("desloc") or 0)) for r in L if _janela_ok(r))


def calcular(dados, dia: date) -> dict:
    bd, g = dados["bd"], dados["gestao"]
    D = {"dia": dia.isoformat(), "avisos": [], "foraPlano": 0}
    w = semana_do_dia(bd, dia)
    nome_dia = DIAS_PT[dia.weekday()]
    rows = []
    if w:
        todos = [r for r in w.get("rows", []) if str(r.get("dia", "")).lower().startswith(nome_dia[:3].lower())]
        rows = [r for r in todos if not r.get("foraDoPlano")]          # só o que estava no plano
        D["foraPlano"] = len(todos) - len(rows)                          # executadas fora do plano
    else:
        D["avisos"].append(f"banco_dados.json não tem a semana de {dia:%d/%m} — sem programação para comparar")
    D["semanaLabel"] = (w or {}).get("label", "") or f"Semana {dia.isocalendar()[1]}"
    D["totalDia"] = len(rows)
    D["manha"] = [r for r in rows if _hora_ini(r) < HORA_CORTE_MANHA]
    D["tarde"] = [r for r in rows if HORA_CORTE_MANHA <= _hora_ini(r) < 24]
    D["fora"] = [r for r in rows if _hora_ini(r) >= 24 or not _janela_ok(r)]
    D["pend"] = [r for r in D["manha"] if r.get("status") != "Finalizados"]
    D["hhPend"], D["hhTarde"] = _hh(D["pend"]), _hh(D["tarde"])

    # uma linha de ação por OS, a que mais rolou primeiro
    grp = {}
    for r in D["pend"]:
        grp.setdefault(r.get("os_id"), []).append(r)
    for L in grp.values():
        L.sort(key=lambda r: r.get("h_ini") or "")
    D["os"] = sorted(grp.items(), key=lambda kv: (-max((r.get("vezes") or 1) for r in kv[1]),
                                                  kv[1][0].get("h_ini") or ""))
    D["reincid"] = sum(1 for _, L in D["os"] if max((r.get("vezes") or 1) for r in L) >= 3)

    D["resp"] = []
    for nome in sorted({(r.get("responsavel") or "—") for r in D["manha"] + D["tarde"]}):
        m = [r for r in D["manha"] if (r.get("responsavel") or "—") == nome]
        p = [r for r in D["pend"] if (r.get("responsavel") or "—") == nome]
        t = [r for r in D["tarde"] if (r.get("responsavel") or "—") == nome]
        D["resp"].append((nome, len(m), len(m) - len(p), len(p), _hh(p), _hh(t)))
    D["resp"].sort(key=lambda x: -x[3])

    ds = dia.isoformat()
    npg = [t for t in g.get("tarefas", []) if (t.get("criacao") or "")[:10] == ds and t.get("tipo") in TIPOS_NAO_PROG]
    D["naoProg"] = {"n": len(npg), "tipos": collections.Counter(t["tipo"] for t in npg).most_common()}
    D["cluster"] = collections.Counter((r.get("cluster") or "—") for r in D["pend"]).most_common(1)
    D["cliente"] = collections.Counter((r.get("cliente") or "—") for r in D["pend"]).most_common(1)
    return D


def analise(D):
    m, p = len(D["manha"]), len(D["pend"])
    feitas = m - p
    carga = D["hhPend"] + D["hhTarde"]
    ins = []
    if not m:
        return ["<b>Sem tarefas programadas para a manhã de hoje</b> na Programação Semanal — nada a recuperar."]
    ins.append(f"<b>A manhã fechou {p0(pct(feitas, m))}%</b> — {n(feitas)} das {n(m)} tarefas programadas até "
               f"{HORA_CORTE_MANHA:02d}:00 estão finalizadas no Fracttal. Restam <b>{n(p)} tarefas em {n(len(D['os']))} "
               f"OS</b>, somando {f0(D['hhPend'])} h de execução.")
    if p:
        aperto = ("muito acima" if carga > 2 * max(D["hhTarde"], 1) else "acima") if D["hhPend"] > 0 else "dentro"
        ins.append(f"<b>A tarde já tem {n(len(D['tarde']))} tarefas programadas</b> ({f0(D['hhTarde'])} h). Somando o "
                   f"que ficou da manhã, a carga da tarde vai a <b>{f0(carga)} h</b> — {aperto} do que o dia comporta. "
                   f"A lista acima está ordenada por quem rolou mais vezes.")
        if D["reincid"]:
            ins.append(f"<b>{n(D['reincid'])} OS já rolaram 3 vezes ou mais</b> e estão pendentes de novo. São as que "
                       f"devem furar a fila da tarde — cada nova rolagem empurra a OS para a semana seguinte.")
        cli = D["cliente"][0] if D["cliente"] else ("—", 0)
        cl = D["cluster"][0] if D["cluster"] else ("—", 0)
        tipos = " · ".join(f"<b>{n(c)}</b> {h(t)}" for t, c in D["naoProg"]["tipos"]) or "nenhuma"
        ins.append(f"<b>{h(cli[0])} concentra {n(cli[1])} das pendências</b> e o cluster {h(cl[0])} tem {n(cl[1])}. "
                   f"Hoje entraram ainda {n(D['naoProg']['n'])} OS não programadas ({tipos}), que disputam o mesmo HH "
                   f"da tarde.")
        ins.append("<b>Atenção ao apontamento:</b> uma tarefa feita e não fechada no Fracttal aparece aqui como pendente. "
                   "Se a lista tiver OS já executadas, o problema é de fechamento — e resolvê-lo é mais rápido que "
                   "reprogramar.")
    else:
        ins.append("<b>Nenhuma pendência da manhã</b> — tudo que estava programado até o meio-dia está fechado no "
                   "Fracttal.")
    return ins


def montar_html(D, dia: date, gerado: datetime, recorte=None) -> str:
    m, p = len(D["manha"]), len(D["pend"])
    carga = D["hhPend"] + D["hhTarde"]
    curto = lambda nm: ((nm.split()[0] + " " + nm.split()[-1][:1] + ".")   # noqa: E731
                        if nm and nm != "—" and len(nm.split()) > 1 else (nm or "—"))
    linhas = []
    for os_, L in D["os"][:LIN_MATINAL]:
        r = L[0]
        v = max((x.get("vezes") or 1) for x in L)
        usina = re.sub(r"^[^-]+ - ", "", r.get("usina") or "").rsplit(" - ", 1)[0]
        tarefa = re.sub(r"^\[.*?\]\s*-?\s*", "", r.get("tarefa") or "")
        est = ("pausado" if any(x["status"] == "pausado" for x in L)
               else "em progresso" if any(x["status"] == "Em progresso" for x in L) else "não iniciada")
        linhas.append((f"#{h(os_)}", h(r.get("h_ini")), h(usina[:20]),
                       h(tarefa[:32]) + (f' <span class="cinza">+{len(L)-1}</span>' if len(L) > 1 else ""),
                       h(curto(r.get("responsavel"))), f"{f1(_hh(L))} h",
                       (f'<b class="al">{v}ª</b>' if v >= 3 else f"{v}ª"),
                       f'<span class="est {est.split()[0]}">{est}</span>'))
    resp = [(h(nm if nm != "—" else "sem responsável no BD"), n(qm), n(qf), n(qp), f"{f0(hp)} h", f"{f0(ht)} h",
             f'<span class="cel {"mal" if hp + ht > 40 else "mid" if hp + ht > 25 else "ok"}">{f0(hp + ht)} h</span>')
            for nm, qm, qf, qp, hp, ht in D["resp"][:8]]
    resto = len(D["os"]) - LIN_MATINAL
    aviso = ""
    if D["fora"]:
        ids = ", ".join(sorted({f"#{r['os_id']}" for r in D['fora']})[:6])
        aviso = (f'<div class="nota aviso">{n(len(D["fora"]))} tarefa(s) com janela impossível na programação (fim depois '
                 f'da meia-noite) ficaram fora da conta de HH: {ids}. Vale corrigir a duração no plano.</div>')
    for a in D["avisos"]:
        aviso += f'<div class="nota aviso">{h(a)}</div>'

    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Recuperação da tarde · {dia:%d/%m/%Y}</title>
<style>
@page{{size:A4;margin:10mm 11mm 10mm}}
*{{box-sizing:border-box}} body{{margin:0;font-family:"Segoe UI",Arial,sans-serif;font-size:9.5pt;color:#191528;line-height:1.3;background:#fff}}
.top{{display:flex;align-items:flex-start;gap:14px;border-bottom:3px solid #c2410c;padding-bottom:8px;margin-bottom:9px}}
.top .logo{{height:20px;width:auto;display:block;margin-top:4px}} .logo-txt{{font-weight:800;font-size:14pt}} .top .t{{flex:1}}
.top h1{{margin:0;font-size:15pt;font-weight:800;white-space:nowrap}} .top .s{{font-size:9.5pt;color:#68667d}}
.top .d{{text-align:right;font-size:9pt;color:#3a3550}} .top .d b{{display:block;font-size:12pt;color:#191528}}
.kpis{{display:grid;grid-template-columns:repeat(5,1fr);gap:6px;margin:8px 0 10px}}
.kpi{{border:1px solid #e4e4ef;border-left:3px solid #cbcbdd;border-radius:6px;padding:5px 8px}} .kpi.g{{border-left-color:#A9DB21}} .kpi.r{{border-left-color:#c2410c}}
.kpi .v{{font-size:14.5pt;font-weight:800;line-height:1.05}} .kpi .n{{font-size:8pt;color:#68667d;text-transform:uppercase;letter-spacing:.04em;margin-top:2px}} .kpi .m{{font-size:8pt;color:#68667d}}
.sec{{margin:8px 0 4px;font-size:8.5pt;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:#68667d;display:flex;align-items:center;gap:8px}} .sec::after{{content:"";flex:1;height:1px;background:#e4e4ef}}
table{{width:100%;border-collapse:collapse;font-size:8.6pt}} td,th{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:230px}}
th{{text-align:left;font-size:7.5pt;text-transform:uppercase;letter-spacing:.04em;color:#68667d;padding:4px 6px;border-bottom:1px solid #cbcbdd;background:#f6f7fa}}
td{{padding:2.6px 6px;border-bottom:1px solid #eceef4;vertical-align:top}} .r{{text-align:right}} th.r{{text-align:right}} .mono{{font-family:Consolas,monospace;font-size:9pt}}
.cel{{display:inline-block;min-width:38px;text-align:center;padding:1px 5px;border-radius:4px;font-weight:700}} .cel.ok{{background:#e3f6ea;color:#1f7a4d}} .cel.mid{{background:#fdf0d5;color:#a04408}} .cel.mal{{background:#fde2e2;color:#b02525}}
.est{{font-size:7.6pt;padding:1px 5px;border-radius:3px;background:#f0f0f6;color:#3a3550}} .est.pausado{{background:#fdf0d5;color:#a04408}} .est.em{{background:#e6efff;color:#1d4ed8}}
.cinza{{color:#68667d}} .al{{color:#b02525}} .vazio{{color:#68667d;font-size:9pt;padding:6px 2px}}
.ins{{margin:0;padding-left:16px}} .ins li{{margin:2px 0;font-size:9pt}}
.nota{{background:#fbfbe8;border-left:3px solid #A9DB21;padding:5px 9px;font-size:8.5pt;color:#3a3550;margin-top:5px}} .nota.aviso{{background:#fdf0d5;border-left-color:#c2410c}}
.pe{{margin-top:9px;border-top:1px solid #e4e4ef;padding-top:6px;font-size:7.8pt;color:#68667d;display:flex;justify-content:space-between;gap:10px}}
</style></head><body>
<div class="top">{logo_html()}<div class="t"><h1>Recuperação da tarde</h1><div class="s">Grid Co. · o programado para a manhã que ainda não fechou{sufixo_recorte(recorte)}</div></div>
  <div class="d"><b>{DIAS_PT[dia.weekday()]}, {dia:%d/%m/%Y}</b>corte às {gerado:%H:%M} · uso interno (PCM, supervisores e engenharia)</div></div>

<div class="kpis">
  <div class="kpi"><div class="v">{n(m)}</div><div class="n">Programadas na manhã</div><div class="m">de {n(D['totalDia'])} no dia · +{n(D["foraPlano"])} fora do plano</div></div>
  <div class="kpi g"><div class="v">{n(m - p)}</div><div class="n">Fechadas</div><div class="m">{p0(pct(m - p, m))}% da manhã</div></div>
  <div class="kpi r"><div class="v">{n(p)}</div><div class="n">Pendentes</div><div class="m">em {n(len(D['os']))} OS · {f0(D['hhPend'])} h</div></div>
  <div class="kpi"><div class="v">{n(len(D['tarde']))}</div><div class="n">Já na tarde</div><div class="m">{f0(D['hhTarde'])} h a partir das {HORA_CORTE_MANHA:02d}:00</div></div>
  <div class="kpi r"><div class="v">{f0(carga)} h</div><div class="n">Carga da tarde</div><div class="m">pendente + programado</div></div>
</div>

<div class="sec">Prioridade de recuperação — OS da manhã ainda abertas</div>
{tabela(linhas, [("OS",""),("Hora",""),("Usina",""),("Tarefa",""),("Responsável",""),("Execução","r"),("Rolagem","r"),("Estado","")], ["mono","mono","","","","r","r",""], "nenhuma pendência da manhã — tudo fechado no Fracttal")}
{f'<div class="nota">Ordenado por número de rolagens: a coluna <b>Rolagem</b> mostra quantas vezes a OS já foi empurrada. As {n(resto)} OS restantes estão no Nexus → PCM → Tarefas e OS, filtro não finalizadas. "+N" na tarefa = a OS tem mais tarefas pendentes além da mostrada.</div>' if resto > 0 else ""}

<div class="sec">Onde há espaço na tarde — por supervisor</div>
{tabela(resp, [("Supervisor",""),("Manhã","r"),("Fechou","r"),("Pendente","r"),("HH a recuperar","r"),("HH já na tarde","r"),("Carga da tarde","r")], ["","r","r","r","r","r","r"], "sem programação no dia")}
{aviso}

<div class="sec">Leitura do meio-dia</div>
<ul class="ins">{''.join(f'<li>{x}</li>' for x in analise(D))}</ul>

<div class="pe"><span>{ORIGEM} · o cliente não recebe este relatório</span><span>Manhã = tarefas com início programado antes das {HORA_CORTE_MANHA:02d}:00. Pendente = não finalizada no Fracttal no momento do corte.</span></div>
</body></html>"""


def gerar(dados, dia: date, gerado: datetime, recorte=None) -> dict:
    D = calcular(dados, dia)
    return {"html": montar_html(D, dia, gerado, recorte), "titulo": f"Recuperação da tarde · {dia:%d/%m/%Y}",
            "resumo": {"manha": len(D["manha"]), "pendentes": len(D["pend"]), "os": len(D["os"]),
                       "hhPend": round(D["hhPend"], 1), "hhTarde": round(D["hhTarde"], 1)},
            "avisos": D["avisos"]}

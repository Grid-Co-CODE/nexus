"""A aba Indicadores do contrato (Comando › Contratos, 26/11/2026): o ano contratual mês a mês, usina por usina.

A sugestão de 26/11/2026: "Uma aba Indicadores no contrato [...] uma matriz: meses do ano contratual nas
colunas, usinas nas linhas", com MPM, MPS e MPA feitas sobre as planejadas, a supressão vegetal e a lavagem de módulos com
a data em que foram feitas (contra o mínimo do contrato), o PR e a disponibilidade expurgada contra a meta do contrato; no
alto, os números do contrato inteiro ponderados pela potência. O Levi, no mesmo dia, junto: "ANIVERSÁRIO DE CONTRATO,
RELATÓRIO DE ANIVERSÁRIO DE CONTRATO". Escolhas dele: o ano conta do início da vigência; entram TODAS as usinas do cliente
no cadastro (como a Visão gerencial); o mês sem dado no banco diz "sem dado" (nunca 0); a régua de cor é a da sugestão
(verde na meta, amarelo até 2 pontos abaixo, vermelho abaixo disso, azul com asterisco quando o mês teve expurgo).

As fontes chegam prontas (a tela as junta, `torres/comando/contratos_tela.py`), cada uma a que a tela dona já usa:
- o PR e a disponibilidade, bruta e com o expurgo do contrato: a conta da Visão gerencial (`gerencial.montar`, usina por
  `usina_id`); o banco tem esses meses só desde 10/2026 (`diagnostico_mes.PRIMEIRO_MES`);
- MPM, MPS e MPA: as tarefas do ano do PCM (`pcm.gestao.classificar`: a sigla no nome e o mês da Data Programada; feita =
  "Finalizada"), ligadas à usina pelo nome (`campo.responsaveis.Nomes`);
- a supressão vegetal (roçagem e poda química) e a lavagem (limpeza de módulos): o histórico do cronograma do Radar da
  Zeladoria (`cronograma_publico`), pelo nome da usina; o mínimo do ano, o `zeladoria_contratual` do Radar por UFV (só o
  "fixo": o "sob demanda" não tem mínimo);
- as metas: a garantia de disponibilidade e o PR que o contrato lido escreve (as regras de "Disponibilidade e desempenho"),
  ou o que o gestor gravou nos Dados do contrato, que vence.

Puro: nada de rede nem Flask. A ligação pelo nome é medida (quantas tarefas e serviços casaram com uma usina do cliente)
e a tela mostra: o que não casou não some calado.
"""
from __future__ import annotations

import re
from datetime import date

SIGLAS = ("MPM", "MPS", "MPA")
SERVICOS = {"rocada": ("Roçagem", "Poda química"), "lavagem": ("Limpeza de módulos",)}
FAIXA = 2.0                                  # pontos abaixo da meta que ainda são amarelo (a régua da sugestão)
_MESES = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
_PCT = re.compile(r"(\d{2,3}(?:[.,]\d+)?)\s*%")
LINHAS = (("MPM", "MPM", "manut"), ("MPS", "MPS", "manut"), ("MPA", "MPA", "manut"),
          ("rocada", "Supressão vegetal", "manut"), ("lavagem", "Lavagem de módulos", "manut"),
          ("pr", "PR", "kpi"), ("disp", "Disponibilidade expurgada", "kpi"))


def meses_do_ano(ano: dict) -> list[dict]:
    """Os 12 meses do ano contratual, do mês do início ao 11º seguinte: {id "AAAA-MM", rot "set/25"}."""
    a, m = int(ano["ini"][:4]), int(ano["ini"][5:7])
    out = []
    for _ in range(12):
        out.append({"id": f"{a:04d}-{m:02d}", "rot": f"{_MESES[m - 1]}/{str(a)[2:]}"})
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return out


def _pct_da_regra(ficha: dict | None, palavras: re.Pattern) -> dict | None:
    for k in (ficha or {}).get("contratos") or []:
        for r in k.get("regras") or []:
            if r.get("categoria") != "Disponibilidade e desempenho" or not palavras.search(str(r.get("nome") or "").lower()):
                continue
            m = _PCT.search(str(r.get("vigente") or r.get("contratual") or ""))
            if m:
                v = float(m.group(1).replace(",", "."))
                if 50 <= v <= 100:
                    return {"pct": v, "origem": f"do contrato: {r.get('nome')}"}
    return None


def metas(contrato: dict, ficha: dict | None) -> dict:
    """{"pr": {pct, origem} | None, "disp": {pct, origem} | None}. O número dos Dados do contrato (o gestor gravou, com
    prova) vence o lido do PDF; sem nenhum, None e a célula fica sem cor."""
    out = {}
    for chave, campo, palavras in (("pr", "meta_pr", re.compile(r"\bpr\b|performance ratio")),
                                   ("disp", "meta_disp", re.compile(r"disponibilidade"))):
        v = contrato.get(campo)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[chave] = {"pct": float(v), "origem": "dos Dados do contrato"}
        else:
            out[chave] = _pct_da_regra(ficha, palavras)
    return out


def tom_kpi(v, meta) -> str:
    """A régua da sugestão: na meta ou acima, ok; até 2 pontos abaixo, alerta; abaixo disso, critico; sem meta ou sem
    valor, sem cor."""
    if v is None or meta is None:
        return ""
    return "ok" if v >= meta else ("alerta" if v >= meta - FAIXA else "critico")


def _br(v, casas=1) -> str:
    return f"{v:.{casas}f}".replace(".", ",")


def _dm(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}"


def _media_pesada(pares) -> float | None:
    """A média de (valor, peso); sem peso (a potência que falta), peso 1."""
    pares = [(v, p if p else 1.0) for v, p in pares if v is not None]
    tot = sum(p for _, p in pares)
    return round(sum(v * p for v, p in pares) / tot, 1) if tot else None


def montar(contrato: dict, ficha: dict | None, ano: dict, usinas: list[dict], pcm: dict, zel: dict, zel_min: dict,
           hoje: date, meses_com_dado: set[str], ligacao: dict | None = None, avisos: list[str] | None = None) -> dict:
    """O que a aba lê.

    `usinas` = as do cliente na Visão gerencial: [{uid, usina, mwp, meses {"AAAA-MM": {pr, disp, ...}}, com_expurgo
    {"AAAA-MM": {disp, pr}}}]; `pcm` = {uid: {sigla: {"AAAA-MM": [feitas, total]}}}; `zel` = {uid: {"rocada" | "lavagem":
    [datas ISO]}}; `zel_min` = {uid: {"rocada" | "lavagem": n por ano}}; `meses_com_dado` = os meses que o banco de
    performance tem (fora deles, "sem dado")."""
    ms = meses_do_ano(ano)
    mes_hoje = hoje.isoformat()[:7]
    mt = metas(contrato, ficha)
    meta_pr, meta_disp = (mt["pr"] or {}).get("pct"), (mt["disp"] or {}).get("pct")
    ano_fechado = hoje.isoformat() > ano["fim"]

    def cel_prev(par, mid):
        if not par:
            return {"txt": "—", "tom": "", "dica": "sem plano no mês"}
        f, t = par
        if f >= t:
            tom = "ok"
        elif mid < mes_hoje:
            tom = "critico"
        else:
            tom = ""
        return {"txt": f"{f}/{t}", "tom": tom, "dica": f"{f} feitas de {t} planejadas"}

    out_us, tot_prev, tot_zel = [], {s: {} for s in SIGLAS}, {"rocada": {}, "lavagem": {}}
    pr_mes_contrato, disp_mes_contrato = {m["id"]: [] for m in ms}, {m["id"]: [] for m in ms}
    fora_pr = fora_disp = 0
    for u in usinas:
        uid, mwp = u.get("uid"), u.get("mwp")
        linhas, fora_u = {}, 0
        for s in SIGLAS:
            dado = (pcm.get(uid) or {}).get(s) or {}
            cels = {m["id"]: cel_prev(dado.get(m["id"]), m["id"]) for m in ms}
            f = sum(dado[m["id"]][0] for m in ms if m["id"] in dado)
            t = sum(dado[m["id"]][1] for m in ms if m["id"] in dado)
            for m in ms:
                if m["id"] in dado:
                    tp = tot_prev[s].setdefault(m["id"], [0, 0])
                    tp[0] += dado[m["id"]][0]
                    tp[1] += dado[m["id"]][1]
            ruim = any(c["tom"] == "critico" for c in cels.values())
            linhas[s] = {"cels": cels, "acum": {"txt": f"{f}/{t}" if t else "—",
                                                "tom": "ok" if t and f >= t else ("critico" if ruim else ""),
                                                "dica": f"{f} feitas de {t} planejadas no ano contratual" if t else "sem plano no ano"}}
            fora_u += sum(1 for c in cels.values() if c["tom"] == "critico")
        for chave in ("rocada", "lavagem"):
            datas = sorted(d for d in (zel.get(uid) or {}).get(chave) or [] if ano["ini"] <= d <= ano["fim"])
            cels = {}
            for m in ms:
                ds = [d for d in datas if d[:7] == m["id"]]
                if ds:
                    tot_zel[chave][m["id"]] = tot_zel[chave].get(m["id"], 0) + 1
                cels[m["id"]] = ({"txt": _dm(ds[0]) + (f" +{len(ds) - 1}" if len(ds) > 1 else ""), "tom": "ok",
                                  "dica": "feita em " + ", ".join(_dm(d) for d in ds)} if ds else {"txt": "—", "tom": "", "dica": ""})
            minimo = (zel_min.get(uid) or {}).get(chave)
            if minimo:
                tom = "ok" if len(datas) >= minimo else ("critico" if ano_fechado else "alerta")
                acum = {"txt": f"{len(datas)}/{minimo}", "tom": tom, "dica": f"{len(datas)} feitas de {minimo} no mínimo do contrato"}
            else:
                acum = {"txt": str(len(datas)) if datas else "—", "tom": "",
                        "dica": "o contrato da zeladoria não traz o mínimo desta usina" if datas else "nenhuma no ano"}
            linhas[chave] = {"cels": cels, "acum": acum}
        # o PR e a disponibilidade: o mês sem dado no banco diz "sem dado" (nunca 0)
        um, ue = u.get("meses") or {}, u.get("com_expurgo") or {}
        cels_pr, cels_disp, prs, disps = {}, {}, [], []
        for m in ms:
            mid = m["id"]
            if mid > mes_hoje:
                cels_pr[mid] = cels_disp[mid] = {"txt": "", "tom": "", "dica": "ainda não chegou"}
                continue
            if mid not in meses_com_dado:
                sem = {"txt": "s/d", "tom": "", "dica": "sem dado no banco: o PR e a disponibilidade por mês começam em 10/2026"}
                cels_pr[mid] = cels_disp[mid] = sem
                continue
            pr = (um.get(mid) or {}).get("pr")
            bruta = (um.get(mid) or {}).get("disp")
            exp = (ue.get(mid) or {}).get("disp")
            disp = exp if exp is not None else bruta
            parcial = " (mês em curso)" if mid == mes_hoje else ""
            tpr = tom_kpi(pr, meta_pr)
            cels_pr[mid] = {"txt": _br(pr) if pr is not None else "s/d", "tom": tpr,
                            "dica": (f"PR {_br(pr)}%" + (f"; meta {_br(meta_pr)}%" if meta_pr is not None else "; sem meta de PR")
                                     + parcial) if pr is not None else "a Performance não publicou o PR do mês"}
            teve = exp is not None and bruta is not None and round(exp, 2) != round(bruta, 2)
            tdi = "info" if teve else tom_kpi(disp, meta_disp)
            cels_disp[mid] = {"txt": (_br(disp) + ("*" if teve else "")) if disp is not None else "s/d", "tom": tdi,
                              "dica": (f"{_br(disp)}% com o expurgo do contrato; sem o expurgo {_br(bruta)}%" if teve else
                                       (f"{_br(disp)}%" + (f"; garantia {_br(meta_disp)}%" if meta_disp is not None else "")))
                              + parcial if disp is not None else "sem disponibilidade publicada no mês"}
            if pr is not None:
                prs.append(pr)
                pr_mes_contrato[mid].append((pr, mwp))
                if meta_pr is not None and pr < meta_pr:
                    fora_pr += 1
                    fora_u += 1
            if disp is not None:
                disps.append(disp)
                disp_mes_contrato[mid].append((disp, mwp))
                if meta_disp is not None and disp < meta_disp:
                    fora_disp += 1
                    fora_u += 1
        acum_pr = round(sum(prs) / len(prs), 1) if prs else None
        acum_disp = round(sum(disps) / len(disps), 1) if disps else None
        linhas["pr"] = {"cels": cels_pr, "acum": {"txt": _br(acum_pr) if acum_pr is not None else "s/d",
                                                  "tom": tom_kpi(acum_pr, meta_pr), "dica": f"a média dos {len(prs)} meses com PR"}}
        linhas["disp"] = {"cels": cels_disp, "acum": {"txt": _br(acum_disp) if acum_disp is not None else "s/d",
                                                      "tom": tom_kpi(acum_disp, meta_disp), "dica": f"a média dos {len(disps)} meses com dado"}}
        out_us.append({"uid": uid, "usina": u.get("usina"), "mwp": mwp, "fora": fora_u,
                       "linhas": [dict(id=i, nome=n, grupo=g, **linhas[i]) for i, n, g in LINHAS]})
    out_us.sort(key=lambda x: (-x["fora"], -(x["mwp"] or 0), str(x["usina"]).lower()))

    # o total do contrato: preventivas somadas, serviços como usinas feitas no mês, PR e disponibilidade pela potência
    total = []
    for s in SIGLAS:
        cels = {m["id"]: cel_prev(tot_prev[s].get(m["id"]), m["id"]) for m in ms}
        f, t = sum(v[0] for v in tot_prev[s].values()), sum(v[1] for v in tot_prev[s].values())
        total.append({"id": s, "nome": s, "grupo": "manut", "cels": cels,
                      "acum": {"txt": f"{f}/{t}" if t else "—", "tom": "ok" if t and f >= t else "", "dica": f"{f} feitas de {t} planejadas"}})
    for chave, nome in (("rocada", "Supressão vegetal"), ("lavagem", "Lavagem de módulos")):
        cels = {m["id"]: ({"txt": str(tot_zel[chave][m["id"]]), "tom": "ok", "dica": "usinas feitas no mês"}
                          if tot_zel[chave].get(m["id"]) else {"txt": "—", "tom": "", "dica": ""}) for m in ms}
        feitas = sum(len([d for d in (zel.get(u.get("uid")) or {}).get(chave) or [] if ano["ini"] <= d <= ano["fim"]]) for u in usinas)
        minimo = sum((zel_min.get(u.get("uid")) or {}).get(chave) or 0 for u in usinas)
        total.append({"id": chave, "nome": nome, "grupo": "manut", "sub": "usinas feitas", "cels": cels,
                      "acum": {"txt": f"{feitas}/{minimo}" if minimo else (str(feitas) if feitas else "—"),
                               "tom": ("ok" if feitas >= minimo else ("critico" if ano_fechado else "alerta")) if minimo else "",
                               "dica": f"{feitas} feitas; mínimo somado das usinas com contrato de zeladoria: {minimo}"}})
    pr_c = {mid: _media_pesada(v) for mid, v in pr_mes_contrato.items()}
    disp_c = {mid: _media_pesada(v) for mid, v in disp_mes_contrato.items()}
    for chave, nome, vals, meta in (("pr", "PR do contrato", pr_c, meta_pr), ("disp", "Disponibilidade expurgada", disp_c, meta_disp)):
        cels = {}
        for m in ms:
            v = vals.get(m["id"])
            if m["id"] > mes_hoje:
                cels[m["id"]] = {"txt": "", "tom": "", "dica": ""}
            elif m["id"] not in meses_com_dado:
                cels[m["id"]] = {"txt": "s/d", "tom": "", "dica": "sem dado no banco antes de 10/2026"}
            else:
                cels[m["id"]] = {"txt": _br(v) if v is not None else "s/d", "tom": tom_kpi(v, meta), "dica": "ponderado pela potência das usinas"}
        ac = _media_pesada([(v, 1.0) for v in vals.values() if v is not None])
        total.append({"id": chave, "nome": nome, "grupo": "kpi", "sub": "% ponderado", "cels": cels,
                      "acum": {"txt": _br(ac) if ac is not None else "s/d", "tom": tom_kpi(ac, meta), "dica": "a média dos meses com dado"}})
    tp = {s: [sum(v[0] for v in tot_prev[s].values()), sum(v[1] for v in tot_prev[s].values())] for s in SIGLAS}
    pr_ac = next((l["acum"]["txt"] for l in total if l["id"] == "pr"), "s/d")
    disp_ac = next((l["acum"]["txt"] for l in total if l["id"] == "disp"), "s/d")
    pior = out_us[0] if out_us and out_us[0]["fora"] else None
    return {"ok": True, "ano": ano, "meses": ms, "mes_hoje": mes_hoje, "ano_fechado": ano_fechado,
            "metas": mt, "usinas": out_us, "total": total,
            "resumo": {"pr": pr_ac, "disp": disp_ac, "prev": tp,
                       "rocada": next(l["acum"]["txt"] for l in total if l["id"] == "rocada"),
                       "lavagem": next(l["acum"]["txt"] for l in total if l["id"] == "lavagem"),
                       "fora_pr": fora_pr, "fora_disp": fora_disp,
                       "pior": {"usina": pior["usina"], "fora": pior["fora"]} if pior else None},
            "ligacao": ligacao or {}, "avisos": list(avisos or [])}

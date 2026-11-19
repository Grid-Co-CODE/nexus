"""Comando › Nexus Insights com o portfólio no alto e a Nexus IA (19/11/2026).

Levi, com o Insights do mockup R18 aberto: "Eu gostaria de incluir um pouco desse Nexus Insights na parte de comandos [...]
vai mostrar o portfólio, a saúde dos portfólios, como é que está sendo o cumprimento, como é que está a pontuação, e aí
ele conseguir entender o que está acontecendo e fazer perguntas para o Haiku 5.5".

O que já existia e entra aqui sem conta nova:
- a nota de cumprimento do contrato de cada usina, mês a mês, e a pontuação de saúde: a Visão gerencial
  (`gerencial.montar`, a cópia de 1 minuto de `gerencial_tela.dados_gerencial`);
- os insights do motor de regras (`motor`), os que não foram concluídos;
- a Nexus IA da carteira (`carteira_ia`), que ganha duas seções no dossiê: o cumprimento e a saúde, e os insights abertos.

Sem o valor dos contratos (ele é da Visão gerencial, que só o administrador e o setor marcado veem) e sem o nome das
pessoas. Puro: nada de rede, banco nem Flask.
"""
from __future__ import annotations

import unicodedata

from . import carteira_ia as CI
from . import gerencial as G

MAX_INSIGHTS_IA = 60            # os insights abertos que vão ao dossiê da IA (os críticos primeiro)
_PESO = {"critico": 0, "atencao": 1, "info": 2}


def _norm(t) -> str:
    s = "".join(c for c in unicodedata.normalize("NFKD", str(t or "")) if not unicodedata.combining(c))
    return " ".join(s.lower().split())


def _media(v: list) -> int | None:
    return round(sum(v) / len(v)) if v else None


def tom(nota) -> str:
    """A cor da nota, na régua da Visão gerencial: 80 ou mais em dia, 55 a 79 atenção, abaixo de 55 risco."""
    if nota is None:
        return "neutro"
    return "ok" if nota >= G.EM_DIA else ("alerta" if nota >= G.ATENCAO else "critico")


def _pior_item(score: dict) -> dict | None:
    itens = [i for i in (score or {}).get("itens") or [] if i.get("nota") is not None]
    return min(itens, key=lambda i: i["nota"]) if itens else None


def _e(nomes: list[str]) -> str:
    return nomes[0] if len(nomes) == 1 else ", ".join(nomes[:-1]) + " e " + nomes[-1]


def _plural(n: int, um: str, varios: str) -> str:
    return f"{n} {um if n == 1 else varios}"


def _itens_do_cliente(notas: list[dict]) -> list[dict]:
    """A média de cada item da nota nas usinas do cliente que o mediram, na ordem da nota (o BarList do funil):
    [{nome, media, tom, n}]. Item que nenhuma usina mediu fica fora (sem dado não se inventa)."""
    ordem, soma = [], {}
    for s in notas:
        for i in s.get("itens") or []:
            if i["nome"] not in soma:
                ordem.append(i["nome"])
                soma[i["nome"]] = []
            if i.get("nota") is not None:
                soma[i["nome"]].append(i["nota"])
    return [{"nome": n, "media": _media(soma[n]), "tom": tom(_media(soma[n])), "n": len(soma[n])} for n in ordem if soma[n]]


def _motivo_cliente(c: dict, mes_ant: str, regras: dict) -> str:
    """O porquê do cliente, em frases curtas, só com o que foi medido (Levi, 19/11/2026: "cliente tal, tá ruim por causa
    disso"): a variação do mês anterior, os itens abaixo de 80 que puxam a nota, as usinas abaixo de 55 e o insight
    crítico mais comum."""
    if c["nota"] is None:
        return (f"Sem nota neste mês: nenhuma das {c['usinas_n']} usinas tem dois itens medidos." if not c["com_nota"]
                else "Sem nota neste mês.")
    frases = []
    if c["delta"]:
        frases.append(f"{'Caiu' if c['delta'] < 0 else 'Subiu'} {_plural(abs(c['delta']), 'ponto', 'pontos')} desde {mes_ant}.")
    fracos = sorted((i for i in c["itens"] if i["media"] < G.EM_DIA), key=lambda i: i["media"])[:2]
    if fracos:
        frases.append("O que puxa a nota: " + _e([f"{i['nome']} (média {i['media']} em {_plural(i['n'], 'usina', 'usinas')})"
                                                   for i in fracos]) + ".")
    else:
        frases.append(f"Todos os itens medidos em {G.EM_DIA} ou mais.")
    if c["abaixo"]:
        frases.append(f"{c['abaixo']} de {c['com_nota']} usinas abaixo de {G.ATENCAO}.")
    if c["criticos"]:
        cont: dict[str, int] = {}
        for u in c["usinas"]:
            for i in u["insights"]:
                if i["sev"] == "critico":
                    cont[i["regra"]] = cont.get(i["regra"], 0) + 1
        rid, n = max(cont.items(), key=lambda kv: kv[1])
        nome = (regras.get(rid) or {}).get("nome") or rid
        frases.append(f"{_plural(c['criticos'], 'insight crítico aberto', 'insights críticos abertos')}"
                      + (f"; o mais comum: {nome} ({n})." if c["criticos"] > 1 else f": {nome}."))
    return " ".join(frases)


def _motivo_usina(s: dict) -> str:
    """O porquê da usina numa linha: o item mais baixo e o que o Nexus mediu nele (o mesmo texto da Visão gerencial)."""
    medidos = [i for i in s.get("itens") or [] if i.get("nota") is not None]
    if s.get("nota") is None:
        return ("Sem nota: " + (f"só {medidos[0]['nome'].lower()} foi medido." if medidos else "nenhum item medido.")
                if len(medidos) < G.MIN_ITENS else "Sem nota.")
    if not medidos:
        return ""
    pi = min(medidos, key=lambda i: i["nota"])
    if pi["nota"] >= G.EM_DIA:
        return "Todos os itens medidos em dia."
    return f"{pi['nome']} {pi['nota']}: {pi.get('mediu') or ''}".strip()


def resumo(g: dict, insights: list[dict], regras: dict | None = None) -> dict:
    """O que a tela mostra: os números do portfólio e o funil cliente → usina. `g` = o `gerencial.montar`; `insights` =
    os do motor que não foram concluídos; `regras` = o catálogo do motor (o nome de cada regra no porquê).
    {ok, mes, mes_ant, totais: {...}, parecer, clientes: [{cliente, usinas_n, mwp, nota, nota_ant, delta, tom, com_nota,
    abaixo, saude, saude_tom, em_risco, criticos, atencao, pior, itens, motivo, usinas: [{uid, usina, mwp, nota, nota_ant,
    delta, tom, saude, saude_tom, itens, motivo, insights, criticos, atencao}]}], avisos, gerado}, os clientes e as usinas
    do pior cumprimento para o melhor (sem nota no fim)."""
    regras = regras or {}
    ms = g.get("meses") or []
    atual = g.get("mes_atual") or (ms[0]["id"] if ms else "")
    ant = ms[1]["id"] if len(ms) > 1 else None
    nome_mes = {m["id"]: m.get("curto") or m["id"] for m in ms}
    mes_ant = nome_mes.get(ant, ant) if ant else ""
    ins_us: dict[str, list[dict]] = {}
    for i in insights or []:
        ins_us.setdefault(_norm(i.get("usina")), []).append(
            {"id": i.get("id"), "sev": i.get("sev") if i.get("sev") in _PESO else "info", "regra": i.get("regra"),
             "regra_nome": (regras.get(i.get("regra")) or {}).get("nome") or i.get("regra") or "",
             "titulo": i.get("titulo") or "", "acao": i.get("acao") or ""})
    linhas, todas_notas, todos_pontos = [], [], []
    for c in g.get("clientes") or []:
        us = c.get("usinas") or []
        notas = [(u, (u.get("score") or {}).get(atual) or {}) for u in us]
        com = [(u, s) for u, s in notas if s.get("nota") is not None]
        pontos = [u["pontos"] for u in us if u.get("pontos") is not None]
        todas_notas += [s["nota"] for _u, s in com]
        todos_pontos += pontos
        nota = ((c.get("score") or {}).get(atual) or {}).get("nota")
        nota_ant = ((c.get("score") or {}).get(ant) or {}).get("nota") if ant else None
        pior = min(com, key=lambda us_: us_[1]["nota"]) if com else None
        pi = _pior_item(pior[1]) if pior else None
        det = []
        for u, s in notas:
            na = (((u.get("score") or {}).get(ant) or {}).get("nota")) if ant else None
            vivos = sorted(ins_us.get(_norm(u["usina"])) or [], key=lambda i: _PESO[i["sev"]])
            det.append({"uid": u.get("uid"), "usina": u["usina"], "mwp": u.get("mwp"), "nota": s.get("nota"), "nota_ant": na,
                        "delta": (s["nota"] - na) if s.get("nota") is not None and na is not None else None,
                        "tom": tom(s.get("nota")), "saude": u.get("pontos"), "saude_tom": tom(u.get("pontos")),
                        "itens": [dict(i, tom=tom(i.get("nota"))) for i in s.get("itens") or []],
                        "motivo": _motivo_usina(s), "insights": vivos,
                        "criticos": sum(1 for i in vivos if i["sev"] == "critico"),
                        "atencao": sum(1 for i in vivos if i["sev"] == "atencao")})
        det.sort(key=lambda x: (x["nota"] is None, x["nota"] if x["nota"] is not None else 0, -x["criticos"],
                                str(x["usina"]).lower()))
        linha = {
            "cliente": c["cliente"], "usinas_n": c.get("usinas_n") or len(us), "mwp": c.get("mwp"),
            "nota": nota, "nota_ant": nota_ant, "tom": tom(nota),
            "delta": (nota - nota_ant) if nota is not None and nota_ant is not None else None,
            "com_nota": len(com), "abaixo": sum(1 for _u, s in com if s["nota"] < G.ATENCAO),
            "saude": c.get("media"), "saude_tom": tom(c.get("media")),
            "em_risco": sum(1 for p in pontos if p < G.ATENCAO),
            "criticos": sum(u["criticos"] for u in det), "atencao": sum(u["atencao"] for u in det),
            "pior": ({"usina": pior[0]["usina"], "uid": pior[0].get("uid"), "nota": pior[1]["nota"], "tom": tom(pior[1]["nota"]),
                      "item": (f"{pi['nome']} {pi['nota']}" if pi else "")} if pior else None),
            "itens": _itens_do_cliente([s for _u, s in notas]), "usinas": det}
        linha["motivo"] = _motivo_cliente(linha, mes_ant, regras)
        linha["puxa"] = min((i for i in linha["itens"] if i["media"] < G.EM_DIA), key=lambda i: i["media"], default=None)
        linhas.append(linha)
    linhas.sort(key=lambda x: (x["nota"] is None, x["nota"] if x["nota"] is not None else 0, -(x["mwp"] or 0)))
    t = g.get("totais") or {}
    media = _media(todas_notas)
    saude = _media(todos_pontos)
    tot = {"clientes": t.get("clientes", len(linhas)), "usinas": t.get("usinas"), "mwp": t.get("mwp"),
           "nota": media, "tom": tom(media), "com_nota": len(todas_notas),
           "abaixo": sum(1 for n in todas_notas if n < G.ATENCAO),
           "em_dia": sum(1 for n in todas_notas if n >= G.EM_DIA),
           "saude": saude, "saude_tom": tom(saude), "em_risco": sum(1 for p in todos_pontos if p < G.ATENCAO),
           "criticos": sum(1 for i in insights or [] if i.get("sev") == "critico"),
           "atencao": sum(1 for i in insights or [] if i.get("sev") == "atencao")}
    return {"ok": True, "mes": nome_mes.get(atual, atual), "mes_ant": mes_ant, "totais": tot,
            "parecer": _parecer(tot, linhas, nome_mes.get(atual, atual)),
            "clientes": linhas, "avisos": list(g.get("avisos") or []), "gerado": g.get("gerado") or ""}


def _parecer(t: dict, clientes: list[dict], mes: str) -> str:
    """A linha do alto: a nota do portfólio e onde ele aperta (os clientes abaixo de 55, os que caíram)."""
    if t["nota"] is None:
        return f"Sem nota de cumprimento do contrato em {mes}: falta dado medido nas usinas."
    ruins = [c["cliente"] for c in clientes if c["nota"] is not None and c["nota"] < G.ATENCAO]
    caiu = [c["cliente"] for c in clientes if (c["delta"] or 0) <= -5 and c["cliente"] not in ruins]
    f = [f"Em {mes}, até ontem, o portfólio cumpre {t['nota']} de 100 do contrato, na média de "
         f"{_plural(t['com_nota'], 'usina', 'usinas')}."]
    if ruins:
        f.append(f"Em risco: {_e(ruins)}.")
    if caiu:
        f.append(f"Caíram 5 pontos ou mais: {_e(caiu[:4])}{' e outros' if len(caiu) > 4 else ''}.")
    if not ruins and not caiu:
        f.append("Nenhum cliente abaixo de 55 nem em queda forte.")
    return " ".join(f)


def secoes_dossie(g: dict, insights: list[dict], regras: dict, primeira: int) -> str:
    """As duas seções que o dossiê da carteira ganha no Nexus Insights, numeradas a partir de `primeira`: o cumprimento do
    contrato e a saúde de cada usina (o mês atual e o anterior, com o item que mais puxa a nota para baixo), e os
    insights abertos do motor de regras (os críticos primeiro, até `MAX_INSIGHTS_IA`). Sem valor de contrato e sem pessoa."""
    ms = g.get("meses") or []
    atual = g.get("mes_atual") or (ms[0]["id"] if ms else "")
    ant = ms[1]["id"] if len(ms) > 1 else None
    nm = {m["id"]: m.get("curto") or m["id"] for m in ms}
    r = resumo(g, insights)
    cab_cli = ["Cliente", "Usinas", "MWp", f"Cumprimento do contrato em {nm.get(atual, atual)}"]
    cab_cli += [f"Cumprimento em {nm.get(ant)}"] if ant else []
    cab_cli += ["Usinas com nota", "Usinas abaixo de 55", "Saúde média", "Usinas em risco na saúde", "Insights críticos",
                "Insights de atenção", "Usina com a pior nota"]
    lin_cli = [[c["cliente"], c["usinas_n"], CI._num(c["mwp"], 1), c["nota"] if c["nota"] is not None else "—"]
               + ([c["nota_ant"] if c["nota_ant"] is not None else "—"] if ant else [])
               + [c["com_nota"], c["abaixo"], c["saude"] if c["saude"] is not None else "—", c["em_risco"], c["criticos"],
                  c["atencao"], (f"{c['pior']['usina']} ({c['pior']['nota']}{'; ' + c['pior']['item'] if c['pior']['item'] else ''})"
                                 if c["pior"] else "—")] for c in r["clientes"]]
    usinas = []
    for c in g.get("clientes") or []:
        for u in c.get("usinas") or []:
            s = (u.get("score") or {}).get(atual) or {}
            sa = ((u.get("score") or {}).get(ant) or {}) if ant else {}
            if s.get("nota") is None and sa.get("nota") is None and u.get("pontos") is None:
                continue
            pi = _pior_item(s)
            usinas.append((s.get("nota") if s.get("nota") is not None else 999, u["usina"].lower(),
                           [u["usina"], c["cliente"], s.get("nota") if s.get("nota") is not None else "—"]
                           + ([sa.get("nota") if sa.get("nota") is not None else "—"] if ant else [])
                           + [f"{pi['nome']} {pi['nota']}: {pi['mediu']}" if pi else "—",
                              u.get("pontos") if u.get("pontos") is not None else "—"]))
    usinas.sort(key=lambda x: (x[0], x[1]))
    cab_us = ["Usina", "Cliente", f"Cumprimento em {nm.get(atual, atual)}"] + ([f"Cumprimento em {nm.get(ant)}"] if ant else []) \
        + ["Item que mais puxa a nota para baixo", "Saúde (pontos)"]
    t = r["totais"]
    sec1 = [f"## {primeira}. Cumprimento do contrato e saúde", "",
            "Fonte: Comando › Visão gerencial (a nota de cumprimento do contrato de cada usina, mês a mês) e a pontuação de "
            "saúde do dossiê do cliente.", "",
            "- A nota de cumprimento do contrato vai de 0 a 100 e é a média de quatro itens: a disponibilidade contra a "
            "garantida no contrato, a geração e o PR, as rotinas (ronda e plano da semana) e os prazos de OS. Item sem dado "
            "fica fora; com menos de 2 itens, a usina fica sem nota.",
            f"- Régua: {G.EM_DIA} ou mais em dia; {G.ATENCAO} a {G.EM_DIA - 1} atenção; abaixo de {G.ATENCAO} risco. A "
            "saúde (pontos) usa a mesma régua.",
            f"- O mês atual ({nm.get(atual, atual)}) é parcial, até ontem.",
            f"- No portfólio: {t['com_nota']} usinas com nota em {nm.get(atual, atual)}, média {t['nota'] if t['nota'] is not None else '—'}; "
            f"{t['abaixo']} abaixo de {G.ATENCAO} e {t['em_dia']} em dia. Saúde média {t['saude'] if t['saude'] is not None else '—'}, "
            f"{t['em_risco']} usinas em risco.", "",
            "Por cliente, do pior cumprimento para o melhor:", ""] + CI._tabela(cab_cli, lin_cli) + [
            "", "Por usina, da pior nota para a melhor (sem nota no fim):", ""] + CI._tabela(cab_us, [x[2] for x in usinas])
    vivos = sorted(insights or [], key=lambda i: (_PESO.get(i.get("sev"), 3), str(i.get("usina") or "")))
    corte = vivos[:MAX_INSIGHTS_IA]
    rot = {"critico": "crítico", "atencao": "atenção", "info": "informativo"}
    sec2 = [f"## {primeira + 1}. Insights abertos do motor de regras", "",
            "Fonte: Comando › Nexus Insights (as regras do Nexus que cruzam as fontes; cada insight tem a ação proposta).", ""]
    if corte:
        sec2 += CI._tabela(["Severidade", "Regra", "Usina", "O que é", "Ação proposta", "Setor dono"],
                           [[rot.get(i.get("sev"), i.get("sev")), (regras.get(i.get("regra")) or {}).get("nome") or i.get("regra"),
                             i.get("usina") or "—", i.get("titulo") or "—", i.get("acao") or "—",
                             (regras.get(i.get("regra")) or {}).get("torre") or "—"] for i in corte])
        if len(vivos) > len(corte):
            sec2 += ["", f"- Mais {len(vivos) - len(corte)} insights abertos de menor severidade ficaram fora."]
    else:
        sec2 += ["- Nenhum insight aberto agora."]
    return "\n".join(sec1 + [""] + sec2) + "\n"


INSTRUCOES = CI.INSTRUCOES + """

Neste Nexus Insights o dossiê traz também o cumprimento do contrato e a saúde de cada usina e cliente, e os insights abertos do motor de regras:
- Para comparar clientes, usinas ou meses no cumprimento do contrato, use as tabelas da seção "Cumprimento do contrato e saúde": as notas já vêm calculadas, e a coluna "Item que mais puxa a nota para baixo" diz o porquê. Não recalcule a nota.
- Quando falar de uma nota, diga o mês (o atual é parcial) e o item que a puxa para baixo.
- Os insights abertos são o que o Nexus já apontou: cite a severidade e a ação proposta."""

# As perguntas sugeridas, uma por cadeira (Levi, 19/11/2026: "perguntas que um CEO, que um gerente de contratos, que um
# head faria, que um supervisor faria"), no tom de quem acompanha, não de quem acusa: a tela é aberta por várias pessoas
# (Levi, no mesmo dia: "suavize essas perguntas, outras pessoas também terão acesso"). Todas se respondem com o dossiê de
# agora (o cumprimento por item, a variação do mês, os insights com o setor dono, a ronda e as OS de cada usina).
SUGESTOES = ("Quais clientes pedem mais atenção neste mês, e por quê?",                                  # diretoria
             "Em quais itens do contrato estamos abaixo do esperado neste mês, e em quais usinas?",       # contratos
             "Quais 5 usinas, tratadas esta semana, mais ajudam a nota do portfólio?",                    # head
             "O que mudou do mês passado para este, e qual setor acompanha cada ponto?",                  # head
             "Quais usinas estão há mais tempo sem ronda e quais OS urgentes aguardam início?")           # supervisor

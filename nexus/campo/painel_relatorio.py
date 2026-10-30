"""O relatório do Painel do responsável em PDF (29/10/2026).

Levi: "Botão de baixar relatório: ao extremo lado direto da mesma linha dos filtros deve ter um botão de exportar
relatório. será em PDF com basicamente o que tem focado no que falta para o supervisor, para não ficar tanta
informação, terá um resumo no início e depois aprofunda!"

- **O dado é o da tela:** o `painel` que o Painel desenha (`painel_responsavel.montar`, os mesmos filtros), a faixa
  "Parada agora" e as OSs em verificação (`verificacao.oss`, da fila guardada). Nada é recalculado aqui.
- **Primeiro o resumo:** os números de cada quadro e "O que cobrar primeiro", as frases do que falta, a pior primeiro.
- **Depois o detalhe, só o que falta:** as usinas abaixo da meta (não as que estão na meta), as paradas, as PT, as OSs
  em verificação, os chamados abertos, as usinas sem ronda há 7 dias ou mais (e as que nunca tiveram) e a longa
  pendente, os extintores vencidos e o ranking das equipes.
- Fonte Helvetica, como o relatório dos extintores (`nexus/hseq/relatorio.py`, o mesmo reportlab e a mesma paleta):
  nada de "≥" ou de seta, que ela não tem.
"""
import io
from xml.sax.saxutils import escape

from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import CondPageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

rl_config.useA85 = 0        # binário, sem ASCII85 (o arquivo 25% menor; ver o relatório dos extintores)

NAVY, VERDE = colors.HexColor("#090d18"), colors.HexColor("#b5d334")
TOM = {"critico": colors.HexColor("#c8102e"), "alerta": colors.HexColor("#b26a00"), "ok": colors.HexColor("#1f7a3f"),
       "neutro": colors.HexColor("#5b6475")}
LINHA, FUNDO, MUDO, TINTA = (colors.HexColor("#d8dce4"), colors.HexColor("#f3f5f8"), colors.HexColor("#5b6475"),
                             colors.HexColor("#111827"))
SITUACAO_RONDA = {"nunca": "nunca teve ronda pelo App", "sem_ronda": "sem ronda há 7 dias ou mais",
                  "longa_pendente": "ronda longa pendente"}
MAX_FRASE = 4               # nomes por frase do resumo, o resto vira "e mais N"
# os temas que a pessoa escolhe levar (Levi, 30/10/2026: "gostaria que na parte de relatório a pessoa possa marcar o tema
# que ela quer levar, as vezes não quer algo, tem que ter a opção de tirar"): a chave, o rótulo da janela e do PDF. O
# tema que fica de fora sai do resumo, de "O que cobrar primeiro" e do detalhe; sem escolha nenhuma, vão todos
TEMAS = (("perf", "Usinas abaixo da meta"), ("paradas", "Parada agora"), ("pts", "PTs pendentes"),
         ("verif", "OSs em verificação"), ("chamados", "Chamados de garantia"), ("rondas", "Rondas"),
         ("extintores", "Extintores vencidos"), ("ranking", "Ranking das equipes"))
CHAVES_TEMAS = tuple(k for k, _ in TEMAS)


def temas_do_pedido(pedidos) -> tuple:
    """Os temas pedidos, na ordem do relatório (o que não é tema não entra); nenhum pedido válido = todos."""
    quer = {str(x).strip() for x in pedidos or ()}
    temas = tuple(k for k in CHAVES_TEMAS if k in quer)
    return temas or CHAVES_TEMAS


def _t(v) -> str:
    s = "" if v is None else str(v)
    for a, b in (("≥", ">="), ("→", "->"), (" ", " "), (" ", " ")):
        s = s.replace(a, b)
    return escape(s)


def _tom(texto: str, c: str, negrito: bool = False) -> str:
    t = f'<font color="#{TOM.get(c, TOM["neutro"]).hexval()[2:]}">{texto}</font>'
    return f"<b>{t}</b>" if negrito else t


def _pct(v, casas: int = 0) -> str:
    if v is None:
        return "—"
    return (f"{v:.{casas}f}%").replace(".", ",")


def _nomes(xs: list[str]) -> str:
    xs = [x for x in xs if x]
    return ", ".join(xs[:MAX_FRASE]) + (f" e mais {len(xs) - MAX_FRASE}" if len(xs) > MAX_FRASE else "")


def _estilos() -> dict:
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=8.4, leading=10.8, textColor=TINTA)
    return {"base": base,
            "mudo": ParagraphStyle("mudo", parent=base, textColor=MUDO, fontSize=7.6, leading=9.8),
            "titulo": ParagraphStyle("titulo", parent=base, fontName="Helvetica-Bold", fontSize=17, leading=21,
                                     textColor=colors.white),
            "eyebrow": ParagraphStyle("eyebrow", parent=base, fontName="Helvetica-Bold", fontSize=7.4, leading=9,
                                      textColor=VERDE),
            "faixa_sub": ParagraphStyle("faixa_sub", parent=base, fontSize=8.6, leading=11,
                                        textColor=colors.HexColor("#c9d1e3")),
            "secao": ParagraphStyle("secao", parent=base, fontName="Helvetica-Bold", fontSize=11, leading=14,
                                    spaceBefore=8, spaceAfter=4),
            "cab": ParagraphStyle("cab", parent=base, fontName="Helvetica-Bold", fontSize=7, leading=9, textColor=MUDO),
            "num": ParagraphStyle("num", parent=base, fontName="Helvetica-Bold", fontSize=16, leading=19),
            "rot": ParagraphStyle("rot", parent=base, fontName="Helvetica-Bold", fontSize=7.2, leading=9,
                                  textColor=MUDO),
            "frase": ParagraphStyle("frase", parent=base, fontSize=8.8, leading=12, leftIndent=10, bulletIndent=0)}


def _tabela(e: dict, cab: list[str], linhas: list[list], larguras: list[float]) -> Table:
    dados = [[Paragraph(_t(c).upper(), e["cab"]) for c in cab]]
    dados += [[c if isinstance(c, Paragraph) else Paragraph(_t(c), e["base"]) for c in l] for l in linhas]
    t = Table(dados, colWidths=larguras, repeatRows=1)
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 0.6, LINHA),
                           ("LINEBELOW", (0, 1), (-1, -1), 0.3, LINHA), ("BACKGROUND", (0, 0), (-1, 0), FUNDO),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                           ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]))
    return t


def _p(txt: str, e: dict, estilo: str = "base") -> Paragraph:
    """Um parágrafo de texto já pronto (com as marcas do `_tom`); o dado de fora entra pelo `_t`."""
    return Paragraph(txt, e[estilo])


def resumo(painel: dict, faixa: list, verif: dict | None, temas=CHAVES_TEMAS) -> list[dict]:
    """Os números do resumo: [{"tema", "rot", "num", "cor", "txt"}], na ordem da tela, só dos `temas` escolhidos."""
    pf, pt, ch, rd, ex, rk = (painel["perf"], painel["pts"], painel["chamados"], painel["rondas"], painel["extintores"],
                              painel["ranking"])
    n_verif = len(verif["lista"]) if verif else None
    todos = [
        {"tema": "perf", "rot": "Usinas abaixo da meta", "num": pf["abaixo"], "cor": "critico" if pf["criticas"] else (
            "alerta" if pf["abaixo"] else "ok"),
         "txt": f"de {pf['com_meta']} com meta · {pf['criticas']} abaixo de 90% · meta do grupo {_pct(pf['meta_grupo'], 1)}"},
        {"tema": "paradas", "rot": "Parada agora", "num": len(faixa), "cor": "critico" if faixa else "ok",
         "txt": "OS de parada abertas" if faixa else "nenhuma parada aberta"},
        {"tema": "pts", "rot": "PTs pendentes", "num": pt["aguardando"], "cor": "critico" if pt["paradas"] else (
            "alerta" if pt["aguardando"] else "ok"),
         "txt": f"esperando o De acordo · {pt['paradas']} há mais de 2 h"},
        {"tema": "verif", "rot": "OSs em verificação", "num": n_verif if n_verif is not None else "—",
         "cor": "neutro" if n_verif is None else ("alerta" if n_verif else "ok"),
         "txt": "esperando concluir" if n_verif is not None else "a fila ainda não foi lida neste servidor"},
        {"tema": "chamados", "rot": "Chamados abertos", "num": ch["abertos"], "cor": "alerta" if ch["abertos"] else "ok",
         "txt": f"em {ch['usinas']} usina{'s' if ch['usinas'] != 1 else ''}"
                + (f" · o mais antigo há {ch['mais_antigo']} d" if ch.get("mais_antigo") is not None else "")},
        {"tema": "rondas", "rot": "Sem ronda há 7 dias ou mais", "num": rd["sem_7"],
         "cor": "critico" if rd["sem_7"] else "ok",
         "txt": f"{rd['nunca']} nunca teve · {rd['em_dia']} de {rd['usinas']} em dia"},
        {"tema": "extintores", "rot": "Extintores vencidos", "num": ex["vencidos"],
         "cor": "critico" if ex["vencidos"] else "ok",
         "txt": f"em {ex['usinas']} usina{'s' if ex['usinas'] != 1 else ''} · {ex['a_vencer']} a vencer"},
        {"tema": "ranking", "rot": f"Equipes ({rk['mes']})", "num": rk["n_equipes"], "cor": "neutro",
         "txt": f"no ranking de {rk['total']} equipes"},
    ]
    return [x for x in todos if x["tema"] in temas]


def frases(painel: dict, faixa: list, verif: dict | None, temas=CHAVES_TEMAS) -> list[str]:
    """O que cobrar primeiro, em frases curtas: o que está parado, o que está vencido e o que falta, nessa ordem, só dos
    `temas` escolhidos. Já com as marcas de cor (texto de fora escapado)."""
    pf, pt, ch, rd, ex, rk = (painel["perf"], painel["pts"], painel["chamados"], painel["rondas"], painel["extintores"],
                              painel["ranking"])
    out = []
    if faixa and "paradas" in temas:
        out.append(_tom(f"{len(faixa)} parada{'s' if len(faixa) != 1 else ''} agora", "critico", True) + ": "
                   + _t(_nomes([f"{u['usina']} ({p.get('escopo') or '—'}, desde {p.get('inicio')})" for u, p in faixa])))
    if pt["paradas"] and "pts" in temas:
        out.append(_tom(f"{pt['paradas']} PT parada{'s' if pt['paradas'] != 1 else ''} há mais de 2 h", "critico", True)
                   + ": " + _t(_nomes([f"{p.get('numero') or ''} {p['usina']}".strip() for p in pt["linhas"]
                                       if p.get("parada")])))
    criticas = [x for x in pf["linhas"] if x["situacao"] == "critico"] if "perf" in temas else []
    if criticas:
        out.append(_tom(f"{len(criticas)} usina{'s' if len(criticas) != 1 else ''} abaixo de 90% da meta", "critico",
                        True) + ": " + _t(_nomes([f"{x['usina']} ({_pct(x['atingimento'])})" for x in criticas])))
    nunca = [x["usina"] for x in rd["linhas"] if x["situacao"] == "nunca"] if "rondas" in temas else []
    sem = ([f"{x['usina']} ({x['dias']} d)" for x in rd["linhas"] if x["situacao"] == "sem_ronda"]
           if "rondas" in temas else [])
    if nunca:
        out.append(_tom(f"{len(nunca)} usina{'s' if len(nunca) != 1 else ''} sem nenhuma ronda pelo App", "critico", True)
                   + ": " + _t(_nomes(nunca)))
    if sem:
        out.append(_tom(f"{len(sem)} usina{'s' if len(sem) != 1 else ''} sem ronda há 7 dias ou mais", "alerta", True)
                   + ": " + _t(_nomes(sem)))
    if ex["vencidos"] and "extintores" in temas:
        out.append(_tom(f"{ex['vencidos']} extintor{'es' if ex['vencidos'] != 1 else ''} vencido"
                        f"{'s' if ex['vencidos'] != 1 else ''}", "critico", True) + ": "
                   + _t(_nomes([f"{x['usina']} ({x['vencidos']})" for x in ex["linhas"]])))
    if verif and verif["lista"] and "verif" in temas:
        v = verif["lista"]
        out.append(_tom(f"{len(v)} OS{'s' if len(v) != 1 else ''} em verificação esperando concluir", "alerta", True)
                   + _t(f": a mais antiga é a OS {v[0]['os']} ({v[0]['usina']}), há {v[0]['espera']}"))
    if ch["grupos"] and "chamados" in temas:
        g = ch["grupos"][0]
        it = g["itens"][0]
        out.append(_tom(f"{ch['abertos']} chamado{'s' if ch['abertos'] != 1 else ''} de garantia em aberto", "alerta",
                        True) + _t(f": o mais antigo é a OS {it.get('os') or '—'} ({g['usina']}, {it['ativo']}"
                                   + (f", há {it['dias']} d" if it.get("dias") is not None else "") + ")"))
    piores = ([c for c in reversed(rk["equipes"]) if c.get("nota") is not None and not c.get("sem_equipe")][:1]
              if "ranking" in temas else [])
    if piores:
        c = piores[0]
        out.append(_tom("Equipe com a menor nota", "alerta", True)
                   + _t(f": {c['equipe']}, nota {c['nota']}" + (f" ({c['posicao']}º de {rk['total']})"
                                                                  if c.get("posicao") else "")))
    return out


def gerar(painel: dict, faixa: list, verif: dict | None, *, filtros: list[str], gerado_em: str,
          temas=CHAVES_TEMAS) -> bytes:
    """O PDF: a faixa com o nome, o resumo, o que cobrar primeiro e o detalhe de cada quadro, só o que falta e só dos
    `temas` escolhidos (`TEMAS`; todos sem escolha)."""
    e = _estilos()
    buf = io.BytesIO()
    pagina = landscape(A4)
    largura = pagina[0] - 24 * mm
    doc = SimpleDocTemplate(buf, pagesize=pagina, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=11 * mm,
                            bottomMargin=11 * mm, title=f"Painel do responsável · {painel['nome']}",
                            author="Nexus · Grid Co.")
    h = []
    sub = (f"{painel['usinas']} usina{'s' if painel['usinas'] != 1 else ''} · "
           f"{', '.join(painel['clientes']) or 'sem cliente'} · {len(painel['equipes'])} equipe"
           f"{'s' if len(painel['equipes']) != 1 else ''} · gerado em {gerado_em}")
    faixa_cab = Table([[[Paragraph("PAINEL DO RESPONSÁVEL", e["eyebrow"]), Paragraph(_t(painel["nome"]), e["titulo"]),
                         Paragraph(_t(sub), e["faixa_sub"])]]], colWidths=[largura])
    faixa_cab.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NAVY), ("LEFTPADDING", (0, 0), (-1, -1), 10),
                                   ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                                   ("LINEBELOW", (0, 0), (-1, -1), 2.2, VERDE)]))
    h += [faixa_cab, Spacer(1, 4)]
    if filtros:
        h.append(_p(_t("Filtros da tela: " + " · ".join(filtros)), e, "mudo"))
    if tuple(temas) != CHAVES_TEMAS:
        rot = dict(TEMAS)
        h.append(_p(_t("Temas escolhidos: " + " · ".join(rot[k] for k in temas)), e, "mudo"))
    # 1. o resumo: os números, quatro por linha
    h.append(_p("Resumo", e, "secao"))
    nums = resumo(painel, faixa, verif, temas)
    caixas = [[Paragraph(_t(n["rot"]).upper(), e["rot"]),
               Paragraph(_tom(_t(n["num"]), n["cor"], True), e["num"]), Paragraph(_t(n["txt"]), e["mudo"])]
              for n in nums]
    linhas = [caixas[i:i + 4] for i in range(0, len(caixas), 4)]
    if linhas and len(linhas[-1]) < 4:          # a tabela é retangular: a última linha leva casas vazias
        linhas[-1] = linhas[-1] + [""] * (4 - len(linhas[-1]))
    # a moldura e o fundo só nas caixas com número: com temas tirados, as casas vazias não viram caixas em branco
    estilo = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 6),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LEFTPADDING", (0, 0), (-1, -1), 7)]
    for i in range(len(caixas)):
        estilo += [("BOX", (i % 4, i // 4), (i % 4, i // 4), 0.5, LINHA),
                   ("BACKGROUND", (i % 4, i // 4), (i % 4, i // 4), FUNDO)]
    t = Table(linhas, colWidths=[largura / 4] * 4)
    t.setStyle(TableStyle(estilo))
    h.append(t)
    fr = frases(painel, faixa, verif, temas)
    h.append(_p("O que cobrar primeiro", e, "secao"))
    if fr:
        h += [Paragraph(f, e["frase"], bulletText="•") for f in fr]
    else:
        h.append(_p("Nada pedindo ação agora nas usinas da tela.", e))
    # 2. o detalhe, só o que falta
    pf = painel["perf"]
    abaixo = [x for x in pf["linhas"] if x["situacao"] in ("critico", "alerta")] if "perf" in temas else []

    def secao(titulo: str, tabela: Table) -> None:
        # o título nunca fica sozinho no pé da página: sem 4 cm sobrando, a seção começa na seguinte
        h.extend([CondPageBreak(40 * mm), _p(_t(titulo), e, "secao"), tabela])
    if abaixo:
        L = [[x["usina"], x["cliente"] or "—",
              _p(_tom(_pct(x["atingimento"]), x["situacao"], True), e),
              (f"{_pct(x['pr'], 1)} de {_pct(x['pr_meta'], 1)}" if x.get("pr") is not None else "—"),
              _pct(x["disp"], 1), x["sujidade"] if x.get("sujidade") is not None else "—",
              x["vegetacao"] if x.get("vegetacao") is not None else "—"] for x in abaixo]
        secao(f"Usinas abaixo da meta ({len(abaixo)})",
              _tabela(e, ["Usina", "Cliente", "Meta do mês", "PR × previsto", "Disponibilidade", "Sujidade",
                          "Vegetação"], L, [w * largura for w in (.24, .16, .11, .15, .12, .11, .11)]))
    if faixa and "paradas" in temas:
        L = [[u["usina"], p.get("escopo") or "—", f"OS {p.get('os')}", p.get("inicio") or "—"] for u, p in faixa]
        secao(f"Parada agora ({len(faixa)})",
              _tabela(e, ["Usina", "Onde", "OS", "Desde"], L, [w * largura for w in (.3, .4, .12, .18)]))
    pt = painel["pts"]
    if pt["linhas"] and "pts" in temas:
        L = [[x.get("numero") or f"OS {x.get('os') or ''}", x["usina"], x.get("tarefa") or "—",
              _p(_tom(_t(_idade(x.get("idade_min"))), "critico" if x.get("parada") else "alerta", True), e)]
             for x in pt["linhas"]]
        secao(f"PTs esperando o De acordo ({len(pt['linhas'])})",
              _tabela(e, ["PT", "Usina", "Tarefa", "Esperando"], L, [w * largura for w in (.14, .24, .47, .15)]))
    if verif and verif["lista"] and "verif" in temas:
        L = [[f"OS {o['os']}", o["usina"], o["titulo"] or "—", o["tecnico"] or "—", o["ativos"], o["espera"]]
             for o in verif["lista"]]
        secao(f"OSs em verificação esperando concluir ({len(verif['lista'])})",
              _tabela(e, ["OS", "Usina", "Título", "Técnico", "Ativos", "Sem conclusão"], L,
                      [w * largura for w in (.09, .19, .34, .2, .07, .11)]))
    ch = painel["chamados"]
    if ch["grupos"] and "chamados" in temas:
        L = [[g["usina"], it["ativo"], it.get("status") or "sem status", f"OS {it.get('os') or '—'}",
              f"{it['dias']} d" if it.get("dias") is not None else "—"] for g in ch["grupos"] for it in g["itens"]]
        secao(f"Chamados de garantia em aberto ({ch['abertos']})",
              _tabela(e, ["Usina", "Ativo", "Status", "OS", "Aberto há"], L, [w * largura for w in (.24, .24, .3, .11, .11)]))
    rd = painel["rondas"]
    falta = [x for x in rd["linhas"] if x["situacao"] in SITUACAO_RONDA] if "rondas" in temas else []
    if falta:
        L = [[x["usina"], _p(_tom(_t(SITUACAO_RONDA[x["situacao"]]), "critico" if x["situacao"] != "longa_pendente"
                                  else "alerta", True), e),
              (f"{x['ultima']} ({x['dias']} d)" if x.get("ultima") else "—"), x.get("tecnico") or "—"] for x in falta]
        secao(f"Rondas que faltam ({len(falta)})",
              _tabela(e, ["Usina", "Situação", "Última ronda", "Quem fez a última"], L,
                      [w * largura for w in (.28, .28, .22, .22)]))
    ex = painel["extintores"]
    if ex["linhas"] and "extintores" in temas:
        L = [[x["usina"], x["vencidos"], x["a_vencer"], (f"{x['pior_ext']}: " if x.get("pior_ext") else "") + (x["pior"] or "—")]
             for x in ex["linhas"]]
        secao(f"Extintores vencidos ({ex['vencidos']})",
              _tabela(e, ["Usina", "Vencidos", "A vencer", "O pior"], L, [w * largura for w in (.28, .1, .1, .52)]))
    rk = painel["ranking"]
    if rk["equipes"] and "ranking" in temas:
        L = [[f"{c['posicao']}º" if c.get("posicao") else "—", c["equipe"] if not c.get("sem_equipe") else "Sem equipe",
              c.get("nota") if c.get("nota") is not None else "—",
              c.get("qualidade") if c.get("qualidade") is not None else "—",
              _pct(c.get("cobertura")) if c.get("cobertura") is not None else "—",
              c.get("n_os", 0), c.get("n_ronda", 0)] for c in rk["equipes"]]
        secao(f"Ranking das equipes · {rk['mes']} ({rk['n_equipes']} equipes, de {rk['total']})",
              _tabela(e, ["Posição", "Equipe", "Nota", "Qualidade", "Cobertura", "Tarefas", "Rondas"], L,
                      [w * largura for w in (.1, .34, .1, .12, .12, .11, .11)]))
    if "ranking" in temas:
        h += [Spacer(1, 6), _p(_t("A nota da equipe = 60% da qualidade (a média das notas das tarefas e rondas do "
                                  "App) + 40% da cobertura (usinas com ronda no mês)."), e, "mudo")]
    h.append(_p(_t("Os números são os da tela, na hora em que o relatório foi gerado."), e, "mudo"))
    doc.build(h)
    return buf.getvalue()


def _idade(m) -> str:
    if m is None:
        return "—"
    m = int(m)
    if m >= 1440:
        return f"{m // 1440} d {(m % 1440) // 60} h"
    if m >= 60:
        return f"{m // 60} h {m % 60} min"
    return f"{m} min"

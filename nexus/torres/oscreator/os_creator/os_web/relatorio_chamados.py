# os_creator/os_web/relatorio_chamados.py
"""O relatório dos chamados de garantia em andamento de UM cliente, para mandar ao cliente (Levi, 28/10/2026: "Incluir
um botão de Exportar Relatório use a referência do relatório dois mas deixe mais polido visualmente e no linguajar para
enviar para o cliente, quero conseguir exportar por cliente").

A referência é a "Atualização dos chamados de garantia" que a gestão de chamados mandava a um cliente: o resumo
executivo (quantos em andamento e com quem está cada um), a visão por usina e os chamados agrupados por quem precisa agir.
Aqui tudo sai do quadro do Acompanhamento de chamados: o status geral (Cliente, Fabricante, Grid, Standby; automático pelo
status, `acomp_web.GERAL_DO_STATUS`) agrupa; a "última atualização" de cada chamado é a última observação escrita na tela
(por isso ela é escrita pensando que o cliente vai ler); o supervisor da usina é o Responsável UFV do cadastro do Nexus.

`modelo()` é o conteúdo (os testes conferem nele); `gerar()` desenha, com o reportlab, no visual do PDF da OS
(`os_pdf.gerar`: a faixa navy com o logo e o fio verde)."""
from __future__ import annotations

import datetime as dt
import os
import re
import unicodedata

from . import acomp_web as aw
from .os_pdf import _seguro, _texto

# a ordem das seções e o nome que o cliente lê; sem status geral, "Em acompanhamento"
SECOES = (("Cliente", "Aguardando o cliente"), ("Fabricante", "Aguardando o fabricante"),
          ("Grid", "Em tratativa pela Grid Co."), ("Standby", "Em standby"), ("", "Em acompanhamento"))
LOGO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "grid-logo.png")


def nome_de_arquivo(texto: str) -> str:
    """O nome do cliente num nome de arquivo (sem / \\ : * ? " < > |)."""
    return re.sub(r'[\\/:*?"<>|]+', "-", " ".join(str(texto or "").split())).strip(" .-") or "cliente"


def _lista(itens) -> str:
    """"A", "A e B", "A, B e C"."""
    itens = [x for x in itens if x]
    return itens[0] if len(itens) == 1 else (", ".join(itens[:-1]) + " e " + itens[-1]) if itens else ""


def _plural(n: int, um: str, varios: str) -> str:
    return "%d %s" % (n, um if n == 1 else varios)


def _data(iso) -> str:
    try:
        return dt.datetime.fromisoformat(str(iso)).strftime("%d/%m")
    except ValueError:
        return ""


def _sem_acento(t) -> str:
    return unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()


def modelo(cards, cliente: str, hoje: dt.datetime, obs: dict) -> dict:
    """O conteúdo do relatório: os chamados EM ANDAMENTO (Chegaram e Ticket aberto) do cliente. `cards` = os cartões do
    quadro (`acomp_web.cartao`, com o `resp_ufv`); `obs` = {nº: (quando, texto)} da última observação de cada OS."""
    abertos = [c for c in cards if c.get("col") in ("chegou", "ticket") and c.get("cliente") == cliente]
    abertos.sort(key=lambda c: (-(c.get("dias") or 0), c.get("folio") or ""))
    numeros = {"andamento": len(abertos), "Cliente": 0, "Fabricante": 0, "Grid": 0, "Standby": 0, "sem": 0}
    usinas = {}
    for c in abertos:
        g = c.get("geral") or ""
        numeros[g or "sem"] += 1
        u = usinas.setdefault(c.get("usina") or "—", {"usina": c.get("usina") or "—", "total": 0, "Cliente": 0,
                                                       "Fabricante": 0, "Grid": 0, "Standby": 0, "sem": 0,
                                                       "responsavel": ""})
        u["total"] += 1
        u[g or "sem"] += 1
        u["responsavel"] = u["responsavel"] or c.get("resp_ufv") or ""
    secoes = []
    for g, nome in SECOES:
        itens = []
        for c in abertos:
            if (c.get("geral") or "") != g:
                continue
            quando, texto = obs.get(c.get("folio"), ("", ""))
            itens.append({"ref": ("Ticket %s" % c["ticket"]) if c.get("ticket") else "OS %s" % c.get("folio"),
                          "onde": " · ".join(x for x in (c.get("usina"), c.get("ativo_nome") or c.get("code")) if x),
                          "status": c.get("status_ch") or "", "fabricante": c.get("marca") or "",
                          "atualizacao": ("%s: %s" % (_data(quando), " ".join(str(texto).split()))) if texto else "",
                          "dias": c.get("dias")})
        if itens:
            secoes.append({"geral": g, "titulo": "%s (%d)" % (nome, len(itens)), "itens": itens})
    marcas = sorted({c.get("marca") for c in abertos if c.get("marca")}, key=_sem_acento)
    tipos = sorted({str(c.get("tipo") or "").lower() for c in abertos if c.get("tipo")}, key=_sem_acento)
    nomes_usinas = sorted(usinas, key=_sem_acento)
    if abertos:
        intro = "Segue a atualização %s de garantia em andamento%s%s%s." % (
            "do chamado" if len(abertos) == 1 else "dos %d chamados" % len(abertos),
            (" com %s %s" % ("o fabricante" if len(marcas) == 1 else "os fabricantes", _lista(marcas))) if marcas else "",
            (", para %s" % _lista(tipos)) if tipos else "",
            (", %s %s" % ("na usina" if len(nomes_usinas) == 1 else "nas usinas", _lista(nomes_usinas))))
    else:
        intro = "Não há chamados de garantia em andamento para o cliente %s nesta data." % cliente
    proximos = []
    if numeros["Cliente"]:
        proximos.append("Acompanhar com o cliente %s listad%s em “Aguardando o cliente”." % (
            _plural(numeros["Cliente"], "pendência", "pendências"), "a" if numeros["Cliente"] == 1 else "as"))
    if numeros["Fabricante"]:
        proximos.append("Cobrar do fabricante o retorno %s em análise." % (
            "do chamado" if numeros["Fabricante"] == 1 else "dos %d chamados" % numeros["Fabricante"]))
    if numeros["Grid"]:
        proximos.append("Concluir as ações da Grid Co. em %s (testes, abertura de OS e retornos internos)." %
                        _plural(numeros["Grid"], "chamado", "chamados"))
    antigos = [c for c in abertos if (c.get("dias") or 0) >= 60][:3]
    if antigos:
        proximos.append("Priorizar os chamados abertos há mais tempo: %s." % _lista(
            ["%s (%s, %d dias)" % (("Ticket %s" % c["ticket"]) if c.get("ticket") else "OS %s" % c["folio"],
                                    " · ".join(x for x in (c.get("usina"), c.get("ativo_nome")) if x), c["dias"])
             for c in antigos]))
    data = hoje.strftime("%d/%m/%Y")
    return {"cliente": cliente, "data": data,
            "titulo": "Atualização dos chamados de garantia · %s" % cliente,
            "subtitulo": "Gestão de Chamados · O&M Grid Co. · Posição de %s" % data,
            "cabecalho": "Grid Co. · O&M · Atualização de chamados %s · %s" % (cliente, data),
            "intro": intro, "numeros": numeros, "usinas": [usinas[n] for n in nomes_usinas],
            "secoes": secoes, "proximos": proximos}


def gerar(m: dict) -> bytes:
    """O PDF de `modelo()`, em A4, no visual do PDF da OS."""
    from io import BytesIO

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import CondPageBreak, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    navy, verde = colors.HexColor("#090d18"), colors.HexColor("#b5d334")
    linha, fundo, mudo, tinta = (colors.HexColor("#d8dce4"), colors.HexColor("#f3f5f8"), colors.HexColor("#5b6475"),
                                 colors.HexColor("#111827"))
    tom = {"Cliente": colors.HexColor("#1f5fa8"), "Fabricante": colors.HexColor("#b26a00"),
           "Grid": colors.HexColor("#1f7a3f"), "Standby": colors.HexColor("#5b6475"), "": colors.HexColor("#5b6475")}
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=9.2, leading=12.6, textColor=tinta)
    e = {"titulo": ParagraphStyle("titulo", parent=base, fontName="Helvetica-Bold", fontSize=17, leading=21),
         "sub": ParagraphStyle("sub", parent=base, fontSize=9.4, leading=12, textColor=mudo),
         "secao": ParagraphStyle("secao", parent=base, fontName="Helvetica-Bold", fontSize=11.5, leading=14,
                                 textColor=navy),
         "num": ParagraphStyle("num", parent=base, fontName="Helvetica-Bold", fontSize=20, leading=23, alignment=1),
         "numl": ParagraphStyle("numl", parent=base, fontSize=7.8, leading=9.6, textColor=mudo, alignment=1),
         "cab": ParagraphStyle("cab", parent=base, fontName="Helvetica-Bold", fontSize=7.6, leading=9.4, textColor=mudo),
         "cel": ParagraphStyle("cel", parent=base, fontSize=8.6, leading=11),
         "celc": ParagraphStyle("celc", parent=base, fontSize=8.6, leading=11, alignment=1),
         # o marcador fora do texto: as linhas que quebram ficam alinhadas com a primeira
         "item": ParagraphStyle("item", parent=base, fontSize=9, leading=12.4, leftIndent=11, bulletIndent=1),
         "mudo": ParagraphStyle("mudo", parent=base, fontSize=8.2, leading=11, textColor=mudo)}
    larg = 182 * mm

    def secao(titulo):
        t = Table([[Paragraph(_texto(titulo), e["secao"])]], colWidths=[larg])
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.8, verde), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        return [CondPageBreak(28 * mm), Spacer(1, 3 * mm), t, Spacer(1, 2.5 * mm)]

    def pagina(c, doc):
        c.saveState()
        w, h = A4
        c.setFillColor(navy)
        c.rect(0, h - 16 * mm, w, 16 * mm, stroke=0, fill=1)
        c.setFillColor(verde)
        c.rect(0, h - 16.6 * mm, w, 0.6 * mm, stroke=0, fill=1)
        if os.path.exists(LOGO):
            try:
                c.drawImage(LOGO, 14 * mm, h - 12 * mm, width=34 * mm, height=6 * mm, mask="auto",
                            preserveAspectRatio=True)
            except Exception:                           # noqa: BLE001 — sem o logo, segue o texto
                pass
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 9.5)
        c.drawRightString(w - 14 * mm, h - 9.4 * mm, _seguro("Atualização de chamados · %s" % m["cliente"]))
        c.setFillColor(mudo)
        c.setFont("Helvetica", 7.5)
        c.drawString(14 * mm, 9 * mm, _seguro(m["cabecalho"]))
        c.drawRightString(w - 14 * mm, 9 * mm, "Página %d" % doc.page)
        c.restoreState()

    h = []
    h += [Paragraph(_texto(m["titulo"]), e["titulo"]), Spacer(1, 1.5 * mm), Paragraph(_texto(m["subtitulo"]), e["sub"]),
          Spacer(1, 5 * mm), Paragraph(_texto(m["intro"]), base)]

    # resumo executivo: os números, cada um com a cor de quem precisa agir
    n = m["numeros"]
    caixas = [("andamento", n["andamento"], "em andamento", navy), ("Cliente", n["Cliente"], "aguardando o cliente",
                                                                     tom["Cliente"]),
              ("Fabricante", n["Fabricante"], "aguardando o fabricante", tom["Fabricante"]),
              ("Grid", n["Grid"], "em tratativa pela Grid Co.", tom["Grid"])]
    if n["Standby"]:
        caixas.append(("Standby", n["Standby"], "em standby", tom["Standby"]))
    linha_n = [Paragraph('<font color="#%s">%d</font>' % (cor.hexval()[2:], v), e["num"]) for _, v, _, cor in caixas]
    linha_l = [Paragraph(_texto(t), e["numl"]) for _, _, t, _ in caixas]
    t = Table([linha_n, linha_l], colWidths=[larg / len(caixas)] * len(caixas))
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), fundo), ("BOX", (0, 0), (-1, -1), 0.6, linha),
                           ("LINEBEFORE", (1, 0), (-1, -1), 0.6, linha), ("TOPPADDING", (0, 0), (-1, 0), 7),
                           ("BOTTOMPADDING", (0, 1), (-1, 1), 7), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    h += secao("Resumo executivo") + [t]

    # a visão por usina
    if m["usinas"]:
        cab = ["Usina (UFV)", "Supervisor", "Total", "Cliente", "Fabricante", "Grid Co."]
        linhas = [[Paragraph(_texto(x), e["cab"]) for x in cab]]
        for u in m["usinas"]:
            linhas.append([Paragraph(_texto(u["usina"]), e["cel"]), Paragraph(_texto(u["responsavel"] or "—"), e["cel"])] +
                          [Paragraph(str(u[k]) if u[k] else "—", e["celc"]) for k in ("total", "Cliente", "Fabricante",
                                                                                       "Grid")])
        tot = ["Total", ""] + [str(sum(u[k] for u in m["usinas"])) for k in ("total", "Cliente", "Fabricante", "Grid")]
        linhas.append([Paragraph("<b>%s</b>" % _texto(x), e["celc"] if i > 1 else e["cel"]) for i, x in enumerate(tot)])
        t = Table(linhas, colWidths=[62 * mm, 50 * mm, 17 * mm, 17 * mm, 19 * mm, 17 * mm], repeatRows=1)
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.8, navy), ("LINEBELOW", (0, 1), (-1, -2), 0.4, linha),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, fundo]),
                               ("LINEABOVE", (0, -1), (-1, -1), 0.8, navy), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        h += secao("Visão por usina") + [t]

    # os chamados, por quem precisa agir
    for i, s in enumerate(m["secoes"], 1):
        h += secao("%d. %s" % (i, s["titulo"]))
        cor = tom.get(s["geral"], tom[""]).hexval()[2:]
        for x in s["itens"]:
            partes = ['<font color="#%s"><b>%s</b></font> | %s' % (cor, _texto(x["ref"]), _texto(x["onde"]))]
            if x["status"]:
                partes.append("<i>%s</i>" % _texto(x["status"]))
            corpo = " · ".join(partes)
            if x["atualizacao"]:
                corpo += "<br/>%s" % _texto(x["atualizacao"])
            if x["dias"] is not None:
                corpo += '<br/><font color="#%s">Chamado aberto há %s.</font>' % (
                    mudo.hexval()[2:], _plural(x["dias"], "dia", "dias"))
            h.append(KeepTogether([Paragraph(corpo, e["item"], bulletText="•"), Spacer(1, 2.2 * mm)]))

    if m["proximos"]:
        h += secao("Próximos passos")
        h += [Paragraph(_texto(p), e["item"], bulletText="•") for p in m["proximos"]]
    h += [Spacer(1, 6 * mm), Paragraph(_texto("Em caso de dúvida, a equipe de Gestão de Chamados da Grid Co. está à "
                                              "disposição."), e["mudo"])]

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=24 * mm,
                            bottomMargin=16 * mm, title=_seguro(m["titulo"]), author="Grid Co. · O&M")
    doc.build(h, onFirstPage=pagina, onLaterPages=pagina)
    return buf.getvalue()

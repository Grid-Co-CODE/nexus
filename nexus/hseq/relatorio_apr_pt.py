"""O relatório de APR e PT em PDF, por mês e cliente (Segurança · HSEQ, 26/11/2026).

Levi, 26/11/2026: "Ali em segurança, a APR PT, na parte de histórico, tem que ter um botão de extrair relatório, e aí a
pessoa vai selecionar um mês e o cliente que ela quer extrair o relatório. E vai selecionar se ela quer só PT, se ela
quer só APR, se ela quer os dois"; "eu quero um formato em PDF [...] No estilo ali parecido com o dos extintores, naquele
padrão". O desenho, as cores e o cabeçalho da página são os do relatório dos extintores e do EPI (`relatorio._estilos`,
`relatorio.TOM`, a faixa navy com o filete verde).

- **As PTs** do mês: as que NASCERAM no mês (a `criada` do `visao.pts`), de todas as situações (De acordo, Não
  autorizada, aguardando, vencida), do cliente da usina no cadastro. Uma linha por PT × equipamento, como a tela.
- **As APRs** do mês: as do livro `apr_app_campo · APR` (o App publica desde a v298; a APR existe no livro desde
  09/10/2026) com o DIA no mês, ligadas à usina do cadastro pelo nome do local e o código do ativo (`b.lig.usina`, a
  mesma ligação da aba Sem APR ou PT). Uma linha por APR; a do dia junta as tarefas da OS no dia.
- A ordem é a do tempo (a mais antiga primeiro): é o registro do mês que o cliente pede.
"""
import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import relatorio as REL

TIPOS = {"ambos": "APR e PT", "pt": "Só PT", "apr": "Só APR"}
MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro")
SITUACAO = {"aguardando": ("Aguardando", "alerta"), "de_acordo": ("De acordo", "ok"),
            "negada": ("Não autorizada", "critico"), "vencida": ("Vencida", "neutro")}


def mes_por_extenso(m: date) -> str:
    return f"{MESES[m.month - 1]} de {m.year}"


def mes_do_texto(v) -> date | None:
    """"2026-11" -> date(2026, 11, 1); o que não é mês, None."""
    try:
        a, m = str(v or "").strip().split("-")
        return date(int(a), int(m), 1)
    except (ValueError, TypeError):
        return None


def _no_mes(d, mes: date) -> bool:
    return d is not None and d.year == mes.year and d.month == mes.month


def pts_do_mes(lista, mes: date, cliente: str) -> list:
    """As linhas de PT que nasceram no mês, do cliente, da mais antiga para a mais nova."""
    out = [p for p in lista if _no_mes(p.get("criada"), mes) and (not cliente or (p.get("cliente") or "") == cliente)]
    return sorted(out, key=lambda p: (p["criada"], str(p.get("numero") or ""), str(p.get("codigo") or "")))


def aprs_do_mes(aprs, mes: date, cliente: str, ligar) -> list:
    """As APRs do livro do App com o dia no mês, do cliente (`ligar(apr)` devolve a usina do cadastro: {usina, cliente}
    e o técnico), da mais antiga para a mais nova."""
    out = []
    for x in aprs:
        a = ligar(x)
        if a is None or not _no_mes(a.get("dia"), mes) or (cliente and (a.get("cliente") or "") != cliente):
            continue
        out.append(a)
    return sorted(out, key=lambda a: (a["dia"], str(a.get("os") or "")))


def _espera(m) -> str:
    if m is None:
        return "—"
    m = int(m)
    if m < 60:
        return f"{m} min"
    if m < 1440:
        return f"{m // 60} h {m % 60:02d}"
    return f"{m // 1440} d {(m % 1440) // 60} h"


def _numeros(nums, e):
    t = Table([[[Paragraph(REL._tom(str(n), cor, True), e["num"]), Paragraph(REL._t(rot), e["num_rot"])]
                for n, rot, cor in nums]], colWidths=[182 * mm / len(nums)] * len(nums))
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, REL.LINHA), ("INNERGRID", (0, 0), (-1, -1), 0.4, REL.LINHA),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return t


def _tabela(cab, larguras, linhas, e):
    t = Table([[Paragraph(c, e["cab"]) for c in cab]] + linhas, colWidths=[w * mm for w in larguras], repeatRows=1)
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, REL.LINHA), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BACKGROUND", (0, 0), (-1, 0), REL.FUNDO), ("TOPPADDING", (0, 0), (-1, -1), 3),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return t


def _linha_pt(p, e) -> list:
    rot, cor = SITUACAO.get(p.get("situacao"), (str(p.get("situacao") or "—"), "neutro"))
    sit = REL._tom(rot, cor, True)
    if p.get("decidida"):
        sit += f"<br/>{p['decidida']:%d/%m %H:%M}"
    if p.get("decidida_por"):
        sit += f"<br/>{REL._t(p['decidida_por'])}" + (f" ({REL._t(p['papel'])})" if p.get("papel") else "")
    if p.get("motivo"):
        sit += "<br/>" + REL._tom(f"Motivo: {p['motivo']}", "critico")
    equip = p.get("ativo") or p.get("codigo") or ""
    tarefa = p.get("tarefa") or ""
    usina = f"<b>{REL._t(p.get('usina') or '—')}</b>" + (f"<br/>{REL._t(equip)}" if equip else "")
    if tarefa and not tarefa.startswith("APR do dia"):
        usina += f"<br/>{REL._t(tarefa[:90])}"
    nao = REL._tom(str(p["respostas_nao"]), "critico", True) if p.get("respostas_nao") else REL._tom("—", "neutro")
    # o mês está no título: a data curta cabe numa linha e a hora embaixo
    return [Paragraph(f"{p['criada']:%d/%m}<br/>{p['criada']:%H:%M}", e["base"]),
            Paragraph(f"<b>{REL._t(p.get('numero') or '')}</b><br/>OS {REL._t(p.get('os') or '—')}", e["base"]),
            Paragraph(usina, e["base"]), Paragraph(REL._t(p.get("solicitante") or "—"), e["base"]),
            Paragraph(nao, e["base"]), Paragraph(sit, e["base"]), Paragraph(REL._t(_espera(p.get("espera_min"))), e["base"])]


def _linha_apr(a, e) -> list:
    if a.get("pt"):
        pt = REL._t(a["pt"])
    elif a.get("precisa_pt") is True:
        pt = REL._tom("pedia PT e ficou sem", "critico", True)
    elif a.get("precisa_pt") is False:
        pt = REL._t("não pedia")
    else:
        pt = REL._tom("não medido", "info")
    t = (a.get("tipo") or "").lower()
    tipo = "APR do dia" if "dia" in t else ("Por tarefa" if "tarefa" in t else (a.get("tipo") or "—"))
    tarefa = f"<b>{REL._t(tipo)}</b>" + (f"<br/>{REL._t(a['tarefa'][:90])}" if a.get("tarefa") else "")
    ativ = "<br/>".join(REL._t(x) for x in a.get("atividades") or []) or REL._t("nenhuma marcada")
    return [Paragraph(f"{a['dia']:%d/%m}", e["base"]), Paragraph(REL._t(a.get("os") or "—"), e["base"]),
            Paragraph(f"<b>{REL._t(a.get('usina') or '—')}</b>", e["base"]), Paragraph(tarefa, e["base"]),
            Paragraph(REL._t(a.get("tecnico") or "—"), e["base"]), Paragraph(ativ, e["mudo"]), Paragraph(pt, e["base"])]


def gerar_pdf(pts: list, aprs: list, *, tipo: str, mes: date, cliente: str, hoje: date, gerado_em: str,
              logo: str | None = None) -> bytes:
    """O PDF do mês e do cliente: os números e, conforme o `tipo` (ambos, pt, apr), a tabela das PTs e a das APRs."""
    e = REL._estilos()
    buf = io.BytesIO()
    titulo = {"pt": "Relatório de PT", "apr": "Relatório de APR"}.get(tipo, "Relatório de APR e PT")

    def pagina(c, doc):
        c.saveState()
        larg, alt = A4
        c.setFillColor(REL.NAVY)
        c.rect(0, alt - 16 * mm, larg, 16 * mm, stroke=0, fill=1)
        c.setFillColor(REL.VERDE)
        c.rect(0, alt - 16.6 * mm, larg, 0.6 * mm, stroke=0, fill=1)
        if logo:
            try:
                c.drawImage(logo, 14 * mm, alt - 12 * mm, width=34 * mm, height=6 * mm, mask="auto",
                            preserveAspectRatio=True)
            except Exception:       # noqa: BLE001 — sem o logo, segue o texto
                pass
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 10)
        c.drawRightString(larg - 14 * mm, alt - 9.4 * mm, f"{titulo} · Segurança · HSEQ")
        c.setFillColor(REL.MUDO)
        c.setFont("Helvetica", 7.5)
        c.drawString(14 * mm, 9 * mm, f"Nexus · Grid Co. · gerado em {gerado_em}")
        c.drawRightString(larg - 14 * mm, 9 * mm, f"Página {doc.page}")
        c.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=22 * mm,
                            bottomMargin=16 * mm, title=f"{titulo} · {cliente or 'todos os clientes'} · "
                            f"{mes_por_extenso(mes)}", author="Nexus · Grid Co.")
    story = [Paragraph(REL._t(titulo), e["titulo"]),
             Paragraph(REL._t(f"{cliente or 'Todos os clientes'} · {mes_por_extenso(mes)}"), e["sub"]),
             Paragraph(REL._t(f"Filtros: mês {mes:%m/%Y}, cliente {cliente or 'todos'}, {TIPOS.get(tipo, tipo).lower()}"
                              f" · situação no dia {hoje:%d/%m/%Y}"), e["mudo"]),
             Spacer(1, 4 * mm)]
    if tipo in ("ambos", "pt"):
        n = {k: sum(1 for p in pts if p.get("situacao") == k) for k in SITUACAO}
        story += [Paragraph("Permissões de trabalho (PT)", e["sub"]), Spacer(1, 2 * mm),
                  _numeros([(len(pts), "PTs no mês", "neutro"), (n["de_acordo"], "De acordo", "ok"),
                            (n["negada"], "não autorizadas", "critico"),
                            (n["aguardando"] + n["vencida"], "aguardando ou vencidas", "alerta")], e), Spacer(1, 3 * mm)]
        if pts:
            story.append(_tabela(("DATA", "PT · OS", "USINA E EQUIPAMENTO", "TÉCNICO", "NÃO", "DECISÃO",
                                  "ESPERA"), (13, 38, 40, 27, 14, 35, 15), [_linha_pt(p, e) for p in pts], e))
        else:
            story.append(Paragraph("Nenhuma PT neste mês para este cliente.", e["mudo"]))
        story.append(Spacer(1, 6 * mm))
    if tipo in ("ambos", "apr"):
        pedia = [a for a in aprs if a.get("precisa_pt") is True]
        sem = [a for a in pedia if not a.get("pt")]
        story += [Paragraph("Análises Preliminares de Risco (APR)", e["sub"]), Spacer(1, 2 * mm),
                  _numeros([(len(aprs), "APRs no mês", "neutro"), (len(pedia), "pediam PT", "info"),
                            (len(pedia) - len(sem), "com a PT", "ok"), (len(sem), "pediam PT e ficaram sem", "critico")],
                           e), Spacer(1, 3 * mm)]
        if aprs:
            story.append(_tabela(("DIA", "OS", "USINA", "TIPO E TAREFA", "TÉCNICO", "ATIVIDADES CRÍTICAS", "PT"),
                                 (12, 14, 31, 33, 26, 32, 34), [_linha_apr(a, e) for a in aprs], e))
        else:
            story.append(Paragraph("Nenhuma APR neste mês para este cliente.", e["mudo"]))
        story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(REL._t(
        "Como ler. A PT entra pelo dia em que o técnico a pediu no App; a decisão é o De acordo ou o Não autorizo de quem "
        "pode assinar (o Responsável UFV, o supervisor, o gestor de contrato, o COS no plantão), e a espera vai do pedido "
        "à decisão. A APR entra pelo dia em que foi feita no App (a do dia junta as tarefas da OS no dia); a coluna PT "
        "diz o número da PT ligada a ela, ou se as atividades críticas pediam PT e ela não foi feita. A usina e o "
        "cliente são os do cadastro do Nexus."), e["mudo"]))
    doc.build(story, onFirstPage=pagina, onLaterPages=pagina)
    return buf.getvalue()

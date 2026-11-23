"""O relatório do EPI (as luvas isolantes) em PDF e em Excel (Segurança · HSEQ).

A Segurança, 23/11/2026: "na aba EPI e EPC, crie a opção de baixar relatório por cliente, no mesmo modelo e opções dos
Extintores". O mesmo modelo: os três pontos da linha da tabela, com Exportar PDF e Exportar planilha (`relatorio.py` e
`planilha.py`, dos extintores). A tabela do EPI é uma linha por usina, sem o agrupamento por cliente; por isso os três
pontos da usina dão o relatório do CLIENTE dela e o da própria usina (a escolha da Segurança na mesma conversa).

- O recorte é o da tela (`_do_relatorio_epi` na torre): os filtros (região do Brasil, cliente, responsável UFV, busca)
  e o da faixa (`f`), com o cliente da linha, ou a usina dela. As mesmas contas (`epi.luvas`): sem luvas, sem
  verificação, com luvas.
- PDF: o resumo com os quatro números e uma tabela (situação, usina com o responsável, a resposta da última ronda com o
  "desde", a última verificação com quem fez e a OS, as últimas respostas). Sem fotos: as das luvas são anexos da OS
  da ronda no Fracttal, que o Nexus só lê com o login de quem olha; o relatório leva o número da OS para achá-las.
- Excel: aba "Usinas" (uma linha por usina, na ordem da tela) e aba "Respostas" (uma linha por resposta das luvas que a
  linha da tela mostra, as 8 últimas de cada usina). Sem cor nem fórmula, a data como data.
O desenho, as cores e o cabeçalho da página são os do relatório dos extintores (`relatorio._estilos`, `relatorio.TOM`).
"""
import io
from datetime import date

from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import epi as EPI
from . import planilha as PLA
from . import relatorio as REL

TITULO = "Relatório de EPI · luvas isolantes"
SEM_RESPONSAVEL = "sem responsável"


def _responsavel(x) -> str:
    r = EPI.responsavel(x)
    return "" if r == EPI.visao.SEM_RESPONSAVEL else r


def _resposta(v) -> str:
    return "Não" if v["luvas"] is False else "Sim"


def _resumo(lista, e):
    c = EPI.contar(lista)
    nums = [(c["usinas"], "usinas", "neutro"), (c["sem_luvas"], "sem luvas", "critico"),
            (c["sem_verificacao"], f"sem verificação há {EPI.DIAS_SEM_VERIFICAR} d ou mais", "info"),
            (c["com_luvas"], "com luvas", "ok")]
    t = Table([[[Paragraph(REL._tom(str(n), cor, True), e["num"]), Paragraph(REL._t(rot), e["num_rot"])]
                for n, rot, cor in nums]], colWidths=[182 * mm / 4] * 4)
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, REL.LINHA), ("INNERGRID", (0, 0), (-1, -1), 0.4, REL.LINHA),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return t


def _linha_pdf(x, hoje, e) -> list:
    rot, cor = EPI.SITUACOES[x["situacao"]]
    u = x["ultima"]
    onde = f"<b>{REL._t(x['usina'])}</b>"
    det = " · ".join(REL._t(v) for v in (x.get("cliente"), _responsavel(x) or SEM_RESPONSAVEL) if v)
    if u:
        luvas = REL._tom(_resposta(u), "critico" if u["luvas"] is False else "ok", True)
        if x["desde"]:
            luvas += "<br/>" + REL._tom(f"desde {x['desde']:%d/%m/%Y} · há {(hoje - x['desde']).days} d", "critico")
        ult = f"{u['dia']:%d/%m/%Y} · " + ("hoje" if x["dias"] == 0 else f"há {x['dias']} d")
        if u.get("tecnico"):
            ult += f"<br/>{REL._t(u['tecnico'])}"
        if u.get("os"):
            ult += f"<br/>OS {REL._t(u['os'])}"
        hist = " ".join(f"{v['dia']:%d/%m} {_resposta(v)}" for v in x["historico"])
        hist = REL._t(hist) + "<br/>" + (REL._tom(f"{x['nao']} Não em {x['verificacoes']}", "critico") if x["nao"]
                                         else REL._t(f"{x['verificacoes']} resposta{'s' if x['verificacoes'] != 1 else ''}"))
    else:
        luvas, ult, hist = REL._tom("nunca verificada", "info"), "—", "—"
    return [Paragraph(REL._tom(rot, cor, True), e["base"]), Paragraph(f"{onde}<br/>{det}", e["base"]),
            Paragraph(luvas, e["base"]), Paragraph(ult, e["base"]), Paragraph(hist, e["mudo"])]


def gerar_pdf(lista, *, filtros_tela: list[str], hoje: date, gerado_em: str, logo: str | None = None) -> bytes:
    """O PDF: o resumo e a tabela das usinas, na ordem da tela (o mais grave primeiro)."""
    e = REL._estilos()
    buf = io.BytesIO()

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
        c.drawRightString(larg - 14 * mm, alt - 9.4 * mm, "Relatório de EPI · Segurança · HSEQ")
        c.setFillColor(REL.MUDO)
        c.setFont("Helvetica", 7.5)
        c.drawString(14 * mm, 9 * mm, f"Nexus · Grid Co. · gerado em {gerado_em}")
        c.drawRightString(larg - 14 * mm, 9 * mm, f"Página {doc.page}")
        c.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=22 * mm,
                            bottomMargin=16 * mm, title=TITULO, author="Nexus · Grid Co.")
    story = [Paragraph(TITULO, e["titulo"]),
             Paragraph(REL._t(f'A pergunta da ronda diária: "{EPI.PERGUNTA}" · situação no dia {hoje:%d/%m/%Y}'),
                       e["sub"]),
             Paragraph(REL._t("Filtros: " + (", ".join(filtros_tela) if filtros_tela else "nenhum (todas as usinas)")),
                       e["mudo"]),
             Spacer(1, 4 * mm), _resumo(lista, e), Spacer(1, 5 * mm)]
    if lista:
        linhas = [[Paragraph(c, e["cab"]) for c in ("SITUAÇÃO", "USINA", "LUVAS ISOLANTES", "ÚLTIMA VERIFICAÇÃO",
                                                     "ÚLTIMAS RESPOSTAS")]]
        linhas += [_linha_pdf(x, hoje, e) for x in lista]
        t = Table(linhas, colWidths=[24 * mm, 46 * mm, 32 * mm, 36 * mm, 44 * mm], repeatRows=1)
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, REL.LINHA), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("BACKGROUND", (0, 0), (-1, 0), REL.FUNDO), ("TOPPADDING", (0, 0), (-1, -1), 4),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        story.append(t)
    else:
        story.append(Paragraph("Nenhuma usina com esses filtros.", e["sub"]))
    story += [Spacer(1, 5 * mm), Paragraph(REL._t(
        "Como cada usina entra. Sem luvas: a última ronda respondeu Não; o \"desde\" é o primeiro Não da sequência até "
        f"ela. Sem verificação: nenhuma resposta há {EPI.DIAS_SEM_VERIFICAR} dias ou mais, ou nunca. Com luvas: a "
        "última ronda respondeu Sim. As fotos das luvas são anexos da OS da ronda no Fracttal (em Infraestrutura)."),
        e["mudo"])]
    doc.build(story, onFirstPage=pagina, onLaterPages=pagina)
    return buf.getvalue()


# (cabeçalho, largura, valor) de cada coluna da aba Usinas
COLUNAS = (
    ("Cliente", 18, lambda x: x.get("cliente") or ""),
    ("Usina", 28, lambda x: x["usina"]),
    ("Responsável UFV", 22, _responsavel),
    ("Equipe", 16, lambda x: x.get("equipe") or ""),
    ("Cidade", 18, lambda x: x.get("cidade") or ""),
    ("UF", 6, lambda x: x.get("uf") or ""),
    ("Situação", 16, lambda x: EPI.SITUACOES[x["situacao"]][0]),
    ("Luvas na última ronda", 12, lambda x: _resposta(x["ultima"]) if x["ultima"] else "nunca verificada"),
    ("Sem luvas desde", 12, lambda x: x.get("desde")),
    ("Última verificação", 12, lambda x: (x.get("ultima") or {}).get("dia")),
    ("Há quantos dias", 10, lambda x: x.get("dias")),
    ("Verificado por", 22, lambda x: (x.get("ultima") or {}).get("tecnico") or ""),
    ("OS da ronda", 10, lambda x: (x.get("ultima") or {}).get("os") or ""),
    ("Respostas na janela", 10, lambda x: x.get("verificacoes")),
    ("Respostas Não", 10, lambda x: x.get("nao")),
)
COLUNAS_RESPOSTAS = (
    ("Cliente", 18, lambda x, v: x.get("cliente") or ""),
    ("Usina", 28, lambda x, v: x["usina"]),
    ("Dia da ronda", 12, lambda x, v: v["dia"]),
    ("Luvas disponíveis", 10, lambda x, v: _resposta(v)),
    ("Verificado por", 22, lambda x, v: v.get("tecnico") or ""),
    ("OS da ronda", 10, lambda x, v: v.get("os") or ""),
)


def gerar_xlsx(lista, *, filtros_tela: list[str], hoje: date, gerado_em: str) -> bytes:
    """O .xlsx: a aba Usinas (uma linha por usina, na ordem da tela) e a aba Respostas (as últimas de cada usina)."""
    topo = [f"Gerado em {gerado_em} · situação no dia {hoje:%d/%m/%Y}",
            "Filtros: " + (" · ".join(filtros_tela) if filtros_tela else "nenhum (todas as usinas)")]
    wb = Workbook()
    ws = wb.active
    ws.title = "Usinas"
    c = EPI.contar(lista)
    PLA._aba(ws, TITULO, topo + [f"{c['usinas']} usina{'s' if c['usinas'] != 1 else ''}: {c['sem_luvas']} sem luvas, "
                                 f"{c['sem_verificacao']} sem verificação, {c['com_luvas']} com luvas"],
             COLUNAS, [[f(x) for _r, _l, f in COLUNAS] for x in lista])
    resp = wb.create_sheet("Respostas")
    PLA._aba(resp, "As últimas respostas das luvas", topo + [
        f'A pergunta da ronda diária: "{EPI.PERGUNTA}"; as {EPI.HISTORICO} últimas de cada usina, da mais nova para a '
        "mais velha."], COLUNAS_RESPOSTAS,
        [[f(x, v) for _r, _l, f in COLUNAS_RESPOSTAS] for x in lista for v in x["historico"]])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

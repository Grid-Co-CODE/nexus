"""O relatório dos extintores em PDF (Segurança · HSEQ).

Levi, 09/10/2026: "Gostaria também que gerássemos um relatório em PDF com esse agrupamento por usina e dia", com as
observações da TST: "RELATÓRIO: TODOS OS EXTINTORES, CRÍTICOS, ATENÇÃO, OK · DETALHES DO EXTINTOR · PARA GERAR O
RELATÓRIO O PADRÃO SERÁ AS FOTOS AO LADO DE CADA EXTINTOR MAS SERÁ POSSÍVEL PUXAR RELATÓRIO SÓ DOS CRÍTICOS".

- O mesmo agrupamento da tabela da tela (`extintores.por_usina_dia`): usina × dia da última conferência, o mais grave
  primeiro; os mesmos filtros (região do Brasil, região de campo, gestor, busca) e as mesmas contas.
- O filtro do relatório é o STATUS DA TST (`FILTROS`): todos, críticos, atenção ou OK (o OK leva o "OK sem validade",
  que também é checklist limpo). Extintor nunca conferido não tem status: só entra em "todos".
- Com fotos (o padrão): cada extintor num quadro, a foto ao lado dos detalhes. Sem fotos: uma tabela por usina e dia.
- A FOTO vem de `foto(codigo)`: a da última conferência que o App enviar ao Nexus. Em 09/10/2026 nenhuma chega ainda (o
  App guarda as fotos dele, e o Nexus não lê o Azure): o quadro sai vazio, dizendo isso, e se preenche quando o envio
  existir. Foto reduzida a 600 px (JPEG 75): com as 773 fotos inteiras o arquivo passaria de 70 MB.

Fonte Helvetica (padrão do PDF, cobre o português); o "CO₂" das classes vira "CO2" (o ₂ não existe nela).
"""
import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (CondPageBreak, Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)
from xml.sax.saxutils import escape

from . import extintores as EXT

# o filtro do relatório (as opções da TST): rótulo e os status que entram (None = todos)
FILTROS = {"todos": ("Todos os extintores", None), "criticos": ("Só os críticos", ("CRITICO",)),
           "atencao": ("Só os de atenção", ("ATENCAO",)), "ok": ("Só os OK", ("OK", "OK_SEM_VALIDADE"))}
FOTO_PX, FOTO_QUALIDADE = 600, 75
NAVY, NAVY_2, VERDE = colors.HexColor("#090d18"), colors.HexColor("#161d30"), colors.HexColor("#b5d334")
TOM = {"critico": colors.HexColor("#c8102e"), "alerta": colors.HexColor("#b26a00"), "ok": colors.HexColor("#1f7a3f"),
       "info": colors.HexColor("#1f5fa8"), "neutro": colors.HexColor("#5b6475")}
LINHA, FUNDO, MUDO, TINTA = (colors.HexColor("#d8dce4"), colors.HexColor("#f3f5f8"), colors.HexColor("#5b6475"),
                             colors.HexColor("#111827"))
_TROCA = {"\u2082": "2", "\u2009": " ", "\u202f": " "}     # o 2 subscrito e os espaços finos que a Helvetica não tem
# a situação no cabeçalho da usina, no singular e no plural ("18 atrasados", "1 em dia")
NO_GRUPO = {"atrasado": ("atrasado", "atrasados"), "perto": ("perto de vencer", "perto de vencer"),
            "sem_validade": ("sem validade", "sem validade"), "em_dia": ("em dia", "em dia")}


def filtrar(lista, filtro: str) -> list:
    """Os extintores que entram no relatório pelo status da TST."""
    quais = FILTROS.get(filtro, FILTROS["todos"])[1]
    return list(lista) if quais is None else [x for x in lista if x.get("status") in quais]


def _t(v) -> str:
    """Texto seguro para o Paragraph do reportlab: escapa o XML e troca o que a Helvetica não tem."""
    s = "" if v is None else str(v)
    for a, b in _TROCA.items():
        s = s.replace(a, b)
    return escape(s)


def _cor(c) -> str:
    return TOM[c].hexval()[2:]


def _tom(texto, c, negrito=False) -> str:
    t = f'<font color="#{_cor(c)}">{texto}</font>'
    return f"<b>{t}</b>" if negrito else t


def _estilos():
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=8.6, leading=11, textColor=TINTA)
    return {"base": base,
            "mudo": ParagraphStyle("mudo", parent=base, textColor=MUDO, fontSize=7.8, leading=10),
            "titulo": ParagraphStyle("titulo", parent=base, fontName="Helvetica-Bold", fontSize=17, leading=21),
            "sub": ParagraphStyle("sub", parent=base, fontSize=9.4, leading=13, textColor=MUDO),
            "grupo": ParagraphStyle("grupo", parent=base, fontName="Helvetica-Bold", fontSize=10.5, leading=13),
            "cab": ParagraphStyle("cab", parent=base, fontName="Helvetica-Bold", fontSize=7.4, leading=9,
                                  textColor=MUDO, alignment=TA_CENTER),
            "num": ParagraphStyle("num", parent=base, fontName="Helvetica-Bold", fontSize=14, leading=16,
                                  alignment=TA_CENTER),
            "num_rot": ParagraphStyle("num_rot", parent=base, fontSize=7.2, leading=9, textColor=MUDO,
                                      alignment=TA_CENTER),
            "foto": ParagraphStyle("foto", parent=base, fontSize=7.4, leading=9.5, textColor=MUDO,
                                   alignment=TA_CENTER)}


def _foto_reduzida(dados: bytes):
    """A foto em JPEG de até FOTO_PX no lado maior; None se não for imagem."""
    try:
        from PIL import Image as PILImage
        im = PILImage.open(io.BytesIO(dados))
        im = im.convert("RGB")
        im.thumbnail((FOTO_PX, FOTO_PX))
        out = io.BytesIO()
        im.save(out, "JPEG", quality=FOTO_QUALIDADE, optimize=True)
        return out.getvalue(), im.size
    except Exception:       # noqa: BLE001 — foto ilegível sai como "sem foto"
        return None


def _quando(fim, hoje) -> tuple[str, str]:
    """("venceu há 18 meses", "critico") / ("vence em 22 d", "alerta") / ("", "") para a validade distante."""
    if not fim:
        return "", ""
    n = (fim - hoje).days
    if n < 0:
        return f"venceu há {EXT.tempo(n)}", "critico"
    if n == 0:
        return "vence hoje", "alerta"
    return (f"vence em {EXT.tempo(n)}", "alerta") if n <= EXT.ALERTA_DIAS else ("", "")


def _etiqueta(v, fim, hoje) -> str:
    frase, c = _quando(fim, hoje)
    return _t(v) + (f" · {_tom(frase, c)}" if frase else "")


def _status(x) -> str:
    st = EXT.STATUS_TST.get(x.get("status"))
    if not st:
        return _tom("sem conferência", "neutro")
    return _tom(st[0], st[1], True) + (f" · {_t(x['motivo'])}" if x.get("motivo") else "")


def _conferencia(x) -> str:
    if not x.get("conferencia"):
        return _tom("nunca conferido", "info")
    partes = [x["conferencia"].strftime("%d/%m/%Y"), f"há {EXT.tempo(x['dias_conferencia'])}"]
    partes += [p for p in (x.get("origem_conferencia"), x.get("conferido_por")) if p]
    return _tom(_t(" · ".join(partes)), "info") if x.get("sem_atualizacao") else _t(" · ".join(partes))


def _detalhes(x, hoje, e) -> list:
    """Os detalhes de UM extintor (a observação da TST: "DETALHES DO EXTINTOR")."""
    sit = EXT.SITUACOES[x["situacao"]]
    local = _t(x.get("local") or "—") + (f" ({_t(x['ativo'])})" if x.get("ativo") else "") + (
        f" · {_t(x['posicao'].lower())}" if x.get("posicao") else "")
    classe = _t(x.get("classe") or "sem classe") + (f" · {_t(x['peso'])} kg" if x.get("peso") else "")
    itens = ", ".join(x.get("itens_nao") or []) or "nenhum"
    carga = {"CARREGADO": "carregado", "SEM_CARGA": "sem carga", "SOBRECARGA": "sobrecarga"}.get(
        str(x.get("carga") or "").upper(), "") if x.get("carga") else ""
    linhas = [f"<b>{_t(x['ext'])}</b> · {local} · {_tom(sit[0], sit[1], True)}",
              f"{classe} · código {_t(x['codigo'])}",
              f"<b>Recarga:</b> {_etiqueta(x['val2'], x.get('fim2'), hoje)} &nbsp; "
              f"<b>Hidrostático:</b> {_etiqueta(x['val3'], x.get('fim3'), hoje)}",
              (f"<b>Carga:</b> {_t(carga)} &nbsp; " if carga else "") + f"<b>Itens com NÃO:</b> {_t(itens)}",
              f"<b>Status da TST:</b> {_status(x)}",
              f"<b>Conferência:</b> {_conferencia(x)}"]
    return [Paragraph(li, e["base"]) for li in linhas]


def _quadro_foto(x, foto, e):
    dados = foto(x["codigo"]) if foto else None
    red = _foto_reduzida(dados) if dados else None
    if not red:
        return Paragraph("Sem foto no Nexus<br/>(as fotos chegam do App de Campo)", e["foto"])
    jpeg, (w, h) = red
    lado = 40 * mm
    esc = min(lado / w, lado / h)
    return Image(io.BytesIO(jpeg), width=w * esc, height=h * esc)


def _cab_grupo(g, hoje, e):
    sit = EXT.SITUACOES[g["situacao"]]
    st = EXT.STATUS_TST.get(g["status"])
    regiao = g.get("regiao_campo") if g.get("regiao_campo") and g["regiao_campo"] != "Sem região de campo" else (
        "sem região de campo")
    sup = g.get("supervisor_campo")
    regiao += f" · Supervisor de Campo: {sup}" if sup else ""
    cont = " · ".join(f"{g[k]} {um if g[k] == 1 else varios}" for k, (um, varios) in NO_GRUPO.items() if g[k])
    rec = (_etiqueta(g["recarga"], g["recarga_fim"], hoje) + f" ({_t(g['recarga_ext'])})") if g["recarga_fim"] else (
        "sem data")
    conf = _conferencia(g)
    linha1 = (f"<b>{_t(g['usina'])}</b> &nbsp; {_tom(sit[0], sit[1], True)} &nbsp; "
              f"<font size=8 color='#{_cor('neutro')}'>{_t(regiao)}</font>")
    linha2 = (f"<b>{g['qtd']} extintor{'es' if g['qtd'] != 1 else ''}</b> ({_t(cont)}) &nbsp; "
              f"<b>Recarga mais próxima:</b> {rec} &nbsp; <b>Última conferência:</b> {conf} &nbsp; "
              f"<b>Status da TST:</b> " + (_tom(st[0], st[1], True) if st else _tom("sem conferência", "neutro")))
    t = Table([[Paragraph(linha1, e["grupo"])], [Paragraph(linha2, e["base"])]], colWidths=[182 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), FUNDO), ("LINEBEFORE", (0, 0), (0, -1), 3,
                                                                       TOM[sit[1]]),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 4),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return t


def _bloco_com_foto(x, hoje, foto, e):
    t = Table([[_quadro_foto(x, foto, e), _detalhes(x, hoje, e)]], colWidths=[46 * mm, 136 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (0, 0), "CENTER"),
                           ("BOX", (0, 0), (-1, -1), 0.6, LINHA), ("LINEAFTER", (0, 0), (0, 0), 0.6, LINHA),
                           ("BACKGROUND", (0, 0), (0, 0), FUNDO),
                           ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return t


def _tabela_sem_foto(g, hoje, e):
    cab = [Paragraph(c, e["cab"]) for c in ("EXTINTOR", "LOCAL", "CLASSE · PESO", "RECARGA", "HIDROSTÁTICO",
                                           "STATUS DA TST")]
    linhas = [cab]
    for x in g["extintores"]:
        sit = EXT.SITUACOES[x["situacao"]]
        st = EXT.STATUS_TST.get(x.get("status"))
        linhas.append([Paragraph(f"<b>{_t(x['ext'])}</b> · {_tom(sit[0], sit[1])}", e["base"]),
                       Paragraph(_t(x.get("local") or "—"), e["base"]),
                       Paragraph(_t(x.get("classe") or "sem classe") + (f" · {_t(x['peso'])} kg" if x.get("peso")
                                                                        else ""), e["base"]),
                       Paragraph(_etiqueta(x["val2"], x.get("fim2"), hoje), e["base"]),
                       Paragraph(_etiqueta(x["val3"], x.get("fim3"), hoje), e["base"]),
                       Paragraph((_tom(st[0], st[1], True) + (f"<br/>{_t(x['motivo_checklist'])}"
                                                               if x.get("motivo_checklist") else ""))
                                 if st else _tom("sem conferência", "neutro"), e["base"])])
    # a recarga ganha a largura para "03/2025 · venceu há 18 meses" caber numa linha (o Levi não quer o dado quebrado
    # quando há espaço); o extintor e a situação, lado a lado
    t = Table(linhas, colWidths=[30 * mm, 26 * mm, 26 * mm, 45 * mm, 26 * mm, 29 * mm], repeatRows=1)
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, LINHA), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return t


def _resumo(lista, e):
    """Os números do relatório: por status da TST e por situação."""
    st = {k: sum(1 for x in lista if (x.get("status") or "") == k) for k in EXT.ORDEM_STATUS}
    sit = {k: sum(1 for x in lista if x["situacao"] == k) for k in EXT.SITUACOES}
    sem_at = sum(1 for x in lista if x["sem_atualizacao"])
    nums = [(len(lista), "extintores", "neutro"), (len({x["usina"] for x in lista}), "usinas", "neutro"),
            (st["CRITICO"], "críticos", "critico"), (st["ATENCAO"], "atenção", "alerta"),
            (st["OK"] + st["OK_SEM_VALIDADE"], "OK", "ok"), (st[""], "sem conferência", "neutro")]
    nums2 = [(sit["atrasado"], "atrasados", "critico"), (sit["perto"], "perto de vencer", "alerta"),
             (sit["sem_validade"], "sem validade", "neutro"), (sit["em_dia"], "em dia", "ok"),
             (sem_at, "sem atualização há +30 d", "info"), ("", "", "neutro")]

    def celula(n, rot, c):
        return [Paragraph(_tom(str(n), c, True) if n != "" else "", e["num"]), Paragraph(_t(rot), e["num_rot"])]
    t = Table([[celula(*n) for n in nums], [celula(*n) for n in nums2]], colWidths=[182 * mm / 6] * 6)
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, LINHA), ("INNERGRID", (0, 0), (-1, -1), 0.4, LINHA),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return t


def gerar(lista, *, filtro: str, com_fotos: bool, filtros_tela: list[str], hoje: date, gerado_em: str,
          logo: str | None = None, foto=None) -> bytes:
    """O PDF: o resumo, depois cada usina × dia com os extintores dela. `lista` = os extintores já com os filtros da
    tela; `filtro` = o status da TST (FILTROS); `foto(codigo)` -> bytes da foto ou None."""
    e = _estilos()
    lista = filtrar(lista, filtro)
    grupos = EXT.por_usina_dia(lista)
    buf = io.BytesIO()

    def pagina(c, doc):
        c.saveState()
        larg, alt = A4
        c.setFillColor(NAVY)
        c.rect(0, alt - 16 * mm, larg, 16 * mm, stroke=0, fill=1)
        c.setFillColor(VERDE)
        c.rect(0, alt - 16.6 * mm, larg, 0.6 * mm, stroke=0, fill=1)
        if logo:
            try:
                c.drawImage(logo, 14 * mm, alt - 12 * mm, width=34 * mm, height=6 * mm, mask="auto",
                            preserveAspectRatio=True)
            except Exception:       # noqa: BLE001 — sem o logo, segue o texto
                pass
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 10)
        c.drawRightString(larg - 14 * mm, alt - 9.4 * mm, "Relatório de extintores · Segurança · HSEQ")
        c.setFillColor(MUDO)
        c.setFont("Helvetica", 7.5)
        c.drawString(14 * mm, 9 * mm, f"Nexus · Grid Co. · gerado em {gerado_em}")
        c.drawRightString(larg - 14 * mm, 9 * mm, f"Página {doc.page}")
        c.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=22 * mm,
                            bottomMargin=16 * mm, title="Relatório de extintores", author="Nexus · Grid Co.")
    rotulo = FILTROS.get(filtro, FILTROS["todos"])[0]
    story = [Paragraph("Relatório de extintores", e["titulo"]),
             Paragraph(_t(f"{rotulo} · {'com as fotos ao lado de cada extintor' if com_fotos else 'sem fotos'} · "
                          f"agrupado por usina e dia da última conferência"), e["sub"]),
             Paragraph(_t("Filtros: " + (", ".join(filtros_tela) if filtros_tela else "nenhum (todas as usinas)")),
                       e["mudo"]),
             Spacer(1, 4 * mm), _resumo(lista, e), Spacer(1, 5 * mm)]
    if not grupos:
        story.append(Paragraph("Nenhum extintor com esses filtros.", e["sub"]))
    for g in grupos:
        if com_fotos:
            blocos = [_bloco_com_foto(x, hoje, foto, e) for x in g["extintores"]]
            story.append(KeepTogether([_cab_grupo(g, hoje, e), Spacer(1, 2 * mm), blocos[0]]))
            for b in blocos[1:]:
                story += [Spacer(1, 1.6 * mm), b]
        else:
            # a tabela da usina corre pelas páginas (o cabeçalho das colunas se repete); só não começa no pé da página.
            # Com KeepTogether, a 1ª usina (19 extintores) não cabia embaixo do resumo e a página 1 saía em branco
            story += [CondPageBreak(45 * mm), _cab_grupo(g, hoje, e), Spacer(1, 1.5 * mm), _tabela_sem_foto(g, hoje, e)]
        story.append(Spacer(1, 5 * mm))
    story.append(Paragraph(_t(
        "Como cada extintor entra. Atrasado: a recarga (2º nível) ou o teste hidrostático (3º nível) venceu; a data "
        "da etiqueta vale até o último dia do mês, e só o ano vale até 31/12. Perto de vencer: uma das duas vence nos "
        f"próximos {EXT.ALERTA_DIAS} dias. Sem validade: a recarga sem data na etiqueta. Status da TST: a regra da "
        "planilha de controle da TST, a mesma do App (crítico, atenção, OK, OK sem validade), que olha também a carga "
        "e os 9 itens do checklist."), e["mudo"]))
    doc.build(story, onFirstPage=pagina, onLaterPages=pagina)
    return buf.getvalue()

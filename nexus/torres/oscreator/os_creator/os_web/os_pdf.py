"""O PDF da OS, com o que o Fracttal junta para imprimir o dele.

Levi, 19/10/2026, em Nexus > Chamados > Garantias: "Gostaria de incluir a opção de baixar o mesmo PDF que o fractall
gera" ("pelo o que entendo ele baixa várias imagens e incluir no PDF") e "inclua a opção de baixar na cadeia de
chamado, uma seta de download!".

Não há um PDF pronto no Fracttal para buscar: a web dele monta o PDF NO NAVEGADOR, com estes pedidos (o curl do Levi):
o cabeçalho (`tasks.work_order_details_new`), as tarefas (`tasks.work_orders_tasks_new_list`), as subtarefas
(`tasks.work_orders_task_form_items_list`), as fotos das subtarefas (`tasks.work_orders_tasks_images_all_list`), os
arquivos de cada tarefa (`tasks.work_orders_tasks_files_list`), os recursos (`tasks.work_orders_resources_all_list`) e
cada foto baixada do S3. Aqui o servidor junta o mesmo com o que o card da OS já lê (`api.get_os_detalhes`, os anexos
do card e `api.get_os_recursos`) e desenha com o reportlab, nesta ordem:

- o cabeçalho (a OS, o status, o título) e os dados da OS (ativo, cliente e usina, tipo, classificação, criticidade,
  responsável, quem criou, datas, duração, solicitação, OS pai, etiquetas);
- cada tarefa com as subtarefas e as respostas, na ordem do card (`os_acoes_web.subtarefas_por_tarefa`);
- os recursos lançados e as observações da OS;
- as fotos, duas por linha (as das subtarefas com a subtarefa embaixo, depois as da OS), reduzidas a FOTO_PX;
- os outros anexos (documentos e notas de texto), pelo nome.

`modelo()` é o conteúdo, sem desenhar (os testes conferem nele); `gerar()` desenha. O reportlab e o Pillow só são
importados aqui, na hora: o OS Creator de mesa nunca passa por este arquivo. Fonte Helvetica (cobre o português); o que
ela não tem (emoji, símbolos) sai sem o caractere, em vez de um quadrado.
"""
from __future__ import annotations

import io
import unicodedata
from xml.sax.saxutils import escape

import api

from . import os_acoes_web as regra

FOTO_PX, FOTO_QUALIDADE = 1000, 72          # a foto no PDF: nítida no zoom, e uma OS de 60 fotos fica em poucos MB
FOTOS_MAX = 200                             # mais que isso, o PDF diz quantas ficaram de fora
TOM_STATUS = {1: "alerta", 2: "info", 3: "ok", 4: "critico"}     # as cores do STATUS_COR do card, no papel
TOM_SITUACAO = {"ok": "ok", "and": "alerta", "nao": "neutro"}    # `os_acoes_web.situacao_tarefa`
SEMPRE = ("Ativo", "Responsável", "Data do evento", "Data fim")  # sem valor, saem com "—"; os outros dados somem


def _vazio(v) -> bool:
    s = str(v if v is not None else "").strip()
    return not s or s.lower() == "none" or s == "—"


def _data(v) -> str:
    return "—" if _vazio(v) else api.fmt_data_br(v)


def numero(v) -> str:
    """3 → "3"; 2.5 → "2,5"; vazio → "—"."""
    try:
        x = float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return "—" if _vazio(v) else str(v).strip()
    if x == int(x):
        return str(int(x))
    return ("%.3f" % x).rstrip("0").rstrip(".").replace(".", ",")


def dinheiro(v) -> str:
    """1234.5 → "R$ 1.234,50"; zero ou vazio → ""."""
    try:
        x = float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return ""
    if not x:
        return ""
    inteiro, dec = ("%.2f" % abs(x)).split(".")
    return ("-" if x < 0 else "") + "R$ %s,%s" % ("{:,}".format(int(inteiro)).replace(",", "."), dec)


def modelo(d: dict, *, recursos=None, anexos_sub=(), anexos_os=(), local=None) -> dict:
    """O conteúdo do PDF, sem desenhar. `d` = `api.get_os_detalhes`; `recursos` = `api.get_os_recursos` (None = não deu
    para ler); `anexos_sub`/`anexos_os` = as duas listas dos anexos do card; `local` = (cliente, usina, tipo) do ativo."""
    d = d or {}
    loc = tuple(local or ()) + ("", "", "")
    etiquetas = ", ".join(str(e.get("nome") or "").strip() for e in (d.get("etiquetas") or [])
                          if isinstance(e, dict) and str(e.get("nome") or "").strip())
    dados = [("Ativo", d.get("ativo")), ("Código do ativo", d.get("code")), ("Cliente", loc[0]), ("Usina", loc[1]),
             ("Tipo de tarefa", d.get("tipo")), ("Classificação", d.get("classif")),
             ("Criticidade", d.get("criticidade")), ("Responsável", d.get("responsavel")),
             ("Criado por", d.get("criado_por")), ("Data do evento", _data(d.get("event_date"))),
             ("Data fim", _data(d.get("data_fim"))),
             ("Duração total", api.duracao_os(d.get("event_date"), d.get("data_fim"))),
             ("Solicitação", d.get("solicitacao")), ("OS pai", d.get("os_pai")), ("Etiquetas", etiquetas),
             ("Motivo do cancelamento", d.get("cancel_motivo")), ("Nota do cancelamento", d.get("cancel_nota"))]
    dados = [(k, "—" if _vazio(v) else str(v).strip()) for k, v in dados if k in SEMPRE or not _vazio(v)]

    tarefas = []
    grupos = regra.subtarefas_por_tarefa(d)
    lista = [t for t in (d.get("tarefas") or []) if isinstance(t, dict)]
    if not grupos:                                   # uma tarefa só: o card mostra a lista direta
        t = lista[0] if lista else {}
        situacao, sit = regra.situacao_tarefa(t) if t else ("", "")
        subs = [s for s in (d.get("subtarefas") or []) if isinstance(s, dict)]
        grupos = [{"id": t.get("id"), "n": 1, "titulo": str(t.get("titulo") or d.get("descricao") or "Tarefa").strip(),
                   "ativo": str(t.get("ativo") or "").strip(), "tipo": str(t.get("tipo") or d.get("tipo") or "").strip(),
                   "programada": t.get("programada"), "inicio": t.get("inicio"), "fim": t.get("fim"),
                   "situacao": situacao, "sit": sit, "subtarefas": subs,
                   "feitas": sum(1 for s in subs if s.get("feito")), "total": len(subs)}]
    por_id = {t.get("id"): t for t in lista if t.get("id") is not None}
    for g in grupos:
        t = por_id.get(g.get("id")) or {}
        tarefas.append({"n": g.get("n"), "titulo": g.get("titulo") or "Tarefa", "ativo": g.get("ativo") or "",
                        "tipo": g.get("tipo") or "", "situacao": g.get("situacao") or "",
                        "tom": TOM_SITUACAO.get(g.get("sit"), "neutro"),
                        "programada": _data(g.get("programada")), "inicio": _data(g.get("inicio")),
                        "fim": _data(g.get("fim")), "duracao": api.duracao_os(g.get("inicio"), g.get("fim")),
                        "nota": str(t.get("nota") or "").strip(),
                        "subtarefas": [{"descricao": str(s.get("descricao") or "").strip(),
                                        "tipo": str(s.get("tipo") or "").strip(),
                                        "resposta": "—" if _vazio(s.get("resposta")) else str(s.get("resposta")).strip(),
                                        "feito": bool(s.get("feito"))} for s in g.get("subtarefas") or []],
                        "feitas": g.get("feitas") or 0, "total": g.get("total") or 0})

    # os anexos como os dois cards do OS Creator os mostram: das subtarefas (todos) e da OS (sem o que já é de subtarefa)
    subs = [a for a in (anexos_sub or []) if isinstance(a, dict)]
    img_s, doc_s, nota_s = regra.separar_anexos(subs)
    img_o, doc_o, nota_o = regra.separar_anexos(regra.anexos_da_os_unicos(subs, anexos_os))
    fotos = ([{"legenda": str(a.get("descricao") or a.get("nome") or "").strip(),
               "de": str(a.get("subtarefa") or "").strip(), "item": {"url": a.get("url"), "value": a.get("value")}}
              for a in img_s]
             + [{"legenda": str(a.get("nome") or "").strip(), "de": str(a.get("user") or "").strip(),
                 "item": {"url": a.get("url"), "value": a.get("value")}} for a in img_o])
    documentos = ([{"nome": str(a.get("nome") or regra.fname(a.get("value")) or "arquivo"),
                    "de": str(a.get("subtarefa") or "").strip()} for a in doc_s]
                  + [{"nome": str(a.get("nome") or regra.fname(a.get("value")) or "arquivo"),
                      "de": str(a.get("user") or "").strip()} for a in doc_o])
    notas = ([{"texto": str(a.get("descricao") or a.get("nome") or "").strip(), "de": str(a.get("subtarefa") or "")}
              for a in nota_s]
             + [{"texto": str(a.get("desc") or a.get("nome") or "").strip(), "de": str(a.get("user") or "")}
                for a in nota_o])
    status_id = d.get("status_id")
    return {"folio": str(d.get("folio") or "").strip(), "descricao": str(d.get("descricao") or "").strip(),
            "status": api.WO_STATUS.get(status_id, ""), "tom_status": TOM_STATUS.get(status_id, "neutro"),
            "dados": dados, "tarefas": tarefas,
            "recursos": None if recursos is None else [r for r in recursos if isinstance(r, dict)],
            "observacoes": str(d.get("notas") or "").strip(),
            "fotos": fotos[:FOTOS_MAX], "fotos_fora": max(0, len(fotos) - FOTOS_MAX),
            "documentos": documentos, "notas_anexo": [n for n in notas if n["texto"]]}


def reduzir(dados: bytes, px: int = FOTO_PX, qualidade: int = FOTO_QUALIDADE):
    """(JPEG de até `px` no lado maior, (largura, altura)), ou None se não for imagem. O JPEG que já cabe passa como veio;
    o maior é decodificado já reduzido (`draft`), como as fotos dos extintores no Nexus (hseq/fotos.py)."""
    try:
        from PIL import Image, ImageOps
        im = Image.open(io.BytesIO(dados))
        if im.format == "JPEG" and im.mode in ("RGB", "L") and max(im.size) <= px and                 im.getexif().get(0x0112, 1) == 1:                        # sem girar: passa como veio
            return dados, im.size
        im.draft("RGB", (px, px))
        im = ImageOps.exif_transpose(im)             # a foto do celular deitada sai em pé, como no Fracttal
        im = im.convert("RGB")
        im.thumbnail((px, px))
        out = io.BytesIO()
        im.save(out, "JPEG", quality=qualidade, optimize=True)
        return out.getvalue(), im.size
    except Exception:       # noqa: BLE001 — arquivo que não é foto (ou ilegível) sai como "a foto não veio"
        return None


# ── o desenho ──────────────────────────────────────────────────────────────────────────────────────────────────────
def _seguro(v) -> str:
    """Só o que a Helvetica tem (cp1252): o acento que vem decomposto fica; emoji e símbolo saem."""
    out = []
    for c in str(v if v is not None else ""):
        try:
            c.encode("cp1252")
            out.append(c)
        except UnicodeEncodeError:
            out.append(unicodedata.normalize("NFKD", c).encode("cp1252", "ignore").decode("cp1252"))
    return "".join(out)


def _texto(v) -> str:
    """Texto seguro para o Paragraph: `_seguro`, com o XML escapado."""
    return escape(_seguro(v))


def _linhas(v) -> str:
    return "<br/>".join(_texto(x) for x in str(v or "").splitlines())


def gerar(m: dict, *, fotos=(), gerado_em: str = "", quem: str = "", logo: str | None = None) -> bytes:
    """O PDF de `modelo()`. `fotos` = uma por `m["fotos"]`, na mesma ordem: o `reduzir()` dela, ou None (não veio)."""
    from reportlab import rl_config
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import CondPageBreak, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    rl_config.useA85 = 0                             # imagens em binário: o ASCII85 aumenta o arquivo em 25%

    navy, verde = colors.HexColor("#090d18"), colors.HexColor("#b5d334")
    linha, fundo, mudo, tinta = (colors.HexColor("#d8dce4"), colors.HexColor("#f3f5f8"), colors.HexColor("#5b6475"),
                                 colors.HexColor("#111827"))
    tom = {"critico": colors.HexColor("#c8102e"), "alerta": colors.HexColor("#b26a00"),
           "ok": colors.HexColor("#1f7a3f"), "info": colors.HexColor("#1f5fa8"), "neutro": colors.HexColor("#5b6475")}
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=8.6, leading=11, textColor=tinta)
    e = {"base": base,
         "mudo": ParagraphStyle("mudo", parent=base, textColor=mudo, fontSize=7.8, leading=10),
         "titulo": ParagraphStyle("titulo", parent=base, fontName="Helvetica-Bold", fontSize=18, leading=22),
         "sub": ParagraphStyle("sub", parent=base, fontSize=10, leading=13, textColor=tinta),
         "secao": ParagraphStyle("secao", parent=base, fontName="Helvetica-Bold", fontSize=11, leading=14,
                                 textColor=navy, spaceBefore=2),
         "k": ParagraphStyle("k", parent=base, fontSize=7.6, leading=10, textColor=mudo),
         "cab": ParagraphStyle("cab", parent=base, fontName="Helvetica-Bold", fontSize=7.2, leading=9, textColor=mudo),
         "tarefa": ParagraphStyle("tarefa", parent=base, fontName="Helvetica-Bold", fontSize=9.6, leading=12),
         "legenda": ParagraphStyle("legenda", parent=base, fontSize=7.4, leading=9.4, textColor=mudo),
         "vazio": ParagraphStyle("vazio", parent=base, fontSize=7.8, leading=10, textColor=mudo, alignment=1)}
    larg_util = 182 * mm

    def cor(t) -> str:
        return tom.get(t, tom["neutro"]).hexval()[2:]

    def secao(titulo, extra=""):
        p = Paragraph(_texto(titulo) + (f' <font size=8 color="#{mudo.hexval()[2:]}">{_texto(extra)}</font>'
                                        if extra else ""), e["secao"])
        t = Table([[p]], colWidths=[larg_util])
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.8, verde), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        return [CondPageBreak(30 * mm), t, Spacer(1, 2.5 * mm)]

    folio = m.get("folio") or "—"

    def pagina(c, doc):
        c.saveState()
        larg, alt = A4
        c.setFillColor(navy)
        c.rect(0, alt - 16 * mm, larg, 16 * mm, stroke=0, fill=1)
        c.setFillColor(verde)
        c.rect(0, alt - 16.6 * mm, larg, 0.6 * mm, stroke=0, fill=1)
        if logo:
            try:
                c.drawImage(logo, 14 * mm, alt - 12 * mm, width=34 * mm, height=6 * mm, mask="auto",
                            preserveAspectRatio=True)
            except Exception:       # noqa: BLE001 — sem o logo, segue o texto
                pass
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 10)
        c.drawRightString(larg - 14 * mm, alt - 9.4 * mm, _seguro(f"Ordem de serviço {folio}"))
        c.setFillColor(mudo)
        c.setFont("Helvetica", 7.5)
        rodape = "OS Creator Web · Grid Co. · dados do Fracttal" + (f" · gerado em {gerado_em}" if gerado_em else "")
        if quem:
            rodape += f" por {quem}"
        c.drawString(14 * mm, 9 * mm, _seguro(rodape))
        c.drawRightString(larg - 14 * mm, 9 * mm, f"Página {doc.page}")
        c.restoreState()

    story = []
    status = (f' &nbsp;<font size=10 color="#{cor(m.get("tom_status"))}"><b>{_texto(m["status"])}</b></font>'
              if m.get("status") else "")
    story += [Paragraph(f"OS {_texto(folio)}{status}", e["titulo"])]
    if m.get("descricao"):
        story.append(Paragraph(_texto(m["descricao"]), e["sub"]))
    story.append(Spacer(1, 4 * mm))

    # os dados da OS, dois pares por linha
    pares = list(m.get("dados") or [])
    linhas = []
    for i in range(0, len(pares), 2):
        par = pares[i:i + 2] + [("", "")] * (2 - len(pares[i:i + 2]))
        linhas.append([c for k, v in par for c in (Paragraph(_texto(k), e["k"]), Paragraph(_texto(v), e["base"]))])
    if linhas:
        t = Table(linhas, colWidths=[28 * mm, 63 * mm, 28 * mm, 63 * mm])
        t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, linha), ("LINEBELOW", (0, 0), (-1, -2), 0.4, linha),
                               ("BACKGROUND", (0, 0), (0, -1), fundo), ("BACKGROUND", (2, 0), (2, -1), fundo),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 3),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        story += [t, Spacer(1, 5 * mm)]

    # as tarefas, cada uma com as subtarefas e as respostas
    tarefas = m.get("tarefas") or []
    story += secao("Tarefas e subtarefas", f"{len(tarefas)} tarefa{'s' if len(tarefas) != 1 else ''}")
    for tf in tarefas:
        n = f"Tarefa {tf['n']} · " if tf.get("n") and len(tarefas) > 1 else ""
        meta = [x for x in (tf.get("ativo"), tf.get("tipo")) if x]
        datas = [f"{k} {v}" for k, v in (("programada", tf.get("programada")), ("início", tf.get("inicio")),
                                         ("fim", tf.get("fim"))) if v and v != "—"]
        if tf.get("duracao"):
            datas.append(f"duração {tf['duracao']}")
        linha1 = f"{_texto(n + tf['titulo'])}"
        if tf.get("situacao"):
            linha1 += f' &nbsp;<font size=8 color="#{cor(tf["tom"])}">{_texto(tf["situacao"])}</font>'
        cab = [[Paragraph(linha1, e["tarefa"])]]
        if meta or datas:
            cab.append([Paragraph(_texto(" · ".join(meta + datas)), e["mudo"])])
        if tf.get("total"):
            cab.append([Paragraph(_texto(f"{tf['feitas']} de {tf['total']} subtarefas feitas"), e["mudo"])])
        ct = Table(cab, colWidths=[larg_util])
        ct.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), fundo),
                                ("LINEBEFORE", (0, 0), (0, -1), 3, tom.get(tf.get("tom"), tom["neutro"])),
                                ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 3),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        bloco = [ct]
        if tf.get("nota"):
            bloco += [Spacer(1, 1.2 * mm), Paragraph("<b>Nota da tarefa:</b> " + _linhas(tf["nota"]), e["base"])]
        subs = tf.get("subtarefas") or []
        if subs:
            rows = [[Paragraph(c, e["cab"]) for c in ("#", "SUBTAREFA", "TIPO", "RESPOSTA", "FEITA")]]
            for i, s in enumerate(subs, 1):
                feita = f'<font color="#{cor("ok")}"><b>Sim</b></font>' if s["feito"] else _texto("—")
                rows.append([Paragraph(str(i), e["mudo"]), Paragraph(_texto(s["descricao"]), e["base"]),
                             Paragraph(_texto(s["tipo"]), e["mudo"]), Paragraph(_linhas(s["resposta"]), e["base"]),
                             Paragraph(feita, e["base"])])
            st = Table(rows, colWidths=[8 * mm, 86 * mm, 22 * mm, 52 * mm, 14 * mm], repeatRows=1)
            st.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, linha), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                    ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
            bloco += [Spacer(1, 1.5 * mm), st]
        else:
            bloco += [Spacer(1, 1.2 * mm), Paragraph("Sem subtarefas.", e["mudo"])]
        # o cabeçalho da tarefa nunca fica sozinho no pé da página; a tabela corre pelas páginas (o cabeçalho dela se
        # repete), sem empurrar uma tarefa longa inteira para a página seguinte
        story += [CondPageBreak(35 * mm), *bloco, Spacer(1, 4 * mm)]

    # os recursos
    recursos = m.get("recursos")
    story += secao("Recursos", "" if not recursos else f"{len(recursos)} lançado{'s' if len(recursos) != 1 else ''}")
    if recursos is None:
        story.append(Paragraph("Não consegui ler os recursos no Fracttal: o PDF saiu sem eles.", e["mudo"]))
    elif not recursos:
        story.append(Paragraph("Nenhum recurso lançado nesta OS.", e["mudo"]))
    else:
        com_custo = any(dinheiro(r.get("custo_total")) for r in recursos)
        cab = ["TIPO", "DESCRIÇÃO", "QTD.", "UN.", "ORIGEM"] + (["CUSTO"] if com_custo else [])
        larguras = ([30 * mm, 72 * mm, 14 * mm, 14 * mm, 30 * mm, 22 * mm] if com_custo
                    else [30 * mm, 88 * mm, 16 * mm, 16 * mm, 32 * mm])
        rows = [[Paragraph(c, e["cab"]) for c in cab]]
        for r in recursos:
            desc = _texto(r.get("descricao")) + (f'<br/><font size=7.4 color="#{mudo.hexval()[2:]}">'
                                                 f'{_texto(r["nota"])}</font>' if r.get("nota") else "")
            linha_r = [Paragraph(_texto(r.get("tipo")), e["base"]), Paragraph(desc, e["base"]),
                       Paragraph(_texto(numero(r.get("qtd"))), e["base"]),
                       Paragraph(_texto(r.get("unidade") or "—"), e["base"]),
                       Paragraph(_texto(r.get("origem") or "—"), e["base"])]
            if com_custo:
                linha_r.append(Paragraph(_texto(dinheiro(r.get("custo_total")) or "—"), e["base"]))
            rows.append(linha_r)
        rt = Table(rows, colWidths=larguras, repeatRows=1)
        rt.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, linha), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
        story.append(rt)
    story.append(Spacer(1, 5 * mm))

    # as observações da OS
    if m.get("observacoes"):
        story += secao("Observações da OS")
        story += [Paragraph(_linhas(m["observacoes"]), e["base"]), Spacer(1, 5 * mm)]

    # as fotos, duas por linha
    lista = list(m.get("fotos") or [])
    prontas = list(fotos or []) + [None] * max(0, len(lista) - len(fotos or ()))
    if lista:
        n_ok = sum(1 for f in prontas[:len(lista)] if f)
        extra = f"{n_ok} de {len(lista)}" if n_ok != len(lista) else str(len(lista))
        story += secao("Fotos", extra)
        lado_w, lado_h = 86 * mm, 66 * mm
        celulas = []
        for f, pronta in zip(lista, prontas):
            if pronta:
                jpeg, (w, h) = pronta
                k = min(lado_w / w, lado_h / h)
                img = Image(io.BytesIO(jpeg), width=w * k, height=h * k)
            else:
                img = Paragraph("A foto não veio do Fracttal<br/>(o link do arquivo expira: gere o PDF de novo).",
                                e["vazio"])
            # um quadro da mesma altura para toda foto (em pé ou deitada): as legendas da linha ficam na mesma altura
            quadro = Table([[img]], colWidths=[lado_w], rowHeights=[lado_h])
            quadro.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                                        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]
                                       + ([] if pronta else [("BACKGROUND", (0, 0), (-1, -1), fundo),
                                                             ("BOX", (0, 0), (-1, -1), 0.6, linha)])))
            leg = (f"<b>{_texto(f['de'])}</b><br/>" if f.get("de") else "") + _texto(f.get("legenda") or "")
            celulas.append([quadro, Spacer(1, 1.2 * mm), Paragraph(leg, e["legenda"])])
        rows = [celulas[i:i + 2] + [""] * (2 - len(celulas[i:i + 2])) for i in range(0, len(celulas), 2)]
        ft = Table(rows, colWidths=[larg_util / 2] * 2)
        ft.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                                ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        story.append(ft)
        if m.get("fotos_fora"):
            story.append(Paragraph(_texto(f"Mais {m['fotos_fora']} fotos ficaram de fora (o PDF leva até "
                                          f"{FOTOS_MAX}); estão nos anexos da OS."), e["mudo"]))
        story.append(Spacer(1, 5 * mm))

    # os outros anexos, pelo nome
    docs, notas = m.get("documentos") or [], m.get("notas_anexo") or []
    if docs or notas:
        story += secao("Outros anexos", f"{len(docs) + len(notas)}")
        for x in docs:
            story.append(Paragraph(f"<b>{_texto(x['nome'])}</b>" + (f" · {_texto(x['de'])}" if x.get("de") else ""),
                                   e["base"]))
        for x in notas:
            story.append(Paragraph(_linhas(x["texto"]) + (f' <font color="#{mudo.hexval()[2:]}">· {_texto(x["de"])}'
                                                         f'</font>' if x.get("de") else ""), e["base"]))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=22 * mm,
                            bottomMargin=16 * mm, title=f"OS {folio}", author="OS Creator Web · Grid Co.")
    doc.build(story, onFirstPage=pagina, onLaterPages=pagina)
    return buf.getvalue()

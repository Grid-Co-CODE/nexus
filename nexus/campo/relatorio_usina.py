"""O relatório da usina em PDF, para o cliente (Levi, 04/11/2026: "é interessante que dê para baixar um relatório da usina
também! Algo bem profissional para o cliente!"). O "Baixar relatório" da Central da usina (a aba da Visão do responsável)
abre a escolha do mês e dos temas, como no Painel ("Tem que poder escolher que nem é no painel").

Decisões do Levi (04/11/2026): o mês é escolhido na hora de baixar, o anterior (fechado) de início, e o mês corrente sai
parcial, até ontem; os temas Performance e disponibilidade, Rondas e limpeza, Manutenção e Chamados de garantia, todos
marcados; PT, Segurança e os nomes dos técnicos ficam de fora (são internos).

- **O dado é o das telas donas, pelo mesmo leitor**, nada recalculado aqui: a meta e o dia a dia do Gerencial
  (`responsaveis.metas`, `serie_diaria`, `tabela_meta`), a disponibilidade (`disponibilidade`, `disp_diaria`,
  `os_disponibilidade`), as rondas da usina (`visao.historico_usina`), as tarefas feitas pelo App (`fato_fechamento`, sem
  as devolvidas), as OS abertas (`fato_tarefa_os`, a regra do bloco Manutenção: sem backoffice, teste e OS de chamado) e
  os chamados (`fato_chamado`, o quadro Acompanhamento de chamados).
- **Os meses:** o atual e os dois anteriores: as rondas, os chamados e as tarefas ficam 90 dias no banco.
- **O tema que não abre** sai com "não consegui ler" no lugar, e o resto do relatório vale.
- Fonte Helvetica e a paleta dos outros relatórios do Nexus (`painel_relatorio`, `hseq/relatorio`): sem "≥" nem seta,
  que ela não tem; o logo é o da Grid Co. (`static/grid-h-branco.png`) na faixa navy do topo.
"""
import calendar
import collections
import io
from datetime import date, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab import rl_config
from reportlab.graphics.shapes import Drawing, Line, PolyLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import CondPageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import visao

rl_config.useA85 = 0        # binário, sem ASCII85 (o arquivo 25% menor; ver o relatório dos extintores)

NAVY, VERDE, VERDE_ESC = colors.HexColor("#090d18"), colors.HexColor("#b5d334"), colors.HexColor("#6f8f0b")
TOM = {"critico": colors.HexColor("#c8102e"), "alerta": colors.HexColor("#b26a00"), "ok": colors.HexColor("#1f7a3f"),
       "neutro": colors.HexColor("#5b6475")}
LINHA, FUNDO, MUDO, TINTA = (colors.HexColor("#d8dce4"), colors.HexColor("#f3f5f8"), colors.HexColor("#5b6475"),
                             colors.HexColor("#111827"))
LOGO = Path(__file__).resolve().parents[1] / "static" / "grid-h-branco.png"
MESES_NOME = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
              "novembro", "dezembro")
MESES = 3                   # o atual e os dois anteriores (90 dias no banco)
LARG = 178 * mm - 12        # a largura útil (o quadro do SimpleDocTemplate tem 6 pt de folga de cada lado)
TEMAS = (("perf", "Performance e disponibilidade"), ("rondas", "Rondas e limpeza"), ("manut", "Manutenção"),
         ("chamados", "Chamados de garantia"))
CHAVES_TEMAS = tuple(k for k, _ in TEMAS)
# Os CAMPOS de cada tema (12/11/2026, Levi, no prontuário da usina: "eu quero o relatório de forma profissional, que dê
# para editar os campos que eu quero que apareça"): cada bloco do PDF é um campo que a pessoa liga e desliga na janela
# do relatório. (a chave, o tema dele — "" = o resumo, que é de todos —, o nome na janela), na ordem do PDF. Sem `campo`
# no pedido valem todos os campos dos temas pedidos: o endereço de antes, só com `tema`, dá o mesmo PDF de sempre
CAMPOS = (("resumo", "", "Resumo do mês, em frases"),
          ("perf_numeros", "perf", "Os números do mês: geração, meta, PR e disponibilidade"),
          ("perf_grafico", "perf", "Gráfico da geração de cada dia contra a meta"),
          ("perf_dias", "perf", "Tabela do dia a dia"),
          ("perf_eventos", "perf", "Eventos que afetaram a disponibilidade"),
          ("rondas_lista", "rondas", "Rondas do mês, com sujidade e vegetação"),
          ("manut_feitas", "manut", "Tarefas executadas no mês"),
          ("manut_abertas", "manut", "Ordens de serviço em aberto"),
          ("manut_zeladoria", "manut", "Zeladoria feita"),
          ("chamados_lista", "chamados", "Chamados do mês"),
          ("chamados_abertos", "chamados", "Chamados em aberto hoje"))
CHAVES_CAMPOS = tuple(k for k, _tema, _rot in CAMPOS)
TIPO_TAREFA = {"preventiva": "Preventiva", "corretiva": "Corretiva", "corretiva_emergencial": "Corretiva emergencial",
               "religamento": "Religamento", "religamento_remoto": "Religamento remoto", "inspecao": "Inspeção",
               "preditiva": "Preditiva", "administrativa": "Administrativa", "zeladoria": "Zeladoria",
               "handover": "Handover"}


# ── o mês e os temas do pedido ─────────────────────────────────────────────────────────────────────────────────────
def meses(hoje: date) -> list[tuple[str, str]]:
    """[("AAAA-MM", "Outubro de 2026")]: o mês atual e os dois anteriores, o mais novo primeiro."""
    out, a, m = [], hoje.year, hoje.month
    for _ in range(MESES):
        out.append((f"{a:04d}-{m:02d}", f"{MESES_NOME[m - 1].capitalize()} de {a}"))
        a, m = (a, m - 1) if m > 1 else (a - 1, 12)
    return out


def mes_padrao(hoje: date) -> str:
    """O mês fechado anterior (a decisão do Levi: o relatório do cliente é de mês fechado, o anterior de início)."""
    return meses(hoje)[1][0]


def mes_do_pedido(valor, hoje: date) -> str:
    validos = [m for m, _ in meses(hoje)]
    return valor if valor in validos else mes_padrao(hoje)


def temas_do_pedido(pedidos) -> tuple:
    """Os temas pedidos, na ordem do relatório (o que não é tema não entra); nenhum pedido válido = todos."""
    quer = {str(x).strip() for x in pedidos or ()}
    return tuple(k for k in CHAVES_TEMAS if k in quer) or CHAVES_TEMAS


def campos_por_tema() -> list[tuple[str, str, list[tuple[str, str]]]]:
    """Os campos agrupados para a janela do relatório: [(tema, o nome do tema, [(campo, nome)])], o geral ("") primeiro."""
    nomes = dict(TEMAS)
    return [(t, nomes.get(t, "Geral"), [(k, rot) for k, tema, rot in CAMPOS if tema == t]) for t in ("",) + CHAVES_TEMAS]


def campos_do_pedido(pedidos, temas=CHAVES_TEMAS) -> tuple:
    """Os campos que entram no PDF, na ordem dele: os pedidos (`campo` repetido) que são dos temas pedidos (o resumo é
    de todos). Sem nenhum campo válido no pedido, ou se nenhum for dos temas, valem todos os campos dos temas (o
    endereço só com `tema`): o relatório nunca sai vazio por um endereço torto."""
    quer = {str(x).strip() for x in pedidos or ()}
    dos_temas = tuple(k for k, tema, _rot in CAMPOS if not tema or tema in temas)
    return tuple(k for k in dos_temas if k in quer) or dos_temas


def temas_dos_campos(temas, campos) -> tuple:
    """Os temas que têm ao menos um campo ligado, na ordem do relatório: o resumo só fala deles (quem desligou todos os
    campos das Rondas não lê a frase das rondas). Com só o resumo ligado, ele fala de todos os temas pedidos."""
    com = {tema for k, tema, _rot in CAMPOS if k in campos and tema}
    return tuple(t for t in temas if t in com) or tuple(temas)


# ── os dados, das telas donas ──────────────────────────────────────────────────────────────────────────────────────
def _num(v):
    try:
        return None if v is None or v == "" else float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _dia_id(v) -> date | None:
    n = visao.D._int(v)
    try:
        return date(n // 10000, n // 100 % 100, n % 100) if n else None
    except ValueError:
        return None


def _tipo(v) -> str:
    t = visao.D._txt(v).strip().lower().replace(" ", "_")
    return TIPO_TAREFA.get(t) or (visao.D._txt(v).strip().capitalize() or "Outras")


def dados(uid: int, mes: str, hoje: date) -> dict:
    """Tudo o que o relatório mostra da usina no mês, cada tema da sua fonte; o tema que não abre fica em `erros`."""
    from ..dados import fato_tarefa_os as FT
    from . import responsaveis as R
    from . import ronda_checklist
    b = visao._Base()
    o = b.onde(uid)
    cad = b.por_id.get(uid) or {}
    ano, m = int(mes[:4]), int(mes[5:7])
    mes_id = ano * 100 + m
    corrente = (ano, m) == (hoje.year, hoje.month)
    fim = (hoje - timedelta(days=1)) if corrente else date(ano, m, calendar.monthrange(ano, m)[1])
    out = {"uid": uid, "usina": o.get("usina") or "", "cliente": o.get("cliente") or "", "cidade": o.get("cidade") or "",
           "uf": o.get("uf") or "", "potencia_mwp": _num(cad.get("potencia_real")), "mes": mes, "mes_id": mes_id,
           "mes_txt": f"{MESES_NOME[m - 1]} de {ano}", "ini": date(ano, m, 1), "fim": fim, "corrente": corrente,
           "hoje": hoje, "erros": {}}
    nomes = R.Nomes(b)
    try:
        meta = R.metas(nomes, mes_id)[0].get(uid) or {}
        disp = R.disponibilidade(nomes, mes)[0].get(uid) or {}
        serie = R.serie_diaria(uid, mes_id, nomes)
        out["perf"] = {"meta": meta, "disp": disp, "serie": serie,
                       "tabela": R.tabela_meta(serie, R.disp_diaria(uid, mes, nomes), disp.get("disp")),
                       "oss": R.os_disponibilidade(uid, mes, nomes)}
    except Exception as e:      # noqa: BLE001 — o tema diz que não leu; o resto vale
        out["erros"]["perf"] = type(e).__name__
    try:
        lr = visao.rondas()
        dr = lr.dados or {}
        if lr.erro:
            raise visao.SemBanco(lr.erro)
        hist = visao.historico_usina(dr.get("todas") or [], ronda_checklist.respostas(), uid, dr.get("validacoes") or [])
        out["rondas"] = sorted((r for r in hist if str(r.get("data") or "")[:7] == mes and not r.get("validada")),
                               key=lambda r: (r.get("data") or "", r.get("ini_hm") or ""))
    except Exception as e:      # noqa: BLE001
        out["erros"]["rondas"] = type(e).__name__
    try:
        os_chamado = {visao.D._id(r.get("os")) for r in visao._livro(R.LIVRO_CHAMADOS, R.ABA_CHAMADOS)}
        feitas = collections.defaultdict(lambda: {"tarefas": 0, "os": set()})
        for x in visao._fato("fechamento", b)["linhas"]:
            if visao.D._id(x.get("usina_id")) != uid or (visao.D._int(x.get("data_id")) or 0) // 100 != mes_id:
                continue
            if visao.D._int(x.get("devolvida")) == 1:
                continue
            g = feitas[_tipo(x.get("tipo_os"))]
            g["tarefas"] += 1
            g["os"].add(visao.D._id(x.get("os")))
        abertas, zel = collections.defaultdict(set), []
        for t in visao._livro(FT.LIVRO, FT.ABA):
            if visao.D._id(t.get("usina_id")) != uid:
                continue
            tipo, os_ = visao.D._txt(t.get("tipo_tarefa")), visao.D._id(t.get("os"))
            if tipo == "zeladoria":
                d = _dia_id(t.get("data_id_fim"))
                if d and (d.year, d.month) == (ano, m) and visao.D._txt(t.get("estado_tarefa")) == "finalizada":
                    zel.append(d)
                continue
            if (visao.D._int(t.get("do_backoffice")) == 1 or tipo == "teste" or os_ in os_chamado
                    or visao.D._txt(t.get("status_os")) not in ("em_processo", "em_verificacao")):
                continue
            abertas[_tipo(tipo)].add(os_)
        out["manut"] = {"feitas": sorted(({"tipo": k, "tarefas": v["tarefas"], "os": len(v["os"] - {None})}
                                          for k, v in feitas.items()), key=lambda x: -x["tarefas"]),
                        "abertas": sorted(({"tipo": k, "os": len(v - {None})} for k, v in abertas.items()),
                                          key=lambda x: -x["os"]),
                        "zeladoria": sorted(set(zel))}
    except Exception as e:      # noqa: BLE001
        out["erros"]["manut"] = type(e).__name__
    try:
        linhas = [r for r in visao._livro(R.LIVRO_CHAMADOS, R.ABA_CHAMADOS) if visao.D._id(r.get("usina_id")) == uid]
        nome_equip = {visao.D._id(r.get("equipamento_id")): str(r.get("descricao") or "").strip()
                      for r in visao._livro(R.LIVRO_EQUIP, R.ABA_EQUIP)} if linhas else {}
        def item(r):
            eid = visao.D._id(r.get("equipamento_id"))
            ini, fim_c = _dia_id(r.get("data_id_abertura")), _dia_id(r.get("data_id_fim"))
            return {"os": visao.D._id(r.get("os")), "ini": ini, "fim": fim_c, "situacao": str(r.get("situacao") or ""),
                    "dias": ((fim_c or hoje) - ini).days if ini else None,
                    "equip": (nome_equip.get(eid) or str(r.get("codigo_ativo") or "") or "equipamento")[:40],
                    "fabricante": str(r.get("fabricante") or ""), "componente": str(r.get("componente") or "")}
        todos = [item(r) for r in linhas]
        no_mes = [c for c in todos if (c["ini"] and (c["ini"].year, c["ini"].month) == (ano, m))
                  or (c["fim"] and c["situacao"] == "concluido" and (c["fim"].year, c["fim"].month) == (ano, m))]
        out["chamados"] = {"mes": sorted(no_mes, key=lambda c: (c["ini"] or date.min, c["os"] or 0)),
                           "em_aberto": sum(1 for c in todos if c["situacao"] in ("aberto", "verificacao"))}
    except Exception as e:      # noqa: BLE001
        out["erros"]["chamados"] = type(e).__name__
    return out


# ── o PDF ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def _t(v) -> str:
    s = "" if v is None else str(v)
    for a, b in (("≥", ">="), ("→", "->"), (" ", " "), (" ", " ")):
        s = s.replace(a, b)
    return escape(s)


def _br(x, casas=1) -> str:
    return "—" if x is None else f"{x:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(x, casas=1) -> str:
    return "—" if x is None else _br(x, casas) + "%"


def _dm(d) -> str:
    return d.strftime("%d/%m") if d else "—"


def _cor(nivel) -> str:
    return "#" + TOM.get(nivel, TOM["neutro"]).hexval()[2:]


def _cls_meta(a):
    from . import responsaveis as R
    return R.cls_meta(a)


def _cls_disp(x):
    from . import responsaveis as R
    return R.cls_disp(x)


def _estilos() -> dict:
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=9, leading=12.5, textColor=TINTA)
    return {"base": base,
            "mudo": ParagraphStyle("mudo", parent=base, fontSize=8, leading=11, textColor=MUDO),
            "titulo": ParagraphStyle("titulo", parent=base, fontName="Helvetica-Bold", fontSize=21, leading=25),
            "sub": ParagraphStyle("sub", parent=base, fontSize=10, leading=14, textColor=MUDO),
            "secao": ParagraphStyle("secao", parent=base, fontName="Helvetica-Bold", fontSize=13, leading=17,
                                    spaceBefore=4, spaceAfter=2),
            "sub_secao": ParagraphStyle("sub_secao", parent=base, fontName="Helvetica-Bold", fontSize=10, leading=14,
                                        spaceBefore=6, spaceAfter=3),
            "cel": ParagraphStyle("cel", parent=base, fontSize=8.5, leading=11),
            "cel_cab": ParagraphStyle("cel_cab", parent=base, fontName="Helvetica-Bold", fontSize=8, leading=10,
                                      textColor=MUDO),
            "kpi_rot": ParagraphStyle("kpi_rot", parent=base, fontSize=8, leading=10, textColor=MUDO),
            "kpi_val": ParagraphStyle("kpi_val", parent=base, fontName="Helvetica-Bold", fontSize=18, leading=22),
            "kpi_sub": ParagraphStyle("kpi_sub", parent=base, fontSize=7.5, leading=10, textColor=MUDO)}


def _secao(titulo: str, e: dict) -> list:
    """O título da seção com o fio verde embaixo (a marca da Grid Co. nos relatórios)."""
    t = Table([[Paragraph(_t(titulo), e["secao"])]], colWidths=[LARG], hAlign="LEFT")
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 1.6, VERDE), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 0)]))
    return [CondPageBreak(60 * mm), Spacer(1, 7 * mm), t, Spacer(1, 3 * mm)]


def _tabela(e: dict, cab: list[str], linhas: list[list], larguras: list[float], total: bool = False,
            direita: tuple = ()) -> Table:
    dados_t = [[Paragraph(_t(c), e["cel_cab"]) for c in cab]]
    for ln in linhas:
        dados_t.append([c if isinstance(c, Paragraph) else Paragraph(_t(c), e["cel"]) for c in ln])
    # as larguras em mm somam a largura toda; a tabela sai alinhada com o texto, à esquerda
    fator = LARG / (sum(larguras) * mm)
    t = Table(dados_t, colWidths=[w * mm * fator for w in larguras], repeatRows=1, hAlign="LEFT")
    st = [("LINEBELOW", (0, 0), (-1, 0), 0.8, MUDO), ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINHA),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 4),
          ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("LEFTPADDING", (0, 0), (-1, -1), 4),
          ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    for i in range(1, len(dados_t)):
        if i % 2 == 0:
            st.append(("BACKGROUND", (0, i), (-1, i), FUNDO))
    if total and len(dados_t) > 1:
        st += [("LINEABOVE", (0, -1), (-1, -1), 0.8, MUDO), ("BACKGROUND", (0, -1), (-1, -1), colors.white)]
    t.setStyle(TableStyle(st))
    return t


def _p(txt: str, e: dict, estilo: str = "cel", cor: str | None = None, negrito: bool = False) -> Paragraph:
    s = _t(txt)
    if negrito:
        s = f"<b>{s}</b>"
    if cor:
        s = f'<font color="{_cor(cor)}">{s}</font>'
    return Paragraph(s, e[estilo])


def _kpis(d: dict, e: dict) -> Table:
    """Os quatro números do mês, na régua da Visão (a cor diz se está na meta)."""
    p = d.get("perf") or {}
    meta, disp = p.get("meta") or {}, p.get("disp") or {}
    ating, pr, prm, dv = meta.get("atingimento"), meta.get("pr"), meta.get("pr_meta"), disp.get("disp")
    cel = [
        ("Geração no mês", f"{_br((meta.get('prod_kwh') or 0) / 1000)} MWh" if meta.get("prod_kwh") is not None else "—",
         f"meta: {_br((meta.get('meta_kwh') or 0) / 1000)} MWh" if meta.get("meta_kwh") else "sem meta publicada",
         None),
        ("Atingimento da meta", _pct(ating, 0), f"{meta.get('dias_cob') or 0} dias medidos" if meta else "", _cls_meta(ating)),
        ("PR (performance ratio)", _pct(pr), f"previsto {_pct(prm)}" if prm is not None else "",
         None if pr is None or prm is None else ("ok" if pr >= prm else "alerta")),
        ("Disponibilidade", _pct(dv), f"{_br(disp.get('h_perdidas'))} h paradas" if disp else "", _cls_disp(dv))]
    linha = []
    for rot, val, sub, nivel in cel:
        linha.append([Paragraph(_t(rot), e["kpi_rot"]),
                      Paragraph(f'<font color="{_cor(nivel) if nivel else "#111827"}">{_t(val)}</font>', e["kpi_val"]),
                      Paragraph(_t(sub), e["kpi_sub"])])
    t = Table([linha], colWidths=[LARG / 4] * 4, hAlign="LEFT")
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), FUNDO), ("BOX", (0, 0), (-1, -1), 0.5, LINHA),
                           ("LINEAFTER", (0, 0), (-2, -1), 0.5, LINHA), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                           ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
    return t


def _grafico(d: dict) -> Drawing | None:
    """A geração de cada dia (barras verdes) contra a meta do dia (a linha navy), em MWh."""
    dias = [x for x in ((d.get("perf") or {}).get("serie") or {}).get("dias") or [] if x.get("geracao_kwh") is not None]
    if not dias:
        return None
    n_mes = calendar.monthrange(d["ini"].year, d["ini"].month)[1]
    larg, alt, esq, base, topo = LARG, 58 * mm, 12 * mm, 9 * mm, 6 * mm
    area_l, area_a = larg - esq - 2 * mm, alt - base - topo
    maximo = max(max((x["geracao_kwh"] or 0) for x in dias), max((x.get("meta_kwh") or 0) for x in dias)) / 1000
    passo = next(p for p in (0.5, 1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500) if maximo / p <= 5)
    teto = passo * (int(maximo / passo) + 1)
    g = Drawing(larg, alt)
    for i in range(int(teto / passo) + 1):
        y = base + area_a * (i * passo) / teto
        g.add(Line(esq, y, larg - 2 * mm, y, strokeColor=LINHA, strokeWidth=0.4))
        g.add(String(esq - 2, y - 2.5, _br(i * passo, 0 if passo >= 1 else 1), fontName="Helvetica", fontSize=6.5,
                     fillColor=MUDO, textAnchor="end"))
    coluna = area_l / n_mes
    pontos = []
    for x in dias:
        cx = esq + coluna * (x["dia"] - 0.5)
        h = area_a * (x["geracao_kwh"] / 1000) / teto
        g.add(Rect(cx - coluna * 0.32, base, coluna * 0.64, h, fillColor=VERDE, strokeColor=None))
        if x.get("meta_kwh") is not None:
            pontos += [cx, base + area_a * (x["meta_kwh"] / 1000) / teto]
    for dia in range(1, n_mes + 1):
        if dia == 1 or dia % 5 == 0:
            g.add(String(esq + coluna * (dia - 0.5), base - 7, str(dia), fontName="Helvetica", fontSize=6.5,
                         fillColor=MUDO, textAnchor="middle"))
    if len(pontos) >= 4:
        g.add(PolyLine(pontos, strokeColor=NAVY, strokeWidth=1.2))
    g.add(Rect(esq, alt - 4, 7, 4, fillColor=VERDE, strokeColor=None))
    g.add(String(esq + 10, alt - 4, "Geração do dia (MWh)", fontName="Helvetica", fontSize=7, fillColor=MUDO))
    g.add(Line(esq + 100, alt - 2, esq + 112, alt - 2, strokeColor=NAVY, strokeWidth=1.2))
    g.add(String(esq + 116, alt - 4, "Meta do dia (MWh)", fontName="Helvetica", fontSize=7, fillColor=MUDO))
    return g


def _resumo(d: dict, temas: tuple) -> list[str]:
    """As frases do resumo do mês, só dos temas escolhidos (o número e o que ele quer dizer)."""
    out = []
    if "perf" in temas and d.get("perf"):
        meta, disp = d["perf"].get("meta") or {}, d["perf"].get("disp") or {}
        if meta.get("prod_kwh") is not None and meta.get("meta_kwh"):
            dif = (meta.get("atingimento") or 0) - 100
            sinal = "acima" if dif >= 0 else "abaixo"
            out.append(f"A usina gerou {_br(meta['prod_kwh'] / 1000)} MWh, {_br(abs(dif), 0)}% {sinal} da meta dos "
                       f"{meta.get('dias_cob') or 0} dias medidos.")
        if meta.get("pr") is not None and meta.get("pr_meta") is not None:
            out.append(f"O PR do mês foi de {_pct(meta['pr'])}, contra {_pct(meta['pr_meta'])} previstos.")
        if disp.get("disp") is not None:
            n = len((d["perf"].get("oss") or {}).get("oss") or [])
            out.append(f"A disponibilidade foi de {_pct(disp['disp'])}" +
                       (f", com {n} evento{'s' if n != 1 else ''} de parada registrado{'s' if n != 1 else ''}."
                        if n else ", sem parada registrada."))
    if "rondas" in temas and d.get("rondas") is not None:
        n = len(d["rondas"])
        lidas = [r for r in d["rondas"] if r.get("sujidade") is not None]
        if n:
            frase = f"Foram feitas {n} rondas na usina" if n != 1 else "Foi feita 1 ronda na usina"
            if lidas:
                u = lidas[-1]
                frase += f"; na última leitura, sujidade {u['sujidade']} e vegetação {u.get('vegetacao') or '—'} (de 1 a 5)"
            out.append(frase + ".")
    if "manut" in temas and d.get("manut"):
        t = sum(x["tarefas"] for x in d["manut"]["feitas"])
        if t:
            out.append(f"A equipe executou {t} tarefa{'s' if t != 1 else ''} de manutenção no mês.")
    if "chamados" in temas and d.get("chamados"):
        fin = sum(1 for c in d["chamados"]["mes"] if c["situacao"] == "concluido" and c["fim"]
                  and (c["fim"].year, c["fim"].month) == (d["ini"].year, d["ini"].month))
        ab = d["chamados"]["em_aberto"]
        if fin or ab:
            out.append(f"Chamados de garantia: {fin} finalizado{'s' if fin != 1 else ''} no mês e {ab} em aberto "
                       f"em {_dm(d['hoje'])}.")
    return out


def _sem(e: dict, txt: str) -> Paragraph:
    return Paragraph(_t(txt), e["mudo"])


def _perf(d: dict, e: dict, campos=CHAVES_CAMPOS) -> list:
    p = d.get("perf") or {}
    out = []
    g = _grafico(d) if "perf_grafico" in campos else None
    if g:
        out += [Paragraph("Geração diária e meta", e["sub_secao"]), g, Spacer(1, 2 * mm)]
    tab = p.get("tabela") or {}
    if "perf_dias" not in campos:
        # sem a tabela, o gráfico pedido que não tem dado diz que não tem (a seção não fica muda)
        if "perf_grafico" in campos and not g:
            out.append(_sem(e, "Sem geração publicada para a usina neste mês."))
    elif tab.get("linhas"):
        linhas = [[f"{x['dia']:02d}", _br(x["real"]), _br(x["meta"]), _p(f"{x['pct']}%" if x["pct"] is not None else "—", e,
                   cor=x["cls"]), _br(x["poa"], 2), _p(_pct(x["disp"]), e, cor=x["disp_cls"] if x["disp"] is not None else None)]
                  for x in tab["linhas"]]
        t = tab["total"]
        linhas.append([_p("Total", e, negrito=True), _p(_br(t["real"]), e, negrito=True), _p(_br(t["meta"]), e, negrito=True),
                       _p(_pct(t["pct"], 0), e, negrito=True, cor=t["cls"]), _p(_br(t["poa"], 2), e, negrito=True),
                       _p(_pct(t["disp"]), e, negrito=True, cor=t["disp_cls"] if t["disp"] is not None else None)])
        out += [Paragraph("Dia a dia", e["sub_secao"]),
                _tabela(e, ["Dia", "Geração (MWh)", "Meta (MWh)", "% da meta", "POA (kWh/m²)", "Disponibilidade"], linhas,
                        [16, 32, 30, 28, 34, 38], total=True),
                Paragraph("A meta e o atingimento contam os dias com geração medida, como no Gerencial; a disponibilidade "
                          "do dia sai quando o dia fecha.", e["mudo"])]
    else:
        out.append(_sem(e, "Sem geração publicada para a usina neste mês."))
    if "perf_eventos" not in campos:
        return out
    oss = (p.get("oss") or {}).get("oss") or []
    out.append(Paragraph("Eventos que afetaram a disponibilidade", e["sub_secao"]))
    if oss:
        # a usina do cadastro que junta duas do Gerencial (Coração 1 e 2) tem o mesmo evento nas duas: a parte diz qual
        partes = len({x.get("usina") for x in oss}) > 1
        linhas = [[x["inicio"], x["fim"] or "em aberto", *([x.get("usina") or "—"] if partes else []),
                   (x["tipo"] or "—")[:1].upper() + (x["tipo"] or "")[1:], x["escopo"],
                   f"{_br((x['sol_min'] or 0) / 60)} h" if x["sol_min"] is not None else "—",
                   _br(x["perda_kwh"], 0) if x["perda_kwh"] is not None else "—"] for x in oss]
        out.append(_tabela(e, ["Início", "Fim", *(["Parte"] if partes else []), "Tipo", "Escopo", "Horas de sol",
                               "Perda (kWh)"], linhas,
                           [20, 20, *([22] if partes else []), 42, 30, 20, 22]))
    else:
        out.append(_sem(e, "Nenhum evento tirou disponibilidade da usina no mês."))
    return out


def _nivel_txt(n) -> Paragraph | str:
    if n is None:
        return "—"
    return f'<font color="{_cor("critico" if n >= 5 else "alerta" if n >= 4 else "ok")}"><b>{n}</b></font>'


def _rondas(d: dict, e: dict, campos=CHAVES_CAMPOS) -> list:
    if "rondas_lista" not in campos:
        return []
    rs = d.get("rondas") or []
    if not rs:
        return [_sem(e, "Nenhuma ronda registrada na usina no mês.")]
    linhas = []
    for r in rs:
        dia = str(r.get("data") or "")
        sens = r.get("sensores_sujos") or []
        linhas.append([f"{dia[8:10]}/{dia[5:7]}", str(r.get("tipo") or "").capitalize() or "—",
                       Paragraph(_nivel_txt(r.get("sujidade")), e["cel"]), Paragraph(_nivel_txt(r.get("vegetacao")), e["cel"]),
                       str(r.get("vala") or "—").capitalize(),
                       ("sujo: " + ", ".join(sens)) if sens else ("limpos" if r.get("lida") else "—")])
    return [_tabela(e, ["Data", "Tipo", "Sujidade", "Vegetação", "Vala de drenagem", "Sensores"], linhas,
                    [20, 22, 22, 24, 40, 50]),
            Paragraph("Sujidade e vegetação em escala de 1 (baixa) a 5 (muito alta): 4 pede atenção e 5, ação. Ronda "
                      "curta: a volta de rotina; longa: a vistoria completa da usina.", e["mudo"])]


def _manut(d: dict, e: dict, campos=CHAVES_CAMPOS) -> list:
    mt = d.get("manut") or {}
    out = [Paragraph("Tarefas executadas no mês", e["sub_secao"])] if "manut_feitas" in campos else []
    if "manut_feitas" not in campos:
        pass
    elif mt.get("feitas"):
        linhas = [[x["tipo"], str(x["tarefas"]), str(x["os"])] for x in mt["feitas"]]
        linhas.append([_p("Total", e, negrito=True), _p(str(sum(x["tarefas"] for x in mt["feitas"])), e, negrito=True),
                       _p(str(sum(x["os"] for x in mt["feitas"])), e, negrito=True)])
        out.append(_tabela(e, ["Tipo", "Tarefas", "Ordens de serviço"], linhas, [70, 40, 50], total=True))
    else:
        out.append(_sem(e, "Nenhuma tarefa executada pela equipe registrada no mês."))
    if "manut_abertas" in campos:
        out.append(Paragraph(f"Ordens de serviço em aberto em {_dm(d['hoje'])}/{d['hoje'].year}", e["sub_secao"]))
        if mt.get("abertas"):
            out.append(_tabela(e, ["Tipo", "Ordens de serviço"], [[x["tipo"], str(x["os"])] for x in mt["abertas"]], [70, 50]))
        else:
            out.append(_sem(e, "Nenhuma ordem de serviço em aberto."))
    if "manut_zeladoria" in campos and mt.get("zeladoria"):
        out.append(Paragraph("Zeladoria feita em " + ", ".join(_dm(x) for x in mt["zeladoria"]) + ".", e["base"]))
    return out


def _chamados(d: dict, e: dict, campos=CHAVES_CAMPOS) -> list:
    ch = d.get("chamados") or {}
    out = []
    if "chamados_lista" not in campos:
        pass
    elif ch.get("mes"):
        linhas = [[str(c["os"] or "—"), c["equip"], c["fabricante"] or "—", c["componente"] or "—", _dm(c["ini"]),
                   _dm(c["fim"]) if c["situacao"] == "concluido" else ("em verificação" if c["situacao"] == "verificacao"
                                                                       else "em aberto"),
                   str(c["dias"]) if c["dias"] is not None else "—"] for c in ch["mes"]]
        out.append(_tabela(e, ["OS", "Equipamento", "Fabricante", "Componente", "Abertura", "Fim", "Dias"], linhas,
                           [16, 44, 28, 34, 18, 22, 16]))
    else:
        out.append(_sem(e, "Nenhum chamado de garantia aberto ou finalizado no mês."))
    if "chamados_abertos" in campos:
        out.append(Paragraph(f"Em aberto em {_dm(d['hoje'])}/{d['hoje'].year}: {ch.get('em_aberto', 0)} "
                             f"chamado{'s' if ch.get('em_aberto', 0) != 1 else ''} de garantia.", e["base"]))
    return out


def gerar(d: dict, temas=CHAVES_TEMAS, gerado_em: str = "", campos=None) -> bytes:
    """O PDF: a faixa navy com o logo, a usina e o mês, os números do mês, o resumo e um tema por seção. `campos` = os
    campos escolhidos na janela (`campos_do_pedido`; None = todos): o campo desligado não se desenha, e o tema sem
    nenhum campo ligado não abre seção."""
    campos = CHAVES_CAMPOS if campos is None else tuple(campos)
    e = _estilos()
    buf = io.BytesIO()
    periodo = (f"{d['ini'].day} a {d['fim'].day} de {d['mes_txt']}" if d["fim"] >= d["ini"] else d["mes_txt"])
    titulo_pdf = f"Relatório da usina {d['usina']} · {d['mes_txt']}"

    def pagina(c, doc):
        w, h = A4
        c.saveState()
        c.setFillColor(NAVY)
        c.rect(0, h - 20 * mm, w, 20 * mm, fill=1, stroke=0)
        c.setFillColor(VERDE)
        c.rect(0, h - 20.8 * mm, w, 0.8 * mm, fill=1, stroke=0)
        if LOGO.exists():
            try:
                c.drawImage(str(LOGO), 16 * mm, h - 13.4 * mm, width=34 * mm, height=6 * mm, mask="auto",
                            preserveAspectRatio=True, anchor="w")
            except Exception:       # noqa: BLE001 — sem o logo, segue o texto
                pass
        c.setFillColor(colors.white)
        c.setFont("Helvetica", 8.5)
        c.drawRightString(w - 16 * mm, h - 9 * mm, "Relatório mensal da usina")
        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(VERDE)
        c.drawRightString(w - 16 * mm, h - 14.5 * mm, d["mes_txt"].capitalize())
        c.setStrokeColor(LINHA)
        c.setLineWidth(0.5)
        c.line(16 * mm, 13 * mm, w - 16 * mm, 13 * mm)
        c.setFillColor(MUDO)
        c.setFont("Helvetica", 7.5)
        c.drawString(16 * mm, 9 * mm, f"Grid Co. · {d['usina']} · gerado em {gerado_em} (horário de Brasília)")
        c.drawRightString(w - 16 * mm, 9 * mm, f"Página {doc.page}")
        c.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=28 * mm,
                            bottomMargin=19 * mm, title=titulo_pdf, author="Grid Co.")
    onde = " · ".join(v for v in (d["cliente"], f"{d['cidade']}/{d['uf']}" if d["cidade"] else d["uf"],
                                  f"{_br(d['potencia_mwp'], 2)} MWp" if d["potencia_mwp"] else "") if v)
    story = [Paragraph(_t(d["usina"]), e["titulo"]), Paragraph(_t(onde), e["sub"]),
             Paragraph(_t(f"Período: {periodo}" + (" (mês em andamento, até ontem)" if d["corrente"] else "")), e["sub"]),
             Spacer(1, 6 * mm)]
    if "perf" in temas and "perf_numeros" in campos:
        story += [_kpis(d, e), Spacer(1, 5 * mm)]
    frases = _resumo(d, temas) if "resumo" in campos else []
    if frases:
        story += [Paragraph("Resumo do mês", e["sub_secao"])]
        story += [Paragraph("• " + _t(f), e["base"]) for f in frases]
    secoes = {"perf": ("Performance e disponibilidade", _perf), "rondas": ("Rondas e limpeza", _rondas),
              "manut": ("Manutenção", _manut), "chamados": ("Chamados de garantia", _chamados)}
    for k in temas:
        titulo, f = secoes[k]
        if k in d["erros"]:
            corpo = [_sem(e, f"Não consegui ler os dados deste tema ({d['erros'][k]}): ele ficou de fora.")]
        else:
            corpo = f(d, e, campos)
        if corpo:
            story += _secao(titulo, e) + corpo
    story += [Spacer(1, 8 * mm),
              Paragraph("Fontes: geração, meta e PR do Gerencial da Grid Co.; disponibilidade, ordens de serviço e chamados "
                        "do sistema de manutenção (Fracttal); rondas do App de Campo. "
                        + ("O mês em andamento é parcial: os números mudam até o mês fechar." if d["corrente"] else ""),
                        e["mudo"])]
    doc.build(story, onFirstPage=pagina, onLaterPages=pagina)
    return buf.getvalue()

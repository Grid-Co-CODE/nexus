"""Os gráficos das janelas da Visão do responsável (12/10/2026), em SVG montado no servidor: o Nexus não usa biblioteca
de gráfico (ver `performance/clima/irradiacao.py`). Puro: recebe o dia a dia e devolve a geometria que o template desenha.

Levi, 12/10/2026, sobre a janela do PR: "essa mesma visão do PAINEL NOC > HISTÓRICO > PR > PR DIÁRIO EXPANDIDO PORÉM UMA
MELHORIA quero que ao invés de uma barra de geração e outra barra de POA em baixo deve ter as barras de geração e uma
linha de POA seguindo a geração e logo abaixo o gráfico de curva do PR!". Então: um gráfico com as barras da geração do
dia (a cor pela meta do dia, a régua do Gerencial: 97% ou mais ok, de 90% a 97% atenção, abaixo de 90% crítico), a meta
do dia tracejada e a linha do POA no eixo da direita (com a meta de POA tracejada); embaixo, a curva do PR com a meta. Os
dois gráficos têm a mesma largura e o mesmo eixo dos dias, um embaixo do outro (o dia 7 de cima é o dia 7 de baixo).
"""
import math

W, H = 760, 250
ESQ, TOPO, DIR, BAIXO = 54, 18, 54, 28        # as margens: os eixos da esquerda e da direita e os dias embaixo
META_NA_META, META_ATENCAO = 0.97, 0.90       # a régua do Gerencial (atingimento do dia)


def _topo(vmax: float, minimo: float = 0) -> tuple[float, list[float]]:
    """O topo do eixo e as marcas: o passo "redondo" (1, 2, 2,5 ou 5 × 10^k) que dá umas 5 marcas, e o topo no 1º
    múltiplo dele acima do maior valor (com 12% de folga para o rótulo da barra): PR de 105% vai a 125%, não a 200%."""
    v = max(vmax * 1.12, minimo, 1e-9)
    bruto = v / 5
    p = 10 ** math.floor(math.log10(bruto))
    passo = next(m * p for m in (1, 2, 2.5, 5, 10) if m * p >= bruto)
    n = max(1, math.ceil(v / passo - 1e-9))
    return passo * n, [round(passo * i, 6) for i in range(n + 1)]


def _num(v, casas=1) -> str:
    if v is None:
        return "—"
    s = f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s


def _x(dia: int, dias_mes: int) -> float:
    banda = (W - ESQ - DIR) / dias_mes
    return ESQ + banda * (dia - 0.5)


def _y(v: float, topo: float) -> float:
    return TOPO + (H - TOPO - BAIXO) * (1 - (v or 0) / topo) if topo else H - BAIXO


def _segmentos(pontos: list[tuple[int, float | None]], dias_mes: int, topo: float) -> list[str]:
    """Os trechos da linha ("x,y x,y ..."): dia sem valor quebra a linha (não liga o que não foi medido)."""
    trechos, atual = [], []
    for dia, v in pontos:
        if v is None:
            if len(atual) > 1:
                trechos.append(" ".join(atual))
            atual = []
            continue
        atual.append(f"{_x(dia, dias_mes):.1f},{_y(v, topo):.1f}")
    if len(atual) > 1:
        trechos.append(" ".join(atual))
    return trechos


def _cls_dia(ger, meta) -> str:
    if ger is None or not meta:
        return "neutro"
    r = ger / meta
    return "ok" if r >= META_NA_META else ("alerta" if r >= META_ATENCAO else "critico")


def geracao(dias: list[dict], dias_mes: int) -> dict:
    """Barras da geração do dia (MWh), a meta do dia tracejada, a linha do POA (kWh/m², eixo da direita) e a meta de POA.
    `dias` = [{dia, geracao_kwh, meta_kwh, ipoa, ipoa_meta, pr, pr_meta}]."""
    mwh = [(d["dia"], None if d.get("geracao_kwh") is None else d["geracao_kwh"] / 1000) for d in dias]
    meta = next((d["meta_kwh"] / 1000 for d in dias if d.get("meta_kwh")), None)
    poa = [(d["dia"], d.get("ipoa")) for d in dias]
    meta_poa = next((d["ipoa_meta"] for d in dias if d.get("ipoa_meta")), None)
    topo, marcas = _topo(max([v for _d, v in mwh if v is not None] + [meta or 0]))
    topo_poa, marcas_poa = _topo(max([v for _d, v in poa if v is not None] + [meta_poa or 0]))
    banda = (W - ESQ - DIR) / dias_mes
    larg = banda * 0.62
    barras = []
    for d in dias:
        v = None if d.get("geracao_kwh") is None else d["geracao_kwh"] / 1000
        if v is None:
            continue
        cx, y = _x(d["dia"], dias_mes), _y(v, topo)
        pct = f" · {round(100 * v / meta)}% da meta" if meta else ""
        barras.append({"x": round(cx - larg / 2, 1), "y": round(y, 1), "w": round(larg, 1),
                       "h": round(max(H - BAIXO - y, 0.5), 1), "cls": _cls_dia(v, meta),
                       "rotulo": _num(v), "rx": round(cx, 1), "ry": round(y - 4, 1)})
    colunas = [{"x": round(ESQ + banda * (d["dia"] - 1), 1), "w": round(banda, 1),
                "dica": f"Dia {d['dia']}: geração {_num(None if d.get('geracao_kwh') is None else d['geracao_kwh'] / 1000)} MWh"
                        + (f" (meta {_num(meta)} MWh, {round(100 * d['geracao_kwh'] / 1000 / meta)}%)"
                           if meta and d.get("geracao_kwh") is not None else "")
                        + f" · POA {_num(d.get('ipoa'), 2)} kWh/m²"} for d in dias]
    return {"viewbox": f"0 0 {W} {H}", "base": H - BAIXO, "esq": ESQ, "dir": W - DIR, "barras": barras,
            "colunas": colunas, "poa": _segmentos(poa, dias_mes, topo_poa),
            "poa_pontos": [{"x": round(_x(d, dias_mes), 1), "y": round(_y(v, topo_poa), 1)} for d, v in poa if v is not None],
            "meta_y": round(_y(meta, topo), 1) if meta else None, "meta": _num(meta),
            "meta_poa_y": round(_y(meta_poa, topo_poa), 1) if meta_poa else None, "meta_poa": _num(meta_poa, 2),
            "grades": [{"y": round(_y(m, topo), 1), "rotulo": _num(m, 0 if topo >= 10 else 1)} for m in marcas],
            "grades_dir": [{"y": round(_y(m, topo_poa), 1), "rotulo": _num(m, 0 if topo_poa >= 10 else 1)} for m in marcas_poa],
            "dias": [{"x": round(_x(d, dias_mes), 1), "rotulo": str(d)} for d in range(1, dias_mes + 1)
                     if dias_mes <= 16 or d % 2 == 1 or d == dias_mes]}


def pr(dias: list[dict], dias_mes: int) -> dict:
    """A curva do PR do dia (%), com a área embaixo e a meta de PR tracejada; dia sem PR quebra a curva."""
    pts = [(d["dia"], d.get("pr")) for d in dias]
    meta = next((d["pr_meta"] for d in dias if d.get("pr_meta")), None)
    topo, marcas = _topo(max([v for _d, v in pts if v is not None] + [meta or 0]), minimo=100)
    validos = [(d, v) for d, v in pts if v is not None]
    area = []
    for trecho in _segmentos(pts, dias_mes, topo):
        xs = [p.split(",")[0] for p in trecho.split(" ")]
        area.append(f"{xs[0]},{H - BAIXO} {trecho} {xs[-1]},{H - BAIXO}")
    banda = (W - ESQ - DIR) / dias_mes
    return {"viewbox": f"0 0 {W} {H}", "base": H - BAIXO, "esq": ESQ, "dir": W - DIR,
            "linha": _segmentos(pts, dias_mes, topo), "area": area,
            "pontos": [{"x": round(_x(d, dias_mes), 1), "y": round(_y(v, topo), 1), "rotulo": f"{_num(v)}%",
                        "cls": "ok" if meta is None or v >= meta else "alerta"} for d, v in validos],
            "colunas": [{"x": round(ESQ + banda * (d - 1), 1), "w": round(banda, 1),
                         "dica": f"Dia {d}: PR {_num(v)}%" + (f" (meta {_num(meta)}%)" if meta else "")}
                        for d, v in validos],
            "meta_y": round(_y(meta, topo), 1) if meta else None, "meta": _num(meta),
            "grades": [{"y": round(_y(m, topo), 1), "rotulo": f"{_num(m, 0)}%"} for m in marcas],
            "dias": [{"x": round(_x(d, dias_mes), 1), "rotulo": str(d)} for d in range(1, dias_mes + 1)
                     if dias_mes <= 16 or d % 2 == 1 or d == dias_mes]}

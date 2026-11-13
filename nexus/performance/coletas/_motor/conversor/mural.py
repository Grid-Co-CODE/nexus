# -*- coding: utf-8 -*-
"""Mural de inversores com BAIXA PERFORMANCE (Levi, 13/11/2026: "um mural de inversores com baixa performance... em
relação aos demais, né? A média ali é 100%... 70 para baixo").

A régua, por usina e por dia, com o que está gravado no BD (BD_Performance e BD_Thopen):
- cada inversor com geração > 0 é comparado com a MÉDIA DOS DEMAIS inversores da mesma usina no mesmo dia (= 100%);
- em kWh/kWp quando todos os inversores do dia têm a "Potência (kWp)" na aba Equipamentos do BD_Performance (inversor
  menor gera menos e não é defeito: na Cascavel o 1.1 tem metade da potência dos outros); sem a potência de algum, em kWh;
- fica no mural o que der 70% ou menos (`LIMIAR`), com pelo menos 2 outros inversores gerando no dia para comparar.
Inversor zerado ou vazio não entra aqui: é furo de coleta ou parada, e já aparece nas outras abas dos Furos.
"""
import datetime as dt
import os
import re
import shutil
import tempfile
from collections import defaultdict

LIMIAR = 0.70
MIN_DEMAIS = 2
_CACHE = {}


def _equip(nome):
    return re.sub(r"(\d),(\d)", r"\1.\2", str(nome or "").strip())      # "Inversor 6,2" (Cascavel) = "Inversor 6.2"


def potencias(caminho_bd_perf):
    """{usina do BD: {"Inversor 1.1": kWp}} da aba Equipamentos do BD_Performance."""
    if not caminho_bd_perf or not os.path.isfile(caminho_bd_perf):
        return {}
    import openpyxl
    tmp = os.path.join(tempfile.gettempdir(), "conversor_potencias.xlsx")
    shutil.copy2(caminho_bd_perf, tmp)
    out = defaultdict(dict)
    wb = openpyxl.load_workbook(tmp, read_only=True, data_only=True)
    try:
        if "Equipamentos" not in wb.sheetnames:
            return {}
        linhas = wb["Equipamentos"].iter_rows(values_only=True)
        cab = None
        for r in linhas:
            s = [str(c).strip() if c is not None else "" for c in r]
            if "Usina" in s and "Equipamento" in s and "Potência (kWp)" in s:
                cab = {n: i for i, n in enumerate(s)}
                break
        if cab is None:
            return {}
        for r in linhas:
            u, e, k = r[cab["Usina"]], r[cab["Equipamento"]], r[cab["Potência (kWp)"]]
            if u and e and isinstance(k, (int, float)) and not isinstance(k, bool) and k > 0:
                out[str(u).strip()][_equip(e)] = float(k)
    finally:
        wb.close()
    return dict(out)


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def calcular(bds, kwp, ini, fim, limiar=LIMIAR):
    """bds: {destino: nucleo.BD}. Devolve as linhas do mural, uma por inversor com dia(s) em `limiar` ou menos."""
    achados = defaultdict(list)          # (destino, usina, inversor) -> [(dia, razão)]
    base = {}
    comparados = defaultdict(int)        # dias em que o inversor entrou na comparação
    for destino, bd in bds.items():
        for nome in bd.abas():
            ab = bd.aba(nome)
            if not ab:
                continue
            cols = [(h, ab.cab.index(h)) for h in ab.colunas_inversor()]
            if len(cols) <= MIN_DEMAIS:
                continue
            kw = kwp.get(nome, {})
            for d in sorted(x for x in ab.datas if ini <= x <= fim):
                vals = {}
                for h, j in cols:
                    v = _num(ab.valor(d, j))
                    if v is not None and v > 0:
                        vals[h] = v
                if len(vals) <= MIN_DEMAIS:
                    continue
                usa_kwp = all(kw.get(_equip(h)) for h in vals)
                esp = {h: (v / kw[_equip(h)] if usa_kwp else v) for h, v in vals.items()}
                tot, n = sum(esp.values()), len(esp)
                for h, e in esp.items():
                    media = (tot - e) / (n - 1)
                    if media <= 0:
                        continue
                    k = (destino, nome, h)
                    comparados[k] += 1
                    base[k] = "kWh/kWp" if usa_kwp else "kWh"
                    r = e / media
                    if r <= limiar:
                        achados[k].append((d, round(r, 3)))
    linhas = []
    for (destino, usina, inv), dias in achados.items():
        rs = [r for _, r in dias]
        linhas.append({"fonte": destino, "usina": usina, "inversor": inv, "base": base[(destino, usina, inv)],
                       "dias": [[d.isoformat(), r] for d, r in dias], "n": len(dias),
                       "comparados": comparados[(destino, usina, inv)],
                       "pior": min(rs), "media": round(sum(rs) / len(rs), 3), "ultimo": dias[-1][0].isoformat()})
    linhas.sort(key=lambda x: (-x["n"], x["pior"], x["usina"], x["inversor"]))
    return linhas


def mural(bds, caminho_bd_perf, mes, hoje=None):
    """O mural do mês ("AAAA-MM") até ontem, com cache pela hora de leitura dos BDs."""
    hoje = hoje or dt.date.today()
    a, m = (int(x) for x in mes.split("-"))
    ini = dt.date(a, m, 1)
    fim = min((dt.date(a + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)), hoje - dt.timedelta(days=1))
    chave = (mes, tuple(sorted((k, str(getattr(b, "lido_em", ""))) for k, b in bds.items())), caminho_bd_perf)
    if chave not in _CACHE:
        _CACHE.clear()
        _CACHE[chave] = calcular(bds, potencias(caminho_bd_perf), ini, fim)
    return {"linhas": _CACHE[chave], "limiar": LIMIAR, "ini": ini.isoformat(), "fim": fim.isoformat()}

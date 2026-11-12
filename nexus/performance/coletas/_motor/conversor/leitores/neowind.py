# -*- coding: utf-8 -*-
"""Cascavel (Sunpower) -> BD_Performance, aba 'Cascavel (Sunpower)'. Dois portais, três formatos (29/10/2026):

- NeoWind, relatório do MÊS ("Sunpower N(NeoWind) - 2026-10.xls"): "Sunpower N Monthly Report", o mês ("2026-10") e,
  em "Inverter Daily Data", um bloco por inversor: "Device SN:XXX(XXX)", a linha "Date" com os dias 1..31 e a linha
  "Daily Production(kWh)" com o kWh de cada dia em texto ("142.20"; dia sem dado = ""). É o que se cola.
- NeoWind, relatório do ANO ("... - 2026.xls"): "Sunpower N Year Report", "Inverter Monthly Data", geração por MÊS.
  Não serve para colar dia a dia: é reconhecido e recusado com aviso.
- "Inverter History Report" (outro portal; título "Inverter_Report_2026-10_Report"): "Inverter SN:...",
  "Datalogger SN:...", "Plant:Sun Power UFV N" e a tabela "Inverter SN | Number | Time | Today Yield(kWh) | ...". O
  .xls traz uma aba por inversor (8 abas: UFV 2, 5 e 6); o .csv traz um inversor só, com ";" e vírgula decimal.

Os .xls dos dois portais são BIFF de verdade (xlrd do núcleo abre; nenhum dos 17 de exemplo era HTML disfarçado). A
conversão .xlsx feita no Excel também é lida.

De-para por S/N — "SunPower, se localiza pela geração!" (Levi, 29/10/2026): os 7 do NeoWind bateram 175/175 dias em
01-25/10 e a geração de ago e set ao kWh; o 181201123B140125 (4.2) 25/25 em outubro. Os quatro da UFV 5 e 6 foram
achados em 10/11/2026 nas outras abas do mesmo History Report: 25/25 dias de 01-25/10 iguais ao BD, e nenhum outro
inversor da aba bate mais de 1 dia. O 6,2 apareceu no History Report de 12/11/2026 (S/N 118222226050049, aba
própria): 11/11 dias de 29/10 a 08/11 iguais ao 6,2 que a equipe tinha colado de outra fonte, e nenhuma outra coluna
bate em dia nenhum.

Não usa nucleo.num() para o kWh: o NeoWind escreve "1186797.5" e o History .csv "331,4"; num() leria um "1.234" de
três casas como milhar. Dia sem número no arquivo não vira célula (nada de 0 deduzido). O portal não diz a hora em que
o relatório foi gerado: o dia em que o arquivo foi baixado (data de modificação) fica de fora, porque podia estar aberto
— o núcleo só tira o dia de hoje, e o relatório baixado às 10h de 30/10 e convertido em 05/11 traria o 30/10 pela metade.
"""
import datetime as dt
import os
import re

from conversor.nucleo import BD_PERFORMANCE, Celula, Leitor, Reconhecimento, br, data_de, norm

ABA = "Cascavel (Sunpower)"
SN_COLUNA = {
    "YHB9949004": "Inversor 1.1",        # Sunpower 1 (NeoWind)
    "GCD0844005": "Inversor 1.2",        # Sunpower 1
    "QEE1A02011": "Inversor 2.1",        # Sunpower 2
    "ZPEAB04003": "Inversor 2.2",        # Sunpower 2
    "QEE1A0200F": "Inversor 3.1",        # Sunpower 3
    "ZVE7A4300R": "Inversor 3.2",        # Sunpower 3
    "QEE1A02016": "Inversor 4.1",        # Sunpower 4
    "181201123B140125": "Inversor 4.2",  # Sun Power UFV 2 (History Report)
    "11022221B090460": "Inversor 5.1",   # Sun Power UFV 5 (History Report, achado em 10/11/2026)
    "11022221B090461": "Inversor 5.2",   # Sun Power UFV 5
    "110162214080035": "Inversor 6.1",   # Sun Power UFV 6
    "1103D221B090006": "Inversor 6.3",   # Sun Power UFV 6
    "118222226050049": "Inversor 6.2",   # Sun Power UFV 6 (achado em 12/11/2026; no BD a coluna é "Inversor 6,2")
}
SN_FORA = {                              # aparecem nos relatórios e ficam de fora de propósito
    "GFD9942009": "parou em abril/2026; o 1.2 é o GCD0844005",
    "QEE1A02019": "vem 0 o ano todo; o 2.2 é o ZPEAB04003",
}


def _txt(v):
    return "" if v is None else str(v).strip()


def _kwh(v, decimal=None):
    """kWh de célula ou texto. decimal ',' (History .csv) ou '.'; sem dizer, decide pelo próprio texto."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = _txt(v).replace("\xa0", "").replace(" ", "")
    if decimal == ",":
        s = s.replace(".", "").replace(",", ".")
    elif decimal == ".":
        s = s.replace(",", "")
    elif "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    else:
        s = s.replace(",", ".")
    return float(s) if re.fullmatch(r"-?\d+(\.\d+)?", s) else None


def _sn(s):
    return re.sub(r"[^0-9A-Za-z]", "", s).upper()


def _dia(y, m, d):
    try:
        return dt.date(y, m, d)
    except (TypeError, ValueError):
        return None


def _inteiro(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)) and float(v).is_integer():
        return int(v)
    return int(v) if isinstance(v, str) and v.strip().isdigit() else None


def _neowind(linhas):
    """Relatório do NeoWind (mês ou ano) de uma aba: dict ou None."""
    titulo = tipo = None
    for r in linhas[:6]:
        n = norm(r[0] if r else "")
        if n.endswith("monthly report"):
            titulo, tipo = _txt(r[0]), "mes"
        elif n.endswith("year report"):
            titulo, tipo = _txt(r[0]), "ano"
        if titulo:
            break
    if not titulo:
        return None
    secao = "inverter daily data" if tipo == "mes" else "inverter monthly data"
    if not any(norm(r[0] if r else "") == secao for r in linhas):
        return None
    ym, series, sn, dias, na_secao = None, {}, None, None, False
    for r in linhas:
        c0 = r[0] if r else None
        n0 = norm(c0)
        if ym is None and tipo == "mes":
            if isinstance(c0, (dt.datetime, dt.date)):        # o Excel pode ter virado "2026-10" em data
                ym = (c0.year, c0.month)
            else:
                m = re.fullmatch(r"(\d{4})-(\d{1,2})", _txt(c0))
                ym = (int(m.group(1)), int(m.group(2))) if m else None
        if n0 == secao:
            na_secao = True
            continue
        if not na_secao:
            continue
        if n0.endswith(" data"):                              # "Storage Daily Data", "Wit Daily Data": acabou
            break
        m = re.match(r"device sn\s*:\s*([0-9a-z]+)", n0)
        if m:
            sn, dias = _sn(m.group(1)), None
            series.setdefault(sn, {})
            continue
        if sn and n0 in ("date", "month"):
            dias = {j: _inteiro(x) for j, x in enumerate(r) if j and _inteiro(x)}
            continue
        if sn and dias and tipo == "mes" and n0.startswith("daily production") and ym:
            for j, k in dias.items():
                v = _kwh(r[j], ".") if j < len(r) else None
                d = _dia(ym[0], ym[1], k)
                if v is not None and d:
                    series[sn][d] = v
    if tipo == "mes" and not ym:
        return None
    return {"tipo": tipo, "titulo": titulo, "mes": ym, "series": series, "plantas": {s: titulo for s in series},
            "avisos": []}


def _historico(linhas):
    """Uma aba (ou o .csv) do Inverter History Report: dict ou None."""
    ym, sn_cab, planta, ih = None, None, "", None
    for i, r in enumerate(linhas[:12]):
        for x in r:
            n = norm(x)
            m = re.match(r"inverter_report_(\d{4})-(\d{1,2})", n)
            if m:
                ym = (int(m.group(1)), int(m.group(2)))
            m = re.match(r"inverter sn\s*:\s*([0-9a-z]+)", n)
            if m:
                sn_cab = _sn(m.group(1))
            if n.startswith("plant:"):
                planta = _txt(x).split(":", 1)[1].strip()
        h = [norm(x) for x in r]
        if "time" in h and any(x.startswith("today yield") for x in h):
            ih = i
            break
    if ih is None or not sn_cab:
        return None
    h = [norm(x) for x in linhas[ih]]
    jt = h.index("time")
    jy = next(j for j, x in enumerate(h) if x.startswith("today yield"))
    js = h.index("inverter sn") if "inverter sn" in h else None
    dados = [r for r in linhas[ih + 1:] if r and any(_txt(x) for x in r)]
    decimal = "," if any("," in _txt(r[jy]) for r in dados if jy < len(r) and isinstance(r[jy], str)) else None
    series, avisos = {}, []
    for r in dados:
        sn = _sn(_txt(r[js])) if js is not None and js < len(r) and _txt(r[js]) else sn_cab
        d = data_de(r[jt]) if jt < len(r) else None
        if d and ym and (d.year, d.month) != ym:
            # "10/01/2026" num relatório de outubro: o portal escreveu mês/dia
            d2 = _dia(d.year, d.day, d.month)
            if d2 and (d2.year, d2.month) == ym:
                d = d2
            else:
                avisos.append("%s: a data %r não é do mês do relatório (%02d/%d) — ficou de fora"
                              % (sn, _txt(r[jt]), ym[1], ym[0]))
                continue
        v = _kwh(r[jy], decimal) if jy < len(r) else None
        if d and v is not None:
            series.setdefault(sn, {})[d] = v
    series.setdefault(sn_cab, {})
    return {"tipo": "historico", "titulo": "Inverter History Report", "mes": ym, "series": series,
            "plantas": {s: planta for s in series}, "avisos": avisos}


def interpretar(planilhas):
    """[(nome da aba, linhas)] -> {'tipo': 'mes'|'ano'|'historico', 'titulo', 'mes', 'series': {S/N: {date: kWh}},
    'plantas': {S/N: planta}, 'avisos'} ou None se não for nenhum dos três formatos."""
    achados = []
    for _, linhas in planilhas:
        x = _neowind(linhas) or _historico(linhas)
        if x:
            achados.append(x)
    if not achados:
        return None
    tipo = achados[0]["tipo"]
    out = {"tipo": tipo, "titulo": achados[0]["titulo"], "mes": achados[0]["mes"], "series": {}, "plantas": {},
           "avisos": []}
    for x in achados:
        if x["tipo"] != tipo:
            continue
        for sn, s in x["series"].items():
            out["series"].setdefault(sn, {}).update(s)
            out["plantas"].setdefault(sn, x["plantas"].get(sn, ""))
        out["avisos"] += x["avisos"]
    return out


def _eh_cascavel(rel):
    """S/N conhecido ou planta "Sunpower"/"Sun Power" — outro cliente no mesmo portal não é pego por este leitor."""
    if any(sn in SN_COLUNA or sn in SN_FORA for sn in rel["series"]):
        return True
    nomes = [rel["titulo"]] + list(rel["plantas"].values())
    return any("sunpower" in norm(n).replace(" ", "") for n in nomes)


def _dia_baixado(arq):
    try:
        return dt.date.fromtimestamp(os.path.getmtime(arq.caminho))
    except (OSError, ValueError):
        return None


class NeoWindCascavel(Leitor):
    id = "neowind"
    fonte = "Cascavel (Sunpower): NeoWind / Inverter History"
    destino = BD_PERFORMANCE

    def reconhecer(self, arq, ctx):
        try:
            if arq.ext in (".csv", ".txt"):
                # CSV grande de outra fonte não pode ser lido inteiro só para dizer "não é meu"
                if not any(norm(l).startswith(("inverter_report_", "inverter sn:")) for l in arq.cabeca(10)):
                    return None
            elif arq.ext not in (".xls", ".xlsx", ".xlsm"):
                return None
            rel = interpretar(arq.planilhas())
        except Exception:                        # arquivo de outro formato não pode derrubar a tela
            return None
        if not rel or not _eh_cascavel(rel):
            return None
        if rel["tipo"] == "ano":
            return Reconhecimento(self.fonte, estado=rel,
                                  detalhe="Relatório do ANO (geração por mês): não serve; baixe o do mês",
                                  recusa="Relatório do ANO da NeoWind (geração por mês) não serve para colar dia a "
                                         "dia — baixe o relatório do MÊS (\"... - AAAA-MM.xls\").")
        com_dado = {sn: s for sn, s in rel["series"].items() if s}
        cols = sorted({SN_COLUNA[sn] for sn in com_dado if sn in SN_COLUNA})
        dias = [d for sn, s in com_dado.items() if sn in SN_COLUNA for d in s]
        qual = ("Relatório do mês %02d/%d" % (rel["mes"][1], rel["mes"][0]) if rel["tipo"] == "mes"
                else "Inverter History Report")
        rec = Reconhecimento(self.fonte, usinas=[ABA] if cols else [], estado=rel,
                             periodo=(min(dias), max(dias)) if dias else None,
                             detalhe="%s · %s" % (qual, ", ".join(cols) if cols else "nenhum S/N com dado no de-para"))
        return rec

    def ler(self, arq, ctx, rec, escolha=None):
        rel = rec.estado
        if rel["tipo"] == "ano":
            return [], ["relatório do ano não serve; baixe o do mês (\"... - AAAA-MM.xls\"): o do ano traz a geração "
                        "por mês, não por dia"]
        avisos = list(rel["avisos"])
        baixado = _dia_baixado(arq)
        cel, aberto = [], set()
        for sn, serie in sorted(rel["series"].items()):
            if not serie:
                continue
            col = SN_COLUNA.get(sn)
            if not col:
                if sn in SN_FORA:
                    avisos.append("S/N %s ficou de fora (%s), mas trouxe %d dia(s) — confira" % (sn, SN_FORA[sn],
                                                                                              len(serie)))
                else:
                    planta = rel["plantas"].get(sn)
                    avisos.append("S/N %s%s com %d dia(s) não está no de-para da Cascavel (Sunpower) — ficou de fora; "
                                  "o de-para se acha pela geração" % (sn, " (%s)" % planta if planta else "",
                                                                       len(serie)))
                continue
            for d, v in sorted(serie.items()):
                if d == baixado:
                    aberto.add(d)
                    continue
                cel.append(Celula(BD_PERFORMANCE, ABA, d, col, v))
        if aberto:
            avisos.append("%s ficou de fora: o arquivo foi baixado nesse dia e o portal não diz a hora — o dia podia "
                          "estar aberto" % ", ".join(br(d) for d in sorted(aberto)))
        return cel, avisos


LEITORES = [NeoWindCascavel]

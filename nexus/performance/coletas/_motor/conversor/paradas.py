# -*- coding: utf-8 -*-
"""Paradas registradas (COS + Fracttal) para explicar furo e baixa performance (Levi, 13/11/2026: "pegue essa falha de
energia, essa indisponibilidade, bata com o coletor... o inversor passa o dia desligado, ou teve 60% a menos de
disponibilidade, então é normal que ele tenha uma baixa performance... baixas performances não explicadas pelo
acompanhamento do COS ou da disponibilidade, que devem ser consideradas").

De onde vem: o banco aberto (`app.gridco.com.br/db_performace`, leitura sem login), livro `falhas_performance` que a
plataforma publica com a régua da disponibilidade (plataforma/disponibilidade.py):
- `disponibilidade_os_dia`: OS ou ocorrência do COS × usina × dia, com o ESCOPO ("Usina inteira", "Cabine N",
  "Inversor N.M"), os trechos parados na janela solar ("06:00-07:56") e as horas perdidas; fonte "cos" ou "fracttal";
- `disponibilidade_os`: as OS, com `aberta` = "sim" para as que seguem abertas (inversor parado há meses: Vertentes 1.8
  desde 24/05, Santarém 2 2.7 desde 12/07 — exatamente os inversores que aparecem vazios todo dia nos Furos).
Sem rede, o app segue sem a explicação (nada quebra).
"""
import datetime as dt
import json
import re
import time
import urllib.request

BASE = "https://app.gridco.com.br/db_performace"
SOL_INI, SOL_FIM = 6 * 60, 18 * 60              # janela solar da régua da disponibilidade
_CACHE = {"t": 0, "dados": None}
VALIDADE_S = 30 * 60


def _get(rota):
    with urllib.request.urlopen(BASE + rota, timeout=60) as r:
        return json.load(r)


def _linhas(sheet_id):
    out, off = [], 0
    while True:
        r = _get("/api/sheets/%d/rows?limit=1000&offset=%d" % (sheet_id, off))
        out += r.get("rows") or []
        if len(r.get("rows") or []) < 1000:
            return out
        off += 1000


def _dicts(rows):
    if not rows:
        return []
    cab = rows[0].get("headers") or []
    return [dict(zip(cab, x.get("values") or [])) for x in rows]


def _min(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def trechos(txt):
    """'06:00-07:56; 09:27-11:13' -> [(360, 476), (567, 673)] na janela solar."""
    out = []
    for a, b in re.findall(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", str(txt or "")):
        i, f = max(_min(a), SOL_INI), min(_min(b), SOL_FIM)
        if f > i:
            out.append((i, f))
    return out


def eq_norm(nome):
    return re.sub(r"(\d),(\d)", r"\1.\2", str(nome or "").strip()).lower()


def cobre(escopo, inversor):
    """O escopo da parada cobre o inversor? Usina inteira cobre todos; "Cabine N"/"SKID N"/"UG N" cobre os N.x;
    "Inversor N.M" só ele."""
    e, inv = eq_norm(escopo), eq_norm(inversor)
    if not e or e.startswith("usina"):
        return True
    m = re.match(r"(?:cabine|skid|ug)\s*0*(\d+)", e)
    if m:
        n = re.match(r"inversor\s*(\d+)\.", inv)
        return bool(n) and n.group(1) == m.group(1)
    return e == inv


def carregar(forcar=False):
    """{"dia": {usina: {"AAAA-MM-DD": [parada...]}}, "abertas": {usina: [parada...]}, "erro": None}."""
    if not forcar and _CACHE["dados"] is not None and time.time() - _CACHE["t"] < VALIDADE_S:
        return _CACHE["dados"]
    dados = {"dia": {}, "abertas": {}, "erro": None, "lido": dt.datetime.now().strftime("%d/%m %H:%M")}
    try:
        ids = {s["sheet_name"]: s["id"] for s in _get("/api/sheets") if s.get("workbook_key") == "falhas_performance"}
        for r in _dicts(_linhas(ids["disponibilidade_os_dia"])):
            u, d = str(r.get("usina") or "").strip(), str(r.get("dia") or "")[:10]
            if not u or not d:
                continue
            dados["dia"].setdefault(u, {}).setdefault(d, []).append({
                "os": str(r.get("os") or ""), "tipo": r.get("tipo") or "", "fonte": r.get("fonte") or "",
                "escopo": r.get("escopo") or "Usina inteira", "trechos": r.get("trechos") or "",
                "aberta": str(r.get("aberta") or "").lower() == "sim"})
        if "disponibilidade_os" in ids:
            vistas = set()
            for r in _dicts(_linhas(ids["disponibilidade_os"])):
                if str(r.get("aberta") or "").lower() != "sim":
                    continue
                u = str(r.get("usina") or "").strip()
                if (u, str(r.get("os")), r.get("escopo")) in vistas:
                    continue                    # a OS aberta repete em cada mês que atravessa
                vistas.add((u, str(r.get("os")), r.get("escopo")))
                dados["abertas"].setdefault(u, []).append({
                    "os": str(r.get("os") or ""), "tipo": r.get("tipo") or "", "escopo": r.get("escopo") or "",
                    "inicio": str(r.get("inicio") or "")[:10]})
    except Exception as e:                      # sem rede/sem o livro: segue sem explicação
        dados["erro"] = "%s: %s" % (type(e).__name__, e)
    _CACHE.update(t=time.time(), dados=dados)
    return dados


def nome_os(os_):
    """Ocorrência do COS ainda sem OS vem com número negativo (Ipixuna 2 Inv 2.2, 29/10/2026: "-3280300568")."""
    return "ocorrência do COS" if str(os_ or "").startswith("-") else "OS %s" % os_


def usina_inteira(escopo):
    return not str(escopo or "").strip() or eq_norm(escopo).startswith("usina")


def minutos_parados(dados, usina, dia, inversor, sem_usina_inteira=False):
    """Minutos da janela solar (06-18) em que alguma parada do dia cobre o inversor (união dos trechos) e as OS.
    `sem_usina_inteira`: só paradas de parte da usina (cabine, SKID, inversor) — é o que explica um inversor ABAIXO dos
    demais; a parada da usina inteira derruba todos por igual (Xavantina 1, 10-11/11/2026: OS da usina inteira o dia
    todo e o 2.3 em 65% dos outros)."""
    iv, oss = [], []
    for p in (dados.get("dia") or {}).get(usina, {}).get(dia, []):
        if sem_usina_inteira and usina_inteira(p["escopo"]):
            continue
        if cobre(p["escopo"], inversor):
            iv += trechos(p["trechos"])
            oss.append(p)
    tot, ca, cb = 0, None, None
    for a, b in sorted(iv):                     # união dos trechos (COS e Fracttal se sobrepõem no mesmo evento)
        if cb is None or a > cb:
            if cb is not None:
                tot += cb - ca
            ca, cb = a, b
        else:
            cb = max(cb, b)
    if cb is not None:
        tot += cb - ca
    return tot, oss


def aberta(dados, usina, inversor, dia=None):
    """A OS aberta que cobre o inversor (e que já tinha começado no dia), ou None."""
    for p in (dados.get("abertas") or {}).get(usina, []):
        if usina_inteira(p["escopo"]):
            continue                            # usina inteira parada é furo do dia todo, não inversor inoperante
        if cobre(p["escopo"], inversor) and (not dia or not p["inicio"] or p["inicio"] <= dia):
            return p
    return None

"""Os expurgos do contrato na nota de cumprimento (22/11/2026): o que o contrato tira da conta, e quanto isso mexe na nota.

Levi, 19/11/2026: "una as informações de contrato, enfim, Nexus Insights, e aí aplique esses expurgos que estão no
relatório"; a ordem combinada foi 1) o cadastro das limitações de potência (Performance › Limitações), 2) o cálculo dos
expurgos na nota do contrato (este módulo) e 3) o cruzamento com a planilha de tickets. Em 22/11: "agora segue com o
cálculo dos expurgos".

A decisão (a "opção A"): CADA CONTRATO diz o que expurga, pela própria cláusula de exclusão que o Comando › Contratos leu
(e que o gestor edita lá). A lista da Grid são as cinco categorias de `CATEGORIAS`, as que aparecem no modelo de proposta
da Grid (o "Saem do tempo planejado" da 8.3.3/9.3.3) e nos contratos dos clientes; uma categoria vale para o cliente só
se a cláusula dele a cita. Contrato sem cláusula de exclusão não expurga nada (sem dado não se inventa). A cláusula diz
também A QUE se aplica: à disponibilidade, ao PR, ou aos dois quando não diz.

O que o Nexus já registra e por isso já entra na conta:
- **rede** (queda da rede, distribuidora, transmissão, ONS): a OCORRÊNCIA DO COS com a geração parada
  (`nexus_cos_normalizacoes`, `geracao_parou` = 1) que o COS ligou a uma OS de RELIGAMENTO (a família "por queda" da
  disponibilidade da plataforma, `falhas_performance · disponibilidade_os`). Levi, 22/11/2026: "Sobre o OS de
  religamento, não. A gente vai contar como queda [...] que tá ali na parte de ocorrências do COS. [...] Lá eles ligam o
  OS, um tipo de tarefa, se for religamento remoto ou não, e se houve queda de geração. Então vai contar lá" (a 1ª versão,
  do mesmo dia, contava toda OS de religamento pelo tempo da OS). O tempo é o do COS, nas horas de sol; a OS dá a
  potência afetada (ver `rede_por_usina`). A disponibilidade do mês devolve essas horas (a mesma régua do Gerencial:
  06–18 h, 12 h por dia).
- **limitacao** (limitação de geração imposta, o curtailment): o cadastro de Performance › Limitações, só a que o time
  marcou SEM responsabilidade da Grid e com a potência nominal. A parcial e a da Grid não entram.
A ENERGIA que a geração e o PR somam: a das duas à potência nominal (a perda que a plataforma publica, kWp × horas de sol,
e kW retidos × horas de sol) vezes a GERAÇÃO MÉDIA da usina nas horas de sol do mês (geração ÷ (kWp × 12 h × dias)). À
nominal ela inflava o PR (22/11/2026, medido no dado real: a usina gera uns 20 a 30% da nominal na média das 12 h; o
relatório de Performance da Ana pondera pela irradiação do dia, que o Nexus não tem por usina). Sem a potência ou os dias
do mês, a energia não entra.
As outras três (força maior, pedido ou responsabilidade da contratante, garantia ou erro do fabricante) o Nexus ainda não
registra: a tela diz que o contrato as expurga e que elas ainda não entram.

O que o Nexus NÃO confere: os contratos pedem aviso em 24 h (Apolo), evidência por tipo de evento, protocolo na
concessionária ou validação conjunta (SEMP). A tela lista essas condições ao lado: o número com o expurgo é o que o
contrato PERMITE tirar, não o que o cliente já aceitou.

Puro: nada de rede, banco nem Flask; quem junta as fontes é `torres/comando/gerencial_tela.py`."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

CATEGORIA_REGRA = "Disponibilidade e desempenho"
# a regra de exclusão: o nome ou o texto falam em tirar da conta
_EXCLUSAO = re.compile(r"exclus|expurg|curtail|n[aã]o (incidem|contam|reduzem)|saem d|sai do tempo|deduzid", re.I)
_PR = re.compile(r"\bPR\b|performance ratio", re.I)
_DISP = re.compile(r"disponib|tempo (de opera|planejad)|\bDt\b", re.I)
# a regra que diz o que NÃO é expurgo (SEMP, "Passivos de obra NÃO são expurgo"): não vira categoria
_NEGA = re.compile(r"n[aã]o (s[aã]o|[eé]) expurg|n[aã]o isenta", re.I)
# a condição para o expurgo valer (o Nexus não confere: a tela lista)
_CONDICAO = re.compile(r"aviso|evid[eê]ncia|valida[cç][aã]o|protocolo|pedido de expurgo", re.I)

# a lista da Grid: id -> (o nome na tela, o padrão no texto da cláusula, tem dado no Nexus)
CATEGORIAS = {
    "rede": ("queda da rede",
             re.compile(r"\brede\b|distribui|concession|transmiss|\bONS\b|agentes? externos?|manobras externas|"
                        r"falta de energia|religamento|eventos externos", re.I), True),
    "limitacao": ("limitação imposta",
                  re.compile(r"curtail|limita[cç][aã]o de gera|restri[cç][aã]o de (inje|despacho)|"
                             r"restri[cç][oõ]es (por agentes|de distribuidora)|redu[cç][aã]o da rede", re.I), True),
    "forca_maior": ("força maior", re.compile(r"for[cç]a maior|caso fortuito", re.I), False),
    "contratante": ("pedido ou responsabilidade da contratante",
                    re.compile(r"(pedid|causad|solicitad)\w* (pel[ao]|d[ao]) contratante|a pedido d[ao] contratante|"
                               r"melhorias|respons\w* d[ao] contratante|a cargo d[ao] contratante|cabe [àa] contratante|"
                               r"sobressalente|interrup[cç][oõ]es programadas aprovadas", re.I), False),
    "fabricante": ("garantia ou erro do fabricante",
                   re.compile(r"garantia|fabricante|erro de projeto|deteriora|defeitos? seriais|\bEPC", re.I), False),
}
SOL_INI, SOL_FIM = 6, 18             # a janela do Gerencial: 06–18 h, 12 h por dia
_BRT = timezone(timedelta(hours=-3))


def _num(v) -> float | None:
    try:
        return None if v is None or v == "" else float(str(v).replace(",", "."))
    except ValueError:
        return None


def _br(x: float, casas: int = 1) -> str:
    return f"{x:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _lista(nomes: list[str]) -> str:
    return nomes[0] if len(nomes) == 1 else ", ".join(nomes[:-1]) + " e " + nomes[-1]


# ── o que cada contrato expurga ─────────────────────────────────────────────────────────────────────────────────────
def do_contrato(ficha: dict | None) -> dict:
    """{"cats": {id: {"alvos": ["disp"|"pr", ...], "regras": [{nome, clausula}]}}, "condicoes": [{nome, clausula}]}
    pelas regras de "Disponibilidade e desempenho" que o Comando › Contratos leu (a ficha do cliente)."""
    cats: dict[str, dict] = {}
    condicoes: list[dict] = []
    for k in (ficha or {}).get("contratos") or []:
        for r in k.get("regras") or []:
            if r.get("categoria") != CATEGORIA_REGRA:
                continue
            nome = str(r.get("nome") or "").strip()
            texto = str(r.get("vigente") or r.get("contratual") or "")
            junto = f"{nome}. {texto}"
            if not _EXCLUSAO.search(junto) or _NEGA.search(nome):
                continue
            ref = {"nome": nome, "clausula": str((r.get("ref") or {}).get("clausula") or "")}
            if _CONDICAO.search(nome):
                if ref not in condicoes:
                    condicoes.append(ref)
                continue
            alvos = [a for a, rx in (("disp", _DISP), ("pr", _PR)) if rx.search(junto)] or ["disp", "pr"]
            for cid, (_rot, rx, _tem) in CATEGORIAS.items():
                if rx.search(junto):
                    c = cats.setdefault(cid, {"alvos": [], "regras": []})
                    c["alvos"] += [a for a in alvos if a not in c["alvos"]]
                    if ref not in c["regras"]:
                        c["regras"].append(ref)
    for c in cats.values():
        c["alvos"].sort()
    return {"cats": cats, "condicoes": condicoes}


# ── a queda da rede: o tempo do COS, a potência da OS de religamento ────────────────────────────────────────────────
_OS_RE = re.compile(r"\d+")


def _quando(v):
    try:
        return datetime.fromisoformat(str(v).strip()) if v else None
    except ValueError:
        return None


def _local(v):
    """A data das OS da plataforma vem sem fuso: é a hora de Brasília."""
    d = _quando(v)
    if d and d.tzinfo is None:
        d = d.replace(tzinfo=_BRT)
    return d


def _juntar(js: list[tuple]) -> list[tuple]:
    """As janelas sobrepostas viram uma (duas ocorrências do COS da mesma OS não contam a mesma hora duas vezes)."""
    out = []
    for a, b in sorted(js):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def rede_por_usina(linhas_cos: list[dict], linhas_os: list[dict], linhas_dia: list[dict], mes: str, ini: datetime,
                   fim: datetime, uid_de) -> dict:
    """{usina_id: {h_eq, delta_disp, kwh, os, ocorrencias}} da queda da rede no mês [ini, fim).

    A queda é a OCORRÊNCIA DO COS com a geração parada (`nexus_cos_normalizacoes`, `geracao_parou` = 1; as normalizadas e
    as ainda abertas) que o COS ligou a uma OS de RELIGAMENTO (a OS ou uma das relacionadas, na família "por queda" da
    disponibilidade da plataforma, `disponibilidade_os`). O TEMPO é o do COS, do início à normalização (a aberta, até o
    fim da janela), nas horas de sol; a OS dá só a potência afetada (a maior, se forem várias) e a usina. Levi, 22/11/2026:
    "A gente vai contar como queda [...] que tá ali na parte de ocorrências do COS"; medido no mesmo dia, a OS do Fracttal
    fica aberta muito depois da volta (novembro: 3.362 h de sol pelas OS contra 1.376 h pelo COS; OS de 252 h para
    paradas de 0 a 4 h). A usina do cadastro com duas linhas no Gerencial (Aparecida do Taboado 1 e 2) é pesada pela
    potência, como a disponibilidade dela (`campo/responsaveis.disponibilidade`). `delta_disp` = os pontos percentuais que
    a disponibilidade do mês ganha sem essas horas; `kwh` = kWp afetado × horas de sol (à potência nominal, a régua da
    plataforma). SÓ SAI o tempo em que a OS estava aberta (o que a disponibilidade oficial descontou) E o COS diz que a
    geração parou: com o tempo do COS inteiro, em 22/11/2026, 47 usinas batiam 100% em novembro, porque o COS registra
    paradas mais longas que a OS em vários casos e o expurgo devolvia hora que a conta oficial nunca tirou."""
    linhas: dict[tuple, dict] = {}
    for r in linhas_dia:
        if str(r.get("mes") or "") != mes:
            continue
        k = (str(r.get("usina") or "").strip(), str(r.get("usina_fracttal") or ""))
        x = linhas.setdefault(k, {"pot": _num(r.get("pot_kwp")), "dias": set(), "h": 0.0, "kwh": 0.0, "os": [], "n": 0})
        x["dias"].add(str(r.get("dia") or ""))
    queda = {str(r.get("os") or "").strip(): r for r in linhas_os
             if str(r.get("mes") or "") == mes and str(r.get("origem") or "").strip().lower() == "queda"}
    # as janelas do COS (geração parada) de cada OS de religamento; a mesma OS em duas ocorrências junta as janelas
    janelas: dict[str, list] = {}
    ocorr: dict[str, set] = {}
    for c in linhas_cos or []:
        if str(c.get("geracao_parou") or "").strip().lower() not in ("1", "true", "sim"):
            continue
        a = _quando(c.get("inicio"))
        if not a:
            continue
        b = _quando(c.get("normalizado_em")) or fim
        chave = (str(c.get("registro") or ""), a.isoformat())
        for n in dict.fromkeys(_OS_RE.findall(f"{c.get('os') or ''} {c.get('os_relacionadas') or ''}")):
            if n in queda:
                janelas.setdefault(n, []).append((a, b))
                ocorr.setdefault(n, set()).add(chave)
    # os pedaços de cada linha do Gerencial: (início, fim, fração da usina, equipamento); só o tempo em que a OS estava
    # aberta (o que a disponibilidade descontou) E o COS diz que a geração parou
    pedacos: dict[int, list] = {}
    for n, js in janelas.items():
        o = queda[n]
        x = linhas.get((str(o.get("usina") or "").strip(), str(o.get("usina_fracttal") or "")))
        kwp = _num(o.get("kwp"))
        o_ini = _local(o.get("inicio"))
        if not x or not x["pot"] or not kwp or not o_ini:
            continue
        o_fim = _local(o.get("fim")) or fim
        equip = str(o.get("codigo_ativo") or o.get("escopo") or n).strip().lower()
        for a, b in _juntar(js):
            a2, b2 = max(a, o_ini, ini), min(b, o_fim, fim)
            if b2 > a2:
                pedacos.setdefault(id(x), []).append((a2, b2, min(1.0, kwp / x["pot"]), equip))
                if n not in x["os"]:
                    x["os"].append(n)
                x.setdefault("_ocorr", set()).update(ocorr[n])
    for x in linhas.values():
        ps = pedacos.get(id(x))
        if not ps:
            continue
        # a varredura: em cada trecho, cada equipamento conta uma vez (a maior fração) e a soma tem o teto da usina
        marcos = sorted({t0 for t0, _t1, _f, _e in ps} | {t1 for _t0, t1, _f, _e in ps})
        for t0, t1 in zip(marcos, marcos[1:]):
            por_equip: dict[str, float] = {}
            for a, b, f, e in ps:
                if a <= t0 and b >= t1:
                    por_equip[e] = max(por_equip.get(e, 0.0), f)
            if por_equip:
                x["h"] += min(1.0, sum(por_equip.values())) * horas_de_sol(t0, t1, ini, fim)
        x["kwh"] = x["h"] * x["pot"]
        x["n"] = len(x.pop("_ocorr", set()))
    por: dict[int, list] = {}
    for (nome, fracttal), x in linhas.items():
        uid = uid_de(nome, fracttal)
        if uid and x["pot"] and x["dias"]:
            por.setdefault(uid, []).append(x)
    out = {}
    for uid, xs in por.items():
        if not any(x["n"] for x in xs):
            continue
        tot = sum(x["pot"] for x in xs)
        out[uid] = {"h_eq": sum(x["pot"] * x["h"] for x in xs) / tot,
                    "delta_disp": sum(x["pot"] * 100.0 * x["h"] / (12.0 * len(x["dias"])) for x in xs) / tot,
                    "kwh": sum(x["kwh"] for x in xs), "ocorrencias": sum(x["n"] for x in xs),
                    "os": sorted({o for x in xs for o in x["os"]}, key=lambda o: (len(o), o))}
    return out


# ── a limitação imposta, pelo cadastro ──────────────────────────────────────────────────────────────────────────────
def horas_de_sol(inicio: datetime, fim: datetime, ini: datetime, fim_periodo: datetime) -> float:
    """As horas de 06 a 18 h de cada dia dentro de [inicio, fim) ∩ [ini, fim_periodo)."""
    a, b = max(inicio, ini), min(fim, fim_periodo)
    h, dia = 0.0, a.replace(hour=0, minute=0, second=0, microsecond=0)
    while dia < b:
        s, e = max(a, dia.replace(hour=SOL_INI)), min(b, dia.replace(hour=SOL_FIM))
        if e > s:
            h += (e - s).total_seconds() / 3600.0
        dia += timedelta(days=1)
    return round(h, 2)


def limitacao_por_usina(lista: list[dict], ini: datetime, fim: datetime) -> dict:
    """{usina_id: {kwh, ids, sem_potencia}} das limitações SEM responsabilidade da Grid que tocam [ini, fim); a que não
    tem a potência nominal conta em `sem_potencia` e fica fora da energia."""
    out: dict[int, dict] = {}
    for v in lista or []:
        if v.get("responsabilidade") != "nao" or not v.get("inicio"):
            continue
        o = out.setdefault(v["usina_id"], {"kwh": 0.0, "ids": [], "sem_potencia": 0})
        if v.get("kw_limitados") is None:
            o["sem_potencia"] += 1
            continue
        horas = horas_de_sol(v["inicio"], v.get("fim") or fim, ini, fim)
        if horas > 0:
            o["kwh"] += float(v["kw_limitados"]) * horas
            o["ids"].append(v["limitacao_id"])
    return {u: o for u, o in out.items() if o["ids"] or o["sem_potencia"]}


# ── a conta ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def _clausulas(cats: dict, ids: list[str]) -> str:
    regras = []
    for cid in ids:
        for r in cats[cid]["regras"]:
            if r not in regras:
                regras.append(r)
    return _lista([f"\"{r['nome']}\"" + (f" ({r['clausula']})" if r["clausula"] else "") for r in regras])


def _sem_registro(cats: dict, alvo: str) -> str:
    sem = [CATEGORIAS[c][0] for c in cats if alvo in cats[c]["alvos"] and not CATEGORIAS[c][2]]
    return f" O contrato também expurga {_lista(sem)}, mas o Nexus ainda não registra esses eventos." if sem else ""


def _condicoes(cond: list[dict]) -> str:
    if not cond:
        return ""
    return " Para valer, o contrato pede: " + _lista([r["nome"] + (f" ({r['clausula']})" if r["clausula"] else "")
                                                       for r in cond]) + "."


def aplicar(contrato: dict, m: dict, ex: dict) -> dict:
    """{"m": o mês com o expurgo, "disp": o texto do item Disponibilidade, "ger": o do item Geração e PR}. `contrato` =
    `do_contrato`; `m` = {disp, meta, pr, prod_kwh, meta_kwh, ...}; `ex` = {"rede": `rede_por_usina`[uid],
    "limitacao": `limitacao_por_usina`[uid]} da usina no mês (o que faltar, não houve)."""
    cats, novo = contrato.get("cats") or {}, dict(m)
    if not cats:
        t = "O contrato lido não traz cláusula de expurgo: nada sai da conta."
        return {"m": novo, "disp": t, "ger": t}
    cond = _condicoes(contrato.get("condicoes") or [])

    # a disponibilidade: só a queda da rede tem horas no Nexus
    d_cats = [c for c in cats if "disp" in cats[c]["alvos"]]
    rede = ex.get("rede") or {}
    if not d_cats:
        t_disp = "A cláusula de expurgo do contrato vale para o PR, não para a disponibilidade."
    elif "rede" in d_cats and rede.get("delta_disp") and m.get("disp") is not None:
        novo["disp"] = round(min(100.0, m["disp"] + rede["delta_disp"]), 2)
        n, q, oss = len(rede.get("os") or []), rede.get("ocorrencias") or 0, rede.get("os") or []
        t_disp = (f"Saem {_br(rede['h_eq'])} h de queda da rede pela potência afetada, o tempo que o COS registrou "
                  f"({q} {'ocorrência do COS' if q == 1 else 'ocorrências do COS'} com a geração parada; "
                  f"{'OS de religamento' if n == 1 else 'OS de religamento'} {', '.join(oss[:6])}{'…' if n > 6 else ''}), "
                  f"pela cláusula {_clausulas(cats, ['rede'])}. Sem o expurgo: {_br(m['disp'])}%.")
    elif "rede" in d_cats:
        t_disp = "Nenhuma queda da rede no mês: nada sai da disponibilidade."
    else:
        t_disp = "Nada que o Nexus registre sai da disponibilidade."
    t_disp += _sem_registro(cats, "disp") + (cond if d_cats else "")

    # a geração e o PR: a energia da queda da rede e da limitação imposta, à potência nominal
    p_cats = [c for c in cats if "pr" in cats[c]["alvos"]]
    lim = ex.get("limitacao") or {}
    partes = []
    if "rede" in p_cats and rede.get("kwh"):
        partes.append(("rede", rede["kwh"]))
    if "limitacao" in p_cats and lim.get("kwh"):
        partes.append(("limitacao", lim["kwh"]))
    prod, meta_kwh = _num(m.get("prod_kwh")), _num(m.get("meta_kwh"))
    pot, dias = _num(m.get("pot_kwp")), _num(m.get("dias"))
    fator = min(1.0, prod / (pot * 12.0 * dias)) if prod and pot and dias else None
    if fator is not None:
        partes = [(c, k * fator) for c, k in partes]
    if not p_cats:
        t_ger = "A cláusula de expurgo do contrato vale para a disponibilidade, não para o PR."
    elif partes and fator is None:
        t_ger = ("Sem a potência e os dias do mês (a base da geração média da usina): a energia expurgada não entra na "
                 "conta.")
    elif partes and prod and meta_kwh:
        e = sum(k for _c, k in partes)
        if m.get("meta") is not None:
            novo["meta"] = round(100.0 * (prod + e) / meta_kwh, 2)
        if m.get("pr") is not None:
            novo["pr"] = round(m["pr"] * (prod + e) / prod, 2)
        detalhe = "; ".join(f"{CATEGORIAS[c][0]}: {_br(k / 1000.0, 2)} MWh" for c, k in partes)
        sem = ([f"{_br(m['meta'])}% da meta"] if m.get("meta") is not None else []) + \
              ([f"PR de {_br(m['pr'])}%"] if m.get("pr") is not None else [])
        t_ger = (f"Somados {_br(e / 1000.0, 2)} MWh que o contrato expurga ({detalhe}), pela geração média da usina nas "
                 f"horas de sol do mês ({_br(100 * fator, 0)}% da potência nominal), pela cláusula "
                 f"{_clausulas(cats, [c for c, _k in partes])}." + (f" Sem o expurgo: {' e '.join(sem)}." if sem else ""))
    elif partes:
        t_ger = "Sem a geração e a meta do mês em kWh: a energia expurgada não entra na conta."
    else:
        t_ger = ("Nenhuma queda da rede nem limitação imposta no mês: nada se soma à geração." if
                 {"rede", "limitacao"} & set(p_cats) else "Nada que o Nexus registre se soma à geração.")
    if lim.get("sem_potencia") and "limitacao" in p_cats:
        q = lim["sem_potencia"]
        t_ger += f" {q} {'limitação' if q == 1 else 'limitações'} sem a potência nominal no cadastro: fora da conta."
    t_ger += _sem_registro(cats, "pr") + (cond if p_cats else "")
    return {"m": novo, "disp": t_disp, "ger": t_ger}

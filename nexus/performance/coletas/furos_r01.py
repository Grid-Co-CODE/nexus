# -*- coding: utf-8 -*-
"""Os furos de coleta da analista (R01) calculados pelo Nexus, a partir do banco e do COS (Levi, 16/11/2026: "upgradae para
a parte de coleta da performance no nexus", com o documento `Regras_e_Cruzamentos_Furos_Coleta_GridCo_R01.md`).

Até aqui o relatório era gerado à mão pela analista no PC (`Gerador_Furos_Coleta\\`: extract2.py, oscross.py, ocn.py,
build2.py) e subia como HTML. Este módulo é a MESMA regra, função a função, sem ler arquivo nenhum: quem chama entrega
as abas dos BDs (do banco), o Info Geral e a Base UFV, as linhas do COS no formato do CSV da tela Ocorrências e as
paradas de outubro congeladas do HTML R01. A saída é o JSON do §9.1 (`months` -> `end`, `plants` com `eqs`, `st`, `cv`,
`os`), o mesmo que a tela 3 do Conversor lê.

As regras e o caso que criou cada uma (o documento da analista, seções entre parênteses):
- célula = equipamento × dia; estados o/v/x/z/p/d/a/e/w (§4); verificação até d-2 em Brasília, sem tolerância (§3);
- o último dia de cada mês é o último com geração de QUALQUER usina; no mês de d-2, no máximo d-2 (§3);
- Ultragaz: valor acima de 5× a mediana dos positivos de setembro em diante, com 10 valores no mínimo, é coleta
  equivocada (`a`; 2× deu falso positivo, a analista validou 5×) (§4.2);
- só linha com data na coluna B; com a coluna A cheia na maior parte da aba, linha de A vazia é ignorada (as linhas de
  acumulado abaixo da tabela da Ibirapuã II sobrescreviam os dias reais, 12/11); data repetida vale a 1ª (§2.1);
- parada cobre o dia com 6 h ou mais na janela solar 06-18 h; UFV cobre tudo, UG n os inversores n.x, Inversor x.y só
  ele (§6.2-6.4); OS 16493 sempre fora ("OS errada"); E1 fora do escopo; do COS só entra "Geração parou" = sim, então
  falha de comunicação sem impacto marcado continua sendo furo (§6.7);
- outubro ficou como a analista mapeou (OS Fracttal + tickets, "não alterar", §6.6): o Nexus não tem essas fontes do jeito
  dela, então as paradas de outubro vêm CONGELADAS do HTML R01 (decisão do Levi, 16/11/2026) e a cobertura é refeita
  com a mesma regra de 6 h sobre os estados lidos agora.
"""
import datetime as dt
import json
import re
import statistics
import unicodedata

REV = "R01"
DESDE = (2026, 10)              # o R01 publica de outubro em diante (setembro saiu, §3)
MEDIANA_DESDE = (2026, 9)       # a régua da Ultragaz olha de setembro em diante (§4.2)
COS_DESDE = "2026-11"           # outubro: paradas congeladas; de novembro em diante, o COS (§6.6-6.7)
LAG = 0                         # sem tolerância de dias em branco (§3): o estado "w" fica desligado
IGN = frozenset({"16493"})      # a OS errada, sempre fora (§10, out/26)
THR = 6.0                       # horas da janela solar 06-18 h para o dia contar como coberto (§6.2)
ULTRAGAZ_X = 5.0
ULTRAGAZ_MIN = 10
UFVN = "Furo de coleta da UFV toda"

# Os nomes do COS que não batem com a aba do BD (ocn.py da analista; §6.7). Os quatro marcados "suposta" ainda esperam a analista
# confirmar; entram como ela deixou.
ALIAS_MANUAL = {
    "Ipixuna do Pará 1": ["Ipixuna do Pará"],
    "Coração 1 e 2": ["Coração 1", "Coração 2"],
    "Ipixuna 1 e 2": ["Ipixuna 1", "Ipixuna 2"],
    "Santarém 1 e 2": ["Santarém 1", "Santarém 2"],
    "Aparecida do Taboado 1 e 2": ["Aparecida do Taboado 1", "Aparecida do Taboado 2"],
    "Santo Antônio da Platina 1 e 2": ["Santo Antonio do Platina"],
    "Santo Antônio da Platina 1": ["Santo Antonio do Platina"],
    "Pharmas 2, 3 e 4": ["Pharma II", "Pharma III", "Pharma IV"],
    "Poconé 1": ["Poconé"],
    "Quixadá 1 (Hortina)": ["Quixadá 1 (Hortina)"],
    "Santo Inácio 12": ["Santo Inácio XII"],                                   # suposta
    "São Bento do Una 1": ["Bento da Una"],                                    # suposta
    "Boa Esperança do Sul IA e IB": ["Boa Esperança do Sul 1", "Boa Esperança do Sul 2"],   # suposta
    "Ceilândia II - Pinheiro, Pitangueira, Atena e Cedro Rosa": ["Ceilândia 2"],   # suposta
}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", s)


def nat(n):
    return [int(x) for x in re.findall(r"\d+", str(n))]


def osid(v):
    if v is None or (isinstance(v, float) and v != v):
        return ""
    return re.sub(r"\.0$", "", str(v).strip())


def num(v):
    """O valor da célula como número; texto e vazio contam como vazio (§2.1)."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _data(v):
    """A coluna B: datetime do Excel ou o texto ISO do banco ("2026-11-01T00:00:00")."""
    if isinstance(v, dt.datetime):
        return v
    if isinstance(v, str) and len(v) >= 10 and v[4] == "-" and v[7] == "-":
        try:
            return dt.datetime.fromisoformat(v[:19] if "T" in v else v[:10])
        except ValueError:
            return None
    return None


def _txt(v):
    return "" if v is None else str(v)


# ── 1. as abas dos BDs (extract2.py) ───────────────────────────────────────────────────────────────────────────────
def ler_abas(src, abas):
    """`abas` = [(nome, cabeçalho da linha 1, linhas abaixo dele na ordem do Excel)], cada linha uma lista posicional
    desde a coluna A. -> (planilhas, log das linhas ignoradas)."""
    out, log = [], []
    for nome, cab, linhas in abas:
        if not cab or len(cab) < 3 or cab[1] != "Data":
            continue
        h = [(str(c).strip() if c is not None else "") for c in cab]
        inv = [i for i, c in enumerate(h) if re.match(r"(?i)^inversor\s*\d", c)]
        ipoa = [i for i, c in enumerate(h) if c.startswith("IPOA") and "DEF" not in c]
        idef = [i for i, c in enumerate(h) if c.startswith("IPOA") and "DEF" in c]
        ghi = [i for i, c in enumerate(h) if c.startswith("GHI")]
        en = [i for i, c in enumerate(h) if c.startswith("Energia Produzida") or c.startswith("Multimedidor")]
        if str(nome).endswith("Backup") or (not inv and not ipoa and not en):
            continue
        linhas = list(linhas)
        ne = sum(1 for r in linhas if r and r[0] not in (None, ""))
        pula_sem_usina = ne > 0.5 * max(1, len(linhas)) or ne >= 20
        cols = sorted(set(inv + ipoa + idef + ghi + en))
        sr = {}
        for r in linhas:
            d = _data(r[1]) if r and len(r) > 1 else None
            if d is None:
                continue
            if pula_sem_usina and r[0] in (None, ""):
                log.append((src, nome, d.date().isoformat(), "linha sem Usina ignorada"))
                continue
            if (d.year, d.month) < MEDIANA_DESDE:       # nenhuma conta olha antes de setembro/2026
                continue
            m = sr.setdefault((d.year, d.month), {})
            if d.day in m:
                log.append((src, nome, d.date().isoformat(), "data duplicada ignorada"))
                continue
            m[d.day] = {i: num(r[i] if i < len(r) else None) for i in cols}     # toda conta passa por num()
        out.append(dict(src=src, sheet=nome, inv=inv, ipoa=ipoa, idef=idef, ghi=ghi, en=en, h=h, sr=sr))
    return out, log


def ultima_data(linhas):
    ds = [d for d in (_data(r[1]) for r in linhas if r and len(r) > 1) if d is not None]
    return max(ds) if ds else None


def velhas(fins):
    """As abas do banco que já não estão no Excel. O banco não apaga a aba renomeada (o `replace=true` da subida só troca
    as que sobem): "Vitesse", "Carosa", "Salvales", "Hortina" e "SunPower" pararam em 09/2026 e a "Iramaia" em 31/10
    (hoje "Iramaia II"), e a Iramaia velha entrava em outubro como usina a mais (prova de 16/11/2026). Sem a lista de
    abas da subida (o `bd_formulas`, que ainda não sobe), vale a régua: a aba viva tem linha de data até o mês em que a
    MAIORIA das abas termina (a coleta deixa o mês inteiro com data); a que termina antes é velha.
    `fins` = {aba: última data}. -> {aba: última data} das velhas."""
    meses = {}
    for d in fins.values():
        if d is not None:
            meses[(d.year, d.month)] = meses.get((d.year, d.month), 0) + 1
    if not meses:
        return {}
    ref = max(meses.items(), key=lambda x: (x[1], x[0]))[0]
    return {n: d for n, d in fins.items() if d is not None and (d.year, d.month) < ref}


def cadastro(info_geral, base_ufv):
    """Info Geral (linhas desde a 3, posicionais desde A: B nome, C descrição, D código, E cliente, Y carteira) e Base UFV
    (desde a 2: B código, C cliente, E supervisor, F status)."""
    def c(r, i):
        return r[i] if r is not None and i < len(r) else None
    info, code2, lista, c2n = {}, {}, [], {}
    for r in info_geral:
        if not c(r, 1):
            continue
        cli = c(r, 4)
        d = dict(cliente=cli.strip() if isinstance(cli, str) else cli, carteira=c(r, 24), codigo=c(r, 3))
        info[norm(c(r, 1))] = d
        if c(r, 3):
            code2[norm(c(r, 3))] = d
            c2n.setdefault(norm(c(r, 3)), set()).add(norm(c(r, 1)))
        lista.append(dict(nome=c(r, 1), desc=c(r, 2), cod=c(r, 3)))
    base = {}
    for r in base_ufv:
        if c(r, 0) and isinstance(c(r, 1), str):
            base[norm(c(r, 1).split("-")[-1])] = (c(r, 2), c(r, 5), c(r, 4), c(r, 3))
    return dict(info=info, code2=code2, lista=lista, c2n=c2n, base=base)


def _lookup(cad, nome):
    n = norm(nome)
    for k in (n, re.sub(r"\d+$", "", n)):
        if k in cad["info"]:
            return cad["info"][k]
    return cad["code2"].get(n)


def d1_de(hoje):
    """A regra d-2 (a analista, 12/11/2026): os dados têm de estar em dia até dois dias antes de hoje (Brasília)."""
    return hoje - dt.timedelta(days=2)


def meses_de(hoje, desde=DESDE):
    d1 = d1_de(hoje)
    out, (y, m) = [], desde
    while (y, m) <= (d1.year, d1.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def estados(planilhas, cad, hoje, desde=DESDE):
    """Os estados de cada célula por mês (§3-§4). -> {"AAAA-MM": {"end": N, "plants": [...]}} (mês sem dado fica fora)."""
    d1, out = d1_de(hoje), {}
    for (Y, MO) in meses_de(hoje, desde):
        last = 0
        for p in planilhas:
            for d, r in p["sr"].get((Y, MO), {}).items():
                if any(num(r.get(i)) not in (None, 0.0) for i in p["inv"] + p["en"]):
                    last = max(last, d)
        END = last
        if (Y, MO) == (d1.year, d1.month):
            END = min(END, d1.day)
        elif (Y, MO) > (d1.year, d1.month):
            END = 0
        plants = []
        for p in planilhas:
            rows = p["sr"].get((Y, MO))
            if not rows:
                continue
            meta = _lookup(cad, p["sheet"])
            code = (meta or {}).get("codigo")
            cli = (meta or {}).get("cliente") or ("Thopen" if p["src"] == "BD_Thopen" else "—")
            cart = (meta or {}).get("carteira") or "—"
            st = cad["base"].get(norm(str(code).split("-")[-1]) if code else "", None)
            gen = p["inv"] if p["inv"] else p["en"]
            TH = {}
            if str(cli).lower().startswith("ultragaz"):
                for ci in gen + p["ipoa"] + p["ghi"]:
                    pv = [num(r.get(ci)) for (yy, mm), dd in p["sr"].items() if (yy, mm) >= MEDIANA_DESDE
                          for r in dd.values()]
                    pv = [v for v in pv if v and v > 0]
                    if len(pv) >= ULTRAGAZ_MIN:
                        TH[ci] = ULTRAGAZ_X * statistics.median(pv)
            eqs = [dict(nome=p["h"][i], tipo="inv" if p["inv"] else "usina", st=[]) for i in gen]
            ipo = dict(nome="IPOA", tipo="ipoa", st=[])
            gh = dict(nome="GHI", tipo="ghi", st=[]) if p["ghi"] else None
            days = list(range(1, END + 1))
            for d in days:
                r = rows.get(d)
                if r is None:
                    for e in eqs:
                        e["st"].append("x")
                    ipo["st"].append("x")
                    if gh:
                        gh["st"].append("x")
                    continue
                vals = [num(r.get(i)) for i in gen]
                pos = sum(1 for v in vals if v and v > 0)
                for e, v, ci in zip(eqs, vals, gen):
                    e["st"].append("v" if v is None else ("a" if (TH.get(ci) and v > TH[ci]) else
                                                          ("o" if v > 0 else ("z" if pos > 0 else "p"))))
                rawv = [v for v in (num(r.get(i)) for i in p["ipoa"]) if v is not None]
                dv = [v for v in (num(r.get(i)) for i in p["idef"]) if v is not None]
                if rawv:
                    ipo["st"].append("a" if (p["ipoa"] and TH.get(p["ipoa"][0]) and max(rawv) > TH[p["ipoa"][0]]) else
                                     ("o" if max(rawv) > 0 else ("z" if pos > 0 else "p")))
                else:
                    ipo["st"].append("d" if (dv and max(dv) > 0) else "v")
                if gh:
                    gv = [v for v in (num(r.get(i)) for i in p["ghi"]) if v is not None]
                    if gv:
                        gh["st"].append("a" if (TH.get(p["ghi"][0]) and max(gv) > TH[p["ghi"][0]]) else
                                        ("o" if max(gv) > 0 else ("z" if pos > 0 else "p")))
                    else:
                        gh["st"].append("v")
            eqs = [ipo] + ([gh] if gh else []) + eqs
            gens = [e for e in eqs if e["tipo"] not in ("ipoa", "ghi")]
            ghs = [e for e in eqs if e["tipo"] == "ghi"]
            hasdata = any(c in "oza" for e in gens for c in e["st"]) or "o" in eqs[0]["st"]
            lag = LAG if (Y, MO) == (hoje.year, hoje.month) else 0
            if hasdata:
                for j in range(END - 1, max(END - 1 - lag, -1), -1):
                    if (all(e["st"][j] in "vx" for e in gens) and eqs[0]["st"][j] in "vxdp"
                            and all(e["st"][j] in "vxp" for e in ghs)):
                        for e in eqs:
                            e["st"][j] = "w"
                    else:
                        break
            for e in eqs:
                e["st"] = "".join(e["st"])
            plants.append(dict(src=p["src"], usina=p["sheet"], cliente=cli, carteira=cart,
                               status=(st[1] if st else None), supervisor=(st[2] if st else None), eqs=eqs, days=days))
        if END == 0 or not plants:
            continue
        out["%d-%02d" % (Y, MO)] = dict(end=END, plants=plants)
    return out


# ── 2. as paradas do COS (ocn.py, load_cos_csv_novo) ──────────────────────────────────────────────────────────────
def _hora_csv(v):
    try:
        return dt.datetime.strptime(str(v).strip(), "%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return None


class Resolvedor:
    """Nome de usina do COS -> abas do BD (ocn.resolve). O COS não traz código confiável (§12.3): a ordem é o alias
    (Info Geral nome/descrição, o mapa código -> aba do nrm3.py, os manuais), o nome igual a uma aba, os combos
    "Base 1 e 2"/"Base 2.1, 2.2 e 2.3" e o prefixo (1 a 4 abas)."""

    def __init__(self, plants, cad, cos_usinas=()):
        self.sheets = {}
        for p in plants:
            self.sheets.setdefault(norm(p["usina"]), p["usina"])
        alias = {}
        for i in cad["lista"]:
            for k in (norm(i["nome"]), norm(i["desc"]) if i["desc"] else None):
                if k and norm(i["nome"]) in self.sheets:
                    alias[k] = [self.sheets[norm(i["nome"])]]
        # o nrm3.py da analista: pelo código do COS (o trecho depois do último "-"), pela descrição e pelo nome do cadastro
        byc = {norm(i["cod"]): i for i in cad["lista"] if i["cod"]}
        byd = {norm(i["desc"]): i for i in cad["lista"] if i["desc"]}
        byn = {norm(i["nome"]): i for i in cad["lista"]}
        for cod, nome in cos_usinas:
            suf, n = norm(str(cod).split("-")[-1]), norm(nome)
            i = byc.get(suf) or byd.get(n) or byn.get(n) or byn.get(suf)
            sh = self.sheets.get(norm(i["nome"])) if i else None
            if not sh:
                sh = self.sheets.get(suf) or self.sheets.get(n)
            if sh:
                alias.setdefault(n, [sh])
        alias.update({norm(k): list(v) for k, v in ALIAS_MANUAL.items()})
        self.alias = alias

    def __call__(self, name):
        sheets, alias = self.sheets, self.alias
        k = norm(name)
        if k in alias:
            return alias[k]
        if k in sheets:
            return [sheets[k]]
        mm = re.match(r"^(.*?)\s+(\d+(?:\.\d+)?(?:\s*,\s*\d+(?:\.\d+)?)*(?:\s+e\s+\d+(?:\.\d+)?)?)$", str(name).strip())
        if mm:
            b, out = mm.group(1), []
            for x in re.findall(r"\d+(?:\.\d+)?", mm.group(2)):
                for cand in (f"{b} {x}", f"{b} {x.split('.')[0]}"):
                    if norm(cand) in sheets:
                        out.append(sheets[norm(cand)])
                        break
                    if norm(cand) in alias:
                        out += alias[norm(cand)]
                        break
            if out:
                return list(dict.fromkeys(out))
            if norm(b) in sheets:
                return [sheets[norm(b)]]
        c = [v for kk, v in sheets.items() if kk.startswith(k) or k.startswith(kk)]
        return c if 0 < len(c) <= 4 else []


def _casa_equip(q, n, e):
    return e["tipo"] == "inv" and ((q.startswith("UG") and nat(e["nome"])[:1] == n[:1]) or
                                   (q.startswith("Inversor") and nat(e["nome"]) == n))


def _val(r, k):
    x = r.get(k)
    return None if x is None or (isinstance(x, str) and x.strip() == "") else x


def _linhas_unicas(linhas):
    """[(linha, início, normalização, OS)] sem repetição: a mesma OS numa linha fechada e noutra aberta vale a fechada;
    linha repetida sai (§6.7.1). -> (linhas, quantas saíram)."""
    v = _val
    rows = [(r, _hora_csv(v(r, "Início")), _hora_csv(v(r, "Normalização")), osid(v(r, "OS"))) for r in linhas]
    fechadas = {o for _r, _i, f, o in rows if f is not None and o != ""}
    vistos, d = set(), []
    for x in rows:
        r, _ini, fim, o = x
        if fim is None and o in fechadas:
            continue
        k = (o, v(r, "Início"), v(r, "Normalização"), v(r, "Equipamentos"), v(r, "Usina"))
        if k in vistos:
            continue
        vistos.add(k)
        d.append(x)
    return d, len(rows) - len(d)


def _fora_do_escopo(r, osn):
    """A OS 16493 (sempre fora) e o cliente E1 (fora do escopo), §6.7. -> o motivo, ou ""."""
    if osn in IGN:
        return "16493"
    cl = norm(_txt(_val(r, "Cliente")))
    return "E1 fora do escopo" if cl == "e1" or cl.startswith("e1energia") else ""


def registros_cos(linhas, plants, cad, agora):
    """As paradas do COS de novembro em diante. `linhas` = dicts com as colunas do CSV da tela Ocorrências ("OS",
    "Início", "Normalização", "Cliente", "Código da usina", "Usina", "Falha", "Equipamentos", "Geração parou"); `plants`
    = as usinas do mês mais novo (os nomes das abas e os inversores de cada uma). -> (registros, rejeitados, sem aba)."""
    v = _val
    d, descartadas = _linhas_unicas(linhas)
    usinas = list(dict.fromkeys((_txt(v(r, "Código da usina")), _txt(v(r, "Usina"))) for r, *_ in d))
    resolve = Resolvedor(plants, cad, usinas)
    EQS = {p["usina"]: p["eqs"] for p in plants}
    rc, rej, unm = [], {}, {}

    def rj(w):
        rej[w] = rej.get(w, 0) + 1
    for r, ini, fim, osn in d:
        shs = resolve(_txt(v(r, "Usina")))
        if not shs:
            k = (_txt(v(r, "Cliente")), _txt(v(r, "Usina")))
            unm[k] = unm.get(k, 0) + 1
            continue
        f = _txt(v(r, "Falha"))
        fn = norm(f)
        eqtxt = v(r, "Equipamentos") if isinstance(v(r, "Equipamentos"), str) else ""
        fora = _fora_do_escopo(r, osn)
        if fora:
            rj(fora)
            continue
        gp = norm(v(r, "Geração parou")) if isinstance(v(r, "Geração parou"), str) else ""
        if not gp.startswith("sim"):
            rj("COS: geração não parou / não informado (%s)" % ("não" if gp.startswith("nao") else "vazio"))
            continue
        invs = re.findall(r"Inversor\s*\d+(?:\.\d+)?", eqtxt)
        ne = norm(eqtxt)
        if fn in ("desligamentodecabine", "desligamentodeskid", "desligamentodeqgbt") or "cabine" in ne \
                or "skid" in ne or "qgbt" in ne:
            eqs = ["UG %s" % n for n in nat(eqtxt)]
        elif invs:
            eqs = invs
        elif fn.startswith("desligamento") or fn in ("falhadaconcessionaria", "atuacaodeprotecao") or "comunica" in fn:
            eqs = ["UFV"]
        else:
            rj("tipo/equipamento não identificado (%s)" % f)
            continue
        if not eqs:
            rj("equipamento não identificado")
            continue
        if ini is None:
            rj("sem início")
            continue
        ab = fim is None
        if ab:
            fim = agora                                  # parada em aberto vale até agora, Brasília (§6.7.5)
        if fim < ini:
            rj("fim<início")
            continue
        for q in eqs:
            shq = shs
            if len(shs) > 1 and q != "UFV":
                # usina agrupada + equipamento específico: só onde o equipamento existe, e se existir numa só (§6.7.7)
                n = nat(q)
                c = [sh for sh in shs if any(_casa_equip(q, n, e) for e in EQS.get(sh, []))]
                if len(c) != 1:
                    rj("usina agrupada: equipamento ambíguo")
                    continue
                shq = c
            for sh in shq:
                rc.append(dict(src="C", usina=sh, cod=None, cli=v(r, "Cliente"), os=osn, eq=q, cls=f, ini=ini,
                               fim=fim, semos=(osn == ""), aberta=ab))
    rej["_sem_aba"] = sum(unm.values())
    rej["_linhas_descartadas_duplicidade"] = descartadas
    return rc, rej, unm


# ── 3. outubro congelado do HTML R01 ──────────────────────────────────────────────────────────────────────────────
_RX_DB = re.compile(r"^const DB=(\{.*\});\s*$", re.M)
_CONF_INI, _CONF_FIM = "/*CONF0*/", "/*END0*/"


def ler_html_r01(texto):
    """(db, conf) do HTML gerado pela analista; ValueError se não for o relatório."""
    m = _RX_DB.search(texto)
    if not m:
        raise ValueError("o arquivo não é o relatório de furos de coleta (não achei os dados 'const DB=')")
    db = json.loads(m.group(1))
    if not isinstance(db, dict) or not isinstance(db.get("months"), dict) or not db["months"]:
        raise ValueError("o relatório não tem nenhum mês")
    conf = {}
    i, j = texto.find(_CONF_INI), texto.find(_CONF_FIM)
    if i >= 0 and j > i:
        bruto = texto[i + len(_CONF_INI):j].replace("*\\/", "*/").replace("<\\/", "</")
        conf = json.loads(bruto) or {}
        if not isinstance(conf, dict):
            raise ValueError("as confirmações do relatório não são um objeto")
    return db, conf


def congelar(db):
    """As paradas que o Nexus não tem como refazer, como estão no HTML: {"2026-10": {"BD_Performance|Usina": [os, ...]}}.
    Outubro inteiro (OS Fracttal + tickets, §6.6) e, de novembro em diante, só as que NÃO são do COS: os tickets da aba
    Desligamentos que começaram em outubro e entram em novembro (na prova de 16/11, PEII até 04/11 e PEIII até 06/11; a
    planilha de tickets parou em outubro, e o Nexus não a lê). As do COS o Nexus refaz ao vivo."""
    out = {}
    for m, mv in (db.get("months") or {}).items():
        por = {}
        for p in mv.get("plants") or []:
            lista = [list(o) for o in p.get("os") or [] if m < COS_DESDE or (o and o[0] != "C")]
            if lista:
                por[f"{p['src']}|{p['usina']}"] = lista
        if por:
            out[m] = por
    return out


def _hora_curta(txt, ano):
    """"28/10 14:05" (e o " (aberta)" do fim) com o ano do mês."""
    s = str(txt).replace("(aberta)", "").strip()
    try:
        return dt.datetime.strptime(f"{s} {ano}", "%d/%m %H:%M %Y")       # com o ano: o 29/02 não quebra
    except ValueError:
        return None


def registros_congelados(lista, ano):
    rc = []
    for o in lista:
        if len(o) < 7:
            continue
        ini, fim = _hora_curta(o[4], ano), _hora_curta(o[5], ano)
        if ini is None or fim is None:
            continue
        if fim < ini:                                  # virou o ano (dez -> jan)
            fim = fim.replace(year=ano + 1)
        rc.append(dict(src=o[0], usina=None, cod=None, os="" if o[1] == "s/ nº" else o[1], eq=o[2], cls=o[3],
                       ini=ini, fim=fim, semos=o[6] == "A", aberta="(aberta)" in str(o[5])))
    return rc


# ── 4. o cruzamento (oscross.cross) ───────────────────────────────────────────────────────────────────────────────
def solar(ini, fim, day):
    a = dt.datetime.combine(day, dt.time(6))
    b = dt.datetime.combine(day, dt.time(18))
    s, e = max(ini, a), min(fim, b)
    return max(0, (e - s).total_seconds() / 3600)


def _cruzar_planta(p, recs, Y, MO):
    lst, cov = [], {}
    for x in recs:
        q, tgt = norm(x["eq"]), []
        if q == "ufv":
            tgt = list(range(len(p["eqs"])))
        else:
            n = nat(x["eq"])
            for j, e in enumerate(p["eqs"]):
                if e["tipo"] != "inv":
                    continue
                en = nat(e["nome"])
                if q.startswith("ug") and n and en and en[0] == n[0]:
                    tgt.append(j)
                elif q.startswith("inversor") and n and en == n:
                    tgt.append(j)
        if not tgt:
            continue
        days = [k for k, dd in enumerate(p["days"]) if solar(x["ini"], x["fim"], dt.date(Y, MO, dd)) >= THR]
        if not days:
            continue
        ridx = len(lst)
        lst.append([x["src"], x["os"] or "s/ nº", x["eq"], x["cls"], x["ini"].strftime("%d/%m %H:%M"),
                    x["fim"].strftime("%d/%m %H:%M") + (" (aberta)" if x.get("aberta") else ""),
                    "A" if x.get("semos") else ""])
        for j in tgt:
            for k in days:
                cov.setdefault(j, {}).setdefault(k, []).append(ridx)
    cells = 0
    for j, e in enumerate(p["eqs"]):
        e.pop("cv", None)
        cv = cov.get(j)
        if cv:
            cv = {str(k): v for k, v in cv.items() if e["st"][k] in "vxzpd"}
            if cv:
                e["cv"] = cv
                cells += len(cv)
    p.pop("os", None)
    if lst:
        p["os"] = lst
    return cells, len(lst)


def cruzar(meses, recs_cos, congelado, cad):
    """Põe `cv` (dia -> paradas que o cobrem) nos equipamentos e `os` (as paradas) nas usinas, mês a mês."""
    stats = dict(cells=0, plants=0)
    cosos = {x["os"] for x in recs_cos if x["os"]}
    idx = {}
    for i, x in enumerate(recs_cos):
        for k in {norm(x["usina"]), norm(x["cod"]) if x["cod"] not in (None, 0, "0") else None}:
            if k:
                idx.setdefault(k, []).append(i)
    for m, mv in meses.items():
        Y, MO = map(int, m.split("-"))
        cong = (congelado or {}).get(m) or {}
        for p in mv["plants"]:
            recs = registros_congelados(cong.get(f"{p['src']}|{p['usina']}") or [], Y)
            if m >= COS_DESDE:
                # o registro do COS substitui o ticket com a mesma OS (§6.7.8); o ticket vem antes, como no oscross
                recs = [x for x in recs if x["os"] not in cosos]
                keys = {norm(p["usina"])} | cad["c2n"].get(norm(p["usina"]), set())
                recs += [recs_cos[i] for i in sorted({i for k in keys for i in idx.get(k, [])})]
            cells, n = _cruzar_planta(p, recs, Y, MO)
            stats["cells"] += cells
            stats["plants"] += 1 if cells else 0
    return stats


# ── 4b. o que o COS registrou no mês, para a tela (não entra na conta) ────────────────────────────────────────────────
def ocorrencias_cos(linhas, meses, cad, agora):
    """Todas as ocorrências do COS de cada usina no mês, normalizadas e em aberto, com a hora de início e de fim: o
    contexto do furo na tela (Levi, 19/11/2026: "linka com as ocorrências de normalizações ou que está em aberto [...]
    se naquele dia teve desligamento, foi de que horas até que horas, e aí ficar mais óbvio").

    NÃO mexe na conta: quem explica o dia continua sendo a regra do R01 (`registros_cos` + `cruzar`: "Geração parou" =
    sim e 6 h na janela solar). Aqui entram também a parada de menos de 6 h e a de "Geração parou" = não ou vazio: a
    falha de comunicação com a usina gerando é justamente o furo que a equipe tem de coletar, e a tela precisa mostrar
    que ela existiu e quando. Fora do escopo, como no R01: a OS 16493 e o cliente E1.

    Põe em cada usina `oc` = [[início, fim (ISO, minuto), falha, equipamentos, OS, geração parou ("s", "n" ou ""),
    em aberto (1/0), explica o dia pela regra (1/0)]], só as que tocam o mês até o último dia verificado. A em aberto
    vai até `agora`, como na conta (§6.7.5). -> quantas foram postas."""
    if not linhas or not meses:
        return 0
    v = _val
    ult = meses[max(meses)]["plants"]
    d, _ = _linhas_unicas(linhas)
    usinas = list(dict.fromkeys((_txt(v(r, "Código da usina")), _txt(v(r, "Usina"))) for r, *_ in d))
    resolve = Resolvedor(ult, cad, usinas)
    EQS = {p["usina"]: p["eqs"] for p in ult}
    por_usina = {}
    for r, ini, fim, osn in d:
        if ini is None or _fora_do_escopo(r, osn):
            continue
        shs = resolve(_txt(v(r, "Usina")))
        if not shs:
            continue
        eqtxt = v(r, "Equipamentos") if isinstance(v(r, "Equipamentos"), str) else ""
        if len(shs) > 1:
            # usina agrupada (Coração 1 e 2): a ocorrência de um inversor vai só para a aba onde ele existe (§6.7.7)
            invs = re.findall(r"Inversor\s*\d+(?:\.\d+)?", eqtxt)
            c = [sh for sh in shs if any(_casa_equip(q, nat(q), e) for q in invs for e in EQS.get(sh, []))]
            shs = c or shs
        gp = norm(v(r, "Geração parou")) if isinstance(v(r, "Geração parou"), str) else ""
        aberta = fim is None
        ate = agora if aberta else fim
        if ate < ini:
            continue
        item = (ini, ate, _txt(v(r, "Falha")), eqtxt[:160], osn, "s" if gp.startswith("sim") else "n" if gp.startswith("nao") else "",
                aberta)
        for sh in shs:
            por_usina.setdefault(norm(sh), []).append(item)
    postas = 0
    for m, mv in meses.items():
        Y, MO = map(int, m.split("-"))
        de, ate_mes = dt.datetime(Y, MO, 1), dt.datetime(Y, MO, mv["end"]) + dt.timedelta(days=1)
        for p in mv["plants"]:
            p.pop("oc", None)
            lst = [x for x in por_usina.get(norm(p["usina"]), []) if x[0] < ate_mes and x[1] > de]
            if not lst:
                continue
            # a que a regra do R01 usou para explicar algum dia está nas paradas da usina (`os`), com a OS e o início
            usou = {(o[1], o[4]) for o in p.get("os") or [] if o[0] == "C"}
            p["oc"] = [[x[0].isoformat(timespec="minutes"), x[1].isoformat(timespec="minutes"), x[2], x[3], x[4], x[5],
                        1 if x[6] else 0, 1 if (x[4] or "s/ nº", x[0].strftime("%d/%m %H:%M")) in usou else 0]
                       for x in sorted(set(lst), key=lambda x: (x[0], x[1], x[4]))]
            postas += len(p["oc"])
    return postas


# ── 5. tudo junto ────────────────────────────────────────────────────────────────────────────────────────────────
def gerar(livros, info_geral, base_ufv, cos_linhas, congelado, hoje, agora, desde=DESDE):
    """O relatório inteiro. `livros` = [("BD_Performance", abas), ("BD_Thopen", abas)] (ver `ler_abas`); `cos_linhas`
    = as linhas do CSV da tela Ocorrências (ou None, sem o COS); `congelado` = `congelar(db do HTML R01)`; `hoje` = a
    data em Brasília; `agora` = a hora em Brasília (o fim da parada em aberto)."""
    planilhas, log = [], []
    for src, abas in livros:
        p, lg = ler_abas(src, abas)
        planilhas += p
        log += lg
    return gerar_de(planilhas, cadastro(info_geral, base_ufv), cos_linhas, congelado, hoje, agora, desde, len(log))


def gerar_de(planilhas, cad, cos_linhas, congelado, hoje, agora, desde=DESDE, ignoradas=0):
    """O mesmo `gerar`, das planilhas já lidas (o serviço guarda a leitura do banco até a próxima subida)."""
    meses = estados(planilhas, cad, hoje, desde)
    ult = meses[max(meses)]["plants"] if meses else []
    recs, rej, unm = registros_cos(cos_linhas or [], ult, cad, agora)
    st = cruzar(meses, recs, congelado, cad)
    usados = len(recs)
    oc = ocorrencias_cos(cos_linhas or [], meses, cad, agora)
    return {"months": meses, "rev": REV, "gen": agora.strftime("%d/%m/%Y %H:%M"),
            "stats": dict(st, cos_registros=usados, cos_ocorrencias=oc, cos_rejeitados=rej,
                          cos_sem_aba=sorted([[c, u, n] for (c, u), n in unm.items()], key=lambda x: -x[2]),
                          linhas_ignoradas=ignoradas, d1=d1_de(hoje).isoformat(),
                          congelado={m: len(v) for m, v in (congelado or {}).items()})}

# -*- coding: utf-8 -*-
"""Metas das usinas pelo PVsyst (protótipo de 25/11/2026). A meta das usinas que NÃO são da Thopen sai do relatório do
PVsyst (a Thopen manda a própria meta, que está no banco). Levi, 24/11/2026: "É por eles que a gente preenche as metas
[...] a parte de balances and main results [...] é onde a gente vai pegar o PR, a energia esperada [...] a ideia seria a
gente anexar esses PVSys e já preencher automático na meta. Faço um protótipo, já pode subir [...] amanhã eu valido".

O que este módulo faz, sem rede e sem gravar no banco:
- `ler_texto(texto)`: o relatório do PVsyst (o texto que o pypdf tira do PDF) -> o projeto, o kWp, a versão, a data da
  simulação, a energia anual P50/P70/P75/P90/P95 (o que o relatório trouxer), o PR do ano e a tabela "Balances and main
  results" mês a mês (GlobHor, DiffHor, T_Amb, GlobInc, GlobEff, EArray, E_Grid, PR), com a energia sempre em kWh (o
  relatório da Iramaia II vem em kWh, o da Gravatá em MWh);
- `meta_do_pvsyst(lido)`: as 12 linhas no formato da aba "Info Mensal" do BD_Performance, a meta que a plataforma lê hoje:
  P50 (MWh) = E_Grid; P90 = P50 do mês × (P90 ÷ P50 do ano); P75 = P50 − (P50 − P90) × 0,6745 ÷ 1,2816 (a mesma
  distribuição normal do PVsyst: a Info Mensal da Iramaia II de hoje bate com essa conta, 578,84 / 555,96 / 566,81);
  PR = o PR do mês; IPOA Previsto = GlobInc; GHI Previsto = GlobHor;
- `validar_meta`/`meta_vazia`/`mudancas`: a meta editável (Levi, 25/11/2026, vendo o protótipo: "deve ser possível
  editar e ter o registro das edições ou inserir todos os dados manualmente [...] que nem no Excel, a pessoa pegar e
  colar"): 12 linhas, o P50 obrigatório, o PR em % vira fração; o que mudou, valor a valor;
- `guardar`/`salvas`: o protótipo guarda na pasta de dados do Nexus (o PDF, o que se leu, a meta e o registro de cada
  Salvar: quem, quando, de onde — "PVsyst", "PVsyst editado" ou "manual" — e cada valor de quanto para quanto), NÃO num
  livro do banco (livro é para sempre: o formato fica para depois da validação). Uma meta por usina. A Sala e o
  Gerencial seguem com a Info Mensal até lá;
- `meta_atual`/`meta_de_hoje`: a meta que a Info Mensal tem hoje, só para comparar na tela (é meta, não o realizado),
  lida uma vez e guardada 10 min.
"""
import difflib
import hashlib
import io
import json
import os
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone

_BRT = timezone(timedelta(hours=-3))
COLUNAS = ("GlobHor", "DiffHor", "T_Amb", "GlobInc", "GlobEff", "EArray", "E_Grid", "PR")
_ENERGIA = ("EArray", "E_Grid")
# os meses como o PVsyst escreve, nas línguas em que ele gera o relatório
_MESES = {}
for _n, _nomes in enumerate((("january", "janeiro", "enero", "janvier"), ("february", "fevereiro", "febrero", "fevrier"),
                             ("march", "marco", "marzo", "mars"), ("april", "abril", "avril"),
                             ("may", "maio", "mayo", "mai"), ("june", "junho", "junio", "juin"),
                             ("july", "julho", "julio", "juillet"), ("august", "agosto", "aout"),
                             ("september", "setembro", "septiembre", "septembre"), ("october", "outubro", "octubre", "octobre"),
                             ("november", "novembro", "noviembre", "novembre"), ("december", "dezembro", "diciembre", "decembre")),
                            start=1):
    for _x in _nomes:
        _MESES[_x] = _n
_ANO = ("year", "ano", "año", "annee", "total")
_FATOR_ENERGIA = {"wh": 0.001, "kwh": 1.0, "mwh": 1000.0, "gwh": 1_000_000.0}
Z90, Z75 = 1.2816, 0.6745      # quantis da normal: o P90 e o P75 a partir do P50 (o PVsyst usa a mesma distribuição)
TOLERANCIA_SOMA = 0.005        # a soma dos 12 meses contra a linha do ano, e o ano contra o P50 do resumo


class NaoEhPvsyst(ValueError):
    pass


def norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _num(s):
    """'6368454' / '6431.9' / '6.431,9' -> float; None se não é número."""
    s = str(s).strip().replace(" ", "")
    if not re.fullmatch(r"-?[\d.,]+", s):
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def texto_do_pdf(dados: bytes) -> str:
    """O texto do PDF pelo pypdf (o mesmo da assinatura da APR, já no requirements)."""
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(dados))
    return "\n".join((p.extract_text() or "") for p in r.pages)


def _energia_anual(linhas: list[str]) -> dict:
    """{"P50": kWh, "P90": kWh, ...} do bloco "System Production": os rótulos "Produced Energy (Pnn)", depois os números,
    depois as unidades (o PVsyst escreve em colunas, e o texto sai assim). Só o 1º bloco: o 2º repete os rótulos com o
    "Specific production"."""
    out = {}
    for i, l in enumerate(linhas):
        if not re.match(r"\s*Produced Energy \(P\d\d\)", l):
            continue
        rot = []
        j = i
        while j < len(linhas) and re.match(r"\s*Produced Energy \(P\d\d\)", linhas[j]):
            rot.append(re.search(r"\((P\d\d)\)", linhas[j]).group(1))
            j += 1
        nums = []
        while j < len(linhas) and len(nums) < len(rot) and _num(linhas[j]) is not None:
            nums.append(_num(linhas[j]))
            j += 1
        unis = []
        while j < len(linhas) and len(unis) < len(rot) and re.match(r"\s*[kMG]?Wh/year", linhas[j]):
            unis.append(linhas[j].strip().split("/")[0].lower())
            j += 1
        if len(nums) == len(rot) == len(unis):
            out = {p: v * _FATOR_ENERGIA.get(u, 1.0) for p, v, u in zip(rot, nums, unis)}
        break
    return out


def _tabela(linhas: list[str]) -> tuple[list[dict], dict | None, dict]:
    """A "Balances and main results": ([12 meses], linha do ano, {coluna: unidade})."""
    i = next((n for n, l in enumerate(linhas) if "Balances and main results" in l), None)
    if i is None:
        raise NaoEhPvsyst("não achei a tabela “Balances and main results” no relatório")
    cab = None
    for n in range(i + 1, min(i + 6, len(linhas))):
        partes = linhas[n].split()
        if "E_Grid" in partes and "GlobHor" in partes:
            cab, i = partes, n
            break
    if not cab:
        raise NaoEhPvsyst("achei a “Balances and main results”, mas não o cabeçalho das colunas (GlobHor … E_Grid)")
    unidades = dict(zip(cab, linhas[i + 1].split())) if i + 1 < len(linhas) else {}
    meses, ano = [], None
    for l in linhas[i + 2:i + 40]:
        partes = l.split()
        if not partes:
            continue
        nome = norm(partes[0])
        vals = [_num(x) for x in partes[1:1 + len(cab)]]
        if len(vals) < len(cab) or any(v is None for v in vals):
            if meses:
                break
            continue
        linha = dict(zip(cab, vals))
        for c in _ENERGIA:                # a energia sempre em kWh
            if c in linha:
                linha[c] *= _FATOR_ENERGIA.get(str(unidades.get(c, "kwh")).lower(), 1.0)
        if nome in _MESES:
            meses.append(dict(linha, mes=_MESES[nome]))
        elif nome in _ANO:
            ano = linha
            break
    if len(meses) != 12 or [m["mes"] for m in meses] != list(range(1, 13)):
        raise NaoEhPvsyst(f"a tabela mensal veio com {len(meses)} mês(es) em vez dos 12, de janeiro a dezembro")
    return meses, ano, unidades


def ler_texto(texto: str) -> dict:
    """O relatório do PVsyst lido (ver o topo). Recusa (NaoEhPvsyst) o que não for relatório do PVsyst ou não tiver a
    tabela mensal inteira: sem dado, nada se inventa."""
    if "PVsyst" not in texto and "PVSYST" not in texto.upper():
        raise NaoEhPvsyst("o arquivo não parece um relatório do PVsyst")
    linhas = [l.rstrip() for l in texto.splitlines()]

    def acha(rx, grupo=1):
        m = re.search(rx, texto)
        return m.group(grupo).strip() if m else ""
    meses, ano, unidades = _tabela(linhas)
    p = _energia_anual(linhas)
    pr_ano = _num(acha(r"Perf(?:ormance|\.)\s*Ratio PR\s*([\d.,]+)\s*%")) if acha(r"Perf(?:ormance|\.)\s*Ratio PR\s*([\d.,]+)\s*%") else None
    kwp = _num(acha(r"System power:\s*([\d.,]+)\s*kWp")) if acha(r"System power:\s*([\d.,]+)\s*kWp") else None
    soma = sum(m["E_Grid"] for m in meses)
    conferencias = []

    def mwh(v):
        return f"{v / 1000:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".") + " MWh"
    if ano and ano.get("E_Grid"):
        ok = abs(soma - ano["E_Grid"]) / ano["E_Grid"] <= TOLERANCIA_SOMA
        conferencias.append({"ok": ok, "texto": f"A soma dos 12 meses ({mwh(soma)}) "
                             f"{'bate' if ok else 'NÃO bate'} com a linha do ano ({mwh(ano['E_Grid'])})."})
    if p.get("P50"):
        ok = abs(soma - p["P50"]) / p["P50"] <= TOLERANCIA_SOMA
        conferencias.append({"ok": ok, "texto": f"A energia do ano {'bate' if ok else 'NÃO bate'} com o P50 do resumo "
                             f"({mwh(p['P50'])})."})
    return {"projeto": acha(r"Project:\s*(.+)"), "versao": acha(r"PVsyst V(\d+\.\d+(?:\.\d+)?)") or acha(r"Version (\d+\.\d+(?:\.\d+)?)"),
            "simulado_em": acha(r"Simulation date:\s*(\d{2}/\d{2}/\d{2,4})"),
            "local": acha(r"Geographical Site\s*\n(.+)"), "kwp": kwp, "pr_ano": pr_ano / 100 if pr_ano and pr_ano > 1.5 else pr_ano,
            "energia_ano_kwh": p, "meses": meses, "ano": ano, "unidades": unidades, "conferencias": conferencias}


def meta_do_pvsyst(lido: dict) -> list[dict]:
    """As 12 linhas da meta no formato da aba Info Mensal (ver o topo). O P90 e o P75 só saem com o P90 no relatório."""
    p50a, p90a = (lido.get("energia_ano_kwh") or {}).get("P50"), (lido.get("energia_ano_kwh") or {}).get("P90")
    soma = sum(m["E_Grid"] for m in lido["meses"])
    base = p50a or soma
    razao = p90a / base if p90a and base else None
    out = []
    for m in lido["meses"]:
        p50 = m["E_Grid"] / 1000
        p90 = p50 * razao if razao else None
        out.append({"mes": m["mes"], "p50_mwh": round(p50, 2), "p90_mwh": round(p90, 2) if p90 is not None else None,
                    "p75_mwh": round(p50 - (p50 - p90) * Z75 / Z90, 2) if p90 is not None else None,
                    "pr": round(m["PR"], 3) if m.get("PR") is not None else None,
                    "ipoa_kwh_m2": m.get("GlobInc"), "ghi_kwh_m2": m.get("GlobHor")})
    return out


# ── a usina: sugestão pelo nome do projeto e do arquivo ───────────────────────────────────────────────────────────────
def sugerir_usina(lido: dict, nome_arquivo: str, usinas: list[str]) -> tuple[str, float]:
    """A usina da meta (os nomes da Info Mensal) mais parecida com o projeto e o nome do arquivo, e a nota (0 a 1).
    Abaixo de 0,6 a tela não escolhe: a pessoa escolhe."""
    def limpo(s):
        return re.sub(r"\b(ufv|usina|anexo|vi|pvsyst|pdf)\b", " ", norm(s)).strip()
    alvos = [limpo(lido.get("projeto")), limpo(re.sub(r"\b[A-Z]{2}\d{3,4}\b", " ", nome_arquivo or ""))]
    melhor, nota = "", 0.0
    for u in usinas:
        lu = limpo(u)
        for a in alvos:
            if not a:
                continue
            n = difflib.SequenceMatcher(None, a, lu).ratio()
            if lu == a or (lu and (lu in a or a in lu)):
                n = max(n, 0.9 if lu == a else 0.8)
            if n > nota:
                melhor, nota = u, n
    return (melhor, round(nota, 2)) if nota >= 0.6 else ("", round(nota, 2))


# ── o protótipo guarda na pasta de dados do Nexus (não no banco: o livro é para sempre) ─────────────────────────────
def _pasta(raiz) -> str:
    p = os.path.join(str(raiz), "metas_pvsyst")
    os.makedirs(os.path.join(p, "pdf"), exist_ok=True)
    return p


def guardar_pdf(raiz, dados: bytes) -> str:
    sha = hashlib.sha256(dados).hexdigest()[:20]
    caminho = os.path.join(_pasta(raiz), "pdf", f"{sha}.pdf")
    if not os.path.exists(caminho):
        with open(caminho + ".tmp", "wb") as f:
            f.write(dados)
        os.replace(caminho + ".tmp", caminho)
    return sha


def ler_pdf_guardado(raiz, sha: str) -> bytes | None:
    if not re.fullmatch(r"[0-9a-f]{20}", sha or ""):
        return None
    caminho = os.path.join(_pasta(raiz), "pdf", f"{sha}.pdf")
    if not os.path.exists(caminho):
        return None
    with open(caminho, "rb") as f:
        return f.read()


def _arquivo_salvas(raiz) -> str:
    return os.path.join(_pasta(raiz), "metas.json")


def salvas(raiz) -> dict:
    """{usina: {...}} das metas salvas pelo PVsyst (a última de cada usina vale; as anteriores ficam no histórico)."""
    try:
        with open(_arquivo_salvas(raiz), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


CAMPOS = ("p50_mwh", "p90_mwh", "p75_mwh", "pr", "ipoa_kwh_m2", "ghi_kwh_m2")


def meta_vazia() -> list[dict]:
    """As 12 linhas em branco: a meta digitada ou colada à mão, sem o PDF."""
    return [dict({c: None for c in CAMPOS}, mes=m) for m in range(1, 13)]


def validar_meta(linhas) -> list[dict]:
    """As 12 linhas que a tela manda (digitadas, coladas do Excel ou do PVsyst), limpas. O P50 é obrigatório nos 12 meses
    (a meta é a energia); o resto pode ficar vazio. O PR digitado em % (73,6) vira fração (0,736). Recusa com ValueError."""
    if not isinstance(linhas, list) or len(linhas) != 12:
        raise ValueError("a meta tem de ter os 12 meses")
    out = []
    for n, x in enumerate(linhas, start=1):
        x = x if isinstance(x, dict) else {}
        linha = {"mes": n}
        for c in CAMPOS:
            v = x.get(c)
            v = None if v in (None, "") else (_num(v) if not isinstance(v, (int, float)) else float(v))
            if v is not None and (v != v or v < 0):
                raise ValueError(f"valor negativo ou inválido em {c} no mês {n}")
            if c == "pr" and v is not None and v > 1.5:
                v = v / 100
            linha[c] = None if v is None else round(v, 4)
        if linha["p50_mwh"] is None:
            raise ValueError(f"falta o P50 do mês {n}")
        out.append(linha)
    return out


def mudancas(antes: list[dict] | None, depois: list[dict]) -> list[dict]:
    """[{mes, campo, de, para}] do que mudou de uma meta para a outra (o registro das edições)."""
    a = {x["mes"]: x for x in (antes or [])}
    out = []
    for x in depois:
        for c in CAMPOS:
            de, para = (a.get(x["mes"]) or {}).get(c), x.get(c)
            if (de is None) != (para is None) or (de is not None and abs(de - para) > 1e-6):
                out.append({"mes": x["mes"], "campo": c, "de": de, "para": para})
    return out


_ROTULO = {"p50_mwh": ("P50", 1, 1, ""), "p90_mwh": ("P90", 1, 1, ""), "p75_mwh": ("P75", 1, 1, ""),
           "pr": ("PR", 100, 1, "%"), "ipoa_kwh_m2": ("IPOA", 1, 1, ""), "ghi_kwh_m2": ("GHI", 1, 1, "")}
_MES_CURTO = ("", "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")


def descrever(m: dict) -> str:
    """Uma mudança do registro como se lê: "mar · P50 576,2 → 700,5", "jan · PR 72,7% → 75,0%"."""
    nome, fator, casas, un = _ROTULO.get(m.get("campo"), (m.get("campo"), 1, 2, ""))

    def f(v):
        return "vazio" if v is None else f"{v * fator:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".") + un
    return f"{_MES_CURTO[m['mes']] if 1 <= (m.get('mes') or 0) <= 12 else m.get('mes')} · {nome} {f(m.get('de'))} → {f(m.get('para'))}"


def guardar(raiz, usina: str, ano: int, meta: list[dict], quem: str, *, sha: str = "", nome_arquivo: str = "",
            lido: dict | None = None) -> dict:
    """Salva a meta da usina. Cada Salvar vira uma entrada no registro das edições (quem, quando, de onde e o que mudou
    contra a meta salva antes; na 1ª vez, contra o PVsyst). A origem: "PVsyst", "PVsyst editado" ou "manual"."""
    d = salvas(raiz)
    anterior = d.get(usina) or {}
    do_pvsyst = meta_do_pvsyst(lido) if lido else (anterior.get("meta_pvsyst") if sha and sha == anterior.get("sha") else None)
    base = anterior.get("meta") or do_pvsyst
    feitas = mudancas(base, meta)
    if do_pvsyst:
        origem = "PVsyst" if not mudancas(do_pvsyst, meta) else "PVsyst editado"
    else:
        origem = "manual"
    agora = datetime.now(_BRT).strftime("%d/%m/%Y %H:%M")
    reg = dict(anterior)
    reg.update({"usina": usina, "ano": ano, "meta": meta, "origem": origem, "salvo_em": agora, "salvo_por": quem})
    if lido:
        reg.update({"sha": sha, "arquivo": nome_arquivo, "projeto": lido.get("projeto"), "kwp": lido.get("kwp"),
                    "versao": lido.get("versao"), "simulado_em": lido.get("simulado_em"), "pr_ano": lido.get("pr_ano"),
                    "energia_ano_kwh": lido.get("energia_ano_kwh"), "meta_pvsyst": do_pvsyst})
    elif not do_pvsyst:
        for k in ("sha", "arquivo", "projeto", "kwp", "versao", "simulado_em", "pr_ano", "energia_ano_kwh", "meta_pvsyst"):
            reg.pop(k, None)
    reg["edicoes"] = (anterior.get("edicoes") or []) + [{"quando": agora, "quem": quem, "origem": origem, "ano": ano,
                                                         "arquivo": nome_arquivo if lido else "", "mudancas": feitas}]
    d[usina] = reg
    caminho = _arquivo_salvas(raiz)
    with open(caminho + ".tmp", "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(caminho + ".tmp", caminho)
    return reg


# ── a meta de hoje (as abas Info Mensal e Info Geral do BD_Performance, no banco) ───────────────────────────────────
_CACHE = {}
TTL_META_S = 600


def meta_atual(base, sessao) -> dict:
    """{"mensal": {usina: {"AAAA-MM": linha}}, "geral": {usina: {kwp, cliente}}, "usinas": [não Thopen], "erro"} da Info
    Mensal e da Info Geral do banco, guardado 10 min. A Thopen fica fora da lista: ela manda a própria meta."""
    c = _CACHE.get("meta")
    if c and time.time() - c["lido_em"] < TTL_META_S:
        return c
    from ..dados import livros
    try:
        a = livros.abas(base, sessao, "bd_performance")
        mensal, geral = {}, {}
        for x in livros._linhas(base, sessao, a["Info Mensal"]) if "Info Mensal" in a else []:
            u, mes = str(x.get("Usina") or "").strip(), str(x.get("Mês") or "")[:7]
            if u and re.fullmatch(r"\d{4}-\d{2}", mes):
                mensal.setdefault(u, {})[mes] = x
        for x in livros._linhas(base, sessao, a["Info Geral"]) if "Info Geral" in a else []:
            u = str(x.get("Usina") or "").strip()
            if not u:
                continue
            kwp = next((_num(v) for k, v in x.items() if "potenc" in norm(k) and "kwp" in norm(k) and _num(v)), None)
            geral[u] = {"kwp": kwp, "cliente": str(x.get("Cliente") or "").strip()}
        def cliente(u):
            return (geral.get(u) or {}).get("cliente") or next((str(r.get("Cliente") or "") for r in mensal.get(u, {}).values()), "")
        usinas = sorted((u for u in set(mensal) | set(geral) if "thopen" not in norm(cliente(u))), key=norm)
        c = {"mensal": mensal, "geral": geral, "usinas": usinas, "clientes": {u: cliente(u) for u in usinas},
             "lido_em": time.time(), "erro": ""}
    except Exception as ex:      # noqa: BLE001 — sem a meta de hoje, a tela compara com nada e diz
        erro = f"{type(ex).__name__}: {str(ex)[:160]}"
        return dict(c, erro=erro) if c else {"mensal": {}, "geral": {}, "usinas": [], "clientes": {}, "lido_em": None,
                                            "erro": erro}
    _CACHE["meta"] = c
    return c


def meta_de_hoje(mensal_usina: dict, ano: int) -> list[dict]:
    """A meta que a Info Mensal tem hoje para os 12 meses do ano (P50, PR, IPOA, GHI): é só a meta, não o realizado."""
    def v(x, k):
        return _num(x.get(k)) if x.get(k) not in (None, "") else None
    out = []
    for m in range(1, 13):
        x = (mensal_usina or {}).get(f"{ano}-{m:02d}") or {}
        pr = v(x, "PR Previsto 1° Ano (%)")
        out.append({"mes": m, "p50_mwh": v(x, "P50 (MWh)"), "p90_mwh": v(x, "P90"), "p75_mwh": v(x, "P75"),
                    "pr": pr / 100 if pr is not None and pr > 1.5 else pr,     # a aba guarda fração; se vier em %, igual
                    "ipoa_kwh_m2": v(x, "IPOA Previsto"), "ghi_kwh_m2": v(x, "GHI Previsto")})
    return out

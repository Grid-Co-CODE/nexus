"""Ligações entre as bases: o de_para calculado, os buracos e as decisões de quem corrige (tela Base → Ligações).

Pedido do Levi (04/10/2026): "quero uma tela para fazer os de-para pelo Nexus, quero que esses buracos de ligação fiquem
expostos para que possamos corrigir". Três tipos de buraco:
- chave de uma base que não liga a usina nenhuma (ex.: "Solier - Cascavel - CE" no Fracttal);
- ligação feita só pelo nome, que alguém precisa conferir;
- usina em operação que uma base não enxerga (ex.: as 36 da Faro Energy fora do Fracttal).

As decisões (ligar à mão, desligar, ignorar, ausência esperada) moram no arquivo de regras, fora do git (são nomes de
usina de cliente), e valem no próximo cálculo e no próximo envio ao banco. O cálculo guarda as fontes lidas
(`de_para_atual.json`): decidir não precisa buscar as bases de novo.
"""
import json
import os
import pickle
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

from . import banco as B
from . import casamento as K

_BRT = timezone(timedelta(hours=-3))
DADOS_PADRAO = Path(r"C:\GridcoAuto\nexus") if os.name == "nt" else Path(__file__).resolve().parents[2] / "dados"
BASE_API = "https://app.gridco.com.br/db_performace"
FRACTTAL = "Fracttal · Classificação 1"
# (sistema no de-para, workbook, aba, coluna do nome, coluna do código, cliente fixo)
FONTES_API = (
    ("BD_Performance · Base UFV", "bd_performance", "Base UFV", "Usina", "Código", None),
    ("Tickets · Base de dados - Usinas", "tickets_performance", "Base de dados - Usinas", "Usina", "Código da usina", None),
    ("BD_Thopen · Dados Gerais Usinas", "bd_thopen", "Dados Gerais Usinas", "Usina", None, "Thopen"),
)
# Geração em linhas (passo 6c do Kimball, 08/10/2026): cada ABA de geração (uma por usina, um inversor por coluna) é
# uma chave do de-para, e é por ela que o fato `nexus_geracao · fato_geracao_usina_dia` acha o usina_id. Medido em
# 08/10: o sistema de antes (`BD_Performance · Base UFV`, chaves "XXXX-ABC100") casava 0 das 53 abas do BD_Performance,
# porque a aba tem o NOME da usina; a ponte é a aba "Info Geral" da mesma base, que tem o nome e o "Código Fractal".
# (sistema no de-para, workbook, aba de referência da mesma base)
FONTES_ABA = (
    ("BD_Thopen · aba", "bd_thopen", "Dados Gerais Usinas"),
    ("BD_Performance · aba", "bd_performance", "Info Geral"),
)
# Base que só cobre um cliente: usina de outro cliente fora dela não é buraco.
SO_DO_CLIENTE = {"BD_Thopen · Dados Gerais Usinas": "Thopen", "BD_Thopen · aba": "Thopen"}
# Base que não cobre um cliente: as abas do BD_Performance não têm usina da Thopen (0 de 47 usinas ligadas em 08/10; a
# geração delas está no BD_Thopen). Sem isto, a aba "Usinas fora" listaria as 80 da Thopen em operação.
SEM_O_CLIENTE = {"BD_Performance · aba": "Thopen"}
# Como o de_para diz que a ligação veio só do nome (o que vale conferir na tela).
POR_NOME = ("nome", "única da cidade", "de-para de trackers")
TIPOS = ("ligar", "desligar", "ignorar", "ausencia")


# ── onde mora ──────────────────────────────────────────────────────────────────────────────────────────────────

def pasta_dados(config) -> Path:
    """Teste sem pasta própria não grava: em 04/10/2026 um teste escreveu no arquivo de regras de verdade."""
    if config.get("TESTING") and not config.get("NEXUS_DADOS"):
        raise RuntimeError("teste sem NEXUS_DADOS: recuso gravar na pasta de dados real")
    return Path(config.get("NEXUS_DADOS") or DADOS_PADRAO)


def caminho_regras(config) -> Path:
    if config.get("NEXUS_DE_PARA_REGRAS"):
        return Path(config["NEXUS_DE_PARA_REGRAS"])
    return pasta_dados(config) / "de_para_regras.json"


def caminho_atual(config) -> Path:
    return pasta_dados(config) / "de_para_atual.json"


def _gravar(p: Path, dado) -> None:
    """Grava inteiro ou nada, e guarda a versão anterior ao lado."""
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        p.with_suffix(p.suffix + ".anterior").write_bytes(p.read_bytes())
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(dado, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def _agora() -> str:
    return datetime.now(_BRT).isoformat(timespec="seconds")


# ── decisões ───────────────────────────────────────────────────────────────────────────────────────────────────

def carregar_regras(config) -> dict:
    p = caminho_regras(config)
    dado = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    return {t: list(dado.get(t) or []) for t in TIPOS} | {"sobre": dado.get("sobre", "")}


class DecisaoInvalida(ValueError):
    pass


def decidir(config, acao: str, sistema: str, chave=None, usina_id=None, cliente_id=None, motivo="", quem="admin"):
    """ligar | desligar | ignorar | ausencia | desfazer. Uma decisão nova para a mesma chave substitui a anterior."""
    r = carregar_regras(config)
    chave = None if chave is None else str(chave)
    if acao == "desfazer":
        tipo = motivo                      # na tela, o tipo da decisão vem no campo "motivo" do desfazer
        if tipo not in TIPOS:
            raise DecisaoInvalida("tipo de decisão desconhecido")
        r[tipo] = [d for d in r[tipo] if not _mesma(d, sistema, chave, usina_id, cliente_id)]
    elif acao in ("ligar", "desligar"):
        if not chave or usina_id is None:
            raise DecisaoInvalida("falta a chave ou a usina")
        for t in ("ligar", "desligar", "ignorar"):
            r[t] = [d for d in r[t] if not (d.get("sistema") == sistema and str(d.get("chave")) == chave)]
        r[acao].append({"sistema": sistema, "chave": chave, "usina_id": int(usina_id), "quem": quem, "quando": _agora()})
    elif acao == "ignorar":
        if not chave or not motivo.strip():
            raise DecisaoInvalida("diga por que ignorar")
        for t in ("ligar", "desligar", "ignorar"):
            r[t] = [d for d in r[t] if not (d.get("sistema") == sistema and str(d.get("chave")) == chave)]
        r["ignorar"].append({"sistema": sistema, "chave": chave, "motivo": motivo.strip(), "quem": quem, "quando": _agora()})
    elif acao == "ausencia":
        if usina_id is None and cliente_id is None or not motivo.strip():
            raise DecisaoInvalida("diga a usina (ou o cliente) e o motivo")
        r["ausencia"].append({"sistema": sistema, "usina_id": None if usina_id is None else int(usina_id),
                              "cliente_id": None if cliente_id is None else int(cliente_id),
                              "motivo": motivo.strip(), "quem": quem, "quando": _agora()})
    else:
        raise DecisaoInvalida("ação desconhecida")
    _gravar(caminho_regras(config), r)
    return r


def _mesma(d, sistema, chave, usina_id, cliente_id) -> bool:
    if d.get("sistema") != sistema:
        return False
    if chave is not None:
        return str(d.get("chave") or d.get("contem")) == chave
    if usina_id is not None:
        return d.get("usina_id") == int(usina_id)
    return cliente_id is not None and d.get("cliente_id") == int(cliente_id)


# ── fontes ─────────────────────────────────────────────────────────────────────────────────────────────────────

def _linhas_api(base, sid):
    import requests
    out, offset = [], 0
    while True:
        r = requests.get(f"{base}/api/sheets/{sid}/rows", params={"limit": 1000, "offset": offset}, timeout=60)
        r.raise_for_status()
        rows = r.json()
        rows = rows.get("rows", rows) if isinstance(rows, dict) else rows
        out += [dict(zip(x.get("headers") or [], x.get("values") or [])) for x in rows]
        if len(rows) < 1000:
            return out
        offset += 1000


def fontes(config) -> dict:
    """O Fracttal vem primeiro: o que ele liga vira a dica do de-para de trackers para o BD_Thopen."""
    if config.get("TESTING"):
        return config.get("NEXUS_LIGACOES_FONTES_TESTE") or {}
    import requests
    base = (config.get("GRIDCO_DB_API") or BASE_API).rstrip("/")
    abas = {(x["workbook_key"], x["sheet_name"]): x["id"] for x in requests.get(f"{base}/api/sheets", timeout=60).json()}
    out = {FRACTTAL: fracttal(config)}
    dicas = {}
    if ("de_para_trackers", "Resumo por usina") in abas:
        for t in _linhas_api(base, abas[("de_para_trackers", "Resumo por usina")]):
            if t.get("Fonte") == "Banco de Dados" and t.get("UFV Fracttal"):
                dicas[B.norm(re.sub(r"^\(\d+\)\s*", "", str(t["UFV Supervisório"])))] = t["UFV Fracttal"]
    lidas = {}
    for sistema, wb, aba, c_nome, c_cod, cliente in FONTES_API:
        itens = []
        lidas[(wb, aba)] = _linhas_api(base, abas[(wb, aba)])
        for d in lidas[(wb, aba)]:
            nome, cod = d.get(c_nome), d.get(c_cod) if c_cod else None
            if not nome:
                continue
            cod = cod if isinstance(cod, str) and cod.strip() else None
            it = {"chave": cod or nome, "codigo": cod, "nome": nome, "cliente": cliente or d.get("Cliente")}
            if not c_cod:          # base sem código (BD_Thopen): nome, cidade, estado e potência para o casamento
                mwp = d.get("Potência (MWp)")
                it.update({"nomes": [nome, d.get("Nome")], "cidade": d.get("Cidade"), "uf": d.get("Estado"),
                           "mwp": float(mwp) if isinstance(mwp, (int, float)) else None,
                           "dica": dicas.get(B.norm(nome)) or dicas.get(B.norm(d.get("Nome")))})
            itens.append(it)
        out[sistema] = itens
    for sistema, wb, ref in FONTES_ABA:      # depois das FONTES_API: o `igual_a` aponta chaves já casadas
        ids = {a: sid for (w, a), sid in abas.items() if w == wb}
        if (wb, ref) not in lidas:
            lidas[(wb, ref)] = _linhas_api(base, abas[(wb, ref)]) if (wb, ref) in abas else []
        out[sistema] = itens_abas(sistema, _primeiras_linhas(base, ids), lidas[(wb, ref)], dicas)
    return out


def _primeiras_linhas(base, ids: dict) -> dict:
    """{aba: [1ª linha]}: o cabeçalho e o nome na coluna "Usina" de cada aba, uma página de 1 linha por aba, em
    paralelo. Ler as abas inteiras levaria ~1 min (76 mil linhas em 08/10); a tela de Ligações espera por isto."""
    import requests
    from concurrent.futures import ThreadPoolExecutor

    def uma(item):
        aba, sid = item
        r = requests.get(f"{base}/api/sheets/{sid}/rows", params={"limit": 1, "offset": 0}, timeout=60)
        r.raise_for_status()
        rows = r.json()
        rows = rows.get("rows", rows) if isinstance(rows, dict) else rows
        return aba, [dict(zip(x.get("headers") or [], x.get("values") or [])) for x in rows[:1]]

    with ThreadPoolExecutor(max_workers=6) as ex:
        return dict(ex.map(uma, ids.items()))


def itens_abas(sistema: str, primeiras: dict, referencia: list, dicas: dict | None = None) -> list[dict]:
    """As chaves de um sistema de aba (`FONTES_ABA`): uma por aba de GERAÇÃO (o mesmo critério do fato,
    `nexus.dados.geracao.abas_de_geracao`), e a chave é o nome da aba. `primeiras` = {aba: [1ª linha]};
    `referencia` = as linhas da aba de referência da mesma base (a 3ª coluna de `FONTES_ABA`).
    - Referência que já é sistema do de-para (o "Dados Gerais Usinas" do BD_Thopen): a aba cujo nome, ou a coluna
      Usina, é o de uma linha dela é a MESMA usina daquela chave: vai `igual_a`, e herda a ligação e as decisões da tela
      (98 de 100 abas em 08/10). Leva também cidade, estado, potência e a dica, para o casamento quando ela não liga.
    - Referência que não é sistema (a "Info Geral" do BD_Performance, que tem o nome e o "Código Fractal"): a aba em
      forma de código ("ABC100") é o próprio código; a aba com nome leva o código da Info Geral como `codigo` +
      `codigo_de` (53 de 53 abas acham a linha em 08/10) e o cliente dela, para o casamento quando o código não liga.
    Nome que está em 2 linhas da referência não é ponte: ligação errada é pior que faltando."""
    from ..dados.geracao import abas_de_geracao
    wb_ref = next(((w, r) for s, w, r in FONTES_ABA if s == sistema), None)
    sistema_ref = next((s for s, w, a, *_ in FONTES_API if (w, a) == wb_ref), None)
    cliente_fixo = SO_DO_CLIENTE.get(sistema)
    idx = defaultdict(list)
    for d in referencia or ():
        if d.get("Usina") not in (None, ""):
            idx[B.norm(d["Usina"])].append(d)
    out = []
    for aba, linhas, _cols in abas_de_geracao(primeiras):
        na_coluna = next((str(l["Usina"]).strip() for l in linhas if l.get("Usina") not in (None, "")), "")
        nomes = [aba] + ([na_coluna] if na_coluna and B.norm(na_coluna) != B.norm(aba) else [])
        par = next((idx[B.norm(n)][0] for n in nomes if len(idx.get(B.norm(n), ())) == 1), None)
        it = {"chave": aba, "nome": aba, "nomes": nomes}
        if cliente_fixo:
            it["cliente"] = cliente_fixo
        if sistema_ref:
            if par:
                mwp = par.get("Potência (MWp)")
                it.update({"igual_a": (sistema_ref, par["Usina"]), "cidade": par.get("Cidade"),
                           "uf": par.get("Estado"), "mwp": float(mwp) if isinstance(mwp, (int, float)) else None})
            it["dica"] = next((dicas[B.norm(n)] for n in nomes if B.norm(n) in (dicas or {})), None)
        else:
            if re.fullmatch(r"[A-Z]{3}\d{3}", aba.strip()):
                it["codigo"] = aba.strip()
            elif par and str(par.get("Código Fractal") or "").strip():
                it.update({"codigo": str(par["Código Fractal"]).strip(), "codigo_de": wb_ref[1]})
            if par and par.get("Cliente") and not cliente_fixo:
                it["cliente"] = par["Cliente"]
        out.append(it)
    return out


def usina_do_caminho(caminho):
    """"// Thopen/ Thopen - Brodowski 1 - SP/ Cabine 1/" -> ("Thopen", "Brodowski 1"). Só o pedaço "Cliente - Usina - UF"."""
    for p in str(caminho or "").split("/"):
        m = re.fullmatch(r"\s*(.+?)\s+-\s+(.+?)\s+-\s+[A-Z]{2}\s*", p)
        if m:
            return m.group(1), m.group(2)
    return None


def fracttal(config) -> list[dict]:
    """Usinas do Fracttal ("Cliente - Usina - UF") com o código tirado dos códigos de equipamento das tarefas: a foto
    mais nova que o motor do PCM gravou (pasta do PCM ou rodadas do Nexus). Sem foto, só a lista de ativos (pelo nome)."""
    from ..pcm import geracao as G
    trab, origem = G.pasta_trabalho(config), G.pasta_origem(config)
    fotos = [p for p in ([Path(origem) / ".cache_semanal_api.pkl"] if origem else [])
             + list((Path(trab) / "geracoes").glob("*/.cache_semanal_api.pkl")) if p.exists()]
    if fotos:
        foto = max(fotos, key=lambda p: p.stat().st_mtime)
        with open(foto, "rb") as f:          # arquivo do próprio motor do PCM, gravado nesta máquina ou na pasta do PCM
            df = pickle.load(f)["df"]
        itens = []
        df = df.assign(_u=df["Ativo Classificação 1"].fillna("").astype(str).str.strip())
        for usina, g in df[df["_u"] != ""].groupby("_u"):
            cods = Counter(c for c in (B.codigo_do_equipamento(x) for x in g["Código"]) if c).most_common(1)
            itens.append({"chave": usina, "nome": usina, "codigo": cods[0][0] if cods else None, "tarefas": len(g)})
        # Ativo sem "Classificação 1" (04/10: 584 tarefas, Brodowski e Nobres entre elas). A usina sai do código do
        # equipamento ("BWK100-INVR1" é Brodowski) e, sem código que case, da "Localização ou parte de" do próprio
        # ativo ("// Thopen/ Thopen - Brodowski 1 - SP/ Cabine 1/"): é assim que "BWK200" e "Transformador 2" acham a usina.
        sem = df[df["_u"] == ""]
        for cod, g in sem.groupby(sem["Código"].map(lambda x: B.codigo_do_equipamento(x)
                                                    or "-".join(str(x or "sem código").split("-")[:2]))):
            it = {"chave": f"(sem Classificação 1) {cod}", "codigo": cod, "tarefas": len(g)}
            locais = Counter(m for m in (usina_do_caminho(x) for x in g["Localização ou parte de"]) if m).most_common(1)
            if locais:
                cliente, usina = locais[0][0]
                it.update({"cliente": cliente, "nomes": [usina], "origem": "localização no Fracttal",
                           "nome": f"{cliente} - {usina}"})
            itens.append(it)
        return itens
    for pasta in (trab, origem):
        cache = Path(pasta or "") / "_ativos_classificacao_cache.json"
        if pasta and cache.exists():
            nomes = sorted({v[0] for v in json.loads(cache.read_text(encoding="utf-8")).values() if v and v[0]})
            return [{"chave": n, "nome": n} for n in nomes]
    return []


# ── cálculo ────────────────────────────────────────────────────────────────────────────────────────────────────

def calcular(config, srv, fs: dict | None = None) -> dict:
    """Lê as bases (ou usa `fs`, as fontes já lidas), aplica as decisões e guarda o resultado."""
    fs = fontes(config) if fs is None else fs
    res = {"gerado_em": _agora() if fs is not None else None, "fontes": fs,
           "linhas": B.de_para(srv, fs, carregar_regras(config))}
    _gravar(caminho_atual(config), res)
    return res


def reaplicar(config, srv) -> dict | None:
    """Depois de uma decisão: as mesmas fontes, as regras novas. Sem buscar nada na rede."""
    atual = ler(config)
    if not atual:
        return None
    atual["linhas"] = B.de_para(srv, atual["fontes"], carregar_regras(config))
    _gravar(caminho_atual(config), atual)
    return atual


def ler(config) -> dict | None:
    p = caminho_atual(config)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


# ── o que a tela mostra ────────────────────────────────────────────────────────────────────────────────────────

def _usinas(srv) -> list[dict]:
    out = []
    for u in srv.registros("usinas"):
        cliente = srv.titulo_de("clientes", u.valor("cliente"))
        pot = u.valor("potencia_contratual")
        out.append({"id": B._id(u.id), "nome": u.valor("nome"), "cliente": cliente,
                    "cliente_id": B._id(u.valor("cliente")) if isinstance(u.valor("cliente"), str) else None,
                    "titulo": f"{cliente} - {u.valor('nome')}" if cliente else str(u.valor("nome")),
                    "codigo": u.valor("codigo") or "", "cidade": u.valor("cidade"), "uf": u.valor("uf"),
                    "status": u.valor("status") or "", "equipe": srv.titulo_de("equipes", u.valor("equipe")),
                    "mwp": float(pot) if isinstance(pot, (int, float)) and not isinstance(pot, bool) else None})
    return out


def _sem_cliente_e_uf(nome, cliente) -> str:
    s = str(nome or "")
    if cliente and B.norm(s).startswith(B.norm(cliente)):
        s = s[len(str(cliente)):] if s.lower().startswith(str(cliente).lower()) else s.split(" - ", 1)[-1]
    s = re.sub(r"^\s*-\s*", "", s)
    return re.sub(r"\s*-\s*[A-Z]{2}\s*$", "", s).strip()


def sugestoes(item: dict, usinas: list[dict], n: int = 3) -> list[dict]:
    """As usinas do cadastro mais parecidas com uma chave sem par: código (letras do "AAA999"), nome, cliente e cidade.
    Só sugere; quem liga é a pessoa."""
    cod = B.sufixo_codigo(item.get("codigo") or (item.get("chave") if re.fullmatch(r"[A-Z0-9-]+", str(item.get("chave"))) else ""))
    nome, cliente = item.get("nome") or (item.get("nomes") or [item.get("chave")])[0], item.get("cliente")
    m = re.fullmatch(r"\s*(.+?)\s+-\s+(.+?)(?:\s+-\s+[A-Z]{2})?\s*", str(nome or ""))
    if not cliente and m:                   # Fracttal: "Athon - Matões 1 - MA" traz o cliente no próprio nome
        cliente, nome = m.group(1), m.group(2)
    nome_item = " ".join(K.palavras(_sem_cliente_e_uf(nome, cliente)))
    cli = B.norm(cliente or "")
    primeiro = next((w for w in nome_item.split() if w.isdigit()), None)
    mwp = item.get("mwp")
    out = []
    for u in usinas:
        if cli and B.norm(u["cliente"]) != cli:
            continue                        # E1 não é Thopen (Levi, 04/10): nem como sugestão
        nums_u = {w for v in K.variantes(u["nome"]) for w in v.split() if w.isdigit()}
        # As mesmas travas do casamento automático (achadas na tela real, 04/10):
        if primeiro and nums_u and primeiro not in nums_u:
            continue                        # número diferente: "Marajoara 2" (e "Marajoara 2 1") não é a "Marajoara 1"
        if item.get("cidade") and K.mesma_cidade(item["cidade"], u["cidade"]) is False:
            continue                        # "Ouro Branco I" de Bandeirantes/PR não é a "Ouro Branco" de AL
        if mwp and u.get("mwp") and abs(u["mwp"] - mwp) > 0.4 * max(u["mwp"], mwp):
            continue                        # "AP. do Taboado" (0,41 MWp) não é a "Aparecida do Taboado 1 e 2" (2,58)
        nota = 0.0
        cu = B.sufixo_codigo(u["codigo"])
        if cod and cu and cod == cu:
            nota += 0.6
        nome_u = " ".join(K.palavras(u["nome"]))
        semelhanca = SequenceMatcher(None, nome_item, nome_u).ratio() if nome_item and nome_u else 0
        if semelhanca >= 0.78:              # abaixo disso é coincidência de letra: na tela real (04/10), "Andradina"
            nota += 0.6 * semelhanca        # sugeria "Canarana" e "Anápolis" sugeria "Fernandópolis", a 53%
        if cli:
            nota += 0.15
        if item.get("cidade") and K.mesma_cidade(item["cidade"], u["cidade"]):
            nota += 0.15
        if nota >= 0.5:
            out.append({"id": u["id"], "titulo": u["titulo"], "codigo": u["codigo"], "nota": round(min(nota, 1) * 100)})
    return sorted(out, key=lambda x: -x["nota"])[:n]


def _por_nome(como: str) -> bool:
    return any(como.startswith(p) for p in POR_NOME)


def panorama(srv, atual: dict | None, regras: dict) -> dict:
    """Os números por base e as quatro listas da tela."""
    usinas = _usinas(srv)
    por_id = {u["id"]: u for u in usinas}
    if not atual:
        return {"usinas": usinas, "sistemas": [], "buracos": [], "por_nome": [], "ausencias": {}, "decisoes": [],
                "gerado_em": None}
    itens = {(s, str(it["chave"])): it for s, its in atual["fontes"].items() for it in its}
    est = defaultdict(lambda: {"ligadas": set(), "buracos": set(), "ignoradas": set(), "usinas": set()})
    buracos, por_nome = [], []
    for uid, sistema, chave, como in atual["linhas"]:
        e, chave = est[sistema], str(chave)
        if como.startswith("ignorado"):
            e["ignoradas"].add(chave)
        elif uid is None:
            e["buracos"].add(chave)
            it = itens.get((sistema, chave), {"chave": chave})
            buracos.append({"sistema": sistema, "chave": chave, "motivo": como, "tarefas": it.get("tarefas"),
                            "nome": it.get("nome"), "cidade": it.get("cidade"),
                            "sugestoes": sugestoes(it, usinas)})
        else:
            e["ligadas"].add(chave)
            e["usinas"].add(uid)
            if _por_nome(como):
                por_nome.append({"sistema": sistema, "chave": chave, "usina_id": uid, "como": como,
                                 "usina": por_id.get(uid, {}).get("titulo", uid)})
    ausencias, n_aus = {}, {}
    for sistema, e in est.items():
        if sistema == "BD_Operações":
            continue
        so, sem = SO_DO_CLIENTE.get(sistema), SEM_O_CLIENTE.get(sistema)
        esperadas = {(d.get("usina_id"), d.get("cliente_id")) for d in regras["ausencia"] if d.get("sistema") == sistema}
        fora = [u for u in usinas if u["status"] == "OPERAÇÃO" and u["id"] not in e["usinas"]
                and (not so or B.norm(u["cliente"]) == B.norm(so))
                and not (sem and B.norm(u["cliente"]) == B.norm(sem))
                and (u["id"], None) not in esperadas and (None, u["cliente_id"]) not in esperadas]
        grupos = defaultdict(list)
        for u in fora:
            grupos[(u["cliente"], u["cliente_id"])].append(u)
        ausencias[sistema] = sorted(grupos.items(), key=lambda kv: -len(kv[1]))
        n_aus[sistema] = len(fora)
    sistemas = []
    for sistema, e in sorted(est.items(), key=lambda kv: (kv[0] != "BD_Operações", kv[0])):
        total = len(e["ligadas"]) + len(e["buracos"])
        sistemas.append({"nome": sistema, "ligadas": len(e["ligadas"]), "total": total, "buracos": len(e["buracos"]),
                         "ignoradas": len(e["ignoradas"]), "fora": n_aus.get(sistema, 0),
                         "pct": round(100 * len(e["ligadas"]) / total, 1) if total else 100.0})
    decisoes = []
    for tipo in TIPOS:
        for d in regras[tipo]:
            if tipo == "ignorar" and not d.get("chave"):
                alvo = f"contém \"{d.get('contem')}\""
            elif tipo == "ausencia":
                alvo = (por_id.get(d.get("usina_id"), {}).get("titulo") if d.get("usina_id") is not None
                        else f"todas do cliente {next((u['cliente'] for u in usinas if u['cliente_id'] == d.get('cliente_id')), d.get('cliente_id'))}")
            else:
                alvo = d.get("chave")
            decisoes.append({"tipo": tipo, "sistema": d.get("sistema") or "todas", "alvo": alvo,
                             "usina": por_id.get(d.get("usina_id"), {}).get("titulo") if tipo in ("ligar", "desligar") else "",
                             "motivo": d.get("motivo", ""), "quem": d.get("quem", ""), "quando": d.get("quando", ""),
                             "chave": d.get("chave") or d.get("contem"), "usina_id": d.get("usina_id"),
                             "cliente_id": d.get("cliente_id")})
    return {"usinas": usinas, "sistemas": sistemas, "buracos": buracos, "por_nome": por_nome, "ausencias": ausencias,
            "decisoes": decisoes, "gerado_em": atual.get("gerado_em")}

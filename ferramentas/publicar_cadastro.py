"""Publica o cadastro do Nexus no PostgreSQL (workbook `cadastro_nexus` da API db_performace). Ver nexus/cadastro/banco.py.

    python ferramentas/publicar_cadastro.py --ensaio   monta e confere, grava só o xlsx local (nada vai ao banco)
    python ferramentas/publicar_cadastro.py            publica

Lê do .env do Nexus: NEXUS_CHAVE_CADASTRO (abre o cadastro e cifra o sensível) e GRIDCO_SQL_TOKEN (escrita na API).
Nenhum dos dois é impresso.
"""
import argparse
import json
import pickle
import re
import sys
from collections import Counter
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from nexus.cadastro import banco as B  # noqa: E402
from nexus.cadastro.armazem import ArmazemLocal  # noqa: E402
from nexus.cadastro.cifra import Cofre  # noqa: E402
from nexus.cadastro.servico import Servico  # noqa: E402
from nexus.cadastro.telas import ARMAZEM_PADRAO  # noqa: E402
from nexus.config import ler_ambiente  # noqa: E402
from nexus.pcm import geracao as G  # noqa: E402

BASE = "https://app.gridco.com.br/db_performace"
# (sistema no de-para, workbook, aba, coluna do nome, coluna do código, cliente fixo)
FONTES_API = (
    ("BD_Performance · Base UFV", "bd_performance", "Base UFV", "Usina", "Código", None),
    ("Tickets · Base de dados - Usinas", "tickets_performance", "Base de dados - Usinas", "Usina", "Código da usina", None),
    ("BD_Thopen · Dados Gerais Usinas", "bd_thopen", "Dados Gerais Usinas", "Usina", None, "Thopen"),
)


def _linhas(base, sid):
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


def fontes(base, cfg) -> dict:
    """O Fracttal vem primeiro: o que ele liga vira a dica do de-para de trackers para o BD_Thopen."""
    abas = {(x["workbook_key"], x["sheet_name"]): x["id"] for x in requests.get(f"{base}/api/sheets", timeout=60).json()}
    out = {"Fracttal · Classificação 1": fracttal(cfg)}
    # de-para de trackers, fonte "Banco de Dados": "(308) Ipixuna 1" -> "Thopen - Ipixuna 1 e 2 - PA" (já conferido)
    dicas = {}
    if ("de_para_trackers", "Resumo por usina") in abas:
        for t in _linhas(base, abas[("de_para_trackers", "Resumo por usina")]):
            if t.get("Fonte") == "Banco de Dados" and t.get("UFV Fracttal"):
                dicas[B.norm(re.sub(r"^\(\d+\)\s*", "", str(t["UFV Supervisório"])))] = t["UFV Fracttal"]
    for sistema, wb, aba, c_nome, c_cod, cliente in FONTES_API:
        itens = []
        for d in _linhas(base, abas[(wb, aba)]):
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
    return out


def _usina_do_caminho(caminho):
    """"// Thopen/ Thopen - Brodowski 1 - SP/ Cabine 1/" -> ("Thopen", "Brodowski 1"). Só o pedaço "Cliente - Usina - UF"."""
    for p in str(caminho or "").split("/"):
        m = re.fullmatch(r"\s*(.+?)\s+-\s+(.+?)\s+-\s+[A-Z]{2}\s*", p)
        if m:
            return m.group(1), m.group(2)
    return None


def regras(env) -> list:
    """Decisões que tiram linhas da conta (teste, tarefa interna, usina que não entra no BD). Moram em dados/, fora do
    git: são nomes de usina de cliente."""
    p = Path(env.get("NEXUS_DE_PARA_REGRAS") or (Path(r"C:\GridcoAuto\nexus") if sys.platform == "win32"
                                                 else RAIZ / "dados") / "de_para_regras.json")
    return json.loads(p.read_text(encoding="utf-8")).get("ignorar", []) if p.exists() else []


def fracttal(cfg) -> list[dict]:
    """Usinas do Fracttal ("Cliente - Usina - UF") com o código tirado dos códigos de equipamento das tarefas: a foto
    mais nova que o motor do PCM gravou (pasta do PCM ou rodadas do Nexus). Sem foto, só a lista de ativos (pelo nome)."""
    trab, origem = G.pasta_trabalho(cfg), G.pasta_origem(cfg)
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
            itens.append({"chave": usina, "nome": usina, "codigo": cods[0][0] if cods else None})
        # Ativo sem "Classificação 1" (04/10: 584 tarefas, Brodowski e Nobres entre elas). A usina sai do código do
        # equipamento ("BWK100-INVR1" é Brodowski) e, sem código que case, da "Localização ou parte de" do próprio
        # ativo ("// Thopen/ Thopen - Brodowski 1 - SP/ Cabine 1/"): é assim que "BWK200" e "Transformador 2" acham a usina.
        sem = df[df["_u"] == ""]
        for cod, g in sem.groupby(sem["Código"].map(lambda x: B.codigo_do_equipamento(x)
                                                    or "-".join(str(x or "sem código").split("-")[:2]))):
            it = {"chave": f"(sem Classificação 1) {cod}", "codigo": cod}
            locais = Counter(m for m in (_usina_do_caminho(x) for x in g["Localização ou parte de"]) if m).most_common(1)
            if locais:
                cliente, usina = locais[0][0]
                it.update({"cliente": cliente, "nomes": [usina], "origem": "localização no Fracttal"})
            itens.append(it)
        print(f"Fracttal: {len(itens)} usinas da foto {foto.parent.name} ({foto.stat().st_size // 1024} KB), "
              f"{len(sem)} tarefas sem Classificação 1")
        return itens
    for pasta in (trab, origem):
        cache = Path(pasta or "") / "_ativos_classificacao_cache.json"
        if pasta and cache.exists():
            nomes = sorted({v[0] for v in json.loads(cache.read_text(encoding="utf-8")).values() if v and v[0]})
            return [{"chave": n, "nome": n} for n in nomes]
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ensaio", action="store_true", help="não envia; grava o xlsx local e confere")
    a = ap.parse_args()
    env = ler_ambiente()
    if not env.get("NEXUS_CHAVE_CADASTRO"):
        sys.exit("falta NEXUS_CHAVE_CADASTRO no .env do Nexus")
    cofre = Cofre(env["NEXUS_CHAVE_CADASTRO"])
    srv = Servico(ArmazemLocal(Path(env.get("NEXUS_ARMAZEM_LOCAL") or ARMAZEM_PADRAO)), cofre)
    base = (env.get("GRIDCO_DB_API") or BASE).rstrip("/")
    anteriores = B.ler_anteriores(base)
    t = B.montar(srv, cofre, fontes(base, env), anteriores, regras(env))
    for aba, (cab, linhas) in t.items():
        print(f"{aba}: {len(linhas)} linhas, {len(cab)} colunas")
    dp = t["de_para"][1]
    print("de-para por sistema:", dict(Counter(l[1] for l in dp)))
    print("casou por:", dict(Counter(l[3] for l in dp)))
    conteudo = B.xlsx_bytes(t)
    if a.ensaio:
        destino = (Path(env.get("NEXUS_PCM_TRABALHO") or G.TRABALHO_PADRAO).parent / "cadastro_nexus_ensaio.xlsx")
        destino.write_bytes(conteudo)
        print("ensaio gravado em", destino)
        return
    if not env.get("GRIDCO_SQL_TOKEN"):
        sys.exit("falta GRIDCO_SQL_TOKEN no .env do Nexus")
    print("API:", B.sincronizar(conteudo, base=base, token=env["GRIDCO_SQL_TOKEN"]))


if __name__ == "__main__":
    main()

"""Publica o cadastro do Nexus no PostgreSQL (workbook `cadastro_nexus` da API db_performace). Ver nexus/cadastro/banco.py.

    python ferramentas/publicar_cadastro.py --ensaio   monta e confere, grava só o xlsx local (nada vai ao banco)
    python ferramentas/publicar_cadastro.py            publica

As bases são lidas e casadas por nexus/cadastro/ligacoes.py, o mesmo módulo da tela Base → Ligações; as decisões
tomadas na tela (ligar, desligar, ignorar) entram aqui também. Lê do .env do Nexus: NEXUS_CHAVE_CADASTRO (abre o
cadastro e cifra o sensível) e GRIDCO_SQL_TOKEN (escrita na API). Nenhum dos dois é impresso.
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from nexus.cadastro import banco as B  # noqa: E402
from nexus.cadastro import ligacoes as L  # noqa: E402
from nexus.cadastro.armazem import ArmazemLocal  # noqa: E402
from nexus.cadastro.cifra import Cofre  # noqa: E402
from nexus.cadastro.servico import Servico  # noqa: E402
from nexus.cadastro.telas import ARMAZEM_PADRAO  # noqa: E402
from nexus.config import ler_ambiente  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ensaio", action="store_true", help="não envia; grava o xlsx local e confere")
    a = ap.parse_args()
    env = ler_ambiente()
    if not env.get("NEXUS_CHAVE_CADASTRO"):
        sys.exit("falta NEXUS_CHAVE_CADASTRO no .env do Nexus")
    cofre = Cofre(env["NEXUS_CHAVE_CADASTRO"])
    srv = Servico(ArmazemLocal(Path(env.get("NEXUS_ARMAZEM_LOCAL") or ARMAZEM_PADRAO)), cofre)
    base = (env.get("GRIDCO_DB_API") or L.BASE_API).rstrip("/")
    atual = L.calcular(env, srv)                       # lê as bases e guarda para a tela
    t = B.montar(srv, cofre, atual["fontes"], B.ler_anteriores(base), L.carregar_regras(env))
    for aba, (cab, linhas) in t.items():
        print(f"{aba}: {len(linhas)} linhas, {len(cab)} colunas")
    dp = t["de_para"][1]
    print("de-para por sistema:", dict(Counter(l[1] for l in dp)))
    print("casou por:", dict(Counter(l[3] for l in dp)))
    conteudo = B.xlsx_bytes(t)
    if a.ensaio:
        destino = L.pasta_dados(env) / "cadastro_nexus_ensaio.xlsx"
        destino.write_bytes(conteudo)
        print("ensaio gravado em", destino)
        return
    if not env.get("GRIDCO_SQL_TOKEN"):
        sys.exit("falta GRIDCO_SQL_TOKEN no .env do Nexus")
    print("API:", B.sincronizar(conteudo, base=base, token=env["GRIDCO_SQL_TOKEN"]))


if __name__ == "__main__":
    main()

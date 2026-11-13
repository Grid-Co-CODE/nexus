"""Publica o cadastro do Nexus no PostgreSQL (workbook `cadastro_nexus` da API db_performace). Ver nexus/cadastro/banco.py.

    python ferramentas/publicar_cadastro.py --ensaio   monta e confere, grava só o xlsx local (nada vai ao banco)
    python ferramentas/publicar_cadastro.py            publica
    ... --bases-guardadas   usa as bases da última leitura da tela Base → Ligações, sem ler de novo (é o que o botão
                            "Publicar no banco" da tela faz)
    ... --aceitar-trocas MARCA   publica mesmo com chaves que trocariam de usina: a marca é a que a recusa (ou o
                            ensaio) mostrou, e só vale para aquela lista

Antes de enviar, confere com o de-para que o BANCO tem, pelas mesmas três regras do botão da tela
(`banco.conferir_com_o_banco`, 12/11/2026): a ligação de chave que esta máquina não leu volta como estava; a chave que
ela leu e deixaria sem usina não publica; a que trocaria de usina por regra automática pede a marca. Até aquela data a
ferramenta enviava direto, e rodada no PC apagaria as ligações que só o servidor conhece (FAMA, plant_id).

`--bases-guardadas` existe porque a leitura das bases pode falhar numa máquina sem quebrar a publicação do cadastro: em
08/10/2026 a foto do Fracttal da pasta do PCM não abria neste PC (sem o pyarrow) e o ensaio da estrutura de campo parou
ali, antes de montar uma linha do cadastro.

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
    ap.add_argument("--bases-guardadas", action="store_true",
                    help="não lê as bases de novo: usa a última leitura da tela Ligações (de_para_atual.json)")
    ap.add_argument("--aceitar-trocas", metavar="MARCA", default="",
                    help="publica com as chaves que trocariam de usina; a marca é a que a recusa mostrou")
    a = ap.parse_args()
    env = ler_ambiente()
    if not env.get("NEXUS_CHAVE_CADASTRO"):
        sys.exit("falta NEXUS_CHAVE_CADASTRO no .env do Nexus")
    cofre = Cofre(env["NEXUS_CHAVE_CADASTRO"])
    srv = Servico(ArmazemLocal(Path(env.get("NEXUS_ARMAZEM_LOCAL") or ARMAZEM_PADRAO)), cofre)
    base = (env.get("GRIDCO_DB_API") or L.BASE_API).rstrip("/")
    atual = L.ler(env) if a.bases_guardadas else L.calcular(env, srv)     # lê as bases e guarda para a tela
    if not atual:
        sys.exit("não há bases guardadas: leia as bases na tela Base → Ligações (ou rode sem --bases-guardadas)")
    if a.bases_guardadas:
        print("bases guardadas, lidas em", atual.get("gerado_em"))
    t = B.montar(srv, cofre, atual["fontes"], B.ler_anteriores(base), L.carregar_regras(env))
    for aba, (cab, linhas) in t.items():
        print(f"{aba}: {len(linhas)} linhas, {len(cab)} colunas")
    # as três regras contra o de-para do banco, antes de montar o xlsx (as mantidas entram nele)
    c = B.conferir_com_o_banco(t, B.ler_de_para(base))
    dp = t["de_para"][1]
    print("de-para por sistema:", dict(Counter(l[1] for l in dp)))
    print("casou por:", dict(Counter(l[3] for l in dp)))
    print(f"ligações de chaves que esta máquina não leu, mantidas como estão no banco: {len(c['mantidas'])}")
    for d in c["perdidas"]:
        print(f"PERDERIA: {d.get('sistema')}: {d.get('chave_externa')} (no banco, usina {B._inteiro(d.get('usina_id'))})")
    marca = B.assinatura_das_trocas(c["trocas"]) if c["trocas"] else ""
    for x in c["trocas"]:
        print(f"TROCARIA: {x['sistema']}: {x['chave_externa']} (no banco, usina {x['de']}; aqui, usina {x['para']}, "
              f"por {x['casou_por']})")
    recusa = None
    if c["perdidas"]:
        recusa = (f"não publiquei: {len(c['perdidas'])} ligação(ões) do banco ficariam sem usina (as linhas PERDERIA "
                  "acima). Ligue na tela Base → Ligações, ou leia as bases de novo, e rode outra vez.")
    elif c["trocas"] and a.aceitar_trocas != marca:
        recusa = (f"não publiquei: {len(c['trocas'])} chave(s) trocariam de usina sem ninguém ter decidido (as linhas "
                  f"TROCARIA acima). Decida na tela Base → Ligações, ou aceite esta lista com --aceitar-trocas {marca}")
    conteudo = B.xlsx_bytes(t)
    if a.ensaio:
        destino = L.pasta_dados(env) / "cadastro_nexus_ensaio.xlsx"
        destino.write_bytes(conteudo)
        print("ensaio gravado em", destino)
        if recusa:
            print("o ensaio diz:", recusa)
        return
    if recusa:
        print(recusa)
        sys.exit(2)
    if not env.get("GRIDCO_SQL_TOKEN"):
        sys.exit("falta GRIDCO_SQL_TOKEN no .env do Nexus")
    print("API:", B.sincronizar(conteudo, base=base, token=env["GRIDCO_SQL_TOKEN"]))


if __name__ == "__main__":
    main()

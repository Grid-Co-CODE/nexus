"""A cópia do Radar de Fornecedores (zeladoria) para os três livros do Nexus. Imprime só contagens, nunca linhas.

    python ferramentas/copiar_zeladoria.py --sql --nomes <de_para_nomes.json>
        imprime a consulta de exportação, para colar no SQL Editor do Supabase (um SELECT só, nada muda lá); o resultado
        (uma célula com o JSON) se salva como arquivo, que é o --arquivo de baixo
    python ferramentas/copiar_zeladoria.py --arquivo <exportação.json> --nomes <de_para_nomes.json>
        o ensaio: monta os três livros com o dado real, cifra e NÃO grava
    python ferramentas/copiar_zeladoria.py --arquivo <exportação.json> --nomes <de_para_nomes.json> --gravar
        grava e confere cada livro

A exportação sai do SQL Editor do Supabase com um SELECT só (`nexus/zeladoria/copia.py`). O de-para de nomes é o mesmo
da limpeza do clone (`ferramentas/zeladoria_limpar_clone.py`). Os dois ficam FORA do repositório, que é público, e o
`--nomes` pode vir da variável NEXUS_ZELADORIA_DE_PARA do `.env`.

Uma máquina grava: até a troca, a cópia roda à mão, sempre na mesma máquina. Depois da troca ela não roda mais: quem grava
é a torre (desenho: docs/superpowers/specs/2026-11-03-zeladoria-no-nexus-design.md).
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from nexus.cadastro.cifra import Cofre  # noqa: E402
from nexus.cadastro.ligacoes import BASE_API  # noqa: E402
from nexus.zeladoria import copia  # noqa: E402


def main(argv=None) -> int:
    load_dotenv(RAIZ / ".env")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--arquivo", help="a exportação do Supabase (JSON)")
    p.add_argument("--sql", action="store_true", help="só imprime a consulta de exportação")
    p.add_argument("--nomes", default=os.environ.get("NEXUS_ZELADORIA_DE_PARA"), help="o de-para de nomes (JSON)")
    p.add_argument("--gravar", action="store_true", help="grava os três livros (sem isto, é o ensaio)")
    a = p.parse_args(argv)
    if not a.nomes:
        print("parei: falta o de-para de nomes (--nomes ou NEXUS_ZELADORIA_DE_PARA no .env)", file=sys.stderr)
        return 1
    de_para = json.loads(Path(a.nomes).read_text(encoding="utf-8"))
    if a.sql:
        print(copia.sql_exportacao(de_para))
        return 0
    if not a.arquivo:
        print("parei: falta o --arquivo com a exportação do Supabase", file=sys.stderr)
        return 1
    exp = json.loads(Path(a.arquivo).read_text(encoding="utf-8"))
    cofre = Cofre(os.environ.get("NEXUS_CHAVE_CADASTRO", ""))
    base = (os.environ.get("GRIDCO_DB_API") or BASE_API).rstrip("/")
    t0 = time.time()
    rel = copia.copiar(exp, de_para=de_para, cofre=cofre, base=base, token=os.environ.get("GRIDCO_SQL_TOKEN", ""),
                       sessao=requests.Session(), gravar=a.gravar, agora=datetime.now(timezone.utc))
    print(f"exportada em {rel['exportado_em']} | {'GRAVOU' if rel['gravou'] else 'ensaio (nada gravado)'} | "
          f"{time.time() - t0:.1f} s | maior célula {rel['maior_celula']} | valores renomeados {rel['trocas']}")
    diferentes = 0
    for aba, n in sorted(rel["abas"].items()):
        marca = "" if not rel["gravou"] or n["origem"] == n["nexus"] else "  <-- DIFERENTE"
        diferentes += bool(marca)
        print(f"  {aba:28} origem {n['origem']:5}  nexus {'-' if n['nexus'] is None else n['nexus']:>5}{marca}")
    return 1 if diferentes else 0


if __name__ == "__main__":
    sys.exit(main())

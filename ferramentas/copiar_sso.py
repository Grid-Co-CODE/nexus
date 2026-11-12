"""Copia o banco do SSO da zeladoria (exportado do Supabase em partes) para os livros cifrados do Nexus.

Uso (com o .env do Nexus):
  python ferramentas/copiar_sso.py --pasta <pasta com os sso_exportacao_*.json>            ensaio: só conta
  python ferramentas/copiar_sso.py --pasta <pasta com os sso_exportacao_*.json> --gravar   grava e confere

As partes saem do SQL Editor do Supabase (`nexus/sso/CLAUDE.md`, "A cópia") e ficam FORA do repositório: têm CPF,
telefone, e-mail e assinaturas. Imprime só contagens.
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
from nexus.sso import copia  # noqa: E402


def main(argv=None) -> int:
    load_dotenv(RAIZ / ".env")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--pasta", required=True, help="a pasta com as partes da exportação (sso_exportacao_*.json)")
    p.add_argument("--gravar", action="store_true", help="grava os livros (sem isto, é o ensaio)")
    p.add_argument("--forcar", action="store_true", help="grava mesmo depois de o Nexus ter gravado mudanças do SSO")
    a = p.parse_args(argv)
    arquivos = sorted(Path(a.pasta).glob("sso_exportacao_*.json"))
    if not arquivos:
        print("parei: nenhuma parte sso_exportacao_*.json na pasta", file=sys.stderr)
        return 1
    partes = []
    for f in arquivos:
        j = json.loads(f.read_text(encoding="utf-8"))
        partes += j if isinstance(j, list) else [j]
    cofre = Cofre(os.environ.get("NEXUS_CHAVE_CADASTRO", ""))
    base = (os.environ.get("GRIDCO_DB_API") or BASE_API).rstrip("/")
    t0 = time.time()
    try:
        rel = copia.copiar(partes, cofre=cofre, base=base, token=os.environ.get("GRIDCO_SQL_TOKEN", ""),
                           sessao=requests.Session(), gravar=a.gravar, agora=datetime.now(timezone.utc), forcar=a.forcar)
    except (copia.CopiaRecusada, copia.ExportacaoIncompleta) as e:
        print(f"parei: {e}", file=sys.stderr)
        return 1
    print(f"exportada em {rel['exportado_em']} | {'GRAVOU' if rel['gravou'] else 'ensaio (nada gravado)'} | "
          f"{time.time() - t0:.1f} s | {rel['linhas']} linhas em {len(rel['abas'])} abas")
    diferentes = 0
    for aba, n in sorted(rel["abas"].items()):
        marca = "" if not rel["gravou"] or n["origem"] == n["nexus"] else "  <-- DIFERENTE"
        diferentes += bool(marca)
        print(f"  {n['livro']:22} {aba:24} origem {n['origem']:5}  nexus {'-' if n['nexus'] is None else n['nexus']:>5}{marca}")
    return 1 if diferentes else 0


if __name__ == "__main__":
    sys.exit(main())

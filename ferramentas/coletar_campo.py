"""Uma rodada do coletor da torre Campo · App, à mão: a primeira carga ou uma conferência (nexus/campo/coletor.py).

Lê o Fracttal só com GET, no ritmo do coletor (pausa entre pedidos, para no primeiro 429), calcula a nota de cada
tarefa nova da fila de verificação e grava na API do PG, conferindo depois. Usa o .env do Nexus (credencial do Fracttal
do OS Creator, GRIDCO_SQL_TOKEN, NEXUS_CHAVE_CADASTRO) sem imprimir nada dele.

Uso:  python ferramentas/coletar_campo.py [--max-os N] [--pausa SEGUNDOS]
Sai com 1 se a rodada terminou com erro; o relatório (só contagens) vai para a tela.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nexus import create_app  # noqa: E402
from nexus.campo import coletor  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Uma rodada do coletor da torre Campo · App")
    ap.add_argument("--max-os", type=int, default=None, help="ordens novas nesta rodada (padrão: 40 de dia, 200 à noite)")
    ap.add_argument("--pausa", type=float, default=coletor.PAUSA_S, help="segundos antes de cada pedido ao Fracttal")
    a = ap.parse_args()
    app = create_app()
    with app.app_context():
        r = coletor.rodar(app.config, max_os=a.max_os, pausa_s=a.pausa)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 1 if r.get("erro") else 0


if __name__ == "__main__":
    sys.exit(main())

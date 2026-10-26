"""Anula um ciclo da varredura do almoxarifado aplicado errado (25/10/2026). Ver `nexus/dados/fato_almoxarifado.py`.

    python ferramentas/anular_ciclo_almox.py --ciclo 2026-10-25T03:00:12Z            mostra o que faria
    python ferramentas/anular_ciclo_almox.py --ciclo 2026-10-25T03:00:12Z --gravar   marca e grava

O livro `nexus_almoxarifado` só cresce: nada se apaga. O ciclo ganha `anulado = 1` no `fato_ciclo_varredura`, e a tela
e as contas passam a ignorá-lo; a foto dele fica no livro do mês. Imprime só o resultado, nunca o token.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nexus.config import ler_ambiente  # noqa: E402
from nexus.dados import carga  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--ciclo", required=True, help="o início do ciclo, como está no fato_ciclo_varredura")
    p.add_argument("--gravar", action="store_true", help="grava (sem isto, só mostra)")
    a = p.parse_args()
    print(carga.anular_ciclo_almox(ler_ambiente(), a.ciclo, gravar=a.gravar))


if __name__ == "__main__":
    main()

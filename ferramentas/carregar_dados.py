"""A carga da camada de dados à mão (a mesma que o Nexus roda de hora em hora, aos :40). Imprime só contagens.

    python ferramentas/carregar_dados.py --ensaio     monta com o dado real e NÃO grava (medir antes de gravar)
    python ferramentas/carregar_dados.py              grava se a última carga tiver mais de 50 min
    python ferramentas/carregar_dados.py --forcar     grava agora
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from nexus import create_app  # noqa: E402
from nexus.dados import carga  # noqa: E402


def main():
    app = create_app()
    ensaio = "--ensaio" in sys.argv
    with app.app_context():
        if ensaio:
            _dim, _fat, rel = carga.montar(app.config, requests.Session())
            rel["ensaio"] = "montado com o dado real; nada gravado"
        else:
            rel = carga.rodar(app.config, requests.Session(), forcar="--forcar" in sys.argv)
    print(json.dumps(rel, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

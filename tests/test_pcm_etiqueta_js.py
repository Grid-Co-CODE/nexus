"""A lista de sugestões da etiqueta do Fracttal no Cadastro de motivos (pcm-etiqueta.js), o filtro no node.

Levi, 19/10/2026: o <datalist> do navegador "tá bugadasso, mal formatado (não está no estilo Nexus) e tá todo torto". A
lista agora é do Nexus e filtra sem acento e sem caixa enquanto se digita, as que começam com o texto primeiro."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parents[1] / "nexus" / "static" / "pcm-etiqueta.js"
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="sem node nesta máquina")
LISTA = ["PERFORMANCE", "ENGENHARIA", "Aguardando Equipamento", "Condições climática adversa", "Sem Material Sobressalente",
         "NECESSITA AUXÍLIO ENGENHARIA"]


def filtrar(q):
    script = ("require(process.argv[1]); const E = globalThis.EtiquetaSugestao;"
              "process.stdout.write(JSON.stringify(E.filtrar(JSON.parse(process.argv[2]), process.argv[3])));")
    r = subprocess.run(["node", "-e", script, str(JS), json.dumps(LISTA), q], capture_output=True, text=True,
                       encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_sem_texto_todas_na_ordem_da_pagina():
    assert filtrar("") == LISTA


def test_sem_acento_e_sem_caixa_as_que_comecam_primeiro():
    assert filtrar("engenharia") == ["ENGENHARIA", "NECESSITA AUXÍLIO ENGENHARIA"]
    assert filtrar("condicoes  CLIMATICA") == ["Condições climática adversa"]
    assert filtrar("auxilio") == ["NECESSITA AUXÍLIO ENGENHARIA"]
    assert filtrar("xyz") == []

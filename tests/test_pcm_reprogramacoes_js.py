"""O bloco das reprogramações da semana em curso no Quadro (pcm-reprogramacoes.js): o resumo do que muda, no node.

19/10/2026, o programador do PCM: "ainda tá meio que fantasma pra mim, sem poder editar". Antes de gravar, o bloco diz
quantas linhas foram editadas, tiradas e incluídas; quem confere cada linha é o servidor (`quadro.problemas_das_linhas`)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parents[1] / "nexus" / "static" / "pcm-reprogramacoes.js"
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="sem node nesta máquina")


def resumo(n):
    script = ("require(process.argv[1]); const R = globalThis.ReprogramacoesTela;"
              "process.stdout.write(JSON.stringify(R.resumo(JSON.parse(process.argv[2]))));")
    r = subprocess.run(["node", "-e", script, str(JS), json.dumps(n)], capture_output=True, text=True,
                       encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_nada_mudou_nada_diz():
    assert resumo({"editadas": 0, "tiradas": 0, "novas": 0}) == ""


def test_singular_plural_e_ordem():
    assert resumo({"editadas": 1, "tiradas": 0, "novas": 0}) == "1 editada: grave para valer"
    assert resumo({"editadas": 2, "tiradas": 1, "novas": 3}) == "2 editadas · 1 tirada · 3 novas: grave para valer"
    assert resumo({"editadas": 0, "tiradas": 2, "novas": 1}) == "2 tiradas · 1 nova: grave para valer"

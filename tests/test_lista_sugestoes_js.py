"""A lista de sugestões do Nexus (lista-sugestoes.js), o filtro no node: sem acento, sem caixa, as que começam primeiro.

Levi, 12/11/2026: o <datalist> do campo "usina do cadastro" das Ligações abria solto e fora do estilo."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parents[1] / "nexus" / "static" / "lista-sugestoes.js"
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="sem node nesta máquina")
LISTA = ["1 · Sol do Norte 1", "2 · Parque Eólico São João", "3 · Usina Açaí", "4 · Norte Verde", "5 · Fazenda Sol Nascente"]


def filtrar(q):
    script = ("require(process.argv[1]); const E = globalThis.ListaSugestoes;"
              "process.stdout.write(JSON.stringify(E.filtrar(JSON.parse(process.argv[2]), process.argv[3])));")
    r = subprocess.run(["node", "-e", script, str(JS), json.dumps(LISTA), q], capture_output=True, text=True,
                       encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_sem_texto_todas_na_ordem_da_pagina():
    assert filtrar("") == LISTA


def test_sem_acento_sem_caixa_e_as_que_comecam_primeiro():
    assert filtrar("acai") == ["3 · Usina Açaí"]
    assert filtrar("SAO  joao") == ["2 · Parque Eólico São João"]
    assert filtrar("xyz") == []


def test_as_que_comecam_com_o_texto_vem_antes():
    lista = ["Casa do Sol", "Sol Nascente", "Solar Norte"]
    script = ("require(process.argv[1]); process.stdout.write(JSON.stringify(globalThis.ListaSugestoes.filtrar("
              "JSON.parse(process.argv[2]), 'sol')));")
    r = subprocess.run(["node", "-e", script, str(JS), json.dumps(lista)], capture_output=True, text=True, timeout=60)
    assert json.loads(r.stdout) == ["Sol Nascente", "Solar Norte", "Casa do Sol"]

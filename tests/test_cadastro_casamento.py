"""Casamento por nome para base sem código (nexus/cadastro/casamento.py). Os casos são os reais do BD_Thopen (04/10/2026)."""
import sys
from pathlib import Path

import pytest

from nexus.cadastro import casamento as K

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import publicar_cadastro as P  # noqa: E402

CAD = [
    {"id": 1, "nome": "Ibaté 1", "cidade": "Ibaté", "uf": "SP", "mwp": 3.13},
    {"id": 2, "nome": "Ibaté 2", "cidade": "Ibaté", "uf": "SP", "mwp": 3.13},
    {"id": 3, "nome": "Ipixuna 1 e 2", "cidade": "Ipixuna do Pará", "uf": "PA", "mwp": 3.27},
    {"id": 4, "nome": "Guatambu 1 a 4", "cidade": "Guatambu", "uf": "SC", "mwp": 6.1},
    {"id": 5, "nome": "Ouro Branco", "cidade": "Ouro Branco", "uf": "AL", "mwp": 2.0},
    {"id": 6, "nome": "Nova Londrina 1", "cidade": "Nova Londrina", "uf": "PR", "mwp": 2.7625},
    {"id": 7, "nome": "Nova Londrina 2", "cidade": "Nova Londrina", "uf": "PR", "mwp": 2.7625},
    {"id": 8, "nome": "Aparecida do Taboado 1 e 2", "cidade": "Aparecida do Taboado", "uf": "MS", "mwp": 2.58},
    {"id": 9, "nome": "Senador Elói I", "cidade": "Senador Elói de Souza", "uf": "RN", "mwp": 1.28},
    {"id": 10, "nome": "Topázio (Matão 2)", "cidade": "Matão", "uf": "SP", "mwp": 3.39},
    {"id": 11, "nome": "Saturnino 1", "cidade": "Campos dos Goytacazes", "uf": "RJ", "mwp": 4.664},
    {"id": 12, "nome": "Caxambu 1", "cidade": "Jundiaí", "uf": "SP", "mwp": 2.07},
    {"id": 13, "nome": "Pharmas 2", "cidade": "Bandeirantes", "uf": "PR", "mwp": 1.0},
    {"id": 14, "nome": "Brodowski", "cidade": "Brodowski", "uf": "SP", "mwp": 5.067},
]


def casa(nomes, cidade=None, uf=None, mwp=None):
    r = K.casar({"nomes": nomes, "cidade": cidade, "uf": uf, "mwp": mwp}, CAD)
    return r and r[0]


@pytest.mark.parametrize("nomes, esperado", [
    (["Ibaté 2", "Ibaté II"], [2]),                       # romano
    (["Ipixuna 2", "Ipixuna II"], [3]),                   # "1 e 2" aberto
    (["Guatambu"], [4]),                                  # "1 a 4", sem número, uma candidata
    (["Matão 2"], [10]),                                  # o que está entre parênteses
    (["Pharma II"], [13]),                                # plural e romano
    (["Caxambu"], [12]),                                  # sem número contra "X 1"
])
def test_convencoes_de_nome(nomes, esperado):
    assert casa(nomes) == esperado


def test_ouro_branco_do_parana_nao_e_a_de_alagoas():
    """Nome-base igual, cidade diferente: a localização veta."""
    assert casa(["Ouro Branco I", "Ouro Branco I - Cristiano"], "Bandeirantes", "Paraná", 1.307) is None
    assert casa(["Ouro Branco I"], "Bandeirantes", "Paraná") is None        # sem potência: só a localização veta


def test_nome_igual_com_localizacao_errada_na_base_casa_e_avisa():
    """O BD_Thopen põe Saturnino "no Paraná"; nome igual não é vetado pela localização, só anotado."""
    r = K.casar({"nomes": ["Saturnino 1"], "cidade": "Saturnino", "uf": "Paraná", "mwp": 4.664}, CAD)
    assert r == ([11], "nome (local diverge entre as bases)")


def test_potencia_decide_entre_x1_e_x2_ou_soma():
    assert casa(["Nova Londrina"], "Nova Londrina", "Paraná", 5.525) == [6, 7]          # a soma: as duas
    assert casa(["Nova Londrina"], "Nova Londrina", "Paraná", 2.76) is None             # bate com as duas: ambíguo
    assert casa(["AP. do Taboado"], "Aparecida do Taboado", "Mato Grosso do Sul", 0.413) is None  # outra usina


def test_unica_usina_da_cidade_com_palavra_do_nome():
    assert casa(["Senador"], "Senador Elói de Souza", "Rio Grande do Norte", 1.28) == [9]


def test_sem_numero_no_cadastro_e_a_1_das_outras_bases():
    """Fracttal: "Thopen - Brodowski 1 - SP" é a "Brodowski" do cadastro."""
    assert casa(["Brodowski 1"]) == [14]


def test_usina_do_caminho_de_localizacao_do_fracttal():
    assert P._usina_do_caminho("// Thopen/ Thopen - Brodowski 1 - SP/ Cabine 1/ SKID 2/ QGBT 2/ ") == ("Thopen", "Brodowski 1")
    assert P._usina_do_caminho("// RenoGrid/ RenoGrid - Nobres 1 - MT/ Cabine 1/ ") == ("RenoGrid", "Nobres 1")
    assert P._usina_do_caminho("// TESTE - PA/ ") is None
    assert P._usina_do_caminho(None) is None

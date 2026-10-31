"""Fixtures comuns: um app com configuração de teste, sem ler o .env real da máquina."""
import sys

import pytest

from nexus import create_app

SENHA_TESTE = "senha-de-teste"


@pytest.fixture
def app():
    app = create_app({
        "NEXUS_SECRET_KEY": "chave-de-teste",
        "NEXUS_SENHA_ADMIN": SENHA_TESTE,
    })
    app.config["TESTING"] = True
    app.config["SESSION_COOKIE_SECURE"] = False  # o cliente de teste fala http
    return app


@pytest.fixture
def cliente(app):
    return app.test_client()


@pytest.fixture
def logado(cliente):
    resp = cliente.post("/entrar", data={"senha": SENHA_TESTE})
    assert resp.status_code == 302
    return cliente


@pytest.fixture(autouse=True)
def _catalogo_de_ativos_isolado():
    """O catálogo de ativos do OS Creator (`os_creator/ativos_central.py`) é UM por processo: a pasta onde ele grava a cópia em
    disco, a função do banco e o que ele guarda valem para o processo inteiro. Um teste que cria o clone "fora dos testes"
    (`TESTING` desligado, como o do token do banco) aponta a pasta para a do usuário da máquina (%APPDATA%), e o seguinte, sem
    saber, migraria o arquivo de lá e gravaria nela. Cada teste começa e termina sem catálogo, sem pasta e sem banco. Só age
    se o módulo já foi importado (o clone do OS Creator no `sys.path`): os demais testes não pagam nada."""
    def limpar():
        mod = sys.modules.get("ativos_central")
        if mod is not None:
            mod.reiniciar()
    limpar()
    yield
    limpar()

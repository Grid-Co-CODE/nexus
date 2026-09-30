"""Fixtures comuns: um app com configuração de teste, sem ler o .env real da máquina."""
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

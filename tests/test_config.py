import pytest

from nexus.config import ConfigErro, OPCIONAIS, carregar_config


def test_a_ponte_da_plataforma_e_opcional():
    assert "NEXUS_PLATAFORMA_URL" in OPCIONAIS and "NEXUS_PLATAFORMA_TOKEN" in OPCIONAIS


def test_falta_variavel_diz_o_nome():
    with pytest.raises(ConfigErro) as erro:
        carregar_config({})
    assert "NEXUS_SECRET_KEY" in str(erro.value)


def test_falta_so_a_senha():
    with pytest.raises(ConfigErro) as erro:
        carregar_config({"NEXUS_SECRET_KEY": "valor-secreto-9f3a"})
    assert "NEXUS_SENHA_ADMIN" in str(erro.value)
    # A mensagem vai para log e terminal: nunca pode trazer o valor de um segredo.
    assert "valor-secreto-9f3a" not in str(erro.value)


def test_variavel_vazia_conta_como_faltando():
    with pytest.raises(ConfigErro):
        carregar_config({"NEXUS_SECRET_KEY": "x", "NEXUS_SENHA_ADMIN": "  "})


def test_completa():
    cfg = carregar_config({"NEXUS_SECRET_KEY": "a", "NEXUS_SENHA_ADMIN": "b"})
    assert cfg["NEXUS_SECRET_KEY"] == "a"
    assert cfg["NEXUS_SENHA_ADMIN"] == "b"

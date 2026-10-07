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


def test_a_ponte_chega_ao_app_config():
    from nexus import create_app
    cfg = {"NEXUS_SECRET_KEY": "x", "NEXUS_SENHA_ADMIN": "y",
           "NEXUS_PLATAFORMA_URL": "http://127.0.0.1:5050", "NEXUS_PLATAFORMA_TOKEN": "t"}
    app = create_app(cfg)
    assert app.config["NEXUS_PLATAFORMA_URL"] == "http://127.0.0.1:5050"
    assert app.config["NEXUS_PLATAFORMA_TOKEN"] == "t"
    sem = create_app({"NEXUS_SECRET_KEY": "x", "NEXUS_SENHA_ADMIN": "y"})
    assert "NEXUS_PLATAFORMA_URL" not in sem.config


def test_os_enderecos_do_clima_sao_opcionais_e_chegam_ao_app_config():
    from nexus import create_app
    for nome in ("NEXUS_CLIMA_INMET_URL", "NEXUS_CLIMA_FOCOS_URL", "NEXUS_CLIMA_RISCO_URL", "NEXUS_CLIMA_POWER_URL"):
        assert nome in OPCIONAIS
    app = create_app({"NEXUS_SECRET_KEY": "x", "NEXUS_SENHA_ADMIN": "y",
                      "NEXUS_CLIMA_INMET_URL": "https://espelho.exemplo.test/avisos"})
    assert app.config["NEXUS_CLIMA_INMET_URL"] == "https://espelho.exemplo.test/avisos"
    assert "NEXUS_CLIMA_FOCOS_URL" not in app.config                 # vazio: vale o padrão do fontes.py
    # e o .env vazio não vira configuração
    assert "NEXUS_CLIMA_RISCO_URL" not in carregar_config({"NEXUS_SECRET_KEY": "a", "NEXUS_SENHA_ADMIN": "b",
                                                           "NEXUS_CLIMA_RISCO_URL": "  "})
    espelho = "https://espelho.exemplo.test/p?x={lat},{lon}&a={inicio}&b={fim}"
    assert create_app({"NEXUS_SECRET_KEY": "x", "NEXUS_SENHA_ADMIN": "y", "NEXUS_CLIMA_POWER_URL": espelho}
                      ).config["NEXUS_CLIMA_POWER_URL"] == espelho

"""As rotas de gravação da torre Zeladoria (etapa 4, 03/11/2026): só onde `NEXUS_ZELADORIA_GRAVA=1`, só da própria
página, com a regra do Radar (aprovado grava; usuários e financeiro, só o HEAD). Banco falso; nomes e e-mails fictícios."""
import pytest

from nexus.cadastro.cifra import Cofre
from nexus.zeladoria import gravacao, leitura
from tests.test_zeladoria_torre import CHAVE, _entrar_como, banco, copiado  # noqa: F401 — as fixtures


@pytest.fixture
def gravando(app, copiado, tmp_path):  # noqa: F811
    app.config.update(NEXUS_ZELADORIA_GRAVA="1", NEXUS_DADOS=str(tmp_path))
    gravacao.esquecer()
    yield copiado
    gravacao.esquecer()


def _salvar(c, ops, versao=0, **headers):
    return c.post("/t/zeladoria/api/gravar", json={"ops": ops, "versao": versao}, headers=headers)


FORN = [{"op": "upsert", "view": "rf_fornecedores", "linhas": [{"id": "FORN-1", "valor_mes": 950}]}]


def test_sem_a_chave_a_torre_continua_so_leitura(logado, copiado):  # noqa: F811
    assert _salvar(logado, FORN).status_code == 405
    assert logado.get("/t/zeladoria/api/eu").get_json()["grava"] is False
    assert '"somenteLeitura": true' in logado.get("/t/zeladoria/app").get_data(as_text=True)
    assert "só para leitura" in logado.get("/t/zeladoria/visao-geral").get_data(as_text=True)


def test_o_aprovado_salva_e_o_banco_recebe_depois(cliente, gravando, app):
    html = cliente.get("/t/zeladoria/app")          # sem login: o portão leva ao login
    assert html.status_code == 302
    c = _entrar_como(cliente, "fulano@exemplo.com")
    html = c.get("/t/zeladoria/app").get_data(as_text=True)
    assert '"somenteLeitura": false' in html and '"rf_perfis": "user_id"' in html
    tela = c.get("/t/zeladoria/visao-geral").get_data(as_text=True)
    assert "só para leitura" not in tela and "<iframe" in tela
    eu = c.get("/t/zeladoria/api/eu").get_json()
    assert eu["grava"] is True and eu["versao"] == 0
    r = _salvar(c, FORN)
    assert r.status_code == 200 and r.get_json()["versao"] == 1 and r.get_json()["situacao"]["pendente"] is True
    assert c.get("/t/zeladoria/api/rf/rf_fornecedores").get_json()[0]["valor_mes"] == 950    # na hora
    gravacao.do_app(app.config).persistir()
    est = leitura.ler_banco("http://pg.falso", gravando, Cofre(CHAVE))
    assert est["versao"] == 1 and est["abas"]["fornecedores"][0]["valor_mes"] == 950
    assert c.get("/t/zeladoria/api/situacao").get_json()["pendente"] is False


def test_pendente_nao_grava_e_pessoa_nova_espera_o_head(cliente, logado, gravando):
    p = _entrar_como(cliente, "beltrano@exemplo.com")
    r = _salvar(p, FORN)
    assert r.status_code == 403 and "aprovado" in r.get_json()["erro"]
    novo = _entrar_como(cliente, "novo@exemplo.com")
    novo.get("/t/zeladoria/api/eu")
    novo.get("/t/zeladoria/api/eu")
    head = logado                                  # o administrador vale HEAD
    with head.session_transaction() as s:
        s["admin"] = True
        s["usuario"] = {"email": "", "nome": "Administrador", "perfil": ""}
    perfis = [x for x in head.get("/t/zeladoria/api/rf/rf_perfis").get_json() if x["email"] == "novo@exemplo.com"]
    assert len(perfis) == 1 and perfis[0]["status"] == "pendente"


def test_so_da_propria_pagina(cliente, gravando):
    c = _entrar_como(cliente, "fulano@exemplo.com")
    assert _salvar(c, FORN, **{"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert _salvar(c, FORN, **{"Sec-Fetch-Site": "same-origin"}).status_code == 200


def test_o_financeiro_so_o_head(cliente, logado, gravando):
    corpo = {"args": {"p_cenario_id": "CEN-X", "p_item_ids": ["IT-1"], "p_provisoes": []}, "versao": 0}
    r = logado.post("/t/zeladoria/api/funcao/fin_promover", json=corpo)
    assert r.status_code == 403 and r.get_json()["erro"] == "fin_promover: cenário CEN-X não encontrado"
    c = _entrar_como(cliente, "fulano@exemplo.com")
    r = c.post("/t/zeladoria/api/funcao/fin_promover", json=corpo)
    assert r.status_code == 403 and "só o HEAD" in r.get_json()["erro"]
    assert c.post("/t/zeladoria/api/funcao/fin_inventada", json=corpo).status_code == 403


def test_pedido_torto_e_recusado(cliente, gravando):
    c = _entrar_como(cliente, "fulano@exemplo.com")
    assert c.post("/t/zeladoria/api/gravar", json={"ops": "x"}).status_code == 403
    assert _salvar(c, [{"op": "drop", "view": "rf_fornecedores"}]).status_code == 403
    assert _salvar(c, [{"op": "upsert", "view": "rf_inexistente", "linhas": []}]).status_code in (403, 404)

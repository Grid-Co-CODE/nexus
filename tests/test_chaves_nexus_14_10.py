"""Base → Chaves do Nexus (14/10/2026). Levi, sobre a chave das contestações no servidor: "Se precisa de TI então vou ter
que mandar um arquivo novo de deploy para a TI ué!" — escolheu a tela: o administrador cola a chave uma vez, sem a T.I. e
sem reiniciar.

Provas: só administrador; a chave colada é conferida (formato e, havendo contestação no banco, que abra uma) e gravada
CIFRADA na pasta de dados (o arquivo não tem o valor); vale na hora nas Contestações e vence a do .env; "Apagar" volta à
do .env; NEXUS_SECRET_KEY trocada = a gravada não abre e a tela diz; o formulário de outro site ou vencido não grava; a
tela nunca devolve o valor. Nada vai ao banco nem à rede (o livro das contestações é dublado)."""
import json
import re

import pytest
from test_contratos_contestacoes import _cifrar, _par

from conftest import SENHA_TESTE
from nexus import create_app
from nexus.auth import chaves as K
from nexus.contratos import contestacoes as CT

URL = "/t/base/chaves-nexus"
NOME = "NEXUS_CONTESTACAO_CHAVE_PRIVADA"
PRIV, PUB = _par()
OUTRA_PRIV, _OUTRA_PUB = _par()


def _linha(i=1, pub=PUB):
    dados = json.dumps({"nome": "Cliente Teste", "contato": "contato@exemplo.test", "mensagem": "olhar o dia 06"})
    return {"id": i, "contestacao_id": f"c{i}", "recebida_em": "2026-10-13T12:00:00Z", "usina": "Usina Teste",
            "setor": "performance", "data_id_contestada_ini": 20261006, "itens": "geracao", "avisado_teams": "sim",
            "dados_cifrados": _cifrar(dados, CT.contexto(i), pub)}


@pytest.fixture(autouse=True)
def _limpa():
    K._CACHE.clear()
    yield
    K._CACHE.clear()


@pytest.fixture
def livro(monkeypatch):
    """O livro das contestações dublado: a conferência da chave e a tela leem daqui."""
    linhas = [_linha(1), _linha(2)]
    monkeypatch.setattr(CT.livros, "ler", lambda *a, **k: list(linhas))
    return linhas


@pytest.fixture
def app(tmp_path):
    app = create_app({"NEXUS_SECRET_KEY": "chave-de-teste-" + "x" * 20, "NEXUS_SENHA_ADMIN": SENHA_TESTE,
                      "NEXUS_DADOS": str(tmp_path / "dados")})
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    app.extensions["nexus_dados_sessao"] = object()   # o "banco": o livro.ler é dublado em cada teste, nada vai à rede
    return app


@pytest.fixture
def admin(app):
    c = app.test_client()
    assert c.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    return c


def _codigo(c) -> str:
    return re.search(r'name="codigo" value="([^"]+)"', c.get(URL).get_data(as_text=True)).group(1)


def _gravar(c, valor, codigo=None, **headers):
    return c.post(URL, data={"codigo": codigo if codigo is not None else _codigo(c), "chave": NOME, "acao": "gravar",
                             "valor": valor}, headers=headers)


def test_so_administrador(app):
    assert app.test_client().get(URL).status_code == 302                       # sem login: vai ao Entrar
    c = app.test_client()
    with c.session_transaction() as s:
        s["logado"], s["admin"] = True, False
        s["usuario"] = {"email": "pessoa@exemplo.test", "nome": "Pessoa", "perfil": ""}
    r = c.get(URL)
    assert r.status_code == 403 and "só para administradores" in r.get_data(as_text=True)
    assert c.post(URL, data={"chave": NOME, "acao": "gravar", "valor": PRIV}).status_code == 403


def test_grava_cifrada_vale_na_hora_e_a_tela_nunca_mostra_o_valor(app, admin, livro, tmp_path):
    h = admin.get(URL).get_data(as_text=True)
    assert "Não posta" in h and 'type="password"' in h
    r = _gravar(admin, f"  {PRIV}\n")                                           # espaço e quebra colados junto
    assert r.status_code == 303
    h = admin.get(URL).get_data(as_text=True)
    assert "abre 2 de 2 contestações" in h and "Posta pela tela" in h and "senha de administrador" in h
    assert PRIV not in h and PRIV[:12] not in h
    arquivo = (tmp_path / "dados" / K.ARQUIVO).read_text(encoding="utf-8")
    assert PRIV not in arquivo and NOME in arquivo                             # cifrada no disco
    with app.app_context():
        assert K.valor(NOME) == PRIV
        d = CT.contestacoes()
    assert not d["sem_chave"] and d["por_setor"]["performance"][0]["nome"] == "Cliente Teste"


def test_chave_que_nao_e_chave_ou_de_outro_par_nao_grava(app, admin, livro, tmp_path):
    for ruim, trecho in (("isto não é chave", "não é a chave privada"), ("QUJD" * 3, "não é a chave privada"),
                         (OUTRA_PRIV, "não abre nenhuma das 2 contestações")):
        r = _gravar(admin, ruim)
        assert r.status_code == 400 and trecho in r.get_data(as_text=True), trecho
        assert ruim not in r.get_data(as_text=True)
    assert not (tmp_path / "dados" / K.ARQUIVO).exists()
    r = admin.post(URL, data={"codigo": _codigo(admin), "chave": "NEXUS_SECRET_KEY", "acao": "gravar", "valor": "x"})
    assert r.status_code == 400 and "Chave desconhecida" in r.get_data(as_text=True)   # a tela não edita o .env


def test_sem_contestacao_no_banco_grava_e_diz_que_nao_conferiu(app, admin, monkeypatch):
    monkeypatch.setattr(CT.livros, "ler", lambda *a, **k: [])
    assert _gravar(admin, PRIV).status_code == 303
    assert "ainda não há contestação no banco" in admin.get(URL).get_data(as_text=True)


def test_a_da_tela_vence_a_do_env_e_apagar_volta_a_ela(app, admin, livro):
    app.config[NOME] = OUTRA_PRIV
    assert "Posta no .env do servidor" in admin.get(URL).get_data(as_text=True)
    assert _gravar(admin, PRIV).status_code == 303
    h = admin.get(URL).get_data(as_text=True)
    assert "Posta pela tela" in h and "O .env também tem uma; vale a da tela." in h
    with app.app_context():
        assert K.valor(NOME) == PRIV
    r = admin.post(URL, data={"codigo": _codigo(admin), "chave": NOME, "acao": "apagar"})
    assert r.status_code == 303 and "vale a do .env" in admin.get(URL).get_data(as_text=True)
    with app.app_context():
        assert K.valor(NOME) == OUTRA_PRIV


def test_secret_key_trocada_a_gravada_nao_abre_e_a_tela_diz(app, admin, livro):
    assert _gravar(admin, PRIV).status_code == 303
    app.config["NEXUS_SECRET_KEY"] = "outra-chave-de-teste-" + "y" * 20
    K._CACHE.clear()
    with app.app_context():
        assert K.valor(NOME) is None                                          # não vale, e não quebra a tela
        assert K.estado(app.config)[0]["nao_abre"] is True


def test_formulario_vencido_ou_de_outro_site_nao_grava(app, admin, livro, tmp_path):
    assert _gravar(admin, PRIV, codigo="outro").status_code == 403
    assert _gravar(admin, PRIV, **{"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert not (tmp_path / "dados" / K.ARQUIVO).exists()


def test_o_menu_da_base_tem_a_tela_e_as_contestacoes_apontam_para_ela(app, admin, monkeypatch):
    monkeypatch.setattr(CT.livros, "ler", lambda *a, **k: [_linha(1)])
    assert 'href="/t/base/chaves-nexus"' in admin.get("/").get_data(as_text=True)
    h = admin.get("/t/contratos/contestacoes").get_data(as_text=True)
    assert "Este Nexus não tem a chave das contestações." in h and "/t/base/chaves-nexus" in h

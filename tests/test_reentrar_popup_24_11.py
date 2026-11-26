"""O pop-up de login (24/11/2026, Levi: os supervisores preenchiam a OS, a solicitação ou a OS avulsa no OS Creator e, ao
finalizar, "aparece lá o login, para eles fazerem o login, eles perdem tudo"; "tem que sempre aparecer um pop-up em cima,
ó, faça o login. E aí ele loga, e ele não perde o que ele fez").

O que estes testes seguram: o Entrar do Nexus e o /os/login do OS Creator respondem em JSON ao pop-up, com as mesmas
travas e os mesmos cookies da entrada de sempre; o /os/api/sessao do "Já entrei"; a casca troca o `nexusEntrarDeNovo` (a
janela ia ao Entrar) pelo pop-up; e o OS Creator carrega o embrulho do fetch em toda tela, menos no login. O Fracttal é
falso; nomes e e-mails inventados."""
import sys
from pathlib import Path

import pytest
from test_auth_limite import IP_A, _fracttal_falso
from test_oscreator_solic_engenharia import cli  # noqa: F401  (fixture: o OS Creator com o Fracttal falso)

from nexus.auth import MAX_ERROS_POR_EMAIL, TEXTO_FRACTTAL_FORA, microsoft
from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
from os_web import criar_app  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
JSON = {"Accept": "application/json"}
JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira


def _entrar_json(cli, email, senha="x"):
    return cli.post("/entrar", data={"email": email, "senha": senha}, headers=JSON, environ_base={"REMOTE_ADDR": IP_A})


def test_o_entrar_responde_ao_pop_up_em_json_com_os_mesmos_cookies(app, monkeypatch):
    _fracttal_falso(monkeypatch)
    cli = app.test_client()
    r = _entrar_json(cli, "certa@exemplo.com")
    assert r.status_code == 200 and r.get_json() == {"ok": True}
    cookies = " ".join(r.headers.getlist("Set-Cookie"))
    # a sessão do OS Creator nasce junto (o pop-up do OS Creator volta com ela) e a do Nexus também
    assert "os_sessao=v" in cookies and app.config["SESSION_COOKIE_NAME"] + "=" in cookies
    with cli.session_transaction() as s:
        assert s["logado"] and s["usuario"]["email"] == "certa@exemplo.com"
    # o mesmo Entrar, sem o pedido em JSON, segue indo para a tela
    assert cli.post("/entrar", data={"email": "certa@exemplo.com", "senha": "x"},
                    environ_base={"REMOTE_ADDR": IP_A}).status_code == 302


def test_o_pop_up_recebe_o_erro_e_as_travas_do_entrar_valem_para_ele(app, monkeypatch):
    chamados = _fracttal_falso(monkeypatch)
    cli = app.test_client()
    r = _entrar_json(cli, "errada@exemplo.com")
    assert r.status_code == 401 and r.get_json() == {"ok": False, "erro": "E-mail ou senha incorretos."}
    for _ in range(MAX_ERROS_POR_EMAIL - 1):
        _entrar_json(cli, "errada@exemplo.com")
    r = _entrar_json(cli, "errada@exemplo.com")              # a trava do e-mail: a 6ª nem vai ao Fracttal
    assert r.status_code == 429 and r.get_json()["ok"] is False and len(chamados) == MAX_ERROS_POR_EMAIL
    # a porta da Microsoft: a senha do Fracttal não entra, e o pop-up sabe por quê
    monkeypatch.setattr(microsoft, "ligado", lambda cfg: True)
    r = _entrar_json(cli, "certa@exemplo.com")
    assert r.status_code == 403 and r.get_json() == {"ok": False, "erro": TEXTO_FRACTTAL_FORA}


def test_a_casca_abre_o_pop_up_em_vez_de_levar_a_janela_ao_entrar(app):
    cli = app.test_client()
    with cli.session_transaction() as s:
        s.update(logado=True, admin=False, usuario={"email": "fulana@exemplo.test", "nome": "Fulana de Teste", "perfil": ""})
    h = cli.get("/").get_data(as_text=True)
    assert "/static/reentrar.js" in h
    assert 'window.NEXUS_REENTRAR = {"email": "fulana@exemplo.test", "ms": false, "raiz": ""}' in h
    # a conferência da sessão (a cada 5 min e ao voltar à aba) chama o nexusEntrarDeNovo, que agora abre o pop-up
    assert 'window.nexusEntrarDeNovo = function () { return window.nexusReentrar({tipo: "nexus"}); };' in h
    assert h.index("reentrar.js") < h.index("confereSessao")
    js = (RAIZ / "nexus" / "static" / "reentrar.js").read_text(encoding="utf-8")
    # o pop-up entra pelo Entrar do Nexus (ou pelo /os/login, quando só o OS Creator caiu), em JSON, e confere antes de fechar
    for trecho in ('rota("/entrar")', 'rota("/os/login")', '"Accept": "application/json"', 'rota("/os/_nexus/sessao")', 'rota("/os/api/sessao")',
                   "Nada do que você preencheu se perde", "window.nexusReentrar = function", "Agora não"):
        assert trecho in js, trecho


@pytest.fixture
def os_cli(monkeypatch):
    """O OS Creator sozinho, sem rede: o login do Fracttal falso grava o JWT de mentira."""
    import requests

    def sem_rede(*a, **k):
        raise AssertionError("o teste tentou ir à rede")
    monkeypatch.setattr(requests.Session, "request", sem_rede)

    def login(email, senha):
        if senha != "certa":
            raise api.FracttalError("E-mail ou senha incorretos.")
        api._save_jwt(JWT)
    monkeypatch.setattr(api, "fracttal_login", login)
    monkeypatch.setattr(api, "get_conta_info", lambda: {"nome": "Pessoa Teste", "email": "teste@exemplo.invalid", "perfil": ""})
    return criar_app(segredo="teste", testing=True).test_client()


def test_o_login_do_os_creator_responde_ao_pop_up_em_json(os_cli, monkeypatch):
    r = os_cli.post("/os/login", data={"email": "teste@exemplo.invalid", "senha": "errada"}, headers=JSON)
    assert r.status_code == 401 and r.get_json() == {"ok": False, "erro": "E-mail ou senha incorretos."}
    assert os_cli.get("/os/api/sessao").get_json() == {"ok": False}
    r = os_cli.post("/os/login", data={"email": "teste@exemplo.invalid", "senha": "certa"}, headers=JSON)
    assert r.status_code == 200 and r.get_json() == {"ok": True}
    monkeypatch.setattr(api, "is_logged_in", lambda: True)
    assert os_cli.get("/os/api/sessao").get_json() == {"ok": True}           # a sessão ficou no cookie do /os
    # sem o pedido em JSON, a tela de sempre
    assert os_cli.post("/os/login", data={"email": "x@exemplo.invalid", "senha": "certa"}).status_code == 302


def test_o_ja_entrei_confere_a_sessao(os_cli, monkeypatch):
    assert os_cli.get("/os/api/sessao").get_json() == {"ok": False}           # sem a sessão: não abre o pop-up de novo
    with os_cli.session_transaction() as s:
        s["jwt"] = JWT
    monkeypatch.setattr(api, "is_logged_in", lambda: True)
    assert os_cli.get("/os/api/sessao").get_json() == {"ok": True}
    monkeypatch.setattr(api, "is_logged_in", lambda: (_ for _ in ()).throw(api.FracttalError("fora")))
    assert os_cli.get("/os/api/sessao").get_json() == {"ok": False}


def test_toda_tela_do_os_creator_embrulha_o_fetch_menos_o_login(cli, os_cli):
    h = cli.get("/os/solicitacao/engenharia").get_data(as_text=True)
    assert '<script src="/os/static/relogin.js"></script>' in h
    assert '<meta name="os-conta-email" content="teste@exemplo.invalid">' in h
    # antes das telas: ele embrulha o fetch que elas usam
    assert h.index("relogin.js") < h.index("os_busca.js") or h.index("relogin.js") < h.index("</head>")
    assert "relogin.js" not in os_cli.get("/os/login").get_data(as_text=True)
    js = Path(ponte.RAIZ_CLONE, "os_web", "static", "relogin.js").read_text(encoding="utf-8")
    # a queda: o 401 com "login" (e o "sessao_encerrada" do Nexus), ou o desvio ao Entrar ou ao /os/login
    for trecho in ("j.login", "j.sessao_encerrada", 'RAIZ + "/entrar"', 'OS + "login"', "r.redirected",
                   # a leitura é refeita; o envio não (nunca duas OS), e a tela recebe o recado no lugar do erro
                   'metodo === "GET" || metodo === "HEAD"', "status: 409",
                   "Clique outra vez para enviar: o que você preencheu continua na tela",
                   "window.__nexusFetch = original", "nexusReentrar"):
        assert trecho in js, trecho
    # debaixo do prefixo a ponte reescreve "/os... entre aspas nos .js do clone: a raiz sairia vazia
    assert '"/os' not in js and "'/os" not in js

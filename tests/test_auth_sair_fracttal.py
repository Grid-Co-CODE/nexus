"""A sessão do Nexus que nasceu do login do Fracttal acaba junto com a do Fracttal (Levi, 09/10/2026: "quando deslogar
do Fracttal deslogue do Nexus, tem que pedir para logar de novo"): no "sair" do OS Creator, quando o token vence, quando
o JWT some do cookie do OS Creator, quando o Fracttal recusa o token no meio de um pedido e na conferência da página. A
senha de administrador não depende do Fracttal: só o "sair" a encerra."""
import base64
import json
import time

import pytest
from flask import Flask, jsonify, redirect, session

from conftest import SENHA_TESTE
from nexus.auth import MOTIVOS, fracttal
from nexus.torres.oscreator import ponte


def _jwt(email="pessoa@exemplo.test", exp_s=3600):
    corpo = base64.urlsafe_b64encode(json.dumps({"email": email, "exp": time.time() + exp_s}).encode())
    return "x." + corpo.decode().rstrip("=") + ".y"


def _pelo_fracttal(cliente, exp_s=3600):
    """A sessão do Nexus como o login do Fracttal grava (com o prazo do token)."""
    with cliente.session_transaction() as s:
        s.clear()
        s.update(logado=True, admin=False, usuario={"email": "pessoa@exemplo.test", "nome": "Pessoa", "perfil": ""},
                 fracttal_exp=time.time() + exp_s)


def _cookie_os(app, cliente, jwt):
    clone = ponte.clone(app)
    valor = clone.session_interface.get_signing_serializer(clone).dumps(
        {"jwt": jwt, "conta": {"email": "pessoa@exemplo.test", "nome": "Pessoa"}})
    cliente.set_cookie("os_sessao", valor, path="/os")


def _admin(app):
    """Outro navegador, que entrou com a senha de administrador."""
    c = app.test_client()
    assert c.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    return c


def _apagou_o_cookie_do_os(resp):
    return any(h.startswith("os_sessao=;") for h in resp.headers.getlist("Set-Cookie"))


def _fora_do_nexus(cliente):
    r = cliente.get("/")
    return r.status_code == 302 and "/entrar" in r.headers["Location"]


def test_o_sair_do_os_creator_sai_do_nexus_e_a_tela_de_entrada_diz_por_que(app, cliente):
    _pelo_fracttal(cliente)
    _cookie_os(app, cliente, _jwt())
    r = cliente.get("/os/logout")
    assert r.status_code == 302 and r.headers["Location"] == "/entrar?motivo=saiu"
    assert _apagou_o_cookie_do_os(r) and _fora_do_nexus(cliente)
    html = cliente.get(r.headers["Location"]).get_data(as_text=True)
    assert MOTIVOS["saiu"] in html and 'class="entrar-aviso"' in html
    # quem entrou com a senha de administrador também sai: sair, de qualquer lugar, sai de tudo
    admin = _admin(app)
    assert admin.get("/").status_code == 200
    assert admin.get("/os/logout").headers["Location"] == "/entrar?motivo=saiu" and _fora_do_nexus(admin)


def test_o_token_vencido_encerra_o_nexus_em_qualquer_tela(cliente):
    _pelo_fracttal(cliente, exp_s=-5)
    r = cliente.get("/t/hseq/extintores?regiao=Sudeste")
    assert r.status_code == 302
    assert r.headers["Location"] == "/entrar?next=/t/hseq/extintores?regiao%3DSudeste&motivo=venceu"
    assert _apagou_o_cookie_do_os(r) and _fora_do_nexus(cliente)
    assert MOTIVOS["venceu"] in cliente.get("/entrar?motivo=venceu").get_data(as_text=True)


def test_sem_o_jwt_no_cookie_do_os_creator_a_sessao_do_nexus_acaba(app, cliente):
    _pelo_fracttal(cliente)
    # a moldura do card da OS (página): vai ao login, que sai da moldura (entrar.html)
    r = cliente.get("/os/_nexus/card/15088", headers={"Sec-Fetch-Dest": "iframe"})
    assert r.status_code == 302 and r.headers["Location"] == "/entrar?next=/os/_nexus/card/15088&motivo=caiu"
    assert _fora_do_nexus(cliente)
    # pedido de dados (fetch): 401 em JSON, e quem fez o pedido leva ao login
    _pelo_fracttal(cliente)
    r = cliente.get("/os/_nexus/quem")
    assert r.status_code == 401 and r.get_json() == {
        "ok": False, "login": True, "sessao_encerrada": True, "entrar": "/entrar?motivo=caiu", "erro": MOTIVOS["caiu"]}
    assert _fora_do_nexus(cliente)
    # o motivo também ficou na sessão: a tela de entrada diz mesmo quando quem leva até ela é o portão
    html = cliente.get("/entrar").get_data(as_text=True)
    assert MOTIVOS["caiu"] in html and 'motivo = "caiu"' in html
    assert MOTIVOS["caiu"] not in cliente.get("/entrar").get_data(as_text=True)      # só uma vez


def test_jwt_vencido_no_cookie_do_os_creator_e_a_decisao_da_pt_volta_para_a_lista(app, cliente):
    _pelo_fracttal(cliente)
    _cookie_os(app, cliente, _jwt(exp_s=-60))
    r = cliente.post("/os/_nexus/pt/PT-1/decidir", data={"decisao": "de_acordo", "volta": "/t/hseq/apr-pt?aba=esperando"},
                     headers={"Sec-Fetch-Dest": "document"})
    assert r.status_code == 302
    assert r.headers["Location"] == "/entrar?next=/t/hseq/apr-pt?aba%3Desperando&motivo=venceu"
    assert _fora_do_nexus(cliente)


def test_a_senha_de_administrador_nao_depende_do_fracttal(app, logado):
    assert logado.get("/os/_nexus/quem").get_json() == {"email": "", "nome": ""}
    assert logado.get("/").status_code == 200
    # o login do OS Creator continua o dele (a pessoa entra no Fracttal ali)
    r = logado.get("/os/login")
    assert r.status_code == 200 and 'action="/os/login"' in r.get_data(as_text=True)
    assert logado.get("/os/_nexus/sessao").get_json() == {"ok": True}


def test_o_login_do_os_creator_e_o_do_nexus(app, cliente):
    # já entrou nos dois: o "entre com o seu login do Fracttal" das telas segue direto para onde ia
    _pelo_fracttal(cliente)
    _cookie_os(app, cliente, _jwt())
    r = cliente.get("/os/login?next=/os/_nexus/pt/PT-1/voltar")
    assert r.status_code == 302 and r.headers["Location"] == "/os/_nexus/pt/PT-1/voltar"
    assert cliente.get("/os/login").headers["Location"] == "/os/"
    assert cliente.get("/").status_code == 200


@pytest.fixture
def clone_falso(app, monkeypatch):
    """Um clone do OS Creator de mentira com a mesma sessão (os_sessao em /os): cada rota faz o que o de verdade faz
    quando o Fracttal derruba, recusa ou renova o token."""
    falso = Flask("clone_falso")
    falso.config.update(SECRET_KEY="chave-do-clone", SESSION_COOKIE_NAME="os_sessao", SESSION_COOKIE_PATH="/os")
    novo = {"jwt": _jwt(exp_s=7200)}

    @falso.route("/os/historico")
    def historico():                 # o _erro_fracttal: tira o JWT e manda ao login dele
        session.pop("jwt", None)
        session["aviso"] = "A sessão do Fracttal caiu."
        return redirect("/os/login?next=%2Fos%2Fhistorico")

    @falso.route("/os/api/tickets")
    def tickets():                   # pedido de dados com a sessão morta
        return jsonify({"erro": "Entre no Fracttal para continuar.", "login": True}), 401

    @falso.route("/os/vencido")
    def vencido():                   # o aviso do app de mesa quando o JWT venceu e não renovou
        return "<html><head></head><body>O JWT expirou: cole um novo em fracttal_login.txt</body></html>"

    @falso.route("/os/renova")
    def renova():                    # o _fechar_sessao com o token renovado
        session["jwt"] = novo["jwt"]
        return "<html><head></head><body>ok</body></html>"

    monkeypatch.setattr(ponte, "clone", lambda _app: falso)
    return falso, novo


def test_a_resposta_do_clone_que_derruba_o_token_derruba_o_nexus(app, cliente, clone_falso):
    falso, novo = clone_falso

    def entra():
        _pelo_fracttal(cliente)
        cliente.set_cookie("os_sessao", falso.session_interface.get_signing_serializer(falso).dumps(
            {"jwt": _jwt(), "conta": {"email": "pessoa@exemplo.test"}}), path="/os")

    entra()
    r = cliente.get("/os/historico", headers={"Sec-Fetch-Dest": "iframe"})
    assert r.status_code == 302 and r.headers["Location"] == "/entrar?next=/os/historico&motivo=caiu"
    assert _apagou_o_cookie_do_os(r) and _fora_do_nexus(cliente)
    entra()
    r = cliente.get("/os/api/tickets")
    assert r.status_code == 401 and r.get_json()["sessao_encerrada"] is True and _fora_do_nexus(cliente)
    entra()
    r = cliente.get("/os/vencido", headers={"Sec-Fetch-Dest": "iframe"})
    assert r.headers["Location"] == "/entrar?next=/os/vencido&motivo=venceu" and _fora_do_nexus(cliente)
    # o token renovado pelo clone estica o prazo da sessão do Nexus junto
    entra()
    r = cliente.get("/os/renova", headers={"Sec-Fetch-Dest": "iframe"})
    assert r.status_code == 200
    with cliente.session_transaction() as s:
        assert s["fracttal_exp"] == pytest.approx(fracttal.exp_do_jwt(novo["jwt"]))


def test_com_a_senha_de_administrador_o_clone_que_pede_login_nao_derruba_o_nexus(app, logado, clone_falso):
    falso, _novo = clone_falso
    logado.set_cookie("os_sessao", falso.session_interface.get_signing_serializer(falso).dumps({"jwt": _jwt()}),
                      path="/os")
    r = logado.get("/os/historico")
    assert r.status_code == 302 and r.headers["Location"].startswith("/os/login")
    assert logado.get("/").status_code == 200


def test_a_conferencia_da_pagina_encerra_so_quando_o_fracttal_diz_que_morreu(app, cliente, monkeypatch):
    respostas = []
    monkeypatch.setattr(ponte, "vivo_no_fracttal", lambda _app, jwt, email="": respostas.pop(0))
    _pelo_fracttal(cliente)
    _cookie_os(app, cliente, _jwt())
    respostas[:] = [True, None]
    assert cliente.get("/os/_nexus/sessao").get_json() == {"ok": True}
    assert cliente.get("/os/_nexus/sessao").get_json() == {"ok": True}      # não sei (429, rede): segue
    respostas[:] = [False]
    r = cliente.get("/os/_nexus/sessao")
    assert r.status_code == 401 and r.get_json()["entrar"] == "/entrar?motivo=caiu" and _fora_do_nexus(cliente)


def test_o_fracttal_e_perguntado_no_maximo_a_cada_5_minutos_e_a_cota_nao_derruba_ninguem(app, monkeypatch):
    ponte.clone(app)
    import api as os_api
    chamadas, saidas = [], []

    def rpc(metodo, params, timeout=45):
        chamadas.append(metodo)
        r = saidas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr(os_api, "_rpc_call", rpc)
    app.extensions.pop("os_fracttal_vivo", None)
    viva, cota, morta = _jwt("a@x.test"), _jwt("b@x.test"), _jwt("c@x.test")
    saidas[:] = [{"data": []}]
    assert ponte.vivo_no_fracttal(app, viva) is True
    assert ponte.vivo_no_fracttal(app, viva) is True and len(chamadas) == 1          # guardada: sem pedido novo
    saidas[:] = [os_api.FracttalError("RPC tasks.work_order_labels_list HTTP 429 — limite")]
    assert ponte.vivo_no_fracttal(app, cota) is None
    assert ponte.vivo_no_fracttal(app, cota) is None and len(chamadas) == 2          # 1 minuto até perguntar de novo
    saidas[:] = [os_api.SessionExpired("Sua sessão do Fracttal expirou ou foi encerrada.")]
    assert ponte.vivo_no_fracttal(app, morta) is False
    # a 2 minutos de vencer o prazo resolve (perguntar faria o clone tentar renovar o token); sem token, morta
    assert ponte.vivo_no_fracttal(app, _jwt(exp_s=60)) is None and ponte.vivo_no_fracttal(app, "") is False
    assert len(chamadas) == 3 and chamadas[0] == os_api.RPC_LABELS_LIST


def test_o_login_pelo_fracttal_guarda_o_prazo_do_token_e_so_ele_ganha_a_conferencia(app, cliente, monkeypatch):
    exp = time.time() + 3600
    monkeypatch.setattr(fracttal, "entrar", lambda app, e, s: {"email": e, "nome": "Pessoa", "perfil": "", "exp": exp,
                                                                  "cookie": ("os_sessao", "valor", 3600)})
    cliente.post("/entrar", data={"email": "pessoa@exemplo.test", "senha": "x"})
    with cliente.session_transaction() as s:
        assert s["fracttal_exp"] == exp
    assert "/os/_nexus/sessao" in cliente.get("/").get_data(as_text=True)
    assert "/os/_nexus/sessao" not in _admin(app).get("/").get_data(as_text=True)      # senha de administrador
    assert fracttal.exp_do_jwt(_jwt(exp_s=100)) == pytest.approx(time.time() + 100, abs=2)
    assert fracttal.exp_do_jwt("opaco") == 0.0


def test_a_tela_de_entrada_sai_da_moldura_e_so_aceita_motivo_conhecido(cliente):
    html = cliente.get("/entrar?motivo=caiu").get_data(as_text=True)
    # o login pelo nexusRota (porta única, 10/10/2026): debaixo do /nexus, "/entrar" cru caía na plataforma
    assert 'window.top.location.replace(nexusRota("/entrar") + "?next="' in html and 'motivo = "caiu"' in html
    estranho = cliente.get("/entrar?motivo=%3Cscript%3E").get_data(as_text=True)
    assert 'class="entrar-aviso"' not in estranho and "&lt;script" not in estranho and 'motivo = ""' in estranho

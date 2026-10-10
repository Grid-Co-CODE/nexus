"""O "sair do Fracttal sai do Nexus" debaixo do /nexus (porta única, 10/10/2026).

Por quê. A `main` ganhou em 09/10/2026 a regra do Levi "quando deslogar do Fracttal deslogue do Nexus" (portão, ponte do
OS Creator, tela de entrada e conferência da página a cada 5 minutos), escrita e provada só na raiz. A porta única põe o
Nexus em app.gridco.com.br/nexus (Levi: "a partir de segunda quero o Nexus como link principal"), e ali um endereço
escrito a partir da raiz cai na plataforma de Performance. Ao juntar as duas, cada endereço dessa regra passou pelo
prefixo; aqui se prova, com o Caddy cortando o /nexus como no servidor de hoje:
- o "sair" do OS Creator leva ao /nexus/entrar e apaga o `os_sessao` no /nexus/os (onde ele mora);
- o token vencido devolve ao login com o `next` como o navegador o vê;
- a decisão da PT volta à lista do HSEQ debaixo do /nexus (o `volta` do formulário vem sem o prefixo);
- o login do clone que já sai com o prefixo (`/nexus/os/login`) também derruba a sessão;
- a página do Entrar, a do card e a conferência da sessão pedem os endereços pelo `nexusRota`.
"""
import base64
import json
import time

import pytest
from werkzeug.test import Client

from conftest import SENHA_TESTE
from nexus import create_app
from nexus.auth import fracttal
from nexus.torres.oscreator import ponte

PREFIXO = "/nexus"


def _jwt(exp_s=3600):
    corpo = base64.urlsafe_b64encode(json.dumps({"email": "pessoa@exemplo.test", "exp": time.time() + exp_s}).encode())
    return "x." + corpo.decode().rstrip("=") + ".y"


@pytest.fixture
def app():
    app = create_app({"NEXUS_SECRET_KEY": "chave-de-teste", "NEXUS_SENHA_ADMIN": SENHA_TESTE, "NEXUS_PREFIXO": PREFIXO})
    app.config["TESTING"] = True
    app.config["SESSION_COOKIE_SECURE"] = False
    return app


def _caddy_corta(app):
    """O Caddy do servidor de hoje: /nexus/* vai ao Nexus SEM o /nexus; o resto é da plataforma."""
    def wsgi(environ, start_response):
        caminho = environ.get("PATH_INFO") or "/"
        if caminho == PREFIXO or caminho.startswith(PREFIXO + "/"):
            environ["PATH_INFO"] = caminho[len(PREFIXO):] or "/"
            return app(environ, start_response)
        start_response("599 PLATAFORMA", [("Content-Type", "text/plain")])
        return [b"isto seria a plataforma"]
    return wsgi


def _valor_os(app, jwt):
    clone = ponte.clone(app)
    return clone.session_interface.get_signing_serializer(clone).dumps(
        {"jwt": jwt, "conta": {"email": "pessoa@exemplo.test", "nome": "Pessoa"}})


def _pelo_fracttal(app, monkeypatch, exp_sessao=3600, exp_jwt=3600):
    """Entra pelo login do Fracttal (de mentira), como no servidor: o `os_sessao` nasce junto, no /nexus/os."""
    valor = _valor_os(app, _jwt(exp_jwt))
    monkeypatch.setattr(fracttal, "entrar", lambda _a, e, s: {
        "email": e, "nome": "Pessoa Teste", "perfil": "", "cookie": ("os_sessao", valor, 3600),
        "exp": time.time() + exp_sessao})
    cli = Client(_caddy_corta(app))
    r = cli.post(PREFIXO + "/entrar", data={"email": "pessoa@exemplo.test", "senha": "x"})
    assert r.status_code == 302 and r.headers["Location"] == PREFIXO + "/"
    (os_cookie,) = [c for c in r.headers.getlist("Set-Cookie") if c.startswith("os_sessao=")]
    assert "Path=/nexus/os;" in os_cookie
    return cli


def _os_apagado_no_prefixo(resp):
    apagados = [c for c in resp.headers.getlist("Set-Cookie") if c.startswith("os_sessao=;")]
    return bool(apagados) and all("Path=/nexus/os" in c for c in apagados)


def _fora(cli):
    r = cli.get(PREFIXO + "/")
    return r.status_code == 302 and r.headers["Location"].startswith(PREFIXO + "/entrar")


def test_o_sair_do_os_creator_leva_ao_entrar_do_nexus_e_apaga_o_cookie_onde_ele_mora(app, monkeypatch):
    cli = _pelo_fracttal(app, monkeypatch)
    assert cli.get(PREFIXO + "/").status_code == 200
    r = cli.get(PREFIXO + "/os/logout")
    assert r.status_code == 302 and r.headers["Location"] == "/nexus/entrar?motivo=saiu"
    assert _os_apagado_no_prefixo(r) and _fora(cli)


def test_token_vencido_volta_ao_login_com_o_next_como_o_navegador_ve(app, monkeypatch):
    cli = _pelo_fracttal(app, monkeypatch, exp_sessao=-5)
    r = cli.get(PREFIXO + "/t/hseq/extintores?regiao=Sudeste")
    assert r.status_code == 302
    assert r.headers["Location"] == "/nexus/entrar?next=/nexus/t/hseq/extintores?regiao%3DSudeste&motivo=venceu"
    assert _os_apagado_no_prefixo(r) and _fora(cli)
    # e o Entrar devolve para lá, debaixo do /nexus (nunca à plataforma)
    r = cli.post("/nexus/entrar?next=/nexus/t/hseq/extintores?regiao%3DSudeste", data={"senha": SENHA_TESTE})
    assert r.headers["Location"] == "/nexus/t/hseq/extintores?regiao=Sudeste"


def test_jwt_vencido_na_decisao_da_pt_volta_para_a_lista_debaixo_do_prefixo(app, monkeypatch):
    cli = _pelo_fracttal(app, monkeypatch, exp_jwt=-60)
    r = cli.post(PREFIXO + "/os/_nexus/pt/PT-1/decidir", data={"decisao": "de_acordo", "volta": "/t/hseq/apr-pt?aba=esperando"},
                 headers={"Sec-Fetch-Dest": "document"})
    assert r.status_code == 302
    assert r.headers["Location"] == "/nexus/entrar?next=/nexus/t/hseq/apr-pt?aba%3Desperando&motivo=venceu"
    assert _fora(cli)


@pytest.mark.parametrize("volta, esperado", [
    ("/t/hseq/apr-pt?aba=esperando", "/nexus/t/hseq/apr-pt?aba=esperando"),          # o request.full_path da tela
    ("/nexus/t/hseq/apr-pt?aba=esperando", "/nexus/t/hseq/apr-pt?aba=esperando"),    # a camada da T.I. pôs o prefixo
    ("https://mal.exemplo.test/t/hseq/", "/nexus/t/campo/pt/PT-1?gravada=1"),        # fora do Nexus: a tela da PT
])
def test_a_decisao_gravada_volta_a_tela_de_onde_saiu_debaixo_do_prefixo(app, monkeypatch, volta, esperado):
    from nexus.campo import decisao_pt
    from nexus.torres.campo import assinatura
    cli = _pelo_fracttal(app, monkeypatch)
    monkeypatch.setattr(assinatura, "quem_assina", lambda: {"email": "pessoa@exemplo.test", "nome": "Pessoa"})
    monkeypatch.setattr(decisao_pt, "decidir", lambda *a, **k: None)
    r = cli.post(PREFIXO + "/os/_nexus/pt/PT-1/decidir", data={"decisao": "de_acordo", "volta": volta})
    assert r.status_code == 302 and r.headers["Location"] == esperado


def test_o_login_do_clone_com_o_prefixo_tambem_derruba_a_sessao(app):
    """O url_for do clone sai com o SCRIPT_NAME do Nexus: debaixo do /nexus o login dele é /nexus/os/login."""
    alvo = ponte.clone(app)
    with app.test_request_context("/os/historico", base_url="http://localhost/nexus/"):
        para_o_login = app.response_class(status=302, headers={"Location": "/nexus/os/login?next=/os/historico"})
        assert ponte._fim_na_resposta(alvo, para_o_login) == "caiu"
        cru = app.response_class(status=302, headers={"Location": "/os/login?next=/os/historico"})
        assert ponte._fim_na_resposta(alvo, cru) == "caiu"
        outra_tela = app.response_class(status=302, headers={"Location": "/nexus/os/historico"})
        assert ponte._fim_na_resposta(alvo, outra_tela) is None


def test_o_endereco_antigo_das_pt_leva_a_lista_do_hseq_debaixo_do_prefixo(app):
    cli = Client(_caddy_corta(app))
    cli.post(PREFIXO + "/entrar", data={"senha": SENHA_TESTE})
    r = cli.get(PREFIXO + "/t/campo/pt?aba=esperando")
    assert r.status_code == 302 and r.headers["Location"] == "/nexus/t/hseq/apr-pt?aba=esperando"


def test_as_paginas_pedem_login_e_sessao_pelo_nexus_rota(app, monkeypatch):
    cli = _pelo_fracttal(app, monkeypatch)
    inicio = cli.get(PREFIXO + "/").get_data(as_text=True)
    assert 'nexusRota("/os/_nexus/sessao")' in inicio and 'fetch("/os/_nexus/sessao"' not in inicio
    assert 'rota("/entrar")' in inicio and 'url || "/entrar"' not in inicio
    entrar = Client(_caddy_corta(app)).get(PREFIXO + "/entrar?motivo=caiu").get_data(as_text=True)
    assert 'window.NEXUS_RAIZ = "/nexus"' in entrar
    assert 'window.top.location.replace(nexusRota("/entrar") + "?next="' in entrar

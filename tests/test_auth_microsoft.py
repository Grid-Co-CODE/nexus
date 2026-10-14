"""Entrar com a conta Microsoft da Grid Co. (Levi, 13/10/2026: "Conseguimos fazer o login do Nexus ser via microsoft só
aceitando quem é da grid?"; `nexus/auth/microsoft.py`).

Desligada sem as quatro variáveis NEXUS_MS_* (a porta segue a do Fracttal). Ligada, a porta é a Microsoft e o Fracttal
sai da porta, também para o POST feito sem a tela. A ida leva ao diretório da Grid com PKCE e escolha de conta; a volta
é o próprio /entrar e só entra quem é do diretório da Grid, não é convidado e tem e-mail de um domínio da Grid. A
sessão da Microsoft não cai com a do Fracttal (ele fica no OS Creator), dura 12 h a partir do login e passa pelo mesmo
portão de setor e de administrador. A Microsoft aqui é de mentira (o endpoint de token troca de lugar com um dublê) e
as pessoas também."""
import base64
import hashlib
import json
import logging
import time
from urllib.parse import parse_qs, quote, urlsplit

import pytest
import requests

from conftest import SENHA_TESTE
from nexus.auth import MOTIVOS, SESSAO_MS_S, TEXTO_FRACTTAL_FORA, TETO_POR_IP, fracttal, microsoft, setor_telas

DIRETORIO = "11111111-2222-3333-4444-555555555555"
OUTRO_DIRETORIO = "99999999-8888-7777-6666-555555555555"
CLIENTE = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
VOLTA = "https://nexus.exemplo.test/entrar"
EMAIL = "pessoa.teste@gridco.com.br"
DE_FORA = microsoft.TEXTO_DE_FORA.format(dominios="@gridco.com.br")
CONVIDADO = microsoft.TEXTO_CONVIDADO.format(dominios="@gridco.com.br")


@pytest.fixture
def ms(app):
    app.config.update(NEXUS_MS_CLIENT_ID=CLIENTE, NEXUS_MS_TENANT_ID=DIRETORIO,
                      NEXUS_MS_CLIENT_SECRET="segredo-de-teste", NEXUS_MS_VOLTA=VOLTA)
    return app


class _Resposta:
    def __init__(self, status, corpo):
        self.status_code, self._corpo = status, corpo

    def json(self):
        return self._corpo


class Microsoft:
    """O endpoint de token de mentira: guarda o que o Nexus mandou e devolve o que o teste pôs em `resposta`."""

    def __init__(self, monkeypatch):
        self.pedidos, self.resposta = [], None
        monkeypatch.setattr(microsoft, "_pedir_token", self._post)

    def _post(self, url, dados):
        self.pedidos.append((url, dict(dados)))
        if isinstance(self.resposta, Exception):
            raise self.resposta
        return _Resposta(*self.resposta)


@pytest.fixture
def fake(monkeypatch):
    return Microsoft(monkeypatch)


def _b64(dado: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(dado).encode()).decode().rstrip("=")


def _claims(nonce_da_ida, **mudar):
    agora = time.time()
    c = {"iss": f"https://login.microsoftonline.com/{DIRETORIO}/v2.0", "aud": CLIENTE, "tid": DIRETORIO,
         "nonce": nonce_da_ida, "iat": agora - 5, "nbf": agora - 5, "exp": agora + 3600, "name": "Pessoa Teste",
         "preferred_username": EMAIL, "email": EMAIL, "oid": "0000-oid", "sub": "sub-de-teste", "ver": "2.0"}
    c.update(mudar)
    return {k: v for k, v in c.items() if v is not None}


def _ida(cliente, next_=None):
    r = cliente.get("/entrar?ms=1" + (f"&next={quote(next_, safe='')}" if next_ else ""))
    assert r.status_code == 302, r.status_code
    q = {k: v[0] for k, v in parse_qs(urlsplit(r.headers["Location"]).query).items()}
    with cliente.session_transaction() as s:
        pedido = dict(s["ms_pedidos"][q["state"]])
    return r, q, pedido


def _volta(cliente, fake, pedido, **mudar):
    fake.resposta = (200, {"id_token": f"{_b64({'alg': 'RS256'})}.{_b64(_claims(pedido['nonce'], **mudar))}.assin",
                           "token_type": "Bearer"})
    return cliente.get(f"/entrar?code=codigo-de-teste&state={pedido['state']}&session_state=sessao-ms")


def _entrar_pela_microsoft(cliente, fake, next_=None):
    _r, _q, pedido = _ida(cliente, next_)
    r = _volta(cliente, fake, pedido)
    assert r.status_code == 302, r.get_data(as_text=True)[:500]
    return r


def _fora_do_nexus(cliente):
    r = cliente.get("/")
    return r.status_code == 302 and "/entrar" in r.headers["Location"]


# ── desligada: a porta de sempre ────────────────────────────────────────────────────────────────────────────────────
def test_sem_as_quatro_variaveis_a_porta_segue_a_do_fracttal(app, cliente):
    html = cliente.get("/entrar").get_data(as_text=True)
    assert "E-mail do Fracttal" in html and "Entrar com a Microsoft" not in html
    r = cliente.get("/entrar?ms=1&next=/t/cos/mesa")
    assert r.status_code == 302 and r.headers["Location"] == "/entrar?next=/t/cos/mesa"
    # uma volta sem a porta ligada é só o Entrar
    assert cliente.get("/entrar?code=x&state=y").status_code == 200 and _fora_do_nexus(cliente)
    # três das quatro, ou o diretório escrito como domínio (nunca casaria com o `tid`): continua desligada
    app.config.update(NEXUS_MS_CLIENT_ID=CLIENTE, NEXUS_MS_TENANT_ID=DIRETORIO, NEXUS_MS_CLIENT_SECRET="s")
    assert not microsoft.ligado(app.config)
    app.config.update(NEXUS_MS_VOLTA=VOLTA, NEXUS_MS_TENANT_ID="gridco.com.br")
    assert not microsoft.ligado(app.config)
    assert "E-mail do Fracttal" in cliente.get("/entrar").get_data(as_text=True)
    app.config.update(NEXUS_MS_TENANT_ID=DIRETORIO.upper())
    assert microsoft.ligado(app.config)


# ── ligada: a porta é a Microsoft ───────────────────────────────────────────────────────────────────────────────────
def test_ligada_a_porta_e_a_microsoft_e_o_fracttal_sai_da_porta(ms, cliente, monkeypatch):
    def nao_vai_ao_fracttal(*_a, **_k):
        raise AssertionError("com a Microsoft ligada, nada vai ao Fracttal pela porta")
    monkeypatch.setattr(fracttal, "entrar", nao_vai_ao_fracttal)
    html = cliente.get("/entrar?next=/t/cos/mesa").get_data(as_text=True)
    assert "Entrar com a Microsoft" in html and "@gridco.com.br" in html and "E-mail do Fracttal" not in html
    assert 'href="/entrar?ms=1&next=/t/cos/mesa"' in html
    assert "Entrar com a senha de administrador" in html
    # o POST do Fracttal feito sem a tela também é recusado, e não conta como senha errada
    r = cliente.post("/entrar", data={"email": "alguem@fracttal.exemplo.test", "senha": "x"})
    assert r.status_code == 403 and TEXTO_FRACTTAL_FORA in r.get_data(as_text=True) and _fora_do_nexus(cliente)
    assert not any(k[0] in ("email", "email_ip") for k in cliente.application.extensions["nexus_erros_login"])
    # a senha de administrador segue de reserva, e a volta dela leva à Microsoft
    assert "Entrar com a conta Microsoft da Grid Co." in cliente.get("/entrar?admin=1").get_data(as_text=True)
    assert cliente.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    assert cliente.get("/").status_code == 200


def test_a_ida_vai_ao_diretorio_da_grid_com_pkce_e_escolha_de_conta(ms, cliente):
    r, q, pedido = _ida(cliente, "/t/cos/mesa")
    assert r.headers["Location"].startswith(f"https://login.microsoftonline.com/{DIRETORIO}/oauth2/v2.0/authorize?")
    assert r.headers["Cache-Control"] == "no-store"
    assert q["client_id"] == CLIENTE and q["redirect_uri"] == VOLTA and q["response_type"] == "code"
    # a volta por GET (com form_post seria um POST de outro site, e o cookie Lax da sessão não iria junto)
    assert q["response_mode"] == "query" and q["scope"] == "openid profile email"
    assert q["state"] == pedido["state"] and q["nonce"] == pedido["nonce"] and len(pedido["verificador"]) >= 43
    desafio = base64.urlsafe_b64encode(hashlib.sha256(pedido["verificador"].encode()).digest()).decode().rstrip("=")
    assert q["code_challenge"] == desafio and q["code_challenge_method"] == "S256"
    # toda entrada pede a senha da Microsoft: no PC da sala do NOC, a conta de quem saiu não abre o Nexus com um clique
    assert q["prompt"] == "login" and q["domain_hint"] == "gridco.com.br"
    assert pedido["next"] == "/t/cos/mesa" and "segredo-de-teste" not in r.headers["Location"]
    # o `next` de fora vira o Início
    assert _ida(cliente, "https://mal.exemplo.test/x")[2]["next"] == "/"


def test_a_volta_certa_abre_o_nexus_como_a_pessoa(ms, cliente, fake):
    # o OS Creator de quem usou este navegador antes (o PC da sala do NOC) não passa para quem entra
    cliente.set_cookie("os_sessao", "sessao-do-fracttal-de-outra-pessoa", path="/os")
    _r, _q, pedido = _ida(cliente, "/t/cos/mesa")
    r = _volta(cliente, fake, pedido)
    assert r.status_code == 302 and r.headers["Location"].endswith("/t/cos/mesa")
    assert any(h.startswith("os_sessao=;") and "Path=/os" in h for h in r.headers.getlist("Set-Cookie"))
    # o código foi trocado servidor a servidor, com o verificador desta ida e a chave do Nexus
    assert len(fake.pedidos) == 1
    url, dados = fake.pedidos[0]
    assert url == f"https://login.microsoftonline.com/{DIRETORIO}/oauth2/v2.0/token"
    assert dados == {"client_id": CLIENTE, "client_secret": "segredo-de-teste", "grant_type": "authorization_code",
                     "code": "codigo-de-teste", "redirect_uri": VOLTA, "code_verifier": pedido["verificador"],
                     "scope": "openid profile email"}
    with cliente.session_transaction() as s:
        assert s["logado"] and s["via"] == "microsoft" and s["admin"] is False
        assert s["usuario"] == {"email": EMAIL, "nome": "Pessoa Teste", "perfil": ""}
        assert s["ms_ate"] == pytest.approx(time.time() + SESSAO_MS_S, abs=30)
        assert "ms_pedidos" not in s and "fracttal_exp" not in s
    html = cliente.get("/").get_data(as_text=True)
    assert "Pessoa Teste" in html
    # cada ida vale uma volta só: a mesma volta de novo não troca código nenhum
    r = cliente.get(f"/entrar?code=codigo-de-teste&state={pedido['state']}")
    assert r.status_code == 403 and microsoft.TEXTO_SEM_PEDIDO in r.get_data(as_text=True) and len(fake.pedidos) == 1


def test_administrador_pela_lista_e_a_lista_vale_a_cada_pedido(ms, cliente, fake):
    _entrar_pela_microsoft(cliente, fake)
    with cliente.session_transaction() as s:
        assert s["admin"] is False
    ms.config["NEXUS_ADMINS"] = "Pessoa.Teste@GridCo.com.br"
    assert cliente.get("/").status_code == 200
    with cliente.session_transaction() as s:
        assert s["admin"] is True


@pytest.mark.parametrize("caso, mudar, texto", [
    ("outro diretório", {"tid": OUTRO_DIRETORIO, "iss": f"https://login.microsoftonline.com/{OUTRO_DIRETORIO}/v2.0"},
     DE_FORA),
    ("emissor de outro diretório", {"iss": f"https://login.microsoftonline.com/{OUTRO_DIRETORIO}/v2.0"}, DE_FORA),
    ("token de outro aplicativo", {"aud": "outro-aplicativo"}, microsoft.TEXTO_NAO_CONFERE),
    ("nonce de outra ida", {"nonce": "nonce-de-outra-ida"}, microsoft.TEXTO_NAO_CONFERE),
    ("id_token vencido", {"exp": time.time() - 3600}, microsoft.TEXTO_NAO_CONFERE),
    ("convidado de outro diretório", {"idp": f"https://sts.windows.net/{OUTRO_DIRETORIO}/"}, CONVIDADO),
    ("convidado com conta pessoal", {"idp": "live.com"}, CONVIDADO),
    ("convidado criado no diretório (acct)", {"acct": 1}, CONVIDADO),
    ("convidado pelo #EXT#", {"preferred_username": "pessoa_exemplo.test#EXT#@gridcoexemplo.onmicrosoft.com",
                              "email": "pessoa@exemplo.test"}, CONVIDADO),
    ("e-mail de fora", {"email": "pessoa@exemplo.test", "preferred_username": "pessoa@exemplo.test"}, DE_FORA),
    ("domínio parecido no fim", {"email": "pessoa@gridco.com.br.exemplo.test",
                                 "preferred_username": "pessoa@gridco.com.br.exemplo.test"}, DE_FORA),
    ("domínio parecido no começo", {"email": "pessoa@xgridco.com.br", "preferred_username": "pessoa@xgridco.com.br"},
     DE_FORA),
    ("sem e-mail", {"email": None, "preferred_username": None}, DE_FORA),
])
def test_quem_nao_e_da_grid_nao_entra(ms, fake, caso, mudar, texto, caplog):
    cliente = ms.test_client()
    _r, _q, pedido = _ida(cliente)
    with caplog.at_level(logging.WARNING, logger="nexus.auth"):
        r = _volta(cliente, fake, pedido, **mudar)
    assert r.status_code == 403, caso
    assert texto in r.get_data(as_text=True), caso
    assert _fora_do_nexus(cliente), caso
    # no journal vai o motivo, nunca o e-mail
    assert caplog.records and not any("pessoa" in rec.getMessage() for rec in caplog.records), caso


def test_membro_com_acct_zero_e_id_do_aplicativo_em_maiuscula_no_env_entram(ms, cliente, fake):
    ms.config["NEXUS_MS_CLIENT_ID"] = CLIENTE.upper()        # o GUID colado em maiúscula não recusa todo mundo
    _r, _q, pedido = _ida(cliente)
    assert _volta(cliente, fake, pedido, acct=0).status_code == 302 and cliente.get("/").status_code == 200


def test_volta_que_este_navegador_nao_pediu_nem_vai_a_microsoft(ms, cliente, fake):
    # o código de outra pessoa colado num link (login CSRF): sem a ida neste navegador, nada é trocado
    r = cliente.get("/entrar?code=codigo-de-outra-pessoa&state=state-forjado")
    assert r.status_code == 403 and microsoft.TEXTO_SEM_PEDIDO in r.get_data(as_text=True)
    assert fake.pedidos == [] and _fora_do_nexus(cliente)
    assert cliente.get("/entrar?code=x").status_code == 403 and fake.pedidos == []
    # nem com uma ida da própria pessoa esperando: o `state` forjado não pega a ida dela, e ela segue valendo
    _r, _q, pedido = _ida(cliente)
    r = cliente.get("/entrar?code=codigo-de-outra-pessoa&state=state-forjado")
    assert r.status_code == 403 and fake.pedidos == [] and _fora_do_nexus(cliente)
    assert _volta(cliente, fake, pedido).status_code == 302 and len(fake.pedidos) == 1


def test_ida_de_mais_de_10_minutos_nao_vale(ms, cliente, fake):
    _r, _q, pedido = _ida(cliente)
    with cliente.session_transaction() as s:
        pedidos = dict(s["ms_pedidos"])
        pedidos[pedido["state"]] = dict(pedido, t=time.time() - microsoft.PEDIDO_S - 1)
        s["ms_pedidos"] = pedidos
    r = _volta(cliente, fake, pedido)
    assert r.status_code == 403 and microsoft.TEXTO_PEDIDO_VENCIDO in r.get_data(as_text=True) and fake.pedidos == []


def test_duas_abas_nao_se_atropelam_e_so_as_tres_ultimas_idas_ficam(ms, cliente, fake):
    idas = [_ida(cliente)[2] for _ in range(4)]
    with cliente.session_transaction() as s:
        assert set(s["ms_pedidos"]) == {p["state"] for p in idas[1:]}
    assert _volta(cliente, fake, idas[0]).status_code == 403          # a mais antiga saiu
    assert _volta(cliente, fake, idas[2]).status_code == 302          # a de outra aba, ainda guardada, entra


@pytest.mark.parametrize("erro, descricao, texto", [
    ("access_denied", "AADSTS65004: User declined to consent to access the app.", "O login foi cancelado na Microsoft."),
    ("access_denied", "AADSTS50105: The signed in user is not assigned to a role for the application.",
     "não está liberada para o Nexus"),
    ("consent_required", "AADSTS65001: The user or administrator has not consented.", "só a T.I. dá"),
])
def test_erro_da_microsoft_vira_texto_e_nao_troca_codigo(ms, fake, erro, descricao, texto):
    cliente = ms.test_client()
    _r, _q, pedido = _ida(cliente)
    r = cliente.get(f"/entrar?error={erro}&error_description={quote(descricao)}&state={pedido['state']}")
    assert r.status_code == 403 and texto in r.get_data(as_text=True) and fake.pedidos == []


def test_erro_forjado_na_volta_nao_escreve_linha_no_journal_e_conta_no_teto(ms, cliente, fake, caplog):
    # quem tem uma ida (qualquer um, pelo /entrar?ms=1) escreve o que quiser no `error`
    _r, _q, pedido = _ida(cliente)
    with caplog.at_level(logging.WARNING, logger="nexus.auth"):
        r = cliente.get(f"/entrar?error={quote('access_denied' + chr(10) + 'linha forjada')}&state={pedido['state']}")
    assert r.status_code == 403 and fake.pedidos == []
    assert "linha forjada" not in caplog.text and "desconhecido" in caplog.text
    assert ("ms", "127.0.0.1") in cliente.application.extensions["nexus_erros_login"]


def test_chave_vencida_avisa_a_ti_e_nao_tranca_a_rede(ms, cliente, fake, caplog):
    fake.resposta = (401, {"error": "invalid_client", "error_description": "AADSTS7000222: The provided client secret "
                                                                          "keys for app are expired."})
    with caplog.at_level(logging.WARNING, logger="nexus.auth"):
        for _ in range(TETO_POR_IP + 2):
            _r, _q, pedido = _ida(cliente)
            r = cliente.get(f"/entrar?code=c&state={pedido['state']}")
            assert r.status_code == 403 and microsoft.TEXTO_CHAVE in r.get_data(as_text=True)
    assert "AADSTS7000222" in caplog.text and "segredo-de-teste" not in caplog.text
    assert ("ms", "127.0.0.1") not in cliente.application.extensions["nexus_erros_login"]


@pytest.mark.parametrize("resposta", [requests.ConnectionError("rede fora"), (503, {"error": "temporarily_unavailable"})])
def test_microsoft_fora_diz_que_nao_respondeu(ms, cliente, fake, resposta):
    _r, _q, pedido = _ida(cliente)
    fake.resposta = resposta
    r = cliente.get(f"/entrar?code=c&state={pedido['state']}")
    assert r.status_code == 503 and microsoft.TEXTO_SEM_RESPOSTA in r.get_data(as_text=True)
    assert _fora_do_nexus(cliente)


def test_codigo_de_lixo_tranca_a_rede_na_volta_e_a_senha_de_admin_segue(ms, cliente, fake):
    fake.resposta = (400, {"error": "invalid_grant", "error_description": "AADSTS70008: The provided authorization "
                                                                         "code has expired."})
    for _ in range(TETO_POR_IP):
        _r, _q, pedido = _ida(cliente)
        assert cliente.get(f"/entrar?code=lixo&state={pedido['state']}").status_code == 403
    chamadas = len(fake.pedidos)
    _r, _q, pedido = _ida(cliente)
    r = cliente.get(f"/entrar?code=lixo&state={pedido['state']}")
    assert r.status_code == 429 and len(fake.pedidos) == chamadas         # trancado: nem vai à Microsoft
    # a reserva continua: a senha de administrador tem o contador dela
    assert cliente.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302


def test_head_no_entrar_e_o_get_sem_corpo_e_nao_tranca_a_senha_de_admin(app, cliente):
    # antes, o HEAD caía no ramo da senha de administrador: 5 de uma rede trancavam a reserva por 15 min
    for _ in range(8):
        assert cliente.head("/entrar").status_code == 200
    assert not cliente.application.extensions["nexus_erros_login"]
    assert cliente.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    app.config.update(NEXUS_MS_CLIENT_ID=CLIENTE, NEXUS_MS_TENANT_ID=DIRETORIO,
                      NEXUS_MS_CLIENT_SECRET="segredo-de-teste", NEXUS_MS_VOLTA=VOLTA)
    r = app.test_client().head("/entrar?ms=1")                 # a conferência do DEPLOY.md 7g (curl -I)
    assert r.status_code == 302 and r.headers["Location"].startswith("https://login.microsoftonline.com/")


@pytest.mark.parametrize("via", [None, "fracttal"])
def test_com_a_microsoft_ligada_quem_estava_dentro_pelo_fracttal_sai(ms, cliente, via):
    # sem isto, a sessão do Fracttal seguia até o fim do token, inclusive a de quem não é da Grid
    with cliente.session_transaction() as s:
        s.update(logado=True, admin=True, fracttal_exp=time.time() + 3600,
                 usuario={"email": "alguem@fracttal.exemplo.test", "nome": "Alguém", "perfil": ""})
        if via:
            s["via"] = via
    cliente.set_cookie("os_sessao", "sessao-do-fracttal", path="/os")
    r = cliente.get("/t/cos/mesa")
    assert r.status_code == 302 and "motivo=porta_microsoft" in r.headers["Location"]
    assert any(h.startswith("os_sessao=;") for h in r.headers.getlist("Set-Cookie")) and _fora_do_nexus(cliente)
    html = cliente.get(r.headers["Location"]).get_data(as_text=True)
    assert MOTIVOS["porta_microsoft"] in html and "Entrar com a Microsoft" in html


# ── a sessão que nasceu da Microsoft ────────────────────────────────────────────────────────────────────────────────
def test_a_sessao_da_microsoft_nao_cai_com_o_fracttal(ms, cliente, fake):
    _entrar_pela_microsoft(cliente, fake)
    # a conferência de 5 minutos da página não derruba quem não entrou pelo Fracttal
    r = cliente.get("/os/_nexus/sessao")
    assert r.status_code == 200 and r.get_json() == {"ok": True}
    # o OS Creator sem o Fracttal pede o login dele, e o Nexus fica
    cliente.get("/os/")
    assert cliente.get("/").status_code == 200
    r = cliente.get("/os/login?next=/os/")
    assert r.status_code == 200 and cliente.get("/").status_code == 200
    # o "sair" do OS Creator, como o Sair do Nexus, sai de tudo (09/10/2026)
    r = cliente.get("/os/logout")
    assert r.status_code == 302 and "motivo=saiu" in r.headers["Location"] and _fora_do_nexus(cliente)


def test_a_sessao_da_microsoft_dura_12_horas_a_partir_do_login(ms, cliente, fake):
    _entrar_pela_microsoft(cliente, fake)
    with cliente.session_transaction() as s:
        s["ms_ate"] = time.time() - 1
    r = cliente.get("/t/cos/mesa")
    assert r.status_code == 302 and "motivo=expirou" in r.headers["Location"] and _fora_do_nexus(cliente)
    html = cliente.get(r.headers["Location"]).get_data(as_text=True)
    assert MOTIVOS["expirou"] in html and "Entrar com a Microsoft" in html


def test_o_portao_do_setor_vale_para_quem_entrou_pela_microsoft(ms, cliente, fake, monkeypatch):
    monkeypatch.setattr(setor_telas, "portao", lambda: ("barrado pelo setor", 418))
    _entrar_pela_microsoft(cliente, fake)
    assert cliente.get("/").status_code == 418
    admin = ms.test_client()
    assert admin.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    assert admin.get("/").status_code == 200                              # a senha de administrador não tem setor


def test_o_prazo_da_tv_e_o_do_login_pela_microsoft(ms):
    from flask import session

    from nexus.torres import moldura
    ate = time.time() + 3600
    with ms.test_request_context():
        session.update(logado=True, via="microsoft", ms_ate=ate,
                       usuario={"email": EMAIL, "nome": "Pessoa Teste", "perfil": ""})
        assert moldura._prazo_da_tv()["vence"] == int(ate)

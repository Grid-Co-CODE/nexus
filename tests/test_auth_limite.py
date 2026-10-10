"""O limite de tentativas do Entrar (auditoria A2 da porta única e revisão adversarial, 10/10/2026).

Até 10/10 o limite era por IP: 5 erros de QUALQUER pessoa no mesmo IP trancavam o Entrar de todos por 15 minutos,
inclusive a senha de administrador, e toda recusa contava, até o 429 do Fracttal. Na segunda-feira em que o Nexus vira
a porta principal todos entram de novo (o cookie é novo), muitos atrás do mesmo IP público do escritório: um colega
errando a senha cinco vezes deixava a sala inteira de fora. A A2 passou o limite para o E-MAIL, e a revisão adversarial
achou o avesso: o contador só por e-mail deixava qualquer um, de qualquer rede, trancar o Entrar de outra pessoa com 5
senhas erradas (o e-mail nome.sobrenome é previsível), e repetindo a cada 15 min o dono ficava de fora o dia todo. Agora:
- 5 erros do mesmo e-mail A PARTIR DA MESMA REDE em 15 min trancam só esse par (e a 6ª nem vai ao Fracttal);
- um teto por e-mail (20 em 15 min, de qualquer rede) segura as tentativas espalhadas;
- o navegador em que a pessoa já entrou (cookie assinado `nexus_dispositivo`) não é barrado pelas travas do e-mail:
  tem um contador só dele (5);
- um teto alto por IP (50 em 15 min) segue contra força bruta de muitos e-mails, para todos;
- recusa que não conferiu a senha (429 ou limite do Fracttal, rede fora) NÃO conta;
- a senha de administrador tem o próprio contador.
"""
import pytest
import requests

from nexus.auth import (COOKIE_DISPOSITIVO, DISPOSITIVO_S, JANELA_S, MAX_ERROS_ADMIN, MAX_ERROS_POR_EMAIL,
                        TETO_POR_EMAIL, TETO_POR_IP, fracttal)

from conftest import SENHA_TESTE

IP_A = "192.0.2.10"          # endereços de documentação (RFC 5737), nunca uma rede de verdade
IP_B = "198.51.100.7"
IP_ATACANTE = "203.0.113.9"
SENHA_DONO = "senha-do-dono"


def _fracttal_falso(monkeypatch, certas=("certa@exemplo.com",), ocupado=False, senha_certa=None):
    """O login do Fracttal sem rede: aceita os e-mails de `certas` (com a `senha_certa`, quando dada) e recusa o resto
    como senha errada (ou como Fracttal ocupado). Devolve a lista de e-mails que chegaram ao Fracttal."""
    chamados = []

    def entrar(app, email, senha):
        chamados.append(email)
        if ocupado:
            raise fracttal.FracttalOcupado("Login falhou: HTTP 429", motivo="limite de pedidos da empresa", limite=True)
        if email.lower() not in certas or (senha_certa is not None and senha != senha_certa):
            raise fracttal.LoginRecusado("E-mail ou senha incorretos.")
        return {"email": email.lower(), "nome": "Pessoa Teste", "perfil": "", "cookie": ("os_sessao", "v", 3600)}
    monkeypatch.setattr(fracttal, "entrar", entrar)
    return chamados


def _entrar(cli, email, ip=IP_A, senha="x"):
    return cli.post("/entrar", data={"email": email, "senha": senha}, environ_base={"REMOTE_ADDR": ip})


def _admin(cli, senha, ip=IP_A):
    return cli.post("/entrar", data={"senha": senha}, environ_base={"REMOTE_ADDR": ip})


def test_os_numeros_do_limite():
    assert (MAX_ERROS_POR_EMAIL, TETO_POR_EMAIL, MAX_ERROS_ADMIN, TETO_POR_IP, JANELA_S) == (5, 20, 5, 50, 15 * 60)
    assert DISPOSITIVO_S == 90 * 24 * 3600


def test_cinco_erros_de_um_email_trancam_so_ele_e_os_colegas_do_mesmo_ip_entram(app, monkeypatch):
    chamados = _fracttal_falso(monkeypatch)
    cli = app.test_client()
    for _ in range(MAX_ERROS_POR_EMAIL):
        assert _entrar(cli, "errou@exemplo.com").status_code == 401
    r = _entrar(cli, "errou@exemplo.com")
    assert r.status_code == 429 and "com este e-mail" in r.get_data(as_text=True)
    # a 6ª tentativa nem foi ao Fracttal (que tem o próprio bloqueio da conta, de ~30 min)
    assert chamados.count("errou@exemplo.com") == MAX_ERROS_POR_EMAIL
    # o colega na mesma rede (o IP público do escritório) entra
    outro = app.test_client()
    assert _entrar(outro, "certa@exemplo.com").status_code == 302


def test_o_email_trancado_vale_com_maiusculas_e_espacos(app, monkeypatch):
    _fracttal_falso(monkeypatch)
    cli = app.test_client()
    for email in ("Errou@Exemplo.com", " errou@exemplo.com", "ERROU@EXEMPLO.COM ", "errou@exemplo.com", "errou@exemplo.COM"):
        assert _entrar(cli, email).status_code == 401
    assert _entrar(app.test_client(), "errou@exemplo.com").status_code == 429     # a mesma rede, outro navegador


def test_acertar_zera_o_contador_do_email(app, monkeypatch):
    certas = ["vai@exemplo.com"]
    _fracttal_falso(monkeypatch, certas=certas)
    cli = app.test_client()
    certas.remove("vai@exemplo.com")
    for _ in range(MAX_ERROS_POR_EMAIL - 1):
        assert _entrar(cli, "vai@exemplo.com").status_code == 401
    certas.append("vai@exemplo.com")
    assert _entrar(cli, "vai@exemplo.com").status_code == 302
    cli.get("/sair")
    certas.remove("vai@exemplo.com")
    for _ in range(MAX_ERROS_POR_EMAIL - 1):
        assert _entrar(cli, "vai@exemplo.com").status_code == 401           # contou do zero de novo


def test_o_fracttal_ocupado_nao_conta_como_senha_errada(app, monkeypatch):
    """429 do Fracttal (o limite de 200/min da empresa, dividido com o App) ou rede fora: o login não foi conferido."""
    chamados = _fracttal_falso(monkeypatch, ocupado=True)
    cli = app.test_client()
    for _ in range(MAX_ERROS_POR_EMAIL * 3):
        r = _entrar(cli, "certa@exemplo.com")
        assert r.status_code == 503
        assert "Fracttal ocupado (limite de pedidos da empresa), tente em instantes" in r.get_data(as_text=True)
    assert len(chamados) == MAX_ERROS_POR_EMAIL * 3
    _fracttal_falso(monkeypatch)                         # o Fracttal voltou
    assert _entrar(cli, "certa@exemplo.com").status_code == 302


def test_a_senha_de_admin_tem_o_proprio_contador(app, monkeypatch):
    _fracttal_falso(monkeypatch)
    cli = app.test_client()
    # os colegas errando o Fracttal não trancam a senha de administrador
    for i in range(MAX_ERROS_POR_EMAIL * 2):
        _entrar(cli, f"pessoa{i % 2}@exemplo.com")
    assert _admin(cli, SENHA_TESTE).status_code == 302
    cli.get("/sair")
    # e quem erra a senha de administrador não tranca o Fracttal de ninguém
    for _ in range(MAX_ERROS_ADMIN):
        assert _admin(cli, "errada").status_code == 401
    r = _admin(cli, SENHA_TESTE)
    assert r.status_code == 429 and "senha de administrador" in r.get_data(as_text=True)
    assert _entrar(app.test_client(), "certa@exemplo.com").status_code == 302


def test_o_teto_por_ip_segura_a_forca_bruta_de_muitos_emails(app, monkeypatch):
    chamados = _fracttal_falso(monkeypatch)
    cli = app.test_client()
    for i in range(TETO_POR_IP):
        assert _entrar(cli, f"tentativa{i}@exemplo.com").status_code == 401
    r = _entrar(cli, "certa@exemplo.com")
    assert r.status_code == 429 and "desta rede" in r.get_data(as_text=True)
    assert _admin(cli, SENHA_TESTE).status_code == 429       # o teto vale para a senha de administrador também
    assert len(chamados) == TETO_POR_IP
    assert _entrar(cli, "certa@exemplo.com", ip=IP_B).status_code == 302     # outra rede segue


def test_a_janela_de_15_minutos_libera_o_email(app, monkeypatch):
    import nexus.auth as auth
    _fracttal_falso(monkeypatch)
    relogio = [1000.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: relogio[0])
    cli = app.test_client()
    for _ in range(MAX_ERROS_POR_EMAIL):
        _entrar(cli, "errou@exemplo.com")
    assert _entrar(cli, "errou@exemplo.com").status_code == 429
    relogio[0] += JANELA_S + 1
    assert _entrar(cli, "errou@exemplo.com").status_code == 401           # destrancou; o Fracttal conferiu de novo


def test_email_ou_senha_vazios_nao_vao_ao_fracttal_nem_contam(app, monkeypatch):
    chamados = _fracttal_falso(monkeypatch)
    cli = app.test_client()
    for _ in range(MAX_ERROS_POR_EMAIL + 2):
        r = cli.post("/entrar", data={"email": "certa@exemplo.com", "senha": ""})
        assert r.status_code == 400 and "Informe o e-mail e a senha" in r.get_data(as_text=True)
    assert chamados == []
    assert _entrar(cli, "certa@exemplo.com").status_code == 302


# ── a tranca do e-mail não pode virar arma contra o dono (revisão adversarial de 10/10/2026) ──────────────────────────
def _redes(n, base=40):
    return [f"203.0.113.{base + i}" for i in range(n)]


def _cookie_do_navegador(cli):
    c = cli.get_cookie(COOKIE_DISPOSITIVO)
    return c.value if c else None


def test_um_ip_tranca_o_email_e_o_dono_de_outra_rede_entra(app, monkeypatch):
    """Como foi provado: 5 erros vindos de 203.0.113.9 e, em seguida, o dono, de 198.51.100.7 e com a senha certa,
    recebia 429."""
    chamados = _fracttal_falso(monkeypatch, certas=("dono@exemplo.com",), senha_certa=SENHA_DONO)
    atacante = app.test_client()
    for _ in range(MAX_ERROS_POR_EMAIL):
        assert _entrar(atacante, "dono@exemplo.com", ip=IP_ATACANTE).status_code == 401
    r = _entrar(atacante, "dono@exemplo.com", ip=IP_ATACANTE)
    assert r.status_code == 429 and "com este e-mail" in r.get_data(as_text=True)
    assert chamados.count("dono@exemplo.com") == MAX_ERROS_POR_EMAIL      # a 6ª do atacante nem foi ao Fracttal
    assert _entrar(app.test_client(), "dono@exemplo.com", ip=IP_B, senha=SENHA_DONO).status_code == 302


def test_o_teto_por_email_segura_tentativas_espalhadas_por_varias_redes(app, monkeypatch):
    chamados = _fracttal_falso(monkeypatch, certas=("dono@exemplo.com",), senha_certa=SENHA_DONO)
    atacante = app.test_client()
    for ip in _redes(TETO_POR_EMAIL // MAX_ERROS_POR_EMAIL):
        for _ in range(MAX_ERROS_POR_EMAIL):
            assert _entrar(atacante, "dono@exemplo.com", ip=ip).status_code == 401
    assert chamados.count("dono@exemplo.com") == TETO_POR_EMAIL
    # mais uma rede (o dono num navegador em que nunca entrou, por exemplo): o teto vale, e nada vai ao Fracttal
    r = _entrar(app.test_client(), "dono@exemplo.com", ip=IP_B)
    assert r.status_code == 429 and "várias redes" in r.get_data(as_text=True)
    assert chamados.count("dono@exemplo.com") == TETO_POR_EMAIL
    # os outros e-mails seguem
    assert _entrar(app.test_client(), "certa@exemplo.com", ip=IP_B).status_code == 401


def test_o_navegador_em_que_o_dono_ja_entrou_nao_e_barrado_pela_tranca_do_email(app, monkeypatch):
    _fracttal_falso(monkeypatch, certas=("dono@exemplo.com",), senha_certa=SENHA_DONO)
    dono = app.test_client()
    assert _entrar(dono, "dono@exemplo.com", ip=IP_A, senha=SENHA_DONO).status_code == 302
    assert _cookie_do_navegador(dono)
    dono.get("/sair")                                    # o Sair encerra a sessão, e o navegador continua conhecido
    assert _cookie_do_navegador(dono)
    # o atacante tranca o e-mail na rede do próprio dono (o mesmo IP do escritório) e no teto global
    atacante = app.test_client()
    for ip in [IP_A] + _redes(TETO_POR_EMAIL // MAX_ERROS_POR_EMAIL - 1):
        for _ in range(MAX_ERROS_POR_EMAIL):
            _entrar(atacante, "dono@exemplo.com", ip=ip)
    assert _entrar(app.test_client(), "dono@exemplo.com", ip=IP_A).status_code == 429     # navegador novo: trancado
    assert _entrar(app.test_client(), "dono@exemplo.com", ip=IP_B).status_code == 429     # teto do e-mail
    # o navegador do dono entra, com a senha certa, da mesma rede do atacante
    assert _entrar(dono, "dono@exemplo.com", ip=IP_A, senha=SENHA_DONO).status_code == 302


def test_o_navegador_conhecido_tem_o_proprio_limite_e_o_teto_do_ip_vale_para_ele(app, monkeypatch):
    chamados = _fracttal_falso(monkeypatch, certas=("dono@exemplo.com",), senha_certa=SENHA_DONO)
    dono = app.test_client()
    assert _entrar(dono, "dono@exemplo.com", senha=SENHA_DONO).status_code == 302
    dono.get("/sair")                                    # quem pegou o navegador depois não sabe a senha
    for _ in range(MAX_ERROS_POR_EMAIL):
        assert _entrar(dono, "dono@exemplo.com").status_code == 401
    antes = len(chamados)
    r = _entrar(dono, "dono@exemplo.com")
    assert r.status_code == 429 and "neste navegador" in r.get_data(as_text=True)
    assert len(chamados) == antes                        # e não foi ao Fracttal
    # o teto da rede vale para todos, com ou sem o cookie
    outro = app.test_client()
    for i in range(TETO_POR_IP):
        _entrar(outro, f"tentativa{i}@exemplo.com", ip=IP_B)
    conhecido = app.test_client()
    assert _entrar(conhecido, "dono@exemplo.com", senha=SENHA_DONO).status_code == 302
    conhecido.get("/sair")
    r = _entrar(conhecido, "dono@exemplo.com", ip=IP_B, senha=SENHA_DONO)
    assert r.status_code == 429 and "desta rede" in r.get_data(as_text=True)


def test_o_cookie_de_outro_email_ou_forjado_nao_destranca(app, monkeypatch):
    _fracttal_falso(monkeypatch, certas=("dono@exemplo.com", "atacante@exemplo.com"), senha_certa=SENHA_DONO)
    atacante = app.test_client()
    # o atacante entra com a conta dele: o navegador dele fica conhecido só para o e-mail dele
    assert _entrar(atacante, "atacante@exemplo.com", ip=IP_ATACANTE, senha=SENHA_DONO).status_code == 302
    atacante.get("/sair")
    for _ in range(MAX_ERROS_POR_EMAIL):
        _entrar(atacante, "dono@exemplo.com", ip=IP_ATACANTE)
    assert _entrar(atacante, "dono@exemplo.com", ip=IP_ATACANTE).status_code == 429
    # um cookie inventado não vale
    forjado = app.test_client()
    forjado.set_cookie(COOKIE_DISPOSITIVO, "eyJkIjoiYWJjIiwiZSI6WyJ4Il19.assinatura.falsa")
    assert _entrar(forjado, "dono@exemplo.com", ip=IP_ATACANTE).status_code == 429


def test_o_cookie_do_navegador_nao_leva_o_email_e_e_so_do_servidor(app, monkeypatch):
    _fracttal_falso(monkeypatch, certas=("dono@exemplo.com",))
    r = _entrar(app.test_client(), "dono@exemplo.com")
    biscoito = [h for h in r.headers.getlist("Set-Cookie") if h.startswith(COOKIE_DISPOSITIVO + "=")]
    assert len(biscoito) == 1
    b = biscoito[0]
    assert "HttpOnly" in b and "SameSite=Lax" in b and "Path=/" in b and f"Max-Age={DISPOSITIVO_S}" in b
    import base64
    valor = b.split(";")[0].split("=", 1)[1]
    corpo = valor.split(".")[0]
    texto = base64.urlsafe_b64decode(corpo + "=" * (-len(corpo) % 4)).decode("latin-1")
    assert "dono" not in texto and "exemplo" not in texto            # só um resumo do e-mail, com a chave do Nexus


def test_o_cookie_do_navegador_sai_no_caminho_do_nexus_debaixo_do_prefixo(monkeypatch):
    from nexus import create_app
    app = create_app({"NEXUS_SECRET_KEY": "chave-de-teste", "NEXUS_SENHA_ADMIN": SENHA_TESTE, "NEXUS_PREFIXO": "/nexus"})
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    _fracttal_falso(monkeypatch, certas=("dono@exemplo.com",))
    r = app.test_client().post("/nexus/entrar", data={"email": "dono@exemplo.com", "senha": "x"})
    b = [h for h in r.headers.getlist("Set-Cookie") if h.startswith(COOKIE_DISPOSITIVO + "=")][0]
    assert "Path=/nexus" in b


# ── o que o clone do OS Creator devolve: conferiu a senha ou não? ──────────────────────────────────────────────────────
class _Resposta:
    def __init__(self, status, corpo):
        self.status_code, self._corpo = status, corpo

    def json(self):
        return self._corpo


@pytest.mark.parametrize("resposta, ocupado", [
    (requests.ConnectionError("rede fora"), True),
    (requests.Timeout("demorou"), True),
    (_Resposta(429, {}), True),
    (_Resposta(429, {"message": "Too Many Requests"}), True),
    (_Resposta(406, {}), True),
    (_Resposta(503, {}), True),
    (_Resposta(502, {"message": "Bad Gateway"}), True),
    (_Resposta(200, {"message": "RATE_LIMIT_EXCEEDED"}), True),
    (_Resposta(200, {"message": "USER_OR_INVALID_KEY"}), False),
    (_Resposta(401, {"message": "USER_OR_INVALID_KEY"}), False),
    (_Resposta(200, {"message": "FAILURE_INTENT_BLOCK"}), False),
])
def test_o_login_do_fracttal_separa_ocupado_de_senha_errada(app, monkeypatch, resposta, ocupado):
    """Pelo `api.fracttal_login` de verdade do clone (só o `requests.post` é falso): as mensagens que ele monta são as
    que o Nexus classifica. Conta bloqueada pelo Fracttal (tentativas demais) conta: é consequência de senha errada."""
    from nexus.torres.oscreator import ponte
    ponte.clone(app)
    import api as os_api

    def post(*a, **k):
        if isinstance(resposta, Exception):
            raise resposta
        return resposta
    monkeypatch.setattr(os_api.requests, "post", post)
    with pytest.raises(fracttal.LoginRecusado) as erro:
        fracttal.entrar(app, "pessoa@exemplo.com", "senha")
    assert isinstance(erro.value, fracttal.FracttalOcupado) is ocupado, str(erro.value)


# ── o erro de verdade aparece na tela e no journal (revisão adversarial de 10/10/2026) ─────────────────────────────────
# Toda "Erro de conexão no login" virava "Fracttal ocupado, tente em instantes", e o erro original (DNS, certificado,
# proxy) era descartado, sem log: se a saída do servidor para o Fracttal quebrasse, todos veriam "tente em instantes"
# para sempre, e o journal ficaria vazio.
def _post_do_requests(monkeypatch, app, resposta):
    from nexus.torres.oscreator import ponte
    ponte.clone(app)
    import api as os_api

    def post(*a, **k):
        if isinstance(resposta, Exception):
            raise resposta
        return resposta
    monkeypatch.setattr(os_api.requests, "post", post)
    return os_api


@pytest.mark.parametrize("erro, classe, original, motivo", [
    (requests.exceptions.SSLError("certificate verify failed: self-signed certificate (pessoa@exemplo.com)"),
     "SSLError", "certificate verify failed", "recusou o certificado do Fracttal"),
    (requests.ConnectionError("HTTPSConnectionPool(host='fracttal.invalid', port=443): Max retries exceeded "
                              "(Caused by NameResolutionError: Failed to resolve 'fracttal.invalid' (getaddrinfo failed))"),
     "ConnectionError", "Failed to resolve", "não achou o endereço do Fracttal (DNS)"),
    (requests.exceptions.ProxyError("Unable to connect to proxy"), "ProxyError", "Unable to connect to proxy",
     "proxy da rede barrou"),
    (requests.ConnectionError("Connection reset by peer"), "ConnectionError", "Connection reset by peer",
     "sem conexão do servidor com o Fracttal"),
    (requests.Timeout("Read timed out. (read timeout=25)"), "Timeout", "Read timed out", "não respondeu a tempo"),
])
def test_o_erro_de_rede_vai_para_o_journal_e_o_motivo_para_a_tela(app, monkeypatch, caplog, erro, classe, original,
                                                                  motivo):
    _post_do_requests(monkeypatch, app, erro)
    cli = app.test_client()
    with caplog.at_level("WARNING", logger="nexus.auth"):
        for _ in range(MAX_ERROS_POR_EMAIL + 2):                    # e não conta: nunca vira 429
            r = _entrar(cli, "pessoa@exemplo.com", senha="segredo-digitado")
            assert r.status_code == 503
    tela = r.get_data(as_text=True)
    assert motivo in tela and "não chegou a ser conferida" in tela and "avise a T.I." in tela
    registros = [x for x in caplog.records if x.name == "nexus.auth"]
    assert len(registros) == MAX_ERROS_POR_EMAIL + 2
    log = registros[-1].getMessage()
    assert f"{classe}: " in log and original in log and motivo in log
    assert "pessoa@exemplo.com" not in log and "segredo-digitado" not in log


def test_o_limite_do_fracttal_diz_ocupado_e_vai_ao_journal(app, monkeypatch, caplog):
    _post_do_requests(monkeypatch, app, _Resposta(429, {}))
    with caplog.at_level("WARNING", logger="nexus.auth"):
        r = _entrar(app.test_client(), "pessoa@exemplo.com")
    assert r.status_code == 503
    assert "Fracttal ocupado (limite de pedidos da empresa), tente em instantes" in r.get_data(as_text=True)
    assert any("HTTP 429" in x.getMessage() for x in caplog.records if x.name == "nexus.auth")


def test_a_sessao_que_nao_veio_e_erro_proprio_mostrado_e_registrado(app, monkeypatch, caplog):
    """A senha passou e o JWT não foi gravado (a costura do clone com o `api._save_jwt`): era um "ocupado" mudo."""
    os_api = _post_do_requests(monkeypatch, app, requests.ConnectionError("não deve chegar aqui"))
    monkeypatch.setattr(os_api, "fracttal_login", lambda email, senha: {"email": email, "jwt_exp": 0})
    cli = app.test_client()
    with caplog.at_level("ERROR", logger="nexus.auth"):
        for _ in range(MAX_ERROS_POR_EMAIL + 2):                    # não é senha errada: não conta
            r = _entrar(cli, "pessoa@exemplo.com")
            assert r.status_code == 500
    tela = r.get_data(as_text=True)
    assert "O Fracttal aceitou a senha, mas a sessão não chegou ao Nexus" in tela and "avise a T.I." in tela
    assert "ocupado" not in tela
    log = [x for x in caplog.records if x.name == "nexus.auth" and x.levelname == "ERROR"]
    assert log and "_save_jwt" in log[-1].getMessage()
    with pytest.raises(fracttal.SessaoNaoVeio):
        fracttal.entrar(app, "pessoa@exemplo.com", "x")
    assert not issubclass(fracttal.SessaoNaoVeio, fracttal.FracttalOcupado)


def test_os_emails_vencidos_saem_da_memoria(app, monkeypatch):
    """O e-mail é texto livre de quem tenta: sem poda, um robô com um e-mail novo a cada tentativa enchia a memória."""
    import nexus.auth as auth
    _fracttal_falso(monkeypatch)
    monkeypatch.setattr(auth, "_MAX_CHAVES", 6)
    relogio = [1000.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: relogio[0])
    cli = app.test_client()
    for i in range(4):
        _entrar(cli, f"velho{i}@exemplo.com", ip=f"192.0.2.{20 + i}")
    relogio[0] += JANELA_S + 1
    for i in range(3):
        _entrar(cli, f"novo{i}@exemplo.com")
    chaves = app.extensions["nexus_erros_login"]
    assert not any(c[1].startswith("velho") for c in chaves)          # os de mais de 15 min saíram
    assert sum(c[0] == "email" for c in chaves) == 3

"""O limite de tentativas do Entrar (auditoria A2 da porta única, 10/10/2026).

Até 10/10 o limite era por IP: 5 erros de QUALQUER pessoa no mesmo IP trancavam o Entrar de todos por 15 minutos,
inclusive a senha de administrador, e toda recusa contava, até o 429 do Fracttal. Na segunda-feira em que o Nexus vira
a porta principal todos entram de novo (o cookie é novo), muitos atrás do mesmo IP público do escritório: um colega
errando a senha cinco vezes deixava a sala inteira de fora. Agora:
- 5 erros do mesmo E-MAIL em 15 min trancam só aquele e-mail (e a 6ª tentativa nem vai ao Fracttal);
- um teto alto por IP (50 em 15 min) segue contra força bruta de muitos e-mails;
- recusa que não conferiu a senha (429 ou limite do Fracttal, rede fora) NÃO conta: a pessoa vê "Fracttal ocupado";
- a senha de administrador tem o próprio contador.
"""
import pytest
import requests

from nexus.auth import JANELA_S, MAX_ERROS_ADMIN, MAX_ERROS_POR_EMAIL, TETO_POR_IP, fracttal

from conftest import SENHA_TESTE

IP_A = "192.0.2.10"          # endereços de documentação (RFC 5737), nunca uma rede de verdade
IP_B = "198.51.100.7"


def _fracttal_falso(monkeypatch, certas=("certa@exemplo.com",), ocupado=False):
    """O login do Fracttal sem rede: aceita os e-mails de `certas` e recusa o resto como senha errada (ou como
    Fracttal ocupado). Devolve a lista de e-mails que chegaram ao Fracttal."""
    chamados = []

    def entrar(app, email, senha):
        chamados.append(email)
        if ocupado:
            raise fracttal.FracttalOcupado("Login falhou: HTTP 429")
        if email.lower() not in certas:
            raise fracttal.LoginRecusado("E-mail ou senha incorretos.")
        return {"email": email.lower(), "nome": "Pessoa Teste", "perfil": "", "cookie": ("os_sessao", "v", 3600)}
    monkeypatch.setattr(fracttal, "entrar", entrar)
    return chamados


def _entrar(cli, email, ip=IP_A, senha="x"):
    return cli.post("/entrar", data={"email": email, "senha": senha}, environ_base={"REMOTE_ADDR": ip})


def _admin(cli, senha, ip=IP_A):
    return cli.post("/entrar", data={"senha": senha}, environ_base={"REMOTE_ADDR": ip})


def test_os_numeros_do_limite():
    assert (MAX_ERROS_POR_EMAIL, MAX_ERROS_ADMIN, TETO_POR_IP, JANELA_S) == (5, 5, 50, 15 * 60)


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
    assert _entrar(cli, "errou@exemplo.com", ip=IP_B).status_code == 429      # o e-mail, de qualquer rede


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
        assert "Fracttal ocupado, tente em instantes" in r.get_data(as_text=True)
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

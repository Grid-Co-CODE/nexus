"""Torre Performance → Tempo real: a plataforma inteira, só leitura, pela ponte (04/10/2026)."""
import pytest

from nexus import create_app
from nexus.performance import ponte

from conftest import SENHA_TESTE


class _Resp:
    # A plataforma que cumpre a chave de leitura devolve `X-Nexus-Leitura-Ok: 1` em toda resposta que ela deixou passar;
    # a ponte exige (falha fechada). `confirma=False` simula a plataforma aberta, sem NEXUS_LEITURA_TOKEN.
    def __init__(self, status=200, corpo=b"{}", tipo="application/json", extra=None, confirma=True):
        self.status_code, self.content = status, corpo
        self.headers = {"Content-Type": tipo, **({"X-Nexus-Leitura-Ok": "1"} if confirma else {}), **(extra or {})}


@pytest.fixture
def app_ponte():
    app = create_app({"NEXUS_SECRET_KEY": "k", "NEXUS_SENHA_ADMIN": SENHA_TESTE,
                      "NEXUS_PLATAFORMA_URL": "https://plat:5050", "NEXUS_PLATAFORMA_TOKEN": "segredo-xyz"})
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    return app


@pytest.fixture
def logado_ponte(app_ponte):
    c = app_ponte.test_client()
    assert c.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    return c


def test_aba_mostra_a_plataforma_na_moldura(logado_ponte):
    html = logado_ponte.get("/t/performance/tempo-real").get_data(as_text=True)
    assert f'src="{ponte.PREFIXO}/tempo-real"' in html and "somente leitura" in html.lower()
    assert 'class="menu"' in html and "Em construção" not in html


def test_ponte_exige_login(app_ponte):
    r = app_ponte.test_client().get(ponte.PREFIXO + "/api/state")
    assert r.status_code == 302


def test_ponte_leva_o_pedido_e_devolve_sem_cookie(logado_ponte, monkeypatch):
    visto = {}

    def falso(**p):
        visto.update(p)
        return _Resp(extra={"Set-Cookie": "s=1"})
    monkeypatch.setattr(ponte, "enviar", falso)
    r = logado_ponte.get(ponte.PREFIXO + "/api/pv/trackers/parados?force=1&data=x")
    assert r.status_code == 200
    # O único cookie que sai é o da sessão do próprio Nexus (12 h deslizantes); o da plataforma não passa.
    cookies = r.headers.getlist("Set-Cookie")
    assert all(c.startswith("session=") for c in cookies) and not any("s=1" in c for c in cookies)
    assert visto["url"] == "https://plat:5050/api/pv/trackers/parados" and visto["params"] == [("data", "x")]
    assert visto["headers"]["X-Nexus-Leitura"] == "segredo-xyz"


def test_caminho_nunca_troca_de_servidor(logado_ponte, monkeypatch):
    # O <path:> chega SEM a barra inicial. Se a rota o entregasse cru, "@evil.com/x" viraria
    # "https://plat:5050@evil.com/x" (usuário "plat", servidor evil.com) e a chave de leitura iria para fora.
    visto = {}

    def falso(**p):
        visto.update(p)
        return _Resp()
    monkeypatch.setattr(ponte, "enviar", falso)
    r = logado_ponte.get(ponte.PREFIXO + "/@evil.com/x")
    assert r.status_code == 200
    assert visto["url"].startswith("https://plat:5050/@evil.com")


@pytest.mark.parametrize("metodo,caminho", [
    ("get", "/api/x%3Fforce=1%26run=1"),
    ("post", "/api/etm/os%3Fforce=1"),
    ("get", "/tempo-real%23x"),
])
def test_query_escondida_no_caminho_nao_sai(logado_ponte, monkeypatch, metodo, caminho):
    # O Flask decodifica %3F e %23 dentro do <path:>. Sem esta recusa, "/api/x%3Fforce=1" viraria a URL
    # ".../api/x?force=1": o force/run chegaria à plataforma por fora do filtro do montar_pedido (que só limpa a
    # query de verdade) e o POST de consulta passaria no pode_passar mesmo com a query colada.
    monkeypatch.setattr(ponte, "enviar", lambda **p: pytest.fail("pedido com query escondida saiu do Nexus"))
    r = getattr(logado_ponte, metodo)(ponte.PREFIXO + caminho)
    assert r.status_code == 400 and r.get_json()["error"] == "caminho inválido"


def test_gravacao_nao_sai_do_nexus(logado_ponte, monkeypatch):
    monkeypatch.setattr(ponte, "enviar", lambda **p: pytest.fail("gravação saiu do Nexus"))
    r = logado_ponte.post(ponte.PREFIXO + "/api/state/tracking", json={"key": "x"})
    assert r.status_code == 403 and r.get_json()["error"] == "somente leitura (Nexus)"


def test_post_de_consulta_passa(logado_ponte, monkeypatch):
    monkeypatch.setattr(ponte, "enviar", lambda **p: _Resp(corpo=b'{"A":1}'))
    r = logado_ponte.post(ponte.PREFIXO + "/api/os-performance/counts", json={"usinas": ["A"]})
    assert r.status_code == 200 and r.get_json() == {"A": 1}


def test_plataforma_fora_mostra_a_hora_e_tentar_de_novo(logado_ponte, monkeypatch):
    def cai(**p):
        raise ponte.ForaDoAr("ReadTimeout")
    monkeypatch.setattr(ponte, "enviar", cai)
    r = logado_ponte.get(ponte.PREFIXO + "/tempo-real")
    assert r.status_code == 502
    corpo = r.get_data(as_text=True)
    assert "Plataforma de Performance sem resposta" in corpo and "Tentar de novo" in corpo
    assert "<title>Plataforma de Performance sem resposta</title>" in corpo


def test_chave_recusada_diz_sem_mostrar_a_chave(logado_ponte, monkeypatch):
    monkeypatch.setattr(ponte, "enviar", lambda **p: _Resp(401, b'{"error":"chave de leitura recusada"}'))
    r = logado_ponte.get(ponte.PREFIXO + "/tempo-real")
    corpo = r.get_data(as_text=True)
    assert r.status_code == 502 and "recusou a chave" in corpo and "segredo-xyz" not in corpo


def test_chave_recusada_pelo_salto_para_o_login_diz_o_mesmo(logado_ponte, monkeypatch):
    # sem a chave valendo, a plataforma manda o pedido para o /login (302); a ponte não segue e diz a causa certa
    monkeypatch.setattr(ponte, "enviar", lambda **p: _Resp(
        302, b"", extra={"Location": "/t/performance/plataforma/login?next=%2Ftempo-real"}))
    r = logado_ponte.get(ponte.PREFIXO + "/tempo-real")
    corpo = r.get_data(as_text=True)
    assert r.status_code == 502 and "recusou a chave" in corpo and "<h1>A plataforma recusou a chave</h1>" in corpo


def test_plataforma_que_nao_confirma_a_chave_nao_mostra_nada(logado_ponte, monkeypatch):
    # Se a plataforma estiver aberta (sem NEXUS_LEITURA_TOKEN) ela ignora a chave e deixa passar qualquer coisa; sem o
    # `X-Nexus-Leitura-Ok` a ponte não mostra a resposta (falha fechada).
    monkeypatch.setattr(ponte, "enviar", lambda **p: _Resp(corpo=b'{"segredo":"x"}', confirma=False))
    r = logado_ponte.get(ponte.PREFIXO + "/api/state")
    corpo = r.get_data(as_text=True)
    assert r.status_code == 502 and "não confirmou a chave de leitura" in corpo and "NEXUS_LEITURA_TOKEN" in corpo
    assert "segredo" not in corpo and "<h1>Plataforma não confirmou a chave</h1>" in corpo


def test_confirmacao_da_chave_vale_em_qualquer_caixa(logado_ponte, monkeypatch):
    # HTTP/2 e Cloudflare baixam a caixa dos nomes
    resp = _Resp(confirma=False)
    resp.headers["x-nexus-leitura-ok"] = "1"
    monkeypatch.setattr(ponte, "enviar", lambda **p: resp)
    assert logado_ponte.get(ponte.PREFIXO + "/api/state").status_code == 200


def test_ponte_ocupada_devolve_503_e_nao_prende_o_nexus(logado_ponte, monkeypatch):
    # 4 vagas: a plataforma lenta (drill da API PV, até 120 s) não pode esgotar as threads do Nexus e travar a casca
    monkeypatch.setattr(ponte, "ESPERA_VAGA_S", 0.05)
    monkeypatch.setattr(ponte, "_SESSAO", type("S", (), {"request": lambda *a, **k: pytest.fail("saiu sem vaga")})())
    tomadas = 0
    while ponte._VAGAS.acquire(blocking=False):
        tomadas += 1
    try:
        r = logado_ponte.get(ponte.PREFIXO + "/api/state")
    finally:
        for _ in range(tomadas):
            ponte._VAGAS.release()
    corpo = r.get_data(as_text=True)
    assert tomadas == 4 and r.status_code == 503
    assert "A ponte está ocupada com outros pedidos à plataforma. Tente de novo em instantes." in corpo
    assert "<h1>Ponte ocupada</h1>" in corpo


def test_salto_para_outro_servidor_nao_leva_a_chave(logado_ponte, monkeypatch):
    class Sessao:
        pedidos = []

        def request(self, **p):
            self.pedidos.append(p)
            return _Resp(302, b"", extra={"Location": "https://evil.com/x"})
    monkeypatch.setattr(ponte, "_SESSAO", Sessao())
    r = logado_ponte.get(ponte.PREFIXO + "/tempo-real")
    corpo = r.get_data(as_text=True)
    assert r.status_code == 502 and "outro servidor" in corpo and "segredo-xyz" not in corpo
    assert len(Sessao.pedidos) == 1 and Sessao.pedidos[0]["url"].startswith("https://plat:5050/")


def _app_com(url):
    app = create_app({"NEXUS_SECRET_KEY": "k", "NEXUS_SENHA_ADMIN": SENHA_TESTE,
                      "NEXUS_PLATAFORMA_URL": url, "NEXUS_PLATAFORMA_TOKEN": "segredo-xyz"})
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    c = app.test_client()
    assert c.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    return c


@pytest.mark.parametrize("url", ["http://plat:5050", "http://10.0.0.5:5050", "http://app.gridco.com.br"])
def test_http_fora_da_maquina_local_e_recusado_antes_de_qualquer_rede(url, monkeypatch):
    # com http a chave de leitura iria em texto puro pela rede
    monkeypatch.setattr(ponte, "enviar", lambda **p: pytest.fail("a chave saiu sem criptografia"))
    monkeypatch.setattr(ponte, "_SESSAO", type("S", (), {"request": lambda *a, **k: pytest.fail("rede")})())
    r = _app_com(url).get(ponte.PREFIXO + "/tempo-real")
    corpo = r.get_data(as_text=True)
    assert r.status_code == 502 and "NEXUS_PLATAFORMA_URL tem de ser https fora da máquina local" in corpo
    assert "<h1>Ponte não configurada</h1>" in corpo


@pytest.mark.parametrize("url", ["http://localhost:5050", "http://127.0.0.1:5050", "http://[::1]:5050", "https://plat"])
def test_http_na_maquina_local_e_https_em_qualquer_lugar_passam(url, monkeypatch):
    monkeypatch.setattr(ponte, "enviar", lambda **p: _Resp())
    assert _app_com(url).get(ponte.PREFIXO + "/api/state").status_code == 200


def test_sem_configuracao_a_aba_diz_o_que_falta(logado):
    html = logado.get("/t/performance/tempo-real").get_data(as_text=True)
    assert "NEXUS_PLATAFORMA_URL" in html

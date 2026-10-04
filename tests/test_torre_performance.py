"""Torre Performance → Tempo real: a plataforma inteira, só leitura, pela ponte (04/10/2026)."""
import pytest

from nexus import create_app
from nexus.performance import ponte

from conftest import SENHA_TESTE


class _Resp:
    def __init__(self, status=200, corpo=b"{}", tipo="application/json", extra=None):
        self.status_code, self.content = status, corpo
        self.headers = {"Content-Type": tipo, **(extra or {})}


@pytest.fixture
def app_ponte():
    app = create_app({"NEXUS_SECRET_KEY": "k", "NEXUS_SENHA_ADMIN": SENHA_TESTE,
                      "NEXUS_PLATAFORMA_URL": "http://plat:5050", "NEXUS_PLATAFORMA_TOKEN": "segredo-xyz"})
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
    assert visto["url"] == "http://plat:5050/api/pv/trackers/parados" and visto["params"] == [("data", "x")]
    assert visto["headers"]["X-Nexus-Leitura"] == "segredo-xyz"


def test_caminho_nunca_troca_de_servidor(logado_ponte, monkeypatch):
    # O <path:> chega SEM a barra inicial. Se a rota o entregasse cru, "@evil.com/x" viraria
    # "http://plat:5050@evil.com/x" (usuário "plat", servidor evil.com) e a chave de leitura iria para fora.
    visto = {}

    def falso(**p):
        visto.update(p)
        return _Resp()
    monkeypatch.setattr(ponte, "enviar", falso)
    r = logado_ponte.get(ponte.PREFIXO + "/@evil.com/x")
    assert r.status_code == 200
    assert visto["url"].startswith("http://plat:5050/@evil.com")


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


def test_chave_recusada_diz_sem_mostrar_a_chave(logado_ponte, monkeypatch):
    monkeypatch.setattr(ponte, "enviar", lambda **p: _Resp(401, b'{"error":"chave de leitura recusada"}'))
    r = logado_ponte.get(ponte.PREFIXO + "/tempo-real")
    corpo = r.get_data(as_text=True)
    assert r.status_code == 502 and "recusou a chave" in corpo and "segredo-xyz" not in corpo


def test_sem_configuracao_a_aba_diz_o_que_falta(logado):
    html = logado.get("/t/performance/tempo-real").get_data(as_text=True)
    assert "NEXUS_PLATAFORMA_URL" in html

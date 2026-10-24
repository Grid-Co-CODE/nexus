"""O Nexus por dentro no Raio-X (24/10/2026, nexus/casca/memoria_nexus.py). Raio-X das 12:05 de 24/10, na máquina nova:
o Nexus com 682 MB na memória e 1.917 MB no swap, e a página mostrava por dentro o worker e o web da plataforma, mas não
o próprio Nexus. A medida é a da plataforma (por amostra), das variáveis dos módulos do Nexus e das extensões do app, a
cada 10 min numa thread, com teto de tempo; o Raio-X só mostra a última (não mede nada ao abrir)."""
import sys
import threading
import time
import types
from datetime import datetime, timedelta

import pytest

from nexus.casca import memoria_nexus as MN
from nexus.casca import raio_x as R


@pytest.fixture(autouse=True)
def _limpo(monkeypatch):
    for nome in ("_WORKER", "_WEB", "_MEMORIA"):
        monkeypatch.setattr(R, nome, {"thread": None, "ultimo": None, "quando": None}, raising=False)
    monkeypatch.setattr(R, "_processador", lambda janela_s=1.0: {"pct": 10, "nucleos": 4, "carga": None})
    monkeypatch.setattr(R, "_memoria_por_programa", lambda prazo_s=R.PRAZO_MEMORIA_S: None)
    monkeypatch.setattr(R, "RELATORIO_WEB", "/nao/existe/web.json")
    monkeypatch.setattr(R, "RELATORIO_WORKER", "/nao/existe/worker.json")


@pytest.fixture
def modulo_com_cache(monkeypatch):
    """Um módulo do Nexus de mentira com um cache de ~10 MB (10 mil textos de 1.000 letras)."""
    m = types.ModuleType("nexus._cache_de_teste")
    m.__file__ = MN.RAIZ + "/nexus/_cache_de_teste.py"
    m._grande = {i: "x" * 1000 + str(i) for i in range(10_000)}
    m._pequeno = [1, 2, 3]
    monkeypatch.setitem(sys.modules, m.__name__, m)
    return m


def test_a_estimativa_por_amostra_bate_com_o_tamanho(modulo_com_cache):
    real = sys.getsizeof(modulo_com_cache._grande) + sum(sys.getsizeof(k) + sys.getsizeof(v)
                                                         for k, v in modulo_com_cache._grande.items())
    est = MN.tamanho_estimado(modulo_com_cache._grande, set())
    assert 0.8 * real < est < 1.2 * real


def test_mede_as_variaveis_e_as_extensoes(app, modulo_com_cache):
    app.extensions["cache_por_app"] = ["y" * 2000 + str(i) for i in range(2000)]          # ~4 MB
    rel = MN.medir(app, prazo_s=30, teto=100_000)
    nomes = {c["nome"]: c for c in rel["caches"]}
    assert all(c["mb"] >= 1 for c in rel["caches"])                               # menos de 1 MB não entra
    assert 8 < nomes["nexus._cache_de_teste._grande"]["mb"] < 12 and nomes["nexus._cache_de_teste._grande"]["itens"] == 10_000
    assert 3 < nomes["app.extensions['cache_por_app']"]["mb"] < 5
    assert "nexus._cache_de_teste._pequeno" not in nomes                          # menos de 1 MB não entra
    assert rel["caches"] == sorted(rel["caches"], key=lambda c: -c["mb"]) and not rel["parcial"]


def test_o_app_nao_vira_um_bloco_so(app, modulo_com_cache, monkeypatch):
    """O app do Flask guarda tudo: medido por ele, uma variável que o aponta engoliria as extensões."""
    modulo_com_cache._o_app = app
    app.extensions["cache_por_app"] = ["y" * 2000 + str(i) for i in range(2000)]
    app.config["_GRANDE_NA_CONFIG"] = ["z" * 2000 + str(i) for i in range(2000)]   # só se alcança pelo app
    nomes = [c["nome"] for c in MN.medir(app, prazo_s=30)["caches"]]
    assert "nexus._cache_de_teste._o_app" not in nomes and "app.extensions['cache_por_app']" in nomes
    assert MN.tamanho_estimado(app, set()) == 0 and MN.tamanho_estimado({"a": app}, set()) < 2**20


def test_o_teto_de_tempo_corta_e_diz(app, modulo_com_cache):
    rel = MN.medir(app, prazo_s=0)
    assert rel["parcial"] is True and rel["caches"] == []


def test_o_raio_x_mostra_a_ultima_medida_e_a_de_1_hora_antes(app, logado, modulo_com_cache):
    assert "Dentro do Nexus" not in logado.get("/t/base/raio-x").get_data(as_text=True)    # antes da 1ª medida
    agora = datetime.now()
    antes = (agora - timedelta(minutes=65)).strftime("%Y-%m-%dT%H:%M:%S")
    MN._anotar(app, {"quando": antes, "rss_mb": 600, "swap_mb": 1800, "parcial": False,
                     "caches": [{"nome": "nexus._cache_de_teste._grande", "mb": 4.0, "itens": 4000}]})
    MN.medir_e_anotar(app)
    h = logado.get("/t/base/raio-x").get_data(as_text=True)
    assert "Dentro do Nexus" in h and "nexus._cache_de_teste._grande" in h
    assert "Às " + (agora - timedelta(minutes=65)).strftime("%H:%M") in h and ">4 MB<" in h


def test_liga_a_thread_que_mede(app, modulo_com_cache):
    MN.ligar(app, intervalo_s=3600, primeira_s=0)
    fim = time.monotonic() + 15
    while MN.ultimo(app) is None:
        assert time.monotonic() < fim, "a thread não mediu"
        time.sleep(0.05)
    assert any(t.name == "nexus-memoria" for t in threading.enumerate())
    assert any(c["nome"] == "nexus._cache_de_teste._grande" for c in MN.ultimo(app)["caches"])

"""Dentro do worker da plataforma de Performance, no Raio-X (20/10/2026). No servidor o worker foi de 3,7 para 5,0 GB
(com o swap) em 26 min, entre 16:12 e 16:38 de 20/10, e o Nexus travou esperando o disco; a medição de dentro só dava no
PC, que não roda os backfills do servidor. Levi escolheu ver no Raio-X: a cada 10 min o próprio worker grava em
/dev/shm quanto cada variável dele ocupa (PerformancePainel, `_relatorio_memoria_worker`), com as últimas 3 h, e o
Raio-X mostra agora × 1 h atrás. Aqui o arquivo é de mentira."""
import json
from datetime import datetime

import pytest

from nexus.casca import raio_x as R


@pytest.fixture(autouse=True)
def _limpo(monkeypatch):
    monkeypatch.setattr(R, "_WORKER", {"thread": None, "ultimo": None, "quando": None}, raising=False)
    monkeypatch.setattr(R, "_MEMORIA", {"thread": None, "ultimo": None, "quando": None}, raising=False)


def _relatorio(caminho, quando="2026-10-20T16:38:00"):
    rel = {"quando": quando, "pid": 4242, "rss_mb": 4443, "swap_mb": 554, "parcial": False, "segundos": 1.2,
           "caches": [{"nome": "app._pv_trk_dia_cache", "mb": 1620.4, "itens": 230},
                      {"nome": "app._2c_str_dia_cache", "mb": 335.0, "itens": 2},
                      {"nome": "app._cache_novo", "mb": 900.0, "itens": 4000}],
           "historico": [{"quando": "2026-10-20T15:28:00", "rss_mb": 2900, "swap_mb": 0,
                          "caches": {"app._pv_trk_dia_cache": 1200.0, "app._2c_str_dia_cache": 330.0}},
                         {"quando": "2026-10-20T15:38:00", "rss_mb": 3050, "swap_mb": 10,
                          "caches": {"app._pv_trk_dia_cache": 1250.0, "app._2c_str_dia_cache": 331.0,
                                     "app._cache_novo": 20.0}},
                         {"quando": "2026-10-20T16:28:00", "rss_mb": 4300, "swap_mb": 400,
                          "caches": {"app._pv_trk_dia_cache": 1600.0}},
                         {"quando": quando, "rss_mb": 4443, "swap_mb": 554,
                          "caches": {"app._pv_trk_dia_cache": 1620.4, "app._2c_str_dia_cache": 335.0,
                                     "app._cache_novo": 900.0}}]}
    caminho.write_text(json.dumps(rel), encoding="utf-8")
    return rel


def test_le_o_relatorio_e_compara_com_uma_hora_antes(tmp_path):
    arq = tmp_path / "gridco_plataforma_worker.json"
    _relatorio(arq)
    w = R._ler_relatorio_worker(str(arq), agora=datetime(2026, 10, 20, 16, 41))
    assert (w["quando"], w["idade_min"], w["rss_mb"], w["swap_mb"], w["velho"]) == ("16:38", 3, 4443, 554, False)
    assert (w["antes_quando"], w["rss_antes_mb"], w["swap_antes_mb"]) == ("15:38", 3050, 10)   # a passada de ~1 h antes
    assert [(c["nome"], c["mb"], c["antes_mb"]) for c in w["caches"]] == [
        ("app._pv_trk_dia_cache", 1620.4, 1250.0), ("app._2c_str_dia_cache", 335.0, 331.0),
        ("app._cache_novo", 900.0, 20.0)]


def test_relatorio_velho_avisa_que_o_worker_parou_de_anotar(tmp_path):
    arq = tmp_path / "gridco_plataforma_worker.json"
    _relatorio(arq)
    assert R._ler_relatorio_worker(str(arq), agora=datetime(2026, 10, 20, 17, 20))["velho"] is True   # 42 min


def test_sem_o_arquivo_nao_ha_secao(tmp_path):
    assert R._ler_relatorio_worker(str(tmp_path / "nao_existe.json")) is None
    (tmp_path / "torto.json").write_text("{", encoding="utf-8")
    assert R._ler_relatorio_worker(str(tmp_path / "torto.json")) is None


def test_o_relatorio_tambem_tem_prazo(monkeypatch):
    """Ler /dev/shm é memória, mas no swap ela também espera o disco: o mesmo prazo da lista de programas."""
    import threading
    solta = threading.Event()
    monkeypatch.setattr(R, "_ler_relatorio_worker", lambda *a, **k: solta.wait(10) and None)
    try:
        assert R._worker_plataforma(prazo_s=0.2)["atrasado"] is True
    finally:
        solta.set()


def test_a_pagina_mostra_o_que_cresce_no_worker(app, logado, monkeypatch, tmp_path):
    arq = tmp_path / "gridco_plataforma_worker.json"
    _relatorio(arq)
    monkeypatch.setattr(R, "RELATORIO_WORKER", str(arq))
    monkeypatch.setattr(R, "_processador", lambda janela_s=1.0: {"pct": 10, "nucleos": 4, "carga": [5.69, 4.62, 3.99],
                                                                   "maquina": None})
    monkeypatch.setattr(R, "_memoria_por_programa", lambda prazo_s=R.PRAZO_MEMORIA_S: None)
    h = logado.get("/t/base/raio-x").get_data(as_text=True)
    assert "Dentro do worker da plataforma" in h and "app._cache_novo" in h
    assert "900 MB" in h and "20 MB" in h                          # agora e 1 h antes, lado a lado


def test_sem_o_relatorio_a_pagina_fica_como_era(app, logado, monkeypatch, tmp_path):
    monkeypatch.setattr(R, "RELATORIO_WORKER", str(tmp_path / "nao_existe.json"))
    monkeypatch.setattr(R, "_processador", lambda janela_s=1.0: {"pct": 10, "nucleos": 4, "carga": None})
    monkeypatch.setattr(R, "_memoria_por_programa", lambda prazo_s=R.PRAZO_MEMORIA_S: None)
    assert "Dentro do worker da plataforma" not in logado.get("/t/base/raio-x").get_data(as_text=True)

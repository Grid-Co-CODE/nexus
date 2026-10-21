"""Dentro do web da plataforma de Performance, no Raio-X (21/10/2026). Raio-X das 14:55 de 21/10: o processo web da
plataforma foi de 0,8 GB às 14:36 para 3,1 GB e 0,7 GB no swap, com a máquina sem memória, e o relatório por dentro só
existia no worker. O web grava o mesmo relatório num arquivo dele (PerformancePainel, `_memoria_web_loop`), e o Raio-X o
mostra como o do worker, com o prazo e o estado próprios. Aqui os arquivos são de mentira."""
import json
import threading
from datetime import datetime

import pytest

from nexus.casca import raio_x as R


@pytest.fixture(autouse=True)
def _limpo(monkeypatch):
    for nome in ("_WORKER", "_WEB", "_MEMORIA"):
        monkeypatch.setattr(R, nome, {"thread": None, "ultimo": None, "quando": None}, raising=False)
    monkeypatch.setattr(R, "_processador", lambda janela_s=1.0: {"pct": 10, "nucleos": 4, "carga": None})
    monkeypatch.setattr(R, "_memoria_por_programa", lambda prazo_s=R.PRAZO_MEMORIA_S: None)


def _relatorio(caminho, quando, rss=3139, swap=744):
    caminho.write_text(json.dumps({"quando": quando, "pid": 5050, "rss_mb": rss, "swap_mb": swap, "parcial": False,
                                   "caches": [{"nome": "app._cache_do_web", "mb": 2100.0, "itens": 640}],
                                   "historico": [{"quando": quando, "rss_mb": rss, "swap_mb": swap,
                                                  "caches": {"app._cache_do_web": 2100.0}}]}), encoding="utf-8")


def test_a_pagina_mostra_o_web_ao_lado_do_worker(app, logado, monkeypatch, tmp_path):
    agora = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    _relatorio(tmp_path / "web.json", agora)
    _relatorio(tmp_path / "worker.json", agora, rss=2207, swap=666)
    monkeypatch.setattr(R, "RELATORIO_WEB", str(tmp_path / "web.json"))
    monkeypatch.setattr(R, "RELATORIO_WORKER", str(tmp_path / "worker.json"))
    h = logado.get("/t/base/raio-x").get_data(as_text=True)
    assert "Dentro do worker da plataforma" in h and "Dentro do web da plataforma" in h
    assert "o web ocupa 3139 MB e 744 MB no swap" in h and "o worker ocupa 2207 MB e 666 MB no swap" in h


def test_sem_o_relatorio_do_web_a_secao_nao_aparece(app, logado, monkeypatch, tmp_path):
    monkeypatch.setattr(R, "RELATORIO_WEB", str(tmp_path / "nao_existe.json"))
    monkeypatch.setattr(R, "RELATORIO_WORKER", str(tmp_path / "nao_existe_tambem.json"))
    assert "Dentro do web da plataforma" not in logado.get("/t/base/raio-x").get_data(as_text=True)


def test_o_web_parado_e_dito_pelo_nome(app, logado, monkeypatch, tmp_path):
    _relatorio(tmp_path / "web.json", "2026-01-01T00:00:00")
    monkeypatch.setattr(R, "RELATORIO_WEB", str(tmp_path / "web.json"))
    monkeypatch.setattr(R, "RELATORIO_WORKER", str(tmp_path / "nao_existe.json"))
    assert "O web não anota há" in logado.get("/t/base/raio-x").get_data(as_text=True)


def test_o_relatorio_do_web_preso_nao_prende_o_do_worker(monkeypatch):
    """No swap, até ler /dev/shm espera o disco: cada relatório tem o seu prazo e a sua leitura em andamento."""
    solta = threading.Event()

    def ler(caminho=None, agora=None):
        if caminho == R.RELATORIO_WEB:
            solta.wait(10)
            return None
        return {"quando": "15:00"}
    monkeypatch.setattr(R, "_ler_relatorio_worker", ler)
    try:
        assert R._web_plataforma(prazo_s=0.2)["atrasado"] is True
        assert R._worker_plataforma(prazo_s=2) == {"quando": "15:00"}
    finally:
        solta.set()

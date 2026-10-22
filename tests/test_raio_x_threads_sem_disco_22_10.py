"""O Raio-X não espera o disco para montar a lista de threads (22/10/2026).

Raio-X do servidor às 08:57 de 22/10: o próprio GET /t/base/raio-x ficou 1 min 15 s preso em `_threads`, com a máquina
em 3,6 GB de swap e o disco ocupado 61% do tempo. Para cada thread, o `traceback.extract_stack` lia no disco (linecache)
o código de TODAS as linhas da pilha, e o rótulo só usa o texto da linha de dentro (o "como": `sleep(`, `.execute(`).
Agora a pilha sai sem o texto (`presos.pilha`) e só a linha de dentro é lida; e a lista inteira tem o prazo de 2 s das
outras seções (`_com_prazo`): passou dele, a página mostra a última lista, com a hora dela."""
import linecache
import sys
import threading
import time
import traceback

import pytest

from nexus.casca import presos as P
from nexus.casca import raio_x as R


def _funda(n, solta):
    if n:
        return _funda(n - 1, solta)
    solta.wait(10)


@pytest.fixture
def fundas():
    solta = threading.Event()
    ts = [threading.Thread(target=_funda, args=(40, solta), name=f"funda-{i}", daemon=True) for i in range(5)]
    for t in ts:
        t.start()
    time.sleep(0.2)
    yield ts
    solta.set()
    for t in ts:
        t.join(5)


@pytest.fixture(autouse=True)
def _limpo(monkeypatch):
    for nome in ("_WORKER", "_WEB", "_MEMORIA", "_THREADS"):
        monkeypatch.setattr(R, nome, {"thread": None, "ultimo": None, "quando": None}, raising=False)


def test_a_lista_de_threads_le_so_a_linha_de_dentro_de_cada_pilha(fundas, monkeypatch):
    lidas = []
    real = linecache.getline
    monkeypatch.setattr(linecache, "getline", lambda *a, **k: lidas.append(a[:2]) or real(*a, **k))
    pedidos, outras = R._threads(None)
    minhas = [o for o in outras if o["nome"].startswith("funda-")]
    assert len(minhas) == 5 and {o["como"] for o in minhas} == {"esperando outra thread"}
    assert len(lidas) <= len(outras) + len(pedidos)                   # eram 5 × ~45 só destas cinco


def test_o_rotulo_e_o_mesmo_de_antes():
    def dentro():
        f = sys._getframe()
        return P.rotulo(P.pilha(f)), P.rotulo(traceback.extract_stack(f))
    novo, antigo = dentro()
    assert novo == antigo


def test_a_lista_de_threads_tem_prazo(app, logado, monkeypatch):
    """No swap, até andar pelas pilhas espera o disco: a página não fica presa com ele."""
    monkeypatch.setattr(R, "_processador", lambda janela_s=1.0: {"pct": 10, "nucleos": 4, "carga": None})
    monkeypatch.setattr(R, "_memoria_por_programa", lambda prazo_s=R.PRAZO_MEMORIA_S: None)
    monkeypatch.setattr(R, "_worker_plataforma", lambda prazo_s=R.PRAZO_MEMORIA_S: None)
    monkeypatch.setattr(R, "_web_plataforma", lambda prazo_s=R.PRAZO_MEMORIA_S: None)
    monkeypatch.setattr(R, "PRAZO_MEMORIA_S", 0.3)
    anterior = ([], [{"nome": "nexus-tarefa-de-ontem", "quem": "?", "onde": "", "como": "em pausa"}])
    monkeypatch.setitem(R._THREADS, "ultimo", anterior)
    monkeypatch.setitem(R._THREADS, "quando", "08:55:42")
    solta = threading.Event()
    monkeypatch.setattr(R, "_threads", lambda estado: solta.wait(10) and ([], []))
    try:
        t0 = time.monotonic()
        h = logado.get("/t/base/raio-x").get_data(as_text=True)
        assert time.monotonic() - t0 < 5
        assert "A lista de threads não respondeu" in h and "08:55:42" in h and "nexus-tarefa-de-ontem" in h
    finally:
        solta.set()


def test_a_ronda_dos_presos_tambem_nao_le_o_codigo_de_cada_linha(monkeypatch):
    """A ronda roda a cada 5 s justamente quando a máquina engasga: o mesmo cuidado."""
    monkeypatch.setattr(traceback, "extract_stack", lambda *a, **k: pytest.fail("leu a pilha com o código"))
    e = P._Estado(4, None)
    seq = e.entrar({"REQUEST_METHOD": "GET", "PATH_INFO": "/os/historico"})
    e.olhar(agora=time.monotonic() + P.LIMITE_S + 1)
    assert e.em_curso[seq].get("preso") is True

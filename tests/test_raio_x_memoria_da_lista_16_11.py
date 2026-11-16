"""O Raio-X não espera a medida da memória da lista central de OS (16/11/2026).

O caso: nos Raio-X das 15:40 e das 16:27 de 16/11/2026, logo depois de um reinício, o próprio `GET /t/base/raio-x`
aparecia entre os pedidos presos, há 41 s e há 40 s, em `os_central.py conta`: a peça "Lista central de OS" mede a memória
da lista andando por todas as OS (~0,4 s com 36 mil OS, uma vez por versão da lista, que muda a cada leitura do leitor),
dentro do pedido. Com o Nexus disputando o processador depois do reinício, os 0,4 s viravam 40 s, e a página que serve
para dizer onde está o gargalo era mais um pedido preso. Agora a medida roda numa thread à parte, com o prazo das outras
leituras lentas do Raio-X (`_com_prazo`): passou dele, a página sai com a última medida (ou sem a linha)."""
import sys
import threading
import time

import pytest

from nexus.casca import raio_x as R
from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import os_central as OC  # noqa: E402


@pytest.fixture
def lista_nova(monkeypatch):
    """A lista numa versão que a medida ainda não viu, e o guardador do Raio-X limpo."""
    monkeypatch.setitem(OC._MEMORIA, "versao", object())
    monkeypatch.setitem(OC._MEMORIA, "mb", None)
    monkeypatch.setattr(R, "_OS_MEMORIA", {"thread": None, "ultimo": None, "quando": None})


def test_a_medida_lenta_nao_segura_a_pagina(lista_nova, monkeypatch):
    entrou, soltar, vezes = threading.Event(), threading.Event(), []

    def lenta(lista=None):
        vezes.append(1)
        entrou.set()
        assert soltar.wait(20)
        return 12.5
    monkeypatch.setattr(OC, "memoria_estimada", lenta)
    try:
        t0 = time.monotonic()
        e = R._estado_da_lista_de_os(OC, prazo_s=0.3)
        assert time.monotonic() - t0 < 3, "o Raio-X esperou a medida da memória da lista"
        assert entrou.is_set() and e["memoria_mb"] is None and "n" in e        # o resto do estado vem na hora
        # a página aberta de novo com a medida ainda andando não abre outra
        e = R._estado_da_lista_de_os(OC, prazo_s=0.3)
        assert len(vezes) == 1 and e["memoria_mb"] is None
    finally:
        soltar.set()
    R._OS_MEMORIA["thread"].join(10)
    # terminou: a próxima página mostra a medida (a lista não mudou de versão: não mede de novo)
    assert R._estado_da_lista_de_os(OC, prazo_s=5)["memoria_mb"] == 12.5
    assert len(vezes) == 1


def test_com_a_medida_presa_a_pagina_mostra_a_ultima(lista_nova, monkeypatch):
    monkeypatch.setattr(OC, "memoria_estimada", lambda lista=None: 20.0)
    assert R._estado_da_lista_de_os(OC, prazo_s=5)["memoria_mb"] == 20.0
    # a lista ganhou versão nova e a medida dela demora: fica a de antes
    monkeypatch.setitem(OC._MEMORIA, "versao", object())
    soltar = threading.Event()
    monkeypatch.setattr(OC, "memoria_estimada", lambda lista=None: soltar.wait(20) and 33.0)
    try:
        assert R._estado_da_lista_de_os(OC, prazo_s=0.3)["memoria_mb"] == 20.0
    finally:
        soltar.set()
    R._OS_MEMORIA["thread"].join(10)
    assert R._estado_da_lista_de_os(OC, prazo_s=5)["memoria_mb"] == 33.0


def test_a_peca_do_raio_x_usa_a_medida_com_prazo():
    """A peça "Lista central de OS" não chama mais o `estado(medir_memoria=True)` dentro do pedido."""
    import inspect
    fonte = inspect.getsource(R._secao_canto_central) if hasattr(R, "_secao_canto_central") else ""
    fonte = fonte or inspect.getsource(R)
    trecho = fonte.split('"os": _peca("os_central"', 1)[1].split("\n", 1)[0]
    assert "_estado_da_lista_de_os" in trecho and "medir_memoria=True" not in trecho

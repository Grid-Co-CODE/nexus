"""O Quadro da equipe da Engenharia pronto enquanto alguém o usa (Levi, 09/10/2026: "talvez um carregamento periódico que
carregue em segundo plano e deixe todos prontos").

Nenhum teste fala com o Fracttal: a releitura é trocada por um marcador, e a volta de cada minuto (`os_equipe._tique`)
é chamada com o relógio que o teste quer."""
import threading
import time

import pytest

import nexus.engenharia as engenharia
from nexus.engenharia import os_equipe as E

PEDIDOS_POR_LEITURA = 8          # medido em 06/10 (os 6 da equipe somavam 55 linhas: ~8 pedidos)


@pytest.fixture(autouse=True)
def _limpo():
    E.limpar()
    yield
    E.limpar()


@pytest.fixture
def pedidos(monkeypatch):
    feitos = []
    monkeypatch.setattr(E, "pedir_releitura", lambda app=None, esperar=False, forcar=False: feitos.append(forcar))
    return feitos


def test_rele_por_tras_quando_alguem_usa_e_a_copia_passou_dos_5_min(pedidos):
    agora = time.time()
    E._EST.update(usado=agora - 600, ts=agora - E.VALIDADE_S)
    assert E._tique(object(), agora) is True and pedidos == [True]


def test_copia_nova_nao_rele(pedidos):
    agora = time.time()
    E._EST.update(usado=agora - 60, ts=agora - 30)
    assert E._tique(object(), agora) is False and pedidos == []


def test_ninguem_em_2_horas_para(pedidos):
    agora = time.time()
    E._EST.update(usado=agora - E.USO_S - 1, ts=agora - 3600)
    assert E._tique(object(), agora) is False and pedidos == []


def test_quadro_nunca_aberto_nao_le(pedidos):
    assert E._tique(object()) is False and pedidos == []


def test_a_cada_5_minutos_e_para_2_horas_depois_da_ultima_visita(monkeypatch):
    """4 h de voltas, uma por minuto, depois de UMA visita: relê a cada 5 min por 2 h e para. Na cota: ~1,6 pedido
    por minuto, menos de 1% dos 200/min da empresa."""
    t0, relogio, leituras = 1_000_000.0, [0.0], []

    def reler(app=None, esperar=False, forcar=False):
        leituras.append(relogio[0])
        E._EST["ts"] = relogio[0]                          # a leitura termina na hora
    monkeypatch.setattr(E, "pedir_releitura", reler)
    E._EST.update(usado=t0, ts=t0)                         # a pessoa abriu agora, com a cópia nova
    for minuto in range(1, 4 * 60):
        relogio[0] = t0 + minuto * 60
        E._tique(object(), relogio[0])
    assert leituras and max(leituras) <= t0 + E.USO_S
    assert {b - a for a, b in zip(leituras, leituras[1:])} == {E.VALIDADE_S}
    por_minuto = len(leituras) * PEDIDOS_POR_LEITURA / (E.USO_S / 60)
    assert por_minuto < 0.01 * 200


def test_abrir_a_tela_marca_o_uso(logado, monkeypatch):
    monkeypatch.setattr(E, "pedir_releitura", lambda app=None, esperar=False, forcar=False: None)
    monkeypatch.setattr(E, "dados", lambda: {"os": [], "equipe": [], "faltam": [], "lido": 1.0, "lendo": False, "erro": ""})
    antes = time.time()
    logado.get("/t/engenharia/equipe")
    assert E._EST["usado"] >= antes


def test_instalar_liga_o_quente_sempre_e_a_leitura_da_subida_so_sem_a_chave(monkeypatch):
    """O servidor (sem a chave) lê o quadro ao subir, depois das OS de falha; o PC (NEXUS_CAMPO_AQUECER=0) não lê nada
    do Fracttal ao subir. O quadro pronto enquanto alguém usa liga nas duas: só lê com alguém usando."""
    ligados, timers = [], []
    monkeypatch.setattr(E, "manter_quente", lambda app: ligados.append("quente"))

    class _Timer:
        def __init__(self, segundos, fn):
            timers.append(segundos)

        def start(self):
            pass
    monkeypatch.setattr(threading, "Timer", _Timer)

    class _App:
        def __init__(self, config):
            self.config = config
    engenharia.instalar(_App({}))
    assert ligados == ["quente"] and timers == [150, 210]
    ligados.clear()
    timers.clear()
    engenharia.instalar(_App({"NEXUS_CAMPO_AQUECER": "0"}))
    assert ligados == ["quente"] and timers == []

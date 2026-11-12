"""Torre COS: a leitura do Andamento que não faz a tela esperar (checkup do COS, 12/11/2026; nexus/cos/andamento.py,
`_com_copia`). Fora dos testes de tela (TESTING), a cópia vencida há pouco é servida na hora e renovada por trás; a mesma
leitura no ar vira um pedido só; e a primeira leitura fria de um cliente chama a dos outros em paralelo. Nada vai à rede: o
`_pedir` é trocado por um falso que conta os pedidos e demora o que o teste manda."""
import threading
import time

import pytest

from nexus.cos import andamento as AND

CLIENTES = ["Cliente A", "Cliente B", "Cliente C", "Cliente D"]
DEMORA = 0.3


def _foto():
    return {"versao": 1, "usinas": [], "eventos": [], "placar": {}, "problemas": [], "fotografias": []}


@pytest.fixture
def falso(monkeypatch):
    pedidos, trava = [], threading.Lock()

    def _pedir(f, caminho, timeout=None):
        with trava:
            pedidos.append(caminho)
        if caminho == "/api/nexus/clientes":
            return {"clientes": CLIENTES}
        time.sleep(DEMORA)
        if "/ocorrencias" in caminho:
            return {"versao": 1, "ocorrencias": [], "envio_ao_cliente": {}}
        return _foto()
    monkeypatch.setattr(AND, "_pedir", _pedir)
    AND.limpar_cache()
    yield pedidos
    AND.limpar_cache()


# fora dos testes de tela: sem TESTING, a leitura de trás vale
CFG = {"NEXUS_COS_ANDAMENTO_URL": "http://andamento:3002", "NEXUS_COS_ANDAMENTO_CHAVE": "chave-de-teste"}
CFG_TESTE = dict(CFG, TESTING=True)


def _envelhecer(segundos):
    with AND._trava:
        for k, v in list(AND._cache.items()):
            AND._cache[k] = (v[0] - segundos, v[1], v[2])


def _esperar_por_tras():
    for _ in range(100):
        if not AND._voando and not [t for t in threading.enumerate() if t.name.startswith("cos-")]:
            return
        time.sleep(0.02)


def test_a_copia_vencida_ha_pouco_vem_na_hora_e_renova_por_tras(falso):
    AND.ler(CFG, "Cliente A")
    _esperar_por_tras()
    _envelhecer(AND.TTL_S + 5)
    falso.clear()
    a = time.perf_counter()
    r = AND.ler(CFG, "Cliente A")
    assert time.perf_counter() - a < DEMORA / 3          # não esperou a Ronda COS
    assert r.dados and not r.velha and not r.erro
    _esperar_por_tras()
    assert [p for p in falso if "Cliente" in p] == ["/api/nexus/Cliente%20A"]   # e a nova saiu por trás
    assert AND.ler(CFG, "Cliente A").lido_em > r.lido_em


def test_a_copia_velha_demais_faz_esperar(falso):
    AND.ler(CFG, "Cliente A")
    _esperar_por_tras()
    _envelhecer(AND.COPIA_MAX_S + 1)
    a = time.perf_counter()
    AND.ler(CFG, "Cliente A")
    assert time.perf_counter() - a >= DEMORA * 0.9


def test_a_mesma_leitura_no_ar_vira_um_pedido_so(falso):
    th = [threading.Thread(target=lambda: AND.ler(CFG, "Cliente A")) for _ in range(6)]
    [t.start() for t in th]
    [t.join() for t in th]
    _esperar_por_tras()
    assert falso.count("/api/nexus/Cliente%20A") == 1


def test_a_fila_de_clientes_espera_a_mais_lenta_e_nao_a_soma(falso):
    a = time.perf_counter()
    lidos = [AND.ler(CFG, c) for c in CLIENTES]           # como a Mesa e a Passagem de turno leem: um por um
    gasto = time.perf_counter() - a
    assert all(x.dados for x in lidos)
    assert gasto < DEMORA * len(CLIENTES) * 0.75           # em fila seria DEMORA × 4
    _esperar_por_tras()
    assert sum(1 for p in falso if p.startswith("/api/nexus/Cliente")) == len(CLIENTES)   # nenhum pedido em dobro


def test_a_falha_da_leitura_de_tras_aparece_na_tela_sem_esconder_a_copia(falso, monkeypatch):
    AND.ler(CFG, "Cliente A")
    _esperar_por_tras()
    _envelhecer(AND.TTL_S + 5)

    def caiu(f, caminho, timeout=None):
        raise AND.FonteErro("o Andamento não respondeu (TimeoutError)")
    monkeypatch.setattr(AND, "_pedir", caiu)
    AND.ler(CFG, "Cliente A")                               # serve a cópia e tenta por trás
    _esperar_por_tras()
    r = AND.ler(CFG, "Cliente A")
    assert r.dados and r.velha and "não respondeu" in r.erro


def test_nos_testes_de_tela_tudo_segue_sincrono(falso):
    AND.ler(CFG_TESTE, "Cliente A")
    _envelhecer(AND.TTL_S + 5)
    falso.clear()
    a = time.perf_counter()
    AND.ler(CFG_TESTE, "Cliente A")
    assert time.perf_counter() - a >= DEMORA * 0.9          # esperou: sem thread, determinístico
    assert not [t for t in threading.enumerate() if t.name.startswith("cos-")]

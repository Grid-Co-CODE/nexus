"""O que o Nexus liga ao subir no Campo (`nexus.campo.instalar`).

Levi, 09/10/2026: "quando clico em Central de atenção ... a hora fica praticamente a hora que cliquei". A pré-carga das
telas pelo banco (`visao.manter_quente`) vinha junto com as leituras do Fracttal sob a mesma chave, e o PC sobe com
NEXUS_CAMPO_AQUECER=0 para não gastar a cota do Fracttal em dobro com o servidor: ficava sem as duas. Agora a pré-carga
pelo banco liga sempre, e a chave desliga só o que vai ao Fracttal. Nenhum teste fala com a rede: os temporizadores são
anotados, e as funções que eles chamariam, trocadas por marcadores.
"""
import pytest

import nexus.campo as campo
from nexus.campo import aprovacao, ronda_checklist, tabelas, visao


class _App:
    def __init__(self, config):
        self.config = config


@pytest.fixture
def chamadas(monkeypatch):
    """Roda `instalar` e devolve o que os temporizadores teriam chamado, sem esperar e sem rede."""
    feitas = []
    monkeypatch.setattr(tabelas, "usar_fornecedor", lambda f: None)       # não troca a fonte dos outros testes
    monkeypatch.setattr(visao, "manter_quente", lambda app: feitas.append("banco: telas do Campo"))
    monkeypatch.setattr(aprovacao, "aquecer", lambda app: feitas.append("Fracttal: fila da Aprovação"))
    monkeypatch.setattr(ronda_checklist, "pedir_releitura", lambda app: feitas.append("Fracttal: rondas aprovadas"))

    class _Timer:
        def __init__(self, segundos, fn):
            self.fn = fn

        def start(self):
            self.fn()

    import threading
    monkeypatch.setattr(threading, "Timer", _Timer)

    def rodar(config):
        feitas.clear()
        campo.instalar(_App(config))
        return list(feitas)
    return rodar


def test_sem_a_chave_liga_tudo(chamadas):
    """O servidor: a T.I. não põe nada no .env e sobe com a pré-carga pelo banco e as leituras do Fracttal."""
    assert chamadas({}) == ["banco: telas do Campo", "Fracttal: fila da Aprovação", "Fracttal: rondas aprovadas"]


def test_chave_em_zero_desliga_so_o_fracttal(chamadas):
    """O PC (NEXUS_CAMPO_AQUECER=0): sem leitura do Fracttal ao subir, mas as telas do Campo saem prontas do banco."""
    assert chamadas({"NEXUS_CAMPO_AQUECER": "0"}) == ["banco: telas do Campo"]

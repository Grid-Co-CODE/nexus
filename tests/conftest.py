"""Fixtures comuns: um app com configuração de teste, sem ler o .env real da máquina, e nenhum pedido ao Fracttal."""
import sys
from urllib.parse import urlsplit

import pytest
import requests

from nexus import create_app

SENHA_TESTE = "senha-de-teste"
BLOQUEIO_DO_FRACTTAL = "rede do Fracttal bloqueada nos testes"


@pytest.fixture(autouse=True)
def _sem_a_rede_do_fracttal(monkeypatch):
    """Nenhum teste fala com o Fracttal de verdade (31/10/2026). Numa outra tarefa, 4 testes antigos mandaram leituras de
    VERDADE ao Fracttal com um JWT falso: deu 401 e nada foi gravado, mas a cota de 200 pedidos por minuto é da empresa toda
    e teste não vai à rede. O pedido a um host que termina em `fracttal.com` levanta `ConnectionError` no adaptador do
    requests (`HTTPAdapter.send`), ABAIXO do `Session.send` que os testes do contador e do porteiro trocam: o adaptador de
    mentira de cada teste (`sessao_real_sem_rede`, o `HTTPAdapter.send` trocado no próprio teste, que vence este) segue
    valendo, e o resto (a própria máquina, o banco de mentira) passa como sempre. A suíte não usa `responses` nem
    `requests_mock` (31/10/2026); quem vier a usar troca o adaptador por cima deste, e o bloqueio volta no fim."""
    enviar = requests.adapters.HTTPAdapter.send

    def send(self, request, **kwargs):
        if (urlsplit(request.url).hostname or "").lower().endswith("fracttal.com"):
            raise requests.ConnectionError(BLOQUEIO_DO_FRACTTAL, request=request)
        return enviar(self, request, **kwargs)
    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", send)


@pytest.fixture
def app():
    app = create_app({
        "NEXUS_SECRET_KEY": "chave-de-teste",
        "NEXUS_SENHA_ADMIN": SENHA_TESTE,
    })
    app.config["TESTING"] = True
    app.config["SESSION_COOKIE_SECURE"] = False  # o cliente de teste fala http
    return app


@pytest.fixture
def cliente(app):
    return app.test_client()


@pytest.fixture
def logado(cliente):
    resp = cliente.post("/entrar", data={"senha": SENHA_TESTE})
    assert resp.status_code == 302
    return cliente


@pytest.fixture(autouse=True)
def _catalogo_de_ativos_isolado():
    """O catálogo de ativos do OS Creator (`os_creator/ativos_central.py`) é UM por processo: a pasta onde ele grava a cópia em
    disco, a função do banco e o que ele guarda valem para o processo inteiro. Um teste que cria o clone "fora dos testes"
    (`TESTING` desligado, como o do token do banco) aponta a pasta para a do usuário da máquina (%APPDATA%), e o seguinte, sem
    saber, migraria o arquivo de lá e gravaria nela. Cada teste começa e termina sem catálogo, sem pasta e sem banco. Só age
    se o módulo já foi importado (o clone do OS Creator no `sys.path`): os demais testes não pagam nada. A lista central de
    OS (`os_creator/os_central.py`, etapa 3) é do mesmo feitio (uma por processo, com a pasta dela) e é limpa junto; a
    gravação em disco que ficou agendada termina antes (ela roda numa thread à parte)."""
    def limpar():
        mod = sys.modules.get("ativos_central")
        if mod is not None:
            mod.reiniciar()
        mod = sys.modules.get("os_central")
        if mod is not None:
            mod.esperar_gravacao(5)
            mod.reiniciar()
        mod = sys.modules.get("os_leitor")                 # e o leitor dela, que liga a entrega das abertas no tarefas_os
        if mod is not None:
            mod.reiniciar()
        mod = sys.modules.get("catalogos")                 # e os catálogos pequenos (etapa 4): o pessoal de mentira de um
        if mod is not None:                                # teste não pode aparecer no seguinte, nem a pasta de um em outro
                                                           # (o `reiniciar` limpa junto os planos e o leitor das pessoas)
            mod.reiniciar()
        # e as listas do Histórico guardadas por visão (`os_web/historico_store.py`, uma por processo). Caso (31/10/2026): os
        # testes dos catálogos abrem o Histórico e deixavam guardada a lista "Todos" do Fracttal de mentira deles (vazia,
        # total 0). No teste seguinte cada pessoa conferia o total dela (5) contra essa lista, não batia, e cada uma buscava a
        # sua (`test_a_lista_de_todos_e_uma_so_para_quem_ve_o_mesmo`, que só quebrava na suíte, com os catálogos antes)
        mod = sys.modules.get("os_web.historico_store")
        if mod is not None:
            mod.limpar()
    limpar()
    yield
    limpar()

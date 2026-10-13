"""A subida sem rajada no Fracttal (13/10/2026). Com o deploy automático, cada push reinicia o servidor, e a subida relia
a fila inteira da Aprovação em 6 de uma vez (no teto de 4 por segundo: acima dos 200 por minuto da empresa) e as OS de
falha. Agora a fila sai paciente (2 de uma vez, 1 min de pausa depois de uma recusa), a última fila boa fica em disco e
o reinício só relê o que venceu. Nada vai ao Fracttal: a varredura é dublada."""
import json
import time

import pytest

from nexus.campo import aprovacao, regras_app
from nexus.engenharia import os_falhas


class _NaHora:
    def __init__(self, target, **k):
        self.target = target

    def start(self):
        self.target()


@pytest.fixture
def fila(app, tmp_path, monkeypatch):
    app.config["NEXUS_DADOS"] = str(tmp_path)
    aprovacao.limpar()
    chamadas = []

    def varredura(status, sort, cap, **k):
        chamadas.append(k)
        return [{"id_work_order": 1, "id_work_orders_tasks": 11}, {"id_work_order": 2, "id_work_orders_tasks": 22}]
    monkeypatch.setattr(regras_app, "_fx_wo_paralelo", varredura)
    monkeypatch.setattr(aprovacao, "fila_toda", lambda params, usinas=None: None)    # a conta da tela não importa aqui
    monkeypatch.setattr(aprovacao.threading, "Thread", _NaHora)
    yield chamadas
    aprovacao.limpar()


def test_a_releitura_sai_paciente_e_grava_a_fila_no_disco(app, fila, tmp_path):
    aprovacao._reler(app)
    assert fila == [{"paciente": True}]
    arq = tmp_path / "campo" / "fila_aprovacao.json.gz"
    assert arq.exists()
    t = regras_app._FILA_CACHE["t"]
    aprovacao.limpar()                                     # o reinício: a memória vai, o disco fica
    assert aprovacao.carregar_do_disco(app) is True
    assert regras_app._FILA_CACHE["t"] == t and len(regras_app._FILA_CACHE["linhas"]) == 2
    assert aprovacao.carregar_do_disco(app) is False       # com fila na memória, o disco não a troca


def test_o_reinicio_com_a_fila_do_disco_recente_nao_rele(app, fila):
    aprovacao._reler(app)
    aprovacao.limpar()
    fila.clear()
    aprovacao.aquecer(app)                                 # a do disco tem segundos: nada de Fracttal
    assert fila == [] and regras_app._FILA_CACHE["linhas"]


def test_o_reinicio_com_a_fila_do_disco_velha_rele_e_mostra_a_velha_enquanto_isso(app, fila, monkeypatch):
    aprovacao._reler(app)
    with app.app_context():
        regras_app._FILA_CACHE["t"] = time.time() - 3600
        aprovacao._gravar_no_disco()
    aprovacao.limpar()
    fila.clear()
    vista = []
    monkeypatch.setattr(aprovacao, "_reler", lambda a: vista.append(regras_app._FILA_CACHE["t"]))
    aprovacao.aquecer(app)
    assert len(vista) == 1 and time.time() - vista[0] > 3000      # releu, com a fila velha já na memória


def test_a_os_aprovada_sai_tambem_do_disco(app, fila):
    aprovacao._reler(app)
    with app.test_request_context():
        assert aprovacao.tirar_da_fila(1) == 1
    aprovacao.limpar()
    aprovacao.carregar_do_disco(app)
    assert [w["id_work_order"] for w in regras_app._FILA_CACHE["linhas"]] == [2]


def test_teste_sem_pasta_nao_grava(app, monkeypatch):
    app.config.pop("NEXUS_DADOS", None)
    aprovacao.limpar()
    with app.app_context():
        regras_app._FILA_CACHE.update(t=time.time(), linhas=[{"id_work_order": 1}])
        aprovacao._gravar_no_disco()                       # a pasta_dados recusa: nada vai para a dados/ de verdade
    assert aprovacao.carregar_do_disco(app) is False
    aprovacao.limpar()


def test_as_os_de_falha_nao_releem_no_reinicio_se_foram_lidas_ha_pouco(app, tmp_path, monkeypatch):
    app.config["NEXUS_DADOS"] = str(tmp_path)
    (tmp_path / "engenharia").mkdir()
    completo = {t: "2026-10-13" for t in os_falhas.TIPOS}
    arq = tmp_path / "engenharia" / "os_falhas.json"
    lidas = []
    monkeypatch.setattr(os_falhas, "_reler", lambda: lidas.append(1))
    try:
        arq.write_text(json.dumps({"concluidas": {}, "vivas": {}, "ate": completo, "vivas_em": time.time() - 60}))
        os_falhas.limpar()
        os_falhas.pedir_releitura(app)
        assert lidas == []                                 # lidas há 1 min (o deploy anterior): não relê
        arq.write_text(json.dumps({"concluidas": {}, "vivas": {}, "ate": completo, "vivas_em": time.time() - 7200}))
        os_falhas.limpar()
        os_falhas.pedir_releitura(app)
        assert lidas == [1]                                # 2 h: relê
    finally:
        os_falhas.limpar()

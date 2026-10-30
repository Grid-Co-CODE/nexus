"""O tempo da tarefa na Clonagem e o tempo da OS que a Fila do PCM cria (o time do PCM, 30/10/2026).

- Clonar: "quando clonamos uma OS ela está vindo com horário padrão de 10minutos por tarefa... gostaria que o tempo que
  viesse fosse o cadastrado do plano, que seria atualizado no 'Atualizar todas do modelo'". O clone nascia com o
  `duration: 600` do `create_os_rpc`. Agora cada tarefa leva o tempo da tarefa de origem, e o "Atualizar do modelo" traz o
  tempo cadastrado no modelo, junto com as subtarefas.
- Fila: "nas SSs o tempo que aparece na OS do Fracttal permanece 10 min, porém nas tarefas aparece o tempo que foi
  solicitado". A tarefa já levava o tempo da decisão (21/10/2026), mas a OS nascia do `_work_order_insert` com o
  `duration=600` fixo. Agora a OS leva a soma do tempo das tarefas.

O Fracttal é de mentira; nada vai à rede."""
import sys

import pytest

from nexus.torres.oscreator import ponte

pytest.importorskip("PyQt6")
if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
from os_web import clonar_web  # noqa: E402

WEB = ponte.RAIZ_CLONE + "/os_web"


def test_a_os_de_origem_traz_o_tempo_de_cada_tarefa(monkeypatch):
    def rpc(metodo, params, timeout=45):
        if metodo == api.RPC_WO_TASKS:
            return {"data": [{"id": 1, "wo_folio": 900, "code_item": "TST-INV1", "items_description": "Inversor 1.1",
                              "tasks_description": "Limpeza", "duration": 5400},
                             {"id": 2, "wo_folio": 900, "code_item": "TST-INV2", "items_description": "Inversor 1.2",
                              "tasks_description": "Limpeza"}]}
        return {"data": []}
    monkeypatch.setattr(api, "_rpc_call", rpc)
    monkeypatch.setattr(api, "_asset_by_code", lambda c: {"id": 5, "code": c})
    d = api.get_os_para_clonar(77)
    assert [t["duracao"] for t in d["tarefas"]] == [5400, None]


def test_o_modelo_traz_o_tempo_cadastrado(monkeypatch):
    eventos = [{"tasks_description": "Limpeza", "id_task": 9, "duration": 7200}]

    def rpc(metodo, params, timeout=45):
        if metodo == api.RPC_TASK_EVENTS:
            return {"data": eventos}
        if metodo == api.RPC_TASK_TEMPLATE_ITEMS:
            return {"data": [{"description": "Foto do antes", "order_number": 1}]}
        raise AssertionError("pedido inesperado: " + metodo)
    monkeypatch.setattr(api, "_rpc_call", rpc)
    ativo = {"id": 5, "code": "TST-INV1", "id_group_task": 1}
    assert api.get_template_subtarefas(ativo, "Limpeza")["duracao"] == 7200
    assert api.atualizar_modelos_subtarefas([{"asset": ativo, "descricao": "Limpeza"}])[0]["duracao"] == 7200
    # sem o tempo no evento: o do plano (tasks_details), e não o 900 que o get_plan_details põe quando falta
    eventos[0].pop("duration")
    monkeypatch.setattr(api, "get_plan_details", lambda idt, idi: {"duration": 900, "raw": {"duration": 3600}})
    assert api.get_template_subtarefas(ativo, "Limpeza")["duracao"] == 3600
    monkeypatch.setattr(api, "get_plan_details", lambda idt, idi: {"duration": 900, "raw": {}})
    assert api.get_template_subtarefas(ativo, "Limpeza")["duracao"] is None


def test_a_tela_manda_o_tempo_e_o_servidor_confere():
    prontas, erro = clonar_web.preparar_tarefas([{"asset": {"id": 5}, "duracao": 5400}, {"asset": {"id": 6}, "duracao": "abc"},
                                                 {"asset": {"id": 7}, "duracao": 0}, {"asset": {"id": 8}, "duracao": True}], {})
    assert not erro and [t.get("duracao") for t in prontas] == [5400, None, None, None]


@pytest.fixture
def fracttal(monkeypatch):
    criadas, wo = [], {}
    monkeypatch.setattr(api, "create_os_rpc", lambda asset, desc, tipo_tarefa, subs, **k: criadas.append(k.get("duracao"))
                        or {"id_task": 100 + len(criadas)})
    monkeypatch.setattr(api, "_classif_ids", lambda *a: {})
    monkeypatch.setattr(api, "_kanban_records", lambda ids: {i: {"id": i} for i in ids})

    def inserir(recs, idr, nome="", duration=600, **k):
        wo["duration"] = duration
        return {"id_work_order": 9, "wo_folio": 1234}
    monkeypatch.setattr(api, "_work_order_insert", inserir)
    monkeypatch.setattr(api, "apply_labels", lambda *a: None)
    return criadas, wo


def test_o_clone_cria_cada_tarefa_e_a_os_com_o_tempo(fracttal):
    criadas, wo = fracttal
    api.clonar_os([{"asset": {"id": 5}, "descricao": "A", "duracao": 5400}, {"asset": {"id": 6}, "descricao": "B"}], 1, "Ana")
    assert criadas == [5400, None]
    assert wo["duration"] == 5400 + api.DURACAO_OS_AVULSA               # a OS é a soma das tarefas


def test_a_os_da_fila_leva_o_tempo_da_decisao(fracttal, monkeypatch):
    _criadas, wo = fracttal
    monkeypatch.setattr(api, "_solicitacao_row", lambda idc: {})
    monkeypatch.setattr(api, "_tarefa_da_solicitacao", lambda idc: None)
    api.aprovar_solicitacao({"id": 11, "code": "TST-INV11"}, "T", [], 5001, 1, "Ana", duracao=5400)
    assert wo["duration"] == 5400
    # a retomada (a tarefa já existia de uma tentativa anterior): a OS leva o tempo da tarefa que ficou
    monkeypatch.setattr(api, "_tarefa_da_solicitacao", lambda idc: {"id": 7, "duration": 3600})
    api.aprovar_solicitacao({"id": 11, "code": "TST-INV11"}, "T", [], 5001, 1, "Ana")
    assert wo["duration"] == 3600


def test_a_tela_do_clone_mostra_e_aplica_o_tempo():
    js = open(WEB + "/static/clonar.js", encoding="utf-8").read()
    html = open(WEB + "/templates/clonar.html", encoding="utf-8").read()
    assert ">Tempo<" in html and 'colspan="5"' in html
    assert "t.duracao = j.duracao" in js and "t.duracao = res.duracao" in js and "hhmm(" in js


# A OS que JUNTA tarefas criadas do zero (o PCM, 30/10/2026: "o clonador deu certo tanto na tarefa como na OS ... agora
# criando do zero o tempo na OS continua 10 min igual na Fila, só na tarefa que o tempo é o que a gente colocou"): a
# Clonagem de planos do PCM, a OS agrupada do Criar OS do zero e a agrupada da Performance também somam as tarefas.

class _Resposta:
    status_code, text = 200, ""

    def __init__(self, id_task):
        self.id_task = id_task

    def json(self):
        return [{"result": {"success": True, "data": {"id_task": self.id_task}}}]


@pytest.fixture
def insert_de_mentira(monkeypatch):
    """O POST do Fracttal devolve a tarefa nova; guarda o tempo de cada tarefa e o da OS."""
    tarefas, wo = [], {}

    def post(url, headers=None, json=None, timeout=None):
        tarefas.append(json[0]["params"]["duration"])
        return _Resposta(100 + len(tarefas))
    monkeypatch.setattr(api.requests, "post", post)
    monkeypatch.setattr(api, "_rpc_headers", lambda: {})
    monkeypatch.setattr(api, "_kanban_records", lambda ids: {i: {"id_task": i} for i in ids})

    def inserir(recs, idr, nome="", duration=600, **k):
        wo["duration"] = duration
        return {"id_work_order": 9, "wo_folio": 1234}
    monkeypatch.setattr(api, "_work_order_insert", inserir)
    monkeypatch.setattr(api, "apply_labels", lambda *a: None)
    return tarefas, wo


ATIVO = {"id": 5, "code": "TST-INV1", "description": "Inversor 1.1", "id_type_item": 1}


def test_a_tarefa_devolve_o_tempo_com_que_nasceu(insert_de_mentira):
    assert api.create_os_rpc(dict(ATIVO), "T", "Corretiva", [], duracao=5400)["duracao"] == 5400
    assert api.create_os_rpc(dict(ATIVO), "T", "Corretiva", [])["duracao"] == api.DURACAO_OS_AVULSA
    plano = {"id_task": 9, "description": "Limpeza", "subtasks": [{"description": "a"}], "duration": 3600}
    assert api.create_planned_os(dict(ATIVO), plano, to_work_order=False)["duracao"] == 3600
    assert api.create_planned_os(dict(ATIVO), plano, to_work_order=False, duracao=1800)["duracao"] == 1800


def test_a_os_do_pcm_soma_o_tempo_das_linhas(insert_de_mentira, monkeypatch):
    tarefas, wo = insert_de_mentira
    monkeypatch.setattr(api, "get_plan_details", lambda idt, idi: {"id_task": 9, "description": "Limpeza",
                                                                   "subtasks": [{"description": "a"}], "duration": 3600})
    r = api.create_planned_os_multi([{"asset": dict(ATIVO), "id_task": 9, "duracao": 5400},
                                     {"asset": dict(ATIVO, id=6), "id_task": 9}], 1, "Ana")
    assert r["ok"] and tarefas == [5400, 3600]
    assert wo["duration"] == 5400 + 3600                          # antes: 600
    api.create_planned_os_one_wo([dict(ATIVO), dict(ATIVO, id=6)], {"id_task": 9, "description": "Limpeza",
                                 "subtasks": [{"description": "a"}], "duration": 1200}, 1, "Ana")
    assert wo["duration"] == 2400


def test_a_os_agrupada_do_zero_soma_as_tarefas(insert_de_mentira):
    tarefas, wo = insert_de_mentira
    r = api.create_work_orders_agrupada([dict(ATIVO), dict(ATIVO, id=6)], "T", "Corretiva", [],
                                        id_responsible=1, responsible_name="Ana")
    assert r["ok"] and len(tarefas) == 2
    assert wo["duration"] == 2 * api.DURACAO_OS_AVULSA


def test_a_agrupada_da_performance_soma_o_tempo_dos_planos(insert_de_mentira, monkeypatch):
    _tarefas, wo = insert_de_mentira
    monkeypatch.setattr(api, "get_plan_details", lambda idt, idi: {"id_task": 9, "description": "Inspeção",
                                                                   "duration": 2700, "subtasks": [{"description": "a"}]})
    monkeypatch.setattr(api, "_label_performance_id", lambda: None)
    monkeypatch.setattr(api, "nascer_ticket", lambda *a, **k: {}, raising=False)
    itens = [{"asset": dict(ATIVO), "plano_id_task": 9}, {"asset": dict(ATIVO, id=6), "plano_id_task": 9}]
    api.create_performance_os_agrupada(itens, id_responsible=1, responsible_name="Ana")
    assert wo["duration"] == 2 * 2700

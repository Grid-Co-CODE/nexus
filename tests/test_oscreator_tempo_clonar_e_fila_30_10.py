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

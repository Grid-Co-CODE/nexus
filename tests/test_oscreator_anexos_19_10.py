"""Os anexos do card da OS (19/10/2026; Levi: "resolva!"). Dois achados do mapa dos pedidos ao Fracttal:

- a lista de tarefas da OS (`tasks.work_orders_tasks_new_list`) traz o id da tarefa DESTA OS no `id`; o `id_task` é o
  MODELO da tarefa (conferido ao vivo: ver `api.id_tarefa_da_os` e o README da torre). O `_ids_tarefas_da_os` caía no
  `id_task`: a tarefa sem foto não tinha os anexos lidos, e o número do modelo podia cair na tarefa antiga de outra OS;
- a contagem de anexos, ~1 s depois do card, relia as tarefas e as subtarefas que o card tinha acabado de ler.
Nada sai da máquina: o Fracttal é de mentira. Números de mentira: o repositório é público."""
import sys

import pytest

from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone

WID, TAREFA, MODELO = 9301, 7702, 5501


class _Fracttal:
    def __init__(self):
        self.n = {}
        self.arquivos = {TAREFA: [{"value": ".ot/%d/laudo.pdf" % WID, "description": ""}],
                         # o número do modelo também é o de uma tarefa antiga de OUTRA OS
                         MODELO: [{"value": ".ot/999/de-outra-os.pdf", "description": ""}]}

    def rpc(self, metodo, params, timeout=45):
        self.n[metodo] = self.n.get(metodo, 0) + 1
        if metodo == api.RPC_WO_TASKS:
            return {"data": [{"id": TAREFA, "id_task": MODELO, "id_work_order": WID, "description": "Inspeção",
                              "tasks_types_main_description": "Corretiva"}]}
        if metodo == api.RPC_WO_FORMIT:
            return {"data": [{"id_work_order_task": TAREFA, "id_work_orders_tasks_form_items": 9, "description": "Foto",
                              "num_attachments": 0}]}
        if metodo == api.RPC_WO_FILES:
            return {"data": self.arquivos.get(params.get("id_work_order_task"), [])}
        return {"data": []}


@pytest.fixture
def fr(monkeypatch):
    f = _Fracttal()
    monkeypatch.setattr(api, "_rpc_call", f.rpc)
    api.esquecer_os()
    yield f
    api.esquecer_os()


def test_os_anexos_sao_da_tarefa_desta_os_e_nao_do_modelo(fr):
    assert api._ids_tarefas_da_os(WID) == [TAREFA]
    assert [a["nome"] for a in api.get_os_anexos(WID)] == ["laudo.pdf"]          # e não o "de-outra-os.pdf"


def test_a_contagem_usa_o_que_o_card_acabou_de_ler(fr):
    api.get_os_detalhes(WID)                                                  # o card
    api.get_os_anexos(WID)                                                    # a contagem, logo depois
    api.get_os_subtarefa_anexos(WID)
    assert fr.n[api.RPC_WO_TASKS] == 1 and fr.n[api.RPC_WO_FORMIT] == 1          # eram 2 de cada


def test_o_card_sempre_le_na_hora(fr):
    api.get_os_detalhes(WID)
    api.get_os_detalhes(WID)                                                  # reabriu: lê de novo
    assert fr.n[api.RPC_WO_TASKS] == 2 and fr.n[api.RPC_WO_FORMIT] == 2


def test_gravar_na_os_tira_a_leitura_guardada(fr):
    api.get_os_detalhes(WID)
    api._rpc_call = fr.rpc                                                    # (o mesmo Fracttal de mentira)
    api._esquecer_leituras({"id_work_order": WID})                            # o que o `_rpc_call` faz ao gravar
    api.get_os_anexos(WID)
    assert fr.n[api.RPC_WO_TASKS] == 2                                        # a contagem leu de novo


def test_so_leitura_nao_tira_e_gravacao_tira(monkeypatch):
    assert api._eh_leitura(api.RPC_WO_TASKS) and api._eh_leitura(api.RPC_WO_DETAILS)
    assert api._eh_leitura(api.RPC_EXEC_GET) and api._eh_leitura(api.RPC_WO_FILES)
    for gravacao in (api.RPC_WO_FORMIT_VALUES, api.RPC_WO_CHANGE_STATUS, api.RPC_WO_RECALCULATE, api.RPC_WO_UPDATE,
                     api.RPC_LABELS_SYNC, api.RPC_WO_CANCEL, api.RPC_EXEC_INSERT, api.RPC_WO_INSERT):
        assert not api._eh_leitura(gravacao), gravacao
    chamadas = []
    monkeypatch.setattr(api, "_rpc_chamar", lambda m, p, t=45: chamadas.append(m) or {"data": [{"id": TAREFA}]})
    api.esquecer_os()
    api._leitura_da_os(api.RPC_WO_TASKS, WID, {"id_work_order": WID}, False)
    api._rpc_call(api.RPC_WO_FORMIT_VALUES, {"id_work_order": WID, "values": []})      # gravou nesta OS
    api._leitura_da_os(api.RPC_WO_TASKS, WID, {"id_work_order": WID})
    assert chamadas.count(api.RPC_WO_TASKS) == 2

"""Performance > Inspeção Geral do Inversor: a OS sai com o tipo de tarefa CORRETIVA (Levi, 29/10/2026: "No OS CREATOR
PERFORMANCE > INSPEÇÃO DO INVERSOR QUERO O TIPO DA TAREFA COMO CORRETIVA!").

O tipo vinha do plano do Fracttal ([Grid Co.] - Inspeção Geral do Inversor), que o `create_planned_os` copia. A troca é
feita na ferramenta, na hora de criar (como as subtarefas que o app acrescenta ao plano), e não no plano: ele é editado por
outra área e vale para quem cria OS por fora. Os outros planos seguem com o tipo deles. Nada vai à rede."""
import sys

import pytest

from nexus.torres.oscreator import ponte

pytest.importorskip("PyQt6")
if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
from os_web import perf_web  # noqa: E402

INSPECAO = {"description": "[Grid Co.] - Inspeção Geral do Inversor", "id_task_type_main": api.TASK_TYPE_MAIN["Inspeção"],
            "tasks_types_main_description": "Inspeção", "subtasks": [{"description": "Conferir alarmes", "id": 1}],
            "duration": 3600}
STRING = dict(INSPECAO, description="[Grid Co.] - Recomposição de String", tasks_types_main_description="Preventiva",
              id_task_type_main=api.TASK_TYPE_MAIN["Preventiva"])


def test_a_inspecao_do_inversor_vira_corretiva_e_os_outros_planos_nao():
    p = api.com_tipo_da_tarefa(dict(INSPECAO))
    assert p["id_task_type_main"] == api.TASK_TYPE_MAIN["Corretiva"] and p["tasks_types_main_description"] == "Corretiva"
    original = dict(INSPECAO)
    api.com_tipo_da_tarefa(original)
    assert original["tasks_types_main_description"] == "Inspeção"              # cópia: o plano em cache não muda
    assert api.com_tipo_da_tarefa(dict(STRING)) == STRING


@pytest.fixture
def criado(monkeypatch):
    planos = {1: INSPECAO, 2: STRING}
    visto = []
    monkeypatch.setattr(api, "get_plan_details", lambda idt, idi: dict(planos[idt]))
    monkeypatch.setattr(api, "_label_performance_id", lambda: None)
    monkeypatch.setattr(api, "create_planned_os", lambda a, plan, **k: visto.append(plan) or
                        {"id_task": 10 + len(visto), "id_work_order": 99, "wo_folio": 17000 + len(visto)})
    monkeypatch.setattr(api, "nascer_ticket", lambda *a, **k: {})
    monkeypatch.setattr(api, "_work_order_insert", lambda *a, **k: {"id_work_order": 99, "wo_folio": 17000}, raising=False)
    return visto


def _itens():
    return [{"asset": {"id": 5, "code": "TST-INV1", "description": "Inversor 1.1"}, "plano_id_task": 1, "plano_id_item": 5},
            {"asset": {"id": 6, "code": "TST-INV2", "description": "Inversor 1.2"}, "plano_id_task": 2, "plano_id_item": 6}]


def test_a_os_da_performance_nasce_corretiva(criado):
    api.create_performance_os(_itens())
    assert [p["tasks_types_main_description"] for p in criado] == ["Corretiva", "Preventiva"]
    assert criado[0]["id_task_type_main"] == api.TASK_TYPE_MAIN["Corretiva"]


def test_a_agrupada_da_performance_tambem(criado):
    try:
        api.create_performance_os_agrupada(_itens())
    except Exception:                                                      # a fase 2 não importa aqui
        pass
    assert [p["tasks_types_main_description"] for p in criado][:2] == ["Corretiva", "Preventiva"]


def test_o_resumo_do_plano_na_tela_diz_corretiva(monkeypatch):
    assert "Tipo: Corretiva" in perf_web.resumo_plano(api.com_tipo_da_tarefa(dict(INSPECAO)))
    import inspect
    from os_web import rotas
    assert "com_tipo_da_tarefa(" in inspect.getsource(rotas.api_plano)

"""A Inspeção nasce Corretiva no OS Creator Web (18/11/2026, Levi: "para as próximas OSs de inspeção ... configure para o
tipo de tarefa nascer como corretiva"). A OS 19361 nasceu Inspeção pela Fila do PCM e o App não perguntou "resolvido em
campo?", que só vale em corretiva, corretiva emergencial e religamento; o chamado do inversor não nasceu. Toda OS avulsa
(`api.create_os_rpc`) troca a Inspeção pela Corretiva, e a Fila do PCM e o Criar OS do zero não oferecem mais a Inspeção.
A inspeção de CHAMADO (o formulário do fabricante) segue Inspeção: é por ela que a administrativa nasce. O Fracttal é de
mentira; nada vai à rede."""
import sys

import pytest
from test_oscreator_garantias_28_10 import tela  # noqa: F401 — a fixture é usada pelo nome

from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone

CORRETIVA, INSPECAO = api.TASK_TYPE_MAIN["Corretiva"], api.TASK_TYPE_MAIN["Inspeção"]


@pytest.mark.parametrize("main_id,nome,esperado", [
    (None, "Inspeção", (CORRETIVA, "Corretiva")), (INSPECAO, "Inspeção", (CORRETIVA, "Corretiva")),
    (INSPECAO, "", (CORRETIVA, "Corretiva")), (None, " inspecao ", (CORRETIVA, "Corretiva")),
    (api.TASK_TYPE_MAIN["Corretiva Emergencial"], "Corretiva Emergencial",
     (api.TASK_TYPE_MAIN["Corretiva Emergencial"], "Corretiva Emergencial")),
    (77001, "Inspeção e Normalização", (77001, "Inspeção e Normalização")),       # o tipo do COS é outro
    (api.TASK_TYPE_MAIN["Administrativa"], "Administrativa", (api.TASK_TYPE_MAIN["Administrativa"], "Administrativa"))])
def test_so_a_inspecao_vira_corretiva(main_id, nome, esperado):
    assert api.tipo_que_nasce(main_id, nome) == esperado


class _Pedido(Exception):
    pass


def _enviado(monkeypatch):
    enviado = []

    def post(url, headers=None, json=None, timeout=None):
        enviado.append(json)
        raise _Pedido()
    monkeypatch.setattr(api.requests, "post", post)
    monkeypatch.setattr(api, "_rpc_headers", lambda: {})          # o login de mentira
    return enviado


def test_a_os_avulsa_de_inspecao_nasce_corretiva(monkeypatch):
    enviado = _enviado(monkeypatch)
    ativo = {"id": 5, "code": "TST-INV1", "description": "Inversor 1.1"}
    with pytest.raises(_Pedido):
        api.create_os_rpc(ativo, "Inspeção da ventoinha", "Inspeção", [])                  # pelo nome (Fila, Clonar)
    with pytest.raises(_Pedido):
        api.create_os_rpc(ativo, "T", "Inspeção", [], tipo={"id_main": INSPECAO})          # pelo id (Criar do zero)
    with pytest.raises(_Pedido):
        api.create_os_rpc(ativo, "T", "Corretiva Emergencial", [])
    p = [e[0]["params"] for e in enviado]
    assert [x["id_task_type_main"] for x in p] == [CORRETIVA, CORRETIVA, api.TASK_TYPE_MAIN["Corretiva Emergencial"]]
    assert [x["tasks_types_main_description"] for x in p] == ["Corretiva", "Corretiva", "Corretiva Emergencial"]


def test_a_inspecao_de_chamado_segue_inspecao(monkeypatch):
    planos = []
    monkeypatch.setattr(api, "create_planned_os", lambda asset, plano, **k: planos.append(plano) or {"id_work_order": 1})
    monkeypatch.setattr(api, "_classif_ids", lambda *a: {})
    monkeypatch.setattr(api, "label_id_por_nome", lambda n: None, raising=False)
    try:
        api.create_inspecao_chamado({"id": 5, "code": "TST-INV1", "tipo": "Inversor", "description": "Inversor 1.1"}, "Huawei")
    except Exception:                                   # noqa: BLE001 — a etiqueta e o resto não importam aqui
        pass
    assert planos and planos[0]["id_task_type_main"] == INSPECAO and planos[0]["tasks_types_main_description"] == "Inspeção"


def test_a_fila_e_o_criar_do_zero_nao_oferecem_a_inspecao(tela, monkeypatch):
    c, _, _ = tela
    import catalogos
    tipos = {"tipos": [{"id": CORRETIVA, "description": "Corretiva"}, {"id": INSPECAO, "description": "Inspeção"},
                       {"id": 77001, "description": "Inspeção e Normalização"}], "c1": [], "c2": []}
    monkeypatch.setattr(catalogos, "tipos_classif", lambda *a, **k: tipos)
    j = c.get("/os/api/tradicional/tipos").get_json()
    assert [t["description"] for t in j["tipos"]] == ["Corretiva", "Inspeção e Normalização"]
    fonte = open(ponte.RAIZ_CLONE + "/os_web/rotas_solic.py", encoding="utf-8").read()
    assert 't.get("description") != api.TIPO_QUE_VIRA_CORRETIVA' in fonte

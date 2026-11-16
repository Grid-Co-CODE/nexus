"""Clonar com a OS pai da original (16/11/2026, Levi: a OS de chamado finalizada por engano, clonada "exatamente como ela
é"). A leitura da OS de referência traz o pai (id e nº); a tela mostra "Manter a OS pai (nº)", marcado; o servidor cria o
clone filho do mesmo pai só quando a caixa vai marcada. O Fracttal é de mentira; nada vai à rede. Nomes e números
inventados (o repositório é público)."""
import sys

from test_oscreator_garantias_28_10 import tela  # noqa: F401 — a fixture é usada pelo nome

from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone

WEB = ponte.RAIZ_CLONE + "/os_web"
ASSET = {"id": 5, "code": "TST-TRK1", "label": "Tracker 1"}


def _rpc(pai_no_cabecalho=True):
    def rpc(metodo, params, timeout=45):
        if metodo == api.RPC_WO_TASKS:
            return {"data": [{"id": 1, "wo_folio": 900, "code_item": "TST-TRK1", "items_description": "Tracker 1",
                              "tasks_description": "Acompanhamento", "id_parent_wo": 4321}]}
        if metodo == api.RPC_WO_DETAILS:
            return {"data": [{"labels": [{"id": 7}], "id_parent_wo": 4321 if pai_no_cabecalho else None}]}
        return {"data": []}
    return rpc


def test_a_os_de_referencia_traz_o_pai(monkeypatch):
    monkeypatch.setattr(api, "_asset_by_code", lambda c: dict(ASSET))
    monkeypatch.setattr(api, "_cabecalho_os", lambda wid: {"wo_folio": 812} if wid == 4321 else {})
    for no_cabecalho in (True, False):                    # sem o pai no cabeçalho, vale o da tarefa
        monkeypatch.setattr(api, "_rpc_call", _rpc(no_cabecalho))
        d = api.get_os_para_clonar(77)
        assert (d["id_parent_wo"], d["os_pai"], d["etiqueta_ids"]) == (4321, "812", [7])


def test_o_clone_nasce_filho_do_pai_so_com_a_caixa_marcada(tela, monkeypatch):
    c, _, _ = tela
    from os_web import lista_central
    chamadas = []
    monkeypatch.setattr(api, "load_assets_cached", lambda *a, **k: [dict(ASSET)])
    monkeypatch.setattr(api, "clonar_os", lambda tarefas, idp, nome, eids, note, **k: chamadas.append(k) or
                        {"ok": True, "os": {"wo_folio": 901, "id_work_order": 9010}, "n_tarefas": 1, "n_criadas": 1})
    monkeypatch.setattr(lista_central, "criadas", lambda r: 0)
    corpo = {"tarefas": [{"asset": {"id": 5}, "descricao": "Acompanhamento"}], "id_responsible": 11,
             "responsible_name": "Pessoa Teste", "note": "nota", "id_parent": 4321}
    assert c.post("/os/api/clonar/criar", json=dict(corpo, manter_pai=True)).status_code == 200
    assert c.post("/os/api/clonar/criar", json=dict(corpo, manter_pai=False)).status_code == 200
    assert c.post("/os/api/clonar/criar", json=dict(corpo, manter_pai=True, id_parent="x")).status_code == 200
    assert [k.get("id_parent") for k in chamadas] == [4321, None, None]


def test_a_tela_mostra_e_manda_o_pai():
    js = open(WEB + "/static/clonar.js", encoding="utf-8").read()
    html = open(WEB + "/templates/clonar.html", encoding="utf-8").read()
    assert 'id="chk_pai"' in html and 'id="lbl_pai" hidden' in html
    assert "manter_pai: !!D.id_parent_wo && $('chk_pai').checked" in js and "id_parent: D.id_parent_wo" in js

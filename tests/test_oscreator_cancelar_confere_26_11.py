"""O Cancelar OS confere no Fracttal se a OS ficou cancelada (26/11/2026).

Maria Oliveira, pelo Levi: "Algumas OSs foram canceladas pelo supervisor no Nexus e não foram canceladas no Fracttal". A OS
18428 (UFV Vitesse) foi cancelada pela tela do Nexus em 16/11 e seguia Em Processo no Fracttal dez dias depois; a 18427,
cancelada no mesmo minuto, ficou cancelada. A tela dizia "cancelada com sucesso" sem reler a OS (o Retornar e o Fazer OS
já releem), e o `cancel_os` só via o {"success": false} quando o `result` vinha como dict, nunca dentro de lista.
Prova: a OS que seguiu aberta devolve 502 com o aviso; a cancelada segue com o "cancelada com sucesso"; o status que não
foi lido não vira erro; o {"success": false} em lista levanta o erro. Contra o código de antes, falha. O Fracttal é de
mentira; números inventados."""
import pytest
from test_oscreator_anexo_incluir import WID, _cliente
from test_oscreator_solic_pcm import api  # noqa: F401

import os_estado  # noqa: E402


@pytest.fixture
def fr(monkeypatch):
    estado = {"st": 4, "pedidos": []}
    monkeypatch.setattr(api, "cancel_os", lambda wid, idm, note="": estado["pedidos"].append((wid, idm, note)) or {"ok": True})
    monkeypatch.setattr(api, "status_da_os", lambda wid: estado["st"])
    return estado


def _cancelar():
    return _cliente().post(f"/os/api/os/{WID}/cancelar",
                           json={"id_status_custom": 9, "folio": "18428", "note": " Atividade realizada em outra OS "})


def test_a_os_cancelada_de_fato_segue_com_sucesso(fr):
    r = _cancelar()
    assert r.status_code == 200 and r.get_json()["mensagem"] == "OS 18428 cancelada com sucesso."
    assert fr["pedidos"] == [(WID, 9, "Atividade realizada em outra OS")]


def test_a_os_que_seguiu_em_processo_nao_vira_sucesso(fr):
    fr["st"] = 1                                       # o caso da 18428: o Fracttal aceitou e a OS seguiu Em Processo
    r = _cancelar()
    j = r.get_json()
    assert r.status_code == 502 and not j.get("ok")
    assert "18428" in j["erro"] and "em processo" in j["erro"] and "NÃO foi cancelada" in j["erro"]


def test_a_os_em_verificacao_tambem_avisa(fr):
    fr["st"] = 2
    r = _cancelar()
    assert r.status_code == 502 and "em verificação" in r.get_json()["erro"]


def test_o_status_que_nao_foi_lido_nao_vira_erro(fr):
    fr["st"] = None                                    # o Fracttal não respondeu a leitura: como antes, sem acusar falha
    assert _cancelar().status_code == 200


@pytest.mark.parametrize("resposta", [
    {"success": False, "message": "sem permissão"},
    [{"success": False, "message": "sem permissão"}],          # o `result` em lista passava calado
])
def test_a_recusa_do_fracttal_vira_erro_em_dict_e_em_lista(monkeypatch, resposta):
    monkeypatch.setattr(api, "_rpc_call", lambda metodo, params: resposta)
    with pytest.raises(api.FracttalError, match="sem permissão"):
        os_estado.cancel_os(WID, 9, "x")


@pytest.mark.parametrize("resposta", [{"success": True}, [{"success": True}], [], None])
def test_a_resposta_sem_recusa_segue(monkeypatch, resposta):
    monkeypatch.setattr(api, "_rpc_call", lambda metodo, params: resposta)
    assert os_estado.cancel_os(WID, 9, "x")["ok"] is True

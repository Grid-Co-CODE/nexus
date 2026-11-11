"""O Fazer OS no card do Histórico e o Editar com o X nos anexos (Levi, 11/11/2026): o botão ao lado do PDF na OS em
processo; a Solicitação só quando há; as respostas que nunca apagam a foto da subtarefa (a gravação troca a lista de
anexos dela, e o OS Creator mandava `[]`); a foto na subtarefa pelo caminho do App de Campo; o envio com o início e o fim
da OS (corrigindo a execução que a tarefa já tem) e a OS Em Verificação lida de volta; o anexo excluído no Fracttal. O
Fracttal é de mentira; números e textos inventados."""
import io

import pytest
from test_oscreator_anexo_incluir import WID, _cliente
from test_oscreator_card_tarefas import Fracttal, _card, _item, _tarefa  # noqa: F401
from test_oscreator_solic_pcm import api  # noqa: F401

import os_execucao  # noqa: E402
from os_web import os_acoes_web as regra  # noqa: E402

TID, FID = 70001, 81001
FOTO = {"value": ".ot/%d/antiga.jpg" % WID, "size": 10, "type": 1, "description": "antiga.jpg"}
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


class Rpc:
    """O RPC do Fracttal de mentira: guarda o que foi mandado; a subtarefa tem a foto `FOTO`."""

    def __init__(self, anexos=None, arquivos=None):
        self.pedidos, self.anexos, self.arquivos = [], list(anexos or []), list(arquivos or [])

    def __call__(self, metodo, params):
        self.pedidos.append((metodo, params))
        if metodo == os_execucao.RPC_FORMIT_ATTACH:
            return {"data": [dict(a) for a in self.anexos]}
        if metodo == "tasks.work_orders_tasks_files_list":
            return {"data": [dict(a) for a in self.arquivos]}
        return {"success": True, "data": []}

    def gravacoes(self):
        return [p for m, p in self.pedidos if m == os_execucao.RPC_WO_FORMIT_VALUES]


def test_regravar_a_resposta_leva_a_foto_que_a_subtarefa_tem(monkeypatch):
    rpc = Rpc(anexos=[FOTO])
    monkeypatch.setattr(api, "_rpc_call", rpc)
    os_execucao.salvar_subtarefas(WID, TID, [{"id_form_item": FID, "valor": "Sim", "tipo": 2, "n_anexos": 1},
                                             {"id_form_item": FID + 1, "valor": "12", "tipo": 3, "n_anexos": 0}])
    (linhas,) = rpc.gravacoes()
    assert linhas[0]["attachments"] == [FOTO] and linhas[1]["attachments"] == []
    assert [m for m, _ in rpc.pedidos].count(os_execucao.RPC_FORMIT_ATTACH) == 1    # só a que tem anexo é lida


def test_sem_ler_as_fotos_nada_se_grava(monkeypatch):
    def recusa(metodo, params):
        if metodo == os_execucao.RPC_FORMIT_ATTACH:
            return {"success": False, "message": "ERRO"}
        raise AssertionError("gravou sem saber das fotos")
    monkeypatch.setattr(api, "_rpc_call", recusa)
    with pytest.raises(api.FracttalError):
        os_execucao.salvar_subtarefas(WID, TID, [{"id_form_item": FID, "valor": "Sim", "tipo": 2, "n_anexos": 1}])


def test_a_foto_na_subtarefa_vai_com_as_que_ela_ja_tinha(monkeypatch):
    rpc = Rpc(anexos=[FOTO])
    monkeypatch.setattr(api, "_rpc_call", rpc)
    monkeypatch.setattr(api, "attach_imagem_os", lambda wid, tid, dados, nome: {"ok": True, "value": f".ot/{wid}/{nome}"})
    r = os_execucao.anexar_no_item(WID, TID, FID, 2, "Sim", PNG, "nova.png")
    (linhas,) = rpc.gravacoes()
    assert r["n"] == 2 and linhas[0]["value"] == "Sim"
    assert [a["value"] for a in linhas[0]["attachments"]] == [FOTO["value"], ".ot/%d/nova.png" % WID]


def test_tirar_a_foto_da_subtarefa_e_dos_anexos_da_tarefa(monkeypatch):
    outra = dict(FOTO, value=".ot/%d/outra.jpg" % WID)
    rpc = Rpc(anexos=[FOTO, outra], arquivos=[{"id": 555, "value": FOTO["value"]}, {"id": 556, "value": "x"}])
    monkeypatch.setattr(api, "_rpc_call", rpc)
    os_execucao.tirar_do_item(WID, TID, FID, 2, "Sim", FOTO["value"])
    (linhas,) = rpc.gravacoes()
    assert linhas[0]["attachments"] == [outra]
    assert ("tasks.work_orders_tasks_files_delete", {"id": 555}) in rpc.pedidos
    with pytest.raises(api.FracttalError):
        os_execucao.tirar_do_item(WID, TID, FID, 2, "Sim", ".ot/nao/existe.jpg")


def test_o_x_do_anexo_da_tarefa_so_exclui_o_que_e_da_os(monkeypatch):
    rpc = Rpc()
    monkeypatch.setattr(api, "_rpc_call", rpc)
    monkeypatch.setattr(api, "get_os_anexos", lambda wid: [{"raw": {"id": 555}, "value": "a"}])
    c = _cliente()
    r = c.post(f"/os/api/os/{WID}/anexo/excluir", json={"tipo": "os", "id": "999"})
    assert r.status_code == 404 and not any(m == os_execucao.RPC_FILES_DELETE for m, _ in rpc.pedidos)
    r = c.post(f"/os/api/os/{WID}/anexo/excluir", json={"tipo": "os", "id": "555"})
    assert r.status_code == 200 and (os_execucao.RPC_FILES_DELETE, {"id": 555}) in rpc.pedidos


def test_os_anexos_dizem_o_que_o_x_exclui():
    os_ = regra.itens_os([{"value": ".ot/1/a.jpg", "nome": "a.jpg", "is_image": True, "raw": {"id": 555}}], WID)
    assert os_[0]["excluir"] == {"tipo": "os", "id": "555"}
    sub = regra.itens_subtarefas([{"value": ".ot/1/b.jpg", "nome": "b.jpg", "is_image": True, "url": "u", "subtarefa": "S",
                                   "id_tarefa": TID, "id_form_item": FID}], WID)
    assert sub[0]["excluir"] == {"tipo": "sub", "tarefa": str(TID), "item": str(FID), "value": ".ot/1/b.jpg"}


# ── o envio do Fazer OS ──
class Os:
    def __init__(self, st=1, campos=None, regs=None, exec_estado="parada"):
        self.st, self.pedidos = st, []
        self.campos = campos if campos is not None else [
            {"id_form_item": FID, "descricao": "Conectores", "valor": "Sim", "obrigatorio": True, "anexo_obrigatorio": True,
             "n_anexos": 1, "tipo": 2}]
        self.regs, self.exec_estado = regs or [], exec_estado

    def ligar(self, mp):
        from os_web import rotas_acomp
        mp.setattr(api, "status_da_os", lambda wid: self.st)
        mp.setattr(api, "_ids_tarefas_da_os", lambda wid: [TID])
        mp.setattr(api, "subtarefas_da_tarefa", lambda tid: [dict(c) for c in self.campos])
        mp.setattr(api, "execucao_atual", lambda tid: {"estado": self.exec_estado})
        mp.setattr(api, "historico_execucao", lambda tid: list(self.regs))
        mp.setattr(api, "editar_execucao", lambda rid, ini, fim: self.pedidos.append(("editar", rid)) or {"ok": True})
        mp.setattr(api, "registrar_execucao",
                   lambda tid, ini, fim, note="": self.pedidos.append(("registrar", tid)) or {"confirmado": True})

        def mudar(wid, st, verificar_gatilhos=True):
            self.pedidos.append(("status", st))
            self.st = st
            return {"ok": True}
        mp.setattr(api, "mudar_status_os", mudar)
        mp.setattr(rotas_acomp, "_ajustar", lambda wid, campos=None, ticket=None: None)
        return self


def _enviar(**k):
    corpo = {"inicio": "2026-11-10T08:00", "fim": "2026-11-10T10:00", "folio": "15900"}
    corpo.update(k)
    return _cliente().post(f"/os/api/os/{WID}/fazer", json=corpo)


def test_fazer_os_lanca_a_execucao_e_manda_para_verificacao(monkeypatch):
    o = Os().ligar(monkeypatch)
    r = _enviar()
    assert r.status_code == 200 and "enviada para verificação" in r.get_json()["mensagem"]
    assert o.pedidos == [("registrar", TID), ("status", 2)]


def test_a_tarefa_que_ja_tem_execucao_tem_as_datas_corrigidas(monkeypatch):
    o = Os(regs=[{"id": 9, "initial_date": "2026-11-10T07:00:00Z", "final_date": "2026-11-10T07:30:00Z"}]).ligar(monkeypatch)
    assert _enviar().status_code == 200 and o.pedidos == [("editar", 9), ("status", 2)]


@pytest.mark.parametrize("campo,falta", [({"valor": ""}, "Conectores"), ({"n_anexos": 0}, "falta a foto")])
def test_o_que_falta_nao_deixa_enviar(monkeypatch, campo, falta):
    base = {"id_form_item": FID, "descricao": "Conectores", "valor": "Sim", "obrigatorio": True,
            "anexo_obrigatorio": True, "n_anexos": 1, "tipo": 2}
    o = Os(campos=[dict(base, **campo)]).ligar(monkeypatch)
    r = _enviar()
    assert r.status_code == 400 and falta in r.get_json()["erro"] and not o.pedidos


def test_sem_o_fim_a_os_em_verificacao_e_o_cronometro_rodando_nao_vao(monkeypatch):
    Os().ligar(monkeypatch)
    assert _enviar(fim="").status_code == 400
    assert _enviar(inicio="2026-11-10T11:00").status_code == 400                       # fim antes do início
    Os(st=2).ligar(monkeypatch)
    assert "verificação" in _enviar().get_json()["erro"]
    o = Os(exec_estado="rodando").ligar(monkeypatch)
    assert "cronômetro" in _enviar().get_json()["erro"] and not o.pedidos


def test_o_botao_fazer_os_e_a_solicitacao_no_card(monkeypatch):
    monkeypatch.setattr(api, "_rpc_call", Fracttal([_tarefa(1)], [_item(1, 1)]).rpc)
    h = _card("Em Processo")
    cab = h[:h.index('class="det-corpo"')]
    assert 'data-acao="fazer"' in cab and cab.index('data-acao="fazer"') < cab.index("data-os-pdf")
    assert "criada sem solicitação" not in h                             # a OS sem solicitação não mostra a pílula
    assert 'data-dlg="fazer"' in h and "data-anx-editar" in h
    assert 'data-acao="fazer"' not in _card("Em Verificação")

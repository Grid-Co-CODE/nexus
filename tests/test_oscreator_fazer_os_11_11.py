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
VINC = {"id": 39957833, "id_work_orders_tasks_files": 91725217, "value": ".ot/%d/antiga.jpg" % WID, "type": 1,
        "description": "antiga.jpg"}
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


class Rpc:
    """O RPC do Fracttal de mentira: guarda o que foi mandado; a subtarefa tem os vínculos de `anexos`."""

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


def test_regravar_a_resposta_nao_manda_anexo(monkeypatch):
    # a gravação ACRESCENTA anexos (OS de teste 19259): a lista inteira duplicava a foto; `[]` não apaga nada
    rpc = Rpc(anexos=[VINC])
    monkeypatch.setattr(api, "_rpc_call", rpc)
    os_execucao.salvar_subtarefas(WID, TID, [{"id_form_item": FID, "valor": "Sim", "tipo": 2, "n_anexos": 1}])
    (linhas,) = rpc.gravacoes()
    assert linhas[0]["attachments"] == [] and not any(m == os_execucao.RPC_FORMIT_ATTACH for m, _ in rpc.pedidos)


def test_a_foto_na_subtarefa_vai_sozinha_na_gravacao(monkeypatch):
    rpc = Rpc(anexos=[VINC])
    monkeypatch.setattr(api, "_rpc_call", rpc)
    monkeypatch.setattr(api, "attach_imagem_os", lambda wid, tid, dados, nome: {"ok": True, "value": f".ot/{wid}/{nome}"})
    os_execucao.anexar_no_item(WID, TID, FID, 2, "Sim", PNG, "nova.png")
    (linhas,) = rpc.gravacoes()
    assert linhas[0]["value"] == "Sim" and [a["value"] for a in linhas[0]["attachments"]] == [".ot/%d/nova.png" % WID]


def test_tirar_a_foto_da_subtarefa_pelo_vinculo_e_depois_o_arquivo(monkeypatch):
    outra = dict(VINC, id=39957999, id_work_orders_tasks_files=91725999, value=".ot/%d/outra.jpg" % WID)
    rpc = Rpc(anexos=[VINC, outra], arquivos=[{"id": "91725207", "value": VINC["value"]}, {"id": "91726000", "value": "x"}])
    monkeypatch.setattr(api, "_rpc_call", rpc)

    def depois_de_tirar(metodo, params):            # a lista do item já sem o vínculo tirado
        if metodo == os_execucao.RPC_FORMIT_ATTACH_DELETE:
            rpc.anexos = [outra]
        return rpc(metodo, params)
    monkeypatch.setattr(api, "_rpc_call", depois_de_tirar)
    os_execucao.tirar_do_item(WID, TID, FID, 39957833)
    apagados = [(m, p) for m, p in rpc.pedidos if m.endswith("_delete")]
    # o vínculo antes do arquivo dele; e o arquivo que a subida pôs nos anexos da tarefa (OS 19259)
    assert apagados == [(os_execucao.RPC_FORMIT_ATTACH_DELETE, {"id": 39957833}),
                        (os_execucao.RPC_FILES_DELETE, {"id": 91725217}),
                        (os_execucao.RPC_FILES_DELETE, {"id": 91725207})]
    with pytest.raises(api.FracttalError):
        os_execucao.tirar_do_item(WID, TID, FID, 123)


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
                                   "id_tarefa": TID, "id_form_item": FID, "raw": {"id": 39957833}}], WID)
    assert sub[0]["excluir"] == {"tipo": "sub", "tarefa": str(TID), "item": str(FID), "id": "39957833"}


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


def test_sem_o_confirmado_vale_o_registro_lido_de_volta(monkeypatch):
    # OS de teste 19259: o Fracttal gravou a execução certa e a resposta não veio "confirmada"
    o = Os().ligar(monkeypatch)
    lidos = []
    monkeypatch.setattr(api, "registrar_execucao", lambda tid, ini, fim, note="": (
        lidos.append({"id": 7, "initial_date": "2026-11-10T11:00:00Z", "final_date": "2026-11-10T13:00:00Z"})
        or {"confirmado": False}))
    monkeypatch.setattr(api, "historico_execucao", lambda tid: list(lidos))
    assert _enviar().status_code == 200 and o.pedidos == [("status", 2)]
    lidos.clear()
    monkeypatch.setattr(api, "registrar_execucao", lambda tid, ini, fim, note="": {"confirmado": False})
    o.st = 1
    assert _enviar().status_code == 502


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

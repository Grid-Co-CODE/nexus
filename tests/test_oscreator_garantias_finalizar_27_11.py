"""O Finalizar do chamado de Garantias em dois casos que travavam (27/11/2026, a analista de chamados pelo Levi):

- OS 13987: "Mais um que não permite finalizar o chamado". A tarefa das OS de chamado antigas pede as validações de
  segurança do Fracttal para ligar o cronômetro (MUST_COMPLETE_SECURITY_VALIDATIONS); o Finalizar registrava a atividade
  antes de concluir e parava aí. Agora conclui sem o registro e diz por quê.
- OS 17320: "está com o status em verificação 17/11, e precisa ser encerrado, porém não tem o botão para concluir, e
  continua aparecendo no relatório que enviamos ao cliente". O Finalizar aparece na OS em verificação e aprova (o
  Concluir da OS em verificação); a conta que não aprova vê isso dito, sem "chamado finalizado".

Fracttal e banco FALSOS (os do teste de 15/11): nenhum pedido vai à rede. Nomes e números de mentira."""
import datetime as dt

from test_oscreator_acomp_30min_20_10 import URL, _cliente, _memoria_limpa, fila, fracttal  # noqa: F401
from test_oscreator_garantias_atividade_15_11 import BRT, cron  # noqa: F401  (fixture: o cronômetro de mentira)

import api  # noqa: E402 — o api.py do clone (o sys.path vem do módulo acima)
from os_web import acomp_raiox  # noqa: E402

ERRO_SEG = {"ok": False, "erro": "MUST_COMPLETE_SECURITY_VALIDATIONS"}


def _status(monkeypatch, cron, antes, depois):
    """A OS com o status `antes` no detalhe e o Fracttal devolvendo `depois` (uma lista: uma leitura por vez)."""
    seq = list(depois)
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: {"folio": 9104, "notas": "", "code": "TST-1", "subtarefas": [],
                                                             "status_id": antes,
                                                             "tarefas": [{"id": t} for t in cron["tarefas"]]})
    monkeypatch.setattr(api, "_cabecalho_os", lambda wid: {"wo_folio": "9104",
                                                           "id_status_work_order": seq.pop(0) if len(seq) > 1 else seq[0]})


def _comentado(cron):
    cron["banco"].append({"id": "o1", "quando": dt.datetime(2026, 9, 22, 9, 0, tzinfo=BRT).isoformat(), "os": "9104",
                          "tipo": "obs", "texto": "Aberto.", "quem": "", "email": "", "ativo": "", "extra": {}})


def _finalizar():
    cli = _cliente()
    cli.get(URL)
    return cli.post("/os/api/acomp/9104/finalizar", json={"wid": 2})


def test_a_tarefa_que_pede_as_validacoes_de_seguranca_conclui_sem_o_registro(cron, fila, monkeypatch):
    _comentado(cron)
    monkeypatch.setattr(api, "iniciar_execucao", lambda tid, inicio=None: dict(ERRO_SEG))
    j = _finalizar().get_json()
    assert j["ok"] is True and cron["concluiu"] == 1 and "foi concluída no Fracttal" in j["mensagem"]
    assert "validações de segurança" in j["aviso"] and "sem o registro da atividade" in j["aviso"]
    assert not [p for p in cron["pedidos"] if p[0] == "finalizar"]          # nada foi ligado, nada a desligar


def test_outra_recusa_ao_registrar_segue_parando_o_finalizar(cron, fila, monkeypatch):
    _comentado(cron)
    monkeypatch.setattr(api, "iniciar_execucao", lambda tid, inicio=None: {"ok": False, "erro": "SEM_PERMISSAO"})
    r = _finalizar()
    assert r.status_code == 400 and "SEM PERMISSAO" in r.get_json()["erro"] and cron["concluiu"] == 0


def test_a_os_em_verificacao_e_aprovada_sem_mexer_na_atividade(cron, fila, monkeypatch):
    _comentado(cron)                                    # o comentário não lança registro: a atividade já foi feita
    _status(monkeypatch, cron, 2, [3])
    j = _finalizar().get_json()
    assert j["ok"] is True and cron["concluiu"] == 1 and "foi concluída no Fracttal" in j["mensagem"]
    assert cron["pedidos"] == []


def test_a_conta_que_nao_aprova_ve_a_os_seguir_em_verificacao(cron, fila, monkeypatch):
    _status(monkeypatch, cron, 2, [2])
    r = _finalizar()
    assert r.status_code == 400 and "manteve a OS 9104 em verificação" in r.get_json()["erro"]
    assert not [x for x in cron["banco"] if x["tipo"] == "finalizado"]        # sem a anotação de chamado finalizado


def test_o_concluir_que_cai_em_verificacao_aprova_na_hora(cron, fila, monkeypatch):
    _status(monkeypatch, cron, 1, [2, 3])
    aprovou = []
    monkeypatch.setattr(api, "concluir_os", lambda wid: aprovou.append(wid) or {"ok": True})
    j = _finalizar().get_json()
    assert j["ok"] is True and aprovou == [2] and "foi concluída no Fracttal" in j["mensagem"]


def test_sem_aprovar_o_chamado_finaliza_e_diz_que_ficou_em_verificacao(cron, fila, monkeypatch):
    _status(monkeypatch, cron, 1, [2, 2])

    def recusa(wid):
        raise api.FracttalError("sem permissão")
    monkeypatch.setattr(api, "concluir_os", recusa)
    j = _finalizar().get_json()
    assert j["ok"] is True and "foi para a verificação no Fracttal" in j["mensagem"]


def test_a_os_ja_concluida_nao_e_finalizada_de_novo(cron, fila, monkeypatch):
    _status(monkeypatch, cron, 3, [3])
    r = _finalizar()
    assert r.status_code == 400 and "já está concluída" in r.get_json()["erro"] and cron["concluiu"] == 0


def test_o_raio_x_marca_o_chamado_em_verificacao(fila):
    base = {"os": 9104, "wid": 2, "titulo": "[Inversor 1.2] - Acompanhamento de chamado", "ativo": "Inversor 1.2",
            "codigo": "TST-1", "criada": "01/10/2026 10:00", "nota": ""}
    ver = acomp_raiox.blocos("9104", dict(base, coluna="verificacao", status="Em Verificação"), ticket="", obs=[])
    aberto = acomp_raiox.blocos("9104", dict(base, coluna="fazer", status="A fazer"), ticket="", obs=[])
    assert (ver["aberto"], ver["em_verificacao"]) == (False, True)
    assert (aberto["aberto"], aberto["em_verificacao"]) == (True, False)

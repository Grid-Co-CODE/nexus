"""As tarefas da OS, uma a uma (Levi, 06/11/2026, na página da OS da Engenharia: "Nos ativos deve mostrar um check quando a
tarefa for concluída"; "Quando temos mais de um ativo deve ter a opção de abrir as subtarefas do ativo e responder a
subtarefa"; "Ao lado do ativo deve ter um botão de 'Iniciar atividade' [...] pode ter a opção de pausar"; "Botão de anexar
na tarefa, aí terá ao lado do nome do ativo 'x anexos' e os botões de iniciar, pausar ou concluir!").

O cronômetro é o do Fracttal web (`os_execucao`), por id da tarefa, com as regras da sessão do OS Creator: pausar pede o
motivo; a pausada é retomada antes de encerrar; o estado é relido depois de cada passo (o Fracttal aceita calado); a tarefa
tem de ser da OS. Concluir a tarefa encerra o tempo, sem lançar outro registro (dobraria as horas), e pede antes as
subtarefas obrigatórias. O Fracttal daqui é de mentira; nenhum teste vai à rede."""
import sys

import pytest

from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
from test_oscreator_anexo_incluir import JWT, _cliente  # noqa: E402,F401

WID, T1, T2 = 9101, 70001, 70002


class Cronometro:
    def __init__(self):
        self.estado = {T1: "parada", T2: "parada"}
        self.pedidos, self.calado = [], False

    def atual(self, tid):
        return {"estado": self.estado.get(tid, "parada"), "inicio": "2026-11-06T10:00:00", "trabalhado_s": 600,
                "motivo": ""}

    def _vai(self, nome, tid, novo, *extra):
        self.pedidos.append((nome, tid) + extra)
        if not self.calado:
            self.estado[tid] = novo
        return {"ok": True}

    def iniciar(self, tid):
        return self._vai("iniciar", tid, "rodando")

    def pausar(self, tid, motivo, nota=""):
        return self._vai("pausar", tid, "pausada", motivo, nota)

    def retomar(self, tid):
        return self._vai("retomar", tid, "rodando")

    def finalizar(self, tid):
        return self._vai("finalizar", tid, "parada")


@pytest.fixture
def fracttal(monkeypatch):
    c = Cronometro()
    det = {"folio": "15900", "tarefas": [
        {"id": T1, "titulo": "Coleta", "ativo": "Inversor 1.1", "inicio": None, "fim": None},
        {"id": T2, "titulo": "Coleta", "ativo": "Inversor 1.2", "inicio": "2026-11-05T08:00:00", "fim": "2026-11-05T09:00:00"}],
        "subtarefas": [{"id_tarefa": T1, "descricao": "Medir", "feito": False, "id_form_item": 1},
                       {"id_tarefa": T2, "descricao": "Medir", "feito": True, "id_form_item": 2}]}
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: det)
    monkeypatch.setattr(api, "_ids_tarefas_da_os", lambda wid: [T1, T2])
    monkeypatch.setattr(api, "execucao_atual", c.atual)
    monkeypatch.setattr(api, "iniciar_execucao", c.iniciar)
    monkeypatch.setattr(api, "pausar_execucao", c.pausar)
    monkeypatch.setattr(api, "retomar_execucao", c.retomar)
    monkeypatch.setattr(api, "finalizar_execucao", c.finalizar)
    c.campos = [{"id_form_item": 1, "descricao": "Medir", "obrigatorio": True, "valor": "", "tipo": 1}]
    monkeypatch.setattr(api, "subtarefas_da_tarefa", lambda tid: [dict(x) for x in c.campos])

    def salvar(wid, tid, valores):
        c.pedidos.append(("salvar", tid, valores))
        for v in valores:
            for x in c.campos:
                if x["id_form_item"] == v["id_form_item"]:
                    x["valor"] = v["valor"]
        return {"ok": True, "n": len(valores)}
    monkeypatch.setattr(api, "salvar_subtarefas", salvar)
    monkeypatch.setattr(api, "motivos_pausa", lambda: [{"id": 7, "descricao": "Almoço"}])
    return c


def _cron(acao, tid=T1, **k):
    return _cliente().post(f"/os/api/os/{WID}/tarefa/{tid}/cronometro", json=dict(acao=acao, **k))


def test_a_lista_traz_cada_tarefa_com_o_check_e_o_cronometro(fracttal):
    j = _cliente().get(f"/os/api/os/{WID}/tarefas").get_json()
    t1, t2 = j["tarefas"]
    assert (t1["id"], t1["ativo"], t1["feita"], t1["execucao"]["estado"]) == (T1, "Inversor 1.1", False, "parada")
    assert (t2["id"], t2["feita"], t2["feitas"], t2["total"]) == (T2, True, 1, 1)


def test_iniciar_pausar_retomar_e_concluir(fracttal):
    fracttal.campos[0]["valor"] = "12,5"
    assert _cron("iniciar").get_json()["estado"] == "rodando"
    r = _cron("pausar")
    assert r.status_code == 400 and "motivo" in r.get_json()["erro"]
    assert _cron("pausar", motivo=7, nota="almoço").get_json()["estado"] == "pausada"
    assert _cron("retomar").get_json()["estado"] == "rodando"
    assert _cron("concluir").get_json()["estado"] == "parada"
    assert [p[0] for p in fracttal.pedidos] == ["iniciar", "pausar", "retomar", "finalizar"]


def test_concluir_a_pausada_retoma_antes(fracttal):
    fracttal.campos[0]["valor"] = "ok"
    fracttal.estado[T1] = "pausada"
    assert _cron("concluir").get_json()["estado"] == "parada"
    assert [p[0] for p in fracttal.pedidos] == ["retomar", "finalizar"]


def test_concluir_pede_as_subtarefas_obrigatorias(fracttal):
    fracttal.estado[T1] = "rodando"
    r = _cron("concluir")
    assert r.status_code == 400 and "Medir" in r.get_json()["erro"] and not fracttal.pedidos


def test_o_que_nao_cabe_no_estado_e_recusado(fracttal):
    assert _cron("pausar", motivo=7).status_code == 400          # parada não pausa
    fracttal.estado[T1] = "rodando"
    assert _cron("iniciar").status_code == 400                    # rodando não inicia de novo
    assert not fracttal.pedidos


def test_a_tarefa_tem_de_ser_da_os(fracttal):
    assert _cron("iniciar", tid=99999).status_code == 404 and not fracttal.pedidos


def test_o_fracttal_que_aceita_calado_e_dito(fracttal):
    fracttal.calado = True
    r = _cron("iniciar")
    assert r.status_code == 502 and "parada" in r.get_json()["erro"]


def test_responder_as_subtarefas_grava_e_le_de_volta(fracttal):
    r = _cliente().post(f"/os/api/os/{WID}/tarefa/{T1}/respostas", json={"valores": {"1": "12,5"}})
    j = r.get_json()
    assert r.status_code == 200 and j["ok"] and "1 resposta" in j["mensagem"] and j["pendentes"] == 0
    assert fracttal.pedidos == [("salvar", T1, [{"id_form_item": 1, "valor": "12,5", "tipo": 1}])]


def test_os_motivos_da_pausa(fracttal):
    assert _cliente().get("/os/api/execucao/motivos").get_json() == {"motivos": [{"id": 7, "descricao": "Almoço"}]}


# o "x anexos" do ativo (06/11/2026: "Botão de anexar na tarefa, aí terá ao lado do nome do ativo 'x anexos'"): o Anexar da
# tarefa grava na aba Anexos DELA (o files_insert do Incluir anexo), e não numa subtarefa; a conta do ativo junta os dois
def test_cada_arquivo_da_os_sabe_a_tarefa_dele(monkeypatch):
    arquivos = {T1: [{"value": ".ot/1/a.pdf"}], T2: [{"value": ".ot/1/b.pdf"}]}
    api.esquecer_os()
    monkeypatch.setattr(api, "_ids_tarefas_da_os", lambda wid: [T1, T2])
    monkeypatch.setattr(api, "_rpc_call", lambda m, p, *a, **k: {"data": arquivos.get(p.get("id_work_order_task"), [])})
    monkeypatch.setattr(api, "s3_get_url", lambda v: None)
    try:
        assert [(a["nome"], a["id_tarefa"]) for a in api.get_os_anexos(WID)] == [("a.pdf", T1), ("b.pdf", T2)]
    finally:
        api.esquecer_os()


def test_a_contagem_traz_os_arquivos_de_cada_tarefa(monkeypatch):
    monkeypatch.setattr(api, "get_os_subtarefa_anexos", lambda wid: [{"id_tarefa": T1, "value": ".ot/1/foto.jpg"}])
    monkeypatch.setattr(api, "get_os_anexos", lambda wid: [{"id_tarefa": T1, "value": ".ot/1/foto.jpg"},   # já é da subtarefa
                                                         {"id_tarefa": T2, "value": ".ot/1/laudo.pdf"},
                                                         {"id_tarefa": T2, "value": ".ot/1/medicao.xlsx"}])
    j = _cliente().get(f"/os/os/{WID}/anexos").get_json()
    assert j["por_tarefa"] == {str(T1): 1} and j["os"] == 2
    assert j["arquivos_por_tarefa"] == {str(T2): 2}

"""A nota da OS no Fracttal quando o motivo é escolhido (20/10/2026, Levi: "quando selecionar o motivo vai preencher na
nota da OS a data, o nome da tarefa, o ativo e o motivo de não fazer a tarefa").

O Nexus escreve nas marcas feitas nele (a janela do Quadro e o Painel do Fora da programação), com o login do Fracttal de
quem marcou (a sessão do OS Creator da pessoa); a justificativa do técnico, o App escreve com o login dele. A linha vai
no FIM da nota (o que já existe fica). Nada aqui vai ao Fracttal: o `api` é de mentira."""
from datetime import datetime, timezone

import pytest

from nexus.pcm import motivos as M
from nexus.pcm import nota_os as NO
from test_pcm_motivos import _mid, tela  # noqa: F401 (fixture)
from test_pcm_publicar import _no_setor, _pessoa


def test_a_linha_da_nota():
    q = datetime(2026, 10, 20, 17, 32, tzinfo=timezone.utc)                      # 14:32 de Brasília
    assert NO.linha(q, "Aguardando material", "[Grid Co.] - MPM - Trafo", "UFV1-TR01", " sem o fusível ") == (
        "20/10/2026 14:32 · Fora da programação: Aguardando material\n"
        "Tarefa: [Grid Co.] - MPM - Trafo · Ativo: UFV1-TR01\n"
        "Observação: sem o fusível")
    # a marca da tarefa em todos os ativos da OS, e sem observação
    assert NO.linha(q, "Prioridade", "Troca de fusível", "", "") == (
        "20/10/2026 14:32 · Fora da programação: Prioridade\nTarefa: Troca de fusível · Ativo: todos os ativos da OS")


def test_a_linha_vai_no_fim_da_nota():
    assert NO.juntar("Nota do supervisor", "linha nova") == "Nota do supervisor\n\nlinha nova"
    assert NO.juntar("  ", "linha nova") == "linha nova" and NO.juntar(None, "linha nova") == "linha nova"
    assert NO.juntar("None", "linha nova") == "linha nova"                      # o RPC às vezes manda o texto "None"


class ApiFalsa:
    """O `api` do OS Creator de mentira: a OS 4321 (id 99) com a nota "Nota antiga"."""
    RPC_WO_TASKS = "tasks.work_orders_tasks_new_list"

    class SessionExpired(Exception):
        pass

    def __init__(self, nota="Nota antiga", recusa=None):
        self.nota, self.recusa, self.gravadas = nota, recusa, []

    def _wo_id_por_folio(self, folio):
        return 99 if str(folio) == "4321" else None

    def _rpc_call(self, metodo, params):
        assert metodo == self.RPC_WO_TASKS and params["id_work_order"] == 99
        return {"data": [{"id": 1, "note": self.nota, "id_assigned_user": 7}]}

    def editar_nota_os(self, wid, nota):
        if self.recusa:
            return {"ok": False, "erro": self.recusa}
        self.gravadas.append((wid, nota))
        return {"ok": True, "nota": nota}


def test_escrever_le_a_nota_e_acrescenta():
    api = ApiFalsa()
    assert NO.gravar(api, "4321", "linha nova") == {"ok": True}
    assert api.gravadas == [(99, "Nota antiga\n\nlinha nova")]
    assert NO.gravar(api, "555", "linha nova") == {"ok": False, "erro": "não achei a OS 555 no Fracttal"}
    r = NO.gravar(ApiFalsa(recusa="Esta OS já está concluída"), "4321", "x")
    assert r == {"ok": False, "erro": "Esta OS já está concluída"}


@pytest.fixture
def notas(monkeypatch):
    """As notas que o Nexus mandaria ao Fracttal: (OS, texto)."""
    feitas = []
    monkeypatch.setattr(NO, "escrever", lambda app, folio, texto: feitas.append((folio, texto)) or {"ok": True})
    monkeypatch.setattr(M, "_agora", lambda: datetime(2026, 10, 20, 17, 32, tzinfo=timezone.utc))
    return feitas


def test_a_janela_do_quadro_escreve_a_nota_ao_escolher_o_motivo(app, tela, notas, monkeypatch):
    c = _pessoa(app)
    _no_setor(monkeypatch, "pcm")
    am, pr = _mid(app.config, "Aguardando material"), _mid(app.config, "Prioridade")
    marca = {"semana": "2026-W41", "os": "5", "tarefa": "[Grid Co.] - MPM - Trafo", "codigo": "UFV1-TR01",
             "motivo_id": am, "obs": "sem o fusível"}
    r = c.post("/t/pcm/quadro/motivo", json=marca).get_json()
    assert r["ok"] and r["nota"] == {"ok": True}
    assert notas == [("5", "20/10/2026 14:32 · Fora da programação: Aguardando material\n"
                           "Tarefa: [Grid Co.] - MPM - Trafo · Ativo: UFV1-TR01\nObservação: sem o fusível")]
    # só a observação mudou: não é escolher o motivo, a nota não ganha linha
    r = c.post("/t/pcm/quadro/motivo", json=dict(marca, obs="sem o fusível, pedido feito")).get_json()
    assert r["ok"] and r["nota"] is None and len(notas) == 1
    # trocar o motivo escreve de novo; tirar, não
    assert c.post("/t/pcm/quadro/motivo", json=dict(marca, motivo_id=pr)).get_json()["nota"] == {"ok": True}
    assert len(notas) == 2 and "Fora da programação: Prioridade" in notas[1][1]
    assert c.post("/t/pcm/quadro/motivo", json=dict(marca, tirar=True)).get_json()["nota"] is None
    assert len(notas) == 2


def test_o_painel_escreve_a_nota_ao_trocar_o_motivo(app, tela, notas, monkeypatch):
    c = _pessoa(app)
    _no_setor(monkeypatch, "pcm")
    am, cl = _mid(app.config, "Aguardando material"), _mid(app.config, "Aguardando cliente")
    c.post("/t/pcm/quadro/motivo", json={"semana": "2026-W41", "os": "6", "tarefa": "Troca de fusível", "codigo": "",
                                         "motivo_id": am})
    item = next(k for k, m in M.vigentes(app.config, M.ler(app.config, forcar=True)).items() if m["os"] == "6")
    c.post("/t/pcm/fora-da-programacao/marcar", data={"item": item, "obs": "só a observação"})
    assert len(notas) == 1                                                      # a observação não escreve
    c.post("/t/pcm/fora-da-programacao/marcar", data={"item": item, "motivo_id": cl})
    assert len(notas) == 2 and "Fora da programação: Aguardando cliente" in notas[1][1]
    assert "Ativo: todos os ativos da OS" in notas[1][1]
    html = c.get("/t/pcm/fora-da-programacao").get_data(as_text=True)
    assert "Nota da OS escrita no Fracttal." in html


def test_sem_o_login_do_fracttal_a_nota_nao_sai_e_a_marca_vale(app, tela, monkeypatch):
    """O administrador pela senha não tem a sessão do Fracttal: a marca grava e a resposta diz que a nota não saiu."""
    from conftest import SENHA_TESTE
    c = app.test_client()
    c.post("/entrar", data={"senha": SENHA_TESTE})
    am = _mid(app.config, "Aguardando material")
    r = c.post("/t/pcm/quadro/motivo", json={"semana": "2026-W41", "os": "6", "tarefa": "Troca de fusível",
                                             "codigo": "", "motivo_id": am}).get_json()
    assert r["ok"] and r["gravou"] and r["nota"]["ok"] is False and "login do Fracttal" in r["nota"]["erro"]

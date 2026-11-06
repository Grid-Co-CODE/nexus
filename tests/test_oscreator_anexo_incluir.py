"""Incluir anexo numa OS que já existe (Levi, 06/11/2026: "poderia incluir um botão de incluir anexo? Aí incluiria um anexo
na OS e será possível ver o anexo e baixar os anexos conforme já temos quando clicamos na OS no histórico de OS"), no card
da OS e nas páginas da OS (a da Engenharia e a do chamado de Garantias).

A rota usa as regras e o envio dos anexos da Solicitação de Engenharia, em produção desde 29/10/2026
(`solic_eng_web.anexos` e `solic_eng_web.anexar`), e acrescenta o que uma OS existente pede: o nome que já está na OS
ganha " (2)" (a chave no S3 é `.ot/<OS>/<nome>`, e o novo apagaria o antigo) e, depois do envio, os anexos são relidos: o
que não aparece na OS não subiu (o Fracttal aceita calado). O Fracttal daqui é de mentira; nenhum teste vai à rede."""
import io
import sys

import pytest

from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
from os_web import criar_app  # noqa: E402

JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira
WID, TAREFA = 9101, 70001
PDF = b"%PDF-1.4\n% laudo de teste\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
EXE = b"MZ\x90\x00" + b"0" * 32


class Fracttal:
    """A OS com um anexo antigo (laudo.pdf); o envio entra na lista, menos o que `calado` diz que o Fracttal engoliu."""

    def __init__(self):
        self.oss = [{"value": f".ot/{WID}/laudo.pdf", "nome": "laudo.pdf", "is_image": False, "is_text": False}]
        self.enviados, self.calado = [], set()

    def subir(self, wid, tid, dados, nome):
        self.enviados.append((wid, tid, nome, dados))
        if nome not in self.calado:
            self.oss.append({"value": f".ot/{wid}/{nome}", "nome": nome, "is_image": nome.endswith(".png"),
                             "is_text": False})
        return {"ok": True, "value": f".ot/{wid}/{nome}"}


@pytest.fixture
def fracttal(monkeypatch):
    f = Fracttal()
    monkeypatch.setattr(api, "_ids_tarefas_da_os", lambda wid: [TAREFA])
    monkeypatch.setattr(api, "attach_imagem_os", f.subir)
    monkeypatch.setattr(api, "get_os_anexos", lambda wid: [dict(a) for a in f.oss])
    monkeypatch.setattr(api, "get_os_subtarefa_anexos", lambda wid: [])
    return f


def _cliente():
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Pessoa Teste", "email": "teste@exemplo.invalid", "perfil": ""}
    return c


def _enviar(c, *arquivos, folio="15900"):
    dados = {"folio": folio, "anexos": [(io.BytesIO(b), n) for n, b in arquivos]}
    return c.post(f"/os/api/os/{WID}/anexos", data=dados, content_type="multipart/form-data")


def test_inclui_o_pdf_e_a_foto_na_tarefa_da_os(fracttal):
    r = _enviar(_cliente(), ("relatorio.pdf", PDF), ("foto.png", PNG))
    j = r.get_json()
    assert r.status_code == 200 and j["ok"] and sorted(j["incluidos"]) == ["foto.png", "relatorio.pdf"]
    assert {(w, t, n) for w, t, n, _ in fracttal.enviados} == {(WID, TAREFA, "relatorio.pdf"), (WID, TAREFA, "foto.png")}
    assert "2 anexos incluídos na OS 15900" in j["mensagem"]


def test_o_nome_que_ja_esta_na_os_ganha_um_numero(fracttal):
    j = _enviar(_cliente(), ("laudo.pdf", PDF)).get_json()
    assert j["incluidos"] == ["laudo (2).pdf"] and fracttal.enviados[0][2] == "laudo (2).pdf"


def test_arquivo_que_nao_e_o_que_diz_e_recusado_sem_ir_ao_fracttal(fracttal):
    r = _enviar(_cliente(), ("planilha.pdf", EXE))
    assert r.status_code == 400 and "Nenhum anexo foi incluído" in r.get_json()["erro"] and not fracttal.enviados


def test_sem_arquivo_e_recusado(fracttal):
    r = _enviar(_cliente())
    assert r.status_code == 400 and not fracttal.enviados


def test_o_que_o_fracttal_engoliu_calado_e_dito_como_falha(fracttal):
    fracttal.calado = {"foto.png"}
    j = _enviar(_cliente(), ("relatorio.pdf", PDF), ("foto.png", PNG)).get_json()
    assert j["incluidos"] == ["relatorio.pdf"] and [f["nome"] for f in j["falhas"]] == ["foto.png"]
    assert not j["ok"] and "foto.png" in j["mensagem"]


def test_sem_a_sessao_do_fracttal_pede_o_login(fracttal):
    c = criar_app(segredo="teste", testing=True).test_client()
    r = _enviar(c, ("relatorio.pdf", PDF))
    assert r.status_code == 401 and not fracttal.enviados


# ── Enviar para verificação (06/11/2026): o status 2 pelo `api.mudar_status_os`, só da OS em processo, lido de volta ──
class Status:
    def __init__(self, inicial=1, calado=False):
        self.st, self.calado, self.pedidos = inicial, calado, []

    def ler(self, wid):
        return self.st

    def mudar(self, wid, st):
        self.pedidos.append((wid, st))
        if not self.calado:
            self.st = st
        return {"ok": True, "status": "Em Verificação"}


def _verificar(monkeypatch, s, ajustes=None):
    from os_web import rotas_acomp
    monkeypatch.setattr(api, "status_da_os", s.ler)
    monkeypatch.setattr(api, "mudar_status_os", s.mudar)
    monkeypatch.setattr(rotas_acomp, "_ajustar", lambda wid, campos=None, ticket=None: (ajustes if ajustes is not None else []).append((wid, campos)))
    return _cliente().post(f"/os/api/os/{WID}/verificacao", json={"folio": "15900"})


def test_a_os_em_processo_vai_para_verificacao_e_o_quadro_de_garantias_sabe(monkeypatch):
    s, ajustes = Status(1), []
    r = _verificar(monkeypatch, s, ajustes)
    assert r.status_code == 200 and "OS 15900 enviada para verificação" in r.get_json()["mensagem"]
    assert s.pedidos == [(WID, 2)] and ajustes == [(WID, {"status_id": 2, "status": "Em Verificação"})]


def test_a_os_que_nao_esta_em_processo_nao_vai(monkeypatch):
    s = Status(3)
    r = _verificar(monkeypatch, s)
    assert r.status_code == 400 and "concluída" in r.get_json()["erro"] and not s.pedidos


def test_o_fracttal_que_aceita_calado_e_dito(monkeypatch):
    r = _verificar(monkeypatch, Status(1, calado=True))
    assert r.status_code == 502 and "seguiu em processo" in r.get_json()["erro"]


def test_o_anexo_vai_para_a_tarefa_escolhida(fracttal, monkeypatch):
    # "Botão de anexar na tarefa" (06/11/2026): com `tarefa`, o anexo vai para ela, que tem de ser da OS
    monkeypatch.setattr(api, "_ids_tarefas_da_os", lambda wid: [TAREFA, 70002])
    c = _cliente()
    dados = {"folio": "15900", "tarefa": "70002", "anexos": [(io.BytesIO(PDF), "laudo-inv2.pdf")]}
    r = c.post(f"/os/api/os/{WID}/anexos", data=dados, content_type="multipart/form-data")
    assert r.status_code == 200 and fracttal.enviados[0][:3] == (WID, 70002, "laudo-inv2.pdf")
    dados["tarefa"], dados["anexos"] = "99999", [(io.BytesIO(PDF), "x.pdf")]
    assert c.post(f"/os/api/os/{WID}/anexos", data=dados, content_type="multipart/form-data").status_code == 404


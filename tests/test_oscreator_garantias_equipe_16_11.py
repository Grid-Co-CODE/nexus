"""A equipe de chamados pela tela do Garantias (16/11/2026, Levi: "passe todas as OSs para a responsável"; no quiz, "as
abertas e as novas"). O administrador do Nexus escolhe a pessoa (a escolha mora na pasta de dados e vence o .env) e passa
os chamados abertos do quadro para ela, por trás, uma OS por vez. Fracttal e banco FALSOS (os do teste de 28/10); nomes e
números de mentira: o repositório é público."""
import json
import os

import pytest
from test_oscreator_garantias_28_10 import tela  # noqa: F401 — a fixture é usada pelo nome

import api  # noqa: E402 — o api.py do clone (o sys.path vem do módulo acima)
from os_web import acomp_equipe as AE  # noqa: E402
from os_web import acomp_web as aw  # noqa: E402

ADMIN, NAO_ADMIN = {"os_web.admin_nexus": True}, {"os_web.admin_nexus": False}


@pytest.fixture(autouse=True)
def limpo():
    AE.configurar_pasta(None)
    with AE._TRAVA:
        AE._ESTADO["lote"] = {"rodando": False, "total": 0, "feitas": 0, "erros": [], "para": "", "inicio": "", "fim": ""}
    yield
    AE.configurar_pasta(None)


def test_a_escolha_da_tela_vence_o_env_e_volta_do_disco(monkeypatch, tmp_path):
    monkeypatch.setenv("OS_WEB_CHAMADO_RESP_ID", "4242")
    monkeypatch.setenv("OS_WEB_CHAMADO_RESP_NOME", "Equipe do Env")
    assert aw.equipe() == (4242, "Equipe do Env")              # sem a escolha, o .env, como sempre
    AE.configurar_pasta(str(tmp_path))
    AE.gravar(77, "  Pessoa   Nova ", quem="Admin Teste")
    assert aw.equipe() == (77, "Pessoa Nova")
    assert json.load(open(os.path.join(tmp_path, AE.ARQUIVO), encoding="utf-8"))["id"] == 77
    AE.configurar_pasta(str(tmp_path))                          # o reinício: a escolha volta do arquivo
    assert aw.equipe() == (77, "Pessoa Nova")
    with pytest.raises(ValueError):
        AE.gravar("", "Sem id")


def test_so_as_abertas_que_nao_estao_com_a_pessoa():
    cards = [{"id": 1, "folio": "1", "col": "chegou", "status_id": 1, "responsavel": "Outra Pessoa"},
             {"id": 2, "folio": "2", "col": "ticket", "status_id": 1, "responsavel": "pessoa  nova"},   # já é dela
             {"id": 3, "folio": "3", "col": "ticket", "status_id": 2, "responsavel": "Outra Pessoa"},
             {"id": 4, "folio": "4", "col": "fim", "status_id": 3, "responsavel": "Outra Pessoa"},      # finalizada
             {"id": None, "folio": "5", "col": "ticket", "status_id": 1, "responsavel": "Outra Pessoa"}]
    assert [c["id"] for c in AE.a_passar(cards, "Pessoa Nova")] == [1, 3]


def test_a_passagem_segue_depois_de_uma_falha():
    cards = [{"id": i, "folio": str(900 + i)} for i in (1, 2, 3)]

    def mudar(wid, idp):
        if wid == 2:
            raise api.FracttalError("Recusado")
        return {"ok": True}
    assert AE.comecar(3, "Pessoa Nova") and not AE.comecar(3, "Pessoa Nova")     # não começa outro por cima
    r = AE.passar(cards, 77, mudar, pausa=0)
    assert (r["rodando"], r["total"], r["feitas"]) == (False, 3, 2)
    assert r["erros"] == [{"os": "902", "erro": "FracttalError: Recusado"}] and r["fim"]


def test_so_o_administrador_ve_e_troca(tela, monkeypatch):
    c, _, _ = tela
    assert "data-equipe>" in c.get("/os/chamados/acompanhamento", environ_overrides=ADMIN).get_data(as_text=True)
    assert "data-equipe>" not in c.get("/os/chamados/acompanhamento", environ_overrides=NAO_ADMIN).get_data(as_text=True)
    assert "data-equipe>" not in c.get("/os/chamados/acompanhamento").get_data(as_text=True)    # o OS Creator sozinho
    r = c.post("/os/api/acomp/equipe", json={"id_personnel": 77, "nome": "Pessoa Nova"}, environ_overrides=NAO_ADMIN)
    assert r.status_code == 403 and AE.atual() is None
    assert c.get("/os/api/acomp/equipe", environ_overrides=NAO_ADMIN).get_json()["pode"] is False


def test_gravar_e_passar_as_abertas(tela, monkeypatch):
    c, _, rotas_acomp = tela
    trocas = []
    monkeypatch.setattr(api, "mudar_responsavel", lambda wid, idp, nota=None: trocas.append((wid, idp)) or {"ok": True})
    monkeypatch.setattr(rotas_acomp, "_em_segundo_plano", lambda fn: fn())         # por trás, aqui na hora
    monkeypatch.setattr(AE, "PAUSA_S", 0)
    monkeypatch.setattr(AE.time, "sleep", lambda s: None)
    r = c.post("/os/api/acomp/equipe", json={"id_personnel": 77, "nome": "Pessoa Nova", "passar": True},
               environ_overrides=ADMIN)
    j = r.get_json()
    assert r.status_code == 200 and j["passar"] == 3 and "Pessoa Nova" in j["mensagem"]
    assert sorted(trocas) == [(1, 77), (2, 77), (3, 77)]                           # a 9104 é finalizada: fica
    g = c.get("/os/api/acomp/equipe", environ_overrides=ADMIN).get_json()
    assert (g["id"], g["nome"], g["pela_tela"], g["pode"]) == (77, "Pessoa Nova", True, True)
    assert (g["lote"]["feitas"], g["lote"]["rodando"]) == (3, False)
    # sem o "passar", só grava a pessoa (as novas nascem no nome dela)
    trocas.clear()
    r = c.post("/os/api/acomp/equipe", json={"id_personnel": 78, "nome": "Outra"}, environ_overrides=ADMIN)
    assert r.get_json()["passar"] == 0 and trocas == [] and aw.equipe() == (78, "Outra")

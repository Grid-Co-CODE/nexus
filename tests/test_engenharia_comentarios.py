"""Os comentários da Engenharia (Levi, 30/10/2026): "só pode comentar com OS criada! Para as que foram acompanhadas e não
tem OS quando a pessoa for comentar deve aparecer 'gerar OS'"; "tem que ter como apagar ou editar esse comentário! tanto
aí quanto no quadro da equipe!". O livro só acrescenta: editar e apagar são eventos novos que apontam o comentário
(`alvo_id`), e a linha da nota da OS no Fracttal muda junto. Banco falso (tests/pg_falso.py) e Fracttal falso; os nomes
são fictícios."""
from datetime import datetime, timedelta, timezone

import pytest
from pg_falso import ApiPGFalsa

from nexus.cadastro.cifra import gerar_chave
from nexus.engenharia import acompanhamento as AC
from nexus.engenharia import os_acompanhamento as O

BRT = timezone(timedelta(hours=-3))
ANA = {"email": "ana.lima@gridco.com.br", "nome": "Ana Lima"}
BETO = {"email": "beto.souza@gridco.com.br", "nome": "Beto Souza"}
SINAL = {"cod": "ALF100-INVR1.3", "usina_id": 7, "usina_ligada_por": "de-para do Fracttal", "nivel": "critico",
         "nFalha": 4, "n7": 2}
OS_ = {"wid": 39550452, "folio": "16502", "codigo": "ALF100-INVR1.3", "usina_id": 7,
       "usina_ligada_por": "de-para do Fracttal"}


@pytest.fixture
def banco(app):
    app.config.update(GRIDCO_DB_API="http://pg.falso", NEXUS_CHAVE_CADASTRO=gerar_chave(),
                      NEXUS_PESSOA_HMAC="hmac-teste", GRIDCO_SQL_TOKEN="tk")
    api = ApiPGFalsa()
    app.extensions["nexus_dados_sessao"] = api
    AC.limpar()
    O.limpar()
    with app.app_context():
        yield api
    AC.limpar()
    O.limpar()
    app.extensions.pop("nexus_dados_sessao", None)


def _acomp():
    (a,) = AC.estado(AC.ler(forcar=True)["eventos"]).values()
    return a


# ── o livro do acompanhamento ───────────────────────────────────────────────────────────────────────────────────────
def test_a_coluna_alvo_entra_no_fim_dos_dois_livros():
    assert AC.CAB_EVENTO[-1] == "alvo_id" and AC.CAB_EVENTO[-3:-1] == ("os_id", "os_folio")
    assert O.CAB[-1] == "alvo_id" and O.CAB[-3:-1] == ("origem", "origem_id")


def test_editar_e_apagar_o_comentario_do_acompanhamento(banco):
    AC.pegar(SINAL, ANA, True, os={"id": 39001, "folio": "12345"})
    aid = _acomp()["id"]
    c = AC.comentar(aid, "Medir o isolamento", ANA, True, linha_nota="[30/10/2026 09:00] Ana Lima (Engenharia): Medir")
    (com,) = _acomp()["comentarios"]
    assert com["id"] == c["id"] and com["linha_nota"].startswith("[30/10/2026 09:00]") and com["hmac"] == AC.codigo(ANA)
    AC.editar_comentario(aid, c["id"], "Medir o isolamento CC", ANA, True, linha_nota="linha nova")
    (com,) = _acomp()["comentarios"]
    assert com["texto"] == "Medir o isolamento CC" and com["editado"] and com["linha_nota"] == "linha nova"
    AC.apagar_comentario(aid, c["id"], ANA, True)
    assert _acomp()["comentarios"] == []
    # nada se apaga do livro: são três eventos
    assert [l["evento"] for l in banco.linhas(AC.LIVRO, AC.ABA_EVENTO)][-3:] == \
        ["comentario", "comentario_editado", "comentario_apagado"]


def test_so_quem_escreveu_ou_o_administrador_muda_o_comentario(banco):
    AC.pegar(SINAL, ANA, True, os={"id": 39001, "folio": "12345"})
    aid = _acomp()["id"]
    c = AC.comentar(aid, "Do Ana", ANA, True)
    with pytest.raises(AC.Recusada, match="quem escreveu"):
        AC.editar_comentario(aid, c["id"], "Mudado", BETO, True)
    with pytest.raises(AC.Recusada, match="quem escreveu"):
        AC.apagar_comentario(aid, c["id"], BETO, True)
    AC.apagar_comentario(aid, c["id"], BETO, True, admin=True)
    assert _acomp()["comentarios"] == []
    with pytest.raises(AC.Recusada, match="Não achei"):
        AC.apagar_comentario(aid, c["id"], ANA, True)


def test_gerar_os_no_acompanhamento_sem_os(banco):
    AC.pegar(SINAL, ANA, True)
    aid = _acomp()["id"]
    assert _acomp()["os_id"] is None
    AC.gerar_os(aid, {"id": 39002, "folio": "12346"}, BETO, True)
    a = _acomp()
    assert a["os_id"] == 39002 and a["os_folio"] == "12346" and a["responsavel"]["nome"] == "Ana Lima"
    with pytest.raises(AC.Recusada, match="já tem a OS 12346"):
        AC.gerar_os(aid, {"id": 39003, "folio": "12347"}, BETO, True)


# ── o livro da OS (a página da OS do Quadro da equipe) ──────────────────────────────────────────────────────────────
def test_editar_e_apagar_o_comentario_da_os(banco):
    c = O.registrar_comentario(OS_, "Trocar o cabo", ANA, True, "sim", linha_nota="[24/10/2026 10:00] Ana Lima "
                                                                                 "(Engenharia): Trocar o cabo")
    est = O.estado(O.ler(forcar=True)["eventos"])["39550452"]
    (ev,) = est["eventos"]
    assert ev["id"] == c["id"] and ev["linha_nota"].endswith("Trocar o cabo")
    O.editar_comentario(OS_, c["id"], "Trocar o cabo de rede", ANA, True, nota="sim", linha_nota="nova")
    (ev,) = O.estado(O.ler(forcar=True)["eventos"])["39550452"]["eventos"]
    assert ev["texto"] == "Trocar o cabo de rede" and ev["editado"]
    assert O.comentarios_por_os(O.ler(forcar=True)["eventos"]) == {"39550452": 1}
    O.apagar_comentario(OS_, c["id"], ANA, True)
    assert O.estado(O.ler(forcar=True)["eventos"])["39550452"]["eventos"] == []
    assert O.comentarios_por_os(O.ler(forcar=True)["eventos"]) == {}
    with pytest.raises(O.Recusada, match="quem escreveu"):
        c2 = O.registrar_comentario(OS_, "Outro", ANA, True, "sim")
        O.editar_comentario(OS_, c2["id"], "x", BETO, True)


# ── a ponte: comentar só com OS, Gerar OS, editar e apagar com a linha da nota ──────────────────────────────────────
from test_engenharia_acompanhamento import SAME, _aid_de, _como, tela  # noqa: E402,F401
from test_engenharia_os_analise import ApiFalsa  # noqa: E402
from test_engenharia_os_quadro import _login_do_fracttal  # noqa: E402

PONTE = "/os/_nexus/engenharia/acompanhamento"


@pytest.fixture
def fracttal(tela, app, monkeypatch):
    pytest.importorskip("PyQt6")
    from nexus.torres.oscreator import ponte as P
    P.clone(app)
    import api as os_api
    monkeypatch.setattr(AC, "pessoas_da_engenharia", lambda: [
        {"hmac": AC.codigo(ANA), "nome": "Ana Lima", "fid": "11"},
        {"hmac": AC.codigo(BETO), "nome": "Beto Souza", "fid": "12"}])
    falso = ApiFalsa()
    for nome in ("_label_id", "_classif_ids", "create_work_orders_bulk", "id_tarefa_da_os", "subtarefas_da_tarefa",
                 "salvar_subtarefas", "registrar_execucao", "concluir_os_analise", "mudar_responsavel", "status_da_os",
                 "execucoes_da_tarefa"):
        monkeypatch.setattr(os_api, nome, getattr(falso, nome))
    falso.nota, falso.escritas = "Nota antiga", []
    monkeypatch.setattr(os_api, "get_os_detalhes", lambda wid: {"notas": falso.nota, "tarefas": [{"id": 1}],
                                                               "cancel_motivo": "", "cancel_nota": ""})

    def editar(wid, nota):
        falso.escritas.append((wid, nota))
        falso.nota = nota
        return {"ok": True}
    monkeypatch.setattr(os_api, "editar_nota_os", editar)
    P._OS_SEM_LIVRO.clear()
    yield falso
    P._OS_SEM_LIVRO.clear()


def _post(cliente, caminho, **dados):
    return cliente.post(PONTE + caminho, data=dados, headers=SAME)


def test_comentar_sem_os_pede_para_gerar_a_os(fracttal, tela, cliente, app):
    _como(cliente, ANA)
    _login_do_fracttal(app, cliente)
    aid = _aid_de("IBI200-INVR1.3")                          # o acompanhamento de antes, sem OS
    html = _post(cliente, f"/{aid}/comentar", cod="IBI200-INVR1.3", texto="Sem OS").get_data(as_text=True)
    assert "gere a OS" in html and AC.estado(AC.ler(forcar=True)["eventos"])[aid]["comentarios"] == []
    # a gaveta do acompanhamento sem OS mostra o Gerar OS no lugar do campo do comentário
    assert "Gerar OS" in html and 'name="texto"' not in html


def test_gerar_os_cria_no_nome_de_quem_acompanha(fracttal, tela, cliente, app):
    _como(cliente, BETO)
    _login_do_fracttal(app, cliente)
    aid = _aid_de("IBI200-INVR1.3")                          # com Ana Lima
    html = _post(cliente, f"/{aid}/gerar-os", cod="IBI200-INVR1.3").get_data(as_text=True)
    assert "OS 12345" in html and 'name="texto"' in html
    (_, assets, _t, _tp, subs, k), = [c for c in fracttal.chamadas if c[0] == "criar"]
    assert assets == ["IBI200-INVR1.3"] and subs == ["Diagnóstico"] and k["id_responsible"] == 11
    assert "Beto Souza" in k["note"] and "Ana Lima" in k["note"]
    assert AC.estado(AC.ler(forcar=True)["eventos"])[aid]["os_folio"] == "12345"


def _com_os_e_um_comentario(cliente, app, texto="Medir o isolamento"):
    _como(cliente, ANA)
    _login_do_fracttal(app, cliente)
    _post(cliente, "/pegar", cod="IBI200-INV02")
    aid = _aid_de("IBI200-INV02")
    _post(cliente, f"/{aid}/comentar", cod="IBI200-INV02", texto=texto)
    (c,) = AC.estado(AC.ler(forcar=True)["eventos"])[aid]["comentarios"]
    return aid, c


def test_editar_o_comentario_troca_a_linha_na_nota_da_os(fracttal, tela, cliente, app):
    aid, c = _com_os_e_um_comentario(cliente, app)
    assert c["linha_nota"] in fracttal.nota
    html = _post(cliente, f"/{aid}/comentario/{c['id']}/editar", cod="IBI200-INV02",
                 texto="Medir o isolamento CC").get_data(as_text=True)
    assert "Comentário editado" in html and "Medir o isolamento CC" in html
    linhas = fracttal.nota.split("\n")
    assert linhas[0] == "Nota antiga" and len(linhas) == 2 and linhas[1].endswith("Medir o isolamento CC (editado)")


def test_apagar_o_comentario_tira_a_linha_da_nota_da_os(fracttal, tela, cliente, app):
    aid, c = _com_os_e_um_comentario(cliente, app)
    html = _post(cliente, f"/{aid}/comentario/{c['id']}/apagar", cod="IBI200-INV02").get_data(as_text=True)
    assert "Comentário apagado" in html and fracttal.nota == "Nota antiga"
    assert AC.estado(AC.ler(forcar=True)["eventos"])[aid]["comentarios"] == []


def test_a_linha_que_mudou_no_fracttal_fica_e_o_nexus_diz(fracttal, tela, cliente, app):
    aid, c = _com_os_e_um_comentario(cliente, app)
    fracttal.nota = "Nota antiga\nalguém reescreveu a nota no Fracttal"
    html = _post(cliente, f"/{aid}/comentario/{c['id']}/apagar", cod="IBI200-INV02").get_data(as_text=True)
    assert "Comentário apagado" in html and "não está mais na nota" in html
    assert fracttal.nota == "Nota antiga\nalguém reescreveu a nota no Fracttal"


def test_outra_pessoa_nao_ve_os_botoes_nem_muda(fracttal, tela, cliente, app):
    aid, c = _com_os_e_um_comentario(cliente, app)
    _como(cliente, BETO)
    html = _post(cliente, f"/{aid}/comentario/{c['id']}/apagar", cod="IBI200-INV02").get_data(as_text=True)
    assert "quem escreveu" in html and AC.estado(AC.ler(forcar=True)["eventos"])[aid]["comentarios"]
    assert "Medir o isolamento" in fracttal.nota
    gav = cliente.get("/t/engenharia/confiabilidade?aba=acompanhamento").get_data(as_text=True)
    assert f"/comentario/{c['id']}/apagar" not in gav


def test_os_botoes_de_quem_escreveu_na_gaveta(fracttal, tela, cliente, app):
    aid, c = _com_os_e_um_comentario(cliente, app)
    gav = cliente.get("/t/engenharia/confiabilidade?aba=acompanhamento").get_data(as_text=True)
    assert f"{PONTE}/{aid}/comentario/{c['id']}/editar" in gav and f"{PONTE}/{aid}/comentario/{c['id']}/apagar" in gav


# ── a página da OS do Quadro da equipe ──────────────────────────────────────────────────────────────────────────────
def test_editar_e_apagar_na_pagina_da_os(fracttal, tela, cliente, app, monkeypatch):
    from nexus.engenharia import os_equipe
    o = {"os": "16502", "wid": 39550452, "codigo": "ALF100-INVR1.3", "nota": "", "status": "", "usina_id": 7,
         "usina": "Cliente X - Usina Teste 1 - SP"}
    monkeypatch.setattr(os_equipe, "ler_os", lambda folio: dict(o))
    _como(cliente, ANA)
    _login_do_fracttal(app, cliente)
    url = "/os/_nexus/engenharia/os/39550452"
    r = cliente.post(url + "/comentar", json={"texto": "Trocar o cabo", "folio": "16502"}, headers=SAME)
    assert r.status_code == 200 and "Trocar o cabo" in fracttal.nota
    (ev,) = O.estado(O.ler(forcar=True)["eventos"])["39550452"]["eventos"]
    r = cliente.post(f"{url}/comentario/{ev['id']}/editar", json={"texto": "Trocar o cabo de rede", "folio": "16502"},
                     headers=SAME)
    assert r.status_code == 200 and r.get_json()["ok"] and fracttal.nota.endswith("Trocar o cabo de rede (editado)")
    r = cliente.post(f"{url}/comentario/{ev['id']}/apagar", json={"folio": "16502"}, headers=SAME)
    assert r.status_code == 200 and fracttal.nota == "Nota antiga"
    assert O.estado(O.ler(forcar=True)["eventos"])["39550452"]["eventos"] == []
    _como(cliente, BETO)
    c2 = O.registrar_comentario(dict(OS_), "Do Ana", ANA, True, "sim")
    r = cliente.post(f"{url}/comentario/{c2['id']}/apagar", json={"folio": "16502"}, headers=SAME)
    assert r.status_code == 400 and "quem escreveu" in r.get_json()["erro"]


def test_o_comentario_digitado_volta_quando_o_livro_falha(fracttal, tela, cliente, app, monkeypatch):
    import requests

    from nexus.dados import livros
    _como(cliente, ANA)
    _login_do_fracttal(app, cliente)
    _post(cliente, "/pegar", cod="IBI200-INV02")
    aid = _aid_de("IBI200-INV02")
    monkeypatch.setattr(livros, "publicar", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("fora")))
    html = _post(cliente, f"/{aid}/comentar", cod="IBI200-INV02", texto="Trocar o cabo de rede").get_data(as_text=True)
    assert "não gravou" in html and ">Trocar o cabo de rede</textarea>" in html


def test_comentario_de_varias_linhas_sai_inteiro_da_nota(fracttal, tela, cliente, app):
    aid, c = _com_os_e_um_comentario(cliente, app, texto="Primeira linha\nSegunda linha")
    assert fracttal.nota.count("\n") == 2                        # a nota antiga e as duas linhas do comentário
    html = _post(cliente, f"/{aid}/comentario/{c['id']}/editar", cod="IBI200-INV02",
                 texto="Uma linha só").get_data(as_text=True)
    assert "mudou junto" in html
    linhas = fracttal.nota.split("\n")
    assert len(linhas) == 2 and linhas[1].endswith("Uma linha só (editado)") and "Segunda linha" not in fracttal.nota
    (c2,) = AC.estado(AC.ler(forcar=True)["eventos"])[aid]["comentarios"]
    html = _post(cliente, f"/{aid}/comentario/{c2['id']}/apagar", cod="IBI200-INV02").get_data(as_text=True)
    assert "mudou junto" in html and fracttal.nota == "Nota antiga"

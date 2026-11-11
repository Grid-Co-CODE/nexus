"""O Raio X da OS, etapa 1 (Levi, 11/11/2026): o nome na página, o nº da OS que abre o card do Histórico do OS Creator, o
Solicitante nos Dados quando a OS nasceu de uma solicitação e o "Incluir OS" na cadeia, com o nome que a pessoa der, o
Renomear e o Tirar (a incluída aparece só na cadeia da OS em que entrou). Banco e Fracttal de mentira; nomes fictícios."""
import sys

import pytest
from test_engenharia_acompanhamento import ANA, BETO, SAME, _como
from test_engenharia_os_quadro import URL, _secao, banco, pagina  # noqa: F401  (fixtures)

from nexus.cadastro import setor_ids as SID
from nexus.comando import solicitacoes_fracttal as SF
from nexus.dados import catalogo
from nexus.engenharia import cadeia_os as C


@pytest.fixture
def cadeia_limpa():
    C.limpar()
    yield
    C.limpar()


def _cadeia(html):
    return _secao(html, "A cadeia da OS")


def _incluir(cli, numero, **extra):
    return cli.post(URL + "/cadeia", data={"acao": "incluir", "os": numero, **extra}, headers=SAME)


def test_o_nome_da_pagina_e_o_numero_que_abre_o_card(pagina, cliente, cadeia_limpa):
    html = _como(cliente, ANA).get(URL).get_data(as_text=True)
    assert '<p class="eg-ac-raiox">Raio X da OS</p>' in html
    wid = pagina["id_work_order"]
    assert (f'<a class="eg-ac-num" href="/os/os/{wid}" data-os-card data-wid="{wid}" data-folio="16502"') in html
    assert "window.NexusOsCard" in html                                  # o card abre por cima da página


def test_incluir_renomear_e_tirar_da_cadeia(pagina, cliente, banco, cadeia_limpa):
    cli = _como(cliente, ANA)
    html = cli.get(URL).get_data(as_text=True)
    assert 'placeholder="Incluir OS"' in _cadeia(html) and 'maxlength="6"' in _cadeia(html)
    r = _incluir(cli, "16511")
    assert r.status_code == 303 and "OS+16511+inclu" in r.headers["Location"]
    cadeia = _cadeia(cli.get(URL).get_data(as_text=True))
    assert '<li class="incluida"><span class="i">4</span><span class="t">OS incluída</span>' in cadeia   # depois das 2 filhas
    linhas = banco.linhas(C.LIVRO, C.ABA)
    assert [(l["evento"], l["os_folio"], l["incluida_folio"]) for l in linhas] == [("incluiu", "16502", "16511")]
    assert "Ana" not in str(linhas)                                      # quem fez só cifrado
    inc = C.incluidas(C.ler(forcar=True)["eventos"], pagina["id_work_order"])[0]
    cli.post(URL + "/cadeia", data={"acao": "renomear", "id": inc["id"], "rotulo": "Inspeção da cabine"}, headers=SAME)
    cadeia = _cadeia(cli.get(URL).get_data(as_text=True))
    assert '<span class="t">Inspeção da cabine</span>' in cadeia
    assert "Inspeção da cabine" not in str(banco.linhas(C.LIVRO, C.ABA))  # o nome dado também só cifrado
    cli.post(URL + "/cadeia", data={"acao": "tirar", "id": inc["id"]}, headers=SAME)
    assert 'class="incluida"' not in _cadeia(cli.get(URL).get_data(as_text=True))
    assert [l["evento"] for l in banco.linhas(C.LIVRO, C.ABA)] == ["incluiu", "renomeou", "tirou"]


@pytest.mark.parametrize("numero,erro", [("99999", "N%C3%A3o+achei+a+OS+99999"), ("12a", "s%C3%B3+n%C3%BAmeros"),
                                         ("1234567", "s%C3%B3+n%C3%BAmeros"), ("16502", "pr%C3%B3pria+OS")])
def test_o_numero_que_nao_entra(pagina, cliente, cadeia_limpa, numero, erro):
    r = _incluir(_como(cliente, ANA), numero)
    assert r.status_code == 303 and erro in r.headers["Location"]


def test_a_mesma_os_duas_vezes_nao_entra(pagina, cliente, cadeia_limpa):
    cli = _como(cliente, ANA)
    _incluir(cli, "16511")
    assert "j%C3%A1+est%C3%A1+na+cadeia" in _incluir(cli, "16511").headers["Location"]


def test_quem_nao_pode_mexer_ve_a_cadeia_sem_o_campo(pagina, cliente, cadeia_limpa, monkeypatch):
    from nexus.auth import setor_telas as ST
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": set(),
                                               "setor": {"id": SID.PERFORMANCE, "nome": "Performance"}, "erro": ""})
    cli = _como(cliente, BETO)
    assert 'placeholder="Incluir OS"' not in _cadeia(cli.get(URL).get_data(as_text=True))
    r = _incluir(cli, "16511")
    assert r.status_code == 303 and "erro=" in r.headers["Location"] and "ok=" not in r.headers["Location"]


def test_o_solicitante_nos_dados(pagina, cliente, cadeia_limpa, monkeypatch):
    monkeypatch.setattr(SF, "da_os", lambda wid, app=None: {"codigo": "4401", "nome": "Pessoa Solicitante"})
    dados = _secao(_como(cliente, ANA).get(URL).get_data(as_text=True), "Dados")
    assert "<dt data-solicitante>Solicitante</dt><dd data-solicitante>Pessoa Solicitante" in dados
    assert "Solicitação 4401" in dados and dados.index("Criado por") < dados.index("Solicitante")


def test_sem_a_leitura_o_solicitante_pergunta_depois(pagina, cliente, cadeia_limpa):
    dados = _secao(_como(cliente, ANA).get(URL).get_data(as_text=True), "Dados")
    wid = pagina["id_work_order"]
    assert "<dt data-solicitante hidden>Solicitante</dt>" in dados
    assert f'data-solicitante-url="/os/api/os/{wid}/solicitacao"' in dados


def test_a_rota_do_os_creator_diz_quem_pediu(monkeypatch):
    from test_oscreator_anexo_incluir import WID, _cliente

    from nexus.torres.oscreator import ponte
    if ponte.RAIZ_CLONE not in sys.path:
        sys.path.append(ponte.RAIZ_CLONE)
    import api
    monkeypatch.setattr(api, "get_solicitacao_por_os",
                        lambda wid: {"id_code": 4401, "criado_por": "Pessoa Solicitante", "data": "2026-11-10T09:00:00"})
    j = _cliente().get(f"/os/api/os/{WID}/solicitacao").get_json()
    assert (j["codigo"], j["solicitante"]) == (4401, "Pessoa Solicitante")
    monkeypatch.setattr(api, "get_solicitacao_por_os", lambda wid: None)
    assert _cliente().get(f"/os/api/os/{WID}/solicitacao").get_json()["codigo"] == ""


def test_o_livro_da_cadeia_esta_no_catalogo_antes_da_1a_gravacao():
    assert any(f.livro == "nexus_cadeia_os · fato_os_na_cadeia" for f in catalogo.FATOS)
    assert any(lv.nome == "nexus_cadeia_os" for lv in catalogo.LIVROS)

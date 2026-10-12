"""Os responsáveis de cada usina para o filtro da Visão gerencial (Levi, 12/10/2026: "Quero um filtro de responsável ->
Visão gerencial"). O nome da pessoa só existe decifrado no Nexus; a moldura entrega o mapa à tela da plataforma quando ela
pede (nexus/performance/responsaveis.py, porta.js)."""
import pytest

from nexus.performance import responsaveis as R

from test_porta_js import pagina, _dados
from test_porta_moldura import _cliente, _dados as _dados_da_pagina


def test_a_chave_casa_acento_pontuacao_e_romano():
    assert R.chave("Piracicaba I") == R.chave("piracicaba 1") == "piracicaba 1"
    assert R.chave("Céu Azul II (103)") == "ceu azul 2 103"
    assert R.chave("  AP. do   Taboado ") == "ap do taboado"
    assert R.chave(None) == ""


PESSOAS = {"p1": "Ana Supervisora", "p2": "Bruno Gestor", "p3": "Carla Supervisora"}
USINAS = [{"id": 1, "nome": "Primavera 1", "om": "p1", "gestor": "p2"},
          {"id": 2, "nome": "Primavera 2", "om": "p1", "gestor": "p2"},
          {"id": 3, "nome": "Nova Londrina 1", "om": "p1", "gestor": "p2"},
          {"id": 4, "nome": "Nova Londrina 2", "om": "p3", "gestor": "p2"},
          {"id": 5, "nome": "Sem Ninguém", "om": None, "gestor": None}]
DE_PARA = [{"usina_id": 1, "sistema": "BD_Thopen · aba", "chave_externa": "Primavera"},
           {"usina_id": 2, "sistema": "BD_Thopen · aba", "chave_externa": "Primavera"},
           {"usina_id": 3, "sistema": "BD_Performance · Base UFV", "chave_externa": "Nova Londrina"},
           {"usina_id": 4, "sistema": "BD_Performance · Base UFV", "chave_externa": "Nova Londrina"},
           {"usina_id": 1, "sistema": "Fracttal · Classificação 1", "chave_externa": "Thopen - Primavera - PR"}]


def test_o_mapa_casa_pelo_cadastro_e_pelo_de_para_e_so_quando_os_responsaveis_batem():
    m = R.mapa(USINAS, DE_PARA, PESSOAS.get)
    assert m["primavera 1"] == {"om": "Ana Supervisora", "gestor": "Bruno Gestor"}
    assert m["primavera"] == {"om": "Ana Supervisora", "gestor": "Bruno Gestor"}      # 1 e 2 com os mesmos
    assert "nova londrina" not in m                                                 # 1 e 2 com responsáveis diferentes
    assert "sem ninguem" not in m                                                   # usina sem responsável nenhum
    assert "thopen primavera pr" not in m                                           # base fora das do Gerencial


def test_a_moldura_leva_o_mapa_e_sem_cadastro_leva_nada(monkeypatch):
    monkeypatch.setattr(R, "do_cadastro", lambda: {"altair": {"om": "Ana", "gestor": "Bruno"}})
    cli = _cliente()
    h = cli.get("/t/performance/gerencial").get_data(as_text=True)
    assert _dados_da_pagina(h)["responsaveis"] == {"altair": {"om": "Ana", "gestor": "Bruno"}}
    monkeypatch.setattr(R, "do_cadastro", lambda: (_ for _ in ()).throw(RuntimeError("sem banco")))
    h = cli.get("/t/performance/gerencial").get_data(as_text=True)
    assert _dados_da_pagina(h)["responsaveis"] is None                              # a tela segue sem o filtro


MAPA = {"altair": {"om": "Ana", "gestor": "Bruno"}}


def test_a_moldura_responde_so_a_ela_e_so_na_mesma_origem():
    pede = {"tipo": "nexus:pede-responsaveis"}
    feito = pagina(dados=_dados("", responsaveis=MAPA), moldura=True, passos=[{"mensagem": pede}])
    assert feito["respostas"] == [{"mensagem": {"tipo": "nexus:responsaveis", "mapa": MAPA},
                                   "origem": "https://app.exemplo.test"}]
    for passo in ({"mensagem": pede, "de": "outra"}, {"mensagem": pede, "origem": "https://outra.exemplo.test"}):
        assert pagina(dados=_dados("", responsaveis=MAPA), moldura=True, passos=[passo])["respostas"] == []
    feito = pagina(dados=_dados(""), moldura=True, passos=[{"mensagem": pede}])           # sem o mapa: diz que não há
    assert feito["respostas"][0]["mensagem"] == {"tipo": "nexus:responsaveis", "mapa": None}

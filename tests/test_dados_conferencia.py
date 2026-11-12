"""A conferência das ligações: o que está gravado no banco aponta para algo que existe? (12/11/2026)

Levi: "Quero uma análise das relações de dados e se as bases estão sendo lincadas da maneira correta". A medida daquele
dia foi feita à mão, lendo o banco inteiro: nos 19 fatos com IDs, nenhum ID órfão e nenhuma chave repetida, e dois
achados que só ela viu (2.197 OS da FAMA com a data fora do calendário e 3 linhas da programação com um equipamento fora
da dimensão). A qualidade de cada fato mede o que LIGOU ao montar; ninguém conferia depois o que ficou gravado. O banco
é o falso; nomes fictícios.
"""
from datetime import datetime, timedelta, timezone

import pytest
from pg_falso import ApiPGFalsa
from test_campo_visao import _aba

from nexus.dados import conferencia as C

BASE = "http://pg.falso"
CFG = {"GRIDCO_DB_API": BASE, "GRIDCO_SQL_TOKEN": "token-de-teste"}
AGORA = datetime(2026, 11, 12, 3, 30, tzinfo=timezone(timedelta(hours=-3)))


@pytest.fixture
def banco():
    api = ApiPGFalsa()
    _aba(api, "cadastro_nexus", "usinas", [{"usina_id": 1, "cliente_id": 1, "equipe_id": 10, "responsavel_om_id": 7},
                                           {"usina_id": 2, "cliente_id": 9, "equipe_id": None, "responsavel_om_id": None}])
    _aba(api, "cadastro_nexus", "clientes", [{"cliente_id": 1}])
    _aba(api, "cadastro_nexus", "equipes", [{"equipe_id": 10}])
    _aba(api, "cadastro_nexus", "pessoas", [{"pessoa_id": 7, "equipe_id": 10}])
    _aba(api, "nexus_dimensoes", "dim_data", [{"data_id": 20261110}, {"data_id": 20261111}])
    _aba(api, "nexus_equipamentos", "dim_equipamento", [{"equipamento_id": 500, "usina_id": 1},
                                                         {"equipamento_id": 501, "usina_id": None}])
    # o fato com IDs: a API devolve número, texto e "93.0" conforme a aba (a mesma usina 1 de três jeitos)
    _aba(api, "nexus_fatos", "fato_fechamento", [
        {"fechamento_id": "a", "data_id": 20261110, "usina_id": 1, "pessoa_id": 7, "equipamento_id": 500,
         "usina_ligada_por": "de-para do Fracttal", "os": 10},
        {"fechamento_id": "b", "data_id": "20261111", "usina_id": "1.0", "pessoa_id": None, "equipamento_id": "500",
         "usina_ligada_por": "de-para do Fracttal", "os": 11},
        {"fechamento_id": "c", "data_id": 20230814, "usina_id": 77, "pessoa_id": 7, "equipamento_id": 999,
         "usina_ligada_por": None, "os": 12},
        {"fechamento_id": "c", "data_id": 20261110, "usina_id": 77, "pessoa_id": 8, "equipamento_id": None,
         "usina_ligada_por": None, "os": 13}])
    _aba(api, "nexus_dimensoes", "usinas_historico", [
        {"usina_id": 1, "cliente_id": 1, "valido_de_id": 19000101, "valido_ate_id": 99991231}])
    # as famílias por período: só o livro mais novo; a posição das pessoas não é lida
    _aba(api, "nexus_geracao_inversor_2026_10", "fato_geracao_inversor_dia", [{"geracao_id": "x", "usina_id": 404}])
    _aba(api, "nexus_geracao_inversor_2026_11", "fato_geracao_inversor_dia", [
        {"geracao_id": "y", "usina_id": 1, "geracao_usina_id": "não é usina", "fama_tipo_equipe_id": 3}])
    _aba(api, "nexus_equipe_pontos_2026_11_12", "fato_ponto_equipe", [{"ponto_id": "p", "pessoa_id": 404}])
    _aba(api, "bd_thopen", "fato_de_outro_sistema", [{"usina_id": 404}])
    return api


def _por(linhas):
    return {(l[0], l[2]): dict(zip(C.CAB, l)) for l in linhas}


def test_o_id_orfao_e_a_chave_repetida_aparecem(banco):
    linhas, r = C.conferir(BASE, banco, AGORA)
    t = _por(linhas)
    fech = "nexus_fatos · fato_fechamento"
    assert t[(fech, "usina_id")]["orfaos_qtd"] == 2 and t[(fech, "usina_id")]["orfaos_distintos_qtd"] == 1
    assert t[(fech, "usina_id")]["preenchido_qtd"] == 4 and t[(fech, "usina_id")]["linhas"] == 4
    assert t[(fech, "data_id")]["orfaos_qtd"] == 1, "a data de 2023 fora do calendário (o caso da FAMA)"
    assert t[(fech, "pessoa_id")]["orfaos_qtd"] == 1 and t[(fech, "pessoa_id")]["preenchido_qtd"] == 3
    assert t[(fech, "equipamento_id")]["orfaos_qtd"] == 1
    assert t[(fech, C.CHAVE)]["chave_repetida_qtd"] == 1 and t[(fech, C.CHAVE)]["fato"] == "fechamento"
    assert (fech, "usina_ligada_por") not in t and (fech, "os") not in t          # a linhagem e a OS não são ID
    # as dimensões que apontam para outra: a usina 2 com o cliente 9, que não existe; a própria coluna de ID não entra
    assert t[("cadastro_nexus · usinas", "cliente_id")]["orfaos_qtd"] == 1
    assert ("cadastro_nexus · usinas", "usina_id") not in t
    assert t[("nexus_equipamentos · dim_equipamento", "usina_id")]["preenchido_qtd"] == 1
    # o vigente e o início presumido do histórico não são datas do calendário
    assert t[("nexus_dimensoes · usinas_historico", "valido_de_id")]["orfaos_qtd"] == 0
    assert t[("nexus_dimensoes · usinas_historico", "valido_ate_id")]["orfaos_qtd"] == 0
    assert r["orfaos"] == 2 + 1 + 1 + 1 + 1 and r["repetidas"] == 1 and r["erros"] == 0
    assert {(p["tabela"], p["coluna"]) for p in r["problemas"]} >= {(fech, "usina_id"), (fech, C.CHAVE)}


def test_so_o_mes_mais_novo_da_familia_e_nada_da_posicao_das_pessoas(banco):
    linhas, _r = C.conferir(BASE, banco, AGORA)
    tabelas = {l[0] for l in linhas}
    assert "nexus_geracao_inversor_2026_11 · fato_geracao_inversor_dia" in tabelas
    assert "nexus_geracao_inversor_2026_10 · fato_geracao_inversor_dia" not in tabelas
    assert not any("equipe_pontos" in t or t.startswith("bd_thopen") for t in tabelas)
    t = _por(linhas)
    nov = "nexus_geracao_inversor_2026_11 · fato_geracao_inversor_dia"
    assert t[(nov, "usina_id")]["orfaos_qtd"] == 0
    assert (nov, "geracao_usina_id") not in t and (nov, "fama_tipo_equipe_id") not in t   # não são a usina nem a equipe
    assert t[(nov, C.CHAVE)]["fato"] == "geracao_inversor_dia" and t[(nov, C.CHAVE)]["chave_repetida_qtd"] == 0


def test_a_coluna_de_id_pelo_nome():
    alvo = C.alvo_da_coluna
    assert [alvo(c) for c in ("data_id", "data_id_criacao", "usina_id", "usina_id_dona", "pessoa_id",
                              "solicitante_pessoa_id", "pessoa_id_tecnico", "equipe_id", "cliente_id", "equipamento_id")] \
        == ["data", "data", "usina", "usina", "pessoa", "pessoa", "pessoa", "equipe", "cliente", "equipamento"]
    assert [alvo(c) for c in ("usina_ligada_por", "pessoa_hmac", "geracao_usina_id", "fama_tipo_equipe_id",
                              "fracttal_tarefa_id", "os", "tarefa_chave", "")] == [None] * 8


def test_a_tabela_que_nao_le_nao_para_as_outras(banco, monkeypatch):
    real = banco.get
    ruim = banco.abas[("nexus_fatos", "fato_fechamento")]["id"]

    def quebra(url, **kw):
        if url.endswith(f"/api/sheets/{ruim}/rows"):
            raise ConnectionError("o banco caiu nesta aba")
        return real(url, **kw)
    monkeypatch.setattr(banco, "get", quebra)
    linhas, r = C.conferir(BASE, banco, AGORA)
    t = _por(linhas)
    assert t[("nexus_fatos · fato_fechamento", None)]["erro"] == "ConnectionError" and r["erros"] == 1
    assert ("cadastro_nexus · usinas", "cliente_id") in t           # as outras foram conferidas


def test_grava_uma_vez_por_dia_e_a_governanca_le(banco):
    r = C.rodar(CFG, banco, agora=AGORA)
    assert r["orfaos"] == 6 and banco.linhas(C.LIVRO, "atualizacao")[0]["orfaos_qtd"] == 6
    gravadas = banco.linhas(C.LIVRO, C.ABA)
    assert len(gravadas) == len(C.conferir(BASE, banco, AGORA)[0])
    assert not any("ConnectionError" in str(v) for l in gravadas for v in l.values())
    assert C.rodar(CFG, banco, agora=AGORA + timedelta(hours=5)) == {"pulou": "já conferido hoje"}
    assert "pulou" not in C.rodar(CFG, banco, agora=AGORA + timedelta(hours=21))
    assert "pulou" not in C.rodar(CFG, banco, agora=AGORA + timedelta(hours=22), forcar=True)
    assert C.rodar({"GRIDCO_DB_API": BASE}, banco, agora=AGORA)["pulou"].startswith("sem a chave")
    u = C.ultima(BASE, banco)
    assert u["orfaos"] == 6 and u["repetidas"] == 1 and u["tabelas"] >= 5 and u["erros"] == 0
    assert {"tabela": "nexus_fatos · fato_fechamento", "coluna": C.CHAVE, "linhas": 4, "repetidas": 1} in u["problemas"]
    assert any(p["coluna"] == "data_id" and p["orfaos"] == 1 for p in u["problemas"])


def test_a_api_que_devolve_tudo_como_texto_da_a_mesma_conta(banco):
    num = C.conferir(BASE, banco, AGORA)[1]
    C.rodar(CFG, banco, agora=AGORA)
    for v in banco.abas.values():                                   # a API que devolve todo valor como texto
        v["linhas"] = [{"headers": x["headers"], "values": [None if c is None else str(c) for c in x["values"]]}
                       for x in v["linhas"]]
    txt = C.conferir(BASE, banco, AGORA)[1]
    assert (txt["orfaos"], txt["repetidas"]) == (num["orfaos"], num["repetidas"])
    assert C.ultima(BASE, banco)["orfaos"] == 6


def test_antes_da_1a_conferencia_a_governanca_nao_inventa(banco):
    assert C.ultima(BASE, banco) is None


def test_a_governanca_mostra_a_conferencia(app, logado, banco, monkeypatch):
    """A tela lê a última conferência gravada, sem pedir a listagem do banco de novo, e diz o que achou."""
    from nexus.dados import previa, telas
    C.rodar(CFG, banco, agora=AGORA)
    app.config["GRIDCO_DB_API"] = BASE
    app.extensions["nexus_dados_sessao"] = banco
    monkeypatch.setattr(telas, "_CACHE", {"t": 0.0, "v": None})
    monkeypatch.setattr(previa, "_ABAS", {"t": 0.0, "v": None})
    # com a listagem que a tela já tem, a leitura da conferência não pede outra
    listagens, real = [], banco.get
    abas = {(x["workbook_key"], x["sheet_name"]): x for x in real(f"{BASE}/api/sheets").json()}
    monkeypatch.setattr(banco, "get", lambda url, **kw: (listagens.append(url) if url.endswith("/api/sheets") else None)
                        or real(url, **kw))
    assert C.ultima(BASE, banco, abas)["orfaos"] == 6 and listagens == []
    try:
        for ver in ("organograma", "matriz"):
            telas._CACHE.update(t=0.0, v=None)
            html = logado.get(f"/t/base/governanca?ver={ver}").get_data(as_text=True)
            assert 'id="dd-conferencia"' in html and 'data-conf="orfaos" class="critico"><b>6</b>' in html
            assert "nexus_fatos · fato_fechamento" in html and "chave repetida" in html and "ID órfão" in html
        assert "Conferência das ligações: <b>6</b> linhas com ID órfão" in logado.get("/t/base/governanca").get_data(as_text=True)
    finally:
        app.extensions.pop("nexus_dados_sessao", None)


def test_o_livro_da_conferencia_esta_no_catalogo():
    from nexus.dados import catalogo
    lv = catalogo.LIVRO_POR_NOME[C.LIVRO]
    assert set(lv.abas) == {C.ABA, "atualizacao"} and not lv.so_cresce        # trocado inteiro a cada conferência

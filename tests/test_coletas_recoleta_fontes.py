# -*- coding: utf-8 -*-
"""A recoleta pelas fontes na Coletas (17/11/2026; Levi: "quero formas de coletar os dados novamente pelas nossas fontes
de dados e gerar uma planilha para colar nos BDs"). A plataforma é dublada com as respostas do contrato combinado com o
chat da Coleta (`/api/recoleta/<fonte>?formato=bd`): nada sai para a rede e nenhuma fonte paga é chamada."""
import datetime as dt
import os
import time

import pytest

from nexus.performance.coletas import pg, recoleta_fontes as RF, servico
from tests.test_coletas import BancoDeMentira, _bd_excel  # o BD de mentira da Coletas: aba "Teste", outubro de 2026

D = dt.date


def test_a_usina_da_tela_e_a_aba_com_todos_os_ids_dela():
    """A mesma planta pode ir para duas abas (Ouro Branco -> 1 e 2) e várias plantas para a mesma aba (Ceilândia 2)."""
    m = RF.por_usina([{"id": "15", "usina": "Ouro Branco 1", "destino": "BD_Thopen"},
                      {"id": "15", "usina": "Ouro Branco 2", "destino": "BD_Thopen"},
                      {"id": 89, "usina": "Ceilândia 2", "destino": "BD_Thopen"}, {"id": 90, "usina": "Ceilândia 2", "destino": "BD_Thopen"},
                      {"id": 89, "usina": "Ceilândia 2", "destino": "BD_Thopen"}, {"id": None, "usina": "X", "destino": "BD_Thopen"}])
    assert m == {"Ouro Branco 1": {"destino": "BD_Thopen", "ids": ["15"]}, "Ouro Branco 2": {"destino": "BD_Thopen", "ids": ["15"]},
                 "Ceilândia 2": {"destino": "BD_Thopen", "ids": ["89", "90"]}}


def test_o_plano_respeita_os_tetos_de_cada_fonte():
    """scada aceita 2 plantas por pedido e a apipv 8; o período maior que o teto de dias vai em trechos."""
    p = RF.plano(["1", "2", "3"], D(2026, 11, 1), D(2026, 11, 9), 2, 7)
    assert p == [(["1", "2"], D(2026, 11, 1), D(2026, 11, 7)), (["3"], D(2026, 11, 1), D(2026, 11, 7)),
                 (["1", "2"], D(2026, 11, 8), D(2026, 11, 9)), (["3"], D(2026, 11, 8), D(2026, 11, 9))]
    assert RF.plano(["1"], D(2026, 11, 1), D(2026, 11, 1), None, None) == [(["1"], D(2026, 11, 1), D(2026, 11, 1))]


def test_as_celulas_saem_da_resposta_e_o_nulo_nunca_vira_zero():
    resp = [{"geracao": [{"usina": "Sapopema", "inversor": "Inversor 01", "data": "2026-11-10", "kwh": 812.46},
                         {"usina": "Sapopema", "inversor": "Inversor 03", "data": "2026-11-10", "kwh": 0.0},
                         {"usina": "Sapopema", "inversor": "Inversor 02", "data": "2026-11-10", "kwh": None},
                         {"usina": "Outra", "inversor": "Inversor 01", "data": "2026-11-10", "kwh": 5.0}],
             "escalares": [{"usina": "Sapopema", "data": "2026-11-10", "coluna": "IPOA", "valor": 6.1234},
                           {"usina": "Sapopema", "data": "2026-11-10", "coluna": "Chuva", "valor": 12.4}],
             "avisos": ["Sapopema 2026-11-11: fonte fora do ar no dia (menos da metade dos inversores com valor); não sugerir",
                        "3 valor(es) sem leitura na fonte ficaram de fora (nulo, não 0)"],
             "dias_fora": [{"usina": "Sapopema", "data": "2026-11-11"}]},
            {"geracao": [{"usina": "Sapopema", "inversor": "Inversor 01", "data": "2026-11-10", "kwh": 812.46}], "avisos": []}]
    cel, av = RF.celulas(resp, "Sapopema", "BD_Thopen")
    got = {(c.coluna, c.data.isoformat()): (c.valor, c.so_vazio) for c in cel}
    assert got == {("Inversor 01", "2026-11-10"): (812.46, False), ("Inversor 03", "2026-11-10"): (0.0, False),   # o 0.0 é leitura
                   ("IPOA", "2026-11-10"): (6.1234, False), ("Chuva", "2026-11-10"): (12.4, True)}             # a chuva só no vazio
    assert all(c.destino == "BD_Thopen" and c.aba == "Sapopema" for c in cel)
    assert av[0][0] == "severo" and "fora do ar" in av[0][1] and av[1][0] == "leve"       # o dia fora do ar entra com aviso


# ── pela tela ────────────────────────────────────────────────────────────────────────────────────────────────────
def _plataforma(monkeypatch, paga=True):
    pedidos = []

    def pedir(rota, chave_, corpo=None, timeout=180):
        pedidos.append((rota, chave_, corpo))
        if "/plantas" in rota:
            return {"plantas": [{"id": "7", "usina": "Teste", "destino": "BD_Performance", "planta": "(7) Planta Teste"},
                                {"id": "8", "usina": "Teste", "destino": "BD_Performance"},
                                {"id": "9", "usina": "Aba que não existe", "destino": "BD_Performance"},
                                {"id": "5", "usina": "Do Thopen", "destino": "BD_Thopen"}],
                    "max_dias": 7, "max_plantas": 1, "paga": paga, "teto": 150 if paga else None,
                    "cota_restante": 147 if paga else None}
        if corpo.get("simular"):
            return {"consultas": 5 if paga else 0, "cota_restante": 147 if paga else None, "teto": 150 if paga else None}
        if corpo["ids"] == ["8"]:
            return {"geracao": [], "escalares": [], "avisos": [], "dias_fora": [], "consultas": 2, "cota_restante": 143}
        return {"geracao": [{"usina": "Teste", "inversor": "Inversor 1.1", "data": "2026-10-14", "kwh": 1500.0},
                            {"usina": "Teste", "inversor": "Inversor 1.2", "data": "2026-10-14", "kwh": 1400.0}],
                "escalares": [{"usina": "Teste", "data": "2026-10-14", "coluna": "IPOA", "valor": 6.1},
                              {"usina": "Teste", "data": "2026-10-14", "coluna": "GHI", "valor": 5.0}],
                "avisos": ["1 valor(es) sem leitura na fonte ficaram de fora (nulo, não 0)"], "dias_fora": [],
                "consultas": 2, "cota_restante": 145, "teto": 150}
    monkeypatch.setattr(RF._recoleta, "_pedir", pedir)
    return pedidos


@pytest.fixture
def tela(app, logado, tmp_path):
    p = _bd_excel(tmp_path)
    pg._GUARDA.clear()
    app.config.update(NEXUS_COLETAS_BANCO=lambda: BancoDeMentira(p), NEXUS_COLETAS_TMP=str(tmp_path),
                      CONVERSOR_RECOLETA_CHAVE="chave-de-teste")
    yield logado
    for k in list(servico._SESSOES):
        servico.esquecer(k)
    pg._GUARDA.clear()


def _api(c, metodo, *args):
    return c.post("/t/performance/coletas/api/" + metodo, json={"args": list(args)})


def _bd_pronto(c):
    for _ in range(50):
        if _api(c, "estado").get_json()["bd_pronto"]:
            return
        time.sleep(0.1)
    raise AssertionError("o BD não ficou pronto")


def test_a_recoleta_de_uma_fonte_mostra_o_custo_antes_e_sai_pela_mesma_montagem(tela, monkeypatch):
    pedidos = _plataforma(monkeypatch)
    html = tela.get("/t/performance/coletas/app").get_data(as_text=True)
    assert "/static/coletas/recoleta.js" in html
    fontes = _api(tela, "fontes_lista").get_json()
    assert [f["id"] for f in fontes] == ["pg", "scada", "apipv", "solaredge", "oem", "sunop", "chuva"]
    assert fontes[0]["nome"] == "Banco da Thopen"                              # primeiro o que não gasta cota
    _bd_pronto(tela)
    pl = _api(tela, "fontes_plantas", "apipv").get_json()
    assert pl["usinas"] == [{"usina": "Teste", "destino": "BD_Performance", "plantas": 2}]
    assert pl["sem_aba"] == ["Aba que não existe"] and pl["sem_bd"] == ["BD_Thopen"]      # o BD_Thopen de mentira não leu
    assert pl["paga"] and pl["teto"] == 150 and pl["cota_restante"] == 147
    assert pedidos[0][:2] == ("/api/recoleta/apipv/plantas?formato=bd", "chave-de-teste")
    arg = ("apipv", "Teste", "2026-10-14", "2026-10-14", True, True, False)
    sim = _api(tela, "fontes_simular", *arg).get_json()
    assert sim == {"consultas": 10, "cota_restante": 147, "teto": 150, "pedidos": 2}        # 2 plantas, 1 por pedido
    assert all(c["simular"] for _r, _k, c in pedidos[1:])                                  # até aqui, nada foi buscado
    plano = _api(tela, "fontes_plano", *arg).get_json()
    assert plano == {"pedidos": [["2026-10-14", "2026-10-14", 1], ["2026-10-14", "2026-10-14", 1]]}
    assert _api(tela, "fontes_parte", 0).get_json() == {"ok": True, "consultas": 2, "cota_restante": 145}
    assert _api(tela, "fontes_parte", 1).get_json() == {"ok": True, "consultas": 2, "cota_restante": 143}
    assert pedidos[-2][0] == "/api/recoleta/apipv?formato=bd" and pedidos[-2][2] == {
        "ids": ["7"], "ini": "2026-10-14", "fim": "2026-10-14", "geracao": True, "etm": True, "chuva": False, "simular": False}
    res = _api(tela, "fontes_montar").get_json()
    assert not res.get("erro") and res["origem"] == "recoleta"
    assert res["recoleta"] == {"usina": "Teste", "celulas": 4, "fonte": "API PV · conta principal"}
    assert res["totais"]["novo"] >= 3 and res["saidas"][0]["indice"] == 0 and os.sep not in res["saidas"][0]["caminho"]
    textos = [a["texto"] for a in res["avisos"]]
    assert any("sem leitura na fonte" in t for t in textos) and any("veio do banco" in t for t in textos)
    assert tela.get("/t/performance/coletas/planilha/0").status_code == 200


def test_fonte_sem_cota_diz_que_nao_custa_e_a_recusa_da_plataforma_chega_como_veio(tela, monkeypatch):
    _plataforma(monkeypatch, paga=False)
    _bd_pronto(tela)
    pl = _api(tela, "fontes_plantas", "pg").get_json()
    assert not pl["paga"] and pl["teto"] is None and pl["nome"] == "Banco da Thopen"
    assert _api(tela, "fontes_simular", "pg", "Teste", "2026-10-14", "2026-10-14", True, False, False).get_json()["consultas"] == 0

    def recusa(rota, chave_, corpo=None, timeout=180):
        raise RF.Falha("teto de 150 consultas por dia da recoleta por apipv atingido (148 usadas hoje); tente amanhã")
    monkeypatch.setattr(RF._recoleta, "_pedir", recusa)
    assert "teto de 150" in _api(tela, "fontes_plantas", "apipv").get_json()["erro"]
    assert _api(tela, "fontes_plantas", "xyz").get_json()["erro"].startswith("Fonte desconhecida")
    assert "venceu" in _api(tela, "fontes_parte", 0).get_json()["erro"]                  # sem plano, nada é pedido
    assert "venceu" in _api(tela, "fontes_montar").get_json()["erro"]


def test_a_fonte_que_nao_devolve_nada_diz_isso_em_vez_de_planilha_vazia(tela, monkeypatch):
    _plataforma(monkeypatch)
    _bd_pronto(tela)
    _api(tela, "fontes_plantas", "apipv")
    monkeypatch.setattr(RF._recoleta, "_pedir", lambda *a, **k: {"geracao": [], "escalares": [], "dias_fora": [],
                                                              "avisos": ["Teste 2026-10-14: a fonte não respondeu"]})
    _api(tela, "fontes_plano", "apipv", "Teste", "2026-10-14", "2026-10-14", True, True, False)
    _api(tela, "fontes_parte", 0)
    erro = _api(tela, "fontes_montar").get_json()["erro"]
    assert "não devolveu nenhum valor de Teste" in erro and "a fonte não respondeu" in erro


def test_as_fontes_so_abrem_para_quem_pode_recoletar(tela, monkeypatch):
    """A trava é a mesma da recoleta do .exe: só o setor Performance (a tela coletas/recoleta). Sem ela, nem o script da
    tela vem, as rotas recusam e nada chega à plataforma."""
    from nexus.auth import setor_telas
    pedidos = _plataforma(monkeypatch)
    monkeypatch.setattr(setor_telas, "acesso", lambda: {"tudo": False, "telas": {"performance/coletas"}, "setor": None, "erro": ""})
    assert "/static/coletas/recoleta.js" not in tela.get("/t/performance/coletas/app").get_data(as_text=True)
    for m in ("fontes_lista", "fontes_plantas", "fontes_simular", "fontes_plano", "fontes_parte", "fontes_montar"):
        assert _api(tela, m, "apipv", "Teste", "2026-10-14", "2026-10-14", True, True, False).status_code == 403
    assert pedidos == []

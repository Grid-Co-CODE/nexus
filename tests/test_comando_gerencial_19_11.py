"""Comando › Visão gerencial (teste), 19/11/2026: o portfólio que afunila (portfólio → cliente → usina) e a nota de
cumprimento do contrato por usina.

Levi, 18 e 19/11/2026: "Quero uma visão do portfólio inteiro puxando mensal por contratos da parte de COMANDO > CONTRATOS
[...] depois vai afunilando, clientes e depois usinas!"; "por cima dos quadradinhos poderia inserir um score de
contratos?"; "quando eu clicar na UFV tem que explicar esse número"; "a cor do bloco segue a nota do contrato"; "é bom
estar filtrado por mês sempre mostrando o mês atual"; "um botão que leva para o prontuário da usina"; "sobe como Visão
gerencial (teste)". Os dados dos testes são inventados (o repositório é público: nada de contrato de verdade aqui).
"""
from datetime import date

import pytest

from nexus.comando import gerencial as G

from test_campo_responsaveis import tela  # noqa: F401  (tela é fixture)
from test_campo_visao import banco  # noqa: F401  (banco é fixture)

GARANTIA = {"pct": 99.0, "nome": "Disponibilidade mínima de 99%", "texto": "Mínima de 99% no mês.", "clausula": "11.2"}
USINA_EM_DIA = {"ronda_dias": 2, "nunca_rondada": False, "plano_pct": 100, "plano_txt": "5 de 5 tarefas do plano · W46",
                "os_abertas": 3, "os_urgentes": 0, "os_atrasadas_n": 0, "mais_antiga_d": None}
MES_BOM = {"meta": 101.0, "pr": 80.0, "pr_prev": 79.0, "disp": 99.6}


def _item(s, nome):
    return next(i for i in s["itens"] if i["nome"] == nome)


# ── a nota: os quatro itens ──────────────────────────────────────────────────────────────────────────────────────────
def test_a_usina_que_cumpre_tudo_tira_100_com_os_quatro_itens():
    s = G.nota_do_contrato(GARANTIA, MES_BOM, USINA_EM_DIA, atual=True, semanas=4)
    assert s["nota"] == 100 and s["medidos"] == 4
    assert [i["nome"] for i in s["itens"]] == ["Disponibilidade", "Geração e PR", "Rotinas", "Prazos de OS"]
    assert all(i["pede"] and i["mediu"] and i["conta"] for i in s["itens"])


def test_cada_ponto_percentual_abaixo_da_garantida_tira_20():
    s = G.nota_do_contrato(GARANTIA, {**MES_BOM, "disp": 97.0}, USINA_EM_DIA, atual=True, semanas=4)
    assert _item(s, "Disponibilidade")["nota"] == 60
    assert "2,0 pontos percentuais" in _item(s, "Disponibilidade")["conta"]
    assert "97,0%" in _item(s, "Disponibilidade")["mediu"]
    # 5 pontos ou mais abaixo zera o item; não fica negativo
    assert _item(G.nota_do_contrato(GARANTIA, {**MES_BOM, "disp": 87.1}, USINA_EM_DIA, True, 4), "Disponibilidade")["nota"] == 0


def test_o_texto_do_que_o_contrato_pede_traz_a_regra_e_a_clausula():
    pede = _item(G.nota_do_contrato(GARANTIA, MES_BOM, USINA_EM_DIA, True, 4), "Disponibilidade")["pede"]
    assert "99%" in pede and "Disponibilidade mínima de 99%" in pede and "11.2" in pede


def test_contrato_sem_garantia_deixa_a_disponibilidade_fora_e_nao_inventa_98():
    s = G.nota_do_contrato(None, MES_BOM, USINA_EM_DIA, True, 4)
    d = _item(s, "Disponibilidade")
    assert d["nota"] is None and "não garante" in d["pede"] and "fora" in d["conta"].lower()
    assert s["medidos"] == 3 and s["nota"] == 100


def test_geracao_e_pr_e_a_media_dos_dois_com_teto_de_100():
    s = G.nota_do_contrato(GARANTIA, {**MES_BOM, "meta": 80.0, "pr": 60.0, "pr_prev": 80.0}, USINA_EM_DIA, True, 4)
    assert _item(s, "Geração e PR")["nota"] == 78          # (80 + 75) / 2 = 77,5
    so_meta = G.nota_do_contrato(GARANTIA, {"meta": 120.0, "pr": None, "pr_prev": None, "disp": 99.5}, USINA_EM_DIA, True, 4)
    assert _item(so_meta, "Geração e PR")["nota"] == 100


def test_pr_acima_de_100_e_leitura_errada_e_fica_fora():
    """18/11/2026: uma usina aparecia com PR de 558,7% em outubro; com o teto, valeria nota cheia."""
    s = G.nota_do_contrato(GARANTIA, {"meta": 64.0, "pr": 558.7, "pr_prev": 81.0, "disp": 99.5}, USINA_EM_DIA, True, 4)
    g = _item(s, "Geração e PR")
    assert g["nota"] == 64 and "leitura errada" in g["mediu"]


def test_rotinas_do_mes_vigente_ronda_a_cada_7_dias_e_o_plano_da_semana():
    u = {**USINA_EM_DIA, "ronda_dias": 15, "plano_pct": 28}
    r = _item(G.nota_do_contrato(GARANTIA, MES_BOM, u, True, 4), "Rotinas")
    assert r["nota"] == 24                                 # ronda 100 - 10 x 8 = 20; plano 28; média 24
    assert "15 dias" in r["mediu"] and "28%" in r["mediu"]


def test_usina_nunca_rondada_fica_fora_da_ronda_e_nao_leva_zero():
    u = {**USINA_EM_DIA, "ronda_dias": None, "nunca_rondada": True, "plano_pct": None, "plano_txt": ""}
    r = _item(G.nota_do_contrato(GARANTIA, MES_BOM, u, True, 4), "Rotinas")
    assert r["nota"] is None and "nunca rondada" in r["mediu"].lower()


def test_prazos_de_os_cada_urgente_tira_25_e_cada_atrasada_tira_10():
    u = {**USINA_EM_DIA, "os_urgentes": 2, "os_atrasadas_n": 3, "mais_antiga_d": 70}
    p = _item(G.nota_do_contrato(GARANTIA, MES_BOM, u, True, 4), "Prazos de OS")
    assert p["nota"] == 20 and "70 dias" in p["mediu"]
    sem_os = _item(G.nota_do_contrato(GARANTIA, MES_BOM, {**USINA_EM_DIA, "os_abertas": None}, True, 4), "Prazos de OS")
    assert sem_os["nota"] is None


def test_com_um_item_so_nao_ha_nota():
    """A E1 sem ronda, sem geração e sem disponibilidade sairia com 100 só por não ter OS atrasada."""
    u = {**USINA_EM_DIA, "ronda_dias": None, "nunca_rondada": True, "plano_pct": None}
    s = G.nota_do_contrato(None, {"meta": None, "pr": None, "pr_prev": None, "disp": None}, u, True, 4)
    assert s["medidos"] == 1 and s["nota"] is None


# ── o mês fechado ────────────────────────────────────────────────────────────────────────────────────────────────────
def test_no_mes_fechado_as_rotinas_sao_as_rondas_do_mes_e_os_prazos_ficam_fora():
    s = G.nota_do_contrato(GARANTIA, {**MES_BOM, "rondas": 3}, USINA_EM_DIA, atual=False, semanas=4)
    assert _item(s, "Rotinas")["nota"] == 75 and "3 rondas" in _item(s, "Rotinas")["mediu"]
    assert _item(s, "Prazos de OS")["nota"] is None and "de hoje" in _item(s, "Prazos de OS")["mediu"]
    assert s["medidos"] == 3
    assert "no mês fechado" in _item(s, "Disponibilidade")["mediu"]
    cheio = G.nota_do_contrato(GARANTIA, {**MES_BOM, "rondas": 7}, USINA_EM_DIA, False, 4)
    assert _item(cheio, "Rotinas")["nota"] == 100
    sem = G.nota_do_contrato(GARANTIA, {**MES_BOM, "rondas": None}, USINA_EM_DIA, False, 4)
    assert _item(sem, "Rotinas")["nota"] is None


# ── o contrato lido: a garantia e o valor de cada usina ──────────────────────────────────────────────────────────────
def _ficha(regras=(), contratos=None):
    return {"contratos": contratos if contratos is not None else [{"id": "K1", "regras": list(regras)}]}


def test_a_garantia_sai_da_regra_de_disponibilidade_do_contrato():
    f = _ficha([{"categoria": "SLA", "nome": "Resposta em 4 h", "vigente": "4 h"},
                {"categoria": "Disponibilidade e desempenho", "nome": "PR de referência", "vigente": "77,5%"},
                {"categoria": "Disponibilidade e desempenho", "nome": "Disponibilidade mínima das UFVs",
                 "vigente": "Meta mínima mensal de 98% de disponibilidade.", "ref": {"clausula": "7.1"}}])
    g = G.garantia_de_disponibilidade(f)
    assert g["pct"] == 98.0 and g["nome"] == "Disponibilidade mínima das UFVs" and g["clausula"] == "7.1"
    assert G.garantia_de_disponibilidade(_ficha([{"categoria": "SLA", "nome": "Disponibilidade da equipe", "vigente": "100%"}])) is None
    assert G.garantia_de_disponibilidade(None) is None


def test_o_valor_da_usina_liga_pelo_nome_pelo_codigo_ou_pelo_nome_sem_o_numero():
    f = _ficha(contratos=[
        {"valor": {"por_usina": [{"usina": "UFV Sol Nascente II", "mensal": 1000.0}, {"usina": "UFV XPT100 (Cliente Lua Cheia)", "mensal": 2000.0}]}},
        {"valor": {"mensal": 3000.0}, "usinas": [{"nome": "Tupi Paulista", "potencia_kwp": 6500}]},
        {"valor": {"por_usina": [{"usina": "União (1ª linha)", "mensal": 400.0}, {"usina": "União (2ª linha)", "mensal": 600.0}]}}])
    usinas = [{"usina": "Sol Nascente 2", "codigo": "ABC-SNC200", "mwp": 3.0}, {"usina": "Lua Cheia 100", "codigo": "ABC-XPT100", "mwp": 5.0},
              {"usina": "Tupi Paulista 1", "codigo": "", "mwp": 6.5}, {"usina": "União 1 e 2", "codigo": "", "mwp": 4.4},
              {"usina": "Sem Par", "codigo": "", "mwp": 1.0}]
    v = G.valores_por_usina(f, usinas)
    assert v == {"Sol Nascente 2": 1000.0, "Lua Cheia 100": 2000.0, "Tupi Paulista 1": 3000.0, "União 1 e 2": 1000.0}


def test_o_nome_sem_o_numero_so_liga_quando_nao_ha_duvida():
    f = _ficha(contratos=[{"valor": {"por_usina": [{"usina": "Mandaguaçu", "mensal": 500.0}]}}])
    dois = [{"usina": "Mandaguaçu 1", "codigo": "", "mwp": 3.0}, {"usina": "Mandaguaçu 2", "codigo": "", "mwp": 3.0}]
    assert G.valores_por_usina(f, dois) == {}                  # duas usinas com o mesmo nome sem o número: não se chuta
    f2 = _ficha(contratos=[{"valor": {"mensal": 500.0}, "usinas": [{"nome": "Araputanga", "potencia_kwp": 9000}]}])
    assert G.valores_por_usina(f2, [{"usina": "Araputanga 1", "codigo": "", "mwp": 3.2}]) == {}   # a potência não bate


def test_o_cliente_do_contrato_e_o_do_cadastro_casam_sem_acento_e_sem_caixa():
    assert G.chave_cliente("RenoGrid") == G.chave_cliente("Renogrid")
    assert G.chave_cliente("E1 Energia") == G.chave_cliente("E1")
    assert G.chave_cliente("Semp") == G.chave_cliente("SEMP")
    assert G.chave_cliente("Elis Energia") != G.chave_cliente("E1 Energia")


# ── a montagem ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _usina(uid, nome, cliente, mwp, **k):
    return {"uid": uid, "usina": nome, "cliente": cliente, "codigo": "", "mwp": mwp, "pontos": 90, **USINA_EM_DIA,
            "meses": {"2026-11": dict(MES_BOM), "2026-10": {**MES_BOM, "rondas": 4}}, **k}


def _contratos():
    return {"contratos": [{"cliente": "CLIENTE A", "valor_mensal": 9000.0, "valor_info": {"minuta": True}, "inicio": "2025-01-01",
                           "fim": "2027-01-01", "dias_fim": 408, "atrasadas": 2}],
            "fichas": {"CLIENTE A": _ficha(
                [{"categoria": "Disponibilidade e desempenho", "nome": "Disponibilidade mínima de 99%", "vigente": "99% no mês."}],
                None) | {"contratos": [{"id": "K1", "valor": {"por_usina": [{"usina": "Alfa", "mensal": 4000.0}]},
                                        "regras": [{"categoria": "Disponibilidade e desempenho", "nome": "Disponibilidade mínima de 99%",
                                                    "vigente": "99% no mês."}]}]}}}


def test_montar_junta_o_contrato_a_nota_por_mes_e_os_totais():
    us = [_usina(1, "Alfa", "Cliente A", 5.0), _usina(2, "Beta", "Cliente A", 3.0, meses={
        "2026-11": {**MES_BOM, "disp": 96.0}, "2026-10": {**MES_BOM, "rondas": 2}}),
        _usina(3, "Gama", "Cliente B", 2.0)]
    d = G.montar(us, _contratos(), date(2026, 11, 19), "19/11/2026 às 01:50")
    assert d["ok"] and d["mes_atual"] == "2026-11" and [m["id"] for m in d["meses"]] == ["2026-11", "2026-10"]
    assert d["meses"][0]["atual"] and d["meses"][1]["nome"] == "outubro de 2026" and d["meses"][1]["semanas"] == 4
    assert d["totais"] == {"clientes": 2, "usinas": 3, "mwp": 10.0, "valor": 9000.0, "com_valor": 1}
    a = next(c for c in d["clientes"] if c["cliente"] == "Cliente A")
    assert a["valor"] == 9000.0 and a["minuta"] and a["dias_fim"] == 408 and a["obrigacoes_atrasadas"] == 2 and a["tem_contrato"]
    assert a["disp_garantida"]["pct"] == 99.0 and a["mwp"] == 8.0 and a["usinas_n"] == 2
    alfa, beta = a["usinas"]
    assert alfa["valor"] == 4000.0 and beta["valor"] is None
    assert alfa["score"]["2026-11"]["nota"] == 100
    assert beta["score"]["2026-11"]["nota"] == 85 and beta["score"]["2026-10"]["nota"] == 83   # (100+100+50)/3
    assert a["score"]["2026-11"] == {"nota": 93, "usinas": 2}                                  # (100 + 85) / 2 = 92,5, meio para cima
    b = next(c for c in d["clientes"] if c["cliente"] == "Cliente B")
    assert not b["tem_contrato"] and b["valor"] is None and b["disp_garantida"] is None
    assert b["usinas"][0]["score"]["2026-11"]["medidos"] == 3


def test_montar_sem_os_contratos_ainda_mostra_as_usinas_e_avisa():
    d = G.montar([_usina(1, "Alfa", "Cliente A", 5.0)], None, date(2026, 11, 19), "19/11/2026 às 01:50", avisos=["o cadastro"])
    assert d["ok"] and not d["contratos_ok"] and d["totais"]["valor"] is None
    assert d["avisos"] == ["o cadastro"] and d["clientes"][0]["usinas"][0]["score"]["2026-11"]["nota"] == 100


def test_a_saude_media_do_cliente_so_existe_com_performance_publicada():
    com = G.montar([_usina(1, "Alfa", "Cliente A", 5.0, pontos=70)], None, date(2026, 11, 19), "x")
    assert com["clientes"][0]["media"] == 70
    sem = G.montar([_usina(1, "Alfa", "Cliente A", 5.0, pontos=97, meses={"2026-11": {"meta": None, "pr": None, "pr_prev": None, "disp": None}})],
                   None, date(2026, 11, 19), "x")
    assert sem["clientes"][0]["media"] is None


# ── a tela e o dados.json ────────────────────────────────────────────────────────────────────────────────────────────
def test_a_visao_gerencial_esta_no_menu_do_comando_com_o_nome_do_levi(tela, logado):
    html = logado.get("/t/comando/visao-gerencial").get_data(as_text=True)
    assert "Visão gerencial (teste)" in html
    assert 'id="vg"' in html and "visao-gerencial/dados.json" in html and "gerencial.js" in html and "gerencial.css" in html
    assert "/t/campo/usinas/" in html                         # a base do endereço do prontuário da usina


def test_o_dados_json_traz_o_portfolio_com_a_nota_e_sem_nome_de_pessoa(tela, logado):
    r = logado.get("/t/comando/visao-gerencial/dados.json")
    assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store"
    d = r.get_json()
    assert d["ok"] and d["clientes"] and d["meses"][0]["atual"]
    u = d["clientes"][0]["usinas"][0]
    assert {"uid", "usina", "mwp", "score", "meses", "valor"} <= set(u)
    assert d["mes_atual"] in u["score"] and len(u["score"][d["mes_atual"]]["itens"]) == 4
    assert "gestor" not in r.get_data(as_text=True)           # o nome do gestor do contrato não sai daqui


def test_o_cliente_nao_abre_a_visao_gerencial(tela, logado):
    with logado.session_transaction() as s:
        s["via"] = "cliente"
    assert logado.get("/t/comando/visao-gerencial").status_code in (302, 403)
    assert logado.get("/t/comando/visao-gerencial/dados.json").status_code in (302, 403)


@pytest.mark.parametrize("arquivo", ["gerencial.js", "gerencial.css", "comando/grid-simbolo.png"])
def test_os_estaticos_da_visao_gerencial_existem(logado, arquivo):
    assert logado.get(f"/static/{arquivo}").status_code == 200


# ── as rondas do mês fechado, do fechamento guardado ─────────────────────────────────────────────────────────────────
def test_as_rondas_do_mes_guardado_e_o_zero_de_quem_nao_teve_atividade():
    """19/11/2026, na conferência com o dado real: a usina que opera e não teve NENHUMA atividade em outubro não tem linha
    no fato, e saía "sem o fechamento" (fora da nota) em vez de 0 ronda. Mês que o fato tem = zero de verdade; mês que o
    fato não tem = não foi guardado (None)."""
    from nexus.dados import fato_atividade_mes as AM
    cab = AM.CAB
    def lin(uid, mes, atividade, n):
        return dict(zip(cab, [f"{uid}-{mes}-{atividade}", mes * 100 + 1, uid, "x", atividade, n, 0, "2026-11-18T14:40"]))
    fato = [lin(1, 202610, "ronda_curta", 3), lin(1, 202610, "ronda_longa", 1), lin(1, 202610, "tarefa_corretiva", 9),
            lin(2, 202610, "pt", 2), lin(1, 202609, "ronda_curta", 5)]
    rondas, meses = AM.rondas_por_mes(fato)
    assert meses == {202610, 202609}
    assert rondas[(1, 202610)] == 4 and rondas[(1, 202609)] == 5 and (2, 202610) not in rondas
    assert AM.rondas_do_mes(rondas, meses, 1, 202610) == 4
    assert AM.rondas_do_mes(rondas, meses, 2, 202610) == 0          # o mês está no fato: sem linha de ronda é zero
    assert AM.rondas_do_mes(rondas, meses, 3, 202610) == 0          # usina sem atividade nenhuma no mês guardado: zero
    assert AM.rondas_do_mes(rondas, meses, 1, 202608) is None       # mês que o fato não tem: não é zero

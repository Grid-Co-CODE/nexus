"""Comando > Contratos, 26/11/2026: a aba Indicadores (o ano contratual mês a mês, usina por usina) e o aniversário do
contrato.

A sugestão: "meses do ano contratual nas colunas, usinas nas linhas", com MPM, MPS e MPA, a supressão vegetal e a lavagem,
o PR e a disponibilidade expurgada contra a meta. O Levi, no mesmo dia: "ANIVERSÁRIO DE CONTRATO, RELATÓRIO DE ANIVERSÁRIO
DE CONTRATO"; o ano conta do início da vigência; todas as usinas do cliente; "sem dado" antes de 10/2026; a régua de cor
da sugestão (verde na meta, amarelo até 2 pontos abaixo, vermelho abaixo, azul com asterisco no mês com expurgo).

Tudo inventado (o repositório é público)."""
from datetime import date, datetime

import pytest

from nexus.contratos import controle as K
from nexus.contratos import indicadores as I
from nexus.contratos import pontos as P
from test_contratos_editavel_18_11 import _como, carga  # noqa: F401 — a fixture da carga inicial

HOJE = date(2026, 11, 26)


def test_o_ano_contratual_conta_do_inicio_da_vigencia():
    assert K.ano_contratual(date(2025, 9, 15), HOJE) == {"n": 2, "ini": "2026-09-15", "fim": "2027-09-14", "atual": True}
    assert K.ano_contratual(date(2025, 9, 15), HOJE, 1) == {"n": 1, "ini": "2025-09-15", "fim": "2026-09-14", "atual": False}
    assert K.ano_contratual(date(2027, 1, 1), HOJE)["n"] == 1                    # antes do início: o 1º ano
    assert K.ano_contratual(date(2024, 2, 29), HOJE)["ini"] == "2026-02-28"      # o 29/02 vira 28/02
    assert K.ano_contratual(None, HOJE) is None
    assert K.proximo_aniversario(date(2025, 11, 26), HOJE) == HOJE               # hoje conta
    assert K.proximo_aniversario(date(2025, 9, 15), HOJE) == date(2027, 9, 15)


def test_o_aniversario_vira_ponto_de_atencao_30_dias_antes():
    c = {"cliente": "Solar Alfa", "aniversario": "2026-12-20", "dias_aniversario": 24, "ano_contratual": {"n": 1}}
    r = P.todos([c], {}, [], {}, {}, HOJE)["por_cliente"]["Solar Alfa"]
    an = [p for p in r if p["id"].startswith("c:aniversario:")]
    assert len(an) == 1 and "20/12/2026" in an[0]["texto"] and "1º ano" in an[0]["texto"]
    c.update(dias_aniversario=31)
    assert not [p for p in P.todos([c], {}, [], {}, {}, HOJE)["por_cliente"]["Solar Alfa"] if p["id"].startswith("c:aniversario:")]


def test_a_regua_de_cor_da_sugestao():
    assert I.tom_kpi(78.0, 78.0) == "ok"
    assert I.tom_kpi(76.5, 78.0) == "alerta"            # até 2 pontos abaixo
    assert I.tom_kpi(75.9, 78.0) == "critico"
    assert I.tom_kpi(80.0, None) == "" and I.tom_kpi(None, 78.0) == ""


def test_as_metas_do_contrato_lido_e_o_numero_dos_dados_vence():
    ficha = {"contratos": [{"regras": [
        {"categoria": "Disponibilidade e desempenho", "nome": "Disponibilidade garantida", "vigente": "Mínimo de 98,5% ao mês"},
        {"categoria": "Disponibilidade e desempenho", "nome": "PR mínimo", "vigente": "PR de 78% no ano"}]}]}
    m = I.metas({}, ficha)
    assert m["disp"]["pct"] == 98.5 and m["pr"]["pct"] == 78.0 and m["pr"]["origem"].startswith("do contrato")
    m = I.metas({"meta_pr": 80.0}, ficha)
    assert m["pr"] == {"pct": 80.0, "origem": "dos Dados do contrato"}
    assert I.metas({}, None) == {"pr": None, "disp": None}


def _montar(**k):
    ano = {"n": 2, "ini": "2026-09-15", "fim": "2027-09-14", "atual": True}
    usinas = [
        {"uid": 1, "usina": "Zeta 1", "mwp": 3.0,
         "meses": {"2026-10": {"pr": 75.0, "disp": 96.0}, "2026-11": {"pr": 79.0, "disp": 99.0}},
         "com_expurgo": {"2026-10": {"disp": 97.5}, "2026-11": {"disp": 99.0}}},
        {"uid": 2, "usina": "Zeta 2", "mwp": 1.0, "meses": {"2026-10": {"pr": 82.0, "disp": 99.5}}, "com_expurgo": {}}]
    pcm = {1: {"MPM": {"2026-09": [1, 1], "2026-10": [0, 1], "2026-11": [0, 1]}, "MPS": {"2026-10": [1, 1]}},
           2: {"MPM": {"2026-10": [1, 1]}}}
    zel = {1: {"rocada": ["2026-09-20", "2026-10-03", "2026-10-28", "2025-01-01"], "lavagem": []}}
    zel_min = {1: {"rocada": 4, "lavagem": 2}, 2: {}}
    contrato = {"meta_pr": 78.0, "meta_disp": 98.0}
    base = dict(contrato=contrato, ficha=None, ano=ano, usinas=usinas, pcm=pcm, zel=zel, zel_min=zel_min, hoje=HOJE,
                meses_com_dado={"2026-10", "2026-11"})
    base.update(k)
    return I.montar(**base)


def _linha(u, i):
    return next(l for l in u["linhas"] if l["id"] == i)


def test_a_matriz_do_ano_contratual():
    d = _montar()
    assert [m["rot"] for m in d["meses"]][:3] == ["set/26", "out/26", "nov/26"] and len(d["meses"]) == 12
    z1 = next(u for u in d["usinas"] if u["uid"] == 1)
    assert d["usinas"][0]["uid"] == 1                                   # a com problema primeiro
    mpm = _linha(z1, "MPM")["cels"]
    assert (mpm["2026-09"]["tom"], mpm["2026-10"]["tom"], mpm["2026-11"]["tom"]) == ("ok", "critico", "")   # o mês em curso não é falta
    assert mpm["2026-12"]["txt"] == "—"
    pr = _linha(z1, "pr")["cels"]
    assert pr["2026-09"]["txt"] == "s/d"                                 # antes de 10/2026: sem dado, nunca 0
    assert pr["2026-10"]["tom"] == "critico" and pr["2026-11"]["tom"] == "ok"
    assert pr["2027-01"]["txt"] == ""                                    # o que ainda não chegou fica em branco
    disp = _linha(z1, "disp")["cels"]
    assert disp["2026-10"]["txt"] == "97,5*" and disp["2026-10"]["tom"] == "info" and "96,0" in disp["2026-10"]["dica"]
    assert disp["2026-11"]["txt"] == "99,0" and disp["2026-11"]["tom"] == "ok"
    roc = _linha(z1, "rocada")
    assert roc["cels"]["2026-10"]["txt"] == "03/10 +1" and roc["acum"]["txt"] == "3/4" and roc["acum"]["tom"] == "alerta"
    assert _linha(z1, "lavagem")["acum"]["txt"] == "0/2"
    # o total: preventivas somadas, o PR do mês pela potência
    tot = {l["id"]: l for l in d["total"]}
    assert tot["MPM"]["cels"]["2026-10"]["txt"] == "1/2"
    assert tot["pr"]["cels"]["2026-10"]["txt"] == "76,8"                 # (75 × 3 + 82 × 1) / 4
    assert d["resumo"]["prev"]["MPM"] == [2, 4] and d["resumo"]["fora_pr"] == 1


def test_sem_meta_a_celula_fica_sem_cor():
    d = _montar(contrato={})
    z1 = next(u for u in d["usinas"] if u["uid"] == 1)
    assert _linha(z1, "pr")["cels"]["2026-10"]["tom"] == "" and d["resumo"]["fora_pr"] == 0


@pytest.fixture
def relogio(monkeypatch):
    from nexus.campo import visao
    monkeypatch.setattr(visao, "_agora", lambda: datetime(2026, 11, 26, 10, 0))


def test_a_rota_dos_indicadores(carga, cliente, relogio, monkeypatch):  # noqa: F811
    from nexus.torres.comando import contratos_tela as CT
    from nexus.torres.comando import gerencial_tela as GT
    adm = _como(cliente, "admin@gridco.com.br", admin=True)
    # a conta da Visão gerencial ainda montando: a página pede de novo
    monkeypatch.setattr(GT, "dados_gerencial_sem_esperar", lambda: None)
    assert adm.get("/t/comando/contratos/indicadores.json", query_string={"cliente": "Solar Alfa"}).get_json() == {"ok": True, "montando": True}
    g = {"meses": [{"id": "2026-11"}, {"id": "2026-10"}], "avisos": ["o COS (a coluna Agora)"],
         "clientes": [{"cliente": "SOLAR ALFA", "usinas": [{"uid": 7, "usina": "Zeta 1", "mwp": 2.0,
                                                           "meses": {"2026-10": {"pr": 80.0, "disp": 99.0}}, "com_expurgo": {}}]}]}
    monkeypatch.setattr(GT, "dados_gerencial_sem_esperar", lambda: g)
    monkeypatch.setattr(CT, "_fontes_da_ligacao", lambda cli, uids, ano: (
        {7: {"MPM": {"2026-10": [1, 1]}}}, {}, {7: {}}, {"pcm": {"ligadas": 1, "total": 2}}, []))
    cliente.application.extensions.pop("nexus_contratos_indicadores", None)
    d = adm.get("/t/comando/contratos/indicadores.json", query_string={"cliente": "Solar Alfa"}).get_json()
    # o padrão são os últimos 12 meses até o mês de hoje (Levi: "puxa pelos últimos 12 meses até atualmente")
    assert d["ano"] == {"n": 0, "ini": "2025-12-01", "fim": "2026-11-30", "atual": True, "rolante": True}
    assert [m["rot"] for m in d["meses"]][0] == "dez/25" and [m["rot"] for m in d["meses"]][-1] == "nov/26"
    assert [a["n"] for a in d["anos"]] == [1, 2] and d["anos"][1]["ini"] == "2026-02-25"   # os anos contratuais, para consultar
    assert d["usinas"][0]["usina"] == "Zeta 1" and d["ligacao"]["pcm"] == {"ligadas": 1, "total": 2}
    assert "o COS (a coluna Agora)" not in d["avisos"]                    # o aviso de outra fonte da Visão gerencial não entra
    d1 = adm.get("/t/comando/contratos/indicadores.json", query_string={"cliente": "Solar Alfa", "ano": 1}).get_json()
    assert d1["ano"] == {"n": 1, "ini": "2025-02-25", "fim": "2026-02-24", "atual": False} and d1["ano_fechado"]
    assert adm.get("/t/comando/contratos/indicadores.json", query_string={"cliente": "Ninguém"}).status_code == 404
    # o contrato traz o aniversário e o ano contratual
    c = next(x for x in adm.get("/t/comando/contratos/dados.json").get_json()["contratos"] if x["cliente"] == "Solar Alfa")
    assert c["aniversario"] == "2027-02-25" and c["ano_contratual"]["n"] == 2


def test_os_ultimos_12_meses_andam_sozinhos():
    assert I.ultimos_12_meses(date(2026, 11, 26)) == {"n": 0, "ini": "2025-12-01", "fim": "2026-11-30", "atual": True, "rolante": True}
    assert I.ultimos_12_meses(date(2027, 1, 5))["ini"] == "2026-02-01" and I.ultimos_12_meses(date(2027, 1, 5))["fim"] == "2027-01-31"
    assert I.ultimos_12_meses(date(2026, 12, 31))["fim"] == "2026-12-31"


def test_a_tela_dos_indicadores(cliente):
    r = cliente.get("/static/contratos.js")
    js = r.get_data(as_text=True)
    r.close()
    for t in ('["indicadores", "Indicadores"]', "function rIndicadores(c)", "indicadores.json?cliente=", "function fatoAniv(c)",
              '"Só KPIs"', '"Só manutenções"', "data-ind-ano", "data-ind-usina", "sem dado no banco", "Últimos 12 meses", "ind-cinco"):
        assert t in js, t


def test_o_pr_acima_de_100_e_leitura_errada_e_os_cartoes_do_alto():
    """Na 1ª prévia (26/11/2026) uma usina com PR de mais de 1.000% fez o PR do contrato dar 730,5%: fica fora, com a dica.
    E o resumo dos quatro cartões do mockup: as barrinhas do mês a mês, os meses abaixo da meta, a disponibilidade sem o
    expurgo, as cores das preventivas e a usina que mais pesa."""
    us = [{"uid": 1, "usina": "Zeta 1", "mwp": 1.0, "meses": {"2026-10": {"pr": 1375.5, "disp": 96.0}}, "com_expurgo": {"2026-10": {"disp": 99.0}}}]
    d = _montar(usinas=us)
    pr = _linha(d["usinas"][0], "pr")["cels"]["2026-10"]
    assert pr["txt"] == "s/d" and "leitura errada" in pr["dica"]
    r = _montar()["resumo"]
    assert [b["tom"] for b in r["pr_barras"][:4]] == ["vazio", "alerta", "ok", "futuro"]       # out/26: 76,8 contra 78
    assert r["pr_abaixo"] == ["out/26"] and r["disp_sem_expurgo"] == "98,0"   # out/26 96,9 e nov/26 99,0, sem o expurgo
    assert r["prev_tom"]["MPM"] == "alerta" and r["pior"] == {"usina": "Zeta 1", "fora": 2}

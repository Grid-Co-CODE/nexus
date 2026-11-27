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
    # o PR lido do PDF saiu: a meta de PR é a da BD Performance, por usina e mês (Levi, 26/11/2026)
    assert m["disp"]["pct"] == 98.5 and m["pr"] is None
    m = I.metas({"meta_pr": 80.0}, ficha)
    assert m["pr"] == {"pct": 80.0, "origem": "dos Dados do contrato"}
    # sem garantia no contrato: 99% (Levi: "As que faltam, bota 99%")
    assert I.metas({}, None) == {"pr": None, "disp": {"pct": 99.0, "origem": "padrão da Grid (99%)"}}


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
    pr = _linha(z1, "pr_exp")["cels"]
    assert pr["2026-09"]["txt"] == "s/d"                                 # antes de 10/2026: sem dado, nunca 0
    assert pr["2026-10"]["tom"] == "critico" and pr["2026-11"]["tom"] == "ok"
    assert pr["2027-01"]["txt"] == ""                                    # o que ainda não chegou fica em branco
    # a disponibilidade em duas linhas (27/11/2026): sem o expurgo e com ele, cada uma contra a garantia
    # só a expurgada na tabela (27/11/2026: "Mostra só expurgada"); o original na dica e na gaveta
    assert [l["id"] for l in z1["linhas"] if l["grupo"] == "kpi"] == ["pr_exp", "disp_exp"]
    dexp = _linha(z1, "disp_exp")["cels"]
    assert (dexp["2026-10"]["txt"], dexp["2026-10"]["tom"]) == ("97,5", "alerta") and "o original (sem o expurgo) 96,0%" in dexp["2026-10"]["dica"]
    assert dexp["2026-11"]["txt"] == "99,0" and dexp["2026-11"]["tom"] == "ok" and "não mudou" in dexp["2026-11"]["dica"]
    roc = _linha(z1, "rocada")
    assert roc["cels"]["2026-10"]["txt"] == "03/10 +1" and roc["acum"]["txt"] == "3/4" and roc["acum"]["tom"] == "alerta"
    assert _linha(z1, "lavagem")["acum"]["txt"] == "0/2"
    # o total: preventivas somadas, o PR do mês pela potência
    tot = {l["id"]: l for l in d["total"]}
    assert tot["MPM"]["cels"]["2026-10"]["txt"] == "1/2"
    assert tot["pr_exp"]["cels"]["2026-10"]["txt"] == "76,8"             # (75 × 3 + 82 × 1) / 4
    assert tot["pr_exp"]["nome"] == "PR expurgado" and "pr" not in tot and "disp" not in tot
    assert d["resumo"]["prev"]["MPM"] == [2, 4] and d["resumo"]["fora_pr"] == 1


def test_sem_meta_a_celula_fica_sem_cor():
    d = _montar(contrato={})
    z1 = next(u for u in d["usinas"] if u["uid"] == 1)
    assert _linha(z1, "pr_exp")["cels"]["2026-10"]["tom"] == "" and d["resumo"]["fora_pr"] == 0


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
    monkeypatch.setattr(CT, "_metas_pr_bd", lambda uids, nomes: {7: {"2026-10": 82.0}})
    from nexus.campo import visao as _v
    monkeypatch.setattr(_v, "_Base", lambda: None)
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
              '"Só KPIs"', '"Só manutenções"', "data-ind-ano", "data-ind-usina", "sem dado no banco", "Últimos 12 meses", "ind-cinco", "data-cel", "function abrirGaveta(c, cel)", "data-os-abrir", "NexusOsCard", "pr_exp", "disp_exp", "atrasada"):
        assert t in js, t
    assert "As leituras das rondas" not in js and "nível 1 a 5" not in js          # a ronda saiu (27/11/2026)


def test_o_pr_acima_de_100_e_leitura_errada_e_os_cartoes_do_alto():
    """Na 1ª prévia (26/11/2026) uma usina com PR de mais de 1.000% fez o PR do contrato dar 730,5%: fica fora, com a dica.
    E o resumo dos quatro cartões do mockup: as barrinhas do mês a mês, os meses abaixo da meta, a disponibilidade sem o
    expurgo, as cores das preventivas e a usina que mais pesa."""
    us = [{"uid": 1, "usina": "Zeta 1", "mwp": 1.0, "meses": {"2026-10": {"pr": 1375.5, "disp": 96.0}}, "com_expurgo": {"2026-10": {"disp": 99.0}}}]
    d = _montar(usinas=us)
    pr = _linha(d["usinas"][0], "pr_exp")["cels"]["2026-10"]
    assert pr["txt"] == "s/d" and "leitura errada" in pr["dica"]
    r = _montar()["resumo"]
    assert [b["tom"] for b in r["pr_barras"][:4]] == ["vazio", "alerta", "ok", "futuro"]       # out/26: 76,8 contra 78
    assert r["pr_abaixo"] == ["out/26"] and r["disp_sem_expurgo"] == "98,0"   # out/26 96,9 e nov/26 99,0, sem o expurgo
    assert r["prev_tom"]["MPM"] == "alerta" and r["pior"] == {"usina": "Zeta 1", "fora": 2}


def test_a_gaveta_da_celula_explica_com_as_os(carga, cliente, relogio, monkeypatch):  # noqa: F811
    """A célula clicada abre a gaveta (Levi, 26/11/2026: "aparecesse a confirmação da resposta no card lateral [...] qual é
    a OS [...] A OS clicável"): as OS do mês com o estado e o id do card, o PR usina a usina com a meta."""
    from types import SimpleNamespace

    from nexus.campo import responsaveis as R
    from nexus.campo import visao
    from nexus.pcm import fonte as PF
    from nexus.torres.comando import gerencial_tela as GT
    adm = _como(cliente, "admin@gridco.com.br", admin=True)
    g = {"meses": [{"id": "2026-11"}, {"id": "2026-10"}], "avisos": [],
         "clientes": [{"cliente": "SOLAR ALFA", "usinas": [{"uid": 7, "usina": "Zeta 1", "mwp": 2.0,
                                                           "meses": {"2026-10": {"pr": 80.0, "pr_prev": 79.0, "disp": 97.0}},
                                                           "com_expurgo": {"2026-10": {"disp": 98.5}}, "score": {}}]}]}
    monkeypatch.setattr(GT, "dados_gerencial_sem_esperar", lambda: g)
    monkeypatch.setattr(visao, "_Base", lambda: None)

    class Nomes:
        def __init__(self, b):
            pass

        def usina(self, nome, fracttal="", codigo=""):
            return (7, "nome") if nome == "Zeta 1" else (None, None)
    monkeypatch.setattr(R, "Nomes", Nomes)
    tarefas = [{"tarefa": "MPM - Preventiva mensal", "dataProg": "2026-10-10", "estado": "Finalizada", "os": "123", "idWO": 999,
                "dataFinal": "2026-10-11", "usina": "Zeta 1"},
               {"tarefa": "MPM - Preventiva mensal", "dataProg": "2026-10-20", "estado": "Em Processo", "os": "124", "idWO": 1000, "usina": "Zeta 1"},
               {"tarefa": "MPM - Preventiva mensal", "dataProg": "2026-10-20", "estado": "Finalizada", "os": "125", "usina": "Outra"}]
    monkeypatch.setattr(PF, "ler_gestao_sem_esperar", lambda cfg: SimpleNamespace(dados={"tarefas": tarefas}))
    q = {"cliente": "Solar Alfa", "uid": "7", "linha": "MPM", "mes": "2026-10"}
    d = adm.get("/t/comando/contratos/indicadores/celula.json", query_string=q).get_json()
    assert [o["os"] for o in d["os"]] == ["124", "123"]                        # a aberta primeiro; a da outra usina não entra
    assert d["os"][1]["id"] == 999 and d["os"][1]["final"] == "2026-10-11"
    assert {n["rot"]: n["val"] for n in d["numeros"]} == {"OS": "2", "Tarefas feitas": "1", "Tarefas planejadas": "2", "Tarefas abertas": "1"}
    d = adm.get("/t/comando/contratos/indicadores/celula.json", query_string=dict(q, uid="t", linha="disp_exp", mes="acum")).get_json()
    assert d["usinas"][0]["val"] == "98,5%" and "original 97,0%" in d["usinas"][0]["extra"]
    d = adm.get("/t/comando/contratos/indicadores/celula.json", query_string=dict(q, uid="t", linha="disp", mes="acum")).get_json()
    assert d["usinas"][0]["val"] == "97,0%" and "Sem o expurgo" in d["fonte"]
    assert any("Antes de 10/2026" in x for x in d["textos"])
    assert adm.get("/t/comando/contratos/indicadores/celula.json", query_string=dict(q, linha="nada")).status_code == 404
    assert adm.get("/t/comando/contratos/indicadores/celula.json", query_string=dict(q, uid="8")).status_code == 404
    assert adm.get("/t/comando/contratos/indicadores/celula.json", query_string=dict(q, mes="2020-01")).status_code == 404


def test_a_meta_de_pr_da_bd_e_as_linhas_da_tabela():
    """A meta de PR por usina e mês da BD Performance (Levi, 26/11/2026: "As metas de PR, você vai entrar na BD
    Performance"); as linhas desde 27/11/2026: o PR e a disponibilidade sem e com o expurgo, sem a ronda ("Sobre sujidade e
    vegetação na ronda, não importa isso daí não")."""
    d = _montar(contrato={}, metas_pr={1: {"2026-10": 78.0, "2026-11": 78.0}, 2: {"2026-10": 80.0}})
    z1 = next(u for u in d["usinas"] if u["uid"] == 1)
    pr = _linha(z1, "pr_exp")["cels"]
    assert pr["2026-10"]["tom"] == "critico" and "meta 78,0%" in pr["2026-10"]["dica"] and pr["2026-11"]["tom"] == "ok"
    assert d["metas"]["pr"]["origem"].startswith("da BD Performance") and d["metas"]["disp"]["pct"] == 99.0
    ordem = ["MPM", "MPS", "MPA", "rocada", "lavagem", "pr_exp", "disp_exp"]
    assert [l["id"] for l in z1["linhas"]] == ordem and [l["id"] for l in d["total"]] == ordem
    tot = {l["id"]: l for l in d["total"]}
    assert [tot[k]["nome"] for k in ("pr_exp", "disp_exp")] == ["PR expurgado", "Disponibilidade expurgada"]
    # o PR do contrato no mês contra a meta do mês pela potência: (78 × 3 + 80 × 1) / 4 = 78,5; o PR 76,8 fica amarelo
    assert tot["pr_exp"]["cels"]["2026-10"]["tom"] == "alerta" and "78,5" in tot["pr_exp"]["cels"]["2026-10"]["dica"]


def test_os_servicos_de_zeladoria_como_o_historico_do_radar():
    """A lavagem e a roçada como o Histórico de Serviços do Radar as junta (Levi, 26/11/2026: "a lavagem de módulos está
    na parte de zeladoria [...] em histórico de serviços"): o histórico, a cotação executada, a rota e a OS de contrato;
    o mesmo serviço no mesmo dia vale uma vez (o do app vence a planilha); o futuro e o sem data ficam fora."""
    abas = {
        "usinas": [{"id": 1, "usina": "ZETA UM - SOLAR", "codigo": "ZT1", "cliente": "Solar Alfa"}],
        "servicos_zeladoria": [{"usina_id": 1, "tipo": "LIMPEZA DE MÓDULOS", "data_termino": "2026-09-10", "origem": "planilha_historica"},
                               {"usina_id": 1, "tipo": "ROÇAGEM", "data_termino": "2026-08-01", "origem": "manual", "excluido": True}],
        "cotacoes": [{"usina": "Zeta Um - Solar", "servico": "LIMPEZA DE MÓDULOS", "data_execucao_fim": "2026-09-10", "numero_os": "501"}],
        "rota_equipe": [{"usina_id": 1, "servicos": ["ROÇAGEM"], "etapas": {"ROÇAGEM": {"dataExecucaoFim": "2026-10-20", "numeroOs": "777"}}},
                        {"usina_id": 1, "servicos": ["ROÇAGEM"], "etapas": {}, "concluida": False, "data_fim": "2026-10-25"}],
        "contrato_os": [{"usina_id": "1", "servico": "LIMPEZA DE MÓDULOS", "data_execucao_fim": "2026-11-05", "numero_os": "888"},
                        {"usina_id": "1", "servico": "LIMPEZA DE MÓDULOS", "data_execucao_fim": "2026-12-20"}]}
    s = I.servicos_do_radar(abas, "2026-11-26")
    assert [(x["tipo"], x["data"], x["rotulo"], x["os"]) for x in s] == [
        ("lavagem", "2026-09-10", "cotação fechada", "501"),          # a cotação (app) vence a planilha no mesmo dia
        ("rocada", "2026-10-20", "rota da equipe", "777"),
        ("lavagem", "2026-11-05", "OS de contrato", "888")]
    assert all(x["codigo"] == "ZT1" for x in s)


def test_a_lavagem_e_a_supressao_nas_os_do_fracttal():
    """As OS finalizadas do Fracttal somam ao Radar (26/11/2026: o Radar tinha 18 lavagens no ano; o Fracttal, 56 tarefas
    de limpeza de módulos finalizadas): a inspeção pré-lavagem não é lavagem; a OS a até 10 dias de um serviço já
    contado é o mesmo serviço; duas tarefas da mesma OS contam uma vez."""
    assert I.tipo_da_tarefa("Acompanhamento - Limpeza de Módulos") == "lavagem"
    assert I.tipo_da_tarefa("Acompanhamento - Supressão Vegetal") == "rocada"
    assert I.tipo_da_tarefa("Inspeção de integridade dos módulos pré-lavagem") is None
    assert I.tipo_da_tarefa("Troca de string box") is None
    assert I.tipo_da_tarefa("") is None
    radar = [{"tipo": "lavagem", "data": "2026-09-10", "rotulo": "cotação fechada", "os": "501"}]
    frac = [{"tipo": "lavagem", "data": "2026-09-15", "os": "9001"},     # 5 dias do Radar: o mesmo serviço
            {"tipo": "lavagem", "data": "2026-11-02", "os": "9002"},
            {"tipo": "lavagem", "data": "2026-11-02", "os": "9002"},     # outra tarefa da mesma OS
            {"tipo": "lavagem", "data": "2026-11-08", "os": "9003"},     # 6 dias da 9002: a mesma lavagem
            {"tipo": "rocada", "data": "2026-09-12", "os": "9004"}]      # outro tipo: conta
    s = I.juntar_servicos(radar, frac)
    assert [(x["tipo"], x["data"], x["os"]) for x in s] == [
        ("lavagem", "2026-09-10", "501"), ("rocada", "2026-09-12", "9004"), ("lavagem", "2026-11-02", "9002")]


def test_o_pr_expurgado_e_a_lavagem_pelo_prazo_do_contrato():
    """Levi, 27/11/2026: "Eu tô sentindo falta do PR ponderado, PR expurgado"; "Disponibilidade expurgada também, mesma
    lógica"; e da supressão e da lavagem: "tem que ser a data que foi feita [...] E não feita, a depender do prazo do
    contrato". O mês com o serviço mostra a data; sem ele, "atrasada" quando o prazo do contrato (o mínimo do ano: 2 por ano
    = a cada 6 meses) venceu desde a última; sem prazo no contrato, a dica diz a última; antes do arquivo do PCM, s/d."""
    usinas = [{"uid": 1, "usina": "Zeta 1", "mwp": 3.0,
               "meses": {"2026-10": {"pr": 74.0, "disp": 99.0}, "2026-11": {"pr": 76.0, "disp": 99.0}},
               "com_expurgo": {"2026-10": {"disp": 99.0, "pr": 75.0}, "2026-11": {"disp": 99.0, "pr": 76.0}}},
              {"uid": 2, "usina": "Zeta 2", "mwp": 1.0, "meses": {}, "com_expurgo": {}}]
    zel = {1: {"lavagem": ["2026-03-10", "2026-11-12"], "rocada": []}, 2: {"lavagem": ["2026-10-05"]}}
    d = _montar(usinas=usinas, zel=zel, zel_min={1: {"lavagem": 2, "rocada": 4}, 2: {}}, zel_desde="2026-09")
    z1 = next(u for u in d["usinas"] if u["uid"] == 1)
    pe = _linha(z1, "pr_exp")["cels"]
    assert pe["2026-10"]["txt"] == "75,0" and "o original (sem o expurgo) 74,0%" in pe["2026-10"]["dica"]
    assert pe["2026-11"]["txt"] == "76,0" and "não mudou" in pe["2026-11"]["dica"]
    lav, roc = _linha(z1, "lavagem")["cels"], _linha(z1, "rocada")["cels"]
    # a última em 10/03 e uma a cada 6 meses: venceu em 10/09
    assert (lav["2026-09"]["txt"], lav["2026-09"]["tom"]) == ("atrasada", "critico") and "venceu em 10/09/26" in lav["2026-09"]["dica"]
    assert lav["2026-10"]["txt"] == "atrasada" and (lav["2026-11"]["txt"], lav["2026-11"]["tom"]) == ("12/11", "ok")
    assert "a próxima vence em 12/05/27" in lav["2026-11"]["dica"] and lav["2026-12"]["txt"] == ""
    # nenhuma roçada desde o 1º mês do arquivo do PCM (set/26) e uma a cada 3 meses: ainda no prazo em nov/26
    assert roc["2026-11"]["txt"] == "—" and "vence em 01/12/26" in roc["2026-11"]["dica"]
    z2 = next(u for u in d["usinas"] if u["uid"] == 2)
    l2 = _linha(z2, "lavagem")["cels"]
    assert l2["2026-10"]["txt"] == "05/10" and l2["2026-11"]["txt"] == "—"
    assert "a última em 05/10/26" in l2["2026-11"]["dica"] and "não traz o prazo" in l2["2026-11"]["dica"]
    tot = {l["id"]: l for l in d["total"]}
    assert (tot["lavagem"]["cels"]["2026-10"]["txt"], tot["lavagem"]["cels"]["2026-10"]["tom"]) == ("1 atras.", "critico")
    assert (tot["lavagem"]["cels"]["2026-11"]["txt"], tot["lavagem"]["cels"]["2026-11"]["tom"]) == ("1", "ok")
    r = d["resumo"]
    assert (r["pr"], r["pr_sem_expurgo"]) == ("75,5", "75,0")              # o original no cartão, só porque mudou
    assert I.passo_do_contrato(2) == 6 and I.passo_do_contrato(4) == 3 and I.passo_do_contrato(None) is None
    # o relógio começa no início da vigência: o contrato que começou em 20/10 não deve a lavagem vencida em setembro
    d = _montar(contrato={"inicio": "2026-10-20"}, usinas=usinas, zel=zel, zel_min={1: {"lavagem": 2, "rocada": 4}, 2: {}},
                zel_desde="2026-01")
    lav = _linha(next(u for u in d["usinas"] if u["uid"] == 1), "lavagem")["cels"]
    assert lav["2026-09"]["txt"] == "—" and "antes do início da vigência" in lav["2026-09"]["dica"]
    assert lav["2026-10"]["txt"] == "—" and "vence em 20/04/27" in lav["2026-10"]["dica"]

"""Os expurgos do contrato na nota de cumprimento (22/11/2026). Levi, 19/11/2026: "una as informações de contrato, enfim,
Nexus Insights, e aí aplique esses expurgos que estão no relatório"; a ordem combinada: 1) o cadastro das limitações,
2) o cálculo dos expurgos na nota do contrato, 3) o cruzamento com a planilha de tickets. Em 22/11: "agora segue com o
cálculo dos expurgos".

O que estes testes seguram: cada contrato diz o que expurga pela PRÓPRIA cláusula de exclusão (as cinco categorias da
lista da Grid; contrato sem cláusula não expurga nada) e a que se aplica (disponibilidade, PR ou os dois); a queda da
rede sai das OS de religamento (a família "por queda" da disponibilidade) e a limitação imposta, do cadastro (só a sem
responsabilidade da Grid); a disponibilidade devolve as horas expurgadas, a geração e o PR somam a energia expurgada;
cada item diz o que saiu, a cláusula e o número sem o expurgo. Contratos e números de mentira."""
from datetime import datetime, timedelta, timezone

from nexus.comando import expurgos as E
from nexus.comando import gerencial as G

BRT = timezone(timedelta(hours=-3))


def _ficha(*regras):
    return {"contratos": [{"regras": [dict(categoria=c, nome=n, vigente=t, ref={"clausula": cl}) for c, n, t, cl in regras]}]}


DISP = ("Disponibilidade e desempenho", "Exclusões da disponibilidade",
        "Saem do tempo planejado: força maior; paradas da rede pedidas por agentes externos; melhorias a pedido da "
        "contratante; garantias do fabricante fora das paradas; falta de equipamento que cabe à contratante.", "8.3.3")
PR = ("Disponibilidade e desempenho", "Exclusões do cálculo do PR",
      "Saem da base do PR os períodos causados por eventos da concessionária e caso fortuito/força maior.", "6.2")
CURT = ("Disponibilidade e desempenho", "Curtailment",
        "Limitação de geração imposta pela distribuidora pode ser ajuste no PR, se comprovada.", "A.5.1")
AVISO = ("Disponibilidade e desempenho", "Aviso de evento de exclusão em 24 h",
         "Comunicar em até 24 h qualquer evento que possa ser exclusão; sem o aviso, a exclusão não é admitida.", "C.2.4")
FORMULA = ("Disponibilidade e desempenho", "Fórmula da disponibilidade", "Tempo realizado / planejado × 100.", "8.3.3")
OUTRA = ("Rescisão", "Força maior acima de 180 dias", "Força maior por mais de 180 dias permite rescindir.", "14")


# ── o que cada contrato expurga ─────────────────────────────────────────────────────────────────────────────────────
def test_o_contrato_diz_o_que_expurga_pela_propria_clausula():
    c = E.do_contrato(_ficha(DISP, FORMULA, OUTRA))
    assert set(c["cats"]) == {"rede", "forca_maior", "contratante", "fabricante"}
    assert c["cats"]["rede"]["alvos"] == ["disp"]
    assert c["cats"]["rede"]["regras"] == [{"nome": "Exclusões da disponibilidade", "clausula": "8.3.3"}]
    assert "limitacao" not in c["cats"]                  # a cláusula não fala de limitação imposta


def test_a_exclusao_do_pr_e_o_curtailment_valem_para_o_pr():
    c = E.do_contrato(_ficha(PR, CURT, AVISO))
    assert c["cats"]["rede"]["alvos"] == ["pr"] and c["cats"]["forca_maior"]["alvos"] == ["pr"]
    assert c["cats"]["limitacao"]["alvos"] == ["pr"]
    assert c["condicoes"] == [{"nome": "Aviso de evento de exclusão em 24 h", "clausula": "C.2.4"}]


def test_contrato_sem_clausula_de_exclusao_nao_expurga_nada():
    assert E.do_contrato(_ficha(FORMULA, OUTRA))["cats"] == {}
    assert E.do_contrato(None)["cats"] == {}


# ── a queda da rede, pelas OS de religamento ────────────────────────────────────────────────────────────────────────
def test_a_queda_da_rede_sai_das_os_de_religamento_pela_potencia_afetada():
    dia = [{"mes": "2026-11", "dia": f"2026-11-{d:02d}", "usina": "Usina A", "usina_fracttal": "UA", "pot_kwp": 1000}
           for d in range(1, 31)]
    os_ = [{"mes": "2026-11", "os": "101", "usina": "Usina A", "usina_fracttal": "UA", "origem": "queda", "kwp": 500,
            "duracao_sol_min": 240, "perda_kwh": 2000},
           {"mes": "2026-11", "os": "102", "usina": "Usina A", "usina_fracttal": "UA", "origem": "equipamento", "kwp": 1000,
            "duracao_sol_min": 600, "perda_kwh": 10000},
           {"mes": "2026-10", "os": "90", "usina": "Usina A", "usina_fracttal": "UA", "origem": "queda", "kwp": 1000,
            "duracao_sol_min": 600, "perda_kwh": 10000}]
    r = E.rede_por_usina(os_, dia, "2026-11", lambda nome, fracttal: 7 if nome == "Usina A" else None)
    assert set(r) == {7}
    assert round(r[7]["h_eq"], 3) == 2.0                 # 500 de 1000 kWp por 4 h
    assert round(r[7]["delta_disp"], 4) == round(100 * 2 / (12 * 30), 4)
    assert r[7]["kwh"] == 2000 and r[7]["os"] == ["101"]


# ── a limitação imposta, pelo cadastro ──────────────────────────────────────────────────────────────────────────────
def test_as_horas_de_sol_contam_so_06_as_18():
    ini, fim = datetime(2026, 11, 10, 8, tzinfo=BRT), datetime(2026, 11, 12, 10, tzinfo=BRT)
    assert E.horas_de_sol(ini, fim, datetime(2026, 11, 1, tzinfo=BRT), datetime(2026, 12, 1, tzinfo=BRT)) == 26.0
    # o pedaço fora do mês não conta
    assert E.horas_de_sol(ini, fim, datetime(2026, 11, 11, tzinfo=BRT), datetime(2026, 12, 1, tzinfo=BRT)) == 16.0


def test_so_a_limitacao_sem_responsabilidade_da_grid_e_com_a_potencia_entra():
    ini, fim = datetime(2026, 11, 1, tzinfo=BRT), datetime(2026, 11, 3, tzinfo=BRT)
    base = dict(situacao="em_andamento", fim=None, inicio=datetime(2026, 11, 1, 6, tzinfo=BRT), usina_id=7)
    lista = [dict(base, limitacao_id="a", responsabilidade="nao", kw_limitados=50.0),
             dict(base, limitacao_id="b", responsabilidade="sim", kw_limitados=80.0),
             dict(base, limitacao_id="c", responsabilidade="parcial", kw_limitados=30.0),
             dict(base, limitacao_id="d", responsabilidade="nao", kw_limitados=None)]
    r = E.limitacao_por_usina(lista, ini, fim)
    assert r[7]["kwh"] == 50.0 * 24                      # dois dias de 12 h de sol
    assert r[7]["ids"] == ["a"] and r[7]["sem_potencia"] == 1


# ── a nota com o expurgo ────────────────────────────────────────────────────────────────────────────────────────────
GARANTIA = {"pct": 98.0, "nome": "Disponibilidade mínima", "texto": "98%", "clausula": "5.1"}


def test_a_disponibilidade_devolve_as_horas_expurgadas_e_diz_o_numero_sem_o_expurgo():
    cont = E.do_contrato(_ficha(DISP))
    ex = {"rede": {"h_eq": 5.4, "delta_disp": 1.5, "kwh": 2000.0, "os": ["101", "102"]}}
    m = {"disp": 96.0, "meta": 90.0, "pr": 75.0, "pr_prev": 80.0, "prod_kwh": 90000.0, "meta_kwh": 100000.0}
    s = G.nota_do_contrato(GARANTIA, m, {}, False, 4, expurgo=E.aplicar(cont, m, ex))
    disp = next(i for i in s["itens"] if i["nome"] == "Disponibilidade")
    assert disp["nota"] == 100 - 20 * 0.5                # 97,5% com o expurgo: meio ponto abaixo de 98
    assert "97,5%" in disp["mediu"] and "96,0%" in disp["expurgo"]
    assert "queda da rede" in disp["expurgo"] and "2 OS de religamento" in disp["expurgo"]
    assert "Exclusões da disponibilidade" in disp["expurgo"] and "8.3.3" in disp["expurgo"]
    ger = next(i for i in s["itens"] if i["nome"] == "Geração e PR")
    assert "expurgo" not in ger or not ger["expurgo"].startswith("Somad")   # a cláusula de disponibilidade não mexe no PR


def test_a_geracao_e_o_pr_somam_a_energia_expurgada():
    cont = E.do_contrato(_ficha(PR, CURT))
    ex = {"rede": {"h_eq": 2.0, "delta_disp": 0.5, "kwh": 2000.0, "os": ["101"]},
          "limitacao": {"kwh": 1000.0, "ids": ["a"], "sem_potencia": 0}}
    # a usina gerou 90 MWh com 1.000 kWp em 30 dias de 12 h de sol: 25% da nominal. Os 3 MWh à potência nominal viram
    # 0,75 MWh pela geração média dela (a energia à nominal inflava o PR; o relatório da Ana pondera pela irradiação)
    m = {"disp": 96.0, "meta": 90.0, "pr": 75.0, "pr_prev": 80.0, "prod_kwh": 90000.0, "meta_kwh": 100000.0,
         "pot_kwp": 1000.0, "dias": 30}
    a = E.aplicar(cont, m, ex)
    assert a["m"]["meta"] == 90.75                        # (90.000 + 750) / 100.000
    assert abs(a["m"]["pr"] - 75.0 * 90750 / 90000) < 0.01   # guardado com 2 casas
    assert a["m"]["disp"] == 96.0                         # o contrato só expurga do PR
    s = G.nota_do_contrato(None, m, {}, False, 4, expurgo=a)
    ger = next(i for i in s["itens"] if i["nome"] == "Geração e PR")
    assert "0,75 MWh" in ger["expurgo"] and "queda da rede: 0,50 MWh" in ger["expurgo"]
    assert "limitação imposta: 0,25 MWh" in ger["expurgo"] and "25% da potência nominal" in ger["expurgo"]
    assert "90,0%" in ger["expurgo"]                      # o número sem o expurgo


def test_sem_a_potencia_e_os_dias_a_energia_nao_entra():
    cont = E.do_contrato(_ficha(PR))
    m = {"meta": 90.0, "pr": 75.0, "prod_kwh": 90000.0, "meta_kwh": 100000.0}
    a = E.aplicar(cont, m, {"rede": {"h_eq": 2.0, "delta_disp": 0.5, "kwh": 2000.0, "os": ["101"]}})
    assert a["m"]["meta"] == 90.0 and a["m"]["pr"] == 75.0
    assert "sem a potência e os dias do mês" in a["ger"].lower()


def test_a_regra_que_diz_o_que_nao_e_expurgo_nao_vira_categoria():
    nega = ("Disponibilidade e desempenho", "Passivos de obra NÃO são expurgo",
            "Não conformidades e erro de projeto do fabricante não isentam a Contratada.", "2")
    assert E.do_contrato(_ficha(nega))["cats"] == {}


def test_sem_clausula_ou_sem_evento_a_nota_e_a_de_sempre_e_o_item_diz_por_que():
    m = {"disp": 96.0, "meta": 90.0, "pr": 75.0, "pr_prev": 80.0, "prod_kwh": 90000.0, "meta_kwh": 100000.0}
    sem = G.nota_do_contrato(GARANTIA, m, {}, False, 4)
    com = G.nota_do_contrato(GARANTIA, m, {}, False, 4, expurgo=E.aplicar(E.do_contrato(_ficha(FORMULA)), m, {}))
    assert [i["nota"] for i in sem["itens"]] == [i["nota"] for i in com["itens"]]
    disp = next(i for i in com["itens"] if i["nome"] == "Disponibilidade")
    assert disp["expurgo"] == "O contrato lido não traz cláusula de expurgo: nada sai da conta."
    com2 = G.nota_do_contrato(GARANTIA, m, {}, False, 4, expurgo=E.aplicar(E.do_contrato(_ficha(DISP)), m, {}))
    disp2 = next(i for i in com2["itens"] if i["nome"] == "Disponibilidade")
    assert "nenhuma queda da rede no mês" in disp2["expurgo"].lower()
    assert "força maior" in disp2["expurgo"] and "o Nexus ainda não registra" in disp2["expurgo"]


def test_o_expurgo_nunca_passa_de_100():
    cont = E.do_contrato(_ficha(DISP))
    m = {"disp": 99.5}
    a = E.aplicar(cont, m, {"rede": {"h_eq": 30.0, "delta_disp": 8.3, "kwh": 0.0, "os": ["1"]}})
    assert a["m"]["disp"] == 100.0


def test_a_montagem_aplica_o_expurgo_do_contrato_do_cliente():
    from datetime import date
    hoje = date(2026, 11, 22)
    ms = G.meses(hoje)
    fechado = next(m["id"] for m in ms if not m["atual"])
    us = [{"uid": 7, "usina": "Usina A", "cliente": "Cliente A", "codigo": "UA", "mwp": 1.0,
           "meses": {fechado: {"disp": 96.0, "meta": 90.0, "pr": 75.0, "pr_prev": 80.0, "prod_kwh": 90000.0,
                               "meta_kwh": 100000.0, "rondas": 4}}}]
    garantia = ("Disponibilidade e desempenho", "Disponibilidade mínima garantida", "Mínima de 98% ao mês.", "5.1")
    contratos = {"contratos": [{"cliente": "Cliente A"}], "fichas": {"Cliente A": _ficha(garantia, DISP)}}
    ex = {"rede": {fechado: {7: {"h_eq": 5.4, "delta_disp": 1.5, "kwh": 2000.0, "os": ["101"]}}}}
    d = G.montar(us, contratos, hoje, "agora", expurgos=ex)
    cli = d["clientes"][0]
    assert cli["expurga"] == ["queda da rede", "força maior", "pedido ou responsabilidade da contratante",
                              "garantia ou erro do fabricante"]
    disp = next(i for i in cli["usinas"][0]["score"][fechado]["itens"] if i["nome"] == "Disponibilidade")
    assert disp["nota"] == 90 and "97,5%" in disp["mediu"] and "Sem o expurgo: 96,0%" in disp["expurgo"]
    sem = G.montar(us, contratos, hoje, "agora")
    disp0 = next(i for i in sem["clientes"][0]["usinas"][0]["score"][fechado]["itens"] if i["nome"] == "Disponibilidade")
    assert disp0["nota"] == 60 and "Nenhuma queda da rede" in disp0["expurgo"]

"""A Zeladoria do Campo · App (Levi, 26/10/2026, com o modelo "Rondas Sujidade e Vegetação": "a evolução por usina deve
ser por cliente!"): as semanas, as leituras pela regra da aba Sujidade e vegetação, a zeladoria do Fracttal pelas três
tarefas do plano, as recomendações, a evolução por cliente e a tela com o banco falso."""
from datetime import date, timedelta

from test_campo_sujidade import NOTA
from test_campo_visao import banco  # noqa: F401  (fixture)

from nexus.campo import aprovacao, ronda_checklist, visao
from nexus.campo import zeladoria as Z
from nexus.dados.fatos import tarefa_chave

HOJE = date(2026, 10, 26)          # uma segunda-feira: a W44 começa hoje
LIMPEZA = tarefa_chave("Acompanhamento - Limpeza de Módulos (Termografia se aplicável)")
SUPRESSAO = tarefa_chave("Acompanhamento - Supressão Vegetal")
PODA = tarefa_chave("Acompanhamento - Poda Química")


def _usina(uid, nome, cliente):
    return {"usina_id": uid, "usina": nome, "cliente": cliente, "uf": "SP", "equipe": "SP Norte 01", "cidade": nome,
            "regiao_campo": "Sudeste 03", "gestor": "Gestor Um"}


def _ronda(uid, dia, os_=None, checklist=None, fim="10:00", tecnico="Fulano Souza", avulsa=False):
    return {"usina_id": uid, "data": dia, "fim": f"{dia}T{fim}:00", "os": os_, "checklist": checklist,
            "tecnico": tecnico, "tipo": "curta", "avulsa": avulsa}


def _resp(suj, veg, vala="Limpa"):
    return {"sujidade": suj, "vegetacao": veg, "vala": vala, "sombreamento": "", "dejeto": "", "sensores_sujos": []}


def _tarefa(uid, os_, chave, status_os, estado, prog=None, fim=None, tipo="zeladoria"):
    d = lambda iso: int(iso.replace("-", "")) if iso else None      # noqa: E731
    return {"usina_id": uid, "os": os_, "fracttal_os_id": 9000 + os_, "tarefa_chave": chave, "tipo_tarefa": tipo,
            "status_os": status_os, "estado_tarefa": estado, "data_id_programada": d(prog), "data_id_fim": d(fim)}


# ── semanas ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_semanas_de_segunda_a_domingo_como_no_pcm():
    assert Z.semana_de(HOJE) == "2026-W44" and Z.semana_de("2026-10-25") == "2026-W43"
    assert Z.segunda("2026-W43") == date(2026, 10, 19)
    assert Z.semanas_ate("2026-W44") == [f"2026-W{n}" for n in range(37, 45)]           # as 8 do modelo
    assert Z.rotulo("2026-W43") == "W43 · 19 a 25/10" and Z.rotulo("2026-W44") == "W44 · 26/10 a 01/11"
    # o filtro: a corrente primeiro e as anteriores cuja janela ainda tem leitura (o checklist fica 90 dias)
    assert Z.semanas_do_filtro(HOJE)[0] == "2026-W44" and len(Z.semanas_do_filtro(HOJE)) == Z.SEMANAS_NO_FILTRO == 5
    assert Z.semana_valida("2026-W42", HOJE) == "2026-W42"
    assert Z.semana_valida("2026-W30", HOJE) == "2026-W44" and Z.semana_valida("lixo", HOJE) == "2026-W44"


# ── leituras ────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_leituras_pela_regra_da_aba_sujidade_e_vegetacao():
    todas = [_ronda(1, "2026-10-20", os_="500"),
             _ronda(1, "2026-10-22", checklist=_resp(2, 3)),                   # sem OS: o checklist do fato
             _ronda(1, "2026-10-23"),                                           # sem OS e sem checklist: não é leitura
             _ronda(1, "2026-10-24", os_="501"),                                # OS sem resposta lida: não é leitura
             _ronda(2, "2026-10-21", os_="502"),
             _ronda(9, "2026-10-21", os_="500")]                                # usina fora da base
    resp = {"500": _resp(4, 5), "502": _resp(None, None)}
    lei = Z.leituras(todas, resp, [], {1, 2})
    assert set(lei) == {1}                                                      # a 502 não tem nenhum dos dois níveis
    assert [(x["data"], x["sujidade"], x["vegetacao"]) for x in lei[1]] == [("2026-10-20", 4, 5), ("2026-10-22", 2, 3)]


def test_validacao_por_foto_vale_no_lugar_das_rondas_do_dia():
    todas = [_ronda(1, "2026-10-20", os_="500", tecnico="Fulano Souza"), _ronda(1, "2026-10-21", os_="501")]
    resp = {"500": _resp(5, 5), "501": _resp(1, 1)}
    val = [{"usina_id": 1, "data": "2026-10-20", "tecnico": "Beltrana Lima", "validada": True, "sujidade": 3,
            "vegetacao": 2, "vala": "", "sombreamento": "", "sensores_sujos": [], "lancada_em": "2026-10-21T10:00"},
           {"usina_id": 1, "data": "2026-10-18", "tecnico": "Beltrana Lima", "validada": True, "sujidade": 4,
            "vegetacao": 4, "vala": "", "sombreamento": "", "sensores_sujos": [], "lancada_em": "2026-10-19T10:00"}]
    lst = Z.leituras(todas, resp, val, {1})[1]
    assert [(x["data"], x["validada"], x["sujidade"]) for x in lst] == [
        ("2026-10-18", True, 4), ("2026-10-20", True, 3), ("2026-10-21", False, 1)]
    assert lst[1]["os"] == "500" and lst[1]["revisa"] == [{"tecnico": "Fulano Souza", "os": "500"}]


def test_valor_da_semana_ultima_ou_pior():
    lst = [{"vegetacao": 4, "sujidade": 2}, {"vegetacao": 2, "sujidade": None}]
    assert Z.valor_da_semana(lst, "vegetacao", "ultima") == 2 and Z.valor_da_semana(lst, "vegetacao", "pior") == 4
    assert Z.valor_da_semana(lst, "sujidade", "ultima") == 2                   # a última que TEM o campo
    assert Z.valor_da_semana([], "sujidade") is None
    assert Z.REGRA_DA_SEMANA == "ultima"


# ── zeladoria do Fracttal ───────────────────────────────────────────────────────────────────────────────────────────
def test_zeladoria_pelas_tres_tarefas_do_plano():
    z = Z.zeladoria_por_usina([
        _tarefa(1, 10, LIMPEZA, "finalizada", "finalizada", "2026-10-01", "2026-10-05"),
        _tarefa(1, 11, SUPRESSAO, "em_verificacao", "finalizada", "2026-10-10", "2026-10-15"),
        _tarefa(1, 12, PODA, "em_processo", "em_progresso", "2026-10-20"),
        _tarefa(1, 13, LIMPEZA, "em_processo", "nao_iniciada", "2026-10-20"),
        _tarefa(1, 14, "outra-chave", "em_processo", "nao_iniciada", "2026-10-30"),
        _tarefa(1, 15, LIMPEZA, "em_processo", "nao_iniciada", "2026-10-20", tipo="preventiva"),   # não é zeladoria
    ], HOJE)[1]
    por_os = {x["os"]: x for x in z}
    assert set(por_os) == {10, 11, 12, 13, 14}
    assert (por_os[10]["tipo"], por_os[10]["situacao"], por_os[10]["fim"]) == ("limpeza", "feita", "2026-10-05")
    assert (por_os[11]["tipo"], por_os[11]["situacao"]) == ("supressao", "verificacao")
    assert (por_os[12]["tipo"], por_os[12]["situacao"]) == ("poda", "execucao")
    assert por_os[13]["situacao"] == "aberta" and por_os[13]["atrasada"] and por_os[13]["fim"] == ""
    assert por_os[14]["tipo"] == "outra" and not por_os[14]["atrasada"]
    assert Z.ultima_feita(z, {"supressao", "poda"})["os"] == 11 and Z.ultima_feita(z, {"limpeza"})["os"] == 10


def test_recomendacao_pede_acao_acima_de_3_e_olha_o_fracttal():
    lei = {"data": "2026-10-20", "vegetacao": 5, "sujidade": 4, "tecnico": "Fulano Souza"}
    # sem OS: a supressão imediata (venceu no dia da leitura) e a limpeza em até 7 dias
    recs = {r["campo"]: r for r in Z.recomendacoes(lei, [], HOJE)}
    assert recs["vegetacao"]["acao"] == "Supressão vegetal" and recs["vegetacao"]["status"] == "sem_os"
    assert recs["vegetacao"]["vence"] == "2026-10-20" and recs["vegetacao"]["atraso_dias"] == 6
    assert recs["sujidade"]["acao"] == "Limpeza de módulos" and recs["sujidade"]["vence"] == "2026-10-27"
    assert not recs["sujidade"]["vencida"]
    # a supressão feita DEPOIS da leitura resolve; a limpeza feita ANTES não conta, a aberta segura
    zel = Z.zeladoria_por_usina([_tarefa(1, 11, SUPRESSAO, "em_verificacao", "finalizada", "2026-10-21", "2026-10-22"),
                                 _tarefa(1, 10, LIMPEZA, "finalizada", "finalizada", "2026-10-01", "2026-10-05")],
                                HOJE)[1]
    recs = {r["campo"]: r for r in Z.recomendacoes(lei, zel, HOJE)}
    assert recs["vegetacao"]["status"] == "feita" and recs["vegetacao"]["z"]["os"] == 11
    assert not recs["vegetacao"]["vencida"]
    assert recs["sujidade"]["status"] == "sem_os"
    zel += Z.zeladoria_por_usina([_tarefa(1, 13, LIMPEZA, "em_processo", "nao_iniciada", "2026-10-28")], HOJE)[1]
    assert {r["campo"]: r for r in Z.recomendacoes(lei, zel, HOJE)}["sujidade"]["status"] == "aberta"
    # nível 3 não pede ação; sem as OS do Fracttal no banco, não dá para dizer que falta OS
    assert Z.recomendacoes({**lei, "vegetacao": 3, "sujidade": 3}, [], HOJE) == []
    assert {r["status"] for r in Z.recomendacoes(lei, [], HOJE, tem_os=False)} == {"sem_dado"}


# ── a conta da tela ─────────────────────────────────────────────────────────────────────────────────────────────────
def _montar(semana=None, tarefas=None):
    cobertura = [_usina(1, "Altair", "Thopen"), _usina(2, "Brodowski 1", "Thopen"), _usina(3, "Coração 1", "Athon")]
    todas = [_ronda(1, "2026-10-14", os_="500"), _ronda(1, "2026-10-16", os_="501"), _ronda(1, "2026-10-21", os_="502"),
             _ronda(2, "2026-10-26", os_="503"), _ronda(3, "2026-09-10", os_="504")]
    resp = {"500": _resp(2, 5), "501": _resp(3, 4), "502": _resp(4, 2, "Obstruída"), "503": _resp(1, 1),
            "504": _resp(5, 5)}
    return Z.montar(todas, cobertura, resp, [], tarefas if tarefas is not None else [], HOJE, semana)


def test_montar_evolucao_ultima_leitura_e_recomendacoes():
    z = _montar()
    assert z["semana"] == "2026-W44" and z["janela"][-1] == "2026-W44" and len(z["semanas"]) == 8
    assert z["semanas"][-1]["corrente"] and z["semanas"][-1]["escolhida"] and z["ate"] == "2026-10-26"
    u = {x["usina"]: x for x in z["usinas"]}
    alt = u["Altair"]
    # W42 com duas leituras: vale a última (16/10: vegetação 4, sujidade 3)
    assert alt["celulas"]["2026-W42"]["vegetacao"] == 4 and alt["celulas"]["2026-W42"]["sujidade"] == 3
    assert len(alt["celulas"]["2026-W42"]["leituras"]) == 2
    assert alt["celulas"]["2026-W43"]["sujidade"] == 4 and alt["celulas"]["2026-W44"]["vegetacao"] is None
    assert alt["leitura"]["data"] == "2026-10-21" and alt["anterior"]["data"] == "2026-10-16"
    assert not alt["na_semana"] and alt["dias"] == 5 and not alt["velha"]
    assert [r["acao"] for r in alt["recs"]] == ["Limpeza de módulos"]
    assert alt["pontos"] == 3 + 4                       # sujidade 4 (3) + vala obstruída (4), a régua das Rondas
    assert u["Brodowski 1"]["na_semana"] and u["Brodowski 1"]["recs"] == []
    cor = u["Coração 1"]
    assert cor["velha"] and cor["dias"] == 46 and {r["campo"] for r in cor["recs"]} == {"vegetacao", "sujidade"}
    # a semana passada: a última leitura até o domingo dela, e a W44 sai da janela
    z = _montar("2026-W42")
    alt = {x["usina"]: x for x in z["usinas"]}["Altair"]
    assert z["ate"] == "2026-10-18" and z["janela"][-1] == "2026-W42"
    assert alt["leitura"]["data"] == "2026-10-16" and alt["na_semana"]
    assert {x["usina"]: x for x in z["usinas"]}["Brodowski 1"]["leitura"] is None


def test_sem_as_os_do_fracttal_a_recomendacao_fica_sem_dado():
    assert not _montar()["tem_os"]
    assert {r["status"] for u in _montar()["usinas"] for r in u["recs"]} == {"sem_dado"}
    z = _montar(tarefas=[_tarefa(3, 20, SUPRESSAO, "em_processo", "nao_iniciada", "2026-10-30")])
    recs = {r["campo"]: r["status"] for r in {u["usina"]: u for u in z["usinas"]}["Coração 1"]["recs"]}
    assert z["tem_os"] and recs == {"vegetacao": "aberta", "sujidade": "sem_os"}


def test_evolucao_por_cliente_situacao_resumo_e_fila():
    z = _montar(tarefas=[_tarefa(3, 20, SUPRESSAO, "em_processo", "nao_iniciada", "2026-10-30")])
    us = z["usinas"]
    g = Z.por_cliente(us, z["semana"], z["janela"], "vegetacao")
    assert [x["cliente"] for x in g] == ["Athon", "Thopen"]                       # os clientes em ordem alfabética
    thopen = g[1]
    # o nível mais alto na última leitura primeiro: a Altair (vegetação 2 em 21/10) antes da Brodowski (1 em 26/10),
    # mesmo a Brodowski tendo leitura na semana corrente e a Altair não; na sujidade, a Altair (4) também
    assert [u["usina"] for u in thopen["usinas"]] == ["Altair", "Brodowski 1"]
    assert [u["usina"] for u in Z.por_cliente(us, z["semana"], z["janela"], "sujidade")[1]["usinas"]] == [
        "Altair", "Brodowski 1"]
    assert thopen["semanas"]["2026-W42"] == {"acima": 1, "lidas": 1}
    assert thopen["semanas"]["2026-W44"] == {"acima": 0, "lidas": 1}
    pelo = lambda qual: sorted(u["usina"] for u in us if Z.situacao(u, qual))    # noqa: E731
    assert pelo("atencao") == ["Altair", "Coração 1"] and pelo("vegetacao") == ["Coração 1"]
    assert pelo("sujidade") == ["Altair", "Coração 1"] and pelo("sem_os") == ["Altair", "Coração 1"]
    assert pelo("sem_leitura") == ["Altair", "Coração 1"] and pelo("sem_alerta") == ["Brodowski 1"]
    assert pelo("") == ["Altair", "Brodowski 1", "Coração 1"]
    r = Z.resumo(us)
    assert (r["usinas"], r["na_semana"], r["com_leitura"]) == (3, 1, 3)
    assert (r["vegetacao_acima"], r["sujidade_acima"], r["vegetacao_5"], r["sujidade_5"]) == (1, 2, 1, 1)
    assert (r["recs"], r["sem_os"], r["abertas"], r["feitas"]) == (3, 2, 1, 0)
    assert r["vegetacao_media"] == round((2 + 1 + 5) / 3, 1)
    fila = Z.fila(us)
    # o nível 5 primeiro; no mesmo nível, sem OS antes de aberta
    assert [(f["u"]["usina"], f["campo"], f["status"]) for f in fila] == [
        ("Coração 1", "sujidade", "sem_os"), ("Coração 1", "vegetacao", "aberta"), ("Altair", "sujidade", "sem_os")]


# ── a tela, com o banco falso ───────────────────────────────────────────────────────────────────────────────────────
def _sem_fracttal(monkeypatch):
    monkeypatch.setattr(ronda_checklist, "respostas", lambda: {"500": ronda_checklist.ler_nota(NOTA)})
    monkeypatch.setattr(ronda_checklist, "pedir_releitura", lambda app=None: None)
    monkeypatch.setattr(ronda_checklist, "estado", lambda: {"lendo": False, "erro": "", "lidas": True, "fila": True})
    monkeypatch.setattr(aprovacao, "_pedir_releitura", lambda: None)


def test_tela_da_zeladoria(banco, logado, monkeypatch):  # noqa: F811
    _sem_fracttal(monkeypatch)
    html = logado.get("/t/campo/zeladoria").get_data(as_text=True)
    assert "Vegetação e sujidade dos módulos" in html and "Evolução por cliente" in html
    assert "Recomendações" in html and "Situação por usina" in html and "Como classificamos" in html
    # os grupos da evolução são os clientes do cadastro; a Altair (sujidade 4 na OS 500) pede limpeza de módulos
    assert '<button type="button" class="zl-cli-bt" aria-expanded="true">Thopen' in html
    assert "Outro Cliente" in html and "Limpeza de módulos" in html
    # o banco falso não tem as OS do Fracttal: a tela diz, e a recomendação não acusa falta de OS
    assert "As OS do Fracttal ainda não chegaram ao banco" in html and "sem a situação da OS" in html
    assert "sem OS de zeladoria no Fracttal" not in html
    # os serviços de terceiros do App continuam no fim
    assert "Serviços de terceiros registrados pelo App" in html and "Nenhum registro de zeladoria pelo App ainda" in html
    assert logado.get("/t/campo/zeladoria?modulo=sujidade&semana=lixo&situacao=lixo").status_code == 200
    html = logado.get("/t/campo/zeladoria?situacao=sem_alerta").get_data(as_text=True)
    assert 'class="zl-linha" data-usina="1"' not in html


def test_tela_com_as_os_de_zeladoria_e_a_gaveta(banco, logado, monkeypatch):  # noqa: F811
    _sem_fracttal(monkeypatch)
    hoje = visao._agora().date()
    prog = (hoje + timedelta(days=2)).strftime("%Y%m%d")
    linhas = [{"fracttal_tarefa_id": 1, "os": 900, "fracttal_os_id": 9900, "tarefa_chave": LIMPEZA, "usina_id": 1,
               "tipo_tarefa": "zeladoria", "status_os": "em_processo", "estado_tarefa": "nao_iniciada",
               "data_id_programada": prog, "data_id_fim": None}]
    banco.workbooks["nexus_os"] = {}
    banco._id("nexus_os", "fato_tarefa_os")["linhas"] = [{"headers": list(linhas[0]), "values": list(linhas[0].values())}]
    visao.limpar()
    html = logado.get("/t/campo/zeladoria").get_data(as_text=True)
    assert "OS 900 · programada para" in html and "As OS do Fracttal ainda não chegaram ao banco" not in html
    g = logado.get(f"/t/campo/zeladoria/usina/1?semana={Z.semana_de(hoje)}").get_data(as_text=True)
    assert "Altair" in g and "Evolução nas últimas 8 semanas" in g and "Zeladoria no Fracttal" in g
    assert "Limpeza de módulos" in g and "OS 900" in g and "Histórico de rondas da usina" in g
    # as fotos só no clique: o botão aponta para as fotos da OS de ronda, a gaveta não vai ao Fracttal
    assert "/t/campo/rondas/os/500/fotos" in g and 'class="zl-bt-fotos"' in g
    assert logado.get("/t/campo/zeladoria/usina/4040").status_code == 404

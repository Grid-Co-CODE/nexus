"""Comando → Insights, Caixa de entrada e o sino (03/11/2026; Levi: "construa o que você sugere", os setores conversando,
a partir da tela de Insights do mockup R18). PRD em .taskmaster/docs/prd.txt.

O que estes testes seguram: cada regra aponta o caso certo e deixa de fora o vizinho (com dado inventado); o motor segue
quando uma fonte falha; o Assumir e o Concluir gravam cifrados e não repetem; a Caixa de entrada mostra só as torres do
setor da pessoa; o sino conta os sem dono pela cópia e nunca calcula na página. Nada vai à rede."""
from datetime import date, datetime, timedelta, timezone

import pytest
from test_campo_visao import banco  # noqa: F401  (fixture: o banco falso)

from nexus.campo import leitura as LE
from nexus.comando import estado as ES
from nexus.comando import motor as MO
from nexus.comando import regras as R
from nexus.dados import catalogo, explica

BRT = timezone(timedelta(hours=-3))
HOJE = date(2026, 11, 3)
PESSOA = {"email": "fulana@exemplo.test", "nome": "Fulana de Teste", "perfil": ""}


def nomes(uid):
    return {1: "Usina Exemplo Um", 2: "Usina Exemplo Dois"}.get(int(uid or 0), "")


# ── as regras (puras) ────────────────────────────────────────────────────────────────────────────────────────────────
def test_r03_tres_religamentos_na_mesma_cabine():
    eqs = [{"cliente": "CLIENTE A", "usina": "Usina Exemplo Um", "rotulo": "Cabine 1", "tag": "EX-UM-CAB1", "total": 3,
            "os": ["17001", "17002", "17003"], "ultima": datetime(2026, 11, 1, 8, tzinfo=BRT)},
           {"cliente": "CLIENTE A", "usina": "Usina Exemplo Um", "rotulo": "Cabine 2", "tag": "EX-UM-CAB2", "total": 2,
            "os": [], "ultima": None}]
    out = R.r03_religamentos(eqs)
    assert [i["id"] for i in out] == ["R03:Usina_Exemplo_Um:EX-UM-CAB1"]          # o id sem espaço
    assert ES.INSIGHT_RE.fullmatch(out[0]["id"])                                   # o Assumir aceita
    assert out[0]["sev"] == "critico" and out[0]["torre"] == "cos" and "3 religamentos" in out[0]["titulo"]
    assert out[0]["link"].startswith("/t/cos/religamentos?cliente=CLIENTE A")


def test_r05_comunicacao_aberta_ha_mais_de_24h():
    abertas = [{"registro": "rg1", "os": "17010", "usina_id": 1, "tipo_falha": "FALHA_COMUNICACAO", "dias_aberta_qtd": 4},
               {"registro": "rg2", "os": "17011", "usina_id": 2, "tipo_falha": "FALHA_COMUNICACAO", "dias_aberta_qtd": 0},
               {"registro": "rg3", "os": "17012", "usina_id": 2, "tipo_falha": "DESLIGAMENTO", "dias_aberta_qtd": 9},
               {"registro": "rg4", "os": "", "usina_id": 2, "tipo_falha": "FALHA_COMUNICACAO", "dias_aberta_qtd": 1}]
    out = {i["id"]: i for i in R.r05_sem_comunicacao(abertas, nomes)}
    assert set(out) == {"R05:rg1", "R05:rg4"}
    assert out["R05:rg1"]["sev"] == "critico" and out["R05:rg4"]["sev"] == "atencao"
    assert "ainda sem OS" in out["R05:rg4"]["evid"]


def test_r06_corretiva_em_ativo_com_chamado():
    tarefas = [{"os": "17100", "tipo_tarefa": "corretiva", "status_os": "em_processo", "equipamento_id": 900,
                "usina_id": 1, "data_id_criacao": 20261101, "codigo_ativo": "EX-UM-INV1"},
               {"os": "17100", "tipo_tarefa": "corretiva", "status_os": "em_processo", "equipamento_id": 900,
                "usina_id": 1, "data_id_criacao": 20261101},                       # a 2ª tarefa da mesma OS: uma vez
               {"os": "17101", "tipo_tarefa": "preventiva", "status_os": "em_processo", "equipamento_id": 900},
               {"os": "17102", "tipo_tarefa": "corretiva", "status_os": "em_processo", "equipamento_id": 901,
                "data_id_criacao": 20261101},                                      # chamado concluído há 120 dias
               {"os": "17103", "tipo_tarefa": "corretiva", "status_os": "em_processo", "equipamento_id": 902,
                "data_id_criacao": 20261001}]                                      # OS antes do chamado: não é nova
    chamados = [{"os": "16000", "equipamento_id": 900, "situacao": "aberto", "data_id_abertura": 20261015,
                 "fabricante": "Fabricante Exemplo"},
                {"os": "16001", "equipamento_id": 901, "situacao": "concluido", "data_id_fim": 20260705},
                {"os": "16002", "equipamento_id": 902, "situacao": "aberto", "data_id_abertura": 20261020}]
    out = R.r06_falha_com_chamado(tarefas, chamados, nomes, HOJE)
    assert [i["id"] for i in out] == ["R06:17100"]
    assert "chamado na OS 16000 com Fabricante Exemplo" in out[0]["evid"] and out[0]["torre"] == "chamados"


def test_r07_r09_r11_r13_e_n01():
    assert [i["id"] for i in R.r07_extintores([{"usina": "Usina Exemplo Um", "usina_id": 1, "atrasado": 2, "qtd": 8},
                                               {"usina": "Usina Exemplo Dois", "usina_id": 2, "atrasado": 0}])] == ["R07:1"]
    cap = R.r09_capacidade({"Equipe A": {"hh_util": 80, "hh_disp": 44, "pend": 3},
                            "Equipe B": {"hh_util": 40, "hh_disp": 44}, "Equipe C": {"hh_util": 50, "hh_disp": 44}}, "W45")
    assert {i["id"]: i["sev"] for i in cap} == {"R09:W45:Equipe_A": "critico", "R09:W45:Equipe_C": "atencao"}
    sem = R.r11_sem_ronda([{"usina_id": 1, "usina": "Usina Exemplo Um", "dias": 999},
                           {"usina_id": 2, "usina": "Usina Exemplo Dois", "dias": 8}, {"usina_id": 3, "dias": 3}])
    assert {i["id"]: i["sev"] for i in sem} == {"R11:1": "critico", "R11:2": "atencao"}
    assert "nenhuma ronda registrada" in sem[0]["titulo"]
    par = R.r13_chamado_parado({1: {"lista": [
        {"os": 16000, "situacao": "aberto", "status": R.FABRICANTE, "dias": 40, "fabricante": "Fabricante Exemplo"},
        {"os": 16001, "situacao": "aberto", "status": R.FABRICANTE, "dias": 2},
        {"os": 16002, "situacao": "aberto", "status": "Testes em campo", "dias": 40},
        {"os": 16003, "situacao": "verificacao", "status": R.FABRICANTE, "dias": 40}]}}, nomes)
    assert [(i["id"], i["sev"]) for i in par] == [("R13:16000", "critico")]
    volta = datetime(2026, 10, 19, 5, 53, tzinfo=BRT)
    n = R.n01_normalizadas([
        {"os": "16702", "usina": "Usina Exemplo Um", "normalizada": True, "aberta": True, "aberta_ha_dias": 15,
         "status": "Em processo", "volta": volta, "conferencia": None},
        {"os": "16703", "usina": "Usina Exemplo Um", "normalizada": True, "aberta": False, "aberta_ha_dias": None,
         "volta": volta, "conferencia": {"situacao": "HORA_A_CORRIGIR", "dif_fim": 122}},
        {"os": "16704", "usina": "Usina Exemplo Um", "normalizada": True, "aberta": True, "aberta_ha_dias": 3,
         "volta": volta, "conferencia": None},
        {"os": "16705", "usina": "Usina Exemplo Um", "normalizada": False, "aberta": True, "aberta_ha_dias": 30}])
    assert {i["id"]: i["sev"] for i in n} == {"N01:16702": "critico", "N01:16703": "atencao"}
    assert "hora a corrigir no Fracttal (conclusão +122 min)" in n[1]["evid"]


def test_a_ordem_e_o_catalogo():
    xs = [R._insight("R11", "a", "atencao", "B", [], "", desde=date(2026, 10, 1)),
          R._insight("R07", "b", "critico", "C", [], ""), R._insight("R13", "c", "atencao", "A", [], "", desde=date(2026, 9, 1))]
    assert [x["id"] for x in R.ordenar(xs)] == ["R07:b", "R13:c", "R11:a"]       # crítico, depois o que espera mais
    assert set(R.REGRAS) == set(MO.FONTES)


# ── o motor ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_motor_segue_quando_uma_fonte_falha(app, monkeypatch):
    def quebra(*a):
        raise RuntimeError("a fonte do Andamento não está ligada neste servidor")
    fontes = {k: (lambda *a: []) for k in MO.FONTES}
    fontes["R03"] = quebra
    fontes["R07"] = lambda *a: [R._insight("R07", "1", "critico", "Usina Exemplo Um: 2 extintores vencidos", [], "x")]
    monkeypatch.setattr(MO, "FONTES", fontes)
    monkeypatch.setattr(MO, "_nomes", lambda: nomes)
    with app.app_context():
        d = MO.calcular()
    assert [i["id"] for i in d["insights"]] == ["R07:1"]
    assert "não está ligada" in d["regras"]["R03"]["erro"] and d["regras"]["R07"] == {"n": 1, "erro": ""}


# ── o estado (Assumir e Concluir) ────────────────────────────────────────────────────────────────────────────────────
INSIGHT = {"id": "N01:16702", "regra": "N01", "torre": "cos"}


@pytest.fixture
def limpo():
    ES.limpar()
    yield
    ES.limpar()


def test_assumir_e_concluir_gravam_cifrados_e_nao_repetem(app, banco, limpo):
    ES.registrar(INSIGHT, "assumiu", PESSOA)
    ES.registrar(INSIGHT, "assumiu", PESSOA)                      # o duplo clique: não grava outra
    ES.registrar(INSIGHT, "concluiu", PESSOA, "Finalizada no Fracttal")
    linhas = banco.linhas(ES.LIVRO, ES.ABA)
    assert [(l["insight_id"], l["evento"], l["torre"]) for l in linhas] == [("N01:16702", "assumiu", "cos"),
                                                                           ("N01:16702", "concluiu", "cos")]
    assert "Fulana" not in str(linhas) and "Finalizada" not in str(linhas)       # nome e nota só cifrados
    est = ES.atual()["N01:16702"]
    assert (est["evento"], est["por"], est["nota"]) == ("concluiu", "Fulana de Teste", "Finalizada no Fracttal")
    with pytest.raises(ES.Recusada):
        ES.registrar(INSIGHT, "assumiu", {"email": "", "nome": ""})              # a senha de administrador não grava
    with pytest.raises(ES.Recusada):
        ES.registrar({"id": "lixo", "regra": "N01"}, "assumiu", PESSOA)


def test_o_livro_esta_no_catalogo_antes_da_1a_gravacao():
    l = catalogo.LIVRO_POR_NOME[ES.LIVRO]
    assert l.abas == (ES.ABA,) and l.so_cresce == (ES.ABA,) and not l.no_banco
    f = catalogo.POR_ID["evento_insight"]
    assert f.livro == f"{ES.LIVRO} · {ES.ABA}" and f.chave[0] == ES.CAB[0] and "pessoa_hmac" in ES.CAB
    assert "evento_insight" in explica.RESUMO and "evento_insight" in explica.PARA_QUE


# ── as telas e o sino ────────────────────────────────────────────────────────────────────────────────────────────────
DOIS = [R._insight("N01", "16702", "critico", "Usina Exemplo Um: a OS 16702 voltou e segue aberta no Fracttal",
                   ["em processo no Fracttal 15 dias depois da volta"], "Finalizar a OS.", "Usina Exemplo Um",
                   "/t/cos/normalizacoes?q=16702"),
        R._insight("R07", "1", "critico", "Usina Exemplo Um: 2 extintores vencidos", [], "Programar a recarga.",
                   "Usina Exemplo Um", "/t/hseq/extintores")]


@pytest.fixture
def motor_dublado(app, monkeypatch):
    lei = LE.Leitura({"insights": R.ordenar(DOIS), "regras": {k: {"n": 0, "erro": ""} for k in R.REGRAS},
                      "gerado_em": datetime(2026, 11, 3, 9, 30, tzinfo=BRT)}, 0)
    monkeypatch.setattr(MO, "ler", lambda: lei)
    monkeypatch.setattr(MO, "do_cache", lambda: lei)
    return lei


def _cliente(app, admin=False):
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(logado=True, admin=admin, usuario=dict(PESSOA))
    return c


def _codigo(c, url="/t/comando/insights") -> str:
    return c.get(url).get_data(as_text=True).split('name="codigo" value="', 1)[1].split('"', 1)[0]


def test_a_tela_de_insights_e_o_assumir(app, banco, limpo, motor_dublado):
    c = _cliente(app)
    html = c.get("/t/comando/insights").get_data(as_text=True)
    assert "a OS 16702 voltou e segue aberta" in html and "2 extintores vencidos" in html
    # a gravidade é um selo (ponto + palavra), sem a faixa vermelha (Levi, 03/11/2026: "não sou muito fã dessa barra
    # lateral em vermelho")
    assert 'class="ins-sev ins-sev--critico">Crítico<' in html and "border-left" not in html
    assert "Ninguém avisado" in html and "Abrir a tela" in html
    assert "As regras" in html and "R13" in html
    r = c.post("/t/comando/insights/acao", data={"codigo": _codigo(c), "insight": "N01:16702", "acao": "assumir",
                                                 "voltar": "/t/comando/insights"})
    assert r.status_code == 303 and r.headers["Location"].endswith("/t/comando/insights#ins-N01-16702")
    assert [l["evento"] for l in banco.linhas(ES.LIVRO, ES.ABA)] == ["assumiu"]
    html = c.get("/t/comando/insights").get_data(as_text=True)
    assert "Assumido: agora é seu." in html and "Com você" in html
    # outro site e o insight que a regra não aponta mais não gravam
    c.post("/t/comando/insights/acao", data={"codigo": _codigo(c), "insight": "N01:16702", "acao": "concluir"},
           headers={"Sec-Fetch-Site": "cross-site"})
    c.post("/t/comando/insights/acao", data={"codigo": _codigo(c), "insight": "N01:99999", "acao": "assumir"})
    assert len(banco.linhas(ES.LIVRO, ES.ABA)) == 1


def test_a_caixa_so_mostra_as_torres_do_setor(app, banco, limpo, motor_dublado, monkeypatch):
    monkeypatch.setattr(MO, "torres_da_pessoa", lambda: {"hseq"})
    html = _cliente(app).get("/t/comando/caixa-de-entrada").get_data(as_text=True)
    assert "2 extintores vencidos" in html and "16702" not in html
    monkeypatch.setattr(MO, "torres_da_pessoa", lambda: None)
    html = _cliente(app).get("/t/comando/caixa-de-entrada").get_data(as_text=True)
    assert "2 extintores vencidos" in html and "16702" in html and "todas as torres" in html


def test_o_sino_conta_os_sem_dono_das_torres_da_pessoa(app, banco, limpo, motor_dublado, monkeypatch):
    monkeypatch.setattr(MO, "torres_da_pessoa", lambda: {"cos"})
    html = _cliente(app).get("/t/comando/insights").get_data(as_text=True)
    sino = html.split('class="sino-topo"', 1)[1].split("</details>", 1)[0]
    assert '<b class="sino-n sino-n--critico">1</b>' in sino and "a OS 16702 voltou" in sino and "extintores" not in sino
    ES.registrar(DOIS[0], "assumiu", PESSOA)                      # com dono: sai do sino
    ES.ler(forcar=True)
    html = _cliente(app).get("/t/comando/insights").get_data(as_text=True)
    sino = html.split('class="sino-topo"', 1)[1].split("</details>", 1)[0]
    assert "sino-n" not in sino and "Nada sem dono" in sino


def test_sem_a_copia_do_motor_o_topo_abre_sem_o_sino(app, logado, monkeypatch):
    monkeypatch.setattr(MO, "do_cache", lambda: None)
    r = logado.get("/")
    assert r.status_code == 200 and 'class="sino-topo"' not in r.get_data(as_text=True)



# ── notificar as áreas e o retorno de cada uma (Levi, 03/11/2026) ────────────────────────────────────────────────────
def test_notificar_e_responder_no_estado(app, banco, limpo):
    """"o manager quer algo como notificar as áreas e saber como está e receber retornos dessas áreas"."""
    R07 = {"id": "R07:1", "regra": "R07", "torre": "hseq"}
    ES.registrar(R07, "notificou", PESSOA, "Trocar até sexta", ["hseq", "campo"])
    ES.registrar(R07, "notificou", PESSOA, "", ["hseq"])               # já avisada e sem resposta: não grava outra
    ES.registrar(R07, "respondeu", {"email": "seg@exemplo.test", "nome": "Ciclana da Segurança"}, "Recarga marcada",
                 ["hseq"], "andamento")
    ES.registrar(R07, "respondeu", {"email": "seg@exemplo.test", "nome": "Ciclana da Segurança"}, "Recarga marcada",
                 ["hseq"], "andamento")                                 # o mesmo retorno de novo: não grava
    linhas = banco.linhas(ES.LIVRO, ES.ABA)
    assert [(l["evento"], l["para"], l["status_retorno"]) for l in linhas] == [
        ("notificou", "hseq,campo", None), ("respondeu", "hseq", "andamento")]
    assert "Recarga" not in str(linhas) and "Ciclana" not in str(linhas)   # o retorno e o nome só cifrados
    ped = ES.atual()["R07:1"]["pedidos"]
    assert (ped["hseq"]["status"], ped["hseq"]["retorno"], ped["hseq"]["retorno_por"]) == (
        "andamento", "Recarga marcada", "Ciclana da Segurança")
    assert (ped["campo"]["status"], ped["campo"]["mensagem"]) == ("pendente", "Trocar até sexta")
    with pytest.raises(ES.Recusada):
        ES.registrar(R07, "respondeu", PESSOA, "", ["pcm"], "resolvido")    # área que não foi notificada
    with pytest.raises(ES.Recusada):
        ES.registrar(R07, "notificou", PESSOA, "", [])


def test_a_tela_notifica_a_area_de_costume_e_a_area_responde(app, banco, limpo, motor_dublado, monkeypatch):
    c = _cliente(app)
    html = c.get("/t/comando/insights").get_data(as_text=True)
    # a ação de costume da regra: o extintor avisa a Segurança e o Campo; a normalização, o Campo
    assert "Notificar Segurança · HSEQ e Campo · App" in html and "Notificar outras áreas" in html
    c.post("/t/comando/insights/acao", data={"codigo": _codigo(c), "insight": "R07:1", "acao": "notificar",
                                             "para": ["hseq", "campo"], "voltar": "/t/comando/insights"})
    assert [l["para"] for l in banco.linhas(ES.LIVRO, ES.ABA)] == ["hseq,campo"]
    ES.ler(forcar=True)
    html = c.get("/t/comando/insights").get_data(as_text=True)
    assert "Notificado: Segurança · HSEQ, Campo · App." in html and "Aguardando retorno" in html
    # a pessoa do setor da Segurança vê o pedido na Caixa, responde, e quem notificou vê o retorno
    monkeypatch.setattr(MO, "torres_da_pessoa", lambda: {"hseq"})
    seg = app.test_client()
    with seg.session_transaction() as s:
        s.update(logado=True, admin=False, usuario={"email": "seg@exemplo.test", "nome": "Ciclana da Segurança"})
    caixa = seg.get("/t/comando/caixa-de-entrada").get_data(as_text=True)
    assert "Pedidos para o seu setor" in caixa and "Responder por Segurança · HSEQ" in caixa
    assert "Responder por Campo · App" not in caixa                          # só responde pela própria área
    sino = caixa.split('class="sino-topo"', 1)[1].split("</details>", 1)[0]
    assert "extintores vencidos" in sino                                   # o pedido pendente acende o sino dela
    seg.post("/t/comando/insights/acao", data={"codigo": _codigo(seg, "/t/comando/caixa-de-entrada"),
                                               "insight": "R07:1", "acao": "responder", "area": "hseq",
                                               "status": "resolvido", "nota": "Extintores trocados",
                                               "voltar": "/t/comando/caixa-de-entrada"})
    seg.post("/t/comando/insights/acao", data={"codigo": _codigo(seg, "/t/comando/caixa-de-entrada"),
                                               "insight": "R07:1", "acao": "responder", "area": "campo",
                                               "status": "resolvido", "voltar": "/t/comando/caixa-de-entrada"})
    assert [l["status_retorno"] for l in banco.linhas(ES.LIVRO, ES.ABA)] == [None, "resolvido"]
    ES.ler(forcar=True)
    monkeypatch.setattr(MO, "torres_da_pessoa", lambda: None)
    html = c.get("/t/comando/insights").get_data(as_text=True)
    assert "Extintores trocados" in html and "Ciclana da Segurança" in html

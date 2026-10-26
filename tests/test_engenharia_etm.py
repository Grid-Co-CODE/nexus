"""A tela ETMs da Engenharia (Levi, 26/10/2026: "Quero que inclua essa visão de ETMs no Nexus, engenharia, aba
própria. Deixe o design alá Nexus!"): a leitura das OS das Estações Meteorológicas, o livro das marcações, a tela e a OS
da ETM. Desenho em docs/superpowers/specs/2026-10-26-engenharia-etm-design.md. Fracttal e banco falsos; nomes de mentira
(repositório público)."""
import time
from datetime import date

import pytest

from nexus.engenharia import etm as E

HOJE = date(2026, 10, 26)
U = "Cliente X - Usina Alfa - MG"
EQUIPE = ["Ana Lima", "Beto Souza"]
ETMS = {"ALF100-ESTM1", "GAM300-ESTM1"}


def w(folio, tipo, resp="Técnico Um", solic="", cod="ALF100-ESTM1", status=1, task="NO_STARTED", criado_por="", pid=7,
      titulo="Estação sem comunicação"):
    return {"wo_folio": str(folio), "id_work_order": 50000 + folio, "id_personnel": pid, "personnel_description": resp,
            "requested_by": solic, "created_by": criado_por, "id_status_work_order": status, "task_status": task,
            "tasks_log_task_type_main": tipo, "description": titulo, "code": cod,
            "items_log_description": f"Estação Meteorológica Alfa {{{cod}}}", "groups_1_description": U,
            "creation_date": "2026-10-20T12:00:00+00:00", "labels": []}


# ── a leitura das OS de ETM (Task 1) ─────────────────────────────────────────────────────────────────────────────────
def test_entram_as_corretivas_e_as_administrativas_de_etm():
    oss = E.montar([w(1, "Corretiva"), w(2, "Administrativa"), w(3, "Preventiva")], ETMS, EQUIPE, HOJE)
    assert sorted(o["os"] for o in oss) == ["1", "2"]


def test_as_outras_so_com_a_equipe_e_analise_ou_campo():
    # a regra do app sem nome no código: a equipe é a lista da Engenharia (a do Quadro da equipe, fora do git)
    oss = {o["os"]: o for o in E.montar([
        w(1, "Preventiva", resp="Ana  Lima"),                       # o nome do Fracttal com dois espaços
        w(2, "Inspeção", resp="Técnico Um", solic="beto souza"),    # solicitante da equipe, sem caixa
        w(3, "Corretiva", resp="Ana Lima"),                         # a corretiva vai a campo, mesmo com a equipe
        w(4, "Administrativa", resp="Técnico Um"),
        w(5, "Preventiva", resp="Ana Lima Souza"),                  # o nome do Fracttal mais comprido que o da lista
    ], ETMS, EQUIPE, HOJE)}
    assert {k: o["trabalho"] for k, o in oss.items()} == {"1": "analise", "2": "campo", "3": "campo", "4": "campo",
                                                         "5": "analise"}


def test_codigo_que_nao_e_de_etm_nao_entra_e_e_uma_os_por_numero():
    linhas = [w(1, "Corretiva"), dict(w(1, "Corretiva"), description="Segunda tarefa"),
              w(5, "Corretiva", cod="ALF100-INV1")]
    oss = E.montar(linhas, ETMS, EQUIPE, HOJE)
    assert [o["os"] for o in oss] == ["1"] and len(oss[0]["tarefas"]) == 2


def test_a_coluna_do_planner():
    col = {o["os"]: o["coluna_etm"] for o in E.montar([
        w(1, "Corretiva"), w(2, "Corretiva", task="IN_PROGRESS"), w(3, "Corretiva", status=2, task="DONE"),
        w(4, "Corretiva", status=3, task="DONE"), w(5, "Corretiva", status=4)], ETMS, EQUIPE, HOJE)}
    assert col == {"1": "nao_iniciada", "2": "em_andamento", "3": "em_andamento", "4": "finalizada", "5": "cancelada"}


def test_o_cartao_traz_cliente_solicitante_e_quem_criou():
    o = E.montar([w(1, "Corretiva", solic="Pessoa Dois", criado_por="Pessoa Três")], ETMS, EQUIPE, HOJE)[0]
    assert (o["cliente"], o["usina"], o["codigo"]) == ("Cliente X", U, "ALF100-ESTM1")
    assert (o["solicitante"], o["criado_por"], o["responsavel"]) == ("Pessoa Dois", "Pessoa Três", "Técnico Um")
    assert E.cliente_de("") == "Não identificado" and E.cliente_de("Só um nome") == "Só um nome"


@pytest.fixture
def fracttal(monkeypatch, app):
    pedidos = []

    def ler(path):
        pedidos.append(path)
        if path.startswith("items?field_1="):
            return {"data": [{"code": "ALF100-ESTM1", "description": "Estação Meteorológica  Alfa  Minas Gerais"},
                             {"code": "X-1", "description": "Inversor 1"}]}
        if path.startswith("work_orders?items_log_description="):
            return {"data": [w(1, "Corretiva"), w(3, "Preventiva")]}
        raise AssertionError(f"a tela não lê {path}")
    monkeypatch.setattr(E, "_ler_fracttal", ler)
    app.config["NEXUS_ENGENHARIA_RESPONSAVEIS"] = "Ana Lima"
    E.limpar()
    yield pedidos
    E.limpar()


def test_le_as_etms_e_as_os_delas_em_poucos_pedidos(fracttal, app):
    # medido em 26/10/2026: as 1213 OS de ETM vêm por um filtro só, contra uma consulta por ETM no app
    E.pedir_releitura(app, esperar=True)
    d = E.dados()
    assert [o["os"] for o in d["os"]] == ["1"] and not d["erro"] and d["lido"]
    assert len(fracttal) == 2
    assert fracttal[0].startswith("items?field_1=Esta%C3%A7%C3%A3o%20Meteorol%C3%B3gica")
    assert fracttal[1].startswith("work_orders?items_log_description=Esta%C3%A7%C3%A3o%20Meteorol%C3%B3gica")
    assert E.eh_etm("ALF100-ESTM1") is True and E.eh_etm("X-1") is False      # a descrição confere a ETM


def test_sem_leitura_nao_se_sabe_se_e_etm(fracttal):
    assert E.eh_etm("ALF100-ESTM1") is None


def test_leitura_que_falha_guarda_a_anterior_e_diz(fracttal, app, monkeypatch):
    E.pedir_releitura(app, esperar=True)

    def cai(path):
        raise RuntimeError("o Fracttal recusou por excesso de pedidos (HTTP 429)")
    monkeypatch.setattr(E, "_ler_fracttal", cai)
    E._EST["ts"] = 0.0
    E.pedir_releitura(app, esperar=True, forcar=True)
    d = E.dados()
    assert [o["os"] for o in d["os"]] == ["1"] and "429" in d["erro"]


def test_leitura_que_passa_do_teto_nao_vira_quadro_pela_metade(fracttal, app, monkeypatch):
    # um filtro que o REST passasse a ignorar viraria o Fracttal inteiro: no teto, a leitura é recusada
    monkeypatch.setattr(E, "TETO_OS", 1)
    monkeypatch.setattr(E, "_ler_fracttal", lambda path: {"data": [w(n, "Corretiva") for n in range(100)]}
                        if path.startswith("work_orders") else
                        {"data": [{"code": "ALF100-ESTM1", "description": "Estação Meteorológica Alfa"}]})
    E.pedir_releitura(app, esperar=True)
    d = E.dados()
    assert d["os"] == [] and "teto" in d["erro"]


def test_releitura_por_tras_so_com_a_tela_em_uso(fracttal, app, monkeypatch):
    agora = time.time()
    assert E._tique(app, agora) is False                     # ninguém abriu a tela
    E.marcar_uso()
    assert E._tique(app, time.time()) is True and len(fracttal) == 2


# ── o livro das marcações (Task 2) ───────────────────────────────────────────────────────────────────────────────────
OSE = {"wid": 50001, "folio": "1", "codigo": "ALF100-ESTM1", "usina_id": 1, "usina_ligada_por": "de-para do Fracttal"}


@pytest.fixture
def banco(app):
    from pg_falso import ApiPGFalsa

    from nexus.cadastro.cifra import gerar_chave
    from nexus.engenharia import etm_marcas as M
    api = ApiPGFalsa()
    app.config.update(GRIDCO_DB_API="http://pg.falso", NEXUS_CHAVE_CADASTRO=gerar_chave(),
                      NEXUS_PESSOA_HMAC="hmac-teste", GRIDCO_SQL_TOKEN="tk")
    app.extensions["nexus_dados_sessao"] = api
    from nexus.engenharia import os_acompanhamento as O
    M.limpar(), O.limpar(), E.limpar()          # as cópias em memória dos dois livros e da leitura, de outro teste
    with app.app_context():
        yield api
    M.limpar(), O.limpar(), E.limpar()
    app.extensions.pop("nexus_dados_sessao", None)


def _marcas(wid=OSE["wid"]):
    from nexus.engenharia import etm_marcas as M
    return M.estado(M.ler(forcar=True)["eventos"]).get(str(wid)) or {}


def test_catalogo_registra_o_livro_das_marcacoes():
    from nexus.dados import catalogo, explica
    from nexus.engenharia import etm_marcas as M
    l = catalogo.LIVRO_POR_NOME[M.LIVRO]
    assert set(l.abas) == {M.ABA, M.ABA_DIAGNOSTICO, M.ABA_STATUS_POS, M.ABA_ETIQUETA}
    assert set(l.so_cresce) == set(l.abas) and all(catalogo.aba_segue_a_regra(x) for x in l.abas)
    f = next(x for x in catalogo.FATOS if x.id == "marcacao_etm")
    assert "1 linha = 1 marcação" in f.grao and {"data", "usina", "equipamento", "pessoa"} <= set(f.dims)
    assert 15 <= len(explica.RESUMO["marcacao_etm"]) <= 70
    assert len(explica.PARA_QUE["marcacao_etm"]) >= 80 and explica.PARA_QUE["marcacao_etm"].endswith(".")


def test_as_listas_sao_as_do_app():
    from nexus.engenharia import etm_marcas as M
    assert [n for _, n in M.DIAGNOSTICOS] == ["Falha de Equipamento", "Falha de Comunicação", "Sujidade", "Outro"]
    assert [n for _, n in M.STATUS_POS] == ["Chamado de Garantia", "Alinhamento com o Cliente", "Regularizado"]
    assert [n for _, n in M.ETIQUETAS] == ["OS em campo", "Stand By", "Validação Final"]


def test_cada_marcacao_e_um_evento_e_o_estado_le_o_ultimo(banco):
    import json

    from test_engenharia_acompanhamento import ANA, BETO

    from nexus.engenharia import etm_marcas as M
    M.marcar(OSE, "diagnostico", 2, ANA, True)
    M.marcar(OSE, "status_pos", 1, ANA, True)
    M.marcar(OSE, "etiqueta", (2, True), BETO, True)
    M.marcar(OSE, "etiqueta", (3, True), BETO, True)
    M.marcar(OSE, "etiqueta", (2, False), BETO, True)          # desliga
    M.marcar(OSE, "acompanhamento", True, ANA, True)
    M.marcar(OSE, "finalizado", True, ANA, True)
    e = _marcas()
    assert (e["diagnostico_id"], e["status_pos_id"], e["etiquetas"]) == (2, 1, {3})
    assert e["acompanhamento"] is True and e["finalizado"] is True and e["ultima"]
    assert e["eventos"][0]["evento"] == "finalizado" and e["eventos"][0]["nome"] == "Ana Lima"
    M.marcar(OSE, "diagnostico", 0, ANA, True)                 # 0 limpa
    assert _marcas()["diagnostico_id"] is None
    linhas = banco.linhas(M.LIVRO, M.ABA)
    assert len(linhas) == 8 and {x["evento"] for x in linhas} == set(M.EVENTOS)
    assert all(x["origem"] == "nexus" for x in linhas)
    cru = json.dumps(linhas, ensure_ascii=False, default=str)
    assert "Ana Lima" not in cru and "ana.lima" not in cru
    assert [x["nome"] for x in banco.linhas(M.LIVRO, M.ABA_DIAGNOSTICO)][1] == "Falha de Comunicação"


def test_marcacao_recusada(banco):
    from test_engenharia_acompanhamento import ANA, BETO

    from nexus.engenharia import etm_marcas as M
    M.marcar(OSE, "diagnostico", 1, ANA, True)
    with pytest.raises(M.Recusada, match="Nada mudou"):
        M.marcar(OSE, "diagnostico", 1, ANA, True)
    with pytest.raises(M.Recusada, match="Engenharia"):
        M.marcar(OSE, "diagnostico", 2, BETO, False)
    with pytest.raises(M.Recusada, match="lista"):
        M.marcar(OSE, "status_pos", 9, ANA, True)
    with pytest.raises(M.Recusada, match="marcação"):
        M.marcar(OSE, "prioridade", 1, ANA, True)
    with pytest.raises(M.Recusada, match="id do Fracttal"):
        M.marcar(dict(OSE, wid=None), "diagnostico", 2, ANA, True)


def test_livro_existente_sem_a_aba_e_leitura_incompleta(banco):
    # a listagem que omite a aba por um instante não vira "sem marcação" (nem se grava por cima)
    from test_engenharia_acompanhamento import ANA

    from nexus.engenharia import etm_marcas as M
    M.marcar(OSE, "diagnostico", 1, ANA, True)
    banco.omitir.add(M.LIVRO)
    M.limpar()
    lido = M.ler()
    assert lido["erro"] and lido["lido_em"] is None
    with pytest.raises(Exception, match="não vieram"):
        M.marcar(OSE, "diagnostico", 2, ANA, True)


# ── a tela ETMs, o Planner (Task 3) ──────────────────────────────────────────────────────────────────────────────────
URL_TELA = "/t/engenharia/etm"


@pytest.fixture
def tela(banco, app, monkeypatch):
    """Quatro OS de ETM: a 1 não iniciada (campo), a 2 em andamento em análise, a 3 finalizada há 5 dias e a 4 cancelada.
    Quem entra é do setor Engenharia."""
    from datetime import datetime, timedelta, timezone

    from nexus.auth import setor_telas as ST
    fim = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    linhas = [w(1, "Corretiva", solic="Pessoa Dois", criado_por="Pessoa Três"),
              w(2, "Preventiva", resp="Ana Lima", task="IN_PROGRESS", cod="GAM300-ESTM1"),
              dict(w(3, "Corretiva", status=3, task="DONE"), final_date=fim, wo_final_date=fim),
              w(4, "Administrativa", status=4)]
    oss = E.montar(linhas, ETMS, EQUIPE, date.today())
    pedidos = []
    monkeypatch.setattr(E, "dados", lambda: {"os": oss, "lido": time.time(), "lendo": False, "erro": ""})
    monkeypatch.setattr(E, "pedir_releitura", lambda app=None, esperar=False, forcar=False:
                        pedidos.append((esperar, forcar)))
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": set(), "setor": {"id": 1, "nome": "Engenharia"},
                                               "erro": ""})
    return pedidos


def _dados_da_tela(html):
    import json
    return json.loads(html.split('<script type="application/json" id="etm-dados">', 1)[1].split("</script>", 1)[0])


def test_a_tela_etms_na_torre_da_engenharia(tela, cliente):
    from test_engenharia_acompanhamento import ANA, _como

    from nexus.torres import engenharia as torre
    t = torre.TORRE.tela("etm")
    assert t.nome == "ETMs" and t.do_setor == "Engenharia"
    html = _como(cliente, ANA).get(URL_TELA).get_data(as_text=True)
    d = _dados_da_tela(html)
    assert sorted(o["os"] for o in d["oss"]) == ["1", "2", "3", "4"]
    assert [c[1] for c in d["colunas"]] == ["Não iniciadas", "Em andamento", "Finalizadas", "Canceladas"]
    o = {x["os"]: x for x in d["oss"]}
    assert (o["1"]["coluna"], o["2"]["coluna"], o["3"]["coluna"], o["4"]["coluna"]) == \
           ("nao_iniciada", "em_andamento", "finalizada", "cancelada")
    assert o["2"]["trabalho"] == "analise" and o["1"]["cliente"] == "Cliente X"
    assert o["1"]["solicitante"] == "Pessoa Dois" and o["1"]["criado_por"] == "Pessoa Três"
    assert "nexusRota('/t/engenharia/etm/os/')" in html          # o clique abre a OS da ETM


def test_os_filtros_do_planner_do_app(tela, cliente):
    from test_engenharia_acompanhamento import ANA, _como
    html = _como(cliente, ANA).get(URL_TELA).get_data(as_text=True)
    for campo in ('id="etm-f-cliente"', 'id="etm-f-usina"', 'id="etm-f-criado"', 'id="etm-f-solicitante"',
                  'id="etm-f-responsavel"', 'data-trabalho="analise"', 'data-trabalho="campo"', 'id="etm-f-ini"',
                  'id="etm-f-fim"', 'id="etm-f-canceladas"', 'id="etm-f-limpar"'):
        assert campo in html, campo
    assert ">Análise de Engenharia<" in html and ">Campo<" in html
    assert '<option value="Cliente X">Cliente X</option>' in html
    # o filtro das etiquetas da Engenharia, na coluna Em andamento como no app
    assert all(f'data-etiqueta="{n}"' in html for n in ("OS em campo", "Stand By", "Validação Final"))


def test_cada_os_leva_as_marcacoes_da_engenharia(tela, cliente):
    from test_engenharia_acompanhamento import ANA, _como

    from nexus.engenharia import etm_marcas as M
    os2 = {"wid": 50002, "folio": "2", "codigo": "GAM300-ESTM1"}
    M.marcar(os2, "diagnostico", 2, ANA, True)
    M.marcar(os2, "status_pos", 1, ANA, True)
    M.marcar(os2, "etiqueta", (3, True), ANA, True)
    M.marcar(os2, "acompanhamento", True, ANA, True)
    d = _dados_da_tela(_como(cliente, ANA).get(URL_TELA).get_data(as_text=True))
    o = {x["os"]: x for x in d["oss"]}
    assert (o["2"]["diagnostico"], o["2"]["status_pos"], o["2"]["etiquetas_eng"]) == \
           ("Falha de Comunicação", "Chamado de Garantia", ["Validação Final"])
    assert o["2"]["acompanhamento"] is True and o["2"]["finalizado"] is False
    assert o["1"]["diagnostico"] is None and o["1"]["etiquetas_eng"] == []


def test_a_faixa_de_numeros(tela, cliente):
    from test_engenharia_acompanhamento import ANA, _como

    from nexus.engenharia import etm_marcas as M
    M.marcar({"wid": 50001, "folio": "1", "codigo": "ALF100-ESTM1"}, "acompanhamento", True, ANA, True)
    html = _como(cliente, ANA).get(URL_TELA).get_data(as_text=True)
    kpis = html.split('aria-label="As ETMs agora"', 1)[1].split("</section>", 1)[0]
    import re
    pares = re.findall(r'kb-kpi-rot">([^<]+)</span>\s*<span class="kb-kpi-linha"><b class="kb-kpi-v[^"]*">([^<]+)</b>', kpis)
    assert pares == [("Abertas no Fracttal", "2"), ("Abertas para a Engenharia", "3"), ("Em acompanhamento", "1"),
                     ("Finalizadas em 30 dias", "1")]


def test_sem_o_livro_a_tela_diz_e_nao_chuta_marcacao(tela, cliente, monkeypatch):
    from test_engenharia_acompanhamento import ANA, _como

    from nexus.engenharia import etm_marcas as M
    monkeypatch.setattr(M, "ler", lambda forcar=False: {"eventos": [], "lido_em": None, "erro": "Timeout: banco"})
    html = _como(cliente, ANA).get(URL_TELA).get_data(as_text=True)
    assert "Não consegui ler as marcações da Engenharia (Timeout)" in html
    assert _dados_da_tela(html)["sem_marcas"] is True
    kpis = html.split('aria-label="As ETMs agora"', 1)[1].split("</section>", 1)[0]
    assert kpis.count('">—</b>') == 2                                # as duas contas que dependem das marcações


def test_atualizar_rele_o_fracttal_e_a_leitura_que_falhou_diz(tela, cliente, monkeypatch):
    from test_engenharia_acompanhamento import ANA, _como
    _como(cliente, ANA).get(URL_TELA + "?atualizar=1")
    assert tela[-1] == (True, True)
    monkeypatch.setattr(E, "dados", lambda: {"os": [], "lido": time.time(), "lendo": False,
                                             "erro": "o Fracttal recusou por excesso de pedidos (HTTP 429)"})
    html = _como(cliente, ANA).get(URL_TELA).get_data(as_text=True)
    assert "O Fracttal recusou a leitura agora" in html and "HTTP 429" in html


def test_a_subida_liga_a_releitura_por_tras(app, monkeypatch):
    from nexus import engenharia as eng_pkg
    from nexus.engenharia import os_equipe
    ligados = []
    monkeypatch.setattr(os_equipe, "manter_quente", lambda a: ligados.append("equipe"))
    monkeypatch.setattr(E, "manter_quente", lambda a: ligados.append("etm"))
    app.config["NEXUS_CAMPO_AQUECER"] = "0"
    eng_pkg.instalar(app)
    assert ligados == ["equipe", "etm"]


# ── a OS da ETM (Task 4): a página da OS da Engenharia com o painel das marcações ───────────────────────────────────
URL_OS = "/t/engenharia/etm/os/17003"


@pytest.fixture
def pagina_etm(banco, app, monkeypatch):
    """A OS 17003 de ETM (em verificação) com o checklist respondido; a 17009 é de um inversor. Quem entra é do setor
    Engenharia."""
    from nexus.auth import setor_telas as ST
    from nexus.engenharia import os_equipe
    from nexus.torres import engenharia as torre
    linhas = {"17003": [dict(w(17003, "Corretiva", status=2, task="DONE"), id_work_order=60003)],
              "17009": [dict(w(17009, "Corretiva", cod="ALF100-INV1"), items_log_description="Inversor 1 {ALF100-INV1}")]}
    subs = {"17003": [{"description": "Ficou alguma pendência? Se sim, descreva", "value": "Não", "order_number": 2},
                      {"description": "Descreva a atividade realizada", "value": "Piranômetro trocado",
                       "order_number": 1, "group": "ATIVIDADE"}]}

    def rest(path):
        valor = path.split("=", 1)[1].split("&", 1)[0]
        if path.startswith("work_orders?wo_folio="):
            return {"data": linhas.get(valor, [])}
        if path.startswith("work_orders?id_parent_wo="):
            return {"data": []}
        if path.startswith("work_orders_subtasks/?folio="):
            return {"data": subs.get(valor, [])}
        raise AssertionError(path)
    monkeypatch.setattr(os_equipe, "_ler_fracttal", rest)
    monkeypatch.setattr(torre, "_onde_do_cadastro",
                        lambda: (lambda texto, cod: {"usina_id": 7, "ligada_por": "de-para do Fracttal"}))
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": set(), "setor": {"id": 1, "nome": "Engenharia"},
                                               "erro": ""})


def _secao_os(html, titulo):
    return html.split(f"<h2>{titulo}</h2>", 1)[1].split("</section>", 1)[0]


def test_a_os_da_etm_tem_o_painel_das_marcacoes(pagina_etm, cliente):
    import re

    from test_engenharia_acompanhamento import ANA, _como
    html = _como(cliente, ANA).get(URL_OS).get_data(as_text=True)
    p = _secao_os(html, "Marcações da Engenharia")
    assert '<option value="0">— sem diagnóstico —</option>' in p
    assert all(f">{n}</option>" in p for n in ("Falha de Equipamento", "Falha de Comunicação", "Sujidade", "Outro"))
    assert all(f">{n}</option>" in p for n in ("Chamado de Garantia", "Alinhamento com o Cliente", "Regularizado"))
    assert all(f'aria-pressed="false">{n}</button>' in p for n in ("OS em campo", "Stand By", "Validação Final"))
    assert ">Pôr em acompanhamento</button>" in p and ">Finalizar pela Engenharia</button>" in p
    assert "<h2>Status e prioridade</h2>" not in html                    # o painel da ETM no lugar dele
    assert re.search(r'class="eg-ac-volta" href="/t/engenharia/etm">← ETMs</a>', html)
    rot = re.findall(r'<div class="lbl">([^<]+)</div>', html.split('class="eg-ac-kpis"', 1)[1].split("</section>", 1)[0])
    assert rot == ["Diagnóstico", "Status pós-OS", "Em aberto", "Última atualização"]


def test_marcar_grava_e_volta_com_o_aviso(pagina_etm, cliente):
    from test_engenharia_acompanhamento import ANA, SAME, _como

    from nexus.engenharia import etm_marcas as M
    c = _como(cliente, ANA)
    r = c.post(URL_OS + "/marcar", data={"diagnostico": "2", "status_pos": "1"}, headers=SAME)
    assert r.status_code == 303 and r.headers["Location"].split("?", 1)[0].endswith(URL_OS) and "ok=" in r.headers["Location"]
    c.post(URL_OS + "/marcar", data={"evento": "etiqueta", "valor": "2", "ligado": "sim"}, headers=SAME)
    c.post(URL_OS + "/marcar", data={"evento": "acompanhamento", "ligado": "sim"}, headers=SAME)
    c.post(URL_OS + "/marcar", data={"evento": "finalizado", "ligado": "sim"}, headers=SAME)
    e = M.estado(M.ler(forcar=True)["eventos"])["60003"]
    assert (e["diagnostico_id"], e["status_pos_id"], e["etiquetas"], e["acompanhamento"], e["finalizado"]) == \
           (2, 1, {2}, True, True)
    html = c.get(URL_OS).get_data(as_text=True)
    assert '<option value="2" selected>Falha de Comunicação</option>' in html
    assert 'aria-pressed="true">Stand By</button>' in html and ">Tirar do acompanhamento</button>" in html
    assert "Diagnóstico: Falha de Comunicação" in _secao_os(html, "Comentários")      # a linha do tempo diz
    r = c.post(URL_OS + "/marcar", data={"diagnostico": "2", "status_pos": "1"}, headers=SAME)
    assert "Nada+mudou" in r.headers["Location"] or "Nada%20mudou" in r.headers["Location"]


def test_marcar_de_outro_site_e_recusado(pagina_etm, cliente):
    from test_engenharia_acompanhamento import ANA, _como
    r = _como(cliente, ANA).post(URL_OS + "/marcar", data={"diagnostico": "2"},
                                 headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_o_checklist_da_os_com_as_respostas(pagina_etm, cliente):
    from test_engenharia_acompanhamento import ANA, _como
    ch = _secao_os(_como(cliente, ANA).get(URL_OS).get_data(as_text=True), "Checklist da OS")
    assert ch.index("Descreva a atividade realizada") < ch.index("Piranômetro trocado") < \
           ch.index("Ficou alguma pendência? Se sim, descreva") < ch.index(">Não<")


def test_quem_nao_e_da_engenharia_le_as_marcacoes_sem_formularios(pagina_etm, cliente, monkeypatch):
    from test_engenharia_acompanhamento import BETO, _como

    from nexus.auth import setor_telas as ST
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": {"etm"}, "setor": {"id": 2, "nome": "Performance"},
                                               "erro": ""})
    p = _secao_os(_como(cliente, BETO).get(URL_OS).get_data(as_text=True), "Marcações da Engenharia")
    assert "<form" not in p and "<dt>Diagnóstico</dt><dd>—</dd>" in p


def test_os_que_nao_e_de_etm_abre_a_pagina_comum(pagina_etm, cliente):
    from test_engenharia_acompanhamento import ANA, _como
    r = _como(cliente, ANA).get("/t/engenharia/etm/os/17009")
    assert r.status_code == 302 and r.headers["Location"].endswith("/t/engenharia/equipe/os/17009")


def test_os_comentarios_sao_os_da_os_da_engenharia(pagina_etm, cliente):
    from test_engenharia_acompanhamento import ANA, _como
    html = _como(cliente, ANA).get(URL_OS).get_data(as_text=True)
    assert 'data-comentar="/os/_nexus/engenharia/os/60003/comentar"' in html
    assert 'data-volta="/t/engenharia/etm?atualizar=1"' in html            # a troca de responsável volta para ETMs


def test_o_login_do_fracttal_do_comentario_volta_para_a_os_da_etm(pagina_etm, cliente):
    # o comentário da página da ETM sem a sessão do Fracttal: o login dele volta para a página da ETM, não para a do Quadro
    import time

    from test_engenharia_acompanhamento import ANA, SAME
    with cliente.session_transaction() as s:
        s["logado"], s["admin"], s["usuario"] = True, False, ANA
        s["via"], s["ms_ate"] = "microsoft", time.time() + 3600
    html = cliente.get(URL_OS).get_data(as_text=True)
    assert 'data-de="/t/engenharia/etm/os/17003"' in html
    r = cliente.post("/os/_nexus/engenharia/os/60003/comentar",
                     json={"texto": "x", "folio": "17003", "de": "/t/engenharia/etm/os/17003"}, headers=SAME)
    assert r.status_code == 401 and "%2Ft%2Fengenharia%2Fetm%2Fos%2F17003" in r.get_json()["login"]
    r = cliente.post("/os/_nexus/engenharia/os/60003/comentar",
                     json={"texto": "x", "folio": "17003", "de": "https://outro.site/x"}, headers=SAME)
    assert "%2Ft%2Fengenharia%2Fequipe%2Fos%2F17003" in r.get_json()["login"]      # endereço estranho: a de sempre


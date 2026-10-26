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
    M.limpar()
    with app.app_context():
        yield api
    M.limpar()
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

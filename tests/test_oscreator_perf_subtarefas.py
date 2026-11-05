"""As subtarefas padrão de cada atividade da Performance no OS Creator (Levi, 05/11/2026: "Quero que no OS Creator >
Performance tenha um campo para subtarefas, que vamos poder editar as subtarefas padrões de cada atividade!"; "Quando
criamos uma OS as atividades já vem com aquelas subtarefas"; quem muda: "Qualquer um").

O que estes testes seguram (o Fracttal e o banco são de mentira; nomes e ids inventados):
- o livro do Nexus: salvar, voltar ao do Fracttal, a versão em vigor, o nome de quem salvou só cifrado, no catálogo;
- o formato: o plano vira a lista do editor, e a lista volta como subtarefas na forma das do plano (o tipo, as opções e a
  unidade de quem veio do plano; a nova na forma da 1ª), com a rede de segurança de volta às do plano;
- a validação da tela;
- a criação: uma OS por ativo e a agrupada levam o padrão no pedido ao Fracttal, ligadas ao plano;
- as rotas: o bloco lê, salva e volta; sem o banco do Nexus, não salva; a criação passa o padrão e avisa quando não o leu.
"""
import copy
import json
import sys
from pathlib import Path

import pytest
from _pytest.monkeypatch import MonkeyPatch
from test_campo_visao import banco  # noqa: F401  (fixture: o banco falso)

from nexus.dados import catalogo, explica
from nexus.torres.oscreator import ponte
from nexus.torres.oscreator import subtarefas_padrao as SP

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
from os_web import criar_app, perf_web, rotas  # noqa: E402
from test_oscreator_os_juntar import EVENTO, INSERIR_TAREFA, PROGRAMADA, FracttalFalso, _preparar, ativo  # noqa: E402

WEB = Path(ponte.RAIZ_CLONE, "os_web")
FRASE = "inspecao geral do inversor"
CONTA = {"nome": "Pessoa Teste", "email": "teste@exemplo.invalid"}
JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira

# o plano como o tasks_details o devolve (só os campos que contam): texto com anexo, sim/não, lista com opções, número com
# unidade
PLANO_SUBS = [
    {"id": "f1", "description": "Conferir o display", "id_task_form_item_type": 1, "task_form_item_type_description": "TEXT",
     "order_number": 1, "attachments_required": True, "is_required": True, "dropdown_options": None, "id_unit": None},
    {"id": "f2", "description": "Inversor ligado?", "id_task_form_item_type": 2,
     "task_form_item_type_description": "BOOLEAN", "order_number": 2, "attachments_required": False, "is_required": True,
     "dropdown_options": None, "id_unit": None},
    {"id": "f3", "description": "Estado do painel", "id_task_form_item_type": 7,
     "task_form_item_type_description": "DROPDOWN", "order_number": 3, "attachments_required": False,
     "is_required": False, "dropdown_options": ["Bom", "Ruim"], "id_unit": None},
    {"id": "f4", "description": "Tensão CC", "id_task_form_item_type": 3, "task_form_item_type_description": "NUMBER",
     "order_number": 4, "attachments_required": False, "is_required": True, "dropdown_options": None, "id_unit": 12,
     "unit_description": "V", "units_code": "V"},
]
PLANO = {"id_task": 900, "description": "[Grid Co.] - Inspeção Geral do Inversor", "subtasks": PLANO_SUBS,
         "duration": 1800, "id_priorities": 3, "tasks_types_main_description": "Preventiva", "id_task_type_main": 43886,
         "raw": {}}
LISTA = [{"desc": "Inversor ligado ao chegar?", "tipo": "verif", "anexo": True, "origem": "f2"},
         {"desc": "Foto da placa", "tipo": "texto", "anexo": True, "origem": None}]


# ── o formato ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_plano_vira_a_lista_do_editor():
    l = api.subtarefas_para_editor(PLANO_SUBS)
    assert [(x["desc"], x["tipo"], x["anexo"], x["origem"]) for x in l] == [
        ("Conferir o display", "texto", True, "f1"), ("Inversor ligado?", "simnao", False, "f2"),
        ("Estado do painel", "plano", False, "f3"), ("Tensão CC", "num", False, "f4")]
    assert l[2]["tipo_rotulo"] == "Lista" and "tipo_rotulo" not in l[0]


def test_a_lista_volta_na_forma_das_subtarefas_do_plano():
    lista = [{"desc": "Inversor ligado ao chegar?", "tipo": "verif", "anexo": True, "origem": "f2"},   # outro texto e tipo
             {"desc": "Estado do painel", "tipo": "plano", "anexo": False, "origem": "f3"},          # a lista do plano
             {"desc": "Tensão CC", "tipo": "num", "anexo": False, "origem": "f4"},                  # a unidade fica
             {"desc": "Foto da placa", "tipo": "texto", "anexo": True, "origem": None}]             # nova; a f1 saiu
    p = api.com_subtarefas_padrao(copy.deepcopy(PLANO), lista)
    s = p["subtasks"]
    assert [x["description"] for x in s] == [x["desc"] for x in lista] and [x["order_number"] for x in s] == [1, 2, 3, 4]
    assert (s[0]["id"], s[0]["id_task_form_item_type"], s[0]["task_form_item_type_description"],
            s[0]["attachments_required"]) == ("f2", 4, "CHECK", True)
    assert (s[1]["id"], s[1]["id_task_form_item_type"], s[1]["dropdown_options"], s[1]["is_required"]) == \
        ("f3", 7, ["Bom", "Ruim"], False)
    assert (s[2]["id"], s[2]["id_unit"], s[2]["unit_description"]) == ("f4", 12, "V")
    assert s[3]["id"] not in {"f1", "f2", "f3", "f4"} and s[3]["id_task_form_item_type"] == 1
    assert s[3]["attachments_required"] is True and s[3]["is_required"] is True and s[3]["dropdown_options"] is None
    assert [x["description"] for x in PLANO["subtasks"]][0] == "Conferir o display"     # cópia: o plano em cache não muda
    # a rede de segurança volta às do plano
    assert api.tem_subtarefas_padrao(p) and api.tem_subtarefas_extra(p)
    volta = api.sem_subtarefas_extra(p)
    assert [x["id"] for x in volta["subtasks"]] == ["f1", "f2", "f3", "f4"] and not api.tem_subtarefas_padrao(volta)
    # o "do plano" cuja subtarefa sumiu do plano (mexeram no Fracttal) vira texto, sem as opções
    p2 = api.com_subtarefas_padrao(copy.deepcopy(PLANO), [{"desc": "X", "tipo": "plano", "origem": "sumiu"}])
    assert p2["subtasks"][0]["id_task_form_item_type"] == 1 and p2["subtasks"][0]["dropdown_options"] is None


# ── a validação da tela ─────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("bruta, erro", [
    ([], "vazia"), ([{"desc": "  "}], "sem texto"), ([{"desc": "Anexo"}, {"desc": "ânexo "}], "duas vezes"),
    ([{"desc": "x" * 251}], "letras"), ([{"desc": "A", "tipo": "lista"}], "tipo"),
    ([{"desc": "S%d" % i} for i in range(41)], "No máximo")])
def test_a_tela_nao_salva_lista_torta(bruta, erro):
    lista, e = perf_web.validar_lista(bruta)
    assert lista == [] and erro in e


def test_a_lista_limpa():
    lista, e = perf_web.validar_lista([{"desc": "  Foto   da placa ", "tipo": "texto", "anexo": 1},
                                       {"desc": "Estado", "tipo": "plano", "origem": "f3", "tipo_rotulo": "Lista"},
                                       {"desc": "Sem origem", "tipo": "plano"}])
    assert not e and lista == [{"desc": "Foto da placa", "tipo": "texto", "anexo": True, "origem": None},
                               {"desc": "Estado", "tipo": "plano", "anexo": False, "origem": "f3", "tipo_rotulo": "Lista"},
                               {"desc": "Sem origem", "tipo": "texto", "anexo": False, "origem": None}]


# ── o livro do Nexus ────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def livro_limpo():
    SP.limpar()
    yield
    SP.limpar()


def test_o_padrao_salvo_vale_e_a_volta_ao_fracttal_fica_no_historico(app, banco, livro_limpo):
    assert SP.atual(FRASE)["lista"] is None and not SP.atual(FRASE)["erro"]   # o livro antes da 1ª gravação: o plano
    e = SP.salvar(FRASE, LISTA, CONTA, "Inspeção")
    assert e["lista"] == LISTA and e["tipo_tarefa"] == "Inspeção" and e["por"] == "Pessoa Teste" and e["evento"] == "salvou"
    assert e["quando"]
    linhas = banco.linhas(SP.LIVRO, SP.ABA)
    assert [(l["atividade"], l["evento"], str(l["n_subtarefas"]), l["tipo_tarefa"]) for l in linhas] == \
        [(FRASE, "salvou", "2", "Inspeção")]
    assert "Pessoa Teste" not in json.dumps(linhas, default=str, ensure_ascii=False) and linhas[0]["pessoa_hmac"]
    assert SP.atual("recomposicao de string")["lista"] is None                # a outra atividade não muda
    e = SP.voltar_ao_fracttal(FRASE, CONTA)
    assert e["lista"] is None and e["tipo_tarefa"] == "" and e["evento"] == "voltou_ao_fracttal"
    assert len(banco.linhas(SP.LIVRO, SP.ABA)) == 2                           # o histórico fica
    with pytest.raises(SP.Recusada, match="login"):
        SP.salvar(FRASE, LISTA, {"nome": "Sem E-mail"})


def test_o_livro_esta_no_catalogo_antes_da_1a_gravacao():
    l = catalogo.LIVRO_POR_NOME[SP.LIVRO]
    assert l.abas == (SP.ABA,) and l.so_cresce == (SP.ABA,) and not l.no_banco
    f = catalogo.POR_ID["versao_subtarefas"]
    assert f.livro == f"{SP.LIVRO} · {SP.ABA}" and f.chave == ("id",) and "pessoa_hmac" in SP.CAB
    assert "versao_subtarefas" in explica.RESUMO and "versao_subtarefas" in explica.PARA_QUE


# ── a criação ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _rodar(fn, **opcoes):
    fr = FracttalFalso(**opcoes)
    with MonkeyPatch.context() as mp:
        _preparar(mp, fr)
        mp.setattr(api, "get_plan_details", lambda idt, idi: copy.deepcopy(PLANO))
        ret = fn()
    return ret, [e["params"] for e in fr.eventos if e.get("pedido") == INSERIR_TAREFA]


def _itens():
    return [{"asset": ativo(1), "plano_id_task": 900, "plano_id_item": 1, "note": "n1", "gerar_ticket": False},
            {"asset": ativo(2), "plano_id_task": 900, "plano_id_item": 2, "note": "n2", "gerar_ticket": False}]


def _uma_por_ativo(padrao):
    return lambda: api.create_performance_os(_itens(), id_responsible=77, responsible_name="Ana Teste", event_date=EVENTO,
                                             prog_date=PROGRAMADA, subtarefas_padrao=padrao)


def _agrupada(padrao):
    return lambda: api.create_performance_os_agrupada(_itens(), id_responsible=77, responsible_name="Ana Teste",
                                                      event_date=EVENTO, prog_date=PROGRAMADA, subtarefas_padrao=padrao)


@pytest.mark.parametrize("caminho", [_uma_por_ativo, _agrupada])
def test_a_os_da_atividade_ja_sai_com_o_padrao(caminho):
    _ret, tarefas = _rodar(caminho(LISTA))
    assert len(tarefas) == 2
    for p in tarefas:
        assert [s["description"] for s in p["subtasks"]] == ["Inversor ligado ao chegar?", "Foto da placa"]
        assert [s["id_task_form_item_type"] for s in p["subtasks"]] == [4, 1]
        assert p["id_task"] == 900 and p["id_task_reference"] == 900                # a OS segue ligada ao plano
    _ret, tarefas = _rodar(caminho(None))                                           # sem padrão salvo: as do plano
    assert [s["description"] for s in tarefas[0]["subtasks"]] == [s["description"] for s in PLANO_SUBS]


def test_a_os_da_atividade_leva_o_tipo_de_tarefa_do_padrao():
    """No mesmo dia: "quero que dê para editar o tipo de tarefa também!": o tipo do padrão vence o do plano e o do app (a
    inspeção do inversor sairia Corretiva)."""
    _ret, tarefas = _rodar(lambda: api.create_performance_os(_itens(), id_responsible=77, responsible_name="Ana Teste",
                                                             event_date=EVENTO, prog_date=PROGRAMADA, subtarefas_padrao=LISTA,
                                                             tipo_tarefa_padrao="Inspeção"))
    assert {(t["tasks_types_main_description"], t["id_task_type_main"]) for t in tarefas} == \
        {("Inspeção", api.TASK_TYPE_MAIN["Inspeção"])}
    _ret, tarefas = _rodar(_uma_por_ativo(LISTA))                                    # sem tipo no padrão: o do app
    assert {t["tasks_types_main_description"] for t in tarefas} == {"Corretiva"}


def test_o_fracttal_que_recusa_o_padrao_cria_com_as_do_plano_e_diz():
    ret, tarefas = _rodar(_uma_por_ativo(LISTA), falha_tarefa=1)
    assert [len(t["subtasks"]) for t in tarefas] == [2, 4, 4]           # a recusada, a de novo e a 2ª, com as do plano
    assert "as subtarefas padrão do Nexus não entraram" in ret[0]["aviso"] and "aviso" not in ret[1]


# ── as rotas ────────────────────────────────────────────────────────────────────────────────────────────────────────
class _Gancho:
    Recusada = SP.Recusada

    def __init__(self, lista=None, erro="", tipo_tarefa=""):
        self.estado = {"lista": lista, "tipo_tarefa": tipo_tarefa, "evento": "salvou" if lista else "",
                       "quando": "05/11/2026 01:30" if lista else "", "por": "Pessoa Teste" if lista else "", "erro": erro}
        self.salvos = []

    def atual(self, frase):
        if frase != FRASE:                    # só a inspeção do inversor tem padrão salvo
            return {"lista": None, "tipo_tarefa": "", "evento": "", "quando": "", "por": "", "erro": self.estado["erro"]}
        return dict(self.estado)

    def salvar(self, frase, lista, conta, tipo_tarefa=""):
        if not conta.get("email"):
            raise SP.Recusada("Entre com o seu login do Fracttal no OS Creator")
        self.salvos.append((frase, lista, conta.get("email"), tipo_tarefa))
        self.estado = {"lista": lista, "tipo_tarefa": tipo_tarefa, "evento": "salvou", "quando": "05/11/2026 01:31",
                       "por": conta.get("nome"), "erro": ""}
        return dict(self.estado)

    def voltar(self, frase, conta):
        self.salvos.append((frase, None, conta.get("email"), ""))
        self.estado = {"lista": None, "tipo_tarefa": "", "evento": "voltou_ao_fracttal", "quando": "05/11/2026 01:32",
                       "por": "", "erro": ""}
        return dict(self.estado)


DO_PLANO = [{"desc": "Conferir o display", "tipo": "texto", "anexo": True, "origem": "f1"}]
PADRAO_DO_PLANO = {"lista": DO_PLANO, "tipo_tarefa": "Corretiva"}


@pytest.fixture
def cli(monkeypatch):
    import requests

    def sem_rede(*a, **k):                    # a cota do Fracttal é da empresa: aqui nada sai da máquina
        raise AssertionError("o teste tentou ir à rede")
    monkeypatch.setattr(requests.Session, "request", sem_rede)
    monkeypatch.setattr(api, "load_assets_cached", lambda *a, **k: [])
    monkeypatch.setattr(perf_web, "padrao_do_fracttal", lambda frase, assets: copy.deepcopy(PADRAO_DO_PLANO))
    monkeypatch.setattr(perf_web, "contar_subtarefas", lambda assets: {"recomposicao de string": ["a", "b"]})
    monkeypatch.setattr(perf_web, "SUBTAREFAS_PADRAO", None)
    rotas._MEMO.clear()
    chamadas = []
    monkeypatch.setattr(api, "create_performance_os", lambda itens, **kw: chamadas.append(kw) or [
        {"ok": True, "asset": it["asset"]["code"], "folio": str(16100 + i)} for i, it in enumerate(itens)])
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = dict(CONTA, perfil="ADMINISTRATOR")
    c.chamadas = chamadas
    yield c
    rotas._MEMO.clear()


def test_sem_o_banco_do_nexus_mostra_o_do_plano_e_nao_salva(cli):
    j = cli.get("/os/api/performance/subtarefas?frase=" + FRASE).get_json()
    assert (j["origem"], j["lista"], j["pode_salvar"], j["tipo_tarefa"]) == ("fracttal", DO_PLANO, False, "Corretiva")
    assert [t[0] for t in j["tipos"]] == ["texto", "simnao", "verif", "num"] and "Preventiva" in j["tipos_tarefa"]
    r = cli.post("/os/api/performance/subtarefas", json={"frase": FRASE, "lista": LISTA})
    assert r.status_code == 503 and "não pode ser salvo" in r.get_json()["erro"]


def test_o_bloco_le_salva_e_volta_ao_do_fracttal(cli, monkeypatch):
    g = _Gancho()
    monkeypatch.setattr(perf_web, "SUBTAREFAS_PADRAO", g)
    assert cli.get("/os/api/performance/subtarefas?frase=" + FRASE).get_json()["origem"] == "fracttal"
    r = cli.post("/os/api/performance/subtarefas", json={"frase": FRASE, "lista": [dict(x, desc=" " + x["desc"]) for x in LISTA],
                                                         "tipo_tarefa": "Preventiva"})
    j = r.get_json()
    assert r.status_code == 200 and (j["origem"], j["lista"], j["por"], j["do_plano"]) == ("nexus", LISTA, "Pessoa Teste", DO_PLANO)
    assert (j["tipo_tarefa"], j["tipo_do_plano"]) == ("Preventiva", "Corretiva")
    assert g.salvos == [(FRASE, LISTA, CONTA["email"], "Preventiva")]        # a lista limpa e o tipo, de quem está logado
    r = cli.post("/os/api/performance/subtarefas", json={"frase": FRASE, "lista": [{"desc": ""}]})
    assert r.status_code == 400 and "sem texto" in r.get_json()["erro"] and len(g.salvos) == 1
    r = cli.post("/os/api/performance/subtarefas", json={"frase": FRASE, "lista": LISTA, "tipo_tarefa": "Inventada"})
    assert r.status_code == 400 and "não existe" in r.get_json()["erro"] and len(g.salvos) == 1
    r = cli.post("/os/api/performance/subtarefas", json={"frase": "outra coisa", "lista": LISTA})
    assert r.status_code == 400
    j = cli.post("/os/api/performance/subtarefas", json={"frase": FRASE, "voltar": True}).get_json()
    assert j["origem"] == "fracttal" and j["lista"] == DO_PLANO and j["tipo_tarefa"] == "Corretiva"
    assert g.salvos[-1] == (FRASE, None, CONTA["email"], "")
    def recusa(*a):                           # o Nexus recusou (sem a chave do banco, sem o e-mail): a tela diz o motivo
        raise SP.Recusada("Este Nexus não tem a chave de gravação do banco (GRIDCO_SQL_TOKEN)")
    monkeypatch.setattr(g, "salvar", recusa)
    r = cli.post("/os/api/performance/subtarefas", json={"frase": FRASE, "lista": LISTA})
    assert r.status_code == 400 and "GRIDCO_SQL_TOKEN" in r.get_json()["erro"]


def _corpo():
    return {"frase": FRASE, "base": "Inspeção Geral do Inversor", "modo": "geracao", "evento": "2026-11-05T08:00",
            "gerar_ticket": False, "responsavel": {"id_personnel": 501, "name": "Pessoa Teste"}, "agrupar": False,
            "itens": [{"asset": {"id": 1, "code": "TST-INV11", "label": "Inversor 1.1", "tipo": "Inversor"},
                       "plano_id_task": 900, "plano_id_item": 1, "linkar": True, "note": "", "os_pai": ""}]}


def test_a_criacao_leva_o_padrao_e_avisa_quando_nao_o_leu(cli, monkeypatch):
    monkeypatch.setattr(perf_web, "SUBTAREFAS_PADRAO", _Gancho(lista=LISTA, tipo_tarefa="Preventiva"))
    j = cli.post("/os/api/performance/criar", json=_corpo()).get_json()
    assert cli.chamadas[-1]["subtarefas_padrao"] == LISTA and cli.chamadas[-1]["tipo_tarefa_padrao"] == "Preventiva"
    assert "alerta" not in j
    monkeypatch.setattr(perf_web, "SUBTAREFAS_PADRAO", _Gancho(erro="ConnectionError: o banco caiu"))
    j = cli.post("/os/api/performance/criar", json=_corpo()).get_json()
    assert cli.chamadas[-1]["subtarefas_padrao"] is None and cli.chamadas[-1]["tipo_tarefa_padrao"] is None
    assert j["alerta"] is True and "Não consegui ler as subtarefas padrão do Nexus" in j["mensagem"]


def test_o_resumo_do_plano_diz_o_tipo_do_padrao(cli, monkeypatch):
    import catalogos_planos
    monkeypatch.setattr(catalogos_planos, "detalhe_do_plano", lambda idt, idi: copy.deepcopy(PLANO))
    url = "/os/api/performance/plano?id_task=900&id_item=1&frase=" + FRASE
    assert "Tipo: Corretiva" in cli.get(url).get_json()["resumo"]          # o do app (a inspeção sai Corretiva)
    monkeypatch.setattr(perf_web, "SUBTAREFAS_PADRAO", _Gancho(lista=LISTA, tipo_tarefa="Preventiva"))
    assert "Tipo: Preventiva" in cli.get(url).get_json()["resumo"]


def test_o_card_da_atividade_conta_o_padrao_salvo(cli, monkeypatch):
    monkeypatch.setattr(perf_web, "SUBTAREFAS_PADRAO", _Gancho(lista=LISTA))
    d = cli.get("/os/api/performance/contagens").get_json()["contagens"]
    assert d[FRASE] == [x["desc"] for x in LISTA] and d["recomposicao de string"] == ["a", "b"]


def test_a_tela_tem_o_bloco_das_subtarefas():
    html = (WEB / "templates" / "perf_criar.html").read_text(encoding="utf-8")
    assert 'id="w_subs"' in html and "Tipo e subtarefas da atividade" in html and 'id="b_subs_salvar"' in html
    assert "para todo mundo" in html and 'id="b_subs_fracttal" hidden' in html and 'id="subs_tipo_sel"' in html
    js = (WEB / "static" / "perf.js").read_text(encoding="utf-8")
    bloco = js.split("As subtarefas padrão da atividade", 1)[1].split("// arranque", 1)[0]
    assert "/os/api/performance/subtarefas" in bloco and "subsSalvar({voltar: true})" in bloco
    assert "tipo_tarefa: subsTipoSel.value" in bloco and "subtarefas') === 'editar'" in bloco
    assert "confirm(" not in bloco and "alert(" not in bloco                 # o aviso de que vale para todos fica escrito
    # o "ver lista" dos cards da tela de Performance mostra a lista em vigor e leva ao editor (Levi, 05/11/2026)
    inicio = (WEB / "templates" / "performance.html").read_text(encoding="utf-8")
    assert "/os/api/performance/subtarefas?frase=" in inicio and "searchParams.set('subtarefas', 'editar')" in inicio
    assert "Editar as subtarefas" in inicio and "Tipo de tarefa:" in inicio

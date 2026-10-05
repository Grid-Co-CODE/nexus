"""A fonte das telas do Campo · App pelos livros que o próprio App grava no banco (v226, 05/10/2026): a nota é a do
painel do App, a pessoa vem pelo código (HMAC do e-mail) e, sem a chave do código, a fonte segue o livro do coletor."""
import json

import pytest
from flask import Flask
from pg_falso import ApiPGFalsa

from nexus.campo import fonte_pg, livros_app, ordens, regras_app, tabelas
from nexus.campo.ligacao_cadastro import codigo_da_pessoa

BASE = "http://pg.falso"
CHAVE = "chave-de-teste-do-codigo"
COLS = ["Registrado em", "OS", "ID da OS no Fracttal", "Tarefa", "Código do ativo", "Usina", "Região", "Tipo da OS",
        "Criticidade", "Técnico (HMAC)", "Nota do painel", "Composição da nota", "Observação no App",
        "Observação suficiente", "GPS no início e no fim", "Pontual", "Offline", "Fotos", "Fotos com descrição",
        "Assinou", "Obrigatórias respondidas", "Todas respondidas", "Peças", "XP", "Revisão", "Devolvida",
        "Previsto (min)", "Execução (min)", "Reprogramada", "Vezes reprogramada", "Hora do celular"]
COLS_RONDA = ["Data", "OS", "Usina", "Ativo da usina no Fracttal", "ID da OS no Fracttal", "Região", "Técnico", "Tipo",
              "Situação da OS", "Nota da ronda", "Falhas", "Trackers apontados", "Trackers respondidos", "Início", "Fim",
              "OS criada em"]


def _fech(folio, nota, rev=None, email="tec1@gridco.com.br", **kw):
    d = {"Registrado em": "2026-10-04T14:00:00.000Z", "OS": str(folio), "ID da OS no Fracttal": str(folio * 10),
         "Tarefa": f"Tarefa {folio}", "Código do ativo": "USA-INV1", "Usina": "Usina A", "Região": "SP 01",
         "Tipo da OS": "Preventiva", "Criticidade": "Alta", "Técnico (HMAC)": codigo_da_pessoa(CHAVE, email),
         "Nota do painel": nota, "Composição da nota": "[]", "Observação no App": None,
         "Observação suficiente": "não", "GPS no início e no fim": "sim", "Pontual": "sim", "Offline": "não",
         "Fotos": 3, "Fotos com descrição": 3, "Assinou": "sim", "Obrigatórias respondidas": "sim",
         "Todas respondidas": "sim", "Peças": 0, "XP": 10, "Revisão": rev, "Devolvida": None, "Previsto (min)": 30,
         "Execução (min)": 45, "Reprogramada": "não", "Vezes reprogramada": 0,
         "Hora do celular": "2026-10-04T13:58:00.000Z"}
    d.update(kw)
    return {"headers": COLS, "values": [d[c] for c in COLS]}


def _ronda(folio, data="2026-10-03", **kw):
    d = {c: None for c in COLS_RONDA}
    d.update({"Data": data, "OS": str(folio) if folio else None, "Usina": "Usina B", "Região": "SP 01",
              "Técnico": "Técnico Um", "Tipo": "curta", "Nota da ronda": 87, "ID da OS no Fracttal": "990"})
    d.update(kw)
    return {"headers": COLS_RONDA, "values": [d[c] for c in COLS_RONDA]}


@pytest.fixture
def livros(tmp_path):
    api = ApiPGFalsa()
    api._id(livros_app.LIVRO_FECHAMENTOS, "Fechamentos")["linhas"] = [
        _fech(15377, 72), _fech(15378, 90, rev="aprovada", Devolvida="sim"), _fech(15379, 55, rev="devolvida"),
        _fech(15380, 40, email="ninguem@gridco.com.br")]
    api._id(livros_app.LIVRO_RONDAS, "OS de ronda")["linhas"] = [_ronda(15390), _ronda(None)]
    ident = tmp_path / "identidades.json"
    ident.write_text(json.dumps({"porEmail": {"tec1@gridco.com.br": {"nome": "Técnico Um", "supervisor": "Sup A"}}}),
                     encoding="utf-8")
    app = Flask(__name__)
    app.config.update(TESTING=True, NEXUS_CAMPO_IDENTIDADES=str(ident))
    f = fonte_pg.Fornecedor({"GRIDCO_DB_API": BASE, "NEXUS_PESSOA_HMAC": CHAVE}, sessao=api)
    tabelas.usar_fornecedor(f)
    with app.app_context():
        yield f, api
    tabelas.usar_fornecedor(None)


def _reg():
    return {e["os"]: e for e in tabelas.tabela("qualidadelog").query_entities("PartitionKey eq 'q'")}


def test_a_nota_e_a_do_painel_do_app_e_a_pessoa_vem_pelo_codigo(livros):
    f, _api = livros
    assert f.do_app and f.completa() and f.serve("qualidadelog")
    e = _reg()["15377"]
    assert e["qualidade"] == 72 and e["pontual"] is True and e["geo_ok"] and e["assinou"] and not e["obs_ok"]
    assert e["email"] == "tec1@gridco.com.br" and e["nome"] == "Técnico Um"
    assert e["dur_prev"] == 30 and e["exec_min"] == 45 and e["fx_tipo"] == "Preventiva"
    assert e["fx_dur_prev_min"] == 0 and e["fx_dur_real_min"] == 0      # a duração do Fracttal o livro não traz
    assert e["server_ts"] == "2026-10-04T14:00:00.000Z" and e["fx_final"] == "2026-10-04T13:58:00.000Z"
    assert _reg()["15380"]["email"] == ""                  # código que o cadastro do App não conhece: sem pessoa


def test_situacao_pela_revisao_do_painel(livros):
    r = _reg()
    assert r["15377"]["fx_status"] == 0 and r["15379"]["fx_status"] == 0     # desconhecida: não vira "em verificação"
    assert r["15378"]["fx_status"] == livros_app.STATUS_APROVADA and r["15378"]["foi_devolvida"]
    assert r["15378"]["fx_rating"] == 0 and r["15378"]["fx_aprov"] == ""    # o livro ainda não traz (ver o módulo)


def test_par_os_ronda_so_com_os(livros):
    os_ = list(tabelas.tabela("rondaos").query_entities("PartitionKey eq 'os'"))
    assert [o["folio"] for o in os_] == ["15390"]
    r = list(tabelas.tabela("rondas").query_entities("PartitionKey ge '2026-10-01'"))
    assert r[0]["qualidade"] == 87 and r[0]["nome"] == "Técnico Um" and "finalizada" not in r[0]


def test_frescor_e_o_fechamento_mais_recente(livros):
    f, _api = livros
    assert f.coleta() == "2026-10-04T14:00:00.000Z"


def test_ordens_de_servico_saem_do_livro_do_app(livros):
    d = regras_app._gestao_os(3650, {}, None, inteira=True)
    assert d["resumo"]["os"] == 4 and d["resumo"]["devolvidas"] >= 1
    assert {l["os"]: l["qualidade"] for l in d["linhas"]} == {"15377": 72, "15378": 90, "15379": 55, "15380": 40}
    # o livro do App tem a pontualidade: a tela mostra o número (com o coletor, "sem dado"); não tem a situação nem
    # as durações do Fracttal: "—", em vez de um número errado
    a = ordens._ajuste_da_fonte(d)["resumo"]
    assert a["pontualidade_pct"] == 100 and a["em_verificacao"] is None and a["tempo_vs_previsto_pct"] is None


def test_sem_a_chave_do_codigo_segue_o_livro_do_coletor(tmp_path):
    f = fonte_pg.Fornecedor({"GRIDCO_DB_API": BASE}, sessao=ApiPGFalsa())
    assert not f.do_app


def test_livro_que_nao_existe_e_vazio():
    assert livros_app.ler(BASE, ApiPGFalsa(), livros_app.LIVRO_FECHAMENTOS) == []

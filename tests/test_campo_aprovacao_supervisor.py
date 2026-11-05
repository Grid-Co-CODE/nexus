"""Aprovação de OS, pedido do Levi de 08/10/2026: a fila inteira (sem "OS fechadas nos X dias"); desde 05/11/2026 em
quadro por fatos (`test_campo_aprovacao_responsavel.py`). O Aprovar com a regra no servidor saiu em 18/10/2026 (Levi:
"pode tirar a rota antiga!"): aprovar é o Concluir do OS Creator. Com a estrutura de O&M de 10/2026 (Levi,
08/10: "pode adaptar, deixa as vagas preparadas"; o Supervisor de Campo "aprova e fecha as OS"): os cartões são por
região de campo (com a alternância para gestor de contrato) e QUEM APROVA é o Supervisor de Campo da região da usina; com
a vaga aberta, o Coordenador de Campo; sem os dois, só um administrador. O Gestor de contrato não aprova.

Fracttal FALSO do começo ao fim: nenhuma OS de verdade é aprovada, e o Concluir do OS Creator é trocado por um
gravador (o portão é provado até a porta do clone, com o caminho, o método e o cookie que ele levaria)."""
import re
from datetime import datetime, timedelta

import pytest
from pg_falso import ApiPGFalsa
from test_campo_aprovacao import FracttalFalso
from test_campo_regras_app import TabelaFalsa
from test_campo_visao import CHAVE_CADASTRO, EQUIPES, REGIOES, _aba, _pessoas

from nexus.campo import aprovacao, fracttal, leitura, regras_app, tabelas, visao

CRIADA_15088 = "2026-09-01T01:30:00.123+00:00"      # 31/08 às 22:30 em Brasília: a data certa é 31/08


def _quando(atras_dias):
    return (datetime.utcnow() - timedelta(days=atras_dias)).strftime("%Y-%m-%dT%H:%M:%S")


def _tarefa(folio, atras, usina, tarefa=1, criada=None, tecnico="Técnico 1"):
    """Uma tarefa em revisão como o REST do Fracttal devolve (work_orders?id_status_work_order=2), com o
    `creation_date` da OS, que vem na mesma linha."""
    return {"id_work_orders_tasks": int(folio) * 10 + tarefa, "id_work_order": int(folio), "wo_folio": str(folio),
            "final_date": _quando(atras), "personnel_description": tecnico, "groups_1_description": usina,
            "groups_2_description": "Área", "items_log_description": "Inversor 1",
            "tasks_description": f"Tarefa {tarefa} da OS {folio}", "rating": 0,
            "creation_date": criada or (datetime.utcnow() - timedelta(days=atras + 2)).strftime("%Y-%m-%dT%H:%M:%S+00:00")}


def _nota(folio, qualidade, devolvida=False):
    return {"PartitionKey": "q", "RowKey": f"q{folio}", "os": str(folio), "server_ts": _quando(1),
            "qualidade": qualidade, "foi_devolvida": devolvida, "foto_divergente": False,
            "fx_dur_prev_min": 60, "fx_dur_real_min": 70}


@pytest.fixture
def fila(app):
    """Cadastro: a usina "SP 01" do Fracttal é da SP Norte 01, região Sudeste 03 (supervisora de campo 92, coordenador
    93); a "SC 01" é da SC Oeste 01, região Sul 01, com a vaga de supervisor aberta (aprova o coordenador 93). Gestores de
    contrato: Beltrano (90) na SP, Ciclano (91) na SC. Fila: 15088 (SP, 2 tarefas, nota 71, já devolvida), 15102 (SP, nota
    96), 15002 (SP, fechada há 120 dias, fora do App) e 16001 (SC, nota 90)."""
    api = ApiPGFalsa()
    _aba(api, "cadastro_nexus", "usinas", [
        {"usina_id": 1, "nome": "Usina A", "status": "OPERAÇÃO", "equipe_id": 10, "data_mobilizacao": "2025-01-01",
         "uf": "SP", "gestor_contrato_id": 90},
        {"usina_id": 3, "nome": "Usina C", "status": "OPERAÇÃO", "equipe_id": 20, "data_mobilizacao": "2025-01-01",
         "uf": "SC", "gestor_contrato_id": 91}])
    _aba(api, "cadastro_nexus", "equipes", EQUIPES)
    _aba(api, "cadastro_nexus", "regioes_campo", REGIOES)
    _aba(api, "cadastro_nexus", "clientes", [])
    _aba(api, "cadastro_nexus", "de_para", [
        {"usina_id": 1, "sistema": "Fracttal · Classificação 1", "chave_externa": "SP 01"},
        {"usina_id": 3, "sistema": "Fracttal · Classificação 1", "chave_externa": "SC 01"}])
    _aba(api, "cadastro_nexus", "pessoas", _pessoas())
    app.config.update(GRIDCO_DB_API="http://pg.falso", NEXUS_CHAVE_CADASTRO=CHAVE_CADASTRO)
    app.extensions["nexus_dados_sessao"] = api
    dados = {"qualidadelog": [_nota(15088, 71, devolvida=True), _nota(15102, 96), _nota(16001, 90)]}
    fx = FracttalFalso([_tarefa(15002, 120, "SP 01", tecnico="Técnico 7"),
                        _tarefa(15088, 8, "SP 01", 1, CRIADA_15088), _tarefa(15088, 8, "SP 01", 2, CRIADA_15088),
                        _tarefa(15102, 4, "SP 01"), _tarefa(16001, 3, "SC 01")])
    fx.api = api
    tabelas.usar_fornecedor(lambda nome: TabelaFalsa(dados.setdefault(nome, [])))
    fracttal.usar_fornecedor(fx)
    leitura.limpar_cache()
    visao.limpar()
    yield fx
    tabelas.usar_fornecedor(None)
    fracttal.usar_fornecedor(None)
    leitura.limpar_cache()
    visao.limpar()
    app.extensions.pop("nexus_dados_sessao", None)


# ── 1. a fila inteira, sem período ──────────────────────────────────────────────────────────────────────────────
def test_fila_inteira_sem_o_filtro_de_dias(fila, logado):
    """Levi, 08/10: "não deve ter filtro 'OS fechadas nos X dias'... ficar preso nessa visão é foda"."""
    html = logado.get("/t/campo/aprovacao").get_data(as_text=True)
    assert "OS fechadas nos" not in html and 'name="dias"' not in html and "últimos 30 dias" not in html
    # a 15002 fechou há 120 dias: com a janela padrão de antes (30 dias) ela sumia da conta
    assert '<b class="gc-num">4</b> OS esperando aprovação, a fila inteira' in html
    assert 'data-folio="15002"' in html and "120 d" in html
    assert aprovacao.FILA_INTEIRA == {"dias": "3650"}


def test_conta_da_fila_inteira_fica_pronta_depois_da_releitura(fila, logado, monkeypatch):
    """A conta que a releitura em segundo plano deixa pronta é a da fila inteira: a visita seguinte não refaz a conta
    nem pede nada ao Fracttal."""
    pendentes = []
    monkeypatch.setattr(aprovacao, "em_segundo_plano", pendentes.append)
    chamadas = []
    original = regras_app._fila_supervisao
    monkeypatch.setattr(regras_app, "_fila_supervisao", lambda req, esc: chamadas.append(dict(req.params)) or original(req, esc))
    assert "Lendo a fila de verificação do Fracttal" in logado.get("/t/campo/aprovacao").get_data(as_text=True)
    assert fila.pedidos == [] and len(pendentes) == 1
    pendentes[0]()                                            # a releitura: lê o Fracttal e já faz a conta
    assert chamadas and all(c["dias"] == "3650" for c in chamadas)
    feitas, pedidos = len(chamadas), len(fila.pedidos)
    html = logado.get("/t/campo/aprovacao").get_data(as_text=True)
    assert "Usina A" in html and "fila lida em" in html
    assert len(chamadas) == feitas and len(fila.pedidos) == pedidos     # nada refeito, nada pedido ao Fracttal


# ── 2. o quadro no lugar da lista das usinas (05/11/2026) ─────────────────────────────────────────────────────────
def test_enderecos_antigos_abrem_o_quadro(fila, logado):
    """Os cartões por região de campo e por gestor de contrato (18/10/2026), as visões por técnico e fila (08/10/2026) e a
    lista das usinas com os indicadores e a barra da idade (05/11/2026) saíram: o endereço guardado de antes abre o
    quadro."""
    for q in ("?por=gestor", "?ver=Sudeste+03", "?regiao_campo=Sudeste+03", "?gestor=Ciclano+Chefe",
              "?equipe=SP+Norte+01", "?vista=tecnicos", "?balde=olho", "?idade=30-"):
        html = logado.get("/t/campo/aprovacao" + q).get_data(as_text=True)
        assert 'class="apq-quadro"' in html and "<h2>Por gestor de contrato</h2>" not in html, q
        assert 'class="ap-usinas"' not in html and "<th>Técnico</th>" not in html and "Idade da fila" not in html, q


def test_csv_tem_as_colunas_do_quadro(fila, logado):
    r = logado.get("/t/campo/aprovacao?csv=1")
    texto = r.get_data(as_text=True)
    assert r.mimetype == "text/csv" and "aprovacao-os.csv" in r.headers["Content-Disposition"]
    assert texto.splitlines()[0].lstrip("\ufeff") == (
        "OS;Dias esperando;Criação da OS;Data fim;Responsável O&M;Usina;Cliente;Técnicos;Tarefas;Nota do App;Coluna;Motivos")
    # a criação em Brasília: 01:30 UTC de 01/09 é 31/08
    assert "15088;8;31/08/26;" in texto and "\n16001;" in texto


# ── 3. quem entrou pelo Fracttal (as telas que vêm já filtradas usam) ─────────────────────────────────────────
def _sessao_nexus(cliente, papel=None, admin=False):
    """Quem entrou no Nexus pelo Fracttal (não admin), com o papel que o login grava (`supervisor_padrao`).

    Com `admin`, o e-mail vai para a NEXUS_ADMINS: desde a tela Base → Acessos (11/10/2026) o `admin` da sessão do
    Fracttal segue a lista de administradores a cada pedido (`auth._admin_em_dia`), e forjar só a sessão não vale mais."""
    email = "x@exemplo.test"
    if admin:
        cfg = cliente.application.config
        cfg["NEXUS_ADMINS"] = ",".join(filter(None, [cfg.get("NEXUS_ADMINS"), email]))
    with cliente.session_transaction() as s:
        s.clear()
        s.update(logado=True, admin=admin, usuario={"email": email, "nome": "X", "perfil": "Supervisor"})
        if papel:
            s["supervisor_padrao"] = papel

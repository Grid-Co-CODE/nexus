"""Aprovação de OS, pedido do Levi de 08/10/2026: a fila inteira (sem "OS fechadas nos X dias") e a tabela das OS com as
colunas pedidas (desde 18/10/2026 na lista por usina, `test_campo_aprovacao_responsavel.py`). O Aprovar com a regra no
servidor saiu em 18/10/2026 (Levi: "pode tirar a rota antiga!"): aprovar é o Concluir do card do OS Creator. Com a estrutura de O&M de 10/2026 (Levi,
08/10: "pode adaptar, deixa as vagas preparadas"; o Supervisor de Campo "aprova e fecha as OS"): os cartões são por
região de campo (com a alternância para gestor de contrato) e QUEM APROVA é o Supervisor de Campo da região da usina; com
a vaga aberta, o Coordenador de Campo; sem os dois, só um administrador. O Gestor de contrato não aprova.

Fracttal FALSO do começo ao fim: nenhuma OS de verdade é aprovada, e o Concluir do OS Creator é trocado por um
gravador (o portão é provado até a porta do clone, com o caminho, o método e o cookie que ele levaria)."""
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone

import pytest
from pg_falso import ApiPGFalsa
from test_campo_aprovacao import FracttalFalso
from test_campo_regras_app import TabelaFalsa
from test_campo_visao import CHAVE_CADASTRO, EQUIPES, REGIOES, _aba, _pessoas

from nexus.campo import aprovacao, fracttal, leitura, regras_app, tabelas, visao

BRT = timezone(timedelta(hours=-3))
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


def _tabela(html, usina="Usina A"):
    """As linhas da tabela das OS da usina: [[célula, ...], ...] em texto (18/10/2026: a lista é por usina)."""
    corpo = html.split(f'<span class="ap-u-nome"><b>{usina}</b>')[1].split("</details>")[0]
    linhas = re.findall(r'<tr class="ap-os".*?</tr>', corpo, re.S)
    return [[" ".join(re.sub(r"<[^>]+>", " ", c).split()) for c in re.findall(r"<td[^>]*>(.*?)</td>", l, re.S)]
            for l in linhas]


# ── 1. a fila inteira, sem período ──────────────────────────────────────────────────────────────────────────────
def test_fila_inteira_sem_o_filtro_de_dias(fila, logado):
    """Levi, 08/10: "não deve ter filtro 'OS fechadas nos X dias'... ficar preso nessa visão é foda"."""
    html = logado.get("/t/campo/aprovacao").get_data(as_text=True)
    assert "OS fechadas nos" not in html and 'name="dias"' not in html and "últimos 30 dias" not in html
    # a 15002 fechou há 120 dias: com a janela padrão de antes (30 dias) ela sumia da conta
    assert "4<small>OS</small>" in html and "com 5 tarefas, a fila inteira" in html
    assert "mais de 60 dias" in html
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


# ── 2. a lista das usinas, cada uma com a tabela das OS dela (18/10/2026, Levi: "quero apenas por responsável da UFV,
# quando abrir aparece uma lista das usinas que tem OSs não concluídas") ─────────────────────────────────────────────
def test_a_usina_abre_a_tabela_das_os_com_as_colunas_pedidas(fila, logado):
    html = logado.get("/t/campo/aprovacao").get_data(as_text=True)
    corpo = html.split('<span class="ap-u-nome"><b>Usina A</b>')[1].split("</details>")[0]
    cab = re.findall(r"<th[^>]*>([^<]+)</th>", corpo.split("</thead>")[0])
    assert cab == ["OS", "Dia", "Data da criação da OS", "Data fim", "Técnicos", "Grupo", "Prontas", "Pedem olho",
                   "Fora do App", "Uso do App", "Nota média", "Devolvidas"]
    linhas = {l[0]: l for l in _tabela(html)}
    assert list(linhas) == ["15002", "15088", "15102"]                          # a mais antiga primeiro
    fim = (datetime.utcnow() - timedelta(days=8)).replace(tzinfo=timezone.utc).astimezone(BRT).strftime("%d/%m/%y")
    # OS, Dia, criação (em Brasília: 01:30 UTC de 01/09 é 31/08), fim, técnicos, grupo, prontas, olho, fora, uso, nota,
    # devolvidas
    assert linhas["15088"] == ["15088", "8 d", "31/08/26", fim, "Técnico 1", "Precisa do seu olho", "0", "2", "0",
                               "100%", "71%", "2"]
    assert linhas["15102"][6:] == ["1", "0", "0", "100%", "96%", "—"]
    assert linhas["15002"][1] == "120 d" and linhas["15002"][6:] == ["0", "0", "1", "0%", "—", "—"]
    assert [l[0] for l in _tabela(html, "Usina C")] == ["16001"]               # a SC 01 é a Usina C


def test_enderecos_antigos_abrem_a_lista(fila, logado):
    """Os cartões por região de campo e por gestor de contrato saíram (Levi, 18/10/2026: "quero apenas por responsável
    da UFV"): quem guardou o endereço de antes cai na lista das usinas."""
    for q in ("?por=gestor", "?ver=Sudeste+03", "?regiao_campo=Sudeste+03", "?gestor=Ciclano+Chefe", "?equipe=SP+Norte+01"):
        html = logado.get("/t/campo/aprovacao" + q).get_data(as_text=True)
        assert 'class="ap-usinas"' in html and "<h2>Por gestor de contrato</h2>" not in html, q


def test_paradas_ha_30_dias_ou_mais_mostra_todas_as_que_conta(fila, logado):
    """O cartão "Paradas há 30 dias ou mais" conta as OS com 30 dias ou mais, e o clique tem de mostrar as MESMAS. Ele
    levava a "31 a 60 dias": com a fila inteira (08/10), a 15002, parada há 120 dias, contava no cartão e sumia no clique."""
    html = logado.get("/t/campo/aprovacao").get_data(as_text=True)
    assert 'href="?idade=30-"' in html and 'href="?idade=31-60"><span class="gc-rotulo">Paradas' not in html
    html = logado.get("/t/campo/aprovacao?idade=30-").get_data(as_text=True)
    assert [l[0] for l in _tabela(html)] == ["15002"] and "esperando há 30 dias ou mais" in html
    assert "Usina C</b>" not in html
    assert 'aria-current="true"><span class="gc-rotulo">Paradas' in html                       # ativo
    # a barra de idade continua com as cinco faixas (a de "30 dias ou mais" é só do cartão)
    assert "?idade=30-" not in html.split('class="cn-idades-barra"')[1].split("</div>")[0]


def test_por_tecnico_e_fila_sairam(fila, logado):
    """Levi, 08/10: "a visão de por técnico e fila pode matar, pode tirar que é irrelevante!"."""
    html = logado.get("/t/campo/aprovacao").get_data(as_text=True)
    assert "Por técnico" not in html and "Fila de verificação</h2>" not in html and "vista=" not in html
    html = logado.get("/t/campo/aprovacao?vista=tecnicos").get_data(as_text=True)    # endereço antigo: a lista
    assert 'class="ap-usinas"' in html and "<th>Técnico</th>" not in html


def test_csv_tem_as_colunas_da_tabela(fila, logado):
    r = logado.get("/t/campo/aprovacao?csv=1")
    texto = r.get_data(as_text=True)
    assert r.mimetype == "text/csv" and "aprovacao-os.csv" in r.headers["Content-Disposition"]
    assert texto.splitlines()[0].lstrip("\ufeff") == (
        "OS;Dias esperando;Criação da OS;Data fim;Responsável O&M;Usina;Cliente;Técnicos;Tarefas;Prontas;Pedem olho;"
        "Fora do App;Uso do App (%);Nota média;Devolvidas;Grupo da OS")
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


def _ler_fila(cliente):
    cliente.get("/t/campo/aprovacao?regiao_campo=*")      # nos testes a releitura roda na hora


@pytest.mark.skipif(not shutil.which("node"), reason="sem node nesta máquina")
def test_o_script_da_tela_e_javascript_valido(fila, logado, tmp_path):
    """Até 08/10 o confirm() do Aprovar tinha uma quebra de linha DENTRO da string: o script inteiro não rodava (nem a
    linha abria, nem o Aprovar funcionava). Desde 18/10 o script é o que abre o card da OS."""
    _ler_fila(logado)
    html = logado.get("/t/campo/aprovacao").get_data(as_text=True)
    scripts = [s for s in re.findall(r"<script>(.*?)</script>", html, re.S) if "tr.ap-os" in s]
    assert scripts
    arq = tmp_path / "aprovacao.js"
    arq.write_text(scripts[0], encoding="utf-8")
    r = subprocess.run(["node", "--check", str(arq)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

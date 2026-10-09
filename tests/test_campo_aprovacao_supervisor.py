"""Aprovação de OS, pedido do Levi de 08/10/2026: a fila inteira (sem "OS fechadas nos X dias"), os cartões que abrem a
tabela das OS com as colunas pedidas, e o Aprovar com a regra no servidor. Com a estrutura de O&M de 10/2026 (Levi,
08/10: "pode adaptar, deixa as vagas preparadas"; o Supervisor de Campo "aprova e fecha as OS"): os cartões são por
região de campo (com a alternância para gestor de contrato) e QUEM APROVA é o Supervisor de Campo da região da usina; com
a vaga aberta, o Coordenador de Campo; sem os dois, só um administrador. O Gestor de contrato não aprova.

Fracttal FALSO do começo ao fim: nenhuma OS de verdade é aprovada, e o Concluir do OS Creator é trocado por um
gravador (o portão é provado até a porta do clone, com o caminho, o método e o cookie que ele levaria)."""
import base64
import json
import re
import shutil
import subprocess
import time
from datetime import datetime, timedelta, timezone

import pytest
from pg_falso import ApiPGFalsa
from test_campo_aprovacao import FracttalFalso
from test_campo_regras_app import TabelaFalsa
from test_campo_visao import CHAVE_CADASTRO, EQUIPES, REGIOES, _aba, _pessoas

from nexus.campo import aprovacao, fracttal, leitura, regras_app, tabelas, visao
from nexus.torres.campo import aprovar_os

BRT = timezone(timedelta(hours=-3))
CRIADA_15088 = "2026-09-01T01:30:00.123+00:00"      # 31/08 às 22:30 em Brasília: a data certa é 31/08
SUPERVISORA = {"pessoa_id": 92, "nome": "Supervisora Campo", "papel": "supervisor_campo", "regioes": ["Sudeste 03"]}
COORDENADOR = {"pessoa_id": 93, "nome": "Coordenador Campo", "papel": "coordenador", "regioes": ["Sudeste 03", "Sul 01"]}


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


def _tabela(html):
    """As linhas da tabela do cartão aberto: [[célula, ...], ...] em texto, sem as linhas de detalhe."""
    corpo = html.split('<table class="cn-expande cn-tab-aprov">')[1].split("</table>")[0]
    linhas = re.findall(r'<tr class="cn-linha".*?</tr>', corpo, re.S)
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
    assert "Sudeste 03" in html and "fila lida em" in html
    assert len(chamadas) == feitas and len(fila.pedidos) == pedidos     # nada refeito, nada pedido ao Fracttal


# ── 2. o cartão da região de campo abre a tabela das OS dela ────────────────────────────────────────────────────
def test_cartao_da_regiao_abre_a_tabela_com_as_colunas_pedidas(fila, logado):
    html = logado.get("/t/campo/aprovacao").get_data(as_text=True)
    assert "<h2>Por região de campo</h2>" in html
    assert 'href="?ver=Sudeste+03"' in html and 'href="?ver=Sul+01"' in html
    # o cartão diz quem aprova ali: a supervisora de campo na Sudeste 03; o coordenador na Sul 01, de vaga aberta
    assert "Quem aprova é o supervisor de campo da região Sudeste 03 (Supervisora Campo) ou um administrador." in html
    assert ("Vaga aberta de supervisor de campo na região Sul 01: aprova o coordenador de campo (Coordenador Campo) ou "
            "um administrador.") in html
    html = logado.get("/t/campo/aprovacao?ver=Sudeste+03").get_data(as_text=True)
    cab = re.findall(r"<th[^>]*>([^<]+)</th>", html.split('<table class="cn-expande cn-tab-aprov">')[1].split("</thead>")[0])
    assert cab == ["OS", "Dia", "Data da criação da OS", "Data fim", "Supervisor de campo", "Prontas", "Pedem olho",
                   "Fora do App", "Uso do App", "Nota média", "Devolvidas"]
    linhas = {l[0]: l for l in _tabela(html)}
    assert list(linhas) == ["15002", "15088", "15102"]                          # a mais antiga primeiro
    fim = (datetime.utcnow() - timedelta(days=8)).replace(tzinfo=timezone.utc).astimezone(BRT).strftime("%d/%m/%y")
    # OS, Dia, criação (em Brasília: 01:30 UTC de 01/09 é 31/08), fim, supervisor de campo, prontas, olho, fora, uso,
    # nota, devolvidas
    assert linhas["15088"] == ["15088", "8 d", "31/08/26", fim, "Supervisora Campo", "0", "2", "0", "100%", "71%", "2"]
    assert linhas["15102"][5:] == ["1", "0", "0", "100%", "96%", "—"]
    assert linhas["15002"][1] == "120 d" and linhas["15002"][5:] == ["0", "0", "1", "0%", "—", "—"]
    assert "16001" not in linhas                                                 # é da Sul 01
    # a linha continua abrindo o porquê do grupo
    assert 'class="cn-detalhe" hidden' in html and "Nota do registro 71%" in html and "Já foi devolvida" in html
    # na Sul 01, a coluna diz que a vaga está aberta
    sul = logado.get("/t/campo/aprovacao?ver=Sul+01").get_data(as_text=True)
    assert _tabela(sul)[0][4] == "vaga" and 'class="cn-vaga">vaga</span>' in sul


def test_alternancia_por_gestor_de_contrato(fila, logado):
    html = logado.get("/t/campo/aprovacao?por=gestor").get_data(as_text=True)
    assert "<h2>Por gestor de contrato</h2>" in html and 'href="?por=gestor&amp;ver=Beltrano+Supervisor"' in html
    assert "Gestor de contrato (Supervisor PM): não aprova OS" in html
    tabela = logado.get("/t/campo/aprovacao?por=gestor&ver=Beltrano+Supervisor").get_data(as_text=True)
    assert [l[0] for l in _tabela(tabela)] == ["15002", "15088", "15102"]
    # o filtro de gestor e o de região de campo, na barra
    assert 'name="regiao_campo"' in html and 'name="gestor"' in html and 'name="supervisor"' not in html
    so_sc = logado.get("/t/campo/aprovacao?gestor=Ciclano+Chefe").get_data(as_text=True)
    assert 'href="?gestor=Ciclano+Chefe&amp;ver=Sul+01"' in so_sc and "ver=Sudeste+03" not in so_sc


def test_paradas_ha_30_dias_ou_mais_mostra_todas_as_que_conta(fila, logado):
    """O cartão "Paradas há 30 dias ou mais" conta as OS com 30 dias ou mais, e o clique tem de mostrar as MESMAS. Ele
    levava a "31 a 60 dias": com a fila inteira (08/10), a 15002, parada há 120 dias, contava no cartão e sumia no clique."""
    html = logado.get("/t/campo/aprovacao").get_data(as_text=True)
    assert 'href="?idade=30-"' in html and 'href="?idade=31-60"><span class="gc-rotulo">Paradas' not in html
    html = logado.get("/t/campo/aprovacao?ver=Sudeste+03&idade=30-").get_data(as_text=True)
    assert [l[0] for l in _tabela(html)] == ["15002"] and "esperando há 30 dias ou mais" in html
    assert 'href="?ver=Sudeste+03" aria-current="true"><span class="gc-rotulo">Paradas' in html   # ativo
    # a barra de idade continua com as cinco faixas (a de "30 dias ou mais" é só do cartão)
    assert "?idade=30-" not in html.split('class="cn-idades-barra"')[1].split("</div>")[0]


def test_por_tecnico_e_fila_sairam(fila, logado):
    """Levi, 08/10: "a visão de por técnico e fila pode matar, pode tirar que é irrelevante!"."""
    html = logado.get("/t/campo/aprovacao").get_data(as_text=True)
    assert "Por técnico" not in html and "Fila de verificação</h2>" not in html and "vista=" not in html
    html = logado.get("/t/campo/aprovacao?vista=tecnicos").get_data(as_text=True)    # endereço antigo: os cartões
    assert 'class="cn-equipes"' in html and "<th>Técnico</th>" not in html


def test_csv_tem_as_colunas_da_tabela(fila, logado):
    r = logado.get("/t/campo/aprovacao?ver=Sudeste+03&csv=1")
    texto = r.get_data(as_text=True)
    assert r.mimetype == "text/csv" and "aprovacao-os.csv" in r.headers["Content-Disposition"]
    assert texto.splitlines()[0].lstrip("﻿").startswith(
        "OS;Dias esperando;Criação da OS;Data fim;Região de campo;Supervisor de campo;Gestor de contrato")
    assert "15088;8;31/08/26;" in texto and "16001" not in texto
    assert ";Sudeste 03;Supervisora Campo;Beltrano Supervisor;" in texto
    assert texto.splitlines()[1].endswith("Quem aprova é o supervisor de campo da região Sudeste 03 (Supervisora Campo) "
                                          "ou um administrador.")


# ── 4. quem aprova: o supervisor de campo da região; com a vaga aberta, o coordenador; senão, admin ──────────────
def _jwt(email):
    corpo = base64.urlsafe_b64encode(json.dumps({"email": email, "exp": time.time() + 3600}).encode())
    return "x." + corpo.decode().rstrip("=") + ".y"


def _fracttal_de(app, cliente, email, nome):
    """O cookie do OS Creator, como o login do Fracttal grava (o portão lê quem entrou por ele)."""
    from nexus.torres.oscreator import ponte
    clone = ponte.clone(app)
    valor = clone.session_interface.get_signing_serializer(clone).dumps(
        {"jwt": _jwt(email), "conta": {"email": email, "nome": nome}})
    cliente.set_cookie("os_sessao", valor, path="/os")


def _sessao_nexus(cliente, papel=None, admin=False):
    """Quem entrou no Nexus pelo Fracttal (não admin), com o papel que o login grava (`supervisor_padrao`)."""
    with cliente.session_transaction() as s:
        s.clear()
        s.update(logado=True, admin=admin, usuario={"email": "x@exemplo.test", "nome": "X", "perfil": "Supervisor"})
        if papel:
            s["supervisor_padrao"] = papel


@pytest.fixture
def concluir(monkeypatch):
    """O Concluir do OS Creator trocado por um gravador: guarda o pedido que chegaria ao clone e responde como ele."""
    pedidos = []

    def clone_falso(environ, start_response):
        pedidos.append({"caminho": environ["PATH_INFO"], "metodo": environ["REQUEST_METHOD"],
                        "corpo": json.loads(environ["wsgi.input"].read(int(environ.get("CONTENT_LENGTH") or 0)) or b"{}"),
                        "cookie": environ.get("HTTP_COOKIE", "")})
        start_response("200 OK", [("Content-Type", "application/json")])
        return [json.dumps({"ok": True, "mensagem": "OS concluída."}).encode()]
    monkeypatch.setattr(aprovar_os, "_clone", lambda: clone_falso)
    return pedidos


def _ler_fila(cliente):
    cliente.get("/t/campo/aprovacao?regiao_campo=*")      # nos testes a releitura roda na hora


def test_supervisor_de_campo_aprova_a_os_da_regiao_dele(app, fila, cliente, concluir):
    _sessao_nexus(cliente, papel=SUPERVISORA)
    _ler_fila(cliente)
    # na tela: entra filtrada na região dela; o botão na OS da Sudeste 03, apagado na da Sul 01 com quem aprova lá
    html = cliente.get("/t/campo/aprovacao").get_data(as_text=True)
    assert '<option value="Sudeste 03" selected>' in html and 'href="?ver=Sul+01"' not in html
    html = cliente.get("/t/campo/aprovacao?ver=Sudeste+03").get_data(as_text=True)
    assert 'data-wo="15088" data-os="15088"' in html and "/os/_nexus/aprovacao/" in html
    outro = cliente.get("/t/campo/aprovacao?ver=Sul+01&regiao_campo=*").get_data(as_text=True)
    assert 'data-wo="16001" data-os' not in outro
    assert "Vaga aberta de supervisor de campo na região Sul 01: aprova o coordenador de campo (Coordenador Campo)" in outro
    # no servidor: quem entrou no Fracttal é a supervisora (pelo e-mail da ficha), e a 15088 é da região dela
    _fracttal_de(app, cliente, "supervisora@exemplo.test", "Supervisora C.")
    r = cliente.post("/os/_nexus/aprovacao/15088/aprovar", json={"folio": "99999"})
    assert r.status_code == 200 and r.get_json()["ok"] and r.get_json()["tarefas_tiradas"] == 2
    assert concluir == [{"caminho": "/os/api/os/15088/concluir", "metodo": "POST", "corpo": {"folio": "15088"},
                         "cookie": concluir[0]["cookie"]}]
    assert "os_sessao=" in concluir[0]["cookie"]                  # o login do Fracttal de quem clicou vai junto
    assert aprovacao.os_na_fila(15088) is None                    # saiu da fila guardada na hora
    # e a da Sul 01 (vaga aberta: é do coordenador) ela não aprova
    r = cliente.post("/os/_nexus/aprovacao/16001/aprovar", json={})
    assert r.status_code == 403 and "aprova o coordenador de campo (Coordenador Campo)" in r.get_json()["erro"]


def test_coordenador_aprova_so_onde_a_vaga_esta_aberta(app, fila, cliente, concluir):
    _sessao_nexus(cliente, papel=COORDENADOR)
    _ler_fila(cliente)
    html = cliente.get("/t/campo/aprovacao?ver=Sul+01").get_data(as_text=True)
    assert 'data-wo="16001" data-os="16001"' in html                                    # vaga aberta: é dele
    html = cliente.get("/t/campo/aprovacao?ver=Sudeste+03").get_data(as_text=True)
    assert 'data-wo="15088" data-os' not in html                                       # a região tem supervisora
    _fracttal_de(app, cliente, "coordenador@exemplo.test", "Coordenador C.")
    assert cliente.post("/os/_nexus/aprovacao/16001/aprovar", json={}).status_code == 200
    r = cliente.post("/os/_nexus/aprovacao/15088/aprovar", json={})
    assert r.status_code == 403 and r.get_json()["erro"] == (
        "Quem aprova é o supervisor de campo da região Sudeste 03 (Supervisora Campo) ou um administrador.")
    assert [p["caminho"] for p in concluir] == ["/os/api/os/16001/concluir"]


def test_gestor_de_contrato_e_quem_nao_tem_papel_levam_403_mesmo_forjando(app, fila, cliente, concluir):
    # o gestor de contrato (o "supervisor" de antes) não aprova: o PDF põe a aprovação no Supervisor de Campo
    _sessao_nexus(cliente, papel={"pessoa_id": 90, "nome": "Beltrano Supervisor", "papel": "gestor",
                                  "gestor": "Beltrano Supervisor"})
    _ler_fila(cliente)
    assert 'data-wo="15088" data-os' not in cliente.get("/t/campo/aprovacao?ver=Sudeste+03").get_data(as_text=True)
    _fracttal_de(app, cliente, "beltrano@exemplo.test", "Beltrano S.")
    r = cliente.post("/os/_nexus/aprovacao/15088/aprovar", json={})
    assert r.status_code == 403 and "supervisor de campo da região Sudeste 03" in r.get_json()["erro"]
    assert concluir == [] and aprovacao.os_na_fila(15088)        # nada foi ao clone; a OS segue na fila
    # o mesmo login do Fracttal, com a sessão do Nexus dizendo "supervisora": vale quem entrou no Fracttal
    _sessao_nexus(cliente, papel=SUPERVISORA)
    assert cliente.post("/os/_nexus/aprovacao/15088/aprovar", json={}).status_code == 403
    # técnico (sem papel nenhum): 403
    _fracttal_de(app, cliente, "tecnico@exemplo.test", "Fulano de Tal")
    assert cliente.post("/os/_nexus/aprovacao/16001/aprovar", json={}).status_code == 403
    assert concluir == []


def test_regiao_sem_supervisor_e_sem_coordenador_so_admin_aprova(app, fila, cliente, logado, concluir):
    sem_ninguem = [dict(REGIOES[0]), dict(REGIOES[1], coordenador_campo_id=None, coordenador_campo_vaga="sim")]
    _aba(fila.api, "cadastro_nexus", "regioes_campo", sem_ninguem)
    visao.limpar()
    _ler_fila(logado)
    html = logado.get("/t/campo/aprovacao").get_data(as_text=True)          # o cartão da região diz quem aprova
    assert ("Só um administrador aprova: a região Sul 01 está sem supervisor e sem coordenador de campo no cadastro "
            "(as duas vagas abertas).") in html
    assert 'data-wo="16001" data-os="16001"' in logado.get("/t/campo/aprovacao?ver=Sul+01").get_data(as_text=True)
    # (o `logado` e o `cliente` são o mesmo navegador: a sessão é trocada aqui)
    _sessao_nexus(cliente, papel=COORDENADOR)
    _fracttal_de(app, cliente, "coordenador@exemplo.test", "Coordenador C.")
    r = cliente.post("/os/_nexus/aprovacao/16001/aprovar", json={})
    assert r.status_code == 403 and r.get_json()["erro"].startswith("Só um administrador aprova: a região Sul 01")
    _sessao_nexus(cliente, admin=True)
    _fracttal_de(app, cliente, "tecnico@exemplo.test", "Fulano de Tal")
    assert cliente.post("/os/_nexus/aprovacao/16001/aprovar", json={}).status_code == 200      # o admin aprova


def test_estrutura_nao_publicada_so_admin_aprova(app, fila, cliente, concluir):
    """Sem a aba `regioes_campo` no banco (antes da 1ª publicação), ninguém é supervisor de campo de nada: só um
    administrador aprova, e a tela e o portão dizem por quê."""
    _aba(fila.api, "cadastro_nexus", "regioes_campo", [])
    visao.limpar()
    _sessao_nexus(cliente, papel=SUPERVISORA)
    _ler_fila(cliente)
    html = cliente.get("/t/campo/aprovacao?ver=Sem+regi%C3%A3o+de+campo&regiao_campo=*").get_data(as_text=True)
    assert "Estrutura de campo ainda não publicada" in html and 'data-wo="15088" data-os' not in html
    _fracttal_de(app, cliente, "supervisora@exemplo.test", "Supervisora C.")
    r = cliente.post("/os/_nexus/aprovacao/15088/aprovar", json={})
    assert r.status_code == 403 and "a estrutura de campo (regiões e supervisores de campo) ainda não foi publicada" in r.get_json()["erro"]


def test_administrador_aprova_qualquer_os(app, fila, logado, cliente, concluir):
    # logado = senha de admin do Nexus; o login do Fracttal pode ser de quem não tem papel nenhum
    _ler_fila(logado)
    html = logado.get("/t/campo/aprovacao?ver=Sul+01").get_data(as_text=True)
    assert 'data-wo="16001" data-os="16001"' in html
    _fracttal_de(app, logado, "tecnico@exemplo.test", "Fulano de Tal")
    assert logado.post("/os/_nexus/aprovacao/16001/aprovar", json={}).status_code == 200
    assert [p["caminho"] for p in concluir] == ["/os/api/os/16001/concluir"]


def test_email_do_fracttal_em_nexus_admins_aprova(app, fila, cliente, concluir):
    app.config["NEXUS_ADMINS"] = "chefe@exemplo.test"
    _sessao_nexus(cliente)
    _ler_fila(cliente)
    _fracttal_de(app, cliente, "chefe@exemplo.test", "Chefe")
    assert cliente.post("/os/_nexus/aprovacao/16001/aprovar", json={}).status_code == 200


def test_portao_sem_login_fora_da_fila_e_de_outro_site(app, fila, logado, concluir):
    _ler_fila(logado)
    r = logado.post("/os/_nexus/aprovacao/15088/aprovar", json={})
    assert r.status_code == 401 and r.get_json()["login"] is True               # sem login do Fracttal
    _fracttal_de(app, logado, "supervisora@exemplo.test", "Supervisora C.")
    assert logado.post("/os/_nexus/aprovacao/77777/aprovar", json={}).status_code == 404   # não está na fila
    r = logado.post("/os/_nexus/aprovacao/15088/aprovar", json={}, headers={"Origin": "https://fora.test"})
    assert r.status_code == 403
    assert concluir == []


def test_clone_recusou_a_os_fica_na_fila(app, fila, logado, monkeypatch):
    def clone_recusa(environ, start_response):
        start_response("400 BAD REQUEST", [("Content-Type", "application/json")])
        return [json.dumps({"erro": "Não foi possível concluir."}).encode()]
    monkeypatch.setattr(aprovar_os, "_clone", lambda: clone_recusa)
    _ler_fila(logado)
    _fracttal_de(app, logado, "supervisora@exemplo.test", "Supervisora C.")
    r = logado.post("/os/_nexus/aprovacao/15088/aprovar", json={})
    assert r.status_code == 400 and "Não foi possível" in r.get_json()["erro"] and aprovacao.os_na_fila(15088)


def test_sessao_antiga_com_o_nome_do_supervisor_nao_vale_como_papel(app, fila, cliente):
    """Quem entrou antes da estrutura de 10/2026 tem no `supervisor_padrao` o nome do supervisor (texto): a tela não
    quebra e não filtra nem mostra o Aprovar por ele."""
    _sessao_nexus(cliente, papel="Beltrano Supervisor")
    _ler_fila(cliente)
    html = cliente.get("/t/campo/aprovacao?ver=Sudeste+03").get_data(as_text=True)
    assert 'data-wo="15088" data-os' not in html and 'href="?ver=Sul+01"' not in html
    assert cliente.get("/t/campo/rondas").status_code == 200


@pytest.mark.skipif(not shutil.which("node"), reason="sem node nesta máquina")
def test_o_script_da_tela_e_javascript_valido(fila, logado, tmp_path):
    """Até 08/10 o confirm() do Aprovar tinha uma quebra de linha DENTRO da string: o script inteiro não rodava (nem a
    linha abria, nem o Aprovar funcionava)."""
    _ler_fila(logado)
    html = logado.get("/t/campo/aprovacao?ver=Sudeste+03").get_data(as_text=True)
    scripts = [s for s in re.findall(r"<script>(.*?)</script>", html, re.S) if "cn-aprovar" in s]
    assert scripts
    arq = tmp_path / "aprovacao.js"
    arq.write_text(scripts[0], encoding="utf-8")
    r = subprocess.run(["node", "--check", str(arq)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

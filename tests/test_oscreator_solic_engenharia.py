"""A Nova solicitação para a ENGENHARIA no OS Creator Web do Nexus (Levi, 06/10/2026): "Em 'Nova Solicitação' aparecerá
duas opções, PCM e Engenharia. PCM realmente criará uma solicitação. Para engenharia terá uma tela nova, estilo
Performance > Geração e ETM > ETM ... porém liberada para todos os ativos".

Regras em `os_web/solic_eng_web.py` (do clone) e a tela inteira pelo app do clone, com o api trocado por dublês — nenhum
teste aqui faz rede. Nomes, códigos e usinas são de mentira: o repositório é público."""
import datetime as dt
import re
import sys

import pytest

from nexus.torres.oscreator import ponte

pytest.importorskip("PyQt6")          # o clone importa o steps/ui.py do OS Creator ao montar a tela de Engenharia
if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
from os_web import criar_app, solic_eng_web as reg  # noqa: E402

JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira
USINA = "Cliente X - Usina Teste 1 - UF"
CATALOGO = [
    {"id": 1, "code": "TST-NBRK1", "label": "TST-NBRK1 — Nobreak", "description": "Nobreak 1      { TST-NBRK1 }",
     "tipo": "NBRK", "usina": USINA, "cliente": "Cliente X"},
    {"id": 2, "code": "TST-INV11", "label": "Inversor 1.1", "description": "Inversor 1.1 Marca Teste", "tipo": "Inversor",
     "usina": USINA, "cliente": "Cliente X"},
    {"id": 3, "code": "TST-RELE1", "label": "TST-RELE1 — Relé da Cabine", "description": "Relé da Cabine 1",
     "tipo": "RELE", "usina": USINA, "cliente": "Cliente X"},
    {"id": 4, "code": "OUT-INV99", "label": "Inversor 9.9", "description": "Inversor 9.9", "tipo": "Inversor",
     "usina": "Cliente Y - Outra Usina - UF", "cliente": "Cliente Y"},
]
PESSOAS = [{"code": "A1", "name": "Ana Teste Silva", "id_personnel": 501}, {"code": "B2", "name": "Bruno Souza", "id_personnel": 502},
           {"code": "B3", "name": "Brunoso Lima", "id_personnel": 503}, {"code": "C4", "name": "Carla Dias", "id_personnel": 504},
           {"code": "S0", "name": "Ana Teste Semid", "id_personnel": None}]
CFG = "Ana Teste;Bruno;Zeca"
AGORA = dt.datetime(2026, 10, 6, 10, 0, tzinfo=reg.BRT)
ETIQ = [{"id": 1, "description": "PERFORMANCE"}, {"id": 900, "description": "ENGENHARIA"}, {"id": 901, "description": "Remoto"},
        {"id": 902, "description": "Religamento Remoto"}, {"id": 2603, "description": "Dar prioridade"}]


# ── regras ─────────────────────────────────────────────────────────────────────────────────────────────
def test_tipo_de_ativo_com_o_nome_no_lugar_da_sigla():
    assert reg.rotulo_tipo("NBRK") == "Nobreak" and reg.rotulo_tipo("DINV") == "Disjuntor do Inversor"
    assert reg.rotulo_tipo("Inversor") == "Inversor" and reg.rotulo_tipo("NCU") == "NCU"     # sem nome no cadastro: como veio
    ativos = reg.ativos_da_usina(CATALOGO, USINA)
    assert reg.tipos_de(ativos) == [("Inversor", "Inversor"), ("NBRK", "Nobreak"), ("RELE", "Relé da Cabine")]


def test_todos_os_ativos_da_usina_de_qualquer_tipo():
    ativos = reg.ativos_da_usina(CATALOGO, USINA, api._asset_short_name)
    assert [a["code"] for a in ativos] == ["TST-INV11", "TST-NBRK1", "TST-RELE1"]           # pelo nome do tipo
    assert [a["curto"] for a in ativos] == ["Inversor 1.1", "Nobreak 1", "Relé da Cabine 1"]       # o mesmo do título


def test_responsavel_so_entre_os_nomes_da_engenharia():
    pessoas, faltam = reg.responsaveis(PESSOAS, reg.nomes_configurados(CFG))
    # "Bruno" não casa com "Brunoso"; quem não tem id_personnel não recebe OS; "Zeca" não está no Fracttal
    assert [p["name"] for p in pessoas] == ["Ana Teste Silva", "Bruno Souza"] and faltam == ["Zeca"]
    assert reg.nomes_configurados("") == [] and reg.nomes_configurados(" A ; B,C ") == ["A", "B", "C"]


def test_etiquetas_so_remoto_e_engenharia_pelo_nome_exato():
    """Levi, 06/10/2026: "Etiqueta de remoto e engenharia fixas sempre! só essas etiquetas viu, sem performance"."""
    assert reg.ETIQUETAS == ("Remoto", "ENGENHARIA")
    assert reg.etiquetas(ETIQ) == ([901, 900], [])
    # sem a "Remoto" no catálogo, a "Religamento Remoto" NÃO serve no lugar: a falta é dita, e nada é criado
    assert reg.etiquetas([e for e in ETIQ if e["id"] != 901]) == ([900], ["Remoto"])
    assert (reg.TIPO_TAREFA, reg.CLASSIF_1) == ("Administrativa", "Programada")


def test_data_programada_7_dias_e_urgente_2():
    assert reg.data_padrao(AGORA, False) == AGORA + dt.timedelta(days=7)
    assert reg.data_padrao(AGORA, True) == AGORA + dt.timedelta(days=2)


def _corpo(**muda):
    c = {"ativos": [1, 3], "descricao": "  Avaliar   o religamento ", "problema": "Desarma toda manhã.",
         "responsavel": {"id_personnel": 501}, "urgente": False}
    c.update(muda)
    return c


def test_o_pedido_e_conferido_no_servidor():
    por_id = {str(a["id"]): a for a in CATALOGO}
    ok, _ = reg.responsaveis(PESSOAS, reg.nomes_configurados(CFG))
    erros = [reg.montar(_corpo(**m), por_id, ok, AGORA, api.perf_os_nome)[2]
             for m in ({"ativos": []}, {"ativos": [77]}, {"descricao": " "}, {"problema": ""}, {"responsavel": {"id_personnel": 504}})]
    assert erros == ["Marque ao menos um ativo.", "Um dos ativos marcados não está no catálogo — recarregue a página.",
                     "Escreva a atividade a ser realizada (o nome da OS).", "Descreva o problema.",
                     "Escolha o responsável entre os nomes da Engenharia."]
    ativos, c, erro = reg.montar(_corpo(), por_id, ok, AGORA, api.perf_os_nome)
    assert erro == "" and [a["code"] for a in ativos] == ["TST-NBRK1", "TST-RELE1"]
    assert c["por_ativo"] == {"TST-NBRK1": {"description": "[Nobreak 1] - Avaliar o religamento"},
                              "TST-RELE1": {"description": "[Relé da Cabine 1] - Avaliar o religamento"}}
    assert (c["note"], c["id_responsible"], c["responsible_name"]) == ("Desarma toda manhã.", 501, "Ana Teste Silva")
    assert c["prog_date"] == dt.datetime(2026, 10, 13, 10, 0, tzinfo=reg.BRT) and c["event_date"] == AGORA


def test_data_do_evento_e_da_tela_e_a_programada_conta_da_criacao():
    """Levi, 06/10/2026: "você sumiu com data do evento, tem que ter data do evento" — como na ETM: editável, padrão
    agora. A programada continua contando da CRIAÇÃO, não do evento."""
    por_id = {str(a["id"]): a for a in CATALOGO}
    ok, _ = reg.responsaveis(PESSOAS, reg.nomes_configurados(CFG))
    _, c, erro = reg.montar(_corpo(evento="2026-10-05T14:30"), por_id, ok, AGORA, api.perf_os_nome)
    assert erro == "" and c["event_date"] == dt.datetime(2026, 10, 5, 14, 30, tzinfo=reg.BRT)
    assert c["prog_date"] == AGORA + dt.timedelta(days=7)
    assert reg.montar(_corpo(evento=""), por_id, ok, AGORA, api.perf_os_nome)[1]["event_date"] == AGORA
    erros = [reg.montar(_corpo(evento=e), por_id, ok, AGORA, api.perf_os_nome)[2] for e in ("ontem", "2026-10-08T10:00")]
    assert erros == ["Data do evento inválida.", "A data do evento não pode estar no futuro."]


def test_a_data_programada_nao_se_edita_o_servidor_calcula():
    """Levi, 06/10/2026: "data programada não deve ser possível editar!". A data que vier no pedido é ignorada, mesmo
    mal escrita ou fora do prazo: vale a hora da criação + 7 dias (Urgente: + 2)."""
    por_id = {str(a["id"]): a for a in CATALOGO}
    ok, _ = reg.responsaveis(PESSOAS, reg.nomes_configurados(CFG))
    for urgente, dias in ((False, 7), (True, 2)):
        for mandada in ("2030-01-01T08:00", "2026-10-01T08:00", "ontem"):
            _, c, erro = reg.montar(_corpo(urgente=urgente, programada=mandada), por_id, ok, AGORA, api.perf_os_nome)
            assert erro == "" and c["prog_date"] == AGORA + dt.timedelta(days=dias), (urgente, mandada)
            assert c["urgente"] is urgente


# ── a tela, pelo app do clone ──────────────────────────────────────────────────────────────────────────
@pytest.fixture
def cli(monkeypatch):
    feito = {}
    monkeypatch.setenv(reg.ENV_RESPONSAVEIS, CFG)
    monkeypatch.setattr(api, "load_assets_cached", lambda *a, **k: [dict(x) for x in CATALOGO])
    monkeypatch.setattr(api, "get_responsaveis", lambda *a, **k: [dict(p) for p in PESSOAS])
    monkeypatch.setattr(api, "get_request_types", lambda *a, **k: {})             # a tela do PCM, sem rede
    monkeypatch.setattr(api, "get_labels", lambda: [dict(e) for e in ETIQ])

    def classif(c1, c2):          # como o de verdade: nome vazio não acha nada
        out = {"id_task_type": 11, "tasks_types_description": c1} if c1 else {}
        out.update({"id_task_type_2": 22, "tasks_types_2_description": c2} if c2 else {})
        return out
    monkeypatch.setattr(api, "_classif_ids", classif)

    def criar(assets, description, task_type, subtasks, **kw):
        feito.update(assets=assets, description=description, task_type=task_type, subtasks=subtasks, **kw)
        return [{"code": a["code"], "ok": True, "os": {"wo_folio": 15000 + i}} for i, a in enumerate(assets)]
    monkeypatch.setattr(api, "create_work_orders_bulk", criar)
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Pessoa Teste", "email": "teste@exemplo.invalid", "perfil": "ADMINISTRATOR"}
    c.feito = feito
    return c


def test_a_nova_solicitacao_tem_as_duas_portas(cli):
    pcm = cli.get("/os/solicitacao").get_data(as_text=True)
    assert '<a class="os-seg-btn on" role="tab" aria-selected="true" href="/os/solicitacao">PCM</a>' in pcm
    assert 'href="/os/solicitacao/engenharia">Engenharia</a>' in pcm
    r = cli.get("/os/solicitacao/engenharia")
    assert r.status_code == 200
    h = r.get_data(as_text=True)
    assert '<a class="os-seg-btn on" role="tab" aria-selected="true" href="/os/solicitacao/engenharia">Engenharia</a>' in h
    for txt in ("Cliente <i>*</i>", "Usina <i>*</i>", "Filtrar <small>", "Tipo de ativo <small>", 'id="cb_tipo" data-busca="1"',
                "Atividade a ser realizada (de forma direta)", "Descreva o problema <i>*</i>", 'id="ck_urg"', "Urgente"):
        assert txt in h, txt
    # a data do EVENTO se edita (padrão: agora); a PROGRAMADA só se vê (7 dias; o Urgente troca para 2)
    assert "Responsável e datas" in h and "Data do evento" in h
    evento = re.search(r'<input id="dt_evento" type="datetime-local" value="([^"]+)"', h).group(1)
    assert evento[:10] == dt.datetime.now(reg.BRT).strftime("%Y-%m-%d")
    assert "<input" not in re.search(r'id="dt_prog"[^>]*>', h).group(0) and h.count('type="datetime-local"') == 1
    mostrada = re.search(r'id="dt_prog"[^>]*>(\d{2}/\d{2}/\d{4} \d{2}:\d{2})<', h).group(1)
    agora = dt.datetime.now(reg.BRT)
    assert mostrada[:10] == (agora + dt.timedelta(days=7)).strftime("%d/%m/%Y")
    assert re.search(r'data-agora="%s' % agora.strftime("%Y-%m-%d"), h)


def test_ativos_e_responsaveis_da_tela(cli):
    j = cli.get("/os/api/solicitacao/engenharia/ativos", query_string={"usina": USINA}).get_json()
    assert [a["tipo_nome"] for a in j["ativos"]] == ["Inversor", "Nobreak", "Relé da Cabine"]
    assert {"tipo": "NBRK", "nome": "Nobreak"} in j["tipos"]
    r = cli.get("/os/api/solicitacao/engenharia/responsaveis").get_json()
    assert [p["name"] for p in r["pessoas"]] == ["Ana Teste Silva", "Bruno Souza"] and r["faltam"] == ["Zeca"]


def test_sem_a_lista_no_env_a_tela_avisa(cli, monkeypatch):
    monkeypatch.delenv(reg.ENV_RESPONSAVEIS)
    assert cli.get("/os/api/solicitacao/engenharia/responsaveis").get_json() == {"pessoas": [], "faltam": [], "configurado": False}
    r = cli.post("/os/api/solicitacao/engenharia/criar", json=_corpo())
    assert r.status_code == 400 and r.get_json()["erro"] == "Escolha o responsável entre os nomes da Engenharia."


def _perto(data, esperada):
    return abs(data - esperada) < dt.timedelta(minutes=2)


def test_criar_sai_como_a_os_de_analise_com_a_etiqueta_da_engenharia(cli):
    # a programada mandada pela tela não vale: o servidor programa para 7 dias depois da criação; o evento vem da tela
    ontem = (dt.datetime.now(reg.BRT) - dt.timedelta(days=1)).replace(second=0, microsecond=0)
    r = cli.post("/os/api/solicitacao/engenharia/criar",
                 json=_corpo(programada="2030-01-01T08:00", evento=ontem.strftime("%Y-%m-%dT%H:%M")))
    assert r.status_code == 200
    f = cli.feito
    assert _perto(f["prog_date"], dt.datetime.now(reg.BRT) + dt.timedelta(days=7)) and f["event_date"] == ontem
    assert r.get_json()["mensagem"] == ("2 OS criada(s) para a Engenharia — Nº 15000, 15001 — programada(s) para %s."
                                        % f["prog_date"].strftime("%d/%m/%Y %H:%M"))
    # tipo Administrativa, só a Classificação 1 (Programada) e só as etiquetas REMOTO + ENGENHARIA — sem PERFORMANCE
    assert (f["task_type"], f["subtasks"], f["etiqueta_ids"]) == ("Administrativa", [], [901, 900])
    assert f["tipo"] == {"id_c1": 11, "desc_c1": "Programada"}
    assert (f["id_responsible"], f["responsible_name"], f["note"]) == (501, "Ana Teste Silva", "Desarma toda manhã.")
    assert f["por_ativo"]["TST-NBRK1"] == {"description": "[Nobreak 1] - Avaliar o religamento"}


def test_urgente_so_muda_a_data_as_etiquetas_sao_as_mesmas(cli):
    r = cli.post("/os/api/solicitacao/engenharia/criar", json=_corpo(urgente=True, programada="2030-01-01T08:00"))
    assert r.status_code == 200
    assert _perto(cli.feito["prog_date"], dt.datetime.now(reg.BRT) + dt.timedelta(days=2))
    assert cli.feito["etiqueta_ids"] == [901, 900]                  # sem "Dar prioridade": só REMOTO e ENGENHARIA


def test_sem_a_etiqueta_no_fracttal_nenhuma_os_e_criada(cli, monkeypatch):
    monkeypatch.setattr(api, "get_labels", lambda: [dict(e) for e in ETIQ if e["id"] != 901])
    r = cli.post("/os/api/solicitacao/engenharia/criar", json=_corpo())
    assert r.status_code == 400
    assert r.get_json()["erro"] == "Não achei no Fracttal a etiqueta Remoto. Nenhuma OS foi criada."
    assert cli.feito == {}


def test_responsavel_de_fora_da_lista_e_recusado(cli):
    r = cli.post("/os/api/solicitacao/engenharia/criar", json=_corpo(responsavel={"id_personnel": 504}))
    assert r.status_code == 400 and "Engenharia" in r.get_json()["erro"]

"""Engenharia > Quadro da equipe: a OS da engenharia (Levi, 24/10/2026: "Ao clicar quero uma visão parecida com o que
aparece quando clica na OS da parte de CHAMADOS > GARANTIA"), com o status e a prioridade da engenharia, os comentários
na nota da OS, as OS filhas e o pulso das paradas. Desenho em docs/superpowers/specs/2026-10-24-engenharia-os-do-quadro-
design.md. Banco falso (tests/pg_falso.py) e Fracttal falso; os nomes são fictícios."""
import json
from urllib.parse import urlencode
import re
from datetime import datetime, timedelta, timezone

import pytest
from pg_falso import ApiPGFalsa
from test_engenharia_acompanhamento import ANA, BETO

from nexus.cadastro.cifra import gerar_chave
from nexus.dados import catalogo, explica
from nexus.engenharia import os_acompanhamento as O
from nexus.cadastro import setor_ids as SID

BRT = timezone(timedelta(hours=-3))
OS1 = {"wid": 39550452, "folio": "16502", "codigo": "IBI200-INVR1.3", "usina_id": 1,
       "usina_ligada_por": "de-para do Fracttal"}


@pytest.fixture
def banco(app):
    api = ApiPGFalsa()
    app.config.update(GRIDCO_DB_API="http://pg.falso", NEXUS_CHAVE_CADASTRO=gerar_chave(),
                      NEXUS_PESSOA_HMAC="hmac-teste", GRIDCO_SQL_TOKEN="tk")
    app.extensions["nexus_dados_sessao"] = api
    O.limpar()
    with app.app_context():
        yield api
    O.limpar()
    app.extensions.pop("nexus_dados_sessao", None)


def _est(wid=OS1["wid"]):
    return O.estado(O.ler(forcar=True)["eventos"]).get(str(wid)) or {}


# ── Task 1: o livro e as regras ─────────────────────────────────────────────────────────────────────────────────────
def test_catalogo_registra_o_livro_da_os():
    l = catalogo.LIVRO_POR_NOME[O.LIVRO]
    assert set(l.abas) == {O.ABA, O.ABA_STATUS, O.ABA_PRIORIDADE} and set(l.so_cresce) == set(l.abas)
    assert all(catalogo.aba_segue_a_regra(x) for x in l.abas)
    f = next(x for x in catalogo.FATOS if x.id == "acompanhamento_os")
    assert "1 linha = 1 evento" in f.grao and {"data", "usina", "equipamento", "pessoa"} <= set(f.dims)
    assert 15 <= len(explica.RESUMO["acompanhamento_os"]) <= 70
    assert len(explica.PARA_QUE["acompanhamento_os"]) >= 80 and explica.PARA_QUE["acompanhamento_os"].endswith(".")


def test_os_oito_status_e_as_tres_prioridades_do_pedido():
    assert [n for _i, n in O.STATUS] == ["Análise de Solução", "Atividade em Andamento", "Diagnóstico em Andamento",
                                         "Agendamento de OS", "Tratativa com Equipe de Campo", "Validação Final",
                                         "Stand-By", "Diagnóstico Concluído"]
    assert [n for _i, n in O.PRIORIDADES] == ["Média", "Alta", "Urgente"]


def test_status_e_prioridade_vao_ao_livro_e_o_estado_le_o_ultimo(banco):
    O.classificar(OS1, 3, 2, ANA, True)
    e = _est()
    assert (e["status_id"], e["prioridade_id"]) == (3, 2)
    O.classificar(OS1, 8, None, BETO, True)                 # só o status: a prioridade fica
    e = _est()
    assert (e["status_id"], e["prioridade_id"]) == (8, 2)
    assert [x["evento"] for x in e["eventos"]][:1] == ["status"] and e["eventos"][0]["nome"] == "Beto Souza"
    linhas = banco.linhas(O.LIVRO, O.ABA)
    assert len(linhas) == 3 and {str(x["os_id"]) for x in linhas} == {str(OS1["wid"])}
    assert [x["nome"] for x in banco.linhas(O.LIVRO, O.ABA_STATUS)][2] == "Diagnóstico em Andamento"
    assert [x["nome"] for x in banco.linhas(O.LIVRO, O.ABA_PRIORIDADE)] == ["Média", "Alta", "Urgente"]


def test_nada_mudou_e_quem_nao_e_da_engenharia_nao_classifica(banco):
    O.classificar(OS1, 1, 1, ANA, True)
    with pytest.raises(O.Recusada, match="Nada mudou"):
        O.classificar(OS1, 1, 1, ANA, True)
    with pytest.raises(O.Recusada, match="Engenharia"):
        O.classificar(OS1, 2, None, BETO, False)
    with pytest.raises(O.Recusada, match="status"):
        O.classificar(OS1, 9, None, ANA, True)                 # fora da lista


def test_comentario_cifrado_e_a_linha_da_nota(banco):
    quando = datetime(2026, 10, 24, 14, 32, tzinfo=BRT)
    assert O.linha_da_nota("Trocar o cabo", "Ana Lima", quando) == "[24/10/2026 14:32] Ana Lima (Engenharia): Trocar o cabo"
    O.registrar_comentario(OS1, "Trocar o cabo do MPPT 2", ANA, True, "sim")
    e = _est()
    c = e["eventos"][0]
    assert c["evento"] == "comentario" and c["texto"] == "Trocar o cabo do MPPT 2" and c["nota"] == "sim"
    cru = json.dumps(banco.linhas(O.LIVRO, O.ABA), ensure_ascii=False, default=str)
    assert "Trocar o cabo" not in cru and "Ana Lima" not in cru and "ana.lima" not in cru
    with pytest.raises(O.Recusada, match="Escreva"):
        O.registrar_comentario(OS1, "   ", ANA, True, "sim")


def test_ultima_atualizacao_e_parada():
    agora = datetime(2026, 10, 24, 12, 0, tzinfo=BRT)
    a, b = agora - timedelta(days=9), agora - timedelta(days=8)
    assert O.ultima_atualizacao([a, None, b]) == b and O.ultima_atualizacao([None]) is None
    assert O.parada("fazer", b, agora) and O.parada("verificacao", b, agora)
    assert not O.parada("fazer", agora - timedelta(days=6), agora)
    assert not O.parada("concluida", b, agora) and not O.parada("cancelada", b, agora)
    assert not O.parada("fazer", None, agora)                   # sem data não se chuta parada


# ── Task 2: a página da OS e o classificar ──────────────────────────────────────────────────────────────────────────
URL = "/t/engenharia/equipe/os/16502"


@pytest.fixture
def pagina(banco, app, monkeypatch):
    """A OS 16502 (a fazer) com duas filhas: a 16510 respondeu "Descreva a atividade realizada", a 16511 não tem a
    subtarefa. Quem entra é do setor Engenharia."""
    from test_engenharia_equipe import AGORA, _w

    from nexus.auth import setor_telas as ST
    from nexus.engenharia import os_equipe as E
    from nexus.torres import engenharia as torre
    mae = _w("16502", 1, note="Nota antiga da OS", personnel_description="Ana  Lima")
    f1 = _w("16510", 1, id_parent_wo=mae["id_work_order"], description="Troca do cabo")
    f2 = _w("16511", 3, task="DONE", fim=AGORA.isoformat(), id_parent_wo=mae["id_work_order"], description="Limpeza")
    subs = {"16510": [{"description": "Descreva a atividade realizada", "value": "Troquei o cabo do MPPT 2"},
                      {"description": "Registro fotográfico da atividade", "value": None}],
            "16511": [{"description": "Registro fotográfico da atividade", "value": None}]}

    def rest(path):
        valor = path.split("=", 1)[1].split("&", 1)[0]
        if path.startswith("work_orders?wo_folio="):
            return {"data": [w for w in (mae, f1, f2) if w["wo_folio"] == valor]}
        if path.startswith("work_orders?id_parent_wo="):
            return {"data": [w for w in (f1, f2) if str(w["id_parent_wo"]) == valor]}
        if path.startswith("work_orders_subtasks/?folio="):
            return {"data": subs.get(valor, [])}
        raise AssertionError(path)
    monkeypatch.setattr(E, "_ler_fracttal", rest)
    monkeypatch.setattr(torre, "_onde_do_cadastro",
                        lambda: (lambda texto, cod: {"usina_id": 7, "ligada_por": "de-para do Fracttal"}))
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": set(), "setor": {"id": SID.ENGENHARIA, "nome": "Engenharia"},
                                               "erro": ""})
    return mae


def _secao(html, titulo):
    marca = f">{titulo}</h2>"
    return html.split(marca, 1)[1].split("</section>", 1)[0] if marca in html else ""


def _acoes(html):
    """A caixa Ações da OS inteira: o `_secao` para no primeiro </section>, e o "!" do título dela tem uma (06/11/2026)."""
    return html.split("data-os-acoes-eng", 1)[1].split("</aside>", 1)[0] if "data-os-acoes-eng" in html else ""


def _kpis(html):
    """Os quatro números do topo, no desenho da faixa da tela do chamado (.kpis da Garantia)."""
    faixa = html.split('<div class="eg-ac-kpis"', 1)[1].split("</section>", 1)[0]
    return (re.findall(r'<div class="lbl">([^<]+)</div>', faixa),
            re.findall(r'<span class="val[^"]*">([^<]+)</span>', faixa))


def test_pagina_da_os_tem_os_quatro_numeros_e_os_blocos(pagina, cliente):
    from test_engenharia_acompanhamento import _como
    html = _como(cliente, ANA).get(URL).get_data(as_text=True)
    rotulos, valores = _kpis(html)
    assert rotulos == ["Status", "Prioridade", "Programada", "Última atualização"] and valores[:2] == ["—", "—"]
    for b in ("Status e prioridade", "Dados", "A cadeia da OS", "Na nota da OS", "Demais respostas do técnico",
              "Comentários"):
        assert _secao(html, b), b
    assert "Nota antiga da OS" in _secao(html, "Na nota da OS")
    assert "Solicitar OS" in html and "Abrir a OS" not in html
    assert "ativo%3DX-INV1.1" in html and f"os_pai%3D{pagina['id_work_order']}" in html and "os_pai_folio%3D16502" in html
    assert "16510" in _secao(html, "A cadeia da OS") and "16511" in _secao(html, "A cadeia da OS")
    assert _secao(html, "OS filhas") == ""


def test_os_dados_dizem_quem_criou_a_os(pagina, cliente):
    # Levi, 27/10/2026: "em quadro da equipe, ao clicar na OS em dados deve ter o "Criado por" e mostra quem criou essa
    # OS" (o `created_by` do Fracttal, com o espaço dobrado limpo)
    from test_engenharia_acompanhamento import _como
    pagina["created_by"] = "Pessoa  Três"
    dados = _secao(_como(cliente, ANA).get(URL).get_data(as_text=True), "Dados")
    assert "<dt>Criado por</dt><dd>Pessoa Três</dd>" in dados
    assert dados.index("Criado por") < dados.index("Criada em")
    pagina["created_by"] = ""
    dados = _secao(_como(cliente, ANA).get(URL).get_data(as_text=True), "Dados")
    assert "<dt>Criado por</dt><dd>—</dd>" in dados


def test_demais_respostas_vem_da_os_filha(pagina, cliente):
    from test_engenharia_acompanhamento import _como
    html = _secao(_como(cliente, ANA).get(URL).get_data(as_text=True), "Demais respostas do técnico")
    assert "Troquei o cabo do MPPT 2" in html and "16510" in html
    assert "16511" in html and "não tem a subtarefa" in html


def test_a_resposta_da_filha_concluida_fica_guardada_e_a_aberta_e_relida(pagina, cliente, monkeypatch):
    """Auditoria de 08/11/2026: cada abertura da pagina pedia ao Fracttal as subtarefas de CADA filha, em fila, da cota de
    200 por minuto que o App de Campo tambem usa. A filha concluida nao muda (a 16511); a aberta (16510) segue relida."""
    from test_engenharia_acompanhamento import _como

    from nexus.engenharia import os_equipe as E
    E._ATIVIDADES.clear()
    pedidos, rest = [], E._ler_fracttal

    def conta(path):
        if path.startswith("work_orders_subtasks/"):
            pedidos.append(path.split("folio=")[1].split("&")[0])
        return rest(path)
    monkeypatch.setattr(E, "_ler_fracttal", conta)
    for _ in range(2):
        html = _secao(_como(cliente, ANA).get(URL).get_data(as_text=True), "Demais respostas do técnico")
        assert "Troquei o cabo do MPPT 2" in html and "não tem a subtarefa" in html
    assert pedidos.count("16511") == 1 and pedidos.count("16510") == 2
    E._ATIVIDADES.clear()


def test_classificar_grava_e_volta_com_o_aviso(pagina, cliente):
    from test_engenharia_acompanhamento import SAME, _como
    r = _como(cliente, ANA).post(URL + "/classificar", data={"status_id": "3", "prioridade_id": "3"}, headers=SAME)
    assert r.status_code == 303 and r.headers["Location"].split("?", 1)[0].endswith(URL)
    html = cliente.get(r.headers["Location"]).get_data(as_text=True)
    _rot, valores = _kpis(html)
    assert valores[:2] == ["Diagnóstico em Andamento", "Urgente"] and '<span class="val pq r">Urgente<' in html
    assert "Status: Diagnóstico em Andamento" in _secao(html, "Comentários")       # a linha do tempo diz a mudança
    r = cliente.post(URL + "/classificar", data={"status_id": "3", "prioridade_id": "3"}, headers=SAME)
    assert "Nada+mudou" in r.headers["Location"] or "Nada%20mudou" in r.headers["Location"]


def test_quem_nao_e_da_engenharia_le_sem_formularios(pagina, cliente, monkeypatch):
    from test_engenharia_acompanhamento import _como

    from nexus.auth import setor_telas as ST
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": set(), "setor": {"id": SID.PERFORMANCE, "nome": "Performance"},
                                               "erro": ""})
    html = _como(cliente, BETO).get(URL).get_data(as_text=True)
    assert "Nota antiga da OS" in html and "/classificar" not in html and "<textarea" not in html


def test_classificar_de_outro_site_e_recusado(pagina, cliente):
    from test_engenharia_acompanhamento import _como
    r = _como(cliente, ANA).post(URL + "/classificar", data={"status_id": "3"}, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_os_que_nao_existe_diz_que_nao_achou(pagina, cliente):
    from test_engenharia_acompanhamento import _como
    r = _como(cliente, ANA).get("/t/engenharia/equipe/os/99999")
    assert r.status_code == 404 and "Não achei a OS 99999" in r.get_data(as_text=True)
    assert "Tentar novamente" not in r.get_data(as_text=True)                  # o nº errado não se resolve tentando de novo


@pytest.mark.parametrize("url", [URL, "/t/engenharia/etm/os/16502"])
def test_o_fracttal_que_recusa_deixa_o_botao_de_tentar_de_novo(pagina, cliente, monkeypatch, url):
    """Levi, 05/11/2026: "Deixa um botão para a pessoa tentar novamente". A recusa costuma ser a cota de 200 pedidos por
    minuto da empresa toda (às 23h30 de 04/11/2026 o App de Campo e esta página levaram 429 juntos): a página diz e dá o
    botão, um link para ela mesma (na tela de ETM, a de ETM)."""
    from test_engenharia_acompanhamento import _como

    from nexus.campo import fracttal
    from nexus.engenharia import os_equipe as E

    def recusa(path):
        raise fracttal.Recusado("o Fracttal recusou por excesso de pedidos (HTTP 429); a fila não foi lida")
    monkeypatch.setattr(E, "_ler_fracttal", recusa)
    r = _como(cliente, ANA).get(url)
    html = r.get_data(as_text=True)
    assert r.status_code == 502 and "O Fracttal não respondeu (Recusado)" in html
    assert f'<a class="eg-ac-btn eg-ac-btn--g" href="{url}">Tentar novamente</a>' in html


# ── Task 3: o comentário na nota da OS (pela ponte do OS Creator, na sessão do Fracttal da pessoa) ───────────────────
COMENTAR = "/os/_nexus/engenharia/os/{}/comentar"


def _login_do_fracttal(app, cliente):
    """O cookie do OS Creator como o login pelo Fracttal o deixa (JWT de mentira; nada vai ao Fracttal)."""
    from nexus.torres.oscreator import ponte
    clone = ponte.clone(app)
    jwt = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"
    valor = clone.session_interface.get_signing_serializer(clone).dumps(
        {"jwt": jwt, "conta": {"nome": "Pessoa Teste", "email": "teste@exemplo.invalid"}})
    cliente.set_cookie("os_sessao", valor, path="/os")


@pytest.fixture
def fracttal_do_os(app, pagina, monkeypatch):
    """O api do clone com a OS de uma tarefa e a nota antiga; o que seria escrito no Fracttal fica em `escritas`."""
    from nexus.torres.oscreator import ponte
    ponte.clone(app)
    import api as os_api
    det = {"notas": "Nota antiga da OS", "tarefas": [{"id": 1}], "cancel_motivo": "", "cancel_nota": ""}
    escritas, resposta = [], {"ok": True}
    monkeypatch.setattr(os_api, "get_os_detalhes", lambda wid: dict(det))

    def editar(wid, nota):
        escritas.append((wid, nota))
        return dict(resposta, nota=nota) if resposta.get("ok") else dict(resposta)
    monkeypatch.setattr(os_api, "editar_nota_os", editar)
    return {"det": det, "escritas": escritas, "resposta": resposta}


def test_comentario_vai_para_a_nota_com_data_e_hora(fracttal_do_os, pagina, cliente, app):
    from test_engenharia_acompanhamento import SAME, _como
    _como(cliente, ANA)
    _login_do_fracttal(app, cliente)
    r = cliente.post(COMENTAR.format(pagina["id_work_order"]), json={"texto": "Trocar o cabo", "folio": "16502"},
                     headers=SAME)
    assert r.status_code == 200 and r.get_json()["ok"] and "nota da OS 16502" in r.get_json()["mensagem"]
    (wid, nota), = fracttal_do_os["escritas"]
    assert wid == pagina["id_work_order"]
    assert re.fullmatch(r"Nota antiga da OS\n\[\d\d/\d\d/\d{4} \d\d:\d\d\] Ana Lima \(Engenharia\): Trocar o cabo", nota)
    c = _est(pagina["id_work_order"])["eventos"][0]
    assert c["evento"] == "comentario" and c["texto"] == "Trocar o cabo" and c["nota"] == "sim"


def test_sem_login_do_fracttal_pede_o_login_e_nao_grava(fracttal_do_os, pagina, cliente):
    # quem entrou pela conta Microsoft não tem a sessão do Fracttal no OS Creator (pelo Fracttal, o portão encerra o
    # Nexus junto com ela, e o caso nem chega aqui)
    import time

    from test_engenharia_acompanhamento import SAME
    with cliente.session_transaction() as s:
        s["logado"], s["admin"], s["usuario"] = True, False, ANA
        s["via"], s["ms_ate"] = "microsoft", time.time() + 3600
    r = cliente.post(COMENTAR.format(pagina["id_work_order"]), json={"texto": "x", "folio": "16502"}, headers=SAME)
    j = r.get_json()
    assert r.status_code == 401 and j["login"].startswith("/os/login?next=")
    assert "%2Ft%2Fengenharia%2Fequipe%2Fos%2F16502" in j["login"]        # o login do Fracttal volta para a página
    assert not fracttal_do_os["escritas"] and not _est(pagina["id_work_order"])


def test_os_de_varias_tarefas_tambem_vai_para_a_nota_da_os(fracttal_do_os, pagina, cliente, app):
    # Levi, 06/11/2026 (a OS 16289, de seis inversores): "o certo é comentar e já incluir na nota da OS". A prova no
    # Fracttal (OS 18754 de TESTE - PA, duas tarefas) mediu: o `work_orders_update` grava a `note` da OS, igual nas duas
    # tarefas, e a observação de cada tarefa (`task_note`) fica como estava. O comentário vai para a nota também aqui
    from test_engenharia_acompanhamento import SAME, _como
    fracttal_do_os["det"]["tarefas"] = [{"id": 1}, {"id": 2}]
    _como(cliente, ANA)
    _login_do_fracttal(app, cliente)
    r = cliente.post(COMENTAR.format(pagina["id_work_order"]), json={"texto": "Visto", "folio": "16502"}, headers=SAME)
    assert r.status_code == 200 and "nota da OS 16502" in r.get_json()["mensagem"]
    (wid, nota), = fracttal_do_os["escritas"]
    assert re.fullmatch(r"Nota antiga da OS\n\[\d\d/\d\d/\d{4} \d\d:\d\d\] Ana Lima \(Engenharia\): Visto", nota)
    c = _est(pagina["id_work_order"])["eventos"][0]
    assert c["texto"] == "Visto" and c["nota"] == "sim"


def test_os_concluida_continua_so_no_nexus(fracttal_do_os, pagina, cliente, app):
    # o Fracttal recusa editar a nota da OS fechada (ERROR_WO_FINISHED_BY_OTHER_USER): essa regra fica
    from test_engenharia_acompanhamento import SAME, _como
    fracttal_do_os["det"].update(tarefas=[{"id": 1}, {"id": 2}], status_id=3)
    _como(cliente, ANA)
    _login_do_fracttal(app, cliente)
    r = cliente.post(COMENTAR.format(pagina["id_work_order"]), json={"texto": "Visto", "folio": "16502"}, headers=SAME)
    assert r.status_code == 200 and "só no Nexus" in r.get_json()["mensagem"]
    assert not fracttal_do_os["escritas"]


# ── levar para a nota os comentários que ficaram só no Nexus (06/11/2026) ─────────────────────────────────────────
LEVAR = "/os/_nexus/engenharia/os/{}/levar-para-a-nota"
MOTIVO_VARIAS = ("Esta OS tem 6 tarefas, e cada uma tem a sua observação. A edição por aqui só é segura em OS de uma "
                 "tarefa — use o Fracttal.")


def _como_admin(cliente, monkeypatch):
    """O administrador é o da lista de Base → Acessos, relida a cada pedido (`auth._admin_em_dia`)."""
    from test_engenharia_acompanhamento import _como

    from nexus import auth
    monkeypatch.setattr(auth, "_admins", lambda: {ANA["email"]})
    return _como(cliente, ANA, admin=True)


def test_o_administrador_leva_para_a_nota_os_comentarios_que_ficaram_so_no_nexus(fracttal_do_os, pagina, cliente, app, monkeypatch):
    """Levi, 06/11/2026: "Sim, leva" (os comentários da OS 16289, de seis inversores, que ficaram só no Nexus antes de o
    comentário da OS de várias tarefas ir para a nota). Cada um vai com o autor e a hora dele, na ordem em que foi
    feito; no livro, um evento novo marca que foi (`comentario_na_nota`), sem mudar nem marcar como editado."""
    from test_engenharia_acompanhamento import SAME
    os_ = {"wid": pagina["id_work_order"], "folio": "16502", "codigo": "X-INV1.1"}
    O.registrar_comentario(os_, "Primeiro", ANA, True, MOTIVO_VARIAS)
    O.registrar_comentario(os_, "Segundo", ANA, True, MOTIVO_VARIAS)
    O.registrar_comentario(os_, "Já foi", ANA, True, "sim", linha_nota="[01/11/2026 10:00] Ana Lima (Engenharia): Já foi")
    fracttal_do_os["det"]["tarefas"] = [{"id": 1}, {"id": 2}]
    _como_admin(cliente, monkeypatch)
    _login_do_fracttal(app, cliente)
    r = cliente.post(LEVAR.format(pagina["id_work_order"]), json={"folio": "16502"}, headers=SAME)
    j = r.get_json()
    assert r.status_code == 200 and j["ok"] and "2 comentários" in j["mensagem"]
    (wid, nota), = fracttal_do_os["escritas"]
    assert re.fullmatch(r"Nota antiga da OS\n\[\d\d/\d\d/\d{4} \d\d:\d\d\] Ana Lima \(Engenharia\): Primeiro\n"
                        r"\[\d\d/\d\d/\d{4} \d\d:\d\d\] Ana Lima \(Engenharia\): Segundo", nota)
    eventos = [e for e in _est(pagina["id_work_order"])["eventos"] if e["evento"] == "comentario"]
    assert {e["texto"]: e["nota"] for e in eventos} == {"Primeiro": "sim", "Segundo": "sim", "Já foi": "sim"}
    assert all(e["linha_nota"] for e in eventos) and not any(e["editado"] for e in eventos)


def test_levar_para_a_nota_e_so_do_administrador(fracttal_do_os, pagina, cliente, app):
    from test_engenharia_acompanhamento import SAME, _como
    _como(cliente, ANA)
    _login_do_fracttal(app, cliente)
    r = cliente.post(LEVAR.format(pagina["id_work_order"]), json={"folio": "16502"}, headers=SAME)
    assert r.status_code == 403 and not fracttal_do_os["escritas"]


def test_sem_comentario_so_no_nexus_nada_vai_ao_fracttal(fracttal_do_os, pagina, cliente, app, monkeypatch):
    from test_engenharia_acompanhamento import SAME
    _como_admin(cliente, monkeypatch)
    _login_do_fracttal(app, cliente)
    r = cliente.post(LEVAR.format(pagina["id_work_order"]), json={"folio": "16502"}, headers=SAME)
    assert r.status_code == 200 and "Nenhum comentário" in r.get_json()["mensagem"] and not fracttal_do_os["escritas"]


def test_a_pagina_mostra_o_levar_para_a_nota_so_ao_administrador(pagina, cliente, monkeypatch):
    from test_engenharia_acompanhamento import _como
    O.registrar_comentario({"wid": pagina["id_work_order"], "folio": "16502", "codigo": "X-INV1.1"}, "Primeiro", ANA,
                           True, MOTIVO_VARIAS)
    assert "data-levar-nota" in _como_admin(cliente, monkeypatch).get(URL).get_data(as_text=True)
    assert "data-levar-nota" not in _como(cliente, BETO).get(URL).get_data(as_text=True)     # fora da lista de admins


def test_erro_do_fracttal_nao_grava_nada(fracttal_do_os, pagina, cliente, app):
    from test_engenharia_acompanhamento import SAME, _como
    fracttal_do_os["resposta"].update(ok=False, erro="O Fracttal recusou")
    _como(cliente, ANA)
    _login_do_fracttal(app, cliente)
    r = cliente.post(COMENTAR.format(pagina["id_work_order"]), json={"texto": "x", "folio": "16502"}, headers=SAME)
    assert r.status_code == 502 and "Nada foi gravado" in r.get_json()["erro"]
    assert not _est(pagina["id_work_order"])


def test_comentario_de_outro_site_ou_de_fora_da_engenharia_e_recusado(fracttal_do_os, pagina, cliente, app,
                                                                      monkeypatch):
    from test_engenharia_acompanhamento import _como

    from nexus.auth import setor_telas as ST
    _como(cliente, ANA)
    _login_do_fracttal(app, cliente)
    r = cliente.post(COMENTAR.format(pagina["id_work_order"]), json={"texto": "x", "folio": "16502"},
                     headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": set(), "setor": {"id": SID.PERFORMANCE, "nome": "Performance"},
                                               "erro": ""})
    r = _como(cliente, BETO).post(COMENTAR.format(pagina["id_work_order"]), json={"texto": "x", "folio": "16502"},
                                  headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 400 and "Engenharia" in r.get_json()["erro"]
    assert not fracttal_do_os["escritas"]


# ── Task 4: o quadro (o clique abre a página, o status e a prioridade nos cartões, o pulso das paradas) ──────────────
def _quadro(cliente, monkeypatch, oss):
    from test_engenharia_acompanhamento import _como

    from nexus.engenharia import os_equipe as E
    monkeypatch.setattr(E, "pedir_releitura", lambda app=None, esperar=False, forcar=False: None)
    monkeypatch.setattr(E, "dados", lambda: {"os": oss, "equipe": [{"id": 1, "nome": "Ana", "nome_fracttal": "Ana Teste"}],
                                             "faltam": [], "lido": 1.0, "lendo": False, "erro": ""})
    html = _como(cliente, ANA).get("/t/engenharia/equipe").get_data(as_text=True)
    dados = json.loads(html.split('id="kb-dados">', 1)[1].split("</script>", 1)[0])
    return html, {o["os"]: o for o in dados["oss"]}


def test_quadro_leva_status_prioridade_e_parada_de_cada_os(banco, cliente, monkeypatch):
    # a OS 1 foi criada há semanas e ninguém mexeu: pulsa; a 2 a engenharia classificou agora: não pulsa
    from test_engenharia_equipe import AGORA, _w

    from nexus.engenharia import os_equipe as E
    oss = E.montar([_w("1", 1, prog_dias=2), _w("2", 2)], {"id": 1, "nome": "Ana"}, AGORA)
    O.classificar({"wid": 9002, "folio": "2", "codigo": "X-INV1.1"}, 6, 3, ANA, True)
    _html, por = _quadro(cliente, monkeypatch, oss)
    assert por["1"]["parada"] is True and por["1"]["eng_status"] == "" and por["1"]["ultima_iso"]
    assert por["2"]["parada"] is False and por["2"]["eng_status"] == "Validação Final"
    assert por["2"]["eng_prioridade"] == "Urgente" and por["2"]["eng_prioridade_id"] == 3


def test_quadro_sem_o_livro_nao_pulsa_e_diz(banco, cliente, monkeypatch):
    from test_engenharia_equipe import AGORA, _w

    from nexus.engenharia import os_equipe as E
    monkeypatch.setattr(O, "ler", lambda forcar=False: {"eventos": [], "lido_em": None, "erro": "ConnectionError: x"})
    oss = E.montar([_w("1", 1, prog_dias=2)], {"id": 1, "nome": "Ana"}, AGORA)
    html, por = _quadro(cliente, monkeypatch, oss)
    assert por["1"]["parada"] is False and "Agora sem o status da engenharia (ConnectionError)" in html


def test_clique_no_cartao_abre_a_pagina_da_os():
    from pathlib import Path
    t = Path("nexus/torres/engenharia/templates/engenharia/equipe.html").read_text(encoding="utf-8")
    # o card do OS Creator só no ramo da Performance (`{% if card %}`, 04/11/2026); o quadro da Engenharia abre a página
    import re
    so_eng = re.sub(r"\{% if card %\}.*?\{% (else|endif) %\}", "", t, flags=re.S)
    assert "nexusRota('/t/engenharia/equipe/os/')" in so_eng and "NexusOsCard" not in so_eng and "card_os_abrir" not in so_eng
    assert "kb-card--parada" in t and "o.eng_status" in t and "o.eng_prioridade" in t


def test_pulso_usa_a_sombra_em_camadas_por_token():
    from pathlib import Path
    css = Path("nexus/static/engenharia.css").read_text(encoding="utf-8")
    regra = re.search(r"\.kb-card--parada::after\{([^}]*)\}", css)
    assert regra and "animation:kb-pulso" in regra.group(1)
    # Levi, 24/10/2026: "poderia fazer algo mais forte que destacasse um pouco mais porém sem destacar tanto": um contorno
    # e um halo laranjas por cima da sombra em camadas dele, pulsando juntos
    assert re.findall(r"var\((--pulso-a\d+)\)", regra.group(1)) == [f"--pulso-a{n}" for n in (71, 43, 71, 57, 43, 28, 14)]
    assert "0 0 0 1.5px var(--pulso-a71),0 0 16px 3px var(--pulso-a43)" in regra.group(1)
    assert re.search(r"@keyframes kb-pulso\{from\{opacity:\.5\}to\{opacity:1\}\}", css)
    assert "prefers-reduced-motion:reduce" in css
    tokens = Path("nexus/static/nexus.css").read_text(encoding="utf-8")
    assert tokens.count("--pulso-a71:") == 2 and tokens.count("--pulso-a14:") == 2                      # os dois temas


def test_os_quatro_numeros_da_os_viram_duas_colunas_no_celular():
    # prova a 375 px (24/10/2026); a faixa é a da tela do chamado: duas colunas a 980 px, como a .kpis de lá
    from pathlib import Path
    css = Path("nexus/static/engenharia.css").read_text(encoding="utf-8")
    assert re.search(r"@media \(max-width:980px\)\{\.eg-ac-kpis\{grid-template-columns:repeat\(2,minmax\(0,1fr\)\)", css)


# ── revisão final (24/10/2026) ───────────────────────────────────────────────────────────────────────────────────────
def test_os_que_o_fracttal_nao_devolveu_inteira_nao_tem_a_nota_apagada(fracttal_do_os, pagina, cliente, app):
    # o get_os_detalhes que falha "mole" volta sem tarefas e com a nota vazia: gravar ali trocaria a nota inteira pela
    # linha nova (as anteriores e os blocos [PCM] iriam embora para sempre)
    from test_engenharia_acompanhamento import SAME, _como
    fracttal_do_os["det"].update(tarefas=[], notas="")
    _como(cliente, ANA)
    _login_do_fracttal(app, cliente)
    r = cliente.post(COMENTAR.format(pagina["id_work_order"]), json={"texto": "x", "folio": "16502"}, headers=SAME)
    assert r.status_code == 502 and "Nada foi gravado" in r.get_json()["erro"]
    assert not fracttal_do_os["escritas"] and not _est(pagina["id_work_order"])


def test_nota_que_nao_bate_com_a_leitura_fica_so_no_nexus(fracttal_do_os, pagina, cliente, app):
    # o Fracttal tem a nota da OS e a da tarefa (a OS 12191 tinha as duas diferentes): se a nota que a página mostra não
    # está no que vai ser regravado, acrescentar apagaria a da página
    from test_engenharia_acompanhamento import SAME, _como
    fracttal_do_os["det"]["notas"] = "TESTE 3"
    _como(cliente, ANA)
    _login_do_fracttal(app, cliente)
    r = cliente.post(COMENTAR.format(pagina["id_work_order"]), json={"texto": "Visto", "folio": "16502"}, headers=SAME)
    assert r.status_code == 200 and "só no Nexus" in r.get_json()["mensagem"]
    assert not fracttal_do_os["escritas"] and "não bateu" in _est(pagina["id_work_order"])["eventos"][0]["nota"]


def test_sessao_do_fracttal_vencida_encerra_quem_entrou_pelo_fracttal(fracttal_do_os, pagina, cliente, app, monkeypatch):
    # o token cassado (antes do exp) voltava do /os/login direto para a página: o portão só olha o exp
    import api as os_api
    from test_engenharia_acompanhamento import SAME, _como

    def vencida(wid):
        raise os_api.SessionExpired("sessão expirada")
    monkeypatch.setattr(os_api, "get_os_detalhes", vencida)
    _como(cliente, ANA)                                   # sem "via": a sessão nasceu do Fracttal
    _login_do_fracttal(app, cliente)
    r = cliente.post(COMENTAR.format(pagina["id_work_order"]), json={"texto": "x", "folio": "16502"}, headers=SAME)
    j = r.get_json()
    assert r.status_code == 401 and j["sessao_encerrada"] and j["login"] is True
    assert not _est(pagina["id_work_order"])


def test_sessao_do_fracttal_vencida_de_quem_entrou_pela_microsoft_tira_o_cookie(fracttal_do_os, pagina, cliente, app,
                                                                                monkeypatch):
    import time

    import api as os_api
    from test_engenharia_acompanhamento import SAME

    def vencida(wid):
        raise os_api.SessionExpired("sessão expirada")
    monkeypatch.setattr(os_api, "get_os_detalhes", vencida)
    with cliente.session_transaction() as s:
        s["logado"], s["admin"], s["usuario"] = True, False, ANA
        s["via"], s["ms_ate"] = "microsoft", time.time() + 3600
    _login_do_fracttal(app, cliente)
    r = cliente.post(COMENTAR.format(pagina["id_work_order"]), json={"texto": "x", "folio": "16502"}, headers=SAME)
    assert r.status_code == 401 and r.get_json()["login"].startswith("/os/login?next=")
    assert any(h.startswith("os_sessao=;") for h in r.headers.getlist("Set-Cookie"))   # o /os/login mostra o formulário


def test_leitura_do_livro_que_falha_fica_guardada_e_tem_prazo_curto(banco, monkeypatch):
    # o quadro passou a ler o banco: com a API pendurada, cada abertura esperava os 60 s do pedido
    prazos, pedidos = [], []

    def pendurada(url, *a, **k):
        pedidos.append(url)
        prazos.append(k.get("timeout"))
        raise TimeoutError("sem resposta")
    monkeypatch.setattr(banco, "get", pendurada)
    O.limpar()
    assert O.ler()["erro"] and O.ler()["erro"]
    assert len(pedidos) == 1 and prazos[0] <= O.PRAZO_S


def test_livro_existente_sem_a_aba_dos_eventos_e_leitura_incompleta(banco):
    # a listagem que omite a aba por um instante não vira "sem nada" por 1 minuto (pulso e números chutados)
    O.classificar(OS1, 1, None, ANA, True)
    banco.omitir.add(O.LIVRO)
    O.limpar()
    lido = O.ler()
    assert lido["erro"] and lido["lido_em"] is None


def test_pagina_sem_o_livro_nao_chuta_a_ultima_atualizacao(pagina, cliente, monkeypatch):
    from test_engenharia_acompanhamento import _como
    monkeypatch.setattr(O, "ler", lambda forcar=False: {"eventos": [], "lido_em": None, "erro": "ConnectionError: x"})
    html = _como(cliente, ANA).get(URL).get_data(as_text=True)
    _rot, valores = _kpis(html)
    assert valores[0] == valores[1] == valores[3] == "—" and "Não consegui ler o status" in html



# ── o topo igual ao da tela do chamado da Garantia (Levi, 24/10/2026: "quero quase idêntico na estrutura mesmo então essa
# parte de cima quero na mesma estrutura e fonte os botões quero nas mesmas posições") ─────────────────────────────────
def test_topo_na_estrutura_da_tela_do_chamado(pagina, cliente):
    from test_engenharia_acompanhamento import _como
    html = _como(cliente, ANA).get(URL).get_data(as_text=True)
    topo = html.split('<div class="eg-ac-head">', 1)[1].split('<div class="eg-ac-kpis"', 1)[0]
    # numa linha: a volta, a pílula do estado e o título com o ativo em verde; embaixo, o local, o tipo e o Fracttal
    tit = topo.split('<div class="eg-ac-tit">', 1)[1].split("</div>", 1)[0]
    assert tit.index("eg-ac-volta") < tit.index("eg-ac-tag") < tit.index("<h1>Análise 16502</h1>")
    assert '<p class="eg-ac-sub">Thopen · Altair 1 · <b>Administrativa</b> · Em Processo no Fracttal</p>' in topo
    # o botão no lugar do "Abrir a OS": à direita, no fim da linha, contorno
    acoes = topo.split('<div class="eg-ac-acoes">', 1)[1]
    assert 'class="eg-ac-btn eg-ac-btn--o"' in acoes and ">Solicitar OS<" in acoes
    assert "gc-eyebrow" not in topo and "kb-kpis" not in html
    assert "family=Inter:wght@400;500;600;700" in html                   # a fonte da tela do chamado


def test_pilula_do_topo_diz_o_estado_como_a_do_chamado(pagina, cliente):
    # a OS de teste está atrasada (programada antes de hoje): a pílula vermelha diz há quantos dias
    from test_engenharia_acompanhamento import _como
    html = _como(cliente, ANA).get(URL).get_data(as_text=True)
    tag = re.search(r'<span class="eg-ac-tag eg-ac-tag--(\w+)">([^<]+)</span>', html)
    assert tag.group(1) == "r" and tag.group(2).startswith("A fazer · atrasada há ")


def test_topo_usa_a_fonte_e_as_medidas_da_tela_do_chamado():
    from pathlib import Path
    css = Path("nexus/static/engenharia.css").read_text(encoding="utf-8")
    assert re.search(r'\.eg-ac\{[^}]*--fonte-ac:"Inter"', css)
    assert re.search(r"\.eg-ac-head h1\{font:700 21px/1\.25 var\(--fonte-ac\)", css)
    assert re.search(r"\.eg-ac-kpi \.val\.pq\{font:600 15px/1\.3 var\(--fonte-ac\)", css)
    assert re.search(r"\.eg-ac-acoes\{margin-left:auto", css)


def test_valor_longo_da_faixa_quebra_em_vez_de_invadir_o_vizinho():
    # prova a 375 px: "Diagnóstico em Andamento" (sem quebra, como as datas da tela do chamado) cobria a Prioridade
    from pathlib import Path
    css = Path("nexus/static/engenharia.css").read_text(encoding="utf-8")
    assert re.search(r"\.eg-ac-kpi \.val\.pq\{[^}]*white-space:normal", css)
    assert re.search(r"\.eg-ac-kpi \.linha\{[^}]*flex-wrap:wrap", css)



# ── 2ª rodada de 24/10/2026 (Levi: o título da OS, a nota de verdade, a cadeia, os Dados e os comentários como os de
# chamados) ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_titulo_da_os_em_cima_e_a_os_e_o_ativo_embaixo(pagina, cliente):
    # Levi, 24/10/2026: "No título invés de OS e ativo bote o título da OS, no lugar do título da OS bote OS e ativo"
    from test_engenharia_acompanhamento import _como
    html = _como(cliente, ANA).get(URL).get_data(as_text=True)
    esq = html.split('<div class="eg-ac-esq">', 1)[1].split('<div class="eg-ac-acoes">', 1)[0]
    assert (esq.index("<h1>Análise 16502</h1>") < esq.index('data-folio="16502" data-status="Em Processo" title="Abrir o card da OS 16502">OS 16502</a> <span>Inversor 1.1</span></p>')
            < esq.index("eg-ac-sub"))


def test_nota_da_os_e_a_que_o_card_do_os_creator_mostra(pagina, cliente):
    # Levi: "não está puxando a nota da OS da engenharia": a nota fica na TAREFA (task_note), como o card lê
    from test_engenharia_acompanhamento import _como
    pagina["task_note"] = "Inversor desarmando à tarde; pedir as curvas."
    html = _como(cliente, ANA).get(URL).get_data(as_text=True)
    nota = _secao(html, "Na nota da OS")
    assert "Inversor desarmando à tarde; pedir as curvas." in nota and "Nota antiga da OS" not in nota


def test_dados_so_com_ativo_usina_responsavel_quem_criou_criacao_e_etiquetas(pagina, cliente):
    # o "Criado por" entrou em 27/10/2026 (Levi: "em dados deve ter o "Criado por"")
    from test_engenharia_acompanhamento import _como
    dados = _secao(_como(cliente, ANA).get(URL).get_data(as_text=True), "Dados")
    assert re.findall(r"<dt>([^<]+)</dt>", dados) == ["Ativo", "Usina", "Responsável", "Criado por", "Criada em",
                                                       "Etiquetas"]


def test_cadeia_da_os_com_o_numero_e_o_pdf_de_cada_uma(pagina, cliente):
    # a OS da engenharia como OS pai das OS de campo: cada uma com o nº e a seta do PDF (com as fotos), como a cadeia
    # do chamado da Garantia
    from test_engenharia_acompanhamento import _como
    html = _como(cliente, ANA).get(URL).get_data(as_text=True)
    cadeia = _secao(html, "A cadeia da OS").split("</form>", 1)[-1]   # depois do Incluir OS do título (11/11/2026)
    itens = re.findall(r'<li( class="aqui")?>.*?</li>', cadeia, re.S)
    assert len(itens) == 3 and itens[0] == ' class="aqui"'
    assert cadeia.index("OS da engenharia") < cadeia.index("16502") < cadeia.index("OS de campo") < cadeia.index("16510")
    for folio in ("16502", "16510", "16511"):
        assert f'data-os-pdf="{folio}"' in cadeia
    # o mesmo PDF da cadeia do chamado, no JS da OS da Engenharia (o mesmo das últimas OS da gaveta, 30/10/2026)
    assert "engenharia-os.js" in html
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent / "nexus/static/engenharia-os.js").read_text(encoding="utf-8")
    assert "nexusRota('/os/api/os/pdf')" in js


def test_comentarios_no_estilo_das_observacoes_do_chamado(pagina, cliente):
    from test_engenharia_acompanhamento import SAME, _como
    _como(cliente, ANA).post(URL + "/classificar", data={"status_id": "3"}, headers=SAME)
    O.registrar_comentario({"wid": pagina["id_work_order"], "folio": "16502", "codigo": "X-INV1.1"}, "Trocar o cabo", ANA,
                           True, "sim")
    html = cliente.get(URL).get_data(as_text=True)
    sec = html.split(">Comentários</h2>", 1)[1].split("</section>", 1)[0]
    assert sec.startswith('<span class="n">2</span>')                      # a contagem ao lado do título
    entradas = re.findall(r'<div class="eg-tl-e([^"]*)">', sec)
    assert entradas == [" novo", " ev"]                                   # o mais novo em destaque; a mudança é evento
    assert re.search(r'<div class="eg-tl-d">\d\d/\d\d</div><div class="eg-tl-a">\d{4}</div>', sec)
    assert '<div class="eg-tl-t">Trocar o cabo</div>' in sec and "Status: Diagnóstico em Andamento" in sec
    assert re.search(r'<div class="eg-tl-u">Ana Lima · \d\d/\d\d/\d{4} \d\d:\d\d</div>', sec)
    assert "Salvar comentário" in sec and "eg-tl-comp" in sec


def test_pulso_vale_mesmo_com_reduzir_movimento():
    # Levi: "a sombra não está pulsando" - o Windows dele está sem os efeitos de animação, e o nexus.css tira toda
    # animação com "reduzir movimento"; o pulso (só a opacidade de uma sombra, sem movimento) fica de fora
    from pathlib import Path
    css = Path("nexus/static/engenharia.css").read_text(encoding="utf-8")
    assert re.search(r"@media \(prefers-reduced-motion:reduce\)\{\.kb-card--parada::after\{animation:kb-pulso 1\.4s "
                     r"ease-in-out infinite alternate!important\}\}", css)
    assert "kb-card--parada::after{animation:none" not in css



# ── 3ª rodada de 24/10/2026: a data do incidente da OS pai e os ativos da OS ─────────────────────────────────────────
def test_solicitar_os_leva_a_data_do_incidente_da_os_pai(pagina, cliente):
    # Levi: "Ao clicar em criar Solicitar OS a data do incidente deve ser a mesma da OS pai". O Fracttal guarda o
    # event_date em UTC; o campo da Nova solicitação é de Brasília
    from test_engenharia_acompanhamento import _como
    pagina["event_date"] = "2026-10-08T09:00:00+00:00"
    html = _como(cliente, ANA).get(URL).get_data(as_text=True)
    assert "data%3D2026-10-08T06%253A00" in html or "data%3D2026-10-08T06%3A00" in html


def test_criar_os_ao_lado_do_solicitar_com_os_mesmos_preenchimentos(pagina, cliente):
    # Levi, 25/10/2026: "ao lado do botão de solicitação quero um botão de 'Criar OS' (...) Fará os mesmos preenchimentos
    # automáticos que já faz na solicitação": o Criar OS do zero do OS Creator com o ativo, esta OS como OS pai e a data
    # do incidente dela
    from urllib.parse import parse_qs, urlsplit

    from test_engenharia_acompanhamento import _como
    pagina["event_date"] = "2026-10-08T09:00:00+00:00"
    html = _como(cliente, ANA).get(URL).get_data(as_text=True)
    acoes = html.split('<div class="eg-ac-acoes">', 1)[1].split("</div>", 1)[0]
    links = re.findall(r'<a class="eg-ac-btn eg-ac-btn--o" href="([^"]+)"[^>]*>([^<]+)</a>', acoes)
    assert [t for _, t in links] == ["Solicitar OS", "Criar OS"]
    destino = {t: urlsplit(parse_qs(urlsplit(h.replace("&amp;", "&")).query)["url"][0]) for h, t in links}
    assert destino["Solicitar OS"].path == "/os/solicitacao" and destino["Criar OS"].path == "/os/tradicional"
    sugestao = parse_qs(destino["Criar OS"].query)
    assert sugestao == parse_qs(destino["Solicitar OS"].query)
    assert sugestao["os_pai_folio"] == ["16502"] and sugestao["data"] == ["2026-10-08T06:00"]
    # os dois, sempre (o OS Creator só escolhe a OS pai com o id E o nº; desde 26/10/2026 o campo fica no Passo 1)
    assert sugestao["os_pai"] == [str(pagina["id_work_order"])]


def test_os_de_varios_ativos_tem_o_bloco_ativos_em_cima_da_nota(pagina, cliente, monkeypatch):
    from test_engenharia_acompanhamento import _como

    from nexus.engenharia import os_equipe as E
    outra = dict(pagina, code="X-INV2.1", items_log_description="Inversor 2.1 {X-INV2.1}", description="Análise 16502")
    lido = E._ler_fracttal

    def com_dois_ativos(path):
        r = lido(path)
        if path.startswith("work_orders?wo_folio=16502"):
            r = {"data": list(r["data"]) + [outra]}
        return r
    monkeypatch.setattr(E, "_ler_fracttal", com_dois_ativos)
    html = _como(cliente, ANA).get(URL).get_data(as_text=True)
    ativos = _secao(html, "Ativos")
    assert "X-INV1.1" in ativos and "X-INV2.1" in ativos and "Inversor 2.1" in ativos
    assert html.index(">Ativos</h2>") < html.index(">Na nota da OS</h2>")
    assert '>OS 16502</a> <span>2 ativos</span></p>' in html
    assert re.search(r"<dt>Ativo</dt><dd[^>]*>2 ativos</dd>", _secao(html, "Dados"))


def test_os_de_um_ativo_nao_tem_o_bloco_ativos(pagina, cliente):
    from test_engenharia_acompanhamento import _como
    assert ">Ativos</h2>" not in _como(cliente, ANA).get(URL).get_data(as_text=True)


def test_ativo_ao_lado_da_os_segue_em_verde():
    # na tela do chamado o ativo vai em verde ao lado da OS; saiu do título grande e ficou na linha de baixo
    from pathlib import Path
    css = Path("nexus/static/engenharia.css").read_text(encoding="utf-8")
    assert re.search(r"\.eg-ac-titulo span\{color:var\(--verde-texto\)", css)


# ── 4ª rodada de 24/10/2026: trocar o responsável como no chamado, e os ativos de 5 em 5 ─────────────────────────────
def test_trocar_o_responsavel_como_no_chamado(pagina, cliente):
    # Levi: "em responsável quero a opção de mudar de responsável que nem é feito no chamados": o "trocar" ao lado do
    # nome nos Dados abre o diálogo de lá (Hoje está com..., a pessoa, Atribuir), pela API do OS Creator
    from test_engenharia_acompanhamento import _como
    html = _como(cliente, ANA).get(URL).get_data(as_text=True)
    dados = _secao(html, "Dados")
    # (06/11/2026, Levi: "tire esse botão trocar e a troca pode ser feita ao clicar no nome do responsável")
    assert re.search(r"<dt>Responsável</dt><dd class=\"eg-resp\"><button type=\"button\" class=\"eg-resp-nome\" "
                     r"data-resp-nome data-trocar-resp[^>]*>Ana Lima</button></dd>", dados)
    assert ">trocar<" not in dados
    assert "Trocar o responsável da OS 16502" in html and "Hoje está com <b data-resp-hoje>Ana Lima</b>." in html
    assert "nexusRota('/os/api/responsaveis')" in html and "nexusRota('/os/api/os/' + wid + '/responsavel')" in html


def test_depois_da_troca_a_volta_rele_o_quadro(pagina, cliente):
    # a OS muda de pessoa no Fracttal na hora, mas o quadro guarda a leitura por até 5 min: depois do Atribuir, o
    # "← Quadro da equipe" volta com ?atualizar=1 (o mesmo que o quadro pede depois de uma mudança pelo card do OS Creator)
    from test_engenharia_acompanhamento import _como
    html = _como(cliente, ANA).get(URL).get_data(as_text=True)
    assert re.search(r'data-trocar-resp[^>]*data-volta="/t/engenharia/equipe\?atualizar=1"', html)
    assert "getAttribute('data-volta')" in html


def test_quem_nao_e_da_engenharia_nao_troca_o_responsavel(pagina, cliente, monkeypatch):
    from test_engenharia_acompanhamento import _como

    from nexus.auth import setor_telas as ST
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": set(), "setor": {"id": SID.PERFORMANCE, "nome": "Performance"},
                                               "erro": ""})
    html = _como(cliente, BETO).get(URL).get_data(as_text=True)
    assert "data-trocar-resp" not in html and "Ana Lima" in _secao(html, "Dados")


def test_ativos_de_cinco_em_cinco(pagina, cliente, monkeypatch):
    # Levi: "no ativos também quero que limite a 5 por vez!": os 5 primeiros e o "Mostrar mais", como a tabela de ativos
    # da Nova solicitação (lá de 10 em 10)
    from test_engenharia_acompanhamento import _como

    from nexus.engenharia import os_equipe as E
    extras = [dict(pagina, code=f"X-INV{n}.1", items_log_description=f"Inversor {n}.1 {{X-INV{n}.1}}") for n in range(2, 8)]
    lido = E._ler_fracttal

    def com_sete(path):
        r = lido(path)
        if path.startswith("work_orders?wo_folio=16502"):
            r = {"data": list(r["data"]) + extras}
        return r
    monkeypatch.setattr(E, "_ler_fracttal", com_sete)
    ativos = _secao(_como(cliente, ANA).get(URL).get_data(as_text=True), "Ativos")
    linhas = re.findall(r"<tr data-ativo( hidden)?>", ativos)
    assert len(linhas) == 7 and linhas[:5] == [""] * 5 and linhas[5:] == [" hidden"] * 2
    assert "Mostrando 5 de 7" in ativos and 'data-mais-ativos="5">Mostrar mais 2</button>' in ativos


def test_ate_cinco_ativos_sem_o_mostrar_mais(pagina, cliente, monkeypatch):
    from test_engenharia_acompanhamento import _como

    from nexus.engenharia import os_equipe as E
    outra = dict(pagina, code="X-INV2.1", items_log_description="Inversor 2.1 {X-INV2.1}")
    lido = E._ler_fracttal
    monkeypatch.setattr(E, "_ler_fracttal", lambda path: ({"data": list(lido(path)["data"]) + [outra]}
                                                           if path.startswith("work_orders?wo_folio=16502") else lido(path)))
    ativos = _secao(_como(cliente, ANA).get(URL).get_data(as_text=True), "Ativos")
    # nenhuma linha de ativo escondida (o painel das tarefas, de 06/11/2026, tem os seus elementos escondidos)
    assert "<tr data-ativo hidden" not in ativos and "Mostrar mais" not in ativos


def test_a_pagina_da_os_tem_as_acoes_da_os(pagina, cliente):
    """Levi, 06/11/2026: "poderia incluir um botão de incluir anexo?" e "Nessas telas devem ter essas opção também:
    Enviar para verificação, concluir e cancelar!". O Incluir anexo sobe da própria página; os anexos, o Concluir e o
    Cancelar abrem o card do OS Creator já no diálogo (o NexusOsCard com a ação)."""
    from test_engenharia_acompanhamento import _como
    html = _como(cliente, ANA).get(URL).get_data(as_text=True)
    caixa = _acoes(html)
    for a in ("anexos-os", "anexos-sub", "verificacao", "concluir", "cancelar"):
        assert f'data-card-acao="{a}"' in caixa, a
    assert "data-incluir-anexo" in caixa and f'data-incluir-url="/os/api/os/{pagina["id_work_order"]}/anexos"' in html
    assert 'accept=".pdf' in caixa and "window.NexusOsCard" in html


def test_as_acoes_da_os_em_dois_grupos_e_as_regras_no_explica(pagina, cliente):
    """Levi, 06/11/2026: "Em ações de OS tire o texto 'PDF; imagem (...) · ou cole com Ctrl+V' e organize melhor a
    informação". A caixa fica em dois grupos (os Anexos, com o Incluir anexo; o Andamento, com a verificação, o concluir e
    o cancelar) e as regras do anexo vão para o "!" do título dela (o padrão do Nexus) e para a dica do botão."""
    from test_engenharia_acompanhamento import _como
    html = _como(cliente, ANA).get(URL).get_data(as_text=True)
    caixa = _acoes(html)
    assert "<span>Anexos</span>" in caixa and "<span>Andamento</span>" in caixa
    assert "MB cada" not in re.sub(r'<details.*?</details>', '', re.sub(r'title="[^"]*"', '', caixa), flags=re.S)                              # a frase não está à vista
    assert re.search(r'data-incluir-anexo[^>]*title="[^"]*até 10 MB cada', caixa)
    assert re.search(r'data-card-acao="anexos-os"><span>Da OS</span><b data-n="os">', caixa)
    explica = caixa.split('class="gc-explica"', 1)[1].split("</details>", 1)[0]
    assert "até 10 MB cada" in explica and "Ctrl+V" in explica


def test_os_ativos_se_recolhem(pagina, cliente):
    """Levi, 06/11/2026: "quero só que dê para recolher os ativos". O Esconder no título do bloco esconde o corpo (a lista
    das tarefas e a do REST) e lembra a escolha neste navegador."""
    from test_engenharia_acompanhamento import _como
    html = _como(cliente, ANA).get(URL).get_data(as_text=True)
    bloco = html.split("data-tarefas-os", 1)[1].split("</section>", 1)[0]
    assert re.search(r'<button type="button" class="eg-recolher" data-recolher-ativos aria-expanded="true" '
                     r'aria-controls="corpo_ativos"', bloco)
    corpo = bloco.split('id="corpo_ativos"', 1)[1]
    assert "data-tarefas-lista" in corpo and "data-tarefas-msg" in corpo        # (a lista do REST, com 2+ ativos, também)
    from pathlib import Path
    js = Path("nexus/static/engenharia-os.js").read_text(encoding="utf-8")
    assert "[data-recolher-ativos]" in js and "localStorage" in js


def test_o_painel_le_o_inicio_em_utc_e_conta_no_singular():
    """Prova no ar de 06/11/2026 (OS 18750): o início do cronômetro vem do Fracttal em UTC sem o fuso ("15:38" era 12:38
    em Brasília), e a OS de uma subtarefa dizia "0 de 1 subtarefas"."""
    from pathlib import Path
    js = Path("nexus/static/engenharia-os.js").read_text(encoding="utf-8")
    assert "iso + 'Z'" in js and "getHours()" in js
    assert "t.total === 1 ? ' subtarefa' : ' subtarefas'" in js


def test_o_painel_das_tarefas_esta_na_pagina_e_os_botoes_sao_da_engenharia(pagina, cliente):
    """06/11/2026: o bloco dos ativos vira o painel das tarefas (o check, os anexos, o cronômetro e as subtarefas pelo OS
    Creator). Os botões que gravam ficaram só com o administrador até a prova no Fracttal (TESTE - PA, OS 18750 e 18751,
    06/11/2026); provados, são da Engenharia."""
    from test_engenharia_acompanhamento import _como
    html = _como(cliente, ANA).get(URL).get_data(as_text=True)
    wid = pagina["id_work_order"]
    assert "data-tarefas-os" in html and f'data-tarefas-url="/os/api/os/{wid}/tarefas"' in html
    assert f'data-tarefa-url="/os/api/os/{wid}/tarefa"' in html and 'data-motivos-url="/os/api/execucao/motivos"' in html
    assert 'data-acoes="sim"' in html.split("data-tarefas-os", 1)[1].split(">", 1)[0]


def test_quem_nao_e_da_engenharia_ve_as_tarefas_sem_os_botoes(pagina, cliente, monkeypatch):
    from test_engenharia_acompanhamento import _como

    from nexus.auth import setor_telas as ST
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": set(), "setor": {"id": SID.PERFORMANCE, "nome": "Performance"},
                                               "erro": ""})
    html = _como(cliente, BETO).get(URL).get_data(as_text=True)
    assert 'data-acoes=""' in html.split("data-tarefas-os", 1)[1].split(">", 1)[0]


def test_a_resposta_de_texto_da_subtarefa_quebra_a_linha():
    """Levi, 09/11/2026: "quando clica na OS e vai digitar na subtarefa tem que abrir uma caixa de texto que quebra o
    texto, está rolando infinito para o lado". A resposta de texto é uma caixa de várias linhas que cresce com o texto; o
    número segue numa linha só (o teclado numérico)."""
    from pathlib import Path
    js = Path("nexus/static/engenharia-os.js").read_text(encoding="utf-8")
    css = Path("nexus/static/engenharia.css").read_text(encoding="utf-8")
    assert "<textarea class=\"eg-ac-campo eg-ac-texto\"" in js
    assert re.search(r"\.eg-ac-texto\{[^}]*field-sizing:content", css) and re.search(r"\.eg-ac-texto\{[^}]*overflow-wrap:anywhere", css)


def test_anexar_abre_o_cartao_de_colar_ou_fazer_o_upload():
    """Levi, 09/11/2026: "ao clicar em anexar aparecesse uma tela card sobrepondo porém sem blur de fundo aparecendo um
    ícone de imagem a mensagem 'Cole ou faça o upload do anexo' o 'faça upload do anexo' será clicável em verde grid".
    O Anexar da tarefa e o Incluir anexo da OS abrem o mesmo cartão; com ele aberto, o colar vai para ele (e não para a
    linha "Anexar à OS" da página)."""
    from pathlib import Path
    js = Path("nexus/static/engenharia-os.js").read_text(encoding="utf-8")
    css = Path("nexus/static/engenharia.css").read_text(encoding="utf-8")
    assert "window.egCartaoAnexo = function" in js and "Cole ou " in js and "faça o upload do anexo" in js
    assert js.count("window.egCartaoAnexo({") == 2                       # a tarefa e a OS
    assert "dialog.eg-anx[open]" in js                                    # o colar da página cede ao cartão
    anx = re.search(r"\.eg-anx\{[^}]*\}", css).group(0)
    assert "backdrop-filter" not in anx and re.search(r"\.eg-anx::backdrop\{background:transparent\}", css)
    assert re.search(r"\.eg-anx-up\{[^}]*color:var\(--verde-texto\)", css)


# ── a página da OS para quem chega de Chamados e da Performance (09/11/2026) ─────────────────────────────────────────
# Levi: "gostaria que essas mudanças feitas para essa tela fossem também para chamados, performance etc" e, perguntado o
# que fazem os que não são da Engenharia, "Tudo, inclusive comentários". O Quadro da Performance e a tela do chamado de
# Garantias abrem esta página; a volta é a de onde veio (`?de=`).
def _de_fora(monkeypatch, telas=("performance/equipe",)):
    from nexus.auth import setor_telas as ST
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": set(telas),
                                               "setor": {"id": SID.PERFORMANCE, "nome": "Performance"}, "erro": ""})


def test_o_portao_abre_a_pagina_da_os_para_quem_tem_o_quadro_da_performance_ou_garantias(app):
    from nexus.auth import setor_telas as ST
    with app.test_request_context():
        for telas in ({"performance/equipe"}, {"chamados/garantias"}, {"engenharia/equipe"}):
            assert ST.pode("/t/engenharia/equipe/os/16502", telas), telas
            assert ST.pode("/t/engenharia/equipe/os/16502/classificar", telas), telas
        assert not ST.pode("/t/engenharia/equipe", {"performance/equipe"})          # o Quadro da Engenharia, não
        assert not ST.pode("/t/engenharia/etm/os/16502", {"chamados/garantias"})   # nem a OS de ETM
        assert not ST.pode("/t/engenharia/equipe/os/16502", {"performance/clima"})


def test_quem_tem_o_quadro_da_performance_age_na_pagina_da_os(pagina, cliente, monkeypatch):
    from test_engenharia_acompanhamento import SAME, _como
    _de_fora(monkeypatch)
    html = _como(cliente, BETO).get(URL).get_data(as_text=True)
    assert "data-trocar-resp" in html and 'data-acoes="sim"' in html.split("data-tarefas-os", 1)[1].split(">", 1)[0]
    assert "data-comentar=" in html
    r = cliente.post(URL + "/classificar", data={"status_id": "3"}, headers=SAME)
    assert r.status_code == 303 and "ok=" in r.headers["Location"]
    assert _est(pagina["id_work_order"])["status_id"] == 3


def test_quem_nao_tem_as_telas_da_pagina_so_ve(pagina, cliente, monkeypatch):
    from test_engenharia_acompanhamento import _como
    _de_fora(monkeypatch, telas=("performance/clima",))
    html = _como(cliente, BETO).get(URL).get_data(as_text=True)
    assert "data-trocar-resp" not in html and "data-comentar=" not in html


def test_a_volta_e_a_de_onde_veio(pagina, cliente):
    from test_engenharia_acompanhamento import _como
    _como(cliente, ANA)
    perf = cliente.get(URL + "?de=performance").get_data(as_text=True)
    assert '<a class="eg-ac-volta" href="/t/performance/equipe">← Quadro da equipe</a>' in perf
    de = "/t/chamados/garantias?abrir=/os/chamados/acompanhamento/812"
    cham = cliente.get(URL + "?" + urlencode({"de": de})).get_data(as_text=True)
    assert '<a class="eg-ac-volta" href="/t/chamados/garantias?abrir=/os/chamados/acompanhamento/812">← Chamado 812</a>' in cham
    for ruim in ("https://fora.exemplo/x", "/t/chamados/garantias?abrir=/os/chamados/acompanhamento/812&x=1", "/t/pcm"):
        outra = cliente.get(URL + "?" + urlencode({"de": ruim})).get_data(as_text=True)
        assert '<a class="eg-ac-volta" href="/t/engenharia/equipe">← Quadro da equipe</a>' in outra, ruim


def test_o_de_segue_no_salvar_da_pagina(pagina, cliente):
    from test_engenharia_acompanhamento import SAME, _como
    _como(cliente, ANA)
    html = cliente.get(URL + "?de=performance").get_data(as_text=True)
    assert '<input type="hidden" name="de" value="performance">' in html
    r = cliente.post(URL + "/classificar", data={"status_id": "3", "de": "performance"}, headers=SAME)
    assert r.status_code == 303 and "de=performance" in r.headers["Location"]
    r = cliente.post(URL + "/classificar", data={"status_id": "3", "de": "https://fora.exemplo"}, headers=SAME)
    assert "fora.exemplo" not in r.headers["Location"]
    # o comentário e o levar para a nota relêem a página com o aviso e o mesmo `de`
    from pathlib import Path
    tpl = Path("nexus/torres/engenharia/templates/engenharia/os_quadro.html").read_text(encoding="utf-8")
    js = Path("nexus/static/engenharia-os.js").read_text(encoding="utf-8")
    assert "window.egVoltarComOk = function" in js and "new URLSearchParams(location.search)" in js
    assert tpl.count("window.egVoltarComOk(") == 2 and js.count("window.egVoltarComOk(") == 1    # comentar, mudar e levar


def test_o_painel_tem_os_registros_com_o_inicio_e_o_fim():
    """09/11/2026: "A ideia é poder editar o início e fim da atividade!": o botão Registros de cada tarefa abre a lista
    dos registros de execução com o início e o fim (datetime-local, a hora de Brasília)."""
    from pathlib import Path
    js = Path("nexus/static/engenharia-os.js").read_text(encoding="utf-8")
    assert "botao('Registros', 'registros')" in js and "registros: function (t)" in js
    assert 'type="datetime-local"' in js and "'/registro/'" in js


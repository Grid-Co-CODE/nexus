"""Desempenho do OS Creator Web do Nexus (Levi, 08/10/2026: "O carregamento de: Acompanhamento de chamados e a tela que
abre quando clica na OS está demorando um pouco para carregar, verificar se dá para melhorar!").

O que mudou e é conferido aqui, com um Fracttal FALSO (cada pedido é contado; nenhum vai à rede):
- o detalhe da OS (o card do Histórico e a tela de um chamado) faz os mesmos pedidos de antes, em duas levas paralelas;
- a contagem dos anexos do card não paga a URL pré-assinada de cada arquivo (era um s3_object_get por foto);
- o Acompanhamento de chamados guarda, POR PESSOA, o ticket das OS concluídas, e a tela de um chamado não relê os
  tickets de todas as OS para abrir uma;
- leitura feita com a sessão do Fracttal morta não fica na memória.
A medida (antes e depois, com 300 ms por pedido) e a comparação valor a valor das telas estão no README da torre.
Nomes e números são de mentira: o repositório é público."""
import sys
import threading
import time

import pytest

from nexus.torres.oscreator import ponte

pytest.importorskip("PyQt6")          # o clone importa o steps/ui.py do OS Creator ao montar a tela de Engenharia
if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
import chamados_obs_store as obs_store  # noqa: E402
from os_web import criar_app, rotas, rotas_acomp  # noqa: E402

JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira
OUTRO_JWT = "aaa.eyJlbWFpbCI6Im91dHJhQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"
WID, PAI = 9001, 4000


class Falso:
    """O Fracttal de mentira: responde ao que o card pede, dorme `espera` por pedido e conta quantos foram juntos."""

    def __init__(self, espera=0.05):
        self.espera, self.n, self.agora, self.pico, self.s3 = espera, {}, 0, 0, 0
        self.trava = threading.Lock()

    def rpc(self, metodo, params, timeout=45):
        with self.trava:
            self.n[metodo] = self.n.get(metodo, 0) + 1
            self.agora += 1
            self.pico = max(self.pico, self.agora)
        try:
            time.sleep(self.espera)
        finally:
            with self.trava:
                self.agora -= 1
        p = params or {}
        if metodo == api.RPC_WO_TASKS:
            return {"data": [{"id": 77, "id_work_order_task": 77, "wo_folio": 15001, "tasks_description": "Preventiva",
                              "tasks_types_main_description": "Preventiva", "items_description": "Cabine 1 { TST-CAB1 }",
                              "code_item": "TST-CAB1", "personnel_description": "Pessoa Teste", "id_parent_wo": PAI,
                              "id_status_work_order": 1, "note": "nota da OS"}]}
        if metodo == api.RPC_WO_FORMIT:
            return {"data": [{"description": "Item %d" % k, "done": "true", "value": "ok", "order_number": k,
                              "id_work_order_task": 77, "id_work_orders_tasks_form_items": 800 + k,
                              "num_attachments": 2 if k == 1 else 0, "id_task_form_item_type": 1} for k in (1, 2)]}
        if metodo == api.RPC_WO_DETAILS:
            if p.get("id") == PAI:
                return {"data": [{"id": PAI, "wo_folio": 12500}]}
            return {"data": [{"id": WID, "labels": [], "created_by": "Pessoa Teste", "id_parent_wo": PAI}]}
        if metodo == api.RPC_REQ_LIST:
            return {"data": []}
        if metodo == api.RPC_WO_FORMIT_ATTACH:
            return {"data": [{"type": 1, "value": ".ot/a/foto%d.jpg" % k} for k in range(2)]}
        if metodo == api.RPC_WO_IMAGES:
            return {"data": [{"id_work_order_task": 77}]}
        if metodo == api.RPC_WO_FILES:
            return {"data": [{"value": ".ot/a/foto0.jpg"}, {"value": ".ot/doc.pdf", "description": "doc"}]}
        raise AssertionError("pedido que o card não faz: " + metodo)

    def s3_get_url(self, nome):
        with self.trava:
            self.s3 += 1
        return "https://s3.exemplo.invalid/" + nome


@pytest.fixture
def falso(monkeypatch):
    f = Falso()
    monkeypatch.setattr(api, "_rpc_call", f.rpc)
    monkeypatch.setattr(api, "s3_get_url", f.s3_get_url)
    return f


def _cliente(jwt=JWT, email="teste@exemplo.invalid"):
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = jwt
        s["conta"] = {"nome": "Pessoa Teste", "email": email, "perfil": ""}
    return c


@pytest.fixture(autouse=True)
def _memoria_limpa(monkeypatch):
    monkeypatch.setattr(obs_store, "_linhas", lambda: [])              # o banco da Gridco: nenhum teste vai
    obs_store._estado.update(lista=None, lido=0.0)
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()
    yield
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()


# ── o detalhe da OS (o card do Histórico) ──────────────────────────────────────────────────────────────────────────
def test_o_detalhe_da_os_vai_em_duas_levas_com_os_mesmos_pedidos(falso):
    d = api.get_os_detalhes(WID)
    # os mesmos 5 pedidos de antes: tarefas, subtarefas e cabeçalho JUNTOS; depois solicitação e OS pai juntas
    assert falso.n == {api.RPC_WO_TASKS: 1, api.RPC_WO_FORMIT: 1, api.RPC_WO_DETAILS: 2, api.RPC_REQ_LIST: 1}
    assert falso.pico == 3
    assert (d["folio"], d["os_pai"], d["os_pai_id"], d["solicitacao"]) == (15001, "12500", PAI, "")
    assert (d["responsavel"], d["criado_por"], d["code"]) == ("Pessoa Teste", "Pessoa Teste", "TST-CAB1")
    assert [s["descricao"] for s in d["subtarefas"]] == ["Item 1", "Item 2"] and d["notas"] == "nota da OS"


def test_leitura_enxuta_pula_a_solicitacao_e_a_os_pai(falso):
    """A tela de um chamado e a conferência antes de gravar o ticket não mostram os dois: 2 pedidos a menos. É por
    contexto, e não por argumento, porque os testes do oem trocam a função por `lambda wid: ...`."""
    with api.enxuta("vinculos"):
        d = api.get_os_detalhes(WID)
    assert falso.n == {api.RPC_WO_TASKS: 1, api.RPC_WO_FORMIT: 1, api.RPC_WO_DETAILS: 1}
    assert (d["os_pai"], d["solicitacao"], d["os_pai_id"]) == ("", "", PAI)
    falso.n.clear()
    api.get_os_detalhes(WID)                                         # fora do `with`, a leitura volta a ser inteira
    assert falso.n[api.RPC_REQ_LIST] == 1 and falso.n[api.RPC_WO_DETAILS] == 2


def test_a_contagem_dos_anexos_nao_paga_a_url_de_cada_foto(falso):
    cli = _cliente()
    r = cli.get("/os/os/%d/anexos" % WID)
    # 2 fotos da subtarefa; na OS, a foto0 repete a da subtarefa e conta só o doc.pdf: o número de antes
    assert r.get_json() == {"sub": 2, "os": 1}
    assert falso.s3 == 0
    # a lista (o clique nos anexos) continua com a URL de cada arquivo, para a galeria abrir
    j = cli.get("/os/api/os/%d/anexos-lista" % WID).get_json()
    assert falso.s3 == 3 and j


# ── Acompanhamento de chamados ─────────────────────────────────────────────────────────────────────────────────────
def _linha(i, folio, status=1, data_fim=""):
    return {"id": i, "folio": str(folio), "cliente": "Cliente Teste", "usina": "Usina Teste", "ativo": "Inversor 1.1",
            "tipo": "Inversor", "tipo_tarefa": "Administrativa", "note": "",
            "descricao": "[Inversor 1.1] - Acompanhamento de chamado Marca", "status_id": status,
            "status": api.WO_STATUS.get(status), "data": "2026-10-01T12:00:00", "data_fim": data_fim,
            "atribuido_a": "", "id_atribuido": None}


@pytest.fixture
def quadro(monkeypatch):
    """O quadro com 2 abertas e 1 concluída (que aparece: fechou há poucos dias). Conta o que vai ao Fracttal."""
    lido = {"listas": 0, "tickets": [], "detalhes": []}
    fechou = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 3 * 86400))

    def listar(**k):
        lido["listas"] += 1
        return [_linha(1, 9103), _linha(2, 9104), _linha(3, 9105, status=3, data_fim=fechou)]

    def tickets(ids):
        lido["tickets"].append(sorted(ids))
        return {i: "TK-%d" % i for i in ids}

    def detalhe(wid):
        lido["detalhes"].append(wid)
        return {"folio": 9100 + wid + 2, "subtarefas": [], "notas": ""}
    monkeypatch.setattr(api, "list_chamados", listar)
    monkeypatch.setattr(api, "tickets_os3_em_massa", tickets)
    monkeypatch.setattr(api, "get_os_detalhes", detalhe)
    return lido


def test_atualizar_o_quadro_nao_rele_o_ticket_da_concluida(quadro):
    cli = _cliente()
    assert cli.get("/os/chamados/acompanhamento").status_code == 200
    assert quadro["tickets"] == [[1, 2, 3]]
    h = cli.get("/os/chamados/acompanhamento?atualizar=1").get_data(as_text=True)
    assert quadro["listas"] == 2 and quadro["tickets"][-1] == [1, 2]     # a concluída (3) veio da memória
    assert "TK-3" in h                                                    # e continua no quadro
    # é POR PESSOA: quem entra com outro login lê tudo de novo (a cópia de um nunca aparece para outro)
    _cliente(OUTRO_JWT, "outra@exemplo.invalid").get("/os/chamados/acompanhamento")
    assert quadro["tickets"][-1] == [1, 2, 3]


def test_gravar_o_ticket_tira_a_os_da_memoria(quadro):
    cli = _cliente()
    cli.get("/os/chamados/acompanhamento")
    rotas_acomp._esquecer(3)
    cli.get("/os/chamados/acompanhamento")
    assert quadro["listas"] == 2 and quadro["tickets"][-1] == [1, 2, 3]


def test_a_tela_de_um_chamado_com_o_quadro_vencido_nao_rele_os_tickets(quadro):
    cli = _cliente()
    cli.get("/os/chamados/acompanhamento")
    with rotas._MEMO_LOCK:                                                # passaram os 3 min do quadro
        for k, (t, v) in list(rotas._MEMO.items()):
            rotas._MEMO[k] = (t - 1000, v)
    r = cli.get("/os/chamados/acompanhamento/9104")
    assert r.status_code == 200 and 'data-folio="9104"' in r.get_data(as_text=True)
    assert quadro["tickets"] == [[1, 2, 3]]                               # só os da 1ª visita ao quadro
    assert quadro["listas"] == 2 and quadro["detalhes"] == [2]            # a lista de novo, e o detalhe uma vez só


def test_leitura_com_a_sessao_morta_nao_fica_na_memoria(monkeypatch):
    """A listagem engole o erro de cada página e devolve vazio. Um quadro vazio guardado ficaria 3 min para a pessoa,
    mesmo depois de ela entrar de novo: a leitura com a sessão morta volta ao login e não é guardada."""
    def listar(**k):
        api._clear_jwt()                                                  # o Fracttal disse USER_NOT_LOGIN
        return []
    monkeypatch.setattr(api, "list_chamados", listar)
    monkeypatch.setattr(api, "tickets_os3_em_massa", lambda ids: {})
    r = _cliente().get("/os/chamados/acompanhamento")
    assert r.status_code == 302 and "/os/login" in r.headers["Location"]
    assert not [k for k in rotas._MEMO if isinstance(k, tuple) and str(k[0]).startswith("acomp")]

"""O card da OS começa a ser lido quando o mouse PARA em cima do cartão (Levi, 09/10/2026: "teria como utilizarmos essas
requisições de forma mais inteligente?"): o Quadro da equipe da Engenharia do Nexus e o Acompanhamento de chamados pedem
o detalhe por trás (`rotas.preparar`), e o clique pega a leitura pronta (`rotas.preparado`), uma vez só.

Fracttal FALSO (cada pedido é contado; nenhum vai à rede). Nomes e números de mentira: o repositório é público."""
import sys
from pathlib import Path

import pytest

from nexus.torres.oscreator import ponte

pytest.importorskip("PyQt6")          # o clone importa o steps/ui.py do OS Creator ao montar a tela de Engenharia
if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
import chamados_obs_store as obs_store  # noqa: E402
from os_web import criar_app, rotas, rotas_acomp  # noqa: E402

JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira
WID = 9201
RAIZ = Path(__file__).resolve().parent.parent


class Fracttal:
    """Responde ao que o card pede, conta os pedidos e anota com a sessão de quem foram feitos."""

    def __init__(self):
        self.n, self.jwt = {}, []

    def rpc(self, metodo, params, timeout=45):
        self.n[metodo] = self.n.get(metodo, 0) + 1
        self.jwt.append(api._read_jwt())
        if metodo == api.RPC_WO_TASKS:
            return {"data": [{"id": 1, "id_work_order_task": 1, "wo_folio": 15201, "tasks_description": "Preventiva",
                              "tasks_types_main_description": "Preventiva", "items_description": "Cabine 1 { TST-CAB1 }",
                              "code_item": "TST-CAB1", "personnel_description": "Pessoa Teste",
                              "id_status_work_order": 1, "note": ""}]}
        if metodo == api.RPC_WO_FORMIT:
            return {"data": []}
        if metodo == api.RPC_WO_DETAILS:
            return {"data": [{"id": WID, "labels": [], "created_by": "Pessoa Teste"}]}
        if metodo == api.RPC_REQ_LIST:
            return {"data": []}
        raise AssertionError("pedido que o card não faz: " + metodo)

    def leituras(self):
        """Quantas vezes o detalhe foi lido (o 1º pedido de cada leitura é o das tarefas)."""
        return self.n.get(api.RPC_WO_TASKS, 0)


@pytest.fixture
def fracttal(monkeypatch):
    f = Fracttal()
    monkeypatch.setattr(api, "_rpc_call", f.rpc)
    return f


@pytest.fixture(autouse=True)
def _limpo(monkeypatch):
    monkeypatch.setattr(obs_store, "_linhas", lambda: [])              # o banco da Gridco: nenhum teste vai
    obs_store._estado.update(lista=None, lido=0.0)

    def zerar():
        _esperar()
        with rotas._PREPARO_LOCK:
            rotas._PREPARO.clear()
            rotas._PREPARO_PEDIDOS.clear()
        with rotas._MEMO_LOCK:
            rotas._MEMO.clear()
    zerar()
    yield
    zerar()


def _esperar():
    """As leituras por trás em curso terminam (no servidor, quem espera é o clique)."""
    with rotas._PREPARO_LOCK:
        futuros = [f for _t, f in rotas._PREPARO.values()]
    for f in futuros:
        try:
            f.result(timeout=10)
        except Exception:      # noqa: BLE001 — o teste confere o efeito
            pass


def _cliente(app=None, email="teste@exemplo.invalid"):
    c = (app or criar_app(segredo="teste", testing=True)).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Pessoa Teste", "email": email, "perfil": ""}
    return c


def _card(cli):
    r = cli.get("/os/os/%d?parcial=1&status=Em+Processo" % WID)
    assert r.status_code == 200
    return r


# ── o card da OS (Quadro da equipe da Engenharia) ─────────────────────────────────────────────────────────────────
def test_mouse_parado_le_por_tras_e_o_clique_pega_a_leitura_uma_vez(fracttal):
    cli = _cliente()
    r = cli.get("/os/api/os/%d/preparar" % WID)
    assert r.status_code == 202 and r.get_json() == {"pedido": True}
    _esperar()
    assert fracttal.leituras() == 1
    _card(cli)
    assert fracttal.leituras() == 1                                       # o clique não foi ao Fracttal
    _card(cli)
    assert fracttal.leituras() == 2                                       # uma vez só: o próximo lê de novo


def test_a_leitura_por_tras_usa_a_sessao_da_pessoa(fracttal):
    _cliente().get("/os/api/os/%d/preparar" % WID)
    _esperar()
    assert fracttal.jwt and set(fracttal.jwt) == {JWT}


def test_o_mesmo_cartao_nao_pede_duas_vezes(fracttal):
    cli = _cliente()
    assert cli.get("/os/api/os/%d/preparar" % WID).get_json() == {"pedido": True}
    assert cli.get("/os/api/os/%d/preparar" % WID).get_json() == {"pedido": False}
    _esperar()
    assert fracttal.leituras() == 1


def test_leitura_mais_velha_que_30_s_nao_vale(fracttal):
    cli = _cliente()
    cli.get("/os/api/os/%d/preparar" % WID)
    _esperar()
    with rotas._PREPARO_LOCK:
        for k, (t, f) in list(rotas._PREPARO.items()):
            rotas._PREPARO[k] = (t - rotas.PREPARO_S - 1, f)
    _card(cli)
    assert fracttal.leituras() == 2


def test_teto_por_pessoa_e_no_total(fracttal):
    """Passar o mouse pelo quadro inteiro não vira rajada no Fracttal: 6 por pessoa e 12 no total, por minuto."""
    a, b, c = _cliente(email="a@exemplo.invalid"), _cliente(email="b@exemplo.invalid"), _cliente(email="c@exemplo.invalid")
    pedidos_a = [a.get("/os/api/os/%d/preparar" % (100 + i)).get_json()["pedido"] for i in range(rotas.PREPARO_PESSOA_MIN + 1)]
    assert pedidos_a == [True] * rotas.PREPARO_PESSOA_MIN + [False]
    for i in range(rotas.PREPARO_TOTAL_MIN - rotas.PREPARO_PESSOA_MIN):
        assert b.get("/os/api/os/%d/preparar" % (200 + i)).get_json()["pedido"] is True
    assert c.get("/os/api/os/300/preparar").get_json()["pedido"] is False   # o total do minuto acabou
    _esperar()
    assert fracttal.leituras() == rotas.PREPARO_TOTAL_MIN


def test_gravar_na_os_joga_fora_a_leitura_de_antes(fracttal):
    """Toda rota POST com o id da OS (concluir, nota, responsável...) tira o que o mouse parado leu antes dela."""
    app = criar_app(segredo="teste", testing=True)
    app.add_url_rule("/os/api/os/<int:wid>/teste-gravar", "teste_gravar", lambda wid: "ok", methods=["POST"])
    cli = _cliente(app)
    cli.get("/os/api/os/%d/preparar" % WID)
    _esperar()
    cli.post("/os/api/os/%d/teste-gravar" % WID)
    _card(cli)
    assert fracttal.leituras() == 2


# ── a tela de um chamado (Acompanhamento de chamados) ──────────────────────────────────────────────────────────────
@pytest.fixture
def chamados(monkeypatch):
    lido = {"detalhes": [], "enxuta": []}

    def listar(**k):
        return [{"id": WID, "folio": "9103", "cliente": "Cliente Teste", "usina": "Usina Teste", "ativo": "Inversor 1.1",
                 "tipo": "Inversor", "tipo_tarefa": "Administrativa", "note": "",
                 "descricao": "[Inversor 1.1] - Acompanhamento de chamado Marca", "status_id": 1,
                 "status": api.WO_STATUS.get(1), "data": "2026-10-01T12:00:00", "data_fim": "",
                 "atribuido_a": "", "id_atribuido": None}]

    def detalhe(wid):
        lido["detalhes"].append(wid)
        lido["enxuta"].append("vinculos" in api._ENXUTA.get())
        return {"folio": 9103, "subtarefas": [], "notas": ""}
    monkeypatch.setattr(api, "list_chamados", listar)
    monkeypatch.setattr(api, "tickets_os3_em_massa", lambda ids: {i: "TK-%d" % i for i in ids})
    monkeypatch.setattr(api, "get_os_detalhes", detalhe)
    return lido


def test_o_chamado_pega_a_leitura_enxuta_que_o_mouse_pediu(chamados):
    cli = _cliente()
    cli.get("/os/chamados/acompanhamento")                                # o quadro: o id de cada nº
    r = cli.get("/os/chamados/acompanhamento/9103/preparar")
    assert r.status_code == 202 and r.get_json() == {"pedido": True}
    _esperar()
    assert chamados["detalhes"] == [WID] and chamados["enxuta"] == [True]  # sem solicitação nem OS pai
    r = cli.get("/os/chamados/acompanhamento/9103")
    assert r.status_code == 200 and 'data-folio="9103"' in r.get_data(as_text=True)
    assert chamados["detalhes"] == [WID]                                  # o clique não foi ao Fracttal


def test_sem_o_quadro_lido_o_chamado_nao_prepara(chamados):
    """Sem o id que o quadro da própria pessoa leu, nada: o clique lê como sempre."""
    assert _cliente().get("/os/chamados/acompanhamento/9103/preparar").get_json() == {"pedido": False}
    assert chamados["detalhes"] == []


def test_gravar_o_ticket_joga_fora_a_leitura_de_antes(chamados):
    cli = _cliente()
    cli.get("/os/chamados/acompanhamento")
    cli.get("/os/chamados/acompanhamento/9103/preparar")
    _esperar()
    rotas_acomp._esquecer(WID)                                            # o que a gravação do ticket chama
    cli.get("/os/chamados/acompanhamento/9103")
    assert chamados["detalhes"] == [WID, WID]


# ── o lado do navegador ──────────────────────────────────────────────────────────────────────────────────────────
def test_os_dois_quadros_pedem_com_o_mouse_parado_250_ms():
    componente = (RAIZ / "nexus/torres/oscreator/templates/oscreator/card_os_abrir.html").read_text(encoding="utf-8")
    assert "'/os/api/os/' + encodeURIComponent(wid) + '/preparar'" in componente and ", 250)" in componente
    assert "preparar: preparar, prepararAoParar: prepararAoParar" in componente
    assert "delete pedidos[wid];" in componente                          # aberta: o próximo mouse parado lê de novo
    equipe = (RAIZ / "nexus/torres/engenharia/templates/engenharia/equipe.html").read_text(encoding="utf-8")
    assert "NexusOsCard.prepararAoParar(c, o.wid)" in equipe
    acomp = Path(ponte.RAIZ_CLONE, "os_web", "static", "acomp.js").read_text(encoding="utf-8")
    assert 'card.getAttribute("href") + "/preparar"' in acomp and "setTimeout(preparar, 250)" in acomp

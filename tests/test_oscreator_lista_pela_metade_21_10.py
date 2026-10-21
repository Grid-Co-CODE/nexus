"""A lista do Fracttal pela metade não vai para a tela (21/10/2026, chat de desempenho).

Raio-X do servidor às 14:36 de 21/10: "Pedido preso 24 vezes em 24 h", o último um GET /os/historico de 45 s esperando o
Fracttal (`api._rpc_chamar`); 45 s é o tempo-limite do pedido. A busca da lista (`api.list_minhas_os`, que serve o
Histórico e o quadro do Acompanhamento de chamados) engolia o erro de cada página e de cada lote das tarefas: sem a 1ª
página, a lista saía VAZIA, sem aviso, e ficava guardada; sem uma do meio, sumiam até 200 OS. E a lista vazia de "Todos"
fazia cada pessoa buscar a dela inteira dali em diante (o total dela não batia com o 0 guardado): mais carga no Fracttal.
Agora a busca em que o Fracttal não entregou algum pedido falha inteira: nada é guardado, e a tela fica com a lista
anterior (com a hora dela) ou diz que o Fracttal não respondeu. O Fracttal aqui é de mentira; nada sai da máquina."""
import sys

import pytest

from nexus.torres.oscreator import ponte

pytest.importorskip("PyQt6")          # o clone importa o steps/ui.py do OS Creator ao montar a tela de Engenharia
if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
import chamados_obs_store as obs_store  # noqa: E402
from os_web import criar_app, rotas, rotas_acomp  # noqa: E402
from os_web import historico_store as HS  # noqa: E402

JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira
TEMPO = ("Erro de conexão (RPC %s): HTTPSConnectionPool(host='app.fracttal.com', port=443): Read timed out. "
         "(read timeout=45)")
AVISO = "pela metade"                  # o que a tela diz quando o Fracttal não entregou a lista inteira


def _w(i):
    """Uma linha crua da listagem de OS do Fracttal (o que o `_shape_wo_row` lê). OS de acompanhamento, para servir
    também ao quadro do Acompanhamento de chamados."""
    return {"id": i, "wo_folio": str(10000 + i), "creation_date": "2026-10-21T08:%02d:00" % (i % 60),
            "id_status_work_order": 1, "tasks_descriptions": "[Inversor 1.1] - Acompanhamento de chamado Marca",
            "labels": [{"id": 7, "description": "CHAMADOS"}]}


class _Fracttal:
    """650 OS em 4 páginas de 200; cada pedido é anotado. `sem_resposta` = as páginas que estouram o tempo-limite;
    `tarefas_sem_resposta`, os lotes das tarefas; `sessao_morta`, a página que falha porque a sessão caiu."""

    def __init__(self, total=650):
        self.total, self.sem_resposta, self.tarefas_sem_resposta, self.sessao_morta = total, set(), False, False
        self.pedidos = []

    def rpc(self, metodo, params, timeout=45):
        self.pedidos.append(metodo)
        if metodo == api.RPC_WO_LIST:
            if params["page"] in self.sem_resposta:
                if self.sessao_morta:
                    raise api.SessionExpired("Sua sessão do Fracttal expirou ou foi encerrada. Faça login de novo.")
                raise api.FracttalError(TEMPO % metodo)
            ini = params["start"]
            fim = min(ini + params["limit"], self.total)
            return {"total": self.total, "data": [_w(i) for i in range(ini + 1, fim + 1)]}
        if metodo == api.RPC_WO_TASKS:
            if self.tarefas_sem_resposta:
                raise api.FracttalError(TEMPO % metodo)
            ids = params["filter"][0]["value"]
            return {"data": [{"id_work_order": i, "tasks_types_main_description": "Administrativa"} for i in ids]}
        return {"data": [], "total": 0}


@pytest.fixture
def fr(monkeypatch):
    import requests

    def sem_rede(*a, **k):                    # a cota do Fracttal é da empresa: aqui nada sai da máquina
        raise AssertionError("o teste tentou ir à rede")
    monkeypatch.setattr(requests.Session, "request", sem_rede)
    f = _Fracttal()
    monkeypatch.setattr(api, "_rpc_call", f.rpc)
    monkeypatch.setattr(api, "get_labels", lambda *a, **k: [{"id": 7, "description": "CHAMADOS"}])
    monkeypatch.setattr(api, "get_pessoas_contas", lambda *a, **k: {"pessoas": [], "eu": None})
    monkeypatch.setattr(api, "_code_to_loc", lambda *a, **k: {})
    monkeypatch.setattr(api, "_read_asset_cache", lambda *a, **k: [])
    monkeypatch.setattr(api, "tickets_os3_em_massa", lambda ids: {})
    monkeypatch.setattr(obs_store, "_linhas", lambda: [])              # o banco da Gridco: nenhum teste vai
    obs_store._estado.update(lista=None, lido=0.0)
    monkeypatch.setattr(rotas, "_em_segundo_plano", lambda fn: None)   # sem renovação por trás: só o que a tela faz
    monkeypatch.setattr(rotas_acomp, "_em_segundo_plano", lambda fn: None)
    relogio = {"t": 1000.0}
    monkeypatch.setattr(HS, "_relogio", lambda: relogio["t"])
    f.relogio = relogio
    HS.limpar()
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()
    yield f
    HS.limpar()
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()


def _cliente(email="pessoa1@exemplo.invalid"):
    c = criar_app(segredo="teste", testing=False).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Pessoa Teste", "email": email, "perfil": "ADMINISTRATOR"}
    return c


def _tela(c, url):
    r = c.get(url)
    assert r.status_code == 200
    return r.get_data(as_text=True)


# ── a busca ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_com_tudo_respondido_a_lista_vem_inteira(fr):
    out = api.list_minhas_os(modo="criadas", id_account="TODOS")
    assert len(out) == 650 and {d["tipo_tarefa"] for d in out} == {"Administrativa"}


def test_sem_a_primeira_pagina_a_busca_falha_em_vez_de_vir_vazia(fr):
    fr.sem_resposta = {1}
    with pytest.raises(api.FracttalError) as e:
        api.list_minhas_os(modo="criadas", id_account="TODOS")
    assert AVISO in str(e.value) and "a tempo" in str(e.value)
    assert fr.pedidos == [api.RPC_WO_LIST]                 # sem a 1ª página, nem pede as outras (a cota é da empresa)


def test_sem_uma_pagina_do_meio_nao_somem_200_os(fr):
    fr.sem_resposta = {2}
    with pytest.raises(api.FracttalError) as e:
        api.list_minhas_os(modo="criadas", id_account="TODOS")
    assert AVISO in str(e.value)
    assert api.RPC_WO_TASKS not in fr.pedidos              # nem lê as tarefas de uma lista que não vai à tela


def test_sem_um_lote_das_tarefas_tambem(fr):
    """O lote que falha deixava 130 OS sem o tipo e as datas; fechadas, elas ficavam assim na memória (o `meta_ja` não
    as relê), e a Visão COS, que filtra pelo tipo, as escondia."""
    fr.tarefas_sem_resposta = True
    with pytest.raises(api.FracttalError) as e:
        api.list_minhas_os(modo="criadas", id_account="TODOS")
    assert AVISO in str(e.value)


def test_a_sessao_que_caiu_numa_pagina_continua_sessao_caida(fr):
    """A sessão morta numa página do meio leva ao login, como na 1ª (e não vira uma lista sem 200 OS)."""
    fr.sem_resposta, fr.sessao_morta = {3}, True
    with pytest.raises(api.SessionExpired):
        api.list_minhas_os(modo="criadas", id_account="TODOS")


# ── o Histórico ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_historico_nao_guarda_a_lista_vazia_e_avisa(fr):
    fr.sem_resposta = {1}
    h = _tela(_cliente(), "/os/historico?modo=cos")
    assert AVISO in h and "10001" not in h
    assert not HS._LISTAS                                  # nada guardado: a próxima visita busca de novo
    fr.sem_resposta = set()                                # o Fracttal volta
    h = _tela(_cliente("pessoa2@exemplo.invalid"), "/os/historico?modo=cos")
    assert "10001" in h and AVISO not in h
    # a lista de "Todos" segue uma só: sem a vazia guardada, ninguém passa a buscar a sua inteira
    assert [k[1] for k in HS._LISTAS] == ["TODOS"]


def test_o_atualizar_que_falha_fica_com_a_lista_anterior(fr):
    c = _cliente()
    assert "10001" in _tela(c, "/os/historico?modo=cos")
    fr.relogio["t"] += HS.INTEIRA_S + 1                    # o ↻ depois de 10 min busca a lista inteira
    fr.sem_resposta = {2}
    h = _tela(c, "/os/historico?modo=cos&atualizar=1")
    assert AVISO in h and "10001" in h and "10650" in h    # o aviso e a lista que já estava, inteira, com a hora dela
    assert len(next(iter(HS._LISTAS.values())).linhas) == 650


# ── o quadro do Acompanhamento de chamados ──────────────────────────────────────────────────────────────────────────
URL_ACOMP = "/os/chamados/acompanhamento"


def _quadro_na_memoria() -> bool:
    return any(isinstance(k, tuple) and k and k[0] in ("acomp", "acomp_linhas") for k in rotas._MEMO)


def test_o_quadro_nao_guarda_a_lista_vazia_por_30_min(fr):
    fr.sem_resposta = {1}
    h = _tela(_cliente(), URL_ACOMP)
    assert AVISO in h and not _quadro_na_memoria()
    fr.sem_resposta = set()
    assert "10001" in _tela(_cliente(), URL_ACOMP)


def test_o_atualizar_do_quadro_que_falha_fica_com_o_quadro_anterior(fr):
    c = _cliente()
    assert "10001" in _tela(c, URL_ACOMP)
    fr.sem_resposta = {2}
    h = _tela(c, URL_ACOMP + "?atualizar=1")
    assert AVISO in h and "10001" in h and "10650" in h

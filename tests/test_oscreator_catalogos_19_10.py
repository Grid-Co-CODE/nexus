"""Os catálogos do Fracttal iguais para todos, guardados (19/10/2026, superplano do OS Creator; Levi: "todas as buscas são
necessárias?"). O pessoal ativo, as etiquetas, os motivos de cancelamento e as OS recentes da tinta dos Ativos eram
relidos a cada tela e a cada clique, por cada pessoa; o catálogo de ~22 mil ativos era decodificado do disco a cada
chamada (26 lugares chamam) e recarregado do Fracttal (~110 pedidos) por cada pedido que o achava vencido ao mesmo tempo;
e o `_code_to_loc`, chamado por linha do Histórico, tentava recarregar o catálogo de novo a cada linha quando a recarga
falhava. Nada sai da máquina."""
import json
import sys
import threading
import time

import pytest

from nexus.torres.oscreator import ponte

pytest.importorskip("PyQt6")          # o clone importa o steps/ui.py do OS Creator ao montar a tela de Engenharia
if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
from os_web import criar_app, rotas  # noqa: E402

JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira


@pytest.fixture(autouse=True)
def _limpo(monkeypatch):
    import requests

    def sem_rede(*a, **k):
        raise AssertionError("o teste tentou ir à rede")
    monkeypatch.setattr(requests.Session, "request", sem_rede)
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()
    _APP.clear()
    yield
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()
    _APP.clear()


_APP = {}


def _cliente(email):
    """Um navegador de cada pessoa no MESMO app, como no servidor (um app de teste novo começa sem os catálogos)."""
    app = _APP.get("app")
    if app is None:
        app = _APP["app"] = criar_app(segredo="teste", testing=True)
    c = app.test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Pessoa Teste", "email": email, "perfil": "ADMINISTRATOR"}
    return c


def test_o_pessoal_e_as_os_recentes_uma_vez_para_todos(monkeypatch):
    lidos = {"pessoal": 0, "recentes": 0}

    def pessoal():
        lidos["pessoal"] += 1
        return [{"code": "1", "name": "Beltrano", "id_personnel": 2}, {"code": "2", "name": "Ana", "id_personnel": 1}]

    def recentes(dias):
        lidos["recentes"] += 1
        return ["TST-INV11"]
    monkeypatch.setattr(api, "get_responsaveis", pessoal)
    monkeypatch.setattr(api, "codigos_os_recentes", recentes)
    for e in ("a@exemplo.invalid", "b@exemplo.invalid"):
        c = _cliente(e)
        assert [p["name"] for p in c.get("/os/api/responsaveis").get_json()["pessoas"]] == ["Ana", "Beltrano"]
        assert c.get("/os/api/ativos/recentes").get_json()["codes"] == ["TST-INV11"]
    assert lidos == {"pessoal": 1, "recentes": 1}


def test_o_erro_do_fracttal_nao_fica_guardado(monkeypatch):
    vezes = []

    def pessoal():
        vezes.append(1)
        if len(vezes) == 1:
            raise api.FracttalError("HTTP 429")
        return [{"code": "1", "name": "Ana", "id_personnel": 1}]
    monkeypatch.setattr(api, "get_responsaveis", pessoal)
    with pytest.raises(api.FracttalError):
        rotas.responsaveis_fracttal()
    assert rotas.responsaveis_fracttal()[0]["name"] == "Ana" and len(vezes) == 2


@pytest.fixture
def catalogo(tmp_path, monkeypatch):
    arq = tmp_path / "assets_cache.json"
    monkeypatch.setattr(api, "ASSETS_CACHE", str(arq))
    monkeypatch.setattr(api, "_ASSETS_MEM", {"chave": None, "c": None})
    monkeypatch.setattr(api, "_seed_cache", lambda: None)

    def gravar(ativos, ts=None):
        arq.write_text(json.dumps({"ts": ts or time.time(), "ver": api._CACHE_VER, "assets": ativos}), encoding="utf-8")
    return gravar


def test_o_catalogo_e_lido_do_disco_uma_vez_por_versao_e_entregue_em_copia(catalogo, monkeypatch):
    catalogo([{"id": 1, "code": "TST-INV11", "usina": "Usina", "cliente": "Cliente", "tipo": "Inversor",
               "description": "Usina Inversor"}])
    lidos = []
    original = json.load
    monkeypatch.setattr(api.json, "load", lambda f: lidos.append(1) or original(f))
    a = api._read_asset_cache()
    a[0]["code"] = "MEXIDO"                                       # quem pediu mexe na cópia dele
    b = api._read_asset_cache()
    assert b[0]["code"] == "TST-INV11" and lidos == [1]


def test_o_resumo_do_catalogo_nao_decodifica_o_arquivo_de_novo(catalogo, monkeypatch):
    """A tela inicial e a de Ativos dizem quantos ativos e de quando é o catálogo (`assets_cache_info`): até 20/10/2026
    ele decodificava o arquivo inteiro (10,5 MB) a cada chamada; agora usa o mesmo decodificado do `_read_asset_cache`."""
    catalogo([{"id": i, "code": "TST-%d" % i} for i in range(3)], ts=time.time() - 3600)
    lidos = []
    original = json.load
    monkeypatch.setattr(api.json, "load", lambda f: lidos.append(1) or original(f))
    info = api.assets_cache_info()
    assert info["n"] == 3 and not info["expirado"] and 0.9 < info["idade_h"] < 1.1
    api.assets_cache_info()
    assert len(api._read_asset_cache()) == 3 and lidos == [1]            # uma decodificação para os três
    catalogo([{"id": 9, "code": "TST-9"}])                               # o arquivo mudou: lido de novo
    assert api.assets_cache_info()["n"] == 1 and lidos == [1, 1]


def test_uma_recarga_do_fracttal_por_vez(catalogo, monkeypatch):
    catalogo([{"id": 1, "code": "VELHO"}], ts=time.time() - api.ASSETS_TTL - 10)     # vencido
    recargas = []

    def recarregar():
        recargas.append(1)
        time.sleep(0.3)
        return [{"id": 2, "code": "NOVO", "usina": "", "cliente": "", "tipo": "", "description": ""}]
    monkeypatch.setattr(api, "get_assets", recarregar)
    saidas = []
    ts = [threading.Thread(target=lambda: saidas.append(api.load_assets_cached())) for _ in range(3)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(recargas) == 1 and all(s[0]["code"] == "NOVO" for s in saidas)


def test_sem_catalogo_o_code_to_loc_nao_tenta_de_novo_a_cada_linha(monkeypatch):
    tentativas = []

    def falha():
        tentativas.append(1)
        raise api.FracttalError("HTTP 429")
    monkeypatch.setattr(api, "load_assets_cached", falha)
    monkeypatch.setattr(api, "_code_loc", {})
    monkeypatch.setattr(api, "_CODE_LOC_TENTOU", [0.0])
    for _ in range(50):                                           # 50 linhas do Histórico
        assert api._code_to_loc() == {}
    assert len(tentativas) == 1


def test_a_os_pelo_numero_num_pedido_so(monkeypatch):
    pedidos = []

    def rpc(metodo, params, timeout=45):
        pedidos.append(params.get("id_status_work_order"))
        return {"data": [{"id": 77, "wo_folio": "13189", "id_status_work_order": 3}]}
    monkeypatch.setattr(api, "_rpc_call", rpc)
    assert api._wo_id_por_folio("13189") == 77 and pedidos == [None]          # eram até 4, um por status


def test_a_os_pelo_numero_sem_achar_varre_os_status_como_antes(monkeypatch):
    pedidos = []

    def rpc(metodo, params, timeout=45):
        st = params.get("id_status_work_order")
        pedidos.append(st)
        return {"data": [{"id": 5, "wo_folio": "9"}]} if st == 4 else {"data": []}
    monkeypatch.setattr(api, "_rpc_call", rpc)
    assert api._wo_id_por_folio("9") == 5 and pedidos == [None, 1, 2, 3, 4]



def test_os_tipos_da_fila_e_as_classificacoes_da_solicitacao_nao_se_misturam(monkeypatch):
    """20/10/2026, o programador do PCM: "não consigo solicitar pelo nexus porque a classificação 1 não abre opção de
    preencher". A Fila guarda o Tipo de tarefa e as Classificações da OS (`get_tipos_classif`: tipos, c1, c2) e, desde
    19/10, a Solicitação guardava o Grupo e as Classificações da solicitação (`get_request_types`: grupo, classif1,
    classif2) na MESMA chave: quem abria a Fila primeiro deixava a Solicitação sem nenhuma opção por 30 min (e o
    contrário esvaziava a Fila)."""
    from os_web import rotas_solic as RS
    monkeypatch.setattr(api, "get_tipos_classif", lambda: {"tipos": [{"id": 1, "description": "Corretiva"}],
                                                           "c1": [{"id": 7, "description": "Programada"}], "c2": []})
    monkeypatch.setattr(api, "get_request_types", lambda: {"grupo": [{"id": 3, "description": "Grupo Teste"}],
                                                           "classif1": [{"id": 9, "description": "Classe Teste"}],
                                                           "classif2": []})
    monkeypatch.setattr(api, "load_assets_cached", lambda force=False: [])
    monkeypatch.setattr(api, "get_responsaveis", lambda: [])
    c = _cliente("pcm@exemplo.invalid")
    with c.application.test_request_context():
        assert RS._tipos()["c1"]                                         # a Fila abriu primeiro
    html = c.get("/os/solicitacao").get_data(as_text=True)
    assert '<option value="9">Classe Teste</option>' in html and '<option value="3">Grupo Teste</option>' in html
    with c.application.test_request_context():
        assert RS._tipos()["tipos"] and RS._tipos()["c1"]                # e a Fila segue com os dela


def test_a_classificacao_vazia_nao_fica_guardada(monkeypatch):
    """O Fracttal que devolve a lista de Classificação 1 vazia (a sessão de alguém sem a permissão) não deixa a tela
    vazia para todos: só a lista com opções é guardada."""
    lidas = []

    def tipos():
        lidas.append(1)
        return {"grupo": [], "classif1": [] if len(lidas) == 1 else [{"id": 9, "description": "Classe Teste"}],
                "classif2": []}
    monkeypatch.setattr(api, "get_request_types", tipos)
    monkeypatch.setattr(api, "load_assets_cached", lambda force=False: [])
    monkeypatch.setattr(api, "get_responsaveis", lambda: [])
    c = _cliente("pcm@exemplo.invalid")
    assert "Classe Teste" not in c.get("/os/solicitacao").get_data(as_text=True)
    assert "Classe Teste" in c.get("/os/solicitacao").get_data(as_text=True)
    c.get("/os/solicitacao")
    assert len(lidas) == 2                                               # a lista com opções, sim, fica guardada

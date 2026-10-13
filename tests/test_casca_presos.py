"""Pedidos presos (13/10/2026, Levi: "As vezes o OS Creator Web fica em um loop infinito, isso é por causa do
fractal?"): das 16:50 às 16:53 o Nexus do servidor não respondeu nem o /saude e, de fora, não dava para ver esperando o
quê. O registro anota cada pedido em andamento; a ronda, passados 30 s, diz onde ele está preso; o administrador vê no
Início. Nada aqui espera 30 s: a idade do pedido e o relógio da ronda são dados na mão."""
import json
import logging
import threading
import time
import traceback

import pytest

from nexus.auth import setor_telas
from nexus.casca import presos

RAIZ = presos._RAIZ


def _wsgi(durante=None, quebra=False):
    def app(environ, start_response):
        if durante:
            durante()
        if quebra:
            raise RuntimeError("quebrou")
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"ok"]
    return app


def _pedido(caminho="/os/performance/criar", **extra):
    return {"REQUEST_METHOD": "GET", "PATH_INFO": caminho, **extra}


def _envelhecer(e, seq, segundos, thread=None):
    """O pedido entrou há `segundos` (e roda na `thread`, se dada)."""
    e.em_curso[seq].update(inicio=time.monotonic() - segundos, inicio_epoca=time.time() - segundos)
    if thread is not None:
        e.em_curso[seq]["thread"] = thread.ident


def _quadro(arquivo, nome, linha=""):
    return traceback.FrameSummary(arquivo, 10, nome, line=linha)


# ── o registro ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_registro_anota_sem_a_query_e_tira_quando_a_resposta_termina():
    e = presos._Estado(16, None)
    vistos = []
    reg = presos._Registro(_wsgi(durante=lambda: vistos.extend(dict(p) for p in e.em_curso.values())), e)
    resposta = reg(_pedido(QUERY_STRING="frase=recomposicao+de+string&usina=Fulano"), lambda *a: None)
    assert [(p["metodo"], p["caminho"]) for p in vistos] == [("GET", "/os/performance/criar")]
    assert "Fulano" not in json.dumps(vistos, default=str)       # a query não entra: pode levar nome de gente
    assert list(resposta) == [b"ok"] and len(e.em_curso) == 1      # a resposta ainda não fechou: segue em andamento
    resposta.close()
    assert e.em_curso == {}


def test_o_pedido_que_quebra_sai_do_registro_e_a_pre_carga_nem_entra():
    e = presos._Estado(16, None)
    with pytest.raises(RuntimeError):
        presos._Registro(_wsgi(quebra=True), e)(_pedido(), lambda *a: None)
    assert e.em_curso == {}
    vistos = []
    presos._Registro(_wsgi(durante=lambda: vistos.append(len(e.em_curso))), e)(
        _pedido("/t/campo/rondas", HTTP_X_NEXUS_PRE_CARGA="1"), lambda *a: None)
    assert vistos == [0]          # a pré-carga roda no test_client, numa thread própria, fora das do waitress


# ── onde ele está ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_rotulo_diz_quem_e_como_pela_pilha():
    api = RAIZ + "nexus/torres/oscreator/os_creator/api.py"
    rede = [_quadro("/opt/nexus/.venv/lib/python3.12/site-packages/waitress/task.py", "service"),
            _quadro(RAIZ + "nexus/torres/oscreator/os_creator/os_web/rotas.py", "performance_criar"),
            _quadro(api, "_rpc_call", "r = requests.post(RPC_PROXY_URL, headers=_rpc_headers(), json=body)"),
            _quadro("/opt/nexus/.venv/lib/python3.12/site-packages/requests/sessions.py", "send"),
            _quadro("/usr/lib/python3.12/ssl.py", "recv_into")]
    assert presos.rotulo(rede) == {"quem": "Fracttal (OS Creator)", "como": "esperando a rede",
                                   "onde": "nexus/torres/oscreator/os_creator/api.py:10 _rpc_call"}
    # o catálogo de ativos esperando as 6 threads dele
    futuros = [_quadro(api, "get_assets", "for f in as_completed(futs):"),
               _quadro("/usr/lib/python3.12/concurrent/futures/_base.py", "as_completed"),
               _quadro("/usr/lib/python3.12/threading.py", "wait")]
    assert presos.rotulo(futuros)["como"] == "esperando outra thread"
    pausa = [_quadro(RAIZ + "nexus/campo/fracttal.py", "ler", "time.sleep(esperas[tentativa])")]
    assert presos.rotulo(pausa)[("quem")] == "Fracttal (Campo)" and presos.rotulo(pausa)["como"] == "em pausa"
    # o .venv mora dentro da pasta do Nexus no servidor (/opt/nexus/.venv): os pacotes dele não são linha nossa
    venv = [_quadro(RAIZ + ".venv/lib/python3.12/site-packages/pandas/core/frame.py", "merge")]
    assert presos.rotulo([_quadro(RAIZ + "nexus/campo/visao.py", "montar", "x = juntar()")] + venv) == {
        "quem": "nexus/campo/visao.py:montar", "como": "trabalhando", "onde": "nexus/campo/visao.py:10 montar"}
    assert presos.rotulo([])["quem"] == "?"


# ── a ronda e o episódio ────────────────────────────────────────────────────────────────────────────────────────────
def _preso_no_evento(evento):
    evento.wait(20)


def test_pedido_preso_vira_episodio_com_onde_ele_esta_e_vai_ao_disco(tmp_path, caplog):
    arq = tmp_path / "casca" / "pedidos_presos.json"
    e = presos._Estado(16, arq)
    evento = threading.Event()
    t = threading.Thread(target=_preso_no_evento, args=(evento,), daemon=True)
    t.start()
    try:
        seq = e.entrar(_pedido())
        rapido = e.entrar(_pedido("/saude"))
        _envelhecer(e, seq, 40, t)
        with caplog.at_level(logging.WARNING, logger="nexus.casca.presos"):
            e.olhar()
        ep = e.episodio
        assert ep["max_presos"] == 1 and ep["max_ocupadas"] == 2 and not ep["fila_cheia"]
        reg = ep["pedidos"][seq]
        assert reg["caminho"] == "/os/performance/criar" and reg["como"] == "esperando outra thread"
        assert reg["quem"] == "tests/test_casca_presos.py:_preso_no_evento" and not reg["terminou"]
        assert rapido not in ep["pedidos"]                         # o de 0 s não é preso
        assert "Pedido preso há 40 s: GET /os/performance/criar" in caplog.text
        # gravado DURANTE o episódio: o processo reiniciado no meio não o perde
        assert json.loads(arq.read_text(encoding="utf-8"))["episodios"][0]["fim"] is None
        # olhar de novo, no mesmo lugar, não repete o aviso
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="nexus.casca.presos"):
            e.olhar()
        assert "Pedido preso" not in caplog.text
    finally:
        evento.set()
        t.join(5)
    e.sair(seq)
    e.sair(rapido)
    assert e.episodio["pedidos"][seq]["terminou"] and e.episodio["pedidos"][seq]["espera_s"] >= 40
    e.olhar(time.monotonic() + 5)
    assert e.episodio is not None                                   # 15 s sem preso para fechar
    e.olhar(time.monotonic() + presos.FIM_S + 1)
    assert e.episodio is None and len(e.historico) == 1 and e.historico[0]["fim"] is not None
    salvo = json.loads(arq.read_text(encoding="utf-8"))["episodios"]
    assert len(salvo) == 1 and salvo[0]["pedidos"][0]["caminho"] == "/os/performance/criar"
    # o boot seguinte lê o que ficou no disco
    outro = presos._Estado(16, arq)
    outro.carregar()
    assert len(outro.historico) == 1 and not outro.historico[0].get("cortado")


def test_fila_cheia_quando_todas_as_threads_estao_ocupadas():
    e = presos._Estado(2, None)
    for _ in range(2):
        _envelhecer(e, e.entrar(_pedido()), 35)
    e.olhar()
    assert e.episodio["fila_cheia"] and e.episodio["max_ocupadas"] == 2 and e.episodio["max_presos"] == 2


def test_o_episodio_aberto_quando_o_processo_caiu_volta_cortado(tmp_path):
    arq = tmp_path / "pedidos_presos.json"
    arq.write_text(json.dumps({"gravado_em": 1760385000.0, "episodios": [
        {"inicio": 1760384800.0, "fim": None, "fim_visto": 1760384990.0, "max_presos": 16, "max_ocupadas": 16,
         "threads": 16, "fila_cheia": True, "pedidos": []}]}), encoding="utf-8")
    e = presos._Estado(16, arq)
    e.carregar()
    assert e.historico[0]["fim"] == 1760384990.0 and e.historico[0]["cortado"]


# ── o que o administrador vê no Início ─────────────────────────────────────────────────────────────────────────────
def _travamento(fim_ha_s=600, duracao_s=180, cortado=False):
    fim = time.time() - fim_ha_s
    pedido = {"metodo": "GET", "caminho": "/os/performance/criar", "terminou": True, "espera_s": 170.0,
              "quem": "Fracttal (OS Creator)", "como": "esperando a rede",
              "onde": "nexus/torres/oscreator/os_creator/api.py:1093 _rpc_call"}
    ep = {"inicio": fim - duracao_s, "fim": fim, "fim_visto": fim, "max_presos": 16, "max_ocupadas": 16, "threads": 16,
          "fila_cheia": True, "pedidos": [pedido, dict(pedido, caminho="/os/api/performance/contagens")]}
    if cortado:
        ep["cortado"] = True
    return ep


def test_o_administrador_ve_o_travamento_no_cartao_da_versao(app, logado):
    e = presos._Estado(16, None)
    app.extensions[presos.CHAVE] = e
    html = logado.get("/").get_data(as_text=True)
    assert "versao-presos" in html and "Nenhum pedido preso em 24 h" in html and "gc-status--ok" in html
    e.historico.append(_travamento())
    html = logado.get("/").get_data(as_text=True)
    assert "gc-status--critico" in html and "Travou 1 vez em 24 h" in html
    assert "e durou 3 min: até 16 pedidos presos juntos, com as 16 threads ocupadas; todos em Fracttal (OS Creator), " \
           "esperando a rede." in html
    assert "GET /os/api/performance/contagens (2 min 50 s, nexus/torres/oscreator/os_creator/api.py:1093 _rpc_call)" in html
    # o de mais de 24 h sai da conta; o cortado pelo restart diz isso
    e.historico[:] = [_travamento(fim_ha_s=25 * 3600), _travamento(cortado=True)]
    html = logado.get("/").get_data(as_text=True)
    assert "Travou 1 vez em 24 h" in html and "acabou com o Nexus reiniciando" in html


def test_pedido_preso_sem_fila_cheia_e_o_aberto_agora(app, logado):
    e = presos._Estado(16, None)
    app.extensions[presos.CHAVE] = e
    um = dict(_travamento(), fila_cheia=False, max_presos=1, max_ocupadas=3)
    um["pedidos"] = um["pedidos"][:1]
    e.historico.append(um)
    html = logado.get("/").get_data(as_text=True)
    assert "gc-status--alerta" in html and "Pedido preso 1 vez em 24 h" in html
    assert "e durou 3 min: 1 pedido preso; em Fracttal (OS Creator), esperando a rede." in html
    seq = e.entrar(_pedido())
    _envelhecer(e, seq, 45)
    e.olhar()
    html = logado.get("/").get_data(as_text=True)
    assert "Pedido preso agora" in html and "(há 45 s)" in html
    # soltou: nos 15 s até o episódio fechar o cartão já não diz "agora" (a prova de 13/10 mostrou "Travado agora" com
    # o Nexus já respondendo)
    e.sair(seq)
    html = logado.get("/").get_data(as_text=True)
    assert "agora" not in html.split("versao-presos", 1)[1][:400] and "Pedido preso 2 vezes em 24 h" in html
    assert "e durou 45 s: 1 pedido preso" in html


def test_quem_nao_e_administrador_nao_ve(app, logado, monkeypatch):
    app.extensions[presos.CHAVE] = presos._Estado(16, None)
    app.extensions[presos.CHAVE].historico.append(_travamento())
    monkeypatch.setattr(setor_telas, "liberadas_do_menu", lambda: None)
    with logado.session_transaction() as s:
        s["admin"] = False
        s["usuario"] = {"email": "pessoa@exemplo.test", "nome": "Pessoa Exemplo", "perfil": ""}
    html = logado.get("/").get_data(as_text=True)
    assert "Versão no ar" in html and "versao-presos" not in html and "Travou" not in html


def test_sem_o_registro_ligado_o_cartao_nao_muda(app, logado):
    """Os testes e a vitrine estática não ligam o registro: o cartão sai como antes."""
    assert presos.CHAVE not in app.extensions
    assert "versao-presos" not in logado.get("/").get_data(as_text=True)

"""A 5070 do PC com NEXUS_PLATAFORMA_LOCAL: caminho do Nexus fica no processo, o resto vai à plataforma (10/10/2026).

Caso: o Levi abriu localhost:5070/t/performance/tempo-real e a moldura disse "configurada em outra origem"; a 5070 passou a
juntar os dois no mesmo endereço, com a mesma divisão do Caddy do servidor na raiz.
"""
import threading
from wsgiref.simple_server import WSGIRequestHandler, make_server

from werkzeug.test import Client

import app as app_local


class _Quieto(WSGIRequestHandler):
    def log_message(self, *a):
        pass


def _plataforma_falsa():
    def wsgi(environ, start_response):
        corpo = f"plataforma {environ['REQUEST_METHOD']} {environ['PATH_INFO']}".encode()
        start_response("200 OK", [("Content-Type", "text/plain"), ("Content-Length", str(len(corpo)))])
        return [corpo]

    srv = make_server("127.0.0.1", 0, wsgi, handler_class=_Quieto)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _nexus_falso(environ, start_response):
    corpo = f"nexus {environ['PATH_INFO']}".encode()
    start_response("200 OK", [("Content-Type", "text/plain"), ("Content-Length", str(len(corpo)))])
    return [corpo]


def test_caminhos_do_nexus_ficam_no_processo_e_o_resto_vai_a_plataforma():
    srv = _plataforma_falsa()
    try:
        c = Client(app_local.juntar_com_a_plataforma(_nexus_falso, f"http://127.0.0.1:{srv.server_port}"))
        for caminho in ("/", "/t/performance/tempo-real", "/entrar", "/os/tickets", "/static/nexus.css", "/saude"):
            assert c.get(caminho).get_data(as_text=True) == f"nexus {caminho}", caminho
        for caminho in ("/tempo-real", "/painel/nexus/entrar", "/api/macro", "/static/notif.js", "/static/logos/x.png",
                        "/healthz"):
            assert c.get(caminho).get_data(as_text=True) == f"plataforma GET {caminho}", caminho
        # o passe é um POST: tem de chegar à plataforma como POST
        assert c.post("/painel/nexus/entrar", data={"passe": "x"}).get_data(as_text=True) == \
            "plataforma POST /painel/nexus/entrar"
    finally:
        srv.shutdown()


def test_plataforma_fora_do_ar_da_502_e_o_nexus_segue():
    c = Client(app_local.juntar_com_a_plataforma(_nexus_falso, "http://127.0.0.1:9"))
    assert c.get("/healthz").status_code == 502
    assert c.get("/t/pcm/quadro").get_data(as_text=True) == "nexus /t/pcm/quadro"

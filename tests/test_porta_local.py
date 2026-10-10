"""A porta local (`ferramentas/porta_local.py`, o papel do Caddy no PC) só repassa: não guarda cookie de ninguém.

Achado na prova da porta única (10/10/2026; Levi: "a partir de segunda quero o Nexus como link principal"): a porta usava
um `requests.Session` com o pote de cookies padrão. O `Set-Cookie` de uma resposta ficava no pote e voltava, por conta
própria, no pedido seguinte de QUALQUER cliente que chegasse sem cookie (curl, outra aba, outro navegador): a sessão de
uma pessoa aparecia na de outra, e a prova de "sem sessão" mentia. O Caddy do servidor não guarda nada; a porta também não.
"""
import importlib.util
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from werkzeug.test import Client

RAIZ = Path(__file__).resolve().parent.parent


def _porta_local():
    spec = importlib.util.spec_from_file_location("porta_local", RAIZ / "ferramentas" / "porta_local.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Origem(BaseHTTPRequestHandler):
    """Faz o papel do Nexus e da plataforma: /define põe um cookie de sessão; /eco devolve o Cookie que chegou."""

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/define"):
            corpo = b"ok"
            self.send_response(200)
            self.send_header("Set-Cookie", "session=de-outra-pessoa; Path=/; HttpOnly")
        else:
            corpo = (self.headers.get("Cookie") or "(nenhum)").encode()
            self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)


def test_a_porta_local_nao_guarda_cookie_de_ninguem():
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), _Origem)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{servidor.server_address[1]}"
        app = _porta_local().criar_app(base, base, "prefixo", False)
        # use_cookies=False: o cliente de teste não guarda nem apaga cookie; o que vale é o que a porta faz
        r = Client(app, use_cookies=False).get("/define")
        assert "session=de-outra-pessoa" in r.headers.get("Set-Cookie", "")     # o cookie chega a QUEM pediu
        # outro cliente, sem cookie: a porta não lhe empresta o cookie do primeiro (nem do lado do Nexus)
        assert Client(app, use_cookies=False).get("/eco").get_data() == b"(nenhum)"
        assert Client(app, use_cookies=False).get("/nexus/eco").get_data() == b"(nenhum)"
        # o cookie do próprio cliente vai como veio
        proprio = Client(app, use_cookies=False).get("/eco", headers={"Cookie": "session=minha"})
        assert proprio.get_data() == b"session=minha"
    finally:
        servidor.shutdown()

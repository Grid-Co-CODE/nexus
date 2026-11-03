"""Nenhum teste fala com o Fracttal de verdade (31/10/2026). Numa outra tarefa, 4 testes antigos mandaram leituras de
VERDADE ao Fracttal com um JWT falso: deu 401 e nada foi gravado, mas a cota de 200 pedidos por minuto é da empresa toda
(o App de Campo vive dela) e teste não vai à rede. O `tests/conftest.py` bloqueia, em todo teste, o pedido a um host que
termina em `fracttal.com` no adaptador do requests (`HTTPAdapter.send`), abaixo do `Session.send` que os testes do
contador trocam: o adaptador de mentira de cada teste (`sessao_real_sem_rede`, o `HTTPAdapter.send` trocado no próprio
teste) segue valendo, e o resto (o banco de mentira, a própria máquina) não muda."""
import http.server
import threading

import pytest
import requests

BLOQUEIO = "rede do Fracttal bloqueada nos testes"


@pytest.mark.parametrize("verbo, url", [
    ("GET", "https://app.fracttal.com/api/work_orders?limit=1"),         # o REST do Campo e dos leitores
    ("POST", "https://app.fracttal.com/rpc/proxy"),                      # o RPC do OS Creator
    ("POST", "https://one.fracttal.com/oauth/token"),                    # o token, noutro host do Fracttal
    ("GET", "http://fracttal.com/"),
])
def test_o_fracttal_de_verdade_e_bloqueado(verbo, url):
    with pytest.raises(requests.ConnectionError, match=BLOQUEIO):
        requests.request(verbo, url, timeout=5)
    s = requests.Session()                                               # e pela Session, sem o proxy do ambiente
    s.trust_env = False
    with pytest.raises(requests.ConnectionError, match=BLOQUEIO):
        s.request(verbo, url, timeout=5)


def test_outro_host_nao_e_afetado():
    # um servidor de verdade na própria máquina: o pedido passa pelo adaptador de verdade do requests e volta
    class _Ok(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *args):
            pass

    servidor = http.server.HTTPServer(("127.0.0.1", 0), _Ok)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        s = requests.Session()
        s.trust_env = False
        r = s.get(f"http://127.0.0.1:{servidor.server_port}/", timeout=5)
        assert r.status_code == 200 and r.text == "ok"
    finally:
        servidor.shutdown()
        servidor.server_close()

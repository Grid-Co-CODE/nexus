"""Teto do OS Creator (14/10/2026, Levi: "pq depende da TI se o OS Creator Web faz parte do Nexus???"): o OS Creator
roda dentro do processo do Nexus e, esperando o Fracttal, prendia todas as threads; agora usa no máximo um teto delas e o
resto do Nexus nunca espera por ele. Provas: com o teto cheio o pedido seguinte do OS Creator volta 503 na hora (HTML que
se recarrega, ou JSON); o resto do Nexus e os estáticos do OS Creator passam; a vaga volta quando a resposta termina; o
servidor liga com 32 threads e teto de 16."""
import json
import threading
import time

from nexus.casca import teto_os as T


def _app_lento(solta):
    def app(environ, start_response):
        if environ["PATH_INFO"].startswith("/os/api"):
            solta.wait(5)
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"ok"]
    return app


def _chamar(app, caminho, accept="application/json", fetch_mode="cors"):
    status = {}

    def sr(s, h):
        status["s"], status["h"] = s, dict(h)
    corpo = b"".join(r := app({"PATH_INFO": caminho, "REQUEST_METHOD": "GET", "HTTP_ACCEPT": accept,
                               "HTTP_SEC_FETCH_MODE": fetch_mode}, sr))
    if hasattr(r, "close"):
        r.close()
    return status["s"], status["h"], corpo


def test_com_o_teto_cheio_o_os_creator_volta_503_e_o_resto_passa():
    solta = threading.Event()
    app = T.Teto(_app_lento(solta), teto=2, espera=0.1)
    presos = [threading.Thread(target=_chamar, args=(app, "/os/api/performance/contagens")) for _ in range(2)]
    for t in presos:
        t.start()
    for _ in range(100):
        if app.estado()["em_uso"] == 2:
            break
        time.sleep(0.01)
    try:
        inicio = time.monotonic()
        s, h, corpo = _chamar(app, "/os/api/selo")
        assert s.startswith("503") and time.monotonic() - inicio < 1 and h["Retry-After"] == "8"
        assert json.loads(corpo) == {"ok": False, "ocupado": True, "erro": T.RECADO}
        s, h, corpo = _chamar(app, "/os/", accept="text/html", fetch_mode="navigate")      # a tela se recarrega
        assert s.startswith("503") and 'http-equiv="refresh"' in corpo.decode() and T.RECADO in corpo.decode()
        assert _chamar(app, "/t/base/acessos")[0].startswith("200")                        # o resto do Nexus passa
        assert _chamar(app, "/os/static/inicio.css")[0].startswith("200")                  # estático não conta
        assert app.estado()["recusados"] == 2
    finally:
        solta.set()
        for t in presos:
            t.join()
    assert app.estado()["em_uso"] == 0                                                     # as vagas voltaram
    assert _chamar(app, "/os/api/selo")[0].startswith("200")


def test_a_vaga_volta_mesmo_quando_o_os_creator_quebra():
    def quebra(environ, start_response):
        raise RuntimeError("o Fracttal caiu no meio")
    app = T.Teto(quebra, teto=1, espera=0.05)
    for _ in range(3):
        try:
            _chamar(app, "/os/api/selo")
        except RuntimeError:
            pass
    assert app.estado()["em_uso"] == 0 and app.estado()["recusados"] == 0


def test_o_servidor_liga_32_threads_e_teto_de_16():
    texto = open("servir.py", encoding="utf-8").read()
    assert "THREADS = 32" in texto and "teto_os.ligar(app, teto=THREADS // 2)" in texto
    assert texto.index("teto_os.ligar") < texto.index("presos.ligar(app, THREADS)")

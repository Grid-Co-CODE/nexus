"""Teto do OS Creator no Nexus (14/10/2026): o OS Creator lento não segura o resto.

Levi, 14/10/2026, depois de "O nexus está muito lento" e "quando clico no OS Creator, fica carregando por um bom tempo":
"pq depende da TI se o OS Creator Web faz parte do Nexus???". O OS Creator Web roda DENTRO do processo do Nexus (a ponte,
`nexus/torres/oscreator/ponte.py`), sem proxy: cada pedido dele que espera o Fracttal (até 45 s por chamada) ocupa uma
das threads do waitress, e com algumas pessoas juntas as 16 acabavam e o Nexus inteiro esperava na fila (o /saude, que
não lê nada, chegou a 17, 30 e 60 s; a plataforma, no mesmo servidor, em 0,2 s). Separar o OS Creator num serviço próprio
pediria a T.I. (o serviço e o Caddy); o mesmo efeito sai daqui de dentro:

- o servidor sobe com 32 threads (servir.py) e o OS Creator (`/os/*` e as telas `/t/os/*`) usa no máximo TETO delas
  ao mesmo tempo: as outras ficam para o resto do Nexus, sempre;
- o pedido do OS Creator que chega com o teto cheio espera até ESPERA_S por uma vaga e, sem ela, volta na hora com 503
  ("o OS Creator está ocupado esperando o Fracttal"): a tela (HTML) se recarrega sozinha em alguns segundos; o pedido de
  dados recebe o recado em JSON. A thread é solta na hora, em vez de entrar na fila do Nexus inteiro;
- os arquivos estáticos do OS Creator (`/os/static/`) e a pré-carga não contam;
- o Raio-X (`/t/base/raio-x`) mostra quantas vagas estão em uso e quantos pedidos voltaram.

Quem liga é o servir.py (o servidor), nunca o create_app: os testes e o PC seguem sem teto.
"""
import json
import logging
import threading
import time

from werkzeug.wsgi import ClosingIterator

log = logging.getLogger(__name__)

CHAVE = "nexus_teto_os"
TETO = 16
ESPERA_S = 3.0
_DO_OS = ("/os/", "/t/os/")
_LIVRES = ("/os/static/",)
_PRE_CARGA = "HTTP_X_NEXUS_PRE_CARGA"     # o cabeçalho da pré-carga (auth/pre_carga.CABECALHO)
_LOG_S = 30.0
RECADO = "O OS Creator está ocupado esperando o Fracttal. Tente de novo em alguns segundos."


class Teto:
    """O middleware: no máximo `teto` pedidos do OS Creator em andamento; o seguinte espera `espera` s e volta com 503."""

    def __init__(self, wsgi, teto: int = TETO, espera: float = ESPERA_S):
        self.wsgi, self.teto, self.espera = wsgi, int(teto), float(espera)
        self.vagas = threading.BoundedSemaphore(self.teto)
        self.trava = threading.Lock()
        self.em_uso = 0
        self.recusados = 0
        self.ultimo_recusado = 0.0          # epoch
        self._logado = 0.0                  # monotonic

    def conta(self, environ) -> bool:
        caminho = environ.get("PATH_INFO", "") or ""
        return caminho.startswith(_DO_OS) and not caminho.startswith(_LIVRES) and not environ.get(_PRE_CARGA)

    def _soltar(self) -> None:
        with self.trava:
            self.em_uso -= 1
        self.vagas.release()

    def __call__(self, environ, start_response):
        if not self.conta(environ):
            return self.wsgi(environ, start_response)
        if not self.vagas.acquire(timeout=self.espera):
            return self._ocupado(environ, start_response)
        with self.trava:
            self.em_uso += 1
        try:
            resposta = self.wsgi(environ, start_response)
        except BaseException:
            self._soltar()
            raise
        return ClosingIterator(resposta, [self._soltar])

    def _ocupado(self, environ, start_response):
        agora = time.monotonic()
        with self.trava:
            self.recusados += 1
            self.ultimo_recusado = time.time()
            logar = agora - self._logado >= _LOG_S
            if logar:
                self._logado = agora
        if logar:
            log.warning("OS Creator no teto (%s pedidos em andamento): %s %s voltou com 503 (%s recusados desde a "
                        "subida)", self.teto, environ.get("REQUEST_METHOD", ""), environ.get("PATH_INFO", ""),
                        self.recusados)
        aceita = environ.get("HTTP_ACCEPT", "") or ""
        navega = environ.get("HTTP_SEC_FETCH_MODE", "") == "navigate" or (
            "text/html" in aceita and "application/json" not in aceita)
        if navega:
            corpo = ("<!doctype html><html lang=\"pt-BR\"><head><meta charset=\"utf-8\">"
                     "<meta http-equiv=\"refresh\" content=\"8\"><title>OS Creator ocupado</title>"
                     "<style>body{font:15px/1.5 system-ui,sans-serif;background:#090d18;color:#e9eef6;margin:0;"
                     "display:grid;place-items:center;min-height:100vh}main{max-width:460px;padding:24px}"
                     "a{color:#b8e84a}</style></head><body><main><h1 style=\"font-size:18px\">OS Creator ocupado</h1>"
                     f"<p>{RECADO} Esta tela se recarrega sozinha em 8 segundos.</p>"
                     "<p><a href=\"\">Tentar agora</a></p></main></body></html>").encode("utf-8")
            tipo = "text/html; charset=utf-8"
        else:
            corpo = json.dumps({"ok": False, "ocupado": True, "erro": RECADO}, ensure_ascii=False).encode("utf-8")
            tipo = "application/json; charset=utf-8"
        start_response("503 Service Unavailable", [("Content-Type", tipo), ("Content-Length", str(len(corpo))),
                                                   ("Retry-After", "8"), ("Cache-Control", "no-store")])
        return [corpo]

    def estado(self) -> dict:
        with self.trava:
            return {"teto": self.teto, "em_uso": self.em_uso, "recusados": self.recusados,
                    "ultimo_recusado": self.ultimo_recusado}


def ligar(app, teto: int = TETO, espera: float = ESPERA_S) -> Teto:
    """Embrulha o wsgi_app (chame ANTES do presos.ligar: o registro dos pedidos fica por fora e vê todos)."""
    t = Teto(app.wsgi_app, teto, espera)
    app.wsgi_app = t
    app.extensions[CHAVE] = t
    return t

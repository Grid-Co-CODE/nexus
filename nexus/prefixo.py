"""O caminho em que o Nexus é servido: na raiz (`/`, o PC e a fase 4) ou debaixo de um prefixo (`/nexus`, o servidor).

Por quê (Levi, 09/10/2026: "a partir de segunda quero o Nexus como link principal; o Nexus será o centro de tudo"): no
servidor o Nexus mora em `app.gridco.com.br/nexus`, ao lado da plataforma de Performance na raiz, e o código não sabia
disso. O menu (`/t/...`), o Início (`/`), o Sair (`/sair`) e os `fetch` saíam da raiz e caíam na plataforma; quem
consertava era uma camada da T.I. fora do repositório, que reescreve a resposta (`nexus/casca/CLAUDE.md`). Agora o
prefixo é do repositório: `NEXUS_PREFIXO` (ex. `/nexus`), lido do `.env` ou do ambiente.

Como chega a cada lugar:
- `Prefixo` (WSGI, posto pelo `create_app`): fixa `SCRIPT_NAME` = prefixo e tira o prefixo do `PATH_INFO` SÓ quando ele
  vem. Serve com o Caddy cortando o `/nexus` (o servidor de hoje, `handle_path`) e sem cortar; o `url_for` passa a sair
  com o prefixo sozinho. `X-Forwarded-Prefix` vindo de fora NUNCA é lido: o Caddy repassa cabeçalho do cliente, e quem
  mandasse um prefixo escolheria para onde os links e o cookie apontam.
- Python: `na_raiz("/t/pcm/gerar")` para todo endereço do Nexus escrito à mão (redirecionamento, link montado).
- Templates: `{{ raiz }}` (o prefixo deste pedido) antes de todo `href`/`src`/`action` absoluto, ou o filtro
  `|na_raiz` num endereço que veio do Python.
- JavaScript: `nexusRota("/t/...")`, definido no `<head>` (`_raiz_js.html`).

Tudo é IDEMPOTENTE (o que já começa com o prefixo não ganha outro): enquanto a camada da T.I. existir, ela põe `/nexus`
em caminho do Nexus escrito no HTML e no JavaScript, e o código não pode dobrar (`/nexus/nexus/...`). Sem a variável,
`raiz` é vazia e nada muda em relação a antes, byte a byte.
"""
import re

from flask import has_request_context, request
from flask.sessions import SecureCookieSessionInterface

# Um ou mais segmentos simples: letras, números, ponto, hífen e sublinhado. Nada de "//", "..", espaço ou query.
_VALIDO = re.compile(r"^(/[A-Za-z0-9._-]+)+$")


class PrefixoInvalido(ValueError):
    pass


def normalizar(valor) -> str:
    """'' (raiz) ou '/nexus': com barra no começo e sem barra no fim. Valor esquisito derruba a subida com o motivo."""
    texto = str(valor or "").strip()
    if texto in ("", "/"):
        return ""
    texto = "/" + texto.strip("/")
    if not _VALIDO.match(texto) or any(p in (".", "..") for p in texto.split("/")[1:]):
        raise PrefixoInvalido(f"NEXUS_PREFIXO inválido: {texto!r} (use algo como /nexus)")
    return texto


class Prefixo:
    """Middleware WSGI: o app passa a se ver debaixo de `prefixo`, com ou sem o proxy cortar o caminho antes."""

    def __init__(self, app, prefixo: str):
        self.app, self.prefixo = app, prefixo

    def __call__(self, environ, start_response):
        caminho = environ.get("PATH_INFO", "") or ""
        if caminho == self.prefixo or caminho.startswith(self.prefixo + "/"):
            caminho = caminho[len(self.prefixo):] or "/"
        environ["SCRIPT_NAME"] = self.prefixo
        environ["PATH_INFO"] = caminho
        return self.app(environ, start_response)


def raiz() -> str:
    """O prefixo deste pedido ('' na raiz). Fora de um pedido (tarefa de fundo), a raiz."""
    return request.script_root if has_request_context() else ""


def ja_na_raiz(caminho: str, base: str) -> bool:
    return bool(base) and (caminho == base or caminho.startswith(base + "/") or caminho.startswith(base + "?"))


def na_raiz(caminho) -> str:
    """O endereço como o navegador o pede: `/t/x` vira `/nexus/t/x` debaixo do prefixo. URL completa, `//...`, âncora
    e texto vazio passam como estão; o que já começa com o prefixo também (a camada da T.I. pode ter posto)."""
    if not isinstance(caminho, str):
        return caminho             # None e afins: o template mostra o que mostrava antes
    base = raiz()
    if not base or not caminho.startswith("/") or caminho.startswith("//") or ja_na_raiz(caminho, base):
        return caminho
    return base + caminho


def sem_raiz(caminho) -> str:
    """O inverso: `/nexus/t/x` vira `/t/x` (o que o roteamento do Nexus entende). O resto passa como está."""
    caminho = "" if caminho is None else str(caminho)
    base = raiz()
    if ja_na_raiz(caminho, base):
        resto = caminho[len(base):]
        return resto if resto.startswith("/") else "/" + resto
    return caminho


class SessaoNoPrefixo(SecureCookieSessionInterface):
    """O cookie da sessão no caminho em que o Nexus roda (`/nexus` no servidor, `/` na raiz), tirado do pedido.

    O nome (`nexus_sessao`) é o que separa o Nexus da plataforma, que usa `session` em `/` no mesmo endereço (spec
    2026-10-09, seção 5.1: entrar num apagava a sessão do outro). O caminho é o arremate: o cookie do Nexus nem vai aos
    pedidos da plataforma. Vem do `SCRIPT_NAME` (o `Prefixo` o fixa), e não de uma configuração à parte, para cookie e
    links saírem do mesmo lugar."""

    def get_cookie_path(self, app):
        return app.config.get("SESSION_COOKIE_PATH") or raiz() or "/"

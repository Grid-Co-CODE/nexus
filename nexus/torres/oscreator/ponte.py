"""Ponte do Nexus para o clone do OS Creator Web (os_creator/os_web, nesta pasta).

Por que DENTRO do Nexus, e não um segundo serviço com proxy como a plataforma faz com o 5090: é um processo só
para subir e acompanhar, e o portão de login do Nexus vale sem esforço — a ponte é uma rota do Nexus, então o
`before_request` do portão roda antes dela. O clone continua sendo um app Flask à parte (sessão própria no cookie
`os_sessao`, Path=/os; templates e estáticos dele); a ponte só entrega a requisição a ele e devolve a resposta.

DENTRO da casca do Nexus, numa moldura, com o menu lateral à vista (Levi, 30/09: "quero que continue no espaço do
Nexus aparecendo a aba lateral"). Até então abria em tela cheia, porque o clone decide se é a casca olhando
`window.top`: numa moldura do Nexus, `window.top` é o Nexus, então a casca dele não ligava as abas (achava que era
uma aba dentro de outra casca) e o login dele fugia da moldura e tomava a janela. A ponte troca, na resposta,
`window.top` por `window.__osTopo()`: a janela mais alta que ainda é do OS Creator. Fora do Nexus ela é o próprio
`window.top`, então o comportamento no supervisório é o mesmo.

O clone fica IDÊNTICO ao do oem (sincronizar = copiar de novo): todo ajuste é feito aqui, na resposta.
"""
import hashlib
import hmac
import logging
import os
import sys
import threading

from flask import Blueprint, current_app, render_template, request

AQUI = os.path.dirname(os.path.abspath(__file__))
# O serviço original roda com a pasta atual em os_creator (os_web.cmd): é de lá que ele importa `api`, `steps`...
RAIZ_CLONE = os.path.join(AQUI, "os_creator")

# Cada tela da torre abre o OS Creator na seção dela. Tela aberta sozinha vai para a casca do OS Creator com ela
# numa aba (base.html do clone); o Setores é a seção da tela inicial.
DESTINOS = {
    "inicio": "/os/",
    "historico": "/os/historico",
    "setores": "/os/#h_setores",
    "solicitacao": "/os/solicitacao",
    "clonagem": "/os/clonar",
}

# O topo do OS Creator diz "← Plataforma": no supervisório, "/" é a Plataforma de Performance. Aqui "/" é o Nexus.
# target=_top: dentro da moldura, o Voltar abriria um Nexus dentro do outro.
_VOLTAR_DE = 'href="/" title="Voltar para a Plataforma de Performance">&larr; Plataforma</a>'.encode()
_VOLTAR_PARA = 'href="/" target="_top" title="Voltar para o Nexus">&larr; Nexus</a>'.encode()

# Sobe de moldura em moldura até a de baixo do Nexus (o <html data-nexus>). Sem Nexus em cima, chega ao topo e é o
# window.top de sempre. Moldura de outro domínio (o supervisório embutido na Engenharia) para a subida no try.
_TOPO_OS = (b'<script>window.__osTopo = function () { var w = window; try { while (w.parent !== w && '
            b'!w.parent.document.documentElement.hasAttribute("data-nexus")) w = w.parent; } catch (e) {} '
            b'return w; };</script>')
_TROCAS_HTML = [
    (b"window.top !== window.self", b"window.__osTopo() !== window.self"),
    (b"window.top.location.href", b"window.__osTopo().location.href"),
]
# O abas.js liga a casca só quando ela não tem pai; dentro do Nexus ela tem, e o pai é o Nexus.
_TROCAS_ABAS = [(b"if (window.parent === window) casca();", b"if (window.__osTopo() === window) casca();")]

_METODOS = ["GET", "POST", "PUT", "PATCH", "DELETE"]
_trava = threading.Lock()

# Sem prefixo de propósito: o OS Creator gera links /os/... absolutos, e o cookie dele vale só em /os.
bp_raiz = Blueprint("os_web_ponte", __name__)


def _segredo(app) -> str:
    """Chave do cookie do clone, derivada da do Nexus: não é a do supervisório (que mora no %APPDATA%) nem a do
    Nexus. Trocar a NEXUS_SECRET_KEY encerra as duas sessões juntas — e não há segredo novo para guardar."""
    return hmac.new(str(app.config["SECRET_KEY"]).encode(), b"nexus/os_web", hashlib.sha256).hexdigest()


def _criar_clone(app):
    # append, não insert: o que já está instalado continua vencendo; os nomes do clone (api, steps, tickets_*...)
    # não existem no Nexus nem na biblioteca padrão
    if RAIZ_CLONE not in sys.path:
        sys.path.append(RAIZ_CLONE)
    from os_web import criar_app

    clone = criar_app(segredo=_segredo(app))
    # o original fala http com a plataforma na mesma máquina; aqui o cookie segue o do Nexus (Secure no servidor)
    clone.config["SESSION_COOKIE_SECURE"] = bool(app.config.get("SESSION_COOKIE_SECURE"))
    return clone


def clone(app):
    """O app do clone, criado na primeira vez que alguém abre /os/ (e não na subida do Nexus): quem não usa o
    OS Creator não paga o import dele, e um clone quebrado não impede o Nexus de subir."""
    ext = app.extensions
    if "os_web_clone" not in ext:
        with _trava:
            if "os_web_clone" not in ext:
                ext["os_web_clone"] = _criar_clone(app)
    return ext["os_web_clone"]


@bp_raiz.route("/os/", defaults={"resto": ""}, methods=_METODOS)
@bp_raiz.route("/os/<path:resto>", methods=_METODOS)
def encaminhar(resto: str):
    app = current_app._get_current_object()
    try:
        alvo = clone(app)
    except Exception as ex:      # noqa: BLE001 — qualquer falha do clone vira aviso, nunca derruba o Nexus
        logging.exception("OS Creator: o clone não subiu")
        return render_template("oscreator/fora.html", motivo=f"{type(ex).__name__}: {ex}"[:300]), 503
    # cópia do environ: o clone monta o request dele sem mexer no do Nexus
    environ = dict(request.environ)
    ajusta_js = resto == "static/abas.js"
    if ajusta_js:
        # O clone só conhece o arquivo ORIGINAL: perguntado "mudou?", ele diria 304 e o navegador seguiria com o
        # original em cache. A pergunta é respondida aqui, sobre a versão ajustada (30/09: todo botão voltava ao
        # Início do OS Creator, porque a casca rodava o abas.js antigo).
        environ.pop("HTTP_IF_NONE_MATCH", None)
        environ.pop("HTTP_IF_MODIFIED_SINCE", None)
    resp = app.response_class.from_app(alvo, environ)
    if resp.mimetype == "text/html":
        corpo = resp.get_data().replace(_VOLTAR_DE, _VOLTAR_PARA)
        if b"<head>" in corpo:
            # a função entra antes de qualquer script da página, que já a usa no <head>
            corpo = corpo.replace(b"<head>", b"<head>\n" + _TOPO_OS, 1)
            for de, para in _TROCAS_HTML:
                corpo = corpo.replace(de, para)
        resp.set_data(corpo)
    elif ajusta_js and resp.status_code == 200:
        corpo = resp.get_data()
        for de, para in _TROCAS_ABAS:
            corpo = corpo.replace(de, para)
        resp.set_data(corpo)
        # Marca de versão própria (a do original + "-nexus") e sem data: a data é a do arquivo original, e um
        # navegador que comparasse só a data acharia que nada mudou.
        etag, _fraca = resp.get_etag()
        resp.set_etag(f"{etag or 'abas'}-nexus")
        resp.headers.pop("Last-Modified", None)
        resp.make_conditional(request)
    return resp


def abrir(torre, tela_id: str):
    """A view de uma tela da torre: a página do Nexus que leva ao OS Creator na seção da tela."""
    def view():
        return render_template("oscreator/abrir.html", torre=torre, tela=torre.tela(tela_id),
                               destino=DESTINOS[tela_id])
    view.__name__ = f"abrir_{tela_id}"
    return view

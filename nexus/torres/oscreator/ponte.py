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
# numa aba (base.html do clone).
DESTINOS = {
    "inicio": "/os/",
    "historico": "/os/historico",
    "ativos": "/os/ativos",
    # um item por setor (Levi, 04/10): o mesmo endereço do card do setor na tela inicial do OS Creator
    "performance": "/os/performance",
    "cos": "/os/cos",
    "pcm": "/os/setor/pcm",
    "chamados": "/os/chamados",
    "engenharia": "/os/engenharia",
    "solicitacao": "/os/solicitacao",
    "clonagem": "/os/clonar",
}

# O topo do OS Creator, dentro do Nexus (Levi, 04/10/2026):
# - sem o "← Plataforma" (no supervisório, "/" é a Plataforma de Performance): o menu lateral do Nexus já leva a
#   qualquer lugar, e o botão só abria um Nexus dentro do outro;
# - sem o símbolo e o "Grid Co." (o topo do Nexus já tem), só o "Sistema de Ordens de Serviço", centralizado.
_VOLTAR_DE = (b'<a class="os-topo-voltar" href="/" title="Voltar para a Plataforma de Performance">'
              b'&larr; Plataforma</a>')
_MARCA_DE = ('<img src="/os/assets/grid-icon.png" alt="" class="os-simbolo">\n'
             '    <div><div class="os-n1">Grid Co.</div><div class="os-n2">Sistema de Ordens de Serviço</div></div>').encode()
_MARCA_PARA = '<div class="os-n2 os-n2--nexus">Sistema de Ordens de Serviço</div>'.encode()
_ESTILO_NEXUS = b'<style>.os-n2--nexus{font-size:13px;line-height:1;align-self:center}</style>'

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
# E a casca só ouve as molduras das próprias abas: o menu lateral do Nexus ganha uma porta própria, para abrir a tela
# como ABA NOVA na faixa do OS Creator, sem recarregar a casca e sem perder as abas abertas (Levi, 04/10/2026: "os
# botões laterais devem contribuir em adicionar novas abas também na tela acima").
_OUVIR_NEXUS = b"""    window.addEventListener('message', function (e) {
      if (e.origin !== location.origin || e.source !== window.parent) return;
      const d = e.data;
      if (!d || d.nexusOs !== 1 || !d.url) return;
      if (d.url === '/os/') ativar('inicio', {focar: true}); else abrir(d.url, d.rotulo);
    });
"""
_ANCORA_MENSAGEM = b"    window.addEventListener('message', function (e) {\n"
_TROCAS_ABAS = [(b"if (window.parent === window) casca();", b"if (window.__osTopo() === window) casca();"),
                (_ANCORA_MENSAGEM, _OUVIR_NEXUS + _ANCORA_MENSAGEM)]

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
        corpo = resp.get_data().replace(_VOLTAR_DE, b"").replace(_MARCA_DE, _MARCA_PARA)
        if b"<head>" in corpo:
            # a função entra antes de qualquer script da página, que já a usa no <head>
            corpo = corpo.replace(b"<head>", b"<head>\n" + _TOPO_OS + _ESTILO_NEXUS, 1)
            for de, para in _TROCAS_HTML:
                corpo = corpo.replace(de, para)
        resp.set_data(corpo)
    elif ajusta_js and resp.status_code == 200:
        corpo = resp.get_data()
        for de, para in _TROCAS_ABAS:
            corpo = corpo.replace(de, para)
        resp.set_data(corpo)
        # Marca de versão própria (a do original + "-nexus-" + o hash do que sai) e sem data: a data é a do arquivo
        # original, e um navegador que comparasse só a data acharia que nada mudou. O hash muda quando o ajuste muda
        # (04/10: a porta do menu lateral entrou num abas.js que já tinha marca "-nexus").
        etag, _fraca = resp.get_etag()
        resp.set_etag(f"{etag or 'abas'}-nexus-{hashlib.sha256(corpo).hexdigest()[:10]}")
        resp.headers.pop("Last-Modified", None)
        resp.make_conditional(request)
    return resp


def abrir(torre, tela_id: str):
    """A view de uma tela da torre: a página do Nexus que leva ao OS Creator na seção da tela."""
    def view():
        # o mapa "item do menu → tela do OS Creator": com ele, o clique no menu abre uma aba na casca já aberta
        menu_os = {f"/t/{torre.id}/{t.id}": {"url": DESTINOS[t.id], "nome": t.nome} for t in torre.telas if t.id in DESTINOS}
        return render_template("oscreator/abrir.html", torre=torre, tela=torre.tela(tela_id),
                               destino=DESTINOS[tela_id], menu_os=menu_os)
    view.__name__ = f"abrir_{tela_id}"
    return view

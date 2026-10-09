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
import re
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

# Tema claro (Levi, 09/10/2026: "faltou o tema claro do OS Creator Web, não está sincronizando com o botão do Nexus"). O
# clone não lê o cookie do Nexus: quem decide é a ponte, pelo mesmo casca.tema_do_pedido das páginas do Nexus.
# - No claro, o <html> da página já sai com data-tema="claro": o servidor desenha, e a página nasce clara, sem piscar o navy.
#   As cores moram no próprio clone (o par :where(html[data-tema="claro"]) no fim de cada .css do os_web/static), que
#   vão ao oem junto: lá ninguém põe o atributo e nada muda.
# - No escuro (o padrão, cookie ausente ou desconhecido) o atributo NÃO entra: o HTML do escuro é o de sempre.
# - Em toda página, o oscreator/_tema_os.html (o _tema_cabeca.html do Nexus) refaz a conta antes de pintar e ouve a troca
#   feita em outra aba. A troca na mesma aba chega pelo botão do Nexus (base.html), moldura por moldura.
_HTML_ABRE = re.compile(rb"<html(?=[\s>])", re.I)
_META_CHARSET = re.compile(rb"<meta charset=[^>]*>", re.I)

_METODOS = ["GET", "POST", "PUT", "PATCH", "DELETE"]
# O aviso do app de DESKTOP quando o JWT do Fracttal venceu e não renovou (api._rpc_headers). Na web ele aparecia na
# tela (Levi, 05/10/2026: "Em histórico de OS do OS Creator Web do Nexus, tem que voltar a logar no Fracttal"): aqui
# vira o que a web faz com sessão morta, voltar ao login, sem mexer no clone.
_JWT_VENCIDO = b"cole um novo em fracttal_login.txt"


def _trocar(corpo: bytes, de: bytes, para: bytes) -> bytes:
    """Troca com a quebra de linha que o arquivo tiver: num clone do Windows (git com core.autocrlf) o clone sai em
    CRLF, e a troca com LF não achava nada (05/10/2026, ensaio da T.I.: a porta do menu lateral não entrava no
    abas.js, sem erro nenhum)."""
    corpo = corpo.replace(de, para)
    if b"\n" in de:
        corpo = corpo.replace(de.replace(b"\n", b"\r\n"), para.replace(b"\n", b"\r\n"))
    return corpo


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
    if resp.mimetype in ("text/html", "application/json") and _JWT_VENCIDO in resp.get_data():
        return _de_volta_ao_login(app, resto, resp.mimetype == "application/json")
    if resp.mimetype == "text/html":
        corpo = _trocar(resp.get_data().replace(_VOLTAR_DE, b""), _MARCA_DE, _MARCA_PARA)
        if b"<head>" in corpo:
            # a função entra antes de qualquer script da página, que já a usa no <head>
            corpo = corpo.replace(b"<head>", b"<head>\n" + _TOPO_OS + _ESTILO_NEXUS, 1)
            for de, para in _TROCAS_HTML:
                corpo = corpo.replace(de, para)
            corpo = _com_o_tema(app, corpo)
        resp.set_data(corpo)
    elif ajusta_js and resp.status_code == 200:
        corpo = resp.get_data()
        for de, para in _TROCAS_ABAS:
            corpo = _trocar(corpo, de, para)
        resp.set_data(corpo)
        # Marca de versão própria (a do original + "-nexus-" + o hash do que sai) e sem data: a data é a do arquivo
        # original, e um navegador que comparasse só a data acharia que nada mudou. O hash muda quando o ajuste muda
        # (04/10: a porta do menu lateral entrou num abas.js que já tinha marca "-nexus").
        etag, _fraca = resp.get_etag()
        resp.set_etag(f"{etag or 'abas'}-nexus-{hashlib.sha256(corpo).hexdigest()[:10]}")
        resp.headers.pop("Last-Modified", None)
        resp.make_conditional(request)
    return resp


def _script_do_tema(app) -> bytes:
    """O <script> do tema (oscreator/_tema_os.html), montado uma vez por app: é só JavaScript, igual em todo pedido."""
    js = app.extensions.get("os_tema_js")
    if js is None:
        texto = app.jinja_env.get_template("oscreator/_tema_os.html").render()
        js = app.extensions["os_tema_js"] = "\n".join(l.strip() for l in texto.splitlines() if l.strip()).encode()
    return js


def _com_o_tema(app, corpo: bytes) -> bytes:
    """A página do clone no tema do Nexus: o <html> com data-tema="claro" quando o Nexus está no claro (no escuro, sem o
    atributo, como sempre), e o script do tema logo depois do <meta charset> (antes de pintar, e sem empurrar o charset para
    além dos primeiros 1.024 bytes, o trecho que o navegador lê para achar a codificação)."""
    from ...casca import tema_do_pedido
    if tema_do_pedido() == "claro":
        corpo = _HTML_ABRE.sub(b'<html data-tema="claro"', corpo, count=1)
    m = _META_CHARSET.search(corpo)
    if m:
        return corpo[:m.end()] + b"\n" + _script_do_tema(app) + corpo[m.end():]
    return corpo.replace(b"<head>\n", b"<head>\n" + _script_do_tema(app), 1)


def _de_volta_ao_login(app, resto: str, json: bool):
    """Sessão do Fracttal vencida: limpa o cookie do OS Creator e manda ao login dele, voltando depois para a mesma
    tela (o login do OS Creator só devolve para /os/...). Pedido de dados (JSON) recebe o 401 que a tela do OS
    Creator já entende ({"login": true})."""
    from urllib.parse import quote
    from flask import jsonify, redirect
    destino = "/os/" + resto + (("?" + request.query_string.decode()) if request.query_string else "")
    if json:
        resp = jsonify({"erro": "Sua sessão do Fracttal venceu. Entre de novo.", "login": True})
        resp.status_code = 401
    else:
        resp = redirect("/os/login?next=" + quote(destino, safe=""))
    resp.delete_cookie(clone(app).config["SESSION_COOKIE_NAME"], path="/os")
    return resp


def _endereco_do_os(url) -> str:
    """Só endereço do próprio OS Creator (/os/...): nada de mandar a moldura ou a janela para fora."""
    url = str(url or "")
    return url if url.startswith("/os/") and not url.startswith("//") and "\\" not in url else ""


def tela_do_endereco(url: str) -> str:
    """A tela da torre de um endereço do OS Creator: a de destino mais comprido que é começo dele (/os/clonar?folio=1 →
    clonagem); o resto é o Início."""
    caminho = url.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    achadas = [(len(d), t) for t, d in DESTINOS.items() if d != "/os/" and (caminho == d or caminho.startswith(d + "/"))]
    return max(achadas)[1] if achadas else "inicio"


def abrir(torre, tela_id: str):
    """A view de uma tela da torre: a página do Nexus que leva ao OS Creator na seção da tela.

    `?abrir=/os/...` abre a moldura nesse endereço, e a casca do OS Creator o põe numa aba (base.html do clone). É por
    onde o card da OS, aberto em outra torre, leva ao "Clonar esta OS" e ao "Abrir chamado" sem sair do Nexus."""
    def view():
        # o mapa "item do menu → tela do OS Creator": com ele, o clique no menu abre uma aba na casca já aberta
        menu_os = {f"/t/{torre.id}/{t.id}": {"url": DESTINOS[t.id], "nome": t.nome} for t in torre.telas if t.id in DESTINOS}
        return render_template("oscreator/abrir.html", torre=torre, tela=torre.tela(tela_id),
                               destino=_endereco_do_os(request.args.get("abrir")) or DESTINOS[tela_id], menu_os=menu_os)
    view.__name__ = f"abrir_{tela_id}"
    return view


# Telas do OS Creator com o atalho em OUTRA torre (Levi, 08/10/2026): "Controle de fornecedores do OS Creator Web tem
# que estar no NEXUS > CHAMADOS > FABRICANTE"; "o mesmo com Acompanhamento de chamados, tem que estar em GARANTIAS";
# "não que vão sair da visão do OS Creator Web, porém, quando for abrir essa janela o atalho deve ficar para a parte de
# CHAMADOS". A tela continua no OS Creator (mesmo endereço, mesma casca); o item do menu do Nexus é que mora na torre.
ATALHOS = {
    "chamados": {"fabricantes": "/os/chamados/fornecedores", "garantias": "/os/chamados/acompanhamento"},
}


def abrir_em(torre, tela_id: str):
    """Como `abrir`, para uma tela de outra torre que abre uma tela do OS Creator (ATALHOS): a moldura do OS Creator
    com o menu lateral da torre dona do atalho (o item dela fica marcado), e o clique entre os atalhos da torre abre
    aba nova na casca já aberta, como na torre OS Creator."""
    destinos = ATALHOS[torre.id]

    def view():
        menu_os = {f"/t/{torre.id}/{t}": {"url": d, "nome": torre.tela(t).nome} for t, d in destinos.items()}
        return render_template("oscreator/abrir.html", torre=torre, tela=torre.tela(tela_id),
                               destino=_endereco_do_os(request.args.get("abrir")) or destinos[tela_id], menu_os=menu_os)
    view.__name__ = f"abrir_{torre.id}_{tela_id}"
    return view


# ── o card da OS em qualquer torre do Nexus (08/10/2026) ───────────────────────────────────────────────────────────
# Levi: "NEXUS > ENGENHARIA > QUADRO DE EQUIPE — Ao clicar na OS quero que abra o mesmo card que aparece quando clicamos
# em uma OS no histórico do OS Creator Web. Como fazem parte do mesmo ambiente compartilhado (Nexus) precisamos fazer os
# setores se conversarem." O card é o do clone, inteiro e sem cópia: o fragmento /os/os/<id>?parcial=1, o os_acoes.js
# (as ações), o os.css e o os_acoes.css. Ele vem numa moldura própria (`oscreator/card_os.html`), por cima da tela que
# o abriu (`oscreator/card_os_abrir.html`, o NexusOsCard): a moldura separa o CSS do OS Creator do CSS do Nexus, e mora
# em /os/_nexus porque o cookie do Fracttal (os_sessao) só vai para /os.
def _tem_login_fracttal(alvo) -> bool:
    """A sessão do OS Creator tem o JWT do Fracttal? Sem pedido ao Fracttal: se ele venceu, quem diz é o próprio card,
    ao buscar a OS (a ponte manda para o login, e a moldura avisa)."""
    s = alvo.session_interface.open_session(alvo, request) or {}
    return bool(s.get("jwt"))


@bp_raiz.route("/os/_nexus/card/<int:wid>")
def card_os(wid: int):
    from urllib.parse import quote, urlencode

    from ...auth import next_seguro
    status = " ".join(str(request.args.get("status") or "").split())[:40]
    de = next_seguro(request.args.get("de"))
    try:
        estado = "ok" if _tem_login_fracttal(clone(current_app._get_current_object())) else "sem"
    except Exception:            # noqa: BLE001 — clone que não sobe: a moldura diz, e a tela de baixo segue
        logging.exception("OS Creator: o clone não subiu (card da OS)")
        estado = "fora"
    q = urlencode({"status": status}) if status else ""
    return render_template("oscreator/card_os.html", wid=wid, estado=estado,
                           fragmento=f"/os/os/{wid}?" + urlencode({"parcial": 1, "status": status}),
                           pagina=f"/os/os/{wid}" + ("?" + q if q else ""),
                           entrar="/entrar?next=" + quote(de, safe="/"))


@bp_raiz.route("/os/_nexus/ir")
def ir():
    """Um link do card da OS para outra tela do OS Creator (Clonar esta OS, Abrir chamado): a torre OS Creator do Nexus,
    com a tela numa aba da casca dele, e não o OS Creator solto, sem o menu do Nexus."""
    from urllib.parse import urlencode

    from flask import redirect
    url = _endereco_do_os(request.args.get("url")) or "/os/"
    return redirect(f"/t/os/{tela_do_endereco(url)}?" + urlencode({"abrir": url}))

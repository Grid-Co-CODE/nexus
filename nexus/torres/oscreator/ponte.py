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
import time
from urllib.parse import urlsplit

from flask import Blueprint, current_app, render_template, request, session
from flask.sessions import SecureCookieSessionInterface

from ...prefixo import ja_na_raiz, na_raiz, raiz, sem_raiz

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
# Tickets de performance saiu do Nexus (Levi, 12/10/2026: "pode excluir essa seção e o código dela!" e "Isso você não
# levará para o oem"): a tela foi apagada da cópia (a sincronia só lista o apagado, não apaga no oem), e os links que o
# código do oem ainda desenha para ela (o card "Tickets" da Performance e a pílula no card do setor, no Início) saem
# aqui, na resposta, para a cópia continuar igual à do oem.
_SEM_TICKETS = re.compile(rb'<a\b[^>]*\bhref="/os/tickets(?:[?#][^"]*)?"[^>]*>.*?</a>\s*', re.S)
_MARCA_DE = ('<img src="/os/assets/grid-icon.png" alt="" class="os-simbolo">\n'
             '    <div><div class="os-n1">Grid Co.</div><div class="os-n2">Sistema de Ordens de Serviço</div></div>').encode()
_MARCA_PARA = '<div class="os-n2 os-n2--nexus">Sistema de Ordens de Serviço</div>'.encode()
# Sem a faixa de abas dentro do Nexus (Levi, 12/10/2026: "tire a visão de abas da parte de cima pois como já temos as
# abas laterais, fica redundante, para um sistema separado, quero passar a impressão de unidade!"): some a faixa da casca
# e a fixa da tela aberta sozinha (as duas são .os-tabs). As telas abertas continuam vivas na casca (o "carregamento" que
# ele quer manter): o menu lateral acende a de cada item, já carregada. No 5090 do supervisório nada muda.
# O botão de recolher o topo morava na faixa: quem tinha recolhido (o osTopoRecolhido do navegador) ficaria sem o topo e
# sem como abri-lo; no Nexus o topo fica sempre à mostra (menos dentro de uma aba, onde a casca já o esconde).
# Sem o 2º cabeçalho DENTRO do Nexus (13/10/2026, Levi: "suma esse 2° cabeçalho tanto de OS Creator Web quanto de
# plataforma de performance! Dá a impressão que é uma tela dentro de uma tela!"): a tela logo abaixo do Nexus (a casca, o
# login, o card da OS) marca o <html> com os-no-nexus antes de pintar, e o topo dela some; quem entrou (o avatar, o nome e
# o perfil) e o Sair moram no topo do Nexus (base.html). Aberta sozinha no navegador, sem o Nexus em cima, a tela segue
# com o topo: é o único lugar com o nome e o sair. As telas dentro de uma aba já não tinham topo (os-embutido).
_MARCA_NO_NEXUS = (b'<script>try { if (window.parent !== window && '
                   b'window.parent.document.documentElement.hasAttribute("data-nexus")) '
                   b'document.documentElement.classList.add("os-no-nexus"); } catch (e) {}</script>')
_ESTILO_NEXUS = (b'<style>.os-n2--nexus{font-size:13px;line-height:1;align-self:center}'
                 b'.os-tabs{display:none!important}'
                 b'html:not(.os-embutido):not(.os-no-nexus) body.os-sem-topo .os-header{display:flex!important}'
                 b'html:not(.os-embutido):not(.os-no-nexus) body.os-sem-topo .os-sep{display:block!important}'
                 b'html.os-no-nexus .os-header,html.os-no-nexus .os-sep{display:none!important}</style>')

# A janela POR CIMA do Tempo real (13/10/2026, Levi: "Em performance > tempo real > criar OS ao invés de direcionar para o
# OS Creator aparece a tela de criação de OS sobrepondo toda a tela dando um blur de fundo, assim que a pessoa finaliza a
# OS só aparece a notificação de criação!"): a plataforma abre a tela de criação com ?janela=1 num iframe que cobre a tela.
# Aqui ela sai sem o topo (a marca os-no-nexus) e avisa a página de baixo quando o POST da criação responde ok
# (`{gc: "os-criada", mensagem, detalhes}`), para a janela fechar e a notificação aparecer. O código do OS Creator não
# muda (a cópia segue igual à do oem): quem embrulha o fetch é esta resposta.
_JANELA_OS = (rb'<script>document.documentElement.classList.add("os-no-nexus","os-janela");'
              rb'(function(){var f=window.fetch;if(!f)return;window.fetch=function(u,o){var p=f.apply(this,arguments);'
              rb'try{if(/\/os\/api\/[a-z_-]+\/criar(\?|$)/.test(String(u))&&o&&String(o.method||"").toUpperCase()==="POST"){'
              rb'p.then(function(r){return r.clone().json().then(function(j){if(r.ok&&j&&j.ok&&window.parent!==window)'
              rb'window.parent.postMessage({gc:"os-criada",mensagem:j.mensagem||"",detalhes:j.detalhes||[]},'
              rb'location.origin);});}).catch(function(){});}}catch(e){}return p;};})();</script>')

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
# Sem a faixa (12/10/2026), ninguém fecha aba pelo X: a casca do Nexus guarda no máximo _ABAS_MAX telas além do Início, e
# a que foi acesa há mais tempo sai quando abre uma a mais (a ativa nunca). 12 cabe os 9 itens do menu lateral da torre
# e mais três (uma OS aberta, uma clonagem): cada aba é uma moldura viva, e sem teto elas se acumulavam a sessão inteira.
_ABAS_MAX = 12
_USO_DE = b"    let abas = [], ativa = 'inicio', seq = 0;\n"
_USO_PARA = _USO_DE + b"    const uso = {}; let relogio = 0;                     // Nexus: quando cada aba foi acesa\n"
_ACENDER_DE = b"      ativa = id;\n"
_ACENDER_PARA = b"      ativa = id; uso[id] = ++relogio;\n"
_LIMITE_DE = b"      seq += 1;\n"
_LIMITE_PARA = (b"      if (abas.length >= %d) {                            // Nexus: sem a faixa, a mais antiga sai\n"
                b"        const velha = abas.filter(function (b) { return b.id !== ativa; })\n"
                b"          .sort(function (x, y) { return (uso[x.id] || 0) - (uso[y.id] || 0); })[0];\n"
                b"        if (velha) fechar(velha.id);\n"
                b"      }\n" % _ABAS_MAX) + _LIMITE_DE
_TROCAS_ABAS = [(b"if (window.parent === window) casca();", b"if (window.__osTopo() === window) casca();"),
                (_ANCORA_MENSAGEM, _OUVIR_NEXUS + _ANCORA_MENSAGEM),
                (_USO_DE, _USO_PARA), (_ACENDER_DE, _ACENDER_PARA), (_LIMITE_DE, _LIMITE_PARA)]

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


# ── o prefixo do Nexus no OS Creator embutido (09/10/2026, porta única) ───────────────────────────────────────────
# Levi: "a partir de segunda quero o Nexus como link principal". No servidor o Nexus mora em /nexus (NEXUS_PREFIXO), e o
# clone escreve /os/... na raiz em ~220 lugares (templates, .js e o JSON das rotas): seguidos ao pé da letra, eles levavam
# à PLATAFORMA (que tem o próprio /os/). O clone fica IDÊNTICO ao do oem (ele roda sozinho na raiz, no 5090); quem põe o
# prefixo é a ponte, na resposta, como já fazia com o resto:
# - HTML, JavaScript e JSON: "/os, '/os, `/os e (/os ganham o prefixo (um caminho do clone começa sempre logo depois de
#   aspas ou parêntese). Fica de fora o value="/os/...": é o `next` do formulário de login, que o clone só aceita sem o
#   prefixo (`_destino_local`). O `next=/os/...` dentro de um endereço também fica (vem depois de "=").
# - Location do redirecionamento que começa por /os ganha o prefixo (o url_for do clone já sai com ele: o clone recebe o
#   SCRIPT_NAME do Nexus).
# - O `next` que chega com o prefixo (o JavaScript do clone monta o next com o location.pathname) sai dele antes de ir ao
#   clone.
# - As EXPRESSÕES REGULARES do clone que testam o caminho (/^\/os\/[^/]/ no abas.js, /^\/os(\/|$)/ no carga.js) também
#   ganham o prefixo, escrito como na expressão (^\/nexus\/os). Revisão de 10/10/2026: só as aspas e o parêntese eram
#   cobertos; debaixo do /nexus o location.pathname é /nexus/os/..., as regras das abas davam "não é tela nossa", e todo
#   item da torre OS Creator abria o Início, os cartões não abriam aba e o "Clonar esta OS" caía no Início.
# Na raiz (o PC, a fase 4) nada disso roda: a resposta é a de sempre, byte a byte.
_DO_CLONE = re.compile(rb"(value=)?([\"'`(])/os(?=[/\"'`?#)])")
_REGEX_DO_CLONE = re.compile(rb"\^\\/os(?=\\/|[(?$])")
_MIMES_COM_CAMINHO = ("text/html", "text/javascript", "application/javascript", "application/json")


def _no_prefixo(corpo: bytes, base: str) -> bytes:
    prefixo = base.encode()
    corpo = _DO_CLONE.sub(lambda m: m.group(0) if m.group(1) else m.group(2) + prefixo + b"/os", corpo)
    # na expressão regular a barra vai escapada e o ponto também (o prefixo só tem letra, número, ponto, hífen e _)
    na_regex = prefixo.replace(b".", b"\\.").replace(b"/", b"\\/")
    return _REGEX_DO_CLONE.sub(lambda m: b"^" + na_regex + b"\\/os", corpo)


def _next_sem_prefixo(environ: dict, base: str) -> None:
    """O `next` da consulta com o prefixo (/nexus/os/x) vira o do clone (/os/x): o login dele só devolve para /os/...;
    com o prefixo, mandava a pessoa ao Início do OS Creator em vez da tela de onde ela veio."""
    from urllib.parse import parse_qsl, urlencode
    consulta = environ.get("QUERY_STRING") or ""
    if "next=" not in consulta:
        return
    pares = parse_qsl(consulta, keep_blank_values=True)
    novos = [(k, sem_raiz(v) if k == "next" and ja_na_raiz(v, base) else v) for k, v in pares]
    if novos != pares:
        environ["QUERY_STRING"] = urlencode(novos)


_trava = threading.Lock()

# Sem prefixo de propósito: o OS Creator gera links /os/... absolutos, e o cookie dele vale só em /os.
bp_raiz = Blueprint("os_web_ponte", __name__)


def _segredo(app) -> str:
    """Chave do cookie do clone, derivada da do Nexus: não é a do supervisório (que mora no %APPDATA%) nem a do
    Nexus. Trocar a NEXUS_SECRET_KEY encerra as duas sessões juntas — e não há segredo novo para guardar."""
    return hmac.new(str(app.config["SECRET_KEY"]).encode(), b"nexus/os_web", hashlib.sha256).hexdigest()


def token_do_banco_para_o_clone(config, ambiente=None) -> bool:
    """Põe no ambiente do processo o GRIDCO_SQL_TOKEN que o Nexus leu do .env dele. True se pôs.

    O Nexus lê o .env para o `app.config` e não mexe no ambiente (`nexus.config.ler_ambiente`); o clone procura o token
    no ambiente (`tickets_escrita._token`: ambiente → cofre do Windows → pasta do usuário → tokens.txt). No servidor não
    há cofre nem pasta do usuário, e o .env do clone só traz a credencial do Fracttal: as observações do Acompanhamento
    de chamados, os modelos do Controle de fornecedores e os temas abriam só para ler (Levi, 19/10/2026, em Garantias:
    "também não está sendo possível digitar observações"). O que já estiver no ambiente vale mais, como sempre."""
    ambiente = os.environ if ambiente is None else ambiente
    tk = str(config.get("GRIDCO_SQL_TOKEN") or "").strip()
    if not tk or str(ambiente.get("GRIDCO_SQL_TOKEN") or "").strip():
        return False
    ambiente["GRIDCO_SQL_TOKEN"] = tk
    return True


def _criar_clone(app):
    # append, não insert: o que já está instalado continua vencendo; os nomes do clone (api, steps, tickets_*...)
    # não existem no Nexus nem na biblioteca padrão
    if RAIZ_CLONE not in sys.path:
        sys.path.append(RAIZ_CLONE)
    # nos testes, não: o ambiente é do processo inteiro, e o token falso de um teste ficaria para os seguintes
    if not app.config.get("TESTING"):
        token_do_banco_para_o_clone(app.config)
    from os_web import criar_app

    clone = criar_app(segredo=_segredo(app))
    # o original fala http com a plataforma na mesma máquina; aqui o cookie segue o do Nexus (Secure no servidor)
    clone.config["SESSION_COOKIE_SECURE"] = bool(app.config.get("SESSION_COOKIE_SECURE"))
    # e mora no /os do Nexus, debaixo do prefixo em que ele roda (o clone fixa "/os", que debaixo de /nexus não ia ao
    # /nexus/os/... e ia ao /os/ da PLATAFORMA; spec da porta única, 5.1). Na raiz, "/os" como sempre.
    clone.session_interface = _SessaoDoClone()
    return clone


class _SessaoDoClone(SecureCookieSessionInterface):
    def get_cookie_path(self, app):
        return raiz() + "/os"


def clone(app):
    """O app do clone, criado na primeira vez que alguém abre /os/ (e não na subida do Nexus): quem não usa o
    OS Creator não paga o import dele, e um clone quebrado não impede o Nexus de subir."""
    ext = app.extensions
    if "os_web_clone" not in ext:
        with _trava:
            if "os_web_clone" not in ext:
                ext["os_web_clone"] = _criar_clone(app)
    return ext["os_web_clone"]


def sessao_do_os(app) -> dict:
    """A sessão do OS Creator deste pedido (o cookie `os_sessao`, que o navegador só manda para /os), ou {}."""
    alvo = clone(app)
    return dict(alvo.session_interface.open_session(alvo, request) or {})


def _sessao_os_na_resposta(alvo, resp) -> dict | None:
    """A sessão do OS Creator que a resposta do clone grava (o Set-Cookie do `os_sessao`): {} quando ela apaga o cookie,
    None quando não mexe nele (ou o valor não confere com a chave do clone)."""
    nome = alvo.config["SESSION_COOKIE_NAME"]
    for linha in resp.headers.getlist("Set-Cookie"):
        chave, _, valor = linha.split(";", 1)[0].partition("=")
        if chave.strip() != nome:
            continue
        valor = valor.strip().strip('"')
        if not valor:
            return {}
        try:
            return dict(alvo.session_interface.get_signing_serializer(alvo).loads(valor))
        except Exception:        # noqa: BLE001 — valor estranho: como se não mexesse
            return None
    return None


def _fim_na_resposta(alvo, resp) -> str | None:
    """O que a resposta do clone diz da sessão do Fracttal, para o Nexus acabar junto (Levi, 09/10/2026: "quando
    deslogar do Fracttal deslogue do Nexus"): "venceu" (o token venceu e não renovou), "caiu" (o Fracttal recusou o
    token: o clone tirou o JWT do cookie, mandou ao login dele ou respondeu 401 pedindo login) ou None. O token que o
    clone renovou estica o prazo da sessão do Nexus junto."""
    if resp.mimetype in ("text/html", "application/json") and _JWT_VENCIDO in resp.get_data():
        return "venceu"
    nova = _sessao_os_na_resposta(alvo, resp)
    if nova is not None:
        jwt = str(nova.get("jwt") or "")
        if not jwt:
            return "caiu"
        from ...auth.fracttal import exp_do_jwt
        exp = exp_do_jwt(jwt)
        if exp > float(session.get("fracttal_exp") or 0):
            session["fracttal_exp"] = exp
    # sem_raiz: debaixo do /nexus o url_for do clone já sai com o prefixo (ele recebe o SCRIPT_NAME do Nexus), e o login
    # dele chega como /nexus/os/login; comparado cru, a sessão que o Fracttal derrubou não derrubava a do Nexus
    if (resp.status_code in (301, 302, 303, 307, 308)
            and sem_raiz(urlsplit(resp.headers.get("Location", "")).path) == "/os/login"):
        return "caiu"
    if resp.status_code == 401 and resp.mimetype == "application/json" and (resp.get_json(silent=True) or {}).get("login"):
        return "caiu"
    return None


# ── a Área PCM do OS Creator: só o setor PCM ou administrador (Levi, 13/10/2026) ───────────────────────────────────
# "Só o setor PCM ou administrador! Quem não é nenhum dos dois recebe a notificação!". A Área PCM é a da `SolicPcmTab`
# do app (a Fila do PCM, que aprova e cria a OS, e os Temas, que gravam no banco com a chave do servidor); no app ela
# pede a senha do PCM. Aqui quem decide é o Nexus, e a decisão vai ao clone no pedido (`request.environ`), onde o
# `rotas_solic` mostra o aviso no lugar da tela e recusa as gravações. O Painel, o Histórico e a Nova solicitação seguem
# abertos (são a Área do Solicitante do app). O setor é o de Base → Acessos → Pessoas e setores, pelo NOME ("PCM"); sem saber o
# setor (banco fora, Nexus sem a NEXUS_PESSOA_HMAC), fecha: só o administrador passa.
AREA_PCM = "os_web.area_pcm"
SETOR_PCM = "pcm"


def _sem_acento(t: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().strip().lower()


def area_pcm() -> dict:
    """{"pode": bool, "aviso": str} da sessão do Nexus de agora."""
    if session.get("admin"):
        return {"pode": True, "aviso": ""}
    regra = "A Fila do PCM e os Temas são do setor PCM e dos administradores do Nexus."
    if not current_app.config.get("NEXUS_PESSOA_HMAC"):
        return {"pode": False, "aviso": regra + " Este Nexus ainda não sabe o setor de cada pessoa (falta a "
                                                "NEXUS_PESSOA_HMAC no servidor): por enquanto só o administrador entra."}
    from ...auth import setor_telas
    u = session.get("usuario")
    email = str(u.get("email") or "").strip().lower() if isinstance(u, dict) else ""
    try:
        setor = setor_telas.setor_da_pessoa(current_app.config, email, *setor_telas._banco())
    except Exception as ex:      # noqa: BLE001 — sem saber o setor, fecha (e diz que é leitura, não falta de setor)
        logging.warning("OS Creator: não consegui ler o setor para a Área PCM (%s)", type(ex).__name__)
        return {"pode": False, "aviso": regra + " Não consegui ler o seu setor agora; tente de novo em instantes."}
    if setor and _sem_acento(setor.get("nome")) == SETOR_PCM:
        return {"pode": True, "aviso": ""}
    onde = ("Você está no setor %s." % setor["nome"]) if setor else "Você está sem setor no Nexus."
    return {"pode": False, "aviso": regra + " " + onde + " Quem põe você no setor PCM é o administrador "
                                                         "(Base → Acessos → Pessoas e setores)."}


@bp_raiz.route("/os/", defaults={"resto": ""}, methods=_METODOS)
@bp_raiz.route("/os/<path:resto>", methods=_METODOS)
def encaminhar(resto: str):
    app = current_app._get_current_object()
    try:
        alvo = clone(app)
    except Exception as ex:      # noqa: BLE001 — qualquer falha do clone vira aviso, nunca derruba o Nexus
        logging.exception("OS Creator: o clone não subiu")
        return render_template("oscreator/fora.html", motivo=f"{type(ex).__name__}: {ex}"[:300]), 503
    # cópia do environ: o clone monta o request dele sem mexer no do Nexus. O SCRIPT_NAME vai junto: debaixo do prefixo,
    # o url_for do clone já sai com ele, e o cookie dele fica no /os do Nexus (_SessaoDoClone)
    environ = dict(request.environ)
    if resto.startswith(("solicitacao", "api/solic")):
        environ[AREA_PCM] = area_pcm()          # a Área PCM é do setor PCM ou do administrador (ver `area_pcm`)
    base = raiz()
    ajusta_js = resto == "static/abas.js"
    # debaixo do prefixo todo .js do clone sai reescrito, e a pergunta "mudou?" vale para a versão reescrita (abaixo)
    reescreve_js = bool(base) and resto.startswith("static/") and resto.endswith(".js")
    if base:
        _next_sem_prefixo(environ, base)
    if ajusta_js or reescreve_js:
        # O clone só conhece o arquivo ORIGINAL: perguntado "mudou?", ele diria 304 e o navegador seguiria com o
        # original em cache. A pergunta é respondida aqui, sobre a versão ajustada (30/09: todo botão voltava ao
        # Início do OS Creator, porque a casca rodava o abas.js antigo).
        environ.pop("HTTP_IF_NONE_MATCH", None)
        environ.pop("HTTP_IF_MODIFIED_SINCE", None)
    resp = app.response_class.from_app(alvo, environ)
    from ...auth import encerrar, via_fracttal
    if via_fracttal():
        # entrou no Nexus pelo Fracttal: a sessão do Fracttal que acabou no meio do pedido leva a do Nexus junto
        fim = _fim_na_resposta(alvo, resp)
        if fim:
            destino = "/os/" + resto + (("?" + request.query_string.decode()) if request.query_string else "")
            return encerrar(fim, destino, json=True if resp.mimetype == "application/json" else None)
    if resp.mimetype in ("text/html", "application/json") and _JWT_VENCIDO in resp.get_data():
        return _de_volta_ao_login(app, resto, resp.mimetype == "application/json")
    if base:
        destino = resp.headers.get("Location", "")
        if destino.startswith("/os") and not ja_na_raiz(destino, base):
            resp.headers["Location"] = base + destino
    if resp.mimetype == "text/html":
        corpo = _SEM_TICKETS.sub(b"", _trocar(resp.get_data().replace(_VOLTAR_DE, b""), _MARCA_DE, _MARCA_PARA))
        if b"<head>" in corpo:
            # a função entra antes de qualquer script da página, que já a usa no <head>
            janela = _JANELA_OS if request.args.get("janela") == "1" else b""
            corpo = corpo.replace(b"<head>", b"<head>\n" + _TOPO_OS + _MARCA_NO_NEXUS + janela + _ESTILO_NEXUS, 1)
            for de, para in _TROCAS_HTML:
                corpo = corpo.replace(de, para)
            corpo = _com_o_tema(app, corpo)
        if base:
            corpo = _no_prefixo(corpo, base)
        resp.set_data(corpo)
    elif (ajusta_js or reescreve_js) and resp.status_code == 200:
        corpo = resp.get_data()
        if ajusta_js:
            for de, para in _TROCAS_ABAS:
                corpo = _trocar(corpo, de, para)
        if base:
            corpo = _no_prefixo(corpo, base)
        resp.set_data(corpo)
        # Marca de versão própria (a do original + "-nexus-" + o hash do que sai) e sem data: a data é a do arquivo
        # original, e um navegador que comparasse só a data acharia que nada mudou. O hash muda quando o ajuste muda
        # (04/10: a porta do menu lateral entrou num abas.js que já tinha marca "-nexus").
        etag, _fraca = resp.get_etag()
        resp.set_etag(f"{etag or 'abas'}-nexus-{hashlib.sha256(corpo).hexdigest()[:10]}")
        resp.headers.pop("Last-Modified", None)
        resp.make_conditional(request)
    elif base and resp.mimetype in _MIMES_COM_CAMINHO and resp.status_code == 200:
        resp.set_data(_no_prefixo(resp.get_data(), base))
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
    from ...auth import os_cookie_path
    destino = "/os/" + resto + (("?" + request.query_string.decode()) if request.query_string else "")
    if json:
        resp = jsonify({"erro": "Sua sessão do Fracttal venceu. Entre de novo.", "login": True})
        resp.status_code = 401
    else:
        # o login no endereço do navegador (com o prefixo); o `next`, no do clone (sem ele: o clone só aceita /os/...)
        resp = redirect(na_raiz("/os/login") + "?next=" + quote(destino, safe=""))
    resp.delete_cookie(clone(app).config["SESSION_COOKIE_NAME"], path=os_cookie_path())
    return resp


# ── a conferência da página: a sessão do Fracttal ainda vale? (Levi, 09/10/2026) ─────────────────────────────────────
# O portão já encerra quem chega a /os sem o JWT ou com ele vencido; o que só o Fracttal sabe é se o token foi derrubado
# por fora (sair no app do Fracttal, por exemplo). A página do Nexus pergunta ao abrir e a cada 5 minutos à vista
# (base.html), e o servidor pergunta ao Fracttal no máximo uma vez a cada 5 minutos por token: a cota é de 200 pedidos
# por minuto para a EMPRESA inteira, App de Campo e robôs incluídos.
_VIVO_S = 5 * 60
_INCERTO_S = 60          # Fracttal fora ou recusando por cota: pergunta de novo em 1 minuto, sem derrubar ninguém
_trava_vivo = threading.Lock()


def vivo_no_fracttal(app, jwt: str, email: str = "") -> bool | None:
    """True/False pelo Fracttal (1 pedido barato, o mesmo do `api.is_logged_in` do clone), guardado por 5 minutos; None
    quando não dá para saber (rede, 429 da cota, token a 2 minutos de vencer, quando o prazo resolve e a pergunta faria o
    clone tentar renovar o token). None nunca derruba ninguém: só o Fracttal dizendo que a sessão morreu derruba."""
    if not jwt:
        return False
    from ...auth.fracttal import exp_do_jwt
    exp = exp_do_jwt(jwt)
    if exp and exp - time.time() < 120:
        return None
    chave = hashlib.sha256(jwt.encode()).hexdigest()
    guardado = app.extensions.setdefault("os_fracttal_vivo", {})
    agora = time.monotonic()
    with _trava_vivo:
        visto = guardado.get(chave)
        if visto and agora < visto[0]:
            return visto[1]
    clone(app)                                   # põe o `api` do clone no sys.path
    import api as os_api                         # noqa: E402
    from os_web import sessao as os_sessao       # noqa: E402
    with os_sessao.contexto(jwt, email):
        try:
            os_api._rpc_call(os_api.RPC_LABELS_LIST, {"sort": [], "page": 1, "limit": 1, "start": 0, "is_tree": False,
                                                      "node": None, "id_work_order": 0, "only_enabled": True}, timeout=10)
            vivo = True
        except os_api.SessionExpired:
            vivo = False
        except Exception:                        # noqa: BLE001 — 429, rede, Fracttal fora: não sei
            vivo = None
    with _trava_vivo:
        for k in [k for k, (ate, _v) in guardado.items() if ate <= agora]:
            del guardado[k]
        guardado[chave] = (agora + (_VIVO_S if vivo is not None else _INCERTO_S), vivo)
    return vivo


@bp_raiz.route("/os/_nexus/sessao")
def sessao_viva():
    """{"ok": true} enquanto a sessão do Fracttal de quem entrou por ele vale; a que o Fracttal diz que morreu encerra o
    Nexus (401, {"sessao_encerrada": true, "entrar": ...}). Quem entrou com a senha de administrador não depende dela."""
    from flask import jsonify

    from ...auth import encerrar, via_fracttal
    if not via_fracttal():
        return jsonify({"ok": True})
    app = current_app._get_current_object()
    s = sessao_do_os(app)
    if vivo_no_fracttal(app, str(s.get("jwt") or ""), str((s.get("conta") or {}).get("email") or "")) is False:
        return encerrar("caiu", json=True)
    return jsonify({"ok": True})


def _endereco_do_os(url) -> str:
    """Só endereço do próprio OS Creator (/os/...): nada de mandar a moldura ou a janela para fora. Sai sem o prefixo
    (o que chega com ele, como o link de um card já reescrito pela ponte, perde): quem desenha põe o do pedido."""
    url = sem_raiz(str(url or ""))
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
        # chaves e endereços como o navegador os vê (com o prefixo): o href do menu e o que a casca do clone abre
        menu_os = {na_raiz(f"/t/{torre.id}/{t.id}"): {"url": na_raiz(DESTINOS[t.id]), "nome": t.nome}
                   for t in torre.telas if t.id in DESTINOS}
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
        menu_os = {na_raiz(f"/t/{torre.id}/{t}"): {"url": na_raiz(d), "nome": torre.tela(t).nome}
                   for t, d in destinos.items()}
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


def _card(caminho: str, wid=None):
    """A moldura do card (`card_os.html`) para uma página do clone (`/os/os/<id>` ou `/os/os/folio/<nº>`): o fragmento
    dela (?parcial=1) vai para dentro da moldura, com o status que a tela mandou."""
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
    # sem o login do Fracttal, o do PRÓPRIO OS Creator (/os/login), e a volta à tela de onde a pessoa saiu pelo
    # /os/_nexus/card/voltar (o clone só devolve para /os/...). Até 18/10/2026 era o /entrar do Nexus, que com a conta
    # Microsoft ligada é a porta DELA: o Levi clicava em "Entrar com o Fracttal" e caía na Microsoft
    volta = "/os/_nexus/card/voltar?" + urlencode({"de": de}, safe="/")
    return render_template("oscreator/card_os.html", wid=wid, estado=estado,
                           fragmento=f"{caminho}?" + urlencode({"parcial": 1, "status": status}),
                           pagina=caminho + ("?" + q if q else ""),
                           entrar=na_raiz("/os/login") + "?next=" + quote(volta, safe=""))


@bp_raiz.route("/os/_nexus/card/voltar")
def card_voltar():
    """A volta do login do Fracttal do OS Creator (o "Entrar com o Fracttal" do card da OS): à tela do Nexus `de`, e só
    a uma do próprio site (`destino_seguro`). O /os/_nexus/voltar é o da assinatura da PT (só telas do Campo)."""
    from flask import redirect

    from ...auth import destino_seguro
    return redirect(destino_seguro(request.args.get("de")))


@bp_raiz.route("/os/_nexus/card/<int:wid>")
def card_os(wid: int):
    return _card(f"/os/os/{wid}", wid)


@bp_raiz.route("/os/_nexus/card/folio/<int:folio>")
def card_os_folio(folio: int):
    """O mesmo card pelo NÚMERO da OS, para a tela que não tem o id do Fracttal (16/10/2026: o nº citado na observação
    do painel Fora da programação do PCM). Quem acha o id é o clone (`/os/os/folio/<nº>`, o "Buscar OS pelo nº" do
    Histórico): um pedido a mais ao Fracttal, e "Não achei nenhuma OS com o nº" dentro da moldura quando não existe."""
    return _card(f"/os/os/folio/{folio}")


@bp_raiz.route("/os/_nexus/ir")
def ir():
    """Um link do card da OS para outra tela do OS Creator (Clonar esta OS, Abrir chamado): a torre OS Creator do Nexus,
    com a tela numa aba da casca dele, e não o OS Creator solto, sem o menu do Nexus."""
    from urllib.parse import urlencode

    from flask import redirect
    url = _endereco_do_os(request.args.get("url")) or "/os/"
    return redirect(na_raiz(f"/t/os/{tela_do_endereco(url)}") + "?" + urlencode({"abrir": url}))


# ── o comentário da Engenharia na nota da OS (24/10/2026) ──────────────────────────────────────────────────────────
# Levi: "Todo comentário que a engenharia fizer vai para a nota da OS com data e hora do comentário." A página da OS do
# Quadro da equipe (/t/engenharia/equipe/os/<nº>) manda aqui, em /os/_nexus, porque o cookie do Fracttal (os_sessao) só
# vai para /os: a nota é escrita pelo `api.editar_nota_os` do clone na sessão do Fracttal da PESSOA, o mesmo caminho do
# card da OS, e a regra medida do card vale (OS concluída, cancelada ou de várias tarefas não deixa editar a nota: com
# várias tarefas, ela sobrescreveria a observação da tarefa errada). O que é só do Nexus fica aqui, nunca na cópia.
_trava_nota = threading.Lock()      # dois comentários juntos na mesma OS: um não apaga o outro na nota
# a página da OS de onde veio o comentário (a do Quadro da equipe ou a da tela ETMs): o login do Fracttal volta para ela
_PAGINA_DA_OS = re.compile(r"^/t/engenharia/(equipe|etm)/os/\d+$")


class _NotaIncompleta(RuntimeError):
    """O Fracttal devolveu a OS sem as tarefas (a leitura que falha "mole"): gravar trocaria a nota inteira."""


class _NotaNaoGravou(RuntimeError):
    """O Fracttal não gravou a nota (a mensagem dele vai junto)."""


def _acrescentar_na_nota(os_api, regra, o: dict, linhas: list[str]) -> str:
    """As linhas no fim da nota da OS no Fracttal (o comentário da Engenharia e, uma vez, o histórico do app de ETM),
    com a regra medida do card: OS concluída, cancelada ou de várias tarefas não deixa editar a nota (com várias, ela
    sobrescreveria a observação da tarefa errada). A nota que a página mostra tem de estar no que vai ser regravado (o
    Fracttal tem a nota da OS e a da tarefa, e a OS 12191 tinha as duas diferentes). A linha que já está na nota não
    volta: trazer o histórico de novo não a repete. Devolve "sim" ou o motivo de o comentário ficar só no Nexus."""
    d = os_api.get_os_detalhes(o["wid"]) or {}
    if not d.get("tarefas"):
        # a leitura que falha "mole" volta sem tarefas e com a nota vazia: gravar trocaria a nota inteira pela linha nova
        # (revisão final de 24/10/2026)
        raise _NotaIncompleta()
    pode_nota, motivo = regra.nota_pode_editar(regra.status_id_de(o.get("status"), d), len(d.get("tarefas") or []))
    if not pode_nota:
        return motivo
    atual = str(d.get("notas") or "").strip()
    na_pagina = " ".join(str(o.get("nota") or "").split())
    if na_pagina and na_pagina not in " ".join(atual.split()):
        return ("a nota da OS no Fracttal não bateu com a leitura da página; para não sobrescrever, o comentário ficou "
                "só no Nexus")
    # a linha inteira, não um trecho (revisão final de 26/10/2026: "Trocar o chip" se achava dentro de "Trocar o chip
    # amanhã" do mesmo minuto, e o comentário não ia)
    def _n(s):
        return "\n".join(x.rstrip() for x in str(s).replace("\r\n", "\n").split("\n"))
    corpo = "\n" + _n(atual) + "\n"
    novas = [x for x in linhas if "\n" + _n(x).strip() + "\n" not in corpo]
    if not novas:
        return "sim"
    r = os_api.editar_nota_os(o["wid"], "\n".join(([atual] if atual else []) + novas))
    if not (isinstance(r, dict) and r.get("ok")):
        raise _NotaNaoGravou((r or {}).get("erro") or "sem resposta")
    return "sim"


@bp_raiz.route("/os/_nexus/engenharia/os/<int:wid>/comentar", methods=["POST"])
def engenharia_comentar(wid: int):
    import logging
    from datetime import datetime, timedelta, timezone
    from urllib.parse import quote, urlencode

    from flask import current_app, jsonify, session

    from ...engenharia import os_acompanhamento as O
    from ...engenharia import os_equipe
    from ..engenharia import _os_para_gravar, _quem_pode
    from ..moldura import _de_outro_site
    if _de_outro_site():
        return jsonify({"erro": "Pedido de outro site: nada foi gravado."}), 403
    c = request.get_json(silent=True) or {}
    pode, _meu = _quem_pode()
    try:
        texto = O.texto_do_comentario(c.get("texto"))
        quem = O.quem_comenta(session.get("usuario"), pode)       # quem o Nexus recusaria não chega ao Fracttal
    except O.Recusada as e:
        return jsonify({"erro": str(e)}), 400
    folio = str(c.get("folio") or "").strip()
    # a volta do login do Fracttal, como no card da OS: o /os/login do clone e o /os/_nexus/card/voltar até a página
    # (a do Quadro da equipe ou, desde 26/10/2026, a da tela ETMs)
    de = str(c.get("de") or "")
    if not _PAGINA_DA_OS.match(de):
        de = f"/t/engenharia/equipe/os/{folio}" if folio.isdigit() else "/t/engenharia/equipe"
    login = na_raiz("/os/login") + "?next=" + quote("/os/_nexus/card/voltar?" + urlencode({"de": de}, safe="/"), safe="")
    app = current_app._get_current_object()
    s = sessao_do_os(app)
    jwt = str(s.get("jwt") or "")
    if not jwt:
        return jsonify({"erro": "Para ir à nota da OS, entre pelo Fracttal.", "login": login}), 401
    o = os_equipe.ler_os(folio) if folio.isdigit() else None
    if not o or str(o.get("wid")) != str(wid):
        return jsonify({"erro": "Não achei esta OS no Fracttal: recarregue a página."}), 404
    linha = O.linha_da_nota(texto, quem["nome"], datetime.now(timezone(timedelta(hours=-3))))
    clone(app)                                   # põe o `api` do clone no sys.path
    import api as os_api                         # noqa: E402
    from os_web import os_acoes_web as regra     # noqa: E402
    from os_web import sessao as os_sessao       # noqa: E402
    with _trava_nota, os_sessao.contexto(jwt, str((s.get("conta") or {}).get("email") or "")):
        try:
            nota = _acrescentar_na_nota(os_api, regra, o, [linha])
        except _NotaIncompleta:
            return jsonify({"erro": "O Fracttal não devolveu a OS inteira agora. Nada foi gravado; tente de novo."}), 502
        except _NotaNaoGravou as e:
            return jsonify({"erro": "O Fracttal não gravou a nota (%s). Nada foi gravado; tente de novo." % e}), 502
        except os_api.SessionExpired:
            # o token cassado antes do exp: quem entrou pelo Fracttal sai do Nexus junto (o /os/login, com o JWT morto
            # no cookie, voltava direto para a página); quem entrou pela Microsoft perde só o cookie do OS Creator, e o
            # login dele mostra o formulário (revisão final de 24/10/2026)
            from ...auth import encerrar, os_cookie_path, via_fracttal
            if via_fracttal():
                return encerrar("caiu", json=True)
            resp = jsonify({"erro": "A sessão do Fracttal venceu: entre de novo.", "login": login})
            resp.status_code = 401
            resp.delete_cookie("os_sessao", path=os_cookie_path())
            return resp
        except Exception as e:                   # noqa: BLE001 — Fracttal fora, cota: nada foi gravado
            logging.warning("comentário da OS %s: o Fracttal não respondeu (%s: %s)", wid, type(e).__name__,
                            str(e)[:160])
            return jsonify({"erro": "O Fracttal não respondeu (%s). Nada foi gravado; tente de novo."
                                    % type(e).__name__}), 502
    try:
        O.registrar_comentario(_os_para_gravar(o), texto, session.get("usuario"), pode, nota)
    except Exception as e:                       # noqa: BLE001 — a nota já foi: dizer, sem pedir para repetir
        logging.exception("comentário da OS %s: foi à nota, mas não ao livro do Nexus", wid)
        if nota == "sim":
            return jsonify({"ok": True, "mensagem": "Foi para a nota da OS %s, mas não entrou nos comentários do Nexus "
                                                    "(%s). Não repita." % (o["os"], type(e).__name__)})
        return jsonify({"erro": "Não consegui gravar no banco (%s). Nada mudou; tente de novo." % type(e).__name__}), 502
    if nota == "sim":
        return jsonify({"ok": True, "mensagem": "Comentário salvo na nota da OS %s, com a data e a hora." % o["os"]})
    return jsonify({"ok": True, "mensagem": "Comentário salvo só no Nexus: %s" % nota})


# ── o histórico do app de ETM, trazido uma vez (26/10/2026) ──────────────────────────────────────────────────────────
# Levi: "Traz 1 vez, para as OSs em aberto bota esses comentários na nota da OS." Mora aqui, em /os/_nexus, porque a nota
# das OS em aberto vai na sessão do Fracttal de quem importa (o cookie os_sessao só vai para /os). A leitura do GitHub e
# a importação rodam por trás (`etm_historico`); a tela ETMs do administrador acompanha pelo GET.
@bp_raiz.route("/os/_nexus/engenharia/etm/historico", methods=["GET", "POST"])
def engenharia_etm_historico():
    from urllib.parse import quote, urlencode

    from flask import jsonify

    from ...engenharia import etm_historico as H
    from ..moldura import _de_outro_site
    if not session.get("admin"):
        return jsonify({"erro": "Só o administrador traz o histórico do app de ETM."}), 403
    if request.method == "GET":
        return jsonify(H.estado_do_job())
    if _de_outro_site():
        return jsonify({"erro": "Pedido de outro site: nada foi feito."}), 403
    app = current_app._get_current_object()
    acao = (request.get_json(silent=True) or {}).get("acao")
    if acao == "ler":
        token = str(app.config.get("NEXUS_ETM_GITHUB_TOKEN") or "").strip()
        repo = str(app.config.get("NEXUS_ETM_GITHUB_REPO") or "").strip()
        if not token or not repo:
            return jsonify({"erro": "Falta no .env do Nexus: NEXUS_ETM_GITHUB_TOKEN (um token que leia as Issues do "
                                    "repositório do app de ETM) e NEXUS_ETM_GITHUB_REPO (dono/nome)."}), 400
        return jsonify(H.iniciar_leitura(app, token, repo)), 202
    if acao == "importar":
        s = sessao_do_os(app)
        jwt = str(s.get("jwt") or "")
        if not jwt:
            login = na_raiz("/os/login") + "?next=" + quote(
                "/os/_nexus/card/voltar?" + urlencode({"de": "/t/engenharia/etm"}, safe="/"), safe="")
            return jsonify({"erro": "Para a nota das OS em aberto, entre pelo Fracttal.", "login": login}), 401
        email = str((s.get("conta") or {}).get("email") or "")
        return jsonify(H.iniciar_importacao(app, lambda o, linhas: _nota_do_historico(app, jwt, email, o, linhas))), 202
    return jsonify({"erro": "Ação desconhecida."}), 400


def _nota_do_historico(app, jwt: str, email: str, o: dict, linhas: list[str]) -> str:
    """As linhas do histórico na nota de uma OS aberta, na sessão do Fracttal de quem importa (por trás, fora do pedido)."""
    from ...engenharia import etm_historico as H
    clone(app)                                   # põe o `api` do clone no sys.path
    import api as os_api                         # noqa: E402
    from os_web import os_acoes_web as regra     # noqa: E402
    from os_web import sessao as os_sessao       # noqa: E402
    with _trava_nota, os_sessao.contexto(jwt, email):
        try:
            return _acrescentar_na_nota(os_api, regra, o, linhas)
        except os_api.SessionExpired as e:
            raise H.SessaoVencida(str(e)) from e
        except os_api.FracttalError as e:
            # o token vencido que não renova chega como FracttalError: com a sessão morta, a importação para e pede o
            # login, em vez de adiar todas as OS que faltam (revisão final de 26/10/2026)
            if os_sessao.morta():
                raise H.SessaoVencida(str(e)) from e
            raise

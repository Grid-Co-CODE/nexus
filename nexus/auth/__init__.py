"""Portão de login do Nexus.

Desde 06/10/2026 a pessoa entra com o login do Fracttal (Levi: "Ao invés de uma senha difícil, no início faça a pessoa
logar com fractall"; `fracttal.py`). A senha de admin ficou como reserva ("Entrar com a senha de administrador"): é
ela que abre o Cadastro (admin), além de quem estiver em NEXUS_ADMINS. As torres só enxergam a sessão:
`logado`, `admin`, `usuario` {email, nome, perfil} e, para quem tem papel no campo, `supervisor_padrao` (o filtro que já
vem marcado no Campo · App e quem pode aprovar OS; o papel da estrutura de O&M de 10/2026).

A sessão que nasceu do login do Fracttal vale enquanto a do Fracttal valer (Levi, 09/10/2026: "quando deslogar do
Fracttal deslogue do Nexus, tem que pedir para logar de novo"). O portão encerra as duas juntas (`encerrar`) quando:
- a pessoa sai pelo OS Creator (o "sair" dele, "Sair do Fracttal nesta área": sair, de qualquer lugar, sai de tudo);
- o token do Fracttal vence (`fracttal_exp`, o `exp` do JWT guardado no login);
- num pedido de /os (o único caminho que recebe o cookie do OS Creator), o JWT sumiu ou venceu.
A ponte do OS Creator (`torres/oscreator/ponte.py`) encerra quando o Fracttal recusa o token no meio de um pedido, e a
página confere a cada 5 minutos (`/os/_nexus/sessao`) se ele não foi derrubado por fora. A senha de administrador não
depende do Fracttal: só o "sair" a encerra.
"""
import hmac
import time
from collections import defaultdict, deque
from urllib.parse import urlsplit

from flask import (Blueprint, current_app, jsonify, make_response, redirect, render_template, request, session,
                   url_for)

from . import fracttal
from ..prefixo import na_raiz, raiz

bp = Blueprint("auth", __name__)

# a foto do extintor que o App envia (Segurança · HSEQ, 09/10/2026) não tem sessão: a rota confere a assinatura HMAC
# dela antes de gravar qualquer coisa (`nexus/hseq/fotos.receber`); só ela passa sem login, e só por POST
ROTAS_PUBLICAS = {"auth.entrar", "casca.saude", "static", "torre_hseq.extintores_foto_receber"}

# Limite de tentativas por IP. Em memória: zera no restart, o que é aceitável enquanto só o admin
# entra. Sem isso, a senha única ficaria aberta a tentativa em massa assim que o servidor subir.
# Fica em app.extensions, não em variável global, para cada app (e cada teste) ter a sua contagem.
MAX_ERROS = 5
JANELA_S = 15 * 60

# Por que a pessoa voltou ao login (o aviso no alto da tela de entrada). Só estes textos aparecem: o motivo que chega
# pelo endereço é uma CHAVE daqui, nunca texto livre.
MOTIVOS = {
    "saiu": "Você saiu do Fracttal, e o Nexus saiu junto. Entre de novo para continuar.",
    "caiu": "A sua sessão do Fracttal terminou, e o Nexus saiu junto. Entre de novo para continuar.",
    "venceu": "A sua sessão do Fracttal venceu (ela dura cerca de 12 horas), e o Nexus saiu junto. Entre de novo para "
              "continuar.",
}
# Pedidos de DADOS de /os quando o navegador não diz o destino (Sec-Fetch-Dest): a resposta vira 401 em JSON, não a
# página de login
_DADOS_DO_OS = ("/os/api/", "/os/_nexus/quem", "/os/_nexus/sessao")


def _erros() -> dict[str, deque]:
    return current_app.extensions["nexus_erros_login"]


def _ip() -> str:
    return request.remote_addr or "?"


def _bloqueado(ip: str) -> bool:
    fila = _erros()[ip]
    agora = time.monotonic()
    while fila and agora - fila[0] > JANELA_S:
        fila.popleft()
    return len(fila) >= MAX_ERROS


def next_seguro(valor: str | None) -> str:
    """Só aceita caminho do próprio site. '//x' e '/\\x' o navegador lê como outro domínio."""
    if not valor or not valor.startswith("/") or valor.startswith("//") or valor.startswith("/\\"):
        return "/"
    return valor


def destino_seguro(valor: str | None) -> str:
    """O `next_seguro` como o navegador o pede: debaixo do prefixo, `/t/x` vira `/nexus/t/x` (e o que já vem com ele,
    como o `next` que a camada da T.I. reescreve, fica como está). Para todo redirecionamento a um `next`/`voltar`."""
    return na_raiz(next_seguro(valor))


def os_cookie_path() -> str:
    """O caminho do cookie do OS Creator embutido (`os_sessao`): o /os do Nexus, debaixo do prefixo em que ele roda.
    Com `/os` fixo, debaixo de `/nexus` ele não ia ao `/nexus/os/...` e ia ao `/os/` da PLATAFORMA (spec 5.1)."""
    return raiz() + "/os"


def _admins() -> set[str]:
    return {e.strip().lower() for e in str(current_app.config.get("NEXUS_ADMINS") or "").split(",") if e.strip()}


def via_fracttal() -> bool:
    """A sessão do Nexus nasceu do login do Fracttal? (a senha de administrador não põe `usuario`)"""
    return bool(session.get("logado") and session.get("usuario"))


def quer_pagina() -> bool:
    """O pedido é uma página (a janela ou uma moldura navegando) ou dados (fetch)? Pelo Sec-Fetch-Dest que o navegador
    manda; sem ele, só os caminhos de dados do OS Creator contam como dados."""
    destino = request.headers.get("Sec-Fetch-Dest")
    if destino:
        return destino in ("document", "iframe", "frame", "embed", "object")
    return not (request.is_json or request.path.startswith(_DADOS_DO_OS) or request.path.endswith("/assinatura-tecnico"))


def _destino_do_pedido() -> str:
    """Para onde voltar depois do login: a página pedida; num POST (a decisão da PT), a tela de onde ele saiu."""
    if request.method == "GET":
        return request.full_path.rstrip("?")
    volta = request.form.get("volta") or ""
    if volta.startswith("/") and not volta.startswith("//"):
        return volta
    ref = urlsplit(request.referrer or "")
    return ref.path + (f"?{ref.query}" if ref.query else "") if ref.netloc == request.host and ref.path else "/"


def encerrar(motivo: str | None = None, destino: str | None = None, json: bool | None = None):
    """Encerra a sessão do Nexus e a do OS Creator juntas e manda ao login dizendo por quê (MOTIVOS). O motivo também
    fica na sessão (sem login), para chegar à tela de entrada mesmo quando quem leva até ela é o portão. Pedido de dados
    recebe 401 em JSON, com o "login": true que as telas do OS Creator já entendem e o endereço do login; a página que
    fez o pedido é quem diz para onde voltar."""
    if json is None:
        json = not quer_pagina()
    session.clear()
    if motivo:
        session["motivo_entrar"] = motivo
    q = {}
    if destino and not json and next_seguro(destino) != "/":
        # o `next` como o navegador o vê (com o prefixo), como o do portão; o Entrar aceita com ou sem ele
        q["next"] = destino_seguro(destino)
    if motivo:
        q["motivo"] = motivo
    url = url_for("auth.entrar", **q)
    if json:
        resp = jsonify({"ok": False, "login": True, "sessao_encerrada": True, "entrar": url,
                        "erro": MOTIVOS.get(motivo, "A sua sessão terminou. Entre de novo para continuar.")})
        resp.status_code = 401
    else:
        resp = redirect(url)
    # o OS Creator sai junto: o cookie dele mora no /os do Nexus, debaixo do prefixo (porta única, spec 5.1); com "/os"
    # fixo, debaixo de /nexus o delete não casava com o cookie e a sessão do OS Creator ficava
    resp.delete_cookie("os_sessao", path=os_cookie_path())
    # e o nexus_sessao velho de Path=/ (entre publicar o código e pôr a NEXUS_PREFIXO), como no Sair
    return _sem_a_sessao_velha_da_raiz(resp)


def _fim_do_fracttal() -> tuple[str | None, object]:
    """Para a sessão que nasceu do login do Fracttal: (motivo de ela ter acabado, None) ou (None, resposta) quando o
    pedido tem outro destino, ou (None, None) quando ela vale e o pedido segue."""
    exp = session.get("fracttal_exp")
    if exp and time.time() >= float(exp):
        return "venceu", None
    caminho = request.path
    if not caminho.startswith("/os/") or caminho.startswith(("/os/static/", "/os/assets/")):
        return None, None
    # só os pedidos de /os trazem o cookie do OS Creator, onde mora o JWT do Fracttal
    try:
        from ..torres.oscreator import ponte
        jwt = str(ponte.sessao_do_os(current_app._get_current_object()).get("jwt") or "")
    except Exception:            # noqa: BLE001 — clone que não sobe: a ponte mostra o aviso dela; a sessão não cai por isso
        return None, None
    if not jwt:
        return "caiu", None
    exp = fracttal.exp_do_jwt(jwt)
    if exp and time.time() >= exp:
        return "venceu", None
    if caminho == "/os/login" and request.method == "GET":
        # o login do OS Creator é o do Nexus, e a pessoa já entrou nos dois: segue para onde ia (o "entre com o seu login
        # do Fracttal" das telas leva para cá com a volta no next)
        # (o `next` do clone vem sem o prefixo; o redirecionamento sai com ele, como o navegador pede)
        return None, redirect(destino_seguro(request.args.get("next")) if request.args.get("next") else na_raiz("/os/"))
    return None, None


def _supervisor_padrao(email: str, nome: str) -> dict:
    """O papel de quem entrou na estrutura de O&M de 10/2026 (Levi, 06/10: "Quando um supervisor logar, o filtro
    supervisor já fica para a pessoa automaticamente"): {"pessoa_id", "nome", "papel" (supervisor_campo, coordenador ou
    gestor), "regioes" ou "gestor"}. O Supervisor de Campo entra filtrado na região dele, o Gestor de contrato nas usinas
    dele e o Coordenador vê tudo (`nexus/campo/visao.py`, `papel_da_pessoa`). Falha aqui não impede a entrada."""
    try:
        from ..campo import visao
        return visao.papel_no_campo(email, nome)
    except Exception:       # noqa: BLE001 — sem cadastro ou banco fora: entra sem o filtro
        return {}


def _entrar_fracttal(destino):
    email = (request.form.get("email") or "").strip()
    try:
        conta = fracttal.entrar(current_app._get_current_object(), email, request.form.get("senha") or "")
    except fracttal.LoginRecusado as e:
        _erros()[_ip()].append(time.monotonic())
        return _tela_entrar(erro=str(e), email=email, destino=destino), 401
    _erros().pop(_ip(), None)
    session.clear()
    session.permanent = True
    session["logado"] = True
    session["usuario"] = {k: conta[k] for k in ("email", "nome", "perfil")}
    session["admin"] = conta["email"] in _admins()
    if conta.get("exp"):
        session["fracttal_exp"] = conta["exp"]       # o Nexus vale enquanto o token do Fracttal valer
    sup = _supervisor_padrao(conta["email"], conta["nome"])
    if sup:
        session["supervisor_padrao"] = sup
    resp = redirect(na_raiz(destino))
    nome, valor, idade = conta["cookie"]
    # a sessão do OS Creator (o JWT do Fracttal) nasce junto: o /os/ e a aprovação de PT abrem sem pedir de novo
    resp.set_cookie(nome, valor, max_age=idade, path=os_cookie_path(), httponly=True, samesite="Lax",
                    secure=bool(current_app.config.get("SESSION_COOKIE_SECURE")))
    return _sem_a_sessao_velha_da_raiz(resp)


def _sem_a_sessao_velha_da_raiz(resp):
    """Debaixo do prefixo, apaga também o `nexus_sessao` de Path=/ (revisão de 10/10/2026).

    Entre publicar o código e pôr a NEXUS_PREFIXO (DEPLOY 5a), quem entrou recebeu o cookie em Path=/ (atrás do Caddy
    que corta o /nexus, a raiz é ''). Depois, o Nexus grava em Path=/nexus, mas o velho continua indo a /nexus/* e
    continua válido (mesma NEXUS_SECRET_KEY, até 12 h): o Sair apagava só o novo, e a pessoa seguia logada, talvez
    como admin; num PC de campo, o próximo entrava com a sessão do anterior. Na raiz (o PC, a fase 4) o cookie de Path=/
    É o da sessão: nada a fazer. O nome é o do Nexus; o `session` da plataforma não é tocado. Só quando o pedido trouxe
    o cookie (o navegador não diz o caminho dele): quem chega sem nenhum não ganha um Set-Cookie a mais."""
    cfg = current_app.config
    if raiz() and cfg["SESSION_COOKIE_NAME"] in request.cookies:
        resp.delete_cookie(cfg["SESSION_COOKIE_NAME"], path="/", secure=bool(cfg.get("SESSION_COOKIE_SECURE")),
                           httponly=True, samesite=cfg.get("SESSION_COOKIE_SAMESITE"))
    return resp


@bp.route("/entrar", methods=["GET", "POST"])
def entrar():
    destino = next_seguro(request.args.get("next"))
    admin = request.args.get("admin") == "1"
    if request.method == "GET":
        guardado = session.pop("motivo_entrar", None)
        motivo = request.args.get("motivo")
        motivo = motivo if motivo in MOTIVOS else (guardado if guardado in MOTIVOS else None)
        return _tela_entrar(erro=None, destino=destino, admin=admin, motivo=motivo, aviso=MOTIVOS.get(motivo))

    ip = _ip()
    if _bloqueado(ip):
        return _tela_entrar(erro="Muitas tentativas. Aguarde 15 minutos.",
                               destino=destino, admin=admin), 429

    if request.form.get("email") is not None:
        return _entrar_fracttal(destino)

    senha = request.form.get("senha", "")
    certa = current_app.config["NEXUS_SENHA_ADMIN"]
    if not hmac.compare_digest(senha.encode(), certa.encode()):
        _erros()[ip].append(time.monotonic())
        return _tela_entrar(erro="Senha incorreta.", destino=destino, admin=True), 401

    _erros().pop(ip, None)
    session.clear()
    session.permanent = True
    session["logado"] = True
    session["admin"] = True
    return _sem_a_sessao_velha_da_raiz(redirect(na_raiz(destino)))


def _tela_entrar(**contexto):
    """A página do Entrar. Com a porta única ligada, ela encerra a sessão do passe que estiver aberta na plataforma neste
    navegador (`plataforma_sair`, revisão de 10/10/2026): num PC compartilhado (a sala do NOC), A não clica em Sair, a
    sessão dele no Nexus vence e B entra; a de A na plataforma valia mais 12 h, e todo acesso direto à plataforma
    (favorito, aba aberta) seguia como A, com o e-mail de A no diário. Sem a chave, a página de sempre."""
    return render_template("entrar.html", plataforma_sair=_plataforma_para_sair(), **contexto)


def _plataforma_para_sair() -> str | None:
    """A base da plataforma de Performance quando a porta única está ligada ('' = a mesma origem), ou None. A mesma
    conta das telas (`estado_da_porta`, com a conferência da origem deste pedido, revisão de 10/10/2026): com a
    NEXUS_PLATAFORMA_URL interna e o Nexus aberto por fora, o POST do Sair iria à máquina de quem está saindo."""
    from ..torres.moldura import estado_da_porta
    estado = estado_da_porta()
    return estado["plataforma"] if estado["ligada"] else None


@bp.route("/sair")
def sair():
    session.clear()
    plataforma = _plataforma_para_sair()
    if plataforma is None:
        resp = redirect(url_for("auth.entrar"))
    else:
        # Porta única (spec 5.2): o Sair do Nexus passa por /painel/nexus/sair da plataforma (POST, mesma origem), que
        # encerra a sessão que o passe abriu lá; sem isso, quem sai do Nexus continuava gravando na Performance pelo
        # mesmo navegador por até 12 h. A página faz o POST e segue para o Entrar (sem JavaScript, um botão).
        resp = make_response(render_template("sair.html", plataforma=plataforma))
        resp.headers["Cache-Control"] = "no-store"
    resp.delete_cookie("os_sessao", path=os_cookie_path())      # sai do OS Creator junto
    return _sem_a_sessao_velha_da_raiz(resp)


def instalar_portao(app) -> None:
    @app.before_request
    def _portao():
        if request.endpoint in ROTAS_PUBLICAS:
            return None
        if not session.get("logado"):
            # o `next` como o navegador o vê (com o prefixo): o endereço a que a pessoa volta depois de entrar
            return redirect(url_for("auth.entrar", next=na_raiz(request.full_path.rstrip("?"))))
        if request.path == "/os/logout":
            # o "sair" do OS Creator ("Sair do Fracttal nesta área") sai do Nexus também, como o Sair do Nexus sai do OS
            # Creator: sair, de qualquer lugar, sai de tudo
            return encerrar("saiu", json=False)
        if request.endpoint == "auth.sair" or not via_fracttal():
            return None
        motivo, resposta = _fim_do_fracttal()
        if motivo:
            return encerrar(motivo, _destino_do_pedido())
        return resposta

    app.extensions["nexus_erros_login"] = defaultdict(deque)

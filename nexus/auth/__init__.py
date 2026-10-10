"""Portão de login do Nexus.

Desde 06/10/2026 a pessoa entra com o login do Fracttal (Levi: "Ao invés de uma senha difícil, no início faça a pessoa
logar com fractall"; `fracttal.py`). A senha de admin ficou como reserva ("Entrar com a senha de administrador"): é
ela que abre o Cadastro (admin), além de quem estiver em NEXUS_ADMINS. As torres só enxergam a sessão:
`logado`, `admin`, `usuario` {email, nome, perfil} e, para quem tem papel no campo, `supervisor_padrao` (o filtro que já
vem marcado no Campo · App e quem pode aprovar OS; o papel da estrutura de O&M de 10/2026).
"""
import hmac
import time
from collections import defaultdict, deque

from flask import (Blueprint, current_app, make_response, redirect, render_template, request, session,
                   url_for)

from . import fracttal
from ..prefixo import na_raiz, raiz

bp = Blueprint("auth", __name__)

ROTAS_PUBLICAS = {"auth.entrar", "casca.saude", "static"}

# Limite de tentativas por IP. Em memória: zera no restart, o que é aceitável enquanto só o admin
# entra. Sem isso, a senha única ficaria aberta a tentativa em massa assim que o servidor subir.
# Fica em app.extensions, não em variável global, para cada app (e cada teste) ter a sua contagem.
MAX_ERROS = 5
JANELA_S = 15 * 60


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
        return render_template("entrar.html", erro=str(e), email=email, destino=destino), 401
    _erros().pop(_ip(), None)
    session.clear()
    session.permanent = True
    session["logado"] = True
    session["usuario"] = {k: conta[k] for k in ("email", "nome", "perfil")}
    session["admin"] = conta["email"] in _admins()
    sup = _supervisor_padrao(conta["email"], conta["nome"])
    if sup:
        session["supervisor_padrao"] = sup
    resp = redirect(na_raiz(destino))
    nome, valor, idade = conta["cookie"]
    # a sessão do OS Creator (o JWT do Fracttal) nasce junto: o /os/ e a aprovação de PT abrem sem pedir de novo
    resp.set_cookie(nome, valor, max_age=idade, path=os_cookie_path(), httponly=True, samesite="Lax",
                    secure=bool(current_app.config.get("SESSION_COOKIE_SECURE")))
    return resp


@bp.route("/entrar", methods=["GET", "POST"])
def entrar():
    destino = next_seguro(request.args.get("next"))
    admin = request.args.get("admin") == "1"
    if request.method == "GET":
        return render_template("entrar.html", erro=None, destino=destino, admin=admin)

    ip = _ip()
    if _bloqueado(ip):
        return render_template("entrar.html", erro="Muitas tentativas. Aguarde 15 minutos.",
                               destino=destino, admin=admin), 429

    if request.form.get("email") is not None:
        return _entrar_fracttal(destino)

    senha = request.form.get("senha", "")
    certa = current_app.config["NEXUS_SENHA_ADMIN"]
    if not hmac.compare_digest(senha.encode(), certa.encode()):
        _erros()[ip].append(time.monotonic())
        return render_template("entrar.html", erro="Senha incorreta.", destino=destino, admin=True), 401

    _erros().pop(ip, None)
    session.clear()
    session.permanent = True
    session["logado"] = True
    session["admin"] = True
    return redirect(na_raiz(destino))


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
    return resp


def instalar_portao(app) -> None:
    @app.before_request
    def _portao():
        if request.endpoint in ROTAS_PUBLICAS or session.get("logado"):
            return None
        # o `next` como o navegador o vê (com o prefixo): o endereço a que a pessoa volta depois de entrar
        return redirect(url_for("auth.entrar", next=na_raiz(request.full_path.rstrip("?"))))

    app.extensions["nexus_erros_login"] = defaultdict(deque)

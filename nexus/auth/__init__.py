"""Portão de login do Nexus.

Nesta fase a entrada é uma senha de admin só. O login Microsoft (Entra) foi deixado de lado em
29/09/2026; quando voltar, entra aqui, e as torres não percebem a troca porque só enxergam a sessão.
"""
import hmac
import time
from collections import defaultdict, deque

from flask import (Blueprint, current_app, redirect, render_template, request, session,
                   url_for)

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


@bp.route("/entrar", methods=["GET", "POST"])
def entrar():
    destino = next_seguro(request.args.get("next"))
    if request.method == "GET":
        return render_template("entrar.html", erro=None, destino=destino)

    ip = _ip()
    if _bloqueado(ip):
        return render_template("entrar.html", erro="Muitas tentativas. Aguarde 15 minutos.",
                               destino=destino), 429

    senha = request.form.get("senha", "")
    certa = current_app.config["NEXUS_SENHA_ADMIN"]
    if not hmac.compare_digest(senha.encode(), certa.encode()):
        _erros()[ip].append(time.monotonic())
        return render_template("entrar.html", erro="Senha incorreta.", destino=destino), 401

    _erros().pop(ip, None)
    session.clear()
    session.permanent = True
    session["logado"] = True
    session["admin"] = True
    return redirect(destino)


@bp.route("/sair")
def sair():
    session.clear()
    return redirect(url_for("auth.entrar"))


def instalar_portao(app) -> None:
    @app.before_request
    def _portao():
        if request.endpoint in ROTAS_PUBLICAS or session.get("logado"):
            return None
        return redirect(url_for("auth.entrar", next=request.full_path.rstrip("?")))

    app.extensions["nexus_erros_login"] = defaultdict(deque)

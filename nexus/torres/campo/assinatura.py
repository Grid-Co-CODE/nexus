"""Quem assina a PT no Nexus: o login do Fracttal do OS Creator (Levi, 05/10/2026: "utilize o login do fractal do OS
Creator Web que já dá certo!").

O OS Creator roda dentro do Nexus (`nexus/torres/oscreator/ponte.py`) com sessão própria no cookie `os_sessao`, que o
navegador só manda para /os. Por isso estas rotas moram em /os/_nexus/...: o roteador do Flask casa a parte fixa antes
do `/os/<path>` da ponte, e a sessão do OS Creator é aberta aqui com a chave dele, só para ler o e-mail de quem entrou.
O portão do Nexus vale antes (quem não entrou no Nexus não chega aqui).
"""
import base64
import json
import time
from urllib.parse import quote, urlsplit

from flask import Blueprint, current_app, jsonify, redirect, request, session

from ...campo import decisao_pt

bp_assinatura = Blueprint("campo_assinatura", __name__)


def _carga(jwt: str) -> dict | None:
    """O que o JWT do Fracttal diz (e-mail, validade), sem pedido ao Fracttal. Token opaco = None."""
    try:
        p = jwt.split(".")[1]
        p += "=" * (-len(p) % 4)
        return json.loads(base64.urlsafe_b64decode(p.encode()))
    except Exception:          # noqa: BLE001
        return None


def _jwt_vivo(jwt: str) -> bool:
    """O JWT ainda vale, pelo `exp` dele (a cota do Fracttal é da empresa inteira: nada de pedido só para conferir).
    Token opaco vale enquanto a sessão do OS Creator valer (12 h)."""
    c = _carga(jwt)
    exp = (c or {}).get("exp")
    return bool(jwt) and (not exp or float(exp) > time.time())


def quem_assina() -> dict:
    """{"email", "nome"} de quem entrou no Fracttal pelo OS Creator, ou {} (sem login, ou o token venceu)."""
    from ..oscreator import ponte
    clone = ponte.clone(current_app._get_current_object())
    s = clone.session_interface.open_session(clone, request) or {}
    jwt = str(s.get("jwt") or "")
    if not jwt or not _jwt_vivo(jwt):
        return {}
    conta = s.get("conta") or {}
    email = str(conta.get("email") or (_carga(jwt) or {}).get("email") or "").strip().lower()
    return {"email": email, "nome": str(conta.get("nome") or email)} if email else {}


def _tela(numero) -> str:
    return f"/t/campo/pt/{quote(str(numero), safe='')}"


def _login(numero) -> str:
    # o OS Creator só devolve para /os/...: a volta passa por /os/_nexus/pt/<n>/voltar
    return "/os/login?next=" + quote(f"/os/_nexus/pt/{quote(str(numero), safe='')}/voltar", safe="")


@bp_assinatura.route("/os/_nexus/quem")
def quem():
    q = quem_assina()
    return jsonify({"email": q.get("email", ""), "nome": q.get("nome", "")})


@bp_assinatura.route("/os/_nexus/pt/<numero>/voltar")
def voltar(numero):
    return redirect(_tela(numero))


@bp_assinatura.route("/os/_nexus/pt/<numero>/decidir", methods=["POST"])
def decidir(numero):
    # pedido de outro site não decide PT (o cookie Lax já barra; a origem confere de novo, porque é segurança do campo)
    origem = request.headers.get("Origin")
    if origem and urlsplit(origem).netloc != request.host:
        return "Origem recusada.", 403
    q = quem_assina()
    if not q:
        return redirect(_login(numero))
    try:
        decisao_pt.decidir(numero, request.form.get("decisao", ""), request.form.get("motivo", ""), q["email"])
    except decisao_pt.Recusada as e:
        session["pt_aviso"] = str(e)
        return redirect(_tela(numero))
    except Exception as e:      # noqa: BLE001 — banco fora do ar: a tela diz, nada é dado como gravado
        session["pt_aviso"] = f"Não consegui gravar a decisão no banco ({type(e).__name__}). Nada foi salvo."
        return redirect(_tela(numero))
    return redirect(_tela(numero) + "?gravada=1")

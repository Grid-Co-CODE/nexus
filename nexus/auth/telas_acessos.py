"""Tela Base → Acessos (11/10/2026): quem é administrador do Nexus, dar e tirar pela tela, e quem entrou em 30 dias.

Só administrador vê e grava (quem não é recebe a página "só para administradores" do Cadastro, com o porquê). O dado e
as regras moram em `acessos.py`; aqui ficam a página e o portão do POST:
- só da própria página: o `Sec-Fetch-Site`/`Origin` com a mesma régua da moldura da Performance (`_de_outro_site`) e um
  código do formulário guardado na sessão (o cookie `Lax` já barra o POST de outro site; dar administrador é a ação
  mais sensível do Nexus, então confere duas vezes);
- POST que grava volta por 303 à tela (F5 não repete), com o aviso guardado na sessão.
"""
import hmac
import logging
import secrets

from flask import current_app, redirect, render_template, request, session, url_for

from . import acessos as A
from . import admins_do_servidor

log = logging.getLogger(__name__)

_CHAVE_CODIGO = "acessos_codigo"
_CHAVE_AVISO = "acessos_aviso"


def _meu_email() -> str:
    u = session.get("usuario")
    return str(u.get("email") or "").strip().lower() if isinstance(u, dict) else ""


def _quem() -> str:
    """Quem fez a mudança, para a lista e a auditoria: o e-mail do Fracttal, ou "senha de administrador"."""
    return _meu_email() or A.SENHA_DE_ADMIN


def _codigo() -> str:
    """O código do formulário desta sessão (nasce na 1ª visita; o login limpa a sessão e troca o código)."""
    if not session.get(_CHAVE_CODIGO):
        session[_CHAVE_CODIGO] = secrets.token_urlsafe(24)
    return session[_CHAVE_CODIGO]


def _de_outro_site() -> bool:
    from ..torres.moldura import _de_outro_site as regra
    return regra()


def _linhas_de_admins(servidor: set[str], est: dict, ultimo: dict) -> list[dict]:
    eu = _meu_email()
    linhas = [{"email": e, "origem": "servidor", "por": "", "quando": "", "ultimo": ultimo.get(e, ""),
               "eu": e == eu} for e in sorted(servidor)]
    for a in sorted(est["admins"], key=lambda x: x["email"]):
        linhas.append({"email": a["email"], "origem": "tela", "por": a["por"], "quando": A.hora_br(a["quando"]),
                       "ultimo": ultimo.get(a["email"], ""), "eu": a["email"] == eu,
                       "tambem_servidor": a["email"] in servidor})
    return linhas


def _pagina(erro: str | None = None, status: int = 200, email_digitado: str = ""):
    cfg = current_app.config
    servidor = admins_do_servidor()
    est = A.estado(cfg)
    da_tela = {a["email"] for a in est["admins"]}
    logins = [dict(x, quando_br=A.hora_br(x["quando"])) for x in A.logins_recentes(cfg)]
    ultimo = {x["email"]: x["quando_br"] for x in logins}
    for x in logins:
        x["senha"] = x["email"] == A.SENHA_DE_ADMIN
        x["admin"] = ("sempre" if x["senha"] else "do servidor" if x["email"] in servidor
                      else "pela tela" if x["email"] in da_tela else "")
    admins = _linhas_de_admins(servidor, est, ultimo)
    contexto = {
        "admins": admins, "auditoria": [dict(x, quando_br=A.hora_br(x.get("quando"))) for x in est["auditoria"]],
        "logins": logins, "sem_pasta": est["sem_pasta"], "arquivo_erro": est["erro"],
        "total_servidor": len(servidor), "total_tela": len(da_tela - servidor), "n_tela": len(da_tela),
        "pessoas_30d": sum(1 for x in logins if not x["senha"]),
        "admins_30d": sum(1 for x in logins if x["admin"] in ("do servidor", "pela tela")),
        "codigo": _codigo(), "erro": erro, "aviso": session.pop(_CHAVE_AVISO, None),
        "email_digitado": email_digitado, "eu": _meu_email(), "max_logins": A.MAX_LOGINS,
        "pode_gravar": not est["sem_pasta"] and not est["erro"],
    }
    return render_template("acessos/acessos.html", **contexto), status


def _sem_permissao():
    return render_template("cadastro/sem_permissao.html", titulo="Acessos", eyebrow="Base · Acessos",
                           area="A tela Acessos", email=_meu_email()), 403


def _gravar():
    if _de_outro_site():
        return _pagina(erro="Pedido de outro site: nada foi gravado.", status=403)
    certo = session.get(_CHAVE_CODIGO) or ""
    enviado = request.form.get("codigo") or ""
    if not certo or not hmac.compare_digest(enviado.encode(), certo.encode()):
        return _pagina(erro="O formulário venceu (a sessão mudou desde que a tela abriu): abra a tela de novo. Nada foi "
                            "gravado.", status=403)
    cfg = current_app.config
    acao = request.form.get("acao")
    digitado = (request.form.get("email") or "")[:300]
    try:
        if acao == "adicionar":
            e = A.adicionar(cfg, digitado, _quem(), admins_do_servidor())
            aviso = (f"{e} agora é administrador do Nexus. Vale no próximo clique da pessoa no Nexus, sem precisar "
                     "sair e entrar.")
        elif acao == "remover":
            e = A.remover(cfg, digitado, _quem(), admins_do_servidor(), eu=_meu_email(),
                          confirmo=request.form.get("confirmo") == "1")
            aviso = f"{e} deixou de ser administrador do Nexus. Vale no próximo clique da pessoa no Nexus."
        else:
            return _pagina(erro="Ação desconhecida: nada foi gravado.", status=400)
    except A.Recusado as ex:
        return _pagina(erro=str(ex), status=400, email_digitado=digitado if acao == "adicionar" else "")
    except A.Ilegivel as ex:
        return _pagina(erro=f"Não gravei: {ex}. Gravar agora apagaria o que está nele; avise a T.I.", status=409)
    except OSError as ex:
        log.error("Acessos: a gravação falhou (%s: %s); nada mudou.", type(ex).__name__, ex)
        return _pagina(erro=f"Não consegui gravar no disco ({type(ex).__name__}): nada mudou. Tente de novo; se "
                            "continuar, avise a T.I.", status=500)
    log.info("Acessos: %s %s (por %s).", "adicionou" if acao == "adicionar" else "removeu", e, _quem())
    if e == _meu_email() and acao == "remover":
        # tirou o próprio acesso: a tela já não abre para ele no próximo pedido; o Início não tem por que recusar
        return redirect(url_for("casca.inicio"), code=303)
    session[_CHAVE_AVISO] = aviso
    return redirect(url_for("torre_base.acessos"), code=303)


def registrar_acessos(bp) -> None:
    """Pendura a tela na torre Base (`/t/base/acessos`), vencendo o placeholder."""
    @bp.route("/acessos", methods=["GET", "POST"])
    def acessos():
        if not session.get("admin"):
            return _sem_permissao()
        if request.method == "POST":
            return _gravar()
        return _pagina()

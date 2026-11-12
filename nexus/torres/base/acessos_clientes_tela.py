"""Base › Acessos dos clientes: as contas por pessoa do Dashboard Thopen (14/10/2026), vindas da torre Contratos e
clientes em 12/11/2026 (Levi: "Joga o acesso cliente lá para bases [...] Essa parte de contrato e clientes aqui vai
sumir, vai ser absorvido por outras seções").

As regras não mudaram de lugar: `nexus/contratos/acessos_clientes.py` e o `nexus/contratos/CLAUDE.md`. O endereço antigo
(`/t/contratos/acessos`) leva a este, e a marca que o setor tinha na tela antiga vale para a nova
(`setor_telas.RENOMEADAS`). Não é o Base › Acessos (o que cada setor do Nexus vê): aqui são as contas dos clientes no
painel do Thopen.
"""
import hmac
import logging
import secrets

from flask import current_app, redirect, render_template, request, session

from ...auth.origem import de_outro_site as _de_outro_site
from ...contratos import acessos_clientes as AC
from ...prefixo import na_raiz

_log = logging.getLogger(__name__)
ENDERECO = "/t/base/acessos-clientes"
# chaves próprias na sessão: o aviso desta tela não pode aparecer em outra
_AC_CODIGO, _AC_AVISO, _AC_LINK = "acessos_clientes_codigo", "acessos_clientes_aviso", "acessos_clientes_link"


def _codigo() -> str:
    if not session.get(_AC_CODIGO):
        session[_AC_CODIGO] = secrets.token_urlsafe(24)
    return session[_AC_CODIGO]


def registrar_acessos_clientes(bp, torre) -> None:
    def _acessos(erro=None, status=200, form=None):
        d = AC.contas()
        resp = current_app.make_response((render_template(
            "acessos_dos_clientes.html", torre=torre, tela=torre.tela("acessos-clientes"), d=d,
            admin=bool(session.get("admin")), carteiras=AC.CARTEIRAS, papeis=AC.PAPEIS, codigo=_codigo(), erro=erro,
            form=form or {}, aviso=session.pop(_AC_AVISO, None), link=session.pop(_AC_LINK, None),
            horas=AC.CONVITE_HORAS), status))
        resp.headers["Cache-Control"] = "no-store"     # o link de definir senha aparece uma vez: nada de cópia em cache
        return resp

    @bp.route("/acessos-clientes", methods=["GET", "POST"])
    def acessos_clientes():
        """As contas do Dashboard Thopen: quem é, que carteiras vê, se está ativa, quando definiu a senha e se há link
        pendente. Só administrador age (nova conta, gerar link, desativar, reativar); POST só da própria página e com o
        código do formulário da sessão. O link aparece uma vez (guardado na sessão até a volta do 303)."""
        if request.method == "GET":
            return _acessos()
        if not session.get("admin"):
            return _acessos(erro="Só um administrador do Nexus cria e muda as contas.", status=403)
        if _de_outro_site():
            return _acessos(erro="Pedido de outro site: nada foi gravado.", status=403)
        certo, enviado = session.get(_AC_CODIGO) or "", request.form.get("codigo") or ""
        if not certo or not hmac.compare_digest(enviado.encode(), certo.encode()):
            return _acessos(erro="O formulário venceu (a sessão mudou desde que a tela abriu): abra a tela de novo. Nada "
                                 "foi gravado.", status=403)
        acao, cid, quem = request.form.get("acao"), request.form.get("conta_id") or "", session.get("usuario")
        form = {}
        try:
            if acao == "criar":
                form = {"nome": request.form.get("nome") or "", "email": request.form.get("email") or "",
                        "carteiras": request.form.getlist("carteira"), "papel": request.form.get("papel") or "cliente"}
                conta, link = AC.criar(form["nome"], form["email"], form["carteiras"], form["papel"], quem)
                session[_AC_LINK] = {"link": link, "nome": conta["nome"], "email": conta["usuario"]}
                session[_AC_AVISO] = f"Conta de {conta['nome']} criada."
            elif acao == "link":
                link = AC.gerar_link(cid, quem)
                nome = next((c["nome"] or c["usuario"] for c in AC.contas()["contas"] if c["conta_id"] == cid), "")
                session[_AC_LINK] = {"link": link, "nome": nome, "email": ""}
                session[_AC_AVISO] = "Link novo gerado; o anterior deixou de valer."
            elif acao in ("desativar", "reativar"):
                AC.definir_status(cid, acao == "reativar", quem)
                session[_AC_AVISO] = ("Conta reativada. Se ela não lembra a senha, gere um link." if acao == "reativar"
                                      else "Conta desativada: sai do painel em até 2 minutos.")
            else:
                raise AC.Recusada("Ação desconhecida: nada mudou.")
        except AC.Recusada as e:
            return _acessos(erro=str(e), status=400, form=form)
        except Exception as e:      # noqa: BLE001 — banco fora: a tela diz, o que foi digitado não se perde
            _log.exception("Acessos dos clientes: a ação %s não gravou", acao)
            return _acessos(erro=f"Não consegui gravar no banco ({type(e).__name__}). Nada mudou; tente de novo em "
                                 "instantes.", status=502, form=form)
        return redirect(na_raiz(ENDERECO), code=303)

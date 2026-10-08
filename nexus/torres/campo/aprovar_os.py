"""O Aprovar da Aprovação de OS, com o portão no servidor (Levi, 08/10/2026: "nessa visão que aparece quando clica no
supervisor, deve ser possível só o supervisor ou ADM conseguir aprovar a OS logando pelo Fracttal").

Aprovar = o Concluir do OS Creator Web (POST /os/api/os/<id>/concluir, a rota do clone), com o login do Fracttal de quem
clica: status 3 + recalculate + reconferência da data de fim. IRREVERSÍVEL. Até 08/10 a tela chamava a rota do clone
direto, e qualquer pessoa com login do Fracttal aprovava qualquer OS da fila. Agora a tela chama
POST /os/_nexus/aprovacao/<id>/aprovar, que:
- só aceita pedido do próprio Nexus (Origin, como a decisão da PT);
- exige o login do Fracttal: o cookie `os_sessao` do OS Creator, que o navegador só manda para /os (por isso a rota mora
  em /os/_nexus, como a assinatura da PT, `assinatura.py`);
- só aprova OS que está na fila guardada (`aprovacao.os_na_fila`, sem pedido ao Fracttal);
- só deixa o SUPERVISOR DA OS (o mesmo que a tela atribui pela usina do Fracttal, pelo cadastro:
  `visao.usinas_do_fracttal`), achado pelo login do Fracttal de quem clica (`visao.supervisor_da_pessoa`, a regra do
  filtro que já vem marcado), ou um ADMINISTRADOR (a sessão de admin do Nexus, que é a de quem está em NEXUS_ADMINS ou
  entrou com a senha de admin, como o Cadastro decide; ou o e-mail do Fracttal em NEXUS_ADMINS). Os demais levam 403,
  inclusive quem montar o pedido à mão;
- repassa ao clone o MESMO pedido que a tela fazia e, aprovada, tira a OS da fila guardada na hora.
A tela só esconde o botão de quem não pode (`pode_na_tela`, pela sessão do Nexus); quem decide é este portão.
"""
import logging
from urllib.parse import urlsplit

from flask import Blueprint, current_app, jsonify, request, session
from werkzeug.test import EnvironBuilder

from ...campo import aprovacao as campo_aprovacao
from ...campo import regras_app, visao
from . import assinatura

bp_aprovar_os = Blueprint("campo_aprovar_os", __name__)

RECUSA = "Só o supervisor desta OS ou um administrador aprova."


def _admin_do_nexus(email: str = "") -> bool:
    from ...auth import _admins
    return bool(session.get("admin")) or bool(email and email.strip().lower() in _admins())


def pode_na_tela(supervisor_da_os) -> bool:
    """Se a tela mostra o Aprovar na linha: admin do Nexus, ou o supervisor que entrou pelo Fracttal (o
    `supervisor_padrao` da sessão) quando a OS é dele. É só aparência: a regra vale no servidor (`aprovar`)."""
    if _admin_do_nexus():
        return True
    meu = session.get("supervisor_padrao") or ""
    return bool(meu) and meu == (supervisor_da_os or "")


def supervisores_da_os(os_fila: dict) -> set[str]:
    """O supervisor da OS pelo cadastro, como a tela atribui: a usina do Fracttal de cada tarefa (de-para "Fracttal ·
    Classificação 1") -> a equipe -> o supervisor dos técnicos. OS com tarefas em usinas de dois supervisores (rara)
    é dos dois."""
    por_nome = (visao.usinas_do_fracttal().dados or {}).get("por_nome") or {}
    return {(por_nome.get(regras_app._norm(n)) or {}).get("supervisor") or "" for n in os_fila["usinas_fx"]} - {""}


def pode_aprovar(os_fila: dict, quem: dict) -> bool:
    """A regra do servidor: administrador, ou quem entrou no Fracttal é o supervisor da OS no cadastro."""
    if _admin_do_nexus(quem.get("email", "")):
        return True
    meu = visao.supervisor_da_pessoa(quem.get("email", ""), quem.get("nome", ""))
    return bool(meu) and meu in supervisores_da_os(os_fila)


def _clone():
    from ..oscreator import ponte
    return ponte.clone(current_app._get_current_object())


def _concluir_no_os_creator(id_wo: int, folio: str):
    """O mesmo POST que a tela fazia antes de 08/10 (o Concluir do card do OS Creator), com o cookie de quem clicou: a
    rota do clone abre a sessão do Fracttal dessa pessoa, conclui e devolve o JSON dela (ok/mensagem ou erro/login).
    O número da OS vai pela fila do servidor, não pelo que o navegador mandou."""
    env = EnvironBuilder(path=f"/os/api/os/{int(id_wo)}/concluir", method="POST", json={"folio": folio},
                         base_url=request.host_url, headers={"Cookie": request.headers.get("Cookie", "")}).get_environ()
    return current_app.response_class.from_app(_clone(), env)


@bp_aprovar_os.route("/os/_nexus/aprovacao/<int:id_wo>/aprovar", methods=["POST"])
def aprovar(id_wo):
    origem = request.headers.get("Origin")
    if origem and urlsplit(origem).netloc != request.host:
        return jsonify({"ok": False, "erro": "Origem recusada."}), 403
    quem = assinatura.quem_assina()
    if not quem:
        return jsonify({"ok": False, "login": True, "erro": "Entre com o seu login do Fracttal para aprovar."}), 401
    os_fila = campo_aprovacao.os_na_fila(id_wo)
    if not os_fila:
        return jsonify({"ok": False, "erro": "Esta OS não está na fila de aprovação lida pelo Nexus (já aprovada, ou a "
                                             "fila ainda não foi lida). Recarregue a página."}), 404
    if not pode_aprovar(os_fila, quem):
        logging.warning("aprovação de OS recusada pelo portão: OS %s (não é o supervisor dela nem admin)", os_fila["os"])
        return jsonify({"ok": False, "erro": RECUSA}), 403
    resp = _concluir_no_os_creator(id_wo, os_fila["os"])
    from ..oscreator import ponte
    if ponte._JWT_VENCIDO in resp.get_data():
        # a sessão do Fracttal venceu no meio: o mesmo tratamento da ponte (limpa o cookie, pede login)
        return ponte._de_volta_ao_login(current_app._get_current_object(), f"api/os/{int(id_wo)}/concluir", True)
    corpo = resp.get_json(silent=True) or {}
    if resp.status_code == 200 and corpo.get("ok"):
        corpo["tarefas_tiradas"] = campo_aprovacao.tirar_da_fila(id_wo)
    saida = jsonify(corpo or {"ok": False, "erro": "O OS Creator não respondeu."})
    saida.status_code = resp.status_code if corpo else 502
    # a sessão do Fracttal renovada pelo clone (cookie os_sessao) volta para o navegador
    for c in resp.headers.getlist("Set-Cookie"):
        saida.headers.add("Set-Cookie", c)
    return saida

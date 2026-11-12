"""Base > Mapa base (11/11/2026): a subida do mapa do Brasil do Mapa de equipe, só administrador.

Levi escolheu o "Upload pelo Nexus" (o arquivo, 2,39 GB, não cabe no git, que é como o Nexus sobe): a página manda o
PMTiles em partes de 8 MB (`campo/equipe/mapa_base.py`), cada uma conferida pelo SHA-256 dela, retoma de onde parou se
a conexão cair, e o servidor confere o arquivo inteiro antes de trocar o que estava no ar. Os POST recusam pedido de
outro site (`_de_outro_site`), como todo formulário de administrador do Nexus."""
from flask import abort, current_app, jsonify, render_template, request, session

from ...campo.equipe import mapa_base as MB


def _so_admin_do_proprio_site():
    from ..moldura import _de_outro_site
    if not session.get("admin"):
        abort(403)
    if request.method == "POST" and _de_outro_site():
        abort(403)


def _resposta(fazer):
    try:
        return jsonify(fazer())
    except MB.Recusa as e:
        return jsonify({"erro": e.texto, **e.extra}), e.status


def registrar_mapa_base(bp) -> None:
    @bp.route("/mapa-base")
    def mapa_base():
        _so_admin_do_proprio_site()
        return render_template("mapa_base.html", estado=MB.estado(current_app.config), parte_max=MB.PARTE_MAX)

    @bp.route("/mapa-base/iniciar", methods=["POST"])
    def mapa_base_iniciar():
        _so_admin_do_proprio_site()
        corpo = request.get_json(silent=True) or {}
        return _resposta(lambda: MB.iniciar(current_app.config, corpo.get("tamanho"), corpo.get("sha256"),
                                            "administrador"))

    @bp.route("/mapa-base/parte", methods=["POST"])
    def mapa_base_parte():
        _so_admin_do_proprio_site()
        # o teto do corpo DESTE pedido: a parte e um pouco de folga (o Nexus aceita 25 MB nos outros)
        request.max_content_length = MB.PARTE_MAX + 64 * 1024
        dados = request.get_data(cache=False)
        return _resposta(lambda: {"recebido": MB.parte(current_app.config, request.args.get("offset"), dados,
                                                        request.headers.get("X-Sha256"))})

    @bp.route("/mapa-base/concluir", methods=["POST"])
    def mapa_base_concluir():
        _so_admin_do_proprio_site()
        return _resposta(lambda: {"pronto": MB.concluir(current_app.config, "administrador")})

    @bp.route("/mapa-base/cancelar", methods=["POST"])
    def mapa_base_cancelar():
        _so_admin_do_proprio_site()
        MB.cancelar(current_app.config)
        return jsonify(MB.estado(current_app.config))

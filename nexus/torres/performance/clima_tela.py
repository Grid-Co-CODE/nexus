"""A tela Clima e risco da torre Performance (06/10/2026): só a rota. A regra mora em `nexus/performance/clima/`.

Fica num módulo à parte e é importada no fim do `__init__` da torre, porque precisa do `bp` e da `TORRE` já definidos lá.
"""
from flask import current_app, render_template, request

from ...performance.clima import usinas, visao
from . import TORRE, bp


@bp.route("/clima")
def clima():
    try:
        cadastro, erro = usinas.do_app(), None
    except usinas.SemCadastro as e:
        cadastro, erro = None, str(e)
    except Exception:                      # noqa: BLE001 — arquivo do cadastro corrompido, por exemplo: a tela diz, e o log guarda
        current_app.logger.exception("clima: o cadastro não abriu")
        cadastro, erro = None, "o cadastro não abriu (o motivo está no log do servidor)."
    v = visao.montar(current_app.config, cadastro=cadastro, erro_cadastro=erro, cliente=request.args.get("cliente", ""),
                     todas=request.args.get("todas") == "1")
    return render_template("performance/clima.html", torre=TORRE, tela=TORRE.tela("clima"), v=v)

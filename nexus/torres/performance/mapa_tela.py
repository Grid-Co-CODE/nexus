"""A tela Mapa de risco da torre Performance (07/10/2026): só a rota. A regra mora em `nexus/performance/clima/mapa.py`.

Fica num módulo à parte (como `clima_tela.py`) e é importada no fim do `__init__` da torre, porque precisa do `bp` e da `TORRE`
já definidos lá. É uma tela complementar à lista do Clima e risco: lê as mesmas fontes pelo mesmo cache.
"""
from flask import current_app, render_template, request

from ...performance.clima import alertas, mapa, usinas
from . import TORRE, bp


@bp.route("/clima/mapa")
def mapa_de_risco():
    try:
        cadastro, erro = usinas.do_app(), None
    except usinas.SemCadastro as e:
        cadastro, erro = None, str(e)
    except Exception:                      # noqa: BLE001 — arquivo do cadastro corrompido, por exemplo: a tela diz, e o log guarda
        current_app.logger.exception("clima: o cadastro não abriu (mapa)")
        cadastro, erro = None, "o cadastro não abriu (o motivo está no log do servidor)."
    v = mapa.montar(current_app.config, cadastro=cadastro, erro_cadastro=erro, regiao=request.args.get("regiao", ""))
    return render_template("performance/mapa.html", torre=TORRE, tela=TORRE.tela("clima/mapa"), v=v,
                           eventos=sorted(alertas.EVENTOS_QUE_ESTRAGAM_USINA))

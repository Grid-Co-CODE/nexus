"""A tela Clima e risco da torre Performance (06/10/2026) e a página de uma usina (07/10/2026): só as rotas. A regra mora em
`nexus/performance/clima/`.

Fica num módulo à parte e é importada no fim do `__init__` da torre, porque precisa do `bp` e da `TORRE` já definidos lá.
"""
from flask import current_app, render_template, request

from ...performance.clima import fontes, usinas, visao
from . import TORRE, bp


def _cadastro():
    """(cadastro, None) ou (None, o que faltou, em texto). O cadastro que não abre nunca derruba a tela: ela diz o motivo."""
    try:
        return usinas.do_app(), None
    except usinas.SemCadastro as e:
        return None, str(e)
    except Exception:                      # noqa: BLE001 — arquivo do cadastro corrompido, por exemplo: a tela diz, e o log guarda
        current_app.logger.exception("clima: o cadastro não abriu")
        return None, "o cadastro não abriu (o motivo está no log do servidor)."


@bp.route("/clima")
def clima():
    cadastro, erro = _cadastro()
    v = visao.montar(current_app.config, cadastro=cadastro, erro_cadastro=erro, cliente=request.args.get("cliente", ""),
                     todas=request.args.get("todas") == "1")
    return render_template("performance/clima.html", torre=TORRE, tela=TORRE.tela("clima"), v=v)


@bp.route("/clima/usina/<usina_id>")
def usina_clima(usina_id):
    """A página de uma usina: os alertas dela e a irradiação diária da NASA POWER. Usina que não é uma das em operação do
    cadastro: 404 com aviso claro; usina sem coordenada: 200 dizendo o que falta (e sem ir a fonte nenhuma)."""
    cadastro, erro = _cadastro()
    cliente = request.args.get("cliente", "")
    vazio = {"erro_cadastro": None, "nao_encontrada": False, "nome": "", "recarrega_em": visao.RECARGA_S, "cliente_filtro": ""}
    if cadastro is None:
        return render_template("performance/clima_usina.html", torre=TORRE, tela=TORRE.tela("clima"),
                               v={**vazio, "erro_cadastro": erro})
    v = visao.montar_usina(current_app.config, cadastro=cadastro, usina_id=usina_id, cliente=cliente)
    if v is None:
        v = {**vazio, "nao_encontrada": True, "cliente_filtro": cliente if cliente in cadastro.clientes() else ""}
        return render_template("performance/clima_usina.html", torre=TORRE, tela=TORRE.tela("clima"), v=v), 404
    v.update(erro_cadastro=None, nao_encontrada=False)
    return render_template("performance/clima_usina.html", torre=TORRE, tela=TORRE.tela("clima"), v=v)


# Os nomes das fontes por extenso para os templates da torre (Levi, 09/10/2026: "Quero as fontes por extenso também, não só
# sigla"): a lista, a página da usina e o mapa escrevem `fonte_nome.inmet` etc., que vêm do único lugar dos nomes (fontes.NOMES).
@bp.context_processor
def _nomes_das_fontes():
    return {"fonte_nome": {k: fontes.extenso(k) for k in fontes.NOMES}}

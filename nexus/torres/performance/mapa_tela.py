"""A tela Mapa de risco da torre Performance (07/10/2026): só a rota. A regra mora em `nexus/performance/clima/mapa.py`.

Fica num módulo à parte (como `clima_tela.py`) e é importada no fim do `__init__` da torre, porque precisa do `bp` e da `TORRE`
já definidos lá. É uma tela complementar à lista do Clima e risco: lê as mesmas fontes pelo mesmo cache.

O estado da tela (camada de fundo, camadas de cima, dia do risco, cliente, filtros) vem do endereço (`mapa.estado_da_tela`), e
`?tv=1` abre o modo TV (09/10/2026, Levi: "Quero visão de tela cheia para colocar no video wall"): o mesmo modelo num template sem
a casca. A rota é a mesma, então o portão de login vale igual: sem sessão, o modo TV vai para o Entrar e volta para ele.
"""
from flask import current_app, render_template, request

from ...performance.clima import alertas, mapa, usinas
from . import TORRE, bp


def modelo(args, endereco: mapa.Endereco = mapa.PERFORMANCE) -> tuple:
    """(modelo do mapa, eventos que estragam a usina) pelos parâmetros do endereço. É o desta tela e o do Mapa de equipe da
    Usinas 360°, que mostra este mesmo mapa dentro dele, no botão Usinas (08/11/2026): o `endereco` diz para onde os links
    voltam. Lá o modo TV não liga (o video wall é desta tela, com o template próprio)."""
    try:
        cadastro, erro = usinas.do_app(), None
    except usinas.SemCadastro as e:
        cadastro, erro = None, str(e)
    except Exception:                      # noqa: BLE001 — arquivo do cadastro corrompido, por exemplo: a tela diz, e o log guarda
        current_app.logger.exception("clima: o cadastro não abriu (mapa)")
        cadastro, erro = None, "o cadastro não abriu (o motivo está no log do servidor)."
    estado = mapa.estado_da_tela(args, endereco)
    if endereco != mapa.PERFORMANCE:
        estado.update(tv=False, girar=None)
    v = mapa.montar(current_app.config, cadastro=cadastro, erro_cadastro=erro, endereco=endereco, **estado)
    return v, sorted(alertas.EVENTOS_QUE_ESTRAGAM_USINA)


@bp.route("/clima/mapa")
def mapa_de_risco():
    v, eventos = modelo(request.args)
    pagina = "performance/mapa_tv.html" if v["tv"] else "performance/mapa.html"
    resposta = current_app.make_response(render_template(pagina, torre=TORRE, tela=TORRE.tela("clima/mapa"), v=v,
                                                         eventos=eventos))
    # A tela se relê sozinha (clima-mapa.js): a resposta nunca fica em cache do navegador nem de proxy, senão o modo TV mostraria
    # o mapa velho como se fosse novo.
    resposta.headers["Cache-Control"] = "no-store"
    return resposta

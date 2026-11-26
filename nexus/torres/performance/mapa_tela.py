"""Os endereços antigos do Clima e risco e do Mapa de risco da Performance (24/11/2026).

O Clima e risco foi para a Usinas 360° (/t/campo/clima, `nexus/torres/campo/clima_tela.py`) e o Mapa de risco saiu (Levi,
24/11/2026: "clima e risco vai para usinas 360. Mapa de risco pode tirar. Já está tudo lá na parte de mapa de equipe"): o
mapa das usinas com os avisos, os focos e o risco de fogo é o do Mapa de equipe, no botão Usinas com o Incluir clima (/t/campo/equipe?ver=usinas&clima=1,
o mesmo `nexus/performance/clima/mapa.py`). Aqui ficam só os endereços antigos, para o link salvo e a aba aberta: a lista e
a página da usina respondem 308 para o mesmo caminho na Usinas 360°, e o mapa (o modo TV também) leva ao Mapa de equipe. O
nome `mapa_de_risco` fica porque o `mapa.Endereco` padrão aponta para ele.
"""
from flask import redirect, request

from ...prefixo import na_raiz
from . import bp


def _consulta() -> str:
    q = request.query_string.decode("latin-1")
    return "?" + q if q else ""


@bp.route("/clima", defaults={"resto": ""})
@bp.route("/clima/usina/<path:resto>")
def clima_mudou(resto):
    return redirect(na_raiz("/t/campo/clima" + ("/usina/" + resto if resto else "")) + _consulta(), 308)


@bp.route("/clima/mapa")
def mapa_de_risco():
    return redirect(na_raiz("/t/campo/equipe?ver=usinas&clima=1"), 302)

"""Torre Segurança · HSEQ: Riscos da semana, APR e PT, DSS e incidentes.

Telas ainda em construção: todas caem no placeholder da casca. Para dar vida a uma tela, crie uma
view com a mesma rota (ela vence a genérica), por exemplo:

    @bp.route("/riscos")
    def riscos():
        return render_template("hseq/riscos.html")
"""
from ..modelo import Tela, Torre

TORRE = Torre(
    id="hseq",
    nome="Segurança · HSEQ",
    ordem=100,
    icone="shield-check",
    descricao="Riscos da semana, APR e PT, DSS e incidentes.",
    telas=[
        Tela("riscos", "Riscos da semana",
             "Que atividade da semana está liberada, condicionada ou bloqueada?",
             "Programação do PCM + Semanal de Segurança"),
        Tela("apr-pt", "APR e PT",
             "Que OS de risco está sem APR ou PT assinada?",
             "App de Campo"),
        Tela("dss", "DSS",
             "Todos os clusters fizeram o DSS?",
             "Registros de DSS"),
        Tela("incidentes", "Incidentes",
             "Que quase acidente ou desvio ainda está sem ação?",
             "Registros de incidentes"),
    ],
)

bp = TORRE.criar_blueprint(__name__)

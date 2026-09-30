"""Torre Engenharia: Confiabilidade dos ativos, criticidade e causa raiz.

Telas ainda em construção: todas caem no placeholder da casca. Para dar vida a uma tela, crie uma
view com a mesma rota (ela vence a genérica), por exemplo:

    @bp.route("/confiabilidade")
    def confiabilidade():
        return render_template("engenharia/confiabilidade.html")
"""
from ..modelo import Tela, Torre

TORRE = Torre(
    id="engenharia",
    nome="Engenharia",
    ordem=40,
    icone="gear-six",
    descricao="Confiabilidade dos ativos, criticidade e causa raiz.",
    telas=[
        Tela("confiabilidade", "Confiabilidade",
             "Quais ativos falham mais e demoram mais a voltar?",
             "confiabilidade.json do painel PCM"),
        Tela("criticidade", "Matriz de criticidade",
             "Qual ativo, se parar, dói mais?",
             "engenharia.json do painel PCM"),
        Tela("fmea", "FMEA e causa raiz",
             "Por que a falha acontece e o que a elimina?",
             "Planilha de confiabilidade (a migrar)"),
        Tela("laudos", "Laudos MPS/MPA",
             "Que laudos estão pendentes ou vencidos?",
             "engenharia.json do painel PCM"),
    ],
)

bp = TORRE.criar_blueprint(__name__)

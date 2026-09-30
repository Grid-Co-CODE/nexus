"""Torre Campo · App: Modo gerencial do App de Campo: aprovação, rondas e qualidade.

Telas ainda em construção: todas caem no placeholder da casca. Para dar vida a uma tela, crie uma
view com a mesma rota (ela vence a genérica), por exemplo:

    @bp.route("/atencao")
    def atencao():
        return render_template("campo/atencao.html")
"""
from ..modelo import Tela, Torre

TORRE = Torre(
    id="campo",
    nome="Campo · App",
    ordem=90,
    icone="hard-hat",
    descricao="Modo gerencial do App de Campo: aprovação, rondas e qualidade.",
    telas=[
        Tela("atencao", "Central de atenção",
             "Que ponto do campo está aberto ou parado há dias?",
             "Rotas gestao/* do App de Campo"),
        Tela("aprovacao", "Aprovação de OS",
             "Que OS em revisão posso aprovar em lote e qual pede meu olho?",
             "Rotas gestao/* do App de Campo"),
        Tela("os", "Ordens de serviço",
             "As OS estão sendo fechadas com evidência?",
             "Rotas gestao/* do App de Campo"),
        Tela("rondas", "Rondas",
             "Que usina está sem ronda de campo há mais tempo?",
             "Rotas gestao/* do App de Campo"),
        Tela("ranking", "Ranking",
             "Qual região tem qualidade e cobertura melhores?",
             "Rotas gestao/* do App de Campo"),
        Tela("triagem", "Triagem de qualidade",
             "O que exige ação hoje na qualidade do fechamento?",
             "Rotas gestao/* do App de Campo"),
        Tela("imagens", "Imagens da ronda",
             "Que foto de ronda mostra um problema?",
             "Motor de imagem do App de Campo"),
        Tela("rotas", "Rotas do dia",
             "Qual a melhor ordem de visitas para cada equipe?",
             "Programação do PCM + localização das usinas"),
    ],
)

bp = TORRE.criar_blueprint(__name__)

"""Torre Comando: sala de comando, fila única de ações e o que pede decisão.

Telas ainda em construção: todas caem no placeholder da casca. Para dar vida a uma tela, crie uma
view com a mesma rota (ela vence a genérica), por exemplo:

    @bp.route("/sala-de-comando")
    def sala_de_comando():
        return render_template("comando/sala-de-comando.html")
"""
from ..modelo import Tela, Torre

TORRE = Torre(
    id="comando",
    nome="Comando",
    ordem=0,
    icone="squares-four",
    descricao="Sala de comando, fila única de ações e o que pede decisão.",
    telas=[
        Tela("sala-de-comando", "Sala de comando",
             "Onde estou perdendo dinheiro esta semana e quem está segurando?",
             "Motor de correlação do Nexus + Performance, PCM e Fracttal"),
        Tela("caixa-de-entrada", "Caixa de entrada",
             "O que é meu para fazer hoje, por prazo e valor?",
             "Itens de trabalho do Nexus (insights, OS, chamados, solicitações)"),
        Tela("kanban", "Kanban",
             "Onde as ações nascidas no Nexus estão travando?",
             "Itens de trabalho do Nexus"),
        Tela("insights", "Nexus Insights",
             "Que regra cruzou as fontes e apontou um problema com dono?",
             "Regras R01 a R13 do motor de correlação"),
        Tela("usinas", "Usinas",
             "Qual é o prontuário de cada usina, com todos os apelidos?",
             "Registro mestre (BD_Performance, BD_Thopen e de-para, via API)"),
        Tela("metas", "Metas do book",
             "Quais KPIs do book R02 estão fora da meta e piorando?",
             "Aba KPIs do Plano de Documentação"),
    ],
)

bp = TORRE.criar_blueprint(__name__)

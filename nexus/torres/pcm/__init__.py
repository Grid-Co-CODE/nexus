"""Torre PCM: Programação semanal, aderência ao plano e capacidade das equipes.

Telas ainda em construção: todas caem no placeholder da casca. Para dar vida a uma tela, crie uma
view com a mesma rota (ela vence a genérica), por exemplo:

    @bp.route("/semana")
    def semana():
        return render_template("pcm/semana.html")
"""
from ..modelo import Tela, Torre

TORRE = Torre(
    id="pcm",
    nome="PCM",
    ordem=20,
    icone="calendar-check",
    descricao="Programação semanal, aderência ao plano e capacidade das equipes.",
    telas=[
        Tela("semana", "Semana",
             "O plano cabe na semana e está sendo cumprido?",
             "banco_dados.json do painel PCM"),
        Tela("insights", "Insights do PCM",
             "Onde a aderência cai e que tarefa já rolou várias vezes?",
             "banco_dados.json do painel PCM"),
        Tela("tarefas", "Tarefas e OS",
             "Qual é a lista consolidada de OS e tarefas da semana?",
             "banco_dados.json do painel PCM"),
        Tela("etiquetas", "Chamados por etiqueta",
             "Quanto está aberto e atrasado em religamento, preventiva e garantia?",
             "banco_dados.json do painel PCM"),
        Tela("gestao", "Gestão PCM",
             "Quanto das preventivas foi concluído por usina e sigla?",
             "gestao_pcm.json do painel PCM"),
        Tela("disponibilidade", "Disponibilidade",
             "De onde vem a indisponibilidade, da teórica ao recorte?",
             "gerencial.json do painel PCM"),
        Tela("52-semanas", "PCM 52 Semanas",
             "O que está planejado no ano para cada usina?",
             "Plano PCM 52 Semanas"),
        Tela("torre-de-controle", "Torre de controle",
             "Os controles do PCM estão em dia?",
             "Controles PCM"),
        Tela("pecas", "Peças e sobressalentes",
             "Tenho a peça crítica no cluster antes de abrir a OS?",
             "Estoque por cluster (a definir)"),
    ],
)

bp = TORRE.criar_blueprint(__name__)

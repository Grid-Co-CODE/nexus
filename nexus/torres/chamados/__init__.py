"""Torre Chamados: Chamados a fabricantes, tickets de performance e garantias.

Telas ainda em construção: todas caem no placeholder da casca. Para dar vida a uma tela, crie uma
view com a mesma rota (ela vence a genérica), por exemplo:

    @bp.route("/fabricantes")
    def fabricantes():
        return render_template("chamados/fabricantes.html")
"""
from ..modelo import Tela, Torre

TORRE = Torre(
    id="chamados",
    nome="Chamados",
    ordem=50,
    icone="ticket",
    descricao="Chamados a fabricantes, tickets de performance e garantias.",
    telas=[
        Tela("fabricantes", "Fabricantes",
             "Qual chamado está parado com o fabricante e há quanto tempo?",
             "Painel de chamados"),
        Tela("tickets", "Tickets de performance",
             "Qual ticket foi detectado e ainda não foi verificado?",
             "tickets_performance, via API"),
        Tela("clientes", "Solicitações de clientes",
             "O que o cliente pediu e qual o prazo pelo contrato?",
             "Solicitações do Nexus"),
        Tela("garantias", "Garantias",
             "Que falha tem garantia vigente e ninguém acionou?",
             "Matriz de garantias"),
    ],
)

bp = TORRE.criar_blueprint(__name__)

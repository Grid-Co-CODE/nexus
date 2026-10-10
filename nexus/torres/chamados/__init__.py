"""Torre Chamados: Chamados a fabricantes, tickets de performance e garantias.

Fabricantes e Garantias abrem telas do OS Creator Web (Levi, 08/10/2026): o Controle de fornecedores e o
Acompanhamento de chamados continuam no OS Creator, com o atalho aqui (`ponte.ATALHOS`). Tickets de performance também
(auditoria B8 da porta única, 10/10/2026: o item dizia "Em construção" com a tela pronta em /os/tickets). Solicitações
de clientes ainda cai no placeholder da casca; para dar vida a ela, crie uma view com a mesma rota (ela vence a
genérica), por exemplo:

    @bp.route("/clientes")
    def clientes():
        return render_template("chamados/clientes.html")
"""
from ..modelo import Tela, Torre
from ..oscreator.ponte import ATALHOS, abrir_em

TORRE = Torre(
    id="chamados",
    nome="Chamados",
    ordem=50,
    icone="ticket",
    descricao="Chamados a fabricantes, tickets de performance e garantias.",
    telas=[
        Tela("fabricantes", "Fabricantes",
             "Como abrir o chamado com cada fabricante e o que a inspeção precisa levar?",
             "Controle de fornecedores do OS Creator Web"),
        Tela("tickets", "Tickets de performance",
             "Qual ticket foi detectado e ainda não foi verificado?",
             "Tickets do OS Creator Web"),
        Tela("clientes", "Solicitações de clientes",
             "O que o cliente pediu e qual o prazo pelo contrato?",
             "Solicitações do Nexus"),
        Tela("garantias", "Garantias",
             "Qual chamado de garantia está aberto, com quem e há quanto tempo?",
             "Acompanhamento de chamados do OS Creator Web"),
    ],
)

bp = TORRE.criar_blueprint(__name__)

# o atalho de cada tela do OS Creator que mora nesta torre (a tela continua no OS Creator, no mesmo endereço)
for _tela_id in ATALHOS[TORRE.id]:
    bp.add_url_rule(f"/{_tela_id}", endpoint=f"abrir_{_tela_id}", view_func=abrir_em(TORRE, _tela_id))

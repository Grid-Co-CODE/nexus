"""Torre Contratos e clientes: SLA, entregáveis e comunicação com cada cliente.

Telas ainda em construção: todas caem no placeholder da casca. Para dar vida a uma tela, crie uma
view com a mesma rota (ela vence a genérica), por exemplo:

    @bp.route("/clientes")
    def clientes():
        return render_template("contratos/clientes.html")
"""
from ..modelo import Tela, Torre

TORRE = Torre(
    id="contratos",
    nome="Contratos e clientes",
    ordem=60,
    icone="handshake",
    descricao="SLA, entregáveis e comunicação com cada cliente.",
    telas=[
        Tela("clientes", "Clientes",
             "Algum contrato está em risco de penalidade ou renovação?",
             "Gestão de contratos (a estruturar)"),
        Tela("onboarding", "Onboarding de cliente",
             "Em que etapa está a entrada do cliente novo?",
             "Checklist de onboarding do Nexus"),
        Tela("comunicacao", "Comunicação por cliente",
             "O que cada cliente quer receber, quando e por onde?",
             "Perfil de comunicação do Nexus (spec R13)"),
        Tela("portal", "Portal do cliente",
             "O que o cliente vê sobre as usinas dele?",
             "Texto público das ocorrências e relatórios"),
    ],
)

bp = TORRE.criar_blueprint(__name__)

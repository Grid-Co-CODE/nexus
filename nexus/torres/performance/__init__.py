"""Torre Performance: Quanto gerou, o que caiu e qual a causa provável.

Telas ainda em construção: todas caem no placeholder da casca. Para dar vida a uma tela, crie uma
view com a mesma rota (ela vence a genérica), por exemplo:

    @bp.route("/tempo-real")
    def tempo_real():
        return render_template("performance/tempo-real.html")
"""
from ..modelo import Tela, Torre

TORRE = Torre(
    id="performance",
    nome="Performance",
    ordem=30,
    icone="chart-line-up",
    descricao="Quanto gerou, o que caiu e qual a causa provável.",
    telas=[
        Tela("tempo-real", "Tempo real",
             "O que está fora do normal agora na frota?",
             "Plataforma de Performance (app.gridco.com.br)"),
        Tela("noc", "Painel NOC",
             "Como está a carteira inteira de relance?",
             "Plataforma de Performance"),
        Tela("diagnostico", "Diagnóstico",
             "Qual anomalia é falha real e qual é clima, e virou OS?",
             "Plataforma de Performance + Fracttal"),
        Tela("strings-trackers", "Strings e trackers",
             "Quais strings e trackers estão perdendo energia?",
             "Plataforma de Performance (falhas_performance, via API)"),
        Tela("gerencial", "Visão gerencial",
             "O mês fecha dentro da meta de PR e geração?",
             "BD_Performance e BD_Thopen, via API"),
        Tela("relatorio", "Criador de relatório",
             "Como monto o relatório do cliente com os números certos?",
             "Plataforma de Performance"),
        Tela("gemeo", "Gêmeo digital",
             "Quanto a usina deveria ter gerado com o sol que teve?",
             "gemeo_digital, via API"),
    ],
)

bp = TORRE.criar_blueprint(__name__)

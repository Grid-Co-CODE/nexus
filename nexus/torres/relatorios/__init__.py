"""Torre Relatórios: Emissão dos relatórios diários, semanais e mensais.

Telas ainda em construção: todas caem no placeholder da casca. Para dar vida a uma tela, crie uma
view com a mesma rota (ela vence a genérica), por exemplo:

    @bp.route("/central")
    def central():
        return render_template("relatorios/central.html")
"""
from ..modelo import Tela, Torre

TORRE = Torre(
    id="relatorios",
    nome="Relatórios",
    ordem=70,
    icone="file-text",
    descricao="Emissão dos relatórios diários, semanais e mensais.",
    telas=[
        Tela("central", "Central de emissão",
             "Que relatório vence hoje e já foi emitido?",
             "Criador de relatório e relatórios da plataforma"),
    ],
)

bp = TORRE.criar_blueprint(__name__)

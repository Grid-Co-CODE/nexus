"""Torre Pessoas: Quem atende agora, escalas, capacidade e treinamento.

Telas ainda em construção: todas caem no placeholder da casca. Para dar vida a uma tela, crie uma
view com a mesma rota (ela vence a genérica), por exemplo:

    @bp.route("/plantao")
    def plantao():
        return render_template("pessoas/plantao.html")
"""
from ...cadastro.telas import registrar_pessoas
from ..modelo import Tela, Torre

TORRE = Torre(
    id="pessoas",
    nome="Pessoas",
    ordem=80,
    icone="users-three",
    descricao="Quem atende agora, escalas, capacidade e treinamento.",
    telas=[
        # Cadastro: o BD_Operações fora da planilha (29/09/2026). As views moram em nexus/cadastro/telas.py.
        Tela("colaboradores", "Colaboradores Operação",
             "Quem é quem, em que equipe, com que cargo e quem supervisiona?",
             "Cadastro do Nexus (antes: aba Relação Geral Colaboradores)"),
        Tela("plantao", "Plantão e sobreaviso",
             "Quem atende agora em cada grupo de clusters?",
             "Escala de sobreaviso"),
        Tela("escala", "Escala de sobreaviso",
             "A escala cumpre as regras de rodízio e cobertura?",
             "Escala de sobreaviso"),
        Tela("equipes", "Equipes e capacidade",
             "Onde falta gente para a carga da semana?",
             "Clusters e PCM"),
        Tela("cadeiras", "Cadeiras e RACI",
             "Quem é R e A em cada processo do book?",
             "Estrutura O&M (book R02)"),
        Tela("academy", "Academy",
             "Que treinamento cada cadeira precisa concluir?",
             "Trilhas por cadeira"),
        Tela("licoes", "Lições aprendidas",
             "O que aprendemos com as ocorrências críticas?",
             "Registros de lições do Nexus"),
    ],
)

bp = TORRE.criar_blueprint(__name__)
registrar_pessoas(bp)

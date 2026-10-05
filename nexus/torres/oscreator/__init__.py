"""Torre OS Creator: o criador de OS da Grid dentro do Nexus.

As telas seguem as seções do OS Creator web (repo Grid-Co-CODE/oem, os_creator/os_web, servido em
/os/* pela plataforma): Início (consulta, setores e solicitações), Histórico de OS, Setores,
Solicitação e Clonagem de OS. Desde 30/09/2026 cada uma abre o CLONE do OS Creator web que mora nesta pasta
(README.md), servido pelo próprio Nexus em /os/* depois do portão de login (ponte.py). O login no Fracttal
continua por pessoa, na tela do próprio OS Creator.
"""
from ..modelo import Tela, Torre
from .ponte import abrir, bp_raiz

TORRE = Torre(
    id="os",
    nome="OS Creator",
    ordem=120,
    icone="clipboard-text",
    descricao="Criar, consultar e clonar OS no Fracttal, por setor.",
    telas=[
        Tela("inicio", "Início",
             "Que OS eu crio ou consulto agora?",
             "OS Creator web (tela inicial: consulta, setores e solicitações) + Fracttal"),
        Tela("historico", "Histórico de OS",
             "Que OS eu criei ou foram atribuídas a mim, e em que situação estão?",
             "Fracttal, pelas visões de histórico do OS Creator web (criadas, atribuídas, período)"),
        Tela("ativos", "Ativos Fracttal",
             "Que ativos o Fracttal tem em cada usina?",
             "Fracttal, pela tela de Ativos do OS Creator web"),
        # Os setores saíram de um item só ("Setores") para um item cada (Levi, 04/10/2026).
        Tela("performance", "Performance", "Que OS a Performance abre?", "Setor Performance do OS Creator web"),
        Tela("cos", "COS", "Que OS o COS abre: desligamento, religamento e inspeção?", "Setor COS do OS Creator web"),
        Tela("pcm", "PCM", "O que o PCM planeja, recebe na fila e já atendeu?", "Setor PCM do OS Creator web"),
        Tela("chamados", "Chamados", "Que chamados de garantia estão abertos e com quem?", "Setor Chamados do OS Creator web"),
        Tela("engenharia", "Engenharia", "Que OS a Engenharia abre?", "Setor Engenharia do OS Creator web"),
        Tela("solicitacao", "Solicitação",
             "Como peço uma OS ao PCM e acompanho o pedido?",
             "Solicitações do OS Creator web + Fila do PCM"),
        Tela("clonagem", "Clonagem de OS",
             "Como reaproveito uma OS existente para abrir outra igual?",
             "Fracttal, pela clonagem do OS Creator web"),
    ],
)

bp = TORRE.criar_blueprint(__name__)

# Uma view por tela: a rota fixa vence o placeholder genérico /<tela_id>.
for _tela in TORRE.telas:
    bp.add_url_rule(f"/{_tela.id}", endpoint=f"abrir_{_tela.id}", view_func=abrir(TORRE, _tela.id))

# A ponte /os/* fica FORA do /t/os (o OS Creator gera links /os/... absolutos). Entra no app junto com a torre, para
# a descoberta por pasta continuar sendo o único registro — tirar a pasta tira a ponte.
bp.record_once(lambda estado: estado.app.register_blueprint(bp_raiz))

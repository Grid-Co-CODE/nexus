"""Torre Base: Cadastros e integrações que sustentam todo o resto.

Telas ainda em construção: todas caem no placeholder da casca. Para dar vida a uma tela, crie uma
view com a mesma rota (ela vence a genérica), por exemplo:

    @bp.route("/registro-mestre")
    def registro_mestre():
        return render_template("base/registro-mestre.html")
"""
from ...cadastro.telas import registrar_base
from ...cadastro.telas_ligacoes import registrar_ligacoes
from ...dados.telas import registrar_governanca
from ..modelo import Tela, Torre

TORRE = Torre(
    id="base",
    nome="Base",
    ordem=110,
    icone="database",
    descricao="Cadastros e integrações que sustentam todo o resto.",
    telas=[
        # Cadastro: o BD_Operações fora da planilha (29/09/2026). As views moram em nexus/cadastro/telas.py.
        Tela("registro-mestre", "Registro mestre",
             "Quais usinas operamos, de quem, com que equipe e contrato?",
             "Cadastro do Nexus (antes: aba Operações do BD_Operações)"),
        Tela("clientes", "Clientes",
             "Quais clientes temos e quais usinas são de cada um?",
             "Cadastro do Nexus (antes: coluna CLIENTE da aba Operações)"),
        Tela("equipes", "Equipes",
             "Quem trabalha em cada equipe e em quais usinas?",
             "Cadastro do Nexus (antes: Equipe Cluster do BD_Operações)"),
        Tela("listas", "Listas",
             "Quais valores cada lista aceita?",
             "Cadastro do Nexus (antes: abas Auxiliar e Parametros)"),
        Tela("importar", "Importar do Excel",
             "O que muda no ensaio se eu importar o BD_Operações de hoje?",
             "BD_Operacoes.xlsx enviado pela tela"),
        Tela("ligacoes", "Ligações entre bases",
             "Que usina cada base chama de quê, e onde a ligação falta?",
             "de_para do Nexus (cadastro_nexus no PostgreSQL)"),
        # Governança de dados (05/10/2026, Levi: "prioridade 0"): a matriz de barramento e a qualidade da ligação por ID.
        Tela("governanca", "Governança de dados",
             "Que dado temos, de onde vem, o que é cada linha e quanto dele liga por ID?",
             "Catálogo do Nexus (nexus/dados) e nexus_fatos · qualidade no banco"),
        Tela("qualidade", "Qualidade do cadastro",
             "O que o Excel deixava passar calado?",
             "Cadastro do Nexus"),
        Tela("fracttal", "Integração Fracttal",
             "A cópia local do Fracttal está em dia?",
             "API do Fracttal"),
        Tela("ia", "Nexus IA",
             "O que a IA leu e sugeriu, e quanto custou?",
             "API do Claude (a definir)"),
        Tela("notificacoes", "Notificações",
             "Que evento avisa quem, por qual canal?",
             "Regras de notificação do Nexus"),
        Tela("estrutura", "Estrutura R02",
             "Quais torres, processos e KPIs compõem o book?",
             "Estrutura O&M (book R02)"),
        Tela("como-usar", "Como usar o Nexus",
             "Como cada tela responde à minha rotina?",
             "Textos de ajuda por tela"),
        Tela("roadmap", "Visão e roadmap",
             "Por que o Nexus existe e em que fase está?",
             "Specs R00 a R13"),
    ],
)

bp = TORRE.criar_blueprint(__name__)
registrar_base(bp)
registrar_ligacoes(bp)
registrar_governanca(bp)

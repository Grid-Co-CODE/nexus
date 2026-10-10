"""Torre COS: Mesa do operador: ver, informar o cliente e acionar o campo em minutos.

Telas ainda em construção: todas caem no placeholder da casca. Para dar vida a uma tela, crie uma
view com a mesma rota (ela vence a genérica), por exemplo:

    @bp.route("/mesa")
    def mesa():
        return render_template("cos/mesa.html")
"""
from ..modelo import Tela, Torre
from ..moldura import registrar_molduras

TORRE = Torre(
    id="cos",
    nome="COS",
    ordem=10,
    icone="broadcast",
    descricao="Mesa do operador: ver, informar o cliente e acionar o campo em minutos.",
    telas=[
        Tela("mesa", "Mesa do operador",
             "O que está aberto na minha mesa e o que falta avisar ao cliente?",
             "Tempo real da Performance + ocorrências do Nexus"),
        Tela("ocorrencias", "Ocorrências",
             "Cada ocorrência cumpriu as cinco etapas no prazo?",
             "Ocorrências do Nexus (detecção, aviso, acionamento, normalização, encerramento)"),
        Tela("ronda", "Ronda padronizada",
             "A ronda do turno foi emitida com as nove verificações?",
             "Tempo real da Performance + ronda do COS"),
        Tela("acionamentos", "Acionamentos e distribuidoras",
             "Quem aciono e qual o canal da distribuidora desta UF?",
             "Cadastro de distribuidoras e contatos por cliente"),
        Tela("desempenho", "Desempenho da equipe",
             "As mesas estão dentro do MTTA e do aviso no prazo?",
             "Ocorrências do Nexus"),
        Tela("eventos", "Parede de eventos",
             "O que aconteceu na frota nas últimas horas?",
             "Linha do tempo de eventos do Nexus"),
        Tela("religamentos", "Religamentos",
             "Onde o religamento remoto resolve e onde se repete na mesma cabine?",
             "COS + Fracttal (OS de religamento)"),
        Tela("turno", "Passagem de turno",
             "O que o próximo turno precisa saber e quem assumiu?",
             "Registros de passagem de turno do Nexus"),
        # Porta única (09/10/2026): o /cos da Plataforma de Performance (MTTA das OS), numa moldura do Nexus. A view sai do
        # mapa das telas da plataforma (nexus/performance/porta.py), pelo registrar_molduras abaixo.
        Tela("acompanhamento", "Acompanhamento COS",
             "As OS do COS estão sendo atendidas no prazo (MTTA)?",
             "Plataforma de Performance (/cos)"),
    ],
)

bp = TORRE.criar_blueprint(__name__)
registrar_molduras(bp, TORRE)

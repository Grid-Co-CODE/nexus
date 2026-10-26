"""Torre PCM: Programação semanal, aderência ao plano e capacidade das equipes.

Desde 30/09/2026 a programação semanal está vindo para o Nexus (nexus/pcm/). Têm tela própria: Tarefas e OS (a
programação que está valendo), Quadro da semana (o quadro do painel do PCM, com a reprogramação de tarefas,
desde 09/10/2026), Gerar a semana (o motor, com o Publicar no App) e Gestão PCM (o bloco "Manutenções — Plano &
Fila" do painel do PCM, desde 08/10/2026); as outras ainda caem no placeholder da casca. Para dar vida a uma tela,
crie a view com a mesma rota (ela vence a genérica) em nexus/pcm/telas.py.

Saíram do menu em 11/10/2026 (Levi: "tire essas seções: Chamados por etiqueta e disponibilidade"): eram placeholder;
a Disponibilidade da Performance (porta única com a plataforma) continua lá. A Semana saiu em 12/10/2026 com o código
dela (Levi: "pode excluir essa seção e o código dela"): o Quadro da semana mostra a semana por equipe e dia.

O Acompanhamento (14/10/2026, Levi, com o pacote do painel de acompanhamento do PCM O&M: "Quero que libere na seção de
PCM essa visão de acompanhamento. O design quero alá Nexus [...] mas as estruturas quero sim que mantenha!"): as abas
MPA, MPS, Radar de Backlog, Mapa e One Page, com as fontes do Nexus (`nexus/pcm/acompanhamento`), do setor PCM.
"""
from ...pcm import acompanhamento, almoxarifado
from ...pcm.inventario import regua as inventario_regua
from ...pcm.telas import registrar_pcm
from ..modelo import Tela, Torre

TORRE = Torre(
    id="pcm",
    nome="PCM",
    ordem=20,
    icone="calendar-check",
    descricao="Programação semanal, aderência ao plano e capacidade das equipes.",
    telas=[
        # o Gerar e o Quadro são do setor PCM e dos supervisores, o setor Responsáveis UFV (16/10/2026, Levi: "mude as
        # configurações para administradores e pessoas do setor de PCM conseguir gerar uma programação semanal!" e "tanto
        # PCM quanto supervisores! Vou criar um setor de Responsáveis UFV"): quem é deles os vê sem marcar em Base →
        # Acessos, gera e mexe nas observações; publicar e gravar a reprogramação é só do PCM e do administrador
        # (`pcm.telas.pode_programar`)
        Tela("quadro", "Quadro da semana",
             "O que cada equipe faz em cada dia, e o que reprogramar?",
             "banco_dados.json do painel PCM e as gerações do Nexus",
             do_setor=("PCM", "Responsáveis UFV")),
        # as tarefas que saíram da programação por um motivo de espera e o cadastro dos motivos (16/10/2026, Levi:
        # "temos que montar um painel de acompanhamento as OSs que saíram da programação por esses motivos!" e "Também
        # temos que ter um canto no PCM onde podemos controlar todos esses motivos"); dos mesmos setores do Quadro
        Tela("fora-da-programacao", "Fora da programação",
             "Que tarefa saiu da programação por um motivo de espera, e desde quando?",
             "Os motivos marcados no Nexus (Quadro da semana e esta tela) e a Gestão PCM",
             do_setor=("PCM", "Responsáveis UFV")),
        # quem vê e pode rondar cada usina no App de Campo (17/10/2026, Levi: "cria uma estrutura que liga usina e
        # técnico e o PCM pode editar a vontade"); dos mesmos setores do Quadro, edita o PCM (`pcm.telas.pode_programar`)
        Tela("tecnicos-por-usina", "Técnicos por usina",
             "Quem cobre cada usina, e quem pode rondar ali no App?",
             "O cadastro do Nexus, as rondas e a programação; as decisões do PCM nesta tela",
             do_setor=("PCM", "Responsáveis UFV")),
        Tela("insights", "Insights do PCM",
             "Onde a aderência cai e que tarefa já rolou várias vezes?",
             "banco_dados.json do painel PCM"),
        Tela("tarefas", "Tarefas e OS",
             "Qual é a lista consolidada de OS e tarefas da semana?",
             "banco_dados.json do painel PCM"),
        Tela("gerar", "Gerar a semana",
             "Qual é a programação da próxima semana, e ela está pronta para ir ao App?",
             "Motor do PCM rodando no Nexus: a sombra é o rascunho, e a semana vai ao App pelo Publicar no App",
             do_setor=("PCM", "Responsáveis UFV")),
        Tela("acompanhamento", "Acompanhamento PCM",
             "Que MPA ou MPS está travada, que OS envelhece no backlog e onde está a carga de cada time?",
             "Fracttal (pela Gestão PCM), programação semanal, Gerencial, cadastro e a curadoria do PCM",
             do_setor="PCM"),
        Tela("gestao", "Gestão PCM",
             "Quanto do plano de manutenção está feito por usina, e que MPA ou MPS está envelhecendo?",
             "gestao_pcm.json do painel PCM (e a planilha da Gerencial, cifrada)"),
        Tela("52-semanas", "PCM 52 Semanas",
             "O que está planejado no ano para cada usina?",
             "Plano PCM 52 Semanas"),
        Tela("torre-de-controle", "Torre de controle",
             "Os controles do PCM estão em dia?",
             "Controles PCM"),
        # o Almoxarifado (25/10/2026, Levi: "No fractall temos almoxarifado, gostaria de uma visão para a gestão desse
        # almoxarifado na parte de PCM"): o lugar que era o placeholder "Peças e sobressalentes", com o MESMO endereço
        # (/t/pcm/pecas), para não mexer nas marcas de Base → Acessos (nexus/pcm/almoxarifado.py)
        Tela("pecas", "Almoxarifado",
             "Que peça está abaixo do mínimo ou no limite, em que almoxarifado, e o que saiu nas OS?",
             "Fracttal (inventário), pela varredura diária do App de Campo",
             do_setor="PCM"),
    ],
)

bp = TORRE.criar_blueprint(__name__)
registrar_pcm(bp)
# o Acompanhamento do PCM (nexus/pcm/acompanhamento)
acompanhamento.registrar(bp)
# o Almoxarifado (nexus/pcm/almoxarifado.py)
almoxarifado.registrar(bp)
# a régua de mínimo e máximo do inventário do almoxarifado (nexus/pcm/inventario/regua.py)
inventario_regua.registrar(bp)

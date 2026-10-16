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
from ...pcm import acompanhamento
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
        Tela("pecas", "Peças e sobressalentes",
             "Tenho a peça crítica no cluster antes de abrir a OS?",
             "Estoque por cluster (a definir)"),
    ],
)

bp = TORRE.criar_blueprint(__name__)
registrar_pcm(bp)
# o Acompanhamento do PCM (nexus/pcm/acompanhamento)
acompanhamento.registrar(bp)

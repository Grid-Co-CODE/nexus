"""Os minutos de cada hora que já têm dono no Nexus (31/10/2026, etapa 3 do canto central do OS Creator; decisão AF).

A cota do Fracttal é de 200 pedidos por minuto para a empresa toda, dividida com o App de Campo, e o Nexus é um processo só
(o GIL): dois laços pesados no mesmo minuto somam na cota e na espera de quem está usando. Cada laço de hora em hora escolheu
um minuto seu, e até aqui a lista só existia espalhada pelos comentários. Ela mora AQUI, num lugar só: o laço novo que precisa
de um horário fixo pede o próximo minuto livre (`proximo_livre`) em vez de chutar, e quem muda o minuto de um laço muda esta
lista no mesmo trabalho (o `nexus/casca/CLAUDE.md` diz os minutos de cada um).

Em Brasília. Só os laços que vão ao Fracttal ou ao banco a cada hora; o :05 do `uso_os` (que só grava no disco local) e a
medida da memória (a cada 10 min desde a subida, sem rede) não ocupam minuto.
"""
from __future__ import annotations

# os ativos do OS Creator lidos pelo servidor (`os_creator/ativos_leitor.py`): os novos às :08 e :38 das 06h às 22h, e o
# Fracttal inteiro às 02:15 (uma vez por noite, não de hora em hora)
ATIVOS_NOVOS = (8, 38)
ATIVOS_COMPLETO = (2, 15)

# {minuto: quem}: os donos de cada minuto de toda hora
OCUPADOS = {
    8: "os ativos novos do OS Creator (06h às 22h)",
    38: "os ativos novos do OS Creator (06h às 22h)",
    22: "as normalizações da Ronda COS no banco",
    25: "o sync do App de Campo",
    32: "a zeladoria",
    40: "a carga de dados de hora em hora",
    50: "os chamados de garantia no banco",
}
# as tarefas das OS no banco (`nexus/campo/tarefas_os.py`): o :10 mais até 10 min que cada processo sorteia ao subir
OCUPADOS.update({m: "as tarefas das OS no banco (:10 mais o atraso sorteado de cada máquina)" for m in range(10, 21)})


def livre(minuto: int) -> bool:
    """O minuto (0 a 59) não tem dono entre os laços de hora em hora."""
    return int(minuto) % 60 not in OCUPADOS


def proximo_livre(minuto: int) -> int:
    """O próprio minuto, se livre; senão o próximo livre da hora (dando a volta no 59): o horário que cai num minuto ocupado
    anda para o seguinte."""
    m = int(minuto) % 60
    for _ in range(60):
        if livre(m):
            return m
        m = (m + 1) % 60
    raise ValueError("nenhum minuto livre na hora")

"""Os minutos de cada hora que já têm dono no Nexus (31/10/2026, etapa 3 do canto central do OS Creator; decisão AF).

A cota do Fracttal é de 200 pedidos por minuto para a empresa toda, dividida com o App de Campo, e o Nexus é um processo só
(o GIL): dois laços pesados no mesmo minuto somam na cota e na espera de quem está usando. Cada laço de hora em hora escolheu
um minuto seu, e até aqui a lista só existia espalhada pelos comentários. Ela mora AQUI, num lugar só: o laço novo que precisa
de um horário fixo pede o próximo minuto livre (`proximo_livre`) em vez de chutar, e quem muda o minuto de um laço muda esta
lista no mesmo trabalho (o `nexus/casca/CLAUDE.md` diz os minutos de cada um). Os laços do canto central do OS Creator (os
ativos, a lista de OS e as pessoas dos catálogos pequenos) leem os minutos DAQUI; os outros têm o `MINUTO_DA_HORA` deles, e um
teste cruza cada um com esta lista (`tests/test_oscreator_os_leitor.py`, rodada 1 da revisão da 3.1+3.2;
`tests/test_oscreator_catalogos.py` para as pessoas). Dois donos no mesmo minuto não passam: `_ocupar` acusa ao montar a lista.

Em Brasília. Só os laços que vão ao Fracttal ou ao banco; o :05 do `uso_os` (que só grava no disco local) e a medida da memória
(a cada 10 min desde a subida, sem rede) não ocupam minuto. Os de uma vez por dia moram em `DIARIOS`, com a hora.
"""
from __future__ import annotations

# os ativos do OS Creator lidos pelo servidor (`os_creator/ativos_leitor.py`): os novos às :08 e :38 das 06h às 22h, e o
# Fracttal inteiro às 02:15 (uma vez por noite, não de hora em hora)
ATIVOS_NOVOS = (8, 38)
ATIVOS_COMPLETO = (2, 15)
# a lista central de OS do OS Creator (`os_creator/os_leitor.py`): os 7 dias de 10 em 10 min das 06h às 20h nos minutos livres
# (o :10, o :20, o :40 e o :50 têm dono), as finalizadas no :46 de toda hora (o :45 é do `uso_os` às 03:45: Minor 1 da rodada
# 1), a conferência das abertas no :55 e a noite às 03:21 (o :20 é das tarefas). As novas, de 1 ou 2 pedidos, cabem em
# qualquer minuto e não ocupam nenhum
OS_SETE_DIAS = (0, 21, 30, 41, 51)
OS_FINALIZADAS = 46
OS_ABERTAS = 55
OS_NOITE = (3, 21)
# o uso do OS Creator levado ao banco (`nexus/casca/uso_os.py`, `GRAVAR_NA_HORA` e `GRAVAR_NO_MINUTO`), uma vez por dia
USO_OS_BANCO = (3, 45)
# os catálogos pequenos do OS Creator (`os_creator/catalogos.py`, etapa 4): as pessoas pelo REST da empresa às 05h, 11h, 17h e
# 23h (2 pedidos, 1 por segundo) no :04, o primeiro minuto livre depois do :00 dos 7 dias (~15 s de leitura) e antes do :08
# dos ativos novos (o :05 do `uso_os` só grava no disco local)
CATALOGOS_PESSOAS = 4

# {minuto: quem}: os donos de cada minuto de toda hora
OCUPADOS: dict = {}


def _ocupar(destino: dict, minutos, dono: str) -> None:
    """Dá os `minutos` ao `dono` em `destino`; o minuto que já tem dono acusa (ValueError), sem mexer em nada."""
    for m in minutos:
        if m in destino:
            raise ValueError("o minuto :%02d já é de %s (o dono novo seria %s)" % (m, destino[m], dono))
    destino.update({m: dono for m in minutos})


_ocupar(OCUPADOS, ATIVOS_NOVOS, "os ativos novos do OS Creator (06h às 22h)")
_ocupar(OCUPADOS, (22,), "as normalizações da Ronda COS no banco")
_ocupar(OCUPADOS, (25,), "o sync do App de Campo")
_ocupar(OCUPADOS, (32,), "a zeladoria")
_ocupar(OCUPADOS, (40,), "a carga de dados de hora em hora")
_ocupar(OCUPADOS, (50,), "os chamados de garantia no banco")
# as tarefas das OS no banco (`nexus/campo/tarefas_os.py`): o :10 mais até 10 min que cada processo sorteia ao subir
_ocupar(OCUPADOS, range(10, 21), "as tarefas das OS no banco (:10 mais o atraso sorteado de cada máquina)")
_ocupar(OCUPADOS, OS_SETE_DIAS, "a lista central de OS do OS Creator: os 7 dias (06h às 20h; o :21 também é o da noite, 03:21)")
_ocupar(OCUPADOS, (OS_FINALIZADAS,), "a lista central de OS do OS Creator: as finalizadas")
_ocupar(OCUPADOS, (OS_ABERTAS,), "a lista central de OS do OS Creator: a conferência das abertas")
_ocupar(OCUPADOS, (CATALOGOS_PESSOAS,), "os catálogos pequenos do OS Creator: as pessoas pelo REST (05h, 11h, 17h e 23h)")

# {(hora, minuto): quem}: os de uma vez por dia
DIARIOS = {
    ATIVOS_COMPLETO: "os ativos do OS Creator inteiros (o Fracttal todo)",
    OS_NOITE: "a noite da lista central de OS do OS Creator (90 dias; no domingo, 365)",
    USO_OS_BANCO: "o uso do OS Creator levado ao banco (uso_os)",
}


def livre(minuto: int, hora: int | None = None) -> bool:
    """O minuto (0 a 59) não tem dono entre os laços de hora em hora; com a `hora`, nem entre os de uma vez por dia."""
    m = int(minuto) % 60
    return m not in OCUPADOS and (hora is None or (int(hora) % 24, m) not in DIARIOS)


def proximo_livre(minuto: int) -> int:
    """O próprio minuto, se livre; senão o próximo livre da hora (dando a volta no 59): o horário que cai num minuto ocupado
    anda para o seguinte."""
    m = int(minuto) % 60
    for _ in range(60):
        if livre(m):
            return m
        m = (m + 1) % 60
    raise ValueError("nenhum minuto livre na hora")

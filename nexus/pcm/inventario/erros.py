"""Os erros que a régua e a curadoria devolvem à tela, e o status HTTP de cada um (26/10/2026).

O `Recusada` do livro (`nexus/dados/fato_inventario.py`) é "nada foi gravado, e o texto é para a tela": o banco não deixou
reler, falta a chave de gravação. As telas do PCM precisam distinguir isso de um pedido que faz sentido mas o estado de
agora não deixa (409) e de uma gravação no Fracttal que não conferiu (502), e o Fracttal em si tem três jeitos de dizer não
(`Limite`, `SemLogin`, `ErroFracttal`). Este módulo é só essa tabela, para as duas telas dizerem a mesma coisa.

Regra do que vira o quê: `ValueError` que não é `Recusada` = o pedido não faz sentido (400, a página mandou número
ruim ou uma peça que não é daquele almoxarifado); `Conflito` = faz sentido, mas já não dá (409); `NaoConfere` = o Fracttal
respondeu e a releitura não bateu (502); `Recusada` pura = o livro do Nexus (503).
"""
from __future__ import annotations

from ...dados.fato_inventario import Recusada
from .estoque import ErroFracttal, Limite, SemLogin


class Conflito(Recusada):
    """O pedido faz sentido, mas o estado de agora não deixa (a linha já foi decidida, a contagem já foi gravada, a peça
    ainda não tem o acordado). 409."""


class NaoConfere(Recusada):
    """O Fracttal respondeu, e a releitura não bateu com o que se mandou: nada é anotado como gravado. 502."""


def resposta(ex: Exception) -> tuple[int, str]:
    """(status, texto para a tela) de um erro das telas da régua e da curadoria. Erro que não é de nenhum destes tipos
    sobe (bug nosso: a tela não o disfarça de mensagem)."""
    if isinstance(ex, Limite):
        return 429, ("O Fracttal pediu para esperar (o limite de pedidos é da empresa inteira): tente de novo em um "
                     "minuto. Nada foi anotado como gravado.")
    if isinstance(ex, SemLogin):
        return 401, ("Gravar no Fracttal pede o login do Fracttal de quem grava: entre no Nexus pelo Fracttal (a senha de "
                     "administrador não tem esse login) ou entre de novo, se a sessão expirou. Nada foi gravado.")
    if isinstance(ex, ErroFracttal):
        return 502, f"O Fracttal recusou o pedido: {ex.mensagem}. Nada foi anotado como gravado."
    if isinstance(ex, OSError):
        # a conexão caiu: a resposta pode ter se perdido DEPOIS de o Fracttal gravar (a régua é idempotente: gravar o mesmo
        # par de novo é seguro, e o evento só sai quando a releitura confere)
        return 502, ("Não consegui falar com o Fracttal agora (rede). Ele pode ter gravado: nada foi anotado como gravado; "
                     "grave de novo, é o mesmo número.")
    if isinstance(ex, Conflito):
        return 409, str(ex)
    if isinstance(ex, NaoConfere):
        return 502, str(ex)
    if isinstance(ex, Recusada):
        return 503, str(ex)
    if isinstance(ex, ValueError):
        return 400, str(ex)
    raise ex

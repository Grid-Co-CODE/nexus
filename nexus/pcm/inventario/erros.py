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


def _de_rede(ex: Exception) -> bool:
    """A conexão (com o Fracttal ou com o banco) caiu ou demorou: o erro de rede, e não o de arquivo local. O `requests` tem a
    hierarquia dele (`RequestException` é um `OSError`, mas não um `ConnectionError` do Python)."""
    from requests import RequestException
    return isinstance(ex, (ConnectionError, TimeoutError, RequestException))


def resposta(ex: Exception, *, ao: str | None = None) -> tuple[int, str]:
    """(status, texto para a tela) de um erro das telas da régua e da curadoria. `ao` diz o que se fazia quando a rede caiu:
    "regua" (gravar o acordado no Fracttal), "cadastro" (criar a peça no Fracttal) ou nada (só leitura e livro). O erro que não
    é de nenhum destes tipos sobe (bug nosso: a tela não o disfarça de mensagem)."""
    if isinstance(ex, Limite):
        return 429, ("O Fracttal pediu para esperar (o limite de pedidos é da empresa inteira): tente de novo em um "
                     "minuto. Nada foi anotado como gravado.")
    if isinstance(ex, SemLogin):
        return 401, ("Gravar no Fracttal pede o login do Fracttal de quem grava: entre no Nexus pelo Fracttal (a senha de "
                     "administrador não tem esse login) ou entre de novo, se a sessão expirou. Nada foi gravado.")
    if isinstance(ex, ErroFracttal):
        return 502, f"O Fracttal recusou o pedido: {ex.mensagem}. Nada foi anotado como gravado."
    if isinstance(ex, OSError):
        if _de_rede(ex):
            # a conexão caiu: se havia um pedido ao Fracttal a caminho, a resposta pode ter se perdido DEPOIS de ele gravar
            if ao == "regua":
                return 502, ("Não consegui falar com o Fracttal agora (rede). Ele pode ter gravado: nada foi anotado como "
                             "gravado; grave de novo, é o mesmo número.")
            if ao == "cadastro":
                return 502, ("Não consegui falar com o Fracttal agora (rede). Se a peça chegou a ser criada, o código ficou "
                             "reservado nesta linha e tentar de novo, com os mesmos dados, não cria outra. Nada foi decidido.")
            return 502, "Não consegui falar com o banco ou com o Fracttal agora (rede): tente de novo em instantes. Nada foi feito."
        # arquivo do Nexus (o controle do código reservado, a pasta de dados): nada a ver com o Fracttal
        return 500, (f"Não consegui ler ou gravar um arquivo do Nexus ({type(ex).__name__}): nada foi decidido. Se repetir, avise "
                     "o suporte.")
    if isinstance(ex, Conflito):
        return 409, str(ex)
    if isinstance(ex, NaoConfere):
        return 502, str(ex)
    if isinstance(ex, Recusada):
        return 503, str(ex)
    if isinstance(ex, ValueError):
        return 400, str(ex)
    raise ex

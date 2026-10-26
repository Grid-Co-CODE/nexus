"""Uma trava por chave (27/10/2026), para a régua e a curadoria.

Por quê: a primeira versão guardava UMA trava do módulo inteiro enquanto falava com o Fracttal (o `criar_peca` e as páginas do
catálogo levam segundos, à razão de 1 pedido por segundo): enquanto uma pessoa cadastrava uma peça, toda decisão de outra pessoa,
de qualquer linha, esperava. A conta que precisa de trava é "ler o que há, conferir e escrever" sobre UMA coisa (a linha da
contagem, a peça do almoxarifado): duas pessoas na mesma linha esperam uma pela outra, e as demais não esperam ninguém.
"""
import threading


class Travas:
    """`de(chave)` devolve sempre a mesma trava para a mesma chave. O registro de chaves tem a trava dele, curta (só para achar ou
    criar a trava da chave, nunca segurada durante um pedido ao Fracttal ou ao banco). As travas guardadas são poucas (uma por
    linha decidida ou peça mexida) e ficam até o processo reiniciar."""

    def __init__(self):
        self._registro = threading.Lock()
        self._por_chave: dict = {}

    def de(self, chave) -> threading.Lock:
        with self._registro:
            return self._por_chave.setdefault(chave, threading.Lock())

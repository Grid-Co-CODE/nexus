"""Aprovação de OS do Nexus: a fila de verificação do painel do App (Levi aprovou a proposta em 04/10/2026).

Quem calcula é a cópia das regras do App (regras_app.py): o mesmo `_fila_supervisao` da rota gestao/supervisao/fila,
com os mesmos grupos ("Evidência completa", "Precisa do seu olho", "Fechadas fora do App") e os mesmos números. A fila
crua vem do Fracttal (OS em revisão), lida pelo Nexus só com GET e um pedido por vez (fracttal.py); a nota do
registro é a do painel do App calculada pelo Nexus com o que o Fracttal guarda (coletor.py -> API do PG ->
fonte_pg.py). Aprovar, aprovar em lote e devolver continuam no App.
"""
from . import fracttal, leitura, regras_app, tabelas
from .leitura import Leitura

# as tabelas do App que esta tela lê (a dos tokens só na linha do cadastro, por pessoas.py)
TABELAS = ("qualidadelog", "rondas", "rondaativos", "rondaos", ("fracttaltokens", "cadastro"))
# a que ela EXIGE para sair do painel do App: sem o registro dos fechamentos, todo mundo cairia em "fora do App"
EXIGIDAS = ("qualidadelog",)
# os parâmetros que a rota do App entende; o resto da URL não chega às regras
PARAMETROS = ("de", "ate", "dias", "sup", "funcao", "colab", "regiao", "os", "balde", "nome", "pag", "tam")
# escopo de Admin: vê a fila inteira (no Nexus só entra quem tem a senha de admin)
ESCOPO_ADMIN = {"clusters": None, "papel": "Admin"}


class _Pedido:
    """O pedaço do HttpRequest que as regras do App leem: só .params.get."""

    def __init__(self, params):
        self.params = dict(params)


def configurado() -> bool:
    return tabelas.configurado(EXIGIDAS) and fracttal.configurado()


def fila(params: dict) -> Leitura:
    p = {k: str(v) for k, v in params.items() if k in PARAMETROS and v not in (None, "")}

    def calcular():
        return regras_app._fila_supervisao(_Pedido(p), ESCOPO_ADMIN)
    return leitura.ler(("fila",) + tuple(sorted(p.items())), calcular)

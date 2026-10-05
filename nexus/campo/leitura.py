"""Uma leitura das telas da torre Campo · App: o dado, quando foi lido e o que deu errado.

As regras do App engolem erro de tabela (logging.warning) e devolvem lista vazia; aqui o erro fica anotado
(tabelas.py) e vira aviso na tela. Leitura com erro não fica guardada: a próxima visita tenta de novo.
"""
import time
from dataclasses import dataclass

from . import tabelas

TTL_S = 300          # 5 min: poupa o Storage e o Fracttal sem envelhecer a tela

_CACHE: dict = {}


@dataclass
class Leitura:
    dados: dict
    lido_em: float
    erro: str = ""


def limpar():
    _CACHE.clear()


def limpar_cache():
    """Esquece o que foi lido, inclusive os caches internos das regras do App (catálogo de usinas, fila do Fracttal)."""
    import importlib
    from . import regras_app
    limpar()
    importlib.reload(regras_app)


def ler(chave, calcular) -> Leitura:
    guardada = _CACHE.get(chave)
    if guardada and time.time() - guardada.lido_em < TTL_S:
        return guardada
    tabelas.comecar_leitura()
    falha = ""
    try:
        dados = calcular()
    except Exception as erro:          # o Fracttal recusou e não havia cópia boa: a fila não foi lida
        dados, falha = {}, f"fila do Fracttal ({type(erro).__name__})"
    erros = sorted(set(tabelas.erros_da_leitura()) | ({falha} if falha else set()))
    leitura = Leitura(dados, time.time(), ("Não consegui ler: " + ", ".join(erros)) if erros else "")
    if not erros:
        _CACHE[chave] = leitura
    return leitura

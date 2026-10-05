"""Triagem de qualidade do Nexus: a mesa de triagem do painel do App, rota gestao/prioridades (Levi, 04/10/2026: "pode
gravar na API do PG e ligar as telas").

Quem calcula é a cópia das regras do App (`_gestao_prioridades`), com os limiares PADRÃO dele (LIMIARES_PADRAO: o
ajuste feito no painel do App mora numa tabela do App). Do que ela junta, o Nexus tem:
- as OS fechadas pelo App, com a nota do painel calculada pelo que o Fracttal guarda (fonte_pg.py);
- os supervisores: fila parada (dias em verificação) e avaliação errada (estrelas do Fracttal contra a nota).
Rondas e usinas sem ronda nascem no App e não vão inteiras ao Fracttal: aparecem zeradas, e a tela diz isso.
"""
from . import leitura, regras_app, tabelas
from .leitura import Leitura

EXIGIDAS = ("qualidadelog",)
PERIODOS = (7, 30, 90)


class _Pedido:
    def __init__(self, params):
        self.params = dict(params)


def configurado() -> bool:
    return tabelas.configurado(EXIGIDAS)


def painel(dias: int = 30) -> Leitura:
    dias = int(dias) if int(dias) in PERIODOS else 30

    def calcular():
        return regras_app._gestao_prioridades(dias, None, janela=regras_app._janela_str(_Pedido({"dias": str(dias)})))
    return leitura.ler(("triagem", dias), calcular)

"""Ordens de serviço do Nexus: a qualidade do registro de fechamento, como na aba do painel do App (04/10/2026).

Quem calcula é a cópia das regras do App (regras_app.py): o mesmo `_gestao_os` da rota gestao/os, para o período e
para a janela anterior de mesmo tamanho (a comparação dos números, como o `janelaAnterior` do painel).

Com a fonte do banco do Nexus (fonte_pg.py) a PONTUALIDADE não vem: é a hora de início no celular contra a
programação, e nenhuma das duas vai ao Fracttal. A regra do App contaria "não pontual" para todo mundo (0%); aqui ela
vira "sem dado" (None), e a tela mostra um traço.
"""
from datetime import datetime, timedelta

from . import leitura, regras_app, tabelas
from .leitura import Leitura

# as tabelas do App que esta tela lê (o cadastro de pessoas para o supervisor de cada técnico)
TABELAS = ("qualidadelog", ("fracttaltokens", "cadastro"))
EXIGIDAS = ("qualidadelog",)
PERIODOS = (7, 30, 90)


class _Pedido:
    def __init__(self, params):
        self.params = dict(params)


def configurado() -> bool:
    return tabelas.configurado(EXIGIDAS)


def _sem_pontualidade(r: dict) -> dict:
    """A fonte do banco do Nexus não tem a hora de início no celular: pontualidade = sem dado, não 0%."""
    if not hasattr(tabelas.fornecedor(), "coleta"):
        return r
    if isinstance(r.get("resumo"), dict):
        r["resumo"]["pontualidade_pct"] = None
    for x in r.get("linhas") or []:
        x["pontual"] = None
    for g in ("por_colaborador", "por_supervisor", "por_regiao", "por_tipo"):
        for x in (r.get(g) or {}).get("itens") or []:
            x["pontualidade"] = None
    return r


def _janela_anterior(dias: int, hoje=None) -> tuple[str, str]:
    """A janela de mesmo tamanho logo antes da atual, como o janelaAnterior() do painel do App (em dias inteiros)."""
    hoje = hoje or datetime.utcnow().date()
    de = hoje - timedelta(days=dias - 1)
    a_ate = de - timedelta(days=1)
    a_de = a_ate - timedelta(days=dias - 1)
    return regras_app._janela_str(_Pedido({"de": a_de.isoformat(), "ate": a_ate.isoformat()}))


def painel(dias: int = 7) -> Leitura:
    dias = int(dias) if int(dias) in PERIODOS else 7

    def calcular():
        atual = _sem_pontualidade(regras_app._gestao_os(
            dias, {}, None, janela=regras_app._janela_str(_Pedido({"dias": str(dias)})), inteira=True))
        anterior = _sem_pontualidade(regras_app._gestao_os(dias, {}, None, janela=_janela_anterior(dias)))
        return {"atual": atual, "anterior": anterior.get("resumo") or {}, "dias": dias}
    return leitura.ler(("ordens", dias), calcular)

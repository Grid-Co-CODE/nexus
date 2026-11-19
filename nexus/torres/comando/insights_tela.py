"""Comando › Nexus Insights: o portfólio no alto e a Nexus IA (19/11/2026).

Levi, com o Insights do mockup R18 aberto: "Eu gostaria de incluir um pouco desse Nexus Insights na parte de comandos [...]
vai mostrar o portfólio, a saúde dos portfólios, como é que está sendo o cumprimento, como é que está a pontuação, e aí
ele conseguir entender o que está acontecendo e fazer perguntas para o Haiku 5.5".

As duas partes novas vêm por trás (comando-insights.js pede os pedaços), para a lista dos insights abrir na hora mesmo
quando a conta do portfólio está fria (a 1ª visita depois de um deploy leva perto de 40 s):
- `/insights/portfolio`: o resumo do portfólio (`nexus/comando/insights_portfolio.py`), da cópia da Visão gerencial, sem o
  valor dos contratos;
- `/insights/ia`: a caixa da Nexus IA, a mesma da carteira, com o dossiê ampliado (o cumprimento, a saúde e os insights
  abertos) e as instruções dele. O modelo é o de sempre (`IA.padrao`: o Claude Haiku 5.5, com a chave da Anthropic).
"""
from flask import current_app, render_template

from ...comando import ia as IA
from ...comando import insights_portfolio as II
from . import ES, MO, RG, _ia_criar_os, _ia_setores, _perguntar_carteira, bp, carteira_ia_demanda
from .contratos_tela import _so_interno

PRIMEIRA_SECAO = 6               # o dossiê da carteira tem 5 seções; as do Insights vêm depois


def _vivos() -> list[dict]:
    """Os insights do motor que não foram concluídos (a cópia que a tela já lê; sem ela, nenhum)."""
    lei = MO.sem_esperar()
    if lei is None:
        return []
    est = ES.atual()
    return [i for i in (lei.dados or {}).get("insights") or [] if ((est.get(i.get("id")) or {}).get("evento")) != "concluiu"]


def _pode_gerencial() -> bool:
    """A pessoa abre a Visão gerencial? Ela tem o valor dos contratos: só o administrador e o setor marcado."""
    from ...auth import setor_telas as ST
    a = ST.acesso()
    return bool(a.get("tudo")) or "comando/visao-gerencial" in (a.get("telas") or set())


@bp.route("/insights/portfolio")
def insights_portfolio():
    """O pedaço do portfólio: os números do alto e um cliente por linha, do pior cumprimento para o melhor."""
    from .gerencial_tela import dados_gerencial
    _so_interno()
    try:
        r = II.resumo(dados_gerencial(), _vivos(), RG.REGRAS)
    except Exception as ex:      # noqa: BLE001 — o portfólio fora não derruba a lista dos insights
        current_app.logger.exception("Nexus Insights: o portfólio não foi montado")
        r = {"ok": False, "erro": type(ex).__name__}
    return render_template("comando/_insights_portfolio.html", r=r, pode_gerencial=_pode_gerencial(), tom=II.tom)


@bp.route("/insights/ia")
def insights_ia():
    """A caixa da Nexus IA do Insights, como pedaço de página (sem janela)."""
    from . import _usinas_montadas
    cfg = current_app.config
    n = len(_usinas_montadas()["linhas"])
    return render_template("comando/_ia.html", modelos=IA.disponiveis(cfg), padrao=IA.padrao(cfg), sugestoes=II.SUGESTOES,
                           gasto=IA.gasto_do_mes(cfg), teto=IA.teto(cfg), max_pergunta=IA.MAX_PERGUNTA,
                           setores=_ia_setores(), criar_os=_ia_criar_os(), ia_base="/t/comando/insights/ia",
                           ia_sobre=f"sobre o portfólio: {n} usinas, o cumprimento do contrato, a saúde e os insights abertos",
                           ia_exemplo="Ex.: o que eu respondo ao cliente que está abaixo de 55 no contrato?")


@bp.route("/insights/ia/perguntar", methods=["POST"])
def insights_ia_perguntar():
    """Como a da carteira, com as duas seções a mais no dossiê (o cumprimento e a saúde; os insights abertos)."""
    from .gerencial_tela import dados_gerencial

    def extra():
        return II.secoes_dossie(dados_gerencial(), _vivos(), RG.REGRAS, PRIMEIRA_SECAO)
    return _perguntar_carteira(extra=extra, instrucoes=II.INSTRUCOES, prefixo="[insights] ")


@bp.route("/insights/ia/demanda", methods=["POST"])
def insights_ia_demanda():
    """A ação de outro setor da resposta, mandada como demanda: a mesma da carteira."""
    return carteira_ia_demanda()

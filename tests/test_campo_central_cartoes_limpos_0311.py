"""A Central de atenção por responsável sem cor que "dói os olhos" (Levi, 03/11/2026: "quero mais minimalista... já tem um
vermelho na lateral e a barra também fica vermelha... dói é os olhos!"): sem borda nem número colorido; a cor fica num
ponto pequeno, ao lado da palavra ou do número (a cor nunca sozinha), e a barra do em dia é neutra. Eram cartões; desde
16/11/2026 é uma linha por responsável (test_campo_central_tabela_16_11.py). Vale para a aba das rondas e a das PT (o
mesmo pedaço da APR e PT). Banco falso do test_campo_visao."""
from pathlib import Path

from test_campo_visao import banco  # noqa: F401  (fixture)


def _tabela(html):
    return html[html.index('<table class="cn-resp-tab">'):html.index("</table>", html.index('<table class="cn-resp-tab">'))]


def test_a_linha_das_rondas_sem_vermelho_cheio(banco, logado):
    c = _tabela(logado.get("/t/campo/atencao").get_data(as_text=True))
    for colorido in ("cn-equipe--critico", "cn-equipe--alerta", 'class="pend"', "cn-t-critico", "cn-barra"):
        assert colorido not in c, colorido
    # a cor num ponto ao lado da palavra; a barra neutra só com o que foi feito
    assert 'class="cn-min-st cn-min-st--' in c and "% feitas</span>" in c and 'class="cn-min-barra"' in c


def test_a_linha_das_pt_sem_numero_colorido(banco, logado):
    c = _tabela(logado.get("/t/campo/atencao?vista=pt").get_data(as_text=True))
    assert "cn-equipe--critico" not in c and "cn-t-critico" not in c
    assert '<span class="cn-min-st cn-min-st--critico">1</span>' in c


def test_o_ponto_tem_a_cor_e_a_barra_fica_neutra():
    css = (Path(__file__).resolve().parents[1] / "nexus" / "static" / "campo.css").read_text(encoding="utf-8")
    bloco = css[css.index("/* Os cartões por responsável da Central de atenção (e da APR e PT), limpos"):]
    assert ".cn-min-barra span{display:block;height:100%;border-radius:inherit;background:var(--tinta-2)" in bloco
    tabela = css[css.index("/* a Central de atenção por responsável em tabela"):]
    assert "critico-cheio" not in tabela                                 # nenhum vermelho cheio na linha

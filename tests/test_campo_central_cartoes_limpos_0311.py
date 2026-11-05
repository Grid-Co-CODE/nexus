"""Os cartões por responsável da Central de atenção, limpos (Levi, 03/11/2026: "quero mais minimalista... já tem um
vermelho na lateral e a barra também fica vermelha... dói é os olhos!"): sem a borda colorida, sem o vermelho na barra e
sem o número colorido; a cor fica num ponto pequeno, ao lado da palavra (a cor nunca sozinha). Vale para a aba das
rondas e a das PT (o mesmo cartão da APR e PT). Banco falso do test_campo_visao."""
from pathlib import Path

from test_campo_visao import banco  # noqa: F401  (fixture)


def _cartoes(html):
    return html[html.index('class="cn-equipes"'):html.index('</main>')]


def test_o_cartao_das_rondas_sem_borda_nem_barra_vermelha(banco, logado):
    c = _cartoes(logado.get("/t/campo/atencao").get_data(as_text=True))
    assert c.count('class="cn-equipe cn-equipe--min') >= 1
    for colorido in ("cn-equipe--critico", "cn-equipe--alerta", "cn-equipe--ok", 'class="pend"', "cn-t-critico", "cn-barra"):
        assert colorido not in c, colorido
    # a cor num ponto ao lado da palavra; a barra neutra só com o que foi feito
    assert 'class="cn-min-st cn-min-st--' in c and "% feitas</span>" in c
    assert 'class="cn-min-barra"' in c and "com a ronda em dia" in c


def test_o_cartao_das_pt_sem_numero_colorido(banco, logado):
    c = _cartoes(logado.get("/t/campo/atencao?vista=pt").get_data(as_text=True))
    assert 'class="cn-equipe cn-equipe--min' in c and "cn-equipe--critico" not in c and "cn-t-critico" not in c
    assert '<span class="cn-min-st cn-min-st--critico">1 parada</span>' in c


def test_o_ponto_tem_a_cor_e_a_superficie_fica_neutra():
    css = (Path(__file__).resolve().parents[1] / "nexus" / "static" / "campo.css").read_text(encoding="utf-8")
    bloco = css[css.index("/* Os cartões por responsável da Central de atenção (e da APR e PT), limpos"):]
    assert ".cn-equipe--min{gap:14px;border-left-width:1px}" in bloco
    assert ".cn-min-barra span{display:block;height:100%;border-radius:inherit;background:var(--tinta-2)" in bloco
    assert "critico-cheio" not in bloco                                  # nenhum vermelho cheio no cartão

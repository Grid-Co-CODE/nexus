"""Ranking de pontos: a parcela do inventário do almoxarifado (App v368, 22/11/2026). O livro `ranking_app_campo` ganhou,
no fim, a coluna "Inventário (pts)", e o "Total (pts)" já a inclui (a regra é a do Levi, 22/11: 50 pontos por almoxarifado
contado no mês, por fora do teto das rondas e dos bônus, desde o ciclo de dezembro). Sem ela, a tela mostrava tarefas +
rondas + bônus que não fechavam com o total. Pessoas de mentira, no banco falso do test_campo_visao."""
import pytest

from nexus.campo import visao
from test_campo_ranking_pontos import _linha, _texto, ranking  # noqa: F401  (fixture)
from test_campo_visao import _aba, banco  # noqa: F401  (fixture)

# o ciclo de dezembro (20/11 a 19/12): a Ana contou um almoxarifado; o Bruno não
DEZEMBRO = [_linha("2026-12", "ana@exemplo.test", 1530, 1, inicio="2026-11-20", fim="2026-12-19",
                   **{"Tarefas (pts)": 1180, "Inventário (pts)": 50}),
            _linha("2026-12", "bruno@exemplo.test", 1137, 2, inicio="2026-11-20", fim="2026-12-19")]


@pytest.fixture
def com_inventario(ranking):
    _aba(ranking, "ranking_app_campo", "Ranking", DEZEMBRO)
    visao.limpar()
    return ranking


def test_a_parcela_do_inventario_vem_do_livro_e_fecha_com_o_total(com_inventario):
    ana, bruno = visao.ranking_pontos().dados["meses"][0]["classificacao"]
    assert ana["inventario_pts"] == 50 and bruno["inventario_pts"] == 0
    for p in (ana, bruno):
        assert p["tarefas_pts"] + p["rondas_pts"] + p["bonus"] + p["inventario_pts"] == p["total"]


def test_o_ciclo_com_inventario_mostra_a_parcela_no_podio_e_na_tabela(com_inventario, logado):
    html = logado.get("/t/campo/ranking?mes=2026-12").get_data(as_text=True)
    podio = _texto(html.split('class="rk-podio"', 1)[1].split('class="cn-numeros"', 1)[0])
    assert "1.180 de tarefas · 200 de rondas · 100 de bônus · 50 de inventário" in podio
    assert "837 de tarefas · 200 de rondas · 100 de bônus" in podio and podio.count("de inventário") == 1  # o 0 não aparece
    assert "<th>Inventário</th>" in html
    tabela = html.split('<h2 class="ui-kicker">Classificação', 1)[1]
    ana = _texto(next(tr for tr in tabela.split("<tr")[1:] if "Ana Souza" in tr))
    assert " 1.530 " in ana and " 100 50 " in ana, ana                             # bônus 100, inventário 50
    assert html.count('colspan="12"') >= 1 and 'colspan="11"' not in html         # a lista da linha cobre a coluna nova
    t = _texto(html.split('class="gc-titulo-explica"', 1)[1].split("</details>", 1)[0])
    assert "pontos de tarefas + pontos de rondas + bônus + inventário" in t
    inv = t.split(" Inventário ", 1)[1]
    for trecho in ("50 pontos por almoxarifado", "uma vez por mês", "fora do teto das rondas e dos bônus",
                   "Recontagem pedida pelo PCM tira os 50"):
        assert trecho in inv, trecho


def test_o_ciclo_sem_inventario_fica_como_antes(ranking, logado):
    html = logado.get("/t/campo/ranking").get_data(as_text=True)                 # outubro: ninguém tem a parcela
    assert "de inventário" not in html and "<th>Inventário</th>" not in html and 'colspan="12"' not in html
    assert "pontos de tarefas + pontos de rondas + bônus. " in _texto(html)

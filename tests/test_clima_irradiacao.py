"""Clima e risco: a irradiação diária na página da usina (07/10/2026), sem Flask e sem rede: os últimos 30 dias, o mês até agora e a
geometria do gráfico. Os números do gráfico vêm do desenho aprovado (Irradiacao.dc.html): um SVG de 620 x 270, o zero em y=230, a
grade de 6 em y=20, os dias de x=40 a x=610 (31 dias a 19 px cada)."""
from datetime import date, timedelta

import pytest

from nexus.performance.clima import irradiacao as I

HOJE = date(2026, 10, 6)


def serie(valores, fim=HOJE):
    """[(data, valor)] com um valor por dia, terminando em `fim`."""
    n = len(valores)
    return [(fim - timedelta(days=n - 1 - i), v) for i, v in enumerate(valores)]


# ── os últimos dias ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_ultimos_30_dias_terminam_hoje_e_vao_do_mais_antigo_ao_mais_novo():
    s = I.ultimos_dias({}, HOJE)
    assert len(s) == 30 and s[0][0] == date(2026, 9, 7) and s[-1][0] == HOJE
    assert [d for d, _ in s] == sorted(d for d, _ in s)


def test_dia_que_a_serie_nao_tem_vem_como_none_e_o_que_ela_tem_vem_inteiro():
    s = I.ultimos_dias({date(2026, 10, 2): 4.5, date(2026, 10, 3): None, date(2026, 8, 1): 9.9}, HOJE)
    por_dia = dict(s)
    assert por_dia[date(2026, 10, 2)] == 4.5 and por_dia[date(2026, 10, 3)] is None and por_dia[date(2026, 10, 6)] is None
    assert date(2026, 8, 1) not in por_dia                                        # fora da janela de 30 dias


def test_a_janela_tem_o_tamanho_pedido():
    assert len(I.ultimos_dias({}, HOJE, 10)) == 10 and I.ultimos_dias({}, HOJE, 1) == [(HOJE, None)]


# ── o mês até agora ──────────────────────────────────────────────────────────────────────────────────────────────────

def mes(valores_por_dia, hoje=HOJE):
    return I.mes_ate_agora({date(2026, 10, d): v for d, v in valores_por_dia.items()}, hoje)


def test_soma_o_mes_ate_o_ultimo_dia_publicado_e_diz_qual_e():
    m = mes({1: 5.0, 2: 4.0, 3: None, 4: None, 5: None, 6: None})
    assert (m["mes"], m["soma"], m["n"], m["ate"], m["buracos"]) == ("outubro/2026", 9.0, 2, date(2026, 10, 2), [])


def test_buraco_no_meio_nao_entra_como_zero_e_e_dito():
    m = mes({1: None, 2: 4.0, 3: 6.0, 4: None, 5: None, 6: None})
    assert (m["soma"], m["n"], m["ate"]) == (10.0, 2, date(2026, 10, 3))
    assert m["buracos"] == [date(2026, 10, 1)]                                   # o dia 1 ficou sem valor; 4 a 6 ainda não saíram


def test_dias_depois_do_ultimo_publicado_nao_sao_buraco_e_dia_faltando_na_serie_conta_como_sem_valor():
    m = I.mes_ate_agora({date(2026, 10, 1): 3.0, date(2026, 10, 3): 5.0}, HOJE)      # o dia 2 nem está na série
    assert m["buracos"] == [date(2026, 10, 2)] and m["soma"] == 8.0 and m["ate"] == date(2026, 10, 3)


def test_nenhum_dia_do_mes_publicado_nao_inventa_soma():
    m = I.mes_ate_agora({date(2026, 9, 28): 5.0, date(2026, 9, 29): 6.0}, HOJE)
    assert (m["soma"], m["n"], m["ate"], m["buracos"]) == (None, 0, None, [])
    assert m["mes"] == "outubro/2026"


def test_so_conta_o_mes_de_hoje_e_ate_hoje():
    dias = {date(2026, 9, 30): 7.0, date(2026, 10, 1): 5.0, date(2026, 10, 7): 9.0, date(2026, 10, 20): 9.0}
    m = I.mes_ate_agora(dias, HOJE)
    assert (m["soma"], m["n"], m["ate"]) == (5.0, 1, date(2026, 10, 1))


def test_zero_publicado_e_numero_e_entra_na_soma():
    m = mes({1: 0.0, 2: 3.0, 3: None, 4: None, 5: None, 6: None})
    assert (m["soma"], m["n"], m["ate"]) == (3.0, 2, date(2026, 10, 2))


def test_no_primeiro_dia_do_mes_so_ha_o_proprio_dia():
    assert I.mes_ate_agora({date(2026, 10, 1): None}, date(2026, 10, 1))["soma"] is None
    assert I.mes_ate_agora({date(2026, 10, 1): 4.0}, date(2026, 10, 1))["soma"] == 4.0


@pytest.mark.parametrize("d,esperado", [(date(2026, 1, 15), "janeiro/2026"), (date(2026, 3, 1), "março/2026"),
                                        (date(2026, 12, 31), "dezembro/2026"), (date(2027, 2, 2), "fevereiro/2027")])
def test_nome_do_mes_em_portugues(d, esperado):
    assert I.nome_do_mes(d) == esperado and I.dd_mm(date(2026, 10, 2)) == "02/10"


# ── a geometria do gráfico (o desenho aprovado) ──────────────────────────────────────────────────────────────────────

ETM_MAIO = [2.86, 5.14, 2.37, 4.16, 2.32, 4.18, 4.95, 3.01, 3.94, 3.88, 4.85, 5.07, 3.29, 3.73, 5.05, 5.06, 4.98, 5.1, 5.29,
            5.35, 5.56, 5.84, 4.96, 4.06, 3.77, 4.62, 3.67, 4.65, 4.0, 3.83, 4.35]            # os 31 dias do mockup


def test_os_pontos_batem_com_a_conta_do_desenho_aprovado_x_igual_40_mais_19_i_e_y_igual_230_menos_35_v():
    s = serie(ETM_MAIO, fim=date(2026, 5, 31))
    g = I.grafico(s, date(2026, 5, 31))
    assert g["viewbox"] == "0 0 620 270" and g["topo"] == 6
    esperado = " ".join(f"{40 + i * 19:.1f},{230 - v * 35:.1f}" for i, v in enumerate(ETM_MAIO))
    assert g["nasa"]["trechos"] == [esperado] and g["nasa"]["isolados"] == []
    assert g["nasa"]["trechos"][0].startswith("40.0,129.9 59.0,50.1 ")


def test_grades_a_cada_2_kwh_do_zero_ate_o_topo():
    g = I.grafico(serie([3.0] * 30), HOJE)
    assert g["topo"] == 6 and [(x["rotulo"], x["y"]) for x in g["grades"]] == [("0", 230.0), ("2", 160.0), ("4", 90.0), ("6", 20.0)]


@pytest.mark.parametrize("maior,topo", [(0.0, 6), (3.0, 6), (6.0, 6), (6.01, 8), (6.4, 8), (7.99, 8), (8.0, 8), (8.01, 10), (11.3, 12)])
def test_o_eixo_vai_ate_o_multiplo_de_2_acima_do_maior_valor_e_no_minimo_6(maior, topo):
    assert I.grafico(serie([1.0] * 29 + [maior]), HOJE)["topo"] == topo


def test_eixo_de_8_reparte_as_grades_pela_altura():
    g = I.grafico(serie([6.4] + [1.0] * 29), HOJE)
    assert [(x["rotulo"], x["y"]) for x in g["grades"]] == [("0", 230.0), ("2", 177.5), ("4", 125.0), ("6", 72.5), ("8", 20.0)]
    assert g["nasa"]["trechos"][0].startswith(f"40.0,{230 - 6.4 * 210 / 8:.1f} ")


def test_rotulos_do_eixo_x_primeiro_meio_e_ultimo_dia():
    g = I.grafico(serie(ETM_MAIO, fim=date(2026, 5, 31)), date(2026, 5, 31))
    assert [(r["x"], r["texto"], r["ancora"]) for r in g["rotulos_x"]] == [(40.0, "01/05", "start"), (325.0, "16/05", "middle"),
                                                                           (610.0, "31/05", "end")]
    g30 = I.grafico(serie([4.0] * 30), HOJE)
    assert [r["texto"] for r in g30["rotulos_x"]] == ["07/09", "21/09", "06/10"] and g30["rotulos_x"][0]["x"] == 40.0
    assert g30["rotulos_x"][-1]["x"] == 610.0


def test_dia_sem_valor_parte_a_linha_e_dia_isolado_vira_ponto():
    s = serie([5.0, 5.0, None, 4.0, None, 3.0, 3.0, 3.0])
    g = I.grafico(s, HOJE)
    assert [len(t.split()) for t in g["nasa"]["trechos"]] == [2, 3] and len(g["nasa"]["isolados"]) == 1
    x, y = g["nasa"]["isolados"][0]
    assert (x, y) == (round(40 + 3 * 570 / 7, 1), round(230 - 4.0 * 35, 1))


def test_sem_nenhum_valor_nao_desenha_linha_nenhuma():
    g = I.grafico(serie([None] * 30), None)
    assert g["nasa"] == {"trechos": [], "isolados": []} and g["topo"] == 6


def test_valor_no_primeiro_e_no_ultimo_dia():
    g = I.grafico(serie([2.0] + [None] * 28 + [3.0]), HOJE)
    assert g["nasa"]["trechos"] == [] and [p[0] for p in g["nasa"]["isolados"]] == [40.0, 610.0]


def test_a_faixa_cobre_os_dias_que_a_nasa_ainda_nao_publicou():
    s = serie([4.0] * 25 + [None] * 5)                                              # termina em HOJE; 01/10 é o último publicado
    g = I.grafico(s, HOJE - timedelta(days=5))
    passo = 570 / 29
    assert g["faixa"]["x"] == round(40 + 25 * passo - passo / 2, 1)
    assert g["faixa"]["y"] == 20.0 and g["faixa"]["altura"] == 210.0
    assert round(g["faixa"]["x"] + g["faixa"]["largura"], 1) == 610.0


def test_sem_nenhum_dia_publicado_a_faixa_cobre_o_grafico_todo():
    g = I.grafico(serie([None] * 30), None)
    assert g["faixa"]["x"] == 40.0 and round(g["faixa"]["x"] + g["faixa"]["largura"], 1) == 610.0


def test_com_tudo_publicado_nao_ha_faixa():
    assert I.grafico(serie([4.0] * 30), HOJE)["faixa"] is None


def test_a_linha_da_etm_vai_por_cima_e_o_eixo_acomoda_o_maior_dos_dois():
    nasa, etm = serie([4.0] * 30), serie([4.5] * 29 + [7.2])
    g = I.grafico(nasa, HOJE, etm=etm)
    assert g["topo"] == 8 and g["etm"]["trechos"] and g["etm"]["trechos"] != g["nasa"]["trechos"]
    assert I.grafico(nasa, HOJE)["etm"] is None


def test_descricao_para_quem_nao_ve_o_grafico():
    g = I.grafico(serie([4.0] * 30), date(2026, 10, 2))
    assert g["descricao"] == "GHI diário de 07/09 a 06/10, Prediction Of Worldwide Energy Resources, projeto da NASA (NASA POWER), em kWh/m²; publicado até 02/10"
    assert "nenhum dia publicado" in I.grafico(serie([None] * 30), None)["descricao"]


def test_so_numeros_sem_coordenada_de_usina_no_desenho():
    g = I.grafico(serie(ETM_MAIO, fim=date(2026, 5, 31)), date(2026, 5, 31))
    import re
    for trecho in g["nasa"]["trechos"]:
        for numero in re.findall(r"-?\d+\.\d+", trecho):
            assert len(numero.split(".")[1]) == 1, numero                      # uma casa: é posição no desenho, não latitude


def test_grafico_de_um_dia_so_nao_existe():
    with pytest.raises(ValueError):
        I.grafico(serie([4.0]), HOJE)

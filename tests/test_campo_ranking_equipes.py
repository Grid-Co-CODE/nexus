"""Ranking das equipes na Visão do responsável (Levi, 18/10/2026: a posição "de acordo com as regras do ranking do app de
campo"; o ranking responde "qual equipe cobrar"). A régua é a do Ranking por região do painel do App (`_ranking_regioes`
no function_app.py: 60% qualidade + 40% cobertura, por cluster, a única conta por equipe que o App tem), sobre o dado do
Nexus. Desenho: docs/superpowers/specs/2026-10-18-visao-responsavel-ranking-equipes-design.md."""
from datetime import date

from nexus.campo import ranking_equipes as RE

HOJE = date(2026, 10, 18)


def test_periodos_de_30_dias():
    p = RE.periodos(HOJE)
    assert p["atual"] == (date(2026, 9, 19), date(2026, 10, 18))
    assert p["anterior"] == (date(2026, 8, 20), date(2026, 9, 18))


def test_agrega_tarefas_e_rondas_por_usina_e_periodo():
    fech = [{"data_id": 20261018, "usina_id": 1, "nota_pts": 90},
            {"data_id": "20260919", "usina_id": "1", "nota_pts": "70"},     # texto da API: a mesma conta
            {"data_id": 20260918, "usina_id": 1, "nota_pts": 100},          # hoje − 30: o período anterior
            {"data_id": 20261010, "usina_id": 1, "nota_pts": None},         # sem nota: fora de tudo
            {"data_id": 20261010, "usina_id": 9, "nota_pts": 50},           # usina não mobilizada: fora
            {"data_id": 20260801, "usina_id": 1, "nota_pts": 10}]           # antes dos dois períodos: fora
    rondas = [{"data": "2026-10-01", "usina_id": 1, "nota": 80},
              {"data": "2026-10-02", "usina_id": 2, "nota": None},          # ronda do App sem nota: ronda, sem nota
              {"data": "2026-10-03", "usina_id": 3, "nota": None, "avulsa": True}]   # avulsa: só a cobertura
    a = RE.agregar(fech, rondas, {1, 2, 3, 4}, HOJE)
    assert a[1]["atual"] == {"q_soma": 240, "q_n": 3, "n_os": 2, "n_ronda": 1, "rondada": True}
    assert a[1]["anterior"] == {"q_soma": 100, "q_n": 1, "n_os": 1, "n_ronda": 0, "rondada": False}
    assert a[2]["atual"] == {"q_soma": 0, "q_n": 0, "n_os": 0, "n_ronda": 1, "rondada": True}
    assert a[3]["atual"] == {"q_soma": 0, "q_n": 0, "n_os": 0, "n_ronda": 0, "rondada": True}
    assert a[4]["atual"]["rondada"] is False and 9 not in a


def test_nota_da_equipe_a_conta_do_app():
    aggs = [{"q_soma": 158, "q_n": 2, "n_os": 1, "n_ronda": 1, "rondada": True},
            {"q_soma": 0, "q_n": 0, "n_os": 0, "n_ronda": 0, "rondada": False}]
    assert RE.nota_da_equipe(aggs) == {"qualidade": 79, "cobertura": 50, "nota": 67, "n_notas": 2, "n_os": 1,
                                       "n_ronda": 1, "rondadas": 1, "usinas": 2}     # 0,6 × 79 + 0,4 × 50 = 67,4


def test_equipe_sem_nenhuma_nota_fica_sem_nota():
    n = RE.nota_da_equipe([{"q_soma": 0, "q_n": 0, "n_os": 0, "n_ronda": 0, "rondada": True}])
    assert (n["qualidade"], n["nota"], n["cobertura"]) == (None, None, 100)


def test_igual_ao_ranking_por_regiao_do_app():
    # a aritmética de `_ranking_regioes` (function_app.py, v283), copiada como referência
    def app(notas, rondadas, total):
        qual = int(round(sum(notas) / float(len(notas))))
        cob = int(round(100.0 * rondadas / total)) if total else None
        return int(round(0.6 * qual + 0.4 * (cob if cob is not None else 0)))
    for notas, rondadas, total in (([95, 88, 100, 61], 3, 4), ([70], 0, 2), ([100] * 5, 1, 1), ([84, 85], 2, 3)):
        aggs = [{"q_soma": sum(notas), "q_n": len(notas), "n_os": len(notas), "n_ronda": 0, "rondada": rondadas > 0}]
        aggs += [{"q_soma": 0, "q_n": 0, "n_os": 0, "n_ronda": 0, "rondada": i < rondadas - 1} for i in range(total - 1)]
        assert RE.nota_da_equipe(aggs)["nota"] == app(notas, rondadas, total), (notas, rondadas, total)


def test_cor_na_escala_do_painel_do_app():
    assert [RE.cor(n) for n in (85, 84, 70, 69, None)] == ["ok", "alerta", "alerta", "critico", "neutro"]


def test_posicoes_e_o_desempate():
    def n(nota, q, c, k):
        return {"nota": nota, "qualidade": q, "cobertura": c, "n_notas": k}
    notas = {"B": n(90, 85, 100, 5), "A": n(90, 85, 100, 5), "C": n(90, 88, 95, 3), "D": n(92, 80, 100, 9),
             "X": n(90, 85, 100, 7), "E": n(None, None, 100, 0)}
    assert RE.posicoes(notas) == {"D": 1, "C": 2, "X": 3, "A": 4, "B": 5}   # nota, qualidade, cobertura, volume, nome


def test_seta():
    assert RE.seta(3, 5) == {"tipo": "sobe", "n": 2} and RE.seta(4, 2) == {"tipo": "desce", "n": 2}
    assert RE.seta(2, 2) == {"tipo": "igual", "n": 0}
    assert RE.seta(2, None) == RE.seta(None, 1) == {"tipo": "sem", "n": 0}

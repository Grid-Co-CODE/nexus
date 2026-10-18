"""Ranking das equipes na Visão do responsável (Levi, 18/10/2026: a posição "de acordo com as regras do ranking do app de
campo"; o ranking responde "qual equipe cobrar"). A régua é a do Ranking por região do painel do App (`_ranking_regioes`
no function_app.py: 60% qualidade + 40% cobertura, por cluster, a única conta por equipe que o App tem), sobre o dado do
Nexus. Desenho: docs/superpowers/specs/2026-10-18-visao-responsavel-ranking-equipes-design.md."""
from datetime import date

from test_campo_responsaveis import tela  # noqa: F401  (fixture: o banco falso com a meta, os chamados e os extintores)
from test_campo_visao import banco  # noqa: F401  (fixture de que a `tela` depende)

from nexus.campo import ranking_equipes as RE
from nexus.campo import responsaveis as R
from nexus.campo import visao

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


# ── As notas na cópia de 5 min da Visão (o banco falso: Altair e Brodowski 1 na SP Norte 01, Coração 1 na SC Oeste 01) ──
def test_as_notas_do_app_chegam_a_usina_do_cadastro(tela):  # noqa: F811
    d = R.visao_responsaveis().dados
    a = d["ranking_por_usina"]
    # Altair: 2 rondas (90) + 3 tarefas fechadas pelo App (90, 70, 100); Brodowski 1: 1 ronda (90); Coração 1: nada
    assert a[1]["atual"] == {"q_soma": 440, "q_n": 5, "n_os": 3, "n_ronda": 2, "rondada": True}
    assert a[2]["atual"] == {"q_soma": 90, "q_n": 1, "n_os": 0, "n_ronda": 1, "rondada": True}
    assert a[3]["atual"]["rondada"] is False and a[3]["atual"]["q_n"] == 0
    assert d["tecnicos_por_equipe"]["SP Norte 01"] == 2 and d["tecnicos_por_equipe"]["SC Oeste 01"] == 1


def test_a_fonte_das_notas_que_falha_nao_derruba_a_visao(tela, monkeypatch):  # noqa: F811
    monkeypatch.setattr(R, "ranking_fonte", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("fato fora")))
    visao.limpar()
    d = R.visao_responsaveis().dados
    assert "fato fora" in d["erros"]["ranking"] and len(d["usinas"]) == 3 and d["ranking_por_usina"] == {}


# ── Os cartões e o que cobrar ────────────────────────────────────────────────────────────────────────────────────
def _u(**kw):
    """Uma usina mínima para as etiquetas (só o que `etiquetas` lê)."""
    base = {"ronda": {}, "acomp": {"valores": {"limpeza": {"cls": "neutro"}}}, "meta": {}, "manutencao": {}}
    return {**base, **kw}


def test_etiquetas_na_regua_de_cada_tela():
    s = {"paradas_abertas": 1, "atrasadas": 17, "paradas": 2, "ext_vencidos": 14, "disp": 95.1, "semana_pct": 48.1,
         "chamados": 1, "tarefas_paradas": 3}
    us = [_u(ronda={"tipo": "sem_ronda"}, acomp={"valores": {"limpeza": {"cls": "critico"}}}, meta={"atingimento": 88.0},
             manutencao={"maior_atraso": 132, "zeladoria_vencida": "2026-10-01"}),
          _u(ronda={"tipo": "longa_pendente"}, meta={"atingimento": 99.0}, manutencao={"maior_atraso": 20})]
    assert [(e["cls"], e["txt"]) for e in RE.etiquetas(s, us, 30)] == [
        ("critico", "1 OS de parada aberta"), ("critico", "17 tarefas atrasadas, a mais antiga há 132 d"),
        ("critico", "2 PT paradas"), ("critico", "2 usinas pedem ronda"), ("critico", "limpeza crítica em 1 usina"),
        ("critico", "14 extintores vencidos"), ("critico", "1 usina abaixo da meta"), ("alerta", "disp. 95,1%"),
        ("alerta", "zeladoria vencida em 1 usina"), ("alerta", "semana passada 48%"),
        ("alerta", "1 chamado com o fabricante"), ("alerta", "3 tarefas fora da programação")]
    # o limite de quem olha: a mais antiga há 132 d com o limite 200 é atenção, e vai para depois dos seis críticos
    assert [(e["cls"], e["txt"]) for e in RE.etiquetas(s, us, 200)][6] == (
        "alerta", "17 tarefas atrasadas, a mais antiga há 132 d")


def test_sem_nada_a_cobrar_nao_ha_etiqueta():
    assert RE.etiquetas({"disp": 99.5, "semana_pct": 90}, [_u(meta={"atingimento": 98})], 30) == []


def test_cartoes_da_pior_para_a_melhor(tela):  # noqa: F811
    d = R.visao_responsaveis().dados
    r = RE.cartoes(R.com_manutencao(d["usinas"], 30), d["ranking_por_usina"], d["tecnicos_por_equipe"], 30)
    assert [c["equipe"] for c in r["cartoes"]] == ["SC Oeste 01", "SP Norte 01"]     # sem nota antes das ranqueadas
    sc, sp = r["cartoes"]
    assert (sc["posicao"], sc["nota"], sc["cor"]) == (None, None, "neutro")
    # SP Norte 01: (440 + 90) ÷ 6 = 88,3 -> 88; 2 de 2 usinas com ronda; 0,6 × 88 + 0,4 × 100 = 92,8 -> 93
    assert (sp["posicao"], sp["qualidade"], sp["cobertura"], sp["nota"], sp["cor"]) == (1, 88, 100, 93, "ok")
    assert (sp["n_os"], sp["n_ronda"], sp["tecnicos"], sp["usinas"], sp["base_pequena"]) == (3, 3, 2, 2, True)
    assert sp["seta"] == {"tipo": "sem", "n": 0} and r["total"] == 1
    assert r["kpis"] == {"equipes": 2, "tecnicos": 3, "melhor": {"nota": 93, "equipe": "SP Norte 01"},
                         "menor": {"nota": 93, "equipe": "SP Norte 01"}, "amplitude": 0}


def test_a_nota_e_refeita_sobre_as_usinas_do_filtro(tela):  # noqa: F811
    d = R.visao_responsaveis().dados
    so_brodowski = [u for u in R.com_manutencao(d["usinas"], 30) if u["usina"] == "Brodowski 1"]
    c = RE.cartoes(so_brodowski, d["ranking_por_usina"], d["tecnicos_por_equipe"], 30)["cartoes"][0]
    assert (c["usinas"], c["qualidade"], c["cobertura"], c["nota"]) == (1, 90, 100, 94)


def test_sem_equipe_vai_para_o_fim_sem_posicao(tela):  # noqa: F811
    d = R.visao_responsaveis().dados
    # a Brodowski 1 (nota 90, a melhor da tela) sem equipe no cadastro: nem com nota ela ganha posição
    us = [dict(u, equipe=visao.SEM_EQUIPE) if u["usina"] == "Brodowski 1" else u for u in R.com_manutencao(d["usinas"], 30)]
    r = RE.cartoes(us, d["ranking_por_usina"], d["tecnicos_por_equipe"], 30)
    assert [c["equipe"] for c in r["cartoes"]] == ["SC Oeste 01", "SP Norte 01", visao.SEM_EQUIPE]
    assert r["cartoes"][-1]["sem_equipe"] and r["cartoes"][-1]["posicao"] is None and r["cartoes"][-1]["cor"] == "neutro"
    assert r["total"] == 1 and r["kpis"]["equipes"] == 2 and r["cartoes"][1]["posicao"] == 1


def test_a_seta_contra_o_periodo_anterior(tela):  # noqa: F811
    d = R.visao_responsaveis().dados

    def agg(s, n):
        return {"q_soma": s, "q_n": n, "n_os": n, "n_ronda": 0, "rondada": True}
    por = {1: {"atual": agg(450, 5), "anterior": agg(350, 5)}, 2: {"atual": agg(90, 1), "anterior": agg(70, 1)},
           3: {"atual": agg(80, 1), "anterior": agg(100, 1)}}
    r = {c["equipe"]: c for c in RE.cartoes(R.com_manutencao(d["usinas"], 30), por, d["tecnicos_por_equipe"], 30)["cartoes"]}
    assert (r["SP Norte 01"]["posicao"], r["SP Norte 01"]["antes"]["posicao"]) == (1, 2)
    assert r["SP Norte 01"]["seta"] == {"tipo": "sobe", "n": 1} and r["SC Oeste 01"]["seta"] == {"tipo": "desce", "n": 1}

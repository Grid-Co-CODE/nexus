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
def test_etiquetas_na_regua_de_cada_tela():
    s = {"paradas_abertas": 1, "atrasadas": 17, "paradas": 2, "pts": 3, "ext_vencidos": 14, "disp": 95.1,
         "semana_pct": 48.1, "chamados": 1, "tarefas_paradas": 3}
    us = [_ua(1, perf=[("meta", "critico"), ("disp", "atencao"), ("ativos", "critico")],
              acomp=[("ronda", "critico"), ("limpeza", "critico"), ("pt", "critico"), ("extintores", "critico"),
                     ("chamados", "atencao")],
              manut=[("parada", "critico"), ("atrasadas", "critico"), ("zeladoria", "atencao"), ("semana", "atencao")],
              meta={"atingimento": 88.0}, ativos={"lista": [{"nivel": "critico"}]}, manutencao={"maior_atraso": 132}),
          _ua(2, acomp=[("ronda", "atencao")], manut=[("atrasadas", "atencao"), ("paradas", "atencao")],
              meta={"atingimento": 99.0}, manutencao={"maior_atraso": 20})]
    assert [(e["cls"], e["txt"]) for e in RE.etiquetas(s, us)] == [
        ("critico", "1 OS de parada aberta"), ("critico", "17 tarefas atrasadas, a mais antiga há 132 d"),
        ("critico", "2 PT paradas"), ("critico", "2 usinas pedem ronda"), ("critico", "limpeza crítica em 1 usina"),
        ("critico", "14 extintores vencidos"), ("critico", "1 ativo em crítico"), ("critico", "1 usina abaixo da meta"),
        ("alerta", "disp. abaixo de 99% em 1 usina"), ("alerta", "zeladoria vencida em 1 usina"),
        ("alerta", "semana passada 48%"), ("alerta", "1 chamado com o fabricante"),
        ("alerta", "3 tarefas fora da programação")]
    # o limite de quem olha já está no nível do alerta (`com_manutencao`): com as atrasadas em atenção, a etiqueta é de
    # atenção e vai para depois dos sete críticos
    us[0]["manut"]["alertas"][1]["nivel"] = "atencao"
    assert [(e["cls"], e["txt"]) for e in RE.etiquetas(s, us)][7] == (
        "alerta", "17 tarefas atrasadas, a mais antiga há 132 d")


def test_sem_nada_a_cobrar_nao_ha_etiqueta():
    assert RE.etiquetas({"disp": 99.5, "semana_pct": 90}, [_ua(1, meta={"atingimento": 98})]) == []


def test_cartoes_da_pior_para_a_melhor(tela):  # noqa: F811
    d = R.visao_responsaveis().dados
    r = RE.cartoes(R.com_manutencao(d["usinas"], 30), d["ranking_por_usina"], d["tecnicos_por_equipe"])
    assert [c["equipe"] for c in r["cartoes"]] == ["SC Oeste 01", "SP Norte 01"]     # sem nota antes das ranqueadas
    sc, sp = r["cartoes"]
    assert (sc["posicao"], sc["nota"], sc["cor"]) == (None, None, "neutro")
    # SP Norte 01: (440 + 90) ÷ 6 = 88,3 -> 88; 2 de 2 usinas com ronda; 0,6 × 88 + 0,4 × 100 = 92,8 -> 93
    assert (sp["posicao"], sp["qualidade"], sp["cobertura"], sp["nota"], sp["cor"]) == (1, 88, 100, 93, "ok")
    assert (sp["n_os"], sp["n_ronda"], sp["tecnicos"], sp["usinas"], sp["base_pequena"]) == (3, 3, 2, 2, True)
    assert sp["seta"] == {"tipo": "sem", "n": 0} and r["total"] == 1
    assert r["kpis"] == {"equipes": 2, "tecnicos": 3, "melhor": {"nota": 93, "equipe": "SP Norte 01"},
                         "menor": {"nota": 93, "equipe": "SP Norte 01"}, "amplitude": 0}


def test_filtrado_o_cartao_da_equipe_e_o_mesmo(tela):  # noqa: F811
    # Levi, 18/10/2026: "O ranking das equipes tem que permancer mesmo filtrados". Até aqui a nota era refeita só sobre
    # as usinas do filtro (só a Brodowski 1: 94); agora o cartão é o da equipe inteira, e o filtro escolhe os cartões
    d = R.visao_responsaveis().dados
    todas = R.com_manutencao(d["usinas"], 30)
    so_brodowski = [u for u in todas if u["usina"] == "Brodowski 1"]
    r = RE.cartoes(todas, d["ranking_por_usina"], d["tecnicos_por_equipe"], so_brodowski)
    assert [c["equipe"] for c in r["cartoes"]] == ["SP Norte 01"]
    c = r["cartoes"][0]
    assert (c["usinas"], c["qualidade"], c["cobertura"], c["nota"], c["posicao"]) == (2, 88, 100, 93, 1)


def test_filtrado_a_posicao_e_a_do_ranking_inteiro(tela):  # noqa: F811
    # "se eu filtro [um responsável] vai contar de 1 a 11, tem que contar de acordo com o ranking": a posição, o "de N" e
    # a seta são os de todas as equipes; os números de cima, os dos cartões que aparecem
    d = R.visao_responsaveis().dados
    todas = R.com_manutencao(d["usinas"], 30)

    def agg(s, n):
        return {"q_soma": s, "q_n": n, "n_os": n, "n_ronda": 0, "rondada": True}
    # SP Norte 01: 540 ÷ 6 = 90 -> 94 (1º; antes 70 -> 82, 2º); SC Oeste 01: 80 -> 88 (2º; antes 100 -> 100, 1º)
    por = {1: {"atual": agg(450, 5), "anterior": agg(350, 5)}, 2: {"atual": agg(90, 1), "anterior": agg(70, 1)},
           3: {"atual": agg(80, 1), "anterior": agg(100, 1)}}
    r = RE.cartoes(todas, por, d["tecnicos_por_equipe"], [u for u in todas if u["usina"] == "Coração 1"])
    assert [c["equipe"] for c in r["cartoes"]] == ["SC Oeste 01"]
    sc = r["cartoes"][0]
    assert (sc["posicao"], r["total"], sc["nota"], sc["antes"]["posicao"]) == (2, 2, 88, 1)
    assert sc["seta"] == {"tipo": "desce", "n": 1}
    assert r["kpis"] == {"equipes": 1, "tecnicos": 1, "melhor": {"nota": 88, "equipe": "SC Oeste 01"},
                         "menor": {"nota": 88, "equipe": "SC Oeste 01"}, "amplitude": 0}


def test_sem_equipe_filtrado_conta_so_as_usinas_do_filtro(tela):  # noqa: F811
    # "Sem equipe" não é equipe do ranking: é a lista do conserto no cadastro, e quem filtra vê só as usinas do filtro
    d = R.visao_responsaveis().dados
    us = [dict(u, equipe=visao.SEM_EQUIPE) if u["usina"] != "Altair" else u for u in R.com_manutencao(d["usinas"], 30)]
    r = RE.cartoes(us, d["ranking_por_usina"], d["tecnicos_por_equipe"], [u for u in us if u["usina"] == "Coração 1"])
    assert [(c["equipe"], c["usinas"]) for c in r["cartoes"]] == [(visao.SEM_EQUIPE, 1)]


def test_sem_equipe_vai_para_o_fim_sem_posicao(tela):  # noqa: F811
    d = R.visao_responsaveis().dados
    # a Brodowski 1 (nota 90, a melhor da tela) sem equipe no cadastro: nem com nota ela ganha posição
    us = [dict(u, equipe=visao.SEM_EQUIPE) if u["usina"] == "Brodowski 1" else u for u in R.com_manutencao(d["usinas"], 30)]
    r = RE.cartoes(us, d["ranking_por_usina"], d["tecnicos_por_equipe"])
    assert [c["equipe"] for c in r["cartoes"]] == ["SC Oeste 01", "SP Norte 01", visao.SEM_EQUIPE]
    assert r["cartoes"][-1]["sem_equipe"] and r["cartoes"][-1]["posicao"] is None and r["cartoes"][-1]["cor"] == "neutro"
    assert r["total"] == 1 and r["kpis"]["equipes"] == 2 and r["cartoes"][1]["posicao"] == 1


def test_a_seta_contra_o_periodo_anterior(tela):  # noqa: F811
    d = R.visao_responsaveis().dados

    def agg(s, n):
        return {"q_soma": s, "q_n": n, "n_os": n, "n_ronda": 0, "rondada": True}
    por = {1: {"atual": agg(450, 5), "anterior": agg(350, 5)}, 2: {"atual": agg(90, 1), "anterior": agg(70, 1)},
           3: {"atual": agg(80, 1), "anterior": agg(100, 1)}}
    r = {c["equipe"]: c for c in RE.cartoes(R.com_manutencao(d["usinas"], 30), por, d["tecnicos_por_equipe"])["cartoes"]}
    assert (r["SP Norte 01"]["posicao"], r["SP Norte 01"]["antes"]["posicao"]) == (1, 2)
    assert r["SP Norte 01"]["seta"] == {"tipo": "sobe", "n": 1} and r["SC Oeste 01"]["seta"] == {"tipo": "desce", "n": 1}


# ── A revisão do ramo (18/10/2026) ───────────────────────────────────────────────────────────────────────────────
def _ua(uid, perf=(), acomp=(), manut=(), **kw):
    """Uma usina com os alertas dos três blocos (área, nível), como `responsaveis.montar`/`com_manutencao` deixam."""
    def bloco(xs):
        return {"alertas": [{"area": a, "nivel": n, "titulo": ""} for a, n in xs]}
    return {"usina_id": uid, "perf": bloco(perf), "acomp": bloco(acomp), "manut": bloco(manut), "meta": {},
            "manutencao": {}, "ativos": {}, **kw}


def test_toda_area_com_alerta_vira_etiqueta():
    # achado 1 da revisão: o semáforo do cartão conta TODOS os alertas da Visão, e a etiqueta só olhava 12 números; uma
    # equipe só com um ativo em crítico mostrava "Performance 1 · 0 · 0" e, embaixo, "nada a cobrar nos três blocos"
    ativo = _ua(1, perf=[("ativos", "critico")], ativos={"lista": [{"nivel": "critico"}]})
    assert [(e["cls"], e["txt"]) for e in RE.etiquetas({}, [ativo])] == [("critico", "1 ativo em crítico")]
    ext = _ua(2, acomp=[("extintores", "atencao")])
    assert [(e["cls"], e["txt"]) for e in RE.etiquetas({}, [ext])] == [
        ("alerta", "extintores a vencer ou sem conferência em 1 usina")]
    pt = _ua(3, acomp=[("pt", "atencao")])
    assert [(e["cls"], e["txt"]) for e in RE.etiquetas({"pts": 1}, [pt])] == [("alerta", "1 PT esperando o De acordo")]
    # a disponibilidade da usina, não a média do grupo pela potência (que escondia uma usina abaixo de 80%)
    disp = _ua(4, perf=[("disp", "critico")])
    assert [(e["cls"], e["txt"]) for e in RE.etiquetas({"disp": 99.2}, [disp])] == [
        ("critico", "disp. abaixo de 80% em 1 usina")]
    pr = _ua(5, perf=[("meta", "atencao")], meta={"atingimento": 99.0})
    assert [(e["cls"], e["txt"]) for e in RE.etiquetas({}, [pr])] == [("alerta", "1 usina com PR abaixo do previsto")]


def test_nada_a_cobrar_so_quando_o_semaforo_esta_todo_em_dia(tela):  # noqa: F811
    d = R.visao_responsaveis().dados
    for c in RE.cartoes(R.com_manutencao(d["usinas"], 30), d["ranking_por_usina"], d["tecnicos_por_equipe"])["cartoes"]:
        pede = any(c["tri"][b]["critico"] or c["tri"][b]["atencao"] for b in ("perf", "acomp", "manut"))
        assert bool(c["etiquetas"]) == pede, c["equipe"]


def test_usina_mobilizada_depois_do_periodo_anterior_fica_fora_dele(tela):  # noqa: F811
    # achado 3 da revisão: a usina mobilizada há 10 dias contava como "sem ronda" no período anterior, quando ainda não
    # era da operação: a cobertura de antes caía e a seta "subia" sem a equipe ter melhorado
    a = RE.agregar([], [{"data": "2026-09-01", "usina_id": 2, "nota": 90}], {1, 2}, HOJE,
                   desde={1: "2026-10-10", 2: "2026-09-01"})
    assert a[1]["anterior"] is None and a[1]["atual"] is not None
    assert a[2]["anterior"]["rondada"] is True
    d = R.visao_responsaveis().dados

    def agg(s, n):
        return {"q_soma": s, "q_n": n, "n_os": n, "n_ronda": 0, "rondada": True}
    por = {1: {"atual": agg(450, 5), "anterior": agg(350, 5)}, 2: {"atual": agg(90, 1), "anterior": None},
           3: {"atual": agg(80, 1), "anterior": agg(100, 1)}}
    r = {c["equipe"]: c for c in RE.cartoes(R.com_manutencao(d["usinas"], 30), por, d["tecnicos_por_equipe"])["cartoes"]}
    assert r["SP Norte 01"]["antes"]["nota"] == 82          # só a Altair: 0,6 × 70 + 0,4 × 100 (antes: 62, com 50%)


# ── O motivo da nota (Levi, 18/10/2026: "Clicando na equipe deve dar um breve resumo do motivo da pontuação da equipe
# estar abaixo para que o supervisor possa cobrar a equipe") ────────────────────────────────────────────────────────
CRITERIOS = (("Subtarefas obrigatórias", 25), ("Fotos", 20), ("Fotos com descrição", 10), ("Assinatura", 10),
             ("Observações", 15), ("GPS no fechamento", 20))


def _itens(faltas=None):
    """A "Composição da nota" do App já lida: os seis critérios, cheios menos os de `faltas` = {critério: (pts, det)}."""
    faltas = faltas or {}
    return [{"rot": r, "peso": p, "pts": faltas.get(r, (p, ""))[0], "det": faltas.get(r, (p, "ok"))[1]}
            for r, p in CRITERIOS]


def _detalhe():
    tarefas = [{"dia": "2026-10-17", "usina_id": 3, "os": "801", "tarefa": "Limpeza do inversor", "tecnico": "Técnico Um",
                "nota": 60, "itens": _itens({"Fotos": (0, "0 fotos (3 dá o total)"), "GPS no fechamento": (0, "sem posição")})},
               {"dia": "2026-10-16", "usina_id": 3, "os": "802", "tarefa": "Inspeção", "tecnico": "Técnico Dois",
                "nota": 100, "itens": _itens()}]
    rondas = [{"dia": "2026-10-17", "usina_id": 3, "os": "501", "tecnico": "Técnico Um", "nota": 50,
               "falhas": "checklist incompleto; item sem foto de evidência"}]
    return {"tarefas": tarefas, "rondas": rondas}


def test_o_motivo_da_nota_fecha_com_a_nota():
    us = [{"usina_id": 3, "usina": "Coração 1"}, {"usina_id": 6, "usina": "Nova Era"}]
    por = {3: {"atual": {"rondada": True}}, 6: {"atual": {"rondada": False}}}
    # qualidade (60 + 100 + 50) ÷ 3 = 70; cobertura 1 de 2 = 50%; 0,6 × 70 + 0,4 × 50 = 62: perde 38 = 18 + 20
    n = RE.nota_da_equipe([{"q_soma": 210, "q_n": 3, "n_os": 2, "n_ronda": 1, "rondada": True},
                           {"q_soma": 0, "q_n": 0, "n_os": 0, "n_ronda": 0, "rondada": False}])
    m = RE.motivos(n, _detalhe(), us, por)
    assert (m["perde"], m["qualidade"]["perde"], m["cobertura"]["perde"]) == (38, 18, 20)
    # a ronda tira 0,6 × 50 ÷ 3 = 10; as fotos e o GPS da tarefa, 0,6 × 20 ÷ 3 = 4 cada (no empate, a ordem do App)
    assert [(p["rot"], p["perde"]) for p in m["qualidade"]["partes"]] == [("Rondas", 10), ("Fotos", 4),
                                                                         ("GPS no fechamento", 4)]
    assert m["qualidade"]["partes"][1]["det"] == "em 1 de 2 tarefas"
    assert m["qualidade"]["partes"][0]["det"] == ("1 de 1 ronda abaixo de 100; falhas: checklist incompleto (1), item "
                                                  "sem foto de evidência (1)")
    assert (m["cobertura"]["com"], m["cobertura"]["usinas"], m["cobertura"]["sem_ronda"]) == (1, 2, ["Nova Era"])
    # as notas mais baixas, a menor primeiro (a de 100 não perdeu nada), com o que faltou
    assert [(p["nota"], p["usina"], p["tecnico"]) for p in m["piores"]] == [(50, "Coração 1", "Técnico Um"),
                                                                            (60, "Coração 1", "Técnico Um")]
    assert m["piores"][0]["o_que"] == "Ronda · OS 501" and m["piores"][1]["o_que"] == "OS 801 · Limpeza do inversor"
    assert m["piores"][1]["faltou"] == "Fotos: 0 fotos (3 dá o total); GPS no fechamento: sem posição"
    assert m["piores"][0]["faltou"] == "checklist incompleto; item sem foto de evidência"
    # por técnico: a média das notas dele, a menor primeiro
    assert [(t["nome"], t["media"], t["n"]) for t in m["tecnicos"]] == [("Técnico Um", 55, 2), ("Técnico Dois", 100, 1)]


def test_os_pontos_que_a_nota_perde_sempre_fecham():
    # a parte de cada critério é exata; o inteiro na tela é repartido pelo maior resto, e a soma é a perda da nota
    for notas in ([67, 93, 88], [99, 98, 97, 61], [55]):
        tarefas = [{"dia": "2026-10-10", "usina_id": 1, "os": str(i), "tarefa": "", "tecnico": "", "nota": v,
                    "itens": _itens({"Fotos": (20 - (100 - v) * 0.4, "x"), "GPS no fechamento": (20 - (100 - v) * 0.35, "y"),
                                     "Observações": (15 - (100 - v) * 0.25, "z")})}
                   for i, v in enumerate(notas)]
        n = RE.nota_da_equipe([{"q_soma": sum(notas), "q_n": len(notas), "n_os": len(notas), "n_ronda": 0,
                                "rondada": True}])
        m = RE.motivos(n, {"tarefas": tarefas, "rondas": []}, [{"usina_id": 1, "usina": "A"}],
                       {1: {"atual": {"rondada": True}}})
        assert sum(p["perde"] for p in m["qualidade"]["partes"]) == m["qualidade"]["perde"], notas
        assert m["qualidade"]["perde"] + m["cobertura"]["perde"] == m["perde"] == 100 - n["nota"], notas


def test_tarefa_sem_a_composicao_da_nota_nao_some_da_conta():
    tarefas = [{"dia": "2026-10-10", "usina_id": 1, "os": "9", "tarefa": "", "tecnico": "", "nota": 70, "itens": []}]
    n = RE.nota_da_equipe([{"q_soma": 70, "q_n": 1, "n_os": 1, "n_ronda": 0, "rondada": True}])
    m = RE.motivos(n, {"tarefas": tarefas, "rondas": []}, [{"usina_id": 1, "usina": "A"}],
                   {1: {"atual": {"rondada": True}}})
    assert [(p["rot"], p["perde"]) for p in m["qualidade"]["partes"]] == [("Sem a composição da nota", 18)]


def test_equipe_sem_nota_nao_tem_conta_de_pontos():
    n = RE.nota_da_equipe([{"q_soma": 0, "q_n": 0, "n_os": 0, "n_ronda": 0, "rondada": False}])
    m = RE.motivos(n, {"tarefas": [], "rondas": []}, [{"usina_id": 1, "usina": "A"}],
                   {1: {"atual": {"rondada": False}}})
    assert m["perde"] is None and m["qualidade"]["partes"] == [] and m["cobertura"]["sem_ronda"] == ["A"]


def test_tarefas_iguais_da_mesma_os_viram_uma_linha():
    # medido em 18/10/2026: uma OS com 4 tarefas iguais (a mesma nota e o mesmo que faltou) ocupava 4 das 5 linhas
    igual = {"dia": "2026-10-15", "usina_id": 1, "os": "14909", "tarefa": "Verificação de tracker", "tecnico": "Técnico Um",
             "nota": 55, "itens": _itens({"Fotos": (0, "0 fotos (3 dá o total)")})}
    tarefas = [dict(igual) for _ in range(4)] + [dict(igual, os="16226", nota=48)]
    n = RE.nota_da_equipe([{"q_soma": 268, "q_n": 5, "n_os": 5, "n_ronda": 0, "rondada": True}])
    m = RE.motivos(n, {"tarefas": tarefas, "rondas": []}, [{"usina_id": 1, "usina": "A"}],
                   {1: {"atual": {"rondada": True}}})
    assert [(p["o_que"], p["nota"], p["vezes"]) for p in m["piores"]] == [
        ("OS 16226 · Verificação de tracker", 48, 1), ("OS 14909 · Verificação de tracker", 55, 4)]
    assert m["mais_piores"] == 0

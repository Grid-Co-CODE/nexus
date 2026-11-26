# -*- coding: utf-8 -*-
"""A conferência automática das OS de ETM pelos dados diários do PG (25/11/2026).

Levi: "Bata com os dados que a gente tem, os dados diários, no PG [...] se o PR não está abaixo de 50 ou se o PR não está
acima de 100. E se o IPOA não está abaixo do GHI. Aí se passar [...] dá como finalizado pela performance. E aí a gente vai
ter a visão só das ETMs com problema mesmo." Nas escolhas: 5 dias; a regra no período; o IPOA "até 8%" abaixo do GHI; a
OS sem dado fica na lista. Números de mentira (repositório público)."""
from datetime import date, timedelta

import pytest
from test_engenharia_etm import OSE, banco  # noqa: F401

from nexus.performance import etm_conferencia as C

HOJE = date(2026, 11, 25)
FIM = date(2026, 11, 15)          # a OS concluída no Fracttal


def dias(n=7, pr=80.0, ipoa=6.0, ghi=5.5, primeiro=date(2026, 11, 17), **muda):
    """`n` dias seguidos a partir de `primeiro`, com o PR, o IPOA e o GHI; `muda` = {dia: {campo: valor}}."""
    out = {}
    for i in range(n):
        d = primeiro + timedelta(days=i)
        out[d] = dict({"pr": pr, "ipoa": ipoa, "ghi": ghi}, **(muda.get(d.isoformat()) or {}))
    return out


def test_ok_com_os_5_dias_mais_recentes_depois_da_conclusao():
    """Os 5 mais recentes com dado, depois da conclusão e antes de hoje: o dia da conclusão, os de antes e o de hoje
    ficam de fora (o dia de hoje está pela metade)."""
    ds = dias(n=12, primeiro=date(2026, 11, 14))                    # de 14 a 25/11
    ds[date(2026, 11, 25)] = {"pr": 10.0, "ipoa": 1.0, "ghi": 9.0}  # hoje, ruim: não conta
    r = C.conferir(FIM, ds, HOJE)
    assert r["estado"] == "ok" and r["dias"] == ["2026-11-20", "2026-11-21", "2026-11-22", "2026-11-23", "2026-11-24"]
    assert r["pr"] == 80.0 and r["ipoa_ghi"] == pytest.approx(109.1, abs=0.1)
    assert "PR médio 80,0% e IPOA 109% do GHI em 5 dias (20/11 a 24/11)" in r["texto"]


@pytest.mark.parametrize("muda, motivo", [
    ({"pr": 45.0}, "PR médio 45,0% (abaixo de 50%)"),
    ({"pr": 104.0}, "PR médio 104,0% (acima de 100%)"),
    ({"ipoa": 5.0, "ghi": 5.5}, "IPOA 91% do GHI (abaixo de 92%)"),
])
def test_reprova_no_periodo(muda, motivo):
    r = C.conferir(FIM, {d: dict(x, **muda) for d, x in dias().items()}, HOJE)
    assert r["estado"] == "falha" and motivo in r["texto"] and r["motivos"] == [motivo]


def test_a_regra_vale_no_periodo_e_a_folga_de_8_por_cento():
    """Um dia com o inversor parado (PR 20%) não reprova se a média dos 5 fica na faixa; o IPOA a 93% do GHI passa."""
    ds = dias(**{"2026-11-23": {"pr": 20.0}})
    assert C.conferir(FIM, ds, HOJE)["estado"] == "ok"                   # (80 × 4 + 20) ÷ 5 = 68%
    assert C.conferir(FIM, dias(ipoa=5.12, ghi=5.5), HOJE)["estado"] == "ok"      # 93%
    assert C.conferir(FIM, dias(ipoa=5.0, ghi=5.5), HOJE)["estado"] == "falha"    # 91%


def test_dia_sem_algum_dos_tres_nao_conta_e_os_5_vem_de_mais_para_tras():
    ds = dias(n=8, primeiro=date(2026, 11, 16), **{"2026-11-24": {"ghi": None}, "2026-11-23": {"pr": None}})
    r = C.conferir(FIM, ds, HOJE)
    assert r["estado"] == "ok" and r["dias"] == ["2026-11-18", "2026-11-19", "2026-11-20", "2026-11-21", "2026-11-22"]


def test_aguardando_os_5_dias_e_depois_sem_dado():
    """Concluída há 3 dias: espera (a coleta grava ontem às 22:30). Concluída há 20 dias sem GHI: fica na lista, com o
    que falta."""
    recente = C.conferir(date(2026, 11, 22), dias(n=2, primeiro=date(2026, 11, 23)), HOJE)
    assert recente["estado"] == "aguardando" and recente["curto"] == "aguardando 2 de 5 dias"
    velha = C.conferir(date(2026, 11, 5), dias(n=10, ghi=None, primeiro=date(2026, 11, 15)), HOJE)
    assert velha["estado"] == "sem_dado" and "sem GHI em 10 de" in velha["texto"]
    assert C.conferir(None, dias(), HOJE)["estado"] == "sem_dado"
    lig = C.conferir(FIM, dias(), HOJE, sem_ligacao="a usina da OS não liga ao cadastro")
    assert lig["estado"] == "sem_dado" and "não liga" in lig["texto"]


def test_os_dados_das_abas_e_do_pr_publicado():
    """O IPOA do SENSOR ("IPOA (kWh/m²) ETM"), não o DEF; duas abas da mesma usina: a média; zero não é dado. O PR
    publicado liga à usina pelo nome."""
    aba1 = [{"Data": "2026-11-20", "IPOA (kWh/m²) ETM": 6.0, "IPOA (kWh/m²) DEF": 0, "GHI (kWh/m²)": 5.0},
            {"Data": "2026-11-21", "IPOA (kWh/m²) ETM": 0, "GHI (kWh/m²)": 5.0},
            {"Data": "2026-10-01", "IPOA (kWh/m²) ETM": 9.0, "GHI (kWh/m²)": 9.0}]
    aba2 = [{"Data": "2026-11-20", "IPOA (kWh/m²)": 8.0, "GHI (kWh/m²)": "5,4"}]
    d = C.dias_das_abas([aba1, aba2], date(2026, 11, 1), HOJE)
    assert d[date(2026, 11, 20)] == {"ipoa": 7.0, "ghi": 5.2} and d[date(2026, 11, 21)] == {"ipoa": None, "ghi": 5.0}
    assert date(2026, 10, 1) not in d
    pr = C.pr_por_usina([{"usina": "Alfa 1", "data_id": 20261120, "pr_pct": 70}, {"usina": "Alfa 2", "data_id": 20261120,
                                                                                   "pr_pct": 80},
                         {"usina": "Outra", "data_id": 20261120, "pr_pct": 50}, {"usina": "Alfa 1", "data_id": 20261121,
                                                                                 "pr_pct": None}],
                        lambda n: 7 if n.startswith("Alfa") else None, date(2026, 11, 1), HOJE)
    assert pr == {7: {date(2026, 11, 20): 75.0}}
    assert C.abas_da_usina([{"sistema": "BD_Thopen · aba", "chave_externa": "Alfa", "usina_id": 7},
                            {"sistema": "BD_Performance · aba", "chave_externa": "ALF100", "usina_id": "7"},
                            {"sistema": "Fracttal · Classificação 1", "chave_externa": "x", "usina_id": 7}]) == \
        {7: [("bd_thopen", "Alfa"), ("bd_performance", "ALF100")]}


def test_so_confere_a_concluida_no_fracttal_e_aberta_para_a_performance():
    oss = [{"wid": 1, "coluna_etm": "finalizada"}, {"wid": 2, "coluna_etm": "em_andamento"},
           {"wid": 3, "coluna_etm": "finalizada"}, {"wid": 4, "coluna_etm": "finalizada"}, {"wid": None, "coluna_etm": "finalizada"}]
    est = {"3": {"finalizado": True}, "4": {"diagnostico_id": 2}}
    assert [o["wid"] for o in C.candidatas(oss, est)] == [1]


def test_finalizar_marca_e_comenta_como_a_conferencia_automatica(banco):  # noqa: F811
    """A ok vira "Finalizado pela Performance" (origem "conferencia", quem = a conferência automática) com o comentário
    dos números; a que já estava finalizada fica como está."""
    from nexus.engenharia import etm_marcas as M
    from nexus.engenharia import os_acompanhamento as O
    r = C.conferir(FIM, dias(), HOJE)
    assert C.finalizar([(OSE, r)]) == ["1"]
    e = M.estado(M.ler(forcar=True)["eventos"])[str(OSE["wid"])]
    assert e["finalizado"] is True and e["eventos"][0]["nome"] == "Nexus (conferência automática)"
    assert banco.linhas(M.LIVRO, M.ABA)[-1]["origem"] == "conferencia"
    coment = [ev for ev in O.estado(O.ler(forcar=True)["eventos"])[O.chave_da_os(OSE["wid"])]["eventos"]
              if ev["evento"] == "comentario"]
    assert coment and coment[0]["texto"].startswith("Finalizado pela Performance: conferência automática")
    assert "PR médio 80,0%" in coment[0]["texto"]
    assert C.finalizar([(OSE, r)]) == []                                # de novo: nada


def test_a_rodada_finaliza_so_a_ok_e_guarda_o_resto_para_a_tela(banco, app, monkeypatch, tmp_path):  # noqa: F811
    from nexus.engenharia import etm as ETM
    from nexus.engenharia import etm_marcas as M
    from nexus.torres import engenharia as TE
    app.config["NEXUS_DADOS"] = str(tmp_path)
    oss = [{"wid": 50001, "os": 1, "coluna_etm": "finalizada", "fim_iso": "2026-11-15", "usina": "U1", "codigo": "A"},
           {"wid": 50002, "os": 2, "coluna_etm": "finalizada", "fim_iso": "2026-11-15", "usina": "U2", "codigo": "B"},
           {"wid": 50003, "os": 3, "coluna_etm": "em_andamento", "fim_iso": "", "usina": "U1", "codigo": "A"},
           {"wid": 50004, "os": 4, "coluna_etm": "finalizada", "fim_iso": "2026-11-15", "usina": "U3", "codigo": "C"}]
    monkeypatch.setattr(ETM, "dados", lambda: {"lido": 1.0, "os": oss})
    uid = {"U1": 1, "U2": 2, "U3": None}
    monkeypatch.setattr(TE, "_onde_do_cadastro", lambda: lambda usina, cod: {"usina_id": uid[usina], "ligada_por": "teste"})
    monkeypatch.setattr(TE, "_na_etm", lambda o: o)
    from nexus.campo import visao
    monkeypatch.setattr(visao, "_Base", lambda: object())
    monkeypatch.setattr(C, "ler_dias", lambda uids, base, sessao, b, hoje: ({1: dias(), 2: dias(pr=30.0)}, {}))
    monkeypatch.setattr(C, "datetime", type("D", (), {"now": staticmethod(lambda tz=None: __import__("datetime").datetime(
        2026, 11, 25, 15, 0, tzinfo=tz))}))
    r = C.rodar(app)
    assert r["finalizadas"] == 1 and r["por_estado"] == {"ok": 1, "falha": 1, "sem_dado": 1}
    est = M.estado(M.ler(forcar=True)["eventos"])
    assert est["50001"]["finalizado"] is True and "50002" not in est
    assert C.resultado(50002)["estado"] == "falha" and "PR médio 30,0%" in C.resultado(50002)["texto"]
    assert C.resultado(50004)["estado"] == "sem_dado"
    C._ESTADO.update(os={}, em=0)
    C.carregar(app.config)                                             # a subida lê a guardada em disco
    assert C.resultado(50002)["estado"] == "falha"
    C._ESTADO.update(os={}, em=0)


def test_a_tela_mostra_o_selo_so_na_aberta_para_a_performance():
    from nexus.torres.performance import etm_tela as T
    C._ESTADO["os"] = {"9": {"estado": "falha", "curto": "PR médio 30,0% (abaixo de 50%)", "texto": "Dados reprovados: x"}}
    try:
        o = {"wid": 9, "coluna_etm": "finalizada"}
        assert T._conf(o, {})["estado"] == "falha"
        assert T._conf(o, {"finalizado": True}) is None and T._conf(dict(o, coluna_etm="em_andamento"), {}) is None
    finally:
        C._ESTADO["os"] = {}

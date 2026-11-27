"""O livro do PR e da disponibilidade de cada usina e mês, com e sem o expurgo (27/11/2026; `nexus/comando/kpi_mes.py`).

Levi: "Eu tô sentindo falta do PR ponderado, PR expurgado [...] Pode até criar um book sobre isso para você não ficar
carregando, calculando toda vez que abre"; "Disponibilidade expurgada também, mesma lógica". Tudo inventado (o
repositório é público)."""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from nexus.comando import kpi_mes as KM
from test_contratos_editavel_18_11 import _como, carga  # noqa: F401 — a fixture da carga inicial

BRT = timezone(timedelta(hours=-3))
AGORA = datetime(2026, 11, 27, 10, 0, tzinfo=BRT)
G = {"clientes": [{"cliente": "SOLAR ALFA", "usinas": [
    {"uid": 7, "usina": "Zeta 1", "mwp": 2.5,
     "meses": {"2026-10": {"pr": 80.0, "disp": 97.0, "prod_kwh": 1000.4, "meta_kwh": 1200.0},
               "2026-11": {"pr": 1375.5, "disp": 99.0}, "2026-12": {"pr": 81.0}},
     "com_expurgo": {"2026-10": {"pr": 81.2, "disp": 98.5}}},
    {"uid": "8", "usina": "Zeta 2", "mwp": None, "meses": {"2026-10": {}}, "com_expurgo": {}}]}]}


def _i(c):
    return KM.CAB.index(c)


def test_as_linhas_saem_da_conta_da_visao_gerencial():
    ls = KM.linhas_do_portfolio(G, AGORA)
    assert [l[_i("kpi_id")] for l in ls] == ["7-202610", "7-202611"]   # o mês que não chegou e o sem número ficam fora
    out, nov = ls
    assert (out[_i("pr_pct")], out[_i("pr_exp_pct")], out[_i("disp_pct")], out[_i("disp_exp_pct")]) == (80.0, 81.2, 97.0, 98.5)
    assert out[_i("potencia_kwp")] == 2500 and out[_i("prod_kwh")] == 1000 and out[_i("mes_fechado")] == 1
    assert out[_i("data_id_mes")] == 20261001 and out[_i("usina_ligada_por")] == KM.LIGADA_POR
    # o PR acima de 100% é leitura errada: vazio; sem expurgo, o expurgado repete o bruto
    assert nov[_i("pr_pct")] == "" and nov[_i("disp_exp_pct")] == 99.0 and nov[_i("mes_fechado")] == 0


def test_o_mes_fechado_congela_no_dia_11_do_seguinte():
    assert not KM.congelado("2026-10", date(2026, 11, 10)) and KM.congelado("2026-10", date(2026, 11, 11))
    assert KM.congelado("2026-12", date(2027, 1, 11))
    novas = KM.linhas_do_portfolio(G, AGORA)                     # out/26 já congelou em 27/11
    banco = [dict(zip(KM.CAB, ["7-202610", "20261001", "7", KM.LIGADA_POR, "SOLAR ALFA", "2500", "79.0", "79.0", "96.0", "96.0",
                               "900", "1200", "1", "2026-11-12T00:00:00"])),
             dict(zip(KM.CAB, ["9-202610", "20261001", "9", KM.LIGADA_POR, "SOLAR ALFA", "", "70.0", "70.0", "", "", "", "", "1", "x"]))]
    todas, congeladas = KM.mesclar(banco, novas, AGORA.date())
    por = {l[_i("kpi_id")]: l for l in todas}
    assert congeladas == 1 and por["7-202610"][_i("pr_pct")] == "79.0"           # o do banco fica
    assert "9-202610" in por and "7-202611" in por                               # a do banco que não veio fica; a nova entra
    # antes do dia 11, o mês fechado ainda troca pela conta
    todas, congeladas = KM.mesclar(banco, novas, date(2026, 11, 5))
    assert congeladas == 0 and {l[_i("kpi_id")]: l for l in todas}["7-202610"][_i("pr_pct")] == 80.0


def test_a_leitura_aceita_numero_como_texto():
    linhas = [dict(zip(KM.CAB, ["7-202610", "20261001", "7", KM.LIGADA_POR, "SOLAR ALFA", "2500", "80", "81.2", "", "98.5",
                                "1000", "1200", "1", "x"]))]
    d = KM.por_usina(linhas)
    assert d == {7: {"2026-10": {"pr": 80.0, "pr_exp": 81.2, "disp": None, "disp_exp": 98.5, "kwp": 2500.0,
                                 "prod_kwh": 1000.0, "meta_kwh": 1200.0, "cliente": "SOLAR ALFA"}}}


def test_publicar_grava_so_quando_muda_e_uma_vez_por_hora(monkeypatch):
    gravado, banco = [], {"linhas": [], "atu": [], "quando": None}
    monkeypatch.setattr(KM.livros, "atualizado_em", lambda base, s, livro: banco["quando"])

    def ler(base, s, livro, aba):
        return banco["linhas"] if aba == KM.ABA else banco["atu"]
    monkeypatch.setattr(KM.livros, "ler", ler)

    def publicar(livro, nome, tabelas, **k):
        gravado.append(tabelas)
        cab, ls = tabelas[KM.ABA]
        banco["linhas"] = [dict(zip(cab, l)) for l in ls]
        cab, ls = tabelas["atualizacao"]
        banco["atu"] = [dict(zip(cab, l)) for l in ls]
        return {"ok": True}
    monkeypatch.setattr(KM.livros, "publicar", publicar)
    cfg = {"GRIDCO_SQL_TOKEN": "t"}
    assert "erro" in KM.publicar({}, G, sessao=SimpleNamespace(), agora=AGORA)
    r = KM.publicar(cfg, G, sessao=SimpleNamespace(), agora=AGORA)
    assert r["gravado"] and r["linhas"] == 2 and len(gravado) == 1
    banco["quando"] = (AGORA - timedelta(minutes=10)).isoformat()
    assert "pulou" in KM.publicar(cfg, G, sessao=SimpleNamespace(), agora=AGORA)              # gravou há 10 min
    banco["quando"] = (AGORA - timedelta(hours=2)).isoformat()
    r = KM.publicar(cfg, G, sessao=SimpleNamespace(), agora=AGORA + timedelta(hours=1))
    assert r.get("pulou") == "as linhas não mudaram" and len(gravado) == 1                   # o mesmo número não regrava
    assert "recusou" in KM.publicar(cfg, {"clientes": []}, sessao=SimpleNamespace(), agora=AGORA, forcar=True)


def test_a_aba_abre_pelo_livro_sem_esperar_a_conta(carga, cliente, monkeypatch):  # noqa: F811
    """Sem a conta da Visão gerencial (o Nexus acabou de subir), a aba lê o livro e abre, em vez de "montando"."""
    from nexus.campo import visao
    from nexus.torres.comando import contratos_tela as CT
    from nexus.torres.comando import gerencial_tela as GT
    monkeypatch.setattr(visao, "_agora", lambda: datetime(2026, 11, 27, 10, 0))
    monkeypatch.setattr(GT, "dados_gerencial_sem_esperar", lambda: None)
    monkeypatch.setattr(KM, "ler", lambda cfg: {7: {"2026-10": {"pr": 80.0, "pr_exp": 81.2, "disp": 97.0, "disp_exp": 98.5,
                                                                "kwp": 2500.0, "prod_kwh": None, "meta_kwh": None,
                                                                "cliente": "SOLAR ALFA"}}})
    monkeypatch.setattr(visao, "_Base", lambda: SimpleNamespace(por_id={7: {"nome": "Zeta 1"}}))
    monkeypatch.setattr(CT, "_fontes_da_ligacao", lambda cli, uids, ano: ({}, {}, {}, {}, []))
    monkeypatch.setattr(CT, "_metas_pr_bd", lambda uids, nomes: {})
    from nexus.campo import responsaveis as R
    monkeypatch.setattr(R, "Nomes", lambda b: None)
    cliente.application.extensions.pop("nexus_contratos_indicadores", None)
    adm = _como(cliente, "admin@gridco.com.br", admin=True)
    d = adm.get("/t/comando/contratos/indicadores.json", query_string={"cliente": "Solar Alfa"}).get_json()
    assert not d.get("montando") and d["usinas"][0]["usina"] == "Zeta 1" and d["usinas"][0]["mwp"] == 2.5
    linhas = {l["id"]: l for l in d["usinas"][0]["linhas"]}
    assert linhas["pr"]["cels"]["2026-10"]["txt"] == "80,0" and linhas["pr_exp"]["cels"]["2026-10"]["txt"] == "81,2"
    assert linhas["disp_exp"]["cels"]["2026-10"]["txt"] == "98,5"

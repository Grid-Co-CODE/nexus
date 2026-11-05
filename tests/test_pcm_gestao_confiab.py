"""Gestão PCM, parte C (Levi, 04/11/2026): a "Confiabilidade por ativo" e o "Tempo médio de reparo por Equipe Cluster"
da aba Gestão PCM do painel do PCM, com a conta da ENGENHARIA (decisão dele): os números são os da tela Engenharia >
Confiabilidade (`nexus/engenharia/confiabilidade.py`), na cópia de 5 min que a torre já guarda, sem calcular de novo nem
ler o Fracttal outra vez. O MTTR do cluster é a média por falha (cada falha pesa igual, como o MTTR do ativo).

Nada vai à rede: as OS de falha são de mentira e o cadastro é um `onde` fictício.
"""
from datetime import datetime, timedelta, timezone

import pytest
from werkzeug.datastructures import MultiDict

from nexus.engenharia import confiabilidade as C
from nexus.engenharia import os_falhas
from nexus.pcm import gestao as G
from nexus.pcm import gestao_confiab as GC

AGORA = datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc)
N1, S2, L1 = "Cliente A - Usina Norte 1 - SP", "Cliente A - Usina Sul 2 - BA", "Cliente B - Usina Leste 1 - CE"
CLUSTER = {"Usina Norte 1": "SP Leste 01", "Usina Sul 2": "BA Sul 01", "Usina Leste 1": "SP Leste 01"}


def _os(cod, dias_atras, usina=N1, horas=5.0, tipo="Corretiva", fim=True, folio=None, wid=None):
    cr = AGORA - timedelta(days=dias_atras)
    return {"wo_folio": folio or f"{cod[-2:]}{dias_atras}", "id_work_order": wid or (1000 + dias_atras),
            "id_work_orders_tasks": f"{cod}|{dias_atras}|{tipo}", "code": cod, "items_log_description": "Inversor {" + cod + "}",
            "groups_1_description": usina, "tasks_log_task_type_main": tipo, "description": f"Falha {cod} {dias_atras}",
            "task_note": "", "creation_date": cr.isoformat(), "event_date": cr.isoformat(),
            "initial_date": (cr + timedelta(hours=1)).isoformat(),
            "final_date": (cr + timedelta(hours=horas)).isoformat() if fim else None, "task_status": "DONE",
            "id_status_work_order": 3 if fim else 1}


def _onde(texto, cod):
    cli, usi = texto.split(" - ")[0], texto.split(" - ")[1]
    return {"usina_id": hash(usi) % 1000, "usina": usi, "cliente": cli, "cluster": CLUSTER.get(usi, ""), "uf": "SP",
            "equipe": "", "mobilizacao": None, "ligada_por": "de-para do Fracttal"}


def linhas():
    return ([_os("UNA100-INV01", d, horas=4.0) for d in (2, 30, 60)]                  # 3 falhas de 4 h
            + [_os("UNA100-INV02", d, horas=48.0) for d in (5,)]                        # 1 falha de 2 dias: 24 h
            + [_os("UNA100-INV02", 3, fim=False, wid=999, folio="9999")]                # aberta: conta, sem reparo
            + [_os("USB200-TRK01", d, usina=S2, horas=96.0, tipo="Religamento") for d in (10, 40)]   # 4 dias: 48 h
            + [_os("ULC300-INV01", d, usina=L1, horas=2.0) for d in (7, 8)])            # 2 h cada


@pytest.fixture
def eng(app, monkeypatch):
    """A Engenharia de mentira: as OS de falha completas, o cadastro fictício e a cópia da torre vazia."""
    from nexus.torres import engenharia as torre
    ls = linhas()
    monkeypatch.setattr(os_falhas, "pedir_releitura", lambda app=None: None)
    monkeypatch.setattr(os_falhas, "linhas", lambda: ls)
    est = {"lendo": False, "erro": "", "completa": True, "n": len(ls),
           "vivas_em": datetime(2026, 11, 4, 21, 10, tzinfo=timezone.utc).timestamp()}
    monkeypatch.setattr(os_falhas, "estado", lambda: dict(est))
    monkeypatch.setattr(torre, "_onde_do_cadastro", lambda: _onde)
    torre._CACHE.clear()
    GC.limpar()
    yield {"torre": torre, "est": est, "linhas": ls}
    torre._CACHE.clear()
    GC.limpar()


def _copia():
    c, aviso = GC.copia()
    assert aviso == "" and c is not None
    return c


def _f(**a):
    return G.filtros(MultiDict([(k, x) for k, v in a.items() for x in (v if isinstance(v, list) else [v])]))


def test_a_arvore_cliente_usina_ativo_com_os_numeros_da_engenharia(app, eng):
    with app.test_request_context("/t/pcm/gestao"):
        c = _copia()
        d = eng["torre"]._dados()["dados"]
        arv = GC.arvore(c, G.Filtros())
    assert [(x["nome"], x["n_usinas"], x["falhas"]) for x in arv] == [("Cliente A", 2, 7), ("Cliente B", 1, 2)]
    norte = arv[0]["usinas"][0]
    assert norte["nome"] == "Usina Norte 1" and norte["falhas"] == 5 and norte["cliente"] == "Cliente A"
    # na usina, os indicadores da Engenharia por usina (as medianas dos ativos), os mesmos da tela de lá
    ind = {r["nome"]: r for r in C.indicadores(d["ativos"], d["sinais"], "usina")}["Usina Norte 1"]
    assert (norte["mtbf"], norte["mttr"], norte["disp"]) == (ind["mtbf"], ind["mttr"], ind["disp"])
    # a tabela da usina: o ativo de mais falhas primeiro, com o MTBF, o MTTR e a disponibilidade dele lá
    tab = GC.tabela_da_usina(c, "Cliente A", "Usina Norte 1")
    eng_ativos = {a["cod"]: a for a in d["ativos"]}
    assert [a["cod"] for a in tab["ativos"]] == ["UNA100-INV01", "UNA100-INV02"]
    for a in tab["ativos"]:
        e = eng_ativos[a["cod"]]
        assert (a["mtbf"], a["mttr"], a["disp"], a["n"]) == (e["mtbf"], e["mttr"], e["disp"], e["n"])
    assert tab["ativos"][1]["n"] == 2 and tab["ativos"][1]["mttr"] == 24.0          # a aberta conta, sem reparo
    assert GC.tabela_da_usina(c, "Cliente A", "Usina que não existe") is None


def test_as_os_do_ativo_com_as_horas_de_reparo_que_fazem_o_mttr(app, eng):
    with app.test_request_context("/t/pcm/gestao"):
        c = _copia()
        tab = GC.tabela_da_usina(c, "Cliente A", "Usina Norte 1")
        oss = GC.os_do_ativo(c, "UNA100-INV02")
        assert GC.os_do_ativo(c, "NAO-EXISTE") is None
    assert "os" not in tab["ativos"][1]                    # as OS vêm à parte, quando o ativo abre (M2)
    assert [o["os"] for o in oss] == ["9999", "025"]                                # a de início mais novo primeiro
    aberta, fechada = oss
    assert (aberta["horas"], aberta["fim"], aberta["wid"], aberta["status"]) == ("—", "—", 999, "Em Processo")
    assert fechada["horas"] == "24,0" and fechada["status"] == "Concluída" and fechada["tipo"] == "Corretiva"
    assert fechada["url"] == "https://one.fracttal.com/tasks/wo/1005"
    assert fechada["inicio"] == (AGORA - timedelta(days=5) + timedelta(hours=1)).astimezone(G._BRT).strftime(
        "%d/%m/%Y %H:%M")
    # a média das horas das OS é o MTTR do ativo (a mesma conta, `confiabilidade.reparo_h`)
    inv1 = tab["ativos"][0]
    horas = [C.reparo_h(r) for r in eng["linhas"] if r["code"] == "UNA100-INV01"]
    assert inv1["mttr"] == sum(horas) / len(horas) == 4.0


def test_mttr_por_cluster_e_a_media_por_falha_os_piores_no_topo(app, eng):
    with app.test_request_context("/t/pcm/gestao"):
        cs = GC.clusters(_copia(), G.Filtros())
    assert [(c["nome"], round(c["mttr"], 4), c["falhas"]) for c in cs] == [
        ("BA Sul 01", 48.0, 2),
        # SP Leste 01: 3 falhas de 4 h + 1 de 24 h (a aberta fica fora da média) + 2 de 2 h = 40 h / 6 falhas; as
        # falhas são as da Engenharia (a aberta conta)
        ("SP Leste 01", round((3 * 4 + 24 + 2 * 2) / 6, 4), 7)]
    sp = cs[1]
    assert sp["cls"] == "ok" and cs[0]["cls"] == "and"                                # até 24 h verde, até 72 h âmbar
    assert (sp["com_reparo"], cs[0]["com_reparo"]) == (6, 2)
    assert [(u["nome"], u["cliente"], round(u["mttr"], 4), u["falhas"]) for u in sp["usinas"]] == [
        ("Usina Norte 1", "Cliente A", 9.0, 5), ("Usina Leste 1", "Cliente B", 2.0, 2)]
    assert sp["clientes"] == ["Cliente A", "Cliente B"]
    assert [GC.classe_mttr(x) for x in (None, 24, 24.01, 72, 72.5)] == ["nulo", "ok", "and", "and", "crit"]
    # a mesma definição do MTTR do ativo: o cluster de um ativo só tem o MTTR dele
    assert cs[0]["mttr"] == 48.0


def test_cluster_sem_cadastro_vai_por_ultimo_e_dito(app, eng, monkeypatch):
    def onde(texto, cod):
        r = _onde(texto, cod)
        return dict(r, cluster="") if r["usina"] == "Usina Sul 2" else r
    monkeypatch.setattr(eng["torre"], "_onde_do_cadastro", lambda: onde)
    eng["torre"]._CACHE.clear()
    with app.test_request_context("/t/pcm/gestao"):
        cs = GC.clusters(_copia(), G.Filtros())
    assert [(c["nome"], c["sem"]) for c in cs] == [("SP Leste 01", False),
                                                   ("Sem cluster no cadastro (ou sem ligação)", True)]


def test_os_filtros_de_cima_cliente_usina_e_cluster_sem_maiuscula(app, eng):
    with app.test_request_context("/t/pcm/gestao"):
        c = _copia()
        assert [x["nome"] for x in GC.arvore(c, _f(cliente="cliente b"))] == ["Cliente B"]
        # a usina da Gestão é o texto do Fracttal (Cliente - Usina - UF); a da Engenharia, o nome do cadastro
        so = GC.arvore(c, _f(usina=S2.upper()))
        assert [(x["nome"], [u["nome"] for u in x["usinas"]]) for x in so] == [("Cliente A", ["Usina Sul 2"])]
        assert [x["nome"] for x in GC.clusters(c, _f(cluster="sp leste 01"))] == ["SP Leste 01"]
        assert [x["nome"] for x in GC.clusters(c, _f(cliente="Cliente B"))] == ["SP Leste 01"]
        assert GC.clusters(c, _f(cliente="Cliente B"))[0]["usinas"][0]["nome"] == "Usina Leste 1"
        assert GC.arvore(c, _f(usina="Cliente C - Outra - MG")) == []
    # os outros filtros não se aplicam aqui, e a linha diz isso só quando algum está escolhido
    assert GC.nao_se_aplicam(G.Filtros()) == ""
    assert GC.nao_se_aplicam(_f(cliente="Cliente A")) == ""
    assert GC.nao_se_aplicam(_f(estado="Pausada")) == "o filtro de estado não se aplica aqui"
    assert GC.nao_se_aplicam(_f(tipo_tarefa="Corretiva", estado="Pausada", etiqueta="X", os="1", pini="2026-10-01")) \
        == "os filtros de tipo, etiqueta, estado, OS e período não se aplicam aqui"


def test_disponibilidade_pela_meta_da_engenharia_e_as_horas_no_formato_de_la():
    assert [GC.classe_disp(x) for x in (None, 0.8499, C.META_DISP, 0.99)] == ["nulo", "crit", "ok", "ok"]
    assert [GC.horas(x) for x in (None, 0, 25.94, 99.96, 5737.2)] == ["—", "0,0", "25,9", "100,0", "5.737"]
    assert [GC.pct(x) for x in (None, 0.873, 1)] == ["—", "87,3%", "100,0%"]


def test_sem_a_leitura_das_os_de_falha_completa_nao_mostra_numero(app, logado, eng, monkeypatch):
    monkeypatch.setattr(os_falhas, "estado", lambda: dict(eng["est"], completa=False))
    monkeypatch.setattr(eng["torre"], "_dados", lambda: (_ for _ in ()).throw(AssertionError("calculou")))
    for cf in ("conf", "mttr"):
        r = logado.get(f"/t/pcm/gestao?cf={cf}")
        h = r.get_data(as_text=True)
        assert r.status_code == 200 and "leitura do Fracttal ainda não terminou: tente em alguns minutos" in h
        assert "data-pgc-incompleta" in h and "MTBF" not in h


def test_as_rotas_usam_a_mesma_copia_da_engenharia(app, logado, eng, monkeypatch):
    """A conta é a da Engenharia, uma vez por cópia: a Confiabilidade, o MTTR e a tabela de cada usina não calculam de
    novo (nem leem o Fracttal: a releitura é a da torre)."""
    contas = []
    original = C.calcular
    monkeypatch.setattr(C, "calcular", lambda *a, **k: contas.append(1) or original(*a, **k))
    h = logado.get("/t/pcm/gestao?cf=conf&cliente=Cliente+A").get_data(as_text=True)
    assert "Usina Norte 1" in h and "Usina Leste 1" not in h and "Cliente B" not in h
    assert 'data-quando="04/11 18:10"' in h                                            # a hora da leitura, em Brasília
    assert 'data-cc="Cliente A" data-cu="Usina Norte 1"' in h
    h = logado.get("/t/pcm/gestao?cf=mttr").get_data(as_text=True)
    assert "SP Leste 01" in h and "BA Sul 01" in h and h.index("BA Sul 01") < h.index("SP Leste 01")
    r = logado.get("/t/pcm/gestao", query_string={"cf": "usina", "cc": "Cliente A", "cu": "Usina Norte 1"})
    h = r.get_data(as_text=True)
    assert r.status_code == 200 and "UNA100-INV01" in h and 'data-r="MTBF (h)"' in h        # cartão no celular
    # as OS de um ativo vêm só quando ele abre (M2: uma usina grande tinha 1.090 OS no pedaço da usina)
    assert 'data-wid="999"' not in h and 'data-ca="UNA100-INV02"' in h
    r = logado.get("/t/pcm/gestao", query_string={"cf": "ativo", "ca": "UNA100-INV02"})
    h = r.get_data(as_text=True)
    assert r.status_code == 200 and 'data-wid="999"' in h and "9999" in h and 'data-r="Horas de reparo"' in h
    # M1: o que é o Início e a regra das horas à vista (no celular o title do cabeçalho some)
    assert "<th>Início do trabalho</th>" in h and "do incidente ao fim" in h.split("</table>", 1)[1]
    assert logado.get("/t/pcm/gestao?cf=ativo&ca=NAO-EXISTE").status_code == 404
    assert len(contas) == 1
    assert logado.get("/t/pcm/gestao?cf=xyz").status_code == 404
    assert logado.get("/t/pcm/gestao", query_string={"cf": "usina", "cc": "Cliente A",
                                                     "cu": "Outra"}).status_code == 404


def test_a_pagina_da_gestao_nao_espera_a_conta_da_engenharia(app, logado, eng, tmp_path, monkeypatch):
    import json
    from test_pcm_gestao_filtros import tarefas
    p = tmp_path / "gestao_pcm.json"
    p.write_text(json.dumps({"geradoEm": "2026-11-04T20:50:31", "dataHash": "conf-tela", "tarefas": tarefas()}),
                 encoding="utf-8")
    app.config["NEXUS_PCM_GESTAO_FONTE"] = str(p)
    monkeypatch.setattr(eng["torre"], "_dados", lambda: (_ for _ in ()).throw(AssertionError("esperou a Engenharia")))
    monkeypatch.setattr(os_falhas, "estado", lambda: (_ for _ in ()).throw(AssertionError("leu as OS de falha")))
    html = logado.get("/t/pcm/gestao?estado=Pausada").get_data(as_text=True)
    sub = html.split('id="pgc-conf"', 1)[1].split("</summary>", 1)[0]
    assert ("MTBF · MTTR · Disponibilidade inerente · base: Corretiva, Corretiva emergencial, Religamento, Religamento"
            " remoto · conta da Engenharia") in sub
    assert "o filtro de estado não se aplica aqui" in sub
    sub = html.split('id="pgc-mttr"', 1)[1].split("</summary>", 1)[0]
    assert "verde até 24 h, âmbar até 72 h, vermelho acima" in sub and "o filtro de estado não se aplica aqui" in sub


# ── rodada 1 da revisão (05/11/2026) ─────────────────────────────────────────────────────────────────────────
def test_sem_o_cadastro_nao_mostra_numero(app, logado, eng, monkeypatch):
    """I2: com o cadastro fora, a conta da Engenharia segue com os nomes do Fracttal, sem cluster e com a mobilização de
    20/10/2025 para todas: número enganoso, e os filtros de cliente e cluster param de casar. Aqui não sai número: o
    bloco diz por quê, com o "Tentar de novo", e nada fica guardado."""
    def onde(texto, cod):
        return _onde(texto, cod)
    onde.sem_cadastro = True
    monkeypatch.setattr(eng["torre"], "_onde_do_cadastro", lambda: onde)
    eng["torre"]._CACHE.clear()
    for cf in ("conf", "mttr"):
        r = logado.get(f"/t/pcm/gestao?cf={cf}")
        h = r.get_data(as_text=True)
        assert r.status_code == 200 and "O cadastro do Nexus não respondeu: tente em alguns minutos" in h
        assert "data-pgc-incompleta" in h and "data-tentar" in h and "MTBF" not in h and "SP Leste" not in h
    assert logado.get("/t/pcm/gestao", query_string={"cf": "usina", "cc": "Cliente A",
                                                     "cu": "Usina Norte 1"}).get_data(as_text=True).count("MTBF") == 0
    assert GC._COPIA == {}


def test_os_dois_mttr_da_mesma_usina_dizem_qual_e_qual(app, logado, eng):
    """I3: a mesma usina tem dois MTTR: na Confiabilidade, a MEDIANA dos ativos (a regra da Engenharia); no bloco do
    cluster, a média POR FALHA. Os dois ficam, cada um com o nome dele e uma frase na legenda."""
    h = logado.get("/t/pcm/gestao?cf=conf").get_data(as_text=True)
    usina = h.split('data-cu="Usina Norte 1"', 1)[1].split("</summary>", 1)[0]
    assert "mediana dos 2 ativos" in usina
    assert "mediana dos ativos" in h.split('class="pg-leg pgc-leg"', 1)[1] and "MTTR por falha" in h.split(
        'class="pg-leg pgc-leg"', 1)[1]
    h = logado.get("/t/pcm/gestao?cf=mttr").get_data(as_text=True)
    assert "<th>MTTR por falha (h)</th>" in h and "<b>MTTR por falha</b>" in h
    assert "não é a mediana dos ativos" in h.split('class="pg-leg pgc-leg"', 1)[1]


def test_a_copia_daqui_nao_prende_a_conta_da_engenharia(app, logado, eng):
    """M8: a cópia daqui guarda só o índice e os resultados; a conta inteira vem da torre a cada pedido (sem segurar a
    cópia velha de ~5 MB até o pedido seguinte)."""
    assert logado.get("/t/pcm/gestao?cf=conf").status_code == 200
    guardada = GC._COPIA["c"]
    assert set(guardada) == {"marca", "idx", "res", "quando"}


def test_sem_cliente_e_sem_usina_ditos_e_por_ultimo():
    """O ativo que nem o cadastro nem o Fracttal ligam a um cliente ou a uma usina não vai para um grupo "—" (Levi,
    05/11/2026: "ajusta o grupo '—' para dizer sem cliente no cadastro e mostrar qual usina é"): o cliente vira "Sem
    cliente no cadastro", a usina sem nome é dita pelo prefixo do código dos ativos, e o grupo fica por último."""
    d = {"ativos": [{"cod": "IPX100-INVR1.1", "cliente": "—", "usina": "—"},
                    {"cod": "UNA100-INV01", "cliente": "Cliente A", "usina": "Usina Norte 1"},
                    {"cod": "XYZ300-TRK1", "cliente": "", "usina": "Usina Solta"}]}
    assert set(GC._grupos(d)) == {(GC.SEM_CLIENTE, "Sem usina (código IPX100)"), ("Cliente A", "Usina Norte 1"),
                                  (GC.SEM_CLIENTE, "Usina Solta")}
    assert GC.SEM_CLIENTE == "Sem cliente no cadastro"
    assert sorted(["SEMP", GC.SEM_CLIENTE, "Athon"], key=GC.ordem_cliente) == ["Athon", "SEMP", GC.SEM_CLIENTE]

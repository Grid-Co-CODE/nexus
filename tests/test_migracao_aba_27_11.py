"""A migração única da aba Equipamentos para o Nexus (27/11/2026). Levi: "NÃO PODE EXISTIR ABA ANTIGA, TUDO TEM QUE SER
NOVO E INTERLIGAR" e "Resolva". Antes de os leitores deixarem a aba, entra no Nexus o que só ela tem: as chaves da usina
do Registro sem estrutura nenhuma (a Segredo, com a "1.2 (643)" da aba virando a "1.2 (889)" que a API PV manda), os
inversores da chave do Nexus que não tem nenhum (a CPP100) e o kWp que o Nexus não tem (a Pharma 2). Uma vez só: a marca
na pasta de dados segura a segunda. Nenhum teste vai à rede: o banco é o falso."""
import json

import pytest
from pg_falso import ApiPGFalsa
from test_campo_visao import _aba

from nexus.cadastro import estrutura_usina as E
from nexus.cadastro import telas_equipamentos as T

BASE = "http://pg.falso"
SEGREDO, CPP, PHARMA = 128, 54, 108
COLS = ("Cliente", "Usina", "Usina Supervisório", "Usina Fractall", "Equipamento", "Equipamento Supervisório",
        "Equipamento Parente", "Potência (kWp)", "N de Inversores", "Strings Ativas", "Full O&M", "String Box")


def _l(**kw):
    return {c: kw.get(c) for c in COLS}


def _inv(chave, usina, n, m, ug, kwp=None, strings=20, sup=None):
    return _l(**{"Cliente": "Thopen", "Usina": usina, "Usina Supervisório": chave, "Equipamento": f"Inversor {n}.{m}",
                 "Equipamento Supervisório": sup or f"INVERSOR0{m}", "Equipamento Parente": ug, "Potência (kWp)": kwp,
                 "Strings Ativas": strings, "Full O&M": "Sim", "String Box": "Não"})


def _ufv(usina, kwp, ugs=(), chave=None):
    comum = {"Cliente": "Thopen", "Usina": usina, "Usina Supervisório": chave, "Full O&M": "Sim", "String Box": "Não"}
    return ([_l(**comum, **{"Equipamento": "UFV", "Potência (kWp)": kwp})]
            + [_l(**comum, **{"Equipamento": ug, "Equipamento Parente": "UFV", "Potência (kWp)": k}) for ug, k in ugs])


ABA_SEGREDO = (_ufv("Segredo", 6697.08, [("UG 01", 6697.08)])
               + [_inv("Segredo 1.1 (643)", "Segredo", 1, m, "UG 01", 167.4, 24) for m in (1, 2)]
               + [_inv("Segredo 1.2 (643)", "Segredo", 2, m, "UG 01", 167.4, 24) for m in (1, 2)])
MAPA_SEGREDO = {SEGREDO: [("Segredo 1.2 (643)", "Segredo 1.2 (889)"), ("Segredo 1.1 (643)", ""), ("Segredo", "")]}


@pytest.fixture(autouse=True)
def _sem_copias():
    E._CACHE.clear()
    yield
    E._CACHE.clear()


@pytest.fixture
def banco():
    api = ApiPGFalsa()
    _aba(api, "bd_performance", "Equipamentos", ABA_SEGREDO)
    return api


@pytest.fixture
def cfg():
    return {"GRIDCO_SQL_TOKEN": "token-de-teste", "NEXUS_PESSOA_HMAC": "chave-de-teste"}


def _livro(banco):
    return {k: banco.linhas(E.LIVRO, a) for k, a in (("sup", E.ABA_SUP), ("cab", E.ABA_CAB), ("inv", E.ABA_INV))}


def test_a_usina_sem_estrutura_nasce_da_aba_com_o_nome_que_a_api_manda(cfg, banco):
    r = E.migrar_da_aba(cfg, BASE, banco, aba_chaves=E.agrupar_aba(ABA_SEGREDO), mapa=MAPA_SEGREDO)
    assert (r["usinas"], r["chaves"], r["inversores"]) == (1, 3, 4)
    lv = _livro(banco)
    sup = {s["usina_supervisorio"]: s for s in lv["sup"]}
    # a chave da UFV vira a da usina, venha em que ordem vier no mapa; a 1.2 vai com o nome da API PV
    assert set(sup) == {"Segredo", "Segredo 1.1 (643)", "Segredo 1.2 (889)"}
    assert sup["Segredo"]["principal"] in (1, True) and not any(s["substitui_aba"] for s in lv["sup"])
    assert {(i["nome"], i["equipamento_supervisorio"], i["strings_esperadas_qtd"], i["potencia_kwp"])
            for i in lv["inv"]} == {("Inversor 1.1", "INVERSOR01", 24, 167.4), ("Inversor 1.2", "INVERSOR02", 24, 167.4),
                                    ("Inversor 2.1", "INVERSOR01", 24, 167.4), ("Inversor 2.2", "INVERSOR02", 24, 167.4)}
    assert [c["nome"] for c in lv["cab"]] == ["UG 01"]
    # a 2ª vez não faz nada: a usina já tem estrutura, e o que está no Nexus vale
    r2 = E.migrar_da_aba(cfg, BASE, banco, aba_chaves=E.agrupar_aba(ABA_SEGREDO), mapa=MAPA_SEGREDO)
    assert (r2["usinas"], r2["chaves"], r2["inversores"]) == (0, 0, 0) and r2["puladas"]
    assert len(_livro(banco)["inv"]) == 4


def test_a_chave_do_nexus_sem_inversor_recebe_os_da_aba_e_a_que_tem_fica(cfg, banco):
    """A CPP100 (27/11/2026): a chave ligada no Nexus, nenhum inversor, 14 na aba. A Segredo, já com os dela, não muda."""
    aba = _ufv("Capitão Poço 100", 4910.0, [("UG 01", 700.0)], chave="CPP100")
    _aba(banco, "bd_performance", "Equipamentos", aba)
    E.ligar_pela_aba({"ligar": {CPP: ["CPP100"]}}, E.agrupar_aba(aba), cfg, BASE, banco)
    assert _livro(banco)["inv"] == []
    aba2 = aba + [_inv("CPP100", "Capitão Poço 100", 1, 1, "UG 01", 356.371, 18, "INV_1"),
                  _inv("CPP100", "Capitão Poço 100", 2, 1, "UG 02", 356.371, 18, "INV_3")]
    r = E.migrar_da_aba(cfg, BASE, banco, aba_chaves=E.agrupar_aba(aba2), mapa={})
    lv = _livro(banco)
    assert r["inversores"] == 2 and {i["equipamento_supervisorio"] for i in lv["inv"]} == {"INV_1", "INV_3"}
    assert sorted(c["nome"] for c in lv["cab"]) == ["UG 01", "UG 02"]      # a UG 02, que o Nexus não tinha, nasce
    r2 = E.migrar_da_aba(cfg, BASE, banco, aba_chaves=E.agrupar_aba(aba2), mapa={})
    assert r2["inversores"] == 0 and len(_livro(banco)["inv"]) == 2


def test_o_kwp_que_o_nexus_nao_tem_vem_da_aba_e_o_que_ele_tem_fica(cfg, banco):
    """A Pharma 2 (27/11/2026): os 6 inversores no Nexus sem kWp, 170,52 e 158,34 na aba."""
    aba = _ufv("Pharmas 2", 990.0, [("UG 01", None)], chave="Pharma 2") + [
        _inv("Pharma 2", "Pharmas 2", 1, 1, "UG 01", None, 14), _inv("Pharma 2", "Pharmas 2", 1, 2, "UG 01", 99.0, 14)]
    _aba(banco, "bd_performance", "Equipamentos", aba)
    E.ligar_pela_aba({"ligar": {PHARMA: ["Pharma 2"]}}, E.agrupar_aba(aba), cfg, BASE, banco)
    aba2 = _ufv("Pharmas 2", 990.0, [("UG 01", 998.76)], chave="Pharma 2") + [
        _inv("Pharma 2", "Pharmas 2", 1, 1, "UG 01", 170.52, 14), _inv("Pharma 2", "Pharmas 2", 1, 2, "UG 01", 158.34, 14)]
    r = E.migrar_da_aba(cfg, BASE, banco, aba_chaves=E.agrupar_aba(aba2), mapa={})
    lv = _livro(banco)
    assert {i["equipamento_supervisorio"]: i["potencia_kwp"] for i in lv["inv"]} == {"INVERSOR01": 170.52,
                                                                                     "INVERSOR02": 99.0}
    assert [c["potencia_kwp"] for c in lv["cab"]] == [998.76] and r["kwp"] == 2


def test_o_mapa_da_migracao_nao_repete_chave_nem_nome():
    da_aba = [a for pares in E.MIGRACAO_ABA.values() for a, _c in pares]
    no_nexus = [c or a for pares in E.MIGRACAO_ABA.values() for a, c in pares]
    assert len(da_aba) == len(set(da_aba)) == 38 and len(no_nexus) == len(set(no_nexus))
    assert {"União", "Rodrigues 2", "AP. do Taboado"}.isdisjoint(da_aba)          # as cópias do que o Nexus já tem
    assert dict(E.MIGRACAO_ABA[128])["Segredo 1.2 (643)"] == "Segredo 1.2 (889)"
    assert dict(E.MIGRACAO_ABA[28])["Aruanã (56)"] == "Aruanã"


def test_o_nome_do_fracttal_e_o_de_verdade_nao_o_codigo_sem_classificacao():
    br = [{"chave": "(sem Classificação 1) BWK100"}, {"chave": "(sem Classificação 1) BWK200"},
          {"chave": "Thopen - Brodowski 1 - SP"}]
    assert T._fracttal_da_usina(br) == "Thopen - Brodowski 1 - SP"
    assert T._fracttal_da_usina(br[:1]) == "(sem Classificação 1) BWK100"
    assert T._fracttal_da_usina([]) == "" and T._fracttal_da_usina(None) == ""


def test_a_migracao_roda_uma_vez_e_guarda_o_que_fez(tmp_path, monkeypatch):
    chamadas = []
    monkeypatch.setattr(E, "migrar_da_aba", lambda *a, **k: chamadas.append(k) or {"log": "migrou", "chaves": 3,
                                                                                   "visao_linhas": 9})
    cfg = {"NEXUS_DADOS": str(tmp_path), "GRIDCO_SQL_TOKEN": "t"}
    assert T._migrar_uma_vez(cfg, BASE, None, {}, {})["chaves"] == 3
    marca = json.loads((tmp_path / E.MIGRACAO_MARCA).read_text(encoding="utf-8"))
    assert marca["chaves"] == 3 and "visao_linhas" not in marca and marca["em"]
    assert T._migrar_uma_vez(cfg, BASE, None, {}, {}) is None and len(chamadas) == 1


# ── a visão TOTAL (27/11/2026): todas as usinas, sem marca nem comparação, para o leitor que já não lê a aba ──────────
def test_a_visao_total_traz_a_usina_nao_marcada_e_o_kwp_pelos_inversores_quando_o_registro_foge(cfg, banco):
    info = {SEGREDO: {"nome": "Segredo", "cliente": "Thopen", "kwp": 6700.0, "kwp_de": "contratual", "fracttal": "F"}}
    E.migrar_da_aba(cfg, BASE, banco, aba_chaves=E.agrupar_aba(ABA_SEGREDO), mapa=MAPA_SEGREDO, info=info)
    assert banco.linhas(E.LIVRO, E.ABA_VISAO) == []                     # nada marcado: a visão de antes fica vazia
    total = banco.linhas(E.LIVRO, E.ABA_VISAO_TOTAL)
    chaves = {(x["Usina Supervisório"], x["Equipamento"]) for x in total}
    assert (None, "UFV") in chaves and ("Segredo 1.2 (889)", "Inversor 2.1") in chaves and len(total) == 6
    ufv = next(x for x in total if x["Equipamento"] == "UFV")
    # 6.700 no Registro × 669,6 nos 4 inversores: foge, e vale a soma (o que a Sala usa hoje, como a aba)
    assert float(ufv["Potência (kWp)"]) == 669.6 and ufv["Usina Fractall"] == "F"
    # com o Registro perto da soma, vale o Registro
    info[SEGREDO]["kwp"] = 680.0
    E.republicar_visao(cfg, BASE, banco, info)
    ufv = next(x for x in banco.linhas(E.LIVRO, E.ABA_VISAO_TOTAL) if x["Equipamento"] == "UFV")
    assert float(ufv["Potência (kWp)"]) == 680.0


def test_a_gravacao_sem_info_nao_apaga_a_visao_total(cfg, banco):
    info = {SEGREDO: {"nome": "Segredo", "cliente": "Thopen", "kwp": 669.6, "kwp_de": "real", "fracttal": ""}}
    E.migrar_da_aba(cfg, BASE, banco, aba_chaves=E.agrupar_aba(ABA_SEGREDO), mapa=MAPA_SEGREDO, info=info)
    n = len(banco.linhas(E.LIVRO, E.ABA_VISAO_TOTAL))
    aba2 = ABA_SEGREDO + [_inv("Segredo 1.1 (643)", "Segredo", 1, 3, "UG 01", 167.4, 24)]
    E._CACHE.clear()
    E.migrar_da_aba(cfg, BASE, banco, aba_chaves=E.agrupar_aba(aba2), mapa={})   # grava sem `info`
    assert len(banco.linhas(E.LIVRO, E.ABA_VISAO_TOTAL)) == n == 6


def test_os_inversores_sem_chave_ganham_a_chave_da_aba_sem_dobrar(cfg, banco):
    """A Gravatá II (27/11/2026): os 10 inversores e a UG 01 no Nexus, nenhuma chave; nenhum leitor os achava. A chave
    nasce da aba, os inversores do Nexus passam a ela pelo nome (com o nome no supervisório e as strings da aba), o kWp
    do Nexus fica, e nenhum inversor dobra."""
    aba = _ufv("Gravatá II", 3396.48, [("UG 01", 3396.48)]) + [
        _inv("Gravatá II", "Gravatá II", 1, m, "UG 01", 339.6, 19) for m in (1, 2)]
    banco_ = banco
    ctl = {"criado_em": "x", "alterado_em": "x", "alterado_por_hmac": "x", "excluido": False}
    soltos = [{"inversor_id": 900 + m, "usina_id": 148, "supervisorio_id": None, "cabine_id": 1,
               "nome": f"Inversor 1.{m}", "equipamento_supervisorio": "", "potencia_kwp": 330.0,
               "strings_esperadas_qtd": None, "equipamento_id": None, "codigo_fracttal": "", "ordem": m, **ctl,
               "potencia_regra": "", "fracttal_ligado_por": "", "conferido_em": ""} for m in (1, 2)]

    def como_estava(est, agora, quem):          # o Nexus como a Gravatá II estava: a UG 01 e os inversores sem chave
        est["cabines"].append({"cabine_id": 1, "usina_id": 148, "nome": "UG 01", "potencia_kwp": None,
                               "equipamento_id": None, "codigo_fracttal": "", "ordem": 1, **ctl, "potencia_regra": ""})
        est["inversores"].extend(soltos)
        return {"log": "o estado da Gravatá II"}
    E._gravar(como_estava, cfg, BASE, banco_)
    r = E.migrar_da_aba(cfg, BASE, banco_, aba_chaves=E.agrupar_aba(aba), mapa={148: [("Gravatá II", "")]})
    lv = _livro(banco_)
    assert r["chaves"] == 1 and len(lv["inv"]) == 2 and len(lv["sup"]) == 1 and lv["sup"][0]["principal"] in (1, True)
    assert {(i["nome"], i["equipamento_supervisorio"], i["strings_esperadas_qtd"], i["potencia_kwp"])
            for i in lv["inv"]} == {("Inversor 1.1", "INVERSOR01", 19, 330.0), ("Inversor 1.2", "INVERSOR02", 19, 330.0)}
    assert all(i["supervisorio_id"] == lv["sup"][0]["supervisorio_id"] for i in lv["inv"])


def test_a_usina_agrupada_sai_com_uma_ufv_por_planta_na_visao_total(cfg, banco):
    """A Ipixuna 1 e 2 (27/11/2026): duas plantas, uma usina no Registro. Com uma UFV só (a da usina), a Ipixuna 2 passava
    de 1.823,3 a 3.079,1 kWp e a Ipixuna 1 ficava sem; agora cada planta sai com a dela, a soma dos inversores dela."""
    aba = (_ufv("Ipixuna 1", 300.0, [("UG 01", 300.0)]) + [_inv("(308) Ipixuna 1", "Ipixuna 1", 1, 1, "UG 01", 100.0)]
           + [_inv("(296) Ipixuna 2", "Ipixuna 2", 2, m, "UG 01", 150.0) for m in (1, 2)])
    _aba(banco, "bd_performance", "Equipamentos", aba)
    info = {SEGREDO: {"nome": "Ipixuna 1 e 2", "cliente": "Thopen", "kwp": 400.0, "kwp_de": "real", "fracttal": ""}}
    E.migrar_da_aba(cfg, BASE, banco, aba_chaves=E.agrupar_aba(aba), info=info,
                    mapa={SEGREDO: [("Ipixuna 1", ""), ("(308) Ipixuna 1", ""), ("(296) Ipixuna 2", "")]})
    ufv = {x["Usina"]: (x["Usina Supervisório"], float(x["Potência (kWp)"]), int(float(x["N de Inversores"])))
           for x in banco.linhas(E.LIVRO, E.ABA_VISAO_TOTAL) if x["Equipamento"] == "UFV"}
    assert ufv == {"Ipixuna 1": ("(308) Ipixuna 1", 100.0, 1), "Ipixuna 2": ("(296) Ipixuna 2", 300.0, 2)}


def test_a_migracao_leva_o_full_om_sim_e_o_nome_de_exibicao_dos_inversores(cfg, banco):
    """A CPP100 (o "Não" do cadastro inicial; a aba diz "Sim") e a Taguaí 1 (173) (os inversores dizem "Taguaí" na aba)."""
    aba = _ufv("Taguaí 1 (173)", 500.0, [("UG 01", 500.0)], chave="Taguaí 1 (173)") + [
        _inv("Taguaí 1 (173)", "Taguaí", 1, m, "UG 01", 250.0) for m in (1, 2)]
    so_a_ufv = [dict(x, **{"Full O&M": "Não"}) for x in aba[:2]]
    _aba(banco, "bd_performance", "Equipamentos", so_a_ufv)
    E.ligar_pela_aba({"ligar": {136: ["Taguaí 1 (173)"]}}, E.agrupar_aba(so_a_ufv), cfg, BASE, banco)
    s = _livro(banco)["sup"][0]
    assert (s["usina_exibicao"], s["full_om"]) == ("Taguaí 1 (173)", 0)
    r = E.migrar_da_aba(cfg, BASE, banco, aba_chaves=E.agrupar_aba(aba), mapa={})
    s = _livro(banco)["sup"][0]
    assert (s["usina_exibicao"], s["full_om"]) == ("Taguaí", 1)
    assert r["full_om"] == ["Taguaí 1 (173)"] and r["exibicao"] == ["Taguaí 1 (173)"]

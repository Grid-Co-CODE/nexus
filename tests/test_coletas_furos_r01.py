# -*- coding: utf-8 -*-
"""Os furos de coleta da analista (R01) calculados pelo Nexus (16/11/2026): o motor (`furos_r01.py`), as validações de todos
(`furos_conf.py`) e as rotas da aba "Furos de coleta". Nada vai à rede: o banco e o COS são dublados.

A prova contra o relatório de verdade (HTML R01 de 16/11 11:13: outubro igual nas 74.927 células, 1.189 coberturas e 186
paradas; novembro igual em coberturas e paradas) está contada no CLAUDE.md da pasta; aqui ficam os casos de referência do
documento da analista (§11) em miniatura, para a regra não escorregar.
"""
import datetime as dt
import io
import json
import os
import re

import pytest

from nexus.performance.coletas import furos_conf as FC
from nexus.performance.coletas import furos_r01 as R

CAB = ["Usina", "Data", "IPOA (kWh/m²)", "IPOA DEF", "GHI (kWh/m²)", "Inversor 1.1", "Inversor 1.2", "Inversor 2.1", "Obs"]
HOJE = dt.date(2026, 11, 10)                    # d-2 = 08/11
AGORA = dt.datetime(2026, 11, 10, 12, 0)


def linha(dia, ipoa, idef, ghi, a, b, c, usina="U", mes=11):
    return [usina, dt.datetime(2026, mes, dia), ipoa, idef, ghi, a, b, c, "ok"]


def linhas_u():
    return [
        linha(1, 5.0, None, 4.0, 10, 11, 12),
        linha(1, 0, None, 0, 0, 0, 0),                  # a data repetida: vale a 1ª
        linha(2, None, 3.0, None, 0, 11, 12),           # IPOA só no DEF; GHI vazio; 1.1 zerado com os outros gerando
        linha(3, 0, None, 0, 0, 0, 0),                  # usina sem geração no dia: não é furo
        # o dia 4 não tem linha
        linha(5, 5.0, None, 4.0, None, "-", 12),        # vazio e texto contam como vazio
        [None, dt.datetime(2026, 11, 6), 0, 0, 0, 0, 0, 0, "acumulado"],   # linha solta sem Usina: ignorada
        linha(6, 5.0, None, 4.0, 10, 11, 12),
        linha(7, 5.0, None, 4.0, 10, 11, 12),
        linha(8, None, None, 4.0, 10, 11, 12),
        linha(9, 5.0, None, 4.0, 10, 11, 12),           # depois de d-2: não é avaliado
    ]


def info(nome, cod, cliente, desc=None, carteira=None):
    r = [None] * 25
    r[1], r[2], r[3], r[4], r[24] = nome, desc, cod, cliente, carteira
    return r


def gerar(abas, cos=None, congelado=None, infos=None, base=None, hoje=HOJE, agora=AGORA):
    return R.gerar([("BD_Performance", abas)], infos or [info("U", "CLI-U100", "Cliente X")],
                   base or [["U", "CLI-U100", "Cliente X", "SP", "Supervisora", "OPERAÇÃO"]], cos, congelado, hoje, agora)


def cos(**k):
    d = {"OS": "", "Início": "", "Normalização": "", "Cliente": "Cliente X", "Código da usina": "", "Usina": "U", "Falha": "",
         "Equipamentos": "", "Geração parou": "sim"}
    d.update({{"os": "OS", "ini": "Início", "fim": "Normalização", "cliente": "Cliente", "usina": "Usina", "falha": "Falha",
               "eq": "Equipamentos", "parou": "Geração parou", "cod": "Código da usina"}[a]: b for a, b in k.items()})
    return d


def st(res, mes="2026-11", usina="U"):
    p = next(p for p in res["months"][mes]["plants"] if p["usina"] == usina)
    return p, {e["nome"]: e for e in p["eqs"]}


# ── os estados (§3 e §4) ─────────────────────────────────────────────────────────────────────────────────────────
def test_estados_d2_linhas_soltas_e_data_repetida():
    res = gerar([("U", CAB, linhas_u())])
    assert res["months"]["2026-11"]["end"] == 8 and res["stats"]["d1"] == "2026-11-08"
    p, e = st(res)
    assert [x["nome"] for x in p["eqs"]] == ["IPOA", "GHI", "Inversor 1.1", "Inversor 1.2", "Inversor 2.1"]
    assert e["IPOA"]["st"] == "odpxooov"
    assert e["GHI"]["st"] == "ovpxoooo"
    assert e["Inversor 1.1"]["st"] == "ozpxvooo"
    assert e["Inversor 1.2"]["st"] == "oopxvooo"
    assert e["Inversor 2.1"]["st"] == "oopxoooo"
    assert (p["cliente"], p["status"], p["supervisor"], p["days"]) == ("Cliente X", "OPERAÇÃO", "Supervisora", list(range(1, 9)))
    assert res["stats"]["linhas_ignoradas"] == 2             # a data repetida e a linha sem Usina


def test_o_ultimo_dia_do_mes_fechado_e_o_ultimo_com_geracao_de_qualquer_usina():
    out = [linha(d, 5.0, None, 4.0, 10, 11, 12, mes=10) for d in range(1, 21)] + \
          [linha(d, None, None, None, None, None, None, mes=10) for d in range(21, 32)]
    res = gerar([("U", CAB, out + linhas_u())])
    assert res["months"]["2026-10"]["end"] == 20 and res["months"]["2026-11"]["end"] == 8


def test_aba_sem_data_na_coluna_b_backup_e_sem_equipamento_ficam_fora():
    abas = [("U", CAB, linhas_u()), ("U - Backup", CAB, linhas_u()), ("Solta", ["Usina", "Dia", "Inversor 1.1"], [["x", dt.datetime(2026, 11, 1), 1]]),
            ("Só GHI", ["Usina", "Data", "GHI"], [["x", dt.datetime(2026, 11, 1), 1]])]
    assert [p["usina"] for p in gerar(abas)["months"]["2026-11"]["plants"]] == ["U"]


def test_ultragaz_valor_acima_de_5x_a_mediana_e_coleta_equivocada():
    cab = ["Usina", "Data", "Multimedidor 1", "Inversor 1.1"]
    ls = [["U", dt.datetime(2026, 10, d), 100.0, 50.0] for d in range(1, 13)]
    ls += [["U", dt.datetime(2026, 11, 1), 100.0, 50.0], ["U", dt.datetime(2026, 11, 2), 100.0, 400.0], ["U", dt.datetime(2026, 11, 3), 100.0, 50.0]]
    ult = gerar([("U", cab, ls)], infos=[info("U", "ULT-U100", "Ultragaz Matriz")], hoje=dt.date(2026, 11, 5))
    assert st(ult)[1]["Inversor 1.1"]["st"] == "oao"          # 400 > 5 × 50
    outro = gerar([("U", cab, ls)], hoje=dt.date(2026, 11, 5))
    assert st(outro)[1]["Inversor 1.1"]["st"] == "ooo"        # a régua é só da Ultragaz (decisão da analista)


def test_aba_velha_do_banco_e_a_que_para_antes_do_mes_da_maioria():
    f = {"A": dt.datetime(2026, 11, 30), "B": dt.datetime(2026, 11, 30), "Iramaia": dt.datetime(2026, 10, 31), "Vitesse": dt.datetime(2026, 9, 30),
         "Futura": dt.datetime(2027, 3, 31)}
    assert sorted(R.velhas(f)) == ["Iramaia", "Vitesse"]
    assert R.velhas({}) == {}


# ── o COS e o cruzamento (§6) ─────────────────────────────────────────────────────────────────────────────────────
def test_cabine_cobre_os_inversores_dela_com_6h_na_janela_solar():
    res = gerar([("U", CAB, linhas_u())], [
        cos(os="100", ini="05/11/2026 06:00", fim="05/11/2026 13:00", falha="Desligamento de cabine", eq="Cabine 1"),
        cos(os="101", ini="05/11/2026 13:00", fim="05/11/2026 18:00", falha="Desligamento de inversor", eq="Inversor 2.1"),   # 5 h: não cobre
        cos(os="102", ini="02/11/2026 00:00", fim="02/11/2026 23:00", falha="Falha de comunicação", eq="", parou="não"),
        cos(os="103", ini="02/11/2026 00:00", fim="02/11/2026 23:00", falha="Falha de comunicação", eq="", parou=""),
        cos(os="16493", ini="04/11/2026 00:00", fim="04/11/2026 23:00", falha="Desligamento de usina"),
        cos(os="104", ini="04/11/2026 00:00", fim="04/11/2026 23:00", falha="Desligamento de usina", cliente="E1 Energia"),
    ])
    p, e = st(res)
    assert e["Inversor 1.1"]["cv"] == {"4": [0]} and e["Inversor 1.2"]["cv"] == {"4": [0]}     # o dia 5 (índice 4), vazio nos dois
    assert "cv" not in e["Inversor 2.1"] and "cv" not in e["IPOA"]                             # a cabine nunca cobre a estação
    assert p["os"] == [["C", "100", "UG 1", "Desligamento de cabine", "05/11 06:00", "05/11 13:00", ""]]
    rej = res["stats"]["cos_rejeitados"]
    assert rej["COS: geração não parou / não informado (não)"] == 1 and rej["COS: geração não parou / não informado (vazio)"] == 1
    assert rej["16493"] == 1 and rej["E1 fora do escopo"] == 1 and res["stats"]["cos_registros"] == 2


def test_parada_aberta_vale_ate_agora_sem_os_e_ponto_de_atencao_e_a_fechada_vence_a_aberta():
    res = gerar([("U", CAB, linhas_u())], [
        cos(os="", ini="08/11/2026 06:00", fim="", falha="Desligamento de usina"),
        cos(os="200", ini="04/11/2026 05:00", fim="", falha="Desligamento de usina"),                       # a versão aberta da mesma OS sai
        cos(os="200", ini="04/11/2026 05:00", fim="04/11/2026 19:00", falha="Desligamento de usina"),
    ])
    p, e = st(res)
    assert p["os"] == [["C", "s/ nº", "UFV", "Desligamento de usina", "08/11 06:00", "10/11 12:00 (aberta)", "A"],
                       ["C", "200", "UFV", "Desligamento de usina", "04/11 05:00", "04/11 19:00", ""]]
    assert e["IPOA"]["cv"] == {"7": [0], "3": [1]}             # a usina toda cobre a estação: o vazio do dia 8 e a linha ausente do 4
    assert e["Inversor 1.1"]["cv"] == {"3": [1]}               # o dia 8 foi coletado: "o" nunca vira esperado
    assert res["stats"]["cos_rejeitados"]["_linhas_descartadas_duplicidade"] == 1


def test_usina_agrupada_so_aplica_o_equipamento_que_existe_numa_so():
    cab1 = ["Usina", "Data", "IPOA", "Inversor 1.1", "Inversor 1.2"]
    cab2 = ["Usina", "Data", "IPOA", "Inversor 2.1", "Inversor 2.2"]
    def ls(u):
        return [[u, dt.datetime(2026, 11, d), None, None, None] for d in range(1, 9)] + [[u, dt.datetime(2026, 11, 9), 1, 1, 1]]
    res = gerar([("Coração 1", cab1, ls("Coração 1")), ("Coração 2", cab2, ls("Coração 2"))], [
        cos(os="1", ini="02/11/2026 06:00", fim="02/11/2026 18:00", usina="Coração 1 e 2", falha="Desligamento de inversor", eq="Inversor 2.1"),
        cos(os="2", ini="03/11/2026 06:00", fim="03/11/2026 18:00", usina="Coração 1 e 2", falha="Desligamento de inversor", eq="Inversor 9.9"),
        cos(os="3", ini="04/11/2026 06:00", fim="04/11/2026 18:00", usina="Coração 1 e 2", falha="Desligamento de usina"),
    ], infos=[info("Coração 1", "C1", "Thopen"), info("Coração 2", "C2", "Thopen")], base=[])
    p1, e1 = st(res, usina="Coração 1")
    p2, e2 = st(res, usina="Coração 2")
    assert [o[1] for o in p1["os"]] == ["3"] and [o[1] for o in p2["os"]] == ["1", "3"]
    assert e2["Inversor 2.1"]["cv"] == {"1": [0], "3": [1]} and e1["IPOA"]["cv"] == {"3": [0]}
    assert res["stats"]["cos_rejeitados"]["usina agrupada: equipamento ambíguo"] == 1


def test_o_cos_inteiro_do_mes_vai_para_a_tela_com_as_horas_sem_mexer_na_conta(monkeypatch):
    """Levi, 19/11/2026: "linka com as ocorrências [...] do COS para responder [...] se naquele dia teve desligamento, foi
    de que horas até que horas". Toda ocorrência do mês vai para `oc` (a de menos de 6 h, a de geração que seguiu, a em
    aberto, até agora); só a que a regra do R01 usou leva o 1 de "explica o dia"; a OS 16493, o E1 e a que fica fora do
    mês verificado não entram; e a conta é a mesma com e sem elas."""
    linhas = [
        cos(os="100", ini="05/11/2026 06:00", fim="05/11/2026 13:00", falha="Desligamento de cabine", eq="Cabine 1"),
        cos(os="101", ini="05/11/2026 13:00", fim="05/11/2026 18:00", falha="Desligamento de inversor", eq="Inversor 2.1"),   # 5 h
        cos(os="102", ini="02/11/2026 00:00", fim="02/11/2026 23:00", falha="Falha de comunicação", eq="", parou="não"),
        cos(os="", ini="08/11/2026 06:00", fim="", falha="Desligamento de usina"),
        cos(os="16493", ini="04/11/2026 00:00", fim="04/11/2026 23:00", falha="Desligamento de usina"),
        cos(os="104", ini="04/11/2026 00:00", fim="04/11/2026 23:00", falha="Desligamento de usina", cliente="E1 Energia"),
        cos(os="105", ini="09/11/2026 08:00", fim="09/11/2026 09:00", falha="Falha de comunicação", parou=""),   # depois de d-2
    ]
    res = gerar([("U", CAB, linhas_u())], linhas)
    p, _ = st(res)
    assert p["oc"] == [
        ["2026-11-02T00:00", "2026-11-02T23:00", "Falha de comunicação", "", "102", "n", 0, 0],
        ["2026-11-05T06:00", "2026-11-05T13:00", "Desligamento de cabine", "Cabine 1", "100", "s", 0, 1],
        ["2026-11-05T13:00", "2026-11-05T18:00", "Desligamento de inversor", "Inversor 2.1", "101", "s", 0, 0],
        ["2026-11-08T06:00", "2026-11-10T12:00", "Desligamento de usina", "", "", "s", 1, 1],
    ]
    assert res["stats"]["cos_ocorrencias"] == 4
    monkeypatch.setattr(R, "ocorrencias_cos", lambda *a: 0)
    sem = gerar([("U", CAB, linhas_u())], linhas)
    p.pop("oc")
    res["stats"].pop("cos_ocorrencias")
    sem["stats"].pop("cos_ocorrencias")
    assert json.dumps(res, sort_keys=True, default=str) == json.dumps(sem, sort_keys=True, default=str)


def test_o_nome_do_cos_acha_a_aba_por_alias_combo_e_prefixo():
    def plantas(*nomes):
        return [{"usina": n, "eqs": []} for n in nomes]
    cad = R.cadastro([info("Pharma II", "PHS200", "Thopen", desc="Pharmas 2")], [])
    r = R.Resolvedor(plantas("Pharma II", "Junco 1", "Junco 2", "Ipixuna do Pará", "Mandaguaçu 1", "Mandaguaçu 2"), cad)
    assert r("Pharmas 2") == ["Pharma II"]                                   # a descrição do Info Geral
    assert r("Ipixuna do Pará 1") == ["Ipixuna do Pará"]                     # o alias manual da analista
    assert r("Junco 1, 2.1 e 2.2") == ["Junco 1", "Junco 2"]                 # o combo: "2.1" e "2.2" caem na aba "Junco 2"
    assert r("Mandaguaçu") == ["Mandaguaçu 1", "Mandaguaçu 2"]               # o prefixo
    assert r("Usina que não existe") == []
    muitas = R.Resolvedor(plantas(*["Santa %d" % i for i in range(1, 6)]), cad)
    assert muitas("Santa") == []                                             # prefixo com mais de 4 abas não vale


def test_outubro_congelado_e_o_ticket_que_entra_em_novembro():
    db = {"gen": "16/11/2026 11:13", "months": {
        "2026-10": {"plants": [{"src": "BD_Performance", "usina": "U", "os": [["F+T", "900", "UFV", "Queda de energia", "30/10 06:00", "31/10 18:00", ""]]}]},
        "2026-11": {"plants": [{"src": "BD_Performance", "usina": "U", "os": [
            ["T", "15538", "UFV", "Queda de energia", "06/10 10:34", "04/11 11:30", ""],
            ["C", "777", "UFV", "Desligamento de usina", "01/11 00:00", "02/11 00:00", ""]]}]}}}
    cong = R.congelar(db)
    assert cong == {"2026-10": {"BD_Performance|U": [["F+T", "900", "UFV", "Queda de energia", "30/10 06:00", "31/10 18:00", ""]]},
                    "2026-11": {"BD_Performance|U": [["T", "15538", "UFV", "Queda de energia", "06/10 10:34", "04/11 11:30", ""]]}}   # a do COS não se congela
    out = [linha(d, None, None, None, None, None, None, mes=10) for d in range(1, 30)] + [linha(30, 1, None, 1, 1, 1, 1, mes=10), linha(31, 1, None, 1, None, None, 5, mes=10)]
    res = gerar([("U", CAB, out + linhas_u())], [], cong)
    p10, e10 = st(res, "2026-10")
    assert e10["Inversor 1.1"]["cv"] == {"30": [0]} and p10["os"][0][:2] == ["F+T", "900"]      # 31/10 vazio, coberto pela parada congelada
    p11, e11 = st(res)
    assert p11["os"] == [["T", "15538", "UFV", "Queda de energia", "06/10 10:34", "04/11 11:30", ""]]
    assert e11["Inversor 1.1"]["cv"] == {"1": [0], "2": [0]}                                    # o zerado do dia 2 e o sem geração do dia 3
    # o registro do COS com a mesma OS substitui o ticket (§6.7.8)
    res = gerar([("U", CAB, linhas_u())], [cos(os="15538", ini="04/11/2026 06:00", fim="04/11/2026 18:00", falha="Desligamento de usina")], cong)
    assert [o[0] for o in st(res)[0]["os"]] == ["C"]


def test_le_o_html_da_ana_com_as_marcacoes():
    html = ('<script>\nconst DB={"gen":"16/11/2026 11:13","months":{"2026-10":{"end":31,"plants":[]}}};\n'
            'DB.conf=/*CONF0*/{"BD_Performance|U|IPOA":{"r":"sem_ipoa","v":"*","o":"a<\\/b *\\/","t":"2026-10-09T12:15:14.355Z"}}/*END0*/;\n</script>')
    db, conf = R.ler_html_r01(html)
    assert db["gen"] == "16/11/2026 11:13" and conf["BD_Performance|U|IPOA"]["o"] == "a</b */"
    with pytest.raises(ValueError):
        R.ler_html_r01("<html></html>")


# ── as validações (§8.4 e a regra permanente da analista) ─────────────────────────────────────────────────────────────────
K = "BD_Performance|U|IPOA"


def test_importar_so_acrescenta_vence_o_mais_recente_e_guarda_copia(tmp_path):
    c = FC.Confirmacoes(str(tmp_path))
    r = c.importar({K: {"r": "sem_ipoa", "v": "*", "o": "", "t": "2026-10-09T12:00:00.000Z"},
                    "BD_Performance|U|GHI": {"r": "sem_ghi", "v": "2026-10,2026-11", "o": "x", "t": "2026-10-09T12:00:00.000Z"},
                    "lixo": {"r": "sem_ipoa", "v": "*"}, K + "@2026-11": {"r": "motivo que não existe", "v": "2026-11"}}, "analista", "confirmacoes_furos.json")
    assert (r["novas"], r["invalidas"], r["total"]) == (2, 2, 2)
    # mais velha não cobre; mais nova cobre; a que não veio no arquivo continua (nunca perde)
    r = c.importar({K: {"r": "outro", "v": "*", "o": "velha", "t": "2026-10-01T00:00:00.000Z"}}, "analista", "velho.json")
    assert (r["mais_novas_no_nexus"], r["atualizadas"], r["total"]) == (1, 0, 2)
    r = c.importar({K: {"r": "coleta_alt", "v": "*", "o": "nova", "t": "2026-11-16T14:14:04.730Z"}}, "analista", "novo.json")
    conf, rev = c.ler()
    assert (r["atualizadas"], r["total"], conf[K]["r"], len(conf)) == (1, 2, "coleta_alt", 2) and rev == 2
    assert len(os.listdir(tmp_path / "confirmacoes_backup")) == 1          # a cópia de antes da 2ª gravação
    hist = [json.loads(x) for x in open(tmp_path / FC.ARQ_HIST, encoding="utf-8")]
    assert [h["acao"] for h in hist] == ["importar", "importar"] and hist[-1]["origem"] == "novo.json"


def test_validar_grava_quem_e_quando_e_o_conflito_nao_grava_nada(tmp_path):
    c = FC.Confirmacoes(str(tmp_path))
    conf, rev = c.aplicar([{"k": K, "v": {"r": "sem_ipoa", "v": "2026-11", "o": ""}, "base": ""}], "Fulana")
    t1 = conf[K]["t"]
    assert conf[K]["q"] == "Fulana" and t1.endswith("Z") and rev == 1
    # outra pessoa, com a tela velha (não viu a 1ª gravação): nada do pedido entra, nem a chave que não conflita
    with pytest.raises(FC.Conflito) as e:
        c.aplicar([{"k": K, "v": {"r": "outro", "v": "2026-11", "o": ""}, "base": ""},
                   {"k": "BD_Performance|U|GHI", "v": {"r": "sem_ghi", "v": "*", "o": ""}, "base": ""}], "Beltrano")
    assert e.value.chaves == [K] and list(c.ler()[0]) == [K]
    # com o `t` certo: a validação por dia, e depois apagar
    conf, _ = c.aplicar([{"k": K, "v": {"r": "", "v": "2026-11", "o": "", "dm": {"2026-11": {"06": "os", "7": "sem_ipoa"}}}, "base": t1}], "Beltrano")
    assert conf[K]["dm"] == {"2026-11": {"6": "os", "7": "sem_ipoa"}} and conf[K]["q"] == "Beltrano"
    conf, rev = c.aplicar([{"k": K, "v": None, "base": conf[K]["t"]}], "Beltrano")
    assert conf == {} and rev == 3
    hist = [json.loads(x) for x in open(tmp_path / FC.ARQ_HIST, encoding="utf-8")]
    assert len(hist) == 3 and hist[-1]["depois"] is None and hist[-1]["antes"]["dm"]        # o que foi apagado fica no histórico


@pytest.mark.parametrize("op", [
    {"k": "sem|barras", "v": {"r": "os", "v": "*"}}, {"k": "Outra|U|IPOA", "v": {"r": "os", "v": "*"}},
    {"k": K, "v": {"r": "inventado", "v": "*"}}, {"k": K, "v": {"r": "os", "v": "novembro"}},
    {"k": K, "v": {"r": "os", "v": "2026-11", "dm": {"2026-11": {"32": "os"}}}}, {"k": K + "@11", "v": {"r": "os", "v": "*"}}])
def test_validacao_torta_nao_entra(tmp_path, op):
    with pytest.raises(ValueError):
        FC.Confirmacoes(str(tmp_path)).aplicar([dict(op, base="")], "x")
    assert not os.path.exists(tmp_path / FC.ARQ_CONF)


def test_arquivo_ilegivel_nunca_e_sobrescrito(tmp_path):
    (tmp_path / FC.ARQ_CONF).write_text("{ quebrado", encoding="utf-8")
    c = FC.Confirmacoes(str(tmp_path))
    with pytest.raises(FC.Ilegivel):
        c.aplicar([{"k": K, "v": {"r": "os", "v": "*", "o": ""}, "base": ""}], "x")
    with pytest.raises(FC.Ilegivel):
        c.importar({K: {"r": "os", "v": "*"}}, "x", "a.json")
    assert (tmp_path / FC.ARQ_CONF).read_text(encoding="utf-8") == "{ quebrado"


def test_a_tela_3_recebe_so_o_que_ela_entende():
    conf = {K: {"r": "os", "v": "2026-10,2026-11", "o": "a", "t": "1"},
            "BD_Performance|U|GHI": {"r": "sem_ghi", "v": "*", "o": "", "t": "1"},
            "BD_Performance|U|Inversor 1.1": {"r": "os", "v": "2026-11", "o": "", "t": "1", "dm": {"2026-11": {"6": "os"}}},
            "BD_Performance|U|Inversor 1.2@2026-11": {"r": "fora_op", "v": "2026-11", "o": "", "t": "1"},
            "BD_Performance|U|Inversor 2.1": {"r": "", "v": "2026-11", "o": "só comentário", "t": "1"}}
    out = FC.para_tela3(conf, "2026-11")
    assert out == {K: {"r": "os", "v": "2026-11", "o": "a", "t": "1"},
                   "BD_Performance|U|GHI": {"r": "sem_ghi", "v": "*", "o": "", "t": "1"},
                   "BD_Performance|U|Inversor 1.2": {"r": "fora_op", "v": "2026-11", "o": "", "t": "1"}}


def test_as_paradas_congeladas_so_trocam_por_relatorio_mais_novo(tmp_path):
    c = FC.Congeladas(str(tmp_path))
    assert c.meses() == {}
    assert c.importar({"2026-10": {"BD_Performance|U": [["F", "1"]]}}, "16/11/2026 11:13", "R01.html", "x")["congelados"] == ["2026-10"]
    r = c.importar({"2026-10": {"BD_Performance|U": []}, "2026-11": {"BD_Performance|U": [["T", "2"]]}}, "11/11/2026 11:07", "velho.html", "x")
    assert r == {"congelados": ["2026-11"], "mantidos": ["2026-10"]}
    assert c.meses()["2026-10"] == {"BD_Performance|U": [["F", "1"]]}


# ── as rotas ────────────────────────────────────────────────────────────────────────────────────────────────────
class BancoDeMentira:
    """O db_performace como a API devolve (row_number, headers, values; a data em texto ISO)."""

    def __init__(self):
        def aba(cab, linhas, primeira=2):
            return [{"row_number": primeira + i, "headers": cab, "values": [v.strftime("%Y-%m-%dT00:00:00") if isinstance(v, dt.datetime) else v for v in r]}
                    for i, r in enumerate(linhas)]
        self.dados = {
            "p:U": aba(CAB, linhas_u()),
            "p:Velha": aba(CAB, [linha(d, 1, None, 1, 1, 1, 1, usina="Velha", mes=10) for d in range(1, 31)]),
            "p:Info Geral": aba(["x"] * 25, [info("U", "CLI-U100", "Cliente X")], primeira=3),
            "p:Base UFV": aba(["Usina", "Código", "Cliente", "Estado", "Supervisor", "Status"], [["U", "CLI-U100", "Cliente X", "SP", "Supervisora", "OPERAÇÃO"]]),
            "t:T": aba(CAB, [linha(d, 5.0, None, 4.0, 10, 11, 12, usina="T") for d in range(1, 10)]),
        }

    def livros(self):
        return {"bd_performance": {"updated_at": "2026-11-09T23:47:01-03:00"}, "bd_thopen": {"updated_at": "2026-11-09T23:58:05-03:00"}}

    def abas(self):
        out = {"bd_performance": {}, "bd_thopen": {}}
        for k in self.dados:
            out["bd_performance" if k[0] == "p" else "bd_thopen"][k[2:]] = {"id": k, "sheet_name": k[2:], "header_row": 1}
        return out

    def linhas(self, sid):
        return self.dados[sid]


@pytest.fixture
def furos(app, logado, tmp_path):
    csv = tmp_path / "ocorrencias.csv"
    csv.write_text("OS;Início;Normalização;Cliente;Código da usina;Usina;Falha;Equipamentos;Geração parou\n"
                   "100;05/11/2026 06:00;05/11/2026 13:00;Cliente X;CLI-U100;U;Desligamento de cabine;Cabine 1;sim\n", encoding="utf-8-sig")
    app.config.update(NEXUS_COLETAS_BANCO=BancoDeMentira, NEXUS_COLETAS_TMP=str(tmp_path), NEXUS_FUROS_COS_CSV=str(csv),
                      NEXUS_FUROS_RELOGIO=lambda: AGORA)
    return logado


def _dados(c):
    for _ in range(50):
        d = c.get("/t/performance/coletas/furos/r01").get_json()
        if d["pronto"] and not d["calculando"]:
            return d
        import time
        time.sleep(0.1)
    raise AssertionError("a conta não saiu")


def test_a_aba_abre_no_padrao_do_nexus(furos):
    r = furos.get("/t/performance/coletas/furos-de-coleta")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and 'class="titulo-pagina">Furos de coleta</h1>' in html
    assert "gc-explica" in html and 'class="gc-subabas"' in html and 'aria-current="page">Furos de coleta</a>' in html
    assert "/static/coletas-furos.js" in html and "/static/filtros-os.js" in html and "/static/coletas-furos.css" in html
    casca = furos.get("/t/performance/coletas").get_data(as_text=True)
    assert "/t/performance/coletas/furos-de-coleta" in casca and 'aria-current="page">Conversor</a>' in casca


def test_ler_o_banco_de_8_em_8_da_o_mesmo_que_uma_aba_por_vez():
    """16/11/2026 ("demora para ler hein"): as abas do banco lidas ao mesmo tempo, na ordem do banco."""
    from nexus.performance.coletas import furos_fonte as FF
    um, oito = FF.ler_banco(BancoDeMentira(), juntas=1), FF.ler_banco(BancoDeMentira(), juntas=8)
    assert oito == um and oito["planilhas"] and oito["velhas"]["BD_Performance"] == [["Velha", "2026-10-30"]]


def test_abrir_a_coletas_ja_comeca_a_conta_e_o_cos_vem_junto_com_o_banco(furos, app):
    """A aba Furos de coleta não espera a 1ª conta quando a pessoa clica nela: abrir a Coletas já a começou. E o COS é
    lido enquanto o banco é lido (antes, só depois)."""
    import threading
    from nexus.torres.performance import furos_tela as FT
    cos_comecou, banco_viu_cos = threading.Event(), []

    class BancoQueOlha(BancoDeMentira):
        def linhas(self, sid):
            if not banco_viu_cos:                            # com o COS só depois do banco, isto esperaria à toa
                banco_viu_cos.append(cos_comecou.wait(3))
            return super().linhas(sid)
    ler_cos = FT.servico(app)._ler_cos

    def cos_que_avisa(agora):
        cos_comecou.set()
        return ler_cos(agora)
    app.config.update(NEXUS_COLETAS_BANCO=BancoQueOlha, NEXUS_FUROS_AQUECER=True)
    FT.servico(app)._ler_cos = cos_que_avisa
    assert furos.get("/t/performance/coletas").status_code == 200
    _res, rodando = FT.servico(app).resultado()
    assert rodando or _res                                   # a casca já pôs a conta para rodar
    d = _dados(furos)
    assert d["pronto"] and banco_viu_cos == [True] and d["fontes"]["cos"]["ligado"]


def test_a_conta_vem_do_banco_e_do_cos(furos):
    d = _dados(furos)
    assert sorted(p["usina"] for p in d["months"]["2026-11"]["plants"]) == ["T", "U"]        # a "Velha" (parou em outubro) saiu
    assert d["fontes"]["velhas"]["BD_Performance"] == [["Velha", "2026-10-30"]]
    assert d["fontes"]["bd"] == {"BD_Performance": "09/11/2026 23:47", "BD_Thopen": "09/11/2026 23:58"} and d["fontes"]["bd_atrasado"] == []
    assert d["fontes"]["cos"]["ligado"] and d["stats"]["cos_registros"] == 1
    p = next(p for p in d["months"]["2026-11"]["plants"] if p["usina"] == "U")
    e = {x["nome"]: x for x in p["eqs"]}
    assert e["Inversor 1.1"]["st"] == "ozpxvooo" and e["Inversor 1.1"]["cv"] == {"4": [0]}     # igual ao Excel, com a data em texto
    assert d["conf"] == {} and d["gen"] == "10/11/2026 12:00" and not any(k.startswith("_") for k in d)
    # a tela 3 do Conversor lê a mesma conta
    t3 = furos.get("/t/performance/coletas/furos").get_json()
    assert t3["nome"].startswith("Calculado pelo Nexus") and list(t3["db"]["months"]) == ["2026-11"] and t3["conf_arquivo"] == {}


def test_validar_pela_rota_o_conflito_e_a_importacao(furos):
    _dados(furos)
    u = "/t/performance/coletas/furos/r01/conf"
    r = furos.post(u, json={"ops": [{"k": K, "v": {"r": "sem_ipoa", "v": "*", "o": ""}, "base": ""}]})
    conf = r.get_json()["conf"]
    assert r.status_code == 200 and conf[K]["q"] and r.get_json()["conf_rev"] == 1
    assert furos.get(u + "?rev=1").get_json() == {"igual": True, "conf_rev": 1}
    velho = furos.post(u, json={"ops": [{"k": K, "v": None, "base": ""}]})
    assert velho.status_code == 409 and "Outra pessoa" in velho.get_json()["erro"] and velho.get_json()["conflito"] == [K]
    assert furos.post(u, json={"ops": [{"k": "x", "v": None}]}).status_code == 400
    assert furos.get("/t/performance/coletas/furos").get_json()["conf_arquivo"][K]["r"] == "sem_ipoa"
    # o JSON da analista: a validação mais nova do Nexus fica; a que só ela tem entra
    arq = {"versao": 1, "conf": {K: {"r": "outro", "v": "*", "o": "", "t": "2026-10-09T12:15:14.355Z"},
                                 "BD_Performance|U|GHI": {"r": "sem_ghi", "v": "*", "o": "", "t": "2026-10-09T12:15:14.355Z"}}}
    r = furos.post("/t/performance/coletas/furos/r01/importar", data={"arquivo": (io.BytesIO(json.dumps(arq).encode()), "confirmacoes_furos.json")})
    j = r.get_json()
    assert r.status_code == 200 and j["resumo"]["validacoes"]["novas"] == 1 and j["resumo"]["validacoes"]["mais_novas_no_nexus"] == 1
    assert j["conf"][K]["r"] == "sem_ipoa" and len(j["conf"]) == 2
    # o HTML R01: as marcações dele e as paradas de outubro
    html = ('<script>\nconst DB={"gen":"16/11/2026 11:13","months":{"2026-10":{"end":31,"plants":[{"src":"BD_Performance","usina":"U","os":'
            '[["F","900","UFV","Queda de energia","30/10 06:00","31/10 18:00",""]]}]}}};\nDB.conf=/*CONF0*/{}/*END0*/;\n</script>')
    r = furos.post("/t/performance/coletas/furos/r01/importar", data={"arquivo": (io.BytesIO(html.encode()), "Furos_R01.html")})
    assert r.get_json()["resumo"]["paradas"] == {"congelados": ["2026-10"], "mantidos": []} and len(r.get_json()["conf"]) == 2
    assert furos.post("/t/performance/coletas/furos/r01/importar", data={"arquivo": (io.BytesIO(b"nada"), "x.txt")}).status_code == 400
    assert _dados(furos)["fontes"]["congelado"]["2026-10"]["origem"] == "Furos_R01.html"


def test_a_tela_3_esconde_o_resumo_e_o_detalhe_e_aponta_para_a_aba(furos):
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    peca = open(os.path.join(raiz, "nexus", "static", "coletas", "filtros.js"), encoding="utf-8").read()
    assert '.fz-tab[data-t="res"], .fz-tab[data-t="det"]' in peca and '"/furos-de-coleta"' in peca and 'target="_top"' in peca
    js = open(os.path.join(raiz, "nexus", "static", "coletas-furos.js"), encoding="utf-8").read()
    # a validação é do servidor, não do navegador: o navegador só lembra se o bloco por cliente está recolhido (19/11/2026)
    assert "nexusPedir(CFG.conf" in js
    assert 'k = "nexus.furos.clientes.aberto"' in js and set(re.findall(r"localStorage\.\w+\(([^,)]*)", js)) == {"k"}
    assert "base: (base[k] || {}).t" in js                                    # cada mudança leva o `t` que a tela viu


def test_as_paradas_saem_das_mesmas_linhas_do_csv_do_cos(monkeypatch):
    """No servidor não há arquivo: as linhas são as do "Exportar CSV" da tela Ocorrências, montadas pela mesma função."""
    from nexus.cos import andamento as AND
    from nexus.cos import normalizacoes as NO
    from nexus.performance.coletas import furos_fonte as FF
    import nexus.torres.cos as TC
    agora = dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.timezone(dt.timedelta(hours=-3)))
    brutas = [
        {"registro": 1, "os": "100", "cliente": "Cliente X", "usina": "U", "usina_codigo": "CLI-U100", "normalizada": True,
         "equipamentos": [{"nome": "Cabine 1"}], "tipo_falha_rotulo": "Desligamento de cabine", "geracao_parou": True,
         "inicio": "2026-11-05T06:00:00-03:00", "normalizado_em": "2026-11-05T13:00:00-03:00"},
        {"registro": 2, "os": "101", "cliente": "Cliente X", "usina": "U", "usina_codigo": "CLI-U100", "normalizada": False,   # desfeita: fora
         "equipamentos": [], "tipo_falha_rotulo": "Desligamento de usina", "geracao_parou": True,
         "inicio": "2026-11-06T06:00:00-03:00", "normalizado_em": "2026-11-06T18:00:00-03:00"},
        {"registro": 3, "os": "102", "cliente": "Cliente X", "usina": "U", "usina_codigo": "CLI-U100", "normalizada": True,
         "equipamentos": [], "tipo_falha_rotulo": "Falha de comunicação", "geracao_parou": False,
         "inicio": "2026-11-02T00:00:00-03:00", "normalizado_em": "2026-11-02T23:00:00-03:00"}]
    aberta = {"registro": "9", "situacao": "andamento", "os": "", "fora": 100, "inicio": agora.replace(day=8, hour=6), "cliente": "Cliente X",
              "usina_codigo": "CLI-U100", "usina": "U", "falha": "Desligamento de usina", "equipamentos": [], "severidade": "ALTA", "operador": "",
              "tecnico": "", "fracttal": {"status": "", "pct": 0, "aberta": False}, "etapa": "aberta", "aguardando": "", "protecoes": [],
              "geracao": "sim", "acao": "", "descricao": "", "notas": []}
    monkeypatch.setattr(NO, "ler", lambda cfg, ag=None: AND.Leitura("", {"itens": brutas, "carregando": False}))
    monkeypatch.setattr(TC, "_andamento_cos", lambda cfg, ag: ([aberta, dict(aberta, registro="1")], [], []))     # a já normalizada não repete
    ls, aviso = FF.linhas_cos({}, agora)
    assert aviso == "" and [(x["OS"], x["Início"], x["Normalização"], x["Geração parou"]) for x in ls] == [
        ("", "08/11/2026 06:00", "", "sim (pelo tipo)"), ("100", "05/11/2026 06:00", "05/11/2026 13:00", "sim"),
        ("102", "02/11/2026 00:00", "02/11/2026 23:00", "não")]
    res = gerar([("U", CAB, linhas_u())], ls)
    assert [o[:3] + o[5:] for o in st(res)[0]["os"]] == [["C", "s/ nº", "UFV", "10/11 12:00 (aberta)", "A"], ["C", "100", "UG 1", "05/11 13:00", ""]]
    # sem o COS (o PC): a conta sai sem as paradas e diz por quê
    monkeypatch.setattr(NO, "ler", lambda cfg, ag=None: AND.Leitura("", None, erro="a fonte do Andamento não está ligada neste servidor"))
    assert FF.linhas_cos({}, agora) == (None, "a fonte do Andamento não está ligada neste servidor")

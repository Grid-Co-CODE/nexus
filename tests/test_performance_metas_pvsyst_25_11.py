# -*- coding: utf-8 -*-
"""Performance › Metas das usinas pelo PVsyst (protótipo de 25/11/2026).

Levi, 24/11/2026: "É por eles [os PVsyst] que a gente preenche as metas [...] a parte de balances and main results [...] é
onde a gente vai pegar o PR, a energia esperada [...] a ideia seria a gente anexar esses PVSys e já preencher automático na
meta". O relatório aqui é inventado (os números e o projeto), no formato do texto que o pypdf tira do PDF do PVsyst 7.3:
os rótulos do resumo em coluna, depois os números, depois as unidades; a tabela mensal em linhas."""
import io

import pytest

from nexus.performance import metas_pvsyst as M

MESES_EN = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November",
            "December")


def relatorio(unidade="kWh", p=("P50", "P70", "P90"), energia=(1000.0, 980.0, 960.0), meses=MESES_EN, fator=1.0):
    """Um relatório do PVsyst inventado: 12 meses de 100 kWh (ou 0,1 MWh) cada, PR 0,8, e o resumo com o P50 do ano."""
    e_mes = 100.0 * fator
    linhas = ["Version 7.3.1", "PVsyst - Simulation report", "Project: UFV Teste Solar II", "System power: 1000 kWp",
              "VC0, Simulation date:", "01/02/25 10:00", "Geographical Site", "Cidade Teste", "Main results", "System Production"]
    linhas += [f"Produced Energy ({x})" for x in p] + [f"{v * fator:g}" for v in energia] + [f"{unidade}/year"] * len(p)
    linhas += ["Specific production (P50)", "Produced Energy (P70)", "Produced Energy (P90)", "1000", "980", "960",
               "kWh/kWp/year", "kWh/kWp/year", "kWh/kWp/year", "Performance Ratio PR 80.00 %", "Balances and main results",
               "GlobHor DiffHor T_Amb GlobInc GlobEff EArray E_Grid PR",
               f"kWh/m² kWh/m² °C kWh/m² kWh/m² {unidade} {unidade} ratio"]
    for n, m in enumerate(meses, start=1):
        linhas.append(f"{m} {150 + n}.0 70.00 23.00 {190 + n}.0 180.0 {e_mes * 1.05:g} {e_mes:g} 0.800")
    linhas.append(f"Year 1900.0 840.00 23.00 2370.0 2160.0 {e_mes * 12 * 1.05:g} {e_mes * 12:g} 0.800")
    linhas += ["Legends", "GlobHor", "Global horizontal irradiation"]
    return "\n".join(linhas)


def test_le_o_resumo_e_a_tabela_mensal_com_a_energia_em_kwh():
    l = M.ler_texto(relatorio(energia=(1200.0, 1180.0, 1150.0)))
    assert (l["projeto"], l["versao"], l["kwp"], l["pr_ano"], l["simulado_em"]) == ("UFV Teste Solar II", "7.3.1", 1000.0,
                                                                                     0.8, "01/02/25")
    assert l["energia_ano_kwh"] == {"P50": 1200.0, "P70": 1180.0, "P90": 1150.0}
    assert [m["mes"] for m in l["meses"]] == list(range(1, 13)) and l["meses"][0]["E_Grid"] == 100.0
    assert l["meses"][0]["GlobInc"] == 191.0 and l["meses"][11]["GlobHor"] == 162.0
    assert all(c["ok"] for c in l["conferencias"])                          # 12 × 100 = 1200 = a linha do ano = o P50
    outro = M.ler_texto(relatorio(energia=(1300.0, 1280.0, 1250.0)))
    assert outro["conferencias"][0]["ok"] and not outro["conferencias"][1]["ok"]   # o P50 do resumo que não bate é dito


def test_o_relatorio_em_mwh_vira_kwh_e_a_conferencia_bate():
    """A Gravatá vem em MWh (552.8), a Iramaia II em kWh (594914): os dois saem em kWh."""
    l = M.ler_texto(relatorio(unidade="MWh", energia=(1200.0, 1180.0, 1150.0), fator=0.001))
    assert l["meses"][0]["E_Grid"] == pytest.approx(100.0) and l["energia_ano_kwh"]["P50"] == pytest.approx(1200.0)
    assert all(c["ok"] for c in l["conferencias"])


def test_a_meta_no_formato_da_info_mensal_p90_e_p75_pela_normal():
    """P50 = E_Grid em MWh; P90 = P50 × (P90 ÷ P50 do ano); P75 = P50 − (P50 − P90) × 0,6745 ÷ 1,2816 (a Info Mensal da
    Iramaia II de hoje segue essa conta: 578,84 / 555,96 / 566,81)."""
    meta = M.meta_do_pvsyst(M.ler_texto(relatorio(energia=(1200.0, 1180.0, 1080.0))))
    m = meta[0]
    assert (m["p50_mwh"], m["p90_mwh"], m["pr"], m["ipoa_kwh_m2"], m["ghi_kwh_m2"]) == (0.1, 0.09, 0.8, 191.0, 151.0)
    assert m["p75_mwh"] == round(0.1 - (0.1 - 0.09) * 0.6745 / 1.2816, 2)
    sem_p90 = M.meta_do_pvsyst(M.ler_texto(relatorio(p=("P50",), energia=(1200.0,))))
    assert sem_p90[0]["p90_mwh"] is None and sem_p90[0]["p75_mwh"] is None          # sem P90 no relatório, nada se inventa


def test_meses_em_portugues_tambem():
    l = M.ler_texto(relatorio(meses=("Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro",
                                     "Outubro", "Novembro", "Dezembro")))
    assert [m["mes"] for m in l["meses"]] == list(range(1, 13))


@pytest.mark.parametrize("texto, motivo", [
    ("um PDF qualquer, sem relatório", "não parece um relatório do PVsyst"),
    (relatorio().replace("Balances and main results", "Outra tabela"), "Balances and main results"),
    ("\n".join(l for l in relatorio().splitlines() if not l.startswith("December")), "11 mês(es)"),
])
def test_recusa_o_que_nao_e_relatorio_ou_vem_pela_metade(texto, motivo):
    with pytest.raises(M.NaoEhPvsyst, match=motivo.replace("(", r"\(").replace(")", r"\)")):
        M.ler_texto(texto)


def test_sugere_a_usina_pelo_projeto_e_nao_chuta():
    l = M.ler_texto(relatorio())
    assert M.sugerir_usina(l, "Anexo VI – PVSyst XX0001 UFV Teste Solar II.pdf", ["Teste Solar I", "Teste Solar II", "Outra"])[0] == "Teste Solar II"
    assert M.sugerir_usina(dict(l, projeto="Nada a ver"), "arquivo.pdf", ["Teste Solar II", "Outra"])[0] == ""


def test_a_meta_editavel_valida_os_12_meses_e_o_pr_em_porcento():
    """Levi, 25/11/2026: "deve ser possível [...] inserir todos os dados manualmente". O P50 é obrigatório; o PR digitado
    em % (80) vira fração; vazio fica vazio; negativo e texto são recusados."""
    linhas = [{"p50_mwh": 100 + n, "pr": 80 if n == 0 else 0.8, "ghi_kwh_m2": ""} for n in range(12)]
    m = M.validar_meta(linhas)
    assert (m[0]["mes"], m[0]["p50_mwh"], m[0]["pr"], m[1]["pr"], m[0]["ghi_kwh_m2"]) == (1, 100.0, 0.8, 0.8, None)
    assert M.meta_vazia()[11] == {"mes": 12, **{c: None for c in M.CAMPOS}}
    for ruim, motivo in ((linhas[:11], "12 meses"), ([dict(x, p50_mwh=None) for x in linhas], "falta o P50 do mês 1"),
                         ([dict(x, p90_mwh=-1) for x in linhas], "negativo"), ("texto", "12 meses")):
        with pytest.raises(ValueError, match=motivo):
            M.validar_meta(ruim)


def test_guardar_registra_cada_edicao_e_a_origem(tmp_path):
    """Cada Salvar fica no registro: quem, de onde, e cada valor de quanto para quanto. A origem é "PVsyst" enquanto a
    meta é a do PDF, "PVsyst editado" quando se mexeu nela, "manual" sem PDF."""
    l = M.ler_texto(relatorio())
    sha = M.guardar_pdf(tmp_path, b"%PDF-1.4 teste")
    assert M.ler_pdf_guardado(tmp_path, sha) == b"%PDF-1.4 teste" and M.ler_pdf_guardado(tmp_path, "../x") is None
    pv = M.meta_do_pvsyst(l)
    r = M.guardar(tmp_path, "Teste Solar II", 2027, pv, "Analista", sha=sha, nome_arquivo="a.pdf", lido=l)
    assert r["origem"] == "PVsyst" and r["edicoes"][0]["mudancas"] == [] and r["arquivo"] == "a.pdf"
    editada = [dict(x) for x in pv]
    editada[0]["p50_mwh"] = 0.2
    r = M.guardar(tmp_path, "Teste Solar II", 2027, editada, "Analista", sha=sha)      # o mesmo PDF, sem reler
    assert r["origem"] == "PVsyst editado" and len(r["edicoes"]) == 2
    assert r["edicoes"][1]["mudancas"] == [{"mes": 1, "campo": "p50_mwh", "de": 0.1, "para": 0.2}]
    assert M.descrever({"mes": 3, "campo": "p50_mwh", "de": 576.23, "para": 1700.5}) == "mar · P50 576,2 → 1.700,5"
    assert M.descrever({"mes": 1, "campo": "pr", "de": 0.727, "para": None}) == "jan · PR 72,7% → vazio"
    manual = M.validar_meta([{"p50_mwh": 50} for _ in range(12)])
    r = M.guardar(tmp_path, "Outra", 2027, manual, "Analista")
    assert r["origem"] == "manual" and "sha" not in r and len(r["edicoes"][0]["mudancas"]) == 12
    assert sorted(M.salvas(tmp_path)) == ["Outra", "Teste Solar II"]


def test_a_meta_de_hoje_da_info_mensal_para_comparar():
    """É a meta que está na aba Info Mensal (meta, não o realizado); o PR em % vira fração como o do PVsyst."""
    hoje = {"2027-01": {"P50 (MWh)": 0.12, "P90": 0.1, "PR Previsto 1° Ano (%)": 0.82, "IPOA Previsto": 190,
                        "GHI Previsto": 150},
            "2027-02": {"P50 (MWh)": "0,11", "PR Previsto 1° Ano (%)": 81.5}}
    c = M.meta_de_hoje(hoje, 2027)
    assert c[0] == {"mes": 1, "p50_mwh": 0.12, "p90_mwh": 0.1, "p75_mwh": None, "pr": 0.82, "ipoa_kwh_m2": 190.0,
                    "ghi_kwh_m2": 150.0}
    assert c[1]["p50_mwh"] == 0.11 and c[1]["pr"] == pytest.approx(0.815) and c[2]["p50_mwh"] is None
    assert len(c) == 12


def test_a_tela_le_o_pdf_edita_e_salva_na_pasta_de_dados(app, logado, tmp_path, monkeypatch):
    """O caminho da tela sem banco (a meta de hoje fica vazia, com o erro) e com o texto do PDF dublado."""
    app.config["NEXUS_DADOS"] = str(tmp_path)
    monkeypatch.setattr(M, "texto_do_pdf", lambda dados: relatorio())
    h = {"Sec-Fetch-Site": "same-origin"}
    assert "Metas das usinas" in logado.get("/t/performance/metas").get_data(as_text=True)
    j = logado.post("/t/performance/metas/ler", data={"arquivo": (io.BytesIO(b"%PDF-1.4 x"), "teste.pdf")},
                    content_type="multipart/form-data", headers=h).get_json()
    assert j["ok"] and j["lido"]["projeto"] == "UFV Teste Solar II" and len(j["meta"]) == 12 and j["erro_meta"]
    assert j["origem"] == "PVsyst" and len(j["hoje"]) == 12
    nao = logado.post("/t/performance/metas/ler", data={"arquivo": (io.BytesIO(b"texto"), "teste.txt")},
                      content_type="multipart/form-data", headers=h).get_json()
    assert not nao["ok"] and "não é um PDF" in nao["erro"]
    # sem a meta de hoje no banco, não há usina para escolher: o Salvar recusa
    r = logado.post("/t/performance/metas/salvar", json={"sha": j["sha"], "usina": "Teste Solar II", "ano": 2027,
                                                         "meta": j["meta"]}, headers=h)
    assert r.status_code == 400
    monkeypatch.setattr(M, "meta_atual", lambda base, sessao: {"mensal": {"Teste Solar II": {}}, "geral": {},
                                                                "usinas": ["Teste Solar II"], "clientes": {}, "erro": ""})
    from nexus.torres.performance import metas_tela
    monkeypatch.setattr(metas_tela, "banco", lambda: ("http://pg.falso", None))
    # sem a meta (ou com 11 meses) não salva
    assert logado.post("/t/performance/metas/salvar", json={"usina": "Teste Solar II", "ano": 2027}, headers=h).status_code == 400
    editada = [dict(x) for x in j["meta"]]
    editada[2]["pr"] = 75          # o PR digitado em %
    r = logado.post("/t/performance/metas/salvar", json={"sha": j["sha"], "usina": "Teste Solar II", "ano": 2027,
                                                         "arquivo": "teste.pdf", "meta": editada}, headers=h).get_json()
    assert r["ok"] and r["salvo"]["origem"] == "PVsyst editado" and "1 valor mudado" in r["aviso"]
    assert M.salvas(tmp_path)["Teste Solar II"]["meta"][2]["pr"] == 0.75
    # abrir de novo traz a meta salva para editar; uma usina sem meta abre em branco (à mão)
    a = logado.post("/t/performance/metas/abrir", json={"usina": "Teste Solar II"}, headers=h).get_json()
    assert a["ok"] and a["meta"][2]["pr"] == 0.75 and a["sha"] == j["sha"] and a["edicoes"] == 1 and a["ano"] == 2027
    b = logado.post("/t/performance/metas/abrir", json={"usina": "Outra"}, headers=h).get_json()
    assert b["origem"] == "manual" and b["meta"][0]["p50_mwh"] is None
    assert logado.post("/t/performance/metas/hoje", json={"usina": "Teste Solar II", "ano": 2026}, headers=h).get_json()["ano"] == 2026
    assert logado.get(f"/t/performance/metas/pdf/{j['sha']}").data == b"%PDF-1.4 x"
    assert "Abrir" in logado.get("/t/performance/metas").get_data(as_text=True)
    # pedido de outro site não lê nem salva
    assert logado.post("/t/performance/metas/ler", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert logado.post("/t/performance/metas/salvar", json={}, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403

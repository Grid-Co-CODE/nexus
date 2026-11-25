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
    meta é a do PDF, "PVsyst editado" quando se mexeu nela, "Info Mensal" salva sem mexer, "manual" no resto. A chave é
    a usina do Registro mestre (o id) e o ano."""
    l = M.ler_texto(relatorio())
    sha = M.guardar_pdf(tmp_path, b"%PDF-1.4 teste")
    assert M.ler_pdf_guardado(tmp_path, sha) == b"%PDF-1.4 teste" and M.ler_pdf_guardado(tmp_path, "../x") is None
    pv = M.meta_do_pvsyst(l)
    r = M.guardar(tmp_path, "7", "Teste Solar II", 2027, pv, "Analista", sha=sha, nome_arquivo="a.pdf", lido=l)
    assert r["origem"] == "PVsyst" and r["edicoes"][0]["mudancas"] == [] and r["arquivo"] == "a.pdf"
    editada = [dict(x) for x in pv]
    editada[0]["p50_mwh"] = 0.2
    r = M.guardar(tmp_path, "7", "Teste Solar II", 2027, editada, "Analista", sha=sha)      # o mesmo PDF, sem reler
    assert r["origem"] == "PVsyst editado" and len(r["edicoes"]) == 2
    assert r["edicoes"][1]["mudancas"] == [{"mes": 1, "campo": "p50_mwh", "de": 0.1, "para": 0.2}]
    assert M.descrever({"mes": 3, "campo": "p50_mwh", "de": 576.23, "para": 1700.5}) == "mar · P50 576,2 → 1.700,5"
    assert M.descrever({"mes": 1, "campo": "pr", "de": 0.727, "para": None}) == "jan · PR 72,7% → vazio"
    info = M.validar_meta([{"p50_mwh": 50, "pr": 0.8} for _ in range(12)])
    r = M.guardar(tmp_path, "8", "Outra", 2027, info, "Analista", antes=info)           # a da Info Mensal, sem mexer
    assert r["origem"] == "Info Mensal" and r["edicoes"][0]["mudancas"] == [] and "sha" not in r
    outra = [dict(x) for x in info]
    outra[5]["pr"] = 0.81
    r = M.guardar(tmp_path, "8", "Outra", 2026, outra, "Analista", antes=info)          # outro ano: outra meta
    assert r["origem"] == "manual" and r["edicoes"][0]["mudancas"] == [{"mes": 6, "campo": "pr", "de": 0.8, "para": 0.81}]
    assert sorted(M.salvas(tmp_path)) == ["7|2027", "8|2026", "8|2027"]


def test_o_formato_de_antes_continua_lido(tmp_path):
    """As poucas horas do 1º formato (por nome, sem o id): a meta aparece na lista e não se perde no próximo Salvar."""
    import json
    pasta = tmp_path / "metas_pvsyst"
    pasta.mkdir()
    (pasta / "metas.json").write_text(json.dumps({"Iramaia II": {"usina": "Iramaia II", "ano": 2027, "meta": []}}),
                                      encoding="utf-8")
    assert M.salvas(tmp_path)["Iramaia II|2027"]["usina_id"] == ""
    M.guardar(tmp_path, "9", "Nova", 2027, M.validar_meta([{"p50_mwh": 1} for _ in range(12)]), "Analista")
    assert sorted(M.salvas(tmp_path)) == ["9|2027", "Iramaia II|2027"]


def test_a_meta_de_hoje_da_info_mensal_e_o_casamento_com_o_registro_mestre():
    """É a meta que está na aba Info Mensal (meta, não o realizado); o PR em % vira fração como o do PVsyst. A usina do
    Registro mestre acha a linha dela pelo nome (romano = número) ou pelo nome dela em Base > Equipamentos."""
    hoje = {"2027-01": {"P50 (MWh)": 0.12, "P90": 0.1, "PR Previsto 1° Ano (%)": 0.82, "IPOA Previsto": 190,
                        "GHI Previsto": 150},
            "2027-02": {"P50 (MWh)": "0,11", "PR Previsto 1° Ano (%)": 81.5}}
    c = M.meta_de_hoje(hoje, 2027)
    assert c[0] == {"mes": 1, "p50_mwh": 0.12, "p90_mwh": 0.1, "p75_mwh": None, "pr": 0.82, "ipoa_kwh_m2": 190.0,
                    "ghi_kwh_m2": 150.0}
    assert c[1]["p50_mwh"] == 0.11 and c[1]["pr"] == pytest.approx(0.815) and c[2]["p50_mwh"] is None
    assert len(c) == 12
    mensal = {"Gravatá II": {}, "Ibirapuã I": {}, "MTS100": {}, "Sete Lagoas": {}}
    assert M.linha_da_info_mensal("Gravata 2", None, mensal) == "Gravatá II"
    assert M.linha_da_info_mensal("Ibirapuã 1", {"Ibirapuã I"}, mensal) == "Ibirapuã I"
    assert M.linha_da_info_mensal("Matões 100", {"MTS100"}, mensal) == "MTS100"
    assert M.linha_da_info_mensal("Matões 100", {"MTS100", "Sete Lagoas"}, mensal) == ""      # duas: não escolhe
    assert M.linha_da_info_mensal("Sem Meta", None, mensal) == ""


# ── a tela, na Base, com o Registro mestre e a Info Mensal de mentira ───────────────────────────────────────────────
INFO = [{"Usina": "Teste Solar II", "Cliente": "Aurora", "Mês": f"2027-{m:02d}-01", "P50 (MWh)": 0.12, "P90": 0.1,
         "P75": 0.11, "PR Previsto 1° Ano (%)": 0.82, "IPOA Previsto": 190, "GHI Previsto": 150} for m in range(1, 13)]
H = {"Sec-Fetch-Site": "same-origin"}


@pytest.fixture
def cli_metas(tmp_path, monkeypatch):
    from pg_falso import ApiPGFalsa
    from test_campo_visao import _aba
    from conftest import SENHA_TESTE
    from nexus import create_app
    from nexus.cadastro.cifra import gerar_chave
    from nexus.cadastro.servico import Carga
    M._CACHE.clear()
    api = ApiPGFalsa()
    _aba(api, "bd_performance", "Info Mensal", INFO)
    app = create_app({"NEXUS_SECRET_KEY": "chave-de-teste", "NEXUS_SENHA_ADMIN": SENHA_TESTE,
                      "NEXUS_CHAVE_CADASTRO": gerar_chave(), "NEXUS_ARMAZEM_LOCAL": str(tmp_path / "cadastro.json"),
                      "NEXUS_DADOS": str(tmp_path / "dados")})
    app.config.update({"TESTING": True, "SESSION_COOKIE_SECURE": False, "GRIDCO_DB_API": "http://pg.falso",
                       "GRIDCO_SQL_TOKEN": "token-de-teste"})
    app.extensions["nexus_dados_sessao"] = api
    monkeypatch.setattr(M, "texto_do_pdf", lambda dados: relatorio())
    from nexus.cadastro.telas import servico
    with app.app_context():
        servico().aplicar_carga(Carga(
            entidades={
                "clientes": [{"id": "1", "ordem": 1, "valores": {"nome": "Thopen"}},
                             {"id": "2", "ordem": 2, "valores": {"nome": "Aurora"}}],
                "usinas": [
                    {"id": "1", "ordem": 1, "valores": {"nome": "Da Thopen", "cliente": "1", "status": "OPERAÇÃO"}},
                    {"id": "2", "ordem": 2, "valores": {"nome": "Teste Solar 2", "cliente": "2", "status": "OPERAÇÃO",
                                                         "potencia_real": 1.0}},
                    {"id": "3", "ordem": 3, "valores": {"nome": "Sem Meta", "cliente": "2", "status": "A MOBILIZAR"}},
                ]},
            listas={"status_usina": ["OPERAÇÃO", "A MOBILIZAR"]}))
    c = app.test_client()
    assert c.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    yield c
    M._CACHE.clear()


def test_a_tela_mora_na_base_com_as_usinas_do_registro_mestre(cli_metas):
    """Levi, 25/11/2026: "metas das usinas tem que estar na parte de base"; "essas usinas [...] são de acordo com o
    registro mestre". A Thopen fica fora (manda a própria meta); o endereço da Performance leva à Base."""
    c = cli_metas
    html = c.get("/t/base/metas").get_data(as_text=True)
    assert "Metas das usinas" in html and 'list="mt-lista-usinas"' in html          # a usina se digita
    assert 'value="Teste Solar 2"' in html and 'value="Sem Meta"' in html and "Da Thopen" not in html
    r = c.get("/t/performance/metas?x=1")
    assert r.status_code == 308 and r.headers["Location"].endswith("/t/base/metas?x=1")
    assert c.post("/t/performance/metas/salvar", json={}, headers=H).status_code == 308


def test_abrir_traz_a_meta_da_info_mensal_e_salvar_registra(cli_metas):
    c = cli_metas
    a = c.post("/t/base/metas/abrir", json={"usina_id": "2", "ano": 2027}, headers=H).get_json()
    assert a["ok"] and a["de_onde"] == "info_mensal" and a["linha_info"] == "Teste Solar II" and a["kwp"] == 1000.0
    assert a["atual"][0]["p50_mwh"] == 0.12 and a["atual"][0]["pr"] == 0.82 and 2027 in a["anos"]
    vazia = c.post("/t/base/metas/abrir", json={"usina_id": "3"}, headers=H).get_json()
    assert vazia["de_onde"] == "" and vazia["atual"][0]["p50_mwh"] is None
    assert c.post("/t/base/metas/abrir", json={"usina_id": "1"}, headers=H).status_code == 400     # a da Thopen não
    # editar um PR (em %) e salvar: o registro compara com a Info Mensal que a tela mostrava
    meta = [dict(x) for x in a["atual"]]
    meta[2]["pr"] = 75
    r = c.post("/t/base/metas/salvar", json={"usina_id": "2", "ano": 2027, "meta": meta}, headers=H).get_json()
    assert r["ok"] and r["salvo"]["origem"] == "manual" and "1 valor mudado" in r["aviso"]
    assert r["salvo"]["edicoes"][0]["mudancas"] == [{"mes": 3, "campo": "pr", "de": 0.82, "para": 0.75}]
    b = c.post("/t/base/metas/abrir", json={"usina_id": "2", "ano": 2027}, headers=H).get_json()
    assert b["de_onde"] == "nexus" and b["atual"][2]["pr"] == 0.75 and b["salva"]["edicoes"] == 1
    assert c.post("/t/base/metas/salvar", json={"usina_id": "2", "ano": 2027}, headers=H).status_code == 400
    assert c.post("/t/base/metas/salvar", json={"usina_id": "9", "ano": 2027, "meta": meta}, headers=H).status_code == 400
    html = c.get("/t/base/metas").get_data(as_text=True)
    assert 'data-abrir="2"' in html and "mar · PR 82,0% → 75,0%" in html
    assert c.post("/t/base/metas/salvar", json={}, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_o_pvsyst_acha_a_usina_e_vem_para_editar(cli_metas, monkeypatch):
    c = cli_metas
    j = c.post("/t/base/metas/ler", data={"arquivo": (io.BytesIO(b"%PDF-1.4 x"), "Anexo VI - PVSyst UFV Teste Solar II.pdf")},
               content_type="multipart/form-data", headers=H).get_json()
    assert j["ok"] and j["usina_id"] == "2" and j["pvsyst"]["lido"]["projeto"] == "UFV Teste Solar II"
    assert len(j["pvsyst"]["meta"]) == 12 and j["atual"][0]["p50_mwh"] == 0.12          # a de agora, para marcar o que muda
    # o projeto claro vence a usina que estava aberta; sem projeto que case, fica a aberta
    k = c.post("/t/base/metas/ler", data={"arquivo": (io.BytesIO(b"%PDF-1.4 x"), "x.pdf"), "usina_id": "3"},
               content_type="multipart/form-data", headers=H).get_json()
    assert k["usina_id"] == "2"
    monkeypatch.setattr(M, "texto_do_pdf", lambda dados: relatorio().replace("UFV Teste Solar II", "Projeto Qualquer"))
    k = c.post("/t/base/metas/ler", data={"arquivo": (io.BytesIO(b"%PDF-1.4 x"), "x.pdf"), "usina_id": "3"},
               content_type="multipart/form-data", headers=H).get_json()
    assert k["usina_id"] == "3"
    monkeypatch.setattr(M, "texto_do_pdf", lambda dados: relatorio())
    nao = c.post("/t/base/metas/ler", data={"arquivo": (io.BytesIO(b"texto"), "teste.txt")},
                 content_type="multipart/form-data", headers=H).get_json()
    assert not nao["ok"] and "não é um PDF" in nao["erro"]
    r = c.post("/t/base/metas/salvar", json={"usina_id": "2", "ano": 2027, "meta": j["pvsyst"]["meta"],
                                             "sha": j["pvsyst"]["sha"], "arquivo": "a.pdf"}, headers=H).get_json()
    assert r["ok"] and r["salvo"]["origem"] == "PVsyst" and r["salvo"]["projeto"] == "UFV Teste Solar II"
    assert len(r["salvo"]["edicoes"][0]["mudancas"]) > 0                     # contra a Info Mensal que estava
    assert c.get(f"/t/base/metas/pdf/{j['pvsyst']['sha']}").data == b"%PDF-1.4 x"
    assert c.post("/t/base/metas/ler", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403

"""A planilha de controle de obrigações na Visão do contrato (16/11/2026). Retorno do supervisor de contratos na prévia:
"Só não encontrei algum setor que fale sobre renovação contratual e/ou ajuste contratual de 12 meses. Essas datas são
importantes para a gestão de contratos"; Levi: "ATUALIZE AGORA COM DADOS REAIS!".

A planilha daqui é inventada (o repositório é público): mesmas abas e colunas da de verdade, clientes e pessoas fictícios."""
import io
from datetime import date, datetime

import openpyxl

from nexus.contratos import controle as K

HOJE = date(2026, 11, 16)
CAB_CARTEIRA = ["Carteira\n(auto)", "Cliente", "Supervisor de Contratos", "Recorte", "Nº / referência\ndo contrato",
                "Início da\nvigência", "Fim da\nvigência", "Data-base\ndo reajuste", "Índice de\nreajuste",
                "Aviso prévio de\nrenovação (dias)", "SLA de atendimento\n(resumo)", "Resumo do contrato\n(E-CTR-05)",
                "Pasta do contrato\n(link)", "Observações", "Usinas no Fracttal\n(auto)", "Dias até fim\nda vigência",
                "Próximo\nreajuste", "Dias até\no reajuste", "Alerta\n(auto)"]
CAB_CAL = ["Carteira *", "Cliente\n(auto)", "Recorte\n(auto)", "Supervisor\n(auto)", "Tipo de obrigação *", "Descrição *",
           "Cláusula / origem", "Periodicidade", "Vencimento *", "Alerta com\nantecedência (dias)", "Executor", "Status *",
           "Data de\nentrega", "Evidência (link)", "Observações", "Dias até\nvencer"]


def _planilha() -> bytes:
    wb = openpyxl.Workbook()
    wb.active.title = "LEIA-ME"
    ws = wb.create_sheet("Carteira")
    for _ in range(4):
        ws.append(["texto de cima"])
    ws.append(CAB_CARTEIRA)
    d = datetime
    ws.append(["Solar Alfa | Norte", "Solar Alfa", "Pessoa Um", "Norte", "Contrato padrão por usina", d(2025, 2, 25),
               d(2026, 8, 25), d(2025, 2, 25), "IPCA", 90, "Corretiva em até 6 h", "Pendente",
               "https://exemplo.sharepoint.com/sites/X/contrato", "Vigência vencida no papel", 2, -77, None, None, "x"])
    ws.append(["Solar Alfa | Sul", "Solar Alfa", "Pessoa Dois", "Sul", None, None, None, None, None, None, None, None,
               None, None, 1, None, None, None, "x"])
    ws.append(["Solar Alfa | Contrato (nível geral)", "Solar Alfa", "Pessoa Três", "Contrato (nível geral)",
               "Contrato padrão por usina", d(2025, 2, 25), d(2026, 8, 25), d(2025, 2, 25), "IPCA", 90, None, None,
               None, None, 3, None, None, None, "VIGÊNCIA VENCIDA"])
    ws.append(["Beta GD | Todas", "Beta GD", "Pessoa Um", "Todas", "Contrato 01/2026", d(2026, 6, 23), d(2027, 6, 23),
               None, "IPCA só se passar de 12 meses", None, None, None, "javascript:alert(1)", None, 0, None, None, None, "OK"])
    ws.append(["Gama | Todas", "Gama", "Pessoa Quatro", "Todas", "[CONTRATO NÃO LOCALIZADO — pasta vazia]", None, None,
               None, None, None, None, None, None, None, 0, None, None, None, "x"])
    wc = wb.create_sheet("Calendario")
    for _ in range(3):
        wc.append(["texto de cima"])
    wc.append(CAB_CAL)
    wc.append(["Solar Alfa | Norte", "Solar Alfa", "Norte", "Pessoa Um", "Entregável", "RMO de setembro — EXEMPLO", None,
               "Mensal", d(2026, 10, 10), 5, "Performance", "Em andamento"])
    wc.append(["Solar Alfa | Contrato (nível geral)", "Solar Alfa", "Contrato (nível geral)", "Pessoa Três",
               "Medição / faturamento (BM)", "BM 20 (competência out/26)", None, "Mensal", d(2026, 10, 25), None,
               "Coordenador", "Não iniciado"])
    wc.append(["Solar Alfa | Norte", "Solar Alfa", "Norte", "Pessoa Um", "Reajuste", "Reajuste anual pelo IPCA", "14.1",
               "Anual", d(2026, 11, 20), 30, "Supervisor de Contratos", "Não iniciado"])
    wc.append(["Beta GD | Todas", "Beta GD", "Todas", "Pessoa Um", "Reunião periódica com cliente", "Reunião mensal", None,
               "Mensal", d(2026, 12, 20), 5, "Supervisor de Contratos", "Não iniciado"])
    wc.append(["Beta GD | Todas", "Beta GD", "Todas", "Pessoa Um", "Reunião periódica com cliente", "Reunião de outubro",
               None, "Mensal", d(2026, 10, 20), 5, "Supervisor de Contratos", "Entregue", d(2026, 10, 20)])
    wu = wb.create_sheet("Usinas")
    for _ in range(3):
        wu.append(["texto de cima"])
    wu.append(["Código Fracttal", "Cliente", "Usina", "UF", "Recorte\n(auto)", "Carteira\n(auto)", "Supervisor\n(auto)"])
    wu.append(["SA-ZZ100", "Solar Alfa", "Zeta 1", "PA", "Norte", "", ""])
    wu.append(["SA-AA100", "Solar Alfa", "Alfa 1", "PA", "Norte", "", ""])
    wu.append(["SA-SS100", "Solar Alfa", "Sul 1", "PR", "Sul", "", ""])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def test_le_a_carteira_juntando_o_contrato_de_cada_cliente():
    d = K.ler_planilha(_planilha(), "controle.xlsx")
    por = {c["cliente"]: c for c in d["contratos"]}
    assert list(por) == ["Beta GD", "Gama", "Solar Alfa"]
    a = por["Solar Alfa"]
    # o gestor é o supervisor da linha "Contrato (nível geral)"; as carteiras, as outras, com as usinas de cada recorte
    assert a["gestor"] == "Pessoa Três"
    assert a["recortes"] == [{"recorte": "Norte", "supervisor": "Pessoa Um", "usinas": 2},
                             {"recorte": "Sul", "supervisor": "Pessoa Dois", "usinas": 1}]
    assert (a["inicio"], a["fim"], a["data_base"], a["indice"], a["aviso_dias"]) == ("2025-02-25", "2026-08-25", "2025-02-25", "IPCA", 90)
    assert a["sla"] == "Corretiva em até 6 h"                     # o campo vazio na linha geral vem da outra linha
    assert [u["usina"] for u in a["usinas"]] == ["Alfa 1", "Sul 1", "Zeta 1"]
    assert por["Beta GD"]["gestor"] == "Pessoa Um" and por["Beta GD"]["recortes"] == []
    assert por["Gama"]["nao_localizado"] and por["Gama"]["fim"] is None
    # a linha de exemplo da planilha ("— EXEMPLO") não entra
    assert [o["descricao"] for o in d["obrigacoes"]] == ["Reunião de outubro", "BM 20 (competência out/26)",
                                                        "Reajuste anual pelo IPCA", "Reunião mensal"]


def test_a_planilha_errada_e_recusada():
    for ruim in (b"isto nao e xlsx",):
        try:
            K.ler_planilha(ruim)
            raise AssertionError("aceitou")
        except K.PlanilhaInvalida as ex:
            assert "xlsx" in str(ex)
    wb = openpyxl.Workbook()
    out = io.BytesIO()
    wb.save(out)
    try:
        K.ler_planilha(out.getvalue())
        raise AssertionError("aceitou")
    except K.PlanilhaInvalida as ex:
        assert "Carteira" in str(ex)


def test_o_proximo_reajuste_e_o_aniversario_da_data_base_que_ainda_vem():
    assert K.proximo_reajuste(date(2025, 2, 25), HOJE) == date(2027, 2, 25)
    assert K.proximo_reajuste(date(2025, 12, 1), HOJE) == date(2026, 12, 1)
    assert K.proximo_reajuste(date(2025, 11, 16), HOJE) == date(2026, 11, 16)        # hoje conta
    assert K.proximo_reajuste(date(2026, 9, 8), HOJE) == date(2027, 9, 8)            # só depois de 12 meses
    assert K.proximo_reajuste(date(2024, 2, 29), HOJE) == date(2027, 2, 28)          # o 29/02 vira 28/02
    assert K.proximo_reajuste(None, HOJE) is None


def test_as_datas_de_renovacao_e_reajuste_e_o_que_esta_em_atraso():
    d = K.com_datas(K.ler_planilha(_planilha()), HOJE)
    por = {c["cliente"]: c for c in d["contratos"]}
    a = por["Solar Alfa"]
    # renovação: avisar até o fim menos o aviso prévio (90 dias antes de 25/08/2026)
    assert (a["avisar_ate"], a["dias_fim"], a["proximo_reajuste"], a["dias_reajuste"]) == ("2026-05-27", -83, "2027-02-25", 101)
    assert a["criticos"] == ["vigência vencida há 83 dias", "1 obrigação em atraso"] and a["atrasadas"] == 1
    b = por["Beta GD"]
    assert b["avisar_ate"] is None and b["proximo_reajuste"] is None and b["proxima_data"] == "2027-06-23"
    tons = {o["descricao"]: o["tom"] for o in d["obrigacoes"]}
    assert tons == {"BM 20 (competência out/26)": "critico", "Reajuste anual pelo IPCA": "alerta",
                    "Reunião mensal": "neutro", "Reunião de outubro": "ok"}
    assert d["hoje"] == "2026-11-16"


def test_importar_e_ler_pela_tela(logado, tmp_path):
    logado.application.config.update(NEXUS_DADOS=str(tmp_path))
    assert logado.get("/t/comando/visao-do-contrato/dados.json").get_json() == {"ok": False}
    html = logado.get("/t/comando/visao-do-contrato").get_data(as_text=True)
    assert "fictícios" in html and 'name="planilha"' in html
    # a planilha errada não importa e não apaga nada
    r = logado.post("/t/comando/visao-do-contrato/importar", data={"planilha": (io.BytesIO(b"x"), "x.xlsx")},
                    content_type="multipart/form-data")
    assert r.status_code == 302 and "Não importei" in logado.get("/t/comando/visao-do-contrato").get_data(as_text=True)
    r = logado.post("/t/comando/visao-do-contrato/importar", data={"planilha": (io.BytesIO(_planilha()), "controle.xlsx")},
                    content_type="multipart/form-data")
    assert r.status_code == 302
    html = logado.get("/t/comando/visao-do-contrato").get_data(as_text=True)
    assert "Planilha importada: 3 contratos e 4 obrigações" in html and "Dados <b>reais</b>" in html
    assert (tmp_path / "contratos" / K.ARQUIVO).exists()
    j = logado.get("/t/comando/visao-do-contrato/dados.json").get_json()
    assert j["ok"] and [c["cliente"] for c in j["contratos"]] == ["Beta GD", "Gama", "Solar Alfa"]
    assert j["contratos"][2]["avisar_ate"] == "2026-05-27" and j["arquivo"] == "controle.xlsx"


def test_so_o_administrador_importa_e_o_cliente_nao_le(logado, tmp_path):
    logado.application.config.update(NEXUS_DADOS=str(tmp_path))
    with logado.session_transaction() as s:
        s["admin"] = False
    r = logado.post("/t/comando/visao-do-contrato/importar", data={"planilha": (io.BytesIO(_planilha()), "c.xlsx")},
                    content_type="multipart/form-data")
    assert r.status_code == 403 and not (tmp_path / "contratos").exists()
    assert 'name="planilha"' not in logado.get("/t/comando/visao-do-contrato").get_data(as_text=True)
    with logado.session_transaction() as s:
        s["via"] = "cliente"
    assert logado.get("/t/comando/visao-do-contrato/dados.json").status_code in (302, 403)


def test_a_pagina_le_os_dados_do_nexus_e_nao_guarda_nenhum(cliente):
    """O repositório é público: a página não tem dado de contrato; pede ao Nexus e, sem resposta, fica no exemplo."""
    r = cliente.get("/static/previa/visao-do-contrato.html")
    p = r.get_data(as_text=True)
    r.close()
    assert '"../../t/comando/visao-do-contrato/dados.json"' in p and "function vTodos()" in p
    assert "Renovação: avisar até" in p and "Próximo reajuste" in p
    assert "Sem dado real ainda" in p
    # o link da pasta só abre se for do SharePoint (a planilha é texto livre)
    assert r"/^https:\/\/[a-z0-9.-]+\.sharepoint\.com\//i" in p

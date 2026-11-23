"""Comando > Contratos, 19/11/2026: a etiqueta curta da cláusula, os pontos de atenção e de divergência do contrato e o
setor de cada regra.

O pedido: "a parte por setor (oq performance atende, o que zeladoria etc)" e "ponto de atenção e pontos de divergência
do contrato" (o "Pontos a resolver" do Radar da Zeladoria). Levi, no mesmo dia: "uma tagzinha [...] da cláusula do
contrato [...] uma forma mais resumida"; "ordenar por setor [...] e aí botar uma linha grossa"; vencendo = 60 dias;
resolver um ponto pede motivo e prova.

Tudo inventado (o repositório é público): os clientes, as datas, as cláusulas e os textos."""
from datetime import date

import pytest

from nexus.contratos import fichas as F
from nexus.contratos import pontos as P
from test_contratos_editavel_18_11 import _como, _editar, carga  # noqa: F401 — a fixture da carga inicial

HOJE = date(2026, 11, 19)


@pytest.mark.parametrize("ref, curta", [
    ("Anexo II (Proposta Técnica), 4.7.2", "Anx II · 4.7.2"),
    ("Anexo A (Proposta Técnica), item 4.11", "Anx A · 4.11"),
    ("Anexo IV, Seção C.4.2", "Anx IV · C.4.2"),
    ("Anexo IV (PSLA REV01 de 06/03/2026), MCEI.12", "Anx IV · MCEI.12"),
    ("Cláusula Vigésima Primeira, iii", "Cl. 21 · iii"),
    ("Cláusula 10.6", "Cl. 10.6"),
    ("9 (c)", "Cl. 9 (c)"),
    ("2.12.1 (Relatório Mensal)", "Cl. 2.12.1"),
    ("Condições Específicas, 3.1", "CE · 3.1"),
    ("Plano Central de Manutenção (rev. 01, jan/2026), 2.15", "Plano Central · 2.15"),
    ("", ""),
])
def test_a_etiqueta_curta_da_clausula(ref, curta):
    assert F.clausula_curta(ref) == curta
    assert len(F.clausula_curta(ref)) <= 22


def _c(cliente="Solar Alfa", **k):
    return {"cliente": cliente, "fim": None, "dias_fim": None, "avisar_ate": None, "dias_aviso": None, **k}


def _ficha(**k):
    return {"cliente": "Solar Alfa", "documentos": [], "contratos": [{"_id": "k1", "id": "ALFA-1", "regras": [], **k}]}


def _ids(r, cli="Solar Alfa"):
    return [p["id"].split(":")[0] + ":" + p["id"].split(":")[1] for p in r["por_cliente"][cli]]


def test_as_contas_vigencia_em_60_dias_renovacao_minuta_e_sem_pdf():
    ficha = _ficha()
    # vence em 21 dias: atenção; o aviso já passou: atenção
    r = P.todos([_c(fim="2026-12-10", dias_fim=21, avisar_ate="2026-11-10", dias_aviso=-9, aviso_dias=30)], {"Solar Alfa": ficha},
                [], {}, {}, HOJE)
    assert _ids(r) == ["c:vigencia", "c:renovacao"]
    assert "10/12/2026" in r["por_cliente"]["Solar Alfa"][0]["texto"]
    # 61 dias: ainda não é "vencendo" (o Levi escolheu 60); o aviso também longe
    r = P.todos([_c(fim="2027-01-19", dias_fim=61, avisar_ate="2027-01-01", dias_aviso=43, aviso_dias=18)], {"Solar Alfa": ficha},
                [], {}, {}, HOJE)
    assert _ids(r) == ["c:renovacao"]
    r = P.todos([_c(fim="2027-03-01", dias_fim=102)], {"Solar Alfa": ficha}, [], {}, {}, HOJE)
    assert r["por_cliente"]["Solar Alfa"] == []
    # vencida: o aviso de renovação não aparece junto (o ponto é a vigência)
    r = P.todos([_c(fim="2026-08-25", dias_fim=-86, avisar_ate="2026-07-26", dias_aviso=-116, aviso_dias=30)], {"Solar Alfa": ficha},
                [], {}, {}, HOJE)
    assert _ids(r) == ["c:vigencia"] and "venceu" in r["por_cliente"]["Solar Alfa"][0]["texto"]
    # sem PDF lido; e a minuta na pasta
    r = P.todos([_c()], {}, [], {}, {}, HOJE)
    assert _ids(r) == ["c:sem_pdf"]
    # sem contrato assinado: só a minuta, ou só o anexo; com o contrato assinado, o anexo sem assinatura é o normal
    f = dict(_ficha(), documentos=[{"arquivo": "minuta.pdf", "tipo": "minuta", "assinado": False}])
    r = P.todos([_c()], {"Solar Alfa": f}, [], {}, {}, HOJE)
    assert _ids(r) == ["c:minuta"] and "minuta.pdf" in r["por_cliente"]["Solar Alfa"][0]["texto"]
    f = dict(_ficha(), documentos=[{"arquivo": "anexo.pdf", "tipo": "anexo", "assinado": None}])
    assert _ids(P.todos([_c()], {"Solar Alfa": f}, [], {}, {}, HOJE)) == ["c:sem_assinado"]
    f = dict(_ficha(), documentos=[{"arquivo": "c.pdf", "tipo": "contrato", "assinado": True}] + [{"arquivo": f"a{i}.pdf", "tipo": "anexo", "assinado": False} for i in range(8)])
    assert P.todos([_c()], {"Solar Alfa": f}, [], {}, {}, HOJE)["por_cliente"]["Solar Alfa"] == []


def test_as_divergencias_dos_leitores_e_da_planilha_com_o_pdf():
    ficha = _ficha(vigencia={"fim": "2027-01-01", "ref": {"arquivo": "contrato.pdf", "pagina": 3}},
                   divergencias=[{"tema": "Roçada", "proposta": "3x por ano", "contrato": "2x por ano", "prevalece": "o contrato"},
                                 {"tema": "Prazo do relatório", "texto": "Contrato: 7 dias corridos. Anexo: 7 dias úteis."}])
    r = P.todos([_c(fim="2027-02-01", dias_fim=74)], {"Solar Alfa": ficha}, [], {}, {}, HOJE)
    ps = r["por_cliente"]["Solar Alfa"]
    assert [p["origem"] for p in ps] == ["leitor", "leitor", "planilha"] and all(p["nivel"] == "divergencia" for p in ps)
    assert ps[0]["texto"] == "Proposta: 3x por ano · Contrato: 2x por ano" and ps[0]["prevalece"] == "o contrato"
    assert ps[1]["texto"].startswith("Contrato: 7 dias corridos")
    assert "01/02/2027" in ps[2]["texto"] and "01/01/2027" in ps[2]["texto"]
    assert ps[2]["onde"] == "p. 3" and ps[2]["onde_inteiro"] == "contrato.pdf, p. 3"


def test_o_radar_da_zeladoria_casa_pelo_nome_e_o_que_nao_casa_aparece():
    radar = [{"cliente": "SÓLAR ALFA", "ufv": "UFV Um", "nivel_alerta": "divergencia", "status": "Divergência: roçagem 3x × 2x"},
             {"cliente": "Solar Alfa", "ufv": "UFV Dois", "nivel_alerta": "divergencia", "status": "Divergência: roçagem 3x × 2x"},
             {"cliente": "Solar Alfa", "ufv": "UFV Três", "nivel_alerta": "ok", "status": "Contrato claro"},
             {"cliente": "Outra Energia", "ufv": "—", "nivel_alerta": "atencao", "status": "VERIFICAR: solicitar contrato"}]
    r = P.todos([_c(fim="2027-06-01", dias_fim=194)], {"Solar Alfa": _ficha()}, radar, {}, {}, HOJE)
    ps = r["por_cliente"]["Solar Alfa"]
    assert len(ps) == 1 and ps[0]["origem"] == "radar" and ps[0]["texto"] == "roçagem 3x × 2x"
    assert ps[0]["onde"] == "UFVs: UFV Um, UFV Dois" and ps[0]["setor"] == "Zeladoria"
    assert r["radar_sem_contrato"] == ["Outra Energia"] and r["radar_lido"] is True
    # o Radar fora do ar: a tela avisa, e os outros pontos seguem
    assert P.todos([_c()], {}, None, {}, {}, HOJE)["radar_lido"] is False


def test_o_resolvido_vai_para_o_fim_e_o_id_muda_com_o_dado():
    c = _c(fim="2026-12-10", dias_fim=21)
    r = P.todos([c], {}, [], {}, {"c:vigencia:2026-12-10": {"id": "rx", "como": "Aditivo assinado"}}, HOJE)
    ps = r["por_cliente"]["Solar Alfa"]
    assert [p["id"] for p in ps] == ["c:sem_pdf", "c:vigencia:2026-12-10"] and ps[1]["resolvido"]["como"] == "Aditivo assinado"
    # a vigência nova é outro ponto: a resolução velha não o esconde
    r = P.todos([_c(fim="2027-01-10", dias_fim=52)], {}, [], {}, {"c:vigencia:2026-12-10": {"id": "rx"}}, HOJE)
    assert all(p["resolvido"] is None for p in r["por_cliente"]["Solar Alfa"])


def test_incluir_e_resolver_um_ponto_pede_motivo_e_prova_e_reabrir_volta(carga, cliente):  # noqa: F811
    adm = _como(cliente, "admin@gridco.com.br", admin=True)
    prova = dict(motivo="Alinhado com o cliente", prova_texto="E-mail do cliente confirmando o combinado.")
    sem = dict(motivo="", prova_texto="")
    novo = {"nivel": "Divergência", "texto": "A proposta e o anexo dizem frequências diferentes", "setor": "Zeladoria"}
    assert _editar(adm, item_tipo="ponto", evento="inclusao", cliente="Solar Alfa", valores=novo, **sem)[0] == 400
    st, r = _editar(adm, item_tipo="ponto", evento="inclusao", cliente="Solar Alfa", valores=novo, **prova)
    assert st == 200
    pid = r["item_ids"][0]
    d = adm.get("/t/comando/contratos/dados.json").get_json()
    p = next(x for x in d["pontos"]["Solar Alfa"] if x["id"] == pid)
    assert p["origem"] == "incluido" and p["nivel"] == "divergencia" and p["resolvido"] is None and p["setor"] == "Zeladoria"
    antes = next(c for c in d["contratos"] if c["cliente"] == "Solar Alfa")["pontos_divergencia"]
    # resolver: sem motivo e prova, não grava; ponto inventado, recusado
    res = {"ponto_id": pid, "ponto_texto": novo["texto"], "como": "Vale o anexo, combinado com o cliente"}
    assert _editar(adm, item_tipo="resolucao", evento="inclusao", cliente="Solar Alfa", valores=res, **sem)[0] == 400
    assert _editar(adm, item_tipo="resolucao", evento="inclusao", cliente="Solar Alfa", valores=dict(res, ponto_id="<x>"), **prova)[0] == 400
    st, r = _editar(adm, item_tipo="resolucao", evento="inclusao", cliente="Solar Alfa", valores=res, **prova)
    assert st == 200
    rid = r["item_ids"][0]
    d = adm.get("/t/comando/contratos/dados.json").get_json()
    p = next(x for x in d["pontos"]["Solar Alfa"] if x["id"] == pid)
    assert p["resolvido"]["como"] == res["como"] and p["resolvido"]["id"] == rid
    assert next(c for c in d["contratos"] if c["cliente"] == "Solar Alfa")["pontos_divergencia"] == antes - 1
    h = adm.get("/t/comando/contratos/historico.json", query_string={"cliente": "Solar Alfa"}).get_json()["historico"]
    assert any(x["item_tipo"] == "Ponto resolvido" and x["motivo"] == prova["motivo"] for x in h)
    # reabrir = retirar a resolução, com motivo e prova também
    assert _editar(adm, item_tipo="resolucao", item_id=rid, evento="retirada", cliente="Solar Alfa", valores={}, **sem)[0] == 400
    assert _editar(adm, item_tipo="resolucao", item_id=rid, evento="retirada", cliente="Solar Alfa", valores={}, **prova)[0] == 200
    d = adm.get("/t/comando/contratos/dados.json").get_json()
    assert next(x for x in d["pontos"]["Solar Alfa"] if x["id"] == pid)["resolvido"] is None
    # quem não é gestor nem administrador não resolve
    fora = _como(cliente, "outra@gridco.com.br")
    assert _editar(fora, item_tipo="resolucao", evento="inclusao", cliente="Solar Alfa", valores=res, **prova)[0] == 400


def test_a_tela_dos_pontos_do_setor_e_da_clausula(cliente):
    r = cliente.get("/static/contratos.js")
    js = r.get_data(as_text=True)
    r.close()
    for t in ('["pontos", "Pontos"]', "function rPontos(c)", "function pontosCel(i, c)", '["setor", "Por setor"]', "ctr-setor",
              "function clTag(ref)", "<th>Cláusula</th>", "data-dobra", "nexus.contratos.dobras", "Reabrir o ponto", "radar_sem_contrato"):
        assert t in js, t
    # o bloco "não batem" saiu das Regras: a planilha × o PDF está na aba Pontos (pontos.py)
    assert "function divergencias(" not in js
    # a célula de texto miúdo não usa a classe .sub (display:block tirava a célula da linha da tabela)
    assert '<td class="sub"' not in js

"""As fichas dos contratos na Visão do contrato (18/11/2026). Levi, 17/11/2026: "e se eu salvar os PDFs dos contratos para
você analisar e fazer algo melhor?", "completa tudo!" e "faça por subagentes para melhor confiabilidade".

As fichas daqui são inventadas (o repositório é público): o mesmo formato das lidas dos PDFs, clientes e cláusulas
fictícios. O que estes testes seguram: o Nexus só aceita o formato (cliente, contratos, regras com categoria conhecida e
referência), casa o cliente da ficha com o da planilha pelo nome sem acento e sem caixa, só o administrador importa, o
arquivo errado não apaga o que estava, e o dados.json entrega as fichas junto da planilha."""
import io
import json

import pytest

from nexus.contratos import fichas as F

from test_contratos_controle import _planilha

FICHA = {
    "cliente": "SOLAR ALFA",
    "documentos": [{"arquivo": "contrato.pdf", "tipo": "contrato", "assinado": True},
                   {"arquivo": "1o aditivo.pdf", "tipo": "aditivo", "assinado": True}],
    "contratos": [{
        "id": "ALFA-NORTE", "arquivo": "contrato.pdf",
        "vigencia": {"inicio": "2025-02-25", "fim": "2027-02-24", "ref": {"arquivo": "contrato.pdf", "pagina": 2, "clausula": "5.1"}},
        "renovacao": {"aviso_previo_dias": 60, "ref": {"arquivo": "contrato.pdf", "pagina": 2, "clausula": "5.2"}},
        "regras": [
            {"categoria": "SLA", "nome": "Chegada em falha crítica", "contratual": "Até 4 h", "vigente": "Até 6 h",
             "alterado_por": {"arquivo": "1o aditivo.pdf", "pagina": 1, "clausula": "2", "resumo": "amplia o prazo",
                              "trecho": "o prazo passa a ser de 6 h"},
             "setor": "Supervisão de Campo", "ref": {"arquivo": "contrato.pdf", "pagina": 9, "clausula": "11.1"},
             "trecho": "chegar ao local em até 4 (quatro) horas"},
            {"categoria": "Entregáveis", "nome": "Relatório mensal", "contratual": "Até o 5º dia útil", "vigente": "Até o 5º dia útil",
             "setor": "Performance", "ref": {"arquivo": "contrato.pdf", "pagina": 7, "clausula": "7.2"}, "trecho": "até o 5º dia útil"}],
        "lacunas": ["o contrato não traz o valor mensal"]}]}


def test_aceita_o_formato_e_recusa_o_que_nao_e():
    assert F.ler(FICHA) == [FICHA] and F.ler([FICHA]) == [FICHA] and F.ler({"fichas": [FICHA]}) == [FICHA]
    ruins = [[], {"x": 1}, {"cliente": "", "contratos": []}, {"cliente": "A", "contratos": []},
             {"cliente": "A", "contratos": [{"regras": [{"categoria": "Inventada", "ref": {}}]}]},
             {"cliente": "A", "contratos": [{"regras": [{"categoria": "SLA"}]}]},          # sem a referência
             [FICHA, dict(FICHA)]]                                                         # o mesmo cliente duas vezes
    for r in ruins:
        with pytest.raises(F.FichasInvalidas):
            F.ler(r)


def test_casa_o_cliente_com_o_da_planilha_pelo_nome():
    outra = dict(FICHA, cliente="Cliente Sem Planilha")
    por = F.por_cliente([FICHA, outra], ["Beta GD", "Solar Alfa"])
    assert set(por) == {"Solar Alfa", "Cliente Sem Planilha"} and por["Solar Alfa"] is FICHA


def test_so_o_administrador_importa_o_errado_nao_apaga_e_o_dados_json_entrega(logado, tmp_path):
    logado.application.config.update(NEXUS_DADOS=str(tmp_path))
    r = logado.post("/t/comando/visao-do-contrato/importar", data={"planilha": (io.BytesIO(_planilha()), "controle.xlsx")},
                    content_type="multipart/form-data")
    assert r.status_code == 302
    html = logado.get("/t/comando/visao-do-contrato").get_data(as_text=True)
    assert 'name="fichas"' in html and "/t/comando/visao-do-contrato/importar-fichas" in html
    assert "fichas" not in logado.get("/t/comando/visao-do-contrato/dados.json").get_json()
    # o arquivo errado é recusado e não grava nada
    r = logado.post("/t/comando/visao-do-contrato/importar-fichas", data={"fichas": (io.BytesIO(b"{nao e json"), "f.json")},
                    content_type="multipart/form-data")
    assert r.status_code == 302 and "Não importei as fichas" in logado.get("/t/comando/visao-do-contrato").get_data(as_text=True)
    assert not (tmp_path / "contratos" / F.ARQUIVO).exists()
    corpo = json.dumps([FICHA], ensure_ascii=False).encode("utf-8")
    r = logado.post("/t/comando/visao-do-contrato/importar-fichas", data={"fichas": (io.BytesIO(corpo), "fichas.json")},
                    content_type="multipart/form-data")
    assert r.status_code == 302
    assert "Fichas importadas: 1 clientes, 1 contratos e 2 regras" in logado.get("/t/comando/visao-do-contrato").get_data(as_text=True)
    j = logado.get("/t/comando/visao-do-contrato/dados.json").get_json()
    assert list(j["fichas"]) == ["Solar Alfa"] and j["fichas"]["Solar Alfa"]["contratos"][0]["id"] == "ALFA-NORTE"
    assert j["fichas_info"]["arquivo"] == "fichas.json"
    # quem não é administrador não importa
    with logado.session_transaction() as s:
        s["admin"] = False
    r = logado.post("/t/comando/visao-do-contrato/importar-fichas", data={"fichas": (io.BytesIO(corpo), "f.json")},
                    content_type="multipart/form-data")
    assert r.status_code == 403


def test_a_pagina_mostra_as_regras_com_a_prova_e_o_que_nao_bate(cliente):
    p = cliente.get("/static/previa/visao-do-contrato.html")
    pagina = p.get_data(as_text=True)
    p.close()
    # a regra abre o trecho literal e a página; a mudada por aditivo mostra o antes riscado
    assert "function rRegrasContrato(c, f)" in pagina and 'class="rg" data-rg="' in pagina and 'class="trecho"' in pagina
    assert "antes: <s>" in pagina
    # a planilha e o contrato que não batem, e o que o contrato não diz
    assert "A planilha de controle e o contrato não batem" in pagina and "O que o contrato não diz" in pagina
    # as outras abas trazem o que o contrato pede
    for t in ('"O que o contrato pede"', '"O atendimento que o contrato pede"', '"Rotinas que o contrato pede"',
              '"Metas, bônus e penalidades do contrato"', "Valor no contrato"):
        assert t in pagina
    # nenhum dado de contrato na página (o repositório é público): vem do dados.json
    assert "fichaDe(c)" in pagina and "REAL.fichas" in pagina

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


def test_o_contrato_completa_so_o_vazio_da_planilha_e_diz_de_onde_veio():
    """Levi, 18/11/2026: "faça um rework lá nos contratos e bote os dados que faltam!"."""
    k1 = {"id": "K1", "vigencia": {"inicio": "2025-06-10", "fim": "2028-06-10", "ref": {"pagina": 14}},
          "renovacao": {"aviso_previo_dias": 30, "ref": {"pagina": 14}}, "reajuste": {"indice": "IPCA", "data_base": "data da assinatura"},
          "valor": {"mensal": 1000.0}, "regras": []}
    k2 = {"id": "K2", "vigencia": {"inicio": "2025-05-21", "fim": "2028-05-21", "ref": {"pagina": 14}},
          "renovacao": {"aviso_previo_dias": 30}, "reajuste": {"indice": "IPCA"}, "valor": {"mensal": 500.5}, "regras": []}
    k3 = {"id": "K3", "vigencia": {}, "renovacao": {"aviso_previo_dias": 90}, "valor": {"mensal": None}, "regras": []}
    f = {"cliente": "Alfa", "documentos": [{"assinado": True}, {"assinado": False}], "contratos": [k1, k2, k3]}
    vazio = {"cliente": "Alfa", "inicio": None, "fim": None, "aviso_dias": None, "indice": "", "data_base": None}
    c = F.completar([vazio, {"cliente": "Sem PDF", "fim": None}], {"Alfa": f})
    a = c[0]
    # o fim mais cedo; o aviso não entra (30 e 90 não viram um); o índice igual entra; a data-base por extenso não
    assert (a["inicio"], a["fim"], a["aviso_dias"], a["indice"], a["data_base"]) == ("2025-05-21", "2028-05-21", None, "IPCA", None)
    assert a["origem"]["fim"] == {"fonte": "contrato", "contrato": "K2", "ref": {"pagina": 14}, "de": 2, "total": 3}
    assert set(a["origem"]) == {"inicio", "fim", "indice"}
    assert a["valor_mensal"] == 1500.5 and a["valor_info"] == {"com_valor": 2, "contratos": 3, "minuta": True}
    # quem não tem PDF segue igual; o dado da planilha não é trocado pelo do contrato
    assert c[1] == {"cliente": "Sem PDF", "fim": None}
    cheio = dict(vazio, fim="2027-01-01", indice="IGP-M")
    b = F.completar([cheio], {"Alfa": f})[0]
    assert (b["fim"], b["indice"]) == ("2027-01-01", "IGP-M") and "fim" not in b["origem"] and "indice" not in b["origem"]

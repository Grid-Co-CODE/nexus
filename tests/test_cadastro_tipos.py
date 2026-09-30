"""Tipos de campo do cadastro: o que entra pelo formulário, o que vem do Excel e o que vai para a API.

A lição que manda aqui é a de 25/08/2026 na plataforma: a API devolve data como TEXTO, e espelhar o texto
sem restaurar o tipo fez as metas colapsarem num mês só, sem erro na tela. Cada tipo tem de fazer a volta
completa (formulário -> API -> leitura) sem perder o tipo.
"""
from datetime import date, datetime

import pytest

from nexus.cadastro.tipos import Legado, ValorInvalido, de_api, de_formulario, do_excel, exibir, para_api


# ── formulário ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("tipo, texto, esperado", [
    ("numero", "2,877", 2.877),
    ("numero", "1.234,5", 1234.5),
    ("numero", "12.5", 12.5),
    ("moeda", "R$ 11.745,00", 11745.0),
    ("inteiro", "1.080", 1080),
    ("inteiro", "12", 12),
    ("coordenada", "-12,345°", -12.345),
    ("data", "2026-09-29", date(2026, 9, 29)),
    ("data", "29/09/2026", date(2026, 9, 29)),
    ("simnao", "nao", "Não"),
    ("simnao", "SIM", "Sim"),
    ("email", "  Fulano.Tal@GridCo.com.br ", "fulano.tal@gridco.com.br"),
    ("cpf", "529.982.247-25", "52998224725"),
    ("telefone", "(11) 91234-5678", "11912345678"),
    ("url", "https://maps.app.goo.gl/abc", "https://maps.app.goo.gl/abc"),
    ("texto", "  Brodowski  ", "Brodowski"),
])
def test_formulario_converte_para_o_tipo(tipo, texto, esperado):
    assert de_formulario(tipo, texto) == esperado


@pytest.mark.parametrize("tipo", ["texto", "numero", "data", "cpf", "email", "simnao"])
def test_formulario_vazio_e_none(tipo):
    # Vazio é vazio de verdade: o sync da API recusa célula de texto vazio (03/09/2026).
    assert de_formulario(tipo, "   ") is None


@pytest.mark.parametrize("tipo, texto", [
    ("numero", "doze"),
    ("inteiro", "12,5"),
    ("coordenada", "200"),
    ("data", "31/02/2026"),
    ("simnao", "talvez"),
    ("email", "fulano.gridco.com.br"),
    ("cpf", "529.982.247-24"),          # dígito verificador errado
    ("cpf", "111.111.111-11"),          # sequência repetida passa na conta e não é CPF
    ("telefone", "1234"),
    ("url", "maps.google.com"),
])
def test_formulario_recusa_valor_fora_do_tipo(tipo, texto):
    with pytest.raises(ValorInvalido):
        de_formulario(tipo, texto)


@pytest.mark.parametrize("texto, esperado", [("n/a", "N/A"), ("N/I", "N/I"), ("-", "-")])
def test_marcador_de_nao_se_aplica_vale_em_campo_numerico(texto, esperado):
    # O BD usa "N/A" em 12 linhas de QTD TCU e em Cabine/SKID/QGBT: é informação, não erro.
    assert de_formulario("inteiro", texto) == esperado


# ── Excel ──────────────────────────────────────────────────────────────────

def test_excel_data_e_datetime_vira_date():
    assert do_excel("data", datetime(2026, 3, 1, 0, 0)) == date(2026, 3, 1)


def test_excel_coordenada_em_texto_vira_numero():
    # 48 latitudes da aba Operações estão como texto: "-9.87", "-9,87", "-9.87°", " -9.87°".
    assert do_excel("coordenada", " -9,8712°") == -9.8712


def test_excel_cpf_numerico_recupera_zero_a_esquerda():
    # 58 CPFs estão como NÚMERO no BD: o Excel comeu o zero da frente.
    assert do_excel("cpf", 1234567890) == "01234567890"


def test_excel_valor_fora_do_tipo_vira_legado_e_nao_se_perde():
    # "Pendente" numa coluna de data (34 linhas de Data Mobilização): guarda o texto, marca, não descarta.
    v = do_excel("data", "Pendente")
    assert isinstance(v, Legado) and v.texto == "Pendente"
    v = do_excel("numero", "2,,5")      # digitação errada real da POTÊNCIA REAL
    assert isinstance(v, Legado) and v.texto == "2,,5"


def test_excel_telefone_numerico_vira_texto_de_digitos():
    assert do_excel("telefone", 11912345678) == "11912345678"


def test_na_digitado_no_lugar_da_pessoa_e_nao_se_aplica():
    # 115 células da aba Operações têm "N/A" digitado no técnico/eletricista/mantenedor e nos contatos: é
    # "esta usina não tem mantenedor". Tratar como legado (ou como vazio = automático) poria o mantenedor da
    # equipe numa usina que não tem.
    assert do_excel("ref", "n/a") == "N/A"
    assert do_excel("telefone", "N/A") == "N/A"
    assert de_api("telefone", "N/A") == "N/A"
    assert de_formulario("telefone", "N/A") == "N/A"


# ── API: ida e volta sem perder o tipo ─────────────────────────────────────

@pytest.mark.parametrize("tipo, valor", [
    ("data", date(2026, 9, 29)),
    ("numero", 2.877),
    ("inteiro", 1080),
    ("moeda", 11745.0),
    ("simnao", "Sim"),
    ("cpf", "01234567890"),
    ("texto", "Brodowski"),
    ("inteiro", "N/A"),
])
def test_api_ida_e_volta(tipo, valor):
    assert de_api(tipo, para_api(tipo, valor)) == valor


def test_api_data_vai_como_texto_iso_e_volta_como_date():
    assert para_api("data", date(2026, 2, 1)) == "2026-02-01"
    assert de_api("data", "2026-02-01") == date(2026, 2, 1)


def test_api_texto_que_nao_e_do_tipo_volta_como_legado():
    v = de_api("data", "Pendente")
    assert isinstance(v, Legado) and v.texto == "Pendente"
    assert para_api("data", v) == "Pendente"


# ── exibição pt-BR ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("tipo, valor, esperado", [
    ("numero", 2.877, "2,877"),
    ("numero", 1234.5, "1.234,5"),
    ("moeda", 11745.0, "R$ 11.745,00"),
    ("inteiro", 1080, "1.080"),
    ("data", date(2026, 9, 29), "29/09/2026"),
    ("cpf", "01234567890", "012.345.678-90"),
    ("telefone", "11912345678", "(11) 91234-5678"),
    ("telefone", "1133334444", "(11) 3333-4444"),
    ("numero", None, ""),
])
def test_exibir_em_pt_br(tipo, valor, esperado):
    assert exibir(tipo, valor) == esperado


def test_exibir_legado_mostra_o_texto_original():
    assert exibir("data", Legado("Pendente")) == "Pendente"

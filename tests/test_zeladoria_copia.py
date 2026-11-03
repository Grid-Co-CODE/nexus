"""A cópia do Radar para os três livros do Nexus, a partir da exportação do Supabase (um JSON com os dados de cada
tabela, os tipos e as chaves; feita pelo SQL Editor, só leitura, 03/11/2026).

Banco falso: tests/pg_falso.py. Nomes, e-mails e valores fictícios; o primeiro nome do supervisor é "fulano".
"""
import json
from datetime import datetime, timezone

import pytest

from nexus.cadastro.cifra import Cofre, gerar_chave
from nexus.zeladoria import copia as C
from nexus.zeladoria import guardar as G
from nexus.zeladoria import tabelas as T
from tests.pg_falso import ApiPGFalsa

COFRE = Cofre(gerar_chave())
BASE = "http://banco"
AGORA = datetime(2026, 11, 3, 17, 0, tzinfo=timezone.utc)
DE_PARA = {"_leia": "fixture", "_nomes": ["fulano", "beltrana"], "fulano": "equipe", "Fulano": "Equipe",
           "planilha_beltrana": "planilha_historica"}


def _exportacao(**mudar):
    """Uma exportação mínima com as 39 tabelas (as da equipe com o nome fictício), quase todas vazias."""
    nomes = [a for a in T.TABELAS if a != "fracttal_ultimas"]
    nomes = [a.replace("_equipe", "_fulano") for a in nomes]
    tipos = {n: [["id", "text"]] for n in nomes}
    chaves = {n: "id" for n in nomes}
    tabelas = {n: [] for n in nomes}
    tipos["fornecedores"] = [["id", "text"], ["empresa", "text"], ["email_contrato", "text"], ["valor_mes", "numeric"]]
    tabelas["fornecedores"] = [{"id": "FORN-1", "empresa": "Fulano de Tal MEI", "email_contrato": "fulano@exemplo.com",
                                "valor_mes": 900}]
    tipos["config"] = [["chave", "text"], ["valor", "text"]]
    chaves["config"] = "chave"
    tabelas["config"] = [{"chave": "previsto_decidido_fulano", "valor": json.dumps({"escopo": "fulano", "x": 1})},
                         {"chave": "tema", "valor": "escuro"}]
    tipos["servicos_zeladoria"] = [["id", "text"], ["origem", "text"]]
    tabelas["servicos_zeladoria"] = [{"id": "SRV-1", "origem": "planilha_beltrana"}]
    tipos["gastos_fulano"] = [["id", "text"], ["valor", "numeric"]]
    tabelas["gastos_fulano"] = [{"id": "GJ-1", "valor": 150}, {"id": "GJ-2", "valor": 90}]
    tipos["rf_fracttal_ultimas"] = [["usina_chave", "text"], ["folio", "bigint"], ["tecnico", "text"]]
    exp = {"gerado_em": "2026-11-03T17:07:25+00:00", "tipos": tipos, "chaves": chaves,
           "ultimas": [{"usina_chave": "u1", "folio": 15504, "tecnico": "Fulano de Tal"}], "tabelas": tabelas}
    for k, v in mudar.items():
        exp[k] = v
    return exp


def _copiar(exp, banco, gravar=True):
    return C.copiar(exp, de_para=DE_PARA, cofre=COFRE, base=BASE, token="t", sessao=banco, gravar=gravar, agora=AGORA)


def test_copia_os_tres_livros_e_confere():
    banco = ApiPGFalsa()
    rel = _copiar(_exportacao(), banco)
    assert rel["gravou"] is True
    assert set(banco.workbooks) == {T.LIVRO_APP, T.LIVRO_FRACTTAL, T.LIVRO_HISTORICO}
    for aba, livro in T.TABELAS.items():
        assert (livro, aba) in banco.abas, aba
        assert rel["abas"][aba]["origem"] == rel["abas"][aba]["nexus"] == len(banco.linhas(livro, aba))
    assert len(banco.linhas(T.LIVRO_APP, "gastos_equipe")) == 2
    assert len(banco.linhas(T.LIVRO_FRACTTAL, "fracttal_ultimas")) == 1
    atu = banco.linhas(T.LIVRO_APP, "atualizacao")
    assert {(l["aba"], l["coluna"], l["tipo_pg"]) for l in atu} >= {("fornecedores", "empresa", "text"),
                                                                      ("gastos_equipe", "valor", "numeric")}


def test_ensaio_nao_grava():
    banco = ApiPGFalsa()
    rel = _copiar(_exportacao(), banco, gravar=False)
    assert rel["gravou"] is False and not banco.workbooks and rel["abas"]["fornecedores"]["origem"] == 1


def test_tabela_desconhecida_nao_grava_nada():
    exp = _exportacao()
    exp["tabelas"]["tabela_nova"] = []
    banco = ApiPGFalsa()
    with pytest.raises(T.TabelaDesconhecida, match="tabela_nova"):
        _copiar(exp, banco)
    assert not banco.workbooks


def test_exportacao_incompleta_nao_grava_nada():
    exp = _exportacao()
    del exp["tabelas"]["usinas"]
    banco = ApiPGFalsa()
    with pytest.raises(C.ExportacaoIncompleta, match="usinas"):
        _copiar(exp, banco)
    assert not banco.workbooks


def test_pessoal_nao_sai_em_claro():
    banco = ApiPGFalsa()
    _copiar(_exportacao(), banco)
    tudo = json.dumps([banco.linhas(wb, aba) for (wb, aba) in banco.abas], default=str)
    assert "Fulano" not in tudo and "fulano@exemplo.com" not in tudo


def test_valores_com_nome_renomeados():
    """O clone renomeou os valores com o primeiro nome do supervisor e o da planilha histórica; os dados seguem o
    mesmo de-para, inclusive dentro do JSON guardado como texto. Nome de gente e e-mail ficam como estão."""
    banco = ApiPGFalsa()
    rel = _copiar(_exportacao(), banco)
    tipos = {"chave": "text", "valor": "text"}
    config = {l["chave"]: l["valor"] for l in G.de_aba("config", tipos, banco.linhas(T.LIVRO_APP, "config"), COFRE, "chave")}
    assert set(config) == {"previsto_decidido_equipe", "tema"}
    assert json.loads(config["previsto_decidido_equipe"]) == {"escopo": "equipe", "x": 1}
    srv = G.de_aba("servicos_zeladoria", {"id": "text", "origem": "text"},
                   banco.linhas(T.LIVRO_APP, "servicos_zeladoria"), COFRE, "id")
    assert srv == [{"id": "SRV-1", "origem": "planilha_historica"}]
    forn = G.de_aba("fornecedores", {"id": "text", "empresa": "text", "email_contrato": "text", "valor_mes": "numeric"},
                    banco.linhas(T.LIVRO_APP, "fornecedores"), COFRE, "id")
    assert forn[0]["empresa"] == "Fulano de Tal MEI" and forn[0]["email_contrato"] == "fulano@exemplo.com"
    assert rel["trocas"] == 3          # a chave do config, o escopo dentro do JSON e a origem da planilha


def test_a_consulta_de_exportacao_sai_do_de_para():
    """A consulta cita as seis tabelas pelo nome do supervisor: ela é montada na hora, pelo de-para que fica fora do
    repositório, e nunca fica escrita nele."""
    sql = C.sql_exportacao(DE_PARA)
    for aba in T.TABELAS:
        if aba != "fracttal_ultimas":
            assert f"radar_fornecedores.{aba.replace('_equipe', '_fulano')} x)" in sql, aba
    assert "public.rf_fracttal_ultimas" in sql and sql.lstrip().startswith("--") and "SÓ LEITURA" in sql
    for proibido in ("insert ", "update ", "delete ", "drop ", "alter ", "create "):
        assert proibido not in sql.lower()
    with pytest.raises(ValueError):
        C.sql_exportacao({"_leia": "sem o nome da equipe"})


def test_tabela_nova_no_esquema_para_a_copia():
    """A exportação real só traz as tabelas que a consulta cita; a tabela nova aparece nos tipos (o esquema inteiro)."""
    exp = _exportacao()
    exp["tipos"]["tabela_nova"] = [["id", "text"]]
    banco = ApiPGFalsa()
    with pytest.raises(T.TabelaDesconhecida, match="tabela_nova"):
        _copiar(exp, banco)
    assert not banco.workbooks


def test_renomeia_so_onde_o_clone_renomeou():
    """Fora das colunas que guardam chave de dado (config, ação do log, origem, escopo, tipo), nada é trocado, nem o
    texto com cara de identificador (revisão final de 03/11/2026: a troca por pedaço em qualquer coluna estragaria id e
    código)."""
    exp = _exportacao()
    exp["tipos"]["usinas"] = [["id", "text"], ["obs", "text"]]
    exp["tabelas"]["usinas"] = [{"id": "USN-1", "obs": "visita_do_fulano"}]       # obs vai cifrado
    banco = ApiPGFalsa()
    _copiar(exp, banco)
    usinas = G.de_aba("usinas", {"id": "text", "obs": "text"}, banco.linhas(T.LIVRO_APP, "usinas"), COFRE, "id")
    assert usinas == [{"id": "USN-1", "obs": "visita_do_fulano"}]


def test_nome_que_sobra_em_claro_para_a_copia():
    exp = _exportacao()
    exp["tipos"]["fila_prioridade"] = [["id", "text"], ["servico", "text"]]
    exp["tabelas"]["fila_prioridade"] = [{"id": "PRI-1", "servico": "Roçagem do Fulano"}]
    banco = ApiPGFalsa()
    with pytest.raises(C.NomeEmClaro, match="fila_prioridade.servico"):
        _copiar(exp, banco)
    assert not banco.workbooks


def test_chave_de_json_renomeada_que_colide_para():
    with pytest.raises(C.TrocaInsegura):
        C.renomear({"k_fulano": 1, "k_equipe": 2}, C._trocas(DE_PARA))

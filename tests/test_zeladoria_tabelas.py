"""O mapa das tabelas do Radar de Fornecedores (a plataforma de zeladoria) para os livros do Nexus.

Desenho: docs/superpowers/specs/2026-11-03-zeladoria-no-nexus-design.md. As 39 tabelas do Supabase do Radar e a view
das últimas rondas vão para três livros com o MESMO nome de tabela (Levi, 03/11/2026: "com a mesma lógica e caminhos do
BD"), menos as seis da equipe primarizada, que levavam o primeiro nome do supervisor e viram `*_equipe` (o repositório
é público). Os nomes de pessoa nos testes são fictícios ("fulano").
"""
import pytest

from nexus.dados import catalogo
from nexus.zeladoria import tabelas as T


def test_as_40_abas_em_um_livro_so():
    assert len(T.TABELAS) == 40
    assert set(T.TABELAS.values()) <= {T.LIVRO_APP, T.LIVRO_FRACTTAL, T.LIVRO_HISTORICO}
    assert T.TABELAS["fracttal_ultimas"] == T.LIVRO_FRACTTAL
    assert T.TABELAS["log"] == T.LIVRO_HISTORICO
    assert T.TABELAS["cotacoes"] == T.LIVRO_APP


def test_equipe_primarizada_casa_por_padrao():
    assert T.nome_no_nexus("gastos_fulano") == "gastos_equipe"
    assert T.nome_no_nexus("orcamento_fulano_semanal") == "orcamento_equipe_semanal"
    assert T.nome_no_nexus("tipos_gasto_fulano") == "tipos_gasto_equipe"
    assert T.nome_no_nexus("simulacao_repasse_fulano") == "simulacao_repasse_equipe"
    assert T.nome_no_nexus("rota_fulano") == "rota_equipe"
    assert T.nome_no_nexus("orcamento_fulano") == "orcamento_equipe"
    assert T.nome_no_nexus("cotacoes") == "cotacoes"


def test_tabela_desconhecida_para():
    with pytest.raises(T.TabelaDesconhecida, match="tabela_nova"):
        T.nome_no_nexus("tabela_nova")


def test_view_vira_aba():
    assert T.aba_da_view("rf_cotacoes") == "cotacoes"
    assert T.aba_da_view("rf_rota_fulano") == "rota_equipe"
    assert T.aba_da_view("rf_fracttal_ultimas") == "fracttal_ultimas"
    with pytest.raises(T.TabelaDesconhecida):
        T.aba_da_view("cotacoes")          # sem o rf_ não é view do Radar


@pytest.mark.parametrize("aba, coluna", [
    ("fornecedores", "empresa"), ("fornecedores", "pix"), ("usinas", "contato_email"), ("usinas", "responsavel_om"),
    ("cotacoes", "obs"), ("perfis", "email"), ("log", "quem"), ("fin_cenario", "criado_por"),
    ("fracttal_rondas", "tecnico"), ("colaboradores", "nome"), ("config", "valor"), ("cronograma_publico", "dados"),
])
def test_coluna_pessoal_e_cifrada(aba, coluna):
    assert T.coluna_cifrada(aba, coluna)


@pytest.mark.parametrize("aba, coluna", [
    ("cotacoes", "valor"), ("colaboradores", "id"), ("colaboradores", "fornecedor_id"), ("usinas", "potencia"),
    ("config", "chave"), ("financeiro_parcelas", "valor"),
])
def test_coluna_de_negocio_fica_em_claro(aba, coluna):
    assert not T.coluna_cifrada(aba, coluna)


def test_livros_no_catalogo():
    for nome in (T.LIVRO_APP, T.LIVRO_FRACTTAL, T.LIVRO_HISTORICO):
        l = catalogo.LIVRO_POR_NOME[nome]
        assert l.no_banco is False                       # regra 10: registrado antes da 1ª gravação
        assert "atualizacao" in l.abas
        assert set(l.abas) - {"atualizacao"} == {a for a, lv in T.TABELAS.items() if lv == nome}
    assert set(catalogo.LIVRO_POR_NOME[T.LIVRO_HISTORICO].so_cresce) == {
        "log", "financeiro_historico", "fin_provisao_historico", "cronograma_alteracoes"}
    assert all(catalogo.aba_segue_a_regra(a) for a in T.TABELAS)

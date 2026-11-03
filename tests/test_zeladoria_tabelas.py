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


# o RADAR (fixture): as 33 tabelas de nome fixo e as seis da equipe primarizada com um primeiro nome fictício
RADAR = [a for a in T.TABELAS if a != "fracttal_ultimas" and not a.endswith(("_equipe", "_equipe_semanal"))] + [
    "tipos_gasto_fulano", "gastos_fulano", "orcamento_fulano", "orcamento_fulano_semanal", "simulacao_repasse_fulano",
    "rota_fulano"]


def test_mapa_de_tabelas_aceita_o_radar():
    m = T.mapa_de_tabelas(RADAR)
    assert len(m) == 39 and sorted(m.values()) == sorted(a for a in T.TABELAS if a != "fracttal_ultimas")
    assert m["gastos_fulano"] == "gastos_equipe" and m["cotacoes"] == "cotacoes"


@pytest.mark.parametrize("troca", [
    ("rota_fulano", "rota_otimizada"),          # outro "nome": não é a mesma equipe
    (None, "gastos_fornecedor"),                # tabela nova que cairia calada em cima de gastos_equipe
])
def test_mapa_recusa_tabela_parecida(troca):
    velho, novo = troca
    nomes = [n for n in RADAR if n != velho] + [novo]
    with pytest.raises(T.TabelaDesconhecida):
        T.mapa_de_tabelas(nomes)


@pytest.mark.parametrize("aba, coluna, tipo", [
    ("fornecedores", "empresa", "text"), ("fornecedores", "pix", "text"), ("usinas", "contato_tecnico", "text"),
    ("usinas", "responsavel_om", "text"), ("cotacoes", "obs", "text"), ("perfis", "email", "text"),
    ("log", "quem", "text"), ("fin_cenario", "criado_por", "text"), ("fracttal_rondas", "tecnico", "text"),
    ("colaboradores", "nome", "text"), ("config", "valor", "text"), ("cronograma_publico", "dados", "jsonb"),
    # cifrado por padrão: o texto que ninguém listou (revisão final de 03/11/2026)
    ("ordens_servico", "justificativa", "text"), ("danos_modulos", "causa_detalhe", "text"),
    ("usinas", "dados_extra", "jsonb"), ("fin_fornecedor_alias", "nome_norm", "text"),
    ("cotacoes", "avaliacao_comentario", "text"), ("financeiro_historico", "campos", "jsonb"),
    ("contratos_anuais", "nome", "text"), ("log", "alvo", None),
])
def test_coluna_pessoal_e_cifrada(aba, coluna, tipo):
    assert T.coluna_cifrada(aba, coluna, tipo)


@pytest.mark.parametrize("aba, coluna, tipo", [
    ("cotacoes", "valor", "numeric"), ("colaboradores", "id", "text"), ("colaboradores", "fornecedor_id", "text"),
    ("colaboradores", "fornecedor_ids", "jsonb"), ("colaboradores", "excluido", "boolean"),
    ("cotacoes", "excluido_em", "timestamp with time zone"), ("usinas", "potencia_real_mwp", "numeric"),
    ("usinas", "cliente", "text"), ("usinas", "usina", "text"), ("cotacoes", "status_head", "text"),
    ("cotacoes", "data_head", "text"), ("cotacoes", "servico", "text"), ("config", "chave", "text"),
    ("fracttal_rondas", "usina_chave", "text"), ("financeiro_parcelas", "valor", "numeric"),
    ("cronograma_alteracoes", "de_inicio", "text"),
])
def test_coluna_de_negocio_fica_em_claro(aba, coluna, tipo):
    assert not T.coluna_cifrada(aba, coluna, tipo)


def test_livros_no_catalogo():
    for nome in (T.LIVRO_APP, T.LIVRO_FRACTTAL, T.LIVRO_HISTORICO):
        l = catalogo.LIVRO_POR_NOME[nome]
        assert l.no_banco is True                        # gravados e conferidos em 03/11/2026 (cópia de 17:07 UTC)
        assert "atualizacao" in l.abas
        assert set(l.abas) - {"atualizacao"} == {a for a, lv in T.TABELAS.items() if lv == nome}
    assert set(catalogo.LIVRO_POR_NOME[T.LIVRO_HISTORICO].so_cresce) == {
        "log", "financeiro_historico", "fin_provisao_historico", "cronograma_alteracoes"}
    assert all(catalogo.aba_segue_a_regra(a) for a in T.TABELAS)

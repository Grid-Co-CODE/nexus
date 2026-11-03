"""As regras do banco do Radar que a gravação da Zeladoria repete (revisão de 03/11/2026): a coluna e o tipo do
Postgres, o ON DELETE dos fornecedores, o histórico que só recebe linha nova, o id que não se reaproveita e o diário
que aguenta a última linha pela metade. Estado montado à mão; nomes e e-mails fictícios."""
import pytest

from nexus.cadastro.cifra import Cofre, gerar_chave
from nexus.zeladoria import gravacao

HEAD = {"id": "u-head", "email": "head@exemplo.com", "papel": "HEAD", "status": "aprovado"}
ANALISTA = {"id": "u-an", "email": "fulano@exemplo.com", "papel": "Analista", "status": "aprovado"}


def _estado():
    tipos = {
        "fornecedores": {"id": "text", "empresa": "text", "excluido": "boolean"},
        "cotacoes": {"id": "text", "fornecedor_id": "text", "periodo_id": "text", "valor": "numeric", "area": "numeric"},
        "documentos": {"id": "text", "fornecedor_id": "text", "colaborador_id": "text"},
        "fin_provisao": {"id": "text", "fornecedor_id": "text", "valor": "numeric"},
        "periodos": {"id": "text"},
        "log": {"id": "bigint", "em": "date", "quem": "text", "acao": "text", "alvo": "text", "obs": "text"},
        "historico_valor": {"id": "bigint", "cotacao_id": "text", "valor": "numeric"},
        "fin_provisao_historico": {"id": "bigint", "item_id": "text", "campo": "text"},
        "cronograma_alteracoes": {"id": "text", "chave": "text", "motivo": "text"},
    }
    abas = {
        "fornecedores": [{"id": "FORN-1", "empresa": "Fulano MEI", "excluido": False},
                         {"id": "FORN-2", "empresa": "Beltrano MEI", "excluido": False}],
        "cotacoes": [{"id": "COT-1", "fornecedor_id": "FORN-1", "periodo_id": "P1", "valor": 100, "area": 2},
                     {"id": "COT-2", "fornecedor_id": "FORN-2", "periodo_id": "P1", "valor": 200, "area": 3}],
        "documentos": [{"id": "DOC-1", "fornecedor_id": "FORN-1", "colaborador_id": None}],
        "fin_provisao": [{"id": "PRV-0001", "fornecedor_id": "FORN-1", "valor": 50}],
        "periodos": [{"id": "P1"}],
        "log": [{"id": 7, "em": "2026-11-01", "quem": "head@exemplo.com", "acao": "criar", "alvo": "COT-1", "obs": None}],
        "historico_valor": [{"id": 3, "cotacao_id": "COT-1", "valor": 100}],
        "fin_provisao_historico": [],
        "cronograma_alteracoes": [{"id": "ALT-1", "chave": "x", "motivo": None}],
    }
    return {"abas": abas, "tipos": tipos, "chaves": {a: "id" for a in abas}, "versao": 0, "versoes": {}}


@pytest.fixture
def g(tmp_path):
    g = gravacao.Gravador(base="http://pg.falso", token="t", sessao=None, cofre=Cofre(gerar_chave()),
                          diario=tmp_path / "diario.jsonl")
    g.carregar(_estado())
    return g


def _por_id(g, aba):
    return {l["id"]: l for l in g.estado["abas"][aba]}


def test_coluna_que_nao_existe_e_tipo_errado_sao_recusados(g):
    with pytest.raises(gravacao.Recusa, match="a coluna nova_coluna não existe"):
        g.aplicar([{"op": "upsert", "view": "rf_cotacoes", "linhas": [{"id": "COT-1", "nova_coluna": 1}]}], ANALISTA, 0)
    with pytest.raises(gravacao.Recusa, match="o valor de area não é numeric"):
        g.aplicar([{"op": "upsert", "view": "rf_cotacoes", "linhas": [{"id": "COT-1", "area": "1,5"}]}], ANALISTA, 0)
    with pytest.raises(gravacao.Recusa, match="o valor de id não é bigint"):
        g.aplicar([{"op": "insert", "view": "rf_log", "linhas": [{"id": "8.5", "acao": "x"}]}], ANALISTA, 0)
    g.aplicar([{"op": "upsert", "view": "rf_cotacoes", "linhas": [{"id": "COT-1", "valor": "150.5", "area": ""}]}],
              ANALISTA, 0)
    assert _por_id(g, "cotacoes")["COT-1"]["valor"] == 150.5 and _por_id(g, "cotacoes")["COT-1"]["area"] is None
    assert g.estado["versao"] == 1


def test_excluir_o_fornecedor_leva_o_que_o_banco_do_radar_levava(g):
    g.aplicar([{"op": "delete", "view": "rf_fornecedores", "filtros": [["eq", "id", "FORN-1"]]}], HEAD, 0)
    assert set(_por_id(g, "cotacoes")) == {"COT-2"}                         # cascade
    assert _por_id(g, "documentos") == {}                                     # cascade
    assert _por_id(g, "fin_provisao")["PRV-0001"]["fornecedor_id"] is None   # set null
    rastro = [l for l in g.estado["abas"]["log"] if l["acao"] == "excluir-definitivo"]
    assert len(rastro) == 1 and rastro[0]["alvo"] == "fornecedores:FORN-1"
    assert rastro[0]["obs"] == "em cascata: cotacoes 1, documentos 1, fin_provisao 1"


def test_excluir_a_rodada_solta_as_cotacoes(g):
    g.aplicar([{"op": "delete", "view": "rf_periodos", "filtros": [["eq", "id", "P1"]]}], HEAD, 0)
    assert {c["periodo_id"] for c in g.estado["abas"]["cotacoes"]} == {None} and len(g.estado["abas"]["cotacoes"]) == 2


def test_o_historico_so_recebe_linha_nova(g):
    with pytest.raises(gravacao.Recusa, match="só muda pelas funções do financeiro"):
        g.aplicar([{"op": "insert", "view": "rf_fin_provisao_historico", "linhas": [{"item_id": "IT-1", "campo": "valor"}]}],
                  HEAD, 0)
    with pytest.raises(gravacao.Recusa, match="já existe"):
        g.aplicar([{"op": "upsert", "view": "rf_log", "linhas": [{"id": 7, "acao": "outra"}]}], HEAD, 0)
    with pytest.raises(gravacao.Recusa, match="só recebe linha nova"):
        g.aplicar([{"op": "update", "view": "rf_log", "patch": {"acao": "outra"}, "filtros": [["eq", "id", 7]]}], HEAD, 0)
    # o motivo da alteração do cronograma, que o app preenche depois, passa
    g.aplicar([{"op": "update", "view": "rf_cronograma_alteracoes", "patch": {"motivo": "chuva"},
                "filtros": [["eq", "id", "ALT-1"]]}], ANALISTA, 0)
    assert _por_id(g, "cronograma_alteracoes")["ALT-1"]["motivo"] == "chuva"


def test_o_id_novo_nao_reaproveita_nem_colide(g):
    # o id explícito igual ao maior + 1, seguido de um gerado no mesmo salvamento, não funde as duas linhas
    r = g.aplicar([{"op": "insert", "view": "rf_historico_valor", "linhas": [{"id": 4, "cotacao_id": "COT-1", "valor": 1},
                                                                            {"cotacao_id": "COT-1", "valor": 2}]}],
                  ANALISTA, 0)
    assert r["ids"] == [[5]] and len(g.estado["abas"]["historico_valor"]) == 3
    g.aplicar([{"op": "delete", "view": "rf_historico_valor", "filtros": [["eq", "id", 5]]}], ANALISTA, 0)
    r = g.aplicar([{"op": "insert", "view": "rf_historico_valor", "linhas": [{"cotacao_id": "COT-2", "valor": 3}]}],
                  ANALISTA, 0)
    assert r["ids"] == [[6]]                                                  # o 5 que saiu não volta


def test_a_ultima_linha_do_diario_pela_metade_e_ignorada(g, tmp_path):
    g.aplicar([{"op": "upsert", "view": "rf_cotacoes", "linhas": [{"id": "COT-1", "valor": 150}]}], ANALISTA, 0)
    with open(tmp_path / "diario.jsonl", "a", encoding="utf-8") as f:
        f.write("cf1:pela-meta")                                              # a queda no meio do acréscimo
    novo = gravacao.Gravador(base="http://pg.falso", token="t", sessao=None, cofre=g.cofre, diario=tmp_path / "diario.jsonl")
    novo.carregar(_estado())
    assert _por_id(novo, "cotacoes")["COT-1"]["valor"] == 150 and novo.estado["versao"] == 1
    # no meio, não se adivinha: a torre não sobe
    texto = (tmp_path / "diario.jsonl").read_text(encoding="utf-8")
    (tmp_path / "diario.jsonl").write_text("cf1:quebrada\n" + texto, encoding="utf-8")
    with pytest.raises(Exception):
        gravacao.Gravador(base="http://pg.falso", token="t", sessao=None, cofre=g.cofre,
                          diario=tmp_path / "diario.jsonl").carregar(_estado())


def test_quem_le_a_lista_antiga_nao_a_ve_mudar(g):
    antes = g.estado["abas"]["cotacoes"]
    g.aplicar([{"op": "delete", "view": "rf_cotacoes", "filtros": [["eq", "id", "COT-1"]]}], HEAD, 0)
    assert len(antes) == 2 and len(g.estado["abas"]["cotacoes"]) == 1

"""A linha do Radar (Supabase) vira linha de aba do livro do Nexus e volta igual: os tipos, a cifra do dado pessoal e o
valor grande partido (a célula do xlsx guarda no máximo 32.767 caracteres; o `config` do Radar tem JSON maior).
Nomes e e-mails fictícios."""
import logging
from datetime import date, datetime, timezone

from nexus.cadastro.cifra import Cofre, gerar_chave
from nexus.zeladoria import guardar as G

COFRE = Cofre(gerar_chave())


def _como_lido(cab, linhas):
    """O que o `livros.ler` devolve: um dict por linha, com o cabeçalho; o vazio volta como None."""
    return [dict(zip(cab, l)) for l in linhas]


def test_ida_e_volta_de_todos_os_tipos():
    colunas = [("id", "text"), ("n", "integer"), ("grande", "bigint"), ("valor", "numeric"), ("ativo", "boolean"),
               ("dia", "date"), ("em", "timestamp with time zone"), ("dados", "jsonb"), ("lista", "ARRAY"),
               ("vazio", "text")]
    linha = {"id": "COT-001", "n": 3, "grande": 12345678901, "valor": 1500.5, "ativo": True, "dia": date(2026, 10, 5),
             "em": datetime(2026, 10, 5, 13, 0, tzinfo=timezone.utc), "dados": {"a": [1, 2], "b": "x"},
             "lista": ["ROÇAGEM", "LIMPEZA"], "vazio": None}
    cab, linhas = G.para_aba("cotacoes", colunas, [linha], COFRE, "id")
    tipos = dict(colunas)
    volta = G.de_aba("cotacoes", tipos, _como_lido(cab, linhas), COFRE, "id")[0]
    assert volta == dict(linha, dia="2026-10-05", em="2026-10-05T13:00:00+00:00")


def test_volta_quando_a_api_devolve_tudo_como_texto():
    colunas = [("id", "text"), ("n", "integer"), ("valor", "numeric"), ("ativo", "boolean"), ("dados", "json")]
    lido = [{"id": "X", "n": "3", "valor": "1500.5", "ativo": "true", "dados": '{"a": 1}'}]
    assert G.de_aba("cotacoes", dict(colunas), lido, COFRE, "id") == [
        {"id": "X", "n": 3, "valor": 1500.5, "ativo": True, "dados": {"a": 1}}]


def test_coluna_pessoal_vai_cifrada():
    colunas = [("id", "text"), ("empresa", "text"), ("valor_mes", "numeric")]
    cab, linhas = G.para_aba("fornecedores", colunas, [{"id": "FORN-1", "empresa": "Fulano MEI", "valor_mes": 900}],
                             COFRE, "id")
    gravada = dict(zip(cab, linhas[0]))
    assert gravada["empresa"].startswith("cf1:") and "Fulano" not in gravada["empresa"]
    assert gravada["valor_mes"] == 900
    assert G.de_aba("fornecedores", dict(colunas), _como_lido(cab, linhas), COFRE, "id")[0]["empresa"] == "Fulano MEI"


def test_cifra_presa_a_linha():
    colunas = [("id", "text"), ("empresa", "text")]
    cab, linhas = G.para_aba("fornecedores", colunas, [{"id": "A", "empresa": "Fulano"}, {"id": "B", "empresa": "Beltrano"}],
                             COFRE, "id")
    lido = _como_lido(cab, linhas)
    lido[1]["empresa"] = lido[0]["empresa"]          # a cifra do A posta na linha do B
    volta = G.de_aba("fornecedores", dict(colunas), lido, COFRE, "id")
    assert volta[0]["empresa"] == "Fulano" and volta[1]["empresa"] == G.NAO_ABRE


def test_valor_grande_partido():
    texto = "x" * 70_000
    colunas = [("chave", "text"), ("valor", "text")]
    cab, linhas = G.para_aba("config", colunas, [{"chave": "planejados", "valor": texto}, {"chave": "c2", "valor": "1"}],
                             COFRE, "chave")
    assert cab[:2] == ["chave", "valor"] and "valor__p2" in cab and "valor__p3" in cab
    assert len(linhas) == 2
    assert all(v is None or len(str(v)) <= G.PARTE for l in linhas for v in l)
    volta = G.de_aba("config", dict(colunas), _como_lido(cab, linhas), COFRE, "chave")
    assert volta == [{"chave": "planejados", "valor": texto}, {"chave": "c2", "valor": "1"}]


def test_cifra_que_nao_abre_nao_derruba(caplog):
    colunas = [("id", "text"), ("email", "text")]
    cab, linhas = G.para_aba("perfis", colunas, [{"id": "u1", "email": "fulano@exemplo.com"}], COFRE, "id")
    outra = Cofre(gerar_chave())
    with caplog.at_level(logging.WARNING):
        volta = G.de_aba("perfis", dict(colunas), _como_lido(cab, linhas), outra, "id")
    assert volta[0]["email"] == G.NAO_ABRE
    assert "perfis" in caplog.text and "email" in caplog.text and "fulano" not in caplog.text


def test_json_que_e_so_texto_volta_igual():
    """Um jsonb pode guardar só um texto ("ROÇAGEM") ou um número escrito como texto ("123")."""
    colunas = [("id", "text"), ("servicos", "jsonb")]
    linhas_radar = [{"id": "A", "servicos": "ROÇAGEM"}, {"id": "B", "servicos": "123"}, {"id": "C", "servicos": [1]}]
    cab, linhas = G.para_aba("fornecedores", colunas, linhas_radar, COFRE, "id")
    assert G.de_aba("fornecedores", dict(colunas), _como_lido(cab, linhas), COFRE, "id") == linhas_radar


def test_json_estragado_nao_derruba(caplog):
    lido = [{"id": "A", "fornecedor_ids": "isto não é json"}]
    with caplog.at_level(logging.WARNING):
        volta = G.de_aba("colaboradores", {"id": "text", "fornecedor_ids": "jsonb"}, lido, COFRE, "id")
    assert volta == [{"id": "A", "fornecedor_ids": "isto não é json"}] and "colaboradores" in caplog.text


def test_nao_abre_so_vale_para_texto():
    """"(não abre)" é verdadeiro no JavaScript: num campo que não é texto ele viraria objeto ou bandeira errada."""
    colunas = [("id", "text"), ("avaliacao_colaboradores", "jsonb"), ("obs", "text")]
    cab, linhas = G.para_aba("cotacoes", colunas, [{"id": "C", "avaliacao_colaboradores": {"x": 1}, "obs": "y"}],
                             COFRE, "id")
    volta = G.de_aba("cotacoes", dict(colunas), _como_lido(cab, linhas), Cofre(gerar_chave()), "id")[0]
    assert volta["avaliacao_colaboradores"] is None and volta["obs"] == G.NAO_ABRE


def test_chave_que_e_dado_pessoal():
    """O apelido do fornecedor é a chave da linha e é nome (fornecedor MEI): vai cifrado, e as outras colunas da
    linha se prendem ao valor dele."""
    colunas = [("nome_norm", "text"), ("fornecedor_id", "text"), ("nome_planilha", "text")]
    linha = {"nome_norm": "fulano de tal", "fornecedor_id": "FORN-1", "nome_planilha": "FULANO DE TAL MEI"}
    cab, linhas = G.para_aba("fin_fornecedor_alias", colunas, [linha], COFRE, "nome_norm")
    gravada = dict(zip(cab, linhas[0]))
    assert gravada["nome_norm"].startswith("cf1:") and gravada["nome_planilha"].startswith("cf1:")
    assert G.de_aba("fin_fornecedor_alias", dict(colunas), _como_lido(cab, linhas), COFRE, "nome_norm") == [linha]


def test_chave_numerica_lida_como_texto():
    """A API pode devolver o id 5 como "5", 5.0 ou "5.0": a cifra da linha tem de abrir nos quatro."""
    colunas = [("id", "bigint"), ("quem", "text")]
    cab, linhas = G.para_aba("log", colunas, [{"id": 5, "quem": "fulano@exemplo.com"}], COFRE, "id")
    for lido_id in (5, "5", 5.0, "5.0"):
        lido = [dict(_como_lido(cab, linhas)[0], id=lido_id)]
        assert G.de_aba("log", dict(colunas), lido, COFRE, "id") == [{"id": 5, "quem": "fulano@exemplo.com"}]

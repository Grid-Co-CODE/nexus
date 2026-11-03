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

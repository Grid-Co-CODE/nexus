"""O almoxarifado no PCM (25/10/2026, Levi: "No fractall temos almoxarifado, gostaria de uma visão para a gestão desse
almoxarifado na parte de PCM"): o contrato dos livros que o App publica da varredura diária do inventário do Fracttal,
as contas, os fatos e a carga do histórico. Desenho: docs/superpowers/specs/2026-10-25-almoxarifado-design.md."""
from nexus.dados import almoxarifado as A
from nexus.dados import dominios


# ── contrato e contas ───────────────────────────────────────────────────────────────────────────────────────────────

def test_numero_le_texto_da_api():
    """A API pode devolver tudo como texto, e o Fracttal manda o saldo como "10.00"."""
    assert A.numero("10.00") == 10.0 and A.numero("0") == 0.0 and A.numero(3) == 3.0
    assert A.numero("") is None and A.numero(None) is None and A.numero("abc") is None


def test_chave_do_local():
    """O pedaço "Cliente - Usina - UF" do caminho do almoxarifado no Fracttal (a mesma chave da Classificação 1)."""
    assert A.chave_do_local("// Greenyellow/ Greenyellow - Irecê 1 - BA/") == "Greenyellow - Irecê 1 - BA"
    assert A.chave_do_local("// Thopen/ Thopen - Brodowski 1 - SP/ Cabine 1/") == "Thopen - Brodowski 1 - SP"
    assert A.chave_do_local("Greenyellow - Cedro 1 - CE") == "Greenyellow - Cedro 1 - CE"
    assert A.chave_do_local("Almoxarifado") is None and A.chave_do_local(None) is None


def test_situacao():
    assert A.situacao(1, 2) == "abaixo"
    assert A.situacao(2, 2) == "no_limite"
    assert A.situacao(0, 0) == "zerada" and A.situacao(0, None) == "zerada"
    assert A.situacao(3, 0) == "sem_minimo" and A.situacao(3, None) == "sem_minimo"
    assert A.situacao(5, 2) == "ok"


def _ciclo(lidos, total, inicio="2026-10-25T03:00:12Z"):
    return {"Início do ciclo": inicio, "Fim do ciclo": "2026-10-25T03:29:42Z", "Itens na lista do Fracttal": total,
            "Itens lidos": lidos, "Erros": 0, "Origem": "automático"}


def test_completo_pelo_proprio_ciclo():
    """Aplica só com 90% dos itens da lista lidos (a queda contra o ciclo anterior não trava: o PCM pode limpar o
    catálogo)."""
    assert A.completo(_ciclo(574, 574)) and A.completo(_ciclo(517, 574))
    assert not A.completo(_ciclo(516, 574)) and not A.completo(_ciclo(0, 0))
    assert A.completo(_ciclo("574", "574"))                          # a API devolve como texto
    assert not A.completo({})


def test_ciclo_comum():
    i = "2026-10-25T03:00:12Z"
    ciclo, itens, saldo = [_ciclo(574, 574, i)], [{"Início do ciclo": i}] * 2, [{"Início do ciclo": i}]
    assert A.ciclo_comum(ciclo, itens, saldo) == i
    assert A.ciclo_comum(ciclo, itens, [{"Início do ciclo": "2026-10-24T03:00:05Z"}]) is None   # Saldo de D-1
    assert A.ciclo_comum(ciclo, [], saldo) is None
    assert A.ciclo_comum(ciclo, itens + [{"Início do ciclo": "2026-10-24T03:00:05Z"}], saldo) is None


def test_contrato_e_dominio():
    assert A.COLUNAS_CICLO == ("Início do ciclo", "Fim do ciclo", "Itens na lista do Fracttal", "Itens lidos", "Erros",
                               "Origem")
    assert A.COLUNAS_SALDO[-1] == "Início do ciclo" and "Local do almoxarifado" in A.COLUNAS_SALDO
    assert "Lançado por (HMAC)" in A.COLUNAS_PECAS and not any("e-mail" in c.lower() for c in A.COLUNAS_PECAS)
    assert dominios.RECUSA_PECA == ("chave recusada pelo Fracttal", "sem permissão", "outro")

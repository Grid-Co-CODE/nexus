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


# ── catálogo ────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_almoxarifado_no_catalogo():
    """Fonte nova entra primeiro no catálogo (PRIORIDADE 0), com grão, tipo, medidas e o livro registrado antes de
    existir: assim os livros do App não aparecem como "novos" no radar da Governança."""
    from nexus.dados import catalogo, explica
    s, c, p = (catalogo.POR_ID[f] for f in ("saldo_almox", "ciclo_varredura", "peca_lancada"))
    assert (s.tipo, c.tipo, p.tipo) == ("snapshot_periodico", "snapshot_acumulado", "snapshot_acumulado")
    assert s.area == c.area == p.area == "pcm"
    assert s.dims["equipamento"][0] == "prop" and s.dims["usina"][0] == "nome" and p.dims["pessoa"][0] == "hmac"
    med = {m.coluna: m for m in s.medidas}
    assert med["saldo_qtd"].soma == med["minimo_qtd"].soma == "semi"
    assert all(catalogo.medida_valida(m) for f in (s, c, p) for m in f.medidas)
    assert A.LIVRO_SALDO + " · " + A.ABA_SALDO in s.fontes and A.LIVRO_PECAS + " · " + A.ABA_PECAS in p.fontes
    assert catalogo.LIVRO_POR_NOME["nexus_almoxarifado"].so_cresce
    assert not catalogo.LIVRO_POR_NOME["nexus_almoxarifado"].no_banco
    assert catalogo.da_familia("nexus_almoxarifado_saldo_2026_10", "fato_saldo_almox")
    assert any(k.livro == A.LIVRO_ITENS and k.papel == "dimensao" for k in catalogo.CONHECIDAS)
    for f in (s, c, p):
        assert explica.RESUMO.get(f.id) and explica.PARA_QUE.get(f.id), f.id

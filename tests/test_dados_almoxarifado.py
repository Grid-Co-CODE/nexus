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
    assert s.dims["equipamento"][0] == "prop" and s.dims["usina"][0] == "id" and p.dims["pessoa"][0] == "id"
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


# ── os fatos ────────────────────────────────────────────────────────────────────────────────────────────────────────

INICIO = "2026-10-25T03:00:12Z"


def _lig():
    from nexus.dados import fatos
    usinas = [{"usina_id": 7, "codigo": "GRYL-IRC100", "excluido": "não"},
              {"usina_id": 9, "codigo": "RNGR-NOB100", "excluido": "não"}]   # o código casaria: não liga por ele
    de_para = [{"usina_id": 7, "sistema": "Fracttal · Classificação 1", "chave_externa": "Greenyellow - Irecê 1 - BA"}]
    return fatos.Ligador(usinas, de_para, [], {"hmac-tec-1": 501})


def _saldo(item, almox, local, saldo, minimo, inicio=INICIO, **kw):
    return dict({"ID do item": str(item), "Código": f"SP-{item}", "ID do almoxarifado": str(almox),
                 "Almoxarifado": f"Almox {almox}", "Local do almoxarifado": local, "Saldo": saldo, "Mínimo": minimo,
                 "Início do ciclo": inicio}, **kw)


IRC = "// Greenyellow/ Greenyellow - Irecê 1 - BA/"
NOB = "// RenoGrid/ RenoGrid - Nobres 1 - MT/"


def test_saldo_liga_a_usina_pela_de_para_e_nao_chuta():
    from nexus.dados import fato_almoxarifado as F
    linhas = F.saldo_do_ciclo([_saldo(2, 123021, IRC, 4, 2), _saldo(1, 123675, NOB, 1, 1)], _lig())
    por = {l[F.CAB_SALDO.index("id_item")]: dict(zip(F.CAB_SALDO, l)) for l in linhas}
    assert por["2"]["usina_id"] == 7 and por["2"]["usina_ligada_por"] == "de-para do Fracttal"
    assert por["1"]["usina_id"] is None and por["1"]["usina_ligada_por"] is None    # a Nobres não está na de-para
    assert [l[F.CAB_SALDO.index("id_item")] for l in linhas] == ["1", "2"]          # ordenado: o sha não varia


def test_saldo_numeros_em_texto():
    from nexus.dados import fato_almoxarifado as F
    l = dict(zip(F.CAB_SALDO, F.saldo_do_ciclo([_saldo(1, 5, IRC, "10.00", "0")], _lig())[0]))
    assert l["saldo_qtd"] == 10.0 and l["minimo_qtd"] == 0.0
    l = dict(zip(F.CAB_SALDO, F.saldo_do_ciclo([_saldo(1, 5, IRC, "3", "")], _lig())[0]))
    assert l["minimo_qtd"] is None


def test_mesma_foto_mesmo_saldo_id_e_releitura_e_outra_foto():
    from nexus.dados import fato_almoxarifado as F
    a = F.saldo_do_ciclo([_saldo(1, 5, IRC, 2, 1), _saldo(2, 5, IRC, 0, 0)], _lig())
    assert a == F.saldo_do_ciclo([_saldo(2, 5, IRC, 0, 0), _saldo(1, 5, IRC, 2, 1)], _lig())
    b = F.saldo_do_ciclo([_saldo(1, 5, IRC, 2, 1, inicio="2026-10-25T18:40:00Z")], _lig())
    i_id, i_dia = F.CAB_SALDO.index("saldo_id"), F.CAB_SALDO.index("data_id")
    assert b[0][i_id] != a[0][i_id] and b[0][i_dia] == a[0][i_dia] == 20261025


def test_data_id_e_o_dia_de_brasilia():
    from nexus.dados import fato_almoxarifado as F
    l = dict(zip(F.CAB_SALDO, F.saldo_do_ciclo([_saldo(1, 5, IRC, 1, 1, inicio="2026-10-26T02:30:00Z")], _lig())[0]))
    assert l["data_id"] == 20261025
    assert F.livro_do_mes(20261025) == "nexus_almoxarifado_saldo_2026_10"


def _peca(lid, situacao, motivo="", **kw):
    return dict({"ID do lançamento": lid, "Recebido em": "2026-10-22T13:10:00Z", "Usada em": "2026-10-22T12:58:00Z",
                 "OS": "16885", "Tarefa": "[Grid Co.] - MPM - Inversor", "Código do ativo": "IRC100-INV1",
                 "ID do item": "45561926", "Código": "SP-PEL-102.06", "ID do almoxarifado": "123021",
                 "Quantidade": "2", "Unidade": "UNIDADE", "Situação": situacao, "Motivo da recusa": motivo,
                 "Lançado por (HMAC)": "hmac-tec-1"}, **kw)


def test_peca_reenviada_vale_a_ultima_e_a_antiga_fica():
    from nexus.dados import fato_almoxarifado as F
    almox = {"123021": (7, "de-para do Fracttal")}
    antes = F.mesclar_pecas([], [_peca("A", "recusada", "chave recusada pelo Fracttal"),
                                 _peca("B", "recusada", "erro de Fulano no Fracttal")], _lig(), almox)
    banco = [dict(zip(F.CAB_PECA, l)) for l in antes]
    depois = F.mesclar_pecas(banco, [_peca("A", "lançada")], _lig(), almox)       # B saiu da janela do App
    por = {l[0]: dict(zip(F.CAB_PECA, l)) for l in depois}
    assert set(por) == {"A", "B"} and por["A"]["lancada"] == 1 and por["A"]["recusa"] == ""
    assert por["B"]["lancada"] == 0 and por["B"]["recusa"] == "outro"          # fora do domínio: nunca o texto
    assert por["A"]["usina_id"] == 7 and por["A"]["pessoa_id"] == 501 and por["A"]["quantidade_qtd"] == 2.0
    assert por["A"]["data_id"] == 20261022 and por["A"]["tarefa_chave"] and por["A"]["os"] == "16885"
    assert not any("Fulano" in str(v) for l in depois for v in l)


def test_peca_sem_usada_em_fica_com_o_dia_do_recebimento():
    from nexus.dados import fato_almoxarifado as F
    p = _peca("C", "lançada", **{"Usada em": "", "Recebido em": "2026-10-23T02:00:00Z"})
    l = dict(zip(F.CAB_PECA, F.mesclar_pecas([], [p], _lig(), {})[0]))
    assert l["data_id"] == 20261022 and l["data_id_recebida"] == 20261022 and l["usina_id"] is None


def test_dim_nao_encolhe():
    from nexus.dados import fato_almoxarifado as F
    banco = [{"id_item": "1", "codigo": "A", "nome": "Fusível", "unidade": "UNIDADE", "familia": "F", "avariado": 0,
              "ferramenta": 0}]
    novas = [["2", "B", "Cabo", "METRO", "C", 0, 0], ["1", "A", "Fusível 10A", "UNIDADE", "F", 0, 0]]
    out = F.mesclar_dim(banco, novas, "id_item", F.CAB_DIM_ITEM)
    assert [l[0] for l in out] == ["1", "2"] and out[0][2] == "Fusível 10A"
    assert F.mesclar_dim(banco, [], "id_item", F.CAB_DIM_ITEM) == [["1", "A", "Fusível", "UNIDADE", "F", 0, 0]]


def test_dims_do_ciclo():
    from nexus.dados import fato_almoxarifado as F
    itens = [{"ID do item": "1", "Código": "A", "Nome": "Fusível", "Unidade": "UNIDADE", "Família": "F",
              "Avariado": "Não", "Ferramenta": "Não", "Início do ciclo": INICIO, "Lido": "Sim"},
             {"ID do item": "2", "Código": "B-AV", "Nome": "[AVARIADO] Cabo", "Unidade": "METRO", "Família": "C",
              "Avariado": "Sim", "Ferramenta": "Não", "Início do ciclo": INICIO, "Lido": "Não"}]
    assert F.dim_itens(itens) == [["1", "A", "Fusível", "UNIDADE", "F", 0, 0],
                                  ["2", "B-AV", "[AVARIADO] Cabo", "METRO", "C", 1, 0]]
    al = F.dim_almoxarifados([_saldo(1, 5, IRC, 1, 1), _saldo(2, 5, IRC, 1, 1), _saldo(1, 6, NOB, 1, 1)], _lig())
    assert al == [["5", "Almox 5", "Greenyellow - Irecê 1 - BA", 7, "de-para do Fracttal"],
                  ["6", "Almox 6", "RenoGrid - Nobres 1 - MT", None, None]]


def test_linha_do_ciclo_e_qualidade_no_cab_da_casa():
    from nexus.dados import fatos
    from nexus.dados import fato_almoxarifado as F
    c = dict(zip(F.CAB_CICLO, F.linha_ciclo(_ciclo(516, 574), "recusado", "516 de 574 itens lidos", "agora")))
    assert c["situacao"] == "recusado" and c["itens_lidos_qtd"] == 516 and c["anulado"] == 0
    assert c["data_id"] == 20261025 and c["ciclo_inicio"] == INICIO
    linhas = F.saldo_do_ciclo([_saldo(2, 123021, IRC, 4, 2), _saldo(1, 123675, NOB, 1, 1)], _lig())
    q = dict(zip(fatos.CAB_QUALIDADE, F.linha_qualidade("saldo_almox", linhas, F.CAB_SALDO, INICIO, "agora",
                                                         sem_usina=["RenoGrid - Nobres 1 - MT"])))
    assert q["linhas"] == 2 and q["pct_usina"] == 50.0 and q["pct_data"] == 100.0
    assert "Nobres" in q["sem_usina_exemplos"] and q["livro_origem"] == "almoxarifado_saldo_app_campo · Saldo"


def test_os_fatos_montados_no_catalogo_batem_com_o_codigo():
    from nexus.dados import catalogo
    from nexus.dados import fato_almoxarifado as F
    for fid, cab in (("saldo_almox", F.CAB_SALDO), ("ciclo_varredura", F.CAB_CICLO), ("peca_lancada", F.CAB_PECA)):
        f = catalogo.POR_ID[fid]
        assert f.estado == "montado" and f.chave[0] == cab[0], fid
        assert f.conformado_em.split(" · ")[0] in (F.LIVRO, "nexus_almoxarifado_saldo_AAAA_MM"), fid

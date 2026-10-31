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
                               "Origem", "Linhas de saldo")
    assert "Início do ciclo" in A.COLUNAS_SALDO and "Local do almoxarifado" in A.COLUNAS_SALDO
    assert "Lançado por (HMAC)" in A.COLUNAS_PECAS and not any("e-mail" in c.lower() for c in A.COLUNAS_PECAS)
    assert dominios.RECUSA_PECA == ("chave recusada pelo Fracttal", "sem permissão", "outro")


def test_colunas_novas_no_fim():
    """30/10/2026 (as nove melhorias do Almoxarifado): coluna nova só no FIM, dos dois lados. O Nexus sobe antes do App,
    então os livros de hoje não têm nenhuma destas; o que falta é vazio, nunca um valor inventado."""
    assert A.COLUNAS_ITENS[-2:] == ("Criticidade", "Curva ABC")
    assert A.COLUNAS_SALDO[-1] == "Custo unitário"
    assert A.COLUNAS_CONTAGENS[13] == "ID da linha"
    assert A.COLUNAS_CONTAGENS[14:] == ("Fabricante", "Modelo", "Número de série", "Fotos dos dados", "Recontagem de")
    assert A.TIPOS_CONTAGEM[-1] == "avariado" and A.TIPOS_CONTAGEM[:3] == ("item", "identificar", "fora_do_catalogo")
    assert A.NA == "n/a"


def test_curva_abc_normaliza():
    """A curva é a que o PCM preenche no cadastro da peça no Fracttal; o Nexus não calcula. Só A, B ou C: o que não
    é uma delas fica vazio ("sem curva"), nunca vira C."""
    assert [A.curva_abc(v) for v in ("A", "b", " Curva C ", "c - baixo giro")] == ["A", "B", "C", "C"]
    assert [A.curva_abc(v) for v in ("", None, "X", "AB", "1")] == ["", "", "", "", ""]
    assert [A.curva_abc(v) for v in ("Curva ABC", "curva", "Baixo", 3, True)] == [""] * 5


def test_custo_so_positivo():
    """O custo que o Fracttal não deu (vazio, 0, texto, "nan") é None: virar 0 faria a peça valer nada na soma."""
    assert A.custo("12,5") == 12.5 and A.custo(3) == 3.0 and A.custo("15.50") == 15.5
    assert [A.custo(v) for v in ("0", "-3", "", None, "nan", "abc")] == [None] * 6
    assert [A.custo(v) for v in ("inf", "None", True, 0, 0.0)] == [None] * 5


def test_fotos_dos_dados():
    assert A.fotos_dos_dados("fabricante:k1|modelo:k2|serie:k3") == {"fabricante": "k1", "modelo": "k2", "serie": "k3"}
    assert A.fotos_dos_dados("modelo:k2|outro:k9|serie:") == {"modelo": "k2"}
    assert A.fotos_dos_dados("") == {} and A.fotos_dos_dados(None) == {}
    # a chave é tudo depois do primeiro ":" (a do App pode ter outros), e os espaços em volta não contam
    assert A.fotos_dos_dados(" serie : a:b | fabricante:k1 ") == {"serie": "a:b", "fabricante": "k1"}
    assert A.fotos_dos_dados("sem-dois-pontos|modelo") == {}


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
    assert med["custo_unitario_brl"].soma == "nao" and med["custo_unitario_brl"].unidade == "R$"   # preço não se soma
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
    novas = [["2", "B", "Cabo", "METRO", "C", 0, 0, "", ""],
             ["1", "A", "Fusível 10A", "UNIDADE", "F", 0, 0, "1.Crítico", "A"]]
    out = F.mesclar_dim(banco, novas, "id_item", F.CAB_DIM_ITEM)
    assert [l[0] for l in out] == ["1", "2"] and out[0][2] == "Fusível 10A" and out[0][-2:] == ["1.Crítico", "A"]
    # a linha do banco gravada antes das colunas novas segue inteira: as duas ficam vazias (None), não inventadas
    assert F.mesclar_dim(banco, [], "id_item", F.CAB_DIM_ITEM) == [["1", "A", "Fusível", "UNIDADE", "F", 0, 0, None, None]]


def test_dims_do_ciclo():
    from nexus.dados import fato_almoxarifado as F
    itens = [{"ID do item": "1", "Código": "A", "Nome": "Fusível", "Unidade": "UNIDADE", "Família": "F",
              "Avariado": "Não", "Ferramenta": "Não", "Início do ciclo": INICIO, "Lido": "Sim"},
             {"ID do item": "2", "Código": "B-AV", "Nome": "[AVARIADO] Cabo", "Unidade": "METRO", "Família": "C",
              "Avariado": "Sim", "Ferramenta": "Não", "Início do ciclo": INICIO, "Lido": "Não"}]
    assert F.dim_itens(itens) == [["1", "A", "Fusível", "UNIDADE", "F", 0, 0, "", ""],
                                  ["2", "B-AV", "[AVARIADO] Cabo", "METRO", "C", 1, 0, "", ""]]
    al = F.dim_almoxarifados([_saldo(1, 5, IRC, 1, 1), _saldo(2, 5, IRC, 1, 1), _saldo(1, 6, NOB, 1, 1)], _lig())
    assert al == [["5", "Almox 5", "Greenyellow - Irecê 1 - BA", 7, "de-para do Fracttal"],
                  ["6", "Almox 6", "RenoGrid - Nobres 1 - MT", None, None]]


def test_historico_leva_criticidade_e_curva():
    """A criticidade e a Curva ABC são as do cadastro da peça no Fracttal (a varredura do App as traz): vão na dimensão
    do item, no fim. O livro Itens de hoje não as tem, e a peça sem curva fica vazia, nunca "C"."""
    from nexus.dados import fato_almoxarifado as F
    assert F.CAB_DIM_ITEM[-2:] == ["criticidade", "curva_abc"]
    itens = [{"ID do item": "1", "Código": "A", "Nome": "Fusível", "Unidade": "UNIDADE", "Família": "F", "Avariado": "Não",
              "Ferramenta": "Não", "Criticidade": "1.Crítico", "Curva ABC": "a"},
             {"ID do item": "2", "Código": "B", "Nome": "Cabo", "Unidade": "METRO", "Família": "C", "Avariado": "Não",
              "Ferramenta": "Não"},
             {"ID do item": "3", "Código": "C", "Nome": "Terminal", "Unidade": "UNIDADE", "Família": "C",
              "Avariado": "Não", "Ferramenta": "Não", "Criticidade": None, "Curva ABC": "sem curva"}]
    por = {l[0]: dict(zip(F.CAB_DIM_ITEM, l)) for l in F.dim_itens(itens)}
    assert (por["1"]["criticidade"], por["1"]["curva_abc"]) == ("1.Crítico", "A")
    assert (por["2"]["criticidade"], por["2"]["curva_abc"]) == ("", "")           # o livro velho: sem as colunas
    assert (por["3"]["criticidade"], por["3"]["curva_abc"]) == ("", "")           # o que não é A, B ou C não vira C


def test_saldo_do_ciclo_leva_custo():
    from nexus.dados import fato_almoxarifado as F
    assert F.CAB_SALDO[-1] == "custo_unitario_brl"
    linhas = F.saldo_do_ciclo([_saldo(1, 5, IRC, 2, 1, **{"Custo unitário": "15,5"}),
                               _saldo(2, 5, IRC, 2, 1, **{"Custo unitário": "0"}),
                               _saldo(3, 5, IRC, 2, 1, **{"Custo unitário": ""}),
                               _saldo(4, 5, IRC, 2, 1)], _lig())
    custo = {l[F.CAB_SALDO.index("id_item")]: l[F.CAB_SALDO.index("custo_unitario_brl")] for l in linhas}
    assert custo == {"1": 15.5, "2": "", "3": "", "4": ""}       # o custo que o Fracttal não deu fica vazio, nunca 0
    assert all(len(l) == len(F.CAB_SALDO) for l in linhas)


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


# ── a carga do histórico (portão próprio, travas, ensaio) ───────────────────────────────────────────────────────────

BASE = "http://pg.falso"
CFG = {"GRIDCO_DB_API": BASE, "GRIDCO_SQL_TOKEN": "t", "NEXUS_ALMOX_GRAVAR": "1"}
ALMOX_LIVRO = "nexus_almoxarifado"
MES = "nexus_almoxarifado_saldo_2026_10"


DE_PARA_IRC = [{"usina_id": 7, "sistema": "Fracttal · Classificação 1", "chave_externa": "Greenyellow - Irecê 1 - BA"}]


def _semear(api, inicio=INICIO, lidos=None, total=2, saldo_inicio=None, pecas=None, txt=False, de_para=None,
            itens_faltando=0, saldo_extra=(), linhas_saldo=None, colunas_novas=False):
    """Os 4 livros do App e o cadastro, no banco de mentira, coerentes entre si: `total` itens na lista (o 1 e o 2 com
    saldo), os `lidos` primeiros com Lido = Sim. `txt`: tudo como texto (a API pode devolver assim);
    `itens_faltando`: o livro Itens chega sem as últimas linhas; `saldo_extra`: linhas a mais no Saldo;
    `colunas_novas`: o App de depois de 30/10/2026, com a Criticidade e a Curva ABC nos Itens (só o item 1 as tem) e o
    Custo unitário no Saldo (só o item 1 no almoxarifado 123021 tem custo)."""
    from test_campo_visao import _aba
    lidos = total if lidos is None else lidos
    t = (lambda v: None if v is None else str(v)) if txt else (lambda v: v)
    conv = lambda linhas: [{k: t(v) for k, v in l.items()} for l in linhas]      # noqa: E731
    _aba(api, "cadastro_nexus", "usinas", [{"usina_id": 7, "codigo": "GRYL-IRC100", "excluido": "não"},
                                           {"usina_id": 9, "codigo": "RNGR-NOB100", "excluido": "não"}])
    _aba(api, "cadastro_nexus", "de_para", DE_PARA_IRC if de_para is None else de_para)
    _aba(api, "cadastro_nexus", "equipes", [{"equipe_id": 1, "nome": "BA Oeste 01", "excluido": "não"}])
    nomes = {1: ("A", "Fusível", "UNIDADE", "F"), 2: ("B", "Cabo", "METRO", "C")}
    itens = [{"ID do item": str(i), "Código": nomes.get(i, (f"I{i}",))[0],
              "Nome": nomes.get(i, ("", f"Item {i}"))[1], "Unidade": nomes.get(i, ("", "", "UNIDADE"))[2],
              "Família": nomes.get(i, ("", "", "", "F"))[3], "Avariado": "Não", "Ferramenta": "Não",
              "Início do ciclo": inicio, "Lido": "Sim" if i <= lidos else "Não"} for i in range(1, total + 1)]
    saldo = [_saldo(1, 123021, IRC, 4, 2, inicio=saldo_inicio or inicio),
             _saldo(2, 123021, IRC, 0, 0, inicio=saldo_inicio or inicio),
             _saldo(1, 123675, NOB, 1, 1, inicio=saldo_inicio or inicio)] + list(saldo_extra)
    if colunas_novas:
        for i in itens:
            i.update({"Criticidade": "1.Crítico" if i["ID do item"] == "1" else "",
                      "Curva ABC": "a" if i["ID do item"] == "1" else ""})
        for s in saldo:
            s["Custo unitário"] = "15,5" if (s["ID do item"], s["ID do almoxarifado"]) == ("1", "123021") else ""
    c = dict(_ciclo(lidos, total, inicio), **{"Linhas de saldo": len(saldo) if linhas_saldo is None else linhas_saldo})
    _aba(api, A.LIVRO_CICLO, A.ABA_CICLO, conv([c]))
    _aba(api, A.LIVRO_ITENS, A.ABA_ITENS, conv(itens[:len(itens) - itens_faltando]))
    _aba(api, A.LIVRO_SALDO, A.ABA_SALDO, conv(saldo))
    _aba(api, A.LIVRO_PECAS, A.ABA_PECAS, conv(pecas if pecas is not None else [_peca("A", "lançada")]))


def _api(**kw):
    from pg_falso import ApiPGFalsa
    api = ApiPGFalsa(como_texto=kw.pop("como_texto", False))
    _semear(api, **kw)
    return api


def test_sem_os_livros_do_app_pula():
    from pg_falso import ApiPGFalsa
    from nexus.dados import carga
    api = ApiPGFalsa()
    assert carga.gerar_almoxarifado(CFG, api)["pulou"] == "o App ainda não publica o almoxarifado"
    assert api.syncs == 0


def test_sem_a_chave_e_ensaio():
    from nexus.dados import carga
    api = _api()
    r = carga.gerar_almoxarifado({k: v for k, v in CFG.items() if k != "NEXUS_ALMOX_GRAVAR"}, api)
    assert r["ensaio"] and r["saldo_linhas"] == 3 and api.syncs == 0


def test_grava_o_mes_e_a_marca_e_na_mesma_hora_pula():
    from nexus.dados import carga
    api = _api()
    r = carga.gerar_almoxarifado(CFG, api)
    assert set(r["gravado"]) == {MES, ALMOX_LIVRO}
    assert len(api.linhas(MES, "fato_saldo_almox")) == 3
    ciclos = api.linhas(ALMOX_LIVRO, "fato_ciclo_varredura")
    assert [c["situacao"] for c in ciclos] == ["aplicado"] and len(api.linhas(ALMOX_LIVRO, "fato_peca_lancada")) == 1
    assert len(api.linhas(ALMOX_LIVRO, "dim_almoxarifado")) == 2 and len(api.linhas(ALMOX_LIVRO, "qualidade")) == 3
    syncs = api.syncs
    assert "pulou" in carga.gerar_almoxarifado(CFG, api) and api.syncs == syncs


def _sem_as_colunas(api, livro, aba, n):
    """Deixa a aba do banco de mentira como estava ANTES das colunas novas: tira as `n` últimas colunas de cada linha."""
    a = api.abas[(livro, aba)]
    a["linhas"] = [{"headers": l["headers"][:-n], "values": l["values"][:-n]} for l in a["linhas"]]


def test_historico_aceita_o_livro_do_app_sem_as_colunas_novas():
    """O Nexus sobe antes do App (30/10/2026): com os livros de hoje, sem Criticidade, Curva ABC nem Custo unitário, a
    carga grava as colunas novas VAZIAS (nada de 0 nem de C), e nada mais muda."""
    from nexus.dados import carga
    api = _api()
    r = carga.gerar_almoxarifado(CFG, api)
    assert "nao_aplica" not in r and set(r["gravado"]) == {MES, ALMOX_LIVRO}, r
    saldo, itens = api.linhas(MES, "fato_saldo_almox"), api.linhas(ALMOX_LIVRO, "dim_item_almox")
    assert len(saldo) == 3 and all("custo_unitario_brl" in l and l["custo_unitario_brl"] is None for l in saldo)
    assert len(itens) == 2 and all(l["criticidade"] is None and l["curva_abc"] is None for l in itens)


def test_linha_velha_sem_a_coluna_convive_com_a_nova_no_historico():
    """O livro é republicado inteiro (`livros.publicar`): a foto do mês e a dimensão que já estão no banco SEM as colunas
    novas voltam com elas vazias, e a foto do ciclo novo traz o custo, a criticidade e a curva do Fracttal."""
    from nexus.dados import carga
    api = _api()
    carga.gerar_almoxarifado(CFG, api)                                    # o ciclo de 25/10, do App de antes
    _sem_as_colunas(api, MES, "fato_saldo_almox", 1)                      # e o banco como estava: sem o custo
    _sem_as_colunas(api, ALMOX_LIVRO, "dim_item_almox", 2)                # nem a criticidade e a curva
    assert "custo_unitario_brl" not in api.linhas(MES, "fato_saldo_almox")[0]
    _semear(api, inicio="2026-10-26T03:00:12Z", colunas_novas=True)       # o ciclo seguinte, do App de depois
    r = carga.gerar_almoxarifado(CFG, api)
    assert "nao_aplica" not in r and set(r["gravado"]) == {MES, ALMOX_LIVRO}, r
    saldo = api.linhas(MES, "fato_saldo_almox")
    assert len(saldo) == 6 and all("custo_unitario_brl" in l for l in saldo)
    velhas = [l for l in saldo if l["ciclo_inicio"] == INICIO]
    novas = {(l["id_item"], l["id_almoxarifado"]): l["custo_unitario_brl"] for l in saldo if l["ciclo_inicio"] != INICIO}
    assert len(velhas) == 3 and all(l["custo_unitario_brl"] is None for l in velhas)
    assert novas == {("1", "123021"): 15.5, ("2", "123021"): None, ("1", "123675"): None}
    itens = {l["id_item"]: l for l in api.linhas(ALMOX_LIVRO, "dim_item_almox")}
    assert (itens["1"]["criticidade"], itens["1"]["curva_abc"]) == ("1.Crítico", "A")
    assert (itens["2"]["criticidade"], itens["2"]["curva_abc"]) == (None, None)


def test_peca_nova_sem_ciclo_novo_grava_so_o_livro_do_nexus():
    from nexus.dados import carga
    from test_campo_visao import _aba
    api = _api()
    carga.gerar_almoxarifado(CFG, api)
    _aba(api, A.LIVRO_PECAS, A.ABA_PECAS, [_peca("A", "lançada"), _peca("B", "recusada", "sem permissão")])
    r = carga.gerar_almoxarifado(CFG, api)
    assert set(r["gravado"]) == {ALMOX_LIVRO} and len(api.linhas(ALMOX_LIVRO, "fato_peca_lancada")) == 2
    assert len(api.linhas(MES, "fato_saldo_almox")) == 3


def test_releitura_no_mesmo_dia_vira_outra_foto():
    from nexus.dados import carga
    api = _api()
    carga.gerar_almoxarifado(CFG, api)
    _semear(api, inicio="2026-10-25T18:40:00Z")
    carga.gerar_almoxarifado(CFG, api)
    assert len(api.linhas(MES, "fato_saldo_almox")) == 6
    assert [c["situacao"] for c in api.linhas(ALMOX_LIVRO, "fato_ciclo_varredura")] == ["aplicado", "aplicado"]


def test_ciclo_incompleto_e_recusado():
    from nexus.dados import carga
    api = _api(lidos=8, total=10)
    r = carga.gerar_almoxarifado(CFG, api)
    assert set(r["gravado"]) == {ALMOX_LIVRO} and not api.linhas(MES, "fato_saldo_almox")
    c = api.linhas(ALMOX_LIVRO, "fato_ciclo_varredura")[0]
    assert c["situacao"] == "recusado" and "8 de 10" in c["porque"]


def test_livros_de_ciclos_diferentes_nao_aplicam():
    from nexus.dados import carga
    api = _api(saldo_inicio="2026-10-24T03:00:05Z")
    r = carga.gerar_almoxarifado(CFG, api)
    assert r["incoerente"] and not api.linhas(MES, "fato_saldo_almox")
    assert not api.linhas(ALMOX_LIVRO, "fato_ciclo_varredura")       # nenhum ciclo a registrar; as peças, sim
    assert len(api.linhas(ALMOX_LIVRO, "fato_peca_lancada")) == 1


def test_leitura_vazia_do_livro_existente_nao_grava():
    from nexus.dados import carga
    api = _api()
    carga.gerar_almoxarifado(CFG, api)
    for aba in ("fato_ciclo_varredura", "fato_peca_lancada"):              # a leitura veio vazia por um instante
        api.abas[(ALMOX_LIVRO, aba)]["linhas"] = []
    _semear(api, inicio="2026-10-26T03:00:12Z")
    syncs = api.syncs
    r = carga.gerar_almoxarifado(CFG, api)
    assert "nao_grava" in r and api.syncs == syncs


def test_listagem_sem_as_abas_do_livro_e_recusada():
    """A listagem do banco omitiu as abas do nexus_almoxarifado por um instante: parece livro novo, e gravar trocaria o
    histórico; a trava do `livros.publicar` (so_cresce) recusa."""
    import pytest
    from nexus.dados import carga, livros
    api = _api()
    carga.gerar_almoxarifado(CFG, api)
    api.omitir.add(ALMOX_LIVRO)
    _semear(api, pecas=[_peca("A", "lançada"), _peca("B", "lançada")])
    with pytest.raises(livros.GravacaoRecusada):
        carga.gerar_almoxarifado(CFG, api)


def test_mes_gravado_e_marca_que_falhou_nao_duplica_a_foto():
    """O livro do mês grava antes da marca (o nexus_almoxarifado); se a marca falhou, a hora seguinte vê o ciclo como
    novo e grava de novo: a foto do mesmo ciclo troca, não duplica."""
    from nexus.dados import carga
    api = _api()
    carga.gerar_almoxarifado(CFG, api)
    api.abas[(ALMOX_LIVRO, "fato_ciclo_varredura")]["linhas"] = []         # a marca não ficou
    carga.gerar_almoxarifado(CFG, api)
    assert len(api.linhas(MES, "fato_saldo_almox")) == 3


def test_livro_do_mes_tem_a_trava_do_catalogo():
    from nexus.dados import livros
    assert livros._so_cresce(MES) == ("fato_saldo_almox",)


def test_como_texto():
    from nexus.dados import carga
    api = _api(como_texto=True, txt=True)
    carga.gerar_almoxarifado(CFG, api)
    assert "pulou" in carga.gerar_almoxarifado(CFG, api)             # o ciclo lido de volta como texto é o mesmo
    _semear(api, inicio="2026-10-26T03:00:12Z", txt=True)
    carga.gerar_almoxarifado(CFG, api)
    assert len(api.linhas("nexus_almoxarifado_saldo_2026_10", "fato_saldo_almox")) == 6
    assert len(api.linhas(ALMOX_LIVRO, "fato_peca_lancada")) == 1


def test_anular_marca_sem_apagar():
    from nexus.dados import carga
    api = _api()
    carga.gerar_almoxarifado(CFG, api)
    n = len(api.linhas(MES, "fato_saldo_almox"))
    r = carga.anular_ciclo_almox(CFG, INICIO, api, gravar=True)
    assert r["anulado"] == INICIO
    c = api.linhas(ALMOX_LIVRO, "fato_ciclo_varredura")[0]
    assert str(c["anulado"]) == "1" and len(api.linhas(MES, "fato_saldo_almox")) == n
    assert "nao_achou" in carga.anular_ciclo_almox(CFG, "2026-01-01T00:00:00Z", api, gravar=True)


def test_a_chave_da_gravacao_vem_do_env():
    from pathlib import Path
    from nexus import config
    assert "NEXUS_ALMOX_GRAVAR" in config.OPCIONAIS
    assert "NEXUS_ALMOX_GRAVAR=" in Path(__file__).resolve().parent.parent.joinpath(".env.example").read_text("utf-8")


# ── a usina dos almoxarifados na Ligação e a qualidade na Governança ───────────────────────────────────────────────

def test_local_de_almoxarifado_entra_na_ligacao():
    """O local que a Classificação 1 já tem não repete; o que ela não tem (a Nobres, sem Classificação 1 nas tarefas)
    entra com a origem, para ligar à mão em Base → Ligações."""
    from nexus.cadastro import ligacoes as L
    saldo = [_saldo(1, 5, IRC, 1, 1), _saldo(2, 5, IRC, 1, 1), _saldo(1, 6, NOB, 1, 1), _saldo(1, 7, "Almoxarifado", 1, 1)]
    novos = L.locais_de_almoxarifado(saldo, {"Greenyellow - Irecê 1 - BA"})
    assert novos == [{"chave": "RenoGrid - Nobres 1 - MT", "nome": "RenoGrid - Nobres 1 - MT",
                      "origem": "local de almoxarifado"}]


def test_fontes_da_ligacao_le_os_locais_do_livro_do_app(monkeypatch):
    import requests
    from pg_falso import ApiPGFalsa
    from test_campo_visao import _aba
    from nexus.cadastro import ligacoes as L
    api = ApiPGFalsa()
    for _s, wb, aba, *_r in L.FONTES_API:
        _aba(api, wb, aba, [])
    for _s, wb, ref in L.FONTES_ABA:
        _aba(api, wb, ref, [])
    _aba(api, A.LIVRO_SALDO, A.ABA_SALDO, [_saldo(1, 5, IRC, 1, 1), _saldo(1, 6, NOB, 1, 1)])
    monkeypatch.setattr(requests, "get", api.get)
    monkeypatch.setattr(L, "fracttal", lambda config: [{"chave": "Greenyellow - Irecê 1 - BA",
                                                         "nome": "Greenyellow - Irecê 1 - BA"}])
    fs = L.fontes({"GRIDCO_DB_API": BASE})
    assert [i["chave"] for i in fs[L.FRACTTAL]] == ["Greenyellow - Irecê 1 - BA", "RenoGrid - Nobres 1 - MT"]


def test_governanca_le_a_qualidade_do_almoxarifado(app, monkeypatch):
    from pg_falso import ApiPGFalsa
    from test_campo_visao import _aba
    from nexus.dados import fatos
    from nexus.dados import telas as T
    api = ApiPGFalsa()
    q = dict(zip(fatos.CAB_QUALIDADE, [None] * len(fatos.CAB_QUALIDADE)), fato="saldo_almox", linhas=3)
    _aba(api, "nexus_almoxarifado", "qualidade", [q])
    app.config.update(GRIDCO_DB_API=BASE)
    app.extensions["nexus_dados_sessao"] = api
    monkeypatch.setitem(T._CACHE, "v", None)
    with app.app_context():
        v = T._ultima_qualidade()
    assert v["qualidade"]["saldo_almox"]["linhas"] == 3, v.get("erro")


# ── a revisão final (25/10/2026): cada teste reproduz um achado e falhou antes do conserto ──────────────────────────

def test_rev_i1_livros_incompletos_nao_aplicam_e_nao_ficam_vistos():
    """Itens com menos linhas que a lista do ciclo, ou Saldo com menos linhas que o ciclo diz: o Nexus leu no meio da
    publicação (ou o App subiu pela metade). Não aplica NESTA hora e não marca o ciclo como visto: a hora seguinte, com
    os livros inteiros, aplica."""
    from nexus.dados import carga
    assert A.conferir_ciclo([_ciclo(2, 2)], [{"Início do ciclo": INICIO, "Lido": "Sim"}],
                            [{"Início do ciclo": INICIO}]).startswith("o livro de itens tem 1 de 2")
    api = _api(itens_faltando=1)
    r = carga.gerar_almoxarifado(CFG, api)
    assert "incompletos" in r["nao_aplica"] and not api.linhas(MES, "fato_saldo_almox")
    assert not api.linhas(ALMOX_LIVRO, "fato_ciclo_varredura")
    _semear(api)                                                       # chegaram inteiros
    carga.gerar_almoxarifado(CFG, api)
    assert len(api.linhas(MES, "fato_saldo_almox")) == 3
    api2 = _api(linhas_saldo=5)                                        # o Saldo veio com 3 das 5 linhas
    assert "o livro de saldo tem 3 de 5" in carga.gerar_almoxarifado(CFG, api2)["nao_aplica"]


def test_rev_i1_queda_de_itens_vai_na_qualidade():
    from nexus.dados import carga
    api = _api(total=10)
    carga.gerar_almoxarifado(CFG, api)
    _semear(api, inicio="2026-10-26T03:00:12Z", total=4)              # o Fracttal listou 4 dos 10 de ontem
    r = carga.gerar_almoxarifado(CFG, api)
    assert r["queda_itens"] == {"antes": 10, "agora": 4}
    q = {l["fato"]: l for l in api.linhas(ALMOX_LIVRO, "qualidade")}
    assert '"queda_itens"' in q["ciclo_varredura"]["extra"]


def test_rev_i2_saldo_vazio_e_nao_informado():
    assert A.situacao(None, 2) == A.situacao("", 2) == A.situacao("", 0) == "nao_informado"
    assert A.situacao(0, 2) == "abaixo"


def test_rev_i3_nao_lidos_no_ciclo_e_na_qualidade():
    from nexus.dados import carga
    api = _api(total=10, lidos=9)
    carga.gerar_almoxarifado(CFG, api)
    c = api.linhas(ALMOX_LIVRO, "fato_ciclo_varredura")[0]
    assert str(c["nao_lidos_qtd"]) == "1"
    q = {l["fato"]: l for l in api.linhas(ALMOX_LIVRO, "qualidade")}
    assert '"nao_lidos":1' in q["ciclo_varredura"]["extra"]


def test_rev_i4_o_mes_corrente_e_religado():
    """A Nobres ligada em Base → Ligações depois da 1ª foto: a foto do mesmo mês ganha a usina na gravação seguinte."""
    from nexus.dados import carga
    api = _api()
    carga.gerar_almoxarifado(CFG, api)
    sem = [l for l in api.linhas(MES, "fato_saldo_almox") if str(l["id_almoxarifado"]) == "123675"]
    assert sem and all(l["usina_id"] in (None, "") for l in sem)
    nob = {"usina_id": 9, "sistema": "Fracttal · Classificação 1", "chave_externa": "RenoGrid - Nobres 1 - MT"}
    _semear(api, inicio="2026-10-26T03:00:12Z", de_para=DE_PARA_IRC + [nob])
    carga.gerar_almoxarifado(CFG, api)
    nobres = [l for l in api.linhas(MES, "fato_saldo_almox") if str(l["id_almoxarifado"]) == "123675"]
    assert len(nobres) == 2 and all(str(l["usina_id"]) == "9" for l in nobres)


def test_rev_i4_de_para_vazio_nao_grava():
    from nexus.dados import carga
    api = _api(de_para=[])
    r = carga.gerar_almoxarifado(CFG, api)
    assert "de-para" in r["nao_grava"] and api.syncs == 0


def test_rev_i7_saldo_id_repetido_recusa_a_foto_e_o_ensaio_mede():
    from nexus.dados import carga
    api = _api(saldo_extra=[_saldo(1, 123021, IRC, 4, 2)])             # o item 1 no almoxarifado 123021 duas vezes
    r = carga.gerar_almoxarifado({k: v for k, v in CFG.items() if k != "NEXUS_ALMOX_GRAVAR"}, api, medir=True)
    assert r["saldo_repetidos"] == 1 and "pct_usina" in r and r["ensaio"]
    r = carga.gerar_almoxarifado(CFG, api)
    assert "chave repetida" in r["recusado"] and not api.linhas(MES, "fato_saldo_almox")


def test_rev_m1_sem_ciclo_e_sem_peca_nao_cria_o_livro():
    from nexus.dados import carga
    api = _api(saldo_inicio="2026-10-24T03:00:05Z", pecas=[])
    r = carga.gerar_almoxarifado(CFG, api)
    assert "pulou" in r and api.syncs == 0 and ALMOX_LIVRO not in api.workbooks

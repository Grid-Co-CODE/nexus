"""Os avariados na contagem do inventário (30/10/2026, item 5 das melhorias do Almoxarifado). Desenho:
docs/superpowers/specs/2026-10-30-almoxarifado-melhorias-design.md, seção "5. Avariados na contagem". O técnico lista na
aba Avariados do App as unidades avariadas de uma peça BOA do catálogo: a linha chega com o Tipo `avariado` e o ID e o
Código da boa, e o Nexus a leva à peça `<código da boa>-AV` (`avariados.resolver`, aplicado UMA vez na `leitura.ler`). Sem
o -AV no catálogo do App, a linha fica `avariado` e vai à curadoria. Dado de mentira: códigos, nomes e IDs inventados, sem
nome de gente."""
import copy

import pytest
from test_campo_visao import _aba, banco  # noqa: F401  (banco é fixture)
from test_pcm_inventario_leitura import _iso, _linha, _publicar, inv  # noqa: F401  (inv é fixture)

from nexus.dados import almoxarifado as A
from nexus.dados import fato_inventario as F
from nexus.pcm.inventario import avariados as AV
from nexus.pcm.inventario import contas
from nexus.pcm.inventario import leitura as L

# o catálogo do App como a `leitura` o monta ({id_item: {codigo, nome, unidade}}, a unidade em minúsculas)
BOM = {"codigo": "SP-3", "nome": "Disjuntor 16A", "unidade": "unidade"}
O_AV = {"codigo": "SP-3-AV", "nome": "[AVARIADO] Disjuntor 16A", "unidade": "unidade"}
CATALOGO = {"3": BOM, "33": O_AV, "5": {"codigo": "SP-5", "nome": "Cabo 6 mm", "unidade": "metro"}}


def _l(id_linha, tipo="avariado", id_item="3", codigo="SP-3", contado="2", **mais):
    l = dict.fromkeys(A.COLUNAS_CONTAGENS, "")
    l.update({"ID da contagem": "C-1", "ID do almoxarifado": "10", "Tipo": tipo, "ID do item": id_item, "Código": codigo,
              "Contado": contado, "ID da linha": id_linha})
    l.update(mais)
    return l


# ── o código e o nome do -AV ─────────────────────────────────────────────────────────────────────────────────────────
def test_codigo_av():
    assert AV.codigo_av(" sp-3 ") == "SP-3-AV"
    assert AV.codigo_av("SP- 3") == "SP-3-AV"                 # sem espaço nenhum: o código do Fracttal não tem
    assert AV.codigo_av("SP-CAB-004") == "SP-CAB-004-AV"
    assert AV.codigo_av("sp-3-av") == "SP-3-AV"               # o -AV de um -AV é ele mesmo (nunca SP-3-AV-AV)
    for vazio in ("", "  ", None):
        assert AV.codigo_av(vazio) == ""                      # sem o código da boa não há -AV


def test_nome_av_no_padrao_dos_av_do_catalogo():
    """O padrão lido dos -AV do livro Itens do App em 30/10/2026: "[AVARIADO] " antes do nome da boa."""
    assert AV.nome_av("Disjuntor 16A") == "[AVARIADO] Disjuntor 16A"
    assert AV.nome_av("  Cabo   6 mm ") == "[AVARIADO] Cabo 6 mm"
    assert AV.nome_av("") == "" and AV.nome_av(None) == ""
    assert AV.nome_av("[AVARIADO] Disjuntor 16A") == "[AVARIADO] Disjuntor 16A"     # não marca duas vezes


# ── o resolver ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_resolver_acha_o_av():
    """A linha avariada da SP-3, com a SP-3-AV no catálogo: vira linha de peça (Tipo `item`) da SP-3-AV, com a marca de
    qual era a boa; o resto da linha (o contado, o ID da linha) fica como veio."""
    (r,) = AV.resolver([_l("L1")], CATALOGO)
    assert (r["Tipo"], r["ID do item"], r["Código"], r["_avariado_de"]) == ("item", "33", "SP-3-AV", "3")
    assert (r["Contado"], r["ID da linha"], r["ID da contagem"]) == ("2", "L1", "C-1")


def test_resolver_sem_av_fica_avariado():
    """Sem a SP-3-AV no catálogo, a linha fica `avariado` (a curadoria decide), com o que o cadastro da curadoria precisa: o
    código -AV que falta, o nome no padrão dos -AV e a unidade da boa."""
    so_o_bom = {"3": BOM, "5": CATALOGO["5"]}
    (r,) = AV.resolver([_l("L1")], so_o_bom)
    assert (r["Tipo"], r["ID do item"], r["Código"]) == ("avariado", "3", "SP-3")
    assert "_avariado_de" not in r
    assert (r["_codigo_av"], r["_nome_av"], r["_unidade_av"]) == ("SP-3-AV", "[AVARIADO] Disjuntor 16A", "UNIDADE")
    (r,) = AV.resolver([_l("L2", id_item="5", codigo="SP-5")], so_o_bom)
    assert (r["_codigo_av"], r["_unidade_av"]) == ("SP-5-AV", "METRO")
    # a boa que nem está no catálogo do App: o código da linha ainda dá o -AV; o nome e a unidade ficam por dizer
    (r,) = AV.resolver([_l("L3", id_item="9", codigo="SP-9")], so_o_bom)
    assert (r["Tipo"], r["_codigo_av"], r["_nome_av"], r["_unidade_av"]) == ("avariado", "SP-9-AV", "", "")


def test_resolver_nao_mexe_nas_outras():
    linhas = [_l("L1", tipo="item", id_item="5", codigo="SP-5"),
              _l("L2", tipo="identificar", id_item="5", codigo="SP-5", **{"Identificado como": "3"}),
              _l("L3", tipo="fora_do_catalogo", id_item="", codigo="", Descrição="peça sem etiqueta"),
              _l("L4", tipo="item", id_item="33", codigo="SP-3-AV"),          # o -AV contado direto continua item
              _l("L5")]
    antes = copy.deepcopy(linhas)
    saida = AV.resolver(linhas, CATALOGO)
    assert linhas == antes                                       # o que entrou não muda (a cópia de 5 min é de todos)
    assert saida[:4] == linhas[:4] and all(s is not l for s, l in zip(saida, linhas))       # cópias
    assert saida[4]["ID do item"] == "33"
    assert AV.resolver([], CATALOGO) == [] and AV.resolver(None, CATALOGO) == []


def test_resolver_sem_caixa():
    """O código casa sem caixa e sem espaço, dos dois lados; o ID com ".0" da API acha a boa."""
    cat = {"3": {"codigo": " sp-3", "nome": "Disjuntor", "unidade": ""}, "33": {"codigo": "Sp-3-av ", "nome": "x", "unidade": ""}}
    (r,) = AV.resolver([_l("L1", id_item="3.0", codigo="sp-3", Tipo="AVARIADO")], cat)
    assert (r["Tipo"], r["ID do item"], r["Código"], r["_avariado_de"]) == ("item", "33", "Sp-3-av", "3")


def test_resolver_pelo_id_da_boa_e_pelo_codigo_da_linha():
    """O código da boa vem do catálogo pelo ID (o ID é a chave; o código da linha é a cópia do App, que pode estar velha), e
    sem o ID no catálogo, do Código da linha."""
    (r,) = AV.resolver([_l("L1", codigo="CODIGO-VELHO")], CATALOGO)
    assert r["ID do item"] == "33"
    (r,) = AV.resolver([_l("L2", id_item="", codigo="SP-3")], CATALOGO)
    assert (r["ID do item"], r["_avariado_de"]) == ("33", "")


def test_resolver_com_dois_av_do_mesmo_codigo_nao_escolhe():
    """Dois itens do catálogo com o mesmo código -AV: escolher um seria chutar o ID. A linha fica para a curadoria, marcada
    `_av_repetido` (a curadoria diz que o código se repete e não cadastra outro)."""
    cat = dict(CATALOGO, **{"34": {"codigo": "SP-3-AV", "nome": "outro", "unidade": ""}})
    (r,) = AV.resolver([_l("L1")], cat)
    assert r["Tipo"] == "avariado" and r["_codigo_av"] == "SP-3-AV" and r["_av_repetido"] is True
    (r,) = AV.resolver([_l("L1")], {"3": BOM})
    assert r["_av_repetido"] is False


def test_resolver_sem_o_id_da_boa_vai_pelo_codigo():
    """A avariada sem o ID da boa: o Código da linha acha o -AV; sem o -AV, a curadoria leva o `codigo_av` dele. O "None" que o
    `sync-xlsx` escreve no lugar do vazio não é código."""
    (r,) = AV.resolver([_l("L1", id_item="", codigo="SP-5")], CATALOGO)
    assert (r["Tipo"], r["_codigo_av"], r["_nome_av"]) == ("avariado", "SP-5-AV", "")
    for vazio in ("", "None", "none"):
        (r,) = AV.resolver([_l("L2", id_item="", codigo=vazio)], CATALOGO)
        assert (r["Tipo"], r["_codigo_av"]) == ("avariado", "")
        assert AV.codigo_da_linha(r) == ""
    assert AV.codigo_da_linha(_l("L3", codigo=" sp-3 ")) == "sp-3"


def test_resolver_sem_o_catalogo_lido():
    """O catálogo do App que não se leu agora (`itens` None) não é catálogo vazio: a avariada não se resolve e fica marcada
    `_sem_catalogo` (a leitura põe o aviso na contagem dela, e a curadoria não a oferece); as outras linhas saem iguais."""
    linhas = [_l("L1"), _l("L2", tipo="item", id_item="5", codigo="SP-5")]
    a, b = AV.resolver(linhas, None)
    assert (a["Tipo"], a["_sem_catalogo"], a["ID do item"]) == ("avariado", True, "3") and "_codigo_av" not in a
    assert b == linhas[1] and "_sem_catalogo" not in b
    (r,) = AV.resolver([_l("L1")], {})                            # lido e vazio: a curadoria decide
    assert "_sem_catalogo" not in r and r["_codigo_av"] == "SP-3-AV"


def test_o_modulo_e_puro():
    """Como as contas: dicts entram, dicts saem (a leitura chama; o resolver não chama ninguém)."""
    import ast
    from pathlib import Path
    arvore = ast.parse(Path(AV.__file__).read_text("utf-8"))
    importados = {a.name for no in ast.walk(arvore) if isinstance(no, ast.Import) for a in no.names}
    importados |= {no.module or "" for no in ast.walk(arvore) if isinstance(no, ast.ImportFrom)}
    assert not {m.split(".")[0] for m in importados} & {"flask", "requests", "os", "pathlib", "json", "threading"}


# ── a leitura resolve uma vez, e a lista e o lote contam igual ───────────────────────────────────────────────────────
def _itens_do_app(api, *itens):
    _aba(api, A.LIVRO_ITENS, A.ABA_ITENS, [{"ID do item": i, "Código": c, "Nome": n, "Unidade": "UNIDADE", "Família": "Teste",
                                            "Avariado": "Não", "Ferramenta": "Não", "Início do ciclo": "x", "Lido": "Sim"}
                                           for i, c, n in itens])


def test_a_leitura_resolve_as_linhas_uma_vez(app, inv):  # noqa: F811
    """`leitura.ler` entrega as linhas já resolvidas: o lote, a curadoria e as contas da lista veem o mesmo. A avariada com o
    -AV no catálogo é peça contada; a sem o -AV é da curadoria; a em branco é em branco."""
    _itens_do_app(inv, ("501", "SP-501", "Fusível"), ("591", "SP-501-AV", "[AVARIADO] Fusível"), ("502", "SP-502", "Relé"))
    _publicar(inv,
              _linha("C-1", "L1", "501", "5"),
              _linha("C-1", "L2", "501", "2", tipo="avariado"),               # vira a SP-501-AV
              _linha("C-1", "L3", "502", "1", tipo="avariado"),               # a SP-502-AV não existe: curadoria
              _linha("C-1", "L4", "502", "", tipo="avariado"))                # em branco: nada a decidir
    lido = L.ler(app.config)
    c = lido["contagens"][0]
    por_linha = {l["ID da linha"]: l for l in c["linhas"]}
    assert (por_linha["L2"]["Tipo"], por_linha["L2"]["ID do item"], por_linha["L2"]["_avariado_de"]) == ("item", "591", "501")
    assert por_linha["L3"]["Tipo"] == "avariado" and por_linha["L3"]["_codigo_av"] == "SP-502-AV"
    assert (c["n_contadas"], c["n_em_branco"], c["n_curadoria"]) == (2, 1, 1)
    lote = contas.itens_do_lote(c["linhas"], {}, L.curadoria_da(app.config, "C-1"), {})
    assert [i["id_item"] for i in lote] == ["501", "591", ""]
    assert sum(len(i["pendentes"]) for i in lote if i["situacao"] == "curadoria") == c["n_curadoria"]
    # a decisão da curadoria leva a avariada sem cadastro a uma peça, e a lista conta como contada
    F.acrescentar(app.config, F.ABA_CURADORIA, [{"contagem_id": "C-1", "chave_linha": "L3", "decisao": "e_a_peca",
                                                 "id_item": "592"}])
    c = L.ler(app.config)["contagens"][0]
    assert (c["n_contadas"], c["n_em_branco"], c["n_curadoria"]) == (3, 1, 0)


def test_a_leitura_nao_estraga_a_copia_com_a_resolucao(app, inv):  # noqa: F811
    """A cópia de 5 min do livro do App é de todos: a resolução sai em cópias, e a próxima leitura parte do livro como veio."""
    _itens_do_app(inv, ("501", "SP-501", "Fusível"), ("591", "SP-501-AV", "[AVARIADO] Fusível"))
    _publicar(inv, _linha("C-1", "L2", "501", "2", tipo="avariado"))
    assert L.ler(app.config)["contagens"][0]["linhas"][0]["ID do item"] == "591"
    crua = L._app()["contagens"][0]["linhas"][0]
    assert (crua["Tipo"], crua["ID do item"]) == ("avariado", "501") and "_avariado_de" not in crua
    assert L.ler(app.config)["contagens"][0]["linhas"][0]["ID do item"] == "591"


def _itens_sem_ler(monkeypatch):
    """O livro Itens do App que não se lê agora (o banco caiu só nele); os outros livros respondem."""
    from nexus.campo import visao
    original = visao._livro

    def livro(nome, aba=None):
        if nome == A.LIVRO_ITENS:
            raise ConnectionError("banco fora")
        return original(nome, aba)
    monkeypatch.setattr(visao, "_livro", livro)
    visao.limpar()


def test_catalogo_que_nao_leu_trava_so_a_contagem_com_avariada(app, inv, monkeypatch):  # noqa: F811
    """O catálogo do App que falhou não vira catálogo vazio (a falha ficaria na cópia de 5 min, e cada avariada que acha o -AV
    viraria "sem cadastro", e a linha direta do -AV contaria sozinha, sem a trava do dobro). A contagem COM avariada ganha o aviso
    e não se aprova até o catálogo ser lido; a sem avariada segue. O aviso não é do App (não é contrato violado): ela continua
    valendo como a mais nova do almoxarifado, e a velha segue substituída."""
    _itens_do_app(inv, ("501", "SP-501", "Fusível"), ("591", "SP-501-AV", "[AVARIADO] Fusível"))
    _publicar(inv,
              _linha("C-0", "K1", "501", "4", contada=_iso(dias_atras=2), enviada=_iso(dias_atras=2)),
              _linha("C-1", "L1", "591", "1"), _linha("C-1", "L2", "501", "2", tipo="avariado"),
              _linha("C-2", "M1", "501", "3", almox="20"))
    _itens_sem_ler(monkeypatch)
    por = {c["contagem_id"]: c for c in L.contagens(app.config)}
    c1 = por["C-1"]
    assert "o catálogo do App não foi lido agora" in c1["aviso"] and c1["aviso_do_app"] is False
    assert not c1["aprovavel"] and "catálogo do App" in c1["motivo_nao_aprovavel"]
    assert [l.get("_sem_catalogo") for l in c1["linhas"]] == [None, True]
    assert (por["C-2"]["aviso"], por["C-2"]["aprovavel"]) == ("", True)
    assert por["C-0"]["estado"] == "substituida"
    # lido de novo, a avariada se resolve e a contagem volta a se aprovar
    monkeypatch.undo()
    from nexus.campo import visao
    visao.limpar()
    c1 = next(c for c in L.contagens(app.config) if c["contagem_id"] == "C-1")
    assert (c1["aviso"], c1["aprovavel"], c1["linhas"][1]["ID do item"]) == ("", True, "591")


def test_catalogo_lido_e_vazio_nao_trava(app, inv):  # noqa: F811
    """O livro Itens lido e vazio (ou que o App ainda não publicou) é catálogo sem o -AV: a avariada vai à curadoria, sem aviso."""
    _itens_do_app(inv)
    _publicar(inv, _linha("C-1", "L2", "501", "2", tipo="avariado"))
    c = L.contagens(app.config)[0]
    assert (c["aviso"], c["aprovavel"], c["n_curadoria"]) == ("", True, 1)


def test_avariada_sem_id_e_sem_codigo_e_contrato_violado(app, inv):  # noqa: F811
    """A avariada sem o ID da boa vai pelo Código (sem o -AV, a curadoria); sem o ID E sem o Código não é de peça nenhuma, e sumir
    com ela em silêncio esconderia unidades contadas: a contagem ganha o aviso do App, como a linha sem ID da linha."""
    _itens_do_app(inv, ("501", "SP-501", "Fusível"))
    _publicar(inv, _linha("C-1", "L1", "", "2", tipo="avariado", **{"Código": "SP-501"}),
              _linha("C-2", "M1", "", "2", tipo="avariado", almox="20", **{"Código": "None"}))
    por = {c["contagem_id"]: c for c in L.contagens(app.config)}
    assert (por["C-1"]["aviso"], por["C-1"]["aprovavel"], por["C-1"]["n_curadoria"]) == ("", True, 1)
    assert por["C-1"]["linhas"][0]["_codigo_av"] == "SP-501-AV"
    c2 = por["C-2"]
    assert c2["aviso"] == "o App mandou avariada sem o ID nem o Código da peça boa" and c2["aviso_do_app"] is True
    assert not c2["aprovavel"] and c2["motivo_nao_aprovavel"] == "avariada sem o ID nem o Código da peça boa"


@pytest.mark.parametrize("tipo", A.TIPOS_CONTAGEM)
def test_todo_tipo_do_contrato_passa_pelo_resolver(tipo):
    (r,) = AV.resolver([_l("L1", tipo=tipo)], CATALOGO)
    assert r["Tipo"] == ("item" if tipo == "avariado" else tipo)

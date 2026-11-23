"""A declaração do técnico sobre o almoxarifado da usina (23/11/2026): o App grava, o PCM confirma no Nexus.

O PCM, 23/11/2026: "quando o técnico botar que não tem almoxarifado, mostra aqui para mim no inventário" e "no app de campo
[...] botar que a usina é compartilhada e botar qual usina ela compartilha". O Levi decidiu (23/11/2026, no chat do Nexus
PCM): a declaração NÃO tira a cobrança do App nem dá pontos; quem decide é o PCM, que confirma (ou marca Próprio) em
Usinas e almoxarifados; e o Nexus publica a lista das usinas por cliente, de onde o App tira a dona do "compartilha".

O que estes testes seguram:
- o contrato do livro que o App grava (`almoxarifado_declaracoes_app_campo · Declaracoes`, as 11 colunas na ordem), registrado
  no catálogo antes da 1ª gravação;
- a lista das usinas para o App (`nexus_almoxarifado_usinas · dim_usina_cliente`): o grupo do cliente (a usina sem o cliente no
  cadastro entra no grupo do cliente do mesmo 1º nó do local no Fracttal), publicada a cada marcação e pelo botão da tela
  quando está velha;
- as declarações a confirmar no Inventário: a última de cada usina, enquanto o PCM não decidiu depois dela e a marcação não é
  já a declarada; o Confirmar e o Próprio pela rota da marcação, que volta ao Inventário.
Dado de mentira (o mesmo cadastro dos testes das Usinas e almoxarifados), sem nome de gente."""
import json

from test_campo_visao import _aba, banco  # noqa: F401  (banco é fixture)
from test_pcm_almox_usinas import _livro, _marcar, _pcm, au  # noqa: F401  (au é fixture)

from nexus.campo import visao
from nexus.dados import almox_usinas as AU
from nexus.dados import almoxarifado as A
from nexus.dados import catalogo
from nexus.pcm import almox_declaracoes as DC
from nexus.pcm import almox_usinas as P

INVENTARIO = "/t/pcm/pecas/inventario"
TECNICO = "a" * 24


def _decl(i, usina, situacao, dona="", quando="2026-11-23T12:00:00Z", **mais):
    linha = dict.fromkeys(A.COLUNAS_DECLARACOES, "")
    linha.update({"ID da declaração": f"D-{i}", "Declarada em": quando, "Hora do celular": quando, "Usina": usina,
                  "Situação": situacao, "Usina dona": dona, "Técnico (HMAC)": TECNICO, "Versão do App": "v380"})
    linha.update(mais)
    return linha


def _publicar_decl(banco, *linhas):  # noqa: F811
    _aba(banco, A.LIVRO_DECLARACOES, A.ABA_DECLARACOES, list(linhas))
    visao.limpar()


# ── o contrato e o catálogo ─────────────────────────────────────────────────────────────────────────────────────────
def test_o_contrato_do_livro_do_app():
    assert (A.LIVRO_DECLARACOES, A.ABA_DECLARACOES) == ("almoxarifado_declaracoes_app_campo", "Declaracoes")
    assert A.COLUNAS_DECLARACOES == ("ID da declaração", "Declarada em", "Hora do celular", "Usina", "Situação",
                                     "Usina dona", "Técnico (HMAC)", "ID da contagem", "ID do almoxarifado", "Observação",
                                     "Versão do App")
    fato = next(f for f in catalogo.FATOS if f.livro == f"{A.LIVRO_DECLARACOES} · {A.ABA_DECLARACOES}")
    assert fato.chave == ("ID da declaração",) and "1 linha = 1 declaração" in fato.grao


def test_a_lista_das_usinas_para_o_app_e_registrada():
    assert AU.ABA_LISTA == "dim_usina_cliente" and AU.ABA_LISTA in AU.ABAS
    assert AU.CAB_LISTA == ("usina_id", "usina", "cliente_id", "grupo_cliente")
    livro = next(l for l in catalogo.LIVROS if l.nome == AU.LIVRO)
    assert AU.ABA_LISTA in livro.abas


# ── a lista das usinas por cliente ──────────────────────────────────────────────────────────────────────────────────
def test_o_grupo_do_cliente_segue_a_regra_da_dona(au):  # noqa: F811
    b = visao._Base()
    lista = {l["usina_id"]: l for l in P.lista_para_o_app(P.usinas_com_fracttal(b))}
    assert set(lista) == {1, 2, 3, 4}                   # a 5 não tem o local no Fracttal; a 6 está excluída
    assert lista[1]["grupo_cliente"] == lista[2]["grupo_cliente"] == "cliente:1"
    assert lista[3]["grupo_cliente"] == "cliente:2"
    # a 4 não tem o cliente no cadastro: entra no grupo do cliente das usinas do mesmo 1º nó do local ("Cliente Alfa")
    assert lista[4]["grupo_cliente"] == "cliente:1" and lista[4]["cliente_id"] is None
    assert lista[1]["usina"] == "Cliente Alfa - Usina Um - SP"


def test_a_marcacao_publica_a_lista_junto(au, monkeypatch):  # noqa: F811
    c = _pcm(au, monkeypatch)
    assert _marcar(c, 2, "compartilha", 1).status_code == 303
    lista = _livro(au)[AU.ABA_LISTA]
    assert {l["usina_id"] for l in lista} == {1, 2, 3, 4}
    assert next(l for l in lista if l["usina_id"] == 4)["grupo_cliente"] == "cliente:1"


def test_a_tela_avisa_a_lista_velha_e_o_botao_publica(au, monkeypatch):  # noqa: F811
    c = _pcm(au, monkeypatch)
    html = c.get(P.TELA).get_data(as_text=True)
    assert "A lista das usinas que o App mostra" in html and 'action="/t/pcm/pecas/usinas/lista"' in html
    r = c.post("/t/pcm/pecas/usinas/lista")
    assert r.status_code == 303
    assert {l["usina_id"] for l in _livro(au)[AU.ABA_LISTA]} == {1, 2, 3, 4}
    assert _livro(au)[AU.ABA_DECISAO] == []                       # publicar a lista não é marcação
    assert "A lista das usinas que o App mostra" not in c.get(P.TELA).get_data(as_text=True)
    # quem só olha não publica
    from test_pcm_publicar import _no_setor
    from nexus.cadastro import setor_ids as SID
    _no_setor(monkeypatch, SID.PERFORMANCE)
    assert c.post("/t/pcm/pecas/usinas/lista").status_code == 403


# ── as declarações a confirmar ──────────────────────────────────────────────────────────────────────────────────────
def test_as_declaracoes_a_confirmar(au, banco):  # noqa: F811
    _publicar_decl(banco,
                   _decl(1, "Cliente Alfa - Usina Dois - SP", "compartilha", "Cliente Alfa - Usina Um - SP",
                         quando="2026-11-22T12:00:00Z", Observação="as peças ficam no contêiner da Usina Um"),
                   _decl(2, "Cliente Beta - Usina Tres - PI", "sem_almoxarifado", quando="2026-11-22T13:00:00Z"),
                   # a mais nova da mesma usina vale
                   _decl(3, "Cliente Beta - Usina Tres - PI", "sem_almoxarifado", quando="2026-11-23T09:00:00Z"),
                   # usina que o Nexus não conhece: aparece, sem o Confirmar
                   _decl(4, "Cliente Gama - Usina X - MG", "sem_almoxarifado"))
    with au.test_request_context("/"):
        d = DC.pendentes(au.config)
    por = {x["usina"]: x for x in d["itens"]}
    assert set(por) == {"Usina Dois", "Usina Tres", "Cliente Gama - Usina X - MG"}
    dois = por["Usina Dois"]
    assert (dois["usina_id"], dois["situacao"], dois["dona_id"], dois["dona"]) == (2, "compartilha", 1, "Usina Um")
    assert dois["observacao"] == "as peças ficam no contêiner da Usina Um" and dois["confirmavel"]
    assert por["Usina Tres"]["id"] == "D-3" and por["Usina Tres"]["confirmavel"]
    assert not por["Cliente Gama - Usina X - MG"]["confirmavel"] and por["Cliente Gama - Usina X - MG"]["problema"]


def test_a_declaracao_some_quando_o_pcm_decide_depois(au, banco, monkeypatch):  # noqa: F811
    _publicar_decl(banco, _decl(1, "Cliente Alfa - Usina Dois - SP", "compartilha", "Cliente Alfa - Usina Um - SP",
                                quando="2026-11-01T12:00:00Z"))
    c = _pcm(au, monkeypatch)
    assert _marcar(c, 2, "proprio").status_code == 303          # o PCM decidiu depois: a declaração sai
    with au.test_request_context("/"):
        assert DC.pendentes(au.config)["itens"] == []


def test_a_declaracao_igual_a_marcacao_nao_pede_nada(au, banco, monkeypatch):  # noqa: F811
    c = _pcm(au, monkeypatch)
    assert _marcar(c, 3, "sem_almoxarifado").status_code == 303
    # o técnico declarou depois o que o PCM já tinha marcado
    _publicar_decl(banco, _decl(1, "Cliente Beta - Usina Tres - PI", "sem_almoxarifado", quando="2099-01-01T00:00:00Z"))
    with au.test_request_context("/"):
        assert DC.pendentes(au.config)["itens"] == []


def test_a_dona_de_outro_cliente_nao_se_confirma(au, banco):  # noqa: F811
    _publicar_decl(banco, _decl(1, "Cliente Alfa - Usina Dois - SP", "compartilha", "Cliente Beta - Usina Tres - PI"))
    with au.test_request_context("/"):
        x = DC.pendentes(au.config)["itens"][0]
    assert not x["confirmavel"] and "outro cliente" in x["problema"]


def test_o_inventario_mostra_e_o_confirmar_volta_para_ele(au, banco, monkeypatch):  # noqa: F811
    _publicar_decl(banco, _decl(1, "Cliente Alfa - Usina Dois - SP", "compartilha", "Cliente Alfa - Usina Um - SP"))
    c = _pcm(au, monkeypatch)
    html = c.get(INVENTARIO).get_data(as_text=True)
    assert "Declarações dos técnicos" in html and "Usina Dois" in html and "Usina Um" in html
    assert 'name="voltar" value="inventario"' in html
    r = c.post("/t/pcm/pecas/usinas/marcar", data={"usina": 2, "situacao": "compartilha", "dona": 1, "voltar": "inventario"})
    assert r.status_code == 303 and r.headers["Location"].endswith(INVENTARIO)
    assert AU.ler(au.config, forcar=True)["marcadas"][2]["situacao"] == "compartilha"
    assert "Declarações dos técnicos" not in c.get(INVENTARIO).get_data(as_text=True)

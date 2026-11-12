"""A 15ª coluna do livro Peças do App ("ID do almoxarifado da usina da OS", o App v339 de 12/11/2026) e a marca "de outro
almoxarifado" onde o PCM vê as peças lançadas (o número "Lançadas pelo App" do Almoxarifado). O livro de antes da v339 tem 14
colunas e continua lendo, sem marca. Dado de mentira."""
from test_campo_visao import _aba, banco  # noqa: F401  (banco é fixture)
from test_pcm_almoxarifado import _abrir, _p, almox  # noqa: F401  (almox é fixture)

from nexus.campo import visao
from nexus.dados import almoxarifado as A
from nexus.pcm import almoxarifado as T


def test_a_coluna_nova_no_fim():
    assert A.COLUNAS_PECAS[-1] == "ID do almoxarifado da usina da OS" and len(A.COLUNAS_PECAS) == 15
    assert A.COLUNAS_PECAS[8] == "ID do almoxarifado"                        # de onde a peça saiu, no mesmo lugar


def test_de_outro_almoxarifado():
    assert A.almoxarifados_da_usina_da_os(" 10, 20.0 ,None,, ") == {"10", "20"}
    assert A.de_outro_almoxarifado("30", "10,20") is True
    assert A.de_outro_almoxarifado("20", "10, 20") is False
    for vazio in (None, "", "None", " , "):                                  # o livro de antes da v339: sem marca
        assert A.de_outro_almoxarifado("30", vazio) is False
    assert A.de_outro_almoxarifado("", "10") is False and A.de_outro_almoxarifado("None", "10") is False


def test_a_marca_no_numero_das_lancadas(app, almox, monkeypatch):
    novo = [dict(_p("A", 1, 10, "lançada"), **{"ID do almoxarifado da usina da OS": "10"}),
            dict(_p("C", 2, 20, "lançada"), **{"ID do almoxarifado da usina da OS": "10,11"}),
            dict(_p("D", 2, 20, "recusada", "sem permissão"), **{"ID do almoxarifado da usina da OS": "10"}),
            _p("E", 1, 20, "lançada")]                                         # sem a coluna: o livro de antes
    _aba(almox, A.LIVRO_PECAS, A.ABA_PECAS, novo)
    visao.limpar()
    with app.app_context():
        d = T.montar().dados
    marcas = sorted((c["id_almox"], c["codigo"], c["situacao"], c["de_outro_almox"]) for c in d["consumo"])
    assert marcas == [("10", "SP-1", "lançada", False), ("20", "SP-1", "lançada", False),     # o livro de antes: sem marca
                      ("20", "SP-2", "lançada", True), ("20", "SP-2", "recusada", True)]
    assert d["kpis"]["lancadas"] == 3 and d["kpis"]["de_outro_almox"] == 1     # a recusada não conta
    html = _abrir(app, monkeypatch).get_data(as_text=True)
    assert "<b>1</b> de outro almoxarifado" in html


def test_o_livro_de_antes_continua_lendo_sem_marca(app, almox, monkeypatch):
    html = _abrir(app, monkeypatch).get_data(as_text=True)
    assert "de outro almoxarifado" not in html and "Lançadas pelo App" in html

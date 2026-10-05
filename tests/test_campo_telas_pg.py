"""As telas da torre Campo · App ligadas no banco do Nexus (Levi, 04/10/2026: "pode gravar na API do PG e ligar as
telas"): Aprovação de OS, Ordens de serviço e Triagem leem os fechamentos que o coletor grava; Atenção e PT continuam
no painel do App, porque o dado delas nasce no App e não vai ao Fracttal.
"""
from datetime import datetime, timedelta, timezone

import pytest
from pg_falso import ApiPGFalsa
from test_campo_aprovacao import FracttalFalso, _os
from test_campo_fonte_pg import BASE, CHAVE, _linha

from nexus.campo import aprovacao, banco_campo, fonte_pg, fracttal, leitura, ordens, tabelas, triagem
from nexus.torres.campo import _motivo


def _iso(dias_atras):
    return (datetime.now(timezone.utc) - timedelta(days=dias_atras)).strftime("%Y-%m-%dT%H:%M:%S")


@pytest.fixture
def banco():
    api = ApiPGFalsa()
    linhas = [_linha(501, 15102, fim=_iso(1), nota=96, n_fotos=3),
              _linha(502, 15088, fim=_iso(2), nota=45, n_fotos=0, gps_fotos=False),   # não dá para comprovar
              _linha(503, 15077, fim=_iso(3), nota=88, status_os=3, aprovacao=_iso(1)),
              _linha(601, 15002, fim=_iso(4), pelo_app=False, nota=None)]
    banco_campo.gravar(linhas, banco_campo.resumo(linhas, "x", completa=True), base=BASE, token="t", sessao=api)
    tabelas.usar_fornecedor(fonte_pg.Fornecedor({"GRIDCO_DB_API": BASE, "NEXUS_CHAVE_CADASTRO": CHAVE}, sessao=api))
    leitura.limpar_cache()
    yield api
    tabelas.usar_fornecedor(None)
    leitura.limpar_cache()


def test_ordens_de_servico_pelo_banco(logado, banco):
    r = ordens.painel(7).dados["atual"]["resumo"]
    assert r["os"] == 3 and r["qualidade_media"] == round((96 + 45 + 88) / 3)
    assert r["pontualidade_pct"] is None              # o Fracttal não tem a hora de início no celular: sem dado, não 0%
    html = logado.get("/t/campo/os?dias=7").get_data(as_text=True)
    assert "#15102" in html and "#15077" in html and "#15002" not in html    # fechada fora do App não entra
    assert "notas do App" in html and "só no App (hora de início no celular)" in html
    assert "<iframe" not in html


def test_triagem_pelo_banco(logado, banco):
    d = triagem.painel(30).dados
    assert d["resumo"]["os_periodo"] == 3
    os_ = {i["id"]: i for i in d["itens"] if i["tipo"] == "os"}
    assert os_["15088"]["nivel"] == "critico" and "sem GPS, sem foto" in os_["15088"]["motivo"]
    assert [e["id"] for e in d["exemplares"]] == ["15102"]          # 96%, 3 fotos, GPS e assinatura
    html = logado.get("/t/campo/triagem").get_data(as_text=True)
    assert "Exige ação hoje" in html and "OS 15088" in html and "<b>sem GPS, sem foto</b>" in html
    assert "<iframe" not in html


def test_motivo_do_app_so_deixa_passar_o_negrito():
    assert str(_motivo("<script>x</script> qualidade <b>45%</b>")) == \
        "&lt;script&gt;x&lt;/script&gt; qualidade <b>45%</b>"


def test_aprovacao_usa_a_nota_do_banco(banco):
    fracttal.usar_fornecedor(FracttalFalso([_os(15002, 4, "Técnico 7"), _os(15088, 2, "Técnico 4"),
                                            _os(15102, 1, "Técnico 5")]))
    try:
        d = aprovacao.fila({"dias": "30"}).dados
    finally:
        fracttal.usar_fornecedor(None)
    assert {x["os"]: (x["balde"], x["qualidade"]) for x in d["linhas"]} == {
        "15002": ("fora_do_app", None), "15088": ("olho", 45), "15102": ("completa", 96)}

"""As telas da torre Campo · App ligadas no banco do Nexus (Levi, 04/10/2026: "pode gravar na API do PG e ligar as
telas"): Aprovação de OS e Triagem leem os fechamentos que o coletor grava (Ordens de serviço saiu em 08/10/2026);
Atenção e PT continuam no painel do App, porque o dado delas nasce no App e não vai ao Fracttal.
"""
from datetime import datetime, timedelta, timezone

import pytest
from pg_falso import ApiPGFalsa
from test_campo_aprovacao import FracttalFalso, _os
from test_campo_fonte_pg import BASE, CHAVE, _linha, semear

from nexus.campo import aprovacao, fonte_pg, fracttal, leitura, tabelas, triagem


def _iso(dias_atras):
    return (datetime.now(timezone.utc) - timedelta(days=dias_atras)).strftime("%Y-%m-%dT%H:%M:%S")


@pytest.fixture
def banco():
    api = ApiPGFalsa()
    linhas = [_linha(501, 15102, fim=_iso(1), nota=96, n_fotos=3),
              _linha(502, 15088, fim=_iso(2), nota=45, n_fotos=0, gps_fotos=False),   # não dá para comprovar
              _linha(503, 15077, fim=_iso(3), nota=88, status_os=3, aprovacao=_iso(1)),
              _linha(601, 15002, fim=_iso(4), pelo_app=False, nota=None)]
    semear(api, linhas, completa=True)
    tabelas.usar_fornecedor(fonte_pg.Fornecedor({"GRIDCO_DB_API": BASE, "NEXUS_CHAVE_CADASTRO": CHAVE}, sessao=api))
    leitura.limpar_cache()
    yield api
    tabelas.usar_fornecedor(None)
    leitura.limpar_cache()


def test_triagem_pelo_banco(logado, banco):
    d = triagem.painel(30).dados
    assert d["resumo"]["os_periodo"] == 3
    os_ = {i["id"]: i for i in d["itens"] if i["tipo"] == "os"}
    assert os_["15088"]["nivel"] == "critico" and "sem GPS, sem foto" in os_["15088"]["motivo"]
    assert [e["id"] for e in d["exemplares"]] == ["15102"]          # 96%, 3 fotos, GPS e assinatura
    # a tela saiu em 09/11/2026 (Levi: "fica redundante pois aprovação de OS traz isso e muito mais"): a conta fica e o
    # endereço guardado leva à Aprovação de OS
    r = logado.get("/t/campo/triagem")
    assert r.status_code == 302 and r.headers["Location"].endswith("/t/campo/aprovacao")


def test_aprovacao_usa_a_nota_do_banco(banco):
    fracttal.usar_fornecedor(FracttalFalso([_os(15002, 4, "Técnico 7"), _os(15088, 2, "Técnico 4"),
                                            _os(15102, 1, "Técnico 5")]))
    try:
        d = aprovacao.fila_toda({"dias": "30"}).dados
    finally:
        fracttal.usar_fornecedor(None)
    assert {x["os"]: (x["balde"], x["qualidade"]) for x in d["linhas"]} == {
        "15002": ("fora_do_app", None), "15088": ("olho", 45), "15102": ("completa", 96)}

"""Engenharia > Quadro da equipe: a OS da engenharia (Levi, 24/10/2026: "Ao clicar quero uma visão parecida com o que
aparece quando clica na OS da parte de CHAMADOS > GARANTIA"), com o status e a prioridade da engenharia, os comentários
na nota da OS, as OS filhas e o pulso das paradas. Desenho em docs/superpowers/specs/2026-10-24-engenharia-os-do-quadro-
design.md. Banco falso (tests/pg_falso.py) e Fracttal falso; os nomes são fictícios."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from pg_falso import ApiPGFalsa
from test_engenharia_acompanhamento import ANA, BETO

from nexus.cadastro.cifra import gerar_chave
from nexus.dados import catalogo, explica
from nexus.engenharia import os_acompanhamento as O

BRT = timezone(timedelta(hours=-3))
OS1 = {"wid": 39550452, "folio": "16502", "codigo": "IBI200-INVR1.3", "usina_id": 1,
       "usina_ligada_por": "de-para do Fracttal"}


@pytest.fixture
def banco(app):
    api = ApiPGFalsa()
    app.config.update(GRIDCO_DB_API="http://pg.falso", NEXUS_CHAVE_CADASTRO=gerar_chave(),
                      NEXUS_PESSOA_HMAC="hmac-teste", GRIDCO_SQL_TOKEN="tk")
    app.extensions["nexus_dados_sessao"] = api
    O.limpar()
    with app.app_context():
        yield api
    O.limpar()
    app.extensions.pop("nexus_dados_sessao", None)


def _est(wid=OS1["wid"]):
    return O.estado(O.ler(forcar=True)["eventos"]).get(str(wid)) or {}


# ── Task 1: o livro e as regras ─────────────────────────────────────────────────────────────────────────────────────
def test_catalogo_registra_o_livro_da_os():
    l = catalogo.LIVRO_POR_NOME[O.LIVRO]
    assert set(l.abas) == {O.ABA, O.ABA_STATUS, O.ABA_PRIORIDADE} and set(l.so_cresce) == set(l.abas)
    assert all(catalogo.aba_segue_a_regra(x) for x in l.abas)
    f = next(x for x in catalogo.FATOS if x.id == "acompanhamento_os")
    assert "1 linha = 1 evento" in f.grao and {"data", "usina", "equipamento", "pessoa"} <= set(f.dims)
    assert 15 <= len(explica.RESUMO["acompanhamento_os"]) <= 70
    assert len(explica.PARA_QUE["acompanhamento_os"]) >= 80 and explica.PARA_QUE["acompanhamento_os"].endswith(".")


def test_os_oito_status_e_as_tres_prioridades_do_pedido():
    assert [n for _i, n in O.STATUS] == ["Análise de Solução", "Atividade em Andamento", "Diagnóstico em Andamento",
                                         "Agendamento de OS", "Tratativa com Equipe de Campo", "Validação Final",
                                         "Stand-By", "Diagnóstico Concluído"]
    assert [n for _i, n in O.PRIORIDADES] == ["Média", "Alta", "Urgente"]


def test_status_e_prioridade_vao_ao_livro_e_o_estado_le_o_ultimo(banco):
    O.classificar(OS1, 3, 2, ANA, True)
    e = _est()
    assert (e["status_id"], e["prioridade_id"]) == (3, 2)
    O.classificar(OS1, 8, None, BETO, True)                 # só o status: a prioridade fica
    e = _est()
    assert (e["status_id"], e["prioridade_id"]) == (8, 2)
    assert [x["evento"] for x in e["eventos"]][:1] == ["status"] and e["eventos"][0]["nome"] == "Beto Souza"
    linhas = banco.linhas(O.LIVRO, O.ABA)
    assert len(linhas) == 3 and {str(x["os_id"]) for x in linhas} == {str(OS1["wid"])}
    assert [x["nome"] for x in banco.linhas(O.LIVRO, O.ABA_STATUS)][2] == "Diagnóstico em Andamento"
    assert [x["nome"] for x in banco.linhas(O.LIVRO, O.ABA_PRIORIDADE)] == ["Média", "Alta", "Urgente"]


def test_nada_mudou_e_quem_nao_e_da_engenharia_nao_classifica(banco):
    O.classificar(OS1, 1, 1, ANA, True)
    with pytest.raises(O.Recusada, match="Nada mudou"):
        O.classificar(OS1, 1, 1, ANA, True)
    with pytest.raises(O.Recusada, match="Engenharia"):
        O.classificar(OS1, 2, None, BETO, False)
    with pytest.raises(O.Recusada, match="status"):
        O.classificar(OS1, 9, None, ANA, True)                 # fora da lista


def test_comentario_cifrado_e_a_linha_da_nota(banco):
    quando = datetime(2026, 10, 24, 14, 32, tzinfo=BRT)
    assert O.linha_da_nota("Trocar o cabo", "Ana Lima", quando) == "[24/10/2026 14:32] Ana Lima (Engenharia): Trocar o cabo"
    O.registrar_comentario(OS1, "Trocar o cabo do MPPT 2", ANA, True, "sim")
    e = _est()
    c = e["eventos"][0]
    assert c["evento"] == "comentario" and c["texto"] == "Trocar o cabo do MPPT 2" and c["nota"] == "sim"
    cru = json.dumps(banco.linhas(O.LIVRO, O.ABA), ensure_ascii=False, default=str)
    assert "Trocar o cabo" not in cru and "Ana Lima" not in cru and "ana.lima" not in cru
    with pytest.raises(O.Recusada, match="Escreva"):
        O.registrar_comentario(OS1, "   ", ANA, True, "sim")


def test_ultima_atualizacao_e_parada():
    agora = datetime(2026, 10, 24, 12, 0, tzinfo=BRT)
    a, b = agora - timedelta(days=9), agora - timedelta(days=8)
    assert O.ultima_atualizacao([a, None, b]) == b and O.ultima_atualizacao([None]) is None
    assert O.parada("fazer", b, agora) and O.parada("verificacao", b, agora)
    assert not O.parada("fazer", agora - timedelta(days=6), agora)
    assert not O.parada("concluida", b, agora) and not O.parada("cancelada", b, agora)
    assert not O.parada("fazer", None, agora)                   # sem data não se chuta parada

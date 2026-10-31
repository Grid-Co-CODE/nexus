"""As contas do inventário do almoxarifado (26/10/2026, Levi): a situação de cada peça (para cima, para baixo, zerar, sem
alteração, não tocada, curadoria), o contado efetivo com a curadoria, o lote que o PCM revisa, a contagem mais nova que
substitui as velhas e a janela de aprovação. Módulo puro (`nexus/pcm/inventario/contas.py`): dicts entram, dicts saem.
Desenho: docs/superpowers/specs/2026-10-26-inventario-almoxarifado-design.md (seções 4.2 e 4.5). Dado de mentira: usina,
códigos e IDs inventados, sem nome de gente."""
import ast
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nexus.dados.almoxarifado import COLUNAS_CONTAGENS
from nexus.pcm.inventario import contas as C

AGORA = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)
ALMOX = "900"


def _linha(id_linha, id_item="", contado="", tipo="item", **mais):
    """Uma linha do livro das contagens do jeito que a API a devolve: as 19 colunas, tudo como texto."""
    l = dict.fromkeys(COLUNAS_CONTAGENS, "")
    l.update({"ID da contagem": "C-1", "Enviada em": "2026-10-26T10:00:00Z", "Contada em": "2026-10-26T09:00:00Z",
              "ID do almoxarifado": ALMOX, "Usina": "Cliente Teste - Usina Alfa - BA", "Tipo": tipo,
              "ID do item": str(id_item), "Código": f"SP-{id_item}" if id_item != "" else "", "Contado": contado,
              "ID da linha": str(id_linha)})
    l.update(mais)
    return l


def _sis(**saldos):
    """O que o `Estoque.ler` devolve: `{id_item: {saldo, minimo, maximo, ligacao, codigo}}` (o `saldo` pode ser None)."""
    return {i[1:]: {"saldo": s, "minimo": None, "maximo": None, "ligacao": f"L{i[1:]}", "codigo": f"EST-{i[1:]}"}
            for i, s in saldos.items()}


def _por_peca(itens):
    return {i["id_item"]: i for i in itens}


# ── as situações ────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_contrato_das_situacoes():
    assert C.SITUACOES == ("para_cima", "para_baixo", "zerar", "sem_alteracao", "nao_tocada", "curadoria")
    assert C.MEXEM == ("para_cima", "para_baixo", "zerar")           # só estes três mexem no estoque
    assert set(C.MEXEM) < set(C.SITUACOES)


@pytest.mark.parametrize("sistema, contado, esperada", [
    (4, 6, "para_cima"),
    (4, 2, "para_baixo"),
    (4, 0, "zerar"),                    # o 0 digitado em peça com saldo
    (0, 0, "sem_alteracao"),
    (4, None, "nao_tocada"),            # em branco não é zero
    (None, 3, "para_cima"),             # saldo não informado vale 0 para a conta
    (4, 4, "sem_alteracao"),
    (0, 5, "para_cima"),
    (2.5, 2.5, "sem_alteracao"),
    (None, 0, "sem_alteracao"),         # saldo vazio não é saldo cheio: o zerar não vale
    (None, None, "nao_tocada"),
    (4, -1, "nao_tocada"),              # contado negativo nunca mexe
])
def test_situacao(sistema, contado, esperada):
    assert C.situacao(sistema, contado) == esperada


def test_situacao_sem_ruido_de_decimal():
    """Metro e massa são decimais: 0.1 + 0.2 não é 0.3 em ponto flutuante, e uma diferença de 5e-17 não é ajuste de
    estoque (virava uma gravação no Fracttal por nada)."""
    assert C.situacao(0.3, 0.1 + 0.2) == "sem_alteracao"
    assert C.situacao(0.3, 0.31) == "para_cima"


# ── o contado efetivo ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_item_vale_o_contado_da_linha_dele():
    linhas = [_linha(1, 101, "7"), _linha(2, 102, "0"), _linha(3, 103, "")]
    assert C.contado_efetivo(linhas, {}) == {"101": 7.0, "102": 0.0, "103": None}


def test_texto_da_api():
    """O livro volta da API todo como texto: "3,0" é 3; o vazio vem "" ou "None" e é "não contei", nunca 0 (o foco 3: um
    vazio virado em 0 zeraria o estoque de uma peça que ninguém contou)."""
    linhas = [_linha(1, 101, "3,0"), _linha(2, 102, ""), _linha(3, 103, "None"), _linha(4, 104, "0"),
              _linha(5, "105.0", "2.5")]
    assert C.contado_efetivo(linhas, {}) == {"101": 3.0, "102": None, "103": None, "104": 0.0, "105": 2.5}
    itens = _por_peca(C.itens_do_lote(linhas, _sis(s101=3, s102=5, s103=5, s104=5, s105=2.5), {}, {}))
    assert itens["101"]["situacao"] == "sem_alteracao"
    assert itens["102"]["situacao"] == itens["103"]["situacao"] == "nao_tocada"
    assert itens["102"]["contado"] is None and itens["103"]["contado"] is None
    assert itens["104"]["situacao"] == "zerar"                       # só o 0 digitado zera
    assert itens["105"]["situacao"] == "sem_alteracao" and itens["105"]["ligada"] is True   # "105.0" é o 105


def test_e_a_peca_x_soma_na_mesma_contagem():
    """"É a peça X": as unidades achadas fora do catálogo são unidades de X contadas nessa mesma contagem. X contada 3 e 2
    achadas dão 5; X em branco e 2 achadas dão 2; X que nem estava na contagem fica só com as achadas. O total SUBSTITUI
    o saldo (o inventário não soma ao Fracttal)."""
    achadas = _linha(9, tipo="fora_do_catalogo", contado="2", **{"Descrição": "parafuso sextavado"})
    cur = {"9": {"decisao": "e_a_peca", "id_item": "101"}}
    assert C.contado_efetivo([_linha(1, 101, "3"), achadas], cur)["101"] == 5.0
    assert C.contado_efetivo([_linha(1, 101, ""), achadas], cur)["101"] == 2.0
    assert C.contado_efetivo([achadas], cur) == {"101": 2.0}
    sem_decisao = C.contado_efetivo([_linha(1, 101, "3"), achadas], {})
    assert sem_decisao == {"101": 3.0}                               # sem decisão, as achadas não valem para peça nenhuma
    descartada = C.contado_efetivo([_linha(1, 101, "3"), achadas], {"9": {"decisao": "descartar", "id_item": ""}})
    assert descartada == {"101": 3.0}
    # no lote: sistema 4, contado 5 (3 + 2) é ajuste para cima de 1
    x = _por_peca(C.itens_do_lote([_linha(1, 101, "3"), achadas], _sis(s101=4), cur, {}))["101"]
    assert (x["contado"], x["contado_campo"], x["sistema"], x["delta"], x["situacao"]) == (5.0, 5.0, 4.0, 1.0, "para_cima")


def test_cadastrar_entra_como_peca_nova_com_as_achadas():
    """A peça cadastrada pela curadoria (a decisão guarda o ID que o Fracttal deu) não estava no catálogo: o contado dela
    é as achadas, e ela não está ligada ao almoxarifado ainda (sistema 0, ligada falso: a gravação a liga)."""
    achadas = _linha(9, tipo="fora_do_catalogo", contado="6")
    cur = {"9": {"decisao": "cadastrar", "id_item": "777", "codigo": "SP-CAB-001"}}
    assert C.contado_efetivo([achadas], cur) == {"777": 6.0}
    nova = _por_peca(C.itens_do_lote([achadas], {}, cur, {}))["777"]
    assert (nova["codigo"], nova["sistema"], nova["ligada"], nova["contado"], nova["situacao"]) == (
        "SP-CAB-001", 0.0, False, 6.0, "para_cima")
    sem_id = {"9": {"decisao": "cadastrar", "id_item": ""}}          # a peça ainda não foi criada: nada vale
    assert C.contado_efetivo([achadas], sem_id) == {}


def test_generico_identificado_sai_do_generico():
    """O genérico (com saldo 4) que o técnico identificou, as 4 unidades, como Y: confirmado, as unidades SAEM do genérico
    (que vai a 0: zerar) e ENTRAM em Y (+4); sem sair, o estoque ficaria em dobro."""
    linhas = [_linha(1, 500, "4", tipo="identificar", **{"Identificado como": "201"})]
    cur = {"1": {"decisao": "confirmar", "id_item": "201"}}
    assert C.contado_efetivo(linhas, cur) == {"500": 0.0, "201": 4.0}
    itens = _por_peca(C.itens_do_lote(linhas, _sis(s500=4, s201=1), cur, {}))
    assert (itens["500"]["contado"], itens["500"]["situacao"]) == (0.0, "zerar")
    assert (itens["201"]["contado"], itens["201"]["situacao"]) == (4.0, "para_cima")      # o Y estava com 1: o total é 4
    # Y que também foi contado como peça da lista: as unidades somam ao dele (3 + 4)
    com_y = C.contado_efetivo([_linha(2, 201, "3")] + linhas, cur)
    assert com_y == {"201": 7.0, "500": 0.0}


def test_generico_em_mais_de_um_especifico():
    """Uma linha por específico, com o mesmo código do genérico: o genérico achou 6, 4 eram Y e 2 eram Z."""
    linhas = [_linha(1, 500, "4", tipo="identificar", **{"Identificado como": "201"}),
              _linha(2, 500, "2", tipo="identificar", **{"Identificado como": "202"})]
    cur = {"1": {"decisao": "confirmar", "id_item": "201"}, "2": {"decisao": "confirmar", "id_item": "202"}}
    assert C.contado_efetivo(linhas, cur) == {"500": 0.0, "201": 4.0, "202": 2.0}


def test_generico_confirmado_em_outro_especifico_vale_o_do_pcm():
    """A decisão do PCM vale sobre o palpite do técnico; sem o ID na decisão, vale o "Identificado como" da linha."""
    linhas = [_linha(1, 500, "4", tipo="identificar", **{"Identificado como": "201"})]
    assert C.contado_efetivo(linhas, {"1": {"decisao": "confirmar", "id_item": "202"}}) == {"500": 0.0, "202": 4.0}
    assert C.contado_efetivo(linhas, {"1": {"decisao": "confirmar"}}) == {"500": 0.0, "201": 4.0}
    nem_um = [_linha(1, 500, "4", tipo="identificar")]                # o técnico não soube e o PCM não disse
    assert C.contado_efetivo(nem_um, {"1": {"decisao": "confirmar"}}) == {"500": 4.0}


def test_curadoria_sem_decisao_nao_mexe():
    """O genérico por identificar e o achado por decidir ficam na situação `curadoria` (não grava nada): gravar o
    genérico com as unidades ainda sem dono viraria, por exemplo, um ajuste para cima de uma peça que não aumentou."""
    linhas = [_linha(1, 500, "6", tipo="identificar", **{"Identificado como": "201"}),
              _linha(2, tipo="fora_do_catalogo", contado="2", **{"Descrição": "arruela lisa"}),
              _linha(3, 101, "3")]
    itens = C.itens_do_lote(linhas, _sis(s500=4, s101=3), {}, {})
    assert [i["situacao"] for i in itens] == ["curadoria", "curadoria", "sem_alteracao"]
    generico, achado, normal = itens
    assert generico["id_item"] == "500" and generico["pendentes"] == ["1"] and generico["contado"] == 6.0
    assert achado["id_item"] == "" and achado["pendentes"] == ["2"] and achado["contado"] == 2.0
    assert achado["ligada"] is False and achado["sistema"] == 0.0
    assert normal["pendentes"] == []
    assert not [i for i in itens if i["situacao"] in C.MEXEM]
    # o genérico decidido sai da curadoria; o outro continua
    cur = {"1": {"decisao": "confirmar", "id_item": "201"}}
    de_novo = C.itens_do_lote(linhas, _sis(s500=4, s101=3), cur, {})
    assert [(i["id_item"], i["situacao"]) for i in de_novo] == [("500", "zerar"), ("201", "para_cima"), ("", "curadoria"),
                                                                ("101", "sem_alteracao")]


def test_decisao_que_nao_cabe_no_tipo_nao_vale():
    """`confirmar` é do genérico e `e_a_peca`/`cadastrar`/`descartar` são do achado fora do catálogo: a decisão que não é
    do tipo da linha não resolve nada (a linha segue pendente, e nada é gravado por engano)."""
    achado = _linha(2, tipo="fora_do_catalogo", contado="2")
    generico = _linha(1, 500, "4", tipo="identificar", **{"Identificado como": "201"})
    assert C.contado_efetivo([achado], {"2": {"decisao": "confirmar", "id_item": "101"}}) == {}
    assert C.contado_efetivo([generico], {"1": {"decisao": "e_a_peca", "id_item": "201"}}) == {"500": 4.0}
    assert C.contado_efetivo([generico], {"1": {"decisao": "descartar"}}) == {"500": 4.0}
    assert C.contado_efetivo([achado], {"2": {"decisao": "qualquer"}}) == {}


def test_contado_negativo_nao_mexe():
    """O App não deveria mandar contado negativo, mas o livro é texto: a peça entra como não contada (contado None,
    `nao_tocada`) e fica `invalido`, nunca mexe no estoque (gravar -3 como saldo estragaria o estoque inteiro)."""
    linhas = [_linha(1, 101, "-3"), _linha(2, 102, "4"), _linha(3, 103, "2"), _linha(4, 103, "-1")]
    assert C.contado_efetivo(linhas, {}) == {"101": None, "102": 4.0, "103": None}
    itens = _por_peca(C.itens_do_lote(linhas, _sis(s101=5, s102=4, s103=2), {}, {}))
    for i in ("101", "103"):
        assert itens[i]["contado"] is None and itens[i]["contado_campo"] is None
        assert itens[i]["situacao"] == "nao_tocada" and itens[i]["invalido"] is True
        assert itens[i]["situacao"] not in C.MEXEM
    assert itens["102"]["invalido"] is False and itens["102"]["situacao"] == "sem_alteracao"
    # o PCM que corrige a peça inválida é quem diz o número (a auditoria guarda o do campo, que não existe)
    certa = _por_peca(C.itens_do_lote(linhas, _sis(s101=5), {}, {"corrigidos": {"101": 4}}))["101"]
    assert (certa["contado"], certa["contado_campo"], certa["invalido"], certa["situacao"]) == (
        4.0, None, True, "para_baixo")
    # o negativo nas achadas contamina a peça que as receberia, e o achado negativo por decidir fica inválido
    achadas = _linha(9, tipo="fora_do_catalogo", contado="-2")
    assert C.contado_efetivo([_linha(1, 101, "3"), achadas], {"9": {"decisao": "e_a_peca", "id_item": "101"}}) == {
        "101": None}
    pendente = C.itens_do_lote([achadas], {}, {}, {})[0]
    assert pendente["invalido"] is True and pendente["contado"] is None and pendente["situacao"] == "curadoria"


def test_soma_decimal_sem_ruido():
    linhas = [_linha(1, 101, "0,1"), _linha(2, tipo="fora_do_catalogo", contado="0,2")]
    ef = C.contado_efetivo(linhas, {"2": {"decisao": "e_a_peca", "id_item": "101"}})
    assert ef == {"101": 0.3}                                         # e não 0.30000000000000004
    assert C.itens_do_lote(linhas, _sis(s101=0.3), {"2": {"decisao": "e_a_peca", "id_item": "101"}}, {})[0][
        "situacao"] == "sem_alteracao"


def test_zero_achadas_nao_zera_a_peca_em_branco():
    """O 0 que a curadoria atribui a uma peça (achadas = 0) não é o 0 que o técnico digitou na linha dela: a peça em
    branco (ninguém a contou, saldo 8 no Fracttal) continua "não contei" e NÃO vira `zerar`. A peça que só existe pela
    decisão, com 0 unidades, nem entra na conta."""
    achadas = _linha(9, tipo="fora_do_catalogo", contado="0")
    cur = {"9": {"decisao": "e_a_peca", "id_item": "101"}}
    linhas = [_linha(1, 101, ""), achadas]
    assert C.contado_efetivo(linhas, cur) == {"101": None}
    x = _por_peca(C.itens_do_lote(linhas, _sis(s101=8), cur, {}))["101"]
    assert (x["contado"], x["situacao"]) == (None, "nao_tocada")
    assert C.contado_efetivo([achadas], cur) == {}                                  # X nem estava na contagem
    assert C.itens_do_lote([achadas], _sis(s101=8), cur, {}) == []
    assert C.contado_efetivo([achadas], {"9": {"decisao": "cadastrar", "id_item": "777"}}) == {}
    em_branco = _linha(9, tipo="fora_do_catalogo", contado="")                      # achadas em branco: também nada
    assert C.contado_efetivo(linhas[:1] + [em_branco], cur) == {"101": None}


def test_zero_do_generico_confirmado_nao_zera_o_especifico_em_branco():
    """O mesmo pelo genérico: 0 unidades confirmadas como Y não contam Y. O genérico, esse, foi contado (o 0 é do técnico,
    na linha dele): continua `zerar`."""
    generico = _linha(2, 500, "0", tipo="identificar", **{"Identificado como": "201"})
    linhas = [_linha(1, 201, ""), generico]
    cur = {"2": {"decisao": "confirmar", "id_item": "201"}}
    assert C.contado_efetivo(linhas, cur) == {"201": None, "500": 0.0}
    itens = _por_peca(C.itens_do_lote(linhas, _sis(s201=8, s500=3), cur, {}))
    assert (itens["201"]["contado"], itens["201"]["situacao"]) == (None, "nao_tocada")
    assert (itens["500"]["contado"], itens["500"]["situacao"]) == (0.0, "zerar")
    assert C.contado_efetivo([generico], cur) == {"500": 0.0}                       # Y nem estava na contagem


def test_zero_achadas_nao_mexe_na_peca_contada():
    achadas = _linha(9, tipo="fora_do_catalogo", contado="0")
    cur = {"9": {"decisao": "e_a_peca", "id_item": "101"}}
    assert C.contado_efetivo([_linha(1, 101, "3"), achadas], cur) == {"101": 3.0}
    generico = _linha(2, 500, "0", tipo="identificar", **{"Identificado como": "201"})
    assert C.contado_efetivo([_linha(1, 201, "3"), generico], {"2": {"decisao": "confirmar"}}) == {"201": 3.0, "500": 0.0}
    # o 0 digitado na linha da própria peça segue sendo o "zerar"
    assert C.itens_do_lote([_linha(1, 101, "0")], _sis(s101=8), {}, {})[0]["situacao"] == "zerar"


def test_generico_em_branco_sem_decisao_e_nao_tocado():
    """Não há o que decidir sobre unidades que ninguém contou: o genérico em branco é `nao_tocada`, não `curadoria`."""
    linhas = [_linha(1, 500, "", tipo="identificar", **{"Identificado como": "201"}),
              _linha(2, 500, "None", tipo="identificar")]
    (g,) = C.itens_do_lote(linhas, _sis(s500=4), {}, {})
    assert (g["id_item"], g["contado"], g["situacao"], g["pendentes"]) == ("500", None, "nao_tocada", [])
    uma_contada = C.itens_do_lote(linhas + [_linha(3, 500, "2", tipo="identificar")], _sis(s500=4), {}, {})[0]
    assert (uma_contada["situacao"], uma_contada["pendentes"]) == ("curadoria", ["3"])     # com unidades, decide-se


def test_achado_em_branco_sem_decisao_nao_vira_pendencia():
    for vazio in ("", "None", "  "):
        achado = _linha(9, tipo="fora_do_catalogo", contado=vazio, **{"Descrição": "arruela lisa"})
        assert C.itens_do_lote([achado], {}, {}, {}) == []
        assert [i["id_item"] for i in C.itens_do_lote([achado, _linha(1, 101, "2")], {}, {}, {})] == ["101"]
    assert len(C.itens_do_lote([_linha(9, tipo="fora_do_catalogo", contado="2")], {}, {}, {})) == 1


def test_linha_reenviada_conta_uma_vez():
    """A fila offline do App reenvia a contagem quando não vê a resposta: a mesma (ID da contagem, ID da linha) é a MESMA
    peça contada, não duas. Vale a última (o reenvio traz o que o técnico deixou na tela)."""
    assert C.contado_efetivo([_linha(1, 101, "3"), _linha(1, 101, "3")], {}) == {"101": 3.0}          # e não 6
    assert C.contado_efetivo([_linha(1, 101, "3"), _linha(1, 101, "5")], {}) == {"101": 5.0}
    achado = _linha(9, tipo="fora_do_catalogo", contado="2")
    assert len(C.itens_do_lote([achado, dict(achado)], {}, {}, {})) == 1                              # uma pendência
    generico = _linha(2, 500, "4", tipo="identificar", **{"Identificado como": "201"})
    cur = {"2": {"decisao": "confirmar", "id_item": "201"}}
    assert C.contado_efetivo([generico, dict(generico)], cur) == {"500": 0.0, "201": 4.0}             # Y +4, não +8
    # o mesmo ID da linha em OUTRA contagem é outra linha; sem ID da linha não há como saber: não se junta
    assert C.contado_efetivo([_linha(1, 101, "3"), _linha(1, 101, "4", **{"ID da contagem": "C-2"})], {}) == {"101": 7.0}
    assert C.contado_efetivo([_linha("", 101, "1"), _linha("", 101, "1")], {}) == {"101": 2.0}


def test_linha_que_nao_e_de_peca_nenhuma_nao_entra():
    """Sem ID do item, ou de um Tipo que não existe, não há peça para tocar: a linha não entra no lote."""
    linhas = [_linha(1, "", "5", tipo="item"), _linha(2, 101, "5", tipo="mistério"), _linha(3, 102, "5")]
    assert C.contado_efetivo(linhas, {}) == {"102": 5.0}


# ── o lote ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_lote_traz_uma_entrada_por_peca_na_ordem_do_livro():
    linhas = [_linha(1, 103, "1"), _linha(2, 101, "2"), _linha(3, 103, "4")]    # a 103 duas vezes: as linhas somam
    itens = C.itens_do_lote(linhas, _sis(s101=2, s103=9), {}, {})
    assert [i["id_item"] for i in itens] == ["103", "101"]
    assert itens[0]["contado"] == 5.0 and itens[0]["situacao"] == "para_baixo" and itens[0]["delta"] == -4.0
    assert set(itens[0]) >= {"id_item", "codigo", "sistema", "contado", "contado_campo", "situacao", "ligada", "corrigido",
                             "tirada", "invalido", "delta", "pendentes"}
    assert C.itens_do_lote([], _sis(s101=2), {}, {}) == [] and C.itens_do_lote(None, None, None, None) == []


def test_peca_nao_ligada():
    """A peça que nunca foi ligada ao almoxarifado no Fracttal não vem na leitura de estoque (o foco 2): ela entra com
    `sistema` 0 e `ligada` falso, e a gravação a liga antes de gravar o saldo."""
    linhas = [_linha(1, 101, "2"), _linha(2, 102, "0")]
    itens = _por_peca(C.itens_do_lote(linhas, _sis(s999=7), {}, {}))
    a, b = itens["101"], itens["102"]
    assert (a["sistema"], a["ligada"], a["situacao"], a["delta"]) == (0.0, False, "para_cima", 2.0)
    assert (b["sistema"], b["ligada"], b["situacao"]) == (0.0, False, "sem_alteracao")      # 0 em peça sem saldo: nada


def test_saldo_vazio_nao_zera():
    """O Fracttal não disse o saldo da peça (None, "não informado", o foco 5): para a conta vale 0, mas contar 0 não é
    "zerar" (zeraria uma peça sem saldo conhecido), e o `sistema` do lote continua None para a tela dizer "não
    informado" e para a conferência da gravação comparar igual com igual."""
    itens = _por_peca(C.itens_do_lote([_linha(1, 101, "0"), _linha(2, 102, "3")], _sis(s101=None, s102=None), {}, {}))
    assert itens["101"]["sistema"] is None and itens["101"]["ligada"] is True
    assert itens["101"]["situacao"] == "sem_alteracao" and itens["101"]["situacao"] != "zerar"
    assert itens["101"]["delta"] == 0.0
    assert itens["102"]["situacao"] == "para_cima" and itens["102"]["delta"] == 3.0


def test_saldo_nan_e_saldo_nao_informado():
    """O `float` aceita "nan" e "inf": o saldo que não é número é "não informado" (None), nunca NaN no `sistema` nem no
    `delta` (NaN não é igual a nada, e a conferência da gravação comparar com ele travaria a peça)."""
    for ruim in (float("nan"), "nan", float("inf"), "inf", float("-inf")):
        (i,) = C.itens_do_lote([_linha(1, 101, "3")], _sis(s101=ruim), {}, {})
        assert i["sistema"] is None and i["ligada"] is True
        assert i["delta"] == 3.0 and i["situacao"] == "para_cima"


def test_o_codigo_do_lote():
    """O código vem da linha do App; a peça que só entrou pela curadoria usa o da decisão e, sem ele, o do estoque."""
    linhas = [_linha(1, 101, "1", **{"Código": "SP-AAA-001"}), _linha(2, tipo="fora_do_catalogo", contado="1")]
    cur = {"2": {"decisao": "e_a_peca", "id_item": "102"}}
    itens = _por_peca(C.itens_do_lote(linhas, _sis(s101=1, s102=1), cur, {}))
    assert itens["101"]["codigo"] == "SP-AAA-001"
    assert itens["102"]["codigo"] == "EST-102"
    cur["2"]["codigo"] = "SP-BBB-002"
    assert _por_peca(C.itens_do_lote(linhas, _sis(s101=1, s102=1), cur, {}))["102"]["codigo"] == "SP-BBB-002"


def test_corrigido_e_tirada():
    """A revisão do PCM: o número corrigido vai ao Fracttal e a auditoria guarda também o do campo; a peça tirada do lote
    não grava (e mantém a situação que teria, para a tela mostrar o que ficou de fora)."""
    linhas = [_linha(1, 101, "3"), _linha(2, 102, "8"), _linha(3, 103, "1")]
    sis = _sis(s101=5, s102=5, s103=1)
    rev = {"tiradas": {"102": "peça emprestada a outra usina"}, "corrigidos": {"101": 6, "103": "abc"}}
    itens = _por_peca(C.itens_do_lote(linhas, sis, {}, rev))
    a, b, c = itens["101"], itens["102"], itens["103"]
    assert (a["contado_campo"], a["contado"], a["corrigido"], a["situacao"], a["delta"]) == (3.0, 6.0, True, "para_cima", 1.0)
    assert (b["tirada"], b["situacao"], b["contado"], b["corrigido"]) == (True, "para_cima", 8.0, False)
    assert (c["corrigido"], c["contado"], c["tirada"]) == (False, 1.0, False)         # correção ilegível não vale
    assert a["tirada"] is False
    # o corrigido pode ser o texto da tela, mas não negativo; "0" é zerar
    assert _por_peca(C.itens_do_lote(linhas, sis, {}, {"corrigidos": {"101": "0,0"}}))["101"]["situacao"] == "zerar"
    ruim = _por_peca(C.itens_do_lote(linhas, sis, {}, {"corrigidos": {"101": -2}}))["101"]
    assert (ruim["corrigido"], ruim["contado"]) == (False, 3.0)
    # sem revisão, ou com a revisão vazia
    for vazia in (None, {}, {"tiradas": None, "corrigidos": None}):
        assert not any(i["corrigido"] or i["tirada"] for i in C.itens_do_lote(linhas, sis, {}, vazia))


def test_ids_com_ponto_zero_acham_a_peca():
    """A API às vezes põe o ".0" no ID ("999.0"): a peça é a 999 na curadoria, na revisão e no estoque."""
    linhas = [_linha(1, "101.0", "2")]
    cur = {"9": {"decisao": "e_a_peca", "id_item": "101.0"}}
    itens = C.itens_do_lote(linhas + [_linha("9.0", tipo="fora_do_catalogo", contado="1")], _sis(s101=2), cur,
                            {"tiradas": {"101.0": "x"}})
    assert len(itens) == 1
    assert itens[0]["id_item"] == "101" and itens[0]["ligada"] is True and itens[0]["tirada"] is True
    assert itens[0]["contado"] == 3.0


def test_nao_mexe_nos_dados_que_recebe():
    linhas = [_linha(1, 101, "3"), _linha(2, 500, "4", tipo="identificar", **{"Identificado como": "201"}),
              _linha(3, tipo="fora_do_catalogo", contado="2")]
    sis = _sis(s101=2, s500=4)
    cur = {"2": {"decisao": "confirmar", "id_item": "201"}, "3": {"decisao": "e_a_peca", "id_item": "101"}}
    rev = {"tiradas": {"101": "x"}, "corrigidos": {"500": 1}}
    antes = copy.deepcopy((linhas, sis, cur, rev))
    C.itens_do_lote(linhas, sis, cur, rev)
    C.contado_efetivo(linhas, cur)
    assert (linhas, sis, cur, rev) == antes


# ── a substituição ──────────────────────────────────────────────────────────────────────────────────────────────────────
def _contagem(cid, contada_em, almox=ALMOX, enviada_em=None):
    return {"contagem_id": cid, "id_almox": almox, "contada_em": contada_em,
            "enviada_em": enviada_em or contada_em, "linhas": []}


def test_a_mais_nova_substitui():
    """Por almoxarifado, vale a contagem mais nova pelo "Contada em"; as mais velhas que ainda não foram gravadas ficam
    `substituída` (aprovar a velha depois da nova desfaria a nova). A gravada fica como está, e um almoxarifado não
    mexe no outro."""
    todas = [_contagem("velha", "2026-10-20T09:00:00Z"), _contagem("meio", "2026-10-22T09:00:00Z"),
             _contagem("nova", "2026-10-24T09:00:00Z"), _contagem("outro", "2026-10-10T09:00:00Z", almox="901")]
    assert C.substituidas(todas, set()) == {"velha", "meio"}
    assert C.substituidas(todas, {"meio"}) == {"velha"}
    assert C.substituidas(todas, {"velha", "meio", "nova"}) == set()
    assert C.substituidas(todas[:1], set()) == set()                 # sozinha, vale
    assert C.substituidas([], set()) == set() and C.substituidas(None, None) == set()


def test_contagem_sem_almoxarifado_nao_agrupa():
    """Sem o ID do almoxarifado não há de quem ser a mais nova: elas não se juntam num "almoxarifado vazio" (a mais nova
    delas substituiria as outras sem nenhum motivo)."""
    sem = [_contagem("s1", "2026-10-20T09:00:00Z", almox=""), _contagem("s2", "2026-10-22T09:00:00Z", almox=None),
           {"contagem_id": "s3", "contada_em": "2026-10-23T09:00:00Z"}]
    assert C.substituidas(sem, set()) == set()
    com = sem + [_contagem("velha", "2026-10-20T09:00:00Z"), _contagem("nova", "2026-10-24T09:00:00Z")]
    assert C.substituidas(com, set()) == {"velha"}


def test_a_mais_nova_e_pelo_instante_e_nao_pelo_texto():
    """O "Contada em" é um instante: 23:30 de Brasília do dia 24 (-03:00) é 02:30 UTC do dia 25, depois da 01:00Z do dia
    25, embora o texto "2026-10-24..." venha antes na ordem das letras."""
    a = _contagem("brasilia", "2026-10-24T23:30:00-03:00")
    b = _contagem("utc", "2026-10-25T01:00:00Z")
    assert C.substituidas([a, b], set()) == {"utc"}
    assert C.substituidas([b, a], set()) == {"utc"}                  # a ordem da lista não importa
    sem_fuso = _contagem("sem_fuso", "2026-10-25T03:00:00")           # sem fuso, é UTC (como o App grava)
    assert C.substituidas([a, sem_fuso], set()) == {"brasilia"}


def test_a_mais_nova_desempata_pelo_envio_e_pelo_id():
    a = _contagem("a", "2026-10-24T09:00:00Z", enviada_em="2026-10-24T09:05:00Z")
    b = _contagem("b", "2026-10-24T09:00:00Z", enviada_em="2026-10-24T09:30:00Z")
    assert C.substituidas([a, b], set()) == {"a"}                    # o enviado depois (a fila offline) vale
    c, d = _contagem("c", "2026-10-24T09:00:00Z"), _contagem("d", "2026-10-24T09:00:00Z")
    assert C.substituidas([c, d], set()) == {"c"} and C.substituidas([d, c], set()) == {"c"}


def test_contada_em_ilegivel_e_a_mais_velha():
    """Sem como ordenar, a de data ilegível não pode ser a que vale (nem se aprova: ver `aprovavel`)."""
    ruim, boa = _contagem("ruim", "ontem de manhã"), _contagem("boa", "2026-10-24T09:00:00Z")
    assert C.substituidas([ruim, boa], set()) == {"ruim"}
    assert C.substituidas([ruim], set()) == set()


# ── a recontagem só das peças marcadas (item 4 das melhorias de 30/10/2026) ──────────────────────────────────────────────
def _recontagem(cid, contada_em, de, almox=ALMOX):
    """A contagem que o App manda quando o PCM pede a recontagem de algumas peças: o "Recontagem de" é o ID da contagem em que
    o pedido foi feito."""
    return dict(_contagem(cid, contada_em, almox), recontagem_de=de)


def test_recontagem_nao_substitui_a_original():
    """A original (10:00) espera o PCM, que pediu a recontagem de duas peças; a recontagem chega (12:00) só com elas. Pela
    regra de antes ela seria "a mais nova" e substituiria a original inteira, e as outras peças perderiam a contagem (o
    desenho chama isso de falha mesmo funcionando). As duas ficam vivas, em qualquer ordem da lista."""
    original = _contagem("original", "2026-10-26T10:00:00Z")
    rec = _recontagem("rec", "2026-10-26T12:00:00Z", "original")
    assert C.substituidas([original, rec], set()) == set()
    assert C.substituidas([rec, original], set()) == set()


def test_original_mais_velha_nao_substitui_a_recontagem():
    """A recontagem fica fora da escolha da nova: a original, mais velha, não a substitui, a recontagem da recontagem (a R2
    aponta para a R1) também não, e a inteira mais nova segue substituindo as inteiras velhas como sempre. Gravada a
    original, a recontagem continua viva."""
    antiga = _contagem("antiga", "2026-10-25T09:00:00Z")
    original = _contagem("original", "2026-10-26T10:00:00Z")
    rec = _recontagem("rec", "2026-10-26T12:00:00Z", "original")
    rec2 = _recontagem("rec2", "2026-10-26T15:00:00Z", "rec")
    todas = [rec2, antiga, rec, original]
    assert C.substituidas(todas, set()) == {"antiga"}
    assert C.substituidas(todas, {"original"}) == {"antiga"}
    assert C.substituidas([rec, rec2], set()) == set()               # só recontagens: nenhuma é "a mais nova"


def test_inteira_nova_substitui_a_recontagem():
    """Uma contagem INTEIRA com "Contada em" depois da recontagem substitui a recontagem (e a original, como sempre). A inteira
    que veio entre a original e a recontagem substitui a original, mas não a recontagem, contada depois dela; e a inteira de
    outro almoxarifado não mexe em nada."""
    original = _contagem("original", "2026-10-26T10:00:00Z")
    rec = _recontagem("rec", "2026-10-26T12:00:00Z", "original")
    assert C.substituidas([original, rec, _contagem("nova", "2026-10-26T14:00:00Z")], set()) == {"original", "rec"}
    assert C.substituidas([original, rec, _contagem("meio", "2026-10-26T11:00:00Z")], set()) == {"original"}
    assert C.substituidas([original, rec, _contagem("outra", "2026-10-26T14:00:00Z", almox="901")], set()) == set()


def test_recontagem_gravada_fica():
    """A recontagem já gravada (ou gravando) fica como está quando a inteira nova chega: o que está no Fracttal não se desfaz."""
    original = _contagem("original", "2026-10-26T10:00:00Z")
    rec = _recontagem("rec", "2026-10-26T12:00:00Z", "original")
    nova = _contagem("nova", "2026-10-26T14:00:00Z")
    assert C.substituidas([original, rec, nova], {"rec"}) == {"original"}
    assert C.substituidas([original, rec, nova], {"rec", "original"}) == set()


def test_recontar_tira_do_lote():
    """A peça com a recontagem pedida sai do lote desta contagem (`recontar`, e `tirada` junto: todo caminho de hoje que deixa
    a tirada de fora, a gravação inclusive, deixa a recontada de fora) e guarda a situação que teria; as outras seguem."""
    linhas = [_linha(1, 101, "3"), _linha(2, 9, "8"), _linha(3, 103, ""), _linha(4, tipo="fora_do_catalogo", contado="1")]
    sis = _sis(s101=5, s9=5, s103=2)
    itens = C.itens_do_lote(linhas, sis, {}, {"recontar": {"9": "m"}})
    por = _por_peca(itens)
    assert (por["9"]["recontar"], por["9"]["tirada"], por["9"]["situacao"]) == (True, True, "para_cima")
    assert (por["101"]["recontar"], por["101"]["tirada"]) == (False, False)
    assert por["103"]["recontar"] is False
    assert all("recontar" in i for i in itens) and por[""]["recontar"] is False          # o achado fora do catálogo também
    # o que vai ao Fracttal (o filtro da gravação): a 101, que desce de 5 para 3; a 9 ficou de fora
    assert [i["id_item"] for i in itens if not i["tirada"] and i["situacao"] in C.MEXEM] == ["101"]
    # o ID com ".0" acha a peça, e a recontada e a tirada podem ser a mesma
    por = _por_peca(C.itens_do_lote(linhas, sis, {}, {"recontar": {"9.0": ""}, "tiradas": {"9": "x"}}))
    assert por["9"]["recontar"] and por["9"]["tirada"]
    for vazia in (None, {}, {"recontar": None}):
        assert not any(i["recontar"] for i in C.itens_do_lote(linhas, sis, {}, vazia))


# ── os avariados (30/10/2026, item 5 das melhorias): a aba Avariados do App, pelo código -AV ─────────────────────────────
# O catálogo do App com a boa SP-101 e a SP-101-AV (o item 901); a 102 não tem -AV. As linhas chegam às contas já resolvidas
# pela `leitura.ler` (o `avariados.resolver`), e é assim que os testes as passam.
CATALOGO_AV = {"101": {"codigo": "SP-101", "nome": "Fusível", "unidade": "unidade"},
               "901": {"codigo": "SP-101-AV", "nome": "[AVARIADO] Fusível", "unidade": "unidade"},
               "102": {"codigo": "SP-102", "nome": "Relé", "unidade": "unidade"}}


def _resolvidas(*linhas):
    from nexus.pcm.inventario import avariados
    return avariados.resolver(list(linhas), CATALOGO_AV)


def test_avariado_entra_no_lote_como_peca_av():
    """A avariada da SP-101 conta para a SP-101-AV como uma peça qualquer da contagem (contagem absoluta; a não ligada ao
    almoxarifado entra com o sistema 0 e a gravação a liga). A boa fica com a linha dela: avariado nunca tira do bom."""
    linhas = _resolvidas(_linha(1, 101, "5"), _linha(2, 101, "2", tipo="avariado"))
    por = _por_peca(C.itens_do_lote(linhas, _sis(s101=6, s901=3), {}, {}))
    assert (por["101"]["contado"], por["101"]["situacao"]) == (5.0, "para_baixo")
    av = por["901"]
    assert (av["codigo"], av["contado"], av["sistema"], av["situacao"], av["ligada"]) == ("SP-101-AV", 2.0, 3, "para_baixo", True)
    assert (av["dobro"], av["invalido"], av["tirada"]) == (False, False, False)
    av = _por_peca(C.itens_do_lote(linhas, _sis(s101=6), {}, {}))["901"]
    assert (av["ligada"], av["sistema"], av["situacao"]) == (False, 0.0, "para_cima")
    assert all("dobro" in i for i in C.itens_do_lote(linhas, {}, {}, {}))
    # a avariada sozinha (sem a linha da boa): a boa nem entra no lote
    assert [i["id_item"] for i in C.itens_do_lote(_resolvidas(_linha(2, 101, "2", tipo="avariado")), {}, {}, {})] == ["901"]


def test_avariado_nao_resolvido_vai_a_curadoria():
    """Sem o -AV no catálogo, a avariada segue o caminho do achado fora do catálogo: pendência sem `id_item` até a decisão
    da curadoria ("cadastrar" e "é a peça X" levam as unidades à peça da decisão; "descartar" as joga fora). A decisão que não é
    do tipo da linha não resolve nada. A avariada sem o ID da boa não é de peça nenhuma."""
    linhas = _resolvidas(_linha(1, 102, "4"), _linha(2, 102, "3", tipo="avariado"))
    itens = C.itens_do_lote(linhas, _sis(s102=4), {}, {})
    assert [(i["id_item"], i["situacao"], i["pendentes"]) for i in itens] == [("102", "sem_alteracao", []),
                                                                                ("", "curadoria", ["2"])]
    for dec in ({"decisao": "cadastrar", "id_item": "777", "codigo": "SP-102-AV"}, {"decisao": "e_a_peca", "id_item": "777"}):
        por = _por_peca(C.itens_do_lote(linhas, _sis(s102=4), {"2": dec}, {}))
        assert set(por) == {"102", "777"} and por["777"]["contado"] == 3.0 and por["102"]["contado"] == 4.0
    assert set(_por_peca(C.itens_do_lote(linhas, {}, {"2": {"decisao": "descartar"}}, {}))) == {"102"}
    assert _por_peca(C.itens_do_lote(linhas, {}, {"2": {"decisao": "confirmar", "id_item": "777"}}, {}))[""]["pendentes"] == ["2"]
    sem_id = _resolvidas(_linha(3, "", "3", tipo="avariado", **{"Código": ""}))
    assert C.itens_do_lote(sem_id, {}, {}, {}) == [] and C.contado_efetivo(sem_id, {}) == {}


def test_avariado_em_dobro_fora_do_lote():
    """A mesma contagem com a SP-101-AV contada direto (Tipo `item`) E pela aba Avariados: somar contaria duas vezes a mesma
    peça. A peça fica `dobro`, com `invalido` junto (o caminho do contado inválido de hoje): não contada, fora do N do gravar
    até o PCM corrigir. A boa não é afetada."""
    linhas = _resolvidas(_linha(1, 101, "5"), _linha(2, 901, "3"), _linha(3, 101, "2", tipo="avariado"))
    itens = C.itens_do_lote(linhas, _sis(s101=5, s901=1), {}, {})
    av = _por_peca(itens)["901"]
    assert (av["dobro"], av["invalido"], av["contado"], av["contado_campo"], av["situacao"]) == (
        True, True, None, None, "nao_tocada")
    assert _por_peca(itens)["101"]["dobro"] is False
    assert [i["id_item"] for i in itens if i["id_item"] and not i["tirada"] and i["situacao"] in C.MEXEM] == []
    assert C.contado_efetivo(linhas, {})["901"] is None
    # a ordem das linhas não importa, e duas linhas da aba (sem a direta) somam, como duas linhas da mesma peça
    invertidas = _resolvidas(_linha(3, 101, "2", tipo="avariado"), _linha(2, 901, "3"))
    assert _por_peca(C.itens_do_lote(invertidas, {}, {}, {}))["901"]["dobro"] is True
    duas_da_aba = _resolvidas(_linha(3, 101, "2", tipo="avariado"), _linha(4, 101, "1", tipo="avariado"))
    av = _por_peca(C.itens_do_lote(duas_da_aba, {}, {}, {}))["901"]
    assert (av["dobro"], av["contado"]) == (False, 3.0)
    # contado em dobro é com número dos dois lados: a direta em branco não conta duas vezes nada
    uma_em_branco = _resolvidas(_linha(2, 901, ""), _linha(3, 101, "2", tipo="avariado"))
    av = _por_peca(C.itens_do_lote(uma_em_branco, {}, {}, {}))["901"]
    assert (av["dobro"], av["contado"]) == (False, 2.0)


def test_dobro_corrigido_entra():
    """O PCM corrige o número da peça em dobro (o motivo vai à auditoria): ela entra no lote como qualquer outra, com o número
    dele, e segue marcada `dobro` para a nota dizer de onde veio."""
    linhas = _resolvidas(_linha(2, 901, "3"), _linha(3, 101, "2", tipo="avariado"))
    av = _por_peca(C.itens_do_lote(linhas, _sis(s901=1), {}, {"corrigidos": {"901": "2"}}))["901"]
    assert (av["dobro"], av["corrigido"], av["contado"], av["situacao"]) == (True, True, 2.0, "para_cima")
    assert av["contado_campo"] is None


def test_avariado_em_branco_nao_zera():
    """A avariada em branco é "não contei": a SP-101-AV com saldo 4 não é zerada; e a sem -AV em branco nem vira pendência."""
    av = _por_peca(C.itens_do_lote(_resolvidas(_linha(2, 101, "", tipo="avariado")), _sis(s901=4), {}, {}))["901"]
    assert (av["contado"], av["situacao"]) == (None, "nao_tocada")
    assert C.itens_do_lote(_resolvidas(_linha(2, 102, "", tipo="avariado")), {}, {}, {}) == []
    # o 0 digitado na aba é zerar o -AV (contagem absoluta, como a linha da própria peça)
    av = _por_peca(C.itens_do_lote(_resolvidas(_linha(2, 101, "0", tipo="avariado")), _sis(s901=4), {}, {}))["901"]
    assert (av["contado"], av["situacao"]) == (0.0, "zerar")


def test_a_decisao_da_curadoria_vence_a_resolucao():
    """A avariada decidida quando o -AV ainda não estava no catálogo do App (descartada, ou levada a uma peça) e que depois
    passa a se resolver (a varredura do dia seguinte trouxe o -AV, criado por outra contagem): vale a decisão do PCM. Sem isso o
    "descartar" sumia em silêncio, e as unidades descartadas iam ao Fracttal."""
    linhas = _resolvidas(_linha(2, 101, "2", tipo="avariado"))
    assert C.itens_do_lote(linhas, {}, {"2": {"decisao": "descartar"}}, {}) == []
    por = _por_peca(C.itens_do_lote(linhas, {}, {"2": {"decisao": "e_a_peca", "id_item": "777"}}, {}))
    assert set(por) == {"777"} and por["777"]["contado"] == 2.0
    # a decisão de outro tipo (o confirmar é do genérico) não é da avariada: a resolução vale
    assert set(_por_peca(C.itens_do_lote(linhas, {}, {"2": {"decisao": "confirmar", "id_item": "777"}}, {}))) == {"901"}


# ── a janela de aprovação ───────────────────────────────────────────────────────────────────────────────────────────────
def test_aprovavel_ate_90_dias():
    """Os 7 dias do rascunho valiam enquanto não houvesse jeito de saber o que se moveu depois da contagem; o passo 0
    achou o histórico do almoxarifado, e o conflito sai dele na gravação. Os 90 dias são a janela do livro do App."""
    def antes(dias, **k):
        return (AGORA - timedelta(days=dias, **k)).isoformat().replace("+00:00", "Z")

    assert C.APROVAVEL_DIAS == 90
    assert C.aprovavel(antes(89), AGORA) is True
    assert C.aprovavel(antes(90), AGORA) is True                      # até 90 dias
    assert C.aprovavel(antes(91), AGORA) is False
    assert C.aprovavel(antes(8), AGORA) is True                       # o limite de 7 dias não vale mais...
    assert C.aprovavel(antes(8), AGORA, dias=7) is False              # ...mas o parâmetro segue valendo
    assert C.aprovavel(antes(0), AGORA) is True
    for ilegivel in ("", "ontem", None, "2026-13-45T00:00:00Z"):
        assert C.aprovavel(ilegivel, AGORA) is False                  # sem a data não há o que olhar depois dela


def test_aprovavel_com_fuso_e_relogio():
    assert C.aprovavel("2026-10-20T09:00:00-03:00", AGORA) is True
    assert C.aprovavel("2026-10-20T09:00:00", AGORA.replace(tzinfo=None)) is True       # sem fuso é UTC, dos dois lados
    assert C.aprovavel("2026-07-20T09:00:00", AGORA.replace(tzinfo=None)) is False
    assert C.aprovavel(datetime(2026, 10, 1, tzinfo=timezone.utc).isoformat(), AGORA) is True


def test_aprovavel_nao_aceita_contagem_do_futuro():
    """O relógio do celular adiantado de dias esconderia todo movimento do Fracttal (a conferência olha o que se moveu
    DEPOIS do "Contada em"): uma contagem de um dia que ainda não chegou não se aprova. Poucos minutos de relógio
    adiantado são normais."""
    assert C.aprovavel((AGORA + timedelta(minutes=10)).isoformat(), AGORA) is True
    assert C.aprovavel((AGORA + timedelta(hours=3)).isoformat(), AGORA) is False
    assert C.aprovavel((AGORA + timedelta(days=30)).isoformat(), AGORA) is False


# ── puro ────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_modulo_e_puro():
    """Sem rede, sem Flask, sem banco, sem arquivo: dicts entram e dicts saem (quem lê o livro e quem grava chama as
    contas; as contas não chamam ninguém)."""
    arvore = ast.parse(Path(C.__file__).read_text("utf-8"))
    importados = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            importados |= {a.name.split(".")[0] for a in no.names}
        elif isinstance(no, ast.ImportFrom) and no.module:
            importados.add(("." * no.level + no.module).lstrip("."))
    proibidos = {"flask", "requests", "urllib", "socket", "http", "sqlite3", "psycopg2", "sqlalchemy", "os", "subprocess",
                 "pathlib", "shutil", "json", "threading"}
    assert not {m.split(".")[0] for m in importados} & proibidos, importados

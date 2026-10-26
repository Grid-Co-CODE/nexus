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
    """Uma linha do livro das contagens do jeito que a API a devolve: as 14 colunas, tudo como texto."""
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

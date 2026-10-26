"""O adaptador do estoque do Fracttal e o Fracttal de mentira (inventário do almoxarifado, 26/10/2026).

O adaptador (`nexus/pcm/inventario/estoque.py`) é a ÚNICA porta de leitura e gravação de estoque: a gravação, a régua e a
curadoria só falam com ele (ou com o `EstoqueFalso`, que cumpre o mesmo contrato). Os métodos, os corpos e as respostas
daqui são os que o passo 0 de 26/10 leu da própria tela do Fracttal (`docs/superpowers/specs/2026-10-26-inventario-
almoxarifado-passo0.md`); nada aqui vai ao Fracttal: o `_rpc_call` é um gravador. Dado de mentira, sem nome de gente."""
import base64
import inspect
import json
import time

import pytest

from estoque_falso import EstoqueFalso
from nexus.pcm.inventario import estoque as E

ALMOX, ITEM, LIGACAO = "134082", "53248312", "15535397"          # o almoxarifado e a peça de teste do passo 0

LISTA = "inventories.warehouses_list"
SALDOS = "inventories.warehouses_items_stock"
LIGAR = "inventories.associate_warehouses_insert"
MODO = "inventories.warehouse_change_mode"
ATUALIZA_ALMOX = "inventories.warehouse_update"
ATUALIZA_LIGACAO = "inventories.warehouses_items_update"
FECHAR = "inventories.warehouse_finalize_mode"
HISTORICO = "inventories.movement_history_list_new"
CRIAR = "inventories.item_insert"
PECAS = "inventories.items_list"
UNIDADES = "companies.units_list"


# ── os instrumentos: um Fracttal que grava o que lhe pedem, um relógio que não espera de verdade ────────────────────────
class FracttalError(Exception):
    """O `FracttalError` do `api.py` do OS Creator (o teste do `api` de verdade está mais abaixo)."""


class SessionExpired(FracttalError):
    session_expired = True           # o marcador que o `api.py` põe na classe para quem não a importa


class Relogio:
    """O tempo de mentira: `dormir` só anda o relógio, e o teste nunca espera de verdade."""

    def __init__(self):
        self.agora, self.dormiu = 1000.0, []

    def __call__(self):
        return self.agora

    def dormir(self, s):
        self.dormiu.append(s)
        self.agora += s


class Fracttal:
    """O `_rpc_call` de mentira. `respostas`: método -> a resposta, a lista de respostas (uma por pedido, em ordem) ou
    uma função dos parâmetros; uma exceção no lugar da resposta é levantada. Guarda os pedidos como JSON."""

    def __init__(self, respostas=None):
        self.respostas, self.pedidos = dict(respostas or {}), []

    def __call__(self, metodo, params):
        self.pedidos.append((metodo, json.loads(json.dumps(params))))
        if metodo not in self.respostas:
            raise AssertionError(f"pedido que o teste não esperava: {metodo}")
        r = self.respostas[metodo]
        if isinstance(r, list):
            r = r.pop(0)
        elif callable(r):
            r = r(params)
        if isinstance(r, Exception):
            raise r
        return r

    @property
    def metodos(self):
        return [m for m, _ in self.pedidos]


def em_paginas(linhas):
    """A lista do Fracttal: respeita o `start` e o `limit` do pedido e diz o `total`."""
    def resposta(params):
        i, n = params["start"], params["limit"]
        return {"success": True, "data": linhas[i:i + n], "total": len(linhas)}
    return resposta


def ok(data=None):
    return {"success": True, "data": data}


def estoque(fr, relogio=None, **kw):
    relogio = relogio or Relogio()
    return E.EstoqueFracttal(fr, relogio=relogio, dormir=relogio.dormir, **kw)


def linha_de_saldo(ligacao, item, codigo, stock, minimo, maximo):
    return {"id": int(ligacao), "id_item": int(item), "code": codigo, "field_1": "Peça de teste", "id_type_item": 4,
            "active": True, "id_warehouse": int(ALMOX), "stock": stock, "min_stock_level": minimo,
            "max_stock_level": maximo, "reorder_level": 0, "stock_temp": 0, "qty_assigned": 0, "lots": []}


PECA_DE_TESTE = linha_de_saldo(LIGACAO, ITEM, "SP-TST-001", 5, 1, 4)


# ── ler ────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_ler_pede_como_a_tela():
    """O corpo é o que a tela do Fracttal manda (passo 0): 200 por página, o almoxarifado em `id_warehouse`."""
    fr = Fracttal({SALDOS: em_paginas([PECA_DE_TESTE])})
    estoque(fr).ler(ALMOX)
    assert fr.pedidos == [(SALDOS, {"filter": [], "sort": [], "page": 1, "limit": 200, "start": 0, "is_tree": False,
                                    "node": None, "id_warehouse": 134082})]


def test_ler_monta_saldo_minimo_maximo_e_ligacao():
    """Duas páginas e um `stock` nulo: o nulo é "não informado" (None), nunca 0; o 0 de verdade continua 0; o mínimo que
    vem como texto ("1") vira número; a ligação (o `id` da linha) e o código vêm junto."""
    linhas = [linha_de_saldo(LIGACAO, ITEM, "SP-TST-001", 5, "1", 4),
              linha_de_saldo("15535398", "53248313", "SP-TST-002", None, None, None),
              linha_de_saldo("15535399", "53248314", "SP-TST-003", 0, 0, 0)]
    fr = Fracttal({SALDOS: em_paginas(linhas)})
    lido = estoque(fr, pagina=2).ler(ALMOX)
    assert lido == {
        "53248312": {"saldo": 5.0, "minimo": 1.0, "maximo": 4.0, "ligacao": LIGACAO, "codigo": "SP-TST-001"},
        "53248313": {"saldo": None, "minimo": None, "maximo": None, "ligacao": "15535398", "codigo": "SP-TST-002"},
        "53248314": {"saldo": 0.0, "minimo": 0.0, "maximo": 0.0, "ligacao": "15535399", "codigo": "SP-TST-003"},
    }
    assert lido["53248312"]["saldo"] is not None and lido["53248314"]["saldo"] == 0 and lido["53248313"]["saldo"] is None
    assert [(p["page"], p["start"], p["limit"]) for _, p in fr.pedidos] == [(1, 0, 2), (2, 2, 2)]


def test_ler_nao_pede_a_pagina_depois_do_total():
    """A página cheia que fecha o `total` é a última: pedir mais gastaria a cota da empresa (200/min) à toa."""
    fr = Fracttal({SALDOS: em_paginas([PECA_DE_TESTE, linha_de_saldo("15535398", "53248313", "SP-TST-002", 1, 0, 0)])})
    assert len(estoque(fr, pagina=2).ler(ALMOX)) == 2 and len(fr.pedidos) == 1


def test_ler_uma_linha_sem_peca_nao_passa_calada():
    fr = Fracttal({SALDOS: ok([{"id": 1, "stock": 3}])})
    with pytest.raises(E.ErroFracttal):
        estoque(fr).ler(ALMOX)


def test_ler_um_numero_que_nao_e_numero_nao_vira_zero_nem_vazio():
    fr = Fracttal({SALDOS: ok([linha_de_saldo(LIGACAO, ITEM, "SP-TST-001", "abc", 1, 4)])})
    with pytest.raises(E.ErroFracttal):
        estoque(fr).ler(ALMOX)


# ── o modo do almoxarifado ───────────────────────────────────────────────────────────────────────────────────────────
def test_modo_le_o_mode_do_almoxarifado():
    fr = Fracttal({LISTA: em_paginas([{"id": 134082, "code": "TESTE-INVENTARIO", "mode": 2, "active": True},
                                      {"id": 134083, "code": "OUTRO", "mode": 3, "active": False},
                                      {"id": 134084, "code": "NORMAL", "mode": 0, "active": True}])})
    est = estoque(fr)
    assert (est.modo("134082"), est.modo("134083"), est.modo("134084")) == (2, 3, 0)
    assert fr.pedidos[0] == (LISTA, {"filter": [], "sort": [], "page": 1, "limit": 200, "start": 0, "is_tree": False,
                                     "node": None})
    with pytest.raises(E.ErroFracttal):
        est.modo("999")                                  # almoxarifado que não existe: não é "modo normal"


# ── a sessão de ajuste: abrir, gravar, fechar ────────────────────────────────────────────────────────────────────────────
def _fracttal_do_ajuste():
    return Fracttal({SALDOS: em_paginas([PECA_DE_TESTE]), MODO: ok(), ATUALIZA_ALMOX: ok(), ATUALIZA_LIGACAO: ok(),
                     FECHAR: ok({"folio_return": 7, "total": 0})})


def test_ajuste_abre_grava_e_fecha_com_a_referencia():
    """O passo 0 de 26/10, na ordem da tela: abre (muda o modo e atualiza o almoxarifado), grava o saldo da peça pela
    ligação, fecha com a referência na `description` e volta o almoxarifado ao modo 0. Devolve o `folio_return`."""
    fr = _fracttal_do_ajuste()
    est = estoque(fr)
    est.ler(ALMOX)                                       # a ligação da peça vem daqui
    est.abrir_ajuste(ALMOX)
    est.gravar_saldo(ALMOX, ITEM, 5.0)
    assert est.fechar_ajuste(ALMOX, "INVENTARIO-c1") == "7"
    assert fr.pedidos[1:] == [
        (MODO, {"id_warehouse": 134082, "mode": 2}),
        (ATUALIZA_ALMOX, {"id": 134082, "mode": 2}),
        (ATUALIZA_LIGACAO, {"id": 15535397, "stock": 5}),
        (FECHAR, {"id_warehouse": 134082, "description": "INVENTARIO-c1"}),
        (ATUALIZA_ALMOX, {"id": 134082, "mode": 0}),
    ]


def test_o_saldo_inteiro_vai_como_inteiro_e_o_quebrado_como_quebrado():
    fr = _fracttal_do_ajuste()
    est = estoque(fr)
    est.ler(ALMOX)
    est.gravar_saldo(ALMOX, ITEM, 2.0)
    est.gravar_saldo(ALMOX, ITEM, 2.5)
    assert [p["stock"] for m, p in fr.pedidos if m == ATUALIZA_LIGACAO] == [2, 2.5]
    assert [type(p["stock"]) for m, p in fr.pedidos if m == ATUALIZA_LIGACAO] == [int, float]


def test_gravar_saldo_sem_ler_antes_le_a_ligacao_e_peca_nao_ligada_e_erro():
    fr = _fracttal_do_ajuste()
    est = estoque(fr)
    est.gravar_saldo(ALMOX, ITEM, 5)
    assert fr.metodos == [SALDOS, ATUALIZA_LIGACAO]      # leu a ligação e gravou
    est.gravar_saldo(ALMOX, ITEM, 6)
    assert fr.metodos == [SALDOS, ATUALIZA_LIGACAO, ATUALIZA_LIGACAO]      # a ligação guardada: sem ler de novo
    antes = len(fr.pedidos)
    with pytest.raises(ValueError):
        est.gravar_saldo(ALMOX, "999", 1)                # nunca ligada: não há ligação para gravar
    assert [m for m, _ in fr.pedidos[antes:]] == [SALDOS]            # tentou ler de novo, não gravou


def test_gravar_saldo_recusa_o_que_nao_e_contagem():
    fr = _fracttal_do_ajuste()
    est = estoque(fr)
    for ruim in (-1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            est.gravar_saldo(ALMOX, ITEM, ruim)
    assert fr.pedidos == []


def test_fechar_sem_referencia_nao_vai_ao_fracttal():
    """A referência na `description` é o que a retomada procura para saber se o fechamento valeu."""
    fr = _fracttal_do_ajuste()
    with pytest.raises(ValueError):
        estoque(fr).fechar_ajuste(ALMOX, "  ")
    assert fr.pedidos == []


def test_ligar_manda_o_corpo_da_tela_e_guarda_a_ligacao():
    fr = Fracttal({LIGAR: ok({"id": 15535397, "stock": 0}), ATUALIZA_LIGACAO: ok()})
    est = estoque(fr)
    assert est.ligar(ALMOX, ITEM) == LIGACAO
    est.gravar_saldo(ALMOX, ITEM, 5)                     # a ligação do `ligar` basta: não relê o almoxarifado
    assert fr.pedidos == [
        (LIGAR, {"id_warehouse": 134082, "id_item": 53248312, "location": "", "stock": 0, "min_stock_level": 0,
                 "max_stock_level": 0, "reorder_level": 0}),
        (ATUALIZA_LIGACAO, {"id": 15535397, "stock": 5})]


def test_ligar_sem_a_ligacao_na_resposta_e_erro():
    with pytest.raises(E.ErroFracttal):
        estoque(Fracttal({LIGAR: ok(None)})).ligar(ALMOX, ITEM)


# ── os erros: o corpo (sucesso falso), o limite, o login ──────────────────────────────────────────────────────────────────
def test_sucesso_falso_vira_erro_fracttal():
    """O Fracttal responde HTTP 200 com `success: false` e a mensagem (caso real do passo 0: desativar a peça com saldo,
    `ASSET_CANNOT_BE_DESABLED_STOCK`). O `_rpc_call` do OS Creator devolve isso sem levantar: o adaptador confere."""
    recusa = {"success": False, "message": "ASSET_CANNOT_BE_DESABLED_STOCK", "data": None}
    fr = Fracttal({LIGAR: recusa, ATUALIZA_LIGACAO: recusa, FECHAR: recusa, ATUALIZA_ALMOX: ok(), SALDOS: recusa})
    est = estoque(fr)
    for chamada in (lambda: est.ligar(ALMOX, ITEM), lambda: est.ler(ALMOX), lambda: est.fechar_ajuste(ALMOX, "INVENTARIO-c1")):
        with pytest.raises(E.ErroFracttal, match="ASSET_CANNOT_BE_DESABLED_STOCK") as erro:
            chamada()
        assert erro.value.mensagem == "ASSET_CANNOT_BE_DESABLED_STOCK"
    # fechar que o Fracttal recusou não segue para o "volta ao modo 0": o almoxarifado fica como está, para a retomada ver
    assert ATUALIZA_ALMOX not in fr.metodos


def test_sucesso_falso_na_gravacao_do_saldo():
    fr = Fracttal({SALDOS: em_paginas([PECA_DE_TESTE]), ATUALIZA_LIGACAO: {"success": False, "message": "WAREHOUSE_LOCKED"}})
    with pytest.raises(E.ErroFracttal, match="WAREHOUSE_LOCKED"):
        estoque(fr).gravar_saldo(ALMOX, ITEM, 5)


def test_resposta_sem_corpo_e_erro():
    with pytest.raises(E.ErroFracttal):
        estoque(Fracttal({SALDOS: None})).ler(ALMOX)


def test_429_vira_limite():
    """O `_rpc_call` do OS Creator levanta `FracttalError("RPC <método> HTTP 429 ...")` no limite de 200/min da empresa."""
    fr = Fracttal({SALDOS: FracttalError("RPC inventories.warehouses_items_stock HTTP 429 — Too Many Requests")})
    with pytest.raises(E.Limite) as erro:
        estoque(fr).ler(ALMOX)
    assert "429" in str(erro.value) and isinstance(erro.value.__cause__, FracttalError)


@pytest.mark.parametrize("erro", [
    SessionExpired("Login recusado (HTTP 401) — faça login de novo no app."),
    SessionExpired("Sua sessão do Fracttal expirou ou foi encerrada. Faça login de novo."),
    FracttalError("Você não está logado no Fracttal. Faça login no app (e-mail + senha)."),
    FracttalError("O JWT do login do Fracttal expirou — cole um novo em fracttal_login.txt."),
])
def test_login_recusado_vira_sem_login(erro):
    with pytest.raises(E.SemLogin):
        estoque(Fracttal({SALDOS: erro})).ler(ALMOX)


def test_o_resto_dos_erros_passa_como_veio():
    """Rede fora e 500 não são limite nem login: quem grava decide (a resposta pode ter se perdido DEPOIS de gravar)."""
    for erro in (FracttalError("RPC x HTTP 500 — erro"), ConnectionError("rede fora"), TimeoutError("demorou")):
        with pytest.raises(type(erro)) as visto:
            estoque(Fracttal({SALDOS: erro})).ler(ALMOX)
        assert visto.value is erro


# ── o ritmo ────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_ritmo_de_um_pedido_por_segundo():
    """A cota de 200/min é da EMPRESA (robôs e App de Campo gastam dela): cada pedido do adaptador espera o segundo dele.
    O relógio é de mentira: 3 chamadas levam pelo menos 2 s, e o teste não espera de verdade."""
    fr = Fracttal({LISTA: ok([{"id": 134082, "mode": 0}])})
    relogio = Relogio()
    est = estoque(fr, relogio)
    t0 = relogio()
    for _ in range(3):
        est.modo(ALMOX)
    assert relogio() - t0 >= 2 and len(fr.pedidos) == 3
    assert relogio.dormiu == [1.0, 1.0]                  # o 1º pedido sai na hora


def test_o_pedido_lento_nao_ganha_espera_a_mais():
    """O segundo conta do INÍCIO de um pedido ao início do outro: o Fracttal que levou 1,5 s já pagou o intervalo."""
    relogio = Relogio()
    fr = Fracttal({LISTA: lambda p: relogio.dormir(1.5) or ok([{"id": 134082, "mode": 0}])})
    est = estoque(fr, relogio)
    est.modo(ALMOX)
    relogio.dormiu.clear()
    est.modo(ALMOX)
    assert relogio.dormiu == [1.5]                       # só a demora do próprio pedido; nenhuma espera do ritmo


def test_o_ritmo_vale_para_as_paginas_tambem():
    linhas = [linha_de_saldo(str(100 + i), str(200 + i), f"SP-TST-{i:03d}", 1, 0, 0) for i in range(5)]
    relogio = Relogio()
    t0 = relogio()
    estoque(Fracttal({SALDOS: em_paginas(linhas)}), relogio, pagina=2).ler(ALMOX)
    assert relogio() - t0 >= 2                           # 3 páginas = 3 pedidos


# ── a régua ────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_regua_so_manda_o_que_veio():
    """Provado em 26/10, fora do modo de ajuste: só `min_stock_level` e `max_stock_level` (como texto, o que a tela manda),
    sem tocar no saldo e sem gerar movimento. O que é None não vai: a régua que ficou como estava segue como estava."""
    fr = Fracttal({SALDOS: em_paginas([PECA_DE_TESTE]), ATUALIZA_LIGACAO: ok()})
    est = estoque(fr)
    est.definir_regua(ALMOX, ITEM, 2, 6)
    est.definir_regua(ALMOX, ITEM, 3.5, None)
    est.definir_regua(ALMOX, ITEM, None, 8)
    est.definir_regua(ALMOX, ITEM, None, None)           # nada a mandar: nem pedido
    assert [(m, p) for m, p in fr.pedidos if m == ATUALIZA_LIGACAO] == [
        (ATUALIZA_LIGACAO, {"id": 15535397, "min_stock_level": "2", "max_stock_level": "6"}),
        (ATUALIZA_LIGACAO, {"id": 15535397, "min_stock_level": "3.5"}),
        (ATUALIZA_LIGACAO, {"id": 15535397, "max_stock_level": "8"})]
    assert all("stock" not in p for m, p in fr.pedidos if m == ATUALIZA_LIGACAO)


def test_regua_recusa_o_que_nao_e_nivel():
    fr = Fracttal({SALDOS: em_paginas([PECA_DE_TESTE]), ATUALIZA_LIGACAO: ok()})
    for ruim in ((-1, 4), (1, float("nan")), (5, 2)):    # negativo, não-número e mínimo acima do máximo
        with pytest.raises(ValueError):
            estoque(fr).definir_regua(ALMOX, ITEM, *ruim)
    assert ATUALIZA_LIGACAO not in fr.metodos


# ── o histórico: achar o movimento e o que se moveu ────────────────────────────────────────────────────────────────────
def mov(folio, item, quando, descricao, tipo=15, estado=1, pessoa="Nome Inventado da Silva"):
    return {"folio": folio, "id_movements": 84000000 + int(folio.split("-")[1]), "id_item": int(item), "code": "SP-TST-001",
            "id_movement_type": tipo, "id_movement_state": estado, "id_warehouse_source": None,
            "id_warehouse_target": 134082, "qty": 5, "date": quando[:10], "date_create": quando,
            "description": descricao, "document": "---", "responsible_description": pessoa}


# do mais novo para o mais velho, como o Fracttal devolve (sort por date_create desc)
HIST = [mov("MOV-6", ITEM, "2026-10-26T15:00:16.570424+00:00", "INVENTARIO-c1"),
        mov("MOV-5", ITEM, "2026-10-26T15:00:16.570000+00:00", "INVENTARIO-c1", estado=2),
        mov("MOV-4", "53248313", "2026-10-26T14:30:00+00:00", "Consumo da OS 16000", tipo=2, estado=2),
        mov("MOV-3", "53248314", "2026-10-26T13:00:00+00:00", "Entrada de compra", tipo=1),
        mov("MOV-2", "53248315", "2026-10-25T09:00:00+00:00", "Consumo antigo", tipo=2, estado=2),
        mov("MOV-1", "53248316", "2026-10-24T09:00:00+00:00", "Entrada antiga", tipo=1)]


def test_achar_movimento_pela_referencia():
    fr = Fracttal({HISTORICO: em_paginas(HIST)})
    est = estoque(fr, pagina=2)
    assert est.achar_movimento(ALMOX, "INVENTARIO-c1") == "MOV-6"
    assert est.achar_movimento(ALMOX, "INVENTARIO-c") is None       # a referência inteira, não um pedaço dela
    assert est.achar_movimento(ALMOX, "INVENTARIO-c9") is None
    assert fr.pedidos[0] == (HISTORICO, {"sort": [{"property": "date_create", "direction": "desc"}], "page": 1,
                                         "limit": 2, "start": 0, "is_tree": False, "node": None, "id_warehouse": 134082})


def test_achar_movimento_para_na_primeira_pagina_que_acha():
    fr = Fracttal({HISTORICO: em_paginas(HIST)})
    estoque(fr, pagina=2).achar_movimento(ALMOX, "INVENTARIO-c1")
    assert len(fr.pedidos) == 1


def test_mexidas_desde_para_na_data_e_ignora_a_referencia():
    """As peças com movimento depois do "Contada em" (ISO UTC), sem os movimentos do próprio ajuste. A lista vem do mais
    novo ao mais velho: para na primeira que passa da data, sem ler o resto do histórico (a cota é de todos)."""
    fr = Fracttal({HISTORICO: em_paginas(HIST)})
    est = estoque(fr, pagina=2)
    mexidas = est.mexidas_desde(ALMOX, "2026-10-26T13:00:00Z", ignorar_referencia="INVENTARIO-c1")
    assert mexidas == {"53248313", "53248314"}           # o ajuste fora; o de 13:00 em ponto ainda conta (>= a data)
    assert len(fr.pedidos) == 3                          # a 3ª página traz a MOV-2 (de ontem) e fecha; não há 4ª
    assert est.mexidas_desde(ALMOX, "2026-10-26T13:00:01+00:00", ignorar_referencia="INVENTARIO-c1") == {"53248313"}
    # sem ignorar, o ajuste conta; fuso de Brasília na data: 12:00 -03:00 = 15:00 UTC
    assert est.mexidas_desde(ALMOX, "2026-10-26T12:00:00-03:00") == {ITEM}
    assert est.mexidas_desde(ALMOX, "2026-10-27T00:00:00") == set()  # sem fuso = UTC; nada depois


def test_mexidas_desde_nao_le_alem_da_data():
    fr = Fracttal({HISTORICO: em_paginas(HIST)})
    estoque(fr, pagina=2).mexidas_desde(ALMOX, "2026-10-26T14:00:00Z")
    assert len(fr.pedidos) == 2 and fr.pedidos[-1][1]["start"] == 2   # MOV-3 (13:00) está na 2ª página e já é velha


def test_mexidas_desde_data_ruim_e_erro_de_quem_chama():
    with pytest.raises(ValueError):
        estoque(Fracttal({HISTORICO: em_paginas(HIST)})).mexidas_desde(ALMOX, "ontem")


def test_nunca_devolve_o_nome_do_responsavel():
    """`responsible_description` do histórico é nome de pessoa: o repositório e a API são compartilhados, e o nome ao lado
    de um movimento é dado pessoal ligado a trabalho. O adaptador não devolve nem guarda."""
    fr = Fracttal({HISTORICO: em_paginas(HIST)})
    est = estoque(fr, pagina=2)
    saidas = [est.achar_movimento(ALMOX, "INVENTARIO-c1"), est.achar_movimento(ALMOX, "nada"),
              est.mexidas_desde(ALMOX, "2026-10-24T00:00:00Z"), est.mexidas_desde(ALMOX, "2026-10-24T00:00:00Z", "x")]
    assert "Nome Inventado" not in repr(saidas) and "Nome Inventado" not in repr(vars(est))
    assert "responsible" not in repr(saidas).lower() and "responsible" not in repr(vars(est)).lower()


# ── a peça: criar e os códigos que existem ───────────────────────────────────────────────────────────────────────────────
def test_criar_peca_acha_a_unidade_e_manda_o_corpo_da_tela():
    fr = Fracttal({UNIDADES: ok([{"id": 362333, "description": "METRO"}, {"id": 362334, "description": "UNIDADE"}]),
                   CRIAR: ok({"id": 53248312, "description": "Peça de teste    { SP-TST-001 }"})})
    est = estoque(fr)
    assert est.criar_peca("SP-TST-001", "Peça de teste do inventário (Nexus)") == ITEM
    assert est.criar_peca("SP-TST-002", "Outra peça", "unidade") == ITEM
    assert fr.metodos == [UNIDADES, CRIAR, CRIAR]        # as unidades se leem uma vez só
    assert fr.pedidos[1] == (CRIAR, {
        "id_type_item": 4, "field_1": "Peça de teste do inventário (Nexus)", "code": "SP-TST-001", "id_unit": 362334,
        "units_description": "UNIDADE", "active": True, "description": "", "is_serial_control": False,
        "is_lot_control": False, "visible_to_all": False, "ids_batch": [], "associate_warehouses": [],
        "associate_third_parties": [], "attached": [], "files": [], "custom_fields": []})


def test_criar_peca_com_unidade_que_nao_existe_nao_cria():
    fr = Fracttal({UNIDADES: ok([{"id": 362334, "description": "UNIDADE"}]), CRIAR: ok({"id": 1})})
    with pytest.raises(E.ErroFracttal):
        estoque(fr).criar_peca("SP-TST-001", "Peça", "FURLONG")
    assert CRIAR not in fr.metodos


def test_criar_peca_sem_codigo_ou_nome_nao_vai_ao_fracttal():
    fr = Fracttal({UNIDADES: ok([{"id": 362334, "description": "UNIDADE"}]), CRIAR: ok({"id": 1})})
    for codigo, nome in (("", "Peça"), ("SP-TST-001", " ")):
        with pytest.raises(ValueError):
            estoque(fr).criar_peca(codigo, nome)
    assert fr.pedidos == []


def test_codigos_so_os_da_sigla():
    pecas = [{"id": 1, "code": "SP-TST-001"}, {"id": 2, "code": "SP-TST-002"}, {"id": 3, "code": "SP-OUT-001"},
             {"id": 4, "code": "SPTST-009"}, {"id": 5, "code": "sp-tst-003"}, {"id": 6, "code": None}, {"id": 7}]
    fr = Fracttal({PECAS: em_paginas(pecas)})
    assert estoque(fr, pagina=3).codigos("TST") == ["SP-TST-001", "SP-TST-002", "sp-tst-003"]
    assert fr.pedidos[0] == (PECAS, {"filter": [], "sort": [], "page": 1, "limit": 3, "start": 0, "is_tree": False,
                                     "node": 0, "id_type_item": 4})
    with pytest.raises(ValueError):
        estoque(fr).codigos("")


# ── o `api` de verdade do clone do OS Creator: o contrato que o adaptador lê dele ────────────────────────────────────────────
def _jwt(email="pessoa@exemplo.test", exp_s=3600):
    corpo = base64.urlsafe_b64encode(json.dumps({"email": email, "exp": time.time() + exp_s}).encode())
    return "x." + corpo.decode().rstrip("=") + ".y"


class _Resposta:
    """O que o `requests.post` devolveria."""

    def __init__(self, status, corpo=None, texto=""):
        self.status_code, self._corpo, self.text = status, corpo, texto

    def json(self):
        return self._corpo


def _result(result):
    return _Resposta(200, [{"jsonrpc": "2.0", "id": "x", "result": result}])


@pytest.fixture
def api_do_clone(app):
    from nexus.torres.oscreator import ponte
    ponte.clone(app)
    import api as os_api
    return os_api


def test_o_marcador_de_sessao_morta_e_o_do_api_de_verdade(api_do_clone):
    """O adaptador não importa o `api` (ele só está no caminho depois que o clone sobe): lê o marcador `session_expired`
    e o texto "HTTP 429" que o `api.py` põe nos erros. Se o `api.py` mudar um dos dois, este teste cai."""
    assert api_do_clone.SessionExpired.session_expired is True
    assert issubclass(api_do_clone.SessionExpired, api_do_clone.FracttalError)


def test_pelo_api_de_verdade_429_login_e_sucesso_falso(app, api_do_clone, monkeypatch):
    pedidos, respostas = [], []

    def post(url, headers=None, json=None, timeout=None):
        pedidos.append((url, headers, json))
        return respostas.pop(0)
    monkeypatch.setattr(api_do_clone.requests, "post", post)
    jwt = _jwt()
    est = E._estoque_do_clone(app, jwt, "pessoa@exemplo.test", relogio=Relogio(), dormir=lambda s: None)
    respostas[:] = [_Resposta(429, texto="Too Many Requests"), _Resposta(401), _Resposta(403),
                    _result({"success": False, "message": "ASSET_CANNOT_BE_DESABLED_STOCK"}),
                    _result({"success": True, "data": [{"id": 134082, "mode": 2}], "total": 1})]
    with pytest.raises(E.Limite):
        est.modo(ALMOX)
    with pytest.raises(E.SemLogin):
        est.modo(ALMOX)
    with pytest.raises(E.SemLogin):
        est.modo(ALMOX)
    with pytest.raises(E.ErroFracttal, match="ASSET_CANNOT_BE_DESABLED_STOCK"):
        est.modo(ALMOX)
    assert est.modo(ALMOX) == 2
    # cada pedido saiu dentro da sessão da pessoa: o JWT dela no cabeçalho, o método e o corpo da tela
    assert all(h["Authorization"] == f"Bearer {jwt}" for _, h, _ in pedidos)
    assert pedidos[-1][0] == api_do_clone.RPC_PROXY_URL
    assert pedidos[-1][2][0]["method"] == LISTA and pedidos[-1][2][0]["params"]["limit"] == 200


def test_sem_jwt_na_sessao_o_api_de_verdade_pede_login(app, api_do_clone):
    est = E._estoque_do_clone(app, "", "", relogio=Relogio(), dormir=lambda s: None)
    with pytest.raises(E.SemLogin):
        est.modo(ALMOX)


def test_o_jwt_renovado_no_meio_fica_para_os_proximos_pedidos(app, api_do_clone, monkeypatch):
    """Um trabalho de minutos passa do prazo do token: o `api` renova (POST /rpc/token) quando falta menos de 1 min, e o
    token novo só existe dentro da sessão daquele pedido. O adaptador o guarda na memória para o pedido seguinte não
    renovar de novo, e nunca o escreve em arquivo (o `api` do desktop escreveria)."""
    velho, novo = _jwt(exp_s=30), _jwt("pessoa@exemplo.test", exp_s=3600)
    pedidos = []

    def post(url, headers=None, json=None, timeout=None):
        pedidos.append((url, headers["Authorization"]))
        if url == api_do_clone.RPC_TOKEN_URL:
            return _Resposta(200, {"token": novo})
        return _result({"success": True, "data": [{"id": 134082, "mode": 0}], "total": 1})
    monkeypatch.setattr(api_do_clone.requests, "post", post)
    est = E._estoque_do_clone(app, velho, "pessoa@exemplo.test", relogio=Relogio(), dormir=lambda s: None)
    est.modo(ALMOX)
    est.modo(ALMOX)
    assert pedidos == [(api_do_clone.RPC_TOKEN_URL, f"Bearer {velho}"), (api_do_clone.RPC_PROXY_URL, f"Bearer {novo}"),
                       (api_do_clone.RPC_PROXY_URL, f"Bearer {novo}")]


def test_estoque_da_sessao_usa_o_login_do_pedido_e_sem_login_levanta(app, api_do_clone, monkeypatch):
    from nexus.torres.oscreator import ponte
    clone = ponte.clone(app)
    jwt = _jwt()
    valor = clone.session_interface.get_signing_serializer(clone).dumps(
        {"jwt": jwt, "conta": {"email": "pessoa@exemplo.test", "nome": "Pessoa"}})
    cabecalhos = []

    def post(url, headers=None, json=None, timeout=None):
        cabecalhos.append(headers["Authorization"])
        return _result({"success": True, "data": [{"id": 134082, "mode": 0}], "total": 1})
    monkeypatch.setattr(api_do_clone.requests, "post", post)
    with app.test_request_context("/t/pcm/pecas", headers={"Cookie": f"os_sessao={valor}"}):
        est = E.estoque_da_sessao(app)
    assert isinstance(est, E.EstoqueFracttal)
    assert est.modo(ALMOX) == 0 and cabecalhos == [f"Bearer {jwt}"]     # fora do pedido (a gravação roda numa thread)
    assert jwt not in repr(est) and jwt not in repr(vars(est))
    with app.test_request_context("/t/pcm/pecas"):                       # quem entrou pela senha não tem o login do Fracttal
        with pytest.raises(E.SemLogin):
            E.estoque_da_sessao(app)


# ── o Fracttal de mentira (`tests/estoque_falso.py`) cumpre o mesmo contrato ─────────────────────────────────────────────────
def falso(**kw):
    return EstoqueFalso({ALMOX: {ITEM: 3, "53248313": {"saldo": 10, "minimo": 2, "maximo": 8, "codigo": "SP-TST-002"}}}, **kw)


def test_falso_e_o_adaptador_tem_as_mesmas_assinaturas():
    """O que o teste prova com o falso vale para o de verdade só se os dois falam do mesmo jeito."""
    assert not inspect.isabstract(EstoqueFalso) and not inspect.isabstract(E.EstoqueFracttal)
    assert issubclass(EstoqueFalso, E.Estoque) and issubclass(E.EstoqueFracttal, E.Estoque)
    for nome in sorted(E.Estoque.__abstractmethods__):
        a, b = (inspect.signature(getattr(k, nome)) for k in (EstoqueFalso, E.EstoqueFracttal))
        assert [(p.name, p.kind, p.default) for p in a.parameters.values()] == \
               [(p.name, p.kind, p.default) for p in b.parameters.values()], nome


def test_falso_perde_a_resposta_mas_grava():
    """A resposta que "se perde": a gravação aconteceu e a chamada levanta, como a conexão que cai depois do Fracttal
    gravar. É o caso que a retomada precisa resolver sem duplicar o ajuste (confere o saldo, acha o movimento)."""
    est = falso(perder_resposta={"gravar_saldo", "fechar_ajuste"})
    est.abrir_ajuste(ALMOX)
    with pytest.raises(ConnectionError):
        est.gravar_saldo(ALMOX, ITEM, 5)
    assert est.ler(ALMOX)[ITEM]["saldo"] == 5            # gravou
    est.gravar_saldo(ALMOX, ITEM, 5)                     # a perda é de uma vez só: o reenvio responde
    with pytest.raises(ConnectionError):
        est.fechar_ajuste(ALMOX, "INVENTARIO-c1")
    assert est.modo(ALMOX) == 0 and est.achar_movimento(ALMOX, "INVENTARIO-c1")      # fechou
    assert [m["tipo"] for m in est.movimentos] == ["saida", "entrada"]


def test_falso_recusa_saldo_fora_do_modo():
    est = falso()
    with pytest.raises(E.ErroFracttal):
        est.gravar_saldo(ALMOX, ITEM, 5)
    assert est.ler(ALMOX)[ITEM]["saldo"] == 3 and est.movimentos == []
    est.abrir_ajuste(ALMOX)
    est.gravar_saldo(ALMOX, ITEM, 5)
    assert est.ler(ALMOX)[ITEM]["saldo"] == 5
    with pytest.raises(ValueError):                      # peça que nunca foi ligada: não há ligação para gravar
        est.gravar_saldo(ALMOX, "999", 1)


def test_falso_fecha_gerando_o_par():
    """Como o Fracttal de verdade (passo 0): ao fechar, uma SAÍDA do saldo antigo inteiro e uma ENTRADA do novo, com a
    referência, só das peças mexidas na sessão; o almoxarifado volta ao modo 0."""
    est = falso()
    est.abrir_ajuste(ALMOX)
    assert est.modo(ALMOX) == 2
    est.gravar_saldo(ALMOX, ITEM, 2)
    assert est.movimentos == []                          # nada se gera até fechar
    assert est.fechar_ajuste(ALMOX, "INVENTARIO-c1")
    assert est.modo(ALMOX) == 0
    assert [(m["id_item"], m["tipo"], m["qtd"], m["referencia"]) for m in est.movimentos] == [
        (ITEM, "saida", 3, "INVENTARIO-c1"), (ITEM, "entrada", 2, "INVENTARIO-c1")]     # a 53248313 não se mexeu
    assert all(m["quando"] for m in est.movimentos)
    assert est.achar_movimento(ALMOX, "INVENTARIO-c1") and est.achar_movimento(ALMOX, "INVENTARIO-c2") is None
    assert est.ler(ALMOX)[ITEM]["saldo"] == 2 and est.ler(ALMOX)["53248313"]["saldo"] == 10
    with pytest.raises(E.ErroFracttal):                  # não há sessão aberta para fechar
        est.fechar_ajuste(ALMOX, "INVENTARIO-c2")


def test_falso_limite_e_login_na_enesima_chamada():
    est = falso(limite_em=2)
    est.modo(ALMOX)
    with pytest.raises(E.Limite):
        est.ler(ALMOX)
    assert est.ler(ALMOX)[ITEM]["saldo"] == 3            # só a 2ª; a 3ª responde
    assert est.chamadas == ["modo", "ler", "ler"]
    est = falso(expirar_em=1)
    with pytest.raises(E.SemLogin):
        est.abrir_ajuste(ALMOX)
    assert est.modo(ALMOX) == 0                          # a chamada que caiu não abriu nada
    est = falso(limite_em=[1, 2])
    for _ in range(2):
        with pytest.raises(E.Limite):
            est.modo(ALMOX)
    assert est.modo(ALMOX) == 0


def test_falso_ligar_regua_peca_e_o_que_se_moveu():
    est = falso()
    ligacao = est.ligar(ALMOX, "777")
    assert est.ler(ALMOX)["777"] == {"saldo": 0.0, "minimo": 0.0, "maximo": 0.0, "ligacao": ligacao, "codigo": ""}
    with pytest.raises(E.ErroFracttal):
        est.ligar(ALMOX, "777")                          # já ligada: o Fracttal não liga duas vezes a mesma peça
    est.definir_regua(ALMOX, ITEM, 2, None)
    est.definir_regua(ALMOX, ITEM, None, 9)
    assert (est.ler(ALMOX)[ITEM]["minimo"], est.ler(ALMOX)[ITEM]["maximo"], est.ler(ALMOX)[ITEM]["saldo"]) == (2, 9, 3)
    assert est.movimentos == []                          # a régua não mexe em saldo nem gera movimento
    with pytest.raises(ValueError):
        est.definir_regua(ALMOX, "999", 1, 2)
    novo = est.criar_peca("SP-TST-009", "Peça nova")
    assert novo and est.criar_peca("SP-TST-010", "Outra") != novo
    with pytest.raises(E.ErroFracttal):
        est.criar_peca("SP-TST-009", "Repetida")
    assert est.codigos("TST") == ["SP-TST-002", "SP-TST-009", "SP-TST-010"] and est.codigos("OUT") == []
    est.mover(ALMOX, ITEM, "saida", 1, quando="2026-10-26T14:00:00Z", referencia="Consumo da OS 16000")
    est.mover(ALMOX, "53248313", "entrada", 4, quando="2026-10-26T12:00:00Z")
    assert est.ler(ALMOX)[ITEM]["saldo"] == 2 and est.ler(ALMOX)["53248313"]["saldo"] == 14
    assert est.mexidas_desde(ALMOX, "2026-10-26T13:00:00Z") == {ITEM}
    assert est.mexidas_desde(ALMOX, "2026-10-26T11:00:00Z") == {ITEM, "53248313"}
    assert est.mexidas_desde(ALMOX, "2026-10-26T11:00:00Z", ignorar_referencia="Consumo da OS 16000") == {"53248313"}

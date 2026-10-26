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
    est = falso(limite_em=1)
    with pytest.raises(E.Limite):
        est.abrir_ajuste(ALMOX)
    assert est.modo(ALMOX) == 0                          # a chamada que caiu não abriu nada
    est = falso(expirar_em=2)
    est.modo(ALMOX)                                      # a 1ª responde
    for chamada in (lambda: est.abrir_ajuste(ALMOX), lambda: est.ler(ALMOX), lambda: est.modo(ALMOX)):
        with pytest.raises(E.SemLogin):                  # da 2ª em diante o login está morto, e não volta
            chamada()
    assert est.chamadas == ["modo", "abrir_ajuste", "ler", "modo"]
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


# ═══ a rodada de correções 1 (revisão de 26/10/2026) ═══════════════════════════════════════════════════════════════════════
# ── a lista que chega pela metade não passa ────────────────────────────────────────────────────────────────────────────────
LEITORES = [
    (SALDOS, PECA_DE_TESTE, lambda e: e.ler(ALMOX)),
    (PECAS, {"id": 1, "code": "SP-TST-001"}, lambda e: e.codigos("TST")),
    (HISTORICO, HIST[0], lambda e: e.achar_movimento(ALMOX, "nada")),
    (HISTORICO, HIST[0], lambda e: e.mexidas_desde(ALMOX, "2026-01-01T00:00:00Z")),
    (LISTA, {"id": 1, "mode": 0}, lambda e: e.modo(ALMOX)),
]


@pytest.mark.parametrize("metodo, linha, ler", LEITORES)
def test_pagina_vazia_antes_do_total_nao_vira_lista_curta(metodo, linha, ler):
    """Caso reproduzido na revisão: `ler` devolvia 1 peça de `total: 5`. Uma página vazia com `start < total` termina a
    lista em silêncio e a tela mostraria o almoxarifado pela metade (número pela metade não vai para a tela); vale para todo
    leitor, porque todos passam pela mesma paginação."""
    def resposta(params):
        return {"success": True, "data": [linha] if params["start"] == 0 else [], "total": 5}
    fr = Fracttal({metodo: resposta})
    with pytest.raises(E.ErroFracttal, match="vazia"):
        ler(estoque(fr))
    assert len(fr.pedidos) == 2                          # a 2ª página veio vazia


@pytest.mark.parametrize("data, total", [(None, 120), ({"id": 1}, 3), ("x", None), ({"id": 1}, None), (7, 0)])
def test_data_que_nao_e_lista_e_erro(data, total):
    """`data: null` com `total: 120` virava `{}` na revisão. `data` que não é lista nunca é "sem linhas"; só o `None` com
    `total` ausente ou zero é lista vazia (testado abaixo)."""
    corpo = {"success": True, "data": data}
    if total is not None:
        corpo["total"] = total
    with pytest.raises(E.ErroFracttal):
        estoque(Fracttal({SALDOS: corpo})).ler(ALMOX)


@pytest.mark.parametrize("corpo", [{"data": None}, {"data": None, "total": 0}, {"data": []}, {"data": [], "total": 0}])
def test_lista_vazia_de_verdade_e_vazia(corpo):
    fr = Fracttal({SALDOS: {"success": True, **corpo}})
    assert estoque(fr).ler(ALMOX) == {} and len(fr.pedidos) == 1


# ── o fechamento são dois pedidos: finalizar e voltar ao modo normal ───────────────────────────────────────────────────────
def test_fechamento_feito_e_modo_0_pendente_se_recupera_so_com_voltar_ao_normal():
    """O `finalize` valeu e o `warehouse_update` do modo 0 falhou (o 429 da cota): o almoxarifado fica em modo 2 com os
    movimentos já gerados. Repetir o fechamento geraria um 2º par de movimentos por cima; a recuperação é só o modo 0."""
    fr = Fracttal({FECHAR: ok({"folio_return": 7, "total": 0}),
                   ATUALIZA_ALMOX: [FracttalError("RPC inventories.warehouse_update HTTP 429 — Too Many Requests"), ok()]})
    est = estoque(fr)
    with pytest.raises(E.Limite):
        est.fechar_ajuste(ALMOX, "INVENTARIO-c1")
    assert fr.metodos == [FECHAR, ATUALIZA_ALMOX]
    assert est.voltar_ao_normal(ALMOX) is None
    assert fr.pedidos[2:] == [(ATUALIZA_ALMOX, {"id": 134082, "mode": 0})]
    assert fr.metodos.count(FECHAR) == 1                 # nenhum 2º fechamento


def test_voltar_ao_normal_so_manda_o_modo_0():
    fr = Fracttal({ATUALIZA_ALMOX: ok()})
    estoque(fr).voltar_ao_normal(ALMOX)
    assert fr.pedidos == [(ATUALIZA_ALMOX, {"id": 134082, "mode": 0})]


def test_falso_fechamento_feito_e_modo_0_pendente():
    """O falso guarda o estado "finalizado, modo 2 pendente": os movimentos existem, o almoxarifado segue travado, um 2º
    fechamento é erro e só o `voltar_ao_normal` o libera, sem outro par de movimentos."""
    est = falso(limite_em=4)         # 1 abrir_ajuste, 2 gravar_saldo, 3 fechar_ajuste, 4 o voltar_ao_normal de dentro dele
    est.abrir_ajuste(ALMOX)
    est.gravar_saldo(ALMOX, ITEM, 2)
    with pytest.raises(E.Limite):
        est.fechar_ajuste(ALMOX, "INVENTARIO-c1")
    assert est.chamadas == ["abrir_ajuste", "gravar_saldo", "fechar_ajuste", "voltar_ao_normal"]
    assert est.modo(ALMOX) == 2                          # ainda travado
    assert [m["tipo"] for m in est.movimentos] == ["saida", "entrada"]
    assert est.achar_movimento(ALMOX, "INVENTARIO-c1")   # o fechamento valeu
    with pytest.raises(E.ErroFracttal):
        est.fechar_ajuste(ALMOX, "INVENTARIO-c1")        # nunca um 2º fechamento
    with pytest.raises(E.ErroFracttal):
        est.mover(ALMOX, ITEM, "saida", 1)               # e o almoxarifado ainda não aceita movimento
    assert len(est.movimentos) == 2
    est.voltar_ao_normal(ALMOX)
    assert est.modo(ALMOX) == 0 and len(est.movimentos) == 2
    est.mover(ALMOX, ITEM, "saida", 1)                   # liberado
    est.voltar_ao_normal(ALMOX)                          # de novo no modo 0: nada a fazer
    assert est.modo(ALMOX) == 0


def test_falso_voltar_ao_normal_e_uma_operacao_a_parte_para_os_defeitos():
    """A resposta do modo 0 que se perde (o Fracttal já voltou ao normal) e o login que morre justo nesse passo."""
    est = falso(perder_resposta={"voltar_ao_normal"})
    est.abrir_ajuste(ALMOX)
    est.gravar_saldo(ALMOX, ITEM, 2)
    with pytest.raises(ConnectionError):
        est.fechar_ajuste(ALMOX, "INVENTARIO-c1")
    assert est.modo(ALMOX) == 0 and est.achar_movimento(ALMOX, "INVENTARIO-c1") and len(est.movimentos) == 2
    est = falso(expirar_em=4)
    est.abrir_ajuste(ALMOX)
    est.gravar_saldo(ALMOX, ITEM, 2)
    with pytest.raises(E.SemLogin):
        est.fechar_ajuste(ALMOX, "INVENTARIO-c1")
    assert [m["tipo"] for m in est.movimentos] == ["saida", "entrada"]       # o fechamento valeu antes do login morrer
    with pytest.raises(E.SemLogin):
        est.voltar_ao_normal(ALMOX)                      # o login não volta nesta instância


def test_falso_voltar_ao_normal_nao_mexe_em_inventario_fisico():
    est = falso()
    est.definir_modo(ALMOX, 3)
    with pytest.raises(E.ErroFracttal):
        est.voltar_ao_normal(ALMOX)
    assert est.modo(ALMOX) == 3
    with pytest.raises(E.ErroFracttal):
        est.abrir_ajuste(ALMOX)


def test_falso_trava_entradas_e_saidas_em_ajuste_e_em_inventario_fisico():
    """O Fracttal de verdade trava Entradas e Saídas com o modo aberto (passo 0): um teste que "lança uma peça" no meio de
    uma gravação tem de ver a recusa, e não passar com um falso mais bonzinho que o real."""
    est = falso()
    est.mover(ALMOX, ITEM, "saida", 1)                   # modo 0: passa
    est.abrir_ajuste(ALMOX)
    with pytest.raises(E.ErroFracttal):
        est.mover(ALMOX, ITEM, "entrada", 1)
    est.voltar_ao_normal(ALMOX)
    est.definir_modo(ALMOX, 3)
    with pytest.raises(E.ErroFracttal):
        est.mover(ALMOX, ITEM, "saida", 1)


# ── achar o movimento sem ler o histórico inteiro ──────────────────────────────────────────────────────────────────────────
def test_achar_movimento_com_data_para_na_primeira_linha_mais_velha():
    """O "não achei" de uma retomada lia o histórico INTEIRO do almoxarifado (a cota de 200/min é da empresa). Com a data
    em que a gravação começou, para na primeira linha mais velha."""
    fr = Fracttal({HISTORICO: em_paginas(HIST)})
    est = estoque(fr, pagina=2)
    assert est.achar_movimento(ALMOX, "INVENTARIO-c9", desde_iso="2026-10-26T14:00:00Z") is None
    assert len(fr.pedidos) == 2                          # a MOV-3 (13:00) está na 2ª página e é mais velha: não há 3ª
    fr.pedidos.clear()
    assert est.achar_movimento(ALMOX, "INVENTARIO-c9") is None and len(fr.pedidos) == 3     # sem a data, lê tudo
    assert est.achar_movimento(ALMOX, "Consumo antigo") == "MOV-2"
    assert est.achar_movimento(ALMOX, "Consumo antigo", "2026-10-26T00:00:00Z") is None     # mais velho que a data: fora
    assert est.achar_movimento(ALMOX, "INVENTARIO-c1", "2026-10-26T00:00:00Z") == "MOV-6"
    with pytest.raises(ValueError):
        est.achar_movimento(ALMOX, "x", "ontem")


def test_falso_achar_movimento_com_data():
    est = falso(agora=lambda: "2026-10-26T15:00:00Z")
    est.abrir_ajuste(ALMOX)
    est.gravar_saldo(ALMOX, ITEM, 2)
    est.fechar_ajuste(ALMOX, "INVENTARIO-c1")
    assert est.achar_movimento(ALMOX, "INVENTARIO-c1", "2026-10-26T14:00:00Z")
    assert est.achar_movimento(ALMOX, "INVENTARIO-c1", "2026-10-26T16:00:00Z") is None
    assert est.achar_movimento(ALMOX, "INVENTARIO-c1")


# ── o ritmo é da empresa, não da instância ─────────────────────────────────────────────────────────────────────────────────
def test_o_ritmo_e_dividido_entre_as_instancias():
    """A cota de 200/min é da EMPRESA: duas pessoas gravando juntas, cada uma com a sua instância (o login é da pessoa),
    não podem pedir 2 por segundo. Duas instâncias com o mesmo `Ritmo`: 4 pedidos levam pelo menos 3 s."""
    relogio = Relogio()
    ritmo = E.Ritmo(relogio, relogio.dormir)
    a = E.EstoqueFracttal(Fracttal({LISTA: ok([{"id": 134082, "mode": 0}])}), ritmo=ritmo)
    b = E.EstoqueFracttal(Fracttal({LISTA: ok([{"id": 134082, "mode": 0}])}), ritmo=ritmo)
    t0 = relogio()
    a.modo(ALMOX), b.modo(ALMOX), a.modo(ALMOX), b.modo(ALMOX)
    assert relogio() - t0 >= 3 and relogio.dormiu == [1.0, 1.0, 1.0]


def test_sem_ritmo_proprio_toda_instancia_usa_o_do_modulo(monkeypatch):
    """O que a produção faz (`estoque_da_sessao` não passa ritmo): o `RITMO` do módulo, de todas as instâncias."""
    relogio = Relogio()
    monkeypatch.setattr(E, "RITMO", E.Ritmo(relogio, relogio.dormir))
    a = E.EstoqueFracttal(Fracttal({LISTA: ok([{"id": 134082, "mode": 0}])}))
    b = E.EstoqueFracttal(Fracttal({LISTA: ok([{"id": 134082, "mode": 0}])}))
    t0 = relogio()
    a.modo(ALMOX), b.modo(ALMOX), a.modo(ALMOX)
    assert relogio() - t0 >= 2


# ── o modo em branco não é "normal" ────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("linha", [{"id": 134082, "mode": None}, {"id": 134082}, {"id": 134082, "mode": ""}])
def test_modo_em_branco_e_erro_nunca_normal(linha):
    """É a conferência da trava: um almoxarifado que veio sem o `mode` não pode ser dado como livre para movimento."""
    with pytest.raises(E.ErroFracttal, match="mode"):
        estoque(Fracttal({LISTA: ok([linha])})).modo(ALMOX)
    assert estoque(Fracttal({LISTA: ok([{"id": 134082, "mode": 0}])})).modo(ALMOX) == 0      # o 0 de verdade segue 0


# ── o `api` de verdade: o cache das OS, o JWT vencido e a sessão morta no corpo ──────────────────────────────────────────────
def test_o_adaptador_nao_esvazia_o_cache_de_leitura_das_os(app, api_do_clone, monkeypatch):
    """O `_rpc_call` do OS Creator trata como "gravação de OS" todo método que não é "_list", "get", "details" ou "load_" e,
    a cada um, limpa a memória das leituras de OS do processo inteiro: `warehouses_items_stock` e toda gravação de estoque
    caem aí. O adaptador chama o `_rpc_chamar` (o mesmo POST, sem a limpeza), e o `api.py` não se edita."""
    assert not api_do_clone._eh_leitura(SALDOS) and not api_do_clone._eh_leitura(ATUALIZA_LIGACAO)      # a premissa
    chave = ("tasks.work_orders_tasks_new_list", 99)
    monkeypatch.setattr(api_do_clone.requests, "post", lambda *a, **k: _result({"success": True, "data": [], "total": 0}))
    est = E._estoque_do_clone(app, _jwt(), "pessoa@exemplo.test", relogio=Relogio(), dormir=lambda s: None)
    try:
        api_do_clone._LEITURAS_OS[chave] = (time.time(), [{"id": 1}])
        est.ler(ALMOX)
        est.abrir_ajuste(ALMOX)
        assert chave in api_do_clone._LEITURAS_OS        # o cache das OS segue de pé
        from os_web import sessao as os_sessao
        with os_sessao.contexto(_jwt(), ""):
            api_do_clone._rpc_call(SALDOS, {"id_warehouse": 1})
        assert chave not in api_do_clone._LEITURAS_OS    # e o teste enxerga a limpeza que o `_rpc_call` faria
    finally:
        api_do_clone._LEITURAS_OS.pop(chave, None)


def test_pelo_api_de_verdade_jwt_vencido_e_sessao_morta_no_corpo(app, api_do_clone, monkeypatch):
    """As duas frases/códigos de sessão morta que não vêm como HTTP 401: o JWT vencido que não renovou (texto do
    `_rpc_headers`) e o `USER_NOT_LOGIN` no corpo (a `SessionExpired` do `_rpc_chamar`)."""
    pedidos = []

    def post(url, headers=None, json=None, timeout=None):
        pedidos.append(url)
        if url == api_do_clone.RPC_TOKEN_URL:
            return _Resposta(401)                        # a renovação recusada
        return _result({"success": False, "message": "USER_NOT_LOGIN"})
    monkeypatch.setattr(api_do_clone.requests, "post", post)
    est = E._estoque_do_clone(app, _jwt(exp_s=-600), "pessoa@exemplo.test", relogio=Relogio(), dormir=lambda s: None)
    with pytest.raises(E.SemLogin, match="expirou"):
        est.modo(ALMOX)
    assert pedidos == [api_do_clone.RPC_TOKEN_URL]       # nem chegou ao proxy
    est = E._estoque_do_clone(app, _jwt(), "pessoa@exemplo.test", relogio=Relogio(), dormir=lambda s: None)
    with pytest.raises(E.SemLogin, match="expirou ou foi encerrada"):
        est.modo(ALMOX)

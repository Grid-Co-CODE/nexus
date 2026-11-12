"""Transferir peça entre almoxarifados do mesmo cliente (12/11/2026, PCM → Almoxarifado → Transferir; o pedido do PCM de
04/11/2026). Desenho: docs/superpowers/specs/2026-11-12-transferir-entre-almoxarifados-design.md. Aqui, a porta do Fracttal
(`estoque.py`) e o Fracttal de mentira; a regra, em `test_pcm_inventario_transferencia_regra.py`.

O Fracttal é o gravador dos testes do adaptador. O corpo de referência é o capturado na tela do Fracttal e reenviado pelo RPC em
12/11/2026 (nos dois almoxarifados de teste, lido de volta e desfeito). Dado de mentira: ids, códigos e nomes inventados, sem
nome de gente."""
import uuid
from datetime import datetime, timezone

import pytest
from estoque_falso import EstoqueFalso
from test_pcm_inventario_estoque import Fracttal, em_paginas, estoque, linha_de_saldo, ok

from nexus.pcm.inventario import estoque as E

ORIGEM, DESTINO, ITEM = "134082", "146124", "53750352"
RESPONSAVEL = {"id": "1414413", "descricao": "Pessoa Teste  {63}"}
UUIDS = ["12345678-1234-5678-1234-567812345678", "87654321-4321-8765-4321-876543218765"]
QUANDO = datetime(2026, 11, 12, 20, 42, 55, 247000, tzinfo=timezone.utc)
NOTA = "OS 4521 · Transferência pelo Nexus NX-TR-0a1b2c3d"
# a linha da peça no `warehouses_items_stock` da ORIGEM, com os campos que a linha da transferência usa
SALDO_DA_ORIGEM = {**linha_de_saldo("15535397", ITEM, "TESTE-NEXUS-0001", 2, 0, 0, unidade="UNIDADE"),
                   "description": "Peça de teste    { TESTE-NEXUS-0001 }", "unit_cost": 0, "is_serial_control": False,
                   "is_lot_control": False}

# O CORPO DA TRANSFERÊNCIA, num lugar só: o capturado na tela do Fracttal, campo a campo e na ordem dela. Mudar o corpo é mudar
# este dicionário e as duas funções do `estoque.py` (`_corpo_da_transferencia` e `_linha_da_transferencia`), e nada mais.
CORPO_DE_REFERENCIA = {
    "id": UUIDS[0], "id_movement_reference": None, "is_from_work_order": False, "folio_source": "", "symbol": "R$",
    "currency_code": "BRL", "id_movement_type": 8, "movements_types_description": "WAREHOUSE_TRANSFER",
    "movements_states_description": "RETURN", "id_movement_state": 2, "id_warehouse_target": 146124,
    "id_warehouse_source": 134082, "id_responsible": 1414413, "responsible_description": "Pessoa Teste  {63}",
    "date": "2026-11-12", "date_create": "2026-11-12T20:42:55.247Z", "document": "OS 4521", "id_third_party": None,
    "third_parties_name": "", "id_cost_center": None, "warehouses_target_description": "Almoxarifado de teste 2",
    "costs_center_description": "", "description": NOTA, "status_display": "",
    "items": [{"id": UUIDS[1], "qty": 1, "unit_cost": 0, "total_cost": 0, "id_taxes": 1, "tax_name": "Exempt",
               "item_tax_rate": 0, "serial_numbers": [], "stock": 2, "id_item": 53750352,
               "items_description": "Peça de teste    { TESTE-NEXUS-0001 }", "units_description": "UNIDADE",
               "unit_cost_company": 0, "qty_max": 0, "is_serial_control": False, "is_lot_control": False}],
    "idInternal": UUIDS[0]}
SUCESSO = {"success": True, "message": "ACTION_DONE",
           "data": {"id": 86719536, "id_movement_type": 8, "folio_source": "MOV-21", "folio_target": "MOV-1",
                    "document": "MOV-1", "description": NOTA}}


def _uuids(monkeypatch):
    fila = list(UUIDS) * 4
    monkeypatch.setattr(uuid, "uuid4", lambda: uuid.UUID(fila.pop(0)))


def _transferir(est, qtd=1, **kw):
    args = dict(id_origem=ORIGEM, id_destino=DESTINO, nome_destino="Almoxarifado de teste 2", id_item=ITEM, qtd=qtd,
                responsavel=RESPONSAVEL, documento="OS 4521", nota=NOTA, agora=QUANDO)
    args.update(kw)
    return est.transferir(**args)


# ── o adaptador: os corpos ───────────────────────────────────────────────────────────────────────────────────────────

def test_o_corpo_da_transferencia_e_o_capturado(monkeypatch):
    """O `outputs_insert` do tipo 8 com a linha do saldo da ORIGEM que o `ler` recebeu (sem ler de novo), na ordem da tela;
    a resposta dá o id do movimento e os folios dos dois lados."""
    _uuids(monkeypatch)
    fr = Fracttal({E.SALDOS: em_paginas([SALDO_DA_ORIGEM]), E.SAIDA: SUCESSO})
    est = estoque(fr)
    est.ler(ORIGEM)
    assert _transferir(est) == {"id": "86719536", "folio_origem": "MOV-21", "folio_destino": "MOV-1"}
    assert fr.pedidos[1:] == [(E.SAIDA, CORPO_DE_REFERENCIA)]
    assert list(fr.pedidos[1][1]) == list(CORPO_DE_REFERENCIA)                       # a ordem da tela
    assert list(fr.pedidos[1][1]["items"][0]) == list(CORPO_DE_REFERENCIA["items"][0])
    # sem a leitura antes, o adaptador lê a origem uma vez e monta a mesma linha
    _uuids(monkeypatch)
    fr2 = Fracttal({E.SALDOS: em_paginas([SALDO_DA_ORIGEM]), E.SAIDA: SUCESSO})
    _transferir(estoque(fr2))
    assert fr2.metodos == [E.SALDOS, E.SAIDA] and fr2.pedidos[1][1] == CORPO_DE_REFERENCIA


def test_o_custo_e_a_quantidade_quebrada(monkeypatch):
    """O custo da linha vai no `unit_cost` e no `unit_cost_company`, e quantidade × custo no `total_cost` (só o custo 0 foi
    provado no Fracttal)."""
    _uuids(monkeypatch)
    fr = Fracttal({E.SALDOS: em_paginas([{**SALDO_DA_ORIGEM, "unit_cost": "12.5", "units_description": "METRO"}]),
                   E.SAIDA: SUCESSO})
    _transferir(estoque(fr), qtd=1.5)
    linha = fr.pedidos[-1][1]["items"][0]
    assert (linha["qty"], linha["unit_cost"], linha["unit_cost_company"], linha["total_cost"]) == (1.5, 12.5, 12.5, 18.75)
    assert linha["units_description"] == "METRO"


def test_o_que_nao_faz_sentido_nem_vai():
    fr = Fracttal({E.SALDOS: em_paginas([SALDO_DA_ORIGEM])})
    est = estoque(fr)
    for kw in ({"qtd": 0}, {"qtd": -1}, {"qtd": "x"}, {"id_destino": ORIGEM}, {"nota": " "}, {"responsavel": {"id": "501"}},
               {"id_item": "999"}):
        with pytest.raises(ValueError):
            _transferir(est, **kw)
    assert E.SAIDA not in fr.metodos


@pytest.mark.parametrize("campo", ["is_serial_control", "is_lot_control"])
def test_a_peca_com_serie_ou_lote_nem_vai(campo):
    fr = Fracttal({E.SALDOS: em_paginas([{**SALDO_DA_ORIGEM, campo: True}])})
    est = estoque(fr)
    assert est.serie_ou_lote(ORIGEM, ITEM) is True
    with pytest.raises(ValueError, match="série ou de lote"):
        _transferir(est)
    assert E.SAIDA not in fr.metodos
    assert estoque(Fracttal({E.SALDOS: em_paginas([SALDO_DA_ORIGEM])})).serie_ou_lote(ORIGEM, ITEM) is False


@pytest.mark.parametrize("motivo, frase", [("ITEMS_NO_LINKED", E.SEM_VINCULO_NO_DESTINO), ("NEGATIVE_VALUE", E.SALDO_NAO_DA)])
def test_as_recusas_com_o_message_nulo_viram_frase_clara(motivo, frase):
    """A recusa da transferência vem com `success` falso, `message` NULO e o motivo em `data[0].message` (medido em
    12/11/2026): é o "não" do Fracttal (`Recusado`), nunca a resposta incerta."""
    recusa = {"success": False, "message": None, "data": [{"message": motivo, "description": "Peça de teste"}]}
    fr = Fracttal({E.SALDOS: em_paginas([SALDO_DA_ORIGEM]), E.SAIDA: recusa})
    with pytest.raises(E.Recusado) as ex:
        _transferir(estoque(fr))
    assert ex.value.mensagem == frase and motivo in frase
    fr2 = Fracttal({E.SALDOS: em_paginas([SALDO_DA_ORIGEM]),
                    E.SAIDA: {"success": False, "message": None, "data": [{"message": "OUTRA_COISA"}]}})
    with pytest.raises(E.Recusado, match="OUTRA_COISA"):
        _transferir(estoque(fr2))


def test_a_rede_na_transferencia_e_a_resposta_incerta():
    fr = Fracttal({E.SALDOS: em_paginas([SALDO_DA_ORIGEM]), E.SAIDA: RuntimeError("HTTP 502")})
    with pytest.raises(E.SemResposta):
        _transferir(estoque(fr))


def _mov(i, tipo, descricao="", documento="", quando="2026-11-12T20:48:07.358433+00:00"):
    return {"id_movements": i, "folio": f"MOV-{i}", "id_item": int(ITEM), "date_create": quando, "description": descricao,
            "document": documento, "id_movement_type": tipo, "id_movement_state": 2, "approved": None,
            "responsible_description": "Nome Inventado da Silva"}


def test_achar_transferencia_so_pela_nota():
    """O tipo 8 (ou a linha sem o tipo) com o código na `description`; no `document` não vale (o Fracttal o troca pelo folio do
    destino); a saída geral com o mesmo texto não conta; para na primeira linha mais velha que o `desde`."""
    hist = [_mov(9, 5, "NX-TR-0a1b2c3d"),
            _mov(8, 8, "outra transferência", documento="NX-TR-0a1b2c3d"),
            _mov(7, 8, "OS 4521 · Transferência pelo Nexus nx-tr-0a1b2c3d", documento="MOV-1"),
            _mov(6, None, "Transferência pelo Nexus NX-TR-ffff0000"),
            _mov(5, 8, "NX-TR-00000001", quando="2026-11-01T12:00:00+00:00")]
    est = estoque(Fracttal({E.HISTORICO: em_paginas(hist)}))
    achada = est.achar_transferencia(DESTINO, "NX-TR-0a1b2c3d", "2026-11-12T00:00:00Z")
    assert achada == {"id": "7", "folio": "MOV-7", "documento": "MOV-1", "quando": "2026-11-12T20:48:07.358433+00:00"}
    assert est.achar_transferencia(DESTINO, "NX-TR-ffff0000", "2026-11-12T00:00:00Z")["id"] == "6"
    assert est.achar_transferencia(DESTINO, "NX-TR-00000001", "2026-11-12T00:00:00Z") is None
    assert "Nome Inventado" not in repr(achada)
    with pytest.raises(ValueError):
        est.achar_transferencia(DESTINO, " ", "2026-11-12T00:00:00Z")


def test_a_lista_dos_almoxarifados_pede_como_a_tela():
    """O `warehouses_list` com o corpo lido no Fracttal de verdade em 12/11/2026 (o `group` vazio inclusive) e os campos de cada
    linha: o `code`, a `description`, o `location_description` como veio, o `mode`, o `active` (o que não vem é ativo) e o
    `transfer_approval` (o que não vem é não)."""
    lista = [{"id": 134082, "code": "ALM-1", "description": " Almoxarifado  Usina Um ", "mode": 0, "active": True,
              "transfer_approval": False, "location_description": "// Cliente Alfa/ Cliente Alfa - Usina Um - PA/ "},
             {"id": 134083, "mode": 2, "active": False, "transfer_approval": True}, {"id": 134084},
             {"code": "sem id"}]
    fr = Fracttal({E.LISTA: em_paginas(lista)})
    lidos = estoque(fr).almoxarifados()
    assert fr.pedidos == [(E.LISTA, {"filter": [], "sort": [], "group": {"property": ""}, "is_tree": False, "node": None,
                                     "page": 1, "limit": 200, "start": 0})]
    assert lidos == [
        {"id": "134082", "codigo": "ALM-1", "nome": "Almoxarifado Usina Um",
         "local": "// Cliente Alfa/ Cliente Alfa - Usina Um - PA/ ", "ativo": True, "modo": 0, "exige_aprovacao": False},
        {"id": "134083", "codigo": "", "nome": "", "local": "", "ativo": False, "modo": 2, "exige_aprovacao": True},
        {"id": "134084", "codigo": "", "nome": "", "local": "", "ativo": True, "modo": None, "exige_aprovacao": False}]


def test_o_ler_guarda_a_linha_sem_mudar_o_que_devolve():
    est = estoque(Fracttal({E.SALDOS: em_paginas([SALDO_DA_ORIGEM])}))
    lido = est.ler(ORIGEM)
    assert set(lido[ITEM]) == {"saldo", "minimo", "maximo", "ligacao", "codigo", "unidade", "criticidade"}


def test_a_recusa_com_o_message_nulo_vale_para_todo_pedido():
    """O `_rpc` lê o motivo no `data[0].message` quando o `message` vem nulo (o ligar, por exemplo), e o "sem motivo" fica com
    o texto de sempre."""
    fr = Fracttal({E.LIGAR: {"success": False, "message": None, "data": [{"message": "ALGUM_MOTIVO"}]}})
    with pytest.raises(E.Recusado, match="ALGUM_MOTIVO"):
        estoque(fr).ligar(DESTINO, ITEM)
    fr2 = Fracttal({E.LIGAR: {"success": False, "message": None, "data": None}})
    with pytest.raises(E.Recusado, match="o Fracttal recusou o pedido"):
        estoque(fr2).ligar(DESTINO, ITEM)
    assert estoque(Fracttal({E.LIGAR: ok({"id": 18454624})})).ligar(DESTINO, ITEM) == "18454624"


# ── o Fracttal de mentira faz o mesmo ───────────────────────────────────────────────────────────────────────────────────

def test_o_falso_transfere_na_hora_e_acha_pela_nota():
    f = EstoqueFalso({ORIGEM: {ITEM: 5}, DESTINO: {ITEM: 1}}, aprovacao_transferencia={DESTINO}, inativos={ORIGEM})
    lista = {a["id"]: a for a in f.almoxarifados()}
    assert lista[DESTINO] == {"id": DESTINO, "codigo": f"ALM-{DESTINO}", "nome": f"Almoxarifado {DESTINO}", "local": "",
                              "ativo": True, "modo": 0, "exige_aprovacao": True}
    assert lista[ORIGEM]["ativo"] is False
    r = _transferir(f, qtd=2)
    assert set(r) == {"id", "folio_origem", "folio_destino"} and r["folio_origem"] != r["folio_destino"]
    assert f.ler(ORIGEM)[ITEM]["saldo"] == 3 and f.ler(DESTINO)[ITEM]["saldo"] == 3
    achada = f.achar_transferencia(ORIGEM, "NX-TR-0a1b2c3d", "2026-11-11T00:00:00Z")
    assert achada["id"] == r["id"] and achada["folio"] == r["folio_origem"] and achada["documento"] == r["folio_destino"]
    assert f.achar_transferencia(DESTINO, "nx-tr-0a1b2c3d", "2026-11-11")["id"] == r["id"]
    assert f.achar_transferencia(DESTINO, "NX-TR-ffffffff", "2026-11-11") is None
    # sem o vínculo no destino e com o saldo que não dá, as recusas claras; nada muda
    f2 = EstoqueFalso({ORIGEM: {ITEM: 5}, DESTINO: {}}, com_serie_ou_lote={"9"})
    with pytest.raises(E.Recusado) as ex:
        _transferir(f2)
    assert ex.value.mensagem == E.SEM_VINCULO_NO_DESTINO and f2.ler(ORIGEM)[ITEM]["saldo"] == 5
    f2.ligar(DESTINO, ITEM)
    with pytest.raises(E.Recusado) as ex:
        _transferir(f2, qtd=6)
    assert ex.value.mensagem == E.SALDO_NAO_DA
    assert _transferir(f2, qtd=5) and f2.ler(DESTINO)[ITEM]["saldo"] == 5 and f2.ler(ORIGEM)[ITEM]["saldo"] == 0
    assert f2.serie_ou_lote(ORIGEM, ITEM) is False

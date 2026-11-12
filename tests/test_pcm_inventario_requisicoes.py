"""As requisições de material no Almoxarifado (12/11/2026, item 6 da 2ª rodada): o "Aceitar" pelo Nexus. O PCM fazia no
Fracttal a Saída "Geral" com a OS, aprovar e mudar para Entrega total; o Nexus faz de uma vez (aprovar, a saída ligada, reler),
com um clique do PCM para as de Rank A (ou de curva desconhecida) e sozinho para as de Rank B e C. O Rank é a Classificação 2 da
peça no Fracttal, pelo código (o mapa da lista de peças), e não a "Curva ABC" do catálogo do App, que vem vazia para os Ranks.

O Fracttal é o `EstoqueFalso` (a requisição, as peças e os responsáveis como o Fracttal os devolve) e, para os corpos, o gravador
dos testes do adaptador; o livro do inventário é o arquivo da cópia de prova. As datas são relativas a agora (nada de
bomba-relógio). Dado de mentira: códigos, ids, OS e nomes inventados, sem nome de gente."""
import json
import re
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from estoque_falso import EstoqueFalso
from test_campo_visao import banco  # noqa: F401  (banco é fixture)
from test_pcm_inventario_curadoria import PESSOA, _pessoa_ms, cur  # noqa: F401  (cur é fixture)
from test_pcm_inventario_estoque import Fracttal, com_o_fracttal, em_paginas, estoque, ok
from test_pcm_inventario_estoque import FracttalError as FracttalErrorDoOSCreator
from test_pcm_publicar import _no_setor

from nexus.cadastro import setor_ids as SID
from nexus.dados import fato_inventario as F
from nexus.pcm.inventario import classificacao as CL
from nexus.pcm.inventario import estoque as E
from nexus.pcm.inventario import gravacao as G
from nexus.pcm.inventario import quem
from nexus.pcm.inventario import requisicoes as RQ
from nexus.pcm.inventario.erros import Conflito

AGORA = datetime.now(timezone.utc)
CONTA = {"id": "77", "nome": "Pessoa Teste"}
RESPONSAVEL = {"id": "501", "descricao": "Pessoa Teste  {P-01}"}
LISTA, TELA = "/os/_nexus/inventario/requisicoes", "/t/pcm/pecas/requisicoes"


def _iso(dias=0, horas=0):
    return (AGORA - timedelta(days=dias, hours=horas)).strftime("%Y-%m-%dT%H:%M:%S")


def _req(i, os_="4521", almox=10, estado=3, aprovada=False, decidida=None, quem_="", comentario="", dias=1):
    """Uma linha do `movements_new_list` do jeito que o Fracttal a devolve."""
    return {"id": i, "folio_source": f"R-{i}", "document": os_, "date": _iso(dias)[:10], "date_create": _iso(dias),
            "id_warehouse_source": almox, "warehouses_source_code": f"ALM-{almox}",
            "warehouses_source_description": f"Almoxarifado {almox}", "id_movement_state": estado, "approved": aprovada,
            "approved_comment": comentario, "approval_date": decidida, "accounts_log_name": quem_,
            "id_work_orders_tasks": 9000 + i, "number_details": 1, "items_log_description": "peças"}


def _det(id_item, code, qty=1):
    """Uma linha do `movements_details_list` como o Fracttal a devolve: o `id_item_original` é o id da peça no catálogo (o do
    saldo) e o `id_item`, o da peça NAQUELE almoxarifado, outro número (provado em 12/11/2026: 47887778 e 53750352)."""
    return {"id": 600 + id_item, "id_item": 47_000_000 + id_item, "id_item_original": id_item, "code": code, "qty": qty,
            "qty_pending": qty, "items_description": f"Peça {code}", "units_description": "UNIDADE"}


# as peças do Fracttal com o Rank (a Classificação 2): o mapa por código
PECAS = [{"code": "SP-1", "id_group_2": 364873, "groups_2_description": "2. Rank A"},
         {"code": "SP-2", "id_group_2": 364874, "groups_2_description": "3. Rank B"},
         {"code": "SP-4", "id_group_2": 364875, "groups_2_description": "4. Rank C"},
         {"code": "SP-5", "id_group_2": 364870, "groups_2_description": "1.Avariado"},
         {"code": "SP-6", "id_group": 318452, "groups_description": "Cabos"}]
A_RANK_A, B_E_C, DESCONHECIDA, AVARIADO = 101, 102, 103, 104
REQS = [_req(A_RANK_A, "4521", dias=1), _req(B_E_C, "4522", dias=2), _req(DESCONHECIDA, "4523", dias=3),
        _req(AVARIADO, "4524", dias=4)]
DETALHES = {A_RANK_A: [_det(1, "SP-1")], B_E_C: [_det(2, "SP-2", 2), _det(4, "SP-4")], DESCONHECIDA: [_det(7, "SP-9")],
            AVARIADO: [_det(5, "SP-5")]}
SALDOS = {"10": {"1": {"saldo": 5, "codigo": "SP-1"}, "2": {"saldo": 8, "codigo": "SP-2"}, "4": {"saldo": 3, "codigo": "SP-4"},
                 "5": {"saldo": 1, "codigo": "SP-5"}, "7": {"saldo": 2, "codigo": "SP-9"}}}


def _falso(reqs=REQS, detalhes=DETALHES, saldos=None, **kw):
    return EstoqueFalso(saldos or json.loads(json.dumps(SALDOS)), pecas_do_catalogo=PECAS, requisicoes=reqs,
                        detalhes=detalhes, responsaveis=[{"id": 501, "email": PESSOA["email"],
                                                          "description": RESPONSAVEL["descricao"]}], **kw)


@pytest.fixture
def rq(cur, monkeypatch):
    """O app de mentira com o automático valendo para as requisições dos testes (criadas há poucos dias): o `AUTO_DESDE` de
    verdade é o dia da entrada no ar."""
    RQ.limpar()
    CL.limpar()
    monkeypatch.setattr(RQ, "AUTO_DESDE", "2026-01-01T00:00:00-03:00")
    monkeypatch.setitem(cur.config, "NEXUS_INVENTARIO_GRAVAR", "1")      # o servidor (a revisão final, I1)
    yield cur
    RQ.aguardar(30)
    RQ.limpar()
    CL.limpar()


def _ctx(app_, falso):
    return RQ.contexto(app_.config, CL.mapa_guardado(falso))


def _aceitar(app_, falso, rid, por="pcm", **kw):
    args = dict(ctx=_ctx(app_, falso), quem_=quem.colunas(app_.config, PESSOA), conta=CONTA, responsavel=RESPONSAVEL)
    args.update(kw)
    return RQ.aceitar(app_.config, falso, str(rid), por=por, **args)


def _eventos(app_, tipo=None):
    return [e for e in F.ler(app_.config, forcar=True)[F.ABA_EVENTO] if tipo is None or e["tipo"] == tipo]


# ── o adaptador: os corpos ───────────────────────────────────────────────────────────────────────────────────────────

def test_a_lista_pede_como_a_tela_e_para_no_corte():
    """`movements_new_list` do tipo 13, da mais nova (id desc), página a página; para na 1ª mais velha que o corte (a cota é
    de todos) e devolve a requisição como a casa a usa, com a recusada (não aprovada COM a data) distinguível."""
    linhas = [_req(9, dias=1), _req(8, dias=10, aprovada="true", decidida=_iso(9), quem_="Alguém"),
              _req(7, dias=20, aprovada=False, decidida=_iso(19)), _req(6, dias=95), _req(5, dias=96)]
    fr = Fracttal({E.MOVIMENTOS: em_paginas(linhas)})
    lidas = estoque(fr, pagina=2).requisicoes(90, AGORA)
    assert [r["id"] for r in lidas] == ["9", "8", "7"]
    assert len(fr.pedidos) == 2                                              # a 3ª página nem se pede: a 4ª linha é velha
    assert fr.pedidos[0] == (E.MOVIMENTOS, {"id_movement_type": 13, "sort": [{"property": "id", "direction": "desc"}],
                                            "is_tree": False, "node": None, "page": 1, "limit": 2, "start": 0})
    r = lidas[1]
    assert (r["os"], r["id_almox"], r["estado"], r["aprovada"], r["decidida_por"]) == ("4521", "10", 3, True, "Alguém")
    assert RQ.recusada(lidas[2]) and not RQ.recusada(lidas[1]) and not lidas[0]["decidida_em"]
    fr2 = Fracttal({E.MOVIMENTOS: em_paginas(linhas)})
    assert estoque(fr2).reler_requisicao("8", 90, AGORA)["id"] == "8" and estoque(fr2).reler_requisicao("6", 90, AGORA) is None


def test_os_corpos_do_aprovar_e_do_recusar():
    """O `outputs_orders_update` com o comentário e a conta de quem decide (os dois: sem eles o "aprovado por" fica vazio);
    sem a conta ou sem o comentário, nada vai."""
    fr = Fracttal({E.DECIDIR_REQUISICAO: ok({})})
    est = estoque(fr)
    est.aprovar_requisicao("101", " Aceita  pelo Nexus ", CONTA)
    est.recusar_requisicao("102", "não era esta peça", CONTA)
    assert fr.pedidos == [
        (E.DECIDIR_REQUISICAO, {"id": 101, "approved": True, "approved_comment": "Aceita pelo Nexus", "id_accounts": 77,
                                "accounts_log_name": "Pessoa Teste"}),
        (E.DECIDIR_REQUISICAO, {"id": 102, "approved": False, "approved_comment": "não era esta peça", "id_accounts": 77,
                                "accounts_log_name": "Pessoa Teste"})]
    for comentario, conta in (("ok", None), ("ok", {"id": "77"}), ("", CONTA), (" ", CONTA)):
        with pytest.raises(ValueError):
            est.aprovar_requisicao("101", comentario, conta)
    assert len(fr.pedidos) == 2
    fr3 = Fracttal({E.DECIDIR_REQUISICAO: {"success": False, "message": "STATE_CHANGED"}})
    with pytest.raises(E.Recusado, match="STATE_CHANGED"):
        estoque(fr3).aprovar_requisicao("101", "ok", CONTA)


def test_o_corpo_da_saida_ligada(monkeypatch):
    """O corpo capturado da tela do Fracttal em 12/11/2026, campo a campo: o mesmo uuid no `id` e no `idInternal`, a requisição
    na referência, o almoxarifado, o responsável, o dia de Brasília e a hora UTC, a OS no `document` e as peças como vieram."""
    monkeypatch.setattr(uuid, "uuid4", lambda: uuid.UUID("12345678-1234-5678-1234-567812345678"))
    fr = Fracttal({E.SAIDA: ok({"id": 88001})})
    req = E.requisicao_da_linha(_req(101, "4521", almox=10))
    pecas = [_det(1, "SP-1", 2)]
    quando = datetime(2026, 11, 12, 2, 30, 15, 123000, tzinfo=timezone.utc)          # 23:30 de 11/11 em Brasília
    assert estoque(fr).saida_da_requisicao(req, pecas, RESPONSAVEL, agora=quando) == "88001"
    u = "12345678-1234-5678-1234-567812345678"
    assert fr.pedidos == [(E.SAIDA, {
        "id": u, "idInternal": u, "id_movement_reference": 101, "is_from_work_order": True, "id_movement_type": 4,
        "movements_types_description": "WORK_ORDER", "id_movement_state": 2, "movements_states_description": "RETURN",
        "id_warehouse_source": 10, "id_warehouse_target": None, "id_responsible": 501,
        "responsible_description": "Pessoa Teste  {P-01}", "date": "2026-11-11", "date_create": "2026-11-12T02:30:15.123Z",
        "document": "4521", "folio_source": "", "symbol": "R$", "currency_code": "BRL", "id_third_party": None,
        "third_parties_name": "", "id_cost_center": None, "warehouses_target_description": "", "costs_center_description": "",
        "description": "", "status_display": "", "items": pecas})]
    for ruim in ({}, {"id": "501"}, {"id": "", "descricao": "x"}):
        with pytest.raises(ValueError):
            estoque(fr).saida_da_requisicao(req, pecas, ruim)
    with pytest.raises(ValueError):
        estoque(fr).saida_da_requisicao(req, [], RESPONSAVEL)
    assert len(fr.pedidos) == 1


def test_as_pecas_e_o_responsavel():
    fr = Fracttal({E.DETALHES: em_paginas([_det(1, "SP-1")]),
                   E.RESPONSAVEIS: em_paginas([{"id": 9, "email": "outra@exemplo.test", "description": "Outra  {P-09}"},
                                               {"id": 501, "email": "Pessoa.Teste@Exemplo.com", "description": "Pessoa  {P-01}"},
                                               {"id": 502, "email": "sem.descricao@exemplo.test", "description": ""}])})
    est = estoque(fr)
    assert est.pecas_da_requisicao("101") == [_det(1, "SP-1")]                           # como vêm (a saída as devolve)
    assert fr.pedidos[0] == (E.DETALHES, {"id_movement": 101, "page": 1, "limit": 200, "start": 0})
    assert est.responsavel("pessoa.teste@exemplo.com") == {"id": "501", "descricao": "Pessoa  {P-01}"}
    assert fr.pedidos[1] == (E.RESPONSAVEIS, {"filter": [], "sort": [], "is_tree": False, "node": None, "noShowDisabled": True,
                                              "page": 1, "limit": 200, "start": 0})
    assert est.responsavel("ninguem@exemplo.test") is None and est.responsavel("sem.descricao@exemplo.test") is None
    with pytest.raises(ValueError):
        est.responsavel(" ")


def test_o_rank_sai_das_pecas_do_fracttal():
    """O mapa por código (a lista de peças inteira) dá a letra do Rank: "2. Rank A" é A; o "1.Avariado", a peça sem a
    Classificação 2 e a que o mapa não tem são a curva desconhecida."""
    mapa = E.mapa_das_pecas(PECAS + [{"code": " sp-1 ", "groups_2_description": "2. Rank A", "groups_description": "Outro"},
                                     {"code": ""}])
    assert mapa["SP-1"] == {"classificacao_2": "2. Rank A"} and mapa["SP-6"] == {"tipo": "Cabos"}     # o 1º código vale
    assert [CL.letra_da_peca(mapa, c) for c in ("SP-1", "sp-2 ", "SP-4", "SP-5", "SP-6", "SP-99", "")] == [
        "A", "B", "C", "", "", "", ""]
    falso, agora = _falso(), [10.0]
    assert CL.mapa_guardado(falso, relogio=lambda: agora[0])["SP-2"]["classificacao_2"] == "3. Rank B"
    CL.guardadas(falso, relogio=lambda: agora[0])                                       # a mesma cópia: as opções e o mapa
    assert falso.chamadas == ["pecas_com_grupos"]


# ── aceitar: a ordem, as falhas e as recusas ────────────────────────────────────────────────────────────────────────────

def test_aceitar_aprova_antes_da_saida_e_rele(rq):
    falso = _falso()
    r = _aceitar(rq, falso, A_RANK_A, comentario="conferida no campo")
    assert r["confirmada"] is True and re.search(r"Requisição da OS 4521 aceita às \d\d:\d\d", r["mensagem"])
    assert falso.chamadas[falso.chamadas.index("reler_requisicao"):] == [
        "reler_requisicao", "pecas_da_requisicao", "modo", "saida_com_a_os", "ler", "aprovar_requisicao",
        "saida_da_requisicao", "reler_requisicao", "ler"]
    assert falso.decisoes == [{"id": A_RANK_A, "approved": True, "approved_comment": "conferida no campo", "id_accounts": 77,
                               "accounts_log_name": "Pessoa Teste"}]
    assert falso.saidas[0]["id_movement_reference"] == A_RANK_A and falso.saidas[0]["id_responsible"] == 501
    assert falso.ler("10")["1"]["saldo"] == 4.0 and falso.reler_requisicao(str(A_RANK_A))["estado"] == 5
    (ev,) = _eventos(rq, "requisicao_aceita")
    # o id do CATÁLOGO (o `id_item_original`), e não o da linha: o saldo de antes e de depois se acha por ele (a revisão, I2)
    assert (ev["movimento_fracttal"], ev["id_almoxarifado"], ev["id_item"], ev["codigo"]) == ("101", "10", "1", "SP-1")
    assert (ev["de_qtd"], ev["para_qtd"], ev["contado_qtd"]) == (5, 4, 1)
    assert falso.saidas[0]["items"] == DETALHES[A_RANK_A]                               # as linhas vão cruas na saída
    assert re.fullmatch(r"[0-9a-f]{24}", ev["pessoa_hmac"]) and ev["usina_id"] == 1
    assert F.decifrar(rq.config, F.ABA_EVENTO, ev) == {"os": "4521", "curva": "A", "saida": falso.saidas[0]["id"], "por": "pcm",
                                                       "confirmada": True, "comentario": "conferida no campo"}
    assert "4521" not in json.dumps(ev) and "conferida" not in json.dumps(ev)            # a OS e o comentário só cifrados
    # sem o comentário do PCM, o padrão com o nome da conta
    falso2 = _falso()
    _aceitar(rq, falso2, B_E_C)
    assert falso2.decisoes[0]["approved_comment"] == "Aceita pelo Nexus por Pessoa Teste"
    falso3 = _falso(reqs=[_req(105, "4525")], detalhes={105: [_det(2, "SP-2")]})
    _aceitar(rq, falso3, 105, por="sozinha")                                            # o do automático
    assert falso3.decisoes[0]["approved_comment"] == "Aceita pelo Nexus (Rank B ou C), na sessão de Pessoa Teste"


def test_state_changed_registra_a_falha_e_nada_mais(rq):
    """A requisição entregue no Fracttal entre a releitura e a aprovação: o Fracttal diz `STATE_CHANGED`, o passo para ali e
    vira o evento `requisicao_falha`, e nenhuma saída sai."""
    class Entregue(EstoqueFalso):
        def aprovar_requisicao(self, id_requisicao, comentario, conta):
            self.mudar_requisicao(id_requisicao, id_movement_state=5)
            return super().aprovar_requisicao(id_requisicao, comentario, conta)
    falso = Entregue(json.loads(json.dumps(SALDOS)), pecas_do_catalogo=PECAS, requisicoes=REQS, detalhes=DETALHES)
    with pytest.raises(RQ.Falhou) as ex:
        _aceitar(rq, falso, A_RANK_A)
    assert ex.value.status == 409 and "STATE_CHANGED" in ex.value.mensagem and "Nada mudou" in ex.value.mensagem
    assert "saida_da_requisicao" not in falso.chamadas and falso.saidas == []
    (ev,) = _eventos(rq, "requisicao_falha")
    assert ev["movimento_fracttal"] == "101"
    assert F.decifrar(rq.config, F.ABA_EVENTO, ev) == {
        "motivo": "STATE_CHANGED", "passo": "aprovar", "por": "pcm", "os": "4521", "travada": False,
        "pecas": [{"codigo": "SP-1", "id_item": "1", "qtd": 1, "curva": "A"}]}         # as peças com a curva (M2)


def test_o_saldo_que_nao_da_fica_antes_de_aprovar(rq):
    """O saldo não dá: o Nexus confere ANTES de aprovar (a revisão, M8), nada vai ao Fracttal, a requisição fica em Falhas com a
    peça que falta, e o automático não tenta de novo. Com a entrada feita, o "Tentar de novo" aceita."""
    saldos = json.loads(json.dumps(SALDOS))
    saldos["10"]["2"]["saldo"] = 1                                                      # a B_E_C pede 2 da SP-2
    falso = _falso(saldos=saldos)
    with pytest.raises(RQ.Falhou) as ex:
        _aceitar(rq, falso, B_E_C, por="sozinha")
    assert ex.value.status == 409 and "SP-2 tem 1 e a requisição pede 2" in ex.value.mensagem
    assert falso.decisoes == [] and falso.saidas == []
    d = RQ.montar(rq.config, falso, _ctx(rq, falso))
    (f,) = d["falhas"]
    assert f["id"] == str(B_E_C) and "saldo insuficiente" in f["falha"]["motivo"] and not f["falha"]["travada"]
    assert d["ids_sozinhas"] == [] and not d["sozinhas"]
    falso._itens["10"]["2"]["saldo"] = 8.0
    assert _aceitar(rq, falso, B_E_C)["confirmada"]
    assert RQ.montar(rq.config, falso, _ctx(rq, falso))["falhas"] == []                # aceita, sai das Falhas


def test_a_aprovada_com_a_saida_recusada_e_a_nova_tentativa_pula_a_aprovacao(rq):
    """O "não" do Fracttal na saída (o `Recusado`): a requisição fica aprovada, a saída não passou, ela vai para Falhas (sem a
    trava: o Fracttal disse que não fez) e a próxima tentativa pula a aprovação."""
    class UmaVezNao(EstoqueFalso):
        nao = True

        def saida_da_requisicao(self, *a, **k):
            if self.nao:
                self.nao = False
                raise E.Recusado("ALGUM_MOTIVO", "saida_da_requisicao")
            return super().saida_da_requisicao(*a, **k)
    falso = UmaVezNao(json.loads(json.dumps(SALDOS)), pecas_do_catalogo=PECAS, requisicoes=REQS, detalhes=DETALHES)
    with pytest.raises(RQ.Falhou) as ex:
        _aceitar(rq, falso, B_E_C, por="sozinha")
    assert ex.value.status == 409 and "ficou aprovada, mas a saída não passou (ALGUM_MOTIVO)" in ex.value.mensagem
    assert falso.reler_requisicao(str(B_E_C))["aprovada"] is True and falso.saidas == []
    (f,) = RQ.montar(rq.config, falso, _ctx(rq, falso))["falhas"]
    assert f["falha"]["passo"] == "saida" and not f["falha"]["travada"]
    antes = len(falso.chamadas)
    assert _aceitar(rq, falso, B_E_C)["confirmada"]
    assert "aprovar_requisicao" not in falso.chamadas[antes:] and len(falso.decisoes) == 1


def test_parcial_cancelada_recusada_e_entregue_ficam_fora(rq):
    reqs = [_req(201, estado=4), _req(202, estado=6), _req(203, decidida=_iso(1)), _req(204, estado=5, aprovada=True,
                                                                                           decidida=_iso(1))]
    falso = _falso(reqs=reqs, detalhes={i: [_det(2, "SP-2")] for i in (201, 202, 203, 204)})
    textos = {201: "entrega parcial: conclua no Fracttal", 202: "cancelada", 203: "recusada", 204: "já está entregue"}
    for rid, texto in textos.items():
        with pytest.raises(Conflito, match=texto):
            _aceitar(rq, falso, rid)
    assert falso.decisoes == [] and falso.saidas == []
    d = RQ.montar(rq.config, falso, _ctx(rq, falso))
    assert [x["id"] for x in d["parciais"]] == ["201"] and d["ids_sozinhas"] == [] and not d["para_pcm"]
    assert {x["id"] for x in d["decididas"]} == {"203", "204"}


def test_sem_o_dono_nada_vai(rq):
    """Sem o responsável do Fracttal a saída não vai, e sem a conta a aprovação não vai: 409 antes de qualquer gravação."""
    falso = _falso()
    with pytest.raises(Conflito, match="lista de responsáveis"):
        _aceitar(rq, falso, A_RANK_A, responsavel=None)
    with pytest.raises(Conflito, match="conta do Fracttal"):
        _aceitar(rq, falso, A_RANK_A, conta=None)
    assert falso.decisoes == [] and falso.saidas == [] and _eventos(rq) == []
    falso.mudar_requisicao(A_RANK_A, approved=True)                                     # aprovada: a conta não faz falta
    assert _aceitar(rq, falso, A_RANK_A, conta=None)["confirmada"]


def test_a_aprovada_nao_se_recusa(rq):
    """A aprovada (falta só a saída) não se recusa: 409, nada vai; a não aprovada se recusa com o comentário cifrado."""
    falso = _falso()
    falso.mudar_requisicao(A_RANK_A, approved=True)
    ctx, quem_ = _ctx(rq, falso), quem.colunas(rq.config, PESSOA)
    with pytest.raises(Conflito, match="já foi aprovada"):
        RQ.recusar(rq.config, falso, str(A_RANK_A), ctx=ctx, quem_=quem_, conta=CONTA, comentario="não era desta OS")
    assert falso.decisoes == []
    r = RQ.recusar(rq.config, falso, str(DESCONHECIDA), ctx=ctx, quem_=quem_, conta=CONTA, comentario="não era desta OS")
    assert r["confirmada"] and falso.decisoes[0]["approved"] is False
    (ev,) = _eventos(rq, "requisicao_recusada")
    assert F.decifrar(rq.config, F.ABA_EVENTO, ev)["motivo"] == "não era desta OS" and "desta OS" not in json.dumps(ev)


def test_o_automatico_nao_aceita_a_de_rank_a(rq):
    falso = _falso()
    for rid in (A_RANK_A, DESCONHECIDA, AVARIADO):
        with pytest.raises(Conflito, match="é o PCM que aceita"):
            _aceitar(rq, falso, rid, por="sozinha")
    assert falso.decisoes == []


def test_a_vez_presa_e_o_modo_seguram(rq, monkeypatch):
    falso = _falso()
    monkeypatch.setattr(G, "vez_presa", lambda cfg, almox: "uma gravação do inventário está andando neste almoxarifado.")
    with pytest.raises(Conflito, match="gravação do inventário"):
        _aceitar(rq, falso, A_RANK_A)
    monkeypatch.setattr(G, "vez_presa", lambda cfg, almox: "")
    falso.definir_modo("10", 2)
    with pytest.raises(Conflito, match="modo 2"):
        _aceitar(rq, falso, A_RANK_A)
    assert falso.decisoes == []


# ── a fila ───────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_fila_pelo_rank(rq):
    """Para o PCM: a com peça Rank A e a de curva desconhecida (fora do mapa, ou "1.Avariado"); sozinhas: só B e C conhecidas.
    A mais nova primeiro; o almoxarifado de teste fora."""
    reqs = REQS + [_req(105, "4525", almox=134082, dias=0)]
    falso = _falso(reqs=reqs, detalhes={**DETALHES, 105: [_det(2, "SP-2")]})
    rq.config["NEXUS_ALMOX_TESTE_IDS"] = "134082"
    d = RQ.montar(rq.config, falso, _ctx(rq, falso))
    assert [x["id"] for x in d["para_pcm"]] == ["101", "103", "104"]
    assert d["para_pcm"][0]["rank_a"] and not d["para_pcm"][1]["rank_a"]
    assert [p["curva"] for p in d["para_pcm"][1]["pecas"]] == [""] and [p["curva"] for p in d["para_pcm"][2]["pecas"]] == [""]
    assert [x["id"] for x in d["sozinhas"]] == ["102"] and d["ids_sozinhas"] == ["102"]
    assert [p["curva"] for p in d["sozinhas"][0]["pecas"]] == ["B", "C"]
    assert d["n_total"] == 4                                                            # sem a do almoxarifado de teste
    # o mapa que não tem nada: toda peça é desconhecida, e nada vai sozinho
    assert RQ.montar(rq.config, falso, RQ.contexto(rq.config, {}))["ids_sozinhas"] == []


def test_as_pecas_ficam_na_copia_de_10_minutos(rq):
    falso = _falso()
    RQ.montar(rq.config, falso, _ctx(rq, falso))
    RQ.montar(rq.config, falso, _ctx(rq, falso))
    assert falso.chamadas.count("pecas_da_requisicao") == 4                              # as 4 pendentes, uma vez cada


# ── o automático ─────────────────────────────────────────────────────────────────────────────────────────────────────

def test_o_automatico_aceita_so_as_b_e_c(rq):
    falso = _falso()
    d = RQ.montar(rq.config, falso, _ctx(rq, falso))
    ctrl = RQ.iniciar_automatico(rq.config, falso, d["ids_sozinhas"], ctx=_ctx(rq, falso),
                                 quem_=quem.colunas(rq.config, PESSOA), conta=CONTA, responsavel=RESPONSAVEL)
    assert ctrl["estado"] == "gravando" and ctrl["total"] == 1
    RQ.aguardar(30)
    est = RQ.estado_automatico(rq.config)
    assert est["estado"] == "concluida" and est["aceitas"] == 1 and "1 aceitas" in est["texto"]
    evs = _eventos(rq, "requisicao_aceita_sozinha")
    assert {(e["codigo"], e["de_qtd"], e["para_qtd"]) for e in evs} == {("SP-2", 8, 6), ("SP-4", 3, 2)}
    assert F.decifrar(rq.config, F.ABA_EVENTO, evs[0])["por"] == "sozinha"
    for rid in (A_RANK_A, DESCONHECIDA, AVARIADO):                                       # a A e a desconhecida ficam
        assert falso.reler_requisicao(str(rid))["estado"] == 3
    d = RQ.montar(rq.config, falso, _ctx(rq, falso))
    (g,) = d["aceitas_sozinhas"]
    assert g["id"] == "102" and g["os"] == "4522" and {p["codigo"] for p in g["pecas"]} == {"SP-2", "SP-4"}
    with pytest.raises(Conflito, match="Nenhuma"):
        RQ.iniciar_automatico(rq.config, falso, d["ids_sozinhas"], ctx=_ctx(rq, falso), quem_={}, conta=CONTA,
                              responsavel=RESPONSAVEL)


def test_o_automatico_para_no_limite_e_um_de_cada_vez(rq):
    reqs = [_req(301, dias=1), _req(302, dias=2)]
    falso = _falso(reqs=reqs, detalhes={301: [_det(2, "SP-2")], 302: [_det(4, "SP-4")]}, limite_em=1)
    ctx = _ctx(rq, _falso())                            # o mapa de outro falso: a 1ª chamada deste é a do 429

    class Devagar(EstoqueFalso):
        def reler_requisicao(self, *a, **k):
            time.sleep(0.3)
            return super().reler_requisicao(*a, **k)
    RQ.iniciar_automatico(rq.config, falso, ["301", "302"], ctx=ctx, quem_={}, conta=CONTA, responsavel=RESPONSAVEL)
    RQ.aguardar(30)
    est = RQ.estado_automatico(rq.config)
    assert est["estado"] == "parada" and "pausa" in est["parou"] and est["feitas"] == 1      # o 429 para o resto
    devagar = Devagar(json.loads(json.dumps(SALDOS)), pecas_do_catalogo=PECAS, requisicoes=reqs,
                      detalhes={301: [_det(2, "SP-2")], 302: [_det(4, "SP-4")]})
    RQ.iniciar_automatico(rq.config, devagar, ["301"], ctx=ctx, quem_={}, conta=CONTA, responsavel=RESPONSAVEL)
    with pytest.raises(Conflito, match="já está aceitando"):
        RQ.iniciar_automatico(rq.config, devagar, ["302"], ctx=ctx, quem_={}, conta=CONTA, responsavel=RESPONSAVEL)
    assert RQ.estado_automatico(rq.config)["estado"] == "gravando"
    RQ.aguardar(30)


def test_o_deploy_espera_o_automatico(tmp_path):
    """O controle "gravando" salvo há menos de 5 min segura o restart (`gravacao.com_lote_aberto`); o velho e o concluído
    não. O ajudante do deploy importa só a gravação."""
    pasta = tmp_path / "almox_inventario"
    pasta.mkdir()
    agora = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)
    arq = pasta / RQ.ARQUIVO_AUTO
    arq.write_text(json.dumps({"estado": "gravando", "atualizado_em": "2026-11-12T14:58:00Z"}), encoding="utf-8")
    assert "requisicoes" in G.com_lote_aberto(pasta, agora)
    arq.write_text(json.dumps({"estado": "gravando", "atualizado_em": "2026-11-12T14:50:00Z"}), encoding="utf-8")
    assert "requisicoes" not in G.com_lote_aberto(pasta, agora)
    arq.write_text(json.dumps({"estado": "concluida", "atualizado_em": "2026-11-12T14:59:00Z"}), encoding="utf-8")
    assert "requisicoes" not in G.com_lote_aberto(pasta, agora)
    assert list(G._controles(pasta)) == []                       # não é controle de contagem
    assert RQ.ARQUIVO_AUTO == G.ARQUIVO_REQUISICOES_AUTO


# ── a ponte e a tela ─────────────────────────────────────────────────────────────────────────────────────────────────

def _pcm(app_, monkeypatch, falso, email=None):
    monkeypatch.setattr(E, "estoque_da_sessao", lambda app: falso)
    monkeypatch.setattr(RQ, "conta_do_fracttal", lambda email, nome="": dict(CONTA))
    _no_setor(monkeypatch, SID.PCM)
    return com_o_fracttal(app_, _pessoa_ms(app_), email or PESSOA["email"])


def test_a_ponte_serve_a_lista(rq, monkeypatch):
    falso = _falso()
    c = _pcm(rq, monkeypatch, falso)
    r = c.get(LISTA)
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store"
    assert "Para o PCM aceitar (3)" in html and "Rank B e C, a aceitar sozinhas (1)" in html
    assert 'data-rq-auto-n="1"' in html and 'data-rq-auto-pode="1"' in html
    assert f'data-rq-url="/os/_nexus/inventario/requisicoes/{A_RANK_A}/aceitar"' in html
    assert 'rq-curva--a">Rank A' in html and "curva desconhecida" in html and "Aceitar agora as 1 de Rank B e C" in html


def test_a_ponte_aceita_recusa_e_diz_a_falha(rq, monkeypatch):
    falso = _falso()
    c = _pcm(rq, monkeypatch, falso)
    r = c.post(f"{LISTA}/{A_RANK_A}/aceitar", json={"comentario": ""})
    assert r.status_code == 200 and r.get_json()["confirmada"] is True and r.get_json()["volta"] == TELA
    assert falso.decisoes[0]["id_accounts"] == 77 and falso.saidas[0]["id_responsible"] == 501
    html = c.get(TELA).get_data(as_text=True)
    assert "Requisição da OS 4521 aceita às" in html and "cn-certo" in html
    # recusar: o comentário é obrigatório
    r = c.post(f"{LISTA}/{DESCONHECIDA}/recusar", json={"comentario": " "})
    assert r.status_code == 400
    r = c.post(f"{LISTA}/{DESCONHECIDA}/recusar", json={"comentario": "não era peça do estoque"})
    assert r.status_code == 200 and falso.decisoes[-1]["approved"] is False
    assert len(_eventos(rq, "requisicao_recusada")) == 1
    # a falha da saída: o JSON com o motivo e o status do Fracttal
    falso._itens["10"]["5"]["saldo"] = 0.0
    r = c.post(f"{LISTA}/{AVARIADO}/aceitar", json={})
    assert r.status_code == 409 and "saldo insuficiente" in r.get_json()["erro"] and len(falso.decisoes) == 2
    # a já entregue no meio: 409, nada vai
    r = c.post(f"{LISTA}/{A_RANK_A}/aceitar", json={})
    assert r.status_code == 409 and "já está entregue" in r.get_json()["erro"]


def test_as_recusas_da_ponte(rq, monkeypatch, logado):
    falso = _falso()
    monkeypatch.setattr(E, "estoque_da_sessao", lambda app: falso)
    monkeypatch.setattr(RQ, "conta_do_fracttal", lambda email, nome="": dict(CONTA))
    com_o_fracttal(rq, logado, "outra.pessoa@exemplo.test")
    for rota, metodo in ((LISTA, "get"), (f"{LISTA}/{A_RANK_A}/aceitar", "post"), (f"{LISTA}/automatico", "post")):
        r = getattr(logado, metodo)(rota, json={})
        assert r.status_code == 409 and "senha de administrador" in r.get_json()["erro"], rota
    _no_setor(monkeypatch, SID.PCM)
    r = _pessoa_ms(rq).post(f"{LISTA}/{A_RANK_A}/aceitar", json={})
    assert r.status_code == 401 and "/os/login?next=" in r.get_json()["login"]
    r = com_o_fracttal(rq, _pessoa_ms(rq), "outra.pessoa@exemplo.test").post(f"{LISTA}/{A_RANK_A}/aceitar", json={})
    assert r.status_code == 409 and "outra conta" in r.get_json()["erro"]
    _no_setor(monkeypatch, SID.PERFORMANCE)
    assert com_o_fracttal(rq, _pessoa_ms(rq)).post(f"{LISTA}/{A_RANK_A}/aceitar", json={}).status_code == 403
    _no_setor(monkeypatch, SID.PCM)
    r = com_o_fracttal(rq, _pessoa_ms(rq)).post(f"{LISTA}/{A_RANK_A}/aceitar", json={},
                                                 headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    assert falso.decisoes == [] and falso.saidas == []


def test_a_ponte_comeca_o_automatico(rq, monkeypatch):
    falso = _falso()
    c = _pcm(rq, monkeypatch, falso)
    r = c.post(f"{LISTA}/automatico", json={})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    RQ.aguardar(30)
    assert len(_eventos(rq, "requisicao_aceita_sozinha")) == 2
    j = c.get(f"{TELA}/automatico.json").get_json()
    assert j["estado"] == "concluida" and j["andando"] is False and "1 aceitas" in j["texto"]
    r = c.post(f"{LISTA}/automatico", json={})
    assert r.status_code == 409 and "Nenhuma" in r.get_json()["erro"]


def test_a_tela(rq, monkeypatch, logado):
    _no_setor(monkeypatch, SID.PCM)
    html = _pessoa_ms(rq).get(TELA).get_data(as_text=True)
    assert f'data-rq-fonte="{LISTA}"' in html and f'data-rq-automatico="{LISTA}/automatico"' in html
    assert "pcm-requisicoes.js" in html and "gc-explica" in html
    # o "!" diz de onde vem o Rank (a Classificação 2 da peça no Fracttal, não o catálogo do App; a revisão, I3), o corte do
    # automático e a regra da Saída Geral
    explica = html.split("gc-explica-caixa")[1].split("</section>")[0]
    assert "Classificação 2 da peça no Fracttal" in explica and "catálogo do App" not in explica
    assert "01/01/2026" in explica and "o PCM não faz mais a Saída" in explica
    # a cópia de 1 h no login de quem a pediu por último (não "o seu"), o código em conflito e a janela (a re-revisão, N5)
    assert "lida com o seu" not in explica and "cópia de até 1 hora" in explica
    assert "Classificações 2 diferentes" in explica and "7 dias antes da requisição" in explica
    nav = html.split('class="alm-abas"')[1].split("</nav>")[0]
    assert re.search(r'aria-selected="true"[^>]*href="/t/pcm/pecas/requisicoes"', nav)
    # a senha de administrador: a tela diz que precisa entrar pelo Fracttal, e nem pede a lista
    html = logado.get(TELA).get_data(as_text=True)
    assert "entre no Nexus pelo Fracttal" in html and "data-rq-lista" not in html and "pcm-requisicoes.js" not in html


def test_a_auditoria_mostra_a_requisicao(rq, monkeypatch, logado):
    falso = _falso()
    _aceitar(rq, falso, A_RANK_A)
    html = logado.get("/t/pcm/pecas/inventario/auditoria").get_data(as_text=True)
    assert "Requisição aceita pelo PCM" in html and "requisição 101: aprovada, saída feita" in html
    assert "saldo 5 para 4" in html and "motivo cifrado" not in html


# ── a revisão do item 6: a saída nunca sai em dobro ─────────────────────────────────────────────────────────────────

def test_a_saida_geral_do_pcm_segura_a_saida(rq):
    """O PCM já deu a Saída "Geral" com a OS (o caminho de antes do Nexus; a sonda B da revisão, C1): o Nexus acha o movimento
    da peça com a OS no histórico (na `description` ou no `document`) e não faz outra; nem aprova. A requisição vai para Falhas,
    travada, fora do automático."""
    falso = _falso()
    falso.mover("10", "2", "saida", 2, referencia="OS 4522 - saída geral")
    with pytest.raises(RQ.Falhou) as ex:
        _aceitar(rq, falso, B_E_C, por="sozinha")
    assert ex.value.status == 409 and "o PCM já deu a saída da OS 4522 em" in ex.value.mensagem
    assert "aprove e mude o status no Fracttal" in ex.value.mensagem
    assert falso.decisoes == [] and falso.saidas == [] and falso.ler("10")["2"]["saldo"] == 6.0
    d = RQ.montar(rq.config, falso, _ctx(rq, falso))
    (f,) = d["falhas"]
    assert f["id"] == str(B_E_C) and f["falha"]["travada"] and d["ids_sozinhas"] == []
    with pytest.raises(Conflito, match="o PCM já deu a saída da OS 4522"):              # o clique também não passa
        _aceitar(rq, falso, B_E_C)
    assert falso.saidas == []
    # a OS no `document`, e só nele, também vale; outro número que contém a OS não é a OS; outra peça com a OS também não
    desde = _iso(5) + "+00:00"
    falso2 = _falso()
    falso2.mover("10", "4", "saida", 1, documento="4522")
    assert falso2.saida_com_a_os("10", "4522", ["2", "4"], desde)["folio"].startswith("MOV-")
    falso3 = _falso()
    falso3.mover("10", "2", "saida", 1, referencia="OS 45220")
    falso3.mover("10", "1", "saida", 1, referencia="OS 4522")
    assert falso3.saida_com_a_os("10", "4522", ["2", "4"], desde) is None


def test_a_regra_da_os_no_historico():
    movs = [{"id_item": "2", "referencia": "INVENTARIO-x 4522", "documento": "", "tipo": 15, "folio": "M1", "quando": "q1"},
            {"id_item": "2", "referencia": "", "documento": "OT-4522", "tipo": 5, "folio": "M2", "quando": "q2"},
            {"id_item": "2", "referencia": "OS 4522", "documento": "", "tipo": 5, "folio": "M3", "quando": "q3"}]
    assert E.primeira_com_a_os(movs, "4522", ["2"]) == {"folio": "M2", "quando": "q2"}    # o ajuste de inventário não conta
    assert E.primeira_com_a_os(movs, "452", ["2"]) is None
    assert E.primeira_com_a_os(movs, "4522", ["9"]) is None and E.primeira_com_a_os(movs, "", ["2"]) is None


def test_o_automatico_so_vale_para_as_de_depois_da_entrada_no_ar(rq, monkeypatch):
    """A de B e C criada antes de `AUTO_DESDE` (o tempo da Saída Geral à mão) vai para o PCM, com o aviso; o automático a
    recusa (a revisão, C1)."""
    monkeypatch.setattr(RQ, "AUTO_DESDE", _iso(1, 12) + "+00:00")                         # entre a de 1 e a de 2 dias
    falso = _falso()
    d = RQ.montar(rq.config, falso, _ctx(rq, falso))
    assert d["ids_sozinhas"] == [] and str(B_E_C) in [x["id"] for x in d["para_pcm"]]
    assert next(x for x in d["para_pcm"] if x["id"] == str(B_E_C))["antiga"] is True
    with pytest.raises(Conflito, match="é de antes do automático"):
        _aceitar(rq, falso, B_E_C, por="sozinha")
    assert falso.decisoes == []
    assert _aceitar(rq, falso, B_E_C)["confirmada"]                                      # o PCM aceita


def test_a_saida_do_nexus_nao_se_repete(rq):
    """A saída do Nexus passou e a requisição ficou no 3 (a saída que não ligou; a sonda A da revisão, C2): a lista a põe em
    Falhas, travada, fora do automático, e o aceite (o automático e o clique) recusa outra saída, pelo livro."""
    class SaidaQueNaoLiga(EstoqueFalso):
        def saida_da_requisicao(self, requisicao, pecas, responsavel, agora=None):
            nova = super().saida_da_requisicao(requisicao, pecas, responsavel, agora)
            self._movs[str(requisicao["id"])]["id_movement_state"] = 3
            return nova
    falso = SaidaQueNaoLiga(json.loads(json.dumps(SALDOS)), pecas_do_catalogo=PECAS, requisicoes=REQS, detalhes=DETALHES)
    r = _aceitar(rq, falso, B_E_C, por="sozinha")
    assert r["confirmada"] is False and "O Nexus não faz outra saída dela" in r["mensagem"]
    d = RQ.montar(rq.config, falso, _ctx(rq, falso))
    assert d["ids_sozinhas"] == []
    (f,) = d["falhas"]
    assert f["id"] == str(B_E_C) and f["falha"]["travada"] and "o Nexus já fez a saída" in f["falha"]["motivo"]
    RQ.limpar()                                                                          # sem a memória: o livro segura
    for por in ("sozinha", "pcm"):
        with pytest.raises(Conflito, match="o Nexus já fez a saída"):
            _aceitar(rq, falso, B_E_C, por=por)
    assert len(falso.saidas) == 1 and falso.ler("10")["2"]["saldo"] == 6.0


def test_a_memoria_segura_quando_o_livro_nao_grava(rq, monkeypatch):
    """A saída feita e o livro que não grava o aceite: a memória do processo segura a repetição."""
    class SaidaQueNaoLiga(EstoqueFalso):
        def saida_da_requisicao(self, requisicao, pecas, responsavel, agora=None):
            nova = super().saida_da_requisicao(requisicao, pecas, responsavel, agora)
            self._movs[str(requisicao["id"])]["id_movement_state"] = 3
            return nova
    falso = SaidaQueNaoLiga(json.loads(json.dumps(SALDOS)), pecas_do_catalogo=PECAS, requisicoes=REQS, detalhes=DETALHES)
    real = F.acrescentar

    def nao_grava(cfg, aba, linhas):
        if any(str(l.get("tipo", "")).startswith("requisicao_aceita") for l in linhas):
            raise F.Recusada("o banco não respondeu (de mentira)")
        return real(cfg, aba, linhas)
    monkeypatch.setattr(F, "acrescentar", nao_grava)
    r = _aceitar(rq, falso, B_E_C)
    assert "Não consegui anotar no livro" in r["mensagem"]
    with pytest.raises(Conflito, match="o Nexus já fez a saída"):
        _aceitar(rq, falso, B_E_C)
    assert len(falso.saidas) == 1


@pytest.mark.parametrize("erro", [ConnectionError("caiu"), E.ErroFracttal("o Fracttal não devolveu o id", "x")])
def test_a_saida_de_resposta_incerta_trava(rq, erro):
    """A resposta da saída que não veio (a rede, ou o Fracttal sem o id): ela pode ter sido feita; a mensagem não diz que não
    passou, a requisição fica em Falhas travada, e o Nexus não a repete (a revisão, C2 passo 4 e M1)."""
    class Incerta(EstoqueFalso):
        def saida_da_requisicao(self, *a, **k):
            super().saida_da_requisicao(*a, **k)
            raise erro
    falso = Incerta(json.loads(json.dumps(SALDOS)), pecas_do_catalogo=PECAS, requisicoes=REQS, detalhes=DETALHES)
    falso._movs[str(B_E_C)]["id_movement_state"] = 3
    with pytest.raises(RQ.Falhou) as ex:
        _aceitar(rq, falso, B_E_C)
    assert ex.value.status == 502 and "pode ter sido feita" in ex.value.mensagem and "não passou" not in ex.value.mensagem
    falso._movs[str(B_E_C)]["id_movement_state"] = 3                                     # ficou no 3
    RQ.limpar()
    (f,) = RQ.montar(rq.config, falso, _ctx(rq, falso))["falhas"]
    assert f["falha"]["travada"] and f["falha"]["passo"] == "saida"
    with pytest.raises(Conflito, match="pode ter sido feita"):
        _aceitar(rq, falso, B_E_C)
    assert len(falso.saidas) == 1


def test_a_pausa_nao_tira_do_automatico(rq):
    """O 429 na aprovação: nada foi feito, nada vai ao livro, e a requisição segue para o automático (a revisão, M3)."""
    class Pausa(EstoqueFalso):
        def aprovar_requisicao(self, *a, **k):
            raise E.Limite("HTTP 429 (de mentira)")
    falso = Pausa(json.loads(json.dumps(SALDOS)), pecas_do_catalogo=PECAS, requisicoes=REQS, detalhes=DETALHES)
    with pytest.raises(RQ.Falhou) as ex:
        _aceitar(rq, falso, B_E_C, por="sozinha")
    assert ex.value.status == 429 and "Nada mudou" in ex.value.mensagem
    assert _eventos(rq) == []
    assert RQ.montar(rq.config, falso, _ctx(rq, falso))["ids_sozinhas"] == [str(B_E_C)]


def test_dois_aceites_da_mesma_requisicao_ao_mesmo_tempo(rq):
    """Duas pessoas (ou o automático e o clique) aceitando a mesma requisição juntas: a segunda leva 409 enquanto a primeira
    anda (a revisão, I1), e só uma saída sai."""
    import threading
    entrou, solta = threading.Event(), threading.Event()

    class Lento(EstoqueFalso):
        def saida_da_requisicao(self, *a, **k):
            entrou.set()
            solta.wait(10)
            return super().saida_da_requisicao(*a, **k)
    falso = Lento(json.loads(json.dumps(SALDOS)), pecas_do_catalogo=PECAS, requisicoes=REQS, detalhes=DETALHES)
    ctx, quem_ = _ctx(rq, falso), quem.colunas(rq.config, PESSOA)
    resultado = {}

    def primeiro():
        resultado["r"] = RQ.aceitar(rq.config, falso, str(A_RANK_A), por="pcm", ctx=ctx, quem_=quem_, conta=CONTA,
                                    responsavel=RESPONSAVEL)
    th = threading.Thread(target=primeiro)
    th.start()
    assert entrou.wait(10)
    with pytest.raises(Conflito, match="Outra pessoa"):
        RQ.aceitar(rq.config, falso, str(A_RANK_A), por="pcm", ctx=ctx, quem_=quem_, conta=CONTA, responsavel=RESPONSAVEL)
    with pytest.raises(Conflito, match="Outra pessoa"):
        RQ.recusar(rq.config, falso, str(A_RANK_A), ctx=ctx, quem_=quem_, conta=CONTA, comentario="x")
    solta.set()
    th.join(10)
    assert resultado["r"]["confirmada"] and len(falso.saidas) == 1
    assert _aceitar(rq, falso, B_E_C)["confirmada"]                                      # a trava é por requisição, e solta


def test_o_rank_em_conflito_no_mesmo_codigo_e_desconhecido(rq):
    """Duas peças com o mesmo código (a lista traz as inativas) e Ranks diferentes: a curva desconhecida, e o automático não
    trata como B uma A (a revisão, M6)."""
    mapa = E.mapa_das_pecas(PECAS + [{"code": "SP-2", "groups_2_description": "2. Rank A"}])
    assert "classificacao_2" not in mapa["SP-2"] and mapa["SP-4"]["classificacao_2"] == "4. Rank C"
    falso = EstoqueFalso(json.loads(json.dumps(SALDOS)), requisicoes=REQS, detalhes=DETALHES,
                         pecas_do_catalogo=PECAS + [{"code": "SP-2", "groups_2_description": "2. Rank A"}])
    d = RQ.montar(rq.config, falso, _ctx(rq, falso))
    assert d["ids_sozinhas"] == []


def test_a_releitura_que_falha_diz_qual(rq):
    """A releitura do saldo que falha não diz que a requisição não foi à Entrega total (a revisão, M7)."""
    class SemSaldoDepois(EstoqueFalso):
        n = 0

        def ler(self, id_almox):
            SemSaldoDepois.n += 1
            if SemSaldoDepois.n > 1:
                raise E.ErroFracttal("lista pela metade", "ler")
            return super().ler(id_almox)
    falso = SemSaldoDepois(json.loads(json.dumps(SALDOS)), pecas_do_catalogo=PECAS, requisicoes=REQS, detalhes=DETALHES)
    r = _aceitar(rq, falso, A_RANK_A)
    assert r["confirmada"] is True and "aceita às" in r["mensagem"]
    (ev,) = _eventos(rq, "requisicao_aceita")
    assert ev["de_qtd"] == 5 and ev["para_qtd"] is None


def test_o_controle_do_automatico_so_tem_texto_do_nexus(rq):
    """O controle `requisicoes-auto.json` não leva o texto do Fracttal (a revisão, M4): ele fica cifrado no livro."""
    class UmaVezNao(EstoqueFalso):
        def saida_da_requisicao(self, *a, **k):
            raise E.Recusado("TEXTO_DO_FRACTTAL", "saida_da_requisicao")
    falso = UmaVezNao(json.loads(json.dumps(SALDOS)), pecas_do_catalogo=PECAS, requisicoes=REQS, detalhes=DETALHES)
    RQ.iniciar_automatico(rq.config, falso, [str(B_E_C)], ctx=_ctx(rq, falso), quem_={}, conta=CONTA, responsavel=RESPONSAVEL)
    RQ.aguardar(30)
    arq = RQ._arquivo(rq.config)
    assert "TEXTO_DO_FRACTTAL" not in arq.read_text(encoding="utf-8")
    assert RQ.estado_automatico(rq.config)["falhas"] == 1


def test_o_responsavel_nao_achado_fica_guardado(rq):
    """O "não achei" na lista de responsáveis fica 5 min na memória (a revisão, M5): cada abertura não relê a lista inteira."""
    falso = EstoqueFalso({}, responsaveis=[])
    agora = [100.0]
    assert RQ.responsavel_de(falso, "ninguem@exemplo.test", relogio=lambda: agora[0]) is None
    assert RQ.responsavel_de(falso, "ninguem@exemplo.test", relogio=lambda: agora[0]) is None
    assert falso.chamadas == ["responsavel"]
    agora[0] += RQ.SEM_RESPONSAVEL_TTL_S + 1
    RQ.responsavel_de(falso, "ninguem@exemplo.test", relogio=lambda: agora[0])
    assert falso.chamadas == ["responsavel", "responsavel"]


def test_as_recusas_da_rota_do_recusar(rq, monkeypatch, logado):
    """O Recusar pela ponte: a senha de administrador 409, sem o login do Fracttal 401, a conta de outra pessoa 409, outro
    setor 403; e ele não lê a lista de responsáveis (não faz saída; a revisão, M5)."""
    falso = _falso()
    monkeypatch.setattr(E, "estoque_da_sessao", lambda app: falso)
    monkeypatch.setattr(RQ, "conta_do_fracttal", lambda email, nome="": dict(CONTA))
    rota = f"{LISTA}/{DESCONHECIDA}/recusar"
    com_o_fracttal(rq, logado, "outra.pessoa@exemplo.test")
    r = logado.post(rota, json={"comentario": "x"})
    assert r.status_code == 409 and "senha de administrador" in r.get_json()["erro"]
    _no_setor(monkeypatch, SID.PCM)
    assert _pessoa_ms(rq).post(rota, json={"comentario": "x"}).status_code == 401
    r = com_o_fracttal(rq, _pessoa_ms(rq), "outra.pessoa@exemplo.test").post(rota, json={"comentario": "x"})
    assert r.status_code == 409 and "outra conta" in r.get_json()["erro"]
    _no_setor(monkeypatch, SID.PERFORMANCE)
    assert com_o_fracttal(rq, _pessoa_ms(rq)).post(rota, json={"comentario": "x"}).status_code == 403
    assert falso.decisoes == []
    _no_setor(monkeypatch, SID.PCM)
    assert com_o_fracttal(rq, _pessoa_ms(rq)).post(rota, json={"comentario": "não era desta OS"}).status_code == 200
    assert "responsavel" not in falso.chamadas


# ── a rodada 2 da revisão do item 6 (fix-W2-item6-r2): a fronteira, a janela, só a GENERAL e o erro de rede ──────────

@pytest.mark.parametrize("texto", ["OS4522", "OT4522", "OS-4522", "OS 4522", "4522", "ref 4522/2026", "OS Nº4522",
                                   "saída geral da OS4522 - usina"])
def test_a_os_colada_em_letra_e_achada(texto):
    """A fronteira é só por dígito (a re-revisão, C1): "OS4522" e "OT4522" eram a saída em dobro (a sonda B2)."""
    for campo in ("referencia", "documento"):
        movs = [{"id_item": "2", "referencia": "", "documento": "", campo: texto, "tipo": 5, "folio": "M1", "quando": "q"}]
        assert E.primeira_com_a_os(movs, "4522", ["2"]) == {"folio": "M1", "quando": "q"}, (campo, texto)


@pytest.mark.parametrize("texto", ["OS 14522", "OS 45221", "OS145220", "R-45223", "045220"])
def test_a_os_dentro_de_outro_numero_nao_e_achada(texto):
    movs = [{"id_item": "2", "referencia": texto, "documento": "", "tipo": 5, "folio": "M1", "quando": "q"}]
    assert E.primeira_com_a_os(movs, "4522", ["2"]) is None, texto


def test_a_os_com_prefixo_na_requisicao_vale_pelos_digitos():
    """O `document` da requisição com prefixo ("OT-4522", a prova pendente): o alvo são só os dígitos."""
    movs = [{"id_item": "2", "referencia": "OS 4522", "documento": "", "tipo": 5, "folio": "M1", "quando": "q"}]
    assert E.primeira_com_a_os(movs, "OT-4522", ["2"]) == {"folio": "M1", "quando": "q"}
    assert E.primeira_com_a_os(movs, "OT-452", ["2"]) is None


@pytest.mark.parametrize("tipo,conta", [(5, True), (None, True), (4, False), (1, False), (2, False), (8, False),
                                        (15, False), (13, False)])
def test_so_a_saida_geral_conta(tipo, conta):
    """Só a saída GENERAL (`id_movement_type` 5) com a OS é a Saída Geral do PCM (a re-revisão, N1; ruling do coordenador). A
    saída ligada a uma requisição (4, WORK_ORDER: a do Nexus ou a da tela "Ordem de Serviço") é de OUTRA requisição; a compra
    (1), a devolução (2), a transferência (8), o ajuste (15) e a própria requisição (13) não tiram a peça. A linha sem o tipo
    conta: na dúvida, a OS basta, para não dar saída em dobro."""
    movs = [{"id_item": "2", "referencia": "OS 4522", "documento": "", "tipo": tipo, "folio": "M1", "quando": "q"}]
    assert (E.primeira_com_a_os(movs, "4522", ["2"]) is not None) is conta


def test_a_geral_com_a_os_colada_trava(rq):
    """A Geral com "OS4522" na `description` (a sonda B2): nada vai, e a requisição fica travada em Falhas."""
    falso = _falso()
    falso.mover("10", "2", "saida", 2, referencia="OS4522")
    with pytest.raises(RQ.Falhou, match="o PCM já deu a saída da OS 4522"):
        _aceitar(rq, falso, B_E_C, por="sozinha")
    assert falso.saidas == [] and falso.decisoes == []


def test_duas_requisicoes_da_mesma_os_e_da_mesma_peca(rq):
    """A OS com duas tarefas pede a mesma peça duas vezes (a re-revisão, N1; a sonda D): a saída do Nexus da 1ª é ligada (tipo
    4) e não é Saída Geral; a 2ª passa, e a peça sai das duas."""
    reqs = REQS + [_req(105, "4522", dias=1)]
    det = dict(DETALHES)
    det[105] = [_det(2, "SP-2", 1)]
    falso = _falso(reqs=reqs, detalhes=det)
    assert _aceitar(rq, falso, B_E_C, por="sozinha")["confirmada"]
    assert falso.ler("10")["2"]["saldo"] == 6.0
    assert _aceitar(rq, falso, 105, por="sozinha")["confirmada"]
    assert len(falso.saidas) == 2 and falso.ler("10")["2"]["saldo"] == 5.0
    assert not RQ.montar(rq.config, falso, _ctx(rq, falso))["falhas"]


def test_a_devolucao_com_a_os_nao_trava(rq):
    """A entrada de devolução com a OS no `document` não tira a peça (a sonda E1)."""
    falso = _falso()
    falso.mover("10", "2", "entrada", 1, documento="4522", tipo_fracttal=2)
    assert _aceitar(rq, falso, B_E_C, por="sozinha")["confirmada"]


@pytest.mark.parametrize("dias_antes,trava", [(2, True), (6, True), (9, False)])
def test_a_janela_comeca_7_dias_antes_da_requisicao(rq, dias_antes, trava):
    """A peça pode sair pela Geral antes de o técnico lançar o recurso no App: a busca começa 7 dias antes da `date_create` da
    requisição (ruling do coordenador; a sonda B3, com a Geral 2 dias antes, deixava passar)."""
    falso = _falso()
    falso.mover("10", "2", "saida", 2, referencia="OS 4522", quando=_iso(2 + dias_antes) + "+00:00")  # a requisição é de 2 dias
    if trava:
        with pytest.raises(RQ.Falhou, match="o PCM já deu a saída da OS 4522"):
            _aceitar(rq, falso, B_E_C)
        assert falso.saidas == []
    else:
        assert _aceitar(rq, falso, B_E_C)["confirmada"] and len(falso.saidas) == 1


def _sem_a_os_no_historico(falso, n):
    """Tira a OS das linhas do histórico que a saída do Nexus deixou (a prova pendente: o `document` pode não vir)."""
    for m in falso.movimentos[n:]:
        m["documento"] = ""


def test_a_saida_com_o_erro_de_rede_do_os_creator_trava(rq):
    """A saída feita no Fracttal e a resposta perdida pela rede, com o `FracttalError` do OS Creator (`Exception` pura, que o
    adaptador de verdade traduz; aqui chega cru, pelo falso: a re-revisão, N2 e as sondas F5 e F6). A 1ª tentativa diz "pode
    ter sido feita" e trava; a 2ª, sem a OS no histórico, não faz outra saída."""
    class RedeCaiu(EstoqueFalso):
        def saida_da_requisicao(self, requisicao, *a, **k):
            n = len(self.movimentos)
            try:
                super().saida_da_requisicao(requisicao, *a, **k)
            finally:
                _sem_a_os_no_historico(self, n)
            self._movs[str(requisicao["id"])]["id_movement_state"] = 3
            raise FracttalErrorDoOSCreator("Erro de conexão (RPC inventories.outputs_insert): ReadTimeout")
    falso = RedeCaiu(json.loads(json.dumps(SALDOS)), pecas_do_catalogo=PECAS, requisicoes=REQS, detalhes=DETALHES)
    with pytest.raises(RQ.Falhou) as ex:
        _aceitar(rq, falso, A_RANK_A)
    assert ex.value.status == 502 and "pode ter sido feita" in ex.value.mensagem and "não repete" in ex.value.mensagem
    (f,) = _eventos(rq, "requisicao_travada")
    assert F.decifrar(rq.config, F.ABA_EVENTO, f)["passo"] == "saida"
    with pytest.raises(Conflito, match="pode ter sido feita"):
        _aceitar(rq, falso, A_RANK_A)
    RQ.limpar()                                                                          # o Nexus reiniciou: o livro segura
    with pytest.raises(Conflito, match="pode ter sido feita"):
        _aceitar(rq, falso, A_RANK_A)
    assert len(falso.saidas) == 1 and falso.ler("10")["1"]["saldo"] == 4.0


def test_a_releitura_com_o_erro_de_rede_grava_o_aceite(rq):
    """A saída passou e a RELEITURA cai na rede (a sonda F7 a F9): o aceite vai ao livro assim mesmo, e depois do restart o
    Nexus não faz outra saída."""
    class ReleituraCai(EstoqueFalso):
        depois = False

        def saida_da_requisicao(self, requisicao, *a, **k):
            n = len(self.movimentos)
            nova = super().saida_da_requisicao(requisicao, *a, **k)
            _sem_a_os_no_historico(self, n)
            self._movs[str(requisicao["id"])]["id_movement_state"] = 3
            self.depois = True
            return nova

        def reler_requisicao(self, *a, **k):
            if self.depois:
                self.depois = False
                raise FracttalErrorDoOSCreator("Erro de conexão (RPC inventories.movements_new_list): ReadTimeout")
            return super().reler_requisicao(*a, **k)

        def ler(self, id_almox):
            if self.depois is False and len(self.saidas):
                raise FracttalErrorDoOSCreator("RPC inventories.warehouses_items_stock HTTP 503 — fora")
            return super().ler(id_almox)
    falso = ReleituraCai(json.loads(json.dumps(SALDOS)), pecas_do_catalogo=PECAS, requisicoes=REQS, detalhes=DETALHES)
    r = _aceitar(rq, falso, A_RANK_A)
    assert r["confirmada"] is False and "não consegui reler a requisição" in r["mensagem"]
    (ev,) = _eventos(rq, "requisicao_aceita")
    assert ev["de_qtd"] == 5 and ev["para_qtd"] is None
    RQ.limpar()                                                                          # o Nexus reiniciou
    with pytest.raises(Conflito, match="o Nexus já fez a saída"):
        _aceitar(rq, falso, A_RANK_A)
    assert len(falso.saidas) == 1


def test_a_aprovacao_com_o_erro_de_rede_pode_ter_sido_feita(rq):
    """O erro de rede na aprovação: "pode ter sido aprovada", a falha registrada, sem trava (nada saiu do saldo)."""
    class AprovaCai(EstoqueFalso):
        def aprovar_requisicao(self, *a, **k):
            raise FracttalErrorDoOSCreator("RPC inventories.outputs_orders_update HTTP 500 — erro")
    falso = AprovaCai(json.loads(json.dumps(SALDOS)), pecas_do_catalogo=PECAS, requisicoes=REQS, detalhes=DETALHES)
    with pytest.raises(RQ.Falhou) as ex:
        _aceitar(rq, falso, A_RANK_A)
    assert ex.value.status == 502 and "pode ter sido aprovada" in ex.value.mensagem
    (f,) = _eventos(rq, "requisicao_falha")
    assert F.decifrar(rq.config, F.ABA_EVENTO, f)["passo"] == "aprovar" and falso.saidas == []


def test_a_lista_com_o_fracttal_fora_nas_pecas(rq):
    """A rede na leitura das peças de uma pendente não derruba a lista (a sonda F10): a requisição diz que não leu."""
    class PecasCai(EstoqueFalso):
        def pecas_da_requisicao(self, *a, **k):
            raise FracttalErrorDoOSCreator("Erro de conexão (RPC inventories.movements_details_list): ReadTimeout")
    falso = PecasCai(json.loads(json.dumps(SALDOS)), pecas_do_catalogo=PECAS, requisicoes=REQS, detalhes=DETALHES)
    d = RQ.montar(rq.config, falso, _ctx(rq, falso))
    assert d["para_pcm"] and all(x["erro_pecas"].startswith("não consegui ler as peças agora") for x in d["para_pcm"])
    assert d["ids_sozinhas"] == []


def test_a_ponte_com_o_fracttal_fora_diz_e_nao_cai(rq, monkeypatch):
    """O GET da lista com o Fracttal fora, pelo adaptador de verdade (o `FracttalError` traduzido): uma mensagem, não um 500."""
    fr = Fracttal({E.PECAS: em_paginas(PECAS),
                   E.MOVIMENTOS: FracttalErrorDoOSCreator("Erro de conexão (RPC inventories.movements_new_list): ReadTimeout")})
    c = _pcm(rq, monkeypatch, estoque(fr))
    r = c.get(LISTA)
    assert r.status_code == 502 and "Não consegui falar" in r.get_json()["erro"]


def test_a_trava_nao_depende_de_decifrar(rq, monkeypatch):
    """A falha travada é um evento próprio (`requisicao_travada`), e a trava vale pelo tipo (a re-revisão, N3; a sonda G): sem
    a chave do cadastro, ou com a de outra instalação, depois do restart, o Nexus não faz outra saída."""
    class Incerta(EstoqueFalso):
        def saida_da_requisicao(self, requisicao, *a, **k):
            n = len(self.movimentos)
            super().saida_da_requisicao(requisicao, *a, **k)
            _sem_a_os_no_historico(self, n)
            self._movs[str(requisicao["id"])]["id_movement_state"] = 3
            raise ConnectionError("caiu")
    falso = Incerta(json.loads(json.dumps(SALDOS)), pecas_do_catalogo=PECAS, requisicoes=REQS, detalhes=DETALHES)
    with pytest.raises(RQ.Falhou):
        _aceitar(rq, falso, A_RANK_A)
    RQ.limpar()
    monkeypatch.setattr(F, "decifrar", lambda cfg, aba, linha: {})
    (f,) = RQ.montar(rq.config, falso, _ctx(rq, falso))["falhas"]
    assert f["falha"]["travada"] and f["id"] == str(A_RANK_A)
    with pytest.raises(Conflito):
        _aceitar(rq, falso, A_RANK_A)
    assert len(falso.saidas) == 1



# ── a re-revisão 2 do item 6, N6: o zero à esquerda e o document com mais de um número ──────────────────────────────

@pytest.mark.parametrize("os_,texto", [("018524", "OS 18524"), ("18524", "OS 018524"), ("018524", "OS0018524"),
                                       ("OT-2026-4522", "OS 4522"), ("4522-1", "OS 4522"), ("4522-1", "saída 1")])
def test_a_os_sem_zero_a_esquerda_e_cada_numero_do_document(os_, texto):
    """A OS compara sem os zeros à esquerda, dos dois lados ("018524" acha a 18524), e o `document` da requisição com mais de
    um número procura cada um: na dúvida, uma recusa a mais para o PCM conferir, nunca uma saída em dobro (o ruling)."""
    movs = [{"id_item": "2", "referencia": texto, "documento": "", "tipo": 5, "folio": "M1", "quando": "q"}]
    assert E.primeira_com_a_os(movs, os_, ["2"]) == {"folio": "M1", "quando": "q"}, (os_, texto)


@pytest.mark.parametrize("os_,texto", [("18524", "OS 185240"), ("018524", "OS 118524"), ("4522", "OS 45221")])
def test_o_zero_a_esquerda_nao_acha_outro_numero(os_, texto):
    movs = [{"id_item": "2", "referencia": texto, "documento": "", "tipo": 5, "folio": "M1", "quando": "q"}]
    assert E.primeira_com_a_os(movs, os_, ["2"]) is None, (os_, texto)



# ── a revisão final do ramo: só no servidor (I1) e o automático que sobe desligado (C1) ─────────────────────────────

def test_requisicao_so_se_grava_no_servidor(rq, monkeypatch):
    """Um Nexus no PC (sem a NEXUS_INVENTARIO_GRAVAR=1) não aceita, não recusa nem começa o automático: 409 antes de qualquer
    leitura (nem o responsável nem as peças), como a gravação da contagem (`gravacao._so_no_servidor`)."""
    monkeypatch.setitem(rq.config, "NEXUS_INVENTARIO_GRAVAR", "")
    falso = _falso()
    c = _pcm(rq, monkeypatch, falso)
    for rota, corpo in ((f"{LISTA}/{A_RANK_A}/aceitar", {}), (f"{LISTA}/{A_RANK_A}/recusar", {"comentario": "x"}),
                        (f"{LISTA}/automatico", {})):
        r = c.post(rota, json=corpo)
        assert r.status_code == 409 and "só roda no servidor" in r.get_json()["erro"], rota
    assert falso.chamadas == [] and falso.decisoes == [] and falso.saidas == []
    for chamar in (lambda: _aceitar(rq, falso, A_RANK_A),
                   lambda: RQ.recusar(rq.config, falso, str(A_RANK_A), ctx={}, quem_={}, conta=CONTA, comentario="x"),
                   lambda: RQ.iniciar_automatico(rq.config, falso, [str(B_E_C)], ctx={}, quem_={}, conta=CONTA,
                                                 responsavel=RESPONSAVEL)):
        with pytest.raises(Conflito, match="só roda no servidor"):
            chamar()
    assert falso.decisoes == [] and falso.saidas == []
    assert c.get(LISTA).status_code == 200                                   # a lista (só leitura) abre no PC


def test_o_automatico_sobe_desligado():
    """O valor do código é None: o aceite automático das de Rank B e C sobe desligado (ligar é trocar o None pela data)."""
    assert RQ.AUTO_DESDE is None


def test_desligado_nenhuma_vai_sozinha(rq, monkeypatch):
    """Desligado: as de Rank B e C ficam em "Para o PCM aceitar", com o selo delas; nenhuma vai sozinha; o botão "Aceitar
    agora" e o grupo das sozinhas somem; o automático e o aceite "sozinha" recusam; a tela diz, no "!" e numa linha curta."""
    monkeypatch.setattr(RQ, "AUTO_DESDE", None)
    falso = _falso()
    d = RQ.montar(rq.config, falso, _ctx(rq, falso))
    assert d["ids_sozinhas"] == [] and d["sozinhas"] == [] and d["auto_ligado"] is False
    b_c = next(x for x in d["para_pcm"] if x["id"] == str(B_E_C))
    assert b_c["de_quem"] == "sozinha" and not b_c["antiga"]
    with pytest.raises(Conflito, match="ainda está desligado"):
        _aceitar(rq, falso, B_E_C, por="sozinha")
    with pytest.raises(Conflito, match="ainda está desligado"):
        RQ.iniciar_automatico(rq.config, falso, [str(B_E_C)], ctx=_ctx(rq, falso), quem_={}, conta=CONTA,
                              responsavel=RESPONSAVEL)
    c = _pcm(rq, monkeypatch, _falso())
    html = c.get(LISTA).get_data(as_text=True)
    assert "Aceitar agora" not in html and "a aceitar sozinhas" not in html and 'data-rq-auto-n="0"' in html
    assert 'inv-selo--info">Rank B e C</span>' in html and "Criada antes do automático" not in html
    tela = c.get(TELA).get_data(as_text=True)
    explica = " ".join(re.sub(r"<[^>]+>", "", tela.split("gc-explica-caixa")[1].split("</section>")[0]).split())
    assert "aceite automático das de Rank B e C ainda está desligado" in explica
    fora_do_explica = tela.split("</section>", 1)[1] if "</section>" in tela else tela
    assert "O aceite automático das de Rank B e C ainda está desligado" in fora_do_explica
    assert falso.decisoes == [] and _aceitar(rq, falso, B_E_C)["confirmada"]          # o PCM aceita com o clique


def test_ligado_as_de_b_e_c_vao_sozinhas(rq, monkeypatch):
    """Ligado (a data no lugar do None): as de Rank B e C criadas a partir dela vão sozinhas, com o botão; a linha do desligado
    some."""
    falso = _falso()
    d = RQ.montar(rq.config, falso, _ctx(rq, falso))
    assert d["auto_ligado"] is True and d["ids_sozinhas"] == [str(B_E_C)]
    c = _pcm(rq, monkeypatch, falso)
    assert "Aceitar agora as 1 de Rank B e C" in c.get(LISTA).get_data(as_text=True)
    assert "ainda está desligado" not in c.get(TELA).get_data(as_text=True)

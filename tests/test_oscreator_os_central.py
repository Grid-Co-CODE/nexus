"""A lista central de OS do OS Creator (31/10/2026, tarefa 3.1 do canto central; desenho
`docs/superpowers/specs/2026-10-30-oscreator-canto-central-design.md`, "Etapa 3").

Uma lista só, de todas as OS, para todas as telas: as visões ("Todos", "criadas por mim", "atribuídas a mim", o período)
viram filtros sobre ela. O que estes testes seguram (o módulo é `os_creator/os_central.py`):
- as linhas do REST `work_orders` (uma por tarefa) viram um registro enxuto por OS, com os campos que o Histórico, o
  Garantias e o card mostram; os índices por id, por nº e por código de ativo;
- cada leitura (a faixa) troca só o que ela cobre: a OS que a lista tinha dentro da faixa e não veio fica "a conferir", e a
  noite tira de vez o que não voltou;
- a ação do OS Creator entra na hora (com o registro, ou lida ao vivo pela sessão do pedido; fora de um pedido, fica para a
  próxima faixa);
- o nº da OS vira o id sem pedido nenhum; os filtros das visões, o que não casa sem ambiguidade e o período fora da janela;
- a cópia em disco, atômica, em fluxo, uma escrita a cada 30 s no máximo, e a corrompida que é ignorada; o boot só lê o disco;
- quem quer mexer recebe cópia: a lista e o registro do canto central são os mesmos para todos.
Fracttal e disco são dublês ou pastas de teste: nada vai à rede. Nomes, códigos, usinas e textos são inventados (repositório
público)."""
import gzip
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest

from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
import os_central as OC  # noqa: E402
import os_disco as OD  # noqa: E402 — a cópia em disco da lista (Ruling AY)
import os_registro as OR  # noqa: E402 — o registro e a linha enxuta (Rulings AY e AV)
from os_web import acomp_web, sessao  # noqa: E402

_UTC = timezone.utc


def _iso(dias_atras: float = 0.0, hora: str | None = None) -> str:
    """Uma data do REST (ISO com o fuso), `dias_atras` antes de agora."""
    d = datetime.now(_UTC) - timedelta(days=dias_atras)
    if hora:
        d = d.replace(hour=int(hora[:2]), minute=int(hora[3:5]), second=0, microsecond=0)
    return d.strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _tarefa(os_id, tarefa_id, *, folio=None, status=1, criada=None, item=None, code="CAL-GAM100-INVR1.1",
            descricao="Troca de fusível", tipo="Corretiva", programada=None, inicio=None, fim=None, wo_fim=None,
            evento=None, criador="Pessoa Fictícia Um ", cod_criador="PF01", responsavel="Pessoa Fictícia Dois",
            id_resp=502, labels=(), nota=None):
    """Uma linha do REST `work_orders` (uma por tarefa), com campos que a lista não guarda (que ela tem de jogar fora)."""
    return {"id_work_orders_tasks": tarefa_id, "id_work_order": os_id, "wo_folio": str(folio or 10000 + os_id),
            "id_status_work_order": str(status), "description": descricao,
            "items_log_description": item or "Inversor 1.1 Marca X  Endereço Inventado km 4  { %s }" % code,
            "code": code, "tasks_log_task_type_main": tipo, "creation_date": criada or _iso(1),
            "date_maintenance": programada, "initial_date": inicio, "final_date": fim, "wo_final_date": wo_fim,
            "event_date": evento, "created_by": criador, "code_create_by": cod_criador, "user_assigned": responsavel,
            "personnel_description": responsavel, "id_personnel": id_resp, "task_note": nota, "tasks_duration": 3600,
            "id_task": 7000 + tarefa_id, "groups_1_description": "Usina Inventada", "id_parent_wo": None,
            "parent_description": "// Cliente Alfa/ Usina Inventada/ ", "latitude": None, "rating": 3,
            "labels": [{"id": i, "description": n, "color": "8892a6", "enabled": True} for i, n in labels]}


@pytest.fixture(autouse=True)
def limpo(monkeypatch):
    """Cada teste começa sem lista, sem pasta e sem leitor; nada vai ao Fracttal (o `api` de verdade recusa)."""
    OC.reiniciar()

    def sem_fracttal(*a, **k):
        raise AssertionError("a lista central foi ao Fracttal")
    monkeypatch.setattr(api, "_rpc_call", sem_fracttal)
    yield
    OC.esperar_gravacao(5)
    OC.reiniciar()


# ── o registro enxuto, montado das tarefas ──────────────────────────────────────────────────────────────────────────────
def test_agrupa_tarefas_por_os():
    criada = _iso(2, "11:00")
    linhas = [
        _tarefa(500, 3, criada=criada, code="CAL-GAM100-INVR1.2", descricao="Inspeção do inversor",
                tipo="Inspeção", programada=_iso(1, "08:00"), evento=_iso(2, "10:30"), inicio=_iso(1, "09:00"),
                labels=((11, "CHAMADOS"),)),
        _tarefa(500, 1, criada=criada, code="CAL-GAM100-INVR1.1", programada=_iso(1, "07:00"), evento=_iso(2, "10:00"),
                labels=((11, "CHAMADOS"),),
                nota="Antes\n" + acomp_web.MARCA_NOTA + "\nMarca: Inventada"),
        _tarefa(500, 2, criada=criada, code="CAL-GAM100-INVR1.1", descricao="Troca de fusível",
                labels=((11, "CHAMADOS"),)),
        _tarefa(500, 1, criada=criada, code="CAL-GAM100-INVR1.1"),                    # a mesma tarefa repetida na página
        _tarefa(501, 9, status=3, criada=_iso(3), fim=_iso(1, "15:00"), wo_fim=_iso(1, "16:00"),
                descricao="X" * 300, item="Y" * 100 + " { CAL-GAM100-SKID1 }", code="CAL-GAM100-SKID1",
                nota="uma nota qualquer, sem o bloco do chamado"),
    ]
    rel = OC.receber(linhas, OC.SETE_DIAS, desde=_iso(7)[:19])
    assert rel["os"] == 2 and rel["entraram"] == 2
    lista = OC.atual()
    a, b = lista.por_id[500], lista.por_id[501]
    assert a.folio == "10500" and a.status_id == 1 and a.status == "Em Processo"
    assert a.descricao == "Troca de fusível, Inspeção do inversor"              # as tarefas na ordem do id, sem repetir
    assert a.ativo == "Inversor 1.1 Marca X  Endereço Inventado km 4"[:60]
    assert a.codigos == ("CAL-GAM100-INVR1.1", "CAL-GAM100-INVR1.2") and a.code == "CAL-GAM100-INVR1.2"
    assert a.tipo_tarefa == "Corretiva / Inspeção"                               # o meta das tarefas, como o RPC
    assert a.programada == _iso(1, "07:00")[:19] and a.event_date == _iso(2, "10:00")[:19]
    assert a.inicio == _iso(1, "09:00")[:19] and a.data == criada[:19] and a.data_fim == ""
    assert (a.criado_por, a.cod_criador, a.atribuido_a, a.id_atribuido) == (
        "Pessoa Fictícia Um", "PF01", "Pessoa Fictícia Dois", 502)
    assert a.etiquetas == ((11, "CHAMADOS"),)
    assert acomp_web.MARCA_NOTA in a.note                                        # a nota só com o bloco do chamado
    assert b.note == "" and len(b.descricao) == OC.DESCRICAO_MAX and len(b.ativo) == OC.ATIVO_MAX
    assert b.data_fim == _iso(1, "16:00")[:19] and b.status == "Concluída"     # a data fim da OS vale mais que a da tarefa
    # os índices: o nº, o código do ativo (as duas OS de cada código, da mais nova para a mais velha)
    assert lista.por_folio["10500"] is a and lista.por_folio["10501"] is b
    assert lista.por_codigo_ativo["CAL-GAM100-INVR1.1"] == (a,) and lista.por_codigo_ativo["CAL-GAM100-SKID1"] == (b,)
    # a linha da tela, no formato do `api.list_minhas_os`, com o cliente e a usina pelo catálogo de ativos
    loc = {"CAL-GAM100-INVR1.2": ("Cliente Alfa", "Usina Inventada", "Inversor")}
    l = a.linha(loc)
    assert (l["id"], l["folio"], l["cliente"], l["usina"], l["tipo"], l["status"]) == (
        500, "10500", "Cliente Alfa", "Usina Inventada", "Inversor", "Em Processo")
    assert l["etiquetas"] == [{"id": 11, "nome": "CHAMADOS"}] and l["codigos"] == ["CAL-GAM100-INVR1.1", "CAL-GAM100-INVR1.2"]
    assert set(l) >= {"descricao", "ativo", "code", "criado_por", "atribuido_a", "id_atribuido", "data", "event_date",
                      "data_fim", "programada", "inicio", "equipe", "gatilho", "status_id", "tipo_tarefa", "note"}
    assert b.linha()["cliente"] == "—"
    assert OC.STATUS == api.WO_STATUS                                            # o mesmo rótulo do Histórico
    assert set(OC.MARCAS_DA_NOTA) == {api._CHAMADO_MK, acomp_web.MARCA_NOTA}


# ── a faixa troca só o que ela cobre ────────────────────────────────────────────────────────────────────────────────────
def _carga_inicial():
    """A lista de uma noite (90 dias): A aberta de 2 dias, B aberta de 60 dias, C concluída de 3 dias, D concluída de 30."""
    linhas = [_tarefa(1, 1, status=1, criada=_iso(2)), _tarefa(2, 2, status=2, criada=_iso(60)),
              _tarefa(3, 3, status=3, criada=_iso(3), fim=_iso(1)), _tarefa(4, 4, status=3, criada=_iso(30), fim=_iso(20))]
    OC.receber(linhas, OC.NOITE, desde=_iso(90)[:10])
    return OC.atual()


def test_faixa_troca_so_o_que_cobre():
    antes = _carga_inicial()
    assert set(antes.por_id) == {1, 2, 3, 4} and antes.a_conferir == frozenset()
    # as abertas: só a A veio; a B estava aberta na lista e não veio (mudou de status ou sumiu): "a conferir"
    rel = OC.receber([_tarefa(1, 1, status=2, criada=_iso(2))], OC.ABERTAS)
    lista = OC.atual()
    assert lista.por_id[1].status_id == 2 and lista.a_conferir == frozenset({2}) and rel["a_conferir"] == 1
    assert lista.por_id[3] is antes.por_id[3] and lista.por_id[4] is antes.por_id[4]     # fora da faixa: intactas
    assert lista.versao > antes.versao
    # os 7 dias: a C veio com outro responsável; a A (criada há 2 dias) não veio: "a conferir"; a D (30 dias) fica
    OC.receber([_tarefa(3, 3, status=3, criada=_iso(3), fim=_iso(1), responsavel="Pessoa Fictícia Três")], OC.SETE_DIAS,
               desde=_iso(7)[:19])
    lista = OC.atual()
    assert lista.por_id[3].atribuido_a == "Pessoa Fictícia Três" and lista.a_conferir == frozenset({1, 2})
    assert lista.por_id[4] is antes.por_id[4]
    # a linha de uma OS mais velha que o piso dos 7 dias (a página que encerra a leitura) não entra: pode vir pela metade
    OC.receber([_tarefa(4, 4, status=1, criada=_iso(30))], OC.SETE_DIAS, desde=_iso(7)[:19])
    assert OC.atual().por_id[4].status_id == 3
    # as novas: a E entra; a A (conhecida) não é tocada pela leitura das novas, e segue "a conferir"
    OC.receber([_tarefa(5, 5, criada=_iso(0.01)), _tarefa(1, 1, status=1, criada=_iso(2))], OC.NOVAS)
    lista = OC.atual()
    assert 5 in lista.por_id and lista.por_id[1].status_id == 2 and 1 in lista.a_conferir
    # as finalizadas: a B veio concluída (sai do "a conferir", com a data fim); a F, que a lista não tem, não entra
    OC.receber([_tarefa(2, 2, status=3, criada=_iso(60), fim=_iso(0.5)), _tarefa(6, 6, status=3, fim=_iso(0.5))],
               OC.FINALIZADAS, desde=_iso(2)[:19])
    lista = OC.atual()
    assert lista.por_id[2].status_id == 3 and lista.por_id[2].data_fim == _iso(0.5)[:19] and 2 not in lista.a_conferir
    assert 6 not in lista.por_id
    # e uma faixa que traz a A de novo tira o "a conferir"
    OC.receber([_tarefa(1, 1, status=1, criada=_iso(2))], OC.ABERTAS)
    assert 1 not in OC.atual().a_conferir and OC.atual().por_id[1].status_id == 1


def test_a_noite_tira_de_vez_o_que_nao_voltou():
    _carga_inicial()
    OC.receber([_tarefa(1, 1, status=1, criada=_iso(2))], OC.ABERTAS)            # a B fica "a conferir"
    # a noite de 90 dias: A, B e C voltam; a D (30 dias) não voltou: sai de vez
    OC.receber([_tarefa(1, 1, criada=_iso(2)), _tarefa(2, 2, status=4, criada=_iso(60)),
                _tarefa(3, 3, status=3, criada=_iso(3), fim=_iso(1))], OC.NOITE, desde=_iso(90)[:10])
    lista = OC.atual()
    assert set(lista.por_id) == {1, 2, 3} and lista.a_conferir == frozenset() and lista.por_id[2].status == "Cancelada"
    # a aberta mais velha que a janela fica (toda aberta, de qualquer idade); fechada, sai na noite seguinte
    OC.receber([_tarefa(9, 9, status=1, criada=_iso(OC.JANELA_DIAS + 50))], OC.ABERTAS)
    assert 9 in OC.atual().por_id
    OC.receber([_tarefa(9, 9, status=3, criada=_iso(OC.JANELA_DIAS + 50), fim=_iso(0.1))], OC.FINALIZADAS,
               desde=_iso(1)[:19])
    OC.receber([_tarefa(1, 1, criada=_iso(2))], OC.NOITE, desde=_iso(90)[:10])
    assert 9 not in OC.atual().por_id
    # a janela: o que a lista leu inteiro (a noite, de 90 dias, até o começo dela)
    de, ate = OC.atual().janela
    assert de == _iso(90)[:10] and ate is not None


# ── a ação do OS Creator entra na hora ──────────────────────────────────────────────────────────────────────────────────
def test_acao_entra_na_hora(monkeypatch):
    _carga_inicial()
    # 1) com o registro (as tarefas que a ação acabou de ler): na hora, sem pedido, e sai do "a conferir"
    OC.receber([_tarefa(1, 1, criada=_iso(2))], OC.SETE_DIAS, desde=_iso(7)[:19])
    assert OC.atualizar_os(1, [_tarefa(1, 1, status=2, criada=_iso(2))])
    assert OC.atual().por_id[1].status_id == 2
    # a linha da tela (o formato do `api.list_minhas_os`) também serve
    assert OC.atualizar_os(7, {"id": 7, "folio": "10007", "descricao": "OS criada agora", "status_id": 1,
                               "data": _iso(0)[:19], "criado_por": "Pessoa Fictícia Um", "etiquetas": [],
                               "codigos": ["CAL-GAM100-INVR1.1"], "code": "CAL-GAM100-INVR1.1"})
    assert OC.atual().por_id[7].folio == "10007" and OC.folio_para_id("10007") == 7
    # 2) sem o registro, dentro de um pedido do OS Creator: lida ao vivo pela sessão da pessoa, o que o card já lê
    pedidos = []

    def tarefas(metodo, wid, params, usar_guardada=True):
        pedidos.append(metodo)
        return [{"id": 81, "id_work_order": wid, "wo_folio": "10008", "tasks_description": "Limpeza dos módulos",
                 "items_description": "Inversor 2.1  { CAL-GAM100-INVR2.1 }", "tasks_types_main_description": "Preventiva",
                 "date_maintenance": "2026-10-31T10:00:00", "id_status_work_order": 1, "personnel_description": "Equipe X",
                 "id_assigned_user": 77, "created_by": "Pessoa Fictícia Um", "creation_date": "2026-10-31T09:00:00"}]

    def cabecalho(wid):
        pedidos.append("cabecalho")
        return {"wo_folio": "10008", "id_status_work_order": 1, "created_by": "Pessoa Fictícia Um",
                "labels": [{"id": 3, "description": "ENGENHARIA"}], "creation_date": "2026-10-31T09:00:00"}
    monkeypatch.setattr(api, "_leitura_da_os", tarefas)
    monkeypatch.setattr(api, "_cabecalho_os", cabecalho)
    with sessao.contexto("jwt.de.mentira", "pessoa@exemplo.invalid"):
        assert OC.atualizar_os(8)
    r = OC.atual().por_id[8]
    assert (r.folio, r.status_id, r.tipo_tarefa, r.code, r.etiquetas, r.id_atribuido) == (
        "10008", 1, "Preventiva", "CAL-GAM100-INVR2.1", ((3, "ENGENHARIA"),), 77)
    assert 1 <= len(pedidos) <= 3
    # 3) fora de um pedido: nada vai ao Fracttal; a OS fica para a próxima faixa ("a conferir" e pendente)
    pedidos.clear()
    assert not OC.atualizar_os(3)
    assert pedidos == [] and 3 in OC.atual().a_conferir and 3 in OC.estado()["pendentes_ids"]
    OC.receber([_tarefa(3, 3, status=3, criada=_iso(3), fim=_iso(1))], OC.SETE_DIAS, desde=_iso(7)[:19])
    assert 3 not in OC.atual().a_conferir and 3 not in OC.estado()["pendentes_ids"]
    # 4) a leitura ao vivo que falha não derruba a ação: fica para a próxima faixa
    monkeypatch.setattr(api, "_cabecalho_os", lambda wid: (_ for _ in ()).throw(api.FracttalError("HTTP 429")))
    with sessao.contexto("jwt.de.mentira", "pessoa@exemplo.invalid"):
        assert not OC.atualizar_os(4)
    assert 4 in OC.atual().a_conferir


# ── o nº da OS vira o id sem pedido ─────────────────────────────────────────────────────────────────────────────────────
def test_folio_para_id_sem_pedido():
    _carga_inicial()
    assert OC.folio_para_id("10003") == 3 and OC.folio_para_id(10003) == 3 and OC.folio_para_id(" 10004 ") == 4
    assert OC.folio_para_id("99999") is None and OC.folio_para_id(None) is None and OC.folio_para_id("abc") is None


# ── as visões viram filtros ─────────────────────────────────────────────────────────────────────────────────────────────
def test_filtros_das_visoes():
    linhas = [
        _tarefa(1, 1, criada=_iso(1), criador="Pessoa Fictícia Um", cod_criador="PF01", id_resp=502,
                labels=((11, "CHAMADOS"),)),
        _tarefa(2, 2, criada=_iso(5), criador="Pessoa Fictícia Um", cod_criador="PF01", id_resp=503, status=3,
                fim=_iso(1)),
        _tarefa(3, 3, criada=_iso(10), criador="Pessoa Fictícia Quatro", cod_criador="PF04", id_resp=502),
        _tarefa(4, 4, criada=_iso(40), criador="Pessoa Fictícia Um", cod_criador="PF01", id_resp=502, status=2),
    ]
    OC.receber(linhas, OC.NOITE, desde=_iso(90)[:10])
    de, ate = _iso(30)[:10], _iso(0)[:10]

    def ids(x):
        return None if x is None else [r.id for r in x]
    assert ids(OC.filtrar("todos", None, de, ate)) == [1, 2, 3]                  # da mais nova para a mais velha
    assert ids(OC.filtrar("todos", None, _iso(90)[:10], ate)) == [1, 2, 3, 4]
    assert ids(OC.filtrar("criadas", {"codigo": "pf01"}, de, ate)) == [1, 2]       # pelo código da pessoa no Fracttal
    assert ids(OC.filtrar("criadas", {"nome": "pessoa  ficticia UM"}, de, ate)) == [1, 2]    # o nome, sem homônimo
    assert ids(OC.filtrar("atribuidas", {"id_personnel": 502}, de, ate)) == [1, 3]
    assert ids(OC.filtrar("todos", None, de, ate, etiqueta=11)) == [1]
    assert ids(OC.filtrar("todos", None, de, ate, status=[3])) == [2]
    assert OC.contar("criadas", {"codigo": "PF01"}, de, ate) == 2 and OC.contar("todos", None, de, ate) == 3
    # o que não casa sem ambiguidade segue ao vivo (None): a pessoa sem nada que a identifique, o homônimo, a visão sem o id
    assert OC.filtrar("criadas", {}, de, ate) is None and OC.filtrar("atribuidas", {"nome": "x"}, de, ate) is None
    OC.receber([_tarefa(5, 5, criada=_iso(2), criador="Pessoa Fictícia Um", cod_criador="PF99")], OC.NOVAS)
    assert OC.filtrar("criadas", {"nome": "Pessoa Fictícia Um"}, de, ate) is None                  # dois códigos, um nome
    assert ids(OC.filtrar("criadas", {"codigo": "PF01", "nome": "Pessoa Fictícia Um"}, de, ate)) == [1, 2]
    assert OC.filtrar("criadas", {"nome": "Pessoa Que Não Criou Nada"}, de, ate) is None           # pelo nome, zero: ao vivo
    assert OC.filtrar("criadas", {"codigo": "PF77"}, de, ate) == []                                 # pelo código, zero é zero
    # a OS da ação (o RPC traz o id da conta de quem criou): pelo id da conta
    OC.atualizar_os(6, {"id": 6, "folio": "10006", "status_id": 1, "data": _iso(0.5)[:19], "id_criador": 4242,
                        "criado_por": "Pessoa Fictícia Um"})
    assert 6 in ids(OC.filtrar("criadas", {"id_account": 4242, "codigo": "PF01"}, de, ate))
    # "a conferir" não entra no filtro de status (o status dela é velho) e entra no resto
    OC.receber([_tarefa(4, 4, criada=_iso(40), status=2)], OC.ABERTAS)                              # a 1 some das abertas
    assert 1 in OC.atual().a_conferir
    assert 1 not in ids(OC.filtrar("todos", None, de, ate, status=[1])) and 1 in ids(OC.filtrar("todos", None, de, ate))
    # o período fora da janela lida inteira: ao vivo
    assert OC.filtrar("todos", None, _iso(200)[:10], ate) is None and OC.contar("todos", None, _iso(200)[:10], ate) is None
    OC.reiniciar()
    assert OC.filtrar("todos", None, de, ate) is None                            # sem lista nenhuma: ao vivo


# ── a cópia em disco ────────────────────────────────────────────────────────────────────────────────────────────────────
def test_disco_atomico_e_corrompido(tmp_path, monkeypatch):
    pasta = str(tmp_path / "oscreator")
    monkeypatch.setattr(OD, "GRAVAR_A_CADA_S", 0.3)
    OC.reiniciar(pasta=pasta)
    _carga_inicial()
    OC.receber([_tarefa(1, 1, criada=_iso(2))], OC.ABERTAS)
    assert OC.esperar_gravacao(5)
    arq = os.path.join(pasta, OC.NOME_ARQUIVO)
    antes = OC.atual()
    with gzip.open(arq, "rt", encoding="utf-8") as f:
        linhas = f.read().splitlines()
    cab = json.loads(linhas[0])
    assert cab["formato"] == OC.FORMATO and cab["n"] == 4 and json.loads(linhas[-1]) == {"fim": 4} and len(linhas) == 6
    assert not [n for n in os.listdir(pasta) if n.endswith(".tmp")]
    # o reinício (um deploy) volta pelo disco, sem pedido nenhum ao Fracttal (o `_rpc_call` recusa, ver `limpo`)
    OC.reiniciar(pasta=pasta)
    depois = OC.atual()
    assert dict(depois.por_id) == dict(antes.por_id) and depois.janela == antes.janela
    assert depois.a_conferir == antes.a_conferir == frozenset({2}) and OC.estado()["disco"]["lido"]
    # as ações seguidas viram uma escrita só, e a última chega ao disco em até GRAVAR_A_CADA_S
    OC.atualizar_os(99, [_tarefa(99, 99, criada=_iso(0.1))])
    assert OC.esperar_gravacao(5)
    escritas = []
    real = OD._trocar_de_uma_vez
    monkeypatch.setattr(OD, "_trocar_de_uma_vez", lambda d, e: escritas.append(d) or real(d, e))
    for i in range(5):
        OC.atualizar_os(100 + i, [_tarefa(100 + i, 200 + i, criada=_iso(0.1))])
    assert OC.esperar_gravacao(5) and len(escritas) == 1
    OC.reiniciar(pasta=pasta)
    assert all(100 + i in OC.atual().por_id for i in range(5))
    # a gravação que falha no meio não estraga a cópia de antes (o rascunho ao lado e a troca de uma vez)
    def quebra(destino, escrever):
        tmp = destino + ".tmp-teste"
        escrever(tmp)
        os.remove(tmp)
        raise OSError("disco cheio")
    monkeypatch.setattr(OD, "_trocar_de_uma_vez", quebra)
    OC.atualizar_os(300, [_tarefa(300, 300, criada=_iso(0.1))])
    OC.esperar_gravacao(5)
    assert "disco cheio" in (OC.estado()["disco"]["erro"] or "")
    OC.reiniciar(pasta=pasta)
    assert 300 not in OC.atual().por_id and 104 in OC.atual().por_id
    # a cópia corrompida (cortada no meio, ou lixo) é ignorada: a lista começa vazia e o estado diz por quê
    with gzip.open(arq, "rb") as f:
        bruto = f.read()
    with gzip.open(arq, "wb") as f:
        f.write(bruto[:len(bruto) // 2])
    OC.reiniciar(pasta=pasta)
    assert len(OC.atual().por_id) == 0 and OC.estado()["disco"]["erro"]
    with open(arq, "wb") as f:
        f.write(b"isto nao e gzip")
    OC.reiniciar(pasta=pasta)
    assert len(OC.atual().por_id) == 0 and "ler" in OC.estado()["disco"]["erro"]


# ── quem quer mexer recebe cópia ────────────────────────────────────────────────────────────────────────────────────────
def test_lista_e_copia_para_quem_muda():
    _carga_inicial()
    de, ate = _iso(90)[:10], _iso(0)[:10]
    a = OC.filtrar("todos", None, de, ate)
    a.clear()
    assert len(OC.filtrar("todos", None, de, ate)) == 4                          # a lista devolvida é de quem pediu
    r = OC.atual().por_id[1]
    with pytest.raises((AttributeError, TypeError)):
        r.status_id = 4
    with pytest.raises(TypeError):
        r["status_id"] = 4
    with pytest.raises(TypeError):
        OC.atual().por_id[99] = r
    linha = r.linha()
    linha["status_id"], linha["_ativo_curto"] = 4, "Inversor 1.1"                # o que a tela acrescenta à linha dela
    linha["etiquetas"].append({"id": 1, "nome": "x"})
    assert OC.atual().por_id[1].status_id == 1 and OC.atual().por_id[1].etiquetas == ()
    assert r.get("folio") == r["folio"] == "10001" and r.get("nao_existe", "-") == "-"
    # a versão de antes segue inteira para quem a pegou, depois da troca
    velha = OC.atual()
    OC.receber([_tarefa(1, 1, status=2, criada=_iso(2))], OC.ABERTAS)
    assert velha.por_id[1].status_id == 1 and OC.atual().por_id[1].status_id == 2


def test_indice_por_partes_igual_ao_inteiro():
    """A ação refaz nos índices só os pedaços da OS dela (`_aplicar`), para não montar a lista inteira dentro do pedido de
    alguém (medido com 36 mil OS: ~0,2 s inteira, ~25 ms por partes); o resultado tem de ser o mesmo da montagem inteira.
    As criações são todas de ontem para trás: com a hora trocada no dia de hoje, das 21:00 de Brasília em diante (o dia UTC
    novo) a OS das 16:00 ficava no futuro, e a que a ação mudou para 14 min atrás não era a mais nova (rodada 2 da 3.3)."""
    linhas = [_tarefa(i, i, criada=_iso(1 + i % 40, "%02d:00" % (i % 24)), code="CAL-GAM100-INVR%d.1" % (i % 7),
                      status=1 + i % 4, cod_criador="PF%02d" % (i % 3)) for i in range(1, 120)]
    OC.receber(linhas, OC.NOITE, desde=_iso(90)[:10])
    base = OC.atual()
    mud = {r.id: r.com(status_id=4, data=_iso(0.5)[:19]) for r in base.ordem[10:20]}
    mud.update({r.id: None for r in base.ordem[30:35]})
    mud[999] = OC.registros_do_rest([_tarefa(999, 999, criada=_iso(3), code="CAL-GAM100-INVR3.1")])[999]
    a = OC._aplicar(base, mud, lido_em=1.0, janela=base.janela, versao=7, a_conferir={1})
    inteiro = dict(base.por_id)
    for wid, r in mud.items():
        if r is None:
            inteiro.pop(wid)
        else:
            inteiro[wid] = r
    b = OC._indexar(inteiro, lido_em=1.0, janela=base.janela, versao=7, a_conferir={1})
    assert dict(a.por_id) == dict(b.por_id) and a.ordem == b.ordem
    assert dict(a.por_folio) == dict(b.por_folio) and dict(a.por_codigo_ativo) == dict(b.por_codigo_ativo)
    assert all(set(b.nomes_criadores[n]) <= set(a.nomes_criadores[n]) for n in b.nomes_criadores)
    # e a ação usa este caminho: a OS mudada entra na posição certa da ordem e do índice do ativo
    r = base.ordem[50]
    OC.atualizar_os(r.id, r.com(data=_iso(0.01)[:19]))
    assert OC.atual().ordem[0].id == r.id and OC.atual().por_codigo_ativo[r.code][0].id == r.id


def test_a_leitura_nao_desfaz_o_que_mudou_durante_ela():
    """A noite inteira leva minutos (~500 páginas a 1 por segundo), e a ação do OS Creator e a entrega das abertas (outra
    thread) não esperam por ela. O que mudou DEPOIS que a leitura começou não é julgado por ela: a OS criada no meio não sai
    (seria a "OS criada pelo OS Creator sumindo até a próxima volta"), nem fica "a conferir", e o status que a ação acabou de
    gravar não volta ao velho que a leitura tinha lido."""
    _carga_inicial()
    inicio = time.time() - 300                                       # a leitura começou há 5 min
    # durante a leitura: a ação muda a OS 1 e cria a 50; as abertas trazem a 60, criada há 1 min
    assert OC.atualizar_os(1, [_tarefa(1, 1, status=2, criada=_iso(2))])
    assert OC.atualizar_os(50, [_tarefa(50, 50, status=1, criada=_iso(0.001))])
    OC.receber([_tarefa(60, 60, status=1, criada=_iso(0.0007))], OC.ABERTAS, lido_em=inicio)   # a volta das abertas também
    # a noite termina com o que ela leu (a 1 ainda com o status velho; a 50 e a 60 ela não viu)
    OC.receber([_tarefa(1, 1, status=1, criada=_iso(2)), _tarefa(2, 2, status=2, criada=_iso(60)),
                _tarefa(3, 3, status=3, criada=_iso(3), fim=_iso(1))], OC.NOITE, desde=_iso(90)[:10], lido_em=inicio)
    lista = OC.atual()
    assert lista.por_id[1].status_id == 2                            # o que a ação gravou fica
    assert {50, 60} <= set(lista.por_id) and not ({50, 60} & lista.a_conferir)
    assert 4 not in lista.por_id                                     # a que sumiu antes da leitura sai, como sempre
    # e as abertas lidas antes da ação não marcam a OS que a ação abriu no meio
    OC.receber([_tarefa(2, 2, status=2, criada=_iso(60))], OC.ABERTAS, lido_em=inicio)
    assert 1 not in OC.atual().a_conferir and 50 not in OC.atual().a_conferir


# ── rodada 1 da revisão: a trava de encolhimento (Ruling AU) ────────────────────────────────────────────────────────────
def test_a_trava_de_encolhimento(caplog):
    """A noite e os 7 dias que tirariam (ou marcariam "a conferir") mais que `ENCOLHE_MAX`% do que cobrem, e mais que
    `ENCOLHE_MIN_OS`, não trocam nada: o motivo vai ao estado e ao log. A 1ª carga (a lista vazia) não tem o que encolher, e
    a leitura dentro do limite passa e tira a recusa da faixa do estado."""
    linhas = [_tarefa(100 + k, 100 + k, criada=_iso(0.1 + 80 * k / 200)) for k in range(200)]   # 200 OS em 80 dias
    rel = OC.receber(linhas, OC.NOITE, desde=_iso(90)[:10])
    assert rel["entraram"] == 200 and not rel.get("recusa")
    antes = OC.atual()
    # a noite que tiraria 100 das 200: nada muda
    with caplog.at_level(logging.WARNING, logger="oscreator.os_central"):
        rel = OC.receber(linhas[:100], OC.NOITE, desde=_iso(90)[:10])
    assert "encolheria" in rel["recusa"] and "100 das 200" in rel["recusa"] and rel["sairam"] == 0
    lista = OC.atual()
    assert (lista.versao, lista.janela, set(lista.por_id)) == (antes.versao, antes.janela, set(antes.por_id))
    assert OC.estado()["recusas"]["noite"]["motivo"] == rel["recusa"]
    assert any("encolheria" in r.getMessage() for r in caplog.records)
    # dentro do limite (10 OS, ou 5% do que a faixa cobre): passa, e a recusa da noite sai do estado
    rel = OC.receber(linhas[:190], OC.NOITE, desde=_iso(90)[:10])
    assert not rel.get("recusa") and rel["sairam"] == 10 and "noite" not in OC.estado()["recusas"]
    # os 7 dias cobrem 18 OS; os que marcariam 13 "a conferir" (mais que 10) são recusados, os que marcariam 8 passam
    nos_7 = [w for w in linhas[:190] if w["creation_date"] >= _iso(7)]
    assert len(nos_7) == 18
    versao = OC.atual().versao
    rel = OC.receber(nos_7[:5], OC.SETE_DIAS, desde=_iso(7)[:19])
    assert "encolheriam" in rel["recusa"] and OC.atual().versao == versao and OC.atual().a_conferir == frozenset()
    assert OC.estado()["recusas"]["sete_dias"]["motivo"] == rel["recusa"]
    rel = OC.receber(nos_7[:10], OC.SETE_DIAS, desde=_iso(7)[:19])
    assert not rel.get("recusa") and rel["a_conferir"] == 8 and OC.estado()["recusas"] == {}


# ── rodada 1 da revisão: a memória no Raio-X (Minor 3) ──────────────────────────────────────────────────────────────────
def test_a_memoria_medida_uma_vez_por_versao(monkeypatch, caplog):
    """A medida percorre a lista inteira (~0,4 s com 36 mil OS): uma vez por versão, e a que falha vai ao log com a pilha."""
    _carga_inicial()
    chamadas = []
    real = OC.memoria_estimada
    monkeypatch.setattr(OC, "memoria_estimada", lambda lista=None: chamadas.append(1) or real(lista))
    a = OC.estado(medir_memoria=True)["memoria_mb"]
    b = OC.estado(medir_memoria=True)["memoria_mb"]
    assert a is not None and a == b and len(chamadas) == 1
    OC.receber([_tarefa(5, 5, criada=_iso(0.01))], OC.NOVAS)                       # a versão mudou: mede de novo
    OC.estado(medir_memoria=True)
    assert len(chamadas) == 2
    monkeypatch.setattr(OC, "memoria_estimada", lambda lista=None: 1 / 0)
    OC.receber([_tarefa(6, 6, criada=_iso(0.01))], OC.NOVAS)
    with caplog.at_level(logging.WARNING, logger="oscreator.os_central"):
        e = OC.estado(medir_memoria=True)
    assert e["memoria_mb"] is None and any("memória" in r.getMessage() and r.exc_info for r in caplog.records)


# ── rodada 1 da revisão: a linha enxuta (Ruling AV) ─────────────────────────────────────────────────────────────────────
def test_a_linha_enxuta_monta_o_mesmo_registro():
    """A projeção por página (`os_registro.enxuta`) guarda só o que o registro lê: o registro montado da linha cortada é o
    MESMO da linha inteira. A nota só leva o texto com o bloco do chamado (a da outra tarefa, sem o bloco, fica de fora nos
    dois caminhos), e a etiqueta só o id e o nome."""
    marca = "Antes\n" + acomp_web.MARCA_NOTA + "\nMarca: Inventada"
    linhas = [
        _tarefa(700, 1, nota=marca, labels=((11, "CHAMADOS"), (12, "ROTINA"))),
        _tarefa(700, 2, nota="uma nota de outra tarefa, sem o bloco"),
        _tarefa(701, 3, status=3, fim=_iso(1), nota="só uma nota qualquer"),
        dict(_tarefa(702, 4), note=api._CHAMADO_MK + "\nStatus: Aberto", trigger_description="NO_SCHEDULE_TASK",
             labels=[{"id": 13, "name": "OUTRA"}, "não é etiqueta"]),
        dict(_tarefa(703, 5), labels="nem lista", task_note=None, note="None"),
        {k: v for k, v in _tarefa(704, 6).items() if k not in ("labels", "task_note", "created_by")},
    ]
    enxutas = [OR.enxuta(w) for w in linhas]
    assert all(set(w) <= set(OR.CAMPOS_REST) for w in enxutas)
    assert "groups_1_description" not in enxutas[0] and "rating" not in enxutas[0] and "task_note" not in enxutas[1]
    assert enxutas[0]["labels"] == [{"id": 11, "description": "CHAMADOS"}, {"id": 12, "description": "ROTINA"}]
    inteiro, cortado = OR.registros_do_rest(linhas), OR.registros_do_rest(enxutas)
    assert inteiro == cortado and set(inteiro) == {700, 701, 702, 703, 704}
    assert acomp_web.MARCA_NOTA in inteiro[700].note and "outra tarefa" not in inteiro[700].note
    assert inteiro[701].note == "" and api._CHAMADO_MK in inteiro[702].note and inteiro[703].note == ""


def test_a_troca_no_disco_tenta_de_novo_o_arquivo_preso(tmp_path, monkeypatch):
    """No Windows (o PC), o antivírus ou o indexador seguram por um instante o arquivo recém-escrito, e o `os.replace` seguinte
    falha com acesso negado (rodada 1 da revisão: 2 de 8 rodadas do teste das pendentes mortas, com uma gravação colada na
    outra, e a pendente que saiu da fila voltava no reinício). A troca tenta de novo antes de desistir; a que segue presa
    levanta, o rascunho sai, e a cópia de antes fica."""
    import canto_disco
    destino = str(tmp_path / "copia.json")
    presas = [PermissionError(13, "Acesso negado"), PermissionError(13, "Acesso negado")]
    real = canto_disco._replace

    def replace(a, b):
        if presas:
            raise presas.pop(0)
        return real(a, b)
    monkeypatch.setattr(canto_disco, "_replace", replace)
    monkeypatch.setattr(canto_disco, "ESPERAS_DA_TROCA", (0, 0, 0))
    canto_disco.trocar_de_uma_vez(destino, lambda tmp: open(tmp, "w", encoding="utf-8").write("nova"))
    assert open(destino, encoding="utf-8").read() == "nova" and presas == []

    def sempre_presa(a, b):
        raise PermissionError(13, "Acesso negado")
    monkeypatch.setattr(canto_disco, "_replace", sempre_presa)
    with pytest.raises(PermissionError):
        canto_disco.trocar_de_uma_vez(destino, lambda tmp: open(tmp, "w", encoding="utf-8").write("outra"))
    assert open(destino, encoding="utf-8").read() == "nova"
    assert not [n for n in os.listdir(tmp_path) if n.endswith(".tmp")]


def test_esperar_a_gravacao_espera_as_duas(tmp_path, monkeypatch):
    """Uma gravação lenta (a troca do Windows tentando de novo) e outra agendada durante ela: `esperar_gravacao` espera as
    DUAS, e o reinício lê a versão de agora (rodada 1 da revisão: com uma bandeira só, a 1ª ao terminar dizia "nenhuma
    escrevendo" com a 2ª ainda na fila, e o teste das pendentes mortas lia a cópia velha)."""
    import threading
    monkeypatch.setattr(OD, "GRAVAR_A_CADA_S", 0)
    OC.reiniciar(pasta=str(tmp_path))
    _carga_inicial()
    assert OC.esperar_gravacao(5)
    dentro, solta, vezes = threading.Event(), threading.Event(), []
    real = OD._trocar_de_uma_vez

    def lenta(destino, escrever):
        vezes.append(1)
        if len(vezes) == 1:
            dentro.set()
            solta.wait(5)                                            # a 1ª, presa na troca
        else:
            time.sleep(0.3)                                          # a 2ª, também lenta
        return real(destino, escrever)
    monkeypatch.setattr(OD, "_trocar_de_uma_vez", lenta)
    OC.receber([_tarefa(5, 5, criada=_iso(0.01))], OC.NOVAS)
    assert dentro.wait(5)
    OC.receber([_tarefa(6, 6, criada=_iso(0.01))], OC.NOVAS)       # agendada com a 1ª escrevendo
    versao = OC.atual().versao
    solta.set()
    assert OC.esperar_gravacao(5)
    OC.reiniciar(pasta=str(tmp_path))
    assert OC.atual().versao == versao and {5, 6} <= set(OC.atual().por_id)


# ── rodada 2 da revisão: o apagamento confirmado ────────────────────────────────────────────────────────────────────────
def test_o_apagamento_confirmado_na_2a_leitura_passa():
    """A saída da trava de encolhimento, como a dupla confirmação dos ativos: a recusa que se repete IGUAL na leitura seguinte
    da mesma faixa (os mesmos ids saindo, ou ao menos 90% deles) é o apagamento de verdade e passa, e o estado diz "aceita na
    2ª leitura". A 2ª diferente é recusada de novo e vira a recusa que a 3ª confere. Sem isso, o apagamento de verdade acima
    de 5% seria recusado toda noite, para sempre."""
    linhas = [_tarefa(100 + k, 100 + k, criada=_iso(0.1 + 80 * k / 200)) for k in range(200)]   # 200 OS em 80 dias
    OC.receber(linhas, OC.NOITE, desde=_iso(90)[:10])
    # 1ª: saem as 100 mais velhas, recusada
    rel = OC.receber(linhas[:100], OC.NOITE, desde=_iso(90)[:10])
    assert rel["recusa"] and len(OC.atual().por_id) == 200
    # 2ª diferente (saem as 100 mais novas): recusada de novo
    rel = OC.receber(linhas[100:], OC.NOITE, desde=_iso(90)[:10])
    assert rel["recusa"] and len(OC.atual().por_id) == 200 and not OC.estado()["confirmadas"]
    # 3ª: 95 das mesmas 100 da 2ª saem (5 voltaram): 95% dos ids, aceita
    rel = OC.receber(linhas[100:] + linhas[:5], OC.NOITE, desde=_iso(90)[:10])
    assert not rel.get("recusa") and rel["sairam"] == 95 and "2ª leitura" in rel["confirmada"]
    e = OC.estado()
    assert len(OC.atual().por_id) == 105 and "noite" not in e["recusas"]
    assert "aceita na 2ª leitura" in e["confirmadas"]["noite"]["motivo"] and e["confirmadas"]["noite"]["sairam"] == 95
    assert "_ids" not in e["confirmadas"]["noite"]                                 # só contagens no estado
    # os 7 dias: a mesma leitura recusada duas vezes seguidas passa na 2ª
    OC.reiniciar()
    OC.receber(linhas, OC.NOITE, desde=_iso(90)[:10])
    nos_7 = [w for w in linhas if w["creation_date"] >= _iso(7)]
    assert OC.receber(nos_7[:5], OC.SETE_DIAS, desde=_iso(7)[:19])["recusa"]
    assert "_ids" not in OC.estado()["recusas"]["sete_dias"]
    rel = OC.receber(nos_7[:5], OC.SETE_DIAS, desde=_iso(7)[:19])
    assert not rel.get("recusa") and rel["a_conferir"] == len(nos_7) - 5 and "2ª leitura" in rel["confirmada"]
    assert len(OC.atual().a_conferir) == len(nos_7) - 5


def test_a_recusa_sobrevive_ao_reinicio(tmp_path, monkeypatch):
    """O servidor reinicia a cada push na main (~10 vezes por dia útil) e a noite roda uma vez por dia: a recusa só na memória
    sumiria entre duas noites, e o apagamento de verdade seria recusado em toda noite de dia útil. Ela vai à cópia em disco
    (com os ids, que só a lista lê), a 2ª leitura igual depois do reinício passa, e a confirmação também fica para o Raio-X."""
    monkeypatch.setattr(OD, "GRAVAR_A_CADA_S", 0)
    OC.reiniciar(pasta=str(tmp_path))
    linhas = [_tarefa(100 + k, 100 + k, criada=_iso(0.1 + 80 * k / 200)) for k in range(200)]
    OC.receber(linhas, OC.NOITE, desde=_iso(90)[:10])
    assert OC.receber(linhas[:100], OC.NOITE, desde=_iso(90)[:10])["recusa"]
    assert OC.esperar_gravacao(5)
    OC.reiniciar(pasta=str(tmp_path))                                             # o deploy entre as duas noites
    rec = OC.estado()["recusas"]["noite"]
    assert rec["sairiam"] == 100 and "_ids" not in rec
    rel = OC.receber(linhas[:100], OC.NOITE, desde=_iso(90)[:10])
    assert not rel.get("recusa") and "2ª leitura" in rel["confirmada"] and len(OC.atual().por_id) == 100
    assert OC.esperar_gravacao(5)
    OC.reiniciar(pasta=str(tmp_path))
    e = OC.estado()
    assert "aceita na 2ª leitura" in e["confirmadas"]["noite"]["motivo"] and e["recusas"] == {}

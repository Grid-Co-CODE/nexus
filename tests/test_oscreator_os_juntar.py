"""O caminho único que junta as tarefas numa OS numerada (31/10/2026, etapa 5, tarefa 5.1 do canto central).

O caso que criou a regra: em 30/10/2026 o tempo da OS (10 min fixos no `_work_order_insert`) estava errado em QUATRO caminhos
de criação, porque cada um tinha a sua cópia da "fase 2" (ler o kanban, inserir a OS, pôr as etiquetas, anexar). O PCM:
"agora criando do zero o tempo na OS continua 10 min igual na Fila, só na tarefa que o tempo é o que a gente colocou". A
conta ficou certa em cada caminho, mas as cópias seguiam ali. Agora a fase 2 é uma só (`os_juntar.juntar_em_os`), e quem cria
(a Clonagem de planos, a Clonagem de OS, a Fila do PCM, o Criar OS do zero, a Performance, o COS, a Engenharia) só cria as
tarefas e a entrega.

O que estes testes seguram (o Fracttal é de mentira no nível do HTTP: cada pedido ao rpc/proxy fica guardado, na ordem; nada
vai à rede; nomes, ativos e ids são inventados):
- `test_payload_igual_ao_de_antes`: o que cada caminho manda ao Fracttal (o pedido que cria cada tarefa, a leitura do kanban,
  a OS, as etiquetas, as fotos) e o que ele devolve a quem o chamou, gravados ANTES da troca (no d18ce7b, o código de antes da
  5.1) em `oscreator_payloads_antes_da_5_1.json`. A troca não pode mudar nenhum;
- `test_todos_os_caminhos_passam_pelo_juntar`: cada um dos oito caminhos chama o `juntar_em_os`, e o pedido que insere a OS só
  sai de dentro dele;
- `test_tempo_e_a_soma_em_todos`: o tempo da OS é a soma do tempo das tarefas que entraram nela, em todos;
- `test_avisos_de_hoje`: o que cada tela diz quando o kanban cai, a tarefa não é achada, a etiqueta falha ou a OS não fecha;
- e o resto do contrato: o kanban lido uma vez para as N OS de "uma OS por ativo", a foto na tarefa do ativo dela mesmo quando
  uma tarefa não entrou na OS, a criação da Engenharia que confere a pessoa e a etiqueta ao vivo ANTES de gravar, e a lista
  central de OS que o caminho único não toca (quem a atualiza são as telas, `lista_central.criadas`).

Para regravar o arquivo (só quando uma mudança de pedido for de propósito): `PYTHONPATH=. python
tests/test_oscreator_os_juntar.py --regravar`."""
import copy
import hashlib
import itertools
import json
import os
import re
import sys
import time
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from _pytest.monkeypatch import MonkeyPatch

from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone

OURO = Path(__file__).with_name("oscreator_payloads_antes_da_5_1.json")
BRT = timezone(timedelta(hours=-3))
EVENTO = datetime(2026, 11, 3, 9, 0, tzinfo=BRT)
PROGRAMADA = datetime(2026, 11, 4, 8, 30, tzinfo=BRT)
AGORA = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
PNG = {"bytes": b"\x89PNG-de-mentira", "nome": "foto.png"}
KANBAN, INSERIR_TAREFA, INSERIR_OS, ETIQUETAS = (api.RPC_KANBAN, api.RPC_METHOD, api.RPC_WO_INSERT, api.RPC_LABELS_SYNC)


# ── o Fracttal de mentira ──────────────────────────────────────────────────────────────────────────────────────────────
class _Resp:
    def __init__(self, corpo, status=200):
        self._corpo, self.status_code, self.text = corpo, status, "erro de mentira" if status >= 400 else ""

    def json(self):
        return self._corpo


class FracttalFalso:
    """O rpc/proxy: responde como o Fracttal e guarda tudo o que recebe, na ordem (`eventos`), junto das leituras e dos anexos
    que o teste troca. `falhar` = os métodos que dão HTTP 500; `kanban_vazio` = a lista de pendentes que não traz as tarefas
    recém-criadas; `falta_a_primeira` = a que não traz a primeira; `falha_tarefa` = a N-ésima tarefa a criar dá HTTP 500."""

    def __init__(self, falhar=(), kanban_vazio=False, falta_a_primeira=False, falha_tarefa=0):
        self.eventos, self.pendentes = [], []
        self.n_tarefa = self.n_os = self.n_pedidos_de_tarefa = 0
        self.falhar, self.kanban_vazio, self.falta_a_primeira = set(falhar), kanban_vazio, falta_a_primeira
        self.falha_tarefa = falha_tarefa

    def post(self, url, headers=None, json=None, timeout=None, **_kw):
        corpo = json[0]
        metodo, params = corpo["method"], copy.deepcopy(corpo["params"])
        self.eventos.append({"pedido": metodo, "params": params})
        if metodo in self.falhar:
            return _Resp({}, 500)
        if metodo == INSERIR_TAREFA:
            self.n_pedidos_de_tarefa += 1
            if self.n_pedidos_de_tarefa == self.falha_tarefa:
                return _Resp({}, 500)
            self.n_tarefa += 1
            idt = 1000 + self.n_tarefa
            if params.get("to_work_order"):                      # a OS já realizada nasce numerada, sem a fase 2
                self.n_os += 1
                return _Resp([{"result": {"success": True, "data": {
                    "id_task": idt, "id_work_order": 7000 + self.n_os, "wo_folio": 9000 + self.n_os}}}])
            self.pendentes.append({"id_task": idt, "id_item": params.get("id_item"), "description": params.get("description"),
                                   "duration": params.get("duration"), "id_request": params.get("id_request")})
            return _Resp([{"result": {"success": True, "data": {"id_task": idt}}}])
        if metodo == KANBAN:
            lista = [] if self.kanban_vazio else copy.deepcopy(self.pendentes)
            if self.falta_a_primeira and lista:
                lista = lista[1:]
            return _Resp([{"result": {"data": lista}}])
        if metodo == INSERIR_OS:
            self.n_os += 1
            return _Resp([{"result": {"data": {"id": 7000 + self.n_os, "wo_folio": 9000 + self.n_os}}}])
        if metodo == api.RPC_WO_PARENTS:
            return _Resp([{"result": {"data": [{"id": 4321, "wo_folio": "1234", "description": "1234"}]}}])
        if metodo == api.RPC_WO_TASKS_NEW:
            return _Resp([{"result": {"data": [{"id": 5001, "id_item": 1}, {"id": 5002, "id_item": 2}]}}])
        return _Resp([{"result": {"success": True, "data": []}}])

    def da_os(self):
        """Os pedidos que inseriram uma OS (o resumo de cada um)."""
        return [e for e in self.eventos if e.get("pedido") == INSERIR_OS]


def ativo(n, **k):
    return dict({"id": n, "code": "TST-INV%d" % n, "description": "Inversor 1.%d { TST-INV%d }" % (n, n),
                 "id_type_item": 1, "id_parent": 90, "id_group_task": 7}, **k)


PLANO = {"id_task": 9, "description": "[Grid Co.] - Limpeza", "tasks_types_main_description": "Preventiva",
         "id_task_type_main": 43886, "tasks_types_description": "Programada", "id_task_type": 5, "id_task_type_2": 6,
         "tasks_types_2_description": "Elétrica", "duration": 3600, "id_priorities": 3,
         "subtasks": [{"description": "Conferir o painel"}], "raw": {}}


def _modulos_do_clone():
    """Os módulos do OS Creator (o `api` e os que dele saíram): o que muda de uma rodada para outra se troca em cada um, e o
    teste vale onde o código estiver."""
    raiz = os.path.normcase(os.path.abspath(ponte.RAIZ_CLONE))
    for m in list(sys.modules.values()):
        arquivo = getattr(m, "__file__", None)
        if arquivo and os.path.normcase(os.path.abspath(arquivo)).startswith(raiz):
            yield m


def _preparar(mp, fr):
    """Tudo o que muda de uma rodada para outra fica fixo: os ids, a hora, a espera e as leituras dos catálogos."""
    contador = itertools.count(1)
    falso_uuid = types.SimpleNamespace(uuid4=lambda: "u%03d" % next(contador))

    class Congelado(datetime):
        @classmethod
        def now(cls, tz=None):
            return AGORA if tz is None else AGORA.astimezone(tz)
    import uuid as uuid_real
    for m in _modulos_do_clone():
        if getattr(m, "uuid", None) is uuid_real:
            mp.setattr(m, "uuid", falso_uuid)
        if getattr(m, "datetime", None) is datetime:
            mp.setattr(m, "datetime", Congelado)
    mp.setattr(api.requests, "post", fr.post)
    mp.setattr(api, "_rpc_headers", lambda: {})
    mp.setattr(time, "sleep", lambda s: None)
    mp.setattr(api, "_classif_ids", lambda *a: {})
    mp.setattr(api, "get_plan_details", lambda idt, idi: copy.deepcopy(PLANO))
    mp.setattr(api, "_label_performance_id", lambda: 31)
    mp.setattr(api, "label_id_por_nome", lambda n: {"ENGENHARIA": 32}.get(n))
    mp.setattr(api, "nascer_ticket", lambda *a, **k: {})

    def tarefas_da_os(wid):
        fr.eventos.append({"tarefas_da_os": wid})
        return [5001, 5002] if wid else []
    mp.setattr(api, "_ids_tarefas_da_os", tarefas_da_os)

    def anexar(wid, tid, dados, nome):
        fr.eventos.append({"anexo": {"os": wid, "tarefa": tid, "nome": nome, "bytes": len(dados)}})
        return {"ok": True}
    mp.setattr(api, "attach_imagem_os", anexar)


# Os dois pedidos que mais se repetem (a tarefa que nasce, com ~60 campos, e a OS que a junta, com o registro de cada tarefa
# duas vezes) vão ao arquivo só com o resumo que se lê (o ativo, o tempo, a janela, a OS pai, a nota, as tarefas) e o SHA-1 do
# corpo inteiro, que prende o resto. As leituras e as etiquetas vão por inteiro.
_RESUMO_DA_TAREFA = ("id_item", "description", "duration", "initial_date", "final_date", "event_date", "id_parent", "id_request",
                     "note", "to_work_order", "work_done", "id_assigned_user", "id_task", "id_priorities", "name")
_RESUMO_DA_OS = ("duration", "id_responsible", "name", "id_parent", "note")


def _resumir(evento):
    metodo = evento.get("pedido")
    if metodo not in (INSERIR_TAREFA, INSERIR_OS):
        return evento
    p = evento["params"]
    corpo = json.dumps(p, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    if metodo == INSERIR_TAREFA:
        resumo = {k: p.get(k) for k in _RESUMO_DA_TAREFA if k in p}
    else:
        resumo = {k: p.get(k) for k in _RESUMO_DA_OS if k in p}
        resumo["tarefas"] = [t.get("id_task") for t in p.get("array_tasks_todo", [])]
    return {"pedido": metodo, "resumo": resumo, "sha1": hashlib.sha1(corpo).hexdigest()}


def _json(x):
    return json.loads(json.dumps(x, sort_keys=True, default=str))


def _rodar(corpo, preparo=None, **opcoes):
    """Roda um caminho de criação contra o Fracttal de mentira → {retorno, eventos (resumidos)}. `preparo(mp, fr)` troca mais
    alguma coisa antes (o espião do teste)."""
    fr = FracttalFalso(**opcoes)
    with MonkeyPatch.context() as mp:
        _preparar(mp, fr)
        if preparo:
            preparo(mp, fr)
        retorno = corpo(mp, fr)
    return _json({"retorno": retorno, "eventos": [_resumir(e) for e in fr.eventos]}), fr


# ── os caminhos de criação (cada um como a tela o chama) ───────────────────────────────────────────────────────────────
def _multi(mp, fr):
    """A Clonagem de planos do PCM: um plano por linha, cada uma com o seu tempo."""
    return api.create_planned_os_multi(
        [{"asset": ativo(1), "id_task": 9, "duracao": 5400, "event_date": EVENTO}, {"asset": ativo(2), "id_task": 9}],
        77, "Ana Teste", event_date=PROGRAMADA, id_parent=555)


def _um_wo(mp, fr):
    return api.create_planned_os_one_wo([ativo(1), ativo(2)], copy.deepcopy(PLANO), 77, "Ana Teste", event_date=EVENTO)


def _agrupada(mp, fr, **mais):
    """O Criar OS do zero e a Engenharia, "Agrupar em UMA OS"."""
    args = dict(etiqueta="x", responsible_name="Ana Teste", id_responsible=77, etiqueta_ids=[11, 12], note="obs",
                tipo={"id_main": 43885, "id_priorities": 3}, event_date=EVENTO, id_parent=555, prog_date=PROGRAMADA,
                imagens_por_ativo={"TST-INV1": [PNG], "TST-INV2": [PNG, dict(PNG, nome="outra.png")]},
                por_ativo={"TST-INV2": {"description": "[Inversor 1.2] - X", "note": "n2"}})
    args.update(mais)
    return api.create_work_orders_agrupada([ativo(1), ativo(2)], "Descrição", "Corretiva", ["Conferir"], **args)


def _perf_itens():
    return [{"asset": ativo(1), "plano_id_task": 9, "plano_id_item": 1, "note": "n1", "titulo": "T1", "os_pai": "1234",
             "imagens": [PNG], "gerar_ticket": False},
            {"asset": ativo(2), "plano_id_task": 9, "plano_id_item": 2, "note": "n2", "gerar_ticket": False}]


def _perf(mp, fr):
    return api.create_performance_os_agrupada(_perf_itens(), id_responsible=77, responsible_name="Ana Teste",
                                              event_date=EVENTO, prog_date=PROGRAMADA, etiquetas_extra=["ENGENHARIA"],
                                              note_os="obs da OS")


def _tarefas_clone():
    return [{"asset": ativo(1), "tipo": "Corretiva", "descricao": "A", "subtarefas": ["s1"], "duracao": 5400,
             "event_date": EVENTO, "classif_1": "", "classif_2": ""},
            {"asset": ativo(2), "tipo": "Corretiva", "descricao": "B", "subtarefas": ["s2"], "notas": "nota"}]


def _clonar(mp, fr, **mais):
    args = dict(etiqueta_ids=[11], note="obs", scheduled_date=PROGRAMADA, id_parent=555)
    args.update(mais)
    return api.clonar_os(_tarefas_clone(), 77, "Ana Teste", **args)


def _aprovar_retomada(mp, fr, id_responsavel=77, **mais):
    """A Fila do PCM aprovando a solicitação cuja tarefa ficou de uma tentativa que parou no meio."""
    mp.setattr(api, "_solicitacao_row", lambda idc: {})
    mp.setattr(api, "_tarefa_da_solicitacao", lambda idc: {"id_task": 4001, "id_item": 1, "duration": 3600})
    args = dict(etiqueta_ids=[11], duracao=5400)
    args.update(mais)
    return api.aprovar_solicitacao(ativo(1), "T", ["s"], 5001, id_responsavel, "Ana Teste", **args)


def _aprovar_nova(mp, fr):
    mp.setattr(api, "_solicitacao_row", lambda idc: {})
    mp.setattr(api, "_tarefa_da_solicitacao", lambda idc: None)
    return api.aprovar_solicitacao(ativo(1), "T", ["s"], 5001, 77, "Ana Teste", etiqueta_ids=[11], prog_date=PROGRAMADA,
                                   duracao=5400, classif=("", ""))


def _sem_plano(mp, fr):
    return api.create_os_sem_plano([{"asset": ativo(1), "event_date": EVENTO}, {"asset": ativo(2)}], 77, "Ana Teste",
                                   descricao="Procedimento X", note="obs", id_parent=555)


def _bulk(mp, fr, **mais):
    """O Criar OS do zero (uma OS por ativo), o COS e a Engenharia."""
    args = dict(responsible_name="Ana Teste", id_responsible=77, etiqueta_ids=[11], note="obs", event_date=EVENTO,
                id_parent=555, imagens_por_ativo={"TST-INV1": [PNG, dict(PNG, nome="b.png")]}, prog_date=PROGRAMADA,
                por_ativo={"TST-INV2": {"description": "[Inversor 1.2] - X", "note": "n2"}})
    args.update(mais)
    return api.create_work_orders_bulk([ativo(1), ativo(2)], "Descrição", "Corretiva", ["Conferir"], **args)


def _bulk_realizada(mp, fr):
    fin = {"to_in_review": False, "final_date": PROGRAMADA, "id_assigned_user": 77, "name": "Ana Teste"}
    return api.create_work_orders_bulk([ativo(1)], "Descrição", "Corretiva", ["Conferir"], id_responsible=77,
                                       etiqueta_ids=[11], finalizar=fin, event_date=EVENTO,
                                       imagens_por_ativo={"TST-INV1": [PNG]})


def _datas(mp, fr, **mais):
    """O COS, "Mesmo ativo · várias datas"."""
    args = dict(responsible_name="Ana Teste", id_responsible=77, etiqueta_ids=[11], note="obs", id_parent=555)
    args.update(mais)
    return api.create_work_orders_datas(ativo(1), "Descrição", "Corretiva", ["Conferir"], [EVENTO, PROGRAMADA], **args)


KANBAN_FORA = {"falhar": [KANBAN]}
CENARIOS = {
    "planos_do_pcm_numa_os": (_multi, {}),
    "planos_do_pcm_kanban_fora": (_multi, KANBAN_FORA),
    "planos_do_pcm_tarefas_nao_achadas": (_multi, {"kanban_vazio": True}),
    "planos_do_pcm_uma_tarefa_nao_nasceu": (_multi, {"falha_tarefa": 2}),
    "um_plano_varios_ativos": (_um_wo, {}),
    "agrupada": (_agrupada, {}),
    "agrupada_sem_responsavel": (lambda mp, fr: _agrupada(mp, fr, id_responsible=None), {}),
    "agrupada_kanban_fora": (_agrupada, KANBAN_FORA),
    "agrupada_a_os_nao_fechou": (_agrupada, {"falhar": [INSERIR_OS]}),
    "agrupada_etiqueta_falhou": (_agrupada, {"falhar": [ETIQUETAS]}),
    "agrupada_falta_uma_tarefa": (lambda mp, fr: _agrupada(mp, fr, imagens_por_ativo=None), {"falta_a_primeira": True}),
    "agrupada_uma_tarefa_nao_nasceu": (_agrupada, {"falha_tarefa": 1}),
    "performance_agrupada": (_perf, {}),
    "performance_agrupada_kanban_fora": (_perf, KANBAN_FORA),
    "performance_agrupada_tarefas_nao_achadas": (_perf, {"kanban_vazio": True}),
    "performance_agrupada_falta_uma_tarefa": (_perf, {"falta_a_primeira": True}),
    "performance_agrupada_etiqueta_falhou": (_perf, {"falhar": [ETIQUETAS]}),
    "clonar": (_clonar, {}),
    "clonar_sem_responsavel": (lambda mp, fr: api.clonar_os(_tarefas_clone(), None, "Ana Teste", etiqueta_ids=[11]), {}),
    "clonar_kanban_fora": (_clonar, KANBAN_FORA),
    "clonar_tarefas_nao_achadas": (_clonar, {"kanban_vazio": True}),
    "clonar_etiqueta_falhou": (_clonar, {"falhar": [ETIQUETAS]}),
    "clonar_sem_etiqueta": (lambda mp, fr: _clonar(mp, fr, etiqueta_ids=None), {}),
    "clonar_uma_tarefa_nao_nasceu": (_clonar, {"falha_tarefa": 2}),
    "fila_do_pcm_retomada": (_aprovar_retomada, {}),
    "fila_do_pcm_retomada_etiqueta_falhou": (_aprovar_retomada, {"falhar": [ETIQUETAS]}),
    "fila_do_pcm_retomada_sem_responsavel": (lambda mp, fr: _aprovar_retomada(mp, fr, id_responsavel=None), {}),
    "fila_do_pcm_retomada_sem_o_tempo_da_tarefa": (lambda mp, fr: _aprovar_retomada(mp, fr, duracao=None), {}),
    "fila_do_pcm_nova": (_aprovar_nova, {}),
    "os_sem_plano": (_sem_plano, {}),
    "uma_os_por_ativo": (_bulk, {}),
    "uma_os_por_ativo_sem_responsavel": (lambda mp, fr: _bulk(mp, fr, id_responsible=None), {}),
    "uma_os_por_ativo_kanban_fora": (_bulk, KANBAN_FORA),
    "uma_os_por_ativo_tarefas_nao_achadas": (_bulk, {"kanban_vazio": True}),
    "uma_os_por_ativo_falta_a_primeira": (_bulk, {"falta_a_primeira": True}),
    "uma_os_por_ativo_a_os_nao_fechou": (_bulk, {"falhar": [INSERIR_OS]}),
    "uma_os_por_ativo_etiqueta_falhou": (_bulk, {"falhar": [ETIQUETAS]}),
    "uma_os_por_ativo_ja_realizada": (_bulk_realizada, {}),
    "uma_os_por_data": (_datas, {}),
    "uma_os_por_data_kanban_fora": (_datas, KANBAN_FORA),
    "uma_os_por_data_etiqueta_falhou": (_datas, {"falhar": [ETIQUETAS]}),
}


def _gravar(ouro: dict) -> str:
    """O JSON com um pedido por linha: dá para ler e comparar no diff."""
    linhas = ["{"]
    for i, (nome, c) in enumerate(sorted(ouro.items())):
        linhas.append(" %s: {" % json.dumps(nome))
        linhas.append('  "retorno": %s,' % json.dumps(c["retorno"], sort_keys=True, ensure_ascii=False))
        linhas.append('  "eventos": [')
        for j, e in enumerate(c["eventos"]):
            linhas.append("   %s%s" % (json.dumps(e, sort_keys=True, ensure_ascii=False), "," if j < len(c["eventos"]) - 1 else ""))
        linhas.append("  ]")
        linhas.append(" }%s" % ("," if i < len(ouro) - 1 else ""))
    linhas.append("}")
    return "\n".join(linhas) + "\n"


def regravar():
    ouro = {nome: _rodar(corpo, **opcoes)[0] for nome, (corpo, opcoes) in CENARIOS.items()}
    OURO.write_text(_gravar(ouro), encoding="utf-8")
    print("gravado: %s (%d cenarios)" % (OURO, len(ouro)))


# ── 1. o que o Fracttal recebe e o que volta a quem chamou: igual ao de antes ──────────────────────────────────────────
@pytest.mark.parametrize("nome", sorted(CENARIOS))
def test_payload_igual_ao_de_antes(nome):
    """Gravado no d18ce7b, ANTES de a fase 2 virar uma só: cada pedido ao Fracttal (o corpo inteiro, preso pelo SHA-1), na
    mesma ordem, e o que a função devolve. É a prova de que a troca só juntou o código: nenhum campo, nenhum pedido a mais ou
    a menos, nenhum aviso com outro texto."""
    ouro = json.loads(OURO.read_text(encoding="utf-8"))
    corpo, opcoes = CENARIOS[nome]
    assert _rodar(corpo, **opcoes)[0] == ouro[nome]


def test_o_arquivo_de_antes_tem_todos_os_cenarios():
    assert sorted(json.loads(OURO.read_text(encoding="utf-8"))) == sorted(CENARIOS)


# ── 2. os oito caminhos passam pelo juntar ─────────────────────────────────────────────────────────────────────────────
# o cenário → quantas OS ele junta (o "uma OS por ativo" e o "por data" juntam uma tarefa em cada OS, duas OS)
OS_POR_CAMINHO = {"planos_do_pcm_numa_os": 1, "um_plano_varios_ativos": 1, "agrupada": 1, "performance_agrupada": 1,
                  "clonar": 1, "fila_do_pcm_retomada": 1, "fila_do_pcm_nova": 1, "os_sem_plano": 1,
                  "uma_os_por_ativo": 2, "uma_os_por_data": 2}


def test_todos_os_caminhos_passam_pelo_juntar():
    """Criar OS do zero (uma OS por ativo, agrupada e por data), Clonagem de OS, Clonagem de planos e OS sem plano do PCM, a
    Fila do PCM (a nova e a retomada), a Performance, o COS e a Engenharia: todos chegam à OS pelo `juntar_em_os`, e o pedido
    que insere a OS (`_work_order_insert`) só sai de dentro dele."""
    import os_juntar
    for nome, vezes in OS_POR_CAMINHO.items():
        chamadas, dentro = [], [False]
        original = os_juntar.juntar_em_os

        def preparo(mp, fr, chamadas=chamadas, dentro=dentro, original=original):
            def espiao(*a, **k):
                chamadas.append((a, k))
                dentro[0] = True
                try:
                    return original(*a, **k)
                finally:
                    dentro[0] = False
            mp.setattr(os_juntar, "juntar_em_os", espiao)
            real = api._work_order_insert

            def guarda(*a, **k):
                assert dentro[0], "%s: a OS foi inserida fora do juntar_em_os" % nome
                return real(*a, **k)
            mp.setattr(api, "_work_order_insert", guarda)
        corpo, opcoes = CENARIOS[nome]
        _rodar(corpo, preparo, **opcoes)
        assert len(chamadas) == vezes, (nome, len(chamadas))


def test_so_o_juntar_chama_o_insert_da_os():
    """Por fora do que roda: nenhum arquivo do OS Creator, além do `os_juntar.py`, chama o `_work_order_insert` (nem o
    `convert_task_to_wo`, que punha os 600 s fixos e saiu). Quem criar um caminho novo e esquecer cai aqui."""
    chamadas = re.compile(r"(?<!def )\b(_work_order_insert|convert_task_to_wo)\(")
    achados = []
    for arquivo in sorted(Path(ponte.RAIZ_CLONE).rglob("*.py")):
        if arquivo.name == "os_juntar.py":
            continue
        for n, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1):
            if chamadas.search(linha.split("#", 1)[0]):
                achados.append("%s:%d" % (arquivo.relative_to(ponte.RAIZ_CLONE), n))
    assert achados == []


# ── 3. o tempo da OS é a soma do tempo das tarefas que entraram nela ───────────────────────────────────────────────────
def _tempos_das_os(nome, **mais):
    corpo, opcoes = CENARIOS[nome]
    _r, fr = _rodar(corpo, **dict(opcoes, **mais))
    return [e["params"]["duration"] for e in fr.da_os()]


def test_tempo_e_a_soma_em_todos():
    """O PCM (30/10/2026): "nas SSs o tempo que aparece na OS do Fracttal permanece 10 min, porém nas tarefas aparece o tempo
    que foi solicitado" e "agora criando do zero o tempo na OS continua 10 min". A OS leva a soma do tempo das tarefas dela,
    em todos os caminhos; a tarefa sem tempo conta os 10 min com que nasce."""
    padrao = api.DURACAO_OS_AVULSA
    esperado = {
        "planos_do_pcm_numa_os": [5400 + 3600],                    # a linha com o tempo editado + o do plano
        "um_plano_varios_ativos": [2 * 3600],
        "agrupada": [2 * padrao],
        "performance_agrupada": [2 * 3600],                        # o tempo do plano, duas vezes
        "clonar": [5400 + padrao],                                 # a tarefa com tempo + a sem
        "fila_do_pcm_nova": [5400],                                # o "Tempo estimado:" da decisão
        "fila_do_pcm_retomada": [3600],                            # o tempo da tarefa que ficou da tentativa anterior
        "fila_do_pcm_retomada_sem_o_tempo_da_tarefa": [3600],
        "os_sem_plano": [2 * padrao],
        "uma_os_por_ativo": [padrao, padrao],                      # uma tarefa em cada OS
        "uma_os_por_data": [padrao, padrao],
    }
    for nome, tempos in esperado.items():
        assert _tempos_das_os(nome) == tempos, nome


def test_a_os_soma_so_as_tarefas_que_entraram_nela():
    """Se o kanban não traz uma das tarefas criadas, ela não está na OS e o tempo dela não conta. A Clonagem de OS somava as
    tarefas CRIADAS (e as outras, as que entraram): a OS ficava com o tempo de uma tarefa que não tem."""
    padrao = api.DURACAO_OS_AVULSA
    assert _tempos_das_os("clonar", falta_a_primeira=True) == [padrao]                 # a de 1h30 não entrou
    assert _tempos_das_os("planos_do_pcm_numa_os", falta_a_primeira=True) == [3600]
    assert _tempos_das_os("performance_agrupada", falta_a_primeira=True) == [3600]


# ── 4. os avisos que cada tela mostra ──────────────────────────────────────────────────────────────────────────────────
_HTTP_500 = "RPC %s HTTP 500 — erro de mentira"


def _retorno(nome, **mais):
    corpo, opcoes = CENARIOS[nome]
    return _rodar(corpo, **dict(opcoes, **mais))[0]["retorno"]


def test_avisos_de_hoje():
    """Cada tela diz do seu jeito o que ficou faltando quando o kanban cai, a tarefa não é achada, a etiqueta falha ou a OS não
    fecha. As frases são as de antes da troca (não se muda o que as telas mostram), e a OS que não saiu devolve as tarefas
    pendentes, sem número."""
    cai = _HTTP_500 % KANBAN
    # PCM (os planos) e o Criar OS agrupado: "não gerei a OS numerada"
    for nome in ("planos_do_pcm_kanban_fora", "agrupada_kanban_fora"):
        r = _retorno(nome)
        assert r["aviso"] == "tarefas criadas; não gerei a OS numerada (%s)." % cai and r["os"] == {"id_tasks": [1001, 1002]}, nome
    for nome in ("planos_do_pcm_tarefas_nao_achadas", "clonar_tarefas_nao_achadas"):
        assert _retorno(nome)["aviso"] == "tarefas criadas, mas não as achei no kanban p/ gerar a OS.", nome
    assert _retorno("agrupada_sem_responsavel")["aviso"].startswith("tarefas criadas e pendentes no kanban")
    # a Clonagem de OS
    assert _retorno("clonar_kanban_fora")["aviso"] == "tarefas criadas; não consegui gerar a OS numerada (%s)." % cai
    r = _retorno("clonar_etiqueta_falhou")
    assert r["aviso"] == "etiqueta falhou: %s" % (_HTTP_500 % ETIQUETAS) and r["os"]["id_work_order"] == 7001
    r = _retorno("clonar_uma_tarefa_nao_nasceu")
    assert r["aviso"].startswith("1 tarefa(s) não criadas: ") and r["n_criadas"] == 1
    # o Criar OS agrupado: a etiqueta e a OS que não fechou
    r = _retorno("agrupada_etiqueta_falhou")
    assert r["aviso"] == "OS 9001 criada, mas a etiqueta falhou: %s" % (_HTTP_500 % ETIQUETAS) and "etiquetas" not in r["os"]
    r = _retorno("agrupada_a_os_nao_fechou")
    assert r["aviso"] == "tarefas criadas; a OS não fechou (%s)." % (_HTTP_500 % INSERIR_OS) and r["os"] == {"id_tasks": [1001, 1002]}
    # a Performance agrupada: as duas frases próprias, a das tarefas que ficaram de fora e a etiqueta
    r = _retorno("performance_agrupada_kanban_fora")
    assert r["aviso"] == ("as 2 tarefas foram criadas, mas não consegui juntá-las numa OS (%s). "
                          "Elas estão pendentes no kanban do Fracttal." % cai) and r["folio"] is None
    assert _retorno("performance_agrupada_tarefas_nao_achadas")["aviso"] == (
        "as 2 tarefas foram criadas mas não as achei no kanban para gerar a OS numerada.")
    assert _retorno("performance_agrupada_falta_uma_tarefa")["aviso"] == "1 tarefa(s) não entraram na OS"
    assert _retorno("performance_agrupada_etiqueta_falhou")["aviso"] == "etiqueta falhou: %s" % (_HTTP_500 % ETIQUETAS)
    # uma OS por ativo / por data: o aviso fica em cada OS (e sem falha, nenhum)
    for nome in ("uma_os_por_ativo", "uma_os_por_data"):
        assert all("aviso" not in x["os"] for x in _retorno(nome)), nome
    for x in _retorno("uma_os_por_ativo_kanban_fora"):
        assert x["os"]["aviso"] == "tarefa criada; não converti em WO (%s)." % cai
    for x in _retorno("uma_os_por_ativo_tarefas_nao_achadas"):
        assert x["os"]["aviso"] == "tarefa criada, mas não a achei no kanban p/ virar WO."
    assert [("aviso" in x["os"]) for x in _retorno("uma_os_por_ativo_falta_a_primeira")] == [True, False]
    for x in _retorno("uma_os_por_ativo_a_os_nao_fechou"):
        assert x["os"]["aviso"] == "tarefa criada, mas falhou virar WO: %s" % (_HTTP_500 % INSERIR_OS)
    for x in _retorno("uma_os_por_ativo_etiqueta_falhou"):
        assert x["os"]["aviso"].startswith("WO 900") and "criada, mas etiqueta falhou: " in x["os"]["aviso"]
    # a retomada da Fila: a etiqueta que falha não vira aviso (a OS existe, o PCM põe a etiqueta se faltar)
    r = _retorno("fila_do_pcm_retomada_etiqueta_falhou")
    assert r["ok"] and r["aviso"].startswith("a tarefa desta solicitacao ja existia")
    assert _retorno("fila_do_pcm_retomada_sem_responsavel")["erro"].startswith("Escolha o responsavel")


def test_o_juntar_diz_o_que_aconteceu_com_as_frases_do_chamador():
    """O contrato do `juntar_em_os` por si só: as tarefas pendentes sem número quando a OS não sai, o número quando sai, o
    aviso do chamador no lugar do padrão, e a falha da etiqueta que não derruba a OS."""
    import os_juntar
    cenas = {}

    def chamar(mp, fr, **k):
        cenas["fr"] = fr
        for i in (1, 2):
            api.create_os_rpc(ativo(i), "T%d" % i, "Corretiva", [])
        return os_juntar.juntar_em_os([1001, 1002], {1001: 5400, 1002: None}, 77, "Ana Teste", **k)
    r = _rodar(lambda mp, fr: chamar(mp, fr, etiqueta_ids=[11], note="obs"))[0]["retorno"]
    assert r == {"id_tasks": [1001, 1002], "id_work_order": 7001, "wo_folio": 9001, "nao_entraram": 0, "etiquetas": [11]}
    r = _rodar(lambda mp, fr: chamar(mp, fr), falhar=[KANBAN])[0]["retorno"]
    assert r == {"id_tasks": [1001, 1002], "aviso": "tarefas criadas; não gerei a OS numerada (%s)." % (_HTTP_500 % KANBAN)}
    r = _rodar(lambda mp, fr: chamar(mp, fr, frases={"kanban": "sem kanban: {erro} ({n})"}), falhar=[KANBAN])[0]["retorno"]
    assert r["aviso"] == "sem kanban: %s (2)" % (_HTTP_500 % KANBAN)
    r = _rodar(lambda mp, fr: chamar(mp, fr, etiqueta_ids=[11]), falhar=[ETIQUETAS])[0]["retorno"]
    assert r["id_work_order"] == 7001 and "etiquetas" not in r and r["aviso"].startswith("OS 9001 criada, mas a etiqueta falhou")
    with pytest.raises(api.FracttalError, match="work_order_insert"):                 # a OS que não fecha sobe: o chamador decide
        _rodar(lambda mp, fr: chamar(mp, fr), falhar=[INSERIR_OS])


# ── 5. o que o caminho único não faz ───────────────────────────────────────────────────────────────────────────────────
def test_a_uma_os_por_tarefa_le_o_kanban_uma_vez_para_todas():
    """"Uma OS por ativo" e "por data" juntam uma tarefa em cada OS, e o kanban é lido UMA vez para todas (50 OS do COS não
    são 50 leituras): o `juntar_em_os` recebe o registro que já veio lido (`registros`)."""
    for nome in ("uma_os_por_ativo", "uma_os_por_data"):
        eventos = _rodar(*CENARIOS[nome][:1])[1].eventos
        assert [e["pedido"] for e in eventos if e.get("pedido")].count(KANBAN) == 1, nome
    # a retomada da Fila já tem o registro da tarefa: nenhuma leitura do kanban
    assert KANBAN not in [e.get("pedido") for e in _rodar(_aprovar_retomada)[1].eventos]


def test_a_foto_vai_para_a_tarefa_do_ativo_dela_mesmo_se_uma_nao_entrou_na_os():
    """No agrupado, a i-ésima tarefa da OS é a i-ésima que ENTROU nela. A conta de antes usava a ordem das criadas: se o
    kanban não trazia a 1ª, a foto do ativo 1 ia para a tarefa do ativo 2 (a única da OS)."""
    anexos = [e["anexo"] for e in _rodar(lambda mp, fr: _agrupada(mp, fr), falta_a_primeira=True)[1].eventos if "anexo" in e]
    assert [(a["tarefa"], a["nome"]) for a in anexos] == [(5001, "foto.png"), (5001, "outra.png")]      # só as do ativo 2


def test_o_juntar_nao_atualiza_a_lista_central_de_os():
    """Quem põe a OS criada na lista central são as telas (`lista_central.criadas`, com a guarda de "lista em uso" e o limite
    por pedido, da 3.3): chamar o `os_central.atualizar_os` daqui pularia a guarda."""
    import os_central

    def proibido(*a, **k):
        raise AssertionError("o caminho único não atualiza a lista central de OS")
    for nome in ("agrupada", "clonar", "uma_os_por_ativo", "performance_agrupada"):
        corpo, opcoes = CENARIOS[nome]
        _rodar(corpo, lambda mp, fr: mp.setattr(os_central, "atualizar_os", proibido, raising=False), **opcoes)


# a criação da Engenharia pela tela, de ponta a ponta: o caminho único não pode tirar a conferência ao vivo de 19/10/2026
USINA = "Cliente X - Usina Teste 1 - UF"
CATALOGO = [{"id": 1, "code": "TST-NBRK1", "label": "TST-NBRK1 — Nobreak", "description": "Nobreak 1      { TST-NBRK1 }",
             "tipo": "NBRK", "usina": USINA, "cliente": "Cliente X", "id_type_item": 1, "id_group_task": 7},
            {"id": 3, "code": "TST-RELE1", "label": "TST-RELE1 — Relé da Cabine", "description": "Relé da Cabine 1",
             "tipo": "RELE", "usina": USINA, "cliente": "Cliente X", "id_type_item": 1, "id_group_task": 7}]
JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"      # de mentira


@pytest.mark.parametrize("agrupar", [False, True])
def test_a_criacao_da_engenharia_confere_ao_vivo_e_passa_pelo_juntar(agrupar, monkeypatch):
    """A regra de 19/10/2026: faltando no Fracttal a pessoa ou a etiqueta ENGENHARIA, nenhuma OS sai. A criação confere as duas
    AO VIVO, antes de gravar o primeiro pedido, e a OS (uma por ativo ou agrupada) chega pelo `juntar_em_os`."""
    import os_juntar
    from os_web import criar_app, solic_eng_web as reg
    fr = FracttalFalso()
    _preparar(monkeypatch, fr)
    monkeypatch.setenv(reg.ENV_RESPONSAVEIS, "Ana Teste")
    monkeypatch.setattr(api, "load_assets_cached", lambda *a, **k: [dict(x) for x in CATALOGO])

    def ao_vivo(quem, valor):
        def ler(*a, **k):
            fr.eventos.append({"ao_vivo": quem})
            return copy.deepcopy(valor)
        return ler
    monkeypatch.setattr(api, "responsaveis_ao_vivo", ao_vivo("pessoal", [{"code": "A1", "name": "Ana Teste Silva",
                                                                            "id_personnel": 501}]))
    monkeypatch.setattr(api, "get_labels", ao_vivo("etiquetas", [{"id": 900, "description": "ENGENHARIA"}]))
    juntou = []
    original = os_juntar.juntar_em_os
    monkeypatch.setattr(os_juntar, "juntar_em_os", lambda *a, **k: juntou.append(a) or original(*a, **k))
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Pessoa Teste", "email": "teste@exemplo.invalid", "perfil": "ADMINISTRATOR"}
    corpo = {"ativos": [1, 3], "descricao": "Avaliar o religamento", "problema": "Desarma toda manhã.",
             "responsavel": {"id_personnel": 501}, "urgente": False, "agrupar": agrupar}
    r = c.post("/os/api/solicitacao/engenharia/criar", json=corpo)
    assert r.status_code == 200 and r.get_json()["ok"], r.get_data(as_text=True)[:300]
    ordem = [e.get("ao_vivo") or e.get("pedido") for e in fr.eventos if e.get("ao_vivo") or e.get("pedido")]
    assert ordem[:2] == ["pessoal", "etiquetas"] and INSERIR_TAREFA in ordem[2:]      # conferiu as duas antes de gravar
    assert len(juntou) == (1 if agrupar else 2)
    etiquetas = [e["params"]["id_labels"] for e in fr.eventos if e.get("pedido") == ETIQUETAS]
    assert etiquetas == [[900]] * len(juntou)                                           # só a ENGENHARIA, em cada OS
    # a pessoa que não está mais no Fracttal ao vivo: nenhuma OS sai, e nenhum pedido de gravação
    antes = len(fr.eventos)
    monkeypatch.setattr(api, "responsaveis_ao_vivo", ao_vivo("pessoal", []))
    r = c.post("/os/api/solicitacao/engenharia/criar", json=corpo)
    assert r.status_code == 400 and not [e for e in fr.eventos[antes:] if e.get("pedido")]


if __name__ == "__main__":
    if "--regravar" in sys.argv:
        regravar()

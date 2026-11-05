"""os_criar.py: os caminhos que CRIAM OS.

Cada um cria as tarefas pendentes (a fase 1, que muda de caminho para caminho: o plano, a clonagem, o título por ativo) e entrega
a `os_juntar.juntar_em_os` (a fase 2, uma só para todos): a Clonagem de planos do PCM, a Clonagem de OS, a OS sem plano, o Criar
OS do zero (uma OS por ativo, agrupada e por data), a Performance, a OS de análise e a do chamado. A tarefa em si
(`create_os_rpc`, `_react_insert_post`) fica no `api.py`: é quem fala com a rede.

Saiu do `api.py` em 31/10/2026 (etapa 5.3 do canto central, "o que sobra do api.py"): mudou só o lugar, o código é o mesmo. O
`api.py` segue expondo os mesmos nomes (`api.X`), porque a ponte, as rotas e os testes chamam e TROCAM `api.X` pelo nome. Por
isso toda função que este módulo chama, dele ou de fora (o `api._rpc_call`, o que também saiu para outro módulo), e todo número
ajustável (um prazo, um teto) vão pelo `api.`, e enxergam a troca; só as outras constantes e o estado daqui são usados direto. O
módulo termina com `import api`: o `api` o importa no fim do arquivo (a fachada), e só precisa dele na hora da chamada."""

import time
import uuid
from datetime import datetime, timedelta, timezone
from fracttal_erro import FracttalError, SessionExpired
import os_juntar


# ── Fase 2: converter tarefa pendente em WO numerada + atribuir responsável ───
RPC_KANBAN   = "tasks.tasks_todo_list_kanban"
RPC_WO_INSERT = "tasks.work_order_insert"
# Campos que o web app inclui no registro de array_tasks_todo mas que a lista do kanban
# não devolve (defaults observados no cURL real). O registro do kanban tem precedência.
_WO_TASK_DEFAULTS = {
    "id_status_work_order": 5, "resources": [], "num_resources": 0, "triggers": {},
    "cfg_description": None, "custom_fields_values": None, "first_date_maintenance": None,
    "related_items": None, "reschedule_causes": None, "task_failure": None,
    "cc_description": None, "wo_folio": None, "custom_fields_groups_description": None,
    "is_configured": True,
}


def _kanban_records(id_tasks: set, tentativas: int = 3) -> dict:
    """Busca na lista de tarefas pendentes (kanban) os registros completos dos id_tasks dados.
    → {id_task: registro}. Retenta pois a tarefa recém-criada pode demorar 1-2s p/ aparecer."""
    faltam = set(id_tasks)
    achados = {}
    for _ in range(tentativas):
        res = api._rpc_call(RPC_KANBAN, {"page": 1, "limit": 200, "start": 0, "append": True,
                                     "is_tree": False, "id_type_item": 0, "filter": [], "group": {}, "sort": []})
        data = res.get("data") if isinstance(res, dict) else res
        for t in (data if isinstance(data, list) else []):
            if isinstance(t, dict) and t.get("id_task") in faltam:
                achados[t["id_task"]] = t
        faltam -= set(achados)
        if not faltam:
            break
        time.sleep(1.5)
    return achados


def _work_order_insert(kanban_recs: list, id_responsible, responsible_name: str = "",
                       duration: int = 600, id_parent=None, note: str = "") -> dict:
    """Insere UMA WO contendo TODAS as tarefas dos registros de kanban dados (array_tasks_todo).
    1 registro → OS de 1 tarefa; N registros → 1 OS com N tarefas (igual a selecionar várias
    tarefas pendentes no kanban e gerar uma OT só). Atribui o responsável (id_personnel)."""
    recs = []
    for kr in kanban_recs:
        rec = {**_WO_TASK_DEFAULTS, **dict(kr)}
        rec["resources"] = []
        recs.append(rec)
    nome = (responsible_name or "").strip()
    inner = {
        "creation_mode": 1, "type_user": "HUMAN_RESOURCES", "duration": duration,
        "enable_budget": False, "id_third_party": None, "third_party_description": "",
        "id_responsible": id_responsible, "personnel_description": nome, "name": nome,
        "array_tasks_todo": recs,
    }
    # OS PAI da OS inteira. Sondado em 26/08: aqui, na CRIAÇÃO, o campo é `id_parent` e funciona
    # (OS 12190 nasceu com id_parent_wo preenchido). DEPOIS não dá: o `work_orders_update` com
    # `id_parent_wo` responde ACTION_DONE e grava None — aceita e ignora, como o `date_maintenance`.
    if id_parent:
        inner["id_parent"] = id_parent
    # OBSERVAÇÃO DA OS — separada das notas das TAREFAS (Levi, 26/08). Sondado na OS 12273: o
    # `note` no insert grava na OS e não encosta nas tarefas, então as duas convivem. É o campo
    # que faltava: até aqui só existia a nota por ativo, e o recado que vale para o lote inteiro
    # não tinha onde morar.
    if (note or "").strip():
        inner["note"] = note.strip()
    params = {"page": 1, "limit": 200, "start": 0, "append": True,
              "id_internal": str(uuid.uuid4()), "id_background_process_type": 1,
              "status": 1, "determinate": False, "params": inner,
              **inner, "wo_creation_status": False, "id_transaction": None}
    res = api._rpc_call(RPC_WO_INSERT, params)
    data = res.get("data") if isinstance(res, dict) else (res if isinstance(res, dict) else {})
    data = data if isinstance(data, dict) else {}
    # síncrono: a resposta (message SUCCESS_NEW_WO_VERIFY_QUEUE) já traz a WO em data.id + wo_folio
    return {"id_work_order": data.get("id") or data.get("id_work_order"),
            "wo_folio": data.get("wo_folio") or data.get("code"),
            "id_transaction": data.get("id_transaction"), "raw": res}


RPC_LABELS_SYNC = "tasks.work_order_labels_sync"


def apply_labels(id_work_order, id_labels: list) -> dict:
    """Aplica (sync) o conjunto de etiquetas id_labels numa WO. Devolve {'ok',...}."""
    ids = [i for i in (id_labels or []) if i]
    if not id_work_order or not ids:
        return {"ok": False, "erro": "sem id_work_order ou id_labels"}
    res = api._rpc_call(RPC_LABELS_SYNC, {"page": 1, "limit": 200, "start": 0, "append": True,
                                      "id_work_order": id_work_order, "id_labels": ids})
    return {"ok": True, "raw": res}


TIPO_ANALISE = "Administrativa"        # tipo de tarefa da OS de análise (Levi, 03/08)
ANALISE_CLASSIF_1 = "Programada"       # Classificação 1  ┐ mesmas das OS de ETM
ANALISE_CLASSIF_2 = "Elétrica"         # Classificação 2  ┘ (conferido nas OS 10445/10444/10383)


def create_os_analise(asset: dict, id_responsible, resp_code="", resp_name="",
                      prioridade="", motivo="", descricao="", pedido_por="",
                      os_pai_folio="", tipo_tarefa=TIPO_ANALISE, bloco_texto="") -> dict:
    """Cria a OS de ANÁLISE de performance, atribuída a um analista.

    TIPO 'Administrativa' + classificação 'Programada / Elétrica' (Levi, 03/08): é trabalho de
    escritório, igual às OS de ETM, e agora sai idêntico a elas no Fracttal. Antes nascia como
    'Inspeção' e sem classificação nenhuma. O que vai a CAMPO é a OS FILHA que a análise gera —
    o exemplo da gestão de chamados na reunião ("a analista fechou o card dela e abriu cinco verificações em campo").
    A classificação é resolvida pelo NOME no catálogo (`_classif_ids`), porque a lista é editável
    dentro do Fracttal e id fixo quebraria na primeira edição.

    `bloco_texto` = o bloco [PERFORMANCE] já montado pelo `perf_spec.bloco()` — vem pronto da tela
    para o api não depender do módulo de regra. Entra ANTES da descrição livre porque a API do
    Fracttal não edita OS criada: o que não for gravado agora só muda no Fracttal web.

    → {'ok','folio','id_work_order','etiqueta_ok','aviso'} ou {'ok':False,'erro'}.
    """
    if not isinstance(asset, dict) or not (asset.get("code") or "").strip():
        return {"ok": False, "erro": "Escolha o ativo (usina ou equipamento) no catálogo."}
    if not id_responsible:
        return {"ok": False, "erro": "Escolha o analista — sem responsável a OS não recebe número."}
    lid = api._label_id(api.perf_spec_nome_etiqueta())
    if not lid:
        return {"ok": False, "erro": "Não achei a etiqueta 'PERFORMANCE' no Fracttal."}
    etiquetas = [lid]
    # "Dar prioridade" (2603) entra JUNTO na prioridade máxima: quem abrir a OS direto no Fracttal,
    # sem passar por esta tela, precisa enxergar a urgência lá também.
    if (prioridade or "").strip().lower() == "máxima".lower():
        pid = api._label_id("Dar prioridade")
        if pid:
            etiquetas.append(pid)

    titulo = api.perf_os_nome(asset, (motivo or "").strip() or "Análise de performance")

    id_parent = None
    folio_pai = str(os_pai_folio or "").strip()
    if folio_pai:
        try:
            for c in api.buscar_os_pai(folio_pai, limit=20):
                if str(c.get("folio")).strip() == folio_pai:
                    id_parent = c.get("id"); break
        except FracttalError:
            pass                        # OS pai é opcional: não achou, cria sem vínculo

    livre = (descricao or "").strip()
    note = (bloco_texto or "").strip()
    note = (note + ("\n\n" + livre if livre else "")) if note else livre

    # `tipo` = classificação 1/2 pelo nome. O `create_os_rpc` só grava o par quando id_c1/id_c2 vêm
    # preenchidos, então nome que não existir no catálogo apenas não entra (OS sem classificação é
    # menos ruim que OS com a classificação errada).
    _c = api._classif_ids(ANALISE_CLASSIF_1, ANALISE_CLASSIF_2)
    tipo = {}
    if _c.get("id_task_type") is not None:
        tipo["id_c1"] = _c["id_task_type"]; tipo["desc_c1"] = _c.get("tasks_types_description") or ""
    if _c.get("id_task_type_2") is not None:
        tipo["id_c2"] = _c["id_task_type_2"]; tipo["desc_c2"] = _c.get("tasks_types_2_description") or ""

    res = api.create_work_orders_bulk([asset], titulo, tipo_tarefa, [], etiqueta_ids=etiquetas,
                                  id_parent=id_parent, id_responsible=id_responsible,
                                  responsible_code=resp_code, responsible_name=resp_name,
                                  note=note, tipo=tipo or None)
    r0 = res[0] if res else {}
    if not r0.get("ok"):
        return {"ok": False, "erro": r0.get("erro") or "não consegui criar a OS."}
    o = r0.get("os") or {}
    return {"ok": True, "folio": o.get("wo_folio"), "id_work_order": o.get("id_work_order"),
            "etiqueta_ok": bool(o.get("etiquetas")), "os_pai": folio_pai or None,
            "aviso": o.get("aviso")}


def create_os_chamado(parent_folio, id_responsible, resp_code="", resp_name="",
                      concluir=False, note="", ticket="", motivo="", subtarefas=None,
                      dados_chamado=None) -> dict:
    """CHAMADOS: cria uma OS NOVA no MESMO ativo de uma OS existente (nº = parent_folio), vinculando-a
    como OS PAI e aplicando a etiqueta 'CHAMADOS'. `concluir` = fecha a OS logo após criar. Herda tipo/
    classificação/criticidade da OS pai. `ticket`/`motivo` entram no título; `subtarefas` (Lista já
    montadas pela tela) viram as subtarefas rastreáveis. → {'ok','folio','os_pai','etiqueta_ok',
    'concluida','aviso'} ou {'ok':False,'erro'}. NADA é criado se a OS/ativo/etiqueta não forem resolvidos."""
    parent_folio = str(parent_folio or "").strip()
    if not parent_folio:
        return {"ok": False, "erro": "Digite o número da OS do chamado."}
    if not id_responsible:
        return {"ok": False, "erro": "Escolha o responsável (a OS pai e a etiqueta só gravam com ele)."}
    d = api.get_os_detalhes_por_folio(parent_folio)
    if not isinstance(d, dict):
        return {"ok": False, "erro": f"Não achei a OS nº {parent_folio}."}
    parent_wo = d.get("id_work_order")
    code = (d.get("code") or "").strip()
    asset = api._asset_by_code(code) if code else None
    if not isinstance(asset, dict):
        return {"ok": False, "erro": f"A OS {parent_folio} não tem um ativo do catálogo "
                "(recarregue os ativos e tente de novo)."}
    lid = api._label_id("CHAMADOS")
    if not lid:
        return {"ok": False, "erro": "Não achei a etiqueta 'CHAMADOS' no Fracttal — crie a etiqueta lá "
                "(Configurações → Etiquetas) e tente de novo."}
    # id_parent = mesma fonte do seletor de OS pai (o 'id' do work_orders_parents_list, não o nº)
    id_parent = parent_wo
    try:
        for c in api.buscar_os_pai(parent_folio, limit=20):
            if str(c.get("folio")).strip() == parent_folio:
                id_parent = c.get("id"); break
    except FracttalError:
        pass
    # tipo/classificação/criticidade herdados da OS pai (ids diretos da tarefa)
    rt = api._rpc_call(api.RPC_WO_TASKS, {"id_work_order": parent_wo, "sort": []})
    t0 = (rt.get("data") or [{}])[0] if isinstance(rt, dict) else {}
    tipo = {"id_main": t0.get("id_task_type_main"),
            "id_priorities": t0.get("id_priorities") or api.ID_PRIORITIES}
    if t0.get("id_task_type") is not None:
        tipo["id_c1"] = t0.get("id_task_type"); tipo["desc_c1"] = str(t0.get("tasks_types_description") or "")
    if t0.get("id_task_type_2") is not None:
        tipo["id_c2"] = t0.get("id_task_type_2"); tipo["desc_c2"] = str(t0.get("tasks_types_2_description") or "")
    main = str(t0.get("tasks_types_main_description") or "Corretiva")
    # título: [Ticket X][Usina][Ativo] - Motivo  (cai no padrão do COS; sem ticket/motivo → fallback)
    tk = str(ticket or "").strip()
    base = str(motivo or "").strip() or "Chamado"
    titulo = (f"[Ticket {tk}] " if tk else "") + api.perf_os_nome(asset, base)
    # observação = BLOCO CHAMADO (que o board lê) + a observação livre do operador
    obs_livre = (note or "").strip()
    if dados_chamado:
        dc = dict(dados_chamado); dc.setdefault("os_pai", parent_folio)   # OS de abertura = a OS pai
        note_final = api.bloco_chamado(dc) + (("\n\n" + obs_livre) if obs_livre else "")
    else:
        note_final = obs_livre
    res = api.create_work_orders_bulk([asset], titulo, main, (subtarefas or []),
                                  etiqueta_ids=[lid], id_parent=id_parent,
                                  id_responsible=id_responsible, responsible_code=resp_code,
                                  responsible_name=resp_name, note=note_final, tipo=tipo)
    r0 = res[0] if res else {}
    if not r0.get("ok"):
        return {"ok": False, "erro": r0.get("erro") or "não consegui criar a OS."}
    o = r0.get("os") or {}
    novo_wo = o.get("id_work_order")
    aviso = o.get("aviso")
    concluida = False
    if concluir and novo_wo:
        try:
            cr = api.concluir_os(novo_wo)
            concluida = not (isinstance(cr, dict) and cr.get("ok") is False)
            if not concluida:
                aviso = ((aviso or "") + " OS criada, mas não consegui concluir.").strip()
        except FracttalError as e:
            aviso = ((aviso or "") + f" OS criada, mas não concluiu: {e}").strip()
    return {"ok": True, "folio": o.get("wo_folio"), "id_work_order": novo_wo,
            "os_pai": parent_folio, "etiqueta_ok": bool(o.get("etiquetas")),
            "concluida": concluida, "aviso": aviso}


def create_planned_os(asset: dict, plan: dict, id_responsible=None, responsible_name: str = "",
                      event_date: datetime = None, to_work_order: bool = True, id_parent=None,
                      descricao: str = None, note: str = "", linkar_plano: bool = True,
                      prog_date: datetime = None, duracao: int = None) -> dict:
    """Cria 1 tarefa planejada (tasks_noscheduled_react_insert com o plano: id_task + subtarefas +
    tipo do plano). `to_work_order=True` → vira WO direto (1 ativo). `to_work_order=False` → tarefa
    PENDENTE no kanban (p/ depois juntar várias numa OS só, via create_planned_os_one_wo).
    `descricao` = nome custom da tarefa (senão usa o do plano); `note` = observação da OS.
    `linkar_plano=False` → cria como OS avulsa com as subtarefas COPIADAS do plano (id_task=None) — usado
    p/ trackers individuais, cujo plano mora no ativo generalizado. `plan` = get_plan_details.
    Devolve {'id_task','id_work_order','wo_folio','id_work_order_task','raw'}."""
    id_item = asset.get("id")
    if not id_item:
        raise FracttalError(f"Ativo '{asset.get('code')}' sem id_item — recarregue os ativos.")
    if linkar_plano and not plan.get("id_task"):
        raise FracttalError("Plano sem id_task.")
    if not plan.get("subtasks"):
        raise FracttalError("Não carreguei as subtarefas do plano (estrutura do tasks_details a confirmar) "
                            "— relogue e/ou me mande a resposta do tasks_details.")
    ev = event_date if event_date is not None else datetime.now(timezone.utc)
    if ev.tzinfo is None:
        ev = ev.replace(tzinfo=timezone.utc)
    # DATA PROGRAMADA separada da data do INCIDENTE (pedido do Levi, 27/07): antes a programação era
    # sempre "incidente + 10 min", ou seja, não dava para abrir hoje uma OS para a semana que vem.
    # O default reproduz exatamente a conta antiga (prog = ev+10 → janela ev-10 .. ev+20).
    prog = prog_date if prog_date is not None else ev + timedelta(minutes=10)
    if prog.tzinfo is None:
        prog = prog.replace(tzinfo=timezone.utc)
    # A DURAÇÃO PODE VIR DA TELA (Levi, 14/09: "mostrar o tempo da tarefa e permitir editar o
    # tempo de cada"). Sem isso vale a do plano, que é o que sempre valeu. Ela não é decorativa:
    # é ela que fecha a janela de programação (`final_date` abaixo), então mudar o tempo aqui
    # muda quanto a OS ocupa na agenda do técnico no Fracttal.
    dur = int(duracao) if duracao else int(plan.get("duration") or 900)
    id_ref = plan.get("id_task") if linkar_plano else None       # tracker individual = OS não-linkada
    # A JANELA COMEÇA NA HORA ESCOLHIDA. Medido na OS 10402 (30/07): o Fracttal IGNORA o
    # `date_maintenance` que a gente manda e grava o `initial_date` como data de programação —
    # mandei 11:00Z e ele guardou 10:40Z, que era o initial_date (prog − 20 min). Ou seja, toda OS
    # criada por aqui, INCLUSIVE as de Performance, nascia programada 20 minutos antes da hora que
    # a pessoa escolheu. Agora initial_date = prog, e a janela fecha na duração estimada.
    params = {
        "event_date": api._iso_z(ev),
        "cal_date_maintenance": api._iso_z(prog),
        "date_maintenance": api._iso_z(prog),
        "initial_date": api._iso_z(prog),
        "final_date": api._iso_z(prog + timedelta(seconds=dur)),
        "type_user": "HUMAN_RESOURCES", "id_priorities": plan.get("id_priorities") or api.ID_PRIORITIES,
        "id_failure_severity": 0, "id_damage_type": 1, "failure_asset": False,
        "to_in_review": False, "work_done": False, "to_work_order": to_work_order, "stop_assets": False,
        "duration": dur, "real_duration": 0,
        "requested_by": (responsible_name or "").strip() or "GridCo O&M", "edit_mode": False,
        "tasks_types_main_description": plan.get("tasks_types_main_description") or "",
        "subtasks": plan.get("subtasks") or [], "array_resources": [],
        "id_item": id_item, "items_description": asset.get("description") or "",
        "id_request": None, "note": note or "", "name": (responsible_name or "").strip() or None,
        "available": None, "initial_date_out_of_service": None,
        "id_group_task": asset.get("id_group_task"), "assigment_date": api._iso_z(ev),
        "id_work_order_task_related": None, "date_asset_out_of_service": None,
        "description": (descricao if descricao is not None else (plan.get("description") or "")),
        "id_type_item": asset.get("id_type_item") or 1,
        "path_node": api._path_node(asset), "msg_availability": "ASSET_OUT_OF_SERVICE",
        "id_task_reference": id_ref, "id_task": id_ref,
        "id_task_type_main": plan.get("id_task_type_main"),
        "id_task_type": plan.get("id_task_type"), "id_task_type_2": plan.get("id_task_type_2"),
        "tasks_types_description": plan.get("tasks_types_description") or "",
        "tasks_types_2_description": plan.get("tasks_types_2_description") or "",
        "task_note": "", "id_parent": id_parent,          # OS pai (opcional)
    }
    if to_work_order and id_responsible is not None:      # WO direto (1 ativo) → atribui o responsável
        params["id_assigned_user"] = id_responsible
    body = [{"id": str(uuid.uuid4()), "jsonrpc": "2.0", "method": api.RPC_METHOD, "params": params}]
    r = {**api._react_insert_post(body), "duracao": dur}        # o tempo da tarefa: a OS que junta as tarefas soma este
    # a OS que nasce numerada (`to_work_order`) leva a OS pai neste mesmo pedido, e ela fica (provado no ar em 04/11/2026: a OS
    # 18571, Performance de uma OS por ativo, nasceu com a 18560 de pai); a conferência depois de gravar é a da fase 2
    if to_work_order and id_parent:
        aviso = os_juntar.conferir_os_pai(r.get("id_work_order"), id_parent, r.get("wo_folio"))
        if aviso:
            r["aviso"] = aviso
    return r


def nascer_ticket(item: dict, asset: dict, plano_desc, folio, event_date) -> dict:
    """A ocorrência de tickets que nasce junto da OS (Levi, 31/08 — "o pulo do gato").

    → {'aba', 'ok', 'quantidade', 'erro', 'aviso_os'}. `aba` vazia = este plano não gera
    ocorrência nenhuma (só Recomposição de String e Verificação de Tracker Parado geram).

    EXTRAÍDA EM 10/09 porque agora são DOIS caminhos chamando: a criação de N OS e a agrupada,
    que até aqui não criava ocorrência alguma — marcar "Agrupar em UMA OS" significava, sem
    nenhum aviso, nenhum ticket. Uma cópia do bloco em cada uma sairia do ar na primeira
    correção feita só de um lado.

    O item pode trazer `gerar_ticket` (a caixa da tela, marcada por padrão) e `qtd_ticket` (o
    card ao lado do ativo). A `note` do item é a observação daquele ativo, e é dela que sai a
    frase de "Comentários gerais".

    FALHAR AQUI NÃO DERRUBA A OS. Ela é o que a equipe precisa; a linha de ticket é registro.
    O erro volta em `aviso_os`, para a tela dizer o que ficou faltando."""
    if not item.get("gerar_ticket", True):
        return {"aba": "", "ok": False, "quantidade": 0, "desligado": True}
    try:
        # import tardio: o tickets_nasce importa este módulo, e no topo daria import circular.
        import tickets_nasce
        aba = tickets_nasce.aba_do_plano(plano_desc)
        if not aba:
            return {"aba": "", "ok": False, "quantidade": 0}
        tk = tickets_nasce.criar(aba, asset, tickets_nasce.usina_do_ativo(asset), folio,
                                 quando=event_date, quantidade=item.get("qtd_ticket"),
                                 nota=item.get("note") or "")
        tk["aba"] = aba
        if not tk.get("ok"):
            tk["aviso_os"] = "ocorrência não registrada: %s" % tk.get("erro")
        elif tk.get("aviso"):
            tk["aviso_os"] = tk["aviso"]
        return tk
    except Exception as e:                           # noqa: BLE001
        return {"aba": "", "ok": False, "quantidade": 0, "erro": str(e)[:120],
                "aviso_os": "ocorrência não registrada (%s)" % str(e)[:80]}


def _plano_da_performance(id_task, id_item, subtarefas_padrao=None) -> dict:
    """O plano de uma atividade da Performance como a OS o leva: com o padrão do Nexus no lugar das subtarefas, quando a
    atividade tem um salvo (05/11/2026, `com_subtarefas_padrao`), senão com as do app (`com_subtarefas_extra`); e o tipo de
    tarefa do app (`com_tipo_da_tarefa`)."""
    p = api.get_plan_details(id_task, id_item)
    if subtarefas_padrao and p.get("subtasks"):
        p = api.com_subtarefas_padrao(p, subtarefas_padrao)
    else:
        p = api.com_subtarefas_extra(p)
    return api.com_tipo_da_tarefa(p)


def create_performance_os(itens: list, id_responsible=None, responsible_name: str = "",
                          event_date: datetime = None, id_parent=None, progresso=None,
                          prog_date: datetime = None, etiquetas_extra=None, subtarefas_padrao=None) -> list:
    """Cria N OS (1 por ativo). `itens` = [{asset, plano_id_task, plano_id_item, linkar, base, note, imagens}]
    onde imagens = [{'bytes','nome'}]. Lê o plano (cache por id_task), cria a OS '[Ativo] - base' + note,
    marca com a etiqueta 'Performance' e anexa as imagens. → [{ok, asset, folio/erro, n_img_ok, img_erro}].

    `event_date` = data do INCIDENTE; `prog_date` = data PROGRAMADA (None → incidente + 10 min, como era).
    `etiquetas_extra` = nomes de etiquetas a somar à 'Performance' (o modo ETM manda 'ENGENHARIA').
    `subtarefas_padrao` = a lista do padrão do Nexus da atividade (`_plano_da_performance`), ou None (a do plano).
    Um item pode trazer `titulo`: título LITERAL da OS, que pula o prefixo automático `[Ativo] -`."""
    cache, out = {}, []
    lbl_perf = api._label_performance_id()               # etiqueta "Performance" em toda OS criada aqui
    lbls = [l for l in [lbl_perf] +
            [api.label_id_por_nome(n) for n in (etiquetas_extra or [])] if l]
    itens = [it for it in (itens or []) if isinstance(it.get("asset"), dict)]
    pai_cache = {}
    def _resolve_pai(folio):                         # nº da OS pai (por ativo) → id_parent (via parents_list)
        folio = str(folio or "").strip()
        if not folio:
            return None
        if folio not in pai_cache:
            pid = None
            try:
                for c in api.buscar_os_pai(folio, limit=20):
                    if str(c.get("folio")).strip() == folio:
                        pid = c.get("id"); break
            except Exception:
                pid = None
            pai_cache[folio] = pid
        return pai_cache[folio]
    for i, it in enumerate(itens):
        a = it["asset"]
        try:
            k = it.get("plano_id_task")
            if k not in cache:
                # as subtarefas extras (ou o padrão do Nexus) entram UMA vez, junto do cache — ver com_subtarefas_extra
                cache[k] = api._plano_da_performance(k, it.get("plano_id_item"), subtarefas_padrao)
            plan = cache[k]
            nome = (it.get("titulo") or "").strip() or \
                api.perf_os_nome(a, it.get("base") or api.plano_base_nome(plan.get("description")))
            folio_pai = str(it.get("os_pai") or "").strip()
            ip = _resolve_pai(folio_pai) or id_parent   # OS pai do ativo (senão o global, se houver)
            def _criar(p):
                return api.create_planned_os(a, p, id_responsible=id_responsible,
                                         responsible_name=responsible_name,
                                         event_date=event_date, id_parent=ip, descricao=nome,
                                         note=it.get("note") or "",
                                         linkar_plano=it.get("linkar", True), prog_date=prog_date)
            aviso_extra = ""
            try:
                res = _criar(plan)
            except FracttalError:
                # REDE DE SEGURANÇA das subtarefas que o app acrescenta: se o RPC recusar por
                # causa delas, a OS sai sem elas em vez de não sair. E o cache perde as extras,
                # para o resto do lote não repetir a tentativa que já falhou.
                if not api.tem_subtarefas_extra(plan):
                    raise
                era_padrao = api.tem_subtarefas_padrao(plan)
                cache[k] = plan = api.sem_subtarefas_extra(plan)
                res = _criar(plan)
                aviso_extra = (("as subtarefas padrão do Nexus" if era_padrao else "as perguntas de fim de atividade")
                               + " não entraram — o Fracttal recusou; a OS foi criada com as subtarefas do plano.")
            # as ressalvas desta OS vão à tela (04/11/2026): a OS pai que o Fracttal não gravou (o `create_planned_os` confere)
            # e a que não achei pelo nº digitado. Até aqui a OS saía sem pai calada, e o aviso das perguntas se perdia aqui
            # dentro (o `res` não volta à tela, só o `out`)
            avisos = [res["aviso"]] if res.get("aviso") else []
            if folio_pai and not ip:
                avisos.append("OS %s criada sem a OS pai: não achei a OS %s no Fracttal." % (res.get("wo_folio"), folio_pai))
            if aviso_extra:
                avisos.append("OS %s: %s" % (res.get("wo_folio"), aviso_extra))
            if lbls and res.get("id_work_order"):
                try:
                    api.apply_labels(res["id_work_order"], lbls)
                except Exception:
                    pass
            tk = api.nascer_ticket(it, a, plan.get("description"), res.get("wo_folio"), event_date)   # o aviso dele vai pelo `ticket`
            nok, nerr = 0, []
            for img in (it.get("imagens") or []):
                try:
                    api.attach_imagem_os(res.get("id_work_order"), res.get("id_work_order_task"),
                                     img.get("bytes"), img.get("nome") or "imagem.png")
                    nok += 1
                except Exception as e:
                    nerr.append(str(e)[:600])
            # o id vai junto (31/10/2026): a tela põe a OS criada na lista central de OS (`lista_central.criadas`)
            out.append({"ok": True, "asset": a.get("label") or a.get("code"), "folio": res.get("wo_folio"),
                        "id_work_order": res.get("id_work_order"), "n_img_ok": nok, "img_erro": nerr, "ticket": tk,
                        **({"aviso": " ".join(avisos)} if avisos else {})})
        except SessionExpired:
            raise
        except Exception as e:
            out.append({"ok": False, "asset": a.get("label") or a.get("code"), "erro": str(e)[:200]})
        if progresso:
            progresso(i + 1, len(itens))
    return out


def create_planned_os_multi(selecoes: list, id_responsible, responsible_name: str = "",
                            event_date: datetime = None, id_parent=None) -> dict:
    """1 OS com as tarefas dos planos SELECIONADOS — `selecoes` = [{asset, id_task[, event_date]}]. Para
    cada um: busca as subtarefas (tasks_details) e cria a tarefa PENDENTE (com a data da própria linha,
    se houver, senão a `event_date` geral); Fase 2 junta tudo numa OS só.
    → {'ok','os':{id_work_order,wo_folio,id_tasks},'n_tarefas','n_criadas','erros'[,'aviso']}."""
    sel = [s for s in (selecoes or []) if isinstance(s.get("asset"), dict) and s.get("id_task")]
    if not sel:
        return {"ok": False, "erro": "Nenhum plano selecionado.", "n_tarefas": 0, "n_criadas": 0}
    id_tasks, erros, dur_de = [], [], {}
    for s in sel:
        asset, idt = s["asset"], s["id_task"]
        try:
            plan = api.get_plan_details(idt, asset.get("id"))
            if not plan.get("subtasks"):
                erros.append(f"{asset.get('code')}: plano sem subtarefas"); continue
            r = api.create_planned_os(asset, plan, event_date=s.get("event_date") or event_date,
                                  to_work_order=False, id_parent=id_parent,
                                  duracao=s.get("duracao"))    # o tempo editado na linha da tela
            if r.get("id_task"):
                id_tasks.append(r["id_task"])
                dur_de[r["id_task"]] = r.get("duracao")
            else:
                erros.append(f"{asset.get('code')}: tarefa não criada")
        except FracttalError as e:
            erros.append(f"{asset.get('code')}: {e}")
    if not id_tasks:
        return {"ok": False, "erro": "Falha ao criar as tarefas: " + "; ".join(erros[:3]),
                "n_tarefas": len(sel), "n_criadas": 0}
    jun = os_juntar.juntar_em_os(id_tasks, dur_de, id_responsible, responsible_name,       # a fase 2, a mesma de todos
                                 id_parent=id_parent)
    saida = {"ok": True, "n_tarefas": len(sel), "n_criadas": len(id_tasks), "erros": erros, "os": os_juntar.da_os(jun)}
    if jun.get("aviso"):
        saida["aviso"] = jun["aviso"]
    return saida


def create_planned_os_one_wo(assets: list, plan: dict, id_responsible, responsible_name: str = "",
                             event_date: datetime = None) -> dict:
    """Cria UMA OS com VÁRIAS tarefas — cada ativo vira 1 tarefa (com as subtarefas do plano).
    Mesmo molde do clone: Fase 1 cria N tarefas planejadas PENDENTES; Fase 2 junta no kanban e faz
    1 work_order_insert → 1 OS multi-tarefa + responsável.
    → {'ok','os':{id_work_order,wo_folio,id_tasks},'n_tarefas','n_criadas','erros'[,'aviso']}."""
    val = []
    for a in (assets or []):
        asset = a if isinstance(a, dict) else api._asset_by_code(a)
        if isinstance(asset, dict) and asset.get("id"):
            val.append(asset)
    if not val:
        return {"ok": False, "erro": "Nenhum ativo válido.", "n_tarefas": 0, "n_criadas": 0}
    if not plan.get("subtasks"):
        return {"ok": False, "erro": "Plano sem subtarefas (estrutura do tasks_details a confirmar) — "
                "relogue e/ou me mande a resposta do tasks_details.", "n_tarefas": len(val), "n_criadas": 0}
    # Fase 1 — N tarefas planejadas PENDENTES (1 por ativo)
    id_tasks, erros, dur_de = [], [], {}
    for asset in val:
        try:
            r = api.create_planned_os(asset, plan, event_date=event_date, to_work_order=False)
            if r.get("id_task"):
                id_tasks.append(r["id_task"])
                dur_de[r["id_task"]] = r.get("duracao")
            else:
                erros.append(f"{asset.get('code')}: tarefa não criada")
        except FracttalError as e:
            erros.append(f"{asset.get('code')}: {e}")
    if not id_tasks:
        return {"ok": False, "erro": "Falha ao criar as tarefas: " + "; ".join(erros[:3]),
                "n_tarefas": len(val), "n_criadas": 0}
    # Fase 2 — junta os registros do kanban e cria 1 WO com TODAS as tarefas (a mesma de todos os caminhos)
    jun = os_juntar.juntar_em_os(id_tasks, dur_de, id_responsible, responsible_name)
    saida = {"ok": True, "n_tarefas": len(val), "n_criadas": len(id_tasks), "erros": erros, "os": os_juntar.da_os(jun)}
    if jun.get("aviso"):
        saida["aviso"] = jun["aviso"]
    return saida


def clonar_os(tarefas: list, id_responsible, responsible_name: str = "",
              etiqueta_ids: list = None, note: str = "", scheduled_date: datetime = None,
              id_parent=None, id_request=None) -> dict:
    """Cria UMA OS nova com TODAS as 'tarefas' dadas (cada uma: asset, tipo, descricao,
    subtarefas — formato de get_os_para_clonar). Fase 1: cria N tarefas pendentes. Fase 2:
    1 work_order_insert com as N → 1 OS multi-tarefa + responsável. Fase 3: etiquetas.
    'note' (se preenchido) sobrescreve a observação de TODAS as tarefas; senão usa a de cada uma.
    Data programada: cada tarefa pode trazer seu próprio 'event_date' (datetime); 'scheduled_date'
    é o fallback p/ as que não tiverem (default de ambos = agora). 'prog_date' (datetime) separa a data PROGRAMADA da
    do evento (a solicitação aprovada na Fila do PCM nasce programada na data sugerida, 15/10/2026). 'duracao' (segundos)
    é o tempo estimado da tarefa (o "Tempo estimado:" da Fila, 21/10/2026); sem ele, o do `create_os_rpc`.
    → {'ok','os':{id_work_order,wo_folio,id_tasks[,etiquetas]}|None,'erro','aviso','n_tarefas','n_criadas'}."""
    val = [t for t in (tarefas or []) if isinstance(t.get("asset"), dict) and t["asset"].get("id")]
    if not val:
        return {"ok": False, "erro": "Nenhuma tarefa com ativo resolvido no catálogo — "
                "recarregue os ativos no Criar OS e tente de novo.",
                "n_tarefas": len(tarefas or []), "n_criadas": 0}
    note = (note or "").strip()
    # Fase 1 — cria as tarefas pendentes (uma por tarefa da OS de referência)
    id_tasks, erros = [], []
    dur_tarefa = {}                    # id da tarefa → o tempo dela (a OS leva a soma)
    for t in val:
        try:
            # a classificação da OS de origem, resolvida no catálogo vivo. Sem isto a OS
            # clonada nascia com Tipo mas SEM Classificação 1 e 2 — e ninguém percebia até
            # abrir a OS no Fracttal (caso das 10893/10895, 27/08).
            _cl = api._classif_ids(t.get("classif_1") or "", t.get("classif_2") or "")
            _tipo = {}
            if _cl.get("id_task_type") is not None:
                _tipo["id_c1"] = _cl["id_task_type"]
                _tipo["desc_c1"] = _cl.get("tasks_types_description") or ""
            if _cl.get("id_task_type_2") is not None:
                _tipo["id_c2"] = _cl["id_task_type_2"]
                _tipo["desc_c2"] = _cl.get("tasks_types_2_description") or ""
            os_ = api.create_os_rpc(t["asset"], t.get("descricao") or "", t.get("tipo") or "Corretiva",
                                t.get("subtarefas") or [], requested_by=responsible_name,
                                tipo=_tipo or None,
                                note=(note or t.get("notas") or ""),
                                event_date=(t.get("event_date") or scheduled_date),
                                prog_date=t.get("prog_date"), duracao=t.get("duracao"),
                                id_parent=id_parent, id_request=id_request)
            if os_.get("id_task"):
                id_tasks.append(os_["id_task"])
                dur_tarefa[os_["id_task"]] = t.get("duracao") or api.DURACAO_OS_AVULSA
            else:
                erros.append(f"{t.get('code') or '?'}: tarefa não criada")
        except FracttalError as e:
            erros.append(f"{t.get('code') or '?'}: {e}")
    if not id_tasks:
        return {"ok": False, "erro": "Falha ao criar as tarefas: " + "; ".join(erros[:3]),
                "n_tarefas": len(val), "n_criadas": 0}
    # sem responsável: ficam como tarefas pendentes (não viram OS numerada)
    if not id_responsible:
        return {"ok": True, "os": {"id_tasks": id_tasks, "wo_folio": None},
                "aviso": "tarefas criadas como pendentes (escolha um responsável p/ gerar a OS numerada).",
                "n_tarefas": len(val), "n_criadas": len(id_tasks)}
    # Fase 2 — junta os registros do kanban e cria 1 WO com TODAS as tarefas, com a SOMA do tempo das tarefas (o PCM, 30/10/2026:
    # "nas SSs o tempo que aparece na OS do Fracttal permanece 10 min, porém nas tarefas aparece o tempo que foi solicitado") e as
    # etiquetas: a mesma de todos os caminhos (`os_juntar`), com as frases desta tela
    jun = os_juntar.juntar_em_os(id_tasks, dur_tarefa, id_responsible, responsible_name, etiqueta_ids=etiqueta_ids,
                                 id_parent=id_parent, frases=os_juntar.FRASES_CLONAR)
    if "id_work_order" not in jun:                       # a OS não saiu: as tarefas ficam pendentes no Fracttal
        return {"ok": True, "os": os_juntar.da_os(jun), "aviso": jun["aviso"],
                "n_tarefas": len(val), "n_criadas": len(id_tasks)}
    avisos = [jun["aviso"]] if jun.get("aviso") else []
    if erros:
        avisos.append(f"{len(erros)} tarefa(s) não criadas: " + "; ".join(erros[:2]))
    return {"ok": True, "os": os_juntar.da_os(jun), "aviso": " | ".join(avisos) or None,
            "n_tarefas": len(val), "n_criadas": len(id_tasks) - jun["nao_entraram"]}


def create_os_sem_plano(selecoes: list, id_responsible, responsible_name: str = "",
                        descricao: str = "", note: str = "", tipo_task: str = "Corretiva",
                        id_parent=None) -> dict:
    """1 OS com VÁRIAS tarefas SEM plano de tarefas — cada ativo vira 1 tarefa com a subtarefa PADRÃO
    'Procedimento' (subtasks=[] → _rpc_subtasks injeta 'Procedimento'). `selecoes` = [{asset[,event_date]}];
    `descricao` (vazia = 'Procedimento') vale p/ todas; `note` = observação. Reusa o motor do clone
    (Fase 1 cria as tarefas pendentes; Fase 2 junta numa OS só + responsável).
    → {'ok','os':{...},'n_tarefas','n_criadas','erros'/'erro'[,'aviso']}."""
    desc = (descricao or "").strip() or "Procedimento"
    tarefas = [{"asset": s.get("asset"), "tipo": tipo_task, "descricao": desc,
                "subtarefas": [], "event_date": s.get("event_date")}
               for s in (selecoes or []) if isinstance(s.get("asset"), dict) and s["asset"].get("id")]
    if not tarefas:
        return {"ok": False, "erro": "Nenhum ativo selecionado.", "n_tarefas": 0, "n_criadas": 0}
    return api.clonar_os(tarefas, id_responsible, responsible_name, etiqueta_ids=None, note=note,
                     id_parent=id_parent)


def _anexa_imagens_bulk(fase1, imagens_por_ativo):
    """Anexa as imagens de cada ativo na OS criada (best-effort). `imagens_por_ativo` = {code: [{bytes,nome}]}.
    Pega o id_work_order_task da OS via _ids_tarefas_da_os. Falha de anexo vira 'aviso' na OS, não derruba."""
    if not imagens_por_ativo:
        return
    for r in fase1:
        os_ = r.get("os") or {}
        if not (r.get("ok") and os_.get("id_work_order")):
            continue
        imgs = imagens_por_ativo.get(r.get("code")) or []
        if not imgs:
            continue
        idwo = os_["id_work_order"]
        try:
            tids = api._ids_tarefas_da_os(idwo)
        except Exception:
            tids = []
        tid = tids[0] if tids else None
        nok = 0
        for im in imgs:
            try:
                api.attach_imagem_os(idwo, tid, im.get("bytes"), im.get("nome") or "imagem.png")
                nok += 1
            except Exception:
                pass
        if nok < len(imgs):
            os_["aviso"] = ((os_.get("aviso") or "") + f" {len(imgs) - nok} imagem(ns) não anexaram.").strip()


def create_work_orders_bulk(assets: list, description: str, task_type: str, subtasks: list,
                            etiqueta: str = "", responsible_code: str = "",
                            responsible_name: str = "", id_responsible=None,
                            etiqueta_ids: list = None, note: str = "", tipo: dict = None,
                            finalizar: dict = None, event_date=None, id_parent=None,
                            imagens_por_ativo: dict = None, por_ativo: dict = None,
                            falha: dict = None, prog_date=None) -> list:
    """Cria N OS (uma por ativo). Fase 1: cria a tarefa pendente (create_os_rpc). Fase 2 (se
    id_responsible): converte em WO numerada + atribui o responsável. Fase 3 (se etiqueta_ids):
    aplica as etiquetas na WO. Fase 4 (se imagens_por_ativo): anexa as imagens em cada OS.
    `por_ativo` (opcional, {code: {'description','note'}}): título/observação POR ativo (COS F2 —
    cada OS ganha '[Usina][Equip] - Motivo' e a observação-pipe do seu próprio ativo). NÃO interrompe
    no 1º erro:
    → [{'code','ok':True,'os':{id_task,id_work_order,wo_folio[,etiquetas][,aviso]}} | {'code','ok':False,'erro'}].
    `finalizar` (OS já realizada) → cada create já devolve a WO concluída c/ responsável → pula Fase 2."""
    fase1 = []
    for a in assets:
        asset = a if isinstance(a, dict) else api._asset_by_code(a)
        code = asset.get("code") if isinstance(asset, dict) else str(a)
        if not isinstance(asset, dict):
            fase1.append({"code": code, "ok": False, "erro": "ativo não encontrado no cache."})
            continue
        ov = (por_ativo or {}).get(code) or {}          # override por ativo (COS F2)
        desc_i = ov.get("description", description)
        note_i = ov.get("note", note)
        try:
            os_ = api.create_os_rpc(asset, desc_i, task_type, subtasks,
                                requested_by=responsible_name, etiqueta=etiqueta, note=note_i,
                                tipo=tipo, event_date=event_date, finalizar=finalizar,
                                id_parent=id_parent, falha=falha, prog_date=prog_date)
            fase1.append({"code": code, "ok": True, "os": os_})
        except FracttalError as e:
            fase1.append({"code": code, "ok": False, "erro": str(e)})

    # OS já realizada: a WO concluída já saiu da Fase 1 (to_work_order) → só aplica etiquetas
    if finalizar:
        if etiqueta_ids:
            for r in [x for x in fase1 if x.get("ok") and x["os"].get("id_work_order")]:
                try:
                    api.apply_labels(r["os"]["id_work_order"], etiqueta_ids)
                    r["os"]["etiquetas"] = list(etiqueta_ids)
                except FracttalError as e:
                    r["os"]["aviso"] = f"WO {r['os'].get('wo_folio')} criada, mas etiqueta falhou: {e}"
        # a OS pai foi no mesmo pedido que criou a OS (provado no ar em 04/11/2026, a OS 18564): conferida como na fase 2
        if id_parent:
            for r in [x for x in fase1 if x.get("ok") and x["os"].get("id_work_order")]:
                aviso_pai = os_juntar.conferir_os_pai(r["os"]["id_work_order"], id_parent, r["os"].get("wo_folio"))
                if aviso_pai:
                    r["os"]["aviso"] = (aviso_pai + " " + (r["os"].get("aviso") or "")).strip()
        api._anexa_imagens_bulk(fase1, imagens_por_ativo)
        return fase1

    # Fase 2 e 3 — converter cada tarefa em WO + responsável + etiquetas (só se um responsável foi escolhido): o kanban é lido
    # uma vez para todas, e cada OS sai pela fase 2 de todos os caminhos (`os_juntar`)
    os_juntar.uma_os_por_tarefa(fase1, id_responsible, responsible_name, etiqueta_ids, id_parent=id_parent)
    api._anexa_imagens_bulk(fase1, imagens_por_ativo)
    return fase1


def create_work_orders_agrupada(assets: list, description: str, task_type: str, subtasks: list,
                                etiqueta: str = "", responsible_name: str = "",
                                id_responsible=None, etiqueta_ids: list = None, note: str = "",
                                tipo: dict = None, event_date=None, id_parent=None,
                                imagens_por_ativo: dict = None, por_ativo: dict = None,
                                falha: dict = None, prog_date=None) -> dict:
    """UMA OS com VÁRIAS tarefas — cada ativo marcado vira uma tarefa dentro da mesma OS.

    Levi, 31/08: é a lógica que o Performance já tinha ("Agrupar em UMA OS com várias tarefas") e
    que faltava no Tradicional, onde marcar N ativos criava N OS separadas. Quando a equipe vai
    ao mesmo lugar mexer em cinco inversores, cinco OS é papelada; uma OS com cinco tarefas é o
    trabalho como ele acontece.

    Mesmo molde do `create_planned_os_one_wo`, mas com as subtarefas DIGITADAS (o Tradicional não
    usa plano): Fase 1 cria N tarefas PENDENTES, Fase 2 junta todas num `work_order_insert` só.
    Sem responsável não há Fase 2 — as tarefas ficam pendentes no kanban, como no fluxo normal.
    → {'ok','os':{id_work_order,wo_folio,id_tasks},'n_tarefas','n_criadas','erros'[,'aviso']}."""
    val, erros = [], []
    for a in (assets or []):
        asset = a if isinstance(a, dict) else api._asset_by_code(a)
        if isinstance(asset, dict) and asset.get("id"):
            val.append(asset)
        else:
            erros.append("%s: ativo não encontrado."
                         % (a.get("code") if isinstance(a, dict) else a))
    if not val:
        return {"ok": False, "erro": "Nenhum ativo válido.", "n_tarefas": 0, "n_criadas": 0,
                "erros": erros}

    id_tasks, por_task, dur_de = [], {}, {}
    for asset in val:
        ov = (por_ativo or {}).get(asset.get("code")) or {}
        try:
            r = api.create_os_rpc(asset, ov.get("description", description), task_type, subtasks,
                              requested_by=responsible_name, etiqueta=etiqueta,
                              note=ov.get("note", note), tipo=tipo, event_date=event_date,
                              id_parent=id_parent, falha=falha, prog_date=prog_date)
            if r.get("id_task"):
                id_tasks.append(r["id_task"])
                por_task[r["id_task"]] = asset.get("code")
                dur_de[r["id_task"]] = r.get("duracao")
            else:
                erros.append("%s: tarefa não criada" % asset.get("code"))
        except FracttalError as e:
            erros.append("%s: %s" % (asset.get("code"), e))
    if not id_tasks:
        return {"ok": False, "erro": "Falha ao criar as tarefas: " + "; ".join(erros[:3]),
                "n_tarefas": len(val), "n_criadas": 0, "erros": erros}

    saida = {"ok": True, "n_tarefas": len(val), "n_criadas": len(id_tasks), "erros": erros,
             "os": {"id_tasks": id_tasks}}
    if not id_responsible:
        saida["aviso"] = ("tarefas criadas e pendentes no kanban — sem responsável não gerei a "
                          "OS numerada.")
        return saida
    # as imagens de CADA ativo vão para a tarefa daquele ativo, dentro da OS única (`os_juntar` as anexa)
    imagens = {idt: imagens_por_ativo.get(por_task[idt]) or [] for idt in id_tasks} if imagens_por_ativo else None
    try:
        jun = os_juntar.juntar_em_os(id_tasks, dur_de, id_responsible, responsible_name, etiqueta_ids=etiqueta_ids,
                                     imagens=imagens, id_parent=id_parent)
    except FracttalError as e:
        saida["aviso"] = "tarefas criadas; a OS não fechou (%s)." % e
        return saida
    saida["os"] = os_juntar.da_os(jun)
    if jun.get("aviso"):
        saida["aviso"] = jun["aviso"]
    return saida


def create_work_orders_datas(asset: dict, description: str, task_type: str, subtasks: list,
                             datas: list, responsible_code: str = "", responsible_name: str = "",
                             id_responsible=None, etiqueta_ids: list = None, note: str = "",
                             tipo: dict = None, finalizar: dict = None, id_parent=None,
                             falha: dict = None) -> list:
    """Cria N OS p/ o MESMO ativo — uma por DATA de incidente. `datas` = lista de datetimes (já no
    horário escolhido; tz-aware = Brasília); se `finalizar`, cada item é uma tupla (inicial, final).
    Mesmas 3 fases do create_work_orders_bulk (tarefa → WO+responsável → etiquetas), sem parar no 1º erro.
    → lista paralela a `datas`: [{'data','ok':True,'os':{...}} | {'data','ok':False,'erro'}]."""
    if not isinstance(asset, dict) or not asset.get("id"):
        return [{"data": None, "ok": False, "erro": "Ativo inválido / sem id — recarregue os ativos."}]
    fase1 = []
    for d in (datas or []):
        if isinstance(d, (tuple, list)):                 # (inicial, final) p/ OS finalizada
            ev_dt, fim_dt = d[0], (d[1] if len(d) > 1 else None)
        else:
            ev_dt, fim_dt = d, None
        rot = ev_dt.strftime("%d/%m %H:%M") if hasattr(ev_dt, "strftime") else str(ev_dt)
        fin = {**finalizar, "final_date": fim_dt} if finalizar else None
        try:
            os_ = api.create_os_rpc(asset, description, task_type, subtasks,
                                requested_by=responsible_name, etiqueta="", note=note,
                                event_date=ev_dt, tipo=tipo, finalizar=fin, id_parent=id_parent, falha=falha)
            fase1.append({"data": rot, "ok": True, "os": os_})
        except FracttalError as e:
            fase1.append({"data": rot, "ok": False, "erro": str(e)})

    if finalizar:                                        # WO concluída já saiu da Fase 1
        if etiqueta_ids:
            for r in [x for x in fase1 if x.get("ok") and x["os"].get("id_work_order")]:
                try:
                    api.apply_labels(r["os"]["id_work_order"], etiqueta_ids)
                    r["os"]["etiquetas"] = list(etiqueta_ids)
                except FracttalError as e:
                    r["os"]["aviso"] = f"WO {r['os'].get('wo_folio')} criada, mas etiqueta falhou: {e}"
        return fase1

    os_juntar.uma_os_por_tarefa(fase1, id_responsible, responsible_name, etiqueta_ids,     # a mesma do uma-OS-por-ativo
                                id_parent=id_parent)
    return fase1


def create_inspecao_chamado(asset: dict, fabricante: str, id_responsible=None,
                            responsible_name: str = "", event_date: datetime = None,
                            prog_date: datetime = None, id_parent=None, note: str = "",
                            etiquetas=None) -> dict:
    """Cria a OS de INSPEÇÃO que alimenta um chamado de garantia.

    As subtarefas vêm do `chamado_insp_spec` (base + tipo do ativo + marca) e vão no PRÓPRIO
    payload — não existe plano cadastrado no Fracttal para isso, e nem precisa: o
    `tasks_noscheduled_react_insert` aceita a lista de subtarefas direto (é o mesmo caminho do
    tracker individual, `linkar_plano=False`).

    `event_date` = data do incidente (herdada da OS pai quando houver, decisão do Levi 29/07);
    `prog_date` = quando o técnico vai a campo. `etiquetas` = nomes; default = LABEL_INSPECAO.
    → {'id_work_order','wo_folio','n_subtarefas','etiqueta_erro'}."""
    import chamado_insp_spec as ci
    tipo_ativo = str(asset.get("tipo") or "").strip()
    subs = ci.subtarefas(tipo_ativo, fabricante)
    if not subs:
        raise FracttalError("Não há modelo de inspeção para %s / %s." % (tipo_ativo or "?",
                                                                         fabricante or "?"))
    desc = ci.titulo(asset, fabricante) if hasattr(ci, "titulo") else (
        "[%s] - Inspeção para chamado %s"
        % ((str(asset.get("description") or "").split("{")[0]).strip()[:60] or asset.get("code"),
           fabricante))
    # `plan` sintético. Dois cuidados: (1) o `create_planned_os` repassa `subtasks` CRU para o RPC,
    # então a lista tem de vir já no formato dele — daí o `_rpc_subtasks`, que é quem põe id,
    # order_number e phantom; (2) sem `id_task_type_main` a OS nasce sem tipo de tarefa, e a visão
    # COS e os filtros do histórico passam a não enxergá-la.
    plano = {"id_task": None, "subtasks": api._rpc_subtasks(subs), "description": desc,
             "tasks_types_main_description": api.TIPO_INSPECAO,
             "id_task_type_main": api.TASK_TYPE_MAIN.get(api.TIPO_INSPECAO)}
    # CLASSIFICAÇÃO Programada / Elétrica (Levi, 30/07). Sem isto a OS nascia com a classificação
    # em branco — verificado na OS 10478. Os ids são resolvidos pelo nome no catálogo do Fracttal,
    # e não fixos, porque a lista é editável lá dentro.
    _cls = api._classif_ids(ci.CLASSIF_1, ci.CLASSIF_2)
    plano.update(_cls)
    r = api.create_planned_os(asset, plano, id_responsible=id_responsible,
                          responsible_name=responsible_name, event_date=event_date,
                          prog_date=prog_date, id_parent=id_parent, descricao=desc,
                          note=note, linkar_plano=False)
    idwo = r.get("id_work_order")
    erro_lbl = ""
    nomes = list(etiquetas) if etiquetas else [api.LABEL_INSPECAO]
    ids = [i for i in (api.label_id_por_nome(n) for n in nomes) if i]
    if idwo and ids:
        try:
            api.apply_labels(idwo, ids)
        except Exception as exc:                 # a OS já existe; a etiqueta é o que pode faltar
            erro_lbl = str(exc)[:200]
    return {"id_work_order": idwo, "wo_folio": r.get("wo_folio"),
            "id_work_order_task": r.get("id_work_order_task"),
            "n_subtarefas": len(subs), "etiqueta_erro": erro_lbl,
            "aviso": r.get("aviso") or ""}                  # a OS pai que o Fracttal não gravou (o `create_planned_os` confere)


def concluir_os_analise(id_work_order, id_work_order_task=None, observacao: str = "") -> dict:
    """FECHA a OS de análise — IRREVERSÍVEL. Encerra o cronômetro (se estiver rodando), tira o
    'Atividade em execução' e conclui.

    `observacao` NÃO vai para a observação da OS: a API do Fracttal não tem método de edição de
    OS já criada (só criar/cancelar/mudar status/etiqueta/anexo). Vai para o log local, do mesmo
    jeito que o histórico de chamados — ver `chamado_log`. No dia em que houver método de escrita,
    é aqui que ele entra."""
    if not id_work_order:
        return {"ok": False, "erro": "OS sem id."}
    # 1) o cronômetro tem de estar TODO fechado. Não basta um `finalizar_execucao`: execução de
    #    outro dia que ficou pausada continua aberta e o Fracttal recusa fechar a OS (ver
    #    `fechar_execucoes_abertas`). E o erro daqui NÃO é mais engolido — era ele que fazia a
    #    conclusão falhar em silêncio, com o app dizendo que tinha dado certo.
    tid = None
    try:
        tid = id_work_order_task or api.id_tarefa_da_os(id_work_order)
    except Exception:
        tid = None
    if tid:
        try:
            fx = api.fechar_execucoes_abertas(tid)
        except Exception as exc:
            return {"ok": False, "erro": "não consegui encerrar o cronômetro: %s" % str(exc)[:200]}
        if not fx.get("ok"):
            return {"ok": False, "erro": fx.get("erro") or "cronômetro ainda aberto."}
    try:
        api.marcar_em_execucao(id_work_order, False)
    except Exception:
        pass                               # a etiqueta é cosmética; o que importa é fechar a OS
    try:
        api.concluir_os(id_work_order)
    except Exception as exc:
        return {"ok": False, "erro": str(exc)[:300]}
    # 2) confere no servidor: o `recalculate` já respondeu sucesso com a OS seguindo aberta.
    #    Sem esta releitura o app diz "concluída" e o card some — mas a OS continua lá.
    try:
        st = api.status_da_os(id_work_order)
        if st is not None and st not in api.STATUS_FECHADOS:
            return {"ok": False, "erro": "o Fracttal aceitou o comando mas a OS continua como '%s'. "
                                         "Verifique no Fracttal se falta subtarefa obrigatória ou "
                                         "permissão para fechar." % api.WO_STATUS.get(st, st)}
    except Exception:
        pass                               # falha na conferência não invalida a conclusão
    # 3) e a tarefa ficou com data de fim? Aqui o cronômetro costuma ter preenchido — mas OS de
    #    análise atribuída a outra pessoa, ou fechada sem nunca ter sido iniciada, cai no mesmo
    #    buraco da 10509. Vai como AVISO no resultado: a OS está fechada, não dá para desfazer.
    return {"ok": True, "data_fim": api.checar_data_fim(id_work_order)}


def create_performance_os_agrupada(itens: list, id_responsible=None, responsible_name: str = "",
                                   event_date: datetime = None, progresso=None,
                                   prog_date: datetime = None, etiquetas_extra=None,
                                   note_os: str = "", subtarefas_padrao=None) -> dict:
    """UMA OS com N tarefas — uma por ativo — no lugar de N OS (Levi, 21/08).

    Mesmo `itens` do `create_performance_os`, para as duas rotas comerem o mesmo prato: trocar de
    modo na tela não pode significar trocar de formato de dado.

    POR QUE NÃO REUSEI o `create_planned_os_one_wo`: ele é cru — um plano só para todos, sem
    etiqueta, sem observação por ativo, sem título, sem data programada e sem imagem. O que o
    Performance manda por ativo (`note`, `titulo`, `imagens`) sumiria em silêncio.

    O QUE SOBREVIVE à Fase 2, medido no registro do kanban (21/08): `task_note` (a observação de
    cada ativo), `description` (o título), tipo, classificação 1 e 2, criticidade e o ativo.

    O QUE NÃO SOBREVIVE, e por isso a tela avisa:
      · `id_parent` — OS pai POR ATIVO deixa de existir; a OS é uma só;
      · `initial_date`/`final_date` — a tarefa nasce sem data de início/fim. No modo de 1 OS por
        ativo isso não acontecia, porque lá o caminho é de chamada única. Quem preenche depois é o
        cronômetro de execução.

    → {'ok','folio','id_work_order','n_tarefas','n_criadas','erros','n_img_ok','img_erro','aviso'}
    """
    itens = [it for it in (itens or []) if isinstance(it.get("asset"), dict) and it["asset"].get("id")]
    if not itens:
        return {"ok": False, "erro": "Nenhum ativo selecionado.", "n_tarefas": 0, "n_criadas": 0}

    # ── Fase 1: uma tarefa PENDENTE por ativo, cada uma com o SEU título e a SUA observação ──
    cache, id_tasks, erros, por_task, dur_de = {}, [], [], {}, {}
    plano_de = {}                    # id(item) → descrição do plano, p/ a Fase 5 saber a aba
    for i, it in enumerate(itens):
        a = it["asset"]
        try:
            k = it.get("plano_id_task")
            if k not in cache:
                # as subtarefas extras (ou o padrão do Nexus) entram UMA vez, junto do cache — ver com_subtarefas_extra
                cache[k] = api._plano_da_performance(k, it.get("plano_id_item"), subtarefas_padrao)
            plan = cache[k]
            plano_de[id(it)] = plan.get("description")
            nome = (it.get("titulo") or "").strip() or \
                api.perf_os_nome(a, it.get("base") or api.plano_base_nome(plan.get("description")))
            r = api.create_planned_os(a, plan, event_date=event_date, prog_date=prog_date,
                                  to_work_order=False, descricao=nome,
                                  note=it.get("note") or "", linkar_plano=it.get("linkar", True))
            idt = r.get("id_task")
            if idt:
                id_tasks.append(idt)
                por_task[idt] = it            # p/ casar as imagens depois, pelo ativo
                dur_de[idt] = r.get("duracao")
            else:
                erros.append("%s: tarefa não criada" % (a.get("code") or "?"))
        except SessionExpired:
            raise
        except Exception as e:
            erros.append("%s: %s" % (a.get("code") or "?", str(e)[:120]))
        if progresso:
            progresso(i + 1, len(itens))

    if not id_tasks:
        return {"ok": False, "erro": "Nenhuma tarefa criada: " + "; ".join(erros[:3]),
                "n_tarefas": len(itens), "n_criadas": 0, "erros": erros}

    # ── Fase 2: junta TODAS numa OS só (a fase 2 de todos os caminhos, `os_juntar`), com as etiquetas (Performance + as extras) ──
    # OS pai: UMA para a OS inteira (no agrupado não existe pai por ativo). Pega o 1º `os_pai`
    # preenchido — a tela manda o mesmo valor em todos os itens. A busca pelo número só vai depois de o kanban trazer as
    # tarefas, na hora de inserir a OS (o `id_parent` do juntar é uma função): com o kanban fora a OS nem sai.
    folio_pai = next((str(it.get("os_pai") or "").strip() for it in itens
                      if str(it.get("os_pai") or "").strip()), "")
    pai: dict = {}

    def _procurar_pai():
        try:
            for c in api.buscar_os_pai(folio_pai, limit=20):
                if str(c.get("folio")).strip() == folio_pai:
                    pai["id"] = c.get("id"); break
        except FracttalError:
            pai["id"] = None
        return pai.get("id")
    lbls = [l for l in [api._label_performance_id()] +
            [api.label_id_por_nome(n) for n in (etiquetas_extra or [])] if l]
    jun = os_juntar.juntar_em_os(id_tasks, dur_de, id_responsible, responsible_name,
                                 id_parent=_procurar_pai if folio_pai else None, note=note_os,
                                 etiqueta_ids=lbls or None, frases=os_juntar.FRASES_PERFORMANCE)
    if "id_work_order" not in jun:                       # a OS não saiu: as tarefas ficam pendentes no kanban do Fracttal
        return {"ok": True, "folio": None, "n_tarefas": len(itens), "n_criadas": len(id_tasks),
                "erros": erros, "aviso": jun["aviso"]}
    idwo, folio = jun["id_work_order"], jun["wo_folio"]
    avisos = []
    if folio_pai and not pai.get("id"):
        avisos.append("não achei a OS pai %s — a OS foi criada sem vínculo" % folio_pai)
    if jun["nao_entraram"]:
        avisos.append("%d tarefa(s) não entraram na OS" % jun["nao_entraram"])
    if jun.get("aviso"):                                 # a etiqueta que falhou
        avisos.append(jun["aviso"])

    # ── Fase 4: imagens. O work_order_insert devolve só o id da OS, não o de cada tarefa — então
    # releio as tarefas e caso pelo ATIVO (id_item), que é o único elo confiável. ──
    n_img_ok, img_erro = 0, []
    quer_img = {id(it): it for it in itens if it.get("imagens")}
    if idwo and quer_img:
        try:
            rt = api._rpc_call(api.RPC_WO_TASKS_NEW, {"filter": [], "sort": [], "page": 1, "limit": 200,
                                              "start": 0, "is_tree": False, "node": None,
                                              "id_work_order": idwo})
            tarefas = (rt.get("data") if isinstance(rt, dict) else rt) or []
        except FracttalError as e:
            tarefas = []
            img_erro.append("não consegui ler as tarefas p/ anexar: %s" % str(e)[:80])
        por_item = {}
        for t in tarefas:
            if isinstance(t, dict) and t.get("id_item") is not None:
                por_item.setdefault(t["id_item"], t.get("id"))
        for it in itens:
            tid = por_item.get(it["asset"].get("id"))
            for img in (it.get("imagens") or []):
                if not tid:
                    img_erro.append("%s: não achei a tarefa da OS p/ anexar" % it["asset"].get("code"))
                    continue
                try:
                    api.attach_imagem_os(idwo, tid, img.get("bytes"), img.get("nome") or "imagem.png")
                    n_img_ok += 1
                except Exception as e:
                    img_erro.append("%s: %s" % (it["asset"].get("code"), str(e)[:80]))
    # ── Fase 5: as ocorrências de tickets, uma POR ATIVO (Levi, 10/09) ──
    # "cada ativo será uma tarefa, isso não impede de reconhecer cada ativo como ticket". Até
    # aqui este caminho não criava ocorrência nenhuma, e o silêncio era igual ao do caminho de
    # N OS — ninguém percebia que agrupar significava perder o registro. As N linhas apontam
    # todas para o MESMO número de OS, que é o que amarra o lote no diário.
    tickets = []
    for it in itens:
        tk = api.nascer_ticket(it, it["asset"], plano_de.get(id(it)), folio, event_date)
        if tk.get("aba"):
            tickets.append(tk)
        if tk.get("aviso_os"):
            avisos.append("%s: %s" % (it["asset"].get("code") or "?", tk["aviso_os"]))
    if erros:
        avisos.append("%d ativo(s) falharam: %s" % (len(erros), "; ".join(erros[:2])))
    return {"ok": True, "folio": folio, "id_work_order": idwo,
            "n_tarefas": len(itens), "n_criadas": len(id_tasks) - jun["nao_entraram"], "erros": erros,
            "n_img_ok": n_img_ok, "img_erro": img_erro, "tickets": tickets,
            "aviso": " · ".join(avisos) or None}


import api  # noqa: E402 — no fim: o `api` importa este módulo

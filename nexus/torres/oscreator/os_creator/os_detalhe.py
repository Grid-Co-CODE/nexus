"""os_detalhe.py: a OS aberta no card.

O cabeçalho, as tarefas, as subtarefas com as respostas, a solicitação de origem, a OS pai (`buscar_os_pai`), quem foi
atribuído, e a OS vista para clonar (`get_os_para_clonar`). É o que o card, o PDF e a Clonagem leem de UMA OS.

Saiu do `api.py` em 31/10/2026 (etapa 5.3 do canto central, "o que sobra do api.py"): mudou só o lugar, o código é o mesmo. O
`api.py` segue expondo os mesmos nomes (`api.X`), porque a ponte, as rotas e os testes chamam e TROCAM `api.X` pelo nome. Por
isso toda função que este módulo chama, dele ou de fora (o `api._rpc_call`, o que também saiu para outro módulo), e todo número
ajustável (um prazo, um teto) vão pelo `api.`, e enxergam a troca; só as outras constantes e o estado daqui são usados direto. O
módulo termina com `import api`: o `api` o importa no fim do arquivo (a fachada), e só precisa dele na hora da chamada."""

from fracttal_erro import FracttalError


# Campos onde o Fracttal pode guardar a RESPOSTA de uma subtarefa (o nome varia por tipo/versão).
_FORM_RESP_KEYS = ("value", "response", "result", "answer", "text_value",
                   "task_form_item_value", "value_description", "observation")


# Verificação (id_task_form_item_type=4) guarda a resposta como 1/2/3 no 'value'.
_VERIF_MAP = {"1": "Aprovado", "2": "Alerta", "3": "Falhou"}


def _form_item_resposta(it: dict) -> str:
    """Melhor esforço p/ extrair a resposta dada numa subtarefa (o nome do campo varia no Fracttal)."""
    verif = it.get("id_task_form_item_type") == 4
    for k in _FORM_RESP_KEYS:
        v = it.get(k)
        if v not in (None, "", "None", "null", "NaN"):
            v = str(v).strip()
            if verif and v in _VERIF_MAP:            # Verificação: 1/2/3 → Aprovado/Alerta/Falhou
                return _VERIF_MAP[v]
            return v
    if verif:                                         # sem value → tenta o 'done'
        dn = str(it.get("done")).lower()
        if dn == "true":
            return "Aprovado"
        if dn == "false":
            return "Não / pendente"
    return ""                                         # Texto/outros sem valor → frontend mostra "(sem resposta)"


def _personnel_nome_por_id() -> dict:
    """Mapa {id_personnel: nome} do pessoal ativo, para resolver o atribuído no card. Desde 31/10/2026 (etapa 4 do canto
    central) do catálogo de pessoas (`catalogos.nome_por_id`): a cópia de antes nunca vencia, e a pessoa nova não tinha nome
    no card até o reinício. Sem o catálogo (o Fracttal fora), o mapa vazio, como antes."""
    import catalogos
    try:
        return catalogos.nome_por_id()
    except FracttalError:
        return {}


# campos de NOME do atribuído/responsável que a resposta do Fracttal pode trazer (shape variável)
_ATRIB_NOME_KEYS = ("personnel_description", "assigned_user_name", "responsible_description",
                    "id_assigned_user_description", "name_assigned_user", "accounts_name")


def _nome_atribuido(fontes) -> str:
    """1º campo de NOME não-vazio em qualquer das fontes (tarefas/cabeçalho da WO). '' se nenhum."""
    for src in fontes:
        if not isinstance(src, dict):
            continue
        for k in _ATRIB_NOME_KEYS:
            v = str(src.get(k) or "").strip()
            if v and v.lower() != "none":
                return v
    return ""


def _ids_atribuido(fontes) -> list:
    """IDs do atribuído/responsável (id_assigned_user/id_responsible) presentes nas fontes."""
    ids = []
    for src in fontes:
        if not isinstance(src, dict):
            continue
        for k in ("id_assigned_user", "id_responsible"):
            iv = src.get(k)
            if iv not in (None, "", 0) and iv not in ids:
                ids.append(iv)
    return ids


def _solicitacao_da_os(id_work_order, det, t0) -> str:
    """Nº (id_code) da solicitação de serviço ligada a esta OS. Tenta um código direto no cabeçalho/
    tarefa; senão consulta requests_list filtrando por id_work_order (confere o vínculo). '' se nenhuma."""
    for src in (det, t0):
        if not isinstance(src, dict):
            continue
        for k in ("request_code", "requests_id_code", "id_code_request", "code_request"):
            v = src.get(k)
            if v not in (None, "", 0):
                return str(v)
    if not id_work_order:
        return ""
    try:
        res = api._rpc_call(api.RPC_REQ_LIST, {"filter": [{"operator": "=", "property": "id_work_order",
            "value": id_work_order}], "page": 1, "limit": 5, "start": 0})
    except FracttalError:
        return ""
    data = res.get("data") if isinstance(res, dict) else res
    for r in (data if isinstance(data, list) else []):
        if (isinstance(r, dict) and str(r.get("id_work_order")) == str(id_work_order)
                and r.get("id_code") not in (None, "", 0)):
            return str(r.get("id_code"))
    return ""


RPC_WO_PARENTS = "tasks.work_orders_parents_list"


def buscar_os_pai(termo="", limit=50) -> list:
    """Busca OSs candidatas a PAI por número (wo_folio, filtro 'like'). Vazio = primeiras da lista.
    → [{'id','folio','descricao'}] — 'id' é o id_parent a mandar na criação (NÃO é o nº)."""
    t = str(termo or "").strip()
    filtro = [{"operator": "like", "property": "wo_folio", "value": t, "condition": "or"}] if t else []
    try:
        r = api._rpc_call(RPC_WO_PARENTS, {"filter": filtro, "sort": [], "page": 1, "limit": limit,
                                       "start": 0, "is_tree": False, "node": None})
    except FracttalError:
        return []
    data = r.get("data") if isinstance(r, dict) else r
    out = []
    for w in (data if isinstance(data, list) else []):
        if not isinstance(w, dict):
            continue
        idp = w.get("id")
        if idp is None:
            continue
        folio = w.get("wo_folio") or w.get("folio") or ""
        desc = str(w.get("description") or w.get("tasks_description")
                   or w.get("items_description") or "").split("{")[0].strip()[:80]
        # 'criada' entra porque a aba Tickets precisa da data de criação da OS para preencher
        # 'Início do chamado pela Grid Co.' (Levi, 31/08: é a data em que a Grid notificou).
        # Vem no mesmo payload — buscar por OS depois seria uma chamada por resultado.
        # 'description' deste RPC vem sendo o PRÓPRIO número (medido: OS 11658 -> "11658"),
        # então a lista mostraria o número duas vezes. O que identifica de verdade é quem está
        # com a OS e a data do serviço.
        out.append({"id": idp, "folio": str(folio),
                    "descricao": "" if desc.strip() == str(folio).strip() else desc,
                    "responsavel": str(w.get("personnel_description") or "").strip(),
                    "data": api.fmt_data_br(w.get("date_maintenance"), com_hora=False),
                    "criada": str(w.get("creation_date") or "")[:19]})
    return out


def _cabecalho_os(id_work_order) -> dict:
    """O cabeçalho da WO (work_order_details_new): etiquetas, quem criou, OS pai. {} se o Fracttal recusar."""
    try:
        rd = api._rpc_call(api.RPC_WO_DETAILS, {"id": id_work_order, "get_iso_codes": False})
    except FracttalError:
        return {}
    det = rd.get("data") if isinstance(rd, dict) else rd
    return det[0] if isinstance(det, list) and det else (det if isinstance(det, dict) else {})


def _folio_da_os_pai(pai_id) -> str:
    """O nº (wo_folio) da OS mãe pelo id dela. '' se o Fracttal recusar."""
    return str(api._cabecalho_os(pai_id).get("wo_folio") or "").strip()


def _juntos(tarefas: dict) -> dict:
    """{nome: (função, *args)} → {nome: resultado}, as funções ao mesmo tempo (no contexto da pessoa, ver
    `_ExecutorComContexto`). Uma só roda aqui mesmo, sem thread. Erro sobe como subiria na chamada direta."""
    if not tarefas:
        return {}
    if len(tarefas) == 1:
        (nome, (fn, *args)), = tarefas.items()
        return {nome: fn(*args)}
    with api._ExecutorComContexto(max_workers=len(tarefas)) as ex:
        futuros = {nome: ex.submit(fn, *args) for nome, (fn, *args) in tarefas.items()}
        return {nome: f.result() for nome, f in futuros.items()}


def _campo_de_nota(t: dict, k: str) -> str:
    v = str((t or {}).get(k) or "").strip()
    return "" if v.lower() == "none" else v


def juntar_notas(tasks: list) -> list[str]:
    """A nota que o card mostra: a `note` e a `task_note` de cada tarefa, sem repetir. A que já está DENTRO de outra não
    aparece de novo (prova no Fracttal de 05/11/2026, OS 18591 de TESTE - PA: o comentário da Engenharia grava a `note`
    com a nota de entrada mais a linha nova, e a `task_note` segue com a de entrada; o card mostrava a de entrada duas
    vezes)."""
    notas: list[str] = []
    for t in tasks:
        for k in ("note", "task_note"):
            v = api._campo_de_nota(t, k)
            if not v or any(v in x for x in notas):
                continue
            notas = [x for x in notas if x not in v] + [v]
    return notas


def get_os_detalhes(id_work_order) -> dict:
    """Detalhe de UMA OS p/ o histórico. → {'folio','descricao','tipo','event_date','responsavel',
    'notas','subtarefas':[{'descricao','feito','tipo','resposta','id_tarefa','id_form_item'}],'tarefas':[…]}.
    event_date/notas da tarefa; subtarefas (descrição + tipo + resposta dada) vêm dos form items, uma vez cada,
    agrupadas pela tarefa na ordem de `tarefas` (ver `ordem`); responsavel = atribuído da OS.

    Os pedidos vão em DUAS LEVAS PARALELAS (Levi, 08/10/2026: "a tela que abre quando clica na OS está demorando um
    pouco para carregar"). Eram até cinco, um atrás do outro. Tarefas, subtarefas e cabeçalho não dependem um do
    outro e vão juntos; a solicitação, a OS pai e o motivo do cancelamento dependem só deles e vão juntos depois.
    São os mesmos pedidos de antes, e a resposta é a mesma. Com o Fracttal falso a 300 ms por pedido, o card caiu de
    1,5 s para 0,6 s.

    Dentro de `enxuta("vinculos")` a 2ª leva fica de fora (solicitação, OS pai e cancelamento: '' nos três). Serve a
    quem não mostra esses campos: a tela do Acompanhamento de chamados e a conferência antes de gravar o ticket. São
    2 pedidos a menos na cota da empresa por abertura."""
    vinculos = not api._cortado("vinculos")
    def _lista(metodo, params):
        r = api._rpc_call(metodo, params)
        d = r.get("data") if isinstance(r, dict) else r
        return d if isinstance(d, list) else []
    # o card lê na hora (e guarda, para a contagem de anexos que vem logo depois usar a mesma leitura)
    lev1 = api._juntos({"tasks": (api._leitura_da_os, api.RPC_WO_TASKS, id_work_order, {"id_work_order": id_work_order, "sort": []},
                              False),
                    "items": (api._leitura_da_os, api.RPC_WO_FORMIT, id_work_order, {"id_work_order": id_work_order}, False),
                    "det": (api._cabecalho_os, id_work_order)})
    tasks, items = lev1["tasks"], lev1["items"]
    t0 = tasks[0] if tasks else {}
    notas = api.juntar_notas(tasks)
    # A ORDEM das subtarefas é a da TAREFA e, dentro dela, o `order_number` (Levi, 08/10/2026: "quando a OS tem mais que
    # uma tarefa está duplicando as subtarefas"). O `order_number` recomeça em 1 em cada tarefa (REST, OS 8709: 13
    # tarefas, cada uma de 1 a n), e a ordem só por ele intercalava as tarefas: na OS de 8 tarefas com o mesmo checklist
    # (a coleta de geração, uma por inversor), a 1ª pergunta saía 8 vezes seguidas e depois a 2ª. Subtarefa de tarefa
    # que não veio vai para o fim, sem sumir. E cada tarefa e cada form item entram UMA vez, pelo id: o REST não repete,
    # o RPC daqui não deu para conferir, e a barra e o "X de Y" do Concluir contam esta lista.
    ordem = {}
    for i, t in enumerate(tasks):
        if t.get("id") is not None:
            ordem.setdefault(t.get("id"), i)
    subtarefas, vistos = [], set()
    for it in sorted(items, key=lambda x: (ordem.get(x.get("id_work_order_task"), len(tasks)),
                                           x.get("order_number") or 0)):
        fid = it.get("id_work_orders_tasks_form_items")
        if fid is not None and fid in vistos:
            continue
        vistos.add(fid)
        desc = str(it.get("description") or "").strip()
        if not desc:
            continue
        tid = it.get("id_task_form_item_type")
        tipo = (api._FORM_ITEM_TYPE_DESC.get(tid)
                or str(it.get("task_form_item_type_description") or "").strip() or "—")
        subtarefas.append({"descricao": desc, "feito": str(it.get("done")).lower() == "true",
                           "tipo": tipo, "resposta": api._form_item_resposta(it),
                           # a QUAL tarefa esta subtarefa pertence. Numa OS de preventiva (a 8709 tem
                           # 13 tarefas e 45 subtarefas) a lista corrida não diz nada — é este id que
                           # deixa o card filtrar por tarefa. Casa com `id` da tarefa (join conferido
                           # ao vivo: 45/45 sem órfã).
                           "id_tarefa": it.get("id_work_order_task"),
                           # os dois ids que a ESCRITA precisa (21/09): sem eles a tela so consegue
                           # LER o checklist — e o pedido era justamente poder preenche-lo na hora
                           # de concluir, em vez de mandar a pessoa para o Fracttal.
                           "id_form_item": it.get("id_work_orders_tasks_form_items"),
                           "tipo_id": tid})
    code0 = (t0.get("code_item") or "").strip() or api._extrai_code(str(t0.get("items_description") or ""))
    ativo0 = (str(t0.get("items_description") or "").split("{")[0]).strip()[:60] or code0
    # cabeçalho da WO (sempre, na 1ª leva) → responsável + quem criou + solicitação ligada
    det = lev1["det"]
    resp = api._nome_atribuido(tasks) or api._nome_atribuido([det])
    ids = [] if resp else api._ids_atribuido(list(tasks) + [det])
    criado_por = str(det.get("created_by") or det.get("creation_user")
                     or det.get("accounts_name") or t0.get("created_by") or "").strip()
    # OS pai (id_parent_wo → folio da OS mãe). Só ~15% das OS têm; resolve o número só quando existe.
    pai_id = det.get("id_parent_wo") or t0.get("id_parent_wo")
    # CANCELAMENTO: só busca quando a OS está cancelada (status 4). É uma chamada REST a mais, e
    # cobrá-la em toda abertura de card seria pagar por 96% de OS que não precisam.
    cancelada = (det.get("id_status_work_order") or t0.get("id_status_work_order")) == 4
    # a 2ª leva: o que depende do cabeçalho e da tarefa, tudo ao mesmo tempo
    lev2 = {}
    if ids:
        lev2["nomes"] = (api._personnel_nome_por_id,)
    if vinculos:
        lev2["solic"] = (api._solicitacao_da_os, id_work_order, det, t0)
        if pai_id:
            lev2["pai"] = (api._folio_da_os_pai, pai_id)
        if cancelada:
            lev2["canc"] = (api.cancelamento_da_os, t0.get("wo_folio"))
    lev2 = api._juntos(lev2)
    if ids:
        nm = lev2["nomes"] or {}
        nomes = [nm.get(i) for i in ids if nm.get(i)]
        resp = " / ".join(dict.fromkeys(nomes)) if nomes else ""
    solic = lev2.get("solic", "")
    os_pai = lev2.get("pai", "")
    # data de conclusão (OS finalizada) — nomes variam; tenta os prováveis na tarefa e no cabeçalho
    data_fim = None
    for src in (t0, det):
        for k in ("final_date", "date_end", "end_date", "real_final_date", "finished_date",
                  "date_finished", "closing_date"):
            v = src.get(k)
            if v not in (None, "") and str(v).lower() != "none":
                data_fim = v
                break
        if data_fim:
            break
    # tipo/classificação/criticidade (rodapé read-only do card, estilo COS)
    _crit_pt = {v: k for k, v in api.CRITICIDADES}          # {1:'Muito alto',…,3:'Médio',…}
    _c1 = str(t0.get("tasks_types_description") or "").strip()
    _c2 = str(t0.get("tasks_types_2_description") or "").strip()
    classif = " / ".join([x for x in (_c1, _c2) if x])
    criticidade = _crit_pt.get(t0.get("id_priorities"), "")
    # cada TAREFA da OS (a preventiva mensal abre uma por sistema: cabine, medidor, módulos…).
    # Só o `t0` ia para o card antes — numa OS de 13 tarefas isso escondia 12.
    tarefas = [{"id": t.get("id"),
                "titulo": str(t.get("tasks_description") or "").strip(),
                "ativo": (str(t.get("items_description") or "").split("{")[0]).strip()[:60],
                "tipo": str(t.get("tasks_types_main_description") or "").strip(),
                "classif": " / ".join([x for x in (str(t.get("tasks_types_description") or "").strip(),
                                                   str(t.get("tasks_types_2_description") or "").strip()) if x]),
                "criticidade": _crit_pt.get(t.get("id_priorities"), ""),
                "programada": api._primeiro(t, "date_maintenance", "cal_date_maintenance"),
                "inicio": api._primeiro(t, "initial_date"),
                "fim": api._primeiro(t, "final_date"),
                "duracao": str(t.get("duration") or "").strip(),
                "gatilho": api.decodifica_gatilho(t.get("trigger_description")),
                "nota": str(t.get("task_note") or t.get("note") or "").strip()}
               for i, t in enumerate(tasks)
               if t.get("id") is None or ordem.get(t.get("id")) == i]     # a mesma tarefa uma vez (ver `ordem`)
    canc = lev2.get("canc") or {"motivo": "", "nota": ""}
    return {"folio": t0.get("wo_folio"),
            "cancel_motivo": canc["motivo"], "cancel_nota": canc["nota"],
            "descricao": str(t0.get("tasks_description") or "").strip(),
            "tipo": str(t0.get("tasks_types_main_description") or "").strip(),
            "classif": classif,
            "criticidade": criticidade,
            "event_date": t0.get("event_date"),
            "data_fim": data_fim,
            "responsavel": resp,
            "criado_por": criado_por,
            "solicitacao": solic,
            "os_pai": os_pai,
            "os_pai_id": pai_id or None,
            "notas": "\n".join(notas),
            # os dois campos crus da 1ª tarefa: o `editar_nota_os` grava só a `note`, e quem escreve na nota parte dela
            # (ou, na 1ª vez, da `task_note` com que a OS nasceu), nunca da junção acima (05/11/2026, a ponte da Engenharia)
            "nota_gravada": api._campo_de_nota(t0, "note"),
            "nota_da_tarefa": api._campo_de_nota(t0, "task_note"),
            "subtarefas": subtarefas,
            "tarefas": tarefas,
            "etiquetas": [{"id": l.get("id"), "nome": l.get("description"), "cor": l.get("color")}
                          for l in (det.get("labels") or []) if isinstance(l, dict) and l.get("id") is not None],
            "code": code0, "ativo": ativo0,
            # a usina e a data de criação no card (Levi, 05/11/2026: "as vezes clico na OS sem contexto e não sei que usina
            # é. adicione também data de criação da OS")
            "usinas": api._usinas_da_os(tasks),
            "criada": det.get("creation_date") or t0.get("creation_date"),
            # o status da OS (1..4, `WO_STATUS`): o PDF da OS diz em que pé ela está (19/10/2026)
            "status_id": det.get("id_status_work_order") or t0.get("id_status_work_order")}


def _usinas_da_os(tasks: list) -> list:
    """As usinas dos ativos das tarefas, na ordem delas e sem repetir: a mesma Usina (nome curto) da coluna do Histórico, pelo
    código do ativo no catálogo central em memória. Sem o catálogo, nenhuma: o card não espera a carga dos ativos."""
    cat = api.ativos_central.atual()
    local = cat.local_por_codigo if cat is not None else {}
    usinas = []
    for t in tasks or []:
        cod = str(t.get("code_item") or "").strip() or api._extrai_code(str(t.get("items_description") or ""))
        u = ((local.get(cod) if cod else None) or ("", "", ""))[1]
        if u and u not in usinas:
            usinas.append(u)
    return usinas


def get_os_detalhes_por_folio(folio) -> dict:
    """Detalhe da OS pelo NÚMERO (wo_folio) em vez do id — usado pelo clonador do COS.
    None se o número não existir."""
    idwo = api._wo_id_por_folio(folio)
    if not idwo:
        return None
    d = api.get_os_detalhes(idwo)
    d["id_work_order"] = idwo
    return d


def get_os_para_clonar(id_work_order) -> dict:
    """Lê uma OS p/ CLONAR — TODAS as tarefas (a OS pode ter vários ativos). →
    {'folio','tarefas':[{'code','asset'(dict do catálogo ou None),'tipo','descricao',
     'subtarefas':[str],'notas'}],'etiqueta_ids':[int],'notas','n_sem_ativo'}.
    Cada tarefa traz seu próprio ativo (resolvido do code_item/items_description), tipo,
    descrição e subtarefas (form items agrupados por id_work_order_task = id da tarefa)."""
    rt = api._rpc_call(api.RPC_WO_TASKS, {"id_work_order": id_work_order, "sort": []})
    tasks = rt.get("data") if isinstance(rt, dict) else rt
    tasks = tasks if isinstance(tasks, list) else []
    rf = api._rpc_call(api.RPC_WO_FORMIT, {"id_work_order": id_work_order})
    items = rf.get("data") if isinstance(rf, dict) else rf
    items = items if isinstance(items, list) else []
    # subtarefas (form items) agrupadas por tarefa (id_work_order_task == id da tarefa).
    # Guarda o TIPO original de cada uma (id_task_form_item_type etc.) p/ o clone preservar
    # Verificação/Texto/etc. em vez de rebaixar tudo p/ Texto.
    subs_por_tarefa = {}
    for it in sorted(items, key=lambda x: x.get("order_number") or 0):
        d = str(it.get("description") or "").strip()
        if not d:
            continue
        subs_por_tarefa.setdefault(it.get("id_work_order_task"), []).append({
            "description": d,
            "id_task_form_item_type": it.get("id_task_form_item_type"),
            "task_form_item_type_description": it.get("task_form_item_type_description"),
            "id_task_form_item_group": it.get("id_task_form_item_group"),
            "task_form_item_group_description": it.get("task_form_item_group_description"),
            "is_required": bool(it.get("is_required")),
            "attachments_required": bool(it.get("attachments_required")),
            "dropdown_options": it.get("dropdown_options"),
        })
    folio = None
    tarefas = []
    notas_os = []
    n_sem_ativo = 0
    for t in tasks:
        folio = folio or t.get("wo_folio")
        code = (t.get("code_item") or "").strip() or api._extrai_code(str(t.get("items_description") or ""))
        asset = api._asset_by_code(code) if code else None
        if asset is None:
            n_sem_ativo += 1
        tipo = str(t.get("tasks_types_main_description") or "").strip()
        notas_t = []
        for k in ("note", "task_note"):
            v = str(t.get(k) or "").strip()
            if v and v.lower() != "none" and v not in notas_t:
                notas_t.append(v)
            if v and v.lower() != "none" and v not in notas_os:
                notas_os.append(v)
        subt = subs_por_tarefa.get(t.get("id")) or subs_por_tarefa.get(t.get("id_work_order_task")) or []
        tarefas.append({
            "code": code, "asset": asset,
            "tipo": tipo if tipo in api.TASK_TYPE_MAIN else "Corretiva",
            # As DUAS classificações, pelo NOME (Levi, 30/08 — a OS clonada nascia sem elas).
            # Vêm como texto porque é o texto que o RPC devolve de forma confiável: os campos
            # `id_task_type`/`id_task_type_2` chegam NULOS ao ler a OS de origem. Quem converte
            # nome→id é o `_classif_ids` na hora de criar, resolvendo no catálogo vivo — id fixo
            # quebraria, já que a lista é editável dentro do Fracttal.
            "classif_1": str(t.get("tasks_types_description") or "").strip(),
            "classif_2": str(t.get("tasks_types_2_description") or "").strip(),
            "descricao": str(t.get("tasks_description") or "").strip(),
            "ativo_nome": (str(t.get("items_description") or "").split("{")[0]).strip()[:60] or code,
            "subtarefas": subt, "notas": "\n".join(notas_t),
            "event_date_orig": t.get("event_date"),        # data programada original (ISO UTC), p/ prefill
            # o tempo da tarefa de origem (o PCM, 30/10/2026: o clone nascia com os 10 min do `create_os_rpc`)
            "duracao": api._segundos(t.get("duration")),
        })
    etiqueta_ids = []
    try:                                              # etiquetas vêm do cabeçalho da WO
        rd = api._rpc_call(api.RPC_WO_DETAILS, {"id": id_work_order, "get_iso_codes": False})
        det = rd.get("data") if isinstance(rd, dict) else rd
        det = det[0] if isinstance(det, list) and det else (det if isinstance(det, dict) else {})
        etiqueta_ids = [l.get("id") for l in (det.get("labels") or [])
                        if isinstance(l, dict) and l.get("id") is not None]
    except FracttalError:
        pass
    return {"folio": folio, "tarefas": tarefas, "etiqueta_ids": etiqueta_ids,
            "notas": "\n".join(notas_os), "n_sem_ativo": n_sem_ativo}


import api  # noqa: E402 — no fim: o `api` importa este módulo

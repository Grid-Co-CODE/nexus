"""os_planos.py: os planos (modelos de tarefa) do Fracttal.

Os planos de um ativo e o detalhe de cada um (as subtarefas, o tempo, o tipo), os planos da Performance, as subtarefas que o app
acrescenta ao plano, a contagem de subtarefas e o tempo de cada plano, e os modelos da Clonagem ("Atualizar do modelo"). O
guardado por ativo é do `catalogos_planos.py` (etapa 4), que chama `api.ler_planos_do_ativo`.

Saiu do `api.py` em 31/10/2026 (etapa 5.3 do canto central, "o que sobra do api.py"): mudou só o lugar, o código é o mesmo. O
`api.py` segue expondo os mesmos nomes (`api.X`), porque a ponte, as rotas e os testes chamam e TROCAM `api.X` pelo nome. Por
isso toda função que este módulo chama, dele ou de fora (o `api._rpc_call`, o que também saiu para outro módulo), e todo número
ajustável (um prazo, um teto) vão pelo `api.`, e enxergam a troca; só as outras constantes e o estado daqui são usados direto. O
módulo termina com `import api`: o `api` o importa no fim do arquivo (a fachada), e só precisa dele na hora da chamada."""

import uuid
from fracttal_erro import FracttalError


RPC_TASK_EVENTS = "tasks.task_events_list"


def get_task_plans(id_item, id_group_task=None) -> list:
    """Planos de tarefa (eventos programados) de um ativo → [{id_task, description}].
    São os MPS/MPA/MPM/Handover que o Fracttal oferece p/ o ativo. PARSE DEFENSIVO — a estrutura
    exata da resposta ainda será confirmada (ajustar os campos quando vier a captura real)."""
    if not id_item:
        return []
    r = api._rpc_call(RPC_TASK_EVENTS, {"filter": [], "sort": [], "page": 1, "limit": 200, "start": 0,
                                    "is_tree": False, "node": None,
                                    "id_item": id_item, "id_group_task": id_group_task})
    data = r.get("data") if isinstance(r, dict) else r
    out = []
    for d in (data if isinstance(data, list) else []):
        if not isinstance(d, dict):
            continue
        idt = d.get("id_task") if d.get("id_task") is not None else d.get("id")
        desc = (d.get("description") or d.get("tasks_description") or d.get("task_description")
                or d.get("code") or "")
        if idt is not None:
            out.append({"id_task": idt, "description": str(desc).strip() or f"Plano {idt}",
                        "raw": d})
    return out


RPC_TASK_DETAILS = "tasks.tasks_details"


def _find_subtasks(plan: dict) -> list:
    """Acha a lista de subtarefas (form items) na resposta do tasks_details (shape variável)."""
    if not isinstance(plan, dict):
        return []
    cands = ["subtasks", "task_form_items", "tasks_form_items", "form_items", "submodules", "items"]
    for k in cands + list(plan.keys()):
        v = plan.get(k)
        if isinstance(v, list) and v and isinstance(v[0], dict) and "id_task_form_item_type" in v[0]:
            return v
    return []


def get_plan_details(id_task, id_item) -> dict:
    """Detalhe do plano (subtarefas + tipo/classif + descrição + duração) p/ montar a OS planejada.
    Parse DEFENSIVO do tasks_details (estrutura exata a confirmar ao vivo)."""
    r = api._rpc_call(RPC_TASK_DETAILS, {"page": 1, "limit": 200, "start": 0, "append": True,
        "id_task": id_task, "include_submodules_data": True, "is_from_unplanned": True, "id_item": id_item})
    data = r.get("data") if isinstance(r, dict) else r
    plan = data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else {})
    if not isinstance(plan, dict):
        plan = {}
    return {"id_task": id_task,
            "description": plan.get("description") or plan.get("task_description") or "",
            "id_task_type_main": plan.get("id_task_type_main"),
            "id_task_type": plan.get("id_task_type"),
            "id_task_type_2": plan.get("id_task_type_2"),
            "tasks_types_main_description": plan.get("tasks_types_main_description") or "",
            "tasks_types_description": plan.get("tasks_types_description") or "",
            "tasks_types_2_description": plan.get("tasks_types_2_description") or "",
            "duration": int(plan.get("duration") or 900),
            "id_priorities": plan.get("id_priorities"),          # criticidade do plano (se vier)
            "subtasks": api._find_subtasks(plan), "raw": plan}


# Planos de PERFORMANCE (aparecem SÓ na aba Performance; escondidos no PCM). Casados por trecho
# distintivo do nome (os planos do Levi não têm a palavra "performance" no nome). Para novos planos:
# ou inclua "performance" no nome (auto), ou acrescente o trecho aqui.
_PERF_PLANOS = (
    "coleta de dados de geracao",
    "inspecao geral do inversor",
    "recomposicao de string",
    "verificacao de tracker parado",
)

# ── Subtarefas que o APP acrescenta ao plano na hora de criar a OS ───────────────────────────
# Sugestão da equipe, trazida pelo Levi em 31/08: "muitas vezes o técnico não comenta, aí não
# fica claro se o tracker voltou ou não, e qual era a causa raiz — se motor, TCU ou outro ponto".
# O plano do Fracttal ([Grid Co.] - Verificação de Tracker Parado) pergunta se o tracker ESTÁ
# parado e os números de série, mas não pergunta como a atividade TERMINOU. Sem isso, quem lê a
# OS depois não sabe dizer se o problema foi resolvido.
#
# Ficam AQUI, e não no plano do Fracttal, porque o plano é editado por outra área e vale para
# quem cria OS por fora do app também — mexer nele seria uma mudança de configuração
# compartilhada. Aqui é reversível e só afeta o que sai desta ferramenta.
#
# Tipos: 2 = BOOLEAN (Sim/Não), 1 = TEXT. Nenhuma exige anexo (`attachments_required`), ao
# contrário das do plano: exigir foto para responder "voltou a operar?" travaria o fechamento.
SUBTAREFAS_EXTRA = {
    "verificacao de tracker parado": [
        ("O tracker voltou a operar ao final da atividade?", 2),
        ("Qual foi a causa raiz? (motor, TCU ou outro ponto)", 1),
    ],
}
_TIPO_ITEM_DESC = {1: "TEXT", 2: "BOOLEAN", 3: "NUMBER", 4: "CHECK", 7: "DROPDOWN"}

# ── O TIPO DE TAREFA que o app põe no lugar do tipo do plano (Levi, 29/10/2026: "PERFORMANCE > INSPEÇÃO DO INVERSOR QUERO O
# TIPO DA TAREFA COMO CORRETIVA!"). O `create_planned_os` copia o tipo do plano do Fracttal; fica aqui, e não no plano,
# pelo mesmo motivo das SUBTAREFAS_EXTRA: o plano é de outra área e vale para quem cria OS por fora do app. Casado pelo
# trecho do nome do plano, como as extras.
TIPO_TAREFA_DO_PLANO = {
    "inspecao geral do inversor": "Corretiva",
}


def com_tipo_da_tarefa(plan: dict) -> dict:
    """O plano com o tipo de tarefa do TIPO_TAREFA_DO_PLANO, quando o nome casa. Devolve uma CÓPIA (o plano fica em cache
    por id_task); sem regra para o plano, devolve o mesmo."""
    desc = api._norm_txt((plan or {}).get("description"))
    tipo = next((t for frase, t in TIPO_TAREFA_DO_PLANO.items() if frase in desc), None)
    if not tipo or tipo not in api.TASK_TYPE_MAIN:
        return plan
    return dict(plan, id_task_type_main=api.TASK_TYPE_MAIN[tipo], tasks_types_main_description=tipo)


def com_subtarefas_extra(plan: dict) -> dict:
    """O plano com as subtarefas do app acrescentadas no fim. Devolve uma CÓPIA — o plano fica
    em cache por id_task e mutá-lo somaria as extras de novo a cada OS do lote.

    Cada item novo é clonado da FORMA de um item que veio do plano, trocando só o que muda. É
    de propósito: a estrutura do form item tem 20 campos (id_company, id_group_task, iterations,
    dropdown_options…) e montar um dicionário do zero seria adivinhar quais o RPC exige."""
    subs = list(plan.get("subtasks") or [])
    if not subs:
        return plan                        # sem modelo para clonar, não invento estrutura
    extras = []
    desc_plano = api._norm_txt(plan.get("description"))
    for frase, itens in SUBTAREFAS_EXTRA.items():
        if frase not in desc_plano:
            continue
        for texto, tipo in itens:
            if any(api._norm_txt(s.get("description")) == api._norm_txt(texto) for s in subs):
                continue                   # o plano já pergunta isso — não duplica
            novo = dict(subs[0])
            novo.update({"id": str(uuid.uuid4()), "description": texto,
                         "id_task_form_item_type": tipo,
                         "task_form_item_type_description": _TIPO_ITEM_DESC.get(tipo),
                         "order_number": len(subs) + len(extras) + 1,
                         "is_required": True, "attachments_required": False,
                         "is_configured": True, "is_changed": False,
                         "id_unit": None, "unit_description": None, "units_code": None,
                         "dropdown_options": None})
            extras.append(novo)
    if not extras:
        return plan
    # A MARCA FICA NO PLANO, não no item: o que vai para o RPC é `plan["subtasks"]`, e uma chave
    # a mais dentro do item seria um campo desconhecido no payload — justamente o que clonar a
    # forma existia para evitar.
    return {**plan, "subtasks": subs + extras, _MARCA_EXTRA: len(extras)}


_MARCA_EXTRA = "_n_subtarefas_do_app"


def sem_subtarefas_extra(plan: dict) -> dict:
    """O plano de volta ao que veio do Fracttal, sem as subtarefas que o app acrescentou (as extras ou o padrão do Nexus).

    É a REDE DE SEGURANÇA da criação: se o RPC recusar a OS com as perguntas novas, ela sai sem
    elas em vez de não sair. A OS de tracker é rotina diária — perdê-la por causa de uma
    melhoria seria trocar um incômodo por uma parada."""
    if plan.get(_MARCA_PADRAO) is not None:
        sobra = {k: v for k, v in plan.items() if k != _MARCA_PADRAO}
        sobra["subtasks"] = list(plan[_MARCA_PADRAO])
        return sobra
    n = int(plan.get(_MARCA_EXTRA) or 0)
    if not n:
        return plan
    sobra = {k: v for k, v in plan.items() if k != _MARCA_EXTRA}
    sobra["subtasks"] = list(plan.get("subtasks") or [])[:-n]
    return sobra


def tem_subtarefas_extra(plan: dict) -> bool:
    return bool(plan.get(_MARCA_EXTRA)) or plan.get(_MARCA_PADRAO) is not None


def tem_subtarefas_padrao(plan: dict) -> bool:
    return plan.get(_MARCA_PADRAO) is not None


# ── O PADRÃO DO NEXUS (05/11/2026) ─────────────────────────────────────────────────────────────
# Levi: "Quero que no OS Creator > Performance tenha um campo para subtarefas, que vamos poder editar as subtarefas padrões
# de cada atividade!". A lista salva no Nexus (`nexus/torres/oscreator/subtarefas_padrao.py`) vale NO LUGAR das subtarefas
# do plano e das do app; o plano do Fracttal não muda. Cada subtarefa da lista: {"desc", "tipo", "anexo", "origem"}, com os
# tipos do editor de Temas da Solicitação (`solic_spec.TIPO_ID`) e "plano" para o tipo que o editor não monta (a lista de
# opções, a unidade): esse fica como está no plano. "origem" = o id da subtarefa do plano de onde ela veio.
TIPO_SUB_ID = {"texto": 1, "simnao": 2, "num": 3, "verif": 4}
_ID_TIPO_SUB = {v: k for k, v in TIPO_SUB_ID.items()}
_MARCA_PADRAO = "_subtarefas_do_plano"


def subtarefas_para_editor(subtasks: list) -> list:
    """As subtarefas (form items do plano) no formato do editor: {"desc", "tipo", "anexo", "origem"[, "tipo_rotulo"]}."""
    out = []
    for s in subtasks or []:
        if not isinstance(s, dict):
            continue
        desc = str(s.get("description") or "").strip()
        if not desc:
            continue
        tid = s.get("id_task_form_item_type")
        item = {"desc": desc, "tipo": _ID_TIPO_SUB.get(tid, "plano"), "anexo": bool(s.get("attachments_required")),
                "origem": str(s["id"]) if s.get("id") not in (None, "") else None}
        if item["tipo"] == "plano":
            item["tipo_rotulo"] = "Lista" if tid == 7 else str(s.get("task_form_item_type_description") or "do plano")
        out.append(item)
    return out


def com_subtarefas_padrao(plan: dict, lista: list) -> dict:
    """O plano com a lista do padrão do Nexus no lugar das subtarefas (as do plano e as do app). Devolve uma CÓPIA (o plano
    fica em cache por id_task). Cada subtarefa sai da FORMA de uma do plano, como as do app (`com_subtarefas_extra`): a de
    onde veio (`origem`), com o tipo, as opções e a unidade dela quando o tipo não mudou; a nova, da forma da 1ª. A marca
    guarda as subtarefas do plano para a rede de segurança (`sem_subtarefas_extra`)."""
    subs = list(plan.get("subtasks") or [])
    if not subs or not lista:
        return plan                        # sem modelo para clonar, não invento estrutura
    por_id = {str(s.get("id")): s for s in subs if s.get("id") not in (None, "")}
    novas = []
    for i, it in enumerate(lista):
        base = por_id.get(str(it.get("origem") or ""))
        tipo = str(it.get("tipo") or "texto")
        novo = dict(base or subs[0])
        if base is not None and (tipo == "plano" or TIPO_SUB_ID.get(tipo) == base.get("id_task_form_item_type")):
            pass                           # o tipo do plano, com as opções e a unidade dele
        else:
            tid = TIPO_SUB_ID.get(tipo, 1)  # o "plano" sem a subtarefa de origem (o plano mudou no Fracttal) vira texto
            novo.update({"id_task_form_item_type": tid, "task_form_item_type_description": _TIPO_ITEM_DESC.get(tid),
                         "dropdown_options": None, "id_unit": None, "unit_description": None, "units_code": None})
        if base is None:
            novo.update({"id": str(uuid.uuid4()), "is_required": True, "is_configured": True, "is_changed": False})
        novo.update({"description": str(it.get("desc") or "").strip(), "order_number": i + 1,
                     "attachments_required": bool(it.get("anexo"))})
        novas.append(novo)
    sobra = {k: v for k, v in plan.items() if k != _MARCA_EXTRA}
    return {**sobra, "subtasks": novas, _MARCA_PADRAO: subs}


def _norm_txt(s) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def _plan_family(desc) -> str:
    """Família do plano a partir da descrição ('[Cliente] - MPM - ...' / 'Handover – ...').
    → 'PERFORMANCE'/'MPM'/'MPA'/'MPS'/'MPQ'/'MPW'/'MPT'/'Handover' ou None."""
    import re
    d = str(desc or "")
    dn = api._norm_txt(d)
    if "performance" in dn or any(p in dn for p in _PERF_PLANOS):   # PERFORMANCE (aba Performance; ocultos no PCM)
        return "PERFORMANCE"
    if "handover" in dn:
        return "Handover"
    m = re.search(r"\bMP[A-Z]\b", d.upper())
    return m.group(0) if m else None


def ler_planos_do_ativo(id_item, id_group_task=None) -> list:
    """Os planos de tarefa de UM ativo (1 task_events_list) → [{id_task, description}]. Levanta o erro do Fracttal. É o
    leitor do catálogo dos planos da Performance (`catalogos_planos.planos_dos_ativos`, 31/10/2026)."""
    r = api._rpc_call(RPC_TASK_EVENTS, {"filter": [], "sort": [], "page": 1, "limit": 300, "start": 0,
                                    "is_tree": False, "node": None, "id_item": id_item, "id_group_task": id_group_task})
    data = r.get("data") if isinstance(r, dict) else r
    res = []
    for d in (data if isinstance(data, list) else []):
        if not isinstance(d, dict):
            continue
        idt = d.get("id_task") if d.get("id_task") is not None else d.get("id")
        desc = d.get("task_description") or d.get("tasks_description") or d.get("description") or ""
        if idt is not None:
            res.append({"id_task": idt, "description": str(desc).strip()})
    return res


def get_plans_for_assets(assets: list, guardados: bool = False) -> list:
    """Planos de tarefa de VÁRIOS ativos (1 task_events_list por ativo, em paralelo). Cada plano vem
    com o ATIVO e a FAMÍLIA (parseada da descrição). → [{id_task, description, family, asset, asset_label}].

    `guardados` (a Performance, 31/10/2026, etapa 4 do canto central): os planos do catálogo dos planos, por ativo
    (`catalogos_planos.planos_dos_ativos`): a 2ª escolha da mesma usina não pede nada; o vencido (24 h) volta e é relido por trás.
    Sem ele (a Clonagem de planos do PCM, que mexe nos planos e os quer como estão agora), ao vivo, como sempre."""
    alist = [a for a in (assets or []) if isinstance(a, dict) and a.get("id")]

    def _decorar(a, planos):
        return [{"id_task": p["id_task"], "description": p["description"], "family": api._plan_family(p["description"]),
                 "asset": a, "asset_label": a.get("label") or a.get("code") or "?"} for p in (planos or [])]
    if guardados:
        import catalogos_planos
        por_ativo = catalogos_planos.planos_dos_ativos(alist)
        out = []
        for a in alist:
            out.extend(_decorar(a, por_ativo.get(catalogos_planos.chave_plano(a.get("id"), a.get("id_group_task")))))
        return out

    def _one(a):
        try:
            return _decorar(a, api.ler_planos_do_ativo(a.get("id"), a.get("id_group_task")))
        except FracttalError:
            return []
    out = []
    with api._ExecutorComContexto(max_workers=8) as ex:
        for r in ex.map(_one, alist):
            out.extend(r)
    return out


# duração (segundos) de cada plano, preenchida de carona no `get_subtask_counts` — ver lá.
_DURACAO_PLANO = {}


def duracao_do_plano(id_task, padrao: int = 900) -> int:
    """Quanto o plano diz que a tarefa dura, em segundos. `padrao` quando ainda não se leu o plano
    (a tela mostra esse valor e a pessoa corrige, que é melhor do que um campo vazio)."""
    return int(_DURACAO_PLANO.get(id_task) or padrao)


def get_subtask_counts(pares: list) -> dict:
    """Nº de subtarefas de cada plano. `pares` = [(id_task, id_item)]. → {id_task: n} (em paralelo,
    via tasks_details). Defensivo: plano que falhar/sem subtarefa não entra no dict (a UI mostra '?')."""
    uniq = {}
    for p in (pares or []):
        try:
            idt, idi = p
        except (TypeError, ValueError):
            continue
        if idt is not None and idt not in uniq:
            uniq[idt] = idi

    def _one(item):
        idt, idi = item
        try:
            det = api.get_plan_details(idt, idi)
            # a DURAÇÃO vem na mesma resposta, e a tela do PCM precisa dela para mostrar o tempo
            # de cada tarefa. Guardar aqui evita uma segunda rodada de `tasks_details` por plano,
            # que é a chamada mais cara desta tela.
            _DURACAO_PLANO[idt] = int(det.get("duration") or 0)
            return (idt, len(det.get("subtasks") or []))
        except Exception:
            return (idt, None)
    out = {}
    if not uniq:
        return out
    with api._ExecutorComContexto(max_workers=8) as ex:
        for idt, n in ex.map(_one, list(uniq.items())):
            if n is not None:
                out[idt] = n
    return out


def get_subtask_names(pares: list) -> dict:
    """Descrições das subtarefas de cada plano. `pares` = [(id_task, id_item)]. → {id_task: [desc,...]}
    (em paralelo, via get_plan_details). Defensivo: plano que falhar/sem subtarefa não entra no dict."""
    uniq = {}
    for p in (pares or []):
        try:
            idt, idi = p
        except (TypeError, ValueError):
            continue
        if idt is not None and idt not in uniq:
            uniq[idt] = idi

    def _one(item):
        idt, idi = item
        try:
            det = api.get_plan_details(idt, idi)
            nomes = [str(s.get("description") or "").strip() for s in (det.get("subtasks") or [])]
            return (idt, [n for n in nomes if n])
        except Exception:
            return (idt, None)
    out = {}
    if not uniq:
        return out
    with api._ExecutorComContexto(max_workers=8) as ex:
        for idt, nomes in ex.map(_one, list(uniq.items())):
            if nomes is not None:
                out[idt] = nomes
    return out


# ── Atualizar subtarefas a partir do MODELO de tarefa do ativo ────────────────
RPC_TASK_EVENTS = "tasks.task_events_list"          # modelos (gatilhos) disponíveis p/ um ativo
RPC_TASK_TEMPLATE_ITEMS = "tasks.tasks_form_items_list"   # subtarefas de um modelo (por id_task)


def _subtarefas_de_modelo(id_task) -> list:
    """Subtarefas (form items) atuais de um modelo de tarefa, pelo id_task do modelo.
    → [{'description','id_task_form_item_type','task_form_item_type_description',...}] ordenadas."""
    res = api._rpc_call(RPC_TASK_TEMPLATE_ITEMS, {"id_task": id_task})
    data = res.get("data") if isinstance(res, dict) else res
    out = []
    for it in sorted((data if isinstance(data, list) else []), key=lambda x: x.get("order_number") or 0):
        d = str(it.get("description") or "").strip()
        if not d:
            continue
        out.append({"description": d,
                    "id_task_form_item_type": it.get("id_task_form_item_type"),
                    "task_form_item_type_description": it.get("task_form_item_type_description"),
                    "id_task_form_item_group": it.get("id_task_form_item_group"),
                    "task_form_item_group_description": it.get("task_form_item_group_description"),
                    "is_required": bool(it.get("is_required")),
                    "attachments_required": bool(it.get("attachments_required")),
                    "dropdown_options": it.get("dropdown_options")})
    return out


def get_template_subtarefas(asset: dict, task_description: str) -> dict:
    """Re-seleciona o MODELO de tarefa do mesmo nome p/ o ativo (como ao criar OS e escolher o
    ativo) e devolve as subtarefas ATUAIS desse modelo — p/ o botão 'Atualizar do modelo' do clone.
    Casa o evento pelo nome (tasks_description == task_description).
    → {'achou':bool,'subtarefas':[dict],'nome','id_task','erro'}."""
    id_item = asset.get("id") if isinstance(asset, dict) else None
    if not id_item:
        return {"achou": False, "subtarefas": [], "erro": "Ativo sem id — recarregue os ativos."}
    res = api._rpc_call(RPC_TASK_EVENTS, {"filter": [], "sort": [], "page": 1, "limit": 300, "start": 0,
                    "is_tree": False, "node": None, "id_item": id_item,
                    "id_group_task": asset.get("id_group_task")})
    data = res.get("data") if isinstance(res, dict) else res
    alvo = (task_description or "").strip().lower()
    id_task, evento = None, {}
    for e in (data if isinstance(data, list) else []):
        nome = str(e.get("tasks_description") or e.get("task_description") or "").strip()
        if nome.lower() == alvo:
            id_task, evento = e.get("id_task"), e
            break
    if not id_task:
        return {"achou": False, "subtarefas": [],
                "erro": f"Nenhum modelo com o nome “{task_description}” para este ativo."}
    subs = api._subtarefas_de_modelo(id_task)
    return {"achou": True, "subtarefas": subs, "nome": task_description, "id_task": id_task,
            "duracao": api._duracao_do_modelo(evento, id_task, id_item)}


def _duracao_do_modelo(evento: dict, id_task, id_item):
    """O tempo cadastrado no MODELO de tarefa (o PCM, 30/10/2026: "o tempo que viesse fosse o cadastrado do plano, que
    seria atualizado no 'Atualizar todas do modelo'"). Do evento da lista de modelos, quando vem; senão do detalhe do
    modelo (`tasks_details`, um pedido a mais), pelo valor CRU: o `get_plan_details` põe 900 quando falta. None se o
    modelo não tem tempo (a tarefa fica com o que tinha)."""
    dur = api._segundos((evento or {}).get("duration"))
    if dur:
        return dur
    try:
        return api._segundos((api.get_plan_details(id_task, id_item).get("raw") or {}).get("duration"))
    except FracttalError:
        return None


def atualizar_modelos_subtarefas(tarefas: list) -> list:
    """Em lote: p/ cada tarefa COM ativo, re-busca o modelo do mesmo nome e devolve as subtarefas
    atuais. NÃO muta as tarefas (a UI aplica, na thread principal). Não interrompe no 1º erro.
    → lista PARALELA a 'tarefas': cada item é None (tarefa sem ativo) ou
      {'achou':bool,'subtarefas':[dict],'erro':str|None}."""
    out = []
    for t in (tarefas or []):
        asset = t.get("asset") if isinstance(t, dict) else None
        if not (isinstance(asset, dict) and asset.get("id")):
            out.append(None)
            continue
        try:
            r = api.get_template_subtarefas(asset, t.get("descricao") or "")
            out.append({"achou": bool(r.get("achou")), "subtarefas": r.get("subtarefas") or [],
                        "duracao": r.get("duracao"), "erro": r.get("erro")})
        except FracttalError as e:
            out.append({"achou": False, "subtarefas": [], "erro": str(e)})
    return out


import api  # noqa: E402 — no fim: o `api` importa este módulo

"""os_estado.py: o estado da OS.

Cancelar (e os motivos), trocar o responsável, reescrever a nota, mudar o status, concluir (e conferir a data fim antes), o
fluxo da OS (todo o encadeamento, para o card de fluxo), o cancelamento por número e achar a OS pelo número (`os_por_folio`,
`_wo_id_por_folio`, que pergunta primeiro à lista central de OS pelo gancho `api.ID_PELA_LISTA`).

Saiu do `api.py` em 31/10/2026 (etapa 5.3 do canto central, "o que sobra do api.py"): mudou só o lugar, o código é o mesmo. O
`api.py` segue expondo os mesmos nomes (`api.X`), porque a ponte, as rotas e os testes chamam e TROCAM `api.X` pelo nome. Por
isso toda função que este módulo chama, dele ou de fora (o `api._rpc_call`, o que também saiu para outro módulo), e todo número
ajustável (um prazo, um teto) vão pelo `api.`, e enxergam a troca; só as outras constantes e o estado daqui são usados direto. O
módulo termina com `import api`: o `api` o importa no fim do arquivo (a fachada), e só precisa dele na hora da chamada."""

from fracttal_erro import FracttalError


# ── Histórico: "Minhas OS" (criadas por mim / atribuídas a mim) ───────────────
RPC_WO_LIST = "tasks.work_orders_list_react"
# Mapa de id_status_work_order → rótulo (confirmado no kanban do Fracttal: colunas
# "OSs em Processo" 1, "em Verificação" 2, "Concluídas" 3 + selo CANCELADO = 4).
WO_STATUS = {1: "Em Processo", 2: "Em Verificação", 3: "Concluída", 4: "Cancelada"}
STATUS_FECHADOS = frozenset({3, 4})      # a OS não está mais na mão de ninguém


def status_da_os(id_work_order):
    """`id_status_work_order` atual da OS, lido do servidor. None se não achar.

    Serve para CONFERIR uma conclusão: o `recalculate` já respondeu sucesso deixando a OS aberta,
    e sem esta leitura o app anuncia "concluída" para uma OS que continua em processo."""
    if not id_work_order:
        return None
    try:
        res = api._rpc_call(RPC_WO_DETAILS, {"id": id_work_order, "get_iso_codes": False})
    except FracttalError:
        return None
    d = res.get("data") if isinstance(res, dict) else res
    d = d[0] if isinstance(d, list) and d else (d if isinstance(d, dict) else {})
    st = (d or {}).get("id_status_work_order")
    return int(st) if st is not None else None


# ── Cancelar OS ───────────────────────────────────────────────────────────────
RPC_WO_CANCEL        = "tasks.work_order_cancel"
RPC_WO_STATUS_CUSTOM = "tasks.work_orders_status_custom_list"   # lista dos MOTIVOS de cancelamento


def get_cancel_motivos() -> list:
    """Motivos de cancelamento de OS (status custom). → [{'id','description'}], ordenado por descrição."""
    r = api._rpc_call(RPC_WO_STATUS_CUSTOM, {"sort": [{"property": "description", "direction": "asc"}],
                                         "page": 1, "limit": 200, "start": 0, "is_tree": False, "node": None})
    data = r.get("data") if isinstance(r, dict) else r
    out = []
    for d in (data if isinstance(data, list) else []):
        idc = d.get("id") if d.get("id") is not None else d.get("id_work_orders_status_custom")
        if idc is not None:
            out.append({"id": idc, "description": str(d.get("description") or "?")})
    return out


def cancel_os(id_work_order, id_status_custom, note: str = "", cancellation_type: int = 1,
              utc_min: int = -180) -> dict:
    """Cancela a OS via tasks.work_order_cancel. id_status_custom = MOTIVO (de get_cancel_motivos);
    cancellation_type=1 ('Cancelar OS', fixo); utc_min=-180 (Brasília). A AUTORIZAÇÃO é do Fracttal —
    se a conta não puder cancelar, a API recusa (FracttalError). → {'ok':True,'raw':...}."""
    if not id_work_order:
        raise FracttalError("OS sem id — recarregue o histórico.")
    if not id_status_custom:
        raise FracttalError("Escolha o motivo do cancelamento.")
    params = {"id": id_work_order, "id_work_orders_status_custom": id_status_custom,
              "note": (note or "").strip(), "cancellation_type": cancellation_type, "utc_min": utc_min}
    res = api._rpc_call(RPC_WO_CANCEL, params)
    if isinstance(res, dict) and res.get("success") is False:      # recusa não-sessão (ex.: sem permissão)
        raise FracttalError(str(res.get("message") or "Cancelamento recusado pelo Fracttal "
                                                      "(sua conta tem permissão p/ cancelar OS?)."))
    return {"ok": True, "raw": res}


RPC_WO_UPDATE = "tasks.work_orders_update"      # troca o RESPONSÁVEL de uma OS já criada


def mudar_responsavel(id_work_order, id_personnel, nota=None) -> dict:
    """Troca o responsável de uma OS existente.

    Capturado do Fracttal web (28/07). É a ÚNICA edição de OS já criada que a API aceita além de
    status, etiqueta e anexo — e reabre a possibilidade de repassar trabalho sem sair do app.
    `type_user: HUMAN_RESOURCES` é o que distingue pessoa de terceiro; `id_assigned_user` é o
    id_personnel (o mesmo que `get_responsaveis` devolve), NÃO o id da OS."""
    if not id_work_order:
        return {"ok": False, "erro": "OS sem id."}
    if not id_personnel:
        return {"ok": False, "erro": "Escolha a pessoa."}
    res = api._rpc_call(RPC_WO_UPDATE, {"page": 1, "limit": 200, "start": 0, "append": True,
                                    "id": id_work_order, "type_user": "HUMAN_RESOURCES",
                                    "id_assigned_user": id_personnel, "note": nota})
    if isinstance(res, dict) and res.get("success") is False:
        return {"ok": False, "erro": str(res.get("message") or "não consegui trocar o responsável")}
    return {"ok": True, "raw": res}


_ERRO_WO_FECHADA = "ERROR_WO_FINISHED_BY_OTHER_USER"


def editar_nota_os(id_work_order, nota: str) -> dict:
    """Reescreve a NOTA (observação) de uma OS já criada. → {'ok'} | {'ok':False,'erro'}.

    Sondado ao vivo em 02/09 (OS 12728, marcador escrito e desfeito). Três coisas que só o teste
    contra a API revelou, e que a chamada precisa respeitar:

    1. O `work_orders_update` GRAVA a nota de verdade — não era garantido: o mesmo endpoint aceita
       `id_parent_wo`, responde ACTION_DONE e grava None (ver `_work_order_insert`). Aqui persiste.
    2. Em OS CONCLUÍDA ele recusa com ERROR_WO_FINISHED_BY_OTHER_USER — apesar do nome, não é
       conflito entre usuários, é a OS estar fechada. A mensagem crua não ajudaria ninguém.
    3. Ele exige `id_assigned_user` junto. Mandar sem, ou com o valor errado, mexeria no
       RESPONSÁVEL de tabela — por isso lemos o atual e devolvemos o mesmo, sem tocar nele.

    A nota fica na TAREFA, não no cabeçalho da OS (o `note` do work_order_details_new vem sempre
    None); é por isso que a leitura confere pelo `work_orders_tasks_new_list`."""
    if not id_work_order:
        return {"ok": False, "erro": "OS sem id."}
    try:
        r = api._rpc_call(api.RPC_WO_TASKS, {"page": 1, "limit": 50, "start": 0,
                                     "id_work_order": id_work_order})
        d = r.get("data") if isinstance(r, dict) else r
        t0 = d[0] if isinstance(d, list) and d else {}
    except Exception as e:                                   # noqa: BLE001
        return {"ok": False, "erro": "não consegui ler a OS antes de gravar (%s)" % str(e)[:70]}
    if not t0:
        return {"ok": False, "erro": "não achei a tarefa desta OS."}
    res = api._rpc_call(RPC_WO_UPDATE, {"page": 1, "limit": 200, "start": 0, "append": True,
                                    "id": id_work_order, "type_user": "HUMAN_RESOURCES",
                                    "id_assigned_user": t0.get("id_assigned_user"),
                                    "note": str(nota or "")})
    if isinstance(res, dict) and res.get("success") is False:
        msg = str(res.get("message") or "")
        if _ERRO_WO_FECHADA in msg:
            return {"ok": False, "erro": "Esta OS já está concluída — o Fracttal não aceita mais "
                                         "editar a observação dela."}
        return {"ok": False, "erro": msg or "o Fracttal recusou a edição da observação."}
    return {"ok": True, "nota": str(nota or "").strip()}      # a API apara os espaços das pontas


RPC_WO_CHANGE_STATUS = "tasks.work_orders_change_status"        # muda o status da WO (1..4)
RPC_WO_RECALCULATE   = "tasks.work_orders_recalculate_new"     # confirma o fechamento (irreversível)


def mudar_status_os(id_work_order, id_status: int = 1) -> dict:
    """Muda o status da OS SEM fechá-la (1 Em Processo · 2 Em Verificação). É a única escrita que
    a API permite numa OS já criada além de etiqueta/anexo — e é o que a equipe de chamados pediu:
    'quando eu abrir o chamado, eu não vou concluir ela, vou colocar como em progresso'.
    NÃO usar com 3 (Concluída): fechar exige o recalculate e é irreversível → `concluir_os`."""
    if not id_work_order:
        return {"ok": False, "erro": "OS sem id."}
    if int(id_status) not in (1, 2):
        return {"ok": False, "erro": "Status inválido aqui (use 1 Em Processo ou 2 Em Verificação)."}
    res = api._rpc_call(RPC_WO_CHANGE_STATUS, {"id_work_order": id_work_order,
                                           "id_status_work_order": int(id_status),
                                           "verify_triggers": True, "update_readings_after": False})
    if isinstance(res, dict) and res.get("success") is False:
        return {"ok": False, "erro": str(res.get("message") or "o Fracttal recusou a mudança "
                                         "(sua conta tem permissão?)")}
    return {"ok": True, "status": WO_STATUS.get(int(id_status), "")}


def concluir_os(id_work_order) -> dict:
    """CONCLUI (fecha) uma OS — IRREVERSÍVEL. 2 passos (fluxo capturado ao vivo, OS 9226):
    1) muda o status p/ Concluída (3); 2) recalcula/fecha (marca subtarefas não executadas como
    pendentes e fecha a OS). A AUTORIZAÇÃO é do Fracttal — sem permissão, a API recusa (FracttalError).
    → {'ok':True}."""
    if not id_work_order:
        raise FracttalError("OS sem id — recarregue o histórico.")
    r1 = api._rpc_call(RPC_WO_CHANGE_STATUS, {"id_work_order": id_work_order, "id_status_work_order": 3,
                                          "verify_triggers": True, "update_readings_after": False})
    if isinstance(r1, dict) and r1.get("success") is False:
        raise FracttalError(str(r1.get("message") or "Não foi possível mudar o status da OS "
                                                     "(sua conta tem permissão p/ fechar OS?)."))
    r2 = api._rpc_call(RPC_WO_RECALCULATE, {"id_work_order": id_work_order, "verify_work_in_progress": True})
    if isinstance(r2, dict) and r2.get("success") is False:
        raise FracttalError(str(r2.get("message") or "Não foi possível fechar a OS."))
    return {"ok": True, "raw": r2}


def _wo_resumo(w: dict) -> dict:
    """Linha crua do work_orders_list_react → nó do fluxo."""
    return {"id": w.get("id"), "folio": str(w.get("wo_folio") or "").strip(),
            "descricao": str(w.get("tasks_description") or w.get("description") or "").strip(),
            "tipo_tarefa": str(w.get("tasks_types_main_description") or "").strip(),
            "status": WO_STATUS.get(w.get("id_status_work_order"), "—"),
            "status_id": w.get("id_status_work_order"),
            "event_date": w.get("event_date"), "criacao": w.get("creation_date")}


def _filhos_da_os(id_work_order) -> list:
    """OS que apontam esta como pai. O RPC aceita o filtro `id_parent_wo` no `filter` — sondado ao
    vivo (03/08): como PARÂMETRO solto ele ignora e devolve o catálogo inteiro; dentro do `filter`
    devolve só os filhos. Não confundir com o `id_parent` da TAREFA, que é o pai do ATIVO."""
    if not id_work_order:
        return []
    try:
        res = api._rpc_call(RPC_WO_LIST, {"page": 1, "limit": 100, "start": 0, "append": True,
                                      "filter": [{"operator": "=", "property": "id_parent_wo",
                                                  "value": id_work_order}],
                                      "sort": [{"property": "id", "direction": "asc"}]})
    except FracttalError:
        return []
    return [api._wo_resumo(w) for w in (res.get("data") or []) if isinstance(w, dict)]


def _os_por_folio_leve(folio) -> dict:
    """Nó do fluxo a partir do NÚMERO. Usa o mesmo filtro exato do `_wo_id_por_folio`, mas devolve
    a linha inteira em vez de só o id — evita uma segunda consulta para saber tipo e status."""
    folio = str(folio or "").strip()
    if not folio:
        return {}
    for st in (1, 2, 3, 4):
        try:
            res = api._rpc_call(RPC_WO_LIST, {"page": 1, "limit": 20, "start": 0, "append": True,
                                          "id_status_work_order": st,
                                          "filter": [{"operator": "=", "property": "wo_folio",
                                                      "value": folio}],
                                          "sort": [{"property": "id", "direction": "desc"}]})
        except FracttalError:
            continue
        for w in (res.get("data") or []):
            if str(w.get("wo_folio")).strip() == folio:
                return api._wo_resumo(w)
    return {}


def _ordem_os(n: dict):
    """Chave de ordenação do fluxo: NÚMERO da OS (Levi, 05/08). O folio é sequencial com a criação,
    então ordena por criação e ainda funciona quando a data vem vazia — que acontece."""
    try:
        return (0, int(str(n.get("folio") or "0").strip()))
    except (TypeError, ValueError):
        return (1, 0)


def fluxo_da_os(id_work_order, limite_ativo: int = 12) -> dict:
    """Todo o encadeamento de uma OS, para o card de fluxo.
    → {'atual', 'cadeia': [nós em ordem], 'ativo': {...}, 'historico': [nós], 'aviso'}

    TRÊS FONTES, porque nenhuma sozinha resolve (medido em 300 OS de julho):
      1. `id_parent_wo` — o pai FORMAL. Confiável, e raro: 7 em 300. Sozinho, 97% das OS abririam
         um fluxo de um nó só.
      2. o bloco `[CHAMADO]` da observação ("OS de abertura: 9738"). É daí que o board de chamados
         tira o "pai" que aparece no card — na OS 10149 o pai formal é nulo e o texto sabe.
      3. o MESMO ATIVO — `ultimas_os_do_ativo`, filtrado no servidor por `id_item`. É como uma
         pessoa reconstrói o fluxo na mão, e é o que dá conteúdo quando não há vínculo nenhum.

    A cadeia sobe pelos pais (1 e 2) e desce pelos filhos (`_filhos_da_os`), com teto de 12 nós —
    ciclo de dados ruins não pode virar laço infinito."""
    vazio = {"atual": {}, "cadeia": [], "ativo": {}, "historico": [], "aviso": ""}
    if not id_work_order:
        return vazio
    try:
        rd = api._rpc_call(RPC_WO_DETAILS, {"id": id_work_order, "get_iso_codes": False})
    except FracttalError as e:
        return {**vazio, "aviso": str(e)[:160]}
    det = rd.get("data") if isinstance(rd, dict) else rd
    det = det[0] if isinstance(det, list) and det else (det if isinstance(det, dict) else {})
    try:
        rt = api._rpc_call(api.RPC_WO_TASKS, {"id_work_order": id_work_order, "sort": []})
    except FracttalError:
        rt = {}
    t0 = ((rt.get("data") if isinstance(rt, dict) else rt) or [{}])[0]

    atual = {"id": id_work_order, "folio": str(t0.get("wo_folio") or det.get("wo_folio") or "").strip(),
             "descricao": str(t0.get("tasks_description") or "").strip(),
             "tipo_tarefa": str(t0.get("tasks_types_main_description") or "").strip(),
             "status": WO_STATUS.get(det.get("id_status_work_order") or t0.get("id_status_work_order"), "—"),
             "status_id": det.get("id_status_work_order") or t0.get("id_status_work_order"),
             "event_date": t0.get("event_date"), "criacao": t0.get("creation_date")}
    ativo = {"id_item": t0.get("id_item"),
             "nome": (str(t0.get("items_description") or "").split("{")[0]).strip(),
             "code": (t0.get("code_item") or "").strip()
                     or api._extrai_code(str(t0.get("items_description") or "")),
             "usina": "", "cliente": ""}
    if ativo["code"]:
        a = api._asset_by_code(ativo["code"])
        if isinstance(a, dict):
            ativo["usina"] = a.get("usina") or ""
            ativo["cliente"] = a.get("cliente") or ""

    # ── sobe: pai formal, e o do bloco [CHAMADO] quando o formal não existe ──
    cadeia, vistos = [atual], {id_work_order}
    pai_id = det.get("id_parent_wo") or t0.get("id_parent_wo")
    nota = "\n".join(str(t0.get(k) or "") for k in ("note", "task_note"))
    if not pai_id:
        folio_pai = str((api.parse_bloco_chamado(nota) or {}).get("os_pai") or "").strip()
        if folio_pai and folio_pai != atual["folio"]:
            n = api._os_por_folio_leve(folio_pai)
            if n.get("id"):
                cadeia.insert(0, n); vistos.add(n["id"]); pai_id = None
    while pai_id and len(cadeia) < 12 and pai_id not in vistos:
        try:
            rp = api._rpc_call(RPC_WO_DETAILS, {"id": pai_id, "get_iso_codes": False})
        except FracttalError:
            break
        dp = rp.get("data") if isinstance(rp, dict) else rp
        dp = dp[0] if isinstance(dp, list) and dp else (dp if isinstance(dp, dict) else {})
        if not dp:
            break
        cadeia.insert(0, api._wo_resumo(dp)); vistos.add(pai_id)
        pai_id = dp.get("id_parent_wo")

    # ── desce: filhos, netos (largura primeiro, teto de 12 no total) ──
    fila = [id_work_order]
    while fila and len(cadeia) < 12:
        for f in api._filhos_da_os(fila.pop(0)):
            if f.get("id") and f["id"] not in vistos:
                cadeia.append(f); vistos.add(f["id"]); fila.append(f["id"])
                if len(cadeia) >= 12:
                    break
    cadeia.sort(key=api._ordem_os)
    # a LINHA da listagem não traz tipo de tarefa (só a `atual` tem, que veio do RPC de tarefas).
    # Sem isto o card mostraria "Corretiva" na OS aberta e vazio nas outras — o fluxo perde a
    # informação que mais importa nele, que é qual etapa cada OS é.
    falta = [n["id"] for n in cadeia if n.get("id") and not n.get("tipo_tarefa")]
    if falta:
        meta = api._meta_tarefa_por_os(falta)
        for n in cadeia:
            m = meta.get(n.get("id")) or {}
            if m.get("tipo_tarefa"):
                n["tipo_tarefa"] = m["tipo_tarefa"]
            if not n.get("event_date") and m.get("event_date"):
                n["event_date"] = m["event_date"]

    # ── o histórico do ativo (o que dá conteúdo quando não há vínculo) ──
    # `limite_ativo <= 0` = quem chama não quer o histórico do ativo — é o caso da tela do fluxo
    # desde 06/08, que passou a mostrar só a cadeia. Sem esta guarda, seria uma ida à rede (e um
    # enriquecimento de tipo por lote) para um dado que ninguém lê.
    hist = []
    if ativo["id_item"] and int(limite_ativo or 0) > 0:
        try:
            hist = sorted(api.ultimas_os_do_ativo(ativo["id_item"], limite=limite_ativo, com_tipo=True),
                          key=api._ordem_os)
        except FracttalError:
            hist = []
        # MESMA data nas duas faixas. O `ultimas_os_do_ativo` tira o event_date da LINHA da
        # listagem, e a cadeia tira do nível TAREFA — para a mesma OS 10597 isso dava 03/08 22:04
        # numa faixa e 04/08 08:00 na outra (incidente x programada). Duas datas para a mesma OS
        # na mesma tela lê como bug mesmo quando os dois números existem.
        if hist:
            meta = api._meta_tarefa_por_os([d["id"] for d in hist if d.get("id")])
            por_id = {n.get("id"): n for n in cadeia}
            for d in hist:
                ev = (meta.get(d.get("id")) or {}).get("event_date")
                if ev:
                    d["event_date"] = ev
                n = por_id.get(d.get("id"))
                if n and n.get("event_date"):
                    d["event_date"] = n["event_date"]
    return {"atual": atual, "cadeia": cadeia, "ativo": ativo, "historico": hist, "aviso": ""}


def cancelamento_da_os(folio) -> dict:
    """Motivo e observação do cancelamento de uma OS. → {'motivo','nota'} (vazios se não achar).

    VEM DO REST, não do RPC (Levi, 03/08). Procurei o motivo nos três lugares que o app já usa —
    a linha do `work_orders_list_react`, o cabeçalho do `work_order_details_new` e o registro da
    tarefa — e não está em nenhum: são 45 e 95 campos, nenhum com o motivo nem com o id dele.
    O REST expõe em `work_orders_status_custom_description`, e responde por NÚMERO da OS
    (`work_orders/10559/`) em ~0,2 s, sem paginar.

    QUEM CANCELOU NÃO EXISTE em lugar nenhum. Todos os campos de pessoa do registro são outra
    coisa: `created_by` é quem abriu (conferido na 10533 — uma analista abriu, o cancelamento é
    anônimo), `user_assigned`/`personnel_description` é o responsável, `requested_by` é o
    solicitante. Não há "cancelado por". Se um dia precisar, sai da bitácora do Fracttal web.

    A `nota` é a observação digitada no cancelamento: ela SOBRESCREVE a observação da OS
    (`note`); a original continua em `task_note`."""
    folio = str(folio or "").strip()
    if not folio:
        return {"motivo": "", "nota": ""}
    try:
        r = api._req("GET", "work_orders/%s/" % folio, timeout=15)
    except FracttalError:
        return {"motivo": "", "nota": ""}
    d = (r.get("data") if isinstance(r, dict) else r) or []
    w = d[0] if isinstance(d, list) and d else (d if isinstance(d, dict) else {})
    return {"motivo": str((w or {}).get("work_orders_status_custom_description") or "").strip(),
            "nota": str((w or {}).get("note") or "").strip()}


def checar_data_fim(id_work_order) -> dict:
    """Quais tarefas da OS estão SEM data de fim (`final_date`).
    → {'ok': bool, 'total': n, 'sem_fim': [título, …]}  (`ok` = todas têm data).

    POR QUE ISTO EXISTE (Levi, 03/08 — caso da OS 10509, religamento em Marialva): a OS fechou
    e a tarefa ficou sem data de fim, e ninguém soube até alguém ir procurar. Medido: das OS
    criadas pelo caminho Fase 1 + Fase 2 (Criar OS, COS, Chamados, PCM, Clonar), a tarefa nasce
    com `initial_date` e `final_date` NULOS — o registro do kanban que vira a OS simplesmente não
    tem esses dois campos, e o `concluir_os` NÃO os preenche (testado na OS 10567: nula antes,
    nula depois). Quem preenche é o cronômetro de execução; sem ele a OS fecha sem data para
    sempre, e conclusão é irreversível.

    Defensivo de propósito: erro de rede aqui devolve `ok=True`. Este é um aviso, não um portão —
    derrubar a conclusão de uma OS porque a conferência falhou seria pior que o problema."""
    if not id_work_order:
        return {"ok": True, "total": 0, "sem_fim": []}
    try:
        rt = api._rpc_call(api.RPC_WO_TASKS, {"id_work_order": id_work_order, "sort": []})
    except FracttalError:
        return {"ok": True, "total": 0, "sem_fim": []}
    tasks = rt.get("data") if isinstance(rt, dict) else rt
    tasks = tasks if isinstance(tasks, list) else []
    sem = []
    for t in tasks:
        v = t.get("final_date")
        if v in (None, "") or str(v).lower() == "none":
            sem.append(str(t.get("tasks_description") or "").strip() or "(tarefa sem título)")
    return {"ok": not sem, "total": len(tasks), "sem_fim": sem}


def concluir_os_checado(id_work_order) -> dict:
    """`concluir_os` + a RECONFERÊNCIA da data de fim, na mesma thread de trabalho.

    O segundo lado do double check: o primeiro avisa ANTES (a tela lê o que já carregou), este
    confere DEPOIS, contra o servidor. Sem ele o app anunciaria "OS concluída" para uma OS que
    fechou sem data de fim — que é exatamente o que ninguém percebeu na 10509.
    → {'ok': True, 'data_fim': {…}} — ver `checar_data_fim`."""
    r = api.concluir_os(id_work_order)
    return {**r, "data_fim": api.checar_data_fim(id_work_order)}


# ── Clonar OS: lê a OS de referência (ativo + tipo + descrição + subtarefas + etiquetas) ──
RPC_WO_DETAILS = "tasks.work_order_details_new"   # cabeçalho da WO (labels, etc.)


def os_por_folio(folio) -> dict:
    """A OS inteira pelo NÚMERO, varrendo a lista por status. None se não achar.

    Existe separado do `buscar_os_pai` porque aquele usa outro RPC, que devolve só 7 campos e
    NÃO traz `creation_date` — traz `date_maintenance`, que é a data do serviço e não a da
    abertura. Para a aba Tickets a diferença importa: 'Início do chamado pela Grid Co.' é quando
    a Grid avisou, ou seja, quando a OS foi CRIADA (Levi, 31/08)."""
    folio = str(folio).strip()
    if not folio:
        return None
    # 1º, UM pedido sem o status (a lista do Histórico, sem ele, traz os quatro status: 19/10/2026, superplano do OS
    # Creator; eram até 4 pedidos um depois do outro); sem achar, a varredura de sempre, status por status
    for st in (None, 1, 2, 3, 4):
        params = {"page": 1, "limit": 50, "start": 0, "append": True,
                  "filter": [{"operator": "=", "property": "wo_folio", "value": folio}],
                  "sort": [{"property": "id", "direction": "desc"}]}
        if st is not None:
            params["id_status_work_order"] = st
        try:
            res = api._rpc_call(RPC_WO_LIST, params)
        except FracttalError:
            continue
        for w in ((res.get("data") or []) if isinstance(res, dict) else []):
            if str(w.get("wo_folio")).strip() == folio:
                return w
    return None


def _wo_id_por_folio(folio):
    """Resolve o nº da OS (wo_folio) → id_work_order. None se não achar. Pela lista central quando ela conhece o nº e a pessoa
    pode (`ID_PELA_LISTA`); senão pela listagem do Fracttal, na sessão da pessoa (`os_por_folio`)."""
    if api.ID_PELA_LISTA is not None:
        try:
            wid = api.ID_PELA_LISTA(folio)
        except Exception:                                   # noqa: BLE001 — o atalho nunca derruba a leitura de sempre
            wid = None
        if wid:
            return wid
    w = api.os_por_folio(folio)
    return w.get("id") if w else None


import api  # noqa: E402 — no fim: o `api` importa este módulo

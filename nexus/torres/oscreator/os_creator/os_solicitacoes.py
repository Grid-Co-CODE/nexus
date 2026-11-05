"""os_solicitacoes.py: as solicitações de serviço (SS).

Criar (uma e em lote), listar as minhas, o status e o catálogo de status, editar a observação, cancelar, achar a solicitação de
uma OS e APROVAR a solicitação em OS numerada (`aprovar_solicitacao`, que se retoma se a tentativa anterior parou no meio).

Saiu do `api.py` em 31/10/2026 (etapa 5.3 do canto central, "o que sobra do api.py"): mudou só o lugar, o código é o mesmo. O
`api.py` segue expondo os mesmos nomes (`api.X`), porque a ponte, as rotas e os testes chamam e TROCAM `api.X` pelo nome. Por
isso toda função que este módulo chama, dele ou de fora (o `api._rpc_call`, o que também saiu para outro módulo), e todo número
ajustável (um prazo, um teto) vão pelo `api.`, e enxergam a troca; só as outras constantes e o estado daqui são usados direto. O
módulo termina com `import api`: o `api` o importa no fim do arquivo (a fachada), e só precisa dele na hora da chamada."""

import re
import uuid
from datetime import datetime, timezone
from fracttal_erro import FracttalError
import os_juntar


# ── Solicitação de Serviço (work request) via RPC requests.requests_insert ────
RPC_REQ_TYPES   = "requests.types_list"     # Grupo
RPC_REQ_TYPES_1 = "requests.types_1_list"   # Classificação 1 (obrigatória)
RPC_REQ_TYPES_2 = "requests.types_2_list"   # Classificação 2
RPC_REQ_INSERT  = "requests.requests_insert"


def _req_type_list(method: str) -> list:
    res = api._rpc_call(method, {"sort": [{"property": "description", "direction": "asc"}],
                             "page": 1, "limit": 200, "start": 0, "is_tree": False, "node": None})
    data = res.get("data") if isinstance(res, dict) else res
    return [{"id": x.get("id"), "description": x.get("description")}
            for x in (data if isinstance(data, list) else []) if x.get("enabled", True)]


def get_request_types() -> dict:
    """Listas dos dropdowns da Solicitação: grupo, classif1 (obrigatória), classif2."""
    return {"grupo":    api._req_type_list(RPC_REQ_TYPES),
            "classif1": api._req_type_list(RPC_REQ_TYPES_1),
            "classif2": api._req_type_list(RPC_REQ_TYPES_2)}


def create_solicitacao(asset: dict, descricao: str, id_type_1, id_type=None, id_type_2=None,
                       observation: str = "", date_incident: datetime = None,
                       is_urgent: bool = False, desc_type_1: str = "",
                       desc_type: str = "", desc_type_2: str = "") -> dict:
    """Cria uma Solicitação de Serviço (work request) via RPC requests.requests_insert.
    Obrigatórios: descrição, ativo (id_item), id_type_1 (Classificação 1).
    desc_type*/_1/_2 = textos dos dropdowns (o web app os envia preenchidos — sem isso o
    servidor recusa a validação da classificação)."""
    if not (descricao or "").strip():
        raise FracttalError("A descrição não pode ficar em branco.")
    if not asset or not asset.get("id"):
        raise FracttalError("Selecione o ativo.")
    if not id_type_1:
        raise FracttalError("A Classificação 1 não pode ficar em branco.")
    dz = api._iso_z(date_incident or datetime.now(timezone.utc))
    uid = str(uuid.uuid4())
    nome = api.current_user_name()
    items_desc = asset.get("parent_description") or ""
    if not items_desc:                      # fallback p/ o caminho do ativo (cosmético)
        cli, usi = asset.get("cliente") or "", asset.get("usina") or ""
        items_desc = f"// {cli}/  {usi}/".strip()
    params = {
        "id": uid, "id_code": None, "id_work_order": 0, "wo_folio": "", "status_description": "",
        "description": descricao.strip(), "is_urgent": bool(is_urgent),
        "id_item": asset.get("id"), "items_description": items_desc,
        "code_item": asset.get("code") or "", "parent_description": "",
        "date": dz, "date_incident": dz, "date_maintenance": dz, "date_solution": dz, "date_status": dz,
        "observation": observation or "", "requests_x_status_notes": "",
        "id_cost_center": None, "costs_center_description": "",
        "id_type": id_type, "types_description": desc_type or "",
        "id_type_1": id_type_1, "types_1_description": desc_type_1 or "",
        "id_type_2": id_type_2, "types_2_description": desc_type_2 or "",
        "priorities_description": "", "rating": "", "rating_notes": "", "id_user": "",
        "accounts_name": nome, "requested_by": nome, "email_requested_by": "",
        "requests_x_status_accounts_name": "",
        "requests_x_key_words_id_key_words": None, "requests_x_key_words_descriptions": None,
        "id_status": 0, "geolocation": None, "attachments": None,
        "id_group": None, "groups_description": "", "groups_1_description": "",
        "id_group_1": None, "id_group_2": None, "groups_2_description": "",
        "identifier": "", "id_work_order_task_related": None, "id_related": "",
        "idInternal": uid,
    }
    res = api._rpc_call(RPC_REQ_INSERT, params)
    # o servidor pode recusar com success:false (HTTP 200) — sem isso a UI mostrava "criada" à toa
    if isinstance(res, dict) and res.get("success") is False:
        raise FracttalError("O Fracttal recusou a solicitação: "
                            + (str(res.get("message") or "").replace("_", " ").strip() or "motivo não informado"))
    data = res.get("data") if isinstance(res, dict) else {}
    data = data if isinstance(data, dict) else {}
    id_code = data.get("id_code") if isinstance(data, dict) else None
    if not id_code:
        raise FracttalError("A solicitação não retornou número (provavelmente não foi criada). "
                            "Resposta do servidor: " + str(res)[:240])
    return {"id_code": id_code, "raw": res}


def create_solicitacoes_bulk(assets: list, descricao: str, id_type_1, id_type=None, id_type_2=None,
                             observation: str = "", date_incident: datetime = None,
                             is_urgent: bool = False, desc_type_1: str = "",
                             desc_type: str = "", desc_type_2: str = "") -> list:
    """Cria N Solicitações — uma por ativo, com os MESMOS campos (descrição/classificação/data).
    Não para no 1º erro. → [{'code','ok':True,'id_code'} | {'code','ok':False,'erro'}]."""
    out = []
    for a in (assets or []):
        asset = a if isinstance(a, dict) else api._asset_by_code(a)
        code = asset.get("code") if isinstance(asset, dict) else str(a)
        if not isinstance(asset, dict):
            out.append({"code": code, "ok": False, "erro": "ativo não encontrado no cache."})
            continue
        try:
            r = api.create_solicitacao(asset, descricao, id_type_1, id_type=id_type, id_type_2=id_type_2,
                                   observation=observation, date_incident=date_incident,
                                   is_urgent=is_urgent, desc_type_1=desc_type_1,
                                   desc_type=desc_type, desc_type_2=desc_type_2)
            out.append({"code": code, "ok": True, "id_code": r.get("id_code")})
        except FracttalError as e:
            out.append({"code": code, "ok": False, "erro": str(e)})
    return out


def _solicitacao_row(id_code):
    """A linha da solicitacao no Fracttal — ou None. So os campos que a listagem devolve."""
    if not id_code:
        return None
    res = api._rpc_call(RPC_REQ_LIST, {"filter": [{"operator": "=", "property": "id_code",
                                               "value": id_code}],
                                   "sort": [], "page": 1, "limit": 2, "start": 0})
    data = res.get("data") if isinstance(res, dict) else res
    return (data or [None])[0] if isinstance(data, list) else None


def _tarefa_da_solicitacao(id_request):
    """A tarefa pendente que JA existe para esta solicitacao — ou None.

    O Fracttal aceita UMA tarefa por solicitacao: a segunda tentativa volta `unique_violation`.
    Logo, uma aprovacao que falhou DEPOIS da fase 1 deixa a solicitacao travada — nunca mais
    aceita conversao pela API. Medido em 02/09 nas solicitacoes 3534 e 3536: as duas ficaram com
    tarefa orfa no kanban (21543888 e 21544130) e toda nova tentativa morria no unique_violation.
    Achando a tarefa aqui, a aprovacao retomada faz so a fase 2 e a solicitacao se destrava."""
    if not id_request:
        return None
    res = api._rpc_call(api.RPC_KANBAN, {"page": 1, "limit": 500, "start": 0, "append": True,
                                 "is_tree": False, "id_type_item": 0, "filter": [],
                                 "group": {}, "sort": []})
    data = res.get("data") if isinstance(res, dict) else res
    alvo = str(id_request)
    for t in (data if isinstance(data, list) else []):
        if isinstance(t, dict) and str(t.get("id_request") or "") == alvo:
            return t
    return None


def aprovar_solicitacao(asset: dict, descricao: str, subtarefas: list, id_request,
                        id_responsible, responsible_name: str = "", note: str = "",
                        tipo: str = "Corretiva", etiqueta_ids: list = None,
                        id_parent=None, classif=None, prog_date: datetime = None, duracao: int = None) -> dict:
    """Converte a solicitacao em OS NUMERADA. Mesmo envelope do `clonar_os`. `prog_date` = a data PROGRAMADA da OS (a
    data sugerida da solicitacao, na Fila do PCM web, 15/10/2026); None = agora, como sempre. `duracao` = o tempo estimado
    da tarefa em segundos (o "Tempo estimado:" da decisao, 21/10/2026); None = o de sempre. Na retomada (a tarefa ja
    existia) ele nao muda: a tarefa nasceu na tentativa anterior.

    Aguenta ser chamada duas vezes: se a tentativa anterior parou no meio (tarefa criada, OS
    nao), retoma pela fase 2 em vez de tentar criar outra tarefa — o que so devolveria
    `unique_violation` e deixaria a solicitacao presa para sempre."""
    # 1) a solicitacao JA virou OS? A fila so mostra pendentes, mas a lista pode estar velha —
    #    e criar a segunda OS para o mesmo pedido e pior que recusar. Medido em 02/09: a segunda
    #    aprovacao da 3537 voltava so "unique_violation", sem dizer que a OS 12778 ja existia.
    try:
        ja = api._solicitacao_row(id_request) or {}
    except FracttalError:
        ja = {}
    if ja.get("id_work_order"):
        return {"ok": False, "n_tarefas": 1, "n_criadas": 0,
                "erro": "Esta solicitacao ja virou a OS %s. Atualize a fila."
                        % (ja.get("wo_folio") or ja.get("id_work_order"))}
    # 2) sobrou tarefa de uma tentativa que parou no meio? Retoma nela.
    rec = None
    try:
        rec = api._tarefa_da_solicitacao(id_request)
    except FracttalError:
        pass   # sem a checagem seguimos pelo caminho normal; o pior caso e o erro de sempre
    if rec is None:
        c1, c2 = (classif or ("", ""))
        # pelo NOME: o `clonar_os` resolve o id no catalogo vivo (`_classif_ids`), que e o mesmo
        # caminho da OS clonada — um lugar so decidindo o que vai no payload.
        return api.clonar_os([{"asset": asset, "tipo": tipo, "descricao": descricao,
                           "classif_1": c1, "classif_2": c2,
                           "subtarefas": subtarefas or [], "prog_date": prog_date, "duracao": duracao}],
                         id_responsible, responsible_name, etiqueta_ids=etiqueta_ids,
                         note=note, id_request=id_request, id_parent=id_parent)
    if not id_responsible:
        return {"ok": False, "erro": "Escolha o responsavel: sem ele a tarefa nao vira OS numerada.",
                "n_tarefas": 1, "n_criadas": 0}
    # a OS com o tempo da tarefa que ficou da tentativa anterior (30/10/2026; antes, os 600 s de sempre), pela fase 2 de todos os
    # caminhos (`os_juntar`) e sem ler o kanban de novo: o registro da tarefa já veio da busca de cima. Na retomada a fase 3
    # tambem tem de acontecer (a tarefa orfa nunca recebeu etiqueta); a que falhar nao vira aviso: a OS existe, e a etiqueta o
    # PCM poe no Fracttal se faltar
    idt = rec.get("id_task")
    jun = os_juntar.juntar_em_os([idt], {idt: api._segundos(rec.get("duration")) or duracao or api.DURACAO_OS_AVULSA}, id_responsible,
                                 responsible_name, etiqueta_ids=etiqueta_ids, registros={idt: rec}, id_parent=id_parent)
    idwo = jun.get("id_work_order")
    return {"ok": bool(idwo),
            "os": {"id_work_order": idwo, "wo_folio": jun.get("wo_folio"),
                   "id_tasks": [rec.get("id_task")]} if idwo else None,
            "erro": None if idwo else "A tarefa existe mas o Fracttal nao gerou a OS numerada.",
            "aviso": "a tarefa desta solicitacao ja existia (tentativa anterior); "
                     "reaproveitada em vez de criar outra.",
            "n_tarefas": 1, "n_criadas": 1 if idwo else 0}


# ── Histórico de Solicitações (work requests) ─────────────────────────────────
RPC_REQ_LIST = "requests.requests_list"
# requests_x_status_description (string estável) → rótulo PT. OT = Ordem de Trabalho (= OS).
REQ_STATUS = {
    "OPEN_STATUS":      "Aberta",
    "OT_IN_PROCESS":    "OS em processo",
    "OT_IN_REVIEW":     "OS em verificação",
    "CLOSE_STATUS":     "Concluída",
    "OT_FINALIZED":     "OS concluída",
    "APPROVED_STATUS":  "Aprovada",
    "REJECTED_STATUS":  "Rejeitada",
    "CANCEL_STATUS":    "Cancelada",
    "SOLVED_WITH_OT_STATUS":    "Resolvida com OS",
    "SOLVED_WITHOUT_OT_STATUS": "Resolvida sem OS",
    "AGAIN_REQUEST_TODO":       "Reaberta (refazer)",
    # Estes tres o Fracttal manda e o mapa nao tinha. Sem eles o fallback "humaniza" o
    # codigo e devolve PALAVRA EM INGLES na tela: REQUEST_TODO virava "Request",
    # PROCESS_STATUS virava "Process" e REJECTED virava "Rejected" — num app que e todo
    # em pt-BR. Os tres foram medidos nas 2.500 solicitacoes em 02/09.
    "REQUEST_TODO":             "Pendente",
    "PROCESS_STATUS":           "Em processo",
    "REJECTED":                 "Rejeitada",
}


def _req_status_label(st_raw, id_status=None):
    """Rótulo PT do status da solicitação. Conhecido → mapa REQ_STATUS; desconhecido → humaniza o
    código cru (ex.: 'FOO_BAR_STATUS' → 'Foo bar') p/ nunca exibir SCREAMING_SNAKE pro usuário."""
    if st_raw in REQ_STATUS:
        return REQ_STATUS[st_raw]
    if st_raw:
        s = st_raw.replace("_STATUS", "").replace("_TODO", "").replace("_", " ").strip()
        return s.capitalize() if s else st_raw
    return f"Status {id_status}" if id_status is not None else "—"


def _cor_de(path_image):
    """'color: #01C0DD' -> '#01C0DD'. None quando o Fracttal nao mandar cor."""
    m = re.search(r"#[0-9A-Fa-f]{6}", str(path_image or ""))
    return m.group(0) if m else None


def _req_row_to_d(r, loc):
    """Linha crua do requests_list → dict do card de solicitação (cliente/usina/ativo/descrição/etc.)."""
    item = str(r.get("items_description") or "")
    code = (r.get("code_item") or "").strip() or api._extrai_code(item)
    ativo = (item.split("{")[0]).strip()[:60] or code
    cliente, usina, tipo = loc.get(code, ("", "", ""))
    st_raw = r.get("requests_x_status_description") or ""
    desc_full = str(r.get("description") or "").strip()
    return {
        "id_code": r.get("id_code"),
        "cliente": cliente or "—", "usina": usina or "—", "ativo": ativo,
        # `id_item` e `code` do ATIVO. Ficavam de fora porque o card só mostra o nome — mas quem
        # for CRIAR a OS a partir desta solicitação precisa do ativo EXATO. O nome não serve:
        # "Chave Seccionadora 1" existe em várias usinas, e casar por nome escolheu a APG100 para
        # uma solicitação da TESTE - PA (visto ao aprovar a 3534 em 02/09). Errar aqui não quebra
        # nada — cria a OS na usina errada, no sistema do cliente.
        "id_item": r.get("id_item"), "code": code,
        # A cor do status vem do PROPRIO Fracttal, no `status_path_image` ("color: #01C0DD").
        # Copiar a paleta para ca criaria duas verdades: no dia em que eles trocassem a cor de
        # um status, o app seguiria pintando a antiga sem ninguem perceber.
        "cor_status": api._cor_de(r.get("status_path_image")),
        "tipo": tipo or "—",
        "descricao": (desc_full[:90] or "—"),
        "descricao_full": desc_full,
        "observacao": str(r.get("observation") or "").strip(),
        "criado_por": str(r.get("requested_by") or r.get("accounts_name") or "").strip(),
        "data": (str(r.get("date") or r.get("date_incident") or ""))[:19],
        "status_id": r.get("id_status"),
        "status": api._req_status_label(st_raw, r.get("id_status")),
        "os_folio": r.get("wo_folio"),
        "id_work_order": r.get("id_work_order"),
    }


def list_minhas_solicitacoes(id_account=None, limite: int = 120) -> list:
    """Solicitações de serviço (work requests). id_account: None = usuário LOGADO (default);
    "TODOS" = todas; ou um id_account específico = filtra por criador. Cada uma traz a OS ligada
    (wo_folio/id_work_order) e a descrição COMPLETA (p/ o detalhe ao clicar no nº).
    → [{'id_code','cliente','usina','ativo','descricao','descricao_full','observacao','criado_por',
        'data','status_id','status','os_folio','id_work_order'}], mais recentes primeiro."""
    if id_account is None:
        _idp, id_account, _nome = api._current_user_info()
        if id_account is None:
            raise FracttalError("Não consegui identificar seu usuário no Fracttal (e-mail não bate no cadastro).")
        filtro = [{"operator": "=", "property": "id_account", "value": id_account}]
    elif id_account == "TODOS":
        filtro = []
    else:
        filtro = [{"operator": "=", "property": "id_account", "value": id_account}]
    res = api._rpc_call(RPC_REQ_LIST, {"filter": filtro,
                                   "sort": [{"property": "id_code", "direction": "desc"}],
                                   "page": 1, "limit": limite, "start": 0})
    data = res.get("data") if isinstance(res, dict) else res
    loc = api._code_to_loc()
    return [api._req_row_to_d(r, loc) for r in (data if isinstance(data, list) else [])]


def get_solicitacao_por_os(id_work_order):
    """Detalhe (dict no formato do SolicitacaoDialog) da solicitação ligada a esta OS. None se não
    houver. Usado p/ abrir o card da solicitação a partir do card da OS."""
    if not id_work_order:
        return None
    try:
        res = api._rpc_call(RPC_REQ_LIST, {"filter": [{"operator": "=", "property": "id_work_order",
            "value": id_work_order}], "page": 1, "limit": 5, "start": 0})
    except FracttalError:
        return None
    data = res.get("data") if isinstance(res, dict) else res
    loc = api._code_to_loc()
    for r in (data if isinstance(data, list) else []):
        if str(r.get("id_work_order")) == str(id_work_order):
            return api._req_row_to_d(r, loc)
    return None


RPC_REQ_STATUS_INSERT = "requests.requests_x_status_insert"
RPC_REQ_STATUS_LIST = "requests.status_list"      # catálogo id → código do status
RPC_REQ_UPDATE = "requests.requests_update"       # edita campos da solicitação (ex.: observação)

# Os status que faz sentido o PCM escolher na Fila (Levi, 14/09: "mudar o status da Solicitação
# pela visualização do Fila do PCM e pôr o motivo, como no Fracttal"). Ids conferidos ao vivo em
# 14/09 pelo `requests.status_list`, que devolve 13.
#
# A LISTA É CURTA DE PROPÓSITO. Os outros existem mas são CONSEQUÊNCIA, não escolha: OT_IN_PROCESS,
# OT_IN_REVIEW, OT_FINALIZED e OT_CANCEL descrevem a OS que nasceu da solicitação e quem os move é
# o andamento dela; CREATED_GUEST_PORTAL e DELETE_TASK_TODO são de outro fluxo. Oferecer todos
# convidaria a marcar à mão um estado que o Fracttal recalcula sozinho, e aí a tela mentiria.
STATUS_SOLICITACAO = [
    (1,  "OPEN_STATUS",              "Aberta"),
    (7,  "REQUEST_TODO",             "Pendente"),
    (2,  "PROCESS_STATUS",           "Em processo"),
    (4,  "SOLVED_WITHOUT_OT_STATUS", "Resolvida sem OS"),
    (10, "AGAIN_REQUEST_TODO",       "Reaberta (refazer)"),
    (12, "REJECTED",                 "Rejeitada"),
    (5,  "CANCEL_STATUS",            "Cancelada"),
]


def status_solicitacao_catalogo(levantar: bool = False) -> list:
    """[(id, código, rótulo)] do que o Fracttal aceita HOJE, cruzado com a lista curta acima.

    Vai à API para não oferecer um id que aquela conta não tenha; se a chamada falhar, devolve a
    lista local — perder a rede não pode impedir a pessoa de cancelar uma solicitação. `levantar`: o erro sobe em vez da
    lista local, e a resposta VAZIA do Fracttal dá a lista vazia (o catálogo dos status, `catalogos.status`, 31/10/2026: a
    lista local guardada 24 h passaria pelo que o Fracttal aceita; lá ela volta sem ficar guardada; revisão da 4.1)."""
    try:
        res = api._rpc_call(RPC_REQ_STATUS_LIST, {"filter": [], "sort": [], "page": 1,
                                              "limit": 100, "start": 0})
        vivos = {s.get("id") for s in ((res.get("data") if isinstance(res, dict) else res) or [])
                 if isinstance(s, dict)}
    except Exception:                                # noqa: BLE001
        if levantar:
            raise
        return list(STATUS_SOLICITACAO)
    if levantar and not vivos:
        return []
    return [t for t in STATUS_SOLICITACAO if not vivos or t[0] in vivos]


def mudar_status_solicitacao(id_request, id_status: int, codigo: str, note: str = "") -> dict:
    """Muda o status de uma solicitação, com o motivo — a mesma rota que o cancelamento usa desde
    25/06, e que por isso já se sabe que funciona em produção.

    `id_request` é o id_code (o Nº que aparece), `codigo` é o texto estável do status
    (CANCEL_STATUS, REJECTED...), e `note` é o motivo, que o Fracttal guarda no histórico."""
    if id_request in (None, ""):
        raise FracttalError("Solicitação sem número (id) — recarregue a lista.")
    if not codigo:
        raise FracttalError("Status sem código — escolha um status da lista.")
    res = api._rpc_call(RPC_REQ_STATUS_INSERT, {"id_request": str(id_request), "id_status": int(id_status),
                                            "requests_x_status_description": codigo,
                                            "notes": (note or "").strip()})
    if isinstance(res, dict) and res.get("success") is False:
        raise FracttalError(str(res.get("message") or "O Fracttal recusou a mudança de status "
                                                      "(sua conta tem permissão para isso?)."))
    return {"ok": True, "raw": res}


def editar_observacao_solicitacao(id_code, observacao: str) -> dict:
    """Reescreve a OBSERVAÇÃO de uma solicitação (Levi, 14/09).

    CUIDADO QUE ESTA FUNÇÃO TEM E O RESTO DO ARQUIVO NÃO PRECISA TER: o `requests_update` aceita
    campos parciais — sondado em 14/09, ele responde ACTION_DONE com só o `id_code` —, mas não há
    documentação dizendo o que acontece com os campos que NÃO vão no corpo. Se ele tratasse a
    chamada como substituição, mandar só a observação apagaria título, ativo e classificação de
    uma solicitação real.

    Por isso a linha atual é LIDA antes e reenviada inteira, com a observação trocada. Custa uma
    consulta e elimina a dúvida: o que volta é o que estava lá."""
    if not id_code:
        raise FracttalError("Solicitação sem número (id).")
    linha = api._solicitacao_row(id_code)
    if not isinstance(linha, dict):
        raise FracttalError("Não achei a solicitação %s no Fracttal." % id_code)
    corpo = {k: v for k, v in linha.items() if not isinstance(v, (dict, list))}
    corpo["id_code"] = linha.get("id_code") or id_code
    corpo["observation"] = observacao or ""
    res = api._rpc_call(RPC_REQ_UPDATE, corpo)
    if isinstance(res, dict) and res.get("success") is False:
        raise FracttalError(str(res.get("message") or "O Fracttal recusou a edição da observação."))
    return {"ok": True, "raw": res}


def cancelar_solicitacao(id_request, note: str = "") -> dict:
    """Cancela uma SOLICITAÇÃO de serviço (work request): status vira CANCEL_STATUS (id_status=5),
    com uma nota opcional. `id_request` = id_code da solicitação (o Nº mostrado). A AUTORIZAÇÃO é a do
    usuário no Fracttal — se a conta não puder cancelar, a API recusa (FracttalError). → {'ok':True,'raw'}."""
    if id_request in (None, ""):
        raise FracttalError("Solicitação sem número (id) — recarregue o histórico.")
    params = {"id_request": str(id_request), "id_status": 5,
              "requests_x_status_description": "CANCEL_STATUS", "notes": (note or "").strip()}
    res = api._rpc_call(RPC_REQ_STATUS_INSERT, params)
    if isinstance(res, dict) and res.get("success") is False:    # recusa não-sessão (ex.: sem permissão)
        raise FracttalError(str(res.get("message") or "Cancelamento recusado pelo Fracttal "
                                                      "(sua conta tem permissão p/ cancelar solicitações?)."))
    return {"ok": True, "raw": res}


import api  # noqa: E402 — no fim: o `api` importa este módulo

"""os_execucao.py: o cronômetro e o checklist da tarefa da OS.

Iniciar, pausar, retomar e finalizar a execução, fechar as abertas, o motivo de pausa, o tempo trabalhado, e as subtarefas (o
checklist) com as respostas, a validação de segurança e o registro da execução. Tudo pelo `api._rpc_call`, com o login de quem
usa. `_PAUSA_CACHE` (os motivos de pausa, lidos uma vez por processo) mora aqui.

Saiu do `api.py` em 31/10/2026 (etapa 5.3 do canto central, "o que sobra do api.py"): mudou só o lugar, o código é o mesmo. O
`api.py` segue expondo os mesmos nomes (`api.X`), porque a ponte, as rotas e os testes chamam e TROCAM `api.X` pelo nome. Por
isso toda função que este módulo chama, dele ou de fora (o `api._rpc_call`, o que também saiu para outro módulo), e todo número
ajustável (um prazo, um teto) vão pelo `api.`, e enxergam a troca; só as outras constantes e o estado daqui são usados direto. O
módulo termina com `import api`: o `api` o importa no fim do arquivo (a fachada), e só precisa dele na hora da chamada."""

import uuid
from datetime import datetime, timezone
from fracttal_erro import FracttalError


# ── PCM: planos de tarefa de um ativo (MPS/MPA/MPM/Handover) ──────────────────
# ── EXECUTAR a tarefa: preencher subtarefa → salvar → registrar início/fim ───────────────────
# Protocolo colhido do Fracttal web em 21/09/2026 (OS 38299179 / tarefa 59150414). O app de mesa
# não fazia isto: ele CRIA a OS e depois manda o técnico para o Fracttal. O que faltava para
# fechar o ciclo era a parte de escrita do checklist e do registro de horas.
#
# A ORDEM IMPORTA, e é a que a tela deles usa:
#   1. `..._form_items_values_insert`  — grava os valores do checklist
#   2. `..._security_validations_validate` — o Fracttal pergunta a si mesmo se pode registrar
#   3. `..._execution_insert`          — o "Adicionar" do Registro, com início e fim
#   4. `wo_task_get_execution`         — relê para confirmar que entrou
# Pular o passo 2 pode dar um registro recusado sem mensagem clara; ele é barato e é o que a
# própria tela faz antes de abrir a janela de registro.
RPC_WO_FORMIT_VALUES = "tasks.work_orders_task_form_items_values_insert"
RPC_WO_EXEC_LIST     = "tasks.wo_tasks_execution_list"
RPC_WO_EXEC_INSERT   = "tasks.wo_tasks_execution_insert"
RPC_WO_EXEC_GET      = "tasks.wo_task_get_execution"
RPC_WO_SEC_VALIDATE  = "tasks.wo_tasks_security_validations_validate"

# id_task_form_item_type → como o campo se comporta. Os quatro primeiros saem do `solic_spec.TIPO_ID`,
# que foi sondado ao vivo nesta conta. O 4 (Verificação) manda o valor como "1"/"2"/"3" — a ordem
# Aprovado/Alerta/Falhou é a do próprio `solic_spec`, mas NÃO foi confirmada chamando a API: por
# isso a tela mostra os três rótulos e manda o número, em vez de o código escolher sozinho.
TIPO_CAMPO = {1: "texto", 2: "simnao", 3: "num", 4: "verif", 7: "lista"}
VERIF_OPCOES = [("1", "Aprovado"), ("2", "Alerta"), ("3", "Falhou")]
SIMNAO_OPCOES = [("1", "Sim"), ("2", "Não"), ("3", "N/A")]


def subtarefas_da_tarefa(id_work_order_task) -> list:
    """O checklist de UMA tarefa, com o valor que já está lá.

    → [{'id_form_item','descricao','tipo','tipo_nome','valor','obrigatorio','anexo_obrigatorio',
        'n_anexos','opcoes'}], na ordem em que o Fracttal devolve (é a ordem da tela)."""
    if not id_work_order_task:
        return []
    r = api._rpc_call(api.RPC_WO_FORMIT, {"filter": [], "sort": [], "page": 1, "limit": 2500, "start": 0,
                                  "is_tree": False, "node": None,
                                  "id_work_order_task": id_work_order_task})
    data = r.get("data") if isinstance(r, dict) else r
    out = []
    for it in (data if isinstance(data, list) else []):
        if not isinstance(it, dict):
            continue
        tipo = it.get("id_task_form_item_type")
        try:
            tipo = int(tipo)
        except (TypeError, ValueError):
            tipo = 1
        nome = TIPO_CAMPO.get(tipo, "texto")
        opcoes = []
        if nome == "verif":
            opcoes = [{"valor": v, "rotulo": t} for v, t in VERIF_OPCOES]
        elif nome == "simnao":
            opcoes = [{"valor": v, "rotulo": t} for v, t in SIMNAO_OPCOES]
        elif nome == "lista":
            # a lista traz as opções do próprio cadastro; sem elas o campo vira texto livre,
            # que é melhor que um <select> vazio que não deixa preencher nada
            for o in (it.get("dropdown_options") or it.get("options") or []):
                if isinstance(o, dict):
                    d = str(o.get("description") or o.get("value") or "").strip()
                    if d:
                        opcoes.append({"valor": d, "rotulo": d})
        try:
            n_anexos = int(it.get("num_attachments") or 0)
        except (TypeError, ValueError):
            n_anexos = 0
        out.append({
            "id_form_item": it.get("id_work_orders_tasks_form_items"),
            "id_work_order": it.get("id_work_order"),
            "descricao": str(it.get("description") or "").strip(),
            "tipo": tipo, "tipo_nome": nome,
            "valor": "" if it.get("value") is None else str(it.get("value")),
            "obrigatorio": bool(it.get("is_required")),
            "anexo_obrigatorio": bool(it.get("attachments_required")),
            "n_anexos": n_anexos, "opcoes": opcoes})
    return out


RPC_FORMIT_ATTACH = "tasks.wo_tasks_form_items_attachments_list"   # os anexos de UMA subtarefa (pelo id do item)
RPC_FORMIT_ATTACH_DELETE = "tasks.wo_tasks_form_items_attachments_delete"   # tira um anexo da subtarefa (o id do vínculo)
RPC_FILES_DELETE = "tasks.work_orders_tasks_files_delete"            # exclui um anexo da tarefa (pelo id dele)
# O QUE O FRACTTAL FAZ (medido na OS de teste 19259, TESTE - PA, 11/11/2026): a gravação das respostas
# (`work_orders_task_form_items_values_insert`) ACRESCENTA os anexos que vão no `attachments` (cada um vira um registro de
# arquivo e um vínculo com a subtarefa) e não mexe nos que a subtarefa já tem: regravar com a lista inteira DUPLICOU a
# foto, e mandar `[]` não apaga nada. Tirar um anexo da subtarefa é o `wo_tasks_form_items_attachments_delete` com o id do
# vínculo (o `files_delete` do arquivo antes dele dá FOREIGN_KEY_VIOLATION); depois sai o arquivo do vínculo.


def anexos_do_item(id_work_order_task, id_form_item) -> list:
    """Os vínculos de anexo da subtarefa: [{id, id_arquivo, value, description}]. O erro sobe."""
    res = api._rpc_call(RPC_FORMIT_ATTACH, {"page": 1, "limit": 200, "start": 0, "is_tree": False, "node": None,
                                            "id_work_order_task": id_work_order_task,
                                            "id_work_orders_tasks_form_items": id_form_item, "link_attachment": True})
    if isinstance(res, dict) and res.get("success") is False:
        raise FracttalError("Não consegui ler os anexos da subtarefa no Fracttal.")
    d = res.get("data") if isinstance(res, dict) else res
    return [{"id": a.get("id"), "id_arquivo": a.get("id_work_orders_tasks_files"), "value": a.get("value"),
             "description": a.get("description") or ""}
            for a in (d if isinstance(d, list) else []) if isinstance(a, dict) and a.get("id")]


def _gravar_valores(params: list) -> object:
    res = api._rpc_call(RPC_WO_FORMIT_VALUES, params)
    if isinstance(res, dict) and res.get("success") is False:
        cod = str(res.get("message") or "").strip()
        if cod.upper() == "WITHOUT_PERMITS":
            raise FracttalError(_CHECKLIST_SEM_PERMISSAO + "  (WITHOUT_PERMITS)")
        raise FracttalError("O Fracttal recusou o checklist: " + (cod.replace("_", " ").strip() or "motivo não informado"))
    return res


def _linha_valor(id_work_order, id_work_order_task, fid, tipo, valor, anexos) -> dict:
    return {"id_work_orders_tasks_form_items": fid, "id_work_order": id_work_order, "id_meter": None, "id_unit": None,
            "id_work_order_task": id_work_order_task, "value": "" if valor is None else str(valor),
            "attachments": anexos, "is_offline": None, "id_task_form_item_type": tipo}


def anexar_no_item(id_work_order, id_work_order_task, id_form_item, tipo, valor, dados: bytes, nome: str) -> dict:
    """A foto (ou arquivo) NA SUBTAREFA, como o App de Campo faz: o arquivo sobe como anexo da tarefa (S3 +
    `files_insert`, que ignora o item: medido pelo App na OS 10597) e vai, SÓ ELE, no `attachments` da gravação do valor
    da subtarefa (a gravação acrescenta: ver acima). Provado na OS 19259."""
    up = api.attach_imagem_os(id_work_order, id_work_order_task, dados, nome)
    novo = {"value": up["value"], "size": len(dados), "type": 1, "description": nome}
    api._gravar_valores([api._linha_valor(id_work_order, id_work_order_task, id_form_item, tipo, valor, [novo])])
    api.esquecer_os(id_work_order)
    return {"ok": True, "value": up["value"]}


def tirar_do_item(id_work_order, id_work_order_task, id_form_item, id_vinculo) -> dict:
    """Tira um anexo da subtarefa pelo id do vínculo e, depois, o arquivo dele (o que sobra do arquivo é limpeza: a falha
    não desfaz o que saiu). Provado na OS 19259."""
    vinc = next((a for a in api.anexos_do_item(id_work_order_task, id_form_item) if str(a["id"]) == str(id_vinculo)), None)
    if vinc is None:
        raise FracttalError("Este anexo não está mais na subtarefa: reabra os anexos.")
    res = api._rpc_call(RPC_FORMIT_ATTACH_DELETE, {"id": vinc["id"]})
    if isinstance(res, dict) and res.get("success") is False:
        raise FracttalError(str(res.get("message") or "O Fracttal recusou tirar o anexo da subtarefa."))
    if vinc.get("id_arquivo"):
        try:
            api.excluir_anexo_da_tarefa(vinc["id_arquivo"])
        except FracttalError:
            pass
    # a subida pôs o arquivo também nos anexos da tarefa (o caminho do App): sem o vínculo, ele apareceria como anexo da
    # OS (visto na OS 19259). Sai junto, se nenhuma outra subtarefa da tarefa o usa
    try:
        if not any(str(a.get("value")) == str(vinc.get("value")) for a in api.anexos_do_item(id_work_order_task, id_form_item)):
            for a in api._arquivos_da_tarefa(id_work_order_task):
                if str(a.get("value")) == str(vinc.get("value")) and str(a.get("id") or "").isdigit():
                    api.excluir_anexo_da_tarefa(int(a["id"]))
    except FracttalError:
        pass
    api.esquecer_os(id_work_order)
    return {"ok": True}


def _arquivos_da_tarefa(id_work_order_task) -> list:
    r = api._rpc_call("tasks.work_orders_tasks_files_list", {"page": 1, "limit": 500, "start": 0, "is_tree": False,
                                                              "node": None, "id_work_order_task": id_work_order_task})
    d = r.get("data") if isinstance(r, dict) else r
    return [a for a in (d if isinstance(d, list) else []) if isinstance(a, dict)]


def excluir_anexo_da_tarefa(id_anexo) -> dict:
    """Exclui um anexo da tarefa (a aba Anexos), pelo id dele: o `files_delete` que o App de Campo usa na limpeza do
    teste sintético."""
    if not id_anexo:
        raise FracttalError("Anexo sem id: reabra os anexos.")
    res = api._rpc_call(RPC_FILES_DELETE, {"id": id_anexo})
    if isinstance(res, dict) and res.get("success") is False:
        raise FracttalError(str(res.get("message") or "O Fracttal recusou a exclusão do anexo (sua conta tem "
                                                      "permissão?)."))
    return {"ok": True}


def salvar_subtarefas(id_work_order, id_work_order_task, valores: list) -> dict:
    """Grava os valores do checklist. `valores` = [{'id_form_item','valor','tipo'}]. O `attachments` vai vazio: a gravação
    ACRESCENTA anexos e não mexe nos que a subtarefa tem (medido na OS 19259; a lista inteira duplicava a foto).

    SÓ VAI O QUE TEM VALOR, e é assim de propósito: na captura, o campo que a pessoa esvaziou
    simplesmente saiu da lista da segunda gravação. Mandar `value:""` seria inventar um contrato
    que a tela deles não usa — e este endpoint escreve em OS de produção."""
    if not (id_work_order and id_work_order_task):
        raise FracttalError("Sem id da OS ou da tarefa — não dá para gravar o checklist.")
    params = []
    for v in (valores or []):
        if not isinstance(v, dict):
            continue
        fid = v.get("id_form_item")
        val = v.get("valor")
        if fid is None or val is None or str(val).strip() == "":
            continue
        try:
            tipo = int(v.get("tipo") or 1)
        except (TypeError, ValueError):
            tipo = 1
        params.append(api._linha_valor(id_work_order, id_work_order_task, fid, tipo, val, []))
    if not params:
        return {"ok": False, "n": 0, "erro": "Nenhum campo preenchido para gravar."}
    res = api._gravar_valores(params)
    return {"ok": True, "n": len(params), "raw": res}


# 24/10/2026: uma analista de chamados não conseguia salvar o nº do ticket (a subtarefa da OS de acompanhamento) e via
# "O Fracttal recusou o checklist: WITHOUT PERMITS"; outra, na mesma tela, salvava. A gravação vai com a conta de QUEM
# ESTÁ LOGADO, e o perfil dela no Fracttal não pode responder subtarefas: não é o app que libera, e a mensagem diz isso.
_CHECKLIST_SEM_PERMISSAO = ("Sua conta do Fracttal não tem permissão para responder as subtarefas (o checklist) "
                            "das OS. A gravação vai com a sua conta, com as permissões dela; quem libera é o "
                            "administrador do Fracttal (perfil do usuário). Para confirmar: tente preencher a mesma "
                            "subtarefa direto no Fracttal; se lá também recusar, é o perfil.")


def validar_seguranca_tarefa(id_work_order_task) -> dict:
    """As validações de segurança que a tela roda ANTES de abrir o registro de execução.

    Não levanta: quando a conta não tem validação configurada a resposta vem vazia, e isso não é
    erro. Quem chama decide o que fazer com o que voltar."""
    try:
        res = api._rpc_call(RPC_WO_SEC_VALIDATE, {"id_work_order_task": id_work_order_task})
    except FracttalError as e:
        return {"ok": False, "erro": str(e)}
    return {"ok": True, "raw": res}


def execucoes_da_tarefa(id_work_order_task) -> list:
    """Os registros de execução já lançados (o que a aba Registro mostra), do mais novo ao mais velho."""
    if not id_work_order_task:
        return []
    r = api._rpc_call(RPC_WO_EXEC_LIST, {"sort": [{"property": "initial_date", "direction": "desc"},
                                              {"property": "id", "direction": "desc"}],
                                     "page": 1, "limit": 200, "start": 0, "is_tree": False,
                                     "node": None, "id_work_order_task": id_work_order_task})
    data = r.get("data") if isinstance(r, dict) else r
    out = []
    for d in (data if isinstance(data, list) else []):
        if isinstance(d, dict):
            out.append({"id": d.get("id"), "nome": str(d.get("name") or "").strip(),
                        "inicio": d.get("initial_date"), "fim": d.get("final_date"),
                        "nota": str(d.get("note") or "").strip(), "done": bool(d.get("done"))})
    return out


def registrar_execucao(id_work_order_task, inicio, fim=None, note: str = "",
                       nome: str = "", validar: bool = True) -> dict:
    """O "Adicionar" do Registro: lança a execução com data/hora de início e de fim.

    `inicio`/`fim` são datetime COM fuso (o `_iso_z` converte para UTC, que é o que o Fracttal
    guarda). Sem `fim`, usa agora — é o que a tela deles faz.

    `done=True` fecha o registro. `id_wo_tasks_stop_reasons=1` é o motivo de parada que a tela
    manda quando o técnico conclui; os dois saíram da captura e não são escolha do código."""
    if not id_work_order_task:
        raise FracttalError("Sem id da tarefa — não dá para registrar a execução.")
    if inicio is None:
        raise FracttalError("Informe a data e a hora de início da execução.")
    fim = fim or datetime.now(timezone.utc)
    if fim < inicio:
        raise FracttalError("A data de fim não pode ser anterior à de início.")
    if validar:
        api.validar_seguranca_tarefa(id_work_order_task)      # o que a tela faz antes de abrir o registro
    uid = str(uuid.uuid4())
    params = {"id": uid, "id_work_order_task": id_work_order_task, "id_accounts_log": 0,
              "id_account": None, "id_wo_tasks_execution_types": None, "note": note or "",
              "name": nome or api.current_user_name() or "",
              "initial_date": api._iso_z(inicio), "final_date": api._iso_z(fim),
              "done": True, "to_pause": False, "to_stop": False,
              "id_wo_tasks_stop_reasons": 1, "id_wo_tasks_execution_categorizations": None,
              "categorization_description": None, "security_validations": None,
              "actions": [], "idInternal": uid}
    res = api._rpc_call(RPC_WO_EXEC_INSERT, params)
    if isinstance(res, dict) and res.get("success") is False:
        raise FracttalError("O Fracttal recusou o registro: "
                            + (str(res.get("message") or "").replace("_", " ").strip()
                               or "motivo não informado"))
    # RELÊ para confirmar: o insert pode voltar 200 sem ter gravado, e a tela deles relê também.
    # Sem isto, "registrado" seria uma afirmação que ninguém conferiu.
    try:
        api._rpc_call(RPC_WO_EXEC_GET, {"page": 1, "limit": 200, "start": 0, "append": True,
                                    "id_work_order_task": id_work_order_task})
        gravadas = api.execucoes_da_tarefa(id_work_order_task)
    except FracttalError:
        gravadas = []
    achou = any(str(e.get("id")) == uid for e in gravadas)
    return {"ok": True, "id": uid, "confirmado": achou, "n_registros": len(gravadas),
            "inicio": api._iso_z(inicio), "fim": api._iso_z(fim)}


# ══════════════════════════════════════════════════════════════════════════════
# EXECUÇÃO DA TAREFA — iniciar · pausar · retomar · concluir
#
# Fluxo capturado ao vivo no Fracttal web (27/07). Tudo gira no `id_work_order_task`
# (a TAREFA), não na OS — uma OS pode ter várias tarefas, cada uma com seu cronômetro.
#
# POR QUE ISTO IMPORTA para o kanban de Performance: o "fazendo agora" dependia do analista
# LEMBRAR de colar a etiqueta "Atividade em execução". Disciplina manual é exatamente o que
# fez 95% das OS atribuídas a analistas terminarem canceladas. Com o cronômetro do próprio
# Fracttal, ele clica em Iniciar e o tempo é medido — e o tempo de conclusão deixa de ser
# "data de fim menos data de criação", que conta noite e fim de semana como trabalho.
#
# A ASSINATURA (`work_orders_sign_update`) NÃO entra aqui: é etapa da interface web, não do
# servidor — o `concluir_os` fecha OS sem ela desde sempre. E assinatura gerada pelo app seria
# registro falso de que alguém assinou.
# ══════════════════════════════════════════════════════════════════════════════
RPC_EXEC_INSERT = "tasks.work_orders_tasks_execution_insert"
RPC_EXEC_PAUSE = "tasks.wo_tasks_execution_pause"
RPC_EXEC_RESUME = "tasks.wo_tasks_execution_resume"
RPC_EXEC_FINISH = "tasks.work_orders_tasks_execution_finish"
RPC_EXEC_GET = "tasks.wo_task_get_execution"
RPC_EXEC_LIST = "tasks.wo_tasks_execution_list"
RPC_EXEC_TYPES = "tasks.wo_tasks_execution_types_list"
# editar um registro de execução (o início e o fim): capturado no Fracttal web pelo Levi em 09/11/2026 (o id do registro,
# o início em UTC com o Z, `to_pause` False e `to_stop` True: o registro segue encerrado)
RPC_EXEC_UPDATE = "tasks.wo_tasks_execution_update"

_PAUSA_CACHE = []       # UMA lista, que nunca é religada: o `api._PAUSA_CACHE` é este mesmo objeto (o `motivos_pausa` muda o conteúdo)


def motivos_pausa() -> list:
    """Catálogo de motivos de pausa → [{'id','descricao'}]. Cacheado: não muda no meio do dia. O cache é mudado no lugar
    (`[:] =`) e não religado com `global`: o `api._PAUSA_CACHE` (a fachada) é este objeto, e religar o nome o deixava vazio para
    sempre, enquanto quem limpasse o apelido não limparia o cache de verdade (revisão final da etapa 5)."""
    if _PAUSA_CACHE:
        return _PAUSA_CACHE
    res = api._rpc_call(RPC_EXEC_TYPES, {"filter": [], "sort": [{"property": "description",
                                                             "direction": "asc"}],
                                     "page": 1, "limit": 200, "start": 0,
                                     "is_tree": False, "node": None})
    data = res.get("data") if isinstance(res, dict) else res
    _PAUSA_CACHE[:] = [{"id": d.get("id"), "descricao": str(d.get("description") or "").strip()}
                       for d in (data if isinstance(data, list) else []) if d.get("id")]
    return _PAUSA_CACHE


RPC_WO_TASKS_NEW = "tasks.work_orders_tasks_new_list"


def id_tarefa_da_os(id_work_order):
    """`id_work_order_task` da PRIMEIRA tarefa da OS — é nela que o cronômetro roda.

    USA O CAMPO `id` DESTE endpoint, e não o `_ids_tarefas_da_os` (que serve aos ANEXOS e
    prefere outros campos). A diferença derrubou o primeiro teste ao vivo: aquele devolvia
    `id_task` = 20878948, que é o MODELO da tarefa, não a tarefa desta OS — o Fracttal recusou
    com FOREIGN_KEY_VIOLATION. O valor certo da mesma OS é `id` = 55875684.
    Conferido contra a captura do Levi: WO 36323580 → id 55869196, exatamente o que o web usa."""
    if not id_work_order:
        return None
    try:
        r = api._rpc_call(RPC_WO_TASKS_NEW, {"filter": [], "sort": [], "page": 1, "limit": 200,
                                         "start": 0, "is_tree": False, "node": None,
                                         "id_work_order": id_work_order})
    except FracttalError:
        return None
    d = (r.get("data") if isinstance(r, dict) else r) or []
    for t in d:
        if isinstance(t, dict) and t.get("id"):
            return t["id"]
    return None


EXEC_ENCERRADA = 3          # id_wo_tasks_execution_status
ACAO_RODANDO, ACAO_PAUSADA = 1, 0    # action_type


def execucao_atual(id_work_order_task) -> dict:
    """Estado do cronômetro → {'estado','inicio','trabalhado_s','pausado_s','motivo','raw'}.
    estado: 'parada' (nunca começou ou já encerrou) | 'rodando' | 'pausada'.

    LIDO DOS CAMPOS CERTOS, não deduzido por data (conferido contra uma execução real,
    tarefa 55869196): a resposta traz `id_wo_tasks_execution_status` (3 = encerrada) e uma
    lista `actions` com os SEGMENTOS do ciclo — cada um com `action_type` (1 = IN_PROGRESS,
    0 = PAUSED) e `duration_seconds`.

    É daí que sai o TEMPO REAL de trabalho: soma dos segmentos em andamento, sem as pausas.
    Muito melhor que "data de fim menos data de criação", que conta noite e fim de semana."""
    vazio = {"estado": "parada", "inicio": None, "trabalhado_s": 0, "pausado_s": 0,
             "motivo": "", "raw": None}
    if not id_work_order_task:
        return vazio
    try:
        res = api._rpc_call(RPC_EXEC_GET, {"page": 1, "limit": 200, "start": 0, "append": True,
                                       "id_work_order_task": id_work_order_task})
    except FracttalError:
        return vazio
    d = res.get("data") if isinstance(res, dict) else res
    if isinstance(d, list):
        d = d[0] if d else None
    if not isinstance(d, dict) or not d:
        return vazio
    # TAREFA NUNCA INICIADA: a resposta NÃO vem vazia — vem um esqueleto com todas as chaves
    # em null. `not d` não pega isso (o dict tem chaves), e sem final_date e sem actions o
    # código caía no ramo "rodando" — ou seja, toda tarefa nunca cronometrada apareceria como
    # EM EXECUÇÃO. Quem diz que existe execução é o `initial_date`.
    if not d.get("initial_date"):
        return vazio

    acoes = [a for a in (d.get("actions") or []) if isinstance(a, dict)]
    trab = sum((a.get("duration_seconds") or 0) for a in acoes
               if a.get("action_type") == ACAO_RODANDO)
    paus = sum((a.get("duration_seconds") or 0) for a in acoes
               if a.get("action_type") == ACAO_PAUSADA)
    ultima = acoes[-1] if acoes else {}

    if d.get("id_wo_tasks_execution_status") == api.EXEC_ENCERRADA or d.get("final_date"):
        estado = "parada"
    elif ultima.get("action_type") == ACAO_PAUSADA:
        estado = "pausada"
    else:
        estado = "rodando"
    return {"estado": estado, "inicio": str(d.get("initial_date") or "")[:19],
            "trabalhado_s": int(trab), "pausado_s": int(paus),
            "motivo": str(ultima.get("paused_reason_description") or "").strip()
                      if estado == "pausada" else "",
            "raw": d}


def iniciar_execucao(id_work_order_task) -> dict:
    """Liga o cronômetro. `initial_date` em UTC com Z, como o web manda."""
    if not id_work_order_task:
        return {"ok": False, "erro": "OS sem tarefa — não dá para iniciar."}
    import datetime as _d
    agora = _d.datetime.now(_d.timezone.utc)
    iso = agora.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (agora.microsecond // 1000)
    res = api._rpc_call(RPC_EXEC_INSERT, {"page": 1, "limit": 200, "start": 0, "append": True,
                                      "id_wo_tasks_execution_categorizations": None,
                                      "id_work_order_task": id_work_order_task,
                                      "initial_date": iso, "done": False})
    if isinstance(res, dict) and res.get("success") is False:
        return {"ok": False, "erro": str(res.get("message") or "nao consegui iniciar")}
    return {"ok": True, "raw": res}


def pausar_execucao(id_work_order_task, id_motivo, nota="") -> dict:
    if not id_work_order_task or not id_motivo:
        return {"ok": False, "erro": "escolha o motivo da pausa."}
    res = api._rpc_call(RPC_EXEC_PAUSE, {"page": 1, "limit": 200, "start": 0, "append": True,
                                     "id_work_order_task": id_work_order_task,
                                     "id_wo_tasks_execution_types": id_motivo,
                                     "note": (nota or "").strip()})
    if isinstance(res, dict) and res.get("success") is False:
        return {"ok": False, "erro": str(res.get("message") or "nao consegui pausar")}
    return {"ok": True, "raw": res}


def retomar_execucao(id_work_order_task) -> dict:
    res = api._rpc_call(RPC_EXEC_RESUME, {"page": 1, "limit": 200, "start": 0, "append": True,
                                      "id_work_order_task": id_work_order_task})
    if isinstance(res, dict) and res.get("success") is False:
        return {"ok": False, "erro": str(res.get("message") or "nao consegui retomar")}
    return {"ok": True, "raw": res}


def finalizar_execucao(id_work_order_task) -> dict:
    """Para o cronômetro. CUIDADO com o nome do parâmetro: aqui é `id`, e nos outros três é
    `id_work_order_task` — mesmo valor, nome diferente. Está assim no fluxo do web."""
    res = api._rpc_call(RPC_EXEC_FINISH, {"page": 1, "limit": 200, "start": 0, "append": True,
                                      "id": id_work_order_task, "view_stop_drawer": False})
    if isinstance(res, dict) and res.get("success") is False:
        return {"ok": False, "erro": str(res.get("message") or "nao consegui concluir")}
    return {"ok": True, "raw": res}


def editar_execucao(id_execucao, inicio, fim=None) -> dict:
    """Muda o início (e o fim) de um registro de execução já encerrado, como o "editar registro" do Fracttal web
    (09/11/2026, Levi: "A ideia é poder editar o início e fim da atividade!"). `inicio`/`fim` são datetime COM fuso; vão
    em UTC com o Z. Quem chama relê o registro: o Fracttal pode aceitar calado."""
    if not id_execucao or inicio is None:
        return {"ok": False, "erro": "Falta o registro ou o início."}
    params = {"id": id_execucao, "initial_date": api._iso_z(inicio)}
    if fim is not None:
        params["final_date"] = api._iso_z(fim)
    params.update(to_pause=False, to_stop=True)
    res = api._rpc_call(RPC_EXEC_UPDATE, params)
    if isinstance(res, dict) and res.get("success") is False:
        return {"ok": False, "erro": str(res.get("message") or "o Fracttal recusou a edição do registro").replace("_", " ")}
    return {"ok": True}


def execucoes_abertas(id_work_order_task) -> list:
    """Execuções da tarefa que NUNCA fecharam (`final_date` vazio). Normalmente é lista vazia."""
    try:
        ex = api.historico_execucao(id_work_order_task)
    except FracttalError:
        return []
    return [e for e in ex
            if not e.get("final_date") or str(e.get("final_date")).lower() == "none"]


def _dono_execucao(e: dict) -> str:
    """Nome de quem abriu a execução (para a mensagem de erro)."""
    return str(e.get("name") or e.get("personnel_description") or "").strip() or "outro usuário"


def fechar_execucoes_abertas(id_work_order_task) -> dict:
    """Fecha as execuções abertas da tarefa que são DO USUÁRIO LOGADO.
    → {'ok', 'fechadas', 'restantes', 'alheias': [...], 'erro'}.

    Caso real que trouxe esta função (OS 10215, 29/07): o Levi tentou concluir quatro vezes e a OS
    não fechava, sem erro nenhum na tela. A tarefa tinha DUAS execuções — a dele, encerrada, e uma
    de **outra pessoa** aberta desde o dia anterior (`IN_PROGRESS`, `final_date` nulo). O
    `work_orders_recalculate` roda com `verify_work_in_progress: True` e recusa fechar OS com
    trabalho em andamento.

    Dois enganos estavam somados:
    1. confiar no `wo_task_get_execution`, que devolve só a execução MAIS RECENTE — o app via a
       do próprio usuário, fechada, e achava que não havia nada rodando. Quem conta a verdade é o
       `wo_tasks_execution_list`;
    2. o `finish` NÃO encerra cronômetro dos outros: responde `USER_HAS_EXECUTION_IN_PROGRESS`.
       Cronômetro alheio só quem abriu encerra (ou alguém com permissão, pelo Fracttal web) —
       daí devolver o nome e a data em vez de insistir num comando que a API nunca vai aceitar.

    Execução pausada não aceita `finish` direto: precisa RETOMAR antes."""
    if not id_work_order_task:
        return {"ok": True, "fechadas": 0, "restantes": 0, "alheias": []}
    try:
        eu = api._current_user_info()[0]
    except Exception:
        eu = None
    fechadas, erro = 0, ""
    for _ in range(4):                       # teto: nunca vimos mais de 2, mas não fica em laço
        minhas = [e for e in api.execucoes_abertas(id_work_order_task)
                  if eu is None or e.get("id_personnel") == eu]
        if not minhas:
            break
        try:
            api.retomar_execucao(id_work_order_task)          # pausada não aceita finish
        except FracttalError:
            pass
        r = api.finalizar_execucao(id_work_order_task)
        if isinstance(r, dict) and r.get("ok") is False:
            erro = str(r.get("erro") or "")
            break
        fechadas += 1
    restantes = api.execucoes_abertas(id_work_order_task)
    alheias = [e for e in restantes if eu is not None and e.get("id_personnel") != eu]
    if alheias:
        quem = "; ".join("%s (desde %s)" % (api._dono_execucao(e), api.fmt_data_br(e.get("initial_date")))
                         for e in alheias[:3])
        erro = ("o cronômetro desta tarefa está aberto no nome de %s. O Fracttal não deixa você "
                "encerrar execução de outra pessoa — peça para quem iniciou parar, ou encerre pelo "
                "Fracttal web. Enquanto estiver aberto, a OS não fecha." % quem)
    elif restantes and not erro:
        erro = ("ainda há %d execução(ões) aberta(s) nesta tarefa — o Fracttal não fecha OS com "
                "trabalho em andamento." % len(restantes))
    return {"ok": not restantes, "fechadas": fechadas, "restantes": len(restantes),
            "alheias": alheias, "erro": erro}


LABEL_EM_EXECUCAO = "Atividade em execução"      # 3377 — é ela que põe o card em "Em processo"


def marcar_em_execucao(id_work_order, ligado: bool = True) -> dict:
    """Liga/desliga a etiqueta 'Atividade em execução' na OS.

    É a etiqueta, e não o status do Fracttal, que decide a coluna do board (`perf_spec.em_execucao`).
    MEDIDO na OS 10152: apesar do `append: True`, o `work_order_labels_sync` **substitui** o
    conjunto — então tirar a etiqueta é remandar a lista SEM ela. Por isso é preciso ler as atuais
    antes. Se sobrar lista vazia o `apply_labels` recusa (guard dele); na prática não acontece,
    porque toda OS daqui carrega a PERFORMANCE junto."""
    if not id_work_order:
        return {"ok": False, "erro": "OS sem id."}
    alvo = api.label_id_por_nome(LABEL_EM_EXECUCAO)
    if not alvo:
        return {"ok": False, "erro": "etiqueta '%s' não existe no Fracttal." % LABEL_EM_EXECUCAO}
    atuais = [e.get("id") for e in ((api.get_os_detalhes(id_work_order) or {}).get("etiquetas") or [])
              if e.get("id")]
    novas = ([i for i in atuais if i != alvo] + [alvo]) if ligado else \
            [i for i in atuais if i != alvo]
    if set(novas) == set(atuais):
        return {"ok": True, "sem_mudanca": True}
    if not novas:
        return {"ok": False, "erro": "não dá para deixar a OS sem nenhuma etiqueta."}
    return api.apply_labels(id_work_order, novas)


def iniciar_execucao_os(id_work_order, id_work_order_task) -> dict:
    """Dá play E marca a OS como 'Atividade em execução' — para quem usa é UM gesto: apertar o
    play tem de mover o card para a coluna 'Em processo'. A etiqueta é o efeito colateral, então
    uma falha nela NÃO invalida o cronômetro: volta em `etiqueta_erro` para a tela avisar."""
    r = api.iniciar_execucao(id_work_order_task)
    if r.get("ok"):
        try:
            e = api.marcar_em_execucao(id_work_order, True)
            if not e.get("ok"):
                r["etiqueta_erro"] = e.get("erro")
        except Exception as exc:
            r["etiqueta_erro"] = str(exc)[:200]
    return r


def finalizar_execucao_os(id_work_order, id_work_order_task) -> dict:
    """Para o cronômetro e MANTÉM o 'Atividade em execução'.

    A v111 tirava a etiqueta aqui e o card voltava para "Não iniciada" — errado, e o Levi
    corrigiu: "mesmo com a OS pausada precisa continuar como Em processo porque foi iniciada".
    Uma vez iniciada, a OS só sai de "Em processo" quando é CONCLUÍDA (`concluir_os_analise`).
    Parar o cronômetro é só encerrar o tempo de trabalho, não devolver a OS para a fila."""
    return api.finalizar_execucao(id_work_order_task)


def historico_execucao(id_work_order_task) -> list:
    """Todas as execuções da tarefa (mais recente primeiro) — daqui sai o tempo REAL de trabalho,
    já descontando as pausas."""
    res = api._rpc_call(RPC_EXEC_LIST, {"sort": [{"property": "initial_date", "direction": "desc"},
                                             {"property": "id", "direction": "desc"}],
                                    "page": 1, "limit": 200, "start": 0, "is_tree": False,
                                    "node": None, "id_work_order_task": id_work_order_task})
    d = res.get("data") if isinstance(res, dict) else res
    return d if isinstance(d, list) else []


def tempo_trabalhado(id_work_order_task):
    """Segundos EFETIVAMENTE trabalhados na tarefa, somando todas as execuções. None quando a
    tarefa nunca foi cronometrada.

    Usa o `total_active_seconds` que o PRÓPRIO Fracttal calcula por execução — conferido contra
    uma execução real (tarefa 55869196): 27 s, idêntico à soma dos segmentos IN_PROGRESS
    (5 + 22), com os 3 s de pausa de fora.

    É a métrica que substitui "data de fim menos data de criação", que contava noite, fim de
    semana e tempo de espera como trabalho."""
    if not id_work_order_task:
        return None
    try:
        h = api.historico_execucao(id_work_order_task)
    except FracttalError:
        return None
    if not h:
        return None
    total = 0
    achou = False
    for e in h:
        if not isinstance(e, dict):
            continue
        v = e.get("total_active_seconds")
        if v is None:                       # execução antiga sem o campo: soma os segmentos
            v = sum((a.get("duration_seconds") or 0)
                    for a in (e.get("actions") or []) if isinstance(a, dict)
                    and a.get("action_type") == ACAO_RODANDO)
        total += int(v or 0)
        achou = True
    return total if achou else None


def tempo_trabalhado_em_massa(ids_work_order, max_workers=8) -> dict:
    """{id_work_order: segundos_trabalhados | None} em paralelo.

    Duas chamadas por OS (achar a tarefa + ler o histórico), então nunca use isto no quadro
    inteiro — só na tela de UMA pessoa, onde são poucas OS."""
    ids = [i for i in (ids_work_order or []) if i]
    if not ids:
        return {}

    def _um(wid):
        try:
            return wid, api.tempo_trabalhado(api.id_tarefa_da_os(wid))
        except Exception:
            return wid, None

    out = {}
    with api._ExecutorComContexto(max_workers=min(max_workers, len(ids))) as ex:
        for wid, seg in ex.map(_um, ids):
            out[wid] = seg
    return out


import api  # noqa: E402 — no fim: o `api` importa este módulo

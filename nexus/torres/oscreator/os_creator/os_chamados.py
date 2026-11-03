"""os_chamados.py: os chamados de garantia nas OS.

O bloco "CHAMADO" da observação da OS (montar e ler), a lista de chamados, as OS de Performance por período (a carga da equipe),
o status de vários chamados em paralelo, a OS 3 (os tickets), a OS de chamado filha de uma OS, as últimas OS de um ativo e as
respostas da inspeção. Criar as OS do chamado (a de análise, a de inspeção, a OS nova no mesmo ativo) está em `os_criar.py`.

Saiu do `api.py` em 31/10/2026 (etapa 5.3 do canto central, "o que sobra do api.py"): mudou só o lugar, o código é o mesmo. O
`api.py` segue expondo os mesmos nomes (`api.X`), porque a ponte, as rotas e os testes chamam e TROCAM `api.X` pelo nome. Por
isso toda função que este módulo chama, dele ou de fora (o `api._rpc_call`, o que também saiu para outro módulo), e todo número
ajustável (um prazo, um teto) vão pelo `api.`, e enxergam a troca; só as outras constantes e o estado daqui são usados direto. O
módulo termina com `import api`: o `api` o importa no fim do arquivo (a fachada), e só precisa dele na hora da chamada."""

from datetime import datetime, timedelta, timezone
from fracttal_erro import FracttalError


_CHAMADO_MK  = "━━━ CHAMADO ━━━"
_CHAMADO_FIM = "━━━━━━━━━━━━━━━━"
# (rótulo no texto, chave no dict) — ordem = ordem no bloco
_CHAMADO_CAMPOS = [("OS de abertura", "os_pai"), ("Ticket/RMA", "ticket"),
                   ("Serial Number", "serial"), ("Status", "status"),
                   ("Fabricante", "fabricante"), ("Motivo", "motivo"), ("Resolução", "resolucao")]


def bloco_chamado(dados: dict) -> str:
    """Monta o BLOCO padrão do chamado (legível + parseável) p/ gravar na observação da OS.
    O mesmo texto serve pros formatos ANTIGOS (colado na OS) e pra o board LER."""
    linhas = [_CHAMADO_MK]
    for rot, k in _CHAMADO_CAMPOS:
        v = str((dados or {}).get(k) or "").strip() or "—"
        linhas.append(f"{rot}: {v}")
    linhas.append(_CHAMADO_FIM)
    return "\n".join(linhas)


def parse_bloco_chamado(texto) -> dict:
    """INVERSO: lê o bloco CHAMADO de uma observação → {os_pai,ticket,serial,status,fabricante,
    motivo,resolucao}. {} se não tiver o bloco. Tolera acento/caixa no rótulo. '—'/vazio → ''."""
    t = str(texto or "")
    if _CHAMADO_MK not in t and "chamado" not in t.lower():
        return {}
    def _norm(s):
        import unicodedata
        return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c)).strip()
    rot2k = {_norm(r): k for r, k in _CHAMADO_CAMPOS}
    out = {}
    for linha in t.splitlines():
        if ":" not in linha:
            continue
        rot, val = linha.split(":", 1)
        k = rot2k.get(_norm(rot))
        if k:
            v = val.strip()
            out[k] = "" if v in ("", "—") else v
    return out


def list_chamados(de=None, ate=None, status_ids=None, info: dict = None, meta_ja: dict = None) -> list:
    """OSs com a etiqueta CHAMADOS no período [de, ate] (de TODOS os criadores), mais recentes
    primeiro. [] se a etiqueta 'CHAMADOS' não existir no Fracttal (e o `info` fica sem o total). `info`
    recebe o total do período (o do `list_minhas_os`); `meta_ja`, o que já se sabia das OS fechadas (ver lá)."""
    lid = api._label_id("CHAMADOS")
    if not lid:
        return []
    return api.list_minhas_os(modo="criadas", id_account="TODOS", id_label=lid,
                          de=de, ate=ate, status_ids=status_ids, info=info, meta_ja=meta_ja)


def total_chamados(de=None) -> int:
    """Quantas OS com a etiqueta CHAMADOS o Fracttal dá a quem está logado desde `de` (a etiqueta e 1 página de 1
    linha): a conferência de que a pessoa vê o mesmo quadro que a cópia dividida do Acompanhamento de chamados
    (19/10/2026). 0 sem a etiqueta."""
    lid = api._label_id("CHAMADOS")
    if not lid:
        return 0
    return int((api.list_minhas_os_pagina("criadas", "TODOS", lid, de, None, None, "", 1, 1) or {}).get("total") or 0)


def list_performance(de=None, ate=None) -> list:
    """OSs com a etiqueta PERFORMANCE no período — a carga do kanban de carga da equipe.

    UMA CONSULTA para o board inteiro. Cada linha já traz `atribuido_a`, `status_id`, `etiquetas`
    e `note`, que é tudo o que o `perf_spec` precisa para dizer de quem é, em que estado está e
    qual a prioridade. Uma busca por analista custaria N vezes isso sem trazer nada a mais.
    Medido em 26/07: **378 OS em 3,8 s** para 90 dias, com todos os criadores.
    """
    lid = api._label_id(api.perf_spec_nome_etiqueta())
    if not lid:
        return []
    return api.list_minhas_os(modo="criadas", id_account="TODOS", id_label=lid, de=de, ate=ate)


def perf_spec_nome_etiqueta():
    """Nome da etiqueta do setor. Isolado numa função para o api não importar o perf_spec
    (que é regra de tela) e criar ciclo."""
    return "PERFORMANCE"


# Subtarefa → chave do painel. A API NÃO deixa o app editar OS já criada, mas a equipe de chamados
# edita a subtarefa no Fracttal web enquanto a OS está aberta — então o status VIVO se lê daqui,
# não do bloco da observação (que fica congelado no que foi gravado na criação).
_CHAMADO_SUB = {
    "status do chamado": "status",
    "fabricante": "fabricante",
    "no do chamado / protocolo": "ticket",
    "ticket / rma": "ticket",
    "numero de serie": "serial",
    "serial number": "serial",
    "no do rma": "rma",
    "garantia": "garantia",
    "equipamento defeituoso coletado?": "coletado",
}


def _chave_sub(desc):
    d = api._norm_txt(desc)
    return _CHAMADO_SUB.get(d)


def status_chamado_em_massa(ids, max_workers: int = 8) -> dict:
    """Lê as subtarefas de VÁRIAS OSs de chamado em paralelo → {id: {status,fabricante,ticket,…}}.
    Medido: ~35 ms por OS com 8 threads (24 OSs em 0,8 s), então dá pra carregar o painel inteiro."""
    ids = [i for i in (ids or []) if i]
    if not ids:
        return {}

    def _um(i):
        try:
            res = api._rpc_call(api.RPC_WO_FORMIT, {"id_work_order": i, "sort": []})
        except FracttalError:
            return i, {}
        out = {}
        for it in ((res.get("data") or []) if isinstance(res, dict) else []):
            k = api._chave_sub(it.get("description"))
            if not k:
                continue
            v = str(api._form_item_resposta(it) or "").strip()
            if v:
                out[k] = v
        return i, out

    with api._ExecutorComContexto(max_workers=min(max_workers, len(ids))) as ex:
        return dict(ex.map(_um, ids))


def tickets_os3_em_massa(ids, max_workers: int = 8) -> dict:
    """O nº do ticket de VÁRIAS OS de acompanhamento de chamado (a OS 3), em paralelo → {id: ticket}.

    A OS 3 nasce no servidor do App de Campo com UMA subtarefa — "Nº do ticket ou protocolo aberto no fabricante" — e é
    ela que diz em que coluna do quadro do Acompanhamento a OS está (Levi, 27/09: "OSs que chegam, que a analista de chamados já
    escreveu número de tickets e OSs finalizadas"). Casa pelo texto ("ticket" ou "protocolo") e não pela frase exata:
    a frase mora no código do App, e uma vírgula mudada lá não pode esvaziar a coluna aqui.

    `None` = NÃO LI (o Fracttal recusou aquela OS); `""` = li e está vazio. São coisas diferentes para quem desenha."""
    ids = [i for i in dict.fromkeys(ids or []) if i]
    if not ids:
        return {}

    def _um(i):
        try:
            res = api._rpc_call(api.RPC_WO_FORMIT, {"id_work_order": i, "sort": []})
        except FracttalError:
            return i, None
        for it in ((res.get("data") or []) if isinstance(res, dict) else []):
            d = api._norm_txt(it.get("description"))
            if "ticket" in d or "protocolo" in d:
                return i, str(api._form_item_resposta(it) or "").strip()
        return i, ""

    with api._ExecutorComContexto(max_workers=min(max_workers, len(ids))) as ex:
        return dict(ex.map(_um, ids))


def get_chamado_de_os(id_work_order) -> dict:
    """A OS de CHAMADO filha desta OS (ou None). Usada no card da OS: com chamado, o botão vira
    "Ver chamado N" e o nº aparece no bloco de vínculos — evita abrir chamado duplicado.
    Filtra por id_parent_wo NO SERVIDOR (testado: devolve só a filha) e confere a etiqueta, porque
    clone e desdobramento de OS também usam OS pai e não são chamado.
    → {'id','folio','status','status_id'} ou None."""
    if not id_work_order:
        return None
    lid = api._label_id("CHAMADOS")
    try:
        res = api._rpc_call(api.RPC_WO_LIST, {"page": 1, "limit": 50, "start": 0, "append": True, "sort": [],
                                      "filter": [{"operator": "=", "property": "id_parent_wo",
                                                  "value": id_work_order}]})
    except FracttalError:
        return None
    for w in ((res.get("data") or []) if isinstance(res, dict) else []):
        etiqs = [str((l or {}).get("description") or "").strip().upper()
                 for l in (w.get("labels") or []) if isinstance(l, dict)]
        ids = [(l or {}).get("id") for l in (w.get("labels") or []) if isinstance(l, dict)]
        if "CHAMADOS" not in etiqs and (not lid or lid not in ids):
            continue
        stid = w.get("id_status_work_order")
        return {"id": w.get("id"), "folio": w.get("wo_folio"),
                "status_id": stid, "status": api.WO_STATUS.get(stid, "—")}
    return None


LABEL_CHAMADOS = "CHAMADOS"
# A inspeção NÃO leva CHAMADOS. O fluxo que o Levi fechou em 30/07 tem TRÊS OS:
#   religamento do COS → INSPEÇÃO (esta) → OS de chamado.
# Como o painel da analista de chamados é montado pela etiqueta CHAMADOS, dar essa etiqueta à inspeção faria a
# OS entrar na fila dela antes de o técnico ter ido a campo. "Chamado Garantia" (id 4821) já
# existia no Fracttal e estava sem uso nenhum (0 OS) — diz "isto caminha para uma garantia" sem
# ser a fila do chamado.
LABEL_INSPECAO = "Aguardando Garantia"   # id 2036, já existia no Fracttal (Levi, 30/07)
TIPO_INSPECAO = "Inspeção"


def ultimas_os_do_ativo(id_item, limite: int = 10, com_tipo: bool = True) -> list:
    """Últimas OS daquele ativo, mais recente primeiro.
    → [{'folio','id','descricao','event_date','status','tipo_tarefa'}].

    Serve ao campo "OS pai" da inspeção: quem abre precisa lembrar qual religamento originou o
    caso, e ninguém decora número de OS.

    Filtra por `id_item` NO SERVIDOR — sondado em 30/07 e funciona (APG100-INVR1.1 → total=4).
    Varrer as OS recentes e casar o code no cliente, que foi a primeira ideia, só olharia as
    últimas dezenas do sistema inteiro: ativo com OS de meses atrás voltaria vazio."""
    if not id_item:
        return []
    try:
        res = api._rpc_call(api.RPC_WO_LIST, {"page": 1, "limit": max(1, int(limite)), "start": 0,
                                      "append": True,
                                      "sort": [{"property": "id", "direction": "desc"}],
                                      "filter": [{"operator": "=", "property": "id_item",
                                                  "value": id_item}]})
    except FracttalError:
        return []
    out = []
    for w in ((res.get("data") or []) if isinstance(res, dict) else []):
        d = api._shape_wo_row(w)
        out.append({"folio": d.get("folio"), "id": d.get("id"), "descricao": d.get("descricao"),
                    "event_date": d.get("event_date") or d.get("data"), "status": d.get("status"),
                    "tipo_tarefa": ""})
    out = out[:limite]
    if com_tipo and out:
        # o tipo de tarefa não vem na listagem (só no nível tarefa). São ≤10 ids: uma chamada só.
        meta = api._meta_tarefa_por_os([d["id"] for d in out])
        for d in out:
            d["tipo_tarefa"] = (meta.get(d["id"], {}) or {}).get("tipo_tarefa", "")
    return out


def os_dos_ativos(ids_itens, limite: int = 400) -> list:
    """Todas as OS de um CONJUNTO de ativos, mais recente primeiro, já com tipo de tarefa e as
    duas datas (aberta / fechada).

    → [{'folio','id','descricao','ativo','usina','status','tipo_tarefa','aberta','fechada'}]

    Serve à lupa da aba Tickets, onde se procura a OS de um ativo — ou da usina inteira — para
    vincular a uma ocorrência.

    UMA CHAMADA para o conjunto todo: sondado em 31/08, o filtro aceita `operator: "in"` numa
    lista de `id_item` (um ativo devolveu total=179; seis, 201). Consultar ativo por ativo, que
    era o caminho óbvio, custaria uma requisição por inversor — numa usina com 60 ativos, 60.

    O filtro por NOME de usina não existe no servidor: `like` em items_log_descriptions e em
    items_description são IGNORADOS (devolveram o total inteiro, 12.511, nos dois casos). Por
    isso o escopo "usina" é resolvido no cliente, montando a lista de ids do catálogo.

    Tipo de tarefa e data de fim não vêm na listagem — são do nível TAREFA e chegam pelo
    `_meta_tarefa_por_os`, que agrupa de 130 em 130 e roda em paralelo."""
    ids = [i for i in dict.fromkeys(ids_itens or []) if i]
    if not ids:
        return []
    filtro = [{"operator": "in", "property": "id_item", "value": ids}]
    linhas, start, page = [], 0, 1
    while len(linhas) < limite and page <= 20:
        try:
            r = api._rpc_call(api.RPC_WO_LIST, {"page": page, "limit": 100, "start": start,
                                        "append": True, "filter": filtro,
                                        "sort": [{"property": "id", "direction": "desc"}]})
        except FracttalError:
            break
        data = (r.get("data") or []) if isinstance(r, dict) else []
        if not data:
            break
        linhas.extend(data)
        start += len(data)
        page += 1
        if len(data) < 100:
            break
    out = []
    for w in linhas[:limite]:
        d = api._shape_wo_row(w)
        out.append({"folio": d.get("folio"), "id": d.get("id"), "descricao": d.get("descricao"),
                    "ativo": d.get("ativo"), "usina": d.get("usina"), "status": d.get("status"),
                    "tipo_tarefa": "", "aberta": d.get("data"), "fechada": d.get("data_fim")})
    if out:
        meta = api._meta_tarefa_por_os([d["id"] for d in out])
        for d in out:
            m = meta.get(d["id"]) or {}
            d["tipo_tarefa"] = m.get("tipo_tarefa", "")
            # a data de fim da LISTAGEM costuma vir vazia; a da tarefa é a que existe de fato
            d["fechada"] = d["fechada"] or m.get("data_fim") or ""
    return out


def codigos_os_recentes(dias: int = 30) -> list:
    """Codes dos ativos com OS CRIADA nos últimos `dias` — qualquer criador, qualquer status.
    → lista ordenada de codes (p/ a aba Ativos tingir quem teve OS recente).

    O code vem de `items_log_descriptions` — o ÚNICO campo da linha da listagem que o carrega
    (medido: `items_description` nem existe nesse nível; ele é da TAREFA). É uma lista
    stringificada com um `{ CODE }` por ativo da OS, daí o findall e não o `_extrai_code`, que
    só pega o último. ~17 páginas para um mês (~1.650 OS); roda em worker. Teto de 40 páginas —
    melhor um mês parcial que travar."""
    import re
    de = (datetime.now(timezone.utc) - timedelta(days=max(1, int(dias)))).strftime("%Y-%m-%d")
    cond = [{"operator": ">=", "property": "creation_date", "value": de}]
    out, page, start = set(), 1, 0
    while page <= 40:
        try:
            r = api._rpc_call(api.RPC_WO_LIST, {"page": page, "limit": 100, "start": start, "append": True,
                                        "filter": cond,
                                        "sort": [{"property": "id", "direction": "desc"}]})
        except FracttalError:
            break
        data = (r.get("data") or []) if isinstance(r, dict) else []
        for w in data:
            for c in re.findall(r"\{\s*([^{}]+?)\s*\}", str(w.get("items_log_descriptions") or "")):
                out.add(c.strip())
        if len(data) < 100:
            break
        page += 1
        start += 100
    return sorted(out)


def respostas_inspecao(id_work_order) -> dict:
    """Respostas do técnico na OS de inspeção, indexadas pela CHAVE do `chamado_spec`.

    É o que faz o diálogo "Abrir chamado" nascer preenchido: a analista de chamados deixa de garimpar serial e
    sintoma na OS. Casa pela DESCRIÇÃO da subtarefa, que é o único elo entre o form item gravado no
    Fracttal e o modelo do `chamado_insp_spec` — o Fracttal não guarda a chave.
    → {chave: resposta} só com o que foi respondido."""
    import chamado_insp_spec as ci
    porc = {}
    for bloco in [ci.BASE] + list(ci.POR_TIPO.values()) + list(ci.POR_FABRICANTE.values()):
        for s in bloco:
            if s.get("chave"):
                porc[s["desc"].strip().lower()] = s["chave"]
    try:
        rf = api._rpc_call(api.RPC_WO_FORMIT, {"id_work_order": id_work_order})
    except FracttalError:
        return {}
    out = {}
    for it in ((rf.get("data") or []) if isinstance(rf, dict) else []):
        ch = porc.get(str(it.get("description") or "").strip().lower())
        if not ch:
            continue
        v = api._form_item_resposta(it)
        if v:
            out[ch] = v
    # o que o app SABE, sem ter perguntado ao técnico: data da falha, nº de unidades e o
    # "menos de 7 dias". Recalculado AGORA, não na criação da OS — a analista de chamados abre o chamado dias
    # depois e a resposta muda (pedido do Levi, 30/07).
    try:
        det = api.get_os_detalhes(id_work_order) or {}
        tipo_ativo = ""
        code = det.get("code") or ""
        if code:
            for a in api.load_assets_cached():
                if a.get("code") == code:
                    tipo_ativo = a.get("tipo") or ""
                    break
        for k, v in ci.derivados(tipo_ativo, det.get("event_date")).items():
            out.setdefault(k, v)
    except Exception:
        pass                       # derivado é bônus; nunca impede o chamado de abrir
    return out


import api  # noqa: E402 — no fim: o `api` importa este módulo

"""os_historico.py: a lista de OS (Histórico, COS, Garantias, Investigar ativo).

A linha de cada OS na lista (`_shape_wo_row`), a leitura por período e por página (`list_minhas_os`, `listar_periodo_completo`,
`list_minhas_os_pagina`; a lista em que o Fracttal não entregou um pedido falha INTEIRA, 21/10/2026), o contador do círculo de
carga (`_Passos`), a meta de cada tarefa (tipo e datas) e as contas do "Criado por" (`get_pessoas_contas`, por pessoa).

Saiu do `api.py` em 31/10/2026 (etapa 5.3 do canto central, "o que sobra do api.py"): mudou só o lugar, o código é o mesmo. O
`api.py` segue expondo os mesmos nomes (`api.X`), porque a ponte, as rotas e os testes chamam e TROCAM `api.X` pelo nome. Por
isso toda função que este módulo chama, dele ou de fora (o `api._rpc_call`, o que também saiu para outro módulo), e todo número
ajustável (um prazo, um teto) vão pelo `api.`, e enxergam a troca; só as outras constantes e o estado daqui são usados direto. O
módulo termina com `import api`: o `api` o importa no fim do arquivo (a fachada), e só precisa dele na hora da chamada."""

import re
import threading
import time
from concurrent.futures import as_completed
from fracttal_erro import FracttalError, SessionExpired
import ativos_central


def _code_to_loc():
    """{code do ativo: (cliente, usina_curta, tipo)} do catálogo central, montado UMA vez por versão dele (o antigo `_code_loc`
    era montado uma vez por processo e nunca refeito: um ativo novo não aparecia no nome das OS até o próximo reinício).
    `tipo` = rótulo do tipo de ativo (Inversor, Tracker, Cabine, Transformador, Usina…).
    Sem o catálogo (o Fracttal fora na recarga), não tenta de novo por 10 min: quem chama é cada linha do Histórico, e
    2.000 linhas eram 2.000 tentativas de recarregar ~22 mil ativos (19/10/2026)."""
    cat = ativos_central.atual()
    if cat is not None:
        return cat.local_por_codigo
    if time.time() - api._CODE_LOC_TENTOU[0] < 600:
        return {}
    api._CODE_LOC_TENTOU[0] = time.time()
    try:
        api.load_assets_cached()
    except Exception:
        pass
    cat = ativos_central.atual()
    return cat.local_por_codigo if cat is not None else {}


def _extrai_code(desc: str) -> str:
    """'... { GDEN-GJR100-ETKR10.200 }' → 'GDEN-GJR100-ETKR10.200'."""
    if "{" in desc and "}" in desc:
        return desc[desc.rfind("{") + 1:desc.rfind("}")].strip()
    return ""


def _extrai_codigos(desc: str) -> list:
    """TODOS os códigos '{ ... }' dos itens da OS, na ordem. A OS de várias tarefas traz um item por ativo, separados por
    vírgula, e o `_extrai_code` fica só com o último: o "Investigar ativo" do Tempo real (26/10/2026) filtra a lista do
    Histórico pelo código, e a OS agrupada de dois inversores tem de aparecer nos dois."""
    return [c.strip() for c in re.findall(r"\{([^{}]*)\}", str(desc or "")) if c.strip()]


HISTORICO_CAP = 2000   # teto de OS por carga do histórico (limita o enriquecimento de tipo_tarefa)


# ── Visão COS do histórico (espelha a que existia no Power BI) ───────────────
# Os 4 tipos que a visão do BI deixava marcados; Preventiva ficava DE FORA (é o PCM, outro fluxo).
TIPOS_COS = ("Corretiva", "Corretiva Emergencial", "Religamento", "Religamento Remoto")


def decodifica_gatilho(bruto) -> str:
    """`trigger_description` do Fracttal → português. As regras vieram do Power Query que o Levi
    usava no Power BI: o campo vem em código (`NO_SCHEDULE_TASK`, `DATE$EVERY$30$DAYS`)."""
    s = str(bruto or "").strip()
    if not s:
        return ""
    if "NO_SCHEDULE_TASK" in s:
        return "Tarefa não agendada"
    s = s.replace("EVENT$", "").replace("DATE$EVERY$", "A cada ")
    s = s.replace("$DAYS", " dias").replace("$MONTHS", " meses").replace("$YEARS", " anos")
    for n, sing in (("1 dias", "1 dia"), ("1 meses", "1 mês"), ("1 anos", "1 ano")):
        s = s.replace(n, sing)
    return s.strip()


def _primeiro(w: dict, *chaves) -> str:
    """1º campo preenchido entre `chaves` (data ISO cortada em 19). O Fracttal muda o nome do
    mesmo dado entre endpoints — é o mesmo parse defensivo do `fim_keys` do `_meta_tarefa_por_os`,
    e sem ele uma renomeação silenciosa esvazia a coluna sem ninguém perceber."""
    for k in chaves:
        v = w.get(k)
        if v not in (None, "", []) and str(v).lower() != "none":
            return str(v)[:19]
    return ""


def _shape_wo_row(w: dict) -> dict:
    """Linha crua do `work_orders_list_react` → o dict que o app inteiro consome. Extraído do
    `list_minhas_os` para a versão PAGINADA usar o mesmo formato — duplicar aqui divergiria."""
    item = w.get("items_log_descriptions") or ""
    if isinstance(item, list):
        item = ", ".join(str(x) for x in item)
    item = str(item)
    code = api._extrai_code(item)
    ativo = (item.split("{")[0]).strip()[:60]
    cliente, usina, tipo = api._code_to_loc().get(code, ("", "", ""))
    desc = w.get("tasks_descriptions") or ""
    if isinstance(desc, list):
        desc = ", ".join(str(x) for x in desc)
    desc = str(desc).strip()[:90] or "—"
    stid = w.get("id_status_work_order")
    etiquetas = [{"id": l.get("id"), "nome": l.get("description")}
                 for l in (w.get("labels") or []) if isinstance(l, dict)]
    return {"id": w.get("id"), "folio": w.get("wo_folio"), "cliente": cliente or "—",
            "usina": usina or "—", "ativo": ativo, "tipo": tipo or "—", "descricao": desc,
            "code": code,       # o código do ativo (28/10/2026: o Responsável UFV da usina, pelo cadastro do Nexus)
            "codigos": api._extrai_codigos(item),          # o filtro por ativo do "Investigar ativo" (26/10/2026)
            "criado_por": str(w.get("created_by") or "").strip(), "etiquetas": etiquetas,
            # QUEM está com a OS. A linha crua já traz isso — sem esses dois campos o
            # board de Performance precisaria de UMA CONSULTA POR ANALISTA; com eles,
            # uma busca só traz todo mundo e o agrupamento é local.
            "atribuido_a": str(w.get("user_assigned")
                               or w.get("personnel_description") or "").strip(),
            "id_atribuido": w.get("id_assigned_user"),
            "data": (w.get("creation_date") or "")[:19],
            "event_date": (w.get("event_date") or w.get("date_maintenance")
                           or w.get("cal_date_maintenance") or "")[:19],   # fallback da lista
            "data_fim": (w.get("final_date") or w.get("date_end")
                         or w.get("real_final_date") or "")[:19],           # fallback da lista
            # ── colunas da visão COS ──
            # Sondado ao vivo em 28/07: a LISTAGEM só tem `date_maintenance` (= programada) e
            # `personnel_description`. `initial_date` e `trigger_description` existem apenas no
            # nível TAREFA — chegam depois, pelo `meta_tarefas_por_os`. Nada de cair no
            # `first_date_task` aqui: ele é IGUAL à data programada, e a coluna "Início" ficaria
            # preenchida com a data errada para toda OS nunca iniciada (33 de 1.306 tarefas
            # medidas têm início real).
            "programada": api._primeiro(w, "date_maintenance", "cal_date_maintenance"),
            "inicio": "",
            "equipe": str(w.get("personnel_description")
                          or w.get("user_assigned") or "").strip(),
            "gatilho": "",
            "status_id": stid, "status": api.WO_STATUS.get(stid, f"Status {stid}")}


class _Passos:
    """O contador do círculo de carga: cada chamada é um pedido ao Fracttal que terminou. Seguro entre threads (as
    páginas e os lotes vão em paralelo) e mudo sem quem escute. Devolve o que recebeu, para embrulhar o resultado."""

    def __init__(self, avisar, total):
        self.avisar, self.total, self.feito = avisar, max(1, int(total or 1)), 0
        self._trava = threading.Lock()

    def __call__(self, resultado=None):
        if self.avisar is not None:
            with self._trava:
                self.feito = min(self.feito + 1, self.total)
                feito = self.feito
            try:
                self.avisar(feito, self.total)
            except Exception:                                  # noqa: BLE001 — o círculo nunca derruba a busca
                pass
        return resultado

    def fim(self):
        if self.avisar is not None:
            try:
                self.avisar(self.total, self.total)
            except Exception:                                  # noqa: BLE001
                pass


def _lista_pela_metade(falhas: list, pedidos: int):
    """A lista em que o Fracttal não entregou algum pedido (tempo esgotado, 429, erro) falha INTEIRA (21/10/2026, chat de
    desempenho). Raio-X do servidor às 14:36 de 21/10: um GET /os/historico de 45 s esperando o Fracttal, 24 pedidos
    presos em 24 h; 45 s é o tempo-limite do `_rpc_chamar`. Até aqui o erro de cada página e de cada lote das tarefas era
    engolido: sem a 1ª página a lista saía vazia e ficava guardada como se não houvesse OS (no Histórico e no quadro do
    Acompanhamento), sem uma do meio sumiam até 200 OS sem aviso, e a lista vazia de "Todos" fazia cada pessoa buscar a
    dela inteira dali em diante (o total dela não batia com o 0 guardado). Quem chama fica com a lista anterior, com a
    hora dela, ou mostra este aviso. A sessão que caiu continua sessão caída: leva ao login."""
    for e in falhas:
        if isinstance(e, SessionExpired):
            raise e
    txt = " ".join(str(e) for e in falhas).lower()
    if "timed out" in txt or "timeout" in txt:
        motivo = "não respondeu a tempo"
    elif "429" in txt:
        motivo = "recusou pedidos (o limite de 200 por minuto da empresa)"
    else:
        motivo = "devolveu erro"
    raise FracttalError("O Fracttal %s em %d de %d pedidos da lista. Para não mostrar OS pela metade, a lista não foi "
                        "atualizada; tente de novo em instantes." % (motivo, len(falhas), pedidos))


def list_minhas_os(modo: str = "criadas", id_account=None, id_label=None,
                   de: str = None, ate: str = None, status_ids=None, cap: int = HISTORICO_CAP,
                   info: dict = None, progresso=None, meta_ja: dict = None) -> list:
    """OS do Fracttal no PERÍODO [de, ate] (datas 'YYYY-MM-DD' — filtradas NO SERVIDOR por
    creation_date, então o período governa a busca de verdade). modo='criadas' (Histórico Geral, por
    'id_created_by') ou 'atribuidas' (id_assigned_user = id_personnel do logado). Em 'criadas',
    id_account: None = LOGADO (default); "TODOS" = todos os criadores; ou um id_account específico.
    id_label (opcional): só OS que CONTÊM a etiqueta. PAGINA o período inteiro (todos os status numa
    busca só) até o teto `cap`, dedup por id, ordena por data desc.
    → [{'id','folio','cliente','usina','ativo','tipo','tipo_tarefa','descricao','criado_por',
        'atribuido_a','id_atribuido','etiquetas','data','status_id','status'}].
        'tipo' = tipo de ativo (Inversor/Tracker/…);
        'tipo_tarefa' = tipo da OS (Corretiva/Preventiva/Inspeção/…), via _tipo_tarefa_por_os.

    `progresso(feito, total)` (opcional) é chamado a cada pedido ao Fracttal que termina — as páginas da listagem e os
    lotes do meta das tarefas. É o que desenha o círculo de carga do Histórico web (Levi, 27/09: "no período de
    carregamento poderia ter um círculo mostrando o progresso"). O total só se sabe depois da 1ª página.

    `meta_ja` (opcional, 19/10/2026): {id: {"status_id", "tipo_tarefa", "event_date", "data_fim", "note", "inicio",
    "gatilho"}} do que já se sabia de cada OS. A OS que estava fechada (Concluída ou Cancelada) e continua com o MESMO
    status não tem as tarefas lidas de novo: o tipo, as datas e o gatilho de uma OS fechada não mudam. Na busca inteira
    do Histórico (a cada 10 min), só as abertas e as novas vão ao RPC de tarefas."""
    # quem é o logado só quando o filtro é dele: "TODOS" (o Acompanhamento de chamados, a Visão COS) não usa, e a
    # primeira busca da pessoa no processo lia o pessoal inteiro do Fracttal só para isso (08/10/2026)
    todos = False
    if modo == "atribuidas":
        prop, val = "id_assigned_user", api._current_user_ids()[0]
    else:                                   # criadas / Histórico Geral
        prop = "id_created_by"
        if id_account is None:    val = api._current_user_ids()[1]     # default: logado
        elif id_account == "TODOS": val, todos = None, True
        else:                     val = id_account
    if not todos and val is None:
        raise FracttalError("Não consegui identificar seu usuário no Fracttal (e-mail não bate no cadastro).")
    cond = [] if todos else [{"operator": "=", "property": prop, "value": val}]
    if id_label:                            # OS que contêm a etiqueta (server-side)
        cond.append({"operator": "=", "property": "id_label", "value": id_label})
    if status_ids:                          # status no servidor (id_status_work_order) — re-busca por status
        cond.append({"operator": "in", "property": "id_status_work_order", "value": list(status_ids)})
    if de:                                  # período no servidor (creation_date é ISO UTC)
        cond.append({"operator": ">=", "property": "creation_date", "value": de})
    if ate:
        cond.append({"operator": "<=", "property": "creation_date", "value": ate + "T23:59:59"})
    limit = 200
    falhas = []                             # os pedidos que o Fracttal não entregou (ver `_lista_pela_metade`)

    def _fetch_page(start):                 # uma página da listagem (período já está em cond)
        try:
            return api._rpc_call(api.RPC_WO_LIST, {"page": start // limit + 1, "limit": limit, "start": start,
                "append": True, "sort": [{"property": "id", "direction": "desc"}], "filter": cond})
        except FracttalError as e:
            falhas.append(e)
            return None

    first = _fetch_page(0)                   # 1ª página dá o total; as demais em paralelo (sem ela, total 0: nenhuma)
    total = int(first.get("total") or 0) if isinstance(first, dict) else 0
    if isinstance(info, dict):               # quem chama pode AVISAR que o teto cortou as mais antigas
        info.update({"total": total, "cap": cap})
    paginas = [first]
    starts = list(range(limit, min(total, cap), limit))
    # a conta do círculo: 1ª página + as outras + os lotes do meta (130 OS cada, ver _meta_tarefa_por_os)
    n_meta = -(-min(total, cap) // 130) if total else 0
    passo = api._Passos(progresso, 1 + len(starts) + n_meta)
    passo()
    if starts:
        with api._ExecutorComContexto(max_workers=min(6, len(starts))) as ex:
            paginas.extend(ex.map(lambda s: passo(_fetch_page(s)), starts))
    if falhas:                               # nem lê as tarefas de uma lista que não vai à tela
        api._lista_pela_metade(falhas, 1 + len(starts))
    vistos = {}
    for res in paginas:
        for w in ((res.get("data") or []) if isinstance(res, dict) else []):
            wid = w.get("id")
            if wid not in vistos:
                vistos[wid] = api._shape_wo_row(w)
    out = list(vistos.values())
    out.sort(key=lambda x: x["data"], reverse=True)
    ids = [d["id"] for d in out]                           # enriquece: tipo de tarefa + evento + fim
    sabido = {}
    for d in out:
        m = (meta_ja or {}).get(d["id"])
        if m and d.get("status_id") in api.STATUS_FECHADOS and m.get("status_id") == d.get("status_id"):
            sabido[d["id"]] = m
    ids = [i for i in ids if i not in sabido]
    # os lotes das tarefas que não vão ao Fracttal (as fechadas já sabidas, ou menos OS do que o total do servidor
    # dizia) contam como feitos já: o total do círculo, dito depois da 1ª página, não muda no meio da carga, e o círculo
    # anda em vez de esperar o fim (19/10/2026; o teste do oem cobra o total fixo e o fechamento em 100%)
    for _ in range(max(0, n_meta - -(-len(ids) // 130))):
        passo()
    meta = api._meta_tarefa_por_os(ids, passo=passo) if progresso is not None else api._meta_tarefa_por_os(ids)
    if getattr(meta, "falhas", None):        # 130 OS sem o tipo e as datas (fechadas, ficariam assim no `meta_ja`)
        api._lista_pela_metade(meta.falhas, -(-len(ids) // 130))
    meta.update(sabido)
    passo.fim()
    for d in out:
        m = meta.get(d["id"], {})
        d["tipo_tarefa"] = m.get("tipo_tarefa", "")
        d["event_date"] = m.get("event_date") or d.get("event_date", "")   # tarefa manda; senão a da lista
        d["data_fim"] = m.get("data_fim") or d.get("data_fim", "")
        d["note"] = m.get("note", "")                                       # p/ o board ler o bloco CHAMADO
        # início real e gatilho (colunas da visão COS): o meta já os trazia e eles eram jogados fora — a tela web
        # buscava tudo de novo, em lotes de 60 sequenciais (34 idas ao Fracttal por carga de 2000 OS, 27/09)
        d["inicio"] = m.get("inicio") or d.get("inicio", "")
        d["gatilho"] = m.get("gatilho") or d.get("gatilho", "")
    return out


def contar_minhas_analises() -> int:
    """Quantas OS de PERFORMANCE estão ATRIBUÍDAS ao logado e ABERTAS (status Em Processo).
    Alimenta o selo "N atribuídas a você" do card Performance no launcher. UMA chamada com
    limite=1 — só o `total` do servidor interessa. Em Verificação/Concluída ficam de fora:
    o selo é cobrança de trabalho pendente, não placar."""
    lid = api._label_performance_id()
    if not lid:
        return 0
    r = api.list_minhas_os_pagina("atribuidas", None, lid, None, None, [1], "", 1, 1)
    return int(r.get("total") or 0)


def listar_periodo_completo(modo: str = "criadas", id_account=None, id_label=None,
                            de: str = None, ate: str = None, status_ids=None,
                            busca: str = "", limite: int = 200, max_paginas: int = 80) -> dict:
    """TODAS as OS do período, de uma vez. → {'linhas', 'total', 'completo'}.

    Existe porque cliente/usina/tipo são filtrados NO APP: o servidor não sabe filtrar por usina
    (o `like` em campo de item é ignorado e o `id_group_task` é família de plano, não planta —
    ambos medidos). Então, para o filtro dar uma resposta correta, o período tem de estar inteiro
    na mão.

    Pagina EM PARALELO: a 1ª página revela o total e as demais vão juntas. Medido em 30/07 com
    5.522 OS — sequencial de 60 em 60 levaria ~93 requisições e mais de um minuto; assim são 28
    requisições em 8 vias. `max_paginas` é o freio para período absurdo: devolve o que deu e marca
    `completo=False`, e aí quem chamou avisa em vez de mentir que acabou."""
    p1 = api.list_minhas_os_pagina(modo, id_account, id_label, de, ate, status_ids, busca, 1, limite)
    total = int(p1.get("total") or 0)
    linhas = list(p1.get("linhas") or [])
    if not p1.get("tem_mais"):
        return {"linhas": linhas, "total": total, "completo": True}
    n_pag = -(-total // limite)                       # teto da divisão
    restantes = list(range(2, min(n_pag, max_paginas) + 1))
    if restantes:
        with api._ExecutorComContexto(max_workers=min(8, len(restantes))) as ex:
            futuros = {ex.submit(api.list_minhas_os_pagina, modo, id_account, id_label, de, ate,
                                 status_ids, busca, p, limite): p for p in restantes}
            for f in as_completed(futuros):
                try:
                    linhas += (f.result() or {}).get("linhas") or []
                except Exception:
                    pass                              # página que falhar não derruba a varredura
    vistos, unicas = set(), []
    for d in linhas:                                  # páginas concorrentes podem repetir na borda
        if d.get("id") in vistos:
            continue
        vistos.add(d.get("id")); unicas.append(d)
    unicas.sort(key=lambda d: d.get("id") or 0, reverse=True)
    return {"linhas": unicas, "total": total, "completo": len(unicas) >= total}


def meta_tarefas_por_os(wo_ids) -> dict:
    """Público: tipo de tarefa + datas da tarefa por OS (o histórico busca DEPOIS de renderizar —
    medido: 3,5 s para 60 ids, contra 0,7 s da página; enriquecer junto quintuplicava a espera)."""
    return api._meta_tarefa_por_os(wo_ids)


def list_minhas_os_pagina(modo: str = "criadas", id_account=None, id_label=None,
                          de: str = None, ate: str = None, status_ids=None,
                          busca: str = "", pagina: int = 1, limite: int = 60,
                          com_meta: bool = False) -> dict:
    """UMA página do histórico — é o que torna a rolagem infinita possível (28/07, reclamação
    da equipe: o histórico puxava até 2000 OS + 16 lotes de enriquecimento ANTES de mostrar a
    primeira linha; medido, uma página de 60 responde em ~0,7 s).

    Mesmos filtros server-side do `list_minhas_os`, MAIS `busca`: like em `wo_folio` OU
    `description` — SÓ essas duas, porque foram as únicas que o servidor comprovadamente filtra
    (sondado ao vivo: 'MOTIVO' em description → 28 acertos reais). CUIDADO ao acrescentar
    propriedade aqui: o servidor IGNORA propriedade desconhecida devolvendo TUDO, e num OR isso
    faz a busca inteira voltar o catálogo completo — foi medido com tasks_descriptions/
    items_description, os dois voltaram total=10272 (tudo).

    → {'linhas': [...], 'total': N no servidor, 'tem_mais': bool}."""
    todos = False                           # quem é o logado só quando o filtro é dele (ver `list_minhas_os`)
    if modo == "atribuidas":
        prop, val = "id_assigned_user", api._current_user_ids()[0]
    else:
        prop = "id_created_by"
        if id_account is None:      val = api._current_user_ids()[1]
        elif id_account == "TODOS": val, todos = None, True
        else:                       val = id_account
    if not todos and val is None:
        raise FracttalError("Não consegui identificar seu usuário no Fracttal (e-mail não bate no cadastro).")
    cond = [] if todos else [{"operator": "=", "property": prop, "value": val}]
    if id_label:
        cond.append({"operator": "=", "property": "id_label", "value": id_label})
    if status_ids:
        cond.append({"operator": "in", "property": "id_status_work_order", "value": list(status_ids)})
    if de:
        cond.append({"operator": ">=", "property": "creation_date", "value": de})
    if ate:
        cond.append({"operator": "<=", "property": "creation_date", "value": ate + "T23:59:59"})
    busca = str(busca or "").strip()
    if busca:
        cond += [{"operator": "like", "property": "wo_folio", "value": busca, "condition": "or"},
                 {"operator": "like", "property": "description", "value": busca, "condition": "or"}]
    pagina = max(1, int(pagina))
    start = (pagina - 1) * limite
    res = api._rpc_call(api.RPC_WO_LIST, {"page": pagina, "limit": limite, "start": start, "append": True,
                                  "sort": [{"property": "id", "direction": "desc"}], "filter": cond})
    total = int(res.get("total") or 0) if isinstance(res, dict) else 0
    linhas, vistos = [], set()
    for w in ((res.get("data") or []) if isinstance(res, dict) else []):
        if w.get("id") in vistos:
            continue
        vistos.add(w.get("id"))
        linhas.append(api._shape_wo_row(w))
    for d in linhas:
        d.setdefault("tipo_tarefa", "")
    # `com_meta=False` é o DEFAULT de propósito: o enriquecimento custa 5× a página (3,5 s vs
    # 0,7 s, medido) — o histórico renderiza primeiro e busca a meta em separado, assíncrono
    # (`meta_tarefas_por_os`). As datas da linha já vêm com o fallback da listagem.
    if com_meta:
        meta = api._meta_tarefa_por_os([d["id"] for d in linhas])
        for d in linhas:
            m = meta.get(d["id"], {})
            d["tipo_tarefa"] = m.get("tipo_tarefa", "")
            d["event_date"] = m.get("event_date") or d.get("event_date", "")
            d["data_fim"] = m.get("data_fim") or d.get("data_fim", "")
            d["note"] = m.get("note", "")
            d["inicio"] = m.get("inicio", "")
            d["gatilho"] = m.get("gatilho", "")
    return {"linhas": linhas, "total": total, "tem_mais": start + len(linhas) < total}


# ── Detalhe de uma OS (ao clicar no nº no histórico): Data do Evento, Notas, Subtarefas ──
RPC_WO_TASKS  = "tasks.work_orders_tasks_new_list"       # tarefa(s) da OS (event_date, notas, tipo)
RPC_WO_FORMIT = "tasks.work_orders_task_form_items_list"  # subtarefas (checklist)


class _MetaLida(dict):
    """O meta das tarefas por OS, com os erros dos lotes que o Fracttal não entregou (`falhas`). Quem não mostra lista
    pela metade (o `list_minhas_os`) confere; quem usa como dict não vê diferença. É atributo, e não argumento novo,
    porque os testes do oem trocam o `_meta_tarefa_por_os` por `lambda ids: {...}`."""
    falhas: list = []


def _meta_tarefa_por_os(wo_ids, passo=None):
    """{id_work_order: {'tipo_tarefa': 'Tipo' (ou 'A / B'), 'event_date': ISO}} p/ as OS dadas. A
    listagem NÃO traz tipo de tarefa nem a data do evento — vêm do RPC de tarefas (1 chamada por lote,
    em paralelo). Erro num lote não quebra a resposta: as OS dele ficam sem o meta, e o erro vai no `falhas` do
    resultado (`_MetaLida`); a lista do Histórico e do Acompanhamento não sai assim (`_lista_pela_metade`)."""
    ids = [w for w in dict.fromkeys(wo_ids) if w]            # únicos, preserva ordem
    if not ids:
        return api._MetaLida()
    CH = 130
    chunks = [ids[i:i + CH] for i in range(0, len(ids), CH)]
    falhas = []

    fim_keys = ("final_date", "date_end", "end_date", "real_final_date", "finished_date",
                "date_finished", "closing_date")

    def _fetch(chunk):
        tipos, evt, fim, notas, start, limit = {}, {}, {}, {}, 0, 2000
        ini, gat = {}, {}                                  # início real e gatilho (visão COS)
        while True:
            try:
                r = api._rpc_call(RPC_WO_TASKS, {"page": 1, "limit": limit, "start": start,
                              "sort": [{"property": "id", "direction": "desc"}],
                              "filter": [{"operator": "in", "property": "id_work_order", "value": chunk}]})
            except FracttalError as e:
                falhas.append(e)
                break
            data = (r.get("data") or []) if isinstance(r, dict) else []
            for t in data:
                wid = t.get("id_work_order")
                if not wid:
                    continue
                tp = str(t.get("tasks_types_main_description") or "").strip()
                if tp:
                    tipos.setdefault(wid, set()).add(tp)
                ev = str(t.get("event_date") or "")[:19]     # data do evento
                if ev and (wid not in evt or ev < evt[wid]):  # a mais antiga (início da OS)
                    evt[wid] = ev
                fv = ""                                       # data fim (conclusão)
                for k in fim_keys:
                    v = t.get(k)
                    if v not in (None, "") and str(v).lower() != "none":
                        fv = str(v)[:19]; break
                if fv and (wid not in fim or fv > fim[wid]):  # a mais recente
                    fim[wid] = fv
                nt = str(t.get("note") or t.get("task_note") or "").strip()   # nota da tarefa
                if nt:
                    cur = notas.get(wid, "")
                    if (api._CHAMADO_MK in nt and api._CHAMADO_MK not in cur) or \
                       (api._CHAMADO_MK not in cur and len(nt) > len(cur)):       # prefere a que tem o bloco
                        notas[wid] = nt
                iv = str(t.get("initial_date") or "")[:19]     # início REAL (só a tarefa tem)
                if iv and iv.lower() != "none" and (wid not in ini or iv < ini[wid]):
                    ini[wid] = iv                              # a mais antiga = início da OS
                gv = str(t.get("trigger_description") or "").strip()
                # Uma OS pode ter tarefas com gatilhos diferentes; a agendada (EVENT$…) diz mais
                # que "não agendada", então ela ganha.
                if gv and (wid not in gat or (gat[wid] == "NO_SCHEDULE_TASK"
                                              and gv != "NO_SCHEDULE_TASK")):
                    gat[wid] = gv
            start += len(data)
            if not data or len(data) < limit:
                break
        if passo is not None:
            passo()                                            # um lote a menos no círculo do Histórico
        return tipos, evt, fim, notas, ini, gat

    tipos_out, evt_out, fim_out, notas_out = {}, {}, {}, {}
    ini_out, gat_out = {}, {}
    with api._ExecutorComContexto(max_workers=min(8, len(chunks))) as ex:
        for tipos, evt, fim, notas, ini, gat in ex.map(_fetch, chunks):
            for wid, s in tipos.items():
                tipos_out.setdefault(wid, set()).update(s)
            for wid, e in evt.items():
                if wid not in evt_out or e < evt_out[wid]:
                    evt_out[wid] = e
            for wid, f2 in fim.items():
                if wid not in fim_out or f2 > fim_out[wid]:
                    fim_out[wid] = f2
            for wid, nt in notas.items():
                cur = notas_out.get(wid, "")
                if (api._CHAMADO_MK in nt and api._CHAMADO_MK not in cur) or (api._CHAMADO_MK not in cur and len(nt) > len(cur)):
                    notas_out[wid] = nt
            for wid, iv in ini.items():
                if wid not in ini_out or iv < ini_out[wid]:
                    ini_out[wid] = iv
            for wid, gv in gat.items():
                if wid not in gat_out or (gat_out[wid] == "NO_SCHEDULE_TASK"
                                          and gv != "NO_SCHEDULE_TASK"):
                    gat_out[wid] = gv
    out = api._MetaLida({wid: {"tipo_tarefa": " / ".join(sorted(tipos_out.get(wid, set()))),
                           "event_date": evt_out.get(wid, ""), "data_fim": fim_out.get(wid, ""),
                           "note": notas_out.get(wid, ""),
                           "inicio": ini_out.get(wid, ""),
                           "gatilho": api.decodifica_gatilho(gat_out.get(wid, ""))}
                     for wid in set(tipos_out) | set(evt_out) | set(fim_out) | set(notas_out)
                                | set(ini_out) | set(gat_out)})
    out.falhas = falhas
    return out


def get_pessoas_contas() -> dict:
    """Contas (quem cria OS/solicitação) p/ o filtro de 'criado por' + a conta do usuário logado.
    Acha o 'eu' (id_account do logado) na MESMA paginação do pessoal — uma passada só.
    → {"pessoas": [{"id_account","nome"}] (ordenado por nome), "eu": id_account_logado}.

    Lido POR PESSOA, com a sessão dela (o Histórico guarda 10 min para cada uma, `rotas._memo(("pessoas", pessoa))`), e NÃO do
    catálogo comum de pessoas: quem não tem a permissão de pessoal no Fracttal recebe a lista vazia, e não as contas da
    empresa (revisão da 4.1, 31/10/2026: a etapa 4 o tinha posto no catálogo, e voltou)."""
    email = (api.current_user() or "").strip().lower()
    eu = None
    vistos = {}
    start = 0
    while True:
        res = api._rpc_call(api.RPC_PERSONNEL, {"page": start // 100 + 1, "limit": 100, "start": start,
                                        "append": True, "filter": [], "sort": []})
        data = res.get("data") if isinstance(res, dict) else res
        data = data if isinstance(data, list) else []
        for p in data:
            ida = p.get("id_account")
            if ida is not None and ida not in vistos:
                nome = (p.get("full_name") or p.get("name") or p.get("account_email") or "").strip()
                if nome:
                    vistos[ida] = nome
            if eu is None and email and (p.get("account_email") or p.get("email") or "").strip().lower() == email:
                eu = ida
        start += 100
        if len(data) < 100:
            break
    pessoas = sorted(({"id_account": k, "nome": v} for k, v in vistos.items()),
                     key=lambda x: x["nome"].lower())
    return {"pessoas": pessoas, "eu": eu}


import api  # noqa: E402 — no fim: o `api` importa este módulo

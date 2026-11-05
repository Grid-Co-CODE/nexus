"""os_anexos.py: o que a OS tem de fotos e arquivos, para LER.

As imagens da OS e das subtarefas, os recursos (peças e mão de obra), os anexos por tarefa e por subtarefa, os da solicitação e
o `_ids_tarefas_da_os` (as tarefas da OS, para saber onde anexar). O ENVIO (`attach_imagem_os` e o S3) e o download
(`s3_get_url`, `baixar_imagem`) ficam no `api.py`: falam com a rede direto, e o Raio-X os mostra como "Fracttal (OS Creator)"
(`nexus/casca/presos.py`, por arquivo).

Saiu do `api.py` em 31/10/2026 (etapa 5.3 do canto central, "o que sobra do api.py"): mudou só o lugar, o código é o mesmo. O
`api.py` segue expondo os mesmos nomes (`api.X`), porque a ponte, as rotas e os testes chamam e TROCAM `api.X` pelo nome. Por
isso toda função que este módulo chama, dele ou de fora (o `api._rpc_call`, o que também saiu para outro módulo), e todo número
ajustável (um prazo, um teto) vão pelo `api.`, e enxergam a troca; só as outras constantes e o estado daqui são usados direto. O
módulo termina com `import api`: o `api` o importa no fim do arquivo (a fachada), e só precisa dele na hora da chamada."""

from fracttal_erro import FracttalError


# ── Fotos anexadas às subtarefas da OS ────────────────────────────────────────
RPC_WO_IMAGES = "tasks.work_orders_tasks_images_all_list"


def _img_url(d: dict):
    """URL (pré-assinada S3) da imagem cheia na resposta — prefere amazonaws/extensão de imagem."""
    cands = [v for v in d.values() if isinstance(v, str) and v.lower().startswith("http")]
    if not cands:
        return None
    for v in cands:
        low = v.lower()
        if "amazonaws" in low or any(e in low for e in (".jpg", ".jpeg", ".png", ".webp", ".gif")):
            return v
    return cands[0]


def _is_img_b64(s) -> bool:
    """True se a string parece base64 de imagem (PNG/JPEG/GIF) — por ASSINATURA, não por tamanho."""
    return isinstance(s, str) and (s.startswith("data:image") or s[:4] == "/9j/"
                                   or s[:5] in ("iVBOR", "R0lGO"))


def _img_thumb(d: dict):
    """Thumbnail em base64, se a resposta trouxer (campos variáveis / assinatura de imagem)."""
    for k in ("thumbnail", "thumb", "base64", "image_base64", "img_base64", "preview"):
        v = d.get(k)
        if api._is_img_b64(v) or (isinstance(v, str) and len(v) > 200 and not v.lower().startswith("http")):
            return v
    for v in d.values():
        if api._is_img_b64(v):
            return v
    return None


def get_os_imagens(id_work_order) -> list:
    """Fotos anexadas às subtarefas de UMA OS (1 chamada → todas). Cada foto: URL pré-assinada da S3
    (imagem cheia) + thumbnail base64 (se vier) + descrição da subtarefa de origem. Parse DEFENSIVO —
    os nomes exatos dos campos ainda serão confirmados ao vivo. → [{'url','thumb','descricao','raw'}]."""
    try:
        res = api._rpc_call(RPC_WO_IMAGES, {"id_work_order": id_work_order,
            "sort": [{"property": "order_number", "direction": "asc"}]})
    except FracttalError:
        return []
    data = res.get("data") if isinstance(res, dict) else res
    out = []
    for d in (data if isinstance(data, list) else []):
        if not isinstance(d, dict):
            continue
        url, thumb = api._img_url(d), api._img_thumb(d)
        if not (url or thumb):
            continue
        out.append({"url": url, "thumb": thumb,
                    "descricao": str(d.get("description") or d.get("task_description")
                                     or d.get("items_log_description") or "").strip(),
                    "ativo": str(d.get("items_description") or d.get("item_description")
                                 or d.get("assets_description") or d.get("description_item") or "").strip(),
                    "raw": d})
    return out


# ── Recursos lançados na OS (peças, mão de obra, serviços) ─────────────────────────────────────────────────────────
RPC_WO_RESOURCES = "tasks.work_orders_resources_all_list"
# o tipo do recurso como o Fracttal grava (`type_description`; o App de Campo lança a peça como INVENTORY desde a v274)
TIPO_RECURSO = {"INVENTORY": "Peça / inventário", "INVENTORIES": "Peça / inventário", "HUMAN_RESOURCES": "Mão de obra",
                "SERVICES": "Serviço", "SERVICE": "Serviço", "TOOLS": "Ferramenta", "THIRD_PARTY": "Terceiro"}


def get_os_recursos(id_work_order) -> list:
    """Os RECURSOS lançados na OS: o que o PDF do Fracttal lista (o pedido do print da web, `{id_work_order}`, que o Levi
    mandou em 19/10/2026). Os campos são os do lançamento que a web faz e o App de Campo copia desde a v274
    (`type_description`, `description`, `qty`, `real_qty_used`, `units_description`, `source_description`, `unit_cost`,
    `total_cost`, `note`); o parse é defensivo, como o das fotos. Erro do Fracttal sobe: quem chama decide (o PDF diz
    que não leu, em vez de dizer que não há recurso).
    → [{'tipo','descricao','qtd','usado','unidade','origem','custo_unit','custo_total','nota','id_tarefa'}]."""
    res = api._rpc_call(RPC_WO_RESOURCES, {"id_work_order": id_work_order})
    data = res.get("data") if isinstance(res, dict) else res
    out = []
    for r in (data if isinstance(data, list) else []):
        if not isinstance(r, dict):
            continue
        tipo = str(r.get("type_description") or "").strip()
        desc = str(r.get("description") or r.get("resource_description") or r.get("items_description")
                   or r.get("personnel_description") or "").strip()
        if not desc and not tipo:
            continue
        out.append({"tipo": TIPO_RECURSO.get(tipo.upper(), tipo.replace("_", " ").capitalize() or "—"),
                    "descricao": desc or "—",
                    "qtd": r.get("qty"), "usado": r.get("real_qty_used"),
                    "unidade": str(r.get("units_description") or "").strip(),
                    "origem": str(r.get("source_description") or r.get("external_source") or "").strip(),
                    "custo_unit": r.get("unit_cost"), "custo_total": r.get("total_cost"),
                    "nota": str(r.get("note") or "").strip(),
                    "id_tarefa": r.get("id_work_orders_tasks") or r.get("id_work_order_task")})
    return out


RPC_WO_FILES = "tasks.work_orders_tasks_files_list"


def _ids_tarefas_da_os(id_work_order) -> list:
    """id_work_order_task de todas as tarefas da OS. Colhe da lista de tarefas E do endpoint de imagens
    (esse traz o id_work_order_task certo dos anexos), pra não errar o id.

    Na lista de tarefas (`tasks.work_orders_tasks_new_list`) o id da tarefa DESTA OS é o `id`; o `id_task` é o MODELO
    da tarefa (conferido ao vivo, ver `id_tarefa_da_os`: 20878948 era o modelo e o Fracttal recusou; o certo era
    55875684). Até 19/10/2026 a lista caía no `id_task` (ela não traz `id_work_order_task`): a tarefa sem foto não tinha
    os anexos lidos, e o número do modelo podia cair na tarefa antiga de outra OS. As tarefas vêm da mesma leitura que o
    card acabou de fazer (`_leitura_da_os`)."""
    tids = []

    def _add(v):
        if v and v not in tids:
            tids.append(v)

    def _ler(metodo, params):
        try:
            r = api._rpc_call(metodo, params)
        except Exception:
            return []
        d = r.get("data") if isinstance(r, dict) else r
        return d if isinstance(d, list) else []
    # as duas listas ao mesmo tempo (08/10/2026): uma não depende da outra; a ordem dos ids é a de antes
    def _tarefas():
        try:
            return api._leitura_da_os(api.RPC_WO_TASKS, id_work_order, {"id_work_order": id_work_order, "sort": []})
        except Exception:
            return []
    lidas = api._juntos({"tarefas": (_tarefas,),
                     "imagens": (_ler, RPC_WO_IMAGES, {"id_work_order": id_work_order,
                                                       "sort": [{"property": "order_number", "direction": "asc"}]})})
    for t in lidas["tarefas"]:
        if isinstance(t, dict):
            _add(t.get("id_work_order_task") or t.get("id"))
    for d in lidas["imagens"]:
        if isinstance(d, dict):
            _add(d.get("id_work_order_task"))
    return tids


def get_os_anexos(id_work_order) -> list:
    """Anexos ligados às TAREFAS da OS (a aba 'Anexos' da tarefa no Fracttal — prints da criação via
    Performance/PCM, notas etc.). São por `id_work_order_task`. Inclui ARQUIVOS (imagem/PDF) E notas de
    TEXTO (sem arquivo). Resolve a URL pré-assinada das imagens p/ a galeria. Separados por usuário.
    → [{'value','nome','user','url','is_image','is_text','desc','raw'}].

    Dentro de `enxuta("url")` não resolve a URL pré-assinada (um s3_object_get por imagem): é o que basta para CONTAR
    os anexos no card da OS, que antes pagava a URL de cada foto só para mostrar um número (08/10/2026). As listas de
    cada tarefa vão ao mesmo tempo; a ordem é a de antes."""
    com_url = not api._cortado("url")
    out, vistos = [], set()

    def _arquivos(tid):
        try:
            return api._rpc_call(RPC_WO_FILES, {"page": 1, "limit": 200, "start": 0, "is_tree": False,
                                            "node": None, "id_work_order_task": tid})
        except Exception:
            return None
    tids = api._ids_tarefas_da_os(id_work_order)
    if len(tids) > 1:
        with api._ExecutorComContexto(max_workers=min(8, len(tids))) as ex:
            respostas = list(ex.map(_arquivos, tids))
    else:
        respostas = [_arquivos(t) for t in tids]
    for res in respostas:
        if res is None:
            continue
        for d in (res.get("data") if isinstance(res, dict) else res) or []:
            if not isinstance(d, dict):
                continue
            val = str(d.get("value") or "").strip()
            url = api._img_url(d)
            desc = str(d.get("description") or "").strip()
            if not val and not url and not desc:          # nada útil
                continue
            nome = (val.rsplit("/", 1)[-1] if val else (desc or "anexo"))
            chave = (val or url or nome).lower()
            if chave in vistos:                            # dedup (tarefas podem repetir)
                continue
            vistos.add(chave)
            user = str(d.get("accounts_name") or d.get("id_personnel_description")
                       or d.get("personnel_description") or d.get("third_party_description")
                       or d.get("created_by") or "").strip()
            low = (val or nome).lower()
            # POR EXTENSÃO, nunca por "tem URL": PDF/Excel/ZIP do S3 também vêm com URL
            # pré-assinada, então `bool(url)` os marcava como IMAGEM — iam para a galeria,
            # a prévia falhava e o arquivo sumia da tela. Era por isso que não dava para
            # abrir documento nenhum.
            is_image = any(low.endswith(e) for e in
                           (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"))
            is_text = not val and not url                  # nota de texto (sem arquivo)
            out.append({"value": val, "nome": nome, "user": user, "url": url,
                        "is_image": is_image, "is_text": is_text, "desc": desc, "raw": d})
    # imagens que só têm o CAMINHO → busca a URL pré-assinada (em paralelo) p/ a galeria abrir
    faltam = [a for a in out if a.get("is_image") and not a.get("url") and a.get("value")] if com_url else []
    if faltam:
        try:
            with api._ExecutorComContexto(max_workers=8) as ex:
                for a, u in zip(faltam, ex.map(lambda x: api.s3_get_url(x["value"]), faltam)):
                    if u:
                        a["url"] = u
        except Exception:
            pass
    return out


RPC_WO_FORMIT_ATTACH = "tasks.wo_tasks_form_items_attachments_list"   # anexos POR subtarefa (form item)


def get_os_subtarefa_anexos(id_work_order) -> list:
    """Anexos ligados às SUBTAREFAS (form items) de UMA OS. Busca por (id_work_order_task, id_form_item)
    em cada subtarefa com num_attachments>0. type=1 = arquivo (value=caminho S3 → resolve URL pré-assinada);
    type=3 = nota de texto. Cada anexo carrega a subtarefa de origem.
    → [{'url','thumb','descricao','nome','value','subtarefa','is_image','is_text','raw'}].

    Dentro de `enxuta("url")` não resolve a URL pré-assinada de cada arquivo: só para CONTAR (ver `get_os_anexos`)."""
    com_url = not api._cortado("url")
    try:
        items = api._leitura_da_os(api.RPC_WO_FORMIT, id_work_order, {"id_work_order": id_work_order})
    except FracttalError:
        return []
    alvos = []
    for it in (items if isinstance(items, list) else []):
        if not isinstance(it, dict):
            continue
        try:
            n = int(it.get("num_attachments") or 0)
        except (TypeError, ValueError):
            n = 0
        wid = it.get("id_work_order_task")
        fid = it.get("id_work_orders_tasks_form_items")
        if n > 0 and wid is not None and fid is not None:
            alvos.append((wid, fid, str(it.get("description") or "").strip()))
    if not alvos:
        return []

    def _fetch(alvo):
        wid, fid, _ = alvo
        try:
            res = api._rpc_call(RPC_WO_FORMIT_ATTACH, {"page": 1, "limit": 200, "start": 0, "is_tree": False,
                "node": None, "id_work_order_task": wid, "id_work_orders_tasks_form_items": fid,
                "link_attachment": True})
        except Exception:
            return []
        return (res.get("data") if isinstance(res, dict) else res) or []

    try:
        with api._ExecutorComContexto(max_workers=8) as ex:
            resultados = list(ex.map(_fetch, alvos))
    except Exception:
        resultados = [_fetch(a) for a in alvos]

    out = []
    for (wid, fid, sub_desc), data in zip(alvos, resultados):
        for d in (data if isinstance(data, list) else []):
            if not isinstance(d, dict):
                continue
            val = str(d.get("value") or "").strip()
            att_desc = str(d.get("description") or "").strip()
            legenda = sub_desc + (f"  ·  {att_desc}" if att_desc and att_desc != val else "")
            if d.get("type") == 1 and val and "/" in val:      # arquivo (imagem/doc) no S3
                nome = val.rsplit("/", 1)[-1]
                low = nome.lower()
                is_image = any(low.endswith(e) for e in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"))
                out.append({"url": None, "thumb": None, "descricao": legenda or nome, "nome": nome,
                            "value": val, "subtarefa": sub_desc, "is_image": is_image,
                            "is_text": False, "raw": d, "id_tarefa": wid})
            else:                                               # nota de texto (type 3)
                out.append({"url": None, "thumb": None, "descricao": legenda or att_desc or val,
                            "nome": att_desc or val or "nota", "value": "", "subtarefa": sub_desc,
                            "is_image": False, "is_text": True, "raw": d, "id_tarefa": wid})
    arquivos = [a for a in out if not a["is_text"] and a["value"]] if com_url else []   # resolve URL pré-assinada (S3)
    if arquivos:
        try:
            with api._ExecutorComContexto(max_workers=8) as ex:
                for a, u in zip(arquivos, ex.map(lambda x: api.s3_get_url(x["value"]), arquivos)):
                    if u:
                        a["url"] = u
        except Exception:
            pass
    return out


RPC_REQ_FILES = "requests.attachments_list"


def get_solic_anexos(id_request) -> list:
    """Anexos de uma SOLICITAÇÃO (work request). `id_request` = id_code (o Nº). Best-effort — se
    falhar/vier vazio, []. → [{'value','nome','user','url','is_image','raw'}]."""
    if id_request in (None, ""):
        return []
    try:
        res = api._rpc_call(RPC_REQ_FILES, {"filter": [], "sort": [], "page": 1, "limit": 200, "start": 0,
                                        "is_tree": False, "node": None, "id_request": id_request})
    except Exception:
        return []
    data = res.get("data") if isinstance(res, dict) else res
    out = []
    for d in (data if isinstance(data, list) else []):
        if not isinstance(d, dict):
            continue
        val = str(d.get("value") or "").strip()
        url = api._img_url(d)
        if not val and not url:
            continue
        nome = val.rsplit("/", 1)[-1] if val else "arquivo"
        user = str(d.get("accounts_name") or d.get("id_personnel_description")
                   or d.get("personnel_description") or d.get("created_by") or "").strip()
        low = (val or nome).lower()
        is_image = any(low.endswith(e) for e in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"))
        out.append({"value": val, "nome": nome, "user": user, "url": url,
                    "is_image": is_image, "raw": d})
    return out


import api  # noqa: E402 — no fim: o `api` importa este módulo

"""catalogos_rpc.py: os leitores dos catálogos pequenos pelo RPC.

O pessoal (`ler_pessoal`), as etiquetas (`get_labels`, o id pelo nome), os tipos e as classificações, as falhas do COS e o tipo
de tarefa ao vivo. São as funções que o `catalogos.py` (etapa 4) chama pelo nome, no `api`, para encher cada catálogo; quem
guarda, dá o prazo e renova é ele. A criação da Engenharia chama `responsaveis_ao_vivo` e `get_labels` direto, para conferir ao
vivo antes de gravar (a regra de 19/10/2026).

Saiu do `api.py` em 31/10/2026 (etapa 5.3 do canto central, "o que sobra do api.py"): mudou só o lugar, o código é o mesmo. O
`api.py` segue expondo os mesmos nomes (`api.X`), porque a ponte, as rotas e os testes chamam e TROCAM `api.X` pelo nome. Por
isso toda função que este módulo chama, dele ou de fora (o `api._rpc_call`, o que também saiu para outro módulo), e todo número
ajustável (um prazo, um teto) vão pelo `api.`, e enxergam a troca; só as outras constantes e o estado daqui são usados direto. O
módulo termina com `import api`: o `api` o importa no fim do arquivo (a fachada), e só precisa dele na hora da chamada."""

from fracttal_erro import FracttalError


def ler_pessoal() -> list:
    """TODO o pessoal do Fracttal, ativo ou não, numa paginação só do RPC personnel.personnel_list (sessão do usuário, 100 por
    página), com o que o OS Creator usa de cada pessoa: [{'id_personnel','code','name','active','id_account','email'}] (o RPC
    chama o id_personnel de `id`, que é o id_responsible da WO; `email` é o da conta, em minúsculas). É o leitor do catálogo de
    pessoas (`catalogos.py`, 31/10/2026, etapa 4 do canto central) e o da criação da Engenharia (`responsaveis_ao_vivo`)."""
    allp, start = [], 0
    while True:
        res = api._rpc_call(api.RPC_PERSONNEL, {"page": start // 100 + 1, "limit": 100, "start": start,
                                        "append": True, "filter": [], "sort": []})
        data = res.get("data") if isinstance(res, dict) else res
        data = data if isinstance(data, list) else []
        allp.extend(data)
        start += 100
        if len(data) < 100:
            break
    return [{"id_personnel": p.get("id"), "code": p.get("code"),
             "name": (p.get("full_name") or p.get("name") or "").strip(), "active": p.get("active"),
             "id_account": p.get("id_account"), "email": (p.get("account_email") or p.get("email") or "").strip().lower()}
            for p in allp if isinstance(p, dict)]


def get_responsaveis() -> list:
    """TODO o pessoal ATIVO, ordenado por nome. → [{'code','name','id_personnel'}] onde id_personnel = campo `id` do RPC
    (= id_responsible da WO; confirmado: Levi id=1414413). Desde 31/10/2026 (etapa 4 do canto central) vem do catálogo de
    pessoas, um para todas as telas (`catalogos.pessoas`), e não mais do Fracttal a cada chamada."""
    import catalogos
    return catalogos.pessoas()


def responsaveis_ao_vivo() -> list:
    """O mesmo pessoal ATIVO do `get_responsaveis`, lido do Fracttal AGORA, com a sessão de quem pede (uma leitura). É o da
    criação da Engenharia: a regra de 19/10/2026 é que, faltando a pessoa no Fracttal, nenhuma OS sai, e a pessoa desligada
    nas últimas horas seguiria no catálogo até a renovação (revisão da 4.1). A sessão morta levanta aqui, antes de gravar."""
    import catalogos
    return catalogos.ativas(api.ler_pessoal())


# ── Fase 3: etiquetas (work_order_labels) — catálogo + aplicar numa WO ─────────
RPC_LABELS_LIST = "tasks.work_order_labels_list"


def get_labels() -> list:
    """Catálogo de etiquetas habilitadas → [{'id','description','color'}] (ordenado por descrição)."""
    res = api._rpc_call(RPC_LABELS_LIST, {"sort": [{"property": "description", "direction": "asc"}],
                                      "page": 1, "limit": 200, "start": 0, "is_tree": False,
                                      "node": None, "id_work_order": 0, "only_enabled": True})
    data = res.get("data") if isinstance(res, dict) else res
    return [{"id": d.get("id"), "description": d.get("description"), "color": d.get("color")}
            for d in (data if isinstance(data, list) else []) if d.get("enabled", True)]


def _label_id(nome: str):
    """id da etiqueta pelo nome (case-insensitive). None se não existir no Fracttal.

    Do catálogo de etiquetas (`catalogos.etiquetas`, 31/10/2026, etapa 4 do canto central). Até então era relido a cada
    lista DE PROPÓSITO (08/10/2026): nas listas por etiqueta era o primeiro pedido, e era ele que acusava a sessão morta,
    porque a listagem engolia o erro de cada página e a sessão morta virava um quadro vazio. Desde 21/10/2026 a página que
    falha derruba a busca inteira (`_lista_pela_metade`): a lista acusa sozinha, e o id não precisa ir ao Fracttal. O nome
    que o catálogo não tem (a etiqueta criada agora) relê uma vez, com a sessão de quem pediu."""
    import catalogos
    alvo = str(nome or "").strip().lower()
    for reler in (False, True):
        for l in (catalogos.etiquetas(reler=reler) or []):
            if str(l.get("description") or "").strip().lower() == alvo:
                return l.get("id")
    return None


# ── Bloco "O ativo falhou?" (F4) — vocabulário (RPC) + enums fixos (confirmados no payload real) ──
RPC_FALHA_TIPOS  = "tasks.failures_types_list"
RPC_FALHA_CAUSAS = "tasks.failures_causes_list"
RPC_FALHA_DETEC  = "tasks.failures_detection_methods_list"
FALHA_SEVERIDADES = [("Muito baixo", "1"), ("Baixo", "2"), ("Médio", "3"), ("Alto", "4"), ("Muito alto", "5")]
FALHA_DANOS = [("Nenhum", 1), ("Dano ao meio ambiente", 2), ("Danos nas Instalações", 3),
               ("Lesões ao pessoal interno", 4), ("Lesões a Terceiros", 5), ("Outros", 6)]


def get_falha_listas(levantar: bool = False) -> dict:
    """{tipos, causas, metodos} p/ o bloco 'O ativo falhou?' — cada um [{'id','description'}], lidos do Fracttal. Quem guarda
    é o catálogo das falhas (`catalogos.falhas`, 24 h e em disco, 31/10/2026); a cópia que ficava aqui nunca vencia.
    `levantar`: o erro de uma lista sobe, em vez de virar a lista vazia (o catálogo: a leitura pela metade não troca a
    completa, e o erro de verdade, a cota ou a sessão, vai ao estado e à tela; revisão da 4.1)."""
    def _lst(metodo, extra=None):
        p = {"sort": [{"property": "description", "direction": "asc"}], "page": 1, "limit": 200,
             "start": 0, "is_tree": False, "node": None}
        if extra:
            p.update(extra)
        try:
            r = api._rpc_call(metodo, p)
            return [{"id": d.get("id"), "description": d.get("description")}
                    for d in (r.get("data") or []) if d.get("id") is not None]
        except FracttalError:
            if levantar:
                raise
            return []
    return {"tipos": _lst(RPC_FALHA_TIPOS),
            "causas": _lst(RPC_FALHA_CAUSAS, {"id_failure_type": None}),
            "metodos": _lst(RPC_FALHA_DETEC, {"id_failure_cause": None})}


# ── Tipo de tarefa + Classificação 1/2 (listas ao vivo p/ os dropdowns de criação) ──
# Quem guarda é o catálogo dos tipos (`catalogos.tipos_classif`, 24 h e em disco, 31/10/2026). A cópia que ficava aqui
# (`_TIPOS_CACHE`, uma leitura por processo) nunca vencia: o tipo criado no Fracttal só aparecia no reinício.
def _lista_tipos(metodo: str, key: str) -> list:
    """Busca uma lista de tipos/classificações (id+description), ordenada por descrição, no Fracttal."""
    r = api._rpc_call(metodo, {"sort": [{"property": "description", "direction": "asc"}],
                           "page": 1, "limit": 300, "start": 0, "is_tree": False, "node": None})
    data = r.get("data") if isinstance(r, dict) else r
    out = []
    for d in (data if isinstance(data, list) else []):
        idv = d.get("id")
        if idv is None:                            # alguns endpoints nomeiam o id de outro jeito
            for k in ("id_task_type_main", "id_task_type", "id_task_type_2"):
                if d.get(k) is not None:
                    idv = d.get(k); break
        if idv is not None:
            out.append({"id": idv, "description": str(d.get("description") or "?")})
    return out


def get_task_types() -> list:
    """Tipos de tarefa AO VIVO (id_task_type_main) — inclui Religamento/Religamento Remoto."""
    return api._lista_tipos(api.RPC_TIPOS_MAIN, "main")


def get_classif1() -> list:
    """Classificação 1 (id_task_type)."""
    return api._lista_tipos(api.RPC_TIPOS_C1, "c1")


def get_classif2() -> list:
    """Classificação 2 (id_task_type_2)."""
    return api._lista_tipos(api.RPC_TIPOS_C2, "c2")


def get_tipos_classif() -> dict:
    """Tipo de tarefa + Classif 1 + Classif 2 numa chamada só (p/ a UI carregar tudo em 1 worker), lidos do Fracttal: é o
    leitor do catálogo dos tipos. As telas leem o catálogo (`catalogos.tipos_classif`)."""
    return {"tipos": api.get_task_types(), "c1": api.get_classif1(), "c2": api.get_classif2()}


def label_id_por_nome(nome: str):
    """id de uma etiqueta pelo NOME (casa exato, senão por trecho), do catálogo de etiquetas (`catalogos.etiquetas`; até
    31/10/2026 numa cópia própria que lembrava o "não existe" até o reinício). None se não existir no catálogo — quem chama
    segue sem a etiqueta em vez de derrubar a criação da OS. O nome que o catálogo não tem relê uma vez."""
    import catalogos
    n = api._norm_txt(nome)
    if not n:
        return None
    for reler in (False, True):
        try:
            labels = catalogos.etiquetas(reler=reler) or []
        except Exception:
            return None                                  # falha de rede não vira "não existe"
        exata = next((l for l in labels if api._norm_txt(l.get("description")) == n), None)
        parcial = next((l for l in labels if n in api._norm_txt(l.get("description"))), None)
        if (exata or parcial or {}).get("id"):
            return (exata or parcial)["id"]
    return None


def _label_performance_id():
    """id da etiqueta 'Performance' (p/ marcar toda OS de Performance)."""
    return api.label_id_por_nome("performance")


def _classif_ids(nome_c1: str, nome_c2: str) -> dict:
    """{'id_task_type','tasks_types_description','id_task_type_2','tasks_types_2_description'} a
    partir dos NOMES. Resolve no catálogo do Fracttal (editável lá dentro, então id fixo quebraria).
    Nome que não existir simplesmente não entra — melhor OS sem classificação que com a errada.
    O catálogo é o dos tipos (`catalogos.tipos_classif`, 31/10/2026); a cópia daqui (`_CLASSIF_CACHE`) nunca vencia."""
    import catalogos
    try:
        classif = catalogos.tipos_classif() or {}
    except Exception:
        return {}
    out = {}
    for chave, nome, campo_id, campo_desc in (
            ("c1", nome_c1, "id_task_type", "tasks_types_description"),
            ("c2", nome_c2, "id_task_type_2", "tasks_types_2_description")):
        alvo = str(nome or "").strip().lower()
        for x in (classif.get(chave) or []):
            if str(x.get("description") or "").strip().lower() == alvo:
                out[campo_id] = x.get("id")
                out[campo_desc] = str(x.get("description") or "")
                break
    return out


def tipo_main_ao_vivo(nome):
    """O id do Tipo de tarefa pelo NOME no catálogo vivo do Fracttal (o mesmo que as listas da Fila e do Criar OS
    mostram) — para o tipo que o TASK_TYPE_MAIN fixo não tem (a Zeladoria, 29/10/2026). Sem caixa nem espaço nas pontas;
    não achando no catálogo dos tipos (`catalogos.tipos_classif`), relê uma vez (tipo criado no Fracttal depois; no máximo
    uma vez por minuto, `catalogos.RELER_NA_FALTA_S`). None se não existir."""
    import catalogos
    alvo = str(nome or "").strip().lower()
    if not alvo:
        return None
    for reler in (False, True):
        try:
            tipos = (catalogos.tipos_classif(reler=reler) or {}).get("tipos") or []
        except Exception:
            return None
        for x in tipos:
            if str(x.get("description") or "").strip().lower() == alvo and x.get("id") is not None:
                return x.get("id")
    return None


import api  # noqa: E402 — no fim: o `api` importa este módulo

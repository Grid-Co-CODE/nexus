"""A nota da OS no Fracttal quando o motivo é escolhido (20/10/2026).

Levi: "quando selecionar o motivo vai preencher na nota da OS a data, o nome da tarefa, o ativo e o motivo de não fazer a
tarefa"; e "a justificativa do técnico também deve estar na OS". O Nexus escreve nas marcas feitas nele (a janela do
Quadro e o Painel do Fora da programação), com o login do Fracttal de quem marcou: a sessão do OS Creator da pessoa (o
cookie `os_sessao`, que o login do Nexus pelo Fracttal abre). A justificativa do técnico chega do App sem o login dele:
quem escreve é o App (o pedido `_propostas/nota-motivo/LEIA.md` do App de Campo).

A linha vai no FIM da nota, e o que já existe fica: o `editar_nota_os` do OS Creator reescreve a nota inteira, então se
lê a nota atual (o `note` da 1ª tarefa da OS no `work_orders_tasks_new_list`, o mesmo que ele lê) e grava ela + a linha.
Escreve ao ESCOLHER o motivo (marcar ou trocar); a observação editada e o motivo tirado não escrevem. A nota é efeito
colateral: a falha nela (sem login do Fracttal, OS concluída, o Fracttal fora) nunca derruba a marca, só é dita.

Em dois pedidos (26/10/2026): o cookie `os_sessao` mora em Path=/os, e o navegador não o manda a /t/pcm. Até aqui a marca
(em /t/pcm) chamava o `escrever` no mesmo pedido, que nunca via o login, e em produção NENHUMA nota saiu desde 20/10 (a
tela dizia "sem o login do Fracttal"; os testes passavam o cookie à mão). Agora a marca devolve um `pedido` assinado (a OS
e a linha, feitas pelo servidor) e a tela o manda à ponte `/os/_nexus/pcm/nota` (`ponte.pcm_nota`), onde o cookie chega,
como o comentário da Engenharia.
"""
from datetime import datetime, timedelta, timezone

from itsdangerous import BadData, URLSafeTimedSerializer

_BRT = timezone(timedelta(hours=-3))
# o pedido vale o bastante para a tela mandá-lo logo depois da marca (a janela do Quadro na hora; o painel ao recarregar)
PRAZO_DO_PEDIDO_S = 10 * 60


def _um(s) -> str:
    """Quebra de linha e espaço repetido viram um espaço só: a justificativa cabe numa linha da nota."""
    return " ".join(str(s or "").split())


def linha(quando: datetime, motivo: str, tarefa: str, codigo: str, obs: str) -> str:
    """Uma linha por justificativa, no formato do Levi (25/10/2026): "[Data e hora] - [Nome da atividade] - Motivo -
    [Justificativa do técnico, se tiver]". O ativo (`codigo`) não entra: não está no formato. Espelho do
    `_fora_nota_linha` do App (v300): os dois escrevem a mesma linha (os mesmos exemplos nos dois testes)."""
    l = f"[{quando.astimezone(_BRT):%d/%m/%Y %H:%M}] - [{_um(tarefa)}] - {_um(motivo)}"
    return l + (f" - [{_um(obs)}]" if _um(obs) else "")


def juntar(atual, nova: str) -> str:
    """A nota de agora com a linha nova no fim, sem linha em branco entre as justificativas (o RPC às vezes manda o texto
    "None" na nota vazia). Espelho do `_fora_nota_juntar` do App."""
    a = str(atual or "").strip()
    if a.lower() == "none":
        a = ""
    return f"{a}\n{nova}" if a else nova


def gravar(api, folio, texto: str) -> dict:
    """Acrescenta `texto` à nota da OS `folio` pelo `api` do OS Creator (na sessão de quem marcou). {"ok"} ou
    {"ok": False, "erro"}."""
    wid = api._wo_id_por_folio(folio)
    if not wid:
        return {"ok": False, "erro": f"não achei a OS {folio} no Fracttal"}
    r = api._rpc_call(api.RPC_WO_TASKS, {"page": 1, "limit": 50, "start": 0, "id_work_order": wid})
    d = r.get("data") if isinstance(r, dict) else r
    t0 = d[0] if isinstance(d, list) and d else {}
    # a linha que já está na nota não volta: a tela pode mandar o mesmo pedido duas vezes (o clique repetido, a volta
    # depois de "o Fracttal não respondeu" com a nota gravada)
    if texto.strip() in (x.strip() for x in str(t0.get("note") or "").splitlines()):
        return {"ok": True}
    res = api.editar_nota_os(wid, juntar(t0.get("note"), texto))
    return {"ok": True} if res.get("ok") else {"ok": False, "erro": res.get("erro") or "o Fracttal recusou a nota"}


def _assinador(app) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(app.secret_key, salt="nexus/pcm/nota_os")


def _quem(usuario) -> str:
    return str((usuario or {}).get("email") or "") if isinstance(usuario, dict) else ""


def pedido(app, folio, texto: str, usuario) -> str:
    """O pedido da nota que a tela leva à ponte: a OS e a linha feitas aqui (a ponte não escreve texto que venha da
    página) e de quem marcou (o pedido não serve noutro login)."""
    return _assinador(app).dumps({"os": str(folio), "texto": texto, "quem": _quem(usuario)})


def abrir_pedido(app, valor, usuario) -> dict | None:
    """{os, texto} do pedido assinado por este Nexus há menos de PRAZO_DO_PEDIDO_S para este login; senão None."""
    try:
        p = _assinador(app).loads(str(valor or ""), max_age=PRAZO_DO_PEDIDO_S)
    except BadData:
        return None
    if not isinstance(p, dict) or p.get("quem") != _quem(usuario) or not p.get("os") or not p.get("texto"):
        return None
    return {"os": str(p["os"]), "texto": str(p["texto"])}


def escrever(app, folio, texto: str) -> dict:
    """A nota da OS com o login do Fracttal de quem está no pedido. Só vê o login num pedido de /os (a ponte
    `/os/_nexus/pcm/nota`); sem ele (o administrador pela senha, a conta Microsoft), não escreve."""
    from ..torres.oscreator import ponte
    s = ponte.sessao_do_os(app)
    jwt = str(s.get("jwt") or "")
    if not jwt:
        return {"ok": False, "erro": "sem o login do Fracttal nesta sessão (quem entra pela senha não tem)"}
    email = str((s.get("conta") or {}).get("email") or "")
    ponte.clone(app)                             # põe o `api` do clone no sys.path
    import api as os_api                         # noqa: E402
    from os_web import sessao as os_sessao       # noqa: E402
    with os_sessao.contexto(jwt, email):
        try:
            return gravar(os_api, folio, texto)
        except os_api.SessionExpired:
            return {"ok": False, "erro": "a sessão do Fracttal caiu: entre de novo"}
        except Exception as e:                   # noqa: BLE001 — rede, 429, Fracttal fora: a marca vale, a nota não
            return {"ok": False, "erro": f"o Fracttal não respondeu ({type(e).__name__})"}


def frase(r: dict | None) -> str:
    """O que a tela diz da nota."""
    if not r:
        return ""
    return "Nota da OS escrita no Fracttal." if r.get("ok") else f"A nota da OS não foi escrita: {r.get('erro')}."

"""As OS das Estações Meteorológicas (ETM) para a tela ETMs da Engenharia (Levi, 26/10/2026: "Quero que inclua essa
visão de ETMs no Nexus, engenharia, aba própria"): o Planner do app de ETM da Engenharia, lido pelo Nexus. Desenho em
docs/superpowers/specs/2026-10-26-engenharia-etm-design.md.

Leitura (medida em 26/10/2026, só leitura): `items?field_1=Estação Meteorológica` dá as ETMs (172, duas páginas; a
descrição confere) e `work_orders?items_log_description=Estação Meteorológica` as OS delas (1213, 13 páginas; o filtro é
por trecho). Fica a OS cujo código é de uma ETM: 15 pedidos por leitura, contra os 172 do app (um por ETM). As linhas do
REST são por tarefa; a tela é por OS (o número), como o Quadro da equipe, e o cartão é o dele (`os_equipe._cartao`). A
usina de cada ETM (o `groups_1_description` do ativo) dá as usinas do Histórico, com quantas ETMs cada uma tem.

Engenharia, Chamados e Campo (Levi, 26/10/2026: "Engenharia e Chamados vai pelas pessoas dos setores, Campo é o
restante!"): o setor de quem está com a OS, pelo id do Fracttal, nos setores de Base → Acessos → Pessoas e setores (livro
`nexus_setores`, a última decisão de cada pessoa); quem não é de nenhum dos dois é Campo. Sem o banco dos setores, a
Engenharia vem da lista do Quadro da equipe (`os_equipe.nomes`, pelo nome), Chamados não se separa e a tela diz.

Quais OS entram (a regra do app, sem nome no código): as Corretivas e as Administrativas, mais as de responsável ou
solicitante da Engenharia ou de Chamados. O solicitante do Fracttal é texto livre: casa pelo nome do Fracttal das
pessoas dos setores, sem acento nem caixa.

A cópia vale 5 min e é relida por trás enquanto a tela é usada (o mesmo do `os_equipe`); a leitura que falha guarda a
anterior e diz. Nada vai para o banco.
"""
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from . import os_equipe

ETM = "Estação Meteorológica"
BRT = timezone(timedelta(hours=-3))
VALIDADE_S = 300
FORCAR_S = 5
USO_S = 2 * 3600
QUENTE_S = 60
TETO_ETMS = 5       # páginas de 100 (172 ETMs em 26/10/2026)
TETO_OS = 40        # páginas de 100 (1213 OS em 26/10/2026): um filtro ignorado não vira o Fracttal inteiro
TIPOS_SEMPRE = ("corretiva", "administrativa")
SETORES = ("engenharia", "chamados")      # os setores que separam a OS (o nome em Base → Acessos, sem acento nem caixa)
COLUNAS = (("nao_iniciada", "Não iniciadas"), ("em_andamento", "Em andamento"), ("finalizada", "Finalizadas"),
           ("cancelada", "Canceladas"))
# a coluna do quadro da equipe → a do Planner do app (a verificação ainda não fechou: está em andamento)
_DA_COLUNA = {"fazer": "nao_iniciada", "execucao": "em_andamento", "verificacao": "em_andamento",
              "concluida": "finalizada", "cancelada": "cancelada"}
SEM_USINA = "Usina não identificada"
UFS = frozenset("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split())
# "etms" = {código da ETM: a usina dela no Fracttal}; "usinas" = {usina: quantas ETMs} (o Histórico lista por elas)
_EST = {"ts": 0.0, "os": [], "etms": {}, "usinas": {}, "lendo": False, "erro": "", "erro_em": 0.0, "usado": 0.0,
        "erro_setores": ""}
_TRAVA = threading.Lock()


def _ler_fracttal(path):
    from ..campo import fracttal
    return fracttal.ler(path)


def cliente_de(usina) -> str:
    """O cliente é o trecho antes do primeiro " - " do nome da usina no Fracttal ("Cliente - Usina - UF")."""
    u = str(usina or "").strip()
    if not u or u == SEM_USINA:
        return "Não identificado"
    return u.split(" - ", 1)[0].strip() or u


def usina_curta(usina) -> str:
    """O nome da usina sem o cliente e o estado (Levi, 26/10/2026: "o nome da usina está vindo completo, o ideal seria
    sem a informação do nome do cliente e estado!"): do "Cliente - Usina - UF" do Fracttal fica o meio. Se não sobra
    nada ("Cliente - MG"), o nome inteiro."""
    u = " ".join(str(usina or "").split())
    if not u:
        return SEM_USINA
    partes = [p.strip() for p in u.split(" - ")]
    if len(partes) == 1:
        return u
    meio = partes[1:]
    if meio[-1].upper() in UFS:
        meio = meio[:-1]
    return " - ".join(meio) or u


def coluna_etm(coluna: str) -> str:
    return _DA_COLUNA.get(coluna, "em_andamento")


def _limpo(v) -> str:
    return " ".join(str(v or "").split())


def _id(v) -> str:
    """O id do Fracttal como texto (a API pode devolver "123.0")."""
    try:
        return str(int(float(v)))
    except (TypeError, ValueError):
        return ""


def _setor_pelo_nome(nome, setores: dict) -> str:
    """O setor pelo nome do Fracttal: igual ou começando pelo nome da pessoa do setor, sem acento nem caixa (o nome da
    lista pode ser o curto; o do Fracttal, mais comprido). "campo" quando não casa."""
    n = os_equipe._norm(nome)
    for s in SETORES:
        if n and any(n == e or n.startswith(e + " ") for e in (setores.get("nomes") or {}).get(s) or []):
            return s
    return "campo"


def _setor_do_responsavel(w0: dict, setores: dict) -> str:
    """Pelo id do Fracttal nos setores de Base → Acessos; sem eles (o banco fora), pelo nome."""
    if setores.get("por_id"):
        return setores["por_id"].get(_id(w0.get("id_personnel")), "campo")
    return _setor_pelo_nome(w0.get("personnel_description"), setores)


def montar(linhas: list[dict], codigos_etm: set, setores: dict, hoje) -> list[dict]:
    """As OS de ETM que a tela mostra (uma por número), no cartão do Quadro da equipe com o que o Planner pede.
    `setores` = {"por_id": {id do Fracttal: setor}, "nomes": {setor: [nomes do Fracttal, sem acento nem caixa]}}."""
    por: dict = {}
    for w in linhas:
        if _limpo(w.get("code")) in codigos_etm:
            por.setdefault(str(w.get("wo_folio") or w.get("id_work_order")), []).append(w)
    out = []
    for folio, ts in por.items():
        w0 = ts[0]
        tipo = os_equipe._norm(w0.get("tasks_log_task_type_main"))
        resp, solic = _limpo(w0.get("personnel_description")), _limpo(w0.get("requested_by"))
        setor = _setor_do_responsavel(w0, setores)
        if not (tipo in TIPOS_SEMPRE or setor != "campo" or _setor_pelo_nome(solic, setores) != "campo"):
            continue
        c = os_equipe._cartao(folio, ts, {"id": w0.get("id_personnel"), "nome": resp}, hoje)
        # a usina com o mesmo nome limpo da ETM (`_ler_etms`): a OS sem grupo virava "" (o cartão dela não abria) e o
        # espaço dobrado separava uma usina em duas (revisão de 26/10/2026)
        usina = _limpo(c["usina"]) or SEM_USINA
        c.update(usina=usina, coluna_etm=coluna_etm(c["coluna"]), trabalho=setor, cliente=cliente_de(usina),
                 responsavel=resp, solicitante=solic, criado_por=_limpo(w0.get("created_by")))
        out.append(c)
    return out


def _ler_setores(app) -> dict:
    """Os setores Engenharia e Chamados de Base → Acessos → Pessoas e setores: quem é de cada um pela última decisão
    (o id do Fracttal) e o nome do Fracttal dessas pessoas (para o solicitante, que é texto livre)."""
    from ..cadastro import setores as S
    from ..campo import visao
    st = S.ler(visao._base(), visao._sessao())
    if not st.get("lido_em"):
        raise RuntimeError(st.get("erro") or "o livro dos setores não veio")
    ids = {os_equipe._norm(s["nome"]): s["setor_id"] for s in S.ativos(st.get("setores") or [])}
    alvo = {ids[n]: n for n in SETORES if n in ids}
    por_id = {_id(fid): alvo[sid] for fid, sid in S.vigentes(st.get("decisoes") or []).items()
              if sid in alvo and _id(fid)}
    nomes: dict = {s: [] for s in SETORES}
    try:
        from ..cadastro import fracttal_pessoal as FP
        pessoal = {_id(p.get("id")): p.get("nome") for p in (FP.ler_pessoal().get("pessoas") or [])}
    except Exception:           # noqa: BLE001 — sem os nomes, o solicitante não separa; o responsável vai pelo id
        pessoal = {}
    for fid, s in por_id.items():
        n = os_equipe._norm(pessoal.get(fid))
        if n:
            nomes[s].append(n)
    return {"por_id": por_id, "nomes": nomes}


def _setores(app) -> tuple[dict, str]:
    """Os setores e o erro: sem o banco, a Engenharia pela lista do Quadro da equipe (os nomes) e Chamados vazio."""
    try:
        return _ler_setores(app), ""
    except Exception as e:      # noqa: BLE001 — a tela lê assim mesmo, e diz
        equipe = [os_equipe._norm(n) for n in os_equipe.nomes(app.config) if os_equipe._norm(n)]
        return {"por_id": {}, "nomes": {"engenharia": equipe, "chamados": []}}, f"{type(e).__name__}: {str(e)[:160]}"


_setores_original = _setores


def _paginas(path: str, teto: int) -> list[dict]:
    out, inicio = [], 0
    for _ in range(teto):
        r = _ler_fracttal(f"{path}&limit=100&start={inicio}")
        d = (r.get("data") if isinstance(r, dict) else r) or []
        out += d
        if len(d) < 100:
            return out
        inicio += 100
    raise RuntimeError(f"a leitura passou do teto de {teto} páginas de {path.split('?')[0]}: nada foi trocado")


def _ler_etms() -> dict:
    """{código da ETM: a usina dela} (o `groups_1_description` do ativo, o mesmo que o app de ETM agrupava)."""
    alvo = os_equipe._norm(ETM)
    return {_limpo(i.get("code")): _limpo(i.get("groups_1_description")) or SEM_USINA
            for i in _paginas(f"items?field_1={quote(ETM)}", TETO_ETMS)
            if i.get("code") and alvo in os_equipe._norm(i.get("description"))}


def _reler(app):
    try:
        with app.app_context():
            setores, erro_setores = _setores(app)
            etms = _ler_etms()
            linhas = _paginas(f"work_orders?items_log_description={quote(ETM)}", TETO_OS)
            oss = montar(linhas, etms, setores, datetime.now(BRT).date())
            usinas: dict = {}
            for u in etms.values():
                usinas[u] = usinas.get(u, 0) + 1
            _EST.update(os=oss, etms=etms, usinas=usinas, ts=time.time(), erro="", erro_em=0.0,
                        erro_setores=erro_setores)
    except Exception as e:      # noqa: BLE001 — 429 ou rede: fica a leitura anterior, e a tela diz
        _EST.update(erro=str(e)[:200], erro_em=time.time())
    finally:
        _EST["lendo"] = False


def pedir_releitura(app=None, esperar=False, forcar=False):
    """Relê se a cópia tem mais de 5 min (`forcar`: mais de 5 s). Sem cópia nenhuma, `esperar` lê na hora."""
    if time.time() - _EST["ts"] < (FORCAR_S if forcar else VALIDADE_S):
        return
    with _TRAVA:
        if _EST["lendo"] or time.time() - _EST["erro_em"] < 60:     # depois de um 429, um minuto de folga
            return
        _EST["lendo"] = True
    if app is None:
        from flask import current_app
        app = current_app._get_current_object()
    if esperar or app.config.get("TESTING"):
        _reler(app)
    else:
        threading.Thread(target=_reler, args=(app,), daemon=True, name="nexus-etm").start()


def marcar_uso():
    """A tela foi aberta agora: o `manter_quente` segue relendo por trás pelas próximas 2 h."""
    _EST["usado"] = time.time()


def _tique(app, agora: float | None = None) -> bool:
    agora = time.time() if agora is None else agora
    if not _EST["usado"] or agora - _EST["usado"] > USO_S:
        return False
    if _EST["ts"] and agora - _EST["ts"] < VALIDADE_S:
        return False
    pedir_releitura(app, forcar=True)
    return True


def manter_quente(app):
    """A volta de cada minuto (`_tique`), numa thread. Quem chama é o `instalar` da engenharia, nunca o create_app."""
    def laco():
        while True:
            time.sleep(QUENTE_S)
            try:
                _tique(app)
            except Exception:       # noqa: BLE001 — a volta seguinte tenta de novo; a tela relê na visita
                pass
    threading.Thread(target=laco, daemon=True, name="nexus-etm-quente").start()


def dados() -> dict:
    return {"os": list(_EST["os"]), "usinas": dict(_EST["usinas"]), "lido": _EST["ts"], "lendo": _EST["lendo"],
            "erro": _EST["erro"], "erro_setores": _EST["erro_setores"]}


def eh_etm(codigo) -> bool | None:
    """O código é de uma ETM? None sem leitura nenhuma (não se chuta)."""
    if not _EST["etms"]:
        return None
    return _limpo(codigo) in _EST["etms"]


def limpar():
    _EST.update(ts=0.0, os=[], etms={}, usinas={}, lendo=False, erro="", erro_em=0.0, usado=0.0, erro_setores="")

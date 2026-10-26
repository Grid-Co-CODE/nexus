"""As OS das Estações Meteorológicas (ETM) para a tela ETMs da Engenharia (Levi, 26/10/2026: "Quero que inclua essa
visão de ETMs no Nexus, engenharia, aba própria"): o Planner do app de ETM da Engenharia, lido pelo Nexus. Desenho em
docs/superpowers/specs/2026-10-26-engenharia-etm-design.md.

Leitura (medida em 26/10/2026, só leitura): `items?field_1=Estação Meteorológica` dá as ETMs (172, duas páginas; a
descrição confere) e `work_orders?items_log_description=Estação Meteorológica` as OS delas (1213, 13 páginas; o filtro é
por trecho). Fica a OS cujo código é de uma ETM: 15 pedidos por leitura, contra os 172 do app (um por ETM). As linhas do
REST são por tarefa; a tela é por OS (o número), como o Quadro da equipe, e o cartão é o dele (`os_equipe._cartao`).

Quais OS entram (a regra do app, sem nome no código): as Corretivas e as Administrativas, mais as de responsável ou
solicitante da equipe da Engenharia (a lista do Quadro da equipe, `os_equipe.nomes`, fora do git; no app eram nomes
escritos no código). Análise de Engenharia = não é Corretiva e o responsável é da equipe; o resto é Campo. O solicitante
do Fracttal é texto livre: casa sem acento nem caixa.

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
COLUNAS = (("nao_iniciada", "Não iniciadas"), ("em_andamento", "Em andamento"), ("finalizada", "Finalizadas"),
           ("cancelada", "Canceladas"))
# a coluna do quadro da equipe → a do Planner do app (a verificação ainda não fechou: está em andamento)
_DA_COLUNA = {"fazer": "nao_iniciada", "execucao": "em_andamento", "verificacao": "em_andamento",
              "concluida": "finalizada", "cancelada": "cancelada"}
_EST = {"ts": 0.0, "os": [], "etms": set(), "lendo": False, "erro": "", "erro_em": 0.0, "usado": 0.0}
_TRAVA = threading.Lock()


def _ler_fracttal(path):
    from ..campo import fracttal
    return fracttal.ler(path)


def cliente_de(usina) -> str:
    """O cliente é o trecho antes do primeiro " - " do nome da usina no Fracttal ("Cliente - Usina - UF")."""
    u = str(usina or "").strip()
    if not u:
        return "Não identificado"
    return u.split(" - ", 1)[0].strip() or u


def coluna_etm(coluna: str) -> str:
    return _DA_COLUNA.get(coluna, "em_andamento")


def _limpo(v) -> str:
    return " ".join(str(v or "").split())


def _da_equipe(nome: str, equipe: list[str]) -> bool:
    """O nome do Fracttal é de alguém da lista: igual ou começando por ele, sem acento nem caixa (o nome da lista é o
    curto; o do Fracttal pode vir mais comprido)."""
    n = os_equipe._norm(nome)
    return bool(n) and any(n == e or n.startswith(e + " ") for e in equipe)


def montar(linhas: list[dict], codigos_etm: set, equipe: list[str], hoje) -> list[dict]:
    """As OS de ETM que a tela mostra (uma por número), no cartão do Quadro da equipe com o que o Planner pede."""
    por: dict = {}
    for w in linhas:
        if _limpo(w.get("code")) in codigos_etm:
            por.setdefault(str(w.get("wo_folio") or w.get("id_work_order")), []).append(w)
    eq = [os_equipe._norm(n) for n in equipe if os_equipe._norm(n)]
    out = []
    for folio, ts in por.items():
        w0 = ts[0]
        tipo = os_equipe._norm(w0.get("tasks_log_task_type_main"))
        resp, solic = _limpo(w0.get("personnel_description")), _limpo(w0.get("requested_by"))
        resp_eq = _da_equipe(resp, eq)
        if not (tipo in TIPOS_SEMPRE or resp_eq or _da_equipe(solic, eq)):
            continue
        c = os_equipe._cartao(folio, ts, {"id": w0.get("id_personnel"), "nome": resp}, hoje)
        c.update(coluna_etm=coluna_etm(c["coluna"]), trabalho="analise" if tipo != "corretiva" and resp_eq else "campo",
                 cliente=cliente_de(c["usina"]), responsavel=resp, solicitante=solic,
                 criado_por=_limpo(w0.get("created_by")))
        out.append(c)
    return out


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


def _ler_etms() -> set:
    alvo = os_equipe._norm(ETM)
    return {_limpo(i.get("code")) for i in _paginas(f"items?field_1={quote(ETM)}", TETO_ETMS)
            if i.get("code") and alvo in os_equipe._norm(i.get("description"))}


def _reler(app):
    try:
        with app.app_context():
            equipe = os_equipe.nomes(app.config)
            etms = _ler_etms()
            linhas = _paginas(f"work_orders?items_log_description={quote(ETM)}", TETO_OS)
            oss = montar(linhas, etms, equipe, datetime.now(BRT).date())
            _EST.update(os=oss, etms=etms, ts=time.time(), erro="", erro_em=0.0)
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
    return {"os": list(_EST["os"]), "lido": _EST["ts"], "lendo": _EST["lendo"], "erro": _EST["erro"]}


def eh_etm(codigo) -> bool | None:
    """O código é de uma ETM? None sem leitura nenhuma (não se chuta)."""
    if not _EST["etms"]:
        return None
    return _limpo(codigo) in _EST["etms"]


def limpar():
    _EST.update(ts=0.0, os=[], etms=set(), lendo=False, erro="", erro_em=0.0, usado=0.0)

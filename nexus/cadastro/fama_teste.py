"""Leitura de TESTE da API da FAMA (11/11/2026): o que já existe lá, só em contagens, para desenhar a ligação das OS dos
clientes com a programação semanal.

Levi, 11/11/2026: o cliente cria a OS na FAMA, ela aparece para o programador automático e cai no App de Campo ("a ideia é
não ficarmos criando e editando e sim acompanhando"). A chave mora só no .env do servidor (a T.I. pôs), então a leitura de
teste roda no servidor, por esta página: só o administrador, fora do menu, só GET, com teto de chamadas e uma pausa entre
as páginas (a API é de outra empresa), e o resultado guardado por 15 min.

Nada de pessoa nem de texto livre na saída: dos usuários, só quantos são; das OS, contagens, datas e quanto cada campo vem
preenchido, nunca o título, a descrição ou o registro; das usinas (os "projetos" da FAMA), o nome. A chave é de
PRESTADORA: só abre as rotas /v2/contractor/ (as gerais pedem o login de um usuário e deram 401). A chave nunca
aparece. Página TEMPORÁRIA: sai depois do teste (nexus/cadastro/CLAUDE.md)."""
from __future__ import annotations

import threading
import time
from collections import Counter

import requests
from flask import current_app, jsonify, request, session

BASE = "https://api.fama.energy"
TETO_CHAMADAS = 10          # a leitura faz 2 (a lista e um detalhe); o teto segura o laço que der errado
TETO_S = 75
PAUSA_S = 0.3               # entre uma chamada e outra: "sem gritar alto" (Levi, 11/11/2026)
GUARDA_S = 15 * 60
_CACHE: dict = {}
_TRAVA = threading.Lock()

def _vazio(v) -> bool:
    return v is None or v == "" or v == [] or v == {}


class _Leitor:
    """Só GET, com a chave no cabeçalho, contando as chamadas e o tempo; erro de rede vira o nome do erro, nunca a mensagem
    (a mensagem do requests pode trazer a URL inteira)."""

    def __init__(self, chave: str, sessao=None):
        self.s = sessao or requests.Session()
        self.chave = chave
        self.chamadas, self.inicio = 0, time.monotonic()

    def pode(self) -> bool:
        return self.chamadas < TETO_CHAMADAS and time.monotonic() - self.inicio < TETO_S

    def get(self, caminho: str, params: dict | None = None) -> tuple[dict, object]:
        if not self.pode():
            return {"status": None, "erro": "teto da leitura"}, None
        if self.chamadas:
            time.sleep(PAUSA_S)
        self.chamadas += 1
        t0 = time.monotonic()
        try:
            r = self.s.get(BASE + caminho, params=params, timeout=20, headers={"X-Contractor-Key": self.chave})
        except requests.RequestException as ex:
            return {"status": None, "erro": type(ex).__name__}, None
        info = {"status": r.status_code, "ms": int((time.monotonic() - t0) * 1000)}
        try:
            return info, r.json()
        except ValueError:
            return info, None


def _forma(corpo) -> dict:
    """A forma da resposta, sem valor nenhum: lista ou objeto, quantos itens e os nomes dos campos."""
    if isinstance(corpo, list):
        prim = corpo[0] if corpo and isinstance(corpo[0], dict) else {}
        return {"tipo": "lista", "itens": len(corpo), "campos": sorted(prim)[:80]}
    if isinstance(corpo, dict):
        return {"tipo": "objeto", "campos": sorted(corpo)[:80]}
    return {"tipo": type(corpo).__name__}


def _itens(corpo) -> list:
    if isinstance(corpo, list):
        return corpo
    if isinstance(corpo, dict):
        for k in ("rows", "projects", "items", "results", "data"):
            if isinstance(corpo.get(k), list):
                return corpo[k]
    return []


def _detalhe(info: dict, corpo) -> str | None:
    """A frase de erro da FAMA ("Could not validate credentials"), cortada; não é dado de pessoa."""
    if info.get("status") != 200 and isinstance(corpo, dict) and isinstance(corpo.get("detail"), str):
        return corpo["detail"][:120]
    return None


def _nome(obj, campo: str) -> str:
    if isinstance(obj, dict):
        return str(obj.get(campo) or obj.get("name") or obj.get("id") or "(vazio)")[:60]
    return "(vazio)"


def _data(v) -> str:
    return str(v or "")[:10]


def ler(chave: str, sessao=None) -> dict:
    """As rotas da PRESTADORA, as únicas que a chave abre (a FAMA recusou as outras com 401 em 11/11/2026): a lista das OS
    atribuídas à Grid, inteira (a rota não tem filtro nem página), e o detalhe da mais nova, só a forma."""
    L = _Leitor(chave, sessao)
    out: dict = {"quando": time.strftime("%d/%m/%Y %H:%M:%S")}
    info, corpo = L.get("/v2/contractor/service-orders/")
    linhas = [x for x in _itens(corpo) if isinstance(x, dict)]
    lst: dict = {**info, "erro_da_fama": _detalhe(info, corpo), "total": len(linhas),
                 "campos": sorted({k for x in linhas for k in x})[:120]}
    if linhas:
        lst["preenchido_pct"] = {c: round(100 * sum(not _vazio(x.get(c)) for x in linhas) / len(linhas))
                                 for c in lst["campos"]}
        for nome, campo, sub in (("por_status", "status", "service_status"), ("por_tipo", "type", "service_type"),
                                 ("por_severidade", "severity", "service_severity"),
                                 ("por_especialidade", "specialty", "specialty"),
                                 ("por_equipe", "management_team_type", "name")):
            lst[nome] = Counter(_nome(x.get(campo), sub) for x in linhas)
        lst["por_usina"] = Counter(_nome(x.get("project"), "name") for x in linhas).most_common(300)
        lst["por_ano"] = Counter(_data(x.get("creation_date"))[:4] or "(sem data)" for x in linhas)
        criadas = sorted(d for d in (_data(x.get("creation_date")) for x in linhas) if d)
        lst["criacao"] = {"mais_antiga": criadas[0] if criadas else None, "mais_nova": criadas[-1] if criadas else None}
        previstas = sorted(d for d in (_data(x.get("expected_execution_date")) for x in linhas) if d)
        lst["previstas"] = {"com_data": len(previstas), "primeira": previstas[0] if previstas else None,
                            "ultima": previstas[-1] if previstas else None}
    out["lista"] = lst
    if linhas:
        nova = max(linhas, key=lambda x: str(x.get("creation_date") or ""))
        info, corpo = L.get(f"/v2/contractor/service-orders/{nova.get('id')}")
        det: dict = {**info, "erro_da_fama": _detalhe(info, corpo)}
        if isinstance(corpo, dict):          # só a forma: os campos e, das listas e objetos, os campos de dentro
            det["campos"] = sorted(corpo)
            det["listas"] = {k: {"itens": len(v), "campos": sorted(v[0]) if v and isinstance(v[0], dict) else []}
                             for k, v in corpo.items() if isinstance(v, list)}
            det["objetos"] = {k: sorted(v) for k, v in corpo.items() if isinstance(v, dict)}
        out["detalhe_da_mais_nova"] = det
    out["chamadas"] = L.chamadas
    out["segundos"] = round(time.monotonic() - L.inicio, 1)
    return out


def registrar_fama_teste(bp) -> None:
    @bp.route("/fama-teste")
    def fama_teste():
        if not session.get("admin"):
            return jsonify({"erro": "só o administrador do Nexus"}), 403
        chave = (current_app.config.get("NEXUS_FAMA_CHAVE") or "").strip()
        if not chave:
            return jsonify({"erro": "sem a NEXUS_FAMA_CHAVE no .env deste Nexus"}), 409
        with _TRAVA:                                     # uma leitura por vez; a guardada vale 15 min
            g = _CACHE.get("leitura")
            if not g or request.args.get("novo") == "1" or time.time() - g["em"] > GUARDA_S:
                g = {"em": time.time(), "dados": ler(chave)}
                _CACHE["leitura"] = g
        return jsonify(g["dados"])

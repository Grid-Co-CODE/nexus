"""Leitura de TESTE da API da FAMA (11/11/2026): o que já existe lá, só em contagens, para desenhar a ligação das OS dos
clientes com a programação semanal.

Levi, 11/11/2026: o cliente cria a OS na FAMA, ela aparece para o programador automático e cai no App de Campo ("a ideia é
não ficarmos criando e editando e sim acompanhando"). A chave mora só no .env do servidor (a T.I. pôs), então a leitura de
teste roda no servidor, por esta página: só o administrador, fora do menu, só GET, com teto de chamadas e uma pausa entre
as páginas (a API é de outra empresa), e o resultado guardado por 15 min.

Nada de pessoa nem de texto livre na saída: dos usuários, só quantos são; das OS, contagens, datas e quanto cada campo vem
preenchido, nunca o título, a descrição ou o registro; das usinas (os "projetos" da FAMA), o id e o nome. A chave nunca
aparece. Página TEMPORÁRIA: sai depois do teste (nexus/cadastro/CLAUDE.md)."""
from __future__ import annotations

import threading
import time
from collections import Counter

import requests
from flask import current_app, jsonify, request, session

BASE = "https://api.fama.energy"
TETO_CHAMADAS = 40          # a leitura inteira faz umas 30; o teto segura o laço que der errado
TETO_S = 75
PAUSA_S = 0.3               # entre uma chamada e outra: "sem gritar alto" (Levi, 11/11/2026)
POR_PAGINA = 100
PAGINAS_DA_AMOSTRA = 5
GUARDA_S = 15 * 60
_CACHE: dict = {}
_TRAVA = threading.Lock()

# os campos da OS cuja presença interessa ao desenho (quanto vem preenchido, nunca o valor)
CAMPOS_OS = ("project_id", "status_id", "type_id", "severity_id", "specialty_id", "management_team_type_id",
             "responsible_id", "company_id", "partner_company_id", "assets", "tasks", "logs", "creation_date",
             "activation_date", "schedule_start_date", "expected_execution_date", "start_date", "finish_date",
             "description", "title")


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


def _nomes(corpo, teto: int = 60) -> list[dict]:
    """Os catálogos (status, tipos, severidades, pendências): o id e o nome, cortado."""
    out = []
    for x in _itens(corpo)[:teto]:
        if isinstance(x, dict):
            nome = x.get("name") or x.get("description") or x.get("title") or ""
            out.append({"id": x.get("id"), "nome": str(nome)[:60]})
    return out


def ler(chave: str, sessao=None) -> dict:
    L = _Leitor(chave, sessao)
    out: dict = {"quando": time.strftime("%d/%m/%Y %H:%M:%S")}

    info, corpo = L.get("/mcp/whoami/")
    out["quem_e_a_chave"] = {**info, "forma": _forma(corpo)}

    catalogos = {}
    for nome, caminho in (("status", "/service-orders/status/"), ("tipos", "/service-orders/types/"),
                          ("severidades", "/service-orders/severities/"), ("especialidades", "/service-orders/specialties/"),
                          ("equipes", "/service-orders/team-types/"), ("pendencias", "/service-orders/pendencies/")):
        info, corpo = L.get(caminho)
        catalogos[nome] = {**info, "itens": _nomes(corpo)}
    out["catalogos"] = catalogos

    info, corpo = L.get("/mcp/projects/", {"limit": 500})
    projetos = [{"id": p.get("id"), "nome": str(p.get("name") or p.get("title") or "")[:80]}
                for p in _itens(corpo) if isinstance(p, dict)]
    out["usinas"] = {**info, "total": corpo.get("total") if isinstance(corpo, dict) else None, "lista": projetos,
                     "campos": _forma(_itens(corpo)).get("campos")}

    info, corpo = L.get("/users/")
    out["usuarios"] = {**info, "quantos": len(_itens(corpo))}           # só a conta: nome e e-mail não saem

    info, corpo = L.get("/assets/")
    out["ativos"] = {**info, "quantos": len(_itens(corpo)), "campos": _forma(_itens(corpo)).get("campos")}

    # as OS: o total, a mais antiga e a mais nova, uma amostra para ver o que vem preenchido e o total de cada status e tipo
    os_: dict = {}
    info, corpo = L.get("/v2/service-orders/", {"limit": 1, "offset": 0})
    os_["total"] = corpo.get("total") if isinstance(corpo, dict) else None
    os_["leitura"] = info
    for ponta, ordem in (("mais_antiga", "asc"), ("mais_nova", "desc")):
        info, corpo = L.get("/v2/service-orders/", {"limit": 1, "offset": 0, "sort": "creation_date", "order": ordem})
        linha = (_itens(corpo) or [{}])[0]
        os_[ponta] = {"status": info.get("status"), "criada_em": str(linha.get("creation_date") or "")[:19] or None}
    amostra: list = []
    for pagina in range(PAGINAS_DA_AMOSTRA):
        info, corpo = L.get("/v2/service-orders/", {"limit": POR_PAGINA, "offset": pagina * POR_PAGINA,
                                                    "sort": "creation_date", "order": "desc"})
        linhas = [x for x in _itens(corpo) if isinstance(x, dict)]
        amostra += linhas
        if len(linhas) < POR_PAGINA:
            break
    os_["amostra"] = len(amostra)
    os_["campos_que_vem"] = sorted({k for x in amostra for k in x})[:120]
    os_["preenchido_pct"] = {c: round(100 * sum(not _vazio(x.get(c)) for x in amostra) / len(amostra))
                             for c in CAMPOS_OS if amostra and any(c in x for x in amostra)}
    os_["tarefas_por_os"] = Counter(min(len(x.get("tasks") or []), 10) for x in amostra)
    os_["ativos_por_os"] = Counter(min(len(x.get("assets") or []), 10) for x in amostra)
    os_["por_usina_na_amostra"] = Counter(str(x.get("project_id")) for x in amostra).most_common(50)
    os_["por_ano_na_amostra"] = Counter(str(x.get("creation_date") or "")[:4] for x in amostra)
    for nome, campo in (("por_status", "status_id"), ("por_tipo", "type_id")):
        totais = {}
        for item in catalogos.get("status" if campo == "status_id" else "tipos", {}).get("itens", [])[:15]:
            info, corpo = L.get("/v2/service-orders/", {"limit": 1, "offset": 0, campo: item["id"]})
            totais[f'{item["id"]} {item["nome"]}'] = corpo.get("total") if isinstance(corpo, dict) else info.get("status")
        os_[nome] = totais
    out["os"] = os_
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

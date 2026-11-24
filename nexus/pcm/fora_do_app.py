"""PCM → OS fora do App (24/11/2026): quem fecha OS fora do App de Campo, por semana.

Levi, 24/11/2026, no chat do App de Campo: "Eu quero uma lista de todos os técnicos que estão fazendo OS pelo computador"
(o caso que puxou: um técnico fechou 11 de 11 OS direto no Fracttal, sem abrir o App em duas semanas). Ele aprovou a
medição fixa por semana e mandou a tela para o Nexus PCM. Decisões dele no mesmo dia, no chat do Nexus PCM: a tela fica no
PCM, junto do Acompanhamento; mostra só os técnicos de campo, com o "Mostrar todos" para conferir; e a veem o PCM, a
Supervisão Campo e os administradores (`Tela.do_setor`).

A MEDIÇÃO É DO APP (v381; o contrato inteiro em `app-campo-docs/_propostas/v381-fonte/contrato_fora_do_app_nexus.md`):
`GET <base>/app/nexus/fora-do-app?semanas=N` com `X-Nexus-Chave` (a mesma chave das Sugestões, `NEXUS_APP_RELATOS_CHAVE`) →
`{"versao": 1, "gerado_em", "cobertura": {"desde", "paginas", "completo", "criacao_mais_antiga_lida"}, "semanas": [{"semana"
(ISO, 2026-W48), "inicio", "fim", "pessoas": [{"nome", "email", "id_personnel", "os_concluidas", "os_pelo_app", "os_fora",
"tarefas", "tarefas_fora", "tipos_fora", "os_fora_lista" (até 40: "os", "descricao")}]}]}`. Concluída = tarefa em status 2 ou
3 no Fracttal com o fim na semana; pelo App = a OS de que o App fechou alguma tarefa, ou a de ronda; fora = o resto (no
computador OU no app do Fracttal: o dado não separa). Semana de segunda a domingo, em Brasília; o App a refaz de madrugada.

TÉCNICO DE CAMPO é quem tem usina hoje nos Técnicos por usina (`atribuicoes.atuais`, papel executa), casado pelo código do
e-mail (`codigo_da_pessoa`, o mesmo do livro): o App manda o e-mail do cadastro de pessoas do Fracttal. Quem vem sem e-mail
só aparece no "Mostrar todos". O Nexus não guarda a medição: lê a rota numa cópia de 10 minutos, na memória (ela muda uma
vez por dia), como as Sugestões e os relatos de segurança.
"""
from __future__ import annotations

import time
import urllib.request

from ..casca import relatos_app as R

VERSAO_DO_CONTRATO = 1
SEMANAS = 8
TTL_S = 600
_CACHE: dict = {}


def limpar() -> None:
    _CACHE.clear()


def url() -> str:
    base = R._url()
    if base.endswith("/relatos"):
        base = base[: -len("/relatos")]
    return f"{base}/fora-do-app?semanas={SEMANAS}"


def _int(v) -> int:
    try:
        return max(0, int(v or 0))
    except (TypeError, ValueError):
        return 0


def _pessoa(p) -> dict | None:
    if not isinstance(p, dict) or not R._txt(p.get("nome")):
        return None
    lista = [{"os": R._txt(o.get("os")), "descricao": R._txt(o.get("descricao"))[:160]}
             for o in (p.get("os_fora_lista") or []) if isinstance(o, dict) and R._txt(o.get("os")).isdigit()]
    tipos = p.get("tipos_fora") if isinstance(p.get("tipos_fora"), dict) else {}
    return {"nome": R._txt(p.get("nome")), "email": R._txt(p.get("email")).lower(),
            "os_concluidas": _int(p.get("os_concluidas")), "os_pelo_app": _int(p.get("os_pelo_app")),
            "os_fora": _int(p.get("os_fora")), "tarefas": _int(p.get("tarefas")), "tarefas_fora": _int(p.get("tarefas_fora")),
            "tipos_fora": {R._txt(k): _int(v) for k, v in tipos.items() if R._txt(k)}, "os_fora_lista": lista[:40]}


def _validar(d) -> tuple[list, dict]:
    if not isinstance(d, dict):
        raise R.FonteErro("a resposta do App não é um objeto")
    if d.get("versao") != VERSAO_DO_CONTRATO:
        raise R.FonteErro(f"o App fala a versão {d.get('versao')!r} do contrato, e o Nexus entende a {VERSAO_DO_CONTRATO}")
    if not isinstance(d.get("semanas"), list):
        raise R.FonteErro("a resposta do App não tem a lista de semanas")
    semanas = []
    for s in d["semanas"]:
        if not isinstance(s, dict) or not R._txt(s.get("semana")):
            continue
        semanas.append({"semana": R._txt(s.get("semana")), "inicio": R._txt(s.get("inicio")), "fim": R._txt(s.get("fim")),
                        "pessoas": [x for x in (_pessoa(p) for p in s.get("pessoas") or []) if x]})
    cob = d.get("cobertura") if isinstance(d.get("cobertura"), dict) else {}
    return semanas, {"completo": cob.get("completo") is True, "desde": R._txt(cob.get("desde")),
                     "mais_antiga": R._txt(cob.get("criacao_mais_antiga_lida")), "gerado_em": R._txt(d.get("gerado_em"))}


def ler(forcar: bool = False) -> dict:
    """{"semanas", "cobertura", "erro", "lido_em", "ligado"}, da cópia de 10 minutos. Sem a chave, nem chama o App. A leitura
    que falha devolve a última boa com o erro."""
    if not R.ligado():
        return {"semanas": [], "cobertura": {}, "erro": "", "lido_em": None, "ligado": False}
    agora = time.time()
    g = _CACHE.get("medicao")
    if g and not forcar and g.get("lido_em") and agora - g["lido_em"] < TTL_S:
        return g
    pedido = urllib.request.Request(url(), headers={"X-Nexus-Chave": R._conf(R.NOME_CHAVE), "Accept": "application/json",
                                                      "User-Agent": "Nexus-GridCo/1 (fora-do-app)"}, method="GET")
    try:
        semanas, cob = _validar(R._chamar(pedido))
    except R.FonteErro as ex:
        base = g or {"semanas": [], "cobertura": {}, "lido_em": None, "ligado": True}
        _CACHE["medicao"] = dict(base, erro=str(ex), lido_em=agora if g else None)
        return _CACHE["medicao"]
    _CACHE["medicao"] = {"semanas": semanas, "cobertura": cob, "erro": "", "lido_em": agora, "ligado": True}
    return _CACHE["medicao"]


def _tecnicos(cfg) -> set[str] | None:
    """Os códigos do e-mail de quem tem usina hoje nos Técnicos por usina (papel executa). None se o livro não se leu (a tela
    diz, e mostra todos)."""
    from . import atribuicoes as AT
    est = AT.ler(cfg)
    if est.get("erro") and not est.get("decisoes"):
        return None
    return {R._txt(x.get("pessoa_hmac")).lower() for x in AT.atuais(est, AT.hoje_id()).values()
            if R._txt(x.get("pessoa_hmac"))}


def _pct(fora: int, total: int) -> int | None:
    return round(100 * fora / total) if total else None


def montar(cfg, args) -> dict:
    """O que a tela mostra: a semana escolhida (`semana`; sem ela, a mais nova) com a anterior ao lado, só os técnicos de campo
    (ou todos, com `todos=1`), os que mais fecham fora primeiro."""
    from ..cadastro.ligacao_campo import codigo_da_pessoa
    d = ler()
    semanas = d["semanas"]
    pedida = R._txt(args.get("semana"))
    i = next((k for k, s in enumerate(semanas) if s["semana"] == pedida), 0)
    semana = semanas[i] if semanas else None
    anterior = semanas[i + 1] if semanas and i + 1 < len(semanas) else None
    todos = R._txt(args.get("todos")) == "1"
    tecnicos = _tecnicos(cfg)
    chave = cfg.get("NEXUS_PESSOA_HMAC")

    def e_tecnico(p) -> bool:
        if tecnicos is None:
            return True
        return bool(p["email"]) and (codigo_da_pessoa(chave, p["email"]) or "").lower() in tecnicos

    antes = {p["email"] or p["nome"]: p for p in (anterior or {}).get("pessoas", [])}
    linhas, fora_da_lista = [], 0
    for p in (semana or {}).get("pessoas", []):
        tec = e_tecnico(p)
        if not tec:
            fora_da_lista += 1
            if not todos:
                continue
        a = antes.get(p["email"] or p["nome"])
        linhas.append(dict(p, tecnico=tec, pct_fora=_pct(p["os_fora"], p["os_concluidas"]),
                           antes={"os_fora": a["os_fora"], "os_concluidas": a["os_concluidas"],
                                  "pct_fora": _pct(a["os_fora"], a["os_concluidas"])} if a else None))
    linhas.sort(key=lambda l: (-l["os_fora"], -(l["pct_fora"] or 0), l["nome"].lower()))
    totais = {"os_fora": sum(l["os_fora"] for l in linhas if l["tecnico"]),
              "os_concluidas": sum(l["os_concluidas"] for l in linhas if l["tecnico"])}
    totais["pct_fora"] = _pct(totais["os_fora"], totais["os_concluidas"])
    return {"ligado": d["ligado"], "erro": d["erro"], "cobertura": d["cobertura"], "semanas": semanas, "semana": semana,
            "anterior": anterior, "linhas": linhas, "todos": todos, "fora_da_lista": fora_da_lista, "totais": totais,
            "sem_tecnicos": tecnicos is None}


def registrar(bp) -> None:
    """A tela `/t/pcm/os-fora-do-app` (`?semana=2026-W48`, `?todos=1`). Quem vê é a marca da tela no portão de setor."""
    from flask import current_app, render_template, request

    @bp.route("/os-fora-do-app", endpoint="os-fora-do-app")
    def tela():
        return render_template("pcm/fora_do_app.html", d=montar(current_app.config, request.args))

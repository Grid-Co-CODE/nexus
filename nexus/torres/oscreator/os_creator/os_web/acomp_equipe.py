# os_creator/os_web/acomp_equipe.py
"""A equipe de chamados escolhida pela tela (16/11/2026, Levi: "passe todas as OSs para a responsável" da equipe; no quiz,
"as 266 abertas e as novas").

A equipe de chamados é a pessoa no nome de quem nascem as administrativas (o relógio do `acomp_cadeia`) e contra quem o
quadro marca "no nome de outra pessoa" (`acomp_web.da_equipe`). Até aqui ela vinha só do .env do servidor
(`OS_WEB_CHAMADO_RESP_ID`/`NOME`), que o Levi não alcança: trocar a pessoa pedia a T.I. Agora o administrador do Nexus
escolhe pela tela do Garantias, e a escolha mora num JSON da pasta de dados (`<dados>/oscreator/garantias/
acomp_equipe.json`), como os administradores do Nexus: é configuração desta instalação, não dado de negócio, e o repositório
é público (nem nome nem id de gente no código). Sem a escolha, vale o .env, como sempre.

Junto, "passar as abertas": o responsável de cada chamado aberto do quadro (Chegaram e Ticket aberto) passa para a pessoa,
uma OS de cada vez, por trás e com pausa (a cota do Fracttal é da empresa). A troca não mexe na nota da OS: conferido na OS
19322 em 16/11/2026 (a nota com as respostas do fabricante, lida antes e depois pelo REST, igual). A finalizada o Fracttal
não deixa mudar, e ela nem entra na conta."""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import threading
import time

log = logging.getLogger(__name__)
ARQUIVO = "acomp_equipe.json"
PAUSA_S = 0.5                    # entre uma troca e a outra (a cota do Fracttal é da empresa; o porteiro do Nexus segura)
_TRAVA = threading.Lock()
_ESTADO: dict = {"pasta": None, "escolha": None, "lido": False,
                 "lote": {"rodando": False, "total": 0, "feitas": 0, "erros": [], "para": "",
                          "inicio": "", "fim": ""}}


def _agora() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).isoformat(timespec="seconds")


def configurar_pasta(pasta) -> None:
    """Onde mora a escolha (a ponte liga, ao lado da cópia do quadro); None = só a memória (os testes)."""
    with _TRAVA:
        _ESTADO.update(pasta=pasta or None, escolha=None, lido=False)


def _arquivo():
    return os.path.join(_ESTADO["pasta"], ARQUIVO) if _ESTADO["pasta"] else None


def atual() -> tuple | None:
    """(id, nome) da equipe escolhida pela tela, ou None (vale o .env)."""
    with _TRAVA:
        if not _ESTADO["lido"]:
            _ESTADO["lido"] = True
            arq = _arquivo()
            if arq and os.path.exists(arq):
                try:
                    with open(arq, encoding="utf-8") as f:
                        _ESTADO["escolha"] = json.load(f) or None
                except Exception:               # noqa: BLE001 — o arquivo que não abre não derruba a tela: vale o .env
                    log.exception("Garantias: a equipe de chamados escolhida não abriu")
        e = _ESTADO["escolha"] or {}
    try:
        rid = int(e.get("id") or 0)
    except (TypeError, ValueError):
        rid = 0
    nome = " ".join(str(e.get("nome") or "").split())
    return (rid, nome) if rid and nome else None


def gravar(id_pessoa, nome: str, quem: str = "") -> dict:
    """Grava a escolha. → o registro gravado. Levanta ValueError sem a pessoa."""
    try:
        rid = int(id_pessoa)
    except (TypeError, ValueError):
        rid = 0
    nome = " ".join(str(nome or "").split())
    if not rid or not nome:
        raise ValueError("Escolha a pessoa da equipe de chamados.")
    reg = {"id": rid, "nome": nome, "quando": _agora(), "quem": " ".join(str(quem or "").split())}
    with _TRAVA:
        _ESTADO.update(escolha=reg, lido=True)
        arq = _arquivo()
    if arq:
        os.makedirs(os.path.dirname(arq), exist_ok=True)
        with open(arq + ".tmp", "w", encoding="utf-8") as f:
            json.dump(reg, f, ensure_ascii=False, indent=1)
        os.replace(arq + ".tmp", arq)
    return reg


def lote() -> dict:
    """Como vai (ou como terminou) a última passagem das abertas."""
    with _TRAVA:
        return json.loads(json.dumps(_ESTADO["lote"]))


def _norm(s) -> str:
    return " ".join(str(s or "").split()).lower()


def a_passar(cartoes, nome: str) -> list:
    """Os cartões abertos do quadro (Chegaram e Ticket aberto) que não estão no nome da pessoa."""
    alvo = _norm(nome)
    return [c for c in cartoes or () if c.get("id") and c.get("col") in ("chegou", "ticket")
            and c.get("status_id") in (1, 2) and _norm(c.get("responsavel")) != alvo]


def comecar(total: int, nome: str) -> bool:
    """Marca o lote como rodando. False se já há um rodando (não começa outro por cima)."""
    with _TRAVA:
        if _ESTADO["lote"]["rodando"]:
            return False
        _ESTADO["lote"] = {"rodando": True, "total": int(total), "feitas": 0, "erros": [], "para": nome,
                           "inicio": _agora(), "fim": ""}
        return True


def passar(cartoes, id_pessoa, mudar, pausa: float = PAUSA_S) -> dict:
    """Troca o responsável de cada cartão (o `comecar` já marcou o lote). `mudar(wid, id)` → {"ok"} ou {"ok": False,
    "erro"}. Uma OS que falha fica nos erros com o motivo e o lote segue. → o lote ao fim."""
    try:
        for i, c in enumerate(cartoes):
            if i:
                time.sleep(pausa)
            try:
                r = mudar(c["id"], id_pessoa)
            except Exception as e:              # noqa: BLE001 — a OS que falha não para as outras
                r = {"ok": False, "erro": "%s: %s" % (type(e).__name__, str(e)[:120])}
            with _TRAVA:
                if isinstance(r, dict) and r.get("ok"):
                    _ESTADO["lote"]["feitas"] += 1
                else:
                    _ESTADO["lote"]["erros"].append({"os": str(c.get("folio") or c["id"]),
                                                     "erro": str((r or {}).get("erro") or "sem resposta")[:160]})
    finally:
        with _TRAVA:
            _ESTADO["lote"].update(rodando=False, fim=_agora())
    return lote()

"""O envio de um e-mail pelo próprio Nexus (25/11/2026), pelo Microsoft Graph com permissão de APLICATIVO (Mail.Send).

Levi: "a informação do app de campo tem que chegar para o Nexus e o Nexus passa essa informação para os e-mails"; "É só a
gente usar a mesma credencial". As credenciais são as do registro do App de Campo no Entra ID (o `_graph_mail` do
function_app.py: client credentials, a caixa `MAIL_FROM`), coladas pelo administrador em Base → Chaves das fontes →
aba Nexus (`nexus/auth/chaves.py`, `NEXUS_EMAIL_*`), ou no `.env`.

Na cópia de prova (`NEXUS_EMAIL_SAIDA_PASTA`), o e-mail vira um arquivo .html nessa pasta e nada sai da máquina; em teste
nada vai à rede (o teste dubla `enviar`). O erro devolvido nunca leva endereço: ele vai para o registro dos envios, que
qualquer sistema lê.
"""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

GRAPH = "https://graph.microsoft.com/v1.0"
NOMES = ("NEXUS_EMAIL_TENANT_ID", "NEXUS_EMAIL_CLIENT_ID", "NEXUS_EMAIL_CLIENT_SECRET", "NEXUS_EMAIL_REMETENTE")
ROTULOS = {"NEXUS_EMAIL_TENANT_ID": "o diretório", "NEXUS_EMAIL_CLIENT_ID": "o ID do aplicativo",
           "NEXUS_EMAIL_CLIENT_SECRET": "o segredo", "NEXUS_EMAIL_REMETENTE": "a caixa que envia"}
_SEM_EMAIL = re.compile(r"[^\s<>()\[\],;:\"']+@[^\s<>()\[\],;:\"']+")
_TOKEN: dict = {"v": None, "ate": 0.0, "de": None}
_TRAVA = threading.Lock()


class EnvioErro(RuntimeError):
    """O Microsoft 365 recusou ou não respondeu; o texto não leva endereço nem segredo."""


def sem_endereco(txt, lim: int = 200) -> str:
    return _SEM_EMAIL.sub("(e-mail)", str(txt or ""))[:lim]


def _chave(cfg, nome: str) -> str:
    from ..auth import chaves
    try:
        return (chaves.valor(nome, cfg) or "").strip()
    except Exception:        # noqa: BLE001 — sem a pasta de dados (teste): só o .env
        return str(cfg.get(nome) or "").strip()


def credenciais(cfg) -> dict:
    return {n: _chave(cfg, n) for n in NOMES}


def faltam(cfg) -> list[str]:
    """O que falta para enviar, em palavras ("o segredo", ...); vazio = pronto. A cópia de prova não precisa de nada."""
    if cfg.get("NEXUS_EMAIL_SAIDA_PASTA"):
        return []
    c = credenciais(cfg)
    return [ROTULOS[n] for n in NOMES if not c[n]]


def envia_nesta_maquina(cfg) -> bool:
    """Uma máquina só envia (o servidor): `NEXUS_EMAIL_ENVIAR` = "1" pela tela de Chaves ou pelo .env."""
    return _chave(cfg, "NEXUS_EMAIL_ENVIAR") == "1"


def pedir_token(tenant: str, cliente: str, segredo: str) -> str:
    """O token de aplicativo (client credentials). Recusa ou rede fora: `EnvioErro` com o motivo do Entra ID."""
    import requests
    try:
        r = requests.post(f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
                          data={"client_id": cliente, "client_secret": segredo, "grant_type": "client_credentials",
                                "scope": "https://graph.microsoft.com/.default"}, timeout=20)
    except Exception as ex:      # noqa: BLE001
        raise EnvioErro(f"sem resposta do Entra ID ({type(ex).__name__})") from None
    try:
        j = r.json()
    except ValueError:
        j = {}
    if r.status_code >= 400 or not j.get("access_token"):
        codigo = str(j.get("error") or r.status_code)
        desc = str(j.get("error_description") or "").split("\r\n")[0].split(" Trace ID")[0]
        raise EnvioErro(sem_endereco(f"{codigo}: {desc}" if desc else codigo, 160))
    return j["access_token"]


def _token(cfg) -> str:
    c = credenciais(cfg)
    de = (c["NEXUS_EMAIL_TENANT_ID"], c["NEXUS_EMAIL_CLIENT_ID"], c["NEXUS_EMAIL_CLIENT_SECRET"])
    with _TRAVA:
        if _TOKEN["v"] and _TOKEN["de"] == de and time.time() < _TOKEN["ate"]:
            return _TOKEN["v"]
        v = pedir_token(*de)
        _TOKEN.update(v=v, ate=time.time() + 50 * 60, de=de)
        return v


def _destinos(xs) -> list[dict]:
    return [{"emailAddress": {"address": e}} for e in xs]


def _arquivo(cfg, para, cc, assunto, html) -> tuple[bool, str, str]:
    """A cópia de prova: o e-mail num arquivo, com quem receberia no alto (é a máquina de quem prova, fora do git)."""
    pasta = Path(cfg["NEXUS_EMAIL_SAIDA_PASTA"])
    pasta.mkdir(parents=True, exist_ok=True)
    nome = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f") + ".html"
    cab = json.dumps({"para": list(para), "cc": list(cc), "assunto": assunto}, ensure_ascii=False)
    (pasta / nome).write_text(f"<!-- {cab} -->\n{html}", encoding="utf-8")
    return True, "arquivo", ""


def enviar(cfg, *, para, assunto: str, html: str, cc=()) -> tuple[bool, str, str]:
    """(ok, via, erro). Manda UM e-mail (todos os `para` juntos, os `cc` em cópia). Nunca levanta: a fila decide."""
    para = [e for e in para if e]
    cc = [e for e in cc if e and e not in para]
    if not para:
        return False, "", "sem destinatário"
    if cfg.get("NEXUS_EMAIL_SAIDA_PASTA"):
        return _arquivo(cfg, para, cc, assunto, html)
    falta = faltam(cfg)
    if falta:
        return False, "", "sem " + ", ".join(falta) + " (Base > Chaves das fontes)"
    import requests
    remetente = credenciais(cfg)["NEXUS_EMAIL_REMETENTE"]
    corpo = {"message": {"subject": assunto, "body": {"contentType": "HTML", "content": html},
                         "toRecipients": _destinos(para), "ccRecipients": _destinos(cc)},
             "saveToSentItems": False}
    for tentativa in (1, 2):
        try:
            tok = _token(cfg)
            r = requests.post(f"{GRAPH}/users/{remetente}/sendMail", json=corpo, timeout=30,
                              headers={"Authorization": "Bearer " + tok})
        except EnvioErro as ex:
            return False, "graph", str(ex)
        except Exception as ex:      # noqa: BLE001 — rede
            return False, "graph", f"sem resposta do Microsoft 365 ({type(ex).__name__})"
        if r.status_code == 202:
            return True, "graph", ""
        if r.status_code == 401 and tentativa == 1:
            _TOKEN.update(v=None)          # o token venceu antes da hora: pede outro uma vez
            continue
        try:
            msg = (r.json().get("error") or {}).get("message") or ""
        except ValueError:
            msg = ""
        return False, "graph", sem_endereco(f"HTTP {r.status_code}: {msg}" if msg else f"HTTP {r.status_code}", 160)
    return False, "graph", "HTTP 401"

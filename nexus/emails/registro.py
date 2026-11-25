"""O registro do que o Nexus mandou (25/11/2026): o livro `nexus_email_envios · fato_envio_email`.

O mesmo desenho do Todos os envios do App de Campo (v380), para a tela de E-mails automáticos ler os dois do mesmo jeito
(`nexus/campo/emails_app.envios`): 1 linha = 1 destinatário de 1 envio, dos últimos `GUARDA_DIAS` dias. O destinatário vai
como o código HMAC do e-mail (o mesmo do App, `ligacao_campo.codigo_da_pessoa`): o livro é de leitura aberta, e e-mail não
entra. O erro vai sem endereço (`envio.sem_endereco`).

Onde mora: um diário no disco da máquina que envia (a pasta de dados, `emails_envios.json`), de onde o laço da fila copia
para o banco quando muda (`publicar_se_mudou`). A tela lê o banco; a cópia de prova lê o arquivo
(`NEXUS_EMAIL_ENVIOS_ARQUIVO`).
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

LIVRO, NOME_LIVRO, ABA = "nexus_email_envios", "Nexus · e-mails enviados pelo Nexus", "fato_envio_email"
CAB = ("ID", "Tipo", "Referência", "Destinatário (HMAC)", "Papel", "Cópia", "Quando", "Via", "Situação", "Tentativas",
       "Erro")
GUARDA_DIAS = 35
ARQUIVO = "emails_envios.json"
_TRAVA = threading.Lock()
_ESTADO = {"publicado": None}
log = logging.getLogger(__name__)


def _caminho(cfg) -> Path | None:
    p = cfg.get("NEXUS_EMAIL_ENVIOS_ARQUIVO")
    if p:
        return Path(p)
    from ..auth import acessos
    pasta = acessos.pasta(cfg)
    return (pasta / ARQUIVO) if pasta else None


def _ler_disco(cfg) -> list[dict]:
    c = _caminho(cfg)
    if not c or not c.exists():
        return []
    try:
        return list(json.loads(c.read_text(encoding="utf-8")).get(ABA) or [])
    except (ValueError, OSError):
        log.exception("E-mails do Nexus: o registro dos envios no disco não abriu")
        return []


def _gravar_disco(cfg, linhas: list[dict]) -> None:
    c = _caminho(cfg)
    if not c:
        return
    c.parent.mkdir(parents=True, exist_ok=True)
    tmp = c.with_suffix(".tmp")
    tmp.write_text(json.dumps({ABA: linhas}, ensure_ascii=False, indent=0), encoding="utf-8")
    tmp.replace(c)


def codigo(cfg, email: str) -> str:
    """O código do destinatário: o do App para o mesmo e-mail. Sem a NEXUS_PESSOA_HMAC, "(sem código)": nunca o e-mail."""
    from ..cadastro.ligacao_campo import codigo_da_pessoa
    return codigo_da_pessoa(cfg.get("NEXUS_PESSOA_HMAC"), email) or "(sem código)"


def anotar(cfg, *, envio_id: str, tipo: str, referencia: str, destinos: list[dict], quando: datetime, via: str,
           situacao: str, tentativas: int, erro: str = "") -> None:
    """Uma linha por destinatário do envio (`destinos`: [{email, papel, copia}]). Sem destino (o desligado de um e-mail
    que não chegou a ter lista), uma linha sem destinatário, para o envio contar."""
    from .envio import sem_endereco
    q = quando.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    novas = []
    for n, d in enumerate(destinos or [{}]):
        novas.append({"ID": f"{envio_id}|{n}", "Tipo": tipo, "Referência": sem_endereco(referencia, 120),
                      "Destinatário (HMAC)": codigo(cfg, d["email"]) if d.get("email") else "",
                      "Papel": sem_endereco(d.get("papel") or "", 40), "Cópia": "cópia" if d.get("copia") else "",
                      "Quando": q, "Via": via, "Situação": situacao, "Tentativas": tentativas,
                      "Erro": sem_endereco(erro, 160)})
    with _TRAVA:
        desde = (datetime.now(timezone.utc) - timedelta(days=GUARDA_DIAS)).strftime("%Y-%m-%dT%H:%M:%SZ")
        linhas = [x for x in _ler_disco(cfg) if str(x.get("Quando") or "") >= desde]
        _gravar_disco(cfg, linhas + novas)


def linhas(cfg) -> list[dict]:
    with _TRAVA:
        return _ler_disco(cfg)


def publicar_se_mudou(cfg) -> bool:
    """Copia o diário para o banco quando ele mudou desde a última cópia (o livro inteiro: a API troca o livro). Na cópia
    de prova e em teste, nada vai ao banco. True = publicou."""
    if cfg.get("TESTING") or cfg.get("NEXUS_EMAIL_ENVIOS_ARQUIVO"):
        return False
    ls = linhas(cfg)
    assinatura = json.dumps(ls, sort_keys=True, ensure_ascii=False)
    if not ls or assinatura == _ESTADO["publicado"]:
        return False
    token = cfg.get("GRIDCO_SQL_TOKEN")
    if not token:
        return False
    from ..dados import livros
    from ..dados.conexao import banco_de
    base, sessao = banco_de(cfg)
    corpo = [[x.get(c) if x.get(c) not in ("",) else None for c in CAB] for x in ls]
    livros.publicar(LIVRO, NOME_LIVRO, {ABA: (list(CAB), corpo)}, base=base, token=token, sessao=sessao)
    _ESTADO["publicado"] = assinatura
    return True

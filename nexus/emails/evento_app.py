"""O App de Campo entrega o evento, o Nexus manda o e-mail (25/11/2026, a fase 3 dos e-mails do Nexus).

Levi: "a informação do app de campo tem que chegar para o Nexus e o Nexus passa essa informação para os e-mails". O App
continua sabendo QUANDO um e-mail nasce (o técnico respondeu Não nas luvas, a PT nasceu, o relato chegou) e monta o texto
dele; quem recebe passa a ser decidido aqui, pelo papel no Registro mestre (`papeis.py`), com a regra da tela e o registro
do Nexus. O caso que pediu: o aviso das luvas, que no App ia só para a TST por uma lista fixa, tem de ir também ao
responsável da usina (Levi, 24/11/2026).

O contrato (v1), para a sessão do App:
- `POST /t/base/emails-automaticos/api/evento`, corpo JSON, com `X-Nexus-Ts` (epoch) e `X-Nexus-Assinatura` = HMAC-SHA256
  de "<ts>." + o corpo cru, na chave HMAC-SHA256(NEXUS_PESSOA_HMAC, "nexus:email:evento") (o mesmo desenho da marca do
  técnico, `pcm/motivos_app.py`, com outro rótulo). A hora vale 15 min para cada lado.
- O corpo: {"tipo": um de `TIPOS_DO_APP` (o tipo do App), "id": único no App (o mesmo id não entra duas vezes),
  "usina_id" (o do cadastro, se o App sabe) ou "local" (o nome do local no Fracttal), "referencia" (sem nome nem e-mail),
  "assunto", "html", "sugeridos": [e-mails que o App mandaria hoje] (opcional: o destino de reserva quando o papel não
  acha ninguém na usina)}.
- A resposta: 202 {"ok": true, "aceito": true, "tipo": "nx_app_...", "para": n} = o Nexus manda (ou registra desligado),
  e o App NÃO manda. Qualquer outra (4xx, 5xx, sem resposta em 20 s) = o App manda como hoje: é a reserva, para um
  reinício do Nexus nunca segurar um aviso de segurança.
- Só a máquina que envia aceita (`envio.envia_nesta_maquina`): nas outras, 503.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from datetime import datetime, timezone

from . import envio, fila, papeis
from .tipos import Tipo, mensagem

ROTULO_CHAVE = b"nexus:email:evento"
JANELA_S = 15 * 60
CORPO_MAX = 600_000          # o HTML do aviso da PT, com o checklist, passa de 40 KB; a foto não vem no corpo
_ID = re.compile(r"^[A-Za-z0-9._:|-]{4,120}$")

# o tipo do App → (o tipo do Nexus, o nome, quando sai, os papéis de quem recebe, crítico, o que se perde ao desligar)
TIPOS_DO_APP = {
    "luvas_tst": ("nx_app_luvas", "Luvas isolantes com Não na ronda (pelo Nexus)",
                  "uns 5 min depois que o técnico responde Não, no App", ("tst", "responsavel_ufv"), True,
                  "A TST e o responsável da usina deixam de saber, por e-mail, de luvas isolantes em falta na ronda."),
    "seguranca_relato": ("nx_app_relato", "Relato de acidente ou incêndio (pelo Nexus)", "na hora do relato, no App",
                         ("tst", "responsavel_ufv"), True,
                         "A TST e o responsável da usina deixam de saber, na hora, de um acidente ou incêndio relatado "
                         "no App."),
    "pt_aviso": ("nx_app_pt", "PT aguardando assinatura (pelo Nexus)",
                 "quando a PT nasce, e o lembrete aos 30 min, no App", ("responsavel_ufv",), True,
                 "O responsável da usina deixa de saber que uma PT espera a assinatura dele: o técnico fica parado."),
    "encaminhamento": ("nx_app_encaminhamento", "Encaminhamento de demanda (pelo Nexus)", "quando alguém encaminha, no App",
                       (), False, ""),
}


def tipos() -> dict:
    """Os tipos do Nexus que nascem dos eventos do App (entram no registro dos tipos como embutidos)."""
    nomes = papeis.nomes()
    out = {}
    for _app, (tid, nome, quando, ps, crit, perde) in TIPOS_DO_APP.items():
        destino = " · ".join(nomes[p] for p in ps) or "quem o App indicar"
        out[tid] = Tipo(tid, nome, quando, destino, critico=crit, quem_deixa=perde, extra={"papeis": ps})
    return out


def chave(cfg) -> bytes | None:
    base = str(cfg.get("NEXUS_PESSOA_HMAC") or "").strip()
    return hmac.new(base.encode(), ROTULO_CHAVE, hashlib.sha256).digest() if base else None


def assinatura(k: bytes, ts, corpo: bytes) -> str:
    return hmac.new(k, f"{int(ts)}.".encode() + corpo, hashlib.sha256).hexdigest()


def conferir(cfg, ts, assinatura_recebida, corpo: bytes, agora=None) -> tuple[int, dict | str]:
    """(200, o evento conferido) ou (status, o porquê). Nada é gravado aqui."""
    k = chave(cfg)
    if not k:
        return 503, "e-mail pelo Nexus desligado (sem NEXUS_PESSOA_HMAC)"
    if not corpo or len(corpo) > CORPO_MAX:
        return 400, "corpo vazio ou grande demais"
    try:
        ts = int(ts)
    except (TypeError, ValueError):
        return 400, "hora do envio (X-Nexus-Ts) fora do formato"
    if abs((agora or time.time()) - ts) > JANELA_S:
        return 401, "hora do envio fora da janela de 15 min"
    if not hmac.compare_digest(assinatura(k, ts, corpo), str(assinatura_recebida or "")):
        return 401, "assinatura não confere"
    try:
        d = json.loads(corpo.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return 400, "o corpo não é JSON"
    if not isinstance(d, dict) or d.get("tipo") not in TIPOS_DO_APP:
        return 400, "tipo que o Nexus não recebe do App"
    eid = str(d.get("id") or "").strip()
    if not _ID.fullmatch(eid):
        return 400, "id do evento fora do formato"
    assunto, html = " ".join(str(d.get("assunto") or "").split())[:200], str(d.get("html") or "")
    if not assunto or not html:
        return 400, "faltam o assunto e o html"
    sug = [str(x).strip().lower() for x in d.get("sugeridos") or [] if "@" in str(x)][:30]
    uid = d.get("usina_id")
    return 200, {"tipo_app": d["tipo"], "id": eid, "usina_id": int(uid) if str(uid or "").isdigit() else None,
                 "local": str(d.get("local") or "").strip()[:200], "referencia": envio.sem_endereco(d.get("referencia"), 120),
                 "assunto": assunto, "html": html, "sugeridos": sug}


def usina_do_local(local: str):
    """O usina_id do cadastro pelo nome do local no Fracttal (o de-para da APR e PT, o mesmo dos Incidentes)."""
    if not local:
        return None
    from ..campo import regras_app, visao
    por_nome = (visao.usinas_do_fracttal().dados or {}).get("por_nome") or {}
    return (por_nome.get(regras_app._norm(local)) or {}).get("usina_id")


def receber(cfg, ev: dict, agora: datetime | None = None) -> tuple[int, dict]:
    """Põe o e-mail do evento na fila do Nexus. 202 = o Nexus cuida (o App não manda); outro = o App manda."""
    agora = agora or datetime.now(timezone.utc)
    if not envio.envia_nesta_maquina(cfg):
        return 503, {"ok": False, "erro": "esta máquina do Nexus não envia: mande pelo App"}
    if envio.faltam(cfg):
        return 503, {"ok": False, "erro": "o Nexus ainda não tem a credencial de envio: mande pelo App"}
    tid, _n, _q, ps, _c, _p = TIPOS_DO_APP[ev["tipo_app"]]
    uid = ev["usina_id"] or usina_do_local(ev["local"])
    ctx = papeis.contexto(cfg)
    para = papeis.resolver(ctx, list(ps), uid)
    if not para and ev["sugeridos"]:
        para = [{"email": e, "papel": "indicado pelo App"} for e in ev["sugeridos"]]
    if not para:
        return 409, {"ok": False, "erro": "ninguém com e-mail para este evento no Registro mestre: mande pelo App"}
    novo = fila.enfileirar(cfg, mensagem(tipo=tid, referencia=ev["referencia"] or ev["tipo_app"],
                                         chave=f"app|{ev['tipo_app']}|{ev['id']}", para=para, assunto=ev["assunto"],
                                         html=ev["html"]), agora)
    return 202, {"ok": True, "aceito": True, "tipo": tid, "para": len(para), "repetido": not novo}

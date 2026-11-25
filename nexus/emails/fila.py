"""A fila dos e-mails do Nexus (25/11/2026): o que entra, a regra da tela aplicada, o envio, a nova tentativa e o registro.

Mora no disco da máquina que envia (a pasta de dados, `emails_fila.json`): sobrevive a um reinício, e o laço continua de
onde parou. Uma máquina só envia (`envio.envia_nesta_maquina`, a chave `NEXUS_EMAIL_ENVIAR`); nas outras, o laço só dorme
e a tela diz que esta máquina não envia.

O caminho de um e-mail:
1. `enfileirar` (um tipo agendado, o botão de teste, um evento do App): a `chave` da mensagem não entra duas vezes.
2. `processar`: a regra do tipo (Base › E-mails automáticos, `emails_controle.NEXUS`) decide, como o App faz com as dele:
   desligado não manda e registra "desligado"; teste com lista manda só à lista, sem cópia, com "[Teste]" no assunto;
   normal com lista soma ao destino padrão ou o substitui. Sem regra, o destino padrão da mensagem.
3. O envio que falha tenta de novo em 1, 5, 15, 30 e 60 min e depois de hora em hora; passadas `VENCE_H` horas, desiste e
   registra "falhou" (um aviso de ontem chegando como novo confunde mais do que ajuda).
4. Cada desfecho vai ao registro (`registro.anotar`), um por destinatário, sem e-mail.
"""
from __future__ import annotations

import json
import logging
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import envio, registro

ARQUIVO = "emails_fila.json"
RECUO_MIN = (1, 5, 15, 30, 60)
VENCE_H = 24
GUARDA_CHAVES_DIAS = 35
A_CADA_S = 20
PUBLICAR_A_CADA_S = 300
_TRAVA = threading.Lock()
log = logging.getLogger(__name__)


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _de_iso(s) -> datetime | None:
    try:
        return datetime.strptime(str(s), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _caminho(cfg) -> Path | None:
    p = cfg.get("NEXUS_EMAIL_ENVIOS_ARQUIVO")
    if p:                      # a cópia de prova: ao lado do registro de prova, nunca na pasta de dados de verdade
        return Path(p).with_name(ARQUIVO)
    from ..auth import acessos
    pasta = acessos.pasta(cfg)
    return (pasta / ARQUIVO) if pasta else None


def _ler(cfg) -> dict:
    c = _caminho(cfg)
    if not c or not c.exists():
        return {"itens": [], "chaves": {}}
    try:
        d = json.loads(c.read_text(encoding="utf-8"))
        return {"itens": list(d.get("itens") or []), "chaves": dict(d.get("chaves") or {})}
    except (ValueError, OSError):
        log.exception("E-mails do Nexus: a fila no disco não abriu")
        return {"itens": [], "chaves": {}}


def _gravar(cfg, d: dict) -> None:
    c = _caminho(cfg)
    if not c:
        raise RuntimeError("sem a pasta de dados: a fila não tem onde morar")
    c.parent.mkdir(parents=True, exist_ok=True)
    tmp = c.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    tmp.replace(c)


def enfileirar(cfg, msg: dict, agora: datetime | None = None) -> bool:
    """Põe a mensagem na fila. False = a mesma `chave` já entrou (não entra de novo)."""
    agora = agora or datetime.now(timezone.utc)
    with _TRAVA:
        d = _ler(cfg)
        if msg["chave"] in d["chaves"]:
            return False
        limite = _iso(agora - timedelta(days=GUARDA_CHAVES_DIAS))
        d["chaves"] = {k: v for k, v in d["chaves"].items() if v >= limite}
        d["chaves"][msg["chave"]] = _iso(agora)
        d["itens"].append(dict(msg, id=f"{_iso(agora)}|{secrets.token_hex(4)}", criado_em=_iso(agora),
                               proxima_em=_iso(agora), tentativas=0, erro=""))
        _gravar(cfg, d)
        return True


def pendentes(cfg) -> list[dict]:
    with _TRAVA:
        return list(_ler(cfg)["itens"])


def _regra(cfg, tipo: str) -> dict | None:
    from ..campo import emails_controle as EC
    est = EC.ler(cfg, alvo=EC.NEXUS)
    if est["erro"] and not est["linhas"]:
        raise RuntimeError(f"a regra não foi lida ({est['erro']})")
    return EC.vigentes(est["linhas"], cfg.get("NEXUS_PESSOA_HMAC"), EC.NEXUS).get(tipo)


def aplicar(regra: dict | None, msg: dict) -> dict:
    """{"situacao": None | "desligado", "para", "cc", "assunto", "teste"} da regra sobre a mensagem (a régua do App)."""
    para, cc, assunto = list(msg["para"]), list(msg["cc"]), msg["assunto"]
    if regra is None:
        return {"situacao": None, "para": para, "cc": cc, "assunto": assunto, "teste": False}
    if not regra["ligado"]:
        return {"situacao": "desligado", "para": para, "cc": cc, "assunto": assunto, "teste": False}
    lista = [{"email": e, "papel": "lista da regra"} for e in regra["destinatarios"]]
    if regra["modo"] == "teste" and lista:
        return {"situacao": None, "para": lista, "cc": [], "assunto": "[Teste] " + assunto, "teste": True}
    if lista and regra["substitui"]:
        return {"situacao": None, "para": lista, "cc": [], "assunto": assunto, "teste": False}
    ja = {d["email"] for d in para + cc}
    return {"situacao": None, "para": para + [x for x in lista if x["email"] not in ja], "cc": cc,
            "assunto": assunto, "teste": False}


def _destinos(r: dict) -> list[dict]:
    return [dict(x, copia=False) for x in r["para"]] + [dict(x, copia=True) for x in r["cc"]]


def processar(cfg, agora: datetime | None = None, enviar=None) -> dict:
    """Uma passada: manda o que chegou a hora. {enviados, falhas, desligados, pendentes}. `enviar` é o do teste."""
    agora = agora or datetime.now(timezone.utc)
    enviar = enviar or envio.enviar
    res = {"enviados": 0, "falhas": 0, "desligados": 0, "pendentes": 0}
    for item in pendentes(cfg):
        if (_de_iso(item["proxima_em"]) or agora) > agora:
            res["pendentes"] += 1
            continue
        try:
            r = aplicar(_regra(cfg, item["tipo"]), item)
        except Exception as ex:      # noqa: BLE001 — sem ler a regra não se manda: o desligado podia ser ignorado
            log.warning("E-mails do Nexus: %s espera a regra (%s)", item["tipo"], ex)
            if agora - (_de_iso(item["criado_em"]) or agora) >= timedelta(hours=VENCE_H):
                registro.anotar(cfg, envio_id=item["id"], tipo=item["tipo"], referencia=item["referencia"],
                                destinos=_destinos({"para": item["para"], "cc": item["cc"]}), quando=agora, via="",
                                situacao="falhou", tentativas=int(item.get("tentativas") or 0),
                                erro="a regra do e-mail não foi lida em 24 h")
                _tirar(cfg, item["id"])
                res["falhas"] += 1
                continue
            res["pendentes"] += 1
            continue
        tent = int(item.get("tentativas") or 0) + 1
        if r["situacao"] == "desligado":
            fim = ("desligado", "", "")
        else:
            ok, via, erro = enviar(cfg, para=[x["email"] for x in r["para"]], cc=[x["email"] for x in r["cc"]],
                                   assunto=r["assunto"], html=item["html"])
            if ok:
                fim = ("teste" if r["teste"] else "enviado", via, "")
            elif agora - (_de_iso(item["criado_em"]) or agora) >= timedelta(hours=VENCE_H):
                fim = ("falhou", via, erro)
            else:
                recuo = RECUO_MIN[min(tent - 1, len(RECUO_MIN) - 1)]
                _atualizar(cfg, item["id"], tentativas=tent, erro=envio.sem_endereco(erro, 160),
                           proxima_em=_iso(agora + timedelta(minutes=recuo)))
                res["falhas"] += 1
                res["pendentes"] += 1
                continue
        situacao, via, erro = fim
        registro.anotar(cfg, envio_id=item["id"], tipo=item["tipo"], referencia=item["referencia"],
                        destinos=_destinos(r), quando=agora, via=via or "", situacao=situacao, tentativas=tent,
                        erro=erro)
        _tirar(cfg, item["id"])
        res["desligados" if situacao == "desligado" else ("falhas" if situacao == "falhou" else "enviados")] += 1
    return res


def _atualizar(cfg, item_id: str, **campos) -> None:
    with _TRAVA:
        d = _ler(cfg)
        for x in d["itens"]:
            if x["id"] == item_id:
                x.update(campos)
        _gravar(cfg, d)


def _tirar(cfg, item_id: str) -> None:
    with _TRAVA:
        d = _ler(cfg)
        d["itens"] = [x for x in d["itens"] if x["id"] != item_id]
        _gravar(cfg, d)


# ── o laço ──────────────────────────────────────────────────────────────────────────────────────────────────────────
ULTIMA: dict = {}


def _rodada(app, ultimo_publicar: list) -> None:
    cfg = app.config
    if not envio.envia_nesta_maquina(cfg):
        ULTIMA.update(quando=_iso(datetime.now(timezone.utc)), ligado=False)
        return
    with app.app_context():
        from . import agenda
        agenda.rodar(cfg)
        res = processar(cfg)
        if time.time() - ultimo_publicar[0] >= PUBLICAR_A_CADA_S:
            ultimo_publicar[0] = time.time()
            registro.publicar_se_mudou(cfg)
    ULTIMA.clear()
    ULTIMA.update(res, quando=_iso(datetime.now(timezone.utc)), ligado=True)


def _laco(app) -> None:
    ultimo_publicar = [0.0]
    while True:
        try:
            _rodada(app, ultimo_publicar)
        except Exception as ex:      # noqa: BLE001 — o banco fora, por exemplo: a próxima rodada tenta de novo
            log.warning("E-mails do Nexus: a rodada não rodou (%s)", type(ex).__name__)
            ULTIMA.update(erro=type(ex).__name__)
        time.sleep(A_CADA_S)


def ligar(app) -> None:
    """Liga o laço em toda máquina servida (o `servir.py`), nunca em teste: cada rodada confere se ESTA máquina envia,
    para a tela de Chaves valer sem reiniciar."""
    if app.config.get("TESTING"):
        return
    threading.Thread(target=_laco, args=(app,), daemon=True, name="nexus-emails-fila").start()

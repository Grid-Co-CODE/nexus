"""O Insights de madrugada, em lote (19/11/2026).

Levi, 19/11/2026: "Insights de madrugada: gerar de noite, fora do período solar, para todas as usinas. Se o dossiê de uma
usina estiver idêntico ao do dia anterior, reaproveite o insight em vez de chamar o Haiku". Com a conta medida no dia
(só 12 de 144 dossiês ficaram idênticos de um dia para o outro: 132 chamadas por noite, US$ 12 a 16 por mês chamando direto
ou a metade pela API em lote), a decisão: "Madrugada em lote, com teto de US$ 12. O lote só garante a resposta em até 24 h,
então comece logo depois da meia-noite e, se às 6h ainda faltar alguma usina, gere essas direto. Registre quantas caíram
nessa rede de segurança".

Como a noite anda (`passo`, chamado pelo laço a cada 5 minutos; o estado fica em `<dados>/ia/noite/AAAA-MM-DD.json`, e o
servidor que reinicia no meio retoma dele):

1. 00:10 (`preparar`): monta o dossiê de cada usina mobilizada. A que já tem o insight de hoje fica como está. A que tem
   o dossiê IDÊNTICO ao do insight de ontem (a mesma `assinatura`: o texto sem a linha "Gerado em") ganha o de ontem,
   com `reaproveitado_de` (a tela diz "sem mudança no dossiê desde dd/mm"). As outras vão num lote da Anthropic (Message
   Batches, 50% do preço), com o MESMO pedido da chamada direta em Busca (`ia.pedido_do_lote`).
2. Até as 6h (`colher`): quando o lote acaba, cada resposta passa pela leitura e pela conferência de sempre
   (`diagnostico.ler`, `tirar_sem_dado`, `conferir`). O que não confere é guardado com o "A conferir" e entra num 2º lote,
   pensando (o mesmo "refaz uma vez pensando" da chamada direta, pela metade do preço).
3. 06:00 (`rede`): o lote que ainda roda é cancelado, e toda usina sem o insight de hoje é gerada direto
   (`diagnostico.gerar`). Quantas caíram aqui fica nas contas da noite (`contas["rede"]`), no log e no painel de uso.
   A noite que não rodou (servidor fora do ar) ainda tem esta rede, até as 7h; depois disso o dia segue sob demanda.

O lote só existe com o Haiku da Anthropic com chave (`fase = "sem_ia"` sem ele) e abaixo do teto do mês
(`fase = "teto"`). O dossiê de cada usina do lote fica guardado em `<dados>/ia/noite/<dia>/<usina>.md` até a conferência.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from . import diagnostico as DG
from . import ia as IA

log = logging.getLogger(__name__)

INICIO = (0, 10)             # logo depois da meia-noite: o dia do diagnóstico já virou
ULTIMO_ENVIO = (5, 30)       # depois disto não vale mandar lote: às 6h vem a rede
REDE_H = 6                   # 06:00: o que faltar é gerado direto
FIM_H = 7                    # a noite que não rodou só tem a rede até aqui; depois, o dia segue sob demanda
LACO_S = 300
PERGUNTA = "[diagnóstico do dia]"
QUEM = "diagnostico-da-noite"

assinatura = DG.assinatura


# ── o estado da noite ────────────────────────────────────────────────────────────────────────────────────────────────
def _pasta(cfg) -> Path | None:
    p = IA._pasta(cfg)
    return p / "noite" if p else None


def estado(cfg, dia: str) -> dict | None:
    p = _pasta(cfg)
    arq = p / f"{dia}.json" if p else None
    if not arq or not arq.exists():
        return None
    try:
        return json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _gravar(cfg, e: dict) -> dict:
    p = _pasta(cfg)
    if p:
        p.mkdir(parents=True, exist_ok=True)
        tmp = p / f"{e['dia']}.tmp"
        tmp.write_text(json.dumps(e, ensure_ascii=False), encoding="utf-8")
        tmp.replace(p / f"{e['dia']}.json")
    return e


def _dossie_guardado(cfg, dia: str, uid) -> Path | None:
    p = _pasta(cfg)
    return p / dia / f"{int(uid)}.md" if p else None


def _modelo(cfg):
    """O Haiku (ou outro da Anthropic) do diagnóstico, com chave; None quando o diagnóstico roda numa IA sem lote."""
    m = {x.id: x for x in IA.modelos(cfg)}.get(DG.modelo(cfg))
    return m if m is not None and m.provedor == "anthropic" and IA.chave(cfg, "anthropic") else None


def _pedido(cfg, m, dossie: str, setores, pensar: bool) -> dict:
    return IA.pedido_do_lote(m, dossie, DG.PEDIDO + DG.lista_de_temas(setores), [s["nome"] for s in setores or []], pensar)


def _tem_o_de_hoje(cfg, uid, dia: str) -> bool:
    g = DG.guardado(cfg, uid, dia)
    return bool(g and g.get("ok"))


# ── 1. preparar: reaproveitar o idêntico e mandar o resto em lote ───────────────────────────────────────────────────
def preparar(cfg, dia: str, usinas: list[int], dossie_de, setores, cliente) -> dict:
    """O estado da noite depois do envio. `dossie_de(usina_id)` devolve (o texto do dossiê, os tokens estimados) ou None
    (a usina sem dossiê); `cliente` é o da Anthropic (`ia.cliente_anthropic`)."""
    e = {"dia": dia, "criado_em": datetime.now(IA._BRT).isoformat(timespec="seconds"), "fase": "colhido", "lote_a": None,
         "lote_b": None, "usinas": {}, "refeitos": []}
    m = _modelo(cfg)
    if m is None:
        return _gravar(cfg, dict(e, fase="sem_ia"))
    if IA.gasto_do_mes(cfg) >= IA.teto(cfg):
        log.warning("Insights de madrugada: o teto do mês da IA foi atingido; a noite de %s não manda lote", dia)
        return _gravar(cfg, dict(e, fase="teto"))
    ontem = f"{datetime.fromisoformat(dia) - timedelta(days=1):%Y-%m-%d}"
    pedidos = []
    for uid in usinas:
        if _tem_o_de_hoje(cfg, uid, dia):
            e["usinas"][str(uid)] = "ja_tinha"
            continue
        try:
            dz = dossie_de(uid)
        except Exception:            # noqa: BLE001 — o dossiê de uma usina que não monta não derruba a noite das outras
            log.exception("Insights de madrugada: o dossiê da usina %s não montou", uid)
            dz = None
        if not dz:
            e["usinas"][str(uid)] = "sem_dossie"
            continue
        texto, _tokens = dz
        sha, ant = assinatura(texto), DG.guardado(cfg, uid, ontem)
        if ant and ant.get("ok") and ant.get("dossie_sha") == sha and (ant.get("diag") or ant.get("texto")):
            # o dossiê não mudou: o insight de ontem vale para hoje, e guarda o dia em que foi FEITO
            DG.gravar(cfg, dict(ant, dia=dia, ts=time.time(), reaproveitado_de=ant.get("reaproveitado_de") or ant.get("dia") or ontem))
            e["usinas"][str(uid)] = "reaproveitado"
            continue
        arq = _dossie_guardado(cfg, dia, uid)
        if arq:
            arq.parent.mkdir(parents=True, exist_ok=True)
            arq.write_text(texto, encoding="utf-8")
        pedidos.append({"custom_id": f"u{int(uid)}", "params": _pedido(cfg, m, texto, setores, pensar=False)})
        e["usinas"][str(uid)] = "lote_a"
    if pedidos:
        lote = cliente.messages.batches.create(requests=pedidos)
        e.update(fase="lote_a", lote_a=lote.id)
        log.info("Insights de madrugada: lote %s com %s usinas (%s reaproveitadas)", lote.id, len(pedidos),
                 sum(1 for v in e["usinas"].values() if v == "reaproveitado"))
    return _gravar(cfg, e)


# ── 2. colher o lote ─────────────────────────────────────────────────────────────────────────────────────────────────
def colher(cfg, dia: str, setores, cliente) -> dict:
    """Olha o lote da fase. Sem ter acabado, devolve o estado como está. Acabou: cada resposta vira o insight do dia
    (com a conferência); o que não confere no 1º lote entra no 2º, pensando."""
    e = estado(cfg, dia)
    if not e or e.get("fase") not in ("lote_a", "lote_b"):
        return e or {}
    fase = e["fase"]
    lid = e[fase]
    if cliente.messages.batches.retrieve(lid).processing_status != "ended":
        return e
    m, pensar, refazer = _modelo(cfg), fase == "lote_b", []
    for res in cliente.messages.batches.results(lid):
        uid = str(res.custom_id)[1:]
        if e["usinas"].get(uid) != fase:
            continue
        arq = _dossie_guardado(cfg, dia, uid)
        dossie = arq.read_text(encoding="utf-8") if arq and arq.exists() else ""
        if getattr(res.result, "type", "") != "succeeded" or m is None or not dossie:
            # o 2º lote que falha deixa valendo o 1º (já guardado, com o "A conferir"); o 1º que falha fica para a rede
            e["usinas"][uid] = "pronto" if pensar else "falhou"
            continue
        r = IA.resposta_do_lote(cfg, m, res.result.message, _pedido(cfg, m, dossie, setores, pensar), dossie,
                                [s["nome"] for s in setores or []])
        IA.registrar(cfg, int(uid), PERGUNTA, [r], QUEM, round(len(dossie) / 4))
        diag = DG.ler(r.get("texto") or "", dossie, setores) if r.get("ok") else None
        DG.tirar_sem_dado(diag, dossie)
        if not r.get("ok") or not (diag or r.get("texto")):
            e["usinas"][uid] = "pronto" if pensar else "falhou"
            continue
        if _tem_o_de_hoje(cfg, uid, dia) and not pensar:
            e["usinas"][uid] = "ja_tinha"          # alguém abriu a usina enquanto o lote rodava: vale o que já está lá
            continue
        falhas = DG.conferir(diag, dossie, dia)
        DG.gravar(cfg, dict(DG.registro(uid, dia, r, diag, falhas, refeito=pensar, dossie=dossie), lote=True))
        if falhas and not pensar:
            refazer.append(uid)
            e["usinas"][uid] = "lote_b"
        else:
            e["usinas"][uid] = "pronto"
            if pensar:
                e["refeitos"] = sorted(set(e.get("refeitos") or []) | {uid})
    for uid, v in e["usinas"].items():
        if v == fase:                              # o lote acabou e esta usina não veio nele
            e["usinas"][uid] = "pronto" if pensar else "falhou"
    e["fase"] = "colhido"
    if refazer and m is not None:
        pedidos = [{"custom_id": f"u{uid}", "params": _pedido(cfg, m, _dossie_guardado(cfg, dia, uid).read_text(encoding="utf-8"),
                                                               setores, pensar=True)} for uid in refazer]
        lote = cliente.messages.batches.create(requests=pedidos)
        e.update(fase="lote_b", lote_b=lote.id)
        log.info("Insights de madrugada: %s usinas não conferiram e foram ao 2º lote (%s), pensando", len(pedidos), lote.id)
    return _gravar(cfg, e)


# ── 3. a rede de segurança das 6h ────────────────────────────────────────────────────────────────────────────────────
def rede(cfg, dia: str, usinas: list[int], dossie_de, setores, cliente) -> dict:
    """Fecha a noite: cancela o lote que ainda roda e gera DIRETO o insight de toda usina que ainda não tem o de hoje.
    As contas da noite (`contas`) dizem quantas caíram aqui."""
    e = estado(cfg, dia) or {"dia": dia, "criado_em": datetime.now(IA._BRT).isoformat(timespec="seconds"), "fase": "sem_lote",
                             "lote_a": None, "lote_b": None, "usinas": {}, "refeitos": []}
    if e.get("fase") in ("lote_a", "lote_b"):
        try:
            cliente.messages.batches.cancel(e[e["fase"]])
        except Exception:            # noqa: BLE001 — o cancelamento que falha não impede a rede
            log.exception("Insights de madrugada: não cancelei o lote %s", e[e["fase"]])
    na_rede, sem = 0, 0
    for uid in usinas:
        if _tem_o_de_hoje(cfg, uid, dia):
            continue
        try:
            dz = dossie_de(uid)
        except Exception:            # noqa: BLE001
            log.exception("Insights de madrugada (rede): o dossiê da usina %s não montou", uid)
            dz = None
        if not dz:
            e["usinas"][str(uid)] = "sem_dossie"
            sem += 1
            continue
        na_rede += 1
        e["usinas"][str(uid)] = "rede"
        d = DG.gerar(cfg, uid, dz[0], dz[1], dia, setores)
        if not (d or {}).get("ok"):
            sem += 1
    vals = list(e["usinas"].values())
    e["contas"] = {"usinas": len(usinas), "reaproveitados": vals.count("reaproveitado"), "ja_tinham": vals.count("ja_tinha"),
                   "pelo_lote": vals.count("pronto"), "refeitos": len(e.get("refeitos") or []), "rede": na_rede,
                   "sem_insight": sem}
    e["fase"] = "fim"
    e["fechado_em"] = datetime.now(IA._BRT).isoformat(timespec="seconds")
    log.info("Insights de madrugada de %s: %s", dia, e["contas"])
    _limpar_dossies(cfg, dia)
    return _gravar(cfg, e)


def _limpar_dossies(cfg, dia: str) -> None:
    """Os dossiês da noite serviram à conferência: saem do disco (o do dia, monta-se de novo na tela)."""
    p = _pasta(cfg)
    pasta = p / dia if p else None
    if pasta and pasta.exists():
        for arq in pasta.glob("*.md"):
            try:
                arq.unlink()
            except OSError:
                pass
        try:
            pasta.rmdir()
        except OSError:
            pass


# ── o relógio ────────────────────────────────────────────────────────────────────────────────────────────────────────
def passo(cfg, agora: datetime, usinas_de, dossie_de, setores_de, cliente_de) -> str:
    """Um passo da noite, pelo relógio e pelo estado guardado. Devolve o que fez (para o log e para os testes).
    `usinas_de()`, `setores_de()` e `cliente_de()` só são chamados quando o passo precisa deles."""
    dia, hm = DG.hoje(agora), (agora.hour, agora.minute)
    e = estado(cfg, dia)
    if e is None:
        if INICIO <= hm < ULTIMO_ENVIO:
            preparar(cfg, dia, usinas_de(), dossie_de, setores_de(), cliente_de())
            return "preparou"
        if REDE_H <= agora.hour < FIM_H:
            rede(cfg, dia, usinas_de(), dossie_de, setores_de(), cliente_de())
            return "rede de segurança"
        return "fora da janela"
    if e.get("fase") in ("fim", "sem_ia", "teto"):
        return "noite fechada"
    if agora.hour >= REDE_H:
        rede(cfg, dia, usinas_de(), dossie_de, setores_de(), cliente_de())
        return "rede de segurança"
    if e.get("fase") in ("lote_a", "lote_b"):
        depois = colher(cfg, dia, setores_de(), cliente_de())
        # o lote que não acabou devolve o estado como estava
        return "esperando o lote" if depois.get("fase") == e["fase"] and depois.get("usinas") == e.get("usinas") else "colheu"
    return "esperando as 6h"


def resumo(cfg, noites: int = 7) -> list[dict]:
    """As últimas noites, a mais nova primeiro, para o painel de uso: {dia, fase, e as contas de quem fechou}."""
    p = _pasta(cfg)
    if not p or not p.exists():
        return []
    out = []
    for arq in sorted(p.glob("????-??-??.json"), reverse=True)[:noites]:
        try:
            e = json.loads(arq.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append({"dia": e.get("dia") or arq.stem, "fase": e.get("fase") or "", **(e.get("contas") or {})})
    return out


# ── o laço ───────────────────────────────────────────────────────────────────────────────────────────────────────────
_LACO = {"thread": None, "parar": threading.Event(), "ultimo": ""}


def ligar(app, usinas_de, dossie_de, setores_de) -> None:
    """O laço da noite, de 5 em 5 minutos. Quem chama é o `campo.instalar` (app.py e servir.py), nunca o create_app: teste
    não liga nada que fale com a rede. Não liga onde `NEXUS_IA_NOITE=0` nem no PC (`NEXUS_CAMPO_AQUECER=0`): duas máquinas
    com a mesma chave mandariam dois lotes. Cada passo roda dentro de um pedido de mentira, porque montar o dossiê usa o
    que as telas usam (a sessão vazia: sem nome de pessoa)."""
    if (_LACO["thread"] is not None or str(app.config.get("NEXUS_IA_NOITE", "1")).strip() == "0"
            or str(app.config.get("NEXUS_CAMPO_AQUECER", "1")).strip() == "0"):
        return

    def laco():
        while not _LACO["parar"].wait(LACO_S):
            agora = datetime.now(IA._BRT)
            if not (agora.hour < FIM_H):
                continue                           # de dia o laço só olha o relógio
            try:
                with app.test_request_context():
                    cfg = app.config
                    feito = passo(cfg, agora, usinas_de, dossie_de, setores_de, lambda: IA.cliente_anthropic(cfg))
                if feito != _LACO["ultimo"]:
                    log.info("Insights de madrugada: %s", feito)
                    _LACO["ultimo"] = feito
            except Exception:        # noqa: BLE001 — o laço não morre por um passo
                log.exception("Insights de madrugada: o passo falhou")

    _LACO["thread"] = threading.Thread(target=laco, name="nexus-insights-da-noite", daemon=True)
    _LACO["thread"].start()

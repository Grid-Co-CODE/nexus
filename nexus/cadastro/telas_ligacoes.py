"""Tela Base → Ligações entre bases: os buracos do de_para à vista, e a correção feita ali mesmo.

Pedido do Levi (04/10/2026): "quero uma tela para fazer os de-para pelo Nexus, quero que esses buracos de ligação
fiquem expostos para que possamos corrigir". A lógica mora em ligacoes.py; aqui só as rotas.
"""
import re
from datetime import datetime
from urllib.parse import urlencode

from flask import current_app, redirect, render_template, request

from . import banco as B
from . import ligacoes as L
from .telas import _quem, _tela

ABAS = (("buracos", "Buracos"), ("por-nome", "Ligado por nome"), ("fora", "Usinas fora"), ("decisoes", "Decisões"))


def _int(v):
    m = re.match(r"\s*(\d+)", str(v or ""))
    return int(m.group(1)) if m else None


def _hora(iso):
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m %H:%M")
    except (TypeError, ValueError):
        return ""


def _volta(**k):
    q = {x: request.form.get(x, "") for x in ("aba", "sistema") if request.form.get(x)}
    q.update({x: y for x, y in k.items() if y})
    return redirect("/t/base/ligacoes?" + urlencode(q), code=303)


def registrar_ligacoes(bp):
    @bp.route("/ligacoes")
    @_tela("Ligações entre bases")
    def ligacoes(srv):
        cfg = current_app.config
        aba = request.args.get("aba") if request.args.get("aba") in dict(ABAS) else "buracos"
        sistema = request.args.get("sistema") or ""
        p = L.panorama(srv, L.ler(cfg), L.carregar_regras(cfg))
        def filtra(xs):
            return [x for x in xs if not sistema or x["sistema"] == sistema]
        fora = [(s, sum(len(us) for _, us in g), g) for s, g in p["ausencias"].items()
                if (not sistema or s == sistema) and g]
        contagem = {"buracos": len(filtra(p["buracos"])), "por-nome": len(filtra(p["por_nome"])),
                    "fora": sum(t for _, t, _ in fora), "decisoes": len(p["decisoes"])}
        return render_template("cadastro/ligacoes.html", p=p, aba=aba, abas=ABAS, sistema=sistema,
                               buracos=filtra(p["buracos"]), por_nome=filtra(p["por_nome"]), fora=fora,
                               contagem=contagem, gerado_em=_hora(p["gerado_em"]), hora=_hora,
                               ok=request.args.get("ok"), erro=request.args.get("erro"),
                               pode_publicar=bool(cfg.get("GRIDCO_SQL_TOKEN")))

    @bp.route("/ligacoes/recalcular", methods=["POST"])
    @_tela("Ligações entre bases")
    def ligacoes_recalcular(srv):
        try:
            L.calcular(current_app.config, srv)
        except Exception as ex:          # noqa: BLE001 — base fora do ar: a tela diz, não quebra
            return _volta(erro=f"Não consegui ler as bases: {type(ex).__name__}: {str(ex)[:160]}")
        return _volta(ok="Bases lidas de novo.")

    @bp.route("/ligacoes/decidir", methods=["POST"])
    @_tela("Ligações entre bases")
    def ligacoes_decidir(srv):
        cfg, f = current_app.config, request.form
        try:
            L.decidir(cfg, f.get("acao", ""), f.get("alvo_sistema", ""), chave=f.get("chave") or None,
                      usina_id=_int(f.get("usina")), cliente_id=_int(f.get("cliente_id")),
                      motivo=f.get("motivo", ""), quem=_quem())
        except L.DecisaoInvalida as ex:
            return _volta(erro=str(ex))
        L.reaplicar(cfg, srv)
        return _volta(ok="Decisão gravada e aplicada.")

    @bp.route("/ligacoes/publicar", methods=["POST"])
    @_tela("Ligações entre bases")
    def ligacoes_publicar(srv):
        cfg = current_app.config
        atual = L.ler(cfg)
        if not atual:
            return _volta(erro="Leia as bases antes de publicar.")
        if not cfg.get("GRIDCO_SQL_TOKEN"):
            return _volta(erro="Falta o GRIDCO_SQL_TOKEN no .env do Nexus.")
        base = (cfg.get("GRIDCO_DB_API") or L.BASE_API).rstrip("/")
        try:
            t = B.montar(srv, srv.cofre, atual["fontes"], B.ler_anteriores(base), L.carregar_regras(cfg))
            r = B.sincronizar(B.xlsx_bytes(t), base=base, token=cfg["GRIDCO_SQL_TOKEN"])
        except Exception as ex:          # noqa: BLE001
            return _volta(erro=f"O banco recusou: {type(ex).__name__}: {str(ex)[:160]}")
        return _volta(ok=f"Publicado no banco: {r.get('inserted', 0)} linhas novas, {r.get('updated', 0)} alteradas.")

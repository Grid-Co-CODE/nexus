"""Tela Base → Governança de dados: a matriz de barramento viva (do catálogo) e a qualidade da última carga.

Levi, 05/10/2026: "prioridade 0 para a governança e controle de dados". A tela mostra o que existe, de onde vem, o que
é cada linha (grão) e quanto de cada fato liga por ID. A qualidade vem do banco (`nexus_fatos · qualidade`, gravada pela
carga de hora em hora); sem ela, a tela mostra só o catálogo e avisa.

08/10/2026 (auditoria Kimball): a matriz mostra também o TIPO de cada fato, a chave, as medidas (com a unidade e se
somam) e quanto a fonte guarda; os livros do Nexus (registrados antes de existir: regra 10); a saúde do histórico
(`nexus_dimensoes · qualidade_historico`) e o resumo da dimensão de equipamento (`nexus_equipamentos · qualidade`).
"""
import json
import time
from datetime import datetime

from flask import current_app, render_template

from . import carga, catalogo, equipamento, historico, livros, programacao

_CACHE = {"t": 0.0, "v": None}
TTL_S = 300
# o que a tela mostra do `nexus_equipamentos · qualidade` (formato longo: grupo, item)
_EQ_RESUMO = (("dimensão", "membros"), ("dimensão", "na foto do Fracttal"), ("dimensão", "com usina_id"),
              ("dimensão", "com pai_id"))


def _ultima_qualidade():
    if _CACHE["v"] is not None and time.time() - _CACHE["t"] < TTL_S:
        return _CACHE["v"]
    import requests
    s = current_app.extensions.get("nexus_dados_sessao")
    if s is None and current_app.config.get("TESTING"):
        return {"qualidade": {}, "atualizacao": {}, "historico": [], "equipamento": [],
                "erro": "teste sem banco"}     # teste nunca vai à rede
    s = s or requests.Session()
    base = carga._base(current_app.config)
    try:
        q = {l.get("fato"): l for l in livros.ler(base, s, carga.LIVRO_FATOS, "qualidade")}
        # a programação do PCM tem livro próprio desde 08/10/2026 (`nexus_programacao`, mescla por semana)
        q.update({l.get("fato"): l for l in livros.ler(base, s, programacao.LIVRO, "qualidade")})
        at = next(iter(livros.ler(base, s, carga.LIVRO_FATOS, "atualizacao")), {})
        hq = livros.ler(base, s, carga.LIVRO_DIM, historico.ABA_QUALIDADE)
        eq = {(l.get("grupo"), l.get("item")): l for l in livros.ler(base, s, equipamento.LIVRO, "qualidade")}
        v = {"qualidade": q, "atualizacao": at, "historico": hq,
             "equipamento": [(item, eq[(g, item)]) for g, item in _EQ_RESUMO if (g, item) in eq], "erro": None}
    except Exception as e:      # noqa: BLE001 — banco fora do ar: a tela mostra o catálogo
        v = {"qualidade": {}, "atualizacao": {}, "historico": [], "equipamento": [], "erro": f"{type(e).__name__}"}
    _CACHE.update(t=time.time(), v=v)
    return v


def _hora(iso) -> str:
    try:
        return datetime.fromisoformat(str(iso)).strftime("%d/%m %H:%M")
    except (TypeError, ValueError):
        return ""


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pct(v) -> str:
    """99.7 -> "99,7%", 100.0 -> "100%", vazio -> "" (a qualidade tem 1 casa desde 08/10; a API pode devolver texto)."""
    x = _num(v)
    if x is None:
        return ""
    return f"{int(x)}%" if x == int(x) else f"{x:.1f}%".replace(".", ",")


def _extra(v) -> dict:
    try:
        d = json.loads(v or "{}")
    except (TypeError, ValueError):
        return {}
    return {k: x for k, x in d.items() if isinstance(x, (int, float, str)) and not isinstance(x, bool)}


def registrar_governanca(bp):
    @bp.route("/governanca")
    def governanca():
        v = _ultima_qualidade()
        grupos = {}
        for f in catalogo.FATOS:
            grupos.setdefault(f.area, []).append(f)
        return render_template("dados/governanca.html", torre=bp.name, catalogo=catalogo, grupos=grupos,
                               resumo=catalogo.resumo(), q=v["qualidade"], atualizacao=v["atualizacao"],
                               hist_q=v["historico"], eq_q=v["equipamento"], erro=v["erro"], hora=_hora, pct=_pct,
                               num=_num, extra=_extra)

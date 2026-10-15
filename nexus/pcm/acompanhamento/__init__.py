"""PCM → Acompanhamento (14/10/2026): o painel de acompanhamento do PCM O&M dentro do Nexus.

Levi, 14/10/2026, com o pacote de integração do "Painel PCM O&M" (as abas MPA, MPS, Radar de Backlog, Mapa e One Page):
"Quero que libere na seção de PCM essa visão de acompanhamento. O design quero alá Nexus, não quero que copie o design,
mas as estruturas quero sim que mantenha!". Regras, de onde vem cada número e como provar: CLAUDE.md desta pasta.

- `dados.py`: as contas (o contrato do painel: DATA, EXTRA e COLAB), sobre fontes já lidas;
- `curadoria.py`: a decisão da reunião de PCM sobre cada MPA/MPS (livro do banco, cifrado);
- `mapa.py`: o desenho do Brasil e as distâncias, com a coordenada presa no servidor;
- aqui: as leituras (as MESMAS das telas donas: `pcm.fonte`, a Gerencial da Gestão PCM, o cadastro) e as rotas. A tela é
  `templates/pcm/acompanhamento.html` com `static/pcm-acomp.js` e `static/pcm-acomp.css`.
"""
import gzip
import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from flask import Response, current_app, render_template, request

from ...dados import livros
from .. import fonte
from . import curadoria as CUR
from . import dados as D
from .mapa import Geo

log = logging.getLogger(__name__)

TELA = "acompanhamento"
BRT = timezone(timedelta(hours=-3))
CACHE_S = 120                       # o mesmo dado para quem abrir nos próximos 2 minutos (a pré-carga aquece)
_CACHE: dict = {}
_TRAVA = threading.Lock()


def _banco():
    from ...auth import setor_telas
    return setor_telas._banco()


def _livro_cadastro(aba: str) -> list[dict]:
    """Uma aba do cadastro publicado (o de-para do Fracttal), guardada por 10 minutos."""
    c = _CACHE.get(("cad", aba))
    if c and time.time() - c[0] < 600:
        return c[1]
    base, sessao = _banco()
    linhas = livros.ler(base, sessao, "cadastro_nexus", aba)
    _CACHE[("cad", aba)] = (time.time(), linhas)
    return linhas


def _geo_e_pessoas() -> tuple:
    """(Geo ou None, colaboradores ativos [{nome, cargo, cluster}], {cluster: supervisor de campo}, aviso). Sem o cadastro
    nesta máquina, o mapa sai sem as usinas e a tela diz por quê."""
    from ...performance.clima.usinas import SemCadastro, do_app
    from ...cadastro.telas import servico
    try:
        cad = do_app()
    except SemCadastro as ex:
        return None, [], {}, str(ex)
    except Exception as ex:          # noqa: BLE001 — cadastro que não abre não derruba a tela
        log.warning("acompanhamento: o cadastro não abriu (%s)", type(ex).__name__)
        return None, [], {}, f"o cadastro não abriu ({type(ex).__name__})"
    from ...dados import fatos as F
    por_fracttal, nome_fracttal, aviso = {}, {}, ""
    try:
        for d in _livro_cadastro("de_para"):
            if str(d.get("sistema") or "").strip() == F.SISTEMA_FRACTTAL and F._id(d.get("usina_id")):
                uid = str(F._id(d.get("usina_id")))
                por_fracttal[D.norm(d.get("chave_externa"))] = uid
                nome_fracttal.setdefault(uid, str(d.get("chave_externa") or "").strip())
    except Exception as ex:          # noqa: BLE001 — sem o de-para, liga pelo nome
        aviso = f"o de-para do Fracttal não abriu ({type(ex).__name__}): as usinas ligam só pelo nome"
    geo = Geo(cad.usinas, por_fracttal, nome_fracttal)
    colab, sup = [], {}
    try:
        srv = servico()
        regiao_sup = {}
        for r in srv.registros("regioes_campo"):
            nome = srv.titulo_de("pessoas", r.valor("supervisor_campo")) if r.valor("supervisor_campo") else ""
            regiao_sup[str(r.id)] = nome
        for e in srv.registros("equipes"):
            reg = e.valor("regiao_campo")
            nome = regiao_sup.get(str(reg), "") if reg else ""
            if nome and e.valor("nome"):
                sup[str(e.valor("nome"))] = nome
        for p in srv.registros("pessoas"):
            if p.ilegivel or str(p.valor("status") or "").strip().lower() != "ativo":
                continue
            colab.append({"nome": str(p.valor("nome") or "").strip(), "cargo": str(p.valor("cargo") or "").strip(),
                          "cluster": srv.titulo_de("equipes", p.valor("equipe")) if p.valor("equipe") else ""})
    except Exception as ex:          # noqa: BLE001 — sem as pessoas, o mapa segue sem as equipes
        log.warning("acompanhamento: as pessoas do cadastro não abriram (%s)", type(ex).__name__)
    return geo, [c for c in colab if c["nome"]], sup, aviso


def montar(forcar: bool = False) -> dict:
    """{"payload" (o JSON da tela), "avisos", "fontes"}, guardado por 2 minutos e pela versão de cada fonte."""
    from ..telas import _gerencial
    cfg = current_app.config
    lg, lb = fonte.ler_gestao(cfg), fonte.ler(cfg)
    mp, ger_erro = _gerencial(cfg)
    try:
        base, sessao = _banco()
    except Exception as ex:          # noqa: BLE001 — sem o banco, a curadoria diz por quê (a de arquivo segue valendo)
        base, sessao = None, str(ex) or type(ex).__name__
    cur = CUR.ler(cfg, base, sessao)
    chave = (lg.baixado_em, lb.baixado_em, (mp or {}).get("geradoEm"), cur.get("lido_em"), len(cur.get("itens") or []))
    c = _CACHE.get("payload")
    if c and not forcar and c[0] == chave and time.time() - c[1] < CACHE_S:
        return c[2]
    with _TRAVA:
        geo, colab, sup, aviso_geo = _geo_e_pessoas()
        hoje = datetime.now(BRT).date()
        payload = D.montar(lg.dados, lb.dados, mp, cur.get("itens") or [], cur.get("manutencao") or {}, hoje, geo=geo,
                           colab=colab, sup_cadastro=sup)
        avisos = {"gestao": "" if lg.dados else (lg.erro or "sem dado"), "bd": "" if lb.dados else (lb.erro or "sem dado"),
                  "gerencial": "" if mp else (ger_erro or "sem dado"), "curadoria": cur.get("erro") or "",
                  "curadoria_ilegiveis": cur.get("ilegiveis") or 0, "mapa": aviso_geo}
        payload["AVISOS"] = avisos
        payload["FONTES"] = {"gestao": (lg.dados or {}).get("geradoEm") or "", "bd": (lb.dados or {}).get("geradoEm") or "",
                             "gerencial": (mp or {}).get("geradoEm") or "", "curadoria": cur.get("fonte") or ""}
        corpo = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        r = {"payload": payload, "json": corpo, "gz": gzip.compress(corpo, 6), "geo": geo}
        _CACHE["payload"] = (chave, time.time(), r)
    return r


def registrar(bp) -> None:
    """A tela (`/t/pcm/acompanhamento`), os dados dela (`.../dados.json`) e a distância entre duas usinas
    (`.../rota?o=&d=`). As sub-rotas seguem a marca da tela no portão de setor."""

    @bp.route(f"/{TELA}", endpoint=TELA)
    def tela():
        return render_template("pcm/acompanhamento.html", aba=request.args.get("aba") or "")

    @bp.route(f"/{TELA}/dados.json", endpoint=f"{TELA}_dados")
    def dados_json():
        r = montar()
        if "gzip" in (request.headers.get("Accept-Encoding") or ""):
            return Response(r["gz"], mimetype="application/json",
                            headers={"Content-Encoding": "gzip", "Vary": "Accept-Encoding", "Cache-Control": "no-store"})
        return Response(r["json"], mimetype="application/json",
                        headers={"Vary": "Accept-Encoding", "Cache-Control": "no-store"})

    @bp.route(f"/{TELA}/rota", endpoint=f"{TELA}_rota")
    def rota():
        """{"km": linha reta entre `o` e `d` (ou null), "perto": as 6 usinas do mapa mais perto de `o`}. A coordenada não
        sai daqui: só a distância."""
        r = montar()
        geo = r["geo"]
        o, d = (request.args.get("o") or "")[:200], (request.args.get("d") or "")[:200]
        if not geo or not o:
            return Response(json.dumps({"km": None, "perto": []}), mimetype="application/json",
                            headers={"Cache-Control": "no-store"})
        nomes = [u["usina"] for u in r["payload"]["EXTRA"]["usinas"] if u.get("pt")]
        corpo = {"km": geo.km(o, d) if d else None, "perto": geo.perto(o, nomes)}
        return Response(json.dumps(corpo, ensure_ascii=False), mimetype="application/json",
                        headers={"Cache-Control": "no-store"})

"""A API do SSO no Nexus, no lugar do Supabase: o site (`sso-zeladoria.gridco.com.br`, no Cloudflare do HEAD da zeladoria)
fica onde está e troca só o `shared/supabase-client.js` pelo de `nexus/sso/site/`, que fala com estas rotas.

Debaixo de `/t/sso` porque o Caddy do servidor só manda ao Nexus os segmentos dele (`t`, `entrar`, `os`, `static`...).
Os caminhos das duas funções e dos arquivos são os do Supabase (`/functions/v1/...`, `/storage/v1/object/public/...`):
o JS do site monta esses endereços sozinho, e não muda.

**Rotas públicas, conscientes** (`auth.ROTAS_PUBLICAS`, todas `sso.*` menos o `voltar` e a página do administrador): o
fornecedor não tem conta. Quem decide é o passe da Gestão (`regras.py`) e, sem ele, o que o RLS do Supabase deixava ao
anônimo (`esquema.py`): enviar, e ler só o que o formulário precisa. Cada uma com o limite por IP (`limite.py`), o teto
de tamanho e só de páginas do site (o `Origin`).
"""
from __future__ import annotations

import json
import os
from urllib.parse import quote, urlsplit

from flask import Blueprint, Response, abort, current_app, jsonify, redirect, render_template, request, send_file, session

from ..prefixo import na_raiz
from . import arquivos as A
from . import esquema as E
from . import gravacao as G
from . import limite
from . import regras as R
from .esquema import Recusa

bp = Blueprint("sso", __name__, url_prefix="/t/sso", template_folder="templates")
ORIGENS_PADRAO = ("https://sso-zeladoria.gridco.com.br",)
CABECALHOS = "authorization, content-type, apikey, x-client-info, prefer"
MAX_JSON = 10 * E.MB                # o lote da Gestão (a planilha de presenças, a linha editada com as assinaturas)
MAX_JSON_FORNECEDOR = 2 * E.MB      # o formulário do fornecedor (a maior linha real, 130 KB; o teto por linha, 1 MB)
# as rotas públicas (sem login do Nexus): o passe ou a regra do anônimo decide
PUBLICAS = frozenset({"sso.preflight", "sso.eu", "sso.ler", "sso.gravar", "sso.progresso", "sso.arquivo_enviar",
                      "sso.funcao_upload", "sso.funcao_assinatura", "sso.arquivo_abrir", "sso.video"})


def aquecer_ao_subir(app) -> None:
    """Os sete livros do SSO lidos por trás logo depois de subir, onde o SSO grava (chamado pelo `servir.py`): a 1ª
    leitura leva ~40 s (medido na cópia de prova, 12/11/2026: o APR tem 4,8 MB), e sem isto o primeiro fornecedor depois
    de cada deploy esperaria."""
    if app.config.get("TESTING"):
        return
    import threading
    import time

    def tarefa():
        time.sleep(5)
        try:
            with app.app_context():
                if G.ativo(app.config):
                    G.do_app(app.config, esperar=True)
        except Exception:        # noqa: BLE001 — o 1º pedido tenta de novo e mostra o erro
            app.logger.warning("sso: a leitura dos livros ao subir falhou", exc_info=True)
    threading.Thread(target=tarefa, daemon=True, name="nexus-sso-aquecer").start()


def origens() -> tuple:
    v = str(current_app.config.get("NEXUS_SSO_ORIGENS") or os.environ.get("NEXUS_SSO_ORIGENS") or "").strip()
    return tuple(o.strip().rstrip("/") for o in v.split(",") if o.strip()) if v else ORIGENS_PADRAO


ENDERECO_PADRAO = "https://app.gridco.com.br"      # o Nexus no servidor, na raiz (o mesmo do e-mail semanal da Segurança)
_LOCAIS = ("localhost", "127.0.0.1", "::1", "[::1]")


def endereco_publico() -> str:
    """O endereço do Nexus como o navegador o vê, para os links que saem para o site (os arquivos assinados, o vídeo) e
    para conferir os endereços de arquivo que o fornecedor grava. NUNCA o `request.host`: no servidor o pedido chega pelo
    proxy com o endereço interno (`10.32.28.19:5070`), e em 13/11/2026 toda linha com foto foi recusada ("endereço de
    arquivo que não é do SSO"), e o link do vídeo e das fotos da Gestão saía com o endereço interno. `NEXUS_SSO_ENDERECO`
    vence; sem ela, a máquina local (o PC, a cópia de prova, os testes) usa o próprio endereço, e o resto, o do servidor."""
    v = str(current_app.config.get("NEXUS_SSO_ENDERECO") or os.environ.get("NEXUS_SSO_ENDERECO") or "").strip()
    if v:
        return v.rstrip("/")
    nome = (request.host or "").rsplit(":", 1)[0].lower() if not (request.host or "").startswith("[") else "[::1]"
    if nome in _LOCAIS or nome.endswith(".localhost"):
        return request.host_url.rstrip("/")
    return ENDERECO_PADRAO


def hosts_do_nexus() -> set:
    """Os endereços que valem como "deste Nexus" num link de arquivo: o público e o do próprio pedido."""
    return {urlsplit(endereco_publico()).netloc.lower(), (request.host or "").lower()} - {""}


def _origem_ok() -> bool:
    o = (request.headers.get("Origin") or "").rstrip("/")
    return o in origens() or (bool(o) and urlsplit(o).netloc.lower() in hosts_do_nexus())


@bp.after_request
def _cors(resp):
    o = (request.headers.get("Origin") or "").rstrip("/")
    # sempre: o vídeo pedido pelo <video> (sem Origin) ficava no cache sem o CORS, e um fetch do site depois falhava
    resp.headers["Vary"] = "Origin"
    if o in origens():
        resp.headers["Access-Control-Allow-Origin"] = o
        resp.headers["Access-Control-Allow-Headers"] = CABECALHOS
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Max-Age"] = "600"
    resp.headers.setdefault("Cache-Control", "no-store")
    return resp


def _rota(regra, **kw):
    """As rotas do SSO sem o OPTIONS automático do Flask: o pedido prévio do CORS cai no `preflight`, que é público
    (senão o portão do login o mandaria ao Entrar, e o navegador recusaria o pedido de verdade)."""
    kw.setdefault("provide_automatic_options", False)
    return bp.route(regra, **kw)


@bp.route("/<path:resto>", methods=["OPTIONS"])
def preflight(resto):
    return Response("ok", status=200)


def _ip() -> str:
    return request.remote_addr or "?"


def _erro(msg: str, status: int = 400):
    return jsonify(error=msg, message=msg), status


def _passe():
    """O passe do pedido, com o "administrador" reconferido na lista de agora (o de quem saiu da lista não vale mais)."""
    from ..auth import _admins
    h = request.headers.get("Authorization") or ""
    return R.ler_passe(current_app._get_current_object(), h[7:].strip() if h.lower().startswith("bearer ") else None,
                       admins=_admins())


def _limitar_arquivo(gestao: bool):
    """O teto do corpo ANTES de ler o formulário: o Flask confere o tamanho na 1ª leitura do `request.form`, com o
    limite geral de 25 MB do Nexus, e depois disso trocar o limite não adianta (revisão de 12/11/2026: o vídeo da
    integração, de 28 MB, voltava 413). O fornecedor fica no teto dos buckets dele."""
    teto = (E.MAIOR if gestao else E.MAIOR_FORNECEDOR) + E.MB
    request.max_content_length = teto
    return (request.content_length or 0) <= teto


def _base_absoluta() -> str:
    return endereco_publico() + na_raiz("/t/sso")


def _gravador():
    """O gravador e o erro: (g, None) ou (None, resposta 503). O SSO só funciona onde a gravação está ligada."""
    try:
        return G.do_app(current_app.config), None
    except G.ForaDoAr as e:
        return None, _erro(str(e), 503)


def _quem(g):
    return R.quem_sou(g.estado, _passe())


def _para_o_app(g, quem, linhas):
    """As linhas como saem: a Gestão recebe os endereços dos arquivos assinados; o fornecedor, o vídeo da sessão pelo
    endereço público dele."""
    if quem["papel"] == "gestao":
        return A.assinadas(current_app._get_current_object(), linhas, _base_absoluta())
    out = []
    for l in linhas:
        if "url_video" in l:
            l = {**l, "url_video": _video_publico(l.get("url_video"))}
        out.append(l)
    return out


def _video_publico(url):
    m = A.URL.match(str(url or "")) if url else None
    if not m or m.group("bucket") != "integracao-video-midia":
        return url
    return f"{_base_absoluta()}/video/{m.group('bucket')}/{m.group('caminho')}"


# ── quem sou e o passe ───────────────────────────────────────────────────────────────────────────────────────────────
@_rota("/voltar")
def voltar():
    """A volta ao site com o passe da Gestão (exige o login do Nexus; quem não tem setor também passa, porque no SSO
    quem decide é o perfil, como no site)."""
    para = request.args.get("para") or ""
    p = urlsplit(para)
    if f"{p.scheme}://{p.netloc}".rstrip("/") not in origens() or not p.path.startswith("/gestao"):
        abort(400)
    u = session.get("usuario") or {}
    passe = R.emitir_passe(current_app._get_current_object(), str(u.get("email") or ""), bool(session.get("admin")))
    destino = para.split("#", 1)[0] + "#nexus_sso=" + quote(passe)
    resp = redirect(destino)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@_rota("/api/eu")
def eu():
    if _passe() is None:
        return _erro("sem passe", 401)
    g, erro = _gravador()
    if erro:
        return erro
    q = _quem(g)
    linha = g.linha("iv_perfis", q["id"])
    if _passe()["admin"] and (linha is None or linha.get("status") != "aprovado"):
        # o administrador do Nexus ganha a linha dele aprovada (sem ela, o app criaria a "pendente" e mostraria a tela
        # de espera); o resto ganha a "pendente" pelo próprio app, como antes
        op = {"op": "insert", "aba": "iv_perfis", "linhas": [{"user_id": q["id"], "email": q["email"],
                                                              "status": "aprovado"}]} if linha is None else \
            {"op": "update", "aba": "iv_perfis", "filtros": [("eq", "user_id", q["id"])], "patch": {"status": "aprovado"}}
        try:
            g.aplicar([op], {"email": q["email"], "status": "aprovado"}, g.estado["versao"])
        except (Recusa, OSError):
            current_app.logger.warning("sso: a linha do administrador no iv_perfis não gravou", exc_info=True)
    return jsonify(user={"id": q["id"], "email": q["email"]}, status=q["status"], papel=q["papel"])


# ── ler e gravar ─────────────────────────────────────────────────────────────────────────────────────────────────────
def _filtros():
    out = []
    for op in ("eq", "neq"):
        for item in request.args.getlist(op):
            col, _, bruto = item.partition(":")
            try:
                val = json.loads(bruto)
            except ValueError:
                val = bruto
            out.append((op, col, val))
    return out


@_rota("/api/v/<view>")
def ler(view):
    g, erro = _gravador()
    if erro:
        return erro
    quem = _quem(g)
    if quem["papel"] != "gestao" and limite.passou(_ip(), "consulta"):
        return _erro("muitas consultas deste endereço; tente de novo mais tarde", 429)
    ordem = []
    for o in request.args.getlist("order"):
        col, _, sentido = o.partition(":")
        ordem.append((col, sentido == "desc"))
    lim = request.args.get("limit")
    colunas = [c.strip() for c in (request.args.get("select") or "*").split(",") if c.strip() and c.strip() != "*"]
    try:
        linhas = R.ler(g.estado, view, filtros=_filtros(), ordem=ordem, limite=int(lim) if lim else None,
                       colunas=colunas or None, quem=quem)
    except (Recusa, ValueError) as e:
        return _erro(str(e), 400)
    return jsonify(_para_o_app(g, quem, linhas))


@_rota("/api/gravar", methods=["POST"])
def gravar():
    if not _origem_ok():
        return _erro("pedido de outro site", 403)
    # o teto antes de ler o corpo: a Gestão manda o lote da planilha; o anônimo, uma linha de formulário (a maior real
    # tem 130 KB)
    request.max_content_length = MAX_JSON if _passe() else MAX_JSON_FORNECEDOR
    g, erro = _gravador()
    if erro:
        return erro
    quem = _quem(g)
    tamanho = request.content_length or 0
    if quem["papel"] != "gestao" and (limite.passou(_ip(), "envio_bytes", tamanho)
                                      or limite.passou(limite.TODOS, "todos_envio_bytes", tamanho)):
        return _erro("muitos envios agora; tente de novo mais tarde", 429)
    corpo = request.get_json(silent=True)
    ops = corpo.get("ops") if isinstance(corpo, dict) else None
    if not isinstance(ops, list) or not ops or len(ops) > 50:
        return _erro("pedido de gravação inválido")
    n = sum(len(o.get("linhas") or []) if isinstance(o, dict) else 1 for o in ops)
    if quem["papel"] != "gestao" and (n > 20 or limite.passou(_ip(), "envio", max(1, n))):
        return _erro("muitos envios deste endereço; tente de novo mais tarde", 429)
    try:
        with g._trava:
            prontos = R.preparar(g.estado, quem, ops, hosts=hosts_do_nexus())
            r = g.aplicar(prontos, {"email": quem.get("email") or "formulario", "status": "aprovado"},
                          g.estado["versao"])
    except Recusa as e:
        return _erro(str(e), 403 if "permissão" in str(e) else 400)
    except OSError:
        current_app.logger.exception("sso: o diário da gravação não gravou")
        return _erro("O Nexus não conseguiu guardar agora. Tente de novo em instantes.", 503)
    feitas = r.get("ids") or []
    if quem["papel"] != "gestao":
        # o fornecedor não lê de volta o que enviou (o RLS não deixava; o app nem pede): só a contagem
        return jsonify(resultado=[[] for _ in feitas], contagem=[len(x) for x in feitas])
    return jsonify(resultado=[_para_o_app(g, quem, x) for x in feitas], contagem=[len(x) for x in feitas])


@_rota("/api/rpc/atualizar_progresso", methods=["POST"])
def progresso():
    """O progresso do vídeo da integração (o bug da seção 6 do pacote: a função existia no banco e o app nunca a achava;
    0 de 52 visualizações tinham progresso)."""
    if not _origem_ok():
        return _erro("pedido de outro site", 403)
    if limite.passou(_ip(), "progresso"):
        return _erro("muitos pedidos deste endereço", 429)
    g, erro = _gravador()
    if erro:
        return erro
    corpo = request.get_json(silent=True) or {}
    try:
        r = G.atualizar_progresso(g, corpo.get("p_visualizacao_id"), corpo.get("p_progresso_segundos"))
    except Recusa as e:
        return _erro(str(e), 400)
    except OSError:
        return _erro("O Nexus não conseguiu guardar agora.", 503)
    return jsonify(r)


# ── as duas funções do Supabase ──────────────────────────────────────────────────────────────────────────────────────
@_rota("/functions/v1/iv-presenca-assinatura", methods=["GET", "POST"])
def funcao_assinatura():
    """O link de assinatura da presença importada por planilha: GET dá só o nome e se já assinou; POST grava a
    assinatura só se ainda não existe (como a função do Supabase, com as mesmas mensagens)."""
    def resp(corpo, status=200):
        return jsonify(corpo), status
    if limite.passou(_ip(), "consulta"):
        return resp({"ok": False, "error": "Muitas tentativas. Tente de novo mais tarde."}, 429)
    g, erro = _gravador()
    if erro:
        return resp({"ok": False, "error": "O Nexus não está guardando o SSO agora. Tente de novo mais tarde."}, 503)
    if request.method == "GET":
        pid = request.args.get("id") or ""
        if not pid:
            return resp({"ok": False, "error": "Link invalido (sem id)."}, 400)
        p = g.linha("iv_presencas", pid)
        if not p:
            return resp({"ok": False, "error": "Registro nao encontrado. Confira o link recebido."}, 404)
        return resp({"ok": True, "nomeCompleto": p.get("nome_completo"), "jaAssinado": bool(p.get("assinatura_base64"))})
    if not _origem_ok():
        return resp({"ok": False, "error": "Pedido de outro site."}, 403)
    corpo = request.get_json(silent=True) or {}
    pid, ass = str(corpo.get("id") or ""), str(corpo.get("assinaturaBase64") or "")
    if not pid:
        return resp({"ok": False, "error": "Link invalido (sem id)."}, 400)
    if not ass.startswith("data:image/"):
        return resp({"ok": False, "error": "Assinatura invalida."}, 400)
    if len(ass) > 2_000_000:
        return resp({"ok": False, "error": "Assinatura grande demais."}, 400)
    with g._trava:
        p = g.linha("iv_presencas", pid)
        if not p:
            return resp({"ok": False, "error": "Registro nao encontrado. Confira o link recebido."}, 404)
        if p.get("assinatura_base64"):
            return resp({"ok": False, "error": "Esse registro ja foi assinado anteriormente."}, 409)
        try:
            g.aplicar([{"op": "update", "aba": "iv_presencas", "filtros": [("eq", "id", pid)],
                        "patch": {"assinatura_base64": ass}}], {"email": "link-assinatura", "status": "aprovado"},
                      g.estado["versao"])
        except (Recusa, OSError) as e:
            return resp({"ok": False, "error": str(e) if isinstance(e, Recusa) else "Falha ao guardar."}, 500)
    return resp({"ok": True})


def _receber(bucket: str, caminho: str, sobrescrever: bool):
    """O arquivo do formulário (o teto do corpo já foi posto antes, `_limitar_arquivo`)."""
    arq = request.files.get("arquivo") or request.files.get("file")
    if arq is None:
        raise A.Recusado("faltou o arquivo")
    return A.guardar(current_app.config, bucket, caminho, arq.stream, sobrescrever=sobrescrever)


_INVENTARIO = {"de": None, "caminhos": frozenset()}


def _do_inventario(g, bucket: str, caminho: str) -> bool:
    """O caminho é de um arquivo antigo (o inventário do Supabase)? O fornecedor não envia para ele: a foto plantada no
    lugar da antiga passaria por prova na Gestão e por resgatada na página do administrador (revisão de 12/11/2026)."""
    lista = g.estado["abas"].get("arquivos", [])
    if _INVENTARIO["de"] is not lista:
        _INVENTARIO.update(de=lista, caminhos=frozenset((a.get("bucket"), a.get("caminho")) for a in lista))
    return (bucket, caminho) in _INVENTARIO["caminhos"]


@_rota("/functions/v1/iv-upload-arquivo", methods=["POST"])
def funcao_upload():
    """O envio da Gestão aprovada que pode sobrescrever (o certificado corrigido, o vídeo da integração)."""
    if not _origem_ok():
        return jsonify(ok=False, error="Pedido de outro site."), 403
    g, erro = _gravador()
    if erro:
        return jsonify(ok=False, error="O Nexus não está guardando o SSO agora."), 503
    if _quem(g)["papel"] != "gestao":
        return jsonify(ok=False, error="Usuário não é gestão aprovada"), 400
    if not _limitar_arquivo(True):
        return jsonify(ok=False, error=f"O arquivo passa de {E.MAIOR // E.MB} MB."), 413
    bucket, caminho = request.form.get("bucket") or "", request.form.get("caminho") or ""
    if bucket not in ("integracao-video-midia", "certificados-integracao-video"):
        return jsonify(ok=False, error="Bucket não permitido"), 400
    try:
        r = _receber(bucket, caminho, True)
    except A.Recusado as e:
        return jsonify(ok=False, error=str(e)), 400
    return jsonify(ok=True, bucket=bucket, caminho=caminho, contentType=r["tipo"], bytes=r["bytes"])


@_rota("/api/arquivo", methods=["POST"])
def arquivo_enviar():
    """O `storage.from(bucket).upload` do app: o fornecedor nos buckets dos formulários, nunca por cima; a Gestão em
    todos, com o `upsert` que pedir."""
    if not _origem_ok():
        return _erro("pedido de outro site", 403)
    g, erro = _gravador()
    if erro:
        return erro
    quem = _quem(g)
    gestao = quem["papel"] == "gestao"
    if not _limitar_arquivo(gestao):
        return _erro(f"o arquivo passa de {(E.MAIOR if gestao else E.MAIOR_FORNECEDOR) // E.MB} MB", 413)
    tamanho = request.content_length or 0
    if not gestao and (limite.passou(_ip(), "arquivo") or limite.passou(_ip(), "bytes", tamanho)
                       or limite.passou(limite.TODOS, "todos_bytes", tamanho)):
        return _erro("muitos arquivos agora; tente de novo mais tarde", 429)
    bucket, caminho = request.form.get("bucket") or "", request.form.get("caminho") or ""
    regra = E.BUCKETS.get(bucket)
    if regra is None or not (gestao or regra["fornecedor"]):
        return _erro("bucket não permitido", 403)
    if not gestao and _do_inventario(g, bucket, caminho):
        return _erro("o arquivo já existe", 409)
    try:
        r = _receber(bucket, caminho, gestao and request.form.get("upsert") == "true")
    except A.Recusado as e:
        return _erro(str(e), 409 if "já existe" in str(e) else 400)
    # o link assinado volta também ao fornecedor, para a miniatura da foto que ele acabou de anexar (a vistoria e o diário
    # mostram a foto pelo endereço; sem a assinatura ela aparecia quebrada, e no Supabase o bucket era público). A linha
    # que ele grava vai ao banco sem a assinatura (`regras._do_fornecedor`)
    url = (f"{_base_absoluta()}/storage/v1/object/public/{bucket}/{caminho}"
           f"?a={quote(A.assinar(current_app._get_current_object(), bucket, caminho))}")
    return jsonify(Key=f"{bucket}/{caminho}", path=caminho, url=url, bytes=r["bytes"])


# ── abrir os arquivos ────────────────────────────────────────────────────────────────────────────────────────────────
def _servir(bucket, caminho):
    try:
        alvo = A.arquivo(current_app.config, bucket, caminho, do_inventario=True)
    except A.Recusado:
        abort(404)
    if not alvo.is_file():
        return _erro("Este arquivo ainda não está no Nexus (ficou no Supabase, travado desde 11/11/2026).", 404)
    with open(alvo, "rb") as f:
        tipo = E.tipo_do_arquivo(f.read(32)) or "application/octet-stream"
    resp = send_file(alvo, mimetype=tipo, conditional=True, download_name=caminho.rsplit("/", 1)[-1])
    resp.headers["Content-Disposition"] = "inline"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Cache-Control"] = "private, max-age=3600"
    return resp


@_rota("/storage/v1/object/public/<bucket>/<path:caminho>")
def arquivo_abrir(bucket, caminho):
    """Só com o link assinado (o que a Gestão recebe ao ler, 12 h): o `<img>` e o html2canvas do site não mandam o
    passe. No Supabase o bucket era público."""
    if bucket not in E.BUCKETS or not A.confere(current_app._get_current_object(), request.args.get("a"), bucket, caminho):
        abort(403)
    return _servir(bucket, caminho)


@_rota("/video/<bucket>/<path:caminho>")
def video(bucket, caminho):
    """O vídeo da sessão ativa, que o fornecedor assiste sem login (só ele; com o Range, para o vídeo andar)."""
    g, erro = _gravador()
    if erro:
        return erro
    ativos = set()
    for s in g.estado["abas"].get("iv_sessoes_video", []):
        m = A.URL.match(str(s.get("url_video") or "")) if s.get("ativo") is True else None
        if m:
            ativos.add((m.group("bucket"), m.group("caminho")))
    if bucket != "integracao-video-midia" or (bucket, caminho) not in ativos:
        abort(404)
    resp = _servir(bucket, caminho)
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp


# ── a página do administrador ────────────────────────────────────────────────────────────────────────────────────────
@_rota("/admin")
def admin():
    """O estado do SSO nesta máquina e o envio dos arquivos que ficaram no Supabase (o vídeo da integração e os do
    inventário). Só o administrador do Nexus."""
    if not session.get("admin"):
        abort(403)
    cfg = current_app.config
    g = erro = None
    if G.ativo(cfg):
        try:
            g = G.do_app(cfg)
        except G.ForaDoAr as e:
            erro = str(e)
    est = g.estado if g else None
    sit = A.situacao(cfg, est)
    sessoes = [{"titulo": s.get("titulo"), "ativo": s.get("ativo"), "url": s.get("url_video")}
               for s in (est or {}).get("abas", {}).get("iv_sessoes_video", [])]
    for s in sessoes:
        m = A.URL.match(str(s["url"] or "")) if s["url"] else None
        s["bucket"], s["caminho"] = (m.group("bucket"), m.group("caminho")) if m else (None, None)
        s["aqui"] = bool(m) and A.existe(cfg, s["bucket"], s["caminho"])
    usinas = sorted((str(u.get("nome") or "") for u in (est or {}).get("abas", {}).get("diario_usinas", [])),
                    key=str.lower)
    return render_template("sso/admin.html", grava=G.ativo(cfg), forcada=G.forcada(cfg), erro=erro,
                           situacao=_situacao(g), estado=est, arquivos=sit, sessoes=sessoes,
                           origens=origens(), maquina=request.host, usinas_diario=usinas,
                           endereco=endereco_publico(), ip=request.remote_addr)


def _situacao(g) -> dict | None:
    """O que a página do administrador mostra do gravador, e relê a cada poucos segundos enquanto ele grava (12/11/2026:
    o Levi clicou em "Regravar cifrado", a página ficou em "gravando…" para sempre e ele não soube se tinha terminado;
    tinha, em menos de um minuto, mas a página não se atualizava)."""
    if g is None:
        return None
    sit = g.situacao()
    rg = g.regravacao
    return {**sit, "gravado_em": g.gravado_em,
            "regravacao": ({**rg, "concluida": g.regravacao_concluida()} if rg else None)}


@_rota("/admin/situacao")
def admin_situacao():
    if not session.get("admin"):
        return jsonify(erro="Só o administrador."), 403
    try:
        g = G.do_app(current_app.config)
    except G.ForaDoAr as e:
        return jsonify(carregado=False, erro=str(e))
    return jsonify(carregado=True, **_situacao(g))


@_rota("/admin/regravar", methods=["POST"])
def admin_regravar():
    """Regrava os sete livros com a regra de cifra de agora (a usina, que a 1ª cópia deixou em claro)."""
    from ..auth.origem import de_outro_site
    if not session.get("admin") or de_outro_site():
        abort(403)
    try:
        g = G.do_app(current_app.config)
    except G.ForaDoAr:
        abort(503)
    g.regravar_tudo(str((session.get("usuario") or {}).get("email") or "administrador"))
    return redirect(na_raiz("/t/sso/admin"))


@_rota("/admin/usina-diario", methods=["POST"])
def admin_usina_diario():
    """Tira um nome da lista de usinas do diário (o fornecedor escreve nela sem lista fechada, e já escreveu o nome de uma
    pessoa; a lista aparece a todo fornecedor no formulário). Só o administrador; o diário já enviado não muda."""
    from ..auth.origem import de_outro_site
    if not session.get("admin") or de_outro_site():
        abort(403)
    try:
        g = G.do_app(current_app.config)
    except G.ForaDoAr:
        abort(503)
    nome = request.form.get("nome") or ""
    if g.linha("diario_usinas", nome) is not None:
        g.aplicar([{"op": "delete", "aba": "diario_usinas", "filtros": [("eq", "nome", nome)]}],
                  {"email": str((session.get("usuario") or {}).get("email") or "administrador"), "status": "aprovado"},
                  g.estado["versao"])
    return redirect(na_raiz("/t/sso/admin") + "#usinas-diario")


@_rota("/admin/arquivo", methods=["POST"])
def admin_arquivo():
    """Um arquivo do inventário (o resgate) pelo caminho dele: só caminho que o inventário cita, e por cima do que já
    houver (o administrador pode reenviar)."""
    from ..auth.origem import de_outro_site
    if not session.get("admin"):
        return jsonify(erro="Só o administrador envia."), 403
    if de_outro_site():
        return jsonify(erro="Pedido de outro site."), 403
    try:
        g = G.do_app(current_app.config)
    except G.ForaDoAr as e:
        return jsonify(erro=str(e)), 503
    if not _limitar_arquivo(True):
        return jsonify(erro=f"O arquivo passa de {E.MAIOR // E.MB} MB."), 413
    bucket, caminho = request.form.get("bucket") or "", request.form.get("caminho") or ""
    citados = {(a.get("bucket"), a.get("caminho")) for a in g.estado["abas"].get("arquivos", [])}
    for s in g.estado["abas"].get("iv_sessoes_video", []):
        m = A.URL.match(str(s.get("url_video") or ""))
        if m:
            citados.add((m.group("bucket"), m.group("caminho")))
    if (bucket, caminho) not in citados:
        return jsonify(erro="Esse caminho não está no inventário do SSO."), 400
    arq = request.files.get("arquivo")
    if arq is None:
        return jsonify(erro="Faltou o arquivo."), 400
    try:
        r = A.guardar(current_app.config, bucket, caminho, arq.stream, sobrescrever=True, do_inventario=True)
    except A.Recusado as e:
        return jsonify(erro=str(e)), 400
    return jsonify(bucket=bucket, caminho=caminho, mb=round(r["bytes"] / E.MB, 1))

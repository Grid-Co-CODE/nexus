# -*- coding: utf-8 -*-
"""A tela Coletas da torre Performance (11/11/2026): só as rotas. A regra mora em `nexus/performance/coletas/` (leia o
CLAUDE.md de lá).

A tela é a do Conversor Grid Co. (o .exe do backoffice), numa moldura: `/coletas` é a casca do Nexus com o "!" e a
moldura; `/coletas/app` é a página do Conversor, que pede ao servidor o que a janela do .exe pedia ao Python
(`/coletas/api/<método>`, a mesma lista de métodos). Nada daqui grava no banco nem nos BDs: a saída é a planilha para
colar, como no .exe.
"""
import json
import os
import tempfile
import uuid

from flask import Response, abort, current_app, render_template, request, send_file, session

from ...cadastro.ligacoes import pasta_dados
from ...dados.conexao import SemBanco, base_de
from ...performance.coletas import pg, servico
from . import TORRE, bp

# Os métodos que a página do Conversor chama (os mesmos da Api do app.py do .exe, sem os da janela do Windows)
METODOS = {"estado", "responder_usina", "separar", "dado_bruto", "remover", "limpar", "reler_bds", "converter",
           "novo_lote", "lote_pronto", "furos_mural"}


def _pasta(*partes):
    try:
        base = pasta_dados(current_app.config)
    except RuntimeError:                       # teste sem pasta de dados: a temporária do teste
        base = current_app.config.get("NEXUS_COLETAS_TMP") or os.path.join(tempfile.gettempdir(), "nexus_coletas_teste")
    p = os.path.join(str(base), "coletas", *partes)
    os.makedirs(p, exist_ok=True)
    return p


def _fabrica_do_banco(app):
    """O banco para a leitura em fundo (fora do pedido): a sessão HTTP que o app instalou. No teste, sem ela, `SemBanco`
    (teste nunca vai à rede), salvo o banco dublado em `NEXUS_COLETAS_BANCO`."""
    def fabrica():
        dublado = app.config.get("NEXUS_COLETAS_BANCO")
        if dublado is not None:
            return dublado()
        s = app.extensions.get("nexus_dados_sessao")
        if s is None and app.config.get("TESTING"):
            raise SemBanco("teste sem banco")
        if s is None:
            import requests
            s = requests.Session()
        return pg.Banco(base_de(app.config), s)
    return fabrica


def _minha():
    chave = session.get("coletas_id")
    if not chave:
        chave = session["coletas_id"] = uuid.uuid4().hex      # uma por navegador: nada de e-mail na chave
    app = current_app._get_current_object()
    return servico.sessao_de(chave, _fabrica_do_banco(app), raiz_temp=app.config.get("NEXUS_COLETAS_TMP"),
                             formatos_novos=_pasta("formatos_novos"))


def _json(d, status=200):
    """O resultado do motor tem data e namedtuple: vai como texto (o pywebview do .exe fazia o mesmo)."""
    return Response(json.dumps(d, ensure_ascii=False, default=str), status=status, mimetype="application/json")


@bp.route("/coletas")
def coletas():
    return render_template("performance/coletas.html", torre=TORRE, tela=TORRE.tela("coletas"))


@bp.route("/coletas/app")
def coletas_app():
    return render_template("performance/coletas_app.html", tela=TORRE.tela("coletas"))


@bp.route("/coletas/api/<metodo>", methods=["POST"])
def coletas_api(metodo):
    if metodo not in METODOS:
        abort(404)
    args = (request.get_json(silent=True) or {}).get("args") or []
    s = _minha()
    try:
        if metodo == "estado":
            return _json(s.estado())
        if metodo == "reler_bds":
            s.carregar_bds()
            return _json(s.estado())
        if metodo == "furos_mural":
            return _json(servico.furos_mural(s, _fabrica_do_banco(current_app._get_current_object()),
                                             str(args[0]) if args else ""))
        if metodo == "novo_lote":
            return _json(s.novo_lote())
        if metodo == "lote_pronto":
            return _json(s.lote_pronto(args[0], args[1] if len(args) > 1 else []))
        if metodo == "responder_usina":
            return _json(s.responder_usina(int(args[0]), args[1]))
        if metodo == "separar":
            return _json(s.separar(int(args[0]), (args[1] if len(args) > 1 else None) or None))
        if metodo == "dado_bruto":
            return _json(s.dado_bruto(int(args[0]), *(args[1:4])))
        if metodo == "remover":
            s.remover(int(args[0]))
            return _json(True)
        if metodo == "limpar":
            s.limpar()
            return _json(True)
        if metodo == "converter":
            if not s.pronto.wait(120):
                return _json({"erro": "os BDs ainda estão sendo lidos do banco: espere um pouco e converta de novo"})
            try:
                return _json(s.converter())
            except Exception as e:             # noqa: BLE001 — a tela diz, o log guarda
                current_app.logger.exception("coletas: converter")
                return _json({"erro": "%s: %s" % (type(e).__name__, e)})
    except (LookupError, IndexError, ValueError) as e:
        return _json({"erro": str(e)}, 400)
    abort(404)


@bp.route("/coletas/arquivo", methods=["POST"])
def coletas_arquivo():
    """Um arquivo de um lote (o navegador manda um por pedido: o teto de envio do Nexus vale por arquivo)."""
    f = request.files.get("arquivo")
    if f is None:
        return _json({"erro": "nenhum arquivo"}, 400)
    s = _minha()
    try:
        s.receber(request.form.get("lote"), request.form.get("rel") or f.filename, f, request.form.get("modificado"))
    except LookupError as e:
        return _json({"erro": str(e)}, 400)
    return _json({"ok": True})


@bp.route("/coletas/planilha/<int:i>")
def coletas_planilha(i):
    s = _minha()
    if i < 0 or i >= len(s.saidas) or not os.path.isfile(s.saidas[i]):
        abort(404)
    return send_file(s.saidas[i], as_attachment=True, download_name=os.path.basename(s.saidas[i]))


# ── Furos de coleta (a tela 3): o relatório é gerado fora, e quem tem o mais novo o sobe aqui; todos veem o mesmo ────
def _furos_atual():
    p = _pasta("furos")
    achados = [os.path.join(p, n) for n in os.listdir(p) if n.lower().endswith((".html", ".htm"))]
    return max(achados, key=os.path.getmtime) if achados else None


@bp.route("/coletas/furos")
def coletas_furos():
    return _json(servico.furos_ler(_furos_atual()))


@bp.route("/coletas/furos", methods=["POST"])
def coletas_furos_subir():
    f = request.files.get("arquivo")
    if f is None:
        return _json({"erro": "nenhum arquivo"}, 400)
    texto = f.read().decode("utf-8", "replace")
    try:
        servico._furos.extrair(texto)
    except ValueError as e:
        return _json({"erro": str(e)}, 400)
    nome = servico.nome_seguro(os.path.basename(f.filename or "Furos_Coleta_Performance.html"))
    p = os.path.join(_pasta("furos"), nome)
    with open(p, "w", encoding="utf-8") as g:
        g.write(texto)
    return _json(servico.furos_ler(p))


@bp.route("/coletas/furos/portal")
def coletas_furos_portal():
    """Onde buscar no portal (a aba "Para coletar"): a aba Equipamentos do BD_Performance, do Excel solto ou do banco."""
    try:
        return _json(servico.furos_portal(_minha(), _fabrica_do_banco(current_app._get_current_object())))
    except Exception:                       # noqa: BLE001 — sem o mapa a aba só não diz onde buscar
        current_app.logger.exception("coletas: furos_portal")
        return _json({})


@bp.route("/coletas/furos/html", methods=["POST"])
def coletas_furos_html():
    """O relatório com as confirmações de quem pediu embutidas (o "Salvar HTML com as marcações")."""
    p = _furos_atual()
    if not p:
        abort(404)
    conf = (request.get_json(silent=True) or {}).get("conf") or {}
    try:
        texto = servico._furos.html_com_marcacoes(p, conf if isinstance(conf, dict) else {})
    except ValueError as e:
        return _json({"erro": str(e)}, 400)
    return Response(texto, mimetype="text/html", headers={
        "Content-Disposition": "attachment; filename=\"%s\"" % os.path.basename(p).replace('"', "")})

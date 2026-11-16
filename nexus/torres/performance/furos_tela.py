# -*- coding: utf-8 -*-
"""Furos de coleta (o R01 da analista no Nexus, 16/11/2026): as rotas da aba "Furos de coleta" da tela Coletas. A regra mora em
`nexus/performance/coletas/` (`furos_r01.py` o motor, `furos_fonte.py` de onde vem cada dado, `furos_conf.py` as
validações); leia o CLAUDE.md de lá.

Tudo debaixo de `/coletas/`: vê e valida quem tem a tela Coletas em Base > Acessos (decisão do Levi, 16/11/2026).
"""
import json
import os
import threading

from flask import current_app, render_template, request, session

from ...cos import andamento as AND
from ...performance.coletas import furos_conf as FC
from ...performance.coletas import furos_fonte as FF
from ...performance.coletas import furos_r01 as R
from . import TORRE, bp
from .coletas_tela import _fabrica_do_banco, _json, _pasta

_TRAVA = threading.Lock()
ENVIO_MAX = 8 * 1024 * 1024          # o HTML R01 tem ~0,5 MB; o teto é folga, não convite


def _quem():
    """Quem valida: o nome (ou o e-mail) de quem entrou; a senha de administrador não é uma pessoa."""
    u = session.get("usuario") or {}
    return (u.get("nome") or u.get("email") or "").strip() or "administrador (senha)"


def servico(app=None):
    """A conta dos furos deste Nexus: uma por pasta de dados (no servidor, uma só; o teste troca a pasta a cada caso)."""
    app = app or current_app._get_current_object()
    with app.app_context():
        pasta = _pasta("furos")
    with _TRAVA:
        todos = app.extensions.setdefault("nexus_furos_r01", {})
        s = todos.get(pasta)
        if s is None:
            cos_csv = app.config.get("NEXUS_FUROS_COS_CSV")      # bancada no PC: o CSV exportado da tela Ocorrências

            def ler_cos(_agora):
                if cos_csv:
                    return FF.linhas_cos_csv(cos_csv), "bancada: paradas do CSV " + os.path.basename(cos_csv)
                with app.app_context():
                    return FF.linhas_cos(app.config, AND.agora())
            relogio = app.config.get("NEXUS_FUROS_RELOGIO") or (lambda: AND.agora().replace(tzinfo=None))
            s = todos[pasta] = FF.Servico(pasta, _fabrica_do_banco(app), ler_cos, relogio)
        return s


def _conf():
    return FC.Confirmacoes(_pasta("furos"))


def publico(res):
    return {k: v for k, v in (res or {}).items() if not k.startswith("_")}


@bp.route("/coletas/furos-de-coleta")
def coletas_furos_tela():
    return render_template("performance/coletas_furos.html", torre=TORRE, tela=TORRE.tela("coletas"),
                           motivos=FC.MOTIVOS)


@bp.route("/coletas/furos/r01")
def coletas_furos_r01():
    """Os furos calculados (o JSON do §9.1 do documento da analista) e as validações de todos."""
    s = servico()
    res, rodando = s.resultado()
    try:
        conf, rev = _conf().ler()
    except FC.Ilegivel as e:
        return _json({"erro": str(e)}, 500)
    d = publico(res)
    d.update(pronto=bool(res), calculando=rodando, erro_conta=s.erro, conf=conf, conf_rev=rev, quem=_quem())
    return _json(d)


@bp.route("/coletas/furos/r01/conf")
def coletas_furos_r01_conf():
    try:
        conf, rev = _conf().ler()
    except FC.Ilegivel as e:
        return _json({"erro": str(e)}, 500)
    if request.args.get("rev") == str(rev):
        return _json({"igual": True, "conf_rev": rev})
    return _json({"conf": conf, "conf_rev": rev})


@bp.route("/coletas/furos/r01/conf", methods=["POST"])
def coletas_furos_r01_gravar():
    ops = (request.get_json(silent=True) or {}).get("ops")
    try:
        conf, rev = _conf().aplicar(ops, _quem())
    except FC.Conflito as e:
        return _json({"erro": "Outra pessoa mudou esta validação agora há pouco. A tela trouxe o que está valendo: "
                              "confira e refaça a sua.", "conflito": e.chaves}, 409)
    except ValueError as e:
        return _json({"erro": f"Não gravei: {e}."}, 400)
    except FC.Ilegivel as e:
        return _json({"erro": str(e)}, 500)
    return _json({"conf": conf, "conf_rev": rev})


def importar(nome, texto, quem):
    """O JSON de confirmações da analista ou o HTML R01 (as marcações dele e as paradas que o Nexus não refaz). -> resumo."""
    pasta = _pasta("furos")
    resumo = {"arquivo": nome}
    if texto.lstrip().startswith("<"):
        db, conf = R.ler_html_r01(texto)
        resumo["paradas"] = FC.Congeladas(pasta).importar(R.congelar(db), db.get("gen") or "", nome, quem)
    else:
        try:
            j = json.loads(texto)
        except ValueError as e:
            raise ValueError("o arquivo não é o JSON de confirmações nem o HTML do relatório") from e
        conf = j.get("conf", j) if isinstance(j, dict) else None
    resumo["validacoes"] = FC.Confirmacoes(pasta).importar(conf, quem, nome)
    return resumo


@bp.route("/coletas/furos/r01/importar", methods=["POST"])
def coletas_furos_r01_importar():
    f = request.files.get("arquivo")
    if f is None:
        return _json({"erro": "Nenhum arquivo."}, 400)
    bruto = f.read(ENVIO_MAX + 1)
    if len(bruto) > ENVIO_MAX:
        return _json({"erro": "O arquivo é grande demais para ser as confirmações ou o relatório."}, 400)
    try:
        resumo = importar(os.path.basename(f.filename or "arquivo"), bruto.decode("utf-8-sig", "replace"), _quem())
    except (ValueError, RuntimeError) as e:
        return _json({"erro": f"Não importei: {e}."}, 400)
    except FC.Ilegivel as e:
        return _json({"erro": str(e)}, 500)
    if resumo.get("paradas", {}).get("congelados"):
        servico().refazer()
    conf, rev = _conf().ler()
    return _json({"resumo": resumo, "conf": conf, "conf_rev": rev})

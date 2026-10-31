# os_creator/os_web/rotas_ativos.py
"""Ativos na web — espelho da `steps/ativos.py` (AtivosTab): o catálogo do Fracttal para CONSULTA.

A tela é de leitura: serve para achar o ativo e ver o que já aconteceu nele; "Criar OS" é um atalho para as telas que
já existem. O catálogo vai enxuto ao navegador e o filtro é todo local, como no app (`_aplica`)."""
from __future__ import annotations

from flask import Blueprint, abort, jsonify, render_template, request

import api
import ativos_central
import chamado_insp_spec as ci

from . import ativos_web
from . import rotas
from .rotas import _conta, exige_sessao

bp = Blueprint("os_web_ativos", __name__, url_prefix="/os")


def _todos() -> list:
    return [a for a in (api.load_assets_cached() or []) if isinstance(a, dict) and a.get("code")]


@bp.route("/ativos")
@exige_sessao
def ativos():
    # o título do botão diz o que ele faz nesta máquina: com o leitor do servidor, só os novos (segundos); sem ele, tudo (minutos)
    return render_template("ativos.html", conta=_conta(), aba="criar", tipos_chip=ativos_web.TIPOS_CHIP,
                           limite=ativos_web.LIMITE_TABELA, leitor=ativos_central.leitor_pronto())


@bp.route("/api/ativos/catalogo")
@exige_sessao
def api_catalogo():
    # `?novos=1`: a tela acabou de apertar "Atualizar ativos" (que voltou na hora) e espera a leitura dos novos em curso, até
    # poucos segundos, para a lista já vir com eles
    if request.args.get("novos") == "1":
        api.esperar_os_novos()
    return jsonify({"ativos": [ativos_web.enxuto(a) for a in _todos()], "info": api.assets_cache_info()})


@bp.route("/api/ativos/recentes")
@exige_sessao
def api_recentes():
    """Codes com OS criada nos últimos 30 dias — a tinta verde da tabela (item 11); em 2º plano, como no app."""
    dias = request.args.get("dias", "30")
    try:
        codes = rotas.os_recentes(int(dias) if dias.isdigit() else 30)       # 10 min, igual para todos
    except api.FracttalError:
        raise
    except Exception:                                   # noqa: BLE001 — a tinta é enfeite; a tela já está usável sem ela
        codes = []
    return jsonify({"codes": sorted(codes)})


@bp.route("/api/ativos/<int:aid>")
@exige_sessao
def api_ativo(aid):
    todos = _todos()
    a = next((x for x in todos if x.get("id") == aid), None)
    if not a:
        abort(404)
    try:                                                # marca deduzida do nome / dos irmãos — mesma regra do chamado (item 9)
        marca = ci.descobrir_marca(a, todos) or ""
    except Exception:                                   # noqa: BLE001
        marca = ""
    try:
        inspecao = bool(ci.aceita(a.get("tipo")))
    except Exception:                                   # noqa: BLE001
        inspecao = False
    os_ = ativos_web.os_resumo(api.ultimas_os_do_ativo(a.get("id"), 4, True))     # 4 (Levi, 06/08)
    return jsonify({"ativo": ativos_web.enxuto(a), "marca": marca or "—", "inspecao": inspecao, "os": os_,
                    "destinos": ativos_web.destinos(a, inspecao)})


@bp.route("/api/ativos/atualizar", methods=["POST"])
@exige_sessao
def api_atualizar():
    """O botão "Atualizar ativos" (Levi, 07/08: quem acabou de cadastrar um ativo precisa dele AGORA). Com o leitor do
    servidor pronto (31/10/2026, tarefa 2.3 do canto central), pede os ativos NOVOS por trás e responde na hora (`novos`
    True: a tela pede a lista com `?novos=1`, que espera essa leitura); sem ele (o PC), baixa o catálogo inteiro pelo RPC com
    a sessão de quem clicou (~110 pedidos: a tela avisa que demora). `ativos_de`: de quando é a lista; `recusa`: o motivo, se
    o Fracttal deu uma lista que o catálogo não aceitou (senão "")."""
    antes = len(api.load_assets_cached() or [])
    novos = ativos_central.leitor_pronto()
    depois = api.load_assets_cached(force=True) or []
    return jsonify({"n": len(depois), "delta": len(depois) - antes, "info": api.assets_cache_info(),
                    "recusa": api.aviso_da_recusa(), "ativos_de": api.ativos_de(), "novos": novos})

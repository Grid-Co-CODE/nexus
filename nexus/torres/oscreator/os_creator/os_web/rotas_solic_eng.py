# os_creator/os_web/rotas_solic_eng.py
"""Rotas da Nova solicitação para a ENGENHARIA (06/10/2026). As regras moram no `solic_eng_web`; aqui só a tela, a
cascata e a criação. A OS sai pelo `api.create_work_orders_bulk` — o mesmo caminho da OS de análise
(`api.create_os_analise`): tipo 'Administrativa', só a Classificação 1 'Programada' (pelo nome), as etiquetas REMOTO e
ENGENHARIA (só elas), sem plano e com o título por ativo no `por_ativo`."""
from __future__ import annotations
import datetime as dt

from flask import Blueprint, jsonify, render_template, request

import api

from . import perf_web
from . import solic_eng_web as reg
from .rotas import _conta, exige_sessao

bp = Blueprint("os_web_solic_eng", __name__, url_prefix="/os")
_FMT = "%Y-%m-%dT%H:%M"


def _agora() -> dt.datetime:
    return dt.datetime.now(reg.BRT).replace(second=0, microsecond=0)


@bp.route("/solicitacao/engenharia")
@exige_sessao
def tela():
    assets = api.load_assets_cached()
    agora = _agora()
    # a hora COM segundos: é a base de onde a tela anda o relógio da data mostrada (que o servidor recalcula ao criar)
    agora_s = dt.datetime.now(reg.BRT).strftime(_FMT + ":%S")
    return render_template("solic_eng.html", conta=_conta(), aba="solic",
                           clientes=sorted(perf_web.clientes_reais(assets)), usinas=perf_web.usinas_para(assets, None),
                           agora=agora_s, evento=agora.strftime(_FMT),
                           programada=reg.data_br(reg.data_padrao(agora, False)), dias=reg.DIAS_PADRAO,
                           dias_urgente=reg.DIAS_URGENTE, sub_descricao=reg.SUB_DESCRICAO, rotulo_problema=reg.ROTULO_PROBLEMA)


@bp.route("/api/solicitacao/engenharia/usinas")
@exige_sessao
def api_usinas():
    cliente = (request.args.get("cliente") or "").strip() or None
    return jsonify({"usinas": perf_web.usinas_para(api.load_assets_cached(), cliente)})


@bp.route("/api/solicitacao/engenharia/ativos")
@exige_sessao
def api_ativos():
    ativos = reg.ativos_da_usina(api.load_assets_cached(), (request.args.get("usina") or "").strip(), api._asset_short_name)
    return jsonify({"ativos": ativos, "tipos": [{"tipo": t, "nome": n} for t, n in reg.tipos_de(ativos)]})


@bp.route("/api/solicitacao/engenharia/responsaveis")
@exige_sessao
def api_responsaveis():
    nomes = reg.nomes_configurados()
    if not nomes:
        return jsonify({"pessoas": [], "faltam": [], "configurado": False})
    pessoas, faltam = reg.responsaveis(api.get_responsaveis() or [], nomes)
    return jsonify({"pessoas": pessoas, "faltam": faltam, "configurado": True})


@bp.route("/api/solicitacao/engenharia/criar", methods=["POST"])
@exige_sessao
def api_criar():
    corpo = request.get_json(silent=True) or {}
    por_id = {str(a.get("id")): a for a in (api.load_assets_cached() or []) if isinstance(a, dict)}
    # o responsável é conferido de novo AQUI: a lista da tela é só a primeira barreira
    permitidos, _ = reg.responsaveis(api.get_responsaveis() or [], reg.nomes_configurados())
    ativos, c, erro = reg.montar(corpo, por_id, permitidos, _agora(), api.perf_os_nome)
    if erro:
        return jsonify({"erro": erro}), 400
    # as etiquetas ANTES de criar: REMOTO e ENGENHARIA sempre, e só elas — faltando uma no Fracttal, nenhuma OS sai
    etiquetas, faltam = reg.etiquetas(api.get_labels() or [])
    if faltam:
        return jsonify({"erro": reg.erro_etiquetas(faltam)}), 400
    # só a Classificação 1, pelo NOME (como a OS de análise): nome que não existir no catálogo apenas não entra
    cl = api._classif_ids(reg.CLASSIF_1, "")
    tipo = {"id_c1": cl["id_task_type"], "desc_c1": cl.get("tasks_types_description") or ""} \
        if cl.get("id_task_type") is not None else None
    res = api.create_work_orders_bulk(ativos, c["descricao"], reg.TIPO_TAREFA, [], etiqueta_ids=etiquetas,
                                      id_responsible=c["id_responsible"], responsible_code=c["responsible_code"],
                                      responsible_name=c["responsible_name"], note=c["note"], tipo=tipo,
                                      event_date=c["event_date"], prog_date=c["prog_date"], por_ativo=c["por_ativo"])
    out = reg.mensagem(res, ativos, c["prog_date"])
    return jsonify(out), (200 if out["ok"] else 400)

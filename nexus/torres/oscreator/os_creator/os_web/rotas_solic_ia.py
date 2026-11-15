# os_creator/os_web/rotas_solic_ia.py
"""Rotas do Pedir com IA (15/11/2026): a tela da conversa e o preencher. As regras moram no `solic_ia`; quem CRIA é a rota de
cada setor, chamada pela tela com a ficha conferida: a Nova solicitação do PCM (`/os/api/solic/criar`) e a da Performance e
da Engenharia (`/os/api/solicitacao/<setor>/criar`, com `origem: "ia"` para a data de 6 dias e as subtarefas da ficha)."""
from __future__ import annotations

from flask import Blueprint, jsonify, redirect, request

import api
import catalogos
import solic_spec as sp

from . import solic_eng_web as reg
from . import solic_ia as IA
from . import solic_web as sw
from . import tradicional_web as trad
from .rotas import exige_sessao

bp = Blueprint("os_web_solic_ia", __name__, url_prefix="/os")


def _chave() -> str:
    try:
        return str(IA.CHAVE() or "").strip() if IA.CHAVE else ""
    except Exception:            # noqa: BLE001 — sem a pasta do Nexus, sem a chave: a tela diz
        return ""


# No Nexus, a ponte diz em cada pedido se o Pedir com IA está liberado para quem pede (em teste, só o administrador; a
# NEXUS_PEDIR_COM_IA=1 libera para todos). O OS Creator sozinho (sem a ponte) não tem a marca: liberado.
IA_LIBERADA = "os_web.ia_liberada"
EM_TESTE = "O Pedir com IA está em teste: por enquanto só os administradores do Nexus o usam."


def _liberada() -> bool:
    v = request.environ.get(IA_LIBERADA)
    return True if v is None else bool(v)


def contexto_ia() -> dict:
    """O que a janela do Pedir com IA precisa nas telas da Nova solicitação (`_solic_ia.html`): sem a chave, ou para quem ela
    ainda não foi liberada, nada aparece."""
    return {"tem_chave": bool(_chave()) and _liberada(), "setores": IA.SETORES, "dias": IA.DIAS, "tipos_sub": IA.TIPOS_SUB,
            "programada": IA.programada(trad.agora_brt()).strftime("%d/%m/%Y")}


@bp.route("/solicitacao/ia")
@exige_sessao
def tela():
    """A janela mora na Nova solicitação (15/11/2026, Levi: "um pouco menor em formato de blur"): este endereço (o cartão do
    Início) abre a do PCM com a janela aberta."""
    return redirect("/os/solicitacao?ia=1")


def _classif1(nome: str) -> dict:
    """{id, txt} da Classificação 1 da SOLICITAÇÃO pelo nome (a do tema; sem tema, a "Programada" de sempre)."""
    try:
        c1 = (catalogos.tipos_solicitacao() or {}).get("classif1") or []
    except api.FracttalError:
        return {}
    alvo = IA.norm(nome or sw.CLASSIF1_PADRAO)
    o = next((x for x in c1 if isinstance(x, dict) and IA.norm(x.get("description")) == alvo), None)
    return {"id": o.get("id"), "txt": o.get("description") or ""} if o else {}


@bp.route("/api/solic/ia/preencher", methods=["POST"])
@exige_sessao
def preencher():
    corpo = request.get_json(silent=True) or {}
    setor = str(corpo.get("setor") or "").strip().lower()
    if not _liberada():
        return jsonify({"erro": EM_TESTE}), 403
    if not IA.setor_de(setor):
        return jsonify({"erro": "Escolha o setor: PCM, Performance ou Engenharia."}), 400
    texto = str(corpo.get("texto") or "").strip()
    if not texto:
        return jsonify({"erro": "Escreva a OS que você precisa."}), 400
    chave = _chave()
    if not chave:
        return jsonify({"erro": IA.SEM_CHAVE, "sem_chave": True}), 503
    assets = api.load_assets_cached() or []
    clientes = trad.clientes(assets)
    usinas = {c: trad.usinas_de(assets, c) for c in clientes}
    temas = sw.temas_para_tela()
    agora = trad.agora_brt()
    anterior = corpo.get("anterior") if isinstance(corpo.get("anterior"), dict) else None
    res = IA.chamar(chave, IA.instrucoes(setor, temas, usinas, agora.date()), IA.mensagem(texto, anterior))
    if res.get("erro"):
        return jsonify({"erro": res["erro"]}), 502
    lido = IA.ler_json(res["texto"])
    if not lido:
        return jsonify({"erro": "A IA respondeu fora do formato. Tente escrever de outro jeito."}), 502
    f = IA.ficha(setor, lido, assets, clientes, lambda c: usinas.get(c) or [],
                 lambda u: reg.ativos_da_usina(assets, u, api._asset_short_name), temas,
                 lambda tema, tipo: sp.de_api(sw.subtarefas_do_tema(tema, tipo)), agora)
    if setor == "pcm":
        f["classif1"] = _classif1(f.get("tema_c1"))
    f["anterior"] = IA.resumo(f)
    return jsonify(f)


@bp.route("/api/solic/ia/ficha", methods=["POST"])
@exige_sessao
def refazer_ficha():
    """A ficha de novo SEM a IA, quando a pessoa troca a usina, o ativo ou o tema na tela: as subtarefas do tema e os temas
    que valem para o tipo do ativo novo (nenhum pedido ao OpenRouter)."""
    corpo = request.get_json(silent=True) or {}
    setor = str(corpo.get("setor") or "").strip().lower()
    if not _liberada():
        return jsonify({"erro": EM_TESTE}), 403
    if not IA.setor_de(setor):
        return jsonify({"erro": "Escolha o setor."}), 400
    assets = api.load_assets_cached() or []
    clientes = trad.clientes(assets)
    usinas = {c: trad.usinas_de(assets, c) for c in clientes}
    ia = {k: corpo.get(k) for k in ("titulo", "descricao", "tema")}
    ia["subtarefas"] = [s for s in corpo.get("extras") or [] if isinstance(s, dict)]
    escolhidos = corpo.get("escolhidos") if isinstance(corpo.get("escolhidos"), dict) else {}
    f = IA.ficha(setor, ia, assets, clientes, lambda c: usinas.get(c) or [],
                 lambda u: reg.ativos_da_usina(assets, u, api._asset_short_name), sw.temas_para_tela(),
                 lambda tema, tipo: sp.de_api(sw.subtarefas_do_tema(tema, tipo)), trad.agora_brt(), escolhidos=escolhidos)
    f["perguntas"] = []                 # a ficha refeita na tela não pergunta de novo: a pessoa está escolhendo nela
    if setor == "pcm":
        f["classif1"] = _classif1(f.get("tema_c1"))
    f["anterior"] = IA.resumo(f)
    return jsonify(f)

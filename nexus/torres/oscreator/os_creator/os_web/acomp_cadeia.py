# os_creator/os_web/acomp_cadeia.py
"""A Inspeção de garantia realizada ganha a OS de acompanhamento que faltou (08/11/2026).

Desenho de 08/11/2026 ("o chamado do tracker na ronda"), com a decisão do Levi no mesmo dia, depois de ver a coluna
"Aguardando a inspeção": "quero que a administrativa só nasça quando a de inspeção é realizada!". A administrativa (tipo
Administrativa, etiqueta CHAMADOS, no nome da equipe de chamados) NÃO nasce junto com a Inspeção: nasce quando ela é
REALIZADA (em verificação ou concluída), com as respostas do técnico na nota, como sempre foi no App.
- O App cria a dele no fechamento da Inspeção que ele mesmo abriu, na hora (a v332, sem mudança).
- Faltava a de toda outra Inspeção de garantia realizada: a do supervisor (criada pelo OS Creator, que nunca ganhava) e a
  fechada na web do Fracttal. Quem cria é o OS Creator (`criar_as_que_faltam`): a Inspeção de garantia realizada há mais
  de `ESPERA_S` sem administrativa ganha uma, filha dela, com a nota e a subtarefa do ticket do pacote
  (`montar_acompanhamento` com as respostas lidas do Fracttal: a nota igual à do App). A espera dá a vez ao App: a dele
  nasce no fechamento e entra na lista central antes disso.
- A CHAVE é o nº da Inspeção: a administrativa que já existe (a da lista central, que aponta a Inspeção na nota, ou a do
  registro das que este OS Creator criou, `criadas`) não nasce de novo. Cada uma é conferida ao vivo antes (o status da
  Inspeção), e falhou fica anotada com o motivo (`pendentes`) e é tentada de novo na volta seguinte.
- QUANDO RODA: na abertura do quadro do Acompanhamento de chamados (`rotas_acomp._andar_junto`), por trás, no máximo a cada
  10 min por processo e até `POR_VEZ` criações, com a sessão de quem abriu (a credencial da empresa só lê). Só no servidor
  isso acha alguma coisa: é lá que a lista central de OS está fresca.
- SÓ AS REALIZADAS A PARTIR DE `a_partir_de()`: ligar não pode criar administrativa para as Inspeções antigas que nunca
  tiveram uma. Sem a data, nada se cria.
DESLIGADO por padrão (`LIGADO_PADRAO`; `OS_WEB_ACOMP_NA_INSPECAO=1` liga numa máquina, `OS_WEB_ACOMP_A_PARTIR_DE` dá a
data): liga o Levi, depois da prova no TESTE - PA.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import threading
import time

import api
from chamado_garantia import montar_acompanhamento
from chamado_garantia import regras as cg_regras

from . import acomp_web as aw

LIGADO_PADRAO = False
A_PARTIR_DE = ""                # AAAA-MM-DD: só as Inspeções realizadas deste dia (Brasília) em diante; vazio = nenhuma
ENV, ENV_DATA = "OS_WEB_ACOMP_NA_INSPECAO", "OS_WEB_ACOMP_A_PARTIR_DE"
DURACAO_S = 900                 # a da administrativa (a do App; a tarefa é escrever o ticket)
ESPERA_S = 30 * 60              # depois do fim da Inspeção: a administrativa do App (no fechamento) chega à lista antes
POR_VEZ = 3                     # criações no Fracttal por volta (a cota é da empresa)
REFAZ_MAX = 10                  # tentativas de uma pendente antes de ela sair da fila (segue anotada)
_BRT = dt.timezone(dt.timedelta(hours=-3))
log = logging.getLogger(__name__)
_TRAVA = threading.Lock()
_PASTA = {"pasta": None}
_FEITOS: dict = {}              # {nº da Inspeção: quando} nesta memória: a mesma não é tentada de novo por 1 h


def ligado() -> bool:
    v = str(os.environ.get(ENV) or "").strip()
    if v in ("0", "1"):
        return v == "1"
    return LIGADO_PADRAO


def a_partir_de() -> dt.date | None:
    v = str(os.environ.get(ENV_DATA) or A_PARTIR_DE or "").strip()
    try:
        return dt.date.fromisoformat(v) if v else None
    except ValueError:
        return None


def configurar_pasta(pasta) -> None:
    """Onde moram as pendentes e o registro das criadas (a ponte liga, ao lado da cópia do quadro); None = só a memória."""
    with _TRAVA:
        _PASTA["pasta"] = pasta or None
        _PASTA.pop("pendentes", None)
        _PASTA.pop("criadas", None)


# ── os dois arquivos: as pendentes e as criadas ─────────────────────────────────────────────────────────────────────────
def _ler(nome: str) -> dict:
    with _TRAVA:
        if nome in _PASTA:
            return json.loads(json.dumps(_PASTA[nome]))
        p, d = _PASTA.get("pasta"), {}
        arq = os.path.join(p, "acomp_%s.json" % nome) if p else None
        if arq and os.path.exists(arq):
            try:
                with open(arq, encoding="utf-8") as f:
                    d = json.load(f) or {}
            except Exception:                   # noqa: BLE001 — o arquivo que não abre não derruba a tela
                log.exception("Acompanhamento: o arquivo %s não abre", nome)
                d = {}
        _PASTA[nome] = d
        return json.loads(json.dumps(d))


def _gravar(nome: str, d: dict) -> None:
    with _TRAVA:
        _PASTA[nome] = d
        p = _PASTA.get("pasta")
        if not p:
            return
        arq = os.path.join(p, "acomp_%s.json" % nome)
        try:
            os.makedirs(p, exist_ok=True)
            with open(arq + ".tmp", "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=1)
            os.replace(arq + ".tmp", arq)
        except Exception:                       # noqa: BLE001
            log.exception("Acompanhamento: o arquivo %s não foi gravado", nome)


def pendentes() -> dict:
    """{nº da Inspeção: {motivo, quando, tentativas}}: as que falharam e são tentadas de novo."""
    return _ler("pendentes")


def criadas() -> dict:
    """{nº da Inspeção: {folio, id}}: as administrativas que ESTE OS Creator criou (o jeito do App, que guarda a dele no
    registro do chamado): a chave mesmo quando a lista central atrasa."""
    return _ler("criadas")


def _anotar(folio_insp: str, motivo: str) -> None:
    d = pendentes()
    p = d.get(folio_insp) or {"tentativas": 0}
    p.update(motivo=str(motivo)[:300], quando=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
             tentativas=int(p.get("tentativas") or 0) + 1)
    d[folio_insp] = p
    _gravar("pendentes", d)


def _resolver(folio_insp: str) -> None:
    d = pendentes()
    if d.pop(folio_insp, None) is not None:
        _gravar("pendentes", d)


def _registrar_criada(folio_insp: str, folio_adm, id_adm) -> None:
    d = criadas()
    d[str(folio_insp)] = {"folio": str(folio_adm or ""), "id": id_adm}
    if len(d) > 5000:                           # as mais antigas saem (o nº cresce com a criação)
        for k in sorted(d, key=lambda x: int(x) if str(x).isdigit() else 0)[:len(d) - 5000]:
            d.pop(k, None)
    _gravar("criadas", d)


# ── a lista central ───────────────────────────────────────────────────────────────────────────────────────────────────
def _lista():
    try:
        import os_central
        return os_central.atual()
    except Exception:                           # noqa: BLE001 — sem a lista, ninguém acha nada (e não se cria às cegas)
        return None


def _nomes(r) -> set:
    return {aw._norm(e[1] if isinstance(e, (tuple, list)) else e) for e in (r.get("etiquetas") or ())}


def eh_inspecao_de_garantia(r) -> bool:
    return (aw._norm(r.get("tipo_tarefa")) == aw._norm(cg_regras.TIPO_TAREFA)
            and aw._norm(cg_regras.ETIQUETA) in _nomes(r))


def _eh_acompanhamento(r) -> bool:
    return aw._norm(cg_regras.ETIQUETA_ACOMPANHAMENTO) in _nomes(r) and aw.eh_os3(r)


def com_administrativa(lista) -> set:
    """Os nº das Inspeções que já têm administrativa não cancelada na lista central (a nota dela aponta a Inspeção)."""
    out = set()
    for r in lista.ordem:
        if r.get("status_id") != 4 and _eh_acompanhamento(r):
            f = str(aw.ler_nota(r.get("note")).get("inspecao") or "")
            if f:
                out.add(f)
    return out


def _fim(r) -> dt.datetime | None:
    v = str(r.get("data_fim") or "").strip()
    if not v:
        return None
    try:
        d = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def faltando(lista, agora: dt.datetime, desde: dt.date) -> list:
    """As Inspeções de garantia realizadas (em verificação ou concluídas) de `desde` em diante, terminadas há mais de
    `ESPERA_S`, sem administrativa (na lista e no registro das criadas), da mais antiga para a mais nova."""
    tem, reg = com_administrativa(lista), criadas()
    out = []
    for r in lista.ordem:
        if r.get("status_id") not in (2, 3) or not eh_inspecao_de_garantia(r):
            continue
        f, fim = str(r.get("folio") or ""), _fim(r)
        if not f or f in tem or f in reg or fim is None:
            continue
        if fim.astimezone(_BRT).date() < desde or (agora - fim).total_seconds() < ESPERA_S:
            continue
        out.append(r)
    out.sort(key=lambda r: (_fim(r), str(r.get("folio"))))
    return out


# ── criar ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
_RX_MARCA = re.compile(r"Inspe[cç][aã]o para chamado\s+(.+?)\s*$", re.I)


def marca_do_titulo(titulo) -> str:
    """O fabricante do título da Inspeção ("[Tracker 10] - Inspeção para chamado STI": o `chamado_insp_spec.titulo`)."""
    m = _RX_MARCA.search(str(titulo or ""))
    return m.group(1).strip() if m else ""


def _respostas(det: dict) -> list:
    return [(s.get("descricao"), s.get("resposta")) for s in (det.get("subtarefas") or [])
            if str(s.get("resposta") or "").strip() and s.get("resposta") != "Não / pendente"]


def _nome_ativo(asset: dict, det: dict) -> str:
    return ((str(asset.get("description") or "").split("{")[0]).strip()[:60]
            or str(asset.get("code") or det.get("code") or ""))


def criar(r_insp) -> dict:
    """A administrativa de UMA Inspeção realizada (o registro da lista central). Confere ao vivo que ela segue realizada,
    lê as respostas e o cabeçalho, e cria. → {"ok", "folio", "id_work_order", "aviso"} ou {"ok": False, "erro"} (a
    pendente fica anotada). Nunca levanta."""
    folio, idwo = str(r_insp.get("folio") or ""), r_insp.get("id")
    try:
        st = api.status_da_os(idwo)
        if st not in (2, 3):
            return {"ok": False, "erro": "a Inspeção %s não está mais realizada (status %s)" % (folio, st),
                    "pulou": True}
        rid, nome = aw.equipe()
        if not rid:
            _anotar(folio, "sem a equipe de chamados configurada (OS_WEB_CHAMADO_RESP_ID)")
            return {"ok": False, "erro": "sem a equipe de chamados configurada"}
        det = api.get_os_detalhes(idwo) or {}
        code = str(r_insp.get("code") or det.get("code") or "").strip()
        asset = next((a for a in (api.load_assets_cached() or []) if str(a.get("code") or "") == code), None)
        if asset is None:
            _anotar(folio, "o ativo %s não está no catálogo" % (code or "?"))
            return {"ok": False, "erro": "o ativo %s não está no catálogo" % (code or "?")}
        marca = marca_do_titulo(det.get("descricao") or r_insp.get("descricao"))
        d = montar_acompanhamento({"folio": folio, "code": code, "nome_ativo": _nome_ativo(asset, det),
                                   "tipo": asset.get("tipo"), "os_pai": str(det.get("os_pai") or ""),
                                   "event_date": det.get("event_date") or r_insp.get("event_date")},
                                  marca, _respostas(det))
        plano = {"id_task": None, "subtasks": api._rpc_subtasks(d["subtarefas"]), "description": d["titulo"],
                 "tasks_types_main_description": d["tipo_tarefa"],
                 "id_task_type_main": api.TASK_TYPE_MAIN.get(d["tipo_tarefa"]), "duration": DURACAO_S,
                 "id_priorities": 2}
        agora = dt.datetime.now(dt.timezone.utc)
        r = api.create_planned_os(asset, plano, id_responsible=rid, responsible_name=nome, event_date=agora,
                                  prog_date=agora, id_parent=idwo, descricao=d["titulo"], note=d["nota"],
                                  linkar_plano=False)
    except Exception as e:                      # noqa: BLE001 — anotada; a volta seguinte tenta de novo
        log.exception("Acompanhamento: a administrativa da Inspeção %s não foi criada", folio)
        _anotar(folio, "%s: %s" % (type(e).__name__, str(e)[:200]))
        return {"ok": False, "erro": str(e)[:200]}
    avisos = [str(r["aviso"])] if r.get("aviso") else []
    lid = api.label_id_por_nome(cg_regras.ETIQUETA_ACOMPANHAMENTO)
    if r.get("id_work_order") and lid:
        try:
            api.apply_labels(r["id_work_order"], [lid])
        except Exception as e:                  # noqa: BLE001 — a OS existe; a etiqueta é o que falta
            avisos.append("a etiqueta %s não foi aplicada: %s" % (cg_regras.ETIQUETA_ACOMPANHAMENTO, str(e)[:120]))
    elif r.get("id_work_order"):
        avisos.append("a etiqueta %s não existe no Fracttal" % cg_regras.ETIQUETA_ACOMPANHAMENTO)
    _registrar_criada(folio, r.get("wo_folio"), r.get("id_work_order"))
    _resolver(folio)
    try:
        from . import lista_central
        lista_central.criadas(r)
    except Exception:                           # noqa: BLE001 — a próxima faixa traz
        log.exception("Acompanhamento: a administrativa não entrou na lista central na hora")
    return {"ok": True, "folio": r.get("wo_folio"), "id_work_order": r.get("id_work_order"), "aviso": "; ".join(avisos)}


def criar_as_que_faltam(agora: dt.datetime | None = None, limite: int = POR_VEZ) -> dict:
    """Uma volta: até `limite` administrativas para as Inspeções realizadas que ficaram sem. → {"criadas": [(nº da
    Inspeção, nº da administrativa)], "erros": [texto], "faltam": n} ou {"pulou": motivo}."""
    if not ligado():
        return {"pulou": "desligado"}
    desde = a_partir_de()
    if desde is None:
        return {"pulou": "sem a data de início (%s)" % ENV_DATA}
    lista = _lista()
    if lista is None or not lista.marca:
        return {"pulou": "a lista central de OS não está neste processo"}
    agora = agora or dt.datetime.now(dt.timezone.utc)
    pend = pendentes()
    alvo = [r for r in faltando(lista, agora, desde)
            if int((pend.get(str(r.get("folio"))) or {}).get("tentativas") or 0) < REFAZ_MAX
            and not (time.monotonic() - _FEITOS.get(str(r.get("folio")), -1e9) < 3600)]
    out = {"criadas": [], "erros": [], "faltam": len(alvo)}
    for r in alvo[:limite]:
        _FEITOS[str(r.get("folio"))] = time.monotonic()
        res = criar(r)
        if res.get("ok"):
            out["criadas"].append((str(r.get("folio")), res.get("folio")))
            if res.get("aviso"):
                out["erros"].append("administrativa %s: %s" % (res.get("folio"), res["aviso"]))
        elif not res.get("pulou"):
            out["erros"].append("a administrativa da Inspeção %s não foi criada: %s" % (r.get("folio"), res.get("erro")))
    return out

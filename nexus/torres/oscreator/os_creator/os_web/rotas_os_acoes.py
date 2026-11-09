# os_creator/os_web/rotas_os_acoes.py
"""As AÇÕES do card de detalhe da OS na web — o que no desktop são os botões do `steps/os_detalhe.py` e os diálogos
`steps/cancelar_os.py`, `steps/os_fluxo.py`, `steps/galeria.py` e `steps/documentos.py`.

Toda escrita passa pela MESMA função do `api.py` que o desktop chama, com os MESMOS argumentos (o comentário em cada
rota aponta a linha do desktop). As rotas devolvem JSON sob `/os/api/os/<wid>/...`; o JS (`static/os_acoes.js`) confirma
antes de escrever e recarrega o fragmento do card (`/os/os/<wid>?parcial=1`) ao terminar. Erro do Fracttal sobe para o
`app_errorhandler` do rotas.py (sessão morta → 401 com `login`; recusa → 502 com a mensagem)."""
from __future__ import annotations
import logging
import mimetypes
import os
import secrets
import tempfile
import threading
import time
from urllib.parse import quote

from flask import Blueprint, Response, jsonify, render_template, request, send_file, session

import api
import ativos_central

from . import lista_central
from . import os_acoes_web as regra
from . import solic_eng_web as regra_anexo
from . import rotas as _rotas
from . import tradicional_web as trad
from .rotas import exige_sessao

log = logging.getLogger(__name__)

bp = Blueprint("os_web_os_acoes", __name__, url_prefix="/os")


# ── o que o template do card precisa e o `rotas.os_detalhe` não passa (ele não é deste pacote) ────────────────
@bp.app_template_global("acoes_nota_regra")
def _tg_nota_regra(d, status):
    """(pode, motivo) do botão Editar da observação — a regra do card do app, com o status que a web conhece."""
    return regra.nota_pode_editar(regra.status_id_de(status, d), len((d or {}).get("tarefas") or []))


@bp.app_template_global("acoes_sem_fim")
def _tg_sem_fim(d):
    return regra.tarefas_sem_fim((d or {}).get("tarefas"))


@bp.app_template_global("acoes_tarefas_pendentes")
def _tg_tarefas_pendentes(d):
    """As tarefas da OS com subtarefa em branco — é por elas que o "fazer a tarefa" é oferecido."""
    return regra.tarefas_pendentes(d)


@bp.app_template_global("acoes_grupos_tarefas")
def _tg_grupos_tarefas(d):
    """As tarefas da OS, cada uma com as subtarefas dela ([] com uma tarefa só) — o card de uma OS de várias tarefas
    (Levi, 08/10/2026: "tem que dividir por tarefa quando clicar!")."""
    return regra.subtarefas_por_tarefa(d)


@bp.app_template_global("acoes_rotulos_tarefas")
def _tg_rotulos_tarefas(d):
    """{id da tarefa: o nome que a distingue das outras} — a pendência do Concluir diz de qual tarefa é."""
    return regra.rotulos_tarefas((d or {}).get("tarefas"))


@bp.app_template_global("acoes_anexo_aceitar")
def _tg_anexo_aceitar():
    """O accept do seletor do Incluir anexo: os tipos dos anexos da Solicitação de Engenharia."""
    return regra_anexo.ACEITAR


@bp.app_template_global("acoes_anexo_regra")
def _tg_anexo_regra():
    return "%s · até %d MB cada, %d por vez · ou cole com Ctrl+V" % (
        regra_anexo.tipos_aceitos(), regra_anexo.MAX_MB_ARQUIVO, regra_anexo.MAX_ARQUIVOS)


def _corpo() -> dict:
    return request.get_json(silent=True) or {}


def _erro(msg, status=400):
    return jsonify({"erro": str(msg)}), status


# ── leituras ──────────────────────────────────────────────────────────────────────────────────────────
@bp.route("/api/os/<int:wid>/fluxo")
@exige_sessao
def api_fluxo(wid):
    # os_fluxo.py:139 — ApiWorker(api.fluxo_da_os, self._wo, 0): 0 = sem o histórico do ativo (só a cadeia, Levi 06/08)
    return jsonify(regra.fluxo_web(api.fluxo_da_os(wid, 0) or {}, api.fmt_data_br))


def _email() -> str:
    return str((session.get("conta") or {}).get("email") or "").strip().lower()


_LISTA_TTL = 180


def _anexos_da_os(wid, forcar=False):
    """(subs, oss) — as duas chamadas do `_carregar` do card (get_os_subtarefa_anexos + get_os_anexos), guardadas 3 min
    POR PESSOA. A lista sempre vem nova (`forcar`); quem reaproveita é o "Baixar todos" logo depois de abrir os anexos:
    cada arquivo de subtarefa custa um s3_object_get, e o limite do Fracttal é de 200/min para a EMPRESA inteira.
    As duas listas vão ao mesmo tempo (08/10/2026): uma não depende da outra."""
    def _ler():
        with api._ExecutorComContexto(max_workers=2) as ex:
            f_subs, f_oss = ex.submit(api.get_os_subtarefa_anexos, wid), ex.submit(api.get_os_anexos, wid)
            return f_subs.result() or [], f_oss.result() or []
    return _rotas._memo(("anexos", _email(), int(wid)), _LISTA_TTL, _ler, forcar=forcar)


@bp.route("/api/os/<int:wid>/anexos-lista")
@exige_sessao
def api_anexos_lista(wid):
    """Imagens, documentos e notas dos dois cards (verde = das subtarefas, azul = da OS), já com a URL pré-assinada que o
    api resolve e o link que a renova — as duas chamadas do `_carregar` do card (get_os_subtarefa_anexos + get_os_anexos)."""
    subs, oss = _anexos_da_os(wid, forcar=True)
    return jsonify(regra.anexos_web(subs, oss, wid))


def _nomes_na_os(wid) -> set:
    """Os nomes dos arquivos que a OS já tem (o fim da chave `.ot/<OS>/<nome>` no S3), sem pedir as URLs pré-assinadas:
    só o nome importa aqui, e cada URL seria um pedido a mais na cota da empresa."""
    with api.enxuta("url"):
        listas = [api.get_os_subtarefa_anexos(wid) or [], api.get_os_anexos(wid) or []]
    return {(str(a.get("value") or "").rsplit("/", 1)[-1] or str(a.get("nome") or "")).lower()
            for lista in listas for a in lista if isinstance(a, dict)} - {""}


# Incluir anexo numa OS que já existe (Levi, 06/11/2026: "poderia incluir um botão de incluir anexo? Aí incluiria um anexo
# na OS e será possível ver o anexo e baixar os anexos conforme já temos quando clicamos na OS no histórico de OS"), no
# card e nas páginas da OS (a da Engenharia e a do chamado de Garantias). As regras e o envio são os dos anexos da
# Solicitação de Engenharia, em produção desde 29/10/2026 (`solic_eng_web.anexos`: o tipo conferido pelo conteúdo, 10 MB
# cada, 20 MB juntos, 5 por vez; `solic_eng_web.anexar`: o S3 do Fracttal e a 1ª tarefa da OS). O que uma OS existente
# pede a mais: o nome que já está nela ganha " (2)" (a chave no S3 é `.ot/<OS>/<nome>`, e o novo apagaria o antigo), e os
# anexos são relidos depois do envio: o que não aparece na OS não subiu (o Fracttal aceita calado).
@bp.route("/api/os/<int:wid>/anexos", methods=["POST"])
@exige_sessao
def api_anexos_incluir(wid):
    try:
        request.max_content_length = regra_anexo.LIMITE_PEDIDO   # só esta rota abre (o app aceita 4 MB por pedido)
    except AttributeError:
        pass
    folio = "".join(ch for ch in str(request.form.get("folio") or "") if ch.isdigit())[:12] or str(int(wid))
    brutos = [(f.filename or "", f.read()) for f in request.files.getlist("anexos")]
    ok, erro = regra_anexo.anexos(brutos, nada=" Nenhum anexo foi incluído.")
    if erro:
        return _erro(erro)
    if not ok:
        return _erro("Escolha o arquivo para anexar à OS.")
    # o anexo de UMA tarefa (06/11/2026: "Botão de anexar na tarefa"), que tem de ser da OS; sem ela, a 1ª tarefa
    tarefa = str(request.form.get("tarefa") or "").strip()
    if tarefa and not _tarefa_da_os(wid, tarefa):
        return _erro("Esta tarefa não é da OS.", 404)
    vistos = _nomes_na_os(wid)
    for a in ok:
        a["nome"] = regra_anexo._sem_repetir(a["nome"], vistos)
    tarefas = (lambda _w: [int(tarefa)]) if tarefa else api._ids_tarefas_da_os
    with api._ExecutorComContexto(max_workers=regra_anexo.ENVIOS_PARALELOS) as ex:
        res = regra_anexo.anexar([{"folio": folio, "id_work_order": wid}], ok, api.attach_imagem_os, tarefas,
                                 mapa=ex.map)
    na_os = _nomes_na_os(wid)
    incluidos, falhas = [], []
    for r in res:
        if r["ok"] and r["nome"].lower() in na_os:
            incluidos.append(r["nome"])
        else:
            falhas.append({"nome": r["nome"], "motivo": "; ".join(m for _, m in r["falhas"])
                           or "o Fracttal aceitou o envio, mas o anexo não apareceu na OS"})
    nao = "; ".join("%s (%s)" % (f["nome"], f["motivo"]) for f in falhas)
    if not incluidos:
        texto = "Nenhum anexo foi incluído na OS %s: %s." % (folio, nao)
    else:
        n = len(incluidos)
        texto = ("1 anexo incluído" if n == 1 else "%d anexos incluídos" % n) + " na OS %s." % folio
        texto += " Não subiu: %s." % nao if falhas else ""
    return jsonify({"ok": not falhas, "mensagem": texto, "incluidos": incluidos, "falhas": falhas}), \
        200 if incluidos else 502


def _falha_anexo(msg: str, status: int):
    """O erro do Abrir e do Baixar de um anexo (09/11/2026, OS 8159: o Abrir mostrava '{"erro":"Falha ao baixar a imagem
    (HTTP 404)."}' e o Baixar salvava esse JSON como arquivo). Aberto numa aba (o Abrir, `abrir=1`), a página de aviso do OS
    Creator; pedido pela tela (o Baixar, que pede JSON e não salva o erro), o JSON de sempre."""
    if request.args.get("abrir") and "application/json" not in (request.headers.get("Accept") or ""):
        return render_template("erro.html", conta=session.get("conta") or {}, aba="", mensagem=msg), status
    return _erro(msg, status)


@bp.route("/api/os/<int:wid>/anexo")
@exige_sessao
def api_anexo_baixar(wid):
    """'Baixar' de um anexo: RENOVA a URL pré-assinada (companies.s3_object_get) e devolve os bytes como download.

    Por quê renovar em vez de mandar a URL da lista: a URL do Fracttal expira, e no desktop o remédio era 'reabrir os
    anexos renova' (documentos.py). Aqui o clique já renova. Os bytes vêm pelo `api.baixar_imagem` — a mesma
    requisição sem cabeçalhos de auth do S3 que a galeria usa (documentos.py faz o mesmo GET por conta própria)."""
    value = (request.args.get("value") or "").strip()
    if not value:
        return _falha_anexo("Este anexo não tem arquivo no Fracttal.", 404)
    nome = regra.fname(request.args.get("nome") or "") or regra.fname(value) or "anexo"
    url = api.s3_get_url(value)
    if not url:
        return _falha_anexo("Não consegui renovar o link deste anexo no Fracttal (reabra os anexos e tente de novo).", 404)
    try:
        dados = api.baixar_imagem(url)
    except api.SessionExpired:
        raise
    except api.FracttalError as e:
        if "HTTP 404" in str(e) or "HTTP 403" in str(e):
            return _falha_anexo("O arquivo \"%s\" não está mais no Fracttal: abra a OS no Fracttal para conferir." % nome, 404)
        return _falha_anexo("Não consegui baixar o anexo \"%s\" do Fracttal agora: tente de novo em instantes." % nome, 502)
    tipo = mimetypes.guess_type(nome)[0] or "application/octet-stream"
    ascii_ = nome.encode("ascii", "ignore").decode() or "anexo"
    # abrir=1: mostra ali mesmo (o PDF no leitor do navegador, a foto na galeria) — o link do anexo que veio sem a
    # pré-assinada (os_acoes_web._item); sem ele, baixa
    modo = "inline" if request.args.get("abrir") else "attachment"
    return Response(dados, mimetype=tipo, headers={
        "Content-Disposition": '%s; filename="%s"; filename*=UTF-8\'\'%s' % (modo, ascii_.replace('"', ""), quote(nome, safe="")),
        "Cache-Control": "private, no-store"})


# ── baixar todos (steps/galeria.py, steps/documentos.py: "Baixar todos (N)") ─────────────────────────────────────────
# Dois passos: o POST junta tudo num .zip no disco e responde quantos vieram e quais não; o GET entrega o arquivo. Num
# passo só a contagem se perderia — o proxy da Plataforma só repassa alguns cabeçalhos —, e um .zip grande ficaria
# inteiro na memória do navegador. O .zip vale 10 minutos, só para quem o pediu.
_ZIPS: dict = {}
_ZIPS_LOCK = threading.Lock()
_ZIP_TTL = 600


def _pasta_zips() -> str:
    p = os.path.join(tempfile.gettempdir(), "os_web_zips")
    os.makedirs(p, exist_ok=True)
    return p


def _varrer_zips(agora: float):
    """Tira os .zip vencidos (os da memória e os que sobraram no disco de um reinício)."""
    with _ZIPS_LOCK:
        for t, z in list(_ZIPS.items()):
            if agora - z["criado"] > _ZIP_TTL:
                _ZIPS.pop(t, None)
    try:
        pasta = _pasta_zips()
        for n in os.listdir(pasta):
            cam = os.path.join(pasta, n)
            if n.endswith((".zip", ".pdf")) and agora - os.path.getmtime(cam) > _ZIP_TTL:   # o PDF da OS mora aqui também
                os.remove(cam)
    except OSError:
        pass                                                         # arquivo ainda sendo entregue: fica para a próxima


def _baixar_anexo(item) -> bytes:
    """Os bytes de um anexo pela pré-assinada da lista; vencida (ou sem ela), renova pelo caminho no S3 e tenta de novo."""
    url = item.get("url")
    if url:
        try:
            return api.baixar_imagem(url)
        except api.FracttalError:
            if not item.get("value"):
                raise
    novo = api.s3_get_url(item.get("value")) if item.get("value") else None
    if not novo:
        raise api.FracttalError("o Fracttal não renovou o link")
    return api.baixar_imagem(novo)


@bp.route("/api/os/<int:wid>/anexos-zip", methods=["POST"])
@exige_sessao
def api_anexos_zip(wid):
    """Junta os anexos de UM card (grupo 'sub' = das subtarefas, 'os' = da OS) num .zip com a arrumação do app:
    `regra.plano_do_zip` (= baixar_em_massa) + `regra.montar_zip`, baixando 6 de cada vez com o contexto da sessão."""
    c = _corpo()
    grupo = str(c.get("grupo") or "")
    if grupo not in ("sub", "os"):
        return _erro("Escolha os anexos: das subtarefas ou da OS.")
    folio = "".join(ch for ch in str(c.get("folio") or "") if ch.isdigit())[:12] or str(int(wid))
    subs, oss = _anexos_da_os(wid)
    # a OS de vários ativos (04/11/2026): o card manda {id da tarefa: ativo}, que vira a pasta e o começo do nome de cada
    # arquivo (só nome de arquivo: o `limpar_nome` tira barra e dois-pontos); com `tarefa`, só os anexos daquela tarefa
    ativos = {str(k)[:20]: str(v)[:80] for k, v in list((c.get("ativos") or {}).items())[:500]} \
        if isinstance(c.get("ativos"), dict) else {}
    tarefa = str(c.get("tarefa") or "").strip()[:20]
    itens = regra.itens_para_baixar(grupo, subs, oss)
    if tarefa:
        itens = [i for i in itens if str(i.get("tarefa")) == tarefa]
    plano = regra.plano_do_zip(itens, ativos)
    if not plano:
        return _erro("Não há anexos para baixar neste card.", 404)
    agora = time.time()
    _varrer_zips(agora)
    token = secrets.token_urlsafe(18)
    caminho = os.path.join(_pasta_zips(), token + ".zip")
    with api._ExecutorComContexto(max_workers=6) as ex:
        r = regra.montar_zip(caminho, plano, _baixar_anexo, mapa=ex.map)
    if not (r["arquivos"] + r["notas"]):
        try:
            os.remove(caminho)
        except OSError:
            pass
        return _erro("Nenhum anexo veio do Fracttal (a URL expira: abra os anexos de novo e tente outra vez).", 502)
    nome = "OS %s - anexos %s.zip" % (folio, "das subtarefas" if grupo == "sub" else "da OS")
    if tarefa and ativos.get(tarefa):
        nome = "OS %s - %s - anexos.zip" % (folio, regra.limpar_nome(ativos[tarefa]))
    with _ZIPS_LOCK:
        _ZIPS[token] = {"caminho": caminho, "nome": nome, "wid": int(wid), "email": _email(), "criado": agora}
    return jsonify({"ok": True, "nome": nome, "url": "/os/api/os/%d/anexos-zip/%s" % (int(wid), token),
                    "arquivos": r["arquivos"], "notas": r["notas"], "bytes": r["bytes"],
                    "falhas": [{"nome": n, "motivo": m} for n, m in r["falhas"]]})


@bp.route("/api/os/<int:wid>/anexos-zip/<token>")
@exige_sessao
def api_anexos_zip_baixar(wid, token):
    with _ZIPS_LOCK:
        z = _ZIPS.get(str(token))
    if (not z or z.get("pdf") or z["wid"] != int(wid) or z["email"] != _email()
            or time.time() - z["criado"] > _ZIP_TTL or not os.path.exists(z["caminho"])):
        return _erro("Este .zip venceu (vale 10 minutos) — clique de novo em Baixar todos.", 404)
    resp = send_file(z["caminho"], mimetype="application/zip", as_attachment=True, download_name=z["nome"], max_age=0)
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


# ── o PDF da OS (Levi, 19/10/2026, em Garantias: "o mesmo PDF que o fractall gera"; a seta de cada OS na cadeia do
# chamado) ─────────────────────────────────────────────────────────────────────────────────────────────────────────
# Como o "Baixar todos": o POST junta o que o Fracttal junta para imprimir (o detalhe, os anexos do card e os recursos),
# baixa as fotos 6 de cada vez, monta o PDF no disco (`os_pdf`) e diz quantas fotos vieram; o GET entrega. O arquivo
# vale 10 minutos, só para quem pediu (o mesmo registro e a mesma pasta dos .zip).
def _recursos_ou_none(wid):
    """Os recursos da OS; None quando o Fracttal não respondeu (o PDF diz que não leu, e não que não há)."""
    try:
        return api.get_os_recursos(wid)
    except api.SessionExpired:
        raise
    except api.FracttalError:
        return None


# as fotos do PDF têm prazo (09/11/2026, OS 8159: "Não consegui montar o PDF... O servidor não respondeu"): a OS com muitas
# fotos baixava todas, 6 de cada vez e até 30 s cada, e o pedido passava do tempo que o caminho até o servidor espera; a
# tela recebia a página de erro do caminho, e não a resposta. Passado o prazo, as fotos que faltam saem no PDF dizendo que
# não vieram (como a foto que o Fracttal não entrega), e o PDF chega
PRAZO_FOTOS_S = 45


@bp.route("/api/os/pdf", methods=["POST"])
@exige_sessao
def api_os_pdf():
    """O PDF de UMA OS: pelo `wid` quando a tela já o sabe, senão pelo nº (`folio`, a OS de campo e a inspeção da
    cadeia do chamado). O erro responde sempre em JSON, com o motivo (09/11/2026: o erro sem JSON virava, na tela, "o
    servidor não respondeu, a gravação pode ter sido feita" no card e "a sua sessão do Nexus acabou" na Aprovação de OS)."""
    try:
        return _os_pdf()
    except api.FracttalError:
        raise                                               # a sessão caída e o erro do Fracttal: o tratador de sempre (JSON)
    except Exception as e:                                  # noqa: BLE001 — o motivo vai à tela e a pilha ao log
        log.exception("PDF da OS: não montou")
        return _erro("Não consegui montar o PDF desta OS (%s): tente de novo em instantes." % type(e).__name__, 500)


def _os_pdf():
    from datetime import datetime

    from . import os_pdf
    c = _corpo()
    folio = "".join(ch for ch in str(c.get("folio") or "") if ch.isdigit())[:12]
    wid = str(c.get("wid") or "").strip()
    wid = int(wid) if wid.isdigit() else None
    if not wid:
        if not folio:
            return _erro("Qual OS? Falta o número.")
        wid = api._wo_id_por_folio(folio)
        if not wid:
            return _erro("Não achei a OS %s no Fracttal." % folio, 404)
    with api._ExecutorComContexto(max_workers=2) as ex:
        f_det = ex.submit(api.get_os_detalhes, wid)
        f_rec = ex.submit(_recursos_ou_none, wid)
        subs, oss = _anexos_da_os(wid)                   # na thread do pedido: a memória dos anexos é por pessoa
        d = f_det.result() or {}
        recursos = f_rec.result()
    if not d.get("folio") and not folio:
        return _erro("Não consegui ler a OS no Fracttal.", 502)
    d.setdefault("folio", folio)
    # o cliente e a usina do ativo, pelo catálogo central (sem catálogo nesta máquina, o PDF sai sem eles: baixá-lo aqui
    # seria ler todos os ativos)
    cat = ativos_central.atual()
    local = cat.local_por_codigo.get(str(d.get("code") or "")) if cat is not None else None
    m = os_pdf.modelo(d, recursos=recursos, anexos_sub=subs, anexos_os=oss, local=local)
    pasta_fotos = os.path.join(api._data_dir(), "os_pdf_fotos")    # a cópia reduzida de cada foto (os_pdf)
    inicio = time.monotonic()

    def _foto(f):
        if time.monotonic() - inicio > PRAZO_FOTOS_S:      # passou do prazo: esta sai no PDF como "não veio"
            return None
        try:
            return os_pdf.reduzir_guardada(_baixar_anexo(f["item"]), pasta_fotos)
        except Exception:                                   # noqa: BLE001 — a que não vem sai no PDF dizendo isso
            return None
    with api._ExecutorComContexto(max_workers=6) as ex:
        fotos = list(ex.map(_foto, m["fotos"]))
    os_pdf.varrer_guardadas(pasta_fotos)
    conta = session.get("conta") or {}
    logo = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "grid-logo.png")
    dados = os_pdf.gerar(m, fotos=fotos, gerado_em=datetime.now(api._BR_TZ).strftime("%d/%m/%Y %H:%M"),
                         quem=str(conta.get("nome") or "").strip(), logo=logo if os.path.exists(logo) else None)
    agora = time.time()
    _varrer_zips(agora)
    token = secrets.token_urlsafe(18)
    caminho = os.path.join(_pasta_zips(), token + ".pdf")
    with open(caminho, "wb") as fh:
        fh.write(dados)
    nome = "OS %s.pdf" % (m["folio"] or folio or wid)
    with _ZIPS_LOCK:
        _ZIPS[token] = {"caminho": caminho, "nome": nome, "wid": int(wid), "email": _email(), "criado": agora, "pdf": True}
    falhas = sum(1 for f in fotos if not f)
    return jsonify({"ok": True, "nome": nome, "url": "/os/api/os/pdf/%s" % token, "bytes": len(dados),
                    "fotos": len(fotos) - falhas, "falhas": falhas})


@bp.route("/api/os/pdf/<token>")
@exige_sessao
def api_os_pdf_baixar(token):
    with _ZIPS_LOCK:
        z = _ZIPS.get(str(token))
    if (not z or not z.get("pdf") or z["email"] != _email() or time.time() - z["criado"] > _ZIP_TTL
            or not os.path.exists(z["caminho"])):
        return _erro("Este PDF venceu (vale 10 minutos): clique de novo na seta da OS.", 404)
    resp = send_file(z["caminho"], mimetype="application/pdf", as_attachment=True, download_name=z["nome"], max_age=0)
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


@bp.route("/api/os/<int:wid>/etiquetas")
@exige_sessao
def api_etiquetas(wid):
    """Catálogo (`get_labels`, como o `_EtiquetasDialog` carrega) + as etiquetas da OS. O card manda as atuais pelos chips
    (`?atuais=1,2` — o desktop também recebe `atuais` do card, sem ir ao servidor); sem o parâmetro, lê a OS."""
    catalogo = [{"id": l.get("id"), "description": str(l.get("description") or "").strip(), "color": regra.cor_hex(l.get("color"))}
                for l in _rotas.etiquetas_fracttal() if isinstance(l, dict) and l.get("id") is not None
                and str(l.get("description") or "").strip()]                 # o `_filtrar` do app pula etiqueta sem descrição
    lista = request.args.get("atuais")
    if lista is not None:
        atuais = [int(x) for x in lista.split(",") if x.strip().isdigit()]
    else:
        atuais = [e.get("id") for e in ((api.get_os_detalhes(wid) or {}).get("etiquetas") or [])
                  if isinstance(e, dict) and e.get("id") is not None]
    return jsonify({"catalogo": catalogo, "atuais": atuais})


@bp.route("/api/os/<int:wid>/cancel-motivos")
@exige_sessao
def api_cancel_motivos(wid):
    # cancelar_os.py:50 — ApiWorker(api.get_cancel_motivos)
    return jsonify({"motivos": _rotas.motivos_cancelamento()})


# ── escritas ──────────────────────────────────────────────────────────────────────────────────────────
@bp.route("/api/os/<int:wid>/responsavel", methods=["POST"])
@exige_sessao
def api_responsavel(wid):
    """Trocar responsável — `TrocarResponsavelDialog._salvar`. Só `id_personnel`: o desktop não manda nota, e o `nota` do
    `mudar_responsavel` vai para o `note` do work_orders_update, que é a OBSERVAÇÃO da OS (ver `editar_nota_os`) —
    mandar algo daqui reescreveria a observação sem a pessoa saber."""
    c = _corpo()
    idp = c.get("id_personnel")
    if not idp:
        return _erro("escolha a pessoa.")
    r = api.mudar_responsavel(wid, idp)                              # os_detalhe.py:331 — (self._wo, p["id_personnel"])
    if not (isinstance(r, dict) and r.get("ok")):
        return _erro((r or {}).get("erro") or "não deu")
    # a OS como ficou entra na lista central de OS na hora (31/10/2026, tarefa 3.3): o Histórico a mostra sem reler o
    # Fracttal ao fechar o card. Lida pela sessão da pessoa; a falha vai ao log e nunca derruba a ação (como em todas abaixo)
    lista_central.mudou(wid)
    # 19/10/2026 (a troca também na tela do chamado): o quadro do Acompanhamento que mostra esta OS sai da memória, senão
    # voltar a ele mostraria o responsável de antes por até 3 min; e `da_equipe` é a cor do nome na tela do chamado, pela
    # regra do quadro. A troca já está no Fracttal: nada daqui vira erro na tela.
    from . import acomp_web, rotas_acomp
    try:
        rotas_acomp.esquecer_se_no_quadro(wid)
    except Exception:                                                  # noqa: BLE001
        pass
    return jsonify({"ok": True, "mensagem": "OS %s agora está com %s." % (c.get("folio") or wid, c.get("name") or "—"),
                    "da_equipe": acomp_web.da_equipe({"id_atribuido": idp, "atribuido_a": c.get("name")})})


@bp.route("/api/os/<int:wid>/etiquetas", methods=["POST"])
@exige_sessao
def api_etiquetas_salvar(wid):
    """Etiquetas — `_EtiquetasDialog._salvar`. `labels_sync` SUBSTITUI o conjunto: o JS manda TODAS as marcadas, não a
    diferença. Vazio não vai (o app pede 'ao menos uma'; o `apply_labels` recusaria de qualquer jeito)."""
    ids = [(int(x) if str(x).strip().isdigit() else x) for x in (_corpo().get("ids") or []) if x not in (None, "")]
    if not ids:
        return _erro("Marque ao menos uma etiqueta (ou Cancelar).")
    r = api.apply_labels(wid, ids)                                   # os_detalhe.py:420 — (self._wo, ids)
    if isinstance(r, dict) and r.get("ok") is False:
        return _erro(r.get("erro") or "não foi possível salvar")
    lista_central.mudou(wid)                                         # a etiqueta é coluna e filtro do Histórico
    return jsonify({"ok": True})


@bp.route("/api/os/<int:wid>/nota", methods=["POST"])
@exige_sessao
def api_nota(wid):
    """Observação da OS — `_nota_salvar`. Antes de gravar, a mesma régua do botão Editar, conferida contra a OS lida
    agora (não contra o que o navegador diz): OS cancelada e OS de várias tarefas não passam, e nada chega ao Fracttal."""
    c = _corpo()
    d = api.get_os_detalhes(wid) or {}
    pode, motivo = regra.nota_pode_editar(regra.status_id_de(c.get("status"), d), len(d.get("tarefas") or []))
    if not pode:
        return _erro(motivo)
    novo = str(c.get("nota") or "").strip()                          # o app grava `toPlainText().strip()`
    r = api.editar_nota_os(wid, novo)                                # os_detalhe.py:1361 — (self._wo, novo)
    if not (isinstance(r, dict) and r.get("ok")):
        return _erro((r or {}).get("erro") or "Não consegui salvar a observação.")
    lista_central.mudou(wid)                                         # a nota com o bloco do chamado é do Garantias
    # a API apara os espaços das pontas — devolver o que ELA gravou, não o que foi digitado
    return jsonify({"ok": True, "nota": r.get("nota", novo)})


@bp.route("/api/os/<int:wid>/concluir", methods=["POST"])
@exige_sessao
def api_concluir(wid):
    """Concluir OS — IRREVERSÍVEL, dois passos dentro do `concluir_os_checado` (status 3 + recalculate) e a reconferência
    da data de fim na volta (`_concluiu`). A confirmação (o `_ConcluirDialog`) é no navegador, antes deste POST."""
    folio = _corpo().get("folio") or wid
    res = api.concluir_os_checado(wid)                               # os_detalhe.py:896 — (self._wo)
    if isinstance(res, dict) and res.get("ok") is False:
        return _erro(res.get("msg") or "Não foi possível concluir.")
    lista_central.mudou(wid)                                         # o status que o Fracttal deu (verificação ou concluída)
    texto, aviso = regra.mensagem_concluida(folio, (res or {}).get("data_fim") if isinstance(res, dict) else None)
    return jsonify({"ok": True, "mensagem": texto, "aviso": aviso,
                    "data_fim": (res or {}).get("data_fim") if isinstance(res, dict) else None})


@bp.route("/api/os/<int:wid>/tarefa/<int:tid>/checklist")
@exige_sessao
def api_checklist(wid, tid):
    """O checklist de UMA tarefa, com o valor que já está lá — o que a janela precisa desenhar."""
    campos = api.subtarefas_da_tarefa(tid)
    return jsonify({"id_tarefa": tid, "id_work_order": wid, "campos": campos,
                    "pendentes": len([c for c in campos if not str(c.get("valor") or "").strip()])})


@bp.route("/api/os/<int:wid>/tarefa/<int:tid>/executar", methods=["POST"])
@exige_sessao
def api_executar(wid, tid):
    """Fazer a tarefa: grava o checklist e lança o registro de execução, NESTA ORDEM.

    A ordem é a da tela do Fracttal e não é indiferente: se o registro fosse primeiro e o checklist
    falhasse, a OS ficaria com horas lançadas para um serviço que não foi registrado — e o
    contrário (checklist gravado, registro falhou) é recuperável, basta lançar o registro de novo.
    """
    c = _corpo()
    valores = c.get("valores") or {}
    campos = api.subtarefas_da_tarefa(tid)
    faltam = regra.faltando_obrigatorias(campos, valores)
    if faltam:
        return _erro(regra.ERRO_OBRIGATORIA % "; ".join(faltam[:4]))
    try:
        ini = trad.data_brt(c.get("inicio"))
    except (ValueError, TypeError):
        return _erro(regra.ERRO_SEM_INICIO)
    if not str(c.get("inicio") or "").strip():
        return _erro(regra.ERRO_SEM_INICIO)
    fim = None
    if str(c.get("fim") or "").strip():
        try:
            fim = trad.data_brt(c.get("fim"))
        except (ValueError, TypeError):
            return _erro("Data de fim inválida.")
        if fim < ini:
            return _erro(regra.ERRO_FIM_ANTES)
    por_id = {str(x.get("id_form_item")): x for x in campos}
    a_gravar = [{"id_form_item": por_id[k]["id_form_item"], "valor": v,
                 "tipo": por_id[k].get("tipo") or 1}
                for k, v in valores.items() if k in por_id and str(v or "").strip()]
    n = 0
    if a_gravar:
        n = (api.salvar_subtarefas(wid, tid, a_gravar) or {}).get("n") or 0
    res = api.registrar_execucao(tid, ini, fim, note=str(c.get("nota") or "").strip())
    if (res or {}).get("confirmado"):
        lista_central.mudou(wid)
    else:
        # sem o registro confirmado, reler a OS seriam 2 pedidos que nada provam (rodada 1 da 3.3): ela fica "a conferir" e
        # pendente, e a faixa das pendentes a lê pelo nº (Minor 3 da rodada 2: o início e o fim da Visão COS podem ter mudado)
        lista_central.pendente(wid)
    texto, aviso = regra.mensagem_execucao(n, res, lambda x: api.fmt_data_br(x) or "—")
    return jsonify({"ok": True, "mensagem": texto, "aviso": aviso, "n": n,
                    "confirmado": bool(res.get("confirmado"))})


# ── as tarefas da OS, uma a uma (06/11/2026) ──────────────────────────────────────────────────────────────────────────
# Levi, na página da OS da Engenharia (a OS 16289, de seis inversores): "Nos ativos deve mostrar um check quando a tarefa
# for concluída"; "Quando temos mais de um ativo deve ter a opção de abrir as subtarefas do ativo e responder a subtarefa";
# "Ao lado do ativo deve ter um botão de 'Iniciar atividade' que o início da atividade já marca a data e hora que a pessoa
# clica, pode ter a opção de pausar"; "Botão de anexar na tarefa, aí terá ao lado do nome do ativo 'x anexos' e os botões
# de iniciar, pausar ou concluir!". O cronômetro é o do Fracttal web (`os_execucao`, capturado em 27/07/2026 e usado pelo
# kanban da Performance do app de mesa), por id da tarefa, com as regras da resposta da sessão do OS Creator (06/11/2026):
# pausar pede o motivo; a pausada é retomada antes de encerrar; o estado é relido depois de cada passo (o Fracttal aceita
# calado); a tarefa tem de ser da OS. Concluir a tarefa encerra o tempo e NÃO lança outro registro de execução (o
# /executar lança um novo, e as horas dobrariam); antes, as subtarefas obrigatórias têm de estar respondidas.
def _uma_tarefa(d: dict) -> list:
    """A OS de UMA tarefa no formato do `subtarefas_por_tarefa` (que devolve [] nela: a lista direta do card)."""
    ts = [t for t in (d.get("tarefas") or []) if isinstance(t, dict) and t.get("id") is not None]
    if not ts:
        return []
    t, subs = ts[0], [s for s in (d.get("subtarefas") or []) if isinstance(s, dict)]
    situacao, sit = regra.situacao_tarefa(t)
    ativo = str(t.get("ativo") or "").strip()
    return [{"id": t["id"], "n": 1, "titulo": str(t.get("titulo") or "").strip() or ativo or "Tarefa 1", "ativo": ativo,
             "situacao": situacao, "sit": sit, "feitas": sum(1 for s in subs if s.get("feito")), "total": len(subs)}]


@bp.route("/api/os/<int:wid>/tarefas")
@exige_sessao
def api_tarefas(wid):
    """Cada tarefa da OS com o ativo, a situação (o check: a tarefa com fim), as subtarefas respondidas e o cronômetro."""
    d = api.get_os_detalhes(wid) or {}
    grupos = [g for g in (regra.subtarefas_por_tarefa(d) or _uma_tarefa(d)) if g.get("id") is not None]
    ids = [g["id"] for g in grupos]
    with api._ExecutorComContexto(max_workers=4) as ex:
        execs = dict(zip(ids, ex.map(api.execucao_atual, ids)))
    out = []
    for g in grupos:
        e = execs.get(g["id"]) or {}
        out.append({"id": g["id"], "n": g["n"], "titulo": g["titulo"], "ativo": g["ativo"], "situacao": g["situacao"],
                    "feita": g["sit"] == "ok", "feitas": g["feitas"], "total": g["total"],
                    "execucao": {"estado": e.get("estado") or "parada", "inicio": e.get("inicio") or "",
                                 "trabalhado_s": e.get("trabalhado_s") or 0, "motivo": e.get("motivo") or ""}})
    return jsonify({"folio": d.get("folio"), "tarefas": out})


@bp.route("/api/execucao/motivos")
@exige_sessao
def api_motivos_pausa():
    return jsonify({"motivos": api.motivos_pausa() or []})


_CRONOMETRO = {  # ação → (o estado de antes que ela aceita, o estado esperado depois, o que se diz)
    "iniciar": (("parada",), "rodando", "Atividade iniciada"),
    "pausar": (("rodando",), "pausada", "Atividade pausada"),
    "retomar": (("pausada",), "rodando", "Atividade retomada"),
    "concluir": (("rodando", "pausada"), "parada", "Atividade concluída"),
}
_ESTADO_TXT = {"parada": "parada", "rodando": "em andamento", "pausada": "pausada"}


def _tarefa_da_os(wid, tid) -> bool:
    try:
        return int(tid) in {int(x) for x in (api._ids_tarefas_da_os(wid) or []) if str(x).isdigit()}
    except (TypeError, ValueError):
        return False


@bp.route("/api/os/<int:wid>/tarefa/<int:tid>/cronometro", methods=["POST"])
@exige_sessao
def api_cronometro(wid, tid):
    c = _corpo()
    acao = str(c.get("acao") or "")
    if acao not in _CRONOMETRO:
        return _erro("Ação desconhecida: use iniciar, pausar, retomar ou concluir.")
    if not _tarefa_da_os(wid, tid):
        return _erro("Esta tarefa não é da OS.", 404)
    aceita, esperado, feito = _CRONOMETRO[acao]
    antes = (api.execucao_atual(tid) or {}).get("estado") or "parada"
    if antes not in aceita:
        return _erro("A atividade está %s: não dá para %s." % (_ESTADO_TXT.get(antes, antes), acao))
    if acao == "iniciar":
        res = api.iniciar_execucao(tid)
    elif acao == "pausar":
        motivo = c.get("motivo")
        if not str(motivo or "").isdigit():
            return _erro("Escolha o motivo da pausa.")
        res = api.pausar_execucao(tid, int(motivo), str(c.get("nota") or "").strip())
    elif acao == "retomar":
        res = api.retomar_execucao(tid)
    else:
        campos = api.subtarefas_da_tarefa(tid)
        faltam = regra.faltando_obrigatorias(campos, {str(x.get("id_form_item")): x.get("valor") for x in campos})
        if faltam:
            return _erro("Responda as subtarefas obrigatórias antes de concluir: %s." % "; ".join(faltam[:4]))
        res = {"ok": True}
        if antes == "pausada":                       # a pausada não aceita encerrar: retoma antes (os_execucao)
            res = api.retomar_execucao(tid)
        if isinstance(res, dict) and res.get("ok"):
            res = api.finalizar_execucao(tid)
    if not (isinstance(res, dict) and res.get("ok")):
        return _erro((res or {}).get("erro") or "O Fracttal não fez.", 502)
    lista_central.mudou(wid)
    agora = api.execucao_atual(tid) or {}
    if (agora.get("estado") or "parada") != esperado:
        return _erro("O Fracttal aceitou, mas a atividade ficou %s." % _ESTADO_TXT.get(agora.get("estado"), "como estava"),
                     502)
    return jsonify({"ok": True, "estado": esperado, "mensagem": feito + " no Fracttal.",
                    "execucao": {"estado": esperado, "inicio": agora.get("inicio") or "",
                                 "trabalhado_s": agora.get("trabalhado_s") or 0}})


# ── os registros da tarefa: editar o início e o fim (09/11/2026) ──────────────────────────────────────────────────────
# Levi: "Gostaria que nas subtarefas fosse possível também editar registros [...] A ideia é poder editar o início e fim
# da atividade!". Os registros são as execuções da tarefa (`historico_execucao`, o `tasks.wo_tasks_execution_list`); o
# editar é o `editar_execucao` (o `tasks.wo_tasks_execution_update` da captura dele). Só o registro encerrado: o
# `to_stop` encerraria o que está rodando. O registro é relido depois (o Fracttal aceita calado).
def _quando_utc(v):
    """O `initial_date`/`final_date` do Fracttal (UTC; com ou sem o Z) → datetime aware em UTC, ou None."""
    from datetime import datetime, timezone
    t = str(v or "").strip()
    if not t or t.lower() == "none":
        return None
    try:
        d = datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _um_registro(e: dict) -> dict:
    ini, fim = _quando_utc(e.get("initial_date")), _quando_utc(e.get("final_date"))
    return {"id": e.get("id"), "inicio": ini.isoformat() if ini else "", "fim": fim.isoformat() if fim else "",
            "aberta": fim is None,
            "quem": str(e.get("name") or e.get("personnel_description") or "").strip(),
            "trabalhado_s": int(e.get("total_active_seconds") or 0)}


@bp.route("/api/os/<int:wid>/tarefa/<int:tid>/registros")
@exige_sessao
def api_registros(wid, tid):
    if not _tarefa_da_os(wid, tid):
        return _erro("Esta tarefa não é da OS.", 404)
    regs = [_um_registro(e) for e in (api.historico_execucao(tid) or []) if isinstance(e, dict) and e.get("id")]
    return jsonify({"registros": regs})


@bp.route("/api/os/<int:wid>/tarefa/<int:tid>/registro/<int:rid>", methods=["POST"])
@exige_sessao
def api_registro_editar(wid, tid, rid):
    """{inicio, fim}: o que o <input type=datetime-local> manda, na hora de Brasília. O fim é opcional (fica o que era)."""
    from datetime import datetime, timedelta
    if not _tarefa_da_os(wid, tid):
        return _erro("Esta tarefa não é da OS.", 404)
    c = _corpo()
    antes = {e.get("id"): e for e in (api.historico_execucao(tid) or []) if isinstance(e, dict)}
    if rid not in antes:
        return _erro("Este registro não é da tarefa.", 404)
    if _quando_utc(antes[rid].get("final_date")) is None:
        return _erro("Encerre a atividade antes de editar o registro (ele ainda está aberto).")
    try:
        if not str(c.get("inicio") or "").strip():
            raise ValueError
        ini = trad.data_brt(c.get("inicio"))
        fim = trad.data_brt(c.get("fim")) if str(c.get("fim") or "").strip() else None
    except (ValueError, TypeError):
        return _erro("Informe o início (e o fim, se quiser) com a data e a hora.")
    if fim is not None and fim < ini:
        return _erro("O fim não pode ser antes do início.")
    if max(ini, fim or ini) > datetime.now(trad.BRT) + timedelta(minutes=5):
        return _erro("O registro não pode ficar no futuro.")
    res = api.editar_execucao(rid, ini, fim)
    if not (isinstance(res, dict) and res.get("ok")):
        return _erro((res or {}).get("erro") or "O Fracttal não gravou o registro.", 502)
    depois = {e.get("id"): e for e in (api.historico_execucao(tid) or []) if isinstance(e, dict)}
    novo = depois.get(rid) or {}

    def bate(lido, pedido):
        d = _quando_utc(lido)
        return d is not None and abs((d - pedido).total_seconds()) < 60
    if not bate(novo.get("initial_date"), ini) or (fim is not None and not bate(novo.get("final_date"), fim)):
        return _erro("O Fracttal aceitou, mas o registro não ficou com o horário pedido. Confira no Fracttal.", 502)
    lista_central.mudou(wid)
    f = lambda d: d.astimezone(trad.BRT).strftime("%d/%m %H:%M")     # noqa: E731
    return jsonify({"ok": True, "mensagem": "Registro alterado no Fracttal: início %s%s." % (
        f(ini), (", fim %s" % f(fim)) if fim is not None else "")})


@bp.route("/api/os/<int:wid>/tarefa/<int:tid>/respostas", methods=["POST"])
@exige_sessao
def api_respostas(wid, tid):
    """Responder as subtarefas de UMA tarefa, sem lançar execução (o "Fazer a tarefa" lança): o `salvar_subtarefas` do
    /executar, e a releitura diz quantas obrigatórias ainda faltam."""
    if not _tarefa_da_os(wid, tid):
        return _erro("Esta tarefa não é da OS.", 404)
    valores = _corpo().get("valores") or {}
    campos = api.subtarefas_da_tarefa(tid)
    por_id = {str(x.get("id_form_item")): x for x in campos}
    a_gravar = [{"id_form_item": por_id[k]["id_form_item"], "valor": v, "tipo": por_id[k].get("tipo") or 1}
                for k, v in valores.items() if k in por_id and str(v or "").strip()]
    if not a_gravar:
        return _erro("Responda ao menos uma subtarefa.")
    n = (api.salvar_subtarefas(wid, tid, a_gravar) or {}).get("n") or 0
    depois = api.subtarefas_da_tarefa(tid)
    faltam = regra.faltando_obrigatorias(depois, {str(x.get("id_form_item")): x.get("valor") for x in depois})
    lista_central.mudou(wid)
    texto = ("1 resposta gravada" if n == 1 else "%d respostas gravadas" % n) + " na tarefa."
    if faltam:
        texto += " Faltam as obrigatórias: %s." % "; ".join(faltam[:4])
    return jsonify({"ok": True, "mensagem": texto, "n": n, "pendentes": len(faltam)})


def _no_quadro_de_garantias(wid, st) -> None:
    """O status novo no quadro guardado de Garantias (o mesmo ajuste do Finalizar de lá, `rotas_acomp._ajustar`): sem ele,
    a OS cancelada ou em verificação pela tela do chamado seguia na coluna de antes até o quadro reler o Fracttal. A
    gravação já está no Fracttal quando isto roda: erro aqui não vira erro na tela."""
    try:
        from . import rotas_acomp
        rotas_acomp._ajustar(wid, {"status_id": st, "status": api.WO_STATUS.get(st, "")})
    except Exception:                                    # noqa: BLE001
        import logging
        logging.exception("o quadro de Garantias não recebeu o status %s da OS %s", st, wid)


# Enviar para verificação (Levi, 06/11/2026: "Nessas telas devem ter essas opção também: Enviar para verificação, concluir
# e cancelar!"): o status 2 (Em Verificação) pelo `api.mudar_status_os(wid, 2)` (tasks.work_orders_change_status), o
# caminho que a revisão das OS provou no ar (a OS 18630 foi para Em Verificação por ele, e a 18635 na volta do
# `_conferir_ja_realizada`; a resposta da sessão do OS Creator, 06/11/2026). Ele só muda o status: o fim e as
# subtarefas são do "Fazer a tarefa", que o diálogo oferece antes, como o do Concluir. Só a OS Em Processo vai, e o
# status é lido antes e depois (o Fracttal aceita calado).
@bp.route("/api/os/<int:wid>/verificacao", methods=["POST"])
@exige_sessao
def api_verificacao(wid):
    folio = _corpo().get("folio") or wid
    antes = api.status_da_os(wid)
    if antes is not None and int(antes) != 1:
        return _erro("A OS %s está %s no Fracttal: só a OS em processo vai para verificação."
                     % (folio, api.WO_STATUS.get(int(antes), "fora de processo").lower()))
    res = api.mudar_status_os(wid, 2)
    if not (isinstance(res, dict) and res.get("ok")):
        return _erro((res or {}).get("erro") or "O Fracttal não mudou o status da OS.", 502)
    lista_central.mudou(wid)
    depois = api.status_da_os(wid)
    if depois is not None and int(depois) != 2:
        return _erro("O Fracttal aceitou o pedido, mas a OS %s seguiu %s." % (
            folio, api.WO_STATUS.get(int(depois), "como estava").lower()), 502)
    _no_quadro_de_garantias(wid, 2)
    return jsonify({"ok": True, "mensagem": "OS %s enviada para verificação no Fracttal." % folio})


@bp.route("/api/os/<int:wid>/cancelar", methods=["POST"])
@exige_sessao
def api_cancelar(wid):
    """Cancelar OS — `CancelarOSDialog._confirmar`: motivo (status custom) obrigatório + observação opcional; o tipo é fixo
    ('Cancelar OS', dentro do `cancel_os`). A AUTORIZAÇÃO é a do usuário no Fracttal: recusa vira FracttalError → 502."""
    c = _corpo()
    idm = c.get("id_status_custom")
    if idm in (None, "", 0, "0"):
        return _erro("Escolha o motivo do cancelamento.")
    api.cancel_os(wid, idm, str(c.get("note") or "").strip())        # cancelar_os.py:77 — (self._wo, idm, obs.strip())
    lista_central.mudou(wid)
    _no_quadro_de_garantias(wid, 4)
    return jsonify({"ok": True, "mensagem": "OS %s cancelada com sucesso." % (c.get("folio") or wid)})

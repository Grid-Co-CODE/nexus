"""Torre Zeladoria: a plataforma de zeladoria (o antigo Radar de Fornecedores) dentro do Nexus.

Levi, 03/11/2026: "trazer toda a estrutura da plataforma de zeladoria com a mesma lógica e caminhos do BD, só que ao
invés de Supabase virá tudo para o Nexus, com design do Nexus". O app do Radar entra como CLONE
(`clone/radar.html`, ver `clone/ORIGEM.md`), num iframe da casca. Cada aba dele é uma tela no menu do Nexus, e a barra
lateral própria do clone some. No lugar do supabase-js, o clone recebe a ponte (`nexus/static/zeladoria/ponte.js`),
que pede o dado às rotas `/api/*` desta torre. Elas leem os três livros da zeladoria (`nexus/zeladoria/leitura.py`).

Até a troca a torre só lê: quem edita é o Radar, e a cópia do Supabase roda sob comando
(`ferramentas/copiar_zeladoria.py`). A gravação pelo Nexus (`nexus/zeladoria/gravacao.py`, etapa 4) só liga onde
`NEXUS_ZELADORIA_GRAVA=1`, o servidor no dia da troca. Leia o CLAUDE.md desta pasta antes de mexer; o desenho é
`docs/superpowers/specs/2026-11-03-zeladoria-no-nexus-design.md`.
"""
import json
import re
from pathlib import Path

from flask import Response, abort, current_app, jsonify, render_template, request, send_file, session, url_for

from ...casca import tema_do_pedido
from ...prefixo import na_raiz
from ...zeladoria import gravacao, leitura
from ...zeladoria.tabelas import TabelaDesconhecida
from ..modelo import Tela, Torre
from ..moldura import _de_outro_site

FONTE = "Radar de Fornecedores (cópia do Supabase até a troca)"
# id da tela no Nexus -> id da aba no app do Radar (o `TABS` do clone)
ABAS = {
    "visao-geral": "overview", "usinas": "usinas", "fornecedores": "fornecedores", "criticidade": "criticidade",
    "prioridades": "prioridades", "rodadas": "rodadas", "aprovacao": "aprovacao", "andamento": "andamento",
    "cotacoes": "cotacoes", "historico": "historico", "farol-contratual": "analiseServicos",
    "planejamento": "planejamento", "contratos": "contratos", "documentacao": "documentacao",
    "financeiro": "financeiro", "danos": "danos", "lixeira": "lixeira", "usuarios": "usuarios",
}

TORRE = Torre(
    id="zeladoria",
    nome="Zeladoria",
    ordem=55,                 # logo abaixo de Chamados (Levi, 05/11/2026: "coloque Zeladoria abaixo de chamados")
    icone="plant",
    descricao="Fornecedores de zeladoria: cotação, aprovação, contratos, documentação, financeiro e criticidade.",
    telas=[
        Tela("visao-geral", "Visão Geral", "Como estão as cotações, os serviços e o orçamento de zeladoria?", FONTE),
        Tela("usinas", "Usinas", "Que usinas a zeladoria atende, e com que dados de contrato?", FONTE),
        Tela("fornecedores", "Fornecedores", "Quem são os fornecedores e as equipes, e com que documentação?", FONTE),
        Tela("criticidade", "Criticidade", "Onde a vegetação e a sujidade estão críticas, pela última ronda?", FONTE),
        Tela("prioridades", "Prioridades", "Que usina e serviço precisam de cotação primeiro?", FONTE),
        Tela("rodadas", "Rodadas", "Que rodadas de cotação estão abertas?", FONTE),
        Tela("aprovacao", "Aprovação", "Que cotação espera a decisão do Analista ou do Head?", FONTE),
        Tela("andamento", "Serviços em Andamento", "Que serviço está em execução, e em que etapa?", FONTE),
        Tela("cotacoes", "Histórico de Cotações", "Quanto cada fornecedor cotou, e como os valores se comparam?", FONTE),
        Tela("historico", "Histórico de Serviços", "Que serviços terminaram, e como foram avaliados?", FONTE),
        Tela("farol-contratual", "Farol Contratual", "Cada usina recebeu a zeladoria que o contrato pede?", FONTE),
        Tela("planejamento", "Planejamento", "O que foi planejado e o que foi feito no cronograma?", FONTE),
        Tela("contratos", "Contratos Anuais", "Como andam os contratos anuais e as OS de cada um?", FONTE),
        Tela("documentacao", "Documentação", "Que documento de fornecedor ou colaborador vence ou falta?", FONTE),
        Tela("financeiro", "Financeiro", "Quanto foi previsto, pago e simulado no orçamento de zeladoria?", FONTE),
        Tela("danos", "Controle de Danos", "Que módulos foram danificados, por quem, e com que pendência?", FONTE),
        Tela("lixeira", "Lixeira", "O que foi excluído e pode voltar?", FONTE),
        Tela("usuarios", "Usuários", "Quem usa o Radar, com que papel, e quem espera aprovação?", FONTE),
    ],
)

bp = TORRE.criar_blueprint(__name__)

CLONE = Path(__file__).resolve().parent / "clone" / "radar.html"
_CLONE = {"texto": None, "tokens": None}
NEXUS_CSS = Path(__file__).resolve().parents[2] / "static" / "nexus.css"
# os seletores dos tokens no nexus.css e o que eles viram dentro do clone: o atributo do Radar (data-theme, que o
# <html> do clone sempre tem) dá a força para vencer o CSS do clone, e o data-tema="claro" do Nexus escolhe o claro
_SELETORES_TOKENS = {':root,:root[data-tema="claro"] .topo{': ":root[data-theme]{",
                     ':root[data-tema="claro"]{': ':root[data-theme][data-tema="claro"]{',
                     ":root{": ":root[data-theme]{"}


def tokens_do_nexus() -> str:
    """Os tokens do nexus.css (os blocos do escuro, do claro e das fontes), para o clone usar a paleta do Nexus (Levi,
    03/11/2026: "bote aquele azul nexus para ficar no padrão nexus de planilha e cards"). Tirados do próprio nexus.css,
    e não copiados: o token que muda lá muda na Zeladoria junto."""
    if _CLONE["tokens"] is None:
        css = NEXUS_CSS.read_text(encoding="utf-8")
        trecho = css[css.index("*/") + 2:css.index("*{box-sizing:border-box}")]
        for de, para in _SELETORES_TOKENS.items():
            if de not in trecho:
                raise RuntimeError(f"o nexus.css mudou: o bloco {de!r} não está mais antes do *{{box-sizing}}")
            trecho = trecho.replace(de, para)
        _CLONE["tokens"] = '<style id="nexus-tokens">' + trecho.strip() + "</style>\n"
    return _CLONE["tokens"]
SOMENTE_LEITURA = "Cópia só leitura até a troca."
_FOLIO = re.compile(r"^\d{1,12}$")


def _estado():
    try:
        return leitura.estado(current_app.config), None
    except leitura.CopiaAusente as e:
        return None, str(e)


def _tela(tela_id: str):
    def view():
        est, erro, banco_fora = None, None, False
        try:
            est = leitura.estado(current_app.config)
        except leitura.CopiaAusente as e:
            erro, banco_fora = str(e), isinstance(e, leitura.BancoFora)
        return render_template("zeladoria/tela.html", torre=TORRE, tela=TORRE.tela(tela_id), aba=ABAS[tela_id],
                               estado=est, erro=erro, banco_fora=banco_fora, grava=_grava())
    return view


for _t in TORRE.telas:
    bp.add_url_rule(f"/{_t.id}", f"tela_{_t.id.replace('-', '_')}", _tela(_t.id))


@bp.route("/app")
def app_radar():
    """O clone, com a configuração e a ponte nos dois marcadores (ver clone/ORIGEM.md)."""
    if _CLONE["texto"] is None:
        _CLONE["texto"] = CLONE.read_text(encoding="utf-8")
    aba = request.args.get("aba")
    if aba not in ABAS.values():
        aba = "overview"
    cfg = {"api": na_raiz("/t/zeladoria/api"), "somenteLeitura": not _grava(), "sair": na_raiz("/sair")}
    if _grava():
        # a coluna-chave das tabelas que não usam `id`: a ponte compara o que leu com o que o app manda, linha a linha
        est, _erro = _estado()
        cfg["chaves"] = {f"rf_{aba}": ch for aba, ch in ((est or {}).get("chaves") or {}).items() if ch != "id"}
    # o tema do Nexus (o escuro é o padrão; o claro, o cookie do botão do topo) vira o data-theme do clone, que a paleta
    # da Zeladoria usa; o botão do topo grava `nexus.tema` no navegador, e o clone muda junto, sem recarregar
    claro = tema_do_pedido() == "claro"
    tema = "light" if claro else "dark"
    config = (f"<script>window.ZELADORIA = {json.dumps(cfg)}; window.ZELADORIA_ABA = {json.dumps(aba)}; "
              f"window.ZELADORIA_TEMA = {json.dumps(tema)};\n"
              "window.addEventListener('storage', function (e) { if (e.key !== 'nexus.tema' || !e.newValue) return; "
              "var h = document.documentElement, c = e.newValue === 'claro'; "
              "h.setAttribute('data-theme', c ? 'light' : 'dark'); "
              "if (c) h.setAttribute('data-tema', 'claro'); else h.removeAttribute('data-tema'); });"
              "</script>\n"
              # o menu é o do Nexus: a barra lateral do clone some (o #app dele é flex, o conteúdo ocupa a largura)
              "<style>.sidebar{display:none !important}</style>")
    ponte = (f'<script src="{url_for("static", filename="zeladoria/ponte.js")}"></script>\n'
             "<script>iniciarRadarApp();</script>")
    atributos = f'data-theme="{tema}"' + (' data-tema="claro"' if claro else "")
    html = (_CLONE["texto"].replace('<html lang="pt-BR">', f'<html lang="pt-BR" {atributos}>', 1)
            .replace('<style id="zeladoria-paleta">', tokens_do_nexus() + '<style id="zeladoria-paleta">', 1)
            .replace("<!--ZELADORIA:CONFIG-->", config).replace("<!--ZELADORIA:PONTE-->", ponte))
    return Response(html, mimetype="text/html", headers={"Cache-Control": "no-store"})


def _quem(est):
    return leitura.quem_sou(est, session.get("usuario"), bool(session.get("admin")))


def _grava() -> bool:
    return gravacao.ativo(current_app.config)


def _corpo() -> dict:
    corpo = request.get_json(silent=True)
    return corpo if isinstance(corpo, dict) else {}


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


def _ordem():
    o = request.args.get("order")
    if not o:
        return None
    col, _, sentido = o.partition(":")
    return col, sentido == "desc"


@bp.route("/api/rf/<view>")
def api_rf(view: str):
    est, erro = _estado()
    if est is None:
        return jsonify(erro=erro or "a cópia do Radar não está no banco"), 503
    try:
        return jsonify(leitura.linhas(est, view, _filtros(), _ordem(), _quem(est)))
    except TabelaDesconhecida:
        abort(404)


@bp.route("/api/eu")
def api_eu():
    est, erro = _estado()
    if est is None:
        return jsonify(erro=erro), 503
    q = _quem(est)
    if not _grava():
        return jsonify(user={"id": q["id"], "email": q["email"]}, grava=False)
    g = gravacao.do_app(current_app.config)
    # a pessoa nova ganha a linha "pendente" no `perfis`, para o HEAD aprovar em Usuários (no Supabase era uma regra do
    # banco ao criar a conta)
    if q.get("status") == "pendente" and q.get("email") and q["id"] != leitura.ADMIN_ID:
        g.garantir_perfil(q)
    return jsonify(user={"id": q["id"], "email": q["email"]}, grava=True, versao=g.estado["versao"],
                   situacao=g.situacao())


def _gravar(fazer):
    """O caminho comum do POST que grava: só com a gravação ligada, só da própria página, a recusa da regra como 403."""
    if not _grava():
        return jsonify(erro=SOMENTE_LEITURA), 405
    if _de_outro_site():
        return jsonify(erro="Pedido de outro site."), 403
    est, erro = _estado()
    if est is None:
        return jsonify(erro=erro), 503
    g = gravacao.do_app(current_app.config)
    try:
        r = fazer(g, _quem(est), _corpo())
    except gravacao.Recusa as e:
        return jsonify(erro=str(e)), 403
    except OSError:
        # o diário não gravou: a mudança NÃO entrou (o "Salvo" do app não acende)
        current_app.logger.exception("zeladoria: o diário da gravação não gravou")
        return jsonify(erro="O Nexus não conseguiu guardar agora. Tente de novo em instantes."), 503
    return jsonify({**r, "situacao": g.situacao()})


@bp.route("/api/gravar", methods=["POST"])
def api_gravar():
    """Um salvamento do app: {"ops": [...], "versao": a versão da página aberta}. Ver `gravacao.Gravador.aplicar`."""
    def fazer(g, quem, corpo):
        ops = corpo.get("ops")
        if not isinstance(ops, list) or not all(isinstance(o, dict) for o in ops):
            raise gravacao.Recusa("pedido de gravação inválido")
        return g.aplicar(ops, quem, corpo.get("versao") or 0)
    return _gravar(fazer)


@bp.route("/api/situacao")
def api_situacao():
    if not _grava():
        return jsonify(grava=False)
    return jsonify(grava=True, **gravacao.do_app(current_app.config).situacao())


@bp.route("/api/funcao/<nome>", methods=["POST"])
def api_funcao(nome: str):
    if nome.startswith("fin_"):
        return _gravar(lambda g, quem, corpo: g.chamar(nome, corpo.get("args") or {}, quem, corpo.get("versao") or 0))
    if nome == "fracttal-os":
        return _fracttal_os()
    if nome == "fracttal-sync":
        return _fracttal_sync()
    if nome != "fracttal-fotos":
        return jsonify(erro=SOMENTE_LEITURA), 405
    est, erro = _estado()
    if est is None:
        return jsonify(erro=erro), 503
    if _quem(est).get("status") != "aprovado":
        return jsonify(erro="Sem permissão."), 403
    folio = str((request.get_json(silent=True) or {}).get("folio") or "").strip()
    if not _FOLIO.match(folio):
        return jsonify(erro="Nº de OS inválido."), 400
    if folio not in leitura.folios(est):
        return jsonify(erro="Essa OS não é ronda da zeladoria."), 404
    from ...campo import nota_fracttal, ronda_fotos
    try:
        anexos = ronda_fotos.anexos(folio)
        sub = nota_fracttal.subtarefas_da_os(folio)
    except Exception:            # noqa: BLE001 — a cota de 200/min é da empresa: o Fracttal recusa e a tela avisa
        current_app.logger.warning("zeladoria: as fotos da OS %s não vieram do Fracttal", folio, exc_info=True)
        return jsonify(erro="O Fracttal não respondeu agora (pode ser o limite de consultas da empresa). "
                            "Tente de novo em 1 minuto."), 502
    fotos = [{"descricao": a.get("desc") or "", "url": url_for(".foto", folio=folio, i=a["i"]), "tipo": a.get("mime")}
             for a in anexos]
    checklist = [{"item": s.get("description") or "", "valor": s.get("value") or ""} for s in sub]
    return jsonify(folio=folio, fotos=fotos, checklist=checklist, validade_horas=24)


def _fracttal_sync():
    """O botão "Sincronizar com Fracttal" do app: relê as rondas na hora (`nexus/zeladoria/rondas_fracttal.py`). Até a
    troca, as rondas vêm da cópia do Radar, e o botão diz isso."""
    if not _grava():
        return jsonify(ok=False, gravadas=0, erro="Até a troca, as rondas vêm da cópia do Radar; o Nexus passa a ler o "
                                                  "Fracttal quando a gravação ligar.")
    if _de_outro_site():
        return jsonify(erro="Pedido de outro site."), 403
    est, erro = _estado()
    if est is None:
        return jsonify(erro=erro), 503
    if _quem(est).get("status") != "aprovado":
        return jsonify(erro="Sem permissão."), 403
    from ...zeladoria import rondas_fracttal
    return jsonify(rondas_fracttal.sincronizar(gravacao.do_app(current_app.config), forcar=_corpo().get("forcar") is True))


def _fracttal_os():
    """A consulta da OS pelo número (`nexus/zeladoria/fracttal_os.py`): só leitura no Fracttal, para quem está aprovado,
    até 10 números por pedido."""
    est, erro = _estado()
    if est is None:
        return jsonify(erro=erro), 503
    if _quem(est).get("status") != "aprovado":
        return jsonify(erro="Sem permissão."), 403
    from ...zeladoria import fracttal_os
    pedidos = _corpo().get("folios")
    if not isinstance(pedidos, list) or not pedidos or len(pedidos) > fracttal_os.LOTE:
        return jsonify(erro=f"Mande de 1 a {fracttal_os.LOTE} números de OS."), 400
    folios = [str(f).strip() for f in pedidos]
    if not all(fracttal_os.FOLIO.match(f) for f in folios):
        return jsonify(erro="Nº de OS inválido."), 400
    return jsonify(fracttal_os.consultar(list(dict.fromkeys(folios))))


def _contratos(est):
    from ...zeladoria import contratos_pdf
    return contratos_pdf, contratos_pdf.caminhos(est)


@bp.route("/api/contrato-pdf")
def api_contrato_pdf():
    """O "link assinado" do PDF do contrato (o `createSignedUrl` do arquivo `contratos-zeladoria` do Radar): o endereço do
    PDF no Nexus, se o arquivo já foi trazido (`nexus/zeladoria/contratos_pdf.py`)."""
    est, erro = _estado()
    if est is None:
        return jsonify(erro=erro), 503
    if _quem(est).get("status") != "aprovado":
        return jsonify(erro="Sem permissão."), 403
    cp, conhecidos = _contratos(est)
    caminho = (request.args.get("caminho") or "").strip()
    if caminho not in conhecidos:
        return jsonify(erro="Esse PDF não é de um contrato da zeladoria."), 404
    if not cp.existe(current_app.config, caminho):
        return jsonify(erro="O PDF deste contrato ainda não foi trazido do Supabase para o Nexus."), 404
    return jsonify(signedUrl=url_for(".contrato_pdf", caminho=caminho))


@bp.route("/contrato/<path:caminho>")
def contrato_pdf(caminho: str):
    est, _erro = _estado()
    if est is None:
        abort(503)
    if _quem(est).get("status") != "aprovado":
        abort(403)
    cp, conhecidos = _contratos(est)
    if caminho not in conhecidos or not cp.existe(current_app.config, caminho):
        abort(404)
    resp = send_file(cp.arquivo(current_app.config, caminho), mimetype="application/pdf", conditional=True,
                     download_name=caminho.rsplit("/", 1)[-1])
    resp.headers["Cache-Control"] = "private, max-age=3600"
    return resp


@bp.route("/contratos-pdf")
def contratos_pdf_pagina():
    """O envio dos PDFs dos contratos para o servidor do Nexus: só o administrador."""
    if not session.get("admin"):
        abort(403)
    est, erro = _estado()
    if est is None:
        return render_template("zeladoria/contratos_pdf.html", torre=TORRE, itens=[], erro=erro)
    cp, _c = _contratos(est)
    return render_template("zeladoria/contratos_pdf.html", torre=TORRE, itens=cp.situacao(current_app.config, est),
                           erro=None, max_mb=cp.MAX_MB)


@bp.route("/api/contratos/enviar", methods=["POST"])
def api_contratos_enviar():
    if not session.get("admin"):
        return jsonify(erro="Só o administrador envia os PDFs."), 403
    if _de_outro_site():
        return jsonify(erro="Pedido de outro site."), 403
    # o limite geral do Nexus é 25 MB por pedido; dois contratos têm 27,5 MB (06/11/2026: voltaram 413). Só esta rota,
    # só do administrador, aceita o teto dos PDFs, e antes de o corpo ser lido
    from ...zeladoria import contratos_pdf
    request.max_content_length = (contratos_pdf.MAX_MB + 1) * contratos_pdf.MB
    est, erro = _estado()
    if est is None:
        return jsonify(erro=erro), 503
    cp, conhecidos = _contratos(est)
    caminho = (request.form.get("caminho") or "").strip()
    arq = request.files.get("arquivo")
    if caminho not in conhecidos:
        return jsonify(erro="Esse caminho não é de um PDF da cópia."), 400
    if arq is None:
        return jsonify(erro="Faltou o arquivo."), 400
    try:
        tamanho = cp.guardar(current_app.config, caminho, arq.stream.read(cp.MAX_MB * cp.MB + 1))
    except cp.Recusado as e:
        return jsonify(erro=str(e)), 400
    return jsonify(caminho=caminho, mb=round(tamanho / cp.MB, 1))


@bp.route("/foto/<folio>/<int:i>")
def foto(folio: str, i: int):
    """A foto da ronda pelo Nexus (o link assinado do Fracttal fica no servidor), como na tela de Rondas do Campo."""
    if not _FOLIO.match(folio):
        abort(404)
    est, _erro = _estado()
    if est is None:
        abort(503)
    if _quem(est).get("status") != "aprovado":
        abort(403)
    if folio not in leitura.folios(est):
        abort(404)
    from ...campo import ronda_fotos
    fazer = ronda_fotos.miniatura if request.args.get("mini") else ronda_fotos.tela
    try:
        corpo, mime = fazer(folio, i)
    except Exception:            # noqa: BLE001 — foto que sumiu do Fracttal ou cota da empresa
        abort(404)
    return Response(corpo, mimetype=mime, headers={"Cache-Control": "private, max-age=3600"})


@bp.route("/api/cronograma", methods=["GET", "OPTIONS"])
def cronograma_api():
    """O link do cronograma para o app central (o `cronograma-api` do Radar; `nexus/zeladoria/cronograma_api.py`). Rota
    pública (`auth.ROTAS_PUBLICAS`): vale a chave no header `x-api-key`, nunca a sessão."""
    from ...auth import chaves
    from ...zeladoria import cronograma_api as CA

    def resp(corpo, status=200):
        r = jsonify(corpo)
        r.status_code = status
        r.headers.update({**CA.CORS, "Cache-Control": "no-store"})
        return r
    if request.method == "OPTIONS":
        return resp("ok")
    esperada = chaves.valor(CA.CHAVE)
    if not esperada:
        return resp({"erro": "API ainda não configurada (falta a chave no Nexus)."}, 503)
    if not CA.chave_confere(esperada, request.headers.get("x-api-key")):
        return resp({"erro": "Chave inválida."}, 401)
    try:
        est = leitura.estado(current_app.config)
    except leitura.BancoFora:
        return resp({"erro": "Falha ao ler o cronograma."}, 502)
    except leitura.CopiaAusente:
        return resp({"erro": "Cronograma ainda não publicado. Abra a Zeladoria no Nexus uma vez para publicar."}, 503)
    status, corpo = CA.responder(est, request.args)
    return resp(corpo, status)

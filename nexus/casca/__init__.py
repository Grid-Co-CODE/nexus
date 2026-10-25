"""A casca: Início, troca de tema, saúde e o que todo template recebe (menu, setor, tema). A cadeira saiu em 12/10/2026:
os setores (Base → Acessos) dizem o que cada pessoa vê."""
import hmac
import io
import os
import secrets
import subprocess
from functools import lru_cache

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.exceptions import RequestEntityTooLarge

from ..auth import destino_seguro, setor_telas
from ..prefixo import raiz
from ..torres import montar_menu, telas_com_conteudo
# no topo, e não dentro do Início: o "no ar desde" do cartão da versão é a hora do import, a do boot (13/10/2026)
from . import versao

bp = Blueprint("casca", __name__)

# Tema (08/10/2026, Levi: "precisamos de um tema claro também"): o escuro navy é o padrão; o claro é escolha da pessoa,
# guardada no cookie (o servidor já desenha o <html data-tema> certo, sem piscar o tema errado ao carregar) e no
# localStorage do navegador (reserva, aplicada pelo _tema_cabeca.html). Cookie desconhecido ou ausente = escuro.
COOKIE_TEMA = "nexus_tema"
TEMAS = ("escuro", "claro")
UM_ANO_S = 365 * 24 * 3600


def tema_do_pedido() -> str:
    tema = request.cookies.get(COOKIE_TEMA, "")
    return tema if tema in TEMAS else "escuro"


@lru_cache(maxsize=1)
def _commit() -> str:
    """Commit em execução. No servidor vem de NEXUS_COMMIT; local, do git; sem git, 'local'."""
    if os.environ.get("NEXUS_COMMIT"):
        return os.environ["NEXUS_COMMIT"][:7]
    try:
        saida = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                               text=True, timeout=3, cwd=os.path.dirname(__file__))
        return saida.stdout.strip() or "local"
    except (OSError, subprocess.SubprocessError):
        return "local"


def _telas_prontas(app) -> frozenset[str]:
    """As telas com conteúdo (o verde do menu), calculadas uma vez: o mapa de rotas não muda depois do boot."""
    if "nexus_telas_prontas" not in app.extensions:
        app.extensions["nexus_telas_prontas"] = telas_com_conteudo(app)
    return app.extensions["nexus_telas_prontas"]


@bp.route("/", methods=["GET", "POST"])
def inicio():
    """O Início, a primeira página de todos. Honesto (auditoria A3 da porta única, 10/10/2026): até então dizia "fase 0"
    e "Com dado real: 0" com 40 telas prontas no ar, e cada cartão abria a 1ª tela da torre, que em Comando, COS,
    Contratos e Relatórios é "Em construção". O número agora é o das telas prontas, pela mesma conta do verde do menu
    (`telas_com_conteudo`); o cartão leva à 1ª tela PRONTA da torre, e a torre sem nenhuma não vira link.

    A aba Atualizações é `/?aba=atualizacoes` (13/10/2026): nasceu em /atualizacoes, e no servidor o Caddy só manda ao
    Nexus a raiz exata e os caminhos do Nexus (DEPLOY.md, 5b): /atualizacoes ia à plataforma, que respondia "Not Found"
    (tests/test_rotas_no_caminho_do_nexus.py). A aba Sugestões (24/10/2026) é `/?aba=sugestoes` pelo mesmo motivo, e o
    envio dela é o único POST da raiz."""
    aba = request.args.get("aba")
    if aba == "sugestoes":
        return _sugestoes()
    if request.method == "POST":
        abort(405)
    if aba == "atualizacoes":
        return _atualizacoes()
    app = current_app._get_current_object()
    torres = _torres_da_pessoa()
    liberadas = setor_telas.liberadas_do_menu()
    prontas = _telas_prontas(app)
    cartoes = []
    for t in torres:
        urls = [f"/t/{t.id}/{s.id}" for s in t.telas if liberadas is None or f"{t.id}/{s.id}" in liberadas]
        das_prontas = [u for u in urls if u in prontas]
        cartoes.append({"torre": t, "url": das_prontas[0] if das_prontas else None, "prontas": len(das_prontas),
                        "total": len(urls)})
    if liberadas is not None:
        prontas = frozenset(u for u in prontas if u[3:] in liberadas)
    return render_template("inicio.html", torres=torres, cartoes=cartoes, total_prontas=len(prontas),
                           total_telas=sum(len([s for s in t.telas if liberadas is None or f"{t.id}/{s.id}" in liberadas])
                                           for t in torres),
                           # a versão no ar: a hora do commit e desde quando está no ar; leva às Atualizações
                           # (casca/versao.py, 13/10/2026). Os pedidos presos saíram do cartão a pedido do Levi
                           # ("tire ... preso em 24hrs"): seguem no log, pelo casca/presos.py
                           versao=versao.cartao(app), aba="inicio")


def _torres_da_pessoa() -> list:
    """Só as torres que o setor da pessoa vê (o administrador vê tudo)."""
    liberadas = setor_telas.liberadas_do_menu()
    return [t for t in current_app.extensions["nexus_torres"]
            if liberadas is None or any(f"{t.id}/{s.id}" in liberadas for s in t.telas)]


# ── Sugestões (24/10/2026) ───────────────────────────────────────────────────────────────────────────────────────────
_CHAVE_CODIGO, _CHAVE_AVISO = "sugestoes_codigo", "sugestoes_aviso"


def _codigo() -> str:
    """O código do formulário desta sessão (o login limpa a sessão e troca o código): outro site não o conhece."""
    if not session.get(_CHAVE_CODIGO):
        session[_CHAVE_CODIGO] = secrets.token_urlsafe(24)
    return session[_CHAVE_CODIGO]


def _sugestoes():
    """A aba Sugestões: o formulário para todos (título, área entre as torres que a pessoa vê, descrição e anexos) e,
    para o administrador, a lista de tudo o que chegou, com quem pediu e os anexos (`casca/sugestoes.py`)."""
    from . import sugestoes as S
    admin = bool(session.get("admin"))
    if request.args.get("anexo"):
        return _anexo_da_sugestao(S, admin)
    areas = {t.id: t.nome for t in _torres_da_pessoa()}
    erro, form = "", {}
    if request.method == "POST":
        erro, form = _enviar_sugestao(S, areas)
        if not erro:
            session[_CHAVE_AVISO] = "Sugestão enviada. Os administradores do Nexus recebem e leem por aqui."
            return redirect(url_for("casca.inicio", aba="sugestoes"))
    usuario = session.get("usuario") if isinstance(session.get("usuario"), dict) else {}
    recebidas, erro_lista = [], ""
    if admin:
        todas = {t.id: t.nome for t in current_app.extensions["nexus_torres"]}
        recebidas, erro_lista = S.lista(todas), S.ler()["erro"]
    resp = render_template("sugestoes.html", aba="sugestoes", areas=areas, form=form, erro=erro,
                           aviso=session.pop(_CHAVE_AVISO, None), codigo=_codigo(), novo_id=S.novo_id(),
                           tem_login=bool(str(usuario.get("email") or "").strip()), faltam=S.faltam_chaves(),
                           admin=admin, recebidas=recebidas, erro_lista=erro_lista, aceitos=S.aceitos(),
                           max_mb=S.MAX_MB_ARQUIVO, max_arquivos=S.MAX_ARQUIVOS, max_total=S.MAX_MB_TOTAL,
                           titulo_max=S.TITULO_MAX, texto_max=S.TEXTO_MAX)
    return resp, (400 if erro else 200)


def _enviar_sugestao(S, areas: dict) -> tuple[str, dict]:
    """(erro, o que a pessoa digitou). O tamanho é conferido antes de ler o corpo: um pedido maior que o limite não
    chega a ocupar a memória nem o disco do servidor."""
    from ..torres.moldura import _de_outro_site
    if _de_outro_site():
        return "Pedido de outro site: nada foi enviado.", {}
    teto = S.MAX_MB_TOTAL * S.MB + S.MB             # os anexos + o texto do formulário, com folga
    if (request.content_length or 0) > teto:
        return (f"Os anexos passam de {S.MAX_MB_TOTAL} MB juntos, o limite por sugestão. Nada foi enviado.", {})
    request.max_content_length = teto                  # o corpo sem tamanho declarado também para no teto
    try:
        form = {k: request.form.get(k, "") for k in ("titulo", "area", "descricao", "novo_id")}
        arquivos = [(f.filename, f.stream) for f in request.files.getlist("anexos")]
    except RequestEntityTooLarge:
        return f"Os anexos passam de {S.MAX_MB_TOTAL} MB juntos, o limite por sugestão. Nada foi enviado.", {}
    certo = session.get(_CHAVE_CODIGO) or ""
    enviado = request.form.get("codigo") or ""
    if not certo or not hmac.compare_digest(enviado.encode(), certo.encode()):
        return "O formulário venceu (a sessão mudou desde que a tela abriu): abra a aba de novo. Nada foi enviado.", form
    usuario = session.get("usuario") if isinstance(session.get("usuario"), dict) else {}
    try:
        S.criar(form, arquivos, usuario, areas)
    except S.Recusada as ex:
        return f"{ex}. Nada foi enviado{'; anexe os arquivos de novo' if arquivos else ''}.", form
    except Exception as ex:      # noqa: BLE001 — banco fora, rede: a pessoa sabe que não foi
        current_app.logger.exception("sugestão não gravada")
        return (f"Não consegui gravar agora ({type(ex).__name__}). Tente de novo em instantes"
                f"{'; anexe os arquivos de novo' if arquivos else ''}.", form)
    return "", form


def _anexo_da_sugestao(S, admin: bool):
    """`/?aba=sugestoes&anexo=<id>&n=<n>`: só o administrador baixa. Imagem abre no navegador; o resto baixa. Com
    `n=todos` (o "Baixar arquivos", 24/10/2026), todos os anexos da sugestão num .zip."""
    if not admin:
        abort(403)
    if request.args.get("n") == "todos":
        pacote = S.zip_da_sugestao(request.args.get("anexo"))
        if not pacote:
            abort(404)
        dados, nome = pacote
        resp = send_file(io.BytesIO(dados), mimetype="application/zip", as_attachment=True, download_name=nome,
                         max_age=0)
        resp.headers["Cache-Control"] = "private, no-store"
        return resp
    achado = S.arquivo(request.args.get("anexo"), request.args.get("n"))
    if not achado:
        abort(404)
    caminho, a = achado
    imagem = S.eh_imagem(a["arquivo"])
    resp = send_file(caminho, mimetype=S.tipo_servido(a["arquivo"]), as_attachment=not imagem,
                     download_name=a.get("nome") or a["arquivo"], max_age=0)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


def _atualizacoes():
    """A aba Atualizações do Início (13/10/2026, Levi: "Inclua no início uma sub aba de atualizações mostrando as últimas
    atualizações dos commits e o que mudou! Ao clicar em versão no ar já leva para lá!"): por dia, com o que mudou; desde
    19/10/2026 só novidade e correção dos últimos 60 dias (`versao.da_aba`)."""
    historico = versao.historico()
    itens = versao.da_aba(historico)
    return render_template("atualizacoes.html", dias=versao.dias(itens), total=len(itens), tem_git=bool(historico),
                           janela=versao.JANELA_DIAS, no_ar=versao.local()["sha"],
                           versao=versao.cartao(current_app._get_current_object()), aba="atualizacoes")


@bp.route("/tema", methods=["POST"])
def tema():
    """A troca de tema sem JavaScript (o botão do topo é um formulário). Com JavaScript a troca é na hora, no navegador,
    que grava o mesmo cookie; aqui ele é gravado pelo servidor e a pessoa volta para a mesma tela."""
    escolhido = request.form.get("tema", "")
    if escolhido not in TEMAS:
        abort(400)
    resp = redirect(destino_seguro(request.form.get("voltar")))
    # sem HttpOnly de propósito: o botão troca o tema no navegador e grava este mesmo cookie
    resp.set_cookie(COOKIE_TEMA, escolhido, max_age=UM_ANO_S, path="/", samesite="Lax",
                    secure=bool(current_app.config.get("SESSION_COOKIE_SECURE")))
    return resp


@bp.route("/saude")
def saude():
    # Público de propósito (monitoramento do servidor). Não diz nada além de "está de pé" e o commit.
    return jsonify(ok=True, commit=_commit())


def instalar_contexto(app) -> None:
    @app.context_processor
    def _contexto():
        blueprint = request.blueprint or ""
        torre_atual = blueprint.removeprefix("torre_") if blueprint.startswith("torre_") else None
        a = setor_telas.acesso()
        return {
            "menu": montar_menu(app.extensions["nexus_torres"], torre_atual, _telas_prontas(app),
                                None if a["tudo"] else a["telas"]),
            # o setor da pessoa, no topo (Base → Acessos → Pessoas e setores); o administrador sem setor não mostra nada
            "setor": a["setor"],
            "caminho": request.path,
            # a volta do formulário do tema (sem JavaScript) para a mesma tela, com os filtros
            "caminho_completo": request.full_path.rstrip("?"),
            "tema": tema_do_pedido(),
            # o prefixo em que o Nexus roda ('' na raiz, '/nexus' no servidor): todo href/src/action absoluto dos templates
            # começa por ele, e o JavaScript o recebe em window.NEXUS_RAIZ (_raiz_js.html). Ver nexus/prefixo.py
            "raiz": raiz(),
        }

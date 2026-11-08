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
                           versao=versao.cartao(app), aba="inicio", sug_abertas=_sugestoes_abertas())


def _torres_da_pessoa() -> list:
    """Só as torres que o setor da pessoa vê (o administrador vê tudo)."""
    liberadas = setor_telas.liberadas_do_menu()
    return [t for t in current_app.extensions["nexus_torres"]
            if liberadas is None or any(f"{t.id}/{s.id}" in liberadas for s in t.telas)]


# ── Sugestões (24/10/2026) ───────────────────────────────────────────────────────────────────────────────────────────
_CHAVE_CODIGO, _CHAVE_AVISO, _CHAVE_AVISO_STATUS = "sugestoes_codigo", "sugestoes_aviso", "sugestoes_aviso_status"


def _codigo() -> str:
    """O código do formulário desta sessão (o login limpa a sessão e troca o código): outro site não o conhece."""
    if not session.get(_CHAVE_CODIGO):
        session[_CHAVE_CODIGO] = secrets.token_urlsafe(24)
    return session[_CHAVE_CODIGO]


def _email_da_sessao() -> str:
    u = session.get("usuario")
    return str(u.get("email") or "").strip().lower() if isinstance(u, dict) else ""


def _sugestoes_abertas():
    """O número ao lado de "Sugestões" nas abas do Início (28/10/2026): as não concluídas (de todos, para o
    administrador; as da pessoa, para ela). Nunca segura a página: sem a cópia, a aba sai sem número."""
    from . import sugestoes as S
    try:
        return S.contador(bool(session.get("admin")), _email_da_sessao())
    except Exception:            # noqa: BLE001 — o contador nunca derruba o Início
        current_app.logger.exception("contador das sugestões")
        return None


def _sugestoes():
    """A aba Sugestões: o formulário para todos (título, área entre as torres que a pessoa vê, descrição e anexos) e,
    para o administrador, a lista de tudo o que chegou, com quem pediu e os anexos (`casca/sugestoes.py`)."""
    from . import sugestoes as S
    admin = bool(session.get("admin"))
    if request.args.get("anexo"):
        return _anexo_da_sugestao(S, admin)
    areas = {t.id: t.nome for t in _torres_da_pessoa()}
    erro, form = "", {}
    # a troca do status vem pelo endereço (?acao=status), e não pelo corpo: ler o corpo antes da conta do tamanho do envio
    # das sugestões tiraria dela a recusa do pedido grande sem ler
    if request.method == "POST" and request.args.get("acao") == "status":
        return _mudar_status_sugestao(S, admin)
    if request.method == "POST":
        erro, form = _enviar_sugestao(S, areas)
        if not erro:
            session[_CHAVE_AVISO] = "Sugestão enviada. Os administradores do Nexus recebem e leem por aqui."
            return redirect(url_for("casca.inicio", aba="sugestoes"))
    usuario = session.get("usuario") if isinstance(session.get("usuario"), dict) else {}
    email = _email_da_sessao()
    recebidas, minhas, erro_lista = [], [], ""
    todas = {t.id: t.nome for t in current_app.extensions["nexus_torres"]}
    if (admin or email) and not S.faltam_chaves():
        lista = S.lista(todas)
        erro_lista = S.ler()["erro"]
        if admin:
            # as que faltam concluir primeiro (a mais nova no alto), as concluídas depois
            recebidas = sorted(lista, key=lambda x: x["status"] == "concluida")
        # Minhas sugestões (28/10/2026, Levi: "Do lado direito tem um espaço para 'Minhas sugestões' - a pessoa consegue
        # ver o que mandou e qual status está"): pelo código do e-mail, em claro no livro
        if email:
            from ..cadastro.ligacao_campo import codigo_da_pessoa
            meu = (codigo_da_pessoa(current_app.config.get("NEXUS_PESSOA_HMAC"), email) or "").lower()
            minhas = [x for x in lista if meu and x["pessoa_hmac"] == meu]
    resp = render_template("sugestoes.html", aba="sugestoes", areas=areas, form=form, erro=erro,
                           aviso=session.pop(_CHAVE_AVISO, None), codigo=_codigo(), novo_id=S.novo_id(),
                           tem_login=bool(str(usuario.get("email") or "").strip()), faltam=S.faltam_chaves(),
                           admin=admin, recebidas=recebidas, minhas=minhas, erro_lista=erro_lista,
                           aceitos=S.aceitos(), status_mudaveis=[(k, S.STATUS[k][0]) for k in S.STATUS_MUDAVEIS],
                           aviso_status=session.pop(_CHAVE_AVISO_STATUS, None),
                           sug_abertas=_sugestoes_abertas(),
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


def _mudar_status_sugestao(S, admin: bool):
    """`POST /?aba=sugestoes` com `acao=status`: o administrador muda o status (Iniciada, Em verificação, Concluída). A
    resposta volta à aba, com o aviso (deu certo ou não) no alto da lista."""
    from ..torres.moldura import _de_outro_site
    if not admin:
        abort(403)
    certo = session.get(_CHAVE_CODIGO) or ""
    enviado = request.form.get("codigo") or ""
    if _de_outro_site() or not certo or not hmac.compare_digest(enviado.encode(), certo.encode()):
        session[_CHAVE_AVISO_STATUS] = ("erro", "O formulário venceu (a sessão mudou desde que a tela abriu): abra a aba "
                                                "de novo. O status não mudou.")
        return redirect(url_for("casca.inicio", aba="sugestoes"))
    usuario = session.get("usuario") if isinstance(session.get("usuario"), dict) else {}
    sid = request.form.get("sugestao")
    try:
        S.mudar_status(sid, request.form.get("status"), usuario)
        session[_CHAVE_AVISO_STATUS] = ("ok", f"Status mudado para {S.STATUS[request.form.get('status')][0]}.")
    except S.Recusada as ex:
        session[_CHAVE_AVISO_STATUS] = ("erro", f"{ex}. O status não mudou.")
    except Exception as ex:      # noqa: BLE001 — banco fora: a pessoa sabe que não foi
        current_app.logger.exception("status da sugestão não gravado")
        session[_CHAVE_AVISO_STATUS] = ("erro", f"Não consegui gravar agora ({type(ex).__name__}). O status não mudou.")
    return redirect(url_for("casca.inicio", aba="sugestoes") + f"#sug-{sid}")


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
                           janela=versao.JANELA_DIAS, no_ar=versao.local()["sha"], conta=versao.contagem,
                           versao=versao.cartao(current_app._get_current_object()), aba="atualizacoes",
                           sug_abertas=_sugestoes_abertas())


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


@bp.route("/t/base/paleta")
def paleta():
    """A Paleta Nexus (04/11/2026): o escuro ao lado do claro, token a token. Só administradores (Levi: "ao clicar no
    nome da pessoa aparecer 'paleta nexus' só para os administradores"). Mora em /t/base/ porque o Caddy do servidor só
    manda ao Nexus a raiz, /t/* e poucos outros caminhos (tests/test_rotas_no_caminho_do_nexus.py)."""
    if not session.get("admin"):
        abort(403)
    from . import paleta_tokens as PA
    escuro, claro, grupos = PA.grupos()
    return render_template("paleta.html", escuro=escuro, claro=claro, grupos=grupos)


def _vista_cliente(menu: list[dict]) -> dict | None:
    """O menu lateral do cliente (e do administrador no Modo cliente), no desenho do mockup da Visão do cliente
    (08/11/2026, Levi: "a ideia é ter uma visão parecida com essa para o cliente"): no alto, o cliente e "acesso de
    cliente · só leitura"; a Visão do cliente vira o item **Comando**, o primeiro; torre com uma tela só vira um item com
    o nome da tela (Rondas); com mais de uma, o grupo da torre (Segurança: Extintores, EPI e EPC). Sem o Início: o Início
    do cliente já é o Comando. None para quem não é cliente."""
    modo = setor_telas.em_modo_cliente()
    if session.get("via") != "cliente" and not modo:
        return None
    nome = (session.get("modo_cliente") or {}).get("nome") if modo else (session.get("usuario") or {}).get("nome")
    itens, comando = [], None
    for t in menu:
        telas = []
        for s in t["telas"]:
            if f"/t/{t['id']}/{s['id']}" == "/t/campo/cliente":
                comando = {"tipo": "item", "nome": "Comando", "url": s["url"], "icone": "gauge", "filhas": s["filhas"]}
            else:
                telas.append(s)
        if len(telas) == 1:
            s = telas[0]
            itens.append({"tipo": "item", "nome": s["nome"], "url": s["url"], "icone": t["icone"], "filhas": s["filhas"]})
        elif telas:
            itens.append({"tipo": "grupo", "nome": t["nome"], "icone": t["icone"], "id": t["id"], "aberta": t["aberta"],
                          "telas": telas})
    return {"nome": nome or "Cliente", "modo": modo, "itens": ([comando] if comando else []) + itens}


# ── o Modo cliente (07/11/2026) ──────────────────────────────────────────────────────────────────────────────────
# Levi: "Ao clicar no nome deles e abrir o menu lateral ter um 'Modo Cliente' aí aparecer um card na frente dando um blur
# de fundo pedindo para escolher o cliente. No menu lateral também tem que ter 'sair do modo cliente'". O administrador
# vê o Nexus como o cliente escolhido veria (as telas do setor Clientes, com as usinas dele: `setor_telas.portao_cliente`
# e `cliente_da_sessao`). Moram em /t/base/ porque o Caddy só manda ao Nexus a raiz, /t/* e poucos outros.
_CODIGO_CASCA = "casca_codigo"


def _codigo_casca() -> str:
    if not session.get(_CODIGO_CASCA):
        session[_CODIGO_CASCA] = secrets.token_urlsafe(24)
    return session[_CODIGO_CASCA]


def _form_da_casca_ok() -> bool:
    from ..torres.moldura import _de_outro_site
    certo, enviado = session.get(_CODIGO_CASCA) or "", request.form.get("codigo") or ""
    return not _de_outro_site() and bool(certo) and hmac.compare_digest(enviado.encode(), certo.encode())


def _clientes_do_cadastro() -> list[dict]:
    """[{id, nome, usinas}] do cadastro do Nexus, em ordem de nome (o mesmo recorte da Visão do cliente: cliente_id da
    usina)."""
    from ..campo import visao
    from ..dados import fatos as D
    b = visao._Base()
    usinas: dict = {}
    for u in b.por_id.values():
        cid = D._id(u.get("cliente_id"))
        if cid:
            usinas[cid] = usinas.get(cid, 0) + 1
    return sorted(({"id": i, "nome": n, "usinas": usinas.get(i, 0)} for i, n in b.nome_cliente.items() if i and n),
                  key=lambda c: c["nome"].lower())


@bp.route("/t/base/modo-cliente/clientes")
def modo_cliente_clientes():
    """A lista do card de escolha (pedida só quando o card abre)."""
    if not session.get("admin"):
        abort(403)
    try:
        return jsonify(ok=True, clientes=_clientes_do_cadastro())
    except Exception as ex:      # noqa: BLE001 — sem o cadastro, o card diz por quê
        return jsonify(ok=False, clientes=[], erro=f"Não consegui ler os clientes do cadastro ({type(ex).__name__})")


@bp.route("/t/base/modo-cliente", methods=["POST"])
def modo_cliente_entrar():
    """Entra (ou troca) no Modo cliente e leva ao Início do cliente, que abre a 1ª tela dele."""
    if not session.get("admin"):
        abort(403)
    if not _form_da_casca_ok():
        abort(403)
    cid = request.form.get("cliente_id", type=int)
    try:
        cliente = next((c for c in _clientes_do_cadastro() if c["id"] == cid), None)
    except Exception:            # noqa: BLE001
        cliente = None
    if not cliente:
        abort(400)
    session["modo_cliente"] = {"id": cliente["id"], "nome": cliente["nome"]}
    current_app.logger.info("Modo cliente: %s vendo como %s.", (session.get("usuario") or {}).get("email") or
                            "senha de administrador", cliente["nome"])
    return redirect(url_for("casca.inicio"), code=303)


@bp.route("/t/base/modo-cliente/sair", methods=["POST"])
def modo_cliente_sair():
    if not _form_da_casca_ok():
        abort(403)
    session.pop("modo_cliente", None)
    return redirect(url_for("casca.inicio"), code=303)


@bp.route("/saude")
def saude():
    # Público de propósito (monitoramento do servidor). Não diz nada além de "está de pé" e o commit.
    return jsonify(ok=True, commit=_commit())


def _sino():
    """O sino do topo (03/11/2026, os setores conversando): os avisos das OS da pessoa (04/11/2026), os pedidos mandados às
    torres dela que ainda esperam resposta ou passaram do prazo (Fase 3) e as menções a ela ou ao setor dela que ainda não
    leu (Fase 2). Os insights sem dono saíram dele em 04/11/2026 (Levi: "tira insights sem dono do sino"): eram mais de mil
    e escondiam o resto; ficam na Caixa de entrada. Só lê as cópias (a do motor, a das conversas, a dos pedidos e a dos
    avisos): nenhuma página espera uma fonte por causa dele. Sem nenhuma cópia (logo depois de subir), não sai número, e a
    conta começa por trás."""
    # o cliente (07/11/2026) não vê insights, pedidos nem menções da Grid; o administrador no Modo cliente também não
    if not session.get("logado") or session.get("via") == "cliente" or setor_telas.em_modo_cliente():
        return None
    try:
        from ..comando import conversa as CV
        from ..comando import motor as MO
        from ..comando import pedidos as PD
        g = MO.do_cache()
        l_conv, _l_est, l_ped = CV.copias()
        avisos = _avisos_do_sino()
        if (not g or not g.dados) and not l_conv and not l_ped and not avisos:
            return None
        torres = MO.torres_da_pessoa()
        todos = (g.dados.get("insights") or []) if g and g.dados else []
        titulo = {"insight:" + i["id"]: i["titulo"] for i in todos}     # o nome do insight citado num pedido ou numa menção

        def _titulo(ob):
            tipo, _, oid = ob.partition(":")
            return titulo.get(ob) or (f"OS {oid}" if tipo == "os" else "Uma usina" if tipo == "usina" else f"Insight {oid}")
        # os pedidos para as minhas áreas que ainda esperam resposta ou passaram do prazo (sem o texto: a cópia do sino
        # não decifra), o mais atrasado primeiro
        pedidos = [{"link": "/t/comando/conversa/" + p["objeto"].replace(":", "/", 1), "titulo": _titulo(p["objeto"]),
                    "sit_rotulo": p["sit_rotulo"], "sit_tom": p["sit_tom"], "atrasado": p["situacao"] == "atrasado"}
                   for p in sorted(PD.pedidos(l_ped).values(), key=PD.ordem)
                   if (torres is None or p["torre"] in torres)
                   and (p["status"] == "pendente" or p["situacao"] == "atrasado")]
        # e as menções que ainda não li
        from ..torres.comando import _meu_hmac
        mencoes = []
        for x in CV.para_mim(CV.conversas(l_conv), _meu_hmac(), torres):
            tipo, _, oid = x["objeto"].partition(":")
            mencoes.append({"link": "/t/comando/conversa/" + tipo + "/" + oid, "n": x["n"],
                            "titulo": _titulo(x["objeto"])})
        # o botão do topo leva o ícone do OS Creator do menu lateral, no lugar do sino (Levi, 04/11/2026: "quero que troque
        # esse símbolo de sino pelo símbolo do OS Creator"): lido da torre, para os dois nunca divergirem
        icone_os = next((t.icone for t in current_app.extensions.get("nexus_torres", []) if t.id == "os"), "clipboard-text")
        return {"n": len(mencoes) + len(pedidos) + len(avisos), "criticos": sum(1 for p in pedidos if p["atrasado"]),
                "mencoes": mencoes[:6], "n_mencoes": len(mencoes), "pedidos": pedidos[:6], "n_pedidos": len(pedidos),
                "avisos": avisos[:8], "n_avisos": len(avisos), "icone_os": icone_os}
    except Exception:            # noqa: BLE001 — o sino nunca derruba uma página
        current_app.logger.exception("sino dos insights")
        return None


def _avisos_do_sino() -> list:
    """Os avisos não lidos das OS da pessoa (04/11/2026, `comando/avisos.py`): "OS x concluída pelo técnico" e "Sua
    solicitação gerou uma OS". A falha aqui não tira o resto do sino."""
    try:
        from ..comando import avisos as AV
        return AV.para_o_sino(session.get("usuario"))
    except Exception:            # noqa: BLE001
        current_app.logger.exception("sino: os avisos das OS")
        return []


@bp.route("/t/comando/aviso/lida", methods=["POST"])
def avisos_lida():
    """O "Marcar como lida" do sino, de um aviso (`aviso`) ou de todos os que ele mostra (`todos=1`). Formulário sem
    JavaScript, como o tema: grava e volta para a mesma tela. O que não gravou (o banco fora, o login sem e-mail) volta com o
    motivo no log, e o aviso segue no sino.
    Mora em /t/comando/ porque o Caddy do servidor só manda ao Nexus a raiz, /t/* e poucos outros caminhos: nasceu em
    /avisos/lida e no servidor caía na plataforma (tests/test_rotas_no_caminho_do_nexus.py). O portão por setor abre o
    caminho a quem tem uma tela do Comando, e a Caixa de entrada é de todo setor. "aviso" no singular, como insight/acao e
    pedido/acao: uma tela "avisos" no Comando casaria com o caminho e trancaria quem não a tem."""
    from ..comando import avisos as AV
    usuario = session.get("usuario")
    ids = request.form.getlist("aviso")
    if request.form.get("todos") == "1":
        ids = [a["id"] for a in AV.para_o_sino(usuario)]
    # o sino da página pede por fetch e espera JSON (Levi, 05/11/2026: "cada vez que clico em marcar como lida a tela
    # atualiza... atrapalha a experiência do usuário"): grava e responde, sem recarregar; o formulário sem JavaScript volta
    quer_json = "application/json" in (request.headers.get("Accept") or "")
    try:
        n = AV.marcar_lidos(usuario, ids)
    except AV.Recusada as ex:
        current_app.logger.warning("sino: os avisos não foram marcados como lidos: %s", ex)
        if quer_json:
            return jsonify({"ok": False, "erro": str(ex)}), 400
    except Exception:            # noqa: BLE001 — banco fora: o aviso segue no sino
        current_app.logger.exception("sino: os avisos não foram marcados como lidos")
        if quer_json:
            return jsonify({"ok": False, "erro": "O banco não respondeu: o aviso segue no sino."}), 503
    else:
        if quer_json:
            return jsonify({"ok": True, "lidos": n})
    return redirect(destino_seguro(request.form.get("voltar")))


def instalar_contexto(app) -> None:
    @app.context_processor
    def _contexto():
        blueprint = request.blueprint or ""
        torre_atual = blueprint.removeprefix("torre_") if blueprint.startswith("torre_") else None
        a = setor_telas.acesso()
        menu = montar_menu(app.extensions["nexus_torres"], torre_atual, _telas_prontas(app),
                           None if a["tudo"] else a["telas"])
        return {
            "menu": menu,
            # o setor da pessoa, no topo (Base → Acessos → Pessoas e setores); o administrador sem setor não mostra nada
            "setor": a["setor"],
            "caminho": request.path,
            # a volta do formulário do tema (sem JavaScript) para a mesma tela, com os filtros
            "caminho_completo": request.full_path.rstrip("?"),
            "tema": tema_do_pedido(),
            # o prefixo em que o Nexus roda ('' na raiz, '/nexus' no servidor): todo href/src/action absoluto dos templates
            # começa por ele, e o JavaScript o recebe em window.NEXUS_RAIZ (_raiz_js.html). Ver nexus/prefixo.py
            "raiz": raiz(),
            # o sino dos insights (03/11/2026), só das cópias: ver `_sino`
            "sino": _sino(),
            # o Modo cliente do administrador (07/11/2026): o cliente que ele está vendo, e o código dos formulários
            # (`cliente_modo`, não `modo_cliente`: a Visão do cliente passa o seu próprio `modo_cliente`, que venceria)
            "cliente_modo": session.get("modo_cliente") if setor_telas.em_modo_cliente() else None,
            # o que o cliente vê no menu lateral (08/11/2026, o mockup da Visão do cliente): o cliente e "Comando"
            "vista_cliente": _vista_cliente(menu),
            "codigo_casca": _codigo_casca() if session.get("admin") else "",
        }

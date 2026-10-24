"""Torre Segurança · HSEQ: a Mesa da Segurança, Extintores, EPI e EPC, Riscos da semana, APR e PT, DSS e incidentes.

A Mesa da Segurança (24/10/2026) é a primeira tela, do setor Segurança, como a Mesa do engenheiro: o que pede ação hoje
(PT parada, extintor vencido ou não reconhecido, usina sem luvas), cada painel levando à tela de origem já filtrada.

Extintores (09/10/2026) é visão nossa (`nexus/hseq/extintores.py`), pelo livro que o App de Campo grava no banco, com
os filtros próprios desde 18/10/2026 (cliente, usina, responsável UFV, equipe e a busca, em cascata; `FILTROS_EXT`).
A Segurança decide ali os não reconhecidos (aceitar ou pedir nova ronda) e a quantidade de extintores de cada usina
(`nexus/hseq/decisoes.py`, o livro `nexus_hseq_extintores`). No EPI (24/10/2026) os cartões são por Responsável O&M da
usina, com as usinas dele, e os filtros são a região do Brasil, o cliente, o responsável UFV e a busca: saíram a região
de campo e o gestor de contrato, e com eles o filtro que vinha do login.

As outras telas ainda caem no placeholder da casca (view com a mesma rota vence a genérica). Leia o CLAUDE.md desta
pasta antes de mexer.
"""
import re
import unicodedata

from urllib.parse import urlencode

from flask import Response, abort, current_app, jsonify, redirect, render_template, request, session

from ...campo import visao
from ...hseq import decisoes as DEC
from ...hseq import epi as EPI
from ...hseq import extintores as EXT
from ...hseq import fotos as FOT
from ...hseq import planilha as PLA
from ...hseq import relatorio as REL
from ..campo import _lido, _url
from ..modelo import Tela, Torre
from ...prefixo import na_raiz

TORRE = Torre(
    id="hseq",
    nome="Segurança · HSEQ",
    ordem=100,
    icone="shield-check",
    descricao="Extintores, EPI e EPC, riscos da semana, APR e PT, DSS e incidentes.",
    telas=[
        # a primeira tela da Segurança (Levi, 24/10/2026: "Criação de mesa da segurança, como PTs atrasadas, extintores
        # vencidos, usinas sem luvas"), do setor Segurança: quem é dele a vê sem marcar em Base → Acessos
        Tela("mesa", "Mesa da Segurança",
             "O que pede ação hoje: PT parada, extintor vencido ou não reconhecido e usina sem luvas?",
             "PT do App, extintores e rondas do App + cadastro do Nexus", do_setor="Segurança"),
        Tela("extintores", "Extintores",
             "Que extintor está vencido, perto de vencer ou sem conferência há mais de 30 dias, em que cliente e usina, "
             "e com qual responsável?",
             "Ronda de extintores do App de Campo (livro extintores_app_campo) + cadastro do Nexus"),
        Tela("epi", "EPI e EPC",
             "Que usina está sem as luvas isolantes, segundo a última ronda diária?",
             "Rondas diárias do App de Campo (o item das luvas isolantes do checklist) + cadastro do Nexus"),
        Tela("riscos", "Riscos da semana",
             "Que atividade da semana está liberada, condicionada ou bloqueada?",
             "Programação do PCM + Semanal de Segurança"),
        # as Permissões de trabalho do Campo · App vieram para cá em 09/10/2026 (Levi: "quero que esse visual e caminho
        # vá para APR e PT de Segurança · HSEQ"; "precisamos ter a visão também de APR")
        Tela("apr-pt", "APR e PT",
             "Que PT está esperando o De acordo, e há quanto tempo? Onde estão a PT e a APR de cada tarefa?",
             "Livro de PT do App + os PDFs da PT e da APR no Fracttal"),
        Tela("dss", "DSS",
             "Todos os clusters fizeram o DSS?",
             "Registros de DSS"),
        Tela("incidentes", "Incidentes",
             "Que quase acidente ou desvio ainda está sem ação?",
             "Registros de incidentes"),
    ],
)

bp = TORRE.criar_blueprint(__name__)

# onde a busca procura: o nome do cadastro e o que o App escreveu, o código, o local, o ativo, a cidade e a equipe
BUSCA = ("usina", "usina_fonte", "codigo", "local", "ativo", "classe", "cidade", "equipe")
LIMITE_LINHAS = 300
# Os filtros de Extintores (Levi, 18/10/2026: "De filtros quero apenas cliente, usina, responsável UFV, equipe e o campo
# para digitar!"), na ordem da tela, com o rótulo. Saíram a região do Brasil, a região de campo e o gestor de contrato, e
# com eles o filtro que já vinha marcado pelo login (o Supervisor de Campo abria na região dele): ninguém abre filtrado.
# O "Responsável UFV" é o Responsável O&M da ficha da usina (o setor "Responsáveis UFV" de Base → Acessos).
FILTROS_EXT = (("cliente", "Cliente"), ("usina", "Usina"), ("responsavel", "Responsável UFV"), ("equipe", "Equipe"))
# os filtros da tela que o "Baixar" de cada usina repete (a usina vai no próprio link)
FILTROS_URL = ("cliente", "responsavel", "equipe", "q", "f")


def _clientes(linhas) -> list[str]:
    """Os clientes do filtro (Levi, 09/10/2026: "Em extintores quero um filtro por cliente!"): os do cadastro, pela
    usina, das linhas da tela."""
    return sorted({x.get("cliente") for x in linhas if x.get("cliente")})


def _opcoes_ext(linhas, escolhidos: dict, passa) -> dict:
    """{filtro: [valores]}: cada lista mostra o que existe com os OUTROS filtros aplicados (em cascata, como a tela
    Técnicos por usina do PCM: escolhido o cliente, a lista de usinas traz só as dele), e a opção escolhida fica mesmo
    sem resultado. Os "Sem ..." vão por último."""
    out = {}
    for campo, _rot in FILTROS_EXT:
        vals = {EXT.valor_do_filtro(x, campo) for x in linhas if passa(x, campo)}
        if escolhidos[campo]:
            vals.add(escolhidos[campo])
        out[campo] = sorted(vals, key=lambda v: (v == EXT.SEM_VALOR.get(campo), v.lower()))
    return out


# o filtro de Status (Levi, 24/10/2026: "Adicione também um filtro de status, caso a pessoa queira ver só os vencidos,
# só os sem validade, só os não reconhecidos etc. Insira não reconhecidos no status também!"): o mesmo `f` da faixa
STATUS = (("atrasado", "Atrasados"), ("perto", "Perto de vencer"), ("sem_validade", "Sem validade"), ("em_dia", "Em dia"),
          ("sem_atualizacao", "Sem atualização"), ("nao_reconhecido", "Não reconhecidos"))
NR = "nao_reconhecido"


def _status() -> str:
    f = request.args.get("f", "")
    return f if f in dict(STATUS) else ""


def _lista(base, f) -> list:
    """Os extintores do filtro de Status (o não reconhecido não tem situação: com ele, nenhum dos outros)."""
    return [] if f == NR else [x for x in base if not f or x[f]]


def _filtrados():
    """A leitura e os extintores com os filtros da tela (cliente, usina, responsável UFV, equipe e busca): a tela e o
    relatório contam o mesmo. Os não reconhecidos em campo (14/10/2026) vêm à parte, com os mesmos filtros: estão fora
    de todas as contas (`extintores.nao_reconhecido`). Os excluídos pela Segurança (24/10/2026) saem das duas listas
    (`decisoes.separar`) e vão para o histórico (`fl["excluidos"]`)."""
    leitura = EXT.extintores()
    d = leitura.dados
    fl = {c: request.args.get(c, "").strip() for c, _rot in FILTROS_EXT}
    q = request.args.get("q", "").strip().lower()

    def passa(x, menos=None):
        return (all(not v or c == menos or EXT.valor_do_filtro(x, c) == v for c, v in fl.items())
                and (not q or q in " ".join(str(x.get(c) or "") for c in BUSCA).lower()))
    todas, seguem, excluidos = DEC.separar(d.get("extintores") or [], d.get("nao_reconhecidos") or [], _decisoes())
    base = [x for x in todas if passa(x)]
    nao_rec = [x for x in seguem if passa(x)]
    opcoes = _opcoes_ext(todas + seguem, fl, passa)
    return leitura, d, todas, base, nao_rec, dict(fl, opcoes=opcoes, excluidos=excluidos, passa=passa, seguem=seguem)


def _decisoes() -> dict:
    """As decisões da Segurança (cache de 1 minuto); sem ler, nenhuma (e a tela diz: `decisoes_erro`)."""
    return DEC.ler(current_app.config)


def _pode() -> bool:
    """Excluir extintor, aceitar o não reconhecido e pedir nova ronda: o administrador e quem é do setor Segurança."""
    from ...auth import setor_telas as ST
    return DEC.pode_decidir((ST.acesso() or {}).get("setor"), bool(session.get("admin")))


def _url_ext(**mudar) -> str:
    """O `_url` do Campo sem o aviso da última gravação (`ok`, `erro`): ele não segue nos links da tela."""
    return _url(ok=None, erro=None, **mudar)


def _rondas(est, todas, seguem) -> dict:
    """Os pedidos de nova ronda ainda pendentes (`decisoes.rondas_pendentes`): os extintores atuais de cada usina, sem
    os excluídos e sem os filtros da tela, e a hora em que o App recebeu cada conferência. Sem pedido, nada se lê."""
    if not est.get("rondas"):
        return {}
    por_usina = {}
    for x in todas + seguem:
        if x.get("usina_id"):
            por_usina.setdefault(x["usina_id"], []).append(x)
    return DEC.rondas_pendentes(est, por_usina, EXT.recebidas().dados or {})


def _historico(d, fl) -> list[dict]:
    """O histórico de excluídos (Levi, 24/10/2026: "vai para um histórico de extintores excluídos com o motivo 'Não
    reconhecido em campo'"), com os filtros da tela: a usina, o cliente e o responsável pela linha do extintor ou, se o
    App já o tirou do livro, pelo cadastro do Nexus (`usina_id`)."""
    por_codigo = {x["codigo"]: x for x in (d.get("extintores") or []) + (d.get("nao_reconhecidos") or [])}
    linhas, b = DEC.historico(current_app.config, _decisoes(), por_codigo), None
    out = []
    for h in linhas:
        e = h["ext"]
        if e is None:
            b = b or visao._Base()
            e = {"codigo": h["codigo"], "ext": h["codigo"].rsplit("-", 1)[-1], "usina_id": h["usina_id"],
                 **(b.onde(h["usina_id"]) if h["usina_id"] else {"usina": ""})}
        if fl["passa"](e):
            out.append(dict(h, ext=e))
    return out


MESA_VISOES = (("responsavel", "Por responsável"), ("cliente", "Por cliente"))


def _grupo(x, chave) -> str:
    return EXT.valor_do_filtro(x, chave)


def _espera(minutos) -> str:
    """Quanto tempo a PT espera, para quem lê a Mesa: minutos, horas e, de 2 dias em diante, dias."""
    m = int(minutos or 0)
    return f"{m} min" if m < 60 else (f"{m // 60} h" if m < 48 * 60 else f"{m // 1440} dias")


@bp.route("/mesa")
def mesa():
    """A Mesa da Segurança (Levi, 24/10/2026: "Criação de mesa da segurança, como PTs atrasadas, extintores vencidos,
    usinas sem luvas"), por grupos (2ª rodada, no mesmo dia: "quero duas visões: Por responsável e cliente (...) não
    queria em formato de lista mas em agrupamentos para o TST saber onde atacar!"): a faixa com os quatro números e um
    cartão por Responsável O&M (ou por cliente), com os quatro números dele, o que tem mais primeiro; cada número leva à
    tela de origem filtrada pelo grupo. Só lê; a fonte que falha diz e o número dela vira "—", sem derrubar as outras."""
    chave = "cliente" if request.args.get("ver") == "cliente" else "responsavel"
    erros, lido = {}, ""
    pts, atr, nrs, luv, semv = [], [], [], [], 0
    try:
        lp = visao.pts()
        lido = _lido(lp)
        if lp.erro:
            erros["pts"] = lp.erro
        else:
            pts = [x for x in (lp.dados or {}).get("aguardando") or [] if x.get("parada")]
    except Exception as e:      # noqa: BLE001 — uma fonte fora não derruba a mesa
        erros["pts"] = type(e).__name__
    try:
        le = EXT.extintores()
        if le.erro or not (le.dados or {}).get("aba_existe"):
            erros["ext"] = le.erro or "os extintores ainda não chegaram ao banco"
        else:
            d = le.dados
            todas, nrs, _exc = DEC.separar(d.get("extintores") or [], d.get("nao_reconhecidos") or [], _decisoes())
            atr = [x for x in todas if x["atrasado"]]
    except Exception as e:      # noqa: BLE001
        erros["ext"] = type(e).__name__
    try:
        lu = EPI.luvas()
        if lu.erro:
            erros["epi"] = lu.erro
        else:
            us = (lu.dados or {}).get("usinas") or []
            luv = [u for u in us if u["situacao"] == "sem_luvas"]
            semv = sum(u["situacao"] == "sem_verificacao" for u in us)
    except Exception as e:      # noqa: BLE001
        erros["epi"] = type(e).__name__
    grupos = {}

    def g(nome):
        return grupos.setdefault(nome, {"nome": nome, "pts": 0, "vencidos": 0, "usinas_venc": set(), "nr": 0,
                                        "sem_luvas": 0, "nova_ronda": 0})
    for x in pts:
        g(_grupo(x, chave))["pts"] += 1
    for x in atr:
        s_ = g(_grupo(x, chave))
        s_["vencidos"] += 1
        s_["usinas_venc"].add(EXT.chave_usina(x))
    for x in nrs:
        g(_grupo(x, chave))["nr"] += 1
    for u in luv:
        g(_grupo(u, chave))["sem_luvas"] += 1
    sem = EXT.SEM_VALOR[chave]
    cartoes = []
    for s_ in grupos.values():
        s_["usinas_venc"] = len(s_["usinas_venc"])
        s_["total"] = s_["pts"] + s_["vencidos"] + s_["nr"] + s_["sem_luvas"]
        s_["cor"] = "critico" if s_["pts"] or s_["sem_luvas"] or s_["vencidos"] else ("alerta" if s_["nr"] else "ok")
        cartoes.append(s_)
    # o que tem mais para atacar primeiro; o "Sem ..." por último
    cartoes.sort(key=lambda s_: (s_["nome"] == sem, -s_["total"], s_["nome"].lower()))
    return render_template("hseq/mesa.html", torre=TORRE, tela=TORRE.tela("mesa"), lido=lido, erros=erros,
                           chave=chave, visoes=MESA_VISOES, cartoes=cartoes, sem=sem,
                           n_pts=len(pts), n_atr=len(atr), n_usinas_atr=len({EXT.chave_usina(x) for x in atr}),
                           n_nr=len(nrs), n_luv=len(luv), n_semv=semv, espera=_espera,
                           mais_antiga=max((x.get("idade_min") or 0 for x in pts), default=0),
                           dias_sem=EPI.DIAS_SEM_VERIFICAR, url=_url)


@bp.route("/extintores")
def extintores():
    """A tabela, que abre por cliente (Levi, 18/10/2026: "Quero agrupado por Cliente, abrindo o cliente terá as usinas
    desse cliente"; a usina abre os extintores, com o botão da foto) e tem ao lado a visão por extintor; os cartões por
    Responsável O&M; e o histórico de excluídos (24/10/2026). A faixa de números e o filtro de Status filtram a tabela
    (atrasado, perto de vencer, sem validade, em dia, sem atualização e não reconhecido). Os não reconhecidos em campo
    ganham a caixa deles logo abaixo da faixa, que aponta para a usina, e é na usina que a Segurança os aceita (24/10/2026:
    "ao ir para a usina a TST resolve"). Os filtros ficam logo acima da tabela e valem em tudo."""
    leitura, d, todas, base, nao_rec, fl = _filtrados()
    f = _status()
    pedido = request.args.get("modo")
    modo = "excluidos" if pedido == "excluidos" else ("responsaveis" if pedido == "responsaveis" and not f else "tabela")
    ver = "extintor" if request.args.get("ver") == "extintor" else "cliente"
    lista = EXT.ordenar(_lista(base, f), f if f in EXT.FILTROS else "")
    est = _decisoes()
    nrs = nao_rec if f in ("", NR) else []
    return render_template(
        "hseq/extintores.html", torre=TORRE, tela=TORRE.tela("extintores"), leitura=leitura, d=d, lido=_lido(leitura),
        url=_url_ext, f=f, modo=modo, ver=ver, fl=fl, filtros_ext=FILTROS_EXT, status_opcoes=STATUS,
        q=request.args.get("q", ""), contagem=EXT.contar(base), lista=lista, limite=LIMITE_LINHAS,
        # os não reconhecidos vão para a usina deles na tabela (é lá que a Segurança decide)
        grupos=EXT.por_cliente(lista, nrs) if modo == "tabela" and ver == "cliente" else [],
        nr_lista=nrs if ver == "extintor" and f == NR else [],
        historico=_historico(d, fl) if modo == "excluidos" else [], n_excluidos=len(fl["excluidos"]),
        pode=_pode(), rondas=_rondas(est, todas, fl["seguem"]), decisoes_erro=est.get("erro"),
        motivos=DEC.MOTIVOS, motivos_botao=DEC.MOTIVOS_DO_BOTAO_DIREITO,
        aviso_ok=request.args.get("ok", ""), aviso_erro=request.args.get("erro", ""),
        cartoes=EXT.por_responsavel(base, d.get("times") or {}) if modo == "responsaveis" else [],
        sem_responsavel=visao.SEM_RESPONSAVEL, sem_cliente=EXT.SEM_CLIENTE, situacoes=EXT.SITUACOES,
        status_tst=EXT.STATUS_TST, tempo=EXT.tempo, alerta_dias=EXT.ALERTA_DIAS,
        sem_atualizacao_dias=EXT.SEM_ATUALIZACAO_DIAS, fotos=FOT.disponiveis(current_app.config),
        filtros_url={k: request.args.get(k) for k in FILTROS_URL if request.args.get(k)}, nao_rec=nao_rec)


@bp.route("/extintores/usina")
def extintores_usina():
    """Os extintores de UMA usina, o pedaço que a linha da usina busca quando abre (19/10/2026: com todos os extintores
    na página, escondidos, eram 897 KB, e o Raio-X do servidor pegou 21 s montando a tela), com os não reconhecidos dela
    em cima. Os mesmos filtros da tela e o de Status; a usina vem com o cliente (o nome sozinho é de duas usinas: as
    duas Linhares 1). Sem o livro, vazio."""
    leitura, d, todas, base, nao_rec, fl = _filtrados()
    if leitura.erro or not d.get("aba_existe") or d.get("colunas_faltando") or not fl["usina"]:
        abort(404)
    f = _status()
    return render_template("hseq/_extintores_usina.html", d=d, extintores=EXT.ordenar(_lista(base, f)),
                           nao_reconhecidos=nao_rec if f in ("", NR) else [], pode=_pode(), sem_cliente=EXT.SEM_CLIENTE,
                           situacoes=EXT.SITUACOES, status_tst=EXT.STATUS_TST, tempo=EXT.tempo,
                           alerta_dias=EXT.ALERTA_DIAS, fotos=FOT.disponiveis(current_app.config))


def _volta(cliente: str, usina: str, **aviso) -> str:
    """A tabela de volta, na usina decidida, com o aviso do que foi feito (ou da recusa)."""
    args = {k: v for k, v in (("cliente", cliente), ("usina", usina), *aviso.items()) if v}
    return na_raiz("/t/hseq/extintores") + ("?" + urlencode(args) if args else "") + "#tabela"


def _decidir(fazer):
    """O POST de uma decisão da Segurança: grava e volta à usina (303, `?ok=`), ou volta com a recusa (`?erro=`). A
    falha que não é recusa vai ao log (e a tela diz que não gravou)."""
    from ..moldura import _de_outro_site
    if _de_outro_site():
        abort(403)
    cliente, usina = request.form.get("cliente", ""), request.form.get("usina", "")
    try:
        texto = fazer(request.form)
        if isinstance(texto, tuple):            # a volta que só o servidor sabe (o botão direito manda só o código)
            texto, cliente, usina = texto
    except DEC.Recusada as e:
        return redirect(_volta(cliente, usina, erro=str(e)), code=303)
    except Exception as e:      # noqa: BLE001 — banco fora, trava: a tela diz
        import logging
        logging.exception("Extintores: a decisão da Segurança falhou")
        return redirect(_volta(cliente, usina, erro=f"Não consegui gravar no banco ({type(e).__name__}). Tente de novo "
                                                    "em instantes"), code=303)
    return redirect(_volta(cliente, usina, ok=texto), code=303)


@bp.route("/extintores/excluir", methods=["POST"])
def extintores_excluir():
    """Exclui um extintor (Levi, 24/10/2026): o não reconhecido aceito na usina ("quando a TST aceita o extintor é
    excluído e vai para um histórico de extintores excluídos com o motivo 'Não reconhecido em campo'") ou qualquer um
    pelo botão direito na linha ("clicar com o botão direito e poder excluir o extintor"). Quem pode: o administrador e
    quem é do setor Segurança (`decisoes.pode_decidir`)."""
    def fazer(form):
        d = EXT.extintores().dados or {}
        todas, seguem, _ = DEC.separar(d.get("extintores") or [], d.get("nao_reconhecidos") or [], _decisoes())
        motivo, codigo = form.get("motivo", ""), form.get("codigo", "")
        if motivo == "nao_reconhecido":
            x = next((x for x in seguem if x["codigo"] == codigo
                      and x["nao_reconhecido"].isoformat() == form.get("marca")), None)
        else:
            x = next((x for x in todas + seguem if x["codigo"] == codigo), None)
        if x is None:
            raise DEC.Recusada("Este extintor não está mais na tela (alguém já o excluiu, ou a equipe o achou): "
                               "atualize a página.")
        return (DEC.excluir(current_app.config, extintor=x, motivo=motivo, obs=form.get("obs", ""),
                            usuario=session.get("usuario"), pode=_pode()), x.get("cliente") or EXT.SEM_CLIENTE, x["usina"])
    return _decidir(fazer)


@bp.route("/extintores/ronda", methods=["POST"])
def extintores_ronda():
    """Pede à equipe uma nova ronda de extintores, do zero, na usina (Levi, 24/10/2026: "pedir uma nova ronda é uma
    nova ronda do zero então será por usina"). O App mostra a ronda pendente; o nome da usina vai como o App a escreve."""
    def fazer(form):
        try:
            uid = int(form.get("usina_id") or 0)
        except ValueError:
            uid = 0
        d = EXT.extintores().dados or {}
        x = next((x for x in (d.get("extintores") or []) + (d.get("nao_reconhecidos") or []) if x.get("usina_id") == uid),
                 None)
        return DEC.pedir_ronda(current_app.config, usina_id=uid, usina=form.get("usina", ""),
                               usina_app=x["usina_fonte"] if x else "", usuario=session.get("usuario"), pode=_pode())
    return _decidir(fazer)


def _slug(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:60] or "usina"


def _do_relatorio(filtro: str = "todos"):
    """O recorte que o PDF e o Excel levam: os filtros da tela (`_filtrados`), o da faixa (`f`), a usina e o dia do
    "Baixar" de cada linha e o cliente da linha do cliente. Devolve None sem o livro do App (a rota volta para a tela).
    Os não reconhecidos em campo vão à parte, só sem o filtro da faixa e no relatório de todos (não têm status da TST);
    com a usina ou o dia, os daquela usina (e daquele dia)."""
    leitura, d, todas, base, nao_rec, fl = _filtrados()
    if leitura.erro or not d.get("aba_existe") or d.get("colunas_faltando"):
        return None
    f = _status()
    usina, dia = request.args.get("usina", ""), request.args.get("dia", "")
    lista = [x for x in _lista(base, f) if (not usina or x["usina"] == usina)
             and (not dia or (x["conferencia"].isoformat() if x["conferencia"] else "nunca") == dia)]
    rotulo_f = dict(STATUS).get(f, "")
    dia_txt = "nunca conferido" if dia == "nunca" else (f"{dia[8:10]}/{dia[5:7]}/{dia[:4]}" if dia else "")
    filtros_tela = [f"{rot}: {v}" for rot, v in (
        ("Usina", usina), ("Dia da conferência", dia_txt), ("Cliente", fl["cliente"]),
        ("Responsável UFV", fl["responsavel"]), ("Equipe", fl["equipe"]), ("Situação", rotulo_f),
        ("Busca", request.args.get("q", "").strip())) if v]
    hoje = d.get("hoje") or visao._agora().date()
    nr = [x for x in nao_rec if (not usina or x["usina"] == usina)
          and (not dia or x["nao_reconhecido"].isoformat() == dia)] if filtro == "todos" and f in ("", NR) else []
    # o nome do arquivo: a usina (e o dia do link de antes), o cliente da linha do cliente, ou o filtro do relatório
    quem = (f"{_slug(usina)}-{dia}" if usina and dia else _slug(usina) if usina
            else _slug(fl["cliente"]) if fl["cliente"] else filtro)
    nome = f"extintores-{quem}" + ("" if usina and dia else f"-{hoje:%Y-%m-%d}")
    return {"lista": lista, "nr": nr, "filtros_tela": filtros_tela, "hoje": hoje, "nome": nome,
            "gerado_em": visao._agora().strftime("%d/%m/%Y %H:%M"),
            "modo": "attachment" if request.args.get("baixar") else "inline"}


@bp.route("/extintores/relatorio.pdf")
def extintores_relatorio():
    """O relatório em PDF (Levi, 09/10/2026, com as observações da TST): agrupado por usina e dia, com os filtros da
    tela, o filtro do status da TST (todos, críticos, atenção, OK) e as fotos ao lado de cada extintor (o padrão;
    `fotos=0` tira). Desde 18/10/2026 a tela só pede o relatório UNITÁRIO (Levi: "O relatório quero a opção de ser
    unitário (...), pode tirar esse RELATÓRIO EM PDF que tira em massa!"): o de cada usina (`usina`, `baixar=1`; os
    filtros da tela e o da faixa, `f`, vêm junto), a usina inteira, todos os dias, e desde 19/10 o de cada cliente
    (`cliente`; a TST: "tem como eu baixar um relatório dos extintores por cliente?"). O `dia` ainda filtra, para quem
    tinha o link de antes. Sem o livro do App, volta para a tela."""
    filtro = request.args.get("status") if request.args.get("status") in REL.FILTROS else "todos"
    r = _do_relatorio(filtro)
    if r is None:
        return redirect(na_raiz("/t/hseq/extintores"))
    com_fotos = (request.args.getlist("fotos") or ["1"])[-1] != "0"
    pdf = REL.gerar(EXT.ordenar(r["lista"]), filtro=filtro, com_fotos=com_fotos, filtros_tela=r["filtros_tela"],
                    hoje=r["hoje"], nao_reconhecidos=r["nr"], gerado_em=r["gerado_em"],
                    logo=str(current_app.static_folder) + "/grid-h-branco.png",
                    foto=lambda c: FOT.foto_pdf(current_app.config, c))   # a cópia de 600 px, feita uma vez por foto
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition": f'{r["modo"]}; filename="{r["nome"]}.pdf"'})


@bp.route("/extintores/relatorio.xlsx")
def extintores_planilha():
    """O mesmo relatório em Excel (a TST, 19/10/2026: "e excel tbm? pq às vezes o cliente pede"), com o mesmo recorte
    do PDF (`_do_relatorio`): uma linha por extintor, na ordem da tabela da tela, e os não reconhecidos numa aba à parte
    (`hseq/planilha.py`). Sempre como anexo."""
    r = _do_relatorio()
    if r is None:
        return redirect(na_raiz("/t/hseq/extintores"))
    xlsx = PLA.gerar(r["lista"], filtros_tela=r["filtros_tela"], hoje=r["hoje"], gerado_em=r["gerado_em"],
                     nao_reconhecidos=r["nr"])
    return Response(xlsx, mimetype=PLA.MIME, headers={"Content-Disposition": f'attachment; filename="{r["nome"]}.xlsx"'})


@bp.route("/extintores/foto", methods=["POST"])
def extintores_foto_receber():
    """O App envia a foto de cada conferência de extintor (Levi, 09/10/2026: "quando tiver foto (ronda de extintor feita
    no app) ... deve ter a opção de visualizar foto de extintor"). Sem sessão: vale a assinatura HMAC (`fotos.receber`);
    o portão de login deixa só esta rota passar (`auth.ROTAS_PUBLICAS`)."""
    arq = request.files.get("foto")
    status, msg = FOT.receber(current_app.config, request.form.get("codigo"), request.form.get("dia"),
                              request.form.get("ts"), request.form.get("assinatura"), arq.read() if arq else b"")
    return jsonify({"ok": status == 200, "mensagem": msg}), status


@bp.route("/extintores/foto/<codigo>.jpg")
def extintores_foto(codigo):
    """A foto do extintor (a mais recente que o App enviou); `mini=1` = a miniatura da tabela."""
    dados = (FOT.mini if request.args.get("mini") else FOT.foto)(current_app.config, codigo)
    if not dados:
        abort(404)
    return Response(dados, mimetype="image/jpeg", headers={"Cache-Control": "private, max-age=300"})


@bp.route("/apr-pt")
def apr_pt():
    """Permissões de trabalho e Análise Preliminar de Risco: a tela das PT que era do Campo · App (o mesmo visual e as
    mesmas contas, `torres.campo.pagina_pt`), com as colunas PT e APR e o detalhe com a assinatura e a decisão."""
    from ..campo import pagina_pt
    return pagina_pt()


@bp.route("/epi")
def epi():
    """EPI e EPC (Levi, 09/10/2026: "criasse um campo de EPI / EPC começando apenas por EPI, puxando as luvas das rondas
    diárias"): as luvas isolantes de cada usina pela última ronda, em cartões por Responsável O&M da usina, com as
    usinas dele (24/10/2026: "tem que ser por responsável da usina, aí mostra as usinas"; até ali, por região de campo e
    por gestor de contrato) e em tabela. Filtros: região do Brasil, cliente, responsável UFV e busca; ninguém abre
    filtrado pelo login. A faixa de números filtra a tabela."""
    leitura = EPI.luvas()
    d = leitura.dados
    regiao, cliente = request.args.get("regiao", ""), request.args.get("cliente", "")
    resp = request.args.get("responsavel", "").strip()
    q = request.args.get("q", "").strip().lower()
    todas = d.get("usinas") or []
    base = [x for x in todas if (not regiao or x.get("regiao_br") == regiao)
            and (not cliente or x.get("cliente") == cliente) and (not resp or EPI.responsavel(x) == resp)
            and (not q or q in " ".join(str(x.get(c) or "") for c in ("usina", "cidade", "equipe")).lower())]
    f = request.args.get("f") if request.args.get("f") in EPI.SITUACOES else ""
    modo = "tabela" if request.args.get("modo") == "tabela" or f else "responsaveis"
    responsaveis = sorted({EPI.responsavel(x) for x in todas} | ({resp} if resp else set()),
                          key=lambda r: (r == visao.SEM_RESPONSAVEL, r.lower()))
    return render_template(
        "hseq/epi.html", torre=TORRE, tela=TORRE.tela("epi"), leitura=leitura, d=d, lido=_lido(leitura), url=_url,
        f=f, modo=modo, regiao=regiao, regioes=visao.REGIOES, cliente=cliente, clientes=_clientes(todas),
        responsavel=resp, responsaveis=responsaveis, sem_responsavel=visao.SEM_RESPONSAVEL,
        q=request.args.get("q", ""), contagem=EPI.contar(base),
        lista=[x for x in base if not f or x["situacao"] == f], limite=LIMITE_LINHAS,
        cartoes=EPI.por_responsavel(base, d.get("times") or {}), situacoes=EPI.SITUACOES, tempo=EXT.tempo,
        dias_sem=EPI.DIAS_SEM_VERIFICAR, pergunta=EPI.PERGUNTA)

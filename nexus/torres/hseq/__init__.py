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


def _filtrados():
    """A leitura e os extintores com os filtros da tela (cliente, usina, responsável UFV, equipe e busca): a tela e o
    "Baixar" de cada usina contam o mesmo. Os não reconhecidos em campo (14/10/2026) vêm à parte, com os mesmos
    filtros: estão fora de todas as contas (`extintores.nao_reconhecido`)."""
    leitura = EXT.extintores()
    d = leitura.dados
    fl = {c: request.args.get(c, "").strip() for c, _rot in FILTROS_EXT}
    q = request.args.get("q", "").strip().lower()

    def passa(x, menos=None):
        return (all(not v or c == menos or EXT.valor_do_filtro(x, c) == v for c, v in fl.items())
                and (not q or q in " ".join(str(x.get(c) or "") for c in BUSCA).lower()))
    todas = d.get("extintores") or []
    base = [x for x in todas if passa(x)]
    # o aceito pela Segurança (a baixa) sai da tela; o de nova ronda segue, com o dia do pedido (`decisoes.aplicar`)
    seguem, _aceitos = DEC.aplicar(d.get("nao_reconhecidos") or [], _decisoes())
    nao_rec = [x for x in seguem if passa(x)]
    opcoes = _opcoes_ext(todas + seguem, fl, passa)
    return leitura, d, todas, base, nao_rec, dict(fl, opcoes=opcoes)


def _decisoes() -> dict:
    """As decisões da Segurança (cache de 1 minuto); sem ler, nenhuma (e a tela diz: `decisoes_erro`)."""
    return DEC.ler(current_app.config)


def _pode() -> bool:
    """Aceitar, pedir nova ronda e editar a quantidade: o administrador e quem é do setor Segurança."""
    from ...auth import setor_telas as ST
    return DEC.pode_decidir((ST.acesso() or {}).get("setor"), bool(session.get("admin")))


def _url_ext(**mudar) -> str:
    """O `_url` do Campo sem o aviso da última gravação (`ok`, `erro`): ele não segue nos links da tela."""
    return _url(ok=None, erro=None, **mudar)


def _cadastro_por_usina(d) -> dict:
    """{usina_id: quantos extintores o cadastro tem na usina}, os não reconhecidos que ainda esperam a Segurança
    inclusive (o "no cadastro" do editar quantidade)."""
    seguem, _ = DEC.aplicar(d.get("nao_reconhecidos") or [], _decisoes())
    out = {}
    for x in (d.get("extintores") or []) + seguem:
        if x.get("usina_id"):
            out[x["usina_id"]] = out.get(x["usina_id"], 0) + 1
    return out


MESA_ITENS = 8          # cada painel da Mesa mostra até 8; o "ver todos" leva à tela de origem


def _espera(minutos) -> str:
    """Quanto tempo a PT espera, para quem lê a Mesa: minutos, horas e, de 2 dias em diante, dias."""
    m = int(minutos or 0)
    return f"{m} min" if m < 60 else (f"{m // 60} h" if m < 48 * 60 else f"{m // 1440} dias")


@bp.route("/mesa")
def mesa():
    """A Mesa da Segurança (Levi, 24/10/2026: "Criação de mesa da segurança, como PTs atrasadas, extintores vencidos,
    usinas sem luvas"), no desenho da Mesa do engenheiro: a faixa com os quatro números e um painel para cada um, o
    mais urgente primeiro, cada item levando à tela de origem já filtrada. Só lê (o banco e as decisões da Segurança);
    a fonte que falha diz no painel dela e não derruba os outros."""
    out = {"lido": "", "pts": [], "pts_erro": "", "usinas_atr": [], "atrasados": 0, "ext_erro": "", "nao_rec": [],
           "sem_luvas": [], "sem_verificacao": 0, "epi_erro": ""}
    try:
        lp = visao.pts()
        out["lido"] = _lido(lp)
        if lp.erro:
            out["pts_erro"] = lp.erro
        else:
            out["pts"] = sorted((x for x in (lp.dados or {}).get("aguardando") or [] if x.get("parada")),
                                key=lambda x: -(x.get("idade_min") or 0))
    except Exception as e:      # noqa: BLE001 — uma fonte fora não derruba a mesa
        out["pts_erro"] = type(e).__name__
    try:
        le = EXT.extintores()
        if le.erro or not (le.dados or {}).get("aba_existe"):
            out["ext_erro"] = le.erro or "os extintores ainda não chegaram ao banco"
        else:
            d = le.dados
            atr = [x for x in d.get("extintores") or [] if x["atrasado"]]
            out["atrasados"] = len(atr)
            out["usinas_atr"] = sorted(EXT.por_usina(atr), key=lambda u: (-u["qtd"], u["usina"]))
            out["nao_rec"] = DEC.aplicar(d.get("nao_reconhecidos") or [], _decisoes())[0]
    except Exception as e:      # noqa: BLE001
        out["ext_erro"] = type(e).__name__
    try:
        lu = EPI.luvas()
        if lu.erro:
            out["epi_erro"] = lu.erro
        else:
            us = (lu.dados or {}).get("usinas") or []
            out["sem_luvas"] = sorted((u for u in us if u["situacao"] == "sem_luvas"),
                                      key=lambda u: (u.get("desde") or visao._agora().date(), u["usina"]))
            out["sem_verificacao"] = sum(u["situacao"] == "sem_verificacao" for u in us)
            out["hoje"] = (lu.dados or {}).get("hoje")
    except Exception as e:      # noqa: BLE001
        out["epi_erro"] = type(e).__name__
    return render_template("hseq/mesa.html", torre=TORRE, tela=TORRE.tela("mesa"), m=out, limite=MESA_ITENS,
                           espera=_espera, tempo=EXT.tempo, sem_cliente=EXT.SEM_CLIENTE,
                           dias_sem=EPI.DIAS_SEM_VERIFICAR)


@bp.route("/extintores")
def extintores():
    """A tabela, que abre por cliente (Levi, 18/10/2026: "Quero agrupado por Cliente, abrindo o cliente terá as usinas
    desse cliente"; a usina, uma linha só, com o responsável, os técnicos e o PDF dela em "Baixar", abre os extintores,
    com a foto de cada um quando o App a enviou) e tem ao lado a visão por extintor; e os cartões por Responsável O&M
    (o "Responsável UFV"), no lugar dos de região de campo e gestor. A faixa de números filtra a tabela pelas situações
    do pedido de 09/10: atrasado, perto de vencer, sem atualização há mais de 30 dias (e sem validade). Os não
    reconhecidos em campo (14/10/2026) ganham a caixa deles logo abaixo da faixa, para a TST; a linha leva à tabela
    filtrada naquela usina. Os filtros (cliente, usina, responsável UFV, equipe e a busca) ficam logo acima da tabela e
    valem em tudo."""
    leitura, d, todas, base, nao_rec, fl = _filtrados()
    f = request.args.get("f") if request.args.get("f") in EXT.FILTROS else ""
    modo = "responsaveis" if request.args.get("modo") == "responsaveis" and not f else "tabela"
    ver = "extintor" if request.args.get("ver") == "extintor" else "cliente"
    lista = EXT.ordenar([x for x in base if not f or x[f]], f)
    est = _decisoes()
    return render_template(
        "hseq/extintores.html", torre=TORRE, tela=TORRE.tela("extintores"), leitura=leitura, d=d, lido=_lido(leitura),
        url=_url_ext, f=f, modo=modo, ver=ver, fl=fl, filtros_ext=FILTROS_EXT, q=request.args.get("q", ""),
        contagem=EXT.contar(base), lista=lista, limite=LIMITE_LINHAS,
        # os não reconhecidos vão para a usina deles na tabela (é lá que a Segurança decide), fora do filtro da faixa
        grupos=EXT.por_cliente(lista, [] if f else nao_rec) if modo == "tabela" and ver == "cliente" else [],
        pode=_pode(), qtd_seg=DEC.por_usina(est), no_cadastro=_cadastro_por_usina(d), decisoes_erro=est.get("erro"),
        aviso_ok=request.args.get("ok", ""), aviso_erro=request.args.get("erro", ""),
        cartoes=EXT.por_responsavel(base, d.get("times") or {}) if modo == "responsaveis" else [],
        sem_responsavel=visao.SEM_RESPONSAVEL, sem_cliente=EXT.SEM_CLIENTE, situacoes=EXT.SITUACOES,
        status_tst=EXT.STATUS_TST, tempo=EXT.tempo, alerta_dias=EXT.ALERTA_DIAS,
        sem_atualizacao_dias=EXT.SEM_ATUALIZACAO_DIAS, fotos=FOT.disponiveis(current_app.config),
        filtros_url={k: request.args.get(k) for k in FILTROS_URL if request.args.get(k)}, nao_rec=nao_rec)


@bp.route("/extintores/usina")
def extintores_usina():
    """Os extintores de UMA usina, o pedaço que a linha da usina busca quando abre (19/10/2026: com todos os extintores
    na página, escondidos, eram 897 KB, e o Raio-X do servidor pegou 21 s montando a tela). Os mesmos filtros da tela e
    o da faixa; a usina vem com o cliente (o nome sozinho é de duas usinas: as duas Linhares 1). Sem o livro, vazio."""
    leitura, d, todas, base, nao_rec, fl = _filtrados()
    if leitura.erro or not d.get("aba_existe") or d.get("colunas_faltando") or not fl["usina"]:
        abort(404)
    f = request.args.get("f") if request.args.get("f") in EXT.FILTROS else ""
    return render_template("hseq/_extintores_usina.html", d=d, extintores=EXT.ordenar([x for x in base if not f or x[f]]),
                           nao_reconhecidos=[] if f else nao_rec, pode=_pode(), sem_cliente=EXT.SEM_CLIENTE,
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
    except DEC.Recusada as e:
        return redirect(_volta(cliente, usina, erro=str(e)), code=303)
    except Exception as e:      # noqa: BLE001 — banco fora, trava: a tela diz
        import logging
        logging.exception("Extintores: a decisão da Segurança falhou")
        return redirect(_volta(cliente, usina, erro=f"Não consegui gravar no banco ({type(e).__name__}). Tente de novo "
                                                    "em instantes"), code=303)
    return redirect(_volta(cliente, usina, ok=texto), code=303)


@bp.route("/extintores/decidir", methods=["POST"])
def extintores_decidir():
    """Aceitar (dar baixa) ou pedir nova ronda para um não reconhecido, na usina dele (Levi, 24/10/2026: "a tabela de
    contestações tem que servir para apontar para a usina, ao ir para a usina a TST resolve"). A decisão responde à
    marca daquele dia; quem pode: o administrador e quem é do setor Segurança (`decisoes.pode_decidir`)."""
    def fazer(form):
        d = EXT.extintores().dados or {}
        seguem, _ = DEC.aplicar(d.get("nao_reconhecidos") or [], _decisoes())
        x = next((x for x in seguem if x["codigo"] == form.get("codigo")
                  and x["nao_reconhecido"].isoformat() == form.get("marca")), None)
        if x is None:
            raise DEC.Recusada("Este extintor não está mais esperando a Segurança (alguém decidiu, ou a equipe o "
                               "achou): atualize a página.")
        return DEC.decidir_extintor(current_app.config, extintor=x, acao=form.get("acao", ""),
                                    usuario=session.get("usuario"), pode=_pode())
    return _decidir(fazer)


@bp.route("/extintores/quantidade", methods=["POST"])
def extintores_quantidade():
    """Quantos extintores existem na usina, segundo a Segurança (Levi, 24/10/2026: "Opção da pessoa do setor de
    segurança editar a quantidade de extintores"). Não mexe no cadastro (que é do App): a tela mostra as duas contas."""
    def fazer(form):
        try:
            uid = int(form.get("usina_id") or 0)
        except ValueError:
            uid = 0
        no_cad = _cadastro_por_usina(EXT.extintores().dados or {}).get(uid, 0)
        return DEC.decidir_quantidade(current_app.config, usina_id=uid, usina=form.get("usina", ""), no_cadastro=no_cad,
                                      quantidade=form.get("quantidade"), motivo_txt=form.get("motivo", ""),
                                      usuario=session.get("usuario"), pode=_pode())
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
    f = request.args.get("f") if request.args.get("f") in EXT.FILTROS else ""
    usina, dia = request.args.get("usina", ""), request.args.get("dia", "")
    lista = [x for x in base if (not f or x[f]) and (not usina or x["usina"] == usina)
             and (not dia or (x["conferencia"].isoformat() if x["conferencia"] else "nunca") == dia)]
    rotulo_f = (EXT.SITUACOES[f][0] if f in EXT.SITUACOES else "Sem atualização") if f else ""
    dia_txt = "nunca conferido" if dia == "nunca" else (f"{dia[8:10]}/{dia[5:7]}/{dia[:4]}" if dia else "")
    filtros_tela = [f"{rot}: {v}" for rot, v in (
        ("Usina", usina), ("Dia da conferência", dia_txt), ("Cliente", fl["cliente"]),
        ("Responsável UFV", fl["responsavel"]), ("Equipe", fl["equipe"]), ("Situação", rotulo_f),
        ("Busca", request.args.get("q", "").strip())) if v]
    hoje = d.get("hoje") or visao._agora().date()
    nr = [x for x in nao_rec if (not usina or x["usina"] == usina)
          and (not dia or x["nao_reconhecido"].isoformat() == dia)] if filtro == "todos" and not f else []
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

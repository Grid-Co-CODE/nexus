"""Torre Segurança · HSEQ: Extintores, EPI e EPC, Riscos da semana, APR e PT, DSS e incidentes.

Extintores (09/10/2026) é visão nossa (`nexus/hseq/extintores.py`), pelo livro que o App de Campo grava no banco, com
os filtros próprios desde 18/10/2026 (cliente, usina, responsável UFV, equipe e a busca, em cascata; `FILTROS_EXT`).
No EPI, os filtros e os cartões da estrutura de O&M de 10/2026 (a região de campo com o Supervisor de Campo, o gestor de
contrato) são os MESMOS da torre Campo · App (`_regiao_campo`, `_gestor`, `_do_papel`, `_papeis` e os pedaços de
template `campo/_filtros_papeis.html`, `campo/_cartoes_papeis.html`, `campo/_aviso_estrutura.html`): quem entra pelo
Fracttal já vem filtrado, como lá. Uma regra só: mudou lá, muda aqui.

As outras telas ainda caem no placeholder da casca (view com a mesma rota vence a genérica). Leia o CLAUDE.md desta
pasta antes de mexer.
"""
import re
import unicodedata

from flask import Response, abort, current_app, jsonify, redirect, render_template, request

from ...campo import visao
from ...hseq import epi as EPI
from ...hseq import extintores as EXT
from ...hseq import fotos as FOT
from ...hseq import planilha as PLA
from ...hseq import relatorio as REL
from ..campo import _do_papel, _gestor, _lido, _papeis, _regiao_campo, _url
from ..modelo import Tela, Torre
from ...prefixo import na_raiz

TORRE = Torre(
    id="hseq",
    nome="Segurança · HSEQ",
    ordem=100,
    icone="shield-check",
    descricao="Extintores, EPI e EPC, riscos da semana, APR e PT, DSS e incidentes.",
    telas=[
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
    nao_rec = [x for x in d.get("nao_reconhecidos") or [] if passa(x)]
    opcoes = _opcoes_ext(todas + (d.get("nao_reconhecidos") or []), fl, passa)
    return leitura, d, todas, base, nao_rec, dict(fl, opcoes=opcoes)


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
    return render_template(
        "hseq/extintores.html", torre=TORRE, tela=TORRE.tela("extintores"), leitura=leitura, d=d, lido=_lido(leitura),
        url=_url, f=f, modo=modo, ver=ver, fl=fl, filtros_ext=FILTROS_EXT, q=request.args.get("q", ""),
        contagem=EXT.contar(base), lista=lista, limite=LIMITE_LINHAS,
        grupos=EXT.por_cliente(lista) if modo == "tabela" and ver == "cliente" else [],
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
                           situacoes=EXT.SITUACOES, status_tst=EXT.STATUS_TST, tempo=EXT.tempo,
                           alerta_dias=EXT.ALERTA_DIAS, fotos=FOT.disponiveis(current_app.config))


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
    diárias"): as luvas isolantes de cada usina pela última ronda, por supervisor (cartões) e em tabela, com os mesmos
    filtros (o de cliente também: a regra do Levi de a melhoria valer para todas as telas que a suportam) e o mesmo
    desenho dos extintores; a faixa de números filtra a tabela."""
    leitura = EPI.luvas()
    d = leitura.dados
    regiao, cliente = request.args.get("regiao", ""), request.args.get("cliente", "")
    regiao_campo, gestor = _regiao_campo(), _gestor()
    q = request.args.get("q", "").strip().lower()
    todas = d.get("usinas") or []
    base = [x for x in todas if (not regiao or x.get("regiao_br") == regiao)
            and (not cliente or x.get("cliente") == cliente) and _do_papel(x, regiao_campo, gestor)
            and (not q or q in " ".join(str(x.get(c) or "") for c in ("usina", "cidade", "equipe")).lower())]
    f = request.args.get("f") if request.args.get("f") in EPI.SITUACOES else ""
    pedido = request.args.get("modo")
    modo = "tabela" if pedido == "tabela" or f else ("gestores" if pedido == "gestores" else "regioes")
    return render_template(
        "hseq/epi.html", torre=TORRE, tela=TORRE.tela("epi"), leitura=leitura, d=d, lido=_lido(leitura), url=_url,
        f=f, modo=modo, regiao=regiao, regioes=visao.REGIOES, cliente=cliente, clientes=_clientes(todas),
        q=request.args.get("q", ""), contagem=EPI.contar(base),
        lista=[x for x in base if not f or x["situacao"] == f], limite=LIMITE_LINHAS,
        cartoes_reg=EPI.por_regiao(base, d.get("regioes") or [], d.get("times") or {}),
        cartoes_gest=EPI.por_gestor(base, d.get("times") or {}), situacoes=EPI.SITUACOES, tempo=EXT.tempo,
        dias_sem=EPI.DIAS_SEM_VERIFICAR, pergunta=EPI.PERGUNTA, **_papeis(d, todas, regiao_campo, gestor))

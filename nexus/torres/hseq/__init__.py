"""Torre Segurança · HSEQ: Extintores, EPI e EPC, Riscos da semana, APR e PT, DSS e incidentes.

Extintores (09/10/2026) é visão nossa (`nexus/hseq/extintores.py`), pelo livro que o App de Campo grava no banco. Os
filtros e os cartões da estrutura de O&M de 10/2026 (a região de campo com o Supervisor de Campo, o gestor de contrato)
são os MESMOS da torre Campo · App (`_regiao_campo`, `_gestor`, `_do_papel`, `_papeis` e os pedaços de template
`campo/_filtros_papeis.html`, `campo/_cartoes_papeis.html`, `campo/_aviso_estrutura.html`): quem entra pelo Fracttal já
vem filtrado, como lá. Uma regra só: mudou lá, muda aqui.

As outras telas ainda caem no placeholder da casca (view com a mesma rota vence a genérica). Leia o CLAUDE.md desta
pasta antes de mexer.
"""
import re
from datetime import datetime

from flask import Response, current_app, redirect, render_template, request

from ...cadastro.ligacoes import pasta_dados
from ...campo import visao
from ...hseq import epi as EPI
from ...hseq import extintores as EXT
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
             "Que extintor está vencido, perto de vencer ou sem conferência há mais de 30 dias, e de qual supervisor?",
             "Ronda de extintores do App de Campo (livro extintores_app_campo) + cadastro do Nexus"),
        Tela("epi", "EPI e EPC",
             "Que usina está sem as luvas isolantes, segundo a última ronda diária?",
             "Rondas diárias do App de Campo (o item das luvas isolantes do checklist) + cadastro do Nexus"),
        Tela("riscos", "Riscos da semana",
             "Que atividade da semana está liberada, condicionada ou bloqueada?",
             "Programação do PCM + Semanal de Segurança"),
        Tela("apr-pt", "APR e PT",
             "Que OS de risco está sem APR ou PT assinada?",
             "App de Campo"),
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


def _filtrados():
    """A leitura e os extintores com os filtros da tela (região do Brasil, região de campo, gestor e busca): a tela e o
    relatório em PDF contam o mesmo."""
    leitura = EXT.extintores()
    d = leitura.dados
    regiao, regiao_campo, gestor = request.args.get("regiao", ""), _regiao_campo(), _gestor()
    q = request.args.get("q", "").strip().lower()
    todas = d.get("extintores") or []
    base = [x for x in todas if (not regiao or x.get("regiao_br") == regiao) and _do_papel(x, regiao_campo, gestor)
            and (not q or q in " ".join(str(x.get(c) or "") for c in BUSCA).lower())]
    return leitura, d, todas, base, regiao, regiao_campo, gestor


@bp.route("/extintores")
def extintores():
    """Duas visões (Levi, 09/10/2026: "Preciso da visão por supervisor"): cartões por supervisor (a região de campo,
    com a alternância para o gestor de contrato, como na Central de atenção) e a tabela, que abre por usina e dia da
    última conferência (Levi, 09/10: "queria agrupado por usina e dia!"; a linha da usina abre os extintores dela) e tem
    ao lado a visão por extintor. A faixa de números filtra a tabela pelas situações do pedido: atrasado, perto de
    vencer, sem atualização há mais de 30 dias (e sem validade). Os filtros da região do Brasil, da região de campo, do
    gestor e a busca valem nas duas visões."""
    leitura, d, todas, base, regiao, regiao_campo, gestor = _filtrados()
    f = request.args.get("f") if request.args.get("f") in EXT.FILTROS else ""
    pedido = request.args.get("modo")
    modo = "tabela" if pedido == "tabela" or f else ("gestores" if pedido == "gestores" else "regioes")
    ver = "extintor" if request.args.get("ver") == "extintor" else "usina"
    lista = EXT.ordenar([x for x in base if not f or x[f]], f)
    return render_template(
        "hseq/extintores.html", torre=TORRE, tela=TORRE.tela("extintores"), leitura=leitura, d=d, lido=_lido(leitura),
        url=_url, f=f, modo=modo, ver=ver, regiao=regiao, regioes=visao.REGIOES, q=request.args.get("q", ""),
        contagem=EXT.contar(base), lista=lista, limite=LIMITE_LINHAS,
        grupos=EXT.por_usina_dia(lista) if modo == "tabela" and ver == "usina" else [],
        cartoes_reg=EXT.por_regiao(base, d.get("regioes") or [], d.get("times") or {}),
        cartoes_gest=EXT.por_gestor(base, d.get("times") or {}), situacoes=EXT.SITUACOES,
        status_tst=EXT.STATUS_TST, tempo=EXT.tempo, alerta_dias=EXT.ALERTA_DIAS,
        sem_atualizacao_dias=EXT.SEM_ATUALIZACAO_DIAS, **_papeis(d, todas, regiao_campo, gestor))


def _foto_extintor(codigo):
    """A foto da última conferência do extintor que o App enviou ao Nexus (`<dados>/hseq/extintores/fotos/<código>.jpg`).
    Em 09/10/2026 o App ainda não envia (as fotos ficam no App): o relatório sai com o quadro vazio, dizendo isso."""
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{2,60}", str(codigo or "")):
        return None
    try:
        arq = pasta_dados(current_app.config) / "hseq" / "extintores" / "fotos" / f"{codigo}.jpg"
    except RuntimeError:            # teste sem pasta de dados: sem foto
        return None
    return arq.read_bytes() if arq.is_file() else None


@bp.route("/extintores/relatorio.pdf")
def extintores_relatorio():
    """O relatório em PDF (Levi, 09/10/2026, com as observações da TST): agrupado por usina e dia, com os filtros da
    tela, o filtro do status da TST (todos, críticos, atenção, OK) e as fotos ao lado de cada extintor (o padrão;
    `fotos=0` tira). Sem o livro do App, volta para a tela, que diz o que falta."""
    leitura, d, todas, base, regiao, regiao_campo, gestor = _filtrados()
    if leitura.erro or not d.get("aba_existe") or d.get("colunas_faltando"):
        return redirect(na_raiz("/t/hseq/extintores"))
    filtro = request.args.get("status") if request.args.get("status") in REL.FILTROS else "todos"
    com_fotos = (request.args.getlist("fotos") or ["1"])[-1] != "0"
    filtros_tela = [f"{rot}: {v}" for rot, v in (("Região do Brasil", regiao), ("Região de campo", regiao_campo),
                                                 ("Gestor de contrato", gestor),
                                                 ("Busca", request.args.get("q", "").strip())) if v]
    hoje = d.get("hoje") or visao._agora().date()
    pdf = REL.gerar(EXT.ordenar(base), filtro=filtro, com_fotos=com_fotos, filtros_tela=filtros_tela, hoje=hoje,
                    gerado_em=visao._agora().strftime("%d/%m/%Y %H:%M"),
                    logo=str(current_app.static_folder) + "/grid-h-branco.png", foto=_foto_extintor)
    nome = f"extintores-{filtro}-{hoje:%Y-%m-%d}.pdf"
    return Response(pdf, mimetype="application/pdf", headers={"Content-Disposition": f'inline; filename="{nome}"'})


@bp.route("/epi")
def epi():
    """EPI e EPC (Levi, 09/10/2026: "criasse um campo de EPI / EPC começando apenas por EPI, puxando as luvas das rondas
    diárias"): as luvas isolantes de cada usina pela última ronda, por supervisor (cartões) e em tabela, com os mesmos
    filtros e o mesmo desenho dos extintores; a faixa de números filtra a tabela."""
    leitura = EPI.luvas()
    d = leitura.dados
    regiao, regiao_campo, gestor = request.args.get("regiao", ""), _regiao_campo(), _gestor()
    q = request.args.get("q", "").strip().lower()
    todas = d.get("usinas") or []
    base = [x for x in todas if (not regiao or x.get("regiao_br") == regiao) and _do_papel(x, regiao_campo, gestor)
            and (not q or q in " ".join(str(x.get(c) or "") for c in ("usina", "cidade", "equipe")).lower())]
    f = request.args.get("f") if request.args.get("f") in EPI.SITUACOES else ""
    pedido = request.args.get("modo")
    modo = "tabela" if pedido == "tabela" or f else ("gestores" if pedido == "gestores" else "regioes")
    return render_template(
        "hseq/epi.html", torre=TORRE, tela=TORRE.tela("epi"), leitura=leitura, d=d, lido=_lido(leitura), url=_url,
        f=f, modo=modo, regiao=regiao, regioes=visao.REGIOES, q=request.args.get("q", ""), contagem=EPI.contar(base),
        lista=[x for x in base if not f or x["situacao"] == f], limite=LIMITE_LINHAS,
        cartoes_reg=EPI.por_regiao(base, d.get("regioes") or [], d.get("times") or {}),
        cartoes_gest=EPI.por_gestor(base, d.get("times") or {}), situacoes=EPI.SITUACOES, tempo=EXT.tempo,
        dias_sem=EPI.DIAS_SEM_VERIFICAR, pergunta=EPI.PERGUNTA, **_papeis(d, todas, regiao_campo, gestor))


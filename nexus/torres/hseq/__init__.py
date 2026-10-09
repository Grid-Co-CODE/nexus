"""Torre Segurança · HSEQ: Extintores, Riscos da semana, APR e PT, DSS e incidentes.

Extintores (09/10/2026) é visão nossa (`nexus/hseq/extintores.py`), pelo livro que o App de Campo grava no banco. Os
filtros e os cartões da estrutura de O&M de 10/2026 (a região de campo com o Supervisor de Campo, o gestor de contrato)
são os MESMOS da torre Campo · App (`_regiao_campo`, `_gestor`, `_do_papel`, `_papeis` e os pedaços de template
`campo/_filtros_papeis.html`, `campo/_cartoes_papeis.html`, `campo/_aviso_estrutura.html`): quem entra pelo Fracttal já
vem filtrado, como lá. Uma regra só: mudou lá, muda aqui.

As outras telas ainda caem no placeholder da casca (view com a mesma rota vence a genérica). Leia o CLAUDE.md desta
pasta antes de mexer.
"""
from flask import render_template, request

from ...campo import visao
from ...hseq import extintores as EXT
from ..campo import _do_papel, _gestor, _lido, _papeis, _regiao_campo, _url
from ..modelo import Tela, Torre

TORRE = Torre(
    id="hseq",
    nome="Segurança · HSEQ",
    ordem=100,
    icone="shield-check",
    descricao="Extintores, riscos da semana, APR e PT, DSS e incidentes.",
    telas=[
        Tela("extintores", "Extintores",
             "Que extintor está vencido, perto de vencer ou sem conferência há mais de 30 dias, e de qual supervisor?",
             "Ronda de extintores do App de Campo (livro extintores_app_campo) + cadastro do Nexus"),
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


@bp.route("/extintores")
def extintores():
    """Duas visões (Levi, 09/10/2026: "Preciso da visão por supervisor"): cartões por supervisor (a região de campo,
    com a alternância para o gestor de contrato, como na Central de atenção) e a tabela dos extintores. A faixa de
    números filtra a tabela pelas situações do pedido: atrasado, perto de vencer, sem atualização há mais de 30 dias (e
    sem validade). Os filtros da região do Brasil, da região de campo, do gestor e a busca valem nas duas visões."""
    leitura = EXT.extintores()
    d = leitura.dados
    regiao, regiao_campo, gestor = request.args.get("regiao", ""), _regiao_campo(), _gestor()
    f = request.args.get("f") if request.args.get("f") in EXT.FILTROS else ""
    pedido = request.args.get("modo")
    modo = "tabela" if pedido == "tabela" or f else ("gestores" if pedido == "gestores" else "regioes")
    q = request.args.get("q", "").strip().lower()
    todas = d.get("extintores") or []
    base = [x for x in todas if (not regiao or x.get("regiao_br") == regiao) and _do_papel(x, regiao_campo, gestor)
            and (not q or q in " ".join(str(x.get(c) or "") for c in BUSCA).lower())]
    return render_template(
        "hseq/extintores.html", torre=TORRE, tela=TORRE.tela("extintores"), leitura=leitura, d=d, lido=_lido(leitura),
        url=_url, f=f, modo=modo, regiao=regiao, regioes=visao.REGIOES, q=request.args.get("q", ""),
        contagem=EXT.contar(base), lista=EXT.ordenar([x for x in base if not f or x[f]], f), limite=LIMITE_LINHAS,
        cartoes_reg=EXT.por_regiao(base, d.get("regioes") or [], d.get("times") or {}),
        cartoes_gest=EXT.por_gestor(base, d.get("times") or {}), situacoes=EXT.SITUACOES,
        status_tst=EXT.STATUS_TST, tempo=EXT.tempo, alerta_dias=EXT.ALERTA_DIAS,
        sem_atualizacao_dias=EXT.SEM_ATUALIZACAO_DIAS, **_papeis(d, todas, regiao_campo, gestor))

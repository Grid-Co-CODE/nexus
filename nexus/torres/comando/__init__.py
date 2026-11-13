"""Torre Comando: sala de comando, fila única de ações e o que pede decisão.

Insights e Caixa de entrada (03/11/2026; Levi: "construa o que você sugere", os setores conversando): o motor de regras
(nexus/comando/regras.py e motor.py) aponta o problema com evidência, ação e torre dona; a Caixa de entrada mostra o das
torres que o setor da pessoa vê; "Assumir" e "Concluir" gravam no livro nexus_insights (nexus/comando/estado.py). O sino
do topo (base.html) conta pela mesma cópia. As outras telas ainda caem no placeholder da casca. Para dar vida a uma tela, crie uma
view com a mesma rota (ela vence a genérica), por exemplo:

    @bp.route("/sala-de-comando")
    def sala_de_comando():
        return render_template("comando/sala-de-comando.html")
"""
import hmac
import secrets

from flask import abort, current_app, redirect, render_template, request, session, url_for

from ...comando import estado as ES
from ...comando import motor as MO
from ...comando import pedidos as PD
from ...comando import regras as RG
from ...prefixo import na_raiz
from ..modelo import Tela, Torre
from ...auth.origem import de_outro_site as _de_outro_site

TORRE = Torre(
    id="comando",
    nome="Comando",
    ordem=0,
    icone="squares-four",
    descricao="Sala de comando, fila única de ações e o que pede decisão.",
    telas=[
        Tela("sala-de-comando", "Sala de comando",
             "Onde estou perdendo dinheiro esta semana e quem está segurando?",
             "Motor de correlação do Nexus + Performance, PCM e Fracttal"),
        Tela("caixa-de-entrada", "Caixa de entrada",
             "O que é meu para fazer hoje, por prazo e valor?",
             "Itens de trabalho do Nexus (insights, OS, chamados, solicitações)", de_todos=True),
        Tela("kanban", "Kanban",
             "Onde as ações nascidas no Nexus estão travando?",
             "Itens de trabalho do Nexus"),
        Tela("insights", "Nexus Insights",
             "Que regra cruzou as fontes e apontou um problema com dono?",
             "Regras R01 a R13 do motor de correlação"),
        # as demandas entre setores (12/11/2026): cada setor diz o que os outros podem pedir a ele, e em quanto tempo
        Tela("temas-do-setor", "Temas do setor",
             "O que os outros setores podem pedir ao seu, e em quanto tempo o seu setor responde?",
             "Temas das demandas (nexus_demandas · dim_tema)", de_todos=True),
        Tela("tempo-de-resposta", "Tempo de resposta",
             "Que área responde no prazo, e quais pedidos estão atrasados?",
             "Pedidos entre áreas, com prazo (nexus_pedidos)"),
        # a tela do mockup "Início > Usinas" (11/11/2026, nexus/comando/usinas.py)
        Tela("usinas", "Usinas",
             "Como está cada usina agora, e o que cada setor diz dela?",
             "Visão do responsável, tempo real, Nexus Insights, extintores e luvas das rondas + cadastro do Nexus"),
        Tela("metas", "Metas do book",
             "Quais KPIs do book R02 estão fora da meta e piorando?",
             "Aba KPIs do Plano de Documentação"),
        # da torre Contratos e clientes, que saiu do menu (12/11/2026, Levi: "contestações, você vai jogar para o
        # comando, prévia visão do contrato, você vai jogar no comando"; as views em contestacoes_tela.py). A prévia é de
        # todos, para cada setor avaliar sem liberar um por um (Ana: "pedir avaliação da Danuth, Camila e Fred")
        Tela("contestacoes", "Contestações",
             "O que os clientes contestaram nos dashboards, e para qual setor?",
             "Dashboard Thopen: a contestação de cada dia, gravada cifrada no banco (livro thopen_contestacoes)"),
        Tela("visao-do-contrato", "Prévia: visão do contrato",
             "Como fica a visão do contrato?",
             "Mockup para avaliação, com dados fictícios: nada grava", de_todos=True),
    ],
)

bp = TORRE.criar_blueprint(__name__)

_CODIGO, _AVISO = "insights_codigo", "insights_aviso"
# as áreas que se notifica: as torres de operação (o Comando e o OS Creator não recebem pedido)
FORA_DE_NOTIFICAR = ("comando", "os")


def _codigo() -> str:
    """O código do formulário desta sessão (outro site não o conhece; o login troca a sessão e o código)."""
    if not session.get(_CODIGO):
        session[_CODIGO] = secrets.token_urlsafe(24)
    return session[_CODIGO]


def _meu_hmac() -> str:
    u = session.get("usuario")
    email = str(u.get("email") or "").strip().lower() if isinstance(u, dict) else ""
    if not email:
        return ""
    from ...cadastro.ligacao_campo import codigo_da_pessoa
    return (codigo_da_pessoa(current_app.config.get("NEXUS_PESSOA_HMAC"), email) or "").lower()


def _nomes_das_torres() -> dict:
    return {t.id: t.nome for t in current_app.extensions["nexus_torres"]}


def _areas() -> list[tuple[str, str]]:
    return [(t.id, t.nome) for t in sorted(current_app.extensions["nexus_torres"], key=lambda t: t.ordem)
            if t.id not in FORA_DE_NOTIFICAR]


def _com_pedidos(lista: list[dict], minhas: set | None, meu: str = "") -> list[dict]:
    """Os pedidos para a tela: o nome da área, o status do retorno (rótulo e tom), o prazo em palavras, se a área é
    minha (respondo por ela) e se fui eu que pedi."""
    nomes, out = _nomes_das_torres(), []
    for p in lista:
        rot, tom = ES.RETORNOS[p["status"]]
        out.append(dict(p, nome=nomes.get(p["torre"], p["torre"]), rotulo=rot, tom=tom,
                        minha=minhas is None or p["torre"] in minhas, eu_pedi=bool(meu) and p["pedido_hmac"] == meu,
                        pedido_em_txt=p["pedido_em"].strftime("%d/%m às %H:%M"),
                        retorno_em_txt=p["retorno_em"].strftime("%d/%m às %H:%M") if p["retorno_em"] else "",
                        prazo_txt=p["prazo"].strftime("%d/%m") if p["prazo"] else ""))
    return out


def _com_estado(insights: list[dict], est: dict, meu: str, minhas: set | None, convs: dict | None = None,
                peds: dict | None = None) -> list[dict]:
    """Cada insight com o dono (novo, assumido por quem, concluído), se é meu, os pedidos às áreas com o prazo e o retorno
    de cada uma (Fase 3), os pedidos para as minhas áreas que esperam a minha resposta e a conversa dele (Fase 2)."""
    out, convs, peds = [], convs or {}, peds if peds is not None else PD.por_objeto(PD.atual())
    for i in insights:
        e = est.get(i["id"]) or {}
        ev = e.get("evento") if e.get("evento") != "reabriu" else ""
        pedidos = _com_pedidos(peds.get("insight:" + i["id"]) or [], minhas, meu)
        out.append(dict(i, estado=ev or "novo", por=e.get("por", ""), quando_txt=e.get("quando_txt", ""),
                        meu=bool(meu) and e.get("pessoa_hmac") == meu and ev == "assumiu",
                        sev_rot=RG.SEVERIDADES[i["sev"]][0], sev_tom=RG.SEVERIDADES[i["sev"]][1],
                        regra_nome=RG.REGRAS[i["regra"]]["nome"], avisar=RG.REGRAS[i["regra"]].get("avisar") or [],
                        pedidos=pedidos, resolvidos=sum(1 for p in pedidos if p["status"] == "resolvido"),
                        para_mim=[p for p in pedidos if p["minha"] and p["status"] != "resolvido"],
                        atrasados=sum(1 for p in pedidos if p["situacao"] == "atrasado"),
                        ob="insight:" + i["id"], conv=_com_conversa(convs.get("insight:" + i["id"]), meu)))
    return out


def _leitura():
    """(leitura, insights, regras, gerado_em). Sem a cópia do motor, a leitura é None e a lista vem vazia: a conta corre
    por trás (`MO.sem_esperar`) e a tela avisa, em vez de segurar o pedido."""
    lei = MO.sem_esperar()
    if lei is None:
        return None, [], {}, None
    d = lei.dados or {}
    return lei, d.get("insights") or [], d.get("regras") or {}, d.get("gerado_em")


def _contexto(**kw) -> dict:
    return dict(kw, nomes_torres=_nomes_das_torres(), areas=_areas(), codigo=_codigo(), aviso=session.pop(_AVISO, None),
                abrir=request.args.get("abrir") or "", hoje=PD.hoje().isoformat(),
                tem_login=bool(_meu_hmac()), voltar=request.full_path.rstrip("?"), retornos=ES.RETORNOS)


@bp.route("/insights")
def insights():
    """Nexus Insights: tudo o que as regras apontaram agora, com a evidência, a ação, a torre dona, as áreas notificadas
    e os retornos; e o catálogo das regras com quantas vezes cada uma disparou e a fonte que não leu."""
    lei, todos, status, gerado = _leitura()
    from ...comando import conversa as CV
    lista = _com_estado(todos, ES.atual(), _meu_hmac(), MO.torres_da_pessoa(), CV.atual())
    a = request.args
    sev = a.get("sev", "") if a.get("sev") in RG.SEVERIDADES else ""
    regra = a.get("regra", "") if a.get("regra") in RG.REGRAS else ""
    torre = a.get("torre", "")
    ver_concluidos = a.get("concluidos") == "1"
    filtrada = [i for i in lista if (not sev or i["sev"] == sev) and (not regra or i["regra"] == regra)
                and (not torre or i["torre"] == torre) and (ver_concluidos or i["estado"] != "concluiu")]
    vivos = [i for i in lista if i["estado"] != "concluiu"]
    contas = {k: sum(1 for i in vivos if i["sev"] == k) for k in RG.SEVERIDADES}
    contas["notificados"] = sum(1 for i in vivos if i["pedidos"])
    contas["aguardando"] = sum(1 for i in vivos for p in i["pedidos"] if p["status"] == "pendente")
    contas["atrasados"] = sum(i["atrasados"] for i in vivos)
    catalogo = [dict(RG.REGRAS[r], id=r, **(status.get(r) or {"n": 0, "erro": ""})) for r in RG.REGRAS]
    return render_template("comando/insights.html", **_contexto(
        torre=TORRE, tela=TORRE.tela("insights"), lei=lei, itens=filtrada, contas=contas, catalogo=catalogo,
        gerado=gerado, sev=sev, regra=regra, torre_f=torre, ver_concluidos=ver_concluidos, severidades=RG.SEVERIDADES,
        calculando=lei is None,
        regras=RG.REGRAS, erro_estado=ES.ler()["erro"]))


def _usinas_montadas() -> dict:
    """A conta do Comando > Usinas (a lista e o prontuário leem a mesma, cada fonte na cópia de 5 min dela): as linhas
    (`nexus/comando/usinas.py`), o que não leu (`avisos`) e os insights vivos de cada usina."""
    from ...campo import responsaveis as campo_resp
    from ...campo import visao
    from ...comando import usinas as CU
    from ...cos import andamento as AND
    from ...hseq import epi as EPI
    leitura = campo_resp.visao_responsaveis()
    d = leitura.dados or {}
    avisos = []
    try:
        b = visao._Base()
        cadastro = b.por_id
    except Exception:            # noqa: BLE001 — sem o cadastro, a tabela segue sem código, MWp e tipologia
        b, cadastro = None, {}
        avisos.append("o cadastro (código, MWp e tipologia)")
    # a coluna Agora pelo COS (11/11/2026, Levi: "Coluna Agora pelo COS", e a régua dele no mesmo dia: religamento em
    # campo crítico, inversor desligado atenção, falha de comunicação sem comunicação): a fotografia da Ronda COS de cada
    # cliente do Andamento (a do COS > Ronda padronizada, cópia de 30 s por cliente), que traz o tipo da tarefa e o da
    # falha de cada ocorrência aberta; a usina liga pelo código do Andamento ("THPN-ALT100"), como os Acionamentos
    cos, cos_ts = None, ""
    cfg = current_app.config
    if AND.fonte(cfg).ligada and b is not None:
        clientes_cos, erro_cli = AND.clientes(cfg)
        leituras = [AND.ler(cfg, c) for c in clientes_cos]
        cos = CU.cos_por_usina(leituras, lambda nome, codigo: b.lig.usina(nome or "", codigo or "")[0])
        falharam = [lt.cliente for lt in leituras if not lt.dados]
        if falharam:
            avisos.append("o COS de " + ", ".join(falharam) + " (essas usinas aparecem Sem leitura)")
        elif erro_cli and not clientes_cos:
            avisos.append("a lista de clientes do COS")
        geradas = [AND.instante(lt.dados.get("gerado_em")) for lt in leituras if lt.dados]
        geradas = [g for g in geradas if g]
        cos_ts = min(geradas).strftime("%H:%M") if geradas else ""
    if cos is None:
        avisos.append("o COS (a coluna Agora)")
    lei_ins = MO.sem_esperar()
    insights, vivos = None, {}
    if lei_ins is not None and b is not None:
        nome_para_uid = {CU._norm(f.get("nome")): uid for uid, f in cadastro.items() if f.get("nome")}
        nome_para_uid.update({CU._norm(f.get("codigo")): uid for uid, f in cadastro.items() if f.get("codigo")})
        est = ES.atual()
        todos = (lei_ins.dados or {}).get("insights") or []
        insights = CU.insights_por_usina(todos, est, nome_para_uid)
        for i in todos:
            uid = nome_para_uid.get(CU._norm(i.get("usina")))
            if uid and ((est.get(i.get("id")) or {}).get("evento")) != "concluiu":
                vivos.setdefault(uid, []).append(i)
    sem_luvas = None
    luv = EPI.luvas()
    if luv.erro:
        avisos.append("as luvas isolantes das rondas")
    else:
        sem_luvas = {x["usina_id"] for x in (luv.dados or {}).get("usinas") or [] if x.get("situacao") == "sem_luvas"}
    erros = d.get("erros") or {}
    com_os = "manut" not in erros and ((d.get("info") or {}).get("manut") or {}).get("publicado", True) is not False
    linhas = CU.montar(d.get("usinas") or [], cadastro, cos, insights, sem_luvas, com_os=com_os)
    return {"linhas": linhas, "avisos": avisos, "erro": leitura.erro, "cos_ts": cos_ts,
            "insights_calculando": insights is None, "vivos": vivos, "visao": d}


@bp.route("/usinas")
def usinas():
    """Comando > Usinas (11/11/2026, Levi: "Em comando quero a mesma visão de Início > Usinas do mockup"): todas as usinas
    mobilizadas, com o estado de agora e o que cada tela dona diz delas (`nexus/comando/usinas.py`). Sem o Score de saúde
    do mockup (Levi: "Fora por agora"). Os filtros no modelo do Histórico de OS (12/11/2026): as listas digitáveis do
    painel (filtram aqui, no Aplicar), a busca e a ordem das colunas na página (comando-usinas.js). Cada fonte que não
    responde vira "sem leitura" na coluna dela. O clique na usina abre o prontuário aqui mesmo, no Comando (Levi: "No
    próprio Comando")."""
    from ...comando import usinas as CU
    m = _usinas_montadas()
    # os filtros do painel (12/11/2026, o modelo do Histórico de OS: listas digitáveis de marcar, que só valem no Aplicar,
    # que recarrega a página com `filtro=a&filtro=b`): cliente, responsável da UFV, estado de agora, faixa da meta e
    # conformidade. A faixa e a legenda seguem com todas as mobilizadas; a tabela, com as do filtro
    escolhidos = {k: [v for v in request.args.getlist(k) if v] for k in CU.FILTROS}
    todas = m["linhas"]
    r = CU.resumo(todas)
    return render_template(
        "comando/usinas.html", torre=TORRE, tela=TORRE.tela("usinas"), linhas=CU.filtrar(todas, escolhidos),
        todas=todas, r=r, legenda=CU.LEGENDA, estados=CU.ESTADOS, erro=m["erro"], avisos=m["avisos"],
        insights_calculando=m["insights_calculando"], cos_ts=m["cos_ts"], escolhidos=escolhidos,
        op_clientes=[(c, c) for c in r["clientes"]], op_responsaveis=[(x, x) for x in r["responsaveis"]],
        op_estados=[(k, e[0]) for k, e in CU.ESTADOS.items()], op_meta=list(CU.META_FAIXAS.items()),
        op_conformidade=list(CU.CONFORMIDADES.items()), q=request.args.get("q", ""))


@bp.route("/usinas/<int:usina_id>")
def usina(usina_id):
    """O prontuário da usina no Comando (11/11/2026, Levi: o clique na usina "No próprio Comando", como o prontuário do
    mockup): a linha dela na lista, a Central da usina (a mesma conta da Usinas 360°, `_central_da_usina`) em leitura e
    os insights do Nexus que estão vivos nela. Desde 12/11/2026 (Levi: "juntar todas as informações daquela usina [...]
    métricas, pendências, insights e etc. Deixe forma visual agradável e direta!") junta também o resumo do que pede
    atenção, o mês a mês, o histórico do COS, a zeladoria semanal, as rondas, os equipamentos com OS aberta, os chamados,
    a segurança, as demandas, a composição da ficha e a linha do tempo (`prontuario_dados.montar`)."""
    from .prontuario_dados import contexto as _prontuario
    ctx = _prontuario(usina_id, rel_url=f"/t/comando/usinas/{usina_id}/relatorio.pdf")
    if ctx is None:
        abort(404)
    return render_template("comando/usina.html", torre=TORRE, tela=TORRE.tela("usinas"), **ctx)


@bp.route("/usinas/<int:usina_id>/relatorio.pdf")
def usina_relatorio(usina_id):
    """O relatório da usina em PDF (o do cliente, `campo/relatorio_usina.py`) pelo endereço do Comando: a mesma conta da
    Usinas 360° (`responsaveis_usina_relatorio`), para quem tem o Comando > Usinas e não a Visão do responsável."""
    from ..campo import responsaveis_usina_relatorio
    return responsaveis_usina_relatorio(usina_id)


def _extras_do_dossie(usina_id: int) -> dict:
    """O que os setores sabem da usina e o prontuário ainda não mostra (Levi, 12/11/2026, conferindo o dossiê: "tá indo o
    que a engenharia tá vendo [...] tá indo alguma anotação de supervisão"): os ativos com sinal na Confiabilidade com os
    números de lá, os ativos em acompanhamento pela Engenharia, os relatórios de FMEA e de causa raiz e as observações do
    Responsável O&M. Cada fonte no `try` dela: a que não abre vai como None, e o dossiê diz "sem leitura" (nunca
    "nenhum"). Nenhuma lê o Fracttal: são as cópias e os livros que as telas donas já leem."""
    import logging

    from ...campo import visao
    log = logging.getLogger(__name__)

    def tentar(nome, f):
        try:
            return f()
        except Exception:           # noqa: BLE001 — a fonte fora do ar não derruba o dossiê
            log.exception("dossiê: %s não abriu", nome)
            return None

    def ativos():
        from ...campo import responsaveis as R
        return R.ativos_da_usina(usina_id, visao._agora().date())

    def acompanhamentos():
        from ...engenharia import acompanhamento as EA
        lido = EA.ler()
        if lido.get("erro") and not lido.get("lido_em"):
            raise RuntimeError(lido["erro"])
        nomes = {str(d.get("id")): d.get("nome") or "" for d in EA.diagnosticos(lido.get("diagnosticos") or [])}
        return [dict(a, diagnostico=nomes.get(str(a.get("diagnostico_id")), "")) for a in EA.estado(lido.get("eventos") or []).values()
                if a.get("usina_id") == usina_id]

    def relatorios():
        from ...engenharia import fmea as F
        lido = F.ler()
        if lido.get("erro") and not lido.get("lido_em"):
            raise RuntimeError(lido["erro"])
        return [r["ultima"] for r in F.relatorios(lido.get("linhas") or []) if r["ultima"].get("usina_id") == usina_id]

    def observacoes():
        from ...campo import observacao_responsavel as OB
        return OB.da_usina(usina_id, limite=20)
    return {"ativos": tentar("a Confiabilidade", ativos), "acompanhamentos": tentar("o acompanhamento da Engenharia", acompanhamentos),
            "relatorios": tentar("os relatórios de falha", relatorios), "observacoes": tentar("as observações", observacoes)}


def _dossie(usina_id: int):
    """(o contexto do prontuário, o dossiê montado) ou 404 para a usina que não está na lista."""
    from ...campo import visao
    from ...comando import dossie as DS
    from .prontuario_dados import contexto as _prontuario
    ctx = _prontuario(usina_id)
    if ctx is None:
        abort(404)
    return ctx, DS.montar(ctx, visao._agora(), extras=_extras_do_dossie(usina_id))


@bp.route("/usinas/<int:usina_id>/dossie")
def usina_dossie(usina_id):
    """O dossiê da usina para a IA (12/11/2026, Levi: "Monte o dossiê da usina inteira, para a gente usar com a IA
    futuramente, do jeito que uma IA possa ver facilmente"): tudo o que o prontuário junta, no texto que a IA vai ler
    junto da pergunta (`nexus/comando/dossie.py`). Esta página mostra o texto, o tamanho dele e deixa copiar e baixar;
    abre para quem abre o prontuário (o mesmo dado, sem o nome das pessoas)."""
    ctx, d = _dossie(usina_id)
    # na janela por cima do prontuário (13/11/2026, Levi: "Pode abrir uma janelinha na frente, sobrepor uma tela. Não
    # precisa ser algo que leva para um link"): só o miolo, sem a casca
    if request.args.get("parcial") == "1":
        return render_template("comando/_dossie_corpo.html", x=ctx["x"], d=d, na_janela=True)
    return render_template("comando/dossie.html", torre=TORRE, tela=TORRE.tela("usinas"), x=ctx["x"], d=d)


@bp.route("/usinas/<int:usina_id>/dossie.md")
def usina_dossie_md(usina_id):
    """O mesmo dossiê em texto puro (Markdown), para colar numa conversa com a IA ou para o Nexus IA mandar pela API.
    `?baixar=1` baixa o arquivo. Sem cópia em cache: o dossiê é de agora."""
    ctx, d = _dossie(usina_id)
    resp = current_app.response_class(d["texto"], mimetype="text/markdown")
    nome = "".join(c if c.isalnum() or c in "-_" else "-" for c in str(ctx["x"].get("codigo") or usina_id))
    resp.headers["Content-Disposition"] = (f'{"attachment" if request.args.get("baixar") else "inline"}; '
                                           f'filename="dossie-{nome}.md"')
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.route("/caixa-de-entrada")
def caixa_de_entrada():
    """Caixa de entrada: os pedidos que outras áreas mandaram para o setor da pessoa, o mais atrasado primeiro (Fase 3:
    com o prazo, sobre insight, OS ou usina); os que ela pediu e ainda estão abertos; as menções (Fase 2); o que ela
    assumiu; e os insights das torres do setor sem dono e com outra pessoa. Sem os concluídos."""
    from ...comando import conversa as CV
    lei, todos, status, gerado = _leitura()
    torres, meu, convs = MO.torres_da_pessoa(), _meu_hmac(), CV.atual()
    todos_peds = PD.atual()
    lista = [i for i in _com_estado(todos, ES.atual(), meu, torres, convs, PD.por_objeto(todos_peds))
             if i["estado"] != "concluiu"]
    # as menções que ainda não li (Fase 2): a pessoa pelo código do e-mail, ou uma área que o setor dela vê
    usinas, mencoes = _usinas(), []
    for x in CV.para_mim(convs, meu, torres):
        titulo, link = _titulo(x["objeto"], todos, usinas)
        mencoes.append(dict(x, titulo=titulo, link=link, conversa=na_raiz(
            "/t/comando/conversa/" + x["objeto"].replace(":", "/", 1)),
            por_area_nomes=[_nomes_das_torres().get(a, a) for a in x["por_area"]]))
    abertos = sorted((p for p in todos_peds.values() if p["status"] != "resolvido"), key=PD.ordem)
    pedidos = [dict(p, titulo=t, link=k) for p in _com_pedidos(abertos, torres, meu) if p["minha"]
               for t, k in [_titulo_e_link(p["objeto"], todos, usinas)]]
    feitos = [dict(p, titulo=t, link=k) for p in _com_pedidos(abertos, torres, meu) if p["eu_pedi"]
              for t, k in [_titulo_e_link(p["objeto"], todos, usinas)]]
    das_minhas = MO.das_torres(lista, torres)
    meus = [i for i in das_minhas if i["meu"]]
    sem_dono = [i for i in das_minhas if not i["meu"] and i["estado"] == "novo"]
    com_dono = [i for i in das_minhas if not i["meu"] and i["estado"] == "assumiu"]
    nomes = _nomes_das_torres()
    from .demandas_tela import contexto as _demandas
    return render_template("comando/caixa.html", **_contexto(
        torre=TORRE, tela=TORRE.tela("caixa-de-entrada"), lei=lei, pedidos=pedidos, feitos=feitos, meus=meus,
        dem=_demandas(),
        sem_dono=sem_dono, erro_pedidos=PD.ler()["erro"],
        com_dono=com_dono, gerado=gerado, mencoes=mencoes, usinas_lista=sorted(usinas.items(), key=lambda u: u[1]),
        erro_conversa=CV.ler()["erro"], calculando=lei is None,
        minhas_torres=sorted(nomes.get(t, t) for t in torres if t not in FORA_DE_NOTIFICAR) if torres is not None else None,
        falhas=[r for r, x in status.items() if x.get("erro")]))


# o miolo e as ações de um insight em /insight/ (no singular): /insights/... casa com a tela Insights no portão por setor,
# e quem só tem a Caixa de entrada (todo setor, 03/11/2026) não abriria o insight nem gravaria o Assumir; o endereço antigo
# segue valendo para quem tem a tela
@bp.route("/insight/corpo")
@bp.route("/insights/corpo")
def insights_corpo():
    """O miolo de um insight (provas, áreas, retornos, conversa), pedido quando a pessoa abre a linha: a lista vem só
    com as linhas (ver `_insight.html`). O `voltar` é o da página que pediu, para os formulários voltarem a ela."""
    from ...comando import conversa as CV
    _lei, todos, _st, _g = _leitura()
    alvo = next((i for i in todos if i["id"] == (request.args.get("id") or "")), None)
    if alvo is not None and not _ve_o_insight(alvo):
        alvo = None
    if alvo is None:
        return ('<p class="mudo ins-nota">Este insight não está mais na lista (a regra parou de apontar, ou a conta está '
                'sendo refeita): recarregue a página.</p>'), 404
    voltar = request.args.get("voltar") or ""
    i = _com_estado([alvo], ES.atual(), _meu_hmac(), MO.torres_da_pessoa(), CV.atual())[0]
    # sem o `_contexto`: ele tira o aviso da sessão, que é da página
    return render_template("comando/_corpo.html", i=i, nomes_torres=_nomes_das_torres(), areas=_areas(),
                           codigo=_codigo(), tem_login=bool(_meu_hmac()), retornos=ES.RETORNOS,
                           hoje=PD.hoje().isoformat(),
                           voltar=voltar if voltar.startswith("/t/comando/") else "/t/comando/insights")


def _ve_o_insight(i: dict) -> bool:
    """Quem tem a tela Insights vê todos; quem só tem a Caixa, os das torres do setor e os que pedem retorno a ele."""
    from ...auth import setor_telas
    a = setor_telas.acesso()
    if a["tudo"] or setor_telas.chave("comando", "insights") in a["telas"]:
        return True
    torres = MO.torres_da_pessoa() or set()
    return i["torre"] in torres or any(p["torre"] in torres for p in PD.atual().values()
                                       if p["objeto"] == "insight:" + i["id"])


def _form_venceu(destino: str):
    """O formulário de outro site ou de outra sessão não grava: devolve o redirecionamento com o aviso, ou None."""
    certo = session.get(_CODIGO) or ""
    enviado = request.form.get("codigo") or ""
    if _de_outro_site() or not certo or not hmac.compare_digest(enviado.encode(), certo.encode()):
        session[_AVISO] = ("erro", "O formulário venceu (a sessão mudou desde que a tela abriu): abra a tela de novo. "
                                   "Nada foi gravado.")
        return redirect(destino, code=303)
    return None


def _destino() -> str:
    voltar = request.form.get("voltar") or ""
    return na_raiz(voltar) if voltar.startswith("/t/comando/") else na_raiz("/t/comando/caixa-de-entrada")


@bp.route("/insight/acao", methods=["POST"])
@bp.route("/insights/acao", methods=["POST"])
def insights_acao():
    """Assumir, Concluir ou Reabrir um insight que o motor aponta agora. Volta à tela de onde veio. (Notificar as áreas e
    o retorno delas são pedidos com prazo: `/pedido/acao`.)"""
    destino = _destino()
    venceu = _form_venceu(destino)
    if venceu:
        return venceu
    evento = {"assumir": "assumiu", "concluir": "concluiu", "reabrir": "reabriu"}.get(request.form.get("acao") or "")
    iid = request.form.get("insight") or ""
    _lei, todos, _st, _g = _leitura()
    alvo = next((i for i in todos if i["id"] == iid), None)
    try:
        if not evento:
            raise ES.Recusada("Ação desconhecida")
        if _lei is None:
            raise ES.Recusada("A conta dos insights está sendo feita agora (o Nexus acabou de subir): tente de novo em "
                              "meio minuto")
        if alvo is None:
            raise ES.Recusada("Este insight não está mais na lista (a regra parou de apontar): recarregue a página")
        ES.registrar(alvo, evento, session.get("usuario"), request.form.get("nota") or "")
        session[_AVISO] = ("ok", {"assumiu": "Assumido: agora é seu.", "concluiu": "Concluído: saiu da Caixa de entrada.",
                                  "reabriu": "Reaberto."}[evento])
    except ES.Recusada as ex:
        session[_AVISO] = ("erro", f"{ex}. Nada foi gravado.")
    except Exception as ex:      # noqa: BLE001 — banco fora: a pessoa sabe que não foi
        current_app.logger.exception("insight: o evento não gravou")
        session[_AVISO] = ("erro", f"Não consegui gravar agora ({type(ex).__name__}). Nada foi gravado.")
    return redirect(destino + f"#ins-{iid.replace(':', '-')}", code=303)


# ── o pedido entre áreas com prazo (Fase 3, 03/11/2026) ──────────────────────────────────────────────────────────────
@bp.route("/pedido/acao", methods=["POST"])
def pedido_acao():
    """Pedir retorno a áreas sobre um insight, uma OS ou uma usina, com o prazo que quem pede escolhe (Levi, 03/11/2026:
    "Quem pede sempre escolhe"); ou a área pedida responder. Volta à tela de onde veio, no objeto."""
    destino = _destino()
    venceu = _form_venceu(destino)
    if venceu:
        return venceu
    from ...comando import conversa as CV
    acao = request.form.get("acao") or ""
    ob = CV.objeto(*(request.form.get("objeto") or "").partition(":")[::2]) or ""
    nomes = _nomes_das_torres()
    try:
        if acao == "pedir":
            if not ob:
                raise PD.Recusada("Não achei este objeto: recarregue a página")
            if ob.startswith("insight:"):
                lei, todos, _st, _g = _leitura()
                if lei is None:
                    raise PD.Recusada("A conta dos insights está sendo feita agora (o Nexus acabou de subir): tente de "
                                      "novo em meio minuto")
                if not any(i["id"] == ob.split(":", 1)[1] for i in todos):
                    raise PD.Recusada("Este insight não está mais na lista (a regra parou de apontar): recarregue a "
                                      "página")
            para = [t for t in request.form.getlist("para") if t in nomes and t not in FORA_DE_NOTIFICAR]
            feito = PD.pedir(ob, para, request.form.get("prazo") or "", session.get("usuario"),
                             request.form.get("nota") or "")
            if feito:
                prazo = PD._dia(feito[0]["prazo"])
                areas = ", ".join(nomes.get(l["torre"], l["torre"]) for l in feito)
                session[_AVISO] = ("ok", f"Pedido enviado a {areas}, com prazo até {prazo.strftime('%d/%m')}. O retorno "
                                         "aparece aqui e no Tempo de resposta.")
            else:
                session[_AVISO] = ("ok", "Essas áreas já tinham pedido aberto sobre isto.")
        elif acao == "responder":
            PD.responder(request.form.get("pedido") or "", request.form.get("status") or "", session.get("usuario"),
                         request.form.get("nota") or "", MO.torres_da_pessoa())
            session[_AVISO] = ("ok", "Retorno enviado: quem pediu já vê.")
        else:
            raise PD.Recusada("Ação desconhecida")
    except PD.Recusada as ex:
        session[_AVISO] = ("erro", f"{ex}. Nada foi gravado.")
    except Exception as ex:      # noqa: BLE001 — banco fora: a pessoa sabe que não foi
        current_app.logger.exception("pedido: o evento não gravou")
        session[_AVISO] = ("erro", f"Não consegui gravar agora ({type(ex).__name__}). Nada foi gravado.")
    ancora = ""
    if ob.startswith("insight:") and "/conversa/" not in destino:
        ancora = "#ins-" + ob.split(":", 1)[1].replace(":", "-")
    return redirect(destino + ancora, code=303)


@bp.route("/tempo-de-resposta")
def tempo_de_resposta():
    """Tempo de resposta: por área pedida, quantos pedidos, abertos, atrasados agora, resolvidos no prazo, e a mediana
    das horas até a 1ª resposta e até resolver; e a lista dos atrasados, o mais velho primeiro."""
    _lei, todos, _st, _g = _leitura()
    peds, nomes = PD.atual(), _nomes_das_torres()
    linhas = [dict(x, nome=nomes.get(x["torre"], x["torre"]), resposta_txt=PD.duracao(x["h_resposta"]),
                   resolver_txt=PD.duracao(x["h_resolver"])) for x in PD.painel(peds)]
    usinas = _usinas()
    atrasados = [dict(p, titulo=t, link=k)
                 for p in _com_pedidos(sorted((p for p in peds.values() if p["situacao"] == "atrasado"), key=PD.ordem),
                                       MO.torres_da_pessoa(), _meu_hmac())
                 for t, k in [_titulo_e_link(p["objeto"], todos, usinas)]]
    total = {"pedidos": len(peds), "abertos": sum(x["abertos"] for x in linhas),
             "atrasados": sum(x["atrasados"] for x in linhas), "resolvidos": sum(x["resolvidos"] for x in linhas),
             "no_prazo": sum(x["no_prazo"] for x in linhas)}
    total["pct_no_prazo"] = round(100 * total["no_prazo"] / total["resolvidos"]) if total["resolvidos"] else None
    return render_template("comando/tempo_de_resposta.html", **_contexto(
        torre=TORRE, tela=TORRE.tela("tempo-de-resposta"), linhas=linhas, atrasados=atrasados, total=total,
        erro_pedidos=PD.ler()["erro"]))


# ── a conversa com @menção (Fase 2, 03/11/2026) ──────────────────────────────────────────────────────────────────────
def _usinas() -> dict:
    """usina_id -> nome, do cadastro do Nexus (o mesmo das regras). Sem o cadastro, vazio: a conversa da usina mostra o
    código."""
    from ...campo import visao
    from ...dados import fatos as D
    try:
        return {D._id(k): str(v.get("nome") or "") for k, v in visao._Base().por_id.items() if v.get("nome")}
    except Exception:            # noqa: BLE001 — o cadastro fora: a conversa segue com o código
        return {}


def _titulo(ob: str, insights: list[dict], usinas: dict) -> tuple[str, str]:
    """(o título da conversa, o link para o objeto)."""
    tipo, _, oid = ob.partition(":")
    if tipo == "insight":
        i = next((x for x in insights if x["id"] == oid), None)
        return ((i["titulo"] if i else f"Insight {oid} (a regra não aponta mais)"),
                na_raiz("/t/comando/insights") + f"#ins-{oid.replace(':', '-')}")
    if tipo == "os":
        return f"OS {oid}", ""
    return f"Usina {usinas.get(int(oid)) or oid}", ""


def _titulo_e_link(ob: str, insights: list[dict], usinas: dict) -> tuple[str, str]:
    """(o título do objeto, a página da conversa dele): é ela que mostra os pedidos e a conversa de qualquer objeto, e
    abre para quem só tem a Caixa de entrada."""
    return _titulo(ob, insights, usinas)[0], na_raiz("/t/comando/conversa/" + ob.replace(":", "/", 1))


def _com_conversa(c: dict | None, meu: str) -> dict:
    """A conversa para a tela: as mensagens com os nomes das áreas e das pessoas mencionadas (o nome sai de quem já
    escreveu na conversa; a pessoa nunca vista fica "uma pessoa")."""
    c = c or {"mensagens": [], "leu": {}}
    nomes, por_hmac = _nomes_das_torres(), {m["pessoa_hmac"]: m["por"] for m in c["mensagens"] if m["por"]}
    msgs = [dict(m, minha=bool(meu) and m["pessoa_hmac"] == meu,
                 areas_nomes=[nomes.get(a, a) for a in m["areas"]],
                 pessoas_nomes=["você" if p == meu else por_hmac.get(p, "uma pessoa") for p in m["pessoas"]])
            for m in c["mensagens"]]
    return {"mensagens": msgs, "n": len(msgs)}


@bp.route("/conversa/<tipo>/<path:oid>")
def conversa(tipo, oid):
    """A página de um objeto (insight, OS ou usina): os pedidos às áreas com prazo e retorno (Fase 3) e a conversa com as
    menções (Fase 2)."""
    from ...comando import conversa as CV
    ob = CV.objeto(tipo, oid)
    if not ob:
        abort(404)
    _lei, todos, _st, _g = _leitura()
    titulo, link = _titulo(ob, todos, _usinas())
    meu = _meu_hmac()
    lido = CV.ler()
    return render_template("comando/conversa.html", **_contexto(
        torre=TORRE, tela=TORRE.tela("caixa-de-entrada"), ob=ob, tipo_nome=CV.TIPOS[tipo], titulo=titulo, link=link,
        conv=_com_conversa(CV.atual().get(ob), meu), erro_conversa=lido["erro"],
        pedidos=_com_pedidos(PD.por_objeto(PD.atual()).get(ob) or [], MO.torres_da_pessoa(), meu),
        erro_pedidos=PD.ler()["erro"]))


@bp.route("/conversa/usina/<int:usina_id>/janela")
def conversa_janela(usina_id):
    """A janela da conversa da usina, por cima do prontuário (13/11/2026, Levi: "A ideia é montar uma caixa de entrada,
    é isso? Escolher o setor e tudo mais. Faça no mesmo modelo de janela [...] algo bem versátil"): um pedaço de página
    (comando/_conversa_janela.html) com a conversa da usina, a Nova demanda com a usina já escolhida e as demandas que a
    citam. `aba` = a que abre (conversa, pedir, demandas). Os formulários são os de sempre (a conversa e a Nova demanda)
    e voltam aqui; aberta sozinha (sem o prontuário), leva à página da conversa."""
    from ...comando import conversa as CV
    from ...comando import demandas as D
    from .demandas_tela import _hoje, _pode_ver
    from .demandas_tela import contexto as contexto_demandas
    ob = CV.objeto("usina", str(usina_id))
    if not ob:
        abort(404)
    if request.headers.get("Sec-Fetch-Dest") == "document":
        return redirect(na_raiz(f"/t/comando/conversa/usina/{usina_id}"))
    nome = _usinas().get(usina_id) or f"usina {usina_id}"
    aba = request.args.get("aba") if request.args.get("aba") in ("conversa", "pedir", "demandas") else "conversa"
    lido = CV.ler()
    dem = contexto_demandas()
    demandas = []
    if not dem["falta"]:
        try:
            demandas = [d for d in D.lista(_hoje()) if any(u == usina_id for u, _n in d["usinas"]) and _pode_ver(d)]
        except Exception:        # noqa: BLE001 — o livro fora: a aba diz que não há, e a conversa segue
            current_app.logger.exception("conversa da usina: as demandas não abriram")
    return render_template("comando/_conversa_janela.html", **_contexto(
        ob=ob, uid=usina_id, nome=nome, aba=aba, conv=_com_conversa(CV.atual().get(ob), _meu_hmac()),
        erro_conversa=lido["erro"], dem=dem, demandas=demandas,
        voltar_jan=f"/t/comando/conversa/usina/{usina_id}/janela?aba=conversa"))


@bp.route("/conversa/pessoas")
def conversa_pessoas():
    """Quem pode ser mencionado (as pessoas com setor e as áreas): a tela pede só quando alguém digita @."""
    from ...comando import conversa as CV
    try:
        pessoas, erro = CV.pessoas_mencionaveis(), ""
    except Exception as ex:      # noqa: BLE001 — o Fracttal ou o banco fora: as áreas seguem
        current_app.logger.warning("conversa: a lista de pessoas não leu (%s)", ex)
        pessoas, erro = [], "Não consegui ler as pessoas agora: as áreas seguem."
    return {"pessoas": pessoas, "areas": [{"id": t, "nome": n} for t, n in _areas()], "erro": erro}


@bp.route("/conversa/acao", methods=["POST"])
def conversa_acao():
    """Escrever na conversa de um objeto (com as menções) ou marcar as menções dele como lidas. Volta à tela de onde
    veio, na conversa."""
    from ...comando import conversa as CV
    voltar = request.form.get("voltar") or ""
    destino = na_raiz(voltar) if voltar.startswith("/t/comando/") else na_raiz("/t/comando/caixa-de-entrada")
    certo = session.get(_CODIGO) or ""
    enviado = request.form.get("codigo") or ""
    if _de_outro_site() or not certo or not hmac.compare_digest(enviado.encode(), certo.encode()):
        session[_AVISO] = ("erro", "O formulário venceu (a sessão mudou desde que a tela abriu): abra a tela de novo. "
                                   "Nada foi gravado.")
        return redirect(destino, code=303)
    acao = request.form.get("acao") or ""
    ob = CV.objeto(*(request.form.get("objeto") or "").partition(":")[::2])
    if acao == "nova":           # a conversa nova da Caixa: a OS pelo número, a usina pela lista
        tipo = request.form.get("tipo") or ""
        ob = CV.objeto(tipo, request.form.get("os" if tipo == "os" else "usina") or "")
        destino = na_raiz(f"/t/comando/conversa/{ob.replace(':', '/', 1)}") if ob else destino
    nomes = _nomes_das_torres()
    try:
        if not ob:
            raise CV.Recusada("Diga sobre o quê: o número da OS ou a usina")
        if acao in ("mensagem", "nova"):
            areas = [t for t in request.form.getlist("area") if t in nomes and t not in FORA_DE_NOTIFICAR]
            feito = CV.registrar(ob, "mensagem", session.get("usuario"), request.form.get("texto") or "",
                                 request.form.getlist("pessoa"), areas)
            n = sum(len(feito[k].split(",")) for k in ("mencoes_pessoas", "mencoes_areas") if feito.get(k))
            avisadas = "" if not n else (": 1 menção avisada." if n == 1 else f": {n} menções avisadas.")
            session[_AVISO] = ("ok", ("Mensagem enviada" + (avisadas or ".")) if feito
                               else "Esta mensagem já estava na conversa.")
        elif acao == "leu":
            CV.registrar(ob, "leu", session.get("usuario"))
            session[_AVISO] = ("ok", "Marcado como lido.")
        else:
            raise CV.Recusada("Ação desconhecida")
    except CV.Recusada as ex:
        session[_AVISO] = ("erro", f"{ex}. Nada foi gravado.")
    except Exception as ex:      # noqa: BLE001 — banco fora: a pessoa sabe que não foi
        current_app.logger.exception("conversa: a mensagem não gravou")
        session[_AVISO] = ("erro", f"Não consegui gravar agora ({type(ex).__name__}). Nada foi gravado.")
    ancora = f"#conv-{ob.replace(':', '-')}" if ob and "/conversa/" not in destino else ""
    return redirect(destino + ancora, code=303)


# as demandas entre setores (12/11/2026) num módulo à parte; importado no fim porque usa o `bp` e os ajudantes daqui
from . import demandas_tela  # noqa: E402,F401
# as Contestações e a Prévia do contrato, vindas da torre Contratos e clientes (12/11/2026)
from . import contestacoes_tela  # noqa: E402,F401

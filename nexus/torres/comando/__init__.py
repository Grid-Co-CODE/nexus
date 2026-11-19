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
import re
import secrets
import time
from urllib.parse import quote

from flask import Blueprint, abort, current_app, redirect, render_template, request, session, url_for

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
    # Saíram do menu em 13/11/2026 (Levi: "remove a opção Kanban, que não tem nada. Então, sala de comando também. Pode
    # remover por hora. Tempo de resposta também. Pode remover. Vai ficar dentro da parte de revisão de contratos"): a
    # Sala de comando e o Kanban, que eram só o lugar reservado; o Tempo de resposta fica por dentro da Prévia do contrato
    # (a página segue no endereço); os Temas do setor viraram uma aba das demandas na Caixa de entrada
    telas=[
        # a ordem do menu (16/11/2026, Levi: "Ordem comando 1 - Caixa de entrada [...] 3 - Visão de contrato 4 - Metas do
        # book 5 - Contestações 6 - Nexus insights"); a Usinas, que era a 2ª, foi para a Usinas 360° no mesmo dia (Levi:
        # "Usinas sai de comando e vai para Usinas 360 abaixo de Visão do responsável!"; as rotas, no `bp_usinas` abaixo)
        Tela("caixa-de-entrada", "Caixa de entrada",
             "O que é meu para fazer hoje, por prazo e valor?",
             "Itens de trabalho do Nexus (insights, OS, chamados, solicitações)", de_todos=True),
        # da torre Contratos e clientes, que saiu do menu (12/11/2026, Levi: "contestações, você vai jogar para o
        # comando, prévia visão do contrato, você vai jogar no comando"; as views em contestacoes_tela.py). A prévia é de
        # todos, para cada setor avaliar sem liberar um por um (o pedido: a avaliação de Contratos e dos outros setores)
        # 18/11/2026: a Prévia virou Contratos, editável pelo gestor do contrato e pelo administrador, com histórico
        # (Levi: "Tire essas opções de subir arquivos [...] Eu quero que essas informações sejam editáveis"; o nome
        # "Contratos" foi a escolha dele; as views em contratos_tela.py; o endereço antigo leva ao novo)
        Tela("contratos", "Contratos",
             "O que cada contrato pede, o que vence e o que está em atraso?",
             "A planilha de controle de Contratos e os PDFs dos contratos, editáveis com histórico", de_todos=True),
        Tela("tempo-de-resposta", "Tempo de resposta",
             "Que área responde no prazo, e quais pedidos estão atrasados?",
             "Pedidos entre áreas, com prazo (nexus_pedidos)", dentro_de="contratos"),
        Tela("metas", "Metas do book",
             "Quais KPIs do book R02 estão fora da meta e piorando?",
             "Aba KPIs do Plano de Documentação"),
        Tela("contestacoes", "Contestações",
             "O que os clientes contestaram nos dashboards, e o que o setor já respondeu?",
             "Dashboard Thopen: a contestação de cada dia, gravada cifrada no banco (livro thopen_contestacoes)"),
        Tela("insights", "Nexus Insights",
             "Que regra cruzou as fontes e apontou um problema com dono?",
             "Regras R01 a R13 do motor de correlação"),
        # 19/11/2026: o portfólio para a gestão, que afunila em cliente e usina e dá a nota de cumprimento do contrato
        # (Levi: "Como a gestão pode acompanhar as carteiras, como está por cliente" e, com o mockup aprovado, "sobe como
        # Visão gerencial (teste)"; as views em gerencial_tela.py). Fica no FIM do menu: a ordem dos outros itens é a que o Levi ditou em 16/11/2026, e a tela nova não a mexe.
        # Não é de todos: tem o valor dos contratos, e só a vê o administrador e o setor que ele marcar em Base › Acessos
        Tela("visao-gerencial", "Visão gerencial (teste)",
             "Como está o portfólio, cliente por cliente e usina por usina, contra o que cada contrato pede?",
             "Comando › Contratos (valor mensal e garantias), Usinas 360° (meta, PR, disponibilidade, OS e rondas)"),
    ],
)

bp = TORRE.criar_blueprint(__name__)

# A Usinas mudou para a Usinas 360° (16/11/2026, Levi: "Usinas sai de comando e vai para Usinas 360 abaixo de Visão do
# responsável!"): a tela é da torre Campo (o id e o /t/campo ficaram quando ela virou "Usinas 360°") e o endereço é
# /t/campo/usinas, que o menu, o portão por setor (`campo/usinas`) e a busca do menu leem; o código não mudou de lugar
# (a lista e o prontuário usam o que é daqui: os insights, as demandas, a IA). O endereço antigo /t/comando/usinas/...
# responde 308 para o novo, com o resto do caminho e o filtro (a Sala de controle da plataforma abre por ele), e a marca
# que o setor tinha em "comando/usinas" vale para "campo/usinas" (`setor_telas.RENOMEADAS`)
USINAS = "/t/campo/usinas"
bp_usinas = Blueprint("torre_campo_usinas", __name__, url_prefix=USINAS)
bp.record_once(lambda estado: estado.app.register_blueprint(bp_usinas))


def _torre_usinas():
    """(a torre, a tela) da Usinas no menu: a Usinas 360° (o eyebrow e o item que acende são os dela)."""
    t = next((x for x in current_app.extensions.get("nexus_torres", []) if x.id == "campo"), None)
    return (t, t.tela("usinas")) if t else (TORRE, None)


@bp.route("/usinas", defaults={"resto": ""}, methods=("GET", "POST"))
@bp.route("/usinas/<path:resto>", methods=("GET", "POST"))
def usinas_mudou(resto):
    """O endereço antigo da Usinas (até 16/11/2026): 308 para o mesmo caminho em /t/campo/usinas, com o filtro (308, e
    não 302, para a pergunta à IA de uma aba aberta no endereço antigo ainda chegar como POST)."""
    q = request.query_string.decode("utf-8", "ignore")
    destino = na_raiz(USINAS + (f"/{resto}" if resto else "")) + (f"?{q}" if q else "")
    return redirect(destino, code=308)

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
    # a lista do motor saiu da tela (19/11/2026, Levi, com o portfólio em funil no alto: "pode tirar esse insights do
    # motor de baixo"); ela continua para quem chega por link (o sino, a Caixa, a conversa e a volta das ações trazem
    # ?abrir= ou um filtro) e pelo "Ver a lista" do pé da página (?lista=1)
    mostrar_lista = bool(a.get("lista") or a.get("abrir") or sev or regra or torre or ver_concluidos)
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
        calculando=lei is None, mostrar_lista=mostrar_lista, n_vivos=len(vivos),
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


@bp_usinas.route("")
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
        "comando/usinas.html", torre=_torre_usinas()[0], tela=_torre_usinas()[1], linhas=CU.filtrar(todas, escolhidos),
        todas=todas, r=r, legenda=CU.LEGENDA, estados=CU.ESTADOS, erro=m["erro"], avisos=m["avisos"],
        insights_calculando=m["insights_calculando"], cos_ts=m["cos_ts"], escolhidos=escolhidos,
        op_clientes=[(c, c) for c in r["clientes"]], op_responsaveis=[(x, x) for x in r["responsaveis"]],
        op_estados=[(k, e[0]) for k, e in CU.ESTADOS.items()], op_meta=list(CU.META_FAIXAS.items()),
        op_conformidade=list(CU.CONFORMIDADES.items()), q=request.args.get("q", ""))


@bp_usinas.route("/abrir")
def usina_pelo_nome():
    """O prontuário pelo NOME da usina (16/11/2026, Levi: "O prontuário da UFV está em NEXUS > COMANDO > USINAS, ao clicar
    na UFV abre o prontuário"): a Sala de controle da Performance (tela da plataforma, que não conhece o id do cadastro
    do Nexus) abre por aqui. Acha a usina na MESMA lista do Comando > Usinas, pelo nome sem acento nem caixa; uma só
    casando, vai ao prontuário dela; nenhuma (ou mais de uma), à lista já com a busca preenchida."""
    import unicodedata
    from urllib.parse import quote

    def norm(s):
        s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().lower()
        return " ".join(re.sub(r"[^a-z0-9 ]", " ", s).split())

    nome = " ".join((request.args.get("nome") or "").split())[:120]
    alvo = norm(nome)
    achadas = [x for x in (_usinas_montadas().get("linhas") or []) if alvo and norm(x.get("usina")) == alvo and x.get("usina_id")]
    if len(achadas) == 1:
        return redirect(na_raiz(f"/t/campo/usinas/{int(achadas[0]['usina_id'])}"))
    return redirect(na_raiz("/t/campo/usinas") + ("?q=" + quote(nome) if nome else ""))


@bp_usinas.route("/<int:usina_id>")
def usina(usina_id):
    """O prontuário da usina no Comando (11/11/2026, Levi: o clique na usina "No próprio Comando", como o prontuário do
    mockup): a linha dela na lista, a Central da usina (a mesma conta da Usinas 360°, `_central_da_usina`) em leitura e
    os insights do Nexus que estão vivos nela. Desde 12/11/2026 (Levi: "juntar todas as informações daquela usina [...]
    métricas, pendências, insights e etc. Deixe forma visual agradável e direta!") junta também o resumo do que pede
    atenção, o mês a mês, o histórico do COS, a zeladoria semanal, as rondas, os equipamentos com OS aberta, os chamados,
    a segurança, as demandas, a composição da ficha e a linha do tempo (`prontuario_dados.montar`)."""
    from ...campo import visao
    from ...comando import diagnostico_mes as DM
    from .prontuario_dados import contexto as _prontuario
    # o mês (18/11/2026, Levi: "O insights e todo o prontuário deve funcionar por mês! Começando por outubro mas quando eu
    # abrir o prontuário quero sempre no mês vigente"): sem `mes`, ou com o vigente, é o prontuário de sempre; o mês
    # fechado (de outubro de 2026 em diante) abre a página do fechamento
    hoje = visao._agora().date()
    mes = DM.mes_fechado(request.args.get("mes"), hoje)
    if mes:
        return _usina_mes(usina_id, mes, hoje)
    ctx = _prontuario(usina_id, rel_url=f"/t/campo/usinas/{usina_id}/relatorio.pdf")
    if ctx is None:
        abort(404)
    return render_template("comando/usina.html", torre=_torre_usinas()[0], tela=_torre_usinas()[1],
                           meses_sel=DM.meses(hoje), mes_uid=usina_id, **ctx)


def _usina_mes(usina_id: int, mes: str, hoje):
    """O prontuário do mês fechado: o fechamento da usina naquele mês, com os dados do relatório em PDF
    (`relatorio_usina.dados`, que recorta o mês) e o que segue pendente hoje. O Insights do mês vem por trás
    (`usina_ia_diagnostico` com `?mes=`). As regras: nexus/comando/diagnostico_mes.py."""
    from ...campo import relatorio_usina as RU
    from ...comando import diagnostico_mes as DM
    usinas = _usinas()
    if usinas and usina_id not in usinas:
        abort(404)
    d = DM.dados(usina_id, mes, hoje)
    if not d.get("usina"):
        abort(404)
    # o tema que não abriu fica None (a página diz "sem leitura"), e o número que falta fica None ("sem dado")
    for tema in ("perf", "rondas", "manut", "religamentos", "chamados"):
        d.setdefault(tema, None)
    perf = d.get("perf") or {}
    meta = {k: (perf.get("meta") or {}).get(k) for k in ("prod_kwh", "meta_kwh", "atingimento", "pr", "pr_meta")}
    disp = {k: (perf.get("disp") or {}).get(k) for k in ("disp", "h_perdidas")}
    ch = (d.get("chamados") or {}).get("mes") or []
    do_mes = lambda dia: bool(dia) and (dia.year, dia.month) == (d["ini"].year, d["ini"].month)  # noqa: E731
    return render_template(
        "comando/usina_mes.html", torre=_torre_usinas()[0], tela=_torre_usinas()[1], d=d, mes=mes, mes_uid=usina_id,
        mes_rot=dict((m, r) for m, r, _v in DM.meses(hoje)).get(mes, mes), meses_sel=DM.meses(hoje), meta=meta, disp=disp,
        cls={"meta": RU._cls_meta(meta.get("atingimento")) if meta.get("atingimento") is not None else "",
             "disp": RU._cls_disp(disp.get("disp")) if disp.get("disp") is not None else ""},
        desligamentos=DM.desligamentos(d), tarefas=sum(x["tarefas"] for x in (d.get("manut") or {}).get("feitas") or []),
        os_abertas=sum(x["os"] for x in (d.get("manut") or {}).get("abertas") or []),
        chamados_fin=[c for c in ch if c.get("situacao") == "concluido" and do_mes(c.get("fim"))],
        chamados_ab=[c for c in ch if do_mes(c.get("ini"))],
        nomes_tema={"perf": "a performance", "rondas": "as rondas", "manut": "a manutenção",
                    "religamentos": "as paradas do COS", "chamados": "os chamados de garantia",
                    "guardado": "o fechamento guardado"})


@bp_usinas.route("/<int:usina_id>/relatorio.pdf")
def usina_relatorio(usina_id):
    """O relatório da usina em PDF (o do cliente, `campo/relatorio_usina.py`) pelo endereço do Comando: a mesma conta da
    Usinas 360° (`responsaveis_usina_relatorio`), para quem tem o Comando > Usinas e não a Visão do responsável."""
    from ..campo import responsaveis_usina_relatorio
    return responsaveis_usina_relatorio(usina_id)


def _guardado_do_dossie(chave, ler, ttl_s: int = 600):
    """A leitura que serve a TODAS as usinas (a programação das duas semanas, as fichas dos contratos), guardada 10 minutos
    por app: o Insights de madrugada monta 144 dossiês em fila e não pode ler o mesmo livro 144 vezes. O erro não se
    guarda: sobe, e a fonte vai para "O que ficou de fora"."""
    import time
    guarda = current_app.extensions.setdefault("nexus_dossie_fontes", {})
    g = guarda.get(chave)
    if g and time.time() < g[0]:
        return g[1]
    valor = ler()
    guarda.clear() if len(guarda) > 8 else None
    guarda[chave] = (time.time() + ttl_s, valor)
    return valor


def _extras_do_dossie(usina_id: int, codigo: str = "", x: dict | None = None) -> dict:
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

    def religamentos():
        """A tela COS › Religamentos desta usina (14/11/2026, Levi: "inclua no dossiê o que aconteceu no religamento"):
        as ocorrências de 30 dias da Ronda COS de todos os clientes, só as da usina (pelo código do Fracttal), na régua
        de lá (`religamentos.painel`). Sem a fonte do Andamento (o PC), None: "sem leitura"."""
        from ...cos import andamento as AND
        from ...cos import religamentos as RE
        cfg = current_app.config
        if not AND.fonte(cfg).ligada:
            return None
        cod = str(codigo or "").strip().upper()
        clientes, erro = AND.clientes(cfg)
        if erro or not cod:
            raise RuntimeError(erro or "a usina sem código do Fracttal")
        ocs = []
        for c in clientes:
            le = AND.ler_ocorrencias(cfg, c, RE.DIAS_PADRAO)
            ocs += [o for o in (le.dados or {}).get("ocorrencias") or [] if str(o.get("usina_codigo") or "").upper() == cod]
        p = RE.painel(AND.Leitura("", {"ocorrencias": ocs}), ver="todos")
        return [{"equipamento": e.rotulo, "total": e.total, "repete": e.repete, "reincidente": e.reincidente,
                 "desfechos": [(RE.DESFECHOS[k][0], n) for k, n in e.desfechos.items()], "tipos": e.tipos, "os": e.os,
                 "ultima": e.ultima.strftime("%d/%m %H:%M") if e.ultima else ""} for e in (p.itens if p else [])]
    def programacao():
        """A programação do PCM: a semana corrente e a seguinte (19/11/2026; `dossie_fontes.programacao_da_usina`)."""
        from datetime import timedelta

        from ...campo import responsaveis as R
        from ...comando import dossie_fontes as DF
        from ...dados.calendario import data_id
        hoje = visao._agora().date()
        segunda = hoje - timedelta(days=hoje.weekday())
        linhas = _guardado_do_dossie(("programacao", segunda), lambda: R._programacao_recente(
            {data_id(segunda), data_id(segunda + timedelta(days=7))}))
        return DF.programacao_da_usina(linhas, usina_id, hoje)

    def contrato():
        """O que o contrato pede: a garantia, o PR e os prazos, sem valor em reais (19/11/2026; `dossie_fontes`)."""
        from ...comando import dossie_fontes as DF
        from .gerencial_tela import _contratos
        hoje = visao._agora().date()

        def fichas():
            v, aviso = _contratos(hoje)
            if v is None:
                raise RuntimeError(aviso or "o Comando › Contratos não abriu")
            return v.get("fichas") or {}
        return DF.contrato_da_usina(_guardado_do_dossie(("contratos", hoje), fichas), (x or {}).get("cliente") or "",
                                    (x or {}).get("usina") or "", codigo)
    return {"ativos": tentar("a Confiabilidade", ativos), "acompanhamentos": tentar("o acompanhamento da Engenharia", acompanhamentos),
            "relatorios": tentar("os relatórios de falha", relatorios), "observacoes": tentar("as observações", observacoes),
            "religamentos": tentar("os religamentos do COS", religamentos),
            "programacao": tentar("a programação do PCM", programacao), "contrato": tentar("o Comando › Contratos", contrato)}


def _dossie(usina_id: int):
    """(o contexto do prontuário, o dossiê montado) ou 404 para a usina que não está na lista."""
    from ...campo import visao
    from ...comando import dossie as DS
    from .prontuario_dados import contexto as _prontuario
    ctx = _prontuario(usina_id)
    if ctx is None:
        abort(404)
    x = ctx.get("x") or {}
    return ctx, DS.montar(ctx, visao._agora(), extras=_extras_do_dossie(usina_id, x.get("codigo") or "", x))


@bp_usinas.route("/<int:usina_id>/dossie")
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
    return render_template("comando/dossie.html", torre=_torre_usinas()[0], tela=_torre_usinas()[1], x=ctx["x"], d=d)


@bp_usinas.route("/<int:usina_id>/dossie.md")
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


# ── Nexus IA: a pergunta sobre a usina (13/11/2026) ──────────────────────────────────────────────────────────────────
# Levi: "Do prontuário, eu quero que tenha um chat. Onde a pessoa possa fazer perguntas [...] como foi a performance no
# mês? Por que a usina caiu? Qual a tendência? [...] Teste com várias IAs". As regras moram em nexus/comando/ia.py.
# 16/11/2026, Levi: "libera para todos": quem abre o prontuário pergunta (era só administrador, no teste). E a caixa fica
# na própria tela, embaixo do Nexus IA Insights, sem janela (retorno do time: "Tem que ser a caixa de texto para a IA sem
# abrir uma janela"): o prontuario.js pede o pedaço desta rota e o põe no lugar. O teto do mês segue valendo para todos.
@bp_usinas.route("/<int:usina_id>/ia")
def usina_ia(usina_id):
    from ...comando import ia as IA
    from .prontuario_dados import contexto as _prontuario
    ctx = _prontuario(usina_id)
    if ctx is None:
        abort(404)
    cfg = current_app.config
    dados = dict(x=ctx["x"], modelos=IA.disponiveis(cfg), padrao=IA.padrao(cfg), sugestoes=IA.SUGESTOES, gasto=IA.gasto_do_mes(cfg),
                 teto=IA.teto(cfg), max_pergunta=IA.MAX_PERGUNTA, setores=_ia_setores(), criar_os=_ia_criar_os())
    if request.args.get("parcial") == "1":          # a janela por cima do prontuário
        return render_template("comando/_ia.html", **dados)
    return render_template("comando/ia.html", torre=_torre_usinas()[0], tela=_torre_usinas()[1], **dados)


def _setores_ativos() -> list[dict]:
    """[{setor_id, nome, temas: [{tema_id, nome}]}] dos setores ativos do cadastro: para onde o diagnóstico do dia pode
    mandar o "Fazer", com os temas em uso de cada um (15/11/2026: a IA escolhe o tema, e a janela do pedido vem com ele).
    A área (Chamados, na Performance) é mais um destino, com os temas dela; o setor fica com os temas sem área."""
    from ...auth import setor_telas as ST
    from ...cadastro import setores as S
    from ...dados.conexao import banco
    try:
        from ...comando import temas_padrao as TP
        from ...comando import demandas as DM
        st = ST._setores_no_clique(*banco())
        try:
            temas = DM.temas()
        except Exception:        # noqa: BLE001 — sem os temas, o "Fazer" vem só com o setor
            current_app.logger.exception("Diagnóstico do dia: os temas não abriram")
            temas = []

        def da(sid, area=""):
            return [{"tema_id": t["tema_id"], "nome": t["nome"]} for t in temas
                    if t["setor_id"] == sid and (t.get("area") or "").lower() == area.lower()]
        out = []
        for s in S.ativos(st.get("setores") or []):
            out.append({"setor_id": s["setor_id"], "nome": s["nome"], "temas": da(s["setor_id"])})
            # a área do setor como mais um destino ("Chamados", na Performance): o pedido vai ao setor, no tema da área
            out += [{"setor_id": f"{s['setor_id']}:{a}", "nome": a, "temas": da(s["setor_id"], a)}
                    for a in TP.areas_do_setor(s["nome"])]
        return out
    except Exception:            # noqa: BLE001 — sem os setores, o item sai sem o "Fazer"
        current_app.logger.exception("Diagnóstico do dia: os setores não abriram")
        return []


def _ia_setores() -> list[dict]:
    """Para onde a resposta pode mandar demanda (14/11/2026, Levi: "ao citar coisas que podem ser feitas por outros
    setores, tem que dar a opção de caixa de entrada para mandar msg para esses setores"): os setores com pessoas, cada um
    com as pessoas (menos quem pergunta) e os temas ativos, a mesma regra da Nova demanda. Fora do ar: lista vazia (a
    resposta sai sem o botão)."""
    from ...auth import setor_telas as ST
    from ...cadastro import setores as S
    from ...comando import demandas as DM
    from ...dados.conexao import banco
    # os setores ativos do cadastro: a IA conhece todos, mesmo sem pessoa ou tema lido agora (no PC sem a credencial do
    # Fracttal não há os nomes; tema, o setor cria em Caixa de entrada › Temas do setor). O botão diz o que falta
    try:
        st = ST._setores_no_clique(*banco())
        out = {s["setor_id"]: {"setor_id": s["setor_id"], "nome": s["nome"], "pessoas": [], "temas": []}
               for s in S.ativos(st.get("setores") or [])}
    except Exception:            # noqa: BLE001 — sem os setores, sem o botão
        current_app.logger.exception("Nexus IA: os setores não abriram")
        return []
    meu = _meu_hmac()
    # a área do setor é mais um destino (16/11/2026, Levi: "quem cobra é o time de chamados [...] solicitar o time de
    # chamados"): "Chamados", na Performance, com os temas dela e as pessoas marcadas nela (sem ninguém marcado, o setor
    # inteiro), a mesma regra da Nova demanda
    from ...comando import areas as AR
    from ...comando import temas_padrao as TP
    areas = {f"{sid}:{a}": {"setor_id": f"{sid}:{a}", "nome": a, "pessoas": [], "temas": [], "_sid": sid, "_area": a}
             for sid, s in out.items() for a in TP.areas_do_setor(s["nome"])}
    try:
        mapa = AR.ler(current_app.config)
    except Exception:            # noqa: BLE001 — sem o mapa, a área recebe o setor inteiro
        current_app.logger.exception("Nexus IA: as áreas das demandas não abriram")
        mapa = {}
    for nome, ler in (("pessoas", DM.pessoas_com_setor), ("temas", DM.temas)):
        try:
            itens = ler()
        except Exception:        # noqa: BLE001 — a parte que não abriu fica vazia, e o botão diz
            current_app.logger.exception("Nexus IA: %s das demandas não abriram", nome)
            continue
        for x in itens:
            s = out.get(x["setor_id"])
            if not s:
                continue
            if nome == "pessoas" and x["hmac"] != meu:
                s["pessoas"].append({"hmac": x["hmac"], "nome": x["nome"]})
                for a in areas.values():
                    if a["_sid"] == x["setor_id"]:
                        a.setdefault("_todas", []).append({"hmac": x["hmac"], "nome": x["nome"]})
                        if a["_area"] in AR.areas_da_pessoa(mapa, x["setor_id"], x["hmac"]):
                            a["pessoas"].append({"hmac": x["hmac"], "nome": x["nome"]})
            elif nome == "temas":
                t = {"tema_id": x["tema_id"], "nome": x["nome"], "prazo": x["prazo_dias_uteis"]}
                area = (x.get("area") or "").strip()
                if not area:
                    s["temas"].append(t)
                elif f"{x['setor_id']}:{area}" in areas:
                    areas[f"{x['setor_id']}:{area}"]["temas"].append(t)
    for a in areas.values():
        if not a["pessoas"]:
            a["pessoas"] = a.get("_todas") or []
        for k in ("_sid", "_area", "_todas"):
            a.pop(k, None)
    return sorted(list(out.values()) + list(areas.values()), key=lambda s: s["nome"].lower())


def _ia_criar_os() -> dict:
    """{setor sem acento: {rot, url}} dos setores que recebem OS pelo Criar OS do prontuário (14/11/2026, Levi: "para
    engenharia dá para criar OS, para performance dá para a pessoa criar um OS"; chamado não, quem abre é o técnico):
    a ação para eles ganha o "Criar OS" ao lado do "Mandar para a caixa de entrada"."""
    from .prontuario_dados import CRIAR_OS
    return {setor: {"rot": rot, "url": url} for rot, _sub, url, _leva in CRIAR_OS
            for setor in ("engenharia", "performance") if url.endswith("/solicitacao/" + setor)}


def _ia_meu_setor() -> str:
    try:
        from .demandas_tela import _meu_setor
        return (_meu_setor() or {}).get("nome") or ""
    except Exception:            # noqa: BLE001
        return ""


def _ia_relatorio(usina_id: int, pedido: dict) -> dict:
    """O PDF do prontuário que o pedido quer (o mês e os temas), sem passar pela IA: o mesmo endereço do botão Relatório."""
    from urllib.parse import urlencode

    from ...campo import relatorio_usina as RU
    from ...campo import visao
    hoje = visao._agora().date()
    rotulo = dict(RU.meses(hoje)).get(pedido["mes"], pedido["mes"])
    temas = dict(RU.TEMAS)
    q = urlencode([("mes", pedido["mes"])] + [("tema", t) for t in pedido["temas"]])
    aviso = (f"O relatório tem só os três últimos meses: vai o de {rotulo.lower()}." if pedido.get("mes_fora") else "")
    return {"url": na_raiz(f"/t/campo/usinas/{usina_id}/relatorio.pdf?{q}"), "mes": rotulo,
            "temas": [temas[t] for t in pedido["temas"]], "aviso": aviso}


def _ia_pedido(usina_id: int):
    """A conferência comum às duas rotas da pergunta (a de sempre e a em fluxo). Devolve (a resposta pronta, None) na
    recusa e no pedido de relatório, ou (None, o pedido conferido, com o dossiê montado AGORA: o mesmo do "Dossiê para
    a IA", uma vez para todos os modelos pedidos)."""
    from flask import jsonify

    from ...campo import visao
    from ...comando import ia as IA
    if _de_outro_site():
        return (jsonify(ok=False, erro="Pedido de outro site."), 403), None
    b = request.get_json(silent=True) or {}
    pergunta = IA.limpar_pergunta(b.get("pergunta"))
    ids = [str(i) for i in (b.get("modelos") or []) if isinstance(i, str)][:10]
    if not pergunta:
        return (jsonify(ok=False, erro="Escreva a pergunta."), 400), None
    if not ids:
        return (jsonify(ok=False, erro="Escolha ao menos um modelo."), 400), None
    # o pedido de relatório baixa o PDF do prontuário, sem gastar pedido da IA (14/11/2026, Levi: "se eu pedisse um
    # relatório já baixa um automático que já temos criado [...] se eu pedir só chamado vem filtrado só chamado")
    rel = IA.pedido_de_relatorio(pergunta, visao._agora().date())
    if rel:
        return jsonify(ok=True, relatorio=_ia_relatorio(usina_id, rel), respostas=[]), None
    historico = [h for h in (b.get("historico") or []) if isinstance(h, dict)][-IA.MAX_HISTORICO:]
    _ctx, d = _dossie(usina_id)
    return None, {"pergunta": pergunta, "ids": ids, "historico": historico, "dossie": d, "quem": _meu_hmac(),
                  "setores": [s["nome"] for s in _ia_setores()], "meu_setor": _ia_meu_setor(), "pensar": _ia_pensar(b)}


def _ia_pensar(b: dict) -> bool:
    """O modo da pergunta (18/11/2026, Levi: "pode ter a opção Busca/Pensamento. O botão fica no busca mas se a pessoa
    quiser que pense ela ativa o pensamento"): só `modo: "pensamento"` faz o Claude pensar antes de responder. Sem o
    campo, ou com outro valor, vale Busca (a resposta direta, mais rápida)."""
    return str(b.get("modo") or "").strip().lower() == "pensamento"


def _ia_fecho(usina_id: int, p: dict, respostas: list) -> dict:
    """O que a tela recebe com as respostas: o tamanho do dossiê, o gasto do mês, o teto e a oferta do relatório do tema
    da conversa (14/11/2026, Levi: "baixar relatório de religamento, baixar relatório de COS, baixar relatório de
    performance"): o PDF do prontuário só com aquele tema, no mês da conversa."""
    from ...campo import visao
    from ...comando import ia as IA
    cfg = current_app.config
    primeira = next((r for r in respostas if r.get("ok")), {})
    mes = IA.mes_da_conversa(p["pergunta"], visao._agora().date())
    relatorios = [_ia_relatorio(usina_id, {"temas": [t], "mes": mes})
                  for t in IA.temas_da_conversa(p["pergunta"], primeira.get("texto") or "")]
    return {"ok": True, "respostas": respostas, "dossie_tokens": p["dossie"]["tokens_estimados"],
            "gasto": IA.gasto_do_mes(cfg), "teto": IA.teto(cfg), "relatorios": relatorios}


@bp_usinas.route("/<int:usina_id>/ia/perguntar", methods=["POST"])
def usina_ia_perguntar(usina_id):
    """JSON {pergunta, modelos: [ids], historico: [{pergunta, resposta}]} -> {ok, respostas, dossie_tokens, gasto, teto}.
    O teto do mês não barra a pergunta (18/11/2026): passou, o pago para e as grátis respondem (`IA.perguntar`)."""
    from flask import jsonify

    from ...comando import ia as IA
    recusa, p = _ia_pedido(usina_id)
    if recusa is not None:
        return recusa
    cfg = current_app.config
    respostas = IA.perguntar(cfg, p["ids"], p["dossie"]["texto"], p["pergunta"], p["historico"], setores=p["setores"],
                             meu_setor=p["meu_setor"], pensar=p["pensar"])
    IA.registrar(cfg, usina_id, p["pergunta"], respostas, p["quem"], p["dossie"]["tokens_estimados"])
    resp = jsonify(**_ia_fecho(usina_id, p, respostas))
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp_usinas.route("/<int:usina_id>/ia/perguntar/fluxo", methods=["POST"])
def usina_ia_perguntar_fluxo(usina_id):
    """A mesma pergunta, com o texto chegando enquanto a IA escreve (18/11/2026, Levi, com a resposta do Haiku em 17,1 s
    numa pergunta simples: "demorou muito"; à pergunta "Quer que o texto apareça enquanto a IA escreve?": "Sim"). O
    pedido é o da rota de sempre, e a recusa e o relatório voltam em JSON, iguais. A resposta é `text/event-stream`,
    uma linha `data: {json}` por evento, com `t`: "inicio" (o dossiê está montado e a pergunta saiu), "pensando",
    "texto" (o trecho em `d`) e "fim" (o mesmo JSON da rota de sempre). O registro do gasto acontece mesmo com a tela
    fechada no meio: a resposta termina por trás, porque a Anthropic cobra por ela do mesmo jeito. As regras de quando
    há texto ao vivo: `IA.perguntar_em_fluxo`."""
    import json

    from flask import stream_with_context

    from ...comando import ia as IA
    recusa, p = _ia_pedido(usina_id)
    if recusa is not None:
        return recusa
    cfg = current_app.config

    def evento(t: str, **k) -> str:
        return "data: " + json.dumps(dict(k, t=t), ensure_ascii=False) + "\n\n"

    def gerar():
        fluxo = IA.perguntar_em_fluxo(cfg, p["ids"], p["dossie"]["texto"], p["pergunta"], p["historico"],
                                      setores=p["setores"], meu_setor=p["meu_setor"], pensar=p["pensar"])
        respostas = None
        try:
            yield evento("inicio")
            for tipo, dado in fluxo:
                if tipo == "fim":
                    respostas = dado
                else:
                    yield evento(tipo, d=dado)
        finally:
            if respostas is None:           # a tela fechou no meio: a resposta termina por trás, para o gasto entrar
                respostas = next((dado for tipo, dado in fluxo if tipo == "fim"), [])
            IA.registrar(cfg, usina_id, p["pergunta"], respostas, p["quem"], p["dossie"]["tokens_estimados"])
        yield evento("fim", **_ia_fecho(usina_id, p, respostas))

    resp = current_app.response_class(stream_with_context(gerar()), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Accel-Buffering"] = "no"        # o proxy não junta os pedaços
    return resp


@bp_usinas.route("/<int:usina_id>/ia/diagnostico")
def usina_ia_diagnostico(usina_id):
    """O diagnóstico do dia da IA, no lugar do parecer do prontuário (14/11/2026, Levi: "Sempre que a pessoa for abrir o
    prontuário da usina, abrir o diagnóstico da IA [...] uma pessoa diferente abrir também no mesmo dia, usar o mesmo
    diagnóstico [...] Para não ficar gastando token à toa"). JSON {estado: pronto | texto | preparando | erro | teto |
    sem_ia, diag, ...}. O guardado do dia volta na hora; sem ele, a primeira abertura pega a trava, monta o dossiê e manda
    fazer numa thread à parte (a página não espera), e as outras veem "preparando" até ficar pronto. Com o "preparando"
    vai o último diagnóstico que deu certo (`anterior`), que a tela mostra com a data dele até o de hoje chegar
    (18/11/2026, Levi: "demora 40 segundos para uma resposta após eu abrir a usina"). Abre para quem abre o prontuário
    (as regras e o guardado: nexus/comando/diagnostico.py)."""
    import threading

    from flask import jsonify

    from ...campo import visao
    from ...comando import diagnostico as DG
    from ...comando import diagnostico_mes as DM
    from ...comando import ia as IA
    usinas = _usinas()
    if usinas and usina_id not in usinas:
        abort(404)
    cfg = current_app.config
    # o mês fechado tem o diagnóstico DO MÊS (um por usina por mês, guardado); sem `mes`, ou com o vigente, o do dia
    mes = DM.mes_fechado(request.args.get("mes"), visao._agora().date())
    if mes:
        return _diagnostico_do_mes(usina_id, mes)
    dia = DG.hoje()
    d = DG.guardado(cfg, usina_id, dia)
    if d:
        out = DG.para_tela(d)
    elif not DG.disponivel(cfg):
        out = {"estado": "sem_ia"}
    elif DG.em_andamento(cfg, usina_id, dia):
        out = {"estado": "preparando"}
    elif not DG.travar(cfg, usina_id, dia):
        out = {"estado": "preparando"}
    else:
        try:
            _ctx, dz = _dossie(usina_id)
        except BaseException:
            DG.soltar(cfg, usina_id, dia)
            raise
        args = (dict(cfg), usina_id, dz["texto"], dz["tokens_estimados"], dia, _setores_ativos())
        if cfg.get("TESTING"):
            out = DG.para_tela(DG.gerar(*args))
        else:
            threading.Thread(target=DG.gerar, args=args, daemon=True, name=f"diagnostico-{usina_id}").start()
            out = {"estado": "preparando"}
    if out.get("estado") == "preparando":
        ant = DG.anterior(cfg, usina_id, dia)
        if ant:
            out["anterior"] = DG.para_tela(ant)
    resp = jsonify(out)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp_usinas.route("/<int:usina_id>/dossie-do-mes.md")
def usina_dossie_do_mes(usina_id):
    """O fechamento do mês em texto (Markdown), o mesmo que a IA lê para o diagnóstico do mês (`?mes=AAAA-MM`, só mês
    fechado): é por ele que se confere o diagnóstico. Abre para quem abre o prontuário (sem o nome das pessoas)."""
    from ...campo import relatorio_usina as RU
    from ...campo import visao
    from ...comando import diagnostico_mes as DM
    hoje = visao._agora().date()
    mes = DM.mes_fechado(request.args.get("mes"), hoje)
    usinas = _usinas()
    if not mes or (usinas and usina_id not in usinas):
        abort(404)
    resp = current_app.response_class(DM.dossie(DM.dados(usina_id, mes, hoje)), mimetype="text/markdown")
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _diagnostico_do_mes(usina_id: int, mes: str):
    """O Nexus IA Insights do mês fechado: JSON {estado: pronto | texto | preparando | erro | sem_ia, mes, diag}. O
    guardado volta na hora; sem ele, a primeira abertura pega a trava, lê o fechamento do mês e manda a IA fazer numa
    thread à parte. As regras: nexus/comando/diagnostico_mes.py."""
    import threading

    from flask import jsonify

    from ...campo import relatorio_usina as RU
    from ...campo import visao
    from ...comando import diagnostico as DG
    from ...comando import diagnostico_mes as DM
    cfg = current_app.config
    ch = DM.chave(mes)
    g = DM.guardado(cfg, usina_id, mes)
    if g:
        out = DM.para_tela(g)
    elif not DG.disponivel(cfg):
        out = {"estado": "sem_ia", "mes": mes}
    elif DG.em_andamento(cfg, usina_id, ch) or not DG.travar(cfg, usina_id, ch):
        out = {"estado": "preparando", "mes": mes}
    else:
        try:
            d = DM.dados(usina_id, mes, visao._agora().date())
        except BaseException:
            DG.soltar(cfg, usina_id, ch)
            raise
        if cfg.get("TESTING"):
            out = DM.para_tela(DM.gerar(dict(cfg), usina_id, d))
        else:
            threading.Thread(target=DM.gerar, args=(dict(cfg), usina_id, d), daemon=True,
                             name=f"diagnostico-mes-{usina_id}").start()
            out = {"estado": "preparando", "mes": mes}
    resp = jsonify(out)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp_usinas.route("/<int:usina_id>/ia/demanda", methods=["POST"])
def usina_ia_demanda(usina_id):
    """A ação de outro setor que a resposta sugeriu, mandada como demanda (JSON {para_hmac, para_setor_id, tema_id,
    titulo, descricao, os, novo_id}): a mesma Nova demanda da Caixa de entrada (`demandas.abrir`, as mesmas recusas),
    com a usina deste prontuário. Quem pergunta (todos, desde 16/11/2026) manda."""
    from flask import jsonify

    from ...comando import demandas as DM
    from .demandas_tela import _usuario
    if _de_outro_site():
        return jsonify(ok=False, erro="Pedido de outro site."), 403
    b = request.get_json(silent=True) or {}
    form = {k: str(b.get(k) or "") for k in ("para_hmac", "para_setor_id", "tema_id", "titulo", "descricao", "os", "novo_id")}
    form["usinas"] = [str(usina_id)]
    try:
        d = DM.abrir(form, [], _usuario())
    except DM.Recusada as ex:
        return jsonify(ok=False, erro=f"{ex}. Nada foi enviado."), 400
    except Exception as ex:      # noqa: BLE001 — banco fora: a pessoa sabe que não foi
        current_app.logger.exception("Nexus IA: a demanda não foi gravada")
        return jsonify(ok=False, erro=f"Não consegui gravar agora ({type(ex).__name__}). Nada foi enviado."), 500
    return jsonify(ok=True, demanda_id=d.get("demanda_id"),
                   aviso="Demanda enviada. Ela está em \u201cQue eu pedi\u201d, na Caixa de entrada, e quem recebeu é avisado no sininho.")


# ── Nexus IA da carteira (16/11/2026) ────────────────────────────────────────────────────────────────────────────────
# Retorno do time: "Eu queria a IA fora do ambiente da usina. Por exemplo... Agora eu quero ver todos os chamados em aberto
# e correlacionar com as usinas com baixa disponibilidade e performance". Levi, com o esboço na mão: "libera para todos e
# só no Comando › Usinas, pode construir". A caixa fica no alto da lista, embutida (comando-usinas.js pede o pedaço); o
# dossiê e as instruções moram em nexus/comando/carteira_ia.py; a IA, a troca e a blindagem são as do prontuário.
def _carteira_ia(cliente: str | None = None) -> dict:
    """O dossiê da carteira de agora, das mesmas cópias que a lista e o prontuário já leem (as de 5 min). Com `cliente`,
    só as usinas dele (o dossiê do cliente)."""
    from ...campo import visao
    from ...comando import carteira_ia as CI
    from .prontuario_dados import _de_todas
    m = _usinas_montadas()
    if cliente is not None:
        m = {**m, "linhas": [l for l in m["linhas"] if (l.get("cliente") or "") == cliente]}
    lei = _de_todas()
    d = lei.dados or {}
    avisos = list(m.get("avisos") or []) + list((d.get("erros") or {}).values())
    if lei.erro:
        avisos.append(f"o histórico das usinas ({lei.erro})")
    if m.get("erro"):
        avisos.append(f"a Visão do responsável ({m['erro']})")
    man = {u.get("usina_id"): u.get("manutencao") or {} for u in (m.get("visao") or {}).get("usinas") or []}
    return CI.montar(m["linhas"], {"disps": d.get("disps"), "metas": d.get("metas"), "cos": d.get("cos"),
                                   "chamados": d.get("chamados"), "nomes_equip": d.get("nomes_equip"), "manutencao": man,
                                   "vivos": m.get("vivos") or {}, "avisos": avisos}, visao._agora())


@bp_usinas.route("/ia")
def carteira_ia():
    """A caixa da Nexus IA da carteira, como pedaço de página para o alto do Comando › Usinas (sem janela)."""
    from ...comando import carteira_ia as CI
    from ...comando import ia as IA
    cfg = current_app.config
    n = len(_usinas_montadas()["linhas"])
    return render_template("comando/_ia.html", modelos=IA.disponiveis(cfg), padrao=IA.padrao(cfg), sugestoes=CI.SUGESTOES,
                           gasto=IA.gasto_do_mes(cfg), teto=IA.teto(cfg), max_pergunta=IA.MAX_PERGUNTA,
                           setores=_ia_setores(), criar_os=_ia_criar_os(), ia_base="/t/campo/usinas/ia",
                           ia_sobre=f"sobre a carteira inteira: {n} usinas",
                           ia_exemplo="Ex.: quais usinas com chamado aberto estão com a disponibilidade baixa?")


@bp_usinas.route("/ia/perguntar", methods=["POST"])
def carteira_ia_perguntar():
    """JSON {pergunta, modelos, historico} -> {ok, respostas, ...}, como a da usina, com o dossiê da carteira de agora e
    as instruções dela. Cada resposta leva `usinas` ({nome: o prontuário}) das usinas que cita, e cada ação as
    `usinas_ids` dela (os nomes do dossiê e a usina da OS do chamado)."""
    return _perguntar_carteira()


def _perguntar_carteira(extra=None, instrucoes: str | None = None, prefixo: str = "[carteira] "):
    """A pergunta sobre a carteira (o corpo da rota acima). O Comando › Nexus Insights (19/11/2026) a usa com o dossiê
    ampliado: `extra` = a função que devolve o texto das seções a mais (chamada só quando a pergunta vai à IA, não na
    resposta pronta) e `instrucoes` = as dele."""
    from flask import jsonify

    from ...comando import carteira_ia as CI
    from ...comando import ia as IA
    if _de_outro_site():
        return jsonify(ok=False, erro="Pedido de outro site."), 403
    b = request.get_json(silent=True) or {}
    pergunta = IA.limpar_pergunta(b.get("pergunta"))
    ids = [str(i) for i in (b.get("modelos") or []) if isinstance(i, str)][:10]
    if not pergunta:
        return jsonify(ok=False, erro="Escreva a pergunta."), 400
    if not ids:
        return jsonify(ok=False, erro="Escolha ao menos um modelo."), 400
    cfg = current_app.config
    # o teto do mês não barra a pergunta (18/11/2026): passou, o pago para e as grátis respondem (`IA.perguntar`)
    teto = IA.teto(cfg)
    historico = [h for h in (b.get("historico") or []) if isinstance(h, dict)][-IA.MAX_HISTORICO:]
    t0 = time.monotonic()
    dz = _carteira_ia()
    por_nome = {k.lower(): v for k, v in dz["usinas"].items()}
    # a pergunta sugerida sai pronta, contada pelo Nexus, sem IA (16/11/2026, Levi: "e a demora pai": a IA grátis levou
    # de 54 a 150 s nelas e errou a conta); a pergunta escrita pela pessoa vai à IA
    pronta = CI.resposta_pronta(pergunta, dz)
    if pronta:
        respostas = [{"id": "nexus", "rotulo": "Contado pelo Nexus", "provedor": "sem IA, na hora", "ok": True,
                      "texto": pronta, "acoes": [], "os": {}, "sem_ia": True,
                      "ms": round((time.monotonic() - t0) * 1000), "entrada": 0, "saida": 0, "cache_lido": 0,
                      "custo_usd": 0.0, "preco_oficial": True, "numeros": {"n": 0, "no_dossie": 0, "fora": []}}]
    else:
        setores = [s["nome"] for s in _ia_setores()]
        texto = dz["texto"] + ("\n" + extra() if extra else "")
        respostas = IA.perguntar(cfg, ids, texto, pergunta, historico, setores=setores,
                                 meu_setor=_ia_meu_setor(), instrucoes=instrucoes or CI.INSTRUCOES, pensar=_ia_pensar(b))
    for r in respostas:
        if not r.get("ok"):
            continue
        r["usinas"] = {n: na_raiz(f"/t/campo/usinas/{uid}")
                       for n, uid in CI.usinas_citadas(r.get("texto") or "", dz["usinas"]).items()}
        for a in r.get("acoes") or []:
            uids = {por_nome[n.lower()] for n in a.get("usinas") or [] if n.lower() in por_nome}
            if a.get("os") is not None and str(a["os"]) in dz["os_usina"]:
                uids.add(dz["os_usina"][str(a["os"])])
            a["usinas_ids"] = sorted(uids)
    IA.registrar(cfg, 0, prefixo + pergunta, respostas, _meu_hmac(), dz["tokens_estimados"])
    resp = jsonify(ok=True, respostas=respostas, dossie_tokens=dz["tokens_estimados"], gasto=IA.gasto_do_mes(cfg),
                   teto=teto, relatorios=[])
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp_usinas.route("/ia/demanda", methods=["POST"])
def carteira_ia_demanda():
    """A ação de outro setor da resposta da carteira, mandada como demanda: a mesma Nova demanda (`demandas.abrir`), com
    as usinas da ação (só as da lista do Comando › Usinas)."""
    from flask import jsonify

    from ...comando import demandas as DM
    from .demandas_tela import _usuario
    if _de_outro_site():
        return jsonify(ok=False, erro="Pedido de outro site."), 403
    b = request.get_json(silent=True) or {}
    form = {k: str(b.get(k) or "") for k in ("para_hmac", "para_setor_id", "tema_id", "titulo", "descricao", "os", "novo_id")}
    validas = {l["usina_id"] for l in _usinas_montadas()["linhas"]}
    pedidas = b.get("usinas") if isinstance(b.get("usinas"), list) else str(b.get("usinas") or "").split(",")
    form["usinas"] = [str(x).strip() for x in pedidas if str(x).strip().isdigit() and int(str(x).strip()) in validas]
    try:
        d = DM.abrir(form, [], _usuario())
    except DM.Recusada as ex:
        return jsonify(ok=False, erro=f"{ex}. Nada foi enviado."), 400
    except Exception as ex:      # noqa: BLE001 — banco fora: a pessoa sabe que não foi
        current_app.logger.exception("Nexus IA da carteira: a demanda não foi gravada")
        return jsonify(ok=False, erro=f"Não consegui gravar agora ({type(ex).__name__}). Nada foi enviado."), 500
    return jsonify(ok=True, demanda_id=d.get("demanda_id"),
                   aviso="Demanda enviada. Ela está em \u201cQue eu pedi\u201d, na Caixa de entrada, e quem recebeu é avisado no sininho.")


@bp_usinas.route("/ia/uso")
def ia_uso():
    """O painel de uso da Nexus IA no mês, para o administrador (18/11/2026): o gasto contra o teto, a projeção do mês e
    as contas por dia, por origem, por modo e por modelo, lidas do registro (`ia.uso`). Só contas: nem o texto das
    perguntas, nem quem perguntou."""
    from ...comando import ia as IA
    if not session.get("admin"):
        abort(403)
    from ...comando import diagnostico_noite as NT
    resp = current_app.make_response(render_template("comando/ia_uso.html", torre=_torre_usinas()[0],
                                                     tela=_torre_usinas()[1], u=IA.uso(current_app.config),
                                                     noites=NT.resumo(current_app.config)))
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp_usinas.route("/dossie-da-carteira.md")
def carteira_dossie_md():
    """O dossiê da carteira em texto (o que a IA lê), para o administrador conferir."""
    if not session.get("admin"):
        abort(403)
    resp = current_app.response_class(_carteira_ia()["texto"], mimetype="text/markdown")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp_usinas.route("/dossie-do-cliente.md")
def cliente_dossie_md():
    """O dossiê do cliente em Markdown, com as UFVs pontuadas (16/11/2026, Levi: "seria interessante o dossiê em .MD do
    cliente! Pontuando as UFVs!"; `nexus/comando/dossie_cliente.py`). O botão aparece no Comando › Usinas filtrado por um
    cliente. É de uso interno (traz as OS e o status dos chamados): a conta do cliente e o Modo cliente não baixam."""
    from ...auth import setor_telas
    from ...campo import visao
    from ...comando import dossie_cliente as DC
    if session.get("via") == "cliente" or setor_telas.em_modo_cliente():
        abort(403)
    cliente = (request.args.get("cliente") or "").strip()
    if not cliente or not any((l.get("cliente") or "") == cliente for l in _usinas_montadas()["linhas"]):
        abort(404)
    d = DC.montar(cliente, _carteira_ia(cliente), visao._agora())
    resp = current_app.response_class(d["texto"], mimetype="text/markdown; charset=utf-8")
    resp.headers["Content-Disposition"] = f'attachment; filename="{d["arquivo"]}"'
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
        # com o ?abrir=: a lista do motor só aparece na tela do Insights quando o link pede (19/11/2026)
        return ((i["titulo"] if i else f"Insight {oid} (a regra não aponta mais)"),
                na_raiz("/t/comando/insights") + f"?abrir={quote(oid)}#ins-{oid.replace(':', '-')}")
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
    # o pedido já preenchido, vindo do "Fazer" do diagnóstico do dia (14/11/2026, Levi: "E aí já vai preenchido
    # automático"): o setor, o título, o texto e a OS; quem envia confere, escolhe a pessoa e o tema
    a = request.args
    pre = {"setor": a.get("setor", "") if re.fullmatch(r"\d+(:[\w ]{1,30})?", a.get("setor") or "") else "",
           "titulo": " ".join((a.get("titulo") or "").split())[:D.TITULO_MAX],
           "descricao": (a.get("descricao") or "").strip()[:D.TEXTO_MAX],
           "os": a.get("os", "") if (a.get("os") or "").isdigit() else "",
           "tema": a.get("tema", "") if D.ID_TEMA.fullmatch(a.get("tema") or "") else ""}
    return render_template("comando/_conversa_janela.html", **_contexto(
        ob=ob, uid=usina_id, nome=nome, aba=aba, conv=_com_conversa(CV.atual().get(ob), _meu_hmac()), pre=pre,
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
from . import contratos_tela  # noqa: E402,F401
from . import gerencial_tela  # noqa: E402,F401
# o Nexus Insights com o portfólio no alto e a Nexus IA (19/11/2026)
from . import insights_tela  # noqa: E402,F401

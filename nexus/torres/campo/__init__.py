"""Torre Campo · App: a visão do Nexus sobre o trabalho de campo. Leia o CLAUDE.md desta pasta antes de mexer.

Levi, 05/10/2026: "quero parar de referenciar o Azure e ter uma visão nossa!". Nenhuma tela abre mais o painel do App
(que mora no Azure) nem aponta para ele: todas leem o banco do Nexus (API db_performace) — os livros que o próprio App
grava de hora em hora e o cadastro do Nexus. Aprovação e Triagem usam a cópia das regras do painel do App
(`nexus/campo/regras_app.py`); Central de atenção, PT, Rondas e Zeladoria são contas NOSSAS (`nexus/campo/visao.py`).
Rotas do dia fica no placeholder: o dado dela ainda não chega ao banco. Ordens de serviço, Imagens da ronda e Ranking
saíram em 08/10/2026 (Levi: "ordens de serviço e imagens da ronda e ranking são redundantes"); o endereço antigo leva
à Central.
"""
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from flask import Response, abort, current_app, make_response, redirect, render_template, request, session
from markupsafe import Markup, escape

import logging as _logging
_log_campo = _logging.getLogger("nexus.campo")
from werkzeug.datastructures import ImmutableMultiDict

from ...campo import aprovacao as campo_aprovacao
from ...campo import fonte_pg as campo_fonte
from ...campo import responsaveis as campo_resp
from ...campo import ranking_equipes as campo_ranking
from ...campo import observacao_responsavel as campo_obs
from ...campo import responsaveis_graficos as campo_graficos
from ...campo import triagem as campo_triagem
from ...campo import regras_app, visao
from ...campo import decisao_pt, pt_fracttal, ronda_avulsa, ronda_checklist, ronda_fotos
from ..modelo import Tela, Torre
from ...prefixo import na_raiz, raiz
from .aprovar_os import bp_aprovar_os, papel_da_sessao, pode_na_tela
from .assinatura import _login as _login_da_pt, _tela as _tela_da_pt, bp_assinatura

FONTE_APP = "Livros que o App de Campo grava no banco do Nexus + cadastro do Nexus"

TORRE = Torre(
    id="campo",
    nome="Campo · App",
    ordem=90,
    icone="hard-hat",
    descricao="Visão do Nexus sobre o campo: aprovação, PT, rondas, zeladoria e qualidade.",
    telas=[
        # A tela dos supervisores (Levi, 12/10/2026: "construa a visão dos responsáveis da usina!"): a 1ª do Campo
        Tela("responsaveis", "Visão do responsável",
             "Nas minhas usinas, onde focar primeiro e o que pode esperar?",
             "Gerencial, Confiabilidade, COS, tickets, rondas e PT, no banco do Nexus"),
        Tela("atencao", "Central de atenção",
             "O que no campo pede ação agora: usina sem ronda, PT parada, ronda sem OS?", FONTE_APP),
        Tela("aprovacao", "Aprovação de OS",
             "Que OS esperam a aprovação de cada supervisor de campo, qual dá para aprovar já e qual pede meu olho?",
             "Fila de verificação do Fracttal + notas do App no banco do Nexus"),
        # As Permissões de trabalho foram para Segurança · HSEQ > APR e PT em 09/10/2026 (Levi: "quero que esse visual e
        # caminho vá para APR e PT de Segurança · HSEQ"): o código continua aqui (`pagina_pt`, a aprovação, os PDFs), a
        # tela mora lá e o endereço antigo leva para lá.
        # Ordens de serviço, Ranking e Imagens da ronda saíram em 08/10/2026 (Levi: "ordens de serviço e imagens da
        # ronda e ranking são redundantes"): a qualidade do fechamento está na Aprovação e na Triagem, a comparação
        # por região e equipe no Painel das Rondas e as fotos no histórico da usina. O endereço antigo leva à Central
        # (TELAS_QUE_SAIRAM).
        Tela("rondas", "Rondas", "Que usina está sem ronda de campo há mais tempo?", FONTE_APP),
        Tela("zeladoria", "Zeladoria",
             "Que serviço de terceiro está parado, sem diária hoje ou com EPI pendente?", FONTE_APP),
        Tela("triagem", "Triagem de qualidade", "O que exige ação hoje na qualidade do fechamento?", FONTE_APP),
        # o placar do ciclo de pontos do App (Levi, 13/10/2026: "Cria uma seção de Ranking de Pontos no App de Campo!"):
        # quem calcula é o App, que publica no livro ranking_app_campo (visao.ranking_pontos). Não é o Ranking de 08/10
        Tela("ranking", "Ranking de pontos", "Quem lidera o ciclo de pontos do App neste mês, e por quê?",
             "Livro ranking_app_campo (o placar do ciclo do App) no banco do Nexus"),
        Tela("rotas", "Rotas do dia", "Qual a melhor ordem de visitas para cada equipe?",
             "Programação do PCM + localização das usinas"),
    ],
)

bp = TORRE.criar_blueprint(__name__)
# as rotas de quem assina a PT moram em /os/_nexus (o cookie do login do Fracttal do OS Creator só vale em /os)
bp.record_once(lambda estado: estado.app.register_blueprint(bp_assinatura))
# e o portão de quem aprova a OS também (Levi, 08/10/2026: "só o supervisor ou ADM consegue aprovar a OS logando pelo
# Fracttal"), pelo mesmo motivo: é ali que o servidor sabe quem entrou no Fracttal
bp.record_once(lambda estado: estado.app.register_blueprint(bp_aprovar_os))

# Ordens de serviço, Ranking e Imagens da ronda saíram do menu em 08/10/2026: quem guardou o endereço cai na Central. O
# /ranking voltou em 13/10/2026 com outra tela, o Ranking de pontos (o placar do ciclo do App)
TELAS_QUE_SAIRAM = ("os", "imagens")


def _tela_que_saiu():
    return redirect(na_raiz("/t/campo/atencao"))


for _id in TELAS_QUE_SAIRAM:
    bp.add_url_rule(f"/{_id}", f"saiu_{_id}", _tela_que_saiu)


TODOS = "*"
_BRT = timezone(timedelta(hours=-3))


# ── Os filtros da estrutura de O&M de 10/2026 ────────────────────────────────────────────────────────────────────
# O filtro "Supervisor" virou dois: a REGIÃO DE CAMPO (com o Supervisor de Campo dela: "Nordeste 02 · vaga") e o GESTOR DE
# CONTRATO (Supervisor PM, pela usina). Quem entra pelo Fracttal já vem filtrado (Levi, 06/10: "Quando um supervisor
# logar, o filtro supervisor já fica para a pessoa automaticamente, mas ela pode mudar o filtro se quiser"): o Supervisor
# de Campo na região dele, o Gestor de contrato nas usinas dele, o Coordenador em todas. "Todas" é uma escolha também:
# vai como "*" (e vence o padrão).
def _regiao_campo() -> str:
    v = request.args.get("regiao_campo")
    if v is None:
        p = papel_da_sessao()
        return (p.get("regioes") or [""])[0] if p.get("papel") == "supervisor_campo" else ""
    return "" if v == TODOS else v


def _gestor() -> str:
    v = request.args.get("gestor")
    if v is None:
        p = papel_da_sessao()
        return p.get("gestor", "") if p.get("papel") == "gestor" else ""
    return "" if v == TODOS else v


def _responsavel() -> str:
    """O Responsável O&M escolhido na Central (Levi, 12/10/2026: "Precisamos deixar filtrado por responsável"): o da
    ficha da usina. Sem padrão pelo login; "Todos" vai como "*"."""
    v = request.args.get("responsavel") or ""
    return "" if v == TODOS else v


def _do_papel(x, regiao_campo, gestor, responsavel="") -> bool:
    """A linha é da região de campo, do gestor e do responsável escolhidos. Linha sem região (equipe de fora da
    estrutura, PT sem usina ligada ao cadastro) conta como "Sem região de campo", sem gestor como "Sem gestor de contrato"
    e sem responsável como "Sem responsável O&M": é o que os cartões próprios mostram, e o clique neles tem de achar as
    mesmas linhas."""
    return ((not regiao_campo or (x.get("regiao_campo") or visao.SEM_REGIAO) == regiao_campo)
            and (not gestor or (x.get("gestor") or visao.SEM_GESTOR) == gestor)
            and (not responsavel or (x.get("responsavel") or visao.SEM_RESPONSAVEL) == responsavel))


def _opcoes_regiao(regioes, linhas, escolhida) -> list[tuple[str, str]]:
    """As regiões de campo do filtro, na ordem da estrutura, com o Supervisor de Campo ("Nordeste 02 · vaga"); depois
    "Sem região de campo", se alguma linha está nela, e a escolhida, se não for nenhuma das duas."""
    out = [(r["nome"], r["rotulo"]) for r in regioes or ()]
    nomes = {v for v, _ in out}
    if any((x.get("regiao_campo") or visao.SEM_REGIAO) == visao.SEM_REGIAO for x in linhas) or escolhida == visao.SEM_REGIAO:
        out.append((visao.SEM_REGIAO, visao.SEM_REGIAO))
        nomes.add(visao.SEM_REGIAO)
    if escolhida and escolhida not in nomes:
        out.append((escolhida, escolhida))
    return out


def _opcoes_gestor(linhas, escolhido) -> list[str]:
    """Os gestores de contrato do filtro (os das usinas das linhas), "Sem gestor de contrato" por último."""
    nomes = {x.get("gestor") for x in linhas if x.get("gestor")} | ({escolhido} if escolhido else set())
    return sorted(nomes - {visao.SEM_GESTOR}) + ([visao.SEM_GESTOR] if visao.SEM_GESTOR in nomes else [])


def _opcoes_responsavel(linhas, escolhido) -> list[str]:
    """Os Responsáveis O&M do filtro (os das usinas das linhas), "Sem responsável O&M" por último."""
    nomes = {x.get("responsavel") for x in linhas if x.get("responsavel")} | ({escolhido} if escolhido else set())
    return sorted(nomes - {visao.SEM_RESPONSAVEL}) + ([visao.SEM_RESPONSAVEL] if visao.SEM_RESPONSAVEL in nomes else [])


def _papeis(d, linhas, regiao_campo, gestor) -> dict:
    """O que os templates dos filtros e do aviso da estrutura precisam (`_filtros_papeis.html`, `_aviso_estrutura.html`)."""
    return {"regiao_campo": regiao_campo, "gestor": gestor, "estrutura_publicada": d.get("estrutura_publicada", True),
            "opcoes_regiao": _opcoes_regiao(d.get("regioes") or [], linhas, regiao_campo),
            "opcoes_gestor": _opcoes_gestor(linhas, gestor), "regioes_info": d.get("regioes") or [],
            "sem_regiao": visao.SEM_REGIAO, "sem_gestor": visao.SEM_GESTOR, "vaga": visao.VAGA}


def _url(**mudar) -> str:
    """O endereço desta tela com os filtros de agora, trocando só o que se pede (None tira o filtro)."""
    args = {k: v for k, v in request.args.items() if v}
    for k, v in mudar.items():
        if v in (None, ""):
            args.pop(k, None)
        else:
            args[k] = v
    return "?" + urlencode(args) if args else "?"


def _dia_curto(iso) -> str:
    s = str(iso or "")
    return f"{s[8:10]}/{s[5:7]}" if len(s) >= 10 else "—"


def _lido(leitura) -> str:
    return datetime.fromtimestamp(leitura.lido_em).strftime("%H:%M")


def _dias(validos, padrao) -> int:
    v = request.args.get("dias")
    return int(v) if v in {str(x) for x in validos} else padrao


def _coleta() -> str:
    """Até quando vão as notas que a fonte serve (o fechamento mais recente do livro do App), "05/10 14:25", no horário
    de Brasília: o App grava em UTC e a tela mostrava 01:23 para um fechamento das 22:23."""
    d = visao._dt(campo_fonte.coleta())
    return d.strftime("%d/%m %H:%M") if d else ""


def _comum(tela_id, leitura, **k):
    base = dict(torre=TORRE, tela=TORRE.tela(tela_id), leitura=leitura, d=leitura.dados, lido=_lido(leitura), url=_url,
                dia_curto=_dia_curto)
    return {**base, **k}


# ── Central de atenção (visão nossa) ─────────────────────────────────────────────────────────────────────────────
# Três visões (Levi, 05/10/2026): ronda e PT separadas, e as rondas pendentes antes do histórico.
# Só o que está PENDENTE (Levi, 05/10: "na parte de atenção quero só o que for pendente"): as rondas feitas, com o que
# ficou faltando nelas, moram na tela Rondas (aba Registros, filtro de pendência).
VISTAS = (("pendentes", "Rondas pendentes"), ("pt", "Permissões de trabalho"))
STATUS_DA_VISTA = {"pendentes": visao.PENDENTE, "pt": visao.PT_STATUS}


def _status(vista, x) -> str:
    return {"pendentes": x.get("tipo"),
            "pt": "parada" if x.get("parada") else "aguardando"}[vista]


def _idade_min(m) -> str:
    m = int(m or 0)
    if m >= 1440:
        return f"{m // 1440} d {(m % 1440) // 60} h"
    return f"{m // 60} h {m % 60} min" if m >= 60 else f"{m} min"


ORDEM_DOS_CARTOES = {"pendentes": lambda c: (-c["pendentes"], c["pct_feitas"] or 0, c["equipe"]),
                     "pt": lambda c: (-c["parada"], -c["pts"], c["equipe"])}
# Por região de campo e por gestor de contrato (estrutura de O&M de 10/2026; era "por supervisor", Levi, 08/10/2026):
# a mesma ordem dos cartões de equipe; "Sem região de campo" e "Sem gestor de contrato" sempre por último, num cartão
# próprio
ORDEM_DAS_REGIOES = {
    "pendentes": lambda s: (s["regiao"] == visao.SEM_REGIAO, -s["pendentes"], s["pct_feitas"] or 0, s["ordem"], s["regiao"]),
    "pt": lambda s: (s["regiao"] == visao.SEM_REGIAO, -s["parada"], -s["pts"], s["ordem"], s["regiao"])}
ORDEM_DOS_GESTORES = {
    "pendentes": lambda s: (s["gestor"] == visao.SEM_GESTOR, -s["pendentes"], s["pct_feitas"] or 0, s["gestor"]),
    "pt": lambda s: (s["gestor"] == visao.SEM_GESTOR, -s["parada"], -s["pts"], s["gestor"])}
# Por Responsável O&M (12/10/2026): a mesma ordem; "Sem responsável O&M" por último
ORDEM_DOS_RESPONSAVEIS = lambda s: (s["responsavel"] == visao.SEM_RESPONSAVEL, -s["pendentes"], s["pct_feitas"] or 0,  # noqa: E731
                                    s["responsavel"])


def _modo(equipe, historico=False) -> str:
    """As visões da Central e da tela de PT: cartões por equipe (o padrão), por região de campo (com a alternância para
    "por gestor de contrato") ou a tabela (a equipe escolhida no cartão abre a tabela dela). O endereço antigo
    `modo=supervisores` cai em "por região de campo"."""
    pedido = request.args.get("modo")
    if pedido == "tabela" or equipe or historico:
        return "tabela"
    if pedido in ("regioes", "supervisores"):
        return "regioes"
    return "gestores" if pedido == "gestores" else "equipes"


@bp.route("/atencao")
def atencao():
    """Três visões em cada aba (Levi, 05/10: "tem que ter a visão por equipe (CARDS grandes agrupados) e a visão da
    tabela!"; 08/10: "adicione mais um botão (por supervisor)"): cartões por equipe, por região de campo (com a
    alternância para por gestor de contrato: a estrutura de O&M de 10/2026) ou a tabela. Filtros da região do Brasil, da
    região de campo e do gestor; o cartão leva à tabela da equipe, da região ou do gestor."""
    dias = _dias((7, 14, 30), 14)
    leitura = visao.atencao(dias)
    d = leitura.dados
    ids = [v[0] for v in VISTAS]
    vista = request.args.get("vista") if request.args.get("vista") in ids else "pendentes"
    f, regiao, equipe = request.args.get("f", ""), request.args.get("regiao", ""), request.args.get("equipe", "")
    regiao_campo, gestor, responsavel = _regiao_campo(), _gestor(), _responsavel()
    modo = _modo(equipe)
    # Por Responsável O&M (Levi, 12/10/2026: "tem que mostrar usinas desse responsável que nunca tiveram ronda, rondas
    # pendentes e feitas! Ao clicar aparecerá um kanban com essas três colunas!"): os cartões dos responsáveis e, com um
    # escolhido (no cartão ou no filtro), o kanban das usinas dele. A tabela continua a um clique.
    if vista == "pendentes" and not equipe:
        if responsavel and request.args.get("modo") != "tabela":
            modo = "kanban"
        elif request.args.get("modo") == "responsaveis":
            modo = "responsaveis"
    q = request.args.get("q", "").strip().lower()
    campos = ("usina", "cidade", "equipe", "obs", "feito_por", "solicitante", "os", "numero", "tarefa")

    def filtra(lista):
        return [x for x in lista if (not regiao or x.get("regiao_br") == regiao)
                and (not equipe or x.get("equipe") == equipe)
                and _do_papel(x, regiao_campo, gestor, responsavel)
                and (not q or q in " ".join(str(x.get(c) or "") for c in campos).lower())]
    fontes = {"pendentes": filtra(d.get("pendentes") or []),
              "pt": com_quem_assina(filtra(d.get("pts") or [])) if vista == "pt" else filtra(d.get("pts") or [])}
    base = fontes[vista]
    contagem = {}
    for x in base:
        contagem[_status(vista, x)] = contagem.get(_status(vista, x), 0) + 1
    lista = [x for x in base if not f or _status(vista, x) == f]
    usinas_f = filtra(d.get("usinas") or [])
    cartoes = visao.por_equipe(usinas_f, fontes["pendentes"], [], fontes["pt"], d.get("times") or {})
    if vista == "pt":
        cartoes = [c for c in cartoes if c["pts"]]
    cartoes.sort(key=ORDEM_DOS_CARTOES[vista])
    # por região de campo: a soma dos cartões de equipe dela (já filtrados); por gestor: pelas usinas dele
    cartoes_reg = sorted(visao.por_regiao(cartoes, d.get("regioes") or []), key=ORDEM_DAS_REGIOES[vista])
    cartoes_gest = visao.por_gestor(*((usinas_f, fontes["pendentes"]) if vista == "pendentes" else ([], [])),
                                    fontes["pt"], d.get("times") or {})
    if vista == "pt":
        cartoes_gest = [c for c in cartoes_gest if c["pts"]]
    cartoes_gest.sort(key=ORDEM_DOS_GESTORES[vista])
    cartoes_resp = sorted(visao.por_responsavel(usinas_f, fontes["pendentes"]), key=ORDEM_DOS_RESPONSAVEIS)
    colunas = visao.kanban(usinas_f, fontes["pendentes"]) if modo == "kanban" else None
    return render_template("campo/atencao.html", **_comum(
        "atencao", leitura, dias=dias, vista=vista, vistas=[(v, n, len(fontes[v])) for v, n in VISTAS],
        status=STATUS_DA_VISTA[vista], status_de=lambda x: _status(vista, x), contagem=contagem, total=len(base),
        lista=lista, f=f, regiao=regiao, equipe=equipe, modo=modo, cartoes=cartoes, regioes=visao.REGIOES,
        cartoes_reg=cartoes_reg, cartoes_gest=cartoes_gest, situacoes=SITUACAO_PT,
        responsavel=responsavel, opcoes_responsavel=_opcoes_responsavel(d.get("usinas") or [], responsavel),
        sem_responsavel=visao.SEM_RESPONSAVEL, cartoes_resp=cartoes_resp, colunas=colunas,
        colunas_kanban=visao.COLUNAS_KANBAN,
        **_papeis(d, (d.get("usinas") or []) + (d.get("pts") or []), regiao_campo, gestor),
        q=request.args.get("q", ""), idade_min=_idade_min))


# ── Visão do responsável (12/10/2026) ───────────────────────────────────────────────────────────────────────────
# Levi: "Precisamos criar uma visão que os supervisores irão usar, uma visão que ele olha as usinas, as metas, os problemas,
# onde ele deve focar, no que ele deve deixar. No caso seria separado por responsável"; e, no protótipo aprovado: "aposte
# em um formato reduzido que quando eu expanda aparece mais informações / Separe a visão em dois blocos". A conta mora em
# nexus/campo/responsaveis.py (cada número da tela dona dele, com a régua de lá); aqui, os filtros, os cartões e os dois
# blocos (Performance e Acompanhamento), cada usina numa linha que abre o detalhe.
# o link de cada área leva à tela dona do número
TELA_DONA = {"meta": "torre_performance.moldura_gerencial", "disp": "torre_performance.moldura_disponibilidade",
             "ativos": "torre_engenharia.confiabilidade", "pt": "torre_hseq.apr_pt",
             "chamados": "torre_chamados.abrir_garantias", "extintores": "torre_hseq.extintores",
             # o bloco Manutenção (18/10/2026): as telas do PCM e a Aprovação de OS
             "gestao": "torre_pcm.gestao", "fora": "torre_pcm.fora", "quadro": "torre_pcm.quadro",
             "aprovacao": "torre_campo.aprovacao"}
LINKS_DO_BLOCO = {"perf": (("Visão gerencial", "meta"), ("Disponibilidade", "disp"), ("Confiabilidade", "ativos")),
                  "acomp": (("APR e PT", "pt"), ("Acompanhamento de chamados", "chamados"), ("Extintores", "extintores")),
                  "manut": (("Gestão PCM", "gestao"), ("Fora da programação", "fora"), ("Quadro da semana", "quadro"),
                            ("Aprovação de OS", "aprovacao"))}
# o limite das atrasadas de quem olha (Levi, 18/10/2026: "o supervisor decide, começa com 30 dias mas pode alterar";
# "no navegador dele"): um cookie de preferência de tela, não dado de negócio, então não vai ao banco
COOKIE_LIMITE = "nexus_resp_limite"
FAIXA_MAX = 6
CAMPOS_DA_BUSCA = ("usina", "cidade", "equipe", "cliente", "uf", "responsavel", "gestor")


def _responsavel_do_login(d) -> str:
    """O Responsável O&M que entrou pelo Fracttal, para o filtro já vir marcado nele (como o Supervisor de Campo e o
    Gestor nas outras telas do Campo); fica na sessão depois da 1ª conta. Quem não é responsável de nenhuma usina
    mobilizada (o coordenador, o administrador) abre nos cartões de todos."""
    if "responsavel_padrao" in session:
        return session["responsavel_padrao"] or ""
    pid = papel_da_sessao().get("pessoa_id")
    if not pid:
        u = session.get("usuario") or {}
        if not u.get("email"):
            return ""
        try:
            pid = visao.pessoa_do_login(u.get("email", ""), u.get("nome", ""))
        except Exception:       # noqa: BLE001 — sem cadastro: abre sem o filtro
            return ""
    nome = (d.get("responsaveis_por_pessoa") or {}).get(pid, "")
    session["responsavel_padrao"] = nome
    return nome


@bp.route("/responsaveis")
def responsaveis():
    """Os cartões dos responsáveis (o padrão de quem não é responsável) ou, com um escolhido (no cartão, no filtro, ou o
    próprio, pelo login), as usinas dele nos dois blocos: Performance (meta, PR, disponibilidade) e Acompanhamento
    (rondas, PT, chamados, extintores); em cada um, o que pede foco, o que pede acompanhamento e o que pode esperar.
    Filtros de responsável, cliente e busca; "Todos" vai como "*"."""
    leitura = campo_resp.visao_responsaveis()
    d = leitura.dados
    # o bloco Manutenção no limite de quem olha: o parâmetro (o campo do bloco) vence o cookie; sem os dois, 30
    pedido_limite = request.args.get("limite")
    limite = campo_resp.limite_do_pedido(pedido_limite if pedido_limite is not None
                                         else request.cookies.get(COOKIE_LIMITE))
    todas = campo_resp.com_manutencao(d.get("usinas") or [], limite)
    # o responsável que entrou pelo Fracttal vai direto para Onde focar, nas usinas dele, e não vê os cartões (Levi,
    # 12/10/2026: "caso a pessoa que logue seja algum desses responsáveis não vai aparecer por responsável, já vai direto
    # para Onde Focar!"); o filtro continua, para olhar as usinas de quem ele estiver cobrindo
    logado = "" if leitura.erro else _responsavel_do_login(d)
    pedido = request.args.get("responsavel")
    if pedido is None:
        responsavel = logado
    else:
        responsavel = "" if pedido == TODOS else pedido
    cliente = request.args.get("cliente", "")
    # a equipe (18/10/2026): o cartão do Ranking das equipes abre Onde focar só com as usinas dela; o nome exato do
    # cadastro, nunca um pedaço (a busca continua para isso)
    equipe = request.args.get("equipe", "")
    q = request.args.get("q", "").strip().lower()

    def passa(u):
        return ((not cliente or u.get("cliente") == cliente)
                and (not equipe or u.get("equipe") == equipe)
                and (not q or q in " ".join(str(u.get(c) or "") for c in CAMPOS_DA_BUSCA).lower()))
    base = [u for u in todas if passa(u)]
    usinas = [u for u in base if not responsavel or (u.get("responsavel") or visao.SEM_RESPONSAVEL) == responsavel]
    modo = request.args.get("modo")
    if logado:
        # o responsável logado nunca vê os cartões dos outros responsáveis; o Ranking das equipes e a Visão geral das
        # usinas dele, sim (18/10/2026)
        modo = modo if modo in ("ranking", "geral") else "foco"
    elif modo not in ("cartoes", "foco", "ranking", "geral"):
        modo = "foco" if responsavel else "cartoes"
    # a Visão geral (18/10/2026, Levi: "uma visão onde unifica todas as usinas"): todas as usinas do filtro numa lista
    # só, e o clique num bloco, nível ou número do resumo filtra (`filtro`, a condição daquele número no `soma`)
    filtro = campo_resp.filtro_geral(request.args.get("filtro")) if modo == "geral" else None
    lista_geral = campo_resp.filtrar_geral(usinas, filtro) if modo == "geral" else []
    contagem_geral = ({k: len(campo_resp.filtrar_geral(usinas, k)) for k in campo_resp.FILTROS_GERAL}
                      if modo == "geral" else {})
    # o Ranking das equipes (18/10/2026, Levi: "qual equipe cobrar"): a régua do ranking por região do App sobre as
    # usinas que passaram pelos filtros, no limite das atrasadas de quem olha (nexus/campo/ranking_equipes.py)
    ranking = (campo_ranking.cartoes(usinas, d.get("ranking_por_usina") or {}, d.get("tecnicos_por_equipe") or {})
               if modo == "ranking" else None)
    nomes = sorted({u.get("responsavel") or visao.SEM_RESPONSAVEL for u in todas} | ({responsavel} if responsavel else set()),
                   key=lambda n: (n == visao.SEM_RESPONSAVEL, n))
    # a faixa "Parada agora" (18/10/2026): as OS de parada abertas nas usinas DO FILTRO, a mais antiga primeiro
    faixa = sorted(((u, p) for u in usinas for p in u.get("paradas_abertas") or ()),
                   key=lambda up: (up[1]["_ini"], up[0]["usina"]))
    from ...campo import tarefas_os
    html = render_template("campo/responsaveis.html", **_comum(
        "responsaveis", leitura, responsavel=responsavel, cliente=cliente, q=request.args.get("q", ""), modo=modo,
        equipe=equipe, ranking=ranking, ranking_cor=campo_ranking.cor, sem_regiao=visao.SEM_REGIAO,
        filtro=filtro, filtros_geral=campo_resp.FILTROS_GERAL, lista_geral=lista_geral, contagem_geral=contagem_geral,
        responsavel_logado=logado, limite=limite, faixa=faixa, faixa_max=FAIXA_MAX, estado_os=tarefas_os.estado(),
        foto_os=campo_resp.foto_das_os(((d.get("info") or {}).get("manut") or {}).get("gerado_em"), visao._agora()),
        usinas=usinas, cartoes=campo_resp.por_responsavel(base), resumo=campo_resp.soma(responsavel or "Todos", usinas),
        blocos=[(b, nome, txt, campo_resp.bloco(usinas, b)) for b, nome, txt in campo_resp.BLOCOS],
        opcoes_responsavel=nomes, opcoes_cliente=sorted({u.get("cliente") for u in todas if u.get("cliente")}),
        sem_responsavel=visao.SEM_RESPONSAVEL, reguas=campo_resp.REGUAS, rotulo_area=campo_resp.ROTULO_AREA,
        tela_dona=TELA_DONA, links_do_bloco=LINKS_DO_BLOCO, info=d.get("info") or {}, erros=d.get("erros") or {},
        mes_id=d.get("mes_id"),
        limites={"meta_ok": campo_resp.META_NA_META, "meta_atencao": campo_resp.META_ATENCAO,
                 "disp_ok": campo_resp.DISP_OK, "disp_critico": campo_resp.DISP_CRITICO}))
    resp = make_response(html)
    if pedido_limite is not None:
        resp.set_cookie(COOKIE_LIMITE, str(limite), max_age=365 * 24 * 3600, path=raiz() or "/", samesite="Lax",
                        secure=bool(current_app.config.get("SESSION_COOKIE_SECURE")))
    return resp


# As janelas por cima da Visão do responsável (Levi, 12/10/2026: "precisamos mostrar para o supervisor de onde está
# vindo!"): um pedaço de página (sem a moldura do Nexus) que a tela carrega num <dialog> com o fundo desfocado. Meta: a
# tabela do dia a dia; PR: a geração com a linha do POA e a curva do PR; Disponibilidade: o mapa diário e as OS que
# formaram o valor. Cada uma lê o MESMO dado da tela dona, publicado no banco pela plataforma.
PAINEIS = {"meta": "Meta do mês", "pr": "PR do mês", "disp": "Disponibilidade do mês", "ativos": "Ativos falhando"}


@bp.route("/responsaveis/usina/<int:usina_id>/<painel>")
def responsaveis_painel(usina_id, painel):
    if painel not in PAINEIS:
        abort(404)
    return _resp_painel(usina_id, painel)


def _observacoes(u: dict, d: dict, aviso: str = "", erro: str = "", texto: str = "") -> dict:
    """A Observação do responsável na janela da Meta (Levi, 13/10/2026): as da usina, a mais nova em cima, e se quem
    está na tela pode escrever (Responsável O&M de alguma usina, pelo login do Fracttal; quem cobre outro também)."""
    logado = _responsavel_do_login(d)
    usuario = session.get("usuario") or {}
    try:
        lista, erro_leitura = campo_obs.da_usina(u["usina_id"]), ""
    except Exception as e:      # noqa: BLE001 — banco fora: a janela diz, o resto segue
        lista, erro_leitura = [], f"Não consegui ler as observações no banco ({type(e).__name__})"
    pode = bool(logado and usuario.get("email"))
    return {"lista": lista, "pode": pode, "quem": usuario.get("nome") or logado, "aviso": aviso,
            "erro": erro or erro_leitura, "texto": texto,
            "cobrindo": u.get("responsavel") if pode and visao._norm_nome(logado) != visao._norm_nome(u.get("responsavel"))
            else ""}


@bp.route("/responsaveis/usina/<int:usina_id>/observacao", methods=["POST"])
def responsaveis_observacao(usina_id):
    """Grava a Observação do responsável e devolve a janela da Meta de novo (com a observação nova, ou com o motivo da
    recusa e o texto digitado). Só da própria página (a régua da moldura: pedido de outro site é 403)."""
    from ..moldura import _de_outro_site
    if _de_outro_site():
        abort(403)
    leitura = campo_resp.visao_responsaveis()
    u = next((x for x in (leitura.dados or {}).get("usinas") or [] if x["usina_id"] == usina_id), None)
    if u is None:
        abort(404)
    hoje = visao._agora().date()
    texto = request.form.get("texto") or ""
    try:
        campo_obs.escrever(usina_id, texto, session.get("usuario"), _responsavel_do_login(leitura.dados or {}),
                           u.get("responsavel") or "", hoje.year * 100 + hoje.month)
    except campo_obs.Recusada as e:
        return _resp_painel(usina_id, "meta", obs_erro=str(e), obs_texto=texto)
    except Exception as e:      # noqa: BLE001 — banco fora: a janela diz, o texto digitado não se perde
        return _resp_painel(usina_id, "meta", obs_texto=texto,
                            obs_erro=f"Não consegui gravar no banco ({type(e).__name__}). Tente de novo em instantes")
    return _resp_painel(usina_id, "meta", obs_aviso="Observação salva")


def _resp_painel(usina_id, painel, obs_aviso="", obs_erro="", obs_texto=""):
    """A janela da usina. O que quebrar ao montar vira a mensagem dentro dela, com o tipo e o texto do erro, e vai ao
    log da máquina; nunca um 500 cru (13/10/2026: a janela da Meta dava "HTTP 500" em todas as usinas no servidor
    recém-subido, e a mesma versão abria no PC: sem o texto do erro não havia como saber o que lá era diferente)."""
    from werkzeug.exceptions import HTTPException
    try:
        return _resp_painel_montar(usina_id, painel, obs_aviso, obs_erro, obs_texto)
    except HTTPException:
        raise
    except Exception as e:      # noqa: BLE001 — a janela diz o erro; a Visão segue
        _log_campo.exception("Visão do responsável: a janela %s da usina %s não montou", painel, usina_id)
        return (f'<header class="cr-jan-cab"><div><p class="gc-eyebrow">{escape(PAINEIS.get(painel, ""))}</p>'
                f'<h2>Não consegui montar esta janela</h2></div></header>'
                f'<div class="cn-erro" role="alert"><b>{escape(type(e).__name__)}: {escape(str(e)[:200])}.</b> Feche e '
                f'abra de novo; se repetir, mande este texto a quem cuida do Nexus.</div>')


def _resp_painel_montar(usina_id, painel, obs_aviso="", obs_erro="", obs_texto=""):
    leitura = campo_resp.visao_responsaveis()
    u = next((x for x in (leitura.dados or {}).get("usinas") or [] if x["usina_id"] == usina_id), None)
    if u is None:
        abort(404)
    import calendar
    hoje = visao._agora().date()
    dias_mes = calendar.monthrange(hoje.year, hoje.month)[1]
    ctx = {"u": u, "painel": painel, "titulo": PAINEIS[painel], "mes_txt": hoje.strftime("%m/%Y"), "erro": "",
           "limites": {"meta_ok": campo_resp.META_NA_META, "meta_atencao": campo_resp.META_ATENCAO,
                       "disp_ok": campo_resp.DISP_OK, "disp_critico": campo_resp.DISP_CRITICO}}
    try:
        nomes = campo_resp.Nomes(visao._Base())
        if painel in ("meta", "pr"):
            serie = campo_resp.serie_diaria(usina_id, hoje.year * 100 + hoje.month, nomes)
            # a Meta leva o POA e a disponibilidade de cada dia (Levi, 13/10/2026): o mapa diário da Disponibilidade
            disp = campo_resp.disp_diaria(usina_id, hoje.strftime("%Y-%m"), nomes) if painel == "meta" else None
            ctx.update(serie=serie, tabela=campo_resp.tabela_meta(serie, disp, (u.get("disp") or {}).get("disp")),
                       graf_ger=campo_graficos.geracao(serie["dias"], dias_mes) if serie["dias"] else None,
                       graf_pr=campo_graficos.pr(serie["dias"], dias_mes) if serie["dias"] else None)
        elif painel == "disp":
            ctx.update(disp=campo_resp.disp_diaria(usina_id, hoje.strftime("%Y-%m"), nomes),
                       oss=campo_resp.os_disponibilidade(usina_id, hoje.strftime("%Y-%m"), nomes))
        else:       # os ativos falhando da Engenharia › Confiabilidade (Levi, 13/10/2026)
            ctx.update(at=campo_resp.ativos_da_usina(usina_id, hoje),
                       tela_confiabilidade="torre_engenharia.confiabilidade")
    except Exception as e:      # noqa: BLE001 — banco fora: a janela diz, a tela segue
        _log_campo.exception("Visão do responsável: a leitura da janela %s da usina %s falhou", painel, usina_id)
        ctx["erro"] = f"Não consegui ler o banco do Nexus ({type(e).__name__}: {str(e)[:160]})"
    if painel == "meta":
        ctx["obs"] = _observacoes(u, leitura.dados or {}, obs_aviso, obs_erro, obs_texto)
    return render_template("campo/_resp_painel.html", **ctx, duracao=_idade_min)


@bp.route("/responsaveis/pt/<numero>")
def responsaveis_pt(numero):
    """A PT por cima da Visão do responsável (Levi, 12/10/2026: "não tirar a pessoa da tela pois ela vai ter que voltar
    para ver mais usinas, se pudesse aparecer sobreposto para o supervisor aprovar seria perfeito!"): a mesma linha da
    PT e a mesma decisão da tela da PT (`pt_aprovar`), assinada com o login do Fracttal; o `volta` traz de volta à Visão
    do responsável, com os filtros dela (o portão só aceita /t/campo/ e /t/hseq/)."""
    ativo = request.args.get("ativo")
    volta = request.args.get("volta") or ""
    volta = volta if volta.startswith("/t/campo/") and not volta.startswith("//") else ""
    leitura = visao.pts()
    p = visao.pt(numero, ativo) if not leitura.erro else None
    nexus, erro_nexus, recusa_app = None, "", ""
    if p:
        try:
            nexus = decisao_pt.da_pt(p["numero"], p.get("codigo") or "")
        except Exception as e:      # noqa: BLE001 — sem o livro de decisões, a janela abre e diz
            erro_nexus = f"Não consegui ler as decisões do Nexus ({type(e).__name__})"
        if nexus and decisao_pt.recusada_pelo_app(p, [nexus]):
            recusa_app, nexus = p.get("nexus_recusa") or "o App não aplicou a decisão", None
    return render_template("campo/_resp_pt.html", p=p, numero=numero, ativo=ativo, volta=volta, erro=leitura.erro,
                           nexus=nexus, erro_nexus=erro_nexus, recusa_app=recusa_app, situacoes=SITUACAO_PT,
                           quem_assina=decisao_pt.aprovadores(p)["texto"] if p else "",
                           entrar=_login_da_pt(p["numero"], p.get("codigo") or "") if p else "",
                           idade_min=_idade_min, decisoes=decisao_pt.DECISOES, quando=visao._dt)


# ── Permissões de trabalho (visão nossa) ─────────────────────────────────────────────────────────────────────────
SITUACAO_PT = {"aguardando": ("Aguardando", "alerta"), "de_acordo": ("De acordo", "ok"),
               "negada": ("Não autorizada", "critico"), "vencida": ("Vencida", "neutro")}


# sem o prefixo, como o roteamento o entende; todo redirecionamento a ela passa pelo na_raiz (debaixo do /nexus, o
# endereço cru levava à plataforma de Performance; porta única, 10/10/2026)
TELA_PT = "/t/hseq/apr-pt"


def _onde_pt():
    """A torre e a tela onde a PT mora desde 09/10/2026: Segurança · HSEQ > APR e PT (import tardio: a torre HSEQ
    importa esta)."""
    from ..hseq import TORRE as HSEQ
    return HSEQ, HSEQ.tela("apr-pt")


def com_quem_assina(pts: list) -> list:
    """Põe em cada PT esperando o texto de quem pode dar o De acordo (`decisao_pt.aprovadores`), com um cadastro só."""
    if not pts:
        return pts
    try:
        b = visao._Base()
        for p in pts:
            p["quem_assina"] = decisao_pt.aprovadores(p, b)["texto"]
    except Exception:       # noqa: BLE001 — sem o cadastro, o detalhe só não diz quem assina
        pass
    return pts


@bp.route("/pt")
def pt():
    """O endereço antigo das Permissões de trabalho: a tela foi para Segurança · HSEQ > APR e PT (09/10/2026)."""
    return redirect(na_raiz(TELA_PT) + ("?" + request.query_string.decode() if request.query_string else ""))


def pagina_pt():
    """Permissões de trabalho e Análise Preliminar de Risco (em Segurança · HSEQ desde 09/10/2026). Duas abas (Levi,
    05/10): as PT esperando o De acordo (por equipe, por região de campo ou por gestor de contrato, ou em tabela, a linha
    abre o detalhe com a assinatura do técnico e a decisão) e o histórico das decididas, com o PDF da PT e o da APR em
    colunas (Levi, 09/10). Filtros de região de campo e de gestor; a equipe vem do cartão."""
    leitura = visao.pts()
    d = leitura.dados
    aba = "historico" if request.args.get("aba") == "historico" else "esperando"
    regiao_campo, gestor, equipe = _regiao_campo(), _gestor(), request.args.get("equipe", "")
    sit, q = request.args.get("sit", ""), request.args.get("q", "").strip().lower()
    modo = _modo(equipe, historico=aba == "historico")
    dias = _dias((7, 30, 90), 30)
    piso = visao._agora() - timedelta(days=dias)
    campos = ("os", "numero", "tarefa", "usina", "ativo", "codigo", "equipe", "solicitante", "decidida_por")

    def filtra(lista):
        return [p for p in lista if _do_papel(p, regiao_campo, gestor)
                and (not equipe or p.get("equipe") == equipe)
                and (not q or q in " ".join(str(p.get(c) or "") for c in campos).lower())]
    aguardando = com_quem_assina(filtra(d.get("aguardando") or []))
    # a aba Esperando é a MESMA da Central de atenção > Permissões de trabalho (Levi, 05/10)
    f = request.args.get("f", "") if request.args.get("f") in visao.PT_STATUS else ""
    regiao = request.args.get("regiao", "")
    if regiao:
        aguardando = [p for p in aguardando if p.get("regiao_br") == regiao]
    contagem_pt = {s: sum(1 for p in aguardando if _status("pt", p) == s) for s in visao.PT_STATUS}
    cartoes_pt = sorted((c for c in visao.por_equipe([], [], [], aguardando, d.get("times") or {}) if c["pts"]),
                        key=ORDEM_DOS_CARTOES["pt"])
    cartoes_reg = sorted(visao.por_regiao(cartoes_pt, d.get("regioes") or []), key=ORDEM_DAS_REGIOES["pt"])
    cartoes_gest = sorted((c for c in visao.por_gestor([], [], aguardando, d.get("times") or {}) if c["pts"]),
                          key=ORDEM_DOS_GESTORES["pt"])
    lista_pt = [p for p in aguardando if not f or _status("pt", p) == f]
    historico = [p for p in filtra(d.get("historico") or []) if (p.get("criada") or piso) >= piso]
    contagem = {}
    for p in historico:
        contagem[p["situacao"]] = contagem.get(p["situacao"], 0) + 1
    historico = [p for p in historico if not sit or p.get("situacao") == sit]
    todas = (d.get("aguardando") or []) + (d.get("historico") or [])
    torre, tela = _onde_pt()
    return render_template("campo/pt.html", **_comum(
        "pt", leitura, torre=torre, tela=tela, titulo="Permissões de trabalho e Análise Preliminar de Risco",
        aviso=session.pop("pt_aviso", ""), gravada=session.pop("pt_gravada", ""),
        aba=aba, modo=modo, aguardando=aguardando, historico=historico, contagem_hist=contagem, sit=sit,
        dias=dias, equipe=equipe, q=request.args.get("q", ""), situacoes=SITUACAO_PT,
        idade_min=_idade_min, cartoes=cartoes_pt, lista=lista_pt, contagem=contagem_pt, total=len(aguardando), f=f,
        cartoes_reg=cartoes_reg, cartoes_gest=cartoes_gest,
        status=visao.PT_STATUS, regiao=regiao, regioes=visao.REGIOES, **_papeis(d, todas, regiao_campo, gestor)))


@bp.route("/pt/<numero>/pdf")
def pt_pdf(numero):
    """O PDF da PT como o App anexou no Fracttal no De acordo, com a assinatura do técnico e a de quem aceitou (Levi,
    05/10: "exportar o anexo do PDF ... conforme estava no Azure"). O Nexus baixa e entrega: o link do Fracttal não
    sai para o navegador."""
    p = visao.pt(numero)
    # o aviso volta para a linha de onde se pediu o PDF (a PT de mais de uma linha, sem ela, só deixa escolher)
    ativo = request.args.get("ativo")
    try:
        if not p or not p.get("os"):
            raise pt_fracttal.SemArquivo(f"{numero} não está no livro do App")
        corpo = pt_fracttal.pdf(p["os"], p["numero"])
    except pt_fracttal.SemArquivo as e:
        session["pt_aviso"] = f"Sem PDF: {e}."
        return redirect(url_for_pt(numero, ativo))
    except Exception as e:      # noqa: BLE001 — Fracttal fora ou recusando
        session["pt_aviso"] = f"Não consegui buscar o PDF no Fracttal ({type(e).__name__}). Tente de novo em instantes."
        return redirect(url_for_pt(numero, ativo))
    return Response(corpo, mimetype="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{p["numero"]}.pdf"'})


@bp.route("/pt/<numero>/apr.pdf")
def pt_apr_pdf(numero):
    """O PDF da APR que o App anexou na tarefa do Fracttal (desde a v251), ao lado do PDF da PT (Levi, 09/10/2026:
    "terá como baixar o relatório de ambas individualmente"). O Nexus baixa e entrega: o link do Fracttal não sai."""
    p = visao.pt(numero)
    try:
        if not p or not p.get("os"):
            raise pt_fracttal.SemArquivo(f"{numero} não está no livro do App")
        corpo, nome = pt_fracttal.apr_pdf(p["os"], p.get("criada"))
    except pt_fracttal.SemArquivo as e:
        session["pt_aviso"] = f"Sem a APR: {e}."
        return redirect(request.referrer if (request.referrer or "").startswith(request.host_url) else na_raiz(TELA_PT))
    except Exception as e:      # noqa: BLE001 — Fracttal fora ou recusando
        session["pt_aviso"] = f"Não consegui buscar a APR no Fracttal ({type(e).__name__}). Tente de novo em instantes."
        return redirect(request.referrer if (request.referrer or "").startswith(request.host_url) else na_raiz(TELA_PT))
    arq = re.sub(r"[^A-Za-z0-9._ -]+", "", nome).strip().replace(" ", "-") or f"APR-{numero}"
    return Response(corpo, mimetype="application/pdf", headers={"Content-Disposition": f'attachment; filename="{arq}.pdf"'})


def url_for_pt(numero, codigo=None) -> str:
    """A tela da PT; com `codigo` (o código do ativo), a mesma linha (`assinatura._tela`)."""
    return _tela_da_pt(numero, codigo)


@bp.route("/pt/<numero>")
def pt_aprovar(numero):
    """A aprovação da PT no Nexus: uma linha da PT e a decisão dela, assinada com o login do Fracttal do OS Creator. A
    PT de mais de um ativo tem uma linha (e uma decisão) por ativo, como no App: `?ativo=<código>` escolhe qual (decisão
    4 do Levi, 11/10/2026), e a tela lista as outras linhas. Sem ele, ou com um código que a PT não tem, a PT de uma
    linha abre a dela e a de mais de uma só lista os equipamentos para escolher: abrir a 1ª calada punha o código dela
    no formulário, e a decisão caía no equipamento errado (revisão adversarial de 11/10/2026)."""
    leitura = visao.pts()
    ativo = request.args.get("ativo")
    linhas = visao.pt_linhas(numero) if not leitura.erro else []
    p = visao.pt(numero, ativo) if linhas and ativo is not None else None
    if p is None and len(linhas) == 1:
        p = linhas[0]                       # uma linha só: não há o que escolher
    escolher = bool(linhas) and p is None
    nexus, erro_nexus = None, ""
    if p:
        try:
            nexus = decisao_pt.da_pt(p["numero"], p.get("codigo") or "")
        except Exception as e:      # noqa: BLE001 — sem o livro de decisões, a tela abre e diz
            erro_nexus = f"Não consegui ler as decisões do Nexus ({type(e).__name__})"
    # o App recusou a última decisão do Nexus nesta linha: a tela diz por quê e abre o formulário de novo (v257)
    recusa_app = ""
    if p and nexus and decisao_pt.recusada_pelo_app(p, [nexus]):
        recusa_app, nexus = p.get("nexus_recusa") or "o App não aplicou a decisão", None
    torre, tela = _onde_pt()
    return render_template("campo/pt_aprovar.html", **_comum(
        "pt", leitura, torre=torre, tela=tela, p=p, linhas=linhas, escolher=escolher, ativo=ativo, numero=numero,
        nexus=nexus, erro_nexus=erro_nexus, recusa_app=recusa_app, situacoes=SITUACAO_PT,
        quem_assina=decisao_pt.aprovadores(p)["texto"] if p else "",
        # o "entre com o seu login do Fracttal" da decisão volta para ESTA linha (`assinatura._login`)
        entrar=_login_da_pt(p["numero"], p.get("codigo") or "") if p else "",
        idade_min=_idade_min, decisoes=decisao_pt.DECISOES, aviso=session.pop("pt_aviso", ""),
        gravada=request.args.get("gravada") == "1", quando=visao._dt))


# ── Rondas e Zeladoria (visão nossa) ─────────────────────────────────────────────────────────────────────────────
# Levi, 08/10/2026: a aba Cobertura saiu ("já não faz sentido tendo o histórico da usina") e entrou a "Sem ronda"; o
# Painel é a "visão a mais, dashboards que mostre de fato" quem está melhor. Os botões de filtro da Sujidade saíram:
# "se a pessoa quiser ordenar ela clica na coluna que ordena e já era!" (o clique no cabeçalho, `_ordenar.html`).
ABAS_RONDAS = (("registros", "Registros"), ("painel", "Painel"), ("sujidade", "Sujidade e vegetação"),
               ("sem", "Sem ronda"), ("trackers", "Trackers"), ("quem", "Quem ronda"))
# a aba Sem ronda: sem ronda no período (o padrão), há 7 dias ou mais, ou nunca em todo o registro
FILTROS_SEM_RONDA = ("sem", "atrasadas", "nunca")
LIMITE_LINHAS = 300


def _duracao(m) -> str:
    """27 min, 1h04: como o painel de rondas mostrava (Levi, 05/10)."""
    if m is None:
        return "—"
    return f"{m // 60}h{m % 60:02d}" if m >= 60 else f"{m} min"


def _iniciais(nome) -> str:
    partes = [p for p in str(nome or "").split() if p]
    return (partes[0][0] + (partes[-1][0] if len(partes) > 1 else "")).upper() if partes else "?"


def _ordem_do_nome(nome) -> str:
    """Ordem alfabética sem acento e sem caixa ("Águas" junto de "Aguas", não no fim da lista)."""
    import unicodedata
    return unicodedata.normalize("NFKD", str(nome or "")).encode("ascii", "ignore").decode().lower()


def _ordem_sem_ronda(c):
    """A mais esquecida primeiro: há mais dias sem ronda (nunca = 999); no empate, a última OS mais antiga (ou nenhuma)."""
    return (-c["dias"], (c.get("ultima_os") or {}).get("data") or "", c["usina"])


@bp.route("/rondas")
def rondas():
    """Cobertura, duração e qualidade da ronda (Levi, 05/10: o estilo do painel de rondas, no tema do Nexus): sete
    indicadores do período e seis abas (Registros, Painel, Sujidade e vegetação, Sem ronda, Trackers, Quem ronda).
    Filtros de região do Brasil, cliente, usina, Responsável O&M, equipe, região de campo e gestor de contrato;
    Exportar CSV dos registros."""
    dias = _dias((7, 14, 30), 30)
    leitura = visao.rondas()
    d = leitura.dados
    regiao, regiao_campo, gestor = request.args.get("regiao", ""), _regiao_campo(), _gestor()
    # cliente pelo cadastro (Levi, 05/10: "filtro por cliente e a cobertura das rondas das UFVs do cliente. Essas usinas
    # tem que bater com as mesmas do registro mestre"): filtra as rondas E a base da cobertura
    cliente, cluster, equipe = request.args.get("cliente", ""), request.args.get("cluster", ""), request.args.get("equipe", "")
    # usina, Responsável O&M e equipe na barra (Levi, 13/10/2026: "deve dar para filtrar cliente, usina, responsável e
    # equipe!"). O responsável é o da ficha da usina (`usinas.responsavel_om_id`), o mesmo da Central; a usina vai pelo
    # id do cadastro (o nome do livro do App não é chave)
    responsavel, usina = _responsavel(), request.args.get("usina", "")
    pedida = "sem" if request.args.get("aba") == "cobertura" else request.args.get("aba")     # endereço antigo
    aba = pedida if pedida in dict(ABAS_RONDAS) else "registros"
    dur, q = request.args.get("dur", ""), request.args.get("q", "").strip().lower()
    pend = request.args.get("pend", "") if request.args.get("pend") in visao.FEITA else ""
    # os indicadores filtram a tabela (Levi, 05/10: "quero que esses botões sejam clicáveis e filtre a tabela")
    ind = request.args.get("ind", "") if request.args.get("ind") in ("hoje", "qualidade", "duracao") else ""
    cob = request.args.get("cob", "") if request.args.get("cob") in FILTROS_SEM_RONDA else ""
    # Quem ronda em blocos (o padrão) ou em tabela (Levi, 08/10: "traga também uma visão em blocos para que fique mais
    # visual para os supervisores!")
    ver = "tabela" if request.args.get("ver") == "tabela" else "blocos"

    def filtra(lista, sem_usina=False):
        return [x for x in lista if (not regiao or x.get("regiao_br") == regiao)
                and _do_papel(x, regiao_campo, gestor, responsavel)
                and (not cliente or x.get("cliente") == cliente)
                and (not equipe or x.get("equipe") == equipe)
                and (sem_usina or not usina or str(x.get("usina_id") or "") == usina)]
    cobertura = filtra(d.get("cobertura") or [])
    painel = visao.painel_rondas(filtra(d.get("todas") or []), cobertura, dias, d.get("hoje") or visao._agora().date().isoformat())
    lim = painel["kpi"]["dur_min"]
    registros = [r for r in painel["periodo"]
                 if (dur != "curta" or (r["dur_min"] is not None and r["dur_min"] < lim))
                 and (dur != "longa" or (r["dur_min"] or 0) > 120)
                 and (not pend or r["pendencia"] == pend)
                 and (ind != "hoje" or r["data"] == painel["hoje"])
                 and (ind != "qualidade" or (r["nota"] is not None and r["nota"] < painel["kpi"]["limite"]))
                 and (not q or q in " ".join(str(r.get(c) or "") for c in ("tecnico", "usina", "equipe", "os")).lower())]
    if ind == "duracao":
        registros.sort(key=lambda r: -(r["dur_min"] if r["dur_min"] is not None else -1))
    # a aba Sem ronda (Levi, 08/10: "troque por uma tabela chamada 'Sem ronda' que mostrará usina, equipe, técnicos,
    # supervisor e última OS feita na usina"): sem ronda no período (padrão), há 7 dias ou mais, ou nunca
    na_aba_sem = {"atrasadas": lambda c: c["dias"] >= visao.DIAS_SEM_RONDA_ALERTA,
                  "nunca": lambda c: c.get("nunca", c["dias"] >= 999)}.get(cob, lambda c: c["dias"] >= dias)
    sem_ronda = sorted((c for c in cobertura if na_aba_sem(c)), key=_ordem_sem_ronda)
    n_sem = {"sem": sum(1 for c in cobertura if c["dias"] >= dias),
             "atrasadas": sum(1 for c in cobertura if c["dias"] >= visao.DIAS_SEM_RONDA_ALERTA),
             "nunca": painel["kpi"]["nunca"]}
    if request.args.get("csv") == "1":
        import csv
        import io
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["Data", "Técnico", "Usina", "Equipe", "Estado", "Região", "Tipo", "Início", "Fim", "Duração (min)",
                    "Qualidade (%)", "Veredito", "Trackers apontados", "Trackers respondidos", "OS", "Pendências",
                    "Região de campo", "Supervisor de campo", "Gestor de contrato"])
        # (a coluna Pendências do CSV leva tudo o que o App anotou, inclusive a ronda longa pendente; as colunas da
        # estrutura de O&M de 10/2026 entraram no fim, para não mudar a posição das de antes)
        for r in registros:
            w.writerow([r["data"], r["tecnico"], r["usina"], r["equipe"], r["uf"], r["regiao_br"], r["tipo"], r["ini_hm"],
                        r["fim_hm"], r["dur_min"] if r["dur_min"] is not None else "", r["nota"] if r["nota"] is not None else "",
                        r["veredito"][1], r["trk_apontados"], r["trk_respondidos"], r["os"] or "", r["falhas"],
                        r.get("regiao_campo") or "", r.get("supervisor_campo") or "", r.get("gestor") or ""])
        return Response("\ufeff" + buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="rondas-{dias}d.csv"'})
    clientes = sorted({c.get("cliente") for c in d.get("cobertura") or [] if c.get("cliente")})
    # as usinas do filtro: as mobilizadas (e as que tiveram ronda) que passam pelos OUTROS filtros — escolher o cliente
    # ou o responsável encurta a lista de usinas; a escolhida fica sempre
    nomes_usina = {}
    for x in filtra(d.get("cobertura") or [], sem_usina=True) + filtra(d.get("todas") or [], sem_usina=True):
        if x.get("usina_id") and x.get("usina"):
            nomes_usina.setdefault(str(x["usina_id"]), x["usina"])
    if usina and usina not in nomes_usina:
        uid_ = next((x for x in (d.get("cobertura") or []) + (d.get("todas") or []) if str(x.get("usina_id") or "") == usina), None)
        nomes_usina[usina] = (uid_ or {}).get("usina") or f"usina {usina}"
    opcoes_usina = sorted(nomes_usina.items(), key=lambda kv: _ordem_do_nome(kv[1]))
    equipes = sorted({x.get("equipe") for x in (d.get("cobertura") or []) + (d.get("todas") or []) if x.get("equipe")}
                     | ({equipe} if equipe else set()), key=_ordem_do_nome)
    cluster_aberto = next((c for c in painel["clusters"] if c["cluster"] == cluster), None) if cluster else None
    suj, suj_estado = None, None
    if aba == "sujidade":
        # as respostas vêm das OS de ronda no Fracttal: as aprovadas, relidas em segundo plano, e as em verificação,
        # que já estão na fila da Aprovação de OS (nunca espera o Fracttal)
        campo_aprovacao._pedir_releitura()
        ronda_checklist.pedir_releitura()
        # + a validação por foto (Levi, 08/10/2026): a leitura da usina naquele dia, no lugar da ronda do mesmo dia
        suj = visao.sujidade_vegetacao(filtra(d.get("todas") or []), cobertura, ronda_checklist.respostas(), dias,
                                       d.get("hoje") or visao._agora().date().isoformat(),
                                       filtra(d.get("validacoes") or []))
        suj_estado = ronda_checklist.estado()
    comparativos = visao.comparativos(painel["periodo"], cobertura) if aba == "painel" else None
    return render_template("campo/rondas.html", **_comum(
        "rondas", leitura, dias=dias, regiao=regiao, aba=aba, abas=ABAS_RONDAS, dur=dur,
        pend=pend, pendencias={k: v for k, v in visao.FEITA.items() if k != "ok"}, ind=ind, cob=cob,
        n_pend={k: sum(1 for r in painel["periodo"] if r["pendencia"] == k) for k in ("sem_os", "incompleta")},
        q=request.args.get("q", ""), k=painel["kpi"], registros=registros, limite=LIMITE_LINHAS, cobertura=cobertura,
        sem_ronda=sem_ronda, n_sem=n_sem, registro_desde=d.get("registro_desde") or "",
        trackers=painel["trackers"], quem=painel["quem"], regioes=visao.REGIOES,
        **_papeis(d, d.get("cobertura") or [], regiao_campo, gestor),
        duracao=_duracao, iniciais=_iniciais, suj=suj, suj_estado=suj_estado, equipe=equipe, ver=ver,
        cliente=cliente, clientes=clientes, clusters=painel["clusters"], cluster_aberto=cluster_aberto,
        responsavel=responsavel, opcoes_responsavel=_opcoes_responsavel(d.get("cobertura") or [], responsavel),
        usina=usina, opcoes_usina=opcoes_usina, equipes=equipes,
        comparativos=comparativos, dimensoes=visao.DIMENSOES, base_pequena=visao.BASE_PEQUENA,
        filtro_da_dimensao={"regiao_br": "regiao", "equipe": "equipe", "cliente": "cliente",
                            "regiao_campo": "regiao_campo", "gestor": "gestor"},
        explicacao_avulsa=ronda_avulsa.EXPLICACAO, explicacao_validada=visao.VALIDADA_EXPLICACAO))


@bp.route("/rondas/usina/<int:usina_id>")
def rondas_usina(usina_id):
    """O histórico de rondas de uma usina, com data, sujidade e vegetação (Levi, 05/10: "quando clicarmos no nome da
    usina já aparece o histórico de rondas ... essas informações são importantes!")."""
    leitura = visao.rondas()
    d = leitura.dados or {}
    ronda_checklist.pedir_releitura()
    campo_aprovacao._pedir_releitura()
    hist = visao.historico_usina(d.get("todas") or [], ronda_checklist.respostas(), usina_id, d.get("validacoes") or [])
    usina = next((c for c in d.get("cobertura") or [] if c["usina_id"] == usina_id), None) or (hist[0] if hist else None)
    # a validação por foto (08/10/2026) é leitura, não ronda: fora da contagem de rondas; a ronda que ela revisou fica
    # fora da evolução (no dia dela, vale o valor validado)
    rondas_hist = [r for r in hist if not r.get("validada")]
    lidas = [r for r in hist if (r["sujidade"] is not None or r["vegetacao"] is not None) and not r.get("revisada")]
    return render_template("campo/rondas_usina.html", **_comum(
        "rondas", leitura, usina=usina, usina_id=usina_id, hist=hist, rondas_hist=rondas_hist, lidas=lidas,
        duracao=_duracao, iniciais=_iniciais, suj_estado=ronda_checklist.estado(),
        explicacao_avulsa=ronda_avulsa.EXPLICACAO, explicacao_validada=visao.VALIDADA_EXPLICACAO))


@bp.route("/rondas/avulsa", methods=["GET", "POST"])
def ronda_avulsa_lancar():
    """Lançar uma ronda avulsa (Levi, 07/10/2026: "a pessoa loga pelo fractal dela ... não terá imagens, só informações
    da tabela, salva nome da pessoa, data e hora e diz que foi avulso"). Recusa volta com o motivo e o que foi digitado
    (400); o lançamento gravado e conferido no banco volta para esta página com o aviso (303)."""
    usuario = session.get("usuario")
    erro = None
    if request.method == "POST":
        try:
            nova = ronda_avulsa.lancar(request.form, usuario)
            session["avulsa_aviso"] = f"Ronda avulsa lançada: {_dia_curto(nova['data'])}, das {nova['inicio'][11:16]} às {nova['fim'][11:16]}."
            return redirect(na_raiz("/t/campo/rondas/avulsa"), code=303)
        except ronda_avulsa.Recusada as e:
            erro = str(e)
        except Exception as e:      # noqa: BLE001 — banco fora: a tela diz, nada some calado
            erro = f"Não consegui gravar no banco ({type(e).__name__}). Tente de novo em instantes."
    leitura = visao.rondas()
    from ...campo.ligacao_cadastro import codigo_da_pessoa
    from flask import current_app
    meu = codigo_da_pessoa(current_app.config.get("NEXUS_PESSOA_HMAC"), (usuario or {}).get("email") or "") if usuario else ""
    minhas = [r for r in (leitura.dados or {}).get("todas") or [] if r.get("avulsa") and meu and r.get("avulsa_hmac") == meu]
    html = render_template("campo/ronda_avulsa.html", **_comum(
        "rondas", leitura, usuario=usuario, erro=erro, aviso=session.pop("avulsa_aviso", None),
        form=request.form if erro else ImmutableMultiDict(), usinas=ronda_avulsa.usinas_para_escolher() if usuario else [],
        minhas=minhas, explicacao_avulsa=ronda_avulsa.EXPLICACAO, hoje=visao._agora().date().isoformat(),
        piso=(visao._agora().date() - timedelta(days=ronda_avulsa.DIAS_ATRAS)).isoformat(),
        tipos=ronda_avulsa.TIPOS, valas=ronda_avulsa.VALAS, sensores=ronda_avulsa.SENSORES,
        estados_sensor=ronda_avulsa.ESTADOS_SENSOR, duracao=_duracao, comentario_max=ronda_avulsa.COMENTARIO_MAX))
    return (html, 400) if erro else html


@bp.route("/rondas/avulsa/<rid>/anular", methods=["POST"])
def ronda_avulsa_anular(rid):
    """Anular a própria ronda avulsa: vira outra linha no banco (o banco não apaga)."""
    try:
        ronda_avulsa.anular(rid, session.get("usuario"))
    except ronda_avulsa.Recusada as e:
        return render_template("campo/ronda_avulsa.html", **_comum(
            "rondas", visao.rondas(), usuario=session.get("usuario"), erro=str(e), aviso=None, form=ImmutableMultiDict(), usinas=[],
            minhas=[], explicacao_avulsa=ronda_avulsa.EXPLICACAO, hoje="", piso="", tipos=(), valas=(), sensores=[],
            duracao=_duracao, comentario_max=ronda_avulsa.COMENTARIO_MAX)), 400
    session["avulsa_aviso"] = "Ronda avulsa anulada: ela sai das telas e a anulação fica registrada no banco."
    return redirect(na_raiz("/t/campo/rondas/avulsa"), code=303)


@bp.route("/rondas/os/<int:os_>/fotos")
def ronda_fotos_os(os_):
    """As fotos da OS de ronda, separadas em sujidade, vegetação e as demais (Levi, 06/10: "ao clicar no botão aparecer
    os anexos, separando vegetação e sujidade"). Pedaço de HTML que o botão Fotos do histórico carrega."""
    try:
        gs = ronda_fotos.grupos(os_)
        erro = ""
        ronda_fotos.preparar(os_, ronda_checklist.em_segundo_plano)     # nos testes, na hora
    except Exception as e:      # noqa: BLE001 — Fracttal fora ou recusando: o pedaço diz, a página segue
        gs = []
        erro = ("O Fracttal recusou agora por excesso de pedidos; tente de novo em 1 minuto."
                if "429" in str(e) else f"Não consegui ler os anexos da OS no Fracttal ({type(e).__name__}).")
    return render_template("campo/_ronda_fotos.html", os_=os_, grupos=gs, erro=erro,
                           total=sum(len(g["fotos"]) for g in gs))


@bp.route("/rondas/os/<int:os_>/foto/<int:i>")
def ronda_foto(os_, i):
    """Uma foto da OS de ronda: o Nexus baixa do Fracttal e entrega (o link assinado não sai para o navegador)."""
    # a ampliada é a versão de tela (13/10/2026, Levi: "na hora de ver expandido demora muito para carregar"); a
    # original, com ?original=1
    fazer = (ronda_fotos.miniatura if request.args.get("mini")
             else ronda_fotos.foto if request.args.get("original") else ronda_fotos.tela)
    try:
        corpo, mime = fazer(os_, i)
    except ronda_fotos.SemFoto as e:
        return Response(str(e), status=404, mimetype="text/plain")
    except Exception as e:      # noqa: BLE001
        return Response(f"Fracttal: {type(e).__name__}", status=502, mimetype="text/plain")
    # com a versão do arquivo no endereço (?v=, o mesmo arquivo do Fracttal), o navegador guarda 7 dias sem perguntar
    guarda = "private, max-age=604800, immutable" if request.args.get("v") else "private, max-age=3600"
    return Response(corpo, mimetype=mime, headers={"Cache-Control": guarda})


@bp.route("/zeladoria")
def zeladoria():
    return render_template("campo/zeladoria.html", **_comum("zeladoria", visao.zeladoria()))


# ── Ranking de pontos (13/10/2026) ───────────────────────────────────────────────────────────────────────────────
# Levi: "Quero que traga o ranking de pontos dos técnicos para o Nexus. Cria uma seção de Ranking de Pontos no App de
# Campo!". O placar é o do ciclo do App, como ele publica (visao.ranking_pontos); aqui só o mês (o corrente e o anterior)
# e a região que o App escreve. A posição é a do ciclo inteiro, mesmo com a região escolhida: é a que o técnico vê no App.
MESES_PT = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
            "novembro", "dezembro")


def _nome_do_mes(mes: str) -> str:
    try:
        ano, m = mes.split("-")
        return f"{MESES_PT[int(m) - 1]} de {ano}"
    except (ValueError, IndexError):
        return mes


def _hora_brt(iso: str) -> str:
    """A hora (de Brasília) em que o App calculou o placar, "13/10 18:25"."""
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return ""
    return (d if d.tzinfo else d.replace(tzinfo=_BRT)).astimezone(_BRT).strftime("%d/%m %H:%M")


@bp.route("/ranking")
def ranking():
    leitura = visao.ranking_pontos()
    meses = leitura.dados.get("meses") or []
    atual = next((m for m in meses if m["mes"] == request.args.get("mes")), meses[0] if meses else None)
    todos = (atual["classificacao"] + atual["fora"]) if atual else []
    regioes = sorted({p["regiao"] for p in todos if p["regiao"]}, key=str.lower)
    regiao = request.args.get("regiao") or ""
    if regiao not in regioes:
        regiao = ""

    def da_regiao(lista):
        return [p for p in lista if not regiao or p["regiao"] == regiao]
    classificacao = da_regiao(atual["classificacao"]) if atual else []
    fora = da_regiao(atual["fora"]) if atual else []
    return render_template("campo/ranking.html", **_comum(
        "ranking", leitura, meses=meses, atual=atual, regioes=regioes, regiao=regiao, classificacao=classificacao,
        fora=fora, nome_do_mes=_nome_do_mes, calculado=_hora_brt(atual["calculado_em"]) if atual else "",
        media=round(sum(p["total"] for p in classificacao) / len(classificacao)) if classificacao else None))


# ── Aprovação de OS (a fila e os grupos são os do App, nexus/campo/aprovacao.py) ─────────────────────────────────
GRUPOS = (("completa", "Evidência completa", "ok",
           "Subtarefas respondidas, nota alta, tempo dentro do previsto, nenhuma foto marcada. Não pede análise, "
           "pede decisão."),
          ("olho", "Precisa do seu olho", "alerta",
           "Nota abaixo de 80, tempo muito fora do previsto, foto marcada pelo motor ou já devolvida antes."),
          ("fora_do_app", "Fechadas fora do App", "neutro",
           "Sem evidência para julgar por aqui. Encolhe conforme a equipe adota o App, e é essa a métrica deste "
           "grupo."))


def _cor_espera(dias) -> str:
    n = int(dias or 0)
    return "critico" if n >= 30 else ("alerta" if n >= 7 else "ok")


IDADES = (("0-2", "até 2 dias", 0, 2), ("3-7", "3 a 7 dias", 3, 7), ("8-30", "8 a 30 dias", 8, 30),
          ("31-60", "31 a 60 dias", 31, 60), ("61-", "mais de 60 dias", 61, 10 ** 6))
# O cartão "Paradas há 30 dias ou mais" filtra as MESMAS OS que conta (30 dias ou mais). Levava à faixa "31 a 60 dias":
# com a fila inteira (Levi, 08/10/2026: "não deve ter filtro 'OS fechadas nos X dias'") a OS parada há 120 dias contava
# no cartão e sumia no clique. Só o cartão usa esta faixa; a barra de idade segue com as cinco de cima.
IDADE_PARADAS = ("30-", "há 30 dias ou mais", 30, 10 ** 6)
# As visões "por técnico" e "fila" saíram em 08/10/2026 (Levi: "a visão de por técnico e fila pode matar, pode tirar que
# é irrelevante!"): ficam os cartões (hoje por região de campo ou por gestor), e o cartão abre a tabela das OS dele
# (`ver=`), onde se aprova.
SEM_CADASTRO = "Sem cadastro"
# Os cartões da Aprovação: por região de campo (o padrão: é o Supervisor de Campo da região quem aprova) ou por gestor de
# contrato (a alternância). `ver=` abre a tabela do cartão do agrupamento de agora.
AGRUPAR = {"regiao": "regiao_cad", "gestor": "gestor_cad"}


# O grupo da OS sai das tarefas dela: quem aprova, aprova a OS inteira (Levi, 05/10: "ele não consegue aprovar uma
# tarefa em si, e sim uma PT ou uma OS"). Basta uma tarefa pedir olho para a OS pedir; sem isso, uma tarefa fechada fora
# do App já tira a OS de "completa"; completa é só a OS com TODAS as tarefas completas.
ORDEM_DO_GRUPO = ("olho", "fora_do_app", "completa")


def _por_os(linhas) -> list[dict]:
    """Uma linha por OS, a partir das tarefas da fila (cada tarefa com o grupo e os motivos do App)."""
    g = {}
    for x in linhas:
        o = g.setdefault(x["os"], {"os": x["os"], "id_wo": None, "tarefas": []})
        o["tarefas"].append(x)
        o["id_wo"] = o["id_wo"] or x.get("id_wo")
    for o in g.values():
        ts = o["tarefas"]
        baldes = {t["balde"] for t in ts}
        o["balde"] = next(b for b in ORDEM_DO_GRUPO if b in baldes)
        o["espera_d"] = max(t.get("espera_d") or 0 for t in ts)              # a tarefa mais antiga
        o["fim"] = max(str(t.get("fim") or "") for t in ts)
        o["tecnicos"] = sorted({t.get("tecnico") or "—" for t in ts})
        primeira = next((t for t in ts if t.get("usina_cad")), ts[0])
        for c in ("usina_cad", "equipe_cad", "regiao_cad", "supervisor_campo_cad", "gestor_cad", "regiao_br"):
            o[c] = primeira.get(c) or ""
        # quem aprova a OS: o das usinas das tarefas (OS em duas regiões, rara, é das duas)
        o["aprovadores"] = []
        for t in ts:
            if t.get("aprovador") and t["aprovador"] not in o["aprovadores"]:
                o["aprovadores"].append(t["aprovador"])
        notas = [int(t["qualidade"]) for t in ts if t.get("pelo_app") and t.get("qualidade") is not None]
        o["nota"] = min(notas) if notas else None                            # a pior tarefa
        o["pelo_app"] = all(t.get("pelo_app") for t in ts)
        o["n_app"] = sum(1 for t in ts if t.get("pelo_app"))
        o["devolvida"] = any(t.get("foi_devolvida") for t in ts)
        o["ronda"] = any(t.get("ronda") for t in ts)
        o["n_por_grupo"] = {b: sum(1 for t in ts if t["balde"] == b) for b in ORDEM_DO_GRUPO}
        # as colunas da tabela do supervisor (Levi, 08/10/2026: "a OS, dia, data da criação da OS, data fim, supervisor,
        # prontas, pedem olho, fora do App, uso do App, nota média e devolvidas"): contadas nas tarefas da OS
        o["criada"] = min((str(t.get("criada")) for t in ts if t.get("criada")), default="")
        o["uso_app"] = round(100 * o["n_app"] / len(ts))
        o["nota_media"] = round(sum(notas) / len(notas)) if notas else None
        o["n_devolvidas"] = sum(1 for t in ts if t.get("foi_devolvida"))
    return sorted(g.values(), key=lambda o: -o["espera_d"])


def _data_br(iso) -> str:
    """dd/mm/aa no horário de Brasília. O Fracttal fala UTC: a data de fim vem sem fuso (o App corta em 19 caracteres)
    e a de criação com "+00:00"; sem converter, a OS fechada às 22 h de Brasília aparecia no dia seguinte."""
    s = str(iso or "").strip().replace("Z", "+00:00")
    if not s:
        return "—"
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return s[:10]
    d = d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    return d.astimezone(_BRT).strftime("%d/%m/%y")


def _agrupa_os(oss, chaves) -> list[dict]:
    """Um cartão por supervisor (a chave que `chaves` der): as OS esperando, os três grupos, a idade e o uso do App,
    em OS. (A nota, as devolvidas, a equipe e o supervisor "da maioria" serviam só à tabela por técnico, que saiu em
    08/10/2026; o que é da OS está na tabela do supervisor, `_por_os`.)"""
    g = {}
    for o in oss:
        for k in chaves(o):
            k = k or SEM_CADASTRO
            a = g.setdefault(k, {"nome": k, "ordens": 0, "tarefas": 0, "completa": 0, "olho": 0, "fora_do_app": 0,
                                 "aged7": 0, "aged30": 0, "espera_max": 0, "pelo_app": 0, "equipes": set(),
                                 "tecnicos": set()})
            a["ordens"] += 1
            a["tarefas"] += len(o["tarefas"])
            a[o["balde"]] += 1
            a["aged7"] += o["espera_d"] >= 7
            a["aged30"] += o["espera_d"] >= 30
            a["espera_max"] = max(a["espera_max"], o["espera_d"])
            a["pelo_app"] += o["pelo_app"]
            a["equipes"].add(o.get("equipe_cad") or SEM_CADASTRO)
            a["tecnicos"].update(o["tecnicos"])
    for a in g.values():
        a["uso_app"] = round(100 * a["pelo_app"] / a["ordens"]) if a["ordens"] else None
        a["n_equipes"], a["n_tecnicos"] = len(a.pop("equipes")), len(a.pop("tecnicos"))
    return list(g.values())


@bp.route("/aprovacao")
def aprovacao():
    """A fila de verificação do Fracttal para tirar insight (Levi, 05/10: "refaça essa parte de aprovação de OS para
    retirada de bons insights"), contada por OS, que é o que se aprova. Os grupos de cada tarefa são os do App (a fila
    inteira pela `_fila_supervisao`); a equipe, a região de campo e o gestor vêm do cadastro do Nexus, pela usina do
    Fracttal (de-para "Fracttal · Classificação 1").
    Desde 08/10/2026 (Levi): a fila INTEIRA, sem "OS fechadas nos X dias"; uma visão só, os cartões (por região de campo,
    a estrutura de O&M de 10/2026, com a alternância para gestor de contrato); o cartão abre a tabela das OS dele
    (`ver=`), uma linha por OS que abre o porquê do grupo e o Aprovar, que só quem aprova a OS (o Supervisor de Campo da
    região; com a vaga aberta, o Coordenador) ou um administrador usa (`aprovar_os.py`). Os indicadores e a barra da
    idade filtram cartões e tabela."""
    equipe, regiao_campo, gestor = request.args.get("equipe", ""), _regiao_campo(), _gestor()
    por = "gestor" if request.args.get("por") == "gestor" else "regiao"
    mapa = visao.usinas_do_fracttal()
    opcoes = mapa.dados or {}
    usinas = None
    for escolhido, grupo in ((equipe, "equipes"), (regiao_campo, "regioes"), (gestor, "gestores")):
        if escolhido:
            nomes = set((opcoes.get(grupo) or {}).get(escolhido) or [])
            usinas = nomes if usinas is None else usinas & nomes
    leitura = campo_aprovacao.fila_toda(campo_aprovacao.FILA_INTEIRA, usinas)
    d = leitura.dados or {}
    por_nome = opcoes.get("por_nome") or {}
    todas = d.get("linhas") or []
    for x in todas:
        cad = por_nome.get(regras_app._norm(x.get("usina_fx"))) or {}
        x["usina_cad"], x["equipe_cad"] = cad.get("usina") or x.get("usina_fx") or "", cad.get("equipe") or ""
        x["regiao_cad"], x["gestor_cad"] = cad.get("regiao_campo") or "", cad.get("gestor") or ""
        x["supervisor_campo_cad"], x["regiao_br"] = cad.get("supervisor_campo") or "", cad.get("regiao_br") or ""
        x["aprovador"] = cad.get("aprovador") or visao.aprovador_sem_cadastro()
    oss = _por_os(todas)
    balde = request.args.get("balde") if request.args.get("balde") in ORDEM_DO_GRUPO else ""
    idade = next((i for i in IDADES + (IDADE_PARADAS,) if i[0] == request.args.get("idade")), None)
    # os indicadores e a idade filtram os cartões e a tabela; os números do topo seguem sobre a fila inteira
    filtradas = [o for o in oss if (not balde or o["balde"] == balde)
                 and (not idade or idade[2] <= o["espera_d"] <= idade[3])]
    # o supervisor aberto (Levi, 08/10: "nessa visão por supervisor deve ser clicável, quando clica aparece a OS ...")
    ver = request.args.get("ver", "")
    tabela = [o for o in filtradas if (o.get(AGRUPAR[por]) or SEM_CADASTRO) == ver] if ver else []
    nome_grupo = {g[0]: g[1] for g in GRUPOS}
    if request.args.get("csv") == "1":
        import csv
        import io
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["OS", "Dias esperando", "Criação da OS", "Data fim", "Região de campo", "Supervisor de campo",
                    "Gestor de contrato", "Equipe", "Usina", "Técnicos",
                    "Tarefas", "Prontas", "Pedem olho", "Fora do App", "Uso do App (%)", "Nota média",
                    "Devolvidas", "Grupo da OS", "Quem aprova"])
        for o in (tabela if ver else filtradas):
            n = o["n_por_grupo"]
            w.writerow([o["os"], o["espera_d"], _data_br(o["criada"]) if o["criada"] else "", _data_br(o["fim"]),
                        o["regiao_cad"], o["supervisor_campo_cad"], o["gestor_cad"], o["equipe_cad"], o["usina_cad"],
                        ", ".join(o["tecnicos"]),
                        len(o["tarefas"]), n["completa"], n["olho"], n["fora_do_app"], o["uso_app"],
                        "" if o["nota_media"] is None else o["nota_media"], o["n_devolvidas"],
                        nome_grupo.get(o["balde"]), " ".join(a["texto"] for a in o["aprovadores"])])
        return Response("\ufeff" + buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="aprovacao-os.csv"'})
    mais_antiga = oss[0] if oss else None
    k = {"ordens": len(oss), "tarefas": len(todas), "baldes": {b: sum(1 for o in oss if o["balde"] == b) for b in ORDEM_DO_GRUPO},
         "aged30": sum(1 for o in oss if o["espera_d"] >= 30), "espera_max": mais_antiga["espera_d"] if mais_antiga else 0,
         "mais_antiga": mais_antiga, "uso_app": round(100 * sum(o["pelo_app"] for o in oss) / len(oss)) if oss else None}
    idades = [(i, sum(1 for o in oss if i[2] <= o["espera_d"] <= i[3])) for i in IDADES]
    info = {r["nome"]: r for r in opcoes.get("regioes_info") or []}
    # sem cadastro (usina sem de-para), sem região de campo e sem gestor: cartões próprios, sempre por último
    sem = (SEM_CADASTRO, visao.SEM_REGIAO, visao.SEM_GESTOR)
    cartoes = sorted(_agrupa_os(filtradas, lambda o: [o.get(AGRUPAR[por])]),
                     key=lambda a: (a["nome"] in sem, -a["aged30"], -a["ordens"], a["nome"]))
    for a in cartoes:
        a["regiao"] = info.get(a["nome"]) if por == "regiao" else None
    aberto = next((a for a in cartoes if a["nome"] == ver), None) if ver else None
    linhas_filtro = [{"regiao_campo": x["regiao_campo"], "gestor": x["gestor"]} for x in (opcoes.get("por_nome") or {}).values()]
    return render_template("campo/aprovacao.html", **_comum(
        "aprovacao", leitura, grupos=GRUPOS, nome_grupo={g[0]: (g[1], g[2]) for g in GRUPOS}, balde=balde,
        cor_espera=_cor_espera, coleta=_coleta(), fila=campo_aprovacao.estado(), equipe=equipe,
        equipes=sorted(opcoes.get("equipes") or {}), por=por,
        **_papeis({"regioes": opcoes.get("regioes_info") or [], "estrutura_publicada": opcoes.get("estrutura_publicada", True)},
                  linhas_filtro, regiao_campo, gestor),
        mapa_erro=mapa.erro, k=k, idades=idades, idade=idade, ver=ver, aberto=aberto, tabela=tabela,
        limite=LIMITE_LINHAS, cartoes=cartoes, sem_cadastro=SEM_CADASTRO, data_br=_data_br,
        pode_aprovar=pode_na_tela, motivos=campo_aprovacao.motivos))


# ── Triagem de qualidade (a mesa de triagem do App, nexus/campo/triagem.py) ──────────────────────────────────────
def _rot_item(i) -> str:
    if i.get("tipo") == "os":
        return f"OS {i.get('id')}"
    if i.get("tipo") == "ronda":
        return f"Ronda {_dia_curto(i.get('data') or i.get('quando') or i.get('id'))}"
    if i.get("tipo") in ("usina", "usina_nunca"):
        return i.get("onde") or "Cobertura"
    return i.get("quem") or str(i.get("id") or "")


def _motivo(texto) -> Markup:
    """O motivo vem das regras do App com <b> no número que importa: escapa tudo e devolve só o negrito."""
    return Markup(str(escape(texto or "")).replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>"))


@bp.route("/triagem")
def triagem():
    dias = _dias((7, 30, 90), 30)
    return render_template("campo/triagem.html", **_comum("triagem", campo_triagem.painel(dias), dias=dias,
                                                          rot_item=_rot_item, motivo=_motivo, coleta=_coleta()))

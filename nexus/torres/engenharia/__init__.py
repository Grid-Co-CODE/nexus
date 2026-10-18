"""Torre Engenharia: Confiabilidade dos ativos, criticidade e causa raiz.

A Confiabilidade é nossa desde 06/10/2026 (Levi: "traga a aba Confiabilidade do pcm.gridco.com.br, não referenciando
diretamente esse caminho mas construindo algo nosso!"): o Nexus lê as OS de falha do Fracttal (`nexus/engenharia/
os_falhas.py`) e faz as contas (`nexus/engenharia/confiabilidade.py`). Desde 18/10/2026 a Confiabilidade tem o
acompanhamento dos ativos com sinal (pegar, encaminhar, diagnóstico, comentários; `nexus/engenharia/acompanhamento.py`).
O Quadro da equipe também é nosso; as outras telas seguem no placeholder da casca.
Leia o CLAUDE.md desta pasta antes de mexer.
"""
import collections
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode

from flask import abort, redirect, render_template, request, session

from ..modelo import Tela, Torre

TORRE = Torre(
    id="engenharia",
    nome="Engenharia",
    ordem=40,
    icone="gear-six",
    descricao="Confiabilidade dos ativos, criticidade e causa raiz.",
    telas=[
        # a primeira tela da Engenharia (Levi, 18/10/2026: "Sim, a primeira"), do setor Engenharia: quem é dele a vê
        # sem marcá-la em Base → Acessos
        Tela("mesa", "Mesa do engenheiro",
             "O que está comigo, o que me encaminharam e o que precisa de dono?",
             "Acompanhamento dos ativos da Engenharia (banco) e as OS de falha do Fracttal",
             do_setor="Engenharia"),
        Tela("confiabilidade", "Confiabilidade",
             "Quais ativos falham mais e demoram mais a voltar?",
             "OS de falha do Fracttal, lidas pelo Nexus"),
        Tela("equipe", "Quadro da equipe",
             "Quem da engenharia está com o quê, o que atrasou e o que vem por aí?",
             "OS do Fracttal dos responsáveis da engenharia"),
        Tela("criticidade", "Matriz de criticidade",
             "Qual ativo, se parar, dói mais?",
             "engenharia.json do painel PCM"),
        Tela("fmea", "FMEA e causa raiz",
             "Por que a falha acontece e o que a elimina?",
             "Planilha de confiabilidade (a migrar)"),
        Tela("laudos", "Laudos MPS/MPA",
             "Que laudos estão pendentes ou vencidos?",
             "engenharia.json do painel PCM"),
    ],
)

bp = TORRE.criar_blueprint(__name__)

BRT = timezone(timedelta(hours=-3))
CACHE_S = 300
_CACHE: dict = {}
# as abas do acompanhamento (18/10/2026): o ativo pego sai de Ativos com sinal e vai para Em acompanhamento; o encerrado,
# para Encerrados; o cadastro dos diagnósticos só para quem pode mexer nele
ABAS = (("ativos", "Ativos com sinal"), ("acompanhamento", "Em acompanhamento"), ("encerrados", "Encerrados"),
        ("indicadores", "Indicadores"), ("diagnosticos", "Diagnósticos"))


def _url(**mudar) -> str:
    args = {k: v for k, v in request.args.items() if v}
    for k, v in mudar.items():
        if v in (None, ""):
            args.pop(k, None)
        else:
            args[k] = v
    return "?" + urlencode(args) if args else "?"


def _onde_do_cadastro():
    """A ligação com o cadastro do Nexus (o registro mestre): a mesma do Campo · App, pelo de-para do Fracttal."""
    from ...campo import visao
    try:
        b = visao._Base()
    except Exception as e:  # noqa: BLE001 — banco fora: segue com o que o Fracttal escreve, e a tela avisa
        import logging
        logging.warning("confiabilidade: o cadastro não respondeu (%s: %s)", type(e).__name__, str(e)[:160])
        b = None
    memo = {}

    def onde(texto: str, cod: str) -> dict:
        chave = (texto, cod.split("-")[0])
        if chave in memo:
            return memo[chave]
        uid, como = b.lig.usina(texto, cod) if b else (None, None)
        u = (b.por_id.get(uid) or {}) if b else {}
        if u:
            mob = None
            try:
                mob = datetime.fromisoformat(str(u.get("data_mobilizacao") or "")[:10]).replace(tzinfo=BRT)
            except ValueError:
                pass
            o = b.onde(uid)
            r = {"usina_id": uid, "usina": o["usina"], "cliente": o["cliente"] or "—", "cluster": o["cluster"],
                 "uf": o["uf"], "equipe": o["equipe"], "mobilizacao": mob, "ligada_por": como}
        else:
            partes = [p.strip() for p in texto.split(" - ")]
            r = {"usina_id": None, "usina": " - ".join(partes[1:]) if len(partes) > 1 else texto or "—",
                 "cliente": partes[0] if partes and partes[0] else "—", "cluster": "", "uf": "", "equipe": "",
                 "mobilizacao": None, "ligada_por": None}
        memo[chave] = r
        return r
    onde.sem_cadastro = b is None
    return onde


def _dados() -> dict:
    """As contas, refeitas quando a leitura do Fracttal muda ou a cada 5 min (são ~13 mil linhas: menos de 1 s)."""
    from ...engenharia import confiabilidade, os_falhas
    os_falhas.pedir_releitura()
    est = os_falhas.estado()
    marca = (est["n"], est["vivas_em"])
    g = _CACHE.get("conf")
    # sem o cadastro, a conta vale só 30 s: a próxima visita tenta de novo
    if g and g["marca"] == marca and time.time() - g["em"] < (30 if g.get("sem_cadastro") else CACHE_S):
        return g
    onde = _onde_do_cadastro()
    d = confiabilidade.calcular(os_falhas.linhas(), onde)
    g = {"marca": marca, "em": time.time(), "dados": d, "sem_cadastro": getattr(onde, "sem_cadastro", False)}
    _CACHE["conf"] = g
    return g


def _h(x) -> str:
    """Horas: 5.737 h, 25,9 h."""
    if x is None:
        return "—"
    return f"{x:,.0f}".replace(",", ".") + " h" if x >= 100 else f"{x:.1f}".replace(".", ",") + " h"


def _pct(x) -> str:
    return "—" if x is None else f"{100 * x:.1f}".replace(".", ",") + "%"


def _gavetas_e_listas(d: dict, f: dict, esconder: bool, aba: str) -> dict:
    """O acompanhamento na Confiabilidade (18/10/2026; desenho em docs/superpowers/specs/2026-10-18-engenharia-
    acompanhamento-design.md): as três listas das abas, com os filtros, e a gaveta de cada cartão da aba aberta."""
    from ...dados.equipamento import canon
    from ...engenharia import acompanhamento as AC
    lido = AC.ler()
    erro_acomp = "" if lido.get("lido_em") else (lido.get("erro") or "").split(":")[0]
    acomps = AC.estado(lido["eventos"])
    diags = AC.diagnosticos(lido["diagnosticos"])
    falhas_em = d.get("falhasEm") or {}
    sep = AC.separar(d["sinais"], acomps, falhas_em)
    # o ativo de um acompanhamento sem sinal agora: o da conta de disponibilidade, ou só o que o livro guardou
    base = {canon(a["cod"]): a for a in d["ativos"]}
    base.update({canon(s["cod"]): s for s in d["sinais"]})

    def ativo_de(x):
        return x["ativo"] or base.get(canon(x["acomp"]["cod"])) or {
            "cod": x["acomp"]["cod"], "nome": x["acomp"]["cod"], "usina": "", "cliente": "", "fam": "", "crit": ""}
    q = f["q"].strip().lower()

    def passa(a, nivel, quem=None):
        return ((not f["cliente"] or a.get("cliente") == f["cliente"]) and (not f["usina"] or a.get("usina") == f["usina"])
                and (not f["fam"] or a.get("fam") == f["fam"]) and (not f["crit"] or a.get("crit") == f["crit"])
                and (not f["nivel"] or nivel == f["nivel"]) and (quem is None or not f["quem"] or quem == f["quem"])
                and (not q or q in f"{a.get('cod')} {a.get('nome')} {a.get('usina')} {a.get('cliente')}".lower()))
    sinais = [s for s in sep["sinal"] if passa(s, s.get("nivel")) and not (esconder and s["soServico"])]
    # em acompanhamento vale o nível de agora; no encerrado, o da entrada (encerrado quase nunca tem sinal agora)
    abertos = [dict(x, a=ativo_de(x)) for x in sep["aberto"]
               if passa(ativo_de(x), (x["ativo"] or {}).get("nivel"), x["acomp"]["responsavel"]["hmac"])]
    encerrados = [dict(x, a=ativo_de(x), voltou_dia=x["voltou"].astimezone(BRT).strftime("%d/%m") if x["voltou"] else "")
                  for x in sep["encerrado"]
                  if passa(ativo_de(x), x["acomp"]["nivel_entrada"], x["acomp"]["responsavel"]["hmac"])]
    anteriores = {}
    for x in sep["encerrado"]:
        anteriores.setdefault(canon(x["acomp"]["cod"]), []).append(x["acomp"])

    def gaveta(i, a, acomp, novas):
        c = canon(a.get("cod") or (acomp or {}).get("cod"))
        return _montar_gaveta(f"g{i}", a, acomp, novas,
                              [x for x in anteriores.get(c, []) if not acomp or x["id"] != acomp["id"]],
                              falhas_em.get(c, []) if a.get("nivel") else [])
    if aba == "ativos":
        gavetas = [gaveta(i, s, None, []) for i, s in enumerate(sinais)]
    elif aba == "acompanhamento":
        gavetas = [gaveta(i, x["a"], x["acomp"], x["novas"]) for i, x in enumerate(abertos)]
    elif aba == "encerrados":
        gavetas = [gaveta(i, x["a"], x["acomp"], []) for i, x in enumerate(encerrados)]
    else:
        gavetas = []
    fonte_quem = sep["aberto"] if aba == "acompanhamento" else sep["encerrado"]
    quem_opcoes = sorted({x["acomp"]["responsavel"]["hmac"]: x["acomp"]["responsavel"]["nome"] or "(sem nome)"
                          for x in fonte_quem if x["acomp"]["responsavel"]["hmac"]}.items(), key=lambda kv: kv[1].lower())
    return {"sinais": sinais, "abertos": abertos, "encerrados": encerrados, "gavetas": gavetas, "diags": diags,
            "diags_ativos": [x for x in diags if not x["excluido"]], "diag_nome": {x["id"]: x["nome"] for x in diags},
            "quem_opcoes": quem_opcoes, "erro_acomp": erro_acomp, "erro_leitura": bool(erro_acomp),
            "velha_em": datetime.fromtimestamp(lido["lido_em"], BRT).strftime("%H:%M") if lido.get("velha") else "",
            "piso": AC.PISO.isoformat(),
            "uso": collections.Counter(a["diagnostico_id"] for a in acomps.values() if a["diagnostico_id"]),
            # sem ler o livro, os números de Em acompanhamento e Encerrados não são 0: são desconhecidos (revisão final)
            "contas": {"ativos": len(sinais), "acompanhamento": "—" if erro_acomp else len(abertos),
                       "encerrados": "—" if erro_acomp else len(encerrados)}}


def _montar_gaveta(gid: str, a: dict, acomp: dict | None, novas: list, anteriores: list, falhas: list) -> dict:
    """O que a gaveta de um ativo mostra (engenharia/_gaveta.html), na página e na resposta das ações: o ativo, o
    acompanhamento, as falhas novas com o dia, os encerrados anteriores e o dia de cada falha do ativo (o aviso de que o
    fim escolhido faz o ativo voltar para Ativos com sinal). `falhas` vazio para o ativo sem o sinal de 30 dias: ele
    não volta para a lista, e o aviso não vale (acabamento da revisão final)."""
    return {"id": gid, "a": a, "acomp": acomp,
            "novas": [dict(x, dia=x["quando"].astimezone(BRT).strftime("%d/%m")) for x in novas],
            "anteriores": anteriores,
            "falhas_dias": sorted({x["quando"].astimezone(BRT).strftime("%Y-%m-%d") for x in falhas})}


def _quem_pode() -> tuple[bool, str | None]:
    """(pode agir no acompanhamento, o código da pessoa do login): o administrador e quem é do setor Engenharia."""
    from ...auth import setor_telas as ST
    from ...engenharia import acompanhamento as AC
    setor = (ST.acesso() or {}).get("setor")
    return AC.pode_agir(setor, bool(session.get("admin"))), AC.codigo(session.get("usuario"))


def _pessoas(pode: bool) -> list[dict]:
    """As pessoas da Engenharia para o Encaminhar (o setor no banco e o nome no Fracttal); sem elas, a lista fica vazia
    e a gaveta diz por quê."""
    if not pode:
        return []
    from ...engenharia import acompanhamento as AC
    try:
        return AC.pessoas_da_engenharia()
    except Exception as e:      # noqa: BLE001 — setor ou Fracttal fora: o Encaminhar diz que não há a quem
        import logging
        logging.warning("confiabilidade: as pessoas da Engenharia não vieram (%s: %s)", type(e).__name__, str(e)[:160])
        return []


@bp.route("/confiabilidade")
def confiabilidade():
    from ...engenharia import confiabilidade as C
    from ...engenharia import os_falhas
    g = _dados()
    d = g["dados"]
    pode, meu = _quem_pode()
    abas = tuple(x for x in ABAS if x[0] != "diagnosticos" or pode)
    f = {k: request.args.get(k, "") for k in ("cliente", "usina", "fam", "crit", "nivel", "q", "quem")}
    esconder = request.args.get("servico") == "0"
    aba = request.args.get("aba") if request.args.get("aba") in dict(abas) else "ativos"
    q = f["q"].strip().lower()

    def passa(a, com_nivel=True):
        return ((not f["cliente"] or a.get("cliente") == f["cliente"]) and (not f["usina"] or a.get("usina") == f["usina"])
                and (not f["fam"] or a["fam"] == f["fam"]) and (not f["crit"] or a["crit"] == f["crit"])
                and (not com_nivel or not f["nivel"] or a.get("nivel") == f["nivel"])
                and (not q or q in f"{a['cod']} {a['nome']} {a.get('usina')} {a.get('cliente')}".lower()))
    # todos os ativos com sinal (acompanhados ou não): o painel ao lado e a faixa descrevem a frota (escolha de 18/10)
    todos = [a for a in d["sinais"] if passa(a) and not (esconder and a["soServico"])]
    ativos = [a for a in d["ativos"] if passa(a, com_nivel=False)]
    por = request.args.get("por") if request.args.get("por") in ("cliente", "usina") else "cliente"
    clientes = sorted({a.get("cliente") for a in d["ativos"] + d["sinais"] if a.get("cliente")})
    usinas = sorted({a.get("usina") for a in d["ativos"] + d["sinais"] if a.get("usina")
                     and (not f["cliente"] or a.get("cliente") == f["cliente"])})
    # o painel ao lado: os clientes com mais ativos com sinal (com os filtros de agora)
    por_cliente = {}
    for a in todos:
        x = por_cliente.setdefault(a.get("cliente") or "—", {"nome": a.get("cliente") or "—", "sinais": 0, "criticos": 0})
        x["sinais"] += 1
        x["criticos"] += a["nivel"] == "critico"
    top_clientes = sorted(por_cliente.values(), key=lambda x: (-x["sinais"], -x["criticos"], x["nome"]))[:6]
    ac = _gavetas_e_listas(d, f, esconder, aba)
    return render_template(
        "engenharia/confiabilidade.html", fams=d.get("familias") or [], crit_dist=d.get("critDist") or {},
        top_clientes=top_clientes, torre=TORRE, tela=TORRE.tela("confiabilidade"), d=d, k=d["kpi"],
        todos=todos, total_sinais=len(d["sinais"]), ativos=ativos, f=f, esconder=esconder, aba=aba, abas=abas,
        por=por, indicadores=C.indicadores(ativos, todos, por) if aba == "indicadores" else [],
        clientes=clientes, usinas=usinas, familias=C.FAMILIAS, niveis=C.NIVEIS, meta=C.META_DISP,
        janela=C.JANELA_DIAS, url=_url, h=_h, pct=_pct, est=os_falhas.estado(), sem_cadastro=g.get("sem_cadastro"),
        lido=datetime.fromtimestamp(g["em"], BRT).strftime("%H:%M"), pode=pode, meu=meu,
        pessoas=_pessoas(pode) if aba in ("ativos", "acompanhamento") else [],
        hoje=datetime.now(BRT).date().isoformat(),
        aviso_dg=session.pop(_AVISO_DG, None), erro_dg=session.pop(_ERRO_DG, None),
        periodo=f"{d['periodo']['de'].astimezone(BRT):%d/%m} a {d['periodo']['ate'].astimezone(BRT):%d/%m/%Y}", **ac)


# ── as ações do acompanhamento (18/10/2026) ─────────────────────────────────────────────────────────────────────────
# Toda ação é POST, só da própria página (`_de_outro_site`), e responde a gaveta do ativo relida do banco, com o aviso
# ou o erro: a gaveta grava sem sair dela, como o card das Contestações. O cadastro dos diagnósticos é a aba dele,
# com o vai-e-volta de sempre (303 e o aviso na sessão).
_AVISO_DG, _ERRO_DG = "engenharia_diag_aviso", "engenharia_diag_erro"
FALHOU_BANCO = "Não consegui gravar no banco ({}). Nada mudou; tente de novo em instantes."


# ── a Mesa do engenheiro (18/10/2026) ───────────────────────────────────────────────────────────────────────────────
# Levi: a primeira tela da Engenharia; cada um vê a sua mesa (o administrador escolhe de quem ver), com "Encaminhados
# para você" (até a pessoa mexer no ativo), "Com você" e "Críticos sem dono", e a faixa com os três números no modelo do
# Acompanhamento de chamados. O clique abre a mesma gaveta da Confiabilidade (_gaveta.html), com as mesmas ações.
def _ativos_por_codigo(d: dict) -> dict:
    """O ativo de cada código canônico: o item de sinais (com o nível) ou, sem sinal agora, o da disponibilidade."""
    from ...dados.equipamento import canon
    base = {canon(a["cod"]): a for a in d["ativos"]}
    base.update({canon(s["cod"]): s for s in d["sinais"]})
    return base


def _ativo_do(x: dict, base: dict) -> dict:
    """O ativo de um acompanhamento: o de agora, ou só o que o livro guardou (o código)."""
    from ...dados.equipamento import canon
    return x["ativo"] or base.get(canon(x["acomp"]["cod"])) or {
        "cod": x["acomp"]["cod"], "nome": x["acomp"]["cod"], "usina": "", "cliente": "", "fam": "", "crit": ""}


def _faixa_da_mesa(caixa: list, comigo: list, sem_dono: list, erro: str) -> list[dict]:
    """Os três números do topo, no modelo do Acompanhamento de chamados (o rótulo, o número pela gravidade, o detalhe).
    Sem ler o livro, os números são "—", nunca 0."""
    from ...engenharia import confiabilidade as C
    rotulos = ("Encaminhados para você", "Com você", "Críticos sem dono")
    if erro:
        return [{"rotulo": r, "valor": "—", "grav": "", "nota": [("não consegui ler os acompanhamentos", False)]}
                for r in rotulos]
    agora = datetime.now(BRT)
    if caixa:
        dias = max(0, (agora - min(x["acomp"]["com_desde"] or agora for x in caixa)).days)
        n1 = ([("o mais antigo chegou ", False), ("hoje", True), (", sem nada seu", False)] if dias == 0 else
              [("o mais antigo há ", False), (_dias(dias), True), (", sem nada seu", False)])
    else:
        n1 = [("nada esperando você", False)]
    comigo_todos = caixa + comigo
    novas = sum(1 for x in comigo_todos if x["novas"])
    n2 = ([(str(novas), True), (" com falha nova desde que entrou" if novas == 1 else
                                " com falha nova desde que entraram", False)] if novas else
          [("nenhum com falha nova", False)])
    if sem_dono:
        pior = max(sem_dono, key=lambda s: s.get("nFalha") or 0)
        n3 = [("o pior: ", False), (f"{pior.get('nFalha')} falhas em {C.JANELA_DIAS} dias", True)]
    else:
        n3 = [("todo crítico tem dono", False)]
    return [{"rotulo": rotulos[0], "valor": len(caixa), "grav": "alerta" if caixa else "", "nota": n1},
            {"rotulo": rotulos[1], "valor": len(comigo_todos), "grav": "", "nota": n2},
            {"rotulo": rotulos[2], "valor": len(sem_dono), "grav": "critico" if sem_dono else "", "nota": n3}]


@bp.route("/mesa")
def mesa():
    from ...dados.equipamento import canon
    from ...engenharia import acompanhamento as AC
    from ...engenharia import confiabilidade as C
    from ...engenharia import os_falhas
    g = _dados()
    d = g["dados"]
    pode, meu = _quem_pode()
    admin = bool(session.get("admin"))
    pessoas = _pessoas(pode)
    # cada um vê a sua; só o administrador escolhe de quem ver (o `pessoa` de outra pessoa é ignorado para os demais)
    alvo, pedida = meu, request.args.get("pessoa", "")
    if admin and pedida and any(p["hmac"] == pedida for p in pessoas):
        alvo = pedida
    nome_alvo = next((p["nome"] for p in pessoas if p["hmac"] == alvo), "")
    lido = AC.ler()
    erro = "" if lido.get("lido_em") else (lido.get("erro") or "").split(":")[0]
    acomps = AC.estado(lido["eventos"])
    falhas_em = d.get("falhasEm") or {}
    sep = AC.separar(d["sinais"], acomps, falhas_em)
    base = _ativos_por_codigo(d)
    nunca = datetime.min.replace(tzinfo=BRT)
    meus = [dict(x, a=_ativo_do(x, base)) for x in sep["aberto"] if alvo and x["acomp"]["responsavel"]["hmac"] == alvo]
    # a caixa: o que outra pessoa passou e quem recebeu ainda não mexeu (Levi: "Até eu mexer nele"), o mais antigo antes
    caixa = sorted((x for x in meus if x["acomp"]["encaminhado_por"] and not x["acomp"]["respondeu"]),
                   key=lambda x: x["acomp"]["com_desde"] or nunca)
    na_caixa = {x["acomp"]["id"] for x in caixa}
    comigo = [x for x in meus if x["acomp"]["id"] not in na_caixa]
    sem_dono = [s for s in sep["sinal"] if s.get("nivel") == "critico"] if not erro else []
    anteriores = {}
    for x in sep["encerrado"]:
        anteriores.setdefault(canon(x["acomp"]["cod"]), []).append(x["acomp"])
    gavetas = []

    def gaveta(a, acomp, novas) -> str:
        c = canon(a.get("cod") or (acomp or {}).get("cod"))
        gv = _montar_gaveta(f"g{len(gavetas)}", a, acomp, novas,
                            [x for x in anteriores.get(c, []) if not acomp or x["id"] != acomp["id"]],
                            falhas_em.get(c, []) if a.get("nivel") else [])
        gavetas.append(gv)
        return gv["id"]
    caixa = [dict(x, gid=gaveta(x["a"], x["acomp"], x["novas"])) for x in caixa]
    comigo = [dict(x, gid=gaveta(x["a"], x["acomp"], x["novas"])) for x in comigo]
    sem_dono = [dict(s, gid=gaveta(s, None, [])) for s in sem_dono]
    diags = AC.diagnosticos(lido["diagnosticos"])
    return render_template(
        "engenharia/mesa.html", torre=TORRE, tela=TORRE.tela("mesa"), alvo=alvo, meu=meu, admin=admin,
        nome_alvo=nome_alvo, pessoas=pessoas, caixa=caixa, comigo=comigo, sem_dono=sem_dono, gavetas=gavetas,
        kpis=_faixa_da_mesa(caixa, comigo, sem_dono, erro), erro_acomp=erro, erro_leitura=bool(erro),
        velha_em=datetime.fromtimestamp(lido["lido_em"], BRT).strftime("%H:%M") if lido.get("velha") else "",
        pode=pode, diags_ativos=[x for x in diags if not x["excluido"]], diag_nome={x["id"]: x["nome"] for x in diags},
        niveis=C.NIVEIS, meta=C.META_DISP, janela=C.JANELA_DIAS, h=_h, pct=_pct,
        hoje=datetime.now(BRT).date().isoformat(), piso=AC.PISO.isoformat(), est=os_falhas.estado(),
        sem_cadastro=g.get("sem_cadastro"), lido=datetime.fromtimestamp(g["em"], BRT).strftime("%H:%M"))


def _para_gravar(s: dict) -> dict:
    """O item de sinais da Confiabilidade no formato do livro (a ligação da usina vem como `ligada_por`)."""
    return {"cod": s["cod"], "usina_id": s.get("usina_id"), "usina_ligada_por": s.get("ligada_por"),
            "nivel": s.get("nivel"), "nFalha": s.get("nFalha"), "n7": s.get("n7")}


def _agora_do_livro():
    """A Confiabilidade, os acompanhamentos relidos agora e a separação das abas: a base de cada ação."""
    from ...engenharia import acompanhamento as AC
    d = _dados()["dados"]
    lido = AC.ler(forcar=True)
    acomps = AC.estado(lido["eventos"])
    return d, lido, acomps, AC.separar(d["sinais"], acomps, d.get("falhasEm") or {})


def _gaveta_de(cod: str, acomp_id: str | None = None, aviso: str = "", erro: str = "", status: int = 200,
               digitado: dict | None = None):
    """A gaveta do ativo como está no banco agora: o acompanhamento `acomp_id` (o que acabou de ser encerrado) ou o
    aberto, e os encerrados dele embaixo."""
    from ...dados.equipamento import canon
    from ...engenharia import acompanhamento as AC
    from ...engenharia import confiabilidade as C
    d, lido, acomps, sep = _agora_do_livro()
    c = canon(cod)
    pode, meu = _quem_pode()
    aberto = next((x for x in sep["aberto"] if canon(x["acomp"]["cod"]) == c), None)
    acomp = acomps.get(acomp_id) if acomp_id else (aberto or {}).get("acomp")
    base = {canon(a["cod"]): a for a in d["ativos"]}
    base.update({canon(s["cod"]): s for s in d["sinais"]})
    a = base.get(c) or {"cod": cod, "nome": cod, "usina": "", "cliente": "", "fam": "", "crit": ""}
    novas = aberto["novas"] if aberto and acomp is aberto["acomp"] else []
    anteriores = [x["acomp"] for x in sep["encerrado"] if canon(x["acomp"]["cod"]) == c
                  and (not acomp or x["acomp"]["id"] != acomp["id"])]
    gv = _montar_gaveta("g", a, acomp, novas, anteriores,
                        (d.get("falhasEm") or {}).get(c, []) if a.get("nivel") else [])
    diags = AC.diagnosticos(lido["diagnosticos"])
    erro_leitura = bool(lido.get("erro") and not lido.get("lido_em"))
    if erro_leitura and not erro:
        erro = f"Não consegui ler os acompanhamentos ({lido['erro'].split(':')[0]}). Recarregue em instantes."
    return render_template("engenharia/_gaveta.html", gv=gv, niveis=C.NIVEIS, pode=pode, meu=meu,
                           pessoas=_pessoas(pode), diags_ativos=[x for x in diags if not x["excluido"]],
                           diag_nome={x["id"]: x["nome"] for x in diags}, meta=C.META_DISP, janela=C.JANELA_DIAS,
                           h=_h, pct=_pct, hoje=datetime.now(BRT).date().isoformat(), piso=AC.PISO.isoformat(),
                           aviso=aviso, erro=erro, erro_leitura=erro_leitura, digitado=digitado or {}), status


def _acao(cod: str, fazer, aviso: str = "", acomp_id=None, form: str = ""):
    """Roda a ação e responde a gaveta. `fazer()` devolve o aviso (ou None para o de `aviso`) e pode trocar o
    acompanhamento mostrado (o encerrado) devolvendo (aviso, acomp_id). Na recusa e no banco fora, o que foi digitado
    no formulário `form` volta preenchido (revisão final: o comentário de até 2.000 letras se perdia)."""
    from ..moldura import _de_outro_site
    if _de_outro_site():
        abort(403)
    from ...engenharia import acompanhamento as AC
    digitado = dict(request.form.items(), form=form)
    try:
        r = fazer()
    except AC.Recusada as e:
        return _gaveta_de(cod, erro=str(e), digitado=digitado)
    except Exception as e:      # noqa: BLE001 — banco fora: a gaveta diz o que aconteceu
        import logging

        from ...dados import livros
        logging.exception("confiabilidade: a ação do acompanhamento em %s não gravou", cod)
        # a GravacaoErro vem da conferência DEPOIS da troca: a troca já foi feita, e repetir pode gravar duas vezes. A
        # GravacaoRecusada (a trava dos livros que só crescem, quando existir) é antes: aí nada mudou mesmo
        recusada = getattr(livros, "GravacaoRecusada", None)
        if isinstance(e, livros.GravacaoErro) and not (recusada and isinstance(e, recusada)):
            erro = ("Gravei, mas a conferência do banco não bateu: confira a lista (recarregue a página) antes de repetir, "
                    "para não gravar duas vezes.")
        else:
            erro = FALHOU_BANCO.format(type(e).__name__)
        return _gaveta_de(cod, erro=erro, digitado=digitado)
    if isinstance(r, tuple):
        aviso, acomp_id = r
    elif r:
        aviso = r
    return _gaveta_de(cod, acomp_id=acomp_id, aviso=aviso)


@bp.route("/confiabilidade/acompanhamento/pegar", methods=["POST"])
def acompanhamento_pegar():
    from ...dados.equipamento import canon
    from ...engenharia import acompanhamento as AC
    cod = request.form.get("cod", "")

    def fazer():
        pode, _ = _quem_pode()
        if not pode:              # a recusa de quem não pode vale antes de todas
            AC.pegar({"cod": cod}, session.get("usuario"), pode)
        _d, _l, acomps, sep = _agora_do_livro()
        ab = AC.aberto_de(acomps, cod)
        if ab:                    # quem chegou depois sabe com quem está (a regra 1 do desenho), mesmo de página velha
            raise AC.Recusada(f"Este ativo já está com {ab['responsavel']['nome'] or 'outra pessoa'}: recarregue a página")
        s = next((x for x in sep["sinal"] if canon(x["cod"]) == canon(cod)), None)
        if not s:
            raise AC.Recusada("Este ativo não está em Ativos com sinal agora: recarregue a página")
        AC.pegar(_para_gravar(s), session.get("usuario"), pode)
    return _acao(cod, fazer, "Agora este ativo está com você: ele saiu de Ativos com sinal e foi para Em acompanhamento.",
                 form="pegar")


@bp.route("/confiabilidade/acompanhamento/encaminhar", methods=["POST"])
def acompanhamento_encaminhar():
    from ...dados.equipamento import canon
    from ...engenharia import acompanhamento as AC
    cod, para = request.form.get("cod", ""), request.form.get("para", "")
    viu_livre = request.form.get("livre") == "1"

    def fazer():
        pode, _ = _quem_pode()
        pessoas = _pessoas(pode)
        _d, _l, _a, sep = _agora_do_livro()
        s = next((x for x in sep["sinal"] if canon(x["cod"]) == canon(cod)), None)
        ab = next((x["acomp"] for x in sep["aberto"] if canon(x["acomp"]["cod"]) == canon(cod)), None)
        aberto = ab is not None
        if not pode:
            AC.encaminhar({"cod": cod}, para, session.get("usuario"), pode, pessoas)
        if viu_livre and ab:      # a gaveta viu o ativo livre e alguém o pegou depois (revisão final)
            raise AC.Recusada(f"Este ativo já está com {ab['responsavel']['nome'] or 'outra pessoa'}: recarregue a "
                              "página para encaminhar")
        if not s and not aberto:
            raise AC.Recusada("Este ativo não está em Ativos com sinal nem em acompanhamento: recarregue a página")
        AC.encaminhar(_para_gravar(s) if s and not aberto else {"cod": cod}, para, session.get("usuario"), pode,
                      pessoas)
        nome = next((p["nome"] for p in pessoas if p["hmac"] == para), "")
        return f"Encaminhado para {nome}." if nome else "Encaminhado."
    return _acao(cod, fazer, form="encaminhar")


def _cod_do(acompanhamento_id: str) -> str:
    from ...engenharia import acompanhamento as AC
    a = AC.estado(AC.ler(forcar=True)["eventos"]).get(acompanhamento_id)
    return a["cod"] if a else ""


@bp.route("/confiabilidade/acompanhamento/<aid>/salvar", methods=["POST"])
def acompanhamento_salvar(aid):
    from ...engenharia import acompanhamento as AC
    from ..moldura import _de_outro_site
    if _de_outro_site():          # antes de qualquer leitura do banco (acabamento da revisão final)
        abort(403)
    cod = request.form.get("cod") or _cod_do(aid)
    fim = request.form.get("fim", "")

    def fazer():
        pode, _ = _quem_pode()
        ev = AC.salvar(aid, request.form.get("inicio", ""), fim, request.form.get("diagnostico", ""),
                       session.get("usuario"), pode)
        if ev["evento"] != "encerrou":
            return "Salvo."
        # encerrar com falha depois do fim faz o ativo voltar para Ativos com sinal (a regra do Levi, 18/10/2026): só
        # se ele ainda tem o sinal de 30 dias (acabamento da revisão final)
        from ...dados.equipamento import canon
        d = _dados()["dados"]
        marco = AC._depois_do_fim(AC._dia(ev["data_id_fim_analise"]))
        tem_sinal = any(canon(s["cod"]) == canon(cod) for s in d["sinais"])
        volta = tem_sinal and any(x["quando"] >= marco for x in (d.get("falhasEm") or {}).get(canon(cod), []))
        return ("Encerrado." + (" O ativo volta para Ativos com sinal: teve falha depois do fim." if volta else ""),
                aid)
    return _acao(cod, fazer, form="salvar")


@bp.route("/confiabilidade/acompanhamento/<aid>/comentar", methods=["POST"])
def acompanhamento_comentar(aid):
    from ...engenharia import acompanhamento as AC
    from ..moldura import _de_outro_site
    if _de_outro_site():
        abort(403)
    cod = request.form.get("cod") or _cod_do(aid)

    def fazer():
        pode, _ = _quem_pode()
        AC.comentar(aid, request.form.get("texto", ""), session.get("usuario"), pode)
    return _acao(cod, fazer, "Comentário salvo.", form="comentar")


def _cadastro(fazer, aviso: str):
    """As ações da aba Diagnósticos: grava, guarda o aviso (ou o erro) na sessão e volta à aba."""
    from ..moldura import _de_outro_site
    if _de_outro_site():
        abort(403)
    from ...engenharia import acompanhamento as AC
    from ...prefixo import na_raiz
    try:
        pode, _ = _quem_pode()
        fazer(pode)
        session[_AVISO_DG] = aviso
    except AC.Recusada as e:
        session[_ERRO_DG] = str(e)
    except Exception as e:      # noqa: BLE001 — banco fora: a aba diz, nada mudou
        import logging
        logging.exception("confiabilidade: o cadastro dos diagnósticos não gravou")
        session[_ERRO_DG] = FALHOU_BANCO.format(type(e).__name__)
    return redirect(na_raiz("/t/engenharia/confiabilidade?aba=diagnosticos"), code=303)


@bp.route("/confiabilidade/diagnosticos/criar", methods=["POST"])
def diagnostico_criar():
    from ...engenharia import acompanhamento as AC
    nome = " ".join(request.form.get("nome", "").split())
    return _cadastro(lambda pode: AC.criar_diagnostico(nome, request.form.get("descricao", ""),
                                                       session.get("usuario"), pode), f"Diagnóstico {nome} criado.")


@bp.route("/confiabilidade/diagnosticos/<int:did>/salvar", methods=["POST"])
def diagnostico_salvar(did):
    from ...engenharia import acompanhamento as AC
    nome = " ".join(request.form.get("nome", "").split())
    return _cadastro(lambda pode: AC.mudar_diagnostico(did, nome, request.form.get("descricao", ""),
                                                       session.get("usuario"), pode), f"Diagnóstico {nome} salvo.")


@bp.route("/confiabilidade/diagnosticos/<int:did>/excluir", methods=["POST"])
def diagnostico_excluir(did):
    from ...engenharia import acompanhamento as AC
    return _cadastro(lambda pode: AC.excluir_diagnostico(did, session.get("usuario"), pode),
                     "Diagnóstico excluído: saiu da escolha; os acompanhamentos que já o usam continuam com ele.")


# ── Quadro da equipe (06/10/2026) ───────────────────────────────────────────────────────────────────────────────────
# Levi: "uma tela que fique no setor de engenharia que agregue todas as OSs que estão abertas ou já foram fechadas ou
# que serão abertas para essas pessoas" e "FAÇA UMA TELA DINÂMICA, ESTILO KANBAN E SUPERCARDS, DEIXE ALGO BOM DE
# GERENCIAR!". A leitura está em nexus/engenharia/os_equipe.py; aqui, os supercards (por pessoa) e o quadro.
CORES_PESSOA = ("#7fb8ff", "#a3d900", "#f2b84b", "#4fd1c5", "#ff8a65", "#e88fb4", "#c7cede")
DIAS_FAIXA = 14
JANELA_CONCLUIDAS = 30
ESPERA_VERIFICACAO = 7      # dias: a OS feita esperando a verificação há mais que isso pinta o número de âmbar


def _iniciais(nome: str) -> str:
    p = [x for x in str(nome or "").split() if x]
    return (p[0][0] + (p[-1][0] if len(p) > 1 else "")).upper() if p else "?"


def supercards(oss: list[dict], equipe: list[dict], hoje) -> list[dict]:
    """Um supercard por pessoa: a carga por etapa, o que atrasou, o que fechou em 30 dias e a faixa dos próximos 14 dias
    (as OS a fazer pela data programada: o "que serão abertas")."""
    piso = (hoje - timedelta(days=JANELA_CONCLUIDAS)).isoformat()
    out = []
    for i, p in enumerate(equipe):
        minhas = [o for o in oss if o["pid"] == p["id"]]
        cont = {c: sum(1 for o in minhas if o["coluna"] == c) for c in ("fazer", "execucao", "verificacao", "concluida", "cancelada")}
        faixa = []
        for d in range(DIAS_FAIXA):
            dia = hoje + timedelta(days=d)
            n = [o for o in minhas if o["coluna"] in ("fazer", "execucao") and o["programada_iso"] == dia.isoformat()]
            faixa.append({"dia": dia.strftime("%d/%m"), "sem": "STQQSSD"[dia.weekday()], "fim_de_semana": dia.weekday() >= 5,
                          "n": len(n), "oss": ", ".join(o["os"] for o in n)})
        abertas = [o for o in minhas if o["coluna"] in ("fazer", "execucao")]
        proxima = min((o for o in abertas if o["dias"] is not None and o["dias"] >= 0), key=lambda o: o["dias"], default=None)
        out.append({"id": p["id"], "nome": p["nome"], "nome_fracttal": p.get("nome_fracttal") or p["nome"],
                    "iniciais": _iniciais(p.get("nome_fracttal") or p["nome"]), "cor": CORES_PESSOA[i % len(CORES_PESSOA)],
                    "cont": cont, "carga": cont["fazer"] + cont["execucao"] + cont["verificacao"],
                    "atrasadas": sum(1 for o in abertas if o["prazo"] == "atrasada"),
                    "vence": sum(1 for o in abertas if o["prazo"] == "vence"),
                    "fechadas30": sum(1 for o in minhas if o["coluna"] == "concluida" and (o["fim_iso"] or "") >= piso),
                    "faixa": faixa, "proxima": proxima, "total": len(minhas)})
    return out


def _dias(n: int) -> str:
    return "1 dia" if n == 1 else f"{n} dias"


def faixa_kpis(oss: list[dict], hoje, janela: int = JANELA_CONCLUIDAS) -> list[dict]:
    """A faixa de números do quadro no modelo do Acompanhamento de chamados do OS Creator (Levi, 08/10/2026: "Precisamos
    padronizar a estética ... o card de KPIS eu gostei mais do de chamados"): o rótulo em cima, o número grande colorido
    pela gravidade e, ao lado, o detalhe que diz por onde começar (a OS mais atrasada, a próxima a vencer, a que espera a
    verificação há mais tempo). As contagens são as dos supercards: a coluna e o prazo de cada OS vêm do os_equipe.

    Cada item: {rotulo, valor, grav ("critico" | "alerta" | "ok" | ""), nota: [(texto, negrito)]}. A nota vai em pedaços
    para o template pôr o nº da OS em negrito sem montar HTML aqui (o título vem do Fracttal e é escapado lá)."""
    col = {c: [o for o in oss if o["coluna"] == c] for c in ("fazer", "execucao", "verificacao", "concluida")}
    abertas = col["fazer"] + col["execucao"]
    piso = (hoje - timedelta(days=janela)).isoformat()
    atrasadas = sorted((o for o in abertas if o["prazo"] == "atrasada"), key=lambda o: (o["dias"], o["os"]))
    vencem = sorted((o for o in abertas if o["prazo"] == "vence"), key=lambda o: (o["dias"], o["os"]))
    fechadas = sorted((o for o in col["concluida"] if (o["fim_iso"] or "") >= piso), key=lambda o: o["fim_iso"], reverse=True)
    # em verificação a OS já foi feita: espera desde o fim da execução (a tarefa fechada); sem ele, a data programada
    verif = sorted(col["verificacao"], key=lambda o: (o["fim_iso"] or o["programada_iso"] or "9999", o["os"]))
    carga = len(abertas) + len(col["verificacao"])

    def os_(o):
        return (f"OS {o['os']}", True)

    k_aberto = {"rotulo": "Em aberto", "valor": carga, "grav": "",
                "nota": [(str(len(col["fazer"])), True), (" a fazer, ", False), (str(len(col["execucao"])), True),
                         (" em execução e ", False), (str(len(col["verificacao"])), True), (" em verificação", False)]
                if carga else [("nenhuma OS em aberto", False)]}
    k_atraso = {"rotulo": "Atrasadas", "valor": len(atrasadas), "grav": "critico" if atrasadas else "",
                "nota": [("a mais atrasada: ", False), os_(atrasadas[0]), (f", {_dias(-atrasadas[0]['dias'])}", False)]
                if atrasadas else [("nenhuma passou da data programada", False)]}
    if vencem:
        d = vencem[0]["dias"]
        nota_vence = [("a próxima: ", False), os_(vencem[0]),
                      (", vence " + ("hoje" if d == 0 else "amanhã" if d == 1 else f"em {_dias(d)}"), False)]
    else:
        nota_vence = [(f"nenhuma até {hoje + timedelta(days=2):%d/%m}", False)]
    k_vence = {"rotulo": "Vencem em 2 dias", "valor": len(vencem), "grav": "alerta" if vencem else "", "nota": nota_vence}
    grav_verif, nota_verif = "", [("nenhuma esperando", False)]
    if verif:
        o = verif[0]
        desde = o["fim_iso"] or o["programada_iso"]
        espera = max(0, (hoje - date.fromisoformat(desde)).days) if desde else None
        if o["fim_iso"]:
            quando = "feita hoje" if espera == 0 else "feita ontem" if espera == 1 else f"feita há {_dias(espera)}"
        else:
            quando = f"programada {o['programada'][:5]}" if o["programada"] else "sem data"
        nota_verif = [("a mais antiga: ", False), os_(o), (f", {quando}", False)]
        grav_verif = "alerta" if espera is not None and espera > ESPERA_VERIFICACAO else ""
    k_verif = {"rotulo": "Esperando verificação", "valor": len(verif), "grav": grav_verif, "nota": nota_verif}
    k_fechadas = {"rotulo": f"Fechadas em {janela} dias", "valor": len(fechadas), "grav": "ok" if fechadas else "",
                  "nota": [("a última: ", False), os_(fechadas[0]), (f", em {fechadas[0]['fim'][:5]}", False)]
                  if fechadas else [(f"nenhuma nos últimos {janela} dias", False)]}
    return [k_aberto, k_atraso, k_vence, k_verif, k_fechadas]


@bp.route("/equipe")
def equipe():
    """O clique numa OS abre o card dela do OS Creator, o mesmo do Histórico (Levi, 08/10/2026: "Ao clicar na OS quero
    que abra o mesmo card que aparece quando clicamos em uma OS no histórico do OS Creator Web ... precisamos fazer os
    setores se conversarem"). Quem muda a OS por ele volta com ?atualizar=1, e o quadro relê o Fracttal na hora."""
    from ...engenharia import os_equipe
    os_equipe.marcar_uso()          # o quadro segue relido por trás nas próximas 2 h (`os_equipe.manter_quente`)
    if request.args.get("atualizar") == "1":
        os_equipe.pedir_releitura(esperar=True, forcar=True)
    else:
        os_equipe.pedir_releitura(esperar=not os_equipe.dados()["lido"])
    d = os_equipe.dados()
    hoje = datetime.now(BRT).date()
    cards = supercards(d["os"], d["equipe"], hoje)
    cor = {c["id"]: c["cor"] for c in cards}
    ini = {c["id"]: c["iniciais"] for c in cards}          # as do supercard (pelo nome no Fracttal)
    oss = [dict(o, cor=cor.get(o["pid"], CORES_PESSOA[-1]), iniciais=ini.get(o["pid"]) or _iniciais(o["pessoa"]))
           for o in d["os"]]
    piso = (hoje - timedelta(days=JANELA_CONCLUIDAS)).isoformat()
    return render_template(
        "engenharia/equipe.html", torre=TORRE, tela=TORRE.tela("equipe"), cards=cards, oss=oss,
        kpis=faixa_kpis(oss, hoje, JANELA_CONCLUIDAS),
        faltam=d["faltam"], erro=d["erro"], colunas=os_equipe.COLUNAS,
        hoje=hoje.isoformat(), piso_concluidas=piso, janela=JANELA_CONCLUIDAS, dias_faixa=DIAS_FAIXA,
        lido=datetime.fromtimestamp(d["lido"], BRT).strftime("%H:%M") if d["lido"] else "—")

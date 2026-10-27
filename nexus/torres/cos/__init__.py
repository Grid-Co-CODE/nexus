"""Torre COS: Mesa do operador: ver, informar o cliente e acionar o campo em minutos.

Ronda padronizada, Parede de eventos e Ocorrências leem o Andamento da Ronda COS (22/10/2026, nexus/cos/andamento.py;
os prazos das Ocorrências em nexus/cos/ocorrencias.py). Religamentos e Acionamentos (26/10/2026) também: as contas em
nexus/cos/religamentos.py e nexus/cos/acionamentos.py. A Passagem de turno (26/10/2026) grava no livro nexus_cos_turno
(nexus/cos/turno.py). OS em aberto (27/10/2026) é o Panorama da Ronda COS, pelo Andamento (os filtros e as contas em
nexus/cos/os_abertas.py). Normalizações (27/10/2026) lê a API de normalizações do Andamento, de minuto em minuto pelo
cursor (nexus/cos/normalizacoes.py). As outras telas caem no placeholder da casca. Para dar vida a uma tela, crie uma view com a
mesma rota (ela vence a genérica), por exemplo:

    @bp.route("/mesa")
    def mesa():
        return render_template("cos/mesa.html")
"""
import logging
from datetime import datetime
from urllib.parse import urlencode

from flask import abort, current_app, redirect, render_template, request, session

from ...cos import acionamentos as AC
from ...cos import andamento as AND
from ...cos import normalizacoes as NO
from ...cos import ocorrencias as OC
from ...cos import os_abertas as OA
from ...cos import religamentos as RE
from ...cos import turno as TU
from ...prefixo import na_raiz
from ..modelo import Tela, Torre
from ..moldura import _de_outro_site, registrar_molduras

_log = logging.getLogger(__name__)

TORRE = Torre(
    id="cos",
    nome="COS",
    ordem=10,
    icone="broadcast",
    descricao="Mesa do operador: ver, informar o cliente e acionar o campo em minutos.",
    telas=[
        Tela("mesa", "Mesa do operador",
             "O que está aberto na minha mesa e o que falta avisar ao cliente?",
             "Tempo real da Performance + ocorrências do Nexus"),
        Tela("desempenho", "Desempenho da equipe",
             "As mesas estão dentro do MTTA e do aviso no prazo?",
             "Ocorrências do Nexus"),
        # Porta única (09/10/2026): o /cos da Plataforma de Performance (MTTA das OS), numa moldura do Nexus. A view sai do
        # mapa das telas da plataforma (nexus/performance/porta.py), pelo registrar_molduras abaixo.
        Tela("acompanhamento", "Acompanhamento COS",
             "As OS do COS estão sendo atendidas no prazo (MTTA)?",
             "Plataforma de Performance (/cos)"),
        # As duas do Andamento (22/10/2026) vêm DEPOIS do Acompanhamento de propósito: o cartão do COS na página inicial
        # leva à primeira tela pronta, e o Acompanhamento (com a porta ligada) continua sendo ela. A Ronda e a Parede
        # contam como prontas mesmo antes de a fonte ser ligada no servidor (a conta de telas_com_conteudo é pela rota).
        # 22/10/2026: a ronda é a do Andamento da Ronda COS (a fotografia de hora em hora que vai ao cliente). As nove
        # verificações da spec R04 ainda não têm de onde ler: a pergunta diz o que a tela responde hoje.
        # 22/10/2026: as Ocorrências também vêm do Andamento (o ciclo de cada uma: quando cada etapa aconteceu); o prazo
        # da spec R04 e o veredito são daqui (nexus/cos/ocorrencias.py).
        Tela("ocorrencias", "Ocorrências",
             "Cada ocorrência cumpriu as cinco etapas no prazo?",
             "Andamento da Ronda COS (registro, envios ao cliente, mudanças de estado)"),
        Tela("ronda", "Ronda padronizada",
             "A fotografia da hora saiu, e o que está aberto agora em cada usina?",
             "Andamento da Ronda COS (fotografia de hora em hora)"),
        Tela("eventos", "Parede de eventos",
             "O que aconteceu na frota nas últimas horas?",
             "Andamento da Ronda COS (eventos das ocorrências)"),
        # 26/10/2026: Religamentos e Acionamentos também leem o Andamento (o ciclo das ocorrências, com a tag da cabine e o
        # religamento de cada uma; e as UCs, os canais e os chamados à concessionária). Depois do Acompanhamento pelo
        # mesmo motivo da Ronda e da Parede. O "quem aciono" é do cadastro do Nexus (nexus/cos/acionamentos.py).
        Tela("religamentos", "Religamentos",
             "Onde o religamento remoto resolve e onde se repete na mesma cabine?",
             "Andamento da Ronda COS (as ocorrências de 30 dias, com o religamento e a cabine de cada uma)"),
        Tela("acionamentos", "Acionamentos e distribuidoras",
             "Quem aciono e qual o canal da distribuidora desta UF?",
             "Cadastro do Nexus (quem aciono) + Andamento da Ronda COS (UCs, canais e chamados à concessionária)"),
        # 26/10/2026: a passagem de turno da spec R12 ("sem registro, ela não aconteceu"), gravada no livro
        # nexus_cos_turno (nexus/cos/turno.py). Depois do Acompanhamento pelo mesmo motivo da Ronda e da Parede.
        Tela("turno", "Passagem de turno",
             "O que o próximo turno precisa saber e quem assumiu?",
             "Passagens registradas no Nexus + o que está aberto no Andamento da Ronda COS"),
        # 27/10/2026: o Panorama da Ronda COS (as OS abertas no Fracttal que o COS abriu), pelo Andamento; depois da
        # Passagem de turno, como o dono pediu.
        Tela("os-abertas", "OS em aberto",
             "Que OS o COS abriu e seguem abertas no Fracttal, e há quanto tempo?",
             "Andamento da Ronda COS (o Panorama das OS abertas no Fracttal)"),
        # 27/10/2026 (Levi: "Gostaria de inserir no COS" a API de normalizações): a hora em que cada usina voltou, pela
        # Ronda COS, ao lado da OS que segue aberta no Fracttal. Depois das OS em aberto, que é o outro lado da mesma conta.
        Tela("normalizacoes", "Normalizações",
             "Quando cada usina voltou, e a OS dela já fechou no Fracttal?",
             "Andamento da Ronda COS (as normalizações, com a hora da volta registrada pelo COS)"),
    ],
)

bp = TORRE.criar_blueprint(__name__)
registrar_molduras(bp, TORRE)

# A Parede mostra até 300 linhas: 7 dias de 3 clientes passam disso em dia agitado, e o filtro afunila.
LIMITE_EVENTOS = 300


def _url(**mudar) -> str:
    """O endereço desta tela com os filtros de agora, trocando só o que se pede (None tira o filtro)."""
    args = {k: v for k, v in request.args.items() if v}
    for k, v in mudar.items():
        if v in (None, ""):
            args.pop(k, None)
        else:
            args[k] = v
    return "?" + urlencode(args) if args else "?"


def _lido(leituras) -> str:
    """A hora da leitura mais velha em uso, em Brasília (o servidor roda em UTC)."""
    lidos = [x.lido_em for x in leituras if x.lido_em]
    return datetime.fromtimestamp(min(lidos), AND._BRT).strftime("%H:%M") if lidos else ""


@bp.route("/ronda")
def ronda():
    """Ronda padronizada (22/10/2026, o dono: "o ANDAMENTO e o RONDA COS vão ser somente base de dados pra esse NEXUS"):
    a fotografia de hora em hora do Andamento, por cliente. A regra mora lá; aqui só se mostra (nexus/cos/andamento.py)."""
    cfg = current_app.config
    fonte = AND.fonte(cfg)
    clientes, erro_clientes = AND.clientes(cfg)
    cliente = request.args.get("cliente", "")
    if cliente not in clientes:
        cliente = clientes[0] if clientes else ""
    leitura = AND.ler(cfg, cliente) if cliente else AND.Leitura("", None, erro=erro_clientes or (
        "" if not fonte.ligada else "o Andamento não informou nenhum cliente"))
    if not fonte.ligada:
        leitura.erro = ""
    return render_template(
        "cos/ronda.html", torre=TORRE, tela=TORRE.tela("ronda"), ligada=fonte.ligada, clientes=clientes,
        cliente=cliente, leitura=leitura, r=AND.ronda(leitura), lido=_lido([leitura]), url=_url)


@bp.route("/eventos")
def eventos():
    """Parede de eventos (22/10/2026): os eventos das ocorrências de todos os clientes do Andamento (nova, atualizada,
    normalizada), do mais novo para o mais velho, em janelas de 8 h, 24 h e 7 dias."""
    cfg = current_app.config
    fonte = AND.fonte(cfg)
    clientes, erro_clientes = AND.clientes(cfg)
    cliente = request.args.get("cliente", "")
    if cliente not in clientes:
        cliente = ""
    leituras = [AND.ler(cfg, c) for c in clientes]
    agora = AND.agora()
    janela = request.args.get("janela", AND.JANELA_PADRAO)
    p = AND.eventos(leituras, agora, janela, cliente=cliente, problema=request.args.get("problema", ""),
                    situacao=request.args.get("situacao", ""))
    problemas = {}
    for lt in leituras:
        if lt.dados:
            problemas.update(AND.nomes_dos_problemas(lt.dados))
    erros = [(lt.cliente, lt.erro, lt.velha) for lt in leituras if lt.erro]
    return render_template(
        "cos/eventos.html", torre=TORRE, tela=TORRE.tela("eventos"), ligada=fonte.ligada, clientes=clientes,
        cliente=cliente, erro_clientes=erro_clientes if fonte.ligada else "", erros=erros, p=p, problemas=problemas,
        situacoes=AND.SITUACOES, janelas=AND.JANELAS, problema=request.args.get("problema", ""),
        situacao=request.args.get("situacao", ""), lido=_lido(leituras), url=_url, limite=LIMITE_EVENTOS)


@bp.route("/ocorrencias")
def ocorrencias():
    """Ocorrências (22/10/2026): o ciclo de cada ocorrência registrada no período — detectada, cliente informado, campo
    acionado, normalizada, encerrada — com o prazo da spec R04. Os fatos vêm do Andamento; o veredito, de
    nexus/cos/ocorrencias.py. Só lê: agir na ocorrência é na Ronda COS (o link de cada linha)."""
    cfg = current_app.config
    fonte = AND.fonte(cfg)
    clientes, erro_clientes = AND.clientes(cfg)
    cliente = request.args.get("cliente", "")
    if cliente not in clientes:
        cliente = clientes[0] if clientes else ""
    dias = OC.dias_pedidos(request.args.get("dias"))
    leitura = AND.ler_ocorrencias(cfg, cliente, dias) if cliente else AND.Leitura("", None, erro=erro_clientes or (
        "" if not fonte.ligada else "o Andamento não informou nenhum cliente"))
    if not fonte.ligada:
        leitura.erro = ""
    situacao = request.args.get("situacao", "")
    if situacao not in OC.SITUACOES:
        situacao = ""
    return render_template(
        "cos/ocorrencias.html", torre=TORRE, tela=TORRE.tela("ocorrencias"), ligada=fonte.ligada, clientes=clientes,
        cliente=cliente, leitura=leitura, p=OC.painel(leitura, AND.agora(), situacao, fonte.url), dias=dias,
        dias_opcoes=AND.DIAS_DAS_OCORRENCIAS, situacao=situacao, situacoes=OC.SITUACOES, etapas=OC.ETAPAS,
        prazos=OC.PRAZOS, lido=_lido([leitura]), url=_url)


@bp.route("/religamentos")
def religamentos():
    """Religamentos (26/10/2026): onde o religamento remoto resolve e onde se repete na mesma cabine. As ocorrências do
    período vêm do Andamento (a rota das Ocorrências, com a tag da cabine e o religamento de cada uma); o desfecho e a
    repetição são de nexus/cos/religamentos.py. Só lê."""
    cfg = current_app.config
    fonte = AND.fonte(cfg)
    clientes, erro_clientes = AND.clientes(cfg)
    cliente = request.args.get("cliente", "")
    if cliente not in clientes:
        cliente = clientes[0] if clientes else ""
    dias = RE.dias_pedidos(request.args.get("dias"))
    leitura = AND.ler_ocorrencias(cfg, cliente, dias) if cliente else AND.Leitura("", None, erro=erro_clientes or (
        "" if not fonte.ligada else "o Andamento não informou nenhum cliente"))
    if not fonte.ligada:
        leitura.erro = ""
    ver = request.args.get("ver", "repetem")
    if ver not in RE.VER:
        ver = "repetem"
    return render_template(
        "cos/religamentos.html", torre=TORRE, tela=TORRE.tela("religamentos"), ligada=fonte.ligada, clientes=clientes,
        cliente=cliente, leitura=leitura, p=RE.painel(leitura, ver), dias=dias, dias_opcoes=RE.DIAS_OPCOES, ver=ver,
        vers=RE.VER, desfechos=RE.DESFECHOS, repete=RE.REPETE_A_PARTIR, reincidente=RE.REINCIDENTE_A_PARTIR,
        lido=_lido([leitura]), url=_url)


@bp.route("/acionamentos")
def acionamentos():
    """Acionamentos e distribuidoras (26/10/2026): quem aciono e qual o canal da distribuidora desta UF. Quem aciono é do
    cadastro do Nexus (o contato decifrado só para a tela); a UC, o canal e os chamados à concessionária, do Andamento
    (nexus/cos/acionamentos.py). Só lê."""
    cfg = current_app.config
    fonte = AND.fonte(cfg)
    clientes, erro_clientes = AND.clientes(cfg)
    leituras = [AND.ler_distribuidoras(cfg, c) for c in clientes] if fonte.ligada else []
    cliente, uf = request.args.get("cliente", ""), request.args.get("uf", "")
    busca = " ".join((request.args.get("q") or "").split())[:80]
    chave = cfg.get("NEXUS_CHAVE_CADASTRO")
    try:
        from ...cadastro.cifra import Cofre
        from ...campo import visao
        p, erro_cadastro = AC.painel(visao._Base(), Cofre(chave) if chave else None, leituras, AND.agora(), cliente, uf,
                                     busca), ""
    except Exception as e:      # noqa: BLE001 — cadastro fora: a tela diz, sem lista pela metade
        _log.exception("Acionamentos: o cadastro não foi lido")
        p, erro_cadastro = None, f"Não consegui ler o cadastro do Nexus ({type(e).__name__})"
    return render_template(
        "cos/acionamentos.html", torre=TORRE, tela=TORRE.tela("acionamentos"), ligada=fonte.ligada, p=p,
        erro_cadastro=erro_cadastro, erro_clientes=erro_clientes if fonte.ligada else "", cliente=cliente, uf=uf,
        busca=busca, com_chave=bool(chave), confianca=AC.CONFIANCA, lido=_lido(leituras), url=_url)


# ── Passagem de turno (26/10/2026) ───────────────────────────────────────────────────────────────────────────────────
_TURNO_AVISO = "cos_turno_aviso"


def _aberto_agora(cfg) -> dict | None:
    """O que está aberto no Andamento agora, por cliente (a cópia de 30 s de cada um); None sem a fonte ligada."""
    if not AND.fonte(cfg).ligada:
        return None
    clientes, erro = AND.clientes(cfg)
    a = TU.aberto_no_andamento([AND.ler(cfg, c) for c in clientes])
    a["erro_clientes"] = erro
    return a


def _turno(erro: str = "", texto: str = "", status: int = 200):
    """A tela: o turno em curso, o formulário de quem sai, a troca que quem entra assume e o histórico de 7 dias. Na
    recusa volta com o motivo e o texto digitado (o texto não cabe no cookie da sessão)."""
    cfg = current_app.config
    usuario = session.get("usuario")
    eu = TU.codigo(usuario) if usuario else None
    try:
        p, erro_livro = TU.painel(AND.agora(), eu=eu), ""
    except Exception as e:      # noqa: BLE001 — banco fora: a tela diz, sem um histórico de "sem registro" falso
        _log.exception("Passagem de turno: o livro não foi lido")
        p, erro_livro = None, f"Não consegui ler as passagens no banco ({type(e).__name__})"
    return render_template(
        "cos/turno.html", torre=TORRE, tela=TORRE.tela("turno"), p=p, erro_livro=erro_livro,
        aberto=_aberto_agora(cfg), com_login=bool((usuario or {}).get("email")), aviso=session.pop(_TURNO_AVISO, None), erro=erro, texto=texto,
        tolerancia=TU.TOLERANCIA_MIN, turnos=TU.TURNOS, texto_max=TU.TEXTO_MAX, situacoes=TU.SITUACOES), status


@bp.route("/turno")
def turno():
    """Passagem de turno (R12: "a passagem é registrada no sistema; sem registro, ela não aconteceu"): quem sai escreve o
    que o próximo turno precisa saber, quem entra diz que assumiu, e as trocas de 7 dias ficam com a situação de cada
    uma. Grava no livro nexus_cos_turno (nexus/cos/turno.py)."""
    return _turno()


@bp.route("/turno/passar", methods=["POST"])
def turno_passar():
    if _de_outro_site():
        abort(403)
    texto = request.form.get("texto") or ""
    a = _aberto_agora(current_app.config) or {}
    try:
        nova = TU.passar(session.get("usuario"), texto, AND.agora(), a.get("abertas"), a.get("criticas"))
    except TU.Recusada as e:
        return _turno(erro=str(e), texto=texto, status=422)
    except Exception as e:      # noqa: BLE001 — banco fora: o texto digitado não se perde
        _log.exception("Passagem de turno: a passagem não gravou")
        return _turno(erro=f"Não consegui gravar no banco ({type(e).__name__}). Tente de novo em instantes.",
                      texto=texto, status=503)
    troca = TU._brt(datetime.fromisoformat(nova["troca_em"]))
    session[_TURNO_AVISO] = (f"Passagem registrada na troca de {troca.strftime('%d/%m')} às {troca.strftime('%H:%M')} "
                             f"({TU.rotulo_da_troca(troca)})")
    return redirect(na_raiz("/t/cos/turno"), code=303)


@bp.route("/turno/assumir", methods=["POST"])
def turno_assumir():
    if _de_outro_site():
        abort(403)
    try:
        troca = TU._brt(datetime.fromisoformat(request.form.get("troca") or ""))
    except ValueError:
        abort(400)
    try:
        TU.assumir(session.get("usuario"), troca, AND.agora())
    except TU.Recusada as e:
        return _turno(erro=str(e), status=422)
    except Exception as e:      # noqa: BLE001 — banco fora: a tela diz, nada mudou
        _log.exception("Passagem de turno: o assumir não gravou")
        return _turno(erro=f"Não consegui gravar no banco ({type(e).__name__}). Tente de novo em instantes.",
                      status=503)
    session[_TURNO_AVISO] = f"Você assumiu o turno ({TU.rotulo_da_troca(troca)} das {troca.strftime('%H:%M')})"
    return redirect(na_raiz("/t/cos/turno"), code=303)


# ── OS em aberto (27/10/2026) ─────────────────────────────────────────────────────────────────────────────────────────
@bp.route("/os-abertas")
def os_abertas():
    """OS em aberto: o Panorama da Ronda COS, as OS abertas no Fracttal que o COS abriu, a mais antiga primeiro. O que
    entra, a situação e o alerta vêm do Andamento; os filtros e as contas, de nexus/cos/os_abertas.py. Só lê: a OS abre
    no card do Fracttal, com o login de quem clica."""
    cfg = current_app.config
    fonte = AND.fonte(cfg)
    leitura = AND.ler_os_abertas(cfg) if fonte.ligada else AND.Leitura("", None)
    a = request.args
    situacao = OA.situacao_pedida(a.get("situacao"))
    faixa = a.get("faixa", "") if a.get("faixa") in OA.FAIXAS else ""
    sem_registro = a.get("sem_registro") == "1"
    busca = " ".join((a.get("q") or "").split())[:OA.BUSCA_MAX]
    cliente, tipo = a.get("cliente", ""), a.get("tipo", "")
    p = OA.painel(leitura, AND.agora(), situacao, cliente, tipo, faixa, sem_registro, busca)
    return render_template(
        "cos/os_abertas.html", torre=TORRE, tela=TORRE.tela("os-abertas"), ligada=fonte.ligada, leitura=leitura, p=p,
        situacao=situacao, cliente=cliente, tipo=tipo, faixa=faixa, sem_registro=sem_registro, busca=busca,
        situacoes=OA.SITUACOES, faixas=OA.FAIXAS, lido=_lido([leitura]), url=_url)


# ── Normalizações (27/10/2026) ────────────────────────────────────────────────────────────────────────────────────────
@bp.route("/normalizacoes")
def normalizacoes():
    """Normalizações: a hora em que cada usina voltou, registrada pelo COS, e se a OS segue aberta no Fracttal. As
    normalizações vêm do Andamento (guardadas em memória pelo cursor, nexus/cos/normalizacoes.py); os filtros e as contas
    são daqui. Só lê: a OS abre no card do Fracttal."""
    cfg = current_app.config
    fonte = AND.fonte(cfg)
    agora = AND.agora()
    leitura = NO.ler(cfg, agora) if fonte.ligada else AND.Leitura("", None)
    a = request.args
    dias = NO.dias_pedidos(a.get("dias"))
    mes = NO.mes_pedido(a.get("mes"), agora)
    severidade = a.get("severidade", "") if a.get("severidade") in NO.SEVERIDADES else ""
    cliente, so_aberta = a.get("cliente", ""), a.get("aberta") == "1"
    p = NO.painel(leitura, agora, dias, cliente, severidade, so_aberta, mes)
    return render_template(
        "cos/normalizacoes.html", torre=TORRE, tela=TORRE.tela("normalizacoes"), ligada=fonte.ligada, leitura=leitura,
        p=p, dias=dias, mes=mes, meses=NO.meses(agora), cliente=cliente, severidade=severidade, so_aberta=so_aberta, opcoes_dias=NO.DIAS,
        severidades=NO.SEVERIDADES, lido=_lido([leitura]), url=_url)

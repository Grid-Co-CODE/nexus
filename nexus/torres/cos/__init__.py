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
import csv
import io
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import urlencode

from flask import Response, abort, current_app, jsonify, redirect, render_template, request, session

from ...auth import setor_telas as ST
from ...cadastro import setor_ids as SID
from ...cos import acionamentos as AC
from ...cos import andamento as AND
from ...cos import desempenho as DE
from ...cos import ficha as FI
from ...cos import mesa as ME
from ...cos import monitoramento as MO
from ...cos import normalizacoes as NO
from ...cos import ocorrencias as OC
from ...cos import ocorrencias_planilha as OP
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
        # Porta única (09/10/2026): o /cos da Plataforma de Performance (MTTA das OS), numa moldura do Nexus. A view sai do
        # mapa das telas da plataforma (nexus/performance/porta.py), pelo registrar_molduras abaixo.
        Tela("acompanhamento", "Acompanhamento COS",
             "As OS do COS estão sendo atendidas no prazo (MTTA)?",
             "Plataforma de Performance (/cos)"),
        # 05/11/2026: a Mesa do operador e o Desempenho da equipe (spec R04) leem o Andamento: a carteira de cada operador
        # da Ronda COS (sem e-mail: o HMAC com a chave do Nexus), a fotografia e o ciclo das ocorrências. Logo depois do
        # Acompanhamento, que segue sendo a 1ª tela pronta (o cartão do COS no Início).
        Tela("mesa", "Mesa do operador",
             "O que está aberto na minha mesa e o que falta avisar ao cliente?",
             "Andamento da Ronda COS (a carteira de cada operador, a fotografia e o ciclo das ocorrências)"),
        Tela("desempenho", "Desempenho da equipe",
             "As mesas estão dentro do MTTA e do aviso no prazo?",
             "Andamento da Ronda COS (o ciclo das ocorrências, com a hora em que o COS viu)"),
        # 09/11/2026 (o dono: "geração em kw ao vivo com a curva de cada usina atualizando constantemente, somente as que
        # tem logger e as que são sunop"): o cartão da tela de monitoramento da Ronda COS, pelo Andamento. Do setor COS sem
        # marca em Base → Acessos (Tela.do_setor), para os operadores a verem no dia em que ela entra.
        Tela("monitoramento", "Monitoramento",
             "Quanto cada usina com logger ou do SunOP está gerando agora, e como foi a curva do dia?",
             "Andamento da Ronda COS (o kW ao vivo do SCADA Grid e do SunOP, e a curva do dia)", do_setor=SID.COS),
        # As duas do Andamento (22/10/2026) vêm DEPOIS do Acompanhamento de propósito: o cartão do COS na página inicial
        # leva à primeira tela pronta, e o Acompanhamento (com a porta ligada) continua sendo ela. A Ronda e a Parede
        # contam como prontas mesmo antes de a fonte ser ligada no servidor (a conta de telas_com_conteudo é pela rota).
        # 22/10/2026: a ronda é a do Andamento da Ronda COS (a fotografia de hora em hora que vai ao cliente). As nove
        # verificações da spec R04 ainda não têm de onde ler: a pergunta diz o que a tela responde hoje.
        # 22/10/2026: as Ocorrências também vêm do Andamento (o ciclo de cada uma: quando cada etapa aconteceu); o prazo
        # da spec R04 e o veredito são daqui (nexus/cos/ocorrencias.py).
        # 12/11/2026, a reorganização do COS (o dono): a tela do prazo de cada etapa vira "Prazos da R04", e o nome
        # "Ocorrências" passa à lista das em andamento e das normalizadas (a tela `normalizacoes`). O id fica (o endereço,
        # os favoritos e as marcas de Base → Acessos são pelo id).
        Tela("ocorrencias", "Prazos da R04",
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
        # 12/11/2026: sai do menu (o dono, na reorganização do COS) e abre por dentro da Ocorrências: o status da OS de
        # cada ocorrência já está lá; quem tinha a tela marcada continua vendo
        Tela("os-abertas", "OS em aberto",
             "Que OS o COS abriu e seguem abertas no Fracttal, e há quanto tempo?",
             "Andamento da Ronda COS (o Panorama das OS abertas no Fracttal)", dentro_de="normalizacoes"),
        # 27/10/2026 (Levi: "Gostaria de inserir no COS" a API de normalizações): a hora em que cada usina voltou, pela
        # Ronda COS, ao lado da OS que segue aberta no Fracttal. Depois das OS em aberto, que é o outro lado da mesma conta.
        # 12/11/2026 (o dono, no protótipo do COS: a tela unificada "segue o padrão da tela de Normalizações"): vira
        # "Ocorrências", com as em andamento no topo da mesma lista e o filtro Situação. O id fica.
        Tela("normalizacoes", "Ocorrências",
             "Quais ocorrências seguem em andamento, quando cada usina voltou, e a OS dela já fechou no Fracttal?",
             "Andamento da Ronda COS (as ocorrências abertas agora e as normalizações, com a hora da volta registrada "
             "pelo COS)"),
    ],
)
# A ordem do menu (12/11/2026, a reorganização do COS pelo dono): o que se usa no turno (Monitoramento, Passagem de turno,
# Ronda, Parede), a consulta (Ocorrências) e os indicadores (Mesa, Desempenho, Prazos da R04, Religamentos, Acionamentos).
# O Acompanhamento segue o 1º: o cartão do COS no Início leva à 1ª tela pronta, e é ele (`test_casca_inicio`).
_ORDEM_DO_MENU = ("acompanhamento", "monitoramento", "turno", "ronda", "eventos", "normalizacoes", "mesa", "desempenho",
                  "ocorrencias", "religamentos", "acionamentos", "os-abertas")
TORRE.telas.sort(key=lambda t: _ORDEM_DO_MENU.index(t.id) if t.id in _ORDEM_DO_MENU else len(_ORDEM_DO_MENU))

bp = TORRE.criar_blueprint(__name__)
registrar_molduras(bp, TORRE)
_AQUECIDO = {"feito": False}


@bp.before_request
def _aquecer_uma_vez():
    """No 1º pedido a uma tela do COS, as cópias das leituras do Andamento enchem por trás (`AND.aquecer`, 12/11/2026):
    a tela seguinte já abre com a cópia, sem esperar a Ronda COS. Uma vez por processo; no registro do blueprint não dá
    (lá a config dos testes ainda não tem o TESTING, e a thread subiria nos testes). Nos testes, `aquecer` não faz nada."""
    if not _AQUECIDO["feito"]:
        _AQUECIDO["feito"] = True
        AND.aquecer(current_app.config)

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
    nexus/cos/ocorrencias.py. Só lê: agir na ocorrência é na Ronda COS (o link de cada linha).

    11/11/2026 (pedido da Ana Barros): `?cliente=todos` junta os clientes numa tabela só, cada linha diz o que aconteceu
    (causa, ação, informe, descrição e notas, como na tela Normalizações) e `?formato=csv` baixa a lista com os filtros."""
    cfg = current_app.config
    fonte = AND.fonte(cfg)
    clientes, erro_clientes = AND.clientes(cfg)
    cliente = request.args.get("cliente", "")
    todos = cliente == OC.TODOS and len(clientes) > 1
    if not todos and cliente not in clientes:
        cliente = clientes[0] if clientes else ""
    dias = OC.dias_pedidos(request.args.get("dias"))
    if todos:
        # Uma leitura por cliente, cada uma com o próprio cache de 60 s (a mesma da aba de cada um), pedidas JUNTAS
        # (11/11/2026): uma depois da outra, a página esperava a soma das sete — a Thopen de 30 dias sozinha tem ~1 MB.
        with ThreadPoolExecutor(max_workers=min(8, len(clientes))) as ex:
            leituras = list(ex.map(lambda c: AND.ler_ocorrencias(cfg, c, dias), clientes))
        erros = [f"{x.cliente}: {x.erro}" for x in leituras if x.erro]
        leitura = AND.Leitura(OC.TODOS, None, erro="; ".join(erros), velha=any(x.velha for x in leituras))
    else:
        leitura = AND.Leitura("", None, erro=erro_clientes or (
            "" if not fonte.ligada else "o Andamento não informou nenhum cliente"))
        if cliente:
            leitura = AND.ler_ocorrencias(cfg, cliente, dias)
        leituras = [leitura]
    if not fonte.ligada:
        leitura.erro = ""
    situacao = request.args.get("situacao", "")
    if situacao not in OC.SITUACOES:
        situacao = ""
    # Os filtros da tela Normalizações (11/11/2026): falha, usina, criado por, técnico, status no Fracttal e a lupa.
    filtros = OC.filtros_pedidos(request.args)
    p = OC.painel(leituras if todos else leitura, AND.agora(), situacao, fonte.url, filtros)
    if request.args.get("formato") == "csv":
        if not p:
            abort(404)
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(OC.CSV_COLUNAS)
        w.writerows([[_celula_csv(v) for v in linha] for linha in OC.csv_linhas(p)])
        # com o BOM, o Excel abre os acentos certos (o mesmo da tela Normalizações)
        resp = Response(BOM + buf.getvalue(), mimetype="text/csv; charset=utf-8")
        nome = "todos" if todos else "".join(ch if ch.isalnum() else "-" for ch in cliente).strip("-").lower()
        resp.headers["Content-Disposition"] = f'attachment; filename="ocorrencias-{nome}-{dias}d.csv"'
        resp.headers["Cache-Control"] = "private, no-store"
        return resp
    if request.args.get("formato") == "xlsx":
        # O Excel (11/11/2026, o dono: "melhora a exportação do CSV, está muito feia") — nexus/cos/ocorrencias_planilha.py
        if not p:
            abort(404)
        nome = "todos" if todos else "".join(ch if ch.isalnum() else "-" for ch in cliente).strip("-").lower()
        resp = Response(OP.gerar(p, titulo="Ocorrências do COS", topo=_topo_da_planilha(p, todos, cliente, dias,
                                                                                         situacao, filtros)),
                        mimetype=OP.MIME)
        resp.headers["Content-Disposition"] = f'attachment; filename="ocorrencias-{nome}-{dias}d.xlsx"'
        resp.headers["Cache-Control"] = "private, no-store"
        return resp
    return render_template(
        "cos/ocorrencias.html", torre=TORRE, tela=TORRE.tela("ocorrencias"), ligada=fonte.ligada, clientes=clientes,
        cliente=OC.TODOS if todos else cliente, todos=todos, leitura=leitura, p=p, dias=dias,
        dias_opcoes=AND.DIAS_DAS_OCORRENCIAS, situacao=situacao, situacoes=OC.SITUACOES, etapas=OC.ETAPAS,
        prazos=OC.PRAZOS, lido=_lido(leituras), url=_url, o_que_aconteceu=OC.o_que_aconteceu,
        status_da_os=OC.status_da_os, filtros=filtros, status_filtro=OC.STATUS_FILTRO)


def _topo_da_planilha(p, todos: bool, cliente: str, dias: int, situacao: str, filtros: dict) -> list[str]:
    """As linhas de cima da planilha das Ocorrências: quando, o recorte (o mesmo da tela) e de onde os prazos contam."""
    rotulos = {"falha": "Falha", "usina": "Usina", "criado_por": "Criado por", "tecnico": "Técnico",
               "status": "Status Fracttal", "q": "Busca"}
    ativos = [f"{rotulos[k]}: {OC.STATUS_FILTRO.get(v, v) if k == 'status' else v}" for k, v in filtros.items() if v]
    if situacao:
        ativos.insert(0, f"Situação: {OC.SITUACOES[situacao]}")
    periodo = "último dia" if dias == 1 else f"últimos {dias} dias"
    return [
        f"Gerada em {AND.agora():%d/%m/%Y %H:%M} · {periodo}"
        + (f" (registradas desde {p.desde:%d/%m/%Y %H:%M})" if p.desde else ""),
        f"Cliente: {'todos os clientes' if todos else cliente}",
        "Filtros: " + (" · ".join(ativos) if ativos else "nenhum"),
        f"Os prazos contam do {OC.RELOGIO}. {len(p.itens)} ocorrência{'s' if len(p.itens) != 1 else ''}.",
    ]


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
# O BOM do UTF-8 na frente do CSV: com ele, o Excel abre os acentos certos (escrito pelo código, e não como o caractere
# invisível no meio do texto, que um editor pode perder sem ninguém ver).
BOM = "\ufeff"


def _celula_csv(v):
    """O texto que o Excel leria como fórmula (=, +, -, @ no começo) vai com um apóstrofo na frente."""
    t = "" if v is None else str(v)
    return "'" + t if t[:1] in ("=", "+", "-", "@") else t


def _andamento_cos(cfg, agora):
    """As ocorrências em andamento de todos os clientes, para a tela Ocorrências: a fotografia de cada um (o que está aberto
    agora, de qualquer data), o ciclo de 7 dias (o detalhe: início, tipo, proteções, notas, quem abriu a OS) e o Panorama
    das OS abertas (o status no Fracttal). → (itens, leituras, erros). O cliente cuja fotografia não veio fica fora e é
    dito na tela; sem o ciclo ou o Panorama a linha só perde o detalhe. As leituras são as cópias das outras telas do COS
    (a fotografia é a da Ronda, o ciclo o da Prazos da R04), então abrir esta tela quase nunca vai à Ronda COS."""
    lista, erro_clientes = AND.clientes(cfg)
    fotos = [(c, AND.ler(cfg, c)) for c in lista]
    ciclos = [AND.ler_ocorrencias(cfg, c, 7) for c in lista]
    panorama = AND.ler_os_abertas(cfg)
    ocorrencias = {str(o.get("registro")): o for x in ciclos if x.dados for o in x.dados.get("ocorrencias") or []
                   if isinstance(o, dict)}
    itens = NO.andamento([(c, x.dados) for c, x in fotos if x.dados], ocorrencias, panorama.dados, agora)
    erros = ([f"a lista de clientes: {erro_clientes}"] if erro_clientes else [])
    erros += [f"{c}: {x.erro}" for c, x in fotos if x.erro and not x.dados]
    return itens, [x for _c, x in fotos] + ciclos + [panorama], erros


@bp.route("/normalizacoes")
def normalizacoes():
    """Ocorrências (até 12/11/2026, Normalizações): no mês corrente, as em andamento no topo e as normalizadas do mês, com o
    filtro Situação; nos meses de antes, só as normalizadas (o mês é o da volta). A hora em que cada usina voltou,
    registrada pelo COS, e se a OS segue aberta no Fracttal. As normalizações vêm do Andamento (guardadas em memória pelo
    cursor, nexus/cos/normalizacoes.py); os filtros e as contas são daqui. Só lê: a OS abre no card do Fracttal.
    `?formato=csv` baixa a lista com os filtros."""
    cfg = current_app.config
    fonte = AND.fonte(cfg)
    agora = AND.agora()
    leitura = NO.ler(cfg, agora) if fonte.ligada else AND.Leitura("", None)
    a = request.args
    mes = NO.mes_pedido(a.get("mes"), agora)
    status = a.get("status", "") if a.get("status") in NO.STATUS_FILTRO else ""
    situacao = a.get("situacao", "") if a.get("situacao") in NO.SITUACAO_FILTRO else ""
    cliente, usina = a.get("cliente", ""), a.get("usina", "")
    operador, tecnico, falha = a.get("criado_por", ""), a.get("tecnico", ""), a.get("falha", "")
    busca = " ".join((a.get("q") or "").split())[:NO.BUSCA_MAX]
    andamento, lidas_andamento, erros_andamento = None, [], []
    if fonte.ligada and mes == NO.meses(agora)[0][0]:
        andamento, lidas_andamento, erros_andamento = _andamento_cos(cfg, agora)
    p = NO.painel(leitura, agora, mes, cliente, usina, status, busca, operador, tecnico, falha, situacao, andamento)
    if a.get("formato") == "csv":
        if not p:
            abort(404)
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(NO.CSV_COLUNAS)
        w.writerows([[_celula_csv(v) for v in linha] for linha in NO.csv_linhas(p)])
        # com o BOM, o Excel abre os acentos certos
        resp = Response(BOM + buf.getvalue(), mimetype="text/csv; charset=utf-8")
        resp.headers["Content-Disposition"] = f'attachment; filename="ocorrencias-{mes}.csv"'
        resp.headers["Cache-Control"] = "private, no-store"
        return resp
    return render_template(
        "cos/normalizacoes.html", torre=TORRE, tela=TORRE.tela("normalizacoes"), ligada=fonte.ligada, leitura=leitura,
        p=p, mes=mes, meses=NO.meses(agora), cliente=cliente, usina=usina, status=status, busca=busca,
        operador=operador, tecnico=tecnico, falha=falha, situacao=situacao, situacao_filtro=NO.SITUACAO_FILTRO,
        erros_andamento=erros_andamento, status_filtro=NO.STATUS_FILTRO, lido=_lido([leitura, *lidas_andamento]),
        url=_url)


# ── Mesa do operador e Desempenho da equipe (05/11/2026) ─────────────────────────────────────────────────────────────
def _carteiras(cfg, fonte):
    return AND.ler_carteiras(cfg) if fonte.ligada else AND.Leitura("", None)


@bp.route("/mesa")
def mesa():
    """Mesa do operador (spec R04: "cada operador tem uma carteira de clientes, e o líder enxerga todas"): o que está
    aberto nos clientes da carteira de quem entrou (a da Ronda COS, pelo HMAC do e-mail) e o que falta avisar ao cliente
    ou acionar o campo, com os prazos da tela Ocorrências. Sem carteira, todas as mesas. Só lê (nexus/cos/mesa.py)."""
    cfg = current_app.config
    fonte = AND.fonte(cfg)
    clientes, erro_clientes = AND.clientes(cfg)
    carteiras = _carteiras(cfg, fonte)
    email = (session.get("usuario") or {}).get("email") or ""
    m = ME.escolher(email, fonte.chave, carteiras, clientes, request.args.get("mesa", ""))
    fotos = [AND.ler(cfg, c) for c in m.clientes] if fonte.ligada else []
    ciclos = [AND.ler_ocorrencias(cfg, c, ME.DIAS_DA_MESA) for c in m.clientes] if fonte.ligada else []
    p = ME.painel(fotos, ciclos, AND.agora(), fonte.url) if fonte.ligada and m.clientes else None
    return render_template(
        "cos/mesa.html", torre=TORRE, tela=TORRE.tela("mesa"), ligada=fonte.ligada, mesa=m, p=p,
        erro_clientes=erro_clientes if fonte.ligada else "", ver=request.args.get("mesa", ""), prazos=OC.PRAZOS,
        dias=ME.DIAS_DA_MESA,
        lido=_lido(fotos + ciclos), url=_url)


@bp.route("/desempenho")
def desempenho():
    """Desempenho da equipe (spec R04: "MTTA, informado no prazo e religamento remoto"): por cliente e por turno, sem
    nome de operador, e as mesas como os conjuntos de clientes das carteiras. MTTA até a hora em que o COS viu. Só lê
    (nexus/cos/desempenho.py)."""
    cfg = current_app.config
    fonte = AND.fonte(cfg)
    clientes, erro_clientes = AND.clientes(cfg)
    dias = DE.dias_pedidos(request.args.get("dias"))
    leituras = [AND.ler_ocorrencias(cfg, c, dias) for c in clientes] if fonte.ligada else []
    carteiras = _carteiras(cfg, fonte)
    email = (session.get("usuario") or {}).get("email") or ""
    minha, _fora = ME.carteira_de(email, carteiras, fonte.chave)
    p = DE.painel(leituras, AND.agora(), ME.mesas(carteiras, clientes), minha) if fonte.ligada else None
    return render_template(
        "cos/desempenho.html", torre=TORRE, tela=TORRE.tela("desempenho"), ligada=fonte.ligada, p=p, dias=dias,
        dias_opcoes=DE.DIAS_OPCOES, turnos=TU.TURNOS, prazos=OC.PRAZOS, carteiras=carteiras,
        erro_clientes=erro_clientes if fonte.ligada else "", lido=_lido(leituras), url=_url)


# ── Ficha da usina (09/11/2026) ──────────────────────────────────────────────────────────────────────────────────────
def _ve(tela_id: str) -> bool:
    """A pessoa abre esta tela do COS? Cada bloco da ficha segue a marca da tela dona (Base → Acessos): a ficha abre
    para quem tem ao menos uma tela do COS (setor_telas.pode), e o "quem aciono", com os telefones, só para quem
    abre Acionamentos. Ninguém vê na ficha o que a própria tela não lhe mostraria."""
    a = ST.acesso()
    return bool(a["tudo"] or ST.chave(TORRE.id, tela_id) in a["telas"])


@bp.route("/usina")
@bp.route("/usina/<codigo>")
def usina(codigo: str = ""):
    """A ficha da usina (nexus/cos/ficha.py): tudo o que as telas do COS sabem de UMA usina, numa página. O nome da usina
    em cada tela do COS leva aqui. Não é tela do menu (não tem marca própria): abre para quem tem ao menos uma tela do
    COS. Sem código, ou com um código que o Andamento não tem, a lista de usinas com a busca. Só lê."""
    cfg = current_app.config
    fonte = AND.fonte(cfg)
    clientes, erro_clientes = AND.clientes(cfg)
    fotos = [AND.ler(cfg, c) for c in clientes] if fonte.ligada else []
    busca = " ".join((request.args.get("q") or "").split())[:FI.BUSCA_MAX]
    foto, u = FI.achar(fotos, codigo) if codigo else (None, None)
    comum = dict(torre=TORRE, ligada=fonte.ligada, erro_clientes=erro_clientes if fonte.ligada else "",
                 erros=[(lt.cliente, lt.erro, lt.velha) for lt in fotos if lt.erro], lido=_lido(fotos))
    if u is None:
        return render_template("cos/usinas.html", usinas=FI.lista(fotos, busca), busca=busca, pedido=codigo,
                               **comum), (404 if codigo and fonte.ligada and any(lt.dados for lt in fotos) else 200)
    agora = AND.agora()
    ve = {t: _ve(t) for t in ("ronda", "ocorrencias", "religamentos", "eventos", "os-abertas", "normalizacoes",
                              "acionamentos")}
    ciclo = AND.ler_ocorrencias(cfg, foto.cliente, FI.DIAS_DO_CICLO) \
        if ve["ocorrencias"] or ve["religamentos"] or ve["ronda"] else None
    f = FI.painel(foto, u, ciclo, AND.ler_os_abertas(cfg) if ve["os-abertas"] else None,
                  NO.ler(cfg, agora) if ve["normalizacoes"] else None, agora, fonte.url)
    acionar, erro_cadastro = None, ""
    chave = cfg.get("NEXUS_CHAVE_CADASTRO")
    if ve["acionamentos"]:
        try:
            from ...cadastro.cifra import Cofre
            from ...campo import visao
            acionar = FI.acionar(visao._Base(), Cofre(chave) if chave else None,
                                 AND.ler_distribuidoras(cfg, foto.cliente), agora, u.get("nome"), u.get("codigo"))
        except Exception as e:      # noqa: BLE001 — cadastro fora: o bloco diz, a ficha segue
            _log.exception("Ficha da usina: o cadastro não foi lido")
            erro_cadastro = f"Não consegui ler o cadastro do Nexus ({type(e).__name__})"
    return render_template(
        "cos/usina.html", f=f, ve=ve, acionar=acionar, erro_cadastro=erro_cadastro, com_chave=bool(chave),
        confianca=AC.CONFIANCA, prazos=OC.PRAZOS, etapas=OC.ETAPAS, desfechos=RE.DESFECHOS,
        dias=FI.DIAS_DO_CICLO, agora=agora, **comum)


# ── Monitoramento (09/11/2026) ───────────────────────────────────────────────────────────────────────────────────────
def _console_da_ronda(fonte) -> str:
    """O Console da Ronda COS (o link "Console" da janela dos inversores), no servidor do Andamento."""
    return OC.link_da_plataforma(fonte.url, "-").split("?", 1)[0] if fonte.ligada else ""


def _inversores_abertos(cfg) -> dict:
    """As ocorrências abertas que citam um inversor, pelas fotografias de cada cliente (as cópias da Ronda padronizada)."""
    lista, _erro = AND.clientes(cfg)
    return MO.abertas_de_inversor([x.dados for x in (AND.ler(cfg, c) for c in lista) if x.dados])


def _url_da_pagina(**mudar) -> str:
    """O `_url` sem o `parcial`: o corpo pedido pelo JavaScript leva os links da página, e não o do pedaço."""
    return _url(parcial=None, **mudar)


@bp.route("/monitoramento")
def monitoramento():
    """Monitoramento: a geração em kW ao vivo e a curva do dia de cada usina com logger (SCADA Grid) e do SunOP, o cartão
    da tela de monitoramento da Ronda COS, pelo Andamento (nexus/cos/monitoramento.py). Só lê. `?parcial=1` devolve só o
    corpo, em JSON, para a página se atualizar sozinha a cada 30 s (static/cos/monitoramento.js)."""
    cfg = current_app.config
    fonte = AND.fonte(cfg)
    a = request.args
    grupo = a.get("situacao", "") if a.get("situacao") in (*MO.GRUPOS, "velhas") else ""
    cliente = a.get("cliente", "")
    busca = " ".join((a.get("q") or "").split())[:MO.BUSCA_MAX]
    # o videowall (?tv=1, 09/11/2026; o dono: "preciso de uma tela de monitoramento adequada pra videowall"): a mesma
    # leitura e a mesma conta, sem a casca, na ordem fixa e só com o cliente (cada tela da parede pode ter o seu)
    tv = a.get("tv") == "1"
    escala = MO.escala_pedida(a.get("escala"))
    if tv:
        grupo, busca = "", ""
    geracao = AND.ler_geracao(cfg) if fonte.ligada else AND.Leitura("", None)
    curvas = AND.ler_curvas(cfg) if fonte.ligada else AND.Leitura("", None)
    agora = AND.agora()
    p = MO.painel(geracao, curvas, agora, cliente, grupo, busca, fixa=tv)
    lido = _lido([x for x in (geracao,) if x.dados])
    ctx = dict(torre=TORRE, tela=TORRE.tela("monitoramento"), ligada=fonte.ligada, geracao=geracao, curvas=curvas, p=p,
               cliente=cliente, grupo=grupo, busca=busca, grupos=MO.GRUPOS, kw_txt=MO.kw_txt, largura=MO.LARGURA,
               altura=MO.ALTURA, curva_de=MO.CURVA_DE_H, curva_ate=MO.CURVA_ATE_H, passo=AND.PASSO_DAS_CURVAS_MIN,
               lido=lido, url=_url_da_pagina, agora=agora, parede=MO.parede(p) if p else None,
               anormal=MO.anormal, escala=escala,
               # 12/11/2026, os inversores de cada usina ao clicar no cartão (cos/_inversores.html): o navegador lê a API
               # da Ronda COS direto, com o login da pessoa. Sem o endereço (NEXUS_COS_API_URL), a janela não entra e o
               # cartão não é botão. As ocorrências abertas de inversor só se leem quando a janela entra.
               cos_api=AND.api_da_ronda(cfg), cos_console=_console_da_ronda(fonte),
               cos_inversores_abertos=lambda: _inversores_abertos(cfg) if fonte.ligada else {})
    corpo = "cos/_monitoramento_tv_corpo.html" if tv else "cos/_monitoramento_corpo.html"
    if a.get("parcial") == "1":
        resp = jsonify(html=render_template(corpo, **ctx), lido=lido)
        resp.headers["Cache-Control"] = "private, no-store"
        return resp
    return render_template("cos/monitoramento_tv.html" if tv else "cos/monitoramento.html", **ctx)

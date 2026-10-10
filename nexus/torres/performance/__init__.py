"""Torre Performance: Quanto gerou, o que caiu e qual a causa provável.

Porta única (09/10/2026; Levi: "a partir de segunda quero o Nexus como link principal; o Nexus será o centro de tudo,
precisamos trazer o tempo real de performance painel para o Nexus"): as telas da Plataforma de Performance abrem aqui
numa moldura, uma por item do mapa (`nexus/performance/porta.py`; as views saem de `registrar_molduras`, em
`nexus/torres/moldura.py`). Clima e risco e Mapa de risco são telas do próprio Nexus.
"""
from datetime import datetime

from flask import Response, current_app, jsonify, render_template, request

from ...performance import ponte
from ...performance.clima import fontes as F
from ...prefixo import na_raiz
from ..modelo import Tela, Torre
from ..moldura import registrar_molduras

TORRE = Torre(
    id="performance",
    nome="Performance",
    ordem=30,
    icone="chart-line-up",
    descricao="Quanto gerou, o que caiu e qual a causa provável.",
    telas=[
        # As telas da Plataforma de Performance (porta única, 09/10/2026): cada uma é uma moldura com a tela da plataforma,
        # na ordem do mapa (nexus/performance/porta.py). Os ids que já existiam no menu não mudam (viram endereço).
        Tela("tempo-real", "Tempo real",
             "O que está fora do normal agora na frota?",
             "Plataforma de Performance, ao vivo"),
        Tela("noc", "Painel NOC",
             "Como está a carteira inteira de relance?",
             "Plataforma de Performance"),
        Tela("diagnostico", "Diagnóstico",
             "Qual anomalia é falha real e qual é clima, e virou OS?",
             "Plataforma de Performance + Fracttal, por usina"),
        Tela("strings-trackers", "Strings e trackers",
             "Quais strings e trackers estão perdendo energia?",
             "Plataforma de Performance"),
        Tela("gerencial", "Visão gerencial",
             "O mês fecha dentro da meta de PR e geração?",
             "Plataforma de Performance (BD_Performance e BD_Thopen)"),
        Tela("disponibilidade", "Disponibilidade",
             "Quanto tempo cada usina ficou disponível no mês, e o que a parou?",
             "Plataforma de Performance (antes só pelo Gerencial)"),
        Tela("relatorio", "Criador de relatório",
             "Como monto o relatório do cliente com os números certos?",
             "Plataforma de Performance"),
        Tela("relatorio-semanal", "Relatório semanal",
             "Como foi a semana de cada usina no relatório do cliente?",
             "Plataforma de Performance (antes só pelo Criador de relatório)"),
        Tela("gemeo", "Gêmeo digital",
             "Quanto a usina deveria ter gerado com o sol que teve?",
             "Gêmeo digital, pela Plataforma de Performance"),
        Tela("historico-plataforma", "Histórico da plataforma",
             "Como cada usina da API PV andou, dia a dia?",
             "Plataforma de Performance"),
        Tela("monitor-ronda", "Monitor da ronda",
             "A ronda dos trackers saiu em cada horário, e onde falhou?",
             "Plataforma de Performance"),
        # O nome de cada fonte por extenso, de fontes.NOMES (Levi, 09/10/2026: "Quero as fontes por extenso também, não só sigla")
        Tela("clima", "Clima e risco",
             f"Onde há aviso do {F.extenso('inmet')}, foco de queimada ou risco de fogo perto das usinas?",
             f"avisos do {F.extenso('inmet')}; focos e risco de fogo do {F.extenso('inpe')}; cruzados com as coordenadas do "
             "cadastro; só leitura"),
        # O id tem barra de propósito: o endereço é /t/performance/clima/mapa, filho da lista (o placeholder `/<tela_id>` não
        # casa com barra, e a view própria é a única que responde ali).
        Tela("clima/mapa", "Mapa de risco",
             "Onde, no mapa do Brasil, estão as usinas que pedem ação por aviso, foco ou risco de fogo?",
             f"contorno dos estados do {F.extenso('ibge')}; avisos do {F.extenso('inmet')}; focos e risco de fogo do "
             f"{F.extenso('inpe')}; com a posição das usinas do cadastro; só leitura"),
    ],
)

bp = TORRE.criar_blueprint(__name__)


# Tempo real (04/10/2026): a Entrada e o Monitoramento da própria plataforma, só leitura, pela ponte. Levi: "tudo da
# plataforma, só leitura", "em paralelo por enquanto". A plataforma segue sendo o motor; o Nexus não pede nada a mais
# às fontes. A regra mora em nexus/performance/ponte.py.
def _config_ponte():
    url = current_app.config.get("NEXUS_PLATAFORMA_URL")
    token = current_app.config.get("NEXUS_PLATAFORMA_TOKEN")
    falta = [n for n, v in (("NEXUS_PLATAFORMA_URL", url), ("NEXUS_PLATAFORMA_TOKEN", token)) if not v]
    return url, token, falta


def _tempo_real_pela_ponte(motivo: str):
    """A reserva do Tempo real com a porta desligada: a ponte de 04/10, como ela funcionava (nada afeta o que funciona
    hoje, spec 10). Com a NEXUS_SSO_CHAVE o item abre a moldura e a ponte sai do menu; a rota dela (/plataforma/...)
    fica no código até a Operação em tempo real entrar. Sem a ponte configurada, None: a tela diz que não está ligada."""
    url, _token, falta = _config_ponte()
    if falta:
        return None
    return render_template("performance/tempo_real.html", torre=TORRE, tela=TORRE.tela("tempo-real"),
                           prefixo=ponte.PREFIXO, plataforma=url, falta=falta, porta_motivo=motivo)


# As molduras das telas da plataforma (uma view por item do mapa); o Tempo real cai na ponte enquanto a porta não liga.
registrar_molduras(bp, TORRE, reserva={"tempo-real": _tempo_real_pela_ponte})


_TITULO_PADRAO = "Plataforma de Performance sem resposta"
# Fora da máquina local, http levaria a chave de leitura em texto puro pela rede.
_LOCAL = ("localhost", "127.0.0.1", "::1")


def _erro(texto: str, titulo: str = _TITULO_PADRAO, status: int = 502) -> Response:
    hora = datetime.now().strftime("%H:%M")
    html = render_template("performance/ponte_erro.html", texto=texto, hora=hora, titulo=titulo)
    return Response(html, status=status, mimetype="text/html")


def _url_invalida(url: str) -> bool:
    # A mesma leitura do salto da ponte: barra invertida, espaço ou controle na URL configurada, ou uma URL que o
    # `requests` não entende como http(s), é recusada. Com o `urlsplit`, "http://evil.com", barra invertida,
    # "@localhost:5050" parecia localhost e passava pela regra do http, mas o `requests` conectava em evil.com, em texto
    # puro e com a chave (revisão, 04/10/2026).
    try:
        ponte.origem_configurada(url)
    except ValueError:
        return True
    return False


def _http_fora_da_maquina_local(url: str) -> bool:
    # Esquema e host vêm da URL como o `requests` a vai usar (`origem_configurada`), e não do `urlsplit`; chame depois de
    # `_url_invalida`. O host de IPv6 já vem sem colchetes ("::1").
    esquema, host, _porta = ponte.origem_configurada(url)
    return esquema == "http" and host not in _LOCAL


def _confirmou_a_chave(r) -> bool:
    # Plataforma sem NEXUS_LEITURA_TOKEN (aberta) ignora a chave e deixa passar até gravação: só a que a cumpre devolve
    # `X-Nexus-Leitura-Ok: 1`. Sem ele, nada é mostrado (falha fechada). Nome de cabeçalho não tem caixa fixa.
    return {str(k).lower(): v for k, v in r.headers.items()}.get("x-nexus-leitura-ok") == "1"


@bp.route("/plataforma/<path:caminho>", methods=["GET", "HEAD", "POST"])
def plataforma(caminho: str):
    url, token, falta = _config_ponte()
    if falta:
        return _erro("A ponte não está configurada: falta " + " e ".join(falta) + " no .env do Nexus.",
                     titulo="Ponte não configurada")
    if _url_invalida(url):
        return _erro("NEXUS_PLATAFORMA_URL é inválida: use https://servidor[:porta], sem barra invertida, espaço ou "
                     "caractere de controle.", titulo="Ponte não configurada")
    if _http_fora_da_maquina_local(url):
        return _erro("NEXUS_PLATAFORMA_URL tem de ser https fora da máquina local: a chave iria sem criptografia.",
                     titulo="Ponte não configurada")
    # A barra inicial é obrigatória: o <path:> chega sem ela, e "@evil.com/x" colado em "http://plat:5050" viraria
    # usuário "plat" no servidor evil.com, levando a chave de leitura para fora (revisão da Tarefa 8).
    c = "/" + caminho
    # O Flask decodifica %3F e %23 dentro do <path:>: "/api/x%3Fforce=1%26run=1" chegaria aqui como "api/x?force=1&run=1"
    # e iria à plataforma como query de verdade, por fora do filtro do montar_pedido (que só limpa a query real) e
    # com o POST de consulta passando no pode_passar mesmo com a query colada. Caminho não leva "?" nem "#".
    if "?" in c or "#" in c:
        return jsonify({"ok": False, "error": "caminho inválido"}), 400
    if not ponte.pode_passar(request.method, c):
        return jsonify({"ok": False, "error": "somente leitura (Nexus)"}), 403
    if ponte.fora_por_api_pv(c):
        return jsonify({"ok": False, "error": ponte.AVISO_API_PV}), 403
    # o caminho da ponte como o navegador o vê (com o prefixo em que o Nexus roda): a plataforma escreve os links com ele
    prefixo = na_raiz(ponte.PREFIXO)
    pedido = ponte.montar_pedido(url, token, request.method, c, list(request.args.items(multi=True)),
                                 request.get_data() if request.method == "POST" else None, request.content_type,
                                 prefixo=prefixo)
    try:
        r = ponte.enviar(**pedido)
    except ponte.Ocupada:
        return _erro("A ponte está ocupada com outros pedidos à plataforma. Tente de novo em instantes.",
                     titulo="Ponte ocupada", status=503)
    except ponte.RedirecionamentoRecusado as e:
        # O motivo vem da exceção (outro servidor, redirecionamentos demais ou endereço inválido): antes a tela dizia
        # sempre "outro servidor", e quem lia ia procurar a causa errada. É texto fixo da ponte, nunca a Location.
        return _erro(f"A ponte não seguiu o redirecionamento da plataforma ({e.motivo}); a chave de leitura não sai do "
                     "servidor configurado.", titulo="Redirecionamento recusado")
    except ponte.ForaDoAr:
        return _erro(f"Plataforma de Performance sem resposta em {ponte.TEMPO_LIMITE_S} s.")
    destino = {str(k).lower(): v for k, v in r.headers.items()}.get("location", "")
    # 401 é a chave errada; 3xx para /login é a plataforma sem sessão e sem a chave valendo (a ponte não o segue)
    if r.status_code == 401 or (300 <= r.status_code < 400 and ponte.vai_para_login(destino)):
        return _erro("A plataforma recusou a chave de leitura do Nexus. Confira NEXUS_PLATAFORMA_TOKEN no .env do "
                     "Nexus e NEXUS_LEITURA_TOKEN na plataforma.", titulo="A plataforma recusou a chave")
    if 200 <= r.status_code < 300 and not _confirmou_a_chave(r):
        return _erro("A plataforma não confirmou a chave de leitura: ela pode estar aberta sem NEXUS_LEITURA_TOKEN. "
                     "Nada foi mostrado.", titulo="Plataforma não confirmou a chave")
    status, cab, corpo = ponte.ajustar_resposta(r.status_code, dict(r.headers), r.content, prefixo=prefixo)
    return Response(corpo, status=status, headers=cab)


# Clima e risco (06/10/2026): alertas públicos por usina. A rota mora em clima_tela.py, importada aqui no fim porque precisa
# do `bp` e da `TORRE` definidos acima; a regra mora em nexus/performance/clima/.
from . import clima_tela  # noqa: E402,F401
# Mapa de risco (07/10/2026): a mesma leitura do Clima e risco, num mapa do Brasil (/t/performance/clima/mapa).
from . import mapa_tela  # noqa: E402,F401

"""Torre Performance: Quanto gerou, o que caiu e qual a causa provável.

Telas ainda em construção: todas caem no placeholder da casca. Para dar vida a uma tela, crie uma
view com a mesma rota (ela vence a genérica), por exemplo:

    @bp.route("/tempo-real")
    def tempo_real():
        return render_template("performance/tempo-real.html")
"""
from datetime import datetime

from flask import Response, current_app, jsonify, render_template, request

from ...performance import ponte
from ..modelo import Tela, Torre

TORRE = Torre(
    id="performance",
    nome="Performance",
    ordem=30,
    icone="chart-line-up",
    descricao="Quanto gerou, o que caiu e qual a causa provável.",
    telas=[
        Tela("tempo-real", "Tempo real",
             "O que está fora do normal agora na frota?",
             "Plataforma de Performance (app.gridco.com.br)"),
        Tela("noc", "Painel NOC",
             "Como está a carteira inteira de relance?",
             "Plataforma de Performance"),
        Tela("diagnostico", "Diagnóstico",
             "Qual anomalia é falha real e qual é clima, e virou OS?",
             "Plataforma de Performance + Fracttal"),
        Tela("strings-trackers", "Strings e trackers",
             "Quais strings e trackers estão perdendo energia?",
             "Plataforma de Performance (falhas_performance, via API)"),
        Tela("gerencial", "Visão gerencial",
             "O mês fecha dentro da meta de PR e geração?",
             "BD_Performance e BD_Thopen, via API"),
        Tela("relatorio", "Criador de relatório",
             "Como monto o relatório do cliente com os números certos?",
             "Plataforma de Performance"),
        Tela("gemeo", "Gêmeo digital",
             "Quanto a usina deveria ter gerado com o sol que teve?",
             "gemeo_digital, via API"),
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


@bp.route("/tempo-real")
def tempo_real():
    url, _token, falta = _config_ponte()
    return render_template("performance/tempo_real.html", torre=TORRE, tela=TORRE.tela("tempo-real"),
                           prefixo=ponte.PREFIXO, plataforma=url, falta=falta)


def _erro(texto: str) -> Response:
    hora = datetime.now().strftime("%H:%M")
    html = render_template("performance/ponte_erro.html", texto=texto, hora=hora)
    return Response(html, status=502, mimetype="text/html")


@bp.route("/plataforma/<path:caminho>", methods=["GET", "HEAD", "POST"])
def plataforma(caminho: str):
    url, token, falta = _config_ponte()
    if falta:
        return _erro("A ponte não está configurada: falta " + " e ".join(falta) + " no .env do Nexus.")
    # A barra inicial é obrigatória: o <path:> chega sem ela, e "@evil.com/x" colado em "http://plat:5050" viraria
    # usuário "plat" no servidor evil.com, levando a chave de leitura para fora (revisão da Tarefa 8).
    c = "/" + caminho
    if not ponte.pode_passar(request.method, c):
        return jsonify({"ok": False, "error": "somente leitura (Nexus)"}), 403
    pedido = ponte.montar_pedido(url, token, request.method, c, list(request.args.items(multi=True)),
                                 request.get_data() if request.method == "POST" else None, request.content_type)
    try:
        r = ponte.enviar(**pedido)
    except ponte.ForaDoAr:
        return _erro(f"Plataforma de Performance sem resposta em {ponte.TEMPO_LIMITE_S} s.")
    if r.status_code == 401:
        return _erro("A plataforma recusou a chave de leitura do Nexus. Confira NEXUS_PLATAFORMA_TOKEN no .env do "
                     "Nexus e NEXUS_LEITURA_TOKEN na plataforma.")
    status, cab, corpo = ponte.ajustar_resposta(r.status_code, dict(r.headers), r.content)
    return Response(corpo, status=status, headers=cab)

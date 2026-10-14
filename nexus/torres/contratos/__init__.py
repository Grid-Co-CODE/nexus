"""Torre Contratos e clientes: SLA, entregáveis e comunicação com cada cliente.

Tela viva: **Contestações** (13/10/2026, Levi: "em contratos e clientes no Nexus pode ter um lugar para essas
contestações separando setores!"), pelo livro que o Dashboard Thopen grava no banco (nexus/contratos/contestacoes.py).
As outras telas ainda caem no placeholder da casca: a view com a mesma rota vence a genérica. Leia o CLAUDE.md desta
pasta antes de mexer.
"""
from flask import render_template, request

from ...contratos import contestacoes as CT
from ..modelo import Tela, Torre

TORRE = Torre(
    id="contratos",
    nome="Contratos e clientes",
    ordem=60,
    icone="handshake",
    descricao="SLA, entregáveis e comunicação com cada cliente.",
    telas=[
        Tela("clientes", "Clientes",
             "Algum contrato está em risco de penalidade ou renovação?",
             "Gestão de contratos (a estruturar)"),
        Tela("contestacoes", "Contestações",
             "O que os clientes contestaram nos dashboards, e para qual setor?",
             "Dashboard Thopen: a contestação de cada dia, gravada cifrada no banco (livro thopen_contestacoes)"),
        Tela("onboarding", "Onboarding de cliente",
             "Em que etapa está a entrada do cliente novo?",
             "Checklist de onboarding do Nexus"),
        Tela("comunicacao", "Comunicação por cliente",
             "O que cada cliente quer receber, quando e por onde?",
             "Perfil de comunicação do Nexus (spec R13)"),
        Tela("portal", "Portal do cliente",
             "O que o cliente vê sobre as usinas dele?",
             "Texto público das ocorrências e relatórios"),
    ],
)

bp = TORRE.criar_blueprint(__name__)


@bp.route("/contestacoes")
def contestacoes():
    """Uma aba por setor (Performance, Zeladoria), a contestação mais nova em cima: quando chegou, a usina, o dia
    contestado, o que o cliente contestou, quem é e como responder, a mensagem e o que ele via na tela naquele dia, e se
    o Teams do setor recebeu o aviso. Nome, contato e mensagem só com a chave privada deste Nexus."""
    d = CT.contestacoes()
    setores = dict(CT.SETORES)
    setor = request.args.get("setor") if request.args.get("setor") in setores else CT.SETORES[0][0]
    return render_template("contratos/contestacoes.html", torre=TORRE, tela=TORRE.tela("contestacoes"), d=d,
                           setores=CT.SETORES, setor=setor, lista=d["por_setor"].get(setor) or [])

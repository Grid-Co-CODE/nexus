"""Comando › Nexus Insights com o portfólio no alto e a Nexus IA (19/11/2026). Levi, com o Insights do mockup R18: "vai
mostrar o portfólio, a saúde dos portfólios, como é que está sendo o cumprimento, como é que está a pontuação, e aí ele
conseguir entender o que está acontecendo e fazer perguntas para o Haiku 5.5".

Nada vai à rede: o portfólio é um `gerencial.montar` inventado e a IA é dublada."""
from test_campo_responsaveis import tela  # noqa: F401  (tela é fixture)
from test_campo_visao import banco  # noqa: F401  (banco é fixture)

from nexus.comando import ia as IA
from nexus.comando import insights_portfolio as II


def _u(uid, nome, nota, nota_ant, pontos, itens=()):
    return {"uid": uid, "usina": nome, "mwp": 6.0, "pontos": pontos,
            "score": {"2026-11": {"nota": nota, "itens": list(itens)}, "2026-10": {"nota": nota_ant, "itens": []}}}


def _g():
    athon = {"cliente": "Athon", "usinas_n": 2, "mwp": 12.0, "media": 66, "valor": 12345.67,
             "score": {"2026-11": {"nota": 62}, "2026-10": {"nota": 70}},
             "usinas": [_u(60, "Marabá 200", 48, 60, 50, [{"nome": "Disponibilidade", "nota": 40, "mediu": "94,8% no mês."},
                                                          {"nome": "Rotinas", "nota": 56, "mediu": "ronda há 9 dias."}]),
                        _u(61, "Timon 100", 76, 80, 82)]}
    thopen = {"cliente": "Thopen", "usinas_n": 1, "mwp": 5.5, "media": 90,
              "score": {"2026-11": {"nota": 88}, "2026-10": {"nota": 85}}, "usinas": [_u(10, "Aparecida 3", 88, 85, 90)]}
    qair = {"cliente": "Qair", "usinas_n": 1, "mwp": 1.0, "media": None, "score": {"2026-11": {"nota": None}},
            "usinas": [_u(99, "Sem Dado", None, None, None)]}
    return {"ok": True, "gerado": "19/11/2026 às 10:00", "mes_atual": "2026-11",
            "meses": [{"id": "2026-11", "curto": "novembro", "atual": True}, {"id": "2026-10", "curto": "outubro", "atual": False}],
            "clientes": [thopen, athon, qair], "avisos": [],
            "totais": {"clientes": 3, "usinas": 4, "mwp": 18.5, "valor": 12345.67}}


INSIGHTS = [{"id": "R01:1", "regra": "R01", "sev": "critico", "usina": "Marabá 200", "titulo": "Parada há 3 dias",
             "acao": "Religar"},
            {"id": "R02:2", "regra": "R02", "sev": "atencao", "usina": "Timon 100", "titulo": "PR baixo", "acao": "Ver"},
            {"id": "R03:3", "regra": "R03", "sev": "info", "usina": "Aparecida 3", "titulo": "Nota", "acao": "-"}]


def test_o_resumo_poe_o_pior_cumprimento_em_cima_e_conta_o_portfolio():
    r = II.resumo(_g(), INSIGHTS, {"R01": {"nome": "Usina parada"}})
    assert [c["cliente"] for c in r["clientes"]] == ["Athon", "Thopen", "Qair"]          # sem nota no fim
    a = r["clientes"][0]
    assert (a["nota"], a["nota_ant"], a["delta"], a["tom"]) == (62, 70, -8, "alerta")
    assert (a["abaixo"], a["em_risco"], a["criticos"], a["atencao"]) == (1, 1, 1, 1)
    assert a["pior"] == {"usina": "Marabá 200", "uid": 60, "nota": 48, "tom": "critico", "item": "Disponibilidade 40"}
    t = r["totais"]
    assert (t["nota"], t["com_nota"], t["abaixo"], t["em_dia"]) == (71, 3, 1, 1)         # (48 + 76 + 88) / 3
    assert (t["saude"], t["em_risco"], t["criticos"], t["atencao"]) == (74, 1, 1, 1)
    assert (r["mes"], r["mes_ant"]) == ("novembro", "outubro")
    # o porquê: do cliente (a queda, o item que puxa, as usinas abaixo de 55, o crítico mais comum) e de cada usina
    assert a["motivo"] == ("Caiu 8 pontos desde outubro. O que puxa a nota: Disponibilidade (média 40 em 1 usina) e Rotinas "
                           "(média 56 em 1 usina). 1 de 2 usinas abaixo de 55. 1 insight crítico aberto: Usina parada.")
    assert a["puxa"]["nome"] == "Disponibilidade"
    m = a["usinas"][0]
    assert (m["usina"], m["delta"], m["motivo"], m["criticos"]) == ("Marabá 200", -12, "Disponibilidade 40: 94,8% no mês.", 1)
    assert m["insights"][0]["regra_nome"] == "Usina parada"
    assert r["parecer"].startswith("Em novembro, até ontem, o portfólio cumpre 71 de 100") and "Caíram 5 pontos ou mais: Athon" in r["parecer"]
    assert r["clientes"][2]["motivo"].startswith("Sem nota neste mês")


def test_o_dossie_da_ia_ganha_o_cumprimento_e_os_insights_sem_valor_de_contrato():
    texto = II.secoes_dossie(_g(), INSIGHTS, {"R01": {"nome": "Usina parada", "torre": "cos"}}, 6)
    assert "## 6. Cumprimento do contrato e saúde" in texto and "## 7. Insights abertos do motor de regras" in texto
    assert "| Marabá 200 | Athon | 48 | 60 | Disponibilidade 40: 94,8% no mês. | 50 |" in texto
    assert "| crítico | Usina parada | Marabá 200 | Parada há 3 dias | Religar | cos |" in texto
    assert "12345" not in texto and "R$" not in texto                                   # o valor do contrato não vai
    assert texto.index("| crítico |") < texto.index("| atenção |")
    assert "Não recalcule a nota" in II.INSTRUCOES and II.INSTRUCOES.startswith(IA.INSTRUCOES[:0] or "Você é o Nexus IA")


def test_a_tela_traz_o_portfolio_e_a_ia_por_tras(tela, logado, monkeypatch):
    from nexus.torres.comando import gerencial_tela as GT
    monkeypatch.setattr(GT, "dados_gerencial", _g)
    html = logado.get("/t/comando/insights").get_data(as_text=True)
    assert 'data-ins-pedaco="/t/comando/insights/portfolio"' in html and 'data-ins-pedaco="/t/comando/insights/ia"' in html
    assert "/static/comando-insights.js" in html and "/static/comando/ia.js" in html
    p = logado.get("/t/comando/insights/portfolio").get_data(as_text=True)
    assert p.index("Athon") < p.index("Thopen") and "↓8" in p and "Marabá 200" in p
    assert "12.345" not in p and "12345" not in p
    # o funil: o cliente pior já aberto, o porquê dele, a usina com o porquê e o prontuário, e a pergunta pronta para a IA
    assert 'data-inf-cli="inf-p-1" aria-controls="inf-p-1" aria-pressed="true"' in p and 'id="inf-p-2" aria-label="Thopen" hidden' in p
    assert "O que puxa a nota: Disponibilidade (média 40 em 1 usina)" in p
    assert 'href="/t/campo/usinas/60"' in p and "Abrir prontuário" in p and "Disponibilidade 40: 94,8% no mês." in p
    assert 'data-inf-perguntar="Por que a usina Marabá 200 está com 48 de cumprimento do contrato em novembro? O que fazer primeiro?"' in p
    c = logado.get("/t/comando/insights/ia").get_data(as_text=True)
    assert 'data-ia-url="/t/comando/insights/ia/perguntar"' in c and II.SUGESTOES[0] in c


def test_a_pergunta_do_insights_leva_o_dossie_ampliado(tela, logado, monkeypatch, tmp_path):
    from nexus.torres.comando import gerencial_tela as GT
    logado.application.config.update(NEXUS_DADOS=str(tmp_path))
    monkeypatch.setattr(GT, "dados_gerencial", _g)
    visto = {}

    def perguntar(cfg, ids, dossie, pergunta, historico=None, setores=None, meu_setor="", instrucoes="", pensar=False):
        visto.update(dossie=dossie, instrucoes=instrucoes)
        return [{"id": "haiku", "ok": True, "texto": "A Athon caiu pela disponibilidade.", "custo_usd": 0.001, "acoes": []}]
    monkeypatch.setattr(IA, "perguntar", perguntar)
    r = logado.post("/t/comando/insights/ia/perguntar", json={"pergunta": "Por que a Athon caiu?", "modelos": ["haiku"]})
    assert r.status_code == 200 and r.get_json()["ok"]
    assert visto["instrucoes"] == II.INSTRUCOES and visto["dossie"].startswith("# Dossiê da carteira de usinas")
    assert "## 6. Cumprimento do contrato e saúde" in visto["dossie"]

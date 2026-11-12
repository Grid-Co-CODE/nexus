"""O prontuário da usina (12/11/2026), a página do Comando > Usinas e da aba da usina da Usinas 360°. Levi: "A ideia do
prontuário da UFV é juntar todas as informações daquela usina para que o supervisor/gestor fique ciente do que está
acontecendo na UFV [...] Deixe forma visual agradável e direta!"; "quanto mais direto formos, melhor [...] Primeiramente,
dando um parecer geral, e quando a pessoa quiser se aprofundar, se aprofunda"; "essa visão irá substituir a central da
usina [...] deve ser possível criar OS para a UFV, criar ticket"; e, vendo a versão enxuta: "dá para colocar um pouquinho
mais de números [...] os KPIs principais de performance, meta, OS, pendências [...] de uma forma mais visual [...] o
visual na frente [...] mesmo dando drill down, a informação direta ali na lata [...] clicar e já se encaminhando para
aquela informação".

O que estes testes seguram: a conta pura (`nexus/comando/prontuario.py`: o parecer, o painel do alto com as barras, o
cartão das OS), as OS de cada estado na tela dona (`campo/manutencao.py`), as formas do Criar OS apontando para as rotas do OS
Creator, o ligador da fotografia do COS, e a mesma página nas duas portas (o que muda entre elas e o que a pessoa sem a tela não vê)."""
import re
from pathlib import Path

from test_campo_responsaveis import HOJE, tela  # noqa: F401  (tela é fixture)
from test_campo_visao import banco  # noqa: F401  (banco é fixture)

from nexus.campo import manutencao as M
from nexus.comando import prontuario as PR

RAIZ = Path(__file__).resolve().parents[1]


def _u(**k):
    """Uma linha da Visão do responsável, só com o que o painel lê."""
    u = {"meta": {"prod_kwh": 167200.0, "meta_kwh": 302200.0, "atingimento": 55.3, "pr": 54.6, "pr_meta": 73.2,
                  "dias_cob": 9, "dias_mes": 30},
         "disp": {"disp": 58.2, "h_perdidas": 46.0},
         "manutencao": {"os_abertas": 41, "em_verificacao": 31, "nao_iniciadas": 8, "em_execucao": 2, "atrasadas": 40,
                        "atrasadas_os": 9, "maior_atraso": 134, "paradas": 0, "vencem": 0, "passada": "2026-W45",
                        "passada_prog": 10, "passada_feitas": 1, "passada_pct": 10.0},
         "ronda": {"dias": 36, "tipo": "sem_ronda"}, "limpeza": {"sujidade": 1, "vegetacao": 5, "vala": "Limpa", "vala_peso": 0},
         "chamados": {"abertos": 12, "verificacao": 1, "mais_antigo": 253},
         "perf": {"valores": {"meta": {"txt": "55%", "cls": "critico"}, "pr": {"txt": "54,6", "cls": "alerta", "sub": "/ 73,2"},
                              "disp": {"txt": "58,2%", "cls": "critico"}}},
         "manut": {"valores": {"atrasadas": {"txt": "40", "cls": "critico", "sub": "134 d"}, "semana": {"txt": "10%", "cls": "alerta"}}},
         "acomp": {"valores": {"ronda": {"txt": "36 d", "cls": "critico"}, "limpeza": {"txt": "S1 V5", "cls": "critico"},
                               "chamados": {"txt": "12 abertos", "cls": "alerta"}}}}
    u.update(k)
    return u


def test_a_barra_fica_presa_no_trilho_e_sem_valor_nao_existe():
    assert PR._barra(55.3) == 55.3 and PR._barra(140) == 100.0 and PR._barra(-3) == 0.0
    assert PR._barra(60, PR.ESCALA_META) == 50.0 and PR._barra(100, PR.ESCALA_META) == 83.3
    assert PR._barra(None) is None and PR._barra("") is None      # nada de barra vazia fingindo zero


def test_o_parecer_conta_e_diz_o_principal():
    itens = [{"tom": "critico", "titulo": "Meta do mês em 55%"}, {"tom": "alerta", "titulo": "PR abaixo"}]
    assert PR.parecer(itens) == {"nivel": "critico", "titulo": "Pede ação agora",
                                 "frase": "1 ponto crítico e 1 de atenção. O principal: Meta do mês em 55%."}
    assert PR.parecer(itens[1:])["titulo"] == "Pede acompanhamento"
    assert PR.parecer([])["nivel"] == "ok" and PR.parecer([])["titulo"] == "Em dia"


def test_o_painel_traz_a_performance_em_medidores_com_a_marca_de_cada_um():
    """"os KPIs principais de performance, meta [...] de uma forma mais visual": o número e a cor são os da Visão; a
    barra vai contra a marca (a meta em 100% numa escala até 120%, o PR previsto, os 99% da régua da disponibilidade)."""
    p = PR.painel(_u(), {"os_abertas": 41}, [], anterior={"curto": "out/26", "ating": "64%", "pr": "79,5%", "disp": "83,3%"})
    assert p["perf"]["periodo"] == "9 de 30 dias"
    meta, pr, disp = p["perf"]["medidores"]
    assert (meta["txt"], meta["cls"], meta["largura"], meta["marca"]) == ("55%", "critico", 46.1, 83.3)
    assert meta["sub"] == "167,2 de 302,2 MWh" and meta["ant"] == "out/26: 64%"
    assert (pr["txt"], pr["cls"], pr["largura"], pr["marca"], pr["sub"]) == ("54,6%", "alerta", 54.6, 73.2, "previsto 73,2%")
    assert (disp["txt"], disp["largura"], disp["marca"], disp["sub"]) == ("58,2%", 58.2, 99.0, "46,0 h paradas")
    # sem a meta publicada, o medidor fica sem barra e sem marca (nunca uma barra em zero)
    vazio = PR.painel({"perf": {"valores": {}}}, {"os_abertas": 0}, [])["perf"]["medidores"][0]
    assert (vazio["txt"], vazio["largura"], vazio["marca"], vazio["sub"]) == ("—", None, None, "")


def test_o_painel_reparte_as_os_pelo_estado_e_diz_o_que_pede_acao():
    o = PR.painel(_u(), {"os_abertas": 41}, [])["os"]
    assert o["abertas"] == 41
    assert [(q["rot"], q["n"]) for q in o["partes"]] == [("não iniciadas", 8), ("em execução", 2), ("em verificação", 31)]
    assert round(sum(q["largura"] for q in o["partes"])) == 100
    linhas = {l["rot"]: l for l in o["linhas"]}
    assert (linhas["Tarefas atrasadas"]["txt"], linhas["Tarefas atrasadas"]["cls"]) == ("40", "critico")
    assert linhas["Tarefas atrasadas"]["sub"] == "em 9 OS · a mais antiga há 134 d"
    assert (linhas["Tarefas pausadas"]["txt"], linhas["Tarefas pausadas"]["cls"]) == ("0", "ok")
    assert "Parada agora" not in linhas
    assert o["semana"] == {"rot": "Semana passada", "txt": "10%", "cls": "alerta", "largura": 10.0,
                           "sub": "1 de 10 tarefas do plano · W45"}
    # a OS de parada aberta agora vai na frente, em crítico
    com_parada = PR.painel(_u(paradas_abertas=[{"os": 1}]), {"os_abertas": 41}, [])["os"]["linhas"][0]
    assert (com_parada["rot"], com_parada["txt"], com_parada["cls"]) == ("Parada agora", "1", "critico")
    # sem a leitura das OS do Fracttal o bloco diz "sem leitura": nunca 0
    assert PR.painel(_u(), {"os_abertas": None}, [])["os"] is None


def test_o_painel_conta_as_pendencias_e_monta_a_faixa():
    itens = [{"tom": "critico"}, {"tom": "critico"}, {"tom": "alerta"}]
    resumo = PR.resumos(_u(extintores={"vencidos": 1}), {"insights": 2}, [{"sev": "critico"}, {"sev": "atencao"}], None)
    assert resumo["seg"]["n"] == 1 and resumo["seg"]["tom"] == "critico"
    p = PR.painel(_u(), {"os_abertas": 41, "insights": 2, "estado": "sem_leitura"}, itens,
                  cos={"por_mes": [{"rot": "novembro", "n": 6, "parou": 5}]},
                  insights=[{"sev": "critico"}, {"sev": "atencao"}], resumo=resumo)
    assert p["pend"] == {"n": 3, "criticos": 2, "alertas": 1}
    f = {c["rot"]: c for c in p["faixa"]}
    assert (f["Última ronda"]["txt"], f["Última ronda"]["cls"], f["Última ronda"]["sub"]) == ("há 36 d", "critico", "sem ronda no prazo")
    assert [(n["rot"], n["n"], n["cls"]) for n in f["Sujidade e vegetação"]["niveis"]] == [("Sujidade", 1, "ok"), ("Vegetação", 5, "critico")]
    assert f["Sujidade e vegetação"]["sub"] == ""                 # a vala limpa não pesa: não aparece
    assert (f["Chamados abertos"]["txt"], f["Chamados abertos"]["sub"]) == ("12", "o mais antigo há 253 dias · 1 em verificação")
    assert (f["Segurança"]["txt"], f["Segurança"]["cls"]) == ("1 pendência", "critico")
    assert (f["COS agora"]["txt"], f["COS agora"]["sub"]) == ("—", "sem leitura agora · 6 normalizadas em novembro")
    assert (f["Insights"]["txt"], f["Insights"]["cls"], f["Insights"]["sub"]) == ("2", "critico", "1 crítico")
    assert {c["secao"] for c in p["faixa"]} == {"rondas", "chamados", "seg", "cos", "insights"}
    # o motor dos insights ainda calculando: travessão, nunca 0
    assert {c["rot"]: c for c in PR.painel(_u(), {"insights": None}, [])["faixa"]}["Insights"]["txt"] == "—"
    # a vala que pesa na régua aparece
    suja = PR.painel(_u(limpeza={"sujidade": 3, "vegetacao": 3, "vala": "Obstruída", "vala_peso": 4}), {}, [])["faixa"]
    assert {c["rot"]: c for c in suja}["Sujidade e vegetação"]["sub"] == "vala obstruída"


def test_o_cartao_das_os_lista_o_que_pede_acao_primeiro_e_as_os_de_cada_estado():
    """"mesmo dando drill down, a informação direta ali na lata": as atrasadas e as pausadas com o que as explica, e
    as OS de cada estado pelo número (cada uma abre o card dela)."""
    man = {"atrasadas": 40, "todas_atrasadas": [{"os": 8466, "wid": 9, "dias": 134, "tipo": "preventiva"},
                                                 {"os": 10790, "wid": None, "dias": 94, "tipo": "inspecao"}],
           "todas_paradas": [{"os": 7001, "wid": 3, "motivo": "Aguardando material", "desde": "2026-11-02", "quem": "PCM"}],
           "os_verificacao": [{"os": 7255, "wid": 1}], "os_em_execucao": [], "os_nao_iniciadas": [{"os": 8466, "wid": 9}]}
    g = PR.os_grupos(man, "critico")
    assert [(x["chave"], x["n"], x["tom"], x["detalhado"]) for x in g] == [
        ("atrasadas", 2, "critico", True), ("pausadas", 1, "alerta", True), ("verificacao", 1, "neutro", False),
        ("nao_iniciadas", 1, "neutro", False)]                      # o grupo vazio (em execução) não entra
    assert g[0]["nota"] == f"40 tarefas programadas há mais de {M.DIAS_ATRASO} dias"
    assert g[0]["itens"] == [{"os": 8466, "wid": 9, "txt": "há 134 d · preventiva"},
                             {"os": 10790, "wid": None, "txt": "há 94 d · inspeção"}]
    assert g[1]["itens"][0]["txt"] == "Aguardando material · desde 02/11 · PCM"
    assert PR.os_grupos(None) == [] and PR.os_grupos({}) == []


def test_a_tela_dona_da_as_os_de_cada_estado_e_a_contagem_e_o_tamanho_da_lista():
    def t(n, os_, status="em_processo", estado="pendente"):
        return {"usina_id": 1, "os": os_, "fracttal_os_id": os_ + 1000, "tarefa_chave": f"t{n}", "codigo_ativo": "A",
                "tipo_tarefa": "preventiva", "estado_tarefa": estado, "status_os": status, "data_id_programada": None}
    r = M.tarefas_por_usina([t(1, 501), t(2, 502, estado="em_execucao"), t(3, 503, status="em_verificacao", estado="finalizada")],
                            [], set(), HOJE)[1]
    assert [x["os"] for x in r["os_verificacao"]] == [503] and r["os_verificacao"][0]["wid"] == 1503
    assert len(r["os_verificacao"]) == r["em_verificacao"] and len(r["os_nao_iniciadas"]) == r["nao_iniciadas"]
    assert len(r["os_em_execucao"]) == r["em_execucao"]
    assert len(r["os_verificacao"]) + len(r["os_nao_iniciadas"]) + len(r["os_em_execucao"]) == r["os_abertas"]


def test_o_mes_a_mes_leva_a_barra_do_atingimento():
    from datetime import date
    ms = PR.mes_a_mes({202610: {"prod_kwh": 592000.0, "meta_kwh": 927900.0, "atingimento": 63.8, "pr": 79.5, "pr_meta": 65.4}},
                      {"2026-10": {"disp": 83.3, "h_perdidas": 51.6}, "2026-09": {"disp": 98.8, "h_perdidas": 4.3}}, date(2026, 11, 12))
    assert [(m["curto"], m["ating"], m["ating_largura"]) for m in ms] == [("out/26", "64%", 53.2), ("set/26", "—", None)]


def test_o_titulo_do_insight_sai_sem_o_nome_da_usina():
    assert PR.sem_o_nome("Mandaguaçu: 1 extintor vencido", "Mandaguaçu") == "1 extintor vencido"
    assert PR.sem_o_nome("Altair sem geração há 2 dias", "Altair") == "Altair sem geração há 2 dias"


def test_o_criar_os_leva_as_formas_de_hoje_do_os_creator():
    """Levi, 12/11/2026: "na parte de criar OS, vai ter as opções que é possível hoje. Então, OS avulsa, OS de
    performance, OS de engenharia, inspeção de chamados, solicitação de OS. E aí o ticket pode tirar o botão de
    ticket". Cada opção aponta para uma rota que o OS Creator tem; a avulsa e a solicitação levam a usina (o ativo)."""
    from nexus.torres.comando.prontuario_dados import CRIAR_OS, criar_os
    assert [o[0] for o in CRIAR_OS] == ["OS avulsa", "OS de Performance", "OS de Engenharia", "Inspeção de chamados",
                                        "Solicitação de OS"]
    web = RAIZ / "nexus" / "torres" / "oscreator" / "os_creator" / "os_web"
    rotas = "".join((web / f).read_text(encoding="utf-8") for f in ("rotas.py", "rotas_tradicional.py", "rotas_engenharia.py",
                                                                    "rotas_chamados.py", "rotas_solic.py"))
    # quem usa o prontuário é quem DEMANDA ("a OS Performance seria mais o caminho para OS Creator Web Solicitação. Aí tem
    # uma abinha de performance, uma abinha de engenharia"): a Performance e a Engenharia abrem a aba delas na Nova
    # solicitação, e não a tela em que o próprio setor cria as OS dele
    por_nome = {o[0]: o[2] for o in CRIAR_OS}
    assert por_nome["OS de Performance"] == "/os/solicitacao/performance" and por_nome["OS de Engenharia"] == "/os/solicitacao/engenharia"
    abas = (web / "templates" / "solic.html").read_text(encoding="utf-8")
    setores = (web / "rotas_solic_eng.py").read_text(encoding="utf-8")
    assert '_SETOR = "<any(engenharia, performance):setor>"' in setores and '@bp.route("/solicitacao/" + _SETOR)' in setores
    for _rot, _sub, url, _leva in CRIAR_OS:
        if url.startswith("/os/solicitacao/"):
            assert f'href="{url}"' in abas, url                           # a aba existe na Nova solicitação
        else:
            assert f'@bp.route("{url[len("/os"):]}")' in rotas, url      # a rota existe no OS Creator
    # as telas que aceitam o ativo pelo endereço são as que usam a sugestão (`tradicional_web.sugestao`)
    for arq, leva in (("rotas_tradicional.py", True), ("rotas_solic.py", True)):
        assert ("trad.sugestao(assets, request.args)" in (web / arq).read_text(encoding="utf-8")) is leva
    ops = {o["rot"]: o["url"] for o in criar_os("THPN-ALT100")}
    assert ops["OS avulsa"] == "/os/tradicional?ativo=THPN-ALT100" and ops["Solicitação de OS"] == "/os/solicitacao?ativo=THPN-ALT100"
    assert ops["OS de Performance"] == "/os/solicitacao/performance" and ops["Inspeção de chamados"] == "/os/chamados/inspecao"
    assert all("?" not in o["url"] for o in criar_os(""))               # sem o código no cadastro, sem a usina


def test_o_ligador_do_cos_nao_liga_o_codigo_com_o_prefixo_de_outro_cliente():
    """A análise das usinas Sem leitura (12/11/2026): o `E1EN-PCN100` (a Poconé da E1, sem código no cadastro) caía na
    Poconé 1 da Thopen (`THPN-PCN100`) pela terminação, e as ocorrências de uma apareciam na outra. A fotografia do COS
    liga pela regra da casa (a das normalizações): o código cheio, ou a terminação de UMA usina sem prefixo de outro
    cliente; antes de tudo, o nome do Fracttal pelo de-para."""
    from nexus.comando import usinas as CU
    from nexus.dados import fatos as D

    class _B:
        usinas = [{"usina_id": 1, "nome": "Poconé 1", "codigo": "THPN-PCN100"}, {"usina_id": 2, "nome": "Poconé", "codigo": ""},
                  {"usina_id": 3, "nome": "Itajá 1 e 2", "codigo": "ITA100"},
                  {"usina_id": 4, "nome": "Aparecida do Taboado 1 e 2", "codigo": "THPN-ADT100"}]
        de_para = [{"sistema": D.SISTEMA_FRACTTAL, "chave_externa": "E1 - Poconé - MT", "usina_id": 2}]
    _B.lig = D.Ligador(_B.usinas, _B.de_para, [], {})
    assert _B.lig.usina("", "E1EN-PCN100")[0] == 1                    # o ligador geral liga errado (a terminação)
    usina_de = CU.ligador_do_cos(_B)
    assert usina_de("Poconé", "E1EN-PCN100") is None                  # o prefixo é de outro cliente: não liga
    assert usina_de("Poconé 1", "THPN-PCN100") == 1                   # o código cheio
    assert usina_de("", "THOPEN-ITA100") == 3 and usina_de("", "ADT100") == 4      # a terminação de uma usina só
    assert usina_de("E1 - Poconé - MT", "E1EN-PCN100") == 2           # o nome do Fracttal, pelo de-para, vem antes
    assert usina_de("", "") is None and usina_de(None, None) is None


# ── a página, nas duas portas ────────────────────────────────────────────────────────────────────────────────────────
def _cartao(html, sec):
    return html.split(f'id="pu-{sec}"', 1)[1].split("</details>", 1)[0]


def test_o_prontuario_abre_pelo_parecer_e_pelo_painel_com_os_cartoes_fechados(tela, logado):
    html = logado.get("/t/comando/usinas/1").get_data(as_text=True)
    assert '<h1 class="cu-nome cmu-nome">Altair ' in html and "Prontuário da usina" in html
    # o parecer numa linha, antes do painel; o painel antes dos cartões
    assert html.index('class="pu-parecer pu-parecer--') < html.index('class="pu-painel"') < html.index('id="pu-perf"')
    painel = html.split('class="pu-painel"', 1)[1].split('class="pu-faixa"', 1)[0]
    for bloco in ("Performance do mês", "OS e manutenção", "Pendências"):
        assert bloco in painel, bloco
    assert painel.count('class="pu-med"') == 3 and "pu-barra-f" in painel and "pu-barra-m" in painel
    # a geração de cada dia do mês, em barras, já no alto (o gráfico inteiro fica no cartão)
    assert 'class="pu-spark"' in painel and painel.count('class="cr-barra cr-barra--') == 2
    # cada número leva ao cartão dele
    assert 'href="#pu-perf" data-pu-abre="perf"' in painel and 'href="#pu-os" data-pu-abre="os"' in painel
    # os cartões vêm fechados, com o estado numa linha
    for sec in ("perf", "os", "rondas", "seg", "cos", "chamados", "insights", "demandas"):
        assert f'<details class="cu-q pu-sec" id="pu-{sec}">' in html, sec
    assert "<details open" not in html and html.count('class="pu-sum-e"') == 8
    # a Performance abre pelo gráfico do mês e não repete a meta, o PR e a disponibilidade do painel
    perf = _cartao(html, "perf")
    assert "Geração diária (MWh) e POA (kWh/m²)" in perf and "<dt>Meta do mês</dt>" not in perf
    # o card da OS é um só na página, e o script do prontuário vem junto
    assert html.count("window.NexusOsCard = window.NexusOsCard") == 1 and "comando/prontuario.js" in html


def test_as_acoes_do_alto_criam_a_os_e_o_ticket_com_a_usina_e_baixam_o_relatorio(tela, logado):
    html = logado.get("/t/comando/usinas/1").get_data(as_text=True)
    acoes = html.split('class="pu-acoes"', 1)[1].split("</header>", 1)[0]
    # o Criar OS abre as cinco formas de hoje do OS Creator; a avulsa e a solicitação já com a usina; sem o ticket
    menu = acoes.split('class="pu-menu-caixa"', 1)[1].split("</div>", 1)[0]
    assert menu.count("<a href=") == 5 and "ticket</b>" not in acoes and "Criar ticket" not in html
    assert re.search(r'href="/os/tradicional\?ativo=[A-Z0-9-]+"><b>OS avulsa</b>', menu)
    assert re.search(r'href="/os/solicitacao\?ativo=[A-Z0-9-]+"><b>Solicitação de OS</b>', menu)
    for url, rot in (("/os/solicitacao/performance", "OS de Performance"), ("/os/solicitacao/engenharia", "OS de Engenharia"),
                     ("/os/chamados/inspecao", "Inspeção de chamados")):
        assert f'href="{url}"><b>{rot}</b>' in menu, rot
    assert "data-pu-rel" in acoes and 'href="/t/comando/conversa/usina/1"' in acoes
    # o relatório do cliente em PDF pelo endereço do próprio Comando: o mês (o anterior marcado) e os temas
    jan = html.split('id="pu-rel"', 1)[1].split("</dialog>", 1)[0]
    assert 'action="/t/comando/usinas/1/relatorio.pdf"' in jan and "Qual mês?" in jan
    # o que entra no PDF: cada tema com os campos dele, todos marcados ("editar os campos que eu quero que apareça")
    from nexus.campo import relatorio_usina as RU
    assert "O que entra no relatório?" in jan and jan.count("data-pu-rel-tema") == 4
    assert jan.count('name="tema"') == 4 and jan.count('name="campo"') == len(RU.CAMPOS) == jan.count(" checked> ") - 4
    for k, _tema, rot in RU.CAMPOS:
        assert f'name="campo" value="{k}" checked> {rot}' in jan, k
    r = logado.get(f"/t/comando/usinas/1/relatorio.pdf?mes={HOJE.strftime('%Y-%m')}")
    assert r.status_code == 200 and r.mimetype == "application/pdf" and r.data[:5] == b"%PDF-"
    assert logado.get("/t/comando/usinas/999/relatorio.pdf").status_code == 404


def test_a_pessoa_sem_a_tela_nao_ve_o_link_nem_o_botao_dela(tela, logado, monkeypatch):
    """O link da tela que a pessoa não abre não aparece (a Central da usina já fazia assim): sem o OS Creator, sem o
    Criar OS; sem tela do Comando, sem a conversa."""
    from nexus.auth import setor_telas
    monkeypatch.setattr(setor_telas, "liberadas_do_menu", lambda: {"campo/responsaveis", "campo/rondas"})
    html = logado.get("/t/campo/responsaveis?modo=usina&usina=1").get_data(as_text=True)
    assert "/os/tradicional" not in html and 'href="/os/solicitacao' not in html and "pu-menu-caixa" not in html
    assert "/t/comando/conversa/usina/1" not in html and "Abrir os Insights" not in html
    assert "Abrir a Mesa da Segurança" not in html and "/t/campo/rondas/usina/1" in html
    assert "data-pu-rel" in html                                               # o relatório é da própria tela


def test_a_aba_da_usinas_360_mostra_o_mesmo_prontuario(tela, logado):
    """"essa visão irá substituir a central da usina": a aba mostra a mesma página, com a busca das usinas no alto e a
    janela desta tela (o dia a dia, os extintores e a decisão da PT abrem por cima)."""
    html = logado.get("/t/campo/responsaveis?modo=usina&usina=1").get_data(as_text=True)
    assert ">Prontuário da usina</a>" in html and "Central da usina" not in html.split("<main", 1)[-1].split("<script", 1)[0]
    assert '<h2 class="cu-nome cmu-nome">Altair ' in html and "<h1 class=\"cu-nome" not in html
    assert 'class="pu-painel"' in html and 'id="pu-perf"' in html and "comando.css" in html
    assert 'action="/t/campo/responsaveis/usina/1/relatorio.pdf"' in html
    # o card da OS da tela, uma vez só (o prontuário não inclui outro)
    assert html.count("window.NexusOsCard = window.NexusOsCard") == 1
    # as PT esperando o De acordo abrem a decisão na janela da tela; o dia a dia e os extintores também
    seg = _cartao(html, "seg")
    assert seg.count('data-cr-painel="/t/campo/responsaveis/pt/') == 2 and "Decidir a PT" in seg
    assert "/t/campo/responsaveis/usina/1/extintores" in seg
    perf = _cartao(html, "perf")
    for k in ("meta", "pr", "disp"):
        assert f'data-cr-painel="/t/campo/responsaveis/usina/1/{k}"' in perf, k
    # no Comando, a PT leva à aba (lá não há a janela da decisão)
    comando = _cartao(logado.get("/t/comando/usinas/1").get_data(as_text=True), "seg")
    assert "data-cr-painel" not in comando and "/t/campo/responsaveis?modo=usina&amp;usina=1#pu-seg" in comando

"""Torre COS: o Monitoramento (09/11/2026) — a geração em kW ao vivo e a curva do dia das usinas com logger e do SunOP.

O kW, a situação e a curva vêm prontos da Ronda COS, pelo Andamento (`GET /api/nexus/geracao` e `/geracao/curvas`); daqui
são os filtros, a faixa e o desenho da curva (nexus/cos/monitoramento.py). Nada vai à rede, e os dados são fictícios."""
import urllib.parse

import pytest

from nexus.cadastro import setor_ids as SID
from nexus.cos import andamento as AND
from nexus.cos import monitoramento as MO
from nexus.torres.cos import TORRE

CHAVE = "chave-de-teste-do-andamento"
AGORA = AND.instante("2026-11-09T14:01:00-03:00")


def _u(id_, codigo, nome, cliente, kw=812.4, chave="GERANDO", texto="Gerando", fresca=True, minutos=0, fonte="SCADA",
       tem_curva=True, **mudar):
    u = {"id": id_, "fonte": fonte, "usina_codigo": codigo, "nome": nome, "sub_usina": None, "cliente": cliente, "kw": kw,
         "inversores_online": 9, "inversores_total": 10, "situacao": {"chave": chave, "texto": texto},
         "lido_em": "2026-11-09T17:00:20.000Z", "minutos_atras": minutos, "fresca": fresca, "tem_curva": tem_curva}
    u.update(mudar)
    return u


def _geracao(**mudar):
    d = {"versao": 1, "gerado_em": "2026-11-09T14:00:30-03:00",
         "fontes": {"scada": {"configurado": True, "ok": True, "motivo": None, "canal_calado": False},
                    "sunop": {"configurado": True, "ok": False, "motivo": "1 de 10 plantas sem leitura do portal agora.",
                              "sem_leitura": ["sunop-xyz100"]}},
         "usinas": [
             _u("scada-a1", "EX-UM100", "Usina Exemplo Um", "Cliente A", kw=812.4),
             _u("scada-b1", "EX-DOIS100", "Usina Exemplo Dois", "Cliente A", kw=0, chave="PAROU", texto="Parou"),
             # sem leitura nova há 42 min: fica fora da soma do "Gerando agora"
             _u("scada-c1", "EX-TRES100", "Usina Exemplo Três", "Cliente B", kw=1500.0, fresca=False, minutos=42),
             _u("sunop-mro100", "EX-MRO100", "Usina Exemplo SunOP", "Cliente B", kw=300, fonte="SUNOP", tem_curva=False),
         ]}
    d.update(mudar)
    return d


def _curvas():
    # de 15 em 15 min desde a meia-noite: o índice 20 é 05:00; às 05:30 não há amostra (o trecho quebra ali)
    return {"versao": 1, "gerado_em": "2026-11-09T14:00:40-03:00", "dia": "2026-11-09", "hoje": True, "passo_min": 15,
            "inicio": "2026-11-09T00:00:00-03:00",
            "curvas": [{"id": "scada-a1", "kw": [None] * 20 + [10, 50, None, 120]}], "sem_serie": []}


def _leitura(d):
    return AND.Leitura("", d, lido_em=1.0)


# --- a regra -----------------------------------------------------------------------------------------------------------

def test_o_kw_em_pt_br_e_em_mw_a_partir_de_mil():
    assert MO.kw_txt(812.4) == "812 kW" and MO.kw_txt(1234) == "1,2 MW" and MO.kw_txt(0) == "0 kW"
    assert MO.kw_txt(None) == "—"      # a Ronda COS não sabe: nunca zero no lugar


def test_a_curva_quebra_onde_falta_amostra_e_acha_o_maximo():
    c = MO.curva([None] * 20 + [10, 50, None, 120], AND.instante("2026-11-09T00:00:00-03:00"), 15)
    # dois trechos (05:00–05:15 e 05:45): sem ponte por cima da falta
    assert c.linha.count("M") == 2 and c.area.count("Z") == 2
    assert c.maximo == 120 and c.maximo_em == "05:45"
    assert c.pontos[:4] == [("05:00", 10), ("05:15", 50), ("05:30", None), ("05:45", 120)]
    # a escala é a da própria usina: o máximo encosta em cima (1 px de folga), o zero embaixo
    assert c.linha.endswith(f",{1.0}")
    # sem amostra nenhuma na janela: sem desenho
    assert MO.curva([None] * 30, AND.instante("2026-11-09T00:00:00-03:00"), 15).linha == ""
    assert MO.curva([], None, 15).linha == ""


def test_a_parada_vem_primeiro_e_a_soma_so_conta_a_leitura_nova():
    p = MO.painel(_leitura(_geracao()), _leitura(_curvas()), AGORA)
    assert [x["id"] for x in p.itens] == ["scada-b1", "scada-a1", "sunop-mro100", "scada-c1"]
    # 812,4 + 0 + 300: a Três (1.500 kW sem leitura nova) fica fora
    assert p.resumo["kw_agora"] == pytest.approx(1112.4)
    assert p.resumo == {**p.resumo, "usinas": 4, "gerando": 3, "paradas": 1, "velhas": 1}
    um = next(x for x in p.itens if x["id"] == "scada-a1")
    assert um["curva"].maximo == 120 and um["codigo"] == "EX-UM100"
    assert next(x for x in p.itens if x["id"] == "sunop-mro100")["curva"] is None
    # a fonte que falhou em parte diz, com o motivo da Ronda COS
    assert p.avisos == ["SunOP: 1 de 10 plantas sem leitura do portal agora"]


def test_os_filtros_contam_antes_e_a_faixa_conta_o_filtrado():
    p = MO.painel(_leitura(_geracao()), None, AGORA, cliente="Cliente A")
    assert [x["id"] for x in p.itens] == ["scada-b1", "scada-a1"] and p.resumo["kw_agora"] == pytest.approx(812.4)
    assert p.clientes == [("Cliente A", 2), ("Cliente B", 2)]       # as opções contam todas, antes do filtro
    p = MO.painel(_leitura(_geracao()), None, AGORA, grupo="velhas")
    assert [x["id"] for x in p.itens] == ["scada-c1"] and p.contagem["velhas"] == 1 and p.contagem["todas"] == 4
    p = MO.painel(_leitura(_geracao()), None, AGORA, busca="sunop")
    assert [x["id"] for x in p.itens] == ["sunop-mro100"]


# --- a leitura do Andamento --------------------------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _limpa():
    AND.limpar_cache()
    yield
    AND.limpar_cache()


@pytest.fixture
def ligada(app):
    app.config.update(NEXUS_COS_ANDAMENTO_URL="http://andamento.exemplo:3002", NEXUS_COS_ANDAMENTO_CHAVE=CHAVE,
                      NEXUS_COS_ANDAMENTO_CLIENTES="Cliente A,Cliente B")
    return app


def _servir(monkeypatch, respostas):
    pedidos = []

    def pedir(f, caminho, timeout=AND.TIMEOUT_S):
        pedidos.append((caminho, timeout))
        r = respostas.get(urllib.parse.urlsplit(caminho).path)
        if isinstance(r, Exception):
            raise r
        if r is None:
            raise AND.FonteErro("o Andamento não tem este cliente, ou a rota do Nexus está desligada lá", 404)
        return r
    monkeypatch.setattr(AND, "_pedir", pedir)
    monkeypatch.setattr(AND, "agora", lambda: AGORA)
    return pedidos


def test_a_api_fora_diz_e_a_ultima_leitura_boa_fica(ligada, monkeypatch):
    respostas = {"/api/nexus/geracao": _geracao()}
    pedidos = _servir(monkeypatch, respostas)
    with ligada.app_context():
        assert AND.ler_geracao(ligada.config).dados["usinas"]
        # o Andamento espera a API até 12 s: o Nexus espera mais que isso, e não os 5 s das outras rotas
        assert pedidos[-1] == ("/api/nexus/geracao", AND.TIMEOUT_GERACAO_S) and AND.TIMEOUT_GERACAO_S > 12
        AND._cache[(AND.fonte(ligada.config).url, "|geracao")] = (-1e9, *AND._cache[(AND.fonte(ligada.config).url,
                                                                                        "|geracao")][1:])
        respostas["/api/nexus/geracao"] = AND.FonteErro("o Andamento respondeu 503", 503)
        lt = AND.ler_geracao(ligada.config)
        assert lt.velha and lt.dados["usinas"] and lt.erro == "a API da Ronda COS não respondeu ao Andamento"
        AND.limpar_cache()
        respostas["/api/nexus/geracao"] = None
        lt = AND.ler_geracao(ligada.config)
        assert lt.dados is None and "ainda não tem a rota da geração" in lt.erro


# --- a tela ------------------------------------------------------------------------------------------------------------

@pytest.fixture
def tela(ligada, logado, monkeypatch):
    _servir(monkeypatch, {"/api/nexus/geracao": _geracao(), "/api/nexus/geracao/curvas": _curvas()})
    return logado


def test_a_tela_e_o_corpo_que_se_atualiza(tela):
    r = tela.get("/t/cos/monitoramento")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Usina Exemplo Um" in html and "812 kW" in html and "1,1 MW" in html
    assert 'class="cos-curva"' in html and 'data-kw="10|50||120"' in html and "máx. 120 kW às 05:45" in html
    assert "sem curva: o SunOP não guarda a série" in html and "SunOP: 1 de 10 plantas sem leitura" in html
    # o nome leva à ficha da usina; o corpo se atualiza pelo static/cos/monitoramento.js
    assert '/t/cos/usina/EX-UM100"' in html and "cos/monitoramento.js" in html
    r = tela.get("/t/cos/monitoramento?parcial=1&cliente=Cliente%20A")
    d = r.get_json()
    assert r.status_code == 200 and r.headers["Cache-Control"] == "private, no-store"
    assert "Usina Exemplo Um" in d["html"] and "Usina Exemplo Três" not in d["html"] and "<h1" not in d["html"]
    # os links do corpo são os da página, nunca os do pedaço
    assert "parcial" not in d["html"] and "situacao=parada" in d["html"]


def test_a_tela_e_do_setor_cos_e_entra_no_menu_sem_mexer_na_ordem():
    tela = TORRE.tela("monitoramento")
    assert tela.do_setor == SID.COS
    ids = [t.id for t in TORRE.telas]
    # o Acompanhamento segue a 1ª tela (o cartão do COS no Início); desde 12/11/2026 (a reorganização do COS pelo dono)
    # o Monitoramento abre o que se usa no turno, logo depois dele
    assert ids[:2] == ["acompanhamento", "monitoramento"]


# --- o videowall (?tv=1) -----------------------------------------------------------------------------------------------

def test_o_videowall_tem_ordem_fixa_os_clientes_e_a_atencao():
    g = _geracao()
    g["usinas"].append(_u("scada-d1", "EX-QUA100", "Usina Exemplo Quatro", "Cliente B", kw=None, chave="SEM_COMUNICACAO",
                          texto="Sem comunicação"))
    p = MO.painel(_leitura(g), None, AGORA, fixa=True)
    # a ordem da parede é sempre a mesma (cliente e nome): a que cai não troca de lugar
    assert [x["id"] for x in p.itens] == ["scada-b1", "scada-a1", "scada-d1", "sunop-mro100", "scada-c1"]
    w = MO.parede(p)
    assert [(c["cliente"], len(c["itens"]), c["anormais"]) for c in w["clientes"]] == [("Cliente A", 2, 1), ("Cliente B", 3, 2)]
    assert w["clientes"][0]["kw_agora"] == pytest.approx(812.4)
    # a atenção: a parada, depois a sem comunicação, depois a sem leitura nova
    assert [(x["id"], MO.anormal(x)) for x in w["atencao"]] == [("scada-b1", "parada"), ("scada-d1", "semcom"),
                                                               ("scada-c1", "velha")]


def test_a_escala_da_parede_fica_entre_os_limites():
    assert MO.escala_pedida("0,5") == 0.5 and MO.escala_pedida("1.25") == 1.25
    assert MO.escala_pedida(None) == 1 and MO.escala_pedida("abc") == 1 and MO.escala_pedida("0") == 1
    assert MO.escala_pedida("9") == MO.ESCALA_MAX and MO.escala_pedida("0.1") == MO.ESCALA_MIN


def test_a_tela_do_videowall_sem_a_casca_e_o_corpo_que_se_atualiza(tela):
    r = tela.get("/t/cos/monitoramento?tv=1&escala=0.5")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and 'class="cos-tv-html"' in html and 'style="--escala:0.5"' in html
    # sem o menu e o topo do Nexus; com a coluna da atenção, o relógio e o JavaScript da parede
    assert 'class="topo"' not in html and "Atenção agora" in html and 'id="cos-tv-hora"' in html
    assert "cos/monitoramento-tv.js" in html and "Usina Exemplo Dois" in html and "Parada" in html
    d = tela.get("/t/cos/monitoramento?tv=1&parcial=1").get_json()
    assert "cos-tv-grade" in d["html"] and "<html" not in d["html"] and 'id="cos-tv-hora"' not in d["html"]
    # a página normal leva à parede, e a parede volta para ela
    assert "tv=1" in tela.get("/t/cos/monitoramento").get_data(as_text=True)
    assert 'href="?"' in html or "Sair do videowall" in html


# --- a visão por usina e os inversores (12/11/2026) --------------------------------------------------------------------

def test_um_cartao_por_usina_com_a_atencao_e_sem_a_api_o_cartao_nao_e_botao(tela):
    html = tela.get("/t/cos/monitoramento").get_data(as_text=True)
    assert html.count('<article class="cos-mon-u') == 4 and 'data-gid="scada-a1"' in html
    assert "Atenção agora" in html and html.index("Atenção agora") < html.index('<article class="cos-mon-u')
    # sem o endereço da API da Ronda COS (NEXUS_COS_API_URL), sem a janela dos inversores e o cartão não é botão
    assert "cos-inv-dlg" not in html and "cos/inversores.js" not in html and 'role="button"' not in html
    assert "cos/fluido.js" in html


def test_com_o_endereco_da_api_o_cartao_abre_os_inversores(tela, ligada):
    ligada.config["NEXUS_COS_API_URL"] = "https://api.exemplo/"
    html = tela.get("/t/cos/monitoramento").get_data(as_text=True)
    assert 'id="cos-inv-dlg"' in html and "cos/inversores.js" in html and 'role="button"' in html
    assert 'api: "https://api.exemplo",' in html and 'console: "http://andamento.exemplo:3000/console",' in html
    assert "inversoresAbertos: {}" in html


def test_as_usinas_da_assistida_da_thopen_que_a_ronda_cos_manda_sem_cliente():
    """O dono, 12/11/2026: as usinas com logger sem cadastro na Ronda COS (sem cliente) são da "Thopen - Operação
    Assistida", e só no Monitoramento. O cliente que a Ronda COS mandar vale primeiro."""
    g = _geracao()
    g["usinas"] += [_u("scada-noig", None, "Usina Exemplo Assistida", None),
                    _u("scada-arbr", None, "Usina Exemplo Assistida B", "Cliente C")]
    p = MO.painel(_leitura(g), None, AGORA)
    cli = {x["id"]: x["cliente"] for x in p.itens}
    assert cli["scada-noig"] == "Thopen - Operação Assistida" and cli["scada-arbr"] == "Cliente C"


def test_as_abertas_de_inversor_pela_fotografia():
    foto = {"usinas": [
        {"codigo": "EX-UM100", "ocorrencias": [
            {"tipo_falha": "Inversor offline", "equipamentos": ["Inversor 1.2"], "os": "17001",
             "abertura": "2026-11-09T08:00:00-03:00"},
            {"tipo_falha": "Desligamento de usina", "equipamentos": [], "os": "17002",
             "abertura": "2026-11-09T09:00:00-03:00"},
            {"tipo_falha": "Falha de comunicação", "equipamentos": ["Inversor 1.3"], "os": "R-abc",
             "abertura": "2026-11-08T10:00:00-03:00"}]},
        {"codigo": None, "ocorrencias": [{"tipo_falha": "Inversor offline", "equipamentos": [], "os": "1"}]}]}
    assert MO.abertas_de_inversor([foto]) == {"EX-UM100": [["Inversor 1.2", "Inversor offline", "17001", "2026-11-09"],
                                                           ["Inversor 1.3", "Falha de comunicação", "", "2026-11-08"]]}

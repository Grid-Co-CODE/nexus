"""A seção "Uso do OS Creator" do Raio-X (31/10/2026, etapa 0 do canto central do OS Creator, tarefa 0.4): as telas mais
pedidas nos últimos 7 dias (os cliques e o que a tela pede sozinha, separados, com a mediana e o p95), os cliques por hora do
dia, os pedidos ao Fracttal por hora (o total e o pico por minuto, com a cota de 200 ao lado) e o corte por setor. É ela que
dá o "antes e depois" de cada etapa seguinte e mostra os horários de pico de verdade.

Provas, sem rede: o banco é a `ApiPGFalsa` com 7 dias gravados pelo próprio `fato_uso_os.gravar`; o que o servidor tem na
memória (a hora aberta, as horas que esperam o banco e o corte por setor) é dublado; o relógio está na mão. A página nunca
espera o banco: banco fora, vazio, lento, tudo vira "sem medição ainda" ou a cópia de antes, e a página abre."""
import re
import threading
import time
from datetime import datetime
from pathlib import Path

import pytest
import requests
from pg_falso import ApiPGFalsa

from nexus.casca import fracttal_conta as C
from nexus.casca import raio_x as R
from nexus.casca import uso_os as U
from nexus.dados import fato_uso_os as F

AQUI = Path(__file__).resolve().parent.parent
HOJE = datetime.fromisoformat("2026-10-30T14:20:00+00:00").timestamp()          # sexta, 11:20 em Brasília
AGORA = "2026103011"
SETOR_A, SETOR_B = "Setor Fictício Alfa", "Setor Fictício Beta"


def _uso(hora_id, rota, automatico=0, **kw):
    d = {"hora_id": hora_id, "rota": rota, "automatico": automatico, "pedidos_qtd": 10, "pessoas_qtd": 3,
         "duracao_p50_ms": 120, "duracao_p95_ms": 900, "erros_qtd": 0, "ocupado_qtd": 0, "fracttal_qtd": 0}
    d.update(kw)
    return d


def _fra(hora_id, origem="*", metodo="*", **kw):
    d = {"hora_id": hora_id, "origem": origem, "metodo": metodo, "pedidos_qtd": 4, "recusas_qtd": 0, "erros_qtd": 0,
         "pico_minuto_qtd": 2}
    d.update(kw)
    return d


# O que o banco guarda: 28, 29 e 30/10 dentro da janela de 7 dias (24 a 30/10) e uma linha de 20/10, fora dela.
USO_BANCO = [
    _uso("2026102810", "/os/historico", 0, pedidos_qtd=40, pessoas_qtd=6, duracao_p50_ms=300, duracao_p95_ms=2000),
    _uso("2026102810", "/os/historico", 1, pedidos_qtd=10, pessoas_qtd=2, duracao_p50_ms=250, duracao_p95_ms=1800),
    _uso("2026102810", "/os/os/<n>", 0, pedidos_qtd=20, pessoas_qtd=4, duracao_p50_ms=500, duracao_p95_ms=4000,
         fracttal_qtd=60),
    _uso("2026102910", "/os/historico", 0, pedidos_qtd=60, duracao_p50_ms=100, duracao_p95_ms=900),
    _uso("2026102910", "/os/_nexus/sessao", 1, pedidos_qtd=200, duracao_p50_ms=20, duracao_p95_ms=40),
    _uso("2026102914", "/os/os/<n>", 0, pedidos_qtd=30, duracao_p50_ms=700, duracao_p95_ms=6000, erros_qtd=2, fracttal_qtd=90),
    _uso("2026103010", "/os/historico", 0, pedidos_qtd=50, duracao_p50_ms=140, duracao_p95_ms=1100),
    _uso("2026103010", "/os/os/<n>", 0, pedidos_qtd=10, duracao_p50_ms=450, duracao_p95_ms=3500, ocupado_qtd=1, fracttal_qtd=30),
    _uso("2026102010", "/os/antiga", 0, pedidos_qtd=999),                            # fora da janela
]
FRACTTAL_BANCO = [
    _fra("2026102810", pedidos_qtd=150, pico_minuto_qtd=120),
    _fra("2026102810", "/os/os/<n>", "work_orders", pedidos_qtd=60, pico_minuto_qtd=50),
    _fra("2026102914", pedidos_qtd=900, recusas_qtd=3, pico_minuto_qtd=188),
    _fra("2026103010", pedidos_qtd=400, pico_minuto_qtd=205),
    _fra("2026102010", pedidos_qtd=5000, pico_minuto_qtd=190),                       # fora da janela
]
# O que o servidor tem na memória agora: a hora aberta (11h), uma linha que já está no banco com número mais novo (vale
# a da memória) e, esperando o banco, uma hora que ele ainda não recebeu.
USO_VIVO = [
    _uso("2026103010", "/os/historico", 0, pedidos_qtd=55, duracao_p50_ms=140, duracao_p95_ms=1100),
    _uso("2026103011", "/os/historico", 0, pedidos_qtd=5, duracao_p50_ms=130, duracao_p95_ms=800),
]
FRACTTAL_VIVO = [_fra("2026103011", pedidos_qtd=50, pico_minuto_qtd=30)]
SETOR = {
    "20261030": {SETOR_A: {"/os/historico": {"cliques": 30, "automaticos": 5}, "/os/os/<n>": {"cliques": 12, "automaticos": 0}},
                 "(sem setor)": {"/os/historico": {"cliques": 3, "automaticos": 0}}},
    "20261029": {SETOR_A: {"/os/historico": {"cliques": 20, "automaticos": 0}},
                 SETOR_B: {"/os/os/<n>": {"cliques": 8, "automaticos": 1}}},
    "20261001": {SETOR_A: {"/os/velha": {"cliques": 999, "automaticos": 0}}},         # fora da janela
}


@pytest.fixture(autouse=True)
def _ambiente(monkeypatch):
    """O que não é desta seção fica leve (o processador espera 1 s; a memória e o worker leem o /proc), o relógio vai à
    sexta 11:20 de Brasília e a cópia do banco começa vazia."""
    monkeypatch.setattr(R, "_processador", lambda janela_s=1.0: {"pct": 10, "nucleos": 4, "carga": None})
    monkeypatch.setattr(R, "_memoria_por_programa", lambda prazo_s=R.PRAZO_MEMORIA_S: None)
    monkeypatch.setattr(R, "RELATORIO_WEB", "/nao/existe/web.json")
    monkeypatch.setattr(R, "RELATORIO_WORKER", "/nao/existe/worker.json")
    for nome in ("_WORKER", "_WEB", "_MEMORIA", "_THREADS"):
        monkeypatch.setattr(R, nome, {"thread": None, "ultimo": None, "quando": None}, raising=False)
    monkeypatch.setattr(R, "_USO", {"thread": None, "dados": None, "lido_em": None, "lido_txt": "", "tentou_em": None,
                                    "erro": ""})
    monkeypatch.setattr(C, "_agora", lambda: HOJE)
    monkeypatch.setattr(U, "instantaneo", lambda: {"linhas": [], "setor": {}})
    monkeypatch.setattr(U, "linhas_pendentes", lambda: {"uso": [], "fracttal": []})
    monkeypatch.setattr(C, "instantaneo", lambda: [])


@pytest.fixture
def banco(app):
    """Um banco com os 7 dias gravados e posto no app como o dos outros testes (`nexus_dados_sessao`)."""
    api = ApiPGFalsa()
    F.gravar(USO_BANCO, FRACTTAL_BANCO, base="http://pg.falso", token="t", sessao=api)
    app.extensions["nexus_dados_sessao"] = api
    yield api
    app.extensions.pop("nexus_dados_sessao", None)


@pytest.fixture
def vivo(monkeypatch):
    """A memória do servidor: a hora aberta, o corte por setor e a hora que espera o banco."""
    monkeypatch.setattr(U, "instantaneo", lambda: {"linhas": USO_VIVO, "setor": SETOR})
    monkeypatch.setattr(C, "instantaneo", lambda: FRACTTAL_VIVO)


def _secao(html):
    ini = html.index('id="uso-os-creator"')
    return html[html.rindex("<section", 0, ini):html.index("</section>", ini)]


def _texto(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


# ── o que a seção calcula ────────────────────────────────────────────────────────────────────────────────────────────
def _modelo(banco_dados=None, vivo_dados=None, **kw):
    banco_dados = banco_dados if banco_dados is not None else {"uso": USO_BANCO, "fracttal": FRACTTAL_BANCO}
    vivo_dados = vivo_dados if vivo_dados is not None else {"uso": USO_VIVO, "fracttal": FRACTTAL_VIVO, "setor": SETOR}
    # o banco devolve a hora como inteiro, a memória como texto: a conta tem de aceitar os dois
    banco_dados = {"uso": [dict(l, hora_id=int(l["hora_id"])) for l in banco_dados["uso"]],
                   "fracttal": [dict(l, hora_id=int(l["hora_id"])) for l in banco_dados["fracttal"]]}
    return R.montar_uso_os(AGORA, banco_dados, vivo_dados, **kw)


def test_as_rotas_mais_pedidas_separam_clique_e_automatico():
    rotas = _modelo()["rotas"]
    assert [r["rota"] for r in rotas] == ["/os/_nexus/sessao", "/os/historico", "/os/os/<n>"]       # por pedidos, os dois tipos
    sessao, historico, card = rotas
    assert (sessao["cliques"], sessao["automaticos"]) == (0, 200)
    # o historico: 40+60+55 (a memória vence o banco em 30/10 10h)+5 de clique, e 10 automáticos
    assert (historico["cliques"], historico["automaticos"]) == (160, 10)
    assert (card["cliques"], card["automaticos"]) == (60, 0) and card["fracttal"] == 180 and card["erros"] == 2
    assert card["ocupado"] == 1
    assert "/os/antiga" not in [r["rota"] for r in rotas]                                           # 20/10 está fora da janela


def test_mediana_e_p95_das_horas_pesadas_pelos_pedidos_atendidos():
    """As horas guardam só a mediana e o p95 de cada uma: juntar horas é o quantil dos quantis, pesado pelos pedidos que
    tiveram duração (o recusado pelo teto não tem). É aproximado, e a seção diz."""
    historico = next(r for r in _modelo()["rotas"] if r["rota"] == "/os/historico")
    # medianas 100 (60 pedidos), 130 (5), 140 (55), 250 (10), 300 (40): a posição 85 de 170 cai no 140
    assert historico["p50_ms"] == 140
    assert historico["p95_ms"] == 2000                                                              # a cauda de 40 pedidos
    card = next(r for r in _modelo()["rotas"] if r["rota"] == "/os/os/<n>")
    # 450 (9 atendidos: 10 pedidos menos 1 ocupado), 500 (20) e 700 (30): a metade de 59 cai no 700; o p95, no 6000
    assert (card["p50_ms"], card["p95_ms"]) == (700, 6000)


def test_so_as_15_rotas_mais_pedidas():
    uso = [_uso("2026103010", f"/os/tela{i:02d}", 0, pedidos_qtd=100 - i) for i in range(20)]
    rotas = _modelo({"uso": uso, "fracttal": []}, {"uso": [], "fracttal": [], "setor": {}})["rotas"]
    assert len(rotas) == 15 and rotas[0]["rota"] == "/os/tela00" and rotas[-1]["rota"] == "/os/tela14"


def test_duracao_vazia_fica_vazia():
    uso = [_uso("2026103010", "/os/api/ocupada", 0, pedidos_qtd=4, ocupado_qtd=4, duracao_p50_ms=None, duracao_p95_ms=None)]
    r = _modelo({"uso": uso, "fracttal": []}, {"uso": [], "fracttal": [], "setor": {}})["rotas"][0]
    assert r["p50_ms"] is None and r["p95_ms"] is None and r["ocupado"] == 4


def test_cliques_e_pedidos_ao_fracttal_por_hora_do_dia():
    horas = {h["hora"]: h for h in _modelo()["horas"]}
    assert sorted(horas) == list(range(24))
    # 10h: cliques 40+20 (28/10) + 60 (29/10) + 55+10 (30/10); automáticos 10 (28/10) + 200 (29/10)
    assert (horas[10]["cliques"], horas[10]["automaticos"]) == (185, 210)
    assert (horas[11]["cliques"], horas[14]["cliques"]) == (5, 30) and horas[3]["cliques"] == 0
    # o total do Fracttal vem da linha `*` da hora (nunca da soma do detalhe, que contaria em dobro): 150 + 400 às 10h
    assert horas[10]["fracttal"] == 550 and horas[14]["fracttal"] == 900 and horas[11]["fracttal"] == 50
    assert horas[10]["pico"] == 205 and horas[14]["pico"] == 188 and horas[11]["pico"] == 30 and horas[3]["pico"] == 0


def test_a_cota_de_200_e_a_palavra_do_pico():
    horas = {h["hora"]: h for h in _modelo()["horas"]}
    assert _modelo()["cota"] == 200 == C.COTA_POR_MINUTO
    assert horas[10]["situacao"] == "na cota" and horas[10]["tom"] == "critico"          # 205 de 200
    assert horas[14]["situacao"] == "perto da cota" and horas[14]["tom"] == "alerta"     # 188 de 200
    assert horas[11]["situacao"] == "" and horas[11]["tom"] == "" and horas[11]["pct_cota"] == 15
    assert horas[10]["pct_cota"] == 100                                                  # a barra não passa da caixa


def test_por_dia_para_o_antes_e_o_depois():
    dias = _modelo()["dias"]
    assert [d["dia"] for d in dias] == ["24/10", "25/10", "26/10", "27/10", "28/10", "29/10", "30/10"]
    assert [d["semana"] for d in dias] == ["sáb", "dom", "seg", "ter", "qua", "qui", "sex"]
    d28, d29, d30 = dias[4], dias[5], dias[6]
    assert (d28["cliques"], d28["automaticos"], d28["fracttal"], d28["recusas"], d28["pico"]) == (60, 10, 150, 0, 120)
    assert (d29["cliques"], d29["automaticos"], d29["fracttal"], d29["recusas"], d29["pico"]) == (90, 200, 900, 3, 188)
    assert d29["pico_hora"] == 14 and d30["pico"] == 205 and d30["pico_hora"] == 10 and d30["fracttal"] == 450
    assert d30["hoje"] is True and d28["hoje"] is False and dias[0]["cliques"] == 0 and dias[0]["pico"] == 0


def test_a_memoria_vence_o_banco_na_mesma_chave_e_a_hora_nao_e_contada_duas_vezes():
    antes = _modelo(vivo_dados={"uso": [], "fracttal": [], "setor": {}})["rotas"]
    com = _modelo()["rotas"]
    h_antes = next(r for r in antes if r["rota"] == "/os/historico")
    h_com = next(r for r in com if r["rota"] == "/os/historico")
    assert h_antes["cliques"] == 150 and h_com["cliques"] == 160     # 50 virou 55 (a memória vence), e as 5 da hora aberta somam


def test_o_corte_por_setor_so_vem_da_memoria_e_so_dos_7_dias():
    setores = _modelo()["setores"]
    assert [s["setor"] for s in setores] == [SETOR_A, SETOR_B, "(sem setor)"]
    a = setores[0]
    assert (a["cliques"], a["automaticos"]) == (62, 5) and a["rotas"][0] == {"rota": "/os/historico", "cliques": 50}
    assert a["rotas"][1] == {"rota": "/os/os/<n>", "cliques": 12}
    assert "/os/velha" not in repr(setores)                          # 01/10 está fora dos 7 dias
    # sem a memória do servidor (o PC, o banco que o servidor não cortou) não há corte: o banco nunca o tem
    assert _modelo(vivo_dados={"uso": [], "fracttal": [], "setor": {}})["setores"] == []


def test_sem_nada_nao_tem():
    assert _modelo({"uso": [], "fracttal": []}, {"uso": [], "fracttal": [], "setor": {}})["tem"] is False
    assert R.montar_uso_os(AGORA, None, {"uso": [], "fracttal": [], "setor": {}})["tem"] is False
    assert _modelo()["tem"] is True


# ── a página ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_secao_com_dado(app, logado, banco, vivo):
    r = logado.get("/t/base/raio-x")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    sec = _secao(html)
    txt = _texto(sec)
    assert "Uso do OS Creator" in txt and "Sem medição ainda" not in txt
    # as telas mais pedidas, os cliques e os automáticos separados, a mediana e o p95
    for coluna in ("Cliques", "Automáticos", "Mediana", "p95"):
        assert coluna in txt, coluna
    assert "/os/historico" in sec and "/os/_nexus/sessao" in sec and "/os/os/&lt;n&gt;" in sec
    assert "/os/antiga" not in sec                                                  # fora da janela
    assert "140 ms" in txt and "2,0 s" in txt                                       # 140 ms de mediana; 2000 ms viram 2,0 s
    # os pedidos ao Fracttal por hora, o pico por minuto e a cota ao lado
    assert "Fracttal" in txt and "205" in txt and "200" in txt and "na cota" in txt and "perto da cota" in txt
    # o corte por setor, e a nota de que mora no disco do servidor
    assert SETOR_A in sec and SETOR_B in sec and "(sem setor)" in sec
    assert "só no disco do servidor" in txt and "30 dias" in txt
    # uma só leitura do banco, e a página traz o link para a seção
    assert "#uso-os-creator" in html


def test_a_pagina_so_pede_ao_banco_uma_vez_em_10_minutos(app, logado, banco, vivo, monkeypatch):
    agora = [1000.0]
    monkeypatch.setattr(R, "_monotonico", lambda: agora[0])
    listagens = []
    pega = banco.get

    def conta(url, params=None, headers=None, timeout=None):
        if url.endswith("/api/sheets"):
            listagens.append(url)
        return pega(url, params=params, headers=headers, timeout=timeout)
    monkeypatch.setattr(banco, "get", conta)
    logado.get("/t/base/raio-x")
    logado.get("/t/base/raio-x")
    agora[0] += R.CACHE_USO_S - 1
    logado.get("/t/base/raio-x")
    assert len(listagens) == 1                                                     # a cópia de 10 min serve as três
    agora[0] += 2                                                                   # passou dos 10 min
    html = logado.get("/t/base/raio-x").get_data(as_text=True)
    assert len(listagens) == 2 and "Uso do OS Creator" in html


def test_secao_sem_dado(app, logado):
    """O PC e o teste: sem banco e sem o registro do servidor, a seção diz que não mediu e a página abre."""
    r = logado.get("/t/base/raio-x")
    assert r.status_code == 200
    txt = _texto(_secao(r.get_data(as_text=True)))
    assert "Sem medição ainda" in txt and "Por hora do dia" not in txt


def test_banco_fora_sem_nada_na_memoria_diz_o_motivo(app, logado):
    class Cai:
        def get(self, *a, **k):
            raise requests.ConnectionError("banco fora")
    app.extensions["nexus_dados_sessao"] = Cai()
    try:
        r = logado.get("/t/base/raio-x")
        assert r.status_code == 200
        txt = _texto(_secao(r.get_data(as_text=True)))
        assert "Sem medição ainda" in txt and "ConnectionError" in txt
        assert "banco fora" not in txt                                              # a mensagem do erro não vai à página
    finally:
        app.extensions.pop("nexus_dados_sessao", None)


def test_banco_fora_com_a_memoria_mostra_a_memoria(app, logado, vivo):
    class Cai:
        def get(self, *a, **k):
            raise requests.ConnectionError("banco fora")
    app.extensions["nexus_dados_sessao"] = Cai()
    try:
        txt = _texto(_secao(logado.get("/t/base/raio-x").get_data(as_text=True)))
        assert "Sem medição ainda" not in txt and "/os/historico" in txt
        assert "não respondeu" in txt and "memória" in txt                          # diz que é só a memória desde o reinício
    finally:
        app.extensions.pop("nexus_dados_sessao", None)


def test_a_falha_nao_e_repetida_a_cada_abertura(app, logado, monkeypatch):
    chamadas = []

    class Cai:
        def get(self, *a, **k):
            chamadas.append(1)
            raise requests.ConnectionError("x")
    app.extensions["nexus_dados_sessao"] = Cai()
    agora = [5000.0]
    monkeypatch.setattr(R, "_monotonico", lambda: agora[0])
    try:
        logado.get("/t/base/raio-x")
        logado.get("/t/base/raio-x")                                                # dentro do minuto de espera: não tenta
        assert len(chamadas) == 1
        agora[0] += R.ESPERA_APOS_FALHA_S + 1
        logado.get("/t/base/raio-x")
        assert len(chamadas) == 2
    finally:
        app.extensions.pop("nexus_dados_sessao", None)


def test_banco_lento_nao_trava_a_pagina(app, logado, monkeypatch):
    solta = threading.Event()

    class Lento:
        def get(self, *a, **k):
            solta.wait(10)
            raise requests.ConnectionError("tarde demais")
    monkeypatch.setattr(R, "PRAZO_USO_S", 0.2)
    app.extensions["nexus_dados_sessao"] = Lento()
    try:
        t0 = time.monotonic()
        r = logado.get("/t/base/raio-x")
        assert r.status_code == 200 and time.monotonic() - t0 < 3                   # a página não esperou os 10 s
        txt = _texto(_secao(r.get_data(as_text=True)))
        assert "Sem medição ainda" in txt and "lendo" in txt.lower()
        t0 = time.monotonic()
        logado.get("/t/base/raio-x")                                                # a leitura presa não abre outra
        assert time.monotonic() - t0 < 3
    finally:
        solta.set()
        app.extensions.pop("nexus_dados_sessao", None)


def test_banco_com_livro_ainda_inexistente_e_sem_medicao(app, logado):
    app.extensions["nexus_dados_sessao"] = ApiPGFalsa()                             # o servidor ainda não gravou nenhuma hora
    try:
        txt = _texto(_secao(logado.get("/t/base/raio-x").get_data(as_text=True)))
        assert "Sem medição ainda" in txt and "nenhuma hora gravada" in txt.lower()
    finally:
        app.extensions.pop("nexus_dados_sessao", None)


def test_hora_que_espera_o_banco_aparece_na_secao(app, logado, banco, vivo, monkeypatch):
    espera = {"uso": [_uso("2026103009", "/os/so_na_espera", 0, pedidos_qtd=7)], "fracttal": []}
    monkeypatch.setattr(U, "linhas_pendentes", lambda: espera)
    sec = _secao(logado.get("/t/base/raio-x").get_data(as_text=True))
    assert "/os/so_na_espera" in sec


def test_a_secao_nunca_derruba_a_pagina(app, logado, monkeypatch):
    def quebra(*a, **k):
        raise RuntimeError("defeito na conta")
    monkeypatch.setattr(R, "montar_uso_os", quebra)
    r = logado.get("/t/base/raio-x")
    assert r.status_code == 200
    assert "Sem medição ainda" in _texto(_secao(r.get_data(as_text=True)))


def test_so_administrador_ve_a_secao(app, cliente):
    c = app.test_client()
    with c.session_transaction() as s:
        s["logado"], s["admin"] = True, False
        s["usuario"] = {"email": "pessoa@exemplo.invalid", "nome": "Pessoa", "perfil": ""}
    assert c.get("/t/base/raio-x").status_code == 403


# ── as cores só por token ────────────────────────────────────────────────────────────────────────────────────────────
def test_sem_cor_fixa(app, logado, banco, vivo):
    """Nem #hex nem rgba() no template, no CSS da página, nem estilo de cor no HTML que a seção gera (a largura da barra é a
    única coisa em `style`)."""
    for arquivo in ("nexus/templates/raio_x.html", "nexus/static/cadastro.css"):
        t = (AQUI / arquivo).read_text(encoding="utf-8")
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", t) and "rgba(" not in t, arquivo
    sec = _secao(logado.get("/t/base/raio-x").get_data(as_text=True))
    estilos = re.findall(r'style="([^"]*)"', sec)
    assert estilos and all(re.fullmatch(r"width:\d{1,3}%", e) for e in estilos), estilos
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", sec)
    # o tom é classe (palavra e cor por token), e a palavra vem junto: nunca só a cor
    assert "rx-tom--critico" in sec and "na cota" in sec and "rx-tom--alerta" in sec and "perto da cota" in sec
    css = (AQUI / "nexus/static/cadastro.css").read_text(encoding="utf-8")
    for classe in ("rx-barra", "rx-tom--critico", "rx-tom--alerta", "rx-sub"):
        assert classe in css, classe


def test_endereco_nunca_a_partir_da_raiz(app, logado, banco, vivo):
    t = (AQUI / "nexus/templates/raio_x.html").read_text(encoding="utf-8")
    assert not re.search(r'(?:href|src|action)="/', t)

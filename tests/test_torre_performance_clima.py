"""Torre Performance -> Clima e risco: a tela /t/performance/clima (06/10/2026).

Mundo inventado e pequeno: cinco usinas numa grade de 40 x 30 pixels, um aviso do INMET por cima de duas delas, um foco
perto de uma, o risco de fogo em quatro dias. Tudo por sessão falsa (nenhum teste vai à rede) e relógio de mentira."""
import json
import re
from datetime import datetime, timedelta, timezone

import pytest

from nexus import create_app
from nexus.cadastro.cifra import gerar_chave
from nexus.cadastro.servico import Carga
from nexus.performance.clima import leitura as L
from nexus.performance.clima import visao as V
from nexus.performance.clima.geotiff import Amostra

from clima_cog import SessaoArquivos, montar_cog
from conftest import SENHA_TESTE

BRT = timezone(timedelta(hours=-3))
AGORA = datetime(2026, 10, 6, 15, 0, tzinfo=BRT)
URL_INMET = "https://inmet.exemplo.test/ativos"
BASE_FOCOS = "https://inpe.exemplo.test/focos/"
RISCO = "https://inpe.exemplo.test/risco/RF.PREV.T{d}.tif"
X0, Y0, D = -45.0, -5.0, 0.01


def centro(col, lin):
    """(lat, lon) do centro do pixel; o cadastro de teste usa estes pontos."""
    return Y0 - (lin + 0.5) * D, X0 + (col + 0.5) * D


# coluna e linha de cada usina na grade do INPE
A, B, C, DD, F, G = (5, 5), (10, 10), (15, 15), (20, 20), (25, 25), (35, 5)


def caixa_aviso(id_, nome, severidade, lon0, lon1, lat0, lat1, evento="Tempestade", inicio="2026-10-06 09:10",
                fim="2026-10-06 23:59"):
    ring = [[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]
    return {"id": id_, "descricao": evento or nome, "severidade": severidade, "inicio": inicio, "fim": fim,
            "poligono": json.dumps({"type": "Polygon", "coordinates": [ring]})}


def inmet(extra_hoje=(), extra_futuro=()):
    # nível 1 sobre A e B; nível 2 só sobre A
    leve = caixa_aviso(1, "leve", "Perigo Potencial", -45.0, -44.88, -5.15, -5.0, evento="Baixa Umidade")
    forte = caixa_aviso(2, "forte", "Perigo", -45.0, -44.93, -5.08, -5.02)
    return json.dumps({"hoje": [leve, forte, *extra_hoje], "futuro": list(extra_futuro)}).encode()


def nome_foco(hh, mm):
    return f"focos_10min_20261006_{hh:02d}{mm:02d}.csv"


def focos():
    lat_a, lon_a = centro(*A)
    perto = f"{lat_a + 1.2 / 111.195:.6f}, {lon_a:.6f},GOES-19,2026-10-06 17:50:00"           # 1,2 km de A (14:50 em Brasília)
    longe = "-9.000000, -40.000000,NOAA-21,2026-10-06 17:40:00"
    arquivos = {nome_foco(17, 50): ("lat,lon,satelite,data\n" + perto + "\n" + longe + "\n").encode()}
    indice = "".join(f'<a href="{n}">{n}</a>' for n in arquivos).encode()
    return {BASE_FOCOS: indice, **{BASE_FOCOS + n: c for n, c in arquivos.items()}}


def grade_risco(dia):
    g = [[0.05] * 40 for _ in range(30)]
    g[A[1]][A[0]] = 0.97
    g[B[1]][B[0]] = 0.30
    g[C[1]][C[0]] = [0.75, 0.80, 0.60, 0.40][dia]
    g[DD[1]][DD[0]] = 0.10
    g[F[1]][F[0]] = None                                       # pixel mascarado; só o vizinho tem valor
    g[F[1]][F[0] + 1] = 0.85
    for dl in range(-2, 3):                                    # G: nada de dado num raio de 2 pixels
        for dc in range(-2, 3):
            g[G[1] + dl][G[0] + dc] = None
    return g


def arquivos_do_mundo(inmet_bytes=None, risco=True):
    a = {URL_INMET: inmet_bytes if inmet_bytes is not None else inmet(), **focos()}
    if risco:
        for d in range(4):
            a[RISCO.format(d=d)] = montar_cog(grade_risco(d), origem=(X0, Y0), escala=D)
    return a


def u(id_, nome, cliente, pos, uf="PI"):
    v = {"nome": nome, "status": "OPERAÇÃO", "cliente": cliente, "uf": uf, "cidade": "Cidade"}
    if pos:
        v["latitude"], v["longitude"] = centro(*pos)
    return {"id": id_, "ordem": int(id_), "valores": v}


def carga():
    return Carga(
        entidades={
            "clientes": [{"id": "1", "ordem": 1, "valores": {"nome": "Cliente X"}},
                         {"id": "2", "ordem": 2, "valores": {"nome": "Cliente Y"}}],
            "usinas": [u("1", "Usina Alfa", "1", A), u("2", "Usina Beta", "1", B), u("3", "Usina Gama", "2", C),
                       u("4", "Usina Delta", "2", DD), u("5", "Usina Epsilon", "1", None), u("6", "Usina Zeta", "2", F),
                       u("7", "Usina Eta", "1", G)],
        },
        listas={"status_usina": ["OPERAÇÃO"], "uf": ["PI"]})


class Relogio:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def mundo(tmp_path, monkeypatch):
    chave = gerar_chave()
    app = create_app({"NEXUS_SECRET_KEY": "k", "NEXUS_SENHA_ADMIN": SENHA_TESTE, "NEXUS_CHAVE_CADASTRO": chave,
                      "NEXUS_ARMAZEM_LOCAL": str(tmp_path / "cadastro.json"),
                      "NEXUS_CLIMA_INMET_URL": URL_INMET, "NEXUS_CLIMA_FOCOS_URL": BASE_FOCOS, "NEXUS_CLIMA_RISCO_URL": RISCO})
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    with app.app_context():
        from nexus.cadastro.telas import servico
        servico().aplicar_carga(carga())
    sessao = SessaoArquivos(arquivos_do_mundo())
    L.limpar_cache()
    L.usar_relogio(Relogio(AGORA.timestamp()))
    L.usar_sessao(sessao)
    monkeypatch.setattr(V, "agora", lambda: AGORA)
    cliente = app.test_client()
    assert cliente.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    yield cliente, sessao, app
    L.usar_sessao(None)
    L.usar_relogio(None)
    L.limpar_cache()


def pagina(c, url="/t/performance/clima", **consulta):
    r = c.get(url, query_string=consulta or None)
    assert r.status_code == 200
    return r.get_data(as_text=True)


def texto(html):
    """O texto visível, sem marcação, para conferir frases."""
    sem_css = re.sub(r"<(style|script)\b.*?</\1>", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", sem_css))


def cartoes(html):
    """{nome da usina: trecho do cartão} na ordem em que aparecem na lista de alertas."""
    achados = re.findall(r'<article class="cl-usina[^"]*".*?</article>', html, flags=re.S)
    return {re.search(r'<h3 class="cl-nome">([^<]+)</h3>', a).group(1): a for a in achados}


# ── a tela ───────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_exige_login(mundo):
    _, _, app = mundo
    assert app.test_client().get("/t/performance/clima").status_code == 302


def test_a_tela_responde_com_titulo_pergunta_e_atualiza_sozinha(mundo):
    c, _, _ = mundo
    html = pagina(c)
    assert "Clima e risco" in html and "Em construção" not in html
    assert '<meta http-equiv="refresh" content="60">' in html


def test_a_tela_aparece_como_pronta_no_menu(mundo):
    c, _, _ = mundo
    assert 'href="/t/performance/clima" class="com-conteudo"' in pagina(c, "/")


def test_faixa_de_resumo_conta_usinas_por_tipo_de_alerta(mundo):
    c, _, _ = mundo
    t = texto(pagina(c))
    # avisos: Alfa e Beta; focos: Alfa; risco alto ou crítico: Alfa (crítico), Gama (alto), Zeta (alto, pelo entorno)
    resumo = re.search(r'<section class="cl-resumo".*?</section>', pagina(c), flags=re.S).group(0)
    cartoes_resumo = {m.group(1): m.group(2) for m in re.finditer(
        r'<div class="cl-num[^"]*" data-id="(\w+)">.*?<span class="cl-valor">([^<]+)</span>', resumo, flags=re.S)}
    assert cartoes_resumo == {"avisos": "2", "focos": "1", "risco": "3"}
    assert "Alertas calculados para 6 usinas em operação com coordenada" in t


def test_resumo_do_risco_conta_cada_dia(mundo):
    c, _, _ = mundo
    t = texto(pagina(c))
    # D0: Alfa, Gama (0,75), Zeta; D+1: Alfa, Gama (0,80), Zeta; D+2: Alfa, Zeta (Gama cai para médio); D+3: Alfa, Zeta
    assert "hoje 3 · D+1 3 · D+2 2 · D+3 2" in t


def test_lista_so_das_usinas_com_alerta_da_mais_grave_para_a_menos(mundo):
    c, _, _ = mundo
    html = pagina(c)
    nomes = list(cartoes(html))
    # Alfa: foco + crítico (nível 3); Gama e Zeta: risco alto (2); Beta: aviso Perigo Potencial (1). Delta e Eta não têm alerta.
    assert nomes == ["Usina Alfa", "Usina Gama", "Usina Zeta", "Usina Beta"]
    assert "Usina Delta" not in html and "Usina Eta" not in html.replace("Usina Eta.", "")     # a Eta só entra na linha de cobertura
    assert "2 usinas sem alerta agora" in texto(html)


def test_cartao_do_aviso_mostra_evento_severidade_e_validade(mundo):
    c, _, _ = mundo
    alfa = texto(cartoes(pagina(c))["Usina Alfa"])
    assert "Tempestade" in alfa and "Perigo" in alfa and "Baixa Umidade" in alfa and "Perigo Potencial" in alfa
    assert "em vigor, até 23:59" in alfa


def test_cartao_do_foco_mostra_quantos_o_mais_perto_satelite_e_hora(mundo):
    c, _, _ = mundo
    alfa = texto(cartoes(pagina(c))["Usina Alfa"])
    assert "1 foco a até 5 km" in alfa and "o mais perto a 1,2 km" in alfa and "GOES-19" in alfa and "14:50" in alfa
    assert "foco" not in texto(cartoes(pagina(c))["Usina Gama"]).lower().replace("focos de queimada", "")


def test_cartao_do_risco_mostra_classe_e_valor_dos_quatro_dias(mundo):
    c, _, _ = mundo
    gama = texto(cartoes(pagina(c))["Usina Gama"])
    assert "Hoje 0,75 alto" in gama and "D+1 0,80 alto" in gama and "D+2 0,60 médio" in gama and "D+3 0,40 médio" in gama
    alfa = texto(cartoes(pagina(c))["Usina Alfa"])
    assert alfa.count("0,97 crítico") == 4


def test_pixel_mascarado_usa_o_entorno_e_diz_entorno(mundo):
    c, _, _ = mundo
    zeta = texto(cartoes(pagina(c))["Usina Zeta"])
    assert "0,85 alto" in zeta and "entorno" in zeta
    assert "entorno" not in texto(cartoes(pagina(c))["Usina Gama"])


def test_sem_dado_nem_no_entorno_diz_sem_vegetacao_e_nao_e_alerta(mundo):
    c, _, _ = mundo
    html = pagina(c)
    assert "Usina Eta" not in "".join(cartoes(html))          # sem alerta, não vira cartão
    # mas a linha de cobertura diz quais usinas não têm dado de risco, e por quê
    assert "Risco de fogo sem dado (sem vegetação no entorno): Usina Eta." in texto(html)


@pytest.mark.parametrize("origem,valor,esperado", [
    ("ponto", 0.97, ("0,97", "crítico", "", 3)),
    ("ponto", 0.30, ("0,30", "baixo", "", 0)),
    ("entorno", 0.85, ("0,85", "alto", "entorno", 2)),
    ("sem_dado", None, ("sem dado (sem vegetação no entorno)", "", "", 0)),
    ("indisponivel", None, ("indisponível", "", "", 0)),
    ("fora_da_grade", None, ("fora da grade do INPE", "", "", 0)),
])
def test_cada_dia_de_risco_e_escrito_pela_origem_do_valor(origem, valor, esperado):
    from nexus.performance.clima.geotiff import Amostra
    c = V.celula_de_risco(2, Amostra(valor, origem))
    assert c["rotulo"] == "D+2"
    assert (c["valor"], c["classe"], c["nota"], c["nivel"]) == esperado


def test_usina_sem_coordenada_aparece_numa_linha_e_a_coordenada_nunca_aparece(mundo):
    c, _, _ = mundo
    html = pagina(c)
    t = texto(html)
    assert "Sem coordenada no cadastro" in t and "Usina Epsilon" in t
    for linha_col in (A, B, C, DD, F, G):
        lat, lon = centro(*linha_col)
        for numero in (f"{abs(lat):.3f}", f"{abs(lon):.3f}", f"{abs(lat):.3f}".replace(".", ","), f"{abs(lon):.3f}".replace(".", ",")):
            assert numero not in html, numero


def test_filtro_por_cliente(mundo):
    c, _, _ = mundo
    html = pagina(c, cliente="Cliente Y")
    assert list(cartoes(html)) == ["Usina Gama", "Usina Zeta"]
    assert "Alertas calculados para 3 usinas em operação com coordenada" in texto(html)
    assert 'value="Cliente Y" selected' in html
    assert "Usina Epsilon" not in html                         # a sem coordenada de outro cliente não aparece
    assert len(cartoes(pagina(c, cliente="Nao Existe"))) == 4                  # cliente inventado = sem filtro


def test_todos_os_clientes_estao_no_seletor(mundo):
    c, _, _ = mundo
    html = pagina(c)
    assert re.search(r'<select[^>]*name="cliente"', html) and 'value="Cliente X"' in html and 'value="Cliente Y"' in html


def test_cada_fonte_diz_de_quando_e_o_dado(mundo):
    c, _, _ = mundo
    t = texto(pagina(c))
    assert "INMET" in t and "lido às 15:00" in t
    assert "arquivos até 14:50" in t                                       # o arquivo é de 17:50 UTC = 14:50 em Brasília
    assert "previsão de 06/10 (arquivo das 06:32)" in t                    # Last-Modified da sessão falsa: 09:32 GMT = 06:32 em Brasília
    html = pagina(c)
    assert len(re.findall(r'class="cl-fonte cl-ok"', html)) == 3


def test_fonte_fora_diz_fora_e_a_hora_da_ultima_boa(mundo):
    c, sessao, _ = mundo
    pagina(c)                                                              # lê tudo uma vez (15:00)
    L.usar_relogio(Relogio(AGORA.timestamp() + L.TTL_AVISOS_S + 60))      # o INMET venceu
    del sessao.arquivos[URL_INMET]                                        # e agora dá 404
    html = pagina(c)
    t = texto(html)
    assert "INMET fora agora; última leitura boa às 15:00" in t
    assert "HTTP 404" in t
    assert 'class="cl-fonte cl-atencao"' in html
    assert len(cartoes(html)) == 4                                        # as outras fontes seguem valendo


def test_fonte_que_nunca_leu_diz_sem_leitura_boa_e_nao_mostra_zero(mundo):
    c, sessao, _ = mundo
    del sessao.arquivos[URL_INMET]
    html = pagina(c)
    t = texto(html)
    assert "INMET fora agora; ainda sem leitura boa" in t
    assert "A lista e os números acima não incluem: avisos do INMET." in t       # a lista diz que está incompleta
    assert 'class="cl-fonte cl-fora"' in html
    resumo = re.search(r'<section class="cl-resumo".*?</section>', html, flags=re.S).group(0)
    assert re.search(r'data-id="avisos">.*?<span class="cl-valor">—</span>', resumo, flags=re.S)       # traço, nunca "0"


def test_texto_do_inmet_e_de_terceiros_e_sai_escapado(mundo):
    c, sessao, _ = mundo
    veneno = caixa_aviso(9, "x", "Perigo <b>Grande</b>", -45.0, -44.9, -5.15, -5.0, evento='<script>alert("oi")</script>')
    sessao.arquivos[URL_INMET] = inmet(extra_hoje=[veneno])
    html = pagina(c)
    assert '<script>alert("oi")</script>' not in html and "<b>Grande</b>" not in html
    assert "&lt;script&gt;" in html and "&lt;b&gt;Grande&lt;/b&gt;" in html


def test_cor_do_inmet_nunca_vira_estilo(mundo):
    c, sessao, _ = mundo
    ruim = caixa_aviso(9, "x", "Perigo", -45.0, -44.9, -5.15, -5.0)
    ruim["aviso_cor"] = '"><script>x</script>'
    sessao.arquivos[URL_INMET] = inmet(extra_hoje=[ruim])
    assert "<script>x</script>" not in pagina(c)


def test_aviso_que_ainda_vai_comecar_diz_quando_comeca(mundo):
    c, sessao, _ = mundo
    futuro = caixa_aviso(9, "x", "Perigo", -45.0, -44.88, -5.15, -5.0, evento="Onda de Calor", inicio="2026-10-07 08:00",
                         fim="2026-10-08 20:00")
    sessao.arquivos[URL_INMET] = inmet(extra_futuro=[futuro])
    beta = texto(cartoes(pagina(c))["Usina Beta"])
    assert "Onda de Calor" in beta and "começa 07/10 08:00, até 08/10 20:00" in beta


def test_previsao_de_risco_de_ontem_fica_em_atencao_e_diz_a_data(mundo):
    c, sessao, _ = mundo
    sessao.modificado = "Mon, 05 Oct 2026 09:32:00 GMT"
    html = pagina(c)
    assert "previsão de 05/10 (arquivo das 06:32)" in texto(html) and "de ontem" in texto(html)
    assert 'class="cl-fonte cl-atencao"' in html


def test_focos_sem_arquivo_novo_ha_mais_de_30_min_ficam_em_atencao(mundo):
    c, sessao, _ = mundo
    antigo = nome_foco(17, 10)                                              # 14:10 em Brasília, e agora são 15:00
    sessao.arquivos = {k: v for k, v in sessao.arquivos.items() if not k.startswith(BASE_FOCOS)}
    sessao.arquivos[BASE_FOCOS] = f'<a href="{antigo}">{antigo}</a>'.encode()
    sessao.arquivos[BASE_FOCOS + antigo] = b"lat,lon,satelite,data\n-9.0,-40.0,NOAA-21,2026-10-06 17:00:00\n"
    html = pagina(c)
    assert "o INPE não publica arquivo novo desde 14:10" in texto(html)
    assert 'class="cl-fonte cl-atencao"' in html


def test_aviso_vencido_nao_conta(mundo):
    c, sessao, _ = mundo
    vencido = caixa_aviso(9, "x", "Grande Perigo", -45.0, -44.9, -5.15, -5.0, evento="Vendaval", fim="2026-10-06 14:00")
    sessao.arquivos[URL_INMET] = inmet(extra_hoje=[vencido])
    assert "Vendaval" not in pagina(c)


def test_uma_so_leitura_da_rede_por_fonte_mesmo_com_varias_visitas(mundo):
    c, sessao, _ = mundo
    pagina(c)
    n = len(sessao.pedidos)
    pagina(c)
    pagina(c, "/t/performance/clima?cliente=Cliente X")                    # o filtro não muda o conjunto de pontos do risco
    assert len(sessao.pedidos) == n


def test_rodape_com_as_fontes_e_a_atribuicao(mundo):
    c, _, _ = mundo
    t = texto(pagina(c))
    assert "Dados: INMET, INPE (Programa Queimadas)." in t
    assert "Programa Queimadas" in t and "somente leitura" in t.lower()


# ── 375 px ───────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_375_px_a_tela_usa_as_classes_responsivas_e_o_css_as_quebra_em_uma_coluna(mundo):
    c, _, _ = mundo
    html = pagina(c)
    assert 'href="/static/clima.css"' in html
    css = c.get("/static/clima.css").get_data(as_text=True)
    # as grades da tela viram uma coluna só abaixo de 700 px, e o texto de terceiros quebra em vez de alargar a página
    midia = re.search(r"@media\s*\(max-width:\s*(\d+)px\)\s*\{(.*)\}\s*$", css, flags=re.S)
    assert midia and 375 < int(midia.group(1)) <= 820
    for classe in ("cl-resumo", "cl-fontes", "cl-lista", "cl-dias"):
        assert classe in html and classe in midia.group(2), classe
    assert "overflow-wrap:anywhere" in css and "min-width:0" in css


def test_375_px_nenhuma_largura_fixa_passa_da_tela_do_celular(mundo):
    c, _, _ = mundo
    css = c.get("/static/clima.css").get_data(as_text=True)
    fora_da_midia = re.sub(r"@media[^{]*\{.*\}\s*$", "", css, flags=re.S)
    for m in re.finditer(r"(?<![-\w])(?:min-)?width:\s*(\d+)px", fora_da_midia):
        assert int(m.group(1)) <= 340, m.group(0)


# ── sem cadastro ─────────────────────────────────────────────────────────────────────────────────────────────────────

def test_sem_cadastro_a_tela_responde_e_diz_o_que_falta(app, logado):
    r = logado.get("/t/performance/clima")
    assert r.status_code == 200
    t = texto(r.get_data(as_text=True))
    assert "Clima e risco" in t and "Cadastro indisponível" in t and "NEXUS_CHAVE_CADASTRO" in t


def test_cadastro_sem_usina_com_coordenada_diz_isso(tmp_path, monkeypatch):
    chave = gerar_chave()
    app = create_app({"NEXUS_SECRET_KEY": "k", "NEXUS_SENHA_ADMIN": SENHA_TESTE, "NEXUS_CHAVE_CADASTRO": chave,
                      "NEXUS_ARMAZEM_LOCAL": str(tmp_path / "c.json")})
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    with app.app_context():
        from nexus.cadastro.telas import servico
        servico().aplicar_carga(Carga(entidades={"usinas": [u("1", "Usina Sozinha", "", None)]}, listas={"status_usina": ["OPERAÇÃO"]}))
    cl = app.test_client()
    cl.post("/entrar", data={"senha": SENHA_TESTE})
    t = texto(cl.get("/t/performance/clima").get_data(as_text=True))
    assert "Nenhuma usina em operação com coordenada" in t and "Usina Sozinha" in t


# ── a tela não parece "tudo bem" quando a fonte não foi lida inteira ──────────────────────────────────────────────────

def _leitura(dados, **kw):
    return L.Leitura(dados, AGORA.timestamp(), **kw)


def _focos_vazio():
    return _leitura({"focos": [], "arquivos": ["a.csv"], "falhos": [], "ate": datetime(2026, 10, 6, 17, 50, tzinfo=timezone.utc),
                     "linhas_ruins": 0})


def _risco(por=None):
    por = por or {str(i): [Amostra(0.1, "ponto")] * 4 for i in range(1, 8)}
    return _leitura({"por_ponto": por, "arquivos": {0: datetime(2026, 10, 6, 9, 32, tzinfo=timezone.utc)}, "erros": {}})


def _instalar(monkeypatch, avisos, focos, risco):
    monkeypatch.setattr(L, "avisos", lambda config, sessao=None: avisos)
    monkeypatch.setattr(L, "focos", lambda config, sessao=None: focos)
    monkeypatch.setattr(L, "risco", lambda config, pontos, sessao=None: risco)


def test_sem_alerta_e_com_fonte_fora_a_tela_nao_diz_nenhuma_usina_com_alerta_agora(mundo, monkeypatch):
    c, _, _ = mundo
    _instalar(monkeypatch, L.Leitura(None, None, erro="HTTP 500"), _focos_vazio(), _risco())
    html = pagina(c)
    t = texto(html)
    assert "Sem leitura de avisos do INMET: não dá para dizer que não há alerta" in t
    assert "Nenhuma usina com alerta agora" not in t and "sem alerta agora" not in t
    assert "usinas sem alerta nas fontes lidas." in t
    assert "A lista e os números acima não incluem: avisos do INMET." in t and "Lendo agora" not in t
    assert '<meta http-equiv="refresh" content="60">' in html


def test_fonte_lendo_a_tela_recarrega_em_10_s_e_a_nota_diz_lendo_e_nao_fora(mundo, monkeypatch):
    c, _, _ = mundo
    _instalar(monkeypatch, L.Leitura(None, None, erro=L.LENDO), _focos_vazio(), _risco())
    html = pagina(c)
    t = texto(html)
    assert '<meta http-equiv="refresh" content="10">' in html
    assert "Lendo agora: avisos do INMET." in t and "A lista e os números acima não incluem" not in t
    assert "Sem leitura de avisos do INMET: não dá para dizer que não há alerta" in t


def test_tudo_lido_e_sem_alerta_a_tela_pode_dizer_agora(mundo, monkeypatch):
    c, _, _ = mundo
    _instalar(monkeypatch, _leitura({"avisos": [], "ignorados": [], "lidos": 0}), _focos_vazio(), _risco())
    t = texto(pagina(c))
    assert "Nenhuma usina com alerta agora" in t and "6 usinas sem alerta agora." in t


def test_fonte_pela_metade_deixa_o_cartao_ambar_e_diz_parcial(mundo, monkeypatch):
    c, _, _ = mundo
    avisos = _leitura({"avisos": [], "ignorados": ["aviso 7: sem polígono"], "lidos": 1})
    _instalar(monkeypatch, avisos, _focos_vazio(), _risco())
    html = pagina(c)
    resumo = re.search(r'<section class="cl-resumo".*?</section>', html, flags=re.S).group(0)
    assert re.search(r'<div class="cl-num cl-na" data-id="avisos">.*?nenhum aviso sobre as usinas · parcial', resumo, flags=re.S)
    assert 'class="cl-fonte cl-atencao"' in html and "1 aviso foi ignorado" in texto(html)


def test_previsao_de_ontem_os_dias_do_cartao_dizem_ontem_e_hoje(mundo):
    c, sessao, _ = mundo
    sessao.modificado = "Mon, 05 Oct 2026 09:32:00 GMT"
    gama = texto(cartoes(pagina(c))["Usina Gama"])
    assert "Ontem 0,75 alto" in gama and "Hoje 0,80 alto" in gama and "D+1 0,60 médio" in gama and "D+2 0,40 médio" in gama


def test_usina_fora_da_grade_do_inpe_aparece_na_linha_de_cobertura_com_o_motivo(mundo, monkeypatch):
    c, _, _ = mundo
    por = {str(i): [Amostra(0.1, "ponto")] * 4 for i in range(1, 8)}
    por["6"] = [Amostra(None, "sem_dado")] * 4                        # Zeta
    por["7"] = [Amostra(None, "fora_da_grade")] * 4                   # Eta
    _instalar(monkeypatch, _leitura({"avisos": [], "ignorados": [], "lidos": 0}), _focos_vazio(), _risco(por))
    t = texto(pagina(c))
    assert "Risco de fogo sem dado (sem vegetação no entorno): Usina Zeta." in t
    assert "Risco de fogo sem dado (fora da grade do INPE): Usina Eta." in t


def test_o_css_tem_o_cartao_ambar_das_fontes_que_nao_estao_inteiras(mundo):
    c, _, _ = mundo
    css = c.get("/static/clima.css").get_data(as_text=True)
    assert ".cl-num.cl-na{border-left-color:var(--cl-atencao)}" in css and ".cl-num.cl-na .cl-valor{color:var(--cl-atencao)}" in css

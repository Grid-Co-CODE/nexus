# tests/test_performance_ponte.py
"""Ponte do Nexus para a plataforma de Performance (04/10/2026): só leitura, com o visual do Nexus."""
import pytest
import requests
from urllib3.util import parse_url

from nexus.performance import ponte as pt


def test_so_leitura_e_os_tres_posts_de_consulta_passam():
    assert pt.pode_passar("GET", "/api/sunop/data")
    assert pt.pode_passar("HEAD", "/tempo-real")
    for c in ("/api/os-performance/counts", "/api/os-creator/fractall-usinas", "/api/etm/os"):
        assert pt.pode_passar("POST", c), c
    assert not pt.pode_passar("POST", "/api/state/tracking")
    assert not pt.pode_passar("DELETE", "/api/state")


def test_pedido_leva_a_chave_o_prefixo_e_tira_o_force():
    # a chave de leitura da plataforma recusa force/forcar/run/backfill (disparam reconstrução, coleta ou backfill)
    p = pt.montar_pedido("http://plat:5050/", "k", "GET", "/api/pv/trackers/parados",
                         [("force", "1"), ("run", "1"), ("backfill", "1"), ("forcar", "1"), ("data", "2026-10-04")],
                         None, None)
    assert p["url"] == "http://plat:5050/api/pv/trackers/parados"
    assert p["params"] == [("data", "2026-10-04")]
    assert p["headers"]["X-Nexus-Leitura"] == "k"
    assert p["headers"]["X-Forwarded-Prefix"] == pt.PREFIXO
    assert "Cookie" not in p["headers"]
    # o salto é seguido por `enviar`, só no mesmo servidor: o `requests` seguiria para qualquer host, com a chave
    assert p["timeout"] == pt.TEMPO_LIMITE_S and p["allow_redirects"] is False


def test_post_de_consulta_leva_o_corpo_e_o_tipo():
    p = pt.montar_pedido("http://plat", "k", "POST", "/api/etm/os", [], b'{"usinas":["A"]}', "application/json")
    assert p["data"] == b'{"usinas":["A"]}' and p["headers"]["Content-Type"] == "application/json"


def test_resposta_sem_cookie_e_sem_cabecalho_de_salto():
    st, cab, corpo = pt.ajustar_resposta(200, {"Content-Type": "application/json", "Set-Cookie": "s=1",
                                               "Content-Length": "9", "Content-Encoding": "gzip",
                                               "Transfer-Encoding": "chunked", "Connection": "keep-alive",
                                               "Content-Disposition": "attachment; filename=x.csv"}, b"{}")
    assert st == 200 and corpo == b"{}"
    assert set(cab) == {"Content-Type", "Content-Disposition"}


def test_html_ganha_o_visual_e_o_guarda_de_leitura():
    st, cab, corpo = pt.ajustar_resposta(200, {"Content-Type": "text/html; charset=utf-8"},
                                         "<html><head><title>x</title></head><body></body></html>".encode())
    html = corpo.decode("utf-8")
    assert html.index('id="nexus-visual"') < html.index("</head>")
    assert 'id="nexus-leitura"' in html and "Somente leitura no Nexus" in html
    assert "/api/etm/os" in html                         # a lista de consulta vai ao guarda do navegador


def test_html_sem_head_tambem_recebe():
    assert 'id="nexus-leitura"' in pt.injetar("<body>x</body>")


def test_guarda_chega_ao_navegador_com_o_prefixo_e_a_regex_das_barras_finais():
    # a string do guarda passa por `%`; se sobrar um `%` solto ou a barra invertida dobrar, o JS quebra no navegador
    html = pt.injetar("<head></head>")
    assert 'P="/t/performance/plataforma"' in html
    assert r"c.replace(/\/+$/,'')" in html              # no JS: /\/+$/ (barras finais), com UMA barra invertida
    assert "%s" not in html


def test_cabecalho_em_minusculo_tambem_e_reconhecido_e_volta_com_o_nome_canonico():
    # Cloudflare e HTTP/2 baixam a caixa dos nomes; antes, o HTML passava SEM o guarda de leitura (falhava aberto)
    st, cab, corpo = pt.ajustar_resposta(200, {"content-type": "text/html; charset=utf-8",
                                               "content-disposition": "inline", "cache-control": "no-store",
                                               "etag": "x", "last-modified": "hoje"}, b"<head></head>")
    assert set(cab) == {"Content-Type", "Content-Disposition", "Cache-Control", "ETag", "Last-Modified"}
    assert cab["Content-Type"] == "text/html; charset=utf-8"
    assert b'id="nexus-leitura"' in corpo and b'id="nexus-visual"' in corpo


def test_tipo_html_em_maiuscula_tambem_recebe_o_guarda():
    _, cab, corpo = pt.ajustar_resposta(200, {"Content-Type": "TEXT/HTML"}, b"<head></head>")
    assert cab["Content-Type"] == "TEXT/HTML" and b'id="nexus-leitura"' in corpo


def test_cookie_e_tamanho_em_minusculo_continuam_barrados():
    _, cab, _ = pt.ajustar_resposta(200, {"content-type": "application/json", "set-cookie": "s=1",
                                          "content-length": "9", "content-encoding": "gzip",
                                          "transfer-encoding": "chunked", "connection": "keep-alive"}, b"{}")
    assert cab == {"Content-Type": "application/json"}


# Controles de gravação das páginas (Monitoramento): o atributo é o REAL de cada um, conferido em
# docs/redesign/"Monitoramento (novo design).html" da plataforma. `tkStrQtdSai` e `tkStrQuem` são `onchange` (não
# `onblur`/`oninput`); a quantidade digitada é `oninput="tkStrQtdDig"`.
CONTROLES_DE_GRAVACAO = [
    '[onclick*="trancarString"]', '[onclick*="excluirComent"]', '[onclick*="gcDesatribuirOS"]',
    '[onclick*="gcUsinaReligada"]', '[onchange*="setTracking"]', '[oninput*="setTracking"]',
    '[onclick*="toggleOsMode"]', '[onclick*="osGerar"]', '[onclick*="gcUsinaDesligada"]',
    '[onclick*="gcDeslConfirmar"]', '[onclick*="tkStrSalvar"]', '[onclick*="tkStrFinalizar"]',
    '[onclick*="tkStrConfirmar"]', '[onclick*="tkStrQtd"]', '[oninput*="tkStrQtdDig"]', '[onchange*="tkStrQtdSai"]',
    '[onclick*="tkStrCampo"]', '[onchange*="tkStrCampo"]', '[onchange*="tkStrFim"]', '[onchange*="tkStrQuem"]',
    '[onclick*="publicarComent"]', '[onclick*="gcAtribuirOS"]', '[onclick*="gcPickOS"]', '[onclick*="gcConfirmarOS"]',
]


@pytest.mark.parametrize("seletor", CONTROLES_DE_GRAVACAO)
def test_todo_controle_de_gravacao_da_pagina_some_no_nexus(seletor):
    # O guarda do navegador já barra o POST; isto tira o botão da frente (senão o analista clica e só vê o aviso).
    html = pt.injetar("<html><head></head><body></body></html>")
    estilo = html[html.index('id="nexus-visual"'):html.index("</style>")]
    assert seletor in estilo, seletor


def test_montar_pedido_recusa_caminho_sem_barra_inicial_ou_com_query():
    # "@evil.com/x" colado na base viraria usuário "plat" no servidor evil.com; "?" e "#" escondem query por fora do filtro
    for ruim in ("@evil.com/x", "api/x", "", "/api/x?force=1", "/api/x#y"):
        with pytest.raises(ValueError):
            pt.montar_pedido("https://plat", "k", "GET", ruim, [], None, None)


class _R:
    """Resposta falsa com a mesma interface mínima do `requests.Response`."""
    def __init__(self, status=200, location=None, corpo=b"{}"):
        self.status_code, self.content = status, corpo
        self.headers = {"Content-Type": "application/json", **({"Location": location} if location else {})}


def _destino_real(p):
    """(esquema, host, porta) a que o `requests`/urllib3 conectaria de verdade para este pedido.

    A sessão de verdade prepara a URL (`Request.prepare`) e é o host DELA que o urllib3 usa: a barra invertida termina o
    host, então "https://evil.com", barra invertida, "@plat:5050/x" conecta em evil.com, ainda que o `urlsplit` do
    Python leia o host como `plat`. A sessão falsa precisa registrar esse destino, e não a URL como texto, senão o teste
    não enxerga a fuga."""
    try:
        u = parse_url(requests.Request(p["method"], p["url"], params=p.get("params")).prepare().url)
    except Exception:
        return ("url inválida",)
    return u.scheme, u.host, u.port or {"http": 80, "https": 443}.get(u.scheme)


class _Sessao:
    """Sessão falsa: devolve as respostas em ordem (ou levanta, se for exceção) e guarda cada pedido recebido,
    com o destino real (`destinos`) a que a conexão iria."""
    def __init__(self, *respostas):
        self.respostas, self.pedidos, self.destinos = list(respostas), [], []

    def request(self, **p):
        self.pedidos.append(p)
        self.destinos.append(_destino_real(p))
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _pedido(base="https://plat:5050"):
    return pt.montar_pedido(base, "chave-k", "GET", "/api/x", [], None, None)


def test_salto_no_mesmo_servidor_e_seguido_com_a_chave(monkeypatch):
    s = _Sessao(_R(302, "/api/novo"), _R(200, corpo=b'{"ok":1}'))
    monkeypatch.setattr(pt, "_SESSAO", s)
    r = pt.enviar(**_pedido())
    assert r.status_code == 200 and r.content == b'{"ok":1}'
    assert [p["url"] for p in s.pedidos] == ["https://plat:5050/api/x", "https://plat:5050/api/novo"]
    # os cabeçalhos (a chave e o prefixo) vão de novo no salto, e quem salta é a ponte: o `requests` não segue sozinho
    assert all(p["headers"]["X-Nexus-Leitura"] == "chave-k" and p["allow_redirects"] is False for p in s.pedidos)


def test_salto_nao_repete_a_query_do_pedido_original(monkeypatch):
    s = _Sessao(_R(302, "/api/novo?x=1"), _R(200))
    monkeypatch.setattr(pt, "_SESSAO", s)
    pt.enviar(**pt.montar_pedido("https://plat:5050", "chave-k", "GET", "/api/x", [("data", "d")], None, None))
    assert s.pedidos[0]["params"] == [("data", "d")]
    assert s.pedidos[1]["url"] == "https://plat:5050/api/novo?x=1" and s.pedidos[1]["params"] == []


def test_salto_303_de_post_vira_get_sem_corpo(monkeypatch):
    s = _Sessao(_R(303, "/api/lista"), _R(200))
    monkeypatch.setattr(pt, "_SESSAO", s)
    pt.enviar(**pt.montar_pedido("https://plat:5050", "chave-k", "POST", "/api/etm/os", [], b"{}", "application/json"))
    assert s.pedidos[1]["method"] == "GET" and "data" not in s.pedidos[1]
    assert "Content-Type" not in s.pedidos[1]["headers"] and s.pedidos[1]["headers"]["X-Nexus-Leitura"] == "chave-k"


@pytest.mark.parametrize("destino", [
    "https://evil.com/x", "//evil.com/x", "https://plat:6060/x", "http://plat:5050/x", "https://plat.evil.com/x",
])
def test_salto_para_outro_servidor_nao_e_seguido_e_a_chave_nao_vai(monkeypatch, destino):
    s = _Sessao(_R(302, destino), _R(200))
    monkeypatch.setattr(pt, "_SESSAO", s)
    with pytest.raises(pt.ForaDoAr, match="redirecionamento para outro servidor"):
        pt.enviar(**_pedido())
    assert len(s.pedidos) == 1                           # o segundo pedido (com a chave) nunca saiu
    assert all(p["url"].startswith("https://plat:5050/") for p in s.pedidos)


# Location que o `urlsplit` do Python lê como o MESMO servidor e o `requests`/urllib3 lê como outro (04/10/2026, revisão
# final): a barra invertida termina o host para o urllib3, então `//evil.com\@plat:5050/x` conectava em evil.com levando
# a chave de leitura. Tudo aqui é Location que a ponte tem de recusar sem mandar pedido algum.
LOCATIONS_ENGANOSAS = [
    r"//evil.com\@plat:5050/x",              # barra invertida: host real = evil.com
    r"https://evil.com\@plat:5050/x",        # o mesmo, com esquema
    r"/x\y",                                 # barra invertida em qualquer lugar é recusada (política, não só o host)
    "https://plat:5050:/x",                  # porta malformada: o urlsplit levantava ValueError (virava 500)
    "https://plat:5050/x y",                 # espaço
    "/x\ty",                                 # tabulação (o urljoin a engole: tem de ser olhada na Location crua)
    "/x\r\nX-Evil: 1",                       # quebra de linha (injeção de cabeçalho)
    "/x\x00y", "/x\x7fy",                    # controles
    "/x\u00a0y", "/x\u2028y",                # espaços que não são o ASCII
    # ASCII puro que passa pela lista de caracteres, mas o `urljoin` do Python 3.14 recusa com ValueError (colchete solto,
    # IPv6 inválido): era 500 na rota, tem de ser a recusa de sempre
    "https://[x@plat:5050/x", "//]", "http://evil.com[/x",
]


@pytest.mark.parametrize("destino", LOCATIONS_ENGANOSAS)
def test_location_enganosa_nao_leva_a_chave_a_outro_servidor(monkeypatch, destino):
    s = _Sessao(_R(302, destino), _R(200))
    monkeypatch.setattr(pt, "_SESSAO", s)
    with pytest.raises(pt.RedirecionamentoRecusado) as e:
        pt.enviar(**_pedido())
    assert e.value.motivo == pt.MOTIVO_LOCATION_INVALIDO
    # nenhum pedido (com a chave) chegou a servidor algum além do original, e o original foi para a plataforma
    assert len(s.pedidos) == 1 and s.destinos == [("https", "plat", 5050)]


def test_origem_e_a_da_url_que_o_requests_vai_usar():
    # o urlsplit do Python diz "plat"; o requests/urllib3 conecta em evil.com. A comparação tem de usar o segundo.
    assert pt._origem(r"https://evil.com\@plat:5050/x") == ("https", "evil.com", 443)
    assert pt._origem("https://PLAT:5050/x") == ("https", "plat", 5050)          # host sem caixa
    assert pt._origem("https://plat/x") == ("https", "plat", 443)                # porta padrão omitida
    assert pt._origem("http://plat/x") == ("http", "plat", 80)
    for malformada in ("https://plat:5050:/x", "https://plat:abc/x", "https:///x", "ftp://plat/x", "/so/caminho"):
        with pytest.raises(ValueError):
            pt._origem(malformada)


def test_origem_de_ipv6_vem_sem_colchetes_e_os_dois_leitores_do_requests_tem_de_concordar(monkeypatch):
    assert pt._origem("http://[::1]:5050/x") == ("http", "::1", 5050)
    # endurecimento: o requests 2.34 escolhe o host do pool pelo `urlparse` e o urllib3 pelo `parse_url`; se um dia
    # discordarem sobre a mesma URL já preparada, não se sabe para onde a conexão iria, e a ponte não vai
    real = pt.parse_url

    def outro_host(u):
        return real(u)._replace(host="evil.com")
    monkeypatch.setattr(pt, "parse_url", outro_host)
    with pytest.raises(ValueError, match="discordam"):
        pt._origem("https://plat:5050/x")


def test_url_limpa_recusa_barra_invertida_espaco_e_controle():
    assert pt.url_limpa("https://plat:5050") and pt.url_limpa("/api/novo?x=1&y=%C3%A1")
    for ruim in ("a\\b", "a b", "a\tb", "a\nb", "a\x00b", "a\x7fb", "a\x85b", "a\u00a0b"):
        assert not pt.url_limpa(ruim), repr(ruim)


def test_origem_configurada_le_a_url_como_o_requests_e_recusa_a_enganosa():
    assert pt.origem_configurada("http://localhost:5050") == ("http", "localhost", 5050)
    assert pt.origem_configurada("http://[::1]:5050") == ("http", "::1", 5050)
    assert pt.origem_configurada("https://plat") == ("https", "plat", 443)
    for ruim in ("http://evil.com\\@localhost:5050", "https://plat:5050 ", " https://plat", "http://plat:5050:",
                 "ftp://plat", "plat:5050", ""):
        with pytest.raises(ValueError):
            pt.origem_configurada(ruim)


@pytest.mark.parametrize("local", ["http://evil.com[/x", "https://[x@plat:5050/x", "//]"])
def test_vai_para_login_nao_estoura_com_location_malformada(local):
    # a rota chama isto na Location crua de respostas 3xx que a ponte não seguiu (300, 305...): colchete solto fazia o
    # `urlsplit` levantar ValueError (500). Não é o login.
    assert pt.vai_para_login(local) is False
    assert pt.vai_para_login("/login?next=%2F") is True


@pytest.mark.parametrize("destino", [r"//evil.com\@plat:5050/x", r"https://evil.com\@plat:5050/x", "https://plat:5050:/x"])
def test_origem_sozinha_ja_barra_mesmo_sem_a_checagem_de_caracteres(monkeypatch, destino):
    # defesa em profundidade: se a lista de caracteres proibidos falhasse (ou fosse afrouxada), a comparação de origem
    # pela URL real do requests ainda barra
    monkeypatch.setattr(pt, "url_limpa", lambda local: True)
    s = _Sessao(_R(302, destino), _R(200))
    monkeypatch.setattr(pt, "_SESSAO", s)
    with pytest.raises(pt.RedirecionamentoRecusado):
        pt.enviar(**_pedido())
    assert len(s.pedidos) == 1 and s.destinos == [("https", "plat", 5050)]


def test_motivo_de_cada_recusa(monkeypatch):
    s = _Sessao(_R(302, "https://evil.com/x"))
    monkeypatch.setattr(pt, "_SESSAO", s)
    with pytest.raises(pt.RedirecionamentoRecusado) as e:
        pt.enviar(**_pedido())
    assert e.value.motivo == pt.MOTIVO_OUTRO_SERVIDOR
    s = _Sessao(*[_R(302, "/a")] * 5)
    monkeypatch.setattr(pt, "_SESSAO", s)
    with pytest.raises(pt.RedirecionamentoRecusado) as e:
        pt.enviar(**_pedido())
    assert e.value.motivo == pt.MOTIVO_DEMAIS


def test_salto_no_mesmo_servidor_com_caminho_e_query_normais_continua_seguido(monkeypatch):
    # a recusa de caracteres não pode pegar Location legítima: acento já vem percent-encoded, e `%5C` (barra invertida
    # codificada) não é a barra invertida crua
    s = _Sessao(_R(302, "/api/novo?x=1&y=%C3%A1"), _R(301, "https://plat:5050/api/b%5Cc"), _R(200))
    monkeypatch.setattr(pt, "_SESSAO", s)
    assert pt.enviar(**_pedido()).status_code == 200
    assert s.destinos == [("https", "plat", 5050)] * 3


def test_no_maximo_tres_saltos(monkeypatch):
    s = _Sessao(_R(302, "/a"), _R(302, "/b"), _R(302, "/c"), _R(302, "/d"), _R(200))
    monkeypatch.setattr(pt, "_SESSAO", s)
    with pytest.raises(pt.ForaDoAr, match="redirecionamentos demais"):
        pt.enviar(**_pedido())
    assert len(s.pedidos) == 4                           # o original + 3 saltos seguidos


def test_porta_padrao_escrita_ou_omitida_e_o_mesmo_servidor(monkeypatch):
    s = _Sessao(_R(301, "https://plat:443/y"), _R(200))
    monkeypatch.setattr(pt, "_SESSAO", s)
    assert pt.enviar(**_pedido("https://plat")).status_code == 200


@pytest.mark.parametrize("login", ["/login?next=%2Ftempo-real", "/t/performance/plataforma/login", "/auth/login"])
def test_salto_para_o_login_volta_como_esta(monkeypatch, login):
    # a plataforma manda a chave sem sessão para o /login: seguir mostraria a tela de login dela dentro do Nexus
    s = _Sessao(_R(302, login), _R(200))
    monkeypatch.setattr(pt, "_SESSAO", s)
    r = pt.enviar(**_pedido())
    assert r.status_code == 302 and len(s.pedidos) == 1


def test_erro_de_rede_vira_fora_do_ar(monkeypatch):
    monkeypatch.setattr(pt, "_SESSAO", _Sessao(requests.ConnectionError("x")))
    with pytest.raises(pt.ForaDoAr, match="ConnectionError"):
        pt.enviar(**_pedido())


def _esgotar_vagas():
    n = 0
    while pt._VAGAS.acquire(blocking=False):
        n += 1
    return n


def test_enviar_devolve_a_vaga_depois_de_erro_de_rede_ou_de_codigo(monkeypatch):
    # sem o `finally`, 4 pedidos que falham deixariam o Nexus sem vaga para sempre
    for erro in (requests.ReadTimeout("x"), RuntimeError("bug")):
        monkeypatch.setattr(pt, "_SESSAO", _Sessao(erro))
        with pytest.raises((pt.ForaDoAr, RuntimeError)):
            pt.enviar(**_pedido())
    n = _esgotar_vagas()
    for _ in range(n):
        pt._VAGAS.release()
    assert n == 4


def test_sem_vaga_levanta_ocupada_depois_de_esperar(monkeypatch):
    monkeypatch.setattr(pt, "ESPERA_VAGA_S", 0.05)
    monkeypatch.setattr(pt, "_SESSAO", _Sessao())        # se chegasse à rede, esvaziaria a lista e quebraria
    n = _esgotar_vagas()
    try:
        with pytest.raises(pt.Ocupada):
            pt.enviar(**_pedido())
    finally:
        for _ in range(n):
            pt._VAGAS.release()
    assert n == 4

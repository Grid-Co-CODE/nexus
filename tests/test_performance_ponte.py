# tests/test_performance_ponte.py
"""Ponte do Nexus para a plataforma de Performance (04/10/2026): só leitura, com o visual do Nexus."""
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
    assert p["timeout"] == pt.TEMPO_LIMITE_S and p["allow_redirects"] is True


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

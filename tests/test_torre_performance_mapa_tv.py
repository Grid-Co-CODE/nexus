"""Torre Performance -> Mapa de risco, o que 09/10/2026 trouxe para a tela: os controles (camada de fundo, as de cima, os filtros)
que funcionam sem JavaScript, o JSON da página, a releitura sem recarregar (as partes marcadas e a próxima leitura), o arquivo de
JavaScript e o modo TV (?tv=1: sem a casca, com login, relógio, as fontes com a hora e o giro das camadas). Sem rede: leituras
prontas no lugar das fontes, e um grupo anda a cadeia de verdade (o COG do risco lido na área, por sessão falsa)."""
import json
import re

import pytest

from nexus.performance.clima import fontes as F
from nexus.performance.clima import leitura as L
from nexus.performance.clima import visao as V
from nexus.performance.clima.usinas import Usina

from clima_mapa_mundo import (ALFA, DELTA, REF, aviso, foco_a, instalar_leituras, lei_avisos, lei_focos, lei_grade, lei_risco,
                              mundo_completo, risco_baixo, tudo_instalado)
from test_torre_performance_mapa import cadeia, nova_app, pagina, svg, texto  # noqa: F401 (a fixture da cadeia de verdade)

URL = "/t/performance/clima/mapa"
INMET, INPE = F.extenso("inmet"), F.extenso("inpe")
PARTES = {"svg", "legenda", "tabela", "fontes", "dados", "hora", "notas"}


@pytest.fixture
def leituras(monkeypatch):
    return instalar_leituras(monkeypatch)


@pytest.fixture
def mundo(tmp_path, monkeypatch, leituras):
    app, cliente = nova_app(tmp_path, extra=[Usina("7", "Usina Sem Posicao", "Cliente X")])
    monkeypatch.setattr(V, "agora", lambda: REF)
    mundo_completo(leituras)
    return cliente


def partes(html):
    return set(re.findall(r'data-parte="([\w-]+)"', html))


# ── os controles, sem JavaScript ─────────────────────────────────────────────────────────────────────────────────────

def test_os_controles_sao_links_que_levam_o_estado_no_endereco(mundo):
    html = pagina(mundo)
    barra = re.search(r'<div class="mp-barra" data-parte="barra">(.*?)</div>\s*<div class="mp-busca"', html, flags=re.S).group(1)
    fundos = re.findall(r'data-fundo="(\w+)" href="([^"]*)" aria-pressed="(\w+)"', barra)
    assert fundos == [("avisos", URL, "true"), ("risco", f"{URL}?fundo=risco", "false"),
                      ("densidade", f"{URL}?fundo=densidade", "false"), ("nenhum", f"{URL}?fundo=nenhum", "false")]
    sobre = re.findall(r'data-sobre="(\w+)" href="([^"]*)" aria-pressed="(\w+)"', barra)
    assert sobre == [("usinas", f"{URL}?ver=focos,siglas", "true"), ("focos", f"{URL}?ver=usinas,siglas", "true"),
                     ("siglas", f"{URL}?ver=usinas,focos", "true")]
    assert "onchange" not in barra and "<script" not in barra


def test_a_camada_de_fundo_escolhida_pelo_endereco_e_o_que_o_svg_desenha(mundo, leituras):
    leituras(avisos=lei_avisos(aviso(3, "Vendaval", ALFA)), focos=lei_focos(foco_a(1.0, DELTA)), risco=lei_risco(risco_baixo()),
             grade=lei_grade(lambda lat, lon: 0.97 if lon > -41.2 else 0.1))
    s = svg(pagina(mundo, fundo="risco"))
    assert 'class="mp-calor mp-calor--risco"' in s and 'clip-path="url(#mp-recorte)"' in s and 'class="mp-avisos"' not in s
    assert s.count("<use href=\"#mp-uf-") == 27 and 'class="mp-divisas"' in s
    assert re.search(r'<path class="mp-cr mp-cr-5" data-classe="5" stroke-width="[\d.]+" d="M', s)
    t = texto(pagina(mundo, fundo="risco"))
    assert f"Risco de fogo do {INPE}" in t and "Crítico acima de 0,95" in t and "Sem cor sem dado" in t
    d = svg(pagina(mundo, fundo="densidade"))
    assert 'class="mp-calor mp-calor--densidade"' in d and "focos por 1.000 km²" in texto(pagina(mundo, fundo="densidade"))
    n = svg(pagina(mundo, fundo="nenhum"))
    assert "mp-calor" not in n and 'class="mp-avisos"' not in n and len(re.findall(r'class="mp-ponto ', n)) == 6


def test_o_que_vai_por_cima_e_os_niveis_escondidos_vem_como_classe_da_tela(mundo):
    html = pagina(mundo, ver="usinas", ocultar="sem")
    raiz = re.search(r'<div class="(cl mp[^"]*)" data-mapa', html).group(1).split()
    assert {"mp-sem-focos", "mp-sem-siglas", "mp-oculta-sem"} <= set(raiz) and "mp-sem-usinas" not in raiz
    assert 'aria-pressed="false" data-acao="estado" data-nivel="sem"' in html                # o botão diz que está escondido


def test_o_evento_escondido_vem_marcado_no_desenho_e_na_legenda(mundo, leituras):
    tudo_instalado(leituras, avisos=lei_avisos(aviso(2, "Baixa Umidade", ALFA), aviso(2, "Tempestade", DELTA)))
    html = pagina(mundo, sem_eventos="baixa-umidade")
    assert re.search(r'data-ev="baixa-umidade" class="mp-av-oculto"', svg(html))
    assert re.search(r'aria-pressed="false" data-acao="estado" data-ev="baixa-umidade"', html)
    assert re.search(r'aria-pressed="true" data-acao="estado" data-ev="tempestade"', html)


def test_o_filtro_de_cliente_do_mapa_e_o_mesmo_da_lista_e_leva_o_resto_do_estado(mundo):
    html = pagina(mundo, fundo="risco")
    form = re.search(r'<form class="cl-filtro mp-cliente".*?</form>', html, flags=re.S).group(0)
    assert 'name="cliente"' in form and '<input type="hidden" name="fundo" value="risco">' in form
    assert 'data-acao="cliente"' in form and "<noscript>" in form


# ── a página que se relê sozinha ─────────────────────────────────────────────────────────────────────────────────────

def test_a_pagina_marca_as_partes_que_se_trocam_e_a_proxima_leitura(mundo):
    html = pagina(mundo)
    assert PARTES <= partes(html)
    assert re.search(r'data-mapa data-fundo="avisos" data-proxima-s="\d+"', html)
    assert '<noscript><meta http-equiv="refresh" content="60"></noscript>' in html          # sem JavaScript, a recarga de sempre
    assert '<script src="/static/clima-mapa.js" defer></script>' in html


def test_o_mapa_e_o_modo_tv_nunca_ficam_em_cache(mundo):
    for consulta in ({}, {"tv": "1"}):
        r = mundo.get(URL, query_string=consulta)
        assert r.headers["Cache-Control"] == "no-store"


def test_o_json_da_pagina_escapa_o_nome_da_usina(tmp_path, monkeypatch, leituras):
    app, c = nova_app(tmp_path, extra=[Usina("8", '</script><script>alert(1)</script> "Cia"', "Cliente X", "PI", "", -9.0, -45.0)])
    monkeypatch.setattr(V, "agora", lambda: REF)
    tudo_instalado(leituras)
    html = pagina(c)
    bloco = re.search(r'<script type="application/json" id="mp-dados" data-parte="dados">(.*?)</script>', html, flags=re.S).group(1)
    assert "</script" not in bloco and "<script" not in bloco
    dados = json.loads(bloco)
    assert dados["usinas"]["8"]["n"] == '</script><script>alert(1)</script> "Cia"'
    assert "<script>alert(1)" not in html


def test_o_javascript_e_servido_e_so_escreve_texto(mundo):
    js = mundo.get("/static/clima-mapa.js").get_data(as_text=True)
    assert "MapaRisco" in js and "textContent" in js
    assert "innerHTML" not in js and "insertAdjacentHTML" not in js and "eval(" not in js     # texto de fora nunca vira HTML
    assert 'redirect: "manual"' in js                                                      # a sessão que cai é percebida


# ── o modo TV ────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_o_modo_tv_nao_tem_a_casca_e_tem_relogio_camada_e_fontes(mundo):
    html = pagina(mundo, tv="1")
    assert '<header class="topo">' not in html and 'class="menu"' not in html and "Sair" not in html.split("mp-tv-controles")[0]
    assert re.search(r'<html lang="pt-BR" class="mp-tv-html" data-nexus data-tema="escuro">', html)
    assert "data-tv" in html and 'class="mp-tv-hora"' in html and "mp-tv-camada-nome" in html
    assert PARTES - {"busca"} <= partes(html)
    t = texto(html)
    assert f"Avisos meteorológicos do {INMET}" in t
    assert re.findall(r'<div class="cl-fonte cl-\w+"><span class="cl-fonte-texto">([^<]*)', html)[0].startswith(INMET)
    assert "window.top !== window.self" in html                                              # não fica dentro de moldura


def test_o_modo_tv_passa_pelo_login_e_volta_para_ele(tmp_path):
    app, _ = nova_app(tmp_path)
    r = app.test_client().get(URL + "?tv=1&girar=30")
    assert r.status_code == 302
    assert "/entrar?next=" in r.headers["Location"] and "tv%3D1" in r.headers["Location"]


def test_o_modo_tv_segue_o_tema(mundo):
    mundo.set_cookie("nexus_tema", "claro")
    assert 'class="mp-tv-html" data-nexus data-tema="claro"' in pagina(mundo, tv="1")


def test_o_giro_do_modo_tv_traz_as_tres_camadas_e_os_tres_titulos(mundo, leituras):
    leituras(avisos=lei_avisos(aviso(2, "Tempestade", ALFA)), focos=lei_focos(foco_a(1.0, DELTA)), risco=lei_risco(risco_baixo()),
             grade=lei_grade(lambda lat, lon: 0.8))
    html = pagina(mundo, tv="1", girar="30")
    assert 'data-girar="30"' in html
    assert [c for c in re.findall(r'class="mp-tv-camada-nome" data-camada="(\w+)"', html)] == ["avisos", "risco", "densidade"]
    s = svg(html)
    assert 'class="mp-avisos" data-camada="avisos"' in s and "mp-calor--risco" in s and "mp-calor--densidade" in s
    assert len(re.findall(r'<section class="mp-leg-camada" data-camada="(\w+)"', html)) == 3
    assert "a cada 30 s" in html and 'aria-pressed="true" role="button">a cada 30 s' in html


def test_o_modo_tv_sem_cadastro_diz_e_nao_quebra(app, logado):
    r = logado.get(URL + "?tv=1")
    assert r.status_code == 200 and "Cadastro indisponível" in r.get_data(as_text=True)


# ── a cadeia de verdade: o COG do risco lido na área, por sessão falsa ──────────────────────────────────────────────

def test_cadeia_real_o_risco_de_fogo_sai_do_cog_na_area_e_a_primeira_visita_ouve_lendo(cadeia):
    c, sessao = cadeia
    tarefas = []
    L.usar_executor(tarefas.append)
    try:
        primeira = pagina(c, URL, fundo="risco")
        assert "lendo a área do Brasil" in texto(primeira) and 'data-proxima-s="10"' in primeira
        assert len(tarefas) == 1
        tarefas.pop()()                                                          # a leitura ao fundo termina
        html = pagina(c, URL, fundo="risco")
        s = svg(html)
        assert re.search(r'class="mp-cr mp-cr-1"', s)                            # o 0,05 do COG de mentira é "Mínimo"
        assert f"{INPE} · risco de fogo: previsão para hoje, do arquivo de 07/10 às 06:32" in texto(html)
        pedidos = [u for u, _ in sessao.pedidos if "RF.PREV.T0" in u]
        assert pedidos                                                           # o T0, por Range, como o risco por usina
    finally:
        L.usar_executor(None)


def test_cada_camada_diz_na_legenda_de_quando_e_o_dado(mundo):
    t = texto(pagina(mundo))
    assert "2 em vigor e 1 a começar, lidos às 15:00." in t                                 # avisos
    assert "2 a até 5 km de uma usina; lidos às 15:00." in t                               # focos

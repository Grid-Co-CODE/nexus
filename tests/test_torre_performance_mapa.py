"""Torre Performance -> Mapa de risco: a tela /t/performance/clima/mapa (07/10/2026).

Mundo inventado (ver `clima_mapa_mundo.py`): seis usinas em pontos do Brasil que não são de usina nenhuma, uma sem coordenada,
avisos e focos postos em cima delas. A maior parte dos testes usa leituras prontas no lugar das fontes; um grupo anda a
cadeia de verdade (JSON do INMET, CSV de focos e COG do risco de fogo, por sessão falsa): nenhum teste vai à rede."""
import re

import pytest

from nexus import create_app
from nexus.cadastro.cifra import gerar_chave
from nexus.cadastro.servico import Carga
from nexus.performance.clima import alertas as A
from nexus.performance.clima import leitura as L
from nexus.performance.clima import mapa as M
from nexus.performance.clima import visao as V

from clima_cog import SessaoArquivos, montar_cog
from clima_mapa_mundo import (ALFA, BETA, DELTA, EPSILON, GAMA, REF, TETA, aviso, instalar_leituras, lei_avisos, lei_focos,
                              lei_risco, mundo_completo, mundo_de_usinas, quebrar_contorno, risco_baixo, tudo_instalado)
from conftest import SENHA_TESTE

URL = "/t/performance/clima/mapa"


def carga(extra=(), base=None):
    usinas = []
    for u in [*(mundo_de_usinas() if base is None else base), *extra]:
        v = {"nome": u.nome, "status": "OPERAÇÃO", "cliente": "1", "uf": u.uf, "cidade": "Cidade"}
        if u.lat is not None:
            v["latitude"], v["longitude"] = u.lat, u.lon
        usinas.append({"id": u.id, "ordem": len(usinas) + 1, "valores": v})
    return Carga(entidades={"clientes": [{"id": "1", "ordem": 1, "valores": {"nome": "Cliente X"}}], "usinas": usinas},
                 listas={"status_usina": ["OPERAÇÃO"], "uf": ["PI"]})


def nova_app(tmp_path, *, extra=(), base=None, config=None):
    app = create_app({"NEXUS_SECRET_KEY": "k", "NEXUS_SENHA_ADMIN": SENHA_TESTE, "NEXUS_CHAVE_CADASTRO": gerar_chave(),
                      "NEXUS_ARMAZEM_LOCAL": str(tmp_path / "cadastro.json"), **(config or {})})
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    with app.app_context():
        from nexus.cadastro.telas import servico
        servico().aplicar_carga(carga(extra, base))
    cliente = app.test_client()
    assert cliente.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    return app, cliente


@pytest.fixture
def leituras(monkeypatch):
    return instalar_leituras(monkeypatch)


@pytest.fixture
def mundo(tmp_path, monkeypatch, leituras):
    """O cliente logado, com o cadastro inventado (mais a Usina Sem Posicao, sem coordenada) e as três fontes lidas."""
    from nexus.performance.clima.usinas import Usina
    app, cliente = nova_app(tmp_path, extra=[Usina("7", "Usina Sem Posicao", "Cliente X")])
    monkeypatch.setattr(V, "agora", lambda: REF)
    mundo_completo(leituras)
    return cliente


def pagina(c, url=URL, **consulta):
    r = c.get(url, query_string=consulta or None)
    assert r.status_code == 200
    return r.get_data(as_text=True)


def texto(html):
    """O texto visível, sem marcação (e sem o que o navegador não mostra), para conferir frases."""
    sem_css = re.sub(r"<(style|script)\b.*?</\1>", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", sem_css))


def svg(html):
    return re.search(r"<svg\b.*?</svg>", html, flags=re.S).group(0)


def trecho(s, de, ate):
    """O pedaço de `s` entre o primeiro `de` e o primeiro `ate` depois dele (as camadas do SVG são irmãs, na ordem)."""
    i = s.index(de)
    return s[i:s.index(ate, i)]


def usinas_do_svg(html):
    """{nome: <a> da usina} lido do primeiro título de cada link."""
    achados = re.findall(r'<a href="/t/performance/clima/usina/[^"]*">.*?</a>', svg(html), flags=re.S)
    return {a.split("<title>")[1].split("\n")[0].strip(): a for a in achados}


# ── a tela ───────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_exige_login(tmp_path):
    app, _ = nova_app(tmp_path)
    assert app.test_client().get(URL).status_code == 302


def test_a_tela_responde_com_titulo_pergunta_e_o_link_para_a_lista(mundo):
    html = pagina(mundo)
    t = texto(html)
    assert "Mapa de risco" in t and "Em construção" not in t
    assert "Onde, no mapa do Brasil, estão as usinas" in t
    assert re.search(r'<a class="gc-btn[^"]*" href="/t/performance/clima">Ver a lista</a>', html)
    assert f'viewBox="{M.vista().viewbox}"' in svg(html)


def test_a_tela_atualiza_sozinha_a_cada_minuto(mundo):
    assert '<meta http-equiv="refresh" content="60">' in pagina(mundo)


def test_a_tela_aparece_como_pronta_no_menu_e_marca_a_atual(mundo):
    assert 'href="/t/performance/clima/mapa" class="com-conteudo"' in pagina(mundo, "/")
    assert 'href="/t/performance/clima/mapa" class="com-conteudo" aria-current="page"' in pagina(mundo)


def test_o_svg_nao_tem_largura_fixa_e_se_descreve_para_o_leitor_de_tela(mundo):
    cabeca = re.match(r"<svg\b[^>]*>", svg(pagina(mundo))).group(0)
    assert "viewBox=" in cabeca and 'role="group"' in cabeca and "aria-labelledby=" in cabeca
    assert not re.search(r'\s(width|height)="', cabeca)
    assert "<title id=" in svg(pagina(mundo))


def test_as_camadas_vao_de_tras_para_frente(mundo):
    s = svg(pagina(mundo))
    ordem = [s.index(f'class="{c}') for c in ("mp-ufs", "mp-avisos", "mp-siglas", "mp-focos", "mp-aneis", "mp-usinas")]
    assert ordem == sorted(ordem)


def test_cada_camada_aparece_com_a_contagem_do_modelo(mundo):
    s = svg(pagina(mundo))
    assert s.count('class="mp-uf"') == 27
    avisos = trecho(s, 'class="mp-avisos"', 'class="mp-siglas"')
    assert avisos.count("<path ") == 3 and avisos.count('<g class="mp-av ') == 3
    assert avisos.count('fill-rule="evenodd"') == 3                              # o buraco do polígono é buraco
    assert 'class="mp-av mp-av-3"' in avisos and 'class="mp-av mp-av-2"' in avisos and 'class="mp-av mp-av-1 mp-av--futuro"' in avisos
    focos = re.search(r'<path class="mp-focos" d="([^"]*)"', s).group(1)
    assert focos.count("M") == 4
    assert '<g class="mp-aneis">' in s and s.count("<circle class=\"mp-anel\"") == 2
    assert len(usinas_do_svg(pagina(mundo))) == 6 and s.count('class="mp-ponto ') == 6


def test_o_brasil_e_a_regiao_levam_classes_diferentes_para_o_css_decidir_o_tamanho_da_sigla(mundo):
    assert 'class="mp-svg mp-svg--brasil"' in svg(pagina(mundo))
    assert 'class="mp-svg mp-svg--regiao"' in svg(pagina(mundo, regiao="sul"))


def test_as_camadas_dos_estados_vem_com_a_sigla_de_quem_cabe_no_recorte(mundo):
    s = svg(pagina(mundo))
    siglas = re.findall(r"<text[^>]*>([A-Z]{2})</text>", s)
    assert len(siglas) == 27 and {"PI", "SP", "RS", "AM", "DF"} <= set(siglas)
    assert 'class="mp-siglas" aria-hidden="true"' in s
    # no recorte do Sul, Minas aparece só na beirada e o centro dela fica de fora: sem sigla, e sem `x="None"` no SVG
    sul = svg(pagina(mundo, regiao="sul"))
    assert "MG" not in re.findall(r"<text[^>]*>([A-Z]{2})</text>", sul) and {"RS", "SC", "PR"} <= set(re.findall(r"<text[^>]*>([A-Z]{2})</text>", sul))
    assert "None" not in sul


# ── a usina ──────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_cada_usina_e_um_link_para_a_pagina_dela_com_o_nivel_na_classe(mundo):
    usinas = usinas_do_svg(pagina(mundo))
    assert set(usinas) == {"Usina Alfa", "Usina Beta", "Usina Gama", "Usina Delta", "Usina Epsilon", "Usina Teta"}
    for nome, id_ in (("Usina Alfa", "1"), ("Usina Teta", "6")):
        assert usinas[nome].startswith(f'<a href="/t/performance/clima/usina/{id_}">')
    classe = {n: re.search(r'class="mp-ponto (mp-n-\w+)"', a).group(1) for n, a in usinas.items()}
    assert classe == {"Usina Alfa": "mp-n-agir", "Usina Delta": "mp-n-agir", "Usina Beta": "mp-n-atencao", "Usina Gama": "mp-n-atencao",
                      "Usina Epsilon": "mp-n-atencao", "Usina Teta": "mp-n-sem"}


def test_o_titulo_da_usina_diz_nome_cliente_nivel_e_motivo(mundo):
    titulo = re.search(r"<title>(.*?)</title>", usinas_do_svg(pagina(mundo))["Usina Delta"], flags=re.S).group(1)
    linhas = titulo.splitlines()
    assert linhas[:3] == ["Usina Delta", "Cliente: Cliente X", "Nível: Agir agora"]
    assert linhas[3].startswith("Motivo: foco de queimada a 1,0 km")


def test_a_ordem_do_svg_deixa_o_que_pede_acao_por_cima(mundo):
    html = pagina(mundo)
    nomes = list(usinas_do_svg(html))
    assert nomes[0] == "Usina Teta" and set(nomes[-2:]) == {"Usina Alfa", "Usina Delta"}


def test_cada_usina_tem_um_alvo_de_toque_maior_que_o_ponto(mundo):
    for a in usinas_do_svg(pagina(mundo)).values():
        alvo = float(re.search(r'class="mp-alvo"[^>]* r="([\d.]+)"', a).group(1))
        ponto = float(re.search(r'class="mp-ponto [^"]*"[^>]* r="([\d.]+)"', a).group(1))
        assert alvo > 2 * ponto


def test_o_texto_de_terceiros_e_o_nome_da_usina_saem_escapados(tmp_path, monkeypatch, leituras):
    from nexus.performance.clima.usinas import Usina
    app, c = nova_app(tmp_path, extra=[Usina("8", '<img src=x onerror=alert(1)> & "Cia"', "Cliente X", "PI", "", -9.0, -45.0)])
    monkeypatch.setattr(V, "agora", lambda: REF)
    veneno = aviso(3, '<script>alert("oi")</script>', (-9.0, -45.0), id_="v")
    tudo_instalado(leituras, avisos=lei_avisos(veneno))
    html = pagina(c)
    assert "<script>alert" not in html and "<img src=x" not in html
    assert "&lt;script&gt;alert(&#34;oi&#34;)&lt;/script&gt;" in html                         # o título do polígono e o da usina
    assert "&lt;img src=x onerror=alert(1)&gt; &amp; &#34;Cia&#34;" in html
    assert html.count("&lt;script&gt;alert(&#34;oi&#34;)&lt;/script&gt;") >= 2                 # o título do polígono e o motivo da usina
    assert not re.search(r"<(script|img)\b[^>]*(alert|onerror)", html)


def test_o_id_estranho_da_usina_nao_quebra_o_link(tmp_path, monkeypatch, leituras):
    from nexus.performance.clima.usinas import Usina
    app, c = nova_app(tmp_path, extra=[Usina('a/b "c"?', "Usina Estranha", "Cliente X", "PI", "", -9.0, -45.0)])
    monkeypatch.setattr(V, "agora", lambda: REF)
    tudo_instalado(leituras)
    assert '<a href="/t/performance/clima/usina/a%2Fb%20%22c%22%3F">' in pagina(c)


# ── a região ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_o_seletor_de_regiao_e_um_link_para_cada_recorte_e_funciona_sem_javascript(mundo):
    html = pagina(mundo)
    nav = re.search(r'<nav class="mp-regioes"[^>]*>(.*?)</nav>', html, flags=re.S).group(1)
    links = re.findall(r'<a class="mp-regiao"[^>]*href="([^"]*)"[^>]*>([^<]*)</a>', nav)
    assert [n for _, n in links] == ["Brasil", "Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul"]
    assert [h for h, _ in links] == [URL] + [f"{URL}?regiao={r}" for r in M.REGIOES]
    assert "<script" not in nav and "onchange" not in nav and "<select" not in nav
    assert nav.count('aria-current="page"') == 1 and re.search(r'aria-current="page"[^>]*>Brasil<', nav)


def test_a_regiao_pedida_refaz_o_viewbox_e_so_desenha_o_que_cai_nela(mundo):
    html = pagina(mundo, regiao="sul")
    assert f'viewBox="{M.vista("sul").viewbox}"' in svg(html)
    assert set(usinas_do_svg(html)) == {"Usina Gama"}
    assert re.search(r'aria-current="page"[^>]*>Sul<', html)
    s = svg(html)
    assert 'class="mp-uf"' in s and s.count('class="mp-uf"') < 27 and 'class="mp-avisos"' in s
    assert "5 usinas em operação estão fora deste recorte" in texto(html)
    assert M.vista("sul").viewbox != M.vista().viewbox


@pytest.mark.parametrize("regiao", ["norte", "nordeste", "centro-oeste", "sudeste", "sul"])
def test_toda_regiao_abre_com_o_viewbox_dela_e_a_usina_que_e_dela(mundo, regiao):
    html = pagina(mundo, regiao=regiao)
    assert f'viewBox="{M.vista(regiao).viewbox}"' in svg(html)
    esperado = {"norte": {"Usina Epsilon"}, "nordeste": {"Usina Alfa", "Usina Beta"}, "centro-oeste": {"Usina Teta"},
                "sudeste": {"Usina Delta", "Usina Teta"}, "sul": {"Usina Gama"}}[regiao]
    assert set(usinas_do_svg(html)) == esperado


def test_regiao_inventada_abre_o_brasil(mundo):
    html = pagina(mundo, regiao="marte")
    assert f'viewBox="{M.vista().viewbox}"' in svg(html) and len(usinas_do_svg(html)) == 6


def test_o_brasil_inteiro_nao_diz_que_ha_usina_fora_do_recorte(mundo):
    assert "fora deste recorte" not in texto(pagina(mundo))


def test_uma_usina_so_fora_do_recorte_diz_no_singular(tmp_path, monkeypatch, leituras):
    from nexus.performance.clima.usinas import Usina
    base = [Usina("1", "Usina Alfa", "Cliente X", "PI", "", *ALFA), Usina("3", "Usina Gama", "Cliente X", "RS", "", *GAMA)]
    app, c = nova_app(tmp_path, base=base)
    monkeypatch.setattr(V, "agora", lambda: REF)
    tudo_instalado(leituras)
    t = texto(pagina(c, regiao="sul"))
    assert "1 usina em operação está fora deste recorte" in t and "usinas em operação estão fora" not in t


# ── a legenda ────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_legenda_conta_os_tres_niveis_e_diz_o_que_cada_um_quer_dizer(mundo):
    t = texto(pagina(mundo))
    assert re.search(r"Agir agora 2\b", t) and re.search(r"Atenção 3\b", t) and re.search(r"Sem alerta 1\b", t)
    assert "foco a até 5 km" in t and "Grande Perigo" in t
    for evento in A.EVENTOS_QUE_ESTRAGAM_USINA:                                             # a lista é a da regra, não uma cópia
        assert evento in t
    assert "risco de fogo alto ou crítico" in t


def test_a_legenda_explica_as_camadas_com_o_que_ha_no_recorte(mundo):
    t = texto(pagina(mundo))
    assert "Perigo Potencial" in t and "Grande Perigo" in t and "tracejado" in t.lower()
    assert "2 em vigor e 1 a começar" in t                                                  # avisos
    assert "4 focos na última hora" in t and "2 a até 5 km de uma usina" in t              # focos
    assert "O risco de fogo do INPE não é desenhado" in t


def test_a_legenda_do_recorte_conta_so_o_que_esta_nele(mundo):
    t = texto(pagina(mundo, regiao="nordeste"))
    assert re.search(r"Agir agora 1\b", t) and re.search(r"Atenção 1\b", t) and re.search(r"Sem alerta 0\b", t)
    assert "2 em vigor e 0 a começar neste recorte" in t and "1 foco na última hora neste recorte, 0 a até 5 km de uma usina" in t


def test_o_rodape_cita_as_tres_fontes_do_mapa(mundo):
    t = texto(pagina(mundo))
    assert "Dados: IBGE, INMET, INPE" in t and "somente leitura" in t.lower()
    assert "Malhas territoriais" in t


def test_o_painel_de_frescor_e_o_mesmo_da_tela_principal(mundo):
    def fontes(html):
        return re.findall(r'<div class="cl-fonte cl-\w+">.*?</div>', html, flags=re.S)
    mapa, lista = fontes(pagina(mundo)), fontes(pagina(mundo, "/t/performance/clima"))
    assert len(mapa) == 3 and mapa == lista
    assert "lido às 15:00" in texto(pagina(mundo))


# ── a honestidade com a fonte que não foi lida inteira ───────────────────────────────────────────────────────────────

def test_fonte_fora_a_camada_some_e_a_legenda_diz_por_que(mundo, leituras):
    leituras(avisos=L.Leitura(None, None, erro="HTTP 500"), focos=lei_focos(), risco=lei_risco(risco_baixo()))
    html = pagina(mundo)
    t = texto(html)
    assert 'class="mp-avisos"' not in svg(html)
    assert "Avisos do INMET: sem leitura boa, a camada não aparece no mapa" in t
    assert "INMET fora agora; ainda sem leitura boa" in t and 'class="cl-fonte cl-fora"' in html
    assert "O mapa não inclui: avisos do INMET." in t and "Lendo agora" not in t


def test_sem_ler_os_avisos_nenhuma_usina_aparece_em_verde(mundo, leituras):
    leituras(avisos=L.Leitura(None, None, erro="HTTP 500"), focos=lei_focos(), risco=lei_risco(risco_baixo()))
    html = pagina(mundo)
    t = texto(html)
    assert "mp-n-sem" not in svg(html) and "mp-n-nx" in svg(html)
    assert re.search(r"Sem leitura completa 6\b", t)                                         # as 6 estariam "sem alerta"
    assert "mp-chave mp-n-sem" not in html                                                   # e a linha "Sem alerta" nem aparece
    assert "sem leitura de avisos do INMET, não dá para dizer que não há alerta" in t
    assert "Usina Teta" in usinas_do_svg(html)


def test_fonte_lendo_a_tela_volta_em_10_s_e_diz_lendo_e_nao_fora(mundo, leituras):
    leituras(avisos=L.Leitura(None, None, erro=L.LENDO), focos=lei_focos(), risco=lei_risco(risco_baixo()))
    html = pagina(mundo)
    t = texto(html)
    assert '<meta http-equiv="refresh" content="10">' in html
    assert "Lendo agora: avisos do INMET." in t and "O mapa não inclui" not in t
    assert "Avisos do INMET: lendo agora, a camada aparece quando a leitura terminar" in t


def test_sem_leitura_dos_focos_somem_os_pontos_e_os_aneis_e_a_legenda_diz(mundo, leituras):
    leituras(avisos=lei_avisos(), focos=L.Leitura(None, None, erro="tempo esgotado"), risco=lei_risco(risco_baixo()))
    html = pagina(mundo)
    s = svg(html)
    assert "mp-focos" not in s and "mp-anel" not in s and "mp-aneis" not in s and 'class="mp-avisos"' in s
    assert "Focos do INPE: sem leitura boa, a camada não aparece no mapa" in texto(html)


def test_sem_ler_o_risco_de_fogo_a_legenda_diz_e_o_verde_some(mundo, leituras):
    leituras(avisos=lei_avisos(), focos=lei_focos(), risco=L.Leitura(None, None, erro="HTTP 503"))
    html = pagina(mundo)
    assert "mp-n-sem" not in svg(html) and "sem leitura de risco de fogo do INPE" in texto(html)


def test_fonte_pela_metade_mantem_o_verde_mas_a_legenda_diz_nas_fontes_lidas(mundo, leituras):
    leituras(avisos=lei_avisos(ignorados=["aviso 7: sem polígono"]), focos=lei_focos(), risco=lei_risco(risco_baixo()))
    html = pagina(mundo)
    t = texto(html)
    assert "mp-n-sem" in svg(html) and re.search(r"Sem alerta nas fontes lidas 6\b", t)
    assert "1 aviso sem polígono utilizável não aparece no mapa" in t and "parcial" in t


def test_leitura_velha_continua_no_mapa_com_a_hora_dela_na_legenda(mundo, leituras):
    velha = L.Leitura({"avisos": [aviso(3, "Vendaval", ALFA)], "ignorados": [], "lidos": 1}, REF.timestamp() - 3600,
                      erro="HTTP 502", velha=True)
    leituras(avisos=velha, focos=lei_focos(), risco=lei_risco(risco_baixo()))
    html = pagina(mundo)
    t = texto(html)
    assert 'class="mp-avisos"' in svg(html) and "dado de 14:00" in t and "INMET fora agora; última leitura boa às 14:00" in t


# ── a coordenada ─────────────────────────────────────────────────────────────────────────────────────────────────────

def test_nenhum_numero_de_coordenada_aparece_como_texto(mundo):
    # A POSIÇÃO é permitida (o mapa a mostra, atrás do login, como o cadastro); o NÚMERO de latitude ou longitude, não. O teste
    # olha o texto que a pessoa lê (e o balão do título), não os atributos da geometria: número com 3 casas ou mais, não.
    for url in (URL, f"{URL}?regiao=nordeste", f"{URL}?regiao=sul"):
        html = pagina(mundo, url)
        t = texto(html)
        assert not re.search(r"\d+[.,]\d{3,}", t), re.search(r"\d+[.,]\d{3,}", t).group(0)
        for pos in (ALFA, BETA, GAMA, DELTA, EPSILON, TETA):
            for valor in (abs(pos[0]), abs(pos[1])):
                for casas in (3, 4, 5):
                    numero = f"{valor:.{casas}f}"
                    for forma in (numero, numero.replace(".", ",")):
                        assert forma not in html, forma                              # nem como texto, nem em atributo
        for titulo in re.findall(r"<title[^>]*>(.*?)</title>", html, flags=re.S):
            assert not re.search(r"\d+[.,]\d{3,}", titulo), titulo


def test_a_pagina_nao_poe_latitude_nem_longitude_em_atributo_nenhum(mundo):
    assert not re.search(r"\b(lat|lon|latitude|longitude)\s*=|data-(lat|lon)", pagina(mundo))


def test_usina_sem_coordenada_vai_para_a_lista_de_pendencias_e_nao_para_o_mapa(mundo):
    html = pagina(mundo)
    t = texto(html)
    assert "Sem coordenada no cadastro (1)" in t and "Usina Sem Posicao" in t
    assert "Usina Sem Posicao" not in usinas_do_svg(html)
    assert "Alertas para 6 usinas" not in t and "6 usinas em operação com coordenada" in t


def test_usina_com_coordenada_fora_do_brasil_tambem_fica_na_lista(tmp_path, monkeypatch, leituras):
    from nexus.performance.clima.usinas import Usina
    app, c = nova_app(tmp_path, extra=[Usina("8", "Usina Trocada", "Cliente X", "PI", "", 0.0, 0.0)])
    monkeypatch.setattr(V, "agora", lambda: REF)
    tudo_instalado(leituras)
    html = pagina(c)
    assert "Coordenada fora do Brasil no cadastro (1)" in texto(html) and "Usina Trocada" not in usinas_do_svg(html)


# ── o contorno que não abre ──────────────────────────────────────────────────────────────────────────────────────────

def test_contorno_que_nao_abre_a_tela_diz_e_mostra_o_resto_em_vez_de_500(mundo, monkeypatch):
    quebrar_contorno(monkeypatch)
    try:
        html = pagina(mundo, regiao="sul")
        t = texto(html)
        s = svg(html)
        assert "O contorno dos estados não abriu" in t and "sem as divisas" in t
        assert 'class="mp-uf"' not in s and len(usinas_do_svg(html)) == 6 and 'class="mp-avisos"' in s       # o resto continua
        assert f'viewBox="{M.vista_de_caixa(M.BRASIL, "Brasil", *M.LIMITES_BRASIL).viewbox}"' in s
        assert 'class="cl-fonte cl-ok"' in html                                                              # o painel das fontes também
    finally:
        M._vista.cache_clear()
        M.ufs_da_vista.cache_clear()


# ── sem cadastro ─────────────────────────────────────────────────────────────────────────────────────────────────────

def test_sem_cadastro_a_tela_responde_e_diz_o_que_falta(app, logado):
    r = logado.get(URL)
    assert r.status_code == 200
    t = texto(r.get_data(as_text=True))
    assert "Mapa de risco" in t and "Cadastro indisponível" in t and "NEXUS_CHAVE_CADASTRO" in t
    assert "<svg" not in r.get_data(as_text=True).split("<main", 1)[1]


def test_cadastro_sem_usina_com_coordenada_diz_isso_e_nao_desenha(tmp_path, monkeypatch, leituras):
    app = create_app({"NEXUS_SECRET_KEY": "k", "NEXUS_SENHA_ADMIN": SENHA_TESTE, "NEXUS_CHAVE_CADASTRO": gerar_chave(),
                      "NEXUS_ARMAZEM_LOCAL": str(tmp_path / "c.json")})
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    with app.app_context():
        from nexus.cadastro.telas import servico
        servico().aplicar_carga(Carga(entidades={"usinas": [{"id": "1", "ordem": 1, "valores": {"nome": "Usina Sozinha", "status": "OPERAÇÃO"}}]},
                                      listas={"status_usina": ["OPERAÇÃO"]}))
    cl = app.test_client()
    cl.post("/entrar", data={"senha": SENHA_TESTE})
    chamadas = tudo_instalado(leituras)
    html = cl.get(URL).get_data(as_text=True)
    t = texto(html)
    assert "Nenhuma usina em operação com coordenada" in t and "Usina Sozinha" in t and "<svg" not in html.split("<main", 1)[1]
    assert chamadas == []


def test_o_mapa_abre_sem_fonte_injetada_nos_testes_e_diz_que_nao_ha_fonte(tmp_path, monkeypatch):
    # Sem a sessão falsa, a fonte responde "sem fonte nos testes" (nunca vai à rede): o mapa sai com tudo em "sem leitura".
    from nexus.performance.clima.usinas import Usina
    L.limpar_cache()
    app, c = nova_app(tmp_path, extra=[Usina("7", "Usina Sem Posicao", "Cliente X")])
    monkeypatch.setattr(V, "agora", lambda: REF)
    html = pagina(c)
    assert "sem fonte nos testes" in html and "mp-n-sem" not in svg(html) and len(usinas_do_svg(html)) == 6


# ── 375 px ───────────────────────────────────────────────────────────────────────────────────────────────────────────

def _blocos_de_midia(css):
    """[(largura máxima, corpo)] de cada `@media (max-width:Npx){...}` do CSS, na ordem (conta as chaves aninhadas)."""
    achados = []
    for m in re.finditer(r"@media\s*\(max-width:\s*(\d+)px\)\s*\{", css):
        i, nivel = m.end(), 1
        while nivel:
            nivel += {"{": 1, "}": -1}.get(css[i], 0)
            i += 1
        achados.append((int(m.group(1)), css[m.end():i - 1]))
    return achados


def test_375_px_o_css_do_mapa_quebra_em_uma_coluna_e_o_svg_ocupa_a_largura(mundo):
    html = pagina(mundo)
    assert 'href="/static/clima.css"' in html and 'href="/static/clima-mapa.css"' in html
    css = mundo.get("/static/clima-mapa.css").get_data(as_text=True)
    assert re.search(r"\.mp-svg\{[^}]*width:100%", css) and re.search(r"\.mp-svg\{[^}]*height:auto", css)
    blocos = _blocos_de_midia(css)
    assert blocos and all(375 < largura <= 1200 for largura, _ in blocos)               # nenhuma regra só do desktop escondida
    assert any(largura >= 820 and "mp-corpo" in corpo and "grid-template-columns:minmax(0,1fr)" in corpo for largura, corpo in blocos)
    assert any(largura <= 820 and "mp-legenda" in corpo for largura, corpo in blocos)
    for classe in ("mp-corpo", "mp-legenda"):
        assert classe in html, classe
    assert "overflow-wrap:anywhere" in css and "min-width:0" in css


def test_375_px_nenhuma_largura_fixa_passa_da_tela_do_celular(mundo):
    css = mundo.get("/static/clima-mapa.css").get_data(as_text=True)
    fora_da_midia = css.split("@media")[0]
    for m in re.finditer(r"(?<![-\w])(?:min-)?width:\s*(\d+)px", fora_da_midia):
        assert int(m.group(1)) <= 340, m.group(0)
    assert not re.search(r"(?<![-\w])min-width:\s*\d{3,}px", css)


def test_375_px_os_pontos_crescem_no_celular_para_dar_para_tocar(mundo):
    css = mundo.get("/static/clima-mapa.css").get_data(as_text=True)
    celular = [corpo for largura, corpo in _blocos_de_midia(css) if largura <= 820]
    assert celular and re.search(r"--mp-k:\s*[1-9]\.\d", celular[0])                        # o fator de escala do ponto no celular
    assert "scale(var(--mp-k" in css


def test_o_css_do_mapa_so_usa_cores_que_o_clima_css_ou_o_nexus_css_definem(mundo):
    mapa = mundo.get("/static/clima-mapa.css").get_data(as_text=True)
    definidas = set(re.findall(r"(--[\w-]+)\s*:", mundo.get("/static/clima.css").get_data(as_text=True)
                               + mundo.get("/static/nexus.css").get_data(as_text=True) + mapa))
    usadas = set(re.findall(r"var\((--[\w-]+)", mapa))
    assert usadas and not (usadas - definidas), usadas - definidas


def _regra(css, seletor):
    """As declarações da regra que tem exatamente este seletor (a primeira)."""
    achou = re.search(r"(?:^|\}|\*/)\s*" + re.escape(seletor) + r"\s*\{([^}]*)\}", css)
    assert achou, seletor
    return achou.group(1)


def test_o_css_do_mapa_guarda_o_contrato_do_desenho(mundo):
    # As cores dizem o nível (o pedido: Agir agora = crítico, Atenção = alerta, Sem alerta = ok; avisos amarelo, laranja e
    # vermelho); a transparência do aviso é do grupo; o traço fica fino em qualquer largura; o foco é um ponto de ponta redonda.
    css = mundo.get("/static/clima-mapa.css").get_data(as_text=True)
    for nivel, cor in (("agir", "critico"), ("atencao", "atencao"), ("sem", "ok"), ("nx", "mudo")):
        assert f"fill:var(--cl-{cor})" in _regra(css, f".mp-ponto.mp-n-{nivel}")
        assert f"background:var(--cl-{cor})" in _regra(css, f".mp-chave.mp-n-{nivel}")
    for nivel, cor in ((1, "atencao"), (2, "alto"), (3, "critico")):
        assert f"color:var(--cl-{cor})" in _regra(css, f".mp-av-{nivel}")
    assert re.search(r"opacity:\s*0?\.\d+", _regra(css, ".mp-av")) and "fill:currentColor" in _regra(css, ".mp-av path")
    futuro = _regra(css, ".mp-av--futuro path")
    assert "fill:none" in futuro and "stroke-dasharray" in futuro and "non-scaling-stroke" in futuro      # só o contorno, tracejado
    assert "opacity:1" in _regra(css, ".mp-av--futuro")                                                  # o grupo do futuro não esmaece
    assert "non-scaling-stroke" in _regra(css, ".mp-uf") and "non-scaling-stroke" in _regra(css, ".mp-anel")
    assert "stroke-linecap:round" in _regra(css, ".mp-focos") and "fill:none" in _regra(css, ".mp-focos")
    assert "fill:transparent" in _regra(css, ".mp-alvo")                                                 # o alvo de toque recebe o toque
    assert "pointer-events:none" in _regra(css, ".mp-anel")                                              # o anel nunca tapa o link
    assert "display:none" in re.search(r"\.mp-svg--brasil \.mp-siglas\{([^}]*)\}", css).group(1)         # sigla some no celular, no Brasil


# ── a cadeia de verdade: JSON do INMET, CSV de focos e COG do risco, por sessão falsa ────────────────────────────────────

URL_INMET = "https://inmet.exemplo.test/ativos"
BASE_FOCOS = "https://inpe.exemplo.test/focos/"
RISCO = "https://inpe.exemplo.test/risco/RF.PREV.T{d}.tif"
X0, Y0, D = -50.0, -10.0, 0.01                           # a grade do INPE de mentira: 40 x 30 pixels de 0,01 grau


def centro(col, lin):
    return Y0 - (lin + 0.5) * D, X0 + (col + 0.5) * D


P_A, P_B, P_C = (5, 5), (10, 10), (15, 15)


def arquivos_da_cadeia():
    import json
    lat_a, lon_a = centro(*P_A)
    ring = [[lon_a - 0.03, lat_a - 0.03], [lon_a + 0.03, lat_a - 0.03], [lon_a + 0.03, lat_a + 0.03], [lon_a - 0.03, lat_a + 0.03],
            [lon_a - 0.03, lat_a - 0.03]]
    inmet = {"hoje": [{"id": 1, "descricao": "Vendaval", "severidade": "Grande Perigo", "inicio": "2026-10-07 09:10",
                       "fim": "2026-10-07 23:59", "poligono": json.dumps({"type": "Polygon", "coordinates": [ring]})}],
             "futuro": []}
    perto = f"{lat_a + 1.2 / 111.195:.6f}, {lon_a:.6f},GOES-19,2026-10-07 17:50:00"
    longe = "-3.000000, -60.000000,NOAA-21,2026-10-07 17:40:00"
    csv = ("lat,lon,satelite,data\n" + perto + "\n" + longe + "\n").encode()
    nome = "focos_10min_20261007_1750.csv"
    arquivos = {URL_INMET: json.dumps(inmet).encode(), BASE_FOCOS: f'<a href="{nome}">{nome}</a>'.encode(), BASE_FOCOS + nome: csv}
    for d in range(4):
        grade = [[0.05] * 40 for _ in range(30)]
        grade[P_C[1]][P_C[0]] = 0.75
        arquivos[RISCO.format(d=d)] = montar_cog(grade, origem=(X0, Y0), escala=D)
    return arquivos


@pytest.fixture
def cadeia(tmp_path, monkeypatch):
    from nexus.performance.clima.usinas import Usina
    usinas = [Usina("1", "Usina A", "Cliente X", "TO", "", *centro(*P_A)), Usina("2", "Usina B", "Cliente X", "TO", "", *centro(*P_B)),
              Usina("3", "Usina C", "Cliente X", "TO", "", *centro(*P_C))]
    chave = gerar_chave()
    app = create_app({"NEXUS_SECRET_KEY": "k", "NEXUS_SENHA_ADMIN": SENHA_TESTE, "NEXUS_CHAVE_CADASTRO": chave,
                      "NEXUS_ARMAZEM_LOCAL": str(tmp_path / "cadeia.json"), "NEXUS_CLIMA_INMET_URL": URL_INMET,
                      "NEXUS_CLIMA_FOCOS_URL": BASE_FOCOS, "NEXUS_CLIMA_RISCO_URL": RISCO})
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    with app.app_context():
        from nexus.cadastro.telas import servico
        servico().aplicar_carga(Carga(
            entidades={"clientes": [{"id": "1", "ordem": 1, "valores": {"nome": "Cliente X"}}],
                       "usinas": [{"id": u.id, "ordem": int(u.id), "valores": {
                           "nome": u.nome, "status": "OPERAÇÃO", "cliente": "1", "uf": "TO", "cidade": "Cidade",
                           "latitude": u.lat, "longitude": u.lon}} for u in usinas]},
            listas={"status_usina": ["OPERAÇÃO"], "uf": ["TO"]}))
    sessao = SessaoArquivos(arquivos_da_cadeia(), modificado="Wed, 07 Oct 2026 09:32:00 GMT")      # o arquivo do INPE é de hoje
    L.limpar_cache()
    L.usar_relogio(lambda: REF.timestamp())
    L.usar_sessao(sessao)
    monkeypatch.setattr(V, "agora", lambda: REF)
    cliente = app.test_client()
    assert cliente.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    yield cliente, sessao
    L.usar_sessao(None)
    L.usar_relogio(None)
    L.limpar_cache()


def test_cadeia_real_o_json_o_csv_e_o_cog_viram_camadas_e_niveis(cadeia):
    c, _ = cadeia
    html = pagina(c)
    s = svg(html)
    classe = {n: re.search(r'class="mp-ponto (mp-n-\w+)"', a).group(1) for n, a in usinas_do_svg(html).items()}
    # A: Grande Perigo de Vendaval em cima e foco a 1,2 km (agir); B: nada (sem alerta); C: risco de fogo alto hoje (atenção)
    assert classe == {"Usina A": "mp-n-agir", "Usina B": "mp-n-sem", "Usina C": "mp-n-atencao"}
    assert s.count('class="mp-av mp-av-3"') == 1 and s.count("<circle class=\"mp-anel\"") == 1
    assert re.search(r'class="mp-focos" d="([^"]*)"', s).group(1).count("M") == 2
    t = texto(html)
    assert "foco de queimada a 1,2 km" in t and "Vendaval (Grande Perigo" in t and "risco de fogo alto (Hoje, D+1, D+2, D+3)" in t
    assert 'class="cl-fonte cl-ok"' in html and html.count('class="cl-fonte cl-ok"') == 3


def test_a_lista_e_o_mapa_dividem_a_mesma_leitura_da_rede(cadeia):
    c, sessao = cadeia
    pagina(c, "/t/performance/clima")
    n = len(sessao.pedidos)
    assert n > 0
    pagina(c)
    pagina(c, URL, regiao="nordeste")
    assert len(sessao.pedidos) == n                                                          # o cache é o mesmo: nada de pedido a mais


def test_o_mapa_primeiro_e_a_lista_depois_tambem_dividem(cadeia):
    c, sessao = cadeia
    pagina(c)
    n = len(sessao.pedidos)
    pagina(c, "/t/performance/clima")
    assert len(sessao.pedidos) == n


def test_cadeia_real_fonte_que_cai_no_meio_vira_leitura_velha_no_mapa(cadeia):
    c, sessao = cadeia
    pagina(c)
    L.usar_relogio(lambda: REF.timestamp() + L.TTL_AVISOS_S + 60)
    del sessao.arquivos[URL_INMET]
    html = pagina(c)
    assert 'class="mp-avisos"' in svg(html) and "INMET fora agora; última leitura boa às 15:00" in texto(html)

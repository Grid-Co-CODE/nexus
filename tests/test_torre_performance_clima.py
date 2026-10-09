"""Torre Performance -> Clima e risco: a tela /t/performance/clima (06/10/2026; leitura rápida em 07/10/2026).

O mundo inventado (usinas, aviso, foco, risco, relógio e fixtures) mora em `clima_mundo.py`: é o mesmo da página da usina."""
import re
from datetime import datetime, timezone

import pytest

from nexus import create_app
from nexus.cadastro.cifra import gerar_chave
from nexus.cadastro.servico import Carga
from nexus.performance.clima import leitura as L
from nexus.performance.clima import visao as V
from nexus.performance.clima.geotiff import Amostra

from clima_mundo import (A, AGORA, B, BASE_FOCOS, C, DD, F, G, URL_INMET, Relogio, caixa_aviso, centro, inmet, mundo,  # noqa: F401
                         mundo25, mundo_usina, nome_foco, pagina, texto, u)
from conftest import SENHA_TESTE

def cartoes(html):
    """{nome da usina: trecho do cartão} dos cartões de "Agir agora", na ordem em que aparecem."""
    achados = re.findall(r'<article class="cl-usina[^"]*".*?</article>', html, flags=re.S)
    return {re.search(r'<h3 class="cl-nome"><a [^>]*>([^<]+)</a></h3>', a).group(1): a for a in achados}


def linhas(html):
    """{nome da usina: trecho da linha} da matriz de "Atenção", na ordem em que aparecem."""
    achados = re.findall(r'<tr class="cl-lin".*?</tr>', html, flags=re.S)
    return {re.search(r'<span class="cl-nome"><a [^>]*>([^<]+)</a></span>', a).group(1): a for a in achados}


def faixa(html):
    """{id: trecho} das quatro células da faixa do topo."""
    secao = re.search(r'<section class="cl-faixa".*?</section>', html, flags=re.S).group(0)
    return {m.group(1): m.group(0) for m in re.finditer(r'<div class="cl-cel[^"]*" data-id="(\w+)">.*?</div>', secao, flags=re.S)}


def valor(celula):
    return re.search(r'<span class="cl-valor">([^<]+)</span>', celula).group(1)


def quadrados(html):
    """{UF: trecho} dos 27 quadrados da grade por estado."""
    return {re.search(r'<span class="cl-uf-sigla">(\w+)</span>', q).group(1): q
            for q in re.findall(r'<div class="cl-uf[ "].*?</div>', html, flags=re.S)}


# ── a tela ───────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_exige_login(mundo):
    _, _, app = mundo
    assert app.test_client().get("/t/performance/clima").status_code == 302


def test_a_tela_responde_com_titulo_pergunta_e_atualiza_sozinha(mundo):
    c, _, _ = mundo
    html = pagina(c)
    assert "Clima e risco" in html and "Em construção" not in html
    assert '<meta http-equiv="refresh" content="60">' in html
    assert "atualizada às 15:00" in texto(html)


def test_a_lista_leva_ao_mapa_de_risco(mundo):
    """A lista e o mapa são duas visões do mesmo dado (Levi, 06/10/2026: "o mapa será complementar"): a lista leva
    ao mapa como o mapa já leva de volta à lista."""
    c, _, _ = mundo
    html = pagina(c)
    assert re.search(r'<a class="gc-btn[^"]*" href="/t/performance/clima/mapa">Ver no mapa</a>', html)


def test_a_tela_aparece_como_pronta_no_menu(mundo):
    c, _, _ = mundo
    assert 'href="/t/performance/clima" class="com-conteudo"' in pagina(c, "/")


def test_a_ordem_das_secoes_e_a_do_desenho_aprovado(mundo):
    c, _, _ = mundo
    html = pagina(c)
    ordem = ['class="cl-faixa"', 'id="cl-agir"', 'id="cl-ufs"', 'id="cl-fontes"', 'id="cl-atencao"']
    posicoes = [html.index(x) for x in ordem]
    assert posicoes == sorted(posicoes)


def test_faixa_do_topo_conta_agir_atencao_sem_alerta_e_cobertura(mundo):
    c, _, _ = mundo
    html = pagina(c)
    f = faixa(html)
    # agir: Alfa; atenção: Gama (risco alto), Zeta (alto pelo entorno) e Beta (aviso Perigo Potencial); sem alerta: Delta e Eta
    assert {i: valor(f[i]) for i in f} == {"agir": "1", "atencao": "3", "sem": "2", "cobertura": "6"}
    t = texto(f["cobertura"])
    assert "em operação com coordenada · 1 sem dado de risco · 1 sem coordenada" in t
    assert "Agir agora" in texto(f["agir"]) and "fogo a até 5 km ou aviso forte do INMET" in texto(f["agir"])
    assert "O que fazer: Avisar o supervisor da região" in texto(f["agir"]) and "O que fazer" not in texto(f["cobertura"])
    assert "nas três fontes lidas" in texto(f["sem"])


def test_agir_agora_so_tem_a_usina_do_foco_e_do_perigo_de_tempestade(mundo):
    c, _, _ = mundo
    html = pagina(c)
    assert list(cartoes(html)) == ["Usina Alfa"]
    assert list(linhas(html)) == ["Usina Gama", "Usina Zeta", "Usina Beta"]
    for fora in ("Usina Delta", "Usina Eta"):
        assert fora not in "".join(cartoes(html)) and fora not in "".join(linhas(html))


def test_cartao_do_foco_mostra_motivo_frase_principal_e_prova(mundo):
    c, _, _ = mundo
    alfa = texto(cartoes(pagina(c))["Usina Alfa"])
    assert "Fogo a 1,2 km da usina" in alfa and "1 foco de queimada a até 5 km na última hora" in alfa
    assert "visto pelo satélite GOES-19 às 14:50" in alfa
    assert "O que pode acontecer" in alfa and "O que conferir" in alfa                  # 09/10/2026: o cartão ensina
    assert "Cliente X · PI" in alfa


def test_cartao_do_aviso_que_manda_agir_mostra_o_evento_o_nivel_e_a_vigencia(mundo):
    c, _, _ = mundo
    alfa = texto(cartoes(pagina(c))["Usina Alfa"])
    # o foco abre o cartão (a pílula é dele); o aviso que manda agir vem logo abaixo, com a frase do nível e a vigência; o aviso
    # que não manda agir (Perigo Potencial) não vira motivo, só contexto
    assert "Fogo a 1,2 km" in alfa and "Tempestade: Perigo (é provável que cause estrago)" in alfa
    assert "Quando: agora, até 23:59" in alfa and "Baixa umidade:" not in alfa


def test_contexto_do_cartao_traz_o_outro_aviso_e_o_risco_de_fogo(mundo):
    c, _, _ = mundo
    alfa = texto(cartoes(pagina(c))["Usina Alfa"])
    assert "Também: Baixa umidade (Perigo Potencial), agora, até 23:59" in alfa
    assert "Risco de fogo crítico de hoje a sex 09/10 (0,97)" in alfa


def test_matriz_da_atencao_mostra_os_quatro_dias_do_risco_com_a_cor_de_cada_um(mundo):
    c, _, _ = mundo
    gama = linhas(pagina(c))["Usina Gama"]
    dias = re.findall(r'<span class="cl-c cl-c-(\w)"[^>]*>([^<]+)</span>', gama)
    assert dias == [("a", "Alto"), ("a", "Alto"), ("n", "Médio"), ("n", "Médio")]       # a palavra; o número vai no balão
    assert re.findall(r'title="([^"]*)"', gama)[-4:] == ["hoje: 0,75 (alto)", "amanhã: 0,80 (alto)", "qui 08/10: 0,60 (médio)",
                                                         "sex 09/10: 0,40 (médio)"]
    assert "Cliente Y · PI" in texto(gama)


def test_a_matriz_diz_o_que_e_cada_coluna_e_os_dias_pelo_calendario(mundo):
    c, sessao, _ = mundo
    html = pagina(c)
    assert "Risco de fogo · hoje · amanhã · qui 08/10 · sex 09/10" in texto(html) and "Por quê" in texto(html)
    sessao.modificado = "Mon, 05 Oct 2026 09:32:00 GMT"
    L.limpar_cache()
    html = pagina(c)
    assert "Risco de fogo · ontem · hoje · amanhã · qui 08/10" in texto(html)
    gama = linhas(html)["Usina Gama"]
    assert re.findall(r'title="([^"]*)"', gama)[-4:] == ["ontem: 0,75 (alto)", "hoje: 0,80 (alto)", "amanhã: 0,60 (médio)",
                                                         "qui 08/10: 0,40 (médio)"]


def test_a_linha_da_atencao_com_aviso_mostra_o_evento_e_a_coluna_do_foco_diz_que_nao_ha(mundo):
    c, _, _ = mundo
    beta = linhas(pagina(c))["Usina Beta"]
    assert "Baixa umidade" in texto(beta) and 'title="Perigo Potencial: agora, até 23:59"' in beta
    assert "Perigo Potencial · agora, até 23:59" in texto(beta)
    assert re.search(r'<td class="cl-col-foco">não</td>', beta) and re.search(r'<td class="cl-col-aviso">nenhum</td>', linhas(pagina(c))["Usina Gama"])
    assert re.search(r'<td class="cl-col-porque">Baixa umidade \(Perigo Potencial\)</td>', beta)          # o porquê em uma linha


def test_pixel_mascarado_usa_o_entorno_e_marca_o_valor(mundo):
    c, _, _ = mundo
    html = pagina(c)
    zeta, gama = linhas(html)["Usina Zeta"], linhas(html)["Usina Gama"]
    assert re.findall(r'<span class="cl-c cl-c-a"[^>]*>([^<]+)</span>', zeta) == ["Alto*"] * 4
    assert "*" not in "".join(re.findall(r'<span class="cl-c[^>]*>([^<]+)</span>', gama))
    assert "hoje: 0,85 (alto, entorno de 2 km)" in zeta
    assert "* maior valor do entorno de 2 km" in texto(html)


def test_sem_dado_nem_no_entorno_a_usina_fica_em_sem_alerta_e_a_cobertura_diz_por_que(mundo):
    c, _, _ = mundo
    html = pagina(c)
    assert "Usina Eta" not in "".join(cartoes(html)) and "Usina Eta" not in "".join(linhas(html))
    assert "Risco de fogo sem dado (sem vegetação no entorno): Usina Eta." in texto(html)


@pytest.mark.parametrize("origem,valor_,esperado", [
    ("ponto", 0.97, ("0,97", "crítico", "", 3)),
    ("ponto", 0.30, ("0,30", "baixo", "", 0)),
    ("entorno", 0.85, ("0,85", "alto", "entorno", 2)),
    ("sem_dado", None, ("sem dado (sem vegetação no entorno)", "", "", 0)),
    ("indisponivel", None, ("indisponível", "", "", 0)),
    ("fora_da_grade", None, ("fora da grade do INPE", "", "", 0)),
])
def test_cada_dia_de_risco_e_escrito_pela_origem_do_valor(origem, valor_, esperado):
    c = V.celula_de_risco(2, Amostra(valor_, origem))
    assert c["rotulo"] == "D+2"
    assert (c["valor"], c["classe"], c["nota"], c["nivel"]) == esperado


def test_usina_sem_coordenada_aparece_numa_linha_e_a_coordenada_nunca_aparece(mundo):
    c, _, _ = mundo
    html = pagina(c)
    t = texto(html)
    assert "Sem coordenada no cadastro" in t and "Usina Epsilon" in t
    # número impresso de coordenada: 3 casas decimais ou mais, com ponto ou vírgula, em qualquer lugar da página
    assert not re.findall(r"\d+[.,]\d{3,}", re.sub(r"<(style|script)\b.*?</\1>", "", html, flags=re.S))
    for linha_col in (A, B, C, DD, F, G):
        lat, lon = centro(*linha_col)
        for numero in (f"{abs(lat):.3f}", f"{abs(lon):.3f}", f"{abs(lat):.3f}".replace(".", ","), f"{abs(lon):.3f}".replace(".", ",")):
            assert numero not in html, numero


def test_filtro_por_cliente(mundo):
    c, _, _ = mundo
    html = pagina(c, cliente="Cliente Y")
    assert list(cartoes(html)) == [] and list(linhas(html)) == ["Usina Gama", "Usina Zeta"]
    assert valor(faixa(html)["cobertura"]) == "3"
    assert 'value="Cliente Y" selected' in html
    assert "Usina Epsilon" not in html                         # a sem coordenada de outro cliente não aparece
    sem_filtro = pagina(c, cliente="Nao Existe")                # cliente inventado = sem filtro
    assert len(cartoes(sem_filtro)) + len(linhas(sem_filtro)) == 4


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
    assert len(cartoes(html)) + len(linhas(html)) == 4                    # as outras fontes seguem valendo


def test_fonte_que_nunca_leu_diz_sem_leitura_boa_e_nao_mostra_zero(mundo):
    c, sessao, _ = mundo
    del sessao.arquivos[URL_INMET]
    html = pagina(c)
    t = texto(html)
    assert "INMET fora agora; ainda sem leitura boa" in t
    assert "Os números da faixa e as listas não incluem: avisos do INMET." in t       # a tela diz que está incompleta
    assert 'class="cl-fonte cl-fora"' in html
    f = faixa(html)
    assert valor(f["sem"]) == "—" and "não dá para dizer" in texto(f["sem"])           # traço, nunca "0" nem número solto
    assert "sem leitura de avisos do INMET" in texto(f["atencao"])
    assert "Sem leitura de avisos do INMET: não dá para dizer que não há alerta" not in t     # há usinas nas duas listas: sem título de vazio


def test_texto_do_inmet_e_de_terceiros_e_sai_escapado(mundo):
    c, sessao, _ = mundo
    veneno = caixa_aviso(9, "x", "Perigo <b>Grande</b>", -45.0, -44.88, -5.15, -5.0, evento='<script>alert("oi")</script>')
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
    beta = linhas(pagina(c))["Usina Beta"]
    assert "Onda de calor" in texto(beta) and "a partir de 07/10 08:00" in texto(beta)
    assert 'title="Perigo: a partir de 07/10 08:00, até 08/10 20:00"' in beta


def test_aviso_futuro_que_estraga_usina_ja_aparece_em_agir_agora_com_o_inicio(mundo):
    c, sessao, _ = mundo
    futuro = caixa_aviso(9, "x", "Perigo", -45.0, -44.88, -5.15, -5.0, evento="Vendaval", inicio="2026-10-07 08:00",
                         fim="2026-10-08 20:00")
    sessao.arquivos[URL_INMET] = inmet(extra_futuro=[futuro])
    html = pagina(c)
    assert list(cartoes(html)) == ["Usina Alfa", "Usina Beta"]
    beta = texto(cartoes(html)["Usina Beta"])
    assert "Vendaval · Perigo" in beta and "Vendaval: Perigo (é provável que cause estrago)" in beta   # aviso como motivo principal
    assert "Quando: a partir de 07/10 08:00, até 08/10 20:00" in beta


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
    assert "focos: arquivos até 14:10" in texto(faixa(html)["agir"])


def test_aviso_vencido_nao_conta(mundo):
    c, sessao, _ = mundo
    vencido = caixa_aviso(9, "x", "Grande Perigo", -45.0, -44.9, -5.15, -5.0, evento="Vendaval", fim="2026-10-06 14:00")
    sessao.arquivos[URL_INMET] = inmet(extra_hoje=[vencido])
    html = pagina(c)
    # o "Entenda os alertas" (09/10/2026) explica todo evento que o INMET publica, o Vendaval inclusive, na lista dos "outros";
    # o que não pode é o aviso vencido aparecer como alerta nem entre os avisos que estão valendo agora
    assert "Vendaval" not in html[:html.index('id="cl-entenda"')]
    assert "Vendaval" not in html[html.index('id="cl-entenda"'):html.index('class="cl-mais-eventos"')]


def test_uma_so_leitura_da_rede_por_fonte_mesmo_com_varias_visitas(mundo):
    c, sessao, _ = mundo
    pagina(c)
    n = len(sessao.pedidos)
    pagina(c)
    pagina(c, "/t/performance/clima?cliente=Cliente X")                    # o filtro não muda o conjunto de pontos do risco
    pagina(c, "/t/performance/clima?todas=1")                              # nem a lista inteira
    assert len(sessao.pedidos) == n


def test_rodape_com_as_fontes_e_a_atribuicao(mundo):
    c, _, _ = mundo
    t = texto(pagina(c))
    assert "Dados: INMET, INPE (Programa Queimadas)." in t
    assert "Programa Queimadas" in t and "somente leitura" in t.lower()
    assert "que não aparecem na tela" in t


# ── o caminho até a página da usina ──────────────────────────────────────────────────────────────────────────────────────

def test_cada_cartao_e_cada_linha_levam_a_pagina_da_usina(mundo):
    c, _, _ = mundo
    html = pagina(c)
    assert 'href="/t/performance/clima/usina/1"' in cartoes(html)["Usina Alfa"]
    assert 'href="/t/performance/clima/usina/3"' in linhas(html)["Usina Gama"]
    assert 'href="/t/performance/clima/usina/2"' in linhas(html)["Usina Beta"]


def test_o_link_da_usina_guarda_o_filtro_de_cliente(mundo):
    c, _, _ = mundo
    html = pagina(c, cliente="Cliente Y")
    assert 'href="/t/performance/clima/usina/3?cliente=Cliente+Y"' in linhas(html)["Usina Gama"]


def test_a_tela_principal_nunca_chama_a_nasa(mundo_usina):
    c, _, _, power = mundo_usina
    pagina(c)
    pagina(c, todas="1")
    pagina(c, cliente="Cliente Y")
    assert power.pedidos == []


# ── a grade por estado ───────────────────────────────────────────────────────────────────────────────────────────────

def test_a_grade_por_estado_tem_27_quadrados_o_numero_de_usinas_com_alerta_e_a_cor_do_pior(mundo):
    c, _, _ = mundo
    html = pagina(c)
    q = quadrados(html)
    assert len(q) == 27 and set(q) == set(V.UFS_GRADE)
    pi = q["PI"]
    assert "cl-uf--agir" in pi and re.search(r'<span class="cl-uf-n">4</span>', pi)             # Alfa, Gama, Zeta e Beta
    assert "grid-column:4;grid-row:3" in pi and 'title="PI: 4 usinas com alerta, 1 para agir agora"' in pi
    pa = q["PA"]
    assert "cl-uf--" not in pa and re.search(r'<span class="cl-uf-n">·</span>', pa)
    assert "cada quadrado é um estado (não é um mapa)" in texto(html)


def test_legenda_da_grade(mundo):
    c, _, _ = mundo
    t = texto(pagina(c))
    for frase in ("tem usina para agir agora", "só atenção", "sem usina com alerta", "número = usinas com alerta no estado"):
        assert frase in t


def test_a_grade_nao_diz_sem_usina_com_alerta_quando_uma_fonte_nao_foi_lida(mundo):
    c, sessao, _ = mundo
    del sessao.arquivos[URL_INMET]
    html = pagina(c)
    assert "sem usina com alerta nas fontes lidas" in texto(html)
    assert 'title="PA: sem usina com alerta nas fontes lidas"' in quadrados(html)["PA"]


# ── a matriz da Atenção: as 20 primeiras e "Ver todas" ───────────────────────────────────────────────────────────────

def test_matriz_com_25_usinas_mostra_as_20_primeiras_e_o_link_para_ver_todas(mundo25):
    c, _, _ = mundo25
    html = pagina(c)
    assert len(linhas(html)) == 20 and list(linhas(html))[0] == "Usina 01" and list(linhas(html))[-1] == "Usina 20"
    t = texto(html)
    assert "25 usinas, as 20 primeiras" in t and "Ver todas (25)" in t
    assert 'href="/t/performance/clima?todas=1#cl-atencao"' in html


def test_com_todas_a_matriz_mostra_as_25_e_oferece_voltar(mundo25):
    c, _, _ = mundo25
    html = pagina(c, todas="1")
    assert len(linhas(html)) == 25 and list(linhas(html))[-1] == "Usina 25"
    t = texto(html)
    assert "25 usinas" in t and "25 usinas, as 20 primeiras" not in t and "Ver todas" not in t and "Ver só as 20 primeiras" in t
    assert 'href="/t/performance/clima#cl-atencao"' in html


def test_ver_todas_guarda_o_filtro_de_cliente(mundo25):
    c, _, _ = mundo25
    html = pagina(c, cliente="Cliente X")
    assert 'href="/t/performance/clima?cliente=Cliente+X&amp;todas=1#cl-atencao"' in html


def test_com_20_usinas_ou_menos_nao_ha_link_nem_corte(mundo):
    c, _, _ = mundo
    t = texto(pagina(c))
    assert "Ver todas" not in t and "as 20 primeiras" not in t and "3 usinas" in t


# ── 375 px ───────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_375_px_a_tela_usa_as_classes_responsivas_e_o_css_as_quebra_em_uma_coluna(mundo):
    c, _, _ = mundo
    html = pagina(c)
    assert 'href="/static/clima.css"' in html
    css = c.get("/static/clima.css").get_data(as_text=True)
    # as grades da tela viram uma coluna só abaixo de 700 px, e o texto de terceiros quebra em vez de alargar a página
    midia = re.search(r"@media\s*\(max-width:\s*(\d+)px\)\s*\{(.*)\}\s*$", css, flags=re.S)
    assert midia and 375 < int(midia.group(1)) <= 820
    for classe in ("cl-faixa", "cl-lista", "cl-duas", "cl-fontes"):
        assert classe in html and classe in midia.group(2), classe
    assert "overflow-wrap:anywhere" in css and "min-width:0" in css


def test_375_px_a_grade_de_estados_e_a_matriz_rolam_dentro_da_caixa_e_nunca_a_pagina(mundo):
    c, _, _ = mundo
    html = pagina(c)
    css = c.get("/static/clima.css").get_data(as_text=True)
    fora_da_midia = re.sub(r"@media[^{]*\{.*\}\s*$", "", css, flags=re.S)
    for caixa in ("cl-ufs-rolagem", "cl-matriz"):
        assert f'class="{caixa}"' in html
        assert re.search(r"\." + caixa + r"\{[^}]*overflow-x:auto", fora_da_midia), caixa


def test_375_px_nenhuma_largura_fixa_passa_da_tela_do_celular(mundo):
    c, _, _ = mundo
    css = c.get("/static/clima.css").get_data(as_text=True)
    fora_da_midia = re.sub(r"/\*.*?\*/", "", re.sub(r"@media[^{]*\{.*\}\s*$", "", css, flags=re.S), flags=re.S)
    largas = []
    for regra in re.finditer(r"([^{}]+)\{([^{}]*)\}", fora_da_midia):
        for m in re.finditer(r"(?<![-\w])(?:min-)?width:\s*(\d+)px", regra.group(2)):
            if int(m.group(1)) > 340:
                largas.append((regra.group(1).strip(), m.group(0)))
    # a ÚNICA largura maior que o celular é a da tabela da matriz, que mora numa caixa com overflow-x:auto (testada acima)
    assert largas == [(".cl-matriz table", "min-width:1000px")]


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


def test_sem_alerta_e_com_fonte_fora_a_tela_nao_diz_nenhuma_usina_para_agir_agora(mundo, monkeypatch):
    c, _, _ = mundo
    _instalar(monkeypatch, L.Leitura(None, None, erro="HTTP 500"), _focos_vazio(), _risco())
    html = pagina(c)
    t = texto(html)
    assert "Sem leitura de avisos do INMET: não dá para dizer que não há alerta" in t
    assert "Nenhuma usina para agir agora" not in t and "Nenhuma usina em atenção" not in t
    f = faixa(html)
    # o agir usa avisos e focos, o atenção usa avisos e risco: cada um perdeu o INMET e segue com o que leu, em âmbar e com a razão
    assert (valor(f["agir"]), valor(f["atencao"]), valor(f["sem"])) == ("0", "0", "—")
    assert "cl-na" in f["agir"] and "cl-na" in f["atencao"] and "sem leitura de avisos do INMET" in texto(f["agir"])
    assert "Os números da faixa e as listas não incluem: avisos do INMET." in t and "Lendo agora" not in t
    assert '<meta http-equiv="refresh" content="60">' in html


def test_fonte_lendo_a_tela_recarrega_em_10_s_e_a_nota_diz_lendo_e_nao_fora(mundo, monkeypatch):
    c, _, _ = mundo
    _instalar(monkeypatch, L.Leitura(None, None, erro=L.LENDO), _focos_vazio(), _risco())
    html = pagina(c)
    t = texto(html)
    assert '<meta http-equiv="refresh" content="10">' in html
    assert "Lendo agora: avisos do INMET." in t and "Os números da faixa e as listas não incluem" not in t
    assert "Sem leitura de avisos do INMET: não dá para dizer que não há alerta" in t
    assert "lendo avisos do INMET" in texto(faixa(html)["agir"])


def test_tudo_lido_e_sem_alerta_a_tela_pode_dizer_que_nao_ha(mundo, monkeypatch):
    c, _, _ = mundo
    _instalar(monkeypatch, _leitura({"avisos": [], "ignorados": [], "lidos": 0}), _focos_vazio(), _risco())
    html = pagina(c)
    t = texto(html)
    assert "Nenhuma usina para agir agora" in t and "Nenhuma usina em atenção" in t
    assert {i: valor(x) for i, x in faixa(html).items()} == {"agir": "0", "atencao": "0", "sem": "6", "cobertura": "6"}


def test_fonte_pela_metade_deixa_a_celula_ambar_e_diz_parcial(mundo, monkeypatch):
    c, _, _ = mundo
    avisos = _leitura({"avisos": [], "ignorados": ["aviso 7: sem polígono"], "lidos": 1})
    _instalar(monkeypatch, avisos, _focos_vazio(), _risco())
    html = pagina(c)
    f = faixa(html)
    assert 'class="cl-cel cl-agir cl-na"' in f["agir"] and "INMET: parcial" in texto(f["agir"])
    assert 'class="cl-cel cl-atencao cl-na"' in f["atencao"] and "cl-na" in f["sem"] and "nas fontes lidas" in texto(f["sem"])
    assert 'class="cl-fonte cl-atencao"' in html and "1 aviso foi ignorado" in texto(html)


def test_previsao_de_ontem_a_matriz_diz_ontem_e_hoje(mundo):
    c, sessao, _ = mundo
    sessao.modificado = "Mon, 05 Oct 2026 09:32:00 GMT"
    html = pagina(c)
    assert "Risco de fogo · ontem · hoje · amanhã · qui 08/10" in texto(html)
    assert re.findall(r'<span class="cl-c cl-c-a"[^>]*>([^<]+)</span>', linhas(html)["Usina Gama"]) == ["Alto", "Alto"]


def test_usina_fora_da_grade_do_inpe_aparece_na_linha_de_cobertura_com_o_motivo(mundo, monkeypatch):
    c, _, _ = mundo
    por = {str(i): [Amostra(0.1, "ponto")] * 4 for i in range(1, 8)}
    por["6"] = [Amostra(None, "sem_dado")] * 4                        # Zeta
    por["7"] = [Amostra(None, "fora_da_grade")] * 4                   # Eta
    _instalar(monkeypatch, _leitura({"avisos": [], "ignorados": [], "lidos": 0}), _focos_vazio(), _risco(por))
    t = texto(pagina(c))
    assert "Risco de fogo sem dado (sem vegetação no entorno): Usina Zeta." in t
    assert "Risco de fogo sem dado (fora da grade do INPE): Usina Eta." in t


def test_o_css_tem_a_celula_ambar_das_fontes_que_nao_estao_inteiras(mundo):
    c, _, _ = mundo
    css = c.get("/static/clima.css").get_data(as_text=True)
    assert ".cl-cel.cl-na .cl-valor{color:var(--cl-atencao)}" in css and ".cl-fonte.cl-atencao{border-color:var(--alerta)}" in css

"""Torre Performance -> Clima e risco: a página de UMA usina, /t/performance/clima/usina/<id> (07/10/2026): os alertas dela e a
irradiação diária da NASA POWER (gráfico dos últimos 30 dias e o mês até agora). Mundo inventado de `clima_mundo.py`; a NASA é uma
sessão falsa (a série vai até 02/10 e o valor de cada dia é o seu número: 1,0 em 01/10, 2,0 em 02/10)."""
import json
import re
from datetime import date, timedelta

import pytest

from nexus.cadastro.servico import Carga
from nexus.performance.clima import leitura as L

from clima_mundo import (A, AGORA, PUBLICADO_ATE, URL_INMET, Relogio, _mundo, arquivos_do_mundo, caixa_aviso, centro,  # noqa: F401
                         inmet, mundo_usina, pagina, texto, u)
from clima_power import SessaoPower

URL = "/t/performance/clima/usina/{}"


def usina_pagina(c, id_="1", **consulta):
    return pagina(c, URL.format(id_), **consulta)


def sem_svg(html):
    return re.sub(r"<svg\b.*?</svg>", " ", html, flags=re.S)


def painel(html, id_):
    """O trecho de uma seção da página, pelo id do título."""
    return re.search(rf'<section[^>]*aria-labelledby="{id_}".*?</section>', html, flags=re.S).group(0)


# ── a página ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_exige_login(mundo_usina):
    _, _, app, _ = mundo_usina
    assert app.test_client().get(URL.format("1")).status_code == 302


def test_a_pagina_responde_com_nome_cliente_uf_e_o_nivel_da_usina(mundo_usina):
    c, _, _, _ = mundo_usina
    html = usina_pagina(c, "1")
    assert '<h1 class="cl-titulo">Usina Alfa</h1>' in html and "Cliente X · PI" in texto(html)
    assert re.search(r'<span class="cl-pill cl-pill--agir"[^>]*>Agir agora</span>', html) and "atualizada às 15:00" in texto(html)
    assert "Usina Alfa" in re.search(r"<title>(.*?)</title>", html, flags=re.S).group(1)


def test_o_nivel_de_cada_usina_do_mundo(mundo_usina):
    c, _, _, _ = mundo_usina
    esperado = {"1": ("agir", "Agir agora"), "2": ("atencao", "Atenção"), "3": ("atencao", "Atenção"), "4": ("sem", "Sem alerta"),
                "6": ("atencao", "Atenção"), "7": ("sem", "Sem alerta")}
    for id_, (classe, rotulo) in esperado.items():
        assert re.search(rf'<span class="cl-pill cl-pill--{classe}"[^>]*>{rotulo}</span>', usina_pagina(c, id_)), id_


def test_os_alertas_da_usina_com_foco_aviso_e_risco(mundo_usina):
    c, _, _, _ = mundo_usina
    t = texto(painel(usina_pagina(c, "1"), "cl-alertas"))
    assert "Fogo a 1,2 km" in t and "1 foco de queimada a até 5 km" in t and "visto pelo satélite GOES-19 às 14:50" in t
    assert "Tempestade: Perigo (é provável que cause estrago)" in t and "Quando: agora, até 23:59" in t
    assert "Baixa Umidade" in t and "Perigo Potencial" in t
    assert t.count("0,97") == 4 and "crítico" in t


def test_usina_sem_alerta_diz_o_que_nao_ha(mundo_usina):
    c, _, _, _ = mundo_usina
    t = texto(painel(usina_pagina(c, "4"), "cl-alertas"))
    assert "Nenhum aviso do Instituto Nacional de Meteorologia (INMET) sobre esta usina" in t and "Nenhum foco a até 5 km" in t
    assert "Foco a" not in t and "Agir agora" not in t


def test_os_quatro_dias_do_risco_da_usina_em_atencao(mundo_usina):
    c, _, _, _ = mundo_usina
    html = painel(usina_pagina(c, "3"), "cl-alertas")
    assert re.findall(r'<span class="cl-c cl-c-(\w)"[^>]*>([^<]+)</span>', html) == [("a", "0,75"), ("a", "0,80"), ("n", "0,60"), ("n", "0,40")]


def test_a_pagina_tem_as_fontes_dos_alertas_e_a_da_nasa_com_a_hora(mundo_usina):
    c, _, _, _ = mundo_usina
    html = usina_pagina(c, "1")
    t = texto(painel(html, "cl-fontes"))
    assert "INMET" in t and "lido às 15:00" in t and "arquivos até 14:50" in t
    assert "Prediction Of Worldwide Energy Resources, projeto da NASA (NASA POWER) · irradiação: lida às 15:00 · publicada até 02/10" in t
    assert len(re.findall(r'class="cl-fonte cl-ok"', html)) == 5                # a NASA FIRMS desde 10/10/2026


# ── a irradiação: gráfico, mês e fonte ───────────────────────────────────────────────────────────────────────────────

def test_o_grafico_dos_ultimos_30_dias_e_um_svg_feito_no_servidor(mundo_usina):
    c, _, _, _ = mundo_usina
    html = usina_pagina(c, "1")
    svg = re.search(r'<svg class="cl-grafico"[^>]*>.*?</svg>', html, flags=re.S).group(0)
    assert 'viewBox="0 0 620 270"' in svg and 'role="img"' in svg and "publicado até 02/10" in svg
    pontos = re.search(r'<polyline class="cl-nasa" points="([^"]+)"', svg).group(1).split()
    assert len(pontos) == 26                                                   # 07/09 a 02/10: os dias que a NASA já publicou
    assert re.findall(r'<text[^>]*>([^<]+)</text>', svg)[:4] == ["0", "2", "4", "6"] and "07/09" in svg and "06/10" in svg
    assert '<rect class="cl-faixa-nasa"' in svg                               # os dias de 03 a 06/10, ainda não publicados
    assert "<script" not in svg and "http" not in svg.replace("http://www.w3.org/2000/svg", "")


def test_o_mes_ate_agora_soma_os_dias_publicados_e_diz_ate_que_dia(mundo_usina):
    c, _, _, _ = mundo_usina
    mini = re.search(r'<div class="cl-mini" data-id="mes">.*?</div>', usina_pagina(c, "1"), flags=re.S).group(0)
    t = texto(mini)
    assert "outubro/2026" in t and "3,0" in t and "kWh/m²" in t and "2 dias, até 02/10" in t


def test_a_pagina_diz_que_a_nasa_atrasa_e_mostra_os_valores_dia_a_dia(mundo_usina):
    c, _, _, _ = mundo_usina
    html = usina_pagina(c, "1")
    t = texto(painel(html, "cl-irradiacao"))
    assert "faixa" in t and "ainda não publicado" in t
    linhas_ = re.findall(r"<tr><td>(\d\d/\d\d)</td><td>([^<]+)</td></tr>", html)
    assert len(linhas_) == 30 and linhas_[0][0] == "07/09" and ("02/10", "2,00") in linhas_ and linhas_[-1] == ("06/10", "—")


def test_a_comparacao_com_a_etm_e_proxima_etapa_e_diz_por_que(mundo_usina):
    c, _, _, _ = mundo_usina
    t = texto(painel(usina_pagina(c, "1"), "cl-irradiacao"))
    assert "Comparação com a ETM: próxima etapa" in t
    assert "BD_Thopen" in t and "BD_Performance" in t and "GHI (kWh/m²)" in t


def test_o_rodape_cita_a_fonte_e_a_grade(mundo_usina):
    c, _, _, _ = mundo_usina
    t = texto(usina_pagina(c, "1"))
    assert "NASA LaRC POWER" in t and "cerca de 50 km" in t and "Dados: Instituto Nacional de Meteorologia (INMET), Instituto Nacional de Pesquisas Espaciais (INPE) (Programa Queimadas)" in t


def test_dia_sem_leitura_no_meio_do_mes_aparece_e_nao_vira_zero(mundo_usina):
    c, _, _, power = mundo_usina
    power.buracos = {date(2026, 10, 1)}
    html = usina_pagina(c, "1")
    t = texto(html)
    assert "1 dia sem leitura da NASA (01/10)" in t and "2,0" in texto(re.search(r'<div class="cl-mini" data-id="mes">.*?</div>', html, flags=re.S).group(0))
    assert ("01/10", "—") in re.findall(r"<tr><td>(\d\d/\d\d)</td><td>([^<]+)</td></tr>", html)


def test_nasa_ainda_sem_nenhum_dia_do_mes(mundo_usina):
    c, _, _, power = mundo_usina
    power.publicado_ate = date(2026, 9, 28)
    t = texto(usina_pagina(c, "1"))
    assert "A NASA ainda não publicou nenhum dia de outubro (último dia publicado: 28/09)" in t


def test_nasa_sem_nenhum_dia_na_janela_inteira(mundo_usina):
    c, _, _, power = mundo_usina
    power.publicado_ate = date(2026, 8, 1)
    html = usina_pagina(c, "1")
    assert "A NASA não publicou nenhum dia nos últimos 40 dias" in texto(html) and 'class="cl-grafico"' not in html


# ── a NASA fora do ar, ou lenta ──────────────────────────────────────────────────────────────────────────────────────

def test_nasa_fora_a_pagina_responde_sem_grafico_e_os_alertas_seguem(mundo_usina):
    c, _, _, power = mundo_usina
    power.status = 503
    html = usina_pagina(c, "1")
    t = texto(html)
    assert "Prediction Of Worldwide Energy Resources, projeto da NASA (NASA POWER) · irradiação: fora agora; ainda sem leitura boa" in t and "HTTP 503" in t
    assert 'class="cl-grafico"' not in html and 'class="cl-fonte cl-fora"' in html
    assert "Fogo a 1,2 km" in t and re.search(r'cl-pill--agir"[^>]*>Agir agora<', html)            # os alertas não dependem da NASA


def test_nasa_com_formato_diferente_diz_o_que_viu_e_nao_mostra_numero(mundo_usina):
    c, _, _, power = mundo_usina
    power.corpo = json.dumps({"properties": {"parameter": {"ALLSKY_SFC_SW_DWN": {"20261001": 3.0}}}}).encode()      # sem a unidade
    html = usina_pagina(c, "1")
    assert "não informou a unidade" in texto(html) and 'class="cl-grafico"' not in html


def test_nasa_que_cai_depois_de_uma_leitura_boa_mostra_a_ultima_com_a_hora(mundo_usina):
    c, _, _, power = mundo_usina
    usina_pagina(c, "1")
    L.usar_relogio(Relogio(AGORA.timestamp() + L.TTL_POWER_S + 60))
    power.status = 500
    html = usina_pagina(c, "1")
    t = texto(html)
    assert "Prediction Of Worldwide Energy Resources, projeto da NASA (NASA POWER) · irradiação: fora agora; última leitura boa às 15:00" in t and "HTTP 500" in t
    assert 'class="cl-grafico"' in html                                       # a série boa segue na tela, dita velha
    assert 'class="cl-fonte cl-atencao"' in html


def test_nasa_lendo_a_pagina_recarrega_em_10_s(mundo_usina, monkeypatch):
    c, _, _, _ = mundo_usina
    monkeypatch.setattr(L, "irradiacao", lambda *a, **k: L.Leitura(None, None, erro=L.LENDO))
    html = usina_pagina(c, "1")
    assert '<meta http-equiv="refresh" content="10">' in html and "Lendo a irradiação do Prediction Of Worldwide Energy Resources, projeto da NASA (NASA POWER)" in texto(html)


def test_a_pagina_se_recarrega_sozinha_a_cada_minuto(mundo_usina):
    c, _, _, _ = mundo_usina
    assert '<meta http-equiv="refresh" content="60">' in usina_pagina(c, "1")


# ── a NASA só é chamada pela página da usina, com cache e sem entregar a posição exata ──────────────────────────────

def test_a_nasa_e_pedida_uma_vez_por_usina_e_guardada_por_12_h(mundo_usina):
    c, _, _, power = mundo_usina
    usina_pagina(c, "1")
    usina_pagina(c, "1")
    usina_pagina(c, "1", cliente="Cliente X")
    assert len(power.pedidos) == 1
    usina_pagina(c, "2")
    assert len(power.pedidos) == 2                                            # outra usina, outro pedido
    L.usar_relogio(Relogio(AGORA.timestamp() + L.TTL_POWER_S + 1))
    usina_pagina(c, "1")
    assert len(power.pedidos) == 3


def test_o_pedido_a_nasa_leva_a_janela_de_40_dias_e_a_coordenada_com_duas_casas(mundo_usina):
    c, _, _, power = mundo_usina
    usina_pagina(c, "1")
    q = power.consulta()
    lat, lon = centro(*A)
    assert (q["latitude"], q["longitude"]) == (f"{lat:.2f}", f"{lon:.2f}")
    assert (q["start"], q["end"]) == ("20260828", "20261006") and q["parameters"] == "ALLSKY_SFC_SW_DWN"
    assert len(q["latitude"].split(".")[1]) == 2


def test_a_tela_principal_nunca_chama_a_nasa(mundo_usina):
    c, _, _, power = mundo_usina
    pagina(c)
    pagina(c, "/t/performance/clima", todas="1")
    pagina(c, "/t/performance/clima", cliente="Cliente Y")
    assert power.pedidos == []


def test_a_coordenada_nunca_aparece_na_pagina_da_usina(mundo_usina):
    c, _, _, power = mundo_usina
    lat, lon = centro(*A)
    for id_ in ("1", "3", "5"):
        html = usina_pagina(c, id_)
        fora_do_svg = sem_svg(re.sub(r"<(style|script)\b.*?</\1>", "", html, flags=re.S))
        assert not re.findall(r"\d+[.,]\d{3,}", fora_do_svg), id_                # número impresso com 3 casas ou mais
        for numero in (f"{abs(lat):.3f}", f"{abs(lon):.3f}", f"{abs(lat):.2f}", f"{abs(lon):.2f}"):
            assert numero not in fora_do_svg, numero
    assert "power.exemplo.test" not in usina_pagina(c, "1") and "latitude=" not in usina_pagina(c, "1")


# ── usina que não existe, e usina sem coordenada ────────────────────────────────────────────────────────────────────

def test_usina_que_nao_existe_da_404_com_aviso_claro_e_link_de_volta(mundo_usina):
    c, _, _, power = mundo_usina
    r = c.get(URL.format("999"))
    html = r.get_data(as_text=True)
    assert r.status_code == 404 and "Usina não encontrada" in texto(html) and 'href="/t/performance/clima"' in html
    assert power.pedidos == []


@pytest.mark.parametrize("id_", ["0", "-1", "abc", "1%2F2", "1;2"])
def test_id_estranho_tambem_da_404_e_nao_quebra(mundo_usina, id_):
    c, _, _, power = mundo_usina
    assert c.get(URL.format(id_)).status_code == 404 and power.pedidos == []


def test_usina_sem_coordenada_da_aviso_claro_e_nao_chama_nenhuma_fonte(mundo_usina):
    c, sessao, _, power = mundo_usina
    antes = len(sessao.pedidos)
    r = c.get(URL.format("5"))
    html = r.get_data(as_text=True)
    t = texto(html)
    assert r.status_code == 200 and "Usina Epsilon" in t and "Sem coordenada no cadastro" in t and "Corrija a coordenada" in t
    assert power.pedidos == [] and len(sessao.pedidos) == antes
    assert 'id="cl-alertas"' not in html and 'id="cl-irradiacao"' not in html


# ── cliente, cadastro e texto de terceiros ───────────────────────────────────────────────────────────────────────────

def test_o_link_de_volta_guarda_o_filtro_de_cliente(mundo_usina):
    c, _, _, _ = mundo_usina
    assert 'href="/t/performance/clima"' in usina_pagina(c, "1")
    assert 'href="/t/performance/clima?cliente=Cliente+X"' in usina_pagina(c, "1", cliente="Cliente X")
    assert 'href="/t/performance/clima"' in usina_pagina(c, "1", cliente="Inventado")


def test_sem_cadastro_a_pagina_responde_e_diz_o_que_falta(app, logado):
    r = logado.get(URL.format("1"))
    assert r.status_code == 200
    t = texto(r.get_data(as_text=True))
    assert "Cadastro indisponível" in t and "NEXUS_CHAVE_CADASTRO" in t


def test_nome_da_usina_e_do_cliente_saem_escapados(tmp_path, monkeypatch):
    carga = Carga(entidades={"clientes": [{"id": "1", "ordem": 1, "valores": {"nome": "Cliente <i>Y</i>"}}],
                             "usinas": [u("1", 'Usina <b>X</b> & "Cia"', "1", A)]},
                  listas={"status_usina": ["OPERAÇÃO"], "uf": ["PI"]})
    power = SessaoPower(PUBLICADO_ATE)
    c, _, _ = _mundo(tmp_path, monkeypatch, carga, arquivos_do_mundo(), power)
    try:
        html = usina_pagina(c, "1")
        assert "<b>X</b>" not in html and "<i>Y</i>" not in html
        assert "&lt;b&gt;X&lt;/b&gt;" in html and "&lt;i&gt;Y&lt;/i&gt;" in html
    finally:
        L.usar_sessao(None)
        L.usar_relogio(None)
        L.limpar_cache()


def test_texto_do_inmet_na_pagina_da_usina_sai_escapado(mundo_usina):
    c, sessao, _, _ = mundo_usina
    veneno = caixa_aviso(9, "x", "Perigo <b>Grande</b>", -45.0, -44.9, -5.15, -5.0, evento='<script>alert("oi")</script>')
    sessao.arquivos[URL_INMET] = inmet(extra_hoje=[veneno])
    html = usina_pagina(c, "1")
    assert '<script>alert("oi")</script>' not in html and "<b>Grande</b>" not in html and "&lt;script&gt;" in html


# ── 375 px ───────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_375_px_o_grafico_escala_com_a_largura_e_a_tabela_dia_a_dia_fica_recolhida(mundo_usina):
    c, _, _, _ = mundo_usina
    html = usina_pagina(c, "1")
    css = c.get("/static/clima.css").get_data(as_text=True)
    assert re.search(r"\.cl-grafico\{[^}]*width:100%", css) and re.search(r"\.cl-grafico\{[^}]*height:auto", css)
    assert '<details class="cl-dias-tabela">' in html and "open" not in re.search(r'<details class="cl-dias-tabela"[^>]*>', html).group(0)
    assert 'width="620"' not in html                                          # nenhuma largura fixa no SVG


def test_375_px_a_pagina_usa_so_as_classes_responsivas_do_css(mundo_usina):
    c, _, _, _ = mundo_usina
    css = c.get("/static/clima.css").get_data(as_text=True)
    midia = re.search(r"@media\s*\(max-width:\s*(\d+)px\)\s*\{(.*)\}\s*$", css, flags=re.S)
    assert midia and "cl-minis" in midia.group(2) and "cl-usina-grade" in midia.group(2)
    html = usina_pagina(c, "1")
    assert 'class="cl-minis"' in html and 'class="cl-usina-grade"' in html

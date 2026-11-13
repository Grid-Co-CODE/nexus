"""O Mapa de equipe com o mapa de verdade (11/11/2026): o MapLibre sobre o mapa base do Brasil (`mapa_base.py`).

Levi, com o guia e a prévia do Willian: "Quero que utilize essa referência para completar nosso mapa", com três condições:
"Pode tirar a opção 3D", "Quero que apareça só Brasil" e "Quero em estilo Nexus". E a regra da LGPD trocada por ele no mesmo
dia ("Pode trocar"): a coordenada vai ao navegador SÓ dos técnicos que o mapa mostra, só para quem pode ver e só depois de
gravado o registro de quem abriu. Sem o mapa base no servidor, a tela é o desenho dos estados de antes (o deploy não
depende do upload), e `?mapa=desenho` força o desenho.

Os fixtures e as pessoas inventadas são os de `test_equipe_tela`; nada vai à rede."""
import json
import re
from pathlib import Path

import pytest
from test_equipe_tela import (ADMIN, ANDANDO, COORDS, DIGITOS, EMAIL, FORA, FORA_DO_PILOTO, MANHA, NA_USINA, NOME,  # noqa: F401
                              NOME_USINA, PCM, PONTO, SEM_PERMISSAO, SEM_POSICAO, SEM_SINAL, USINA_A, USINA_B,
                              _acessos, _entrar, _html, _receber, banco, clima_das_usinas, pontos, relogio, risco, setor)
from test_mapa_base import _pmtiles

from nexus.campo.equipe import mapa_base as MB


@pytest.fixture
def com_mapa_base(app, banco):
    p = Path(app.config["NEXUS_DADOS"]) / "mapa"
    p.mkdir(parents=True, exist_ok=True)
    (p / MB.NOME).write_bytes(_pmtiles())
    return p


def _dados(html) -> dict:
    m = re.search(r'<script type="application/json" id="eq-dados">(.*?)</script>', html, flags=re.S)
    assert m, "a página não trouxe os dados do mapa"
    return json.loads(m.group(1))


def _lonlat(pid):
    (lat, lon), _min, _mov = PONTO[pid]
    return [round(lon, 5), round(lat, 5)]


def test_sem_o_mapa_base_a_tela_segue_no_desenho_dos_estados(cliente, pontos, setor):
    _, html = _html(_entrar(cliente, EMAIL[PCM]))
    assert '<svg class="eq-svg' in html and 'id="eq-mapa"' not in html and "maplibre-gl" not in html
    assert not [d for d in DIGITOS if d in html]                           # a regra de antes, sem o mapa de verdade


def test_com_o_mapa_base_a_coordenada_vai_so_de_quem_o_mapa_mostra(cliente, pontos, setor, com_mapa_base):
    """O mapa de verdade precisa da coordenada no navegador: ela vai só dos técnicos que o mapa desenha (o piloto e o
    filtro, com ponto nos 7 dias), depois do registro "abriu_mapa". Quem está fora do piloto, o sem permissão sem ponto
    e o sem posição não têm coordenada na página."""
    _, html = _html(_entrar(cliente, EMAIL[PCM]))
    assert 'id="eq-mapa"' in html and '<svg class="eq-svg' not in html
    assert "vendor/maplibre-gl-4.7.1/maplibre-gl.js" in html and "vendor/pmtiles-3.2.1/pmtiles.js" in html
    assert "campo-mapa.js" in html
    d = _dados(html)
    assert d["blocos"] == "/t/campo/equipe/mapa-base.pmtiles" and d["modo"] == "tecnicos"
    assert d["brasil"].endswith("clima/ibge-brasil-minima.geojson") and "{fontstack}/{range}.pbf" in d["fontes"]
    tec = {t["pid"]: t for t in d["tecnicos"]}
    assert set(tec) == {NA_USINA, ANDANDO, SEM_SINAL, FORA}
    for pid in tec:
        assert tec[pid]["c"] == _lonlat(pid) and tec[pid]["nome"] == NOME[pid]
    assert tec[ANDANDO]["tom"] == "info" and tec[NA_USINA]["tom"] == "ok" and tec[ANDANDO]["ini"] == "AT"
    assert "tecnico=2" in tec[ANDANDO]["url"] and "de=" in tec[ANDANDO]["url"]           # o clique abre o percurso
    # quem não aparece no mapa não tem coordenada na página
    (lat, lon), _m, _v = PONTO[FORA_DO_PILOTO]
    assert str(round(lat, 5))[-5:] not in html and str(round(lon, 5))[-5:] not in html
    assert not {SEM_PERMISSAO, SEM_POSICAO, FORA_DO_PILOTO} & set(tec)
    # as usinas, uma a uma, pela coordenada do cadastro
    us = {u["id"]: u for u in d["usinas"]}
    assert set(us) == {str(USINA_A), str(USINA_B)} and us[str(USINA_A)]["nome"] == NOME_USINA[USINA_A]
    assert us[str(USINA_A)]["c"] == [round(COORDS["7"][1], 5), round(COORDS["7"][0], 5)]
    # o registro da LGPD antes de a coordenada sair
    assert [a["acao"] for a in _acessos(pontos)] == ["abriu_mapa"]


def test_sem_3d_sem_satelite_e_o_desenho_quando_pedido(cliente, pontos, setor, com_mapa_base):
    """Levi, 11/11/2026: "Pode tirar a opção 3D, não deve ter pois é muito pesada e sem necessidade". `?mapa=desenho`
    volta ao SVG. (O satélite voltou em 12/11/2026, com a chave da Esri: o teste dele é o de baixo.)"""
    _, html = _html(_entrar(cliente, EMAIL[PCM]))
    corpo = html.split("<main", 1)[1]
    assert not re.search(r">\s*3D\s*<|data-3d", corpo)
    js = (Path(__file__).resolve().parent.parent / "nexus" / "static" / "campo-mapa.js").read_text(encoding="utf-8")
    assert "setTerrain" not in js and "fill-extrusion" not in js and "maxPitch: 0" in js
    assert "dragRotate: false" in js and "maxBounds" in js                 # só o Brasil, de cima
    _, html = _html(cliente, query_string={"mapa": "desenho"})
    assert '<svg class="eq-svg' in html and 'id="eq-mapa"' not in html


def test_o_modo_usinas_leva_so_as_usinas(cliente, pontos, setor, risco, com_mapa_base):
    _, html = _html(_entrar(cliente, EMAIL[PCM]), query_string={"ver": "usinas"})
    d = _dados(html)
    assert d["modo"] == "usinas" and d["tecnicos"] == [] and d["percurso"] is None
    assert len(d["usinas"]) == 6 and all(len(u["c"]) == 2 for u in d["usinas"])
    assert {u["onde"] for u in d["usinas"]} == {"Cliente X · PI"}
    assert not [n for n in NOME.values() if n in html] and _acessos(pontos) == []


def test_o_percurso_vai_ao_mapa_com_os_marcos(cliente, pontos, setor, com_mapa_base):
    _receber(pontos, ANDANDO, MANHA)
    pontos.registro.novos()
    _, html = _html(_entrar(cliente, EMAIL[PCM]),
                    query_string={"tecnico": ANDANDO, "de": "2026-11-08T06:00", "ate": "2026-11-08T12:00"})
    d = _dados(html)
    p = d["percurso"]
    assert len(p["linha"]) == 4 and [x["hora"] for x in p["pontos"]] == ["09:00", "10:00", "11:00", "11:59"]
    assert [(m["tipo"], m["texto"]) for m in p["marcos"]] == [
        ("inicio", "Primeira posição, em deslocamento"), ("parado", "Parado fora de usina"),
        ("ultimo", "Última posição, em deslocamento")]
    assert all(len(m["c"]) == 2 for m in p["marcos"]) and len(p["caixa"]) == 4
    assert 'data-eq-zoom="percurso"' in html
    assert [a["acao"] for a in _acessos(pontos)][-1] == "abriu_percurso"


def test_o_clima_vai_ao_mapa_em_coordenadas(cliente, pontos, setor, clima_das_usinas, com_mapa_base):
    _, html = _html(_entrar(cliente, EMAIL[PCM]), query_string={"clima": "1"})
    d = _dados(html)
    av = d["clima"]["avisos"]["features"]
    assert len(av) == 1 and av[0]["properties"]["nivel"] == 3 and av[0]["geometry"]["type"] == "Polygon"
    us = {u["id"]: u for u in d["usinas"]}
    assert us[str(USINA_A)]["nivel"] == "agir" and us[str(USINA_B)]["nivel"] == "sem"
    assert "Vendaval" in us[str(USINA_A)]["motivo"]


def test_a_cor_da_usina_e_o_agora_do_comando_pelo_cos(cliente, pontos, setor, com_mapa_base, monkeypatch):
    """Levi, 12/11/2026: "Quero as cores das usinas de acordo com o tempo real, OS Abertas do setor COS, as regras estão
    em 'Comando > Usinas' pode pegar as cores de lá!". A cor é o "Agora" de Comando > Usinas (`comando.usinas`: a
    fotografia da Ronda COS de cada cliente, na régua do Levi) com o tom de lá; sem a leitura do COS, sem cor."""
    from nexus.comando import usinas as CU
    from nexus.torres.campo import equipe_tela as ET
    monkeypatch.setattr(ET, "_cos_por_usina", lambda b: {"ocs": {USINA_A: [{"os": "18412", "tipo_tarefa": "Religamento",
                        "tipo_falha": "Desligamento de usina", "abertura": "2026-11-08T12:00:00Z"}]},
                        "lidas": {USINA_A, USINA_B}})
    _, html = _html(_entrar(cliente, EMAIL[PCM]))
    us = {u["id"]: u for u in _dados(html)["usinas"]}
    assert us[str(USINA_A)]["agora"] == {"estado": "critico", "rotulo": "Crítico", "tom": "critico",
                                         "motivo": CU.motivo({"tipo_falha": "Desligamento de usina"})}
    assert us[str(USINA_B)]["agora"]["estado"] == "normal" and us[str(USINA_B)]["agora"]["tom"] == "ok"
    monkeypatch.setattr(ET, "_cos_por_usina", lambda b: None)
    _, html = _html(cliente)
    assert all(u["agora"] is None for u in _dados(html)["usinas"])


def test_o_satelite_da_esri_com_a_chave_e_o_botao_sempre_a_vista(app, cliente, pontos, setor, com_mapa_base):
    """Levi, 12/11/2026: "Quero a visão de mapa e satélite", e a escolha dele no mesmo dia: a Esri (ArcGIS), com a chave
    da conta dele em Base > Chaves (NEXUS_ESRI_CHAVE). Sem a chave o botão sumia, e ele perguntou "CADÊ A OPÇÃO
    MAPA/SATÉLITE??": o botão fica sempre à vista e, sem a chave, diz o que falta (o administrador ganha o link)."""
    _, html = _html(_entrar(cliente, EMAIL[PCM]))
    assert _dados(html)["satelite"] is None
    assert 'data-eq-base="satelite"' in html and "data-eq-sem-chave" in html
    falta = html.split('class="eq-sat-falta"', 1)[1].split("</p>", 1)[0]
    assert "chave da Esri" in falta and "Base &gt; Chaves" in falta and "Mapa de equipe: satélite" in falta
    assert "chaves-nexus" not in falta                                    # quem não é administrador não ganha o link
    _, html = _html(_entrar(cliente, EMAIL[ADMIN], admin=True))
    falta = html.split('class="eq-sat-falta"', 1)[1].split("</p>", 1)[0]
    assert 'href="/t/base/chaves-nexus"' in falta                         # o GET leva à aba Nexus das Chaves
    app.config["NEXUS_ESRI_CHAVE"] = "AAPTxy" + "k" * 90
    _, html = _html(cliente)
    sat = _dados(html)["satelite"]
    assert sat["url"].startswith("https://ibasemaps-api.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/tile/")
    assert "{z}/{y}/{x}" in sat["url"] and sat["url"].endswith("token=AAPTxy" + "k" * 90) and "Esri" in sat["credito"]
    assert 'data-eq-base="mapa"' in html and 'data-eq-base="satelite"' in html and "data-eq-sem-chave" not in html


def test_dois_focos_zoom_mais_rapido_e_a_reproducao_do_percurso(cliente, pontos, setor, com_mapa_base):
    """Levi, 12/11/2026: "Quero ter dois focos, foco técnico e focos usina", "Quero o zoom um pouco mais rápido, pelo
    menos o dobro", "aumente um pouco o tamanho do círculo dos técnicos" e "Cliquei em percurso e não aparece a animação
    da referência" (a prévia: a câmera vai ao percurso, a linha com o sentido e o trecho atual andando, e o controle que
    reproduz o dia)."""
    _, html = _html(_entrar(cliente, EMAIL[PCM]))
    assert 'data-eq-foco="tecnico"' in html and 'data-eq-foco="usina"' in html
    js = (Path(__file__).resolve().parent.parent / "nexus" / "static" / "campo-mapa.js").read_text(encoding="utf-8")
    assert "setWheelZoomRate" in js and "zoomTo(mapa.getZoom() + 2" in js
    assert '"circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 10' in js
    assert "perc-setas" in js and "perc-formigas" in js and "line-gradient" in js
    _receber(pontos, ANDANDO, MANHA)
    pontos.registro.novos()
    _, html = _html(cliente, query_string={"tecnico": ANDANDO, "de": "2026-11-08T06:00", "ate": "2026-11-08T12:00"})
    assert 'data-eq-replay' in html and 'data-eq-replay-vel' in html
    p = _dados(html)["percurso"]
    assert [q["t"] for q in p["pontos"]] == sorted(q["t"] for q in p["pontos"]) and isinstance(p["pontos"][0]["t"], int)
    # os campos De e Até lado a lado (Levi: "podem facilmente ficar lado a lado")
    assert 'class="eq-perc-datas"' in html


def test_o_mapa_e_mais_alto():
    """Levi, 12/11/2026: "Pode aumentar a altura do mapa, até para quando for expandir o percurso caber mais para cima!"."""
    css = (Path(__file__).resolve().parent.parent / "nexus" / "static" / "campo.css").read_text(encoding="utf-8")
    assert "--eq-alt:clamp(620px,calc(100vh - 140px),1600px)" in css
    assert ".eq-perc-datas{display:grid;grid-template-columns:1fr 1fr" in css


def test_o_script_do_mapa_so_tem_as_cores_do_nexus():
    """"Quero em estilo Nexus" (Levi, 11/11/2026): o estilo do mapa é montado no navegador a partir dos tokens do
    nexus.css (os dois temas), sem nenhuma cor escrita no script. As contas puras, no node."""
    raiz = Path(__file__).resolve().parent.parent / "nexus" / "static"
    js = (raiz / "campo-mapa.js").read_text(encoding="utf-8")
    sem_comentario = re.sub(r"/\*.*?\*/|//[^\n]*", "", js, flags=re.S)
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(\s*\d", sem_comentario)
    for t in ("--superficie", "--fundo", "--verde", "--tinta", "--info-cheio", "--critico"):
        assert f'"{t}"' in js, t
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("sem node nesta máquina")
    codigo = ("const m=require(process.argv[1]);console.log(JSON.stringify({mix:m.mistura('#000000','#ffffff',0.25),"
              "mask:m.mascara({type:'FeatureCollection',features:[{type:'Feature',geometry:{type:'MultiPolygon',"
              "coordinates:[[[[0,0],[1,0],[1,1],[0,0]]],[[[2,2],[3,2],[3,3],[2,2]]]]}}]})}))")
    r = json.loads(subprocess.run([node, "-e", codigo, str(raiz / "campo-mapa.js")], capture_output=True, text=True,
                                  check=True).stdout)
    assert r["mix"] == "rgb(64, 64, 64)"
    aneis = r["mask"]["geometry"]["coordinates"]
    assert len(aneis) == 3 and aneis[1] == [[0, 0], [1, 0], [1, 1], [0, 0]]       # o mundo e os dois buracos


def test_so_o_brasil_a_mascara_cobre_o_resto_por_inteiro():
    """Levi, 12/11/2026, depois do satélite: "tem como mostrar só Brasil?". A máscara de fora do Brasil era 90% opaca:
    no satélite (o mundo inteiro) e nas bordas do recorte, os vizinhos e o mar apareciam apagados por baixo. Agora ela é
    a cor do fundo, cheia."""
    js = (Path(__file__).resolve().parent.parent / "nexus" / "static" / "campo-mapa.js").read_text(encoding="utf-8")
    assert re.search(r'fora:\s*t\["--fundo"\]\s*,', js), "a máscara de fora do Brasil tem de ser opaca"


def test_sem_o_anel_vermelho_em_volta_da_usina():
    """Levi, 12/11/2026: "TIRE ESSA BORDA ENORME DAS UFVs em vermelho!" (o anel que pulsava em volta da usina crítica e
    da de clima "agir"). A cor do losango continua; a divisa do Brasil segue pulsando."""
    js = (Path(__file__).resolve().parent.parent / "nexus" / "static" / "campo-mapa.js").read_text(encoding="utf-8")
    assert "usinas-pulso" not in js and "pulso:" not in js
    assert "brasil-borda" in js


def test_as_cores_de_cada_foco():
    """Levi, 12/11/2026: "No foco técnico todas as UFVs ficam sem cor exceto desligamento e o resto fica cinza. No modo
    usina os técnicos ficam cinzas e o foco é na usina!". A conta pura (`corNoFoco`, no node): no foco técnico só a
    usina crítica do Agora (a parada) mantém a cor, o resto do Agora vira cinza; o nível do clima, ligado de propósito,
    fica. No foco usina, a cor de sempre. E os técnicos no foco usina são cinza (o script troca a cor do círculo)."""
    raiz = Path(__file__).resolve().parent.parent / "nexus" / "static"
    js = (raiz / "campo-mapa.js").read_text(encoding="utf-8")
    assert re.search(r'"circle-color",\s*u \? P\.t\["--mudo"\]', js), "no foco usina o técnico é cinza"
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("sem node nesta máquina")
    cores = ["a_critico", "a_alerta", "a_ok", "a_neutro", "sem_leitura", "neutra", "agir", "atencao", "sem", "a_semcom"]
    codigo = ("const m=require(process.argv[1]);const c=" + json.dumps(cores) + ";console.log(JSON.stringify({"
              "t:c.map(x=>m.corNoFoco(x,'tecnico')),u:c.map(x=>m.corNoFoco(x,'usina'))}))")
    r = json.loads(subprocess.run([node, "-e", codigo, str(raiz / "campo-mapa.js")], capture_output=True, text=True,
                                  check=True).stdout)
    assert r["t"] == ["a_critico", "cinza", "cinza", "cinza", "cinza", "cinza", "agir", "atencao", "sem", "cinza"]
    # a usina sem comunicação é roxa no mapa (12/11/2026, a cor de Comando > Usinas): o ícone existe e lê o token
    assert 'a_semcom: P.t["--semcom-cheio"]' in js and '"--semcom"' in js
    assert r["u"] == cores


def test_a_escala_com_a_borda_inteira_e_os_creditos_recolhidos():
    """Levi, 13/11/2026 (pela sessão Nexus Field): "Esse contador de 500 km aí do mapa [...] tá sem a borda de cima. Isso
    deixou muito estranho" (a escala do MapLibre vem por padrão com a borda só dos lados e embaixo) e "tem exclamação que
    fica estendida, mostrando de onde está vindo os dados [...] Deixa essa exclamação sempre recolhida" (os créditos do
    mapa, que o MapLibre abre no começo e só recolhe no primeiro arrasto)."""
    raiz = Path(__file__).resolve().parent.parent / "nexus" / "static"
    css = (raiz / "campo.css").read_text(encoding="utf-8")
    escala = re.search(r"\.eq-ml \.maplibregl-ctrl-scale\{([^}]*)\}", css).group(1)
    assert "border:1px solid var(--linha-forte)" in escala and "border-top" not in escala
    js = (raiz / "campo-mapa.js").read_text(encoding="utf-8")
    assert "function recolherCreditos" in js and 'classList.remove("maplibregl-compact-show")' in js
    assert 'removeAttribute("open")' in js and 'mapa.on("load", recolherCreditos)' in js


def test_a_usina_arredondada_e_o_roxo_forte_da_sem_comunicacao():
    """Levi, 13/11/2026: "No foco usina, eu quero as formas arredondadas [...] E lá embaixo também, no rodapé, fica com o
    símbolo da usina arredondada. E também eu quero, quando a usina estiver sem comunicação, ficar um roxo mais forte".
    O losango tem os cantos arredondados (o ícone do mapa e o da legenda) e a sem comunicação pinta com o roxo cheio
    (`--semcom-cheio`, nos dois temas), não com o roxo de texto das etiquetas."""
    raiz = Path(__file__).resolve().parent.parent / "nexus" / "static"
    js = (raiz / "campo-mapa.js").read_text(encoding="utf-8")
    los = js[js.index("function losango("):js.index("function corDaUsina(")]
    assert "arcTo" in los and 'lineJoin = "round"' in los
    assert 'a_semcom: P.t["--semcom-cheio"]' in js and '"--semcom-cheio"' in js
    nexus = (raiz / "nexus.css").read_text(encoding="utf-8")
    assert nexus.count("--semcom-cheio:") == 2
    css = (raiz / "campo.css").read_text(encoding="utf-8")
    leg = re.search(r"(?m)^\.eq-leg-usina\{([^}]*)\}", css).group(1)
    assert "border-radius:3px" in leg and "rotate(45deg)" in leg

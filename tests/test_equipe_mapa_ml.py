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
    """Levi, 11/11/2026: "Pode tirar a opção 3D, não deve ter pois é muito pesada e sem necessidade". O satélite também
    fica de fora: o da prévia é de demonstração e o de produção pede licença (o guia). `?mapa=desenho` volta ao SVG."""
    _, html = _html(_entrar(cliente, EMAIL[PCM]))
    corpo = html.split("<main", 1)[1]
    assert not re.search(r">\s*3D\s*<|data-3d|Satélite|satelite", corpo)
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


def test_a_usina_com_ocorrencia_aberta_leva_a_cor_da_pior(cliente, pontos, setor, com_mapa_base, monkeypatch):
    """O guia: a cor da usina é o dado; neutra, com a cor da severidade quando há ocorrência aberta (as ocorrências da
    Usinas 360°, a mesma etiqueta da Visão geral: muito alta = crítico, alta = alerta)."""
    import nexus.torres.campo as TC
    monkeypatch.setattr(TC, "_ocorrencias_abertas", lambda: {USINA_A: {"n": 2, "pior": "muito_alta"}})
    _, html = _html(_entrar(cliente, EMAIL[PCM]))
    us = {u["id"]: u for u in _dados(html)["usinas"]}
    assert us[str(USINA_A)]["oc"] == {"n": 2, "pior": "muito_alta", "tom": "critico"} and us[str(USINA_B)]["oc"] is None


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

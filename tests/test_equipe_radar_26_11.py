"""O radar de chuva do Mapa de equipe, servido pelo próprio Nexus (26/11/2026).

O Levi aprovou o protótipo com a chuva do radar ("azul mais chuva, quando tiver fortalecendo, ficar uma região mais
vermelha"): a RainViewer (grátis, sem chave) dá os quadros das últimas 2 h. O navegador NUNCA pede bloco a ela: o Nexus
busca e repassa (o guia do mapa: nenhum terceiro vê a região que o COS está olhando). Só quem vê o mapa pede; o caminho do
bloco é conferido (o Nexus não vira um repassador aberto); a lista e os blocos ficam numa cópia em memória.
Nada vai à rede: a busca é dublada."""
import pytest
from test_equipe_tela import EMAIL, OUTRO, PCM, _entrar, banco, pontos, relogio, setor  # noqa: F401

from nexus.torres.campo import equipe_tela as ET

LISTA = {"version": "2.0", "generated": 1795715422, "host": "https://tilecache.rainviewer.com",
         "radar": {"past": [{"time": 1795708200, "path": "/v2/radar/d0106049b096"},
                            {"time": 1795708800, "path": "/v2/radar/f7a50ce4a066"}], "nowcast": []},
         "satellite": {"infrared": []}}
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 40
BLOCO = "/t/campo/equipe/radar/v2/radar/d0106049b096/256/6/22/36/8/1_1.png"


class Busca:
    def __init__(self):
        self.pedidos, self.fora = [], False

    def __call__(self, url):
        self.pedidos.append(url)
        if self.fora:
            raise OSError("rede fora (teste)")
        return (200, LISTA) if url.endswith(".json") else (200, PNG)


@pytest.fixture
def busca(monkeypatch):
    b = Busca()
    monkeypatch.setattr(ET, "_buscar_radar", b)
    ET._RADAR.update(lista=None, lista_em=0.0)
    ET._RADAR["blocos"].clear()
    yield b
    ET._RADAR.update(lista=None, lista_em=0.0)
    ET._RADAR["blocos"].clear()


def test_a_lista_dos_quadros_so_para_quem_ve_o_mapa(cliente, pontos, setor, busca):  # noqa: F811
    _entrar(cliente, OUTRO)
    assert cliente.get("/t/campo/equipe/radar.json").status_code == 403 and busca.pedidos == []
    _entrar(cliente, EMAIL[PCM])
    r = cliente.get("/t/campo/equipe/radar.json")
    assert r.status_code == 200
    j = r.get_json()
    # só os quadros (a hora e o caminho, que o navegador pede ao NOSSO endereço), sem o servidor de lá
    assert j == {"quadros": [{"time": 1795708200, "path": "/v2/radar/d0106049b096"},
                             {"time": 1795708800, "path": "/v2/radar/f7a50ce4a066"}]}
    assert busca.pedidos == ["https://api.rainviewer.com/public/weather-maps.json"]
    cliente.get("/t/campo/equipe/radar.json")
    assert len(busca.pedidos) == 1                                   # a cópia em memória


def test_o_bloco_vem_pelo_nexus_e_o_caminho_e_conferido(cliente, pontos, setor, busca):  # noqa: F811
    _entrar(cliente, EMAIL[PCM])
    r = cliente.get(BLOCO)
    assert r.status_code == 200 and r.mimetype == "image/png" and r.data == PNG
    assert busca.pedidos == ["https://tilecache.rainviewer.com/v2/radar/d0106049b096/256/6/22/36/8/1_1.png"]
    assert "private" in r.headers["Cache-Control"]
    cliente.get(BLOCO)
    assert len(busca.pedidos) == 1                                   # o mesmo bloco não vai de novo à RainViewer
    # o que não é um bloco do radar não é repassado
    for ruim in ("/t/campo/equipe/radar/v2/radar/d0106049b096/256/6/22/36/8/1_1.png/../../x",
                 "/t/campo/equipe/radar/v2/satellite/abc123/256/6/22/36/0/0_0.png",
                 "/t/campo/equipe/radar/v2/radar/zz/256/6/22/36/8/1_1.png", "/t/campo/equipe/radar/qualquer.png"):
        assert cliente.get(ruim).status_code == 404, ruim
    assert len(busca.pedidos) == 1
    _entrar(cliente, OUTRO)
    assert cliente.get(BLOCO).status_code == 403


def test_a_fonte_fora_responde_503(cliente, pontos, setor, busca):  # noqa: F811
    _entrar(cliente, EMAIL[PCM])
    busca.fora = True
    assert cliente.get("/t/campo/equipe/radar.json").status_code == 503
    assert cliente.get(BLOCO).status_code == 503

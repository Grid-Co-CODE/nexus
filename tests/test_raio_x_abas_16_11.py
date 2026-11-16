"""O Raio-X em abas, com cara de TV (16/11/2026, Levi: "vamos elegantizar a parte de raio-x [...] como a gente separa por
categoria, deixou várias abinhas ali dentro da página [...] deixa bem visual [...] bem cara de televisão").

O que estes testes seguram: o parecer do alto só com os sinais que a página já tinha (threads todas ocupadas, pedidos
presos em 24 h, o OS Creator no teto, a máquina trocando com o swap, o relatório de memória parado), cada um com a palavra
e o tom; as cinco abas pelo ?aba= (a página traz todas e mostra uma; a aba desconhecida vira a Agora); e o JS das abas,
do "Atualizar sozinho" e da tela cheia na página."""
import re

import pytest

from nexus.casca import raio_x as R


def _cpu(**mudar):
    c = {"pct": 37, "nucleos": 4, "carga": [0.5, 0.4, 0.3], "maquina": None}
    c.update(mudar)
    return c


@pytest.fixture
def sem_espera(monkeypatch):
    monkeypatch.setattr(R, "_processador", lambda janela_s=1.0: _cpu())


def test_parecer_tudo_respondendo():
    p = R.parecer([], 16, {"teto": 6, "em_uso": 2, "recusados": 0}, {"trocando_mb_s": "0"},
                  {"classe": "ok", "rotulo": "Nenhum pedido preso em 24 h"}, (("Nexus", None), ("worker", {"velho": False})))
    assert p == {"tom": "ok", "titulo": "Tudo respondendo", "itens": []}


def test_parecer_com_os_sinais_de_cada_tom():
    pedidos = [{}] * 8
    p = R.parecer(pedidos, 8, {"teto": 6, "em_uso": 6, "recusados": 3}, {"trocando_mb_s": "3,0"},
                  {"classe": "alerta", "rotulo": "2 pedidos presos nas últimas 24 h"},
                  (("Nexus", {"velho": False}), ("worker", {"velho": True, "idade_min": 42}),
                   ("web", {"atrasado": True, "anterior": {"velho": True}})))
    assert p["tom"] == "critico" and p["titulo"] == "Gargalo agora"
    assert p["itens"] == [
        ("critico", "Todas as 8 threads do Nexus ocupadas: a fila espera"),
        ("alerta", "2 pedidos presos nas últimas 24 h"),
        ("alerta", "O OS Creator está no teto: 6 de 6 threads em uso"),
        ("alerta", "A máquina está trocando com o swap agora (3,0 MB/s)"),
        ("alerta", "O worker não anota a memória há 42 min")]       # o web atrasado não vira "parado" (não se sabe)
    # só alerta: o tom do alto é o alerta
    so = R.parecer([], 8, None, None, {"classe": "critico", "rotulo": "Pedido preso agora"}, ())
    assert so["tom"] == "critico" and so["itens"] == [("critico", "Pedido preso agora")]
    assert R.parecer([], 0, None, {"trocando_mb_s": "1,5"}, None, ())["tom"] == "alerta"


def test_as_abas_pelo_endereco(logado, sem_espera):
    h = logado.get("/t/base/raio-x").get_data(as_text=True)
    assert [a for a in re.findall(r'data-rx-aba="([a-z]+)"', h)] == ["agora", "memoria", "pedidos", "uso", "canto"]
    abertos = re.findall(r'data-rx-painel="([a-z]+)"(?! hidden)', h)
    assert abertos == ["agora"] and 'data-rx-aba="agora" aria-current="page"' in h
    assert "rx-parecer rx-parecer--" in h and "raio-x.js" in h and "data-rx-cheia" in h and "data-rx-sozinho" in h
    h = logado.get("/t/base/raio-x?aba=memoria").get_data(as_text=True)
    assert re.findall(r'data-rx-painel="([a-z]+)"(?! hidden)', h) == ["memoria"]
    assert 'href="/t/base/raio-x?aba=memoria" data-rx-ler' in h               # o "Ler de novo" fica na mesma aba
    h = logado.get("/t/base/raio-x?aba=nao-existe").get_data(as_text=True)
    assert re.findall(r'data-rx-painel="([a-z]+)"(?! hidden)', h) == ["agora"]


def test_o_anel_e_a_carga_na_aba_agora(logado, sem_espera):
    h = logado.get("/t/base/raio-x").get_data(as_text=True)
    agora = h[h.index('data-rx-painel="agora"'):h.index('data-rx-painel="memoria"')]
    assert 'stroke-dasharray="37 100"' in agora                                # o processador do Nexus: 37%
    assert ">0,50<" in agora and "width:12%" in agora                          # 0,50 de carga em 4 núcleos (12,5%)


def test_o_js_das_abas_existe_e_nao_escreve_endereco_da_raiz():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "nexus" / "static" / "raio-x.js").read_text(encoding="utf-8")
    assert "data-rx-aba" in js and "nexus.raiox.sozinho" in js and "requestFullscreen" in js
    assert not re.search(r"""["'`]/(t|os|static)/""", js)                   # o endereço sai do location (prefixo)

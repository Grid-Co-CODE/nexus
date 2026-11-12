"""A aba Transferir do Almoxarifado (`/t/pcm/pecas/transferir`; 12/11/2026): a casca do formulário (as listas e o que grava vêm
da ponte do login do Fracttal), o "!" e as Últimas transferências do livro. Dado de mentira."""
import re

from test_campo_visao import banco  # noqa: F401  (banco é fixture)
from test_pcm_inventario_curadoria import _pessoa_ms
from test_pcm_inventario_transferencia_ponte import BASE, PEDIDO, _pcm
from test_pcm_inventario_transferencia_regra import _falso, tr  # noqa: F401  (tr é fixture)
from test_pcm_publicar import _no_setor

from nexus.cadastro import setor_ids as SID

TELA = "/t/pcm/pecas/transferir"


def test_a_tela_do_pcm(tr, monkeypatch):
    _no_setor(monkeypatch, SID.PCM)
    html = _pessoa_ms(tr).get(TELA).get_data(as_text=True)
    for fim in ("almoxarifados", "pecas", "conferir"):
        assert f'data-tr-{"almox" if fim == "almoxarifados" else fim}="{BASE}/{fim}"' in html
    assert f'data-tr-transferir="{BASE}"' in html and "pcm-transferir.js" in html
    # todo campo com o rótulo
    for campo in re.findall(r'<(?:select|input)[^>]* id="([^"]+)"', html):
        assert f'for="{campo}"' in html, campo
    # o "!": para que serve, a peça instalada e a guardada, o empréstimo entre clientes, o vínculo com 0 e 0
    explica = html.split("gc-explica-caixa")[1].split("</section>")[0]
    assert "instalada" in explica and "empréstimo" in explica and "mínimo e máximo 0" in explica
    assert "Últimas transferências" in html and "Nenhuma transferência pelo Nexus ainda." in html
    nav = html.split('class="alm-abas"')[1].split("</nav>")[0]
    assert re.search(r'aria-selected="true"[^>]*href="/t/pcm/pecas/transferir"', nav)
    # a aba também está na tela principal do Almoxarifado
    assert 'href="/t/pcm/pecas/transferir">Transferir</a>' in _pessoa_ms(tr).get("/t/pcm/pecas").get_data(as_text=True)


def test_a_senha_de_administrador_nao_transfere(tr, logado):
    html = logado.get(TELA).get_data(as_text=True)
    assert "entre no Nexus pelo Fracttal" in html and "data-tr-form" not in html and "pcm-transferir.js" not in html
    assert "Últimas transferências" in html


def test_depois_de_transferir_o_aviso_e_o_historico(tr, monkeypatch):
    c = _pcm(tr, monkeypatch, _falso())
    assert c.post(BASE, json=dict(PEDIDO, item="2", qtd="1")).status_code == 200
    html = c.get(TELA).get_data(as_text=True)
    assert "cn-certo" in html and "Transferência NX-TR-" in html
    tabela = html.split("Últimas transferências")[1]
    assert "Almoxarifado Usina Um → Almoxarifado Usina Dois" in tabela and "criado (0 e 0)" in tabela
    assert 'inv-selo--ok">Feita' in tabela and "2,5 → 1,5" in tabela and "0 → 1" in tabela
    assert "Quem" in tabela                                                   # o PCM vê quem transferiu
    _no_setor(monkeypatch, SID.PCM)
    assert c.get(TELA).get_data(as_text=True).count("cn-certo") == 0          # o aviso aparece uma vez

"""O catálogo de ativos vencido não segura o clique (24/10/2026, nexus/torres/oscreator/os_creator/api.py).

Caso real, 23/10/2026 às 10:44: o catálogo de ~22 mil ativos passou das 24 h e o primeiro a precisar dele baixou tudo de
novo DENTRO do pedido (~110 pedidos ao Fracttal, 6 de cada vez): um "Criar OS" da Performance ficou 3 min 51 s em
`get_assets`, e o Histórico 1 min 52 s esperando o mesmo download (o filtro de cliente e usina). Levi, 24/10: "deixe um
botão de atualizar ativos e quando atualizar vai atualizar a lista de todos, não só daquela pessoa".

O que estes testes seguram: vencido, o catálogo de ontem volta na hora e o novo é baixado por trás, uma vez só, com a
sessão de quem pediu; o próximo pedido já recebe o novo; o download que falha deixa o de ontem e só tenta de novo depois
de ASSETS_ESPERA_TENTATIVA; quem precisa do catálogo em dia (`em_dia=True`: resolver o ativo da OS na aprovação) espera,
como antes; sem catálogo nenhum, espera o download; e o botão "Atualizar" da tela de Ativos baixa na hora e vale para
todos (o catálogo é um só).

Desde 31/10/2026 o catálogo é o central (`ativos_central`, etapa 2 do canto central): os cenários são os mesmos, e o que o
download faz agora é trocar o catálogo da memória (e a cópia em disco), em vez de gravar o `assets_cache.json`."""
import contextvars
import sys
import threading
import time

import pytest

from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone (o mesmo módulo que as rotas do os_web usam)
import ativos_central  # noqa: E402

VELHO = [{"id": 1, "code": "VELHO", "usina": "", "cliente": "", "tipo": "", "description": ""}]
NOVO = [{"id": 2, "code": "NOVO", "usina": "", "cliente": "", "tipo": "", "description": ""}]
QUEM = contextvars.ContextVar("quem_pediu", default=None)


@pytest.fixture
def catalogo(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "_ASSETS_RENOVA", {"tentou": 0.0})
    ativos_central.reiniciar(pasta=str(tmp_path / "oscreator"))

    def gravar(ativos, ts=None):
        """O catálogo de que o processo parte (a cópia de ontem, ou a de agora): como se tivesse subido com ele."""
        ativos_central.reiniciar(pasta=str(tmp_path / "oscreator"))
        assert ativos_central.trocar(ativos, "rpc", lido_em=ts or time.time())
    yield gravar
    ativos_central.reiniciar()


class _Fracttal:
    """O download do catálogo, lento e contado, com a sessão (o contexto) de quem o fez."""

    def __init__(self, monkeypatch, demora=0.4, falhar=False):
        self.vezes, self.quem, self.demora, self.falhar = 0, [], demora, falhar
        monkeypatch.setattr(api, "get_assets", self)

    def __call__(self):
        self.vezes += 1
        self.quem.append(QUEM.get())
        time.sleep(self.demora)
        if self.falhar:
            raise api.FracttalError("HTTP 429")
        return [dict(a) for a in NOVO]


def _esperar_o_download(prazo=5):
    fim = time.monotonic() + prazo
    while api._ASSETS_RECARGA.locked() or any(t.name == "os-catalogo-por-tras" for t in threading.enumerate()):
        assert time.monotonic() < fim, "o download por trás não terminou"
        time.sleep(0.02)


def test_vencido_volta_o_de_ontem_na_hora_e_o_novo_vem_por_tras(catalogo, monkeypatch):
    catalogo(VELHO, ts=time.time() - api.ASSETS_TTL - 10)
    fr = _Fracttal(monkeypatch)
    QUEM.set("sessao-da-pessoa")
    t0 = time.monotonic()
    saidas = [api.load_assets_cached() for _ in range(3)]            # três telas no mesmo minuto
    assert time.monotonic() - t0 < fr.demora, "o pedido esperou o download"
    assert all(s[0]["code"] == "VELHO" for s in saidas)
    _esperar_o_download()
    assert fr.vezes == 1 and fr.quem == ["sessao-da-pessoa"]           # um download, com a sessão de quem pediu
    assert api.load_assets_cached()[0]["code"] == "NOVO"
    assert fr.vezes == 1


def test_o_download_que_falha_deixa_o_de_ontem_e_espera_para_tentar_de_novo(catalogo, monkeypatch):
    catalogo(VELHO, ts=time.time() - api.ASSETS_TTL - 10)
    fr = _Fracttal(monkeypatch, demora=0.05, falhar=True)
    assert api.load_assets_cached()[0]["code"] == "VELHO"
    _esperar_o_download()
    assert api.load_assets_cached()[0]["code"] == "VELHO" and fr.vezes == 1      # dentro da espera: não tenta
    _esperar_o_download()
    assert fr.vezes == 1
    api._ASSETS_RENOVA["tentou"] = time.time() - api.ASSETS_ESPERA_TENTATIVA - 1
    fr.falhar = False
    api.load_assets_cached()
    _esperar_o_download()
    assert fr.vezes == 2 and api.load_assets_cached()[0]["code"] == "NOVO"


def test_em_dia_espera_o_novo(catalogo, monkeypatch):
    catalogo(VELHO, ts=time.time() - api.ASSETS_TTL - 10)
    fr = _Fracttal(monkeypatch, demora=0.05)
    assert api.load_assets_cached(em_dia=True)[0]["code"] == "NOVO" and fr.vezes == 1


def test_uma_recarga_por_vez_para_quem_precisa_em_dia(catalogo, monkeypatch):
    catalogo(VELHO, ts=time.time() - api.ASSETS_TTL - 10)
    fr = _Fracttal(monkeypatch, demora=0.3)
    saidas = []
    ts = [threading.Thread(target=lambda: saidas.append(api.load_assets_cached(em_dia=True))) for _ in range(3)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert fr.vezes == 1 and all(s[0]["code"] == "NOVO" for s in saidas)


def test_sem_catalogo_nenhum_espera_o_download(catalogo, monkeypatch):
    fr = _Fracttal(monkeypatch, demora=0.05)
    assert api.load_assets_cached()[0]["code"] == "NOVO" and fr.vezes == 1


def test_em_dia_nao_baixa(catalogo, monkeypatch):
    catalogo(VELHO)
    fr = _Fracttal(monkeypatch, demora=0.05)
    assert api.load_assets_cached()[0]["code"] == "VELHO" and api.load_assets_cached(em_dia=True)[0]["code"] == "VELHO"
    assert fr.vezes == 0 and not api._ASSETS_RECARGA.locked()


def test_a_aprovacao_resolve_o_ativo_com_o_catalogo_em_dia(catalogo, monkeypatch):
    from os_web import rotas_solic
    catalogo(VELHO, ts=time.time() - api.ASSETS_TTL - 10)
    _Fracttal(monkeypatch, demora=0.05)
    assert rotas_solic._catalogo_para_aprovar()[0]["code"] == "NOVO"

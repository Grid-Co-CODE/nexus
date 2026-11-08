"""O leitor do GitHub do PCM (`nexus/pcm/fonte.py`) não faz uma tela esperar o download de outra.

Ronda de dados do PCM (27/10/2026): havia UMA trava para todos os arquivos, pega antes de olhar a cópia em memória. Um
download lento do gestao_pcm.json (14,9 MB, até 30 s) segurava a leitura do banco_dados.json, dos relatórios e da
justificativa do App, mesmo com a cópia deles válida. Agora a trava é por arquivo, e quem já tem cópia não espera o
download que outro pedido já está fazendo.
"""
import threading
import time

import pytest

from nexus.pcm import fonte

URL_A = "https://exemplo.invalido/gestao_pcm.json"
URL_B = "https://exemplo.invalido/banco_dados.json"


@pytest.fixture
def leitor(app, monkeypatch):
    """Os dois arquivos apontados para endereços falsos e um `_baixar` que segura o A até o teste soltar."""
    app.config["NEXUS_PCM_GESTAO_FONTE"] = URL_A
    app.config["NEXUS_PCM_FONTE"] = URL_B
    solta, entrou, baixados = threading.Event(), threading.Event(), []

    def baixar(url, validar, etag=None):
        baixados.append(url)
        if url == URL_A:
            entrou.set()
            assert solta.wait(5), "o teste não soltou o download"
            return {"tarefas": [{"v": len(baixados)}]}, None
        return {"semanas": [{"week": "2026-W44", "rows": [{"v": len(baixados)}]}]}, None

    monkeypatch.setattr(fonte, "_baixar", baixar)
    for u in (URL_A, URL_B):
        fonte._cache.pop(u, None)
    yield app, solta, entrou, baixados
    solta.set()
    for u in (URL_A, URL_B):
        fonte._cache.pop(u, None)


def _em_fundo(app, ler):
    out = {}

    def corre():
        with app.app_context():
            out["leitura"] = ler(app.config)
    t = threading.Thread(target=corre, daemon=True)
    t.start()
    return t, out


def test_o_download_lento_de_um_arquivo_nao_segura_a_leitura_de_outro(leitor):
    app, solta, entrou, _ = leitor
    with app.app_context():
        fonte.ler(app.config)                                  # o B com cópia válida
    t, _ = _em_fundo(app, fonte.ler_gestao)                   # o A preso no download
    assert entrou.wait(2)
    with app.app_context():
        t0 = time.monotonic()
        b = fonte.ler(app.config)
        assert time.monotonic() - t0 < 1 and b.dados and not b.erro
    solta.set()
    t.join(5)


def test_quem_ja_tem_copia_nao_espera_o_download_do_mesmo_arquivo(leitor, monkeypatch):
    app, solta, entrou, baixados = leitor
    solta.set()
    with app.app_context():
        antes = fonte.ler_gestao(app.config)                   # a 1ª cópia do A
    solta.clear()
    entrou.clear()
    monkeypatch.setattr(fonte, "TTL_S", 0)                     # a cópia venceu: o próximo pedido rebaixa
    t, _ = _em_fundo(app, fonte.ler_gestao)
    assert entrou.wait(2)
    with app.app_context():
        t0 = time.monotonic()
        durante = fonte.ler_gestao(app.config)
        assert time.monotonic() - t0 < 1
    assert durante.dados is antes.dados and not durante.erro and not durante.velha
    assert baixados.count(URL_A) == 2                          # o segundo pedido não baixou outra vez
    solta.set()
    t.join(5)


def test_sem_copia_o_segundo_pedido_espera_o_primeiro_e_nao_baixa_de_novo(leitor):
    app, solta, entrou, baixados = leitor
    t1, o1 = _em_fundo(app, fonte.ler_gestao)
    assert entrou.wait(2)
    t2, o2 = _em_fundo(app, fonte.ler_gestao)
    time.sleep(0.2)
    solta.set()
    t1.join(5)
    t2.join(5)
    assert baixados.count(URL_A) == 1
    assert o1["leitura"].dados is o2["leitura"].dados and o2["leitura"].dados


def test_o_304_do_github_renova_a_copia_em_memoria(app, monkeypatch):
    """Auditoria ponytail de 08/11/2026: no 304 a cópia nova só era guardada se o mapa de clientes tivesse mudado, então o
    relógio da cópia ficava velho e TODA leitura seguinte perguntava ao GitHub de novo (6 pedidos onde bastavam 2)."""
    app.config["NEXUS_PCM_FONTE"] = URL_B
    fonte._cache.pop(URL_B, None)
    baixados = []

    def baixar(url, validar, etag=None):
        baixados.append(etag)
        if etag is None:
            return {"semanas": []}, "e1"
        return None, etag                                  # 304: o arquivo não mudou

    monkeypatch.setattr(fonte, "_baixar", baixar)
    monkeypatch.setattr(fonte, "TTL_S", 0.3)
    try:
        with app.app_context():
            fonte.ler(app.config)
            time.sleep(0.4)                                # a cópia venceu
            for _ in range(5):
                assert fonte.ler(app.config).dados is not None
        assert len(baixados) == 2, baixados                # a 1ª baixa; a 2ª só pergunta e renova; as outras usam a cópia
    finally:
        fonte._cache.pop(URL_B, None)

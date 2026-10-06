"""Clima e risco: o cache de cada fonte (padrão de `publicacao.py` da operação em tempo real): TTL, janela de 60 s depois de
falha, uma busca por vez, última leitura boa servida com o erro e a hora, e nenhuma rede nos testes sem sessão injetada."""
import json
import threading

import pytest
import requests

from nexus.performance.clima import fontes
from nexus.performance.clima import leitura as L

from clima_cog import Resposta, SessaoArquivos, montar_cog


class Relogio:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t

    def avanca(self, s):
        self.t += s


@pytest.fixture
def relogio():
    r = Relogio()
    L.usar_relogio(r)
    L.limpar_cache()
    yield r
    L.usar_relogio(None)
    L.usar_sessao(None)
    L.limpar_cache()


def cache(relogio, ttl=100):
    return L.Cache(ttl, relogio=relogio)


class Busca:
    """Uma busca que conta quantas vezes foi chamada e pode falhar."""

    def __init__(self, resultado="dado", falha=None):
        self.n, self.resultado, self.falha = 0, resultado, falha

    def __call__(self):
        self.n += 1
        if self.falha:
            raise self.falha
        return self.resultado


# ── o cache ──────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_le_uma_vez_e_guarda_pelo_ttl(relogio):
    c, busca = cache(relogio), Busca()
    a = c.ler(busca)
    assert (a.dados, a.erro, a.velha, a.lido_em) == ("dado", None, False, relogio.t)
    relogio.avanca(99)
    assert c.ler(busca) is a and busca.n == 1
    relogio.avanca(2)
    c.ler(busca)
    assert busca.n == 2


def test_ttl_de_cada_fonte():
    assert (L.TTL_AVISOS_S, L.TTL_FOCOS_S, L.TTL_RISCO_S) == (30 * 60, 10 * 60, 6 * 3600)
    assert L.FALHA_TTL_S == 60


def test_falha_serve_a_ultima_boa_dizendo_o_erro_e_nunca_como_fresca(relogio):
    c = cache(relogio)
    boa = c.ler(Busca("ontem"))
    relogio.avanca(150)                                      # venceu
    r = c.ler(Busca(falha=requests.ConnectionError("sem rota")))
    assert r.dados == "ontem" and r.velha is True and r.erro == "sem conexão com o servidor"
    assert r.lido_em == boa.lido_em                          # a hora é a da leitura boa, não a da tentativa


def test_dentro_de_60_s_da_falha_nao_insiste_e_depois_tenta_de_novo(relogio):
    c = cache(relogio)
    c.ler(Busca("boa"))
    relogio.avanca(150)
    fora = Busca(falha=requests.Timeout("lento"))
    assert c.ler(fora).erro == "tempo esgotado" and fora.n == 1
    relogio.avanca(59)
    r = c.ler(fora)
    assert fora.n == 1 and r.velha and r.dados == "boa" and r.erro == "tempo esgotado"
    relogio.avanca(2)                                        # 61 s depois
    c.ler(fora)
    assert fora.n == 2


def test_voltou_a_funcionar_limpa_o_erro(relogio):
    c = cache(relogio)
    c.ler(Busca("boa"))
    relogio.avanca(150)
    c.ler(Busca(falha=requests.ConnectionError()))
    relogio.avanca(61)
    r = c.ler(Busca("nova"))
    assert (r.dados, r.erro, r.velha) == ("nova", None, False)
    assert r.lido_em == relogio.t


def test_falha_sem_nenhuma_boa_diz_o_erro_dentro_da_janela(relogio):
    c, fora = cache(relogio), Busca(falha=requests.ConnectionError())
    r1 = c.ler(fora)
    assert (r1.dados, r1.lido_em, r1.velha) == (None, None, False) and r1.erro
    r2 = c.ler(fora)
    assert fora.n == 1 and r2.dados is None and r2.erro == r1.erro


def test_o_erro_vira_texto_curto_para_a_tela(relogio):
    resposta = requests.Response()
    resposta.status_code = 503
    casos = [(requests.ConnectionError("HTTPSConnectionPool(host='x', port=443): Max retries exceeded with url ..."), "sem conexão com o servidor"),
             (requests.Timeout("x"), "tempo esgotado"),
             (requests.HTTPError("503 Server Error: ... for url: https://x/y?z", response=resposta), "HTTP 503"),
             (fontes.FonteErro("a resposta do INMET não é JSON"), "a resposta do INMET não é JSON"),
             (ValueError("quebrou"), "ValueError: quebrou")]
    for exc, esperado in casos:
        L.limpar_cache()
        c = cache(relogio)
        assert c.ler(Busca(falha=exc)).erro == esperado


def test_chave_diferente_nao_serve_a_leitura_de_outra(relogio):
    c, busca = cache(relogio), Busca()
    c.ler(busca, chave="a")
    c.ler(busca, chave="a")
    assert busca.n == 1
    c.ler(busca, chave="b")
    assert busca.n == 2
    relogio.avanca(150)
    r = c.ler(Busca(falha=requests.ConnectionError()), chave="c")        # falha com a chave nova: a velha não vale para ela
    assert r.dados is None and r.erro


class _Parada:
    """Busca que fica presa até o teste liberar (Event, sem dormir)."""

    def __init__(self, resultado="dado"):
        self.comecou, self.liberar, self.n, self.resultado = threading.Event(), threading.Event(), 0, resultado

    def __call__(self):
        self.n += 1
        self.comecou.set()
        assert self.liberar.wait(10)
        return self.resultado


def test_uma_busca_por_vez_quem_chega_no_meio_recebe_a_ultima_boa_sem_esperar(relogio):
    c = cache(relogio)
    c.ler(Busca("boa"))
    relogio.avanca(150)
    presa, saida = _Parada("nova"), []
    t = threading.Thread(target=lambda: saida.append(c.ler(presa)))
    t.start()
    assert presa.comecou.wait(10)
    try:
        outra = c.ler(Busca("nao devia ser chamada"))
        assert outra.dados == "boa" and outra.velha is False and outra.erro is None
    finally:
        presa.liberar.set()
        t.join(10)
    assert saida[0].dados == "nova" and presa.n == 1


def test_uma_busca_por_vez_sem_nenhuma_boa_volta_com_lendo(relogio):
    c = cache(relogio)
    presa, saida = _Parada(), []
    t = threading.Thread(target=lambda: saida.append(c.ler(presa)))
    t.start()
    assert presa.comecou.wait(10)
    try:
        outra = c.ler(Busca("nao devia ser chamada"))
        assert outra.dados is None and outra.erro == L.LENDO and outra.velha is False
    finally:
        presa.liberar.set()
        t.join(10)
    assert saida[0].dados == "dado"


def test_a_trava_de_busca_solta_mesmo_quando_a_busca_falha(relogio):
    c = cache(relogio)
    c.ler(Busca(falha=ValueError("x")))
    relogio.avanca(61)
    assert c.ler(Busca("ok")).dados == "ok"


# ── as três fontes, com o cache e sem rede ──────────────────────────────────────────────────────────────────────────

URLS = {"NEXUS_CLIMA_INMET_URL": "https://inmet.exemplo.test/ativos",
        "NEXUS_CLIMA_FOCOS_URL": "https://inpe.exemplo.test/focos/",
        "NEXUS_CLIMA_RISCO_URL": "https://inpe.exemplo.test/risco/RF.PREV.T{d}.tif"}


def config(**extra):
    return {**URLS, **extra}


def inmet(n=1):
    quadrado = {"type": "Polygon", "coordinates": [[[-41, -5], [-39, -5], [-39, -3], [-41, -3], [-41, -5]]]}
    avisos = [{"id": i, "descricao": "Tempestade", "severidade": "Perigo", "inicio": "2026-10-06 09:00", "fim": "2026-10-06 23:00",
               "poligono": json.dumps(quadrado)} for i in range(n)]
    return json.dumps({"hoje": avisos, "futuro": []}).encode()


def test_sem_sessao_nos_testes_nao_vai_a_rede(monkeypatch, relogio):
    def nao(*a, **k):
        raise AssertionError("foi à rede")
    monkeypatch.setattr(fontes, "sessao_padrao", nao)
    monkeypatch.setattr(requests.Session, "get", nao)
    for l in (L.avisos({"TESTING": True}), L.focos({"TESTING": True}), L.risco({"TESTING": True}, [("a", -10, -40)])):
        assert l.dados is None and l.erro == "sem fonte nos testes" and l.lido_em is None


def test_avisos_com_sessao_injetada(relogio):
    s = SessaoArquivos({URLS["NEXUS_CLIMA_INMET_URL"]: inmet(2)})
    l = L.avisos(config(TESTING=True), s)
    assert l.erro is None and len(l.dados["avisos"]) == 2 and l.lido_em == relogio.t
    L.avisos(config(TESTING=True), s)
    assert len(s.pedidos) == 1                                # o cache valeu


def test_sessao_do_teste_vale_para_as_tres_fontes(relogio):
    s = SessaoArquivos({URLS["NEXUS_CLIMA_INMET_URL"]: inmet()})
    L.usar_sessao(s)
    assert L.avisos(config(TESTING=True)).dados is not None
    assert L.focos(config(TESTING=True)).erro                  # a sessão não tem o índice: erro, e não rede
    assert all(u.startswith("https://inmet.exemplo.test") or u.startswith("https://inpe.exemplo.test") for u, _ in s.pedidos)


def test_fonte_fora_nao_derruba_as_outras(relogio):
    s = SessaoArquivos({URLS["NEXUS_CLIMA_INMET_URL"]: inmet()})            # focos e risco dão 404
    c = config(TESTING=True)
    assert L.avisos(c, s).erro is None
    f = L.focos(c, s)
    assert f.dados is None and "404" in f.erro


def test_endereco_vem_da_configuracao(relogio):
    s = SessaoArquivos({"https://outro.exemplo.test/avisos": inmet()})
    l = L.avisos({"TESTING": True, "NEXUS_CLIMA_INMET_URL": "https://outro.exemplo.test/avisos"}, s)
    assert l.erro is None and s.pedidos[0][0] == "https://outro.exemplo.test/avisos"


def _cogs():
    quadro = [[0.2] * 40 for _ in range(30)]
    return SessaoArquivos({URLS["NEXUS_CLIMA_RISCO_URL"].format(d=d): montar_cog(quadro, origem=(-50.0, 10.0), escala=0.01)
                           for d in range(4)})


def test_risco_guarda_pelo_conjunto_de_pontos_e_refaz_se_o_conjunto_mudar(relogio):
    s = _cogs()
    c = config(TESTING=True)
    p1 = [("a", 9.9, -49.9), ("b", 9.8, -49.8)]
    L.risco(c, p1, s)
    n = len(s.pedidos)
    L.risco(c, list(reversed(p1)), s)                          # mesma gente, outra ordem: vale o cache
    assert len(s.pedidos) == n
    L.risco(c, p1 + [("c", 9.75, -49.75)], s)                  # entrou uma usina no cadastro: lê de novo
    assert len(s.pedidos) > n
    assert set(L.risco(c, p1 + [("c", 9.75, -49.75)], s).dados["por_ponto"]) == {"a", "b", "c"}


def test_risco_sem_pontos_nao_busca_nada(relogio):
    s = _cogs()
    l = L.risco(config(TESTING=True), [], s)
    assert l.dados["por_ponto"] == {} and s.pedidos == []


def test_as_tres_fontes_tem_cache_proprio(relogio):
    s = SessaoArquivos({URLS["NEXUS_CLIMA_INMET_URL"]: inmet()})
    c = config(TESTING=True)
    L.avisos(c, s)
    relogio.avanca(L.TTL_AVISOS_S + 1)
    L.focos(c, s)                                              # falha (404), mas só a dos focos
    assert L.avisos(c, s).erro is None and L.avisos(c, s).velha is False

"""Clima e risco: o cache de cada fonte (padrão de `publicacao.py` da operação em tempo real): TTL, janela de 60 s depois de
falha, uma busca por vez, última leitura boa servida com o erro e a hora, e nenhuma rede nos testes sem sessão injetada."""
import json
import logging
import threading
from datetime import date, datetime, timedelta, timezone

import pytest
import requests

from nexus.performance.clima import fontes
from nexus.performance.clima import leitura as L

from clima_cog import SessaoArquivos, montar_cog
from clima_power import SessaoPower

BRT = timezone(timedelta(hours=-3))


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


def _cogs(**kw):
    quadro = [[0.2] * 40 for _ in range(30)]
    return SessaoArquivos({URLS["NEXUS_CLIMA_RISCO_URL"].format(d=d): montar_cog(quadro, origem=(-50.0, 10.0), escala=0.01)
                           for d in range(4)}, **kw)


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


# ── o TTL do risco de fogo conta da DATA do arquivo, não só da leitura ──────────────────────────────────────────────

def _brt(dia, hh, mm=0):
    return datetime(2026, 10, dia, hh, mm, tzinfo=BRT).timestamp()


def test_ttl_do_risco_de_arquivo_desatualizado():
    assert L.TTL_RISCO_DESATUALIZADO_S == 15 * 60


def test_risco_lido_antes_da_publicacao_com_o_arquivo_de_ontem_so_vale_15_min(relogio):
    # O INPE publica às ~06:30. Lido às 05:00, o T0 ainda é o de 05/10: com 6 h de TTL a tela ficava com o arquivo de ontem
    # até as 11:01, mesmo com o de hoje no ar desde as 06:32.
    relogio.t = _brt(6, 5, 0)
    s = _cogs(modificado="Mon, 05 Oct 2026 09:32:00 GMT")                       # 06:32 de 05/10 em Brasília
    c, p = config(TESTING=True), [("a", 9.9, -49.9)]
    L.risco(c, p, s)
    n = len(s.pedidos)
    relogio.avanca(14 * 60)
    L.risco(c, p, s)
    assert len(s.pedidos) == n                                                  # 14 min depois ainda vale
    relogio.avanca(2 * 60)
    L.risco(c, p, s)
    assert len(s.pedidos) > n                                                   # 16 min depois lê de novo


def test_risco_lido_com_o_arquivo_de_hoje_vale_as_6_h(relogio):
    relogio.t = _brt(6, 7, 0)
    s = _cogs(modificado="Tue, 06 Oct 2026 09:32:00 GMT")                       # 06:32 de 06/10: o de hoje
    c, p = config(TESTING=True), [("a", 9.9, -49.9)]
    L.risco(c, p, s)
    n = len(s.pedidos)
    relogio.avanca(6 * 3600 - 60)
    L.risco(c, p, s)
    assert len(s.pedidos) == n                                                  # 5 h 59 min depois ainda vale
    relogio.avanca(120)
    L.risco(c, p, s)
    assert len(s.pedidos) > n


def test_risco_sem_a_data_do_arquivo_nao_ganha_6_h_na_duvida(relogio):
    relogio.t = _brt(6, 7, 0)
    s = _cogs(modificado=None)
    c, p = config(TESTING=True), [("a", 9.9, -49.9)]
    L.risco(c, p, s)
    n = len(s.pedidos)
    relogio.avanca(16 * 60)
    L.risco(c, p, s)
    assert len(s.pedidos) > n


def test_o_ttl_do_risco_vem_do_t0_e_nao_dos_outros_dias(relogio):
    # o T0 de ontem e os outros dias de hoje (arquivos publicados em horas diferentes): vale o T0
    relogio.t = _brt(6, 5, 0)
    dados = {"arquivos": {0: datetime(2026, 10, 5, 9, 32, tzinfo=timezone.utc), 1: datetime(2026, 10, 6, 9, 32, tzinfo=timezone.utc)}}
    assert L._ttl_do_risco(dados, relogio.t) == L.TTL_RISCO_DESATUALIZADO_S
    dados = {"arquivos": {1: datetime(2026, 10, 6, 9, 32, tzinfo=timezone.utc)}}                   # sem o T0: não dá para confirmar
    assert L._ttl_do_risco(dados, relogio.t) == L.TTL_RISCO_DESATUALIZADO_S
    assert L._ttl_do_risco({"arquivos": {0: datetime(2026, 10, 6, 9, 32, tzinfo=timezone.utc)}}, relogio.t) == L.TTL_RISCO_S


def test_o_ttl_das_outras_fontes_nao_muda(relogio):
    c = L.Cache(100, relogio=relogio)
    assert c.ler(Busca("a")).dados == "a"
    relogio.avanca(99)
    assert c.ler(Busca("b")).dados == "a"                                       # sem hook de validade, é o TTL do cache
    relogio.avanca(2)
    assert c.ler(Busca("c")).dados == "c"


def test_hook_de_validade_encurta_a_leitura_de_cada_resultado(relogio):
    c = L.Cache(1000, relogio=relogio, validade=lambda dados, t: 10 if dados == "curta" else 1000)
    c.ler(Busca("curta"))
    relogio.avanca(11)
    assert c.ler(Busca("nova")).dados == "nova"
    relogio.avanca(11)
    assert c.ler(Busca("outra")).dados == "nova"                                # "nova" ganhou o TTL longo


# ── a busca interrompida não deixa "lendo a fonte" para sempre ───────────────────────────────────────────────────────

class _Interrompida(BaseException):
    """Como Ctrl+C ou SystemExit: não é Exception, e `except Exception` não pega."""


def test_busca_interrompida_por_baseexception_solta_a_trava_e_a_proxima_busca_roda(relogio):
    c = cache(relogio)

    def morre():
        raise _Interrompida()
    with pytest.raises(_Interrompida):
        c.ler(morre)
    r = c.ler(Busca("ok"))
    assert (r.dados, r.erro) == ("ok", None)                                    # antes: "lendo a fonte" para sempre


# ── a falha vai ao log, uma vez por falha ────────────────────────────────────────────────────────────────────────────

def test_falha_da_fonte_vai_ao_log_uma_vez_por_falha_sem_a_mensagem_crua_da_rede(relogio, caplog):
    c = L.Cache(100, relogio=relogio, nome="INMET")
    c.ler(Busca("boa"))
    relogio.avanca(150)
    fora = Busca(falha=requests.ConnectionError("HTTPSConnectionPool(host='apiprevmet3.inmet.gov.br', port=443): Max retries"))
    with caplog.at_level(logging.WARNING, logger="nexus.performance.clima.leitura"):
        c.ler(fora)                                                             # a falha de verdade
        c.ler(fora)
        c.ler(fora)                                                             # dentro dos 60 s: nem busca, nem loga
    avisos = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(avisos) == 1 and fora.n == 1
    msg = avisos[0].getMessage()
    assert "INMET" in msg and "sem conexão com o servidor" in msg and "HTTPSConnectionPool" not in msg
    relogio.avanca(61)
    with caplog.at_level(logging.WARNING, logger="nexus.performance.clima.leitura"):
        c.ler(fora)                                                             # outra tentativa que falha: outro aviso
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 2


def test_leitura_boa_nao_loga_aviso(relogio, caplog):
    c = L.Cache(100, relogio=relogio, nome="INMET")
    with caplog.at_level(logging.DEBUG, logger="nexus.performance.clima.leitura"):
        c.ler(Busca("boa"))
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


def test_as_tres_fontes_tem_nome_no_log(relogio, caplog):
    s = SessaoArquivos({})                                                       # tudo dá 404
    with caplog.at_level(logging.WARNING, logger="nexus.performance.clima.leitura"):
        L.avisos(config(TESTING=True), s)
        L.focos(config(TESTING=True), s)
        L.risco(config(TESTING=True), [("a", -5.0, -45.0)], s)
    mensagens = " | ".join(r.getMessage() for r in caplog.records)
    assert "INMET" in mensagens and "focos" in mensagens and "risco de fogo" in mensagens and "HTTP 404" in mensagens


def test_hoje_e_a_data_de_brasilia_e_nao_a_do_utc(relogio):
    # 22:00 de 06/10 em Brasília já é 01:00 de 07/10 em UTC. O arquivo de 06:32 de 06/10 (BRT) é o de hoje: 6 h de TTL
    relogio.t = _brt(6, 22, 0)
    s = _cogs(modificado="Tue, 06 Oct 2026 09:32:00 GMT")
    c, p = config(TESTING=True), [("a", 9.9, -49.9)]
    L.risco(c, p, s)
    n = len(s.pedidos)
    relogio.avanca(16 * 60)
    L.risco(c, p, s)
    assert len(s.pedidos) == n


def test_a_data_do_arquivo_tambem_e_a_de_brasilia(relogio):
    # arquivo de 22:30 de 05/10 em Brasília = 01:30 de 06/10 em UTC: pela data em UTC pareceria "de hoje" às 05:00 de 06/10
    relogio.t = _brt(6, 5, 0)
    s = _cogs(modificado="Tue, 06 Oct 2026 01:30:00 GMT")
    c, p = config(TESTING=True), [("a", 9.9, -49.9)]
    L.risco(c, p, s)
    n = len(s.pedidos)
    relogio.avanca(16 * 60)
    L.risco(c, p, s)
    assert len(s.pedidos) > n


def test_falha_dentro_da_janela_de_60_s_nao_loga_de_novo(relogio, caplog):
    c = L.Cache(100, relogio=relogio, nome="focos")
    fora = Busca(falha=requests.Timeout("lento"))
    with caplog.at_level(logging.WARNING, logger="nexus.performance.clima.leitura"):
        for _ in range(5):
            c.ler(fora)
    assert fora.n == 1 and len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1


# ── a irradiação da NASA POWER: um cache POR USINA, 12 h ─────────────────────────────────────────────────────────────

HOJE = date(2026, 10, 7)
PUBLICADO = date(2026, 10, 2)


def cfg_testing(**extra):
    return {"TESTING": True, **extra}


def test_o_ttl_da_nasa_power_e_12_h_e_a_janela_e_de_40_dias():
    assert L.TTL_POWER_S == 12 * 3600 and L.JANELA_POWER_DIAS == 40


def test_pede_os_40_dias_que_terminam_hoje_e_so_uma_vez_pelo_ttl(relogio):
    s = SessaoPower(PUBLICADO)
    l = L.irradiacao(cfg_testing(), "1", -5.0, -45.0, HOJE, s)
    assert l.erro is None and l.velha is False and l.lido_em == relogio.t
    assert l.dados["publicado_ate"] == PUBLICADO and len(l.dados["dias"]) == 40
    q = s.consulta()
    assert (q["start"], q["end"]) == ("20260829", "20261007")
    L.irradiacao(cfg_testing(), "1", -5.0, -45.0, HOJE, s)
    assert len(s.pedidos) == 1
    relogio.avanca(12 * 3600 - 1)
    L.irradiacao(cfg_testing(), "1", -5.0, -45.0, HOJE, s)
    assert len(s.pedidos) == 1                                              # 11 h 59 min 59 s depois ainda vale
    relogio.avanca(2)
    L.irradiacao(cfg_testing(), "1", -5.0, -45.0, HOJE, s)
    assert len(s.pedidos) == 2


def test_virou_o_dia_com_o_cache_valido_nao_pede_de_novo(relogio):
    s = SessaoPower(PUBLICADO)
    L.irradiacao(cfg_testing(), "1", -5.0, -45.0, HOJE, s)
    relogio.avanca(3600)
    l = L.irradiacao(cfg_testing(), "1", -5.0, -45.0, HOJE + timedelta(days=1), s)       # a janela mudou, a leitura não
    assert len(s.pedidos) == 1 and l.erro is None


def test_cada_usina_tem_o_seu_cache_e_a_sua_coordenada(relogio):
    s = SessaoPower(PUBLICADO)
    L.irradiacao(cfg_testing(), "1", -5.0, -45.0, HOJE, s)
    L.irradiacao(cfg_testing(), "2", -10.0, -40.0, HOJE, s)
    assert len(s.pedidos) == 2
    assert (s.consulta(0)["latitude"], s.consulta(0)["longitude"]) == ("-5.00", "-45.00")
    assert (s.consulta(1)["latitude"], s.consulta(1)["longitude"]) == ("-10.00", "-40.00")
    L.irradiacao(cfg_testing(), "1", -5.0, -45.0, HOJE, s)
    L.irradiacao(cfg_testing(), "2", -10.0, -40.0, HOJE, s)
    assert len(s.pedidos) == 2


def test_o_id_da_usina_vale_como_texto(relogio):
    s = SessaoPower(PUBLICADO)
    L.irradiacao(cfg_testing(), 7, -5.0, -45.0, HOJE, s)
    L.irradiacao(cfg_testing(), 7, -5.0, -45.0, HOJE, s)
    L.irradiacao(cfg_testing(), "7", -5.0, -45.0, HOJE, s)
    assert len(s.pedidos) == 1


def test_a_falha_de_uma_usina_nao_derruba_a_outra(relogio):
    boa, ruim = SessaoPower(PUBLICADO), SessaoPower(PUBLICADO, status=503)
    assert L.irradiacao(cfg_testing(), "1", -5.0, -45.0, HOJE, boa).erro is None
    l = L.irradiacao(cfg_testing(), "2", -10.0, -40.0, HOJE, ruim)
    assert l.dados is None and l.erro == "HTTP 503" and l.velha is False
    assert L.irradiacao(cfg_testing(), "1", -5.0, -45.0, HOJE, boa).erro is None and len(boa.pedidos) == 1


def test_falha_serve_a_ultima_leitura_boa_dizendo_o_erro_e_a_hora_dela(relogio):
    s = SessaoPower(PUBLICADO)
    boa = L.irradiacao(cfg_testing(), "1", -5.0, -45.0, HOJE, s)
    relogio.avanca(13 * 3600)                                               # venceu
    s.status = 500
    l = L.irradiacao(cfg_testing(), "1", -5.0, -45.0, HOJE, s)
    assert l.dados == boa.dados and l.velha is True and l.erro == "HTTP 500" and l.lido_em == boa.lido_em


def test_nasa_dentro_de_60_s_da_falha_nao_insiste_e_depois_tenta_de_novo(relogio):
    s = SessaoPower(PUBLICADO, status=503)
    L.irradiacao(cfg_testing(), "1", -5.0, -45.0, HOJE, s)
    relogio.avanca(59)
    L.irradiacao(cfg_testing(), "1", -5.0, -45.0, HOJE, s)
    assert len(s.pedidos) == 1
    relogio.avanca(2)
    L.irradiacao(cfg_testing(), "1", -5.0, -45.0, HOJE, s)
    assert len(s.pedidos) == 2


def test_formato_diferente_da_nasa_vira_erro_do_cache_e_nao_numero(relogio):
    s = SessaoPower(PUBLICADO, corpo=b'{"properties": {}}')
    l = L.irradiacao(cfg_testing(), "1", -5.0, -45.0, HOJE, s)
    assert l.dados is None and "ALLSKY_SFC_SW_DWN" in l.erro


def test_uma_busca_por_vez_em_cada_usina_e_as_outras_usinas_nao_esperam(relogio):
    comecou, liberar = threading.Event(), threading.Event()

    def segura(url):
        comecou.set()
        assert liberar.wait(10)

    presa, livre, saida = SessaoPower(PUBLICADO, ao_pedir=segura), SessaoPower(PUBLICADO), []
    t = threading.Thread(target=lambda: saida.append(L.irradiacao(cfg_testing(), "1", -5.0, -45.0, HOJE, presa)))
    t.start()
    assert comecou.wait(10)
    try:
        mesma = L.irradiacao(cfg_testing(), "1", -5.0, -45.0, HOJE, SessaoPower(PUBLICADO))
        assert mesma.dados is None and mesma.erro == L.LENDO                  # quem chega no meio não espera a rede
        outra = L.irradiacao(cfg_testing(), "2", -10.0, -40.0, HOJE, livre)
        assert outra.erro is None and len(livre.pedidos) == 1               # a outra usina busca à parte, sem esperar a primeira
    finally:
        liberar.set()
        t.join(10)
    assert saida[0].erro is None and len(presa.pedidos) == 1


def test_sem_sessao_nos_testes_a_nasa_nao_vai_a_rede(monkeypatch, relogio):
    def nao(*a, **k):
        raise AssertionError("foi à rede")
    monkeypatch.setattr(fontes, "sessao_padrao", nao)
    monkeypatch.setattr(requests.Session, "get", nao)
    l = L.irradiacao({"TESTING": True}, "1", -5.0, -45.0, HOJE)
    assert l.dados is None and l.erro == "sem fonte nos testes"


def test_a_sessao_injetada_para_todos_vale_para_a_nasa(relogio):
    s = SessaoPower(PUBLICADO)
    L.usar_sessao(s)
    assert L.irradiacao(cfg_testing(), "1", -5.0, -45.0, HOJE).erro is None and len(s.pedidos) == 1


def test_o_endereco_da_nasa_vem_da_configuracao(relogio):
    s = SessaoPower(PUBLICADO)
    cfg = cfg_testing(NEXUS_CLIMA_POWER_URL="http://espelho.exemplo.test/p?x={lat},{lon}&a={inicio}&b={fim}")
    assert L.irradiacao(cfg, "1", -5.0, -45.0, HOJE, s).erro is None
    assert s.pedidos[0] == "http://espelho.exemplo.test/p?x=-5.00,-45.00&a=20260829&b=20261007"


def test_limpar_o_cache_esquece_as_usinas_da_nasa(relogio):
    s = SessaoPower(PUBLICADO)
    L.irradiacao(cfg_testing(), "1", -5.0, -45.0, HOJE, s)
    L.limpar_cache()
    L.irradiacao(cfg_testing(), "1", -5.0, -45.0, HOJE, s)
    assert len(s.pedidos) == 2


def test_a_falha_da_nasa_vai_ao_log_sem_coordenada_nem_usina(relogio, caplog):
    s = SessaoPower(PUBLICADO, status=503)
    with caplog.at_level(logging.WARNING, logger="nexus.performance.clima.leitura"):
        L.irradiacao(cfg_testing(), "usina-secreta-77", -5.4321, -45.1234, HOJE, s)
    mensagens = " | ".join(r.getMessage() for r in caplog.records)
    assert "NASA POWER" in mensagens and "HTTP 503" in mensagens
    for proibido in ("usina-secreta-77", "5.4321", "45.1234", "5,4321"):
        assert proibido not in mensagens

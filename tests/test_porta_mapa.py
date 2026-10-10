"""Porta única (09/10/2026): o mapa das telas da Plataforma de Performance e o passe (nexus/performance/porta.py).

Levi: "a partir de segunda quero o Nexus como link principal; o Nexus será o centro de tudo". O mapa é a fonte única
(spec 2026-10-09, seção 5.6): o Nexus é o dono e a plataforma tem a cópia (`plataforma/porta_nexus.py`). Os dois lados
comparam o MESMO texto canônico (abaixo, copiado do teste da plataforma); com `PLATAFORMA_REPO` apontando para o clone do
PerformancePainel, este teste também abre o módulo de lá e confere, de verdade, que os dois mapas são iguais, que a regra
do destino é a mesma e que o passe montado aqui é aceito pela plataforma (e o repetido, o vencido e o adulterado não).
"""
import base64
import hashlib
import hmac
import importlib.util
import json
import os
import time
from pathlib import Path

import pytest

from nexus.performance import porta

CHAVE = "c" * 40

# O texto canônico do mapa, igual ao da plataforma (`porta_nexus.texto_canonico_do_mapa()`). Mudou o mapa: muda aqui, lá
# e no teste de lá. A assinatura é o sha256 deste texto (16 primeiros), a mesma que a plataforma confere.
TEXTO_DA_PLATAFORMA = """performance|tempo-real|/tempo-real|/tempo-real/<fonte> /monitor|
performance|noc|/painel||
performance|diagnostico|/painel/usina/<id>||
performance|strings-trackers|/painel/falhas||
performance|gerencial|/gerencial||
performance|disponibilidade|/gerencial/disponibilidade||
performance|relatorio|/relatorio||
performance|relatorio-semanal|/relatorio/semanal||
performance|gemeo|/gemeo/|/gemeo/<path:resto>|
performance|historico-plataforma|/historico-plataforma||
performance|monitor-ronda|/ronda/monitor||
cos|acompanhamento|/cos||
base|chaves-fontes|/tokens||admin"""
ASSINATURA_DA_PLATAFORMA = "b80243d6133920c6"


def _decodificar(passe: str) -> tuple[dict, bytes, bytes]:
    corpo_b64, assin_b64 = passe.split(".")
    corpo = base64.urlsafe_b64decode(corpo_b64 + "=" * (-len(corpo_b64) % 4))
    assin = base64.urlsafe_b64decode(assin_b64 + "=" * (-len(assin_b64) % 4))
    return json.loads(corpo), corpo, assin


# ── o mapa ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_mapa_e_o_mesmo_da_plataforma():
    assert porta.texto_canonico_do_mapa() == TEXTO_DA_PLATAFORMA
    assert porta.assinatura_do_mapa() == ASSINATURA_DA_PLATAFORMA
    assert len(porta.MAPA) == 13 and len({(t.torre, t.tela) for t in porta.MAPA}) == 13


@pytest.mark.parametrize("caminho, tela", [
    ("/tempo-real", "tempo-real"), ("/tempo-real/pv", "tempo-real"), ("/monitor", "tempo-real"),
    ("/monitor?fonte=pv&embed=1", "tempo-real"), ("/painel", "noc"), ("/painel/usina/297410", "diagnostico"),
    ("/painel/usina/abc?fonte=pg&nome=Usina%20X", "diagnostico"), ("/painel/falhas", "strings-trackers"),
    ("/gerencial", "gerencial"), ("/gerencial/disponibilidade", "disponibilidade"), ("/relatorio", "relatorio"),
    ("/relatorio/semanal", "relatorio-semanal"), ("/gemeo/", "gemeo"), ("/gemeo/usina/12", "gemeo"),
    ("/historico-plataforma", "historico-plataforma"), ("/ronda/monitor", "monitor-ronda"), ("/cos", "acompanhamento"),
    ("/tokens", "chaves-fontes"),
])
def test_cada_caminho_cai_na_tela_certa(caminho, tela):
    assert porta.tela_do_caminho(caminho).tela == tela
    assert porta.destino_permitido(caminho) == caminho


@pytest.mark.parametrize("ruim", [
    None, "", "tempo-real", "//evil.example/x", "/\\evil.example", "https://evil.example/tempo-real", "/login",
    "/os/", "/painel/nexus/entrar", "/painel/usina/", "/painel/usina/1/2", "/gemeo", "/tempo-real#x",
    "/tempo-real x", "/painel/usina/a'b", '/painel/usina/a"b', "/painel/usina/<b>", "/tempo-real/../tokens",
    "/painel/usina/1\n", "/" + "a" * 2048, "/api/macro", "/",
])
def test_destino_fora_do_mapa_e_recusado(ruim):
    assert porta.destino_permitido(ruim) is None


def test_padroes_do_navegador_valem_igual_no_python():
    """As expressões que o porta.js usa para acender o item são as mesmas do Python (sem o "\\-" do re.escape)."""
    import re
    for t in porta.MAPA:
        for fonte in porta.padroes_do_navegador(t):
            assert "\\-" not in fonte and fonte.startswith("^") and fonte.endswith("$")
            assert re.compile(fonte)
    assert porta.padroes_do_navegador(porta.tela_do_caminho("/gemeo/")) == ["^/gemeo/$", "^/gemeo/[^?#]+$"]


# ── o passe ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_passe_assina_com_a_chave_e_vence_em_60_s():
    agora = time.time()
    passe = porta.montar_passe(CHAVE, "pessoa@exemplo.test", "Pessoa Teste", False, "/painel")
    dados, corpo, assin = _decodificar(passe)
    assert hmac.compare_digest(assin, hmac.new(CHAVE.encode(), corpo, hashlib.sha256).digest())
    assert dados["v"] == 1 and dados["email"] == "pessoa@exemplo.test" and dados["nome"] == "Pessoa Teste"
    assert dados["admin"] is False and dados["destino"] == "/painel"
    assert agora + 59 <= dados["vence"] <= agora + 60
    assert 16 <= len(dados["numero"]) <= 128 and all(c.isalnum() or c in "-_" for c in dados["numero"])
    assert "=" not in passe and "/" not in passe and "+" not in passe     # base64url sem preenchimento


def test_o_passe_muda_a_cada_abertura():
    passes = {porta.montar_passe(CHAVE, "p@exemplo.test", "P", True, "/tempo-real") for _ in range(20)}
    numeros = {_decodificar(p)[0]["numero"] for p in passes}
    assert len(passes) == 20 and len(numeros) == 20


def test_outra_chave_nao_confere():
    _, corpo, assin = _decodificar(porta.montar_passe(CHAVE, "p@exemplo.test", "P", False, "/cos"))
    assert not hmac.compare_digest(assin, hmac.new(("d" * 40).encode(), corpo, hashlib.sha256).digest())


@pytest.mark.parametrize("chave", ["", None, "curta", "c" * 31])
def test_sem_chave_ou_chave_curta_nao_monta_passe(chave):
    assert porta.motivo_da_chave(chave)
    with pytest.raises(ValueError):
        porta.montar_passe(chave, "p@exemplo.test", "P", False, "/painel")


def test_o_motivo_da_chave_nunca_mostra_o_valor():
    assert "curta-secreta" not in (porta.motivo_da_chave("curta-secreta") or "")
    assert porta.motivo_da_chave(CHAVE) is None and porta.motivo_da_chave("  " + CHAVE + "  ") is None


def test_passe_para_fora_do_mapa_nao_sai():
    for ruim in ("//evil.example/", "/login", "https://evil.example/painel"):
        with pytest.raises(ValueError):
            porta.montar_passe(CHAVE, "p@exemplo.test", "P", False, ruim)


# ── a base da plataforma para o navegador ────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("valor, base", [
    ("", ""), (None, ""), ("  ", ""), ("https://app.exemplo.test", "https://app.exemplo.test"),
    ("https://app.exemplo.test/", "https://app.exemplo.test"), ("http://127.0.0.1:5150", "http://127.0.0.1:5150"),
    ("http://localhost:5150/", "http://localhost:5150"), ("https://app.exemplo.test/plataforma", "https://app.exemplo.test/plataforma"),
])
def test_base_da_plataforma(valor, base):
    assert porta.base_da_plataforma(valor) == base


@pytest.mark.parametrize("ruim", ["http://app.exemplo.test", "ftp://x.test", "https://x.test/a?b=1", "https://x.test/#a",
                                  "https://u:s@x.test", "https://x.test\\@127.0.0.1", "https://x .test", "javascript:x",
                                  "//x.test"])
def test_base_da_plataforma_recusa(ruim):
    with pytest.raises(ValueError):
        porta.base_da_plataforma(ruim)


# ── os dois lados de verdade (com o clone do PerformancePainel à mão) ────────────────────────────────────────────────
def _modulo_da_plataforma():
    raiz = os.environ.get("PLATAFORMA_REPO", "")
    arquivo = Path(raiz) / "plataforma" / "porta_nexus.py" if raiz else None
    if not arquivo or not arquivo.is_file():
        pytest.skip("PLATAFORMA_REPO não aponta para um clone do PerformancePainel com plataforma/porta_nexus.py")
    spec = importlib.util.spec_from_file_location("porta_nexus_da_plataforma", arquivo)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_com_o_clone_da_plataforma_o_mapa_e_a_regra_do_destino_sao_os_mesmos():
    pn = _modulo_da_plataforma()
    assert pn.texto_canonico_do_mapa() == porta.texto_canonico_do_mapa()
    assert pn.assinatura_do_mapa() == porta.assinatura_do_mapa()
    assert [t.nome for t in pn.MAPA] == [t.nome for t in porta.MAPA]
    casos = [t.caminho.replace("<id>", "297410") for t in porta.MAPA] + [
        "/monitor?fonte=pv&embed=1", "/gemeo/usina/1", "/painel/usina/a%20b?nome=X%27Y", "//evil.example", "/login",
        "/os/", "/tempo-real#x", "/painel/usina/a'b", "/tempo-real/../tokens", "/painel/nexus/entrar", "/", "",
        "/tempo-real?x=<b>", "/api/macro"]
    for c in casos:
        assert pn.destino_permitido(c) == porta.destino_permitido(c), c


def test_com_o_clone_da_plataforma_o_passe_do_nexus_e_aceito_uma_vez():
    pn = _modulo_da_plataforma()
    usados = pn.NumerosUsados()
    passe = porta.montar_passe(CHAVE, "Pessoa@Exemplo.test", "Pessoa Teste", True, "/painel/usina/12?fonte=pv")
    lido = pn.ler_passe(passe, CHAVE, time.time(), usados)
    assert lido == {"email": "pessoa@exemplo.test", "nome": "Pessoa Teste", "admin": True,
                    "destino": "/painel/usina/12?fonte=pv"}
    with pytest.raises(pn.PasseRecusado, match="já foi usado"):
        pn.ler_passe(passe, CHAVE, time.time(), usados)
    with pytest.raises(pn.PasseRecusado, match="venceu"):
        pn.ler_passe(porta.montar_passe(CHAVE, "p@exemplo.test", "P", False, "/cos"), CHAVE, time.time() + 61, usados)
    with pytest.raises(pn.PasseRecusado, match="assinatura"):
        pn.ler_passe(porta.montar_passe(CHAVE, "p@exemplo.test", "P", False, "/cos"), "d" * 40, time.time(), usados)
    corpo, assin = porta.montar_passe(CHAVE, "p@exemplo.test", "P", False, "/cos").split(".")
    dados = json.loads(base64.urlsafe_b64decode(corpo + "=" * (-len(corpo) % 4)))
    dados["admin"] = True                                    # alguém tenta virar admin no caminho
    adulterado = base64.urlsafe_b64encode(json.dumps(dados).encode()).decode().rstrip("=") + "." + assin
    with pytest.raises(pn.PasseRecusado, match="assinatura"):
        pn.ler_passe(adulterado, CHAVE, time.time(), usados)
    # o da senha de administrador do Nexus também entra (e-mail da reserva, num domínio que não existe)
    lido = pn.ler_passe(porta.montar_passe(CHAVE, porta.EMAIL_DA_SENHA_DE_ADMIN, porta.NOME_DA_SENHA_DE_ADMIN, True,
                                           "/tokens"), CHAVE, time.time(), usados)
    assert lido["email"] == porta.EMAIL_DA_SENHA_DE_ADMIN and lido["admin"] is True

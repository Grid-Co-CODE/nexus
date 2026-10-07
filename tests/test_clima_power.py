"""Clima e risco: o cliente da NASA POWER (irradiação diária, GHI) no formato real medido ao vivo em 07/10/2026. Sem rede.

A resposta de verdade: `properties.parameter.ALLSKY_SFC_SW_DWN` = {AAAAMMDD: kWh/m²/dia}, a unidade em `parameters`, e -999 para o dia
ainda não publicado (a NASA atrasa uns 5 dias; em 07/10 o último dia com valor era 02/10) e para um buraco isolado no meio."""
import json
from datetime import date
from urllib.parse import urlsplit

import pytest
import requests

from nexus.performance.clima import fontes as F

from clima_power import SessaoPower, corpo_power

HOJE = date(2026, 10, 7)
PUBLICADO = date(2026, 10, 2)


def ler(sessao=None, lat=-15.78, lon=-47.93, inicio=date(2026, 9, 1), fim=HOJE, **kw):
    sessao = sessao or SessaoPower(PUBLICADO)
    return F.nasa_power(lat, lon, inicio, fim, sessao, **kw), sessao


# ── o pedido ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_o_pedido_tem_o_endereco_e_os_parametros_da_nasa_power():
    _, s = ler()
    partes = urlsplit(s.pedidos[0])
    assert (partes.scheme, partes.netloc, partes.path) == ("https", "power.larc.nasa.gov", "/api/temporal/daily/point")
    assert s.consulta() == {"parameters": "ALLSKY_SFC_SW_DWN", "community": "RE", "longitude": "-47.93", "latitude": "-15.78",
                            "start": "20260901", "end": "20261007", "format": "JSON"}
    assert len(s.pedidos) == 1


def test_a_coordenada_vai_com_duas_casas_para_nao_entregar_a_posicao_exata_da_usina():
    _, s = ler(lat=-15.784321, lon=-47.931999)
    q = s.consulta()
    assert (q["latitude"], q["longitude"]) == ("-15.78", "-47.93")
    assert "784321" not in s.pedidos[0] and "931999" not in s.pedidos[0]


def test_o_pedido_aceita_resposta_json_e_tem_tempo_limite():
    visto = {}

    class S(SessaoPower):
        def get(self, url, params=None, headers=None, timeout=None):
            visto.update(headers=headers, timeout=timeout)
            return super().get(url, params, headers, timeout)

    ler(S(PUBLICADO))
    assert visto["headers"] == {"Accept": "application/json"} and visto["timeout"] == F.TEMPO_LIMITE_S


def test_janela_ao_contrario_e_erro_de_quem_chama():
    with pytest.raises(ValueError):
        ler(inicio=date(2026, 10, 7), fim=date(2026, 10, 1))


# ── a série ──────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_le_a_serie_diaria_em_kwh_por_m2():
    r, s = ler(inicio=date(2026, 9, 28), fim=date(2026, 10, 1))
    dias = [date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 1)]
    assert r["dias"] == {d: s.valor(d) for d in dias} and all(isinstance(v, float) for v in r["dias"].values())
    assert r["publicado_ate"] == date(2026, 10, 1)


def test_menos_999_no_fim_e_dia_nao_publicado_nunca_zero():
    r, _ = ler()
    assert r["publicado_ate"] == PUBLICADO
    for dia in (date(2026, 10, 3), date(2026, 10, 4), date(2026, 10, 7)):
        assert r["dias"][dia] is None
    assert r["dias"][PUBLICADO] is not None and 0 not in r["dias"].values()
    assert len(r["dias"]) == 37                                       # a janela inteira vem, com None onde falta


def test_menos_999_no_meio_da_serie_e_buraco_e_tambem_nao_vira_zero():
    s = SessaoPower(PUBLICADO, buracos={date(2026, 9, 7)})            # o que a NASA mandou em 07/10 para 07/09
    r, _ = ler(s)
    assert r["dias"][date(2026, 9, 7)] is None and r["dias"][date(2026, 9, 6)] is not None
    assert r["publicado_ate"] == PUBLICADO


def test_serie_toda_sem_dado_nao_e_erro_e_diz_que_nenhum_dia_foi_publicado():
    r, _ = ler(SessaoPower(date(2026, 8, 1)), inicio=date(2026, 10, 3), fim=HOJE)
    assert r["publicado_ate"] is None and set(r["dias"].values()) == {None}


def test_zero_que_a_nasa_manda_e_zero_mesmo():
    s = SessaoPower(PUBLICADO, valor=lambda d: 0.0)
    r, _ = ler(s, inicio=date(2026, 9, 30), fim=date(2026, 10, 1))
    assert set(r["dias"].values()) == {0.0}                          # só o -999 é "sem dia"; 0 é número


@pytest.mark.parametrize("valor", [0.5, 5.4321, 11.9, 15.0])
def test_valores_dentro_do_possivel_passam(valor):
    r, _ = ler(SessaoPower(PUBLICADO, valor=lambda d: valor), inicio=date(2026, 9, 30), fim=date(2026, 9, 30))
    assert r["dias"] == {date(2026, 9, 30): valor}


# ── formato diferente é erro explícito ──────────────────────────────────────────────────────────────────────────────

BOM = {"20260930": 5.0, "20261001": 4.0}


def com(corpo):
    return SessaoPower(PUBLICADO, corpo=corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode())


def trocar(caminho, valor):
    """Cópia do JSON bom com `caminho` (lista de chaves) trocado por `valor` (None apaga a chave)."""
    novo = json.loads(corpo_power(BOM))
    no = novo
    for k in caminho[:-1]:
        no = no[k]
    if valor is None:
        del no[caminho[-1]]
    else:
        no[caminho[-1]] = valor
    return novo


@pytest.mark.parametrize("corpo,trecho", [
    (b"isto nao e json", "não é JSON"),
    (b"[1, 2, 3]", "não é um objeto"),
    (json.dumps({"header": {}}).encode(), "ALLSKY_SFC_SW_DWN"),
    (trocar(["properties", "parameter"], {"OUTRA": {"20260930": 1.0}}), "ALLSKY_SFC_SW_DWN"),
    (trocar(["properties"], None), "ALLSKY_SFC_SW_DWN"),
    (trocar(["properties", "parameter", "ALLSKY_SFC_SW_DWN"], {}), "vazia"),
    (trocar(["properties", "parameter", "ALLSKY_SFC_SW_DWN"], [5.0, 4.0]), "vazia ou fora do formato"),
    (trocar(["properties", "parameter", "ALLSKY_SFC_SW_DWN"], {"2026-09-30": 5.0}), "AAAAMMDD"),
    (trocar(["properties", "parameter", "ALLSKY_SFC_SW_DWN"], {"20260230": 5.0}), "AAAAMMDD"),
    (trocar(["properties", "parameter", "ALLSKY_SFC_SW_DWN"], {"20260930": "5.0"}), "não é número"),
    (trocar(["properties", "parameter", "ALLSKY_SFC_SW_DWN"], {"20260930": True}), "não é número"),
    (trocar(["properties", "parameter", "ALLSKY_SFC_SW_DWN"], {"20260930": None}), "não é número"),
    (trocar(["properties", "parameter", "ALLSKY_SFC_SW_DWN"], {"20260930": 25.0}), "fora da faixa"),
    (trocar(["properties", "parameter", "ALLSKY_SFC_SW_DWN"], {"20260930": -3.0}), "fora da faixa"),
    (trocar(["properties", "parameter", "ALLSKY_SFC_SW_DWN"], {"20260930": 15.5}), "fora da faixa"),
    (trocar(["parameters", "ALLSKY_SFC_SW_DWN", "units"], "MJ/m^2/day"), "unidade da NASA POWER mudou (esperava kW-hr/m^2/day, veio MJ/m^2/day)"),
    (trocar(["parameters", "ALLSKY_SFC_SW_DWN", "units"], "Wh/m^2/day"), "unidade da NASA POWER mudou"),
    (trocar(["parameters"], None), "não informou a unidade"),
    (trocar(["parameters", "ALLSKY_SFC_SW_DWN"], {}), "não informou a unidade"),
    (trocar(["header", "fill_value"], -9999.0), "-9999"),
])
def test_formato_diferente_do_medido_levanta_fonte_erro_dizendo_o_que_viu(corpo, trecho):
    with pytest.raises(F.FonteErro) as e:
        ler(com(corpo))
    assert trecho in str(e.value)


def test_sem_o_fill_value_no_cabecalho_vale_o_menos_999_do_formato_medido():
    r, _ = ler(com(trocar(["header"], {})), inicio=date(2026, 9, 30), fim=date(2026, 10, 1))
    assert r["dias"] == {date(2026, 9, 30): 5.0, date(2026, 10, 1): 4.0}


def test_um_menos_999_inteiro_e_o_mesmo_que_o_decimal():
    corpo = corpo_power({"20260930": -999, "20261001": 4.0})
    r, _ = ler(com(corpo))
    assert r["dias"] == {date(2026, 9, 30): None, date(2026, 10, 1): 4.0}


@pytest.mark.parametrize("status", [400, 422, 429, 500, 503])
def test_resposta_de_erro_da_nasa_levanta_com_o_codigo(status):
    with pytest.raises(requests.HTTPError) as e:
        ler(SessaoPower(PUBLICADO, status=status))
    assert F.resumo_do_erro(e.value) == f"HTTP {status}"


def test_rede_caida_e_tempo_esgotado_atravessam_para_o_cache_dizer():
    with pytest.raises(requests.ConnectionError):
        ler(SessaoPower(PUBLICADO, erro=requests.ConnectionError("sem rede")))
    with pytest.raises(requests.Timeout):
        ler(SessaoPower(PUBLICADO, erro=requests.Timeout("lento")))
    assert F.resumo_do_erro(requests.Timeout("x")) == "tempo esgotado"


def test_mensagem_de_erro_do_corpo_422_nao_vira_serie():
    corpo = json.dumps({"header": "falhou", "messages": ["Please provide a correct start date formatting."]}).encode()
    with pytest.raises(F.FonteErro):
        ler(com(corpo))


# ── o endereço troca pela configuração ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("modelo", ["http://x/{lat}/{lon}/{inicio}/{fim}/{outro}", "http://x/{lat}/{lon}/{inicio}/{fim}/{",
                                    "http://x/{lat}/{lon}/{inicio}/{fim}/{0}"])
def test_modelo_com_outras_chaves_ou_chave_aberta_e_erro_claro_e_nao_excecao_crua(modelo):
    s = SessaoPower(PUBLICADO)
    with pytest.raises(F.FonteErro) as e:
        ler(s, modelo_url=modelo)
    assert "entre chaves" in str(e.value) and s.pedidos == []


def test_endereco_padrao_e_o_da_nasa_e_troca_pela_configuracao():
    e = F.enderecos({})
    assert e["power"] == F.NASA_POWER and e["power"].startswith("https://power.larc.nasa.gov/api/temporal/daily/point?")
    assert "{lat}" in e["power"] and "{lon}" in e["power"] and "{inicio}" in e["power"] and "{fim}" in e["power"]
    assert F.enderecos({"NEXUS_CLIMA_POWER_URL": "http://espelho.exemplo.test/p?x={lat},{lon}&a={inicio}&b={fim}"})["power"] == \
        "http://espelho.exemplo.test/p?x={lat},{lon}&a={inicio}&b={fim}"
    assert F.enderecos({"NEXUS_CLIMA_POWER_URL": "   "})["power"] == F.NASA_POWER            # vazio: vale o padrão


def test_o_modelo_trocado_e_o_que_vai_na_rede():
    modelo = "http://espelho.exemplo.test/p?x={lat},{lon}&a={inicio}&b={fim}"
    _, s = ler(modelo_url=modelo, lat=-5.01234, lon=-45.0)
    assert s.pedidos[0] == "http://espelho.exemplo.test/p?x=-5.01,-45.00&a=20260901&b=20261007"


@pytest.mark.parametrize("modelo", ["http://x/{lat}/{lon}/{inicio}", "http://x/{lon}/{inicio}/{fim}", "http://x/fixo", ""])
def test_modelo_sem_um_dos_quatro_lugares_e_erro_antes_de_ir_a_rede(modelo):
    s = SessaoPower(PUBLICADO)
    with pytest.raises(F.FonteErro) as e:
        ler(s, modelo_url=modelo)
    assert "{lat}" in str(e.value) and s.pedidos == []

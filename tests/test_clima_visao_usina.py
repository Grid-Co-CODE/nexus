"""Clima e risco: o view-model da página de UMA usina (`visao.montar_usina`, 07/10/2026), com leituras prontas no lugar das fontes. Sem
rede, sem Flask. O cadastro, os avisos, os focos e o risco são os de `test_clima_visao.py`; a NASA é uma leitura pronta."""
from datetime import date, datetime, timedelta, timezone

import pytest

from nexus.performance.clima import leitura as L
from nexus.performance.clima import visao as V
from nexus.performance.clima.geotiff import Amostra

from test_clima_visao import (REF, UTC, aviso, cadastro, dias, foco_a, lei_avisos, lei_focos, lei_risco, leituras,  # noqa: F401
                              usina)

HOJE = date(2026, 10, 6)                         # REF é 06/10/2026 15:00 em Brasília


def serie_nasa(ate=date(2026, 10, 2), de=date(2026, 8, 28), valor=lambda d: float(d.day) if d.month == 10 else 4.0, buracos=()):
    """O que a NASA devolve na janela de 40 dias: um valor por dia até `ate`, None depois e nos `buracos`."""
    dias_, d = {}, de
    while d <= HOJE:
        dias_[d] = None if (d > ate or d in buracos) else valor(d)
        d += timedelta(days=1)
    publicados = [d for d, v in dias_.items() if v is not None]
    return {"dias": dias_, "publicado_ate": max(publicados) if publicados else None}


def lei_nasa(dados=None, **kw):
    return L.Leitura(dados if dados is not None else serie_nasa(), REF.timestamp(), **kw)


@pytest.fixture
def nasa(monkeypatch):
    """Troca `leitura.irradiacao` por uma leitura pronta e guarda como foi chamada."""
    chamadas = []

    def instalar(leitura):
        def falsa(config, usina_id, lat, lon, hoje, sessao=None):
            chamadas.append({"id": usina_id, "lat": lat, "lon": lon, "hoje": hoje})
            return leitura
        monkeypatch.setattr(L, "irradiacao", falsa)
        return chamadas
    return instalar


def tudo_lido(leituras, avisos=(), focos=(), risco=None):
    leituras(avisos=lei_avisos(*avisos), focos=lei_focos(*focos), risco=risco or lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1)}))


def pagina(**kw):
    return V.montar_usina({}, cadastro=kw.pop("cadastro", cadastro(usina("1", "U"))), usina_id=kw.pop("usina_id", "1"), ref=REF, **kw)


# ── achar a usina ────────────────────────────────────────────────────────────────────────────────────────────────────

def test_usina_que_nao_existe_devolve_none(leituras, nasa):
    tudo_lido(leituras)
    nasa(lei_nasa())
    assert pagina(usina_id="99") is None and pagina(usina_id="") is None


def test_o_id_vale_como_texto_e_o_cabecalho_traz_nome_cliente_e_uf(leituras, nasa):
    tudo_lido(leituras)
    nasa(lei_nasa())
    v = pagina(cadastro=cadastro(usina("1", "Usina Um", cliente="Cliente X", uf="PA")), usina_id=1)
    assert (v["id"], v["nome"], v["cliente"], v["uf"], v["onde"]) == ("1", "Usina Um", "Cliente X", "PA", "Cliente X · PA")
    assert v["atualizada"] == "15:00" and v["pendencia"] == ""


def test_so_acha_usina_em_operacao_do_cadastro_e_sem_uf_a_linha_nao_fica_com_ponto(leituras, nasa):
    tudo_lido(leituras)
    nasa(lei_nasa())
    assert pagina(cadastro=cadastro(usina("1", "U", uf="")))["onde"] == "Cliente"


def test_o_filtro_de_cliente_so_vale_se_o_cliente_existe(leituras, nasa):
    tudo_lido(leituras)
    nasa(lei_nasa())
    cad = cadastro(usina("1", "U", cliente="X"))
    assert pagina(cadastro=cad, cliente="X")["cliente_filtro"] == "X" and pagina(cadastro=cad, cliente="Inventado")["cliente_filtro"] == ""


# ── usina sem coordenada: aviso claro e nenhuma fonte ────────────────────────────────────────────────────────────────

def test_usina_sem_coordenada_diz_o_que_falta_e_nao_vai_a_nenhuma_fonte(monkeypatch):
    def nao(*a, **k):
        raise AssertionError("foi buscar fonte para usina sem coordenada")
    for f in ("avisos", "focos", "risco", "firms", "irradiacao"):
        monkeypatch.setattr(L, f, nao)
    cad = cadastro(usina("1", "Com"), sem=[usina("2", "Sem Coordenada", None, None)])
    v = V.montar_usina({}, cadastro=cad, usina_id="2", ref=REF)
    assert v["nome"] == "Sem Coordenada" and v["card"] is None and v["irradiacao"] is None and v["fontes"] == []
    assert v["pendencia"] == ("Sem coordenada no cadastro: sem latitude e longitude não há onde procurar aviso, foco, risco de fogo "
                              "nem irradiação. Corrija a coordenada no cadastro.")


def test_usina_com_coordenada_fora_do_brasil_diz_o_que_falta(monkeypatch):
    def nao(*a, **k):
        raise AssertionError("foi buscar fonte")
    for f in ("avisos", "focos", "risco", "firms", "irradiacao"):
        monkeypatch.setattr(L, f, nao)
    v = V.montar_usina({}, cadastro=cadastro(fora=[usina("3", "Zero", 0.0, 0.0)]), usina_id="3", ref=REF)
    assert v["pendencia"].startswith("Coordenada fora do Brasil no cadastro") and v["card"] is None


# ── os alertas da usina ──────────────────────────────────────────────────────────────────────────────────────────────

def test_o_nivel_da_usina_e_o_mesmo_da_tela_principal(leituras, nasa):
    nasa(lei_nasa())
    tudo_lido(leituras, focos=[foco_a(1.0)])
    v = pagina()
    assert (v["nivel"], v["rotulo"]) == ("agir", "Agir agora") and v["card"]["motivos"][0]["pill"] == "Fogo a 1,0 km"
    tudo_lido(leituras, avisos=[aviso(1, evento="Baixa Umidade")])
    assert (pagina()["nivel"], pagina()["rotulo"]) == ("atencao", "Atenção")
    tudo_lido(leituras)
    assert (pagina()["nivel"], pagina()["rotulo"]) == ("sem", "Sem alerta")


def test_sem_alerta_com_fonte_faltando_nao_diz_sem_alerta(leituras, nasa):
    nasa(lei_nasa())
    leituras(focos=lei_focos(), risco=lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1)}))              # o INMET está fora
    v = pagina()
    assert (v["nivel"], v["rotulo"]) == ("duvida", "Sem leitura completa")
    assert v["faltando"] == ["avisos do Instituto Nacional de Meteorologia (INMET)"] and v["alertas"]["avisos_vazio"] == "Sem leitura dos avisos do Instituto Nacional de Meteorologia (INMET)"


def test_sem_alerta_com_fonte_pela_metade_diz_nas_fontes_lidas(leituras, nasa):
    nasa(lei_nasa())
    leituras(avisos=lei_avisos(ignorados=["aviso 7: sem polígono"]), focos=lei_focos(), risco=lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1)}))
    assert (pagina()["nivel"], pagina()["rotulo"]) == ("sem", "Sem alerta nas fontes lidas")


def test_com_alerta_o_nivel_vale_mesmo_com_fonte_faltando(leituras, nasa):
    nasa(lei_nasa())
    leituras(focos=lei_focos(foco_a(1.0)), risco=lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1)}))
    v = pagina()
    assert (v["nivel"], v["rotulo"]) == ("agir", "Agir agora") and v["faltando"] == ["avisos do Instituto Nacional de Meteorologia (INMET)"]


def test_o_bloco_de_alertas_diz_o_que_ha_e_o_que_nao_ha(leituras, nasa):
    nasa(lei_nasa())
    tudo_lido(leituras, avisos=[aviso(2, evento="Vendaval")], focos=[foco_a(2.0)], risco=lei_risco({"1": dias(1.0, 0.8, 0.1, 0.1)}))
    a = pagina()["alertas"]
    assert [x["evento"] for x in a["avisos"]] == ["Vendaval"] and a["avisos_vazio"] == ""
    assert a["foco"] == "1 foco a até 5 km · o mais perto a 2,0 km (GOES-19, 14:50)"
    assert [(d["rotulo"], d["curto"], d["cor"]) for d in a["dias"]] == [("Hoje", "1,00", "c"), ("D+1", "0,80", "a"), ("D+2", "0,10", "n"),
                                                                       ("D+3", "0,10", "n")]
    tudo_lido(leituras)
    a = pagina()["alertas"]
    assert a["avisos"] == [] and a["avisos_vazio"] == "Nenhum aviso do Instituto Nacional de Meteorologia (INMET) sobre esta usina" and a["foco"] == "Nenhum foco a até 5 km"


def test_sem_leitura_dos_focos_e_do_risco_o_bloco_nao_inventa(leituras, nasa):
    nasa(lei_nasa())
    leituras(avisos=lei_avisos())
    a = pagina()["alertas"]
    assert a["foco"] == "Sem leitura dos focos do Instituto Nacional de Pesquisas Espaciais (INPE)" and a["dias"] is None and a["risco_vazio"] == "Sem leitura do risco de fogo do Instituto Nacional de Pesquisas Espaciais (INPE)"


def test_sem_dado_de_risco_nos_quatro_dias_diz_a_causa(leituras, nasa):
    nasa(lei_nasa())
    tudo_lido(leituras, risco=lei_risco({"1": dias(None, None, None, None)}))
    a = pagina()["alertas"]
    assert a["risco_linha"] == "sem dado (sem vegetação no entorno)" and a["risco_vazio"] is None


def test_o_risco_e_lido_para_todas_as_usinas_do_cadastro_e_nao_so_para_esta(leituras, nasa):
    nasa(lei_nasa())
    pedidos = leituras(avisos=lei_avisos(), focos=lei_focos(), risco=lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1), "2": dias(0.1, 0.1, 0.1, 0.1)}))
    pagina(cadastro=cadastro(usina("1", "A"), usina("2", "B", -5.5)))
    assert len(pedidos["risco"][0]) == 2                                          # o cache do risco vale pelo conjunto de pontos


def test_as_fontes_da_pagina_dizem_de_quando_e_o_dado(leituras, nasa):
    nasa(lei_nasa())
    tudo_lido(leituras)
    v = pagina()
    assert [f["id"] for f in v["fontes"]] == ["inmet", "focos", "risco", "firms", "power"] and [f["estado"] for f in v["fontes"]] == ["ok"] * 5
    assert "lido às 15:00" in v["fontes"][0]["texto"] and v["fontes"][4]["texto"] == "Prediction Of Worldwide Energy Resources, projeto da NASA (NASA POWER) · irradiação: lida às 15:00 · publicada até 02/10"


# ── a irradiação ─────────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_nasa_e_chamada_com_a_usina_a_coordenada_e_hoje_de_brasilia(leituras, nasa):
    tudo_lido(leituras)
    chamadas = nasa(lei_nasa())
    pagina(cadastro=cadastro(usina("1", "U", -5.5, -45.5)))
    assert chamadas == [{"id": "1", "lat": -5.5, "lon": -45.5, "hoje": HOJE}]
    tarde = datetime(2026, 10, 7, 1, 30, tzinfo=UTC)                          # 22:30 de 06/10 em Brasília
    V.montar_usina({}, cadastro=cadastro(usina("1", "U")), usina_id="1", ref=tarde)
    assert chamadas[-1]["hoje"] == HOJE


def test_leitura_boa_da_nasa_traz_grafico_mes_tabela_e_a_fonte(leituras, nasa):
    tudo_lido(leituras)
    nasa(lei_nasa())
    ir = pagina()["irradiacao"]
    assert ir["estado"] == "ok" and ir["texto"] == "Prediction Of Worldwide Energy Resources, projeto da NASA (NASA POWER) · irradiação: lida às 15:00 · publicada até 02/10" and ir["erro"] == ""
    g = ir["grafico"]
    assert g["viewbox"] == "0 0 620 270" and len(g["nasa"]["trechos"]) == 1 and len(g["nasa"]["trechos"][0].split()) == 26
    assert g["faixa"] is not None and "publicado até 02/10" in g["descricao"]
    assert g["rotulos_x"][0]["texto"] == "07/09" and g["rotulos_x"][-1]["texto"] == "06/10"
    assert len(ir["tabela"]) == 30 and ir["tabela"][-1] == {"dia": "06/10", "valor": "—"} and ir["tabela"][-5] == {"dia": "02/10", "valor": "2,00"}


def test_o_mes_ate_agora_soma_ate_o_ultimo_dia_publicado_e_diz_qual(leituras, nasa):
    tudo_lido(leituras)
    nasa(lei_nasa())
    mes = pagina()["irradiacao"]["mes"]
    assert mes["rotulo"] == "outubro/2026" and mes["valor"] == "3,0" and mes["unidade"] == "kWh/m²"
    assert mes["texto"] == "3,0 kWh/m² em 2 dias, até 02/10 (o último dia que a NASA publicou)"
    assert mes["sub"] == "2 dias, até 02/10" and mes["avisos"] == []


def test_dia_sem_leitura_no_meio_do_mes_e_dito_e_nao_vira_zero(leituras, nasa):
    tudo_lido(leituras)
    nasa(lei_nasa(serie_nasa(buracos={date(2026, 10, 1)})))
    mes = pagina()["irradiacao"]["mes"]
    assert mes["valor"] == "2,0" and mes["sub"] == "1 dia, até 02/10" and mes["avisos"] == ["1 dia sem leitura da NASA (01/10)"]
    assert "1 dia sem leitura da NASA (01/10)" in mes["texto"]


def test_mais_de_um_buraco_no_plural(leituras, nasa):
    tudo_lido(leituras)
    nasa(lei_nasa(serie_nasa(ate=date(2026, 10, 4), buracos={date(2026, 10, 1), date(2026, 10, 3)})))
    mes = pagina()["irradiacao"]["mes"]
    assert mes["avisos"] == ["2 dias sem leitura da NASA (01/10, 03/10)"] and mes["valor"] == "6,0"


def test_a_nasa_ainda_nao_publicou_nenhum_dia_do_mes(leituras, nasa):
    tudo_lido(leituras)
    nasa(lei_nasa(serie_nasa(ate=date(2026, 9, 28))))
    ir = pagina()["irradiacao"]
    assert ir["mes"]["valor"] == "—" and ir["mes"]["sub"] == "nenhum dia publicado"
    assert ir["mes"]["texto"] == "A NASA ainda não publicou nenhum dia de outubro (último dia publicado: 28/09)"
    assert ir["grafico"] is not None and ir["grafico"]["faixa"] is not None                          # o gráfico segue, com a faixa maior


def test_a_nasa_nao_publicou_nenhum_dia_da_janela_inteira(leituras, nasa):
    tudo_lido(leituras)
    nasa(lei_nasa(serie_nasa(ate=date(2026, 8, 1))))
    ir = pagina()["irradiacao"]
    assert ir["estado"] == "ok" and ir["grafico"] is None and ir["tabela"] == []
    assert ir["texto"] == "Prediction Of Worldwide Energy Resources, projeto da NASA (NASA POWER) · irradiação: lida às 15:00"
    assert ir["mes"]["texto"] == "A NASA não publicou nenhum dia nos últimos 40 dias" and ir["mes"]["valor"] == "—"


def test_a_nasa_fora_sem_nenhuma_leitura_boa(leituras, nasa):
    tudo_lido(leituras)
    nasa(L.Leitura(None, None, erro="HTTP 503"))
    ir = pagina()["irradiacao"]
    assert ir["estado"] == "fora" and ir["texto"] == "Prediction Of Worldwide Energy Resources, projeto da NASA (NASA POWER) · irradiação: fora agora; ainda sem leitura boa" and ir["erro"] == "HTTP 503"
    assert ir["grafico"] is None and ir["mes"] is None and ir["tabela"] == []
    assert pagina()["nivel"] == "sem"                                              # os alertas não dependem da NASA


def test_a_nasa_lendo_a_pagina_volta_em_10_s(leituras, nasa):
    tudo_lido(leituras)
    nasa(L.Leitura(None, None, erro=L.LENDO))
    v = pagina()
    assert v["irradiacao"]["estado"] == "lendo" and v["irradiacao"]["texto"].startswith("Lendo a irradiação do Prediction Of Worldwide Energy Resources, projeto da NASA (NASA POWER)") and v["recarrega_em"] == 10
    nasa(lei_nasa())
    assert pagina()["recarrega_em"] == 60


def test_fonte_de_alerta_lendo_tambem_encurta_a_recarga(leituras, nasa):
    nasa(lei_nasa())
    leituras(avisos=L.Leitura(None, None, erro=L.LENDO), focos=lei_focos(), risco=lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1)}))
    assert pagina()["recarrega_em"] == 10 and pagina()["lendo"] == ["avisos do Instituto Nacional de Meteorologia (INMET)"]


def test_a_nasa_velha_mostra_a_ultima_leitura_boa_com_a_hora(leituras, nasa):
    tudo_lido(leituras)
    velha = L.Leitura(serie_nasa(), REF.timestamp() - 3600 * 20, erro="tempo esgotado", velha=True)           # 19:00 de ontem
    nasa(velha)
    ir = pagina()["irradiacao"]
    assert ir["estado"] == "velha" and ir["texto"] == "Prediction Of Worldwide Energy Resources, projeto da NASA (NASA POWER) · irradiação: fora agora; última leitura boa às 05/10 19:00" and ir["erro"] == "tempo esgotado"
    assert ir["grafico"] is not None and ir["mes"]["valor"] == "3,0"                  # a série boa continua valendo, dita velha


def test_a_nasa_pela_metade_nunca_chega_aqui_formato_diferente_e_erro_do_cache(leituras, nasa):
    tudo_lido(leituras)
    nasa(L.Leitura(None, None, erro="a unidade da NASA POWER mudou (esperava kW-hr/m^2/day, veio MJ/m^2/day)"))
    ir = pagina()["irradiacao"]
    assert ir["estado"] == "fora" and "unidade" in ir["erro"] and ir["grafico"] is None


def test_a_comparacao_com_a_etm_e_proxima_etapa(leituras, nasa):
    tudo_lido(leituras)
    nasa(lei_nasa())
    etm = pagina()["etm"]
    assert etm["texto"] == "Comparação com a ETM: próxima etapa"
    assert "BD_Thopen" in etm["motivo"] and "BD_Performance" in etm["motivo"] and "GHI (kWh/m²)" in etm["motivo"]

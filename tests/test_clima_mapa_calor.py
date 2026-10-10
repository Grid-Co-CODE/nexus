"""Mapa de risco, as camadas de 09/10/2026 no modelo (`mapa.montar`): a camada de fundo (avisos, risco de fogo ou densidade de focos),
as de cima, o dia do risco, o filtro de cliente, os níveis e os eventos escondidos, o modo TV com o giro, a próxima releitura no ritmo
dos caches e a dica de cada usina com as fontes que pesaram, por extenso. Leituras prontas no lugar das fontes: sem rede."""
import json
import re
from datetime import datetime, timezone

import pytest

from nexus.performance.clima import calor as C
from nexus.performance.clima import fontes as F
from nexus.performance.clima import leitura as L
from nexus.performance.clima import mapa as M
from nexus.performance.clima import visao as V

from clima_mapa_mundo import (ALFA, BETA, DELTA, EPSILON, GAMA, LIDO, REF, TETA, aviso, cadastro, foco_a, foco_em,
                              instalar_leituras, lei_avisos, lei_focos, lei_grade, lei_risco, montar, mundo_completo,
                              mundo_de_usinas, risco_baixo, tudo_instalado, usina)

UTC = timezone.utc
INMET, INPE = F.extenso("inmet"), F.extenso("inpe")


@pytest.fixture
def leituras(monkeypatch):
    return instalar_leituras(monkeypatch)


def seco_no_leste(lat, lon):
    """O risco do teste: crítico a leste de -41,2, mínimo a oeste; sem dado numa faixa (cidade) em volta de -43. A divisa cai na borda
    de um quadrado de 0,16 grau (o Brasil junta 2 x 2 blocos de 0,08 a partir de -46): um quadrado que pegasse os dois lados teria a
    média dos dois (médio), e é assim que tem de ser."""
    if -43.2 < lon < -42.8:
        return None
    return 0.97 if lon > -41.2 else 0.10


# ── a camada de fundo: risco de fogo ─────────────────────────────────────────────────────────────────────────────────

def test_o_risco_de_fogo_desenha_as_classes_com_a_fonte_a_hora_e_a_escala(leituras):
    chamadas = tudo_instalado(leituras)
    leituras(avisos=lei_avisos(), focos=lei_focos(), risco=lei_risco(risco_baixo()), grade=lei_grade(seco_no_leste))
    m = montar(fundo="risco")
    cr = m["calor_risco"]
    assert cr["estado"] == "ok" and m["fundos_no_svg"] == ["risco"] and m["camada_avisos"]["grupos"] == []
    com_caminho = {c["id"] for c in cr["classes"] if c["d"]}
    assert com_caminho == {1, 5}                                                 # só o que existe vira cor
    assert [c["rotulo"] for c in cr["classes"]] == ["Mínimo", "Baixo", "Médio", "Alto", "Crítico"]
    assert all(c["faixa"] for c in cr["classes"]) and cr["sem_dado_pct"] != ""
    assert cr["texto"].startswith(f"{INPE} · risco de fogo: previsão para hoje, do arquivo de 07/10 às 06:32 · lido às 15:00")
    assert cr["qualifica"] == []
    assert [d["nome"] for d in cr["dias"]] == ["hoje", "amanhã", "sex 09/10", "sáb 10/10"] and cr["dias"][0]["atual"]
    assert cr["lado_km"] == round(0.16 * C.KM_POR_GRAU)                          # 2 x 2 blocos-base no Brasil inteiro
    assert m["divisas"] and "M" in m["divisas"]                                  # as divisas vêm por cima do calor
    assert "grade0" in chamadas


def test_a_regiao_desenha_o_risco_em_quadrados_menores(leituras):
    leituras(avisos=lei_avisos(), focos=lei_focos(), risco=lei_risco(risco_baixo()), grade=lei_grade(seco_no_leste))
    assert montar(fundo="risco", regiao="nordeste")["calor_risco"]["lado_km"] == round(0.08 * C.KM_POR_GRAU)


def test_o_risco_lendo_diz_lendo_nao_desenha_e_a_tela_volta_em_10_s(leituras):
    leituras(avisos=lei_avisos(), focos=lei_focos(), risco=lei_risco(risco_baixo()), grade=L.Leitura(None, None, erro=L.LENDO))
    m = montar(fundo="risco")
    assert m["calor_risco"]["estado"] == "lendo" and m["calor_risco"]["classes"] == []
    assert "lendo a área do Brasil" in m["calor_risco"]["texto"] and m["proxima_s"] == V.RECARGA_LENDO_S
    assert m["divisas"] == ""


def test_o_risco_fora_diz_fora_e_a_ultima_boa_vem_com_a_hora_dela(leituras):
    leituras(avisos=lei_avisos(), focos=lei_focos(), risco=lei_risco(risco_baixo()), grade=L.Leitura(None, None, erro="HTTP 503"))
    cr = montar(fundo="risco")["calor_risco"]
    assert cr["estado"] == "fora" and cr["classes"] == [] and "fora agora; ainda sem leitura boa" in cr["texto"]
    velha = lei_grade(seco_no_leste, erro="HTTP 503", velha=True)
    velha.lido_em = LIDO - 3600
    leituras(avisos=lei_avisos(), focos=lei_focos(), risco=lei_risco(risco_baixo()), grade=velha)
    cr = montar(fundo="risco")["calor_risco"]
    assert cr["estado"] == "ok" and "última leitura boa às 14:00" in cr["texto"] and "dado de 14:00" in cr["qualifica"]


def test_a_previsao_de_ontem_fica_qualificada_e_o_hoje_e_o_dia_seguinte_do_arquivo(leituras):
    ontem = datetime(2026, 10, 6, 9, 32, tzinfo=UTC)
    leituras(avisos=lei_avisos(), focos=lei_focos(), risco=lei_risco(risco_baixo(), arquivos={0: ontem}),
             grade={1: lei_grade(seco_no_leste, modificado=ontem), 0: lei_grade(seco_no_leste, modificado=ontem)})
    cr = montar(fundo="risco")["calor_risco"]
    assert cr["dia"] == 1 and [d["nome"] for d in cr["dias"]][:2] == ["ontem", "hoje"]   # o T1 de ontem é a previsão de hoje
    assert "previsão de 06/10" in cr["qualifica"]


def test_o_dia_escolhido_le_o_arquivo_daquele_dia(leituras):
    chamadas = leituras(avisos=lei_avisos(), focos=lei_focos(), risco=lei_risco(risco_baixo()),
                        grade={2: lei_grade(seco_no_leste)})
    cr = montar(fundo="risco", dia=2)["calor_risco"]
    assert "grade2" in chamadas and cr["dia"] == 2 and cr["dia_nome"] == "sex 09/10"
    assert "previsão para sex 09/10" in cr["texto"]


def test_sem_o_risco_no_fundo_o_arquivo_grande_do_inpe_nem_e_lido(leituras):
    chamadas = tudo_instalado(leituras)
    montar()
    assert not [c for c in chamadas if c.startswith("grade")]


# ── a camada de fundo: densidade de focos ────────────────────────────────────────────────────────────────────────────

def test_a_densidade_desenha_onde_ha_foco_conta_os_do_recorte_e_diz_o_raio(leituras):
    focos = [foco_a(1.0 + i * 0.2, DELTA) for i in range(10)] + [foco_em(-9.0, -40.0)]
    tudo_instalado(leituras, focos=lei_focos(*focos))
    m = montar(fundo="densidade")
    cd = m["calor_densidade"]
    assert cd["estado"] == "ok" and cd["n_focos"] == 11 and cd["raio_km"] == C.RAIO_KM_BRASIL
    assert any(c["d"] for c in cd["classes"]) and cd["pico_um"] == "0,38"         # 3 / (pi x 50²) x 1.000
    assert f"Calculada no Nexus com os 11 focos da última hora do {INPE}" in cd["texto"]
    assert "cada foco pesa até 50 km" in cd["texto"]
    sudeste = montar(fundo="densidade", regiao="sudeste")["calor_densidade"]
    assert sudeste["raio_km"] == C.RAIO_KM and sudeste["n_focos"] == 10 and sudeste["pico_um"] == "1,5"


def test_sem_leitura_dos_focos_a_densidade_some_e_diz_por_que(leituras):
    leituras(avisos=lei_avisos(), focos=L.Leitura(None, None, erro="HTTP 500"), risco=lei_risco(risco_baixo()))
    cd = montar(fundo="densidade")["calor_densidade"]
    assert cd["estado"] == "fora" and cd["classes"] == [] and f"Sem leitura boa dos focos de queimada do {INPE}" in cd["texto"]


def test_nenhum_foco_e_dado_e_nao_vira_cor(leituras):
    tudo_instalado(leituras, focos=lei_focos())
    cd = montar(fundo="densidade")["calor_densidade"]
    assert cd["estado"] == "ok" and not any(c["d"] for c in cd["classes"]) and cd["n_focos"] == 0


# ── nenhuma camada, o modo TV e o giro ───────────────────────────────────────────────────────────────────────────────

def test_sem_camada_de_fundo_nada_de_area_e_o_resto_continua(leituras):
    chamadas = tudo_instalado(leituras)
    m = montar(fundo="nenhum")
    assert m["fundos_no_svg"] == [] and m["calor_risco"] is None and m["calor_densidade"] is None and m["divisas"] == ""
    assert len(m["usinas"]) == 6 and sorted(c for c in chamadas if not c.startswith("grade")) == ["avisos", "firms", "focos", "risco"]


def test_fundo_desconhecido_cai_nos_avisos(leituras):
    tudo_instalado(leituras)
    assert montar(fundo="marte")["fundo"] == "avisos"


def test_no_modo_tv_com_giro_as_tres_camadas_vem_prontas(leituras):
    leituras(avisos=lei_avisos(aviso(2, "Tempestade", ALFA)), focos=lei_focos(foco_a(1.0, DELTA)), risco=lei_risco(risco_baixo()),
             grade=lei_grade(seco_no_leste))
    m = montar(tv=True, girar=20)
    assert m["fundos_no_svg"] == list(M.GIRO) and m["girar"] == 20
    assert m["calor_risco"]["estado"] == "ok" and m["calor_densidade"]["estado"] == "ok"
    assert m["dados_js"]["giro"] == list(M.GIRO) and m["dados_js"]["girar"] == 20
    assert montar(girar=20)["girar"] is None                                     # o giro é só do modo TV


# ── a próxima releitura, no ritmo dos caches ─────────────────────────────────────────────────────────────────────────

def test_a_proxima_leitura_e_o_vencimento_do_primeiro_cache_mais_a_folga():
    agora = 1000.0
    lendo = L.Leitura(None, None, erro=L.LENDO)
    com = [L.Leitura("a", agora, vence_em=agora + 1800), L.Leitura("f", agora, vence_em=agora + 600)]
    assert V.proxima_leitura_s(com, agora) == 600 + V.FOLGA_PROXIMA_S
    assert V.proxima_leitura_s(com + [lendo], agora) == V.RECARGA_LENDO_S          # a leitura em curso não vai de novo à rede
    assert V.proxima_leitura_s([L.Leitura("x", agora)], agora) == V.RECARGA_S      # sem data: o minuto de sempre
    assert V.proxima_leitura_s([L.Leitura("x", agora, vence_em=agora - 50)], agora) == V.RECARGA_LENDO_S   # nunca menos de 10 s
    assert V.proxima_leitura_s([L.Leitura("x", agora, vence_em=agora + 99999)], agora) == V.PROXIMA_MAX_S


def test_o_cache_diz_quando_vence_a_leitura_boa_e_a_janela_da_falha():
    relogio = [5000.0]
    c = L.Cache(600, relogio=lambda: relogio[0])
    boa = c.ler(lambda: "dado")
    assert boa.vence_em == 5600.0
    relogio[0] = 5700.0

    def falha():
        raise RuntimeError("fora")
    velha = c.ler(falha)
    assert velha.velha and velha.vence_em == 5700.0 + L.FALHA_TTL_S


def test_o_mapa_marca_a_proxima_leitura_pelas_fontes_que_usou(leituras):
    leituras(avisos=L.Leitura({"avisos": [], "ignorados": [], "lidos": 0}, LIDO, vence_em=LIDO + 1800),
             focos=L.Leitura({"focos": [], "arquivos": ["a"], "falhos": [], "ate": REF, "linhas_ruins": 0}, LIDO,
                             vence_em=LIDO + 600),
             risco=lei_risco(risco_baixo()))
    m = M.montar({}, cadastro=cadastro(*mundo_de_usinas()), ref=REF)
    assert m["proxima_s"] == V.proxima_leitura_s([L.Leitura(1, LIDO, vence_em=LIDO + 600)])


# ── o estado da tela no endereço ─────────────────────────────────────────────────────────────────────────────────────

def test_o_estado_vem_do_endereco_validado_e_o_que_nao_existe_cai_no_padrao():
    e = M.estado_da_tela({"fundo": "Risco", "ver": "usinas,focos,lixo", "dia": "2", "cliente": " X ", "ocultar": "sem,nada",
                          "sem_eventos": "baixa-umidade,<script>", "tv": "1", "girar": "30", "regiao": "sul"})
    assert e == {"regiao": "sul", "fundo": "risco", "ver": frozenset({"usinas", "focos"}), "dia": 2, "cliente": "X",
                 "ocultar": frozenset({"sem"}), "sem_eventos": frozenset({"baixa-umidade"}), "tv": True, "girar": 30}
    assert M.estado_da_tela({"dia": "9", "girar": "5", "fundo": "x"}) == {
        "regiao": "", "fundo": "avisos", "ver": None, "dia": None, "cliente": "", "ocultar": frozenset(),
        "sem_eventos": frozenset(), "tv": False, "girar": None}
    assert M.estado_da_tela({"ver": ""})["ver"] == frozenset()                     # tudo desligado é escolha, não padrão


def test_os_links_levam_o_resto_do_estado_e_o_padrao_e_o_endereco_puro(leituras):
    tudo_instalado(leituras)
    padrao = montar()
    assert padrao["links"]["regiao"]["brasil"] == {} and padrao["links"]["regiao"]["sul"] == {"regiao": "sul"}
    assert padrao["links"]["fundo"]["risco"] == {"fundo": "risco"} and padrao["links"]["ver"]["focos"] == {"ver": "usinas,siglas"}
    m = montar(fundo="risco", regiao="sul", ocultar=frozenset({"sem"}))
    assert m["links"]["regiao"]["norte"] == {"regiao": "norte", "fundo": "risco", "ocultar": "sem"}
    assert m["links"]["ocultar"]["sem"] == {"regiao": "sul", "fundo": "risco"}       # clicar de novo mostra
    assert m["links"]["tv"]["tv"] == 1 and "tv" not in m["links"]["sair_tv"]


# ── a dica da usina e o filtro de cliente ────────────────────────────────────────────────────────────────────────────

def test_a_dica_diz_o_que_pesou_com_o_nome_da_fonte_por_extenso(leituras):
    mundo_completo(leituras)
    d = montar()["dados_js"]["usinas"]
    alfa, delta, teta = d["1"], d["4"], d["6"]
    assert alfa["v"] == "agir" and alfa["f"][0][0] == INMET and alfa["f"][0][1].startswith("Vendaval (Grande Perigo)")
    assert delta["f"][0][0] == INPE and "foco de queimada a 1,0 km, visto pelo satélite GOES-19" in delta["f"][0][1]
    assert d["5"]["f"] == [[INPE, "risco de fogo alto hoje (até 0,80)"]]
    assert teta["v"] == "sem" and teta["f"][0][0] == "" and teta["f"][0][1].startswith("Nenhum aviso, nenhum foco a até 5 km")
    assert json.loads(json.dumps(d))                                             # vira JSON sem perder nada


def test_a_dica_e_os_dados_da_pagina_nao_levam_numero_de_coordenada(leituras):
    mundo_completo(leituras)
    texto = json.dumps(montar()["dados_js"], ensure_ascii=False)
    assert not re.search(r"\d+\.\d{3,}", texto)
    for pos in (ALFA, BETA, GAMA, DELTA, EPSILON, TETA):
        assert f"{abs(pos[0]):.3f}"[:6] not in texto and f"{abs(pos[1]):.3f}"[:6] not in texto


def test_sem_leitura_completa_a_dica_nao_diz_nada_previsto(leituras):
    leituras(avisos=L.Leitura(None, None, erro="HTTP 500"), focos=lei_focos(), risco=lei_risco(risco_baixo()))
    teta = montar()["dados_js"]["usinas"]["6"]
    assert teta["v"] == "nx" and "Sem leitura de avisos do" in teta["f"][0][1]


def test_o_filtro_de_cliente_vale_no_mapa_e_o_risco_le_todas_as_usinas(leituras, monkeypatch):
    pontos = []
    tudo_instalado(leituras)
    original = L.risco
    monkeypatch.setattr(L, "risco", lambda config, p, sessao=None: pontos.append(list(p)) or original(config, p, sessao))
    cad = cadastro(usina("1", "Usina Alfa", ALFA, cliente="Cliente X"), usina("2", "Usina Beta", BETA, cliente="Cliente Y"))
    m = M.montar({}, cadastro=cad, ref=REF, cliente="Cliente Y")
    assert [u["nome"] for u in m["usinas"]] == ["Usina Beta"] and m["cliente"] == "Cliente Y" and m["n_usinas"] == 1
    assert len(pontos[0]) == 2                                                   # o risco é lido para as duas
    assert M.montar({}, cadastro=cad, ref=REF, cliente="Inventado")["cliente"] == ""


def test_os_eventos_dos_avisos_vao_para_a_legenda_e_o_escondido_vem_marcado(leituras):
    tudo_instalado(leituras, avisos=lei_avisos(aviso(1, "Baixa Umidade", ALFA), aviso(2, "Baixa Umidade", BETA),
                                               aviso(2, "Tempestade", GAMA)))
    av = montar(sem_eventos=frozenset({"baixa-umidade"}))["camada_avisos"]
    assert [(e["nome"], e["n"], e["agir"], e["oculto"]) for e in av["eventos"]] == [
        ("Tempestade", 1, True, False), ("Baixa umidade", 2, False, True)]
    marcados = [i for g in av["grupos"] for i in g["itens"] if i["oculto"]]
    assert len(marcados) == 2 and {i["ev"] for i in marcados} == {"baixa-umidade"}

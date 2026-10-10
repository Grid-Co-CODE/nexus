"""Mapa de risco: as camadas do SVG (`mapa.montar`), com leituras prontas no lugar das fontes. Sem rede e sem Flask.

O mundo inventado (seis usinas, cada uma com o seu motivo de nível, e avisos e focos postos em cima delas) mora em
`tests/clima_mapa_mundo.py`, para a tela usar o mesmo."""
import random
import re
from datetime import datetime, timedelta, timezone

import pytest

from nexus.performance.clima import alertas as A
from nexus.performance.clima import geometria
from nexus.performance.clima import leitura as L
from nexus.performance.clima import mapa as M
from nexus.performance.clima import visao as V
from nexus.performance.clima.fontes import Foco
from nexus.performance.clima.usinas import Usina

from clima_mapa_mundo import (ALFA, BETA, DELTA, EPSILON, GAMA, LIDO, REF, TETA, UM_GRAU, aviso, cadastro, dias, foco_a,
                              foco_em, instalar_leituras, lei_avisos, lei_focos, lei_risco, montar, mundo_completo, mundo_de_usinas,
                              por_nome, quebrar_contorno, risco_baixo, tudo_instalado, usina)

UTC = timezone.utc


@pytest.fixture
def leituras(monkeypatch):
    return instalar_leituras(monkeypatch)


# ── os focos dentro do raio, para os anéis ───────────────────────────────────────────────────────────────────────────

def _foco(lat, lon):
    return Foco(lat, lon, "GOES-19", datetime(2026, 10, 7, 17, 50, tzinfo=UTC))


def test_no_raio_traz_cada_foco_com_a_sua_distancia_e_deixa_de_fora_o_que_passa_do_raio():
    idx = A.IndiceFocos([_foco(-10 + 1.0 / UM_GRAU, -40), _foco(-10 + 4.9 / UM_GRAU, -40), _foco(-10 + 5.1 / UM_GRAU, -40)])
    achados = idx.no_raio(-10, -40)
    assert sorted(round(km, 1) for km, _ in achados) == [1.0, 4.9]
    assert all(isinstance(f, Foco) for _, f in achados)
    assert A.IndiceFocos([]).no_raio(-10, -40) == [] and A.IndiceFocos([_foco(-9, -40)]).no_raio(-10, -40) == []


def test_no_raio_confere_com_a_conta_por_forca_bruta_e_o_perto_continua_o_mesmo():
    r = random.Random(70101)
    focos = [_foco(r.uniform(-12, -8), r.uniform(-44, -40)) for _ in range(2500)]
    idx = A.IndiceFocos(focos)
    for _ in range(30):
        lat, lon = r.uniform(-12, -8), r.uniform(-44, -40)
        for raio in (A.FOCO_KM, 12.0):
            bruto = sorted(round(geometria.distancia_km(lat, lon, f.lat, f.lon), 6) for f in focos
                           if geometria.distancia_km(lat, lon, f.lat, f.lon) <= raio)
            assert sorted(round(km, 6) for km, _ in idx.no_raio(lat, lon, raio)) == bruto
            resumo = idx.perto(lat, lon, raio)
            assert (resumo["n"] if resumo else 0) == len(bruto)
            if bruto:
                assert resumo["km"] == pytest.approx(bruto[0], abs=1e-6)


# ── o nível de cada usina, pelas regras de alertas.py ────────────────────────────────────────────────────────────────

CASOS = [
    ("foco a 4,9 km", dict(focos=lambda: lei_focos(foco_a(4.9, ALFA))), "agir"),
    ("aviso Grande Perigo", dict(avisos=lambda: lei_avisos(aviso(3, "Onda de Calor", ALFA))), "agir"),
    ("Perigo de evento que estraga usina", dict(avisos=lambda: lei_avisos(aviso(2, "Tempestade", ALFA))), "agir"),
    ("Perigo de evento fora da lista", dict(avisos=lambda: lei_avisos(aviso(2, "Baixa Umidade", ALFA))), "atencao"),
    ("Perigo Potencial, mesmo de evento que estraga", dict(avisos=lambda: lei_avisos(aviso(1, "Vendaval", ALFA))), "atencao"),
    ("aviso que ainda vai comecar", dict(avisos=lambda: lei_avisos(aviso(1, "Baixa Umidade", ALFA, inicio=REF + timedelta(hours=20),
                                                                          quando="futuro"))), "atencao"),
    ("risco de fogo alto em D+3", dict(risco=lambda: lei_risco({"1": dias(0.1, 0.1, 0.1, 0.8)})), "atencao"),
    ("risco de fogo critico hoje", dict(risco=lambda: lei_risco({"1": dias(0.99, 0.1, 0.1, 0.1)})), "atencao"),
    ("risco de fogo medio", dict(risco=lambda: lei_risco({"1": dias(0.6, 0.6, 0.6, 0.6)})), "sem"),
    ("foco a 5,1 km", dict(focos=lambda: lei_focos(foco_a(5.1, ALFA))), "sem"),
    ("nada", dict(), "sem"),
]


@pytest.mark.parametrize("motivo,fontes,esperado", CASOS, ids=[c[0] for c in CASOS])
def test_o_nivel_de_cada_usina_vem_da_regra_dos_tres_niveis(leituras, motivo, fontes, esperado):
    leituras(avisos=fontes["avisos"]() if "avisos" in fontes else lei_avisos(),
             focos=fontes["focos"]() if "focos" in fontes else lei_focos(),
             risco=fontes["risco"]() if "risco" in fontes else lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1)}))
    m = montar(cadastro=cadastro(usina("1", "Usina Alfa", ALFA)))
    assert [(u["nome"], u["nivel"]) for u in m["usinas"]] == [("Usina Alfa", esperado)], motivo


def test_a_contagem_por_nivel_e_a_do_que_esta_no_recorte(leituras):
    tudo_instalado(leituras,
                   avisos=lei_avisos(aviso(3, "Vendaval", ALFA), aviso(2, "Baixa Umidade", BETA),
                                     aviso(1, "Onda de Calor", GAMA, inicio=REF + timedelta(days=1), quando="futuro")),
                   focos=lei_focos(foco_a(1.0, DELTA)),
                   risco=lei_risco({**risco_baixo(), "5": dias(0.8, 0.1, 0.1, 0.1)}))
    m = montar()
    assert m["contagem"] == {"agir": 2, "atencao": 3, "sem": 1, "nx": 0}
    assert {u["nome"]: u["nivel"] for u in m["usinas"]} == {
        "Usina Alfa": "agir", "Usina Beta": "atencao", "Usina Gama": "atencao", "Usina Delta": "agir",
        "Usina Epsilon": "atencao", "Usina Teta": "sem"}
    assert m["rotulo_sem"] == "Sem alerta"


# ── as camadas ───────────────────────────────────────────────────────────────────────────────────────────────────────

def test_o_brasil_desenha_cada_camada_com_a_sua_contagem(leituras):
    mundo_completo(leituras)
    m = montar()
    av = m["camada_avisos"]
    assert av["estado"] == "ok" and av["n_vigor"] == 2 and av["n_futuros"] == 1
    assert [(g["nivel"], g["futuro"], len(g["itens"])) for g in av["grupos"]] == [(2, False, 1), (3, False, 1), (1, True, 1)]
    fo = m["camada_focos"]
    assert fo["estado"] == "ok" and fo["n"] == 4 and fo["d"].count("M") == 4
    assert re.fullmatch(r"(M-?\d+(\.\d)? -?\d+(\.\d)?h\.01){4}", fo["d"]), fo["d"]       # cada foco, um ponto de ponta redonda
    assert fo["n_perto"] == 2 and len(fo["aneis"]) == 2                       # os dois a até 5 km da Delta
    assert len(m["usinas"]) == 6 and m["n_no_recorte"] == 6 and m["fora_do_recorte"] == 0
    assert len(m["ufs"]) == 27 and m["viewbox"] == M.vista().viewbox


def test_a_regiao_so_desenha_o_que_cai_nela(leituras):
    mundo_completo(leituras)
    ne = montar(regiao="nordeste")
    assert sorted(u["nome"] for u in ne["usinas"]) == ["Usina Alfa", "Usina Beta"]
    assert ne["fora_do_recorte"] == 4 and ne["contagem"] == {"agir": 1, "atencao": 1, "sem": 0, "nx": 0}
    assert (ne["camada_avisos"]["n_vigor"], ne["camada_avisos"]["n_futuros"]) == (2, 0)
    assert ne["camada_focos"]["n"] == 1 and ne["camada_focos"]["n_perto"] == 0       # só o foco de -9, -40 está no Nordeste
    sul = montar(regiao="sul")
    assert [u["nome"] for u in sul["usinas"]] == ["Usina Gama"]
    assert (sul["camada_avisos"]["n_vigor"], sul["camada_avisos"]["n_futuros"]) == (0, 1)
    assert sul["camada_focos"]["n"] == 0 and sul["viewbox"] == M.vista("sul").viewbox
    assert montar(regiao="sul")["regiao"] == "sul" and montar(regiao="nada")["regiao"] == "brasil"


def test_as_regioes_do_seletor_dizem_qual_e_a_atual(leituras):
    mundo_completo(leituras)
    m = montar(regiao="sudeste")
    assert [r["id"] for r in m["regioes"]] == ["brasil", "norte", "nordeste", "centro-oeste", "sudeste", "sul"]
    assert [r["nome"] for r in m["regioes"]][:2] == ["Brasil", "Norte"]
    assert [r["id"] for r in m["regioes"] if r["atual"]] == ["sudeste"]


def test_aviso_vencido_nao_e_desenhado_nem_contado(leituras):
    tudo_instalado(leituras, avisos=lei_avisos(aviso(3, "Vendaval", ALFA, fim=REF - timedelta(minutes=1)),
                                               aviso(2, "Tempestade", BETA)))
    m = montar()
    assert m["camada_avisos"]["n_vigor"] == 1 and len(m["camada_avisos"]["grupos"]) == 1
    assert por_nome(m)["Usina Alfa"]["nivel"] == "sem"                        # o vencido também não conta para o nível


def test_aviso_futuro_vai_em_grupo_proprio_e_o_em_vigor_do_mesmo_nivel_vai_noutro(leituras):
    tudo_instalado(leituras, avisos=lei_avisos(
        aviso(2, "Chuvas Intensas", ALFA), aviso(2, "Chuvas Intensas", BETA, inicio=REF + timedelta(hours=3), quando="futuro")))
    grupos = montar()["camada_avisos"]["grupos"]
    assert [(g["nivel"], g["futuro"]) for g in grupos] == [(2, False), (2, True)]


def test_a_ordem_dos_grupos_de_aviso_deixa_o_mais_grave_por_cima(leituras):
    tudo_instalado(leituras, avisos=lei_avisos(
        aviso(3, "Vendaval", ALFA), aviso(1, "Onda de Calor", BETA), aviso(2, "Granizo", GAMA)))
    assert [g["nivel"] for g in montar()["camada_avisos"]["grupos"]] == [1, 2, 3]


def test_cada_aviso_leva_o_titulo_com_evento_severidade_e_vigencia_e_o_caminho(leituras):
    tudo_instalado(leituras, avisos=lei_avisos(aviso(2, "Tempestade", ALFA)))
    item = montar()["camada_avisos"]["grupos"][0]["itens"][0]
    assert item["titulo"] == "Tempestade · Perigo · em vigor, até 23:00"
    assert item["d"].startswith("M") and item["d"].endswith("z")


def test_aviso_fora_do_recorte_nao_pesa_a_pagina(leituras):
    tudo_instalado(leituras, avisos=lei_avisos(aviso(3, "Vendaval", GAMA)))
    assert montar(regiao="norte")["camada_avisos"]["grupos"] == []


def test_aviso_com_buraco_vira_um_caminho_so_com_dois_subcaminhos(leituras):
    geo = {"type": "Polygon", "coordinates": [
        [[-42, -8], [-41, -8], [-41, -7], [-42, -7], [-42, -8]], [[-41.8, -7.8], [-41.8, -7.2], [-41.2, -7.2], [-41.2, -7.8], [-41.8, -7.8]]]}
    tudo_instalado(leituras, avisos=lei_avisos(aviso(2, "Vendaval", ALFA, geo=geo)))
    d = montar()["camada_avisos"]["grupos"][0]["itens"][0]["d"]
    assert d.count("M") == 2 and d.count("z") == 2


def test_multipolygon_do_inmet_desenha_todos_os_pedacos(leituras):
    geo = {"type": "MultiPolygon", "coordinates": [[[[-42, -8], [-41, -8], [-41, -7], [-42, -8]]],
                                                   [[[-52, -28], [-51, -28], [-51, -27], [-52, -28]]]]}
    tudo_instalado(leituras, avisos=lei_avisos(aviso(2, "Vendaval", ALFA, geo=geo)))
    assert montar()["camada_avisos"]["grupos"][0]["itens"][0]["d"].count("M") == 2


def test_focos_no_mesmo_ponto_do_desenho_viram_um_so_e_a_contagem_continua_a_da_fonte(leituras):
    juntos = [foco_em(-9.0, -40.0, "GOES-19"), foco_em(-9.0001, -40.0001, "NOAA-21"), foco_em(-9.0002, -40.0, "MSG-03")]
    tudo_instalado(leituras, focos=lei_focos(*juntos, foco_em(-12.0, -45.0)))
    fo = montar()["camada_focos"]
    assert fo["n"] == 4 and fo["d"].count("M") == 2


def test_anel_so_para_foco_a_ate_5_km_de_alguma_usina_e_cada_posicao_conta_uma_vez(leituras):
    perto = foco_a(4.9, DELTA, "GOES-19")
    mesmo_lugar = Foco(perto.lat, perto.lon, "NOAA-21", perto.data)               # outro satélite, o mesmo ponto
    longe = foco_a(5.2, TETA)
    tudo_instalado(leituras, focos=lei_focos(perto, mesmo_lugar, longe))
    fo = montar()["camada_focos"]
    assert fo["n"] == 3 and fo["n_perto"] == 1 and len(fo["aneis"]) == 1
    assert por_nome(montar())["Usina Delta"]["nivel"] == "agir" and por_nome(montar())["Usina Teta"]["nivel"] == "sem"


def test_foco_perto_de_usina_de_outra_regiao_nao_aparece_na_regiao_que_nao_o_mostra(leituras):
    tudo_instalado(leituras, focos=lei_focos(foco_a(1.0, DELTA)))
    assert montar(regiao="sul")["camada_focos"]["aneis"] == [] and montar(regiao="sudeste")["camada_focos"]["n_perto"] == 1


def test_o_anel_e_o_ponto_do_foco_cai_onde_a_projecao_poe_o_foco(leituras):
    f = foco_a(1.0, DELTA)
    tudo_instalado(leituras, focos=lei_focos(f))
    v = M.vista()
    x, y = v.ponto(f.lat, f.lon)
    anel = montar()["camada_focos"]["aneis"][0]
    assert (float(anel["x"]), float(anel["y"])) == pytest.approx((x, y), abs=0.06)


def test_usina_cai_onde_a_projecao_a_poe(leituras):
    tudo_instalado(leituras)
    v = M.vista("sudeste")
    x, y = v.ponto(*DELTA)
    u = por_nome(montar(regiao="sudeste"))["Usina Delta"]
    assert (float(u["x"]), float(u["y"])) == pytest.approx((x, y), abs=0.06)


def test_a_ordem_de_desenho_deixa_o_que_pede_acao_por_cima(leituras):
    mundo_completo(leituras)
    niveis = [u["nivel"] for u in montar()["usinas"]]
    ordem = {"nx": 0, "sem": 1, "atencao": 2, "agir": 3}
    assert niveis == sorted(niveis, key=ordem.get)
    assert niveis[0] == "sem" and niveis[-1] == "agir"


def test_o_ponto_do_nivel_que_pede_acao_e_maior(leituras):
    mundo_completo(leituras)
    r = {u["nivel"]: float(u["r"]) for u in montar()["usinas"]}
    assert r["agir"] > r["atencao"] > r["sem"] > 0


# ── o link e o título de cada usina ──────────────────────────────────────────────────────────────────────────────────

def test_cada_usina_aponta_para_a_pagina_dela_com_o_id_escapado(leituras):
    tudo_instalado(leituras)
    m = montar(cadastro=cadastro(usina("1", "A", ALFA), usina("a/b c?x=1#y", "B", BETA), usina("12ª", "C", GAMA)))
    hrefs = {u["nome"]: u["href"] for u in m["usinas"]}
    assert hrefs["A"] == "/t/performance/clima/usina/1"
    assert hrefs["B"] == "/t/performance/clima/usina/a%2Fb%20c%3Fx%3D1%23y"
    assert hrefs["C"] == "/t/performance/clima/usina/12%C2%AA"


def test_o_titulo_diz_nome_cliente_nivel_e_o_motivo(leituras):
    tudo_instalado(leituras, avisos=lei_avisos(aviso(3, "Vendaval", ALFA)), focos=lei_focos(foco_a(1.2, ALFA, "GOES-19")))
    t = por_nome(montar())["Usina Alfa"]["titulo"]
    assert t.splitlines()[:3] == ["Usina Alfa", "Cliente: Cliente X", "Nível: Agir agora"]
    assert "foco de queimada a 1,2 km" in t and "Vendaval (Grande Perigo, em vigor, até 23:00)" in t
    assert t.splitlines()[3].startswith("Motivo: foco de queimada a 1,2 km; Vendaval")        # o que manda agir vem primeiro


def test_o_motivo_de_atencao_lista_os_avisos_e_os_dias_do_risco(leituras):
    tudo_instalado(leituras, avisos=lei_avisos(aviso(2, "Baixa Umidade", ALFA), aviso(1, "Onda de Calor", ALFA)),
                   risco=lei_risco({"1": dias(0.8, 0.1, 0.99, 0.1)}))
    t = por_nome(montar(cadastro=cadastro(usina("1", "Usina Alfa", ALFA))))["Usina Alfa"]["titulo"]
    assert "Nível: Atenção" in t
    assert "Baixa Umidade (Perigo, em vigor, até 23:00)" in t and "Onda de Calor (Perigo Potencial" in t
    assert "risco de fogo crítico (Hoje, D+2)" in t


def test_o_motivo_de_quem_nao_tem_alerta_diz_que_nao_ha_aviso_foco_nem_risco_alto(leituras):
    tudo_instalado(leituras)
    t = por_nome(montar())["Usina Teta"]["titulo"]
    assert "Nível: Sem alerta" in t and "Motivo: nenhum aviso, foco a até 5 km nem risco de fogo alto" in t


def test_o_titulo_corta_a_lista_de_motivos_e_diz_quantos_ficaram_de_fora(leituras):
    muitos = [aviso(1, f"Evento {i}", ALFA, id_=i) for i in range(6)]
    tudo_instalado(leituras, avisos=lei_avisos(*muitos))
    motivo = por_nome(montar())["Usina Alfa"]["titulo"].splitlines()[3]
    assert motivo.count("Evento") == 3 and motivo.endswith("e mais 3")


def test_o_motivo_de_agir_nunca_perde_o_que_manda_agir_para_o_corte_da_lista(leituras):
    # Cinco avisos de Baixa Umidade (Perigo, que só pede atenção) começaram ANTES da Tempestade (Perigo, que manda agir): na
    # ordem do INMET a Tempestade ficaria em sexto, e o "e mais 3" a esconderia justo da usina que está em "Agir agora" por ela.
    antes = [aviso(2, "Baixa Umidade", ALFA, inicio=REF - timedelta(hours=10 - i), id_=i) for i in range(5)]
    tempestade = aviso(2, "Tempestade", ALFA, inicio=REF - timedelta(hours=1), id_="t")
    tudo_instalado(leituras, avisos=lei_avisos(*antes, tempestade))
    u = por_nome(montar())["Usina Alfa"]
    assert u["nivel"] == "agir"
    assert u["titulo"].splitlines()[3].startswith("Motivo: Tempestade (Perigo")


@pytest.mark.parametrize("n_avisos,resto", [(2, None), (3, None), (4, 1), (5, 2)])
def test_o_corte_do_motivo_so_acontece_acima_de_tres_e_conta_certo(leituras, n_avisos, resto):
    tudo_instalado(leituras, avisos=lei_avisos(*[aviso(1, f"Evento {i}", ALFA, id_=i) for i in range(n_avisos)]))
    motivo = por_nome(montar())["Usina Alfa"]["titulo"].splitlines()[3]
    assert motivo.count("Evento") == min(n_avisos, 3)
    assert (f"e mais {resto}" in motivo) if resto else ("e mais" not in motivo)


def test_o_titulo_nao_repete_o_mesmo_aviso_escrito_duas_vezes(leituras):
    tudo_instalado(leituras, avisos=lei_avisos(aviso(2, "Baixa Umidade", ALFA, id_=1), aviso(2, "Baixa Umidade", ALFA, id_=2)))
    assert por_nome(montar())["Usina Alfa"]["titulo"].count("Baixa Umidade") == 1


def test_o_texto_de_terceiros_vai_cru_ao_modelo_e_o_escape_e_do_template(leituras):
    # O modelo não escapa (o Jinja escapa na página); o que não pode é o texto perder caracteres no caminho.
    tudo_instalado(leituras, avisos=lei_avisos(aviso(2, "<b>Vendaval</b> & \"granizo\"", ALFA)))
    m = montar(cadastro=cadastro(usina("1", "<i>Alfa</i> & Cia", ALFA, cliente='C "X" <y>')))
    u = m["usinas"][0]
    assert u["titulo"].startswith("<i>Alfa</i> & Cia\nCliente: C \"X\" <y>")
    assert "<b>Vendaval</b> & \"granizo\"" in m["camada_avisos"]["grupos"][0]["itens"][0]["titulo"]


def test_nenhum_texto_do_modelo_traz_numero_de_coordenada(leituras):
    mundo_completo(leituras)
    m = montar()
    textos = [u["titulo"] for u in m["usinas"]] + [i["titulo"] for g in m["camada_avisos"]["grupos"] for i in g["itens"]]
    textos += [f["texto"] for f in m["fontes"]] + [f["detalhe"] for f in m["fontes"]]
    for t in textos:
        assert not re.search(r"\d+[.,]\d{3,}", t), t
    for pos in (ALFA, BETA, GAMA, DELTA, EPSILON, TETA):
        for t in textos:
            assert f"{abs(pos[0]):.3f}" not in t and f"{abs(pos[1]):.3f}" not in t


# ── a honestidade com a fonte que não foi lida inteira ───────────────────────────────────────────────────────────────

def test_sem_leitura_do_inmet_a_camada_some_e_quem_ficaria_sem_alerta_vira_sem_leitura(leituras):
    leituras(avisos=L.Leitura(None, None, erro="HTTP 500"), focos=lei_focos(foco_a(1.0, DELTA)), risco=lei_risco(risco_baixo()))
    m = montar()
    assert m["camada_avisos"]["estado"] == "fora" and m["camada_avisos"]["grupos"] == []
    assert m["contagem"] == {"agir": 1, "atencao": 0, "sem": 0, "nx": 5}
    nx = por_nome(m)["Usina Teta"]
    assert nx["nivel"] == "nx" and "Nível: Sem leitura completa" in nx["titulo"]
    assert "sem leitura de avisos do Instituto Nacional de Meteorologia (INMET); não dá para dizer que não há alerta" in nx["titulo"]
    assert por_nome(m)["Usina Delta"]["nivel"] == "agir"                      # o que as outras fontes provam continua valendo
    assert m["sem_leitura_de"] == "avisos do Instituto Nacional de Meteorologia (INMET)" and m["faltando"] == ["avisos do Instituto Nacional de Meteorologia (INMET)"] and m["completa"] is False


def test_fonte_lendo_diz_lendo_e_a_tela_volta_em_10_segundos(leituras):
    leituras(avisos=L.Leitura(None, None, erro=L.LENDO), focos=lei_focos(), risco=lei_risco(risco_baixo()))
    m = montar()
    assert m["camada_avisos"]["estado"] == "lendo" and m["lendo"] == ["avisos do Instituto Nacional de Meteorologia (INMET)"] and m["faltando"] == []
    assert m["recarrega_em"] == 10
    tudo_instalado(leituras)
    assert montar()["recarrega_em"] == 60


def test_sem_leitura_dos_focos_somem_os_pontos_e_os_aneis(leituras):
    leituras(avisos=lei_avisos(), focos=L.Leitura(None, None, erro="tempo esgotado"), risco=lei_risco(risco_baixo()))
    m = montar()
    fo = m["camada_focos"]
    assert fo["estado"] == "fora" and fo["d"] == "" and fo["aneis"] == [] and fo["n"] == 0
    assert m["contagem"]["nx"] == 6 and m["sem_leitura_de"] == "focos de queimada do Instituto Nacional de Pesquisas Espaciais (INPE)"


def test_sem_leitura_do_risco_de_fogo_ninguem_fica_com_o_verde(leituras):
    leituras(avisos=lei_avisos(aviso(3, "Vendaval", ALFA)), focos=lei_focos(), risco=L.Leitura(None, None, erro="HTTP 503"))
    m = montar()
    assert m["contagem"] == {"agir": 1, "atencao": 0, "sem": 0, "nx": 5} and m["sem_leitura_de"] == "risco de fogo do Instituto Nacional de Pesquisas Espaciais (INPE)"
    assert m["camada_avisos"]["estado"] == "ok" and m["camada_focos"]["estado"] == "ok"


def test_duas_fontes_sem_leitura_dizem_as_duas_na_ordem_do_painel(leituras):
    leituras(avisos=L.Leitura(None, None, erro="x"), focos=lei_focos(), risco=L.Leitura(None, None, erro=L.LENDO))
    m = montar()
    assert m["sem_leitura_de"] == "avisos do Instituto Nacional de Meteorologia (INMET) e risco de fogo do Instituto Nacional de Pesquisas Espaciais (INPE)"
    assert "sem leitura de avisos do Instituto Nacional de Meteorologia (INMET) e risco de fogo do Instituto Nacional de Pesquisas Espaciais (INPE)" in por_nome(m)["Usina Teta"]["titulo"]


def test_tudo_lido_mas_com_fonte_parcial_o_verde_fica_e_diz_nas_fontes_lidas(leituras):
    tudo_instalado(leituras, avisos=lei_avisos(ignorados=["aviso 7: sem polígono"]))
    m = montar()
    assert m["completa"] is False and m["sem_leitura_de"] == ""
    assert m["contagem"]["sem"] == 6 and m["rotulo_sem"] == "Sem alerta nas fontes lidas"
    t = por_nome(m)["Usina Teta"]["titulo"]
    assert "Nível: Sem alerta nas fontes lidas" in t and "nas fontes lidas" in t.splitlines()[3]
    assert m["camada_avisos"]["ignorados"] == 1


def test_leitura_velha_continua_no_mapa_e_o_painel_diz_a_hora_dela(leituras):
    velha = L.Leitura({"avisos": [aviso(3, "Vendaval", ALFA)], "ignorados": [], "lidos": 1}, LIDO - 3600, erro="HTTP 502", velha=True)
    leituras(avisos=velha, focos=lei_focos(), risco=lei_risco(risco_baixo()))
    m = montar()
    assert m["camada_avisos"]["estado"] == "ok" and m["camada_avisos"]["n_vigor"] == 1
    assert "Instituto Nacional de Meteorologia (INMET) · avisos: fora agora; última leitura boa às 14:00" in m["fontes"][0]["texto"]
    assert "dado de 14:00" in m["camada_avisos"]["qualifica"]


def test_o_painel_das_fontes_e_o_mesmo_da_tela_principal(leituras):
    # Reuso literal: o mapa não reescreve o texto de frescor, chama o mesmo código. Se a tela principal mudar, este teste diz.
    for fontes in (dict(avisos=lei_avisos(), focos=lei_focos(), risco=lei_risco(risco_baixo())),
                   dict(avisos=L.Leitura(None, None, erro="HTTP 500"), focos=lei_focos(ruins=2, falhos=["b.csv"]),
                        risco=lei_risco(risco_baixo(), erros={2: "arquivo ausente"}))):
        leituras(**fontes)
        cad = cadastro(*mundo_de_usinas())
        assert M.montar({}, cadastro=cad, ref=REF)["fontes"] == V.montar({}, cadastro=cad, ref=REF)["fontes"]


def test_o_mapa_le_as_fontes_pelo_cache_compartilhado_com_a_tela_principal(leituras):
    chamadas = tudo_instalado(leituras)
    montar()
    assert sorted(chamadas) == ["avisos", "firms", "focos", "risco"]             # a NASA FIRMS desde 10/10/2026


# ── o cadastro ───────────────────────────────────────────────────────────────────────────────────────────────────────

def test_usina_sem_coordenada_e_fora_do_brasil_ficam_na_lista_e_nao_no_mapa(leituras):
    tudo_instalado(leituras)
    cad = cadastro(*mundo_de_usinas(), sem=[Usina("7", "Usina Sem Posicao", "Cliente X")],
                   fora=[Usina("8", "Usina Trocada", "Cliente X", "", "", 0.0, 0.0)])
    m = montar(cadastro=cad)
    assert len(m["usinas"]) == 6 and m["sem_coordenada"] == ["Usina Sem Posicao"] and m["fora_do_brasil"] == ["Usina Trocada"]
    assert "Usina Sem Posicao" not in {u["nome"] for u in m["usinas"]}


def test_sem_usina_com_coordenada_nao_vai_a_rede_nenhuma(leituras):
    chamadas = tudo_instalado(leituras)
    m = montar(cadastro=cadastro(sem=[Usina("7", "Usina Sem Posicao", "Cliente X")]))
    assert m["sem_usinas"] is True and chamadas == [] and m["usinas"] == [] and m["sem_coordenada"] == ["Usina Sem Posicao"]


def test_sem_cadastro_o_modelo_so_traz_o_erro(leituras):
    chamadas = tudo_instalado(leituras)
    m = M.montar({}, cadastro=None, erro_cadastro="Falta a chave.", ref=REF)
    assert m["erro_cadastro"] == "Falta a chave." and m["usinas"] == [] and chamadas == []


def test_o_modelo_diz_a_hora_da_tela_e_a_recarga_normal(leituras):
    tudo_instalado(leituras)
    m = montar()
    assert m["atualizada"] == "15:00" and m["recarrega_em"] == 60 and m["completa"] is True


def test_a_ilha_fora_do_recorte_do_brasil_e_dita_e_nao_some(leituras):
    # Uma usina numa ilha oceânica (o ponto é inventado, em pleno Atlântico a leste do continente) cai fora do contorno "mínimo"
    # do IBGE, que não traz as ilhas, e fora do viewBox: a tela diz que não a desenha, em vez de a contar entre as do recorte.
    tudo_instalado(leituras)
    m = montar(cadastro=cadastro(*mundo_de_usinas(), usina("9", "Usina Ilha", (-10.0, -30.0))))
    assert len(m["usinas"]) == 6 and m["fora_do_recorte"] == 1 and m["n_usinas"] == 7


# ── o contorno que não abre ──────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("erro", [ValueError("o arquivo do IBGE não traz: RS"), FileNotFoundError("sem o arquivo")],
                         ids=["conteudo-errado", "arquivo-ausente"])
def test_contorno_que_nao_abre_vira_aviso_e_o_mapa_sai_sem_as_divisas_em_vez_de_500(leituras, monkeypatch, caplog, erro):
    quebrar_contorno(monkeypatch, erro)
    mundo_completo(leituras)
    m = montar(regiao="sul")
    assert m["erro_contorno"].startswith("O contorno dos estados não abriu") and m["ufs"] == ()
    assert m["regiao"] == "brasil" and m["viewbox"] == M.vista_de_caixa(M.BRASIL, "Brasil", *M.LIMITES_BRASIL).viewbox
    assert len(m["usinas"]) == 6 and m["camada_avisos"]["n_vigor"] == 2 and m["camada_focos"]["n"] == 4      # o resto continua
    assert "o contorno dos estados do IBGE não abriu" in caplog.text and str(erro) in caplog.text                  # o motivo vai ao log
    M._vista.cache_clear()
    M.ufs_da_vista.cache_clear()


def test_com_o_contorno_aberto_nao_ha_erro_de_contorno(leituras):
    mundo_completo(leituras)
    assert montar()["erro_contorno"] == ""


def test_os_limites_do_mapa_sem_contorno_cobrem_o_continente_sem_sobrar_muito():
    x0 = min(e.caixa[0] for e in M.estados())
    y0 = min(e.caixa[1] for e in M.estados())
    x1 = max(e.caixa[2] for e in M.estados())
    y1 = max(e.caixa[3] for e in M.estados())
    lon0, lat0, lon1, lat1 = M.LIMITES_BRASIL
    assert lon0 <= x0 and lat0 <= y0 and lon1 >= x1 and lat1 >= y1
    assert x0 - lon0 < 1.0 and y0 - lat0 < 1.0 and lon1 - x1 < 1.0 and lat1 - y1 < 1.0

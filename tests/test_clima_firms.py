"""O fogo das últimas 24 h dos satélites da NASA (FIRMS) no Clima e risco (Levi, 10/10/2026: "veja se é viável para o que fazemos
agora, se sim melhore e inclua coisas no mapa"). O leitor dos arquivos públicos (sem chave), a regra (fogo a até 5 km nas últimas
24 h é atenção), a confirmação do foco do INPE com a força e a confiança, o aviso da própria usina, a honestidade sem a NASA, a
camada do mapa e os textos das telas. Nenhum teste vai à rede."""
import math
import re
from datetime import datetime, timedelta, timezone

import pytest

from nexus.performance.clima import fontes as F
from nexus.performance.clima import leitura as L
from nexus.performance.clima import mapa as M
from nexus.performance.clima import visao as V

import clima_mapa_mundo as MM
from clima_mapa_mundo import (ALFA, DELTA, REF as REF_MAPA, TETA, aviso, cadastro as cad_mapa, foco_a as foco_mapa,
                              instalar_leituras, lei_avisos as avisos_mapa, lei_firms as firms_mapa, lei_focos as focos_mapa,
                              lei_risco as risco_mapa, mundo_de_usinas, nasa_a, risco_baixo)
from clima_mundo import CAB_MODIS, CAB_VIIRS
from test_clima_visao import (REF, UTC, cadastro, dias, faixa, foco_a, lei_avisos, lei_firms, lei_focos, lei_risco,  # noqa: F401
                              leituras, usina)

BASE = "https://firms.exemplo.test/active_fire/"


class Resposta:
    def __init__(self, status, corpo=b"", cabecalhos=None):
        self.status_code, self.content, self.headers = status, corpo, cabecalhos or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


class SessaoFirms:
    """Serve os arquivos do FIRMS por URL, com ETag; responde ao HEAD (o servidor da NASA ignora o If-None-Match)."""

    def __init__(self, arquivos, etags=None):
        self.arquivos, self.etags, self.gets, self.heads = dict(arquivos), dict(etags or {}), [], []

    def get(self, url, headers=None, timeout=None):
        self.gets.append(url)
        if url not in self.arquivos:
            return Resposta(404)
        return Resposta(200, self.arquivos[url], {"ETag": self.etags.get(url, '"e1"'),
                                                  "Last-Modified": "Sat, 10 Oct 2026 02:50:02 GMT"})

    def head(self, url, timeout=None):
        self.heads.append(url)
        return Resposta(200 if url in self.arquivos else 404, b"", {"ETag": self.etags.get(url, '"e1"')})


def arquivos(viirs_n20=(), modis=()):
    a = {}
    for sat, caminho in F.FIRMS_ARQUIVOS.items():
        if sat == "MODIS":
            corpo = CAB_MODIS + "\n" + "".join(l + "\n" for l in modis)
        elif sat == "NOAA-20":
            corpo = CAB_VIIRS + "\n" + "".join(l + "\n" for l in viirs_n20)
        else:
            corpo = CAB_VIIRS + "\n"
        a[BASE + caminho] = corpo.encode()
    return a


VIIRS = "-5.10000,-45.20000,340.1,0.39,0.36,2026-10-09,1642,N20,{conf},2.0NRT,296.0,{frp},{dn}"


# ── o leitor dos arquivos ────────────────────────────────────────────────────────────────────────────────────────────

def test_le_viirs_e_modis_com_satelite_confianca_forca_e_hora_em_utc():
    r = F.nasa_firms(SessaoFirms(arquivos(
        viirs_n20=[VIIRS.format(conf="high", frp="35.20", dn="D"), VIIRS.format(conf="l", frp="1.0", dn="N"),
                   "40.00000,-74.00000,330,0.4,0.4,2026-10-09,1642,N20,nominal,2.0NRT,295,3,D"],      # fora do Brasil: nem guarda
        modis=["-6.00000,-44.00000,320.0,1.00,1.00,2026-10-09,0501,A,85,6.1NRT,300.0,12.0,N",
               "-6.10000,-44.10000,320.0,1.00,1.00,2026-10-09,1334,T,25,6.1NRT,300.0,4.0,D"])), BASE)
    por_sat = {(f.satelite, f.confianca): f for f in r["focos"]}
    alta = por_sat[("NOAA-20", "alta")]
    assert (alta.sensor, alta.frp, alta.dia, alta.data) == ("VIIRS", 35.2, True, datetime(2026, 10, 9, 16, 42, tzinfo=timezone.utc))
    assert ("NOAA-20", "baixa") in por_sat and por_sat[("NOAA-20", "baixa")].dia is False
    assert por_sat[("Aqua", "alta")].sensor == "MODIS" and ("Terra", "baixa") in por_sat     # MODIS: 85 = alta, 25 = baixa
    assert len(r["focos"]) == 4 and r["falhos"] == {} and r["linhas_ruins"] == 0
    assert r["ate"] == datetime(2026, 10, 9, 16, 42, tzinfo=timezone.utc)


def test_linha_ilegivel_conta_e_cabecalho_diferente_e_formato_mudado():
    r = F.nasa_firms(SessaoFirms(arquivos(viirs_n20=[VIIRS.format(conf="nominal", frp="3", dn="D"),
                                                     VIIRS.format(conf="talvez", frp="3", dn="D"),
                                                     VIIRS.format(conf="nominal", frp="-1", dn="D")])), BASE)
    assert len(r["focos"]) == 1 and r["linhas_ruins"] == 2
    quebrado = arquivos()
    quebrado[BASE + F.FIRMS_ARQUIVOS["NOAA-20"]] = b"lat,lon,frp\n-5,-45,3\n"
    with pytest.raises(F.FonteErro, match="faltam"):
        F.nasa_firms(SessaoFirms(quebrado), BASE)


def test_um_satelite_fora_e_parcial_e_todos_fora_e_erro():
    a = arquivos(viirs_n20=[VIIRS.format(conf="nominal", frp="3", dn="D")])
    del a[BASE + F.FIRMS_ARQUIVOS["S-NPP"]]
    r = F.nasa_firms(SessaoFirms(a), BASE)
    assert r["falhos"] == {"S-NPP": "HTTP 404"} and len(r["focos"]) == 1
    with pytest.raises(F.FonteErro, match="nenhum arquivo do FIRMS"):
        F.nasa_firms(SessaoFirms({}), BASE)


def test_a_releitura_pergunta_pelo_head_e_so_baixa_o_arquivo_que_mudou():
    a = arquivos(viirs_n20=[VIIRS.format(conf="nominal", frp="3", dn="D")])
    s = SessaoFirms(a)
    primeira = F.nasa_firms(s, BASE)
    assert len(s.gets) == 4 and s.heads == []
    s.gets.clear()
    s.etags[BASE + F.FIRMS_ARQUIVOS["MODIS"]] = '"e2"'                        # só o MODIS mudou
    segunda = F.nasa_firms(s, BASE, anterior=primeira)
    assert len(s.heads) == 4 and s.gets == [BASE + F.FIRMS_ARQUIVOS["MODIS"]]
    assert segunda["arquivos"]["NOAA-20"] is primeira["arquivos"]["NOAA-20"]   # o mesmo arquivo: nem relido


def test_o_endereco_troca_pela_configuracao_e_o_cache_e_de_30_min():
    assert F.enderecos({"NEXUS_CLIMA_FIRMS_URL": "https://espelho.test/firms"})["firms"] == "https://espelho.test/firms/"
    assert F.enderecos({})["firms"] == F.FIRMS_BASE and L.TTL_FIRMS_S == 30 * 60
    assert L.firms({"TESTING": True}).erro == L.SEM_FONTE_NOS_TESTES                # nos testes, sem sessão, não vai à rede


# ── a regra: fogo a até 5 km nas últimas 24 h é atenção ─────────────────────────────────────────────────────────────

def nasa(km, horas=6.0, frp=8.0, confianca="nominal", lat=-5.0, lon=-45.0, sat="NOAA-20"):
    return F.FocoNasa(lat + km / 111.195, lon, sat, (REF - timedelta(hours=horas)).astimezone(UTC), "VIIRS", confianca, frp, True)


def uma_usina(leituras, firms, focos=(), avisos=()):
    leituras(avisos=lei_avisos(*avisos), focos=lei_focos(*focos), risco=lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1)}), firms=firms)
    return V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)


def test_fogo_da_nasa_a_ate_5_km_nas_ultimas_24_h_e_atencao_com_o_motivo(leituras):
    v = uma_usina(leituras, lei_firms(nasa(3.0, horas=6, frp=12.0)))
    c = v["atencao"][0]
    assert c["nivel"] == "atencao" and c["por_que"] == "Fogo a 3,0 km há 6 h"
    assert c["fogo24"]["texto"] == "a 3,0 km há 6 h" and c["fogo24"]["classe"] == "médio"
    assert c["fogo24"]["detalhe"].startswith("1 foco a até 5 km nas últimas 24 h · o mais perto a 3,0 km, às 09:00 "
                                             "(VIIRS NOAA-20, confiança nominal, força 12 MW (médio))")


def test_fogo_velho_longe_ou_sem_leitura_nao_e_atencao(leituras):
    assert uma_usina(leituras, lei_firms(nasa(3.0, horas=30)))["atencao"] == []          # há mais de 24 h
    assert uma_usina(leituras, lei_firms(nasa(6.0, horas=2)))["atencao"] == []           # a mais de 5 km


def test_sem_a_nasa_o_verde_vira_nas_fontes_lidas_e_nao_cinza(leituras):
    v = uma_usina(leituras, L.Leitura(None, None, erro="HTTP 503"))
    f = faixa(v)["sem"]
    assert v["sem_alerta"] == 1 and f["valor"] == "1" and f["sub"] == "nas fontes lidas" and "cl-na" in f["classe"]
    assert f["qual"] == ["sem leitura de fogo das últimas 24 h da Fire Information for Resource Management System, sistema da NASA "
                         "(NASA FIRMS)"]
    assert v["completa"] is False and v["foco_vazio"] == "não na última hora"
    assert v["faltando"] == [V.NOME_LONGO["firms"]] and v["fontes"][3]["estado"] == "fora"


def test_passagem_velha_fica_em_atencao_e_satelite_fora_e_parcial(leituras):
    velha = lei_firms(nasa(40.0, horas=20))                                   # o foco mais novo é de 20 h atrás
    v = uma_usina(leituras, velha)
    f = v["fontes"][3]
    assert f["estado"] == "atencao" and f["qualifica"] == ["passagens até 05/10 19:00"]
    v = uma_usina(leituras, lei_firms(nasa(40.0, horas=2), falhos={"MODIS": "HTTP 404"}))
    assert v["fontes"][3]["qualifica"] == ["parcial"] and "satélites indisponíveis (MODIS)" in v["fontes"][3]["detalhe"]


def test_o_foco_do_inpe_confirmado_pela_nasa_ganha_a_forca_e_a_confianca(leituras):
    inpe = foco_a(1.0, sat="NOAA-20")                                          # 17:50 UTC
    mesmo = F.FocoNasa(inpe.lat + 0.002, inpe.lon, "NOAA-20", datetime(2026, 10, 6, 17, 42, tzinfo=UTC), "VIIRS", "alta", 35.2, True)
    v = uma_usina(leituras, lei_firms(mesmo), focos=[inpe])
    c = v["agir"][0]
    assert c["motivos"][0]["prova"].endswith("· confirmado pela NASA (VIIRS NOAA-20, confiança alta, força 35 MW (forte))")
    assert not any("fogo visto pela NASA" in x for x in c["contexto"])       # o mesmo fogo: não repete no "Também"


def test_foco_a_menos_de_400_m_avisa_que_pode_ser_a_propria_usina(leituras):
    v = uma_usina(leituras, lei_firms(), focos=[foco_a(0.3)])
    assert "a menos de 400 m do ponto da usina: pode ser a própria usina (reflexo do sol nos módulos ou telhado quente); confira " \
           "antes de acionar" in v["agir"][0]["motivos"][0]["prova"]
    assert v["agir"][0]["nivel"] == "agir"                                    # continua mandando agir: o aviso só pede conferir


def test_dentro_da_atencao_o_fogo_forte_vem_antes_do_fraco(leituras):
    leituras(avisos=lei_avisos(), focos=lei_focos(),
             risco=lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1), "2": dias(0.1, 0.1, 0.1, 0.1)}),
             firms=lei_firms(nasa(4.0, frp=2.0), nasa(4.0, frp=60.0, lon=-46.0)))
    v = V.montar({}, cadastro=cadastro(usina("1", "Fraco"), usina("2", "Forte", lon=-46.0)), ref=REF)
    assert [c["nome"] for c in v["atencao"]] == ["Forte", "Fraco"]


# ── o mapa ───────────────────────────────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def leituras_mapa(monkeypatch):
    return instalar_leituras(monkeypatch)


def mapa_com(leituras_mapa, firms, **kw):
    leituras_mapa(avisos=avisos_mapa(), focos=focos_mapa(), risco=risco_mapa(risco_baixo()), firms=firms)
    return MM.montar(**kw)


def test_a_camada_da_nasa_desenha_so_perto_das_usinas_e_pela_forca(leituras_mapa):
    m = mapa_com(leituras_mapa, firms_mapa(nasa_a(3.0, DELTA, frp=2.0), nasa_a(10.0, DELTA, frp=8.0),
                                           nasa_a(20.0, DELTA, frp=40.0), nasa_a(80.0, DELTA, frp=40.0)))
    na = m["camada_nasa"]
    assert na["estado"] == "ok" and na["n"] == 3 and na["n_perto"] == 1                # o de 80 km não entra
    assert {c["id"]: bool(c["d"]) for c in na["classes"]} == {"fraco": True, "médio": True, "forte": True}
    assert [c["css"] for c in na["classes"]] == ["fraco", "medio", "forte"]
    delta = M.montar({}, cadastro=cad_mapa(*mundo_de_usinas()), ref=REF_MAPA)["dados_js"]["usinas"]["4"]
    assert delta["v"] == "atencao" and delta["m"] == "Fogo a 3,0 km há 6 h"
    assert [F.extenso("nasa_firms"), delta["f"][0][1]] == delta["f"][0] and "VIIRS NOAA-20" in delta["f"][0][1]


def test_sem_a_nasa_a_camada_some_e_a_usina_sem_alerta_fica_verde_nas_fontes_lidas(leituras_mapa):
    m = mapa_com(leituras_mapa, L.Leitura(None, None, erro="HTTP 503"))
    assert m["camada_nasa"]["estado"] == "fora" and m["camada_nasa"]["classes"] == []
    assert m["contagem"]["sem"] == 6 and m["contagem"]["nx"] == 0 and m["rotulo_sem"] == "Sem alerta nas fontes lidas"
    assert m["faltando"] == [V.NOME_LONGO["firms"]]


def test_a_pagina_do_mapa_tem_a_camada_a_legenda_e_a_citacao(tmp_path, monkeypatch, leituras_mapa):
    from test_torre_performance_mapa import nova_app
    _, c = nova_app(tmp_path)
    monkeypatch.setattr(V, "agora", lambda: REF_MAPA)
    leituras_mapa(avisos=avisos_mapa(), focos=focos_mapa(foco_mapa(1.0, ALFA)), risco=risco_mapa(risco_baixo()),
                  firms=firms_mapa(nasa_a(3.0, DELTA, frp=25.0), nasa_a(2.0, TETA, frp=3.0)))
    html = c.get("/t/performance/clima/mapa").get_data(as_text=True)
    assert '<g class="mp-nasa"><path class="mp-na mp-na-fraco"' in html and 'class="mp-na mp-na-forte"' in html
    assert "data-camada" not in re.search(r'<g class="mp-nasa"[^>]*>', html).group(0)   # o atributo das camadas de fundo esconderia
    # o contorno rosa nas usinas com fogo a até 5 km: a Delta (forte, 25 MW) e a Teta (fraco, 3 MW); a Alfa (foco do INPE) não
    assert html.count('class="mp-anel-nasa mp-anel-nasa--forte"') == 1 and html.count('class="mp-anel-nasa mp-anel-nasa--fraco"') == 1
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    assert "Fogo nas últimas 24 h · Fire Information for Resource Management System, sistema da NASA (NASA FIRMS)" in t
    assert "2 detecções a até 25 km das usinas nas últimas 24 h, 2 a até 5 km" in t
    assert "Forte 20 MW ou mais" in t and "Fraco abaixo de 5 MW" in t and "Usina com fogo a até 5 km nas últimas 24 h" in t
    assert "Fogo das últimas 24 h: Fire Information for Resource Management System, sistema da NASA (NASA FIRMS)." in t
    assert "Dados e imagens do FIRMS, parte do Earth Science Data and Information System (ESDIS) da NASA." in t
    # o botão "Focos" liga e desliga as camadas de fogo: a da NASA e o contorno das usinas vão junto
    css = (__import__("pathlib").Path(M.__file__).resolve().parents[2] / "static" / "clima-mapa.css").read_text(encoding="utf-8")
    assert ".mp-sem-focos .mp-nasa,.mp-sem-focos .mp-anel-nasa{display:none}" in css


# ── a lista e a página da usina ──────────────────────────────────────────────────────────────────────────────────────

def test_a_lista_mostra_o_fogo_da_nasa_na_atencao_e_explica_a_forca(mundo_lista):
    from clima_mundo import pagina, texto
    c, _sessao, _app = mundo_lista
    html = pagina(c)
    assert re.search(r'<td class="cl-col-foco"><span class="cl-fogo24 cl-fogo24--medio" title="1 foco a até 5 km nas últimas 24 h'
                     r'[^"]*">a 2,0 km há 2 h</span></td>', html)
    t = texto(html)
    assert "Fogo nas últimas 24 horas" in t and "Fraco: abaixo de 5 MW. Médio: de 5 a 20 MW. Forte: 20 MW ou mais." in t
    assert "Foco a menos de 400 m da usina pode ser a própria usina: confira antes de acionar." in t
    assert "Fogo das últimas 24 h: Fire Information for Resource Management System, sistema da NASA (NASA FIRMS)." in t


@pytest.fixture
def mundo_lista(tmp_path, monkeypatch):
    """O mundo da lista com a NASA vendo fogo a 2 km da Usina Delta (sem aviso, sem foco do INPE, risco baixo), 2 h antes."""
    import clima_mundo as CM
    lat, lon = CM.centro(*CM.DD)
    perto = (f"{lat + 2.0 / 111.195:.5f},{lon:.5f},335.0,0.39,0.36,2026-10-06,1600,N20,nominal,2.0NRT,296.0,9.50,D")
    a = CM.arquivos_do_mundo(nasa=False)
    a.update(CM.firms(linhas_viirs=[perto]))
    yield CM._mundo(tmp_path, monkeypatch, CM.carga(), a)
    L.usar_sessao(None)


def test_a_pagina_da_usina_diz_o_fogo_das_ultimas_24_h(mundo_lista):
    from clima_mundo import texto
    c, _sessao, _app = mundo_lista
    t = texto(c.get("/t/performance/clima/usina/4").get_data(as_text=True))
    assert "Fogo nas últimas 24 h, satélites da NASA" in t and "o mais perto a 2,0 km, às 13:00 (VIIRS NOAA-20" in t
    assert "Nenhum fogo a até 5 km nas últimas 24 h" in texto(c.get("/t/performance/clima/usina/1").get_data(as_text=True))

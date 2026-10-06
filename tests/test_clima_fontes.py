"""Clima e risco: os três clientes públicos (INMET, focos e risco de fogo do INPE), com payloads inventados no formato real
medido em 06/10/2026 (`apiprevmet3.inmet.gov.br/avisos/ativos`, o índice e os CSV de 10 min do INPE, o COG do risco)."""
import json
from datetime import datetime, timedelta, timezone

import pytest
import requests

from nexus.performance.clima import fontes as F
from nexus.performance.clima import geotiff as GT

from clima_cog import SessaoArquivos, montar_cog

BRT = timezone(timedelta(hours=-3))
UTC = timezone.utc
URL_INMET = "https://inmet.exemplo.test/avisos/ativos"
BASE_FOCOS = "https://inpe.exemplo.test/focos/10min/"
RISCO = "https://inpe.exemplo.test/risco/RF.PREV.T{d}.tif"

QUADRADO = [[-41.0, -5.0], [-39.0, -5.0], [-39.0, -3.0], [-41.0, -3.0], [-41.0, -5.0]]


def aviso(id=1, descricao="Tempestade", severidade="Perigo", inicio="2026-10-05 09:10", fim="2026-10-06 23:59",
          poligono=None, **extra):
    """Um aviso como o INMET manda: o polígono é uma STRING de JSON (nos 12 avisos medidos), e vem um `icone` enorme."""
    geo = {"type": "Polygon", "coordinates": [QUADRADO]} if poligono is None else poligono
    d = {"id": id, "id_aviso": id + 1000, "descricao": descricao, "severidade": severidade, "id_severidade": 7,
         "aviso_cor": "#F96602", "inicio": inicio, "fim": fim, "poligono": json.dumps(geo) if isinstance(geo, dict) else geo,
         "riscos": ["Chuva entre 20 e 30 mm/h."], "estados": "Ceará,Piauí", "icone": "data:image/png;base64," + "A" * 4000}
    d.update(extra)
    return d


def sessao_inmet(hoje=(), futuro=(), bruto=None):
    corpo = bruto if bruto is not None else json.dumps({"hoje": list(hoje), "futuro": list(futuro)}).encode()
    return SessaoArquivos({URL_INMET: corpo})


# ── INMET ────────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_inmet_le_hoje_e_futuro_com_o_poligono_que_vem_como_texto():
    s = sessao_inmet(hoje=[aviso(1), aviso(2, "Baixa Umidade", "Perigo Potencial")], futuro=[aviso(3, "Acumulado de Chuva")])
    r = F.inmet_avisos(s, URL_INMET)
    assert [a.id for a in r["avisos"]] == [1, 2, 3]
    a = r["avisos"][0]
    assert (a.quando, a.evento, a.severidade, a.nivel) == ("hoje", "Tempestade", "Perigo", 2)
    assert a.geometria["type"] == "Polygon" and a.caixa == (-41.0, -5.0, -39.0, -3.0)
    assert r["avisos"][2].quando == "futuro"
    assert r["ignorados"] == [] and r["lidos"] == 3


def test_inmet_horario_e_de_brasilia():
    r = F.inmet_avisos(sessao_inmet(hoje=[aviso()]), URL_INMET)
    a = r["avisos"][0]
    assert a.inicio == datetime(2026, 10, 5, 9, 10, tzinfo=BRT) and a.fim == datetime(2026, 10, 6, 23, 59, tzinfo=BRT)


def test_inmet_nivel_pela_severidade_e_desconhecida_vira_o_mais_baixo_sem_perder_o_nome():
    s = sessao_inmet(hoje=[aviso(1, severidade="Perigo Potencial"), aviso(2, severidade="Perigo"),
                           aviso(3, severidade="Grande Perigo"), aviso(4, severidade="Severidade Nova")])
    niveis = {a.id: (a.nivel, a.severidade) for a in F.inmet_avisos(s, URL_INMET)["avisos"]}
    assert niveis == {1: (1, "Perigo Potencial"), 2: (2, "Perigo"), 3: (3, "Grande Perigo"), 4: (1, "Severidade Nova")}


def test_inmet_aceita_poligono_ja_em_objeto_e_multipoligono():
    multi = {"type": "MultiPolygon", "coordinates": [[QUADRADO], [[[10, 10], [11, 10], [11, 11], [10, 10]]]]}
    um, dois = aviso(1), aviso(2)
    um["poligono"] = {"type": "Polygon", "coordinates": [QUADRADO]}       # objeto, não texto
    dois["poligono"] = multi
    r = F.inmet_avisos(sessao_inmet(hoje=[um, dois]), URL_INMET)
    assert [a.id for a in r["avisos"]] == [1, 2] and r["avisos"][1].caixa == (-41.0, -5.0, 11, 11)


@pytest.mark.parametrize("poligono,motivo", [
    (None, "sem polígono"), ("", "sem polígono"), ("null", "sem polígono"),
    ("{nao e json", "ilegível"),
    ('{"type": "Point", "coordinates": [1, 1]}', "polígono"),
    ('{"type": "Polygon", "coordinates": [[[1, 1], [2]]]}', "polígono"),
])
def test_inmet_aviso_que_nao_da_para_localizar_e_contado_nao_perdido_em_silencio(poligono, motivo):
    ruim = aviso(7)
    ruim["poligono"] = poligono
    r = F.inmet_avisos(sessao_inmet(hoje=[aviso(1), ruim]), URL_INMET)
    assert [a.id for a in r["avisos"]] == [1]
    assert r["lidos"] == 2 and len(r["ignorados"]) == 1 and motivo in r["ignorados"][0]


def test_inmet_o_mesmo_aviso_nas_duas_listas_conta_uma_vez():
    r = F.inmet_avisos(sessao_inmet(hoje=[aviso(1)], futuro=[aviso(1), aviso(2)]), URL_INMET)
    assert [a.id for a in r["avisos"]] == [1, 2] and r["avisos"][0].quando == "hoje"


def test_inmet_aviso_ignorado_repetido_nas_duas_listas_tambem_conta_uma_vez():
    ruim = aviso(7)
    ruim["poligono"] = None
    r = F.inmet_avisos(sessao_inmet(hoje=[ruim], futuro=[dict(ruim)]), URL_INMET)
    assert r["lidos"] == 1 and len(r["ignorados"]) == 1


def test_inmet_nao_guarda_o_icone_e_corta_texto_enorme():
    r = F.inmet_avisos(sessao_inmet(hoje=[aviso(1, descricao="X" * 5000, severidade="Perigo " + "Y" * 5000)]), URL_INMET)
    a = r["avisos"][0]
    assert len(a.evento) <= 120 and len(a.severidade) <= 60
    assert not hasattr(a, "icone")


def test_inmet_campos_faltando_nao_derrubam():
    r = F.inmet_avisos(sessao_inmet(hoje=[{"id": 9, "poligono": json.dumps({"type": "Polygon", "coordinates": [QUADRADO]})}]),
                       URL_INMET)
    a = r["avisos"][0]
    assert a.evento == "Aviso" and a.severidade == "sem severidade" and a.nivel == 1 and a.inicio is None and a.fim is None


def test_inmet_formato_inesperado_e_erro_explicito():
    for bruto in (b"nao e json", b"[1, 2]", b'{"avisos": []}', b'{"hoje": "x", "futuro": []}', b""):
        with pytest.raises(F.FonteErro):
            F.inmet_avisos(sessao_inmet(bruto=bruto), URL_INMET)


def test_inmet_lista_vazia_e_normal():
    r = F.inmet_avisos(sessao_inmet(), URL_INMET)
    assert r["avisos"] == [] and r["lidos"] == 0
    r = F.inmet_avisos(sessao_inmet(bruto=b'{"hoje": null, "futuro": []}'), URL_INMET)
    assert r["avisos"] == []


def test_inmet_http_de_erro_levanta():
    with pytest.raises(requests.HTTPError):
        F.inmet_avisos(SessaoArquivos({}), URL_INMET)


# ── focos de queimada ────────────────────────────────────────────────────────────────────────────────────────────────

def nome_foco(hora, minuto, dia=6):
    return f"focos_10min_202610{dia:02d}_{hora:02d}{minuto:02d}.csv"


def csv_focos(*linhas, cabecalho="lat,lon,satelite,data"):
    return (cabecalho + "\n" + "\n".join(linhas) + "\n").encode()


def indice(*nomes):
    return ("<html><body><h1>Index</h1><table>" + "".join(f'<tr><td><a href="{n}">{n}</a></td></tr>' for n in nomes)
            + '</table><a href="../">Parent</a></body></html>').encode()


def sessao_focos(arquivos: dict, nomes=None):
    nomes = sorted(arquivos) if nomes is None else nomes
    return SessaoArquivos({BASE_FOCOS: indice(*nomes), **{BASE_FOCOS + n: c for n, c in arquivos.items()}})


def test_focos_le_os_seis_ultimos_arquivos_do_indice():
    todos = {nome_foco(h, m): csv_focos(f"  -10.0000,  -40.0000,GOES-19,2026-10-06 {h:02d}:{m:02d}:00")
             for h in (16, 17, 18) for m in (0, 10, 20, 30, 40, 50)}
    s = sessao_focos(todos)
    r = F.inpe_focos(s, BASE_FOCOS)
    assert r["arquivos"] == sorted(todos)[-6:]
    assert len(r["focos"]) == 6
    # o índice, mais os seis arquivos, e nada além
    assert [p[0] for p in s.pedidos] == [BASE_FOCOS] + [BASE_FOCOS + n for n in sorted(todos)[-6:]]


def test_focos_numero_com_espaco_na_frente_e_hora_em_utc():
    n = nome_foco(19, 10)
    s = sessao_focos({n: csv_focos("  -8.319400, -75.610800,GOES-19,2026-10-06 18:50:00",
                                   "  -4.551500, -80.661800,NOAA-21,2026-10-06 16:16:00")})
    r = F.inpe_focos(s, BASE_FOCOS)
    f = r["focos"][0]
    assert (f.lat, f.lon, f.satelite) == (-8.3194, -75.6108, "GOES-19")
    assert f.data == datetime(2026, 10, 6, 18, 50, tzinfo=UTC)
    assert r["focos"][1].satelite == "NOAA-21"


def test_focos_repetido_em_dois_arquivos_conta_uma_vez():
    linha = "-8.3194,-75.6108,GOES-19,2026-10-06 18:50:00"
    s = sessao_focos({nome_foco(19, 0): csv_focos(linha), nome_foco(19, 10): csv_focos(linha, "-9.0,-70.0,GOES-19,2026-10-06 19:00:00")})
    assert len(F.inpe_focos(s, BASE_FOCOS)["focos"]) == 2


def test_focos_linha_ruim_e_contada_e_pulada():
    s = sessao_focos({nome_foco(19, 0): csv_focos("-8.3,-75.6,GOES-19,2026-10-06 18:50:00", "abc,-75.6,GOES-19,2026-10-06 18:50:00",
                                                  "-8.3,-75.6,GOES-19,ontem", "-95.0,-75.6,GOES-19,2026-10-06 18:50:00", "so,tres,campos")})
    r = F.inpe_focos(s, BASE_FOCOS)
    assert len(r["focos"]) == 1 and r["linhas_ruins"] == 4


def test_focos_ate_quando_vai_o_dado_e_a_hora_do_arquivo_mais_novo_lido():
    s = sessao_focos({nome_foco(18, 50): csv_focos("-8.3,-75.6,GOES-19,2026-10-06 18:40:00"),
                      nome_foco(19, 0): csv_focos("-8.4,-75.6,GOES-19,2026-10-06 18:50:00")})
    assert F.inpe_focos(s, BASE_FOCOS)["ate"] == datetime(2026, 10, 6, 19, 0, tzinfo=UTC)


def test_focos_um_arquivo_que_falha_nao_derruba_os_outros_mas_fica_dito():
    a, b = nome_foco(19, 0), nome_foco(19, 10)
    s = SessaoArquivos({BASE_FOCOS: indice(a, b), BASE_FOCOS + a: csv_focos("-8.3,-75.6,GOES-19,2026-10-06 18:50:00")})   # b dá 404
    r = F.inpe_focos(s, BASE_FOCOS)
    assert len(r["focos"]) == 1 and r["falhos"] == [b] and r["ate"] == datetime(2026, 10, 6, 19, 0, tzinfo=UTC)


def test_focos_todos_os_arquivos_falhando_e_erro():
    a = nome_foco(19, 0)
    with pytest.raises(F.FonteErro):
        F.inpe_focos(SessaoArquivos({BASE_FOCOS: indice(a)}), BASE_FOCOS)


def test_focos_indice_sem_arquivo_e_erro():
    with pytest.raises(F.FonteErro):
        F.inpe_focos(SessaoArquivos({BASE_FOCOS: indice()}), BASE_FOCOS)


def test_focos_cabecalho_diferente_e_erro_e_nao_arquivo_falho():
    n = nome_foco(19, 0)
    s = sessao_focos({n: csv_focos("-8.3,-75.6,2026-10-06 18:50:00", cabecalho="latitude,longitude,data")})
    with pytest.raises(F.FonteErro) as e:
        F.inpe_focos(s, BASE_FOCOS)
    assert "cabeçalho" in str(e.value)


def test_focos_arquivo_vazio_so_com_cabecalho_e_valido():
    r = F.inpe_focos(sessao_focos({nome_foco(19, 0): csv_focos()}), BASE_FOCOS)
    assert r["focos"] == [] and r["falhos"] == []


# ── risco de fogo ────────────────────────────────────────────────────────────────────────────────────────────────────

X0, Y0, D = -50.0, 10.0, 0.01


def centro(c, r):
    return Y0 - (r + 0.5) * D, X0 + (c + 0.5) * D


def sessao_risco(valores_por_dia, **kw):
    arquivos = {}
    for d, g in valores_por_dia.items():
        arquivos[RISCO.format(d=d)] = montar_cog(g, origem=(X0, Y0), escala=D, **kw)
    return SessaoArquivos(arquivos)


def plano(v, w=40, h=30):
    return [[v] * w for _ in range(h)]


def test_risco_le_os_quatro_dias_por_ponto():
    s = sessao_risco({0: plano(0.10), 1: plano(0.45), 2: plano(0.80), 3: plano(0.99)})
    pontos = [("a", *centro(3, 3)), ("b", *centro(30, 20))]
    r = F.inpe_risco_fogo(pontos, s, RISCO)
    assert [a.valor for a in r["por_ponto"]["a"]] == [0.10, 0.45, 0.80, 0.99]
    assert [a.origem for a in r["por_ponto"]["b"]] == ["ponto"] * 4
    assert set(r["arquivos"]) == {0, 1, 2, 3} and all(isinstance(v, datetime) for v in r["arquivos"].values())
    assert r["erros"] == {}


def test_risco_ponto_sem_dado_usa_o_entorno_e_ponto_fora_da_grade_diz_fora():
    g = plano(0.30)
    g[10][10] = None                                       # o pixel do ponto "a" é nodata; o entorno vale 0,3
    s = sessao_risco({d: g for d in range(4)})
    r = F.inpe_risco_fogo([("a", *centro(10, 10)), ("f", Y0 + 1, X0)], s, RISCO)
    assert [(a.valor, a.origem) for a in r["por_ponto"]["a"]] == [(0.30, "entorno")] * 4
    assert [a.origem for a in r["por_ponto"]["f"]] == ["fora_da_grade"] * 4


def test_risco_valor_fora_de_0_a_1_e_erro_porque_a_escala_pode_ter_mudado():
    s = sessao_risco({0: plano(0.2), 1: plano(0.2), 2: plano(55.0), 3: plano(0.2)})
    r = F.inpe_risco_fogo([("a", *centro(3, 3))], s, RISCO)
    # o dia ruim sai do resultado com a causa; os outros seguem
    assert r["por_ponto"]["a"][2].origem == "indisponivel" and "0 a 1" in r["erros"][2]
    assert r["por_ponto"]["a"][0].valor == 0.2


def test_risco_um_dia_que_falta_nao_derruba_os_outros_e_a_tela_fica_sabendo():
    s = sessao_risco({0: plano(0.2), 1: plano(0.3), 2: plano(0.4)})            # T3 dá 404
    r = F.inpe_risco_fogo([("a", *centro(3, 3))], s, RISCO)
    assert [a.valor for a in r["por_ponto"]["a"]] == [0.2, 0.3, 0.4, None]
    assert r["por_ponto"]["a"][3].origem == "indisponivel" and "404" in r["erros"][3]


def test_risco_formato_do_arquivo_mudou_em_todos_os_dias_e_erro_da_fonte():
    s = sessao_risco({d: plano(0.2) for d in range(4)}, tags={259: (3, 8)})
    with pytest.raises(F.FonteErro) as e:
        F.inpe_risco_fogo([("a", *centro(3, 3))], s, RISCO)
    assert "compress" in str(e.value).lower()


def test_risco_sem_pontos_nao_vai_a_rede():
    s = SessaoArquivos({})
    r = F.inpe_risco_fogo([], s, RISCO)
    assert r["por_ponto"] == {} and s.pedidos == []


def test_risco_os_quatro_dias_sao_buscados_ao_mesmo_tempo():
    # Cada dia é um arquivo independente: com 160 usinas, um a um levava 10 s na primeira visita. A barreira só deixa o
    # primeiro pedido de cada dia passar quando os QUATRO estão no ar; se os dias fossem em fila, ela estouraria o tempo.
    import threading
    barreira = threading.Barrier(4, timeout=5)

    class Concorrente(SessaoArquivos):
        def get(self, url, params=None, headers=None, timeout=None):
            if len(self.pedidos) < 4 and not hasattr(self, "_barrou_" + url):
                setattr(self, "_barrou_" + url, True)
                barreira.wait()
            return super().get(url, params, headers, timeout)

    s = Concorrente({RISCO.format(d=d): montar_cog(plano(0.2), origem=(X0, Y0), escala=D) for d in range(4)})
    r = F.inpe_risco_fogo([("a", *centro(3, 3))], s, RISCO)
    assert [a.valor for a in r["por_ponto"]["a"]] == [0.2] * 4 and r["erros"] == {}


def test_risco_so_busca_as_tiles_dos_pontos():
    s = sessao_risco({d: plano(0.2) for d in range(4)})
    F.inpe_risco_fogo([("a", *centro(3, 3))], s, RISCO, janela=512)
    # por dia: cabeçalho + 1 tile; nunca o arquivo inteiro
    assert len(s.pedidos) == 4 * 2
    assert all(faixa and faixa.startswith("bytes=") for _, faixa in s.pedidos)


# ── endereços ────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_enderecos_padrao_e_sobrescritos_pela_configuracao():
    e = F.enderecos({})
    assert e["inmet"] == "https://apiprevmet3.inmet.gov.br/avisos/ativos"
    assert e["focos"] == "https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/10min/"
    assert e["risco"].endswith("/riscofogo_meteorologia/previsto/risco_fogo/RF.PREV.T{d}.tif")
    e = F.enderecos({"NEXUS_CLIMA_INMET_URL": "http://a/x", "NEXUS_CLIMA_FOCOS_URL": "http://b/y", "NEXUS_CLIMA_RISCO_URL": "http://c/{d}.tif"})
    assert (e["inmet"], e["focos"], e["risco"]) == ("http://a/x", "http://b/y/", "http://c/{d}.tif")

"""A cidade do técnico parado fora de usina, pela malha de municípios do IBGE (08/11/2026, Levi: "Faça puxar uma API do
IBGE"; `nexus/campo/equipe/municipios.py`).

A posição do técnico NUNCA vai ao IBGE: baixa-se a malha do ESTADO inteiro e a lista dos nomes, e o ponto no polígono
roda no servidor. A malha fica no disco 30 dias; o IBGE fora do ar não quebra o mapa (o painel mostra só o estado). O
IBGE é de mentira (`baixar` injetado), com o formato da resposta de verdade (conferido em 08/11/2026 com o DF: `codarea`
em texto na malha, `id` número na lista de nomes); nada vai à rede. Municípios e coordenadas inventados."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from nexus.campo.equipe import municipios as MU
from nexus.campo.equipe import situacao as SI

AGORA = datetime(2026, 11, 8, 15, 0, tzinfo=timezone.utc)
USINAS = {"7": (-16.612345, -49.187654, "GO")}
FORA = (-16.567381, -49.187643)              # 5 km da usina 7, parado: a casa, o hotel


def _anel(lon0, lat0, lon1, lat1):
    return [[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]


def _municipio(codigo, *aneis, tipo="Polygon"):
    return {"type": "Feature", "properties": {"codarea": codigo},
            "geometry": {"type": tipo, "coordinates": list(aneis) if tipo == "Polygon" else [[a] for a in aneis]}}


# dois municípios lado a lado; o 1º tem um buraco, que é o 3º (o enclave); o 4º vem em dois pedaços (MultiPolygon)
MALHA = {"type": "FeatureCollection", "features": [
    _municipio("5200001", _anel(-50.0, -17.0, -49.0, -16.0), _anel(-49.6, -16.6, -49.4, -16.4)),
    _municipio("5200002", _anel(-49.0, -17.0, -48.0, -16.0)),
    _municipio("5200003", _anel(-49.6, -16.6, -49.4, -16.4)),
    _municipio("5200004", _anel(-48.0, -17.0, -47.5, -16.5), _anel(-47.0, -17.0, -46.5, -16.5), tipo="MultiPolygon")]}
NOMES = [{"id": 5200001, "nome": "Cidade Um Teste"}, {"id": 5200002, "nome": "Cidade Dois Teste"},
         {"id": 5200003, "nome": "Enclave Teste"}, {"id": 5200004, "nome": "Cidade Quatro Teste"}]


class IBGE:
    """O IBGE de mentira: guarda cada endereço pedido; `fora` faz todo pedido cair, como a rede."""

    def __init__(self):
        self.pedidos, self.fora = [], False

    def __call__(self, url):
        self.pedidos.append(url)
        if self.fora:
            raise ConnectionError("IBGE fora do ar (teste)")
        return MALHA if "/malhas/" in url else NOMES


@pytest.fixture(autouse=True)
def _memoria_limpa():
    MU.limpar()
    yield
    MU.limpar()


def test_acha_a_cidade_pelo_poligono(tmp_path):
    ibge = IBGE()
    assert MU.cidade(-16.5123, -48.5321, "GO", pasta=tmp_path, baixar=ibge) == "Cidade Dois Teste"
    assert MU.cidade(-16.8123, -49.8321, "GO", pasta=tmp_path, baixar=ibge) == "Cidade Um Teste"
    # o buraco do 1º é o enclave: o ponto nele é do enclave, não do 1º
    assert MU.cidade(-16.5123, -49.5321, "GO", pasta=tmp_path, baixar=ibge) == "Enclave Teste"
    # o município em dois pedaços: os dois valem
    assert MU.cidade(-16.7, -47.7, "GO", pasta=tmp_path, baixar=ibge) == "Cidade Quatro Teste"
    assert MU.cidade(-16.7, -46.7, "GO", pasta=tmp_path, baixar=ibge) == "Cidade Quatro Teste"
    assert len(ibge.pedidos) == 2                                    # a malha e os nomes, uma vez só para o estado


def test_fora_de_todos_devolve_none(tmp_path):
    ibge = IBGE()
    assert MU.cidade(-10.0, -40.0, "GO", pasta=tmp_path, baixar=ibge) is None           # centenas de km dali
    assert MU.cidade(-16.75, -47.25, "GO", pasta=tmp_path, baixar=ibge) is None         # entre os pedaços, a 27 km
    # a 1 km da borda de fora (o litoral simplificado da malha "mínima" põe a praia no mar): o de borda mais perto
    assert MU.cidade(-16.7, -46.49, "GO", pasta=tmp_path, baixar=ibge) == "Cidade Quatro Teste"
    # a UF que não é UF nem vai ao IBGE (ela entra no endereço)
    antes = len(ibge.pedidos)
    for uf in ("G/O", "XX", "", None, "../GO"):
        assert MU.cidade(-16.5, -48.5, uf, pasta=tmp_path, baixar=ibge) is None, uf
    assert len(ibge.pedidos) == antes
    # a sigla em minúscula vale
    assert MU.cidade(-16.5123, -48.5321, "go", pasta=tmp_path, baixar=ibge) == "Cidade Dois Teste"


def test_a_malha_fica_no_disco_e_nao_baixa_de_novo(tmp_path):
    ibge = IBGE()
    assert MU.cidade(-16.5123, -48.5321, "GO", pasta=tmp_path, baixar=ibge) == "Cidade Dois Teste"
    arq = tmp_path / "equipe" / "ibge" / "GO.json"
    assert arq.exists() and len(ibge.pedidos) == 2
    assert MU.cidade(-16.8123, -49.8321, "GO", pasta=tmp_path, baixar=ibge) == "Cidade Um Teste"
    assert len(ibge.pedidos) == 2
    # o processo reiniciou: a memória some, o disco fica, e o IBGE não é chamado
    MU.limpar()
    assert MU.cidade(-16.5123, -48.5321, "GO", pasta=tmp_path, baixar=ibge) == "Cidade Dois Teste"
    assert len(ibge.pedidos) == 2
    dado = json.loads(arq.read_text(encoding="utf-8"))
    assert dado["uf"] == "GO" and len(dado["municipios"]) == 4

    def baixado_ha(dias):
        """O arquivo do disco baixado há `dias` dias, e o processo reiniciado (só o disco vale)."""
        dado["baixado_em"] = (datetime.now(timezone.utc) - timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%SZ")
        arq.write_text(json.dumps(dado), encoding="utf-8")
        MU.limpar()
    # com 29 dias ainda vale
    baixado_ha(29)
    assert MU.cidade(-16.5123, -48.5321, "GO", pasta=tmp_path, baixar=ibge) == "Cidade Dois Teste"
    assert len(ibge.pedidos) == 2
    # com mais de 30 dias baixa de novo, e o arquivo novo vale outros 30
    baixado_ha(31)
    assert MU.cidade(-16.5123, -48.5321, "GO", pasta=tmp_path, baixar=ibge) == "Cidade Dois Teste"
    assert len(ibge.pedidos) == 4
    novo = datetime.strptime(json.loads(arq.read_text(encoding="utf-8"))["baixado_em"], "%Y-%m-%dT%H:%M:%SZ")
    assert datetime.now(timezone.utc) - novo.replace(tzinfo=timezone.utc) < timedelta(minutes=5)
    # o arquivo estragado (a queda no meio da gravação) é como nenhum: baixa de novo, sem quebrar
    arq.write_text("{quebrado", encoding="utf-8")
    MU.limpar()
    assert MU.cidade(-16.5123, -48.5321, "GO", pasta=tmp_path, baixar=ibge) == "Cidade Dois Teste"
    assert len(ibge.pedidos) == 6


def test_ibge_fora_do_ar_nao_quebra_o_mapa(tmp_path):
    ibge = IBGE()
    ibge.fora = True
    assert MU.cidade(*FORA, "GO", pasta=tmp_path, baixar=ibge) is None
    # a próxima abertura do mapa, logo depois, não espera o IBGE de novo
    assert MU.cidade(*FORA, "GO", pasta=tmp_path, baixar=ibge) is None and len(ibge.pedidos) == 1
    # a situação segue, só com o estado
    estado = {"ultimo": {"instante": "2026-11-08T14:55:00Z", "lat": FORA[0], "lon": FORA[1], "mov": False},
              "permissao": "ok", "desde": None}
    s = SI.situacao(estado, USINAS, AGORA, cidade=lambda la, lo, uf: MU.cidade(la, lo, uf, pasta=tmp_path, baixar=ibge))
    assert (s["chave"], s["uf"], s["cidade"]) == ("fora_usina", "GO", None)
    # a função da cidade que quebra também não derruba a situação
    def quebra(la, lo, uf):
        raise RuntimeError("quebrou")
    assert SI.situacao(estado, USINAS, AGORA, cidade=quebra)["cidade"] is None
    # com o IBGE de volta (outra pasta, sem a falha guardada), a cidade vem; e só para o parado fora de usina
    ok = IBGE()
    cid = lambda la, lo, uf: MU.cidade(la, lo, uf, pasta=tmp_path / "outra", baixar=ok)  # noqa: E731
    assert SI.situacao(estado, USINAS, AGORA, cidade=cid)["cidade"] == "Cidade Um Teste"
    andando = dict(estado, ultimo=dict(estado["ultimo"], mov=True))
    assert SI.situacao(andando, USINAS, AGORA, cidade=cid)["cidade"] is None


def test_o_ibge_fora_com_a_malha_vencida_no_disco_fica_com_a_vencida(tmp_path):
    ibge = IBGE()
    MU.cidade(-16.5123, -48.5321, "GO", pasta=tmp_path, baixar=ibge)
    arq = tmp_path / "equipe" / "ibge" / "GO.json"
    dado = json.loads(arq.read_text(encoding="utf-8"))
    dado["baixado_em"] = "2026-01-01T00:00:00Z"
    arq.write_text(json.dumps(dado), encoding="utf-8")
    MU.limpar()
    ibge.fora = True
    assert MU.cidade(-16.5123, -48.5321, "GO", pasta=tmp_path, baixar=ibge) == "Cidade Dois Teste"
    assert len(ibge.pedidos) == 3                                    # tentou (só a malha) e ficou com a do disco


def test_a_url_nunca_leva_a_coordenada(tmp_path):
    ibge = IBGE()
    lat, lon = FORA
    MU.cidade(lat, lon, "GO", pasta=tmp_path, baixar=ibge)
    assert ibge.pedidos == [
        "https://servicodados.ibge.gov.br/api/v3/malhas/estados/GO?formato=application/vnd.geo+json"
        "&intrarregiao=municipio&qualidade=minima",
        "https://servicodados.ibge.gov.br/api/v1/localidades/estados/GO/municipios"]
    for url in ibge.pedidos:
        for v in (lat, lon):
            for texto in (str(v), str(abs(v)), f"{abs(v):.2f}", f"{abs(v):.1f}".replace(".", ","), "567381",
                          "187643"):
                assert texto not in url, (url, texto)

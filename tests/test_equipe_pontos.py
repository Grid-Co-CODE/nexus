"""Mapa de equipe: os pontos do Nexus Field (validacao, janela de trabalho, cifra e diario do dia). Dados ficticios."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from nexus.campo.equipe import CAB_PONTOS
from nexus.campo.equipe.pontos import Diario, aceitar, linha_do_banco
from nexus.cadastro.cifra import Cofre, gerar_chave

AGORA = datetime(2026, 11, 8, 23, 0, tzinfo=timezone.utc)   # 20:00 em Brasilia


@pytest.fixture
def cofre():
    return Cofre(gerar_chave())


def _t(h, m=0, dia=8):
    """Milissegundos UTC de dia/11/2026 h:m UTC."""
    return int(datetime(2026, 11, dia, h, m, tzinfo=timezone.utc).timestamp() * 1000)


def _p(t, **kw):
    p = {"t": t, "lat": -23.5505, "lon": -46.6333, "prec": 8.5, "vel": 1.2, "mov": True}
    p.update(kw)
    return p


def _lote(pontos, fuso=-180):
    return {"aparelho": "A1", "fuso": fuso, "pontos": pontos}


def _agora_tarde():
    return datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


def test_a_janela_e_das_6h_as_22h_na_hora_do_tecnico(cofre):
    # 08:59 UTC = 05:59 em Brasilia; 09:00 = 06:00; 00:59 do dia seguinte = 21:59; 01:00 = 22:00
    agora = _agora_tarde()
    ok = lambda t, fuso=-180: len(aceitar(7, _lote([_p(t)], fuso), agora, cofre)) == 1
    assert not ok(_t(8, 59)) and ok(_t(9, 0))
    assert ok(_t(0, 59, dia=8))
    assert not ok(_t(1, 0, dia=8))
    # o mesmo t com Mato Grosso (-240) muda de lado: 09:00 UTC = 05:00 la (sai); 01:00 UTC = 21:00 la (entra)
    assert not ok(_t(9, 0), -240)
    assert ok(_t(1, 0, dia=8), -240)


def test_ponto_com_mais_de_7_dias_ou_no_futuro_sai(cofre):
    agora = datetime(2026, 11, 8, 15, 0, tzinfo=timezone.utc)
    velho = int((agora - timedelta(days=7, minutes=1)).timestamp() * 1000)
    quase = int((agora - timedelta(days=6, hours=20)).timestamp() * 1000)
    futuro = int((agora + timedelta(minutes=6)).timestamp() * 1000)
    leve = int((agora + timedelta(minutes=4)).timestamp() * 1000)   # relogio do celular adiantado
    out = aceitar(7, _lote([_p(velho), _p(quase), _p(futuro), _p(leve)]), agora, cofre)
    assert len(out) == 2


def test_ponto_invalido_sai_e_o_resto_entra(cofre):
    ruins = [_p(_t(15), lat=91), _p(_t(15), lon=-181), _p(_t(15), prec=-1), _p("abc"), _p(_t(15), mov="talvez"),
             _p(_t(15), lat=None),
             # o inteiro que não cabe num float levanta OverflowError no float(): sai o ponto, não o lote
             _p(10 ** 400), _p(_t(15), lat=10 ** 400), _p(_t(15), prec=10 ** 400)]
    bom = _p(_t(15, 5))
    out = aceitar(7, _lote(ruins + [bom]), _agora_tarde(), cofre)
    assert len(out) == 1 and out[0]["instante"] == "2026-11-08T15:05:00Z"
    # a velocidade é opcional: a gigante vira "sem velocidade" e o ponto entra
    (p,) = aceitar(7, _lote([_p(_t(15, 7), vel=10 ** 400)]), _agora_tarde(), cofre)
    assert p["vel_ms"] is None


def test_fuso_ausente_ou_absurdo_descarta_o_lote(cofre):
    assert aceitar(7, {"pontos": [_p(_t(15))]}, _agora_tarde(), cofre) == []
    assert aceitar(7, _lote([_p(_t(15))], fuso=900), _agora_tarde(), cofre) == []
    assert aceitar(7, _lote([_p(_t(15))], fuso="x"), _agora_tarde(), cofre) == []
    assert aceitar(7, _lote([_p(_t(15))], fuso=10 ** 400), _agora_tarde(), cofre) == []


def test_lote_com_mais_de_200_pontos_e_recusado(cofre):
    with pytest.raises(ValueError):
        aceitar(7, _lote([_p(_t(15) + i) for i in range(201)]), _agora_tarde(), cofre)
    assert len(aceitar(7, _lote([_p(_t(15) + i) for i in range(200)]), _agora_tarde(), cofre)) == 200


def test_o_mesmo_ponto_entra_uma_vez(cofre, tmp_path):
    lote = _lote([_p(_t(15)), _p(_t(15, 1))])
    d = Diario(tmp_path, cofre, agora=_agora_tarde())
    a = aceitar(7, lote, _agora_tarde(), cofre)
    d.acrescentar(a)
    b = aceitar(7, lote, _agora_tarde(), cofre)       # reenvio do mesmo lote
    assert [p["ponto_id"] for p in a] == [p["ponto_id"] for p in b]
    d.acrescentar(b)
    assert len(d.do_dia(date(2026, 11, 8))) == 2
    assert Diario(tmp_path, cofre, agora=_agora_tarde()).do_dia(date(2026, 11, 8)).__len__() == 2


def test_a_linha_do_banco_nao_tem_coordenada(cofre):
    p = aceitar(7, _lote([_p(_t(15))]), _agora_tarde(), cofre)[0]
    linha = linha_do_banco(p)
    assert len(linha) == len(CAB_PONTOS)
    assert linha[0] == p["ponto_id"] and linha[1] == 20261108 and linha[3] == 7
    texto = json.dumps(linha)
    assert "-23.55" not in texto and "-46.63" not in texto
    dado = json.loads(cofre.decifrar(linha[4], f"equipe/ponto/{p['ponto_id']}"))
    assert dado == {"lat": -23.5505, "lon": -46.6333, "prec_m": 8.5, "vel_ms": 1.2, "mov": True}


def test_data_id_e_o_dia_de_brasilia(cofre):
    # 00:30 UTC do dia 9 ainda e dia 8 em Brasilia (21:30)
    p = aceitar(7, _lote([_p(_t(0, 30, dia=9))]), _agora_tarde(), cofre)[0]
    assert p["data_id"] == 20261108


def test_o_diario_sobrevive_ao_reinicio(cofre, tmp_path):
    d = Diario(tmp_path, cofre, agora=_agora_tarde())
    d.acrescentar(aceitar(7, _lote([_p(_t(15)), _p(_t(16), lat=-10.0)]), _agora_tarde(), cofre))
    d.acrescentar(aceitar(9, _lote([_p(_t(14))]), _agora_tarde(), cofre))
    novo = Diario(tmp_path, cofre, agora=_agora_tarde())
    assert novo.ultimos(_agora_tarde()) == d.ultimos(_agora_tarde())
    assert novo.ultimos(_agora_tarde())[7]["lat"] == -10.0
    for arq in (tmp_path / "equipe").glob("pontos_*.jsonl"):
        bruto = arq.read_text(encoding="utf-8")
        # a chave JSON com as aspas: o base64 da cifra nunca tem aspas, e o `lat` solto aparecia nele ao acaso (~0,1%)
        assert "-23.55" not in bruto and '"lat"' not in bruto


def test_linha_corrompida_e_pulada_e_contada(cofre, tmp_path):
    d = Diario(tmp_path, cofre, agora=_agora_tarde())
    d.acrescentar(aceitar(7, _lote([_p(_t(15))]), _agora_tarde(), cofre))
    arq = next((tmp_path / "equipe").glob("pontos_*.jsonl"))
    with open(arq, "a", encoding="utf-8") as f:
        f.write("lixo-que-nao-decifra\n")
    novo = Diario(tmp_path, cofre, agora=_agora_tarde())
    assert len(novo.do_dia(date(2026, 11, 8))) == 1 and novo.linhas_ruins == 1


def test_apagar_velhos_tira_o_arquivo_de_mais_de_7_dias(cofre, tmp_path):
    d = Diario(tmp_path, cofre, agora=_agora_tarde())
    d.acrescentar(aceitar(7, _lote([_p(_t(15, dia=1))]), datetime(2026, 11, 2, 12, tzinfo=timezone.utc), cofre))
    d.acrescentar(aceitar(7, _lote([_p(_t(15))]), _agora_tarde(), cofre))
    d.apagar_velhos(date(2026, 11, 9))
    nomes = sorted(a.name for a in (tmp_path / "equipe").glob("pontos_*.jsonl"))
    assert nomes == ["pontos_20261108.jsonl"]
    assert d.do_dia(date(2026, 11, 1)) == []


def test_o_diario_poda_sozinho_ao_carregar_e_na_virada_do_dia(cofre, tmp_path):
    """A guarda de 7 dias no disco e na memória não depende do gravador (revisão final de 08/11/2026: só ele chamava o
    `apagar_velhos`, e numa máquina sem NEXUS_EQUIPE_GRAVA=1 o diário guardaria a trilha para sempre). Fica o dia de
    hoje e os 6 de antes: o ponto mais velho que sobra tem menos de 7 dias."""
    def em(dia, h=12):
        return datetime(2026, 11, dia, h, tzinfo=timezone.utc)
    d = Diario(tmp_path, cofre, agora=em(2))
    d.acrescentar(aceitar(7, _lote([_p(_t(15, dia=1))]), em(2), cofre))
    d.acrescentar(aceitar(7, _lote([_p(_t(15, dia=5))]), em(6), cofre))
    # o boot de 07/11 ainda tem o 01/11: é o 7º dia, e o ponto dele tem menos de 6 dias
    d = Diario(tmp_path, cofre, agora=em(7))
    assert d.do_dia(date(2026, 11, 1)) and d.do_dia(date(2026, 11, 5))
    d.podar(em(7, 23))                                      # o mesmo dia de Brasília: nada sai
    assert d.do_dia(date(2026, 11, 1))
    d.podar(em(8, 3))                                       # 00:00 de Brasília do dia 8: o dia 01/11 sai
    assert d.do_dia(date(2026, 11, 1)) == [] and d.do_dia(date(2026, 11, 5))
    assert sorted(a.name for a in (tmp_path / "equipe").glob("pontos_*.jsonl")) == ["pontos_20261105.jsonl"]
    # e o boot de muito depois nem lê o que passou de 7 dias: o arquivo sai do disco
    novo = Diario(tmp_path, cofre, agora=em(20))
    assert novo.do_dia(date(2026, 11, 5)) == [] and not list((tmp_path / "equipe").glob("pontos_*.jsonl"))

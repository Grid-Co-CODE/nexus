"""A foto diária dos extintores fora do em dia (24/11/2026, `nexus/hseq/extintores_historico.py`): só as mudanças, com a
foto completa no 1º dia de cada mês (a escolha da Segurança depois da medida no banco real). O livro é um arquivo
(`NEXUS_HSEQ_EXTINTORES_HISTORICO_ARQUIVO`): nada vai ao banco.

O caso é o do `com_livro` de test_hseq_extintores.py, no dia 09/10/2026: ALT01 atrasado (a recarga), ALT02 perto de
vencer e sem atualização, ALT03 e o de Irecê em dia, BWK01 sem validade e nunca conferido, COR01 atrasado (o
hidrostático) e sem atualização."""
import json
import logging
from datetime import date, datetime, timedelta, timezone

import pytest
from test_campo_visao import _aba, banco  # noqa: F401  (banco é fixture)
from test_hseq_extintores import LIVRO, _ext, com_livro  # noqa: F401

from nexus.campo import visao
from nexus.hseq import decisoes as DEC
from nexus.hseq import email_semanal as EM
from nexus.hseq import extintores as EXT
from nexus.hseq import extintores_historico as H

BRT = timezone(timedelta(hours=-3))
FORA = {"ALT100-INFC1-PPCI-EXT01", "ALT100-INFC1-PPCI-EXT02", "BWK100-INFC1-PPCI-EXT01", "COR100-INFC1-PPCI-EXT01"}


def _hora(dia, h, m=0):
    return datetime(2026, 10, dia, h, m, tzinfo=BRT)


@pytest.fixture
def livro(app, tmp_path):
    arq, dec = tmp_path / "historico.json", tmp_path / "decisoes.json"
    app.config["NEXUS_HSEQ_EXTINTORES_HISTORICO_ARQUIVO"] = str(arq)
    app.config["NEXUS_HSEQ_DECISOES_ARQUIVO"] = str(dec)
    DEC.limpar()
    yield arq, dec
    DEC.limpar()


def _abas(arq):
    return json.loads(arq.read_text(encoding="utf-8"))


def _publicar(app, agora):
    with app.app_context():
        return H.publicar(app.config, agora)


def _no_dia(monkeypatch, dia):
    monkeypatch.setattr(visao, "_agora", lambda: _hora(dia, 10))
    visao.limpar()


def test_grava_uma_vez_por_dia_e_so_depois_das_6(com_livro, app, livro):
    arq, _dec = livro
    assert _publicar(app, _hora(9, 5, 59)) == {"gravou": False, "dia": "2026-10-09", "erro": ""}
    assert not arq.exists()                                             # antes das 06:00, nada
    r = _publicar(app, _hora(9, 6, 10))
    assert (r["gravou"], r["completa"], r["linhas"]) == (True, True, 4)  # o 1º dia do livro é a foto completa
    assert _publicar(app, _hora(9, 18))["gravou"] is False               # o dia já está no livro: não grava de novo
    d = _abas(arq)
    assert len(d[H.ABA]) == 4 and len(d[H.ABA_DIA]) == 1
    assert d[H.ABA_DIA][0] | {"gravada_em": ""} == {"data_id": 20261009, "gravada_em": "", "completa": "sim",
                                                   "extintores": 6, "fora_do_em_dia": 4, "linhas": 4}


def test_leva_so_os_que_nao_estao_em_dia_e_nada_pessoal(com_livro, app, livro):
    arq, _dec = livro
    _publicar(app, _hora(9, 7))
    linhas = _abas(arq)[H.ABA]
    assert {x["codigo"] for x in linhas} == FORA                         # ALT03 e Irecê (em dia) ficam fora
    assert all(set(x) == set(H.CAB) for x in linhas)                     # só as colunas do contrato
    por = {x["codigo"]: x for x in linhas}
    assert (por["ALT100-INFC1-PPCI-EXT01"]["situacao"], por["ALT100-INFC1-PPCI-EXT01"]["venceu"]) == ("atrasado", "recarga")
    assert (por["COR100-INFC1-PPCI-EXT01"]["venceu"], por["COR100-INFC1-PPCI-EXT01"]["sem_atualizacao"]) == (
        "hidrostático", "sim")
    assert (por["ALT100-INFC1-PPCI-EXT02"]["situacao"], por["ALT100-INFC1-PPCI-EXT02"]["sem_atualizacao"]) == (
        "perto", "sim")
    assert por["BWK100-INFC1-PPCI-EXT01"]["situacao"] == "sem_validade"
    texto = arq.read_text(encoding="utf-8")
    for pessoal in ("@", "exemplo.test", "Thopen", "Altair", "HMAC", "hmac", "Técnico"):   # sem pessoa nem cliente
        assert pessoal not in texto, pessoal


def test_respeita_as_exclusoes_da_seguranca(com_livro, app, livro):
    """A foto bate com a tela: o extintor que a Segurança excluiu sai dela."""
    arq, dec = livro
    dec.write_text(json.dumps({DEC.ABA_EXC: [{"decidida_em": "2026-10-08T09:00:00-03:00", "data_id": 20261008,
                                              "usina_id": 1, "codigo": "ALT100-INFC1-PPCI-EXT01",
                                              "motivo": "retirado"}]}), encoding="utf-8")
    _publicar(app, _hora(9, 7))
    assert {x["codigo"] for x in _abas(arq)[H.ABA]} == FORA - {"ALT100-INFC1-PPCI-EXT01"}


def test_a_leitura_que_falha_nao_grava(com_livro, app, livro, monkeypatch):
    arq, _dec = livro
    monkeypatch.setattr(DEC, "ler", lambda cfg, forcar=False: {"erro": "ConnectionError: fora", "exclusoes": []})
    r = _publicar(app, _hora(9, 7))
    assert r["gravou"] is False and "decisões sem leitura" in r["erro"] and not arq.exists()


def test_depois_do_1o_dia_so_as_mudancas_e_o_dia_se_reconstroi(com_livro, app, livro, monkeypatch):
    arq, dec = livro
    _publicar(app, _hora(9, 7))
    # 10/10: o ALT02 foi conferido (sai do "sem atualização", segue perto de vencer) e o ALT01 foi excluído
    novo = [dict(x) for x in LIVRO]
    novo[1]["Última conferência"] = "2026-10-10"
    _aba(com_livro, EXT.LIVRO, EXT.ABA, novo)
    dec.write_text(json.dumps({DEC.ABA_EXC: [{"decidida_em": "2026-10-10T08:00:00-03:00", "data_id": 20261010,
                                              "usina_id": 1, "codigo": "ALT100-INFC1-PPCI-EXT01",
                                              "motivo": "retirado"}]}), encoding="utf-8")
    DEC.limpar()
    _no_dia(monkeypatch, 10)
    r = _publicar(app, _hora(10, 7))
    assert (r["gravou"], r["completa"], r["linhas"]) == (True, False, 2)
    d = _abas(arq)
    mud = {x["codigo"]: x for x in d[H.ABA] if x["tipo"] == "mudanca"}
    assert mud["ALT100-INFC1-PPCI-EXT01"]["situacao"] == "fora"           # saiu da tela (excluído)
    assert (mud["ALT100-INFC1-PPCI-EXT02"]["situacao"], mud["ALT100-INFC1-PPCI-EXT02"]["sem_atualizacao"]) == (
        "perto", "nao")
    assert set(H.estado_em(d, date(2026, 10, 10))) == FORA - {"ALT100-INFC1-PPCI-EXT01"}
    assert set(H.estado_em(d, date(2026, 10, 9))) == FORA                 # o dia de antes segue o mesmo
    assert H.estado_em(d, date(2026, 10, 8)) is None                      # antes da 1ª foto: não há
    assert H.dias_gravados(d) == {date(2026, 10, 9), date(2026, 10, 10)}  # o dia fora daqui é lacuna


def test_no_1o_dia_do_mes_a_foto_completa_e_a_conferencia(caplog):
    """No dia 1 grava a foto inteira; se o estado montado pelas mudanças não bate, o log diz quantos (só o número)."""
    um = {"codigo": "X1", "usina_id": 1, "situacao": "atrasado", "vence_qual": "recarga", "sem_atualizacao": False}
    dois = dict(um, codigo="X2", situacao="perto", vence_qual="recarga")
    cru = {H.ABA: [dict(H.do_extintor(um), data_id=20261031, tipo="completa")], H.ABA_DIA: []}
    with caplog.at_level(logging.WARNING, logger="nexus.hseq"):
        novas, dia = H.montar_dia(cru, [um, dois], date(2026, 11, 1))
    assert dia["completa"] == "sim" and {x["codigo"] for x in novas} == {"X1", "X2"}
    assert {x["tipo"] for x in novas} == {"completa"}
    assert "1 extintores divergiram" in caplog.text and "X2" not in caplog.text
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="nexus.hseq"):
        H.montar_dia(cru, [um], date(2026, 11, 1))                         # bate: nenhum aviso
    assert "divergiram" not in caplog.text


def test_quem_liga_e_a_chave_propria(app, monkeypatch):
    """O laço liga pelo `email_semanal.ligar` (o servir.py é do Levi), ANTES do retorno antecipado do e-mail, com chave
    própria; não liga no PC (NEXUS_CAMPO_AQUECER=0)."""
    assert H.ligado({}) and not H.ligado({"NEXUS_HSEQ_EXT_FOTO_AUTO": "0"})
    assert not H.ligado({"NEXUS_CAMPO_AQUECER": "0"})
    chamou = []
    monkeypatch.setattr(H, "ligar", lambda a: chamou.append(a))
    monkeypatch.setitem(app.config, "NEXUS_HSEQ_EMAIL_AUTO", "0")         # o e-mail desligado não leva a foto junto
    EM.ligar(app)
    assert chamou == [app] and EM._LACO["thread"] is None


def test_o_livro_esta_no_catalogo_antes_da_1a_gravacao():
    from nexus.dados import catalogo
    l = catalogo.LIVRO_POR_NOME[H.LIVRO]
    assert l.abas == (H.ABA, H.ABA_DIA) and l.so_cresce
    f = catalogo.POR_ID["extintor_dia"]
    assert f.livro == f"{H.LIVRO} · {H.ABA}" and f.chave == ("data_id", "codigo")
    assert catalogo.POR_ID["foto_extintores_dia"].livro == f"{H.LIVRO} · {H.ABA_DIA}"
    from nexus.dados import explica
    for fid in ("extintor_dia", "foto_extintores_dia"):
        r, p = explica.RESUMO[fid], explica.PARA_QUE[fid]
        assert 15 <= len(r) <= 70 and not r.endswith(".") and len(p) >= 80 and p.endswith("."), fid

"""Torre COS: a tela Relógios de prazo (23/11/2026) — o que está com o prazo de 15 min correndo ou vencido agora?

O Andamento da Ronda COS calcula e escala (`GET /api/nexus/<cliente>/prazos`); a tela só lê. Nada aqui vai à rede, e os
dados são fictícios."""
import pytest

from nexus.cos import andamento as AND
from nexus.cos import prazos as PZ

CHAVE = "chave-de-teste-do-andamento"


def _prazo(tipo="ALARME_SEM_OCORRENCIA", nome="Usina Exemplo Um", o_que="1 de 13 inversores sem gerar", minutos=5,
           resolvido=None, dentro=None, escalado=None, os=None, inicio="2026-11-23T09:00:00-03:00"):
    return {"tipo": tipo, "rotulo": PZ.TIPOS[tipo], "usina": "EX-UM100", "nome": nome, "os": os, "o_que": o_que,
            "inicio": inicio, "vence_em": "2026-11-23T09:15:00-03:00", "escalado_em": escalado, "resolvido_em": resolvido,
            "minutos": minutos, "dentro_do_prazo": dentro}


def _dados(abertos, recentes=(), ligado=True, envio="ensaio", **mudar):
    tudo = list(abertos) + list(recentes)
    conta = lambda xs: {"total": len(xs), "dentro": sum(1 for x in xs if x["dentro_do_prazo"] is True),
                        "fora": sum(1 for x in xs if x["dentro_do_prazo"] is False),
                        "abertos": sum(1 for x in xs if x["resolvido_em"] is None)}
    resumo = {"total": conta(tudo), **{t: conta([x for x in tudo if x["tipo"] == t]) for t in PZ.TIPOS}}
    d = {"versao": 1, "cliente": "Cliente A", "gerado_em": "2026-11-23T09:40:00-03:00", "ligado": ligado, "prazo_min": 15,
         "envio": envio, "desde": "2026-11-23T08:00:00-03:00", "abertos": list(abertos), "recentes": list(recentes),
         "resumo": resumo}
    d.update(mudar)
    return d


def test_o_painel_poe_o_vencido_primeiro_e_diz_quanto_passou_ou_falta():
    vencido = _prazo(nome="Vencida", minutos=40, dentro=False, escalado="2026-11-23T09:15:00-03:00")
    correndo = _prazo(nome="Correndo", minutos=6, inicio="2026-11-23T09:34:00-03:00")
    parado = _prazo(tipo="VOLTOU_SEM_NORMALIZAR", nome="Parada", minutos=10, resolvido="2026-11-23T09:10:00-03:00", dentro=True)
    p = PZ.painel(AND.Leitura("Cliente A", _dados([correndo, vencido], [parado])))
    assert [l.nome for l in p.abertos] == ["Vencida", "Correndo"]
    assert [(l.prazo, l.tom, l.escalado) for l in p.abertos] == [("vencido há 25 min", "critico", True),
                                                                  ("faltam 9 min", "alerta", False)]
    assert [(l.prazo, l.tom) for l in p.recentes] == [("no prazo (10 min)", "ok")]
    assert p.vencidos_agora == 1 and p.pct_no_prazo == 50


def test_dias_fora_das_opcoes_cai_no_padrao():
    assert PZ.dias_pedidos("7") == 7 and PZ.dias_pedidos("99") == 1 and PZ.dias_pedidos(None) == 1


def test_contrato_de_outra_versao_e_recusado():
    with pytest.raises(AND.FonteErro):
        AND.validar_prazos({"versao": 2, "abertos": [], "recentes": [], "resumo": {}})
    with pytest.raises(AND.FonteErro):
        AND.validar_prazos({"versao": 1, "abertos": None, "recentes": [], "resumo": {}})


@pytest.fixture
def ligada(app):
    app.config.update(NEXUS_COS_ANDAMENTO_URL="http://andamento.exemplo:3002", NEXUS_COS_ANDAMENTO_CHAVE=CHAVE,
                      NEXUS_COS_ANDAMENTO_CLIENTES="Cliente A,Cliente B")
    return app


def _servir(monkeypatch, respostas: dict):
    pedidos = []

    def pedir(f, caminho, timeout=AND.TIMEOUT_S):
        pedidos.append(caminho)
        r = respostas.get(caminho)
        if r is None:
            raise AND.FonteErro("o Andamento não tem este cliente, ou a rota do Nexus está desligada lá")
        return r
    monkeypatch.setattr(AND, "_pedir", pedir)
    return pedidos


def test_tela_mostra_o_que_corre_e_avisa_do_ensaio(ligada, logado, monkeypatch):
    vencido = _prazo(nome="Usina Vencida", minutos=40, dentro=False, escalado="2026-11-23T09:15:00-03:00", os="20145")
    pedidos = _servir(monkeypatch, {"/api/nexus/Cliente%20A/prazos?dias=1": _dados([vencido])})
    html = logado.get("/t/cos/prazos").get_data(as_text=True)
    assert pedidos == ["/api/nexus/Cliente%20A/prazos?dias=1"]
    assert "Usina Vencida" in html and "OS 20145" in html and "vencido há 25 min" in html
    assert "Ensaio." in html and "Nenhum relógio parado no período." in html


def test_tela_diz_quando_os_relogios_nao_estao_ligados_e_quando_a_fonte_esta_desligada(ligada, app, logado, monkeypatch):
    _servir(monkeypatch, {"/api/nexus/Cliente%20A/prazos?dias=7": _dados([], ligado=False)})
    html = logado.get("/t/cos/prazos?dias=7").get_data(as_text=True)
    assert "Os relógios não estão ligados para Cliente A." in html and "Nenhum relógio correndo agora." in html
    app.config.update(NEXUS_COS_ANDAMENTO_URL="", NEXUS_COS_ANDAMENTO_CHAVE="")
    assert "não está ligada neste servidor" in logado.get("/t/cos/prazos").get_data(as_text=True)

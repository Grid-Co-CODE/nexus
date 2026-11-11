"""Torre COS: o Desempenho da equipe (05/11/2026) — as mesas estão dentro do MTTA e do aviso no prazo?

MTTA (início → a hora em que o COS viu), informado no prazo (o veredito da tela Ocorrências) e religamento remoto (a
regra da tela Religamentos), por cliente e por turno, sem nome de operador; as mesas como os conjuntos de clientes das
carteiras (nexus/cos/desempenho.py). Nada aqui vai à rede, e os dados são fictícios."""
from datetime import datetime, timedelta

import pytest

from nexus.cos import andamento as AND
from nexus.cos import desempenho as DE
from nexus.cos import mesa as ME

CHAVE = "chave-de-teste-do-andamento"
AGORA = datetime(2026, 11, 5, 10, 0, tzinfo=AND._BRT)
ENVIO = {"grupos": "regioes", "desde": "2026-10-01T00:00:00-03:00"}


def _oc(registro, inicio, viu=None, informado_min=None, remoto=False, aberta=False):
    """Uma ocorrência do ciclo: `viu` e `informado_min` em minutos depois do início."""
    i = AND.instante(inicio)
    em = lambda m: (i + timedelta(minutes=m)).isoformat()  # noqa: E731
    return {"registro": registro, "os": "90001", "usina": "Usina Exemplo Um", "usina_codigo": "EX-UM100",
            "equipamentos": [], "tipo_falha": "Desligamento de usina", "severidade": "CRITICO",
            "estado": "TRATATIVA_REMOTA" if aberta else "NORMALIZADO", "aberta": aberta, "inicio": inicio,
            "registrada_em": inicio, "detectada_em": em(viu) if viu is not None else None, "os_aberta_em": None,
            "cliente_informado": {"em": em(informado_min), "por": "flash"} if informado_min is not None else None,
            "campo": {"acionado_em": None, "acionado_por": None, "escalonado_em": None},
            "normalizada": None if aberta else {"fim": em(40), "declarada_em": em(41), "por": "pessoa"},
            "volta_informada": None, "encerrada_em": None, "religamento": {"remoto": remoto, "local": False}}


def _ciclo(cliente, ocs, **mudar):
    d = {"versao": 1, "cliente": cliente, "gerado_em": "2026-11-05T10:00:00-03:00", "desde": "2026-10-29T10:00:00-03:00",
         "envio_ao_cliente": ENVIO, "truncado": False, "ocorrencias": ocs}
    d.update(mudar)
    return d


A = _ciclo("Cliente A", [
    _oc("a1", "2026-11-04T08:00:00-03:00", viu=4, informado_min=10, remoto=True),     # dia
    _oc("a2", "2026-11-04T14:00:00-03:00", viu=10, informado_min=25),                 # dia: aviso fora do prazo
    _oc("a3", "2026-11-04T20:00:00-03:00", viu=30, informado_min=12, remoto=True),    # noite
    _oc("a4", "2026-11-05T02:00:00-03:00", informado_min=5),                          # noite, sem a hora em que viu
    _oc("a5", "2026-11-05T09:55:00-03:00", viu=-5, aberta=True),                      # dia, correndo; viu "antes"
])
B = _ciclo("Cliente B", [_oc("b1", "2026-11-04T19:00:00-03:00", viu=6, informado_min=8)])


def _painel(leituras=None, mesas=None, minha=None):
    return DE.painel(leituras or [AND.Leitura("Cliente A", A), AND.Leitura("Cliente B", B)], AGORA, mesas, minha)


def test_o_turno_e_o_da_ronda_cos_pela_hora_do_inicio():
    t = lambda h: DE.turno_de(datetime(2026, 11, 5, h, 0, tzinfo=AND._BRT))  # noqa: E731
    assert [t(h) for h in (0, 5, 6, 17, 18, 23)] == ["noite", "noite", "dia", "dia", "noite", "noite"]


def test_mtta_e_a_mediana_ate_o_cos_ver_sem_os_que_nao_tem_a_hora_nem_a_espera_negativa():
    p = _painel()
    a = next(c for c in p.clientes if c["cliente"] == "Cliente A")
    assert (a["total"]["mtta"], a["total"]["mtta_amostra"], a["total"]["ocorrencias"]) == (10, 3, 5)
    assert a["turnos"]["dia"]["mtta"] == 7 and a["turnos"]["noite"]["mtta"] == 30      # (4+10)/2 = 7; só a3
    assert p.total["mtta"] == 8 and p.total["mtta_amostra"] == 4                        # 4, 6, 10, 30


def test_informado_no_prazo_so_sobre_as_decididas():
    a = next(c for c in _painel().clientes if c["cliente"] == "Cliente A")["total"]
    # a1, a3 e a4 no prazo; a2 fora (25 min); a5 ainda corre os 15 min e fica fora da conta
    assert (a["informado_cumpriu"], a["informado_fora"], a["informado_correndo"], a["informado_pct"]) == (3, 1, 1, 75)


def test_religamento_remoto_das_normalizadas():
    a = next(c for c in _painel().clientes if c["cliente"] == "Cliente A")["total"]
    assert (a["remoto"], a["normalizadas"], a["remoto_pct"]) == (2, 4, 50)                # a5 está aberta


def test_por_turno_soma_os_clientes():
    p = _painel()
    assert p.turnos["dia"]["ocorrencias"] == 3 and p.turnos["noite"]["ocorrencias"] == 3   # b1 começou às 19h
    assert p.completo and p.com_deteccao


def test_as_mesas_somam_os_clientes_e_marcam_a_de_quem_entrou():
    mesas = [{"clientes": ["Cliente A"], "operadores": 2}, {"clientes": ["Cliente A", "Cliente B"], "operadores": 1},
             {"clientes": ["Cliente C"], "operadores": 1}]                                # C não foi lido: fica de fora
    p = _painel(mesas=mesas, minha=["Cliente B", "Cliente A"])
    assert [(m["clientes"], m["minha"], m["resumo"]["ocorrencias"]) for m in p.mesas] == [
        (["Cliente A"], False, 5), (["Cliente A", "Cliente B"], True, 6)]
    assert p.mesas[1]["resumo"]["mtta"] == 8


def test_cliente_sem_leitura_e_andamento_sem_a_hora_em_que_viu():
    sem_hora = _ciclo("Cliente A", [{k: v for k, v in o.items() if k != "detectada_em"} for o in A["ocorrencias"]])
    p = _painel([AND.Leitura("Cliente A", sem_hora), AND.Leitura("Cliente B", None, erro="o Andamento não respondeu")])
    assert not p.completo and not p.com_deteccao and p.total["mtta"] is None
    assert p.erros == [("Cliente B", "o Andamento não respondeu", False)]


# --- a tela ----------------------------------------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _limpa():
    AND.limpar_cache()
    yield
    AND.limpar_cache()


@pytest.fixture
def ligada(app, monkeypatch):
    app.config.update(NEXUS_COS_ANDAMENTO_URL="http://andamento.exemplo:3002", NEXUS_COS_ANDAMENTO_CHAVE=CHAVE,
                      NEXUS_COS_ANDAMENTO_CLIENTES="Cliente A,Cliente B")
    monkeypatch.setattr(AND, "agora", lambda: AGORA)
    return app


def test_a_tela(ligada, cliente, monkeypatch):
    ana = "ana.ficticia@exemplo.com"
    respostas = {
        "/api/nexus/Cliente%20A/ocorrencias?dias=7": A, "/api/nexus/Cliente%20B/ocorrencias?dias=7": B,
        "/api/nexus/Cliente%20A/ocorrencias?dias=30": A, "/api/nexus/Cliente%20B/ocorrencias?dias=30": B,
        "/api/nexus/carteiras": {"versao": 1, "carteiras": [
            {"pessoa": AND.chave_da_pessoa(ana, CHAVE), "clientes": ["Cliente A", "Cliente B"], "fora": []},
            {"pessoa": AND.chave_da_pessoa("bia@exemplo.com", CHAVE), "clientes": ["Cliente A"], "fora": []}]},
    }
    pedidos = []

    def pedir(f, caminho, timeout=AND.TIMEOUT_S):
        pedidos.append(caminho)
        return respostas[caminho]
    monkeypatch.setattr(AND, "_pedir", pedir)
    with cliente.session_transaction() as s:
        s["logado"], s["admin"], s["usuario"] = True, False, {"email": ana, "nome": "Ana Ficticia"}
    html = cliente.get("/t/cos/desempenho").get_data(as_text=True)
    assert "/api/nexus/Cliente%20A/ocorrencias?dias=7" in pedidos
    assert "8 min" in html and "4 de 6 com a hora em que o COS viu" in html
    assert "Cliente A · Cliente B" in html and 'cn-pill cn-info">sua mesa<' in html and "2 operador" not in html
    # a carteira dos outros não diz de quem é: nem o HMAC sai na tela
    assert AND.chave_da_pessoa("bia@exemplo.com", CHAVE) not in html and "bia@" not in html
    cliente.get("/t/cos/desempenho?dias=30")
    assert "/api/nexus/Cliente%20A/ocorrencias?dias=30" in pedidos


def test_a_fonte_desligada(app, logado):
    assert "não está ligada neste servidor" in logado.get("/t/cos/desempenho").get_data(as_text=True)


def test_mesa_e_desempenho_usam_a_mesma_conta_das_mesas():
    assert ME.mesas(AND.Leitura("", None), ["Cliente A"]) == []

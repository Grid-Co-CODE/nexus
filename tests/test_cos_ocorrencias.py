"""Torre COS: a tela Ocorrências (22/10/2026) — cada ocorrência cumpriu as cinco etapas no prazo?

O Andamento da Ronda COS diz quando cada etapa aconteceu (`GET /api/nexus/<cliente>/ocorrencias`); o prazo da spec R04 e
o veredito são do Nexus (nexus/cos/ocorrencias.py). Nada aqui vai à rede, e os dados são fictícios."""
from datetime import datetime

import pytest

from nexus.cos import andamento as AND
from nexus.cos import ocorrencias as OC

CHAVE = "chave-de-teste-do-andamento"
AGORA = datetime(2026, 10, 22, 15, 0, tzinfo=AND._BRT)
ENVIO = {"grupos": "regioes", "desde": "2026-10-21T13:04:00-03:00"}


def _oc(registro="r1", **mudar):
    o = {
        "registro": registro, "os": "90001", "usina": "Usina Exemplo Um", "usina_codigo": "EX-UM100", "regiao": "Região A",
        "equipamentos": [], "tipo_falha": "Desligamento de usina", "severidade": "CRITICO", "severidade_rotulo": "Crítico",
        "estado": "NORMALIZADO", "estado_rotulo": "Normalizada", "aberta": False,
        "inicio": "2026-10-22T09:00:00-03:00", "registrada_em": "2026-10-22T09:10:00-03:00", "registrada_por": "pessoa",
        "os_aberta_em": "2026-10-22T09:12:00-03:00",
        "cliente_informado": {"em": "2026-10-22T09:06:00-03:00", "por": "flash"},
        "campo": {"acionado_em": None, "acionado_por": None, "escalonado_em": None},
        "normalizada": {"fim": "2026-10-22T09:18:00-03:00", "declarada_em": "2026-10-22T09:20:00-03:00", "por": "religamento_remoto"},
        "volta_informada": {"em": "2026-10-22T09:21:00-03:00", "por": "flash"},
        "encerrada_em": None,
    }
    o.update(mudar)
    return o


def _etapa(o, nome, envio=ENVIO):
    return OC.linha(o, envio, AGORA).etapas[nome]


def _dados(ocorrencias, **mudar):
    d = {"versao": 1, "cliente": "Cliente A", "gerado_em": "2026-10-22T15:00:00-03:00",
         "desde": "2026-10-15T15:00:00-03:00", "envio_ao_cliente": ENVIO, "truncado": False, "ocorrencias": ocorrencias}
    d.update(mudar)
    return d


@pytest.fixture(autouse=True)
def _limpa():
    AND.limpar_cache()
    yield
    AND.limpar_cache()


@pytest.fixture
def ligada(app):
    app.config.update(NEXUS_COS_ANDAMENTO_URL="http://andamento.exemplo:3002", NEXUS_COS_ANDAMENTO_CHAVE=CHAVE,
                      NEXUS_COS_ANDAMENTO_CLIENTES="Cliente A,Cliente B")
    return app


def _servir(monkeypatch, respostas: dict):
    pedidos = []

    def pedir(f, caminho):
        pedidos.append(caminho)
        r = respostas.get(caminho)
        if isinstance(r, Exception):
            raise r
        if r is None:
            raise AND.FonteErro("o Andamento não tem este cliente, ou a rota do Nexus está desligada lá")
        return r
    monkeypatch.setattr(AND, "_pedir", pedir)
    return pedidos


# --- o prazo e o veredito ---------------------------------------------------------------------------------------------

def test_os_prazos_sao_os_da_spec_e_contam_do_inicio():
    assert OC.PRAZOS["informado"].minutos == 15 and OC.PRAZOS["campo"].minutos == 30
    assert all(p.porque.startswith("R04") for p in OC.PRAZOS.values())
    assert OC.CONTA_DE == "inicio"


def test_cliente_informado_no_prazo_e_fora_dele():
    e = _etapa(_oc(), "informado")
    assert (e.estado, e.rotulo, e.tom, e.detalhe) == ("no_prazo", "09:06", "ok", "flash · em 6 min")
    e = _etapa(_oc(cliente_informado={"em": "2026-10-22T10:02:00-03:00", "por": "fotografia"},
                   volta_informada={"em": "2026-10-22T10:30:00-03:00", "por": "flash"}), "informado")
    assert (e.estado, e.tom) == ("fora", "critico") and e.detalhe == "fotografia · em 1 h 02 (prazo 15 min)"


def test_cliente_informado_correndo_atrasado_e_nunca():
    aberta = dict(estado="EM_CAMPO", estado_rotulo="Técnico acionado", aberta=True, cliente_informado=None, normalizada=None)
    e = _etapa(_oc(inicio="2026-10-22T14:55:00-03:00", **aberta), "informado")
    assert (e.estado, e.rotulo, e.tom, e.detalhe) == ("pendente", "aguardando", "info", "faltam 10 min")
    e = _etapa(_oc(inicio="2026-10-22T14:00:00-03:00", **aberta), "informado")
    assert (e.estado, e.tom, e.detalhe) == ("atrasada", "critico", "há 1 h 00 (prazo 15 min)")
    e = _etapa(_oc(inicio="2026-10-22T14:00:00-03:00", **{**aberta, "os": None}), "informado")
    assert e.estado == "atrasada" and "ainda sem OS" in e.detalhe
    e = _etapa(_oc(cliente_informado=None, volta_informada=None), "informado")
    assert (e.estado, e.rotulo, e.detalhe) == ("nao_informado", "não avisado", "fechou sem aviso ao cliente")


def test_no_religamento_remoto_o_cliente_sabe_pelo_aviso_da_volta():
    # decisão do dono, 21/10/2026: o religamento remoto vai ao cliente só pela normalização
    e = _etapa(_oc(cliente_informado=None, volta_informada={"em": "2026-10-22T09:04:00-03:00", "por": "flash"}), "informado")
    assert (e.estado, e.rotulo, e.detalhe) == ("no_prazo", "09:04", "flash da volta · em 4 min")
    # a volta avisada DEPOIS do aviso da ocorrência não muda nada
    e = _etapa(_oc(), "informado")
    assert e.detalhe == "flash · em 6 min"


def test_o_prazo_se_compara_em_minutos_inteiros():
    e = _etapa(_oc(campo={"acionado_em": "2026-10-22T09:30:40-03:00", "acionado_por": "pessoa", "escalonado_em": None}), "campo")
    assert (e.estado, e.detalhe) == ("no_prazo", "por pessoa · em 30 min")
    e = _etapa(_oc(campo={"acionado_em": "2026-10-22T09:31:00-03:00", "acionado_por": "pessoa", "escalonado_em": None}), "campo")
    assert (e.estado, e.detalhe) == ("fora", "por pessoa · em 31 min (prazo 30 min)")


def test_cliente_informado_nao_se_mede_antes_do_envio_sem_grupo_e_no_alarme():
    e = _etapa(_oc(inicio="2026-10-20T09:00:00-03:00"), "informado")
    assert (e.estado, e.detalhe) == ("nao_medido", "antes de o Andamento mandar ao cliente")
    e = _etapa(_oc(), "informado", envio={"grupos": "nenhum", "desde": None})
    assert (e.estado, e.detalhe) == ("nao_medido", "o Andamento não manda a este cliente")
    e = _etapa(_oc(estado="DETECTADO", aberta=True, cliente_informado=None), "informado")
    assert e.estado == "nao_medido" and "não confirmado" in e.detalhe


def test_o_escalonamento_automatico_nao_e_acionamento_de_campo():
    e = _etapa(_oc(campo={"acionado_em": None, "acionado_por": None, "escalonado_em": "2026-10-22T09:15:00-03:00"}), "campo")
    assert (e.estado, e.rotulo, e.tom) == ("so_automatico", "só automático", "alerta")
    assert "09:15" in e.detalhe and "sem acionamento registrado por pessoa" in e.detalhe


def test_campo_acionado_nao_precisou_e_sem_campo():
    e = _etapa(_oc(campo={"acionado_em": "2026-10-22T09:20:00-03:00", "acionado_por": "criacao_da_os", "escalonado_em": None}), "campo")
    assert (e.estado, e.rotulo, e.detalhe) == ("no_prazo", "09:20", "OS com religamento local · em 20 min")
    e = _etapa(_oc(campo={"acionado_em": "2026-10-22T09:45:00-03:00", "acionado_por": "pessoa", "escalonado_em": None}), "campo")
    assert (e.estado, e.detalhe) == ("fora", "por pessoa · em 45 min (prazo 30 min)")
    e = _etapa(_oc(), "campo")                                                # voltou em 18 min, de longe
    assert (e.estado, e.rotulo, e.tom, e.detalhe) == ("nao_precisou", "não precisou", "neutro", "normalizada em 18 min")
    e = _etapa(_oc(normalizada={"fim": "2026-10-22T11:10:00-03:00", "declarada_em": None, "por": "pessoa"}), "campo")
    assert (e.estado, e.tom, e.detalhe) == ("sem_campo", "alerta", "normalizada em 2 h 10, sem acionamento")
    e = _etapa(_oc(aberta=True, normalizada=None, inicio="2026-10-22T14:20:00-03:00"), "campo")
    assert (e.estado, e.detalhe) == ("atrasada", "há 40 min (prazo 30 min)")


def test_detectada_normalizada_e_encerrada_dizem_o_que_houve():
    x = OC.linha(_oc(), ENVIO, AGORA)
    assert (x.etapas["detectada"].rotulo, x.etapas["detectada"].detalhe) == ("09:00", "registrada 10 min depois · OS aberta 09:12")
    n = x.etapas["normalizada"]
    assert (n.rotulo, n.tom) == ("09:18", "ok")
    assert n.detalhe == "fora 18 min · declarada 09:20 religamento remoto · cliente avisado 09:21"
    assert (x.etapas["encerrada"].estado, x.etapas["encerrada"].detalhe) == ("aguardando", "a OS ainda não foi finalizada")
    assert OC.linha(_oc(encerrada_em="2026-10-21T10:00:00-03:00"), ENVIO, AGORA).etapas["encerrada"].rotulo == "21/10 10:00"
    assert OC.linha(_oc(os=None, os_aberta_em=None), ENVIO, AGORA).etapas["detectada"].detalhe.endswith("sem OS")


def test_o_placar_conta_so_o_que_se_mede():
    p = OC.painel(AND.Leitura("Cliente A", _dados([
        _oc("a"),                                                                                    # avisada a tempo
        _oc("b", cliente_informado={"em": "2026-10-22T10:00:00-03:00", "por": "fotografia"}),      # avisada tarde
        _oc("c", inicio="2026-10-20T09:00:00-03:00"),                                              # antes do envio: fora da conta
        _oc("d", campo={"acionado_em": None, "acionado_por": None, "escalonado_em": "2026-10-22T09:15:00-03:00"}),
    ])), AGORA)
    assert p.resumo["informado"] == {"cumpriu": 2, "nao_cumpriu": 1, "pendente": 0, "automatico": 0, "medidas": 3, "pct": 67}
    assert p.resumo["campo"]["automatico"] == 1 and p.resumo["campo"]["medidas"] == 0 and p.resumo["campo"]["pct"] is None
    assert p.contagem == {"abertas": 0, "fora": 1, "pendentes": 0, "automatico": 1}
    fora = OC.painel(AND.Leitura("Cliente A", _dados([_oc("a"), _oc("b", cliente_informado=None, volta_informada=None)])), AGORA, "fora")
    assert [x.o["registro"] for x in fora.itens] == ["b"] and fora.total == 2


def test_o_link_abre_a_ocorrencia_na_ronda_cos_no_mesmo_servidor():
    assert OC.link_da_plataforma("http://andamento.exemplo:3002", "r 1") == "http://andamento.exemplo:3000/console?registro=r%201"
    assert OC.link_da_plataforma("", "r1") == "" and OC.link_da_plataforma("http://andamento.exemplo:3002", "") == ""


def test_os_dias():
    assert OC.dias_pedidos("1") == 1 and OC.dias_pedidos("30") == 30
    for v in (None, "", "3", "abc", "31"):
        assert OC.dias_pedidos(v) == 7


# --- a leitura --------------------------------------------------------------------------------------------------------

def test_a_leitura_pede_a_rota_do_ciclo_com_os_dias_e_guarda_a_copia(ligada, monkeypatch):
    pedidos = _servir(monkeypatch, {"/api/nexus/Cliente%20A/ocorrencias?dias=30": _dados([_oc()])})
    lt = AND.ler_ocorrencias(ligada.config, "Cliente A", 30)
    assert lt.dados["ocorrencias"][0]["registro"] == "r1" and not lt.erro
    AND.ler_ocorrencias(ligada.config, "Cliente A", 30)
    assert pedidos == ["/api/nexus/Cliente%20A/ocorrencias?dias=30"]           # 60 s de cópia
    AND.ler_ocorrencias(ligada.config, "Cliente A", 99)                          # fora das opções: o padrão
    assert pedidos[-1].endswith("?dias=7")


def test_outra_versao_das_ocorrencias_e_recusada(ligada, monkeypatch):
    _servir(monkeypatch, {"/api/nexus/Cliente%20A/ocorrencias?dias=7": _dados([], versao=2)})
    lt = AND.ler_ocorrencias(ligada.config, "Cliente A", 7)
    assert lt.dados is None and "versão 2 das ocorrências" in lt.erro


# --- a tela -----------------------------------------------------------------------------------------------------------

def test_a_tela_sem_a_fonte_diz_que_ela_nao_esta_ligada(logado):
    html = logado.get("/t/cos/ocorrencias").get_data(as_text=True)
    assert "ainda não está ligada neste servidor" in html and "NEXUS_COS_ANDAMENTO_CHAVE" in html


def test_a_tela_mostra_o_ciclo_o_placar_e_o_link(ligada, logado, monkeypatch):
    _servir(monkeypatch, {"/api/nexus/Cliente%20A/ocorrencias?dias=7": _dados([
        _oc("r1"),
        _oc("r2", usina="Usina Exemplo Dois", estado="EM_CAMPO", estado_rotulo="Técnico acionado", aberta=True, normalizada=None,
            volta_informada=None, inicio="2026-10-22T13:00:00-03:00", cliente_informado=None,
            campo={"acionado_em": None, "acionado_por": None, "escalonado_em": "2026-10-22T13:15:00-03:00"}),
    ])})
    monkeypatch.setattr(AND, "agora", lambda: AGORA)
    r = logado.get("/t/cos/ocorrencias")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "Usina Exemplo Um" in html and "Usina Exemplo Dois" in html and "OS 90001" in html
    assert "só automático" in html and "não avisado" in html and "flash · em 6 min" in html
    assert "http://andamento.exemplo:3000/console?registro=r1" in html
    assert "50%" in html                                                         # 1 de 2 avisadas a tempo
    assert 'aria-current="page">Cliente A<' in html and CHAVE not in html
    fora = logado.get("/t/cos/ocorrencias?situacao=fora").get_data(as_text=True)
    assert "Usina Exemplo Dois" in fora and "Usina Exemplo Um" not in fora


def test_a_tela_com_o_andamento_fora_do_ar(ligada, logado, monkeypatch):
    _servir(monkeypatch, {})
    html = logado.get("/t/cos/ocorrencias").get_data(as_text=True)
    assert "O Andamento não tem este cliente" in html and CHAVE not in html

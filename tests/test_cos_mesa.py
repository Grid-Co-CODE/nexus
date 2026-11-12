"""Torre COS: a Mesa do operador (05/11/2026) — o que está aberto na minha mesa e o que falta avisar ao cliente?

A carteira é a da Ronda COS (`GET /api/nexus/carteiras`, com o HMAC do e-mail pela chave do Nexus); o que está aberto, a
fotografia do Andamento; o que falta avisar e o campo a acionar, o ciclo das ocorrências com os vereditos da tela
Ocorrências (nexus/cos/mesa.py). Nada aqui vai à rede, e os dados e as pessoas são fictícios."""
from datetime import datetime

import pytest

from nexus.cos import andamento as AND
from nexus.cos import mesa as ME

CHAVE = "chave-de-teste-do-andamento"
AGORA = datetime(2026, 11, 5, 10, 0, tzinfo=AND._BRT)
ENVIO = {"grupos": "regioes", "desde": "2026-10-01T00:00:00-03:00"}
ANA = {"email": "ana.ficticia@exemplo.com", "nome": "Ana Ficticia"}
BIA = {"email": "bia.ficticia@exemplo.com", "nome": "Bia Ficticia"}


def _oc(registro, inicio, aberta=True, informado=None, campo=None, usina="Usina Exemplo Um", **mudar):
    o = {"registro": registro, "os": "90001", "usina": usina, "usina_codigo": "EX-UM100", "regiao": "Região A",
         "equipamentos": [], "tipo_falha": "Desligamento de usina", "severidade": "CRITICO", "severidade_rotulo": "Crítico",
         "estado": "TRATATIVA_REMOTA" if aberta else "NORMALIZADO", "estado_rotulo": "Tratativa remota", "aberta": aberta,
         "inicio": inicio, "registrada_em": inicio, "registrada_por": "pessoa", "os_aberta_em": None,
         "cliente_informado": {"em": informado, "por": "flash"} if informado else None,
         "campo": {"acionado_em": campo, "acionado_por": "pessoa" if campo else None, "escalonado_em": None},
         "normalizada": None if aberta else {"fim": inicio, "declarada_em": inicio, "por": "pessoa"},
         "volta_informada": None, "encerrada_em": None}
    o.update(mudar)
    return o


def _ciclo(cliente, ocs):
    return {"versao": 1, "cliente": cliente, "gerado_em": "2026-11-05T10:00:00-03:00",
            "desde": "2026-10-29T10:00:00-03:00", "envio_ao_cliente": ENVIO, "truncado": False, "ocorrencias": ocs}


def _foto(*classes):
    return {"versao": 1, "placar": {}, "problemas": [], "eventos": [], "fotografias": [],
            "usinas": [{"ocorrencias": [{"severidade_classe": c} for c in classes]}]}


def _carteiras(*pares):
    return {"versao": 1, "gerado_em": "2026-11-05T10:00:00-03:00",
            "carteiras": [{"pessoa": AND.chave_da_pessoa(e, CHAVE), "clientes": list(c), "fora": list(f)}
                          for e, c, f in pares]}


CICLO_A = _ciclo("Cliente A", [
    _oc("a1", "2026-11-05T09:30:00-03:00"),                                              # 30 min sem aviso: atrasada
    _oc("a2", "2026-11-05T09:52:00-03:00"),                                              # 8 min: correndo
    _oc("a3", "2026-11-05T09:00:00-03:00", informado="2026-11-05T09:05:00-03:00",
        campo="2026-11-05T09:20:00-03:00"),                                              # avisado e acionado: nada a fazer
    _oc("a4", "2026-11-05T08:00:00-03:00", aberta=False),                                # fechada: fora da mesa
])
CICLO_B = _ciclo("Cliente B", [_oc("b1", "2026-11-05T09:40:00-03:00", usina="Usina Exemplo Dois",
                                   informado="2026-11-05T09:44:00-03:00")])
RESPOSTAS = {
    "/api/nexus/carteiras": _carteiras((ANA["email"], ["Cliente A"], ["CLIENTE FORA"])),
    "/api/nexus/Cliente%20A": _foto("crit", "medio", "alto"),
    "/api/nexus/Cliente%20B": _foto("medio"),
    f"/api/nexus/Cliente%20A/ocorrencias?dias={ME.DIAS_DA_MESA}": CICLO_A,
    f"/api/nexus/Cliente%20B/ocorrencias?dias={ME.DIAS_DA_MESA}": CICLO_B,
}


# --- a carteira ------------------------------------------------------------------------------------------------------

def test_o_hmac_do_email_e_o_mesmo_do_andamento():
    """O vetor é o do teste do Andamento (`nexus-carteiras.test.ts`): a conta dos dois lados tem de dar o mesmo."""
    assert AND.chave_da_pessoa("ana.ficticia@exemplo.com", "chave-de-teste-do-nexus") == \
        "bc9e677b524fa42e47153ca8b86002e396e667b6f7a80f23a4b965f503e1aca5"
    assert AND.chave_da_pessoa("  ANA.Ficticia@Exemplo.com ", "chave-de-teste-do-nexus") == \
        AND.chave_da_pessoa("ana.ficticia@exemplo.com", "chave-de-teste-do-nexus")


@pytest.mark.parametrize("email,ver,clientes,minha,aviso", [
    (ANA["email"], "", ["Cliente A"], True, ""),
    (ANA["email"], "todas", ["Cliente A", "Cliente B"], False, ""),
    (BIA["email"], "", ["Cliente A", "Cliente B"], False, "não tem carteira"),
    ("", "", ["Cliente A", "Cliente B"], False, "sem e-mail"),
])
def test_a_mesa_de_quem_entrou(email, ver, clientes, minha, aviso):
    leitura = AND.Leitura("", RESPOSTAS["/api/nexus/carteiras"])
    m = ME.escolher(email, CHAVE, leitura, ["Cliente A", "Cliente B"], ver)
    assert (m.clientes, m.minha) == (clientes, minha)
    assert aviso in m.aviso
    if minha:
        assert m.fora == ["CLIENTE FORA"]


def test_sem_leitura_das_carteiras_mostra_todas_e_diz_por_que():
    m = ME.escolher(ANA["email"], CHAVE, AND.Leitura("", None, erro="o Andamento não respondeu"), ["Cliente A"])
    assert m.clientes == ["Cliente A"] and not m.minha and "o Andamento não respondeu" in m.aviso


def test_as_mesas_sao_os_conjuntos_de_clientes_sem_quem():
    leitura = AND.Leitura("", _carteiras(("a@x.y", ["Cliente B", "Cliente A"], []), ("b@x.y", ["Cliente A", "Cliente B"], []),
                                         ("c@x.y", ["Cliente A"], []), ("d@x.y", [], ["OUTRO"])))
    assert ME.mesas(leitura, ["Cliente A", "Cliente B"]) == [
        {"clientes": ["Cliente A"], "operadores": 1}, {"clientes": ["Cliente A", "Cliente B"], "operadores": 2}]


# --- o painel --------------------------------------------------------------------------------------------------------

def test_falta_avisar_e_campo_a_acionar_so_das_abertas_a_atrasada_primeiro():
    p = ME.painel([AND.Leitura("Cliente A", _foto("crit", "medio", "alto"))],
                  [AND.Leitura("Cliente A", CICLO_A)], AGORA)
    assert [(i.linha.o["registro"], i.etapa.estado) for i in p.falta_avisar] == [("a1", "atrasada"), ("a2", "pendente")]
    assert [(i.linha.o["registro"], i.etapa.estado) for i in p.campo] == [("a1", "pendente"), ("a2", "pendente")]
    assert p.resumo == {"abertas": 3, "criticas": 2, "falta_avisar": 2, "avisar_atrasadas": 1, "campo": 2,
                        "campo_atrasadas": 0}


def test_um_cliente_sem_leitura_nao_vira_zero():
    p = ME.painel([AND.Leitura("Cliente A", None, erro="o Andamento não respondeu")],
                  [AND.Leitura("Cliente A", None, erro="o Andamento não respondeu")], AGORA)
    assert p.resumo["abertas"] is None and p.erros == [("Cliente A", "o Andamento não respondeu", False)]


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


def _servir(monkeypatch, respostas):
    pedidos = []

    def pedir(f, caminho, timeout=AND.TIMEOUT_S):
        pedidos.append(caminho)
        r = respostas.get(caminho)
        if isinstance(r, Exception):
            raise r
        if r is None:
            raise AND.FonteErro("o Andamento não tem este cliente, ou a rota do Nexus está desligada lá", 404)
        return r
    monkeypatch.setattr(AND, "_pedir", pedir)
    return pedidos


def _como(cli, usuario):
    with cli.session_transaction() as s:
        s["logado"], s["admin"], s["usuario"] = True, False, usuario
    return cli


def test_a_tela_abre_na_carteira_de_quem_entrou(ligada, cliente, monkeypatch):
    pedidos = _servir(monkeypatch, RESPOSTAS)
    html = _como(cliente, ANA).get("/t/cos/mesa").get_data(as_text=True)
    assert "Sua carteira: <b>Cliente A</b>" in html and "CLIENTE FORA" in html
    assert not any("Cliente%20B" in x for x in pedidos)                     # só os clientes da mesa
    assert html.index('cn-pill cn-critico">Atrasada<') < html.index('cn-pill cn-info">Correndo<')
    assert "abrir na Ronda COS" in html
    assert "/t/cos/ronda?cliente=Cliente%20A" in html
    # o e-mail de quem entrou está no menu da conta (o do Nexus); o HMAC da carteira não sai na tela
    assert AND.chave_da_pessoa(ANA["email"], CHAVE) not in html
    html = _como(cliente, ANA).get("/t/cos/mesa?mesa=todas").get_data(as_text=True)
    # b1 (Cliente B) já foi avisada, mas o campo ainda corre o prazo: entra só no "Campo a acionar"
    assert html.count("Usina Exemplo Dois") == 1
    assert "<b>Cliente A · Cliente B</b>" in html


def test_sem_carteira_mostra_todas_e_o_andamento_sem_a_rota(ligada, cliente, monkeypatch):
    respostas = dict(RESPOSTAS)
    respostas.pop("/api/nexus/carteiras")
    _servir(monkeypatch, respostas)
    html = _como(cliente, ANA).get("/t/cos/mesa").get_data(as_text=True)
    assert "ainda não tem a rota das carteiras" in html and "<b>Cliente A · Cliente B</b>" in html


def test_a_fonte_desligada(app, logado):
    assert "não está ligada neste servidor" in logado.get("/t/cos/mesa").get_data(as_text=True)


def test_a_mesa_vem_logo_depois_do_acompanhamento():
    """O cartão do COS no Início leva à 1ª tela pronta, e o Acompanhamento continua sendo ela. Desde 12/11/2026 (a
    reorganização do COS pelo dono) a Mesa e o Desempenho vão para os indicadores, juntas, depois da Ocorrências."""
    from nexus.torres.cos import TORRE
    ids = [t.id for t in TORRE.telas]
    assert ids[0] == "acompanhamento"
    assert ids.index("mesa") == ids.index("normalizacoes") + 1 and ids.index("desempenho") == ids.index("mesa") + 1

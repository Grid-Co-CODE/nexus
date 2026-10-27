"""Torre COS: a tela Religamentos (26/10/2026) — onde o religamento remoto resolve e onde se repete na mesma cabine?

As ocorrências vêm do Andamento da Ronda COS (`GET /api/nexus/<cliente>/ocorrencias`, com a tag dos equipamentos e o
religamento de cada uma); o desfecho e a repetição são do Nexus (nexus/cos/religamentos.py). Nada aqui vai à rede, e os
dados são fictícios."""
import pytest

from nexus.cos import andamento as AND
from nexus.cos import religamentos as RE

CHAVE = "chave-de-teste-do-andamento"


def _oc(registro, os="90001", usina="Usina Exemplo Um", codigo="EX-UM100", ativos=("EX-UM100-CABN1",),
        nomes=("Cabine 1",), remoto=False, local=False, aberta=False, campo_em=None, escalonado_em=None,
        inicio="2026-10-20T09:00:00-03:00", tipo="Desligamento de cabine", **mudar):
    o = {"registro": registro, "os": os, "usina": usina, "usina_codigo": codigo, "equipamentos": list(nomes),
         "ativos": list(ativos), "tipo_falha": tipo, "tipo_falha_codigo": "DESLIGAMENTO_CABINE", "protecoes": ["27"],
         "religamento": {"remoto": remoto, "local": local}, "aberta": aberta, "inicio": inicio,
         "campo": {"acionado_em": campo_em, "acionado_por": "pessoa" if campo_em else None, "escalonado_em": escalonado_em},
         "normalizada": None if aberta else {"fim": "2026-10-20T09:30:00-03:00", "declarada_em": None, "por": "pessoa"}}
    o.update(mudar)
    return o


def _dados(ocorrencias, **mudar):
    d = {"versao": 1, "cliente": "Cliente A", "gerado_em": "2026-10-26T15:00:00-03:00",
         "desde": "2026-09-26T15:00:00-03:00", "envio_ao_cliente": {"grupos": "cliente", "desde": None},
         "truncado": False, "ocorrencias": ocorrencias}
    d.update(mudar)
    return d


def _painel(ocs, ver="repetem"):
    return RE.painel(AND.Leitura("Cliente A", _dados(ocs)), ver)


# --- o desfecho ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("o,esperado", [
    (_oc("a", remoto=True), "resolveu"),                                          # fechou sem ir a campo
    (_oc("b", remoto=True, local=True), "foi_a_campo"),                           # o remoto não segurou: OS local
    (_oc("c", remoto=True, campo_em="2026-10-20T10:00:00-03:00"), "foi_a_campo"),  # campo acionado por pessoa
    (_oc("d", remoto=True, aberta=True), "em_aberto"),
    (_oc("e", local=True), "so_local"),
    (_oc("f"), None),                                                              # sem religamento: fora da tela
])
def test_o_desfecho_de_cada_ocorrencia(o, esperado):
    assert RE.desfecho(o, RE.religamento(o)[0]) == esperado


def test_o_escalonamento_automatico_nao_e_ida_a_campo():
    """A passagem automática a "Técnico acionado" (a tratativa remota que passou do tempo) não é ninguém indo a campo,
    como na tela Ocorrências: o remoto que fechou depois dela resolveu."""
    o = _oc("a", remoto=True, escalonado_em="2026-10-20T09:15:00-03:00")
    assert RE.desfecho(o, RE.religamento(o)[0]) == "resolveu"


def test_andamento_de_antes_dos_campos_novos_conta_pelo_que_da():
    """Sem `religamento` e sem `ativos` (o Andamento de antes de 26/10/2026): o remoto que normalizou pela plataforma e a
    OS com religamento local, e a cabine pelo nome; a tela diz que está incompleta."""
    velho = _oc("a")
    for k in ("religamento", "ativos"):
        velho.pop(k)
    velho["normalizada"]["por"] = "religamento_remoto"
    assert RE.religamento(velho) == ({"remoto": True, "local": False}, False)
    assert RE.equipamentos(velho) == ([("nome:Cabine 1", "Cabine 1")], False)
    p = _painel([velho])
    assert not p.completo and not p.pela_tag and p.resumo["resolveu"] == 1


# --- a repetição -----------------------------------------------------------------------------------------------------

def test_agrupa_pela_tag_e_conta_a_repeticao():
    ocs = [_oc("a1", os="1", remoto=True, inicio="2026-10-01T09:00:00-03:00"),
           _oc("a2", os="2", remoto=True, local=True, inicio="2026-10-10T09:00:00-03:00"),
           _oc("a3", os="3", remoto=True, inicio="2026-10-20T09:00:00-03:00"),
           # a mesma cabine de NOME em outra usina não se junta (a tag é outra)
           _oc("b1", os="4", usina="Usina Exemplo Dois", codigo="EX-DOIS100", ativos=("EX-DOIS100-CABN1",), remoto=True),
           _oc("b2", os="5", usina="Usina Exemplo Dois", codigo="EX-DOIS100", ativos=("EX-DOIS100-CABN2",),
               nomes=("Cabine 2",), local=True),
           _oc("c1", os="6", usina="Usina Exemplo Dois", codigo="EX-DOIS100", ativos=(), nomes=(), remoto=True),
           _oc("c2", os="7", usina="Usina Exemplo Dois", codigo="EX-DOIS100", ativos=(), nomes=(), remoto=True),
           _oc("x", os="8")]                                                       # sem religamento
    p = _painel(ocs)
    assert [(e.usina, e.rotulo, e.total) for e in p.itens] == [
        ("Usina Exemplo Um", "Cabine 1", 3), ("Usina Exemplo Dois", RE.USINA_INTEIRA, 2)]
    um = p.itens[0]
    assert um.reincidente and um.repete and um.desfechos == {"resolveu": 2, "foi_a_campo": 1}
    assert um.os == ["3", "2", "1"] and um.ultima.day == 20 and um.tag == "EX-UM100-CABN1"
    assert not p.itens[1].reincidente and p.itens[1].repete
    assert p.contagem == {"repetem": 2, "todos": 4}
    assert p.resumo["remotos"] == 6 and p.resumo["resolveu"] == 5 and p.resumo["foi_a_campo"] == 1
    assert p.resumo["so_local"] == 1 and p.resumo["pct_resolveu"] == 83 and p.resumo["reincidentes"] == 1
    assert len(_painel(ocs, "todos").itens) == 4


def test_a_ocorrencia_de_varios_equipamentos_conta_em_cada_um():
    ocs = [_oc("a", remoto=True, ativos=("EX-UM100-INVR1", "EX-UM100-INVR2"), nomes=("Inversor 1", "Inversor 2")),
           _oc("b", remoto=True, ativos=("EX-UM100-INVR2",), nomes=("Inversor 2",))]
    p = _painel(ocs, "todos")
    assert {(e.rotulo, e.total) for e in p.itens} == {("Inversor 1", 1), ("Inversor 2", 2)}
    assert p.resumo["remotos"] == 2                                                # a ocorrência conta uma vez no resumo


def test_a_regua_e_a_do_rdo():
    assert (RE.REPETE_A_PARTIR, RE.REINCIDENTE_A_PARTIR) == (2, 3) and RE.DIAS_PADRAO == 30
    assert RE.dias_pedidos("7") == 7 and RE.dias_pedidos("1") == RE.dias_pedidos("x") == 30


# --- a tela ----------------------------------------------------------------------------------------------------------

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
        if r is None:
            raise AND.FonteErro("o Andamento não tem este cliente, ou a rota do Nexus está desligada lá")
        return r
    monkeypatch.setattr(AND, "_pedir", pedir)
    return pedidos


def test_tela_mostra_onde_repete(ligada, logado, monkeypatch):
    ocs = [_oc("a1", os="11", remoto=True, inicio="2026-10-01T09:00:00-03:00"),
           _oc("a2", os="12", remoto=True, local=True, inicio="2026-10-10T09:00:00-03:00"),
           _oc("a3", os="13", remoto=True, inicio="2026-10-20T09:00:00-03:00")]
    pedidos = _servir(monkeypatch, {"/api/nexus/Cliente%20A/ocorrencias?dias=30": _dados(ocs)})
    html = logado.get("/t/cos/religamentos").get_data(as_text=True)
    assert pedidos == ["/api/nexus/Cliente%20A/ocorrencias?dias=30"]
    assert "Usina Exemplo Um" in html and "Cabine 1 · EX-UM100-CABN1" in html and "13 · 12 · 11" in html
    assert 'cn-pill cn-critico">3<' in html and "Repetem<b>1</b>" in html and "67%" in html
    assert "ainda não manda tudo" not in html


def test_tela_avisa_do_andamento_antigo_e_da_fonte_desligada(ligada, app, logado, monkeypatch):
    velho = _oc("a", remoto=False)
    for k in ("religamento", "ativos"):
        velho.pop(k)
    _servir(monkeypatch, {"/api/nexus/Cliente%20A/ocorrencias?dias=7": _dados([velho])})
    html = logado.get("/t/cos/religamentos?dias=7").get_data(as_text=True)
    assert "ainda não manda tudo" in html and "agrupada pelo nome" in html and "Nenhum religamento no período" in html
    app.config.update(NEXUS_COS_ANDAMENTO_URL="", NEXUS_COS_ANDAMENTO_CHAVE="")
    assert "não está ligada neste servidor" in logado.get("/t/cos/religamentos").get_data(as_text=True)

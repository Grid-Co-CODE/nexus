"""Torre COS: a ficha da usina (09/11/2026) — tudo o que as telas do COS sabem de UMA usina, numa página.

A ficha não tem conta própria: cada bloco passa pela conta da tela dona (ocorrencias, religamentos, os_abertas,
normalizacoes) e só recorta pela usina (nexus/cos/ficha.py). Os dados são os fictícios das telas (test_cos_*), e nada
vai à rede."""
import urllib.parse

import pytest
from test_cos_andamento import AGORA, CHAVE
from test_cos_andamento import _dados as _foto
from test_cos_normalizacoes import _n, _resp
from test_cos_ocorrencias import _dados as _ciclo
from test_cos_ocorrencias import _oc
from test_cos_os_abertas import _dados as _os_dados
from test_cos_os_abertas import _os

from nexus.auth import setor_telas as ST
from nexus.cos import andamento as AND
from nexus.cos import ficha as FI
from nexus.cos import normalizacoes as NO

# a Usina Exemplo Vermelha (EX-VER100) da fotografia fictícia: duas ocorrências abertas (r1 e r4)
VER = "EX-VER100"


def _rel(registro, inicio, **mudar):
    """Um religamento remoto que resolveu (normalizou sem ir a campo) no SKID 1 da Vermelha."""
    return _oc(registro, usina="Usina Exemplo Vermelha", usina_codigo=VER, inicio=inicio, os="9100" + registro[-1],
               equipamentos=["SKID 1"], ativos=[VER + "-SKID1"], tipo_falha_codigo="DESLIGAMENTO",
               religamento={"remoto": True, "local": False}, **mudar)


def _ocorrencias():
    return [
        # a r1 da fotografia, aberta, ainda sem o aviso ao cliente: no ciclo, ela traz o prazo
        _oc("r1", usina="Usina Exemplo Vermelha", usina_codigo=VER, inicio="2026-10-22T13:02:00-03:00", aberta=True,
            estado="ABERTO", estado_rotulo="Aberta", cliente_informado=None, normalizada=None, volta_informada=None),
        _rel("r7", "2026-10-20T10:00:00-03:00"),
        _rel("r8", "2026-10-21T10:00:00-03:00"),
        # de outra usina: não entra na ficha da Vermelha
        _oc("r9", usina="Usina Exemplo Amarela", usina_codigo="EX-AMA200", inicio="2026-10-21T09:00:00-03:00"),
    ]


def _leitura(cliente, dados):
    return AND.Leitura(cliente, dados, lido_em=1.0)


# --- a regra (nexus/cos/ficha.py) -------------------------------------------------------------------------------------

def test_o_codigo_casa_inteiro_ou_pelo_sufixo_so_sem_o_prefixo():
    assert FI.mesma("EX-VER100", "ex-ver100 ")
    # o `cod` dos eventos ("VER100") é a mesma usina do `codigo` ("EX-VER100")
    assert FI.mesma("VER100", "EX-VER100") and FI.mesma("EX-VER100", "VER100")
    # dois prefixos diferentes são dois clientes: usinas diferentes, mesmo com o sufixo igual
    assert not FI.mesma("EX-VER100", "XY-VER100")
    assert not FI.mesma("", "EX-VER100") and not FI.mesma(None, None)


def test_achar_prefere_o_codigo_inteiro_ao_sufixo_de_outro_cliente():
    a = _leitura("Cliente A", _foto())
    b = _leitura("Cliente B", _foto("Cliente B", usinas=[{"id": 9, "codigo": "XY-VER100", "cod": "VER100",
                                                           "nome": "Outra Vermelha", "ocorrencias": []}]))
    # o código inteiro de B acha a de B, mesmo com A antes na lista e o mesmo sufixo
    lt, u = FI.achar([a, b], "XY-VER100")
    assert lt.cliente == "Cliente B" and u["nome"] == "Outra Vermelha"
    lt, u = FI.achar([a, b], "EX-VER100")
    assert lt.cliente == "Cliente A" and u["nome"] == "Usina Exemplo Vermelha"
    assert FI.achar([a, b], "NAO000") == (None, None)


def test_a_lista_poe_as_vermelhas_primeiro_e_a_busca_casa_cada_palavra():
    fotos = [_leitura("Cliente A", _foto())]
    assert [x["codigo"] for x in FI.lista(fotos)] == ["EX-VER100", "EX-AMA200", "EX-OK300"]
    assert [x["codigo"] for x in FI.lista(fotos, "exemplo amarela")] == ["EX-AMA200"]
    assert [x["codigo"] for x in FI.lista(fotos, "ok300")] == ["EX-OK300"]


def test_cada_bloco_e_a_conta_da_tela_dona_recortada_pela_usina():
    foto = _leitura("Cliente A", _foto())
    ciclo = _leitura("Cliente A", _ciclo(_ocorrencias(), cliente="Cliente A"))
    os_lt = _leitura("", _os_dados([_os(201, usina="Usina Exemplo Vermelha", codigo=VER, em_alerta=True),
                                    _os(202, usina="Usina Exemplo Amarela", codigo="EX-AMA200")]))
    norm_lt = _leitura("", {"itens": [_n("n1", usina="Usina Exemplo Vermelha", usina_codigo=VER,
                                         volta="2026-10-20T08:00:00-03:00", inicio="2026-10-20T07:00:00-03:00"),
                                      _n("n2", usina="Usina Exemplo Amarela", usina_codigo="EX-AMA200",
                                         volta="2026-10-20T08:00:00-03:00", inicio="2026-10-20T07:00:00-03:00")]})
    _lt, u = FI.achar([foto], VER)
    f = FI.painel(foto, u, ciclo, os_lt, norm_lt, AGORA, "http://andamento.exemplo:3002")

    # aberto agora: as duas da fotografia; a r1 está no ciclo e traz o prazo, a r4 (ainda sem ciclo) não
    assert [o["registro"] for o in f.abertas] == ["r1", "r4"]
    assert f.abertas[0]["linha"].etapas["informado"].estado != "" and f.abertas[1]["linha"] is None
    # o ciclo é só da Vermelha, o mais novo primeiro
    assert [x.o["registro"] for x in f.ciclo] == ["r1", "r8", "r7"]
    # os religamentos: o SKID 1 da Vermelha com 2, que já "repete" (a régua da tela Religamentos)
    assert [(e.rotulo, e.total, e.repete) for e in f.religamentos] == [("SKID 1", 2, True)]
    # os eventos pelo `cod` curto, só os da Vermelha
    assert [e["os"] for e in f.eventos] == ["90001"]
    assert [o["folio"] for o in f.os_abertas] == [201] and f.resumo["os_em_alerta"] == 1
    assert [n["registro"] for n in f.normalizacoes] == ["n1"]
    assert f.resumo["abertas"] == 2 and f.resumo["religamentos"] == 2 and f.resumo["repete"]


# --- a tela ---------------------------------------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _limpa():
    AND.limpar_cache()
    NO.limpar()
    yield
    AND.limpar_cache()
    NO.limpar()


@pytest.fixture
def ficha(app, logado, monkeypatch):
    app.config.update(NEXUS_COS_ANDAMENTO_URL="http://andamento.exemplo:3002", NEXUS_COS_ANDAMENTO_CHAVE=CHAVE,
                      NEXUS_COS_ANDAMENTO_CLIENTES="Cliente A")
    respostas = {
        "/api/nexus/Cliente%20A": _foto(),
        "/api/nexus/Cliente%20A/ocorrencias": _ciclo(_ocorrencias(), cliente="Cliente A"),
        "/api/nexus/os-abertas": _os_dados([_os(201, usina="Usina Exemplo Vermelha", codigo=VER, em_alerta=True)]),
        "/api/normalizacoes": _resp([_n("n1", usina="Usina Exemplo Vermelha", usina_codigo=VER,
                                        volta="2026-10-20T08:00:00-03:00", inicio="2026-10-20T07:00:00-03:00")]),
    }

    def pedir(f, caminho, timeout=AND.TIMEOUT_S):
        r = respostas.get(urllib.parse.urlsplit(caminho).path)
        if r is None:
            raise AND.FonteErro("o Andamento não tem este cliente, ou a rota do Nexus está desligada lá", 404)
        return r
    monkeypatch.setattr(AND, "_pedir", pedir)
    monkeypatch.setattr(AND, "agora", lambda: AGORA)
    return logado


def _so(monkeypatch, *telas):
    """A pessoa só com estas telas do COS marcadas no setor (Base → Acessos)."""
    monkeypatch.setattr(ST, "acesso", lambda: {"tudo": False, "telas": {f"cos/{t}" for t in telas}, "setor": None,
                                               "erro": ""})


def test_a_ficha_junta_os_blocos_da_usina(ficha):
    r = ficha.get("/t/cos/usina/" + VER)
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "<h1 class=\"cn-titulo\">Usina Exemplo Vermelha</h1>" in html and "Cliente A" in html
    for bloco in ("Aberto agora", "Quem acionar e a distribuidora", "Ocorrências dos últimos 30 dias",
                  "Religamentos em 30 dias", "OS em aberto no Fracttal", "Normalizações do mês", "O que aconteceu em 7 dias"):
        assert bloco in html, bloco
    assert "Usina desligada, trip 27" in html and 'data-folio="201"' in html and "Em alerta" in html
    # sem o cadastro (o teste não monta o banco), o bloco de quem acionar diz, e a ficha segue
    assert "Não consegui ler o cadastro do Nexus" in html


def test_sem_a_usina_a_lista_com_a_busca(ficha):
    r = ficha.get("/t/cos/usina/NAO000")
    html = r.get_data(as_text=True)
    assert r.status_code == 404 and "A usina NAO000 não está no Andamento" in html
    assert "Usina Exemplo Amarela" in html
    r = ficha.get("/t/cos/usina?q=amarela")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Usina Exemplo Amarela" in html and "Usina Exemplo Verde" not in html


def test_o_nome_da_usina_leva_a_ficha_em_cada_tela(ficha):
    assert '/t/cos/usina/EX-VER100"' in ficha.get("/t/cos/ronda").get_data(as_text=True)
    # o evento só traz o `cod`: o link sai com o código inteiro, achado na fotografia do mesmo cliente
    eventos = ficha.get("/t/cos/eventos?janela=7d").get_data(as_text=True)
    assert '/t/cos/usina/EX-AMA200"' in eventos and '/t/cos/usina/AMA200"' not in eventos
    assert '/t/cos/usina/EX-VER100"' in ficha.get("/t/cos/ocorrencias?dias=30").get_data(as_text=True)
    assert '/t/cos/usina/EX-VER100"' in ficha.get("/t/cos/religamentos?ver=todos").get_data(as_text=True)
    assert '/t/cos/usina/EX-VER100"' in ficha.get("/t/cos/os-abertas?situacao=todas").get_data(as_text=True)
    assert '/t/cos/usina/EX-VER100"' in ficha.get("/t/cos/normalizacoes").get_data(as_text=True)


def test_cada_bloco_segue_a_marca_da_tela_dona(ficha, monkeypatch):
    # só o Desempenho: a ficha abre (é do COS), mas sem os blocos das telas que a pessoa não abre — e sem os telefones
    _so(monkeypatch, "desempenho")
    html = ficha.get("/t/cos/usina/" + VER).get_data(as_text=True)
    assert "Usina Exemplo Vermelha" in html
    for bloco in ("Aberto agora", "Quem acionar e a distribuidora", "Ocorrências dos últimos", "OS em aberto no Fracttal",
                  "Normalizações do mês", "O que aconteceu em 7 dias"):
        assert bloco not in html, bloco
    _so(monkeypatch, "ronda", "acionamentos")
    html = ficha.get("/t/cos/usina/" + VER).get_data(as_text=True)
    assert "Aberto agora" in html and "Quem acionar e a distribuidora" in html
    assert "Ocorrências dos últimos" not in html

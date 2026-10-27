"""Torre COS: a Passagem de turno (26/10/2026), spec R12 — "a passagem é registrada no sistema; sem registro, ela não
aconteceu". O livro nexus_cos_turno no banco falso (tests/pg_falso.py); nada vai à rede, e as pessoas são fictícias."""
import json
from datetime import datetime

import pytest
from pg_falso import ApiPGFalsa

from nexus.cadastro.cifra import gerar_chave
from nexus.cos import andamento as AND
from nexus.cos import turno as TU

BRT = TU._BRT
ANA = {"email": "ana.lima@gridco.com.br", "nome": "Ana Lima"}
BETO = {"email": "beto.souza@gridco.com.br", "nome": "Beto Souza"}
CAIO = {"email": "caio.rocha@gridco.com.br", "nome": "Caio Rocha"}


def _t(dia, h, m=0):
    return datetime(2026, 10, dia, h, m, tzinfo=BRT)


@pytest.fixture
def banco(app):
    api = ApiPGFalsa()
    app.config.update(GRIDCO_DB_API="http://pg.falso", NEXUS_CHAVE_CADASTRO=gerar_chave(),
                      NEXUS_PESSOA_HMAC="hmac-teste", GRIDCO_SQL_TOKEN="tk")
    app.extensions["nexus_dados_sessao"] = api
    with app.app_context():
        yield api
    app.extensions.pop("nexus_dados_sessao", None)


@pytest.fixture(autouse=True)
def _limpa():
    AND.limpar_cache()
    yield
    AND.limpar_cache()


def _como(cli, usuario, admin=False):
    with cli.session_transaction() as s:
        s["logado"], s["admin"], s["usuario"] = True, admin, usuario
    return cli


def _linha(troca, evento, quando, hmac="p1", abertas=None):
    """Uma linha do livro como o banco devolve (sem cifra: o nome sai vazio)."""
    return {"id": f"{evento}-{troca:%d%H}-{hmac}", "registrado_em": quando.astimezone(TU.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "troca_em": troca.isoformat(), "evento": evento, "pessoa_hmac": hmac, "abertas_qtd": abertas}


# --- o relógio dos turnos ---------------------------------------------------------------------------------------------

def test_os_turnos_sao_os_da_ronda_cos():
    assert [(t.id, t.inicio_h) for t in TU.TURNOS] == [("dia", 6), ("noite", 18)]
    assert TU.turno_que_sai(_t(26, 18)).id == "dia" and TU.turno_que_comeca(_t(26, 18)).id == "noite"
    assert TU.turno_que_sai(_t(27, 6)).id == "noite" and TU.rotulo_da_troca(_t(27, 6)) == "Noite → Dia"


@pytest.mark.parametrize("escrita,troca", [
    (_t(26, 17, 30), _t(26, 18)),      # antes da troca: a do fim do turno
    (_t(26, 18, 10), _t(26, 18)),      # 10 min depois: ainda é a do dia (quem saiu às 18:00 escreveu atrasado)
    (_t(26, 18, 59), _t(26, 18)),
    (_t(26, 19, 0), _t(27, 6)),        # passou a tolerância: é a do fim da noite
    (_t(27, 0, 30), _t(27, 6)),        # depois da meia-noite, a mesma troca das 06:00
    (_t(26, 6, 0), _t(26, 6)),         # na hora exata é a que acabou de acontecer
])
def test_a_passagem_vai_para_a_troca_certa(escrita, troca):
    assert TU.troca_da_passagem(escrita) == troca


def test_quem_entra_assume_a_troca_do_turno_ou_a_seguinte_perto_da_hora():
    assert TU.trocas_que_se_pode_assumir(_t(26, 20)) == [_t(26, 18)]
    assert TU.trocas_que_se_pode_assumir(_t(26, 17, 15)) == [_t(26, 6), _t(26, 18)]   # chegou 45 min antes
    assert TU.trocas_que_se_pode_assumir(_t(27, 2)) == [_t(26, 18)]


def test_o_historico_tem_7_dias_e_a_troca_que_vem():
    h = TU.trocas_do_historico(_t(26, 20))
    assert h[0] == _t(27, 6) and h[1] == _t(26, 18) and len(h) == 15 and h == sorted(h, reverse=True)


# --- a situação de cada troca ----------------------------------------------------------------------------------------

def test_sem_passagem_depois_da_tolerancia_e_sem_registro():
    troca = _t(26, 18)
    assert TU.situacao(troca, None, _t(26, 18, 30)) == "aguardando"
    assert TU.situacao(troca, None, _t(26, 19)) == "sem_registro"
    x = {"passagens": [{"hmac": "a"}], "assumiu": []}
    assert TU.situacao(troca, x, _t(26, 18, 30)) == "registrada"
    assert TU.situacao(troca, x, _t(26, 19)) == "sem_assumir"
    assert TU.situacao(troca, {**x, "assumiu": [{"hmac": "b"}]}, _t(26, 19)) == "assumida"


def test_painel_conta_so_as_trocas_que_fecharam(app):
    with app.app_context():
        linhas = [_linha(_t(26, 6), "passagem", _t(26, 5, 50), "a", abertas=4),
                  _linha(_t(26, 6), "assumiu", _t(26, 6, 5), "b"),
                  _linha(_t(25, 18), "passagem", _t(25, 18, 25), "a"),             # registrada 25 min depois, ninguém assumiu
                  _linha(_t(26, 18), "passagem", _t(26, 17, 40), "c")]             # a troca de agora, ainda na tolerância
        p = TU.painel(_t(26, 18, 20), linhas, eu="b")
    h = {x["troca"]: x for x in p["historico"]}
    assert h[_t(26, 6)]["situacao"] == "assumida" and h[_t(26, 6)]["passagens"][0]["abertas"] == 4
    assert h[_t(25, 18)]["situacao"] == "sem_assumir" and h[_t(25, 18)]["atraso_min"] == 25
    assert h[_t(26, 18)]["situacao"] == "registrada" and not h[_t(26, 18)]["fechou"]
    assert h[_t(25, 6)]["situacao"] == "sem_registro"
    # 14 trocas fecharam nos 7 dias (a das 18:00 de hoje ainda está na tolerância); 2 tiveram passagem
    assert (p["fechadas"], p["registradas"], p["assumidas"], p["sem_assumir"]) == (13, 2, 1, 1)
    assert p["sem_registro"] == 11 and p["pct_registradas"] == 15
    assert p["destino"] == _t(26, 18) and p["destino_atrasada"]
    assert [a["troca"] for a in p["assumiveis"]] == [_t(26, 18)]


def test_aberto_no_andamento_soma_so_com_todos_os_clientes_lidos():
    usinas = [{"ocorrencias": [{"severidade_classe": "crit"}, {"severidade_classe": "medio"}]},
              {"ocorrencias": [{"severidade_classe": "alto"}]}, {"ocorrencias": []}]
    a = TU.aberto_no_andamento([AND.Leitura("Cliente A", {"usinas": usinas}), AND.Leitura("Cliente B", {"usinas": []})])
    assert (a["abertas"], a["criticas"]) == (3, 2) and a["por_cliente"][0]["criticas"] == 2
    b = TU.aberto_no_andamento([AND.Leitura("Cliente A", {"usinas": usinas}), AND.Leitura("Cliente B", None, erro="fora")])
    assert b["abertas"] is None and b["por_cliente"][0]["abertas"] == 3     # número pela metade não vai ao livro


# --- gravar ----------------------------------------------------------------------------------------------------------

def test_passar_e_assumir_gravam_cifrado(banco):
    agora = _t(26, 17, 40)
    TU.passar(ANA, "Usina Exemplo Um   em acompanhamento\n\nChamado à distribuidora aberto", agora, abertas=7, criticas=2)
    TU.passar(CAIO, "Sem pendências na minha carteira", agora)
    TU.assumir(BETO, _t(26, 18), _t(26, 18, 5))
    x = TU.por_troca()[_t(26, 18)]
    assert [p["nome"] for p in x["passagens"]] == ["Ana Lima", "Caio Rocha"] and x["assumiu"][0]["nome"] == "Beto Souza"
    assert x["passagens"][0]["texto"] == "Usina Exemplo Um em acompanhamento\n\nChamado à distribuidora aberto"
    assert (x["passagens"][0]["abertas"], x["passagens"][0]["criticas"]) == (7, 2)
    lin = banco.linhas(TU.LIVRO, TU.ABA)
    assert len(lin) == 3 and list(lin[0]) == list(TU.CAB)
    assert lin[0]["turno_que_sai"] == "dia" and lin[0]["data_id_troca"] in (20261026, "20261026")
    # a API do banco tem leitura aberta: nem nome, nem e-mail, nem o texto em claro
    claro = json.dumps(lin, ensure_ascii=False, default=str).lower()
    assert "ana lima" not in claro and ANA["email"] not in claro and "beto souza" not in claro
    assert "acompanhamento" not in claro and "pendências" not in claro


def test_as_recusas(banco):
    with pytest.raises(TU.Recusada, match="login"):                       # a senha de administrador não diz quem é
        TU.passar(None, "texto", _t(26, 17))
    with pytest.raises(TU.Recusada, match="Escreva"):
        TU.passar(ANA, "   \n ", _t(26, 17))
    with pytest.raises(TU.Recusada, match="não aconteceu"):               # assumir sem passagem
        TU.assumir(BETO, _t(26, 18), _t(26, 18, 5))
    TU.passar(ANA, "Nada pendente", _t(26, 17, 50))
    with pytest.raises(TU.Recusada, match="própria passagem"):
        TU.assumir(ANA, _t(26, 18), _t(26, 18, 5))
    TU.assumir(BETO, _t(26, 18), _t(26, 18, 5))
    with pytest.raises(TU.Recusada, match="já assumiu"):
        TU.assumir(BETO, _t(26, 18), _t(26, 18, 6))
    with pytest.raises(TU.Recusada, match="já passou"):                   # a troca de ontem não se assume hoje
        TU.assumir(CAIO, _t(26, 18), _t(27, 7))
    assert len(banco.linhas(TU.LIVRO, TU.ABA)) == 2


def test_quem_ja_assumiu_escreve_para_a_troca_seguinte(banco):
    TU.passar(ANA, "Nada pendente", _t(26, 17, 50))
    TU.assumir(BETO, _t(26, 18), _t(26, 18, 5))
    TU.passar(CAIO, "Esqueci de passar a minha carteira", _t(26, 18, 20))      # quem saiu, atrasado: a das 18:00
    TU.passar(BETO, "Anotação para quem vem às 06:00", _t(26, 18, 30))         # quem entrou: a troca seguinte
    trocas = TU.por_troca()
    assert [p["nome"] for p in trocas[_t(26, 18)]["passagens"]] == ["Ana Lima", "Caio Rocha"]
    assert [p["nome"] for p in trocas[_t(27, 6)]["passagens"]] == ["Beto Souza"]
    assert TU.painel(_t(26, 18, 30), eu=TU.codigo(BETO))["destino"] == _t(27, 6)
    assert TU.painel(_t(26, 18, 30), eu=TU.codigo(CAIO))["destino"] == _t(26, 18)
    assert banco.linhas(TU.LIVRO, TU.ABA)[-1]["turno_que_sai"] == "noite"


def test_catalogo_registra_o_livro_antes_da_gravacao():
    from nexus.dados import catalogo, explica
    l = catalogo.LIVRO_POR_NOME[TU.LIVRO]
    assert l.abas == (TU.ABA,) and l.so_cresce == (TU.ABA,) and not l.no_banco and catalogo.aba_segue_a_regra(TU.ABA)
    f = catalogo.POR_ID["passagem_turno"]
    assert f.fontes == (f"{TU.LIVRO} · {TU.ABA}",) and f.area == "cos" and f.tipo == "transacao"
    assert {m.coluna for m in f.medidas} == {"abertas_qtd", "criticas_qtd"} <= set(TU.CAB)
    assert "passagem_turno" in explica.RESUMO and "passagem_turno" in explica.PARA_QUE


# --- a tela ----------------------------------------------------------------------------------------------------------

@pytest.fixture
def relogio(monkeypatch):
    agora = {"v": _t(26, 17, 40)}
    monkeypatch.setattr(AND, "agora", lambda: agora["v"])
    return agora


def test_tela_passar_e_assumir(banco, app, cliente, relogio):
    _como(cliente, ANA)
    html = cliente.get("/t/cos/turno").get_data(as_text=True)
    assert "Registrar a passagem" in html and "troca de <b>26/10 às 18:00</b>" in html and "Dia → Noite" in html
    assert "não está ligado neste servidor" in html                          # sem o Andamento, vai sem a contagem
    r = cliente.post("/t/cos/turno/passar", data={"texto": "Usina Exemplo Um em acompanhamento"},
                     headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 303 and r.headers["Location"].endswith("/t/cos/turno")
    html = cliente.get("/t/cos/turno").get_data(as_text=True)
    assert "Passagem registrada na troca de 26/10 às 18:00" in html and "Usina Exemplo Um em acompanhamento" in html
    assert "Você passou este turno" in html and "Li e assumi o turno" not in html
    # quem entra lê e assume
    relogio["v"] = _t(26, 18, 5)
    _como(cliente, BETO)
    html = cliente.get("/t/cos/turno").get_data(as_text=True)
    assert "Li e assumi o turno" in html and 'value="2026-10-26T18:00:00-03:00"' in html
    r = cliente.post("/t/cos/turno/assumir", data={"troca": "2026-10-26T18:00:00-03:00"},
                     headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 303
    html = cliente.get("/t/cos/turno").get_data(as_text=True)
    assert "Você assumiu o turno" in html and "Você já assumiu este turno" in html and "Beto Souza" in html


def test_tela_recusa_volta_com_o_texto_e_de_outro_site_nada_grava(banco, app, cliente, relogio):
    _como(cliente, ANA)
    r = cliente.post("/t/cos/turno/assumir", data={"troca": "2026-10-26T18:00:00-03:00"},
                     headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 422 and "Nada foi gravado" in r.get_data(as_text=True)
    assert cliente.post("/t/cos/turno/passar", data={"texto": "x"}, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert cliente.post("/t/cos/turno/assumir", data={"troca": "ontem"}, headers={"Sec-Fetch-Site": "same-origin"}).status_code == 400
    app.config["NEXUS_PESSOA_HMAC"] = None                                  # recusada: o texto digitado volta
    r = cliente.post("/t/cos/turno/passar", data={"texto": "Texto que não se perde"}, headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 422 and "Texto que não se perde</textarea>" in r.get_data(as_text=True)
    assert banco.linhas(TU.LIVRO, TU.ABA) == []


def test_tela_com_a_senha_de_administrador_le_e_nao_grava(banco, app, cliente, relogio):
    _como(cliente, None, admin=True)
    html = cliente.get("/t/cos/turno").get_data(as_text=True)
    assert "Entre com o seu login" in html and "Registrar a passagem" not in html and "Sem registro" in html


def test_tela_com_o_banco_fora_nao_mostra_historico_falso(app, cliente, relogio, monkeypatch):
    def falha(*a, **k):
        raise ConnectionError("banco fora")
    monkeypatch.setattr(TU, "ler_todas", falha)
    _como(cliente, ANA)
    html = cliente.get("/t/cos/turno").get_data(as_text=True)
    assert "Não consegui ler as passagens no banco (ConnectionError)" in html and "Sem registro" not in html


def test_tela_mostra_o_que_esta_aberto_no_andamento(banco, app, cliente, relogio, monkeypatch):
    app.config.update(NEXUS_COS_ANDAMENTO_URL="http://andamento.exemplo:3002", NEXUS_COS_ANDAMENTO_CHAVE="chave-de-teste",
                      NEXUS_COS_ANDAMENTO_CLIENTES="Cliente A,Cliente B")
    resposta = {"versao": 1, "placar": {}, "problemas": [], "eventos": [], "fotografias": [],
                "usinas": [{"ocorrencias": [{"severidade_classe": "crit"}, {"severidade_classe": "medio"}]}]}

    def pedir(f, caminho):
        if caminho.endswith("Cliente%20B"):
            raise AND.FonteErro("o Andamento não respondeu (TimeoutError)")
        return resposta
    monkeypatch.setattr(AND, "_pedir", pedir)
    _como(cliente, ANA)
    html = cliente.get("/t/cos/turno").get_data(as_text=True)
    assert "2 abertas, 1 crítica" in html and "sem leitura" in html and "passagem vai sem a contagem" in html
    cliente.post("/t/cos/turno/passar", data={"texto": "ok"}, headers={"Sec-Fetch-Site": "same-origin"})
    (lin,) = banco.linhas(TU.LIVRO, TU.ABA)
    assert lin["abertas_qtd"] in (None, "")                                 # um cliente sem leitura: sem número

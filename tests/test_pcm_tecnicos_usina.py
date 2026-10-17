"""A visão da tela Técnicos por usina (17/10/2026, nexus/pcm/tecnicos_usina.py).

O que estes testes seguram: a carga inicial pela regra da equipe (a mesma do App: cada pessoa da equipe vê as usinas da
equipe), a linha da usina com os técnicos, a evidência de campo (rondas e fechamentos de 30 dias, a programação da
semana, o técnico do cadastro) e os avisos; os filtros em cascata; a visão por técnico; a tela sem a chave do cadastro;
a usina que mudou de nome no Fracttal (reenviar ao App); e a comparação com a foto do App (só no App, só no Nexus,
pendências para a troca). Banco falso (pg_falso), datas fixas (hoje = 17/10/2026, sábado da W42)."""
import json

import pytest

from pg_falso import ApiPGFalsa
from nexus.cadastro.cifra import Cofre, gerar_chave
from nexus.campo import visao
from nexus.campo.ligacao_cadastro import codigo_da_pessoa
from nexus.pcm import atribuicoes as A
from nexus.pcm import tecnicos_usina as T

HOJE = 20261017
SEGUNDA = 20261012
HMAC = "chave-hmac-de-teste"
CHAVE_CADASTRO = gerar_chave()
F1, F2 = "Cliente A - Usina 1 - SP", "Cliente A - Usina 2 - SP"
PESSOA = {"email": "pcm.teste@exemplo.test", "nome": "Pcm Teste"}


def _aba(api, livro, aba, linhas):
    api.workbooks[livro] = {}
    cab = list(linhas[0]) if linhas else ["vazio"]
    api._id(livro, aba)["linhas"] = [{"headers": cab, "values": [l.get(c) for c in cab]} for l in linhas]


def _usina(uid, nome, equipe, status="OPERAÇÃO", **kw):
    d = {"usina_id": uid, "nome": nome, "codigo": f"CLA-U{uid}", "status": status, "equipe_id": equipe,
         "data_mobilizacao": "2025-10-01", "cliente_id": 1, "excluido": "não", "tecnico_om_id": None,
         "responsavel_om_id": 90}
    d.update(kw)
    return d


USINAS = [_usina(1, "Usina Um", 10, tecnico_om_id=10), _usina(2, "Usina Dois", 10), _usina(3, "Usina Três", 20),
          _usina(4, "Usina Parada", 20, status="DESMOBILIZADA")]
EQUIPES = [{"equipe_id": 10, "nome": "SP Norte 01", "regiao_campo_id": 1},
           {"equipe_id": 20, "nome": "SC Oeste 01", "regiao_campo_id": 2}]
REGIOES = [{"regiao_campo_id": 1, "nome": "Sudeste 03", "ordem": 1, "excluido": "não"},
           {"regiao_campo_id": 2, "nome": "Sul 01", "ordem": 2, "excluido": "não"}]
DE_PARA = [{"usina_id": 1, "sistema": "Fracttal · Classificação 1", "chave_externa": F1},
           {"usina_id": 2, "sistema": "Fracttal · Classificação 1", "chave_externa": F2}]


def _pessoas():
    cofre = Cofre(CHAVE_CADASTRO)

    def p(pid, vinculo, equipe, status, nome, email=None):
        return {"pessoa_id": pid, "vinculo": vinculo, "cargo": "Técnico O&M", "equipe_id": equipe, "status": status,
                "excluido": "não",
                "sensivel_cifrado": cofre.cifrar(json.dumps({"nome": nome, "nome_padrao": nome, "email": email}),
                                                 f"banco/pessoas/{pid}")}
    return [p(10, "Colaborador de campo", 10, "Ativo", "Técnico Dez", "t10@exemplo.test"),
            p(11, "Colaborador de campo", 10, "Ativo", "Técnico Onze", "t11@exemplo.test"),
            p(12, "Colaborador de campo", 20, "Ativo", "Técnico Doze", "t12@exemplo.test"),
            p(13, "Colaborador de campo", None, "Ativo", "Técnico Treze"),
            p(14, "Colaborador de campo", 10, "Desligado", "Técnico Catorze", "t14@exemplo.test"),
            p(90, "Supervisor", None, None, "Responsável Noventa", "r90@exemplo.test")]


def _h(email):
    return codigo_da_pessoa(HMAC, email)


@pytest.fixture
def banco(app, tmp_path):
    api = ApiPGFalsa()
    _aba(api, "cadastro_nexus", "usinas", USINAS)
    _aba(api, "cadastro_nexus", "equipes", EQUIPES)
    _aba(api, "cadastro_nexus", "clientes", [{"cliente_id": 1, "nome": "Cliente A"}])
    _aba(api, "cadastro_nexus", "de_para", DE_PARA)
    _aba(api, "cadastro_nexus", "pessoas", _pessoas())
    _aba(api, "cadastro_nexus", "regioes_campo", REGIOES)
    _aba(api, "nexus_fatos", "fato_ronda", [{"data_id": 20261012, "usina_id": 1, "pessoa_id": 12},
                                            {"data_id": 20260907, "usina_id": 1, "pessoa_id": 10}])
    _aba(api, "nexus_fatos", "fato_fechamento", [{"data_id": 20261014, "usina_id": 2, "pessoa_id": 11}])
    _aba(api, "nexus_programacao", "fato_programacao", [{"data_id_semana": SEGUNDA, "usina_id": 1,
                                                         "pessoa_id_tecnico": 10},
                                                        {"data_id_semana": 20261005, "usina_id": 2,
                                                         "pessoa_id_tecnico": 12}])
    app.config.update(GRIDCO_DB_API="http://pg.falso", NEXUS_PESSOA_HMAC=HMAC, NEXUS_CHAVE_CADASTRO=CHAVE_CADASTRO,
                      NEXUS_PCM_ATRIBUICOES_ARQUIVO=str(tmp_path / "atribuicoes.json"))
    app.extensions["nexus_dados_sessao"] = api
    visao.limpar()
    A.limpar()
    yield api
    app.extensions.pop("nexus_dados_sessao", None)


def _por(app, uid, pid, fracttal=None, hmac=None, **kw):
    A.decidir(app.config, usina_id=uid, usina_fracttal={1: F1, 2: F2}.get(uid, "") if fracttal is None else fracttal,
              pessoa_id=pid, pessoa_hmac=_h(f"t{pid}@exemplo.test") if hmac is None else hmac, na_usina=True,
              usuario=PESSOA, **kw)


def _montar(app, **args):
    with app.test_request_context():
        return T.montar(app.config, args, hoje=HOJE)


def _linha(ctx, uid):
    return next(l for l in ctx["linhas"] if l["usina_id"] == uid)


def test_carga_inicial_e_a_regra_da_equipe(app, banco):
    with app.test_request_context():
        base = visao._Base()
        pessoas = T.pessoas_de_campo(base, app.config)
        peds = T.pedidos_da_carga_inicial(base, pessoas)
    assert {(p["usina_id"], p["pessoa_id"]) for p in peds} == {(1, 10), (1, 11), (2, 10), (2, 11), (3, 12), (4, 12)}
    p1 = next(p for p in peds if (p["usina_id"], p["pessoa_id"]) == (1, 10))
    assert p1["usina_fracttal"] == F1 and p1["pessoa_hmac"] == _h("t10@exemplo.test") and p1["na_usina"] is True
    assert next(p for p in peds if p["usina_id"] == 3)["usina_fracttal"] == ""
    assert 14 not in pessoas and 90 not in pessoas and pessoas[13]["hmac"] == ""


def test_linha_mostra_tecnicos_evidencia_e_avisos(app, banco):
    _por(app, 1, 10)
    _por(app, 1, 13, hmac="")
    ctx = _montar(app)
    l1 = _linha(ctx, 1)
    assert {t["pessoa_id"]: t["sem_email"] for t in l1["tecnicos"]} == {10: False, 13: True}
    ev = {e["pessoa_id"]: e for e in l1["evidencia"]}
    assert ev[12]["rondas"] == 1 and not ev[12]["na_programacao"]
    assert ev[10]["rondas"] == 0 and ev[10]["na_programacao"] and ev[10]["do_cadastro"]   # a ronda de 40 dias não conta
    avisos = " | ".join(l1["avisos"]).lower()
    assert "técnico doze rondou aqui e não está na lista" in avisos and "técnico treze sem e-mail" in avisos
    assert "sem técnico" not in avisos
    assert _linha(ctx, 2)["evidencia"][0]["pessoa_id"] == 11 and _linha(ctx, 2)["evidencia"][0]["fechamentos"] == 1
    a3 = " | ".join(_linha(ctx, 3)["avisos"]).lower()
    assert "sem técnico" in a3 and "sem nome do fracttal" in a3
    assert l1["equipe"] == "SP Norte 01" and l1["regiao"] == "Sudeste 03" and l1["responsavel"] == "Responsável Noventa"
    assert ctx["pessoas_json"] and all(set(p) == {"id", "nome", "equipe_id"} for p in ctx["pessoas_json"])


def test_filtros_em_cascata(app, banco):
    _por(app, 1, 10)
    assert {l["usina_id"] for l in _montar(app)["linhas"]} == {1, 2, 3}
    assert {l["usina_id"] for l in _montar(app, todas="1")["linhas"]} == {1, 2, 3, 4}
    ctx = _montar(app, equipe="SP Norte 01")
    assert {l["usina_id"] for l in ctx["linhas"]} == {1, 2}
    assert [v for v, _n in ctx["opcoes"]["regiao"]] == ["Sudeste 03"]
    assert {v for v, _n in ctx["opcoes"]["equipe"]} == {"SP Norte 01", "SC Oeste 01"}      # não restringe a si mesmo
    vazio = _montar(app, equipe="SC Oeste 01", regiao="Sudeste 03")
    assert vazio["linhas"] == [] and "SC Oeste 01" in {v for v, _n in vazio["opcoes"]["equipe"]}
    assert "Sudeste 03" in {v for v, _n in vazio["opcoes"]["regiao"]}                     # a escolhida fica
    assert {l["usina_id"] for l in _montar(app, situacao="sem_tecnico")["linhas"]} == {2, 3}
    assert {l["usina_id"] for l in _montar(app, q="tecnico dez")["linhas"]} == {1}
    assert {l["usina_id"] for l in _montar(app, q="usina tres")["linhas"]} == {3}


def test_visao_por_tecnico(app, banco):
    _por(app, 1, 10)
    _por(app, 2, 10)
    ctx = _montar(app, ver="tecnico")
    por = {t["pessoa_id"]: t for t in ctx["tecnicos"]}
    assert {u["usina_id"] for u in por[10]["usinas"]} == {1, 2} and por[10]["n_usinas"] == 2
    assert por[12]["n_usinas"] == 0 and por[12]["rondas"] == 1
    assert 14 not in por and 90 not in por
    assert {t["pessoa_id"] for t in _montar(app, ver="tecnico", equipe="SC Oeste 01")["tecnicos"]} == {12}


def test_sem_chave_do_cadastro_a_tela_abre_e_avisa(app, banco):
    _por(app, 1, 10)
    app.config.pop("NEXUS_CHAVE_CADASTRO")
    ctx = _montar(app)
    assert _linha(ctx, 1)["tecnicos"][0]["nome"] == "Pessoa 10"
    assert any("chave do cadastro" in a.lower() for a in ctx["avisos_gerais"])


def test_usina_que_mudou_de_nome_no_fracttal(app, banco):
    _por(app, 1, 10, fracttal="Nome Antigo", ate="2026-10-31")
    assert _linha(_montar(app), 1)["fracttal_mudou"] is True
    with app.test_request_context():
        base = visao._Base()
        peds = T.pedidos_da_reemissao(base, T.pessoas_de_campo(base, app.config), A.ler(app.config, forcar=True), 1,
                                      HOJE)
    assert [(p["pessoa_id"], p["usina_fracttal"], p["ate"]) for p in peds] == [(10, F1, "2026-10-31")]
    assert A.decidir_varias(app.config, peds, PESSOA, "reemissao") == 1
    assert _linha(_montar(app), 1)["fracttal_mudou"] is False


def test_comparacao_com_a_foto_do_app(app, banco):
    _por(app, 1, 10)
    _por(app, 2, 11)
    assert _montar(app)["app"]["existe"] is False

    def linha(usina, email, papel="executa"):
        return {"Usina": usina, "Pessoa (HMAC)": _h(email), "Papel": papel, "De": "2026-09-01", "Ate": None,
                "Origem": "bd_operacoes"}
    _aba(banco, "organizacao_app_campo", "Atribuicoes", [
        linha(F1, "t10@exemplo.test"), linha(F1, "t11@exemplo.test"), linha(F1, "quem.nao.tem.ficha@exemplo.test"),
        linha("Usina Fantasma - XX", "t10@exemplo.test"), linha(F2, "t12@exemplo.test", "responsavel")])
    visao.limpar()
    app_ = _montar(app)["app"]
    assert app_["existe"] is True
    assert [(x["usina_id"], x["pessoa_id"]) for x in app_["so_no_app"]] == [(1, 11)]
    assert [(x["usina_id"], x["pessoa_id"]) for x in app_["so_no_nexus"]] == [(2, 11)]
    assert len(app_["pendencias"]) == 2

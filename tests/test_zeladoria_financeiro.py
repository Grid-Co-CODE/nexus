"""As três funções do financeiro do Radar em Python (etapa 4, 03/11/2026): a mesma regra e a mesma mensagem das funções
do banco do Supabase (`docs/financeiro/*.sql` do Radar), aplicadas pelo gravador num salvamento só. Nomes fictícios."""
import copy

import pytest

from nexus.cadastro.cifra import Cofre, gerar_chave
from nexus.zeladoria import financeiro as F
from nexus.zeladoria import gravacao

HEAD = {"id": "u-head", "email": "head@exemplo.com", "papel": "HEAD", "status": "aprovado"}
ANALISTA = {"id": "u-an", "email": "fulano@exemplo.com", "papel": "Analista", "status": "aprovado"}
AGORA = "2026-11-03T18:00:00+00:00"

ITEM = {"id": "IT-1", "cenario_id": "CEN-1", "descricao": "Roçada", "tipo": "T", "fornecedor_id": "FORN-1",
        "fornecedor_nome": "Fulano MEI", "forma": "mensal", "valor": 100, "n_meses": 3, "agenda": None, "via": "nf",
        "usina": "UFV A", "cliente": "Cliente A", "promovido_em": None, "promovido_por": None, "excluido": False,
        "fornecedor_a_definir": False, "fornecedor_definido_em": None}


def _estado():
    abas = {
        "fin_cenario": [{"id": "CEN-1", "nome": "Plano 2027", "arquivado": False, "excluido": False}],
        "fin_cenario_item": [dict(ITEM),
                             {**ITEM, "id": "IT-2", "descricao": "Limpeza", "forma": "personalizado", "valor": None,
                              "agenda": [{"mes": "2027-01", "valor": 50}, {"mes": "2027-02", "valor": 70}],
                              "fornecedor_id": None, "fornecedor_nome": None, "fornecedor_a_definir": True},
                             {**ITEM, "id": "IT-3", "descricao": "Poda", "fornecedor_id": None, "fornecedor_nome": None}],
        "fin_provisao": [{"id": "PRV-0009", "item_id": "IT-9", "mes": "2026-01", "valor": 1, "excluido": False}],
        "fin_provisao_historico": [],
        "fornecedores": [{"id": "FORN-1", "empresa": "Fulano MEI", "tipo": "Terceirizado", "excluido": False},
                         {"id": "FORN-2", "empresa": "Equipe própria", "tipo": "Primarizado", "excluido": False}],
        "log": [],
    }
    tipos = {a: {c: "text" for l in ls for c in l} for a, ls in abas.items()}
    tipos["fin_provisao_historico"] = {c: "text" for c in ("item_id", "mes", "campo", "valor_antigo", "valor_novo",
                                                           "texto_antigo", "texto_novo", "minimo_conciliado", "motivo",
                                                           "quem", "em")}
    tipos["fin_provisao_historico"]["id"] = "bigint"
    tipos["log"] = {"id": "bigint", "em": "date", "quem": "text", "acao": "text", "alvo": "text"}
    return {"abas": abas, "tipos": tipos, "chaves": {a: "id" for a in abas}, "versao": 0}


def _promover(est, itens, provs, quem=HEAD):
    return F.fin_promover(est, quem, {"p_cenario_id": "CEN-1", "p_item_ids": itens, "p_provisoes": provs}, AGORA)


TRES = [{"item_id": "IT-1", "mes": m, "valor": 100} for m in ("2027-01", "2027-02", "2027-03")]


def test_promover_cria_as_provisoes_numeradas_e_marca_o_item():
    ops, r = _promover(_estado(), ["IT-1"], TRES)
    prv = ops[0]["linhas"]
    assert [p["id"] for p in prv] == ["PRV-0010", "PRV-0011", "PRV-0012"]       # o próximo depois do maior
    assert prv[0]["promovido_por"] == "head@exemplo.com" and prv[0]["fornecedor_nome"] == "Fulano MEI"
    assert ops[1] == {"op": "upsert", "view": "rf_fin_cenario_item",
                      "linhas": [{"id": "IT-1", "promovido_em": AGORA, "promovido_por": "head@exemplo.com"}]}
    assert r["promovidos"] == ["IT-1"] and len(r["provisoes"]) == 3


@pytest.mark.parametrize("provs, msg", [
    (TRES[:2], "as provisões somam 200.0 mas o total do item é 300.0"),
    (TRES + [{"item_id": "IT-1", "mes": "2027-01", "valor": 1}], "mês repetido para o mesmo item"),
    ([{"item_id": "IT-1", "mes": "2027-1", "valor": 300}], "mês fora do formato AAAA-MM"),
    ([{"item_id": "IT-1", "mes": "2027-01", "valor": 0}], "valor inválido no mês 2027-01"),
    ([{"item_id": "IT-2", "mes": "2027-01", "valor": 300}], "há provisão de item que não foi escolhido"),
])
def test_promover_recusa_como_o_banco_do_radar(provs, msg):
    with pytest.raises(F.FinErro, match=msg):
        _promover(_estado(), ["IT-1"], provs)


def test_promover_regras_do_item_e_do_papel():
    with pytest.raises(F.FinErro, match="só o HEAD pode promover"):
        _promover(_estado(), ["IT-1"], TRES, quem=ANALISTA)
    with pytest.raises(F.FinErro, match='ligue o item "Poda" a um fornecedor'):
        _promover(_estado(), ["IT-3"], [{"item_id": "IT-3", "mes": "2027-01", "valor": 300}])
    est = _estado()
    est["abas"]["fin_cenario"][0]["arquivado"] = True
    with pytest.raises(F.FinErro, match="está arquivado"):
        _promover(est, ["IT-1"], TRES)
    # o "a definir" passa sem fornecedor, e o personalizado soma a agenda
    ops, r = _promover(_estado(), ["IT-2"], [{"item_id": "IT-2", "mes": "2027-01", "valor": 50},
                                             {"item_id": "IT-2", "mes": "2027-02", "valor": 70}])
    assert r["promovidos"] == ["IT-2"] and ops[0]["linhas"][0]["fornecedor_a_definir"] is True


def test_promover_de_novo_ignora_e_nao_duplica_o_mes():
    est = _estado()
    est["abas"]["fin_cenario_item"][0]["promovido_em"] = AGORA
    ops, r = _promover(est, ["IT-1"], TRES)
    assert ops == [] and r["ignorados"][0]["motivo"] == "já promovido"


def test_definir_fornecedor_atualiza_o_item_e_as_provisoes_abertas():
    est = _estado()
    est["abas"]["fin_provisao"] += [
        {"id": "PRV-0020", "item_id": "IT-2", "mes": "2027-01", "valor": 50, "excluido": False, "fechamento": None,
         "fornecedor_a_definir": True},
        {"id": "PRV-0021", "item_id": "IT-2", "mes": "2027-02", "valor": 70, "excluido": False, "fechamento": "alinhada",
         "fornecedor_a_definir": True}]
    ops, r = F.fin_definir_fornecedor(est, HEAD, {"p_item_id": "IT-2", "p_fornecedor_id": "FORN-1"}, AGORA)
    assert ops[0]["linhas"][0]["fornecedor_definido_por"] == "head@exemplo.com"
    assert [p["id"] for p in ops[1]["linhas"]] == ["PRV-0020"]                   # a fechada não muda
    assert ops[1]["linhas"][0]["conciliar_a_partir_de"] == AGORA
    assert r["provisoes_atualizadas"] == 1 and r["fornecedor"] == "Fulano MEI"
    with pytest.raises(F.FinErro, match="não serve para um item terceirizado"):
        F.fin_definir_fornecedor(est, HEAD, {"p_item_id": "IT-2", "p_fornecedor_id": "FORN-2"}, AGORA)
    with pytest.raises(F.FinErro, match="não está com fornecedor a definir"):
        F.fin_definir_fornecedor(est, HEAD, {"p_item_id": "IT-1", "p_fornecedor_id": "FORN-1"}, AGORA)


def _promovido():
    est = _estado()
    est["abas"]["fin_cenario_item"][0].update(promovido_em="2026-10-01T00:00:00+00:00", promovido_por="head@exemplo.com")
    est["abas"]["fin_provisao"] += [
        {"id": f"PRV-001{i}", "item_id": "IT-1", "mes": m, "valor": 100, "excluido": False, "fechamento": f}
        for i, (m, f) in enumerate([("2027-01", "alinhada"), ("2027-02", None), ("2027-03", None)])]
    return est


def _editar(est, provs, **mais):
    args = {"p_item_id": "IT-1", "p_provisoes": provs, "p_motivo": "replanejado", "p_usina": "UFV A",
            "p_cliente": "Cliente A", **mais}
    return F.fin_editar_provisao(est, HEAD, args, AGORA)


def test_editar_provisao_tira_muda_inclui_e_deixa_historico():
    ops, r = _editar(_promovido(), [{"mes": "2027-02", "valor": 120, "minimo": 30}, {"mes": "2027-04", "valor": 80}])
    prv = {p["id"]: p for p in ops[0]["linhas"]}
    assert prv["PRV-0012"]["excluido"] is True                                  # o março saiu, para a lixeira
    assert prv["PRV-0011"] == {"id": "PRV-0011", "valor": 120}                  # o fevereiro mudou
    novo = prv["PRV-0013"]
    assert novo["mes"] == "2027-04" and novo["promovido_em"] == "2026-10-01T00:00:00+00:00"   # o promovido original
    campos = [(h["mes"], h["campo"]) for h in ops[-1]["linhas"]]
    assert campos == [("2027-03", "mes_removido"), ("2027-02", "valor"), ("2027-04", "mes_incluido")]
    assert ops[-1]["linhas"][1]["minimo_conciliado"] == 30
    assert r["alteracoes"] == 3 and r["total_antigo"] == 200 and r["total_novo"] == 200


def test_editar_provisao_recusa_como_o_banco_do_radar():
    with pytest.raises(F.FinErro, match="o motivo é obrigatório"):
        _editar(_promovido(), None, p_motivo="  ")
    with pytest.raises(F.FinErro, match="2027-01 tem provisão alinhada ou cancelada"):
        _editar(_promovido(), [{"mes": "2027-01", "valor": 10}])
    with pytest.raises(F.FinErro, match="ficaria abaixo do que já foi conciliado"):
        _editar(_promovido(), [{"mes": "2027-02", "valor": 10, "minimo": 50}])
    with pytest.raises(F.FinErro, match="nada mudou"):
        _editar(_promovido(), [{"mes": "2027-02", "valor": 100}, {"mes": "2027-03", "valor": 100}])
    with pytest.raises(F.FinErro, match="ainda não foi promovido"):
        _editar(_estado(), None, p_usina="UFV B")


def test_editar_so_a_usina():
    ops, r = _editar(_promovido(), None, p_usina=" UFV B ")
    assert ops[0] == {"op": "upsert", "view": "rf_fin_cenario_item", "linhas": [{"id": "IT-1", "usina": "UFV B"}]}
    h = ops[-1]["linhas"][0]
    assert (h["campo"], h["texto_antigo"], h["texto_novo"]) == ("usina", "UFV A", "UFV B") and r["alteracoes"] == 1


def test_o_gravador_chama_tudo_ou_nada(tmp_path):
    g = gravacao.Gravador(base="http://pg.falso", token="t", sessao=None, cofre=Cofre(gerar_chave()),
                          diario=tmp_path / "diario.jsonl")
    g.carregar(_promovido())
    r = g.chamar("fin_editar_provisao", {"p_item_id": "IT-1", "p_motivo": "x", "p_usina": "UFV B", "p_cliente": "Cliente A"},
                 HEAD, 0)
    assert r["dados"]["alteracoes"] == 1 and r["versao"] == 1
    antes = copy.deepcopy(g.estado)
    with pytest.raises(gravacao.Recusa, match="nada mudou"):
        g.chamar("fin_editar_provisao", {"p_item_id": "IT-1", "p_motivo": "x", "p_usina": "UFV B",
                                         "p_cliente": "Cliente A"}, HEAD, 1)
    with pytest.raises(gravacao.Recusa, match="só o HEAD"):
        g.chamar("fin_promover", {"p_cenario_id": "CEN-1", "p_item_ids": ["IT-1"], "p_provisoes": TRES}, ANALISTA, 1)
    assert g.estado == antes                                                     # a recusa não deixou nada pela metade
    hist = g.estado["abas"]["fin_provisao_historico"]
    assert hist[0]["id"] == 1 and hist[0]["em"] and hist[0]["quem"] == "head@exemplo.com"

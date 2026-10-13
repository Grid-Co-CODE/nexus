"""Base > Equipamentos das usinas (Levi, 13/10/2026: "Temos que substituir a aba equipamentos aproveitando o que tem lá e
usando o Nexus como ponto de partida"; "Não quero que faça as conexões automaticamente, quero poder ver e fazer de forma
versátil"). A usina do Registro mestre ligada, à mão, ao nome do Fracttal (a decisão das Ligações) e às chaves do
supervisório, e a estrutura dela (cabines, inversores, strings, potência) no livro `nexus_estrutura_usina`. Nenhum teste
vai à rede: o banco é o falso (`pg_falso`) e o Fracttal, as fontes de teste das Ligações."""
import json

import pytest
from pg_falso import ApiPGFalsa
from test_campo_visao import _aba

from conftest import SENHA_TESTE
from nexus import create_app
from nexus.cadastro import estrutura_usina as E
from nexus.cadastro import ligacoes as L
from nexus.cadastro.cifra import gerar_chave
from nexus.cadastro.servico import Carga
from nexus.dados import catalogo

FR = L.FRACTTAL
FONTES = {FR: [{"chave": "Thopen - Brodowski 1 - SP", "codigo": "BWK100", "nome": "Thopen - Brodowski 1 - SP"},
               {"chave": "Athon - Matões 1 - MA", "codigo": "MTS100", "nome": "Athon - Matões 1 - MA", "tarefas": 843}]}
BASE = "http://pg.falso"
JSON_ = {"Accept": "application/json"}


def _linha_aba(chave, equip, usina="Brodowski", sup="", pai="", kwp=None, n_inv=None, strings=None, full="Sim"):
    return {"": None, "Cliente": "Thopen", "Usina": usina, "Usina Supervisório": chave, "Usina Fractall":
            "Thopen - Brodowski 1 - SP" if usina == "Brodowski" else "", "Equipamento": equip,
            "Equipamento Supervisório": sup, "Equipamento Parente": pai, "Chave": None, "Chave 2": None,
            "Potência (kWp)": kwp, "N de Inversores": n_inv, "String Box": "Não", "Full O&M": full,
            "Strings Ativas": strings, "Observações": None}


# a aba como ela é (13/10/2026): na Altair, a UFV e as UG ficam numa chave e os inversores em outra, por cabine
ABA = [_linha_aba("Brodowski", "UFV", kwp=1000.0, n_inv=4),
       _linha_aba("Brodowski", "UG 01", kwp=500.0, n_inv=2),
       _linha_aba("Brodowski", "UG 02", kwp=500.0, n_inv=2),
       _linha_aba("Brodowski 1 (90)", "Inversor 1.1", sup="INVERSOR01", pai="UG 01", kwp=250.0, strings=20),
       _linha_aba("Brodowski 1 (90)", "Inversor 1.2", sup="INVERSOR02", pai="UG 01", kwp=250.0, strings=20),
       _linha_aba("Brodowski 2 (91)", "Inversor 2.1", sup="INVERSOR01", pai="UG 02", kwp=None, strings=18),
       _linha_aba("Brodowski 2 (91)", "Inversor 2.2", sup="INVERSOR02", pai="UG 02", kwp=None, strings=None),
       _linha_aba("", "Inversor 1", usina="Pedra do Sal", sup="INV-1", pai="", kwp=100.0, strings=10, full="Não"),
       _linha_aba("Brodowski", "Medidor", kwp=None)]                   # outro equipamento: fica de fora
ATIVOS = [{"equipamento_id": 7001, "codigo": "THPN-BWK100-INVR-01", "descricao": "Inversor 01", "usina_id": 1,
           "familia": "INVR"},
          {"equipamento_id": 7002, "codigo": "THPN-BWK100-CABN-01", "descricao": "Cabine 01", "usina_id": 1,
           "familia": "CABN"},
          {"equipamento_id": 7003, "codigo": "ATH-MTS100-INVR-01", "descricao": "Inversor", "usina_id": 2,
           "familia": "INVR"}]


@pytest.fixture(autouse=True)
def _sem_copias():
    E._CACHE.clear()
    yield
    E._CACHE.clear()


@pytest.fixture
def banco():
    api = ApiPGFalsa()
    _aba(api, "bd_performance", "Equipamentos", ABA)
    _aba(api, "nexus_equipamentos", "dim_equipamento", ATIVOS)
    return api


@pytest.fixture
def cfg():
    return {"GRIDCO_SQL_TOKEN": "token-de-teste", "NEXUS_PESSOA_HMAC": "chave-de-teste"}


@pytest.fixture
def app_eq(tmp_path, banco):
    app = create_app({"NEXUS_SECRET_KEY": "chave-de-teste", "NEXUS_SENHA_ADMIN": SENHA_TESTE,
                      "NEXUS_CHAVE_CADASTRO": gerar_chave(), "NEXUS_ARMAZEM_LOCAL": str(tmp_path / "cadastro.json"),
                      "NEXUS_DADOS": str(tmp_path / "dados")})
    app.config.update({"TESTING": True, "SESSION_COOKIE_SECURE": False, "NEXUS_LIGACOES_FONTES_TESTE": FONTES,
                       "GRIDCO_DB_API": BASE, "GRIDCO_SQL_TOKEN": "token-de-teste",
                       "NEXUS_PESSOA_HMAC": "chave-de-teste"})
    app.extensions["nexus_dados_sessao"] = banco
    from nexus.cadastro.telas import servico
    with app.app_context():
        servico().aplicar_carga(Carga(
            entidades={
                "clientes": [{"id": "1", "ordem": 1, "valores": {"nome": "Thopen"}},
                             {"id": "3", "ordem": 2, "valores": {"nome": "Athon"}}],
                "usinas": [
                    {"id": "1", "ordem": 1, "valores": {"nome": "Brodowski", "codigo": "THPN-BWK100", "cliente": "1",
                                                         "status": "OPERAÇÃO", "cidade": "Brodowski", "uf": "SP",
                                                         "potencia_contratual": 1.0}},
                    {"id": "2", "ordem": 2, "valores": {"nome": "Matões 100", "codigo": "CÓDIGO", "cliente": "3",
                                                         "status": "OPERAÇÃO", "cidade": "Matões", "uf": "MA",
                                                         "potencia_contratual": 0.4, "potencia_real": 0.5}},
                ]},
            listas={"status_usina": ["OPERAÇÃO"], "uf": ["SP", "MA"]}))
        L.calcular(app.config, servico())
    yield app
    app.extensions.pop("nexus_dados_sessao", None)


@pytest.fixture
def cli(app_eq):
    c = app_eq.test_client()
    assert c.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    return c


def _estado(banco):
    return {"sup": banco.linhas(E.LIVRO, E.ABA_SUP), "cab": banco.linhas(E.LIVRO, E.ABA_CAB),
            "inv": banco.linhas(E.LIVRO, E.ABA_INV)}


def _editor(cfg, banco, usina_id):
    return E.da_usina(E.ler(BASE, banco, forcar=True), usina_id)


# ── a aba Equipamentos (só referência) ───────────────────────────────────────────────────────────────────────────────
def test_a_aba_agrupa_por_chave_do_supervisorio():
    g = E.agrupar_aba(ABA)
    assert set(g) == {"Brodowski", "Brodowski 1 (90)", "Brodowski 2 (91)", "Pedra do Sal"}   # sem chave: a "Usina"
    b = g["Brodowski"]
    assert (b["ufv_kwp"], b["ufv_inversores"], b["fracttal"], b["full_om"]) == (1000.0, 4, "Thopen - Brodowski 1 - SP", True)
    assert [c["nome"] for c in b["cabines"]] == ["UG 01", "UG 02"] and b["inversores"] == []
    inv = g["Brodowski 2 (91)"]["inversores"]
    assert inv[0] == {"nome": "Inversor 2.1", "equipamento_supervisorio": "INVERSOR01", "cabine": "UG 02", "kwp": None,
                      "strings": 18}
    assert inv[1]["strings"] is None and g["Pedra do Sal"]["full_om"] is False


# ── as chaves do supervisório ────────────────────────────────────────────────────────────────────────────────────────
def test_ligar_chave_uma_usina_por_chave_e_o_id_nao_volta(cfg, banco):
    r = E.ligar_supervisorio(1, " Brodowski  1 (90) ", cfg, BASE, banco, quem_email="admin@exemplo.test")
    assert {k: r[k] for k in ("supervisorio_id", "novo", "log")} == {
        "supervisorio_id": 1, "novo": True, "log": "ligou a chave Brodowski 1 (90) à usina 1"}
    assert E.ligar_supervisorio(1, "Brodowski 1 (90)", cfg, BASE, banco)["novo"] is False      # já estava
    with pytest.raises(E.Recusada, match="já está ligada a outra usina"):
        E.ligar_supervisorio(2, "Brodowski 1 (90)", cfg, BASE, banco)
    with pytest.raises(E.Recusada, match="não está ligada a esta usina"):
        E.desligar_supervisorio(1, 2, cfg, BASE, banco)                       # a chave é da usina 1
    assert E.desligar_supervisorio(1, 1, cfg, BASE, banco)["inversores_sem_chave"] == 0
    assert E.ligar_supervisorio(2, "Brodowski 1 (90)", cfg, BASE, banco)["supervisorio_id"] == 2   # o 1 não volta
    sup = _estado(banco)["sup"]
    assert [(x["supervisorio_id"], x["usina_id"], x["excluido"]) for x in sup] == [(1, 1, "sim"), (2, 2, None)]
    assert list(sup[0]) == list(E.CAB_SUP) and sup[0]["full_om"] == 0 and sup[0]["substitui_aba"] == 0
    assert sup[1]["principal"] == 1                               # a 1ª chave da usina 2 é a da usina


def test_desligar_a_chave_deixa_os_inversores_na_usina_sem_chave(cfg, banco):
    sid = E.ligar_supervisorio(1, "Brodowski 1 (90)", cfg, BASE, banco)["supervisorio_id"]
    u = _editor(cfg, banco, 1)
    E.salvar_usina(1, {"inversores": [{"nome": "Inversor 1.1", "chave": sid}]}, E.selo(u), cfg, BASE, banco)
    r = E.desligar_supervisorio(sid, 1, cfg, BASE, banco)
    assert r["inversores_sem_chave"] == 1
    inv = _estado(banco)["inv"]
    assert len(inv) == 1 and inv[0]["supervisorio_id"] is None and inv[0]["excluido"] is None


# ── a estrutura ──────────────────────────────────────────────────────────────────────────────────────────────────────
def _montar(cfg, banco):
    s1 = E.ligar_supervisorio(1, "Brodowski 1 (90)", cfg, BASE, banco)["supervisorio_id"]
    s2 = E.ligar_supervisorio(1, "Brodowski 2 (91)", cfg, BASE, banco)["supervisorio_id"]
    dados = {"chaves": [{"supervisorio_id": s1, "full_om": True, "string_box": False, "principal": True}],
             "cabines": [{"k": "n1", "nome": "UG 01", "potencia_kwp": "500"}, {"k": "n2", "nome": "UG 02", "potencia_kwp": 500}],
             "inversores": [
                 {"nome": "Inversor 1.1", "chave": s1, "cabine": "n1", "equipamento_supervisorio": "INVERSOR01",
                  "potencia_kwp": "250,5", "strings_esperadas_qtd": "20", "equipamento_id": 7001,
                  "codigo_fracttal": "THPN-BWK100-INVR-01"},
                 {"nome": "Inversor 1.2", "chave": s1, "cabine": "n1", "equipamento_supervisorio": "INVERSOR02",
                  "potencia_kwp": 249.5, "strings_esperadas_qtd": 20},
                 {"nome": "Inversor 2.1", "chave": s2, "cabine": "n2", "equipamento_supervisorio": "INVERSOR01",
                  "strings_esperadas_qtd": 18},                              # o mesmo nome no supervisório, outra chave
                 {"nome": "Inversor 2.2", "chave": s2, "cabine": "n2", "equipamento_supervisorio": "INVERSOR02"}]}
    r = E.salvar_usina(1, dados, E.selo(_editor(cfg, banco, 1)), cfg, BASE, banco, quem_email="admin@exemplo.test")
    return s1, s2, r


def test_salvar_cria_a_estrutura_com_a_cabine_da_usina_e_o_inversor_da_chave(cfg, banco):
    s1, s2, r = _montar(cfg, banco)
    assert r["mudancas"] == 7                     # 1 chave (Full O&M) + 2 cabines + 4 inversores
    est = _estado(banco)
    assert [(c["cabine_id"], c["nome"], c["potencia_kwp"], c["usina_id"]) for c in est["cab"]] == [
        (1, "UG 01", 500, 1), (2, "UG 02", 500, 1)]
    inv = {i["nome"]: i for i in est["inv"]}
    assert (inv["Inversor 1.1"]["supervisorio_id"], inv["Inversor 1.1"]["cabine_id"], inv["Inversor 1.1"]["potencia_kwp"],
            inv["Inversor 1.1"]["strings_esperadas_qtd"], inv["Inversor 1.1"]["equipamento_id"]) == (s1, 1, 250.5, 20, 7001)
    assert inv["Inversor 2.1"]["supervisorio_id"] == s2 and inv["Inversor 2.1"]["cabine_id"] == 2
    assert {x["supervisorio_id"]: x["full_om"] for x in est["sup"]} == {s1: 1, s2: 0}
    # potência: a da cabine 2 (500) dividida pelos 2 inversores dela, sem kWp, conta como calculado
    res = r["resumo"]
    assert (res["chaves"], res["cabines"], res["inversores"], res["strings"]) == (2, 2, 4, 58)
    assert (res["kwp_cabines"], res["kwp_inversores"], res["kwp_calculado"]) == (1000, 1000, 500)
    assert (res["sem_chave"], res["sem_cabine"], res["sem_strings"]) == (0, 0, 1)
    assert E.conferir_potencia(1000.0, res["kwp_inversores"]) == "fecha"
    assert E.conferir_potencia(1000.0, 970) == "perto" and E.conferir_potencia(1000.0, 800) == "nao_fecha"
    assert E.conferir_potencia(None, 800) == ""
    # regra 8: quem mudou, só o código; nada de e-mail no livro de leitura aberta
    tudo = [str(v) for aba in est.values() for x in aba for v in x.values()]
    assert not [v for v in tudo if "@" in v] and all(x["alterado_por_hmac"] for x in est["inv"])


def test_salvar_de_novo_atualiza_o_que_mudou_exclui_o_que_saiu_e_o_id_nao_volta(cfg, banco):
    s1, s2, _ = _montar(cfg, banco)
    u = _editor(cfg, banco, 1)
    antes = {i["nome"]: i for i in _estado(banco)["inv"]}
    # sem mexer: nada muda (abrir e salvar não gera alteração)
    ed = {"chaves": [{k: s[k] for k in ("supervisorio_id", "usina_exibicao", "principal", "full_om", "string_box",
                                        "substitui_aba")} for s in u["supervisorios"]],
          "cabines": [{"id": c["cabine_id"], "k": f"c{c['cabine_id']}", **{k: c[k] for k in ("nome", "potencia_kwp",
                       "equipamento_id", "codigo_fracttal")}} for c in u["cabines"]],
          "inversores": [{"id": i["inversor_id"], "chave": i["supervisorio_id"], "cabine": f"c{i['cabine_id']}",
                          **{k: i[k] for k in ("nome", "equipamento_supervisorio", "potencia_kwp",
                                               "strings_esperadas_qtd", "equipamento_id", "codigo_fracttal")}}
                         for i in u["inversores"]]}
    assert E.salvar_usina(1, ed, E.selo(u), cfg, BASE, banco)["mudancas"] == 0
    # muda as strings de um, tira o 1.2, renomeia a UG 02 e põe um inversor novo
    ed["inversores"][0]["strings_esperadas_qtd"] = 22
    ed["inversores"] = [i for i in ed["inversores"] if i["nome"] != "Inversor 1.2"]
    ed["cabines"][1]["nome"] = "Cabine 2"
    ed["inversores"].append({"nome": "Inversor 2.3", "chave": s2, "cabine": "c2"})
    r = E.salvar_usina(1, ed, E.selo(u), cfg, BASE, banco)
    assert r["mudancas"] == 6                     # + a ordem dos dois depois do 1.2, que subiram (a ordem é gravada)
    inv = {i["inversor_id"]: i for i in _estado(banco)["inv"]}
    assert inv[antes["Inversor 1.1"]["inversor_id"]]["strings_esperadas_qtd"] == 22
    assert inv[antes["Inversor 1.2"]["inversor_id"]]["excluido"] == "sim"
    assert inv[5]["nome"] == "Inversor 2.3" and inv[5]["cabine_id"] == 2      # id novo = maior + 1
    assert _estado(banco)["cab"][1]["nome"] == "Cabine 2" and r["resumo"]["inversores"] == 4
    assert [i["inversor_id"] for i in r["usina"]["inversores"]] == [1, 3, 4, 5]


def test_salvar_recusa_o_que_nao_deve_e_nao_grava_nada(cfg, banco):
    s1, s2, _ = _montar(cfg, banco)
    u = _editor(cfg, banco, 1)
    selo = E.selo(u)
    sid_outra = E.ligar_supervisorio(2, "Pedra do Sal", cfg, BASE, banco)["supervisorio_id"]
    u = _editor(cfg, banco, 1)
    assert E.selo(u) == selo                                       # a chave de outra usina não muda o selo desta
    antes = json.dumps(_estado(banco), sort_keys=True, default=str)
    casos = [
        ({"cabines": [{"nome": "UG 01"}, {"nome": "ug  01"}]}, "Duas cabines"),
        ({"cabines": [{"nome": ""}]}, "sem nome"),
        ({"inversores": [{"nome": "A"}, {"nome": "a"}]}, "Dois inversores"),
        ({"inversores": [{"nome": "A", "chave": s1, "equipamento_supervisorio": "INV1"},
                         {"nome": "B", "chave": s1, "equipamento_supervisorio": "inv1"}]}, "mesma chave"),
        ({"inversores": [{"nome": "A", "cabine": "x9"}]}, "cabine que não está na lista"),
        ({"cabines": [{"nome": "UG 01", "potencia_kwp": "-3"}]}, "não é um número"),
        ({"inversores": [{"nome": "A", "strings_esperadas_qtd": "2,5"}]}, "número inteiro"),
        ({"inversores": [{"nome": "A", "chave": sid_outra}]}, "não é desta usina"),
    ]
    for dados, msg in casos:
        with pytest.raises(E.Recusada, match=msg):
            E.salvar_usina(1, dados, selo, cfg, BASE, banco)
    with pytest.raises(E.Recusada, match="mudou desde que a tela abriu"):
        E.salvar_usina(1, {}, "selo-velho", cfg, BASE, banco)
    with pytest.raises(E.Recusada, match="Escolha a usina"):
        E.salvar_usina(None, {}, selo, cfg, BASE, banco)
    assert json.dumps(_estado(banco), sort_keys=True, default=str) == antes


def test_sem_token_ou_com_o_banco_fora_nada_grava(cfg, banco):
    with pytest.raises(E.Recusada, match="GRIDCO_SQL_TOKEN"):
        E.ligar_supervisorio(1, "Brodowski", dict(cfg, GRIDCO_SQL_TOKEN=None), BASE, banco)

    class Fora:
        def get(self, *a, **k):
            raise ConnectionError("banco fora")
        post = get
    with pytest.raises(E.Recusada, match="nada foi gravado"):
        E.ligar_supervisorio(1, "Brodowski", cfg, BASE, Fora())
    assert _estado(banco)["sup"] == [] and banco.syncs == 0
    # a leitura que falha devolve vazio com o erro (sem cópia boa), e a tela não deixa gravar
    assert E.ler(BASE, Fora(), forcar=True)["erro"].startswith("ConnectionError")


def test_ativos_do_fracttal_por_usina(banco):
    a = E.ativos_da_usina(BASE, banco, 1)
    assert a["erro"] == "" and [x["codigo"] for x in a["ativos"]] == ["THPN-BWK100-CABN-01", "THPN-BWK100-INVR-01"]
    assert [x["equipamento_id"] for x in E.ativos_da_usina(BASE, banco, 2)["ativos"]] == [7003]
    assert E.ativos_da_usina(BASE, banco, 99)["ativos"] == []


# ── a tela ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_so_administrador(app_eq):
    c = app_eq.test_client()
    with c.session_transaction() as s:
        s["logado"] = True; s["admin"] = False
        s["usuario"] = {"email": "pessoa@exemplo.test", "nome": "Pessoa", "perfil": ""}
    assert c.get("/t/base/equipamentos").status_code == 403
    assert c.post("/t/base/equipamentos/chave", data={"usina": 1, "acao": "ligar", "chave": "X"}).status_code == 403
    assert c.post("/t/base/equipamentos/salvar", json={"usina_id": 1}).status_code == 403
    assert c.get("/t/base/equipamentos/ativos?usina=1").status_code == 403
    assert app_eq.extensions["nexus_dados_sessao"].syncs == 0


def test_a_tela_mostra_a_lista_e_os_dois_passos_sem_fracttal_e_sem_ligar_nada_sozinha(cli, banco):
    html = cli.get("/t/base/equipamentos").get_data(as_text=True)
    assert "Equipamentos das usinas" in html and "Como funciona" in html and "Matões 100" in html
    # sem Fracttal na tela (Levi, 13/10/2026: a UFV já liga ao Fracttal pelo código no Registro mestre)
    assert "sem Fracttal" not in html and "Com nome do Fracttal" not in html
    html = cli.get("/t/base/equipamentos?usina=1").get_data(as_text=True)
    for passo in ('id="passo-chave"', 'id="passo-estrutura"', 'id="eq-dados"'):
        assert passo in html
    assert 'id="passo-fracttal"' not in html and "ativos_url" not in html.split('id="eq-dados"')[0]
    # a tabela nas colunas da aba Equipamentos, e o editor não pede os ativos do Fracttal
    for col in ("Usina Supervisório", "Equipamento Supervisório", "Equipamento Parente", "Strings Ativas"):
        assert col in html
    assert "pedirAtivos" not in html and "Ativo no Fracttal" not in html
    # as chaves da aba com motivo vêm primeiro, com o porquê, e nenhuma vem escolhida
    sugeridas = html.split('label="Com motivo para esta usina"')[1].split("</optgroup>")[0]
    assert "Brodowski 1 (90) — nome parecido" in sugeridas and " selected" not in sugeridas
    assert "Fracttal" not in sugeridas
    assert "Nenhuma chave do supervisório ligada" in html
    dados = json.loads(html.split('id="eq-dados">')[1].split("</script>")[0])
    assert dados["usina_id"] == 1 and dados["kwp_usina"] == 1000.0 and dados["chaves"] == [] and dados["selo"]
    assert dados["kwp_de"] == "contratual"                          # sem a real, confere pela contratual
    assert _estado(banco)["sup"] == []                              # abrir não grava nada
    # com a potência real na ficha, é ela que vale (a aba Equipamentos bate com a real), e a contratual fica à vista
    html = cli.get("/t/base/equipamentos?usina=2").get_data(as_text=True)
    dados = json.loads(html.split('id="eq-dados">')[1].split("</script>")[0])
    assert (dados["kwp_usina"], dados["kwp_de"]) == (500.0, "real") and "contratual 400,0 kWp" in html


def test_ligar_o_fracttal_pela_tela_e_a_decisao_das_ligacoes(app_eq, cli):
    r = cli.post("/t/base/equipamentos/fracttal", data={"usina": 2, "acao": "ligar", "chave": "Athon - Matões 1 - MA"})
    assert r.status_code == 303 and "usina=2" in r.headers["Location"]
    linha = next(x for x in L.ler(app_eq.config)["linhas"] if x[1] == FR and x[2] == "Athon - Matões 1 - MA")
    assert linha[0] == 2 and linha[3].startswith("manual (") and "admin" not in linha[3]
    regras = json.loads(L.caminho_regras(app_eq.config).read_text(encoding="utf-8"))
    assert regras["ligar"][0]["chave"] == "Athon - Matões 1 - MA" and regras["ligar"][0]["quem"] == "admin"
    html = cli.get(r.headers["Location"]).get_data(as_text=True)
    assert "ligado a esta usina" in html and "Publicar no banco" in html
    # nome que não é do Fracttal lido não liga
    r = cli.post("/t/base/equipamentos/fracttal", data={"usina": 2, "acao": "ligar", "chave": "Inventado - X"})
    assert "não está na lista do Fracttal" in cli.get(r.headers["Location"]).get_data(as_text=True)


def test_ligar_chave_e_salvar_a_estrutura_pela_tela(cli, banco):
    r = cli.post("/t/base/equipamentos/chave", data={"usina": 1, "acao": "ligar", "chave": "Brodowski 1 (90)",
                                                     "q": "brod", "filtro": "sem_chave"})
    assert r.status_code == 303 and "usina=1" in r.headers["Location"] and "q=brod" in r.headers["Location"]
    html = cli.get(r.headers["Location"]).get_data(as_text=True)
    assert "Chave “Brodowski 1 (90)” ligada a esta usina." in html
    dados = json.loads(html.split('id="eq-dados">')[1].split("</script>")[0])
    sid = dados["chaves"][0]["supervisorio_id"]
    # chave digitada que não está na aba: liga, e o aviso pede para conferir
    r = cli.post("/t/base/equipamentos/chave", data={"usina": 1, "acao": "ligar", "chave_nova": "Brodowski Nova"})
    assert "não está na aba Equipamentos" in cli.get(r.headers["Location"]).get_data(as_text=True)
    html = cli.get("/t/base/equipamentos?usina=1").get_data(as_text=True)
    dados = json.loads(html.split('id="eq-dados">')[1].split("</script>")[0])
    corpo = {"usina_id": 1, "selo": dados["selo"], "chaves": [], "cabines": [{"k": "n1", "nome": "UG 01", "potencia_kwp": 500}],
             "inversores": [{"nome": "Inversor 1.1", "chave": sid, "cabine": "n1", "strings_esperadas_qtd": 20}]}
    r = cli.post("/t/base/equipamentos/salvar", json=corpo, headers=JSON_)
    j = r.get_json()
    assert r.status_code == 200 and j["ok"] and j["aviso"].startswith("Salvo: 2 mudanças")
    assert j["editor"]["cabines"][0]["k"] == "c1" and j["editor"]["inversores"][0] == {
        "id": 1, "nome": "Inversor 1.1", "chave": sid, "cabine": "c1", "equipamento_supervisorio": "",
        "potencia_kwp": None, "strings_esperadas_qtd": 20, "equipamento_id": None, "codigo_fracttal": ""}
    # o mesmo corpo com o selo velho: a usina mudou, nada grava
    r = cli.post("/t/base/equipamentos/salvar", json=corpo, headers=JSON_)
    assert r.status_code == 409 and "mudou desde que a tela abriu" in r.get_json()["erro"]
    # outro site não grava
    r = cli.post("/t/base/equipamentos/salvar", json=dict(corpo, selo=j["editor"]["selo"]),
                 headers=dict(JSON_, **{"Sec-Fetch-Site": "cross-site"}))
    assert r.status_code == 403
    # desligar a chave pela tela: o inversor fica, sem chave
    r = cli.post("/t/base/equipamentos/chave", data={"usina": 1, "acao": "desligar", "supervisorio_id": sid})
    assert "1 inversor(es) ficaram sem chave" in cli.get(r.headers["Location"]).get_data(as_text=True)
    assert _estado(banco)["inv"][0]["supervisorio_id"] is None


def test_os_ativos_da_usina_pela_tela(cli):
    j = cli.get("/t/base/equipamentos/ativos?usina=1").get_json()
    assert [x["familia"] for x in j["ativos"]] == ["CABN", "INVR"] and j["erro"] == ""


def test_catalogo_e_menu():
    livro = catalogo.LIVRO_POR_NOME["nexus_estrutura_usina"]
    assert livro.abas == (E.ABA_SUP, E.ABA_CAB, E.ABA_INV, E.ABA_VISAO) and livro.no_banco is False
    assert catalogo.aba_segue_a_regra(E.ABA_VISAO)                  # exceção declarada, com o porquê
    from nexus.torres.base import TORRE
    assert "equipamentos" in [t.id for t in TORRE.telas]


# ── no lugar da aba: a visão, a sobreposição e a comparação (13/10/2026) ─────────────────────────────────────────────
INFO = {1: {"nome": "Brodowski", "cliente": "Thopen", "kwp": 1000.0, "fracttal": "Thopen - Brodowski 1 - SP"}}


def _igual_a_aba(cfg, banco, marcar=True):
    """A Brodowski montada no Nexus exatamente como a aba a tem (é o que o "Trazer da aba" faz), com as três chaves."""
    ids = [E.ligar_supervisorio(1, k, cfg, BASE, banco, exibicao_aba="Brodowski", info=INFO)["supervisorio_id"]
           for k in ("Brodowski", "Brodowski 1 (90)", "Brodowski 2 (91)")]
    u = _editor(cfg, banco, 1)
    assert [s["principal"] for s in u["supervisorios"]] == [True, False, False]      # a 1ª ligada é a da usina
    dados = {"chaves": [{"supervisorio_id": s, "usina_exibicao": "Brodowski", "principal": s == ids[0], "full_om": True,
                         "string_box": False, "substitui_aba": marcar} for s in ids],
             "cabines": [{"k": "n1", "nome": "UG 01", "potencia_kwp": 500}, {"k": "n2", "nome": "UG 02", "potencia_kwp": 500}],
             "inversores": [
                 {"nome": "Inversor 1.1", "chave": ids[1], "cabine": "n1", "equipamento_supervisorio": "INVERSOR01",
                  "potencia_kwp": 250, "strings_esperadas_qtd": 20},
                 {"nome": "Inversor 1.2", "chave": ids[1], "cabine": "n1", "equipamento_supervisorio": "INVERSOR02",
                  "potencia_kwp": 250, "strings_esperadas_qtd": 20},
                 {"nome": "Inversor 2.1", "chave": ids[2], "cabine": "n2", "equipamento_supervisorio": "INVERSOR01",
                  "strings_esperadas_qtd": 18},
                 {"nome": "Inversor 2.2", "chave": ids[2], "cabine": "n2", "equipamento_supervisorio": "INVERSOR02"}]}
    r = E.salvar_usina(1, dados, E.selo(u), cfg, BASE, banco, info=INFO)
    return ids, r


def test_a_visao_tem_o_formato_da_aba_e_so_as_chaves_marcadas(cfg, banco):
    ids, r = _igual_a_aba(cfg, banco, marcar=False)
    assert r["visao_linhas"] == 0 and banco.linhas(E.LIVRO, E.ABA_VISAO) == []          # nada marcado, visão vazia
    u = _editor(cfg, banco, 1)
    linhas = E.visao_da_usina(u, INFO[1], todas=True)
    assert list(linhas[0]) == list(E.CAB_VISAO)
    ufv = linhas[0]
    # a chave da usina é o próprio nome de exibição: a UFV sai sem "Usina Supervisório", como 103 das 146 da aba
    assert (ufv["Equipamento"], ufv["Usina Supervisório"], ufv["Usina"], ufv["Potência (kWp)"], ufv["N de Inversores"],
            ufv["Chave 2"], ufv["Full O&M"], ufv["Usina Fractall"]) == (
        "UFV", None, "Brodowski", 1000.0, 4, "UFV", "Sim", "Thopen - Brodowski 1 - SP")
    ug = [x for x in linhas if x["Equipamento"].startswith("UG")]
    assert [(x["Equipamento"], x["Equipamento Parente"], x["N de Inversores"]) for x in ug] == [
        ("UG 01", "UFV", 2), ("UG 02", "UFV", 2)]
    inv = next(x for x in linhas if x["Equipamento"] == "Inversor 1.1")
    assert (inv["Usina Supervisório"], inv["Equipamento Supervisório"], inv["Equipamento Parente"], inv["Chave"],
            inv["Chave 2"], inv["Strings Ativas"]) == (
        "Brodowski 1 (90)", "INVERSOR01", "UG 01", "Brodowski 1 (90)INVERSOR01", "Brodowski 1 (90)Inversor 1.1", 20)
    # marcar duas chaves: a visão leva só as delas, gravada junto do estado
    dados = {"chaves": [{"supervisorio_id": s["supervisorio_id"], "usina_exibicao": s["usina_exibicao"],
                         "principal": s["principal"], "full_om": s["full_om"], "string_box": s["string_box"],
                         "substitui_aba": s["supervisorio_id"] != ids[2]} for s in u["supervisorios"]],
             **{k: v for k, v in _payload_de(u).items() if k != "chaves"}}
    r = E.salvar_usina(1, dados, E.selo(u), cfg, BASE, banco, info=INFO)
    gravada = banco.linhas(E.LIVRO, E.ABA_VISAO)
    assert r["visao_mudou"] and r["visao_linhas"] == len(gravada) == 5        # UFV + 2 UG + 2 inversores da chave 90
    assert {E.chave_efetiva(x) for x in gravada} == {"Brodowski", "Brodowski 1 (90)"}
    # nome que não começa por "Inversor": os leitores só contam o que começa assim
    assert E.nome_de_inversor("INV 7") == "Inversor INV 7" and E.nome_de_inversor("inversor 3") == "inversor 3"


def _payload_de(u):
    return {"chaves": [{k: s[k] for k in ("supervisorio_id", "usina_exibicao", "principal", "full_om", "string_box",
                                          "substitui_aba")} for s in u["supervisorios"]],
            "cabines": [{"id": c["cabine_id"], "k": f"c{c['cabine_id']}", **{k: c[k] for k in (
                "nome", "potencia_kwp", "equipamento_id", "codigo_fracttal")}} for c in u["cabines"]],
            "inversores": [{"id": i["inversor_id"], "chave": i["supervisorio_id"],
                            "cabine": f"c{i['cabine_id']}" if i["cabine_id"] else None,
                            **{k: i[k] for k in ("nome", "equipamento_supervisorio", "potencia_kwp",
                                                 "strings_esperadas_qtd", "equipamento_id", "codigo_fracttal")}}
                           for i in u["inversores"]]}


def test_montada_igual_a_aba_a_comparacao_diz_igual_e_a_sobreposicao_nao_muda_nada(cfg, banco):
    """A prova da troca: a Brodowski montada no Nexus como a aba a tem, as três chaves no lugar da aba, e o leitor vê
    exatamente o que via (agrupar_aba é o leitor de referência: chave, exibição, Fracttal, cliente, UFV, UG, inversores)."""
    ids, _r = _igual_a_aba(cfg, banco)
    u = _editor(cfg, banco, 1)
    cmp = E.comparar_usina(u, INFO[1], E.agrupar_aba(ABA))
    assert all(c["iguais"] for c in cmp.values()), cmp
    visao = banco.linhas(E.LIVRO, E.ABA_VISAO)
    assert len(visao) == 7                                       # UFV, 2 UG e 4 inversores
    junta = E.sobrepor(ABA, visao)
    assert E.agrupar_aba(junta) == E.agrupar_aba(ABA)
    assert sum(1 for x in junta if x.get("Equipamento") == "Medidor") == 1     # o que não é UFV, UG nem inversor fica
    # a Pedra do Sal, fora da visão, segue da aba
    assert [x for x in junta if E.chave_efetiva(x) == "Pedra do Sal"] == [x for x in ABA if E.chave_efetiva(x) == "Pedra do Sal"]


def test_a_comparacao_aponta_cada_diferenca(cfg, banco):
    ids, _r = _igual_a_aba(cfg, banco)
    u = _editor(cfg, banco, 1)
    p = _payload_de(u)
    p["inversores"][0]["strings_esperadas_qtd"] = 22                  # Inversor 1.1: 20 na aba
    p["inversores"] = [i for i in p["inversores"] if i["nome"] != "Inversor 2.2"]
    p["chaves"][1]["usina_exibicao"] = "Brodowski Norte"
    E.salvar_usina(1, p, E.selo(u), cfg, BASE, banco, info=INFO)
    cmp = E.comparar_usina(_editor(cfg, banco, 1), INFO[1], E.agrupar_aba(ABA))
    c90, c91 = cmp[ids[1]], cmp[ids[2]]
    assert not c90["iguais"] and "INVERSOR01: strings: 20 na aba, 22 no Nexus." in c90["dif"]
    assert "Nome de exibição: “Brodowski” na aba, “Brodowski Norte” no Nexus." in c90["dif"]
    assert "INVERSOR02 (Inversor 2.2) está na aba e não no Nexus." in c91["dif"]
    # a chave da usina também acusa: a UFV conta os inversores da usina inteira
    assert cmp[ids[0]]["dif"] == ["Inversores da usina: 4 na aba, 3 no Nexus."]
    fora = E.comparar_chave(None, [])
    assert not fora["na_aba"] and "não está na aba" in fora["dif"][0]


def test_a_chave_da_usina_uma_so_e_desligar_passa_para_outra(cfg, banco):
    ids, _r = _igual_a_aba(cfg, banco)
    u = _editor(cfg, banco, 1)
    p = _payload_de(u)
    for c in p["chaves"]:
        c["principal"] = True
    with pytest.raises(E.Recusada, match="Só uma chave"):
        E.salvar_usina(1, p, E.selo(u), cfg, BASE, banco, info=INFO)
    p = _payload_de(u)
    for c in p["chaves"]:
        c["principal"] = c["supervisorio_id"] == ids[2]
    E.salvar_usina(1, p, E.selo(u), cfg, BASE, banco, info=INFO)
    u = _editor(cfg, banco, 1)
    assert {s["supervisorio_id"]: s["principal"] for s in u["supervisorios"]} == {ids[0]: False, ids[1]: False, ids[2]: True}
    r = E.desligar_supervisorio(ids[2], 1, cfg, BASE, banco, info=INFO)
    assert r["nova_principal"] == "Brodowski"                     # a 1ª das que ficam, pelo nome
    # a visão acompanhou: a chave desligada saiu, e a UFV voltou para a "Brodowski"
    visao = banco.linhas(E.LIVRO, E.ABA_VISAO)
    assert "Brodowski 2 (91)" not in {E.chave_efetiva(x) for x in visao}
    assert next(x for x in visao if x["Equipamento"] == "UFV")["supervisorio_id"] == ids[0]


def test_a_visao_so_e_regravada_quando_muda(cfg, banco):
    _igual_a_aba(cfg, banco)
    antes = banco.syncs
    r = E.republicar_visao(cfg, BASE, banco, INFO)
    assert not r["visao_mudou"] and banco.syncs == antes           # nada mudou: não grava
    r = E.republicar_visao(cfg, BASE, banco, {1: dict(INFO[1], kwp=1100.0)})
    assert r["visao_mudou"] and banco.syncs == antes + 1           # a potência do Registro mestre mudou
    assert next(x for x in banco.linhas(E.LIVRO, E.ABA_VISAO) if x["Equipamento"] == "UFV")["Potência (kWp)"] == 1100


def test_a_tela_mostra_a_comparacao_e_o_salvar_devolve_a_nova(cli, banco):
    cli.post("/t/base/equipamentos/chave", data={"usina": 1, "acao": "ligar", "chave": "Brodowski 1 (90)"})
    html = cli.get("/t/base/equipamentos?usina=1").get_data(as_text=True)
    dados = json.loads(html.split('id="eq-dados">')[1].split("</script>")[0])
    ch = dados["chaves"][0]
    # a chave nasce com o nome de exibição da aba, como a da usina e fora do lugar da aba
    assert (ch["usina_exibicao"], ch["principal"], ch["substitui_aba"]) == ("Brodowski", True, False)
    cmp = dados["comparacao"][str(ch["supervisorio_id"])]
    assert cmp["na_aba"] and not cmp["iguais"]                    # nada montado ainda: os 2 inversores da aba faltam
    corpo = {"usina_id": 1, "selo": dados["selo"],
             "chaves": [dict(ch, substitui_aba=True, full_om=True)],
             "cabines": [{"k": "n1", "nome": "UG 01", "potencia_kwp": 500}],
             "inversores": [{"nome": f"Inversor 1.{n}", "chave": ch["supervisorio_id"], "cabine": "n1",
                             "equipamento_supervisorio": f"INVERSOR0{n}", "potencia_kwp": 250, "strings_esperadas_qtd": 20}
                            for n in (1, 2)]}
    j = cli.post("/t/base/equipamentos/salvar", json=corpo, headers=JSON_).get_json()
    assert j["ok"] and "visão no formato da aba foi refeita" in j["aviso"]
    c = j["comparacao"][str(ch["supervisorio_id"])]
    assert any("linha da usina" in t for t in c["dif"])           # a UFV fica na "Brodowski" na aba
    assert not any("INVERSOR0" in t for t in c["dif"])              # os dois inversores agora batem
    assert len(banco.linhas(E.LIVRO, E.ABA_VISAO)) == 4             # UFV, UG 01 e os 2 inversores
    html = cli.get("/t/base/equipamentos?usina=1").get_data(as_text=True)
    assert "no lugar da aba" in html and "Refazer a visão" in html
    r = cli.post("/t/base/equipamentos/visao", data={"usina": 1})
    assert "já estava em dia" in cli.get(r.headers["Location"]).get_data(as_text=True)

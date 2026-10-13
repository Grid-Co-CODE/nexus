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
    assert r == {"supervisorio_id": 1, "novo": True, "log": "ligou a chave Brodowski 1 (90) à usina 1"}
    assert E.ligar_supervisorio(1, "Brodowski 1 (90)", cfg, BASE, banco)["novo"] is False      # já estava
    with pytest.raises(E.Recusada, match="já está ligada a outra usina"):
        E.ligar_supervisorio(2, "Brodowski 1 (90)", cfg, BASE, banco)
    with pytest.raises(E.Recusada, match="não está ligada a esta usina"):
        E.desligar_supervisorio(1, 2, cfg, BASE, banco)                       # a chave é da usina 1
    assert E.desligar_supervisorio(1, 1, cfg, BASE, banco)["inversores_sem_chave"] == 0
    assert E.ligar_supervisorio(2, "Brodowski 1 (90)", cfg, BASE, banco)["supervisorio_id"] == 2   # o 1 não volta
    sup = _estado(banco)["sup"]
    assert [(x["supervisorio_id"], x["usina_id"], x["excluido"]) for x in sup] == [(1, 1, "sim"), (2, 2, None)]
    assert list(sup[0]) == list(E.CAB_SUP) and sup[0]["full_om"] == 0


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
    dados = {"chaves": [{"supervisorio_id": s1, "full_om": True, "string_box": False}],
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
    ed = {"chaves": [{"supervisorio_id": s["supervisorio_id"], "full_om": s["full_om"], "string_box": s["string_box"]}
                     for s in u["supervisorios"]],
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


def test_a_tela_mostra_a_lista_e_os_tres_passos_sem_ligar_nada_sozinha(cli, banco):
    html = cli.get("/t/base/equipamentos").get_data(as_text=True)
    assert "Equipamentos das usinas" in html and "Como funciona" in html and "Matões 100" in html
    assert "sem Fracttal" in html                                  # a Matões 100 não tem nome do Fracttal
    html = cli.get("/t/base/equipamentos?usina=1").get_data(as_text=True)
    for passo in ('id="passo-fracttal"', 'id="passo-chave"', 'id="passo-estrutura"', 'id="eq-dados"'):
        assert passo in html
    assert "Thopen - Brodowski 1 - SP" in html and "ligado por código" in html      # o Fracttal pelo código
    # as chaves da aba com motivo vêm primeiro, com o porquê, e nenhuma vem escolhida
    sugeridas = html.split('label="Com motivo para esta usina"')[1].split("</optgroup>")[0]
    assert "Brodowski 1 (90) — mesmo nome do Fracttal na aba" in sugeridas and " selected" not in sugeridas
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
    assert livro.abas == (E.ABA_SUP, E.ABA_CAB, E.ABA_INV) and livro.no_banco is False
    from nexus.torres.base import TORRE
    assert "equipamentos" in [t.id for t in TORRE.telas]

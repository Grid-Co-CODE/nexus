"""Atualizar o Registro mestre pelo CSV do BD_Operações novo (15/10/2026).

Levi, 15/10/2026: "Esse é o novo BD_Operações, conseguimos atualizar os dados do Nexus com esse CSV? daqui a duas semanas
vamos ter acesso em tempo real a esses dados". Decisões dele: a equipe é a do CSV ("Trocar pela do CSV", a nova é criada),
célula vazia não apaga ("Manter o do Nexus"), status novo entra na lista ("Aplicar os novos"). Os casos de cada regra
vieram do arquivo real de 15/10 (258 usinas): arredondamento (7,0488 × 7,049), o "CÓDIGO" da Matões 100, "23.1" × "23,1",
nome completo no CSV e curto no cadastro ("Fulana Rodrigues Prado" × "Fulana Prado"), dois modelos de inversor
que viram um.
"""
import re

import pytest

from nexus import create_app
from nexus.cadastro import importar_csv as ic
from nexus.cadastro.cifra import gerar_chave
from nexus.cadastro.servico import Carga

from conftest import SENHA_TESTE

CAB = ("ID da usina;Nome;Código;Status;Potência real (MWp);Região;Cidade;Equipe;Responsável O&M;Cliente;"
       "Modelo do inversor;Tensão de linha;Latitude;Receita mensal (R$);Endereço;Mobilizado?")
LINHAS = [
    # arredondado, região só com hífen, cidade vazia, equipe nova, pessoa pelo nome contido, inversor resumido,
    # o mesmo número com vírgula, a mesma coordenada
    "UFV-001;Brodowski;BRD-001;OPERAÇÃO;7,049;Centro Oeste;;Brumado / Tanhaçu;Fulana Rodrigues Prado;Thopen;"
    "SUN2000-250KTL-H1;23,1;-9,8712;;;Sim",
    # o código de mentira, status novo, cidade que o Nexus não tinha, equipe que existe, pessoa e cliente sem par, a
    # receita igual à conta automática, endereço (sensível)
    "UFV-002;Matões 100;CÓDIGO;PRONTA PARA MOBILIZAR;;Sudeste;Matões;sp leste 01;Fulano Desconhecido;Cliente Novo;"
    ";;;2.500,00;Rua Teste 123;Não",
    "UFV-999;Usina que não existe;;OPERAÇÃO;;;;;;;;;;;;",
    "UFV-001;Brodowski repetida;;;;;;;;;;;;;;",                          # a segunda linha do mesmo ID não conta
]


def _csv(linhas=None, cab=CAB) -> bytes:
    return ("﻿" + "\n".join([cab] + (LINHAS if linhas is None else linhas)) + "\n").encode("utf-8")


@pytest.fixture
def app_csv(tmp_path):
    app = create_app({"NEXUS_SECRET_KEY": "chave-de-teste", "NEXUS_SENHA_ADMIN": SENHA_TESTE,
                      "NEXUS_CHAVE_CADASTRO": gerar_chave(), "NEXUS_ARMAZEM_LOCAL": str(tmp_path / "cadastro.json")})
    app.config["TESTING"] = True
    app.config["SESSION_COOKIE_SECURE"] = False
    from nexus.cadastro.telas import servico
    with app.app_context():
        servico().aplicar_carga(Carga(
            entidades={
                "equipes": [{"id": "1", "ordem": 1, "valores": {"nome": "SP Leste 01"}},
                            {"id": "2", "ordem": 2, "valores": {"nome": "BATANHA01"}}],
                "pessoas": [
                    {"id": "1", "ordem": 1, "valores": {"nome": "Fulana Prado", "vinculo": "Supervisor"}},
                    {"id": "2", "ordem": 2, "valores": {"nome": "Ana Maria Lima", "vinculo": "Colaborador de campo"}},
                    {"id": "3", "ordem": 3, "valores": {"nome": "Ciclano Araújo", "vinculo": "Supervisor"}},
                    {"id": "4", "ordem": 4, "valores": {"nome": "Ciclano Henrique De Paula",
                                                        "vinculo": "Colaborador de campo"}}],
                "clientes": [{"id": "1", "ordem": 1, "valores": {"nome": "Thopen"}}],
                "usinas": [
                    {"id": "1", "ordem": 1, "valores": {
                        "nome": "Brodowski", "codigo": "BRD-001", "id_bd": "UFV-001", "status": "OPERAÇÃO",
                        "potencia_real": 7.0488, "regiao": "Centro-Oeste", "cidade": "Brodowski", "uf": "SP",
                        "equipe": "2", "responsavel_om": "2", "cliente": "1", "tensao_linha": "23.1",
                        "modelo_inversores": "SUN2000-250KTL-H1 + SUN2000-330KTL-H1", "latitude": -9.8712}},
                    {"id": "2", "ordem": 2, "valores": {
                        "nome": "Matões 100", "codigo": "MAB100", "id_bd": "UFV-002", "status": "A MOBILIZAR",
                        "regiao": "Sudeste", "equipe": "2", "cliente": "1", "preco_mwp": 1000.0,
                        "potencia_contratual": 2.5}}],
            },
            listas={"status_usina": ["OPERAÇÃO", "A MOBILIZAR"], "uf": ["SP"], "regiao": ["Centro-Oeste", "Sudeste"],
                    "vinculo": ["Colaborador de campo", "Supervisor"]},
        ))
    return app


@pytest.fixture
def srv(app_csv):
    from nexus.cadastro.telas import servico
    with app_csv.app_context():
        yield servico()


@pytest.fixture
def cli(app_csv):
    c = app_csv.test_client()
    assert c.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    return c


def _prop(srv, dados=None):
    cab, linhas = ic.ler_csv(dados or _csv())
    return ic.proposta(linhas, srv, cab)


def _campos(p):
    return {pc["campo"]: {ln["id_bd"]: ln for ln in pc["linhas"]} for pc in p["por_campo"]}


def test_a_previa_segue_as_regras_e_nao_grava(srv):
    antes = srv.registro("usinas", "1").versao
    p = _prop(srv)
    c = _campos(p)
    assert p["total"] == 3 and p["sem_par"] == [{"id_bd": "UFV-999", "nome": "Usina que não existe"}]
    # o que muda
    assert set(c) == {"status", "cidade", "modelo_inversores", "equipe", "responsavel_om", "endereco"}
    assert c["status"]["UFV-002"]["depois"] == "PRONTA PARA MOBILIZAR"
    assert c["cidade"]["UFV-002"]["antes"] == "" and c["cidade"]["UFV-002"]["depois"] == "Matões"
    assert c["modelo_inversores"]["UFV-001"]["resume"] is True            # dois modelos viram um: marcado
    assert c["equipe"]["UFV-001"]["depois"] == "Brumado / Tanhaçu" and c["equipe"]["UFV-001"]["nota"] == "equipe nova"
    assert c["equipe"]["UFV-002"]["depois"] == "sp leste 01"                # casou sem maiúscula: a SP Leste 01
    assert c["responsavel_om"]["UFV-001"]["depois"] == "Fulana Prado"
    assert c["responsavel_om"]["UFV-001"]["nota"] == "no CSV: Fulana Rodrigues Prado"
    # o responsável que não tem ficha ganha uma (Levi, 16/10: "não quero que siga com os dados antigos")
    assert c["responsavel_om"]["UFV-002"]["depois"] == "Fulano Desconhecido"
    assert c["responsavel_om"]["UFV-002"]["nota"] == "ficha nova"
    nova = next(m for m in p["pessoas"] if m["acao"] == "criar")
    assert nova["formulario"] == {"nome": "Fulano Desconhecido", "vinculo": "Supervisor de Campo", "status": "Ativo"}
    # o que fica, e por quê
    # 7,049 × 7,0488 é arredondamento; a latitude igual e a receita igual à conta automática não contam
    assert p["arredondados"] == {"Potência real (MWp)": 1}
    assert p["vazios"] == {"Cidade": 1}
    assert p["ignorados"] == {'Código (o valor de mentira "CÓDIGO")': 1}
    assert p["sem_pessoa"] == {} and p["sem_cliente"] == {"Cliente Novo": 1}
    assert p["novos_valores"] == {"status_usina": ["PRONTA PARA MOBILIZAR"], "vinculo": ["Supervisor de Campo"],
                                  "status_contratacao": ["Ativo"]}
    assert p["equipes_novas"] == ["Brumado / Tanhaçu"] and p["sem_campo"] == ["Mobilizado?"]
    # região "Centro Oeste" × "Centro-Oeste", tensão "23,1" × "23.1" e a mesma latitude: nada muda
    assert "regiao" not in c and "tensao_linha" not in c and "latitude" not in c
    assert srv.registro("usinas", "1").versao == antes                     # a prévia não grava


def test_aplicar_grava_pela_ficha_e_a_segunda_previa_fica_vazia(srv):
    p = _prop(srv)
    res = ic.aplicar(p, srv, "teste")
    assert res["atualizadas"] == 2 and res["equipes_criadas"] == 1 and res["conflitos"] == [] and res["erros"] == []
    assert sorted(res["valores_incluidos"]) == ["Ativo", "PRONTA PARA MOBILIZAR", "Supervisor de Campo"]
    assert res["pessoas_criadas"] == 1
    u1, u2 = srv.registro("usinas", "1").valores, srv.registro("usinas", "2").valores
    nova = next(r for r in srv.registros("equipes") if r.valores["nome"] == "Brumado / Tanhaçu")
    assert u1["equipe"] == nova.id and u1["responsavel_om"] == "1"
    assert u1["potencia_real"] == 7.0488 and u1["cidade"] == "Brodowski"   # o mais preciso e o vazio ficam
    assert u1["modelo_inversores"] == "SUN2000-250KTL-H1" and u1["tensao_linha"] == "23.1"
    assert u2["status"] == "PRONTA PARA MOBILIZAR" and u2["codigo"] == "MAB100" and u2["equipe"] == "1"
    assert u2["cidade"] == "Matões" and u2["cliente"] == "1" and u2["endereco"] == "Rua Teste 123"
    assert srv.titulo_de("pessoas", u2["responsavel_om"]) == "Fulano Desconhecido"
    assert u2.get("receita_mensal") is None                                 # a conta igual não congela o automático
    assert "PRONTA PARA MOBILIZAR" in srv.listas()["status_usina"]
    assert srv.registro("usinas", "2").versao == 2                          # pela ficha: versão nova
    acoes = [a["acao"] for a in srv.auditoria(20)]
    assert "atualizou pelo CSV do BD_Operações" in acoes and "alterou" in acoes
    p2 = _prop(srv)
    assert p2["mudancas"] == [] and p2["por_campo"] == [] and p2["equipes_novas"] == [] and p2["pessoas"] == []


def test_so_as_colunas_marcadas_sao_gravadas(srv):
    res = ic.aplicar(_prop(srv), srv, "teste", ["status"])
    assert res["atualizadas"] == 1 and res["equipes_criadas"] == 0
    u1, u2 = srv.registro("usinas", "1").valores, srv.registro("usinas", "2").valores
    assert u2["status"] == "PRONTA PARA MOBILIZAR" and u2["equipe"] == "2" and u2.get("cidade") is None
    assert u1["equipe"] == "2" and u1["responsavel_om"] == "2"
    assert all(r.valores["nome"] != "Brumado / Tanhaçu" for r in srv.registros("equipes"))


def test_quem_salvou_a_ficha_depois_da_previa_ganha(srv):
    p = _prop(srv)
    r = srv.registro("usinas", "1")
    assert srv.salvar("usinas", "1", {"nome_spe": "SPE Teste"}, r.versao, "outra pessoa").ok
    res = ic.aplicar(p, srv, "teste")
    assert res["conflitos"] == [{"id_bd": "UFV-001", "nome": "Brodowski"}] and res["atualizadas"] == 1
    assert srv.registro("usinas", "1").valores["nome_spe"] == "SPE Teste"
    assert srv.registro("usinas", "1").valores["equipe"] == "2"


def test_pessoa_pelo_nome_contido_so_quando_uma_serve():
    pes = [("1", [ic._nomes("Fulana Prado")]), ("3", [ic._nomes("Ciclano Araújo")]),
           ("4", [ic._nomes("Ciclano Henrique De Paula")]), ("5", [ic._nomes("Ana Maria Lima")]),
           ("6", [ic._nomes("Ana Paula Lima")])]
    assert ic._achar_pessoa("Fulana Rodrigues Prado", pes) == "1"
    assert ic._achar_pessoa("Ciclano Araújo Rocha", pes) == "3"
    assert ic._achar_pessoa("CICLANO ARAUJO", pes) == "3"                   # sem acento e sem maiúscula
    assert ic._achar_pessoa("Ana Lima", pes) is None                         # duas Anas Lima: não adivinha
    assert ic._achar_pessoa("Daniel", pes) is None                           # um nome só não basta
    assert ic._achar_pessoa("Beltrano Nunes", pes) is None


def test_o_csv_resume_e_o_mesmo_numero():
    assert ic._resume("SUN2000-250KTL-H1 + SUN2000-330KTL-H1", "SUN2000-250KTL-H1")
    assert ic._resume("250 kW / 275 kVA", "250") and ic._resume("2 unidades (3000 kVA cada)", "2")
    assert not ic._resume("575 Wp", "575")                                   # só a unidade: não é resumo
    assert not ic._resume("1250", "250") and not ic._resume("STI", "Array Technologies (STI Norland)")
    assert ic._mesmo_numero("23.1", "23,1") and not ic._mesmo_numero("300", "330")


def test_ler_csv_aceita_cp1252_e_virgula():
    cab, linhas = ic.ler_csv("ID da usina,Região\nUFV-001,Nordeste\n".encode("cp1252"))
    assert cab == ["ID da usina", "Região"] and linhas == [{"ID da usina": "UFV-001", "Região": "Nordeste"}]
    cab, _ = ic.ler_csv(b"ID da usina;Nome\n\x81\x8d;x\n")                  # byte que nem o cp1252 lê: não quebra
    assert cab == ["ID da usina", "Nome"]


def test_a_tela_mostra_a_previa_e_aplica_uma_vez(cli):
    html = cli.get("/t/base/registro-mestre").get_data(as_text=True)
    assert "/t/base/registro-mestre/atualizar" in html and "Atualizar pelo CSV" in html
    assert "Ver o que muda" in cli.get("/t/base/registro-mestre/atualizar").get_data(as_text=True)
    r = cli.post("/t/base/registro-mestre/atualizar", data={"arquivo": (__import__("io").BytesIO(_csv()), "bd.csv")},
                 content_type="multipart/form-data")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Prévia da atualização" in html and "o CSV resume" in html
    assert '<span class="csv-nota">equipe nova</span>' in html and "Fulano Desconhecido" in html and "Mobilizado?" in html
    assert "UFV-999" in html and "PRONTA PARA MOBILIZAR" in html
    assert "Rua Teste 123" not in html and "•••" in html                     # sensível mascarado
    token = re.search(r'name="token" value="([^"]+)"', html).group(1)
    campos = re.findall(r'name="campos" value="([^"]+)"', html)
    r = cli.post("/t/base/registro-mestre/atualizar/aplicar", data={"token": token, "campos": campos})
    assert r.status_code == 303 and "/t/base/registro-mestre/atualizar?feito=" in r.headers["Location"]
    html = cli.get(r.headers["Location"]).get_data(as_text=True)
    assert "2 usina(s) atualizada(s)" in html and "1 equipe(s) nova(s)" in html
    r = cli.post("/t/base/registro-mestre/atualizar/aplicar", data={"token": token, "campos": campos})
    assert r.status_code == 410 and "nada foi gravado" in r.get_data(as_text=True)


def test_a_tela_recusa_o_que_nao_e_o_csv_e_o_pedido_de_fora(cli, srv):
    io_ = __import__("io")
    r = cli.post("/t/base/registro-mestre/atualizar", data={"arquivo": (io_.BytesIO(b"x"), "bd.xlsx")},
                 content_type="multipart/form-data")
    assert r.status_code == 400
    r = cli.post("/t/base/registro-mestre/atualizar", data={"arquivo": (io_.BytesIO(b"Nome;UF\nA;SP\n"), "bd.csv")},
                 content_type="multipart/form-data")
    assert r.status_code == 400 and "ID da usina" in r.get_data(as_text=True)
    r = cli.post("/t/base/registro-mestre/atualizar", data={"arquivo": (io_.BytesIO(_csv()), "bd.csv")},
                 content_type="multipart/form-data", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    r = cli.post("/t/base/registro-mestre/atualizar", data={"arquivo": (io_.BytesIO(_csv()), "bd.csv")},
                 content_type="multipart/form-data")
    token = re.search(r'name="token" value="([^"]+)"', r.get_data(as_text=True)).group(1)
    # nenhuma coluna marcada: nada grava e a prévia continua valendo
    r = cli.post("/t/base/registro-mestre/atualizar/aplicar", data={"token": token})
    assert r.status_code == 400 and "Marque ao menos uma coluna" in r.get_data(as_text=True)
    r = cli.post("/t/base/registro-mestre/atualizar/aplicar", data={"token": token, "campos": ["status"]},
                 headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    assert srv.registro("usinas", "2").valores["status"] == "A MOBILIZAR"
    r = cli.post("/t/base/registro-mestre/atualizar/aplicar", data={"token": token, "campos": ["status"]})
    assert r.status_code == 303 and srv.registro("usinas", "2").valores["status"] == "PRONTA PARA MOBILIZAR"


def test_so_admin_e_com_login(app_csv):
    c = app_csv.test_client()
    assert c.get("/t/base/registro-mestre/atualizar").status_code == 302
    with c.session_transaction() as s:
        s["logado"] = True
        s["usuario"] = {"email": "pessoa@exemplo.test", "nome": "Pessoa Exemplo", "perfil": ""}
        s["admin"] = False
    assert c.get("/t/base/registro-mestre/atualizar").status_code == 403
    assert c.post("/t/base/registro-mestre/atualizar/aplicar", data={"token": "x"}).status_code == 403


# ── "Pessoas da equipe" (16/10/2026, Levi: "procure esses 5 no fractall, faça a relação e adicione no Nexus, não podemos
# ficar sem informação! Se adapte"): os casos reais com nomes fictícios. A grafia do CSV difere da ficha ("Samiel" ×
# "Samuel", "das Neves" × "Dasneves") e o nome padrão calculado resolve; quem falta nasce com o e-mail da conta do
# Fracttal; quem atende duas equipes fica; desligado sem ficha não entra; a conta do Fracttal acha a ficha de outro nome.
CAB_P = "ID da usina;Nome;Equipe;Pessoas da equipe"
LINHAS_P = [
    "UFV-001;Brodowski;Equipe Nova Teste;Renato Samiel Lopes Andrade (Mantenedor), Teodoro Mendes Paiva (Eletricista), "
    "Silvio Prates Leme (Eletricista · Desligado), Marcelo Fonte Rios (Técnico de O&M)",
    "UFV-002;Matões 100;sp leste 01;Otavio Vitor das Neves Ramos (Mantenedor), Marcelo Fonte Rios (Técnico de O&M), "
    "Fulano Real Silva (Técnico de O&M)",
]
FRACTTAL = [{"nome": "Teodoro Mendes Paiva", "email": "teodoro.paiva@exemplo.test", "conta_ativa": True},
            {"nome": "Fulano Real Silva", "email": "fulano.real@exemplo.test", "conta_ativa": True},
            {"nome": "Outra Pessoa", "email": "outra@exemplo.test", "conta_ativa": True}]


@pytest.fixture
def srv_p(app_csv):
    from nexus.cadastro.telas import servico
    with app_csv.app_context():
        s = servico()
        for lista, vals in (("cargos", ("Técnico O&M", "Eletricista O&M", "Mantenedor O&M")),
                            ("status_contratacao", ("Ativo", "Desligado"))):
            for v in vals:
                assert s.adicionar_valor(lista, v, "teste").ok
        for f in ({"nome": "Renato Samuel Lopes Andrade", "vinculo": "Colaborador de campo", "equipe": "2"},
                  {"nome": "Otavio Vitor Dasneves Ramos", "vinculo": "Colaborador de campo", "cargo": "Mantenedor O&M",
                   "status": "Ativo", "equipe": "1"},
                  {"nome": "Marcelo Fonte Rios", "vinculo": "Colaborador de campo", "cargo": "Técnico O&M",
                   "status": "Ativo", "equipe": "1"},
                  {"nome": "Fulano de Tal", "vinculo": "Colaborador de campo", "email": "fulano.real@exemplo.test",
                   "equipe": "2"}):
            assert s.criar("pessoas", f, "teste").ok
        yield s


def _por_nome(srv, nome):
    return next(r for r in srv.registros("pessoas") if r.valores.get("nome") == nome)


def test_pessoas_da_celula_le_nome_cargo_e_desligado():
    assert ic.pessoas_da_celula("Ana Lima (Técnico de O&M), Bia Souza (Eletricista · Desligado), "
                                "Caio da Silva e Silva (Man), Duda Reis") == [
        ("Ana Lima", "Técnico O&M", False), ("Bia Souza", "Eletricista O&M", True),
        ("Caio da Silva e Silva", "Mantenedor O&M", False), ("Duda Reis", None, False)]


def test_a_previa_das_pessoas(srv_p):
    cab, linhas = ic.ler_csv(_csv(LINHAS_P, CAB_P))
    p = ic.proposta(linhas, srv_p, cab, FRACTTAL)
    por = {m["nome"]: m for m in p["pessoas"]}
    renato = por["Renato Andrade"]                  # a ficha "Renato Samuel...": casou pelo nome padrão
    assert renato["acao"] == "completar" and renato["formulario"] == {
        "equipe": "nova:Equipe Nova Teste", "cargo": "Mantenedor O&M", "status": "Ativo"}
    teo = por["Teodoro Mendes Paiva"]               # sem ficha: nasce com o e-mail da conta do Fracttal
    assert teo["acao"] == "criar" and teo["formulario"] == {
        "nome": "Teodoro Mendes Paiva", "vinculo": "Colaborador de campo", "status": "Ativo", "cargo": "Eletricista O&M",
        "equipe": "nova:Equipe Nova Teste", "email": "teodoro.paiva@exemplo.test"}
    fulano = por["Fulano Tal"]                      # o nome do CSV não casa; a conta do Fracttal acha a ficha pelo e-mail
    assert fulano["acao"] == "completar" and fulano["formulario"] == {"equipe": "1", "cargo": "Técnico O&M",
                                                                       "status": "Ativo"}
    assert "Otavio Ramos" not in por                # "das Neves" × "Dasneves": casou e não falta nada
    assert p["pessoas_desligadas_sem_ficha"] == ["Silvio Prates Leme"]
    # o técnico, o eletricista e o mantenedor vão para a usina; quem atende duas equipes aparece nas duas
    c = _campos(p)
    marcelo, renato_id = _por_nome(srv_p, "Marcelo Fonte Rios").id, _por_nome(srv_p, "Renato Samuel Lopes Andrade").id
    assert c["tecnico_om"]["UFV-001"]["depois"] == c["tecnico_om"]["UFV-002"]["depois"] == "Marcelo Rios"
    usina = {m["id_bd"]: m["formulario"] for m in p["mudancas"]}
    assert usina["UFV-001"]["tecnico_om"] == usina["UFV-002"]["tecnico_om"] == marcelo
    assert usina["UFV-001"]["mantenedor_om"] == renato_id
    assert usina["UFV-001"]["eletricista_om"] == "nova-pessoa:teodoro mendes paiva"
    assert usina["UFV-002"]["mantenedor_om"] == _por_nome(srv_p, "Otavio Vitor Dasneves Ramos").id
    assert "Pessoas da equipe" not in p["sem_campo"]


def test_aplicar_cria_e_completa_e_a_segunda_previa_fica_vazia(srv_p):
    cab, linhas = ic.ler_csv(_csv(LINHAS_P, CAB_P))
    res = ic.aplicar(ic.proposta(linhas, srv_p, cab, FRACTTAL), srv_p, "teste")
    assert res["pessoas_criadas"] == 1 and res["pessoas_completadas"] == 2 and res["erros"] == []
    nova = next(r for r in srv_p.registros("equipes") if r.valores["nome"] == "Equipe Nova Teste")
    teo = _por_nome(srv_p, "Teodoro Mendes Paiva").valores
    assert teo["email"] == "teodoro.paiva@exemplo.test" and teo["equipe"] == nova.id and teo["cargo"] == "Eletricista O&M"
    renato = _por_nome(srv_p, "Renato Samuel Lopes Andrade").valores
    assert renato["equipe"] == nova.id and renato["cargo"] == "Mantenedor O&M" and renato["status"] == "Ativo"
    assert _por_nome(srv_p, "Marcelo Fonte Rios").valores["equipe"] == "1"       # atende duas: a ficha fica
    u1 = next(r for r in srv_p.registros("usinas") if r.valores.get("id_bd") == "UFV-001")
    assert u1.valores["eletricista_om"] == _por_nome(srv_p, "Teodoro Mendes Paiva").id   # a ficha nova, na usina
    assert u1.valores["tecnico_om"] == _por_nome(srv_p, "Marcelo Fonte Rios").id
    assert not any(r.valores.get("nome") == "Silvio Prates Leme" for r in srv_p.registros("pessoas"))
    p2 = ic.proposta(linhas, srv_p, cab, FRACTTAL)
    assert p2["pessoas"] == []


def test_sem_o_fracttal_a_ficha_nasce_sem_email_e_desmarcar_pessoas_nao_grava(srv_p):
    cab, linhas = ic.ler_csv(_csv(LINHAS_P, CAB_P))
    p = ic.proposta(linhas, srv_p, cab, [])
    assert "email" not in next(m for m in p["pessoas"] if m["acao"] == "criar")["formulario"]
    res = ic.aplicar(p, srv_p, "teste", ["equipe"])
    assert res["pessoas_criadas"] == 0 and res["pessoas_completadas"] == 0
    assert not _por_nome(srv_p, "Renato Samuel Lopes Andrade").valores.get("cargo")


def test_a_tela_mostra_e_aplica_as_pessoas(cli, srv_p, monkeypatch):
    from nexus.cadastro import telas
    monkeypatch.setattr(telas, "_pessoal_fracttal", lambda: FRACTTAL)
    r = cli.post("/t/base/registro-mestre/atualizar", data={"arquivo": (__import__("io").BytesIO(_csv(LINHAS_P, CAB_P)),
                                                                        "bd.csv")}, content_type="multipart/form-data")
    html = r.get_data(as_text=True)
    assert "Fichas das pessoas do CSV" in html and "1 ficha nova" in html and "e-mail do Fracttal" in html
    assert "Técnico O&amp;M (Pessoas da equipe)" in html
    assert "teodoro.paiva@exemplo.test" not in html                  # o e-mail não aparece na prévia
    assert "Silvio Prates Leme" in html
    token = re.search(r'name="token" value="([^"]+)"', html).group(1)
    campos = re.findall(r'name="campos" value="([^"]+)"', html)
    assert "pessoas" in campos
    r = cli.post("/t/base/registro-mestre/atualizar/aplicar", data={"token": token, "campos": campos})
    html = cli.get(r.headers["Location"]).get_data(as_text=True)
    assert "1 pessoa(s) nova(s) em Colaboradores" in html and "2 ficha(s)" in html


def test_o_csv_sem_tecnico_deixa_a_usina_sem_tecnico(srv_p):
    """A equipe do CSV sem técnico: a usina fica sem ("-"), não herda o técnico fixado no BD antigo nem o da equipe."""
    u = next(r for r in srv_p.registros("usinas") if r.valores.get("id_bd") == "UFV-002")
    assert srv_p.salvar("usinas", u.id, {"tecnico_om": _por_nome(srv_p, "Marcelo Fonte Rios").id}, u.versao, "t").ok
    cab, linhas = ic.ler_csv(_csv(["UFV-002;Matões 100;sp leste 01;Otavio Vitor das Neves Ramos (Mantenedor)"], CAB_P))
    p = ic.proposta(linhas, srv_p, cab, [])
    c = _campos(p)
    assert c["tecnico_om"]["UFV-002"]["antes"] == "Marcelo Rios" and c["tecnico_om"]["UFV-002"]["depois"] == "—"
    ic.aplicar(p, srv_p, "teste")
    u = srv_p.registro("usinas", u.id)
    assert u.valores["tecnico_om"] == "-" and u.valor("tecnico_om") == "-"
    assert ic.proposta(linhas, srv_p, cab, [])["mudancas"] == []           # de novo: nada


def test_responsavel_sem_ficha_nasce_supervisor_com_o_email_do_fracttal(srv_p):
    cab, linhas = ic.ler_csv(_csv(["UFV-002;Matões 100;Dalton Ferraz Neto"], "ID da usina;Nome;Responsável O&M"))
    conta = [{"nome": "Dalton Ferraz Neto", "email": "dalton.neto@exemplo.test", "conta_ativa": True}]
    p = ic.proposta(linhas, srv_p, cab, conta)
    nova = next(m for m in p["pessoas"] if m["acao"] == "criar")
    assert nova["formulario"] == {"nome": "Dalton Ferraz Neto", "vinculo": "Supervisor de Campo", "status": "Ativo",
                                  "email": "dalton.neto@exemplo.test"}
    ic.aplicar(p, srv_p, "teste")
    u = next(r for r in srv_p.registros("usinas") if r.valores.get("id_bd") == "UFV-002")
    assert srv_p.titulo_de("pessoas", u.valores["responsavel_om"]) == "Dalton Neto"


def test_nome_de_duas_fichas_nao_liga_nem_cria(srv_p):
    for nome in ("Beto Lins Costa", "Beto Ramos Costa"):          # os dois têm o nome padrão "Beto Costa"
        assert srv_p.criar("pessoas", {"nome": nome, "vinculo": "Colaborador de campo"}, "t").ok
    cab, linhas = ic.ler_csv(_csv(["UFV-002;Matões 100;sp leste 01;Beto Costa (Técnico de O&M)"], CAB_P))
    p = ic.proposta(linhas, srv_p, cab, [])
    assert p["pessoas_ambiguas"].get("Beto Costa")
    assert not any(m["acao"] == "criar" for m in p["pessoas"])
    assert "tecnico_om" not in {cid for m in p["mudancas"] for cid in m["formulario"]}

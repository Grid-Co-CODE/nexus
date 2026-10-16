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
    # o que fica, e por quê
    # 7,049 × 7,0488 é arredondamento; a latitude igual e a receita igual à conta automática não contam
    assert p["arredondados"] == {"Potência real (MWp)": 1}
    assert p["vazios"] == {"Cidade": 1}
    assert p["ignorados"] == {'Código (o valor de mentira "CÓDIGO")': 1}
    assert p["sem_pessoa"] == {"Fulano Desconhecido": 1} and p["sem_cliente"] == {"Cliente Novo": 1}
    assert p["novos_valores"] == {"status_usina": ["PRONTA PARA MOBILIZAR"]}
    assert p["equipes_novas"] == ["Brumado / Tanhaçu"] and p["sem_campo"] == ["Mobilizado?"]
    # região "Centro Oeste" × "Centro-Oeste", tensão "23,1" × "23.1" e a mesma latitude: nada muda
    assert "regiao" not in c and "tensao_linha" not in c and "latitude" not in c
    assert srv.registro("usinas", "1").versao == antes                     # a prévia não grava


def test_aplicar_grava_pela_ficha_e_a_segunda_previa_fica_vazia(srv):
    p = _prop(srv)
    res = ic.aplicar(p, srv, "teste")
    assert res["atualizadas"] == 2 and res["equipes_criadas"] == 1 and res["conflitos"] == [] and res["erros"] == []
    assert res["valores_incluidos"] == ["PRONTA PARA MOBILIZAR"]
    u1, u2 = srv.registro("usinas", "1").valores, srv.registro("usinas", "2").valores
    nova = next(r for r in srv.registros("equipes") if r.valores["nome"] == "Brumado / Tanhaçu")
    assert u1["equipe"] == nova.id and u1["responsavel_om"] == "1"
    assert u1["potencia_real"] == 7.0488 and u1["cidade"] == "Brodowski"   # o mais preciso e o vazio ficam
    assert u1["modelo_inversores"] == "SUN2000-250KTL-H1" and u1["tensao_linha"] == "23.1"
    assert u2["status"] == "PRONTA PARA MOBILIZAR" and u2["codigo"] == "MAB100" and u2["equipe"] == "1"
    assert u2["cidade"] == "Matões" and u2["cliente"] == "1" and u2["endereco"] == "Rua Teste 123"
    assert u2.get("receita_mensal") is None                                 # a conta igual não congela o automático
    assert "PRONTA PARA MOBILIZAR" in srv.listas()["status_usina"]
    assert srv.registro("usinas", "2").versao == 2                          # pela ficha: versão nova
    acoes = [a["acao"] for a in srv.auditoria(20)]
    assert "atualizou pelo CSV do BD_Operações" in acoes and "alterou" in acoes
    p2 = _prop(srv)
    assert p2["mudancas"] == [] and p2["por_campo"] == [] and p2["equipes_novas"] == []


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

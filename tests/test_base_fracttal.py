"""Base > Integração Fracttal (Levi, 12/10/2026: "Temos a relação do time de campo, precisamos da relação do pessoal do
fractall e também posteriormente vamos precisar relacionar os setores"): o pessoal do Fracttal ao lado do cadastro de
pessoas, pelo critério do login (e-mail da ficha; sem ele, o nome de UMA ficha), e as fichas sem conta no Fracttal. Só
administrador. Nenhum teste vai ao Fracttal: o fornecedor falso do cliente do Campo."""
import pytest
from test_campo_visao import banco  # noqa: F401  (fixture)

from nexus.cadastro import fracttal_pessoal as FP
from nexus.campo import fracttal

PESSOAL = [
    {"id_personnel": 501, "full_name": "Beltrano Supervisor", "email": "beltrano@exemplo.test", "code": "B1",
     "groups_permissions_description": "Administrator", "account_active": True},
    {"id_personnel": 502, "full_name": "Ciclano Chefe", "email": "ciclano.chefe@empresa.test", "code": "",
     "groups_permissions_description": "Leitura", "account_active": True},
    {"id_personnel": 503, "full_name": "Fulana Escritorio", "email": "fulana@empresa.test", "code": "F3",
     "groups_permissions_description": "Administrator", "account_active": True},
    {"id_personnel": 504, "full_name": "Pessoa Sem Conta", "email": "sem.conta@empresa.test", "code": None,
     "groups_permissions_description": None, "account_active": False},
]


@pytest.fixture
def com_fracttal(app):
    pedidos = []

    def fornecedor(path):
        pedidos.append(path)
        return {"data": PESSOAL if path.startswith("personnel") else []}
    fracttal.usar_fornecedor(fornecedor)
    FP._CACHE.clear()
    yield pedidos
    fracttal.usar_fornecedor(None)
    FP._CACHE.clear()


def _ficha(pid, nome, padrao=None, email="", status="Ativo"):
    return {"pessoa_id": pid, "nome": nome, "nome_padrao": padrao or nome, "email": email, "vinculo": "Colaborador de campo",
            "cargo": "", "equipe_id": None, "status": status}


def test_liga_pelo_email_ou_pelo_nome_de_uma_ficha_so():
    pessoal = [FP.da_api(p) for p in PESSOAL]
    fichas = [_ficha(90, "Beltrano Supervisor", email="beltrano@exemplo.test"), _ficha(91, "Ciclano da Silva Chefe"),
              _ficha(5, "Ana Souza"), _ficha(6, "Ana Maria Souza")]
    r = FP.ligar(pessoal + [FP.da_api({"id_personnel": 9, "full_name": "Ana Souza", "email": "ana@x.test"})], fichas)
    por = {x["id"]: x for x in r["linhas"]}
    assert por[501]["ficha"]["pessoa_id"] == 90 and por[501]["por"] == "e-mail"
    assert por[502]["ficha"]["pessoa_id"] == 91 and por[502]["por"] == "nome"     # primeiro e último nome
    assert por[503]["ficha"] is None and not por[503]["ambiguo"]
    assert por[9]["ficha"] is None and por[9]["ambiguo"]                          # "Ana Souza" serve a duas fichas
    assert [f["pessoa_id"] for f in r["sem_conta"]] == [6, 5]                 # pelo nome padrão
    assert (r["ligadas"], r["sem_ficha"], r["ambiguas"]) == (2, 3, 1)


def test_a_mesma_ficha_para_duas_contas_fica_marcada():
    fichas = [_ficha(90, "Beltrano Supervisor", email="beltrano@exemplo.test")]
    duas = [FP.da_api(PESSOAL[0]), FP.da_api({"id_personnel": 600, "full_name": "Beltrano Supervisor",
                                               "email": "outro@empresa.test"})]
    r = FP.ligar(duas, fichas)
    assert all(x["repetida"] for x in r["linhas"]) and r["repetidas"] == 2


def test_acesso_e_conta_do_fracttal():
    assert [FP.da_api(p)["acesso"] for p in PESSOAL] == ["Administrador", "Leitura", "Administrador", "sem acesso"]
    assert [FP.da_api(p)["conta_ativa"] for p in PESSOAL] == [True, True, True, False]
    # a origem pelo domínio do e-mail: a casa é gridco.com.br; cliente com acesso de leitura é externo
    assert FP.da_api({"email": "pessoa@gridco.com.br"})["origem"] == "Grid Co."
    assert FP.da_api({"email": "cliente@cliente.test"})["origem"] == "Externo"


def test_a_tela_mostra_o_pessoal_e_as_fichas_sem_conta(banco, com_fracttal, logado):
    html = logado.get("/t/base/fracttal").get_data(as_text=True)
    assert "Integração Fracttal" in html and "Pessoal do Fracttal" in html
    # 4 no Fracttal; Beltrano pelo e-mail e Ciclano pelo nome (fichas 90 e 91 do banco falso); 2 sem ficha
    assert '<div class="r">No Fracttal</div><div class="v">4</div>' in html
    assert '<div class="r">Com ficha no Nexus</div><div class="v">2</div>' in html
    assert '<div class="r">Sem ficha no Nexus</div><div class="v">2</div>' in html
    assert 'href="/t/pessoas/colaborador/90">Beltrano Supervisor</a>' in html and "pelo e-mail" in html
    assert 'href="/t/pessoas/colaborador/91">Ciclano Chefe</a>' in html and "pelo nome" in html
    # as fichas ativas sem conta no Fracttal: a supervisora e o coordenador de campo
    sem = html[html.index("Fichas do Nexus sem conta no Fracttal"):]
    assert "Supervisora Campo" in sem and "Coordenador Campo" in sem and "Beltrano" not in sem
    assert "a definir" in html                                                   # o setor espera a base
    assert "0 da Grid Co. · 2 externos" in html                                   # Fulana e a sem conta, sem gridco
    so_ext = logado.get("/t/base/fracttal?origem=Externo").get_data(as_text=True)
    assert "Fulana Escritorio" in so_ext
    # filtros e a leitura guardada: a 2ª visita não pede de novo ao Fracttal
    n = len(com_fracttal)
    sem_ficha = logado.get("/t/base/fracttal?ligacao=sem_ficha").get_data(as_text=True)
    assert "Fulana Escritorio" in sem_ficha and "Beltrano" not in sem_ficha.split("Fichas do Nexus")[0]
    assert len(com_fracttal) == n
    logado.get("/t/base/fracttal?reler=1")
    assert len(com_fracttal) == n + 1


def test_so_administrador(app, banco, com_fracttal):
    c = app.test_client()
    with c.session_transaction() as s:
        s["logado"], s["admin"] = True, False
        s["usuario"] = {"email": "pessoa.teste@exemplo.test", "nome": "Pessoa Teste", "perfil": "PCM"}
    r = c.get("/t/base/fracttal")
    assert r.status_code == 403 and "só para administradores" in r.get_data(as_text=True)
    assert not com_fracttal                                                      # nem chega a ler o Fracttal

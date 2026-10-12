"""Base > Integração Fracttal (Levi, 12/10/2026: "Temos a relação do time de campo, precisamos da relação do pessoal do
fractall e também posteriormente vamos precisar relacionar os setores"): o pessoal do Fracttal ao lado do cadastro de
pessoas, pelo critério do login (e-mail da ficha; sem ele, o nome de UMA ficha), as fichas sem conta no Fracttal e o
setor de cada pessoa (Levi: "Como faço para definir um setor???? tem que dar possibilidade"), gravado no livro
`nexus_setores` do banco. Só administrador. Nenhum teste vai ao Fracttal (o fornecedor falso do cliente do Campo) nem ao
banco de verdade (o banco falso do `test_campo_visao`)."""
import pytest
from test_campo_visao import banco  # noqa: F401  (fixture)

from nexus.cadastro import fracttal_pessoal as FP
from nexus.cadastro import setores as S
from nexus.campo import fracttal
from nexus.dados import catalogo

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
JSON = {"Accept": "application/json"}


@pytest.fixture(autouse=True)
def _sem_copia_dos_setores():
    S._CACHE.clear()
    yield
    S._CACHE.clear()


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
    assert "codigo" not in FP.da_api(PESSOAL[0])                                  # a coluna Código saiu (12/10)
    # a origem pelo domínio do e-mail: a casa é gridco.com.br; cliente com acesso de leitura é externo
    assert FP.da_api({"email": "pessoa@gridco.com.br"})["origem"] == "Grid Co."
    assert FP.da_api({"email": "cliente@cliente.test"})["origem"] == "Externo"


def test_a_tela_mostra_o_pessoal_e_as_fichas_sem_conta(banco, com_fracttal, logado):
    html = logado.get("/t/base/fracttal").get_data(as_text=True)
    assert "Integração Fracttal" in html
    # 12/10, Levi: sem o título "Pessoal do Fracttal", sem a coluna Código e o "Como liga" vira a dica do (!)
    assert "Pessoal do Fracttal" not in html and "<th>Código</th>" not in html
    assert 'class="fr-dica-botao"' in html and 'role="tooltip"' in html and "Como liga." in html
    assert "cad-aviso--info" not in html
    # 4 no Fracttal; Beltrano pelo e-mail e Ciclano pelo nome (fichas 90 e 91 do banco falso); 2 sem ficha
    assert '<div class="r">No Fracttal</div><div class="v">4</div>' in html
    assert '<div class="r">Com ficha no Nexus</div><div class="v">2</div>' in html
    assert '<div class="r">Sem ficha no Nexus</div><div class="v">2</div>' in html
    assert 'href="/t/pessoas/colaborador/90">Beltrano Supervisor</a>' in html and "pelo e-mail" in html
    assert 'href="/t/pessoas/colaborador/91">Ciclano Chefe</a>' in html and "pelo nome" in html
    # as fichas ativas sem conta no Fracttal: a supervisora e o coordenador de campo
    sem = html[html.index("Fichas do Nexus sem conta no Fracttal"):]
    assert "Supervisora Campo" in sem and "Coordenador Campo" in sem and "Beltrano" not in sem
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
    # e não grava: nem o setor de uma pessoa, nem a lista
    assert c.post("/t/base/fracttal/setor", data={"pessoa": "501", "setor_id": ""}).status_code == 403
    assert c.post("/t/base/fracttal/setores", data={"acao": "criar", "nome": "PCM"}).status_code == 403
    assert not banco.linhas(S.LIVRO, S.ABA_SETOR)


# ── o setor (12/10/2026) ──────────────────────────────────────────────────────────────────────────────────────────
def test_o_setor_de_cada_pessoa_e_a_ultima_decisao():
    d = [{"decidida_em": "2026-10-12T10:00:00Z", "fracttal_id": 1, "setor_id": 2},
         {"decidida_em": "2026-10-12T09:00:00Z", "fracttal_id": 1, "setor_id": 3},     # mais antiga, fora de ordem
         {"decidida_em": "2026-10-12T11:00:00Z", "fracttal_id": 2, "setor_id": 2},
         {"decidida_em": "2026-10-12T12:00:00Z", "fracttal_id": 2, "setor_id": None}]  # tirada do setor
    assert S.vigentes(d) == {1: 2, 2: None}


def test_criar_renomear_excluir_e_definir_no_banco(app, banco):
    cfg, base, sessao = app.config, "http://pg.falso", banco
    pcm = S.criar(" PCM ", cfg, base, sessao)
    cos = S.criar("COS", cfg, base, sessao)
    assert (pcm["setor_id"], cos["setor_id"]) == (1, 2) and pcm["nome"] == "PCM"
    with pytest.raises(S.Recusada, match="Já existe"):
        S.criar("pcm", cfg, base, sessao)                     # o mesmo nome, sem caixa nem acento
    with pytest.raises(S.Recusada, match="e-mail"):
        S.criar("fulana@empresa.test", cfg, base, sessao)     # o banco tem leitura aberta
    pessoa = {"id": 501, "email": "beltrano@exemplo.test", "ficha": {"pessoa_id": 90}, "por": "e-mail"}
    sem_ficha = {"id": 503, "email": "fulana@empresa.test", "ficha": None, "por": ""}
    r = S.definir([pessoa, sem_ficha], 1, cfg, base, sessao, quem_email="admin@exemplo.test")
    assert r == {"gravadas": 2, "iguais": 0, "setor": "PCM"}
    # quem já está no setor não ganha linha nova (abrir e salvar sem mexer não muda nada)
    assert S.definir([pessoa], 1, cfg, base, sessao)["gravadas"] == 0
    linhas = banco.linhas(S.LIVRO, S.ABA_DECISAO)
    assert len(linhas) == 2 and list(linhas[0]) == list(S.CAB_DECISAO)
    assert (linhas[0]["fracttal_id"], linhas[0]["pessoa_id"], linhas[0]["pessoa_ligada_por"]) == (501, 90, "e-mail")
    assert linhas[1]["pessoa_id"] is None and linhas[1]["pessoa_hmac"]          # sem ficha: o código do e-mail
    assert linhas[0]["decidida_por_hmac"] and linhas[0]["origem"] == "tela"
    # regra 8: nenhum nome nem e-mail de pessoa no banco
    tudo = [str(v) for x in linhas + banco.linhas(S.LIVRO, S.ABA_SETOR) for v in x.values()]
    assert not [v for v in tudo if "@" in v or "Beltrano" in v or "Fulana" in v]
    # excluir só setor sem ninguém; renomear mantém o ID e as decisões
    with pytest.raises(S.Recusada, match="2 pessoas estão no setor PCM"):
        S.excluir(1, cfg, base, sessao)
    assert S.renomear(1, "PCM e Programação", cfg, base, sessao)["setor_id"] == 1
    S.definir([pessoa, sem_ficha], None, cfg, base, sessao)                     # tira as duas do setor
    assert S.excluir(1, cfg, base, sessao)["excluido"]
    setores = {x["setor_id"]: x for x in banco.linhas(S.LIVRO, S.ABA_SETOR)}
    assert setores[1]["excluido"] == "sim" and setores[1]["nome"] == "PCM e Programação" and setores[2]["excluido"] is None
    with pytest.raises(S.Recusada, match="não existe mais"):
        S.definir([pessoa], 1, cfg, base, sessao)                               # setor excluído não recebe ninguém
    assert S.criar("Engenharia", cfg, base, sessao)["setor_id"] == 3            # o ID do excluído não volta
    assert len(banco.linhas(S.LIVRO, S.ABA_DECISAO)) == 4                       # 2 decisões + as 2 de tirar


def test_leitura_que_falha_nao_grava_e_sem_token_nao_grava(app, banco):
    cfg = app.config
    S.criar("PCM", cfg, "http://pg.falso", banco)

    class Fora:
        def get(self, *a, **k):
            raise ConnectionError("banco fora")
        post = get
    pessoa = {"id": 501, "email": "beltrano@exemplo.test", "ficha": None, "por": ""}
    with pytest.raises(S.Recusada, match="nada foi gravado"):
        S.definir([pessoa], 1, cfg, "http://pg.falso", Fora())
    sem_token = dict(cfg, GRIDCO_SQL_TOKEN=None)
    with pytest.raises(S.Recusada, match="GRIDCO_SQL_TOKEN"):
        S.definir([pessoa], 1, sem_token, "http://pg.falso", banco)
    assert banco.linhas(S.LIVRO, S.ABA_DECISAO) == [] and len(banco.linhas(S.LIVRO, S.ABA_SETOR)) == 1


def test_a_tela_cria_o_setor_e_poe_a_pessoa_nele(banco, com_fracttal, logado):
    # sem setor ainda: a coluna diz "a definir" e o painel convida a criar
    html = logado.get("/t/base/fracttal").get_data(as_text=True)
    assert "a definir" in html and "Nenhum setor ainda" in html and "Setores (0)" in html
    # criar pela lista (formulário: volta à mesma tela, com os filtros e o painel aberto)
    r = logado.post("/t/base/fracttal/setores", data={"acao": "criar", "nome": "PCM", "volta": "origem=Externo&x=1"})
    assert r.status_code == 303 and r.headers["Location"].endswith("/t/base/fracttal?origem=Externo")
    html = logado.get("/t/base/fracttal?origem=Externo").get_data(as_text=True)
    assert "Setor PCM criado." in html and 'id="fr-setores" open' in html and "Setores (1)" in html
    # o setor de UMA pessoa pelo fetch: JSON, sem recarregar
    r = logado.post("/t/base/fracttal/setor", data={"pessoa": "501", "setor_id": "1"}, headers=JSON)
    assert r.status_code == 200 and r.get_json()["ok"] and r.get_json()["setor"] == "PCM"
    assert [x["fracttal_id"] for x in banco.linhas(S.LIVRO, S.ABA_DECISAO)] == [501]
    html = logado.get("/t/base/fracttal").get_data(as_text=True)
    linha = html[html.index('id="p-501"'):html.index('id="p-502"')]
    assert '<option value="1" selected>PCM</option>' in linha
    assert "PCM (1)" in html and "Sem setor (3)" in html and "1 pessoa</span>" in html
    # o painel não deixa excluir setor com gente; o filtro acha quem está nele
    assert 'value="excluir" formnovalidate disabled' in html
    so_pcm = logado.get("/t/base/fracttal?setor=1").get_data(as_text=True)
    assert 'id="p-501"' in so_pcm and 'id="p-503"' not in so_pcm
    sem = logado.get("/t/base/fracttal?setor=sem").get_data(as_text=True)
    assert 'id="p-501"' not in sem and 'id="p-503"' in sem
    # as marcadas de uma vez (formulário da barra): 303 de volta, uma linha por pessoa que mudou
    r = logado.post("/t/base/fracttal/setor", data={"pessoa": ["501", "502", "503"], "setor_id": "1", "volta": "setor=sem"})
    assert r.status_code == 303 and r.headers["Location"].endswith("/t/base/fracttal?setor=sem")
    assert "2 pessoas no setor PCM; 1 já estavam." in logado.get("/t/base/fracttal").get_data(as_text=True)
    assert len(banco.linhas(S.LIVRO, S.ABA_DECISAO)) == 3


def test_a_tela_recusa_o_que_nao_deve_gravar(banco, com_fracttal, logado):
    logado.post("/t/base/fracttal/setores", data={"acao": "criar", "nome": "PCM"})
    # de outro site: nada
    r = logado.post("/t/base/fracttal/setor", data={"pessoa": "501", "setor_id": "1"},
                    headers=dict(JSON, **{"Sec-Fetch-Site": "cross-site"}))
    assert r.status_code == 403 and not r.get_json()["ok"]
    # pessoa fora da lista do Fracttal de agora (página velha) e setor que não existe
    r = logado.post("/t/base/fracttal/setor", data={"pessoa": "999", "setor_id": "1"}, headers=JSON)
    assert r.status_code == 400 and "atualize a página" in r.get_json()["erro"]
    r = logado.post("/t/base/fracttal/setor", data={"pessoa": "501", "setor_id": "7"}, headers=JSON)
    assert r.status_code == 409 and "não existe mais" in r.get_json()["erro"]
    assert banco.linhas(S.LIVRO, S.ABA_DECISAO) == []
    # a volta só leva os filtros conhecidos: nada de endereço vindo do formulário
    r = logado.post("/t/base/fracttal/setores", data={"acao": "criar", "nome": "COS", "volta": "//mal.test/x?q=a"})
    assert r.headers["Location"].startswith("/t/base/fracttal")


def test_setores_no_catalogo_da_governanca():
    """Regra 10: livro registrado antes de existir, abas na regra, o fato com grão, chave e texto; nada pessoal."""
    livro = catalogo.LIVRO_POR_NOME[S.LIVRO]
    assert livro.abas == (S.ABA_SETOR, S.ABA_DECISAO) and not livro.no_banco
    f = catalogo.POR_ID["decisao_setor"]
    assert f.livro == f"{S.LIVRO} · {S.ABA_DECISAO}" and all(c in S.CAB_DECISAO for c in f.chave)
    assert f.dims["pessoa"][0] == "id" and f.area == "base"
    assert not [c for c in S.CAB_DECISAO if c in ("nome", "email") or c.startswith(("nome_", "email_"))]

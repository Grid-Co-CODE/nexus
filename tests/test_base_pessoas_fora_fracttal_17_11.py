"""Base > Acessos > Pessoas e setores: a pessoa que não está no Fracttal (17/11/2026, Levi: "tem que ter a opção de
inserir uma pessoa que não está no fracttal").

O que estes testes seguram: o "Incluir pessoa" grava a pessoa no livro `nexus_pessoas_fora_fracttal` (nome e e-mail só
cifrados) com o id da faixa reservada, e o setor dela no `nexus_setores` pelo mesmo id; o login acha o setor pelo código
do e-mail, como o de quem está no Fracttal; a pessoa aparece na mesma lista com a etiqueta "fora do Fracttal" e muda de
setor pela linha; as recusas (e-mail de fora da Grid, o que já está no Fracttal, a repetida, o nome vazio, outro site, quem
não é administrador); e o "Tirar da lista", que a deixa sem setor. Banco falso e Fracttal falso, como os da aba."""
import json

import pytest
from test_base_fracttal import JSON, URL, _sem_copia_dos_setores, _visivel, com_fracttal  # noqa: F401  (fixtures)
from test_campo_visao import banco  # noqa: F401  (fixture)

from nexus.auth import setor_telas as ST
from nexus.cadastro import pessoas_fora as PF
from nexus.cadastro import setores as S
from nexus.cadastro.ligacao_campo import codigo_da_pessoa
from nexus.dados import catalogo

FORA = "/t/base/fracttal/pessoa-fora"
EMAIL = "gabriela.nova@gridco.com.br"
PID = PF.ID_BASE + 1


@pytest.fixture(autouse=True)
def _sem_copia_das_pessoas_fora():
    PF.esquecer()
    yield
    PF.esquecer()


def _incluir(cli, **mais):
    dados = {"acao": "incluir", "nome": "Gabriela  Nova", "email": EMAIL}
    dados.update(mais)
    return cli.post(FORA, data=dados)


def test_incluir_grava_cifrado_poe_no_setor_e_o_login_acha(app, banco, com_fracttal, logado):
    logado.post("/t/base/fracttal/setores", data={"acao": "criar", "nome": "PCM"})
    r = _incluir(logado, setor_id="1", volta="setor=sem")
    assert r.status_code == 303 and r.headers["Location"].endswith("/t/base/acessos?aba=pessoas&setor=sem#p-%d" % PID)
    html = logado.get(URL).get_data(as_text=True)
    assert "Gabriela Nova entrou na lista, no setor PCM." in html
    assert "5</span> pessoas (<span class=\"gc-num\">1</span> fora do Fracttal)" in html
    linha = html[html.index(f'id="p-{PID}"'):]
    linha = linha[:linha.index("</tr>")]
    assert "fora do Fracttal</span>" in linha and EMAIL in linha and '<option value="1" selected>PCM</option>' in linha
    assert "Tirar da lista" in linha and "sem conta" in linha
    # o livro: o id da faixa reservada, a pessoa pelo código do e-mail; nome e e-mail nunca em claro (regra 8)
    (l,) = banco.linhas(PF.LIVRO, PF.ABA)
    assert list(l) == list(PF.CAB) and l["pessoa_fora_id"] == PID and l["ativa"] == "sim"
    assert l["pessoa_hmac"] == codigo_da_pessoa(app.config["NEXUS_PESSOA_HMAC"], EMAIL)
    claro = json.dumps(banco.linhas(PF.LIVRO, PF.ABA) + banco.linhas(S.LIVRO, S.ABA_DECISAO), default=str).lower()
    assert "gabriela" not in claro and EMAIL not in claro
    # o setor dela vai no nexus_setores pelo mesmo id, e o login acha pelo código do e-mail
    (d,) = banco.linhas(S.LIVRO, S.ABA_DECISAO)
    assert d["fracttal_id"] == PID and d["setor_id"] == 1 and d["pessoa_hmac"] == l["pessoa_hmac"]
    assert ST.setor_da_pessoa(app.config, EMAIL, "http://pg.falso", banco) == {"id": 1, "nome": "PCM"}
    # muda de setor pela linha, como as do Fracttal
    logado.post("/t/base/fracttal/setores", data={"acao": "criar", "nome": "COS"})
    r = logado.post("/t/base/fracttal/setor", data={"pessoa": str(PID), "setor_id": "2"}, headers=JSON)
    assert r.status_code == 200 and r.get_json()["setor"] == "COS"
    # o filtro do Acesso tem a opção, e a busca acha
    assert '<option value="Fora do Fracttal">Fora do Fracttal</option>' in html
    assert _visivel(logado.get(URL + "&q=gabriela").get_data(as_text=True), PID)


def test_as_recusas(app, banco, com_fracttal, logado):
    r = _incluir(logado, email="alguem@empresa.test")
    assert r.status_code == 303 and "Só e-mail da Grid Co." in logado.get(URL).get_data(as_text=True)
    assert "Escreva o nome" in logado.post(FORA, data={"acao": "incluir", "nome": " ", "email": EMAIL},
                                           headers=JSON).get_json()["erro"]
    assert "Escreva o e-mail" in logado.post(FORA, data={"acao": "incluir", "nome": "Gabriela Nova", "email": "x"},
                                             headers=JSON).get_json()["erro"]
    assert banco.linhas(PF.LIVRO, PF.ABA) == []
    # o e-mail que já está no Fracttal: a pessoa já está na lista
    with pytest.raises(PF.Recusada, match="já está no Fracttal"):
        PF.incluir("Gabriela Nova", EMAIL, ["outra@gridco.com.br", " Gabriela.Nova@gridco.com.br"], app.config)
    # a repetida
    assert _incluir(logado).status_code == 303
    r = logado.post(FORA, data={"acao": "incluir", "nome": "Gabriela N", "email": EMAIL.upper()}, headers=JSON)
    assert r.status_code == 409 and "já foi incluída" in r.get_json()["erro"]
    # de outro site e quem não é administrador: nada
    r = logado.post(FORA, data={"acao": "incluir", "nome": "Outra Pessoa", "email": "outra.pessoa@gridco.com.br"},
                    headers=dict(JSON, **{"Sec-Fetch-Site": "cross-site"}))
    assert r.status_code == 403
    with logado.session_transaction() as s:
        s["admin"] = False
    assert logado.post(FORA, data={"acao": "incluir", "nome": "Outra Pessoa",
                                   "email": "outra.pessoa@gridco.com.br"}).status_code == 403
    assert len(banco.linhas(PF.LIVRO, PF.ABA)) == 1


def test_sem_as_chaves_nao_grava(app, banco, com_fracttal, logado):
    app.config["NEXUS_CHAVE_CADASTRO"] = None
    html = logado.get(URL).get_data(as_text=True)
    assert "Este Nexus não grava a pessoa" in html
    r = logado.post(FORA, data={"acao": "incluir", "nome": "Gabriela Nova", "email": EMAIL}, headers=JSON)
    assert r.status_code == 409 and "NEXUS_CHAVE_CADASTRO" in r.get_json()["erro"]
    assert banco.linhas(PF.LIVRO, PF.ABA) == []


def test_tirar_da_lista_deixa_sem_setor(app, banco, com_fracttal, logado):
    logado.post("/t/base/fracttal/setores", data={"acao": "criar", "nome": "PCM"})
    _incluir(logado, setor_id="1")
    r = logado.post(FORA, data={"acao": "tirar", "pessoa": str(PID)})
    assert r.status_code == 303
    html = logado.get(URL).get_data(as_text=True)
    assert "Gabriela Nova saiu da lista e ficou sem setor." in html and f'id="p-{PID}"' not in html
    (l,) = banco.linhas(PF.LIVRO, PF.ABA)
    assert l["ativa"] == "não"                                       # a linha fica (o id não volta)
    assert [d["setor_id"] for d in banco.linhas(S.LIVRO, S.ABA_DECISAO)] == [1, None]
    assert ST.setor_da_pessoa(app.config, EMAIL, "http://pg.falso", banco) is None
    # só quem foi incluído aqui sai por aqui; e a que já saiu não sai de novo
    r = logado.post(FORA, data={"acao": "tirar", "pessoa": "501"}, headers=JSON)
    assert r.status_code == 409 and "Só se tira da lista" in r.get_json()["erro"]
    r = logado.post(FORA, data={"acao": "tirar", "pessoa": str(PID)}, headers=JSON)
    assert r.status_code == 409 and "não está mais na lista" in r.get_json()["erro"]
    # incluir de novo ganha outro id
    _incluir(logado)
    assert [x["pessoa_fora_id"] for x in banco.linhas(PF.LIVRO, PF.ABA)] == [PID, PID + 1]


def test_no_catalogo_antes_da_gravacao():
    l = catalogo.LIVRO_POR_NOME[PF.LIVRO]
    assert l.abas == (PF.ABA,) and catalogo.aba_segue_a_regra(PF.ABA) and not l.no_banco
    assert PF.e_de_fora(PF.ID_BASE + 1) and not PF.e_de_fora(2_072_681)

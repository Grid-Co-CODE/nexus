"""Colaboradores (Segurança · HSEQ, 05/11/2026): as pessoas do cadastro do Nexus, só leitura, com os desligados num filtro
("após o colaborador ser demitido eu ainda preciso ter a visibilidade dele"). Banco falso do Campo (test_campo_visao.py)
com quatro fichas de nome fictício: uma Ativa, uma Desligada, uma sem status e uma excluída."""
import json
import re

import pytest
from test_campo_visao import CHAVE_CADASTRO, _aba, banco  # noqa: F401  (banco é fixture)

from nexus.cadastro.cifra import Cofre
from nexus.campo import visao
from nexus.hseq import colaboradores as COL


def _ficha(pid, nome, status, equipe=10, vinculo="Colaborador de campo", cargo="Técnico O&M", excluido="não"):
    sens = Cofre(CHAVE_CADASTRO).cifrar(json.dumps({"nome": nome, "nome_padrao": nome, "cpf": "000.000.000-00"}),
                                        f"banco/pessoas/{pid}") if nome else None
    return {"pessoa_id": pid, "vinculo": vinculo, "cargo": cargo, "equipe_id": equipe, "status": status,
            "supervisor_id": None, "excluido": excluido, "sensivel_cifrado": sens}


@pytest.fixture
def pessoas(banco):
    _aba(banco, "cadastro_nexus", "pessoas", [
        _ficha(1, "Bruna Ficticia Lima", "Ativo"),
        _ficha(2, "Ana Exemplo Rocha", "Desligado", cargo="Eletricista O&M"),
        _ficha(3, "Caio Teste Prado", None, equipe=20, vinculo="Gestor de contrato", cargo=None),
        _ficha(4, "Davi Apagado Nunes", "Ativo", excluido="sim"),
        _ficha(5, None, "Ativo")])
    visao.limpar()
    return banco


def test_le_o_cadastro_sem_as_excluidas_e_com_a_regiao_da_equipe(pessoas):
    d = COL.colaboradores().dados
    p = {x["pessoa_id"]: x for x in d["pessoas"]}
    assert set(p) == {1, 2, 3, 5}                                            # a excluída não entra
    assert (p[1]["nome"], p[1]["equipe"], p[1]["regiao"], p[1]["status"], p[1]["desligado"]) == (
        "Bruna Ficticia Lima", "SP Norte 01", "Sudeste 03", "Ativo", False)
    assert (p[2]["status"], p[2]["desligado"]) == ("Desligado", True)
    assert (p[3]["status"], p[3]["desligado"]) == (COL.SEM_STATUS, False)  # sem status conta como ativo
    assert p[3]["vinculo"] == "Gestor de contrato (Supervisor PM)"         # o rótulo do cadastro
    assert (p[5]["nome"], p[5]["com_nome"], d["sem_nome"]) == ("Pessoa 5", False, 1)
    # a ordem: pelo nome, e quem não tem nome legível por último
    assert [x["pessoa_id"] for x in d["pessoas"]] == [2, 1, 3, 5]
    assert "cpf" not in p[1] and "000.000.000-00" not in json.dumps(d["pessoas"])   # só o nome sai do cofre


def test_contas_e_filtro_de_situacao():
    lista = [{"desligado": False}, {"desligado": True}, {"desligado": False}]
    assert COL.contar(lista) == {"todos": 3, "ativos": 2, "desligados": 1}
    assert [COL.na_situacao(x, "desligados") for x in lista] == [False, True, False]
    assert all(COL.na_situacao(x, "todos") for x in lista)
    assert COL.situacao("qualquer") == "ativos" and COL.situacao("desligados") == "desligados"


def test_sem_a_chave_do_cadastro_mostra_o_numero(pessoas, app):
    app.config["NEXUS_CHAVE_CADASTRO"] = None
    visao.limpar()
    d = COL.colaboradores().dados
    assert d["sem_chave"] is True and {x["nome"] for x in d["pessoas"]} == {"Pessoa 1", "Pessoa 2", "Pessoa 3",
                                                                              "Pessoa 5"}


def _linhas(html) -> list[str]:
    corpo = html.split("<tbody>")[1].split("</tbody>")[0]
    return [" ".join(re.sub(r"<[^>]+>", " ", t).split()) for t in re.findall(r"<tr>(.*?)</tr>", corpo, re.S)]


def test_tela_abre_nos_ativos_e_mostra_os_desligados_no_filtro(pessoas, logado):
    html = logado.get("/t/hseq/colaboradores").get_data(as_text=True)
    linhas = _linhas(html)
    assert any("Bruna Ficticia Lima" in x for x in linhas) and not any("Ana Exemplo Rocha" in x for x in linhas)
    texto = " ".join(re.sub(r"<[^>]+>", " ", html).split())
    assert "Ativos 3 na operação" in texto and "Desligados 1 continuam no cadastro" in texto and "Todos 4" in texto
    assert 'class="gc-explica-caixa"' in html and "De onde vem" in html     # a explicação no "!" do título
    assert "000.000.000-00" not in html
    so = _linhas(logado.get("/t/hseq/colaboradores?situacao=desligados").get_data(as_text=True))
    assert len(so) == 1 and "Ana Exemplo Rocha" in so[0] and "Desligado" in so[0]
    todos = _linhas(logado.get("/t/hseq/colaboradores?situacao=todos").get_data(as_text=True))
    assert len(todos) == 4


def test_filtros_de_vinculo_regiao_e_busca(pessoas, logado):
    g = _linhas(logado.get("/t/hseq/colaboradores?vinculo=Gestor+de+contrato+(Supervisor+PM)").get_data(as_text=True))
    assert len(g) == 1 and "Caio Teste Prado" in g[0] and "Sul 01" in g[0]
    r = _linhas(logado.get("/t/hseq/colaboradores?regiao=Sudeste+03&situacao=todos").get_data(as_text=True))
    assert len(r) == 3 and not any("Caio" in x for x in r)
    b = _linhas(logado.get("/t/hseq/colaboradores?q=bruna").get_data(as_text=True))
    assert len(b) == 1 and "Bruna Ficticia Lima" in b[0]
    nada = _linhas(logado.get("/t/hseq/colaboradores?q=ninguem").get_data(as_text=True))
    assert nada == ["Nenhum colaborador com esses filtros."]

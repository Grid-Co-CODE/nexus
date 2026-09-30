"""Cifra do dado sensível e selo da linha.

A API db_performace é compartilhada por vários sistemas e pessoas: o que for gravado lá sem cifra, todos
esses leem. E a escrita usa um token compartilhado por vários programas, então o selo é o que diz
se uma linha foi mexida fora do Nexus.
"""
import pytest

from nexus.cadastro.cifra import CifraErro, Cofre, gerar_chave


@pytest.fixture
def cofre():
    return Cofre(gerar_chave())


def test_ida_e_volta(cofre):
    c = cofre.cifrar("529.982.247-25", "pessoas/P-0001/cpf")
    assert c.startswith("cf1:")
    assert "529" not in c
    assert cofre.decifrar(c, "pessoas/P-0001/cpf") == "529.982.247-25"


def test_mesmo_texto_cifra_diferente_a_cada_vez(cofre):
    # Nonce novo por cifra: senão dois CPFs iguais teriam a mesma cifra e dava para cruzar linhas.
    a = cofre.cifrar("mesmo", "x")
    b = cofre.cifrar("mesmo", "x")
    assert a != b


def test_cifra_nao_serve_em_outra_linha_nem_em_outro_campo(cofre):
    # Quem tem o token de escrita não pode mover o CPF de uma pessoa para a linha de outra.
    c = cofre.cifrar("dado", "pessoas/P-0001/dados")
    with pytest.raises(CifraErro):
        cofre.decifrar(c, "pessoas/P-0002/dados")
    with pytest.raises(CifraErro):
        cofre.decifrar(c, "usinas/P-0001/dados")


def test_cifra_adulterada_falha(cofre):
    c = cofre.cifrar("dado", "x")
    corpo = c[4:]
    troca = "A" if corpo[10] != "A" else "B"
    with pytest.raises(CifraErro):
        cofre.decifrar("cf1:" + corpo[:10] + troca + corpo[11:], "x")


def test_outra_chave_nao_decifra(cofre):
    c = cofre.cifrar("dado", "x")
    with pytest.raises(CifraErro):
        Cofre(gerar_chave()).decifrar(c, "x")


def test_chave_invalida_recusada():
    with pytest.raises(CifraErro):
        Cofre("curta")


def test_selo_confere_e_acusa_mudanca(cofre):
    linha = {"id": "UFV-1", "nome": "Brodowski", "_versao": 3}
    linha["_selo"] = cofre.selar(linha)
    assert cofre.selo_confere(linha)
    mexida = dict(linha, nome="Brodowski 2")
    assert not cofre.selo_confere(mexida)
    assert not cofre.selo_confere(dict(linha, _versao=4))


def test_selo_nao_depende_da_ordem_das_colunas(cofre):
    a = {"id": "E-001", "nome": "SP Leste 01"}
    b = {"nome": "SP Leste 01", "id": "E-001"}
    assert cofre.selar(a) == cofre.selar(b)


def test_linha_sem_selo_nao_confere(cofre):
    assert not cofre.selo_confere({"id": "x"})

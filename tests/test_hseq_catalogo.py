"""O catálogo de dados da Segurança na pasta dela (05/11/2026, Levi: "eu quero deixar ela independente, não podemos
deixar travas com ela"; "independente no setor dela, claro"): `nexus/hseq/catalogo.py` declara os fatos e livros que o
Nexus grava pela Segurança, e o catálogo central os junta. As regras e as provas do catálogo continuam centrais; esta
prova segura o "no setor dela": daqui só sai fato da área hseq, gravado em livro `nexus_hseq_*`."""
from nexus.dados import catalogo as C
from nexus.dados import explica as X
from nexus.hseq import catalogo as H


def test_os_fatos_e_livros_da_seguranca_entram_no_catalogo_central():
    ids = [f.id for f in C.FATOS]
    assert len(ids) == len(set(ids))                                          # nenhum fato repetido entre as áreas
    assert {f.id for f in H.FATOS} <= set(ids)
    assert {l.nome for l in H.LIVROS} <= set(C.LIVRO_POR_NOME)
    for f in H.FATOS:
        assert X.RESUMO.get(f.id) and X.PARA_QUE.get(f.id)                    # o texto amigável vem junto


def test_a_seguranca_so_declara_o_que_e_dela():
    for f in H.FATOS:
        assert f.area == "hseq", f.id
        assert f.livro.startswith("nexus_hseq_"), f.id                        # o que o Nexus grava pela Segurança
    for l in H.LIVROS:
        assert l.nome.startswith("nexus_hseq_"), l.nome
    assert set(H.RESUMO) == set(H.PARA_QUE) == {f.id for f in H.FATOS}       # só texto dos fatos dela


def test_o_modelo_e_o_mesmo_do_catalogo():
    from nexus.dados import modelo
    assert C.Fato is modelo.Fato and C.Livro is modelo.Livro and C.DIMENSOES is modelo.DIMENSOES

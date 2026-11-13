"""O grupo Chamados da tela ETMs é o setor Performance (13/11/2026, Levi: "o setor vira performance mas continua na aba
chamados"). Em 05/11 o setor Chamados foi excluído e as pessoas dele foram para a Performance; o grupo, achado pelo NOME
do setor, ficou vazio, e as OS delas iam para Campo. Agora os grupos vão pelo setor_id. Banco e Fracttal de mentira,
nomes fictícios."""
from nexus.cadastro import setor_ids as SID
from nexus.engenharia import etm as E

SETORES = [{"setor_id": SID.ENGENHARIA, "nome": "Engenharia", "excluido": False},
           {"setor_id": SID.PERFORMANCE, "nome": "Performance", "excluido": False},
           {"setor_id": SID.CHAMADOS, "nome": "Chamados", "excluido": True},
           {"setor_id": SID.COS, "nome": "COS", "excluido": False}]
DECISOES = {"101": SID.ENGENHARIA, "202": SID.PERFORMANCE, "303": SID.COS}


def _com_banco(monkeypatch, setores=SETORES):
    from nexus.cadastro import fracttal_pessoal as FP
    from nexus.cadastro import setores as S
    from nexus.dados import conexao
    monkeypatch.setattr(conexao, "banco", lambda: (None, None))
    monkeypatch.setattr(S, "ler", lambda *a, **k: {"lido_em": 1.0, "setores": setores, "decisoes": []})
    monkeypatch.setattr(S, "vigentes", lambda decisoes: dict(DECISOES))
    monkeypatch.setattr(FP, "ler_pessoal", lambda: {"pessoas": [{"id": "101", "nome": "Ana Lima"},
                                                                 {"id": "202", "nome": "Carla Dias"},
                                                                 {"id": "303", "nome": "Bruno Reis"}]})


def test_o_grupo_chamados_e_o_setor_performance(app, monkeypatch):
    _com_banco(monkeypatch)
    s = E._ler_setores(app)
    assert s["por_id"] == {"101": "engenharia", "202": "chamados"}            # o COS fica de fora: é Campo
    assert s["nomes"] == {"engenharia": ["ana lima"], "chamados": ["carla dias"]}
    assert E._setor_do_responsavel({"id_personnel": 202}, s) == "chamados"
    assert E._setor_do_responsavel({"id_personnel": 303}, s) == "campo"


def test_pelo_id_e_nao_pelo_nome(app, monkeypatch):
    """Renomear o setor não tira o grupo (o caso de 05/11 foi a exclusão; o nome não manda mais)."""
    _com_banco(monkeypatch, [dict(s, nome="Performance e Chamados") if s["setor_id"] == SID.PERFORMANCE else s
                             for s in SETORES])
    assert E._ler_setores(app)["por_id"]["202"] == "chamados"


def test_os_grupos_usam_os_ids_do_codigo():
    assert E.GRUPO_DO_SETOR == {SID.ENGENHARIA: "engenharia", SID.PERFORMANCE: "chamados"}
    assert set(E.GRUPO_DO_SETOR.values()) == set(E.SETORES)

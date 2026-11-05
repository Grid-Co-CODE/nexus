"""O setor pelo setor_id, nunca pelo nome (04/11/2026, Levi, antes de renomear setores em Base → Acessos → Pessoas e
setores: "logo mais vou fazer alterações, não podemos ficar dependente de texto").

O que estes testes seguram: toda tela dona de setor (`Tela.do_setor`) e toda regra de quem age (Engenharia, Segurança,
PCM, OS Creator, COS) usam um ID de `cadastro/setor_ids.py`; renomear um setor no banco falso não muda quem vê nem quem
age; e o setor 10 ("Responsável UFV" no banco) recebe as telas que são dele, que pelo nome ("Responsáveis UFV") não casavam."""
import pytest

from nexus.auth import setor_telas as ST
from nexus.cadastro import setor_ids as SID
from nexus.cadastro import setores as S
from test_setor_telas import BASE, SETORES_DE_PRODUCAO, _sem_copias, banco  # noqa: F401  (fixtures)


def _donos(tela) -> tuple:
    d = tela.do_setor
    return tuple(d) if isinstance(d, (tuple, list)) else ((d,) if d else ())


def test_toda_tela_dona_de_setor_usa_um_setor_id_conhecido(app):
    vistas = 0
    for t in app.extensions["nexus_torres"]:
        for s in t.telas:
            for d in _donos(s):
                assert isinstance(d, int) and not isinstance(d, bool), f"{t.id}/{s.id}: do_setor={d!r} (use cadastro/setor_ids.py)"
                assert d in SID.TODOS, f"{t.id}/{s.id}: setor_id {d} fora de cadastro/setor_ids.py"
                vistas += 1
    assert vistas >= 15          # Engenharia, Segurança, PCM, Campo e os relatórios da Central


def test_as_regras_de_quem_age_usam_o_setor_id():
    from nexus.campo import verificacao
    from nexus.engenharia import acompanhamento
    from nexus.hseq import decisoes
    from nexus.pcm import telas as pcm_telas
    from nexus.performance import quadro_equipe
    from nexus.torres.oscreator import ponte
    assert acompanhamento.SETOR == SID.ENGENHARIA and decisoes.SETOR == SID.SEGURANCA
    assert quadro_equipe.SETOR == SID.PERFORMANCE
    assert pcm_telas.SETOR_PCM == SID.PCM and pcm_telas.SETORES_MARCAM == (SID.PCM, SID.RESPONSAVEL_UFV)
    assert ponte.SETOR_PCM == SID.PCM and ponte.SETOR_OBS_GARANTIAS == SID.PERFORMANCE and verificacao.SETOR_COS == SID.COS
    assert all(s == ponte.TODOS_OS_SETORES or s in SID.TODOS for s in ponte.SETORES_COM_LISTA_CENTRAL)


def test_os_ids_sao_os_da_ordem_de_producao():
    """A lista dos testes (`SETORES_DE_PRODUCAO`, criada nessa ordem no banco falso) e os IDs do código contam a mesma
    história: o 1º criado é o 1, e assim por diante."""
    ids = {n: i for i, n in enumerate(SETORES_DE_PRODUCAO, start=1)}
    assert (ids["Engenharia"], ids["Performance"], ids["Zeladoria"], ids["Segurança"], ids["COS"]) == (
        SID.ENGENHARIA, SID.PERFORMANCE, SID.ZELADORIA, SID.SEGURANCA, SID.COS)
    assert (ids["Supervisão Campo"], ids["Chamados"], ids["PCM"], ids["Responsável UFV"]) == (
        SID.SUPERVISAO_CAMPO, SID.CHAMADOS, SID.PCM, SID.RESPONSAVEL_UFV)


@pytest.fixture
def producao(app, banco):     # noqa: F811
    for nome in SETORES_DE_PRODUCAO:
        S.criar(nome, app.config, BASE, banco)
    return banco


def test_renomear_o_setor_nao_muda_quem_ve(app, producao):
    with app.app_context():
        antes = {sid: ST.das_do_setor({"id": sid, "nome": "?"}) for sid in (SID.PCM, SID.ENGENHARIA, SID.RESPONSAVEL_UFV)}
        S.renomear(SID.PCM, "Planejamento e Controle", app.config, BASE, producao)
        S.renomear(SID.ENGENHARIA, "Engenharia de Ativos", app.config, BASE, producao)
        nomes = {s["setor_id"]: s["nome"] for s in S.ler(BASE, producao, forcar=True)["setores"]}
        assert nomes[SID.PCM] == "Planejamento e Controle"
        for sid, telas in antes.items():
            assert ST.das_do_setor({"id": sid, "nome": nomes[sid]}) == telas
        assert "pcm/gerar" in antes[SID.PCM] and "engenharia/mesa" in antes[SID.ENGENHARIA]
        # o nome sozinho não dá a tela de ninguém: outro setor chamado "PCM" não vê o que é do PCM
        assert "pcm/gerar" not in ST.das_do_setor({"id": SID.ZELADORIA, "nome": "PCM"})


def test_o_responsavel_ufv_recebe_as_telas_dele(app):
    """O setor 10 se chama "Responsável UFV" no banco, e o código procurava "Responsáveis UFV": pelo nome, sem acento e
    sem caixa, os dois não casavam, e as telas do PCM e do Campo que são dele não abriam sozinhas."""
    with app.app_context():
        telas = ST.das_do_setor({"id": SID.RESPONSAVEL_UFV, "nome": "Responsável UFV"})
    assert {"pcm/gerar", "pcm/quadro", "pcm/fora-da-programacao", "pcm/tecnicos-por-usina", "campo/ocorrencias"} <= telas


def test_renomear_nao_muda_quem_age():
    from nexus.engenharia import acompanhamento
    from nexus.hseq import decisoes
    assert acompanhamento.pode_agir({"id": SID.ENGENHARIA, "nome": "Engenharia de Ativos"}, False)
    assert not acompanhamento.pode_agir({"id": SID.PERFORMANCE, "nome": "Engenharia"}, False)
    assert decisoes.pode_decidir({"id": SID.SEGURANCA, "nome": "HSEQ"}, False)
    assert not decisoes.pode_decidir({"id": SID.COS, "nome": "Segurança"}, False)
    # o Quadro da equipe da Performance: a equipe é a do setor 2, com qualquer nome
    from nexus.performance import quadro_equipe as Q
    st = {"setores": [{"setor_id": SID.PERFORMANCE, "nome": "Desempenho", "excluido": False},
                     {"setor_id": SID.ENGENHARIA, "nome": "Performance", "excluido": False}],
          "decisoes": [{"fracttal_id": 10, "setor_id": SID.PERFORMANCE, "decidida_em": "2026-11-01T10:00:00"},
                       {"fracttal_id": 11, "setor_id": SID.ENGENHARIA, "decidida_em": "2026-11-01T10:00:00"}]}
    assert Q.ids_do_setor(st) == ["10"]

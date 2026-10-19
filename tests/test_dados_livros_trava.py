"""A trava dos livros que só crescem (Levi, 18/10/2026: "Proteger os livros do Nexus de gravar sobre leitura vazia").

A gravação troca o livro inteiro (`sync-xlsx?replace=true`). Se a listagem do banco omitir as abas de um livro por um
instante, quem relê antes de gravar recebe vazio, e a gravação seguinte publicaria só a linha nova: o histórico iria
embora para sempre (a API não apaga nem devolve). O livro que só cresce é declarado no catálogo (`Livro.so_cresce`), e o
`livros.publicar` confere ANTES de trocar: listagem incompleta, aba que encolheria e aba que sumiria são recusadas.
Medido no banco real em 18/10/2026: o `row_count` da listagem é o número de linhas que a leitura devolve, e o
`sheet_count` do livro diz quantas abas ele tem. Banco falso (tests/pg_falso.py)."""
import json

import pytest
from pg_falso import ApiPGFalsa

from nexus.dados import catalogo, livros

B = "http://pg.falso"


def _livro(api, nome, abas):
    """Põe no banco falso um livro com as abas {aba: número de linhas}."""
    api.workbooks[nome] = {"key": nome}
    for aba, n in abas.items():
        api._id(nome, aba)["linhas"] = [{"headers": ["id"], "values": [i]} for i in range(n)]


def _tab(**abas):
    return {aba: (["id"], [[i] for i in range(n)]) for aba, n in abas.items()}


def _pub(api, nome, tabelas):
    return livros.publicar(nome, nome, tabelas, base=B, token="tk", sessao=api)


def test_livro_que_so_cresce_recusa_aba_que_encolheria():
    api = ApiPGFalsa()
    _livro(api, "nexus_setores", {"dim_setor": 10, "fato_decisao_setor": 37})
    with pytest.raises(livros.GravacaoRecusada, match="37"):
        _pub(api, "nexus_setores", _tab(dim_setor=10, fato_decisao_setor=1))
    assert api.syncs == 0 and len(api.linhas("nexus_setores", "fato_decisao_setor")) == 37


def test_livro_que_so_cresce_recusa_listagem_incompleta():
    # o caso que apagaria tudo: o livro diz que tem 2 abas e a listagem não traz nenhuma
    api = ApiPGFalsa()
    _livro(api, "nexus_setores", {"dim_setor": 10, "fato_decisao_setor": 37})
    api.omitir.add("nexus_setores")
    assert livros.ler(B, api, "nexus_setores", "fato_decisao_setor") == []      # quem relê recebe vazio
    with pytest.raises(livros.GravacaoRecusada, match="listagem"):
        _pub(api, "nexus_setores", _tab(dim_setor=1, fato_decisao_setor=1))
    assert api.syncs == 0
    api.omitir.clear()
    assert len(api.linhas("nexus_setores", "fato_decisao_setor")) == 37


def test_livro_que_so_cresce_recusa_aba_que_sumiria():
    api = ApiPGFalsa()
    _livro(api, "nexus_setores", {"dim_setor": 10, "fato_decisao_setor": 37})
    with pytest.raises(livros.GravacaoRecusada, match="fato_decisao_setor"):
        _pub(api, "nexus_setores", _tab(dim_setor=10))
    assert api.syncs == 0


def test_crescer_ou_manter_grava():
    api = ApiPGFalsa()
    _livro(api, "nexus_setores", {"dim_setor": 10, "fato_decisao_setor": 37})
    assert _pub(api, "nexus_setores", _tab(dim_setor=10, fato_decisao_setor=38)) == {"dim_setor": 10,
                                                                                     "fato_decisao_setor": 38}
    # renomear um setor troca a linha sem mudar a contagem: grava
    assert _pub(api, "nexus_setores", _tab(dim_setor=10, fato_decisao_setor=38))["dim_setor"] == 10
    assert api.syncs == 2


def test_livro_que_ainda_nao_existe_nasce():
    api = ApiPGFalsa()
    assert _pub(api, "nexus_setores", _tab(dim_setor=1, fato_decisao_setor=1)) == {"dim_setor": 1,
                                                                                   "fato_decisao_setor": 1}
    assert api.criacoes == 1


def test_a_aba_visao_pode_encolher_e_as_dimensoes_nao():
    # a aba_equipamentos da estrutura das usinas é uma VISÃO refeita a cada gravação (encolhe quando uma chave sai do
    # lugar da aba); as dimensões só crescem (excluir marca excluido = sim)
    api = ApiPGFalsa()
    abas = {"dim_supervisorio": 5, "dim_cabine": 5, "dim_inversor": 5, "aba_equipamentos": 4}
    _livro(api, "nexus_estrutura_usina", abas)
    _pub(api, "nexus_estrutura_usina", _tab(**dict(abas, aba_equipamentos=1)))
    with pytest.raises(livros.GravacaoRecusada, match="dim_cabine"):
        _pub(api, "nexus_estrutura_usina", _tab(**dict(abas, dim_cabine=4)))


def test_livro_sem_trava_segue_como_antes():
    # a carga de hora em hora encolhe de propósito (a janela da fonte): o livro dela não é dos que só crescem
    api = ApiPGFalsa()
    _livro(api, "nexus_fatos", {"fato_fechamento": 50, "qualidade": 3})
    assert _pub(api, "nexus_fatos", _tab(fato_fechamento=40)) == {"fato_fechamento": 40}


def test_os_livros_que_so_crescem_estao_declarados_no_catalogo():
    from nexus.auth import dono_relatorio, setor_telas
    from nexus.cadastro import estrutura_usina, setores
    from nexus.campo import decisao_pt, observacao_responsavel, ocorrencias, ronda_avulsa
    from nexus.contratos import acessos_clientes, tratamento
    from nexus.engenharia import acompanhamento
    from nexus.pcm import atribuicoes, motivos
    from nexus.pcm.acompanhamento import curadoria
    for m in (dono_relatorio, setor_telas, estrutura_usina, setores, decisao_pt, observacao_responsavel, ronda_avulsa,
              acessos_clientes, tratamento, atribuicoes, motivos, curadoria, acompanhamento, ocorrencias):
        l = catalogo.LIVRO_POR_NOME[m.LIVRO]
        assert l.so_cresce and set(l.so_cresce) <= set(l.abas), m.LIVRO
    assert "aba_equipamentos" not in catalogo.LIVRO_POR_NOME[estrutura_usina.LIVRO].so_cresce
    for nome in ("nexus_fatos", "nexus_dimensoes", "nexus_equipamentos", "nexus_chamados", "nexus_os"):
        assert catalogo.LIVRO_POR_NOME[nome].so_cresce == (), nome
    for l in catalogo.LIVROS:
        assert set(l.so_cresce) <= set(l.abas), l.nome


def test_contestacao_pega_com_a_listagem_vazia_nao_apaga_o_historico(app):
    # o caso de verdade, por um módulo: o "Pegar para mim" relê o livro, a listagem falha, ele vê vazio e grava só a
    # linha nova; a trava recusa e as duas linhas que havia continuam
    from nexus.cadastro.cifra import gerar_chave
    from nexus.contratos import tratamento as TR
    api = ApiPGFalsa()
    api.workbooks[TR.LIVRO] = {"key": TR.LIVRO}
    api._id(TR.LIVRO, TR.ABA)["linhas"] = [{"headers": list(TR.CAB), "values": [f"e{i}"] + [None] * (len(TR.CAB) - 1)}
                                           for i in range(2)]
    app.config.update(GRIDCO_DB_API=B, NEXUS_CHAVE_CADASTRO=gerar_chave(), NEXUS_PESSOA_HMAC="hmac-teste",
                      GRIDCO_SQL_TOKEN="tk")
    app.extensions["nexus_dados_sessao"] = api
    try:
        with app.app_context():
            api.omitir.add(TR.LIVRO)
            with pytest.raises(livros.GravacaoRecusada):
                TR.pegar("a9", "performance", {"email": "ana.lima@gridco.com.br", "nome": "Ana Lima"}, admin=False)
            api.omitir.clear()
            assert [l["id"] for l in api.linhas(TR.LIVRO, TR.ABA)] == ["e0", "e1"]
            assert "ana lima" not in json.dumps(api.linhas(TR.LIVRO, TR.ABA), default=str).lower()
    finally:
        app.extensions.pop("nexus_dados_sessao", None)


def test_aba_que_o_catalogo_nao_declara_pode_sair():
    # a aba antiga "decisoes" do livro de decisões de PT não vale mais (um Nexus velho a gravava): a troca a tira, como
    # antes. A trava protege as abas que o catálogo declara; a desconhecida não é dado do livro (o radar a mostra)
    api = ApiPGFalsa()
    _livro(api, "nexus_pt_decisoes", {"decisoes": 2, "fato_decisao_pt": 3})
    assert _pub(api, "nexus_pt_decisoes", _tab(fato_decisao_pt=4)) == {"fato_decisao_pt": 4}


class _Listagens:
    """O banco falso com /api/workbooks mexido (revisão final, 18/10/2026: a trava não pode ficar cega quando a listagem
    de livros falha ou deixa de trazer o sheet_count)."""

    def __init__(self, api, livros_sem=(), sem_sheet_count=False):
        self.api, self.livros_sem, self.sem_sheet_count = api, set(livros_sem), sem_sheet_count

    def get(self, url, *a, **k):
        r = self.api.get(url, *a, **k)
        if url.endswith("/api/workbooks"):
            from pg_falso import Resposta
            ws = [dict(w) for w in r.json() if w["key"] not in self.livros_sem]
            for w in ws:
                if self.sem_sheet_count:
                    w.pop("sheet_count", None)
            r = Resposta(200, ws)
        return r

    def post(self, *a, **k):
        return self.api.post(*a, **k)


def test_livro_fora_da_listagem_de_livros_mas_com_abas_recusa():
    # /api/workbooks sem o livro: o publicar o "criava" e trocava sem conferir nada; as abas dele seguem listadas
    api = ApiPGFalsa()
    _livro(api, "nexus_setores", {"dim_setor": 10, "fato_decisao_setor": 37})
    with pytest.raises(livros.GravacaoRecusada, match="listagem"):
        livros.publicar("nexus_setores", "x", _tab(dim_setor=1, fato_decisao_setor=1), base=B, token="tk",
                        sessao=_Listagens(api, livros_sem={"nexus_setores"}))
    assert api.syncs == 0 and len(api.linhas("nexus_setores", "fato_decisao_setor")) == 37


def test_sem_sheet_count_e_sem_abas_listadas_recusa():
    # a API deixou de mandar o sheet_count e a listagem de abas veio vazia: sem as duas, a trava não via nada
    api = ApiPGFalsa()
    _livro(api, "nexus_setores", {"dim_setor": 10, "fato_decisao_setor": 37})
    api.omitir.add("nexus_setores")
    with pytest.raises(livros.GravacaoRecusada, match="abas"):
        livros.publicar("nexus_setores", "x", _tab(dim_setor=1, fato_decisao_setor=1), base=B, token="tk",
                        sessao=_Listagens(api, sem_sheet_count=True))
    assert api.syncs == 0


def test_livro_criado_e_nunca_gravado_grava():
    # sheet_count 0 dito pelo banco (o livro foi criado e a 1ª troca falhou): sem abas listadas, grava
    api = ApiPGFalsa()
    api.workbooks["nexus_setores"] = {"key": "nexus_setores"}
    assert _pub(api, "nexus_setores", _tab(dim_setor=1, fato_decisao_setor=1)) == {"dim_setor": 1,
                                                                                   "fato_decisao_setor": 1}

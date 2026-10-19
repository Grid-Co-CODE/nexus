"""A pré-leitura da Visão do responsável (Levi, 19/10/2026: "as vezes abre rápido e as vezes é um parto para abrir").
A tela guarda a conta por 5 min e abre em 0,01 s; a demora era a 1ª abertura depois de cada deploy (o Nexus reinicia a
cada push), que fazia a conta inteira lendo as abas uma a uma, cada uma com a sua listagem do banco e as páginas uma
depois da outra: 26 a 46 s no banco real. Agora as abas das fontes vêm juntas (`responsaveis.pre_leitura` ->
`visao.carregar`: UMA listagem, as páginas em paralelo), com as mesmas linhas. Banco falso: nada vai à rede."""
import time

import pytest
import requests
from pg_falso import Resposta
from test_campo_responsaveis import tela  # noqa: F401  (fixture)
from test_campo_visao import _aba, banco  # noqa: F401  (fixture)

from nexus.campo import responsaveis as R
from nexus.campo import visao
from nexus.dados import livros


def _linhas(n, inicio=0):
    return [{"n": i} for i in range(inicio, inicio + n)]


class _Banco:
    """Conta os pedidos ao banco falso (as listagens e as páginas) e deixa trocar a resposta de cada um."""

    def __init__(self, api, trocar=None):
        self.listagens, self.paginas, self._get, self._trocar = 0, [], api.get, trocar
        api.get = self.get

    def get(self, url, params=None, **k):
        if url.endswith("/api/sheets"):
            self.listagens += 1
        elif url.endswith("/rows"):
            self.paginas.append((int(url.rsplit("/", 2)[-2]), int((params or {}).get("offset", 0))))
        r = self._get(url, params=params, **k)
        return self._trocar(url, r) if self._trocar else r


def _contagem(api, livro, aba, n):
    """A listagem dizendo `n` linhas para a aba (a que ela tinha quando foi listada)."""
    sid = api.abas[(livro, aba)]["id"]

    def trocar(url, r):
        if url.endswith("/api/sheets"):
            return Resposta(200, [dict(x, row_count=n) if x["id"] == sid else x for x in r.json()])
        return r
    return trocar


def test_as_paginas_vem_juntas_e_iguais_a_leitura_de_sempre(banco):
    _aba(banco, "livro_grande", "aba", _linhas(2500))
    _aba(banco, "livro_grande", "outra", _linhas(10, 5000))
    sempre = livros.ler(visao._base(), banco, "livro_grande", "aba")
    visao.limpar()
    b = _Banco(banco)
    visao.carregar([("livro_grande", "aba"), ("livro_grande", "outra")])
    assert len(sempre) == 2500 and visao._livro("livro_grande", "aba") == sempre
    assert visao._livro("livro_grande", "outra") == _linhas(10, 5000)
    # uma listagem para as duas abas; as três páginas da grande e a da pequena, e nada de novo no `_livro`
    assert b.listagens == 1 and sorted(o for _sid, o in b.paginas) == [0, 0, 1000, 2000]


def test_a_conta_que_fecha_em_mil_pede_a_pagina_vazia_como_a_leitura_de_sempre(banco):
    _aba(banco, "livro", "aba", _linhas(1000))
    b = _Banco(banco)
    visao.carregar([("livro", "aba")])
    assert visao._livro("livro", "aba") == _linhas(1000) and sorted(o for _s, o in b.paginas) == [0, 1000]


def test_a_aba_que_cresceu_depois_da_listagem_vem_inteira(banco):
    """A listagem diz 1.500 linhas e a aba já tem 3.200 (gravada entre a listagem e a leitura): a última página
    prometida vem cheia, e a leitura segue até a incompleta, como a de sempre."""
    _aba(banco, "livro", "aba", _linhas(3200))
    _Banco(banco, _contagem(banco, "livro", "aba", 1500))
    visao.carregar([("livro", "aba")])
    assert visao._livro("livro", "aba") == _linhas(3200)


def test_a_aba_que_encolheu_para_na_pagina_incompleta(banco):
    _aba(banco, "livro", "aba", _linhas(1200))
    _Banco(banco, _contagem(banco, "livro", "aba", 3000))
    visao.carregar([("livro", "aba")])
    assert visao._livro("livro", "aba") == _linhas(1200)


def test_a_aba_sem_nome_e_a_primeira_do_livro_e_a_que_nao_existe_vem_vazia(banco):
    _aba(banco, "livro_x", "primeira", _linhas(3))
    _aba(banco, "livro_x", "segunda", _linhas(5, 100))
    visao.carregar([("livro_x", None), ("livro_x", "nao_existe"), ("sem_livro", "aba")])
    assert visao._livro("livro_x") == livros.ler(visao._base(), banco, "livro_x") == _linhas(3)
    assert visao._livro("livro_x", "nao_existe") == [] and visao._livro("sem_livro", "aba") == []


def test_a_aba_que_falha_nao_leva_as_outras(banco):
    _aba(banco, "bom", "aba", _linhas(5))
    _aba(banco, "ruim", "aba", _linhas(5))
    sid = banco.abas[("ruim", "aba")]["id"]

    def trocar(url, r):
        if url.endswith(f"/api/sheets/{sid}/rows"):
            return Resposta(500, {})
        return r
    _Banco(banco, trocar)
    with pytest.raises(requests.HTTPError):
        visao.carregar([("bom", "aba"), ("ruim", "aba")])
    assert visao._LIVROS[("bom", "aba")][1] == _linhas(5) and ("ruim", "aba") not in visao._LIVROS


def _aquecer_como_o_servidor():
    """O que o `manter_quente` faz ao subir (a Central, as Rondas, as PT...); depois, a cópia dos livros vence."""
    for f in (visao.rondas, visao.pts, visao.zeladoria, lambda: visao.atencao(), visao.usinas_do_fracttal):
        f()
    visao._LIVROS.clear()


def test_a_pre_leitura_cobre_as_fontes(tela, monkeypatch):
    """Toda aba que as fontes da Visão leem pelo `_livro` vem na pré-leitura. Falhou aqui: a fonte nova lê um livro que
    não está em `responsaveis.pre_leitura`, e a 1ª abertura depois do deploy volta a ler aba por aba. A programação do
    PCM fica fora de propósito: é lida do fim para trás, só as semanas pedidas (`_programacao_recente`)."""
    from nexus.dados import programacao as PG
    _aba(tela, PG.LIVRO, PG.ABA, [{"data_id_semana": 20261012}])        # no banco real ela existe: o caminho de lá
    _aquecer_como_o_servidor()
    fora, original = [], visao._livro

    def livro(nome, aba=None):
        g = visao._LIVROS.get((nome, aba))
        if not (g and time.time() - g[0] < visao.LIVRO_S):
            fora.append((nome, aba))
        return original(nome, aba)
    monkeypatch.setattr(visao, "_livro", livro)
    lei = R.visao_responsaveis()
    assert not lei.erro and not lei.dados["erros"] and fora == []


def test_a_conta_e_a_mesma_com_e_sem_a_pre_leitura(tela, monkeypatch):
    _aquecer_como_o_servidor()
    guardadas = dict(visao._CACHE)
    com = R.visao_responsaveis().dados
    visao._CACHE.clear()
    visao._CACHE.update(guardadas)
    visao._LIVROS.clear()
    monkeypatch.setattr(R, "pre_leitura", lambda: ())
    sem = R.visao_responsaveis().dados
    assert com["usinas"] and com == sem


def test_sem_a_pre_leitura_a_tela_abre_como_antes(tela, monkeypatch):
    """A pré-leitura é atalho: o banco piscou nela, cada fonte lê a sua, como antes (e a que falhar a tela diz)."""
    def piscou(pares):
        raise requests.ConnectionError("o banco piscou")
    monkeypatch.setattr(visao, "carregar", piscou)
    lei = R.visao_responsaveis()
    assert not lei.erro and not lei.dados["erros"]
    assert {u["usina"] for u in lei.dados["usinas"]} == {"Altair", "Brodowski 1", "Coração 1"}


def test_a_programacao_usa_a_listagem_da_pre_leitura(tela):
    from nexus.dados import programacao as PG
    _aba(tela, PG.LIVRO, PG.ABA, [{"data_id_semana": 20261012, "x": 1}, {"data_id_semana": 20261005, "x": 2}])
    b = _Banco(tela)
    meta = {(PG.LIVRO, PG.ABA): (tela.abas[(PG.LIVRO, PG.ABA)]["id"], 2)}
    assert R._programacao_recente({20261012}, meta) == [{"data_id_semana": 20261012, "x": 1}]
    assert b.listagens == 0
    assert R._programacao_recente({20261012}) == [{"data_id_semana": 20261012, "x": 1}] and b.listagens == 1

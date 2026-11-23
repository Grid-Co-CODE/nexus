"""A barra do Nexus Field no Mapa de equipe (23/11/2026; `celulares.adesao`, `equipe_tela._ve_adesao`).

O Levi: "eu queria que tivesse uma barra aqui embaixo já. Do mapa que vai estar contando o percentual de técnicos. Então
vai pegar todos os técnicos, todo o time de campo e vai estar contando quais deles já estão com o Nexus Field instalado e
com todas as autorizações e quais não estão [...] uma visão que só os administradores veem. Administradores e
supervisores responsáveis de usina." As escolhas dele: a conta é de todos os técnicos de campo ativos do cadastro (a
pessoa de teste fica fora); veem o administrador, o supervisor de campo da região e o Responsável O&M de usina; a barra
segue o filtro de supervisor e equipe do mapa.

"Celular pronto" é o que o mapa já mede (`celulares.situacao`). Instalou = a chave do aparelho, o livro do App ou o
celular que já mandou os ajustes. Banco de mentira, pessoas inventadas; nada vai à rede."""
import json
import re

import pytest
from test_equipe_tela import (ADMIN, AGORA, ANDANDO, CENTRO, CHAVE_CADASTRO, EMAIL, EQUIPE_DE, FORA,  # noqa: F401
                              FORA_DO_PILOTO, LESTE, NA_USINA, NOME, NOME_SUP, NOME_USINA, PCM, SEM_PERMISSAO,
                              SEM_POSICAO, SEM_SINAL, SUP_CENTRO, SUP_LESTE, SUP_OESTE, TECNICOS, USINA_B,
                              USINAS_CADASTRO, _entrar, _ficha, _html, banco, pontos, relogio, setor)

from nexus.cadastro import setor_ids as SID
from nexus.campo import visao
from nexus.campo.equipe import TERMO_ATUAL
from nexus.campo.equipe import celulares as CE
from nexus.campo.equipe import servico as S

PRONTO = {"termo": TERMO_ATUAL, "localizacao": "precisa", "tempoTodo": True, "bateriaSemRestricao": True,
          "notificacao": True}


def test_a_conta_separa_pronto_falta_liberar_e_nao_instalou():
    tecnicos = {1: {"nome": "Ana Teste", "equipe": "Centro"}, 2: {"nome": "Bia Teste", "equipe": "Centro"},
                3: {"nome": "Caio Teste", "equipe": "Leste"}, 4: {"nome": "Davi Teste", "equipe": "Leste"},
                5: {"nome": "Eva Teste", "equipe": ""}, 6: {"nome": "Fabi Teste", "equipe": "Leste"},
                7: {"nome": "Gil Teste", "equipe": "Centro"}}
    reg = {1: {"ajustes": PRONTO}, 2: {"ajustes": {**PRONTO, "bateriaSemRestricao": False}}, 3: {"ajustes": None}}
    a = CE.adesao(tecnicos, com_app={5, 6}, com_chave={1, 2, 3, 4}, fora={6}, de=reg.get)
    assert (a["total"], a["n_pronto"], a["n_falta"], a["n_sem"], a["n_instalou"]) == (7, 1, 5, 1, 6)
    assert a["pct"] == 14 and a["pct_instalou"] == 86                 # 1 de 7 e 6 de 7, arredondados
    assert [(t["nome"], t["texto"]) for t in a["pronto"]] == [("Ana Teste", "Celular pronto")]
    assert [(t["nome"], t["texto"]) for t in a["falta"]] == [
        ("Bia Teste", "Falta: bateria sem restrição"), ("Caio Teste", "Versão antiga do app"),
        ("Davi Teste", "Não aceitou o termo ou não abriu o app"),
        ("Eva Teste", "Instalou, mas o celular ainda não se registrou no Nexus"),
        ("Fabi Teste", "Instalou, mas a coleta está parada pelo administrador")]
    assert [(t["nome"], t["equipe"]) for t in a["sem_app"]] == [("Gil Teste", "Centro")]
    vazio = CE.adesao({}, com_app=set(), com_chave=set(), fora=set(), de=lambda p: None)
    assert vazio["total"] == 0 and vazio["pct"] is None


def _linhas(api, livro, aba, linhas):
    """Troca só esta aba (o `_aba` dos testes refaz o livro inteiro)."""
    cab = list(linhas[0])
    api._id(livro, aba)["linhas"] = [{"headers": cab, "values": [l.get(c) for c in cab]} for l in linhas]


RESP = 40
EMAIL_SUP, EMAIL_RESP = "supervisor.centro@gridco.com.br", "responsavel.om@gridco.com.br"


@pytest.fixture
def quadro(app, banco, pontos, setor, monkeypatch):  # noqa: F811
    """O supervisor da Centro (Responsável O&M da Usina Alfa) e a Responsável O&M da Usina Bravo com e-mail (os dois no setor deles, para abrirem o
    mapa), e os celulares: um pronto, um faltando a bateria, um na versão antiga, um com a chave e sem ajustes, um só no
    livro do App e dois sem nada."""
    fichas = [_ficha(pid, nome, equipe_id=EQUIPE_DE[pid]) for pid, nome in NOME.items()]
    fichas += [_ficha(PCM, "Analista Pcm Teste", EMAIL[PCM], vinculo="Colaborador"),
               _ficha(ADMIN, "Administradora Teste", EMAIL[ADMIN], vinculo="Colaborador"),
               _ficha(SUP_CENTRO, NOME_SUP[SUP_CENTRO], EMAIL_SUP, vinculo="Colaborador", equipe_id=None),
               _ficha(SUP_LESTE, NOME_SUP[SUP_LESTE], vinculo="Colaborador", equipe_id=None),
               _ficha(SUP_OESTE, NOME_SUP[SUP_OESTE], vinculo="Colaborador", equipe_id=None),
               _ficha(RESP, "Rita Teste", EMAIL_RESP, vinculo="Colaborador", equipe_id=None)]
    _linhas(banco, "cadastro_nexus", "pessoas", fichas)
    _linhas(banco, "cadastro_nexus", "usinas", [{**u, "responsavel_om_id": RESP} if u["usina_id"] == USINA_B else u
                                                for u in USINAS_CADASTRO])
    visao.limpar()
    setor[EMAIL_SUP] = {"id": SID.SUPERVISAO_CAMPO, "nome": "Supervisão Campo"}
    setor[EMAIL_RESP] = {"id": SID.RESPONSAVEL_UFV, "nome": "Responsáveis UFV"}
    srv = pontos
    srv.chaves_prontas(AGORA)
    for pid in (NA_USINA, ANDANDO, FORA, SEM_SINAL):
        srv.chaveiro.emitir(pid, f"aparelho-{pid}", "NexusField/1.2.3", AGORA)
    srv.celulares = CE.Celulares(None, srv.cofre)     # os pontos do `pontos` vieram sem os ajustes: começa limpo
    srv.celulares.anotar(NA_USINA, PRONTO, AGORA)
    srv.celulares.anotar(ANDANDO, {**PRONTO, "bateriaSemRestricao": False}, AGORA)
    srv.celulares.anotar(FORA, None, AGORA)
    srv._com_app = S._Copia("quem instalou o Nexus Field", 300, lambda: frozenset({SEM_PERMISSAO}))
    return srv


def _barra(html):
    m = re.search(r'<section class="eq-adesao"(.*?)</section>', html, flags=re.S)
    return m.group(1) if m else None


def test_o_administrador_ve_a_barra_com_o_time_inteiro(cliente, quadro):
    _, html = _html(_entrar(cliente, EMAIL[ADMIN], admin=True), query_string=TECNICOS)
    b = _barra(html)
    assert b is not None
    assert "14%" in b and "1 de 7 técnicos de campo" in b
    assert "Celular pronto <b>1</b>" in b and "Instalou, falta liberar <b>4</b>" in b and "Não instalou <b>2</b>" in b
    assert "Falta: bateria sem restrição" in b and "Versão antiga do app" in b
    assert "Instalou, mas o celular ainda não se registrou no Nexus" in b
    assert NOME[SEM_POSICAO] in b and NOME[FORA_DO_PILOTO] in b
    # os segmentos na proporção do time, na ordem do semáforo
    assert re.findall(r'eq-ad-seg--(\w+)" style="flex-grow:(\d+)"', b) == [("ok", "1"), ("alerta", "4"), ("critico", "2")]


def test_o_supervisor_e_o_responsavel_veem_e_os_outros_setores_nao(cliente, quadro):
    for email in (EMAIL_SUP, EMAIL_RESP):
        st, html = _html(_entrar(cliente, email), query_string=TECNICOS)
        assert st == 200 and _barra(html) is not None, email
    # o PCM vê o mapa, mas não a barra
    st, html = _html(_entrar(cliente, EMAIL[PCM]), query_string=TECNICOS)
    assert st == 200 and "eq-ad" not in html
    # o Usinas não tem a barra, nem para o administrador
    _, html = _html(_entrar(cliente, EMAIL[ADMIN], admin=True), query_string={"ver": "usinas"})
    assert "eq-ad" not in html


def test_a_barra_segue_o_filtro_do_mapa(cliente, quadro):
    _entrar(cliente, EMAIL_SUP)
    _, html = _html(cliente, query_string={"equipe": LESTE, **TECNICOS})
    b = _barra(html)
    # a Leste: a Pietra (só no livro do App) e o Paulo (nada)
    assert "0%" in b and "0 de 2 técnicos de campo" in b and "neste filtro" in b
    assert NOME[SEM_PERMISSAO] in b and NOME[SEM_POSICAO] in b and NOME[NA_USINA] not in b
    _, html = _html(cliente, query_string={"supervisor": SUP_CENTRO, **TECNICOS})
    assert "1 de 4 técnicos de campo" in _barra(html)

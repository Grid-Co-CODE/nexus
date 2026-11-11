"""As OS da FAMA no Quadro sem esperar o banco (revisão de 11/11/2026, item 1: a velocidade). O caminho de PRODUÇÃO
(TESTING desligado), com o banco de mentira (`ApiPGFalsa`) e o livro da FAMA gravado pelo caminho da parte A (a carga de
hora em hora, `fama.gerar_fama`, com uma FAMA de mentira).

O que estes testes seguram: o pedido da tela nunca lê o banco; a 1ª visita depois de subir abre sem a FAMA, com o aviso, e
não espera; a cópia vencida volta na hora e a renovação vai por trás, uma de cada vez (o voo único); o livro que não mudou
(o `updated_at` da listagem) não tem as páginas relidas; o livro que mudou é relido; e a falha do banco não trava (com a
cópia boa, ela fica). Projetos, usinas, títulos e pessoas inventados; nenhum teste vai à rede."""
import json
import threading
import time
from datetime import date, datetime, timedelta, timezone

import pytest
import requests
from pg_falso import ApiPGFalsa

from nexus import create_app
from nexus.cadastro.cifra import Cofre, gerar_chave
from nexus.campo import visao
from nexus.dados import fama
from nexus.dados import fato_os_fama as FOF
from nexus.pcm import fama_os as FO
from nexus.pcm import fama_quadro as FQ
from nexus.pcm import quadro as Q
from test_dados_os_fama import FamaFalsa, _os, _semear
from test_pcm_quadro import _r

BASE = "http://pg.falso"
BRT = timezone(timedelta(hours=-3))
CHAVE = gerar_chave()
SENHA = "senha-de-teste-da-copia"
TITULO = "Troca de string box fictícia"
GESTOR = "Pessoa Gestora Fictícia"


def _cadastro(api):
    """O cadastro do banco: a usina 37, ligada ao projeto 10 da FAMA (a decisão da tela) e ao nome dela no Fracttal, com o
    gestor de contrato cifrado na ficha da pessoa (como o banco guarda)."""
    _semear(api, "cadastro_nexus", "usinas", [{"usina_id": 37, "nome": "Usina 1", "cliente_id": 1, "equipe_id": 5,
                                                "gestor_contrato_id": 9}])
    _semear(api, "cadastro_nexus", "de_para", [
        {"usina_id": 37, "sistema": FOF.SISTEMA, "chave_externa": "10", "casou_por": "manual (11/11)"},
        {"usina_id": 37, "sistema": FO.SISTEMA_FRACTTAL, "chave_externa": "Cliente A - Usina 1 - SP", "casou_por": "nome"}])
    _semear(api, "cadastro_nexus", "equipes", [{"equipe_id": 5, "nome": "SP Leste 02"}])
    _semear(api, "cadastro_nexus", "clientes", [{"cliente_id": 1, "nome": "Cliente A"}])
    _semear(api, "cadastro_nexus", "pessoas", [{"pessoa_id": 9, "sensivel_cifrado": Cofre(CHAVE).cifrar(
        json.dumps({"nome": GESTOR, "nome_padrao": "Pessoa Gestora"}), "banco/pessoas/9")}])


def _aberta(i, prevista="2026-10-06"):
    return _os(i, status=("planned", 2), prevista=prevista, fim=None, titulo=TITULO)


def _carga(api, itens):
    """A carga de hora em hora da parte A, com a FAMA de mentira: o livro vai ao banco pelo caminho do servidor."""
    cfg = {"NEXUS_FAMA_CHAVE": "chave-da-fama-de-teste", "GRIDCO_SQL_TOKEN": "token-de-teste",
           "NEXUS_CHAVE_CADASTRO": CHAVE, "GRIDCO_DB_API": BASE}
    r = fama.gerar_fama(cfg, api, fama=FamaFalsa(itens), agora=datetime.now(BRT), forcar=True)
    assert r.get("gravado"), r


class Lento:
    """O banco que só responde quando o teste solta: o pedido da tela não pode esperar por ele."""

    def __init__(self, api):
        self.api, self.solta, self.pedidos = api, threading.Event(), []

    def get(self, url, *a, **k):
        self.pedidos.append(url)
        if not self.solta.wait(10):
            raise requests.ConnectionError("o banco de mentira ficou preso")
        return self.api.get(url, *a, **k)


class Fora:
    def get(self, *a, **k):
        raise requests.ConnectionError("banco de mentira fora do ar")


@pytest.fixture
def producao(monkeypatch):
    monkeypatch.setattr(fama, "_maquina", lambda: "servidor")         # a carga da parte A só grava no servidor
    FQ.limpar()
    visao.limpar()
    api = ApiPGFalsa()
    _cadastro(api)
    _carga(api, [_aberta(1), _os(2, status=("closed", 9))])
    app = create_app({"NEXUS_SECRET_KEY": "chave-de-teste-da-copia", "NEXUS_SENHA_ADMIN": SENHA,
                      "GRIDCO_DB_API": BASE, "NEXUS_CHAVE_CADASTRO": CHAVE})
    app.config["SESSION_COOKIE_SECURE"] = False
    app.extensions["nexus_dados_sessao"] = api
    assert not app.config.get("TESTING")                              # o caminho de produção
    yield app, api
    FQ.esperar(10)
    FQ.limpar()
    visao.limpar()


def _ler(app):
    with app.test_request_context("/"):
        t0 = time.monotonic()
        r = FQ.ler(app.config)
        assert time.monotonic() - t0 < 0.5, "o pedido da tela esperou o banco"
        return r


def _carregada(app):
    _ler(app)
    assert FQ.esperar(10)
    r = _ler(app)
    assert r["estado"] == "ok", r
    return r


def test_a_1a_visita_abre_sem_a_fama_e_nao_espera_o_banco(producao):
    app, api = producao
    lento = Lento(api)
    app.extensions["nexus_dados_sessao"] = lento
    r = _ler(app)
    assert (r["estado"], r["linhas"]) == ("lendo", [])
    assert _ler(app)["estado"] == "lendo"                     # a 2ª visita durante a leitura também não espera
    assert FQ.voltas() == 1                                    # e não abre outra leitura (o voo único)
    lento.solta.set()
    assert FQ.esperar(10)
    r = _ler(app)
    assert r["estado"] == "ok" and [l["fama_os_id"] for l in r["linhas"]] == [1, 2]
    assert r["linhas"][0]["titulo"] == TITULO and r["linhas"][1]["titulo"] is None     # a fechada não é decifrada
    assert r["gerado_em"] and not FO.velho(r["gerado_em"])
    assert r["cadastro"][37]["nomes"] == ["Cliente A - Usina 1 - SP"] and r["cadastro"][37]["responsavel"] == GESTOR


def test_a_copia_vencida_volta_na_hora_e_o_livro_que_nao_mudou_nao_e_relido(producao, monkeypatch):
    app, api = producao
    _carregada(app)
    paginas = api.paginas_lidas
    monkeypatch.setattr(FQ, "COPIA_S", 0)                      # vencida
    lento = Lento(api)
    app.extensions["nexus_dados_sessao"] = lento
    r = _ler(app)
    assert r["estado"] == "ok" and len(r["linhas"]) == 2       # a cópia, na hora; a renovação por trás
    assert _ler(app)["estado"] == "ok" and FQ.voltas() == 2    # uma renovação de cada vez
    lento.solta.set()
    assert FQ.esperar(10)
    assert api.paginas_lidas == paginas                        # o updated_at não mudou: nenhuma página relida
    assert lento.pedidos and all(u.endswith("/api/workbooks") for u in lento.pedidos)


def test_o_livro_que_mudou_e_relido_por_tras(producao, monkeypatch):
    app, api = producao
    _carregada(app)
    _carga(api, [_aberta(1), _os(2, status=("closed", 9)), _aberta(3, prevista="2026-10-07")])
    monkeypatch.setattr(FQ, "COPIA_S", 0)
    assert len(_ler(app)["linhas"]) == 2                       # na hora, a cópia de antes
    assert FQ.esperar(10)
    assert [l["fama_os_id"] for l in _ler(app)["linhas"]] == [1, 2, 3]


def test_a_falha_do_banco_nao_trava_e_a_copia_boa_fica(producao, monkeypatch):
    app, api = producao
    app.extensions["nexus_dados_sessao"] = Fora()
    assert _ler(app)["estado"] == "lendo"
    assert FQ.esperar(10)
    r = _ler(app)
    assert (r["estado"], r["erro"]) == ("erro", "ConnectionError")
    assert FQ.voltas() == 1                                    # a falha não vira laço: a próxima tentativa espera
    # com a cópia boa, a renovação que falha deixa a cópia
    FQ.limpar()
    visao.limpar()
    app.extensions["nexus_dados_sessao"] = api
    _carregada(app)
    monkeypatch.setattr(FQ, "COPIA_S", 0)
    app.extensions["nexus_dados_sessao"] = Fora()
    assert len(_ler(app)["linhas"]) == 2
    assert FQ.esperar(10)
    r = _ler(app)
    assert r["estado"] == "ok" and len(r["linhas"]) == 2


def test_a_tela_abre_na_hora_com_o_aviso_e_depois_mostra_a_os(producao, tmp_path, monkeypatch):
    app, api = producao
    monkeypatch.setattr(Q, "hoje", lambda: date(2026, 10, 7))
    banco = tmp_path / "banco_dados.json"
    sem = {"week": "2026-W41", "label": "Semana 41", "rows": [_r(1, "Segunda-feira", "08:00")], "pendentes": [],
           "dates": {"seg": "05/10", "ter": "06/10", "qua": "07/10", "qui": "08/10", "sex": "09/10"}}
    banco.write_text(json.dumps({"geradoEm": "2026-10-07T12:00:00Z", "semana_ativa": "2026-W41", "semanas": [sem]}),
                     encoding="utf-8")
    app.config.update(NEXUS_PCM_FONTE=str(banco), NEXUS_PCM_TRABALHO=str(tmp_path / "trab"))
    c = app.test_client()
    assert c.post("/entrar", data={"senha": SENHA}).status_code == 302
    html = c.get("/t/pcm/quadro").get_data(as_text=True)
    assert "Lendo as OS da FAMA: recarregue em alguns segundos" in html and "FAMA-1<" not in html
    assert FQ.esperar(10)
    html = c.get("/t/pcm/quadro").get_data(as_text=True)
    assert 'class="q-c-os gc-num">FAMA-1<' in html and "OS da FAMA lidas em" in html and TITULO in html
    assert "Lendo as OS da FAMA" not in html

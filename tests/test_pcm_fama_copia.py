"""As OS da FAMA no Quadro sem esperar o banco (revisão de 11/11/2026, item 1: a velocidade). O caminho de PRODUÇÃO
(TESTING desligado), com o banco de mentira (`ApiPGFalsa`) e o livro da FAMA gravado pelo caminho da parte A (a volta de
10 em 10 minutos, `fama.gerar_fama`, com uma FAMA de mentira).

O que estes testes seguram: o pedido da tela nunca lê o banco; a 1ª visita depois de subir abre sem a FAMA, com o aviso, e
não espera; a cópia vencida volta na hora e a renovação vai por trás, uma de cada vez (o voo único, também com duas
visitas na mesma expiração); o livro que não mudou (o `updated_at` da listagem) não tem as páginas relidas, e sem o
livro no banco a renovação só confere a listagem; o livro que mudou é relido; a subida do Nexus aquece a cópia por trás
(nunca nos testes nem na cópia de prova); e a falha do banco não trava (com a cópia boa, ela fica). Projetos, usinas,
títulos e pessoas inventados; nenhum teste vai à rede."""
import json
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

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
    """A volta de 10 em 10 minutos da parte A, com a FAMA de mentira: o livro vai ao banco pelo caminho do servidor."""
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


def _app(api):
    app = create_app({"NEXUS_SECRET_KEY": "chave-de-teste-da-copia", "NEXUS_SENHA_ADMIN": SENHA,
                      "GRIDCO_DB_API": BASE, "NEXUS_CHAVE_CADASTRO": CHAVE})
    app.config["SESSION_COOKIE_SECURE"] = False
    app.extensions["nexus_dados_sessao"] = api
    assert not app.config.get("TESTING")                              # o caminho de produção
    return app


@pytest.fixture
def producao(monkeypatch):
    monkeypatch.setattr(fama, "_maquina", lambda: "servidor")         # a carga da parte A só grava no servidor
    FQ.limpar()
    visao.limpar()
    api = ApiPGFalsa()
    _cadastro(api)
    _carga(api, [_aberta(1), _os(2, status=("closed", 9))])
    yield _app(api), api
    FQ.esperar(10)
    FQ.limpar()
    visao.limpar()


@pytest.fixture
def sem_livro():
    """O banco antes da 1ª carga do servidor: o cadastro está lá, o livro da FAMA não."""
    FQ.limpar()
    visao.limpar()
    api = ApiPGFalsa()
    _cadastro(api)
    yield _app(api), api
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


def test_duas_visitas_na_mesma_expiracao_abrem_uma_renovacao_so(producao, monkeypatch):
    """Re-revisão de 11/11/2026, item 1: o `start()` da thread roda fora da trava, e a thread criada e ainda não
    começada diz `is_alive()` False. Sem a marca "rodando", posta e tirada dentro da trava, a visita que chegava nesse
    intervalo abria a 2ª renovação da mesma expiração."""
    app, api = producao
    _carregada(app)
    monkeypatch.setattr(FQ, "COPIA_S", 0)
    no_intervalo, solta = threading.Event(), threading.Event()

    class Lerda(threading.Thread):
        """A 1ª renovação para entre soltar a trava e começar de verdade: o intervalo da corrida."""

        def start(self):
            if not no_intervalo.is_set():
                no_intervalo.set()
                assert solta.wait(10)
            super().start()

    monkeypatch.setattr(FQ, "_novo_fio", lambda cfg, a: Lerda(target=FQ._rodar, args=(cfg, a), daemon=True))

    def primeira():
        with app.test_request_context("/"):
            FQ.ler(app.config)
    a = threading.Thread(target=primeira, daemon=True)
    a.start()
    assert no_intervalo.wait(10)                               # a 1ª visita abriu a renovação e ainda não a começou
    assert _ler(app)["estado"] == "ok"                         # a 2ª, na mesma expiração: a cópia, na hora
    solta.set()
    a.join(10)
    assert FQ.esperar(10)
    assert FQ.voltas() == 2                                    # a 1ª leitura e UMA renovação


def test_a_renovacao_que_nem_comeca_nao_prende_a_vez(producao, monkeypatch):
    """A marca "rodando" só sai no fim do `_rodar`: a thread que nem começa (sem recurso para outra) a tira na hora, senão
    a cópia não se renovaria mais até o Nexus reiniciar."""
    app, api = producao

    class Quebrada(threading.Thread):
        def start(self):
            raise RuntimeError("sem thread")

    novo = FQ._novo_fio
    monkeypatch.setattr(FQ, "_novo_fio", lambda cfg, a: Quebrada())
    with app.test_request_context("/"), pytest.raises(RuntimeError):
        FQ.ler(app.config)
    monkeypatch.setattr(FQ, "_novo_fio", novo)
    assert _ler(app)["estado"] == "lendo" and FQ.voltas() == 2   # a próxima visita começa a leitura
    assert FQ.esperar(10) and _ler(app)["estado"] == "ok"


def test_sem_o_livro_no_banco_a_renovacao_so_confere_a_listagem(sem_livro, monkeypatch):
    """Re-revisão de 11/11/2026, item 2: antes da 1ª carga do servidor o livro não existe e o `updated_at` vem None.
    None igual a None é o livro igual até o `COMPLETA_S`: a renovação de 2 em 2 min confere a listagem e não relê as
    outras duas (a do livro e a das abas, dentro do `fama.ler_banco`)."""
    app, api = sem_livro
    r = _carregada(app)
    assert (r["linhas"], r["gerado_em"]) == ([], None)
    monkeypatch.setattr(FQ, "COPIA_S", 0)
    conta = Lento(api)
    conta.solta.set()
    app.extensions["nexus_dados_sessao"] = conta
    _ler(app)
    assert FQ.esperar(10)
    assert len(conta.pedidos) == 1 and conta.pedidos[0].endswith("/api/workbooks"), conta.pedidos
    # passado o COMPLETA_S, a leitura inteira volta (o livro pode ter nascido sem a listagem dizer)
    monkeypatch.setattr(FQ, "COMPLETA_S", 0)
    conta.pedidos.clear()
    _ler(app)
    assert FQ.esperar(10)
    assert any(u.endswith("/api/sheets") for u in conta.pedidos), conta.pedidos
    assert FQ.voltas() == 3


def test_o_nexus_aquece_a_copia_ao_subir_sem_segurar_a_subida(producao):
    """Re-revisão de 11/11/2026, item 3: cada deploy reinicia o Nexus e a cópia começa vazia; sem o aquecimento,
    quem abria o Quadro depois do deploy via "Lendo as OS da FAMA". A subida liga a renovação por trás e segue; a 1ª
    visita já acha a cópia (o aviso fica só para quem chega nos primeiros segundos)."""
    app, api = producao
    lento = Lento(api)
    app.extensions["nexus_dados_sessao"] = lento
    t0 = time.monotonic()
    assert FQ.aquecer_ao_subir(app) is True
    assert time.monotonic() - t0 < 0.5, "o aquecimento segurou a subida"
    assert _ler(app)["estado"] == "lendo" and FQ.voltas() == 1  # nos primeiros segundos, o aviso; sem 2ª leitura
    lento.solta.set()
    assert FQ.esperar(10)
    r = _ler(app)
    assert r["estado"] == "ok" and [l["fama_os_id"] for l in r["linhas"]] == [1, 2]
    assert FQ.voltas() == 1


def test_o_aquecimento_nao_roda_nos_testes_nem_com_a_pre_carga_desligada(producao):
    app, api = producao
    app.config["NEXUS_PRE_CARGA"] = "0"                        # a máquina que desligou a pré-carga
    assert FQ.aquecer_ao_subir(app) is False
    app.config.update(TESTING=True, NEXUS_PRE_CARGA="1")       # o teste nunca aquece, nem com a pré-carga pedida
    assert FQ.aquecer_ao_subir(app) is False
    assert FQ.voltas() == 0


def test_quem_aquece_e_a_subida_do_servidor_e_do_pc_nunca_o_create_app_nem_a_copia_de_prova():
    """O gancho é o do `pre_carga.aquecer_ao_subir`: o `servir.py` e o `app.py` chamam; o `create_app` (os testes) e a
    cópia de prova (`ferramentas/subir_copia_de_prova.py`) não."""
    raiz = Path(__file__).resolve().parents[1]
    for arq in ("servir.py", "app.py"):
        assert "fama_quadro.aquecer_ao_subir(app)" in (raiz / arq).read_text(encoding="utf-8"), arq
    for arq in ("nexus/__init__.py", "ferramentas/subir_copia_de_prova.py"):
        assert "fama_quadro" not in (raiz / arq).read_text(encoding="utf-8"), arq


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
    assert 'class="q-c-os gc-num">FAMA-1<' in html and "livro da FAMA gravado em" in html and TITULO in html
    assert "Lendo as OS da FAMA" not in html


def test_a_releitura_inteira_acompanha_a_volta_da_fama():
    """12/11/2026: a FAMA é lida de 10 em 10 minutos, e a cópia do Quadro é relida inteira no mesmo ritmo (era de hora em
    hora): o que muda só no cadastro chega ao Quadro em até 10 min. A cópia de 2 min continua por cima."""
    from nexus.dados import carga
    assert FQ.COMPLETA_S == carga.FAMA_INTERVALO_S == 600 and FQ.COPIA_S < FQ.COMPLETA_S

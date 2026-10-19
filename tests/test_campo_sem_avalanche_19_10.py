"""O Nexus não trava quando as contas do Campo esfriam (Levi, 19/10/2026: "o nexus travou foi tudo não carrega nada").
O Raio-X das 15:06 mostrou duas Visões do responsável frias calculando ao mesmo tempo, presas lendo o banco (que mora no
mesmo servidor), e o Desempenho esperando a listagem dele. Três causas, três provas:

1. a decisão de PT e a ronda avulsa zeravam TODAS as contas do Campo (`visao.limpar`): agora sai só o que mudou;
2. a mesma conta fria era feita por cada pedido que chegava: agora uma só, e quem chega espera a mesma;
3. as páginas do banco lidas em paralelo têm teto pelo processo inteiro, e não por conta. Banco falso: nada vai à rede."""
import threading
import time

from test_campo_ronda_avulsa import _form, tecnico  # noqa: F401  (tecnico é fixture)
from test_campo_visao import _aba, _entrar_no_fracttal, _jwt, banco  # noqa: F401  (banco é fixture)

from nexus.campo import visao
from nexus.dados import livros


def _esperar(cond, s=5.0):
    fim = time.time() + s
    while not cond() and time.time() < fim:
        time.sleep(0.01)


def test_a_conta_fria_e_feita_uma_vez_so():
    feitas = []

    def calcular():
        feitas.append(1)
        time.sleep(0.3)
        return {"n": len(feitas)}
    visao.limpar()
    saidas = []
    ts = [threading.Thread(target=lambda: saidas.append(visao._ler(("teste_fria",), calcular).dados)) for _ in range(4)]
    try:
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert feitas == [1] and saidas == [{"n": 1}] * 4
    finally:
        visao.limpar()


def test_quem_espera_demais_recebe_o_aviso_e_nao_faz_outra_conta(monkeypatch):
    monkeypatch.setattr(visao, "ESPERA_S", 0.1)
    liberar, feitas = threading.Event(), []

    def calcular():
        feitas.append(1)
        liberar.wait(5)
        return {"ok": True}
    visao.limpar()
    dono = threading.Thread(target=lambda: visao._ler(("teste_lenta",), calcular))
    try:
        dono.start()
        _esperar(lambda: ("teste_lenta",) in visao._EM_CALCULO)
        r = visao._ler(("teste_lenta",), calcular)
        assert r.erro == visao.AVISO_CALCULANDO and feitas == [1]
        liberar.set()
        dono.join()
        assert visao._ler(("teste_lenta",), calcular).dados == {"ok": True} and feitas == [1]
    finally:
        liberar.set()
        visao.limpar()


def test_a_renovacao_por_tras_nao_dobra_a_conta_fria(app):
    visao.limpar()
    try:
        visao._CALCULOS[("k",)] = lambda: {"x": 1}
        visao._EM_CALCULO[("k",)] = {"pronto": threading.Event(), "r": None}       # a conta fria em andamento
        with app.app_context():
            visao._renovar(("k",), app)                    # o manter_quente vê a chave sem cópia
        assert ("k",) not in visao._CACHE and ("k",) not in visao._RENOVANDO
    finally:
        visao.limpar()


def test_as_paginas_do_banco_tem_teto_no_processo(app, banco, monkeypatch):
    for i in range(3):
        _aba(banco, f"livro_{i}", "aba", [{"n": j} for j in range(2500)])
    monkeypatch.setattr(visao, "_VAGAS_BANCO", threading.BoundedSemaphore(2))
    juntas, maximo, trava = [0], [0], threading.Lock()
    original = livros.pagina

    def pagina(*a, **k):
        with trava:
            juntas[0] += 1
            maximo[0] = max(maximo[0], juntas[0])
        try:
            time.sleep(0.02)
            return original(*a, **k)
        finally:
            with trava:
                juntas[0] -= 1
    monkeypatch.setattr(livros, "pagina", pagina)

    def carregar(i):
        with app.app_context():
            visao.carregar([(f"livro_{i}", "aba")])
    # três contas carregando juntas (como três telas frias): o teto vale para as três somadas
    ts = [threading.Thread(target=carregar, args=(i,)) for i in range(3)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert maximo[0] <= 2
    assert all(visao._livro(f"livro_{i}", "aba") == [{"n": j} for j in range(2500)] for i in range(3))


def test_decidir_uma_pt_nao_zera_as_outras_telas(app, banco, logado):
    visao.rondas()
    visao.zeladoria()
    visao.atencao()
    antes = dict(visao._CACHE)
    assert ("visao_pt",) in antes and ("visao_rondas",) in antes
    _entrar_no_fracttal(app, logado, _jwt())
    r = logado.post("/os/_nexus/pt/PT-1/decidir", data={"decisao": "de_acordo"})
    assert r.status_code == 302 and "nexus_pt_decisoes" in banco.workbooks           # a decisão foi gravada
    # a conta das PT foi refeita com o livro do App de agora; as outras telas seguem com as mesmas cópias
    assert visao._CACHE[("visao_pt",)] is not antes[("visao_pt",)]
    for k, v in antes.items():
        if k != ("visao_pt",):
            assert visao._CACHE.get(k) is v, k
    assert not visao._VENCIDAS


def test_a_ronda_avulsa_refaz_as_rondas_na_hora_e_o_resto_por_tras(tecnico, banco):
    visao.rondas()
    visao.zeladoria()
    visao.atencao()
    antes = dict(visao._CACHE)
    central = next(k for k in antes if k[0] == "visao_atencao")
    assert tecnico.post("/t/campo/rondas/avulsa", data=_form()).status_code == 303
    assert ("visao_rondas",) not in visao._CACHE                      # quem lançou se vê nas Rondas na próxima visita
    assert visao._CACHE[("visao_zeladoria",)] is antes[("visao_zeladoria",)]          # não conta ronda: intacta
    assert visao._CACHE[central] is antes[central] and central in visao._VENCIDAS     # a cópia segue, refeita por trás
    # a visita seguinte recebe a cópia na hora e pede a renovação (no teste, feita na hora; no servidor, por trás)
    assert visao.atencao() is antes[central]
    assert central not in visao._VENCIDAS and visao._CACHE[central] is not antes[central]
    assert any(r.get("avulsa") for r in visao.rondas().dados["todas"])

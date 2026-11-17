"""A conta da fila da Aprovação sem repetir a fila inteira a cada página (Desempenho, 16/11/2026).

O caso: no reinício das 21:13 de 16/11/2026, lido thread por thread, a conta da fila da Aprovação (`nexus-fila-conta`)
usou um núcleo inteiro por 22 s, e foi nela que o Raio-X voltou a abrir em 7 s. Medido no PC com a fila de verdade (6.511
tarefas): a regra copiada do App devolve no máximo 200 linhas por chamada e percorre a fila INTEIRA em cada uma; a
`fila_toda` a chamava 33 vezes (uma por página), 215 mil passagens por tarefa para 6.511 tarefas, 8,4 s de processador
com tudo quente. A regra copiada não muda (`regras_app.py` não se edita): a fila passa a ser entregue a ela em pedaços de
uma página, cada tarefa uma vez, e o que ela relia a cada chamada (o cadastro, as notas, as rondas) vale pela conta
inteira. Na fila de verdade: as mesmas 6.425 linhas, na mesma ordem, em 0,6 s.

Aqui a regra do App é a de verdade, sobre uma fila de mentira com mais de duas páginas."""
import pytest
from test_campo_aprovacao import _nota, _os  # noqa: F401
from test_campo_regras_app import TabelaFalsa

from nexus.campo import aprovacao, leitura, regras_app, tabelas

P = {"dias": "3650"}


@pytest.fixture
def fila(monkeypatch):
    """450 tarefas (3 páginas), com a mesma tarefa repetida em páginas diferentes, uma sem data de fim, uma fora da
    janela de 10 anos e muitos empates no tempo de espera."""
    import time
    linhas = [_os(15000 + i, (i * 7) % 40 + 1, f"Técnico {i % 9}") for i in range(450)]
    linhas.insert(260, dict(linhas[10]))                     # a mesma tarefa de novo, 250 posições depois
    linhas.insert(30, dict(_os(19001, 5), final_date=""))    # sem data de fim: a regra do App a deixa de fora
    linhas.insert(300, _os(19002, 4000))                     # fora da janela
    linhas.insert(420, dict(linhas[5], personnel_description="Outro Nome"))   # a repetida com outro técnico: vale a 1ª
    dados = {"qualidadelog": [_nota(15007, 96), _nota(15300, 71)]}
    tabelas.usar_fornecedor(lambda nome: TabelaFalsa(dados.setdefault(nome, [])))
    monkeypatch.setattr(regras_app, "_FILA_CACHE", {"t": time.time(), "ts": time.time(), "linhas": linhas})
    monkeypatch.setattr(regras_app, "FILA_TTL_S", 10 ** 9)
    monkeypatch.setattr(aprovacao, "_PRONTA", {})
    monkeypatch.setattr(aprovacao, "_ESTADO", dict(aprovacao._ESTADO, lendo=True))     # ninguém relê a fila aqui
    leitura.limpar()
    yield linhas
    tabelas.usar_fornecedor(None)
    leitura.limpar()


def _pagina_a_pagina():
    """A conta de antes: uma chamada por página, cada uma sobre a fila inteira."""
    pag, todas, primeira = 1, [], None
    while True:
        d = regras_app._fila_supervisao(aprovacao._Pedido({**P, "pag": str(pag), "tam": "200"}), aprovacao.ESCOPO_ADMIN)
        primeira = primeira or d
        todas += d.get("linhas") or []
        if pag >= int((d.get("pagina") or {}).get("paginas") or 1):
            break
        pag += 1
    return primeira, todas


def test_em_pedacos_saem_as_mesmas_linhas_na_mesma_ordem(app, fila):
    with app.test_request_context():
        ref_primeira, ref = _pagina_a_pagina()
        primeira, todas = aprovacao._linhas_da_fila(P, aprovacao.ESCOPO_ADMIN)
    assert len(ref) == 450 and int(ref_primeira["pagina"]["paginas"]) == 3          # a fila de mentira tem 3 páginas
    assert todas == ref                                                             # as mesmas linhas, na mesma ordem
    for campo in ("janela", "resumo", "baldes", "sem_cadastro"):
        assert primeira.get(campo) == ref_primeira.get(campo), campo
    # a repetida entra uma vez, com o técnico da 1ª ocorrência; a sem data e a fora da janela não entram
    assert sum(1 for x in todas if x["os"] == "15005") == 1
    assert next(x for x in todas if x["os"] == "15005")["tecnico"] != "Outro Nome"
    assert not [x for x in todas if x["os"] in ("19001", "19002")]
    # e, acabada a conta, a regra volta a ver a fila inteira nesta thread
    assert len(regras_app._fila_bruta()) == len(fila)


def test_cada_tarefa_passa_pela_regra_do_app_no_maximo_duas_vezes(app, fila, monkeypatch):
    """Uma passada inteira (o resumo e os baldes da fila toda) e uma em pedaços (as linhas): antes, uma por página."""
    passagens = []
    real = regras_app._txt_tarefa
    monkeypatch.setattr(regras_app, "_txt_tarefa", lambda w: passagens.append(1) or real(w))
    with app.test_request_context():
        _pagina_a_pagina()
        antes = len(passagens)
        del passagens[:]
        aprovacao._linhas_da_fila(P, aprovacao.ESCOPO_ADMIN)
    assert antes >= 3 * 450                                   # 3 páginas x a fila inteira
    assert len(passagens) <= 2 * 452, f"{len(passagens)} passagens para 450 tarefas"


def test_o_que_a_regra_relia_a_cada_chamada_vale_pela_conta_inteira(app, fila, monkeypatch):
    chamadas = {"notas": 0, "rondas": 0, "cadastro": 0}
    reais = dict(aprovacao._ORIGINAIS)                        # as da cópia, por baixo do que a Aprovação embrulhou
    # por baixo do que a Aprovação embrulhou: conta quantas vezes a leitura de verdade roda
    monkeypatch.setattr(aprovacao, "_ORIGINAIS", {
        "_fila_bruta": reais["_fila_bruta"],
        "_qlog_por_os": lambda *a: chamadas.__setitem__("notas", chamadas["notas"] + 1) or reais["_qlog_por_os"](*a),
        "_rondas_os_por_folio": lambda *a: (chamadas.__setitem__("rondas", chamadas["rondas"] + 1)
                                            or reais["_rondas_os_por_folio"](*a)),
        "_pessoa_por_nome": lambda *a: (chamadas.__setitem__("cadastro", chamadas["cadastro"] + 1)
                                        or reais["_pessoa_por_nome"](*a)),
    })
    with app.test_request_context():
        aprovacao._linhas_da_fila(P, aprovacao.ESCOPO_ADMIN)
    assert chamadas == {"notas": 1, "rondas": 1, "cadastro": 1}, chamadas
    # fora da conta inteira (uma tela que filtra, o App), cada chamada lê como sempre: nada fica guardado
    with app.test_request_context():
        regras_app._fila_supervisao(aprovacao._Pedido({**P, "pag": "1", "tam": "50"}), aprovacao.ESCOPO_ADMIN)
        regras_app._fila_supervisao(aprovacao._Pedido({**P, "pag": "1", "tam": "50"}), aprovacao.ESCOPO_ADMIN)
    assert chamadas == {"notas": 3, "rondas": 3, "cadastro": 3}, chamadas


def test_a_fila_de_uma_pagina_so_faz_uma_chamada(app, fila, monkeypatch):
    del regras_app._FILA_CACHE["linhas"][150:]                # 150 tarefas: cabem numa página
    chamadas = []
    real = regras_app._fila_supervisao
    monkeypatch.setattr(regras_app, "_fila_supervisao", lambda req, esc: chamadas.append(req.params.get("pag")) or real(req, esc))
    with app.test_request_context():
        primeira, todas = aprovacao._linhas_da_fila(P, aprovacao.ESCOPO_ADMIN)
    assert chamadas == ["1"] and len(todas) == len(primeira["linhas"]) > 100


def test_o_pedaco_e_so_de_quem_esta_fazendo_a_conta(app, fila):
    """Enquanto a conta inteira entrega a fila em pedaços, outra thread (uma tela, a releitura) vê a fila inteira."""
    import threading
    vistos = []
    token = aprovacao._PEDACO.set(regras_app._FILA_CACHE["linhas"][:7])
    try:
        assert len(regras_app._fila_bruta()) == 7
        t = threading.Thread(target=lambda: vistos.append(len(regras_app._fila_bruta())))
        t.start()
        t.join(10)
    finally:
        aprovacao._PEDACO.reset(token)
    assert vistos == [len(regras_app._FILA_CACHE["linhas"])] and len(regras_app._fila_bruta()) == vistos[0]


def test_a_tela_recebe_a_fila_inteira_pela_conta_em_pedacos(app, fila, monkeypatch):
    passagens = []
    real = regras_app._txt_tarefa
    with app.test_request_context():
        ref = [x["id_wt"] for x in _pagina_a_pagina()[1]]
        monkeypatch.setattr(regras_app, "_txt_tarefa", lambda w: passagens.append(1) or real(w))
        r = aprovacao.fila_toda(aprovacao.FILA_INTEIRA)
    linhas = r.dados["linhas"]
    assert [x["id_wt"] for x in linhas] == ref and r.dados["resumo"]["tarefas"] == 450
    assert len(passagens) <= 2 * 452, f"a tela fez {len(passagens)} passagens para 450 tarefas"
    assert all("usina_fx" in x and "criada" in x and "exec_s" in x for x in linhas)     # o que a tela soma a cada linha


def test_se_os_pedacos_nao_batem_com_a_regra_vale_o_pagina_a_pagina(app, fila, monkeypatch, caplog):
    """A regra do App pode mudar de um jeito que os pedaços não acompanham (uma conta que dependa das outras tarefas da
    fila): se o total em pedaços não é o que a própria regra contou na fila inteira, a conta volta ao caminho de antes."""
    import logging
    real = regras_app._fila_supervisao

    def muda_em_pedacos(req, esc):
        d = real(req, esc)
        if aprovacao._PEDACO.get() is not None and d.get("linhas"):
            d = dict(d, linhas=d["linhas"][1:])               # em pedaços, a regra "perde" uma linha por chamada
        return d
    with app.test_request_context():
        ref_primeira, ref = _pagina_a_pagina()
        monkeypatch.setattr(regras_app, "_fila_supervisao", muda_em_pedacos)
        with caplog.at_level(logging.WARNING):
            primeira, todas = aprovacao._linhas_da_fila(P, aprovacao.ESCOPO_ADMIN)
    assert todas == ref and primeira["resumo"] == ref_primeira["resumo"]
    assert any("página a página" in r.getMessage() for r in caplog.records)


def test_a_copia_recarregada_ganha_o_embrulho_de_novo(app, monkeypatch):
    """A `leitura.limpar_cache` recarrega a cópia das regras (os testes a chamam entre um e outro), e a cópia nova vinha
    sem as quatro funções embrulhadas: a conta voltava, calada, a percorrer a fila inteira em cada pedaço e caía no
    caminho de antes. Achado pela suíte inteira em 16/11/2026 (sozinho, este arquivo passava)."""
    import importlib
    import time
    leitura.limpar_cache()
    assert all(getattr(getattr(regras_app, n), "_nexus_embrulho", False) for n in ("_fila_bruta",) + aprovacao._LEMBRADAS)
    # e mesmo recarregada por fora, a conta inteira refaz o embrulho antes de começar
    importlib.reload(regras_app)
    assert not getattr(regras_app._fila_bruta, "_nexus_embrulho", False)
    dados = {"qualidadelog": []}
    tabelas.usar_fornecedor(lambda nome: TabelaFalsa(dados.setdefault(nome, [])))
    linhas = [_os(15000 + i, i % 30 + 1) for i in range(450)]
    monkeypatch.setattr(regras_app, "_FILA_CACHE", {"t": time.time(), "ts": time.time(), "linhas": linhas})
    monkeypatch.setattr(regras_app, "FILA_TTL_S", 10 ** 9)
    passagens = []
    real = regras_app._txt_tarefa
    monkeypatch.setattr(regras_app, "_txt_tarefa", lambda w: passagens.append(1) or real(w))
    try:
        with app.test_request_context():
            _primeira, todas = aprovacao._linhas_da_fila(P, aprovacao.ESCOPO_ADMIN)
    finally:
        tabelas.usar_fornecedor(None)
    assert len(todas) == 450 and len(passagens) <= 2 * 450
    assert getattr(regras_app._fila_bruta, "_nexus_embrulho", False)
    # o embrulho de novo não empilha: embrulhar duas vezes deixa uma camada só
    antes = regras_app._fila_bruta
    aprovacao._embrulhar_a_copia()
    assert regras_app._fila_bruta is antes
    for nome in ("_fila_bruta",) + aprovacao._LEMBRADAS:                    # por baixo segue a função da cópia
        assert not getattr(aprovacao._ORIGINAIS[nome], "_nexus_embrulho", False), nome
    assert len(regras_app._fila_bruta()) == 450                             # e a chamada segue respondendo

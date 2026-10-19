"""O filtro da Visão do responsável não espera o banco (Levi, 19/10/2026: "quando eu já filtrei o responsável e vou
filtrar o cliente carrega de novo, como se fizesse requisições novas e acaba demorando para carregar"). Cada filtro é um
pedido novo; a conta da tela já vem da memória, mas o pedido relia duas cópias curtas quando venciam (quem olhava a tela
mais de um minuto antes de filtrar): as ocorrências abertas (1 min) e o de-para dos sites do Fracttal (2 min), +0,9 a
1,5 s medidos no banco real. Agora o site vem na conta e as ocorrências voltam na hora, relidas por trás."""
from test_campo_pre_leitura_19_10 import _Banco
from test_campo_responsaveis import tela  # noqa: F401  (fixture)
from test_campo_visao import banco  # noqa: F401  (fixture)

from nexus.campo import ocorrencias as O
from nexus.campo import visao


def test_as_ocorrencias_voltam_na_hora_e_se_releem_por_tras(app, monkeypatch):
    lidas = []
    monkeypatch.setattr(O.livros, "ler", lambda *a, **k: lidas.append(1) or [{"x": len(lidas)}])
    monkeypatch.setattr(O, "_banco", lambda: ("http://pg.falso", None))
    with app.app_context():
        O.limpar()
        try:
            assert O.ler_sem_esperar()["eventos"] == [{"x": 1}]                 # sem cópia (1ª vez): lê agora
            assert O.ler_sem_esperar()["eventos"] == [{"x": 1}] and len(lidas) == 1      # cópia nova: nada
            O._CACHE["livro"]["lido_em"] -= O.TTL_S + 1                          # venceu
            # a cópia vencida volta e a releitura vai por trás (no teste, na hora); a próxima já tem a nova
            assert O.ler_sem_esperar()["eventos"] == [{"x": 1}] and len(lidas) == 2
            assert O.ler_sem_esperar()["eventos"] == [{"x": 2}] and not O._RELENDO[0]
            # uma releitura por vez
            O._CACHE["livro"]["lido_em"] -= O.TTL_S + 1
            O._RELENDO[0] = True
            assert O.ler_sem_esperar()["eventos"] == [{"x": 2}] and len(lidas) == 2
        finally:
            O._RELENDO[0] = False
            O.limpar()


def test_a_releitura_que_falha_fica_com_a_copia_boa(app, monkeypatch):
    monkeypatch.setattr(O, "_banco", lambda: ("http://pg.falso", None))
    with app.app_context():
        O.limpar()
        try:
            monkeypatch.setattr(O.livros, "ler", lambda *a, **k: [{"x": 1}])
            O.ler_sem_esperar()
            O._CACHE["livro"]["lido_em"] -= O.TTL_S + 1

            def fora(*a, **k):
                raise ConnectionError("banco fora")
            monkeypatch.setattr(O.livros, "ler", fora)
            assert O.ler_sem_esperar()["eventos"] == [{"x": 1}]
            assert O._CACHE["livro"]["eventos"] == [{"x": 1}] and "ConnectionError" in O._CACHE["falha"]["erro"]
        finally:
            O.limpar()


def test_o_filtro_nao_espera_o_banco(tela, logado, monkeypatch):
    assert logado.get("/t/campo/responsaveis?modo=geral&responsavel=*").status_code == 200    # a conta pronta
    visao._LIVROS.clear()                                  # a cópia dos livros (2 min) venceu
    O._CACHE["livro"]["lido_em"] -= O.TTL_S + 1             # e a das ocorrências (1 min)
    por_tras = []
    monkeypatch.setattr(O, "_reler_por_tras", lambda: por_tras.append(1))   # no servidor, outra thread
    b = _Banco(tela)
    r = logado.get("/t/campo/responsaveis?modo=geral&responsavel=Ciclano+Chefe&cliente=Thopen")
    assert r.status_code == 200 and b.listagens == 0 and b.paginas == [] and por_tras == [1]

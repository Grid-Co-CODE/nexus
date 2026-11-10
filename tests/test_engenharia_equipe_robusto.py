"""O Quadro da equipe não some com o 429 nem com o deploy (Desempenho, 10/11/2026).

O caso (Levi, 10/11: "em engenharia > quadro de equipe temos frequentemente esses problemas com o Fractall"): o quadro
zerado, "lidas às —", "Nenhum responsável da engenharia achado no Fracttal" e o aviso "O Fracttal recusou a leitura
agora (HTTP 429)". Medido no livro dos pedidos ao Fracttal: o laço do quadro pede 250 a 570 por dia (~3% do Nexus) e é
recusado em 6% a 15% deles; quem enche a cota é o resto do Nexus e o App de Campo. Mas a leitura era tudo ou nada (um 429
em qualquer página de qualquer pessoa jogava fora a leitura inteira) e morava só na memória (cada deploy zerava o quadro
até uma leitura inteira dar certo, e a 1ª visita esperava por ela). Agora cada pessoa é lida à parte (a recusada fica com
a leitura anterior dela, e o aviso diz quem) e a última leitura vai ao disco, de volta no 1º uso depois do reinício com a
hora que tinha. Nomes fictícios.
"""
from urllib.parse import unquote

from test_engenharia_equipe import PESSOAS, _w

from nexus.campo import fracttal
from nexus.engenharia import os_equipe as E
from nexus.performance import quadro_equipe as Q


class _Rest:
    """O REST de mentira: as OS de cada pessoa pelo trecho do nome; quem está em `recusar` leva o 429."""

    def __init__(self):
        self.oss = {"Ana": [_w("100", 1, pid=1, personnel_description="Ana  Teste")],
                    "Bruno": [_w("200", 1, pid=2, personnel_description="Bruno Exemplo")]}
        self.recusar = set()

    def __call__(self, path):
        if path.startswith("personnel?"):
            return {"data": PESSOAS}
        trecho = unquote(path.split("personnel_description=", 1)[1].split("&", 1)[0])
        if any(r in trecho for r in self.recusar):
            raise fracttal.Recusado("o Fracttal recusou por excesso de pedidos (HTTP 429)")
        return {"data": [w for ws in self.oss.values() for w in ws if trecho in w["personnel_description"]]}


def _preparar(app, monkeypatch, tmp_path=None):
    rest = _Rest()
    monkeypatch.setattr(E, "_ler_fracttal", rest)
    monkeypatch.setattr(E.time, "sleep", lambda s: None)
    app.config["NEXUS_ENGENHARIA_RESPONSAVEIS"] = "Ana Teste;Bruno Exemplo"
    if tmp_path is not None:
        app.config["NEXUS_DADOS"] = str(tmp_path)
    monkeypatch.setattr(Q, "_setores", lambda: {"decisoes": [1]})
    monkeypatch.setattr(Q, "ids_do_setor", lambda st: ["1", "2"])
    E.limpar()
    Q.limpar()
    return rest


def _oss(est):
    return sorted(o["os"] for o in est["os"])


def test_o_429_de_uma_pessoa_nao_derruba_a_leitura_das_outras(app, monkeypatch):
    rest = _preparar(app, monkeypatch)
    for quadro in (E, Q):
        quadro._reler(app)
        assert _oss(quadro._EST) == ["100", "200"] and not quadro._EST["erro"]
        lida = quadro._EST["ts"]
        rest.oss["Ana"].append(_w("101", 1, pid=1, personnel_description="Ana  Teste"))     # a OS nova da Ana
        rest.recusar = {"Bruno"}                                                         # e o 429 no Bruno
        quadro._reler(app)
        assert _oss(quadro._EST) == ["100", "101", "200"], f"{quadro.__name__}: a leitura da Ana se perdeu no 429 do Bruno"
        assert "Bruno" in quadro._EST["erro"] and quadro._EST["erro_em"]
        assert quadro._EST["ts"] == lida                 # "lidas às" segue a hora da última leitura inteira
        rest.oss["Ana"].pop()
        rest.recusar = set()
    E.limpar()
    Q.limpar()


def test_a_leitura_volta_do_disco_depois_do_reinicio(app, monkeypatch, tmp_path):
    rest = _preparar(app, monkeypatch, tmp_path)
    for quadro in (E, Q):
        quadro._reler(app)
        lida = quadro._EST["ts"]
        quadro.limpar()                                   # o deploy: a memória vazia
        rest.recusar = {"Ana", "Bruno"}                   # e o Fracttal recusando tudo
        with app.test_request_context():
            d = quadro.dados()
        assert sorted(o["os"] for o in d["os"]) == ["100", "200"], f"{quadro.__name__}: o reinício zerou o quadro"
        assert d["lido"] == lida and [p["id"] for p in d["equipe"]]
        rest.recusar = set()
    E.limpar()
    Q.limpar()


def test_a_1a_visita_depois_do_reinicio_abre_com_a_copia(app, logado, monkeypatch, tmp_path):
    rest = _preparar(app, monkeypatch, tmp_path)
    E._reler(app)
    E.limpar()
    rest.recusar = {"Ana", "Bruno"}
    html = logado.get("/t/engenharia/equipe").get_data(as_text=True).replace("'", '"')
    assert '"os": "100"' in html and '"os": "200"' in html, "a 1ª visita depois do deploy abriu o quadro vazio"
    assert "lidas às —" not in html
    E.limpar()


def test_a_1a_releitura_do_boot_parte_da_copia_do_disco(app, monkeypatch, tmp_path):
    """O boot pede a releitura (`nexus/engenharia/__init__.py`, 210 s depois de subir) antes de qualquer visita: quem o
    Fracttal recusar nela fica com a leitura do disco, não vazio."""
    rest = _preparar(app, monkeypatch, tmp_path)
    for quadro in (E, Q):
        quadro._reler(app)
        quadro.limpar()
        rest.recusar = {"Bruno"}
        quadro.pedir_releitura(app)
        assert _oss(quadro._EST) == ["100", "200"], f"{quadro.__name__}: a releitura do boot perdeu o Bruno"
        rest.recusar = set()
    E.limpar()
    Q.limpar()

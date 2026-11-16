"""O novo da Sala de controle da Performance no sino do topo (16/11/2026).

Levi: a ocorrência nova chega nas notificações, agrupada POR USINA. A regra do que é novo é da plataforma; o Nexus
pergunta pela ponte e nunca segura a página por isso. Nenhum teste vai à rede; pessoas e usinas são de mentira.
"""
import pytest

from nexus.performance import ponte, sala_novas


@pytest.fixture(autouse=True)
def _limpo():
    sala_novas.limpar()
    yield
    sala_novas.limpar()


CFG = {"NEXUS_PLATAFORMA_URL": "http://plataforma.falsa:5050", "NEXUS_PLATAFORMA_TOKEN": "chave-de-teste"}
DADO = {"total": 5, "n_usinas": 2, "desde": "2026-11-14 18:00",
        "usinas": [{"usina": "Usina Teste 1", "strings": 3, "inversores": 2, "trackers": 0},
                   {"usina": "Usina Teste 2", "strings": 0, "inversores": 0, "trackers": 2}]}


class _Resp:
    def __init__(self, status=200, corpo=None, marca="1"):
        self.status_code, self._c = status, corpo
        self.headers = {"X-Nexus-Leitura-Ok": marca} if marca else {}

    def json(self):
        return self._c


def test_le_pela_ponte_dizendo_a_pessoa(monkeypatch):
    visto = {}

    def enviar(**pedido):
        visto.update(pedido)
        return _Resp(corpo={"ok": True, **DADO})
    monkeypatch.setattr(ponte, "enviar", enviar)
    d = sala_novas.ler(CFG, "pessoa@exemplo.test")
    assert d == DADO
    assert "/api/sala/novas" in str(visto) and "pessoa%40exemplo.test" in str(visto) or "pessoa@exemplo.test" in str(visto)


@pytest.mark.parametrize("resp", [_Resp(status=503, corpo={}), _Resp(corpo={"ok": True, **DADO}, marca=""),
                                  _Resp(corpo={"ok": False}), _Resp(corpo=[1, 2])])
def test_resposta_que_nao_serve_vira_nada(monkeypatch, resp):
    monkeypatch.setattr(ponte, "enviar", lambda **p: resp)
    assert sala_novas.ler(CFG, "pessoa@exemplo.test") is None
    assert sala_novas.ler({}, "pessoa@exemplo.test") is None                 # ponte desligada: nem pergunta


def test_o_sino_usa_a_copia_e_nao_pergunta_de_novo_a_cada_pagina():
    chamadas = []

    def leitor(cfg, email):
        chamadas.append(email)
        return DADO
    assert sala_novas.do_sino(CFG, "Pessoa@Exemplo.test", leitor=leitor, em_fundo=False) == DADO
    assert sala_novas.do_sino(CFG, "pessoa@exemplo.test", leitor=leitor, em_fundo=False) == DADO
    assert chamadas == ["pessoa@exemplo.test"]                               # a 2ª página saiu da cópia
    # sem e-mail (o administrador pela senha) não há de quem perguntar
    assert sala_novas.do_sino(CFG, "", leitor=leitor, em_fundo=False) is None
    assert sala_novas.do_sino(CFG, "admin@nexus.invalid", leitor=leitor, em_fundo=False) is None
    assert chamadas == ["pessoa@exemplo.test"]


def test_a_plataforma_fora_nao_derruba_e_guarda_o_que_havia(monkeypatch):
    estado = {"fora": False, "n": 0}

    def leitor(cfg, email):
        estado["n"] += 1
        if estado["fora"]:
            raise RuntimeError("plataforma fora")
        return DADO
    assert sala_novas.do_sino(CFG, "pessoa@exemplo.test", leitor=leitor, em_fundo=False) == DADO
    estado["fora"] = True
    monkeypatch.setattr(sala_novas, "VALIDADE_S", -1)                         # a cópia venceu
    assert sala_novas.do_sino(CFG, "pessoa@exemplo.test", leitor=leitor, em_fundo=False) == DADO   # vale a última boa
    antes = estado["n"]
    assert sala_novas.do_sino(CFG, "pessoa@exemplo.test", leitor=leitor, em_fundo=False) == DADO
    assert estado["n"] == antes                                               # falhou há pouco: espera para tentar de novo


def test_em_fundo_a_primeira_pagina_nao_espera(monkeypatch):
    import threading
    solta = threading.Event()

    def leitor(cfg, email):
        solta.wait(5)
        return DADO
    assert sala_novas.do_sino(CFG, "pessoa@exemplo.test", leitor=leitor) is None      # não esperou a plataforma
    assert sala_novas.do_sino(CFG, "pessoa@exemplo.test", leitor=leitor) is None      # nem disparou outra leitura junto
    solta.set()
    for _ in range(100):
        if sala_novas._COPIA.get("pessoa@exemplo.test"):
            break
        threading.Event().wait(0.05)
    assert sala_novas.do_sino(CFG, "pessoa@exemplo.test", leitor=leitor) == DADO


def test_o_sino_do_topo_mostra_por_usina_para_quem_tem_a_tela(app, monkeypatch):
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(logado=True, admin=True, usuario={"email": "pessoa@exemplo.test", "nome": "Pessoa"}, casca_codigo="x")
    monkeypatch.setattr(sala_novas, "do_sino", lambda cfg, email, **k: DADO if email == "pessoa@exemplo.test" else None)
    html = c.get("/").get_data(as_text=True)
    assert "2 usinas com ocorrência nova na Performance" in html
    assert "Usina Teste 1" in html and "3 strings em 2 inversores" in html and "2 trackers" in html
    assert "/t/performance/sala-de-controle" in html
    # sem novidade, o bloco não aparece
    monkeypatch.setattr(sala_novas, "do_sino", lambda cfg, email, **k: None)
    assert "ocorrência nova na Performance" not in c.get("/").get_data(as_text=True)

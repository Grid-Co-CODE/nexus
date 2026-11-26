"""As PTs esperando o De acordo no sino do topo (26/11/2026). Levi: "além de receber o e-mail, ele também tem que receber
notificação no Nexus"; "a notificação do Nexus pode subir".

O que estes testes seguram: quem pode assinar (o Responsável UFV da ficha da usina, o Supervisor de Campo da região, o
gestor de contrato) vê no sino as PTs dele, com o link do card de assinar; quem não pode, não vê; o administrador pela
senha (sem pessoa) não tem; o COS só no plantão; a PT que o Nexus já decidiu sai. Banco falso e nomes de mentira."""
import pytest

from nexus.campo import decisao_pt
from nexus.campo import pt_sino as PS
from test_campo_pt_assinar import CARD_PT1, RESP, _sessao, com_responsavel  # noqa: F401 (fixture)
from test_campo_visao import banco  # noqa: F401 (fixture)


@pytest.fixture(autouse=True)
def _sem_copia():
    PS.limpar()
    yield
    PS.limpar()


def _sino(html: str) -> str:
    i = html.index('aria-label="Notificações"')
    return html[i:html.index("</details>", i)]


def test_o_responsavel_ufv_ve_as_pts_dele_no_sino(app, com_responsavel):
    html = _sessao(app, RESP, "Responsável Exemplo").get("/").get_data(as_text=True)
    sino = _sino(html)
    assert "As PTs esperando o seu De acordo" in html
    assert f'href="{CARD_PT1}"' in sino and "PT PT-1 · Altair" in sino and "Esperando o seu De acordo há" in sino
    assert ">Assinar</a>" in sino


def test_quem_nao_pode_assinar_nao_ve_pt_no_sino(app, com_responsavel):
    html = _sessao(app, "tecnico@exemplo.test", "Técnico Exemplo").get("/").get_data(as_text=True)
    assert "/assinar" not in (html[html.index('aria-label="Notificações"'):] if 'aria-label="Notificações"' in html else "")
    assert PS.para_o_sino("tecnico@exemplo.test") == []


def test_o_administrador_pela_senha_nao_tem_pt_no_sino(com_responsavel, logado):
    html = logado.get("/").get_data(as_text=True)
    assert "Esperando o seu De acordo" not in html


def test_o_cos_so_no_plantao(app, com_responsavel, monkeypatch):
    monkeypatch.setattr(decisao_pt, "_do_setor_cos", lambda email: email == "cos@exemplo.test")
    monkeypatch.setattr(decisao_pt, "cos_no_plantao", lambda agora=None: False)
    with app.test_request_context("/"):
        assert PS.para_o_sino("cos@exemplo.test") == []
        PS.limpar()
        monkeypatch.setattr(decisao_pt, "cos_no_plantao", lambda agora=None: True)
        assert any(p["numero"] == "PT-1" for p in PS.para_o_sino("cos@exemplo.test"))


def test_a_pt_que_o_nexus_ja_decidiu_sai_do_sino(app, com_responsavel, monkeypatch):
    monkeypatch.setattr(decisao_pt, "decisoes", lambda: [{"pt": "PT-1", "codigo_ativo": "THPN-ALT100-INVR1",
                                                         "decisao": "de_acordo"}])
    with app.test_request_context("/"):
        assert all(not (p["numero"] == "PT-1" and p["codigo"] == "THPN-ALT100-INVR1") for p in PS.para_o_sino(RESP))


def test_a_espera_curta():
    assert [PS._espera(m) for m in (None, 40, 60, 185, 1440, 1570)] == ["", "40 min", "1 h", "3 h 5 min", "1 d", "1 d 2 h"]

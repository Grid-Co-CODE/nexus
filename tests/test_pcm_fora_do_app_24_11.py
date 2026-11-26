"""PCM → OS fora do App (24/11/2026, `nexus/pcm/fora_do_app.py`): quem fecha OS fora do App de Campo, por semana.

Levi, 24/11/2026, no chat do App de Campo: "Eu quero uma lista de todos os técnicos que estão fazendo OS pelo computador";
depois aprovou a medição fixa por semana e mandou para o Nexus PCM. A medição é do App (v381, a rota
`/api/app/nexus/fora-do-app`, com a mesma chave das Sugestões); a tela é do Nexus. Decisões do Levi no mesmo dia, no chat do
Nexus PCM: a tela fica no PCM, junto do Acompanhamento; mostra só os técnicos de campo (quem tem usina nos Técnicos por
usina), com o "Mostrar todos" para conferir; e a veem o PCM, a Supervisão Campo e os administradores.

O que estes testes seguram: o contrato da resposta (a versão, as semanas, as pessoas), a conta do percentual e a semana
anterior ao lado, o filtro dos técnicos pelo código do e-mail, a tela (a lista, as OS de cada um, o "Mostrar todos") e
quem a vê. O App é de mentira; nomes e OS inventados (repositório público)."""
import io
import json
import urllib.error

import pytest
from test_campo_visao import banco  # noqa: F401  (fixture)
from test_pcm_publicar import _no_setor, _pessoa

from nexus.cadastro import setor_ids as SID
from nexus.cadastro.ligacao_campo import codigo_da_pessoa
from nexus.casca import relatos_app as R
from nexus.pcm import fora_do_app as FA

TELA = "/t/pcm/os-fora-do-app"
CHAVE = "k" * 40
HMAC = "chave-hmac-de-teste"


def _p(nome, email, concluidas, app_, os_fora=(), tipos=None):
    fora = len(os_fora)
    return {"nome": nome, "email": email, "id_personnel": "1", "os_concluidas": concluidas, "os_pelo_app": app_,
            "os_fora": fora, "tarefas": concluidas * 2, "tarefas_fora": fora * 2, "tipos_fora": tipos or {"Sem tipo": fora},
            "os_fora_lista": [{"os": str(o), "descricao": f"[TST-USN100] - Tarefa {o}"} for o in os_fora]}


SEMANAS = [
    {"semana": "2026-W48", "inicio": "2026-11-23", "fim": "2026-11-29", "pessoas": [
        _p("Tecnico Um", "tecnico.um@exemplo.test", 10, 0, range(9001, 9011)),
        _p("Tecnico Dois", "tecnico.dois@exemplo.test", 8, 6, (9101, 9102)),
        _p("Operador do Escritorio", "operador@exemplo.test", 5, 0, range(9201, 9206), {"Desligamento": 5})]},
    {"semana": "2026-W47", "inicio": "2026-11-16", "fim": "2026-11-22", "pessoas": [
        _p("Tecnico Um", "tecnico.um@exemplo.test", 6, 0, range(9301, 9307)),
        _p("Tecnico Dois", "tecnico.dois@exemplo.test", 4, 0, range(9401, 9405))]},
]


class _AppFalso:
    def __init__(self, corpo=None, status=200):
        self.corpo = corpo if corpo is not None else {
            "versao": 1, "gerado_em": "2026-11-25T06:33:10+00:00",
            "cobertura": {"desde": "2026-10-27T03:00:00+00:00", "paginas": 54, "completo": True,
                          "criacao_mais_antiga_lida": "2026-09-08T12:00:00+00:00"},
            "semanas": SEMANAS}
        self.status = status
        self.pedidos = []

    def __call__(self, req, timeout=None):
        self.pedidos.append({"url": req.full_url, "chave": req.get_header("X-nexus-chave")})
        if self.status != 200:
            raise urllib.error.HTTPError(req.full_url, self.status, "erro", {}, io.BytesIO(b"{}"))
        return io.BytesIO(json.dumps(self.corpo).encode("utf-8"))


@pytest.fixture
def app_falso(app, banco, monkeypatch):  # noqa: F811
    app.config.update(NEXUS_APP_RELATOS_CHAVE=CHAVE, NEXUS_PESSOA_HMAC=HMAC)
    FA.limpar()
    falso = _AppFalso()
    monkeypatch.setattr(R, "_abrir", falso)
    # os técnicos de campo: quem tem usina nos Técnicos por usina (aqui, dublado pelo código do e-mail)
    monkeypatch.setattr(FA, "_tecnicos", lambda cfg: {codigo_da_pessoa(HMAC, "tecnico.um@exemplo.test"),
                                                       codigo_da_pessoa(HMAC, "tecnico.dois@exemplo.test")})
    yield falso
    FA.limpar()


def _como(app, monkeypatch, setor):
    _no_setor(monkeypatch, setor)
    return _pessoa(app)


# ── a leitura e a conta ─────────────────────────────────────────────────────────────────────────────────────────────
def test_le_a_rota_do_app_com_a_chave_e_as_semanas(app, app_falso):
    with app.test_request_context("/"):
        d = FA.ler()
    assert d["erro"] == "" and [s["semana"] for s in d["semanas"]] == ["2026-W48", "2026-W47"]
    pedido = app_falso.pedidos[0]
    assert pedido["url"].endswith("/fora-do-app?semanas=8") and pedido["chave"] == CHAVE
    assert d["cobertura"]["completo"] is True


def test_a_versao_que_o_nexus_nao_entende_vira_erro(app, app_falso):
    app_falso.corpo = {"versao": 2, "semanas": []}
    with app.test_request_context("/"):
        d = FA.ler()
    assert "versão" in d["erro"] and d["semanas"] == []


def test_a_semana_com_a_anterior_ao_lado_e_so_os_tecnicos(app, app_falso):
    with app.test_request_context("/"):
        m = FA.montar(app.config, {})
    assert m["semana"]["semana"] == "2026-W48" and m["anterior"]["semana"] == "2026-W47"
    nomes = [l["nome"] for l in m["linhas"]]
    assert nomes == ["Tecnico Um", "Tecnico Dois"]                 # o escritório fica fora
    um = m["linhas"][0]
    assert (um["os_fora"], um["os_concluidas"], um["pct_fora"]) == (10, 10, 100)
    assert (um["antes"]["os_fora"], um["antes"]["pct_fora"]) == (6, 100)
    dois = m["linhas"][1]
    assert (dois["pct_fora"], dois["antes"]["pct_fora"]) == (25, 100)
    assert m["fora_da_lista"] == 1 and m["totais"]["os_fora"] == 12 and m["totais"]["os_concluidas"] == 18
    with app.test_request_context("/"):
        todos = FA.montar(app.config, {"todos": "1"})
    assert [l["nome"] for l in todos["linhas"]][0] == "Tecnico Um" and len(todos["linhas"]) == 3
    with app.test_request_context("/"):
        w47 = FA.montar(app.config, {"semana": "2026-W47"})
    assert w47["semana"]["semana"] == "2026-W47" and w47["anterior"] is None


def test_sem_a_chave_nao_chama_o_app(app, banco, monkeypatch):  # noqa: F811
    app.config.pop("NEXUS_APP_RELATOS_CHAVE", None)
    FA.limpar()
    falso = _AppFalso()
    monkeypatch.setattr(R, "_abrir", falso)
    with app.test_request_context("/"):
        d = FA.ler()
    assert falso.pedidos == [] and d["ligado"] is False


# ── a tela e quem a vê ──────────────────────────────────────────────────────────────────────────────────────────────
def test_a_tela_mostra_a_lista_e_as_os_de_cada_um(app, app_falso, monkeypatch):
    c = _como(app, monkeypatch, SID.PCM)
    html = c.get(TELA).get_data(as_text=True)
    assert "OS fora do App" in html and "Tecnico Um" in html and "Operador do Escritorio" not in html
    assert "100%" in html and "25%" in html and "2026-W47" in html
    assert "9001" in html and "/os/_nexus/card/folio/9001" in html
    assert 'name="todos"' in html
    assert "Operador do Escritorio" in c.get(TELA + "?todos=1").get_data(as_text=True)


@pytest.mark.parametrize("setor, ve", [(SID.PCM, True), (SID.SUPERVISAO_CAMPO, True), (SID.PERFORMANCE, False)])
def test_quem_ve_a_tela(app, setor, ve):
    """A tela é DO PCM e da Supervisão Campo (`Tela.do_setor`): quem é deles a vê sem marcar em Base → Acessos; os outros
    setores, só se o administrador marcar. O administrador vê tudo."""
    from nexus.auth import setor_telas as ST
    with app.test_request_context("/"):
        assert ("pcm/os-fora-do-app" in ST.das_do_setor({"id": setor, "nome": "?"})) is ve

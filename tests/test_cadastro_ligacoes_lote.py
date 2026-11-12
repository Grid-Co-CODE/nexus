"""O botão "Ligar as sugestões de 100%" das Ligações entre bases (11/11/2026). Bases, chaves e usinas inventadas; o
panorama é trocado por buracos controlados, e as decisões vão à pasta de dados do teste."""
import pytest

from nexus import create_app
from nexus.cadastro import ligacoes as L
from nexus.cadastro.cifra import gerar_chave

from conftest import SENHA_TESTE

BASE = "Base Fictícia · Projetos"
OUTRA = "Outra Base Fictícia"


def _b(chave, *notas_ids, sistema=BASE):
    return {"sistema": sistema, "chave": chave, "motivo": "sem usina", "tarefas": None, "nome": chave, "cidade": None,
            "rotulo": None, "os": None, "sugestoes": [{"id": i, "titulo": f"Usina {i}", "codigo": "", "nota": n}
                                                      for n, i in notas_ids]}


BURACOS = [
    _b("a", (100, 1)),                     # liga
    _b("b", (99, 2)),                      # abaixo de 100
    _b("c", (100, 3), (80, 4)),            # duas sugestões
    _b("d"),                               # sem sugestão
    _b("e", (100, 5)), _b("f", (100, 5)),  # a mesma usina em duas chaves: ambíguo
    _b("g", (100, 6), sistema=OUTRA),      # de outra base: não entra
]


@pytest.fixture
def app_lote(tmp_path, monkeypatch):
    app = create_app({"NEXUS_SECRET_KEY": "chave-de-teste", "NEXUS_SENHA_ADMIN": SENHA_TESTE,
                      "NEXUS_CHAVE_CADASTRO": gerar_chave(), "NEXUS_ARMAZEM_LOCAL": str(tmp_path / "cadastro.json"),
                      "NEXUS_DADOS": str(tmp_path / "dados")})
    app.config.update({"TESTING": True, "SESSION_COOKIE_SECURE": False})
    monkeypatch.setattr(L, "panorama", lambda srv, atual, regras: {
        "buracos": BURACOS, "por_nome": [], "ausencias": {}, "decisoes": [], "sistemas": [], "usinas": [],
        "gerado_em": "2026-11-11T10:00:00"})
    chamadas = []
    monkeypatch.setattr(L, "reaplicar", lambda cfg, srv: chamadas.append(1))
    app.reaplicadas = chamadas
    return app


def _entra(app):
    c = app.test_client()
    assert c.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    return c


def _ligadas(app):
    return {(d["chave"], d["usina_id"]) for d in L.carregar_regras(app.config)["ligar"] if d["sistema"] == BASE}


def test_liga_so_a_unica_de_100_e_pula_o_resto(app_lote):
    r = _entra(app_lote).post("/t/base/ligacoes/aceitar-sugestoes", data={"alvo_sistema": BASE})
    assert r.status_code == 303
    assert _ligadas(app_lote) == {("a", 1)}
    assert [d for d in L.carregar_regras(app_lote.config)["ligar"] if d["sistema"] == OUTRA] == []
    assert len(app_lote.reaplicadas) == 1
    from urllib.parse import parse_qs, urlparse
    ok = parse_qs(urlparse(r.headers["Location"]).query)["ok"][0]
    assert ok.startswith("1 ligação feita") and "Publique no banco" in ok
    assert "5 para você decidir" in ok and "mais de uma sugestão" in ok and "abaixo de 100%" in ok
    assert "sem sugestão" in ok and "duas chaves" in ok


def test_sem_alvo_recusa(app_lote):
    r = _entra(app_lote).post("/t/base/ligacoes/aceitar-sugestoes", data={})
    assert "erro" in r.headers["Location"]
    assert _ligadas(app_lote) == set() and not app_lote.reaplicadas


def test_quem_nao_e_admin_recebe_403(app_lote):
    r = app_lote.test_client().post("/t/base/ligacoes/aceitar-sugestoes", data={"alvo_sistema": BASE})
    assert r.status_code in (401, 403, 302) and _ligadas(app_lote) == set()
    c = _entra(app_lote)
    with c.session_transaction() as s:
        s["admin"] = False
    assert c.post("/t/base/ligacoes/aceitar-sugestoes", data={"alvo_sistema": BASE}).status_code == 403
    assert _ligadas(app_lote) == set()


def test_outro_site_e_recusado(app_lote):
    c = _entra(app_lote)
    for h in ({"Sec-Fetch-Site": "cross-site"}, {"Origin": "https://outro.exemplo"}):
        r = c.post("/t/base/ligacoes/aceitar-sugestoes", data={"alvo_sistema": BASE}, headers=h)
        assert r.status_code == 403
    assert _ligadas(app_lote) == set()


def test_o_n_do_botao_e_o_que_a_rota_liga(app_lote):
    c = _entra(app_lote)
    from nexus.cadastro.telas_ligacoes import contexto
    with app_lote.test_request_context("/"):
        from nexus.cadastro.telas import servico
        n = contexto(servico(), app_lote.config, {"sistema": BASE})["n_sugestoes_100"]
        assert contexto(servico(), app_lote.config, {})["n_sugestoes_100"] == 0   # sem base escolhida, sem botão
    c.post("/t/base/ligacoes/aceitar-sugestoes", data={"alvo_sistema": BASE})
    assert n == len(_ligadas(app_lote)) == 1


def test_o_botao_aparece_com_a_base_e_pede_confirmacao(app_lote):
    html = _entra(app_lote).get(f"/t/base/governanca?aba=buracos&sistema={BASE}").get_data(as_text=True)
    assert "Ligar as 1 sugestões de 100%" in html and 'data-confirmar="Ligar 1 chaves' in html
    assert "aceitar-sugestoes" not in _entra(app_lote).get("/t/base/governanca").get_data(as_text=True)


def test_a_recusa_de_uma_nao_para_o_lote_e_o_fim_ainda_reaplica(app_lote, monkeypatch):
    """Uma ligação recusada pelo de-para (DecisaoInvalida) não derruba a página nem deixa as outras sem o reaplicar."""
    original = L.decidir

    def decidir(cfg, acao, sistema, **kw):
        if kw.get("chave") == "a":
            raise L.DecisaoInvalida("usina fora do cadastro")
        return original(cfg, acao, sistema, **kw)
    monkeypatch.setattr(L, "decidir", decidir)
    r = _entra(app_lote).post("/t/base/ligacoes/aceitar-sugestoes", data={"alvo_sistema": BASE})
    assert r.status_code == 303
    from urllib.parse import parse_qs, urlparse
    ok = parse_qs(urlparse(r.headers["Location"]).query)["ok"][0]
    assert ok.startswith("0 ligações feitas") and "1 recusada(s) pelo de-para" in ok
    assert len(app_lote.reaplicadas) == 0

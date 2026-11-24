"""Base › E-mails automáticos (24/11/2026): o que o App de Campo manda sozinho por e-mail, só administrador. Levi, pela
sessão do App: "Gostaria de poder controlar esses e-mails automáticos ou ter pelo menos um controle! E gostaria que
estivesse no Nexus"; e, aqui: "Só admin". A 1ª fase só lê os livros email_app_campo. Nada vai ao banco: os livros são
dublados."""
from datetime import datetime, timezone

import pytest

from nexus.campo import emails_app as EA

AGORA = datetime(2026, 11, 24, 15, 0, tzinfo=timezone.utc)
TODOS = [
    {"ID": "1", "Tipo": "pt_aviso", "Referência": "PT 501", "Destinatário": "abc123", "Papel": "supervisor",
     "Quando": "2026-11-24T11:00:00Z", "Via": "graph", "Situação": "enviado", "Tentativas": "1", "Erro": ""},
    {"ID": "2", "Tipo": "pt_aviso", "Referência": "PT 502", "Destinatário": "caixa:COS", "Papel": "COS",
     "Quando": "2026-11-23T02:00:00Z", "Via": "graph", "Situação": "falhou", "Tentativas": "3", "Erro": "503 Graph"},
    {"ID": "3", "Tipo": "pt_aviso", "Referência": "PT 300", "Destinatário": "abc123", "Papel": "supervisor",
     "Quando": "2026-11-01T10:00:00Z", "Via": "graph", "Situação": "enviado", "Tentativas": "1", "Erro": ""},
    {"ID": "4", "Tipo": "luvas_tst", "Referência": "UFV-010", "Destinatário": "caixa:TST", "Papel": "TST",
     "Quando": "2026-11-20T13:00:00Z", "Via": "graph", "Situação": "desligado", "Tentativas": "0", "Erro": ""},
]
TIPOS = [{"Tipo": "pt_aviso", "Nome": "PT aguardando assinatura", "Gatilho": "Quando a PT nasce", "Destino padrão":
          "Supervisor da usina", "Ligado": "sim", "De onde vem a regra": "App Setting"},
         {"Tipo": "luvas_tst", "Ligado": "não", "De onde vem a regra": "Nexus"}]
SEMANAL = [{"Semana": "2026-W47", "Destinatário (HMAC)": "abc123", "Papel": "TST", "Enviado em": "2026-11-24T10:05:00Z",
            "Via": "graph", "Tentativas": "1", "Erro": "", "Situação": "enviado"}]


def test_a_lista_conta_sete_dias_e_sabe_o_que_o_app_diz():
    d = EA.montar(TIPOS, TODOS, SEMANAL, AGORA)
    assert d["fonte"] == "todos" and d["tem_tipos"]
    t = {x["tipo"]: x for x in d["tipos"]}
    assert [x["tipo"] for x in d["tipos"]][:2] == ["pt_aviso", "luvas_tst"]          # a ordem do catálogo
    pt = t["pt_aviso"]
    assert (pt["enviados"], pt["falhas"], pt["ligado"], pt["critico"]) == (1, 1, True, True)   # a PT de 01/11 fica fora
    assert pt["ultimo"] == datetime(2026, 11, 24, 11, 0, tzinfo=timezone.utc)
    assert t["luvas_tst"]["ligado"] is False and t["luvas_tst"]["enviados"] == 0
    assert t["luvas_tst"]["nome"] == "Luvas isolantes reprovadas na ronda"           # sem nome no livro: o do catálogo
    # o tipo sem envio nenhum na aba de todos os envios: zero (a aba existe), não "não sei"
    assert t["auditoria_diaria"]["enviados"] == 0 and t["auditoria_diaria"]["ultimo"] is None


def test_sem_a_aba_nova_so_o_semanal_tem_numero():
    """Até o App publicar a aba "Todos os envios", só o e-mail semanal da Segurança (a aba Envios de antes) tem número; o
    resto fica "—" (sem dado não se inventa)."""
    d = EA.montar(None, None, SEMANAL, AGORA)
    t = {x["tipo"]: x for x in d["tipos"]}
    assert d["fonte"] == "semanal" and not d["tem_tipos"]
    assert t["seguranca_semanal"]["enviados"] == 1 and t["pt_aviso"]["enviados"] is None
    assert t["pt_aviso"]["ligado"] is None
    assert EA.montar(None, None, None, AGORA)["fonte"] == "nenhum"


def test_o_historico_mostra_a_pessoa_pelo_nome_e_a_caixa_e_nunca_o_codigo():
    h = EA.historico(TODOS, None, "pt_aviso", {"abc123": "Fulana Prado"}, AGORA)
    assert [e["id"] for e in h] == ["1", "2", "3"]                                    # do mais novo para o mais antigo
    assert (h[0]["quem"], h[1]["quem"], h[1]["rotulo"], h[1]["tom"]) == ("Fulana Prado", "Caixa COS", "Falhou", "critico")
    assert EA.quem("zzz", {}) == "Pessoa sem e-mail no cadastro"


@pytest.fixture
def com_livros(monkeypatch):
    from nexus.torres.base import emails_tela as ET
    monkeypatch.setattr(ET, "_livros", lambda: ({EA.ABA_TIPOS: TIPOS, EA.ABA_TODOS: TODOS, EA.ABA_SEMANAL: SEMANAL}, ""))
    monkeypatch.setattr(ET, "_nomes", lambda: {"abc123": "Fulana Prado"})


def test_a_tela_e_so_do_administrador(app, com_livros):
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(logado=True, admin=False, usuario={"email": "alguem@exemplo.test", "nome": "Alguém"})
    assert c.get("/t/base/emails-automaticos").status_code == 403
    assert c.get("/t/base/emails-automaticos/pt_aviso").status_code == 403


def test_a_tela_lista_os_tipos_e_abre_o_historico(app, com_livros):
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(logado=True, admin=True)
    html = c.get("/t/base/emails-automaticos").get_data(as_text=True)
    assert "PT aguardando assinatura" in html and "/t/base/emails-automaticos/pt_aviso" in html
    assert "1 enviados" in html and "1 falha" in html and "Desligado" in html
    h = c.get("/t/base/emails-automaticos/pt_aviso").get_data(as_text=True)
    assert "Fulana Prado" in h and "Caixa COS" in h and "503 Graph" in h and "abc123" not in h
    assert "24/11 08:00" in h                                                      # 11:00 UTC = 08:00 de Brasília
    assert c.get("/t/base/emails-automaticos/nao_existe").status_code == 404

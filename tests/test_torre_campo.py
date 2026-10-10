"""Torre Campo · App: a visão do Nexus sobre o campo, sem o painel do App nem o Azure (Levi, 05/10/2026: "quero parar de
referenciar o Azure e ter uma visão nossa!")."""
from nexus.torres import descobrir_torres

# Ordens de serviço ("os"), Ranking e Imagens da ronda saíram em 08/10/2026 (Levi: "são redundantes")
NOSSAS = ("atencao", "aprovacao", "rondas", "zeladoria", "triagem")


def _campo():
    return next(t for t in descobrir_torres() if t.id == "campo")


def test_zeladoria_tem_tela_e_a_pt_foi_para_seguranca(logado):
    # Levi, 04/10: "crie para PT, ZELADORIA". Em 09/10 a PT foi para Segurança · HSEQ > APR e PT ("quero que esse
    # visual e caminho vá para APR e PT de Segurança · HSEQ"): o endereço antigo leva para lá, com os filtros
    assert _campo().tela("zeladoria") is not None and "Zeladoria" in logado.get("/t/campo/zeladoria").get_data(as_text=True)
    assert _campo().tela("pt") is None
    r = logado.get("/t/campo/pt?aba=historico&dias=7")
    assert r.status_code == 302 and r.headers["Location"].endswith("/t/hseq/apr-pt?aba=historico&dias=7")
    html = logado.get("/t/hseq/apr-pt").get_data(as_text=True)
    assert "Permissões de trabalho e Análise Preliminar de Risco" in html and "Segurança · HSEQ" in html


def test_zeladoria_fica_junto_das_telas_parecidas():
    # a zeladoria é acompanhamento do dia, como a ronda
    ids = [t.id for t in _campo().telas]
    assert ids.index("zeladoria") == ids.index("rondas") + 1


def test_nenhuma_tela_aponta_para_o_azure_nem_abre_moldura(logado):
    for t in _campo().telas:
        html = logado.get(f"/t/campo/{t.id}").get_data(as_text=True)
        assert "azurewebsites" not in html and "gridco-campo-mw" not in html, t.id
        assert "<iframe" not in html and "Abrir no App" not in html, t.id
        assert ("Em construção" in html) == (t.id not in NOSSAS), t.id


def test_sem_banco_a_tela_avisa_e_nao_some(logado):
    # no teste não há banco (nunca vai à rede): a tela do Nexus abre e diz que não conseguiu ler
    html = logado.get("/t/campo/rondas").get_data(as_text=True)
    assert "Não consegui ler o banco do Nexus" in html and "Rondas" in html


def test_rotas_segue_em_construcao(logado):
    html = logado.get("/t/campo/rotas").get_data(as_text=True)
    assert "Em construção" in html and "<iframe" not in html

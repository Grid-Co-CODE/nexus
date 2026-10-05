"""Torre Campo · App: cada aba do painel de gestão do App de Campo tem o seu lugar no Nexus (Levi, 04/10/2026)."""
from pathlib import Path

from nexus.torres import descobrir_torres

PAINEL = "https://gridco-campo-mw.azurewebsites.net/api/gestao"
# tela do Nexus -> aba do painel do App (o gestao.html abre direto na aba com #ir=<aba>)
ABAS = {"atencao": "atn", "aprovacao": "su", "pt": "pt", "os": "os", "rondas": "ro",
        "zeladoria": "zl", "ranking": "des", "triagem": "vg", "imagens": "img"}


def _campo():
    return next(t for t in descobrir_torres() if t.id == "campo")


def test_pt_e_zeladoria_tem_tela_na_torre_campo(logado):
    # Levi, 04/10: "crie para PT, ZELADORIA". As duas abas do painel do App não tinham lugar na torre.
    for tela_id, nome in (("pt", "Permissões de trabalho"), ("zeladoria", "Zeladoria")):
        assert _campo().tela(tela_id) is not None, tela_id
        resp = logado.get(f"/t/campo/{tela_id}")
        assert resp.status_code == 200, tela_id
        assert nome in resp.get_data(as_text=True)


def test_pt_e_zeladoria_ficam_junto_das_telas_parecidas():
    # A PT é fila de decisão, como a aprovação de OS; a zeladoria é acompanhamento do dia, como a ronda.
    ids = [t.id for t in _campo().telas]
    assert ids.index("pt") == ids.index("aprovacao") + 1
    assert ids.index("zeladoria") == ids.index("rondas") + 1


def test_tela_com_aba_no_app_abre_o_painel_do_app_na_aba_certa(logado):
    # Levi, 04/10: "você construiu as abas mas ainda não vejo nada". Enquanto a chave só de leitura das tabelas do
    # App não existe, cada tela abre o próprio painel do App, na aba dela, dentro do Nexus (com o menu à vista).
    assert set(ABAS) == {t.id for t in _campo().telas} - {"rotas"}
    for tela_id, aba in ABAS.items():
        html = logado.get(f"/t/campo/{tela_id}").get_data(as_text=True)
        assert f'src="{PAINEL}#ir={aba}"' in html, tela_id
        assert 'class="menu"' in html, tela_id
        assert "Em construção" not in html, tela_id


def test_rotas_do_dia_nao_existe_no_app_e_segue_em_construcao(logado):
    html = logado.get("/t/campo/rotas").get_data(as_text=True)
    assert "Em construção" in html
    assert "<iframe" not in html


def test_painel_do_app_fica_num_recorte_que_esconde_o_menu_dele(logado):
    # Levi, 04/10: "está duplicando a barra lateral, mantenha apenas a barra lateral do Nexus". O painel vem de outro
    # endereço e o Nexus não mexe nele: a moldura fica 224 px mais larga e a faixa do menu do App fica fora da vista.
    html = logado.get("/t/campo/zeladoria").get_data(as_text=True)
    assert '<div class="campo-recorte">' in html


def test_recorte_segue_as_medidas_do_painel_do_app():
    # gestao.html v225: .sb{width:224px}, e @media(max-width:900px) o próprio painel esconde o menu (vira gaveta).
    # Por isso o recorte só vale com 677 px ou mais de área visível (677 + 224 = 901 > 900).
    css = (Path(__file__).parent.parent / "nexus" / "static" / "nexus.css").read_text(encoding="utf-8")
    assert "@container (min-width:677px)" in css
    assert "width:calc(100% + 224px);margin-left:-224px" in css


def test_central_de_atencao_tem_atencao_e_encaminhamentos(logado):
    # Sem o menu do App, Encaminhamentos só se alcança por aqui (o encaixe de 04/10 pôs os dois nesta tela).
    html = logado.get("/t/campo/atencao").get_data(as_text=True)
    assert f'src="{PAINEL}#ir=atn"' in html
    assert 'href="?aba=enc"' in html
    html = logado.get("/t/campo/atencao?aba=enc").get_data(as_text=True)
    assert f'src="{PAINEL}#ir=enc"' in html
    assert 'href="?aba=enc" aria-current="page"' in html
    # aba que não existe volta para a primeira, sem montar endereço com o que veio na URL
    html = logado.get("/t/campo/atencao?aba=xyz").get_data(as_text=True)
    assert f'src="{PAINEL}#ir=atn"' in html and "xyz" not in html


def test_toda_tela_do_painel_tem_saida_para_o_app_inteiro(logado):
    # O rodapé do menu do App (Conta Fracttal, sair) também fica fora da vista: o link abre o painel do App inteiro.
    html = logado.get("/t/campo/rondas").get_data(as_text=True)
    assert f'href="{PAINEL}#ir=ro" target="_blank" rel="noopener"' in html


def test_endereco_do_painel_vem_da_configuracao(app, logado):
    app.config["NEXUS_CAMPO_PAINEL"] = "https://exemplo.test/api/gestao"
    html = logado.get("/t/campo/zeladoria").get_data(as_text=True)
    assert 'src="https://exemplo.test/api/gestao#ir=zl"' in html

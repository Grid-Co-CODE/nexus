"""Os retoques do Ranking de pontos (Levi, 15/11/2026: "segue com Ranking e Ocorrências", a última parte da revisão de
desenho da Usinas 360° de 12/11) e o fim da tela Ocorrências.

Ranking: o "Líder 3.240 pontos" repetia o 1º lugar do pódio logo acima, e a procedência estava em dois lugares ("calculado
em" no canto e "livro do ranking do App · lido às" na barra). O e-mail do pódio FICA: o RH paga o prêmio pelo e-mail
(Fillipe Figueiró, 03/11/2026), e a auditoria não sabia disso.
Ocorrências: SAIU (Levi, 15/11/2026: "mandei capar novas ocorrências mesmo, vai ser substituída por caixa de entrada em
comando"; "tem que matar esse caminho de ocorrências!"): o menu, a tela, a etiqueta da Visão geral e a seção do
prontuário; todo endereço antigo leva à Caixa de entrada do Comando e nada se grava. O livro e a conta ficam (é dado)."""
import html as html_mod
import re

from test_campo_ocorrencias import ADMIN, _entra, _form, cad  # noqa: F401  (cad é fixture)
from test_campo_ranking_pontos import _texto, ranking  # noqa: F401  (fixture)
from test_campo_visao import banco  # noqa: F401  (fixture)

from nexus.campo import ocorrencias as O


# ── Ranking ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_ranking_sem_o_lider_repetido(ranking, logado):
    html = logado.get("/t/campo/ranking").get_data(as_text=True)
    numeros = re.search(r'<div class="cn-numeros">.*?</div>', html, re.S).group(0)
    assert "Líder" not in numeros
    assert re.findall(r'<span class="gc-rotulo">([^<]*)<', numeros) == ["Classificados", "", "Média do mês"]
    assert "Fora do ciclo" in numeros                                     # o rótulo com a explicação no mouse


def test_a_procedencia_do_ranking_num_lugar_so(ranking, logado):
    html = logado.get("/t/campo/ranking").get_data(as_text=True)
    t = _texto(html)
    assert "livro do ranking do App" not in t and 'class="cn-barra-fonte"' not in html
    assert "calculado em 13/10 18:25" in _texto(re.search(r'<div class="cn-frescor">.*?</div>', html, re.S).group(0))
    # a hora em que o Nexus leu o livro vai para o "!" do título, como nas outras telas revisadas
    assert re.search(r"Como o App calcula\..*?lido pelo Nexus às \d\d:\d\d", t)


def test_o_email_do_podio_fica_para_o_rh(ranking, logado):
    html = logado.get("/t/campo/ranking").get_data(as_text=True)
    podio = html.split('class="rk-podio"', 1)[1].split('class="cn-numeros"', 1)[0]
    assert podio.count('class="rk-email"') == 3


# ── Ocorrências: o caminho saiu ──────────────────────────────────────────────────────────────────────────────────────
def test_a_tela_saiu_do_menu_da_usinas_360():
    from nexus.torres.campo import TORRE
    assert "ocorrencias" not in [t.id for t in TORRE.telas]


def test_todo_endereco_antigo_leva_a_caixa_de_entrada_e_nada_grava(cad, logado):
    for caminho in ("/t/campo/ocorrencias", "/t/campo/ocorrencias?responsavel=*&ver=quadro", "/t/campo/ocorrencias/nova",
                    "/t/campo/ocorrencias/oc0123456789a"):
        r = logado.get(caminho)
        assert r.status_code == 303 and r.headers["Location"].endswith("/t/comando/caixa-de-entrada"), caminho
    for caminho in ("/t/campo/ocorrencias/nova", "/t/campo/ocorrencias/oc0123456789a/andamento"):
        r = logado.post(caminho, data=_form(titulo="Cerca caída"))
        assert r.status_code == 303 and r.headers["Location"].endswith("/t/comando/caixa-de-entrada"), caminho
    assert cad.linhas(O.LIVRO, O.ABA) == []


def test_a_visao_geral_sem_a_etiqueta_de_ocorrencias(cad, logado):
    O.criar(_form(titulo="Inversor 2 desarmando", criticidade="alta"), ADMIN, True)          # uma que já existisse
    html = logado.get("/t/campo/responsaveis?modo=geral&responsavel=*").get_data(as_text=True)
    assert "Altair" in html and not re.search(r">\d+ ocorrência", html)      # a etiqueta "1 ocorrência" no nome
    assert "/t/campo/ocorrencias" not in html

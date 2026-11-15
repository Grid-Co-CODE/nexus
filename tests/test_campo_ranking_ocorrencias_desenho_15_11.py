"""Os retoques do Ranking de pontos e das Ocorrências (Levi, 15/11/2026: "segue com Ranking e Ocorrências", a última
parte da revisão de desenho da Usinas 360° de 12/11).

Ranking: o "Líder 3.240 pontos" repetia o 1º lugar do pódio logo acima, e a procedência estava em dois lugares ("calculado
em" no canto e "livro do ranking do App · lido às" na barra). O e-mail do pódio FICA: o RH paga o prêmio pelo e-mail
(Fillipe Figueiró, 03/11/2026), e a auditoria não sabia disso.
Ocorrências: sem nenhuma ocorrência (em 15/11 eram 0 em produção), a tela mostrava três zeros, o cabeçalho de uma lista
sem linhas e "Nenhuma ocorrência com esse filtro" sem filtro nenhum; e era a única sem o "!" ao lado do título. E as
novas estão fechadas (Levi, 15/11/2026: "mandei capar novas ocorrências mesmo, vai ser substituída por caixa de entrada
em comando"): a nova vai para a Caixa de entrada do Comando; as que já existem seguem na tela."""
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


# ── Ocorrências ──────────────────────────────────────────────────────────────────────────────────────────────────────
def _vazio(html):
    m = re.search(r'<div class="oc-vazio-inicio".*?</div>', html, re.S)
    return m.group(0) if m else ""


def test_sem_nenhuma_ocorrencia_a_tela_leva_a_caixa_de_entrada(cad, cliente):
    # Levi, 15/11/2026: "mandei capar novas ocorrências mesmo, vai ser substituída por caixa de entrada em comando"
    c = _entra(cliente, ADMIN)
    html = c.get("/t/campo/ocorrencias?responsavel=*").get_data(as_text=True)
    v = _vazio(html)
    assert "Nenhuma ocorrência registrada" in v and "Caixa de entrada" in v
    assert re.search(r'<a class="gc-btn gc-btn--primario"[^>]*href="/t/comando/caixa-de-entrada"[^>]*>Abrir a Caixa de entrada</a>', v)
    # nada de registrar aqui, de zeros, do cabeçalho de uma lista sem linhas nem do "com esse filtro" sem filtro
    assert 'href="/t/campo/ocorrencias/nova' not in html and "Registrar" not in v
    assert 'class="oc-numeros"' not in html and "oc-lin--cab" not in html and "com esse filtro" not in html
    q = c.get("/t/campo/ocorrencias?responsavel=*&ver=quadro").get_data(as_text=True)
    assert _vazio(q) and 'class="oc-quadro"' not in q


def test_a_ocorrencia_nova_vai_para_a_caixa_e_nada_grava(cad, cliente):
    c = _entra(cliente, ADMIN)
    r = c.get("/t/campo/ocorrencias/nova?usina=3")
    assert r.status_code == 303 and r.headers["Location"].endswith("/t/comando/caixa-de-entrada")
    r = c.post("/t/campo/ocorrencias/nova", data=_form(titulo="Cerca caída", usina_id="3"))
    assert r.status_code == 303 and r.headers["Location"].endswith("/t/comando/caixa-de-entrada")
    assert cad.linhas(O.LIVRO, O.ABA) == []


def test_as_que_ja_existem_seguem_na_lista_sem_o_nova(cad, cliente):
    O.criar(_form(titulo="Inversor 2 desarmando", criticidade="alta"), ADMIN, True)
    c = _entra(cliente, ADMIN)
    html = c.get("/t/campo/ocorrencias?responsavel=*").get_data(as_text=True)
    assert "Inversor 2 desarmando" in html and "oc-lin--cab" in html and 'class="oc-numeros"' in html
    assert "Nova ocorrência" not in html and 'href="/t/campo/ocorrencias/nova' not in html
    assert re.search(r'Ocorrência nova:.*?<a[^>]*href="/t/comando/caixa-de-entrada"', html, re.S)


def test_com_ocorrencias_e_o_filtro_vazio_a_lista_diz_o_filtro_sem_o_cabecalho(cad, cliente):
    O.criar(_form(titulo="Inversor 2 desarmando", criticidade="alta"), ADMIN, True)
    c = _entra(cliente, ADMIN)
    html = c.get("/t/campo/ocorrencias?responsavel=*&criticidade=baixa").get_data(as_text=True)
    assert "Nenhuma ocorrência com esse filtro" in html and "oc-lin--cab" not in html and not _vazio(html)


def test_o_titulo_tem_o_exclamacao_e_o_eyebrow_nao_repete_o_nome(cad, logado):
    html = logado.get("/t/campo/ocorrencias?responsavel=*").get_data(as_text=True)
    cab = re.search(r'<div class="cn-cab">.*?<p class="cn-pergunta">', html, re.S).group(0)
    assert 'class="gc-titulo-explica"' in cab and "Entenda esta tela" in cab
    assert re.search(r'<p class="gc-eyebrow">Usinas 360°</p>', cab)
    t = html_mod.unescape(_texto(cab))
    assert "plano de ação" in t and "Caixa de entrada" in t and "Lido às" in t

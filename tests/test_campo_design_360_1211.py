"""A revisão de desenho da Usinas 360° (12/11/2026). Levi: "Web design guidelines em todas as páginas do usinas 360°.
Vamos procurar hierarquias, ver onde dá para enxugar informação repetida e deixar mais bonito!"; depois de ver a
auditoria e a prévia do quadro comparativo: "Segue pai".

1ª entrega: os ajustes técnicos das diretrizes de interface web, a Rotas do dia fora do menu (era um aviso para
programador) e a Visão do responsável > Por responsável como QUADRO COMPARATIVO (uma linha por pessoa, as três frentes
em coluna, o "Focar primeiro" ao lado do nome, a legenda das cores uma vez só) com a "Parada agora" numa linha."""
import re
from pathlib import Path

from test_campo_responsaveis import banco, manut, tela  # noqa: F401

from nexus.torres import campo as TC

RAIZ = Path(__file__).resolve().parent.parent / "nexus"
URL = "/t/campo/responsaveis?modo=cartoes&responsavel=*"


# ── os ajustes técnicos ───────────────────────────────────────────────────────────────────────────────────────────────
def test_reticencias_de_verdade_nas_mensagens_de_carregamento():
    js = (RAIZ / "torres/campo/templates/campo/_ronda_fotos_caixa.html").read_text(encoding="utf-8")
    assert "Fracttal…'" in js and "carregando…'" in js
    assert "Fracttal...'" not in js and "carregando...'" not in js


def test_o_foco_do_teclado_nao_some_e_os_titulos_nao_deixam_palavra_sozinha():
    css = (RAIZ / "static/campo.css").read_text(encoding="utf-8")
    assert ".cn-evolucao .cn-ponto{outline:none}" not in css
    assert re.search(r"\.cn-evolucao \.cn-ponto:focus-visible[^{]*\{[^}]*stroke", css)
    assert re.search(r"\.cn-titulo[^{]*\{[^}]*text-wrap:balance", css)


def test_o_navegador_sabe_que_o_tema_e_escuro_ou_claro():
    """A barra de rolagem, os campos e as listas nativas seguem o tema (`color-scheme`), e a barra do navegador no
    celular tem a cor do fundo (`theme-color`)."""
    css = (RAIZ / "static/nexus.css").read_text(encoding="utf-8")
    assert "html{color-scheme:dark}" in css and 'html[data-tema="claro"]{color-scheme:light}' in css
    base = (RAIZ / "templates/base.html").read_text(encoding="utf-8")
    assert '<meta name="theme-color"' in base


# ── Rotas do dia ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_rotas_do_dia_sai_do_menu_ate_existir(logado):
    """Estava no menu e mostrava "Para construir esta tela, crie a view em nexus/torres/campo/": aviso para
    programador. Sai do menu; o endereço guardado leva à Central, como as outras telas que saíram."""
    assert "rotas" not in {t.id for t in TC.TORRE.telas}
    r = logado.get("/t/campo/rotas")
    assert r.status_code == 302 and r.headers["Location"].endswith("/t/campo/atencao")
    assert "Rotas do dia" not in logado.get("/t/campo/atencao").get_data(as_text=True)


# ── o quadro comparativo ──────────────────────────────────────────────────────────────────────────────────────────────
def _quadro(html):
    i = html.index('<table class="cr-quadro"')
    return html[i:html.index("</table>", i)]


def test_por_responsavel_e_um_quadro_com_uma_linha_por_pessoa(manut, logado):
    html = logado.get(URL).get_data(as_text=True)
    q = _quadro(html)
    cab = q[:q.index("</thead>")]
    for coluna in ("Responsável", "Focar primeiro", "Performance", "Acompanhamento", "Manutenção"):
        assert coluna in cab, coluna
    # o número de cada frente diz o que é uma vez, no cabeçalho, e não em cada linha
    assert "meta do mês" in cab and "rondas pendentes" in cab and "tarefas atrasadas" in cab
    linhas = re.findall(r"<tr class=\"cr-qlin[^\"]*\">", q)
    assert len(linhas) >= 2 and "Ciclano Chefe" in q
    # (o `data-rot` de cada célula é o rótulo do celular, onde cada linha vira um bloco e o cabeçalho some)
    a_vista = re.sub(r' data-rot="[^"]*"', "", q)
    assert a_vista.count("rondas pendentes") == 1 and a_vista.count("Meta do mês") == 0
    # os cartões de antes saíram: nem o bloco, nem a borda vermelha em todo mundo
    assert 'class="cn-equipes"' not in html and "cr-card-bloco" not in html and "cn-equipe--critico" not in html


def test_a_legenda_das_cores_aparece_uma_vez(manut, logado):
    html = logado.get(URL).get_data(as_text=True)
    assert html.count('class="cr-quadro-leg"') == 1
    leg = html[html.index('class="cr-quadro-leg"'):][:400]
    assert "focar" in leg and "acompanhar" in leg and "em dia" in leg
    assert "cr-tri-leg" not in _quadro(html)


def test_o_focar_primeiro_fica_ao_lado_do_nome_e_a_linha_abre_as_usinas(manut, logado):
    html = logado.get(URL + "&filtro=manut.atrasadas&bloco=perf").get_data(as_text=True)
    q = _quadro(html)
    assert "Primeiro: " not in html
    links = re.findall(r'<a class="cr-qquem" href="([^"]*)"', q)
    assert links and all("responsavel=" in h and "filtro=" not in h and "bloco=" not in h for h in links)
    # cada linha: quem, o foco e as três frentes, com a barra que diz quantas usinas em cada nível
    linha = q[q.index('class="cr-qlin'):]
    linha = linha[:linha.index("</tr>")]
    assert linha.count('class="cr-qbar"') == 3 and 'class="cr-qfoco"' in linha
    assert re.search(r'aria-label="\d+ para focar, \d+ para acompanhar e \d+ em dia"', linha)


def test_o_que_sai_da_frente_fica_no_clique(manut, logado):
    """Abaixo da meta, chamados, tarefas pausadas e a semana passada saem do quadro (ficam nas usinas da pessoa); a
    disponibilidade, a PT parada e o extintor vencido só aparecem quando a régua de sempre os pinta de crítico."""
    q = _quadro(logado.get(URL).get_data(as_text=True))
    for fora in ("Abaixo da meta", "Chamados", "Tarefas pausadas", "Semana passada"):
        assert fora not in q, fora


def test_a_parada_agora_numa_linha_com_o_total_e_a_lista_no_clique(manut, logado):
    html = logado.get(URL).get_data(as_text=True)
    i = html.index('<details class="cr-parada"')
    faixa = html[i:html.index("</details>", i)]
    resumo = faixa[:faixa.index("</summary>")]
    assert re.search(r"<b>1</b>\s*<span>parada agora</span>", resumo)
    assert "a mais antiga" not in resumo and "Altair" in resumo and "13002" in resumo      # uma só: ela inteira
    assert faixa.count("<li>") == 0


# ── a 2ª entrega: o Painel e a Visão geral ────────────────────────────────────────────────────────────────────────────
def test_no_painel_a_parada_agora_tambem_e_uma_linha(manut, logado):
    """No Painel a faixa era um bloco vermelho com todas as paradas em texto corrido (18 na visão de todos, 12/11/2026),
    e os dois números ao lado esticavam vazios até a altura dele. Agora a mesma linha das outras abas (o total, a mais
    antiga, a lista inteira no clique: nada fica de fora) e os números com a altura deles."""
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=painel").get_data(as_text=True)
    topo = html[html.index('class="pn-topo"'):]
    topo = topo[:topo.index('class="pn"')]
    assert '<details class="cr-parada"' in topo and 'class="cr-parada" role="status"' not in html
    assert "Altair" in topo and "13002" in topo
    css = (RAIZ / "static/campo.css").read_text(encoding="utf-8")
    assert re.search(r"\.pn-topo\{[^}]*align-items:flex-start", css)


def test_na_visao_geral_os_numeros_do_bloco_nao_sao_caixas_e_a_lista_so_pinta_o_fora_da_regua():
    """Eram 12 caixas de número dentro de 3 cartões (caixa dentro de caixa) e, na lista, toda célula colorida (13 por
    linha): o olho não achava o problema. O número do bloco fica sem caixa (só o escolhido como filtro se destaca) e, na
    lista, o valor em dia fica sem fundo: a cor é do crítico e da atenção."""
    css = (RAIZ / "static/campo.css").read_text(encoding="utf-8")
    kpi = re.search(r"\n\.cr-gr-kpi\{([^}]*)\}", css).group(1)
    assert "border:1px solid" not in kpi and "background:var(--superficie-2)" not in kpi
    em_dia = re.search(r"\.cr-gr-lista \.cr-v--ok\{([^}]*)\}", css).group(1)
    assert "background:none" in em_dia and "color:var(--tinta-2)" in em_dia


def test_a_procedencia_da_manutencao_mora_no_ponto_de_exclamacao(manut, logado):
    """O parágrafo "A semana vem do arquivo do PCM..." morava dentro do cartão Manutenção: é procedência, vai para o "!"
    do título, com as outras."""
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True)
    assert 'class="cr-nota-bloco"' not in html
    i = html.index('<details class="gc-explica">')
    explica = html[i:html.index("</details>", i)]
    assert "A semana vem do arquivo do PCM" in explica

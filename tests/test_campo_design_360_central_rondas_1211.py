"""A revisão de desenho da Usinas 360°, 3ª entrega (12/11/2026): a Central de atenção e as Rondas, cada número com a
sua tela dona. A proposta ao Levi: "'Nunca tiveram ronda' e 'rondas pendentes' estão hoje nas duas telas. Central fica
com o que está pendente (quem está sem ronda). Rondas fica só com o que foi feito (cobertura, duração e qualidade)";
a resposta: "ok". Banco falso do test_campo_visao."""
import re

from test_campo_visao import banco  # noqa: F401  (fixture)


# ── a Central de atenção ──────────────────────────────────────────────────────────────────────────────────────────────
def test_a_procedencia_da_central_mora_no_ponto_de_exclamacao(banco, logado):
    """O canto do título dizia "rondas e PT do App + cadastro do Nexus / lido às HH:MM" e, em letra de código, "fato_ronda
    calculado na hora; o banco tem a carga das...". É procedência: vai para o "!" (como na Aprovação, nas Rondas, no
    Mapa de equipe e na Central da usina, que já não têm o `cn-frescor`)."""
    for url in ("/t/campo/atencao", "/t/campo/atencao?vista=pt"):
        html = logado.get(url).get_data(as_text=True)
        assert 'class="cn-frescor"' not in html, url
        i = html.index('<details class="gc-explica">')
        assert "Lido às" in html[i:html.index("</details>", i)], url


def test_o_cartao_do_responsavel_sem_a_lista_de_equipes(banco, logado):
    """Cada cartão escrevia todas as equipes da pessoa ("BA Sul 01, ES Norte 01, MA Leste 01..."): ruído; fica a conta
    ("12 equipes"), e as equipes estão no kanban dela."""
    for url in ("/t/campo/atencao", "/t/campo/atencao?vista=pt"):
        html = logado.get(url).get_data(as_text=True)
        assert 'class="cn-equipe cn-equipe--min' in html and "cn-sup-equipes" not in html, url
        assert re.search(r"\d+ equipes?</span>", html), url


def test_o_total_das_pendentes_com_a_composicao(banco, logado):
    """Eram quatro números do mesmo peso (84, 15, 46, 23) sem dizer que o 1º é a soma dos outros. Agora o total grande e,
    ao lado, a barra da composição com os três motivos; cada um segue filtrando a tabela."""
    html = logado.get("/t/campo/atencao").get_data(as_text=True)
    assert 'class="cn-numeros cn-numeros--filtro"' not in html
    comp = html[html.index('<div class="cn-comp">'):]
    comp = comp[:comp.index("<!-- /cn-comp -->")]
    assert 'class="cn-comp-total"' in comp and 'class="cn-comp-barra"' in comp
    assert "pedindo ronda" in comp
    partes = re.findall(r'<a class="cn-comp-parte[^"]*" href="([^"]*)"', comp)
    assert len(partes) == 3 and all("modo=tabela" in h for h in partes)
    assert [re.search(r"f=(\w+)", h).group(1) for h in partes] == ["nunca", "sem_ronda", "longa_pendente"]


# ── as Rondas ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_as_rondas_ficam_com_o_que_foi_feito_e_levam_a_central_pelo_pendente(banco, logado):
    html = logado.get("/t/campo/rondas").get_data(as_text=True)
    faixa = html.split('class="cn-numeros cn-numeros--filtro rd-numeros">', 1)[1].split("</div>", 1)[0]
    for feito in ("Rondas finalizadas", "Cobertura de usinas", "Qualidade média", "Duração média"):
        assert feito in faixa, feito
    assert "Nunca tiveram ronda" not in faixa and "Usina mais atrasada" not in faixa
    # o pendente tem a tela dona dele: uma linha diz o total daqui e leva até lá
    pend = html[html.index('class="rd-pend"'):][:600]
    assert "/t/campo/atencao" in pend and "Central de atenção" in pend
    assert re.search(r"<b>1</b> usina nunca teve ronda", pend)                 # a Coração 1 do banco falso
    # quem quiser a lista aqui continua tendo o "Mostrar" dos Filtros
    assert 'value="nunca"' in html

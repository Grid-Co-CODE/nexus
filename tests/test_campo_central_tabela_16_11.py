"""A Central de atenção por responsável em tabela, uma linha por responsável (Levi, 16/11/2026: "Central de atenção em
formato de tabela por linhas!"). Eram cartões (um por Responsável UFV) nas duas abas; a aba das PT é o mesmo pedaço da
Segurança > APR e PT (Levi, 05/10/2026: "a mesma tela do Central de atenção > Permissões de Trabalho"), que vira tabela
junto. A linha leva aonde o cartão levava: nas rondas, ao kanban da pessoa; nas PT, à tabela das PT dela. A cor segue só
no ponto ao lado da palavra (Levi, 03/11/2026: "dói é os olhos!"). Banco falso do test_campo_visao."""
import re

from test_campo_visao import banco  # noqa: F401  (fixture)


def _tabela(html):
    m = re.search(r'<table class="cn-resp-tab">.*?</table>', html, re.S)
    return m.group(0) if m else ""


def _cab(t):
    return [re.sub(r"<[^>]+>", "", x).strip() for x in re.findall(r"<th[^>]*>(.*?)</th>", t, re.S)]


def test_as_rondas_por_responsavel_numa_tabela(banco, logado):
    html = logado.get("/t/campo/atencao").get_data(as_text=True)
    t = _tabela(html)
    assert _cab(t) == ["Responsável UFV", "Usinas", "Pendentes", "Nunca teve ronda", "Sem ronda", "Ronda longa pendente",
                       "Em dia"]
    linhas = re.findall(r'<tr class="cn-resp-linha[^"]*" data-href="([^"]+)"', t)
    assert linhas and all("responsavel=" in h for h in linhas)
    # sem os cartões
    assert 'class="cn-equipe' not in html and 'class="cn-equipes"' not in html
    # a cor só no ponto: nada de número ou fundo colorido
    assert "cn-t-critico" not in t and "critico-cheio" not in t and 'class="cn-min-st cn-min-st--' in t


def test_a_linha_das_rondas_leva_ao_kanban_da_pessoa(banco, logado):
    t = _tabela(logado.get("/t/campo/atencao").get_data(as_text=True))
    nome = re.search(r'<a class="cn-resp-nome" href="([^"]+)">', t).group(1).replace("&amp;", "&")
    assert "responsavel=" in nome
    kanban = logado.get("/t/campo/atencao" + nome).get_data(as_text=True)
    assert 'class="cn-kanban"' in kanban


def test_as_pt_por_responsavel_numa_tabela_e_a_linha_leva_as_pt_dela(banco, logado):
    for base in ("/t/campo/atencao?vista=pt", "/t/hseq/apr-pt"):
        html = logado.get(base).get_data(as_text=True)
        t = _tabela(html)
        assert _cab(t) == ["Responsável UFV", "PT esperando", "Paradas há mais de 2 h", "Aguardando", "Usinas",
                           "Equipes"], base
        assert 'class="cn-equipe cn-equipe--min' not in html, base
        assert '<span class="cn-min-st cn-min-st--critico">1</span>' in t, base          # a parada: o ponto e o número
        href = re.search(r'<a class="cn-resp-nome" href="([^"]+)">', t).group(1).replace("&amp;", "&")
        assert "modo=tabela" in href and "responsavel=" in href, base
        tabela = logado.get(base.split("?")[0] + href).get_data(as_text=True)
        assert 'class="cn-link cn-os"' in tabela, base

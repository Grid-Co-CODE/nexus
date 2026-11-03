"""Rondas enxuta, pedido do Levi de 03/11/2026 (Nexus > Campo · App > Rondas: "tem filtro em cima e filtro na tabela, tá
uma bagunça"; "Menos é mais!"): sem o filtro de dias e de 300 em 300; os filtros num painel escondido, no modelo do
Histórico do OS Creator Web, com uma etiqueta por filtro; os indicadores juntos numa faixa; a duração e a pendência no
cabeçalho da coluna; sem o Painel, a Sujidade e vegetação e o Quem ronda; a Sem ronda como filtro dos Registros; o
"Buscar por usina" que leva à página da usina; e, na usina, a evolução por mês, os números juntos e o "De onde vem" na
exclamação amarela. Banco falso (pg_falso) do test_campo_visao."""
import re
from pathlib import Path

from test_campo_visao import _dia, banco  # noqa: F401  (fixture)

from nexus.campo import visao


def _tabela(html):
    """A parte das abas: a página leva também a lista do "Buscar por usina", com todas as usinas."""
    return html.split('<section class="cn-painel">', 1)[1]


def test_sem_filtro_de_dias_e_a_tabela_de_300_em_300(banco, logado, monkeypatch):
    html = logado.get("/t/campo/rondas").get_data(as_text=True)
    assert "últimos 7 dias" not in html and "dias=" not in html and "nos últimos 30 dias" in html
    # o dias=7 de um link antigo não muda nada: o período é fixo
    assert logado.get("/t/campo/rondas?dias=7").get_data(as_text=True).count("<h2>Rondas diárias</h2>") == 1
    # de 300 em 300: com a página de 2, as 3 rondas do banco falso vão em duas páginas
    from nexus.torres import campo
    monkeypatch.setattr(campo, "LIMITE_LINHAS", 2)
    p1 = logado.get("/t/campo/rondas").get_data(as_text=True)
    assert "página 1 de 2" in p1 and 'href="?pag=2"' in p1 and _tabela(p1).count('class="cn-pessoa"') == 2
    p2 = logado.get("/t/campo/rondas?pag=2").get_data(as_text=True)
    assert "página 2 de 2" in p2 and _tabela(p2).count('class="cn-pessoa"') == 1 and "2 anteriores" in p2


def test_os_filtros_moram_no_painel_escondido_com_uma_etiqueta_por_filtro(banco, logado):
    html = logado.get("/t/campo/rondas").get_data(as_text=True)
    painel = html.split('<div class="rd-painel" id="rd-painel" role="dialog" aria-label="Filtros" hidden>', 1)[1].split('<div class="rd-rodape">', 1)[0]
    assert re.findall(r'<select class="gc-campo" name="(\w+)"', painel) == [
        "cob", "regiao", "cliente", "usina", "responsavel", "equipe", "regiao_campo", "gestor"]
    assert "onchange" not in painel                                # só vale no Aplicar
    assert ">Aplicar</button>" in html and "data-rd-limpar" in html and 'class="rd-etiquetas"' not in html
    # aplicado: a contagem no botão e uma etiqueta por filtro, com o × que tira só aquele
    h = logado.get("/t/campo/rondas?cliente=Thopen&equipe=SP+Norte+01&dur=curta").get_data(as_text=True)
    assert '<span class="rd-badge">2</span>' in h
    etiquetas = re.findall(r'<a class="rd-etiqueta" href="([^"]+)"[^>]*>([^<]+)<b>([^<]+)</b>', h)
    assert [(rot.strip(), val) for _href, rot, val in etiquetas] == [
        ("Cliente:", "Thopen"), ("Equipe:", "SP Norte 01"), ("Duração:", "abaixo de 10 min")]
    assert [href for href, _r, _v in etiquetas] == ["?equipe=SP+Norte+01&amp;dur=curta",
                                                    "?cliente=Thopen&amp;dur=curta", "?cliente=Thopen&amp;equipe=SP+Norte+01"]
    # a região de campo que vem do login sai com o "*" (todas), como a opção da lista
    h = logado.get("/t/campo/rondas?regiao_campo=Sudeste+03").get_data(as_text=True)
    assert 'href="?regiao_campo=%2A"' in h and "Região de campo: <b>Sudeste 03 · Supervisora Campo</b>" in h
    assert "Limpar tudo" in h


def test_a_duracao_e_a_pendencia_se_escolhem_no_cabecalho(banco, logado):
    html = logado.get("/t/campo/rondas").get_data(as_text=True)
    dur = html.split('<th class="rd-th" data-ordem-menu', 1)[1].split("</th>", 1)[0]
    assert 'data-ordenar="desc">Mais longa primeiro' in dur and 'data-ordenar="asc">Mais curta primeiro' in dur
    assert 'href="?dur=curta"' in dur and 'href="?dur=longa"' in dur and 'aria-current="true">Toda duração' in dur
    pend = html.split('<th class="rd-th" data-sem-ordem>', 1)[1].split("</th>", 1)[0]
    assert 'href="?pend=sem_os"' in pend and 'href="?pend=incompleta"' in pend and "<b>1</b>" in pend
    # os botões de cima saíram ("tem filtro em cima e filtro na tabela")
    assert "Toda duração</a>" not in html.split("<thead>", 1)[0] and 'class="cn-seg"' not in html
    # o menu ordena pela mesma ordem do clique no cabeçalho
    assert "th._ordenar = function (desc)" in html and "if (th.hasAttribute('data-ordem-menu')) return;" in html
    marcado = logado.get("/t/campo/rondas?dur=longa").get_data(as_text=True)
    assert '<summary class="rd-menu-ativo">Duração' in marcado


def test_buscar_por_usina_leva_a_pagina_dela(banco, logado):
    html = logado.get("/t/campo/rondas?cliente=Outro+Cliente").get_data(as_text=True)
    lista = html.split('<ul class="rd-usinas" id="rd-usinas" role="listbox"', 1)[1].split("</ul>", 1)[0]
    # todas as usinas, sem os filtros (buscar é ir à usina), na lista do Nexus com o cliente e a UF (03/11/2026: "essa
    # lista está mal formatada, quero estilo nexus")
    assert re.findall(r'<li role="option" id="rd-us-(\d+)" data-href="/t/campo/rondas/usina/\d+"><b>([^<]+)</b><span>([^<]+)</span>', lista) == [
        ("1", "Altair", "Thopen · SP"), ("2", "Brodowski 1", "Thopen · SP"), ("3", "Coração 1", "Outro Cliente · SC")]
    assert "<datalist" not in html and 'role="combobox"' in html and "Nenhuma usina com esse nome" in lista
    # sem o script: o nome igual (sem acento nem caixa) ou o único que contém vai à usina; senão, a busca da tabela
    assert logado.get("/t/campo/rondas/buscar-usina?nome=coracao+1").headers["Location"] == "/t/campo/rondas/usina/3"
    assert logado.get("/t/campo/rondas/buscar-usina?nome=brodow").headers["Location"] == "/t/campo/rondas/usina/2"
    assert logado.get("/t/campo/rondas/buscar-usina?nome=Xique").headers["Location"] == "/t/campo/rondas?q=Xique"


def test_o_como_ler_e_o_de_onde_vem_na_exclamacao_amarela(banco, logado):
    html = logado.get("/t/campo/rondas").get_data(as_text=True)
    titulo = html.split('<div class="hs-titulo"><h1 class="cn-titulo">Rondas</h1>', 1)[1].split("</details>", 1)[0]
    assert '<details class="hs-aviso"><summary class="hs-aviso-bt" title="Como ler as Rondas"' in titulo
    assert "De onde vem" in titulo and "lido às" in titulo and 'class="cn-entenda"' not in html
    assert "hseq.css" in html and 'class="cn-barra-fonte"' not in html
    pag = logado.get("/t/campo/rondas/usina/1").get_data(as_text=True)
    assert '<summary class="hs-aviso-bt" title="De onde vem"' in pag and "lido às" in pag
    assert 'class="cn-frescor"' not in pag and "<b>De onde vem.</b>" not in pag      # nem no canto, nem no fim
    # os números juntos numa faixa, nas duas páginas
    assert 'class="cn-numeros cn-numeros--filtro rd-numeros"' in html and 'class="cn-kpi' not in html
    assert '<div class="cn-numeros rd-numeros">' in pag and 'class="cn-kpi' not in pag


def test_a_evolucao_da_usina_nos_ultimos_30_dias(banco, logado, monkeypatch):
    """Levi, 03/11/2026, depois de ver o filtro de mês: "Quando clica na usina deixa os últimas 30 dias, melhor que por
    mês". A tabela segue com os 90 dias."""
    from datetime import timedelta
    from nexus.campo import ronda_checklist
    monkeypatch.setattr(ronda_checklist, "respostas", lambda: {"500": {"sujidade": 4, "vegetacao": 2}})
    pag = logado.get("/t/campo/rondas/usina/1").get_data(as_text=True)
    assert 'id="rd-mes"' not in pag and "últimos 30 dias" in pag and pag.count('class="cn-ponto"') == 2
    hoje = visao._agora().date()
    base = visao.rondas().dados["todas"][0]

    def leituras(*dias):
        return lambda todas, resp, uid, validacoes=(): [
            dict(base, data=(hoje - timedelta(days=n)).isoformat(), sujidade=3, vegetacao=1, lida=True, os=str(900 + n),
                 sensores_sujos=[], vala="") for n in dias]
    # a de 31 dias fica de fora da evolução e na tabela; a de 30, dentro
    monkeypatch.setattr(visao, "historico_usina", leituras(30, 31))
    pag = logado.get("/t/campo/rondas/usina/1").get_data(as_text=True)
    assert pag.count('class="cn-ponto"') == 1 and 'data-x="380.0"' in pag             # uma leitura só fica no meio
    monkeypatch.setattr(visao, "historico_usina", leituras(31, 40))
    pag = logado.get("/t/campo/rondas/usina/1").get_data(as_text=True)
    assert "Nenhuma leitura de sujidade e vegetação nos últimos 30 dias." in pag and 'class="cn-ponto"' not in pag
    assert pag.count('class="rd-linha"') == 2                                         # a tabela segue com as duas


def test_a_linha_abre_a_barra_lateral_com_tudo_da_ronda(banco, logado, monkeypatch):
    """Levi, 03/11/2026: "Tira esse botão 'Fotos' ao clicar na linha já abre uma barra lateral mostrando tudo da ronda, a
    barra pode representar 1/3 do tamanho da tela. Ficará do lado direito! Não irá mais abrir abaixo da linha"."""
    from nexus.campo import ronda_checklist
    monkeypatch.setattr(ronda_checklist, "respostas", lambda: {"500": {"sujidade": 4, "vegetacao": 2, "vala": "Parcial",
                                                                       "sensores_sujos": ["IPOA"]}})
    det = logado.get(f"/t/campo/rondas/usina/1/ronda?os=500&data={_dia(1)}").get_data(as_text=True)
    for txt in ("Altair", "Fulano Souza", "07:00 às 08:00", "Sujidade dos módulos", "cn-nivel-txt--4", "Parcial",
                "IPOA sujo", "ronda longa pendente", "item sem foto de evidência", 'data-fotos-url="/t/campo/rondas/os/500/fotos"'):
        assert txt in det, txt
    # sem OS: pelo dia e pela hora do início; a que não existe diz isso
    assert "as fotos ficam só no App" in logado.get(f"/t/campo/rondas/usina/2/ronda?data={_dia(2)}&ini=07:00").get_data(as_text=True)
    assert "Não achei esta ronda" in logado.get("/t/campo/rondas/usina/1/ronda?os=999&data=2026-01-01").get_data(as_text=True)
    # a barra: 1/3 da tela, à direita; no celular, a tela inteira
    css = (Path(__file__).resolve().parents[1] / "nexus" / "static" / "campo.css").read_text(encoding="utf-8")
    assert ".rd-gaveta{position:fixed;z-index:60;top:0;right:0;bottom:0;display:flex;flex-direction:column;width:33.333vw" in css
    assert "@media (max-width:900px){.rd-gaveta{width:100vw;min-width:0}}" in css

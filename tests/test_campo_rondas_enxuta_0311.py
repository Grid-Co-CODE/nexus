"""Rondas enxuta, pedido do Levi de 03/11/2026 (Nexus > Campo · App > Rondas: "tem filtro em cima e filtro na tabela, tá
uma bagunça"; "Menos é mais!"): sem o filtro de dias e de 300 em 300; os filtros num painel escondido, no modelo do
Histórico do OS Creator Web, com uma etiqueta por filtro; os indicadores juntos numa faixa; a duração e a pendência no
cabeçalho da coluna; sem o Painel, a Sujidade e vegetação e o Quem ronda; a Sem ronda como filtro dos Registros; o
"Buscar por usina" que leva à página da usina; e, na usina, a evolução por mês, os números juntos e o "De onde vem" na
exclamação amarela. Banco falso (pg_falso) do test_campo_visao."""
import re

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
    lista = html.split('<datalist id="rd-usinas">', 1)[1].split("</datalist>", 1)[0]
    # todas as usinas, sem os filtros (buscar é ir à usina)
    assert re.findall(r'<option value="([^"]+)" data-href="/t/campo/rondas/usina/(\d+)">', lista) == [
        ("Altair", "1"), ("Brodowski 1", "2"), ("Coração 1", "3")]
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


def test_a_evolucao_da_usina_vem_por_mes_aberta_no_de_agora(banco, logado, monkeypatch):
    from nexus.campo import ronda_checklist
    monkeypatch.setattr(ronda_checklist, "respostas", lambda: {"500": {"sujidade": 4, "vegetacao": 2}})
    agora = visao._agora().strftime("%Y-%m")
    pag = logado.get("/t/campo/rondas/usina/1").get_data(as_text=True)
    sel = pag.split('<select class="gc-campo" id="rd-mes" name="mes"', 1)[1].split("</select>", 1)[0]
    assert re.search(rf'<option value="{agora}" selected>', sel)                # o mês de agora, de início
    meses = re.findall(r'<option value="(\d{4}-\d{2})"', sel)
    assert meses == sorted({agora, _dia(1)[:7], _dia(3)[:7]}, reverse=True)
    n_agora = sum(1 for d in (_dia(1), _dia(3)) if d[:7] == agora)
    assert pag.count('class="cn-ponto"') == n_agora
    # o mês de agora sem leitura diz isso (e o mês da leitura fica na lista); um mês com uma leitura só põe o ponto no meio
    from datetime import date, timedelta
    antes = (date.fromisoformat(agora + "-01") - timedelta(days=1)).strftime("%Y-%m")
    base = visao.rondas().dados["todas"][0]

    def uma_leitura(mes):
        return lambda todas, resp, uid, validacoes=(): [dict(base, data=f"{mes}-02", sujidade=3, vegetacao=1, lida=True,
                                                            os="901", sensores_sujos=[], vala="")]
    monkeypatch.setattr(visao, "historico_usina", uma_leitura(antes))
    vazio = logado.get("/t/campo/rondas/usina/1").get_data(as_text=True)
    assert "Nenhuma leitura de sujidade e vegetação em" in vazio and 'class="cn-ponto"' not in vazio
    assert f'<option value="{antes}">' in vazio
    assert logado.get(f"/t/campo/rondas/usina/1?mes={antes}").get_data(as_text=True).count('class="cn-ponto"') == 1
    monkeypatch.setattr(visao, "historico_usina", uma_leitura(agora))
    um = logado.get("/t/campo/rondas/usina/1").get_data(as_text=True)
    assert um.count('class="cn-ponto"') == 1 and 'data-x="380.0"' in um

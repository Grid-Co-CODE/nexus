"""Gestão PCM, a tela (parte B do pedido do Levi de 04/11/2026): o cabeçalho com os quatro números, a barra de filtros
recolhível com as listas de várias escolhas, o Plano & Fila, as "Não finalizadas no período", a árvore por cliente, o Só
atrasadas em partes e os dois blocos da confiabilidade fechados. A estrutura é a da aba Gestão PCM do painel do PCM; o
visual, o do Nexus. As contas são as da parte A (`nexus/pcm/gestao.py`, provadas contra o painel).

Nada vai à rede: a fonte é um arquivo local no formato do gestao_pcm.json; os nomes são fictícios.
"""
import json
import re
from pathlib import Path

import pytest
from werkzeug.datastructures import MultiDict

from nexus.pcm import gestao as G
from test_pcm_gestao_filtros import A1, A2, B1, t, tarefas

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture
def fonte(app, tmp_path, request):
    def gravar(ts, hash_=None):
        p = tmp_path / "gestao_pcm.json"
        p.write_text(json.dumps({"geradoEm": "2026-11-04T20:50:31", "corteData": "2026-01-01", "diasAlerta": 10,
                                 "dataHash": hash_ or ("tela-" + request.node.name + str(len(ts))), "tarefas": ts}),
                     encoding="utf-8")
        app.config["NEXUS_PCM_GESTAO_FONTE"] = str(p)
    gravar(tarefas())
    return gravar


def _html(logado, q=""):
    r = logado.get("/t/pcm/gestao" + q)
    assert r.status_code == 200, q
    return r.get_data(as_text=True)


def _trecho(html, inicio, fim):
    return html.split(inicio, 1)[1].split(fim, 1)[0]


# ── o cabeçalho ──────────────────────────────────────────────────────────────────────────────────────────────
def test_cabecalho_com_a_linha_do_atualizado_e_os_quatro_numeros(logado, fonte):
    html = _html(logado)
    assert '<h1 class="titulo-pagina">Gestão PCM</h1>' in html
    assert "Atualizado: 04/11/2026, 17:50:31 · corte 01/01/2026 · fonte: API Fracttal" in html
    nums = _trecho(html, '<div class="pgn"', '<section class="pgf"')
    assert re.search(r'Visíveis</span>\s*<b class="gc-num">6</b>', nums)
    assert re.search(r'Em aberto</span>\s*<b class="gc-num">4</b>', nums)
    # Finalizadas em verde, com a dica do painel (a mesma função que a prova confere contra ele)
    numeros = G.aba(G.escopo(tarefas()), 10)["numeros"]
    dica = G.dica_finalizadas(numeros)
    assert dica == ('Estado da Tarefa = Finalizada · 33% do que está visível (as 1 de "Não Finalizadas no Período" '
                    'ficam fora desta conta)')
    assert 'class="pgn-n pgn-n--ok" title="' + dica.replace('"', "&#34;") + '"' in nums
    # Atrasadas em vermelho: um link que liga o Só atrasadas, e marcado quando ligado
    atr = re.search(r'<a class="pgn-n pgn-n--crit[^"]*" href="([^"]*)"([^>]*)>', nums)
    assert atr and atr.group(1) == "?atr=1" and "aria-current" not in atr.group(2)
    nums = _trecho(_html(logado, "?atr=1&cliente=Cliente+A"), '<div class="pgn"', '<section class="pgf"')
    atr = re.search(r'<a class="pgn-n pgn-n--crit[^"]*" href="([^"]*)"([^>]*)>', nums)
    assert atr.group(1) == "?cliente=Cliente+A" and 'aria-current="true"' in atr.group(2)
    assert G.dica_finalizadas({"pct_finalizadas": 50, "nf": 0}) == "Estado da Tarefa = Finalizada · 50% do que está visível"


# ── a barra de filtros ───────────────────────────────────────────────────────────────────────────────────────
def test_a_barra_de_filtros_vem_fechada_com_os_escolhidos_em_etiquetas(logado, fonte):
    html = _html(logado, "?cliente=Cliente+A&cliente=Cliente+B&estado=Pausada&os=100&modo=fila")
    barra = _trecho(html, '<section class="pgf"', "</section>")
    bt = re.search(r'<button type="button" class="pgf-abre"[^>]*>', barra).group(0)
    assert 'aria-expanded="false"' in bt and 'aria-controls="pgf-corpo"' in bt
    assert re.search(r'<form class="pg-filtros pgf-corpo" id="pgf-corpo"[^>]*hidden', barra)    # fechada por padrão
    assert "4 filtros" in barra
    # cada etiqueta tira só o escolhido dela (o resto da URL fica)
    tirar = dict(re.findall(r'<a class="pgf-x" href="([^"]*)" aria-label="Tirar ([^"]*)"', barra)[i][::-1]
                 for i in range(4))
    assert tirar["Cliente: Cliente A"] == "?cliente=Cliente+B&amp;estado=Pausada&amp;os=100&amp;modo=fila"
    assert tirar["Estado: Pausada"] == "?cliente=Cliente+A&amp;cliente=Cliente+B&amp;os=100&amp;modo=fila"
    assert tirar["OS: 100"] == "?cliente=Cliente+A&amp;cliente=Cliente+B&amp;estado=Pausada&amp;modo=fila"
    # sem filtro, nenhum escolhido
    barra = _trecho(_html(logado), '<section class="pgf"', "</section>")
    assert "nenhum filtro" in barra and 'class="pgf-x"' not in barra


def test_as_sete_listas_de_varias_escolhas_na_ordem_do_painel(logado, fonte):
    html = _html(logado, "?cliente=Cliente+A&estado=pausada&estado=Em+progresso")
    barra = _trecho(html, '<section class="pgf"', "</section>")
    rotulos = re.findall(r'<span class="pgf-rot" id="pgf-l-(\w+)">([^<]*)</span>', barra)
    assert rotulos[:7] == [("cliente", "Cliente"), ("usina", "Usina"), ("cluster", "Equipe cluster"),
                           ("responsavel", "Responsável O&amp;M"), ("tipo_tarefa", "Tipo"), ("etiqueta", "Etiqueta"),
                           ("estado", "Estado")]
    # o botão diz "Todos", o valor escolhido ou "N selecionados"; abre o painel (aria-expanded, o padrão de revelar)
    # com busca e caixinhas
    assert re.search(r'id="pgf-v-cliente">Cliente A</span>', barra)
    assert re.search(r'id="pgf-v-usina">Todas</span>', barra)
    assert re.search(r'id="pgf-v-estado">2 selecionados</span>', barra)
    ms = _trecho(barra, 'data-nome="estado"', "</div>\n    </div>")
    assert '<button type="button" class="pgf-ms-bt" aria-expanded="false" aria-controls="pgf-p-estado"' in barra
    assert re.search(r'<div class="pgf-ms-painel" id="pgf-p-estado" role="group"[^>]*hidden>', barra)
    assert re.search(r'<input type="checkbox" name="estado" value="Pausada" checked>', barra)
    assert re.search(r'<input type="checkbox" name="estado" value="Em progresso" checked>', barra)
    assert re.search(r'<input type="checkbox" name="estado" value="Não Iniciada">', barra)
    assert 'class="gc-campo pgf-ms-busca"' in ms and 'data-ms="todos">Todos</button>' in ms
    assert 'data-ms="limpar">Limpar</button>' in ms
    # os filtros de antes saíram do topo: nenhuma lista de uma escolha, e cada filtro uma vez só
    assert '<select class="gc-campo" name="cliente"' not in html
    assert html.count('type="checkbox" name="cliente" value="Cliente A"') == 1
    assert '<input type="hidden" name="cliente"' not in barra                     # nem escondido na barra


def test_os_campos_de_texto_o_periodo_e_os_botoes(app, logado, fonte):
    html = _html(logado, "?os=100&ss=29&pini=2026-10-01&pfim=2026-10-31&pmodo=fim&modo=fila&tipo=prev&q=norte")
    barra = _trecho(html, '<section class="pgf"', "</section>")
    assert re.search(r'<input class="gc-campo" type="text" name="os" value="100"', barra)
    assert re.search(r'<input class="gc-campo" type="text" name="ss" value="29"', barra)
    assert re.search(r'<input class="gc-campo" type="date" name="pini" value="2026-10-01"', barra)
    assert re.search(r'<input class="gc-campo" type="date" name="pfim" value="2026-10-31"', barra)
    pmodo = _trecho(barra, 'name="pmodo"', "</select>")
    assert [v for v, _r in G.PMODOS] == re.findall(r'<option value="(\w+)"', pmodo)
    assert '<option value="fim" selected>' in pmodo
    # o resto da tela (modo, tipo do Plano, busca) vai junto, escondido; os filtros não se repetem escondidos
    assert '<input type="hidden" name="modo" value="fila">' in barra and '<input type="hidden" name="q" value="norte">' in barra
    assert '<input type="hidden" name="os"' not in barra
    # Só atrasadas, Limpar filtros e o Relatório executivo da Central de emissão
    assert re.search(r'<a class="pgf-bt pgf-atr" href="\?os=100[^"]*&amp;atr=1"', barra)
    limpar = re.search(r'<a class="pgf-bt" href="([^"]*)">Limpar filtros</a>', barra).group(1)
    assert limpar == "?modo=fila&amp;tipo=prev"
    assert 'href="/t/relatorios/pcm-executivo"' in barra and "Relatório executivo" in barra


def test_a_busca_do_plano_mora_no_plano_e_leva_os_filtros(logado, fonte):
    html = _html(logado, "?cliente=Cliente+A&q=norte")
    barra = _trecho(html, '<section class="pgf"', "</section>")
    assert 'name="q"' not in barra.replace('<input type="hidden" name="q" value="norte">', "")
    busca = re.search(r'<form class="pg-busca-f"[^>]*>(.*?)</form>', html, re.S).group(1)
    assert 'name="q" value="norte"' in busca and '<input type="hidden" name="cliente" value="Cliente A">' in busca


# ── as árvores ───────────────────────────────────────────────────────────────────────────────────────────────
def test_nao_finalizadas_num_bloco_fechado_com_o_numero_e_a_arvore(logado, fonte):
    html = _html(logado)
    nf = _trecho(html, '<section class="pga-nf" data-arv="nf"', "</section>")
    assert '<details class="pga-bloco">' in nf                                       # FECHADO
    assert re.search(r'Não finalizadas no período</span>\s*<span class="pga-badge[^"]*">1</span>', nf)
    assert re.search(r'<details class="pga-cli" data-ac="Cliente A">', nf)
    assert re.search(r'<details class="pga-usi" data-au="' + re.escape(A2) + '">', nf)
    assert re.search(r'<details class="pga-tip pga-tip--inspecao" data-at="Inspeção">', nf)
    assert '<div class="pga-tab"></div>' in nf                                       # a tabela vem pela rota


def test_a_arvore_por_cliente_abre_sozinha_ate_60_tarefas(logado, fonte):
    html = _html(logado)
    arv = _trecho(html, '<section class="pga" data-arv="todas"', "</section>")
    assert re.search(r'<details class="pga-cli" data-ac="Cliente A" open>', arv)
    assert re.search(r'Cliente A</span>\s*<span class="pga-badge">4</span>', arv)
    # o tipo com as atrasadas em vermelho, e a tabela já na página (o autoOpen do painel)
    prev = _trecho(arv, 'data-at="Preventiva" open>', "</details>")
    assert '<span class="pga-atr">1 atrasada</span>' in prev
    assert "Cabine" in prev and "12d" in prev and 'data-cheio="1"' in prev
    # mais de 60: só as contagens, fechado, e a tabela pela rota
    fonte([t(A1, f"Tarefa {i}", os_=str(5000 + i), wid=5000 + i) for i in range(61)])
    arv = _trecho(_html(logado), '<section class="pga" data-arv="todas"', "</section>")
    assert '<details class="pga-cli" data-ac="Cliente A">' in arv and "Tarefa 1" not in arv
    assert '<div class="pga-tab"></div>' in arv and "pga-atr" not in arv


def test_a_tabela_do_tipo_vira_cartao_no_celular(logado, fonte):
    h = logado.get("/t/pcm/gestao", query_string={"arv": "todas", "ac": "Cliente A", "au": A1,
                                                  "at": "Preventiva"}).get_data(as_text=True)
    assert 'class="pg-tbl pg-arv-tbl pg-cartoes"' in h
    for r in ("OS", "Tarefa", "Estado", "Etiquetas", "Data Prog.", "Data Final", "Dias"):
        assert f'data-r="{r}"' in h
    css = (RAIZ / "nexus" / "static" / "pcm.css").read_text(encoding="utf-8")
    assert re.search(r"\.pg-cartoes td::before\{[^}]*content:attr\(data-r\)", css)


def test_as_mensagens_sao_as_constantes_que_a_prova_confere(logado, fonte):
    assert G.MSG_SEM_TAREFA in _html(logado, "?os=999999")
    fonte([t(A2, "Inspeção visual", tipo="Inspeção", os_="2002", os_status="Finalizados", dias=40, atrasado=True)],
          "so-nf")
    assert G.MSG_SO_NF in _html(logado)
    fonte([t(A1, "Sem atraso", os_="1", dias=1)], "sem-atraso")
    assert G.MSG_SEM_ATRASADA in _html(logado, "?atr=1")


def test_so_atrasadas_no_lugar_das_arvores_em_partes(logado, fonte):
    ts = [t(B1 if i % 2 else A1, f"Tarefa {i:03d}", os_=str(7000 + i), wid=7000 + i, dias=20 + i, atrasado=True)
          for i in range(130)]
    fonte(ts + tarefas())
    html = _html(logado, "?atr=1")
    assert '<section class="pga" data-arv="todas"' not in html and "pga-nf" not in html   # no lugar das árvores
    lista = _trecho(html, '<section class="pgs"', "</section>")
    assert re.search(r"Atrasadas</h2>\s*<span class=\"pga-badge pga-badge--crit\">132</span>", lista)
    assert lista.count('<tr class="pgs-lin') == G.PAGINA_ATRASADAS == 100
    assert lista.index("Tarefa 129") < lista.index("Tarefa 128")                        # as mais velhas primeiro
    mais = re.search(r'<button type="button" class="pgf-bt pgs-mais" data-url="([^"]*)"[^>]*>([^<]*)<', lista)
    assert mais.group(1) == "?atr=1&amp;ap=100" and "Mostrar mais 32" in mais.group(2)
    # a próxima parte vem pela rota, com a marca de onde parar
    h = logado.get("/t/pcm/gestao?atr=1&ap=100").get_data(as_text=True)
    assert h.count('<tr class="pgs-lin') == 32 and 'data-proximo="132" data-restam="0"' in h
    assert "Tarefa 029" in h or "Tarefa 028" in h
    assert logado.get("/t/pcm/gestao?ap=100").status_code == 404                     # sem o Só atrasadas, nada
    # a OS abre o card do Nexus também aqui e na árvore (o clique ouvia só dentro do painel lateral)
    assert 'class="pgp-os-n" data-wid="7129"' in lista


def test_o_clique_da_os_vale_na_arvore_e_no_so_atrasadas(logado, fonte):
    js = (RAIZ / "nexus" / "static" / "pcm-gestao.js").read_text(encoding="utf-8")
    assert "closest('.pgp-os-n[data-wid]')" in js and "prepararAoParar" in js
    for q in ("", "?modo=fila"):
        html = _html(logado, q)
        assert "pcm-gestao.js" in html and "NexusOsCard" in html                       # nos dois modos
    html = _html(logado)
    assert "closest('#pgp .pgp-os-n[data-wid]')" not in html                          # um só ouvinte: nada abre duas vezes


def test_os_blocos_da_confiabilidade_vem_fechados_e_carregam_ao_abrir(logado, fonte):
    html = _html(logado, "?cliente=Cliente+A")
    conf = re.search(r'<details class="pgc" id="pgc-conf" data-url="([^"]*)"([^>]*)>', html)
    mttr = re.search(r'<details class="pgc" id="pgc-mttr" data-url="([^"]*)"([^>]*)>', html)
    assert conf and mttr and "open" not in conf.group(2) and "open" not in mttr.group(2)
    assert conf.group(1) == "?cliente=Cliente+A&amp;cf=conf" and mttr.group(1) == "?cliente=Cliente+A&amp;cf=mttr"
    assert "Confiabilidade por ativo" in html and "Tempo médio de reparo por Equipe Cluster" in html
    assert html.index("pgc-conf") > html.index('<section class="pga" data-arv="todas"')   # a ordem do painel


def test_a_ordem_dos_blocos_de_cima_para_baixo(logado, fonte):
    html = _html(logado)
    ordem = [html.index(x) for x in ('<div class="pgn"', '<section class="pgf"', "Manutenções: Plano &amp; Fila",
                                     '<section class="pga-nf" data-arv="nf"', '<section class="pga" data-arv="todas"',
                                     'id="pgc-conf"', 'id="pgc-mttr"')]
    assert ordem == sorted(ordem)
    assert not re.search("[\U0001F000-\U0001FAFF☀-➿]", html)                          # sem emoji


# ── a cópia guardada (revisão da parte A) ────────────────────────────────────────────────────────────────────
def test_urls_equivalentes_dividem_a_mesma_copia(logado, fonte, monkeypatch):
    """A chave da cópia é o filtro normalizado: sem maiúscula, as escolhas em ordem e o "considerar" sem datas no
    padrão. Duas URLs que filtram igual não guardam duas cópias (a memória do servidor é curta)."""
    assert G.chave(G.filtros(MultiDict([("cliente", "Cliente B"), ("cliente", "cliente a"), ("pmodo", "fim")]))) == \
        G.chave(G.filtros(MultiDict([("cliente", "CLIENTE A"), ("cliente", "cliente b")])))
    assert G.chave(G.filtros({"pini": "2026-10-01", "pmodo": "fim"})) != G.chave(G.filtros({"pini": "2026-10-01"}))
    contas = []
    original = G.recortar
    monkeypatch.setattr(G, "recortar", lambda *a, **k: contas.append(1) or original(*a, **k))
    for q in ("?cliente=Cliente+A&cliente=Cliente+B", "?cliente=cliente+b&cliente=CLIENTE+A&pmodo=ini"):
        assert logado.get("/t/pcm/gestao" + q).status_code == 200
    assert len(contas) == 1


def test_o_teto_da_copia_nao_joga_fora_a_versao(app, logado, fonte):
    """Passou do teto, a cópia limpa tudo menos a versão do arquivo: sem ela, o pedido seguinte via "outra versão" e
    limpava de novo, perdendo o que o anterior acabou de montar."""
    from nexus.pcm import telas
    assert logado.get("/t/pcm/gestao").status_code == 200
    versao = telas._G_CACHE["versao"]
    for i in range(telas._G_TETO + 2):
        telas._guardado(("teste", i), lambda: i)
    assert telas._G_CACHE.get("versao") == versao
    telas._guardado(("depois",), lambda: 1)
    assert logado.get("/t/pcm/gestao").status_code == 200 and ("depois",) in telas._G_CACHE

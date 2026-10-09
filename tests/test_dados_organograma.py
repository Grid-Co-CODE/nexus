"""Base → Governança de dados, visão Organograma (Levi, 08/10/2026: "Quero uma visão de cima da governança também, teria
como fazer um organograma??"; 09/10/2026, depois de usar: organograma como padrão, sem aposentado, fontes abertas, gaveta
que cresce com o conteúdo, linguagem amigável e a tabela de verdade ao lado, só para ler).

O que estes testes seguram: o organograma é o padrão e a matriz vem pela URL; cada fato do catálogo que não se aposentou
aparece uma vez, sob o setor dele (as fontes de outro fato abertas no rodapé do setor); o aposentado não aparece em
nenhuma visão; as contas da raiz batem com `catalogo.resumo()`; o estado pela palavra, além da cor; o texto amigável de
cada fato; o detalhe com o grão, as medidas e por onde liga cada dimensão que o fato tem, e a qualidade da última carga
quando ela existe; quem grava cada livro; a faixa das dimensões; a prévia da tabela (só tabelas do catálogo, do fim
para o começo, por página, e-mail mascarado, aba de outro assunto recusada); a tela nos dois temas. Banco falso em
memória (nada vai à rede)."""
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from markupsafe import escape
from pg_falso import ApiPGFalsa, Resposta

from nexus.dados import catalogo, explica, previa
from nexus.dados import telas as telas_dados

BASE = "http://pg.falso"
URL = "/t/base/governanca"
MAT = URL + "?ver=matriz"
TAB = URL + "/tabela"
VAZIOS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
MOSTRADOS = [f for f in catalogo.FATOS if f.estado != "aposentado"]


class _Arvore(HTMLParser):
    """Para cada cartão de fato (<button data-fato>), o setor em que ele está (o <li data-setor> de cima) e se está entre
    as tabelas de origem (<div class="dd-org-fontes">). Guarda também as contas da raiz e as linhas das dimensões."""

    def __init__(self):
        super().__init__()
        self.pilha, self.cartoes, self.contas, self.dims = [], [], {}, {}
        self._conta = self._dim = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "button" and "data-fato" in a:
            setor = next((x.get("data-setor") for _, x in reversed(self.pilha) if "data-setor" in x), None)
            fonte = any("dd-org-fontes" in (x.get("class") or "").split() for _, x in self.pilha)
            self.cartoes.append((a["data-fato"], setor, fonte, a.get("class", ""), a.get("type")))
        if tag in VAZIOS:
            return
        self.pilha.append((tag, a))
        if tag == "li" and "data-conta" in a and any("dd-org-contas" in (x.get("class") or "") for _, x in self.pilha):
            self._conta = [a["data-conta"], ""]
        if tag == "li" and "data-dim" in a:
            self._dim = a["data-dim"]
        if tag == "span" and "data-conta" in a and self._dim:
            self._conta = [f"{self._dim}:{a['data-conta']}", ""]

    def handle_endtag(self, tag):
        while self.pilha:
            t, a = self.pilha.pop()
            if self._conta and t in ("li", "span") and a.get("data-conta"):
                chave, texto = self._conta
                (self.dims if ":" in chave else self.contas)[chave] = int(texto.split()[0])
                self._conta = None
            if t == "li" and a.get("data-dim"):
                self._dim = None
            if t == tag:
                break

    def handle_data(self, data):
        if self._conta is not None:
            self._conta[1] += " " + data


def _arvore(texto: str) -> _Arvore:
    p = _Arvore()
    p.feed(texto)
    return p


def _esc(texto) -> str:
    """Como o Jinja escapa (as aspas viram &#34; e &#39;, não o &quot; do html.escape)."""
    return str(escape(texto))


def _template(texto: str, fato_id: str) -> str:
    ini = texto.index(f'<template id="dd-det-{fato_id}">')
    return texto[ini:texto.index("</template>", ini)]


def _cartao(html: str, fid: str) -> str:
    ini = html.index(f'data-fato="{fid}"')
    return html[ini:html.index("</button>", ini)]


@pytest.fixture
def tela(logado):
    telas_dados._CACHE.update(t=0.0, v=None)
    previa.limpar_cache()
    yield logado
    telas_dados._CACHE.update(t=0.0, v=None)
    previa.limpar_cache()


def _aba(api, livro, nome, linhas):
    api.workbooks.setdefault(livro, {})
    cab = list(linhas[0]) if linhas else []
    api._id(livro, nome)["linhas"] = [{"headers": cab, "values": [l.get(c) for c in cab]} for l in linhas]


def _banco_com_qualidade(app):
    """A qualidade de UMA carga, só do fechamento (como a do banco grava: 1 casa decimal, extra em JSON)."""
    api = ApiPGFalsa()
    _aba(api, "nexus_fatos", "qualidade", [{"fato": "fechamento", "livro_origem": "fechamentos_app_campo · Fechamentos",
                                            "linhas": 2955, "pct_data": 100.0, "pct_usina": 99.7, "pct_equipe": 97.7,
                                            "pct_pessoa": 94.4, "com_equipamento": 2946, "pct_equipamento": 99.7,
                                            "pct_usina_versao": 100.0, "pct_pessoa_versao": 100.0,
                                            "gerado_em": "2026-10-08T17:40:00-03:00",
                                            "extra": '{"tarefas_sem_chave": 3}'}])
    _aba(api, "nexus_fatos", "atualizacao", [{"gerado_em": "2026-10-08T17:40:00-03:00", "maquina": "servidor"}])
    app.config["GRIDCO_DB_API"] = BASE
    app.extensions["nexus_dados_sessao"] = api


class ApiComContagem(ApiPGFalsa):
    """O banco falso com o que a API de verdade dá na listagem das abas (a contagem de linhas e a visibilidade) e a
    janela pedida a cada leitura de linhas, para provar que a prévia lê só a página e não a aba inteira."""

    def __init__(self, ocultas=()):
        super().__init__()
        self.ocultas, self.janelas = set(ocultas), []

    def get(self, url, params=None, headers=None, timeout=None):
        if url.endswith("/api/sheets"):
            return Resposta(200, [{"id": v["id"], "workbook_key": wb, "sheet_name": aba, "row_count": len(v["linhas"]),
                                   "visibility": "hidden" if aba in self.ocultas else "visible"}
                                  for (wb, aba), v in self.abas.items()])
        if url.endswith("/api/workbooks"):
            return Resposta(200, [{"key": k, "updated_at": "2026-10-09T08:40:00-03:00"} for k in self.workbooks])
        if "/rows" in url:
            self.janelas.append((int(params["offset"]), int(params["limit"])))
            r = super().get(url, params=params)
            return Resposta(200, {"offset": params["offset"], "limit": params["limit"], "rows": r.json()})
        return super().get(url, params=params, headers=headers, timeout=timeout)


def _banco_da_previa(app, api=None):
    api = api or ApiComContagem()
    app.config["GRIDCO_DB_API"] = BASE
    app.extensions["nexus_dados_sessao"] = api
    return api


# ── a alternância ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_organograma_e_o_padrao_e_a_matriz_vem_pela_url(tela):
    padrao = tela.get(URL).get_data(as_text=True)
    assert "Organograma da governança" in padrao and "dd-org-arvore" in padrao and 'class="dd-matriz"' not in padrao
    assert f'<a href="{URL}" aria-current="page">Organograma</a>' in padrao and f'<a href="{MAT}">Matriz</a>' in padrao
    # Levi, 09/10: "Deixe organograma como padrão, Matriz em segundo"
    assert padrao.index(">Organograma</a>") < padrao.index(">Matriz</a>")

    mat = tela.get(MAT).get_data(as_text=True)
    assert "Matriz de barramento" in mat and 'class="dd-matriz"' in mat and "dd-org-arvore" not in mat
    assert f'<a href="{MAT}" aria-current="page">Matriz</a>' in mat and f'<a href="{URL}">Organograma</a>' in mat
    # o link antigo do organograma segue valendo; visão que não existe cai no padrão (a URL nunca quebra a tela)
    for ver in ("organograma", "matrix", "", "ORGANOGRAMA", "<script>"):
        r = tela.get(URL, query_string={"ver": ver})
        assert r.status_code == 200 and "dd-org-arvore" in r.get_data(as_text=True), ver
    # a troca de tema sem JavaScript volta para a mesma visão
    assert '<input type="hidden" name="voltar" value="/t/base/governanca?ver=matriz">' in mat


def test_a_tela_abre_nas_duas_visoes_e_nos_dois_temas(tela):
    for tema in ("escuro", "claro"):
        tela.set_cookie("nexus_tema", tema)
        for url in (URL, MAT):
            r = tela.get(url)
            assert r.status_code == 200, (tema, url)
            assert f'<html lang="pt-BR" data-nexus data-tema="{tema}">' in r.get_data(as_text=True), (tema, url)


def test_sem_login_nao_abre(cliente):
    for url in (URL, MAT, TAB + "?fato=fechamento"):
        r = cliente.get(url)
        assert r.status_code == 302 and "/entrar" in r.headers["Location"], url


# ── a árvore ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_cada_fato_mostrado_aparece_uma_vez_sob_o_seu_setor(tela):
    html = tela.get(URL).get_data(as_text=True)
    arv = _arvore(html)
    ids = [c[0] for c in arv.cartoes]
    assert sorted(ids) == sorted(f.id for f in MOSTRADOS) and len(ids) == len(set(ids))
    ativos = {f.id for f in catalogo.ativos()}
    for fid, setor, fonte, classe, tipo in arv.cartoes:
        f = catalogo.POR_ID[fid]
        assert setor == f.area, fid
        # a fonte de outro fato fica no rodapé do setor, aberta (Levi, 09/10: "Se sim já deixa expandido e pronto")
        assert fonte == (fid not in ativos), fid
        # o cartão é um botão (clique, Enter e Espaço abrem o detalhe)
        assert tipo == "button" and "dd-org-fato" in classe.split(), fid
    assert "dd-org-mais" not in html and "Mostrar também" not in html
    # os setores na ordem em que aparecem no catálogo (a mesma da matriz), cada um uma vez
    setores = list(dict.fromkeys(f.area for f in MOSTRADOS))
    assert setores == [x.split('"')[0] for x in html.split('data-setor="')[1:]]


def test_aposentado_nao_aparece_em_nenhuma_visao(tela):
    """Levi, 09/10/2026: "Não mostre aposentado, se ele é inútil deixe em sua inutilidade"."""
    aposentados = [f for f in catalogo.FATOS if f.estado == "aposentado"]
    assert aposentados, "o catálogo não tem mais aposentado: este teste perdeu o objeto"
    org, mat = tela.get(URL).get_data(as_text=True), tela.get(MAT).get_data(as_text=True)
    for f in aposentados:
        assert f'data-fato="{f.id}"' not in org and f'dd-det-{f.id}' not in org, f.id
        assert _esc(f.nome) not in org and _esc(f.nome) not in mat, f.id
        assert tela.get(TAB, query_string={"fato": f.id}).status_code == 404, f.id
    assert ">aposentado<" not in org and ">aposentado<" not in mat     # nem na legenda


def test_as_fontes_de_outro_fato_dizem_o_que_alimentam(tela):
    html = tela.get(URL).get_data(as_text=True)
    for f in (x for x in MOSTRADOS if x.estado == "parte"):
        nomes = [catalogo.POR_ID[p].nome for p in f.parte_de]
        cartao = _cartao(html, f.id)
        assert '<span class="dd-org-estado neutro">fonte</span>' in cartao, f.id
        assert all(_esc(n) in cartao for n in nomes) and "alimenta:" in cartao, f.id
        det = _template(html, f.id)
        assert "Tabela de origem: os dados daqui alimentam" in det and all(_esc(n) in det for n in nomes), f.id
    # cada setor com fontes diz quantas, no rodapé
    assert "tabelas de origem</b> que alimentam os fatos acima" in html


def test_o_setor_tem_o_nome_da_torre_e_as_contas_dele(tela):
    html = tela.get(URL).get_data(as_text=True)
    torres = {t.id: t for t in tela.application.extensions["nexus_torres"]}
    for area in dict.fromkeys(f.area for f in MOSTRADOS):
        ini = html.index(f'data-setor="{area}"')
        no = html[ini:html.index("</summary>", ini)]
        ativos = [f for f in catalogo.ativos() if f.area == area]
        conf = sum(f.estado == "conformado" for f in ativos)
        assert f"<b>{_esc(torres[area].nome)}</b>" in no, area
        assert f"<b>{len(ativos)}</b> {'fato' if len(ativos) == 1 else 'fatos'}" in no, area
        assert f"<b>{conf}</b> {'conformado' if conf == 1 else 'conformados'}" in no, area
    # área sem torre (um "cadastro", por exemplo) vira o nome legível, sem quebrar
    assert telas_dados._setor("cadastro_geral", {})["rotulo"] == "Cadastro geral"


def test_as_contas_da_raiz_batem_com_o_resumo_do_catalogo(tela):
    arv = _arvore(tela.get(URL).get_data(as_text=True))
    r = catalogo.resumo()
    origem = sum(f.estado == "origem" for f in catalogo.ativos())
    assert arv.contas == {"fatos": r["fatos"], "conformados": r["conformados"], "montados": r["montados"],
                          "origem": origem, "fora": r["fora"], "dimensoes": r["dimensoes"], "livros": r["livros"]}
    # todo fato ativo está em um dos quatro degraus: estado novo no catálogo aparece aqui antes de sumir da conta
    assert r["conformados"] + r["montados"] + origem + r["fora"] == r["fatos"]


def test_o_estado_vem_pela_palavra_e_pelo_tom_nunca_so_pela_cor(tela):
    html = tela.get(URL).get_data(as_text=True)
    for f in MOSTRADOS:
        palavra, tom, _ = telas_dados.ESTADO_ORG[f.estado]
        cartao = _cartao(html, f.id)
        assert f'<span class="dd-org-estado {tom}">{palavra}</span>' in cartao, f.id
        assert _esc(f.nome) in cartao and _esc(explica.RESUMO[f.id]) in cartao, f.id
    # todo estado do catálogo tem palavra e tom (estado novo sem tom cairia no neutro, calado), e frase na gaveta
    assert set(telas_dados.ESTADO_ORG) == set(catalogo.ESTADOS_FATO) == set(telas_dados.ESTADO_FRASE)


def test_todo_fato_mostrado_tem_o_texto_amigavel():
    """Levi, 09/10/2026: "Deixe a linguagem do card mais amigável e entendível para alguém que quer saber para o que
    essa tabela serve, o que ela faz, de onde vem". Fato novo no catálogo sem texto em `explica.py` cai aqui."""
    ids = {f.id for f in MOSTRADOS}
    # todo fato mostrado tem o texto; texto de fato que ainda não está no catálogo não quebra (sessões em paralelo: o
    # texto pode entrar antes do fato), mas o resumo e o para-que andam juntos
    assert ids <= set(explica.RESUMO) and set(explica.RESUMO) == set(explica.PARA_QUE)
    for fid in ids:
        assert 15 <= len(explica.RESUMO[fid]) <= 70 and not explica.RESUMO[fid].endswith("."), fid
        assert explica.PARA_QUE[fid].endswith(".") and len(explica.PARA_QUE[fid]) >= 80, fid
    assert set(telas_dados.TIPO_FRASE) == set(catalogo.TIPOS_FATO)
    assert set(telas_dados.LIGA_FRASE) == set(catalogo.ESTADOS) - {"nao"}


def test_o_cartao_diz_onde_o_fato_mora_e_quem_grava(tela):
    html = tela.get(URL).get_data(as_text=True)
    # conformado: o livro de origem e o do Nexus, cada um com quem grava. No livro do Nexus o cartão diz "Nexus" e a
    # gaveta guarda o caminho do código (o `quem_grava` do LIVROS), em letra pequena
    c = _cartao(html, "fechamento")
    assert "fechamentos_app_campo" in c and "grava: App de Campo" in c
    assert "→ nexus_fatos" in c and "grava: Nexus<" in c and "nexus/dados/carga.py" not in c
    assert _esc(catalogo.LIVRO_POR_NOME["nexus_fatos"].quem_grava) in _template(html, "fechamento")
    # montado: o destino registrado, ainda sem gravar
    assert "vai para nexus_geracao" in _cartao(html, "geracao_usina_dia")
    # de origem, em livro do Nexus
    assert "grava: Nexus<" in _cartao(html, "decisao_pt")
    det = _template(html, "decisao_pt")
    assert '<span class="dd-gav-quem-nome">Nexus</span>' in det
    assert _esc(catalogo.LIVRO_POR_NOME["nexus_pt_decisoes"].quem_grava) in det
    # fora do banco: o lugar, e quem grava é o robô do PCM
    p = _cartao(html, "programacao")
    assert "fora do banco: banco_dados.json do PCM" in p and "robô do PCM" in p


def test_quem_grava_cada_livro():
    assert telas_dados.quem_grava("nexus_fatos · fato_ronda") == (catalogo.LIVRO_POR_NOME["nexus_fatos"].quem_grava,
                                                                   catalogo.LIVRO_POR_NOME["nexus_fatos"].cadencia)
    assert telas_dados.quem_grava("rondas_app_campo · OS de ronda")[0] == "App de Campo"
    assert telas_dados.quem_grava("falhas_performance · strings_os")[0] == "plataforma de performance"
    assert telas_dados.quem_grava("bd_thopen · 1 aba por usina")[0] == "coletor da API PV"
    assert telas_dados.quem_grava("pcm · banco_dados.json · semanas[].rows")[0] == "robô do PCM"
    # livro do Nexus fora do LIVROS (regra 10) e família desconhecida não inventam dono
    assert telas_dados.quem_grava("nexus_novo · fato_x")[0] == "Nexus"
    assert telas_dados.quem_grava("planilha_nova · aba")[0] == telas_dados.A_DECLARAR
    # todo livro que o catálogo cita hoje tem dono conhecido. Se falhar: registre o livro em catalogo.LIVROS (livro do
    # Nexus) ou ponha a família dele em telas.QUEM_GRAVA_ORIGEM, dizendo quem grava
    sem_dono = [(f.id, x) for f in catalogo.FATOS for x in (f.fontes or (f.livro,))
                if telas_dados.quem_grava(x)[0] == telas_dados.A_DECLARAR]
    assert sem_dono == []


# ── o detalhe ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_detalhe_fala_para_que_serve_e_liga_cada_dimensao_que_o_fato_tem(tela):
    html = tela.get(URL).get_data(as_text=True)
    assert '<dialog class="dd-gaveta" id="dd-gaveta"' in html and 'aria-controls="dd-gaveta"' in html
    for f in MOSTRADOS:
        det = _template(html, f.id)
        for titulo in ("Para que serve", "O que cada linha guarda", "De onde vem e quem grava",
                       "Como se liga às outras tabelas", "O que dá para medir", "Para quem mantém o dado"):
            assert titulo in det, (f.id, titulo)
        assert _esc(explica.PARA_QUE[f.id]) in det, f.id
        frase = telas_dados.ESTADO_FRASE[f.estado]
        assert _esc(frase.split("{")[0]) in det, f.id
        assert _esc(telas_dados.TIPO_FRASE[f.tipo]) in det, f.id
        # o grão inteiro (técnico) fica em "Para quem mantém o dado"; o amigável, sem o "1 linha = "
        assert _esc(f.grao) in det and f"Cada linha é <b>{_esc(re.sub(r'^1 linha = ', '', f.grao))}</b>" in det, f.id
        assert _esc(f.nome) in det and catalogo.TIPO_ROTULO[f.tipo] in det, f.id
        for c in f.chave:
            assert _esc(c) in det, f.id
        for m in f.medidas:
            assert f"<code>{m.coluna}</code>" in det and _esc(m.unidade) in det, (f.id, m.coluna)
        # só as dimensões que o fato tem, com o estado da célula da matriz e a coluna; as outras numa linha
        sem = []
        for did, nome, _onde, _chave in catalogo.DIMENSOES:
            est, col = f.dims[did]
            if est == "nao":
                assert f'<tr data-dim="{did}">' not in det, (f.id, did)
                sem.append(nome)
                continue
            ini = det.index(f'<tr data-dim="{did}">')
            linha = det[ini:det.index("</tr>", ini)]
            assert _esc(nome) in linha and f'class="dd-chip {est}">{catalogo.ESTADOS[est]}<' in linha, (f.id, did)
            assert _esc(col) in linha, (f.id, did)
            assert _esc(telas_dados.LIGA_FRASE[est]) in det, (f.id, est)       # a legenda do jeito que ele usa
        if sem:
            assert f"Não se liga a: {_esc(', '.join(sem))}." in det, f.id
        if f.observacao:
            assert _esc(f.observacao) in det, f.id


def test_o_detalhe_mostra_a_qualidade_da_ultima_carga(tela, app):
    _banco_com_qualidade(app)
    html = tela.get(URL).get_data(as_text=True)
    det = _template(html, "fechamento")
    assert "2955 linhas na carga de 08/10 17:40" in det

    def celula(did):
        ini = det.index(f'<tr data-dim="{did}">')
        return det[ini:det.index("</tr>", ini)]
    assert '<td class="dd-gav-pct">99,7%</td>' in celula("usina")
    assert '<td class="dd-gav-pct">97,7%</td>' in celula("equipe")
    assert '<td class="dd-gav-pct">—</td>' in celula("os")             # dimensão sem medida na qualidade
    for rot in ("Data", "Usina", "Equipe", "Pessoa", "Equipamento"):
        assert f'<span class="rot">{rot}</span>' in det, rot
    assert "tarefas sem chave" in det                              # o extra da qualidade
    # fato sem linha na qualidade diz por quê, sem barra inventada nem coluna de % vazia
    ronda = _template(html, "ronda")
    assert 'class="dd-barra"' not in ronda and "não trouxe esta tabela" in ronda and ">Ligado<" not in ronda
    assert "Como ainda não grava" in _template(html, "geracao_usina_dia")
    assert "ainda não monta esta tabela" in _template(html, "ticket")
    assert "A qualidade da ligação é medida em Ronda" in _template(html, "ronda_avulsa")
    # a raiz diz a hora e a máquina da última carga
    assert "Última carga: <b>08/10 17:40</b> · servidor" in html


def test_a_gaveta_cresce_com_o_conteudo_e_tem_o_botao_da_tabela_ao_lado_do_x(tela):
    """Levi, 09/10/2026: a barra lateral "aumentasse e diminuisse de acordo com a informação" e "um botão ao lado esquerdo
    do 'X' em formato de tabela". A largura é a das tabelas da gaveta (o texto corrido não empurra)."""
    html = tela.get(URL).get_data(as_text=True)
    ini = html.index('<dialog class="dd-gaveta"')
    dlg = html[ini:html.index("</dialog>", ini)]
    assert f'data-url-tabela="{TAB}"' in dlg
    acoes = dlg[dlg.index('class="dd-gav-acoes"'):]
    assert acoes.index('class="dd-gav-tabela"') < acoes.index('class="dd-gav-fechar"')
    assert 'class="ph ph-table"' in acoes and 'aria-controls="dd-prev"' in acoes
    css = (Path(telas_dados.__file__).parents[1] / "static" / "dados.css").read_text(encoding="utf-8")
    corpo = css[css.index(".dd-gav-corpo{"):]
    corpo = corpo[:corpo.index("}")]
    assert "width:max-content" in corpo and "min-width:min(520px,100vw)" in corpo
    assert "max-width:min(940px,100vw)" in corpo
    assert ".dd-gav-conteudo>*{contain:inline-size}" in css and ".dd-gav-conteudo>.dd-gav-largo{contain:none}" in css


# ── a tabela, só para ler ─────────────────────────────────────────────────────────────────────────────────────────
def test_a_previa_so_oferece_as_tabelas_do_catalogo():
    def lista(fid):
        return [(a["papel"], a["livro"], a["aba"], a["por_usina"], bool(a.get("fora")))
                for a in previa.alvos(catalogo.POR_ID[fid])]
    assert lista("fechamento") == [("nexus", "nexus_fatos", "fato_fechamento", False, False),
                                   ("origem", "fechamentos_app_campo", "Fechamentos", False, False)]
    assert lista("ronda") == [("nexus", "nexus_fatos", "fato_ronda", False, False),
                              ("origem", "rondas_app_campo", "OS de ronda", False, False),
                              ("origem", "nexus_rondas_checklist", "fato_checklist_ronda", False, False),
                              ("origem", "nexus_rondas_avulsas", "fato_ronda_avulsa", False, False)]
    # a programação do PCM: a tabela do Nexus e o arquivo do robô, que não está no banco
    assert lista("programacao") == [("nexus", "nexus_programacao", "fato_programacao", False, False),
                                    ("origem", "", "", False, True)]
    # a geração: as abas de usina dos dois livros; a fonte de dois grãos: as duas abas
    assert lista("geracao_usina_dia")[1:] == [("origem", "bd_thopen", "", True, False),
                                              ("origem", "bd_performance", "", True, False)]
    assert lista("falha_string") == [("origem", "falhas_performance", "strings_episodios", False, False),
                                     ("origem", "falhas_performance", "strings_inversor_dia", False, False)]
    for f in MOSTRADOS:
        assert previa.alvos(f), f.id


def test_a_previa_abre_no_fim_da_tabela_e_le_so_a_pagina(tela, app):
    api = _banco_da_previa(app)
    _aba(api, "nexus_fatos", "fato_fechamento", [{"fechamento_id": f"f{i:03d}", "nota_pts": i} for i in range(1, 121)])
    _aba(api, "fechamentos_app_campo", "Fechamentos", [{"OS": "1"}])
    r = tela.get(TAB, query_string={"fato": "fechamento"})
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "data-previa" in html and 'data-t="0"' in html
    assert "<code>nexus_fatos · fato_fechamento</code>" in html and "A tabela do Nexus, com os IDs" in html
    assert "<b>120</b> linhas" in html and "gravada em 09/10/2026 08:40" in html
    # abre no fim da tabela (as 50 últimas, 71 a 120), na ordem dela; só essa janela foi lida no banco. Não diz "as mais
    # novas": nem todo livro só acrescenta (o fato_programacao termina na W38)
    assert "Linhas <b>71</b> a <b>120</b> de <b>120</b> (o fim da tabela)" in html and "mais novas" not in html
    assert html.index(">f071<") < html.index(">f120<") and ">f070<" not in html
    assert api.janelas == [(70, 50)]
    # no fim, Próximas e Fim param; Anteriores volta 50 linhas e Início vai à 1ª
    assert 'data-ini="71" disabled>Próximas' in html and 'data-ini="71" disabled>Fim' in html
    assert 'data-ini="1">Início' in html and 'data-ini="21"><i class="ph ph-caret-left" aria-hidden="true"></i> Anteriores' in html
    html = tela.get(TAB, query_string={"fato": "fechamento", "ini": 21}).get_data(as_text=True)
    assert "Linhas <b>21</b> a <b>70</b> de <b>120</b></span>" in html and ">f021<" in html and ">f020<" not in html
    # o Início mostra a página cheia (1 a 50, e não 1 a 20); linha pedida fora da tabela vai para a ponta
    for ini in (1, 0, -5):
        html = tela.get(TAB, query_string={"fato": "fechamento", "ini": ini}).get_data(as_text=True)
        assert "Linhas <b>1</b> a <b>50</b> de <b>120</b> (o começo da tabela)" in html, ini
        assert 'data-ini="1" disabled>Início' in html and 'data-ini="51">Próximas' in html, ini
    for ini in (71, 99, 10 ** 6, "x"):
        html = tela.get(TAB, query_string={"fato": "fechamento", "ini": ini}).get_data(as_text=True)
        assert "Linhas <b>71</b> a <b>120</b> de <b>120</b> (o fim da tabela)" in html, ini
    # a outra tabela da lista, pelo número dela
    html = tela.get(TAB, query_string={"fato": "fechamento", "t": 1}).get_data(as_text=True)
    assert "<code>fechamentos_app_campo · Fechamentos</code>" in html and "A tabela de origem" in html


def test_a_previa_mascara_email_e_corta_texto_longo(tela, app):
    api = _banco_da_previa(app)
    longo = "observação " * 30
    _aba(api, "decisoes_app_campo", "Decisões", [{"Quando": "2026-10-09", "Por": "fulano.tal@gridco.com.br",
                                                   "Motivo": longo, "Vazio": None, "Inteiro": 3.0,
                                                   "Energia": 41782.399999999994}])
    html = tela.get(TAB, query_string={"fato": "decisao"}).get_data(as_text=True)
    assert "gridco.com.br" not in html and ">[e-mail]<" in html
    corte = " ".join(longo.split())
    assert f'title="{corte}"' in html and f">{corte[:previa.CELULA_MAX - 1]}…<" in html
    assert "<td></td>" in html and "<td>3</td>" in html and "<td>41782.4</td>" in html


def test_a_previa_recusa_o_que_nao_e_do_catalogo(tela, app):
    api = _banco_da_previa(app, ApiComContagem(ocultas={"Altair - Backup"}))
    _aba(api, "bd_thopen", "Clientes", [{"Cliente": "X", "Contato": "a@b.com"}])          # fora da lista de escolha
    _aba(api, "bd_thopen", "Altair - Backup", [{"Data": "2026-10-01", "Inversor 1.1": 5}])   # oculta: fora também
    _aba(api, "bd_thopen", "Altair", [{"Data": "2026-10-01", "Inversor 1.1": 10}])
    _aba(api, "bd_thopen", "Planilha Nova", [{"Nome": "x", "Telefone": "1"}])             # de outro assunto
    assert tela.get(TAB, query_string={"fato": "nao_existe"}).status_code == 404
    html = tela.get(TAB, query_string={"fato": "geracao_thopen"}).get_data(as_text=True)
    # a lista de abas de usina: sem a de cadastro conhecida e sem a oculta; a 1ª é a que abre
    assert "<option selected>Altair</option>" in html and ">Clientes<" not in html and "Backup" not in html
    assert "<code>bd_thopen · Altair</code>" in html and "<td>10</td>" in html
    # aba pedida fora da lista não é lida: abre a 1ª da lista
    html = tela.get(TAB, query_string={"fato": "geracao_thopen", "aba": "Clientes"}).get_data(as_text=True)
    assert "Contato" not in html and "<code>bd_thopen · Altair</code>" in html
    # aba nova que não é de geração aparece na lista, mas não mostra linha nenhuma
    html = tela.get(TAB, query_string={"fato": "geracao_thopen", "aba": "Planilha Nova"}).get_data(as_text=True)
    assert "não é de geração por usina" in html and "Telefone" not in html and "<td>" not in html
    # número de tabela fora da lista cai na 1ª que existe no banco
    html = tela.get(TAB, query_string={"fato": "geracao_thopen", "t": 7}).get_data(as_text=True)
    assert 'data-t="0"' in html


def test_a_previa_diz_quando_a_tabela_nao_esta_no_banco(tela, app):
    api = _banco_da_previa(app)
    _aba(api, "rondas_app_campo", "OS de ronda", [{"OS": "15001", "Início": "2026-10-08T10:00:00"}])
    _aba(api, "nexus_programacao", "fato_programacao", [{"programacao_id": "a1"}])
    _aba(api, "zeladoria_app_campo", "Zeladoria", [])
    # o fato_ronda ainda não está no banco: sem escolha, abre a 1ª que está (a do App); escolhido, diz que não está
    html = tela.get(TAB, query_string={"fato": "ronda"}).get_data(as_text=True)
    assert 'data-t="1"' in html and ">15001<" in html and "(ainda não está no banco)" in html
    html = tela.get(TAB, query_string={"fato": "ronda", "t": 0}).get_data(as_text=True)
    assert "ainda não está no banco" in html and "passa a existir quando o Nexus gravar" in html
    # o arquivo do robô do PCM: fora do banco, sem tabela
    html = tela.get(TAB, query_string={"fato": "programacao", "t": 1}).get_data(as_text=True)
    assert "Fora do banco: banco_dados.json do PCM" in html and "não está no banco de dados" in html
    # tabela que existe e está vazia
    assert "está vazia" in tela.get(TAB, query_string={"fato": "zeladoria"}).get_data(as_text=True)


def test_a_previa_sem_banco_avisa_e_nao_quebra(tela, app):
    # teste sem banco configurado: nunca vai à rede
    html = tela.get(TAB, query_string={"fato": "fechamento"}).get_data(as_text=True)
    assert "data-previa" in html and "Não consegui ler a tabela no banco (teste sem banco)" in html

    class Fora:
        def get(self, *a, **k):
            raise ConnectionError("banco fora do ar")
    _banco_da_previa(app, Fora())
    html = tela.get(TAB, query_string={"fato": "fechamento"}).get_data(as_text=True)
    assert "Não consegui ler a tabela no banco (ConnectionError)" in html


def test_a_previa_funciona_sem_a_contagem_na_listagem(tela, app):
    """O banco falso de sempre (sem `row_count`): a prévia lê a aba e conta, e mostra igual."""
    api = ApiPGFalsa()
    _aba(api, "pt_app_campo", "PT", [{"PT": str(i)} for i in range(1, 8)])
    _banco_da_previa(app, api)
    html = tela.get(TAB, query_string={"fato": "pt", "t": 1}).get_data(as_text=True)
    assert "<b>7</b> linhas" in html and "Linhas <b>1</b> a <b>7</b> de <b>7</b> (a tabela inteira)" in html
    assert html.index("<td>1</td>") < html.index("<td>7</td>")


# ── as dimensões ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_faixa_das_dimensoes_conta_por_id_e_por_outro_caminho(tela):
    arv = _arvore(tela.get(URL).get_data(as_text=True))
    for did, _nome, _onde, _chave in catalogo.DIMENSOES:
        estados = [f.dims[did][0] for f in catalogo.ativos()]
        assert arv.dims[f"{did}:id"] == estados.count("id"), did
        assert arv.dims[f"{did}:outro"] == sum(e not in ("id", "nao") for e in estados), did
    html = tela.get(URL).get_data(as_text=True)
    for did, _nome, onde, chave in catalogo.DIMENSOES:
        ini = html.index(f'data-dim="{did}"')
        bloco = html[ini:html.index("</li>", ini)]
        assert _esc(onde) in bloco and _esc(chave) in bloco, did


# ── o radar do banco (Levi, 09/10/2026: "verifique se aparece a cada tabela nova que aparece!") ─────────────────────
def _banco_do_radar(app):
    api = _banco_da_previa(app)
    _aba(api, "fechamentos_app_campo", "Fechamentos", [{"OS": "1"}])                   # fonte de fato
    _aba(api, "bd_thopen", "Altair", [{"Data": "2026-10-01", "Inversor 1.1": 10}])       # aba de usina
    _aba(api, "bd_thopen", "Clientes", [{"Cliente": "X"}])                              # conhecida (apoio)
    _aba(api, "cadastro_nexus", "usinas", [{"usina_id": 1}])                            # conhecida (dimensão)
    _aba(api, "zz_teste_claude_apagar", "T", [{"a": 1}])                                # teste: só na conta
    _aba(api, "planilha_nova", "eventos", [{"quando": "2026-10-09", "quem": "fulano.tal@exemplo.com"},
                                           {"quando": "2026-10-10", "quem": "outra"}])  # nova
    _aba(api, "nexus_fatos", "fato_novo", [{"x": 1}])               # livro do Nexus fora do LIVROS (regra 10): nova
    api.ocultas.add("Altair - Backup")
    _aba(api, "bd_thopen", "Altair - Backup", [{"Data": "2026-10-01"}])                  # oculta e sem declarar: nova
    return api


def _bloco(html: str, inicio: str, fim: str) -> str:
    ini = html.index(inicio)
    return html[ini:html.index(fim, ini)]


NOVAS = ("planilha_nova · eventos", "nexus_fatos · fato_novo", "bd_thopen · Altair - Backup")


def test_tabela_nova_no_banco_aparece_sozinha_nas_duas_visoes(tela, app):
    _banco_do_radar(app)
    org = tela.get(URL).get_data(as_text=True)
    contas = _bloco(org, '<ul class="dd-radar-contas">', "</ul>")
    for caixa, n in (("total", 8), ("fato", 1), ("usina", 1), ("conhecida", 3)):
        assert f'<li data-radar="{caixa}"><b>{n}</b>' in contas, caixa
    assert '<li data-radar="nova" class="critico"><b>3</b><span>novas, fora do catálogo</span>' in contas
    novas = _bloco(org, '<ul class="dd-radar-novas">', "</ul>")
    for t in NOVAS:
        assert f"<code>{_esc(t)}</code>" in novas, t
    for t in ("Fechamentos", "Altair</code>", "Clientes", "usinas", "zz_teste"):
        assert t not in novas, t
    # cada nova abre o detalhe na gaveta, que diz o que fazer; a raiz do organograma conta e leva ao radar
    for i, _t in enumerate(NOVAS, 1):
        assert f'data-det="dd-det-nova-{i}"' in novas and f'<template id="dd-det-nova-{i}">' in org
    det = _bloco(org, '<template id="dd-det-nova-1">', "</template>")
    assert "o catálogo do Nexus não diz o que ela é" in det and "CONHECIDAS" in det and "LIVROS" in det
    assert 'href="#dd-radar">Radar do banco: <b>3</b> tabelas novas, fora do catálogo' in org
    # as conhecidas dizem o porquê; a de teste só entra na conta
    conhecidas = _bloco(org, '<details class="dd-radar-conhecidas">', "</details>")
    assert _esc(catalogo.conhecida("bd_thopen", "Clientes").motivo) in conhecidas
    assert "zz_teste" not in conhecidas and "(1 de teste ou aposentadas só entram na conta)" in conhecidas
    # a matriz mostra o mesmo radar, sem a gaveta
    mat = tela.get(MAT).get_data(as_text=True)
    novas = _bloco(mat, '<ul class="dd-radar-novas">', "</ul>")
    assert all(f"<code>{_esc(t)}</code>" in novas for t in NOVAS) and "data-det" not in novas


def test_sem_tabela_nova_o_radar_diz_que_todas_tem_dono(tela, app):
    api = _banco_da_previa(app)
    _aba(api, "fechamentos_app_campo", "Fechamentos", [{"OS": "1"}])
    _aba(api, "cadastro_nexus", "usinas", [{"usina_id": 1}])
    org = tela.get(URL).get_data(as_text=True)
    assert '<li data-radar="nova" class="ok"><b>0</b>' in org and 'class="dd-radar-novas"' not in org
    assert "Nenhuma tabela nova: as 2 tabelas do banco têm dono no catálogo." in org
    assert "Radar do banco: nenhuma tabela nova; as 2 têm dono" in org
    # sem banco, o radar diz que não leu, sem inventar zero
    telas_dados._CACHE.update(t=0.0, v=None)
    app.extensions.pop("nexus_dados_sessao")
    org = tela.get(URL).get_data(as_text=True)
    assert "Não consegui ler a lista de tabelas do banco (teste sem banco)" in org and 'data-radar="nova"' not in org


def test_a_tabela_nova_so_abre_para_administrador_e_so_enquanto_for_nova(tela, app):
    _banco_do_radar(app)
    q = {"nova": 1, "livro": "planilha_nova", "aba_nova": "eventos"}
    html = tela.get(TAB, query_string=q).get_data(as_text=True)
    assert "Tabela nova no banco, que o catálogo ainda não conhece" in html
    assert "<code>planilha_nova · eventos</code>" in html
    assert "<td>2026-10-10</td>" in html and ">[e-mail]<" in html and "exemplo.com" not in html
    # o que não é nova não abre por aqui: de fato, conhecida, de usina ou inexistente
    for livro, aba in (("fechamentos_app_campo", "Fechamentos"), ("bd_thopen", "Clientes"), ("bd_thopen", "Altair"),
                       ("cadastro_nexus", "usinas"), ("planilha_nova", "outra")):
        assert tela.get(TAB, query_string={"nova": 1, "livro": livro, "aba_nova": aba}).status_code == 404, aba
    # quem não é administrador vê o detalhe, sem as linhas (nem o botão da tabela na gaveta)
    c = app.test_client()
    with c.session_transaction() as s:
        s["logado"], s["admin"] = True, False
        s["usuario"] = {"email": "pessoa.teste@exemplo.com", "nome": "Pessoa Teste", "perfil": "Técnico"}
    html = c.get(TAB, query_string=q).get_data(as_text=True)
    assert "só administrador vê as linhas" in html and "2026-10-10" not in html
    org = c.get(URL).get_data(as_text=True)
    assert re.search(r'data-det="dd-det-nova-1"\s+data-previa=""', org) and "só aparecem para administrador" in org


def test_toda_conhecida_diz_o_porque_e_nao_se_mistura_com_fato():
    vistos = set()
    pares, _ = previa.cobertas()
    for c in catalogo.CONHECIDAS:
        assert c.papel in catalogo.PAPEIS_CONHECIDA and len(c.motivo) >= 20 and c.abas, c.livro
        assert c.abas != ("*",) or c.papel == "teste", c.livro       # o livro inteiro, só o de teste
        for aba in c.abas:
            assert (c.livro, aba) not in vistos, (c.livro, aba)      # declarada uma vez só
            assert (c.livro, aba) not in pares, (c.livro, aba)       # nem conhecida e fato ao mesmo tempo
            vistos.add((c.livro, aba))


def test_fato_novo_no_catalogo_aparece_sozinho_e_cobra_o_texto(tela, app, monkeypatch):
    """O outro lado do pedido: o fato que entrar no catálogo aparece no organograma com o cartão, a gaveta e a tabela,
    sem tocar na tela, e o teste do texto amigável cobra o "para que serve" dele."""
    novo = catalogo.Fato("teste_novo", "Tabela de teste", "chamados", "planilha_nova · eventos", "1 linha = 1 evento",
                         catalogo._d(data=("cod", "quando")), tipo="transacao", chave=("quando",))
    monkeypatch.setattr(catalogo, "FATOS", catalogo.FATOS + (novo,))
    monkeypatch.setattr(catalogo, "POR_ID", dict(catalogo.POR_ID, teste_novo=novo))
    monkeypatch.setattr(previa, "_COBERTAS", {})
    _banco_do_radar(app)
    org = tela.get(URL).get_data(as_text=True)
    assert ("teste_novo", "chamados") in {(c[0], c[1]) for c in _arvore(org).cartoes}
    assert '<template id="dd-det-teste_novo">' in org
    # a tabela dele deixou de ser nova no radar e abre pela prévia do fato
    novas = _bloco(org, '<ul class="dd-radar-novas">', "</ul>")
    assert "planilha_nova" not in novas and '<li data-radar="nova" class="critico"><b>2</b>' in org
    html = tela.get(TAB, query_string={"fato": "teste_novo"}).get_data(as_text=True)
    assert "<code>planilha_nova · eventos</code>" in html
    faltam = [f.id for f in catalogo.FATOS if f.estado != "aposentado" and f.id not in explica.PARA_QUE]
    assert faltam == ["teste_novo"]

"""Base → Governança de dados, visão Organograma (Levi, 08/10/2026: "Quero uma visão de cima da governança também, teria
como fazer um organograma??").

O que estes testes seguram: a alternância Matriz | Organograma pela URL (a matriz continua o padrão); cada fato do
catálogo aparece uma vez, sob o setor dele (os aposentados e os que viraram fonte de outro fato, no "mostrar também");
as contas da raiz batem com `catalogo.resumo()`; o estado pela palavra, além da cor; o detalhe de cada fato com o grão,
o tipo, as medidas e por onde liga cada dimensão, e a qualidade da última carga quando ela existe; quem grava cada
livro; a faixa das dimensões; a tela nos dois temas. Banco falso em memória (nada vai à rede)."""
from html.parser import HTMLParser

import pytest
from markupsafe import escape
from pg_falso import ApiPGFalsa

from nexus.dados import catalogo
from nexus.dados import telas as telas_dados

BASE = "http://pg.falso"
URL = "/t/base/governanca"
ORG = URL + "?ver=organograma"
VAZIOS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class _Arvore(HTMLParser):
    """Para cada cartão de fato (<button data-fato>), o setor em que ele está (o <li data-setor> de cima) e se está no
    "mostrar também" (<details class="dd-org-mais">). Guarda também as contas da raiz e as linhas das dimensões."""

    def __init__(self):
        super().__init__()
        self.pilha, self.cartoes, self.contas, self.dims = [], [], {}, {}
        self._conta = self._dim = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "button" and "data-fato" in a:
            setor = next((x.get("data-setor") for _, x in reversed(self.pilha) if "data-setor" in x), None)
            mais = any("dd-org-mais" in (x.get("class") or "").split() for _, x in self.pilha)
            self.cartoes.append((a["data-fato"], setor, mais, a.get("class", ""), a.get("type")))
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


@pytest.fixture
def tela(logado):
    telas_dados._CACHE.update(t=0.0, v=None)
    yield logado
    telas_dados._CACHE.update(t=0.0, v=None)


def _banco_com_qualidade(app):
    """A qualidade de UMA carga, só do fechamento (como a do banco grava: 1 casa decimal, extra em JSON)."""
    api = ApiPGFalsa()

    def aba(livro, nome, linhas):
        api.workbooks.setdefault(livro, {})
        cab = list(linhas[0])
        api._id(livro, nome)["linhas"] = [{"headers": cab, "values": [l.get(c) for c in cab]} for l in linhas]
    aba("nexus_fatos", "qualidade", [{"fato": "fechamento", "livro_origem": "fechamentos_app_campo · Fechamentos",
                                      "linhas": 2955, "pct_data": 100.0, "pct_usina": 99.7, "pct_equipe": 97.7,
                                      "pct_pessoa": 94.4, "com_equipamento": 2946, "pct_equipamento": 99.7,
                                      "pct_usina_versao": 100.0, "pct_pessoa_versao": 100.0,
                                      "gerado_em": "2026-10-08T17:40:00-03:00", "extra": '{"tarefas_sem_chave": 3}'}])
    aba("nexus_fatos", "atualizacao", [{"gerado_em": "2026-10-08T17:40:00-03:00", "maquina": "servidor"}])
    app.config["GRIDCO_DB_API"] = BASE
    app.extensions["nexus_dados_sessao"] = api


# ── a alternância ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_matriz_continua_o_padrao_e_o_organograma_vem_pela_url(tela):
    padrao = tela.get(URL).get_data(as_text=True)
    assert "Matriz de barramento" in padrao and 'class="dd-matriz"' in padrao and "dd-org-arvore" not in padrao
    assert f'<a href="{URL}" aria-current="page">Matriz</a>' in padrao
    assert f'<a href="{ORG}">Organograma</a>' in padrao

    org = tela.get(ORG).get_data(as_text=True)
    assert "Organograma da governança" in org and "dd-org-arvore" in org and 'class="dd-matriz"' not in org
    assert f'<a href="{ORG}" aria-current="page">Organograma</a>' in org and f'<a href="{URL}">Matriz</a>' in org
    # visão que não existe cai na matriz (a URL nunca quebra a tela)
    for ver in ("matrix", "", "ORGANOGRAMA", "<script>"):
        r = tela.get(URL, query_string={"ver": ver})
        assert r.status_code == 200 and 'class="dd-matriz"' in r.get_data(as_text=True), ver
    # a troca de tema sem JavaScript volta para a mesma visão
    assert '<input type="hidden" name="voltar" value="/t/base/governanca?ver=organograma">' in org


def test_a_tela_abre_nas_duas_visoes_e_nos_dois_temas(tela):
    for tema in ("escuro", "claro"):
        tela.set_cookie("nexus_tema", tema)
        for url in (URL, ORG):
            r = tela.get(url)
            assert r.status_code == 200, (tema, url)
            assert f'<html lang="pt-BR" data-nexus data-tema="{tema}">' in r.get_data(as_text=True), (tema, url)


def test_sem_login_nao_abre(cliente):
    r = cliente.get(ORG)
    assert r.status_code == 302 and "/entrar" in r.headers["Location"]


# ── a árvore ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_cada_fato_do_catalogo_aparece_uma_vez_sob_o_seu_setor(tela):
    arv = _arvore(tela.get(ORG).get_data(as_text=True))
    ids = [c[0] for c in arv.cartoes]
    assert sorted(ids) == sorted(f.id for f in catalogo.FATOS) and len(ids) == len(set(ids))
    ativos = {f.id for f in catalogo.ativos()}
    for fid, setor, mais, classe, tipo in arv.cartoes:
        f = catalogo.POR_ID[fid]
        assert setor == f.area, fid
        # os que não contam mais (fonte de outro fato, aposentado) ficam recolhidos no "mostrar também" do setor
        assert mais == (fid not in ativos), fid
        # o cartão é um botão (clique, Enter e Espaço abrem o detalhe)
        assert tipo == "button" and "dd-org-fato" in classe.split(), fid
    # os setores na ordem em que aparecem no catálogo (a mesma da matriz), cada um uma vez
    setores = list(dict.fromkeys(f.area for f in catalogo.FATOS))
    html = tela.get(ORG).get_data(as_text=True)
    assert [s for s in setores] == [x.split('"')[0] for x in html.split('data-setor="')[1:]]


def test_o_setor_tem_o_nome_da_torre_e_as_contas_dele(tela):
    html = tela.get(ORG).get_data(as_text=True)
    torres = {t.id: t for t in tela.application.extensions["nexus_torres"]}
    for area in dict.fromkeys(f.area for f in catalogo.FATOS):
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
    arv = _arvore(tela.get(ORG).get_data(as_text=True))
    r = catalogo.resumo()
    origem = sum(f.estado == "origem" for f in catalogo.ativos())
    assert arv.contas == {"fatos": r["fatos"], "conformados": r["conformados"], "montados": r["montados"],
                          "origem": origem, "fora": r["fora"], "dimensoes": r["dimensoes"], "livros": r["livros"]}
    # todo fato ativo está em um dos quatro degraus: estado novo no catálogo aparece aqui antes de sumir da conta
    assert r["conformados"] + r["montados"] + origem + r["fora"] == r["fatos"]


def test_o_estado_vem_pela_palavra_e_pelo_tom_nunca_so_pela_cor(tela):
    html = tela.get(ORG).get_data(as_text=True)
    for f in catalogo.FATOS:
        palavra, tom, _ = telas_dados.ESTADO_ORG[f.estado]
        ini = html.index(f'data-fato="{f.id}"')
        cartao = html[ini:html.index("</button>", ini)]
        assert f'<span class="dd-org-estado {tom}">{palavra}</span>' in cartao, f.id
        assert _esc(f.nome) in cartao and catalogo.TIPO_ROTULO[f.tipo] in cartao, f.id
    # todo estado do catálogo tem palavra e tom (estado novo sem tom cairia no neutro, calado)
    assert set(telas_dados.ESTADO_ORG) == set(catalogo.ESTADOS_FATO)


def test_o_cartao_diz_onde_o_fato_mora_e_quem_grava(tela):
    html = tela.get(ORG).get_data(as_text=True)

    def cartao(fid):
        ini = html.index(f'data-fato="{fid}"')
        return html[ini:html.index("</button>", ini)]
    # conformado: o livro de origem e o do Nexus, cada um com quem grava (o do Nexus vem do LIVROS)
    c = cartao("fechamento")
    assert "fechamentos_app_campo" in c and "grava: App de Campo" in c
    assert "→ nexus_fatos" in c and f"grava: {catalogo.LIVRO_POR_NOME['nexus_fatos'].quem_grava}" in c
    # montado: o destino registrado, ainda sem gravar
    assert "vai para nexus_geracao" in cartao("geracao_usina_dia")
    # de origem, em livro do Nexus: quem grava sai do LIVROS
    assert f"grava: {catalogo.LIVRO_POR_NOME['nexus_pt_decisoes'].quem_grava}" in cartao("decisao_pt")
    # fora do banco: o lugar, e quem grava é o robô do PCM
    assert "fora do banco: banco_dados.json do PCM" in cartao("programacao") and "robô do PCM" in cartao("programacao")


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
def test_o_detalhe_tem_grao_tipo_chave_medidas_e_cada_dimensao(tela):
    html = tela.get(ORG).get_data(as_text=True)
    assert '<dialog class="dd-gaveta" id="dd-gaveta"' in html and 'aria-controls="dd-gaveta"' in html
    for f in catalogo.FATOS:
        det = _template(html, f.id)
        assert _esc(f.grao) in det, f.id
        assert _esc(f.nome) in det and catalogo.TIPO_ROTULO[f.tipo] in det, f.id
        for c in f.chave:
            assert _esc(c) in det, f.id
        for m in f.medidas:
            assert f"<code>{m.coluna}</code>" in det and _esc(m.unidade) in det, (f.id, m.coluna)
        # as 7 dimensões, cada uma com o estado da célula da matriz e a coluna/observação dela
        for did, nome, _onde, _chave in catalogo.DIMENSOES:
            est, col = f.dims[did]
            ini = det.index(f'<tr data-dim="{did}">')
            linha = det[ini:det.index("</tr>", ini)]
            assert _esc(nome) in linha and f'class="dd-chip {est}">{catalogo.ESTADOS[est]}<' in linha, \
                (f.id, did)
            assert _esc(col) in linha, (f.id, did)
        if f.observacao:
            assert _esc(f.observacao) in det, f.id


def test_o_detalhe_mostra_a_qualidade_da_ultima_carga(tela, app):
    _banco_com_qualidade(app)
    html = tela.get(ORG).get_data(as_text=True)
    det = _template(html, "fechamento")
    assert "2955 linhas na carga de 08/10 17:40" in det
    assert "99,7% ligado" in det and "97,7% ligado" in det          # a célula da matriz, com o % da carga
    for rot in ("Data", "Usina", "Equipe", "Pessoa", "Equipamento"):
        assert f'<span class="rot">{rot}</span>' in det, rot
    assert "tarefas sem chave" in det                              # o extra da qualidade
    # fato sem linha na qualidade diz por quê, sem barra inventada
    assert 'class="dd-barra"' not in _template(html, "ronda") and "não trouxe a linha deste fato" in _template(html, "ronda")
    assert "Montado, sem gravar" in _template(html, "geracao_usina_dia")
    assert "ainda não monta este fato" in _template(html, "ticket")
    # a raiz diz a hora e a máquina da última carga
    assert "Última carga: <b>08/10 17:40</b> · servidor" in html


# ── as dimensões ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_faixa_das_dimensoes_conta_por_id_e_por_outro_caminho(tela):
    arv = _arvore(tela.get(ORG).get_data(as_text=True))
    for did, _nome, _onde, _chave in catalogo.DIMENSOES:
        estados = [f.dims[did][0] for f in catalogo.ativos()]
        assert arv.dims[f"{did}:id"] == estados.count("id"), did
        assert arv.dims[f"{did}:outro"] == sum(e not in ("id", "nao") for e in estados), did
    html = tela.get(ORG).get_data(as_text=True)
    for did, _nome, onde, chave in catalogo.DIMENSOES:
        ini = html.index(f'data-dim="{did}"')
        bloco = html[ini:html.index("</li>", ini)]
        assert _esc(onde) in bloco and _esc(chave) in bloco, did

"""O desenho da Aprovação de OS (Levi, 15/11/2026, "desenho: Ok" às duas réguas recomendadas na revisão da Usinas 360°):

1. 30 OS por coluna de cada vez, com "Ver mais". Até ali a página mandava a fila inteira: em 15/11 eram 2.175 cartões,
   3,48 MB, de 3 a 6 s para montar. Valem as três colunas e os blocos Ainda conferindo e Fora do pré-filtro.
2. A idade sem cor ("há 86 d" era vermelho em toda OS: a fila vai de 70 a 177 dias, qualquer limite pinta quase tudo),
   com a mais antiga primeiro.
E, da mesma proposta: o Aprovar verde cheio só na Pronta (nas outras colunas, de contorno).

Como nem todo cartão está na página, a busca e o cliente passam a ir ao servidor: a busca continua respondendo enquanto
se digita (a rota `aprovacao/cartoes` devolve as seções de novo), o cliente vai no painel Filtros com os outros.

A fila dos testes: a de test_campo_aprovacao_responsavel.py (16001 Pronta; 15002 e 15088 Em dúvida; 15102 Não OK;
17001 fora do pré-filtro) e, em `muitas`, mais 35 OS da Usina A fechadas fora do App (Em dúvida): 30001 a 30035."""
import re

import pytest
from test_campo_aprovacao_responsavel import _cartao, _coluna, _folios, fila_resp, quadro  # noqa: F401  (fixtures)
from test_campo_aprovacao_supervisor import _tarefa, fila  # noqa: F401  (fixtures)

from nexus.campo import prefiltro_fundo


@pytest.fixture
def muitas(quadro):  # noqa: F811
    for i in range(1, 36):
        w = _tarefa(30000 + i, 10 + i, "SP 01")
        quadro.linhas.append(w)
        prefiltro_fundo._META[str(w["id_work_order"])] = {"v": prefiltro_fundo.META_V, "chave": "x", "lido_em": 1.0,
                                                           "fotos": [], "vazias": [], "faltando": []}
    return quadro


def _n(html, coluna):
    m = re.search(r'data-apq-n>(\d+)<', _coluna(html, coluna))
    return int(m.group(1)) if m else None


def test_trinta_por_coluna_com_o_ver_mais(muitas, logado):
    html = logado.get("/t/campo/aprovacao?responsavel=*").get_data(as_text=True)
    duvida = _coluna(html, "duvida")
    assert len(_folios(duvida)) == 30 and _n(html, "duvida") == 37          # o número da coluna é o total, não os 30
    # a mais antiga primeiro: as 30 que esperam há mais tempo
    assert _folios(duvida)[:3] == ["15002", "30035", "30034"]
    assert re.search(r'<button[^>]*data-apq-mais[^>]*data-secao="duvida"[^>]*data-de="30"[^>]*>Ver mais 7</button>', duvida)
    # a coluna com menos de 30 tem o Ver mais escondido (a busca o mostra quando o recorte passa de 30)
    assert re.search(r'<button[^>]*data-apq-mais[^>]*data-secao="pronta"[^>]*hidden', _coluna(html, "pronta"))


def test_a_rota_traz_os_proximos(muitas, logado):
    r = logado.get("/t/campo/aprovacao/cartoes?responsavel=*&secao=duvida&de=30")
    j = r.get_json()
    assert r.status_code == 200 and j["secao"] == "duvida" and j["total"] == 37 and j["resta"] == 0
    # 15002 (120 d) e 30035 a 30007 (45 a 17 d) foram na página; vêm 30006 a 30001 (16 a 11 d) e a 15088 (8 d)
    assert _folios(j["html"]) == ["30006", "30005", "30004", "30003", "30002", "30001", "15088"]
    # o cartão que chega pela rota é o mesmo da página: marca para o lote e abre a barra lateral
    assert "data-apq-marcar" in j["html"] and "data-apq-detalhe" in j["html"]


def test_a_busca_vai_ao_servidor_e_responde_enquanto_digita(muitas, logado):
    j = logado.get("/t/campo/aprovacao/cartoes?responsavel=*&q=15088").get_json()
    assert {k: v["total"] for k, v in j["secoes"].items()} == {"pronta": 0, "duvida": 1, "nao_ok": 0, "conferindo": 0,
                                                               "fora": 0}
    assert _folios(j["secoes"]["duvida"]["html"]) == ["15088"] and j["n_os"] == 1
    # a busca sem acento, pela usina e pelo técnico, como antes
    j = logado.get("/t/campo/aprovacao/cartoes?responsavel=*&q=tecnico+7").get_json()
    assert _folios(j["secoes"]["duvida"]["html"]) == ["15002"]
    # a página aberta com a busca no endereço (a busca fica no endereço para a recarga e para o Aplicar dos Filtros)
    html = logado.get("/t/campo/aprovacao?responsavel=*&q=15088").get_data(as_text=True)
    assert _folios(html) == ["15088"]
    assert re.search(r'<input[^>]*name="q"[^>]*value="15088"', html) and re.search(r'<input[^>]*data-apq-busca', html)


def test_o_cliente_vai_no_painel_filtros(quadro, logado):
    html = logado.get("/t/campo/aprovacao?responsavel=*&cliente=Thopen").get_data(as_text=True)
    assert re.search(r'<select[^>]*name="cliente"[^>]*>.*?<option value="Thopen" selected>Thopen</option>', html, re.S)
    assert sorted(_folios(html)) == ["15002", "15088", "15102", "16001", "17001"]
    assert _folios(logado.get("/t/campo/aprovacao?responsavel=*&cliente=Outro").get_data(as_text=True)) == []


def test_o_csv_leva_a_busca(quadro, logado):
    csv = logado.get("/t/campo/aprovacao?responsavel=*&q=15102&csv=1").get_data(as_text=True)
    assert [x.split(";")[0] for x in csv.splitlines()[1:] if x.strip()] == ["15102"]


def test_a_idade_sem_cor(quadro, logado):
    html = logado.get("/t/campo/aprovacao?responsavel=*").get_data(as_text=True)
    for folio in ("15002", "15088", "15102", "16001"):
        dias = re.search(r'<span class="(apq-c-dias[^"]*)"', _cartao(html, folio)).group(1)
        assert dias == "apq-c-dias", (folio, dias)
    detalhe = logado.get("/t/campo/aprovacao/15002/detalhe").get_data(as_text=True)
    eyebrow = re.search(r'<p class="gc-eyebrow">.*?</p>', detalhe, re.S).group(0)
    assert "cn-t-" not in eyebrow and "há 120 dias" in eyebrow


def test_o_aprovar_cheio_so_na_pronta(quadro, logado):
    html = logado.get("/t/campo/aprovacao?responsavel=*").get_data(as_text=True)

    def botao(folio):
        return re.search(r'<button[^>]*data-apq-aprovar[^>]*>', _cartao(html, folio)).group(0)
    assert "gc-btn--primario" in botao("16001")
    for folio in ("15088", "15102", "17001"):
        assert "gc-btn--primario" not in botao(folio) and "gc-btn--contorno" in botao(folio), folio
    pronta = logado.get("/t/campo/aprovacao/16001/detalhe").get_data(as_text=True)
    duvida = logado.get("/t/campo/aprovacao/15088/detalhe").get_data(as_text=True)
    assert re.search(r'<button[^>]*gc-btn--primario[^>]*data-apq-aprovar-de', pronta)
    assert re.search(r'<button[^>]*gc-btn--contorno[^>]*data-apq-aprovar-de', duvida)


def test_selecionar_diz_que_sao_as_mostradas(muitas, logado):
    html = logado.get("/t/campo/aprovacao?responsavel=*").get_data(as_text=True)
    assert "Selecionar as mostradas" in _coluna(html, "duvida") and "Selecionar todas" not in html

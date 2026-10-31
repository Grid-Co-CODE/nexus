"""A gravação de hora em hora do uso do OS Creator e dos pedidos ao Fracttal no banco (31/10/2026, etapa 0 do canto
central do OS Creator, tarefa 0.3). Até aqui os dois contadores só viviam na memória do processo: um deploy ou um reinício
apagava a história, e o "antes e depois" de cada etapa seguinte seria chute. Agora o servidor leva as horas fechadas ao
banco, num livro por mês (`nexus_oscreator_uso_AAAA_MM`).

Provas, sem rede (a API do banco é a `ApiPGFalsa`, inclusive com `como_texto=True`, que devolve tudo como texto, e com a que
devolve a célula vazia como o texto "None", como o `sync-xlsx` real; o Flask é de mentira, o Fracttal é um adaptador falso do
`requests` e o relógio está na mão): o grão e a chave; a mesma hora regravada que não duplica; a virada do mês e do ano que
vai a dois livros; nada de pessoa, setor nem e-mail no banco; o catálogo e a trava `so_cresce`; a falha que guarda as linhas
para a hora seguinte (no máximo 48 h); a leitura curta do livro que não grava por cima; e a ponta a ponta com os contadores
de verdade."""
import logging
import re
import threading
from datetime import datetime

import pytest
import requests
from flask import Flask
from pg_falso import ApiPGFalsa, Resposta
from sessao_real_sem_rede import sessao_real

from nexus.casca import fracttal_conta as C
from nexus.casca import uso_os as U
from nexus.dados import catalogo, explica, livros
from nexus.dados import fato_uso_os as F
from nexus.dados.fato_ronda import GraoDuplicado

BASE = "http://pg.falso"
TOKEN = "token-de-teste"
H10, H11, H12 = "2026103010", "2026103011", "2026103012"
_CHAVE_PESSOA = "chave-de-pessoa-de-teste"
_EMAIL = "pessoa.um@exemplo.invalid"
_SETOR = "Setor Fictício Alfa"
LIVRO_OUT = "nexus_oscreator_uso_2026_10"


# ── o banco de mentira e seus defeitos ───────────────────────────────────────────────────────────────────────────────
class ApiQueFalha(ApiPGFalsa):
    """O banco que cai: os `cai` próximos pedidos de gravação (POST) falham com erro de rede, antes de gravar nada."""

    def __init__(self, cai=0, **kw):
        super().__init__(**kw)
        self.cai = cai

    def post(self, url, **kw):
        if self.cai > 0:
            self.cai -= 1
            raise requests.ConnectionError("banco fora")
        return super().post(url, **kw)


class ApiQueDizNone(ApiPGFalsa):
    """O `sync-xlsx` real devolve a célula vazia como o texto "None" (a nota do `almoxarifado.contado`)."""

    def get(self, url, params=None, headers=None, timeout=None):
        r = super().get(url, params=params, headers=headers, timeout=timeout)
        if re.search(r"/api/sheets/\d+/rows$", url):
            return Resposta(200, [{"headers": x["headers"], "values": ["None" if v is None else v for v in x["values"]]}
                                  for x in r.json()])
        return r


class ApiQueDevolveDecimal(ApiPGFalsa):
    """O banco que devolve o inteiro como número com ponto ("2026103010.0", "120.0"): a coluna com célula vazia vira decimal."""

    def get(self, url, params=None, headers=None, timeout=None):
        r = super().get(url, params=params, headers=headers, timeout=timeout)
        if re.search(r"/api/sheets/\d+/rows$", url):
            return Resposta(200, [{"headers": x["headers"], "values": [
                float(v) if isinstance(v, int) and not isinstance(v, bool) else v for v in x["values"]]} for x in r.json()])
        return r


class ApiComLeituraCurta(ApiPGFalsa):
    """A página de linhas que volta sem a última (a listagem segue dizendo o `row_count` de verdade)."""
    curta = False

    def get(self, url, params=None, headers=None, timeout=None):
        r = super().get(url, params=params, headers=headers, timeout=timeout)
        if self.curta and re.search(r"/api/sheets/\d+/rows$", url):
            return Resposta(200, r.json()[:-1])
        return r


@pytest.fixture(params=[False, True], ids=["tipos", "como_texto"])
def api(request):
    return ApiPGFalsa(como_texto=request.param)


# ── as linhas como os contadores as entregam (`drenar`) ──────────────────────────────────────────────────────────────
def _uso(hora_id, rota="/os/historico", automatico=0, **kw):
    d = {"hora_id": hora_id, "rota": rota, "automatico": automatico, "pedidos_qtd": 10, "pessoas_qtd": 3,
         "duracao_p50_ms": 120, "duracao_p95_ms": 900, "erros_qtd": 0, "ocupado_qtd": 0, "fracttal_qtd": 4}
    d.update(kw)
    return d


def _fra(hora_id, origem="/os/historico", metodo="work_orders", **kw):
    d = {"hora_id": hora_id, "origem": origem, "metodo": metodo, "pedidos_qtd": 4, "recusas_qtd": 0, "erros_qtd": 0,
         "pico_minuto_qtd": 2}
    d.update(kw)
    return d


def _gravar(api, uso, fra):
    return F.gravar(uso, fra, base=BASE, token=TOKEN, sessao=api)


def _int(v):
    return None if v is None else int(float(v))


def _chaves(api, livro, aba, colunas):
    return [tuple(str(_int(l[c]) if c in ("hora_id", "automatico") else l[c]) for c in colunas)
            for l in api.linhas(livro, aba)]


# ── o grão e a chave ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_grao_e_chave():
    ok = [_uso(H10), _uso(H10, automatico=1), _uso(H10, "/os/os/<n>"), _uso(H11)]
    F.conferir_grao(ok, F.ABA_USO)                    # a mesma hora × rota, clique e automático: duas linhas, não uma
    with pytest.raises(GraoDuplicado):
        F.conferir_grao(ok + [_uso(H10, pedidos_qtd=99)], F.ABA_USO)
    total = _fra(H10, "*", "*")                       # a linha de total da hora é uma chave como as outras
    F.conferir_grao([total, _fra(H10), _fra(H10, metodo="outro"), _fra(H11, "*", "*")], F.ABA_FRACTTAL)
    with pytest.raises(GraoDuplicado):
        F.conferir_grao([total, dict(total)], F.ABA_FRACTTAL)
    with pytest.raises(GraoDuplicado):                # chave vazia também é grão quebrado
        F.conferir_grao([_uso("")], F.ABA_USO)
    # a chave do código é a do catálogo, e é a que o cabeçalho começa
    assert F.CHAVE_USO == ("hora_id", "rota", "automatico") and F.CHAVE_FRACTTAL == ("hora_id", "origem", "metodo")
    assert F.CAB_USO[0] == F.CAB_FRACTTAL[0] == "hora_id" and set(F.CHAVE_USO) <= set(F.CAB_USO)
    assert set(F.CHAVE_FRACTTAL) <= set(F.CAB_FRACTTAL)


def test_a_chave_repetida_no_lote_nao_grava_nada(api):
    with pytest.raises(GraoDuplicado):
        _gravar(api, [_uso(H10), _uso(H10)], [_fra(H10)])
    assert not api.workbooks and api.syncs == 0       # nada foi criado nem trocado


@pytest.mark.parametrize("ruim", [
    {"hora_id": "amanha"}, {"hora_id": "20261030"}, {"hora_id": "2026133010"}, {"hora_id": "2026103025"},
    {"automatico": 2}, {"pedidos_qtd": -1}, {"pedidos_qtd": None}, {"duracao_p95_ms": "lento"}, {"rota": ""}])
def test_linha_fora_da_forma_e_erro_de_quem_chama_e_nada_se_grava(api, ruim):
    with pytest.raises(ValueError):
        _gravar(api, [_uso(H10), dict(_uso(H11), **ruim)], [])
    assert not api.workbooks and api.syncs == 0


# ── gravar, regravar e o mês ─────────────────────────────────────────────────────────────────────────────────────────
def test_grava_as_duas_abas_com_data_e_hora_e_confere(api):
    rel = _gravar(api, [_uso(H10), _uso(H10, "/os/os/<n>", automatico=1, pedidos_qtd=7)],
                  [_fra(H10, "*", "*", pedidos_qtd=9, pico_minuto_qtd=5), _fra(H10, "/os/os/<n>", "get_assets")])
    assert rel["gravado"] == {LIVRO_OUT: {"fato_uso_hora": 2, "fato_fracttal_hora": 2}}
    assert rel["uso_qtd"] == 2 and rel["fracttal_qtd"] == 2
    assert set(api.workbooks) == {LIVRO_OUT} and api.tokens[0] == f"Bearer {TOKEN}"
    uso = api.linhas(LIVRO_OUT, "fato_uso_hora")
    assert list(uso[0]) == F.CAB_USO and list(api.linhas(LIVRO_OUT, "fato_fracttal_hora")[0]) == F.CAB_FRACTTAL
    # a hora de Brasília vira o dia (data_id) e a hora do dia (0 a 23)
    assert {(_int(l["hora_id"]), _int(l["data_id"]), _int(l["hora"])) for l in uso} == {(2026103010, 20261030, 10)}
    clique = next(l for l in uso if _int(l["automatico"]) == 0)
    assert clique["rota"] == "/os/historico" and _int(clique["pedidos_qtd"]) == 10 and _int(clique["pessoas_qtd"]) == 3
    assert _int(clique["duracao_p50_ms"]) == 120 and _int(clique["duracao_p95_ms"]) == 900
    # a linha de total do Fracttal (origem * e método *) vai como as outras
    fra = {(l["origem"], l["metodo"]): l for l in api.linhas(LIVRO_OUT, "fato_fracttal_hora")}
    assert _int(fra[("*", "*")]["pico_minuto_qtd"]) == 5 and _int(fra[("*", "*")]["pedidos_qtd"]) == 9


def test_mesma_hora_regravada_nao_duplica(api):
    _gravar(api, [_uso(H10), _uso(H10, "/os/os/<n>")], [_fra(H10, "*", "*"), _fra(H10)])
    # a regravação da hora 10 (a gravação seguinte falhou na conferência, ou voltou depois do reinício) mais a hora 11
    _gravar(api, [_uso(H10, pedidos_qtd=11), _uso(H10, "/os/os/<n>"), _uso(H11)], [_fra(H10, "*", "*", pedidos_qtd=8), _fra(H11)])
    chaves = _chaves(api, LIVRO_OUT, "fato_uso_hora", F.CHAVE_USO)
    assert len(chaves) == len(set(chaves)) == 3
    uso = {(_int(l["hora_id"]), l["rota"]): l for l in api.linhas(LIVRO_OUT, "fato_uso_hora")}
    assert _int(uso[(2026103010, "/os/historico")]["pedidos_qtd"]) == 11      # a linha mais nova vale
    assert _int(uso[(2026103010, "/os/os/<n>")]["pedidos_qtd"]) == 10         # a que não veio de novo fica como estava
    fra = _chaves(api, LIVRO_OUT, "fato_fracttal_hora", F.CHAVE_FRACTTAL)
    assert len(fra) == len(set(fra)) == 3
    total = next(l for l in api.linhas(LIVRO_OUT, "fato_fracttal_hora") if l["origem"] == "*" and _int(l["hora_id"]) == 2026103010)
    assert _int(total["pedidos_qtd"]) == 8
    # regravar exatamente o mesmo lote outra vez não muda nada
    antes = (api.linhas(LIVRO_OUT, "fato_uso_hora"), api.linhas(LIVRO_OUT, "fato_fracttal_hora"))
    _gravar(api, [_uso(H10, pedidos_qtd=11), _uso(H11)], [_fra(H11)])
    assert (api.linhas(LIVRO_OUT, "fato_uso_hora"), api.linhas(LIVRO_OUT, "fato_fracttal_hora")) == antes


def test_regravar_conserva_o_tipo_dos_numeros():
    """O livro lido de volta (como texto, na API real) é regravado com número de novo, não com o texto do número."""
    api = ApiPGFalsa(como_texto=False)
    _gravar(api, [_uso(H10)], [_fra(H10)])
    _gravar(api, [_uso(H11)], [])
    for l in api.linhas(LIVRO_OUT, "fato_uso_hora"):
        assert all(isinstance(l[c], int) for c in ("hora_id", "data_id", "hora", "automatico", "pedidos_qtd", "pessoas_qtd",
                                                   "duracao_p50_ms", "duracao_p95_ms", "erros_qtd", "ocupado_qtd",
                                                   "fracttal_qtd")), l
    assert all(isinstance(l["pedidos_qtd"], int) for l in api.linhas(LIVRO_OUT, "fato_fracttal_hora"))


def test_a_celula_vazia_volta_vazia_e_nao_o_texto_none():
    """Um balde só de pedidos recusados pelo teto não tem duração: a célula fica vazia, e a releitura (que no banco real
    devolve o texto "None") não a transforma em texto."""
    api = ApiQueDizNone()
    _gravar(api, [_uso(H10, "/os/api/ocupada", pedidos_qtd=3, ocupado_qtd=3, duracao_p50_ms=None, duracao_p95_ms=None)], [])
    _gravar(api, [_uso(H11)], [])
    vazia = next(l for l in api.linhas(LIVRO_OUT, "fato_uso_hora") if l["rota"] == "/os/api/ocupada")
    assert vazia["duracao_p50_ms"] is None and vazia["duracao_p95_ms"] is None and _int(vazia["ocupado_qtd"]) == 3


def test_o_banco_que_devolve_o_inteiro_com_ponto_zero_nao_repete_a_hora():
    """Se a chave relida ("2026103010.0") não casasse com a nova ("2026103010"), cada gravação repetiria a hora."""
    api = ApiQueDevolveDecimal()
    _gravar(api, [_uso(H10), _uso(H10, "/os/b", automatico=1)], [_fra(H10, "*", "*")])
    _gravar(api, [_uso(H10, pedidos_qtd=12), _uso(H11)], [_fra(H10, "*", "*", pedidos_qtd=9)])
    uso = api.linhas(LIVRO_OUT, "fato_uso_hora")
    assert len(uso) == 3 and len({(l["hora_id"], l["rota"], l["automatico"]) for l in uso}) == 3
    assert {l["pedidos_qtd"] for l in uso if l["hora_id"] == int(H10) and l["rota"] == "/os/historico"} == {12}
    fra = api.linhas(LIVRO_OUT, "fato_fracttal_hora")
    assert len(fra) == 1 and fra[0]["pedidos_qtd"] == 9                          # a linha de total foi trocada, não repetida


def test_o_livro_sai_em_ordem_em_qualquer_maquina(api):
    _gravar(api, [_uso(H11, "/os/z"), _uso(H10, "/os/b", automatico=1), _uso(H10, "/os/a")], [])
    _gravar(api, [_uso(H12, "/os/c")], [])
    ordem = [(_int(l["hora_id"]), l["rota"], _int(l["automatico"])) for l in api.linhas(LIVRO_OUT, "fato_uso_hora")]
    assert ordem == sorted(ordem) and len(ordem) == 4        # a mesma ordem em qualquer máquina


@pytest.mark.parametrize("hora_a, hora_b, livro_a, livro_b", [
    ("2026103123", "2026110100", "nexus_oscreator_uso_2026_10", "nexus_oscreator_uso_2026_11"),     # virada do mês
    ("2026123123", "2027010100", "nexus_oscreator_uso_2026_12", "nexus_oscreator_uso_2027_01")])    # virada do ano
def test_virada_do_mes_vai_a_dois_livros(api, hora_a, hora_b, livro_a, livro_b):
    rel = _gravar(api, [_uso(hora_a), _uso(hora_b), _uso(hora_b, "/os/os/<n>")], [_fra(hora_a, "*", "*"), _fra(hora_b, "*", "*")])
    assert set(api.workbooks) == {livro_a, livro_b} and set(rel["gravado"]) == {livro_a, livro_b}
    assert [_int(l["hora_id"]) for l in api.linhas(livro_a, "fato_uso_hora")] == [int(hora_a)]
    assert sorted(_int(l["hora_id"]) for l in api.linhas(livro_b, "fato_uso_hora")) == [int(hora_b)] * 2
    assert [_int(l["hora_id"]) for l in api.linhas(livro_b, "fato_fracttal_hora")] == [int(hora_b)]
    assert F.livro_do_mes(hora_a) == livro_a and F.livro_do_mes(hora_b) == livro_b
    # o lote regravado não duplica em nenhum dos dois, e o mês de antes não ganha a linha do mês de depois
    _gravar(api, [_uso(hora_a), _uso(hora_b), _uso(hora_b, "/os/os/<n>")], [_fra(hora_a, "*", "*"), _fra(hora_b, "*", "*")])
    assert len(api.linhas(livro_a, "fato_uso_hora")) == 1 and len(api.linhas(livro_b, "fato_uso_hora")) == 2


def test_hora_so_de_uma_das_abas_nao_apaga_a_outra(api):
    """Gravar um livro troca o livro inteiro: a aba que o lote não traz tem de seguir como estava."""
    _gravar(api, [_uso(H10)], [_fra(H10, "*", "*")])
    _gravar(api, [], [_fra(H11, "*", "*")])
    _gravar(api, [_uso(H12)], [])
    assert len(api.linhas(LIVRO_OUT, "fato_uso_hora")) == 2 and len(api.linhas(LIVRO_OUT, "fato_fracttal_hora")) == 2


def test_sem_linhas_nao_toca_no_banco(api):
    assert _gravar(api, [], []) == {"gravado": {}, "uso_qtd": 0, "fracttal_qtd": 0}
    assert not api.workbooks and api.syncs == 0 and not api.tokens


def test_falha_na_conferencia_depois_de_gravar_sobe_e_a_regravacao_conserta():
    """O banco que perdeu uma linha na gravação: `livros.publicar` acusa, e a hora seguinte, relendo o livro, completa."""
    ruim = ApiPGFalsa(perder=1)
    with pytest.raises(livros.GravacaoErro):
        _gravar(ruim, [_uso(H10), _uso(H10, "/os/b"), _uso(H10, "/os/c")], [])
    assert len(ruim.linhas(LIVRO_OUT, "fato_uso_hora")) == 2                    # chegou uma a menos
    ruim.perder = 0
    _gravar(ruim, [_uso(H10), _uso(H10, "/os/b"), _uso(H10, "/os/c")], [])
    assert len(ruim.linhas(LIVRO_OUT, "fato_uso_hora")) == 3


def test_leitura_curta_do_livro_nao_grava_por_cima():
    """Página que volta sem a última linha daria um livro menor; a gravação de UMA linha o levaria de volta ao tamanho que
    a trava `so_cresce` aceita, apagando as últimas (a mesma lição do livro do inventário, 26/10/2026)."""
    api = ApiComLeituraCurta()
    _gravar(api, [_uso(H10), _uso(H10, "/os/b"), _uso(H10, "/os/c")], [_fra(H10, "*", "*")])
    syncs, linhas = api.syncs, api.linhas(LIVRO_OUT, "fato_uso_hora")
    api.curta = True
    with pytest.raises(F.LeituraIncompleta):
        _gravar(api, [_uso(H11), _uso(H11, "/os/b"), _uso(H11, "/os/c"), _uso(H11, "/os/d")], [])
    assert api.syncs == syncs and api.linhas(LIVRO_OUT, "fato_uso_hora") == linhas


# ── nada pessoal no banco ────────────────────────────────────────────────────────────────────────────────────────────
def test_nada_pessoal_nas_colunas(api):
    proibidas = ("nome", "email", "mail", "setor", "pessoa", "usuario", "login", "hmac", "cpf", "telefone", "token", "senha")
    for cab in (F.CAB_USO, F.CAB_FRACTTAL):
        # só a contagem de pessoas distintas (`pessoas_qtd`) é permitida: nunca quem
        assert [c for c in cab if any(p in c for p in proibidas) and c != "pessoas_qtd"] == [], cab
    assert F.CAB_USO == ["hora_id", "data_id", "hora", "rota", "automatico", "pedidos_qtd", "pessoas_qtd",
                         "duracao_p50_ms", "duracao_p95_ms", "erros_qtd", "ocupado_qtd", "fracttal_qtd"]
    assert F.CAB_FRACTTAL == ["hora_id", "data_id", "hora", "origem", "metodo", "pedidos_qtd", "recusas_qtd", "erros_qtd",
                              "pico_minuto_qtd"]
    # a coluna que o lote traz a mais (um setor, uma pessoa) não vai ao banco: o livro só tem as colunas do contrato
    _gravar(api, [dict(_uso(H10), setor="Setor Fictício", pessoa="alguem@exemplo.invalid")], [dict(_fra(H10), quem="x")])
    for aba in F.ABAS:
        assert list(api.linhas(LIVRO_OUT, aba)[0]) == F.CABS[aba]
    assert "@" not in repr([api.linhas(LIVRO_OUT, aba) for aba in F.ABAS]) and "Setor" not in repr(api.abas)


def test_rota_com_e_mail_no_caminho_vira_id_antes_de_ir_ao_banco():
    """Quem digita um e-mail no endereço (`/os/maria@exemplo.invalid`) não o deixa na rota que o contador guarda: o banco é de
    leitura aberta e não apaga."""
    assert "@" not in U.normalizar_rota("/os/pessoa.um@exemplo.invalid/historico")
    assert U.normalizar_rota("/os/pessoa.um@exemplo.invalid/historico") == "/os/<id>/historico"
    assert U.normalizar_rota("/os/historico") == "/os/historico"


# ── o catálogo e a trava ─────────────────────────────────────────────────────────────────────────────────────────────
def test_catalogo_registra_o_livro_e_os_fatos():
    lv = catalogo.LIVRO_POR_NOME[F.LIVRO_MOLDE]
    assert F.LIVRO_MOLDE == "nexus_oscreator_uso_AAAA_MM" and lv.abas == (F.ABA_USO, F.ABA_FRACTTAL)
    assert lv.so_cresce == lv.abas and lv.no_banco is False        # as duas abas só crescem; registrado antes de existir
    assert "uso_os.py" in lv.quem_grava and "servidor" in lv.cadencia + lv.observacao
    # a família: o livro de cada mês casa pelo padrão, acha a trava do molde e a aba é da família (o radar não a acha "nova")
    assert any(p.match("nexus_oscreator_uso_2026_10") for p in catalogo.FAMILIAS)
    assert not any(p.match(n) for p in catalogo.FAMILIAS for n in
                   ("nexus_oscreator_uso_2026_1", "nexus_oscreator_uso", "nexus_oscreator_uso_2026_10_x", "x_nexus_oscreator_uso_2026_10"))
    assert livros._do_catalogo("nexus_oscreator_uso_2026_10") is lv and livros._so_cresce("nexus_oscreator_uso_2026_10") == lv.abas
    assert catalogo.da_familia("nexus_oscreator_uso_2026_10", F.ABA_USO) and catalogo.da_familia("nexus_oscreator_uso_2027_01", F.ABA_FRACTTAL)
    assert not catalogo.da_familia("nexus_oscreator_uso_2026_10", "outra")
    for fid, aba, cab, chave in (("uso_os_hora", F.ABA_USO, F.CAB_USO, F.CHAVE_USO),
                                 ("fracttal_hora", F.ABA_FRACTTAL, F.CAB_FRACTTAL, F.CHAVE_FRACTTAL)):
        f = catalogo.POR_ID[fid]
        assert f.livro == f.conformado_em == f"{F.LIVRO_MOLDE} · {aba}" and f.fontes == (f.livro,) and f.estado == "conformado"
        assert f.tipo == "snapshot_periodico" and f.chave == chave and f.area == "os" and f.grao.startswith("1 linha")
        assert f.dims["data"][0] == "id" and all(f.dims[d][0] == "nao" for d in catalogo.DIM_IDS if d != "data")
        assert f.medidas and all(m.coluna in cab and catalogo.medida_valida(m) for m in f.medidas)
        assert "o Nexus é a fonte" in f.janela_origem
        assert fid in explica.RESUMO and fid in explica.PARA_QUE        # a camada cobra o texto amigável
    # a soma de cada medida: a contagem de pedidos soma; pessoas distintas, tempo e o pico por minuto, nunca
    uso = {m.coluna: m for m in catalogo.POR_ID["uso_os_hora"].medidas}
    assert uso["pedidos_qtd"].soma == uso["erros_qtd"].soma == uso["ocupado_qtd"].soma == uso["fracttal_qtd"].soma == "aditiva"
    assert uso["pessoas_qtd"].soma == uso["duracao_p50_ms"].soma == uso["duracao_p95_ms"].soma == "nao"
    assert uso["duracao_p50_ms"].unidade == "ms" and catalogo.medida_valida(uso["duracao_p95_ms"])
    fra = {m.coluna: m for m in catalogo.POR_ID["fracttal_hora"].medidas}
    assert fra["pedidos_qtd"].soma == fra["recusas_qtd"].soma == fra["erros_qtd"].soma == "aditiva"
    assert fra["pico_minuto_qtd"].soma == "nao"


# ── o laço de gravação ───────────────────────────────────────────────────────────────────────────────────────────────
class _Relogio:
    """O relógio na mão (a hora de Brasília e o cronômetro do pedido andam só quando o teste manda)."""

    def __init__(self, utc="2026-10-30T13:00:00+00:00"):
        self.t = datetime.fromisoformat(utc).timestamp()

    def agora(self):
        return self.t

    def cronometro(self):
        return self.t

    def passa(self, segundos):
        self.t += segundos

    def em(self, utc):
        self.t = datetime.fromisoformat(utc).timestamp()
        return self


@pytest.fixture
def relogio(monkeypatch):
    """Os dois contadores zerados e o relógio na mão (10:00 de Brasília = 13:00Z). O `Session.send` volta ao que era."""
    monkeypatch.setattr(requests.sessions.Session, "send", requests.sessions.Session.send)
    r = _Relogio()
    monkeypatch.setattr(U, "_agora", r.agora)
    monkeypatch.setattr(U, "_cronometro", r.cronometro)
    monkeypatch.setattr(C, "_agora", r.agora)
    C.limpar()
    U.limpar()
    C.ligar()
    yield r
    C.limpar()
    U.limpar()


@pytest.fixture
def setor(monkeypatch):
    from nexus.auth import setor_telas
    monkeypatch.setattr(setor_telas, "acesso", lambda: {"tudo": True, "telas": set(), "setor": {"id": 1, "nome": _SETOR}, "erro": ""})


@pytest.fixture
def mini(tmp_path, relogio, setor):
    """Um Flask de mentira com duas telas do OS Creator (uma pede ao Fracttal), o uso ligado como no servidor."""
    app = Flask(__name__)
    app.config.update(SECRET_KEY="chave-de-teste", TESTING=True, NEXUS_DADOS=str(tmp_path), NEXUS_PESSOA_HMAC=_CHAVE_PESSOA,
                      GRIDCO_SQL_TOKEN=TOKEN, GRIDCO_DB_API=BASE)
    fracttal, _ = sessao_real(*[(200, None)] * 800)

    @app.route("/os/historico")
    def historico():
        return "ok"

    @app.route("/os/os/<int:wid>")
    def card(wid):
        fracttal.get("https://app.fracttal.com/api/work_orders")
        return "card"

    U.ligar(app, gravar=True)
    return app


def _clica(app, rota="/os/historico", hora_utc=None, relogio=None, email=_EMAIL):
    if hora_utc:
        relogio.em(hora_utc)
    c = app.test_client()
    with c.session_transaction() as s:
        s["logado"] = True
        s["usuario"] = {"email": email}
    assert c.get(rota).status_code == 200


def test_o_laco_tira_so_as_horas_fechadas_e_a_hora_aberta_e_lida_antes_dos_dois(mini, relogio, monkeypatch):
    """A hora aberta fica onde está, a mesma nos dois `drenar`, lida ANTES de qualquer um: o relógio que anda entre os dois
    não faz o segundo passar uma hora que ainda não fechou."""
    vistos = []

    def uso(ate):
        vistos.append(("uso", ate))
        relogio.passa(3600)                           # o tempo anda entre os dois
        return []

    def fracttal(ate):
        vistos.append(("fracttal", ate))
        return []
    monkeypatch.setattr(U, "drenar", uso)
    monkeypatch.setattr(C, "drenar", fracttal)
    relogio.em("2026-10-30T14:07:00+00:00")           # 11:07 em Brasília
    U.gravar_no_banco(mini.config, sessao=ApiPGFalsa())
    assert vistos == [("uso", H11), ("fracttal", H11)]


def test_falha_guarda_para_a_proxima_hora(mini, relogio):
    _clica(mini, "/os/os/1", "2026-10-30T13:10:00+00:00", relogio)               # 10:10: um pedido que vai ao Fracttal
    _clica(mini, "/os/historico")
    relogio.em("2026-10-30T14:05:00+00:00")                                      # 11:05: o laço
    caiu = ApiQueFalha(cai=1)
    rel = U.gravar_no_banco(mini.config, sessao=caiu)
    assert "erro" in rel and not caiu.workbooks and rel["pendentes"]["horas"] == 1
    assert U.pendentes()["uso"] == 2 and U.pendentes()["fracttal"] >= 2          # guardadas, não perdidas
    assert not [l for l in U.instantaneo()["linhas"] if l["hora_id"] == H10]     # e já tiradas dos contadores (drenadas 1 vez)
    _clica(mini, "/os/os/2", "2026-10-30T14:20:00+00:00", relogio)               # 11:20, na hora seguinte
    relogio.em("2026-10-30T15:05:00+00:00")                                      # 12:05: o banco voltou
    banco = ApiPGFalsa()
    rel = U.gravar_no_banco(mini.config, sessao=banco)
    assert "erro" not in rel and rel["gravado"][LIVRO_OUT]["fato_uso_hora"] == 3
    assert U.pendentes() == {"uso": 0, "fracttal": 0, "horas": 0}
    horas = sorted((_int(l["hora_id"]), l["rota"]) for l in banco.linhas(LIVRO_OUT, "fato_uso_hora"))
    assert horas == [(2026103010, "/os/historico"), (2026103010, "/os/os/<n>"), (2026103011, "/os/os/<n>")]
    totais = {_int(l["hora_id"]): _int(l["pedidos_qtd"]) for l in banco.linhas(LIVRO_OUT, "fato_fracttal_hora") if l["origem"] == "*"}
    assert totais == {2026103010: 1, 2026103011: 1}
    # uma volta sem hora nova não grava de novo
    syncs = banco.syncs
    assert U.gravar_no_banco(mini.config, sessao=banco).get("pulou") and banco.syncs == syncs


def test_a_falha_ao_ler_o_livro_tambem_guarda_as_linhas(mini, relogio):
    _clica(mini, "/os/historico", "2026-10-30T13:10:00+00:00", relogio)
    relogio.em("2026-10-30T14:05:00+00:00")
    banco = ApiComLeituraCurta()
    U.gravar_no_banco(mini.config, sessao=banco)                                 # cria o livro com a hora 10
    _clica(mini, "/os/historico", "2026-10-30T14:30:00+00:00", relogio)
    relogio.em("2026-10-30T15:05:00+00:00")
    banco.curta = True
    rel = U.gravar_no_banco(mini.config, sessao=banco)                           # a leitura curta recusa; a hora 11 espera
    assert "erro" in rel and U.pendentes()["uso"] == 1 and len(banco.linhas(LIVRO_OUT, "fato_uso_hora")) == 1
    banco.curta = False
    relogio.em("2026-10-30T16:05:00+00:00")
    U.gravar_no_banco(mini.config, sessao=banco)
    assert len(banco.linhas(LIVRO_OUT, "fato_uso_hora")) == 2 and U.pendentes()["uso"] == 0


def test_horas_pendentes_tem_teto_de_48(mini, relogio, caplog):
    """O banco fora por dias não enche a memória: ficam as 48 horas mais novas (a decisão do desenho), e o aviso vai ao log."""
    fora = ApiQueFalha(cai=10_000)
    relogio.em("2026-10-30T13:10:00+00:00")                                       # 10:10
    with caplog.at_level(logging.WARNING):
        for _ in range(52):                          # uma hora nova a cada volta, todas com o banco fora
            _clica(mini, "/os/os/1")
            relogio.passa(3600)
            U.gravar_no_banco(mini.config, sessao=fora)
    assert U.pendentes()["horas"] == 48 and not fora.workbooks
    assert "descartei" in caplog.text
    horas = sorted({l["hora_id"] for l in U._pendentes["uso"]})
    assert len(horas) == 48 and horas[0] == "2026103014" and horas[-1] == "2026110113"       # as 48 mais novas
    banco = ApiPGFalsa()
    relogio.passa(3600)
    U.gravar_no_banco(mini.config, sessao=banco)
    gravadas = {_int(l["hora_id"]) for livro in ("nexus_oscreator_uso_2026_10", "nexus_oscreator_uso_2026_11")
                for l in banco.linhas(livro, "fato_uso_hora")}
    assert len(gravadas) == 48 and U.pendentes()["horas"] == 0 and len(banco.workbooks) == 2


def test_sem_o_token_nao_grava_e_guarda(mini, relogio):
    _clica(mini, "/os/historico", "2026-10-30T13:10:00+00:00", relogio)
    relogio.em("2026-10-30T14:05:00+00:00")
    banco = ApiPGFalsa()
    config = dict(mini.config, GRIDCO_SQL_TOKEN="")
    rel = U.gravar_no_banco(config, sessao=banco)
    assert "GRIDCO_SQL_TOKEN" in rel["erro"] and not banco.workbooks and banco.syncs == 0
    assert U.pendentes()["uso"] == 1                                              # guardada para quando houver chave


def test_em_teste_sem_sessao_nunca_vai_a_rede(mini, relogio, monkeypatch):
    def sem_rede(*a, **k):
        raise AssertionError("o teste foi à rede")
    monkeypatch.setattr(requests, "Session", sem_rede)
    _clica(mini, "/os/historico", "2026-10-30T13:10:00+00:00", relogio)
    relogio.em("2026-10-30T14:05:00+00:00")
    assert "teste" in U.gravar_no_banco(mini.config)["pulou"]


def test_gravou_salva_o_parcial_e_o_reinicio_nao_traz_a_hora_de_volta(mini, relogio, tmp_path):
    _clica(mini, "/os/historico", "2026-10-30T13:10:00+00:00", relogio)
    U.salvar()                                                                    # o laço de 5 min já guardou a hora 10
    assert H10 in (tmp_path / "casca" / "uso_os_parcial.json").read_text(encoding="utf-8")
    relogio.em("2026-10-30T14:05:00+00:00")
    U.gravar_no_banco(mini.config, sessao=ApiPGFalsa())
    assert H10 not in (tmp_path / "casca" / "uso_os_parcial.json").read_text(encoding="utf-8")
    U.limpar()
    app2 = Flask(__name__)
    app2.config.update(SECRET_KEY="x", TESTING=True, NEXUS_DADOS=str(tmp_path))
    U.ligar(app2, gravar=True)                                                    # o "reinício": lê o parcial do disco
    assert not [l for l in U.instantaneo()["linhas"] if l["hora_id"] == H10]


def test_a_falha_nao_salva_o_parcial(mini, relogio, tmp_path):
    """Com o banco fora o parcial segue como estava: o reinício ainda traz a hora de volta e o laço a grava."""
    _clica(mini, "/os/historico", "2026-10-30T13:10:00+00:00", relogio)
    U.salvar()
    antes = (tmp_path / "casca" / "uso_os_parcial.json").read_text(encoding="utf-8")
    relogio.em("2026-10-30T14:05:00+00:00")
    U.gravar_no_banco(mini.config, sessao=ApiQueFalha(cai=1))
    assert (tmp_path / "casca" / "uso_os_parcial.json").read_text(encoding="utf-8") == antes


@pytest.mark.parametrize("utc, esperado", [
    ("2026-10-30T13:00:00+00:00", 300), ("2026-10-30T13:04:59+00:00", 1), ("2026-10-30T13:05:00+00:00", 3600),
    ("2026-10-30T13:30:00+00:00", 2100), ("2026-10-30T13:59:59+00:00", 301), ("2026-10-30T23:59:00+00:00", 360)])
def test_o_laco_acorda_no_minuto_5_de_cada_hora(utc, esperado):
    assert U.espera_ate_a_gravacao(datetime.fromisoformat(utc).timestamp()) == pytest.approx(esperado)
    assert U.GRAVAR_NO_MINUTO == 5


def test_o_laco_de_gravacao_so_liga_no_servidor(tmp_path, relogio, monkeypatch):
    gravacao, cinco_min = threading.Event(), threading.Event()
    monkeypatch.setattr(U, "_laco_gravacao", lambda: gravacao.set())
    monkeypatch.setattr(U, "_laco", cinco_min.set)

    def app_(**extra):
        a = Flask(__name__)
        a.config.update(SECRET_KEY="x", NEXUS_DADOS=str(tmp_path), **extra)
        return a
    U.ligar(app_(TESTING=True), gravar=True)                                      # teste: nenhum dos dois
    assert not gravacao.wait(0.3) and not cinco_min.wait(0.1)
    U.limpar()
    U.ligar(app_(TESTING=False), gravar=False)                                    # o PC: só o de 5 min, a gravação não
    assert cinco_min.wait(3) and not gravacao.wait(0.3)
    U.limpar()
    U.ligar(app_(TESTING=False), gravar=True)                                     # o servidor: os dois
    assert gravacao.wait(3)
    assert U.MAX_HORAS_PENDENTES == 48


# ── a ponta a ponta, com os contadores de verdade ────────────────────────────────────────────────────────────────────
def test_ponta_a_ponta_grava_as_horas_fechadas_e_nada_pessoal_vai_ao_banco(mini, relogio):
    relogio.em("2026-10-30T13:10:00+00:00")                                       # 10:10
    _clica(mini, "/os/os/16995")
    _clica(mini, "/os/os/16996")
    _clica(mini, "/os/historico")
    relogio.em("2026-10-30T14:02:00+00:00")                                       # 11:02: já é a hora seguinte, a aberta
    _clica(mini, "/os/historico")
    banco = ApiPGFalsa()
    relogio.em("2026-10-30T14:05:00+00:00")                                       # 11:05: o laço
    rel = U.gravar_no_banco(mini.config, sessao=banco)
    assert rel["gravado"][LIVRO_OUT]["fato_uso_hora"] == 2 and rel["uso_qtd"] == 2
    uso = {l["rota"]: l for l in banco.linhas(LIVRO_OUT, "fato_uso_hora")}
    assert set(uso) == {"/os/os/<n>", "/os/historico"} and uso["/os/os/<n>"]["pedidos_qtd"] == 2
    assert uso["/os/os/<n>"]["pessoas_qtd"] == 1 and uso["/os/os/<n>"]["fracttal_qtd"] == 2
    total = next(l for l in banco.linhas(LIVRO_OUT, "fato_fracttal_hora") if l["origem"] == "*")
    assert total["pedidos_qtd"] == 2 and total["pico_minuto_qtd"] == 2 and total["hora_id"] == int(H10)
    # a hora aberta (a das 11) ficou nos contadores e não foi ao banco
    assert [l["hora_id"] for l in U.instantaneo()["linhas"]] == [H11]
    # o setor, o e-mail e o código da pessoa não estão em lugar nenhum do banco (tabelas, cabeçalhos, livros)
    from nexus.campo.ligacao_cadastro import codigo_da_pessoa
    tudo = repr(banco.abas) + repr(banco.workbooks)
    for proibido in (_SETOR, _EMAIL, "exemplo.invalid", codigo_da_pessoa(_CHAVE_PESSOA, _EMAIL), "Setor"):
        assert proibido not in tudo, proibido
    # mas o corte por setor existe na memória do servidor (e no disco dele), para o Raio-X
    assert _SETOR in U.instantaneo()["setor"]["20261030"]

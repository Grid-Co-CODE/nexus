"""A gravação do uso do OS Creator e dos pedidos ao Fracttal no banco (31/10/2026, etapa 0 do canto central do OS Creator,
tarefa 0.3, com os Rulings M e N da controladora). Até aqui os dois contadores só viviam na memória do processo: um deploy ou
um reinício apagava a história, e o "antes e depois" de cada etapa seguinte seria chute. Agora o servidor tira as horas
fechadas dos contadores de hora em hora (no :05) e as guarda no DISCO dele (`casca/uso_os_pendente.json`); ao BANCO elas vão
UMA vez por dia, às 04:45 de Brasília, num livro por mês (`nexus_oscreator_uso_AAAA_MM`, três abas: o uso, o detalhe do
Fracttal e o total da hora). Reescrever o livro do mês inteiro a cada hora custaria ~7 s de processador no GIL do único
processo do Nexus (medido em 31/10/2026); uma vez por dia, no horário mais parado, custa o mesmo e não trava ninguém.

Provas, sem rede (a API do banco é a `ApiPGFalsa`, inclusive com `como_texto=True`, que devolve tudo como texto, e com a que
devolve a célula vazia como o texto "None", como o `sync-xlsx` real; o Flask é de mentira, o Fracttal é um adaptador falso do
`requests` e o relógio está na mão): o grão e a chave das três abas; o total da hora na aba dele e o detalhe sem a linha `*`;
a mesma hora regravada que não duplica; a virada do mês e do ano que vai a dois livros; nada de pessoa, setor nem e-mail no
banco; o catálogo e a trava `so_cresce`; o que o laço faz de hora em hora (disco, nunca o banco) e às 04:45 (o banco); o
pendente que sobrevive ao reinício, que vem quebrado, que tem teto de 3 dias; a leitura curta do livro que não grava por
cima; e a ponta a ponta com os contadores de verdade."""
import json
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
LIVRO_NOV = "nexus_oscreator_uso_2026_11"
ABA_USO, ABA_FRA, ABA_TOT = "fato_uso_hora", "fato_fracttal_hora", "fato_fracttal_total_hora"


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
         "pico_minuto_qtd": 2, "esperas_qtd": 0}
    d.update(kw)
    return d


def _total(hora_id, **kw):
    """A linha de total que o `fracttal_conta.drenar` entrega no meio das outras (origem e método `*`): quem a leva à aba
    própria é o `fato_uso_os.gravar`."""
    return _fra(hora_id, "*", "*", **kw)


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
    F.conferir_grao([_fra(H10), _fra(H10, metodo="outro"), _fra(H11)], F.ABA_FRACTTAL)
    with pytest.raises(GraoDuplicado):
        F.conferir_grao([_fra(H10), dict(_fra(H10))], F.ABA_FRACTTAL)
    F.conferir_grao([_total(H10), _total(H11)], F.ABA_TOTAL)           # o total: 1 linha por hora
    with pytest.raises(GraoDuplicado):
        F.conferir_grao([_total(H10), _total(H10, pedidos_qtd=9)], F.ABA_TOTAL)
    with pytest.raises(GraoDuplicado):                # chave vazia também é grão quebrado
        F.conferir_grao([_uso("")], F.ABA_USO)
    # a chave do código é a do catálogo, e é a que o cabeçalho começa
    assert F.CHAVE_USO == ("hora_id", "rota", "automatico") and F.CHAVE_FRACTTAL == ("hora_id", "origem", "metodo")
    assert F.CHAVE_TOTAL == ("hora_id",)
    assert F.CAB_USO[0] == F.CAB_FRACTTAL[0] == F.CAB_FRACTTAL_TOTAL[0] == "hora_id" and set(F.CHAVE_USO) <= set(F.CAB_USO)
    assert set(F.CHAVE_FRACTTAL) <= set(F.CAB_FRACTTAL) and F.ABAS == (ABA_USO, ABA_FRA, ABA_TOT)


def test_a_chave_repetida_no_lote_nao_grava_nada(api):
    with pytest.raises(GraoDuplicado):
        _gravar(api, [_uso(H10), _uso(H10)], [_fra(H10)])
    with pytest.raises(GraoDuplicado):                # duas linhas de total na mesma hora
        _gravar(api, [_uso(H10)], [_total(H10), _total(H10, pedidos_qtd=7)])
    with pytest.raises(GraoDuplicado):
        _gravar(api, [_uso(H10)], [_fra(H10), _fra(H10)])
    assert not api.workbooks and api.syncs == 0       # nada foi criado nem trocado


@pytest.mark.parametrize("ruim", [
    {"hora_id": "amanha"}, {"hora_id": "20261030"}, {"hora_id": "2026133010"}, {"hora_id": "2026103025"},
    {"automatico": 2}, {"pedidos_qtd": -1}, {"pedidos_qtd": None}, {"duracao_p95_ms": "lento"}, {"rota": ""}])
def test_linha_fora_da_forma_e_erro_de_quem_chama_e_nada_se_grava(api, ruim):
    with pytest.raises(ValueError):
        _gravar(api, [_uso(H10), dict(_uso(H11), **ruim)], [])
    assert not api.workbooks and api.syncs == 0


@pytest.mark.parametrize("ruim", [{"pico_minuto_qtd": None}, {"recusas_qtd": -1}, {"hora_id": "amanha"}, {"pedidos_qtd": "4"}])
def test_total_fora_da_forma_e_erro_de_quem_chama_e_nada_se_grava(api, ruim):
    with pytest.raises(ValueError):
        _gravar(api, [], [_total(H10), dict(_total(H11), **ruim)])
    assert not api.workbooks and api.syncs == 0


# ── o total da hora na aba dele (Ruling N): um total dentro do detalhe mistura dois grãos ───────────────────────────────
def test_separar_total_tira_a_linha_asterisco_do_detalhe():
    detalhe, totais = F.separar_total([_total(H10, pedidos_qtd=9, pico_minuto_qtd=5), _fra(H10), _fra(H10, "x", "y")])
    assert [(d["origem"], d["metodo"]) for d in detalhe] == [("/os/historico", "work_orders"), ("x", "y")]
    assert totais == [{"hora_id": H10, "pedidos_qtd": 9, "recusas_qtd": 0, "erros_qtd": 0, "pico_minuto_qtd": 5,
                       "esperas_qtd": 0}]
    assert F.separar_total([]) == ([], []) and F.separar_total(None) == ([], [])


@pytest.mark.parametrize("origem, metodo", [("*", "work_orders"), ("/os/historico", "*")])
def test_asterisco_so_na_origem_ou_so_no_metodo_e_grao_quebrado(api, origem, metodo):
    """Só o par `*` e `*` é o total que o contador entrega; um `*` sozinho é defeito de quem chama, e nada se grava."""
    with pytest.raises(ValueError):
        F.separar_total([_fra(H10, origem, metodo)])
    with pytest.raises(ValueError):
        _gravar(api, [_uso(H10)], [_fra(H10, origem, metodo)])
    assert not api.workbooks and api.syncs == 0


def test_o_total_vai_para_a_aba_propria_e_o_detalhe_fica_puro(api):
    _gravar(api, [_uso(H10)], [_total(H10, pedidos_qtd=9, recusas_qtd=1, erros_qtd=2, pico_minuto_qtd=5),
                               _total(H11, pedidos_qtd=3, pico_minuto_qtd=2), _fra(H10, "/os/os/<n>", "get_assets")])
    detalhe = api.linhas(LIVRO_OUT, ABA_FRA)
    assert [(l["origem"], l["metodo"]) for l in detalhe] == [("/os/os/<n>", "get_assets")]          # sem a linha `*`
    total = {_int(l["hora_id"]): l for l in api.linhas(LIVRO_OUT, ABA_TOT)}
    assert sorted(total) == [2026103010, 2026103011] and list(total[2026103010]) == F.CAB_FRACTTAL_TOTAL
    assert [_int(total[2026103010][c]) for c in ("data_id", "hora", "pedidos_qtd", "recusas_qtd", "erros_qtd",
                                                  "pico_minuto_qtd")] == [20261030, 10, 9, 1, 2, 5]
    assert _int(total[2026103011]["hora"]) == 11 and _int(total[2026103011]["pedidos_qtd"]) == 3
    assert "origem" not in total[2026103010] and "metodo" not in total[2026103010]               # 1 linha = 1 hora


def test_so_o_total_tambem_grava(api):
    """A hora em que só houve a linha de total (sem detalhe) e o livro que ainda não tem a aba do detalhe."""
    _gravar(api, [], [_total(H10)])
    assert len(api.linhas(LIVRO_OUT, ABA_TOT)) == 1 and api.linhas(LIVRO_OUT, ABA_FRA) == []


# ── as esperas no porteiro (etapa 5): a coluna no fim das duas abas do Fracttal ───────────────────────────────────────
def test_esperas_do_porteiro_vao_as_duas_abas_e_a_hora_de_antes_fica_vazia(api):
    """O porteiro do Fracttal (`casca/fracttal_conta.py`, etapa 5) conta, por linha, os pedidos que esperaram a vez: vão ao
    detalhe e ao total da hora como `esperas_qtd`, a última coluna. A linha que o contador de antes do porteiro deixou no
    pendente em disco não tem a coluna: vale (não é a linha ruim que o pendente joga fora) e vai com a célula vazia, nunca
    com um 0 inventado."""
    def sem_esperas(d):
        return {k: v for k, v in d.items() if k != "esperas_qtd"}
    velha, velho_total = sem_esperas(_fra(H11, "/os/os/<n>", "get_assets")), sem_esperas(_total(H11, pedidos_qtd=4))
    assert F.valida(velha, ABA_FRA) and F.valida(velho_total, ABA_FRA)
    _gravar(api, [], [_total(H10, pedidos_qtd=9, esperas_qtd=3), _fra(H10, "/os/os/<n>", "get_assets", esperas_qtd=2),
                      _fra(H10, "fundo:nexus-os-leitor:noite", "work_orders", esperas_qtd=1), velho_total, velha])
    assert list(api.linhas(LIVRO_OUT, ABA_FRA)[0])[-1] == "esperas_qtd"            # a coluna nova é a última das duas
    assert list(api.linhas(LIVRO_OUT, ABA_TOT)[0])[-1] == "esperas_qtd"

    def lidas():
        detalhe = {(_int(l["hora_id"]), l["origem"]): l["esperas_qtd"] for l in api.linhas(LIVRO_OUT, ABA_FRA)}
        total = {_int(l["hora_id"]): l["esperas_qtd"] for l in api.linhas(LIVRO_OUT, ABA_TOT)}
        return detalhe, total
    detalhe, total = lidas()
    assert _int(detalhe[(2026103010, "/os/os/<n>")]) == 2 and _int(detalhe[(2026103010, "fundo:nexus-os-leitor:noite")]) == 1
    assert _int(total[2026103010]) == 3
    assert detalhe[(2026103011, "/os/os/<n>")] is None and total[2026103011] is None      # antes do porteiro: vazia
    _gravar(api, [_uso(H12)], [])                     # a gravação seguinte relê o mês: o vazio não vira 0, o 3 fica 3
    assert lidas() == (detalhe, total)


@pytest.mark.parametrize("ruim", [{"esperas_qtd": -1}, {"esperas_qtd": "2"}, {"esperas_qtd": 1.5}])
def test_esperas_fora_da_forma_e_erro_de_quem_chama(api, ruim):
    with pytest.raises(ValueError):
        _gravar(api, [], [_total(H10), dict(_fra(H10), **ruim)])
    with pytest.raises(ValueError):
        _gravar(api, [], [dict(_total(H11), **ruim)])
    assert not api.workbooks and api.syncs == 0


# ── gravar, regravar e o mês ─────────────────────────────────────────────────────────────────────────────────────────
def test_grava_as_tres_abas_com_data_e_hora_e_confere(api):
    rel = _gravar(api, [_uso(H10), _uso(H10, "/os/os/<n>", automatico=1, pedidos_qtd=7)],
                  [_total(H10, pedidos_qtd=9, pico_minuto_qtd=5), _fra(H10, "/os/os/<n>", "get_assets")])
    assert rel["gravado"] == {LIVRO_OUT: {ABA_USO: 2, ABA_FRA: 1, ABA_TOT: 1}}
    assert rel["uso_qtd"] == 2 and rel["fracttal_qtd"] == 1 and rel["total_qtd"] == 1
    assert set(api.workbooks) == {LIVRO_OUT} and api.tokens[0] == f"Bearer {TOKEN}"
    uso = api.linhas(LIVRO_OUT, ABA_USO)
    assert list(uso[0]) == F.CAB_USO and list(api.linhas(LIVRO_OUT, ABA_FRA)[0]) == F.CAB_FRACTTAL
    # a hora de Brasília vira o dia (data_id) e a hora do dia (0 a 23)
    assert {(_int(l["hora_id"]), _int(l["data_id"]), _int(l["hora"])) for l in uso} == {(2026103010, 20261030, 10)}
    clique = next(l for l in uso if _int(l["automatico"]) == 0)
    assert clique["rota"] == "/os/historico" and _int(clique["pedidos_qtd"]) == 10 and _int(clique["pessoas_qtd"]) == 3
    assert _int(clique["duracao_p50_ms"]) == 120 and _int(clique["duracao_p95_ms"]) == 900
    total = api.linhas(LIVRO_OUT, ABA_TOT)
    assert len(total) == 1 and _int(total[0]["pico_minuto_qtd"]) == 5 and _int(total[0]["pedidos_qtd"]) == 9


def test_mesma_hora_regravada_nao_duplica(api):
    _gravar(api, [_uso(H10), _uso(H10, "/os/os/<n>")], [_total(H10), _fra(H10)])
    # a regravação da hora 10 (a gravação seguinte falhou na conferência, ou voltou depois do reinício) mais a hora 11
    _gravar(api, [_uso(H10, pedidos_qtd=11), _uso(H10, "/os/os/<n>"), _uso(H11)],
            [_total(H10, pedidos_qtd=8), _fra(H11)])
    chaves = _chaves(api, LIVRO_OUT, ABA_USO, F.CHAVE_USO)
    assert len(chaves) == len(set(chaves)) == 3
    uso = {(_int(l["hora_id"]), l["rota"]): l for l in api.linhas(LIVRO_OUT, ABA_USO)}
    assert _int(uso[(2026103010, "/os/historico")]["pedidos_qtd"]) == 11      # a linha mais nova vale
    assert _int(uso[(2026103010, "/os/os/<n>")]["pedidos_qtd"]) == 10         # a que não veio de novo fica como estava
    fra = _chaves(api, LIVRO_OUT, ABA_FRA, F.CHAVE_FRACTTAL)
    assert len(fra) == len(set(fra)) == 2                                     # o detalhe da hora 10 e o da 11
    total = api.linhas(LIVRO_OUT, ABA_TOT)
    assert len(total) == 1 and _int(total[0]["pedidos_qtd"]) == 8             # o total da hora 10, trocado e não repetido
    # regravar exatamente o mesmo lote outra vez não muda nada
    antes = tuple(api.linhas(LIVRO_OUT, aba) for aba in F.ABAS)
    _gravar(api, [_uso(H10, pedidos_qtd=11), _uso(H11)], [_fra(H11), _total(H10, pedidos_qtd=8)])
    assert tuple(api.linhas(LIVRO_OUT, aba) for aba in F.ABAS) == antes


def test_regravar_conserva_o_tipo_dos_numeros():
    """O livro lido de volta (como texto, na API real) é regravado com número de novo, não com o texto do número."""
    api = ApiPGFalsa(como_texto=False)
    _gravar(api, [_uso(H10)], [_fra(H10), _total(H10)])
    _gravar(api, [_uso(H11)], [])
    for l in api.linhas(LIVRO_OUT, ABA_USO):
        assert all(isinstance(l[c], int) for c in ("hora_id", "data_id", "hora", "automatico", "pedidos_qtd", "pessoas_qtd",
                                                   "duracao_p50_ms", "duracao_p95_ms", "erros_qtd", "ocupado_qtd",
                                                   "fracttal_qtd")), l
    assert all(isinstance(l["pedidos_qtd"], int) for l in api.linhas(LIVRO_OUT, ABA_FRA))
    assert all(isinstance(l[c], int) for l in api.linhas(LIVRO_OUT, ABA_TOT) for c in F.CAB_FRACTTAL_TOTAL)


def test_a_celula_vazia_volta_vazia_e_nao_o_texto_none():
    """Um balde só de pedidos recusados pelo teto não tem duração: a célula fica vazia, e a releitura (que no banco real
    devolve o texto "None") não a transforma em texto."""
    api = ApiQueDizNone()
    _gravar(api, [_uso(H10, "/os/api/ocupada", pedidos_qtd=3, ocupado_qtd=3, duracao_p50_ms=None, duracao_p95_ms=None)], [])
    _gravar(api, [_uso(H11)], [])
    vazia = next(l for l in api.linhas(LIVRO_OUT, ABA_USO) if l["rota"] == "/os/api/ocupada")
    assert vazia["duracao_p50_ms"] is None and vazia["duracao_p95_ms"] is None and _int(vazia["ocupado_qtd"]) == 3


def test_o_banco_que_devolve_o_inteiro_com_ponto_zero_nao_repete_a_hora():
    """Se a chave relida ("2026103010.0") não casasse com a nova ("2026103010"), cada gravação repetiria a hora."""
    api = ApiQueDevolveDecimal()
    _gravar(api, [_uso(H10), _uso(H10, "/os/b", automatico=1)], [_total(H10)])
    _gravar(api, [_uso(H10, pedidos_qtd=12), _uso(H11)], [_total(H10, pedidos_qtd=9)])
    uso = api.linhas(LIVRO_OUT, ABA_USO)
    assert len(uso) == 3 and len({(l["hora_id"], l["rota"], l["automatico"]) for l in uso}) == 3
    assert {l["pedidos_qtd"] for l in uso if l["hora_id"] == int(H10) and l["rota"] == "/os/historico"} == {12}
    total = api.linhas(LIVRO_OUT, ABA_TOT)
    assert len(total) == 1 and total[0]["pedidos_qtd"] == 9                      # o total foi trocado, não repetido


def test_o_livro_sai_em_ordem_em_qualquer_maquina(api):
    _gravar(api, [_uso(H11, "/os/z"), _uso(H10, "/os/b", automatico=1), _uso(H10, "/os/a")], [_total(H11), _total(H10)])
    _gravar(api, [_uso(H12, "/os/c")], [_total(H12)])
    ordem = [(_int(l["hora_id"]), l["rota"], _int(l["automatico"])) for l in api.linhas(LIVRO_OUT, ABA_USO)]
    assert ordem == sorted(ordem) and len(ordem) == 4        # a mesma ordem em qualquer máquina
    horas = [_int(l["hora_id"]) for l in api.linhas(LIVRO_OUT, ABA_TOT)]
    assert horas == sorted(horas) == [2026103010, 2026103011, 2026103012]


@pytest.mark.parametrize("hora_a, hora_b, livro_a, livro_b", [
    ("2026103123", "2026110100", "nexus_oscreator_uso_2026_10", "nexus_oscreator_uso_2026_11"),     # virada do mês
    ("2026123123", "2027010100", "nexus_oscreator_uso_2026_12", "nexus_oscreator_uso_2027_01")])    # virada do ano
def test_virada_do_mes_vai_a_dois_livros(api, hora_a, hora_b, livro_a, livro_b):
    lote = ([_uso(hora_a), _uso(hora_b), _uso(hora_b, "/os/os/<n>")],
            [_total(hora_a), _total(hora_b), _fra(hora_a), _fra(hora_b)])
    rel = _gravar(api, *lote)
    assert set(api.workbooks) == {livro_a, livro_b} and set(rel["gravado"]) == {livro_a, livro_b}
    assert [_int(l["hora_id"]) for l in api.linhas(livro_a, ABA_USO)] == [int(hora_a)]
    assert sorted(_int(l["hora_id"]) for l in api.linhas(livro_b, ABA_USO)) == [int(hora_b)] * 2
    assert [_int(l["hora_id"]) for l in api.linhas(livro_b, ABA_FRA)] == [int(hora_b)]
    assert [_int(l["hora_id"]) for l in api.linhas(livro_a, ABA_TOT)] == [int(hora_a)]
    assert [_int(l["hora_id"]) for l in api.linhas(livro_b, ABA_TOT)] == [int(hora_b)]
    assert F.livro_do_mes(hora_a) == livro_a and F.livro_do_mes(hora_b) == livro_b
    # o lote regravado não duplica em nenhum dos dois, e o mês de antes não ganha a linha do mês de depois
    _gravar(api, *lote)
    assert len(api.linhas(livro_a, ABA_USO)) == 1 and len(api.linhas(livro_b, ABA_USO)) == 2
    assert len(api.linhas(livro_a, ABA_TOT)) == 1 and len(api.linhas(livro_b, ABA_TOT)) == 1


def test_hora_so_de_uma_das_abas_nao_apaga_as_outras(api):
    """Gravar um livro troca o livro inteiro: a aba que o lote não traz tem de seguir como estava."""
    _gravar(api, [_uso(H10)], [_total(H10), _fra(H10)])
    _gravar(api, [], [_total(H11)])
    _gravar(api, [_uso(H12)], [])
    _gravar(api, [], [_fra(H12, "/os/b", "get_assets")])
    assert len(api.linhas(LIVRO_OUT, ABA_USO)) == 2 and len(api.linhas(LIVRO_OUT, ABA_TOT)) == 2
    assert len(api.linhas(LIVRO_OUT, ABA_FRA)) == 2


def test_sem_linhas_nao_toca_no_banco(api):
    assert _gravar(api, [], []) == {"gravado": {}, "uso_qtd": 0, "fracttal_qtd": 0, "total_qtd": 0}
    assert not api.workbooks and api.syncs == 0 and not api.tokens


def test_falha_na_conferencia_depois_de_gravar_sobe_e_a_regravacao_conserta():
    """O banco que perdeu uma linha na gravação: `livros.publicar` acusa, e a gravação seguinte, relendo o livro, completa."""
    ruim = ApiPGFalsa(perder=1)
    with pytest.raises(livros.GravacaoErro):
        _gravar(ruim, [_uso(H10), _uso(H10, "/os/b"), _uso(H10, "/os/c")], [])
    assert len(ruim.linhas(LIVRO_OUT, ABA_USO)) == 2                    # chegou uma a menos
    ruim.perder = 0
    _gravar(ruim, [_uso(H10), _uso(H10, "/os/b"), _uso(H10, "/os/c")], [])
    assert len(ruim.linhas(LIVRO_OUT, ABA_USO)) == 3


def test_leitura_curta_do_livro_nao_grava_por_cima():
    """Página que volta sem a última linha daria um livro menor; a gravação de UMA linha o levaria de volta ao tamanho que
    a trava `so_cresce` aceita, apagando as últimas (a mesma lição do livro do inventário, 26/10/2026)."""
    api = ApiComLeituraCurta()
    _gravar(api, [_uso(H10), _uso(H10, "/os/b"), _uso(H10, "/os/c")], [_total(H10)])
    syncs, linhas = api.syncs, api.linhas(LIVRO_OUT, ABA_USO)
    api.curta = True
    with pytest.raises(F.LeituraIncompleta):
        _gravar(api, [_uso(H11), _uso(H11, "/os/b"), _uso(H11, "/os/c"), _uso(H11, "/os/d")], [])
    assert api.syncs == syncs and api.linhas(LIVRO_OUT, ABA_USO) == linhas


# ── a leitura dos 7 dias: só o uso e o total (o detalhe do Fracttal é a aba grande e a tela não o usa) ─────────────────
def test_ler_dias_le_so_o_uso_e_o_total_e_junta_os_dois_meses(monkeypatch):
    api = ApiPGFalsa()
    _gravar(api, [_uso("2026102010", "/os/antiga"), _uso("2026102912"), _uso("2026103123", "/os/c")],
            [_total("2026102010"), _total("2026102912", pedidos_qtd=7), _total("2026103123"), _fra("2026102912")])
    _gravar(api, [_uso("2026110100", "/os/d"), _uso("2026110203", "/os/e")], [_total("2026110100", pico_minuto_qtd=9)])
    lidas = []
    pega = api.get

    def anota(url, params=None, headers=None, timeout=None):
        m = re.search(r"/api/sheets/(\d+)/rows$", url)
        if m:
            lidas.append(next(k for k, v in api.abas.items() if v["id"] == int(m.group(1))))
        return pega(url, params=params, headers=headers, timeout=timeout)
    monkeypatch.setattr(api, "get", anota)
    dados = F.ler_dias(BASE, api, "2026110203", dias=7)                  # 27/10 a 02/11: toca os dois livros
    assert set(dados) == {"uso", "total"} and "fracttal" not in dados
    assert sorted((_int(l["hora_id"]), l["rota"]) for l in dados["uso"]) == [
        (2026102912, "/os/historico"), (2026103123, "/os/c"), (2026110100, "/os/d"), (2026110203, "/os/e")]
    assert sorted(_int(l["hora_id"]) for l in dados["total"]) == [2026102912, 2026103123, 2026110100]   # o de 20/10 fica fora
    assert {aba for _, aba in lidas} == {ABA_USO, ABA_TOT} and {livro for livro, _ in lidas} == {LIVRO_OUT, LIVRO_NOV}
    tudo = F.ler_dias(BASE, api, "2026110203", dias=7, abas=F.ABAS)       # a pedido, as três
    assert set(tudo) == {"uso", "fracttal", "total"} and len(tudo["fracttal"]) == 1


# ── nada pessoal no banco ────────────────────────────────────────────────────────────────────────────────────────────
def test_nada_pessoal_nas_colunas(api):
    proibidas = ("nome", "email", "mail", "setor", "pessoa", "usuario", "login", "hmac", "cpf", "telefone", "token", "senha")
    for cab in (F.CAB_USO, F.CAB_FRACTTAL, F.CAB_FRACTTAL_TOTAL):
        # só a contagem de pessoas distintas (`pessoas_qtd`) é permitida: nunca quem
        assert [c for c in cab if any(p in c for p in proibidas) and c != "pessoas_qtd"] == [], cab
    assert F.CAB_USO == ["hora_id", "data_id", "hora", "rota", "automatico", "pedidos_qtd", "pessoas_qtd",
                         "duracao_p50_ms", "duracao_p95_ms", "erros_qtd", "ocupado_qtd", "fracttal_qtd"]
    assert F.CAB_FRACTTAL == ["hora_id", "data_id", "hora", "origem", "metodo", "pedidos_qtd", "recusas_qtd", "erros_qtd",
                              "pico_minuto_qtd", "esperas_qtd"]
    assert F.CAB_FRACTTAL_TOTAL == ["hora_id", "data_id", "hora", "pedidos_qtd", "recusas_qtd", "erros_qtd",
                                    "pico_minuto_qtd", "esperas_qtd"]
    # a coluna que o lote traz a mais (um setor, uma pessoa) não vai ao banco: o livro só tem as colunas do contrato
    _gravar(api, [dict(_uso(H10), setor="Setor Fictício", pessoa="alguem@exemplo.invalid")],
            [dict(_fra(H10), quem="x"), dict(_total(H10), quem="y")])
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
    assert F.LIVRO_MOLDE == "nexus_oscreator_uso_AAAA_MM" and lv.abas == (ABA_USO, ABA_FRA, ABA_TOT)
    assert lv.so_cresce == lv.abas and lv.no_banco is False        # as três abas só crescem; registrado antes de existir
    assert "uso_os.py" in lv.quem_grava and "servidor" in lv.cadencia + lv.observacao
    assert "04:45" in lv.cadencia and "disco" in lv.cadencia         # no disco de hora em hora, no banco uma vez por dia
    # a família: o livro de cada mês casa pelo padrão, acha a trava do molde e a aba é da família (o radar não a acha "nova")
    assert any(p.match("nexus_oscreator_uso_2026_10") for p in catalogo.FAMILIAS)
    assert not any(p.match(n) for p in catalogo.FAMILIAS for n in
                   ("nexus_oscreator_uso_2026_1", "nexus_oscreator_uso", "nexus_oscreator_uso_2026_10_x", "x_nexus_oscreator_uso_2026_10"))
    assert livros._do_catalogo("nexus_oscreator_uso_2026_10") is lv and livros._so_cresce("nexus_oscreator_uso_2026_10") == lv.abas
    assert all(catalogo.da_familia("nexus_oscreator_uso_2027_01", aba) for aba in F.ABAS)
    assert not catalogo.da_familia("nexus_oscreator_uso_2026_10", "outra")
    for fid, aba, cab, chave in (("uso_os_hora", F.ABA_USO, F.CAB_USO, F.CHAVE_USO),
                                 ("fracttal_hora", F.ABA_FRACTTAL, F.CAB_FRACTTAL, F.CHAVE_FRACTTAL),
                                 ("fracttal_total_hora", F.ABA_TOTAL, F.CAB_FRACTTAL_TOTAL, F.CHAVE_TOTAL)):
        f = catalogo.POR_ID[fid]
        assert f.livro == f.conformado_em == f"{F.LIVRO_MOLDE} · {aba}" and f.fontes == (f.livro,) and f.estado == "conformado"
        assert f.tipo == "snapshot_periodico" and f.chave == chave and f.area == "os" and f.grao.startswith("1 linha")
        assert f.dims["data"][0] == "id" and all(f.dims[d][0] == "nao" for d in catalogo.DIM_IDS if d != "data")
        assert f.medidas and all(m.coluna in cab and catalogo.medida_valida(m) for m in f.medidas)
        assert "o Nexus é a fonte" in f.janela_origem and "04:45" in f.janela_origem
        assert fid in explica.RESUMO and fid in explica.PARA_QUE        # a camada cobra o texto amigável
    # a soma de cada medida: a contagem de pedidos soma; pessoas distintas, tempo e o pico por minuto, nunca
    uso = {m.coluna: m for m in catalogo.POR_ID["uso_os_hora"].medidas}
    assert uso["pedidos_qtd"].soma == uso["erros_qtd"].soma == uso["ocupado_qtd"].soma == uso["fracttal_qtd"].soma == "aditiva"
    assert uso["pessoas_qtd"].soma == uso["duracao_p50_ms"].soma == uso["duracao_p95_ms"].soma == "nao"
    assert uso["duracao_p50_ms"].unidade == "ms" and catalogo.medida_valida(uso["duracao_p95_ms"])
    for fid in ("fracttal_hora", "fracttal_total_hora"):
        fra = {m.coluna: m for m in catalogo.POR_ID[fid].medidas}
        assert fra["pedidos_qtd"].soma == fra["recusas_qtd"].soma == fra["erros_qtd"].soma == "aditiva", fid
        assert fra["pico_minuto_qtd"].soma == "nao", fid
        # as esperas no porteiro (etapa 5) são pedidos contados: somam, e o catálogo diz o que são
        assert fra["esperas_qtd"].soma == "aditiva" and fra["esperas_qtd"].unidade == "qtd", fid
        assert "porteiro" in catalogo.POR_ID[fid].observacao, fid
    # Ruling N: o total não mora no detalhe. O grão do detalhe não o cita, e o do total é 1 linha por hora
    assert "origem * e método *" not in catalogo.POR_ID["fracttal_hora"].grao
    assert catalogo.POR_ID["fracttal_total_hora"].grao.startswith("1 linha = 1 hora")
    assert "fracttal_total_hora" in catalogo.POR_ID["fracttal_hora"].observacao
    assert "04:45" in catalogo.POR_ID["uso_os_hora"].observacao


# ── o laço: de hora em hora para o disco, às 04:45 para o banco ──────────────────────────────────────────────────────
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
    # o porteiro do Fracttal mora no mesmo gancho (etapa 5): a espera dele anda este relógio em vez de dormir, e o teste que
    # passa de 90 de fundo no mesmo minuto termina, em vez de esperar para sempre o relógio parado
    monkeypatch.setattr(C, "_cronometro", r.cronometro)
    monkeypatch.setattr(C, "_esperar", lambda cond, segundos: r.passa(segundos))
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


def _app(tmp_path, **extra):
    app = Flask(__name__)
    app.config.update(SECRET_KEY="chave-de-teste", TESTING=True, NEXUS_DADOS=str(tmp_path), NEXUS_PESSOA_HMAC=_CHAVE_PESSOA,
                      GRIDCO_SQL_TOKEN=TOKEN, GRIDCO_DB_API=BASE)
    app.config.update(extra)
    return app


@pytest.fixture
def mini(tmp_path, relogio, setor):
    """Um Flask de mentira com duas telas do OS Creator (uma pede ao Fracttal), o uso ligado como no servidor."""
    app = _app(tmp_path)
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


def _arquivo_pendente(tmp_path):
    return tmp_path / "casca" / "uso_os_pendente.json"


def _pendente_em_disco(tmp_path):
    return json.loads(_arquivo_pendente(tmp_path).read_text(encoding="utf-8"))


def _um_dia_de_uso(app, relogio):
    """O dia 30/10 como o laço o vê: um clique que vai ao Fracttal às 10h, outro às 11h, e o das 01h de 31/10; cada hora é
    tirada dos contadores no :05 seguinte (de hora em hora, para o disco). Termina às 02:05 de 31/10."""
    _clica(app, "/os/os/1", "2026-10-30T13:10:00+00:00", relogio)                # 10:10
    relogio.em("2026-10-30T14:05:00+00:00")
    U.drenar_para_o_disco()                                                      # 11:05
    _clica(app, "/os/historico", "2026-10-30T14:30:00+00:00", relogio)           # 11:30
    relogio.em("2026-10-30T15:05:00+00:00")
    U.drenar_para_o_disco()                                                      # 12:05
    _clica(app, "/os/os/2", "2026-10-31T04:10:00+00:00", relogio)                # 01:10 de 31/10
    relogio.em("2026-10-31T05:05:00+00:00")
    U.drenar_para_o_disco()                                                      # 02:05


@pytest.mark.parametrize("utc, esperado, passo", [
    ("2026-10-30T13:00:00+00:00", 300, "drenar"),       # 10:00 BRT: o :05 vem em 5 min
    ("2026-10-30T13:04:59+00:00", 1, "drenar"),
    ("2026-10-30T13:05:00+00:00", 3600, "drenar"),      # já é :05: o seguinte é o da hora seguinte
    ("2026-10-30T23:59:00+00:00", 360, "drenar"),
    ("2026-10-30T02:30:00+00:00", 2100, "drenar"),      # 23:30 BRT de 29/10: o 04:45 ainda está longe
    ("2026-10-30T06:00:00+00:00", 300, "drenar"),       # 03:00 BRT: o :05 vem antes do 04:45
    ("2026-10-30T06:05:00+00:00", 3600, "drenar"),      # 03:05 BRT: o :05 de 04:00 vem antes do 04:45 (até 31/10 a gravação era às 03:45)
    ("2026-10-30T06:44:00+00:00", 1260, "drenar"),
    ("2026-10-30T07:05:00+00:00", 2400, "gravar"),      # 04:05 BRT: o 04:45 vem antes do :05 de 05:00
    ("2026-10-30T07:30:00+00:00", 900, "gravar"),
    ("2026-10-30T07:44:00+00:00", 60, "gravar"),
    ("2026-10-30T07:45:00+00:00", 1200, "drenar"),      # 04:45 em ponto: já passou, a próxima gravação é amanhã
    ("2026-10-30T07:46:00+00:00", 1140, "drenar"),
    ("2026-10-30T05:59:59+00:00", 301, "drenar")])
def test_o_laco_acorda_no_5_de_toda_hora_e_grava_as_4h45(utc, esperado, passo):
    espera, quem = U.proximo_passo(datetime.fromisoformat(utc).timestamp())
    assert (round(espera, 6), quem) == (esperado, passo)
    assert (U.DRENAR_NO_MINUTO, U.GRAVAR_NA_HORA, U.GRAVAR_NO_MINUTO) == (5, 4, 45)


def test_de_hora_em_hora_o_laco_guarda_no_disco_e_nunca_vai_ao_banco(mini, relogio, tmp_path, monkeypatch):
    chamou = []
    monkeypatch.setattr(F, "gravar", lambda *a, **k: chamou.append(1))
    _clica(mini, "/os/os/1", "2026-10-30T13:10:00+00:00", relogio)               # 10:10: um pedido que vai ao Fracttal
    _clica(mini, "/os/historico")
    relogio.em("2026-10-30T13:50:00+00:00")                                       # 10:50: a hora 10 ainda está aberta
    assert U.drenar_para_o_disco()["drenou"] == {"uso": 0, "fracttal": 0}
    assert not _arquivo_pendente(tmp_path).exists() and U.pendentes()["horas"] == 0
    relogio.em("2026-10-30T14:05:00+00:00")                                       # 11:05: o laço
    rel = U.drenar_para_o_disco()
    assert rel["drenou"] == {"uso": 2, "fracttal": 2} and rel["pendentes"] == {"uso": 2, "fracttal": 2, "horas": 1}
    assert not chamou                                                              # o banco nem foi chamado
    dados = _pendente_em_disco(tmp_path)
    assert dados["versao"] == 1 and {l["hora_id"] for l in dados["uso"]} == {H10} and len(dados["uso"]) == 2
    assert {(l["origem"], l["metodo"]) for l in dados["fracttal"]} == {("*", "*"), ("/os/os/<n>", "work_orders")}
    # a hora saiu da memória dos contadores e do parcial: o reinício não a traz de volta em dobro
    assert not [l for l in U.instantaneo()["linhas"] if l["hora_id"] == H10]
    assert H10 not in (tmp_path / "casca" / "uso_os_parcial.json").read_text(encoding="utf-8")
    assert U.linhas_pendentes()["uso"][0]["hora_id"] == H10


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
    U.drenar_para_o_disco()
    assert vistos == [("uso", H11), ("fracttal", H11)]


def test_as_4h45_gravam_o_que_esta_no_disco_e_o_pendente_esvazia(mini, relogio, tmp_path):
    _um_dia_de_uso(mini, relogio)
    banco = ApiPGFalsa()
    assert not banco.workbooks and U.pendentes()["horas"] == 3                    # as 10h, as 11h e a 01h, só no disco
    relogio.em("2026-10-31T07:45:00+00:00")                                       # 04:45 de 31/10
    rel = U.gravar_no_banco(mini.config, sessao=banco)
    # as 11h só tiveram um clique que não pediu nada ao Fracttal: o detalhe e o total têm a hora 10 e a 01 de 31/10
    assert rel["gravado"] == {LIVRO_OUT: {ABA_USO: 3, ABA_FRA: 2, ABA_TOT: 2}}
    assert sorted((_int(l["hora_id"]), l["rota"]) for l in banco.linhas(LIVRO_OUT, ABA_USO)) == [
        (2026103010, "/os/os/<n>"), (2026103011, "/os/historico"), (2026103101, "/os/os/<n>")]
    assert sorted(_int(l["hora_id"]) for l in banco.linhas(LIVRO_OUT, ABA_TOT)) == [2026103010, 2026103101]
    # o que foi gravado saiu do pendente, da memória e do disco; o parcial foi regravado; a hora da gravação ficou anotada
    assert U.pendentes() == {"uso": 0, "fracttal": 0, "horas": 0}
    dados = _pendente_em_disco(tmp_path)
    assert dados["uso"] == [] and dados["fracttal"] == []
    assert U.gravou_em() == relogio.agora()
    # a gravação não faz nada de novo sem hora nova
    syncs = banco.syncs
    assert U.gravar_no_banco(mini.config, sessao=banco).get("pulou") and banco.syncs == syncs


def test_a_virada_do_mes_no_pendente_grava_os_dois_livros_as_4h45(mini, relogio, tmp_path):
    _clica(mini, "/os/os/1", "2026-11-01T02:10:00+00:00", relogio)                # 31/10 23:10 de Brasília
    relogio.em("2026-11-01T03:05:00+00:00")
    U.drenar_para_o_disco()                                                       # 00:05 de 01/11
    _clica(mini, "/os/historico", "2026-11-01T03:10:00+00:00", relogio)           # 01/11 00:10
    relogio.em("2026-11-01T04:05:00+00:00")
    U.drenar_para_o_disco()                                                       # 01:05
    horas = {l["hora_id"] for l in _pendente_em_disco(tmp_path)["uso"]}
    assert horas == {"2026103123", "2026110100"}                                  # o pendente atravessa a virada do mês
    banco = ApiPGFalsa()
    relogio.em("2026-11-01T07:45:00+00:00")                                       # 04:45 de 01/11
    rel = U.gravar_no_banco(mini.config, sessao=banco)
    assert set(rel["gravado"]) == {LIVRO_OUT, LIVRO_NOV}                          # o mês que fechou ganha as últimas horas
    assert [_int(l["hora_id"]) for l in banco.linhas(LIVRO_OUT, ABA_USO)] == [2026103123]
    assert [_int(l["hora_id"]) for l in banco.linhas(LIVRO_NOV, ABA_USO)] == [2026110100]
    assert [_int(l["hora_id"]) for l in banco.linhas(LIVRO_OUT, ABA_TOT)] == [2026103123]
    assert U.pendentes()["horas"] == 0


def test_o_banco_fora_as_4h45_deixa_tudo_no_disco_e_a_gravacao_do_dia_seguinte_leva(mini, relogio, tmp_path):
    _um_dia_de_uso(mini, relogio)
    relogio.em("2026-10-31T07:45:00+00:00")
    caiu = ApiQueFalha(cai=1)
    rel = U.gravar_no_banco(mini.config, sessao=caiu)
    assert "erro" in rel and not caiu.workbooks and rel["pendentes"]["horas"] == 3
    assert len(_pendente_em_disco(tmp_path)["uso"]) == 3 and U.gravou_em() == 0   # nada saiu, e ninguém anota gravação que não houve
    # o dia seguinte: mais uma hora no disco (a das 10h de 31/10) e, às 04:45 de 01/11, o banco volta
    _clica(mini, "/os/historico", "2026-10-31T13:10:00+00:00", relogio)
    relogio.em("2026-10-31T14:05:00+00:00")
    U.drenar_para_o_disco()
    banco = ApiPGFalsa()
    relogio.em("2026-11-01T07:45:00+00:00")
    rel = U.gravar_no_banco(mini.config, sessao=banco)
    assert "erro" not in rel and len(banco.linhas(LIVRO_OUT, ABA_USO)) == 4
    assert U.pendentes() == {"uso": 0, "fracttal": 0, "horas": 0}


def test_a_leitura_curta_do_livro_nas_4h45_nao_grava_e_o_pendente_fica(mini, relogio, tmp_path):
    _clica(mini, "/os/historico", "2026-10-30T13:10:00+00:00", relogio)
    relogio.em("2026-10-30T14:05:00+00:00")
    U.drenar_para_o_disco()
    banco = ApiComLeituraCurta()
    relogio.em("2026-10-31T07:45:00+00:00")
    U.gravar_no_banco(mini.config, sessao=banco)                                 # cria o livro com a hora 10
    _clica(mini, "/os/historico", "2026-10-31T13:30:00+00:00", relogio)
    relogio.em("2026-10-31T15:05:00+00:00")
    U.drenar_para_o_disco()
    banco.curta = True
    relogio.em("2026-11-01T07:45:00+00:00")
    rel = U.gravar_no_banco(mini.config, sessao=banco)                           # a leitura curta recusa
    assert "erro" in rel and U.pendentes()["uso"] == 1 and len(banco.linhas(LIVRO_OUT, ABA_USO)) == 1
    assert len(_pendente_em_disco(tmp_path)["uso"]) == 1
    banco.curta = False
    relogio.em("2026-11-02T07:45:00+00:00")
    U.gravar_no_banco(mini.config, sessao=banco)
    assert len(banco.linhas(LIVRO_OUT, ABA_USO)) == 2 and U.pendentes()["uso"] == 0


def test_sem_o_token_nao_grava_e_o_pendente_fica_no_disco(mini, relogio, tmp_path):
    _clica(mini, "/os/historico", "2026-10-30T13:10:00+00:00", relogio)
    relogio.em("2026-10-31T07:45:00+00:00")
    banco = ApiPGFalsa()
    rel = U.gravar_no_banco(dict(mini.config, GRIDCO_SQL_TOKEN=""), sessao=banco)
    assert "GRIDCO_SQL_TOKEN" in rel["erro"] and not banco.workbooks and banco.syncs == 0
    assert U.pendentes()["uso"] == 1 and len(_pendente_em_disco(tmp_path)["uso"]) == 1   # guardada para quando houver chave


def test_em_teste_sem_sessao_nunca_vai_a_rede_nem_tira_dos_contadores(mini, relogio, monkeypatch):
    def sem_rede(*a, **k):
        raise AssertionError("o teste foi à rede")
    monkeypatch.setattr(requests, "Session", sem_rede)
    _clica(mini, "/os/historico", "2026-10-30T13:10:00+00:00", relogio)
    relogio.em("2026-10-31T07:45:00+00:00")
    assert "teste" in U.gravar_no_banco(mini.config)["pulou"]
    assert [l["hora_id"] for l in U.instantaneo()["linhas"]] == [H10] and U.pendentes()["horas"] == 0


def test_o_pendente_sobrevive_ao_reinicio_e_o_parcial_nao_traz_a_hora_de_volta(mini, relogio, tmp_path):
    _clica(mini, "/os/os/1", "2026-10-30T13:10:00+00:00", relogio)
    U.salvar()                                                                    # o laço de 5 min já guardou a hora 10
    assert H10 in (tmp_path / "casca" / "uso_os_parcial.json").read_text(encoding="utf-8")
    relogio.em("2026-10-30T14:05:00+00:00")
    U.drenar_para_o_disco()
    antes = U.linhas_pendentes()
    assert H10 not in (tmp_path / "casca" / "uso_os_parcial.json").read_text(encoding="utf-8")
    U.limpar()                                                                    # o processo morre: a memória some
    assert U.pendentes()["horas"] == 0
    app2 = _app(tmp_path)
    U.ligar(app2, gravar=True)                                                    # o "reinício": lê o parcial e o pendente
    assert not [l for l in U.instantaneo()["linhas"] if l["hora_id"] == H10]      # a hora não volta aos contadores
    assert U.linhas_pendentes() == antes and U.pendentes() == {"uso": 1, "fracttal": 2, "horas": 1}
    banco = ApiPGFalsa()
    relogio.em("2026-10-31T07:45:00+00:00")
    rel = U.gravar_no_banco(app2.config, sessao=banco)                            # e as 04:45 levam o que veio do disco
    assert rel["gravado"][LIVRO_OUT][ABA_USO] == 1 and rel["gravado"][LIVRO_OUT][ABA_TOT] == 1


def test_a_hora_que_o_parcial_antigo_traz_de_volta_nao_repete_a_chave_do_pendente(mini, relogio, tmp_path):
    """A janela do desastre: o pendente foi ao disco e o processo morreu ANTES do parcial ser regravado. No boot a hora volta
    aos contadores (pelo parcial velho) e já está no pendente: a mesma chave não pode ir duas vezes ao banco (o grão
    quebraria e ninguém mais gravaria)."""
    _clica(mini, "/os/os/1", "2026-10-30T13:10:00+00:00", relogio)
    U.salvar()
    parcial_velho = (tmp_path / "casca" / "uso_os_parcial.json").read_text(encoding="utf-8")
    relogio.em("2026-10-30T14:05:00+00:00")
    U.drenar_para_o_disco()
    (tmp_path / "casca" / "uso_os_parcial.json").write_text(parcial_velho, encoding="utf-8")     # o parcial que sobrou
    U.limpar()
    app2 = _app(tmp_path)
    U.ligar(app2, gravar=True)
    assert [l["hora_id"] for l in U.instantaneo()["linhas"]] == [H10]             # voltou aos contadores...
    relogio.em("2026-10-30T14:06:00+00:00")
    U.drenar_para_o_disco()                                                       # ...e sai de novo, com a mesma chave
    assert U.pendentes() == {"uso": 1, "fracttal": 2, "horas": 1}                 # a chave repetida ficou uma só
    assert len({(l["hora_id"], l["rota"], l["automatico"]) for l in U.linhas_pendentes()["uso"]}) == 1
    banco = ApiPGFalsa()
    relogio.em("2026-10-31T07:45:00+00:00")
    assert "erro" not in U.gravar_no_banco(app2.config, sessao=banco)
    assert len(banco.linhas(LIVRO_OUT, ABA_USO)) == 1


@pytest.mark.parametrize("conteudo", [
    "{isto não é json", "[1, 2, 3]", '"texto solto"', '{"versao": 1}', '{"uso": "x", "fracttal": 5}', "", "\x00\x00\x00"])
def test_pendente_quebrado_e_ignorado_e_o_nexus_sobe(mini, relogio, tmp_path, caplog, conteudo):
    _arquivo_pendente(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    _arquivo_pendente(tmp_path).write_text(conteudo, encoding="utf-8")
    U.limpar()
    with caplog.at_level(logging.WARNING):
        U.ligar(_app(tmp_path), gravar=True)                                      # não levanta
    assert U.pendentes() == {"uso": 0, "fracttal": 0, "horas": 0}
    assert "Uso do OS Creator" in caplog.text                                     # e diz no log que ignorou o arquivo
    # o próximo tirar de hora em hora o conserta
    _clica(mini, "/os/historico", "2026-10-30T13:10:00+00:00", relogio)
    relogio.em("2026-10-30T14:05:00+00:00")
    U.drenar_para_o_disco()
    assert len(_pendente_em_disco(tmp_path)["uso"]) == 1


def test_pendente_com_uma_linha_ruim_aproveita_as_boas(mini, relogio, tmp_path, caplog):
    boa = _uso(H10)
    _arquivo_pendente(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    _arquivo_pendente(tmp_path).write_text(json.dumps({"versao": 1, "uso": [boa, dict(_uso(H11), automatico=7), "lixo", {}],
                                                       "fracttal": [_fra(H10, "*", "x"), _total(H10), dict(_fra(H11), pedidos_qtd=-1)]}),
                                           encoding="utf-8")
    U.limpar()
    with caplog.at_level(logging.WARNING):
        U.ligar(_app(tmp_path), gravar=True)
    assert U.linhas_pendentes() == {"uso": [boa], "fracttal": [_total(H10)]}
    assert "5 linha(s) ruim(ns)" in caplog.text                                   # as 5 linhas ruins vão ao log, contadas


def test_o_pendente_tem_teto_de_3_dias(mini, relogio, tmp_path, caplog):
    """O banco fora por dias não enche o disco nem a memória: ficam as 72 horas mais novas (3 dias), e o aviso vai ao log."""
    relogio.em("2026-10-30T13:10:00+00:00")                                       # 10:10
    with caplog.at_level(logging.WARNING):
        for _ in range(75):                          # uma hora nova a cada passo, nenhuma gravada
            _clica(mini, "/os/os/1")
            relogio.passa(3600)
            U.drenar_para_o_disco()
    assert U.pendentes()["horas"] == 72 == U.MAX_HORAS_PENDENTES
    assert "descartei" in caplog.text
    horas = sorted({l["hora_id"] for l in U.linhas_pendentes()["uso"]})
    assert len(horas) == 72 and horas[0] == "2026103013" and horas[-1] == "2026110212"      # as 72 mais novas
    assert sorted({l["hora_id"] for l in _pendente_em_disco(tmp_path)["uso"]}) == horas        # o disco diz o mesmo
    banco = ApiPGFalsa()
    relogio.em("2026-11-03T07:45:00+00:00")                                       # o 04:45 seguinte à última hora tirada
    U.gravar_no_banco(mini.config, sessao=banco)
    gravadas = {_int(l["hora_id"]) for livro in (LIVRO_OUT, LIVRO_NOV) for l in banco.linhas(livro, ABA_USO)}
    assert len(gravadas) == 72 and U.pendentes()["horas"] == 0 and len(banco.workbooks) == 2


def test_disco_que_falha_nao_derruba_e_a_memoria_segue_com_as_linhas(mini, relogio, tmp_path, monkeypatch, caplog):
    _clica(mini, "/os/historico", "2026-10-30T13:10:00+00:00", relogio)
    relogio.em("2026-10-30T14:05:00+00:00")

    def nao_troca(*a, **k):
        raise OSError("disco cheio")
    with monkeypatch.context() as m, caplog.at_level(logging.WARNING):
        m.setattr(U.os, "replace", nao_troca)
        rel = U.drenar_para_o_disco()                                             # o arquivo não saiu, e o laço segue
    assert "disco cheio" in caplog.text and rel["pendentes"]["uso"] == 1
    assert not _arquivo_pendente(tmp_path).exists()
    assert U.linhas_pendentes()["uso"][0]["hora_id"] == H10                       # a memória guarda: o Raio-X ainda a mostra
    _clica(mini, "/os/historico", "2026-10-30T14:30:00+00:00", relogio)
    relogio.em("2026-10-30T15:05:00+00:00")
    U.drenar_para_o_disco()                                                       # o disco voltou: tudo vai junto
    assert len(_pendente_em_disco(tmp_path)["uso"]) == 2


def test_o_laco_so_liga_no_servidor(tmp_path, relogio, monkeypatch):
    gravacao, cinco_min = threading.Event(), threading.Event()
    monkeypatch.setattr(U, "_laco_gravacao", lambda: gravacao.set())
    monkeypatch.setattr(U, "_laco", cinco_min.set)
    U.ligar(_app(tmp_path, TESTING=True), gravar=True)                            # teste: nenhum dos dois
    assert not gravacao.wait(0.3) and not cinco_min.wait(0.1)
    U.limpar()
    U.ligar(_app(tmp_path, TESTING=False), gravar=False)                          # o PC: só o de 5 min, a gravação não
    assert cinco_min.wait(3) and not gravacao.wait(0.3)
    U.limpar()
    U.ligar(_app(tmp_path, TESTING=False), gravar=True)                           # o servidor: os dois
    assert gravacao.wait(3)
    assert U.MAX_HORAS_PENDENTES == 72


# ── a ponta a ponta, com os contadores de verdade ────────────────────────────────────────────────────────────────────
def test_ponta_a_ponta_grava_as_4h45_o_que_o_disco_guardou_e_nada_pessoal_vai_ao_banco(mini, relogio, tmp_path):
    relogio.em("2026-10-30T13:10:00+00:00")                                       # 10:10
    _clica(mini, "/os/os/16995")
    _clica(mini, "/os/os/16996")
    _clica(mini, "/os/historico")
    relogio.em("2026-10-30T14:02:00+00:00")                                       # 11:02: já é a hora seguinte, a aberta
    _clica(mini, "/os/historico")
    relogio.em("2026-10-30T14:05:00+00:00")                                       # 11:05: o laço tira a hora 10, para o disco
    U.drenar_para_o_disco()
    assert [l["hora_id"] for l in U.instantaneo()["linhas"]] == [H11]             # a hora aberta fica nos contadores
    banco = ApiPGFalsa()
    relogio.em("2026-10-31T07:45:00+00:00")                                       # 04:45 do dia seguinte
    rel = U.gravar_no_banco(mini.config, sessao=banco)
    # a hora 11 ficou aberta até o :05 que o laço tiraria; a gravação de 04:45 também tira o que fechou desde então
    assert rel["gravado"][LIVRO_OUT][ABA_USO] == 3 and rel["uso_qtd"] == 3
    uso = {(l["hora_id"], l["rota"]): l for l in banco.linhas(LIVRO_OUT, ABA_USO)}
    assert set(uso) == {(2026103010, "/os/os/<n>"), (2026103010, "/os/historico"), (2026103011, "/os/historico")}
    assert uso[(2026103010, "/os/os/<n>")]["pedidos_qtd"] == 2 and uso[(2026103010, "/os/os/<n>")]["pessoas_qtd"] == 1
    assert uso[(2026103010, "/os/os/<n>")]["fracttal_qtd"] == 2
    total = {l["hora_id"]: l for l in banco.linhas(LIVRO_OUT, ABA_TOT)}
    assert total[2026103010]["pedidos_qtd"] == 2 and total[2026103010]["pico_minuto_qtd"] == 2
    assert all(l["origem"] != "*" for l in banco.linhas(LIVRO_OUT, ABA_FRA))      # o detalhe não tem a linha de total
    # o setor, o e-mail e o código da pessoa não estão em lugar nenhum do banco (tabelas, cabeçalhos, livros)
    from nexus.campo.ligacao_cadastro import codigo_da_pessoa
    tudo = repr(banco.abas) + repr(banco.workbooks)
    for proibido in (_SETOR, _EMAIL, "exemplo.invalid", codigo_da_pessoa(_CHAVE_PESSOA, _EMAIL), "Setor"):
        assert proibido not in tudo, proibido
    # nem no pendente em disco (só contagens), mas o corte por setor existe no disco do servidor, para o Raio-X
    assert _SETOR not in _arquivo_pendente(tmp_path).read_text(encoding="utf-8")
    assert _SETOR in U.instantaneo()["setor"]["20261030"]


# ── o relógio deste arquivo e o porteiro do Fracttal (etapa 5) ───────────────────────────────────────────────────────
def test_o_relogio_deste_arquivo_nao_trava_o_porteiro(relogio):
    # o gancho do Fracttal está ligado aqui, e o porteiro mora nele: com o relógio parado e a espera de verdade, o 91º de
    # fundo no mesmo minuto esperaria para sempre. A espera deste relógio anda o relógio: o teste termina
    fracttal, _ = sessao_real(*[(200, None)] * 91)
    with C.origem("fundo:laco"):
        for _ in range(91):
            fracttal.get("https://app.fracttal.com/api/work_orders")
    linha = next(lin for lin in C.instantaneo() if lin["origem"] == "fundo:laco")
    assert (linha["pedidos_qtd"], linha["esperas_qtd"]) == (91, 1)

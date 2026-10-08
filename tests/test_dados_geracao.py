"""Geração em linhas (passo 6c do Kimball, 08/10/2026): o formato largo do `bd_thopen` e do `bd_performance` (uma aba
por usina, um inversor por coluna) vira `fato_geracao_usina_dia` e `fato_geracao_inversor_dia`, com a usina SÓ pelo
de-para publicado (sistemas `BD_Thopen · aba` e `BD_Performance · aba`). Nomes e códigos aqui são inventados."""
import hashlib
import json
import sys
from datetime import date

import pytest
from pg_falso import ApiPGFalsa

from nexus.cadastro import banco as B
from nexus.cadastro import ligacoes as L
from nexus.dados import fatos, geracao as G
from nexus.dados import livros

HOJE = date(2026, 10, 8)
TH, PF = G.SISTEMA_ABA["bd_thopen"], G.SISTEMA_ABA["bd_performance"]


def _linha(dia, **kw):
    d = {"Usina": "Usina Exemplo 1", "Data": dia, "IPOA (kWh/m²)": 6.1, "GHI (kWh/m²)": 5.2, "Chuva (mm)": 0,
         "Energia Produzida (kWh)": 3000.5, "Disponibilidade Usina (%)": 1, "Inversor 1.1": 1000.0,
         "Inversor 1.2": "#N/A", "inversor 2.1": "962,800", "SKID 1 (kWh)": 2000, "Validação": 1,
         "Comentário": "texto livre com nome"}
    d.update(kw)
    return d


def _aba_thopen():
    return [_linha("2026-10-06"), _linha("2026-10-07", **{"Inversor 1.1": -5, "inversor 2.1": 39063388.18}),
            _linha("2026-10-09", **{"Inversor 1.1": 999.0}),           # futuro: pré-criada e até preenchida
            _linha("", **{"Inversor 1.1": 7.0})]                       # sem data


def _de(usina_id, sistema, chave, como):
    return {"usina_id": usina_id, "sistema": sistema, "chave_externa": chave, "casou_por": como}


def _col(cab, linha, c):
    return linha[cab.index(c)]


# ── leitura das células ─────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("bruto, esperado", [
    (12, 12.0), (3.5, 3.5), ("962,800", 962.8), ("1.234,5", 1234.5), ("853.1", 853.1), ("-83,6", -83.6),
    (" 7 ", 7.0), ("#N/A", None), ("Valores Zerado", None), ("\xa0", None), ("", None), (None, None), (True, None),
    ("1.234.567", None), ("Inversor 3", None), (float("nan"), None)])
def test_numero_le_virgula_decimal_e_recusa_texto(bruto, esperado):
    assert G.numero(bruto) == esperado


def test_abas_de_geracao_so_as_largas_com_data():
    abas = {"Usina Exemplo 1": _aba_thopen(),
            "Só medidor": [{"Usina": "x", "Data": "2026-10-01", "Energia Produzida (kWh)": 10}],
            "Dados Gerais Usinas": [{"Usina": "x", "Cidade": "y", "Quantidade de Inversores": 3}],
            "Histórico longo": [{"Data": "2026-10-01", "Usina": "x", "Geração": 5}],
            "Vazia": []}
    r = {aba: cols for aba, _l, cols in G.abas_de_geracao(abas)}
    assert set(r) == {"Usina Exemplo 1", "Só medidor"}
    assert r["Usina Exemplo 1"] == ["Inversor 1.1", "Inversor 1.2", "inversor 2.1"] and r["Só medidor"] == []
    assert G.rotulo_inversor(" inversor 2.1 ") == "Inversor 2.1" and G.rotulo_inversor("Junco 1.1") is None


# ── inversor × dia ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_aba_larga_vira_uma_linha_por_inversor_com_valor():
    usina = (7, "de-para (igual a BD_Thopen · Dados Gerais Usinas)", "")
    linhas, conta = G.linhas_inversor_dia("bd_thopen", "Usina Exemplo 1", _aba_thopen(), usina, 168480.0, {}, HOJE)
    d = [dict(zip(G.CAB_INVERSOR_DIA, l)) for l in linhas]
    # 06/10: 1.1 e 2.1 (o "#N/A" do 1.2 não vira linha); 07/10: os dois fora da faixa; 09/10 (futuro) e sem data: fora
    assert [(x["data_id"], x["inversor"], x["energia_kwh"], x["kwh_fora_da_faixa"]) for x in d] == [
        (20261006, "Inversor 1.1", 1000.0, 0), (20261006, "Inversor 2.1", 962.8, 0),
        (20261007, "Inversor 1.1", None, 1), (20261007, "Inversor 2.1", None, 1)]
    assert conta["texto"] == 2 and conta["dia_futuro"] == 1 and conta["sem_data"] == 1 and conta["fora_da_faixa"] == 2
    assert {x["usina_id"] for x in d} == {7} and {x["equipamento_id"] for x in d} == {None}
    # a chave é estável: sha1(fonte|aba|inversor|dia)
    chave = "bd_thopen|Usina Exemplo 1|Inversor 1.1|2026-10-06"
    assert d[0]["geracao_id"] == hashlib.sha1(chave.encode()).hexdigest()[:16]
    assert len({x["geracao_id"] for x in d}) == len(d)


def test_sem_teto_so_o_negativo_cai_e_coluna_repetida_sai_inteira():
    aba = [{"Data": "2026-10-06", "Inversor 1.1": 5000.0, "inversor 1.1": 4.0, "Inversor 2.1": -1}]
    linhas, conta = G.linhas_inversor_dia("bd_performance", "ABC100", aba, None, None, None, HOJE)
    assert [(l[7], l[8], l[9]) for l in linhas] == [("Inversor 2.1", None, 1)]
    assert conta["coluna_repetida"] == 2                       # "Inversor 1.1" e "inversor 1.1": não há qual escolher


# ── usina × dia ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_usina_dia_medidas_agregados_e_dia_futuro():
    aba, usina = _aba_thopen(), (7, "de-para (código)", "")
    cols = ["Inversor 1.1", "Inversor 1.2", "inversor 2.1"]
    inv, _ = G.linhas_inversor_dia("bd_thopen", "U", aba, usina, 168480.0, {}, HOJE)
    linhas, conta = G.linhas_usina_dia("bd_thopen", "U", aba, usina, HOJE, cols, inv, teto=168480.0)
    d = {x["data_id"]: x for x in (dict(zip(G.CAB_USINA_DIA, l)) for l in linhas)}
    assert set(d) == {20261006, 20261007} and conta["dia_futuro"] == 1 and conta["sem_data"] == 1
    a = d[20261006]
    assert (a["energia_medidor_kwh"], a["ipoa_kwh_m2"]) == (3000.5, 6.1)
    assert (a["disponibilidade_pct"], a["validado"]) == (100.0, 1)            # a fonte grava fração: 1 = 100%
    # os agregados são a soma/contagem das linhas do inversor × dia, nunca outra conta
    assert (a["energia_inversores_kwh"], a["inversores_com_dado_qtd"], a["inversores_qtd"]) == (1962.8, 2, 3)
    assert (d[20261007]["energia_inversores_kwh"], d[20261007]["inversores_com_dado_qtd"]) == (None, 0)
    assert a["usina_id"] == 7 and a["usina_motivo"] is None and a["fonte"] == "bd_thopen"
    assert "texto livre com nome" not in json.dumps(linhas, ensure_ascii=False)        # o comentário fica fora


def test_medidor_e_clima_fora_da_faixa_ficam_vazios():
    aba = [{"Data": "2026-10-06", "Multimedidor": 6982663, "IPOA (kWh/m²)": 6.0, "IPOA (kWh/m²) DEF": 26.0,
            "GHI (kWh/m²)": -170.6, "Pluviômetro (mm)": 40209.81, "Validação": 1, "Disponibilidade Usina (%)": None},
           {"Data": "2026-10-05", "Multimedidor": "\xa0", "IPOA (kWh/m²) DEF": 5.95, "IPOA (kWh/m²)": 9.0,
            "Disponibilidade Usina (%)": "98,5%"}]
    linhas, conta = G.linhas_usina_dia("bd_performance", "ABC100", aba, None, HOJE, [], (), teto=168480.0)
    d = {x["data_id"]: x for x in (dict(zip(G.CAB_USINA_DIA, l)) for l in linhas)}
    o = d[20261006]
    assert (o["energia_medidor_kwh"], o["medidor_fora_da_faixa"]) == (None, 1)
    # IPOA é o "DEF" (escolha da COLUNA, nunca célula a célula): 26 kWh/m² num dia não existe -> vazio, sem cair no
    # IPOA simples
    assert (o["ipoa_kwh_m2"], o["ghi_kwh_m2"], o["chuva_mm"]) == (None, None, None)
    assert (d[20261005]["ipoa_kwh_m2"], d[20261005]["disponibilidade_pct"]) == (5.95, 98.5)
    assert conta["medidor_fora_da_faixa"] == 1 and conta["ipoa_kwh_m2_fora_da_faixa"] == 1
    assert o["usina_id"] is None and o["usina_motivo"] == G.MOTIVO_SEM_DE_PARA


def test_dia_repetido_divergente_sai_e_igual_vale_uma_vez():
    aba = [{"Data": "2026-10-06", "Inversor 1.1": 10}, {"Data": "2026-10-06", "Inversor 1.1": 11},
           {"Data": "2026-10-05", "Inversor 1.1": 10}, {"Data": "2026-10-05", "Inversor 1.1": 10}]
    linhas, conta = G.linhas_inversor_dia("bd_thopen", "U", aba, None, None, None, HOJE)
    assert [l[1] for l in linhas] == [20261005]
    assert conta["dia_repetido_divergente"] == 2 and conta["dia_repetido_igual"] == 1


# ── a usina da aba: só o de-para publicado ──────────────────────────────────────────────────────────────────────────
def test_usina_da_aba_so_pelo_de_para_publicado():
    antes = [_de(7, "BD_Thopen · Dados Gerais Usinas", "Usina Exemplo 1", "nome")]       # o sistema de antes não vale
    assert G.usina_da_aba(TH, "Usina Exemplo 1", antes) == (None, None, G.MOTIVO_SEM_DE_PARA)
    dp = antes + [_de(7, TH, "Usina Exemplo 1", "igual a BD_Thopen · Dados Gerais Usinas"),
                  _de(8, TH, "Soma", "igual a BD_Thopen · Dados Gerais Usinas"),
                  _de(9, TH, "Soma", "igual a BD_Thopen · Dados Gerais Usinas"),
                  _de(None, TH, "Sem par", B.SEM_PAR), _de("12.0", PF, "ABC100", "código")]
    assert G.usina_da_aba(TH, "Usina Exemplo 1", dp) == (7, "de-para (igual a BD_Thopen · Dados Gerais Usinas)", "")
    assert G.usina_da_aba(PF, "ABC100", dp) == (12, "de-para (código)", "")
    u, como, motivo = G.usina_da_aba(TH, "Soma", dp)           # o kWh contaria em dobro: não liga
    assert u is None and motivo.startswith("aba de 2 usinas")
    assert G.usina_da_aba(TH, "Sem par", dp) == (None, None, B.SEM_PAR)
    assert G.usina_da_aba(TH, "Aba criada depois", dp)[2] == G.MOTIVO_ABA_NOVA
    with pytest.raises(ValueError):
        G.usina_da_aba("BD_Thopen · Dados Gerais Usinas", "x", dp)


# ── teto e equipamento ──────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("texto, kw", [("250", 250.0), ("250 kW", 250.0), ("125 / 250", 250.0), ("75kWac", 75.0),
                                       ("100 kVA, 60 kVA e 75 Kw", 100.0), ("330 kW (480,5 A / 800 Vca)", 330.0),
                                       ("60 e 125kW", 125.0), ("N/I", None), ("", None), (None, None)])
def test_potencia_dos_inversores_em_kw(texto, kw):
    assert G.potencia_kw(texto) == kw


def test_teto_em_cascata():
    assert G.tetos({"potencia_inversores": "250", "potencia_contratual": 2.5}, 7.0)[:2] == (6000.0, 60000.0)
    assert G.tetos({"potencia_contratual": 2.5}, 7.0)[0] == 60000.0          # inversor <= a usina dele
    assert G.tetos(None, 7.02) == (168480.0, 168480.0, "maior usina do cadastro × 24 h")
    assert G.tetos(None, None) == (None, None, "sem teto: só o negativo cai")


def test_inversor_liga_pelo_apelido_do_modulo_de_equipamento_so_se_o_codigo_existe():
    """"Inversor 2.4" da aba da usina 7 liga ao membro "<código da usina 7>-INVR2.4" só se ele existe. A regra é UMA, do
    módulo de equipamento (apelido `BD_Thopen · coluna`, chave "aba|coluna"); o fato só lê os apelidos."""
    from nexus.dados import equipamento as E
    usinas = [{"usina_id": 7, "codigo": "XYZ-ABC100"}]
    fontes = {"bd_thopen": {"Aba A": [{"Data": "2026-10-06", "Inversor 2.4": 10.0, "inversor 2.5": 11.0}]}}
    dp = [_de(7, TH, "Aba A", "código")]
    assert G.usinas_das_abas(fontes, dp) == {("bd_thopen", "Aba A"): 7}
    cols = E.colunas_de_geracao(G.cabecalhos(fontes), G.usinas_das_abas(fontes, dp))
    apel = E.apelidos([], [], cols, E.membros([], {"fechamentos": ["XYZ-ABC100-INVR2.4"]}, usinas))
    _t, inv, _rel = G.montar(fontes, dp, usinas, HOJE, "agora", apelidos=apel)
    d = {x[7]: x for x in inv}
    assert d["Inversor 2.4"][3:5] == [E.equipamento_id("XYZ-ABC100-INVR2.4"), "apelido BD_Thopen · coluna"]
    assert d["Inversor 2.5"][3] is None                       # o código não existe: não chuta
    # sem usina ligada, nenhum apelido vale (mesmo que exista)
    _t, inv, _rel = G.montar(fontes, [], usinas, HOJE, "agora", apelidos=apel)
    assert {x[3] for x in inv} == {None}


# ── a montagem ──────────────────────────────────────────────────────────────────────────────────────────────────────
USINAS = [{"usina_id": 7, "codigo": "XYZ-ABC100", "potencia_contratual": 2.5, "potencia_inversores": "250"},
          {"usina_id": 8, "codigo": "DEF100", "potencia_contratual": 7.02}, {"usina_id": 9, "excluido": "sim"}]


def _fontes():
    perf = [{"Usina": "DEF100", "Data": "2026-10-06", "Multimedidor": 5000, "IPOA (kWh/m²) DEF": 5.9,
             "Inversor 1": 2400.0, "Inversor 2": 13000.0, "Validação": 1}]
    return {"bd_thopen": {"Usina Exemplo 1": _aba_thopen(), "Dados Gerais Usinas": [{"Usina": "Usina Exemplo 1"}]},
            "bd_performance": {"DEF100": perf, "Info Geral": [{"Usina": "DEF100", "Código Fractal": "DEF100"}]}}


def test_montar_sem_de_para_publicado_deixa_a_usina_vazia_com_o_motivo():
    t, inv, rel = G.montar(_fontes(), [], USINAS, HOJE, "2026-10-08T01:40:00-03:00")
    cab, linhas = t[G.ABA_USINA]
    assert len(linhas) == 3 and rel["pct_usina"] == 0.0
    assert {_col(cab, l, "usina_motivo") for l in linhas} == {G.MOTIVO_SEM_DE_PARA}
    # sem usina, o teto é o da maior usina do cadastro (7,02 MWp × 24 h): 13 mil kWh num inversor passa, 39 milhões não
    assert rel["teto"] == {"maior usina do cadastro × 24 h": 2}
    assert sorted(l[8] for l in inv if l[5] == "bd_performance") == [2400.0, 13000.0]
    assert G.ABA_INVERSOR not in t                     # o inversor × dia não vai ao banco até a decisão
    q = dict(zip(*[t["qualidade"][0], t["qualidade"][1][0]]))
    assert q["fato"] == "geracao_usina_dia" and q["pct_usina"] == 0.0 and q["linhas"] == 3
    assert t["qualidade"][0] == list(fatos.CAB_QUALIDADE)
    # o relatório (o que o ensaio imprime) não leva nome de aba
    assert "Usina Exemplo 1" not in json.dumps(rel, ensure_ascii=False)


def test_montar_com_de_para_publicado_liga_usina_teto_e_equipamento():
    dp = [_de(7, TH, "Usina Exemplo 1", "igual a BD_Thopen · Dados Gerais Usinas"), _de(8, PF, "DEF100", "código")]
    apel = [[11, "BD_Thopen · coluna", "Usina Exemplo 1|Inversor 1.1", "número do inversor"],
            {"equipamento_id": "12", "sistema": "BD_Performance · coluna", "chave_externa": "DEF100|Inversor 2"},
            [13, "Supervisório · tracker", "DEF100|Inversor 1", "x"]]           # outro sistema: não é coluna
    t, inv, rel = G.montar(_fontes(), dp, USINAS, HOJE, "agora", apelidos=apel)
    assert rel["pct_usina"] == 100.0 and rel["usina_por"]["de-para (código)"] == 1
    d = [dict(zip(G.CAB_INVERSOR_DIA, l)) for l in inv]
    # a usina 7 tem inversor de 250 kW: teto 6.000 kWh/dia
    assert {x["energia_kwh"] for x in d if x["usina_id"] == 7 and x["data_id"] == 20261006} == {1000.0, 962.8}
    # a 8 sem potência de inversor: teto = a própria usina (7,02 MWp × 24 h)
    p = {x["inversor"]: x for x in d if x["usina_id"] == 8}
    assert p["Inversor 2"]["energia_kwh"] == 13000.0 and p["Inversor 2"]["equipamento_id"] == 12
    assert p["Inversor 1"]["equipamento_id"] is None                       # sem apelido de coluna
    assert {x["equipamento_ligado_por"] for x in d if x["equipamento_id"]} == {"apelido BD_Thopen · coluna",
                                                                               "apelido BD_Performance · coluna"}


def test_aba_copia_da_mesma_usina_nao_liga_e_partes_da_usina_ligam():
    """Caso de 08/10: a aba velha parou em 30/09 com os MESMOS números da nova (100% iguais): somar as duas pelo
    usina_id dobraria o kWh. Partes da usina ("X 1" e "X 2" da "X 1 e 2") têm números diferentes e ligam as duas."""
    def aba(fator, dias=12, ate=None):
        return [{"Data": f"2026-09-{d:02d}", "Inversor 1.1": 100.0 * fator + d, "Inversor 1.2": 0}
                for d in range(1, (ate or dias) + 1)]
    fontes = {"bd_performance": {"Velha": aba(1, ate=11), "Nova": aba(1), "X 1": aba(2), "X 2": aba(3),
                                 "Zeros A": [{"Data": f"2026-09-{d:02d}", "Inversor 1.1": 0} for d in range(1, 13)],
                                 "Zeros B": [{"Data": f"2026-09-{d:02d}", "Inversor 1.1": 0} for d in range(1, 13)]}}
    dp = [_de(5, PF, "Velha", "código (Info Geral)"), _de(5, PF, "Nova", "código (Info Geral)"),
          _de(6, PF, "X 1", "código (Info Geral)"), _de(6, PF, "X 2", "código (Info Geral)"),
          _de(7, PF, "Zeros A", "código"), _de(7, PF, "Zeros B", "código")]
    t, _i, rel = G.montar(fontes, dp, [], HOJE, "agora")
    cab, linhas = t[G.ABA_USINA]
    por_aba = {_col(cab, l, "aba"): (_col(cab, l, "usina_id"), _col(cab, l, "usina_motivo")) for l in linhas}
    assert por_aba["Velha"] == por_aba["Nova"] == (None, G.MOTIVO_COPIA)
    assert por_aba["X 1"] == por_aba["X 2"] == (6, None)
    assert por_aba["Zeros A"] == (7, None)                      # zero igual não prova cópia
    assert rel["abas_copia"] == 2 and rel["usinas_em_2_abas"] == 2


def test_tabelas_publicaveis_e_conferidas_no_banco_falso():
    """O formato das tabelas é o da carga: `livros.publicar` grava e confere aba a aba (num banco FALSO)."""
    api = ApiPGFalsa()
    t, _inv, _rel = G.montar(_fontes(), [], USINAS, HOJE, "agora")
    r = livros.publicar(G.LIVRO, G.NOME_LIVRO, t, base="http://pg.falso", token="t", sessao=api)
    assert r == {G.ABA_USINA: 3, "qualidade": 1, "atualizacao": 1}
    lido = livros.ler("http://pg.falso", api, G.LIVRO, G.ABA_USINA)
    assert {x["data_id"] for x in lido} == {20261006, 20261007}


def test_encolhidas_aponta_a_aba_que_perdeu_dias():
    t, _i, _r = G.montar(_fontes(), [], USINAS, HOJE, "agora")
    anterior = [dict(zip(G.CAB_USINA_DIA, l)) for l in t[G.ABA_USINA][1]]
    menor = _fontes()
    menor["bd_thopen"]["Usina Exemplo 1"] = _aba_thopen()[1:]               # a aba foi regravada sem o 06/10
    _t, _i, rel = G.montar(menor, [], USINAS, HOJE, "agora", anterior=anterior)
    assert rel["encolhidas"] == 1
    assert G.encolhidas(G.dias_por_aba(anterior), {}) == sorted(
        [("bd_performance", "DEF100", 1, 0), ("bd_thopen", "Usina Exemplo 1", 2, 0)])


# ── o de-para dos sistemas de aba (nexus/cadastro) ──────────────────────────────────────────────────────────────────
class _U:
    def __init__(self, id_, **v):
        self.id, self._v = str(id_), v

    def valor(self, c):
        return self._v.get(c)


class _S:
    clientes = {"1": "Thopen", "2": "Cliente B"}

    def registros(self, ent, incluir_excluidos=False):
        return [_U(1, nome="Exemplo Norte 1", cliente="1", codigo="THPN-ENT100", cidade="Cidade A", uf="SP"),
                _U(2, nome="Exemplo Sul 1", cliente="1", codigo="THPN-EXS100", cidade="Cidade B", uf="SP"),
                _U(3, nome="Exemplo Sul 2", cliente="1", codigo="THPN-EXS200", cidade="Cidade B", uf="SP"),
                _U(4, nome="Exemplo Leste", cliente="2", codigo="CLB-ELT100")]

    def titulo_de(self, ent, ref):
        return self.clientes.get(str(ref), "")


def test_de_para_aba_igual_a_chave_casada_herda_e_codigo_de_outra_aba_fica_escrito():
    fontes = {"BD_Thopen · Dados Gerais Usinas": [
                  {"chave": "Exemplo Norte I", "nome": "Exemplo Norte I", "nomes": ["Exemplo Norte I"],
                   "cliente": "Thopen"},
                  {"chave": "Teste 9", "nome": "Teste 9", "nomes": ["Teste 9"], "cliente": "Thopen"}],
              TH: [{"chave": "Aba Norte", "nome": "Aba Norte", "nomes": ["Aba Norte"], "cliente": "Thopen",
                    "igual_a": ("BD_Thopen · Dados Gerais Usinas", "Exemplo Norte I")},
                   {"chave": "Aba Nove", "nome": "Aba Nove", "nomes": ["Exemplo Norte I"], "cliente": "Thopen",
                    "igual_a": ("BD_Thopen · Dados Gerais Usinas", "Teste 9")}],
              PF: [{"chave": "Exemplo Leste", "nome": "Exemplo Leste", "codigo": "CLB-ELT100",
                    "codigo_de": "Info Geral"},
                   {"chave": "ELT100", "nome": "ELT100", "codigo": "ELT100"}]}
    regras = [{"contem": "teste", "motivo": "teste"}]
    dp = B.de_para(_S(), fontes, regras)
    assert [1, "BD_Thopen · Dados Gerais Usinas", "Exemplo Norte I", "nome"] in dp
    assert [1, TH, "Aba Norte", "igual a BD_Thopen · Dados Gerais Usinas"] in dp
    # a referência saiu da conta: a aba também (sem isto, o nome "Exemplo Norte I" casaria pelo casamento)
    assert [None, TH, "Aba Nove", "ignorado: teste"] in dp
    assert [4, PF, "Exemplo Leste", "código (Info Geral)"] in dp and [4, PF, "ELT100", "código"] in dp


def test_de_para_aba_herda_a_soma_e_o_fato_nao_liga():
    """A referência ligada a 2 usinas (soma por potência) passa as 2 para a aba; o fato de geração recusa as duas."""
    fontes = {"Ref": [{"chave": "Exemplo Sul", "nome": "Exemplo Sul", "nomes": ["Exemplo Sul"], "cliente": "Thopen",
                       "mwp": 2.0}],
              TH: [{"chave": "Aba Sul", "nome": "Aba Sul", "igual_a": ("Ref", "Exemplo Sul")}]}

    class S2(_S):
        def registros(self, ent, incluir_excluidos=False):
            return [_U(2, nome="Exemplo Sul 1", cliente="1", potencia_contratual=1.0, cidade="Cidade B"),
                    _U(3, nome="Exemplo Sul 2", cliente="1", potencia_contratual=1.0, cidade="Cidade B")]
    dp = B.de_para(S2(), fontes)
    da_aba = [l for l in dp if l[1] == TH]
    assert sorted(l[0] for l in da_aba) == [2, 3]
    dicts = [dict(zip(B.CAB_DE_PARA, l)) for l in dp]
    assert G.usina_da_aba(TH, "Aba Sul", dicts)[0] is None


def test_itens_das_abas_thopen_e_performance():
    ref_th = [{"Usina": "Exemplo Norte I", "Cidade": "Cidade A", "Estado": "SP", "Potência (MWp)": 1.2},
              {"Usina": "Duplicada", "Cidade": "x"}, {"Usina": "duplicada", "Cidade": "y"}]
    primeiras = {"Exemplo Norte I": [_linha("2026-08-01", Usina="Exemplo Norte I")],
                 "Outro nome": [_linha("2026-08-01", Usina="Exemplo Norte I")],
                 "Duplicada": [_linha("2026-08-01", Usina="Duplicada")],
                 "Dados Gerais Usinas": [{"Usina": "x", "Cidade": "y"}]}
    it = {i["chave"]: i for i in L.itens_abas(TH, primeiras, ref_th, {})}
    assert set(it) == {"Exemplo Norte I", "Outro nome", "Duplicada"}            # a aba de cadastro não é chave
    assert it["Exemplo Norte I"]["igual_a"] == ("BD_Thopen · Dados Gerais Usinas", "Exemplo Norte I")
    assert it["Outro nome"]["igual_a"][1] == "Exemplo Norte I"                   # pela coluna Usina
    assert "igual_a" not in it["Duplicada"]                                       # nome de 2 linhas não é ponte
    assert it["Exemplo Norte I"]["cliente"] == "Thopen" and it["Exemplo Norte I"]["mwp"] == 1.2
    ref_pf = [{"Usina": "Exemplo Leste", "Código Fractal": "CLB-ELT100", "Cliente": "Cliente B"}]
    prim = {"Exemplo Leste": [{"Usina": "Exemplo Leste", "Data": "2026-08-01", "Inversor 1.1": 1}],
            "ABC100": [{"Usina": "ABC100", "Data": "2026-08-01", "Multimedidor": 1}],
            "Base UFV": [{"Usina": "x", "Código": "y"}]}
    ip = {i["chave"]: i for i in L.itens_abas(PF, prim, ref_pf)}
    assert set(ip) == {"Exemplo Leste", "ABC100"}
    assert (ip["Exemplo Leste"]["codigo"], ip["Exemplo Leste"]["codigo_de"], ip["Exemplo Leste"]["cliente"]) == (
        "CLB-ELT100", "Info Geral", "Cliente B")
    assert ip["ABC100"]["codigo"] == "ABC100" and "codigo_de" not in ip["ABC100"]
    assert L.SO_DO_CLIENTE[TH] == "Thopen" and [s for s, *_ in L.FONTES_ABA] == [TH, PF]


# ── a ponte pela tabela Equipamentos do BD_Performance (Levi, 08/10/2026: "se liga ao fractall ... fecharia esse ciclo")
EQUIP = [
    {"Cliente": "Thopen", "Usina": "Exemplo Norte I", "Usina Fractall": "Thopen - Exemplo Norte 1 - SP", "Equipamento": "UFV"},
    # espaço e caixa não fazem outro nome
    {"Cliente": "Thopen", "Usina": "Exemplo Norte I", "Usina Fractall": " thopen  - Exemplo Norte 1 - SP", "Equipamento": "Inversor 1.1"},
    {"Cliente": "Thopen", "Usina": "Sem Nome", "Usina Fractall": None, "Equipamento": "UFV"},
    # a linha UFV com o nome de outra usina (a "Rodrigues 2" de 08/10): 2 nomes, não liga
    {"Cliente": "Thopen", "Usina": "Duas", "Usina Fractall": "Thopen - Duas 1 - SP", "Equipamento": "UFV"},
    {"Cliente": "Thopen", "Usina": "Duas", "Usina Fractall": "Thopen - Duas 2 - SP", "Equipamento": "Inversor 1.1"},
    # o mesmo nome em outro cliente: a aba do BD_Thopen não o vê, e a do BD_Performance não vê o da Thopen
    {"Cliente": "Cliente B", "Usina": "Exemplo Norte I", "Usina Fractall": "Cliente B - Outra - CE", "Equipamento": "UFV"},
]


def test_itens_das_abas_levam_a_ponte_da_tabela_de_equipamentos():
    primeiras = {"Exemplo Norte I": [_linha("2026-08-01", Usina="Exemplo Norte I")],
                 "Pela Coluna": [_linha("2026-08-01", Usina="Exemplo Norte I")],
                 "Sem Nome": [_linha("2026-08-01", Usina="Sem Nome")], "Duas": [_linha("2026-08-01", Usina="Duas")],
                 "Fora": [_linha("2026-08-01", Usina="Fora da tabela")]}
    it = {i["chave"]: i for i in L.itens_abas(TH, primeiras, [], {}, EQUIP)}
    assert it["Exemplo Norte I"]["ponte"] == (L.FRACTTAL, "Thopen - Exemplo Norte 1 - SP", L.VIA_EQUIPAMENTOS)
    assert it["Pela Coluna"]["ponte"][1] == "Thopen - Exemplo Norte 1 - SP"        # pela coluna Usina da aba
    assert it["Pela Coluna"]["usina_equipamentos"] == "Exemplo Norte I"
    assert it["Sem Nome"]["ponte_motivo"].startswith("sem 'Usina Fractall'") and "ponte" not in it["Sem Nome"]
    assert it["Duas"]["ponte_motivo"].startswith("2 nomes do Fracttal")
    assert it["Fora"]["ponte_motivo"] == "sem linha na tabela de equipamentos"
    # o BD_Performance não cobre a Thopen: a mesma "Usina" acha só a linha do outro cliente
    ip = {i["chave"]: i for i in L.itens_abas(PF, {"Exemplo Norte I": [_linha("2026-08-01")]}, [], None, EQUIP)}
    assert ip["Exemplo Norte I"]["ponte"][1] == "Cliente B - Outra - CE"
    # sem a tabela, as abas casam como antes de 08/10
    assert not any("ponte" in i or "ponte_motivo" in i for i in L.itens_abas(TH, primeiras, [], {}))


def test_de_para_pela_ponte_liga_ao_que_o_fracttal_liga_e_nao_chuta():
    v = L.VIA_EQUIPAMENTOS
    fontes = {
        L.FRACTTAL: [{"chave": "Thopen - Exemplo Norte 1 - SP", "nome": "Thopen - Exemplo Norte 1 - SP",
                      "codigo": "THPN-ENT100"},
                     {"chave": "Thopen - Exemplo Sul 1  - SP", "nome": "Thopen - Exemplo Sul 1  - SP",
                      "codigo": "THPN-EXS100"},
                     {"chave": "Thopen - Sem Cadastro - SP", "nome": "Thopen - Sem Cadastro - SP"},
                     {"chave": "Thopen - Interna X - SP", "nome": "Thopen - Interna X - SP", "codigo": "THPN-ENT100"}],
        "BD_Thopen · Dados Gerais Usinas": [{"chave": "Exemplo Sul I", "nome": "Exemplo Sul I",
                                             "nomes": ["Exemplo Sul I"], "cliente": "Thopen"}],
        TH: [{"chave": "A", "nome": "A", "ponte": (L.FRACTTAL, "Thopen - Exemplo Norte 1 - SP", v)},
             # a chave do Fracttal tem dois espaços: o nome normalizado acha a ÚNICA chave
             {"chave": "B", "nome": "B", "ponte": (L.FRACTTAL, "Thopen - Exemplo Sul 1 - SP", v)},
             # a ponte diz a usina 1, o Dados Gerais diz a 2: ninguém liga
             {"chave": "C", "nome": "C", "ponte": (L.FRACTTAL, "Thopen - Exemplo Norte 1 - SP", v),
              "igual_a": ("BD_Thopen · Dados Gerais Usinas", "Exemplo Sul I")},
             {"chave": "D", "nome": "D", "ponte": (L.FRACTTAL, "Thopen - Sem Cadastro - SP", v)},
             {"chave": "E", "nome": "E", "codigo": "THPN-EXS100", "ponte_motivo": "sem linha na tabela de equipamentos"},
             {"chave": "F teste", "nome": "F teste", "ponte": (L.FRACTTAL, "Thopen - Exemplo Norte 1 - SP", v)},
             {"chave": "G", "nome": "G", "ponte": (L.FRACTTAL, "Thopen - Nunca Vista - SP", v)},
             # a chave do Fracttal ignorada não ignora a aba: vale o caminho antigo
             {"chave": "H", "nome": "H", "codigo": "THPN-EXS100", "ponte": (L.FRACTTAL, "Thopen - Interna X - SP", v)}]}
    regras = {"ignorar": [{"contem": "teste", "motivo": "teste"},
                          {"contem": "interna", "sistema": L.FRACTTAL, "motivo": "interna"}], "ligar": [], "desligar": []}

    class S(_S):
        def registros(self, ent, incluir_excluidos=False):
            return super().registros(ent)[:2]
    dp = {(l[1], l[2]): (l[0], l[3]) for l in B.de_para(S(), fontes, regras)}
    assert dp[(TH, "A")] == (1, f"{v} (código)")
    assert dp[(TH, "B")] == (2, f"{v} (código)")
    assert dp[(TH, "C")][0] is None and dp[(TH, "C")][1].startswith("conflito:")
    assert "usina 1" in dp[(TH, "C")][1] and "usina 2" in dp[(TH, "C")][1]
    assert dp[(TH, "D")] == (None, f"{B.SEM_PAR} ({v}: chave do Fracttal {B.SEM_PAR})")
    assert dp[(TH, "E")] == (2, "código")                                    # a ponte não fecha: o caminho antigo
    assert dp[(TH, "F teste")] == (None, "ignorado: teste")                  # decisão da tela vence a ponte
    assert dp[(TH, "G")] == (None, f"{B.SEM_PAR} ({v}: nome do Fracttal fora do de-para)")
    assert dp[(TH, "H")] == (2, "código")
    # o fato de geração herda o caminho na linhagem
    t, _i, _r = G.montar({"bd_thopen": {"A": [_linha("2026-10-06")]}}, [_de(u, s, k, c) for (s, k), (u, c) in
                                                                       dp.items() if u], [], HOJE, "agora")
    assert t[G.ABA_USINA][1][0][3] == f"de-para ({v} (código))"


def test_ponte_decide_entre_as_duas_usinas_que_o_caminho_antigo_somou():
    """A "Nova Londrina 1" de 08/10: o Dados Gerais a ligava a 2 usinas (a soma do casamento por potência, que a
    geração recusa); a tabela de equipamentos aponta UMA delas, e vale a dela."""
    ligado = {(L.FRACTTAL, "Thopen - X 1 - PR"): ([101], "código")}
    it = {"chave": "X 1", "ponte": (L.FRACTTAL, "Thopen - X 1 - PR", L.VIA_EQUIPAMENTOS)}
    assert B._pela_ponte(it, [101, 103], "igual a BD_Thopen · Dados Gerais Usinas", ligado, {}) == (
        [101], f"{L.VIA_EQUIPAMENTOS} (código)")
    assert B._pela_ponte(it, [102, 103], "igual a X", ligado, {})[0] == []     # nenhuma das duas: conflito
    duas = {(L.FRACTTAL, "Thopen - X 1 - PR"): ([101, 102], "nome")}
    assert B._pela_ponte(it, [], None, duas, {}) == (
        [], f"{B.SEM_PAR} ({L.VIA_EQUIPAMENTOS}: chave do Fracttal de 2 usinas)")


def test_tela_ligacoes_nao_lista_como_fora_a_usina_do_cliente_que_a_base_nao_cobre():
    """As abas do BD_Performance não têm usina da Thopen (a geração delas é do BD_Thopen): não é buraco."""
    class S3(_S):
        def registros(self, ent, incluir_excluidos=False):
            return [_U(1, nome="Exemplo Norte 1", cliente="1", codigo="THPN-ENT100", status="OPERAÇÃO"),
                    _U(4, nome="Exemplo Leste", cliente="2", codigo="CLB-ELT100", status="OPERAÇÃO"),
                    _U(5, nome="Exemplo Oeste", cliente="2", codigo="CLB-EOE100", status="OPERAÇÃO")]
    fontes = {PF: [{"chave": "ELT100", "nome": "ELT100", "codigo": "ELT100"}]}
    regras = {t: [] for t in L.TIPOS}
    pan = L.panorama(S3(), {"fontes": fontes, "linhas": B.de_para(S3(), fontes)}, regras)
    fora = {u["id"] for _cli, us in pan["ausencias"][PF] for u in us}
    assert fora == {5}                                          # a 1 (Thopen) não conta; a 5 (outro cliente) conta


def test_de_ponta_a_ponta_aba_do_de_para_calculado_liga_o_fato():
    """itens das abas -> de-para (como a tela publicaria) -> o fato acha o usina_id."""
    ref = [{"Usina": "Exemplo Norte I", "Cidade": "Cidade A"}]
    fontes = {"BD_Thopen · Dados Gerais Usinas": [{"chave": "Exemplo Norte I", "nome": "Exemplo Norte I",
                                                    "nomes": ["Exemplo Norte I"], "cliente": "Thopen"}],
              TH: L.itens_abas(TH, {"Aba Norte": [_linha("2026-10-06", Usina="Exemplo Norte I")]}, ref)}
    dp = [dict(zip(B.CAB_DE_PARA, l)) for l in B.de_para(_S(), fontes)]
    t, _i, rel = G.montar({"bd_thopen": {"Aba Norte": [_linha("2026-10-06")]}}, dp,
                          [{"usina_id": 1, "codigo": "THPN-ENT100"}], HOJE, "agora")
    assert rel["pct_usina"] == 100.0 and t[G.ABA_USINA][1][0][2] == 1


# ── a ferramenta: só ensaio ─────────────────────────────────────────────────────────────────────────────────────────
def test_ferramenta_recusa_gravar_e_o_adaptador_do_cadastro_serve_ao_de_para(monkeypatch):
    from ferramentas import carregar_geracao as F
    monkeypatch.setattr(sys, "argv", ["carregar_geracao.py"])
    with pytest.raises(SystemExit) as e:
        F.main()
    assert "--ensaio" in str(e.value)
    cad = F.CadastroDoBanco([{"usina_id": 5.0, "codigo": "ABC100", "nome": "Exemplo", "cliente_id": 1.0},
                             {"usina_id": 6, "codigo": "DEF100", "excluido": "sim"}],
                            [{"cliente_id": 1, "nome": "Cliente B"}])
    dp = B.de_para(cad, {PF: [{"chave": "ABC100", "nome": "ABC100", "codigo": "ABC100"},
                              {"chave": "DEF100", "nome": "DEF100", "codigo": "DEF100"}]})
    assert [5, PF, "ABC100", "código"] in dp and [None, PF, "DEF100", B.SEM_PAR] in dp

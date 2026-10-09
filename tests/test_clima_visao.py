"""Clima e risco: o view-model da tela (`visao.montar`), com leituras prontas no lugar das fontes. Sem rede, sem Flask."""
from datetime import datetime, timedelta, timezone

import pytest

from nexus.performance.clima import explica as EX
from nexus.performance.clima import geometria
from nexus.performance.clima import leitura as L
from nexus.performance.clima import visao as V
from nexus.performance.clima.fontes import Aviso, Foco
from nexus.performance.clima.geotiff import Amostra
from nexus.performance.clima.usinas import Cadastro, Usina

BRT = timezone(timedelta(hours=-3))
UTC = timezone.utc
REF = datetime(2026, 10, 6, 15, 0, tzinfo=BRT)
LIDO = REF.timestamp()
GRANDE = {"type": "Polygon", "coordinates": [[[-46, -6], [-44, -6], [-44, -4], [-46, -4], [-46, -6]]]}


def usina(id_, nome, lat=-5.0, lon=-45.0, cliente="Cliente", uf="PI"):
    return Usina(id_, nome, cliente, uf, "Cidade", lat, lon)


def cadastro(*usinas, sem=(), fora=()):
    return Cadastro(list(usinas), list(sem), list(fora), len(usinas) + len(sem) + len(fora))


def aviso(nivel=2, evento="Tempestade", inicio=None, fim=None, geo=GRANDE):
    sev = {1: "Perigo Potencial", 2: "Perigo", 3: "Grande Perigo"}[nivel]
    return Aviso(nivel * 10, "hoje", evento, sev, nivel, inicio or REF - timedelta(hours=1), fim or REF + timedelta(hours=8),
                 geo, geometria.caixa(geo))


def lei_avisos(*avisos, ignorados=()):
    return L.Leitura({"avisos": list(avisos), "ignorados": list(ignorados), "lidos": len(avisos)}, LIDO)


def lei_focos(*focos, ate=None, falhos=(), ruins=0):
    ate = ate or datetime(2026, 10, 6, 17, 50, tzinfo=UTC)
    return L.Leitura({"focos": list(focos), "arquivos": ["a.csv"], "falhos": list(falhos), "ate": ate, "linhas_ruins": ruins}, LIDO)


def foco_a(km, lat=-5.0, lon=-45.0, sat="GOES-19"):
    return Foco(lat + km / 111.195, lon, sat, datetime(2026, 10, 6, 17, 50, tzinfo=UTC))


def lei_risco(por_ponto, arquivos=None, erros=None):
    arquivos = {0: datetime(2026, 10, 6, 9, 32, tzinfo=UTC)} if arquivos is None else arquivos
    return L.Leitura({"por_ponto": por_ponto, "arquivos": arquivos, "erros": erros or {}}, LIDO)


def dias(*valores, origem="ponto"):
    return [Amostra(v, origem if v is not None else "sem_dado") for v in valores]


@pytest.fixture
def leituras(monkeypatch):
    pedidos = {"risco": []}

    def instalar(avisos=None, focos=None, risco=None):
        vazio = L.Leitura(None, None, erro="sem fonte nos testes")
        monkeypatch.setattr(L, "avisos", lambda config, sessao=None: avisos or vazio)
        monkeypatch.setattr(L, "focos", lambda config, sessao=None: focos or vazio)

        def lr(config, pontos, sessao=None):
            pedidos["risco"].append(list(pontos))
            return risco or vazio
        monkeypatch.setattr(L, "risco", lr)
        return pedidos
    return instalar


def nomes(v):
    return [c["nome"] for c in v["alertas"]]


def faixa(v):
    return {f["id"]: f for f in v["faixa"]}


def tudo_lido(leituras, avisos=(), focos=(), risco=None, id_="1"):
    """As três fontes lidas e inteiras, para o teste olhar só o que interessa."""
    leituras(avisos=lei_avisos(*avisos), focos=lei_focos(*focos), risco=risco or lei_risco({id_: dias(0.1, 0.1, 0.1, 0.1)}))


def so_a_usina(leituras, *, avisos=(), foco_km=None, risco=(0.1, 0.1, 0.1, 0.1)):
    """Uma usina "U" com as três fontes lidas; devolve a tela."""
    focos = [foco_a(foco_km)] if foco_km is not None else []
    tudo_lido(leituras, avisos, focos, lei_risco({"1": dias(*risco)}))
    return V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)


def nivel(v):
    return (v["alertas"] or [{"nivel": "sem"}])[0]["nivel"]


def em_volta(lat, lon, meia=0.05):
    return {"type": "Polygon", "coordinates": [[[lon - meia, lat - meia], [lon + meia, lat - meia], [lon + meia, lat + meia],
                                                [lon - meia, lat + meia], [lon - meia, lat - meia]]]}


# ── os três níveis (07/10/2026): cada regra, uma de cada vez ─────────────────────────────────────────────────────────

def test_foco_a_ate_5_km_manda_agir_e_a_5_1_km_nao(leituras):
    v = so_a_usina(leituras, foco_km=4.9)
    assert nivel(v) == "agir" and v["alertas"][0]["rotulo"] == "Agir agora"
    assert nivel(so_a_usina(leituras, foco_km=5.1)) == "sem"


@pytest.mark.parametrize("evento", ["Onda de Calor", "Baixa Umidade", "Evento Novo do INMET"])
def test_grande_perigo_de_qualquer_evento_manda_agir(leituras, evento):
    assert nivel(so_a_usina(leituras, avisos=[aviso(3, evento=evento)])) == "agir"


@pytest.mark.parametrize("evento", ["Tempestade", "Chuvas Intensas", "Acumulado de Chuva", "Vendaval", "Ventos Costeiros",
                                    "Granizo", "TEMPESTADE", " chuvas   intensas "])
def test_perigo_de_evento_que_estraga_usina_manda_agir(leituras, evento):
    assert nivel(so_a_usina(leituras, avisos=[aviso(2, evento=evento)])) == "agir"


@pytest.mark.parametrize("evento", ["Onda de Calor", "Baixa Umidade", "Geada", "Evento Novo do INMET"])
def test_perigo_de_evento_desconhecido_vai_para_atencao_e_nao_some(leituras, evento):
    v = so_a_usina(leituras, avisos=[aviso(2, evento=evento)])
    assert nivel(v) == "atencao" and v["alertas"][0]["avisos"][0]["evento"] == evento


@pytest.mark.parametrize("evento", ["Tempestade", "Vendaval", "Baixa Umidade"])
def test_perigo_potencial_e_atencao_ate_de_tempestade(leituras, evento):
    assert nivel(so_a_usina(leituras, avisos=[aviso(1, evento=evento)])) == "atencao"


def test_aviso_que_ainda_vai_comecar_conta_e_diz_quando_comeca(leituras):
    futuro = aviso(2, evento="Vendaval", inicio=REF + timedelta(days=1), fim=REF + timedelta(days=1, hours=9))
    v = so_a_usina(leituras, avisos=[futuro])
    assert nivel(v) == "agir"
    assert v["alertas"][0]["motivos"][0]["prova"] == "Quando: a partir de 07/10 15:00, até 08/10 00:00"
    potencial = aviso(1, evento="Tempestade", inicio=REF + timedelta(hours=30), fim=REF + timedelta(hours=40))
    assert nivel(so_a_usina(leituras, avisos=[potencial])) == "atencao"


def test_aviso_vencido_nao_conta(leituras):
    vencido = aviso(3, evento="Vendaval", inicio=REF - timedelta(hours=9), fim=REF - timedelta(minutes=1))
    assert nivel(so_a_usina(leituras, avisos=[vencido])) == "sem"


@pytest.mark.parametrize("risco", [(0.8, 0.1, 0.1, 0.1), (0.1, 0.1, 0.1, 0.71), (0.1, 0.99, 0.1, 0.1)])
def test_risco_alto_ou_critico_em_qualquer_dos_quatro_dias_e_atencao(leituras, risco):
    assert nivel(so_a_usina(leituras, risco=risco)) == "atencao"


def test_risco_medio_nao_e_alerta(leituras):
    assert nivel(so_a_usina(leituras, risco=(0.69, 0.5, 0.4, 0.2))) == "sem"


def test_foco_vence_o_resto_e_agir_vence_atencao(leituras):
    leve = aviso(1, evento="Baixa Umidade")
    v = so_a_usina(leituras, avisos=[leve], foco_km=1.0, risco=(0.99, 0.99, 0.99, 0.99))
    assert nivel(v) == "agir" and len(v["agir"]) == 1 and v["atencao"] == []


def test_sem_alerta_so_conta_com_as_tres_fontes_lidas(leituras):
    tudo_lido(leituras)
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    f = faixa(v)["sem"]
    assert (v["sem_alerta"], f["valor"], f["sub"], f["qual"]) == (1, "1", "nas três fontes lidas", [])
    leituras(focos=lei_focos(), risco=lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1)}))                  # o INMET está fora
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    f = faixa(v)["sem"]
    assert (v["sem_alerta"], f["valor"], f["sub"]) == (None, "—", "não dá para dizer")
    assert f["qual"] == ["sem leitura de avisos do Instituto Nacional de Meteorologia (INMET)"]


@pytest.mark.parametrize("faltando", ["avisos", "focos", "risco"])
def test_faltou_qualquer_fonte_o_sem_alerta_vira_traco(leituras, faltando):
    ok = {"avisos": lei_avisos(), "focos": lei_focos(), "risco": lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1)})}
    ok.pop(faltando)
    leituras(**ok)
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert v["sem_alerta"] is None and faixa(v)["sem"]["valor"] == "—"


# ── ordem: o nível primeiro, e DENTRO de cada nível a gravidade que já existia ────────────────────────────────────────

def test_agir_agora_vem_antes_de_atencao_mesmo_com_risco_critico_do_outro_lado(leituras):
    # "A" só tem risco crítico (gravidade 3) e é atenção; "Z" tem Perigo de tempestade (gravidade 2) e é agir agora: Z primeiro
    cad = cadastro(usina("1", "A Risco critico", -5.0, -45.0), usina("2", "Z Tempestade", -5.0, -50.0))
    tudo_lido(leituras, [aviso(2, evento="Tempestade", geo=em_volta(-5.0, -50.0))],
              risco=lei_risco({"1": dias(0.99, 0.99, 0.99, 0.99), "2": dias(0.1, 0.1, 0.1, 0.1)}))
    v = V.montar({}, cadastro=cad, ref=REF)
    assert nomes(v) == ["Z Tempestade", "A Risco critico"]
    assert [c["nome"] for c in v["agir"]] == ["Z Tempestade"] and [c["nome"] for c in v["atencao"]] == ["A Risco critico"]


def test_dentro_do_nivel_o_pior_alerta_de_cada_usina_vem_primeiro(leituras):
    cad = cadastro(usina("1", "A Potencial", -5.0), usina("2", "B Alto", -5.1), usina("3", "C Critico", -5.2))
    leituras(avisos=lei_avisos(aviso(1, geo={"type": "Polygon", "coordinates": [[[-46, -5.05], [-44, -5.05], [-44, -4.9], [-46, -4.9], [-46, -5.05]]]})),
             focos=lei_focos(), risco=lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1), "2": dias(0.8, 0.1, 0.1, 0.1), "3": dias(0.99, 0.1, 0.1, 0.1)}))
    v = V.montar({}, cadastro=cad, ref=REF)
    assert [c["nivel"] for c in v["alertas"]] == ["atencao"] * 3 and nomes(v) == ["C Critico", "B Alto", "A Potencial"]


# Os desempates abaixo se provam um de cada vez: em cada cenário só UMA chave da ordem decide, e os nomes estão em ordem
# alfabética contrária à esperada, para o nome nunca ser quem acerta.

def test_desempate_foco_vem_antes_de_mais_tipos_de_alerta(leituras):
    cad = cadastro(usina("1", "A Aviso e risco", -5.0, -45.0), usina("2", "Z So foco", -5.0, -50.0))
    leituras(avisos=lei_avisos(aviso(3, geo=em_volta(-5.0, -45.0))), focos=lei_focos(foco_a(2.0, -5.0, -50.0)),
             risco=lei_risco({"1": dias(0.99, 0.1, 0.1, 0.1), "2": dias(0.1, 0.1, 0.1, 0.1)}))
    v = V.montar({}, cadastro=cad, ref=REF)
    assert [c["nivel"] for c in v["alertas"]] == ["agir", "agir"]                      # empatados no nível e na gravidade 3
    assert nomes(v) == ["Z So foco", "A Aviso e risco"]


def test_desempate_mais_tipos_de_alerta_primeiro(leituras):
    cad = cadastro(usina("1", "A So aviso", -5.0, -45.0), usina("2", "Z Aviso e risco", -5.0, -50.0))
    leituras(avisos=lei_avisos(aviso(2, geo=em_volta(-5.0, -45.0)), aviso(2, geo=em_volta(-5.0, -50.0))), focos=lei_focos(),
             risco=lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1), "2": dias(0.8, 0.1, 0.1, 0.1)}))
    v = V.montar({}, cadastro=cad, ref=REF)
    assert [c["nivel"] for c in v["alertas"]] == ["agir", "agir"]
    assert nomes(v) == ["Z Aviso e risco", "A So aviso"]


def test_desempate_o_aviso_mais_grave_primeiro(leituras):
    # as duas são atenção (aviso fora da lista de eventos que estragam usina), gravidade 3 (risco crítico) e 2 tipos de alerta
    cad = cadastro(usina("1", "A Potencial", -5.0, -45.0), usina("2", "Z Perigo", -5.0, -50.0))
    leituras(avisos=lei_avisos(aviso(1, evento="Onda de Calor", geo=em_volta(-5.0, -45.0)),
                               aviso(2, evento="Onda de Calor", geo=em_volta(-5.0, -50.0))), focos=lei_focos(),
             risco=lei_risco({"1": dias(0.99, 0.1, 0.1, 0.1), "2": dias(0.99, 0.1, 0.1, 0.1)}))
    v = V.montar({}, cadastro=cad, ref=REF)
    assert [c["nivel"] for c in v["alertas"]] == ["atencao", "atencao"]
    assert nomes(v) == ["Z Perigo", "A Potencial"]


def test_empate_o_foco_mais_perto_primeiro(leituras):
    cad = cadastro(usina("1", "A Longe", -5.0, -45.0), usina("2", "Z Perto", -5.0, -44.0))
    leituras(avisos=lei_avisos(), focos=lei_focos(foco_a(4.0, -5.0, -45.0), foco_a(0.5, -5.0, -44.0)))
    assert nomes(V.montar({}, cadastro=cad, ref=REF)) == ["Z Perto", "A Longe"]


def test_ultimo_desempate_e_o_nome_sem_acento_nem_caixa(leituras):
    cad = cadastro(usina("1", "zebra", -5.0), usina("2", "Árvore", -5.0), usina("3", "Mata", -5.0))
    leituras(risco=lei_risco({i: dias(0.9, 0.9, 0.9, 0.9) for i in "123"}))
    assert nomes(V.montar({}, cadastro=cad, ref=REF)) == ["Árvore", "Mata", "zebra"]


# ── a faixa do topo: Agir agora, Atenção, Sem alerta, Cobertura ──────────────────────────────────────────────────────

def test_faixa_conta_os_niveis_e_a_cobertura_e_a_soma_fecha(leituras):
    cad = cadastro(usina("1", "A Agir", -5.0, -45.0), usina("2", "B Atencao", -5.0, -50.0), usina("3", "C Sem", -5.0, -55.0),
                   usina("4", "D Sem", -5.0, -56.0), sem=[usina("5", "E Sem coordenada", None, None)])
    tudo_lido(leituras, [aviso(3, geo=em_volta(-5.0, -45.0))],
              risco=lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1), "2": dias(0.9, 0.1, 0.1, 0.1), "3": dias(0.1, 0.1, 0.1, 0.1),
                               "4": dias(0.1, 0.1, 0.1, 0.1)}))
    v = V.montar({}, cadastro=cad, ref=REF)
    f = faixa(v)
    assert [x["id"] for x in v["faixa"]] == ["agir", "atencao", "sem", "cobertura"]
    assert [x["rotulo"] for x in v["faixa"]] == ["Agir agora", "Atenção", "Sem alerta", "Cobertura"]
    assert [f[i]["valor"] for i in ("agir", "atencao", "sem", "cobertura")] == ["1", "1", "2", "4"]
    assert int(f["agir"]["valor"]) + int(f["atencao"]["valor"]) + int(f["sem"]["valor"]) == v["n_usinas"] == 4
    assert f["cobertura"]["sub"] == "em operação com coordenada · 1 sem coordenada"
    assert f["agir"]["sub"] == "fogo a até 5 km ou aviso forte (tempestade, chuva forte, vento, granizo) do Instituto Nacional de Meteorologia (INMET)"
    assert f["atencao"]["sub"] == "outro aviso do Instituto Nacional de Meteorologia (INMET) ou risco de fogo alto nos próximos 4 dias: acompanhar"
    # "O que fazer" (09/10/2026) em cada nível que tem usina; a cobertura não tem
    assert f["agir"]["fazer"].startswith("Avisar o supervisor") and f["atencao"]["fazer"].startswith("Acompanhar")
    assert f["sem"]["fazer"] == "Nada." and f["cobertura"]["fazer"] == ""
    assert (v["sem_alerta"], len(v["agir"]), len(v["atencao"])) == (2, 1, 1)


def test_faixa_cobertura_diz_quantas_estao_sem_dado_de_risco(leituras):
    tudo_lido(leituras, risco=lei_risco({"1": dias(None, None, None, None), "2": dias(0.1, 0.1, 0.1, 0.1)}))
    v = V.montar({}, cadastro=cadastro(usina("1", "Sem vegetacao"), usina("2", "Normal", -5.5)), ref=REF)
    assert faixa(v)["cobertura"]["valor"] == "2"
    assert faixa(v)["cobertura"]["sub"] == "em operação com coordenada · 1 sem dado de risco"


def test_faixa_cobertura_conta_a_coordenada_fora_do_brasil(leituras):
    tudo_lido(leituras)
    v = V.montar({}, cadastro=cadastro(usina("1", "U"), fora=[usina("2", "Zero", 0.0, 0.0)]), ref=REF)
    assert faixa(v)["cobertura"]["sub"] == "em operação com coordenada · 1 com coordenada fora do Brasil"


def test_unidade_no_singular_e_no_plural(leituras):
    v = so_a_usina(leituras, foco_km=1.0)
    assert faixa(v)["agir"]["unidade"] == "usina" and faixa(v)["atencao"]["unidade"] == "usinas"


def test_fonte_sem_leitura_mostra_traco_e_as_outras_seguem(leituras):
    cad = cadastro(usina("1", "U"))
    leituras(risco=lei_risco({"1": dias(0.99, 0.1, 0.1, 0.1)}))               # avisos e focos sem leitura
    v = V.montar({}, cadastro=cad, ref=REF)
    f = faixa(v)
    assert (f["agir"]["valor"], f["agir"]["unidade"]) == ("—", "")             # o agir depende dos avisos e dos focos: nenhum lido
    assert f["atencao"]["valor"] == "1"                                         # o risco foi lido, e o número vale
    assert f["atencao"]["qual"] == ["sem leitura de avisos do Instituto Nacional de Meteorologia (INMET)"]
    assert f["sem"]["valor"] == "—"
    assert [x["estado"] for x in v["fontes"]] == ["fora", "fora", "ok"]
    assert nomes(v) == ["U"]


def test_o_agir_so_vira_traco_quando_nem_os_avisos_nem_os_focos_foram_lidos(leituras):
    leituras(focos=lei_focos(foco_a(1.0)), risco=lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1)}))         # só o INMET fora
    f = faixa(V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF))
    assert f["agir"]["valor"] == "1" and f["agir"]["qual"] == ["sem leitura de avisos do Instituto Nacional de Meteorologia (INMET)"]
    leituras(avisos=lei_avisos(), risco=lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1)}))                     # só os focos fora
    f = faixa(V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF))
    assert f["agir"]["valor"] == "0" and f["agir"]["qual"] == ["sem leitura de focos de queimada do Instituto Nacional de Pesquisas Espaciais (INPE)"] and "cl-na" in f["agir"]["classe"]


def test_o_atencao_so_vira_traco_quando_nem_os_avisos_nem_o_risco_foram_lidos(leituras):
    leituras(focos=lei_focos())
    f = faixa(V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF))
    assert f["atencao"]["valor"] == "—" and f["agir"]["valor"] == "0"


def test_zero_e_zero_quando_as_fontes_leram_e_nao_ha_alerta(leituras):
    tudo_lido(leituras)
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    f = faixa(v)
    assert [f[i]["valor"] for i in ("agir", "atencao", "sem")] == ["0", "0", "1"]
    assert all("cl-na" not in f[i]["classe"] for i in ("agir", "atencao", "sem"))
    assert v["alertas"] == [] and v["sem_alerta"] == 1


def test_lista_diz_que_esta_incompleta_quando_falta_uma_fonte(leituras):
    leituras(risco=lei_risco({"1": dias(0.99, 0.1, 0.1, 0.1)}))               # sem avisos e sem focos
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert v["faltando"] == ["avisos do Instituto Nacional de Meteorologia (INMET)", "focos de queimada do Instituto Nacional de Pesquisas Espaciais (INPE)"]
    leituras(avisos=lei_avisos(), focos=lei_focos(), risco=lei_risco({"1": dias(0.99, 0.1, 0.1, 0.1)}))
    assert V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["faltando"] == []
    velha = L.Leitura({"avisos": [], "ignorados": [], "lidos": 0}, LIDO - 3600, erro="tempo esgotado", velha=True)
    leituras(avisos=velha, focos=lei_focos(), risco=lei_risco({"1": dias(0.99, 0.1, 0.1, 0.1)}))
    assert V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["faltando"] == []     # a leitura velha ainda vale, com a hora dela


def test_fonte_lendo_diz_lendo(leituras):
    leituras(avisos=L.Leitura(None, None, erro=L.LENDO))
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert v["fontes"][0]["estado"] == "atencao" and "lendo a fonte" in v["fontes"][0]["texto"]


def test_fonte_lendo_diz_lendo_na_faixa_e_nao_sem_leitura(leituras):
    leituras(avisos=L.Leitura(None, None, erro=L.LENDO), focos=lei_focos(), risco=lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1)}))
    f = faixa(V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF))
    assert f["agir"]["qual"] == ["lendo avisos do Instituto Nacional de Meteorologia (INMET)"] and f["atencao"]["qual"] == ["lendo avisos do Instituto Nacional de Meteorologia (INMET)"]
    assert f["sem"]["valor"] == "—" and f["sem"]["qual"] == ["lendo avisos do Instituto Nacional de Meteorologia (INMET)"]


def test_leitura_velha_diz_fora_agora_e_a_hora_da_ultima_boa(leituras):
    velha = L.Leitura({"avisos": [], "ignorados": [], "lidos": 0}, LIDO - 3600, erro="tempo esgotado", velha=True)
    leituras(avisos=velha)
    f = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["fontes"][0]
    assert f["texto"] == "Instituto Nacional de Meteorologia (INMET) · avisos: fora agora; última leitura boa às 14:00" and f["detalhe"] == "tempo esgotado" and f["estado"] == "atencao"


def test_leitura_boa_de_ontem_leva_a_data_na_hora(leituras):
    velha = L.Leitura({"avisos": [], "ignorados": [], "lidos": 0}, LIDO - 86400, erro="HTTP 500", velha=True)
    leituras(avisos=velha)
    assert "última leitura boa às 05/10 15:00" in V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["fontes"][0]["texto"]


def test_aviso_ignorado_aparece_no_detalhe_da_fonte(leituras):
    leituras(avisos=lei_avisos(ignorados=["aviso 7: sem polígono", "aviso 8: ilegível"]))
    assert "2 avisos foram ignorados" in V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["fontes"][0]["detalhe"]


def test_arquivo_de_focos_que_falhou_aparece_no_detalhe(leituras):
    leituras(focos=lei_focos(falhos=["b.csv"]))
    assert "1 de 2 arquivos indisponíveis" in V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["fontes"][1]["detalhe"]


def test_dia_do_risco_que_falhou_diz_qual_dia_e_por_que(leituras):
    por = {"1": [Amostra(0.2, "ponto")] * 3 + [Amostra(None, "indisponivel")]}
    leituras(risco=lei_risco(por, erros={3: "HTTP 404"}))
    f = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["fontes"][2]
    assert f["estado"] == "atencao" and f["detalhe"] == "D+3 indisponível (HTTP 404)"


# ── cliente e cobertura ──────────────────────────────────────────────────────────────────────────────────────────────

def test_filtro_por_cliente_nunca_muda_o_conjunto_de_pontos_do_risco(leituras):
    cad = cadastro(usina("1", "A", cliente="X"), usina("2", "B", cliente="Y", lat=-5.5))
    pedidos = leituras(risco=lei_risco({"1": dias(0.9, 0.9, 0.9, 0.9), "2": dias(0.9, 0.9, 0.9, 0.9)}))
    todos = V.montar({}, cadastro=cad, ref=REF)
    so_y = V.montar({}, cadastro=cad, ref=REF, cliente="Y")
    assert nomes(todos) == ["A", "B"] and nomes(so_y) == ["B"] and so_y["cliente"] == "Y" and so_y["n_usinas"] == 1
    assert pedidos["risco"][0] == pedidos["risco"][1] and len(pedidos["risco"][0]) == 2


def test_cliente_que_nao_existe_vale_como_todos(leituras):
    cad = cadastro(usina("1", "A", cliente="X"))
    leituras(risco=lei_risco({"1": dias(0.9, 0.9, 0.9, 0.9)}))
    v = V.montar({}, cadastro=cad, ref=REF, cliente="Inventado")
    assert v["cliente"] == "" and nomes(v) == ["A"]


def test_sem_usina_com_coordenada_nao_vai_a_rede(leituras, monkeypatch):
    def nao(*a, **k):
        raise AssertionError("foi buscar fonte sem ter usina")
    for f in ("avisos", "focos", "risco"):
        monkeypatch.setattr(L, f, nao)
    v = V.montar({}, cadastro=cadastro(sem=[usina("1", "Sem", None, None)]), ref=REF)
    assert v["sem_usinas"] is True and v["sem_coordenada"] == ["Sem"] and v["faixa"] == [] and v["fontes"] == [] and v["ufs"] == []


def test_sem_coordenada_e_fora_do_brasil_seguem_o_filtro_e_o_cadastro_com_erro_nao_tem_nada(leituras):
    cad = cadastro(usina("1", "A", cliente="X"), sem=[usina("2", "SemX", None, None, "X"), usina("3", "SemY", None, None, "Y")],
                   fora=[usina("4", "ForaY", 0.0, 0.0, "Y")])
    leituras(risco=lei_risco({"1": dias(0.9, 0.9, 0.9, 0.9)}))
    v = V.montar({}, cadastro=cad, ref=REF, cliente="Y")
    assert v["sem_coordenada"] == ["SemY"] and v["fora_do_brasil"] == ["ForaY"]
    assert V.montar({}, cadastro=None, erro_cadastro="falta a chave", ref=REF)["erro_cadastro"] == "falta a chave"


def test_cliente_sem_nenhuma_usina_no_mapa_mostra_so_as_pendencias_e_nao_vai_a_rede(leituras, monkeypatch):
    cad = cadastro(usina("1", "A", cliente="X"), sem=[usina("2", "SemY", None, None, "Y")])
    leituras(risco=lei_risco({"1": dias(0.9, 0.9, 0.9, 0.9)}))
    v = V.montar({}, cadastro=cad, ref=REF, cliente="Y")
    assert v["cliente"] == "Y" and v["sem_usinas"] is True and v["sem_coordenada"] == ["SemY"] and v["alertas"] == []


def test_usina_sem_dado_de_risco_nos_quatro_dias_entra_na_cobertura(leituras):
    leituras(risco=lei_risco({"1": dias(None, None, None, None), "2": dias(0.1, None, 0.1, 0.1)}))
    v = V.montar({}, cadastro=cadastro(usina("1", "Toda sem dado"), usina("2", "Parcial", -5.5)), ref=REF)
    assert v["sem_risco"] == [{"motivo": "sem vegetação no entorno", "nomes": ["Toda sem dado"]}]


# ── frases ───────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_frase_do_foco_no_singular_e_no_plural(leituras):
    leituras(focos=lei_focos(foco_a(1.0)))
    um = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["alertas"][0]["foco"]["texto"]
    assert um == "1 foco a até 5 km · o mais perto a 1,0 km (GOES-19, 14:50)"
    leituras(focos=lei_focos(foco_a(1.0), foco_a(2.0), foco_a(3.0)))
    tres = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["alertas"][0]["foco"]["texto"]
    assert tres.startswith("3 focos a até 5 km · o mais perto a 1,0 km")


def test_milhar_em_portugues_na_contagem_de_focos(leituras):
    muitos = [Foco(-9.0 - i * 0.001, -40.0, "NOAA-21", datetime(2026, 10, 6, 17, 50, tzinfo=UTC)) for i in range(4829)]
    leituras(focos=lei_focos(*muitos))
    assert "4.829 focos na última hora" in V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["fontes"][1]["texto"]
    assert V.milhar(7) == "7" and V.milhar(1000) == "1.000" and V.milhar(1234567) == "1.234.567"


def test_hora_com_e_sem_o_dia():
    assert V.hora(datetime(2026, 10, 6, 17, 50, tzinfo=UTC), REF) == "14:50"
    assert V.hora(datetime(2026, 10, 7, 11, 0, tzinfo=UTC), REF) == "07/10 08:00"
    assert V.hora(datetime(2026, 10, 6, 2, 30, tzinfo=UTC), REF) == "05/10 23:30"        # 02:30 UTC ainda é 23:30 de ontem em Brasília
    assert V.numero(0.5) == "0,50" and V.numero(1.234, 1) == "1,2"


def test_previsao_de_dia_diferente_do_de_hoje_fica_em_atencao(leituras):
    ontem = {0: datetime(2026, 10, 5, 9, 32, tzinfo=UTC)}
    leituras(risco=lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1)}, arquivos=ontem))
    f = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["fontes"][2]
    assert f["estado"] == "atencao" and "previsão de 05/10 (arquivo das 06:32) · de ontem" in f["texto"]
    anteontem = {0: datetime(2026, 10, 3, 9, 32, tzinfo=UTC)}
    leituras(risco=lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1)}, arquivos=anteontem))
    assert "· de 03/10" in V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["fontes"][2]["texto"]


# ── o cartão do "Agir agora": motivo, frase principal, prova e contexto ──────────────────────────────────────────────

def test_cartao_do_foco_tem_motivo_frase_principal_e_prova(leituras):
    v = so_a_usina(leituras, foco_km=0.2)
    c = v["agir"][0]
    # 09/10/2026 ("deixe mais didático"): a frase fala "fogo", e o motivo leva o que pode acontecer e o que conferir (explica.py)
    assert c["motivos"] == [{"tipo": "foco", "pill": "Fogo a 0,2 km", "principal": "Fogo a 0,2 km da usina",
                             "prova": "1 foco de queimada a até 5 km na última hora · visto pelo satélite GOES-19 às 14:50",
                             **EX.FOCO}]
    assert (c["id"], c["nome"], c["cliente"], c["uf"], c["onde"]) == ("1", "U", "Cliente", "PI", "Cliente · PI")


def test_cartao_do_foco_no_plural_e_com_o_mais_perto(leituras):
    tudo_lido(leituras, focos=[foco_a(3.8, sat="NOAA-21"), foco_a(0.5, sat="GOES-19")])
    c = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["agir"][0]
    assert c["motivos"][0]["pill"] == "Fogo a 0,5 km" and c["motivos"][0]["principal"] == "Fogo a 0,5 km da usina"
    assert c["motivos"][0]["prova"] == "2 focos de queimada a até 5 km na última hora · visto pelo satélite GOES-19 às 14:50"


def test_cartao_do_aviso_tem_motivo_com_o_nivel_frase_principal_e_prova(leituras):
    # o nível vai pela palavra do INMET, com o que ela quer dizer (a cor fica na tela), e o evento leva o texto do explica.py
    v = so_a_usina(leituras, avisos=[aviso(2, evento="Tempestade")])
    assert v["agir"][0]["motivos"] == [{"tipo": "aviso", "pill": "Tempestade · Perigo",
                                        "principal": "Tempestade: Perigo (é provável que cause estrago)",
                                        "prova": "Quando: agora, até 23:00", **EX.evento("Tempestade")}]
    v = so_a_usina(leituras, avisos=[aviso(3, evento="Onda de Calor")])
    assert v["agir"][0]["motivos"][0]["pill"] == "Onda de calor · Grande Perigo"
    assert v["agir"][0]["motivos"][0]["principal"] == "Onda de calor: Grande Perigo (o nível mais alto: risco de grande estrago)"


def test_com_foco_e_aviso_o_foco_abre_e_os_avisos_que_mandam_agir_vem_depois_do_mais_grave(leituras):
    avisos = [aviso(2, evento="Vendaval"), aviso(3, evento="Granizo"), aviso(1, evento="Baixa Umidade")]
    c = so_a_usina(leituras, avisos=avisos, foco_km=1.0)["agir"][0]
    assert [m["tipo"] for m in c["motivos"]] == ["foco", "aviso", "aviso"]                      # o Perigo Potencial não é motivo
    assert [m["pill"] for m in c["motivos"]][1:] == ["Granizo · Grande Perigo", "Vendaval · Perigo"]
    assert c["contexto"][0].startswith("Também: Baixa umidade (Perigo Potencial)")


def test_contexto_traz_os_outros_avisos_e_o_risco_de_fogo(leituras):
    avisos = [aviso(2, evento="Tempestade"), aviso(1, evento="Baixa Umidade")]
    c = so_a_usina(leituras, avisos=avisos, risco=(1.0, 1.0, 1.0, 1.0))["agir"][0]
    assert c["contexto"] == ["Também: Baixa umidade (Perigo Potencial), agora, até 23:00",
                             "Risco de fogo crítico de hoje a sex 09/10 (1,00)"]


def test_contexto_sem_risco_alto_diz_ate_onde_chega(leituras):
    c = so_a_usina(leituras, foco_km=1.0, risco=(0.5, 0.4, 0.3, 0.2))["agir"][0]
    assert c["contexto"] == ["Risco de fogo médio nos 4 dias da previsão (no máximo 0,50)"]


def test_contexto_quando_o_risco_nao_tem_dado_diz_por_que(leituras):
    tudo_lido(leituras, focos=[foco_a(1.0)], risco=lei_risco({"1": dias(None, None, None, None)}))
    c = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["agir"][0]
    assert c["contexto"] == ["Risco de fogo: sem dado (sem vegetação no entorno)"]
    tudo_lido(leituras, focos=[foco_a(1.0)], risco=lei_risco({"1": [Amostra(None, "fora_da_grade")] * 4}))
    c = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["agir"][0]
    assert c["contexto"] == ["Risco de fogo: fora da grade do Instituto Nacional de Pesquisas Espaciais (INPE)"]


def test_contexto_sem_leitura_do_risco_nao_inventa_numero(leituras):
    leituras(avisos=lei_avisos(), focos=lei_focos(foco_a(1.0)))                     # o risco está fora
    c = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["agir"][0]
    assert c["contexto"] == ["Risco de fogo: sem leitura do Instituto Nacional de Pesquisas Espaciais (INPE)"]


@pytest.mark.parametrize("valores,frase", [
    ((1.0, 1.0, 1.0, 1.0), "Risco de fogo crítico de hoje a D+3 (1,00)"),
    ((0.8, 0.9, 0.1, 0.1), "Risco de fogo alto hoje e D+1 (0,90)"),
    ((0.1, 0.1, 0.8, 0.1), "Risco de fogo alto em D+2 (0,80)"),
    ((0.1, 0.8, 0.8, 0.8), "Risco de fogo alto de D+1 a D+3 (0,80)"),
    ((0.99, 0.8, 0.1, 0.1), "Risco de fogo crítico hoje (0,99); alto em D+1"),
    ((0.8, 0.1, 0.97, 0.1), "Risco de fogo crítico em D+2 (0,97); alto hoje"),
    ((0.8, 0.1, 0.8, 0.1), "Risco de fogo alto hoje e D+2 (0,80)"),
    ((0.1, 0.1, 0.8, 0.8), "Risco de fogo alto em D+2 e D+3 (0,80)"),
    ((0.8, 0.8, 0.1, 0.8), "Risco de fogo alto hoje, D+1 e D+3 (0,80)"),
    ((0.1, 0.8, 0.8, 0.1), "Risco de fogo alto em D+1 e D+2 (0,80)"),
    ((0.5, 0.4, 0.3, 0.2), "Risco de fogo médio nos 4 dias da previsão (no máximo 0,50)"),
    ((0.1, 0.1, 0.1, 0.1), "Risco de fogo mínimo nos 4 dias da previsão (no máximo 0,10)"),
])
def test_frase_do_risco_de_fogo(valores, frase):
    rotulos = ["Hoje", "D+1", "D+2", "D+3"]
    assert V.frase_do_risco([V.celula_de_risco(i, a, rotulos) for i, a in enumerate(dias(*valores))]) == frase


def test_frase_do_risco_com_o_arquivo_de_ontem_usa_os_rotulos_do_calendario():
    rotulos = ["Ontem", "Hoje", "D+1", "D+2"]
    cels = [V.celula_de_risco(i, a, rotulos) for i, a in enumerate(dias(0.8, 0.8, 0.1, 0.1))]
    assert V.frase_do_risco(cels) == "Risco de fogo alto ontem e hoje (0,80)"


def test_frase_do_risco_sem_numero_nenhum_nao_inventa():
    rotulos = ["Hoje", "D+1", "D+2", "D+3"]
    assert V.frase_do_risco([V.celula_de_risco(i, a, rotulos) for i, a in enumerate(dias(None, None, None, None))]) is None


# ── a grade por UF: 27 quadrados, um número e uma cor por estado ─────────────────────────────────────────────────────

POSICOES = {"RR": (2, 1), "AP": (4, 1), "AM": (2, 2), "PA": (3, 2), "MA": (4, 2), "CE": (5, 2), "RN": (6, 2), "AC": (1, 3),
            "RO": (2, 3), "TO": (3, 3), "PI": (4, 3), "PE": (5, 3), "PB": (6, 3), "MT": (2, 4), "GO": (3, 4), "BA": (4, 4),
            "AL": (5, 4), "SE": (6, 4), "MS": (2, 5), "DF": (3, 5), "MG": (4, 5), "ES": (5, 5), "PR": (2, 6), "SP": (3, 6),
            "RJ": (4, 6), "SC": (2, 7), "RS": (2, 8)}


def test_a_grade_tem_as_27_ufs_nas_posicoes_do_desenho_aprovado():
    assert V.UFS_GRADE == POSICOES and len(set(V.UFS_GRADE.values())) == 27
    assert all(1 <= c <= 7 and 1 <= r <= 8 for c, r in V.UFS_GRADE.values())


def usinas_em_ufs(*pares):
    """[(uf, nome)] em pontos distintos de uma faixa de latitude, todos dentro do aviso GRANDE."""
    return [usina(str(i + 1), nome, -4.2 - i * 0.05, -45.0, uf=uf) for i, (uf, nome) in enumerate(pares)]


def tiles(v):
    return {t["uf"]: t for t in v["ufs"]}


def test_a_grade_conta_usinas_com_alerta_por_estado_e_pega_a_cor_do_pior(leituras):
    usinas = usinas_em_ufs(("PA", "A"), ("PA", "B"), ("BA", "C"), ("BA", "D"), ("SP", "E"))      # lat -4,20 -4,25 -4,30 -4,35 -4,40
    avisos = [aviso(2, evento="Vendaval", geo=em_volta(-4.2, -45.0, 0.03)),            # só a usina A (agir)
              aviso(1, evento="Baixa Umidade", geo=em_volta(-4.30, -45.0, 0.08))]       # B, C e D (atenção); a E fica de fora
    tudo_lido(leituras, avisos, risco=lei_risco({str(i): dias(0.1, 0.1, 0.1, 0.1) for i in range(1, 6)}))
    v = V.montar({}, cadastro=cadastro(*usinas), ref=REF)
    t = tiles(v)
    assert (t["PA"]["n"], t["PA"]["nivel"], t["PA"]["texto"]) == (2, "agir", "2")      # A agir, B atenção: o pior colore
    assert (t["BA"]["n"], t["BA"]["nivel"]) == (2, "atencao")
    assert (t["SP"]["n"], t["SP"]["nivel"], t["SP"]["texto"]) == (0, "", "·")          # usina sem alerta não entra na conta
    assert (t["RS"]["n"], t["RS"]["nivel"], t["RS"]["texto"]) == (0, "", "·")          # estado sem usina nenhuma
    assert len(v["ufs"]) == 27
    assert t["PA"]["titulo"] == "PA: 2 usinas com alerta, 1 para agir agora"
    assert t["BA"]["titulo"] == "BA: 2 usinas com alerta" and t["RS"]["titulo"] == "RS: sem usina com alerta"


def test_a_grade_no_singular_e_na_ordem_de_leitura(leituras):
    usinas = usinas_em_ufs(("PI", "A"))
    tudo_lido(leituras, [aviso(3, geo=em_volta(-4.2, -45.0, 0.03))], risco=lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1)}))
    v = V.montar({}, cadastro=cadastro(*usinas), ref=REF)
    assert tiles(v)["PI"]["titulo"] == "PI: 1 usina com alerta, 1 para agir agora"
    ordem = [(t["row"], t["col"]) for t in v["ufs"]]
    assert ordem == sorted(ordem) and (tiles(v)["PI"]["col"], tiles(v)["PI"]["row"]) == (4, 3)


def test_uf_escrita_em_minuscula_ou_com_espaco_vale(leituras):
    usinas = [usina("1", "A", -4.2, -45.0, uf=" pa "), usina("2", "B", -4.3, -45.0, uf="Ba")]
    tudo_lido(leituras, [aviso(1, geo=GRANDE)], risco=lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1), "2": dias(0.1, 0.1, 0.1, 0.1)}))
    t = tiles(V.montar({}, cadastro=cadastro(*usinas), ref=REF))
    assert t["PA"]["n"] == 1 and t["BA"]["n"] == 1


def test_usina_com_alerta_e_uf_invalida_nao_some_a_grade_diz_quantas(leituras):
    usinas = [usina("1", "A", -4.2, -45.0, uf=""), usina("2", "B", -4.3, -45.0, uf="Piauí"), usina("3", "C", -4.4, -45.0, uf="PI")]
    tudo_lido(leituras, [aviso(1, geo=GRANDE)], risco=lei_risco({str(i): dias(0.1, 0.1, 0.1, 0.1) for i in (1, 2, 3)}))
    v = V.montar({}, cadastro=cadastro(*usinas), ref=REF)
    assert v["ufs_sem_uf"] == 2 and tiles(v)["PI"]["n"] == 1
    assert sum(t["n"] for t in v["ufs"]) == 1


def test_a_grade_segue_o_filtro_de_cliente(leituras):
    usinas = [usina("1", "A", -4.2, -45.0, "X", uf="PA"), usina("2", "B", -4.3, -45.0, "Y", uf="BA")]
    tudo_lido(leituras, [aviso(1, geo=GRANDE)], risco=lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1), "2": dias(0.1, 0.1, 0.1, 0.1)}))
    t = tiles(V.montar({}, cadastro=cadastro(*usinas), ref=REF, cliente="Y"))
    assert t["BA"]["n"] == 1 and t["PA"]["n"] == 0


def test_a_legenda_do_estado_sem_alerta_nao_afirma_o_que_nao_foi_lido(leituras):
    tudo_lido(leituras)
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert v["ufs_legenda_sem"] == "sem usina com alerta" and tiles(v)["PI"]["titulo"] == "PI: sem usina com alerta"
    leituras(focos=lei_focos(), risco=lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1)}))               # INMET fora
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert v["ufs_legenda_sem"] == "sem usina com alerta nas fontes lidas"
    assert tiles(v)["PI"]["titulo"] == "PI: sem usina com alerta nas fontes lidas"


# ── "Atenção": as 20 primeiras e a lista inteira ─────────────────────────────────────────────────────────────────────

def varias_em_atencao(n):
    usinas = [usina(str(i), f"U{i:02d}", -4.2 - i * 0.01, -45.0) for i in range(1, n + 1)]
    return usinas, lei_risco({u.id: dias(0.1, 0.1, 0.1, 0.1) for u in usinas})


@pytest.mark.parametrize("n,todas,mostradas,resumida", [(25, False, 20, True), (25, True, 25, False), (20, False, 20, False),
                                                       (21, False, 20, True), (3, False, 3, False)])
def test_atencao_mostra_as_20_primeiras_e_todas_so_quando_pedido(leituras, n, todas, mostradas, resumida):
    usinas, risco = varias_em_atencao(n)
    tudo_lido(leituras, [aviso(1, geo=GRANDE)], risco=risco)
    v = V.montar({}, cadastro=cadastro(*usinas), ref=REF, todas=todas)
    assert (v["n_atencao"], len(v["atencao_linhas"]), v["atencao_resumida"]) == (n, mostradas, resumida)
    assert len(v["atencao"]) == n and [c["nome"] for c in v["atencao_linhas"]] == [f"U{i:02d}" for i in range(1, mostradas + 1)]


def test_a_linha_da_atencao_traz_o_aviso_o_foco_e_os_quatro_dias(leituras):
    tudo_lido(leituras, [aviso(1, evento="Baixa Umidade"), aviso(2, evento="Onda de Calor")], risco=lei_risco({"1": dias(1.0, 0.82, 0.1, None)}))
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    c = v["atencao_linhas"][0]
    assert [(a["evento"], a["cor"]) for a in c["avisos"]] == [("Onda de Calor", "laranja"), ("Baixa Umidade", "amarelo")]
    assert [(d["rotulo"], d["curto"], d["cor"]) for d in c["dias"]] == [("Hoje", "1,00", "c"), ("D+1", "0,82", "a"),
                                                                       ("D+2", "0,10", "n"), ("D+3", "—", "n")]
    # a célula diz com palavra que leu e não há (09/10/2026; antes "—"), o risco vai em palavra e o porquê cabe numa linha
    assert (v["aviso_vazio"], v["foco_vazio"]) == ("nenhum", "não")
    assert [d["palavra"] for d in c["dias"]] == ["Crítico", "Alto", "Mínimo", "—"]
    assert c["por_que"] == "Onda de calor (Perigo) · Baixa umidade (Perigo Potencial) · e mais 1"


def test_celula_vazia_diz_sem_leitura_quando_a_fonte_nao_foi_lida(leituras):
    leituras(risco=lei_risco({"1": dias(0.9, 0.1, 0.1, 0.1)}))                    # avisos e focos fora
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert (v["aviso_vazio"], v["foco_vazio"]) == ("sem leitura", "sem leitura")


# ── I1: a lista só diz "não há alerta" depois de ler tudo o que ela usa ──────────────────────────────────────────────

def _baixo():
    return lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1)})


def test_fonte_fora_e_sem_alerta_nao_diz_nenhuma_usina_para_agir_agora(leituras):
    leituras(focos=lei_focos(), risco=_baixo())                                     # o INMET está fora
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert v["alertas"] == [] and v["faltando"] == ["avisos do Instituto Nacional de Meteorologia (INMET)"] and v["lendo"] == []
    assert v["vazio_agir"] == "Sem leitura de avisos do Instituto Nacional de Meteorologia (INMET): não dá para dizer que não há alerta"
    assert v["vazio_atencao"] == "Sem leitura de avisos do Instituto Nacional de Meteorologia (INMET): não dá para dizer que não há alerta"
    assert v["completa"] is False


def test_fonte_lendo_nao_e_fonte_fora_e_a_tela_volta_em_10_s(leituras):
    leituras(avisos=L.Leitura(None, None, erro=L.LENDO), focos=lei_focos(), risco=_baixo())
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert v["lendo"] == ["avisos do Instituto Nacional de Meteorologia (INMET)"] and v["faltando"] == []
    assert v["vazio_agir"].startswith("Sem leitura de avisos do Instituto Nacional de Meteorologia (INMET)")
    assert v["recarrega_em"] == 10


def test_uma_fonte_fora_e_outra_lendo_aparecem_cada_uma_na_sua_lista(leituras):
    leituras(avisos=L.Leitura(None, None, erro=L.LENDO), focos=L.Leitura(None, None, erro="HTTP 500"), risco=_baixo())
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert v["lendo"] == ["avisos do Instituto Nacional de Meteorologia (INMET)"] and v["faltando"] == ["focos de queimada do Instituto Nacional de Pesquisas Espaciais (INPE)"]
    assert v["vazio_agir"] == "Sem leitura de avisos do Instituto Nacional de Meteorologia (INMET) e focos de queimada do Instituto Nacional de Pesquisas Espaciais (INPE): não dá para dizer que não há alerta"
    assert v["vazio_atencao"] == "Sem leitura de avisos do Instituto Nacional de Meteorologia (INMET): não dá para dizer que não há alerta"     # o atenção não usa os focos


def test_tudo_lido_e_sem_alerta_pode_dizer_que_nao_ha(leituras):
    leituras(avisos=lei_avisos(), focos=lei_focos(), risco=_baixo())
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert v["vazio_agir"] == "Nenhuma usina para agir agora" and v["vazio_atencao"] == "Nenhuma usina em atenção"
    assert v["completa"] is True and v["recarrega_em"] == 60 and v["lendo"] == []


def test_leitura_velha_sem_alerta_nao_diz_que_nao_ha_sem_ressalva(leituras):
    velha = L.Leitura({"avisos": [], "ignorados": [], "lidos": 0}, LIDO - 3600, erro="tempo esgotado", velha=True)
    leituras(avisos=velha, focos=lei_focos(), risco=_baixo())
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert v["vazio_agir"] == "Nenhuma usina para agir agora nas leituras disponíveis (veja o estado das fontes)"
    assert v["vazio_atencao"] == "Nenhuma usina em atenção nas leituras disponíveis (veja o estado das fontes)"
    assert faixa(v)["sem"]["sub"] == "nas fontes lidas" and faixa(v)["sem"]["valor"] == "1"


def test_o_vazio_de_cada_secao_so_olha_as_fontes_que_ela_usa(leituras):
    # o INPE (risco) velho não atrapalha o "agir agora" (que vive de avisos e focos), mas atrapalha o "atenção"
    velha = L.Leitura({"por_ponto": {"1": dias(0.1, 0.1, 0.1, 0.1)}, "arquivos": {0: datetime(2026, 10, 6, 9, 32, tzinfo=UTC)}, "erros": {}},
                      LIDO - 3600, erro="tempo esgotado", velha=True)
    leituras(avisos=lei_avisos(), focos=lei_focos(), risco=velha)
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert v["vazio_agir"] == "Nenhuma usina para agir agora"
    assert v["vazio_atencao"] == "Nenhuma usina em atenção nas leituras disponíveis (veja o estado das fontes)"
    leituras(avisos=lei_avisos(), focos=lei_focos())                                 # o risco fora
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert v["vazio_agir"] == "Nenhuma usina para agir agora"
    assert v["vazio_atencao"] == "Sem leitura de risco de fogo do Instituto Nacional de Pesquisas Espaciais (INPE): não dá para dizer que não há alerta"


def test_com_usina_para_agir_o_vazio_nao_aparece_e_o_que_falta_continua_dito(leituras):
    leituras(focos=lei_focos(foco_a(1.0)), risco=lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1)}))
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert v["vazio_agir"] == "" and len(v["agir"]) == 1 and v["faltando"] == ["avisos do Instituto Nacional de Meteorologia (INMET)"]
    assert v["vazio_atencao"] == "Sem leitura de avisos do Instituto Nacional de Meteorologia (INMET): não dá para dizer que não há alerta"


# ── I3: degradação parcial não fica "ok", e a faixa do topo diz ──────────────────────────────────────────────────────

def test_aviso_ignorado_deixa_o_inmet_em_atencao_e_a_faixa_parcial(leituras):
    leituras(avisos=lei_avisos(aviso(2), ignorados=["aviso 7: sem polígono"]), focos=lei_focos(), risco=_baixo())
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    f = v["fontes"][0]
    assert f["estado"] == "atencao" and f["qualifica"] == ["parcial"] and "1 aviso foi ignorado" in f["detalhe"]
    fx = faixa(v)
    assert fx["agir"]["qual"] == ["avisos do Instituto Nacional de Meteorologia (INMET): parcial"] and fx["atencao"]["qual"] == ["avisos do Instituto Nacional de Meteorologia (INMET): parcial"] and fx["sem"]["qual"] == ["avisos do Instituto Nacional de Meteorologia (INMET): parcial"]
    assert fx["agir"]["valor"] == "1" and "cl-na" not in fx["agir"]["classe"]             # com alerta, a cor não vira "dúvida"
    assert fx["sem"]["sub"] == "nas fontes lidas"


def test_faixa_de_fonte_em_atencao_sem_alerta_nao_fica_verde(leituras):
    # "0" lido de uma fonte pela metade não é "tudo bem": âmbar, e com a razão
    leituras(avisos=lei_avisos(ignorados=["aviso 7: sem polígono"]), focos=lei_focos(), risco=_baixo())
    fx = faixa(V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF))
    assert (fx["agir"]["valor"], fx["agir"]["qual"]) == ("0", ["avisos do Instituto Nacional de Meteorologia (INMET): parcial"]) and "cl-na" in fx["agir"]["classe"]
    assert (fx["atencao"]["valor"], fx["atencao"]["qual"]) == ("0", ["avisos do Instituto Nacional de Meteorologia (INMET): parcial"]) and "cl-na" in fx["atencao"]["classe"]
    assert "cl-na" in fx["sem"]["classe"]


def test_fonte_parcial_com_usina_em_atencao_nao_pinta_o_numero_de_ambar(leituras):
    leituras(avisos=lei_avisos(ignorados=["aviso 7: sem polígono"]), focos=lei_focos(), risco=lei_risco({"1": dias(0.9, 0.1, 0.1, 0.1)}))
    fx = faixa(V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF))
    assert fx["atencao"]["valor"] == "1" and fx["atencao"]["qual"] == ["avisos do Instituto Nacional de Meteorologia (INMET): parcial"] and "cl-na" not in fx["atencao"]["classe"]


def test_leitura_velha_a_faixa_diz_de_que_hora_e_o_dado(leituras):
    velha = L.Leitura({"avisos": [aviso(2)], "ignorados": [], "lidos": 1}, LIDO - 3600, erro="tempo esgotado", velha=True)
    leituras(avisos=velha, focos=lei_focos(), risco=_baixo())
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert faixa(v)["agir"]["valor"] == "1" and faixa(v)["agir"]["qual"] == ["avisos do Instituto Nacional de Meteorologia (INMET): dado de 14:00"]
    assert v["fontes"][0]["qualifica"] == ["dado de 14:00"]
    sem = L.Leitura({"avisos": [], "ignorados": [], "lidos": 0}, LIDO - 3600, erro="tempo esgotado", velha=True)
    leituras(avisos=sem, focos=lei_focos(), risco=_baixo())
    fx = faixa(V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF))
    assert (fx["agir"]["valor"], fx["agir"]["qual"]) == ("0", ["avisos do Instituto Nacional de Meteorologia (INMET): dado de 14:00"]) and "cl-na" in fx["agir"]["classe"]


def test_arquivo_de_focos_que_falhou_deixa_os_focos_em_atencao_e_o_agir_parcial(leituras):
    leituras(avisos=lei_avisos(), focos=lei_focos(falhos=["b.csv"]), risco=_baixo())
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    f = v["fontes"][1]
    assert f["estado"] == "atencao" and "1 de 2 arquivos indisponíveis" in f["detalhe"]
    fx = faixa(v)
    assert fx["agir"]["qual"] == ["focos de queimada do Instituto Nacional de Pesquisas Espaciais (INPE): parcial"] and "cl-na" in fx["agir"]["classe"]
    assert fx["atencao"]["qual"] == [] and "cl-na" not in fx["atencao"]["classe"]          # o atenção não depende dos focos


def test_linhas_ilegiveis_nos_focos_deixam_em_atencao_e_dizem_quantas(leituras):
    leituras(avisos=lei_avisos(), focos=lei_focos(foco_a(1.0), ruins=3), risco=_baixo())
    f = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["fontes"][1]
    assert f["estado"] == "atencao" and "3 linhas ilegíveis" in f["detalhe"] and f["qualifica"] == ["parcial"]
    leituras(avisos=lei_avisos(), focos=lei_focos(foco_a(1.0), ruins=1), risco=_baixo())
    assert "1 linha ilegível" in V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["fontes"][1]["detalhe"]


def test_focos_atrasados_a_faixa_diz_ate_que_hora_vai_o_dado(leituras):
    leituras(avisos=lei_avisos(), focos=lei_focos(ate=datetime(2026, 10, 6, 17, 10, tzinfo=UTC)), risco=_baixo())      # 14:10
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert v["fontes"][1]["estado"] == "atencao"
    assert faixa(v)["agir"]["qual"] == ["focos de queimada do Instituto Nacional de Pesquisas Espaciais (INPE): arquivos até 14:10"] and "cl-na" in faixa(v)["agir"]["classe"]


def test_dia_do_risco_sem_leitura_deixa_o_atencao_parcial_e_o_dia_aparece_na_fonte(leituras):
    por = {"1": [Amostra(0.99, "ponto"), Amostra(0.99, "ponto"), Amostra(None, "indisponivel"), Amostra(0.99, "ponto")]}
    leituras(avisos=lei_avisos(), focos=lei_focos(), risco=lei_risco(por, erros={2: "HTTP 404"}))
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert faixa(v)["atencao"]["valor"] == "1" and faixa(v)["atencao"]["qual"] == ["risco de fogo do Instituto Nacional de Pesquisas Espaciais (INPE): parcial"]
    assert v["fontes"][2]["estado"] == "atencao" and v["fontes"][2]["detalhe"] == "D+2 indisponível (HTTP 404)"
    assert [d["curto"] for d in v["alertas"][0]["dias"]] == ["0,99", "0,99", "—", "0,99"]


def test_fonte_inteira_nao_ganha_qualificador(leituras):
    leituras(avisos=lei_avisos(aviso(2)), focos=lei_focos(foco_a(1.0)), risco=lei_risco({"1": dias(0.99, 0.1, 0.1, 0.1)}))
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert [f["qualifica"] for f in v["fontes"]] == [[], [], []] and [f["estado"] for f in v["fontes"]] == ["ok"] * 3
    assert all(faixa(v)[i]["qual"] == [] for i in ("agir", "atencao", "sem")) and v["completa"] is True


# ── M3: sem a data do arquivo do INPE ────────────────────────────────────────────────────────────────────────────────

def test_risco_sem_a_data_do_arquivo_fica_em_atencao_e_diz_por_que(leituras):
    leituras(avisos=lei_avisos(), focos=lei_focos(), risco=lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1)}, arquivos={0: None, 1: None}))
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    f = v["fontes"][2]
    assert f["estado"] == "atencao" and "sem data do arquivo" in f["texto"] and f["qualifica"] == ["sem data do arquivo"]
    assert faixa(v)["atencao"]["qual"] == ["risco de fogo do Instituto Nacional de Pesquisas Espaciais (INPE): sem data do arquivo"]


# ── M2: Hoje, D+1... pela data do calendário ─────────────────────────────────────────────────────────────────────────

def test_rotulos_dos_dias_pela_data_do_calendario():
    assert V.rotulos_dos_dias(datetime(2026, 10, 6, 9, 32, tzinfo=UTC), REF) == ["Hoje", "D+1", "D+2", "D+3"]
    assert V.rotulos_dos_dias(datetime(2026, 10, 5, 9, 32, tzinfo=UTC), REF) == ["Ontem", "Hoje", "D+1", "D+2"]
    assert V.rotulos_dos_dias(datetime(2026, 10, 3, 9, 32, tzinfo=UTC), REF) == ["03/10", "04/10", "Ontem", "Hoje"]
    assert V.rotulos_dos_dias(None, REF) == ["Hoje", "D+1", "D+2", "D+3"]                  # sem a data, assume que é de hoje
    assert V.rotulos_dos_dias(datetime(2026, 10, 6, 2, 30, tzinfo=UTC), REF)[0] == "Ontem"   # 02:30 UTC ainda é 23:30 de ontem


def test_com_o_arquivo_de_ontem_os_dias_da_usina_dizem_ontem_e_hoje(leituras):
    ontem = {0: datetime(2026, 10, 5, 9, 32, tzinfo=UTC)}
    leituras(avisos=lei_avisos(), focos=lei_focos(), risco=lei_risco({"1": dias(0.8, 0.9, 0.1, 0.1)}, arquivos=ontem))
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert [d["rotulo"] for d in v["alertas"][0]["dias"]] == ["Ontem", "Hoje", "D+1", "D+2"]


def test_dia_que_falhou_leva_o_rotulo_do_calendario_no_detalhe(leituras):
    ontem = {0: datetime(2026, 10, 5, 9, 32, tzinfo=UTC)}
    por = {"1": [Amostra(0.8, "ponto"), Amostra(None, "indisponivel"), Amostra(0.8, "ponto"), Amostra(0.8, "ponto")]}
    leituras(avisos=lei_avisos(), focos=lei_focos(), risco=lei_risco(por, arquivos=ontem, erros={1: "HTTP 404"}))
    assert V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["fontes"][2]["detalhe"] == "Hoje indisponível (HTTP 404)"


# ── M7: usina fora da grade do Instituto Nacional de Pesquisas Espaciais (INPE) ──────────────────────────────────────────────────────────────────────────────────

def test_usina_fora_da_grade_do_inpe_nos_quatro_dias_entra_na_lista_sem_risco_com_o_motivo(leituras):
    fora = [Amostra(None, "fora_da_grade")] * 4
    leituras(avisos=lei_avisos(), focos=lei_focos(),
             risco=lei_risco({"1": dias(None, None, None, None), "2": fora, "3": dias(0.1, 0.1, 0.1, 0.1)}))
    cad = cadastro(usina("1", "Sem vegetação", -5.0), usina("2", "Fora da grade", -5.5), usina("3", "Normal", -5.8))
    v = V.montar({}, cadastro=cad, ref=REF)
    assert v["sem_risco"] == [{"motivo": "sem vegetação no entorno", "nomes": ["Sem vegetação"]},
                              {"motivo": "fora da grade do Instituto Nacional de Pesquisas Espaciais (INPE)", "nomes": ["Fora da grade"]}]
    assert faixa(v)["cobertura"]["sub"] == "em operação com coordenada · 2 sem dado de risco"


def test_cartao_de_usina_fora_da_grade_diz_uma_vez_so(leituras):
    fora = [Amostra(None, "fora_da_grade")] * 4
    leituras(avisos=lei_avisos(aviso(2)), focos=lei_focos(), risco=lei_risco({"1": fora}))
    c = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["alertas"][0]
    assert c["risco_linha"] == "fora da grade do Instituto Nacional de Pesquisas Espaciais (INPE)"


def test_dias_misturados_nao_viram_uma_linha_so_e_nao_entram_na_lista_sem_risco(leituras):
    por = {"1": [Amostra(None, "sem_dado"), Amostra(0.9, "ponto"), Amostra(0.9, "ponto"), Amostra(0.9, "ponto")]}
    leituras(avisos=lei_avisos(), focos=lei_focos(), risco=lei_risco(por))
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    c = v["alertas"][0]
    assert c["risco_linha"] is None and [d["valor"] for d in c["dias"]][1:] == ["0,90"] * 3
    assert v["sem_risco"] == []

"""Clima e risco: o view-model da tela (`visao.montar`), com leituras prontas no lugar das fontes. Sem rede, sem Flask."""
import json
from datetime import datetime, timedelta, timezone

import pytest

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


def usina(id_, nome, lat=-5.0, lon=-45.0, cliente="Cliente"):
    return Usina(id_, nome, cliente, "PI", "Cidade", lat, lon)


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


# ── ordem por gravidade ──────────────────────────────────────────────────────────────────────────────────────────────

def test_ordem_pelo_pior_alerta_de_cada_usina(leituras):
    cad = cadastro(usina("1", "A Atencao", -5.0), usina("2", "B Alto", -5.1), usina("3", "C Critico", -5.2))
    leituras(avisos=lei_avisos(aviso(1, geo={"type": "Polygon", "coordinates": [[[-46, -5.05], [-44, -5.05], [-44, -4.9], [-46, -4.9], [-46, -5.05]]]})),
             risco=lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1), "2": dias(0.8, 0.1, 0.1, 0.1), "3": dias(0.99, 0.1, 0.1, 0.1)}))
    assert nomes(V.montar({}, cadastro=cad, ref=REF)) == ["C Critico", "B Alto", "A Atencao"]


def em_volta(lat, lon, meia=0.05):
    return {"type": "Polygon", "coordinates": [[[lon - meia, lat - meia], [lon + meia, lat - meia], [lon + meia, lat + meia],
                                                [lon - meia, lat + meia], [lon - meia, lat - meia]]]}


# Os desempates abaixo se provam um de cada vez: em cada cenário só UMA chave da ordem decide, e os nomes estão em ordem
# alfabética contrária à esperada, para o nome nunca ser quem acerta.

def test_desempate_foco_vem_antes_de_mais_tipos_de_alerta(leituras):
    cad = cadastro(usina("1", "A Aviso e risco", -5.0, -45.0), usina("2", "Z So foco", -5.0, -50.0))
    leituras(avisos=lei_avisos(aviso(3, geo=em_volta(-5.0, -45.0))), focos=lei_focos(foco_a(2.0, -5.0, -50.0)),
             risco=lei_risco({"1": dias(0.99, 0.1, 0.1, 0.1), "2": dias(0.1, 0.1, 0.1, 0.1)}))
    v = V.montar({}, cadastro=cad, ref=REF)
    assert [c["nivel"] for c in v["alertas"]] == [3, 3]                         # empatados no nível
    assert nomes(v) == ["Z So foco", "A Aviso e risco"]


def test_desempate_mais_tipos_de_alerta_primeiro(leituras):
    cad = cadastro(usina("1", "A So aviso", -5.0, -45.0), usina("2", "Z Aviso e risco", -5.0, -50.0))
    leituras(avisos=lei_avisos(aviso(2, geo=em_volta(-5.0, -45.0)), aviso(2, geo=em_volta(-5.0, -50.0))),
             risco=lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1), "2": dias(0.8, 0.1, 0.1, 0.1)}))
    v = V.montar({}, cadastro=cad, ref=REF)
    assert [c["nivel"] for c in v["alertas"]] == [2, 2]
    assert nomes(v) == ["Z Aviso e risco", "A So aviso"]


def test_desempate_o_aviso_mais_grave_primeiro(leituras):
    cad = cadastro(usina("1", "A Perigo Potencial", -5.0, -45.0), usina("2", "Z Perigo", -5.0, -50.0))
    leituras(avisos=lei_avisos(aviso(1, geo=em_volta(-5.0, -45.0)), aviso(2, geo=em_volta(-5.0, -50.0))),
             risco=lei_risco({"1": dias(0.99, 0.1, 0.1, 0.1), "2": dias(0.99, 0.1, 0.1, 0.1)}))
    v = V.montar({}, cadastro=cad, ref=REF)
    assert [c["nivel"] for c in v["alertas"]] == [3, 3]                         # os dois críticos pelo risco, com 2 tipos cada
    assert nomes(v) == ["Z Perigo", "A Perigo Potencial"]


def test_empate_o_foco_mais_perto_primeiro(leituras):
    cad = cadastro(usina("1", "A Longe", -5.0, -45.0), usina("2", "Z Perto", -5.0, -44.0))
    leituras(focos=lei_focos(foco_a(4.0, -5.0, -45.0), foco_a(0.5, -5.0, -44.0)))
    assert nomes(V.montar({}, cadastro=cad, ref=REF)) == ["Z Perto", "A Longe"]


def test_ultimo_desempate_e_o_nome_sem_acento_nem_caixa(leituras):
    cad = cadastro(usina("1", "zebra", -5.0), usina("2", "Árvore", -5.0), usina("3", "Mata", -5.0))
    leituras(risco=lei_risco({i: dias(0.9, 0.9, 0.9, 0.9) for i in "123"}))
    assert nomes(V.montar({}, cadastro=cad, ref=REF)) == ["Árvore", "Mata", "zebra"]


def test_risco_medio_nao_e_alerta_e_o_foco_e_sempre_critico(leituras):
    cad = cadastro(usina("1", "Medio"), usina("2", "Com foco", -5.0, -50.0))
    leituras(focos=lei_focos(foco_a(4.9, -5.0, -50.0)), risco=lei_risco({"1": dias(0.69, 0.5, 0.4, 0.2), "2": dias(0.1, 0.1, 0.1, 0.1)}))
    v = V.montar({}, cadastro=cad, ref=REF)
    assert nomes(v) == ["Com foco"] and v["alertas"][0]["nivel"] == 3 and v["alertas"][0]["rotulo"] == "Crítico"
    assert v["sem_alerta"] == 1


# ── fonte sem leitura: traço, nunca zero ─────────────────────────────────────────────────────────────────────────────

def test_fonte_sem_leitura_mostra_traco_e_as_outras_seguem(leituras):
    cad = cadastro(usina("1", "U"))
    leituras(risco=lei_risco({"1": dias(0.99, 0.1, 0.1, 0.1)}))               # avisos e focos sem leitura
    v = V.montar({}, cadastro=cad, ref=REF)
    por_id = {r["id"]: r for r in v["resumo"]}
    assert (por_id["avisos"]["valor"], por_id["avisos"]["classe"]) == ("—", "cl-nx")
    assert (por_id["focos"]["valor"], por_id["focos"]["sub"]) == ("—", "fonte fora")
    assert por_id["risco"]["valor"] == "1" and por_id["risco"]["classe"] == "cl-n3"
    assert [f["estado"] for f in v["fontes"]] == ["fora", "fora", "ok"]
    assert nomes(v) == ["U"]


def test_lista_diz_que_esta_incompleta_quando_falta_uma_fonte(leituras):
    leituras(risco=lei_risco({"1": dias(0.99, 0.1, 0.1, 0.1)}))               # sem avisos e sem focos
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert v["faltando"] == ["avisos do INMET", "focos do INPE"]
    leituras(avisos=lei_avisos(), focos=lei_focos(), risco=lei_risco({"1": dias(0.99, 0.1, 0.1, 0.1)}))
    assert V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["faltando"] == []
    velha = L.Leitura({"avisos": [], "ignorados": [], "lidos": 0}, LIDO - 3600, erro="tempo esgotado", velha=True)
    leituras(avisos=velha, focos=lei_focos(), risco=lei_risco({"1": dias(0.99, 0.1, 0.1, 0.1)}))
    assert V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["faltando"] == []     # a leitura velha ainda vale, com a hora dela


def test_zero_e_zero_quando_a_fonte_leu_e_nao_ha_alerta(leituras):
    leituras(avisos=lei_avisos(), focos=lei_focos(), risco=lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1)}))
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert [r["valor"] for r in v["resumo"]] == ["0", "0", "0"] and [r["classe"] for r in v["resumo"]] == ["cl-n0"] * 3
    assert v["alertas"] == [] and v["sem_alerta"] == 1


def test_fonte_lendo_diz_lendo(leituras):
    leituras(avisos=L.Leitura(None, None, erro=L.LENDO))
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert v["fontes"][0]["estado"] == "atencao" and "lendo a fonte" in v["fontes"][0]["texto"]


def test_leitura_velha_diz_fora_agora_e_a_hora_da_ultima_boa(leituras):
    velha = L.Leitura({"avisos": [], "ignorados": [], "lidos": 0}, LIDO - 3600, erro="tempo esgotado", velha=True)
    leituras(avisos=velha)
    f = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["fontes"][0]
    assert f["texto"] == "INMET fora agora; última leitura boa às 14:00" and f["detalhe"] == "tempo esgotado" and f["estado"] == "atencao"


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
    assert v["sem_usinas"] is True and v["sem_coordenada"] == ["Sem"] and v["resumo"] == [] and v["fontes"] == []


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


def test_resumo_do_risco_conta_por_dia_e_o_de_avisos_conta_os_em_vigor(leituras):
    cad = cadastro(usina("1", "A"), usina("2", "B", -5.5))
    futuro = aviso(2, inicio=REF + timedelta(hours=3), evento="Onda de Calor", geo={"type": "Polygon", "coordinates": [[[-46, -5.6], [-44, -5.6], [-44, -5.4], [-46, -5.4], [-46, -5.6]]]})
    so_a = {"type": "Polygon", "coordinates": [[[-46, -5.2], [-44, -5.2], [-44, -4.8], [-46, -4.8], [-46, -5.2]]]}
    leituras(avisos=lei_avisos(aviso(1, geo=so_a), futuro), risco=lei_risco({"1": dias(0.9, 0.9, 0.5, 0.5), "2": dias(0.5, 0.9, 0.9, 0.5)}))
    por_id = {r["id"]: r for r in V.montar({}, cadastro=cad, ref=REF)["resumo"]}
    assert (por_id["avisos"]["valor"], por_id["avisos"]["sub"]) == ("2", "1 em vigor agora")
    assert (por_id["risco"]["valor"], por_id["risco"]["sub"]) == ("2", "hoje 1 · D+1 2 · D+2 1 · D+3 0")


def test_previsao_de_dia_diferente_do_de_hoje_fica_em_atencao(leituras):
    ontem = {0: datetime(2026, 10, 5, 9, 32, tzinfo=UTC)}
    leituras(risco=lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1)}, arquivos=ontem))
    f = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["fontes"][2]
    assert f["estado"] == "atencao" and "previsão de 05/10 (arquivo das 06:32) · de ontem" in f["texto"]
    anteontem = {0: datetime(2026, 10, 3, 9, 32, tzinfo=UTC)}
    leituras(risco=lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1)}, arquivos=anteontem))
    assert "· de 03/10" in V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["fontes"][2]["texto"]


# ── I1: a lista só diz "não há alerta" depois de ler tudo ────────────────────────────────────────────────────────────

def _baixo():
    return lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1)})


def _cartoes(v):
    return {r["id"]: r for r in v["resumo"]}


def test_fonte_fora_e_sem_alerta_nao_diz_nenhuma_usina_com_alerta_agora(leituras):
    leituras(focos=lei_focos(), risco=_baixo())                                     # o INMET está fora
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert v["alertas"] == [] and v["faltando"] == ["avisos do INMET"] and v["lendo"] == []
    assert v["titulo_lista"] == "Sem leitura de avisos do INMET: não dá para dizer que não há alerta"
    assert v["sem_alerta_texto"] == "1 usina sem alerta nas fontes lidas."
    assert v["completa"] is False


def test_fonte_lendo_nao_e_fonte_fora_e_a_tela_volta_em_10_s(leituras):
    leituras(avisos=L.Leitura(None, None, erro=L.LENDO), focos=lei_focos(), risco=_baixo())
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert v["lendo"] == ["avisos do INMET"] and v["faltando"] == []
    assert v["titulo_lista"].startswith("Sem leitura de avisos do INMET")
    assert v["recarrega_em"] == 10


def test_uma_fonte_fora_e_outra_lendo_aparecem_cada_uma_na_sua_lista(leituras):
    leituras(avisos=L.Leitura(None, None, erro=L.LENDO), focos=L.Leitura(None, None, erro="HTTP 500"), risco=_baixo())
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert v["lendo"] == ["avisos do INMET"] and v["faltando"] == ["focos do INPE"]
    assert v["titulo_lista"] == "Sem leitura de avisos do INMET e focos do INPE: não dá para dizer que não há alerta"


def test_tudo_lido_e_sem_alerta_pode_dizer_agora(leituras):
    leituras(avisos=lei_avisos(), focos=lei_focos(), risco=_baixo())
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert v["titulo_lista"] == "Nenhuma usina com alerta agora" and v["sem_alerta_texto"] == "1 usina sem alerta agora."
    assert v["completa"] is True and v["recarrega_em"] == 60 and v["lendo"] == []


def test_leitura_velha_sem_alerta_nao_diz_agora(leituras):
    velha = L.Leitura({"avisos": [], "ignorados": [], "lidos": 0}, LIDO - 3600, erro="tempo esgotado", velha=True)
    leituras(avisos=velha, focos=lei_focos(), risco=_baixo())
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert v["titulo_lista"] == "Nenhuma usina com alerta nas leituras disponíveis (veja o estado das fontes)"
    assert v["sem_alerta_texto"] == "1 usina sem alerta nas fontes lidas."


def test_com_alerta_o_titulo_conta_e_continua_dizendo_que_falta_fonte(leituras):
    leituras(focos=lei_focos(), risco=lei_risco({"1": dias(0.99, 0.1, 0.1, 0.1)}))
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert v["titulo_lista"] == "Usinas com alerta (1), da mais grave para a menos" and v["faltando"] == ["avisos do INMET"]


# ── I3: degradação parcial não fica "ok", e os cartões do topo dizem ─────────────────────────────────────────────────

def test_aviso_ignorado_deixa_o_inmet_em_atencao_e_o_cartao_parcial(leituras):
    leituras(avisos=lei_avisos(aviso(2), ignorados=["aviso 7: sem polígono"]), focos=lei_focos(), risco=_baixo())
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    f = v["fontes"][0]
    assert f["estado"] == "atencao" and f["qualifica"] == ["parcial"] and "1 aviso foi ignorado" in f["detalhe"]
    c = _cartoes(v)["avisos"]
    assert c["sub"] == "1 em vigor agora · parcial" and c["classe"] == "cl-n2"       # com alerta, a cor segue a gravidade


def test_cartao_de_fonte_em_atencao_sem_alerta_nao_fica_verde(leituras):
    # "0" lido de uma fonte pela metade não é "tudo bem": âmbar, e com a razão
    leituras(avisos=lei_avisos(ignorados=["aviso 7: sem polígono"]), focos=lei_focos(), risco=_baixo())
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    c = _cartoes(v)
    assert (c["avisos"]["valor"], c["avisos"]["sub"], c["avisos"]["classe"]) == ("0", "nenhum aviso sobre as usinas · parcial", "cl-na")
    assert c["focos"]["classe"] == "cl-n0" and c["risco"]["classe"] == "cl-n0"          # as fontes inteiras seguem verdes


def test_leitura_velha_o_cartao_diz_de_que_hora_e_o_dado(leituras):
    velha = L.Leitura({"avisos": [aviso(2)], "ignorados": [], "lidos": 1}, LIDO - 3600, erro="tempo esgotado", velha=True)
    leituras(avisos=velha, focos=lei_focos(), risco=_baixo())
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    c = _cartoes(v)["avisos"]
    assert c["sub"] == "1 em vigor agora · dado de 14:00" and c["classe"] == "cl-n2"
    assert v["fontes"][0]["qualifica"] == ["dado de 14:00"]
    sem = L.Leitura({"avisos": [], "ignorados": [], "lidos": 0}, LIDO - 3600, erro="tempo esgotado", velha=True)
    leituras(avisos=sem, focos=lei_focos(), risco=_baixo())
    c = _cartoes(V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF))["avisos"]
    assert (c["valor"], c["sub"], c["classe"]) == ("0", "nenhum aviso sobre as usinas · dado de 14:00", "cl-na")


def test_arquivo_de_focos_que_falhou_deixa_os_focos_em_atencao_e_o_cartao_parcial(leituras):
    leituras(avisos=lei_avisos(), focos=lei_focos(falhos=["b.csv"]), risco=_baixo())
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    f = v["fontes"][1]
    assert f["estado"] == "atencao" and "1 de 2 arquivos indisponíveis" in f["detalhe"]
    c = _cartoes(v)["focos"]
    assert c["sub"] == "nenhum foco a até 5 km · parcial" and c["classe"] == "cl-na"


def test_linhas_ilegiveis_nos_focos_deixam_em_atencao_e_dizem_quantas(leituras):
    leituras(avisos=lei_avisos(), focos=lei_focos(foco_a(1.0), ruins=3), risco=_baixo())
    f = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["fontes"][1]
    assert f["estado"] == "atencao" and "3 linhas ilegíveis" in f["detalhe"] and f["qualifica"] == ["parcial"]
    leituras(avisos=lei_avisos(), focos=lei_focos(foco_a(1.0), ruins=1), risco=_baixo())
    assert "1 linha ilegível" in V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["fontes"][1]["detalhe"]


def test_focos_atrasados_o_cartao_diz_ate_que_hora_vai_o_dado(leituras):
    leituras(avisos=lei_avisos(), focos=lei_focos(ate=datetime(2026, 10, 6, 17, 10, tzinfo=UTC)), risco=_baixo())      # 14:10
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert v["fontes"][1]["estado"] == "atencao"
    c = _cartoes(v)["focos"]
    assert "arquivos até 14:10" in c["sub"] and c["classe"] == "cl-na"


def test_dia_do_risco_sem_leitura_aparece_com_traco_no_resumo_e_nunca_como_zero(leituras):
    por = {"1": [Amostra(0.99, "ponto"), Amostra(0.99, "ponto"), Amostra(None, "indisponivel"), Amostra(0.99, "ponto")]}
    leituras(avisos=lei_avisos(), focos=lei_focos(), risco=lei_risco(por, erros={2: "HTTP 404"}))
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    c = _cartoes(v)["risco"]
    assert c["sub"] == "hoje 1 · D+1 1 · D+2 — · D+3 1 · parcial" and c["classe"] == "cl-n3"
    assert v["fontes"][2]["estado"] == "atencao" and v["fontes"][2]["detalhe"] == "D+2 indisponível (HTTP 404)"


def test_fonte_inteira_nao_ganha_qualificador(leituras):
    leituras(avisos=lei_avisos(aviso(2)), focos=lei_focos(foco_a(1.0)), risco=lei_risco({"1": dias(0.99, 0.1, 0.1, 0.1)}))
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert [f["qualifica"] for f in v["fontes"]] == [[], [], []] and [f["estado"] for f in v["fontes"]] == ["ok"] * 3
    assert _cartoes(v)["avisos"]["sub"] == "1 em vigor agora" and v["completa"] is True


# ── M3: sem a data do arquivo do INPE ────────────────────────────────────────────────────────────────────────────────

def test_risco_sem_a_data_do_arquivo_fica_em_atencao_e_diz_por_que(leituras):
    leituras(avisos=lei_avisos(), focos=lei_focos(), risco=lei_risco({"1": dias(0.1, 0.1, 0.1, 0.1)}, arquivos={0: None, 1: None}))
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    f = v["fontes"][2]
    assert f["estado"] == "atencao" and "sem data do arquivo" in f["texto"] and f["qualifica"] == ["sem data do arquivo"]
    assert "sem data do arquivo" in _cartoes(v)["risco"]["sub"]


# ── M2: Hoje, D+1... pela data do calendário ─────────────────────────────────────────────────────────────────────────

def test_rotulos_dos_dias_pela_data_do_calendario():
    assert V.rotulos_dos_dias(datetime(2026, 10, 6, 9, 32, tzinfo=UTC), REF) == ["Hoje", "D+1", "D+2", "D+3"]
    assert V.rotulos_dos_dias(datetime(2026, 10, 5, 9, 32, tzinfo=UTC), REF) == ["Ontem", "Hoje", "D+1", "D+2"]
    assert V.rotulos_dos_dias(datetime(2026, 10, 3, 9, 32, tzinfo=UTC), REF) == ["03/10", "04/10", "Ontem", "Hoje"]
    assert V.rotulos_dos_dias(None, REF) == ["Hoje", "D+1", "D+2", "D+3"]                  # sem a data, assume que é de hoje
    assert V.rotulos_dos_dias(datetime(2026, 10, 6, 2, 30, tzinfo=UTC), REF)[0] == "Ontem"   # 02:30 UTC ainda é 23:30 de ontem


def test_com_o_arquivo_de_ontem_os_dias_do_cartao_e_do_resumo_dizem_ontem_e_hoje(leituras):
    ontem = {0: datetime(2026, 10, 5, 9, 32, tzinfo=UTC)}
    leituras(avisos=lei_avisos(), focos=lei_focos(), risco=lei_risco({"1": dias(0.8, 0.9, 0.1, 0.1)}, arquivos=ontem))
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    assert [d["rotulo"] for d in v["alertas"][0]["dias"]] == ["Ontem", "Hoje", "D+1", "D+2"]
    assert _cartoes(v)["risco"]["sub"].startswith("ontem 1 · hoje 1 · D+1 0 · D+2 0")


def test_dia_que_falhou_leva_o_rotulo_do_calendario_no_detalhe(leituras):
    ontem = {0: datetime(2026, 10, 5, 9, 32, tzinfo=UTC)}
    por = {"1": [Amostra(0.8, "ponto"), Amostra(None, "indisponivel"), Amostra(0.8, "ponto"), Amostra(0.8, "ponto")]}
    leituras(avisos=lei_avisos(), focos=lei_focos(), risco=lei_risco(por, arquivos=ontem, erros={1: "HTTP 404"}))
    assert V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["fontes"][2]["detalhe"] == "Hoje indisponível (HTTP 404)"


# ── M7: usina fora da grade do INPE ──────────────────────────────────────────────────────────────────────────────────

def test_usina_fora_da_grade_do_inpe_nos_quatro_dias_entra_na_lista_sem_risco_com_o_motivo(leituras):
    fora = [Amostra(None, "fora_da_grade")] * 4
    leituras(avisos=lei_avisos(), focos=lei_focos(),
             risco=lei_risco({"1": dias(None, None, None, None), "2": fora, "3": dias(0.1, 0.1, 0.1, 0.1)}))
    cad = cadastro(usina("1", "Sem vegetação", -5.0), usina("2", "Fora da grade", -5.5), usina("3", "Normal", -5.8))
    v = V.montar({}, cadastro=cad, ref=REF)
    assert v["sem_risco"] == [{"motivo": "sem vegetação no entorno", "nomes": ["Sem vegetação"]},
                              {"motivo": "fora da grade do INPE", "nomes": ["Fora da grade"]}]


def test_cartao_de_usina_fora_da_grade_diz_uma_vez_so(leituras):
    fora = [Amostra(None, "fora_da_grade")] * 4
    leituras(avisos=lei_avisos(aviso(2)), focos=lei_focos(), risco=lei_risco({"1": fora}))
    c = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)["alertas"][0]
    assert c["risco_linha"] == "fora da grade do INPE"


def test_dias_misturados_nao_viram_uma_linha_so_e_nao_entram_na_lista_sem_risco(leituras):
    por = {"1": [Amostra(None, "sem_dado"), Amostra(0.9, "ponto"), Amostra(0.9, "ponto"), Amostra(0.9, "ponto")]}
    leituras(avisos=lei_avisos(), focos=lei_focos(), risco=lei_risco(por))
    v = V.montar({}, cadastro=cadastro(usina("1", "U")), ref=REF)
    c = v["alertas"][0]
    assert c["risco_linha"] is None and [d["valor"] for d in c["dias"]][1:] == ["0,90"] * 3
    assert v["sem_risco"] == []

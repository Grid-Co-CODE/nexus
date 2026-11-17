"""O dossiê do cliente em .md, com as UFVs pontuadas (16/11/2026, Levi: "seria interessante o dossiê em .MD do cliente!
Pontuando as UFVs!"). A régua é a do mockup R18 mais a disponibilidade (a escolha do Levi: sem ela, a Capitão Poço 100,
com 85,3% e 26,4 h parada, saía "em dia"); uso interno; o botão no Comando › Usinas filtrado por um cliente.

Nada vai à rede: o dossiê é montado com linhas inventadas; a rota usa a tela de teste."""
import re
from datetime import datetime

from test_campo_responsaveis import tela  # noqa: F401  (tela é fixture)
from test_campo_visao import banco  # noqa: F401  (banco é fixture)
from test_comando_carteira_ia import _fontes, _linha

from nexus.comando import carteira_ia as CI
from nexus.comando import dossie_cliente as DC

AGORA = datetime(2026, 11, 16, 21, 57)


def _b(**k):
    base = {"disp": 99.5, "atingimento": 101.0, "estado": "normal", "desligamentos": 0, "atrasadas": 0, "urgentes": 0,
            "extintores": 0}
    return dict(base, **k)


def test_a_usina_sem_nada_fica_com_100():
    assert DC.pontuar(_b(), "novembro") == (100, [])
    assert DC.nivel(100) == "em dia"


def test_a_capitao_poco_perde_pela_disponibilidade():
    """O caso que fez a disponibilidade entrar: 85,3% no mês, meta em 91,5%, 3 extintores e 16 desligamentos. Pela régua
    do R18 sozinha dava 80 (em dia); com a disponibilidade, 67 (atenção)."""
    p, porque = DC.pontuar(_b(disp=85.3, atingimento=91.5, extintores=3, desligamentos=16), "novembro")
    assert porque == [("Meta de novembro em 91,5%", 2), ("Disponibilidade de novembro em 85,3%", 13),
                      ("3 extintores vencidos", 10), ("16 desligamentos em novembro", 8)]
    assert (p, DC.nivel(p)) == (67, "atenção")


def test_cada_regra_da_regua():
    assert DC.pontuar(_b(atingimento=10.0))[1] == [("Meta de mês em 10,0%", 35)]          # o teto da meta
    assert DC.pontuar(_b(disp=0.0))[1] == [("Disponibilidade de mês em 0,0%", 20)]       # o teto da disponibilidade
    assert DC.pontuar(_b(disp=None))[1] == [("Disponibilidade de mês sem publicar", 3)]
    assert DC.pontuar(_b(atingimento=None))[0] == 100                                   # sem meta: nada a tirar
    assert DC.pontuar(_b(estado="critico"))[1] == [("Crítico agora no COS", 20)]
    assert DC.pontuar(_b(estado="atencao"))[1] == [("Atenção agora no COS", 8)]
    assert DC.pontuar(_b(estado="sem_com"))[1] == [("Sem comunicação agora no COS", 6)]
    assert DC.pontuar(_b(estado="sem_leitura"))[0] == 100                               # sem leitura não pesa
    assert DC.pontuar(_b(urgentes=2, atrasadas=1))[1] == [("2 OS urgentes não iniciadas", 24), ("1 OS atrasada", 5)]
    assert DC.pontuar(_b(urgentes=None, atrasadas=None))[0] == 100                      # sem a fonte das OS
    assert DC.pontuar(_b(extintores=1))[1] == [("1 extintor vencido", 10)]
    assert DC.pontuar(_b(desligamentos=2))[0] == 100 and DC.pontuar(_b(desligamentos=3))[0] == 92
    # nunca abaixo de 0; os níveis
    assert DC.pontuar(_b(disp=0.0, atingimento=0.0, estado="critico", urgentes=5))[0] == 0
    assert [DC.nivel(p) for p in (80, 79, 55, 54)] == ["em dia", "atenção", "atenção", "risco"]


def test_o_dossie_do_cliente_poe_o_ranking_na_frente():
    dz = CI.montar([_linha(1, "Colíder 1", extintores_vencidos=1), _linha(2, "Colíder 2", atingimento=98.0, os_atrasadas=0,
                                                    conformidade=[])], _fontes(), AGORA)
    d = DC.montar("Renogrid", dz, AGORA)
    t = d["texto"]
    assert d["arquivo"] == "dossie-cliente-renogrid-2026-11-16.md"
    assert t.startswith("# Dossiê do cliente Renogrid") and "não é para mandar ao cliente" in t
    assert t.index("## 1. Pontuação das UFVs") < t.index("## 2. Resumo do cliente") < t.index("## 3. Usinas")
    assert "## 6. O que ficou de fora" in t and "- Por cliente:" not in t
    # a pior primeiro: a Colíder 1 com 0% de disponibilidade, meta 84,9%, 1 urgente, 1 atrasada e 1 extintor: 100 - 53
    (n1, p1, _v1, w1), (n2, p2, _v2, _w2) = d["ranking"]
    assert (n1, n2) == ("Colíder 1", "Colíder 2") and p1 < p2
    assert w1 == [("Meta de novembro em 84,9%", 6), ("Disponibilidade de novembro em 0,0%", 20),
                  ("1 OS urgente não iniciada", 12), ("1 OS atrasada", 5), ("1 extintor vencido", 10)] and p1 == 47
    assert f"| 1 | Colíder 1 | {p1} | risco |" in t
    assert "usinas sem leitura do COS agora: o estado não tirou pontos delas" in t
    assert "Fulano Responsável" not in t and "Pessoas: não constam" in t


def test_o_botao_e_a_rota_do_dossie_do_cliente(tela, logado):
    lista = logado.get("/t/comando/usinas").get_data(as_text=True)
    assert "filtre por um cliente" in lista and "dossie-do-cliente.md" not in lista
    sel = lista.split('name="cliente"', 1)[1].split("</select>", 1)[0]
    cliente = re.findall(r'<option value="([^"]+)"', sel)[0]
    filtrada = logado.get("/t/comando/usinas", query_string={"cliente": cliente}).get_data(as_text=True)
    assert "/t/comando/usinas/dossie-do-cliente.md?cliente=" in filtrada and f"Baixar o dossiê do cliente {cliente}" in filtrada
    r = logado.get("/t/comando/usinas/dossie-do-cliente.md", query_string={"cliente": cliente})
    assert r.status_code == 200 and r.mimetype == "text/markdown"
    assert r.headers["Content-Disposition"].startswith('attachment; filename="dossie-cliente-')
    t = r.get_data(as_text=True)
    assert t.startswith(f"# Dossiê do cliente {cliente}") and "## 1. Pontuação das UFVs" in t
    assert logado.get("/t/comando/usinas/dossie-do-cliente.md", query_string={"cliente": "Marte"}).status_code == 404
    assert logado.get("/t/comando/usinas/dossie-do-cliente.md").status_code == 404
    # uso interno: a conta do cliente não baixa
    with logado.session_transaction() as s:
        s["via"] = "cliente"
    assert logado.get("/t/comando/usinas/dossie-do-cliente.md", query_string={"cliente": cliente}).status_code in (302, 403)

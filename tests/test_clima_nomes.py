"""Os nomes das fontes por extenso (Levi, 09/10/2026, olhando o bloco "Fontes" do Mapa de risco: "Quero as fontes por extenso
também, não só sigla"). Um lugar só para os nomes (`fontes.NOMES`), usado pela lista do Clima e risco, pelo mapa (fontes, legendas e
dicas), pelo modo TV e pela página da usina. O que estes testes seguram: o nome por extenso não está escrito à mão em nenhum outro
arquivo do Nexus, e cada tela mostra o nome por extenso com a sigla, antes de qualquer sigla sozinha."""
import re
from pathlib import Path

import pytest

from nexus.performance.clima import fontes as F
from nexus.performance.clima import visao as V

from clima_mapa_mundo import REF, instalar_leituras, mundo_completo
from clima_mundo import mundo_usina  # noqa: F401 (a fixture da página da usina, com a NASA de mentira)
from clima_mundo import mundo  # noqa: F401 (a fixture da lista, com o INMET e o INPE de mentira)
from clima_mundo import pagina as pagina_lista, texto
from test_torre_performance_mapa import nova_app

RAIZ = Path(__file__).resolve().parent.parent
NOMES = {"inmet": "Instituto Nacional de Meteorologia", "inpe": "Instituto Nacional de Pesquisas Espaciais",
         "nasa_power": "Prediction Of Worldwide Energy Resources", "ibge": "Instituto Brasileiro de Geografia e Estatística",
         "nasa_firms": "Fire Information for Resource Management System"}


def test_cada_fonte_tem_nome_por_extenso_e_sigla():
    assert F.extenso("inmet") == "Instituto Nacional de Meteorologia (INMET)"
    assert F.extenso("inpe") == "Instituto Nacional de Pesquisas Espaciais (INPE)"
    assert F.extenso("ibge") == "Instituto Brasileiro de Geografia e Estatística (IBGE)"
    assert F.extenso("nasa_power") == "Prediction Of Worldwide Energy Resources, projeto da NASA (NASA POWER)"
    assert F.extenso("nasa_firms") == "Fire Information for Resource Management System, sistema da NASA (NASA FIRMS)"
    assert set(F.NOMES) == set(NOMES)


def test_o_nome_por_extenso_mora_so_no_fontes_py():
    """Escrever "Instituto Nacional de Meteorologia" em outro arquivo é ter dois lugares para o mesmo nome: um muda e o outro não."""
    achados = []
    for arq in sorted((RAIZ / "nexus").rglob("*")):
        if arq.suffix not in (".py", ".html", ".js", ".css") or "os_creator" in arq.parts or arq.name == "fontes.py":
            continue
        corpo = arq.read_text(encoding="utf-8", errors="replace")
        for nome in NOMES.values():
            if nome in corpo:
                achados.append(f"{arq.relative_to(RAIZ)}: {nome}")
    assert achados == [], "nome de fonte escrito à mão fora do fontes.py:\n" + "\n".join(achados)


def _primeira_sigla_vem_com_o_nome(t, sigla, nome):
    i = t.find(sigla)
    return i < 0 or t[max(0, i - len(nome) - 2):i] == f"{nome} ("


@pytest.fixture
def leituras(monkeypatch):
    return instalar_leituras(monkeypatch)


@pytest.mark.parametrize("consulta", [{}, {"fundo": "risco"}, {"fundo": "densidade"}, {"tv": "1"}])
def test_o_mapa_e_o_modo_tv_escrevem_o_nome_por_extenso_antes_de_qualquer_sigla(tmp_path, monkeypatch, leituras, consulta):
    _, c = nova_app(tmp_path)
    monkeypatch.setattr(V, "agora", lambda: REF)
    mundo_completo(leituras)
    html = c.get("/t/performance/clima/mapa", query_string=consulta).get_data(as_text=True)
    t = texto(html)
    for org, sigla in (("inmet", "INMET"), ("inpe", "INPE")):
        assert F.extenso(org) in t, (org, consulta)
        assert _primeira_sigla_vem_com_o_nome(t, sigla, F.nome_de(org)), (sigla, consulta, t[max(0, t.find(sigla) - 80):t.find(sigla) + 20])
    if not consulta.get("tv"):
        assert F.extenso("ibge") in t                                            # o contorno dos estados, no rodapé
    linhas = re.findall(r'<span class="cl-fonte-texto">([^<]*)', html)
    assert len(linhas) == 4 and linhas[0].startswith(F.extenso("inmet")) and linhas[1].startswith(F.extenso("inpe"))
    assert linhas[2].startswith(F.extenso("inpe")) and linhas[3].startswith(F.extenso("nasa_firms"))


def test_a_lista_do_clima_e_risco_escreve_o_nome_por_extenso(mundo):  # noqa: F811
    c, _sessao, _app = mundo
    t = texto(pagina_lista(c))
    for org, sigla in (("inmet", "INMET"), ("inpe", "INPE")):
        assert F.extenso(org) in t
        assert _primeira_sigla_vem_com_o_nome(t, sigla, F.nome_de(org)), sigla
    assert f"Dados: {F.extenso('inmet')} e {F.extenso('inpe')}, Programa Queimadas." in t


def test_a_pagina_da_usina_escreve_o_nome_da_nasa_power_por_extenso(mundo_usina):  # noqa: F811
    c = mundo_usina[0]
    t = texto(pagina_lista(c, "/t/performance/clima/usina/1"))
    assert F.extenso("nasa_power") in t and F.extenso("inmet") in t and F.extenso("inpe") in t
    assert _primeira_sigla_vem_com_o_nome(t, "NASA POWER", F.nome_de("nasa_power"))
    assert "NASA LaRC POWER" in t                                                 # a citação que a NASA pede continua no rodapé


def test_a_dica_do_mapa_cita_a_fonte_por_extenso(leituras):
    from clima_mapa_mundo import montar
    mundo_completo(leituras)
    fontes = {par[0] for u in montar()["dados_js"]["usinas"].values() for par in u["f"] if par[0]}
    assert fontes == {F.extenso("inmet"), F.extenso("inpe")}
    assert montar()["dados_js"]["nomes"]["inmet"] == F.extenso("inmet")

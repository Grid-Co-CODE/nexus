"""A Integração Fracttal dentro de Acessos, filtrando na própria página (25/10/2026). Levi: "melhore o desempenho da tela
de base > integração fractall cada pesquisa faz um carregamento novo na tabela que já está carregada. também gostaria que
não tivesse uma tela só para integração fractall e sim fosse para acessos". Medido antes (180 pessoas): cada busca ou
filtro recarregava a página inteira (319 KB: o campo Setor de cada linha levava a lista de setores toda) e a 1ª abertura
fria levava ~2,4 s. O que estes testes seguram: o endereço antigo leva à aba com os filtros; a aba de telas não lê o
Fracttal; todas as linhas vêm, com o que cada filtro olha, e as de fora do filtro do endereço chegam escondidas; o campo
Setor leve; e o Fracttal ligado às fichas guardado, renovado por trás quando vence. Nada vai ao Fracttal nem ao banco."""
import threading
import time

import pytest
from test_base_fracttal import PESSOAL, URL, com_fracttal, _visivel  # noqa: F401 (fixture)
from test_campo_visao import banco  # noqa: F401  (fixture)

from nexus.cadastro import setores as S
from nexus.cadastro import telas_fracttal as TF


@pytest.fixture(autouse=True)
def _limpo():
    S._CACHE.clear()
    TF.esquecer()
    yield
    S._CACHE.clear()
    TF.esquecer()


def test_o_endereco_antigo_leva_a_aba_com_os_filtros(banco, com_fracttal, logado):
    r = logado.get("/t/base/fracttal?q=beltrano&setor=sem&outra=x")
    assert r.status_code == 302 and r.headers["Location"].endswith("/t/base/acessos?aba=pessoas&q=beltrano&setor=sem")


def test_a_aba_de_telas_nao_le_o_fracttal_e_o_menu_nao_tem_mais_a_tela(banco, com_fracttal, logado):
    h = logado.get("/t/base/acessos").get_data(as_text=True)
    assert 'aria-current="page">Telas e administradores' in h and ">Pessoas e setores</a>" in h
    assert not com_fracttal                                                     # só a aba Pessoas lê o Fracttal
    assert "Integração Fracttal" not in h


def test_todas_as_linhas_vem_e_o_filtro_e_da_pagina(banco, com_fracttal, logado):
    logado.post("/t/base/fracttal/setores", data={"acao": "criar", "nome": "PCM"})
    logado.post("/t/base/fracttal/setor", data={"pessoa": "501", "setor_id": "1"}, headers={"Accept": "application/json"})
    h = logado.get(URL + "&setor=1&q=beltr").get_data(as_text=True)
    assert all(f'id="p-{p["id_personnel"]}"' in h for p in PESSOAL)            # as quatro vêm
    assert _visivel(h, 501) and not _visivel(h, 502) and not _visivel(h, 503)
    linha = h[h.index('id="p-501"'):h.index(">", h.index('id="p-501"'))]
    assert 'data-f-setor="1"' in linha and 'data-f-ligacao="ligadas"' in linha and 'data-f-origem="Externo"' in linha
    assert 'data-f-busca="beltrano supervisor beltrano@exemplo.test' in linha and linha.rstrip('"').endswith("pcm")
    sem = h[h.index('id="p-503"'):h.index(">", h.index('id="p-503"'))]
    assert 'data-f-setor="sem"' in sem and 'data-f-ligacao="sem_ficha"' in sem
    assert 'id="fr-filtros" data-filtro-local' in h and 'name="q"' in h and 'data-fl-texto="contem"' in h
    assert 'data-fl-conta="fr">1<' in h and "filtro-local.js" in h and "acessos-pessoas.js" in h
    assert 'onchange="this.form.submit()"' not in h                            # nenhum filtro recarrega a página


def test_o_campo_setor_vem_so_com_o_setor_da_linha(banco, com_fracttal, logado):
    for nome in ("PCM", "COS", "Performance"):
        logado.post("/t/base/fracttal/setores", data={"acao": "criar", "nome": nome})
    logado.post("/t/base/fracttal/setor", data={"pessoa": "501", "setor_id": "2"}, headers={"Accept": "application/json"})
    h = logado.get(URL).get_data(as_text=True)
    modelo = h[h.index('<template id="fr-opcoes">'):h.index("</template>")]
    assert all(f">{n}</option>" in modelo for n in ("PCM", "COS", "Performance"))

    def opcoes(pid):
        i = h.index(f'id="p-{pid}"')
        sel = h[h.index('class="gc-campo fr-setor-sel"', i):h.index("</select>", i)]
        return sel.count("<option")
    assert opcoes(501) == 2 and opcoes(502) == 1                               # "a definir" e o setor dela


def test_o_fracttal_ligado_as_fichas_fica_guardado_e_vence_por_tras(banco, com_fracttal, logado, monkeypatch):
    leituras, solta = [], threading.Event()
    certo = TF._relacao

    def relacao(cfg, lido):
        leituras.append(1)
        if len(leituras) > 1:
            solta.wait(5)                                                      # a releitura por trás demora
        return certo(cfg, lido)
    monkeypatch.setattr(TF, "_relacao", relacao)
    logado.get(URL)
    logado.get(URL + "&q=x")
    assert len(leituras) == 1                                                  # fresca: a cópia
    TF._TELA["g"]["t"] -= TF.RELACAO_S + 1
    t0 = time.monotonic()
    h = logado.get(URL).get_data(as_text=True)
    assert time.monotonic() - t0 < 2 and 'id="p-501"' in h                     # vencida: a cópia na hora
    logado.get(URL)                                                            # a releitura já está em curso: não abre outra
    solta.set()
    fim = time.monotonic() + 5
    while TF._TELA["renovando"]:
        assert time.monotonic() < fim
        time.sleep(0.02)
    assert len(leituras) == 2 and time.time() - TF._TELA["g"]["t"] < 5
    logado.get(URL + "&reler=1")                                               # o "Ler o Fracttal de novo" lê na hora
    assert len(leituras) == 3


def test_a_leitura_ruim_nao_fica_guardada(banco, com_fracttal, logado, monkeypatch):
    monkeypatch.setattr(TF, "_relacao", lambda cfg, lido: ({"linhas": [], "sem_conta": [], "ligadas": 0, "sem_ficha": 0,
                                                            "ambiguas": 0, "repetidas": 0}, "OSError: banco fora"))
    logado.get(URL)
    assert TF._TELA["g"] is None

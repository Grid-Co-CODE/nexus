"""O OS Creator abre sem esperar o Fracttal (14/10/2026, Levi: "quando clico no OS Creator, fica carregando por um bom
tempo"). A tela inicial esperava o selo "N atribuídas a você" (um pedido ao Fracttal, até 45 s com ele lento) e cada
abertura da Performance pedia de novo os planos e as subtarefas; com algumas pessoas juntas, as threads do Nexus ficavam
todas presas. Provas: a tela inicial sai sem pedir nada ao Fracttal e o navegador pede o selo depois (/api/selo, 2 min
por pessoa); a contagem das subtarefas fica 6 h na memória; erro não fica guardado. Nada vai à rede."""
import sys

import pytest

from nexus.torres.oscreator import ponte

pytest.importorskip("PyQt6")          # o clone importa o steps/ui.py do OS Creator ao montar a tela de Engenharia
if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
from os_web import lancador, perf_web, rotas  # noqa: E402
from test_oscreator_desempenho import _cliente, _memoria_limpa  # noqa: E402,F401  (fixture)


def test_a_tela_inicial_nao_pede_nada_ao_fracttal_e_o_selo_vem_depois(monkeypatch):
    monkeypatch.setattr(api, "contar_minhas_analises", lambda: pytest.fail("a tela inicial não pode esperar o Fracttal"))
    h = _cliente().get("/os/").get_data(as_text=True)
    assert "data-selo" in h and "hidden>" in h.split("data-selo", 1)[1][:160]
    assert "fetch('/os/api/selo'" in h


def test_o_selo_vem_da_api_uma_vez_a_cada_2_min_e_a_tela_seguinte_ja_o_traz(monkeypatch):
    vezes = []
    monkeypatch.setattr(api, "contar_minhas_analises", lambda: vezes.append(1) or 3)
    c = _cliente()
    for _ in range(2):
        assert c.get("/os/api/selo").get_json() == {"selo": lancador.texto_selo(3)}
    assert len(vezes) == 1
    h = c.get("/os/").get_data(as_text=True)
    assert lancador.texto_selo(3) in h and "hidden>" not in h.split("data-selo", 1)[1][:160]
    assert len(vezes) == 1                                                     # a tela não pediu de novo


def test_selo_com_o_fracttal_fora_e_vazio_e_nao_fica_guardado(monkeypatch):
    def fora():
        raise api.FracttalError("Fracttal lento")
    monkeypatch.setattr(api, "contar_minhas_analises", fora)
    monkeypatch.setattr(rotas.sessao, "morta", lambda: False)
    c = _cliente()
    assert c.get("/os/api/selo").get_json() == {"selo": ""}
    monkeypatch.setattr(api, "contar_minhas_analises", lambda: 2)
    assert c.get("/os/api/selo").get_json() == {"selo": lancador.texto_selo(2)}


def test_as_contagens_da_performance_ficam_6_h_na_memoria(monkeypatch):
    vezes = []
    monkeypatch.setattr(api, "load_assets_cached", lambda force=False: [])
    monkeypatch.setattr(perf_web, "contar_subtarefas", lambda assets: vezes.append(1) or {"Limpeza": ["a", "b"]})
    c = _cliente()
    for _ in range(3):
        assert c.get("/os/api/performance/contagens").get_json() == {"contagens": {"Limpeza": ["a", "b"]}}
    assert len(vezes) == 1 and rotas.CONTAGENS_TTL_S == 6 * 3600

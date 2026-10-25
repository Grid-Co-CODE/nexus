"""Três pedidos do Levi de 24/10/2026 na torre Chamados:
1 - "Tem como o logo da página do NEXUS no browser ser o logo branco da grid?": o ícone da aba do navegador;
2 - "Ordene as janelas de chamados em: Garantias, Fabricantes e Solicitação de Clientes";
3 - uma conta "da esse erro do anexo quando tenta salvar o nome de um ticket" ("Não gravou: O Fracttal recusou o
    checklist: WITHOUT PERMITS"): o ticket vai para a subtarefa da OS com a conta de QUEM ESTÁ LOGADO no Fracttal, e o
    perfil dessa conta não pode responder subtarefas. Não é o Nexus que libera: a mensagem passa a dizer o que fazer.

Nada vai à rede: o Fracttal é de mentira."""
import sys
from pathlib import Path

import pytest
from PIL import Image

from nexus.torres.chamados import TORRE
from nexus.torres.oscreator import ponte

ICONE = Path(__file__).resolve().parents[1] / "nexus" / "static" / "grid-icone-branco.png"


# ── 2: a ordem das telas ────────────────────────────────────────────────────────────────────────────────────────
def test_as_telas_de_chamados_na_ordem_garantias_fabricantes_solicitacoes():
    assert [t.id for t in TORRE.telas] == ["garantias", "fabricantes", "clientes"]


def test_o_menu_lateral_segue_a_ordem(logado):
    html = logado.get("/t/chamados/garantias").get_data(as_text=True)
    pos = [html.find('href="/t/chamados/%s"' % t) for t in ("garantias", "fabricantes", "clientes")]
    assert -1 not in pos and pos == sorted(pos)


# ── 1: o ícone da aba do navegador ──────────────────────────────────────────────────────────────────────────────
def test_o_icone_e_o_simbolo_branco_da_grid_num_quadrado():
    im = Image.open(ICONE).convert("RGBA")
    assert im.size[0] == im.size[1] >= 64
    # o símbolo é branco e opaco (o centro da barra horizontal do "G", à direita do meio)
    r, g, b, a = im.getpixel((int(im.size[0] * 0.85), int(im.size[1] * 0.56)))
    assert a == 255 and min(r, g, b) >= 245
    # e não some na aba clara do navegador: o fundo atrás do símbolo é escuro (o navy do Nexus), e não transparente
    r, g, b, a = im.getpixel((im.size[0] // 2, int(im.size[1] * 0.70)))
    assert a == 255 and max(r, g, b) <= 40


@pytest.mark.parametrize("rota", ["/", "/t/chamados/garantias"])
def test_as_paginas_do_nexus_levam_o_icone(logado, rota):
    html = logado.get(rota).get_data(as_text=True)
    assert '<link rel="icon" type="image/png" href="/static/grid-icone-branco.png">' in html


def test_a_entrada_tambem_leva_o_icone(cliente):
    html = cliente.get("/entrar").get_data(as_text=True)
    assert '<link rel="icon" type="image/png" href="/static/grid-icone-branco.png">' in html


# ── 3: o Fracttal que recusa o checklist pela permissão da conta ─────────────────────────────────────────────────
@pytest.fixture
def api_clone():
    pytest.importorskip("PyQt6")          # o clone importa o steps/ui.py do OS Creator ao montar a tela de Engenharia
    if ponte.RAIZ_CLONE not in sys.path:
        sys.path.append(ponte.RAIZ_CLONE)
    import api
    return api


def test_sem_permissao_no_checklist_diz_o_que_fazer(api_clone, monkeypatch):
    monkeypatch.setattr(api_clone, "_rpc_call", lambda rpc, params: {"success": False, "message": "WITHOUT_PERMITS"})
    with pytest.raises(api_clone.FracttalError) as e:
        api_clone.salvar_subtarefas(1, 2, [{"id_form_item": 3, "valor": "SR 90000001", "tipo": 1}])
    msg = str(e.value)
    assert "não tem permissão para responder as subtarefas" in msg
    assert "administrador do Fracttal" in msg and "(WITHOUT_PERMITS)" in msg


def test_outra_recusa_do_checklist_segue_como_era(api_clone, monkeypatch):
    monkeypatch.setattr(api_clone, "_rpc_call", lambda rpc, params: {"success": False, "message": "ALGO_NOVO"})
    with pytest.raises(api_clone.FracttalError) as e:
        api_clone.salvar_subtarefas(1, 2, [{"id_form_item": 3, "valor": "x", "tipo": 1}])
    assert str(e.value) == "O Fracttal recusou o checklist: ALGO NOVO"

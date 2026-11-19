"""O tipo de plano e o turno na Clonagem de planos do PCM (19/11/2026, `os_web/pcm_web.py`, `pcm.html`, `pcm.js`).

Sugestão de uma pessoa do PCM, pelo Sugestões do Nexus (OS Creator, "painel de Clonagem de planos para PCM"): "além da
família de plano, possamos também escolher o tipo de plano em lista suspensa, se é grid, [...] e os demais tipos
de plano de cliente das tarefas. Bem como, uma caixa de seleção se é atividade diurna (todas as atividades que não
contenham noturna ou noturno no título) ou noturna (que contém a palavra noturno ou noturna no título)".

O tipo é o que o plano traz entre colchetes no começo do nome ("[Grid Co.] - MPA - Inversor"): a lista sai dos planos
carregados, e não de uma lista escrita no código (cliente novo aparece sozinho). O que estes testes seguram: o tipo e a
chave dele (a mesma para grafias diferentes; o "+" separa), o turno pelo título, a lista de tipos com o Grid na frente,
o corpo do "Carregar planos" com o tipo e o turno de cada plano, e a tela com os dois filtros, que de saída ficam em
"(todos)": sem escolher nada, a tela é a de antes. Nomes de plano inventados (repositório público)."""
import sys
from pathlib import Path

import pytest

from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

from os_web import pcm_web as pcm  # noqa: E402

WEB = Path(ponte.RAIZ_CLONE, "os_web")


def _p(idt, desc, aid=11, family="MPA"):
    return {"id_task": idt, "description": desc, "family": family, "asset": {"id": aid}}


@pytest.mark.parametrize("desc, tipo", [
    ("[Grid Co.] - MPA - Inversor", "Grid Co."),
    ("  [Cliente A] - MPS - Transformador", "Cliente A"),
    ("[Cliente B+] - MPA - Inversor (noturno)", "Cliente B+"),
    ("Handover – Inversores", None),                       # sem colchetes: sem tipo
    ("MPA - Inversor [Grid Co.]", None),                   # só o do COMEÇO do nome é o tipo
    ("[] - MPA - Inversor", None),
    (None, None),
])
def test_o_tipo_e_o_que_vem_entre_colchetes_no_comeco(desc, tipo):
    assert pcm.tipo_do_plano(desc) == tipo


def test_a_chave_do_tipo_junta_grafias_e_o_mais_separa():
    assert pcm.chave_tipo("Grid Co.") == pcm.chave_tipo("GRID CO") == pcm.chave_tipo(" grid  co ")
    assert pcm.chave_tipo("Cliente B") != pcm.chave_tipo("Cliente B+")
    assert pcm.chave_tipo("Sérvia") == pcm.chave_tipo("servia")
    assert pcm.chave_tipo(None) == ""


@pytest.mark.parametrize("desc, turno", [
    ("[Grid Co.] - MPA - Inversor", "diurna"),
    ("[Grid Co.] - MPA - Inversor (Noturno)", "noturna"),
    ("[Grid Co.] - MPS - Termografia NOTURNA", "noturna"),
    ("[Grid Co.] - MPA - Inspeções noturnas", "noturna"),
    ("[Grid Co.] - MPA - Turno da noite", "diurna"),       # a regra do pedido é a palavra noturno ou noturna
    (None, "diurna"),
])
def test_o_turno_sai_do_titulo(desc, turno):
    assert pcm.turno_do_plano(desc) == turno


def test_a_lista_de_tipos_com_o_grid_na_frente_e_o_nome_mais_usado():
    planos = [_p(1, "[Cliente B] - MPA - Inversor"), _p(2, "[GRID CO] - MPA - Inversor"),
              _p(3, "[Grid Co.] - MPA - Inversor", aid=12), _p(4, "[Grid Co.] - MPS - Trafo", aid=12),
              _p(5, "[Cliente A] - MPA - Inversor"), _p(6, "Handover – Inversores", family="Handover")]
    assert pcm.tipos_ordenados(planos) == [{"chave": pcm.chave_tipo("Grid Co."), "nome": "Grid Co."},
                                           {"chave": pcm.chave_tipo("Cliente A"), "nome": "Cliente A"},
                                           {"chave": pcm.chave_tipo("Cliente B"), "nome": "Cliente B"}]
    assert pcm.tipos_ordenados([]) == []


def test_o_carregar_planos_leva_o_tipo_e_o_turno_de_cada_plano():
    planos = [_p(1, "[Grid Co.] - MPA - Inversor"), _p(2, "[Cliente A] - MPA - Inversor (noturno)"),
              _p(3, "Handover – Inversores", family="Handover"), _p(9, "Performance - Limpeza", family="PERFORMANCE")]
    corpo, pares = pcm.montar_planos(planos, [11])
    assert corpo["tipos"] == [{"chave": pcm.chave_tipo("Grid Co."), "nome": "Grid Co."},
                              {"chave": pcm.chave_tipo("Cliente A"), "nome": "Cliente A"}]
    por = {p["id_task"]: p for p in corpo["por_ativo"]["11"]}
    assert por[1]["tipo"] == pcm.chave_tipo("Grid Co.") and por[1]["turno"] == "diurna"
    assert por[2]["tipo"] == pcm.chave_tipo("Cliente A") and por[2]["turno"] == "noturna"
    assert por[3]["tipo"] == "" and por[3]["turno"] == "diurna"
    assert 9 not in por                                    # a família PERFORMANCE segue escondida do PCM
    # o que já ia continua indo, e os pares da contagem são os de antes (a 1ª família, o plano com "grid")
    assert por[1]["description"] == "[Grid Co.] - MPA - Inversor" and por[1]["family"] == "MPA"
    assert pares == [(3, 11)] and corpo["familia"] == "Handover"


def test_a_tela_tem_os_dois_filtros_e_o_script_filtra_por_eles():
    html = (WEB / "templates" / "pcm.html").read_text(encoding="utf-8")
    assert 'id="cb_tipo_plano"' in html and "Tipo de plano" in html
    assert 'id="cb_turno"' in html and ">Diurna<" in html and ">Noturna<" in html
    # de saída, "(todos)": sem escolher nada a tela é a de antes
    assert '<option value="" selected>(todos)</option>' in html.split('id="cb_turno"')[1].split("</select>")[0]
    js = (WEB / "static" / "pcm.js").read_text(encoding="utf-8")
    assert "p.tipo === tp" in js and "p.turno === tu" in js
    assert "cbTipoP.onchange = refresh" in js and "cbTurno.onchange = refresh" in js

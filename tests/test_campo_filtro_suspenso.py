"""O filtro suspenso das telas da Usinas 360° (10/11/2026; `nexus/static/campo-filtros.js`) e as contas do zoom do
percurso do Mapa de equipe (`nexus/static/campo-percurso.js`).

Levi, 10/11/2026: "Quero que o visual dos filtros de todas as seções do usinas 360° tenha a estrutura de filtros usando
como referência os filtros de histórico de OS, um filtro suspenso e simples". As Rondas já tinham esse modelo no próprio
template (03/11); as outras telas ganham o mesmo pelo script, que monta o botão Filtros, o painel com o Aplicar e as
etiquetas com as listas do formulário marcado com `data-fs`. O HTML do servidor não muda de regra: sem o script, cada
lista segue filtrando ao trocar."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent / "nexus"
TELAS = ("atencao", "ocorrencias", "equipe", "responsaveis", "aprovacao", "ranking")


@pytest.mark.parametrize("tela", TELAS)
def test_o_formulario_de_filtros_da_tela_usa_o_filtro_suspenso(tela):
    html = (RAIZ / "torres/campo/templates/campo" / f"{tela}.html").read_text(encoding="utf-8")
    form = re.search(r"<form[^>]* data-fs>.*?</form>", html, flags=re.S)
    assert form, tela
    assert "<select" in form.group(0)
    # o script vem logo depois do formulário (monta o painel antes de a tela aparecer, sem piscar as listas na barra)
    depois = html[form.end():form.end() + 700]
    assert "campo-filtros.js" in depois, tela


def test_as_rondas_seguem_com_o_modelo_no_template():
    html = (RAIZ / "torres/campo/templates/campo/rondas.html").read_text(encoding="utf-8")
    assert "data-rd-form" in html and "data-fs" not in html


def test_o_mes_do_ranking_fica_na_barra():
    html = (RAIZ / "torres/campo/templates/campo/ranking.html").read_text(encoding="utf-8")
    assert re.search(r'<select[^>]*name="mes"[^>]*data-fs-fora', html)


def test_o_script_do_filtro_usa_o_painel_das_rondas_e_so_vale_no_aplicar():
    js = (RAIZ / "static/campo-filtros.js").read_text(encoding="utf-8")
    css = (RAIZ / "static/campo.css").read_text(encoding="utf-8")
    for classe in ("rd-btn", "rd-badge", "rd-painel", "rd-grade", "rd-cel", "rd-rodape", "rd-etiquetas", "rd-etiqueta"):
        assert classe in js and f".{classe}" in css, classe
    assert 'removeAttribute("onchange")' in js            # a lista não filtra mais ao trocar: só no Aplicar
    assert ".fs-barra{position:relative}" in css and "fs-barra" in js


def test_as_contas_do_zoom_do_percurso():
    """As contas do zoom (as do Mapa de risco da Performance, com o mínimo da vista vindo do servidor), rodadas no node:
    a vista nunca sai do mapa nem passa do mínimo, o ponto sob o mouse fica parado, e o nível sai da largura em km."""
    node = shutil.which("node")
    if not node:
        pytest.skip("sem node nesta máquina")
    js = RAIZ / "static/campo-percurso.js"
    codigo = ("const m=require(process.argv[1]);const b=[0,0,1000,800];const n=[1200,500,150,40,8];"
              "console.log(JSON.stringify({fora:m.limitar([-50,-50,2000,0],b,5),perto:m.limitar([10,10,1,0],b,5),"
              "zoom:m.zoomEm(b,b,5,250,200,2),foco:m.enquadrar([100,100,104,101],b,5),"
              "niveis:[4200,1200,499,100,20,3].map(k=>m.nivelDa(k,n))}))")
    r = json.loads(subprocess.run([node, "-e", codigo, str(js)], capture_output=True, text=True, check=True).stdout)
    assert r["fora"] == [0, 0, 1000, 800]                              # mais largo que o mapa: o mapa inteiro
    assert r["perto"][2] == 5 and r["perto"][3] == 4                   # nunca menor que o mínimo, na proporção do mapa
    x, y, w, h = r["zoom"]
    assert (w, h) == (500, 400) and (250 - x) / w == pytest.approx(0.25) and (200 - y) / h == pytest.approx(0.25)
    fx, fy, fw, fh = r["foco"]
    assert fx <= 100 and fx + fw >= 104 and fy <= 100 and fy + fh >= 101 and fw / fh == pytest.approx(1.25)
    assert r["niveis"] == [0, 1, 2, 3, 4, 5]

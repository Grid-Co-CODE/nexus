"""O vídeo wall em satélite, a chuva parada no último quadro, a TV que se relê no lugar e o percurso que abre no lugar
(27/11/2026; `static/campo-mapa.js`, `static/campo-videowall.js`).

Levi, olhando o vídeo wall: "Deixa fixo em modo satélite. E esse GIF aí do clima, não precisa não, deixa sempre no
último, entendeu? [...] quando eu clicar no técnico, eu gostaria de ver o percurso [...] Quando eu clico no técnico, ele
atualiza o link para depois atualizar o percurso, não, ele atualiza o percurso direto."

O satélite fixo esbarrava na cota grátis da Esri (a opção A de 15/11/2026: a TV recarregava a página a cada 2 min e
baixava o satélite de novo a cada recarga). Agora a TV se relê no lugar (os dados trocam, o mapa fica) e recarrega a
página inteira só uma vez por hora: o satélite baixa uma vez por hora."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent / "nexus" / "static"


def _js(nome):
    return (RAIZ / nome).read_text(encoding="utf-8")


def _funcao(js: str, nome: str) -> str:
    """O corpo de `function nome(` até a próxima `function ` do mesmo nível (basta para os testes de texto)."""
    i = js.index(f"function {nome}(")
    f = js.find("\n  function ", i + 10)
    return js[i:f if f > 0 else len(js)]


def test_no_video_wall_o_satelite_e_fixo():
    """O vídeo wall abre e fica no satélite (sem o botão Mapa | Satélite); fora dele, a escolha segue guardada."""
    js = _js("campo-mapa.js")
    assert re.search(r'var fundoBase = D\.satelite \? \(D\.tv \? "satelite" : guardado\("nexus\.equipe\.base", "mapa"\)\) : "mapa";', js)
    tpl = (RAIZ.parent / "torres" / "campo" / "templates" / "campo" / "_equipe_mapa_ml.html").read_text(encoding="utf-8")
    seg = tpl[tpl.index('aria-label="Fundo do mapa"') - 200:tpl.index('aria-label="Fundo do mapa"')]
    assert "{% if not mapa_js.tv %}" in seg, "no vídeo wall o Mapa | Satélite não aparece: o satélite é fixo"


def test_no_video_wall_a_chuva_fica_no_ultimo_quadro():
    """A chuva do vídeo wall é o último quadro do radar, parado ("esse GIF aí do clima, não precisa não, deixa sempre no
    último"): sem tocar, sem a barra de tempo e só o último quadro pedido."""
    js = _js("campo-mapa.js")
    assert "radarTocar" not in _funcao(js, "tvTipo")
    carregar = _funcao(js, "radarCarregar")
    assert "radarTocar" not in carregar and "if (D.tv) q = q.slice(-1);" in carregar
    css = _js("campo.css")
    assert ".eqtv .eq-radar [data-eq-radar-tocar],.eqtv .eq-radar [data-eq-radar-quadro]{display:none}" in css


def test_o_video_wall_se_rele_no_lugar():
    """A releitura de 2 em 2 min troca os dados sem recarregar a página (o mapa, o satélite e o radar ficam); a recarga
    inteira é uma por hora (e pega o JS e o CSS novos de uma subida)."""
    vw = _js("campo-videowall.js")
    reler = _funcao(vw, "reler")
    # a releitura troca no lugar; a página inteira só recarrega se a troca quebrar (a página que veio diferente)
    assert "fetch(location.href" in reler and reler.count("location.reload()") == 1
    assert "try { trocar(html); } catch (e) { location.reload(); return; }" in reler
    assert "RELEITURAS_ATE_RECARREGAR = Math.max(1, Math.round(3600 / segundos))" in vw
    assert 'new CustomEvent("eqtv:dados"' in vw
    # a lista que rola sozinha para quando é trocada (senão cada releitura deixaria um laço rodando)
    assert "if (!caixa.isConnected) return;" in _funcao(vw, "rolar")
    js = _js("campo-mapa.js")
    assert 'document.addEventListener("eqtv:dados"' in js


def _node(codigo):
    node = shutil.which("node")
    if not node:
        pytest.skip("sem node nesta máquina")
    r = subprocess.run([node, "-e", codigo, str(RAIZ / "campo-mapa.js")], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def test_o_percurso_abre_no_lugar():
    """O clique no técnico (no mapa, na lista ou nos eventos) troca o painel e o percurso sem recarregar a página: só
    quando o endereço novo é o MESMO mapa com outro técnico, período ou painel (`trocaNoLugar`). Outro filtro, o clima,
    o Usinas, o vídeo wall ou outra tela seguem pelo link de sempre."""
    base = "https://app.exemplo/t/campo/equipe"
    casos = [
        (f"{base}?tecnico=5&de=2026-11-27T06:00&ate=2026-11-27T12:00&equipe=3", f"{base}?equipe=3", True),
        (f"{base}?painel=tecnicos&equipe=3", f"{base}?tecnico=5&equipe=3", True),
        (f"{base}?tecnico=5", f"{base}?tecnico=7&de=2026-11-26T06:00", True),
        (f"{base}?tecnico=5&clima=1", f"{base}", False),
        (f"{base}?ver=usinas", f"{base}?tecnico=5", False),
        (f"{base}?tecnico=5&tv=1", f"{base}", False),
        ("https://app.exemplo/t/campo/aprovacao?tecnico=5", f"{base}", False),
        ("https://outro.exemplo/t/campo/equipe?tecnico=5", f"{base}", False),
    ]
    codigo = ("const m=require(process.argv[1]);const c=" + json.dumps([[a, b] for a, b, _ in casos]) +
              ";console.log(JSON.stringify(c.map(x=>m.trocaNoLugar(x[0],x[1]))))")
    assert _node(codigo) == [esperado for _a, _b, esperado in casos]
    js = _js("campo-mapa.js")
    abrir = _funcao(js, "abrirNoLugar")
    assert "history.pushState" in abrir and "prepararReplay()" in abrir
    assert 'window.addEventListener("popstate"' in js
    # o clique no técnico do mapa também abre no lugar
    clique = js[js.index('mapa.on("click", "tecnicos"'):]
    clique = clique[:clique.index("});")]
    assert "abrirNoLugar(" in clique


# ── a lista dos técnicos abre o percurso do dia, como o ponto do mapa ─────────────────────────────────────────────────
from test_equipe_tela import EMAIL, NA_USINA, PCM, SEM_POSICAO, TECNICOS, _entrar, _html, banco, pontos, relogio, setor  # noqa: E402,F401


def test_a_lista_dos_tecnicos_abre_o_percurso_do_dia(cliente, pontos, setor):  # noqa: F811
    """Levi, 27/11/2026: "quando eu clicar no técnico, eu gostaria de ver o percurso que ele fez". O clique no ponto do
    mapa e nos eventos já abria o percurso do dia; o da lista abria só a ficha (sem o período). Agora a lista leva o
    mesmo endereço do ponto (`q_ponto`): o dia da última posição; quem não tem posição abre só a ficha, como antes."""
    _entrar(cliente, EMAIL[PCM])
    _, html = _html(cliente, query_string=TECNICOS)
    lista = html.split('<aside class="eq-lado', 1)[1]
    assert re.search(rf'href="/t/campo/equipe\?tecnico={NA_USINA}&amp;de=[^"&]+&amp;ate=[^"&]+"', lista)
    assert f'href="/t/campo/equipe?tecnico={SEM_POSICAO}"' in lista


def test_o_bloco_do_radar_leva_o_molde_sem_codificar():
    """Achado em 27/11/2026, na bancada: todo bloco do radar dava 404, porque o endereço passava inteiro pelo `new URL()`,
    que codifica as chaves do molde ({z} vira %7Bz%7D) e o MapLibre não trocava mais nada: a chuva do radar nunca
    aparecia (só a escala). O molde fica fora do URL() (`blocoDoRadar`), como as fontes já faziam."""
    r = _node("const m=require(process.argv[1]);console.log(JSON.stringify(m.blocoDoRadar('/t/campo/equipe/radar/',"
              "'/v2/radar/abc123','https://app.exemplo/t/campo/equipe?tv=1')))")
    assert r == "https://app.exemplo/t/campo/equipe/radar/v2/radar/abc123/256/{z}/{x}/{y}/8/1_1.png"
    assert "blocoDoRadar(D.radar.bloco, q.path, location.href)" in _js("campo-mapa.js")

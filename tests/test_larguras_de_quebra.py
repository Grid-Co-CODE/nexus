"""As larguras de quebra do CSS (o mapa do desembaraço, 08/11/2026): eram mais de 15 larguras diferentes (640, 900, 1100,
560, 760, 1000, 700, ...), cada tela com as suas, e o responsivo de uma tela não batia com o da vizinha.

O padrão está no `DESIGN.md`, seção 4: 480, 640, 820, 900, 1100 e 1180 (e o par de cada uma: `max-width:639px` com
`min-width:640px`). Este teste é a catraca: CSS novo só usa o padrão, e as larguras antigas, listadas abaixo arquivo por
arquivo, só podem diminuir (cada uma sai quando a tela for conferida a 375 px e no desktop com a largura padrão mais
perto). O clone da Zeladoria fica de fora (é a cópia de outro sistema).
"""
import collections
import re
from pathlib import Path

PADRAO = {480, 640, 820, 900, 1100, 1180}

# as que já existiam em 08/11/2026: a migrar, tela por tela (só diminuem)
LEGADO = {
    "nexus/static/cadastro.css": {560: 5, 760: 1, 980: 1},
    "nexus/static/campo.css": {560: 2, 600: 1, 700: 5, 760: 4, 800: 1, 860: 1, 980: 1, 1080: 1, 1280: 1, 1366: 1},
    "nexus/static/clima.css": {700: 1},
    "nexus/static/dados.css": {600: 1},
    "nexus/static/engenharia-folha.css": {600: 2},
    "nexus/static/engenharia.css": {600: 1, 980: 1, 1000: 1},
    "nexus/static/hseq.css": {1000: 1},
    "nexus/static/nexus.css": {760: 1},
    "nexus/static/ocorrencias.css": {760: 1, 1000: 1},
    "nexus/static/pcm-acomp.css": {700: 1, 1000: 1, 1200: 1},
    "nexus/static/pcm.css": {560: 1, 760: 1, 980: 1, 1200: 1},
    "nexus/torres/oscreator/os_creator/os_web/static/chamados.css": {980: 1, 1000: 3, 1200: 1},
    "nexus/torres/oscreator/os_creator/os_web/static/cos.css": {760: 1, 860: 2},
    "nexus/torres/oscreator/os_creator/os_web/static/inicio.css": {860: 1, 1000: 1, 1280: 1},
    "nexus/torres/oscreator/os_creator/os_web/static/os.css": {560: 2, 980: 1},
    "nexus/torres/oscreator/os_creator/os_web/static/os_acoes.css": {520: 1, 680: 1, 940: 1},
}


def _fora_do_padrao() -> dict:
    raiz = Path(__file__).resolve().parents[1]
    achadas = collections.defaultdict(collections.Counter)
    for p in sorted((raiz / "nexus").rglob("*.css")):
        rel = p.relative_to(raiz).as_posix()
        if "zeladoria/clone" in rel:
            continue
        texto = re.sub(r"/\*.*?\*/", "", p.read_text(encoding="utf-8"), flags=re.S)
        for consulta in re.findall(r"@media[^{]*", texto):
            for lado, w in re.findall(r"(max|min)-width:\s*(\d+)px", consulta):
                w = int(w)
                par = w + 1 if lado == "max" else w - 1        # max-width:639px com min-width:640px
                if w not in PADRAO and par not in PADRAO:
                    achadas[rel][w] += 1
    return achadas


def test_css_novo_usa_so_as_larguras_do_padrao():
    novas = []
    for arq, larguras in _fora_do_padrao().items():
        for w, n in larguras.items():
            antes = LEGADO.get(arq, {}).get(w, 0)
            if n > antes:
                novas.append(f"{arq}: {w}px ({n}, eram {antes})")
    assert not novas, ("largura de quebra fora do padrão (DESIGN.md, seção 4: 480, 640, 820, 900, 1100, 1180): "
                       + "; ".join(novas))


def test_a_lista_das_antigas_acompanha_o_que_saiu():
    """A largura antiga que saiu do CSS sai também do LEGADO (senão ela poderia voltar sem o teste ver)."""
    agora = _fora_do_padrao()
    sobras = [f"{arq}: {w}px" for arq, larguras in LEGADO.items() for w, n in larguras.items()
              if agora.get(arq, {}).get(w, 0) < n]
    assert not sobras, "tire do LEGADO o que saiu do CSS: " + "; ".join(sobras)

"""O CSS da Segurança fecha cada bloco que abre (25/11/2026). Ao juntar a `main` no pedido 44, o conflito no fim do
`hseq.css` (as tratativas de um lado, a tela Incidentes do outro) perdeu a chave que fechava o `@media (max-width:640px)`:
tudo o que vinha depois, inclusive o estilo dos Incidentes, passou a valer só no celular. O navegador não avisa; este
teste sim."""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent / "nexus" / "static"


def _profundidade(css: str) -> list[int]:
    """A profundidade das chaves ao fim de cada linha, sem os comentários e os textos entre aspas."""
    css = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), css, flags=re.S)
    css = re.sub(r'"[^"\n]*"|\'[^\'\n]*\'', '""', css)
    fundo, out = 0, []
    for linha in css.split("\n"):
        fundo += linha.count("{") - linha.count("}")
        assert fundo >= 0, f"chave fechada a mais na linha {len(out) + 1}"
        out.append(fundo)
    return out


def test_cada_bloco_do_css_da_seguranca_fecha():
    for arq in sorted(RAIZ.glob("hseq*.css")):
        p = _profundidade(arq.read_text(encoding="utf-8"))
        assert p[-1] == 0, f"{arq.name}: {p[-1]} bloco(s) sem fechar"


def test_o_teste_pega_o_media_sem_fechar():
    assert _profundidade("@media (max-width:640px){\n  .a{color:red}\n\n/* x { */\n.b{content:\"}\"}\n")[-1] == 1

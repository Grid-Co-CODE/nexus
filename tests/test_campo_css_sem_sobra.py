"""O CSS da torre Campo sem regra que nada usa (Levi, 18/10/2026: "pode excluir o que está sem uso"; as regras dos três
blocos de Onde focar sobraram quando a Visão geral tomou o lugar dele). Toda classe `cr-` do `campo.css` aparece num
template, num script ou no Python, inteira ou montada por prefixo (`cr-lin--{{ nivel }}`); a que não aparece é sobra."""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _fontes() -> str:
    out = []
    for p in [*RAIZ.joinpath("nexus").rglob("*.html"), *RAIZ.joinpath("nexus").rglob("*.js"),
              *RAIZ.joinpath("nexus").rglob("*.py")]:
        out.append(re.sub(r"\{#.*?#\}", "", p.read_text(encoding="utf-8", errors="ignore"), flags=re.S))
    return "\n".join(out)


def test_toda_classe_do_campo_css_e_usada():
    css = RAIZ.joinpath("nexus", "static", "campo.css").read_text(encoding="utf-8")
    fontes = _fontes()

    def usada(c):
        if re.search(r"(?<![\w-])" + re.escape(c) + r"(?![\w-])", fontes):
            return True
        m = re.match(r"(.*?(--|-))[a-z0-9]+$", c)
        return bool(m and re.search(r"(?<![\w-])" + re.escape(m.group(1)) + r"\{\{", fontes))
    sobras = sorted(c for c in set(re.findall(r"\.(cr-[a-z0-9-]+)", css)) if not usada(c))
    assert not sobras, f"classes do campo.css que nada usa: {sobras}"

"""A Paleta Nexus (04/11/2026): o tema escuro ao lado do claro, token a token, lidos do próprio nexus.css.

Levi, 04/11/2026, ao ver a comparação feita para decidir o cinza dos cartões do claro: "achei do caralho essa visão...
gostaria até que inserisse essa página ao clicar no nome da pessoa aparecer 'paleta nexus' só para os administradores".
Nada é guardado: a página lê os dois blocos de tokens do CSS a cada abertura, então mostra sempre o que está no ar. As
cores de texto trazem o contraste sobre o cartão (mínimo 4,5:1, a mesma conta do tests/test_tema.py).
"""
import re
from pathlib import Path

from flask import current_app

SELETOR_ESCURO = ':root,:root[data-tema="claro"] .topo{'
SELETOR_CLARO = ':root[data-tema="claro"]{'

GRUPOS = [
    ("Superfícies", "O fundo da página, o cartão e os tons dentro dele",
     ["fundo", "superficie", "superficie-2", "superficie-3", "barra", "linha", "linha-forte"], False),
    ("Texto", "Sobre o cartão (--superficie); a razão é o contraste, mínimo 4,5:1 para texto",
     ["tinta", "tinta-2", "mudo", "fraco"], True),
    ("Verde Grid", "A marca: o verde de área, o de texto e o de foco",
     ["verde", "verde-hover", "verde-suave", "verde-texto", "sobre-verde", "foco", "faixa-verde"], False),
    ("Semáforo (palavra)", "A cor da palavra de status, sobre o cartão",
     ["ok", "alerta", "severo", "critico", "erro", "info", "semcom", "laranja", "fogo-nasa"], True),
    ("Semáforo (fundo suave)", "O fundo da etiqueta de status",
     ["ok-suave", "alerta-suave", "severo-suave", "critico-suave", "info-suave", "semcom-suave"], False),
    ("Semáforo como área", "Barras e preenchimentos, com texto escuro por cima",
     ["ok-cheio", "lima-cheio", "alerta-cheio", "severo-cheio", "critico-cheio", "info-cheio", "sobre-cheio"], False),
    ("Pódio", "", ["ouro", "prata", "bronze"], False),
    ("Gráficos e mapa", "As séries e as rampas de calor",
     ["serie-sujidade", "serie-vegetacao", "serie-nasa", "serie-etm", "mapa-mar", "mapa-terra", "mapa-borda",
      "calor-risco-1", "calor-risco-2", "calor-risco-3", "calor-risco-4", "calor-risco-5",
      "calor-densidade-1", "calor-densidade-2", "calor-densidade-3", "calor-densidade-4", "calor-densidade-5"], False),
    ("Sombra, véu e rolagem", "", ["sombra", "veu", "contador-fundo", "rolagem", "rolagem-hover", "marca-fundo",
                                   "pessoa-padrao"], False),
]


def _bloco(css: str, seletor: str) -> dict:
    j = css.index("{", css.index(seletor))
    return dict(re.findall(r"--([\w-]+)\s*:\s*([^;]+);", css[j + 1:css.index("}", j)]))


def tokens() -> tuple[dict, dict]:
    """(o escuro, o claro) do nexus.css de agora; o claro herda do escuro o que não redefine."""
    css = (Path(current_app.static_folder) / "nexus.css").read_text(encoding="utf-8")
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    esc = {k: v.strip() for k, v in _bloco(css, SELETOR_ESCURO).items()}
    return esc, {**esc, **{k: v.strip() for k, v in _bloco(css, SELETOR_CLARO).items()}}


def _rgb(v: str):
    m = re.fullmatch(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})", v)
    if m:
        h = m.group(1)
        h = "".join(c * 2 for c in h) if len(h) == 3 else h
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)), 1.0
    m = re.fullmatch(r"rgba?\(([^)]+)\)", v)
    if m:
        p = [x.strip() for x in m.group(1).split(",")]
        return tuple(int(float(x)) for x in p[:3]), float(p[3]) if len(p) > 3 else 1.0
    return None, None


def _lum(c) -> float:
    def ch(x):
        x /= 255
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2])


def contraste(cor: str, fundo: str) -> float | None:
    """A razão de contraste da cor (composta sobre o fundo, se translúcida) com o fundo; None se não for cor simples."""
    c, a = _rgb(cor)
    f, _ = _rgb(fundo)
    if c is None or f is None:
        return None
    c = tuple(round(c[i] * a + f[i] * (1 - a)) for i in range(3))
    la, lb = sorted([_lum(c), _lum(f)], reverse=True)
    return round((la + 0.05) / (lb + 0.05), 1)


def grupos() -> tuple[dict, dict, list[dict]]:
    """(escuro, claro, os grupos com as linhas): cada linha com o valor de cada tema, o contraste das de texto e se é
    igual nos dois. O que não está em grupo nenhum vai no último, fechado."""
    esc, cla = tokens()
    vistos = {t for _, _, ts, _ in GRUPOS for t in ts}

    def lado(tema, nome, texto):
        cr = contraste(tema[nome], tema["superficie"]) if texto else None
        return {"valor": tema[nome], "cr": cr, "ruim": cr is not None and cr < 4.5, "fundo": tema["superficie"],
                "tinta": tema["tinta-2"]}

    def linhas(nomes, texto):
        return [{"nome": n, "texto": texto, "igual": esc[n].lower() == cla[n].lower(), "esc": lado(esc, n, texto),
                 "cla": lado(cla, n, texto)} for n in nomes if n in esc]
    out = [{"titulo": t, "sub": s, "linhas": linhas(ns, tx), "fechado": False} for t, s, ns, tx in GRUPOS]
    resto = [k for k in esc if k not in vistos]
    out.append({"titulo": f"As outras transparências e o papel ({len(resto)} tokens)", "sub": "",
                "linhas": linhas(resto, False), "fechado": True})
    return esc, cla, out

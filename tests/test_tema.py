"""Tema escuro (padrão) e claro (Levi, 08/10/2026: "precisamos de um tema claro também ... com calma para que não ocorra
bugs!").

O que estes testes seguram:
- o servidor desenha o <html data-tema> pelo cookie nexus_tema (sem piscar o tema errado), no Nexus e na tela de entrar;
- o botão do topo e a troca sem JavaScript (POST /tema), atrás do login, voltando para a mesma tela;
- as duas folhas de tokens do nexus.css completas (todo token do escuro tem par no claro) e o escuro igual ao de sempre;
- nenhuma cor fixa fora dos tokens nos .css do Nexus e no estilo dos templates; todo var(--x) usado existe;
- o contraste AA (4,5:1) das combinações de texto do tema claro.

Fora da varredura, de propósito:
- `nexus/torres/oscreator/os_creator/**`: a cópia idêntica do OS Creator do oem (o README de lá); ele segue no escuro dele;
- as cores de DADO que o servidor manda (a cor de cada pessoa no Quadro da equipe, a cor da etiqueta do Fracttal): são as
  mesmas nos dois temas, com texto escuro por cima;
- o estilo que a ponte da Performance injeta na página da Plataforma (nexus/performance/ponte.py): é da plataforma, escura.
"""
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
ESTATICO = RAIZ / "nexus" / "static"
SELETOR_ESCURO = ':root,:root[data-tema="claro"] .topo'
SELETOR_CLARO = ':root[data-tema="claro"]'

# O escuro de sempre: os valores de cada token no tema escuro. Os 19 primeiros são os do nexus.css de antes do tema claro;
# os outros são as cores que cada tela já usava escritas direto no CSS (a mesma cor, agora com nome). Mudar um valor aqui
# é mudar o escuro, que o Levi quer como está: só com pedido dele.
ESCURO_DE_SEMPRE = {
    "--fundo": "#090d18", "--superficie": "#161d30", "--superficie-2": "#1c2640", "--superficie-3": "#243154",
    "--barra": "#0d1526", "--tinta": "#e9eef6", "--tinta-2": "#c3cad7", "--mudo": "#96a0b4", "--fraco": "#767d92",
    "--linha": "rgba(255,255,255,.09)", "--linha-forte": "rgba(255,255,255,.16)", "--verde": "#a3d900",
    "--verde-hover": "#8bbf00", "--verde-suave": "rgba(163,217,0,.12)", "--verde-texto": "#c4e755",
    "--sobre-verde": "#191528", "--sobre-barra": "#fff", "--sobre-barra-mudo": "#a6adb4", "--foco": "#a3d900",
    "--verde-a16": "rgba(163,217,0,.16)", "--verde-a35": "rgba(163,217,0,.35)", "--verde-a40": "rgba(163,217,0,.4)",
    "--verde-a42": "rgba(163,217,0,.42)", "--verde-a45": "rgba(163,217,0,.45)", "--verde-a60": "rgba(163,217,0,.6)",
    "--ok": "#4ade80", "--ok-suave": "rgba(74,222,128,.14)", "--ok-a12": "rgba(74,222,128,.12)", "--alerta": "#ffd83d",
    "--alerta-suave": "rgba(255,216,61,.14)", "--alerta-a08": "rgba(255,216,61,.08)",
    "--alerta-a10": "rgba(255,216,61,.10)", "--alerta-a12": "rgba(255,216,61,.12)",
    "--alerta-a16": "rgba(255,216,61,.16)", "--alerta-a18": "rgba(255,216,61,.18)",
    "--alerta-a35": "rgba(255,216,61,.35)", "--alerta-a40": "rgba(255,216,61,.4)",
    "--alerta-a45": "rgba(255,216,61,.45)", "--alerta-a50": "rgba(255,216,61,.5)",
    "--alerta-a55": "rgba(255,216,61,.55)", "--alerta-a60": "rgba(255,216,61,.6)", "--severo": "#ff9f43",
    "--severo-suave": "rgba(255,159,67,.14)", "--laranja": "#ff9f5a", "--laranja-a16": "rgba(255,143,60,.16)",
    "--critico": "#ff5b6e", "--critico-suave": "rgba(255,91,110,.14)", "--critico-a12": "rgba(255,91,110,.12)",
    "--critico-a18": "rgba(255,91,110,.18)", "--critico-a30": "rgba(255,91,110,.30)",
    "--critico-a35": "rgba(255,91,110,.35)", "--critico-a45": "rgba(255,91,110,.45)", "--agir-tinta": "#fff",
    "--erro": "#ff7a7a", "--erro-cheio": "#ff7a7a", "--erro-a08": "rgba(255,122,122,.08)",
    "--erro-a42": "rgba(255,122,122,.42)", "--erro-a55": "rgba(255,122,122,.55)", "--info": "#7fb8ff",
    "--info-suave": "rgba(91,157,255,.14)", "--info-a10": "rgba(127,184,255,.10)",
    "--info-a42": "rgba(127,184,255,.42)", "--semcom": "#b39dff", "--semcom-suave": "rgba(179,157,255,.14)",
    "--ok-cheio": "#4ade80", "--lima-cheio": "#a8e05f", "--alerta-cheio": "#ffd83d", "--severo-cheio": "#ff8f3c",
    "--critico-cheio": "#ff5b6e", "--info-cheio": "#7fb8ff", "--sobre-cheio": "#0b1220", "--serie-sujidade": "#7fb8ff",
    "--serie-vegetacao": "#a3d900", "--serie-nasa": "#c3cad7", "--serie-etm": "#6ec1e4", "--mapa-mar": "#0d1526",
    "--mapa-terra": "#1c2640", "--mapa-borda": "rgba(255,255,255,.22)", "--mapa-sigla": "rgba(233,238,246,.42)",
    "--clarao-a04": "rgba(255,255,255,.04)", "--clarao-a05": "rgba(255,255,255,.05)",
    "--clarao-a08": "rgba(255,255,255,.08)", "--sombra": "rgba(0,0,0,.35)", "--veu": "rgba(9,13,24,.55)",
    "--contador-fundo": "rgba(0,0,0,.18)", "--cartao-brilho": "rgba(255,255,255,.05)",
    "--cartao-brilho-alto": "rgba(255,255,255,.06)", "--cartao-sombra": "rgba(0,0,0,.85)",
    "--cartao-sombra-alta": "rgba(0,0,0,.95)", "--rolagem": "#243154", "--rolagem-hover": "#34426b",
    "--pessoa-padrao": "#c7cede", "--marca-fundo": "#0d1526", "--foto-veu": "rgba(9,13,24,.92)",
    "--foto-etiqueta": "rgba(9,13,24,.78)", "--foto-tinta": "#fff", "--foto-legenda": "#e6e9f2",
    "--foto-borda": "rgba(255,255,255,.3)", "--foto-borda-hover": "#a3d900", "--papel": "#fff",
    "--papel-mudo": "#5b6475", "--papel-link": "#3d5c00",
}

COR = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(", re.I)
# nomes de cor do CSS que alguém escreveria à mão; transparent, currentColor, inherit e none não são cor fixa
NOMES_DE_COR = re.compile(r"(?<![\w-])(white|black|red|green|blue|yellow|orange|purple|gray|grey|silver|navy|teal|"
                          r"maroon|olive|lime|aqua|fuchsia|pink|brown|gold|violet|indigo|crimson|salmon|tomato)(?![\w-])",
                          re.I)


def _sem_comentarios(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _regras(css: str):
    """(seletor, corpo) de cada regra; a de dentro de um @media vem com o próprio seletor (o @media fica de fora)."""
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", _sem_comentarios(css)):
        seletor = " ".join(m.group(1).split())
        seletor = re.sub(r"^@media[^{]*$", "", seletor).strip()
        yield seletor, m.group(2)


def _declaracoes(corpo: str):
    for d in corpo.split(";"):
        if ":" in d:
            prop, valor = d.split(":", 1)
            yield prop.strip(), " ".join(valor.split())


def _tokens(seletor_procurado: str) -> dict:
    css = (ESTATICO / "nexus.css").read_text(encoding="utf-8")
    achados = [corpo for seletor, corpo in _regras(css) if seletor == seletor_procurado]
    assert len(achados) == 1, f"o nexus.css precisa de UM bloco {seletor_procurado!r}"
    return {p: v for p, v in _declaracoes(achados[0]) if p.startswith("--")}


def _css_do_nexus():
    return sorted(ESTATICO.glob("*.css"))


def _templates_do_nexus():
    pastas = [RAIZ / "nexus" / "templates"] + sorted((RAIZ / "nexus" / "torres").glob("*/templates"))
    for pasta in pastas:
        for t in sorted(pasta.rglob("*.html")):
            if "os_creator" not in t.parts:
                yield t


# ── o servidor desenha o tema ─────────────────────────────────────────────────────────────────────────────────────
def test_sem_cookie_o_tema_e_o_escuro(logado):
    html = logado.get("/").get_data(as_text=True)
    assert '<html lang="pt-BR" data-nexus data-tema="escuro">' in html
    assert '<span class="rotulo-tema">Tema: Escuro</span>' in html


def test_cookie_claro_desenha_o_claro_no_servidor(logado):
    logado.set_cookie("nexus_tema", "claro")
    for url in ("/", "/t/cos/mesa"):
        html = logado.get(url).get_data(as_text=True)
        assert '<html lang="pt-BR" data-nexus data-tema="claro">' in html, url
        assert '<span class="rotulo-tema">Tema: Claro</span>' in html, url


def test_cookie_desconhecido_cai_no_escuro(logado):
    logado.set_cookie("nexus_tema", "lilas")
    assert 'data-tema="escuro"' in logado.get("/").get_data(as_text=True)


def test_tela_de_entrar_segue_o_tema(cliente):
    assert '<html lang="pt-BR" data-tema="escuro">' in cliente.get("/entrar").get_data(as_text=True)
    cliente.set_cookie("nexus_tema", "claro")
    html = cliente.get("/entrar").get_data(as_text=True)
    assert '<html lang="pt-BR" data-tema="claro">' in html
    # a reserva do localStorage também vale antes do login
    assert 'localStorage.getItem("nexus.tema")' in html


# ── o botão e a troca ─────────────────────────────────────────────────────────────────────────────────────────────
def test_botao_do_tema_no_topo_diz_o_tema_de_agora(logado):
    html = logado.get("/t/campo/rondas?aba=painel").get_data(as_text=True)
    topo = html.split('<header class="topo">', 1)[1].split("</header>", 1)[0]
    assert 'class="troca-tema-form" method="post" action="/tema"' in topo
    assert '<input type="hidden" name="tema" value="claro">' in topo
    # a volta leva os filtros da tela (sem JavaScript o formulário passa pelo servidor)
    assert '<input type="hidden" name="voltar" value="/t/campo/rondas?aba=painel">' in topo
    assert 'aria-label="Tema: escuro. Trocar para o tema claro"' in topo
    assert 'class="tema-icone"' in topo and "Tema: Escuro" in topo
    # sem <svg> no topo: as telas com gráfico procuram o primeiro <svg> da página (o Mapa de risco quebrou com um ícone SVG)
    assert "<svg" not in topo
    # o script da troca grava o cookie e o localStorage, e não anima com o movimento reduzido do sistema
    assert "NexusTema.gravar(novo)" in html and "prefers-reduced-motion: reduce" in html


def test_no_claro_o_botao_oferece_o_escuro(logado):
    logado.set_cookie("nexus_tema", "claro")
    topo = logado.get("/").get_data(as_text=True).split('<header class="topo">', 1)[1].split("</header>", 1)[0]
    assert '<input type="hidden" name="tema" value="escuro">' in topo
    assert 'aria-label="Tema: claro. Trocar para o tema escuro"' in topo


def test_cabeca_aplica_a_reserva_antes_de_pintar(logado):
    html = logado.get("/").get_data(as_text=True)
    cabeca = html.split("</head>", 1)[0]
    # o script do tema roda no <head>, depois do nexus.css e antes do <body>
    assert cabeca.index("nexus.css") < cabeca.index('localStorage.getItem("nexus.tema")')
    assert "nexus_tema=" in cabeca and "SameSite=Lax" in cabeca


def test_post_tema_grava_o_cookie_e_volta_para_a_tela(logado):
    resp = logado.post("/tema", data={"tema": "claro", "voltar": "/t/pcm/gestao?modo=fila"})
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/t/pcm/gestao?modo=fila")
    cookie = resp.headers.get("Set-Cookie", "")
    assert "nexus_tema=claro" in cookie and "Path=/" in cookie and "SameSite=Lax" in cookie
    assert "Max-Age=31536000" in cookie and "HttpOnly" not in cookie
    assert 'data-tema="claro"' in logado.get("/").get_data(as_text=True)
    logado.post("/tema", data={"tema": "escuro", "voltar": "/"})
    assert 'data-tema="escuro"' in logado.get("/").get_data(as_text=True)


def test_post_tema_recusa_tema_desconhecido_e_volta_de_fora(logado):
    assert logado.post("/tema", data={"tema": "lilas", "voltar": "/"}).status_code == 400
    resp = logado.post("/tema", data={"tema": "claro", "voltar": "//site.com/x"})
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/")
    assert "site.com" not in resp.headers["Location"]


def test_post_tema_sem_login_barra(cliente):
    resp = cliente.post("/tema", data={"tema": "claro", "voltar": "/"})
    assert resp.status_code == 302 and "/entrar" in resp.headers["Location"]


def test_cookie_do_tema_e_secure_no_servidor(app, logado):
    app.config["SESSION_COOKIE_SECURE"] = True
    cookie = logado.post("/tema", data={"tema": "claro", "voltar": "/"}).headers.get("Set-Cookie", "")
    assert "Secure" in cookie


# ── as duas folhas de tokens ──────────────────────────────────────────────────────────────────────────────────────
def test_todo_token_do_escuro_tem_par_no_claro():
    escuro, claro = _tokens(SELETOR_ESCURO), _tokens(SELETOR_CLARO)
    assert len(escuro) >= 100
    assert set(escuro) - set(claro) == set(), "token do escuro sem valor no claro"
    assert set(claro) - set(escuro) == set(), "token do claro sem valor no escuro"


def test_o_escuro_e_o_de_sempre():
    """O escuro não muda (Levi: "acho foda"): cada token tem o valor que a tela já usava."""
    assert _tokens(SELETOR_ESCURO) == ESCURO_DE_SEMPRE


def test_o_topo_continua_navy_no_claro():
    """O bloco do escuro vale de novo dentro do .topo: o cabeçalho é navy com o logo claro nos dois temas."""
    css = _sem_comentarios((ESTATICO / "nexus.css").read_text(encoding="utf-8"))
    assert SELETOR_ESCURO.replace(" ", "") in css.replace(" ", "").replace("\n", "")


def test_nunca_lilas_no_fundo():
    """Navy tem o azul claramente acima do vermelho; o #191528 do mockup (lilás) não entra como fundo."""
    def rgb(h):
        h = h.lstrip("#")
        return [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    for tokens in (_tokens(SELETOR_ESCURO), _tokens(SELETOR_CLARO)):
        for nome in ("--fundo", "--superficie", "--superficie-2", "--superficie-3", "--barra", "--marca-fundo"):
            r, _g, b = rgb(tokens[nome])
            assert tokens[nome] != "#191528" and b >= r, nome


# ── nenhuma cor fixa fora dos tokens ──────────────────────────────────────────────────────────────────────────────
def test_css_do_nexus_sem_cor_fixa_fora_dos_tokens():
    erros = []
    for arq in _css_do_nexus():
        for seletor, corpo in _regras(arq.read_text(encoding="utf-8")):
            bloco_de_tema = arq.name == "nexus.css" and seletor in (SELETOR_ESCURO, SELETOR_CLARO)
            for prop, valor in _declaracoes(corpo):
                if bloco_de_tema and prop.startswith("--"):
                    continue
                if COR.search(valor) or NOMES_DE_COR.search(valor):
                    erros.append(f"{arq.name}: {seletor} {{{prop}:{valor}}}")
    assert erros == [], "cor fixa fora dos tokens (use var(--token) e ponha o valor nos dois temas do nexus.css):\n" + \
        "\n".join(erros)


def test_templates_sem_cor_fixa():
    """style="...", <style> e os atributos de pintura do SVG (fill, stroke, stop-color) dos templates do Nexus."""
    erros = []
    for t in _templates_do_nexus():
        html = t.read_text(encoding="utf-8")
        trechos = re.findall(r'\sstyle="([^"]*)"', html) + re.findall(r"<style[^>]*>(.*?)</style>", html, flags=re.S)
        trechos += re.findall(r'\s(?:fill|stroke|stop-color|flood-color|color)="([^"]*)"', html)
        for trecho in trechos:
            sem_jinja = re.sub(r"\{\{.*?\}\}|\{%.*?%\}", "", trecho, flags=re.S)
            if COR.search(sem_jinja) or NOMES_DE_COR.search(_sem_comentarios(sem_jinja)):
                erros.append(f"{t.relative_to(RAIZ)}: {trecho.strip()[:80]}")
    assert erros == [], "cor fixa em template:\n" + "\n".join(erros)


def test_todo_var_usado_existe():
    """Um var(--x) com nome errado vira 'sem cor' em silêncio: todo token usado nos .css e nos templates tem de existir
    (nos dois temas do nexus.css, num token local de um .css, ou posto pelo template/JS, como --cor da pessoa)."""
    definidos = set(_tokens(SELETOR_ESCURO))
    usados = {}
    fontes = [(a, a.read_text(encoding="utf-8")) for a in _css_do_nexus()]
    fontes += [(t, t.read_text(encoding="utf-8")) for t in _templates_do_nexus()]
    for arq, texto in fontes:
        # comentário fala de var(--token) sem usar: fica de fora
        texto = re.sub(r"\{#.*?#\}|<!--.*?-->", "", _sem_comentarios(texto), flags=re.S)
        definidos |= set(re.findall(r"(--[\w-]+)\s*:", texto))
        definidos |= set(re.findall(r"""setProperty\(\s*['"](--[\w-]+)""", texto))
        for nome in re.findall(r"var\(\s*(--[\w-]+)", texto):
            usados.setdefault(nome, arq.name)
    faltam = {n: a for n, a in usados.items() if n not in definidos}
    assert faltam == {}, f"var() sem token: {faltam}"


# ── contraste do claro ────────────────────────────────────────────────────────────────────────────────────────────
def _rgba(valor: str):
    valor = valor.strip()
    if valor.startswith("#"):
        h = valor[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return [int(h[i:i + 2], 16) for i in (0, 2, 4)] + [1.0]
    m = re.match(r"rgba?\(([^)]*)\)", valor)
    partes = [float(x) for x in re.split(r"[\s,/]+", m.group(1).strip()) if x]
    return partes[:3] + [partes[3] if len(partes) > 3 else 1.0]


def _sobre(cima, baixo):
    a = cima[3]
    return [cima[i] * a + baixo[i] * (1 - a) for i in range(3)] + [1.0]


def _lum(c):
    def f(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])


def _razao(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _contrastes_do_claro():
    t = _tokens(SELETOR_CLARO)
    c = {k: _rgba(v) for k, v in t.items()}
    superficies = ["--fundo", "--superficie", "--superficie-2", "--superficie-3"]
    casos = []

    def fundo(*camadas):
        base = [255, 255, 255, 1.0]
        for nome in camadas:
            base = _sobre(c[nome], base)
        return base

    for texto in ("--tinta", "--tinta-2", "--mudo", "--fraco", "--verde-texto"):
        for s in superficies:
            casos.append((texto, s, fundo(s)))
    for texto in ("--tinta", "--tinta-2", "--mudo", "--verde-texto"):
        for s in ("--superficie", "--superficie-2", "--superficie-3"):
            casos.append((texto, f"--verde-suave sobre {s}", fundo(s, "--verde-suave")))
    for nome in ("--ok", "--alerta", "--severo", "--critico", "--info", "--semcom"):
        for s in superficies:
            casos.append((nome, s, fundo(s)))
        for s in ("--superficie", "--superficie-2", "--superficie-3"):
            casos.append((nome, f"{nome}-suave sobre {s}", fundo(s, f"{nome}-suave")))
    for nome, fundos in (("--alerta", ("--alerta-a08", "--alerta-a10", "--alerta-a12", "--alerta-a16", "--alerta-a18")),
                         ("--critico", ("--critico-a12", "--critico-a18", "--critico-suave")),
                         ("--erro", ("--erro-a08",)), ("--info", ("--info-a10",)), ("--ok", ("--ok-a12",)),
                         ("--severo", ("--laranja-a16", "--severo-suave")), ("--verde-texto", ("--verde-a16",))):
        for f in fundos:
            for s in ("--superficie", "--superficie-2"):
                casos.append((nome, f"{f} sobre {s}", fundo(s, f)))
    for cheio in ("--ok-cheio", "--lima-cheio", "--alerta-cheio", "--severo-cheio", "--critico-cheio", "--info-cheio"):
        casos.append(("--sobre-cheio", cheio, fundo(cheio)))
    casos += [("--sobre-verde", "--verde", fundo("--verde")), ("--sobre-verde", "--verde-hover", fundo("--verde-hover")),
              ("--agir-tinta", "--critico-a30 sobre --superficie", fundo("--superficie", "--critico-a30")),
              ("--tinta", "--alerta-a16 sobre --superficie", fundo("--superficie", "--alerta-a16")),
              ("--mudo", "--barra", fundo("--barra")), ("--tinta-2", "--barra", fundo("--barra")),
              ("--papel-mudo", "--papel", fundo("--papel")), ("--papel-link", "--papel", fundo("--papel"))]
    for serie in ("--serie-sujidade", "--serie-vegetacao"):
        for s in ("--superficie", "--superficie-2"):
            casos.append((serie, s, fundo(s)))
    # a sigla do estado no mapa é translúcida: compõe sobre a terra
    casos.append(("--mapa-sigla", "--mapa-terra", fundo("--mapa-terra")))
    resultado = []
    for texto, nome_fundo, base in casos:
        cor = _sobre(c[texto], base) if c[texto][3] < 1 else c[texto]
        resultado.append((texto, nome_fundo, round(_razao(cor, base), 2)))
    return resultado


@pytest.mark.parametrize("texto,fundo,razao", _contrastes_do_claro())
def test_contraste_aa_do_texto_no_claro(texto, fundo, razao):
    assert razao >= 4.5, f"{texto} sobre {fundo}: {razao}:1 (mínimo 4,5:1)"

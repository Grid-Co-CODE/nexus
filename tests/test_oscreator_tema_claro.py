"""O tema claro do OS Creator Web dentro do Nexus (Levi, 09/10/2026: "faltou o tema claro do OS Creator Web, não está
sincronizando com o botão do Nexus").

O que estes testes seguram:
- a ponte desenha o <html data-tema="claro"> da página do clone pelo cookie nexus_tema, e no escuro não põe nada (o HTML do
  escuro não depende do cookie); o script do tema vai em toda página, logo depois do <meta charset>;
- o card da OS (card_os.html) segue o mesmo cookie;
- o botão do tema do Nexus troca as molduras do /os/ abertas, moldura dentro de moldura, e só elas (a função do base.html,
  rodada no node sobre um DOM falso);
- o clone não importa o nexus (vai para o oem, que não tem o Nexus);
- a COBERTURA, que pega o esquecimento: toda cor fixa do escuro de cada .css do clone tem o par do claro (o mesmo seletor e a
  mesma propriedade), toda variável de cor tem o valor do claro, toda cor de traço de ícone tem a do claro e toda cor escrita
  num template (ou montada no JS) do clone tem o gancho do claro;
- o claro só existe sob html[data-tema="claro"], em :where() (não soma especificidade: o estado .on/:hover/:focus do escuro
  continua vencendo); fora dele (o oem sozinho) nada muda;
- a paleta --osc-* do clone é a do tema claro do Nexus;
- o contraste AA (4,5:1) do texto do claro, regra a regra, com o fundo que a própria regra declara.
A tela foi conferida no Chrome sem janela (README da torre, seção "Tema claro").
"""
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from nexus.torres.oscreator import ponte

RAIZ = Path(__file__).resolve().parent.parent
CLONE = Path(ponte.RAIZ_CLONE)
WEB = CLONE / "os_web"
ESTATICO = WEB / "static"
NEXUS_CSS = RAIZ / "nexus" / "static" / "nexus.css"
CLARO = ':where(html[data-tema="claro"])'
VARS_CLARO = 'html[data-tema="claro"]'

COR = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch)\(|(?<![\w-])(?:white|black)(?![\w-])", re.I)

# O que fica igual nos dois temas, de propósito (o claro não precisa de par): a foto ampliada (o visor das fotos do card) é
# sempre escura, como a do Nexus (--foto-*): foto se olha no escuro. Dentro dele as variáveis voltam ao escuro.
FICA_ESCURO = {("os_acoes.css", ".visor"), ("os_acoes.css", ".visor-img img"), ("os_acoes.css", ".visor-lado"),
               ("os_acoes.css", ".visor-cap")}
# A cor de DADO que é a mesma nos dois temas, com texto escuro por cima: a do avatar de cada pessoa no quadro do
# Acompanhamento (acomp_web.cor_avatar), como a cor da pessoa no Quadro da equipe do Nexus.
VARIAVEIS_DO_DADO = {"--av"}

# a propriedade do escuro -> as propriedades do claro que a cobrem
def _cobre(prop: str) -> set:
    if prop.startswith("background"):
        return {"background", "background-color", "background-image"}
    m = re.fullmatch(r"border-(top|right|bottom|left)(-color)?", prop)
    if m:
        return {f"border-{m.group(1)}", f"border-{m.group(1)}-color", "border-color", "border"}
    if prop in ("border", "border-color"):
        return {"border", "border-color"}
    if prop == "outline":
        return {"outline", "outline-color"}
    return {prop}


def _sem_comentarios(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _partes(seletor: str) -> list:
    """O seletor separado nas vírgulas de fora (a vírgula dentro de :where()/:not() não separa)."""
    partes, nivel, atual = [], 0, ""
    for ch in seletor:
        if ch == "(":
            nivel += 1
        elif ch == ")":
            nivel -= 1
        if ch == "," and nivel == 0:
            partes.append(atual.strip())
            atual = ""
        else:
            atual += ch
    partes.append(atual.strip())
    return [" ".join(p.split()) for p in partes if p.strip()]


def _regras(css: str):
    """(partes do seletor, [(propriedade, valor)]) de cada regra, na ordem; a de dentro do @media vem com o próprio
    seletor."""
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", _sem_comentarios(css)):
        seletor = " ".join(m.group(1).split())
        if seletor.startswith("@") or seletor in ("from", "to") or re.fullmatch(r"[\d.]+%", seletor):
            continue
        decls = []
        for d in m.group(2).split(";"):
            if ":" in d:
                p, v = d.split(":", 1)
                decls.append((p.strip().lower(), " ".join(v.split())))
        yield _partes(seletor), decls


def _eh_claro(parte: str) -> bool:
    return parte.startswith(CLARO) or parte.startswith(VARS_CLARO)


def _sem_reserva(valor: str) -> str:
    """var(--x, #reserva) -> var(--x): a reserva do var() não pinta enquanto a variável existe."""
    return re.sub(r"var\((--[\w-]+)\s*,[^()]*(?:\([^()]*\)[^()]*)*\)", r"var(\1)", valor)


def _css_do_clone():
    return sorted(ESTATICO.glob("*.css"))


def _par_do_claro(parte: str) -> str:
    """O seletor do claro que repete o do escuro."""
    if parte in (":root", "html"):
        return VARS_CLARO
    return f"{CLARO} {parte}"


# ── a ponte e o card: o tema chega desenhado pelo servidor ──────────────────────────────────────────────────────────
# o clone importa o steps/ui.py do OS Creator (PyQt6) ao montar a tela de Engenharia; as folhas não precisam dele
precisa_do_clone = pytest.mark.skipif(importlib.util.find_spec("PyQt6") is None, reason="sem PyQt6 nesta máquina")


def _html_abre(h: str) -> str:
    return re.search(r"<html[^>]*>", h).group(0)


@precisa_do_clone
def test_ponte_poe_o_tema_claro_pelo_cookie(logado):
    logado.set_cookie("nexus_tema", "claro")
    h = logado.get("/os/login").get_data(as_text=True)
    assert 'data-tema="claro"' in _html_abre(h)
    # o script do tema vai logo depois do <meta charset> (antes de pintar; o charset segue nos primeiros 1.024 bytes)
    cabeca = h.split("</head>", 1)[0]
    assert cabeca.index('<meta charset="utf-8">') < cabeca.index('localStorage.getItem("nexus.tema")')
    assert h.encode().index(b"<meta charset") < 1024
    assert 'window.addEventListener("storage"' in cabeca


@precisa_do_clone
@pytest.mark.parametrize("cookie", [None, "escuro", "lilas"])
def test_ponte_nao_poe_o_atributo_no_escuro(logado, cookie):
    """No escuro (o padrão, o cookie ausente ou desconhecido) o <html> do clone é o de sempre, sem data-tema."""
    if cookie:
        logado.set_cookie("nexus_tema", cookie)
    h = logado.get("/os/login").get_data(as_text=True)
    assert "data-tema" not in _html_abre(h)
    assert _html_abre(h) == '<html lang="pt-BR" data-sem-abas="1">'


@precisa_do_clone
def test_no_escuro_a_resposta_nao_depende_do_cookie(logado):
    """O HTML do escuro é um só (sem cookie, cookie escuro ou cookie estranho), e a ponte não mexe no que não é HTML."""
    sem = logado.get("/os/login").get_data()
    css_sem = logado.get("/os/static/os.css").get_data()
    for c in ("escuro", "lilas"):
        logado.set_cookie("nexus_tema", c)
        assert logado.get("/os/login").get_data() == sem
    logado.set_cookie("nexus_tema", "claro")
    assert logado.get("/os/static/os.css").get_data() == css_sem
    assert logado.get("/os/login").get_data() != sem


def _login_do_fracttal(app, cliente):
    clone = ponte.clone(app)
    jwt = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"
    valor = clone.session_interface.get_signing_serializer(clone).dumps(
        {"jwt": jwt, "conta": {"nome": "Pessoa Teste", "email": "teste@exemplo.invalid"}})
    cliente.set_cookie("os_sessao", valor, path="/os")


@precisa_do_clone
def test_card_da_os_segue_o_tema(app, logado):
    _login_do_fracttal(app, logado)
    url = "/os/_nexus/card/9001?status=Em%20Processo&de=/t/engenharia/equipe"
    h = logado.get(url).get_data(as_text=True)
    assert _html_abre(h) == '<html lang="pt-BR">'
    logado.set_cookie("nexus_tema", "claro")
    h = logado.get(url).get_data(as_text=True)
    assert _html_abre(h) == '<html lang="pt-BR" data-tema="claro">'
    cabeca = h.split("</head>", 1)[0]
    assert 'localStorage.getItem("nexus.tema")' in cabeca and 'window.addEventListener("storage"' in cabeca
    assert cabeca.index('href="/os/static/os.css"') < cabeca.index("nexus_tema=")


# ── o botão do Nexus troca as molduras abertas ──────────────────────────────────────────────────────────────────────
def _funcao(js: str, nome: str) -> str:
    """O texto de uma função do script (das chaves balanceadas)."""
    i = js.index(f"function {nome}(")
    j = js.index("{", i)
    nivel = 0
    for k in range(j, len(js)):
        nivel += {"{": 1, "}": -1}.get(js[k], 0)
        if nivel == 0:
            return js[i:k + 1]
    raise AssertionError(f"função {nome} sem fim")


def test_botao_do_tema_chama_a_troca_nas_molduras(logado):
    h = logado.get("/").get_data(as_text=True)
    mostrar = _funcao(h, "mostrarTema")
    assert 'raiz.setAttribute("data-tema", t);' in mostrar and "temaNasMolduras(document, t);" in mostrar
    # a troca de outra aba (evento storage) passa pelo mesmo mostrarTema
    assert 'ev.key === "nexus.tema"' in h and "mostrarTema(ev.newValue)" in h


@pytest.mark.skipif(not shutil.which("node"), reason="sem node nesta máquina")
def test_troca_chega_a_moldura_dentro_de_moldura_e_so_ao_os_creator(logado):
    """A função do base.html sobre um DOM falso: a moldura da torre (/os/, a casca) com uma aba dentro (/os/historico) e o
    card da OS (/os/_nexus/card); a página da Plataforma (outro sistema, /plataforma) e uma moldura de outra origem (que dá
    exceção ao ler) ficam como estão."""
    fn = _funcao(logado.get("/").get_data(as_text=True), "temaNasMolduras")
    script = r"""
const vm = require('vm');
function doc(molduras) { const at = {}; return {documentElement: {setAttribute: (k, v) => { at[k] = v; }, at},
  getElementsByTagName: (t) => t === 'iframe' ? molduras : []}; }
function moldura(caminho, d) { return {contentWindow: {location: {pathname: caminho}, document: d}}; }
const aba = doc([]), casca = doc([moldura('/os/historico', aba)]), card = doc([]), plat = doc([]);
const fora = {get contentWindow() { return {get document() { throw new Error('SecurityError'); }, location: {}}; }};
const vazia = {contentWindow: {location: {pathname: 'blank'}, document: doc([])}};
const topo = doc([moldura('/os/', casca), moldura('/os/_nexus/card/9001', card), moldura('/plataforma/x', plat), fora, vazia]);
const ctx = {}; vm.createContext(ctx); vm.runInContext(process.argv[1] + '; this.f = temaNasMolduras;', ctx);
ctx.f(topo, 'claro');
const r1 = [casca, aba, card, plat].map((d) => d.documentElement.at['data-tema'] || null);
ctx.f(topo, 'escuro');
const r2 = [casca, aba, card, plat].map((d) => d.documentElement.at['data-tema'] || null);
console.log(JSON.stringify({r1, r2}));
"""
    r = subprocess.run(["node", "-e", script, fn], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["r1"] == ["claro", "claro", "claro", None]
    assert out["r2"] == ["escuro", "escuro", "escuro", None]


# ── o clone continua sem o Nexus ────────────────────────────────────────────────────────────────────────────────────
def test_clone_nao_importa_o_nexus():
    """Toda .py da cópia (inclusive a que ainda não está no git): o tema claro mora no CSS do clone e na ponte."""
    from nexus.torres.oscreator import sincronia as S
    pys = [p.relative_to(S.AQUI).as_posix() for pasta in S.PASTAS for p in (S.AQUI / pasta).rglob("*.py")]
    assert pys and S.importa_o_nexus(S.AQUI, pys) == []
    # e nenhum template, script ou folha do clone carrega coisa do Nexus (o clone só conhece o atributo data-tema)
    for arq in list(WEB.rglob("*.html")) + list(WEB.rglob("*.js")) + list(WEB.rglob("*.css")):
        texto = _sem_comentarios(arq.read_text(encoding="utf-8"))
        assert not re.search(r"(?:href|src)=[\"']/static/|@import|NexusTema|NexusOsCard|nexus_tema", texto), arq.name


# ── a cobertura do claro, folha por folha ───────────────────────────────────────────────────────────────────────────
def _tudo(arq: Path):
    return list(_regras(arq.read_text(encoding="utf-8")))


@pytest.mark.parametrize("arq", _css_do_clone(), ids=lambda a: a.name)
def test_cada_cor_fixa_do_escuro_tem_o_par_do_claro(arq):
    """O esquecimento de verdade: cor nova no escuro sem o claro ao lado. Vale a ÚLTIMA declaração de cada seletor e
    propriedade (a de antes, sobrescrita no mesmo seletor, nunca pinta)."""
    escuro, claro = {}, {}
    for partes, decls in _tudo(arq):
        for parte in partes:
            alvo = claro if _eh_claro(parte) else escuro
            for prop, valor in decls:
                if not prop.startswith("--"):
                    alvo.setdefault(parte, {})[prop] = valor
    faltam = []
    for parte, decls in escuro.items():
        if (arq.name, parte) in FICA_ESCURO:
            continue
        par = claro.get(_par_do_claro(parte), {})
        for prop, valor in decls.items():
            if COR.search(_sem_reserva(valor)) and not (_cobre(prop) & set(par)):
                faltam.append(f"{arq.name}: {parte} {{{prop}:{valor}}}")
    assert faltam == [], "cor fixa do escuro sem o par do claro (repita o seletor dentro de " + CLARO + "):\n" + \
        "\n".join(faltam)


@pytest.mark.parametrize("arq", _css_do_clone(), ids=lambda a: a.name)
def test_cada_variavel_de_cor_tem_o_valor_do_claro(arq):
    escuro, claro = {}, {}
    for partes, decls in _tudo(arq):
        for parte in partes:
            alvo = claro if _eh_claro(parte) else escuro
            for prop, valor in decls:
                if prop.startswith("--"):
                    alvo.setdefault(parte, {})[prop] = valor
    faltam = [f"{arq.name}: {parte} {nome}" for parte, decls in escuro.items() for nome, valor in decls.items()
              if COR.search(_sem_reserva(valor)) and nome not in VARIAVEIS_DO_DADO
              and nome not in claro.get(_par_do_claro(parte), {})]
    assert faltam == [], "variável de cor sem o valor do claro:\n" + "\n".join(faltam)


def test_o_claro_so_existe_sob_o_atributo_e_sem_somar_especificidade():
    """O claro mora todo sob html[data-tema="claro"]: no oem sozinho (sem o atributo) nada dele vale. As regras vão em
    :where(), que não soma especificidade (o ".x" do claro não pode passar por cima do ".x.on" e do ":focus" do escuro);
    só os blocos de variáveis ficam em html[data-tema="claro"], para vencer o :root."""
    erros = []
    for arq in _css_do_clone():
        for partes, decls in _tudo(arq):
            for parte in partes:
                if "data-tema" not in parte:
                    continue
                if parte == VARS_CLARO:
                    if any(not (p.startswith("--") or p in ("scrollbar-color", "color-scheme")) for p, _ in decls):
                        erros.append(f"{arq.name}: {parte} com regra de elemento (use {CLARO})")
                elif not parte.startswith(CLARO):
                    erros.append(f"{arq.name}: {parte}")
    assert erros == [], "\n".join(erros)


def test_toda_folha_do_clone_que_tem_cor_tem_o_claro():
    sem = [a.name for a in _css_do_clone()
           if COR.search(_sem_comentarios(a.read_text(encoding="utf-8"))) and CLARO not in a.read_text(encoding="utf-8")]
    assert sem == []


# ── a paleta é a do Nexus ───────────────────────────────────────────────────────────────────────────────────────────
PALETA_DO_NEXUS = {
    "--osc-pagina": "--fundo", "--osc-cartao": "--superficie", "--osc-secao": "--superficie-2", "--osc-secao-2": "--superficie-3",
    "--osc-texto": "--tinta", "--osc-texto-2": "--tinta-2", "--osc-mudo": "--mudo", "--osc-fraco": "--fraco",
    "--osc-linha": "--linha", "--osc-linha-forte": "--linha-forte", "--osc-lima": "--verde", "--osc-lima-hover": "--verde-hover",
    "--osc-lima-suave": "--verde-suave", "--osc-musgo": "--verde-texto", "--osc-musgo-borda": "--verde-a45",
    "--osc-sobre-lima": "--sobre-verde", "--osc-ok": "--ok", "--osc-ok-suave": "--ok-suave", "--osc-alerta": "--alerta",
    "--osc-alerta-suave": "--alerta-suave", "--osc-alerta-borda": "--alerta-a35", "--osc-severo": "--severo",
    "--osc-severo-suave": "--severo-suave", "--osc-critico": "--critico", "--osc-critico-suave": "--critico-suave",
    "--osc-critico-forte": "--critico-a30", "--osc-critico-borda": "--critico-a45", "--osc-info": "--info",
    "--osc-info-suave": "--info-suave", "--osc-info-borda": "--info-a42", "--osc-ok-cheio": "--ok-cheio",
    "--osc-alerta-cheio": "--alerta-cheio", "--osc-severo-cheio": "--severo-cheio", "--osc-critico-cheio": "--critico-cheio",
    "--osc-info-cheio": "--info-cheio", "--osc-sobre-cheio": "--sobre-cheio", "--osc-clarao": "--clarao-a04",
    "--osc-clarao-2": "--clarao-a08", "--osc-sombra": "--sombra", "--osc-sombra-alta": "--cartao-sombra", "--osc-veu": "--veu",
    "--osc-rolagem": "--rolagem", "--osc-rolagem-hover": "--rolagem-hover", "--osc-marca-fundo": "--marca-fundo",
}


def _bloco(arq: Path, seletor: str) -> dict:
    achados = [dict(d) for partes, d in _regras(arq.read_text(encoding="utf-8")) if partes == [seletor]]
    assert len(achados) >= 1, f"{arq.name} sem o bloco {seletor}"
    out = {}
    for d in achados:
        out.update(d)
    return out


def test_a_paleta_clara_do_clone_e_a_do_nexus():
    clone = _bloco(ESTATICO / "os.css", VARS_CLARO)
    nexus = _bloco(NEXUS_CSS, ':root[data-tema="claro"]')
    difere = {cl: (clone.get(cl), nexus.get(nx)) for cl, nx in PALETA_DO_NEXUS.items()
              if clone.get(cl, "").replace(" ", "") != nexus.get(nx, "").replace(" ", "")}
    assert difere == {}, "o claro do OS Creator tem de acompanhar o do Nexus (nexus.css):\n" + "\n".join(
        f"{k}: clone {a} x Nexus {PALETA_DO_NEXUS[k]} {b}" for k, (a, b) in difere.items())


# ── os ícones e as cores escritas nos templates e no JavaScript do clone ───────────────────────────────────────────
def _fontes_do_clone():
    for ext in ("*.html", "*.py", "*.js"):
        yield from CLONE.rglob(ext)


def test_toda_cor_de_icone_tem_a_do_claro():
    """O traço do ícone vem no stroke="#…" do <svg> (lancador.icone e os <svg> dos templates): cor nova sem o par do claro
    ficaria o verde-claro (1,6:1) ou o branco no fundo branco."""
    cores = set()
    for arq in _fontes_do_clone():
        if "steps" in arq.parts:                          # o app de desktop (PyQt): não vai à web
            continue
        texto = arq.read_text(encoding="utf-8", errors="replace")
        for chamada in re.findall(r"icone\([^)]*\)", texto):
            cores |= {c.lower() for c in re.findall(r"['\"](#[0-9a-fA-F]{3,8})['\"]", chamada)}
        cores |= {c.lower() for c in re.findall(r"stroke=[\"'](#[0-9a-fA-F]{3,8})[\"']", texto)}
        cores |= {c.lower() for c in re.findall(r"def icone\([^)]*cor: str = \"(#[0-9a-fA-F]{3,8})\"", texto)}
    claro = {m.lower() for partes, _ in _regras((ESTATICO / "os.css").read_text(encoding="utf-8")) for p in partes
             for m in re.findall(rf'^{re.escape(CLARO)} svg\[stroke="(#[0-9a-fA-F]{{3,8}})" i\]$', p)}
    assert len(cores) >= 8
    assert sorted(cores - claro) == [], "cor de ícone sem o claro (os.css, svg[stroke=\"…\" i])"


def _regras_claras_de_todas():
    out = []
    for arq in _css_do_clone():
        for partes, decls in _regras(arq.read_text(encoding="utf-8")):
            for p in partes:
                if p.startswith(CLARO):
                    out.append((p[len(CLARO):].strip(), dict(decls)))
    return out


def test_toda_cor_escrita_nos_templates_e_no_js_tem_o_gancho_do_claro():
    """style="…" com cor num template do clone (ou montado pelo JavaScript): a cor fixa ganha uma classe com o claro em
    !important (vence o style); a cor que vem do DADO (status, etiqueta, placar) ganha o -webkit-text-fill-color do claro,
    a cor do próprio elemento com a luminosidade no teto."""
    claras = _regras_claras_de_todas()
    faltam = []

    def tem(seletores_ok, prop, importante=False):
        for sel, decls in claras:
            if any(sel == s or sel.endswith(" " + s) or sel.endswith(">" + s) for s in seletores_ok) and prop in decls:
                if not importante or decls[prop].endswith("!important"):
                    return True
        return False

    for arq in list(WEB.rglob("*.html")) + list(WEB.rglob("*.js")):
        texto = arq.read_text(encoding="utf-8")
        # o style pode vir depois de um {% if %} (style colado no %}): não exige espaço antes
        for m in re.finditer(r"<(\w+)([^<>]*?)(?<![\w-])style=(?:\\?[\"'])([^\"']*)", texto):
            tag, attrs, estilo = m.group(1), m.group(2), m.group(3)
            classes = (re.search(r"class=\\?[\"']([^\"'{}]*)", attrs) or [None, ""])[1].split()
            dado = "{{" in estilo or estilo.rstrip().endswith(":") or "' +" in texto[m.end():m.end() + 4]
            for prop in ("color", "background", "border-color"):
                if not re.search(rf"(?:^|;)\s*{prop}\s*:", estilo):
                    continue
                valor = re.search(rf"(?:^|;)\s*{prop}\s*:\s*([^;]*)", estilo).group(1)
                if dado and prop == "color":
                    # pela classe do elemento; sem classe, pela tag (o <span style> do nó do Fluxo)
                    alvos = [f".{c}[style]" for c in classes] or [f"{tag}[style]"]
                    if not tem(alvos, "-webkit-text-fill-color"):
                        faltam.append(f"{arq.name}: <{tag} class=\"{' '.join(classes)}\"> {prop} do dado")
                elif not dado and COR.search(valor):
                    if not tem([f".{c}" for c in classes], prop, importante=True):
                        faltam.append(f"{arq.name}: <{tag} class=\"{' '.join(classes)}\"> {prop}:{valor}")
    assert faltam == [], "cor escrita sem o gancho do claro:\n" + "\n".join(faltam)


# ── o contraste do texto do claro ───────────────────────────────────────────────────────────────────────────────────
def _rgba(valor: str):
    v = valor.strip().lower()
    if v.startswith("#"):
        h = v[1:]
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        return [int(h[i:i + 2], 16) for i in (0, 2, 4)] + [1.0]
    m = re.match(r"rgba?\(([^)]*)\)", v)
    if not m:
        return None
    p = [float(x) for x in re.split(r"[\s,/]+", m.group(1).strip()) if x]
    return p[:3] + [p[3] if len(p) > 3 else 1.0]


def _sobre(cima, baixo):
    a = cima[3]
    return [cima[i] * a + baixo[i] * (1 - a) for i in range(3)] + [1.0]


def _razao(a, b):
    def lum(c):
        def f(x):
            x /= 255
            return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _variaveis_do_claro() -> dict:
    """As variáveis no claro: as do bloco html[data-tema="claro"] de cada folha e as dos escopos (.os-cos, .tp)."""
    v = {}
    for arq in _css_do_clone():
        for partes, decls in _regras(arq.read_text(encoding="utf-8")):
            if any(p == VARS_CLARO or (p.startswith(CLARO) and not p.startswith(CLARO + " .visor")) for p in partes):
                v.update({k: val for k, val in decls if k.startswith("--")})
    return v


def _resolver(valor: str, vs: dict, prof=0):
    valor = _sem_reserva(valor).replace("!important", "").strip()
    m = re.fullmatch(r"var\((--[\w-]+)\)", valor)
    if m:
        return _resolver(vs[m.group(1)], vs, prof + 1) if m.group(1) in vs and prof < 8 else None
    return _rgba(valor)


def _fundo(valor: str, vs: dict):
    """A cor de fundo de um 'background' (a cor solta no shorthand)."""
    valor = _sem_reserva(valor)
    if "gradient" in valor or "url(" in valor:
        return None
    for pedaco in [valor] + valor.split():
        c = _resolver(pedaco, vs)
        if c:
            return c
    return None


def _contrastes_do_claro():
    vs = _variaveis_do_claro()
    efetivo = {}                                          # seletor -> {propriedade: valor} no claro (o par do claro vence)
    for arq in _css_do_clone():
        for partes, decls in _regras(arq.read_text(encoding="utf-8")):
            for p in partes:
                if p == VARS_CLARO:
                    continue
                chave = p[len(CLARO):].strip() if p.startswith(CLARO) else p
                for prop, valor in decls:
                    if prop == "color" or prop.startswith("background"):
                        efetivo.setdefault((arq.name, chave), {})["color" if prop == "color" else "bg"] = valor
    casos = []
    for (arq, sel), d in efetivo.items():
        if "color" not in d or (arq, sel) in FICA_ESCURO or sel.startswith(".visor"):
            continue
        sem_not = re.sub(r":not\([^()]*\)", "", sel)
        if re.search(r":disabled|\.desab\b|\.off\b|::placeholder", sem_not):
            continue                                      # desligado não entra na regra de contraste
        texto = _resolver(d["color"], vs)
        if texto is None:
            continue                                      # currentColor, inherit, color-mix do dado: o navegador mede
        fundos = []
        if "bg" in d:
            f = _fundo(d["bg"], vs)
            if f:
                fundos = [_sobre(f, [255, 255, 255, 1.0])]
        if not fundos:
            fundos = [[255, 255, 255, 1.0], _rgba("#f5f6f8")]
        pior = min(_razao(_sobre(texto, b) if texto[3] < 1 else texto, b) for b in fundos)
        casos.append((f"{arq}: {sel}", round(pior, 2)))
    return casos


def test_contraste_aa_do_texto_do_claro():
    casos = _contrastes_do_claro()
    assert len(casos) > 150
    baixos = [f"{nome}: {r}:1" for nome, r in casos if r < 4.5]
    assert baixos == [], "texto do claro abaixo de 4,5:1:\n" + "\n".join(baixos)


def test_borda_de_campo_do_claro_tem_3_para_1():
    """A borda do campo é o que mostra onde ele está: 3:1 contra o branco e contra o cinza de seção (WCAG 1.4.11)."""
    vs = _variaveis_do_claro()
    borda = _resolver("var(--osc-campo)", vs)
    for fundo in ("#ffffff", "#f5f6f8"):
        base = _rgba(fundo)
        assert _razao(_sobre(borda, base), base) >= 3, fundo

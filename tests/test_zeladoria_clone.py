"""O clone do app do Radar (nexus/torres/zeladoria/clone/radar.html), limpo pelo ferramentas/zeladoria_limpar_clone.py.

Ele entra no repositório público sem o Supabase (sem endereço, sem chave, sem o carregador das CDNs) e sem e-mail de
gente; os nomes de colega o test_sem_nomes_no_repositorio.py cobre. Os dois marcadores são onde a torre, ao servir,
põe a configuração e a ponte (nexus/static/zeladoria/ponte.js)."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
CLONE = RAIZ / "nexus" / "torres" / "zeladoria" / "clone" / "radar.html"


@pytest.fixture(scope="module")
def html():
    return CLONE.read_text(encoding="utf-8")


def test_sem_supabase(html):
    for proibido in ("supabase.co", "sb_publishable", "cdn.jsdelivr.net/npm/@supabase", "unpkg.com/@supabase",
                     "SUPABASE_URL", "SUPABASE_ANON_KEY"):
        assert proibido not in html, proibido
    assert html.count("window.supabase.createClient()") == 1


def test_marcadores(html):
    assert html.count("<!--ZELADORIA:CONFIG-->") == 1 and html.count("<!--ZELADORIA:PONTE-->") == 1
    assert html.index("<!--ZELADORIA:CONFIG-->") < html.index("<script")      # a configuração vem antes de tudo


def test_abre_na_aba_pedida(html):
    assert "tab: (window.ZELADORIA_ABA || 'overview')" in html


def test_sem_email_da_empresa(html):
    assert not re.search(r"[\w.+-]+@gridco\.com\.br", html, re.IGNORECASE)


def test_js_valido(html, tmp_path):
    if not shutil.which("node"):
        pytest.skip("sem node nesta máquina")
    scripts = re.findall(r"<script(?: id=\"[^\"]*\")?>(.*?)</script>", html, re.S)
    assert len(scripts) >= 2
    for i, js in enumerate(scripts):
        arq = tmp_path / f"s{i}.js"
        arq.write_text(js, encoding="utf-8")
        r = subprocess.run(["node", "--check", str(arq)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-800:]


def test_origem_da_planilha_sem_nome_de_gente(html):
    """A planilha histórica levava o primeiro nome de quem a mantinha, no comentário e no valor gravado (`origem`).
    O valor passa a ser `planilha_historica`, aqui e nos dados copiados (a cópia aplica o mesmo de-para)."""
    assert "planilha_historica:1" in html and "origem='planilha_historica'" in html


def test_rota_da_equipe_casa_pelo_comeco(html):
    """O cronograma importado (arquivo do PCM) escreve "Rota do <supervisor>" com o nome de verdade: a regra que
    reconhecia a rota pelo nome não pode depender dele, senão as paradas da rota viram cotação."""
    assert "rota (do )?equipe" not in html
    assert html.count(r"/^\s*rota\b") == 3 and r"/^\s*rota\b|eco ?clean" in html     # 2 sozinhas + 1 na alternância


# ── o visual da Zeladoria (etapa 3, 03/11/2026): as três cores do Levi, as fontes do Nexus, sem emoji ──
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿⏩-⏺]")
VARIAVEIS_DO_CLONE = ("--bg", "--surface", "--surface-2", "--surface-sunken", "--border", "--ink", "--ink-2",
                      "--ink-muted", "--accent", "--accent-strong", "--accent-ink", "--accent-soft", "--good",
                      "--good-soft", "--warn", "--warn-soft", "--critical", "--critical-soft", "--info", "--info-soft",
                      "--frozen", "--frozen-soft", "--neutral-pill", "--shadow", "--fx-aberto", "--fx-prov")


def _paleta(html):
    m = re.search(r'<style id="zeladoria-paleta">(.*?)</style>', html, re.S)
    assert m, "sem a paleta da Zeladoria"
    blocos = dict(re.findall(r':root\[data-theme="(dark|light)"\]\s*\{([^}]*)\}', m.group(1)))
    return m.group(1), {t: dict(re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", c)) for t, c in blocos.items()}


def test_sem_emoji(html):
    achados = sorted({c for c in EMOJI.findall(html)})
    assert not achados, [f"U+{ord(c):04X}" for c in achados]


def test_as_tres_cores_nos_dois_temas(html):
    texto, temas = _paleta(html)
    assert set(temas) == {"dark", "light"}
    for t in ("dark", "light"):
        v = temas[t]
        assert (v["--zel-preto"], v["--zel-azul"], v["--zel-lima"]) == ("#030407", "#1558c9", "#d4ff24"), t
        assert set(VARIAVEIS_DO_CLONE) <= set(v), (t, set(VARIAVEIS_DO_CLONE) - set(v))
        assert v["--accent"] == "var(--zel-lima)" and v["--accent-ink"] == "var(--zel-preto)", t
    assert set(temas["dark"]) == set(temas["light"])
    assert temas["dark"]["--bg"] == "var(--zel-preto)"
    # no claro o lima é só superfície: o texto de destaque é escuro, e o azul faz o papel de informação
    assert temas["light"]["--accent-strong"] != "var(--zel-lima)" and temas["light"]["--info"] == "var(--zel-azul)"


def test_paleta_depois_do_css_do_clone(html):
    cabeca = html[:html.index("</head>")]
    assert cabeca.rindex('<style id="zeladoria-paleta">') > cabeca.index("<style>")     # vem depois, e vence


def test_fontes_do_nexus(html):
    assert "family=Poppins" in html and "family=Raleway" in html
    assert "family=Inter" not in html and '"Inter"' not in html and "font-family:Inter" not in html


def test_css_sem_cor_fixa_fora_da_paleta(html):
    css = "".join(re.findall(r"<style>(.*?)</style>", html, re.S))           # o CSS do clone, sem a paleta
    regras = re.sub(r"--[a-z0-9-]+\s*:[^;]+;", "", css)
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", regras)


def test_cores_de_aviso_do_js_viram_variavel(html):
    """O relatório de impressão fica de fora: a folha é sempre papel branco, nos dois temas (DESIGN.md)."""
    ini = html.index("var css = '@page{size:A4 landscape")
    html = html[:ini] + html[html.index("';\n", ini) + 3:]
    html = re.sub(r"--[a-zA-Z0-9-]+\s*:[^;]+;", "", html)          # as definições da paleta (a original, vencida)
    # a cor de DADO fica igual nos dois temas: o avatar de cada pessoa e a escala de dias de atraso
    html = re.sub(r"var AVATAR_COLORS = \[[^\]]*\];|function raCorFaixa\(f\)\{[^\n]*", "", html)
    for fixa in ("rgb(196,61,48)", "rgb(185,112,11)", "rgb(46,158,82)", "#5b5fc7", "#2e9e52", "#c43d30", "#b9700b",
                 "#d9921c", "#5c9a22"):
        assert fixa not in html.lower(), fixa


def test_o_tema_vem_do_nexus(html):
    assert "var t = window.ZELADORIA_TEMA || localStorage.getItem('rf_tema');" in html

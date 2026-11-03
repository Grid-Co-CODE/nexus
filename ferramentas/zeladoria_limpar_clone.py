"""Limpa o index.html do Radar de Fornecedores para ele entrar no Nexus como o clone da torre Zeladoria.

O que faz, e por quê:
- troca os nomes de colegas pelo papel ("o aprovador" vira Head, a segunda alçada vira Analista, o supervisor da equipe
  primarizada vira Equipe), em identificadores, rótulos, comentários e chaves de dado. O repositório do Nexus é público.
  O de-para com os nomes fica FORA dele (`--nomes`, um JSON {"texto": "troca"}), e a frase vem antes do nome solto;
- tira o Supabase: as duas constantes (endereço e chave) e o carregador das CDNs. No lugar do carregador entra o marcador
  `<!--ZELADORIA:PONTE-->`, onde a torre, ao servir, põe a ponte (nexus/static/zeladoria/ponte.js);
- põe `<!--ZELADORIA:CONFIG-->` logo no `<head>`, antes de qualquer script, para a configuração da torre;
- faz o app abrir na aba pedida pelo menu do Nexus (`window.ZELADORIA_ABA`);
- troca o e-mail de exemplo da tela de login;
- veste o clone com o visual da Zeladoria (`vestir`, etapa 3, 03/11/2026):
  - a paleta com as três cores do Levi (preto #030407, azul #1558c9, lima #d4ff24), nos dois temas;
  - as fontes do Nexus;
  - a cor fixa do CSS e dos estilos do JavaScript virando variável;
  - os emojis saindo (regra do Nexus);
  - o tema vindo do Nexus.

Cada troca estrutural tem de acontecer exatamente uma vez. Se o Radar mudar e uma delas não casar, a ferramenta para e
diz qual, em vez de gerar um clone pela metade. No fim ela procura os nomes que sobraram: sobrando algum, sai com erro e
lista as linhas.

Uso: python -I ferramentas/zeladoria_limpar_clone.py --origem <index.html do Radar> --nomes <de_para.json> --saida
nexus/torres/zeladoria/clone/radar.html
"""
import argparse
import json
import re
import sys
from pathlib import Path


class TrocaFalhou(RuntimeError):
    pass


def _uma_vez(texto: str, velho, novo: str, o_que: str, regex=False, flags=0) -> str:
    if regex:
        achados = re.findall(velho, texto, flags)
        if len(achados) != 1:
            raise TrocaFalhou(f"{o_que}: esperava 1, achei {len(achados)}")
        return re.sub(velho, lambda _m: novo, texto, count=1, flags=flags)
    n = texto.count(velho)
    if n != 1:
        raise TrocaFalhou(f"{o_que}: esperava 1, achei {n}")
    return texto.replace(velho, novo)


def trocar_nomes(texto: str, de_para: dict) -> str:
    for velho in sorted((k for k in de_para if not k.startswith("_")), key=len, reverse=True):
        texto = texto.replace(velho, de_para[velho])
    return texto


def limpar(texto: str, de_para: dict) -> str:
    texto = trocar_nomes(texto, de_para)
    # o cronograma importado (arquivo do PCM) escreve "Rota do <supervisor>" com o nome de verdade: a rota se
    # reconhece pelo começo do texto, sem depender do nome
    n = texto.count("/rota (do )?equipe")
    if n != 3:
        raise TrocaFalhou(f"a regra da rota da equipe: esperava 3, achei {n}")
    texto = texto.replace("/rota (do )?equipe", r"/^\s*rota\b")
    texto = _uma_vez(texto, r"^var SUPABASE_URL = '[^']*';\r?\n", "", "a constante do endereço do Supabase",
                     regex=True, flags=re.M)
    texto = _uma_vez(texto, r"^var SUPABASE_ANON_KEY = '[^']*';\r?\n", "", "a constante da chave do Supabase",
                     regex=True, flags=re.M)
    texto = _uma_vez(texto, "window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY)",
                     "window.supabase.createClient()", "a criação do cliente")
    texto = _uma_vez(texto, r"<script>\s*/\* Carrega o supabase-js.*?</script>", "<!--ZELADORIA:PONTE-->",
                     "o carregador das CDNs", regex=True, flags=re.S)
    texto = _uma_vez(texto, r"^<head>\r?$", "<head>\n<!--ZELADORIA:CONFIG-->", "o <head>", regex=True, flags=re.M)
    texto = _uma_vez(texto, "var ui = { tab: 'overview',", "var ui = { tab: (window.ZELADORIA_ABA || 'overview'),",
                     "a aba inicial")
    texto = texto.replace("voce@gridco.com.br", "voce@empresa.com.br")
    return texto


# ── o visual da Zeladoria (etapa 3) ────────────────────────────────────────────────────────────────────────────────
# A paleta entra DEPOIS do CSS do clone e redefine as variáveis dele nos dois temas; o servidor marca o <html> com
# data-theme="dark" ou "light", pelo tema do Nexus, e por isso o seletor com o atributo vence o :root e o
# prefers-color-scheme do Radar. Levi, 03/11/2026: "use as cores Black 030407, Blue 1558c9, lime D4FF24", só na
# Zeladoria. No claro, o lima é só superfície (texto preto em cima), e o texto de destaque é um lima escuro legível: o
# lima puro no branco não passa no contraste, como o verde Grid (DESIGN.md). O azul faz o papel de informação.
PALETA = """<style id="zeladoria-paleta">
/* A paleta da Zeladoria (nexus/torres/zeladoria/CLAUDE.md): as três cores e as variáveis do clone, nos dois temas.
   Vem depois do CSS do clone e vence ele (o <html> sempre tem o data-theme, posto pelo Nexus). */
:root[data-theme="dark"] {
  --zel-preto: #030407; --zel-azul: #1558c9; --zel-lima: #d4ff24;
  --zel-sobre-cor: #ffffff; --zel-veu: rgba(3,4,7,0.72); --zel-linha-clara: rgba(255,255,255,0.22);
  --sidebar-bg: var(--zel-preto); --sidebar-bg-2: #0b0e14; --sidebar-border: #232a36; --sidebar-ink: #c3cad7;
  --sidebar-ink-muted: #96a0b4; --sidebar-active-bg: var(--zel-lima); --sidebar-active-ink: var(--zel-preto);
  --bg: var(--zel-preto); --surface: #0b0e14; --surface-2: #141923; --surface-sunken: var(--zel-preto);
  --border: #232a36; --ink: #e9eef6; --ink-2: #c3cad7; --ink-muted: #96a0b4;
  --accent: var(--zel-lima); --accent-strong: var(--zel-lima); --accent-ink: var(--zel-preto);
  --accent-soft: rgba(212,255,36,0.14);
  --good: #4ade80; --good-soft: rgba(74,222,128,0.16); --warn: #ffd83d; --warn-soft: rgba(255,216,61,0.16);
  --critical: #ff5b6e; --critical-soft: rgba(255,91,110,0.16);
  --info: #7aa2f7; --info-soft: rgba(21,88,201,0.28); --frozen: #7fb8ff; --frozen-soft: rgba(127,184,255,0.16);
  --neutral-pill: rgba(255,255,255,0.07); --shadow: 0 1px 2px rgba(0,0,0,0.5), 0 3px 14px rgba(0,0,0,0.5);
  --fx-aberto: #a6c93a; --fx-prov: var(--warn);
}
:root[data-theme="light"] {
  --zel-preto: #030407; --zel-azul: #1558c9; --zel-lima: #d4ff24;
  --zel-sobre-cor: #ffffff; --zel-veu: rgba(3,4,7,0.45); --zel-linha-clara: rgba(3,4,7,0.18);
  --sidebar-bg: var(--zel-preto); --sidebar-bg-2: #0b0e14; --sidebar-border: #232a36; --sidebar-ink: #c3cad7;
  --sidebar-ink-muted: #96a0b4; --sidebar-active-bg: var(--zel-lima); --sidebar-active-ink: var(--zel-preto);
  --bg: #fcfcfc; --surface: #ffffff; --surface-2: #f5f6f8; --surface-sunken: #f3f5f7;
  --border: #e3e7eb; --ink: var(--zel-preto); --ink-2: #475569; --ink-muted: #5a6475;
  --accent: var(--zel-lima); --accent-strong: #4b5e00; --accent-ink: var(--zel-preto); --accent-soft: #f2fbd0;
  --good: #166b36; --good-soft: #e3f5e9; --warn: #7a5200; --warn-soft: #fbeeda;
  --critical: #b42230; --critical-soft: #fae1de;
  --info: var(--zel-azul); --info-soft: #e3ecfa; --frozen: #0a5fc4; --frozen-soft: #dcecfb;
  --neutral-pill: #eceef2; --shadow: 0 1px 2px rgba(3,4,7,0.06), 0 3px 12px rgba(3,4,7,0.07);
  --fx-aberto: #8fb31a; --fx-prov: #d9921c;
}
/* os títulos na fonte de título do Nexus */
.page-title, .modal-head h3 { font-family: "Raleway", "Poppins", sans-serif; }
/* a 375 px (a prova do Nexus) nada rola de lado: a grade de duas colunas posta no estilo do elemento cai para uma, e o
   botão de rótulo longo ("Acompanhamento de Pagamentos - Terceirizados") quebra a linha */
@media (max-width: 600px) {
  .grid[style*="grid-template-columns"] { grid-template-columns: 1fr !important; }
  .btn { white-space: normal; }
  /* a tabela larga rola dentro da própria caixa (DESIGN.md), não a página */
  table { display: block; max-width: 100%; overflow-x: auto; }
  /* a linha de botões, etiquetas e filtros quebra em vez de empurrar a página */
  .head-actions, .chiprow, [style*="display:flex"], [style*="display: flex"] { flex-wrap: wrap; }
  select, input, textarea { max-width: 100%; }
  .card { min-width: 0; max-width: 100%; overflow-x: auto; }
}
</style>
"""
FONTES_RADAR = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,500;0,600;'
                '0,700;0,800;1,500&family=IBM+Plex+Mono:wght@400;500;600&display=swap">')
FONTES_NEXUS = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700'
                '&family=Raleway:wght@700;800&family=IBM+Plex+Mono:wght@400;500&display=swap">')

# a cor fixa das regras do CSS do clone (fora as reservas dentro de var(), que só saem)
CSS_DECLARACOES = {
    "background: #0d0c14": "background: var(--bg)",
    "box-shadow: 0 10px 44px rgba(0,0,0,0.5)": "box-shadow: var(--shadow)",
    "background: #5C9A22": "background: var(--accent)",
    "box-shadow: 0 10px 34px rgba(92,154,34,0.4)": "box-shadow: var(--shadow)",
    "border: 3px solid rgba(255,255,255,0.22)": "border: 3px solid var(--zel-linha-clara)",
    "border-top-color: #8FD14F": "border-top-color: var(--accent)",
    "background: rgba(23,32,0,0.16)": "background: var(--accent-soft)",
    "color: #8A5A08": "color: var(--warn)",
    "color: #963025": "color: var(--critical)",
    "color: #145E85": "color: var(--frozen)",
    "background: rgba(10,14,10,0.5)": "background: var(--zel-veu)",
    "box-shadow: 0 1px 3px rgba(0,0,0,.08)": "box-shadow: var(--shadow)",
    "#F4D8A6 3px 6px": "var(--warn-soft) 3px 6px",
    "#D4D5F4 3px 6px": "var(--info-soft) 3px 6px",
}

# a cor fixa dos estilos que o JavaScript escreve (style="..."): a de aviso e a de apoio viram a variável do mesmo papel.
# A cor CALCULADA (a escala de calor da criticidade, rgb(' + rgb.join(',') + ')) fica: é cor de dado, igual nos dois
# temas, como no resto do Nexus. O CSS do relatório de impressão fica de fora (a folha é sempre papel branco).
JS_CORES = {
    "var(--critical)": ("rgb(196,61,48)", "#c43d30", "#c0392b", "#d0392f", "#d9453a", "rgba(196,61,48,0.75)",
                        "rgba(196,61,48,0.9)", "rgba(196,61,48,.5)"),
    "var(--critical-soft)": ("rgba(196,61,48,0.10)", "rgba(196,61,48,0.06)", "rgba(196,61,48,0.12)",
                             "rgba(196,61,48,0.15)"),
    "var(--warn)": ("rgb(185,112,11)", "#b9700b", "#d9921c", "#d98c1f", "#ef9a1a", "#e3a43a", "rgb(214,110,20)",
                    "rgb(230,126,34)", "rgb(214,84,40)", "rgb(226,183,20)"),
    "var(--warn-soft)": ("rgba(185,112,11,0.35)",),
    "var(--good)": ("rgb(46,158,82)", "#2e9e52", "rgb(46,120,82)", "rgba(46,158,82,0.55)", "rgba(46,158,82,0.6)"),
    "var(--good-soft)": ("rgba(46,158,82,0.10)",),
    "var(--info)": ("#5b5fc7", "#4462c4", "#7276d6"),
    "var(--info-soft)": ("#e3e4fa",),
    "var(--frozen)": ("#2f7fb0", "rgb(47,127,176)", "rgba(47,127,176,.5)", "#9fd3ff"),
    "var(--accent-strong)": ("#5c9a22",),
    "var(--accent)": ("#a0d439",),
    "var(--fx-aberto)": ("#a6d27a",),
    "var(--accent-soft)": ("rgba(92,154,34,0.08)",),
    "var(--ink-muted)": ("#6b7584", "#4a5260", "#7a8392", "#8a96a3", "#9aa3b0", "rgb(130,138,150)",
                         "rgb(120,128,140)", "rgb(110,118,130)", "#6b6880"),
    "var(--border)": ("#e4e7ec", "#e3e7ec", "#cdd3db", "#b9c2cb", "#eef0f3"),
    "var(--surface-2)": ("#f3f5f7", "#f5f6f8"),
    "var(--zel-sobre-cor)": ("#fff",),
}
_PROP_COR = (r"(?:color|background(?:-color|-image)?|border(?:-[a-z]+)*|fill|stroke|outline(?:-color)?|box-shadow)"
             r"\s*:\s*")
# a cor de DADO fica igual nos dois temas, como no resto do Nexus (DESIGN.md): a do avatar de cada pessoa e a escala de
# dias de atraso das rondas
COR_DE_DADO = (r"var AVATAR_COLORS = \[[^\]]*\];", r"function raCorFaixa\(f\)\{[^\n]*")

# os emojis da interface (a mesma faixa dos testes do Nexus, mais as setas e relógios que viram emoji no celular)
EMOJI = "[\U0001F000-\U0001FAFF☀-➿⬀-⯿⏩-⏺]️?"
# o emoji que era o botão inteiro vira palavra (sem ele o botão ficaria vazio)
EMOJI_SOZINHO = {"🗑": "Excluir", "✎": "Editar", "✏️": "Editar", "✏": "Editar", "✕": "×", "⚠": "Atenção",
                 "🧮": "Simular", "✓": "OK", "✔": "OK", "🕘": "Histórico", "📄": "Doc", "👁": "Ver", "📷": "Fotos"}


def _fora_da_impressao(texto: str, fazer) -> str:
    """Aplica `fazer` no texto todo, menos no CSS do relatório de impressão (papel branco nos dois temas)."""
    ini = texto.index("var css = '@page{size:A4 landscape")
    fim = texto.index("';\n", ini) + 3
    return fazer(texto[:ini]) + texto[ini:fim] + fazer(texto[fim:])


def _cores_do_js(texto: str) -> str:
    guardadas = []

    def guardar(m):
        guardadas.append(m.group(0))
        return f"@@DADO{len(guardadas) - 1}@@"
    for padrao in COR_DE_DADO:
        texto = re.sub(padrao, guardar, texto)
    texto = re.sub(r"var\((--[a-z0-9-]+),\s*#[0-9a-fA-F]{3,8}\)", r"var(\1)", texto)
    for var, fixas in JS_CORES.items():
        for fixa in sorted(fixas, key=len, reverse=True):
            c = re.escape(fixa)
            # só onde é cor: valor de propriedade, atributo fill/stroke ou texto que é a cor inteira ('rgb(...)')
            texto = re.sub("(" + _PROP_COR + r"[^;\"'<>]*?)" + c + r"(?![0-9a-fA-F])",
                           lambda m, v=var: m.group(1) + v, texto, flags=re.I)
            texto = re.sub(r"((?:fill|stroke)=)([\"'])" + c + r"\2",
                           lambda m, v=var: m.group(1) + m.group(2) + v + m.group(2), texto, flags=re.I)
            texto = re.sub(r"(['\"])" + c + r"\1", lambda m, v=var: m.group(1) + v + m.group(1), texto, flags=re.I)
            # a borda montada como texto ('2px solid rgb(...)')
            texto = re.sub(r"((?:solid|dashed|dotted)\s+)" + c, lambda m, v=var: m.group(1) + v, texto, flags=re.I)
    return re.sub(r"@@DADO(\d+)@@", lambda m: guardadas[int(m.group(1))], texto)


def _emojis(texto: str) -> str:
    texto = texto.replace("'★ '", "'nota '").replace("(breve ? ' ⏳' : '')", "(breve ? ' · vence logo' : '')")
    texto = re.sub(r"ico:'" + EMOJI + "'", "ico:''", texto)

    def sozinho(m):
        e = m.group(2)
        return m.group(1) + EMOJI_SOZINHO.get(e, EMOJI_SOZINHO.get(e[0], "")) + m.group(3)
    texto = re.sub(r"([>'\"])(" + EMOJI + r")([<'\"+])", sozinho, texto)
    return re.sub(EMOJI + " ?", "", texto)


def vestir(texto: str) -> str:
    texto = _uma_vez(texto, FONTES_RADAR, FONTES_NEXUS, "as fontes do Radar")
    texto = re.sub(r'"Inter"', '"Poppins"', texto)
    texto = texto.replace("font-family:Inter,", "font-family:Poppins,")

    def css(bloco):
        bloco = re.sub(r"var\((--[a-z0-9-]+),\s*#[0-9a-fA-F]{3,8}\)", r"var(\1)", bloco)
        for velho, novo in CSS_DECLARACOES.items():
            bloco = bloco.replace(velho, novo)
        bloco = re.sub(r"(" + _PROP_COR + r")#fff\b", r"\1var(--zel-sobre-cor)", bloco)
        return bloco
    texto = re.sub(r"(<style>)(.*?)(</style>)", lambda m: m.group(1) + css(m.group(2)) + m.group(3), texto,
                   count=0, flags=re.S)
    texto = _fora_da_impressao(texto, _cores_do_js)
    texto = _emojis(texto)
    texto = _uma_vez(texto, "var t = localStorage.getItem('rf_tema');",
                     "var t = window.ZELADORIA_TEMA || localStorage.getItem('rf_tema');", "o tema salvo do Radar")
    return _uma_vez(texto, "\n</head>", "\n" + PALETA + "</head>", "o fim do <head>")


def sobras(texto: str, de_para: dict) -> list:
    nomes = {k.lower() for k in de_para if not k.startswith("_")}
    padrao = re.compile("|".join(re.escape(n) for n in sorted(nomes)), re.IGNORECASE)
    return [i for i, linha in enumerate(texto.splitlines(), 1) if padrao.search(linha)]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--origem", required=True)
    p.add_argument("--nomes", required=True)
    p.add_argument("--saida", required=True)
    a = p.parse_args(argv)
    texto = Path(a.origem).read_text(encoding="utf-8")
    de_para = json.loads(Path(a.nomes).read_text(encoding="utf-8"))
    try:
        limpo = vestir(limpar(texto, de_para))
    except TrocaFalhou as e:
        print(f"parei: {e}", file=sys.stderr)
        return 1
    linhas = sobras(limpo, de_para)
    if linhas:
        print(f"parei: sobraram nomes em {len(linhas)} linha(s): {linhas[:30]}", file=sys.stderr)
        return 1
    saida = Path(a.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(limpo, encoding="utf-8", newline="\n")
    print(f"ok: {saida} ({len(limpo.splitlines())} linhas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

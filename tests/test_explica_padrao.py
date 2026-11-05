"""O "!" amarelo das explicações é o padrão do Nexus (05/11/2026, Levi: "Disclaimers de 'entenda o que aconteceu' 'o que é'
precisa estar em um símbolo de exclamação amarelo no estilo segurança > extintores ... sempre que uma tela for criada tenha
esse estilo, padrão nexus!").

O que estes testes seguram: toda explicação de como a tela funciona ("Entenda esta tela", "De onde vem.", "Como se conta.",
"Como funciona", "Como ler:", "Como vale.", em <b> ou em <strong>) mora dentro do `{% call explica(...) %}` de
`_explica.html` (ou do `aviso` da Segurança, que passa para ele), nunca solta na tela; e o componente abre a caixa com o
título e o texto."""
import re
from pathlib import Path

from flask import render_template_string

RAIZ = Path(__file__).resolve().parent.parent / "nexus"
# o clone do OS Creator e o da Zeladoria ficam iguais aos apps de origem de propósito (os README deles); o modo TV do
# Mapa de risco mostra a legenda inteira na tela, sem clique (não há quem clique numa TV)
FORA = ("torres/oscreator/os_creator/", "torres/zeladoria/clone/", "templates/_explica.html", "hseq/_legenda.html",
        "performance/mapa_tv.html", "performance/_mapa_legenda.html")
# em <b> ou <strong> (2ª revisão de 05/11/2026: o "Como vale." solto em <strong> passava)
MARCAS = re.compile(r"<(?:b|strong)>(?:De onde vem|Como se conta|Como funciona|Como ler|Como vale)[.:]?</(?:b|strong)>"
                    r"|Entenda esta tela|>Como funciona</h\d>")
CALL = re.compile(r"{%-?\s*call\s+(?:explica|aviso)\(")
FIM = re.compile(r"{%-?\s*endcall\s*-?%}")


def _sem_comentarios(t: str) -> str:
    return re.sub(r"{#.*?#}", lambda m: " " * len(m.group(0)), t, flags=re.S)


def _dentro_do_explica(t: str, pos: int) -> bool:
    ini = [m.start() for m in CALL.finditer(t) if m.start() <= pos]
    if not ini:
        return False
    fim = FIM.search(t, ini[-1])
    return fim is not None and fim.start() > pos


def test_a_marca_pega_o_strong_e_o_como_vale():
    """2ª revisão de 05/11/2026: o "Como vale." solto na aba dos administradores do App não era pego, porque vinha em
    <strong> e a marca só olhava o <b> (e não tinha o "Como vale")."""
    for solta in ("<strong>Como vale.</strong>", "<b>Como vale.</b>", "<strong>De onde vem.</strong>",
                  "<strong>Como ler:</strong>"):
        assert MARCAS.search(solta), solta
    assert not MARCAS.search("<strong>Gravado.</strong>") and not MARCAS.search("<strong>Nada mudou.</strong>")


def test_nenhuma_explicacao_solta_na_tela():
    soltas = []
    for p in sorted(RAIZ.rglob("*.html")):
        rel = p.relative_to(RAIZ).as_posix()
        if any(f in rel for f in FORA):
            continue
        t = _sem_comentarios(p.read_text(encoding="utf-8"))
        for m in MARCAS.finditer(t):
            if not _dentro_do_explica(t, m.start()):
                soltas.append(f"{rel}:{t.count(chr(10), 0, m.start()) + 1}: {m.group(0)}")
    assert not soltas, "explicação fora do \"!\" do título (DESIGN.md, seção 6):\n" + "\n".join(soltas)


def test_o_componente_abre_a_caixa_com_o_titulo_e_o_texto(app):
    with app.test_request_context("/"):
        html = render_template_string(
            '{% from "_explica.html" import explica, termo %}'
            '{% call explica("Entenda esta tela", "o pé") %}<p><b>De onde vem.</b> Do livro X.</p>{% endcall %}'
            '{% call explica("Como ler", termos=True) %}{{ termo("Atrasado", "critico") }}<dd>venceu</dd>{% endcall %}')
    assert '<details class="gc-explica"><summary class="gc-explica-bt" title="Entenda esta tela"' in html
    assert '<div class="gc-explica-texto"><p><b>De onde vem.</b> Do livro X.</p></div>' in html
    assert '<p class="gc-explica-pe">o pé</p>' in html
    assert '<dl class="gc-explica-termos"><dt><span class="gc-ponto gc-ponto--critico">Atrasado</span></dt><dd>venceu</dd></dl>' in html


def test_o_aviso_da_seguranca_passa_para_o_componente(app):
    with app.test_request_context("/"):
        html = render_template_string('{% from "hseq/_legenda.html" import aviso, termo %}'
                                      '{% call aviso("Como cada extintor entra") %}{{ termo("Atrasado", "critico") }}'
                                      '<dd>venceu</dd>{% endcall %}')
    assert 'class="gc-explica"' in html and 'class="gc-explica-termos"' in html and "venceu" in html


def test_o_estilo_e_o_fechar_sao_globais():
    css = (RAIZ / "static" / "nexus.css").read_text(encoding="utf-8")
    base = (RAIZ / "templates" / "base.html").read_text(encoding="utf-8")
    assert ".gc-explica-bt{" in css and ".gc-explica-caixa{" in css and ".gc-titulo-explica{" in css
    assert 'details.gc-explica[open]' in base

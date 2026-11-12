"""Os filtros do Nexus no padrão do Histórico de OS do OS Creator Web (12/11/2026, Levi: "em todas as partes do nexo, eu
quero que os filtros sejam no padrão de nexos, OS Creator, histórico de OS [...] Com o mesmo estilo, as mesmas
funcionalidades [...] Não é só um cartão suspenso" e "Para todas as abas do COS que tiver filtro, eu quero esse padrão").

O que estes testes seguram: toda tela do COS com <select> de filtro num formulário GET leva o `data-fo` e o script do
padrão; o Comando > Usinas também; o script e o estilo têm as funções do modelo (a lista digitável, o Aplicar que só
acende com mudança, as etiquetas, o Limpar tudo); e nada vai para as <select> antes do Aplicar."""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
COS = RAIZ / "nexus" / "torres" / "cos" / "templates" / "cos"
JS = (RAIZ / "nexus" / "static" / "filtros-os.js").read_text(encoding="utf-8")
CSS = (RAIZ / "nexus" / "static" / "nexus.css").read_text(encoding="utf-8")
_FORM = re.compile(r"<form\b([^>]*)>(.*?)</form>", re.S)


def _formularios_de_filtro(html: str):
    """(atributos, corpo) de cada formulário GET com <select> (o de gravar, POST, não é filtro)."""
    return [(a, c) for a, c in _FORM.findall(html) if 'method="post"' not in a and "<select" in c]


def test_toda_tela_do_cos_com_filtro_usa_o_padrao():
    com_filtro = []
    for arq in sorted(COS.glob("*.html")):
        html = arq.read_text(encoding="utf-8")
        for atributos, _corpo in _formularios_de_filtro(html):
            assert "data-fo" in atributos, f"{arq.name}: o formulário de filtro não leva data-fo"
            com_filtro.append(arq.name)
    assert com_filtro == ["_monitoramento_corpo.html", "acionamentos.html", "eventos.html", "normalizacoes.html",
                          "ocorrencias.html", "os_abertas.html"]
    # o script do padrão na página de cada um (o corpo do Monitoramento é trocado a cada 30 s: o script fica na página)
    for nome in ("monitoramento.html", "acionamentos.html", "eventos.html", "normalizacoes.html", "ocorrencias.html",
                 "os_abertas.html"):
        assert "filename='filtros-os.js'" in (COS / nome).read_text(encoding="utf-8"), nome
    assert 'data-fo="local"' in (COS / "normalizacoes.html").read_text(encoding="utf-8")     # a que filtra na página
    # o painel aberto segura a troca do corpo do Monitoramento
    assert ".fo-painel:not([hidden])" in (RAIZ / "nexus" / "static" / "cos" / "monitoramento.js").read_text(encoding="utf-8")


def test_o_comando_usinas_usa_o_mesmo_componente():
    html = (RAIZ / "nexus" / "torres" / "comando" / "templates" / "comando" / "usinas.html").read_text(encoding="utf-8")
    assert "data-fo" in html and "filename='filtros-os.js'" in html and "multiple" in html
    assert "cmu-fl" not in html
    assert "cmu-fl" not in (RAIZ / "nexus" / "static" / "comando.css").read_text(encoding="utf-8")
    assert "cmu-fl" not in (RAIZ / "nexus" / "static" / "comando-usinas.js").read_text(encoding="utf-8")


def test_o_script_tem_as_funcoes_do_modelo():
    for trecho in ("Digite para filtrar",                # a lista digitável
                   '"Sem alterações"', "alterações",     # o Aplicar que só acende com mudança
                   "Limpar tudo", "Tirar este filtro",   # as etiquetas
                   "Fechar sem aplicar", '"Escape"',     # fechar descarta
                   "ArrowDown",                          # as setas andam
                   'getAttribute("data-fo") === "local"', "MutationObserver"):
        assert trecho in JS, trecho
    # nada vai para a <select> antes do Aplicar: só o `porValor` escreve nela, e só o `aplicarAgora` o chama
    assert JS.count("porValor(") == 3 and "function aplicarAgora" in JS
    corpo = JS.split("function aplicarAgora", 1)[1].split("abrir.addEventListener", 1)[0]
    assert corpo.count("porValor(") == 2
    # o que acontece dentro do painel não chega ao formulário da tela
    assert 'painel.addEventListener(ev, function (e) { e.stopPropagation(); })' in JS


def test_o_estilo_e_da_casa_e_vale_nos_dois_temas():
    bloco = CSS.split("/* ── Os filtros do Nexus no padrão do Histórico de OS", 1)[1]
    for classe in (".fo-barra", ".fo-painel", ".fo-procura", ".fo-aplicar", ".fo-chip", ".fo-uni .fo-op.sel",
                   ".fo-cel.mudou"):
        assert classe in bloco, classe
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", bloco), "cor só por token"
    assert ".fo-barra [data-fo-some],.fo-barra ~ [data-fo-some]{display:none}" in bloco

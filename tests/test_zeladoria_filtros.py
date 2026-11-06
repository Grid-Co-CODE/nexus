"""Os filtros da Zeladoria no painel suspenso do Histórico de OS (06/11/2026, nexus/static/zeladoria/filtros.js e .css).

A peça mexe só no DOM do clone: acha os campos `flt-*` e as listas `.msf` do Radar, esconde, e no Aplicar dispara o
`change` deles. Estes testes guardam o que ela supõe do clone (que um Radar novo pode mudar) e a regra de cor do Nexus.
O comportamento (abrir, digitar, aplicar, etiqueta, ×, Esc, Limpar tudo) foi provado no navegador, nas 18 telas."""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
JS = (RAIZ / "nexus" / "static" / "zeladoria" / "filtros.js").read_text(encoding="utf-8")
CSS = (RAIZ / "nexus" / "static" / "zeladoria" / "filtros.css").read_text(encoding="utf-8")
CLONE = (RAIZ / "nexus" / "torres" / "zeladoria" / "clone" / "radar.html").read_text(encoding="utf-8")
NEXUS_CSS = (RAIZ / "nexus" / "static" / "nexus.css").read_text(encoding="utf-8")


def test_a_rota_do_clone_carrega_o_painel(logado):
    html = logado.get("/t/zeladoria/app?aba=criticidade").get_data(as_text=True)
    assert "/static/zeladoria/filtros.js" in html and "/static/zeladoria/filtros.css" in html
    # depois da ponte: o painel lê o #app que o Radar desenha
    assert html.index("zeladoria/ponte.js") < html.index("zeladoria/filtros.js")


def test_o_clone_ainda_tem_o_que_o_painel_procura():
    # os filtros de um valor: <select id="flt-*"> pelo selectFiltro, ligados no change
    assert len(set(re.findall(r"selectFiltro\('(flt-[a-z-]+)'", CLONE))) >= 60
    assert "addEventListener('change'" in CLONE
    # os de vários valores: .msf[data-msf] com as marcas .msf-check e os botões de marcar e desmarcar todos
    for marca in ('class="msf" data-msf="', "msf-check", "data-msf-idx", "data-msf-all", "data-msf-none", "data-msf-toggle"):
        assert marca in CLONE, marca
    # o Radar refaz a tela trocando o #app inteiro: é isso que o MutationObserver do painel vê
    assert "document.getElementById('app').outerHTML = renderShell()" in CLONE


def test_os_que_escolhem_a_tela_ficam_fora_e_existem_no_clone():
    fora = re.search(r"var FORA = \{([^}]*)\}", JS).group(1)
    ids = re.findall(r'"(flt-[a-z-]+)"', fora)
    assert set(ids) == {"flt-perm-outro-usuario", "flt-fin-geral-prev", "flt-gj-mes"}
    for i in ids:
        assert i in CLONE, f"{i} sumiu do clone: tire da FORA"


def test_cor_so_por_token_e_todo_token_existe():
    sem_coment = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", sem_coment)
    proprios = set(re.findall(r"(--zf-[a-z0-9-]+)\s*:", sem_coment))
    do_nexus = set(re.findall(r"(--[a-z0-9-]+)\s*:", NEXUS_CSS))
    usados = set(re.findall(r"var\((--[a-z0-9-]+)\)", sem_coment))
    faltam = sorted(u for u in usados if u not in proprios and u not in do_nexus)
    assert not faltam, faltam


def test_o_celular_vira_folha_de_baixo_para_cima():
    celular = CSS[CSS.index("@media (max-width:639px)"):]
    assert "position:fixed" in celular and "bottom:0" in celular and ".zf-veu" in celular

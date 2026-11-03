"""Os filtros do Histórico de OS no modelo A (Levi, 03/11/2026): a barra de uma linha, as etiquetas dos filtros aplicados e o
painel suspenso com o Aplicar no rodapé, e tudo digitável.

Os pedidos do Levi: "selecionar os filtros sem carregar a cada filtro, [...] só filtra mesmo se aplicar" (a regra do Aplicar,
da manhã de 03/11); "refaz esse modelo de filtros [...] algo minimalista e moderno ao mesmo tempo"; "opção A, suspenso com um
botão de aplicar no final"; "quero que todas as opções do filtro sejam digitáveis para facilitar encontrar o que quero".

Duas camadas:
- o que o HTML que o servidor monta tem (a barra, o painel, os campos, os selects escondidos no formulário) e o que o CSS não
  pode ter (cor fora dos tokens);
- o comportamento, no node: o HTML de verdade da página é lido por um DOM de mentira (`historico_pagina_falsa.js`) que roda o
  script que está nela e o `os_busca.js` do clone, e o teste mexe como a pessoa mexe (clicar, digitar, teclar, passar o tempo).
  O `fetch` e o envio do formulário só anotam o que a página mandou: nada vai à rede, e o conftest ainda bloqueia o Fracttal.
Nenhum nome real: pessoas, usinas e clientes são de mentira (o repositório é público).
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
from os_web import criar_app  # noqa: E402

WEB = Path(ponte.RAIZ_CLONE, "os_web")
TEMPLATE = WEB / "templates" / "historico.html"
OS_CSS = WEB / "static" / "os.css"
BUSCA_JS = WEB / "static" / "os_busca.js"
FALSA = Path(__file__).resolve().parent / "historico_pagina_falsa.js"

JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira
USINA_SAO = "Cliente X - Usina São Exemplo - UF"
USINA_ACUDE = "Cliente X - Usina Açude Exemplo - UF"
USINA_TRES = "Cliente Y - Usina Três - UF"
USINA_QUATRO = "Cliente Y - Usina Quatro - UF"
USINAS = [USINA_SAO, USINA_ACUDE, USINA_TRES, USINA_QUATRO]
PESSOAS = [{"id_account": 11, "nome": "Ana Teste Silva"}, {"id_account": 12, "nome": "João Exemplo"},
           {"id_account": 13, "nome": "Zélia Souza"}]
PERIODO = "de=2026-10-04&ate=2026-11-03"            # fixo: o padrão da página depende do relógio do servidor


@pytest.fixture
def cli(monkeypatch):
    import requests

    def sem_rede(*a, **k):                    # a cota do Fracttal é da empresa: aqui nada sai da máquina
        raise AssertionError("o teste tentou ir à rede")
    monkeypatch.setattr(requests.Session, "request", sem_rede)
    monkeypatch.setattr(api, "load_assets_cached", lambda *a, **k: [
        {"id": 1, "code": "TST-INV11", "label": "Inversor 1.1", "description": "Inversor 1.1", "tipo": "Inversor",
         "usina": USINA_SAO, "cliente": "Cliente X"}])
    monkeypatch.setattr(api, "ler_pessoal", lambda *a, **k: [])
    monkeypatch.setattr(api, "get_labels", lambda *a, **k: [{"id": 7, "description": "PERFORMANCE"},
                                                            {"id": 8, "description": "Garantia"}])
    monkeypatch.setattr(api, "get_pessoas_contas", lambda *a, **k: {"pessoas": [dict(p) for p in PESSOAS], "eu": 11})
    monkeypatch.setattr(api, "_code_to_loc", lambda *a, **k: {})
    monkeypatch.setattr(api, "_read_asset_cache", lambda *a, **k: [])
    linhas = [{"id": 900 + i, "folio": str(15000 + i), "cliente": u.split(" - ")[0], "usina": u, "tipo": "Inversor",
               "ativo": "Inversor 1.1", "descricao": "Teste %d" % i, "status": "Em Processo" if i % 2 else "Concluída",
               "data": "2026-10-07T10:00:00"} for i, u in enumerate(USINAS)]
    monkeypatch.setattr(api, "list_minhas_os", lambda *a, **k: [dict(x) for x in linhas])
    from os_web import rotas

    def limpar_a_memoria():            # o "Criado por" de cada pessoa fica 10 min na memória do processo (rotas._MEMO): sem isto,
        with rotas._MEMO_LOCK:         # as pessoas de um teste apareceriam no seguinte, e o teste das pessoas vazias não valeria
            rotas._MEMO.clear()
    limpar_a_memoria()
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Pessoa Teste", "email": "teste@exemplo.invalid", "perfil": "ADMINISTRATOR"}
    yield c
    limpar_a_memoria()


def _pagina(cli, consulta="") -> str:
    r = cli.get("/os/historico?" + PERIODO + ("&" + consulta if consulta else ""))
    assert r.status_code == 200
    return r.get_data(as_text=True)


# ══ 1. o que o servidor monta ═════════════════════════════════════════════════════════════════════════════════════════════
def test_a_barra_tem_os_controles_do_modelo_a_na_ordem_do_desenho(cli):
    """Uma linha só: as abas, a busca por texto, o Buscar OS, o período, o Filtros com a contagem e, à direita, só o ícone de
    Exportar e o de Atualizar (com o title e os atalhos de sempre). O "Lista das" fica na linha do resumo da tabela."""
    h = _pagina(cli)
    ordem = ['class="fl-barra"', 'class="fl-seg"', 'id="busca_no"', 'id="busca_os"', 'id="b_periodo"', 'id="b_filtros"',
             'id="fl_n"', 'id="b_export"', 'id="b_atualizar"', 'id="fl_painel"']
    pos = [h.index(x) for x in ordem]
    assert pos == sorted(pos), "a ordem da barra mudou"
    # as três visões, a ativa marcada
    assert re.findall(r'<button type="button" data-modo="(\w+)" class="(on)?"', h)[:3] == [
        ("criadas", "on"), ("atribuidas", ""), ("cos", "")]
    # Exportar e Atualizar: só ícone, mas com nome e os atalhos de hoje
    exportar = re.search(r'<button[^>]*id="b_export"[^>]*>', h).group(0)
    atualizar = re.search(r'<button[^>]*id="b_atualizar"[^>]*>', h).group(0)
    assert "[Ctrl+E]" in exportar and 'aria-label="Exportar"' in exportar
    assert 'type="submit"' in atualizar and "[F5]" in atualizar and 'aria-label="Atualizar"' in atualizar
    assert "Exportar</button>" not in h and ">Limpar filtros<" not in h                   # sem os botões de texto de antes
    # o período mostra o aplicado, e a contagem do Filtros nasce escondida (o script a acende)
    assert re.search(r'id="fl_periodo_txt">04/10 – 03/11<', h)
    assert re.search(r'<span class="fl-badge" id="fl_n" hidden>', h)
    # "Lista das HH:MM · atualiza a cada 10 min", apagado, na linha do resumo
    resumo = h[h.index('class="fl-resumo"'):h.index('id="tab_hist"')]
    assert 'id="hint"' in resumo and "Lista das " in resumo and "atualiza a cada 10 min" in resumo
    assert h.index('id="lbl_auto"') > h.index('class="fl-resumo"')                       # não está mais na barra


def test_o_painel_traz_o_periodo_primeiro_os_sete_campos_e_o_rodape(cli):
    h = _pagina(cli)
    painel = h[h.index('id="fl_painel"'):h.index("</form>")]
    ordem = ['data-filtro="periodo"', 'data-filtro="pessoa"', 'data-filtro="etiqueta"', 'data-filtro="status"',
             'data-filtro="cliente"', 'data-filtro="usina"', 'data-filtro="tipo"', 'data-filtro="tarefa"', 'id="b_painel_limpar"',
             'id="fl_nalt"', 'id="b_aplicar"']
    pos = [painel.index(x) for x in ordem]
    assert pos == sorted(pos), "a ordem do painel mudou"
    assert [m for m in re.findall(r'data-atalho="([\w]+)"', painel)] == ["7", "30", "mes"]
    assert [m for m in re.findall(r'<button[^>]*data-atalho[^>]*>([^<]+)<', painel)] == ["7 dias", "30 dias", "Este mês"]
    assert re.search(r'<button type="button" class="fl-btn fl-lima" id="b_aplicar" disabled>Aplicar</button>', painel)
    assert re.search(r'id="b_painel_limpar">Limpar</button>', painel)
    assert 'role="dialog"' in h and 'id="fl_painel"' in h and re.search(r'id="fl_painel"[^>]*hidden', h)
    # o painel está dentro do formulário: os campos dele vão no envio, os mesmos de antes
    assert h.index('id="f_hist"') < h.index('id="fl_painel"') < h.index("</form>")
    nomes = set(re.findall(r'<(?:input|select)[^>]*\bname="(\w+)"', h[h.index('id="f_hist"'):h.index("</form>")]))
    assert nomes == {"modo", "atualizar", "pessoa", "etiqueta", "status", "de", "ate", "busca"}


def test_os_selects_do_servidor_ficam_no_formulario_e_cada_campo_e_digitavel(cli):
    """"Mantenha o <select name="pessoa"> e o <select name="etiqueta"> no formulário, escondidos, e desenhe o campo digitável por
    cima": o servidor, o formulário e os testes que leem select[name=...] seguem iguais. Todas as listas levam a busca (antes só a
    de Usina e as de 6 opções ou mais)."""
    h = _pagina(cli)
    assert '<select name="pessoa">' in h and '<select name="etiqueta">' in h
    for nome in ("pessoa", "etiqueta"):
        cel = re.search(r'<div class="fl-cel" data-filtro="%s"([^>]*)>' % nome, h).group(1)
        assert "data-campo-proprio" in cel                       # o os_busca não põe a busca por cima do <select>
        assert re.search(r'<details class="os-multi hf-multi fl-uni" data-nome="%s" data-select="%s" data-busca="1">' % (nome, nome), h)
    for nome in ("status", "cliente", "usina", "tipo", "tarefa"):
        assert re.search(r'<details class="os-multi hf-multi" data-nome="%s"[^>]*data-busca="1">' % nome, h), nome
    # Criado por: as pessoas estão no select e na lista de escolha, na mesma ordem, e "Todos os usuários" vem primeiro
    sel = re.search(r'<select name="pessoa">(.*?)</select>', h, re.S).group(1)
    uni = re.search(r'data-nome="pessoa" data-select="pessoa".*?</details>', h, re.S).group(0)
    assert re.findall(r'<option value="([^"]*)"', sel) == re.findall(r'<input type="radio" value="([^"]*)"', uni) == ["TODOS", "11", "12", "13"]
    # no celular e no PC o clique continua sendo o do <summary>: nenhum campo é <select> nativo à vista
    assert "Todos os usuários" in uni and "Todas as etiquetas" in h


def test_o_enviar_e_os_textos_que_outros_testes_recortam_ficam_iguais():
    """`tests/test_casca_uso_os.py` roda o `enviar` no node, recortado do template pelo texto: o `function enviar(forcar, auto)`,
    o `form.addEventListener("submit"` logo depois, o `fechar` do card com `enviar(false);` e a atualização de 10 min."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "function enviar(forcar, auto)" in html and '\n  form.addEventListener("submit"' in html
    assert html.index("function enviar(forcar, auto)") < html.index('\n  form.addEventListener("submit"')
    assert "enviar(false, true);\n  }, 10 * 60 * 1000)" in html and html.count("enviar(false, true)") == 1
    fechar = html[html.index("function fechar() {"):html.index('document.querySelectorAll("a.os-folio")')]
    assert "enviar(false);" in fechar
    assert 'else if (a) a.remove();' in html and 'name = "nx_auto"' in html


# ══ 2. as cores: só por token, nos dois temas ═════════════════════════════════════════════════════════════════════════════
def _secao_css() -> str:
    css = OS_CSS.read_text(encoding="utf-8")
    ini = css.index("/* ── HISTÓRICO: os filtros no modelo A")
    fim = css.index("/* ══ TEMA CLARO")
    return css[ini:fim]


COR = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|oklch|oklab)\(|(?<![\w-])(?:white|black)(?![\w-])", re.I)


def test_o_css_do_modelo_a_so_tem_cor_por_token():
    """Cor só por var(--...): nada de #hex nem rgba() fora da definição dos tokens, que ficam no :root (escuro) e no bloco
    html[data-tema="claro"] que já existia. O fundo da página e o resto do OS Creator seguem como estavam."""
    secao = re.sub(r"/\*.*?\*/", "", _secao_css(), flags=re.S)
    sem_tokens = re.sub(r"(?m)^:root\{[^}]*\}", "", secao)
    achados = [m.group(0) for m in COR.finditer(sem_tokens)]
    assert achados == [], "cor fora dos tokens: %s" % achados
    assert "--fl-lima:#D4FF24" in secao and "--fl-azul:#1558c9" in secao and "--fl-preto:#030407" in secao


def test_os_tokens_novos_tem_o_par_do_claro():
    css = OS_CSS.read_text(encoding="utf-8")
    escuro = re.search(r"/\* ── HISTÓRICO: os filtros no modelo A.*?\n:root\{([^}]*)\}", css, re.S).group(1)
    claro = re.search(r'html\[data-tema="claro"\]\{(.*?)\n\}', css, re.S).group(1)
    nomes = re.findall(r"(--fl-[\w-]+):", escuro)
    assert len(nomes) >= 20
    sem_par = [n for n in nomes if n + ":" not in claro]
    assert sem_par == [], "token sem o valor do claro: %s" % sem_par
    # o que o Levi pediu para o claro: o texto azul é o próprio #1558c9, o botão lima segue lima com texto escuro, e o ponto do
    # que mudou usa o lima escuro (o musgo)
    assert re.search(r"--fl-azul-texto:\s*#1558c9", claro)
    assert re.search(r"--fl-lima:\s*#D4FF24", claro) and re.search(r"--fl-sobre-lima:\s*#030407", claro)
    assert re.search(r"--fl-ponto:\s*var\(--osc-musgo\)", claro)


def test_no_celular_o_painel_vira_folha_de_baixo_com_o_rodape_fixo():
    """Largura menor que 640 px: o painel sobe de baixo, na largura toda, com o rodapé que não rola e as listas no fluxo (a
    lista solta por cima seria cortada pela rolagem da folha)."""
    secao = _secao_css()
    celular = secao[secao.index("@media (max-width:639px)"):]
    for regra in ("position:fixed", "bottom:0", "border-radius:16px 16px 0 0", "grid-template-columns:1fr}", "position:static",
                  "env(safe-area-inset-bottom)", ".fl-veu{"):
        assert regra in celular, regra
    assert "@media (prefers-reduced-motion:no-preference)" in secao                      # a entrada animada respeita o sistema


def test_o_hidden_vale_nos_controles_novos():
    """O botão Aplicar de hoje de manhã tinha `hidden` e aparecia sempre: `.os-btn{display:inline-flex}` vence o `hidden` do
    navegador. Os controles novos que nascem escondidos dizem isso no CSS."""
    secao = _secao_css()
    for sel in (".fl-painel[hidden]", ".fl-veu[hidden]", ".fl-badge[hidden]", ".fl-etiquetas[hidden]", ".fl-link[hidden]",
                ".fl-aviso[hidden]"):
        assert sel in secao, sel


def test_o_os_busca_aceita_o_campo_de_uma_escolha_so_e_nao_cobre_o_select_escondido():
    js = BUSCA_JS.read_text(encoding="utf-8")
    assert "[data-campo-proprio]" in js                                                   # o <select> escondido não vira combobox
    assert "input[type=checkbox], input[type=radio]" in js                                # o Enter marca e escolhe
    assert ".fl-rot" in js and ".fl-cel" in js                                            # o nome do campo para o leitor de tela


# ══ 3. o comportamento, no node ═══════════════════════════════════════════════════════════════════════════════════════════
RODAR = r"""
const fs = require("fs");
const [falsa, buscaJs, opcoesJson, cenario] = process.argv.slice(1);
const {abrir} = require(falsa);
const pag = abrir(fs.readFileSync(0, "utf8"), Object.assign({busca_js: buscaJs, hoje: "2026-11-03"}, JSON.parse(opcoesJson)));
const sair = (new Function("pag", "return (" + cenario + ")(pag);"))(pag);
console.log(JSON.stringify(sair));
"""

# o que todo cenário precisa: achar a caixa de uma lista, abrir um campo e escolher pelo teclado como a pessoa
AJUDA = r"""
const caixa = (nome, valor) => pag.$$('.os-multi[data-nome="' + nome + '"] input[type=checkbox]').find((c) => c.value === valor);
const aplicarLigado = () => !pag.$("#b_aplicar").disabled;
const aberto = () => !pag.$("#fl_painel").hidden;
const cel = (nome) => pag.$('.fl-cel[data-filtro="' + nome + '"]');
const mudou = (nome) => cel(nome).classList.contains("mudou");
const pontos = () => pag.$$(".mudou").length;                 // quantos campos, ao todo, estão com o ponto de "mudou"
const nalt = () => pag.texto("#fl_nalt");
const etiquetas = () => pag.$$(".fl-chip").map((c) => pag.texto(c));
const campo = (nome) => (pag.envios[pag.envios.length - 1] || []).filter((c) => c[0] === nome).map((c) => c[1]);
const abrirCampo = (nome) => { const d = pag.$('details[data-nome="' + nome + '"]'); if (!d.open) d.querySelector("summary").click(); return d; };
const escolher = (nome, texto) => {                      // abre o campo, digita na caixa de busca e tecla Enter
  const d = abrirCampo(nome), b = d.querySelector(".osm-busca");
  pag.digitar(b, texto); pag.tecla(b, "Enter"); return d;
};
"""


def _rodar(html: str, cenario: str, **opcoes) -> dict:
    if not shutil.which("node"):
        pytest.skip("sem node nesta máquina")
    pronto = "(pag) => {" + AJUDA + " return (" + cenario + ")(pag); }"
    r = subprocess.run(["node", "-e", RODAR, str(FALSA), str(BUSCA_JS), json.dumps(opcoes), pronto], input=html,
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_a_troca_nao_filtra_e_acende_o_aplicar_e_desfeita_apaga(cli):
    r = _rodar(_pagina(cli), """(pag) => {
      const s = {};
      s.inicio = {aplicar: aplicarLigado(), nalt: nalt(), visiveis: pag.visiveis().length, aberto: aberto()};
      pag.clicar("#b_filtros");
      s.aberto = aberto();
      const status = caixa("status", "Em Processo"); status.click();
      s.status = {aplicar: aplicarLigado(), nalt: nalt(), visiveis: pag.visiveis().length, mudou: mudou("status"), envios: pag.envios.length};
      caixa("usina", "%s").click();
      s.dois = {nalt: nalt(), mudou: mudou("usina"), visiveis: pag.visiveis().length};
      status.click(); caixa("usina", "%s").click();
      s.desfeito = {aplicar: aplicarLigado(), nalt: nalt(), mudou: mudou("status") || mudou("usina")};
      return s;
    }""" % (USINA_SAO, USINA_SAO))
    assert r["inicio"] == {"aplicar": False, "nalt": "Sem alterações", "visiveis": 4, "aberto": False}
    assert r["aberto"] is True
    assert r["status"] == {"aplicar": True, "nalt": "1 alteração", "visiveis": 4, "mudou": True, "envios": 0}   # não filtrou
    assert r["dois"] == {"nalt": "2 alterações", "mudou": True, "visiveis": 4}
    assert r["desfeito"] == {"aplicar": False, "nalt": "Sem alterações", "mudou": False}                  # desfeita, apaga


def test_o_aplicar_so_filtra_a_tabela_quando_so_mudou_o_da_tabela(cli):
    r = _rodar(_pagina(cli), """(pag) => {
      pag.clicar("#b_filtros");
      caixa("status", "Em Processo").click();
      pag.clicar("#b_aplicar");
      return {visiveis: pag.visiveis(), envios: pag.envios.length, aberto: aberto(), aplicar: aplicarLigado(), nalt: nalt(),
              etiquetas: etiquetas(), contagem: pag.texto("#fl_n"), contagemVisivel: !pag.$("#fl_n").hidden};
    }""")
    assert r["visiveis"] == ["901", "903"] and r["envios"] == 0               # só a tabela, sem pedido
    assert r["aberto"] is False and r["aplicar"] is False and r["nalt"] == "Sem alterações"
    assert r["etiquetas"] == ["Criado por Ana Teste Silva", "Status Em Processo"]
    assert r["contagem"] == "2" and r["contagemVisivel"] is True


def test_criado_por_etiqueta_e_periodo_buscam_no_servidor_e_o_resto_vai_junto(cli):
    r = _rodar(_pagina(cli), """(pag) => {
      pag.clicar("#b_filtros");
      escolher("pessoa", "joao");                                   // Criado por: não busca na troca
      escolher("etiqueta", "garan");                                // nem a Etiqueta
      const depois = {envios: pag.envios.length, aplicar: aplicarLigado(), nalt: nalt()};
      const de = pag.$("input[name=de]"); de.value = "2026-10-20"; de.dispatchEvent({type: "change", bubbles: true});
      caixa("usina", "%s").click();                                  // e uma da tabela, que atravessa a busca
      pag.clicar("#b_aplicar");
      return {depois, envios: pag.envios.length, pessoa: campo("pessoa"), etiqueta: campo("etiqueta"), de: campo("de"), ate: campo("ate"), atualizar: campo("atualizar"),
              guardado: pag.sessao["os_hist_filtros_da_tabela"]};
    }""" % USINA_SAO)
    assert r["depois"] == {"envios": 0, "aplicar": True, "nalt": "2 alterações"}
    assert r["envios"] == 1 and r["pessoa"] == ["12"] and r["etiqueta"] == ["8"]
    assert r["de"] == ["2026-10-20"] and r["ate"] == ["2026-11-03"]
    assert r["atualizar"] == [""]                                              # é a busca de um clique, e não o ↻
    assert json.loads(r["guardado"])["usina"] == [USINA_SAO]                  # a usina atravessa a busca


def test_periodo_sem_as_duas_datas_ou_invertido_nao_aplica_e_avisa(cli):
    r = _rodar(_pagina(cli), """(pag) => {
      pag.clicar("#b_filtros");
      const de = pag.$("input[name=de]"); de.value = "2026-12-01"; de.dispatchEvent({type: "change", bubbles: true});   // depois do "até"
      pag.clicar("#b_aplicar");
      const invertido = {envios: pag.envios.length, aviso: pag.texto("#fl_aviso"), avisoVisivel: !pag.$("#fl_aviso").hidden, aberto: aberto()};
      de.value = ""; de.dispatchEvent({type: "change", bubbles: true});
      pag.clicar("#b_aplicar");
      return {invertido, vazio: {envios: pag.envios.length, aberto: aberto()}};
    }""")
    assert r["invertido"]["envios"] == 0 and r["invertido"]["avisoVisivel"] is True and r["invertido"]["aberto"] is True
    assert "O período não vale" in r["invertido"]["aviso"]
    assert r["vazio"] == {"envios": 0, "aberto": True}


@pytest.mark.parametrize("como", ["esc", "fora", "botao"])
def test_fechar_o_painel_sem_aplicar_descarta_as_escolhas(cli, como):
    """Esc, o clique fora ou o botão de novo: os campos voltam ao aplicado, o Aplicar apaga e nada vai ao servidor."""
    r = _rodar(_pagina(cli), """(pag) => {
      const COMO = %s;
      pag.clicar("#b_filtros");
      caixa("status", "Concluída").click();
      caixa("cliente", "Cliente Y").click();
      escolher("pessoa", "zelia");
      pag.$("input[name=de]").value = "2026-10-20"; pag.$("input[name=de]").dispatchEvent({type: "change", bubbles: true});
      const antes = {aplicar: aplicarLigado(), nalt: nalt(), pontos: pontos()};
      if (COMO === "esc") pag.tecla(pag.doc, "Escape");
      else if (COMO === "fora") pag.clicar("#hint");
      else pag.clicar("#b_filtros");
      return {antes, aberto: aberto(), aplicar: aplicarLigado(), nalt: nalt(), envios: pag.envios.length,
              status: caixa("status", "Concluída").checked, cliente: caixa("cliente", "Cliente Y").checked,
              pessoa: pag.$("select[name=pessoa]").value, resumoPessoa: pag.texto('details[data-nome="pessoa"] summary'),
              de: pag.$("input[name=de]").value, pontos: pontos(),
              expandido: pag.$("#b_filtros").getAttribute("aria-expanded"), visiveis: pag.visiveis().length};
    }""" % json.dumps(como))
    assert r["antes"] == {"aplicar": True, "nalt": "4 alterações", "pontos": 4}
    assert r["aberto"] is False and r["aplicar"] is False and r["nalt"] == "Sem alterações" and r["envios"] == 0
    assert (r["status"], r["cliente"]) == (False, False)
    assert r["pessoa"] == "11" and r["resumoPessoa"] == "Ana Teste Silva" and r["de"] == "2026-10-04" and r["pontos"] == 0
    assert r["expandido"] == "false" and r["visiveis"] == 4


def test_o_x_de_uma_etiqueta_tira_aquele_filtro_e_aplica_na_hora(cli):
    """A da tabela (Usina) aplica sem pedido; a do servidor (Criado por) manda a busca na hora; uma e outra deixam a pessoa com o
    que ela não tocou."""
    r = _rodar(_pagina(cli, "pessoa=12"), """(pag) => {
      const s = {inicio: etiquetas()};
      pag.clicar("#b_filtros"); caixa("usina", "%s").click(); caixa("status", "Concluída").click(); pag.clicar("#b_aplicar");
      s.depoisDoAplicar = etiquetas();
      // o clique do × na etiqueta da Usina: sai só ela, a tabela volta a mostrar o status, sem pedido
      pag.clicar('.fl-chip[data-filtro="usina"] .fl-chip-x');
      s.semUsina = {etiquetas: etiquetas(), envios: pag.envios.length, visiveis: pag.visiveis()};
      // o do Criado por: busca no servidor na hora, com o que ficou escolhido no resto (Concluída)
      pag.clicar('.fl-chip[data-filtro="pessoa"] .fl-chip-x');
      s.semPessoa = {envios: pag.envios.length, pessoa: campo("pessoa"), status: campo("status"), atualizar: campo("atualizar")};
      return s;
    }""" % USINA_SAO)
    assert r["inicio"] == ["Criado por João Exemplo"]
    assert r["depoisDoAplicar"] == ["Criado por João Exemplo", "Status Concluída", "Usina " + USINA_SAO]
    assert r["semUsina"]["etiquetas"] == ["Criado por João Exemplo", "Status Concluída"]
    assert r["semUsina"]["envios"] == 0 and r["semUsina"]["visiveis"] == ["900", "902"]          # só a tabela
    assert r["semPessoa"]["envios"] == 1 and r["semPessoa"]["pessoa"] == ["TODOS"] and r["semPessoa"]["status"] == ["Concluída"]
    assert r["semPessoa"]["atualizar"] == [""]


def test_o_x_aplica_sozinho_sem_levar_o_que_estava_no_painel_e_sem_filtro_a_linha_some(cli):
    """O clique do × passa antes pelo "clique fora" do painel aberto: a escolha que não foi aplicada não vai junto. E sem filtro
    aplicado a linha de etiquetas não aparece (aqui, tirando o Criado por, que é o único que a página tem)."""
    r = _rodar(_pagina(cli, "pessoa=12"), """(pag) => {
      const s = {linha: !pag.$("#fl_etiquetas").hidden, contagem: pag.texto("#fl_n"), limpar: !pag.$("#b_limpar").hidden};
      pag.clicar("#b_filtros");
      caixa("status", "Concluída").click();                         // escolhido e NÃO aplicado
      pag.clicar('.fl-chip[data-filtro="pessoa"] .fl-chip-x');
      s.envios = pag.envios.length; s.status = campo("status"); s.pessoa = campo("pessoa");
      // a página que volta, sem nenhum filtro aplicado
      return s;
    }""")
    assert r["linha"] is True and r["contagem"] == "1" and r["limpar"] is False       # só o Criado por: nada a "limpar"
    assert r["envios"] == 1 and r["pessoa"] == ["TODOS"] and r["status"] == []
    sem = _rodar(_pagina(cli, "pessoa=TODOS"), """(pag) => ({linha: !pag.$("#fl_etiquetas").hidden,
      contagem: !pag.$("#fl_n").hidden, etiquetas: etiquetas()})""")
    assert sem == {"linha": False, "contagem": False, "etiquetas": []}


def test_o_status_que_o_servidor_ja_cortou_so_sai_com_uma_busca_nova(cli):
    """A página que chegou com Status no endereço já veio com as OS desse status (o servidor filtra por ele): tirar a etiqueta
    só pela tabela mostraria as mesmas OS e diria que são todas. Mudar esse status busca de novo; a página que veio sem status
    segue filtrando só a tabela."""
    r = _rodar(_pagina(cli, "status=Em%20Processo"), """(pag) => {
      const s = {inicio: etiquetas()};
      pag.clicar('.fl-chip[data-filtro="status"] .fl-chip-x');
      s.envios = pag.envios.length; s.status = campo("status"); s.atualizar = campo("atualizar");
      return s;
    }""")
    assert r["inicio"] == ["Criado por Ana Teste Silva", "Status Em Processo"]
    assert r["envios"] == 1 and r["status"] == []                                # buscou de novo, sem o status
    r = _rodar(_pagina(cli, "status=Em%20Processo"), """(pag) => {
      pag.clicar("#b_filtros"); caixa("status", "Concluída").click(); pag.clicar("#b_aplicar");
      return {envios: pag.envios.length, status: campo("status")};
    }""")
    assert r == {"envios": 1, "status": ["Em Processo", "Concluída"]}           # trocou o status que o servidor tinha cortado


def test_as_etiquetas_dizem_o_valor_e_o_quanto_de_cada_lista(cli):
    """Uma etiqueta por filtro aplicado, na ordem do painel; uma lista com vários valores diz quantos ("Usina · 3 selecionadas",
    no feminino da usina), e a contagem do botão Filtros é o número de etiquetas, sem contar o período."""
    r = _rodar(_pagina(cli), """(pag) => {
      pag.clicar("#b_filtros");
      caixa("usina", "%s").click(); caixa("usina", "%s").click(); caixa("usina", "%s").click();
      caixa("status", "Em Processo").click(); caixa("status", "Concluída").click();
      pag.clicar("#b_aplicar");
      const tres = {etiquetas: etiquetas(), contagem: pag.texto("#fl_n"), limpar: !pag.$("#b_limpar").hidden,
                    resumoUsina: pag.texto('details[data-nome="usina"] .os-multi-txt'), resumoStatus: pag.texto('details[data-nome="status"] .os-multi-txt')};
      pag.clicar("#b_filtros");
      caixa("usina", "%s").click(); caixa("usina", "%s").click();            // fica uma só: o valor, e não a conta
      caixa("cliente", "Cliente X").click();
      pag.clicar("#b_aplicar");
      return {tres, uma: etiquetas(), contagem: pag.texto("#fl_n")};
    }""" % (USINA_SAO, USINA_ACUDE, USINA_TRES, USINA_ACUDE, USINA_TRES))
    assert r["tres"]["etiquetas"] == ["Criado por Ana Teste Silva", "Status 2 selecionados", "Usina 3 selecionadas"]
    assert r["tres"]["contagem"] == "3" and r["tres"]["limpar"] is True
    assert r["tres"]["resumoUsina"] == "3 selecionadas" and r["tres"]["resumoStatus"] == "2 selecionados"
    assert r["uma"] == ["Criado por Ana Teste Silva", "Status 2 selecionados", "Cliente Cliente X", "Usina " + USINA_SAO]
    assert r["contagem"] == "4"


def test_um_atalho_de_periodo_so_preenche_as_datas_e_espera_o_aplicar(cli):
    r = _rodar(_pagina(cli), """(pag) => {
      pag.clicar("#b_periodo");
      const ler = () => ({de: pag.$("input[name=de]").value, ate: pag.$("input[name=ate]").value});
      const ligados = () => pag.$$("[data-atalho]").filter((b) => b.classList.contains("on")).map((b) => b.getAttribute("data-atalho"));
      const s = {inicio: ligados(), abertoPeloPeriodo: aberto()};
      pag.clicar('[data-atalho="7"]');
      s.sete = Object.assign(ler(), {ligados: ligados(), aplicar: aplicarLigado(), nalt: nalt(), pontoDe: pag.$('[data-ponto="de"]').classList.contains("mudou"),
                                    pontoAte: pag.$('[data-ponto="ate"]').classList.contains("mudou"), envios: pag.envios.length});
      pag.clicar('[data-atalho="mes"]');
      s.mes = Object.assign(ler(), {ligados: ligados(), envios: pag.envios.length});
      pag.clicar('[data-atalho="30"]');
      s.trinta = Object.assign(ler(), {ligados: ligados(), aplicar: aplicarLigado(), nalt: nalt()});
      return s;
    }""")
    assert r["inicio"] == ["30"] and r["abertoPeloPeriodo"] is True                  # o botão do período abre o mesmo painel
    assert (r["sete"]["de"], r["sete"]["ate"]) == ("2026-10-27", "2026-11-03")
    assert r["sete"]["ligados"] == ["7"] and r["sete"]["aplicar"] is True and r["sete"]["nalt"] == "1 alteração"
    assert r["sete"]["pontoDe"] is True and r["sete"]["pontoAte"] is False and r["sete"]["envios"] == 0     # espera o Aplicar
    assert (r["mes"]["de"], r["mes"]["ate"]) == ("2026-11-01", "2026-11-03") and r["mes"]["ligados"] == ["mes"]
    assert r["mes"]["envios"] == 0
    assert (r["trinta"]["de"], r["trinta"]["ate"]) == ("2026-10-04", "2026-11-03")
    assert r["trinta"]["ligados"] == ["30"] and r["trinta"]["aplicar"] is False and r["trinta"]["nalt"] == "Sem alterações"


def test_o_botao_do_periodo_mostra_o_periodo_aplicado_e_o_ano_quando_nao_e_o_de_hoje(cli):
    r = _rodar(_pagina(cli), """(pag) => pag.texto("#fl_periodo_txt")""")
    assert r == "04/10 – 03/11"
    antigo = _rodar(cli.get("/os/historico?de=2025-12-20&ate=2026-01-05").get_data(as_text=True),
                    """(pag) => pag.texto("#fl_periodo_txt")""")
    assert antigo == "20/12/25 – 05/01/26"


def test_a_busca_de_um_campo_filtra_sem_acento_nem_caixa(cli):
    """A caixa de busca no topo de cada lista: "sao" acha "São" e "ACUDE" acha "Açude", nas listas de marcar e na de Criado
    por; o que não casa sai da lista, e a lista diz quando nada casa."""
    r = _rodar(_pagina(cli), """(pag) => {
      pag.clicar("#b_filtros");
      const dentro = (nome) => pag.$$('details[data-nome="' + nome + '"] label').filter((l) => !l.classList.contains("osm-fora") && !l.hidden)
                                .map((l) => pag.texto(l));
      const s = {};
      const usina = abrirCampo("usina"), b = usina.querySelector(".osm-busca");
      s.temBusca = !!b;
      s.todas = dentro("usina").length;
      pag.digitar(b, "sao"); s.sao = dentro("usina");
      pag.digitar(b, "ACUDE"); s.acude = dentro("usina");
      pag.digitar(b, "exemplo sao"); s.palavras = dentro("usina");             // em qualquer ordem
      pag.digitar(b, "zzz"); s.nada = {linhas: dentro("usina"), aviso: pag.texto(usina.querySelector(".osm-vazio")), visivel: !usina.querySelector(".osm-vazio").hidden};
      const pessoa = abrirCampo("pessoa"), bp = pessoa.querySelector(".osm-busca");
      pag.digitar(bp, "JOAO"); s.pessoa = dentro("pessoa");
      pag.digitar(bp, "zelia"); s.pessoaZ = dentro("pessoa");
      s.todosTemBusca = ["pessoa", "etiqueta", "status", "cliente", "usina", "tipo", "tarefa"].every((n) => !!pag.$('details[data-nome="' + n + '"] .osm-busca'));
      return s;
    }""")
    assert r["temBusca"] is True and r["todas"] == 4
    assert r["sao"] == ["Cliente X - Usina São Exemplo - UF"]
    assert r["acude"] == ["Cliente X - Usina Açude Exemplo - UF"]
    assert r["palavras"] == ["Cliente X - Usina São Exemplo - UF"]
    assert r["nada"]["linhas"] == [] and r["nada"]["visivel"] is True and "zzz" in r["nada"]["aviso"]
    assert r["pessoa"] == ["João Exemplo"] and r["pessoaZ"] == ["Zélia Souza"]
    assert r["todosTemBusca"] is True                                           # todas as opções do filtro são digitáveis


def test_enter_escolhe_na_lista_de_um_valor_e_fecha_e_marca_na_de_varios(cli):
    r = _rodar(_pagina(cli), """(pag) => {
      pag.clicar("#b_filtros");
      const s = {};
      // Criado por (um valor só): digitar, as setas andam, Enter escolhe e fecha a lista
      const pessoa = abrirCampo("pessoa"), b = pessoa.querySelector(".osm-busca");
      pag.digitar(b, "e");                                                     // Ana, João e Zélia têm "e" (o "Todos os usuários" não): a 1ª fica marcada
      const marcada = pag.$$('details[data-nome="pessoa"] label').filter((l) => l.classList.contains("on")).map((l) => pag.texto(l));
      pag.tecla(b, "ArrowDown");
      const marcada2 = pag.$$('details[data-nome="pessoa"] label').filter((l) => l.classList.contains("on")).map((l) => pag.texto(l));
      pag.tecla(b, "Enter");
      s.pessoa = {marcada, marcada2, valor: pag.$("select[name=pessoa]").value, aberta: pessoa.open, resumo: pag.texto(pessoa.querySelector("summary")),
                  tem: pessoa.classList.contains("fl-tem"), aplicar: aplicarLigado(), mudou: mudou("pessoa"),
                  escolhida: pag.$$('details[data-nome="pessoa"] input[type=radio]').filter((x) => x.checked).map((x) => x.value),
                  envios: pag.envios.length};
      // Usina (vários): Enter marca, a lista segue aberta e o resumo diz quantas
      const usina = abrirCampo("usina"), bu = usina.querySelector(".osm-busca");
      pag.digitar(bu, "sao"); pag.tecla(bu, "Enter");
      pag.digitar(bu, "tres"); pag.tecla(bu, "Enter");
      s.usina = {marcadas: pag.$$('details[data-nome="usina"] input[type=checkbox]').filter((x) => x.checked).map((x) => x.value),
                 aberta: usina.open, resumo: pag.texto(usina.querySelector(".os-multi-txt")), ultimaBusca: bu.value};
      return s;
    }""")
    assert r["pessoa"]["marcada"] == ["Ana Teste Silva"]                          # a 1ª que casa já vem marcada
    assert r["pessoa"]["marcada2"] == ["João Exemplo"]                            # a seta anda
    assert r["pessoa"]["valor"] == "12" and r["pessoa"]["aberta"] is False        # escolheu e fechou
    assert r["pessoa"]["resumo"] == "João Exemplo" and r["pessoa"]["tem"] is True and r["pessoa"]["escolhida"] == ["12"]
    assert r["pessoa"]["aplicar"] is True and r["pessoa"]["mudou"] is True and r["pessoa"]["envios"] == 0
    assert r["usina"]["marcadas"] == [USINA_SAO, USINA_TRES] and r["usina"]["aberta"] is True
    assert r["usina"]["resumo"] == "2 selecionadas"                               # a Usina é feminina


def test_esc_fecha_so_a_lista_e_o_esc_seguinte_fecha_o_painel(cli):
    """Levi: "Esc fecha só a lista". Com a lista aberta, um Esc a fecha de uma vez (o texto digitado sai com ela) e o painel fica;
    com a lista fechada, o Esc fecha o painel."""
    r = _rodar(_pagina(cli), """(pag) => {
      pag.clicar("#b_filtros");
      const usina = abrirCampo("usina"), b = usina.querySelector(".osm-busca");
      pag.digitar(b, "sao");
      const s = {};
      pag.tecla(b, "Escape");                                                  // 1º: a lista fecha de uma vez, e o painel fica
      s.primeiro = {lista: usina.open, painel: aberto(), texto: b.value};
      // com o foco no resumo (sem a caixa de busca no foco, como no toque): o Esc do documento fecha só a lista
      const status = abrirCampo("status");
      pag.tecla(status.querySelector("summary"), "Escape");
      s.resumo = {lista: status.open, painel: aberto()};
      pag.tecla(pag.doc, "Escape");                                            // sem lista aberta: fecha o painel
      s.segundo = {painel: aberto()};
      return s;
    }""")
    assert r["primeiro"] == {"lista": False, "painel": True, "texto": ""}
    assert r["resumo"] == {"lista": False, "painel": True}
    assert r["segundo"] == {"painel": False}


def test_fora_do_painel_o_esc_da_lista_continua_limpando_a_busca_antes_de_fechar(cli):
    """O `os_busca.js` é de todas as telas: o 1º Esc limpa o que foi digitado e o 2º fecha (README, "Digitar para achar"). Só o
    contêiner que pede (`[data-esc-fecha]`, o painel do Histórico) tem o Esc direto."""
    r = _rodar(_pagina(cli), """(pag) => {
      pag.clicar("#b_filtros");
      pag.$("#fl_painel").removeAttribute("data-esc-fecha");                  // como numa tela que não pediu
      const usina = abrirCampo("usina"), b = usina.querySelector(".osm-busca");
      pag.digitar(b, "sao");
      pag.tecla(b, "Escape");
      const primeiro = {lista: usina.open, texto: b.value};
      pag.tecla(b, "Escape");
      return {primeiro, segundo: {lista: usina.open, painel: aberto()}};
    }""")
    assert r["primeiro"] == {"lista": True, "texto": ""} and r["segundo"] == {"lista": False, "painel": True}


def test_o_painel_aberto_segura_a_atualizacao_de_10_minutos(cli):
    r = _rodar(_pagina(cli), """(pag) => {
      const dezMin = 10 * 60 * 1000, s = {};
      pag.clicar("#b_filtros"); caixa("status", "Concluída").click();
      pag.avanca(dezMin);
      s.comAlteracao = pag.envios.length;                                      // espera: mandaria a escolha sem o Aplicar
      pag.tecla(pag.doc, "Escape");
      pag.avanca(dezMin);
      s.depois = {envios: pag.envios.length, nx: campo("nx_auto"), p: campo("p"), status: campo("status"), atualizar: campo("atualizar")};
      return s;
    }""")
    assert r["comAlteracao"] == 0
    assert r["depois"] == {"envios": 1, "nx": ["1"], "p": ["tok"], "status": [], "atualizar": [""]}      # sem a escolha descartada


def test_o_limpar_do_painel_zera_os_filtros_e_espera_o_aplicar(cli):
    """Limpar zera os filtros do painel (Etiqueta, Status, Cliente, Usina e os Tipos); Criado por e o Período são o escopo da
    lista e ficam: o mesmo que o Limpar filtros de sempre fazia ("como no app"). E, como tudo no painel, espera o Aplicar."""
    r = _rodar(_pagina(cli, "pessoa=12"), """(pag) => {
      pag.clicar("#b_filtros");
      caixa("usina", "%s").click(); caixa("status", "Concluída").click(); pag.clicar("#b_aplicar");   // aplicados, só na tabela
      pag.clicar("#b_filtros");
      escolher("etiqueta", "perf");
      const antes = {nalt: nalt(), etiqueta: pag.$("select[name=etiqueta]").value};
      pag.clicar("#b_painel_limpar");
      return {antes, aberto: aberto(), etiqueta: pag.$("select[name=etiqueta]").value, pessoa: pag.$("select[name=pessoa]").value,
              de: pag.$("input[name=de]").value, usina: caixa("usina", "%s").checked, status: caixa("status", "Concluída").checked,
              nalt: nalt(), aplicar: aplicarLigado(), envios: pag.envios.length, visiveis: pag.visiveis().length, etiquetas: etiquetas()};
    }""" % (USINA_SAO, USINA_SAO))
    assert r["antes"] == {"nalt": "1 alteração", "etiqueta": "7"}
    assert r["aberto"] is True and r["etiqueta"] == "" and r["pessoa"] == "12" and r["de"] == "2026-10-04"
    assert r["usina"] is False and r["status"] is False
    assert r["aplicar"] is True and r["nalt"] == "2 alterações"                  # Status e Usina; a Etiqueta voltou ao aplicado (vazio)
    assert r["envios"] == 0 and r["visiveis"] == 1                               # a tabela só muda no Aplicar
    assert r["etiquetas"] == ["Criado por João Exemplo", "Status Concluída", "Usina " + USINA_SAO]


def test_limpar_tudo_faz_o_que_o_limpar_filtros_fazia(cli):
    """A navegação para o endereço limpo: mantém a visão, o Criado por e o período; sai o resto (a busca, a etiqueta, o status,
    as listas); e o que a aba guardava das listas da tabela vai embora."""
    r = _rodar(_pagina(cli, "pessoa=12&etiqueta=7&status=Concluída&busca=teste"), """(pag) => {
      pag.sessao["os_hist_filtros_da_tabela"] = "{}";
      const antes = {limpar: !pag.$("#b_limpar").hidden};
      pag.clicar("#b_limpar");
      return {antes, foiPara: pag.foiPara, guardado: "os_hist_filtros_da_tabela" in pag.sessao, painel: !pag.$("#fl_painel").hidden};
    }""")
    assert r["antes"] == {"limpar": True}
    assert len(r["foiPara"]) == 1
    url = r["foiPara"][0]
    assert url.startswith("/os/historico?") and "modo=criadas" in url and "pessoa=12" in url
    assert "de=2026-10-04" in url and "ate=2026-11-03" in url and "p=tok" in url
    for fora in ("etiqueta", "status", "busca", "usina", "cliente"):
        assert fora + "=" not in url, fora
    assert r["guardado"] is False


def test_enter_na_data_aplica_e_nao_deixa_o_formulario_ir_pelo_botao_de_atualizar(cli):
    """Enter num campo do formulário, sem tratamento, envia o formulário pelo 1º botão de envio: o ↻, que busca tudo de novo no
    Fracttal e leva as escolhas sem o Aplicar. No painel, o Enter na data é o Aplicar; no resto, não envia nada."""
    r = _rodar(_pagina(cli), """(pag) => {
      pag.clicar("#b_filtros");
      const de = pag.$("input[name=de]"); de.value = "2026-10-20"; de.dispatchEvent({type: "change", bubbles: true});
      pag.tecla(de, "Enter");
      const s = {envios: pag.envios.length, atualizar: campo("atualizar"), de: campo("de")};
      return s;
    }""")
    assert r == {"envios": 1, "atualizar": [""], "de": ["2026-10-20"]}
    r = _rodar(_pagina(cli), """(pag) => {
      pag.clicar("#b_filtros"); const c = caixa("status", "Concluída"); c.click();
      pag.tecla(c, "Enter");                                                   // numa caixa de marcar: nada
      return {envios: pag.envios.length, aberto: aberto(), aplicar: aplicarLigado()};
    }""")
    assert r == {"envios": 0, "aberto": True, "aplicar": True}


def test_tudo_que_envia_o_formulario_descarta_antes_o_que_o_painel_tinha_escolhido(cli):
    """F5, o ↻, as abas da visão e o Limpar tudo mandam o formulário: com o painel aberto e uma escolha sem aplicar, ela não vai
    junto (o painel fecha descartando antes)."""
    cenario = """(pag) => {
      pag.clicar("#b_filtros"); caixa("status", "Concluída").click();
      const de = pag.$("input[name=de]"); de.value = "2026-10-20"; de.dispatchEvent({type: "change", bubbles: true});
      %s
      return {envios: pag.envios.length, status: campo("status"), de: campo("de"), atualizar: campo("atualizar"), modo: campo("modo")};
    }"""
    f5 = _rodar(_pagina(cli), cenario % 'pag.tecla(pag.doc, "F5");')
    assert f5 == {"envios": 1, "status": [], "de": ["2026-10-04"], "atualizar": ["1"], "modo": ["criadas"]}
    seta = _rodar(_pagina(cli), cenario % 'pag.clicar("#b_atualizar");')
    assert seta["envios"] == 1 and seta["status"] == [] and seta["de"] == ["2026-10-04"] and seta["atualizar"] == ["1"]
    aba = _rodar(_pagina(cli), cenario % 'pag.clicar(\'[data-modo="cos"]\');')
    assert aba["envios"] == 1 and aba["status"] == [] and aba["de"] == ["2026-10-04"] and aba["modo"] == ["cos"]


def test_a_cascata_cliente_usina_continua_e_o_descartar_devolve_o_que_ela_desmarcou(cli):
    r = _rodar(_pagina(cli), """(pag) => {
      const escondidas = () => pag.$$('details[data-nome="usina"] label').filter((l) => l.hidden).map((l) => pag.texto(l));
      pag.clicar("#b_filtros");
      caixa("usina", "%s").click(); pag.clicar("#b_aplicar");                  // uma usina do Cliente X, aplicada
      pag.clicar("#b_filtros");
      caixa("cliente", "Cliente Y").click();                                   // a cascata esconde as do Cliente X e desmarca a usina
      const s = {escondidas: escondidas().length, usina: caixa("usina", "%s").checked, nalt: nalt()};
      pag.tecla(pag.doc, "Escape");                                            // descarta: a escolha volta, e a usina com ela
      s.depois = {escondidas: escondidas().length, usina: caixa("usina", "%s").checked, cliente: caixa("cliente", "Cliente Y").checked,
                  etiquetas: etiquetas()};
      return s;
    }""" % (USINA_SAO, USINA_SAO, USINA_SAO))
    assert r["escondidas"] == 2 and r["usina"] is False and r["nalt"] == "2 alterações"      # Cliente e Usina mudaram
    assert r["depois"]["escondidas"] == 0 and r["depois"]["usina"] is True and r["depois"]["cliente"] is False
    assert r["depois"]["etiquetas"] == ["Criado por Ana Teste Silva", "Usina " + USINA_SAO]


def test_a_busca_por_texto_segue_filtrando_enquanto_se_digita_sem_aplicar(cli):
    r = _rodar(_pagina(cli), """(pag) => {
      const b = pag.$("#busca_no");
      pag.digitar(b, "SÃO");                                                  // a busca por texto é a de sempre: sem caixa, com acento
      pag.avanca(300);
      return {visiveis: pag.visiveis(), aplicar: aplicarLigado(), envios: pag.envios.length, etiquetas: etiquetas()};
    }""")
    assert r == {"visiveis": ["900"], "aplicar": False, "envios": 0, "etiquetas": ["Criado por Ana Teste Silva"]}


def test_o_buscar_os_abre_a_os_direto_e_o_card_fecha_com_enter_no_campo(cli):
    r = _rodar(_pagina(cli), """(pag) => {
      const b = pag.$("#busca_os");
      b.value = "15003";
      pag.tecla(b, "Enter");
      return {card: !pag.$("#os_card").hidden, campo: b.value, envios: pag.envios.length, atalhoExportar: pag.$("#b_export").title};
    }""")
    assert r["card"] is True and r["campo"] == "" and r["envios"] == 0
    assert "[Ctrl+E]" in r["atalhoExportar"]


def test_o_painel_e_acessivel_o_botao_diz_se_esta_aberto_e_o_foco_volta(cli):
    r = _rodar(_pagina(cli), """(pag) => {
      const s = {inicio: [pag.$("#b_filtros").getAttribute("aria-expanded"), pag.$("#b_periodo").getAttribute("aria-expanded")]};
      pag.clicar("#b_filtros");
      s.aberto = [pag.$("#b_filtros").getAttribute("aria-expanded"), pag.$("#b_periodo").getAttribute("aria-expanded"), pag.$("#fl_painel").getAttribute("role")];
      pag.clicar("#b_periodo");                                                // o outro botão só muda o painel de lugar
      s.outro = {aberto: aberto(), filtros: pag.$("#b_filtros").getAttribute("aria-expanded"), periodo: pag.$("#b_periodo").getAttribute("aria-expanded")};
      pag.tecla(pag.doc, "Escape");
      s.fechado = {aberto: aberto(), foco: pag.doc.activeElement && pag.doc.activeElement.id};
      s.rotulos = pag.$$("details.fl-uni summary, details.fl-multi summary, .os-multi summary").every((x) => x.hasAttribute("aria-labelledby"));
      pag.clicar("#b_filtros"); caixa("status", "Concluída").click(); pag.clicar("#b_aplicar");       // o Aplicar some com o painel
      s.aplicado = {aberto: aberto(), foco: pag.doc.activeElement && pag.doc.activeElement.id};
      return s;
    }""")
    assert r["inicio"] == ["false", "false"]
    assert r["aberto"] == ["true", "false", "dialog"]
    assert r["outro"] == {"aberto": True, "filtros": "false", "periodo": "true"}
    assert r["fechado"] == {"aberto": False, "foco": "b_periodo"}                 # o foco volta a quem abriu
    assert r["rotulos"] is True
    assert r["aplicado"] == {"aberto": False, "foco": "b_filtros"}                # e o foco não se perde: volta ao botão


def test_no_celular_o_painel_nao_e_posicionado_pelo_javascript(cli):
    """Como PC o painel se prende ao botão (left calculado); no celular (menos de 640 px) o CSS faz dele uma folha de baixo, e o
    JavaScript não pode deixar um left inline por cima."""
    pc = _rodar(_pagina(cli), """(pag) => { pag.clicar("#b_filtros"); return pag.$("#fl_painel").getAttribute("style") || ""; }""")
    assert re.search(r"left:\s*\d+px", pc)
    cel = _rodar(_pagina(cli), """(pag) => { pag.clicar("#b_filtros"); return pag.$("#fl_painel").getAttribute("style") || ""; }""",
                 celular=True)
    assert "left" not in cel


@pytest.mark.parametrize("consulta,fixo,etiquetas", [
    ("modo=criadas", False, ["Criado por Ana Teste Silva"]),
    ("modo=atribuidas", True, []),                                              # Criado por não se aplica: fica apagado no lugar
    ("modo=cos", False, ["Tipo de tarefa %d selecionados" % len(api.TIPOS_COS)]),  # a COS já vem com os tipos dela marcados
])
def test_cada_visao_abre_o_painel_sem_erro(cli, consulta, fixo, etiquetas):
    r = _rodar(_pagina(cli, consulta), """(pag) => {
      pag.clicar("#b_filtros");
      const s = {fixo: !!pag.$('.fl-cel[data-filtro="pessoa"] .fl-campo-fixo'), lista: !!pag.$('details[data-nome="pessoa"]'),
                 aberto: aberto(), visao: pag.$$(".fl-seg button.on").map((b) => b.getAttribute("data-modo")),
                 aplicar: aplicarLigado(), etiquetas: etiquetas()};
      pag.tecla(pag.doc, "Escape");
      s.fechado = !aberto();
      return s;
    }""")
    assert r["fixo"] is fixo and r["lista"] is (not fixo)
    assert r["aberto"] is True and r["fechado"] is True and r["aplicar"] is False
    assert r["visao"] == [consulta.split("=")[1]] and r["etiquetas"] == etiquetas


def test_sem_pessoas_nem_etiquetas_no_catalogo_o_painel_abre_e_nada_quebra(cli, monkeypatch):
    """Quem não tem a permissão de pessoal no Fracttal recebe a lista de pessoas vazia, e o catálogo de etiquetas pode vir vazio:
    Criado por fica só com "Todos os usuários", Etiqueta só com "Todas as etiquetas", e o resto da tela segue igual."""
    monkeypatch.setattr(api, "get_pessoas_contas", lambda *a, **k: {"pessoas": [], "eu": None})
    monkeypatch.setattr(api, "get_labels", lambda *a, **k: [])
    r = _rodar(_pagina(cli), """(pag) => {
      pag.clicar("#b_filtros");
      const s = {pessoas: pag.$$('details[data-nome="pessoa"] label').length, etiquetas: pag.$$('details[data-nome="etiqueta"] label').length,
                 chips: etiquetas()};
      escolher("pessoa", "todos");
      s.depois = {pessoa: pag.$("select[name=pessoa]").value, aplicar: aplicarLigado()};
      pag.tecla(pag.doc, "Escape");
      s.fechado = !aberto();
      return s;
    }""")
    assert r["pessoas"] == 1 and r["etiquetas"] == 1 and r["chips"] == []
    assert r["depois"] == {"pessoa": "TODOS", "aplicar": False} and r["fechado"] is True       # escolher o que já valia não muda nada

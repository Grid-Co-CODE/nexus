"""Os filtros do Quadro da semana no modelo A do Histórico de OS (Levi, 16/11/2026: "Quadro da semana quero os filtros no
mesmo padrão de qualidade e funcionalidades do filtro de Histórico de OS > OS Creator!").

O modelo A (o do Histórico, `nexus/torres/oscreator/README.md`): uma barra de uma linha com a busca e o botão Filtros (com a
contagem dos aplicados), as etiquetas dos filtros aplicados logo abaixo (o × tira aquele e aplica na hora, e o "Limpar
tudo"), e um painel suspenso com os campos em duas colunas e o rodapé Limpar · "N alterações" · Aplicar. Nada filtra antes
do Aplicar; fechar sem aplicar (Esc, clique fora, o botão de novo, o × da folha) descarta. Toda lista é digitável (sem
acento nem caixa, setas, Enter marca). No celular, o painel é uma folha de baixo para cima com o rodapé fixo.

O que é do Quadro e fica: a cascata com a conta de cada opção (o filtro lista só o que existe com os OUTROS filtros, a
opção escolhida fica na lista), a conta da FAMA à parte ("+N FAMA"), o filtro vindo pelo endereço e a reprogramação que
leva os filtros nos campos `f_*`. Com o Aplicar, a cascata passou a ser recontada na página, enquanto a pessoa marca
(`quadro.painel_filtros` manda as linhas da semana em números); antes, cada lista se aplicava ao fechar.

Duas camadas, como o teste do Histórico: o que o servidor monta, e o comportamento no node, pelo DOM de mentira do
Histórico (`historico_pagina_falsa.js`), rodando o `pcm-quadro-filtros.js` na página que o servidor de verdade montou.
Nada sai da máquina. Nomes de mentira (o repositório é público).
"""
import json
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

from nexus.pcm import quadro as Q
from test_pcm_quadro import _banco, _semana_teste

RAIZ = Path(__file__).resolve().parents[1]
JS = RAIZ / "nexus" / "static" / "pcm-quadro-filtros.js"
CSS = RAIZ / "nexus" / "static" / "pcm.css"
FALSA = Path(__file__).resolve().parent / "historico_pagina_falsa.js"
CAMPOS = ["equipe", "resp", "cliente", "tipo", "estado", "turno"]


# ══ 1. as contas ═══════════════════════════════════════════════════════════════════════════════════════════════════════════
def test_o_painel_recebe_todos_os_valores_da_busca_em_numeros():
    rows = _semana_teste()["rows"]
    p = Q.painel_filtros(rows, [], {})
    assert p["campos"] == CAMPOS
    assert p["valores"]["equipe"] == ["RN Sul 01", "SP Leste 02"]
    assert p["valores"]["tipo"] == ["Corretiva", "MPA", "MPM"]
    assert p["valores"]["estado"] == ["Não iniciada", "Finalizada"]           # na ordem da situação, não a do alfabeto
    assert p["valores"]["turno"] == ["Manhã", "Tarde", "Noite", "Sem horário"]
    assert len(p["linhas"]) == len(rows) and p["fora"] == []
    # cada linha é o índice do valor de cada campo: a 4ª tarefa é a da RN Sul 01, MPA, finalizada, de manhã
    eq, rp, cl, tp, es, tu = p["linhas"][3]
    assert (p["valores"]["equipe"][eq], p["valores"]["tipo"][tp], p["valores"]["estado"][es],
            p["valores"]["turno"][tu]) == ("RN Sul 01", "MPA", "Finalizada", "Manhã")


def test_o_painel_ja_vem_com_a_busca_aplicada_e_os_outros_filtros_nao():
    rows = _semana_teste()["rows"]
    p = Q.painel_filtros(rows, [], {"q": "trafo", "equipe": "RN Sul 01"})
    assert len(p["linhas"]) == 1                                            # só a busca corta as linhas
    assert p["valores"]["tipo"] == ["MPM"]
    # a equipe escolhida que a busca não tem fica na lista (a tela não esconde o filtro que vale)
    assert p["valores"]["equipe"] == ["SP Leste 02", "RN Sul 01"]


def test_o_painel_conta_a_fama_a_parte():
    rows = _semana_teste()["rows"]
    fama = [{"cluster": "SP Leste 02", "responsavel": "Pessoa A", "cliente": "Cliente A", "tipo": "Limpeza de módulos",
             "status": "Não Iniciada", "h_ini": "", "os_id": "F1", "usina": "Cliente A - Usina 1 - SP", "tarefa": "x"}]
    p = Q.painel_filtros(rows, fama, {})
    assert "Limpeza de módulos" in p["valores"]["tipo"] and len(p["fora"]) == 1
    assert p["valores"]["tipo"][p["fora"][0][3]] == "Limpeza de módulos"


# ══ 2. o que o servidor monta ══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.fixture
def tela(app, logado, tmp_path, monkeypatch):
    monkeypatch.setattr(Q, "hoje", lambda: date(2026, 10, 7))
    app.config.update(NEXUS_PCM_FONTE=str(_banco(tmp_path)), NEXUS_PCM_TRABALHO=str(tmp_path / "trab"))

    def abrir(consulta="semana=2026-W41"):
        r = logado.get("/t/pcm/quadro?" + consulta)
        assert r.status_code == 200
        return r.get_data(as_text=True)
    return abrir


def _barra(html):
    return html.split('class="q-barra"', 1)[1].split("</form>", 1)[0]


def test_a_barra_tem_a_busca_e_o_botao_filtros_e_os_campos_so_no_painel(tela):
    barra = _barra(tela())
    linha = barra.split('id="qf_painel"', 1)[0]
    assert linha.index('name="q"') < linha.index('id="qf_botao"')           # a busca e o botão Filtros, nessa ordem
    assert re.search(r'<button type="button" class="qf-btn" id="qf_botao" aria-haspopup="dialog" aria-expanded="false" '
                     r'aria-controls="qf_painel">', linha)
    assert "data-filtro" not in linha and "data-ms" not in barra              # os chips de antes saíram
    painel = barra.split('id="qf_painel"', 1)[1]
    assert 'role="dialog" aria-label="Filtros" tabindex="-1" hidden' in barra
    assert re.findall(r'class="qf-cel" data-filtro="(\w+)"', painel) == CAMPOS
    assert 'id="qf_fechar"' in painel and 'aria-label="Fechar os filtros sem aplicar"' in painel
    rodape = painel.split('class="qf-rodape"', 1)[1]
    assert rodape.index('id="qf_limpar"') < rodape.index('id="qf_nalt"') < rodape.index('id="qf_aplicar"')
    assert re.search(r'id="qf_aplicar"[^>]*disabled', rodape) and "Sem alterações" in rodape
    assert 'id="qf_veu"' in barra and "pcm-quadro-filtros.js" in tela()


def test_cada_campo_e_uma_lista_digitavel_com_a_conta_de_cada_opcao(tela):
    painel = _barra(tela()).split('id="qf_painel"', 1)[1]
    tipo = painel.split('data-filtro="tipo"', 1)[1].split('class="qf-cel"', 1)[0]
    assert 'class="qf-lista-busca"' in tipo and 'type="search"' in tipo
    assert not re.search(r'class="qf-lista-busca"[^>]*name=', tipo)          # a caixa de busca não vai no formulário
    assert re.search(r'<input type="checkbox" name="tipo" value="MPM">\s*<span>MPM</span><small class="gc-num">2</small>',
                     tipo)
    assert '<span class="qf-multi-txt" data-todos="Todos" data-plural="selecionados" id="qf_val_tipo">Todos</span>' in tipo
    equipe = painel.split('data-filtro="equipe"', 1)[1].split('class="qf-cel"', 1)[0]
    assert 'data-todos="Todas" data-plural="selecionadas"' in equipe
    assert json.loads(tela().split('id="qf_dados">', 1)[1].split("</script>", 1)[0])["campos"] == CAMPOS


def test_a_opcao_que_a_cascata_tira_vem_escondida_e_a_escolhida_vem_marcada(tela):
    painel = _barra(tela("semana=2026-W41&equipe=RN+Sul+01")).split('id="qf_painel"', 1)[1]
    tipo = painel.split('data-filtro="tipo"', 1)[1].split('class="qf-cel"', 1)[0]
    # com a RN Sul 01, o Tipo só tem MPA; as outras vêm na página, escondidas (o painel reconta enquanto se marca)
    assert re.search(r'<label class="qf-op" title="MPA">\s*<input type="checkbox" name="tipo" value="MPA">', tipo)
    assert re.search(r'<label class="qf-op" hidden title="MPM">\s*<input type="checkbox" name="tipo" value="MPM">', tipo)
    equipe = painel.split('data-filtro="equipe"', 1)[1].split('class="qf-cel"', 1)[0]
    assert re.search(r'name="equipe" value="RN Sul 01" checked', equipe)
    assert '<span class="qf-multi-txt" data-todos="Todas" data-plural="selecionadas" id="qf_val_equipe">RN Sul 01</span>' in equipe


def test_as_etiquetas_sao_os_filtros_aplicados_e_o_x_tira_so_aquele(tela):
    barra = _barra(tela("semana=2026-W41&tipo=MPA&tipo=MPM&equipe=SP+Leste+02"))
    etq = barra.split('id="qf_etiquetas"', 1)[1].split("</div>", 1)[0]
    chips = re.findall(r'<span class="qf-chip" data-filtro="(\w+)"><i>([^<]+)</i> <span class="qf-chip-v"[^>]*>([^<]+)</span>',
                       etq)
    assert chips == [("equipe", "Equipe", "SP Leste 02"), ("tipo", "Tipo", "2 selecionados")]
    x_tipo = re.search(r'data-filtro="tipo">.*?<a class="qf-chip-x" href="([^"]+)" aria-label="([^"]+)"', etq, re.S)
    assert "semana=2026-W41" in x_tipo.group(1) and "equipe=SP+Leste+02" in x_tipo.group(1)
    assert "tipo=" not in x_tipo.group(1) and x_tipo.group(2) == "Tirar o filtro Tipo: 2 selecionados"
    # os endereços são o do Quadro, e não "?..." relativo: a página de erro do Reprogramar é servida em
    # /t/pcm/quadro/reprogramar, e o relativo cairia lá
    assert x_tipo.group(1).startswith("/t/pcm/quadro?")
    assert re.search(r'<a class="qf-link" id="qf_limpar_tudo" href="/t/pcm/quadro\?semana=2026-W41">Limpar tudo</a>', etq)
    assert re.search(r'<span class="qf-badge" id="qf_n">2</span>', barra)           # a contagem do botão Filtros


def test_o_formulario_dos_filtros_vai_sempre_ao_quadro(tela):
    assert '<form class="q-barra" method="get" action="/t/pcm/quadro" data-q-barra>' in tela()


def test_sem_filtro_nao_ha_etiquetas_e_a_contagem_fica_escondida(tela):
    barra = _barra(tela())
    assert re.search(r'id="qf_etiquetas"[^>]*hidden', barra)
    assert re.search(r'<span class="qf-badge" id="qf_n" hidden>0</span>', barra)


def test_a_busca_conta_no_limpar_tudo_mas_nao_vira_etiqueta(tela):
    barra = _barra(tela("semana=2026-W41&q=trafo"))
    assert "qf-chip" not in barra and 'value="trafo"' in barra


def test_a_reprogramacao_continua_levando_os_filtros(tela):
    html = tela("semana=2026-W41&tipo=MPA&tipo=MPM")
    assert '<input type="hidden" name="f_tipo" value="MPA|MPM">' in html


# ══ 3. o CSS ═══════════════════════════════════════════════════════════════════════════════════════════════════════════════
def _secao_css():
    css = CSS.read_text(encoding="utf-8")
    return css.split("/* ── QUADRO: os filtros no modelo A", 1)[1].split("/* ── ", 1)[0]


def test_o_css_do_painel_so_tem_cor_por_token():
    s = _secao_css()
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", s)


def test_o_hidden_vale_nos_controles_novos():
    s = _secao_css()
    for sel in (".qf-painel[hidden]", ".qf-veu[hidden]", ".qf-badge[hidden]", ".qf-etiquetas[hidden]", ".qf-op[hidden]"):
        assert sel in s, sel


def test_no_celular_o_painel_vira_folha_de_baixo_com_o_rodape_fixo():
    s = _secao_css()
    cel = s.split("@media (max-width:639px)", 1)[1]
    assert re.search(r"\.qf-painel\{position:fixed;[^}]*bottom:0", cel) and ".qf-veu{display:block" in cel
    assert re.search(r"\.qf-rodape\{flex:none", cel) and re.search(r"\.qf-grade\{grid-template-columns:1fr\}", cel)


# ══ 4. o comportamento, no node ════════════════════════════════════════════════════════════════════════════════════════════
RODAR = r"""
const fs = require("fs");
const [falsa, opcoesJson, cenario] = process.argv.slice(1);
const {abrir} = require(falsa);
const pag = abrir(fs.readFileSync(0, "utf8"), JSON.parse(opcoesJson));
const sair = (new Function("pag", "return (" + cenario + ")(pag);"))(pag);
console.log(JSON.stringify(sair));
"""

AJUDA = r"""
const caixa = (nome, valor) => pag.$$('details[data-nome="' + nome + '"] input[type=checkbox]').find((c) => c.value === valor);
const aplicarLigado = () => !pag.$("#qf_aplicar").disabled;
const aberto = () => !pag.$("#qf_painel").hidden;
const mudou = (nome) => pag.$('.qf-cel[data-filtro="' + nome + '"]').classList.contains("mudou");
const pontos = () => pag.$$(".qf-cel.mudou").length;
const nalt = () => pag.texto("#qf_nalt");
const resumo = (nome) => pag.texto('details[data-nome="' + nome + '"] .qf-multi-txt');
const opcoes = (nome) => pag.$$('details[data-nome="' + nome + '"] .qf-op').filter((l) => !l.hidden && !l.classList.contains("qf-fora"))
  .map((l) => [l.querySelector("input").value, pag.texto(l.querySelector(".gc-num"))]);
const enviado = () => pag.envios[pag.envios.length - 1] || null;
const campo = (nome) => (enviado() || []).filter((c) => c[0] === nome).map((c) => c[1]);
const abrirCampo = (nome) => { const d = pag.$('details[data-nome="' + nome + '"]'); if (!d.open) d.querySelector("summary").click(); return d; };
"""


def _rodar(html: str, cenario: str, **opcoes) -> dict:
    if not shutil.which("node"):
        pytest.skip("sem node nesta máquina")
    opcoes = dict({"pagina": "/t/pcm/quadro?semana=2026-W41", "script_js": str(JS)}, **opcoes)
    pronto = "(pag) => {" + AJUDA + " return (" + cenario + ")(pag); }"
    r = subprocess.run(["node", "-e", RODAR, str(FALSA), json.dumps(opcoes), pronto], input=html,
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_ao_abrir_a_pagina_as_contas_do_painel_sao_as_do_servidor(tela):
    html = tela("semana=2026-W41&equipe=RN+Sul+01")
    r = _rodar(html, """(pag) => ({tipo: opcoes("tipo"), equipe: opcoes("equipe"), estado: opcoes("estado"),
                                   aplicar: aplicarLigado(), nalt: nalt(), pontos: pontos()})""")
    op = Q.montar(_semana_teste(), [], {"equipe": "RN Sul 01"})["opcoes"]
    for c in ("tipo", "equipe", "estado"):
        assert sorted(r[c]) == sorted([v, str(n)] for v, n in op[c]), c
    assert r["aplicar"] is False and r["nalt"] == "Sem alterações" and r["pontos"] == 0


def test_marcar_nao_filtra_acende_o_aplicar_e_desfeito_apaga(tela):
    r = _rodar(tela(), """(pag) => {
      const s = {};
      pag.clicar("#qf_botao"); s.aberto = aberto(); s.expandido = pag.$("#qf_botao").getAttribute("aria-expanded");
      caixa("tipo", "MPM").click();
      s.um = {aplicar: aplicarLigado(), nalt: nalt(), mudou: mudou("tipo"), envios: pag.envios.length, resumo: resumo("tipo")};
      caixa("equipe", "SP Leste 02").click();
      s.dois = {nalt: nalt(), pontos: pontos(), resumo: resumo("equipe")};
      caixa("tipo", "MPA").click();
      s.tres = {nalt: nalt(), resumo: resumo("tipo")};
      caixa("tipo", "MPM").click(); caixa("tipo", "MPA").click(); caixa("equipe", "SP Leste 02").click();
      s.desfeito = {aplicar: aplicarLigado(), nalt: nalt(), pontos: pontos(), resumo: resumo("tipo")};
      return s;
    }""")
    assert r["aberto"] is True and r["expandido"] == "true"
    assert r["um"] == {"aplicar": True, "nalt": "1 alteração", "mudou": True, "envios": 0, "resumo": "MPM"}
    assert r["dois"] == {"nalt": "2 alterações", "pontos": 2, "resumo": "SP Leste 02"}
    assert r["tres"] == {"nalt": "2 alterações", "resumo": "2 selecionados"}
    assert r["desfeito"] == {"aplicar": False, "nalt": "Sem alterações", "pontos": 0, "resumo": "Todos"}


def test_o_aplicar_manda_o_formulario_com_o_que_esta_marcado_e_a_busca(tela):
    r = _rodar(tela("semana=2026-W41&q=mpm"), """(pag) => {
      pag.clicar("#qf_botao"); caixa("tipo", "MPM").click(); caixa("equipe", "SP Leste 02").click();
      pag.clicar("#qf_aplicar");
      return {envios: pag.envios.length, tipo: campo("tipo"), equipe: campo("equipe"), semana: campo("semana"), q: campo("q"),
              buscas: (enviado() || []).filter((c) => c[0] === "").length};
    }""")
    assert r == {"envios": 1, "tipo": ["MPM"], "equipe": ["SP Leste 02"], "semana": ["2026-W41"], "q": ["mpm"], "buscas": 0}


def test_a_cascata_reconta_enquanto_se_marca(tela):
    r = _rodar(tela(), """(pag) => {
      const s = {};
      pag.clicar("#qf_botao");
      s.antes = opcoes("tipo");
      caixa("equipe", "RN Sul 01").click();
      s.rn = {tipo: opcoes("tipo"), equipe: opcoes("equipe"), turno: opcoes("turno")};
      caixa("tipo", "MPA").click();
      caixa("equipe", "RN Sul 01").click();                       // a escolhida de Tipo fica na lista com a conta nova
      s.volta = opcoes("tipo");
      return s;
    }""")
    assert r["antes"] == [["Corretiva", "3"], ["MPA", "1"], ["MPM", "2"]]
    assert r["rn"]["tipo"] == [["MPA", "1"]] and r["rn"]["turno"] == [["Manhã", "1"]]
    assert r["rn"]["equipe"] == [["RN Sul 01", "1"], ["SP Leste 02", "5"]]     # o filtro não conta a si mesmo
    assert r["volta"] == [["Corretiva", "3"], ["MPA", "1"], ["MPM", "2"]]


def test_a_escolhida_sem_tarefa_com_os_outros_filtros_fica_na_lista(tela):
    r = _rodar(tela(), """(pag) => {
      pag.clicar("#qf_botao"); caixa("tipo", "MPM").click(); caixa("equipe", "RN Sul 01").click();
      return {tipo: opcoes("tipo")};
    }""")
    assert r["tipo"] == [["MPA", "1"], ["MPM", "0"]]


@pytest.mark.parametrize("como", ["esc", "fora", "botao", "fechar"])
def test_fechar_o_painel_sem_aplicar_descarta(tela, como):
    r = _rodar(tela("semana=2026-W41&tipo=MPA"), """(pag) => {
      pag.clicar("#qf_botao"); caixa("tipo", "MPA").click(); caixa("tipo", "MPM").click(); caixa("equipe", "RN Sul 01").click();
      const como = "%s";
      if (como === "esc") pag.tecla(pag.$("#qf_painel"), "Escape");
      if (como === "fora") pag.clicar(".q-rolo");
      if (como === "botao") pag.clicar("#qf_botao");
      if (como === "fechar") pag.clicar("#qf_fechar");
      return {aberto: aberto(), envios: pag.envios.length, mpa: caixa("tipo", "MPA").checked, mpm: caixa("tipo", "MPM").checked,
              rn: caixa("equipe", "RN Sul 01").checked, nalt: nalt(), pontos: pontos(), resumo: resumo("tipo"),
              equipe: opcoes("equipe"), expandido: pag.$("#qf_botao").getAttribute("aria-expanded")};
    }""" % como)
    assert r["aberto"] is False and r["envios"] == 0 and r["expandido"] == "false"
    assert (r["mpa"], r["mpm"], r["rn"]) == (True, False, False)
    assert r["nalt"] == "Sem alterações" and r["pontos"] == 0 and r["resumo"] == "MPA"
    assert r["equipe"] == [["RN Sul 01", "1"]]                                  # a cascata voltou à do aplicado


def test_esc_fecha_so_a_lista_e_o_esc_seguinte_fecha_o_painel(tela):
    r = _rodar(tela(), """(pag) => {
      pag.clicar("#qf_botao"); const d = abrirCampo("tipo"); caixa("tipo", "MPM").click();
      pag.tecla(d.querySelector(".qf-lista-busca"), "Escape");
      const s = {lista: d.open, painel: aberto(), mpm: caixa("tipo", "MPM").checked};
      pag.tecla(pag.$("#qf_painel"), "Escape");
      s.depois = {painel: aberto(), mpm: caixa("tipo", "MPM").checked, foco: pag.doc.activeElement && pag.doc.activeElement.id};
      return s;
    }""")
    assert r["lista"] is False and r["painel"] is True and r["mpm"] is True
    assert r["depois"] == {"painel": False, "mpm": False, "foco": "qf_botao"}


def test_a_lista_e_digitavel_sem_acento_nem_caixa_e_o_enter_marca(tela):
    r = _rodar(tela(), """(pag) => {
      pag.clicar("#qf_botao"); const d = abrirCampo("estado"), b = d.querySelector(".qf-lista-busca");
      pag.digitar(b, "nao INIC");
      const s = {visiveis: opcoes("estado").map((o) => o[0])};
      pag.tecla(b, "Enter");
      s.marcou = caixa("estado", "Não iniciada").checked; s.envios = pag.envios.length; s.nalt = nalt();
      pag.digitar(b, "xyz");
      s.vazio = pag.texto(d.querySelector(".qf-vazio"));
      pag.tecla(b, "Escape");
      s.limpou = b.value;
      return s;
    }""")
    assert r["visiveis"] == ["Não iniciada"] and r["marcou"] is True and r["envios"] == 0 and r["nalt"] == "1 alteração"
    assert r["vazio"] == "Nenhuma opção tem “xyz”." and r["limpou"] == ""


def test_as_setas_andam_na_lista_e_o_enter_marca_a_marcada(tela):
    r = _rodar(tela(), """(pag) => {
      pag.clicar("#qf_botao"); const d = abrirCampo("tipo"), b = d.querySelector(".qf-lista-busca");
      pag.tecla(b, "ArrowDown"); pag.tecla(b, "ArrowDown"); pag.tecla(b, "Enter");
      return {mpa: caixa("tipo", "MPA").checked, corretiva: caixa("tipo", "Corretiva").checked};
    }""")
    assert r == {"mpa": True, "corretiva": False}


def test_o_limpar_do_painel_desmarca_tudo_e_espera_o_aplicar(tela):
    r = _rodar(tela("semana=2026-W41&tipo=MPA&equipe=RN+Sul+01"), """(pag) => {
      pag.clicar("#qf_botao"); pag.clicar("#qf_limpar");
      return {marcadas: pag.$$("#qf_painel input[type=checkbox]").filter((c) => c.checked).length, envios: pag.envios.length,
              aberto: aberto(), nalt: nalt(), tipo: opcoes("tipo").length};
    }""")
    assert r == {"marcadas": 0, "envios": 0, "aberto": True, "nalt": "2 alterações", "tipo": 3}


def test_enter_na_busca_manda_sem_levar_o_que_estava_no_painel(tela):
    r = _rodar(tela("semana=2026-W41&tipo=MPA"), """(pag) => {
      pag.clicar("#qf_botao"); caixa("tipo", "MPM").click();
      const q = pag.$("#q"); pag.digitar(q, "cabine"); pag.tecla(q, "Enter");
      return {envios: pag.envios.length, tipo: campo("tipo"), q: campo("q"), aberto: aberto()};
    }""")
    assert r == {"envios": 1, "tipo": ["MPA"], "q": ["cabine"], "aberto": False}


def test_o_clique_no_x_de_uma_etiqueta_descarta_antes_o_que_o_painel_tinha(tela):
    r = _rodar(tela("semana=2026-W41&tipo=MPA&equipe=RN+Sul+01"), """(pag) => {
      pag.clicar("#qf_botao"); caixa("tipo", "MPM").click();
      pag.clicar('.qf-chip[data-filtro="equipe"] .qf-chip-x');
      return {aberto: aberto(), mpm: caixa("tipo", "MPM").checked, envios: pag.envios.length};
    }""")
    assert r == {"aberto": False, "mpm": False, "envios": 0}                    # o link do × faz o resto


def test_no_celular_o_painel_nao_e_posicionado_pelo_javascript(tela):
    r = _rodar(tela(), """(pag) => { pag.clicar("#qf_botao"); return {estilo: pag.$("#qf_painel").getAttribute("style"),
                                                                      veu: !pag.$("#qf_veu").hidden}; }""", celular=True)
    assert r["estilo"] in (None, "") and r["veu"] is True

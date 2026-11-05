"""Os filtros de Garantias no modelo do Histórico (Levi, 05/11/2026: "quero que os filtros dos chamados sejam no estilo OS
CREATOR WEB > HISTÓRICO", "algo suspenso e moderno, do jeito que está está ocupando muito espaço na tela!").

A busca fica à vista e filtra enquanto se digita; os seis campos (Fornecedor, Cliente, Tipo de ativo, Status geral, Status
do chamado e Responsável UFV) moram no painel suspenso do botão Filtros, de marcar vários, e só valem no Aplicar; fechar
sem aplicar descarta; cada filtro aplicado vira uma etiqueta, e o × dela o tira na hora. Sem "Limpar" (28/10/2026: "Tire o
botão de limpar filtros"). O filtro aplicado fica guardado na aba do navegador e volta com a tela (24/10/2026).

Roda a página de verdade no node: o HTML que o servidor monta (com o Fracttal e o banco falsos do teste de 28/10) é lido
pelo DOM de mentira do Histórico (`historico_pagina_falsa.js`), que executa o `acomp.js` e o `os_busca.js`. Nomes e
números de mentira: o repositório é público."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from nexus.torres.oscreator import ponte
from test_oscreator_garantias_28_10 import _quadro, tela  # noqa: F401 — a fixture é usada pelo nome

FALSA = Path(__file__).resolve().parent / "historico_pagina_falsa.js"
ACOMP_JS = Path(ponte.RAIZ_CLONE) / "os_web" / "static" / "acomp.js"
BUSCA_JS = Path(ponte.RAIZ_CLONE) / "os_web" / "static" / "os_busca.js"

RODAR = r"""
const fs = require("fs");
const [falsa, opcoesJson, cenario] = process.argv.slice(1);
const {abrir} = require(falsa);
const pag = abrir(fs.readFileSync(0, "utf8"), Object.assign({pagina: "/os/chamados/acompanhamento"}, JSON.parse(opcoesJson)));
const sair = (new Function("pag", "return (" + cenario + ")(pag);"))(pag);
console.log(JSON.stringify(sair));
"""

AJUDA = r"""
const caixa = (nome, valor) => pag.$$('.os-multi[data-nome="' + nome + '"] input[type=checkbox]').find((c) => c.value === valor);
const cartoes = () => pag.$$("a.card[href]").filter((c) => !c.classList.contains("oculto"))
  .map((c) => c.getAttribute("href").split("/").pop()).sort();
const linhas = () => pag.$$("tr[data-linha]").filter((t) => !t.classList.contains("oculto")).map((t) => t.dataset.folio).sort();
const aberto = () => !pag.$("#fl_painel").hidden;
const etiquetas = () => pag.$$(".fl-chip").map((c) => pag.texto(c));
const nalt = () => pag.texto("#fl_nalt");
const contagem = () => (pag.$("#fl_n").hidden ? "" : pag.texto("#fl_n"));
const mudou = (nome) => pag.$('.fl-cel[data-filtro="' + nome + '"]').classList.contains("mudou");
const resumo = (nome) => pag.texto('.os-multi[data-nome="' + nome + '"] .os-multi-txt');
const guardado = () => JSON.parse(pag.sessao["acomp.filtros"] || "null");
"""


def _rodar(html: str, cenario: str, **opcoes) -> dict:
    if not shutil.which("node"):
        pytest.skip("sem node nesta máquina")
    opcoes = dict({"script_js": str(ACOMP_JS), "busca_js": str(BUSCA_JS)}, **opcoes)
    pronto = "(pag) => {" + AJUDA + " return (" + cenario + ")(pag); }"
    r = subprocess.run(["node", "-e", RODAR, str(FALSA), json.dumps(opcoes), pronto], input=html,
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


# ── a página ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_barra_tem_a_busca_e_o_filtros_e_o_painel_os_seis_campos_digitaveis(tela):
    c, _, _ = tela
    h = _quadro(c)
    barra = h.split('id="fl_barra"', 1)[1].split('id="fl_painel"', 1)[0]
    assert 'data-f="busca"' in barra and 'id="b_filtros"' in barra and 'id="fl_n"' in barra
    painel = h.split('id="fl_painel"', 1)[1].split('<div class="board">', 1)[0]
    nomes = [x.split('"', 1)[0] for x in painel.split('class="os-multi" data-nome="')[1:]]
    assert nomes == ["marca", "cliente", "tipo", "geral", "st", "ufv"]
    assert painel.count('data-busca="1"') == 6                                # todas digitáveis (os_busca.js)
    assert 'id="b_aplicar" disabled>Aplicar</button>' in painel
    assert "Limpar" not in painel and 'id="b_limpar"' not in h                 # 28/10/2026: sem o Limpar
    assert 'class="filtros"' not in h and "<select data-f=" not in h            # a linha de antes saiu


# ── o comportamento, no node ─────────────────────────────────────────────────────────────────────────────────────
def test_marcar_nao_filtra_e_o_aplicar_filtra_vira_etiqueta_e_fica_guardado(tela):
    c, _, _ = tela
    r = _rodar(_quadro(c), """(pag) => {
      const s = {todos: cartoes()};
      pag.clicar("#b_filtros");
      s.aberto = aberto();
      caixa("marca", "STI").click();
      s.marcado = {cartoes: cartoes(), nalt: nalt(), aplicar: !pag.$("#b_aplicar").disabled, mudou: mudou("marca"),
                   resumo: resumo("marca")};
      pag.clicar("#b_aplicar");
      s.aplicado = {cartoes: cartoes(), linhas: linhas(), aberto: aberto(), etiquetas: etiquetas(), contagem: contagem(),
                    nalt: nalt(), mudou: mudou("marca"), guardado: guardado().marca};
      return s;
    }""")
    assert r["todos"] == ["9101", "9102", "9103"] and r["aberto"] is True      # a 9104, cancelada, não entra no quadro
    assert r["marcado"] == {"cartoes": r["todos"], "nalt": "1 alteração", "aplicar": True, "mudou": True, "resumo": "STI"}
    assert r["aplicado"] == {"cartoes": ["9102"], "linhas": ["9102"], "aberto": False, "etiquetas": ["Fornecedor STI"],
                             "contagem": "1", "nalt": "Sem alterações", "mudou": False, "guardado": ["STI"]}


def test_varios_valores_valem_qualquer_um_e_o_sem_pega_o_que_nao_tem(tela):
    c, _, _ = tela
    r = _rodar(_quadro(c), """(pag) => {
      pag.clicar("#b_filtros");
      caixa("st", "Standby").click(); caixa("st", "Aguardando retorno do Cliente").click();
      pag.clicar("#b_aplicar");
      const s = {st: cartoes(), resumo: resumo("st"), etiquetas: etiquetas()};
      pag.clicar("#b_filtros");
      caixa("ufv", "_sem").click();
      pag.clicar("#b_aplicar");
      s.dois = {cartoes: cartoes(), contagem: contagem(), etiquetas: etiquetas()};
      return s;
    }""")
    assert r["st"] == ["9101", "9103"]                                         # Standby ou Aguardando retorno do Cliente
    assert r["resumo"] == "2 selecionados" and r["etiquetas"] == ["Status do chamado 2 selecionados"]
    # e os campos se somam: dos dois, só a 9103 está sem Responsável UFV
    assert r["dois"] == {"cartoes": ["9103"], "contagem": "2",
                         "etiquetas": ["Status do chamado 2 selecionados", "Responsável UFV Sem responsável UFV"]}


@pytest.mark.parametrize("campo,valor,ficam", [("geral", "Cliente", ["9101"]), ("geral", "Standby", ["9103"]),
                                               ("ufv", "Supervisor Um", ["9101"]), ("ufv", "_sem", ["9103"])])
def test_o_status_geral_e_o_responsavel_ufv_no_quadro_e_na_tabela(tela, campo, valor, ficam):
    """28/10/2026: o Status geral e o Responsável UFV no lugar do Responsável; "_sem" acha o que não tem."""
    c, _, _ = tela
    r = _rodar(_quadro(c), """(pag) => {
      pag.clicar("#b_filtros"); caixa("%s", "%s").click(); pag.clicar("#b_aplicar");
      return {cartoes: cartoes(), linhas: linhas(), vazio: !pag.$("[data-vazio-tabela]").classList.contains("oculto")};
    }""" % (campo, valor))
    assert r == {"cartoes": ficam, "linhas": ficam, "vazio": False}


def test_filtro_sem_nenhuma_linha_diz_que_nao_ha(tela):
    c, _, _ = tela
    r = _rodar(_quadro(c), """(pag) => {
      pag.clicar("#b_filtros"); caixa("marca", "STI").click(); caixa("cliente", "Cliente B").click(); pag.clicar("#b_aplicar");
      return {cartoes: cartoes(), linhas: linhas(), vazio: !pag.$("[data-vazio-tabela]").classList.contains("oculto"),
              vaziosDasColunas: pag.$$("[data-vazio]").filter((v) => !v.classList.contains("oculto")).length};
    }""")
    assert r == {"cartoes": [], "linhas": [], "vazio": True, "vaziosDasColunas": 3}


def test_fechar_sem_aplicar_descarta_pelo_clique_fora_pelo_esc_e_pelo_botao(tela):
    c, _, _ = tela
    r = _rodar(_quadro(c), """(pag) => {
      const s = {};
      const tenta = (fechar) => {
        pag.clicar("#b_filtros"); caixa("cliente", "Cliente B").click();
        fechar();
        return {aberto: aberto(), marcado: caixa("cliente", "Cliente B").checked, mudou: mudou("cliente"), nalt: nalt(),
                cartoes: cartoes().length, resumo: resumo("cliente")};
      };
      s.fora = tenta(() => pag.clicar(".kpis"));
      s.esc = tenta(() => pag.tecla(pag.doc.body, "Escape"));
      s.botao = tenta(() => pag.clicar("#b_filtros"));
      return s;
    }""")
    for como in ("fora", "esc", "botao"):
        assert r[como] == {"aberto": False, "marcado": False, "mudou": False, "nalt": "Sem alterações", "cartoes": 3,
                           "resumo": "Todos"}, como


def test_o_x_da_etiqueta_tira_aquele_filtro_na_hora(tela):
    c, _, _ = tela
    r = _rodar(_quadro(c), """(pag) => {
      pag.clicar("#b_filtros");
      caixa("marca", "Huawei").click(); caixa("cliente", "Cliente A").click();
      pag.clicar("#b_aplicar");
      const s = {antes: cartoes()};
      pag.$('.fl-chip[data-filtro="marca"] .fl-chip-x').click();
      s.depois = {cartoes: cartoes(), etiquetas: etiquetas(), contagem: contagem(), resumo: resumo("marca"),
                  guardado: guardado()};
      return s;
    }""")
    assert r["antes"] == ["9101"]                                              # Huawei do Cliente A
    assert r["depois"]["cartoes"] == ["9101", "9102"] and r["depois"]["etiquetas"] == ["Cliente Cliente A"]
    assert r["depois"]["contagem"] == "1" and r["depois"]["resumo"] == "Todos"
    assert r["depois"]["guardado"]["marca"] == [] and r["depois"]["guardado"]["cliente"] == ["Cliente A"]


def test_a_busca_filtra_enquanto_se_digita_sem_o_aplicar(tela):
    c, _, _ = tela
    r = _rodar(_quadro(c), """(pag) => {
      pag.digitar(pag.$('[data-f="busca"]'), "9103");
      return {cartoes: cartoes(), contagem: contagem(), busca: guardado().busca};
    }""")
    assert r == {"cartoes": ["9103"], "contagem": "", "busca": "9103"}          # a busca não conta no botão


def test_o_filtro_guardado_volta_com_a_tela(tela):
    """A volta de um chamado, o Atualizar e a tela que troca sozinha (24/10/2026). O guardado de antes de 05/11 tinha um
    valor só por campo: vale como lista de um. Valor que saiu da lista (o fornecedor sem chamado aberto) não vira filtro."""
    c, _, _ = tela
    h = _quadro(c)
    cena = """(pag) => ({cartoes: cartoes(), etiquetas: etiquetas(), contagem: contagem(), resumo: resumo("marca"),
                         busca: pag.$('[data-f="busca"]').value})"""
    novo = _rodar(h, cena, sessao={"acomp.filtros": json.dumps({"marca": ["STI"], "busca": ""})})
    assert novo == {"cartoes": ["9102"], "etiquetas": ["Fornecedor STI"], "contagem": "1", "resumo": "STI", "busca": ""}
    antigo = _rodar(h, cena, sessao={"acomp.filtros": json.dumps({"marca": "STI", "busca": "9102"})})
    assert antigo == {"cartoes": ["9102"], "etiquetas": ["Fornecedor STI"], "contagem": "1", "resumo": "STI",
                      "busca": "9102"}
    saiu = _rodar(h, cena, sessao={"acomp.filtros": json.dumps({"marca": ["Marca Que Saiu"]})})
    assert saiu == {"cartoes": ["9101", "9102", "9103"], "etiquetas": [], "contagem": "", "resumo": "Todos",
                    "busca": ""}


def test_o_relatorio_vem_com_os_clientes_do_filtro_marcados(tela):
    c, _, _ = tela
    r = _rodar(_quadro(c), """(pag) => {
      pag.clicar("#b_filtros"); caixa("cliente", "Cliente B").click(); pag.clicar("#b_aplicar");
      const dlg = pag.$("[data-dlg-relatorio]");
      dlg.showModal = () => {};
      pag.clicar("[data-relatorio]");
      return dlg.querySelectorAll('input[type="checkbox"]').filter((x) => x.checked).map((x) => x.value);
    }""")
    assert r == ["Cliente B"]

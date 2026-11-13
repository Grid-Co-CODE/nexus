# -*- coding: utf-8 -*-
"""A página da tela Coletas sai da tela do Conversor Grid Co. (`ui/index.html` e `ui/furos.js` do .exe), por trocas
conferidas: cada troca acha o trecho exatamente uma vez, ou a geração para e diz qual trecho mudou no .exe.

Por que gerar e não copiar à mão (11/11/2026): o .exe muda quase todo dia (1.0.0 a 1.0.8 em dois dias) e a tela do Nexus
tem de acompanhar. O que muda de uma para a outra é só o que um servidor muda:
- o Python da janela vira pedido ao servidor (`window.pywebview.api.X(...)` -> `POST /t/performance/coletas/api/X`); o
  diálogo de arquivo do Windows vira o <input type=file> do navegador, e o arquivo sobe um por pedido (o teto do Nexus);
- o soltar arquivo, que o .exe tratava no Python (o caminho completo do pywebview), passa a ler os arquivos e as pastas
  no navegador; o reconhecimento segue em fundo no servidor e a tela pergunta o estado até acabar;
- o BD vem do banco: o botão de cada BD usa um Excel no lugar dele; a faixa vermelha diz por que o banco não serve;
- "Abrir no Excel" vira "Baixar a planilha"; "Mostrar na pasta" e a atualização do .exe saem (a versão é a do servidor);
- as cores são as do Nexus (os dois temas, o da casca de quem abriu) e a fonte é a do Nexus;
- nos Furos, o relatório sobe para o Nexus (todos veem o mesmo) e as confirmações ficam no navegador de cada pessoa,
  como no HTML original (confirmação compartilhada é dado novo no banco: catálogo antes, decisão do Levi).

Uso: chamado pelo `sincronizar_conversor.py` (que copia o motor e gera estes dois arquivos).
"""
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGINA = os.path.join(RAIZ, "nexus", "torres", "performance", "templates", "performance", "coletas_app.html")
FUROS_JS = os.path.join(RAIZ, "nexus", "static", "coletas", "furos.js")


class TrechoMudou(Exception):
    pass


def _troca(t, velho, novo, onde):
    n = t.count(velho)
    if n != 1:
        raise TrechoMudou(f"{onde}: o trecho aparece {n} vez(es) no .exe (esperava 1): {velho[:90]!r}")
    return t.replace(velho, novo)


CORES = """  /* As cores e a fonte são as do Nexus (os dois temas; nexus.css, ligado acima): a tela do .exe tinha o navy fixo.
     Os nomes do .exe apontam para os do Nexus; a página segue o tema da casca de quem abriu (o script no fim). */
  :root{--sup:var(--superficie);--txt:var(--tinta);--mut:var(--mudo);--fra:var(--fraco);--borda:var(--linha-forte);
        --borda2:var(--linha-forte);--leve:var(--alerta);--sev:var(--severo);--err:var(--critico)}"""

CABECA = """<!doctype html>
<html lang="pt-BR" data-tema="escuro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Coletas · Nexus</title>
{# GERADO por ferramentas/portar_tela_conversor.py a partir do ui/index.html do Conversor Grid Co. (o .exe): não edite
   aqui, mude o .exe e rode `python ferramentas/sincronizar_conversor.py`. #}
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{{ url_for('static', filename='nexus.css') }}">
<script>window.NX = {base: {{ url_for('torre_performance.coletas')|tojson }}};</script>
{% raw %}
"""

# O que a janela do Windows fazia, no navegador. Entra no lugar do `const api = () => window.pywebview.api;`
SHIM = r"""// ---- a ponte com o servidor do Nexus (no .exe era o Python da janela; ver ferramentas/portar_tela_conversor.py)
const NX_BASE = window.NX.base;
const TETO_ENVIO = 25 * 1024 * 1024;        // o teto de envio do Nexus, por pedido (um arquivo por pedido)
const CHAVE_CONF = "nexus.coletas.furos.conf";
const CHAVE_RONDA = "nexus.coletas.furos.ronda";    // a Ronda da aba "Para coletar" (1.0.10): por pessoa, como as confirmações
async function nxPost(metodo, args, auto) {
  const h = {"Content-Type": "application/json", "Accept": "application/json"};
  if (auto) h["X-Nexus-Auto"] = "1";        // a pergunta do estado não conta como uso da pessoa
  const r = await fetch(NX_BASE + "/api/" + metodo, {method: "POST", credentials: "same-origin", headers: h,
                                                       body: JSON.stringify({args: args || []})});
  let d = null; try { d = await r.json(); } catch (e) {}
  if (r.status === 401) {
    try { if (d && d.sessao_encerrada && parent.nexusEntrarDeNovo) parent.nexusEntrarDeNovo(d.entrar); } catch (e) {}
    throw new Error("a sessão do Nexus acabou: entre de novo");
  }
  if (!r.ok && !(d && d.erro)) throw new Error("O Nexus respondeu " + r.status + ".");
  return d;
}
function escolher(o) {
  return new Promise(ok => {
    const i = document.createElement("input");
    i.type = "file"; i.multiple = !!o.multiple; if (o.accept) i.accept = o.accept;
    if (o.pasta) { i.webkitdirectory = true; i.multiple = true; }
    i.onchange = () => ok([...(i.files || [])]);
    i.addEventListener("cancel", () => ok([]));
    i.click();
  });
}
function baixarBlob(nome, blob) {
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = nome;
  document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}
async function enviar(lista) {
  if (!lista.length) return;
  const lote = await nxPost("novo_lote", []);
  const tops = new Set(), grandes = [];
  let i = 0;
  for (const {file, rel} of lista) {
    i++; $("#status").textContent = `Enviando ${i} de ${lista.length}: ${rel}`;
    if (file.size > TETO_ENVIO) { grandes.push(rel); continue; }
    const fd = new FormData();
    fd.append("lote", lote); fd.append("rel", rel); fd.append("modificado", file.lastModified || ""); fd.append("arquivo", file, file.name);
    const r = await fetch(NX_BASE + "/arquivo", {method: "POST", credentials: "same-origin", body: fd});
    if (!r.ok) { let d = null; try { d = await r.json(); } catch (e) {} toast("Não consegui enviar " + rel + (d && d.erro ? ": " + d.erro : "")); continue; }
    tops.add(rel.split("/")[0]);
  }
  if (grandes.length) toast(`Ficou de fora (mais de 25 MB, o teto do Nexus): ${grandes.join(", ")}`);
  aplicarEstado(await nxPost("lote_pronto", [lote, [...tops]]));
  vigiar();
}
async function lerEntrada(ent, pref, out) {
  if (ent.isFile) { const f = await new Promise((ok, no) => ent.file(ok, no)); out.push({file: f, rel: pref + f.name}); return; }
  if (!ent.isDirectory) return;
  const rd = ent.createReader();
  for (;;) {
    const lote = await new Promise((ok, no) => rd.readEntries(ok, no));
    if (!lote.length) break;
    for (const x of lote) await lerEntrada(x, pref + ent.name + "/", out);
  }
}
function aplicarEstado(e) {
  if (!e || e.erro) { if (e && e.erro) $("#status").textContent = "Erro: " + e.erro; return; }
  app.bds(e.bds, e.bd_pronto);
  app.cards.clear(); app.cartoes(e.itens || []);
}
let vigiaT = null;
function vigiar() {
  clearTimeout(vigiaT);
  vigiaT = setTimeout(async () => {
    let e = null;
    try { e = await nxPost("estado", [], true); } catch (x) { $("#status").textContent = x.message; return; }
    aplicarEstado(e);
    if (!e.bd_pronto || (e.itens || []).some(c => c.estado === "identificando")) vigiar();
    else $("#status").textContent = "Pronto.";
  }, 900);
}
function lerChave(k) { try { return JSON.parse(localStorage.getItem(k) || "{}") || {}; } catch (e) { return {}; } }
const lerConf = () => lerChave(CHAVE_CONF);
async function furosLer(r) { const d = await r.json(); if (d && !d.erro) { d.conf = lerConf(); d.ronda = lerChave(CHAVE_RONDA); } return d; }
const WEB = {
  async escolher_arquivos() { await enviar((await escolher({multiple: true})).map(f => ({file: f, rel: f.name}))); return true; },
  async escolher_pasta() { await enviar((await escolher({pasta: true})).map(f => ({file: f, rel: f.webkitRelativePath || f.name}))); return true; },
  async escolher_bd(destino) {
    const fs = await escolher({accept: ".xlsx,.xlsm"});
    // o servidor reconhece o BD pelo nome: "BD_Performance · <arquivo>" entra no lugar do banco
    if (fs.length) await enviar([{file: fs[0], rel: destino + " · " + fs[0].name}]);
    return nxPost("estado", []);
  },
  abrir() { return true; },
  mostrar_pasta() { return true; },
  atualizar() { return {erro: "no Nexus a versão é a do servidor"}; },
  async furos_carregar() { return furosLer(await fetch(NX_BASE + "/furos", {credentials: "same-origin"})); },
  async furos_mais_novo() { return WEB.furos_carregar(); },
  async furos_abrir() {
    const fs = await escolher({accept: ".html,.htm"});
    if (!fs.length) return null;
    const fd = new FormData(); fd.append("arquivo", fs[0], fs[0].name);
    return furosLer(await fetch(NX_BASE + "/furos", {method: "POST", credentials: "same-origin", body: fd}));
  },
  furos_gravar_conf(c) { try { localStorage.setItem(CHAVE_CONF, JSON.stringify(c || {})); } catch (e) {} return true; },
  furos_gravar_ronda(x) { try { localStorage.setItem(CHAVE_RONDA, JSON.stringify(x || {})); } catch (e) {} return true; },
  // onde buscar no portal: a aba Equipamentos do BD_Performance (o do banco, ou o Excel que a pessoa soltou)
  async furos_portal() {
    try { const r = await fetch(NX_BASE + "/furos/portal", {credentials: "same-origin"}); return r.ok ? await r.json() : {}; }
    catch (e) { return {}; }
  },
  furos_salvar(nome, texto) { baixarBlob(nome, new Blob([texto], {type: nome.endsWith(".csv") ? "text/csv" : "application/json"})); return nome; },
  async furos_importar() {
    const fs = await escolher({accept: ".json"});
    if (!fs.length) return null;
    try { const j = JSON.parse(await fs[0].text()); return j && j.conf ? j.conf : j; } catch (e) { toast("O arquivo não é um JSON de confirmações"); return null; }
  },
  async furos_salvar_html(caminho, conf) {
    const r = await fetch(NX_BASE + "/furos/html", {method: "POST", credentials: "same-origin",
      headers: {"Content-Type": "application/json"}, body: JSON.stringify({conf})});
    const nome = caminho || "Furos_Coleta_Performance.html";
    baixarBlob(nome, await r.blob());
    return nome;
  },
};
const API = new Proxy({}, {get: (_, m) => WEB[m] || ((...a) => nxPost(m, a))});
const api = () => API;"""

BDS_VELHO = """  bds(lista) {
    for (const b of lista) {
      const el = b.destino === "BD_Performance" ? $("#bd-perf") : $("#bd-thopen");
      el.querySelector(".dot").className = "dot " + (b.lido ? "g" : "r");
      el.querySelector("b").textContent = b.lido ? "lido " + b.lido_em : "não encontrado — escolher";
      el.title = (b.caminho || "") + (b.erro ? "\\n" + b.erro : "") + "\\nClique para escolher outro arquivo";
    }
  },"""
BDS_NOVO = """  // o BD vem do banco (a subida do coletor) ou do Excel que a pessoa soltou; sem nenhum, a faixa diz por quê
  bds(lista, pronto) {
    const erros = [];
    for (const b of lista) {
      const el = b.destino === "BD_Performance" ? $("#bd-perf") : $("#bd-thopen");
      const lendo = pronto === false;
      el.querySelector(".dot").className = "dot " + (lendo ? "y" : b.lido ? "g" : "r");
      el.querySelector("b").textContent = lendo ? "lendo do banco…" : !b.lido ? "sem BD — usar um Excel" :
        (b.origem === "banco" ? "banco · subida de " : "Excel · ") + b.lido_em;
      el.title = (b.caminho || "") + (b.erro ? "\\n" + b.erro : "") + "\\nClique para usar um Excel do BD no lugar do banco";
      if (!lendo && !b.lido && b.erro) erros.push(b.destino + ": " + b.erro);
    }
    $("#bd-aviso").hidden = !erros.length;
    $("#bd-aviso").innerHTML = erros.map(e => `<div>${esc(e)}</div>`).join("");
  },"""

INICIAR_VELHO = """  async iniciar() {
    const e = await api().estado();
    $("#versao").textContent = e.versao;
    this.bds(e.bds.map(b => e.bd_pronto ? b : {...b, lido: false, lido_em: null}));
    if (!e.bd_pronto) { $("#bd-perf b").textContent = "lendo…"; $("#bd-thopen b").textContent = "lendo…";
      document.querySelectorAll(".top .dot").forEach(d => d.className = "dot y"); }
    if (e.atualizacao) this.atualizacao(e.atualizacao);
    this.cartoes(e.itens);
  },"""
INICIAR_NOVO = """  async iniciar() {
    const e = await api().estado();
    $("#versao").textContent = e.versao;
    aplicarEstado(e);
    if (!e.bd_pronto || (e.itens || []).some(c => c.estado === "identificando")) vigiar();
  },"""

TEMA = """// o tema é o da casca do Nexus de quem abriu (escuro ou claro), e acompanha a troca feita lá
(function () {
  const copiar = () => { try { const t = parent.document.documentElement.getAttribute("data-tema");
    if (t) document.documentElement.setAttribute("data-tema", t); } catch (e) {} };
  copiar();
  try { new MutationObserver(copiar).observe(parent.document.documentElement, {attributes: true, attributeFilter: ["data-tema"]}); } catch (e) {}
})();
// soltar arquivos e pastas na tela (no .exe o Python recebia o caminho; aqui o navegador lê e sobe)
document.addEventListener("dragover", e => e.preventDefault());
document.addEventListener("drop", async e => {
  e.preventDefault();
  const ents = [...(e.dataTransfer.items || [])].map(i => i.webkitGetAsEntry && i.webkitGetAsEntry()).filter(Boolean);
  const lista = [];
  if (ents.length) { for (const x of ents) await lerEntrada(x, "", lista); }
  else lista.push(...[...(e.dataTransfer.files || [])].map(f => ({file: f, rel: f.name})));
  await enviar(lista);
});
app.iniciar();"""


# As cores fixas do CSS do .exe viram tokens do Nexus (regra do Nexus: cor só por token, nos dois temas; tests/test_tema.py).
# O rgba(r,g,b,a) de uma cor de estado vira color-mix com o token dela, com a mesma opacidade.
_RGB_TOKEN = {"74,222,128": "--ok", "255,91,110": "--critico", "255,143,60": "--severo", "244,114,182": "--anomalo",
              "45,212,191": "--esperado"}
_HEX_TOKEN = {"#f472b6": "var(--anomalo)", "#2dd4bf": "var(--esperado)", "#8a1c2a": "var(--critico-escuro)"}


def _cores_por_token(t):
    import re
    i, j = t.index("<style>"), t.index("</style>")
    css = t[i:j]
    css = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"\s*\(?#[0-9a-fA-F]{3,8}\b[^)*]*\)?", "", m.group(0)), css, flags=re.S)
    css = css.replace("rgba(0,0,0,.55)", "var(--veu)")

    def rgba(m):
        tok = _RGB_TOKEN.get(m.group(1).replace(" ", ""))
        if not tok:
            raise TrechoMudou(f"cor sem token no CSS do .exe: {m.group(0)}")
        return "color-mix(in srgb,var(%s) %d%%,transparent)" % (tok, round(float(m.group(2)) * 100))
    css = re.sub(r"rgba\(([\d ,]+?),\s*([\d.]+)\)", rgba, css)
    for h, v in _HEX_TOKEN.items():
        css = re.sub(re.escape(h) + r"\b", v, css, flags=re.I)
    sobra = re.findall(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(", css)
    if sobra:
        raise TrechoMudou(f"cor fixa sem token no CSS do .exe: {sorted(set(sobra))}")
    return t[:i] + css + t[j:]


def gerar_pagina(index_html: str) -> str:
    t = index_html.replace("\r\n", "\n")
    ini = t.index("<style>")
    t = CABECA + t[ini:]
    t = _troca(t, """  :root{--fundo:#090d18;--barra:#0d1526;--sup:#161d30;--linha:#1f2940;--borda:#2a3550;--borda2:#3a4664;
        --txt:#e9eef6;--mut:#94a3b8;--fra:#64748b;--verde:#a3d900;--ok:#4ade80;--leve:#ffd83d;--sev:#ff8f3c;--err:#ff5b6e;
        --rolagem:#243154;--rolagem-hover:#34426b}""", CORES, "cores")
    t = _troca(t, 'font-family:"Segoe UI",system-ui,sans-serif;font-size:13px}', "font-family:var(--font-sans);font-size:13px}",
               "fonte")
    # o verde como TEXTO é o --verde-texto do Nexus (no claro o #a9db21 some no branco); como fundo, o --verde
    for velho in (".logo span{color:var(--verde)}", ".drop a{color:var(--verde);", ".chip.best{border-color:var(--verde);color:var(--verde)}",
                  ".nm .bruto{color:var(--verde);", ".fz-chip.on{border-color:var(--verde);color:var(--verde)}",
                  ".fz-sug{color:var(--verde);"):
        t = _troca(t, velho, velho.replace("color:var(--verde)", "color:var(--verde-texto)"), "verde-texto")
    t = _troca(t, ".upd{margin-left:auto;background:var(--verde);color:var(--fundo);",
               ".upd{margin-left:auto;background:var(--verde);color:var(--sobre-verde);", "upd")
    t = _troca(t, ".btn{background:var(--verde);color:var(--fundo);", ".btn{background:var(--verde);color:var(--sobre-verde);", "btn")
    t = _troca(t, ".amar{background:var(--leve);color:var(--fundo);font-weight:600}",
               ".amar{background:var(--alerta-cheio);color:var(--sobre-cheio);font-weight:600}", "amarelo")
    t = _troca(t, ".grid td.amar.marc{background:var(--leve);", ".grid td.amar.marc{background:var(--alerta-cheio);", "amarelo-marc")
    t = _troca(t, ".grid td.marc{background:rgba(163,217,0,.16);", ".grid td.marc{background:var(--verde-suave);", "marc")
    t = _troca(t, ".fz-sw input:checked+span{background:rgba(163,217,0,.3)}",
               ".fz-sw input:checked+span{background:var(--verde-a35)}", "chave")
    # sem a marca e o nome do .exe (a casca do Nexus já diz onde se está); a versão é a do motor do Conversor
    i, j = t.index('    <div class="logo">'), t.index('Conversor <span>Grid Co.</span></div>\n')
    t = t[:i] + t[j + len('Conversor <span>Grid Co.</span></div>\n'):]
    t = _troca(t, '<span class="pill">versão <b id="versao">-</b></span>',
               '<span class="pill" title="a versão do motor do Conversor Grid Co. que esta tela usa">Conversor <b id="versao">-</b></span>',
               "versão")
    t = _troca(t, 'title="Clique para escolher outro arquivo"><span class="dot"></span>BD_Performance <b>lendo…</b>',
               'title="Clique para usar um Excel do BD no lugar do banco"><span class="dot"></span>BD_Performance <b>lendo…</b>',
               "bd-perf")
    t = _troca(t, 'title="Clique para escolher outro arquivo"><span class="dot"></span>BD_Thopen <b>lendo…</b>',
               'title="Clique para usar um Excel do BD no lugar do banco"><span class="dot"></span>BD_Thopen <b>lendo…</b>',
               "bd-thopen")
    t = _troca(t, "xlsx, xls, csv, zip, tar.gz · um ou vários de uma vez</div>",
               "xlsx, xls, csv, zip, tar.gz · um ou vários de uma vez · o BD_Performance ou o BD_Thopen em Excel solto "
               "junto entra no lugar do banco</div>\n        <div class=\"av erro\" id=\"bd-aviso\" hidden></div>", "drop")
    t = _troca(t, '<button class="btn2 fz-sm" id="fzNovo" title="Volta para o relatório mais novo da pasta 4. O&amp;M &gt; '
                  '9.Pós Operação &gt; 1. Performance">Usar o relatório mais novo da pasta</button>',
               '<button class="btn2 fz-sm" id="fzNovo" title="Volta para o relatório mais novo que subiu ao Nexus">Usar o '
               'relatório mais novo no Nexus</button>', "furos: mais novo")
    # os filtros dos Furos no modelo do Histórico de OS (12/11/2026): o painel e as etiquetas da Zeladoria (zf-*) e a barra
    t = _troca(t, "</style>\n</head>",
               "</style>\n{% endraw %}<link rel=\"stylesheet\" href=\"{{ url_for('static', filename='zeladoria/filtros.css') }}\">\n"
               "<link rel=\"stylesheet\" href=\"{{ url_for('static', filename='coletas/coletas.css') }}\">{% raw %}\n</head>",
               "filtros: css")
    t = _troca(t, '<script src="furos.js"></script>',
               "{% endraw %}<script src=\"{{ url_for('static', filename='coletas/furos.js') }}\"></script>\n"
               "<script src=\"{{ url_for('static', filename='coletas/filtros.js') }}\" defer></script>{% raw %}", "furos.js")
    # A recoleta pela API PV (1.0.14) fica DESLIGADA no Nexus: ela gasta a cota paga da API PV (o servidor da plataforma
    # atende pela chave X-Recoleta-Chave, o HMAC da PV_PASSWORD) e, aqui, qualquer pessoa com a tela Coletas poderia
    # gastar. Ligar é decisão do Levi (13/11/2026): falta a chave no servidor do Nexus e os métodos recoleta_* na lista.
    t = _troca(t, '<button class="btn2" id="rcAbrir">Recoletar pela API</button>',
               '<button class="btn2" id="rcAbrir" hidden>Recoletar pela API</button>', "recoleta desligada")
    t = _troca(t, "const api = () => window.pywebview.api;", SHIM, "api")
    t = _troca(t, BDS_VELHO, BDS_NOVO, "bds")
    t = _troca(t, INICIAR_VELHO, INICIAR_NOVO, "iniciar")
    t = _troca(t, """<button class="btn bk" data-abrir="${i}">Abrir no Excel</button><button class="btn2 bk" data-pasta="${i}">Mostrar na pasta</button></div>`""",
               """<button class="btn bk" data-abrir="${i}">Baixar a planilha</button></div>`""", "saídas")
    t = _troca(t, """b.onclick = () => api().abrir(r.saidas[+b.dataset.abrir].caminho));""",
               """b.onclick = () => { location.href = NX_BASE + "/planilha/" + r.saidas[+b.dataset.abrir].indice; });""",
               "baixar")
    t = _troca(t, """$("#bd-perf").onclick = async () => { const e = await api().escolher_bd("BD_Performance"); app.bds(e.bds); app.cartoes(e.itens); };
$("#bd-thopen").onclick = async () => { const e = await api().escolher_bd("BD_Thopen"); app.bds(e.bds); app.cartoes(e.itens); };""",
               """$("#bd-perf").onclick = async () => aplicarEstado(await api().escolher_bd("BD_Performance"));
$("#bd-thopen").onclick = async () => aplicarEstado(await api().escolher_bd("BD_Thopen"));""", "escolher_bd")
    t = _troca(t, 'window.addEventListener("pywebviewready", () => app.iniciar());', TEMA, "início")
    t = _troca(t, "</script>\n</body>", "</script>\n{% endraw %}\n</body>", "fim")
    t = _cores_por_token(t)
    if "pywebview.api." in t.replace("window.pywebview && window.pywebview.api && window.pywebview.api.copiar", ""):
        raise TrechoMudou("sobrou uma chamada ao pywebview na página")
    return t


FUROS_VARIOS = [
    ('const FILTROS = ["fzQ", "fzCli", "fzCart", "fzSrc", "fzSt", "fzSit"];',
     'const FILTROS = ["fzQ", "fzCli", "fzCart", "fzSrc", "fzSt", "fzSit"];\n'
     '  // Nexus (Coletas): vários valores por filtro, como o Histórico de OS; nenhum marcado = todos\n'
     '  const vs = i => [...$f(i).options].filter(o => o.selected && o.value !== "").map(o => o.value);\n'
     '  const sitOk = (x, m) => x === "falha" ? m.sit === "falha" : x === "conf" ? m.sit === "conf" : x === "ok" ? m.sit === "ok" :\n'
     '    x === "ipoa" ? !!m.ipF : x === "ghi" ? !!m.ghF : x === "inop" ? !!m.inopN : x === "os" ? !!m.ex : x === "noos" ? !!m.noos :\n'
     '    x === "inv" ? !!m.invF : true;',
     "furos: vários"),
    ('const ps = P(), keep = [$f("fzCli").value, $f("fzCart").value, $f("fzSt").value];',
     'const ps = P(), keep = [vs("fzCli"), vs("fzCart"), vs("fzSt")];', "furos: guardar"),
    ('$f("fzCli").value = keep[0]; $f("fzCart").value = keep[1]; $f("fzSt").value = keep[2];',
     '[["fzCli", 0], ["fzCart", 1], ["fzSt", 2]].forEach(([i, k]) => [...$f(i).options].forEach(o => '
     '{ o.selected = o.value !== "" && keep[k].includes(o.value); }));', "furos: remarcar"),
    ('let n = FILTROS.filter(i => $f(i).value).length;',
     'let n = FILTROS.filter(i => i === "fzQ" ? $f(i).value : vs(i).length).length;', "furos: ativos"),
    ('FILTROS.forEach(i => { $f(i).value = ""; });',
     'FILTROS.forEach(i => { if (i === "fzQ") $f(i).value = ""; else [...$f(i).options].forEach(o => { o.selected = false; }); });',
     "furos: limpar"),
    ('const q = $f("fzQ").value.toLowerCase(), c = $f("fzCli").value, ca = $f("fzCart").value, s = $f("fzSrc").value, '
     'st = $f("fzSt").value, sit = $f("fzSit").value;',
     'const q = $f("fzQ").value.toLowerCase(), c = vs("fzCli"), ca = vs("fzCart"), s = vs("fzSrc"), st = vs("fzSt"), '
     'sit = vs("fzSit");', "furos: ler"),
    ('      if (c && p.cliente !== c) return false; if (ca && p.carteira !== ca) return false; if (s && p.src !== s) return false;\n'
     '      if (st && (p.status || "—") !== st) return false; if (q && !p.usina.toLowerCase().includes(q)) return false;\n'
     '      if (sit === "falha" && m.sit !== "falha") return false; if (sit === "conf" && m.sit !== "conf") return false; '
     'if (sit === "ok" && m.sit !== "ok") return false;\n'
     '      if (sit === "ipoa" && !m.ipF) return false; if (sit === "ghi" && !m.ghF) return false; if (sit === "inop" && !m.inopN) '
     'return false;\n'
     '      if (sit === "os" && !m.ex) return false; if (sit === "noos" && !m.noos) return false; if (sit === "inv" && !m.invF) '
     'return false;',
     '      if (c.length && !c.includes(p.cliente)) return false; if (ca.length && !ca.includes(p.carteira)) return false; '
     'if (s.length && !s.includes(p.src)) return false;\n'
     '      if (st.length && !st.includes(p.status || "—")) return false; if (q && !p.usina.toLowerCase().includes(q)) return false;\n'
     '      if (sit.length && !sit.some(x => sitOk(x, m))) return false;', "furos: filtrar"),
    ('e.onclick = () => { cliSel = e.dataset.c; $f("fzCli").value = cliSel; render(); });',
     'e.onclick = () => { cliSel = e.dataset.c; [...$f("fzCli").options].forEach(o => { o.selected = !!cliSel && o.value === cliSel; }); '
     'render(); });', "furos: chip do cliente"),
    ('if (i === "fzOS") applyOS(); if (i === "fzCli") cliSel = $f("fzCli").value; render();',
     'if (i === "fzOS") applyOS(); if (i === "fzCli") { const v = vs("fzCli"); cliSel = v.length === 1 ? v[0] : ""; } render();',
     "furos: cliente escolhido"),
    # a aba Baixa performance (1.0.11) lê os mesmos filtros: vários valores também
    ('const q = norm($f("fzQ").value), s = $f("fzSrc").value, c = $f("fzCli").value, ca = $f("fzCart").value, '
     'mn = +$f("fzBpMin").value || 1;',
     'const q = norm($f("fzQ").value), s = vs("fzSrc"), c = vs("fzCli"), ca = vs("fzCart"), mn = +$f("fzBpMin").value || 1;',
     "furos: mural ler"),
    # no Nexus a 1ª conta lê o BD inteiro do banco (~40 s, medido em 13/11/2026); depois fica guardada até a próxima subida
    ('Calculando o mural com o BD e as paradas do COS… (uns 15 segundos)',
     'Calculando o mural com o BD do banco e as paradas do COS… (até 1 minuto na primeira vez do dia; depois é na hora)',
     "furos: mural espera"),
    ('if (s && x.fonte !== s) return false;', 'if (s.length && !s.includes(x.fonte)) return false;', "furos: mural fonte"),
    ('if (c && (!p || p.cliente !== c)) return false; if (ca && (!p || p.carteira !== ca)) return false;',
     'if (c.length && (!p || !c.includes(p.cliente))) return false; if (ca.length && (!p || !ca.includes(p.carteira))) '
     'return false;', "furos: mural cliente"),
    ('    $f("fzContagem").textContent = rr.length + " de " + all.length + " usinas";',
     '    $f("fzContagem").textContent = rr.length + " de " + all.length + " usinas";\n'
     '    if (window.coletasFiltros) window.coletasFiltros.atualizar();     // Nexus: a barra no modelo do Histórico de OS',
     "furos: barra"),
]


def gerar_furos_js(furos_js: str) -> str:
    t = furos_js.replace("\r\n", "\n")
    # no Nexus o CSV e o JSON são baixados pelo navegador (não vão para a "pasta do Conversor")
    t = _troca(t, 'toast("Salvo: " + p.split("\\\\").pop() + " (pasta do Conversor)");',
               'toast("Baixado: " + p.split("\\\\").pop());', "furos: salvar")
    t = _troca(t, 'toast("Salvo: " + p.split("\\\\").pop());', 'toast("Baixado: " + p.split("\\\\").pop());', "furos: html")
    # os filtros no modelo do Histórico de OS (Levi, 12/11/2026; static/coletas/filtros.js): cada filtro aceita VÁRIOS
    # valores (os <select> viram multiple; nenhum marcado = todos), e o desenho avisa a barra ao fim de cada render
    for velho, novo, onde in FUROS_VARIOS:
        t = _troca(t, velho, novo, onde)
    return ("// GERADO por ferramentas/portar_tela_conversor.py a partir do ui/furos.js do Conversor Grid Co.: não edite aqui.\n"
            + t)


def gerar(ui_dir):
    """Escreve a página e o furos.js; devolve (página, furos.js) para o teste comparar."""
    with open(os.path.join(ui_dir, "index.html"), encoding="utf-8") as f:
        pagina = gerar_pagina(f.read())
    with open(os.path.join(ui_dir, "furos.js"), encoding="utf-8") as f:
        furos = gerar_furos_js(f.read())
    return pagina, furos


def escrever(ui_dir):
    pagina, furos = gerar(ui_dir)
    os.makedirs(os.path.dirname(FUROS_JS), exist_ok=True)
    for caminho, texto in ((PAGINA, pagina), (FUROS_JS, furos)):
        with open(caminho, "w", encoding="utf-8", newline="\n") as f:
            f.write(texto)
    return PAGINA, FUROS_JS

// prova_gestao.js: roda o PRÓPRIO JavaScript do painel do PCM (js/preventivas.js + o pedaço do js/app.js que a aba
// Gestão PCM usa) contra o mesmo gestao_pcm.json que o Nexus lê, e devolve o que o painel desenharia.
//
// Quem chama é o nexus/pcm/prova_gestao.py (que compara com o Nexus célula a célula); este arquivo só lê a entrada
// pelo stdin e escreve a saída no stdout, em JSON. O código do painel roda num contexto `vm` isolado, sem `require`,
// sem rede e sem disco: só os dados e os stubs de navegador que ele usa (um `document` de mentira com os campos da
// barra de filtros e os quadros que o renderGestao escreve; sessionStorage).
//
// Entrada: {js: {preventivas, app}, gestao, mp, agora,
//           casos: [{id, gpv: {...}, topo}],                  o Plano & Fila (preventivas.js)
//           casosArv: [{id, topo, maxTabelas}]}               a aba além dele: números, árvores, Só atrasadas, listas
//   topo: nas chaves do GP_SEL do painel ({cliente, usina, cluster, resp, tipo, etq, estado}: valor ou lista) mais
//         {os, ss, pini, pfim, pmodo} (os campos de texto e de data da barra) e {atr} (o Só atrasadas)
// Saída:   {casos: {<id>: {plano | fila, kpis, n, par}}, arv: {<id>: {...}}, sub}
'use strict';
const vm = require('vm');

function lerTudo(stream) {
  return new Promise((ok, falha) => {
    const partes = [];
    stream.on('data', p => partes.push(p));
    stream.on('end', () => ok(Buffer.concat(partes).toString('utf8')));
    stream.on('error', falha);
  });
}

// Recorta do app.js uma declaração inteira pelo casamento de chaves (o painel não tem build: o app.js é um script só).
function recorta(fonte, inicio) {
  const i = fonte.indexOf(inicio);
  if (i < 0) throw new Error('não achei no app.js: ' + inicio);
  let j = fonte.indexOf('{', i), nivel = 0;
  for (; j < fonte.length; j++) {
    const c = fonte[j];
    if (c === '{') nivel++;
    else if (c === '}') { nivel--; if (nivel === 0) break; }
  }
  let fim = j + 1;
  if (fonte[fim] === ';') fim++;
  return fonte.slice(i, fim);
}

const DES = { '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#39;': "'" };
const desesc = s => String(s == null ? '' : s).replace(/&(amp|lt|gt|quot|#39);/g, m => DES[m]);
// texto visível da célula: sem tags, entidades desfeitas e espaços normalizados (o &#9679; vira ●, &#10003; vira ✓)
const texto = h => desesc(String(h).replace(/<[^>]*>/g, '')
  .replace(/&#(\d+);/g, (m, n) => String.fromCodePoint(+n)).replace(/&hellip;/g, '…')).replace(/\s+/g, ' ').trim();
// o texto de um nome, sem juntar os espaços (o Fracttal tem usina com espaço duplo, e a chave da árvore é ela inteira)
const nome = h => desesc(String(h).replace(/<[^>]*>/g, ''));
const attr = (h, nome) => { const m = new RegExp(nome + '="([^"]*)"').exec(h); return m ? desesc(m[1]) : null; };
const tds = h => { const out = [], rx = /<td([^>]*)>([\s\S]*?)<\/td>/g; let m; while ((m = rx.exec(h))) out.push({ a: m[1], h: m[2] }); return out; };
const linhas = h => h.split('<tr').slice(1).map(x => '<tr' + x.split('</tr>')[0]);
const etiquetas = h => { const out = [], rx = /<span class="gp-etq">([\s\S]*?)<\/span>/g; let m; while ((m = rx.exec(h))) out.push(nome(m[1])); return out; };
const pilula = h => /<span class="gp-pill ([^"]*)">([\s\S]*?)<\/span>/.exec(h) || [];

function celula(td) {
  const sp = /<span class="gpv-cel ([^"]*)"([\s\S]*?)>([\s\S]*?)<\/span>/.exec(td.h);
  if (!sp) return { cls: '', frac: false, title: '', txt: texto(td.h) };
  const cls = sp[1].split(/\s+/);
  return { cls: cls[0], frac: cls.indexOf('gpv-frac') >= 0, title: attr(sp[2], 'title') || '', txt: texto(sp[3]) };
}

function lerPlano(html, ncols) {
  const out = [];
  linhas(html.split('<tbody>')[1] || '').forEach(tr => {
    const k = /class="gpv-sub"/.test(tr) ? 'g' : /class="gpv-filho"/.test(tr) ? 'f'
      : /class="gpv-total"/.test(tr) ? 't' : /class=""/.test(tr) ? 'u' : 'vazio';
    if (k === 'vazio') { out.push({ k }); return; }
    const t = tds(tr);
    const nome = desesc((/<b>([\s\S]*?)<\/b>/.exec(t[0].h) || [])[1] || '');
    const mini = texto((/<span class="gpv-mini">([\s\S]*?)<\/span>/.exec(t[0].h) || [])[1] || '');
    const resto = t.slice(1);
    const cols = resto.slice(0, ncols).map(celula);
    const geral = celula(resto[ncols]);
    const pend = texto(resto[ncols + 1].h);
    let obs = null;
    if (resto.length > ncols + 2) {
      const o = resto[ncols + 2], b = /<span class="gpv-crit ([^"]*)">([\s\S]*?)<\/span>/.exec(o.h);
      obs = { critCls: b ? b[1] : '', crit: b ? desesc(b[2]) : '', title: attr(o.a, 'title'),
              vazio: !texto(o.h) || texto(o.h) === '—' };
    }
    out.push({ k, nome, mini, cols, geral: { cls: geral.cls, txt: geral.txt }, pend, obs });
  });
  return out;
}

function lerFila(html, temGer) {
  const out = [];
  const corpo = (html.split('<tbody>')[1] || '').split('</tbody>')[0];
  linhas(corpo).forEach(tr => {
    if (!/class="gma-lin/.test(tr)) return;
    const t = tds(tr).map(x => x.h), c = [];
    let i = 0;
    c.push(texto(t[i++]));                     // Cliente – Usina
    c.push(texto(t[i++]));                     // Tipo
    if (temGer) { c.push(texto(t[i++])); c.push(texto(t[i++])); }   // Criticidade, Prevista
    c.push(texto(t[i++]));                     // Programada (+ ● quando diverge)
    const atr = t[i++];
    c.push(texto(atr) + ((/gma-atr (f\d)/.exec(atr) || [])[1] ? '|' + /gma-atr (f\d)/.exec(atr)[1] : ''));
    c.push(texto(t[i++]));                     // OS
    c.push(texto(t[i++]));                     // Situação
    c.push(texto(t[i++]));                     // Última observação | Tarefas
    out.push({ conclu: /gma-ok/.test(tr.split('>')[0]), c });
  });
  return out;
}

function lerKpis(html) {
  const out = [], rx = /<div class="gma-kpi ([a-z]+)[^"]*"[^>]*><div class="v">([\s\S]*?)<\/div><div class="l">([\s\S]*?)<\/div>/g;
  let m; while ((m = rx.exec(html))) out.push({ cls: m[1], v: texto(m[2]), rot: texto(m[3]) });
  return out;
}

// A árvore do gpTreeHTML, andando pelas tags (div e span) com uma pilha: os nós em ordem, cada um com o nome, a
// contagem e, no tipo, as atrasadas e o índice da lista dele no GP_TIP_DATA. O bloco "Não Finalizadas no Período"
// (div.gp-nf-b) separa a árvore das não finalizadas da principal.
function lerArvore(html) {
  const out = { nfN: null, nf: [], todas: [], aberta: null, msg: null };
  const rx = /<(\/?)(div|span)([^>]*)>|([^<]+)/g, divs = [], spans = [];
  let m, cab = null;
  const naNf = () => divs.some(d => d.cls === 'gp-nf-b');
  while ((m = rx.exec(html))) {
    if (m[4] !== undefined) {
      const sp = spans[spans.length - 1];
      if (sp) sp.txt += m[4];
      else if (divs.length && divs[divs.length - 1].cls === 'gp-nores') out.msg = (out.msg || '') + m[4];
      continue;
    }
    const fecha = m[1] === '/', cls = (/class="([^"]*)"/.exec(m[3]) || [])[1] || '';
    if (m[2] === 'span') {
      if (!fecha) { spans.push({ cls, txt: '' }); continue; }
      const sp = spans.pop();
      if (!sp) continue;
      if (cab && sp.cls === 'nm') cab.nome = nome(sp.txt);
      else if (cab && /^gp-badge/.test(sp.cls)) cab.badges.push(texto(sp.txt));
      else if (sp.cls === 'gp-nf-badge') out.nfN = texto(sp.txt);
      continue;
    }
    if (fecha) {
      const d = divs.pop();
      if (d && d.cab) {
        const c = d.cab, no = { k: c.k, nome: c.nome, n: c.badges[0] || '' };
        if (c.k === 't') { no.atr = c.badges.length > 1 ? c.badges[1].replace(/^\D+/, '') : '0'; no.idx = c.idx; }
        (c.nf ? out.nf : out.todas).push(no);
        cab = null;
      }
      continue;
    }
    const d = { cls, cab: null }, nivel = { 'gp-cli-h': 'c', 'gp-usi-h': 'u', 'gp-tip-h': 't' }[cls];
    if (nivel) {
      cab = { k: nivel, nome: '', badges: [], nf: naNf(),
              idx: nivel === 't' ? +((/gpTogTip\(this,(\d+)\)/.exec(m[3]) || [])[1]) : null };
      d.cab = cab;
    }
    if (/^gp-cli( |$)/.test(cls) && !naNf() && out.aberta === null) out.aberta = / gp-open/.test(cls);
    divs.push(d);
  }
  if (out.msg !== null) out.msg = texto(out.msg);
  return out;
}

// A tabela de um tipo (gpTableHTML): OS, Tarefa, Estado, Etiquetas, Data Prog., Data Final, Dias
function lerTabela(html) {
  return linhas((html.split('<tbody>')[1] || '').split('</tbody>')[0]).map(tr => {
    const t = tds(tr).map(x => x.h), p = pilula(t[2]), d = /<span class="gp-dias ([^"]*)">([\s\S]*?)<\/span>/.exec(t[6]) || [];
    return { os: texto(t[0]).replace(/^#/, ''), tarefa: nome(t[1]), estado: nome(p[2] || ''), estadoCls: p[1] || '',
             etiquetas: etiquetas(t[3]), prog: texto(t[4]), fim: texto(t[5]), dias: texto(d[2] || ''), diasCls: d[1] || '' };
  });
}

// O Só atrasadas (gpFlatHTML): Dias, OS, Cliente, Usina, Tarefa, Tipo, Estado, Data Prog., Etiqueta, Observação da OS
function lerPlana(html) {
  const rows = linhas((html.split('<tbody>')[1] || '').split('</tbody>')[0]).map(tr => {
    const t = tds(tr), p = pilula(t[6].h), dd = /class="dd([^"]*)"/.exec(t[0].a);
    return { dias: texto(t[0].h), diasCls: dd ? dd[1].trim() : '', os: texto(t[1].h).replace(/^#/, ''),
             cliente: nome(t[2].h), usina: nome(t[3].h), tarefa: nome(t[4].h), tipo: nome(t[5].h), estado: nome(p[2] || ''),
             estadoCls: p[1] || '', prog: texto(t[7].h), etiquetas: etiquetas(t[8].h),
             obs: t[9].h.indexOf('<span class="gp-data">') === 0 ? '' : nome(t[9].h) };
  });
  return { cnt: (/<span class="cnt">(\d+)<\/span>/.exec(html) || [])[1] || null,
           lim: (/vermelho = mais de (\d+) dias/.exec(html) || [])[1] || null, rows,
           msg: /class="gp-nores"/.test(html) ? texto(html) : null };
}

// os ids que o renderGestao e o gpFilteredTarefas do painel leem e escrevem; o resto da página não existe aqui
const IDS = ['gp-tree', 'gp-sub', 'gp-k-vis', 'gp-k-fin', 'gp-k-ab', 'gp-k-atr', 'gp-kpi-fin', 'gp-kpi-atr', 'gp-atr-toggle',
  'tcnt-gestaoPcm', 'gp-f-os', 'gp-f-ss', 'gp-f-pini', 'gp-f-pfim', 'gp-f-pmodo',
  ...['cliente', 'usina', 'cluster', 'resp', 'tipo', 'etq', 'estado'].map(k => 'gp-ms-lbl-' + k)];

async function main() {
  const ent = JSON.parse(await lerTudo(process.stdin));
  const ctx = vm.createContext({ console: { info() {}, warn() {}, log() {} } });
  ctx.__gestao = JSON.stringify(ent.gestao);
  ctx.__mp = ent.mp ? JSON.stringify(ent.mp) : '';
  ctx.__ids = JSON.stringify(IDS);
  // relógio parado no mesmo instante que o lado Python usa: "hoje", os três meses e os dias de atraso batem
  vm.runInContext(`
    const __AGORA = ${Number(ent.agora)};
    const __Data = Date;
    class __DataFixa extends __Data {
      constructor(...a) { if (a.length === 0) super(__AGORA); else super(...a); }
      static now() { return __AGORA; }
    }
    Date = __DataFixa;
    var __IDS = new Set(JSON.parse(__ids)), __els = {};
    function __el(id) {
      if (!__els[id]) __els[id] = { id, value: '', textContent: '', title: '', innerHTML: '',
        classList: { toggle() {}, add() {}, remove() {}, contains() { return false; } },
        querySelectorAll() { return []; }, querySelector() { return null; } };
      return __els[id];
    }
    var document = { getElementById: id => __IDS.has(id) ? __el(id) : null, querySelector: () => null,
                     querySelectorAll: () => [], addEventListener() {} };
    var sessionStorage = { getItem: () => null, setItem() {} };
    var S = { user: '', isAdmin: true };
    var GP = { soAtrasadas: false };
    var GESTAO_DB = JSON.parse(__gestao);
    var MP = __mp ? JSON.parse(__mp) : null;
    function renderConfiab() {}
    function renderMttrCluster() {}
  `, ctx, { filename: 'prelúdio' });
  const app = ent.js.app;
  const linha = x => { const i = app.indexOf(x); if (i < 0) throw new Error('não achei no app.js: ' + x); return app.slice(i, app.indexOf('\n', i)); };
  const doApp = ['const CONFIG = {', 'function gpEsc(', 'function gpFmtData(', 'function gpWoUrl(', 'function gpTipoClass(',
                 'function gpEstadoPill(', 'function gpDiasCell(', 'function gpScopedTarefas(', 'const GP_MS=', 'const GP_SEL=',
                 'function gpMsOptions(', 'function gpMsLabel(', 'function gpVal(', 'function gpFilteredTarefas(',
                 'function gpNaoFin(', 'function gpTreeHTML(', 'function renderGestao(', 'function gpFlatHTML(',
                 'function gpTableHTML(', 'const mpBd=', 'function mpSit(', 'let GP_TIP_DATA='].map(x =>
    (x === 'const mpBd=' || x === 'let GP_TIP_DATA=') ? linha(x) : recorta(app, x)).join('\n');
  // o renderGestao do app.js antes do engate do preventivas.js (que o embrulha para desenhar também o Plano & Fila)
  vm.runInContext(doApp + '\nvar __renderGestaoOrig = renderGestao;', ctx, { filename: 'app.js (recorte)' });
  vm.runInContext(ent.js.preventivas, ctx, { filename: 'preventivas.js' });
  if (ent.mp) await vm.runInContext('gpvMpCarregar()', ctx);       // monta o mapa de criticidade/observação
  vm.runInContext(String.raw`
    // a barra de filtros do caso: as caixas (GP_SEL), os campos de texto e de data e o Só atrasadas
    function __porTopo(topo) {
      topo = topo || {};
      Object.keys(GP_SEL).forEach(k => {
        GP_SEL[k].clear();
        const v = topo[k];
        (Array.isArray(v) ? v : (v ? [v] : [])).forEach(x => { if (x) GP_SEL[k].add(x); });
      });
      ['os', 'ss', 'pini', 'pfim', 'pmodo'].forEach(k => { __el('gp-f-' + k).value = topo[k] || ''; });
      GP.soAtrasadas = !!topo.atr;
    }
    // a aba (renderGestao) com os filtros do caso: os números, o que ela desenha no quadro da árvore, as tabelas dos
    // tipos (todas ou uma amostra) e, de cada lista, o gpMsOptions do painel sobre as tarefas dos OUTROS filtros (a
    // cascata é regra do Nexus; a grafia e a ordem são as do painel)
    function __casoArv(json) {
      const caso = JSON.parse(json);
      __porTopo(caso.topo);
      __renderGestaoOrig(false);
      const html = __el('gp-tree').innerHTML;
      const out = { k: { vis: String(__el('gp-k-vis').textContent), fin: String(__el('gp-k-fin').textContent),
                         ab: String(__el('gp-k-ab').textContent), atr: String(__el('gp-k-atr').textContent),
                         finTitle: String(__el('gp-kpi-fin').title) }, html, tabelas: {}, opcoes: {} };
      const idxs = [], rx = /gpTogTip\(this,(\d+)\)/g;
      let m;
      while ((m = rx.exec(html))) idxs.push(+m[1]);
      const passo = Math.max(1, Math.ceil(idxs.length / (caso.maxTabelas || 1e9)));
      idxs.forEach((i, j) => { if (j % passo === 0) out.tabelas[i] = gpTableHTML(GP_TIP_DATA[i] || []); });
      Object.keys(GP_MS).forEach(k => {
        const guarda = GP_SEL[k];
        GP_SEL[k] = new Set();
        const sub = gpFilteredTarefas();
        GP_SEL[k] = new Set(guarda);                 // o gpMsOptions apaga do GP_SEL o que não está na lista
        const orig = gpScopedTarefas;
        gpScopedTarefas = () => sub;
        try { out.opcoes[k] = gpMsOptions(k); } finally { gpScopedTarefas = orig; GP_SEL[k] = guarda; }
      });
      return JSON.stringify(out);
    }
    // a linha "Atualizado: …" com o geradoEm lido como UTC (o robô grava em UTC sem fuso; o Nexus mostra Brasília)
    function __sub() {
      const g = GESTAO_DB.geradoEm;
      if (g && !/(?:[zZ]|[+-]\d\d:?\d\d)$/.test(g)) GESTAO_DB.geradoEm = g + 'Z';
      __porTopo({});
      try { __renderGestaoOrig(false); return String(__el('gp-sub').textContent); } finally { GESTAO_DB.geradoEm = g; }
    }
  `, ctx, { filename: 'prova (ajudantes)' });

  const saida = { casos: {}, arv: {}, sub: (ent.casosArv || []).length ? vm.runInContext('__sub()', ctx) : null };
  for (const caso of ent.casos) {
    ctx.__caso = JSON.stringify(caso);
    const r = vm.runInContext(`(() => {
      const caso = JSON.parse(__caso);
      __porTopo(caso.topo);
      Object.assign(GPV, caso.gpv);
      GPV.fechados = new Set(); GPV._dimAnterior = GPV.dim;       // grupos todos abertos: a prova lê todas as usinas
      _gpvBase = null; _gpvCacheKey = null;
      const temGer = !!(GPV_MP.estado === 'ok' && MP);
      const fila = temGer ? gpvFilaLinhas().filter(gpvFilaTopOk) : gpvFilaFracttal();
      const out = { par: gpvParTopo(fila, temGer), temGer, ncols: gpvCols().length };
      if (GPV.modo === 'plano') out.plano = gpvRenderPlano();
      else out.fila = gpvRenderFila(fila, temGer, false);
      return JSON.stringify(out);
    })()`, ctx, { filename: 'caso ' + caso.id });
    const o = JSON.parse(r);
    const res = { par: texto(o.par), temGer: o.temGer };
    if (o.plano !== undefined) res.plano = lerPlano(o.plano, o.ncols);
    else {
      res.fila = lerFila(o.fila, o.temGer);
      res.kpis = lerKpis(o.fila);
      const n = /<span class="gma-n">([\s\S]*?)<\/span>/.exec(o.fila);
      res.n = n ? texto(n[1]) : null;
    }
    saida.casos[caso.id] = res;
  }
  for (const caso of ent.casosArv || []) {
    ctx.__caso = JSON.stringify(caso);
    const o = JSON.parse(vm.runInContext('__casoArv(__caso)', ctx, { filename: 'aba ' + caso.id }));
    const res = { k: o.k, opcoes: o.opcoes };
    if (caso.topo && caso.topo.atr) res.plana = lerPlana(o.html);
    else {
      res.arvore = lerArvore(o.html);
      res.tabelas = {};
      Object.entries(o.tabelas).forEach(([i, h]) => { res.tabelas[i] = lerTabela(h); });
    }
    saida.arv[caso.id] = res;
  }
  process.stdout.write(JSON.stringify(saida));
}

main().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });

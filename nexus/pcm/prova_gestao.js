// prova_gestao.js: roda o PRÓPRIO JavaScript do painel do PCM (js/preventivas.js + o pedaço do js/app.js que ele usa)
// contra o mesmo gestao_pcm.json que o Nexus lê, e devolve as células que o painel desenharia.
//
// Quem chama é o nexus/pcm/prova_gestao.py (que compara com o Nexus célula a célula); este arquivo só lê a entrada
// pelo stdin e escreve a saída no stdout, em JSON. O código do painel roda num contexto `vm` isolado, sem `require`,
// sem rede e sem disco: só os dados e os stubs de navegador que ele usa (document, sessionStorage).
//
// Entrada: {js: {preventivas, app}, gestao, mp, agora, casos: [{id, gpv: {...}, topo: {cliente, usina, cluster, resp}}]}
// Saída:   {casos: {<id>: {plano: [...linhas], fila: [...linhas], kpis: [...], n, par: [...]}}}
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
const attr = (h, nome) => { const m = new RegExp(nome + '="([^"]*)"').exec(h); return m ? desesc(m[1]) : null; };
const tds = h => { const out = [], rx = /<td([^>]*)>([\s\S]*?)<\/td>/g; let m; while ((m = rx.exec(h))) out.push({ a: m[1], h: m[2] }); return out; };
const linhas = h => h.split('<tr').slice(1).map(x => '<tr' + x.split('</tr>')[0]);

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

async function main() {
  const ent = JSON.parse(await lerTudo(process.stdin));
  const ctx = vm.createContext({ console: { info() {}, warn() {}, log() {} } });
  ctx.__gestao = JSON.stringify(ent.gestao);
  ctx.__mp = ent.mp ? JSON.stringify(ent.mp) : '';
  // relógio parado no mesmo instante que o lado Python usa: "hoje", os três meses e os dias de atraso batem
  vm.runInContext(`
    const __AGORA = ${Number(ent.agora)};
    const __Data = Date;
    class __DataFixa extends __Data {
      constructor(...a) { if (a.length === 0) super(__AGORA); else super(...a); }
      static now() { return __AGORA; }
    }
    Date = __DataFixa;
    var document = { getElementById: () => null, querySelector: () => null, querySelectorAll: () => [] };
    var sessionStorage = { getItem: () => null, setItem() {} };
    var S = { user: '', isAdmin: true };
    var GP = { soAtrasadas: false };
    var GESTAO_DB = JSON.parse(__gestao);
    var MP = __mp ? JSON.parse(__mp) : null;
  `, ctx, { filename: 'prelúdio' });
  const app = ent.js.app;
  const doApp = ['function gpEsc(', 'function gpScopedTarefas(', 'const GP_MS=', 'const GP_SEL=', 'function gpVal(',
                 'function gpFilteredTarefas(', 'const mpBd=', 'function mpSit('].map(x => {
    if (x === 'const mpBd=') { const i = app.indexOf(x); return app.slice(i, app.indexOf('\n', i)); }
    return recorta(app, x);
  }).join('\n');
  vm.runInContext(doApp, ctx, { filename: 'app.js (recorte)' });
  vm.runInContext(ent.js.preventivas, ctx, { filename: 'preventivas.js' });
  if (ent.mp) await vm.runInContext('gpvMpCarregar()', ctx);       // monta o mapa de criticidade/observação

  const saida = {};
  for (const caso of ent.casos) {
    ctx.__caso = JSON.stringify(caso);
    const r = vm.runInContext(`(() => {
      const caso = JSON.parse(__caso);
      Object.keys(GP_SEL).forEach(k => GP_SEL[k].clear());
      Object.entries(caso.topo || {}).forEach(([k, v]) => { if (v) GP_SEL[k].add(v); });
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
    saida[caso.id] = res;
  }
  process.stdout.write(JSON.stringify({ casos: saida }));
}

main().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });

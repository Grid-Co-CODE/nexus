// GERADO por ferramentas/portar_tela_conversor.py a partir do ui/furos.js do Conversor Grid Co.: não edite aqui.
// Furos de coleta — tela 3 do Conversor (Levi, 11/11/2026: "inclua também na versão 1.0.3 esse HTML porém deixe estilo
// nexus, melhor os filtros e sempre centralize as tabelas"). A REGRA é a do relatório Furos_Coleta_Performance_18.html
// (calc, sugestões, OS que justificam, furo da UFV toda) — aqui só muda a cara: navy, um nível de superfície, cor só
// para estado (sem emoji), filtros agrupados com "Limpar filtros (n)", tabelas centralizadas. Os dados vêm do HTML mais
// novo da pasta de publicação (furos.py); as confirmações de cada pessoa ficam no app (furos_gravar_conf).
const furos = (() => {
  const $f = id => document.getElementById(id);
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  let REL = null, DB = null, MKEYS = [], MONTH = "", TAB = "col", cliSel = "";   // abre no "Para coletar" (13/11)
  // "Para coletar" (Levi, 13/11/2026, relato de quem coleta a Thopen no iSolarCloud): a lista do que falta por usina,
  // no formato da planilha de ronda dela (POA | GHI | Inversores | Ronda), com ONDE buscar no portal — "tem várias
  // Ceilândia, aí eu não sei qual delas devo clicar". PORTAL vem da aba Equipamentos do BD_Performance (furos.portal).
  let PORTAL = {}, RONDA = {};
  // Mural de baixa performance (Levi, 13/11/2026: "inversores com baixa performance... em relação aos demais... a média
  // ali é 100%... 70 para baixo"): calculado no app com o BD (mural.py), por mês; não vem do relatório de furos.
  const MURAL = {}; let bpSort = {k: "n", d: -1};
  const sortK = {res: "pend", det: "pend", col: "usina"}, sortD = {res: -1, det: -1, col: 1};
  const OPEN = {res: new Set(), det: new Set(), col: new Set()}, SHOWALL = new Set();
  const COLF = {res: {}, det: {}, col: {}}, CFO = {res: {}, det: {}, col: {}}, CATS = ["cliente", "carteira", "status", "src", "sit", "ronda"];
  const NUMK = new Set(["pendN", "confN", "ex", "inopN", "ipF", "ghF", "invF", "nInv", "cp", "comp"]);
  const MN = ["", "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
              "novembro", "dezembro"];
  const mlabel = k => MN[+k.split("-")[1]] + "/" + k.split("-")[0];
  const MOT = [
    {k: "sem_ipoa", l: "Usina sem sensor de IPOA (esperado)", ap: "ipoa"},
    {k: "sem_ghi", l: "Usina sem sensor de GHI (esperado)", ap: "ghi"},
    {k: "coleta_alt", l: "IPOA/dado vem de outra fonte (esperado)", ap: "both"},
    {k: "fora_op", l: "Equipamento inoperante / fora de operação (OK, mas fica sinalizado)", ap: "inv"},
    {k: "nao_mob", l: "Usina não mobilizada / fora de operação", ap: "both"},
    {k: "os", l: "Parada com OS / manutenção programada", ap: "both"},
    {k: "zero_real", l: "Zero real (geração confirmada, não é furo)", ap: "inv"},
    {k: "corrigido", l: "Dado já corrigido / não é falha", ap: "both"},
    {k: "outro", l: "Outro (descrever na observação)", ap: "both"}];
  const MOTL = Object.fromEntries(MOT.map(m => [m.k, m.l]));
  const isGen = e => e.nome !== "IPOA" && e.nome !== "GHI";
  const UFVN = "Furo de coleta da UFV toda";
  const tipoOf = n => n === UFVN ? "UFV" : n === "IPOA" ? "IPOA" : n === "GHI" ? "GHI" : "Inversor";
  const apOf = t => t === "IPOA" ? "ipoa" : t === "GHI" ? "ghi" : "inv";
  const norm = s => String(s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]/g, "");
  const KNOWN_NOIPOA = new Set(["ceuazul", "guatambu", "indaiatuba", "ipixuna1", "ipixuna2", "brodowski", "vargemgrande1"]);
  const SEVL = {ok: "Sem falha", at: "Falha", cr: "Falha crítica", cf: "Confirmado OK"};
  const ESTADO = {o: "coletado", v: "vazio", x: "linha ausente", z: "zerado", p: "usina sem geração",
                  a: "VALOR ANÔMALO (muito acima do padrão – coleta equivocada)", d: "IPOA ausente (só DEF)", w: "pendente"};

  // ---------------------------------------------------------------- confirmações
  let CONF = {};
  let gravarT = null;
  function save() {
    clearTimeout(gravarT);
    gravarT = setTimeout(() => { try { api().furos_gravar_conf(CONF); } catch (e) {} }, 300);
  }
  const ckey = (p, n) => p.src + "|" + p.usina + "|" + n;
  function getConf(p, n) { const c = CONF[ckey(p, n)]; return c && (c.v === "*" || c.v === MONTH) ? c : null; }
  function setConf(p, n, r, vig, obs) {
    const k = ckey(p, n);
    if (!r) { delete CONF[k]; save(); return; }
    const o = CONF[k] || {};
    CONF[k] = {r, v: vig === "*" ? "*" : MONTH, o: obs !== undefined ? obs : (o.o || ""), t: new Date().toISOString()};
    save();
  }

  // ---------------------------------------------------------------- utilitários (iguais ao relatório)
  const M = () => DB.months[MONTH], P = () => M().plants;
  const fmtD = d => String(d).padStart(2, "0") + "/" + MONTH.split("-")[1];
  const nat = n => n.split(/[^0-9]+/).filter(Boolean).map(Number);
  function cmpN(a, b) { const x = nat(a.nome), y = nat(b.nome); for (let i = 0; i < Math.max(x.length, y.length); i++) { const d = (x[i] || 0) - (y[i] || 0); if (d) return d; } return 0; }
  function ranges(idx, days) {
    const o = []; let a = null, b = null;
    idx.forEach(i => { const d = days[i]; if (a === null) { a = b = d; } else if (d === b + 1) { b = d; } else { o.push([a, b]); a = b = d; } });
    if (a !== null) o.push([a, b]);
    return o.map(([x, y]) => x === y ? String(x).padStart(2, "0") : String(x).padStart(2, "0") + "–" + String(y).padStart(2, "0")).join(", ");
  }
  function suggest(p, it) {
    if (it.tipo === "UFV") return null;
    const emp = p.eqs.filter(isGen).every(e => [...e.st].every(c => "vxwe".includes(c)));
    const n = p.eqs[it.i].st.replace(/w/g, "").length, pc = n ? Math.round(100 * it.idx.length / n) : 0;
    if (p.status && p.status !== "OPERAÇÃO") return ["nao_mob", "Status da usina: " + p.status];
    if (it.tipo === "IPOA") {
      if (KNOWN_NOIPOA.has(norm(p.usina))) return ["sem_ipoa", "Consta nas notas Thopen (07/10) como usina sem IPOA/GHI"];
      if (n >= 5 && pc >= 90) return ["sem_ipoa", "IPOA ausente em " + pc + "% dos dias – provável usina sem sensor"];
    } else if (it.tipo === "GHI") { if (n >= 5 && pc >= 90) return ["sem_ghi", "GHI ausente em " + pc + "% dos dias – provável usina sem sensor"]; }
    else if (!emp && n >= 5 && pc >= 90) return ["fora_op", "Sem geração/coleta em " + pc + "% dos dias – provável equipamento fora de operação"];
    return null;
  }
  function calc(p) {
    const z = $f("fzZero").checked, useC = $f("fzConf").checked, items = []; let cellT = 0; const tmp = [];
    p.eqs.forEach((e, i) => {
      const s = e.st, bs = e.nome === "IPOA" ? (z ? "vxdza" : "vxda") : (z ? "vxza" : "vxa"), idx = [], zi = [];
      for (let k = 0; k < s.length; k++) { if (bs.includes(s[k])) idx.push(k); if (s[k] === "z") zi.push(k); if (s[k] !== "w" && s[k] !== "p") cellT++; }
      tmp.push({e, i, idx, zi});
    });
    // furo de coleta da UFV toda: dias em que TODOS os inversores estão em falha viram um único item
    const G = tmp.filter(x => isGen(x.e)); let ufv = null;
    if (G.length >= 2) {
      const D = G[0].idx.filter(k => G.every(x => x.idx.includes(k)));
      if (D.length) {
        const Ds = new Set(D);
        G.forEach(x => { x.idx = x.idx.filter(k => !Ds.has(k)); x.zi = x.zi.filter(k => !Ds.has(k)); });
        let c = getConf(p, UFVN); if (!c && G.every(x => getConf(p, x.e.nome))) c = getConf(p, G[0].e.nome);
        ufv = {e: {nome: UFVN, st: G[0].e.st}, i: -1, nome: UFVN, tipo: "UFV", idx: D, zi: [], conf: c, ok: !!(c && useC), w: G.length};
      }
    }
    if (ufv) items.push(ufv);
    tmp.forEach(x => { if (x.idx.length) { const c = getConf(p, x.e.nome); items.push({e: x.e, i: x.i, nome: x.e.nome, tipo: tipoOf(x.e.nome), idx: x.idx, zi: x.zi, conf: c, ok: !!(c && useC)}); } });
    const pend = items.filter(t => !t.ok), done = items.filter(t => t.ok);
    const inop = p.eqs.filter(e => { if (!isGen(e) || !/[vxzp]/.test(e.st)) return false; const c = getConf(p, e.nome); return c && c.r === "fora_op"; }).map(e => e.nome);
    const cp = pend.reduce((a, t) => a + t.idx.length * (t.w || 1), 0), cc = done.reduce((a, t) => a + t.idx.length * (t.w || 1), 0);
    const empty = p.eqs.every(e => [...e.st].every(c => "vxdwe".includes(c))); const ex = p.eqs.reduce((a, e) => a + (e.st.split("e").length - 1), 0);
    const comp = cellT ? 1 - cp / cellT : 1;
    const sit = pend.length ? "falha" : (items.length ? "conf" : "ok");
    let sev = "ok"; if (pend.length) sev = (empty && pend.length === items.length) || comp < .5 ? "cr" : "at";
    const ipP = pend.find(t => t.tipo === "IPOA"), ghP = pend.find(t => t.tipo === "GHI"), invP = pend.filter(t => t.tipo === "Inversor");
    return {ufv, items, pend, done, cp, cc, cellT, comp, empty, sit, sev, ex, noos: (p.os || []).filter(o => o[6] === "A").length,
            ipF: ipP ? ipP.idx.length : 0, ghF: ghP ? ghP.idx.length : 0, invF: invP.length, nInv: p.eqs.filter(isGen).length,
            pendN: pend.length, confN: done.length, inop, inopN: inop.length};
  }
  function falhaTxt(p, m) {
    const parts = [];
    if (m.empty && m.pendN === m.items.length && m.pendN) parts.push('<b class="fz-cr">Sem nenhuma coleta no mês</b>');
    const uf = m.pend.find(t => t.tipo === "UFV");
    if (uf) parts.push('<b class="fz-cr">Furo de coleta da UFV toda</b> (todos os ' + uf.w + " inversores) " + uf.idx.length + " dia(s) <small>(" + ranges(uf.idx, p.days) + ")</small>");
    const ip = m.pend.find(t => t.tipo === "IPOA"); if (ip) parts.push("<b>IPOA</b> ausente " + ip.idx.length + " dia(s) <small>(" + ranges(ip.idx, p.days) + ")</small>");
    const gh = m.pend.find(t => t.tipo === "GHI"); if (gh) parts.push("<b>GHI</b> ausente " + gh.idx.length + " dia(s) <small>(" + ranges(gh.idx, p.days) + ")</small>");
    const iv = m.pend.filter(t => t.tipo === "Inversor");
    if (iv.length) { const nm = iv.slice(0, 4).map(t => t.nome.replace(/^Inversor\s*/i, "")).join(", "); parts.push("<b>" + iv.length + " de " + m.nInv + " inversor(es)</b> com furo: " + nm + (iv.length > 4 ? " +" + (iv.length - 4) : "")); }
    const an = m.pend.reduce((a, t) => a + t.idx.filter(k => t.e.st[k] === "a").length, 0);
    if (an) parts.push('<b class="fz-an">' + an + " célula(s) com valor anômalo</b> <small>(muito acima do padrão – coleta equivocada)</small>");
    if (m.inopN) parts.push('<small class="fz-in"><b>' + m.inopN + " equipamento(s) inoperante(s)</b> (sem geração esperada): " + m.inop.slice(0, 6).map(n => n.replace(/^Inversor\s*/i, "")).join(", ") + (m.inopN > 6 ? " +" + (m.inopN - 6) : "") + "</small>");
    if (m.confN) parts.push('<small class="fz-okt">' + m.confN + " item(ns) confirmado(s) OK</small>");
    return parts.join("<br>") || "<small>—</small>";
  }
  // "Falha identificada" resumida em selos curtos (Levi, 11/11/2026: "resuma mais a falha identificada"); o texto completo
  // (datas, inversores) fica no passar o mouse e no painel da usina
  function falhaResumo(p, m) {
    const k = (cls, txt, tip) => `<span class="fz-k ${cls}" title="${esc(tip || "")}">${txt}</span>`;
    const dias = n => n + (n === 1 ? " dia" : " dias");
    const out = [];
    const uf = m.pend.find(t => t.tipo === "UFV");
    if (m.empty && m.pendN === m.items.length && m.pendN) {
      out.push(k("k-cr", "Sem coleta no mês", "Nenhuma coleta no mês"));
    } else {
      if (uf) out.push(k("k-cr", "UFV toda · " + dias(uf.idx.length), "Furo de coleta da UFV toda (" + uf.w + " inversores): " + ranges(uf.idx, p.days)));
      const iv = m.pend.filter(t => t.tipo === "Inversor");
      if (iv.length) out.push(k("k-at", "Inversores · " + iv.length + "/" + m.nInv, iv.map(t => t.nome.replace(/^Inversor\s*/i, "") + " (" + ranges(t.idx, p.days) + ")").join(", ")));
      const ip = m.pend.find(t => t.tipo === "IPOA"), gh = m.pend.find(t => t.tipo === "GHI");
      if (ip && gh && ip.idx.length === gh.idx.length) out.push(k("k-at", "IPOA e GHI · " + dias(ip.idx.length), "IPOA: " + ranges(ip.idx, p.days) + " · GHI: " + ranges(gh.idx, p.days)));
      else {
        if (ip) out.push(k("k-at", "IPOA · " + dias(ip.idx.length), "IPOA ausente: " + ranges(ip.idx, p.days)));
        if (gh) out.push(k("k-at", "GHI · " + dias(gh.idx.length), "GHI ausente: " + ranges(gh.idx, p.days)));
      }
    }
    const an = m.pend.reduce((a, t) => a + t.idx.filter(x => t.e.st[x] === "a").length, 0);
    if (an) out.push(k("k-an", "Anômalo · " + an, "Células com valor muito acima do padrão (coleta equivocada)"));
    if (m.inopN) out.push(k("k-in", "Inoperante · " + m.inopN, m.inop.join(", ")));
    if (m.confN) out.push(k("k-ok", "Confirmado · " + m.confN, m.confN + " item(ns) confirmado(s) OK"));
    if (!out.length) return m.ex ? k("k-os", "OS/ticket · " + m.ex, m.ex + " célula(s) com ausência esperada por OS/ticket") : '<small class="f">Sem falha</small>';
    return '<div class="fz-ks">' + out.join("") + "</div>";
  }

  // ---------------------------------------------------------------- OS / ticket = ausência esperada
  function applyOS() {
    const on = $f("fzOS").checked;
    Object.values(DB.months).forEach(mv => mv.plants.forEach(p => p.eqs.forEach(e => {
      if (e.st0 === undefined) e.st0 = e.st;
      if (!e.cv || !on) { e.st = e.st0; return; }
      const a = [...e.st0]; Object.keys(e.cv).forEach(k => { if ("vxzpd".includes(a[k])) a[k] = "e"; }); e.st = a.join("");
    })));
  }
  function osTxt(p, e, i) {
    const r = e.cv && e.cv[i];
    return r ? r.map(j => { const o = p.os[j]; return (o[6] === "A" ? "COS sem OS" : (o[0] === "T" ? "ticket " : "OS ") + o[1]) + " (" + o[2] + ")"; }).join("; ") : "";
  }

  // ---------------------------------------------------------------- filtros
  const FILTROS = ["fzQ", "fzCli", "fzCart", "fzSrc", "fzSt", "fzSit"];
  // Nexus (Coletas): vários valores por filtro, como o Histórico de OS; nenhum marcado = todos
  const vs = i => [...$f(i).options].filter(o => o.selected && o.value !== "").map(o => o.value);
  const sitOk = (x, m) => x === "falha" ? m.sit === "falha" : x === "conf" ? m.sit === "conf" : x === "ok" ? m.sit === "ok" :
    x === "ipoa" ? !!m.ipF : x === "ghi" ? !!m.ghF : x === "inop" ? !!m.inopN : x === "os" ? !!m.ex : x === "noos" ? !!m.noos :
    x === "inv" ? !!m.invF : true;
  const FALTA = [["fzFInv", "inv"], ["fzFIpoa", "ipoa"], ["fzFGhi", "ghi"]];
  // falta marcada: todas ligadas = sem filtro; senão a usina precisa ter pendência de um dos tipos ligados
  const faltaOn = () => FALTA.filter(([i]) => $f(i).checked).map(([, t]) => t);
  const temFalta = (m, tipos) => tipos.some(t => t === "inv" ? (m.invF || m.pend.some(x => x.tipo === "UFV")) : t === "ipoa" ? m.ipF : m.ghF);
  function fillFilters() {
    const ps = P(), keep = [vs("fzCli"), vs("fzCart"), vs("fzSt")];
    $f("fzCli").innerHTML = '<option value="">Todos</option>' + [...new Set(ps.map(p => p.cliente))].sort().map(c => `<option>${esc(c)}</option>`).join("");
    $f("fzCart").innerHTML = '<option value="">Todas</option>' + [...new Set(ps.filter(p => p.cliente === "Thopen").map(p => p.carteira))].sort().map(c => `<option>${esc(c)}</option>`).join("");
    $f("fzSt").innerHTML = '<option value="">Todos</option>' + [...new Set(ps.map(p => p.status || "—"))].sort().map(c => `<option>${esc(c)}</option>`).join("");
    [["fzCli", 0], ["fzCart", 1], ["fzSt", 2]].forEach(([i, k]) => [...$f(i).options].forEach(o => { o.selected = o.value !== "" && keep[k].includes(o.value); }));
  }
  function ativos() {
    let n = FILTROS.filter(i => i === "fzQ" ? $f(i).value : vs(i).length).length;
    if (TAB === "col" && faltaOn().length < FALTA.length) n++;
    n += Object.values(COLF[TAB]).filter(v => v !== "").length;
    return n;
  }
  function limparFiltros() {
    FILTROS.forEach(i => { if (i === "fzQ") $f(i).value = ""; else [...$f(i).options].forEach(o => { o.selected = false; }); }); FALTA.forEach(([i]) => { $f(i).checked = true; });
    cliSel = ""; COLF.res = {}; COLF.det = {}; COLF.col = {}; render();
  }
  const rowsAll = () => P().map(p => ({p, m: calc(p)}));
  function filtered() {
    const q = $f("fzQ").value.toLowerCase(), c = vs("fzCli"), ca = vs("fzCart"), s = vs("fzSrc"), st = vs("fzSt"), sit = vs("fzSit");
    const tipos = faltaOn(), restringe = TAB === "col" && tipos.length < FALTA.length;
    return rowsAll().filter(({p, m}) => {
      if (restringe && !temFalta(m, tipos)) return false;
      if (c.length && !c.includes(p.cliente)) return false; if (ca.length && !ca.includes(p.carteira)) return false; if (s.length && !s.includes(p.src)) return false;
      if (st.length && !st.includes(p.status || "—")) return false; if (q && !p.usina.toLowerCase().includes(q)) return false;
      if (sit.length && !sit.some(x => sitOk(x, m))) return false;
      return true;
    });
  }
  const sitLbl = m => m.sit === "falha" ? SEVL[m.sev] : m.sit === "conf" ? "Confirmado OK" : "Sem falha";
  function colVal(k, {p, m}) {
    switch (k) {
      case "usina": return p.usina; case "cliente": return p.cliente; case "carteira": return p.carteira; case "status": return p.status || "—";
      case "src": return p.src; case "sit": return sitLbl(m); case "falha": return (falhaResumo(p, m) + " " + falhaTxt(p, m)).replace(/<[^>]+>/g, " ");
      case "comp": return Math.round(m.comp * 100);
      case "ipD": return ipTxt(p, m); case "ghD": return ghTxt(p, m); case "invD": return invTxt(p, m);
      case "portal": return portalTxt(p, m).replace(/<[^>]+>/g, " "); case "ronda": return RONDA[rkey(p)] ? "feita" : "";
      default: return m[k];
    }
  }
  function numOk(v, q) {
    const r = q.match(/^\s*(>=|<=|!=|>|<|=)?\s*(-?\d+(?:[.,]\d+)?)\s*$/);
    if (!r) return String(v).includes(q.trim());
    const n = parseFloat(r[2].replace(",", ".")), o = r[1] || "="; v = +v || 0;
    return o === ">" ? v > n : o === "<" ? v < n : o === ">=" ? v >= n : o === "<=" ? v <= n : o === "!=" ? v !== n : v === n;
  }
  function applyCol(rows, tab) {
    const f = COLF[tab], ks = Object.keys(f).filter(k => f[k] !== ""); if (!ks.length) return rows;
    return rows.filter(r => ks.every(k => { const v = colVal(k, r), q = f[k]; if (CATS.includes(k)) return String(v) === q; if (NUMK.has(k)) return numOk(v, q); return norm(v).includes(norm(q)); }));
  }
  function sortRows(rows, tab) {
    const k = sortK[tab], d = sortD[tab], sv = {falha: 2, conf: 1, ok: 0};
    const val = ({p, m}) => k === "sit" ? sv[m.sit] : k === "pend" ? (m.sit === "falha" ? 1e6 : m.sit === "conf" ? 5e5 : m.inopN ? 1e5 : 0) + m.cp : (k in m ? m[k] : (p[k] || ""));
    rows.sort((a, b) => { const x = val(a), y = val(b); return (x > y ? 1 : x < y ? -1 : 0) * d || (b.m.cp - a.m.cp) || a.p.usina.localeCompare(b.p.usina); });
  }

  // ---------------------------------------------------------------- desenho
  const rid = p => p.src + "|" + p.usina;
  const sitBadge = m => m.sit === "falha" ? `<span class="fz-b fz-b-${m.sev}">${SEVL[m.sev]}</span>` : m.sit === "conf" ? '<span class="fz-b fz-b-cf">Confirmado OK</span>' : '<span class="fz-b fz-b-ok">Sem falha</span>';
  const rowCls = m => m.sit === "falha" ? "gap g-" + m.sev + (m.inopN ? " inop" : "") : (m.sit === "conf" || m.inopN) ? "cf" + (m.inopN ? " inop" : "") : "nogap";
  const noosBadge = m => m.noos ? ` <span class="fz-b fz-b-at" title="Parada registrada no COS sem número de OS">${m.noos} parada(s) sem OS</span>` : "";
  const inopBadge = m => m.inopN ? ` <span class="fz-b fz-b-in" title="${esc(m.inop.join(", "))}">${m.inopN} inoperante(s)</span>` : "";

  function head(cols, tab) {
    const f = COLF[tab];
    const cell = ([k, , nn]) => {
      const v = f[k] || "", on = v !== "" ? " on" : "";
      if (CATS.includes(k)) return `<td><select data-cf="${k}" class="${on}"><option value="">Todos</option>${(CFO[tab][k] || []).map(o => `<option ${o === v ? "selected" : ""}>${esc(o)}</option>`).join("")}</select></td>`;
      return `<td><input data-cf="${k}" class="${on}" value="${esc(v)}" placeholder="${NUMK.has(k) ? "ex.: >0" : "filtrar…"}"></td>`;
    };
    $f("fzTb").tHead.innerHTML = "<tr>" + cols.map(([k, l]) => `<th data-k="${k}">${l}${sortK[tab] === k ? (sortD[tab] > 0 ? " ▲" : " ▼") : ""}</th>`).join("") +
      '</tr><tr class="fz-cf">' + cols.map(cell).join("") + "</tr>";
    $f("fzTb").tHead.querySelectorAll("th").forEach(t => t.onclick = () => {
      const k = t.dataset.k; if (sortK[tab] === k) sortD[tab] *= -1; else { sortK[tab] = k; sortD[tab] = (k === "usina" || k === "cliente") ? 1 : -1; } render();
    });
  }
  function renderRes(rows) {
    head([["usina", "Usina"], ["cliente", "Cliente"], ["carteira", "Carteira"], ["status", "Status"], ["src", "Fonte"], ["falha", "Falha identificada"],
          ["pendN", "Pendentes", 1], ["confN", "Confirmados", 1], ["ex", "Esperado c/ OS", 1], ["inopN", "Inoperantes", 1], ["sit", "Situação"]], "res");
    sortRows(rows, "res"); let h = "";
    rows.forEach(({p, m}) => {
      const id = rid(p);
      h += `<tr class="pl ${rowCls(m)}${OPEN.res.has(id) ? " aberta" : ""}" data-id="${esc(id)}"><td><b>${esc(p.usina)}</b></td><td>${esc(p.cliente)}</td><td>${esc(p.carteira)}</td><td>${esc(p.status || "—")}</td><td>${esc(p.src)}</td><td class="fz-falha">${falhaResumo(p, m)}</td><td>${m.pendN}</td><td>${m.confN}</td><td>${m.ex || ""}</td><td>${m.inopN || ""}</td><td>${sitBadge(m)}${inopBadge(m)}${noosBadge(m)}</td></tr>`;
      if (OPEN.res.has(id)) h += `<tr class="fz-det"><td colspan="11">${panel(p, m)}</td></tr>`;
    });
    $f("fzTb").tBodies[0].innerHTML = h || '<tr><td colspan="11" class="fz-vazio">Nenhuma usina para os filtros.</td></tr>';
  }
  function renderDet(rows) {
    head([["usina", "Usina"], ["cliente", "Cliente"], ["carteira", "Carteira"], ["status", "Status"], ["src", "Fonte"], ["ipF", "Dias sem IPOA", 1], ["ghF", "Dias sem GHI", 1],
          ["invF", "Inversores c/ furo", 1], ["nInv", "Total inv.", 1], ["cp", "Células c/ furo", 1], ["comp", "Completude", 1], ["inopN", "Inoperantes", 1], ["sit", "Situação"]], "det");
    sortRows(rows, "det"); let h = "";
    rows.forEach(({p, m}) => {
      const id = rid(p);
      h += `<tr class="pl ${rowCls(m)}${OPEN.det.has(id) ? " aberta" : ""}" data-id="${esc(id)}"><td><b>${esc(p.usina)}</b></td><td>${esc(p.cliente)}</td><td>${esc(p.carteira)}</td><td>${esc(p.status || "—")}</td><td>${esc(p.src)}</td><td>${m.ipF}</td><td>${m.ghF}</td><td>${m.invF}</td><td>${m.nInv}</td><td>${m.cp}</td><td><span class="fz-bar"><i style="width:${(m.comp * 100).toFixed(0)}%"></i></span>${(m.comp * 100).toFixed(0)}%</td><td>${m.inopN || ""}</td><td>${sitBadge(m)}${inopBadge(m)}${noosBadge(m)}</td></tr>`;
      if (OPEN.det.has(id)) h += `<tr class="fz-det"><td colspan="13">${heat(p, m)}</td></tr>`;
    });
    $f("fzTb").tBodies[0].innerHTML = h || '<tr><td colspan="13" class="fz-vazio">Nenhuma usina para os filtros.</td></tr>';
  }
  // ---------------------------------------------------------------- Para coletar
  const rkey = p => MONTH + "|" + p.src + "|" + p.usina;
  const curto = n => n.replace(/^Inversor\s*/i, "");
  const eqN = n => String(n).replace(/(\d),(\d)/g, "$1.$2");
  function ipTxt(p, m) { if (!faltaOn().includes("ipoa")) return ""; const t = m.pend.find(x => x.tipo === "IPOA"); return t ? ranges(t.idx, p.days) : ""; }
  function ghTxt(p, m) { if (!faltaOn().includes("ghi")) return ""; const t = m.pend.find(x => x.tipo === "GHI"); return t ? ranges(t.idx, p.days) : ""; }
  function invTxt(p, m) {
    if (!faltaOn().includes("inv")) return "";
    const out = [], uf = m.pend.find(x => x.tipo === "UFV");
    if (uf) out.push("UFV toda: " + ranges(uf.idx, p.days));
    m.pend.filter(x => x.tipo === "Inversor").forEach(t => out.push("Inv " + curto(t.nome) + " (" + ranges(t.idx, p.days) + ")"));
    return out.join("; ");
  }
  // planta e equipamento no portal; sem de-para no cadastro, a planta provável pelos irmãos (2.3 -> a planta do 2.x)
  function portalDe(p, nome) {
    const u = PORTAL[p.usina]; if (!u) return null;
    const x = u.inv[eqN(nome)]; if (x) return {pl: x[0], eq: x[1]};
    const pre = (eqN(nome).match(/(\d+)\.\d+$/) || [])[1];
    const irmao = pre && Object.entries(u.inv).find(([k]) => (k.match(/(\d+)\.\d+$/) || [])[1] === pre);
    return {pl: irmao ? irmao[1][0] : null, eq: null};
  }
  function portalTxt(p, m) {
    const u = PORTAL[p.usina], tipos = faltaOn();
    if (!u) return '<small class="f">sem a usina no cadastro Equipamentos</small>';
    const por = {}, sem = [];
    const add = (pl, txt) => { (por[pl] = por[pl] || []).push(txt); };
    if (tipos.includes("inv")) {
      if (m.pend.some(x => x.tipo === "UFV")) u.plantas.forEach(pl => add(pl, "todos"));
      m.pend.filter(x => x.tipo === "Inversor").forEach(t => {
        const d = portalDe(p, t.nome);
        if (d && d.eq) add(d.pl, d.eq);
        else if (d && d.pl) add(d.pl, curto(t.nome) + " sem de-para no cadastro");
        else sem.push(curto(t.nome));
      });
    }
    if (!Object.keys(por).length && !sem.length && (m.pend.some(x => x.tipo === "IPOA" || x.tipo === "GHI")))
      u.plantas.forEach(pl => add(pl, "estação"));
    const h = Object.entries(por).map(([pl, eqs]) => "<b>" + esc(pl) + "</b>: " + esc([...new Set(eqs)].join(", ")));
    if (sem.length) h.push('<span class="fz-an">' + esc(sem.join(", ")) + " sem de-para no cadastro</span>");
    return h.join("<br>") || '<small class="f">—</small>';
  }
  function linhasCol(rows) {
    const tipos = faltaOn();
    return rows.filter(({m}) => temFalta(m, tipos));
  }
  function renderCol(rows) {
    head([["usina", "Usina"], ["src", "Fonte"], ["ipD", "POA (dias)"], ["ghD", "GHI (dias)"], ["invD", "Inversores (dias)"],
          ["portal", "Onde buscar no portal"], ["ronda", "Ronda"]], "col");
    sortRows(rows, "col"); let h = "";
    rows.forEach(({p, m}) => {
      const id = rid(p), feita = !!RONDA[rkey(p)];
      h += `<tr class="pl ${feita ? "fz-feito" : rowCls(m)}" data-id="${esc(id)}"><td><b>${esc(p.usina)}</b></td><td>${esc(p.src.replace("BD_", ""))}</td>` +
        `<td>${esc(ipTxt(p, m))}</td><td>${esc(ghTxt(p, m))}</td><td class="fz-inv">${esc(invTxt(p, m))}</td><td class="fz-portal">${portalTxt(p, m)}</td>` +
        `<td><input type="checkbox" class="fz-ronda" data-a="ronda" data-id="${esc(id)}" ${feita ? "checked" : ""} title="${feita ? "Ronda feita em " + esc(RONDA[rkey(p)]) : "Marcar a ronda desta usina"}"></td></tr>`;
    });
    $f("fzTb").tBodies[0].innerHTML = h || '<tr><td colspan="7" class="fz-vazio">Nenhuma usina com falta para os filtros.</td></tr>';
  }
  function listaTsv() {
    const L = [["Usina", "Fonte", "POA (dias)", "GHI (dias)", "Inversores (dias)", "Onde buscar no portal", "Ronda"]];
    const rr = applyCol(linhasCol(filtered()), "col"); sortRows(rr, "col");
    rr.forEach(({p, m}) => L.push([p.usina, p.src, ipTxt(p, m), ghTxt(p, m), invTxt(p, m),
      portalTxt(p, m).replace(/<br>/g, " | ").replace(/<[^>]+>/g, ""), RONDA[rkey(p)] ? "feita" : ""]));
    return L;
  }
  async function copiarLista() {
    const texto = (TAB === "bp" ? bpTsv() : listaTsv()).map(r => r.join("\t")).join("\r\n");
    let ok = false;
    try { if (window.pywebview && window.pywebview.api && window.pywebview.api.copiar) ok = await api().copiar(texto); } catch (e) {}
    if (!ok) { try { await navigator.clipboard.writeText(texto); ok = true; } catch (e) {} }
    toast(ok ? "Lista copiada — cole no Excel com Ctrl+V" : "Não consegui copiar");
  }
  // ---------------------------------------------------------------- Mural de baixa performance
  const pct = r => Math.round(r * 100) + "%";
  const bpCls = r => r <= 0.5 ? "fz-b-cr" : "fz-b-at";
  function bpLinhas() {
    const dm = MURAL[MONTH]; if (!dm || !dm.linhas) return [];
    const q = norm($f("fzQ").value), s = vs("fzSrc"), c = vs("fzCli"), ca = vs("fzCart"), mn = +$f("fzBpMin").value || 1;
    const porU = {}; P().forEach(p => { porU[p.src + "|" + p.usina] = p; });
    const L = dm.linhas.filter(x => {
      const p = porU[x.fonte + "|" + x.usina];
      if (x.n < mn) return false; if (s.length && !s.includes(x.fonte)) return false; if (q && !norm(x.usina).includes(q)) return false;
      if (c.length && (!p || !c.includes(p.cliente))) return false; if (ca.length && (!p || !ca.includes(p.carteira))) return false;
      return true;
    });
    const k = bpSort.k, d = bpSort.d;
    L.sort((a, b) => { const x = a[k], y = b[k]; return ((x > y ? 1 : x < y ? -1 : 0) * d) || (b.n - a.n) || (a.pior - b.pior); });
    return L;
  }
  const bpDias = x => ranges(x.dias.map((_, i) => i), x.dias.map(([dd]) => +dd.slice(8, 10)));
  const bpTip = x => x.dias.map(([dd, r]) => dd.slice(8, 10) + "/" + dd.slice(5, 7) + ": " + pct(r)).join(" · ");
  function bpPortal(x) {
    const d = portalDe({usina: x.usina}, x.inversor);
    return d && d.eq ? "<b>" + esc(d.pl) + "</b>: " + esc(d.eq) : d && d.pl ? "<b>" + esc(d.pl) + "</b>" : '<small class="f">—</small>';
  }
  function renderBp() {
    const dm = MURAL[MONTH];
    if (!dm) {
      MURAL[MONTH] = {carregando: true};
      Promise.resolve(api().furos_mural(MONTH)).then(r => { MURAL[MONTH] = r || {erro: "sem resposta"}; if (TAB === "bp") render(); });
    }
    const cols = [["usina", "Usina"], ["fonte", "Fonte"], ["inversor", "Inversor"], ["n", "Dias ≤ 70%"], ["comparados", "Dias comparados"],
                  ["pior", "Pior dia"], ["media", "Média nos dias baixos"], ["ultimo", "Dias"], ["portal", "Onde buscar no portal"], ["base", "Base"]];
    $f("fzTb").tHead.innerHTML = "<tr>" + cols.map(([k, l]) => `<th data-bk="${k}">${l}${bpSort.k === k ? (bpSort.d > 0 ? " ▲" : " ▼") : ""}</th>`).join("") + "</tr>";
    $f("fzTb").tHead.querySelectorAll("th").forEach(t => t.onclick = () => {
      const k = t.dataset.bk; if (k === "portal") return;
      if (bpSort.k === k) bpSort.d *= -1; else { bpSort.k = k; bpSort.d = (k === "usina" || k === "inversor" || k === "fonte" || k === "pior" || k === "media") ? 1 : -1; }
      render();
    });
    const m = MURAL[MONTH];
    if (m.carregando) { $f("fzTb").tBodies[0].innerHTML = '<tr><td colspan="10" class="fz-vazio">Calculando o mural com o BD do banco… (até 1 minuto na primeira vez do dia; depois é na hora)</td></tr>'; return; }
    if (m.erro) { $f("fzTb").tBodies[0].innerHTML = '<tr><td colspan="10" class="fz-vazio">' + esc(m.erro) + "</td></tr>"; return; }
    const L = bpLinhas();
    $f("fzTb").tBodies[0].innerHTML = L.map(x => `<tr class="pl ${x.pior <= 0.5 ? "gap g-cr" : "gap g-at"}"><td><b>${esc(x.usina)}</b></td><td>${esc(x.fonte.replace("BD_", ""))}</td><td>${esc(curto(x.inversor))}</td>` +
      `<td>${x.n}</td><td>${x.comparados}</td><td><span class="fz-b ${bpCls(x.pior)}">${pct(x.pior)}</span></td><td><span class="fz-b ${bpCls(x.media)}">${pct(x.media)}</span></td>` +
      `<td title="${esc(bpTip(x))}">${esc(bpDias(x))}</td><td class="fz-portal">${bpPortal(x)}</td><td><small class="f">${esc(x.base)}</small></td></tr>`).join("") ||
      '<tr><td colspan="10" class="fz-vazio">Nenhum inversor abaixo de 70% para os filtros.</td></tr>';
    const us = new Set(L.map(x => x.usina)).size;
    $f("fzKpis").innerHTML = [["Inversores ≤ 70%", L.length, L.length ? "sv" : ""], ["Usinas", us, ""], ["Com 5 dias ou mais", L.filter(x => x.n >= 5).length, ""],
      ["Abaixo de 50% (pior dia)", L.filter(x => x.pior <= 0.5).length, L.some(x => x.pior <= 0.5) ? "sv" : ""]]
      .map(([a, b, c]) => `<div class="kpi"><div class="n ${c}">${b}</div><div class="t">${a}</div></div>`).join("");
    $f("fzLegend").innerHTML = '<span class="f">Cada inversor com geração no dia contra a MÉDIA DOS DEMAIS inversores da mesma usina no mesmo dia (= 100%), em kWh/kWp quando a aba Equipamentos tem a potência de todos (senão em kWh). Fica quem fez 70% ou menos, com pelo menos 2 outros gerando. Zerado/vazio não entra (é furo, nas outras abas). Período: ' +
      esc(m.ini.slice(8, 10) + "/" + m.ini.slice(5, 7)) + " a " + esc(m.fim.slice(8, 10) + "/" + m.fim.slice(5, 7)) + '. Passe o mouse em "Dias" para ver o % de cada dia.</span>';
    $f("fzContagem").textContent = L.length + " inversor(es) em " + us + " usina(s)";
  }
  function bpTsv() {
    const L = [["Usina", "Fonte", "Inversor", "Dias <= 70%", "Dias comparados", "Pior dia", "Média nos dias baixos", "Dias", "Onde buscar no portal", "Base"]];
    bpLinhas().forEach(x => L.push([x.usina, x.fonte, x.inversor, x.n, x.comparados, pct(x.pior), pct(x.media), bpTip(x),
      bpPortal(x).replace(/<[^>]+>/g, ""), x.base]));
    return L;
  }

  let rondaT = null;
  function salvarRonda() { clearTimeout(rondaT); rondaT = setTimeout(() => { try { api().furos_gravar_ronda(RONDA); } catch (e) {} }, 300); }

  const motOpts = (ap, sel) => '<option value="">— pendente de confirmação —</option>' + MOT.filter(x => x.ap === "both" || x.ap === ap).map(x => `<option value="${x.k}" ${sel === x.k ? "selected" : ""}>${x.l}</option>`).join("");
  function panel(p, m) {
    const id = esc(rid(p));
    let h = `<div class="fz-tools"><b>${esc(p.usina)}</b><span class="f">${esc(p.cliente)}${p.supervisor ? " · Supervisor: " + esc(p.supervisor) : ""}</span>
      <span style="flex:1"></span>
      <button class="btn2 fz-sm" data-a="sug" data-id="${id}">Aceitar sugestões automáticas</button>
      <select class="fz-ctl" data-a="bulkmot" data-id="${id}">${motOpts("both", "")}</select>
      <select class="fz-ctl" data-a="bulkvig" data-id="${id}"><option value="m">só este mês</option><option value="*">todos os meses</option></select>
      <button class="btn fz-sm" data-a="bulk" data-id="${id}">Aplicar a todos os pendentes</button>
      <button class="btn2 fz-sm" data-a="clear" data-id="${id}">Limpar confirmações</button></div>`;
    h += osBox(p);
    if (!m.items.length) return h + '<p class="f">Nenhum item com falha neste critério.</p>' + heat(p, m);
    h += '<table class="fz-it"><thead><tr><th>Item</th><th>Dias</th><th>Datas</th><th>Sugestão automática</th><th>Confirmar ausência como OK?</th><th>Vigência</th><th>Observação</th></tr></thead><tbody>';
    m.items.forEach(t => {
      const s = suggest(p, t), c = t.conf, ap = apOf(t.tipo), n = esc(t.nome);
      h += `<tr><td class="fz-item"><b>${n}</b></td><td>${t.idx.length}</td><td class="fz-datas">${ranges(t.idx, p.days)}</td>
        <td class="fz-sug">${s ? "<b>Sugestão:</b> " + MOTL[s[0]] + "<br><small>" + esc(s[1]) + "</small>" : '<small class="f">—</small>'}</td>
        <td><select class="fz-ctl" data-a="mot" data-id="${id}" data-n="${n}">${motOpts(ap, c ? c.r : "")}</select></td>
        <td><select class="fz-ctl" data-a="vig" data-id="${id}" data-n="${n}" ${c ? "" : "disabled"}><option value="m" ${c && c.v !== "*" ? "selected" : ""}>só este mês</option><option value="*" ${c && c.v === "*" ? "selected" : ""}>todos os meses</option></select></td>
        <td><input class="fz-ctl" type="text" data-a="obs" data-id="${id}" data-n="${n}" value="${c ? esc(c.o || "") : ""}" placeholder="ex.: inversor desinstalado, sem sensor…" ${c ? "" : "disabled"}></td></tr>`;
    });
    return h + "</tbody></table>" + heat(p, m);
  }
  function osBox(p) {
    if (!p.os || !p.os.length) return "";
    const cnt = p.os.map(() => 0); p.eqs.forEach(e => { if (e.cv) Object.values(e.cv).forEach(v => v.forEach(j => cnt[j]++)); });
    return `<details class="fz-os" ${$f("fzOS").checked ? "open" : ""}><summary><b>OS, tickets e paradas do COS registrados nesta usina (${p.os.length})</b> — cobertura = ≥6h na janela solar (06–18h) no dia; "sem OS" = parada registrada no COS sem número de OS (ponto de atenção)</summary>` +
      '<table class="fz-it"><thead><tr><th>Fonte</th><th>OS</th><th>Equipamento</th><th>Classificação</th><th>Início</th><th>Fim</th><th>Células cobertas</th></tr></thead><tbody>' +
      p.os.map((o, j) => `<tr><td>${({T: "Ticket", F: "Fracttal", C: "COS (normalização)", "F+T": "Fracttal + ticket"})[o[0]] || esc(o[0])}</td><td>${o[6] === "A" ? '<span class="fz-b fz-b-at">sem OS</span>' : esc(o[1])}</td><td>${esc(o[2])}</td><td>${esc(o[3])}</td><td>${esc(o[4])}</td><td>${esc(o[5])}</td><td>${cnt[j]}</td></tr>`).join("") + "</tbody></table></details>";
  }
  function heat(p, m) {
    const sa = SHOWALL.has(rid(p)), z = $f("fzZero").checked, days = p.days;
    const byN = {}; m.items.forEach(t => byN[t.nome] = t);
    const eqs = p.eqs.filter(e => sa || byN[e.nome] || e.st.includes("e") || (m.ufv && isGen(e))); const Dset = new Set(m.ufv ? m.ufv.idx : []);
    let h = `<div class="fz-tools"><button class="btn2 fz-sm" data-a="all" data-id="${esc(rid(p))}">${sa ? "Mostrar só equipamentos com falha" : "Mostrar todos os equipamentos (" + p.eqs.length + ")"}</button></div>`;
    if (!eqs.length) return h;
    h += '<div class="fz-rol"><table class="fz-hm"><tr><th></th>' + days.map(d => `<th>${d}</th>`).join("") + "</tr>";
    if (m.ufv) h += `<tr><td class="l"><b>${UFVN}</b>${m.ufv.ok ? ' <span class="fz-okt">OK</span>' : ""}</td>` + days.map((d, i) => `<td class="c s-${Dset.has(i) ? (m.ufv.ok ? (m.ufv.conf.r === "fora_op" ? "i" : "c") : "v") : "o"}" title="${Dset.has(i) ? "Furo de coleta da UFV toda (todos os inversores) · " + fmtD(d) : "sem furo da UFV toda · " + fmtD(d)}"></td>`).join("") + "</tr>";
    eqs.forEach(e => {
      const t = byN[e.nome], bs = e.nome === "IPOA" ? (z ? "vxdza" : "vxda") : (z ? "vxza" : "vxa"), conf = t && t.ok;
      h += `<tr><td class="l">${esc(e.nome)}${conf ? ' <span class="fz-okt">OK</span>' : ""}</td>` + [...e.st].map((c, i) => {
        const u = (m.ufv && Dset.has(i) && isGen(e)) ? m.ufv : null;
        const cc = u ? (u.ok ? (u.conf.r === "fora_op" ? "i" : "c") : c) : ((conf && bs.includes(c)) ? (t.conf.r === "fora_op" ? "i" : "c") : c);
        const nome = c === "e" ? "ausência ESPERADA – " + osTxt(p, e, i) : ESTADO[c];
        return `<td class="c s-${cc}" title="${esc(e.nome)} · ${fmtD(days[i])} · ${esc(nome)}${(u ? u.ok : conf && bs.includes(c)) ? " (confirmado OK)" : ""}${u ? " · furo de coleta da UFV toda" : ""}"></td>`;
      }).join("") + "</tr>";
    });
    return h + "</table></div>";
  }
  const LEG_DET = [["o", "Coletado"], ["v", "Vazio"], ["x", "Linha ausente"], ["z", "Zerado"], ["d", "IPOA só DEF (estimado)"], ["c", "Ausência confirmada OK"],
                   ["i", "Equipamento inoperante (OK, sinalizado)"], ["p", "Usina sem geração"], ["a", "Valor anômalo (muito acima do padrão)"],
                   ["w", "Pendente (último dia)"], ["e", "Ausência esperada – OS/ticket de desligamento"]];
  function render() {
    if (!DB) return;
    const all = rowsAll(), cs = {};
    all.forEach(({p, m}) => { const c = cs[p.cliente] = cs[p.cliente] || {n: 0, f: 0}; c.n++; if (m.sit === "falha") c.f++; });
    $f("fzClients").innerHTML = `<button class="fz-chip ${cliSel === "" ? "on" : ""}" data-c="">Todos <i>${all.filter(x => x.m.sit === "falha").length}</i>/${all.length}</button>` +
      Object.keys(cs).sort().map(k => `<button class="fz-chip ${cliSel === k ? "on" : ""}" data-c="${esc(k)}">${esc(k)} <i>${cs[k].f}</i>/${cs[k].n}</button>`).join("");
    $f("fzClients").querySelectorAll(".fz-chip").forEach(e => e.onclick = () => { cliSel = e.dataset.c; [...$f("fzCli").options].forEach(o => { o.selected = !!cliSel && o.value === cliSel; }); render(); });
    const rows = filtered(), n = k => rows.filter(r => r.m.sit === k).length;
    const cT = rows.reduce((a, r) => a + r.m.cellT, 0), cP = rows.reduce((a, r) => a + r.m.cp, 0);
    const emU = f => "em " + rows.filter(f).length + " usina(s)";
    // 4 números na frente (13/11/2026: "muita informação"); o resto está no Resumo e no Detalhe
    const K = [["Usinas com falha", n("falha"), n("falha") ? "sv" : "", "de " + rows.length],
      ["Inversores com furo", rows.reduce((a, r) => a + r.m.invF, 0), "", emU(r => r.m.invF)],
      ["Usinas sem IPOA ou GHI", rows.filter(r => r.m.ipF || r.m.ghF).length, ""],
      ["Completude", cT ? ((1 - cP / cT) * 100).toFixed(1) + "%" : "—", ""]];
    $f("fzKpis").innerHTML = K.map(([a, b, c, d]) => `<div class="kpi"><div class="n ${c}">${b}</div><div class="t">${a}${d ? '<br><span class="f">' + d + '</span>' : ''}</div></div>`).join("");
    $f("fzLegend").innerHTML = TAB === "col"
      ? '<span class="f">Só as usinas com falta pendente dos tipos marcados em "Falta". Onde buscar = planta e equipamento no supervisório (aba Equipamentos do BD_Performance, o mesmo de-para da coleta); "sem de-para no cadastro" é inversor que a coleta não consegue preencher. Ronda fica salva neste computador.</span>'
      : TAB === "det"
      ? LEG_DET.map(([c, l]) => `<span><i class="s-${c}"></i>${l}</span>`).join("")
      : '<span><i class="lg-at"></i>Falha pendente</span><span><i class="lg-cr"></i>Falha crítica (≥50% das células ou sem coleta)</span><span><i class="lg-cf"></i>Confirmado OK</span><span><i class="lg-in"></i>Equipamento inoperante (conta como OK, fica sinalizado)</span><span><i class="s-e"></i>Células esperadas por OS/ticket (fora da falha)</span><span class="f">Linhas esmaecidas = sem falha. Clique na linha para revisar e confirmar.</span>';
    CFO[TAB] = {}; CATS.forEach(k => CFO[TAB][k] = [...new Set(rows.map(r => String(colVal(k, r))))].sort());
    $f("fzCopiar").hidden = TAB !== "col" && TAB !== "bp";
    $f("fzBpMin").parentElement.hidden = TAB !== "bp";
    $f("fzFaltaBox").hidden = TAB !== "col";
    $f("fzTb").classList.toggle("sem-cf", !$f("fzColF").checked || TAB === "bp");
    const nm = ["fzCli", "fzCart", "fzSt", "fzSit"].filter(i => $f(i).value).length;
    $f("fzMaisN").textContent = nm ? "(" + nm + " ligado" + (nm > 1 ? "s" : "") + ")" : "";
    if (TAB === "bp") { renderBp(); return; }
    const rr = applyCol(TAB === "col" ? linhasCol(rows) : rows, TAB);
    TAB === "res" ? renderRes(rr) : TAB === "det" ? renderDet(rr) : renderCol(rr);
    // filtro ativo fica com a borda verde; o botão diz quantos estão ligados
    FILTROS.forEach(i => $f(i).classList.toggle("on", !!$f(i).value));
    const na = ativos();
    $f("fzLimpar").textContent = na ? "Limpar filtros (" + na + ")" : "Limpar filtros";
    $f("fzLimpar").disabled = !na;
    $f("fzLimpar").hidden = !na;
    $f("fzContagem").textContent = rr.length + " de " + all.length + " usinas";
    if (window.coletasFiltros) window.coletasFiltros.atualizar();     // Nexus: a barra no modelo do Histórico de OS
    const nc = Object.keys(CONF).length, ne = Object.keys(REL.conf_arquivo || {}).length;
    const nr = Object.keys(RONDA).filter(k => k.startsWith(MONTH + "|")).length;
    if (TAB === "col") $f("fzContagem").textContent = rr.length + " usina(s) com falta · ronda feita em " + nr;
    $f("fzNconf").textContent = "Confirmações: " + nc + (ne ? " (do relatório: " + ne + ")" : "");
  }

  // ---------------------------------------------------------------- eventos
  const byId = id => P().find(p => rid(p) === id);
  function onClick(e) {
    const b = e.target.closest("button[data-a]");
    if (b) {
      e.stopPropagation(); const p = byId(b.dataset.id), a = b.dataset.a; if (!p) return; const m = calc(p);
      if (a === "all") { SHOWALL.has(b.dataset.id) ? SHOWALL.delete(b.dataset.id) : SHOWALL.add(b.dataset.id); }
      else if (a === "sug") { m.pend.forEach(t => { const s = suggest(p, t); if (s) setConf(p, t.nome, s[0], (s[0] === "sem_ipoa" || s[0] === "sem_ghi") ? "*" : "m", s[1]); }); }
      else if (a === "clear") { m.items.forEach(t => setConf(p, t.nome, "")); }
      else if (a === "bulk") {
        const tr = b.closest("div"), mot = tr.querySelector("[data-a=bulkmot]").value, vig = tr.querySelector("[data-a=bulkvig]").value;
        if (mot) { const mo = MOT.find(x => x.k === mot); m.pend.forEach(t => { const ap = apOf(t.tipo); if (mo.ap === "both" || mo.ap === ap) setConf(p, t.nome, mot, vig); }); }
      }
      render(); return;
    }
    if (e.target.closest("select,input,button,summary,details")) return;
    const tr = e.target.closest("tr.pl"); if (!tr) return;
    const S = OPEN[TAB], id = tr.dataset.id; S.has(id) ? S.delete(id) : S.add(id); render();
  }
  function onChange(e) {
    const t = e.target, a = t.dataset.a; if (!a || a.startsWith("bulk")) return; const p = byId(t.dataset.id); if (!p) return;
    const n = t.dataset.n, tr = t.closest("tr");
    if (a === "ronda") { const k = rkey(p); if (t.checked) RONDA[k] = new Date().toLocaleString("pt-BR", {dateStyle: "short", timeStyle: "short"}); else delete RONDA[k]; salvarRonda(); render(); return; }
    if (a === "mot") { const vig = tr.querySelector("[data-a=vig]").value; setConf(p, n, t.value, vig); render(); }
    else if (a === "vig") { const c = getConf(p, n); if (c) { setConf(p, n, c.r, t.value); render(); } }
    else if (a === "obs") { const c = getConf(p, n); if (c) { CONF[ckey(p, n)].o = t.value; save(); } }
  }
  async function salvar(nome, texto) {
    const p = await api().furos_salvar(nome, texto);
    toast("Baixado: " + p.split("\\").pop()); api().mostrar_pasta(p);
  }
  function csv() {
    if (TAB === "col" || TAB === "bp") {
      const L = TAB === "bp" ? bpTsv() : listaTsv();
      salvar((TAB === "bp" ? "baixa_performance_" : "para_coletar_") + MONTH + ".csv", "\ufeff" + L.map(r => r.map(x => '"' + String(x).replace(/"/g, '""') + '"').join(";")).join("\n"));
      return;
    }
    const L = [["Mês", "Cliente", "Carteira", "Usina", "Fonte", "Status usina", "Item", "Tipo", "Dias com furo", "Datas", "Situação", "Motivo da confirmação", "Vigência", "Observação"]];
    applyCol(filtered(), TAB).forEach(({p, m}) => m.items.forEach(t => {
      const c = t.conf;
      L.push([MONTH, p.cliente, p.carteira, p.usina, p.src, p.status || "", t.nome, t.tipo, t.idx.length, ranges(t.idx, p.days), t.ok ? "Confirmado OK" : "Pendente",
              c ? MOTL[c.r] || c.r : "", c ? (c.v === "*" ? "todos os meses" : "só " + c.v) : "", c ? (c.o || "") : ""]);
    }));
    salvar("furos_coleta_" + MONTH + ".csv", "﻿" + L.map(r => r.map(x => '"' + String(x).replace(/"/g, '""') + '"').join(";")).join("\n"));
  }
  const expConf = () => salvar("confirmacoes_furos.json", JSON.stringify({versao: 1, exportado: new Date().toISOString(), conf: CONF}, null, 1));
  async function impConf() {
    const j = await api().furos_importar(); if (!j) return;
    Object.assign(CONF, j); save(); render(); toast("Confirmações importadas: " + Object.keys(j).length);
  }
  async function saveHtml() {
    const p = await api().furos_salvar_html(REL.caminho, CONF);
    toast("Baixado: " + p.split("\\").pop()); api().mostrar_pasta(p);
  }

  // ---------------------------------------------------------------- carga
  function aplicar(r) {
    if (!r) return;
    $f("fzErro").hidden = !r.erro; $f("fzCorpo").hidden = !!r.erro;
    if (r.erro) { $f("fzErro").innerHTML = esc(r.erro); $f("fzOrigem").textContent = ""; return; }
    REL = r; DB = r.db; MKEYS = Object.keys(DB.months).sort();
    MKEYS.forEach(k => DB.months[k].plants.forEach(p => { p.eqs = [...p.eqs.filter(e => !isGen(e)), ...p.eqs.filter(isGen).sort(cmpN)]; }));
    // confirmações: as do relatório + as desta pessoa; a mais recente vence (como o localStorage do HTML original)
    RONDA = Object.assign({}, r.ronda || {});
    try { Promise.resolve(api().furos_portal()).then(x => { PORTAL = x || {}; render(); }); } catch (e) {}
    CONF = Object.assign({}, r.conf_arquivo || {});
    Object.entries(r.conf || {}).forEach(([k, v]) => { const a = CONF[k]; if (!a || (v.t || "") >= (a.t || "")) CONF[k] = v; });
    if (!MKEYS.includes(MONTH)) MONTH = MKEYS[MKEYS.length - 1];
    OPEN.res.clear(); OPEN.det.clear(); SHOWALL.clear();
    $f("fzMes").innerHTML = MKEYS.map(k => `<option value="${k}">${mlabel(k)}</option>`).join(""); $f("fzMes").value = MONTH;
    const dm = new Date(r.modificado * 1000);
    $f("fzOrigem").textContent = r.nome + " · gerado em " + (r.gerado || "?") + " · arquivo de " + dm.toLocaleString("pt-BR", {dateStyle: "short", timeStyle: "short"});
    $f("fzOrigem").title = r.caminho;
    applyOS(); fillFilters(); subtitulo(); render();
  }
  function subtitulo() {
    $f("fzSub").textContent = "Período: 01/" + MONTH.split("-")[1] + " a " + fmtD(M().end) + "/" + MONTH.split("-")[0] + " · " + P().length + " usinas com linhas no mês";
  }
  let carregado = false;
  async function abrirTela() {
    if (carregado) return;
    carregado = true;
    $f("fzErro").hidden = false; $f("fzErro").textContent = "Lendo o relatório de furos…"; $f("fzCorpo").hidden = true;
    aplicar(await api().furos_carregar());
  }
  function iniciar() {
    $f("fzMes").onchange = () => { MONTH = $f("fzMes").value; OPEN.res.clear(); OPEN.det.clear(); SHOWALL.clear(); fillFilters(); subtitulo(); render(); };
    $f("fzCopiar").onclick = copiarLista;
    ["fzCli", "fzCart", "fzSrc", "fzSt", "fzSit", "fzZero", "fzConf", "fzOS", "fzFInv", "fzFIpoa", "fzFGhi", "fzBpMin", "fzColF"].forEach(i => $f(i).onchange = () => {
      if (i === "fzOS") applyOS(); if (i === "fzCli") { const v = vs("fzCli"); cliSel = v.length === 1 ? v[0] : ""; } render();
    });
    $f("fzQ").oninput = render;
    $f("fzLimpar").onclick = limparFiltros;
    const onCol = e => {
      const el = e.target.closest("[data-cf]"); if (!el) return;
      COLF[TAB][el.dataset.cf] = el.value; const k = el.dataset.cf, isIn = el.tagName === "INPUT"; render();
      if (isIn) { const nn = document.querySelector('#fzTb [data-cf="' + k + '"]'); if (nn) { nn.focus(); nn.setSelectionRange(nn.value.length, nn.value.length); } }
    };
    $f("fzTb").tHead.addEventListener("input", onCol);
    $f("fzTb").tHead.addEventListener("change", e => { if (e.target.tagName === "SELECT") onCol(e); });
    $f("fzCsv").onclick = csv; $f("fzExp").onclick = expConf; $f("fzImp").onclick = impConf; $f("fzHtml").onclick = saveHtml;
    document.querySelector(".fz-menu-c").addEventListener("click", e => { if (e.target.closest("button")) e.currentTarget.closest("details").open = false; });
    $f("fzAbrir").onclick = async () => aplicar(await api().furos_abrir());
    $f("fzNovo").onclick = async () => aplicar(await api().furos_mais_novo());
    document.querySelectorAll(".fz-tab").forEach(t => t.onclick = () => {
      TAB = t.dataset.t; document.querySelectorAll(".fz-tab").forEach(x => x.classList.toggle("on", x === t)); render();
    });
    $f("fzTb").addEventListener("click", onClick); $f("fzTb").addEventListener("change", onChange);
  }
  return {iniciar, abrirTela, recarregar: async () => { carregado = true; aplicar(await api().furos_carregar()); }};
})();

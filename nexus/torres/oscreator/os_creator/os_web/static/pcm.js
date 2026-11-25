// os_creator/os_web/static/pcm.js — a PcmTab do app (steps/pcm.py), no navegador: o card PCM, "PCM — OS por plano de
// tarefas". Mesma lógica: cascata Cliente → Usina → Tipo + busca (_on_cli/_on_usi/_refresh); a marcação sobrevive a
// filtro e a troca de usina (o `_checked`); "Carregar planos" (get_plans_for_assets + as contagens); a família do plano
// reordena a tabela com plano no topo; cada linha mostra o plano da família (o "[Grid Co.]" de saída), as subtarefas, a
// data/hora e o TEMPO (seta de 30 em 30 min); a programação em massa; "Sem plano de tarefas"; observação, Requerido
// por e OS pai; e a confirmação antes de criar UMA OS com cada LINHA como tarefa (o ativo com dois planos do mesmo tipo,
// o Diurno e o Noturno, vira duas linhas desde 25/11/2026: `grupoDoAtivo`). Aviso fica na página, nunca em janela.
(function () {
  'use strict';
  const cmp = (x, y) => (x < y ? -1 : (x > y ? 1 : 0));    // a ordem do Python (ponto de código), não a do idioma

  // Os planos de UM ativo na tela, já filtrados por família, tipo de plano e turno → {ps, gi, grupo}: `ps` por nome (o
  // combo), `gi` o de saída (o primeiro com "grid" no nome, o [Grid Co.]; senão o primeiro: pcm_web.plano_padrao) e
  // `grupo`, as TAREFAS do ativo, uma linha cada (25/11/2026, Levi, pelo chat do PCM: "Em MPA tem algumas tarefas que são 2
  // tarefas para o mesmo ativo [...] quando tiver mais de uma tarefa no mesmo ativo, ele duplica aquele ativo e aí só muda
  // a nomenclatura da tarefa"). O grupo é o de saída e os outros do MESMO tipo e da MESMA família dele: o Inversor (Diurno)
  // e o (Noturno) do [Grid Co.] são duas tarefas; o [Axis] do mesmo ativo é outra opção do combo, não uma 3ª tarefa.
  function grupoDoAtivo(planos) {
    const ps = (planos || []).slice().sort((x, y) => cmp(String(x.description || '').toLowerCase(), String(y.description || '').toLowerCase()));
    let gi = ps.findIndex((p) => String(p.description || '').toLowerCase().includes('grid'));
    if (gi < 0) gi = 0;
    const base = ps[gi];
    const grupo = !base ? [] : [base].concat(ps.filter((p, i) => i !== gi && p.family === base.family && p.tipo === base.tipo));
    return {ps: ps, gi: gi, grupo: grupo};
  }
  globalThis.OsPcmTarefas = {grupoDoAtivo: grupoDoAtivo};  // as contas, para o teste no node
  if (typeof document === 'undefined') return;

  const root = document.getElementById('pcm');
  if (!root) return;
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const enc = encodeURIComponent;
  const apiErro = (j, r) => (j && j.erro) ? (j.login ? j.erro + ' Entre de novo em /os/login.' : j.erro) : ('HTTP ' + r.status);
  const p2 = (n) => (n < 10 ? '0' : '') + n;
  const HOJE = root.dataset.hoje;
  const SEL = '— selecione —';                                // steps/pcm.py::_SEL
  const DUR_PADRAO = 900;                                     // api.duracao_do_plano(padrao=900): 15 min até ler o plano
  const DICA_TEMPO = 'Quanto a tarefa deve durar. Vem do plano; edite se esta for diferente. A seta anda de 30 em 30 minutos.';
  const SVG_CIMA = '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m18 15-6-6-6 6"/></svg>';
  const SVG_BAIXO = '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';

  const cbCli = $('cb_cli'), cbUsi = $('cb_usi'), cbTipo = $('cb_tipo'), busca = $('busca');
  const ckSem = $('ck_sem_plano'), descLbl = $('desc_lbl'), edDesc = $('ed_desc');
  const famLbl = $('fam_lbl'), cbFam = $('cb_familia'), bPlanos = $('b_planos'), avisoPlanos = $('aviso_planos');
  const cbTipoP = $('cb_tipo_plano'), tipoPLbl = $('tipo_plano_lbl'), cbTurno = $('cb_turno'), turnoLbl = $('turno_lbl');
  const bComPlano = $('b_complano'), bAll = $('b_all'), bNone = $('b_none'), tbody = $('tbody'), selLbl = $('sel_lbl');
  const bulkDate = $('bulk_date'), obs = $('obs'), cbResp = $('cb_resp'), bResp = $('b_resp');
  const ospaiIn = $('ospai_in'), ospaiLista = $('ospai_lista'), btn = $('btn_criar'), hint = $('hint'), res = $('resultado');

  // ── o estado, com os nomes do PcmTab.__init__ ──
  let ativos = [];                    // os ativos da usina (o `_assets` já filtrado por cliente/usina e pela regra do tracker)
  let linhas = [];                    // as linhas da tabela, na ordem da tela — é o que o `_criar` percorre
  const checked = new Set();          // _checked: ids marcados; sobrevivem a filtro, a troca de usina e a Limpar fora da tabela
  let planosByAsset = {};             // _planos_by_asset: id do ativo -> [planos] (do último Carregar)
  let loadedFor = new Set();          // _loaded_for: os ativos cujos planos já foram carregados
  const subt = {};                    // _subt: id_task -> nº de subtarefas (cache da tela)
  const durPlano = {};                // id_task -> segundos: a duração do plano, que chega junto da contagem
  // a data e o tempo são POR LINHA (desde 25/11/2026, as duas tarefas do mesmo ativo): a chave é o id do ativo na 1ª linha
  // dele e "id|n" na n-ésima tarefa (`chave`), e a 1ª segue como era
  const dtByAsset = {};               // _dt_by_asset: a data de cada linha sobrevive à troca de família
  const durByAsset = {};              // _dur_by_asset: só o tempo que a PESSOA mexeu; ausente = vale o do plano
  const extraOff = new Set();         // as 2ª, 3ª... tarefas que a pessoa desmarcou ("id|n"); de saída vão todas
  const chave = (aid, slot) => (slot ? aid + '|' + slot : aid);
  const chaveDe = (tr) => chave(Number(tr.dataset.id), Number(tr.dataset.slot || 0));
  let semPlano = false;               // _sem_plano
  let pessoas = [];                   // a lista do "Requerido por"
  let ultimaData = bulkDate.value || HOJE;

  // o pedido que a PESSOA disparou: com o círculo de carga (carga.js)
  async function pedir(url, opcoes, texto) {
    const r = await OsCarga.buscar(url, Object.assign({credentials: 'same-origin'}, opcoes || {}), texto || 'Carregando…');
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(apiErro(j, r));
    return j;
  }

  // ── cascata (_cli / _usi / _on_cli / _on_usi) ──
  // o cliente vai no `value` da opção (o texto cru, o `currentText()` do app): sem o atributo, o navegador colapsa o
  // espaço duplo do nome (tests/test_os_web_option_value.py, 22/09)
  const cli = () => (cbCli.selectedIndex > 0 ? cbCli.options[cbCli.selectedIndex].value : null);
  const usi = () => (cbUsi.selectedIndex > 0 ? cbUsi.options[cbUsi.selectedIndex].value : null);
  const tipo = () => (cbTipo.selectedIndex > 0 ? cbTipo.options[cbTipo.selectedIndex].value : null);
  const fam = () => cbFam.value || null;                     // _fam: "(carregue os planos)" e "(todas)" = qualquer família
  const opcao = (v) => '<option value="' + esc(v) + '">' + esc(v) + '</option>';
  let seqCli = 0, seqUsi = 0;                                // a resposta velha (cliente trocado no meio) não pinta a tela

  async function onCli() {
    const c = cli(), meu = ++seqCli;
    cbUsi.innerHTML = '<option value="">— Selecione a usina —</option>'; cbUsi.disabled = true;
    if (c) {
      try {
        const us = (await pedir('/os/api/pcm/usinas?cliente=' + enc(c), null, 'Carregando as usinas…')).usinas || [];
        if (meu !== seqCli) return;
        cbUsi.innerHTML += us.map(opcao).join('');
        cbUsi.disabled = !us.length;
      } catch (e) { if (meu === seqCli) hint.textContent = '⚠ ' + e.message; }
    }
    if (meu === seqCli) await onUsi();
  }

  async function onUsi() {
    const c = cli(), u = usi(), meu = ++seqUsi;
    cbTipo.innerHTML = '<option value="">Todos os tipos</option>'; cbTipo.disabled = true;
    ativos = [];
    if (u) {
      try {
        const j = await pedir('/os/api/pcm/ativos?cliente=' + enc(c || '') + '&usina=' + enc(u), null, 'Carregando os ativos…');
        if (meu !== seqUsi) return;
        const ts = j.tipos || [];
        cbTipo.innerHTML += ts.map(opcao).join('');
        cbTipo.disabled = !ts.length;
        ativos = j.ativos || [];
      } catch (e) { if (meu === seqUsi) hint.textContent = '⚠ ' + e.message; }
    }
    if (meu === seqUsi) refresh();
  }

  // ── a tabela (_has_plan / _refresh / _fill_row / _fill_planos) ──
  // o tipo de plano e o turno (19/11/2026, sugestão do PCM) filtram junto com a família; "(todos)" = qualquer um
  const planosDe = (aid, f) => {
    const tp = cbTipoP.value || null, tu = cbTurno.value || null;
    return (planosByAsset[aid] || []).filter((p) => (f == null || p.family === f) && (tp == null || p.tipo === tp) && (tu == null || p.turno === tu));
  };
  const comFiltro = () => !!(cbTipoP.value || cbTurno.value);   // a linha sem plano diz se foi a família ou o filtro
  function temPlano(aid, f) {                                // _has_plan: só conta o ativo já carregado
    return aid != null && loadedFor.has(aid) && planosDe(aid, f).length > 0;
  }
  const linhaDe = (aid) => tbody.querySelector('tr[data-id="' + aid + '"]:not([data-slot])');   // a 1ª linha do ativo
  const extrasDe = (aid) => tbody.querySelectorAll('tr[data-id="' + aid + '"][data-slot]');      // as das outras tarefas
  const dim = (t) => '<span class="pcm-dim">' + esc(t) + '</span>';

  function refresh() {                                       // _refresh: filtra, ordena e redesenha tudo
    const u = usi(), t = tipo(), txt = (busca.value || '').trim().toLowerCase(), f = fam();
    linhas = !u ? [] : ativos.filter((a) => a.tipo && (!t || a.tipo === t) && (!txt || String(a.label || '').toLowerCase().includes(txt)));
    // COM plano (na família atual) no topo, SEM plano embaixo; cada bloco por nome
    linhas.sort((a, b) => ((temPlano(a.id, f) ? 0 : 1) - (temPlano(b.id, f) ? 0 : 1))
      || cmp(String(a.label || a.code || '').toLowerCase(), String(b.label || b.code || '').toLowerCase()));
    fillPlanos();
  }

  function fillPlanos() {                                    // _fill_planos: todas as linhas, na ordem que já estão
    tbody.innerHTML = linhas.length ? linhas.map(linhaHtml).join('')
      : '<tr class="vazio"><td colspan="5">' + (usi() ? 'Nenhum ativo nesta seleção.' : 'Selecione cliente e usina para ver os ativos.') + '</td></tr>';
    fetchCounts();
    updLabel();
  }

  // o ativo e, logo abaixo, uma linha para cada outra tarefa dele (grupoDoAtivo); todas as linhas do ativo que tem mais de
  // uma tarefa ficam de fundo laranja claro (Levi, 25/11/2026: "Tem 2 inversor no ponto 2, então vai pintar os dois")
  function linhaHtml(a) {
    return [0].concat(slotsExtras(a.id)).map((s) => trHtml(a, s)).join('');
  }
  // as linhas das outras tarefas: só do ativo marcado, com os planos carregados e fora do "Sem plano de tarefas"
  function slotsExtras(aid) {
    if (semPlano || !checked.has(aid) || !loadedFor.has(aid)) return [];
    const n = grupoDoAtivo(planosDe(aid, fam())).grupo.length;
    return Array.from({length: Math.max(0, n - 1)}, (_, i) => i + 1);
  }
  function trHtml(a, slot) {
    const c = celulas(a, slot), marcada = slot ? !extraOff.has(chave(a.id, slot)) : checked.has(a.id);
    const cls = (c.sem ? 'sem' : '') + (slot || slotsExtras(a.id).length ? ' dupla' : '');
    return '<tr data-id="' + esc(a.id) + '"' + (slot ? ' data-slot="' + slot + '" title="Outra tarefa do mesmo ativo (outro plano)"' : '')
      + (cls.trim() ? ' class="' + cls.trim() + '"' : '') + '><td class="c-ativo"><label class="pcm-chk">'
      + '<input type="checkbox" class="chk"' + (marcada ? ' checked' : '') + '><span>' + esc(a.label || a.code || '?') + '</span></label></td>'
      + '<td class="c-plano">' + c.c1 + '</td><td class="c-subt">' + c.c2 + '</td><td class="c-dt">' + c.c3 + '</td><td class="c-tempo">' + c.c4 + '</td></tr>';
  }

  // _fill_row de UM ativo (o check da pessoa não é redesenhado): a 1ª linha e, de novo, as das outras tarefas dele
  function fillRow(aid) {
    const tr = linhaDe(aid), a = linhas.find((x) => x.id === aid);
    if (!tr || !a) return;
    extrasDe(aid).forEach((x) => x.remove());
    const c = celulas(a, 0), td = tr.children, slots = slotsExtras(aid);
    tr.classList.toggle('sem', !!c.sem);
    tr.classList.toggle('dupla', slots.length > 0);         // a 1ª linha também, enquanto o ativo tem mais de uma tarefa
    td[1].innerHTML = c.c1; td[2].innerHTML = c.c2; td[3].innerHTML = c.c3; td[4].innerHTML = c.c4;
    const extras = slots.map((s) => trHtml(a, s)).join('');
    if (extras) tr.insertAdjacentHTML('afterend', extras);
  }

  // Plano (combo) + nº de subtarefas + data + tempo de UMA linha, conforme o modo, a família e se o ativo está marcado;
  // `slot` > 0 é a linha da outra tarefa do ativo, que abre no plano dela e se desmarca sozinha
  function celulas(a, slot) {
    const aid = a.id, k = chave(aid, slot);
    if (!checked.has(aid)) return {c1: dim('—'), c2: '', c3: dim('—'), c4: ''};
    if (semPlano) {                                          // ativo marcado = tarefa com a subtarefa 'Procedimento'
      return {c1: '<span class="pcm-dim pcm-pre">' + esc('Procedimento  (sem plano de tarefas)') + '</span>', c2: '1', c3: dataHtml(aid), c4: ''};
    }
    if (!loadedFor.has(aid)) return {c1: dim('clique em “Carregar planos”'), c2: '', c3: dim('—'), c4: ''};
    const g = grupoDoAtivo(planosDe(aid, fam())), ps = g.ps;
    if (!ps.length) return {sem: true, c1: esc(comFiltro() ? '— sem plano neste filtro —' : '— sem plano nesta família —'), c2: '—', c3: '—', c4: ''};
    // a 1ª linha abre no plano de saída (o [Grid Co.]); a da outra tarefa, no plano dela
    const plano = g.grupo[slot] || g.grupo[0];
    if (slot && extraOff.has(k)) return {c1: dim(plano.description || '?'), c2: '', c3: dim('—'), c4: ''};
    const c1 = '<select class="plano" data-osb="nativo">' + ps.map((p) => '<option value="' + esc(p.id_task) + '"'
      + (p === plano ? ' selected' : '') + '>' + esc(p.description || '?') + '</option>').join('') + '</select>';
    const idt = plano.id_task;
    return {c1: c1, c2: contagemHtml(idt), c3: dataHtml(k, aid), c4: tempoHtml(k, idt)};
  }

  function contagemHtml(idt) {                               // _set_count_cell
    const n = subt[idt];
    if (n == null) return dim('…');
    if (Number(n) === 0) return '<span class="pcm-red">0</span>';
    return esc(n);
  }

  // _add_date_editor: a data vale POR LINHA (a tabela é redesenhada a cada troca de família); a primeira vez, a data da
  // programação em massa às 08:00, e a da outra tarefa do ativo começa na da 1ª linha dele (`base`)
  function dataHtml(k, base) {
    if (!dtByAsset[k]) dtByAsset[k] = (base != null && base !== k && dtByAsset[base]) || ((bulkDate.value || ultimaData || HOJE) + 'T08:00');
    return '<input type="datetime-local" class="dt" value="' + esc(dtByAsset[k]) + '" autocomplete="off">';
  }

  // ── o tempo da tarefa (o _TempoTarefa): HH:mm, começando no que o PLANO diz; a seta anda de 30 em 30 min ──
  const minutosDe = (seg) => Math.floor(Number(seg) / 60);
  function hhmm(min) { const t = Math.max(0, Math.min(min, 23 * 60 + 59)); return p2(Math.floor(t / 60)) + ':' + p2(t % 60); }
  function lerTempo(txt) {                                   // "01:30" (ou "1:30", "0130") → minutos; null se não é horário
    const m = /^\s*(\d{1,2}):?(\d{2})\s*$/.exec(txt || '');
    if (!m) return null;
    const h = Number(m[1]), mi = Number(m[2]);
    return (h <= 23 && mi <= 59) ? h * 60 + mi : null;
  }
  // _TempoTarefa.stepBy: vai para o múltiplo seguinte NA DIREÇÃO do passo (01:10 sobe para 01:30 e desce para 01:00);
  // nunca zera (piso de 15 min, ou o do plano se ele for mais curto); para em 23:30; no limite não anda, nunca ao contrário
  function passoTempo(m, passos) {
    const PASSO = 30, TETO = 23 * 60 + 30;
    let novo = passos > 0 ? (Math.floor(m / PASSO) + 1) * PASSO : (Math.floor((m + PASSO - 1) / PASSO) - 1) * PASSO;
    const piso = Math.min(15, m) || 15;
    novo = Math.max(piso, Math.min(TETO, novo));
    if ((passos > 0 && novo < m) || (passos < 0 && novo > m)) novo = m;
    return novo;
  }
  const segTempo = (k, idt) => durByAsset[k] || durPlano[idt] || DUR_PADRAO;   // `_dur_by_asset.get(aid) or duracao_do_plano`, por linha
  function tempoHtml(k, idt) {
    return '<span class="pcm-tempo" title="' + esc(DICA_TEMPO) + '"><input type="text" class="tp" value="' + hhmm(minutosDe(segTempo(k, idt)))
      + '" inputmode="numeric" maxlength="5" autocomplete="off" aria-label="Tempo da tarefa (HH:mm)"><span class="tp-setas">'
      + '<button type="button" class="tp-b" data-passo="1" tabindex="-1" aria-label="Mais 30 minutos">' + SVG_CIMA + '</button>'
      + '<button type="button" class="tp-b" data-passo="-1" tabindex="-1" aria-label="Menos 30 minutos">' + SVG_BAIXO + '</button></span></span>';
  }
  function planoDaLinha(tr) { const cb = tr && tr.querySelector('select.plano'); return cb && cb.value ? Number(cb.value) : null; }
  // o tempo que a linha mostra quando ninguém mexeu nele: o do plano que o combo mostra agora
  function pintarTempo(tr) {
    const inp = tr && tr.querySelector('input.tp'), k = tr && chaveDe(tr);
    if (!inp || durByAsset[k] != null || document.activeElement === inp) return;
    inp.value = hhmm(minutosDe(segTempo(k, planoDaLinha(tr))));
  }
  function andar(inp, passos) {
    const tr = inp.closest('tr'), k = chaveDe(tr);
    const m = lerTempo(inp.value);
    const atual = m == null ? minutosDe(segTempo(k, planoDaLinha(tr))) : m;
    const novo = passoTempo(atual, passos);
    inp.value = hhmm(novo);
    if (novo !== atual) durByAsset[k] = novo * 60;          // o timeChanged do app só vem quando o tempo muda
  }

  // ── contagem de subtarefas (_fetch_counts_visiveis / _set_counts / _counts_err) ──
  let contando = false;
  function paresFaltando() {
    const out = [];
    tbody.querySelectorAll('tr[data-id] select.plano').forEach((cb) => {
      if (cb.value && !(cb.value in subt)) out.push([Number(cb.value), Number(cb.closest('tr').dataset.id)]);
    });
    return out;
  }
  // em segundo plano, sem o círculo: no app é uma thread e a tabela segue usável. Um pedido por vez (o `self._ws`); no
  // fim, pega o que sobrou — menos o que acabou de ser pedido e não veio, para a falha não virar um laço de pedidos
  function fetchCounts(excluir) {
    if (contando) return;
    const pares = paresFaltando().filter((p) => !(excluir && excluir.has(p[0])));
    if (!pares.length) return;
    contando = true;
    const pedidos = new Set(excluir || []);
    pares.forEach((p) => pedidos.add(p[0]));
    fetch('/os/api/pcm/subtarefas?pares=' + pares.map((p) => p[0] + ':' + p[1]).join(','), {credentials: 'same-origin'})
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => { if (j) { Object.assign(subt, j.subt || {}); Object.assign(durPlano, j.dur || {}); } })
      .catch(() => { /* _counts_err: a linha fica em "…" */ })
      .then(() => { contando = false; pintarContagens(); fetchCounts(pedidos); });
  }
  function pintarContagens() {
    tbody.querySelectorAll('tr[data-id]').forEach((tr) => {
      const idt = planoDaLinha(tr);
      if (idt == null) return;
      tr.children[2].innerHTML = contagemHtml(idt);
      pintarTempo(tr);
    });
  }

  // ── "N marcado(s)" (_upd_label / _sem_plano_rows) ──
  function semPlanoRows() {
    if (semPlano) return [];
    const f = fam();
    return linhas.filter((a) => checked.has(a.id) && loadedFor.has(a.id) && !planosDe(a.id, f).length);
  }
  function updLabel() {
    if (semPlano) {
      selLbl.textContent = checked.size + " marcado(s) · sem plano (cada ativo = 1 tarefa, subtarefa 'Procedimento')";
      return;
    }
    const com = linhas.filter((a) => checked.has(a.id) && planoDaLinha(linhaDe(a.id)) != null).length;
    const sem = semPlanoRows().length, tarefas = linhasQueViramTarefa().length;
    let msg = esc(checked.size + ' marcado(s)');
    if (loadedFor.size) {
      msg += ' · ' + com + ' com plano';
      if (tarefas > com) msg += ' · ' + tarefas + ' tarefa(s)';   // o ativo com duas tarefas conta duas
      if (sem) msg += ' · <span class="pcm-red">' + sem + (comFiltro() ? ' SEM plano neste filtro' : ' SEM plano nesta família') + '</span>';
    }
    selLbl.innerHTML = msg;
  }

  // ── eventos da tabela ──
  tbody.addEventListener('change', (ev) => {
    const tr = ev.target.closest('tr[data-id]');
    if (!tr) return;
    const aid = Number(tr.dataset.id), slot = Number(tr.dataset.slot || 0), k = chave(aid, slot), el = ev.target;
    if (el.classList.contains('chk') && slot) {              // a outra tarefa do ativo: só ela entra ou sai
      if (el.checked) extraOff.delete(k); else extraOff.add(k);
      const a = linhas.find((x) => x.id === aid);
      if (a) tr.outerHTML = trHtml(a, slot);
      fetchCounts(); updLabel();
    } else if (el.classList.contains('chk')) {               // _on_item
      if (el.checked) checked.add(aid); else checked.delete(aid);
      [...extraOff].forEach((x) => { if (x.startsWith(aid + '|')) extraOff.delete(x); });   // marcar de novo traz todas
      fillRow(aid); fetchCounts(); updLabel();
    } else if (el.classList.contains('plano')) {             // _on_combo
      tr.children[2].innerHTML = contagemHtml(Number(el.value));
      pintarTempo(tr);
      fetchCounts();
    } else if (el.classList.contains('dt')) {
      if (el.value) dtByAsset[k] = el.value; else el.value = dtByAsset[k] || '';   // o QDateTimeEdit nunca fica vazio
    } else if (el.classList.contains('tp')) {
      const m = lerTempo(el.value);                          // digitar é livre; o que não é horário volta ao que era
      el.value = m == null ? hhmm(minutosDe(segTempo(k, planoDaLinha(tr)))) : hhmm(m);
    }
  });
  tbody.addEventListener('input', (ev) => {
    const tr = ev.target.closest('tr[data-id]');
    if (!tr) return;
    const k = chaveDe(tr), el = ev.target;
    if (el.classList.contains('dt') && el.value) dtByAsset[k] = el.value;
    if (el.classList.contains('tp')) { const m = lerTempo(el.value); if (m != null) durByAsset[k] = m * 60; }
  });
  tbody.addEventListener('keydown', (ev) => {
    if (!ev.target.classList.contains('tp')) return;
    const passos = {ArrowUp: 1, PageUp: 1, ArrowDown: -1, PageDown: -1}[ev.key];
    if (passos) { ev.preventDefault(); andar(ev.target, passos); }
  });
  tbody.addEventListener('click', (ev) => {
    const b = ev.target.closest('.tp-b');
    if (b) andar(b.closest('.pcm-tempo').querySelector('input.tp'), Number(b.dataset.passo));
  });

  // ── marcar (_marcar_todos / _marcar_com_plano): só as linhas da tabela; marcado fora dela continua marcado ──
  function marcarTodos(marcar) {
    linhas.forEach((a) => { if (marcar) checked.add(a.id); else checked.delete(a.id); });
    extraOff.clear();                                        // as outras tarefas voltam marcadas com o ativo
    fillPlanos();
  }
  bAll.onclick = () => marcarTodos(true);
  bNone.onclick = () => marcarTodos(false);
  bComPlano.onclick = () => {
    if (!loadedFor.size) { hint.textContent = 'Carregue os planos primeiro (marque os ativos → Carregar planos).'; return; }
    const f = fam();
    linhas.forEach((a) => { if (temPlano(a.id, f)) checked.add(a.id); else checked.delete(a.id); });
    extraOff.clear();
    fillPlanos();
  };

  // ── "Sem plano de tarefas" (_on_sem_plano): família, Carregar e Só com plano inativos; aparece a descrição ──
  ckSem.onchange = () => {
    semPlano = ckSem.checked;
    cbFam.disabled = bPlanos.disabled = bComPlano.disabled = cbTipoP.disabled = cbTurno.disabled = semPlano;
    [famLbl, tipoPLbl, turnoLbl].forEach((l) => l.classList.toggle('desab', semPlano));
    descLbl.hidden = edDesc.hidden = !semPlano;
    refresh();
  };

  // ── carregar planos (_carregar_planos / _set_planos / _planos_err) ──
  bPlanos.onclick = async () => {
    const ids = [...checked];                                // TODOS os marcados, inclusive os que o filtro esconde
    avisoPlanos.hidden = true;
    if (!ids.length) { avisoPlanos.textContent = 'Marque ao menos um ativo primeiro.'; avisoPlanos.hidden = false; return; }
    bPlanos.disabled = true;
    const txt = 'buscando planos de ' + ids.length + ' ativo(s)…';
    hint.textContent = txt;
    try {
      const j = await pedir('/os/api/pcm/planos?ativos=' + ids.join(',') + '&visiveis=' + linhas.map((a) => a.id).join(',')
        + '&conhecidos=' + Object.keys(subt).join(','), null, txt);
      setPlanos(j, ids);
    } catch (e) { hint.textContent = '⚠ planos: ' + e.message; }
    finally { bPlanos.disabled = semPlano; }
  };
  function setPlanos(j, ids) {
    loadedFor = new Set(ids);
    planosByAsset = {};
    Object.keys(j.por_ativo || {}).forEach((k) => { planosByAsset[Number(k)] = j.por_ativo[k] || []; });
    Object.assign(subt, j.subt || {}); Object.assign(durPlano, j.dur || {});
    const fams = j.familias || [];
    // "(todas)" + as famílias; o combo volta para a PRIMEIRA família a cada carga, como no app
    cbFam.innerHTML = '<option value="">(todas)</option>' + fams.map(opcao).join('');
    cbFam.value = j.familia || '';
    // o tipo de plano: "(todos)" + os tipos dos planos carregados; o que a pessoa tinha escolhido fica, se ainda existe
    const tipoAntes = cbTipoP.value, tipos = j.tipos || [];
    cbTipoP.innerHTML = '<option value="">(todos)</option>' + tipos.map((t) => '<option value="' + esc(t.chave) + '">' + esc(t.nome) + '</option>').join('');
    cbTipoP.value = tipos.some((t) => t.chave === tipoAntes) ? tipoAntes : '';
    hint.textContent = j.n_planos ? j.n_planos + ' plano(s) em ' + fams.length + ' família(s).' : 'Nenhum plano encontrado p/ os ativos marcados.';
    refresh();                                               // re-ordena com plano no topo + preenche
  }

  // ── data/hora em massa (_set_todas_data / _set_todas_hora / _avancar_mes): nas linhas que têm data ──
  function editores(fn) {
    tbody.querySelectorAll('tr[data-id] input.dt').forEach((inp) => {
      const k = chaveDe(inp.closest('tr')), v = inp.value || dtByAsset[k];
      if (!v) return;
      inp.value = dtByAsset[k] = fn(v);
    });
  }
  // QDateTime.addMonths(1): o mesmo dia no mês seguinte; se o dia não existe lá (31/01), o último dia do mês (28/02)
  function maisUmMes(v) {
    const m = /^(\d{4})-(\d{2})-(\d{2})(T.*)$/.exec(v);
    if (!m) return v;
    let y = Number(m[1]), mo = Number(m[2]) + 1;
    if (mo > 12) { mo = 1; y += 1; }
    const ultimo = new Date(Date.UTC(y, mo, 0)).getUTCDate();
    return String(y).padStart(4, '0') + '-' + p2(mo) + '-' + p2(Math.min(Number(m[3]), ultimo)) + m[4];
  }
  $('b_data').onclick = () => { const d = bulkDate.value; if (d) editores((v) => d + v.slice(10)); };
  $('b_manha').onclick = () => editores((v) => v.slice(0, 10) + 'T07:00');
  $('b_tarde').onclick = () => editores((v) => v.slice(0, 10) + 'T13:00');
  $('b_noite').onclick = () => editores((v) => v.slice(0, 10) + 'T17:00');
  $('b_mes').onclick = () => editores(maisUmMes);
  bulkDate.addEventListener('change', () => { if (bulkDate.value) ultimaData = bulkDate.value; else bulkDate.value = ultimaData; });

  // ── responsável (_carregar_resp / _set_resp / _resp_err) ──
  async function carregarResp(comCirculo) {
    cbResp.innerHTML = '<option value="">carregando…</option>';
    try {
      const url = '/os/api/responsaveis', op = {credentials: 'same-origin'};
      const r = comCirculo ? await OsCarga.buscar(url, op, 'Recarregando os responsáveis…') : await fetch(url, op);
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(apiErro(j, r));
      pessoas = j.pessoas || [];                             // já em ordem de nome, como o _set_resp
      cbResp.innerHTML = '<option value="">' + SEL + '</option>'
        + pessoas.map((p, i) => '<option value="' + i + '">' + esc(p.name || p.code || '?') + '</option>').join('');
    } catch (e) {
      pessoas = [];
      cbResp.innerHTML = '<option value="">⚠ falha — relogue e clique em ↻</option>';
      hint.textContent = '⚠ responsável: ' + e.message;
    }
  }
  bResp.onclick = () => carregarResp(true);
  const pessoa = () => (cbResp.value === '' ? null : (pessoas[Number(cbResp.value)] || null));

  // ── OS pai (OsPaiPicker): digitou → 300 ms → buscar_os_pai; escolher guarda o id; digitar de novo cancela a escolha ──
  let ospaiSel = null, ospaiTimer = null, ospaiSeq = 0;
  ospaiIn.addEventListener('input', () => { ospaiSel = null; clearTimeout(ospaiTimer); ospaiTimer = setTimeout(buscarOsPai, 300); });
  async function buscarOsPai() {
    const termo = ospaiIn.value.trim();
    if (!termo) return;                                      // _buscar: vazio não busca
    const meu = ++ospaiSeq;
    let lista = [];
    try { lista = (await pedir('/os/api/pcm/os-pai?termo=' + enc(termo), null, 'Buscando a OS pai…')).resultados || []; } catch (e) { lista = []; }
    if (meu !== ospaiSeq) return;
    ospaiLista.innerHTML = lista.map((r, i) => '<div class="pcm-ospai-item' + (i === 0 ? ' on' : '') + '" data-id="' + esc(r.id) + '">'
      + esc(r.folio || '') + (r.descricao ? ' — ' + esc(r.descricao) : '') + '</div>').join('');
    ospaiLista.hidden = !lista.length || document.activeElement !== ospaiIn;   // _preencher: abre se o campo tem o foco
  }
  function escolherOsPai(it) {                               // _on_pick
    ospaiSel = {id: Number(it.dataset.id)};
    ospaiIn.value = it.textContent;
    ospaiLista.hidden = true;
  }
  ospaiLista.addEventListener('mousedown', (ev) => {        // mousedown: o blur do campo chegaria antes do click
    const it = ev.target.closest('.pcm-ospai-item');
    if (it) { ev.preventDefault(); escolherOsPai(it); }
  });
  ospaiIn.addEventListener('keydown', (ev) => {
    if (ospaiLista.hidden) return;
    const itens = [...ospaiLista.querySelectorAll('.pcm-ospai-item')];
    let k = itens.findIndex((x) => x.classList.contains('on'));
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      ev.preventDefault();
      k = Math.max(0, Math.min(itens.length - 1, k + (ev.key === 'ArrowDown' ? 1 : -1)));
      itens.forEach((x, i) => x.classList.toggle('on', i === k));
    } else if (ev.key === 'Enter' && itens[k]) { ev.preventDefault(); escolherOsPai(itens[k]); }
    else if (ev.key === 'Escape') ospaiLista.hidden = true;
  });
  ospaiIn.addEventListener('blur', () => setTimeout(() => { ospaiLista.hidden = true; }, 150));
  const idParent = () => (ospaiIn.value.trim() ? (ospaiSel ? ospaiSel.id : null) : null);   // OsPaiPicker.id_parent

  // ── criar: 1 OS com cada ativo marcado como tarefa (_criar / _criar_sem_plano / _criou / _err) ──
  function mostrar(msg, ruim, j) {
    res.hidden = false; res.classList.toggle('ruim', !!ruim); res.textContent = msg;
    if (j && j.ok && j.id_work_order) {                      // a OS criada, a um clique (o detalhe da web)
      const a = document.createElement('a');
      a.className = 'os-link pcm-abrir'; a.href = '/os/os/' + enc(j.id_work_order);
      a.textContent = 'Abrir a OS' + (j.folio ? ' nº ' + j.folio : '');
      res.appendChild(document.createTextNode('\n\n')); res.appendChild(a);
    }
    res.scrollIntoView({behavior: 'smooth', block: 'nearest'});
  }
  // a data de cada linha que vai virar tarefa: o campo da linha (é o que a pessoa vê)
  function dataDaTr(tr) { const inp = tr && tr.querySelector('input.dt'); return inp ? inp.value : null; }
  function dataDaLinha(aid) { return dataDaTr(linhaDe(aid)); }

  // as linhas MARCADAS com plano, na ordem da tela: a 1ª de cada ativo e, embaixo, as das outras tarefas dele que
  // continuam marcadas (a desmarcada não tem combo, então não tem plano)
  function linhasQueViramTarefa() {
    const out = [];
    linhas.forEach((a) => {
      if (!checked.has(a.id)) return;
      const tr = linhaDe(a.id);
      if (!tr || planoDaLinha(tr) == null) return;
      out.push(tr);
      extrasDe(a.id).forEach((x) => { if (!extraOff.has(chaveDe(x)) && planoDaLinha(x) != null) out.push(x); });
    });
    return out;
  }

  btn.onclick = () => { if (semPlano) criarSemPlano(); else criar(); };

  // O que o app deixa de fora SEM avisar (27/09): o ativo marcado que o filtro escondeu (ou que é de outra usina — a
  // marca sobrevive à troca) e, no caminho com plano, o marcado depois do último "Carregar planos". A OS continua saindo
  // igual à do app, com as linhas da tabela; só a confirmação passa a dizer quem não vai.
  function lista(itens) {
    return itens.slice(0, 10).map((a) => a.label || a.code || '?').join('\n- ') + (itens.length > 10 ? '\n- …' : '');
  }
  function avisoEscondidos() {
    const naTabela = new Set(linhas.map((a) => a.id));
    const fora = [...checked].filter((id) => !naTabela.has(id));
    if (!fora.length) return '';
    const conhecidos = ativos.filter((a) => fora.includes(a.id)), outros = fora.length - conhecidos.length;
    return '\n\nFicam de FORA (marcados, mas fora da tabela — limpe a busca ou o tipo para incluí-los):'
      + (conhecidos.length ? '\n- ' + lista(conhecidos) : '')
      + (outros ? '\n- ' + outros + ' ativo(s) marcado(s) em outra usina' : '');
  }

  function criar() {
    const sel = [], sem = [], vistos = new Set(), repetidos = [];
    // uma seleção por LINHA marcada (25/11/2026): o ativo com duas tarefas manda duas, cada uma com o seu plano, data e tempo
    linhasQueViramTarefa().forEach((tr) => {
      const aid = Number(tr.dataset.id), idt = planoDaLinha(tr), k = chaveDe(tr);
      if (vistos.has(aid + ':' + idt)) {                     // o mesmo plano em duas linhas do mesmo ativo: a mesma tarefa duas vezes
        const a = linhas.find((x) => x.id === aid);
        repetidos.push((a && (a.label || a.code)) || '?');
      }
      vistos.add(aid + ':' + idt);
      sel.push({asset_id: aid, id_task: idt, event_date: dataDaTr(tr),
                duracao: durByAsset[k] != null ? durByAsset[k] : null});   // o tempo da linha; null = o do plano
    });
    linhas.forEach((a) => {
      if (checked.has(a.id) && loadedFor.has(a.id) && planoDaLinha(linhaDe(a.id)) == null) sem.push(a.label || a.code || '?');
    });
    if (!sel.length) { mostrar('Carregue os planos e marque ao menos um ativo com plano.', true); return; }
    if (repetidos.length) {
      mostrar('O mesmo plano está em duas linhas do mesmo ativo (escolha outro plano ou desmarque uma delas):\n- '
              + repetidos.slice(0, 10).join('\n- '), true);
      return;
    }
    const p = pessoa();
    if (!p || !p.id_personnel) { mostrar('Escolha o responsável.', true); return; }
    if (sel.some((s) => !s.event_date)) { mostrar('Data inválida.', true); return; }
    const nAtivos = new Set(sel.map((s) => s.asset_id)).size;
    let aviso = '';
    if (sem.length) aviso = '\n\nFicam de FORA (sem plano nesta família):\n- ' + sem.slice(0, 10).join('\n- ') + (sem.length > 10 ? '\n- …' : '');
    const semCarga = linhas.filter((a) => checked.has(a.id) && !loadedFor.has(a.id));
    if (semCarga.length) aviso += '\n\nFicam de FORA (marcados depois de carregar os planos — clique em “Carregar planos” de novo):\n- ' + lista(semCarga);
    aviso += avisoEscondidos();
    const cada = nAtivos === sel.length ? ' — uma por ativo marcado.'
      : ' — uma por linha marcada (' + (sel.length - nAtivos) + ' a mais nos ativos com mais de uma tarefa).';
    if (!confirm('Vou criar UMA OS com ' + sel.length + ' tarefa(s)' + cada + aviso + '\n\nContinuar?')) return;
    enviar({sem_plano: false, selecoes: sel, responsavel: {id_personnel: p.id_personnel, name: p.name},
            descricao: '', note: obs.value.trim(), id_parent: idParent()}, sel.length);
  }

  function criarSemPlano() {
    const sel = linhas.filter((a) => checked.has(a.id)).map((a) => ({asset_id: a.id, event_date: dataDaLinha(a.id)}));
    if (!sel.length) { mostrar('Marque ao menos um ativo.', true); return; }
    const p = pessoa();
    if (!p || !p.id_personnel) { mostrar('Escolha o responsável.', true); return; }
    if (sel.some((s) => !s.event_date)) { mostrar('Data inválida.', true); return; }
    const desc = edDesc.value.trim();
    if (!confirm('Vou criar UMA OS com ' + sel.length + " tarefa(s) SEM plano — uma por ativo, subtarefa 'Procedimento'"
                 + (desc ? ' · descrição: ' + desc : '') + '.' + avisoEscondidos() + '\n\nContinuar?')) return;
    enviar({sem_plano: true, selecoes: sel, responsavel: {id_personnel: p.id_personnel, name: p.name},
            descricao: desc, note: obs.value.trim(), id_parent: idParent()}, sel.length);
  }

  async function enviar(corpo, n) {
    btn.disabled = true; res.hidden = true;
    hint.textContent = 'criando 1 OS com ' + n + ' tarefa(s)… (pode levar alguns segundos)';
    try {
      const r = await OsCarga.buscar('/os/api/pcm/criar', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(corpo), credentials: 'same-origin'}, 'Criando a OS no Fracttal…');
      const j = await r.json().catch(() => ({}));
      if (!r.ok) mostrar(apiErro(j, r), true);               // _err (e a recusa do servidor, que repete as do app)
      else mostrar(j.mensagem || '', !j.ok, j);              // _criou
    } catch (e) { mostrar(String(e), true); }
    finally { btn.disabled = false; hint.textContent = ''; }
  }

  // ── arranque (_fill_clientes → _on_cli; carregar_inicial → _carregar_resp) ──
  // o navegador devolve o que estava nos campos ao voltar para a página; a tela nasce limpa, como o diálogo do app
  cbCli.selectedIndex = 0; ckSem.checked = false; busca.value = ''; edDesc.value = ''; obs.value = ''; ospaiIn.value = '';
  if (!bulkDate.value) bulkDate.value = HOJE;
  cbCli.onchange = onCli;
  cbUsi.onchange = onUsi;
  cbTipo.onchange = refresh;
  busca.oninput = refresh;
  cbFam.onchange = refresh;                                  // re-ordena (com plano no topo) + re-preenche
  cbTipoP.onchange = refresh;                                // o tipo de plano e o turno, como a família
  cbTurno.onchange = refresh;
  refresh();
  carregarResp(false);
})();

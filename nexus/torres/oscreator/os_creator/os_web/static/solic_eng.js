// os_creator/os_web/static/solic_eng.js — a Nova solicitação para a ENGENHARIA (Levi, 06/10/2026). Cascata cliente →
// usina, TODOS os ativos da usina (filtro por texto e por tipo, com o nome no lugar da sigla), uma OS por ativo com
// '[Ativo] - Descrição', o problema na observação, o responsável só entre os da Engenharia e a data programada de 7 dias
// (Urgente: 2), que NÃO se edita: a tela só mostra, e o servidor calcula ao criar. As regras de verdade são do servidor
// (solic_eng_web.py) — aqui é a primeira barreira.
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const raiz = $('eng');
  if (!raiz) return;
  const cbCli = $('cb_cli'), cbUsi = $('cb_usi'), busca = $('busca'), cbTipo = $('cb_tipo'), tbody = $('tbody');
  const bAll = $('b_all'), bNone = $('b_none'), selLbl = $('sel_lbl'), edDesc = $('ed_desc'), taProb = $('ta_prob');
  const preview = $('preview'), cbResp = $('cb_resp'), dtProg = $('dt_prog'), ckUrg = $('ck_urg'), lbPrazo = $('lb_prazo');
  const dtEvento = $('dt_evento');
  const hintResp = $('hint_resp'), hintCriar = $('hint_criar'), btn = $('btn_criar'), resultado = $('resultado');
  const DIAS = Number(raiz.dataset.dias), DIAS_URG = Number(raiz.dataset.diasUrgente);
  let ativos = [], pessoas = [], criando = false;
  const marcados = new Set();
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const semAcento = (t) => String(t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

  async function pedir(url, opcoes, texto) {
    const r = await OsCarga.buscar(url, Object.assign({credentials: 'same-origin', headers: {'Accept': 'application/json'}}, opcoes || {}), texto);
    let j = null;
    try { j = await r.json(); } catch (e) { j = null; }
    if (!r.ok) throw new Error((j && (j.erro || j.mensagem)) || ('HTTP ' + r.status));
    return j || {};
  }
  function mostrar(texto, ruim) {
    resultado.hidden = !texto; resultado.textContent = texto || ''; resultado.classList.toggle('ruim', !!ruim);
  }

  // ── cascata ────────────────────────────────────────────────────────────────────────────────────────
  function semAtivos(texto) {
    ativos = []; marcados.clear();
    cbTipo.innerHTML = '<option value="">Todos os tipos</option>';
    [busca, cbTipo, bAll, bNone].forEach((x) => { x.disabled = true; });
    tbody.innerHTML = '<tr class="vazio"><td colspan="3">' + esc(texto) + '</td></tr>';
    contar();
  }
  async function trocarCliente() {
    try {
      const j = await pedir('/os/api/solicitacao/engenharia/usinas?cliente=' + encodeURIComponent(cbCli.value), null, 'Carregando as usinas…');
      const antes = cbUsi.value, us = j.usinas || [];
      cbUsi.innerHTML = '<option value="">— Selecione a usina —</option>'
        + us.map((u) => '<option value="' + esc(u) + '">' + esc(u) + '</option>').join('');
      if (us.indexOf(antes) >= 0) cbUsi.value = antes;
      else { cbUsi.value = ''; semAtivos('Selecione a usina para carregar os ativos.'); }
    } catch (e) { mostrar('Não consegui carregar as usinas: ' + e.message, true); }
  }
  async function trocarUsina() {
    if (!cbUsi.value) { semAtivos('Selecione a usina para carregar os ativos.'); return; }
    try {
      const j = await pedir('/os/api/solicitacao/engenharia/ativos?usina=' + encodeURIComponent(cbUsi.value), null, 'Buscando os ativos da usina…');
      ativos = j.ativos || []; marcados.clear();
      cbTipo.innerHTML = '<option value="">Todos os tipos</option>'
        + (j.tipos || []).map((t) => '<option value="' + esc(t.tipo) + '">' + esc(t.nome) + '</option>').join('');
      [busca, cbTipo, bAll, bNone].forEach((x) => { x.disabled = false; });
      busca.value = '';
      pintar();
    } catch (e) { semAtivos('Não consegui carregar os ativos: ' + e.message); }
  }

  // ── a tabela ───────────────────────────────────────────────────────────────────────────────────────
  function visiveis() {
    const q = semAcento(busca.value.trim()), t = cbTipo.value;
    return ativos.filter((a) => (!t || a.tipo === t) && (!q || semAcento(a.label + ' ' + a.code).indexOf(q) >= 0));
  }
  function pintar() {
    const vs = visiveis();
    if (!ativos.length) tbody.innerHTML = '<tr class="vazio"><td colspan="3">Esta usina não tem ativos no catálogo.</td></tr>';
    else if (!vs.length) tbody.innerHTML = '<tr class="vazio"><td colspan="3">Nenhum ativo com esse filtro.</td></tr>';
    else {
      tbody.innerHTML = vs.map((a) => '<tr data-id="' + esc(a.id) + '"' + (marcados.has(String(a.id)) ? ' class="sel"' : '') + '>'
        + '<td class="c-chk"><input type="checkbox"' + (marcados.has(String(a.id)) ? ' checked' : '') + ' aria-label="Marcar ' + esc(a.label) + '"></td>'
        + '<td>' + esc(a.label) + '</td><td>' + esc(a.tipo_nome) + '</td></tr>').join('');
    }
    contar();
  }
  function contar() {
    selLbl.textContent = marcados.size + ' marcado(s)';
    const primeiro = ativos.find((a) => marcados.has(String(a.id)));
    const d = edDesc.value.trim() || 'Descrição';
    preview.textContent = primeiro
      ? 'Ex.: [' + (primeiro.curto || primeiro.label) + '] - ' + d + (marcados.size > 1 ? '   (+' + (marcados.size - 1) + ' OS, uma por ativo)' : '')
      : 'O prefixo [Ativo] entra automático em cada OS.';
  }
  tbody.addEventListener('click', (e) => {
    const tr = e.target.closest('tr[data-id]');
    if (!tr) return;
    const ck = tr.querySelector('input[type=checkbox]');
    if (e.target !== ck) ck.checked = !ck.checked;          // clicar na linha também marca
    const id = tr.dataset.id;
    if (ck.checked) marcados.add(id); else marcados.delete(id);
    tr.classList.toggle('sel', ck.checked);
    contar();
  });
  bAll.addEventListener('click', () => { visiveis().forEach((a) => marcados.add(String(a.id))); pintar(); });
  bNone.addEventListener('click', () => { marcados.clear(); pintar(); });
  busca.addEventListener('input', pintar);
  cbTipo.addEventListener('change', pintar);
  cbCli.addEventListener('change', trocarCliente);
  cbUsi.addEventListener('change', trocarUsina);
  edDesc.addEventListener('input', contar);

  // ── responsável e data ─────────────────────────────────────────────────────────────────────────────
  async function carregarResponsaveis() {
    try {
      const j = await pedir('/os/api/solicitacao/engenharia/responsaveis', null, 'Carregando os responsáveis…');
      pessoas = j.pessoas || [];
      cbResp.innerHTML = '<option value="">— Selecione —</option>'
        + pessoas.map((p) => '<option value="' + esc(p.id_personnel) + '">' + esc(p.name) + '</option>').join('');
      cbResp.disabled = !pessoas.length;
      if (!j.configurado) hintResp.textContent = 'A lista da Engenharia não está configurada (OS_WEB_ENGENHARIA_RESPONSAVEIS no .env do servidor).';
      else if ((j.faltam || []).length) hintResp.textContent = 'Não achei no Fracttal: ' + j.faltam.join(', ') + '.';
      else hintResp.textContent = '';
    } catch (e) {
      cbResp.innerHTML = '<option value="">não carregou</option>';
      hintResp.textContent = 'Não consegui carregar os responsáveis: ' + e.message;
    }
  }
  // A data programada NÃO se edita (Levi, 06/10): a tela só mostra a hora da criação + 7 dias (Urgente: + 2). A base é a
  // hora do servidor quando a página abriu, andando com o relógio daqui — com a página aberta por muito tempo, a data
  // mostrada continua sendo a que o servidor vai pôr ao criar (é ele quem põe; a tela não manda data nenhuma).
  const m0 = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?/.exec(raiz.dataset.agora || '');
  const BASE = m0 ? Date.UTC(+m0[1], +m0[2] - 1, +m0[3], +m0[4], +m0[5], +(m0[6] || 0)) : null, T0 = Date.now();
  const p2 = (n) => String(n).padStart(2, '0');
  function dataProg() {
    if (BASE === null) return dtProg.textContent;
    const d = new Date(BASE + (Date.now() - T0) + (ckUrg.checked ? DIAS_URG : DIAS) * 864e5);
    return p2(d.getUTCDate()) + '/' + p2(d.getUTCMonth() + 1) + '/' + d.getUTCFullYear() + ' ' + p2(d.getUTCHours()) + ':' + p2(d.getUTCMinutes());
  }
  function mostrarData() {
    const urg = ckUrg.checked;
    raiz.classList.toggle('eng-e-urgente', urg);
    dtProg.textContent = dataProg();
    lbPrazo.textContent = '(automática' + (urg ? ', urgente' : '') + ': ' + (urg ? DIAS_URG : DIAS) + ' dias a partir da criação)';
  }
  ckUrg.addEventListener('change', mostrarData);
  setInterval(mostrarData, 30000);

  // ── criar ──────────────────────────────────────────────────────────────────────────────────────────
  function falta() {
    if (!marcados.size) return 'Marque ao menos um ativo.';
    if (!edDesc.value.trim()) return 'Escreva a atividade a ser realizada (o nome da OS).';
    if (!taProb.value.trim()) return 'Descreva o problema.';
    if (!cbResp.value) return 'Escolha o responsável da Engenharia.';
    if (!dtEvento.value) return 'Informe a data do evento.';
    return '';
  }
  const evBr = (v) => { const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}:\d{2})/.exec(v || ''); return m ? m[3] + '/' + m[2] + '/' + m[1] + ' ' + m[4] : v; };
  btn.addEventListener('click', async () => {
    if (criando) return;
    const erro = falta();
    hintCriar.textContent = erro;
    if (erro) return;
    const resp = pessoas.find((p) => String(p.id_personnel) === cbResp.value) || {};
    const n = marcados.size, urg = ckUrg.checked;
    if (!confirm('Vou criar ' + n + ' OS — uma por ativo — para a Engenharia, atribuída' + (n > 1 ? 's' : '') + ' a ' + resp.name
                 + ', com o evento em ' + evBr(dtEvento.value) + ' e programada' + (n > 1 ? 's' : '') + ' para ' + dataProg()
                 + (urg ? ' (URGENTE)' : '') + '.\n\nContinuar?')) return;
    criando = true; btn.disabled = true; mostrar('');
    try {
      const j = await pedir('/os/api/solicitacao/engenharia/criar', {
        method: 'POST', headers: {'Accept': 'application/json', 'Content-Type': 'application/json'},
        body: JSON.stringify({ativos: Array.from(marcados), descricao: edDesc.value, problema: taProb.value,
                              responsavel: {id_personnel: resp.id_personnel}, evento: dtEvento.value, urgente: urg})},
        'Criando as OS no Fracttal…');
      mostrar(j.mensagem + ((j.avisos || []).length ? '\n\n' + j.avisos.join('\n') : ''), j.falhas > 0);
      marcados.clear(); pintar();                            // o que foi criado sai da seleção: um 2º clique não duplica
    } catch (e) { mostrar(e.message, true); }
    finally { criando = false; btn.disabled = false; }
  });

  carregarResponsaveis();
})();

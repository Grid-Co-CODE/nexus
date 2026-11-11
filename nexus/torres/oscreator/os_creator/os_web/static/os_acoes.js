// os_creator/os_web/static/os_acoes.js — as AÇÕES do card da OS no navegador: trocar responsável, etiquetas, editar a
// observação, Concluir OS, Cancelar OS, Fluxo e anexos (steps/os_detalhe.py, cancelar_os.py, os_fluxo.py, galeria.py,
// documentos.py). Mesma sequência de cada diálogo do app: carrega a lista → a pessoa escolhe → confirma → grava → o card
// recarrega (/os/os/<wid>?parcial=1). Erros vão para a .os-resultado do card ou para a linha de hint do diálogo, nunca alert().
//
// DELEGAÇÃO no document, e não um listener por card: o card chega por innerHTML (o Histórico injeta o fragmento no modal) e
// é trocado inteiro a cada recarga — um listener preso ao elemento se perderia. Basta o script estar na página.
//
// Fora do card, uma caixa com data-os-acoes (e data-wid/data-folio) também recebe as ações: a tela do chamado do
// Acompanhamento troca o responsável assim (19/10/2026). Com data-no-lugar, o que mudou é escrito ali mesmo
// (trocouNoLugar), porque não há card para recarregar.
(function () {
  'use strict';
  if (window.OsAcoes) return;                         // incluído duas vezes (página cheia + card) não duplica handlers

  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const apiErro = (j, r) => (j && j.erro) ? (j.login ? j.erro + ' Entre de novo em /os/login.' : j.erro) : ('HTTP ' + (r && r.status));
  const q = (el, s) => el.querySelector(s);
  const card = (el) => el.closest('.det, [data-os-acoes]');
  const anexosCache = new WeakMap();                  // a lista de anexos por card — duas rodadas de RPC, não repetir a cada clique

  async function pedir(url, corpo, texto) {
    const opt = {credentials: 'same-origin', headers: {'Accept': 'application/json'}};
    if (corpo !== undefined) { opt.method = 'POST'; opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(corpo); }
    const r = await OsCarga.buscar(url, opt, texto || 'Gravando no Fracttal…');
    let j = null; try { j = await r.json(); } catch (e) { j = null; }
    if (!r.ok) throw new Error(apiErro(j, r));
    return j || {};
  }

  function mensagem(d, texto, ruim) {
    const m = q(d, '[data-msg]'); if (!m) return;
    m.hidden = !texto; m.textContent = texto || ''; m.classList.toggle('ruim', !!ruim);
  }

  // contagem dos dois cards de anexos — chega depois do detalhe, como no app (o Histórico faz o mesmo na 1ª abertura)
  // o "Retornar para responsável" (10/11/2026) só aparece para quem pode: a rota diz, depois que o card abre (o cadastro
  // das usinas não é lido na frente do card). Erro ou "não pode": o botão segue escondido
  function retornarPode(d) {
    const b = q(d, '[data-retornar-pode]'); if (!b) return;
    fetch(b.getAttribute('data-retornar-pode'), {credentials: 'same-origin', headers: {'Accept': 'application/json'}})
      .then((r) => r.ok ? r.json() : null)
      .then((j) => { b.hidden = !(j && j.pode); })
      .catch(() => { b.hidden = true; });
  }

  function contagem(d) {
    retornarPode(d);
    const el = q(d, '[data-anexos]'); if (!el) return;
    fetch(el.getAttribute('data-anexos'), {credentials: 'same-origin', headers: {'Accept': 'application/json'}})
      .then((r) => r.ok ? r.json() : null)
      .then((j) => {
        d.querySelectorAll('.det-n').forEach((n) => { const v = j ? j[n.getAttribute('data-n')] : null; n.textContent = (v === null || v === undefined) ? '—' : v; });
        // quantos anexos cada tarefa tem (04/11/2026): o número no ativo e o botão dos anexos dela
        const pt = (j && j.por_tarefa) || {};
        d.querySelectorAll('[data-n-tarefa]').forEach((el) => { const n = pt[el.getAttribute('data-n-tarefa')] || 0; el.textContent = n === 1 ? '1 anexo' : n + ' anexos'; el.hidden = !n; });
        d.querySelectorAll('[data-acao="anexos-tarefa"]').forEach((b) => { b.hidden = !pt[b.dataset.tarefaId]; });
      })
      .catch(() => { d.querySelectorAll('.det-n').forEach((n) => { n.textContent = '—'; }); });
  }

  // Recarrega o card NO LUGAR (o corpo do modal do Histórico ou o main da página cheia): o Fracttal é a fonte do que ficou.
  async function recarregar(d, url, texto, ruim) {
    const r = await OsCarga.buscar(url, {credentials: 'same-origin', headers: {'X-Requested-With': 'fetch'}}, 'Abrindo a OS…');
    const html = await r.text();
    const tmp = document.createElement('div'); tmp.innerHTML = html;
    const novo = tmp.querySelector('.det') || tmp.firstElementChild;
    if (!novo) { mensagem(d, 'Não consegui recarregar a OS.', true); return d; }
    d.replaceWith(novo);
    if (novo.classList.contains('det')) { contagem(novo); if (texto) mensagem(novo, texto, ruim); }
    const rolo = novo.closest('.os-modal-card'); if (rolo) rolo.scrollTop = 0; else window.scrollTo(0, 0);
    return novo;
  }
  // O envio do Incluir anexo (06/11/2026), do seletor e do colar: o POST /os/api/os/<id>/anexos, que relê a OS e diz o
  // que subiu e o que não (o Fracttal aceita calado); depois, o card recarregado ou, fora dele, a contagem relida
  async function enviarAnexos(d, fs) {
    const b = q(d, '[data-acao="anexo-incluir"]'), rotulo = b ? b.textContent : '';
    const fd = new FormData(); fs.forEach((f) => fd.append('anexos', f, f.name)); fd.append('folio', d.dataset.folio || '');
    if (b) trava(b, true, 'enviando…');
    mensagem(d, '');
    try {
      const r = await OsCarga.buscar('/os/api/os/' + d.dataset.wid + '/anexos',
        {method: 'POST', credentials: 'same-origin', headers: {'Accept': 'application/json'}, body: fd},
        fs.length === 1 ? 'Enviando o anexo para o Fracttal…' : 'Enviando ' + fs.length + ' anexos para o Fracttal…');
      let j = null; try { j = await r.json(); } catch (e) { j = null; }
      if (!r.ok && !(j && j.incluidos && j.incluidos.length)) throw new Error(apiErro(j, r));
      anexosCache.delete(d); alterou(d); if (b) trava(b, false, rotulo);
      if (d.hasAttribute('data-no-lugar')) { contagem(d); mensagem(d, j.mensagem, !j.ok); return; }
      await recarregar(d, urlCard(d), j.mensagem, !j.ok);
    } catch (e) { if (b) trava(b, false, rotulo); mensagem(d, 'Não consegui incluir o anexo: ' + e.message, true); }
  }

  // Colar para anexar (Levi, 06/11/2026: "No anexo pode ser possível anexar com CTRL + V OU WINDOWS + V"): o arquivo ou a
  // imagem da área de transferência (o Win+V cola do histórico pelo mesmo evento) vai para a OS aberta depois de um
  // "Anexar à OS" à vista: colar sem querer não sobe nada. Colar num campo de texto segue sendo texto. A imagem colada vem
  // como "image.png": ganha o nome com a data e a hora, para não virar "image (7).png" na OS.
  function nomeColado(f, i) {
    if (f.name && !/^image\.(png|jpe?g|gif|webp|bmp)$/i.test(f.name)) return f;
    const p = (n) => String(n).padStart(2, '0'), a = new Date();
    const ext = ((f.type || '').split('/')[1] || 'png').replace('jpeg', 'jpg');
    const nome = 'colado ' + a.getFullYear() + '-' + p(a.getMonth() + 1) + '-' + p(a.getDate()) + ' ' + p(a.getHours()) + 'h'
      + p(a.getMinutes()) + 'm' + p(a.getSeconds()) + 's' + (i ? ' ' + (i + 1) : '') + '.' + ext;
    return new File([f], nome, {type: f.type});
  }
  function oferecerColados(d, fs) {
    const linha = q(d, '.det-anx-incluir'); if (!linha) return;
    let caixa = q(d, '[data-anx-colado]');
    if (!caixa) { caixa = document.createElement('div'); caixa.className = 'det-anx-colado'; caixa.setAttribute('data-anx-colado', ''); linha.after(caixa); }
    caixa.innerHTML = '<span>' + esc(fs.length === 1 ? '1 arquivo colado: ' : fs.length + ' arquivos colados: ')
      + esc(fs.map((f) => f.name).join(', ')) + '</span>'
      + '<button type="button" class="det-b verde" data-colado-sim>Anexar à OS</button>'
      + '<button type="button" class="det-b ghost" data-colado-nao>Descartar</button>';
    caixa.querySelector('[data-colado-sim]').addEventListener('click', () => { caixa.remove(); enviarAnexos(d, fs); });
    caixa.querySelector('[data-colado-nao]').addEventListener('click', () => caixa.remove());
  }
  document.addEventListener('paste', (e) => {
    const t = e.target;
    if (t && t.closest && t.closest('input, textarea, select, [contenteditable="true"]')) return;
    const fs = Array.from((e.clipboardData && e.clipboardData.files) || []).map(nomeColado);
    if (!fs.length) return;
    const inp = document.querySelector('.det [data-anx-arquivos], [data-os-acoes] [data-anx-arquivos]');
    const d = inp && card(inp); if (!d) return;
    e.preventDefault();
    oferecerColados(d, fs);
  });

  // Fora do card (a tela do chamado de Garantias, 06/11/2026): o que mudou o status da OS relê a página inteira, com o
  // recado à vista um instante antes
  function relerPagina(d, texto, ruim) {
    mensagem(d, (texto || 'Feito.') + ' Atualizando a tela…', ruim);
    setTimeout(() => location.reload(), 1600);
  }
  const urlCard = (d, status) => '/os/os/' + d.dataset.wid + '?parcial=1&status=' + encodeURIComponent(status || d.dataset.status || '');
  // a OS mudou no Fracttal: quem mostra uma LISTA dela (o Histórico, por baixo do card) sabe que tem de reler ao fechar
  const alterou = (d) => document.dispatchEvent(new CustomEvent('os:alterada', {detail: {wid: d && d.dataset.wid}}));

  // ── diálogo: clona o <template data-dlg> do card num overlay ACIMA do modal do Histórico ──
  let aberto = null;
  let visor = null;                                   // o carrossel das fotos (abrirVisor), por cima de tudo
  // "2026-09-21T14:30" no fuso de quem esta olhando — o <input datetime-local> nao aceita ISO com Z
  function agoraLocal() {
    const t = new Date(); t.setMinutes(t.getMinutes() - t.getTimezoneOffset());
    return t.toISOString().slice(0, 16);
  }

  // Cada subtarefa vira o campo do SEU tipo. Texto num campo que devia ser Aprovado/Alerta/Falhou
  // grava lixo no checklist — e o Fracttal aceita, que e o pior dos casos.
  function campoHTML(c) {
    const id = 'f' + c.id_form_item, req = c.obrigatorio ? ' <span class="os-req">obrigatória</span>' : '';
    const fot = c.anexo_obrigatorio ? ' <span class="det-ajuda">(pede foto no Fracttal)</span>' : '';
    let ctrl;
    if ((c.opcoes || []).length) {
      ctrl = '<select data-fid="' + esc(c.id_form_item) + '" id="' + id + '"><option value="">— selecione —</option>'
        + c.opcoes.map((o) => '<option value="' + esc(o.valor) + '"' + (String(o.valor) === String(c.valor) ? ' selected' : '') + '>' + esc(o.rotulo) + '</option>').join('') + '</select>';
    } else if (c.tipo_nome === 'num') {
      ctrl = '<input type="number" step="any" data-fid="' + esc(c.id_form_item) + '" id="' + id + '" value="' + esc(c.valor) + '">';
    } else {
      // o texto numa caixa que quebra a linha e cresce (09/11/2026: "está rolando infinito para o lado")
      ctrl = '<textarea class="acoes-ta acoes-resp" rows="2" data-fid="' + esc(c.id_form_item) + '" id="' + id + '">' + esc(c.valor) + '</textarea>';
    }
    return '<label class="os-campo acoes-exec-c"><span class="os-lbl">' + esc(c.descricao) + req + fot + '</span>' + ctrl + '</label>';
  }

  function dialogo(d, nome) {
    const t = q(d, 'template[data-dlg="' + nome + '"]'); if (!t) return null;
    if (aberto) aberto.fechar();
    const fundo = document.createElement('div'); fundo.className = 'acoes-fundo';
    const caixa = document.createElement('div'); caixa.className = 'acoes-dlg acoes-dlg-' + nome;
    caixa.setAttribute('role', 'dialog'); caixa.setAttribute('aria-modal', 'true');
    caixa.appendChild(t.content.cloneNode(true)); fundo.appendChild(caixa); document.body.appendChild(fundo);
    const dlg = {caixa, fechar() { fundo.remove(); if (aberto === dlg) aberto = null; }};
    fundo.addEventListener('click', (e) => { if (e.target === fundo || e.target.closest('[data-fechar]')) dlg.fechar(); });
    aberto = dlg;
    // a busca do os_busca entra JÁ, e não só quando o observador dele acordar: o foco abaixo cai nela, e não num <select>
    // que ele embrulharia logo depois, tirando o foco (Levi, 08/10/2026: "conseguir digitar no responsável")
    if (window.OsBusca) window.OsBusca.aplicar(caixa);
    const foco = caixa.querySelector('select, input, textarea, button:not([data-fechar])'); if (foco) foco.focus();
    return dlg;
  }
  // Escape fecha o MEU diálogo, e só ele: o Histórico também escuta Escape no document para fechar o card inteiro —
  // a captura na window chega antes e segura a propagação enquanto um diálogo estiver aberto.
  window.addEventListener('keydown', (e) => {
    if (visor) {                                        // o carrossel (28/09) por cima da galeria: ele responde primeiro
      if (e.key === 'Escape') { e.stopPropagation(); e.preventDefault(); visor.fechar(); }
      else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.stopPropagation(); e.preventDefault(); visor.ir(e.key === 'ArrowLeft' ? -1 : 1); }
      return;
    }
    // com a lista da busca aberta (trocar responsável), o 1º Esc é dela: fecha a lista e volta o texto; o 2º fecha o
    // diálogo. Antes o Esc fechava o diálogo inteiro com a lista aberta (revisão de 08/10/2026, "digitar no responsável")
    const t = e.target;
    if (e.key === 'Escape' && aberto && t && t.matches && t.matches('.osb-in[aria-expanded="true"]') && aberto.caixa.contains(t)) return;
    if (e.key === 'Escape' && aberto) { e.stopPropagation(); e.preventDefault(); aberto.fechar(); }
  }, true);
  const hint = (dlg, texto) => { const h = q(dlg.caixa, '[data-hint]'); if (h) h.textContent = texto || ''; };
  const trava = (btn, on, texto) => { btn.disabled = !!on; if (texto !== undefined) btn.textContent = texto; };
  const numero = (v) => /^\d+$/.test(String(v)) ? Number(v) : v;

  function modoNota(d, editando) {                    // leitura ↔ edição no MESMO espaço: só um dos dois fica visível
    q(d, '[data-nota-leitura]').hidden = editando; q(d, '[data-nota-editor]').hidden = !editando;
    q(d, '[data-acao="nota-editar"]').hidden = editando;
    q(d, '[data-acao="nota-salvar"]').hidden = !editando; q(d, '[data-acao="nota-cancelar"]').hidden = !editando;
  }

  // A tela do chamado (Garantias, 19/10/2026): o nome muda ali mesmo, a cor de "no nome de outra pessoa" segue a regra
  // do servidor (j.da_equipe, a do quadro) e o diálogo, aberto de novo, já diz com quem a OS ficou.
  function trocouNoLugar(d, nome, j) {
    const n = q(d, '[data-resp-nome]');
    if (n) {
      n.textContent = nome;
      const dd = n.closest('dd'); if (dd && typeof j.da_equipe === 'boolean') dd.classList.toggle('a', !j.da_equipe);
    }
    const t = q(d, 'template[data-dlg="responsavel"]');
    if (t) {
      let s = t.content.querySelector('.acoes-s');
      if (!s) {
        s = document.createElement('div'); s.className = 'acoes-s'; s.innerHTML = 'Hoje está com <b></b>.';
        t.content.querySelector('.acoes-t').after(s);
      }
      s.querySelector('b').textContent = nome;
    }
    mensagem(d, j.mensagem);
  }

  const ACOES = {
    // TrocarResponsavelDialog: lista o pessoal, a pessoa escolhe, 'Atribuir' grava (api.mudar_responsavel)
    async responsavel(d) {
      const dlg = dialogo(d, 'responsavel'); if (!dlg) return;
      const sel = q(dlg.caixa, '[data-resp-sel]'), ok = q(dlg.caixa, '[data-conf="responsavel"]');
      try {
        const j = await pedir('/os/api/responsaveis');
        sel.innerHTML = '<option value="">— escolha a pessoa —</option>' + (j.pessoas || []).filter((p) => p.id_personnel)
          .map((p) => '<option value="' + esc(p.id_personnel) + '">' + esc(p.name || '?') + '</option>').join('');
        ok.disabled = false;
      } catch (e) { hint(dlg, 'não consegui buscar o pessoal: ' + e.message); }
      ok.addEventListener('click', async () => {
        const opt = sel.selectedOptions[0];
        if (!opt || !opt.value) { hint(dlg, 'escolha a pessoa.'); return; }
        trava(ok, true); hint(dlg, 'gravando no Fracttal…');
        try {
          const j = await pedir('/os/api/os/' + d.dataset.wid + '/responsavel', {id_personnel: numero(opt.value), name: opt.textContent, folio: d.dataset.folio});
          alterou(d); dlg.fechar();
          if (d.hasAttribute('data-no-lugar')) { trocouNoLugar(d, opt.textContent, j); return; }
          await recarregar(d, urlCard(d), j.mensagem);
        } catch (e) { trava(ok, false); hint(dlg, e.message); }
      });
    },

    // _EtiquetasDialog: catálogo marcável (bolinha da cor), filtro, 'Salvar' manda o CONJUNTO inteiro (labels_sync substitui)
    async etiquetas(d) {
      const dlg = dialogo(d, 'etiquetas'); if (!dlg) return;
      const busca = q(dlg.caixa, '[data-etq-busca]'), lista = q(dlg.caixa, '[data-etq-lista]'), ok = q(dlg.caixa, '[data-conf="etiquetas"]');
      const atuais = Array.from(d.querySelectorAll('.det-chip[data-id]')).map((c) => c.dataset.id);   // o card já sabe as da OS
      const marcadas = new Set(atuais);
      let labels = [];
      function pintar() {
        const txt = (busca.value || '').trim().toLowerCase();
        lista.innerHTML = labels.filter((l) => (l.description || '').trim() && (!txt || l.description.toLowerCase().includes(txt)))
          .map((l) => '<label class="acoes-etq"><input type="checkbox" value="' + esc(l.id) + '"' + (marcadas.has(String(l.id)) ? ' checked' : '') + '>'
            + '<i style="background:' + esc(l.color) + '"></i><span>' + esc(l.description) + '</span></label>').join('');
      }
      try {
        const j = await pedir('/os/api/os/' + d.dataset.wid + '/etiquetas?atuais=' + encodeURIComponent(atuais.join(',')));
        labels = j.catalogo || []; (j.atuais || []).forEach((i) => marcadas.add(String(i)));
        busca.placeholder = labels.length ? 'Filtrar etiquetas…' : 'nenhuma etiqueta no catálogo'; pintar();
      } catch (e) { busca.placeholder = 'etiquetas não carregaram — relogue'; hint(dlg, e.message); }
      busca.addEventListener('input', pintar);
      lista.addEventListener('change', (e) => { const c = e.target; if (c.type !== 'checkbox') return; if (c.checked) marcadas.add(c.value); else marcadas.delete(c.value); });
      ok.addEventListener('click', async () => {
        const ids = Array.from(marcadas).filter(Boolean).map(numero);
        if (!ids.length) { hint(dlg, 'Marque ao menos uma etiqueta (ou Cancelar).'); return; }
        trava(ok, true); hint(dlg, 'salvando…');
        try { await pedir('/os/api/os/' + d.dataset.wid + '/etiquetas', {ids}); alterou(d); dlg.fechar(); await recarregar(d, urlCard(d)); }
        catch (e) { trava(ok, false); hint(dlg, '⚠ ' + e.message); }
      });
    },

    // NOTAS inline (Editar / Salvar / Cancelar): o editor nasce com a observação atual; nada mudou = não gastar uma escrita
    'nota-editar'(d) { const ta = q(d, '[data-nota-editor]'); ta.value = ta.defaultValue; modoNota(d, true); ta.focus(); },
    'nota-cancelar'(d) { modoNota(d, false); },
    async 'nota-salvar'(d, btn) {
      const ta = q(d, '[data-nota-editor]'); const novo = ta.value.trim();
      if (novo === ta.defaultValue.trim()) { modoNota(d, false); return; }
      trava(btn, true, 'salvando…');
      try { await pedir('/os/api/os/' + d.dataset.wid + '/nota', {nota: novo, status: d.dataset.status}); alterou(d); await recarregar(d, urlCard(d)); }
      catch (e) { trava(btn, false, 'Salvar'); mensagem(d, 'Não consegui salvar a observação. ' + e.message, true); }
    },

    // _ConcluirDialog (já montado pelo servidor: %, pendentes, data de fim) → api.concluir_os_checado; depois o card em 'Concluída'
    concluir(d) {
      const dlg = dialogo(d, 'concluir'); if (!dlg) return;
      const ok = q(dlg.caixa, '[data-conf="concluir"]');
      // fazer a tarefa ANTES de fechar: o dialogo de concluir sai de cena e o da execucao entra
      dlg.caixa.querySelectorAll('[data-fazer]').forEach((b) => {
        b.addEventListener('click', () => { dlg.fechar(); ACOES.executar(d, b.dataset.fazer, b.dataset.fazerTitulo); });
      });
      ok.addEventListener('click', async () => {
        trava(ok, true, 'concluindo…');
        try {
          const j = await pedir('/os/api/os/' + d.dataset.wid + '/concluir', {folio: d.dataset.folio});
          alterou(d); dlg.fechar();
          if (d.hasAttribute('data-no-lugar')) { relerPagina(d, j.mensagem, !!j.aviso); return; }
          await recarregar(d, urlCard(d, 'Concluída'), j.mensagem, !!j.aviso);
        } catch (e) { trava(ok, false, 'Concluir OS'); hint(dlg, 'Erro ao concluir OS: ' + e.message); }
      });
    },

    // Enviar para verificação (06/11/2026): o diálogo, como o do Concluir, oferece fazer a tarefa antes; o status 2 pela
    // rota /verificacao, que lê o status antes e depois
    verificacao(d) {
      const dlg = dialogo(d, 'verificacao'); if (!dlg) return;
      const ok = q(dlg.caixa, '[data-conf="verificacao"]');
      dlg.caixa.querySelectorAll('[data-fazer]').forEach((b) => {
        b.addEventListener('click', () => { dlg.fechar(); ACOES.executar(d, b.dataset.fazer, b.dataset.fazerTitulo); });
      });
      ok.addEventListener('click', async () => {
        trava(ok, true, 'enviando…');
        try {
          const j = await pedir('/os/api/os/' + d.dataset.wid + '/verificacao', {folio: d.dataset.folio});
          alterou(d); dlg.fechar();
          if (d.hasAttribute('data-no-lugar')) { relerPagina(d, j.mensagem); return; }
          await recarregar(d, urlCard(d, 'Em Verificação'), j.mensagem);
        } catch (e) { trava(ok, false, 'Enviar para verificação'); hint(dlg, 'Não foi possível enviar: ' + e.message); }
      });
    },

    // Retornar para responsável (10/11/2026): a OS volta de Em Verificação para Em Processo pela rota /retornar, que
    // confere de novo quem pode e lê o status antes e depois
    retornar(d) {
      const dlg = dialogo(d, 'retornar'); if (!dlg) return;
      const ok = q(dlg.caixa, '[data-conf="retornar"]');
      ok.addEventListener('click', async () => {
        trava(ok, true, 'retornando…');
        try {
          const j = await pedir('/os/api/os/' + d.dataset.wid + '/retornar', {folio: d.dataset.folio});
          alterou(d); dlg.fechar();
          if (d.hasAttribute('data-no-lugar')) { relerPagina(d, j.mensagem); return; }
          await recarregar(d, urlCard(d, 'Em Processo'), j.mensagem);
        } catch (e) { trava(ok, false, 'Retornar para responsável'); hint(dlg, 'Não foi possível retornar: ' + e.message); }
      });
    },

    // Fazer a tarefa (Levi, 21/09): preenche o checklist e lanca o registro de execucao sem sair
    // da web. O protocolo e o da tela do Fracttal, capturado em 21/09 na OS 38299179: gravar os
    // valores, validar a seguranca, inserir a execucao e reler para confirmar.
    async executar(d, tid, titulo) {
      const dlg = dialogo(d, 'executar'); if (!dlg) return;
      const caixa = q(dlg.caixa, '[data-exec-campos]'), ok = q(dlg.caixa, '[data-conf="executar"]');
      const ini = q(dlg.caixa, '[data-exec-ini]'), fim = q(dlg.caixa, '[data-exec-fim]');
      if (titulo) q(dlg.caixa, '[data-exec-titulo]').textContent = 'Fazer a tarefa — ' + titulo;
      // o fim ja vem AGORA e o inicio em branco: e a unica informacao que so a pessoa tem, e
      // deixa-la adivinhar o formato foi o que produziu OS sem data de fim antes.
      fim.value = agoraLocal();
      trava(ok, true, 'carregando…');
      let campos = [];
      try {
        const j = await pedir('/os/api/os/' + d.dataset.wid + '/tarefa/' + tid + '/checklist');
        campos = j.campos || [];
      } catch (e) { caixa.innerHTML = '<p class="os-erro">Não consegui carregar o checklist: ' + esc(e.message) + '</p>'; trava(ok, false, 'Salvar e registrar'); return; }
      trava(ok, false, 'Salvar e registrar');
      if (!campos.length) { caixa.innerHTML = '<p class="det-ajuda">Esta tarefa não tem subtarefas — dá para lançar só o registro.</p>'; }
      else caixa.innerHTML = campos.map((c) => campoHTML(c)).join('');
      ok.addEventListener('click', async () => {
        const valores = {};
        caixa.querySelectorAll('[data-fid]').forEach((el) => { const v = (el.value || '').trim(); if (v) valores[el.dataset.fid] = v; });
        if (!ini.value) { hint(dlg, 'Informe a data e a hora de início da execução.'); return; }
        trava(ok, true, 'gravando…');
        try {
          const j = await pedir('/os/api/os/' + d.dataset.wid + '/tarefa/' + tid + '/executar',
            {valores, inicio: ini.value, fim: fim.value, nota: q(dlg.caixa, '[data-exec-nota]').value});
          alterou(d); dlg.fechar();
          if (d.hasAttribute('data-no-lugar')) { relerPagina(d, j.mensagem, !!j.aviso); return; }
          await recarregar(d, urlCard(d), j.mensagem, !!j.aviso);
        } catch (e) { trava(ok, false, 'Salvar e registrar'); hint(dlg, 'Não consegui registrar: ' + e.message); }
      });
    },

    // CancelarOSDialog: motivos do Fracttal, observação opcional, a pergunta do app antes de gravar (api.cancel_os)
    async cancelar(d) {
      const dlg = dialogo(d, 'cancelar'); if (!dlg) return;
      const sel = q(dlg.caixa, '[data-canc-motivo]'), obs = q(dlg.caixa, '[data-canc-obs]'), ok = q(dlg.caixa, '[data-conf="cancelar"]');
      hint(dlg, 'carregando motivos…');
      try {
        const j = await pedir('/os/api/os/' + d.dataset.wid + '/cancel-motivos');
        const ms = j.motivos || [];
        sel.innerHTML = '<option value="">— selecione o motivo —</option>' + ms.map((m) => '<option value="' + esc(m.id) + '">' + esc(m.description || '?') + '</option>').join('');
        hint(dlg, ms.length ? '' : '⚠ nenhum motivo retornado pelo Fracttal');
      } catch (e) { hint(dlg, '⚠ ' + e.message); }
      sel.addEventListener('change', () => { ok.disabled = !sel.value; });
      ok.addEventListener('click', async () => {
        if (!sel.value) { hint(dlg, 'Escolha o motivo do cancelamento.'); return; }
        const folio = d.dataset.folio || d.dataset.wid;
        if (!confirm('Confirma o cancelamento da OS ' + folio + '?\nIsto muda o status dela no Fracttal.')) return;
        trava(ok, true); hint(dlg, 'cancelando no Fracttal…');
        try {
          const j = await pedir('/os/api/os/' + d.dataset.wid + '/cancelar', {id_status_custom: numero(sel.value), note: obs.value.trim(), folio});
          alterou(d); dlg.fechar();
          if (d.hasAttribute('data-no-lugar')) { relerPagina(d, j.mensagem); return; }
          await recarregar(d, urlCard(d, 'Cancelada'), j.mensagem);
        } catch (e) { trava(ok, false); hint(dlg, 'Não foi possível cancelar: ' + e.message); }
      });
    },

    // O Fazer OS (11/11/2026, Levi: "eles devem preencher com o rigor da OS então a pessoa vai expandir as subtarefas,
    // responder, se tiver anexo obrigatório deve ter a opção de anexar na OS ... e de anexar na subtarefa também"; "editar
    // a ocorrência com a data de início e data fim da OS e mandar para 'Em verificação'"). As respostas de cada tarefa vão
    // pelo /respostas (as fotos que a subtarefa tem vão junto, no servidor); a foto da subtarefa, pelo /item/<id>/anexo; o
    // envio, pelo /fazer, que confere de novo o que falta
    async fazer(d) {
      const dlg = dialogo(d, 'fazer'); if (!dlg) return;
      const corpo = q(dlg.caixa, '[data-fazer-corpo]'), ok = q(dlg.caixa, '[data-conf="fazer"]');
      const salvar = q(dlg.caixa, '[data-fazer-salvar]'), ini = q(dlg.caixa, '[data-fazer-ini]'), fim = q(dlg.caixa, '[data-fazer-fim]');
      const base = '/os/api/os/' + d.dataset.wid;
      fim.value = agoraLocal();
      let tarefas = [];
      try {
        tarefas = (await pedir(base + '/tarefas', undefined, 'Abrindo as tarefas…')).tarefas || [];
        const cks = await Promise.all(tarefas.map((t) => pedir(base + '/tarefa/' + t.id + '/checklist', undefined, 'Abrindo as subtarefas…')));
        tarefas.forEach((t, i) => { t.campos = cks[i].campos || []; });
      } catch (e) { corpo.innerHTML = '<div class="acoes-hint">' + esc('Não consegui abrir as tarefas: ' + e.message) + '</div>'; return; }
      const inis = tarefas.map((t) => (t.execucao || {}).inicio).filter(Boolean).sort();
      if (inis.length) ini.value = String(inis[0]).slice(0, 16);
      corpo.innerHTML = tarefas.map((t) => fzTarefaHTML(t, tarefas.length > 1)).join('') || '<div class="acoes-hint">A OS não tem tarefas.</div>';
      const conta = () => fzConta(dlg, ok, ini, fim);
      corpo.addEventListener('click', (e) => {
        const op = e.target.closest('.fz-op');
        if (op) {
          const g = op.closest('[data-fid]');
          g.querySelectorAll('.fz-op').forEach((x) => x.classList.toggle('on', x === op && !op.classList.contains('on')));
          const on = g.querySelector('.fz-op.on'); g.dataset.valor = on ? (on.dataset.v || '') : '';
          g.closest('.fz-sub').classList.add('mexida'); conta(); return;
        }
        const fb = e.target.closest('[data-fazer-foto]');
        if (fb) { fb.parentElement.querySelector('input[type=file]').click(); return; }
        const ab = e.target.closest('[data-fazer-anexo-os]');
        if (ab) ab.parentElement.querySelector('input[type=file]').click();
      });
      corpo.addEventListener('input', (e) => { const s = e.target.closest('.fz-sub'); if (s) s.classList.add('mexida'); conta(); });
      corpo.addEventListener('change', async (e) => {
        const inp = e.target; if (!(inp.matches && inp.matches('input[type=file]')) || !inp.files.length) return;
        const f = inp.files[0]; inp.value = '';
        const sub = inp.closest('.fz-sub'), tarefa = inp.closest('.fz-tarefa');
        const fd = new FormData(); fd.append('anexos', f, f.name);
        let url;
        if (sub) { url = base + '/tarefa/' + tarefa.dataset.tid + '/item/' + sub.dataset.fid + '/anexo'; fd.append('valor', fzValor(sub)); }
        else { url = base + '/anexos'; fd.append('folio', d.dataset.folio || ''); fd.append('tarefa', tarefa.dataset.tid); }
        const alvo = sub || tarefa;
        const st = inp.parentElement.querySelector('[data-fazer-fotos]');
        st.textContent = 'enviando ' + f.name + '…'; st.classList.remove('ruim');
        try {
          const r = await OsCarga.buscar(url, {method: 'POST', credentials: 'same-origin', headers: {'Accept': 'application/json'}, body: fd}, 'Enviando para o Fracttal…');
          let j = null; try { j = await r.json(); } catch (x) { j = null; }
          if (!r.ok) throw new Error(apiErro(j, r));
          if (sub) { sub.dataset.anexos = String(j.n_anexos || (Number(sub.dataset.anexos || 0) + 1)); }
          else { tarefa.dataset.anexos = String(Number(tarefa.dataset.anexos || 0) + 1); }
          const n = Number(alvo.dataset.anexos || 0);
          st.textContent = n === 1 ? '1 anexo' : n + ' anexos'; anexosCache.delete(d); alterou(d); conta();
        } catch (x) { st.textContent = 'Não subiu: ' + x.message; st.classList.add('ruim'); }
      });
      [ini, fim].forEach((x) => x.addEventListener('input', conta));
      conta();
      const gravar = async () => {
        let n = 0;
        for (const t of corpo.querySelectorAll('.fz-tarefa')) {
          const valores = {};
          t.querySelectorAll('.fz-sub.mexida').forEach((s) => { const v = fzValor(s).trim(); if (v) valores[s.dataset.fid] = v; });
          if (!Object.keys(valores).length) continue;
          await pedir(base + '/tarefa/' + t.dataset.tid + '/respostas', {valores}, 'Gravando as respostas no Fracttal…');
          t.querySelectorAll('.fz-sub.mexida').forEach((s) => s.classList.remove('mexida'));
          n += Object.keys(valores).length;
        }
        return n;
      };
      salvar.addEventListener('click', async () => {
        trava(salvar, true, 'salvando…');
        try { const n = await gravar(); alterou(d); hint(dlg, n ? (n === 1 ? '1 resposta gravada no Fracttal.' : n + ' respostas gravadas no Fracttal.') : 'Nada novo para gravar.'); }
        catch (e) { hint(dlg, 'Não consegui gravar: ' + e.message); }
        finally { trava(salvar, false, 'Salvar respostas'); }
      });
      ok.addEventListener('click', async () => {
        trava(ok, true, 'enviando…');
        try {
          await gravar();
          const j = await pedir(base + '/fazer', {inicio: ini.value, fim: fim.value, folio: d.dataset.folio}, 'Enviando para verificação…');
          alterou(d); dlg.fechar();
          if (d.hasAttribute('data-no-lugar')) { relerPagina(d, j.mensagem); return; }
          await recarregar(d, urlCard(d, 'Em Verificação'), j.mensagem);
        } catch (e) { trava(ok, false, 'Enviar para verificação'); conta(); hint(dlg, 'Não foi possível enviar: ' + e.message); }
      });
    },

    // FluxoDialog: só a cadeia; clicar num nó abre o card daquela OS no lugar deste (como o app fecha um e abre o outro)
    async fluxo(d) {
      const dlg = dialogo(d, 'fluxo'); if (!dlg) return;
      const corpo = q(dlg.caixa, '[data-fluxo-corpo]');
      try { pintarFluxo(dlg, await pedir('/os/api/os/' + d.dataset.wid + '/fluxo')); }
      catch (e) { corpo.innerHTML = '<div class="acoes-hint i">' + esc('não consegui montar o fluxo: ' + e.message.slice(0, 140)) + '</div>'; }
      corpo.addEventListener('click', async (e) => {
        const no = e.target.closest('a.acoes-no'); if (!no) return;
        e.preventDefault(); dlg.fechar();
        await recarregar(d, no.getAttribute('href') + '&parcial=1');          // o href já traz ?status=
      });
    },

    // Incluir anexo (Levi, 06/11/2026): o seletor de arquivos e o envio para a 1ª tarefa da OS, com as regras dos anexos
    // da Solicitação de Engenharia; o servidor relê a OS e diz o que subiu e o que não (o Fracttal aceita calado)
    'anexo-incluir'(d, b) {
      const inp = q(d, '[data-anx-arquivos]'); if (!inp) return;
      inp.value = '';
      inp.onchange = () => { const fs = Array.from(inp.files || []); if (fs.length) enviarAnexos(d, fs); };
      inp.click();
    },

    'anexos-sub'(d) { return abrirAnexos(d, 'sub', 'Anexos das subtarefas', 'Sem anexos nas subtarefas.'); },
    'anexos-tarefa'(d, b) { return abrirAnexos(d, 'sub', 'Anexos · ' + (b.dataset.ativo || 'tarefa'), 'Sem anexos nesta tarefa.', b.dataset.tarefaId); },
    'anexos-os'(d) { return abrirAnexos(d, 'os', 'Anexos da OS', 'Sem anexos nesta OS.'); }
  };

  function pintarFluxo(dlg, j) {
    q(dlg.caixa, '[data-fluxo-sub]').textContent = j.subtitulo || '—';
    const corpo = q(dlg.caixa, '[data-fluxo-corpo]'); corpo.innerHTML = '';
    const cadeia = j.cadeia || [];
    const faixa = document.createElement('div'); faixa.className = 'acoes-cadeia';
    cadeia.forEach((no, i) => {
      faixa.insertAdjacentHTML('beforeend',
        '<a class="acoes-no' + (no.atual ? ' atual' : '') + '" href="' + esc(no.href) + '">'
        + '<div class="acoes-no-topo"><b>' + esc(no.folio || '—') + '</b>' + (no.atual ? '<span class="acoes-atual">ATUAL</span>' : '') + '</div>'
        + '<div class="acoes-no-tipo">' + esc(no.tipo_tarefa || '—') + '</div><div class="acoes-no-desc">' + esc(no.descricao || '') + '</div>'
        + '<div class="acoes-no-base"><i style="background:' + esc(no.cor) + '"></i><span style="color:' + esc(no.cor) + '">' + esc(no.status || '—') + '</span><small>' + esc(no.data || '') + '</small></div></a>');
      if (i < cadeia.length - 1) faixa.insertAdjacentHTML('beforeend', '<div class="acoes-seta"><span>gerou</span></div>');
    });
    corpo.appendChild(faixa);
    if (cadeia.length <= 1) corpo.insertAdjacentHTML('beforeend', '<div class="acoes-hint i centro">' + esc(j.aviso || 'Esta OS não tem outra ligada a ela — nem como pai, nem como filha.') + '</div>');
  }

  async function abrirAnexos(d, chave, titulo, vazio, tarefa) {
    const dlg = dialogo(d, 'anexos'); if (!dlg) return;
    dlg.d = d;                                           // o X do Editar exclui na OS deste card
    q(dlg.caixa, '[data-anx-titulo]').textContent = titulo;
    const corpo = q(dlg.caixa, '[data-anx-corpo]');
    try {
      let j = anexosCache.get(d);
      if (!j) { j = await pedir('/os/api/os/' + d.dataset.wid + '/anexos-lista', undefined, 'Abrindo os anexos…'); anexosCache.set(d, j); }
      const ativos = mapaAtivos(d);
      let itens = (j[chave] || {itens: []}).itens || [];
      if (tarefa) itens = itens.filter((x) => String(x.tarefa) === String(tarefa));
      itens = itens.map((x) => comAtivo(x, ativos));
      pintarAnexos(dlg, itens, vazio);
      const n = tarefa ? itens.filter((x) => x.tipo !== 'nota' || (x.texto || '').trim()).length : (j[chave] || {}).baixar || 0;
      baixarTodos(d, dlg, chave, n, tarefa, ativos);
    } catch (e) { corpo.innerHTML = '<div class="acoes-hint">' + esc('não consegui carregar os anexos: ' + e.message) + '</div>'; }
  }

  // A OS de vários ativos (Levi, 04/11/2026: "o download sai com o nome do ativo!"): {id da tarefa: ativo}, lido das
  // tarefas do card; cada anexo diz de qual ativo é, e o arquivo baixado começa pelo nome dele
  function mapaAtivos(d) {
    const m = {};
    d.querySelectorAll('details.det-tarefa[data-ativo]').forEach((t) => { const id = t.getAttribute('data-tarefa'); if (id) m[id] = t.getAttribute('data-ativo'); });
    return m;
  }
  function comAtivo(x, ativos) {
    const a = x.tarefa != null ? ativos[String(x.tarefa)] : '';
    if (!a) return x;
    const nome = a + ' - ' + x.nome;
    return Object.assign({}, x, {legenda: a + ' · ' + (x.legenda || x.nome || ''), quem: a, nome: nome,
      baixar: x.baixar ? x.baixar.replace(/([?&]nome=)[^&]*/, '$1' + encodeURIComponent(nome)) : x.baixar});
  }

  // "Baixar todos (N)" — o do app (steps/galeria.py, steps/documentos.py). Lá grava numa pasta; aqui o servidor junta o
  // card num .zip com a MESMA arrumação (uma pasta por subtarefa, as notas em .txt) e diz o que não veio. N conta o que
  // vai no .zip: arquivo, ou nota com texto.
  function baixarTodos(d, dlg, chave, n, tarefa, ativos) {
    const b = q(dlg.caixa, '[data-baixar-todos]'); if (!b) return;
    const rot = 'Baixar todos (' + n + ')';
    b.textContent = rot; b.hidden = !n;
    b.onclick = async () => {
      if (b.disabled) return;
      trava(b, true, 'Juntando…'); msgAnexos(dlg, '');
      try {
        const j = await pedir('/os/api/os/' + d.dataset.wid + '/anexos-zip',
                              {grupo: chave, folio: d.dataset.folio || '', ativos: ativos || {}, tarefa: tarefa || ''},
                              'Juntando os anexos num .zip…');
        const a = document.createElement('a');              // o navegador baixa (o arquivo não passa pela memória da tela)
        a.href = j.url; a.download = j.nome || '';
        document.body.appendChild(a); a.click(); a.remove();
        const falhas = j.falhas || [], total = (j.arquivos || 0) + (j.notas || 0);
        let txt = total + ' anexo(s) em "' + j.nome + '"';
        if (falhas.length) {
          txt += ' · ' + falhas.length + (falhas.length === 1 ? ' não veio' : ' não vieram') + ' (a URL do Fracttal expira; abrir os anexos de novo renova): '
            + falhas.slice(0, 4).map((f) => f.nome.split('/').pop()).join(', ') + (falhas.length > 4 ? ' e mais ' + (falhas.length - 4) : '')
            + ' — a lista está no _nao_vieram.txt';
        }
        msgAnexos(dlg, txt, falhas.length > 0);
      } catch (e) { msgAnexos(dlg, 'Não consegui baixar: ' + e.message, true); }
      finally { trava(b, false, rot); }
    };
  }
  function msgAnexos(dlg, texto, ruim) {
    const m = q(dlg.caixa, '[data-anx-msg]'); if (!m) return;
    m.hidden = !texto; m.textContent = texto || ''; m.classList.toggle('ruim', !!ruim);
  }

  // ── o Fazer OS: o HTML de cada tarefa e de cada subtarefa, o valor e a conta do que falta ──
  const FZ_TIPO = {verif: 'Verificação', simnao: 'Sim/Não', lista: 'Lista', num: 'Número', texto: 'Texto'};
  function fzTarefaHTML(t, varias) {
    const cab = varias ? '<div class="fz-t-cab"><b>' + esc(t.titulo || t.ativo || ('Tarefa ' + t.n)) + '</b>' + (t.ativo && t.ativo !== t.titulo ? '<span>' + esc(t.ativo) + '</span>' : '') + '</div>' : '';
    return '<section class="fz-tarefa" data-tid="' + esc(t.id) + '" data-anexos="0">' + cab
      + (t.campos.length ? t.campos.map(fzSubHTML).join('') : '<div class="acoes-hint">Esta tarefa não tem subtarefas.</div>')
      + '<div class="fz-anexo-os"><button type="button" class="det-b ghost acoes-mini" data-fazer-anexo-os>Anexar na OS</button>'
      + '<input type="file" hidden accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.txt"><span class="fz-fotos" data-fazer-fotos></span></div></section>';
  }
  function fzSubHTML(c) {
    const v = c.valor == null ? '' : String(c.valor), fid = esc(c.id_form_item);
    let ctrl;
    if ((c.opcoes || []).length && (c.tipo_nome !== 'lista' || c.opcoes.length <= 6)) {
      ctrl = '<div class="fz-opcoes" data-fid="' + fid + '" data-valor="' + esc(v) + '">' + c.opcoes.map((o) =>
        '<button type="button" class="fz-op' + (String(o.valor) === v ? ' on' : '') + '" data-v="' + esc(o.valor) + '">' + esc(o.rotulo) + '</button>').join('') + '</div>';
    } else if ((c.opcoes || []).length) {
      ctrl = '<select class="fz-campo" data-fid="' + fid + '"><option value="">— selecione —</option>' + c.opcoes.map((o) =>
        '<option value="' + esc(o.valor) + '"' + (String(o.valor) === v ? ' selected' : '') + '>' + esc(o.rotulo) + '</option>').join('') + '</select>';
    } else if (c.tipo_nome === 'num') {
      ctrl = '<input class="fz-campo" type="number" step="any" inputmode="decimal" data-fid="' + fid + '" value="' + esc(v) + '">';
    } else {
      ctrl = '<textarea class="fz-campo acoes-ta" rows="2" data-fid="' + fid + '">' + esc(v) + '</textarea>';
    }
    const n = Number(c.n_anexos || 0);
    return '<div class="fz-sub" data-fid="' + fid + '" data-anexos="' + n + '" data-req="' + (c.obrigatorio ? 1 : 0) + '" data-foto="' + (c.anexo_obrigatorio ? 1 : 0) + '">'
      + '<div class="fz-sub-cab"><span class="fz-sub-t">' + esc(c.descricao) + '</span><span class="fz-selos">'
      + (c.obrigatorio ? '<span class="fz-selo req">obrigatória</span>' : '') + (c.anexo_obrigatorio ? '<span class="fz-selo foto">foto obrigatória</span>' : '')
      + '<span class="fz-selo">' + esc(FZ_TIPO[c.tipo_nome] || 'Texto') + '</span></span></div>' + ctrl
      + '<div class="fz-foto-l"><button type="button" class="det-b ghost acoes-mini" data-fazer-foto>Anexar foto</button>'
      + '<input type="file" hidden accept="image/*,.pdf" capture="environment"><span class="fz-fotos" data-fazer-fotos>' + (n ? (n === 1 ? '1 anexo' : n + ' anexos') : '') + '</span></div></div>';
  }
  function fzValor(sub) {
    const g = sub.querySelector('[data-fid]'); if (!g) return '';
    return g.classList.contains('fz-opcoes') ? (g.dataset.valor || '') : (g.value || '');
  }
  function fzConta(dlg, ok, ini, fim) {
    let total = 0, feitas = 0;
    dlg.caixa.querySelectorAll('.fz-sub').forEach((s) => {
      const resp = !!fzValor(s).trim(), foto = Number(s.dataset.anexos || 0) > 0;
      s.classList.toggle('ok', resp && (s.dataset.foto !== '1' || foto));
      if (s.dataset.req === '1') { total++; if (resp) feitas++; }
      if (s.dataset.foto === '1') { total++; if (foto) feitas++; }
    });
    const pct = total ? Math.round(feitas * 100 / total) : 100;
    q(dlg.caixa, '[data-fazer-barra]').style.width = pct + '%';
    q(dlg.caixa, '[data-fazer-conta]').textContent = total ? feitas + ' de ' + total + ' obrigatórias' : 'sem obrigatórias';
    const pronta = feitas === total && ini.value && fim.value && fim.value >= ini.value;
    ok.disabled = !pronta;
    ok.title = pronta ? '' : (feitas < total ? 'Faltam ' + (total - feitas) + ' obrigatória(s)' : 'Informe o início e o fim da OS');
  }

  // GaleriaDialog + DocumentosDialog: fotos e notas de texto juntas (saem da MESMA subtarefa), arquivos com Abrir/Baixar
  function pintarAnexos(dlg, itens, vazio) {
    const imgs = itens.filter((x) => x.tipo === 'imagem'), docs = itens.filter((x) => x.tipo === 'documento'), notas = itens.filter((x) => x.tipo === 'nota');
    q(dlg.caixa, '[data-anx-sub]').textContent = (imgs.length + docs.length) + ' arquivo(s) · ' + notas.length + ' nota(s) de texto';
    const corpo = q(dlg.caixa, '[data-anx-corpo]'); corpo.innerHTML = '';
    corpo._fotos = imgs;                                 // o carrossel anda por elas, na ordem da grade
    if (!itens.length) { corpo.innerHTML = '<div class="acoes-hint">' + esc(vazio) + '</div>'; return; }
    if (imgs.length || notas.length) {
      corpo.insertAdjacentHTML('beforeend', '<div class="acoes-hint">Clique numa foto para ver em tamanho cheio e passar pelas outras (setas do teclado também) · clique numa nota para ler o texto.</div>');
      corpo.insertAdjacentHTML('beforeend', '<div class="acoes-fotos">'
        + imgs.map((x, k) => '<figure class="acoes-foto"' + xAttr(x) + '>' + xBotao(x) + '<figcaption title="' + esc(x.legenda) + '">' + esc(x.legenda) + '</figcaption>'
          + '<a class="img" href="' + esc(x.url) + '" target="_blank" rel="noopener" data-foto="' + k + '"><img src="' + esc(x.url) + '" alt="" loading="lazy"></a>'
          + (x.baixar ? '<a class="acoes-baixar" href="' + esc(x.baixar) + '" download="' + esc(x.nome) + '" data-baixar-arq>Baixar</a>' : '') + '</figure>').join('')
        + notas.map((x) => '<details class="acoes-nota"><summary>' + esc(x.legenda || 'nota') + '</summary><pre>' + esc(x.texto || '(nota vazia)') + '</pre></details>').join('')
        + '</div>');
    }
    if (docs.length) {
      corpo.insertAdjacentHTML('beforeend', '<div class="acoes-docs">' + docs.map((x) => {
        const sub = [x.quem, (x.legenda && x.legenda !== x.nome) ? x.legenda : ''].filter(Boolean).join(' · ');
        return '<div class="acoes-doc"' + xAttr(x) + '>' + xBotao(x) + '<span class="acoes-ext">' + esc(x.ext || 'ARQ') + '</span><div class="acoes-doc-t"><div>' + esc(x.nome) + '</div>'
          + (sub ? '<small>' + esc(sub) + '</small>' : '') + '</div>'
          + '<a class="det-b ghost acoes-mini" href="' + esc(x.url) + '" target="_blank" rel="noopener">Abrir</a>'
          + (x.baixar ? '<a class="det-b ghost acoes-mini" href="' + esc(x.baixar) + '" download="' + esc(x.nome) + '" data-baixar-arq>Baixar</a>' : '') + '</div>';
      }).join('') + '</div>');
    }
    corpo.onclick = (e) => {
      const x = e.target.closest('[data-anx-x]'); if (x) { excluirAnexo(e, dlg, x); return; }
      const a = e.target.closest('a[data-baixar-arq]'); if (a) baixarArquivo(e, dlg, a);
    };
    // o Editar (11/11/2026): mostra o X nos anexos que se podem excluir
    const ed = q(dlg.caixa, '[data-anx-editar]');
    if (ed) {
      ed.hidden = !itens.some((x) => x.excluir);
      ed.onclick = () => { const on = dlg.caixa.classList.toggle('editando'); ed.textContent = on ? 'Concluir edição' : 'Editar'; };
    }
  }
  const xAttr = (x) => x.excluir ? ' data-excluir="' + esc(JSON.stringify(x.excluir)) + '"' : '';
  const xBotao = (x) => x.excluir ? '<button type="button" class="acoes-x" data-anx-x title="Excluir ' + esc(x.nome) + '" aria-label="Excluir ' + esc(x.nome) + '">×</button>' : '';
  // o X: pergunta, exclui no Fracttal e tira o anexo da tela (a contagem do card é relida)
  async function excluirAnexo(e, dlg, b) {
    e.preventDefault(); e.stopPropagation();
    const box = b.closest('[data-excluir]'); if (!box || !dlg.d) return;
    const nome = (box.querySelector('figcaption, .acoes-doc-t div') || {}).textContent || 'este anexo';
    if (!confirm('Excluir "' + nome + '" da OS no Fracttal?\nIsto não se desfaz.')) return;
    b.disabled = true; msgAnexos(dlg, 'Excluindo…');
    try {
      const j = await pedir('/os/api/os/' + dlg.d.dataset.wid + '/anexo/excluir', JSON.parse(box.dataset.excluir), 'Excluindo o anexo no Fracttal…');
      box.remove(); anexosCache.delete(dlg.d); alterou(dlg.d); contagem(dlg.d); msgAnexos(dlg, j.mensagem || 'Anexo excluído.');
    } catch (x) { b.disabled = false; msgAnexos(dlg, 'Não consegui excluir: ' + x.message, true); }
  }

  // O BAIXAR DE UM ANEXO (09/11/2026, OS 8159: o Baixar salvava o erro do servidor como um arquivo .json). Pela rota do
  // Nexus, o arquivo vem por fetch e só é salvo quando veio o arquivo; o erro vira a frase no rodapé dos anexos. O link
  // de fora (a pré-assinada do S3) segue como sempre: o navegador baixa direto
  async function baixarArquivo(e, dlg, a) {
    if (a.origin !== location.origin) return;
    e.preventDefault();
    const nome = a.getAttribute('download') || 'anexo';
    msgAnexos(dlg, 'Baixando "' + nome + '"…');
    try {
      const r = await fetch(a.href, {credentials: 'same-origin', headers: {'Accept': 'application/json, */*'}});
      const tipo = r.headers.get('Content-Type') || '';
      if (!r.ok || tipo.indexOf('json') >= 0) {
        const j = await r.json().catch(() => ({}));
        msgAnexos(dlg, 'Não consegui baixar "' + nome + '": ' + (j.erro || ('o servidor respondeu ' + r.status + '.')), true);
        return;
      }
      const u = URL.createObjectURL(await r.blob());
      const t = document.createElement('a'); t.href = u; t.download = nome;
      document.body.appendChild(t); t.click(); t.remove();
      setTimeout(() => URL.revokeObjectURL(u), 60000);
      msgAnexos(dlg, '');
    } catch (err) { msgAnexos(dlg, 'Não consegui baixar "' + nome + '": ' + err.message, true); }
  }

  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-acao]'); if (!b || b.disabled) return;
    const d = card(b); if (!d) return;
    const fn = ACOES[b.dataset.acao]; if (!fn) return;
    e.preventDefault();
    Promise.resolve(fn(d, b)).catch((err) => mensagem(d, String((err && err.message) || err), true));
  });
  // ── o PDF da OS (19/10/2026: a seta de cada OS na cadeia do chamado) ──
  // Como o "Baixar todos": o POST monta o PDF no servidor (as fotos vêm do S3) com o círculo de carga, e o arquivo baixa
  // pelo link que ele devolve. O aviso (foto que não veio, erro) vai para o [data-pdf-msg] da caixa, nunca em alert().
  document.addEventListener('click', async (e) => {
    const b = e.target.closest('[data-os-pdf]'); if (!b) return;
    e.preventDefault();
    if (b.getAttribute('aria-busy') === 'true') return;                 // o 2º clique espera o 1º
    const caixa = b.closest('[data-pdf-caixa]') || document;
    const msg = caixa.querySelector('[data-pdf-msg]');
    const dizer = (texto, ruim) => {
      if (!msg) return;
      msg.hidden = !texto; msg.textContent = texto || ''; msg.classList.toggle('ruim', !!ruim); msg.classList.toggle('ok', !ruim);
    };
    const folio = b.getAttribute('data-os-pdf');
    b.setAttribute('aria-busy', 'true'); dizer('');
    try {
      const j = await pedir('/os/api/os/pdf', {folio: folio, wid: b.getAttribute('data-wid') || ''}, 'Montando o PDF da OS ' + folio + '…');
      const a = document.createElement('a');
      a.href = j.url; a.download = j.nome || '';
      document.body.appendChild(a); a.click(); a.remove();
      dizer(j.falhas ? ('PDF da OS ' + folio + ' baixado; ' + j.falhas + ' foto(s) não vieram do Fracttal.') : '', !!j.falhas);
    } catch (err) {
      dizer('Não consegui montar o PDF da OS ' + folio + ': ' + err.message, true);
    } finally {
      b.removeAttribute('aria-busy');
    }
  });

  document.addEventListener('keydown', (e) => {          // os cards de anexos são divs com role=button: Enter/Espaço também abrem
    if ((e.key === 'Enter' || e.key === ' ') && e.target.matches && e.target.matches('.det-anexo[data-acao]')) { e.preventDefault(); e.target.click(); }
  });

  // ── o carrossel das fotos (28/09/2026) — o ImagemViewer do app (steps/galeria.py) ──
  // Levi: "quando eu clicar na foto quero que abra uma visão das fotos ... basicamente abrindo o Carrossel das fotos".
  // Por cima da galeria (z 90 > 80): Esc fecha SÓ o carrossel e as setas andam — o `keydown` da janela, na captura,
  // chega antes do da galeria e do Histórico. Ctrl/Shift/meio-clique na miniatura seguem abrindo a foto em outra aba.
  // A conta de cada foto, pura (o teste roda no node): o `_carregar` do ImagemViewer — "N de M", Anterior desligado na
  // 1ª, Próxima na última. O Salvar vai pela rota que renova a URL (/os/api/.../anexo, baixa aqui mesmo); sem ela, a URL
  // do S3 é de outro domínio, o navegador ignora o `download` e trocaria a página — então abre em outra aba.
  function estadoVisor(fotos, i) {
    const x = fotos[i] || {}, n = fotos.length, salvar = x.baixar || x.url || '#';
    return {pos: (i + 1) + ' de ' + n, titulo: 'Foto ' + (i + 1) + ' de ' + n + (x.legenda ? ' — ' + x.legenda : ''),
      legenda: x.legenda || '', url: x.url || '', antOff: i <= 0, proxOff: i >= n - 1,
      salvar, download: x.nome || 'foto.jpg', salvarOutraAba: !/^\//.test(salvar)};
  }
  const passoVisor = (i, delta, n) => (i + delta >= 0 && i + delta < n) ? i + delta : i;   // nas pontas, fica
  const deslize = (dx) => Math.abs(dx) > 50 ? (dx < 0 ? 1 : -1) : 0;   // dedo para a esquerda = próxima; toque curto não anda

  function abrirVisor(fotos, idx, origem) {
    if (!fotos || !fotos.length) return;
    if (visor) visor.fechar();
    const el = document.createElement('div');
    el.className = 'visor'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-modal', 'true');
    el.innerHTML = '<div class="visor-palco">'
      + '<button type="button" class="visor-lado ant" data-v="ant" aria-label="Foto anterior">‹</button>'
      + '<div class="visor-img"><img alt=""><div class="visor-msg">baixando imagem…</div></div>'
      + '<button type="button" class="visor-lado prox" data-v="prox" aria-label="Próxima foto">›</button></div>'
      + '<div class="visor-cap"></div>'
      + '<div class="visor-fita">' + fotos.map((x, k) => '<button type="button" class="visor-mini" data-i="' + k + '" aria-label="Foto '
          + (k + 1) + '"><img src="' + esc(x.url) + '" alt="" loading="lazy"></button>').join('') + '</div>'
      + '<div class="visor-barra"><button type="button" class="det-b ghost" data-v="ant">‹ Anterior</button>'
      + '<span class="visor-pos"></span><button type="button" class="det-b ghost" data-v="prox">Próxima ›</button>'
      + '<span class="visor-cresce"></span>'
      + '<a class="det-b ghost" data-v="salvar">Salvar…</a>'
      + '<a class="det-b ghost" data-v="aba" target="_blank" rel="noopener">Abrir em outra aba</a>'
      + '<button type="button" class="det-b ghost" data-v="fechar">Fechar</button></div>';
    document.body.appendChild(el);
    const img = q(el, '.visor-img img'), msg = q(el, '.visor-msg'), cap = q(el, '.visor-cap'), pos = q(el, '.visor-pos');
    const salvar = q(el, '[data-v="salvar"]'), aba = q(el, '[data-v="aba"]');
    let i = idx;
    function mostrar() {
      const st = estadoVisor(fotos, i);
      el.setAttribute('aria-label', st.titulo);
      msg.textContent = 'baixando imagem…'; msg.hidden = false; img.hidden = true;
      img.onload = () => { msg.hidden = true; img.hidden = false; };
      img.onerror = () => { msg.textContent = '(não consegui baixar a imagem)'; msg.hidden = false; img.hidden = true; };
      img.src = st.url;
      if (img.complete && img.naturalWidth) { msg.hidden = true; img.hidden = false; }   // já estava em cache
      cap.textContent = st.legenda;
      pos.textContent = st.pos;
      el.querySelectorAll('[data-v="ant"]').forEach((b) => { b.disabled = st.antOff; });
      el.querySelectorAll('[data-v="prox"]').forEach((b) => { b.disabled = st.proxOff; });
      salvar.href = st.salvar; salvar.setAttribute('download', st.download); salvar.target = st.salvarOutraAba ? '_blank' : '';
      aba.href = st.url || '#';
      el.querySelectorAll('.visor-mini').forEach((b) => b.classList.toggle('on', Number(b.dataset.i) === i));
      const mini = q(el, '.visor-mini.on');
      if (mini) mini.scrollIntoView({block: 'nearest', inline: 'center'});
      [i - 1, i + 1].forEach((k) => { if (fotos[k] && fotos[k].url) new Image().src = fotos[k].url; });   // a vizinha já vem pronta
    }
    function ir(delta) { const novo = passoVisor(i, delta, fotos.length); if (novo !== i) { i = novo; mostrar(); } }
    el.addEventListener('click', (e) => {
      const b = e.target.closest('[data-v], .visor-mini');
      if (!b) {                                            // o escuro em volta da foto fecha; a foto em si, não
        if (e.target === el || e.target.classList.contains('visor-palco') || e.target.classList.contains('visor-img')) visor.fechar();
        return;
      }
      if (b.classList.contains('visor-mini')) { i = Number(b.dataset.i); mostrar(); return; }
      const v = b.dataset.v;
      if (v === 'ant') ir(-1); else if (v === 'prox') ir(1); else if (v === 'fechar') visor.fechar();
    });
    let x0 = null;                                        // o deslizar do dedo, no celular
    el.addEventListener('touchstart', (e) => { x0 = e.target.closest('.visor-fita') ? null : e.touches[0].clientX; }, {passive: true});
    el.addEventListener('touchend', (e) => {
      if (x0 === null) return;
      const passo = deslize(e.changedTouches[0].clientX - x0); x0 = null;
      if (passo) ir(passo);
    });
    visor = {ir, fechar() {                              // o foco volta para a miniatura da ÚLTIMA foto vista, não a do clique
      el.remove(); visor = null;
      const corpo = origem && origem.closest('[data-anx-corpo]');
      const alvo = (corpo && corpo.querySelector('a.img[data-foto="' + i + '"]')) || origem;
      if (alvo && alvo.focus) alvo.focus();
    }};
    mostrar();
    const foco = q(el, '.visor-barra [data-v="prox"]:not(:disabled)') || q(el, '.visor-barra [data-v="fechar"]');
    if (foco) foco.focus();
  }
  // foto que o S3 não entrega (link vencido, arquivo apagado): a miniatura diz isso em vez do ícone partido do navegador.
  // `error` não sobe pela árvore — só a captura no document pega a de uma <img> criada por innerHTML.
  document.addEventListener('error', (e) => {
    const im = e.target;
    if (!im || im.tagName !== 'IMG') return;
    const caixa = im.closest('.acoes-foto a.img, .visor-mini');
    if (caixa) caixa.classList.add('quebrada');
  }, true);
  document.addEventListener('click', (e) => {
    const a = e.target.closest && e.target.closest('.acoes-foto a.img');
    if (!a || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    const corpo = a.closest('[data-anx-corpo]');
    if (!corpo || !corpo._fotos) return;
    e.preventDefault();
    abrirVisor(corpo._fotos, Number(a.dataset.foto), a);
  });

  function arranque() { document.querySelectorAll('.det').forEach(contagem); }   // página cheia: o card já está na tela
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', arranque); else arranque();
  window.OsAcoes = {recarregar, contagem, dialogo, abrirVisor, estadoVisor, passoVisor, deslize};
})();

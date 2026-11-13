/* Comando → Caixa de entrada: as demandas entre setores (12/11/2026; comando/_demandas.html). Troca a aba, o filtro e a
   demanda aberta sem recarregar; abre a Nova demanda, filtra a pessoa e o tema pelo setor, traz as OS das usinas
   escolhidas e abre o card da OS. Sem este arquivo a lista aparece inteira e os formulários gravam do mesmo jeito. */
/* A Nova demanda (12/11/2026), de qualquer caixa desde 13/11/2026: o diálogo da Caixa de entrada e a aba "Pedir a um
   setor" da janela da conversa da usina, no prontuário (comando/_demanda_nova.html). `dlg` = a caixa em volta dos campos,
   com o `data-pessoas-url` e o `data-os-url`. Devolve {carregarPessoas}: a lista de quem recebe vem quando a caixa abre. */
window.NexusDemandaNova = function (dlg) {
  'use strict';
  // ── a Nova demanda ────────────────────────────────────────────────────────────────────────────────────────────────
  var fSetor = dlg.querySelector('[data-dm-f-setor]'), fPessoa = dlg.querySelector('[data-dm-f-pessoa]');
  var fTema = dlg.querySelector('[data-dm-f-tema]'), fPrazo = dlg.querySelector('[data-dm-f-prazo]');
  var prazoTexto = fPrazo.textContent, erroPessoas = dlg.querySelector('[data-dm-f-pessoas-erro]');
  // as opções guardadas: a lista se refaz pelo setor (esconder <option> não vale em todo navegador)
  function guardar(sel) {
    return Array.prototype.slice.call(sel.options).filter(function (o) { return o.value; }).map(function (o) { return o.cloneNode(true); });
  }
  var pessoas = [], temas = guardar(fTema), carregou = false;

  // quem recebe vem ao abrir (os nomes são do pessoal do Fracttal: a Caixa não o lê ao abrir)
  function carregarPessoas() {
    if (carregou) return;
    fetch(dlg.getAttribute('data-pessoas-url'), {credentials: 'same-origin'})
      .then(function (r) { return r.json(); })
      .then(function (j) {
        var lista = j.pessoas || [], setores = {};
        if (!j.ok || !lista.length) {
          erroPessoas.textContent = !j.ok ? 'Não li a lista de pessoas agora: feche e abra de novo em instantes.'
            : 'Ainda não há pessoas com setor no Nexus para receber demandas (Base → Acessos → Pessoas e setores).';
          erroPessoas.hidden = false;
          fSetor.innerHTML = '<option value="">Sem setores</option>';
          return;
        }
        carregou = true; erroPessoas.hidden = true;
        pessoas = lista.map(function (p) {
          setores[p.setor_id] = p.setor_nome;
          var o = document.createElement('option');
          o.value = p.hmac; o.setAttribute('data-setor', String(p.setor_id)); o.textContent = p.nome + ' · ' + p.setor_nome;
          return o;
        });
        fSetor.innerHTML = '';
        var v = document.createElement('option'); v.value = ''; v.textContent = 'Escolha o setor'; fSetor.appendChild(v);
        Object.keys(setores).sort(function (a, b) { return setores[a].localeCompare(setores[b], 'pt-BR'); }).forEach(function (sid) {
          var o = document.createElement('option'); o.value = sid; o.textContent = setores[sid]; fSetor.appendChild(o);
        });
        // sem setor escolhido, a pessoa se escolhe da lista inteira (escolher a pessoa acerta o setor)
        refazer(fPessoa, pessoas, '', 'Escolha a pessoa');
        fPessoa.options[0].textContent = 'Escolha a pessoa';
      })
      .catch(function () {
        erroPessoas.textContent = 'Não li a lista de pessoas agora: feche e abra de novo em instantes.';
        erroPessoas.hidden = false;
      });
  }
  function refazer(sel, todas, setor, vazio) {
    var antes = sel.value;
    sel.innerHTML = '';
    var lista = todas.filter(function (o) { return !setor || o.getAttribute('data-setor') === setor; });
    var v = document.createElement('option'); v.value = '';
    v.textContent = !setor ? 'Escolha o setor primeiro' : (lista.length ? vazio : 'Este setor ainda não tem ' + (sel === fTema ? 'tema' : 'pessoa'));
    sel.appendChild(v);
    lista.forEach(function (o) { sel.appendChild(o.cloneNode(true)); });
    sel.value = lista.some(function (o) { return o.value === antes; }) ? antes : '';
  }
  function prazo() {
    var o = fTema.selectedOptions && fTema.selectedOptions[0];
    var ate = o && o.getAttribute('data-ate');
    if (ate) { fPrazo.innerHTML = ''; fPrazo.appendChild(document.createTextNode('Resposta até ')); var b = document.createElement('b'); b.textContent = ate; fPrazo.appendChild(b); }
    else fPrazo.textContent = prazoTexto;
  }
  fSetor.addEventListener('change', function () {
    refazer(fPessoa, pessoas, fSetor.value, 'Escolha a pessoa');
    refazer(fTema, temas, fSetor.value, 'Escolha o tema');
    prazo();
  });
  // escolher a pessoa primeiro acerta o setor
  fPessoa.addEventListener('change', function () {
    var o = fPessoa.selectedOptions && fPessoa.selectedOptions[0];
    var s = o && o.getAttribute('data-setor');
    if (s && fSetor.value !== s) { fSetor.value = s; var p = fPessoa.value; fSetor.dispatchEvent(new Event('change')); fPessoa.value = p; }
  });
  fTema.addEventListener('change', prazo);
  refazer(fTema, temas, fSetor.value, 'Escolha o tema');

  // as usinas: a busca filtra a lista; marcar traz as OS delas
  var busca = dlg.querySelector('[data-dm-f-busca]'), caixa = dlg.querySelector('[data-dm-f-usinas]');
  var fixa = dlg.querySelector('[data-dm-f-usina-fixa]');
  var fOs = dlg.querySelector('[data-dm-f-os]'), osDica = dlg.querySelector('[data-dm-f-os-dica]'), dicaOs = osDica.textContent;
  if (busca) busca.addEventListener('input', function () {
    var q = busca.value.trim().toLowerCase();
    caixa.querySelectorAll('.dm-usina').forEach(function (u) {
      u.hidden = q && u.textContent.toLowerCase().indexOf(q) < 0 && !u.querySelector('input').checked;
    });
  });
  var pedido = 0;
  function trazerOs(ids) {
    var antes = fOs.value, n = ++pedido;
    fOs.innerHTML = '<option value="">Sem OS</option>';
    if (!ids.length) { osDica.textContent = dicaOs; return; }
    osDica.textContent = 'Buscando as OS…';
    fetch(dlg.getAttribute('data-os-url') + '?usinas=' + encodeURIComponent(ids.join(',')), {credentials: 'same-origin'})
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (n !== pedido) return;
        (j.os || []).forEach(function (o) {
          var op = document.createElement('option'); op.value = o.os; op.textContent = o.rotulo; fOs.appendChild(op);
        });
        if ((j.os || []).some(function (o) { return String(o.os) === antes; })) fOs.value = antes;
        osDica.textContent = !j.ok ? 'Não li as OS agora: dá para enviar sem OS.'
          : (j.os.length ? 'Só as OS das usinas marcadas (as abertas e em verificação).' : 'Nenhuma OS aberta nessas usinas.');
      })
      .catch(function () { if (n === pedido) osDica.textContent = 'Não li as OS agora: dá para enviar sem OS.'; });
  }
  if (caixa) caixa.addEventListener('change', function () {
    trazerOs(Array.prototype.slice.call(caixa.querySelectorAll('input:checked')).map(function (i) { return i.value; }));
  });
  if (fixa) trazerOs([fixa.value]);

  // os anexos: o limite conferido antes de enviar (o servidor confere de novo)
  var fAnx = dlg.querySelector('[data-dm-f-anexos]'), erro = dlg.querySelector('[data-dm-f-anexos-erro]');
  fAnx.addEventListener('change', function () {
    var mb = 1024 * 1024, fs = Array.prototype.slice.call(fAnx.files || []), total = 0, msg = '';
    var maxMb = +fAnx.getAttribute('data-max-mb'), maxN = +fAnx.getAttribute('data-max-arquivos'), maxT = +fAnx.getAttribute('data-max-total');
    fs.forEach(function (f) { total += f.size; if (!msg && f.size > maxMb * mb) msg = f.name + ' passa de ' + maxMb + ' MB.'; });
    if (!msg && fs.length > maxN) msg = 'São até ' + maxN + ' arquivos.';
    if (!msg && total > maxT * mb) msg = 'Os anexos passam de ' + maxT + ' MB juntos.';
    erro.textContent = msg; erro.hidden = !msg;
    fAnx.setCustomValidity(msg);
  });
  return {carregarPessoas: carregarPessoas};
};

(function () {
  'use strict';
  var raiz = document.querySelector('[data-dm]');
  if (!raiz) return;
  var abaAtual = raiz.getAttribute('data-aba') || 'para';
  var filtroDe = {};          // o filtro escolhido em cada aba

  function painel(aba) { return raiz.querySelector('[data-dm-painel="' + aba + '"]'); }
  function linhas(aba) { return Array.prototype.slice.call(painel(aba).querySelectorAll('[data-dm-linha]')); }

  function passa(l, aba) {
    var f = filtroDe[aba] || 'abertas';
    if ((' ' + (l.getAttribute('data-f') || '') + ' ').indexOf(' ' + f + ' ') < 0) return false;
    if (aba !== 'setor') return true;
    var p = painel(aba), sp = p.querySelector('[data-dm-pessoa]'), st = p.querySelector('[data-dm-tema]');
    if (sp && sp.value && l.getAttribute('data-para') !== sp.value) return false;
    if (st && st.value && l.getAttribute('data-tema') !== st.value) return false;
    return true;
  }

  function aplicar(aba) {
    var vistas = 0;
    linhas(aba).forEach(function (l) { var v = passa(l, aba); l.hidden = !v; if (v) vistas++; });
    var vazio = painel(aba).querySelector('[data-dm-vazio]');
    if (vazio) vazio.hidden = vistas > 0;
    painel(aba).querySelectorAll('[data-dm-filtro]').forEach(function (c) {
      c.setAttribute('aria-pressed', c.getAttribute('data-dm-filtro') === (filtroDe[aba] || 'abertas') ? 'true' : 'false');
    });
  }

  function abrir(id) {
    var achou = false;
    raiz.querySelectorAll('[data-dm-det]').forEach(function (a) {
      var e = a.getAttribute('data-dm-det') === id; a.hidden = !e; if (e) achou = true;
    });
    var vazio = raiz.querySelector('[data-dm-det-vazio]');
    if (vazio) vazio.hidden = achou;
    raiz.querySelectorAll('[data-dm-linha]').forEach(function (l) {
      l.setAttribute('aria-current', l.getAttribute('data-dm-linha') === id ? 'true' : 'false');
    });
    // os formulários do detalhe voltam para a aba que está aberta
    raiz.querySelectorAll('[data-dm-det="' + id + '"] input[name="aba"]').forEach(function (i) { i.value = abaAtual; });
    if (window.history && history.replaceState) {
      var u = new URL(window.location.href);
      u.searchParams.set('dem', abaAtual);
      if (id) u.searchParams.set('d', id); else u.searchParams.delete('d');
      history.replaceState(null, '', u.pathname + u.search + '#demandas');
    }
  }

  function primeiraVisivel(aba) {
    var l = linhas(aba).filter(function (x) { return !x.hidden; })[0];
    return l ? l.getAttribute('data-dm-linha') : '';
  }

  function trocarAba(aba, id) {
    abaAtual = aba;
    raiz.querySelectorAll('[data-dm-aba]').forEach(function (b) {
      b.setAttribute('aria-selected', b.getAttribute('data-dm-aba') === aba ? 'true' : 'false');
    });
    raiz.querySelectorAll('[data-dm-painel]').forEach(function (p) { p.hidden = p.getAttribute('data-dm-painel') !== aba; });
    // a aba dos Temas do setor (13/11/2026): sem lista nem detalhe; a tabela ocupa a largura
    raiz.classList.toggle('dm--temas', aba === 'temas');
    if (aba === 'temas') {
      if (window.history && history.replaceState) {
        var u = new URL(window.location.href);
        u.searchParams.set('dem', 'temas'); u.searchParams.delete('d');
        history.replaceState(null, '', u.pathname + u.search + '#demandas');
      }
      return;
    }
    // a demanda pedida (?d=) pode estar fora do filtro "Abertas" (a que acabou de ser concluída): vai para o filtro dela
    var alvo = id && painel(aba).querySelector('[data-dm-linha="' + id + '"]');
    if (alvo) {
      var fs = (alvo.getAttribute('data-f') || '').split(' ').filter(Boolean);
      if (fs.length && fs.indexOf(filtroDe[aba] || 'abertas') < 0) filtroDe[aba] = fs[0];
    }
    aplicar(aba);
    abrir(alvo ? id : primeiraVisivel(aba));
  }

  raiz.addEventListener('click', function (ev) {
    var b = ev.target.closest('[data-dm-aba]');
    if (b) { trocarAba(b.getAttribute('data-dm-aba')); return; }
    var c = ev.target.closest('[data-dm-filtro]');
    if (c) { filtroDe[abaAtual] = c.getAttribute('data-dm-filtro'); aplicar(abaAtual); abrir(primeiraVisivel(abaAtual)); return; }
    var o = ev.target.closest('[data-os-folio]');
    if (o && window.NexusOsCard) { ev.preventDefault(); NexusOsCard.abrirFolio(o.getAttribute('data-os-folio'), {status: ''}); return; }
    var l = ev.target.closest('[data-dm-linha]');
    if (l) abrir(l.getAttribute('data-dm-linha'));
  });
  raiz.addEventListener('keydown', function (ev) {
    var l = ev.target.closest && ev.target.closest('[data-dm-linha]');
    if (l && (ev.key === 'Enter' || ev.key === ' ')) { ev.preventDefault(); abrir(l.getAttribute('data-dm-linha')); }
  });
  raiz.addEventListener('change', function (ev) {
    if (ev.target.matches('[data-dm-pessoa], [data-dm-tema]')) { aplicar('setor'); abrir(primeiraVisivel('setor')); }
  });
  // o duplo clique não manda duas vezes (o novo_id já protege o banco; isto evita a espera dobrada)
  document.addEventListener('submit', function (ev) {
    var f = ev.target;
    if (!f.matches('[data-dm-form], [data-dm-form-nova]')) return;
    if (f.getAttribute('data-enviando')) { ev.preventDefault(); return; }
    f.setAttribute('data-enviando', '1');
  });

  // o ?d= do endereço só entra no seletor se tiver a forma de um id (um link mexido não para o script)
  var sel = raiz.getAttribute('data-sel') || '';
  trocarAba(abaAtual, /^d[0-9a-f]{11}$/.test(sel) ? sel : '');

  // ── a Nova demanda (os campos: NexusDemandaNova, no alto deste arquivo) ──
  var dlg = document.getElementById('dm-nova'), botao = raiz.querySelector('[data-dm-nova]');
  if (!dlg || !botao) return;
  var nova = window.NexusDemandaNova(dlg);
  botao.addEventListener('click', function () {
    nova.carregarPessoas();
    if (dlg.showModal) dlg.showModal(); else dlg.setAttribute('open', '');
  });
  dlg.querySelectorAll('[data-dm-fechar]').forEach(function (b) { b.addEventListener('click', function () { dlg.close(); }); });
})();

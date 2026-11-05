/* Gestão PCM (Levi, 04/11/2026: o resto da aba Gestão PCM do painel do PCM): o que abre sem recarregar a página.
   - A barra dos filtros de cima, recolhível ("suspenso e expandível"): lembra se estava aberta (sessionStorage; o estado
     é aplicado logo depois da barra, no template, para não piscar).
   - As 7 listas de várias escolhas (o gp-ms do painel): o botão abre o painel com a busca, "Todos", "Limpar" e as
     caixinhas; Esc, o clique fora ou o foco que sai fecham, e a escolha APLICA AO FECHAR (não a cada caixinha). Todas
     marcadas = sem filtro (nada vai na URL). Os campos de texto aplicam ao Enter ou ao sair do campo.
   - As árvores: o tipo pede a tabela dele à rota da tela (?arv=&ac=&au=&at=) na 1ª abertura ("Lendo…", e o erro com
     "Tentar de novo"); o Só atrasadas pede as partes seguintes (?ap=); a Confiabilidade por ativo e o MTTR por equipe
     cluster pedem o corpo quando o bloco abre (?cf=), e a usina da confiabilidade, a tabela dela (?cf=usina).
   - A OS (o botão .pgp-os-n) abre o card dela no Nexus em qualquer lugar da tela: no painel lateral das pendentes, na
     tabela da árvore, no Só atrasadas e na confiabilidade. Um ouvinte só: dois abririam o card duas vezes.
   Endereços: tudo sai do próprio endereço da tela ("?..."), então o prefixo do Nexus (/nexus) vale sozinho. */
(function () {
  'use strict';
  var BARRA = 'nexus.pcm.gestao.filtros', MAX = 50;
  var corpo = document.getElementById('pgf-corpo'), abre = document.getElementById('pgf-abre');

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  }
  function semAcento(s) { return String(s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase(); }

  // ── a barra recolhível ──
  if (abre && corpo) {
    abre.addEventListener('click', function () {
      var abrir = corpo.hidden;
      corpo.hidden = !abrir;
      abre.setAttribute('aria-expanded', String(abrir));
      try { sessionStorage.setItem(BARRA, abrir ? '1' : '0'); } catch (e) { /* sem armazenamento: só não lembra */ }
    });
  }

  // ── o envio dos filtros (as listas, os campos e o "considerar") ──
  var mexida = null;            // a lista que acabou de fechar com outra escolha: só ela vira "Todos" quando cheia
  function enviar() {
    if (!corpo) return;
    if (corpo.requestSubmit) corpo.requestSubmit(); else if (antesDeEnviar()) corpo.submit();
  }
  function antesDeEnviar() {
    if (mexida) {
      var cx = mexida.querySelectorAll('input[type=checkbox]'), m = mexida.querySelectorAll('input[type=checkbox]:checked');
      if (cx.length && m.length === cx.length) {
        cx.forEach(function (i) { i.disabled = true; });          // todas = "Todos": a lista sai da URL
      } else if (m.length > MAX) {
        var av = mexida.querySelector('.pgf-ms-aviso');
        if (av) { av.textContent = 'Escolha até ' + MAX + ' itens, ou todos.'; av.hidden = false; }
        abrirMs(mexida);
        mexida = null;
        return false;
      }
    }
    // o que está vazio não vai na URL; o "considerar" só vale com uma data
    ['os', 'ss', 'pini', 'pfim'].forEach(function (n) {
      var el = corpo.elements[n];
      if (el && !String(el.value || '').trim()) el.disabled = true;
    });
    var pm = corpo.elements.pmodo, ini = corpo.elements.pini, fim = corpo.elements.pfim;
    if (pm && (pm.value === 'qq' || !((ini && ini.value) || (fim && fim.value)))) pm.disabled = true;
    return true;
  }
  if (corpo) {
    corpo.addEventListener('submit', function (ev) { if (!antesDeEnviar()) ev.preventDefault(); });
    // a volta pelo histórico (bfcache) traz a página como saiu: os campos desligados para o envio voltam a valer
    window.addEventListener('pageshow', function () {
      corpo.querySelectorAll('input:disabled, select:disabled').forEach(function (el) { el.disabled = false; });
    });
    // OS e Solicitação, e o período (de, até e o considerar), em grupos: aplicam ao Enter ou quando o foco SAI do grupo,
    // e não a cada campo (revisão de 05/11/2026: preencher "Período de" e ir para o "Até" recarregava a tela com meio
    // período, também no seletor de data do celular), nem a cada dígito (a data muda de valor enquanto o ano é
    // digitado). O Enter é daqui: o formulário tem vários campos e nenhum botão de enviar, e aí o navegador não envia.
    // O considerar sem data não envia (sem data ele não filtra nada)
    [['os', 'ss'], ['pini', 'pfim', 'pmodo']].forEach(function (nomes) {
      var els = nomes.map(function (n) { return corpo.elements[n]; }).filter(Boolean);
      var antes = els.map(function (e) { return e.value; });
      function mudou() {
        var ini = corpo.elements.pini, fim = corpo.elements.pfim;
        return els.some(function (e, i) {
          if (e.value === antes[i]) return false;
          return e.name !== 'pmodo' || !!((ini && ini.value) || (fim && fim.value));
        });
      }
      els.forEach(function (el) {
        el.addEventListener('blur', function (ev) {
          if (ev.relatedTarget && els.indexOf(ev.relatedTarget) >= 0) return;       // ainda dentro do grupo
          if (mudou()) enviar();
        });
        el.addEventListener('keydown', function (ev) {
          if (ev.key === 'Enter') { ev.preventDefault(); if (mudou()) enviar(); }
        });
      });
    });
  }

  // ── as listas de várias escolhas ──
  var aberta = null, marcadasAntes = '';
  function marcadas(ms) {
    return Array.prototype.map.call(ms.querySelectorAll('input[type=checkbox]:checked'), function (i) { return i.value; }).join('\u0001');
  }
  function rotular(ms) {
    var m = ms.querySelectorAll('input[type=checkbox]:checked'), v = ms.querySelector('.pgf-ms-v');
    if (!v) return;
    v.textContent = !m.length ? (ms.dataset.vazio || 'Todos') :
      (m.length === 1 ? m[0].value : m.length + (ms.dataset.vazio === 'Todas' ? ' selecionadas' : ' selecionados'));
    ms.classList.toggle('on', m.length > 0);
  }
  function abrirMs(ms) {
    var bt = ms.querySelector('.pgf-ms-bt'), painel = ms.querySelector('.pgf-ms-painel');
    if (aberta && aberta !== ms) fecharMs(aberta, false);
    aberta = ms; marcadasAntes = marcadas(ms);
    painel.classList.remove('pgf-ms-painel--dir');
    painel.hidden = false; bt.setAttribute('aria-expanded', 'true');
    // a lista larga (acima de 640 px) passaria da borda direita da tela: vira para a esquerda
    if (painel.getBoundingClientRect().right > document.documentElement.clientWidth - 8) painel.classList.add('pgf-ms-painel--dir');
    // a busca só ganha o foco com ponteiro fino: no celular o teclado subia a cada abertura (revisão de 05/11/2026)
    var busca = painel.querySelector('.pgf-ms-busca');
    if (busca && window.matchMedia && window.matchMedia('(pointer: fine)').matches) busca.focus();
  }
  function fecharMs(ms, focar) {
    if (!ms) return;
    var bt = ms.querySelector('.pgf-ms-bt'), painel = ms.querySelector('.pgf-ms-painel');
    painel.hidden = true; bt.setAttribute('aria-expanded', 'false');
    if (aberta === ms) aberta = null;
    // a busca não fica pela metade para a próxima abertura
    var busca = painel.querySelector('.pgf-ms-busca');
    if (busca && busca.value) { busca.value = ''; painel.querySelectorAll('.pgf-ms-op').forEach(function (o) { o.hidden = false; }); }
    if (focar) bt.focus();
    if (marcadas(ms) !== marcadasAntes) { mexida = ms; enviar(); }       // aplica ao fechar, se mudou
  }
  document.querySelectorAll('.pgf-ms').forEach(function (ms) {
    var bt = ms.querySelector('.pgf-ms-bt'), painel = ms.querySelector('.pgf-ms-painel'),
        busca = ms.querySelector('.pgf-ms-busca');
    bt.addEventListener('click', function () { if (aberta === ms) fecharMs(ms, false); else abrirMs(ms); });
    painel.addEventListener('change', function () { rotular(ms); var av = ms.querySelector('.pgf-ms-aviso'); if (av) av.hidden = true; });
    painel.addEventListener('click', function (ev) {
      var q = ev.target.closest('[data-ms]');
      if (!q) return;
      if (q.dataset.ms === 'todos') {
        painel.querySelectorAll('.pgf-ms-op:not([hidden]) input').forEach(function (i) { i.checked = true; });
      } else {
        painel.querySelectorAll('input[type=checkbox]').forEach(function (i) { i.checked = false; });
      }
      rotular(ms);
    });
    if (busca) {
      busca.addEventListener('input', function () {
        var q = semAcento(busca.value.trim());
        painel.querySelectorAll('.pgf-ms-op').forEach(function (o) { o.hidden = q && semAcento(o.textContent).indexOf(q) < 0; });
      });
      // o Enter na busca fecha a lista (e aplica), em vez de enviar o formulário com a busca pela metade
      busca.addEventListener('keydown', function (ev) { if (ev.key === 'Enter') { ev.preventDefault(); fecharMs(ms, true); } });
    }
    ms.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape' && aberta === ms) { ev.preventDefault(); ev.stopPropagation(); fecharMs(ms, true); }
    });
    // o foco que sai da lista (Tab) fecha; o clique num canto vazio do painel não tira o foco para fora dela
    ms.addEventListener('focusout', function (ev) {
      if (aberta === ms && ev.relatedTarget && !ms.contains(ev.relatedTarget)) fecharMs(ms, false);
    });
  });
  document.addEventListener('click', function (ev) {
    if (aberta && !aberta.contains(ev.target)) fecharMs(aberta, false);
  });

  // ── o que vem por fetch: a tabela do tipo, a confiabilidade, a usina dela e as partes do Só atrasadas ──
  function ler(url) {
    return fetch(url, {credentials: 'same-origin', headers: {'Accept': 'text/html'}})
      .then(function (r) { return r.text().then(function (t) { return {ok: r.ok, status: r.status, t: t}; }); });
  }
  // o erro de um pedaço (revisão de 05/11/2026): 404 = a lista mudou (o robô regravou o arquivo, ou a conta da
  // Engenharia mudou), e "Tentar de novo" não adianta; outro erro, a mensagem que o servidor mandou (não "HTTP 503"),
  // com o "Tentar de novo"
  function falha(r, semTentar) {
    if (r.status === 404) {
      return '<p class="pgx-erro" role="alert">A lista mudou: <a class="pcm-link" href="">recarregue a página</a>.</p>';
    }
    var tpl = document.createElement('template');
    tpl.innerHTML = r.t || '';
    var msg = (tpl.content.textContent || '').replace(/\s+/g, ' ').replace(/Tentar de novo/g, '').trim();
    return '<p class="pgx-erro" role="alert">' + esc(msg || 'Não consegui ler agora.')
      + (semTentar ? '' : ' <button type="button" class="pgf-lnk" data-tentar>Tentar de novo</button>') + '</p>';
  }
  function encher(caixa, url, depois) {
    if (!caixa || caixa.dataset.cheio === '1' || caixa.dataset.lendo === '1') return;
    caixa.dataset.url = url; caixa.dataset.lendo = '1';
    caixa.innerHTML = '<p class="pgx-carga" role="status">Lendo…</p>';
    ler(url).then(function (r) {
      caixa.dataset.lendo = '';
      if (!r.ok) { caixa.innerHTML = falha(r); return; }
      caixa.innerHTML = r.t;
      // a confiabilidade sem a leitura completa das OS de falha não fica guardada: abrir de novo pergunta de novo
      if (!caixa.querySelector('[data-pgc-incompleta]')) caixa.dataset.cheio = '1';
      prepararOs(caixa);
      if (depois) depois(caixa);
    }).catch(function (e) {
      caixa.dataset.lendo = '';
      caixa.innerHTML = '<p class="pgx-erro" role="alert">Não consegui ler agora (' + esc(e && e.message || 'sem conexão')
        + '). <button type="button" class="pgf-lnk" data-tentar>Tentar de novo</button></p>';
    });
  }
  document.addEventListener('click', function (ev) {
    var t = ev.target.closest('[data-tentar]');
    if (!t) return;
    var caixa = t.closest('.pga-tab, .pgc-corpo, .pgc-tab, .pgc-os-caixa');
    if (caixa && caixa.dataset.url) { caixa.dataset.cheio = ''; encher(caixa, caixa.dataset.url, quandoDe(caixa)); }
  });
  function urlCom(base, mudar) {
    var q = new URLSearchParams(String(base || '?').replace(/^\?/, ''));
    Object.keys(mudar).forEach(function (k) { q.set(k, mudar[k]); });
    return '?' + q.toString();
  }
  // a hora da leitura das OS de falha vai para a linha de baixo do título do bloco
  function quandoDe(caixa) {
    var bloco = caixa.closest('.pgc');
    if (!bloco || !caixa.classList.contains('pgc-corpo')) return null;
    return function () {
      var f = caixa.querySelector('[data-quando]'), q = bloco.querySelector('.pgc-quando');
      if (f && q && f.dataset.quando) q.textContent = ' · atualizado ' + f.dataset.quando;
    };
  }
  // <details> não propaga o "toggle": ouvido na captura
  document.addEventListener('toggle', function (ev) {
    var d = ev.target;
    if (!d.open || !d.matches) return;
    if (d.matches('.pga-tip')) {
      var sec = d.closest('[data-arv]'), cli = d.closest('[data-ac]'), usi = d.closest('[data-au]');
      if (!sec || !cli || !usi) return;
      encher(d.querySelector('.pga-tab'), urlCom(sec.dataset.base, {arv: sec.dataset.arv, ac: cli.dataset.ac,
                                                                    au: usi.dataset.au, at: d.dataset.at}));
    } else if (d.matches('.pgc')) {
      var caixa = d.querySelector('.pgc-corpo');
      encher(caixa, d.dataset.url, quandoDe(caixa));
    } else if (d.matches('.pgc-usi[data-cu]')) {
      var bloco = d.closest('.pgc');
      if (bloco) encher(d.querySelector('.pgc-tab'), urlCom(bloco.dataset.url, {cf: 'usina', cc: d.dataset.cc, cu: d.dataset.cu}));
    }
  }, true);

  // o ativo da confiabilidade abre as OS dele (a linha de baixo), pedidas só na 1ª abertura (?cf=ativo&ca=<código>):
  // uma usina grande tinha 1.090 OS no pedaço dela (revisão de 05/11/2026)
  document.addEventListener('click', function (ev) {
    var bt = ev.target.closest('.pgc-a-bt');
    if (!bt) return;
    var det = document.getElementById(bt.getAttribute('aria-controls'));
    if (!det) return;
    det.hidden = !det.hidden;
    bt.setAttribute('aria-expanded', String(!det.hidden));
    var caixa = det.querySelector('.pgc-os-caixa'), bloco = bt.closest('.pgc');
    if (!det.hidden && caixa && bloco) encher(caixa, urlCom(bloco.dataset.url, {cf: 'ativo', ca: caixa.dataset.ca}));
  });

  // o Só atrasadas em partes: o "Mostrar mais" pede a parte seguinte (o tamanho no data-pagina) e a põe no fim da
  // tabela; no erro, o próprio botão é o "tentar de novo"
  document.addEventListener('click', function (ev) {
    var bt = ev.target.closest('.pgs-mais');
    if (!bt || bt.disabled) return;
    var corpoT = document.getElementById(bt.getAttribute('aria-controls')), msg = bt.parentNode.querySelector('.pgs-msg');
    bt.disabled = true;
    if (msg) msg.textContent = 'Lendo…';
    ler(bt.dataset.url).then(function (r) {
      if (!r.ok) {
        bt.disabled = false;
        var p = document.createElement('template');
        p.innerHTML = falha(r, true);
        if (msg) msg.innerHTML = p.content.firstChild.innerHTML;
        if (r.status === 404) bt.parentNode.removeChild(bt);
        return;
      }
      var tpl = document.createElement('template');
      tpl.innerHTML = r.t;
      var tb = tpl.content.querySelector('tbody[data-proximo]');
      if (!tb) throw new Error('resposta sem as linhas');
      Array.prototype.slice.call(tb.querySelectorAll('tr')).forEach(function (tr) { corpoT.appendChild(tr); });
      prepararOs(corpoT);
      var restam = parseInt(tb.dataset.restam, 10) || 0;
      if (msg) msg.textContent = '';
      if (!restam) { bt.parentNode.removeChild(bt); return; }
      bt.dataset.url = urlCom(bt.dataset.url, {ap: tb.dataset.proximo});
      var pagina = parseInt(bt.dataset.pagina, 10) || 100;
      bt.textContent = 'Mostrar mais ' + Math.min(restam, pagina).toLocaleString('pt-BR')
        + (restam > pagina ? ' de ' + restam.toLocaleString('pt-BR') + ' restantes' : '');
      bt.disabled = false;
    }).catch(function (e) {
      bt.disabled = false;
      if (msg) msg.textContent = 'Não consegui ler agora (' + (e && e.message || 'sem conexão') + '): tente de novo.';
    });
  });

  // ── a OS abre o card dela no Nexus (oscreator/card_os_abrir.html), em qualquer lugar da tela ──
  function prepararOs(raiz) {
    if (!window.NexusOsCard || !NexusOsCard.prepararAoParar) return;
    (raiz || document).querySelectorAll('.pgp-os-n[data-wid]').forEach(function (b) {
      if (b.dataset.preparado) return;
      b.dataset.preparado = '1';
      NexusOsCard.prepararAoParar(b, b.dataset.wid);
    });
  }
  document.addEventListener('click', function (ev) {
    var os = ev.target.closest('.pgp-os-n[data-wid]');
    if (os && window.NexusOsCard) NexusOsCard.abrir(os.dataset.wid, {status: os.dataset.status, folio: os.dataset.folio});
  });
  prepararOs(document);
  window.pgGestao = {prepararOs: prepararOs};
})();

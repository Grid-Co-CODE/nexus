/* O prontuário da usina (12/11/2026; comando/_prontuario.html). Os cartões vêm fechados (Levi: "primeiramente, dando um
   parecer geral, e quando a pessoa quiser se aprofundar, se aprofunda"): cada número do painel e cada pendência abrem
   o cartão deles; o endereço com #pu-<cartão> também. O número da OS abre o card dela (o do OS Creator); a linha do
   tempo filtra por fonte; o Relatório abre a janela do mês e dos temas. Sem este arquivo a página segue: os cartões
   abrem no clique (são <details>) e a OS fica como texto. */
(function () {
  'use strict';
  var raiz = document.querySelector('[data-pu]');
  if (!raiz) return;

  // ── o diagnóstico do dia da IA, no lugar do parecer (14/11/2026) ───────────────────────────────────────────────────
  // Um por usina por dia: a primeira abertura manda fazer (a rota responde "preparando" e a página segue), e quem abre
  // depois lê o guardado. Sem a IA (sem chave, teto, erro), fica o parecer que já está na página
  function escD(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  }
  function osDiag(n, tipo) {
    if (!n) return '';
    if (tipo === 'os' || !tipo) {
      return ' <button type="button" class="pu-diag-os" data-pu-os="' + escD(n) + '" title="Abrir o card da OS ' + escD(n) + '">OS ' + escD(n) + '</button>';
    }
    var de = tipo === 'chamado' ? '?de=garantias' : (tipo === 'performance' ? '?de=performance' : '');
    return ' <a class="pu-diag-os" href="' + escD(nexusRota('/t/engenharia/equipe/os/')) + escD(n) + de +
      '" target="_blank" rel="noopener" title="Raio X da OS ' + escD(n) + ' (abre em outra aba)">OS ' + escD(n) + '</a>';
  }
  var LISTAS_DIAG = [['tem_que_fazer', 'Tem que fazer', 'critico'], ['pode_fazer', 'Pode fazer', 'ok'],
                     ['pendente', 'Pendente com outros', 'alerta']];
  var CHAVE_RECOLHIDO = 'nexus.pu-diag.recolhido';
  function recolher(el, sim) {
    var corpo = el.querySelector('[data-pu-diag-corpo]'), bt = el.querySelector('[data-pu-diag-alterna]');
    corpo.hidden = sim;
    bt.setAttribute('aria-expanded', sim ? 'false' : 'true');
    bt.querySelector('span').textContent = sim ? 'Ver o que fazer' : 'Recolher';
    bt.querySelector('i').className = 'ph ' + (sim ? 'ph-caret-down' : 'ph-caret-up');
  }
  function desenharDiag(el, j) {
    var frase = el.querySelector('[data-pu-diag-frase]'), corpo = el.querySelector('[data-pu-diag-corpo]');
    var fonte = el.querySelector('[data-pu-diag-fonte]'), bt = el.querySelector('[data-pu-diag-alterna]');
    var d = j.diag;
    if (d) {
      frase.textContent = d.situacao;
      frase.classList.add('pu-par-t--ia');
      // o selo diz de quem é a leitura, na cor do nível do parecer (14/11/2026, Levi: "mude o nome de 'Pede ação agora'
      // para Nexus IA Insights"); sem a IA, fica o título do parecer
      el.querySelector('[data-pu-diag-selo]').textContent = 'Nexus IA Insights';
      corpo.innerHTML = LISTAS_DIAG.map(function (l) {
        var itens = d[l[0]] || [];
        if (!itens.length) return '';
        return '<div class="pu-diag-col pu-diag-col--' + l[2] + '"><h3>' + l[1] + '</h3><ul>' + itens.map(function (x) {
          return '<li>' + escD(x.texto) + osDiag(x.os, x.os_tipo) + '</li>';
        }).join('') + '</ul></div>';
      }).join('');
    } else {
      corpo.innerHTML = '<p class="pu-diag-texto">' + escD(j.texto) + '</p>';
    }
    fonte.textContent = 'Diagnóstico da IA de ' + (j.data || 'hoje') + (j.hora ? ', feito às ' + j.hora : '') +
      (j.rotulo ? ' pelo ' + j.rotulo : '') + ', com a performance até ontem e as pendências daquela hora. ' +
      'É um por dia: quem abrir hoje vê este mesmo.' + (j.troca ? ' ' + j.troca : '');
    fonte.hidden = false;
    if (corpo.innerHTML) {
      bt.hidden = false;
      var recolhido = false;
      try { recolhido = localStorage.getItem(CHAVE_RECOLHIDO) === '1'; } catch (e) { /* sem armazenamento: aberto */ }
      recolher(el, recolhido);
    }
  }
  function carregarDiag(el, vez) {
    var fonte = el.querySelector('[data-pu-diag-fonte]');
    fetch(el.getAttribute('data-pu-diag'), {credentials: 'same-origin', headers: {'Accept': 'application/json'}})
      .then(function (r) { return r.ok ? r.json() : {estado: 'fora'}; })
      .then(function (j) {
        if (j.estado === 'pronto' || j.estado === 'texto') { desenharDiag(el, j); return; }
        if (j.estado === 'preparando') {
          fonte.textContent = 'A IA está fazendo o diagnóstico do dia desta usina. Quem abrir depois já vê pronto.';
          fonte.hidden = false;
          if (vez < 36) { setTimeout(function () { carregarDiag(el, vez + 1); }, 5000); }
          return;
        }
        if (j.estado === 'erro' || j.estado === 'teto') {
          fonte.textContent = j.estado === 'teto' ? 'O diagnóstico da IA não saiu: o teto do mês do Nexus IA foi atingido. Vale o parecer acima.'
            : 'O diagnóstico da IA não saiu agora (' + (j.erro || 'sem resposta') + '). Vale o parecer acima; a IA tenta de novo em 20 minutos.';
          fonte.hidden = false;
        }
      })
      .catch(function () { /* sem conexão: fica o parecer */ });
  }
  var diagEl = raiz.querySelector('[data-pu-diag]');
  if (diagEl && window.fetch) {
    diagEl.querySelector('[data-pu-diag-alterna]').addEventListener('click', function () {
      var sim = !diagEl.querySelector('[data-pu-diag-corpo]').hidden;
      recolher(diagEl, sim);
      try { localStorage.setItem(CHAVE_RECOLHIDO, sim ? '1' : '0'); } catch (e) { /* segue sem lembrar */ }
    });
    carregarDiag(diagEl, 0);
  }

  // o número, a barra e a pendência do alto levam ao cartão deles: ele abre, os outros fecham (a página não vira uma
  // parede de texto), fica marcado e sobe para a vista (Levi, 12/11/2026: "clicar e já se encaminhando para aquela
  // informação. Aquela informação aparecer na tela dela"). Quem abre o cartão pelo título dele não fecha os outros
  function abrir(sec, rolar) {
    var d = document.getElementById('pu-' + sec);
    if (!d) return;
    raiz.querySelectorAll('details.pu-sec').forEach(function (o) {
      if (o !== d) { o.open = false; }
      o.classList.toggle('pu-sec--foco', o === d);
    });
    if (!d.open) d.open = true;
    if (rolar) d.scrollIntoView({block: 'start'});
  }
  raiz.addEventListener('click', function (ev) {
    var a = ev.target.closest('[data-pu-abre]');
    if (a) { ev.preventDefault(); abrir(a.getAttribute('data-pu-abre'), true); return; }
    var b = ev.target.closest('[data-pu-os]');
    if (b && window.NexusOsCard) {
      ev.preventDefault();
      var op = {folio: b.getAttribute('data-pu-os'), status: ''}, wid = b.getAttribute('data-pu-wid');
      if (wid) NexusOsCard.abrir(wid, op); else NexusOsCard.abrirFolio(op.folio, op);
    }
  });
  var h = (location.hash || '').slice(1);
  if (/^pu-[a-z]+$/.test(h)) abrir(h.slice(3), true);

  // o menu do Criar OS fecha no clique fora e no Esc
  var menu = raiz.querySelector('.pu-menu');
  if (menu) {
    document.addEventListener('click', function (ev) { if (menu.open && !menu.contains(ev.target)) menu.open = false; });
    document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape' && menu.open) menu.open = false; });
  }

  // o Criar OS por cima do prontuário (13/11/2026, Levi: "está jogando para uma aba nova do OS Creator, que não dá a
  // opção de voltar para o prontuário da usina [...] Abre o cardzão da OS, dando um blur de fundo, e aí quando a pessoa
  // cria a OS, ela só pode fechar o card e já era"): a tela de criação do OS Creator numa janela com o fundo desfocado,
  // pela moldura do meio (/os/_nexus/criar, a mesma ideia da tela do chamado). Criou sem falha: a janela fecha e o aviso
  // aparece (o mesmo do Tempo real). Com falha, a janela fica: a tela diz o que não saiu. Fechar, Esc e o clique fora
  // fecham, e a moldura sai junto. O botão do meio e o Ctrl abrem a tela numa aba, pelo href
  var jan = document.getElementById('pu-os-jan');
  if (jan) {
    var mold = null;
    var tirar = function () { if (mold) { mold.remove(); mold = null; } };
    var fecharJan = function () { if (jan.open) jan.close(); tirar(); };
    raiz.addEventListener('click', function (ev) {
      var a = ev.target.closest('[data-pu-criar]');
      if (!a || ev.button || ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.altKey) return;
      ev.preventDefault();
      if (menu) menu.open = false;
      tirar();
      var rot = ((a.querySelector('b') || a).textContent || '').trim() || 'Criar OS';
      var q = new URLSearchParams({url: a.getAttribute('data-pu-criar'), de: location.pathname + location.search});
      mold = document.createElement('iframe');
      mold.className = 'cr-chamado-moldura';
      mold.title = rot;
      mold.src = nexusRota('/os/_nexus/criar') + '?' + q.toString();
      document.getElementById('pu-os-jan-t').textContent = rot;
      jan.appendChild(mold);
      jan.showModal();
    });
    jan.addEventListener('close', tirar);
    jan.addEventListener('click', function (ev) { if (ev.target === jan) fecharJan(); });
    jan.querySelector('[data-pu-os-fechar]').addEventListener('click', fecharJan);
    window.addEventListener('message', function (e) {
      if (!mold || e.origin !== location.origin || e.source !== mold.contentWindow) return;
      var d = e.data || {};
      if (d.nexusCriarOs !== 1) return;
      if (d.tipo === 'fechar') { fecharJan(); return; }
      if (d.tipo === 'criada' && !d.falhas) { fecharJan(); avisar(d.mensagem || 'OS criada no Fracttal.'); }
    });
  }
  // a janela da usina (13/11/2026, Levi: "Pode abrir uma janelinha na frente, sobrepor uma tela. Não precisa ser algo
  // que leva para um link [...] tira totalmente a imersão da tela do prontuário"; e, da conversa: "faça algo bem versátil
  // para as pessoas usarem"): o dossiê e a conversa vêm como pedaço de página. O que se faz lá dentro fica lá: os
  // formulários vão por trás e a resposta (depois do 303) é a janela de novo, com o aviso; as abas trocam sem pedido
  var pj = document.getElementById('pu-jan');
  if (pj) {
    var pjCorpo = pj.querySelector('[data-pu-jan-corpo]'), pjT = document.getElementById('pu-jan-t'), novas = [];
    var montarJan = function () {
      if (window.nexusConversa) window.nexusConversa(pjCorpo);
      novas = [];
      pjCorpo.querySelectorAll('[data-pu-dm-nova]').forEach(function (f) {
        if (window.NexusDemandaNova) novas.push(window.NexusDemandaNova(f));
      });
      // a aba Pedir aberta já de início (a volta de um envio que falhou): quem recebe vem agora
      var pedir = pjCorpo.querySelector('[data-pu-seg-painel="pedir"]');
      if (pedir && !pedir.hidden) novas.forEach(function (n) { n.carregarPessoas(); });
    };
    var carregar = function (url, opcoes) {
      pjCorpo.setAttribute('aria-busy', 'true');
      return fetch(url, Object.assign({credentials: 'same-origin'}, opcoes || {})).then(function (r) {
        if (r.redirected && /\/entrar/.test(r.url)) { location.reload(); return null; }     // a sessão do Nexus caiu
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.text();
      }).then(function (html) {
        if (html === null) return;
        pjCorpo.innerHTML = html;
        montarJan();
      }).catch(function (e) {
        pjCorpo.innerHTML = '<div class="cn-erro" role="alert"><b>Não consegui abrir agora (' + e.message + ').</b> Feche e tente de novo.</div>';
      }).then(function () { pjCorpo.removeAttribute('aria-busy'); });
    };
    raiz.addEventListener('click', function (ev) {
      var a = ev.target.closest('[data-pu-jan]');
      if (!a || ev.button || ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.altKey) return;
      ev.preventDefault();
      pjT.textContent = a.getAttribute('data-pu-jan-t') || 'Usina';
      pjCorpo.innerHTML = '<p class="mudo pu-jan-carregando">Carregando…</p>';
      if (!pj.open) pj.showModal();
      carregar(a.getAttribute('data-pu-jan'));
    });
    pj.addEventListener('submit', function (ev) {
      var f = ev.target;
      if (!f || String(f.getAttribute('method') || '').toLowerCase() !== 'post' || ev.defaultPrevented) return;
      ev.preventDefault();
      var dados = new FormData(f);
      if (ev.submitter && ev.submitter.name) dados.append(ev.submitter.name, ev.submitter.value);
      f.querySelectorAll('button[type="submit"]').forEach(function (b) { b.disabled = true; });
      carregar(f.action, {method: 'POST', body: dados});
    });
    pj.addEventListener('click', function (ev) {
      if (ev.target === pj) { pj.close(); return; }
      var s = ev.target.closest('[data-pu-seg]');
      if (s) {
        var k = s.getAttribute('data-pu-seg');
        pjCorpo.querySelectorAll('[data-pu-seg]').forEach(function (b) { b.setAttribute('aria-selected', b === s ? 'true' : 'false'); });
        pjCorpo.querySelectorAll('[data-pu-seg-painel]').forEach(function (p) { p.hidden = p.getAttribute('data-pu-seg-painel') !== k; });
        if (k === 'pedir') novas.forEach(function (n) { n.carregarPessoas(); });
        return;
      }
      var c = ev.target.closest('[data-ds-copiar]');
      if (c) {
        var pre = pjCorpo.querySelector('[data-ds-texto]'), rot = c.lastChild.textContent;
        var fim = function (ok) { c.lastChild.textContent = ok ? ' Copiado' : ' Não deu para copiar: selecione o texto'; setTimeout(function () { c.lastChild.textContent = rot; }, 2500); };
        if (pre && navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(pre.textContent).then(function () { fim(true); }, function () { fim(false); });
        else fim(false);
      }
    });
    pj.querySelector('[data-pu-jan-fechar]').addEventListener('click', function () { pj.close(); });
    // o Nexus IA fecha a janela para o card da OS aparecer e a reabre depois (data-manter): o chat não se perde
    pj.addEventListener('close', function () { if (pj.dataset.manter) return; pjCorpo.innerHTML = ''; novas = []; });
  }
  // o aviso no pé da tela, que some sozinho (a OS criada, com o número)
  function avisar(texto) {
    var t = document.getElementById('pu-aviso');
    if (!t) {
      t = document.createElement('div'); t.id = 'pu-aviso'; t.className = 'pu-aviso'; t.setAttribute('role', 'status');
      document.body.appendChild(t);
    }
    t.textContent = texto; t.hidden = false;
    clearTimeout(t._fim); t._fim = setTimeout(function () { t.hidden = true; }, 8000);
  }

  // o relatório em PDF: a janela do mês e dos campos de cada tema; sem campo marcado o Baixar trava e diz por quê
  var dlg = document.getElementById('pu-rel'), bRel = raiz.querySelector('[data-pu-rel]');
  if (dlg && bRel) {
    var form = dlg.querySelector('[data-pu-rel-form]');
    // o tema liga e desliga os campos dele; o tema fica marcado enquanto houver um campo dele marcado
    var conferir = function () {
      form.querySelectorAll('[data-pu-rel-tema]').forEach(function (t) {
        var grupo = t.closest('[data-pu-rel-grupo]');
        if (grupo) { t.checked = !!grupo.querySelector('input[name="campo"]:checked'); }
      });
      var algum = !!form.querySelector('input[name="campo"]:checked');
      form.querySelector('button[type="submit"]').disabled = !algum;
      form.querySelector('.pn-rel-aviso').hidden = algum;
      return algum;
    };
    bRel.addEventListener('click', function () { if (dlg.showModal) dlg.showModal(); else dlg.setAttribute('open', ''); });
    dlg.addEventListener('click', function (ev) {
      if (ev.target === dlg || ev.target.closest('[data-pu-rel-fechar]')) { dlg.close(); return; }
      var t = ev.target.closest('[data-pu-rel-todos]');
      if (t) {
        var marcar = t.getAttribute('data-pu-rel-todos') === '1';
        form.querySelectorAll('input[name="campo"]').forEach(function (c) { c.checked = marcar; });
        conferir();
      }
    });
    form.addEventListener('change', function (ev) {
      var t = ev.target;
      if (t.matches && t.matches('[data-pu-rel-tema]')) {
        t.closest('[data-pu-rel-grupo]').querySelectorAll('input[name="campo"]').forEach(function (c) { c.checked = t.checked; });
      }
      conferir();
    });
    form.addEventListener('submit', function (ev) {
      if (!conferir()) { ev.preventDefault(); return; }
      setTimeout(function () { if (dlg.open) dlg.close(); }, 400);       // o PDF chega como download; a página fica
    });
  }

  // a linha do tempo: o filtro por fonte e os dias anteriores
  var linha = raiz.querySelector('.pu-linha');
  if (!linha) return;
  var fonte = '', todos = false;
  function aplicar() {
    linha.querySelectorAll('.pu-dia').forEach(function (dia) {
      var vistos = 0;
      dia.querySelectorAll('li[data-fonte]').forEach(function (li) {
        var v = !fonte || li.getAttribute('data-fonte') === fonte;
        li.hidden = !v; if (v) vistos++;
      });
      // com filtro, os dias anteriores aparecem (a fonte escolhida pode só ter evento mais velho)
      dia.hidden = !vistos || (!todos && !fonte && dia.hasAttribute('data-pu-antigo'));
    });
    raiz.querySelectorAll('[data-pu-fonte]').forEach(function (c) {
      c.setAttribute('aria-pressed', c.getAttribute('data-pu-fonte') === fonte ? 'true' : 'false');
    });
    var mais = raiz.querySelector('[data-pu-mais]');
    if (mais) mais.parentNode.hidden = todos || !!fonte;
  }
  raiz.addEventListener('click', function (ev) {
    var c = ev.target.closest('[data-pu-fonte]');
    if (c) { fonte = c.getAttribute('data-pu-fonte'); aplicar(); return; }
    if (ev.target.closest('[data-pu-mais]')) { todos = true; aplicar(); }
  });
})();

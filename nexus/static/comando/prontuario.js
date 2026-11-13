/* O prontuário da usina (12/11/2026; comando/_prontuario.html). Os cartões vêm fechados (Levi: "primeiramente, dando um
   parecer geral, e quando a pessoa quiser se aprofundar, se aprofunda"): cada número do painel e cada pendência abrem
   o cartão deles; o endereço com #pu-<cartão> também. O número da OS abre o card dela (o do OS Creator); a linha do
   tempo filtra por fonte; o Relatório abre a janela do mês e dos temas. Sem este arquivo a página segue: os cartões
   abrem no clique (são <details>) e a OS fica como texto. */
(function () {
  'use strict';
  var raiz = document.querySelector('[data-pu]');
  if (!raiz) return;

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
        var grupo = t.closest('fieldset');
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
        t.closest('fieldset').querySelectorAll('input[name="campo"]').forEach(function (c) { c.checked = t.checked; });
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

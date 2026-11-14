/* Nexus IA na janela do prontuário (13/11/2026; as regras: nexus/comando/ia.py, a janela: comando/_ia.html).
   A janela chega como pedaço de página (prontuario.js põe o HTML no corpo dela), então tudo aqui é por delegação no
   documento. Cada pergunta vai em JSON para data-ia-url com os modelos marcados e as últimas perguntas e respostas (a
   pergunta de seguimento: "e no mês passado?"); a resposta de cada modelo vira um cartão, lado a lado quando há mais de
   um (o modo de comparar). O texto da IA é escapado antes de virar parágrafo, lista e negrito: nada dele vira HTML. */
(function () {
  'use strict';
  var historico = [];          // [{pergunta, resposta}] da usina aberta (a janela fechada zera: o corpo some)

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  }
  function num(v, casas) {
    return Number(v || 0).toLocaleString('pt-BR', {minimumFractionDigits: casas || 0, maximumFractionDigits: casas || 0});
  }
  // o mínimo de Markdown que as IAs escrevem: parágrafo, lista com "-" ou "*" ou "1.", e **negrito**
  function texto(md) {
    var linhas = esc(md).split(/\r?\n/), out = [], lista = null;
    function fecha() { if (lista) { out.push('</' + lista + '>'); lista = null; } }
    linhas.forEach(function (l) {
      var t = l.trim(), m = t.match(/^([-*•]|\d+[.)])\s+(.*)$/);
      if (m) {
        var tipo = /\d/.test(m[1]) ? 'ol' : 'ul';
        if (lista !== tipo) { fecha(); out.push('<' + tipo + '>'); lista = tipo; }
        out.push('<li>' + m[2] + '</li>');
      } else if (!t) { fecha(); }
      else { fecha(); out.push('<p>' + t.replace(/^#+\s*/, '') + '</p>'); }
    });
    fecha();
    return out.join('').replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
  }
  function cartao(r) {
    var cab = '<div class="ia-r-cab"><b>' + esc(r.rotulo) + '</b><span class="mudo">' + esc(r.provedor) + '</span></div>';
    if (!r.ok) {
      return '<article class="ia-r ia-r--erro">' + cab + '<p class="ia-r-erro" role="alert">' + esc(r.erro || 'Sem resposta.') + '</p>' +
        (r.ms ? '<p class="ia-r-pe mudo">' + num(r.ms / 1000, 1) + ' s</p>' : '') + '</article>';
    }
    var n = r.numeros || {n: 0, no_dossie: 0, fora: []};
    var conf = n.n ? '<span class="ia-num ia-num--' + (n.fora.length ? 'alerta' : 'ok') + '" title="' +
      (n.fora.length ? 'Fora do dossiê (cálculo da IA ou invenção): ' + esc(n.fora.join(', ')) : 'Todos os números da resposta estão no dossiê') +
      '">' + n.no_dossie + ' de ' + n.n + ' números no dossiê</span>' : '';
    var custo = 'US$ ' + num(r.custo_usd, 4) + (r.preco_oficial ? '' : ' (ref.)');
    return '<article class="ia-r">' + cab + '<div class="ia-r-texto">' + texto(r.texto) + '</div>' +
      (r.parou ? '<p class="ia-r-aviso">A resposta foi cortada (' + esc(r.parou) + ').</p>' : '') +
      '<p class="ia-r-pe">' + conf + '<span class="mudo">' + num(r.ms / 1000, 1) + ' s · ' + num(r.entrada + (r.cache_lido || 0)) +
      ' → ' + num(r.saida) + ' tokens · ' + custo + '</span></p></article>';
  }

  function enviar(raiz, pergunta) {
    var marcados = Array.prototype.map.call(raiz.querySelectorAll('[data-ia-modelo]:checked'), function (c) { return c.value; });
    var conversa = raiz.querySelector('[data-ia-conversa]'), campo = raiz.querySelector('[data-ia-pergunta]');
    var botao = raiz.querySelector('[data-ia-enviar]');
    pergunta = String(pergunta || '').trim();
    if (!pergunta) { campo.focus(); return; }
    var vazio = raiz.querySelector('[data-ia-vazio]');
    if (vazio) vazio.remove();
    var turno = document.createElement('section');
    turno.className = 'ia-turno';
    turno.innerHTML = '<p class="ia-pergunta">' + esc(pergunta) + '</p>' +
      (marcados.length ? '<div class="ia-respostas ia-respostas--' + Math.min(marcados.length, 3) + '"><p class="ia-lendo mudo">Lendo o dossiê e perguntando a ' +
        marcados.length + (marcados.length === 1 ? ' modelo' : ' modelos') + '…</p></div>'
        : '<p class="ia-r-erro" role="alert">Marque ao menos um modelo.</p>');
    conversa.appendChild(turno);
    turno.scrollIntoView({block: 'end'});
    if (!marcados.length) return;
    campo.value = '';
    botao.disabled = true;
    fetch(raiz.getAttribute('data-ia-url'), {
      method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
      body: JSON.stringify({pergunta: pergunta, modelos: marcados, historico: historico})
    }).then(function (r) {
      return r.json().catch(function () { return {ok: false, erro: 'Resposta inesperada (' + r.status + ').'}; });
    }).then(function (j) {
      var caixa = turno.querySelector('.ia-respostas');
      if (!j.ok) { caixa.innerHTML = '<p class="ia-r-erro" role="alert">' + esc(j.erro || 'Não respondeu.') + '</p>'; return; }
      caixa.innerHTML = j.respostas.map(cartao).join('');
      var primeira = j.respostas.filter(function (r) { return r.ok; })[0];
      if (primeira) historico = historico.concat([{pergunta: pergunta, resposta: primeira.texto}]).slice(-3);
      var g = raiz.querySelector('[data-ia-gasto]');
      if (g && j.gasto != null) g.textContent = 'US$ ' + num(j.gasto, 2);
    }).catch(function () {
      turno.querySelector('.ia-respostas').innerHTML = '<p class="ia-r-erro" role="alert">Sem conexão com o Nexus.</p>';
    }).then(function () { botao.disabled = false; campo.focus(); });
  }

  document.addEventListener('submit', function (ev) {
    var f = ev.target.closest && ev.target.closest('[data-ia-form]');
    if (!f) return;
    ev.preventDefault();
    var raiz = f.closest('[data-ia]');
    enviar(raiz, raiz.querySelector('[data-ia-pergunta]').value);
  });
  document.addEventListener('keydown', function (ev) {
    var c = ev.target;
    if (!c.matches || !c.matches('[data-ia-pergunta]') || ev.key !== 'Enter' || ev.shiftKey || ev.isComposing) return;
    ev.preventDefault();
    var raiz = c.closest('[data-ia]');
    if (!raiz.querySelector('[data-ia-enviar]').disabled) enviar(raiz, c.value);
  });
  document.addEventListener('click', function (ev) {
    var s = ev.target.closest('[data-ia-sugestao]');
    if (!s) return;
    var raiz = s.closest('[data-ia]');
    if (raiz.querySelector('[data-ia-enviar]').disabled) return;
    enviar(raiz, s.textContent);
  });
  // a janela que fecha leva a conversa junto (o corpo dela é esvaziado)
  var jan = document.getElementById('pu-jan');
  if (jan) jan.addEventListener('close', function () { historico = []; });
})();

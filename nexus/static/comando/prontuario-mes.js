/* O Nexus IA Insights do mês fechado (18/11/2026; a página: comando/usina_mes.html; as regras:
   nexus/comando/diagnostico_mes.py). Um por usina por mês: a primeira abertura manda a IA fazer (a rota responde
   "preparando" e a página segue), e quem abre depois lê o guardado. O texto da IA é escapado antes de virar HTML. */
(function () {
  'use strict';
  var el = document.querySelector('[data-pm-diag]');
  if (!el || !window.fetch) return;
  var frase = el.querySelector('[data-pm-frase]'), corpo = el.querySelector('[data-pm-corpo]'), fonte = el.querySelector('[data-pm-fonte]');
  var mes = el.getAttribute('data-pm-mes') || 'do mês';
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  }
  // a OS do item: a parada do COS abre o card da OS; o chamado, o Raio X (noutra aba)
  function os(n, tipo) {
    if (!n) return '';
    if (tipo === 'chamado') {
      return ' <a class="pu-diag-os" href="' + esc(nexusRota('/t/engenharia/equipe/os/')) + esc(n) + '?de=garantias" target="_blank" rel="noopener" title="Raio X da OS ' + esc(n) + ' (abre em outra aba)">Ver OS ' + esc(n) + '</a>';
    }
    return ' <button type="button" class="pu-diag-os" data-pm-os="' + esc(n) + '" title="Abrir o card da OS ' + esc(n) + '">Ver OS ' + esc(n) + '</button>';
  }
  var LISTAS = [['pesou', 'O que pesou no mês', 'critico'], ['feito', 'O que foi feito', 'ok'], ['pendente', 'Segue pendente', 'alerta']];
  function desenhar(j) {
    var d = j.diag;
    if (d) {
      frase.textContent = d.situacao;
      frase.classList.add('pu-par-t--ia');
      corpo.innerHTML = LISTAS.map(function (l) {
        var itens = d[l[0]] || [];
        if (!itens.length) return '';
        return '<div class="pu-diag-col pu-diag-col--' + l[2] + '"><h3>' + l[1] + '</h3><ul>' + itens.map(function (x) {
          return '<li>' + esc(x.texto) + os(x.os, x.os_tipo) + '</li>';
        }).join('') + '</ul></div>';
      }).join('');
    } else {
      frase.textContent = 'O diagnóstico de ' + mes;
      corpo.innerHTML = '<p class="pu-diag-texto">' + esc(j.texto) + '</p>';
    }
    corpo.hidden = !corpo.innerHTML;
    fonte.textContent = 'Diagnóstico da IA sobre ' + mes + ', feito em ' + (j.data || '') + (j.hora ? ' às ' + j.hora : '') +
      (j.rotulo ? ' pelo ' + j.rotulo : '') + ', com os números do fechamento do mês. É um por mês: quem abrir vê este mesmo.' +
      (j.troca ? ' ' + j.troca : '') + (j.conferir && j.conferir.length ? ' A conferir: ' + j.conferir.join('; ') + '.' : '');
    fonte.hidden = false;
  }
  function carregar(vez) {
    fetch(el.getAttribute('data-pm-diag'), {credentials: 'same-origin', headers: {'Accept': 'application/json'}})
      .then(function (r) { return r.ok ? r.json() : {estado: 'fora'}; })
      .then(function (j) {
        if (j.estado === 'pronto' || j.estado === 'texto') { desenhar(j); return; }
        if (j.estado === 'preparando') {
          frase.textContent = 'A IA está lendo o fechamento de ' + mes + '…';
          fonte.textContent = 'Só na primeira abertura: depois o diagnóstico do mês fica guardado.';
          fonte.hidden = false;
          if (vez < 60) setTimeout(function () { carregar(vez + 1); }, 3000);
          return;
        }
        frase.textContent = 'Os números de ' + mes + ' estão abaixo.';
        fonte.textContent = j.estado === 'sem_ia' ? 'Sem IA ligada neste servidor: o diagnóstico do mês não foi feito.'
          : 'O diagnóstico da IA não saiu agora (' + (j.erro || 'sem resposta') + '). A IA tenta de novo em 20 minutos.';
        fonte.hidden = false;
      })
      .catch(function () { frase.textContent = 'Os números de ' + mes + ' estão abaixo.'; });
  }
  el.addEventListener('click', function (ev) {
    var b = ev.target.closest('[data-pm-os]');
    if (b && window.NexusOsCard) window.NexusOsCard.abrirFolio(String(b.getAttribute('data-pm-os')), {status: ''});
  });
  carregar(0);
})();

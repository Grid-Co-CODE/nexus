/* Tema do Nexus: ?tema=claro|escuro na URL, ou postMessage({tipo:'tema', tema:'escuro'}) da página que embute. */
(function(){
 function aplicar(t){ t = t==='escuro'?'escuro':'claro';
  document.querySelectorAll('.tela').forEach(function(e){ e.classList.toggle('escuro', t==='escuro'); });
  document.documentElement.setAttribute('data-tema', t); }
 aplicar(new URLSearchParams(location.search).get('tema'));
 addEventListener('message', function(ev){ var d = ev.data||{}; if(d && d.tipo==='tema') aplicar(d.tema); });
})();

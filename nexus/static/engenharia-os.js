/* A OS do Fracttal nas telas da Engenharia: o PDF e o card do OS Creator.

   O PDF (24/10/2026, a seta da cadeia da página da OS do Quadro; 30/10/2026 também nas últimas OS da gaveta do ativo,
   Levi: "Também deve ser possível baixar o PDF da OS, bote um botão de download!"): o POST monta o PDF no servidor do OS
   Creator (as fotos vêm do Fracttal) e o arquivo baixa pelo link que ele devolve. Sem a sessão do Fracttal, o aviso traz
   o login dele, que volta para a tela. O botão: [data-os-pdf="<nº>"] (e data-wid); o aviso: o [data-pdf-msg] da caixa
   [data-pdf-caixa] (o data-login-fracttal dela é o login).

   O card (30/10/2026, Levi: "Ao clicar na OS deve aparecer o card da OS que aparece quando clicamos em uma OS no OS
   Creator!"): [data-os-card] com data-wid e data-folio abre o NexusOsCard (oscreator/card_os_abrir.html, que a tela
   inclui) por cima da tela. */
(function () {
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-os-pdf]'); if (!b) return;
    e.preventDefault();
    if (b.getAttribute('aria-busy') === 'true') return;
    var caixa = b.closest('[data-pdf-caixa]') || document, msg = caixa.querySelector('[data-pdf-msg]');
    var folio = b.getAttribute('data-os-pdf');
    function dizer(texto, ruim, link) {
      if (!msg) return;
      msg.replaceChildren(document.createTextNode(texto || ''));
      if (link) { var a = document.createElement('a'); a.href = link; a.textContent = 'Entrar pelo Fracttal'; msg.appendChild(document.createTextNode(' ')); msg.appendChild(a); }
      msg.hidden = !texto; msg.classList.toggle('eg-os-msg--ruim', !!ruim);
    }
    b.setAttribute('aria-busy', 'true'); dizer('Montando o PDF da OS ' + folio + '…');
    fetch(nexusRota('/os/api/os/pdf'), {method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
      body: JSON.stringify({folio: folio, wid: b.getAttribute('data-wid') || ''})})
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { return {r: r, j: j}; }); })
      .then(function (x) {
        if (x.r.ok && x.j.url) {
          var a = document.createElement('a');
          a.href = nexusRota(x.j.url); a.download = x.j.nome || '';
          document.body.appendChild(a); a.click(); a.remove();
          dizer(x.j.falhas ? ('PDF da OS ' + folio + ' baixado; ' + x.j.falhas + ' foto(s) não vieram do Fracttal.') : '', !!x.j.falhas);
        } else if (x.j.sessao_encerrada) { location.href = x.j.entrar || location.href; }
        else if (x.j.login) { dizer('Para baixar o PDF, entre pelo Fracttal.', true, caixa.getAttribute('data-login-fracttal')); }
        else { dizer('Não consegui montar o PDF da OS ' + folio + ': ' + (x.j.erro || ('HTTP ' + x.r.status)), true); }
      })
      .catch(function () { dizer('Não consegui falar com o Nexus. Tente de novo.', true); })
      .then(function () { b.removeAttribute('aria-busy'); });
  });
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-os-card]'); if (!b) return;
    e.preventDefault();
    if (!window.NexusOsCard) return;
    NexusOsCard.abrir(b.getAttribute('data-wid'), {status: b.getAttribute('data-status') || '', folio: b.getAttribute('data-folio')});
  });
})();

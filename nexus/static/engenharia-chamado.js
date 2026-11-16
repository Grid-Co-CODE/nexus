/* O chamado de garantia no Raio X da OS (16/11/2026, Levi: "A OS de garantia está abrindo um chamado dentro do chamado";
   no quiz, "Uma página só"): as escritas dos blocos do chamado (engenharia/_chamado.html) vão às MESMAS rotas da tela do
   chamado do OS Creator (/os/api/acomp/<nº>/...), com o cookie dele, e as regras delas valem igual: o status do chamado,
   o ticket, a observação (o 1º comentário inicia a atividade da OS no Fracttal), editar e excluir a observação (o setor
   e o administrador, a regra da ponte) e o Finalizar (encerra a atividade e conclui a OS). Sem a sessão do Fracttal, o
   aviso traz o login. A raiz: o [data-ch-raiz] da página (o nº, o id, o ativo, o começo das rotas e o login). */
(function () {
  var raiz = document.querySelector('[data-ch-raiz]');
  if (!raiz) return;
  var base = raiz.getAttribute('data-base'), wid = raiz.getAttribute('data-wid');
  var ativo = raiz.getAttribute('data-ativo'), login = raiz.getAttribute('data-login');

  function dizer(caixa, texto, ruim, comLogin) {
    var msg = caixa && caixa.querySelector('.eg-os-msg');
    if (!msg) { if (texto) window.alert(texto); return; }
    msg.replaceChildren(document.createTextNode(texto || ''));
    if (comLogin && login) {
      var a = document.createElement('a'); a.href = login; a.textContent = 'Entrar pelo Fracttal';
      msg.appendChild(document.createTextNode(' ')); msg.appendChild(a);
    }
    msg.hidden = !texto; msg.classList.toggle('eg-os-msg--ruim', !!ruim);
  }
  function postar(caminho, corpo) {
    return fetch(base + caminho, {method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/json', 'Accept': 'application/json', 'X-Requested-With': 'fetch'},
      body: JSON.stringify(corpo || {})})
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (j) {
          if (r.status === 401 || j.login) { var e = new Error('Para gravar no chamado, entre pelo Fracttal.'); e.login = true; throw e; }
          if (!r.ok || j.erro) throw new Error(j.erro || ('HTTP ' + r.status));
          return j;
        });
      });
  }
  function recarregar(ms) { window.setTimeout(function () { window.location.reload(); }, ms || 900); }
  // a resposta da atividade no Fracttal (o 1º comentário, o comentário apagado): a frase dela, ou o aviso
  function daAtividade(j) { var a = (j && j.atividade) || {}; return a.mensagem || a.aviso || ''; }

  function acao(b) {
    var caixa = b.closest('[data-ch-caixa]'), tipo = b.getAttribute('data-ch-acao'), corpo, caminho, ok;
    if (tipo === 'status') {
      caminho = '/status'; corpo = {status: caixa.querySelector('[data-ch-status]').value, wid: wid}; ok = 'Status gravado.';
    } else if (tipo === 'ticket') {
      var tk = caixa.querySelector('[data-ch-ticket]').value.trim();
      if (!tk) { dizer(caixa, 'Escreva o nº do ticket ou do protocolo.', true); return; }
      caminho = '/ticket'; corpo = {ticket: tk, wid: wid}; ok = 'Ticket gravado.';
    } else if (tipo === 'obs') {
      var tx = caixa.querySelector('[data-ch-texto]').value.trim();
      if (!tx) { dizer(caixa, 'Escreva a observação antes de salvar.', true); return; }
      caminho = '/obs'; corpo = {texto: tx, ativo: ativo, wid: wid}; ok = 'Salvo.';
    } else { return; }
    b.disabled = true; dizer(caixa, 'Gravando…');
    postar(caminho, corpo).then(function (j) {
      var at = daAtividade(j);
      dizer(caixa, (j.mensagem || ok) + (at ? ' ' + at : ''));
      recarregar(at ? 2600 : 900);
    }, function (e) { b.disabled = false; dizer(caixa, e.message, true, e.login); });
  }

  function mexerObs(b) {
    var caixa = b.closest('[data-ch-obs-id]'), id = caixa.getAttribute('data-ch-obs-id'), tipo = b.getAttribute('data-ch-obs-acao');
    var corpo = {wid: wid};
    if (tipo === 'editar') {
      corpo.texto = caixa.querySelector('textarea').value.trim();
      if (!corpo.texto) { dizer(caixa, 'A observação não pode ficar vazia: para tirá-la, use o Excluir.', true); return; }
    } else if (!window.confirm('Excluir esta observação? Ela sai da linha do tempo (o banco guarda quem excluiu e quando).')) {
      return;
    }
    b.disabled = true; dizer(caixa, tipo === 'editar' ? 'Gravando…' : 'Excluindo…');
    postar('/obs/' + encodeURIComponent(id) + '/' + tipo, corpo).then(function (j) {
      var at = daAtividade(j);
      dizer(caixa, at || (tipo === 'editar' ? 'Editada.' : 'Excluída.'));
      recarregar(at ? 2600 : 700);
    }, function (e) { b.disabled = false; dizer(caixa, e.message, true, e.login); });
  }

  function finalizar(b) {
    var topo = document.querySelector('[data-ch-msg-topo]');
    var caixa = topo ? {querySelector: function () { return topo; }} : null;
    if (!window.confirm('Finalizar o chamado? A atividade é encerrada e a OS ' + raiz.getAttribute('data-folio') +
                        ' é concluída no Fracttal. Não tem volta pela tela.')) return;
    b.disabled = true; dizer(caixa, 'Finalizando…');
    postar('/finalizar', {wid: wid}).then(function (j) {
      dizer(caixa, [j.mensagem, j.aviso, j.aviso_obs].filter(Boolean).join(' '));
      recarregar(2600);
    }, function (e) { b.disabled = false; dizer(caixa, e.message, true, e.login); });
  }

  function copiar(b) {
    var texto = b.getAttribute('data-ch-copiar') || '';
    var feito = function () { var t = b.textContent; b.textContent = 'Copiado'; window.setTimeout(function () { b.textContent = t; }, 1400); };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(texto).then(feito, function () {});
  }

  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-ch-acao]');
    if (b) { acao(b); return; }
    b = e.target.closest('[data-ch-obs-acao]');
    if (b) { mexerObs(b); return; }
    b = e.target.closest('[data-ch-finalizar]');
    if (b) { finalizar(b); return; }
    b = e.target.closest('[data-ch-copiar]');
    if (b) copiar(b);
  });
})();

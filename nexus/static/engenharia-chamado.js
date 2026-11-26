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

/* A Nova demanda do chamado (24/11/2026; o mockup aprovado): a demanda da Caixa de entrada dentro do chamado de Garantias.
   As listas são as digitáveis do Nexus (`lista-sugestoes.js`, input[data-lista]): o texto escolhido vira o valor escondido
   (o setor, a pessoa, o tema). Ao abrir, as pessoas com setor vêm do servidor (a mesma lista da Caixa); o setor da
   Supervisão Campo já vem escolhido, com o supervisor de campo da usina (achado pelo nome do cadastro) e o tema
   "Acompanhamento de chamado" (Levi: "quando a pessoa escolhe supervisor de campo, já puxa automaticamente o supervisor
   de campo daquela usina"). A usina e a OS vão do chamado, fixas no formulário. */
(function () {
  var veu = document.querySelector('[data-dm-ch]');
  if (!veu) return;
  var form = veu.querySelector('[data-dm-ch-form]'), dados = {};
  try { dados = JSON.parse(document.getElementById('dm-ch-dados').textContent) || {}; } catch (e) { dados = {}; }
  var setores = dados.setores || [], temas = dados.temas || [], pessoas = null, carregando = null;
  var sem = (window.ListaSugestoes && window.ListaSugestoes.sem) ||
    function (s) { return String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, ' ').trim(); };
  function campo(k) { return form.querySelector('[data-dm-ch-t="' + k + '"]'); }
  function valor(k) { return form.querySelector('[data-dm-ch-v="' + k + '"]'); }
  var msg = form.querySelector('[data-dm-ch-msg]'), sug = form.querySelector('[data-dm-ch-sug]');
  function dizer(t) { msg.textContent = t || ''; msg.hidden = !t; }
  // a lista de um campo: um <script type="application/json"> com id próprio (a lista-sugestoes guarda cada id que leu)
  function lista(id, nomes) {
    var no = document.getElementById(id);
    if (!no) {
      no = document.createElement('script'); no.type = 'application/json'; no.id = id;
      no.textContent = JSON.stringify(nomes); document.body.appendChild(no);
    }
    return id;
  }
  function idDe(prefixo, v) { return prefixo + String(v).replace(/[^a-z0-9]+/gi, '-'); }
  // o que a pessoa vê de cada setor e o valor que vai: "Supervisão Campo" vira "7"; a área "Chamados", "2:Chamados"
  function setorDoTexto(t) {
    var a = sem(t), s = setores.filter(function (x) { return sem(x[1]) === a; })[0];
    return s ? s[0] : '';
  }
  function pessoasDoSetor(v) {
    if (!pessoas) return [];
    var partes = String(v).split(':'), sid = parseInt(partes[0], 10), area = partes.slice(1).join(':');
    var ps = pessoas.filter(function (p) { return p.setor_id === sid; });
    if (area) {                                    // a área com gente marcada recebe só nela (a regra da Caixa)
      var marcadas = ps.filter(function (p) { return (p.areas || []).indexOf(area) >= 0; });
      if (marcadas.length) ps = marcadas;
    }
    return ps;
  }
  function temasDoSetor(v) { return temas.filter(function (t) { return t.setor === String(v); }); }
  // o nome do cadastro (o curto, "Nome padrão") e o do Fracttal (o completo): o mesmo 1º nome, e as palavras do mais
  // curto aparecem no mais comprido, na mesma ordem ("Fulana Souza" acha "Fulana de Tal Souza")
  function mesmoNome(a, b) {
    var x = sem(a).split(' '), y = sem(b).split(' ');
    if (!x[0] || !y[0] || x[0] !== y[0]) return false;
    var curto = x.length <= y.length ? x : y, longo = curto === x ? y : x, i = 0;
    longo.forEach(function (w) { if (i < curto.length && w === curto[i]) i++; });
    return i === curto.length;
  }
  function aoPessoa() {
    var a = sem(campo('pessoa').value), v = valor('setor').value;
    var p = pessoasDoSetor(v).filter(function (x) { return sem(x.nome) === a; })[0];
    valor('pessoa').value = p ? p.hmac : '';
  }
  function aoTema() {
    var a = sem(campo('tema').value), v = valor('setor').value;
    var t = temasDoSetor(v).filter(function (x) { return sem(x.nome) === a; })[0];
    valor('tema').value = t ? t.tema_id : '';
  }
  function aoSetor(manter) {
    var v = setorDoTexto(campo('setor').value), mudou = valor('setor').value !== v;
    var p = campo('pessoa'), t = campo('tema');
    valor('setor').value = v;
    sug.hidden = true;
    if (!v) {
      if (!manter) { p.value = ''; valor('pessoa').value = ''; t.value = ''; valor('tema').value = ''; }
      p.setAttribute('data-lista', 'dm-ch-pessoas-vazio');
      t.setAttribute('data-lista', 'dm-ch-temas-vazio');
      p.placeholder = t.placeholder = 'Escolha o setor primeiro';
      return;
    }
    p.setAttribute('data-lista', pessoas ? lista(idDe('dm-ch-p-', v), pessoasDoSetor(v).map(function (x) { return x.nome; }))
                                         : 'dm-ch-pessoas-vazio');
    t.setAttribute('data-lista', lista(idDe('dm-ch-t-', v), temasDoSetor(v).map(function (x) { return x.nome; })));
    p.placeholder = pessoas ? 'Digite ou escolha' : 'Carregando as pessoas…';
    t.placeholder = 'Digite ou escolha';
    if (mudou && !manter) { p.value = ''; valor('pessoa').value = ''; t.value = ''; valor('tema').value = ''; }
    if (v === String(dados.sugerido)) {
      var sup = dados.supervisor ? pessoasDoSetor(v).filter(function (x) { return mesmoNome(x.nome, dados.supervisor); })[0] : null;
      if (sup && !p.value) { p.value = sup.nome; aoPessoa(); }
      if (dados.supervisor) {
        sug.textContent = 'Sugerido: ' + (sup ? sup.nome : dados.supervisor) + ', supervisor de campo da usina' +
          (sup || !pessoas ? '' : ' (não achei no setor com esse nome: escolha na lista)');
        sug.hidden = false;
      }
      var tp = temas.filter(function (x) { return x.tema_id === dados.tema_padrao; })[0];
      if (tp && !t.value) { t.value = tp.nome; aoTema(); }
    }
  }
  campo('setor').addEventListener('input', function () { aoSetor(false); });
  campo('pessoa').addEventListener('input', aoPessoa);
  campo('tema').addEventListener('input', aoTema);
  function carregar() {
    if (pessoas) return Promise.resolve();
    if (carregando) return carregando;
    carregando = fetch(dados.pessoas_url, {credentials: 'same-origin', headers: {'Accept': 'application/json'}})
      .then(function (r) { return r.json(); })
      .then(function (j) {
        pessoas = (j && j.pessoas) || [];
        if (!j || j.ok === false) dizer('Não consegui ler a lista de pessoas agora: recarregue a página.');
      })
      .catch(function () { pessoas = []; dizer('Não consegui ler a lista de pessoas agora: recarregue a página.'); })
      .then(function () { carregando = null; aoSetor(true); });
    return carregando;
  }
  function abrir() {
    veu.hidden = false;
    dizer('');
    if (!campo('setor').value) {
      var s = setores.filter(function (x) { return x[0] === String(dados.sugerido); })[0];
      if (s) campo('setor').value = s[1];
    }
    aoSetor(true);
    carregar().then(function () {
      var alvo = !valor('setor').value ? campo('setor') : !valor('pessoa').value ? campo('pessoa')
        : !valor('tema').value ? campo('tema') : form.querySelector('[name="titulo"]');
      alvo.focus();
    });
  }
  function fechar() { veu.hidden = true; }
  document.addEventListener('click', function (e) {
    if (e.target.closest('[data-dm-ch-abrir]')) { abrir(); return; }
    if (e.target.closest('[data-dm-ch-fechar]') || e.target === veu) fechar();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !veu.hidden && !document.querySelector('.ls-menu:not([hidden])')) fechar();
  });
  form.addEventListener('submit', function (e) {
    aoPessoa(); aoTema();
    if (!valor('setor').value || !valor('pessoa').value || !valor('tema').value) {
      e.preventDefault();
      dizer(!valor('setor').value ? 'Escolha o setor da lista.' : !valor('pessoa').value ? 'Escolha a pessoa da lista do setor.'
        : 'Escolha o tema da lista do setor.');
    }
  });
  if (location.hash === '#demandas' && /[?&](ok|erro)=/.test(location.search)) {
    var b = document.getElementById('demandas');
    if (b) b.scrollIntoView();
  }
})();

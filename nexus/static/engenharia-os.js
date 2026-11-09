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

/* As ações da OS na página da OS do Quadro (06/11/2026, Levi: "poderia incluir um botão de incluir anexo?"; "Nessas telas
   devem ter essas opção também: Enviar para verificação, concluir e cancelar!"). A caixa [data-os-acoes-eng]:
   - a contagem dos anexos é a do card (/os/os/<id>/anexos), lida ao abrir e depois de incluir;
   - [data-card-acao] abre o card do OS Creator já na ação (o NexusOsCard com `acao`): o diálogo e a regra são os dele, e
     a página relê quando o card mudou a OS;
   - o Incluir anexo sobe daqui (o seletor só abre com o clique nesta página, não dentro da moldura do card): o POST
     /os/api/os/<id>/anexos, que relê a OS e diz o que subiu e o que não. Sem a sessão do Fracttal, o aviso traz o login. */
(function () {
  var caixa = document.querySelector('[data-os-acoes-eng]'); if (!caixa) return;
  var msg = caixa.querySelector('[data-acoes-msg]'), inp = caixa.querySelector('[data-anexo-arquivos]');
  var btn = caixa.querySelector('[data-incluir-anexo]');
  function dizer(texto, ruim, link) {
    msg.replaceChildren(document.createTextNode(texto || ''));
    if (link) { var a = document.createElement('a'); a.href = link; a.textContent = 'Entrar pelo Fracttal'; msg.appendChild(document.createTextNode(' ')); msg.appendChild(a); }
    msg.hidden = !texto; msg.classList.toggle('eg-os-msg--ruim', !!ruim);
  }
  function contar() {
    fetch(caixa.dataset.anexosUrl, {credentials: 'same-origin', headers: {'Accept': 'application/json'}})
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { caixa.querySelectorAll('[data-n]').forEach(function (b) { var v = j ? j[b.getAttribute('data-n')] : null; b.textContent = (v === null || v === undefined) ? '—' : v; }); })
      .catch(function () { caixa.querySelectorAll('[data-n]').forEach(function (b) { b.textContent = '—'; }); });
  }
  contar();
  caixa.addEventListener('click', function (e) {
    var b = e.target.closest('[data-card-acao]');
    if (b) {
      e.preventDefault();
      if (!window.NexusOsCard) return;
      NexusOsCard.abrir(caixa.dataset.wid, {folio: caixa.dataset.folio, acao: b.getAttribute('data-card-acao'),
        aoFechar: function (mudou) { if (mudou) location.reload(); else contar(); }});
      return;
    }
    // o Incluir anexo abre o cartão do anexo (09/11/2026): colar, soltar ou o "faça o upload do anexo"
    if (e.target.closest('[data-incluir-anexo]') && inp) {
      window.egCartaoAnexo({alvo: 'na OS ' + (caixa.dataset.folio || ''), aceitar: inp.getAttribute('accept') || '',
        regra: btn.getAttribute('title') || '', enviar: enviar});
    }
  });
  if (!inp) return;
  inp.addEventListener('change', function () {
    var fs = Array.prototype.slice.call(inp.files || []); if (fs.length) enviar(fs).catch(function () {});
  });
  // colar para anexar (06/11/2026: "No anexo pode ser possível anexar com CTRL + V OU WINDOWS + V"): o arquivo da área de
  // transferência espera o "Anexar à OS" (colar sem querer não sobe nada); colar num campo de texto segue sendo texto. A
  // imagem colada ("image.png") ganha o nome com a data e a hora
  function nomeColado(f, i) {
    if (f.name && !/^image\.(png|jpe?g|gif|webp|bmp)$/i.test(f.name)) return f;
    function p(n) { return String(n).padStart(2, '0'); }
    var a = new Date(), ext = ((f.type || '').split('/')[1] || 'png').replace('jpeg', 'jpg');
    return new File([f], 'colado ' + a.getFullYear() + '-' + p(a.getMonth() + 1) + '-' + p(a.getDate()) + ' ' + p(a.getHours())
      + 'h' + p(a.getMinutes()) + 'm' + p(a.getSeconds()) + 's' + (i ? ' ' + (i + 1) : '') + '.' + ext, {type: f.type});
  }
  document.addEventListener('paste', function (e) {
    var t = e.target;
    if (document.querySelector('dialog.eg-anx[open]')) return;        // o cartão do anexo aberto recebe o colar
    if (t && t.closest && t.closest('input, textarea, select, [contenteditable="true"]')) return;
    var fs = Array.prototype.slice.call((e.clipboardData && e.clipboardData.files) || []).map(nomeColado);
    if (!fs.length) return;
    e.preventDefault();
    var velho = caixa.querySelector('[data-anexo-colado]'); if (velho) velho.remove();
    var linha = document.createElement('div');
    linha.className = 'eg-os-acoes-l'; linha.setAttribute('data-anexo-colado', '');
    var txt = document.createElement('span');
    txt.textContent = (fs.length === 1 ? '1 arquivo colado: ' : fs.length + ' arquivos colados: ') + fs.map(function (f) { return f.name; }).join(', ');
    var sim = document.createElement('button'), nao = document.createElement('button');
    sim.type = nao.type = 'button';
    sim.className = 'eg-ac-btn eg-ac-btn--g eg-ac-btn--p'; sim.textContent = 'Anexar à OS';
    nao.className = 'eg-ac-btn eg-ac-btn--o eg-ac-btn--p'; nao.textContent = 'Descartar';
    sim.addEventListener('click', function () { linha.remove(); enviar(fs).catch(function () {}); });
    nao.addEventListener('click', function () { linha.remove(); });
    linha.appendChild(txt); linha.appendChild(sim); linha.appendChild(nao);
    caixa.querySelector('[data-grupo-anexos]').appendChild(linha);
  });
  function enviar(fs) {
    var fd = new FormData();
    fs.forEach(function (f) { fd.append('anexos', f, f.name); });
    fd.append('folio', caixa.dataset.folio || '');
    btn.disabled = true;
    dizer(fs.length === 1 ? 'Enviando o anexo para o Fracttal…' : 'Enviando ' + fs.length + ' anexos para o Fracttal…');
    // devolve a promessa (o cartão do anexo diz o resultado nele): a mensagem, ou o erro com o login quando falta
    return fetch(caixa.dataset.incluirUrl, {method: 'POST', credentials: 'same-origin', headers: {'Accept': 'application/json'}, body: fd})
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { return {r: r, j: j}; }); },
        function () { btn.disabled = false; var m = 'Não consegui falar com o OS Creator. Tente de novo.'; dizer(m, true); throw new Error(m); })
      .then(function (x) {
        btn.disabled = false;
        if (x.r.status === 401 || x.j.login) {
          dizer('Para incluir anexo, entre pelo Fracttal.', true, caixa.dataset.login);
          var e = new Error('Para incluir anexo, entre pelo Fracttal.'); e.login = caixa.dataset.login; throw e;
        }
        if (x.j.mensagem) { dizer(x.j.mensagem, !x.j.ok); contar(); if (!x.j.ok) throw new Error(x.j.mensagem); return x.j.mensagem; }
        var m = x.j.erro || ('O OS Creator não gravou (HTTP ' + x.r.status + '). Nada mudou; tente de novo.');
        dizer(m, true); throw new Error(m);
      });
  }
})();

/* As tarefas da OS, uma a uma (06/11/2026): a caixa [data-tarefas-os] da página da OS. Cada tarefa (o ativo) com o check
   quando concluída (a tarefa com fim no Fracttal), as subtarefas respondidas, "x anexos" e, para quem pode, Subtarefas
   (responder), Anexar (na tarefa), Iniciar, Pausar (com o motivo), Retomar e Concluir: o cronômetro do Fracttal pelo OS
   Creator (/os/api/os/<id>/tarefa/<tid>/cronometro), que relê o estado depois de cada passo. Os diálogos são <dialog>
   da página. Sem a sessão do Fracttal, fica a lista do REST e o aviso traz o login. */
(function () {
  var caixa = document.querySelector('[data-tarefas-os]'); if (!caixa) return;
  var lista = caixa.querySelector('[data-tarefas-lista]'), msg = caixa.querySelector('[data-tarefas-msg]');
  var inp = caixa.querySelector('[data-tarefa-arquivos]'), rest = caixa.querySelector('[data-tarefas-rest]');
  var pode = caixa.dataset.acoes === 'sim', tarefas = [], anexos = {fotos: {}, arquivos: {}};
  function esc(t) { return String(t == null ? '' : t).replace(/[&<>"']/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]; }); }
  function dizer(texto, ruim, link) {
    msg.replaceChildren(document.createTextNode(texto || ''));
    if (link) { var a = document.createElement('a'); a.href = link; a.textContent = 'Entrar pelo Fracttal'; msg.appendChild(document.createTextNode(' ')); msg.appendChild(a); }
    msg.hidden = !texto; msg.classList.toggle('eg-os-msg--ruim', !!ruim);
  }
  function pedir(url, corpo) {
    var op = {credentials: 'same-origin', headers: {'Accept': 'application/json'}};
    if (corpo instanceof FormData) { op.method = 'POST'; op.body = corpo; }
    else if (corpo !== undefined) { op.method = 'POST'; op.headers['Content-Type'] = 'application/json'; op.body = JSON.stringify(corpo); }
    return fetch(url, op).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (r.status === 401 || j.login) { var e = new Error('Para mexer na tarefa, entre pelo Fracttal.'); e.login = true; throw e; }
        if (!r.ok && !(j && j.incluidos && j.incluidos.length)) throw new Error(j.erro || ('HTTP ' + r.status));
        return j;
      });
    });
  }
  function falhou(e) { dizer(e.message, true, e.login ? caixa.dataset.login : ''); }
  // o início do cronômetro vem do Fracttal em UTC e sem o fuso (na prova no ar de 06/11/2026, "15:38" era 12:38 em
  // Brasília): lido como UTC, sai na hora de quem olha
  function hora(iso) {
    if (!iso) return '';
    var d = new Date(/(Z|[+-]\d\d:?\d\d)$/.test(iso) ? iso : iso + 'Z');
    return isNaN(d.getTime()) ? '' : String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
  }
  function botao(texto, acao, classe) {
    return '<button type="button" class="eg-ac-btn eg-ac-btn--p ' + (classe || 'eg-ac-btn--o') + '" data-tarefa-acao="' + acao + '">' + texto + '</button>';
  }
  function pintar() {
    lista.innerHTML = tarefas.map(function (t) {
      var e = t.execucao || {}, n = (anexos.fotos[String(t.id)] || 0) + (anexos.arquivos[String(t.id)] || 0), partes = [];
      if (t.titulo && t.titulo !== t.ativo) partes.push(esc(t.titulo));
      if (t.total) partes.push(t.feitas + ' de ' + t.total + (t.total === 1 ? ' subtarefa' : ' subtarefas'));
      partes.push(n === 1 ? '1 anexo' : n + ' anexos');
      if (e.estado === 'rodando') partes.push('em andamento' + (hora(e.inicio) ? ' desde ' + hora(e.inicio) : ''));
      else if (e.estado === 'pausada') partes.push('pausada' + (e.motivo ? ' (' + esc(e.motivo) + ')' : ''));
      var bts = '';
      if (pode) {
        bts = botao('Subtarefas', 'subtarefas') + botao('Anexar', 'anexar');
        if (!t.feita && e.estado === 'parada') bts += botao('Iniciar', 'iniciar', 'eg-ac-btn--g');
        if (e.estado === 'rodando') bts += botao('Pausar', 'pausar');
        if (e.estado === 'pausada') bts += botao('Retomar', 'retomar', 'eg-ac-btn--g');
        if (e.estado === 'rodando' || e.estado === 'pausada') bts += botao('Concluir', 'concluir', 'eg-ac-btn--g');
      }
      return '<div class="eg-tar' + (t.feita ? ' eg-tar--feita' : '') + '" data-tid="' + esc(t.id) + '">'
        + '<span class="eg-tar-ok" ' + (t.feita ? 'title="Tarefa concluída" aria-label="Tarefa concluída">✓' : 'aria-hidden="true">') + '</span>'
        + '<div class="eg-tar-t"><b>' + esc(t.ativo || t.titulo || 'Tarefa ' + t.n) + '</b><small>' + partes.join(' · ') + '</small></div>'
        + (bts ? '<div class="eg-tar-b">' + bts + '</div>' : '') + '</div>';
    }).join('');
  }
  function carregar() {
    return Promise.all([pedir(caixa.dataset.tarefasUrl), pedir(caixa.dataset.anexosUrl).catch(function () { return {}; })])
      .then(function (r) {
        // o "x anexos" do ativo: as fotos das subtarefas dela e os arquivos da aba Anexos dela (onde o Anexar grava)
        tarefas = r[0].tarefas || []; anexos = {fotos: (r[1] && r[1].por_tarefa) || {}, arquivos: (r[1] && r[1].arquivos_por_tarefa) || {}};
        if (!tarefas.length) return;
        pintar(); lista.hidden = false; if (rest) rest.hidden = true;
      })
      .catch(function (e) { if (e.login) dizer('Para ver as tarefas e o cronômetro, entre pelo Fracttal.', false, caixa.dataset.login); });
  }
  carregar();

  // o diálogo da página (as subtarefas e o motivo da pausa): um <dialog> por vez
  function dialogo(titulo, corpo, okTexto, aoOk) {
    var d = document.createElement('dialog'); d.className = 'eg-dlg';
    d.innerHTML = '<form method="dialog"><h3>' + esc(titulo) + '</h3><div class="eg-dlg-c">' + corpo + '</div>'
      + '<p class="eg-dlg-hint" data-hint></p><div class="eg-dlg-b"><button type="button" class="eg-ac-btn eg-ac-btn--o eg-ac-btn--p" data-fechar>Fechar</button>'
      + '<button type="submit" class="eg-ac-btn eg-ac-btn--g eg-ac-btn--p">' + esc(okTexto) + '</button></div></form>';
    document.body.appendChild(d);
    var hint = d.querySelector('[data-hint]'), ok = d.querySelector('[type=submit]');
    d.querySelector('[data-fechar]').addEventListener('click', function () { d.close(); });
    d.addEventListener('close', function () { d.remove(); });
    d.querySelector('form').addEventListener('submit', function (ev) {
      ev.preventDefault(); ok.disabled = true; hint.textContent = 'gravando no Fracttal…';
      Promise.resolve(aoOk(d)).then(function () { d.close(); })
        .catch(function (e) { ok.disabled = false; hint.textContent = e.message; });
    });
    d.showModal();
    return d;
  }
  function campo(c) {
    var id = 'tc' + c.id_form_item, req = c.obrigatorio ? ' <span class="eg-dlg-req">obrigatória</span>' : '', ctrl;
    if ((c.opcoes || []).length) {
      ctrl = '<select class="eg-ac-campo" data-fid="' + esc(c.id_form_item) + '" id="' + id + '"><option value="">— selecione —</option>'
        + c.opcoes.map(function (o) { return '<option value="' + esc(o.valor) + '"' + (String(o.valor) === String(c.valor) ? ' selected' : '') + '>' + esc(o.rotulo) + '</option>'; }).join('') + '</select>';
    } else if (c.tipo_nome === 'num') {
      // o número com vírgula (o teclado do Brasil): campo de texto com o teclado numérico, e a vírgula vira ponto no envio,
      // que é o que o campo numérico do card manda (o type=number recusava "7,9" e a resposta saía vazia)
      ctrl = '<input class="eg-ac-campo" type="text" inputmode="decimal" data-num data-fid="' + esc(c.id_form_item) + '" id="' + id + '" value="' + esc(c.valor) + '">';
    } else {
      // o texto numa caixa que quebra a linha e cresce (09/11/2026: "tem que abrir uma caixa de texto que quebra o texto,
      // está rolando infinito para o lado")
      ctrl = '<textarea class="eg-ac-campo eg-ac-texto" rows="2" data-fid="' + esc(c.id_form_item) + '" id="' + id + '">' + esc(c.valor) + '</textarea>';
    }
    return '<label class="eg-dlg-campo" for="' + id + '"><span>' + esc(c.descricao) + req + '</span>' + ctrl + '</label>';
  }
  var url = function (tid, fim) { return caixa.dataset.tarefaUrl + '/' + encodeURIComponent(tid) + '/' + fim; };
  var wid = caixa.dataset.wid;
  function depois(j) { dizer(j.mensagem || 'Feito.', !!j.aviso); return carregar(); }
  var ACOES = {
    subtarefas: function (t) {
      pedir(caixa.dataset.tarefaUrl.replace(/\/tarefa$/, '') + '/tarefa/' + encodeURIComponent(t.id) + '/checklist').then(function (j) {
        var cs = j.campos || [];
        if (!cs.length) { dizer('Esta tarefa não tem subtarefas.'); return; }
        dialogo('Subtarefas · ' + (t.ativo || t.titulo), cs.map(campo).join(''), 'Salvar respostas', function (d) {
          var valores = {};
          var ruim = '';
          d.querySelectorAll('[data-fid]').forEach(function (el) {
            var v = (el.value || '').trim();
            if (v && el.hasAttribute('data-num')) { v = v.replace(',', '.'); if (!/^-?\d+(\.\d+)?$/.test(v)) ruim = el.closest('label').querySelector('span').firstChild.textContent; }
            if (v) valores[el.getAttribute('data-fid')] = v;
          });
          if (ruim) return Promise.reject(new Error('Use só número em: ' + ruim));
          return pedir(url(t.id, 'respostas'), {valores: valores}).then(depois);
        });
      }).catch(falhou);
    },
    // o Anexar da tarefa abre o cartão do anexo (09/11/2026); o arquivo vai para a aba Anexos desta tarefa
    anexar: function (t) {
      window.egCartaoAnexo({alvo: 'na tarefa ' + (t.ativo || t.titulo || t.n), aceitar: inp ? inp.getAttribute('accept') || '' : '',
        enviar: function (fs) {
          var fd = new FormData();
          fs.forEach(function (f) { fd.append('anexos', f, f.name); });
          fd.append('folio', caixa.dataset.folio || ''); fd.append('tarefa', t.id);
          return pedir(caixa.dataset.incluirUrl, fd).then(function (j) {
            dizer(j.mensagem, !j.ok); carregar();
            if (!j.ok) throw new Error(j.mensagem);
            return j.mensagem;
          }, function (e) { falhou(e); if (e.login) e.login = caixa.dataset.login; throw e; });
        }});
    },
    iniciar: function (t) { return pedir(url(t.id, 'cronometro'), {acao: 'iniciar'}).then(depois).catch(falhou); },
    retomar: function (t) { return pedir(url(t.id, 'cronometro'), {acao: 'retomar'}).then(depois).catch(falhou); },
    // o check sai da tarefa relida (a data de fim que o Fracttal grava na tarefa), não do "concluída" da rota: se o tempo
    // fechou e a tarefa não ficou finalizada lá, a tela diz, em vez de um "concluída" sem o check do lado
    concluir: function (t) {
      return pedir(url(t.id, 'cronometro'), {acao: 'concluir'}).then(depois).then(function () {
        var agora = tarefas.filter(function (x) { return String(x.id) === String(t.id); })[0];
        if (agora && !agora.feita) dizer('O tempo foi encerrado no Fracttal, mas a tarefa ainda não aparece como finalizada lá.', true);
      }).catch(falhou);
    },
    pausar: function (t) {
      pedir(caixa.dataset.motivosUrl).then(function (j) {
        var ms = j.motivos || [];
        var corpo = '<label class="eg-dlg-campo"><span>Motivo da pausa <span class="eg-dlg-req">obrigatório</span></span><select class="eg-ac-campo" data-motivo required><option value="">— selecione —</option>'
          + ms.map(function (m) { return '<option value="' + esc(m.id) + '">' + esc(m.descricao) + '</option>'; }).join('') + '</select></label>'
          + '<label class="eg-dlg-campo"><span>Observação (opcional)</span><input class="eg-ac-campo" type="text" data-nota></label>';
        dialogo('Pausar · ' + (t.ativo || t.titulo), corpo, 'Pausar', function (d) {
          var m = d.querySelector('[data-motivo]').value;
          if (!m) return Promise.reject(new Error('Escolha o motivo da pausa.'));
          return pedir(url(t.id, 'cronometro'), {acao: 'pausar', motivo: Number(m), nota: d.querySelector('[data-nota]').value}).then(depois);
        });
      }).catch(falhou);
    }
  };
  lista.addEventListener('click', function (e) {
    var b = e.target.closest('[data-tarefa-acao]'); if (!b || b.disabled) return;
    var tid = b.closest('[data-tid]').getAttribute('data-tid');
    var t = tarefas.filter(function (x) { return String(x.id) === tid; })[0]; if (!t) return;
    var fn = ACOES[b.getAttribute('data-tarefa-acao')]; if (!fn) return;
    b.disabled = true;
    Promise.resolve(fn(t)).then(function () { b.disabled = false; }, function () { b.disabled = false; });
  });
})();

/* Recolher os ativos (06/11/2026, Levi: "quero só que dê para recolher os ativos"): o Esconder do título do bloco esconde
   o corpo; a escolha fica neste navegador (o localStorage pode faltar: aí abre sempre aberto). */
(function () {
  var bt = document.querySelector('[data-recolher-ativos]'); if (!bt) return;
  var corpo = document.getElementById(bt.getAttribute('aria-controls')), rot = bt.querySelector('[data-recolher-rotulo]');
  var CHAVE = 'nexus.engenharia.os.ativos.recolhidos';
  function por(recolhido) {
    corpo.hidden = recolhido; bt.setAttribute('aria-expanded', recolhido ? 'false' : 'true');
    rot.textContent = recolhido ? 'Mostrar' : 'Esconder';
  }
  try { por(localStorage.getItem(CHAVE) === '1'); } catch (e) { por(false); }
  bt.addEventListener('click', function () {
    var recolher = !corpo.hidden; por(recolher);
    try { localStorage.setItem(CHAVE, recolher ? '1' : '0'); } catch (e) { /* sem onde lembrar: só agora */ }
  });
})();

/* Levar para a nota os comentários que ficaram só no Nexus (06/11/2026, "Sim, leva"): o administrador manda pela ponte do
   OS Creator, e a página volta relida com o aviso. Sem o login do Fracttal, o aviso traz o login. */
(function () {
  var caixa = document.querySelector('[data-levar-nota]'); if (!caixa) return;
  var btn = caixa.querySelector('button'), msg = caixa.querySelector('.eg-os-msg');
  function diz(texto, ruim, link) {
    msg.replaceChildren(document.createTextNode(texto || ''));
    if (link) { var a = document.createElement('a'); a.href = link; a.textContent = 'Entrar pelo Fracttal'; msg.appendChild(document.createTextNode(' ')); msg.appendChild(a); }
    msg.hidden = !texto; msg.classList.toggle('eg-os-msg--ruim', !!ruim);
  }
  btn.addEventListener('click', function () {
    btn.disabled = true; diz('Levando para a nota da OS…');
    fetch(caixa.dataset.levarNota, {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({folio: caixa.dataset.folio})})
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { return {r: r, j: j}; }); })
      .then(function (x) {
        btn.disabled = false;
        if (x.r.ok && x.j.ok) { window.egVoltarComOk(x.j.mensagem || 'Feito.'); return; }
        if (x.j.login) { diz(x.j.erro || 'Para ir à nota da OS, entre pelo Fracttal.', true, x.j.login); return; }
        diz(x.j.erro || ('O Nexus não levou (HTTP ' + x.r.status + '). Nada mudou; tente de novo.'), true);
      })
      .catch(function () { btn.disabled = false; diz('Não consegui falar com o Nexus. Tente de novo.', true); });
  });
})();

/* O cartão do anexo (09/11/2026, Levi: "ao clicar em anexar aparecesse uma tela card sobrepondo porém sem blur de fundo
   aparecendo um ícone de imagem a mensagem 'Cole ou faça o upload do anexo' o 'faça upload do anexo' será clicável em
   verde grid"). O Anexar da tarefa e o Incluir anexo da OS o abrem com o `enviar` deles (que devolve a promessa); o link
   abre o seletor de arquivos, o Ctrl+V (ou o Win+V) cola e o arrastar solta. Sem véu nem desfoque atrás; o clique fora,
   o Esc e o x fecham. A imagem colada ("image.png") ganha o nome com a data e a hora. */
(function () {
  function nomeColado(f, i) {
    if (f.name && !/^image\.(png|jpe?g|gif|webp|bmp)$/i.test(f.name)) return f;
    function p(n) { return String(n).padStart(2, '0'); }
    var a = new Date(), ext = ((f.type || '').split('/')[1] || 'png').replace('jpeg', 'jpg');
    return new File([f], 'colado ' + a.getFullYear() + '-' + p(a.getMonth() + 1) + '-' + p(a.getDate()) + ' ' + p(a.getHours())
      + 'h' + p(a.getMinutes()) + 'm' + p(a.getSeconds()) + 's' + (i ? ' ' + (i + 1) : '') + '.' + ext, {type: f.type});
  }
  window.egCartaoAnexo = function (op) {
    var d = document.createElement('dialog');
    d.className = 'eg-anx'; d.setAttribute('aria-label', 'Anexar ' + (op.alvo || ''));
    d.innerHTML = '<button type="button" class="eg-anx-x" data-fechar aria-label="Fechar">×</button>'
      + '<svg class="eg-anx-ico" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4.5" width="18" height="15" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.6"/>'
      + '<circle cx="9" cy="10" r="1.8" fill="none" stroke="currentColor" stroke-width="1.6"/>'
      + '<path d="M3.8 17.8 9.3 12.3l4 4 2.6-2.6 4.3 4.3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/></svg>'
      + '<p class="eg-anx-t">Cole ou <button type="button" class="eg-anx-up" data-upload>faça o upload do anexo</button></p>'
      + '<p class="eg-anx-s"></p><input type="file" multiple hidden>'
      + '<p class="eg-anx-msg" role="status" hidden></p>';
    document.body.appendChild(d);
    var up = d.querySelector('[data-upload]'), inp = d.querySelector('input[type=file]'), msg = d.querySelector('.eg-anx-msg');
    d.querySelector('.eg-anx-s').textContent = op.alvo || '';
    if (op.aceitar) inp.setAttribute('accept', op.aceitar);
    if (op.regra) up.title = op.regra;
    var ocupado = false;
    function dizer(texto, ruim, link) {
      msg.replaceChildren(document.createTextNode(texto || ''));
      if (link) { var a = document.createElement('a'); a.href = link; a.textContent = 'Entrar pelo Fracttal'; msg.appendChild(document.createTextNode(' ')); msg.appendChild(a); }
      msg.hidden = !texto; msg.classList.toggle('eg-anx-msg--ruim', !!ruim);
    }
    function mandar(fs) {
      if (ocupado || !fs.length) return;
      ocupado = true; up.disabled = true;
      dizer(fs.length === 1 ? 'Enviando ' + fs[0].name + '…' : 'Enviando ' + fs.length + ' arquivos…');
      Promise.resolve().then(function () { return op.enviar(fs); }).then(function (m) {
        dizer(m || 'Anexo incluído.'); setTimeout(function () { if (d.open) d.close(); }, 1400);
      }, function (e) {
        ocupado = false; up.disabled = false; dizer((e && e.message) || 'Não consegui anexar. Tente de novo.', true, e && e.login);
      });
    }
    function colar(e) {
      var fs = Array.prototype.slice.call((e.clipboardData && e.clipboardData.files) || []).map(nomeColado);
      if (!fs.length) return;
      e.preventDefault(); mandar(fs);
    }
    up.addEventListener('click', function () { inp.value = ''; inp.click(); });
    inp.addEventListener('change', function () { mandar(Array.prototype.slice.call(inp.files || [])); });
    d.querySelector('[data-fechar]').addEventListener('click', function () { d.close(); });
    d.addEventListener('click', function (e) {       // o clique fora do cartão (no fundo) fecha
      if (e.target !== d) return;
      var r = d.getBoundingClientRect();
      if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) d.close();
    });
    d.addEventListener('dragover', function (e) { e.preventDefault(); d.classList.add('eg-anx--sobre'); });
    d.addEventListener('dragleave', function () { d.classList.remove('eg-anx--sobre'); });
    d.addEventListener('drop', function (e) {
      e.preventDefault(); d.classList.remove('eg-anx--sobre');
      mandar(Array.prototype.slice.call((e.dataTransfer && e.dataTransfer.files) || []));
    });
    document.addEventListener('paste', colar);
    d.addEventListener('close', function () { document.removeEventListener('paste', colar); d.remove(); });
    d.showModal(); up.focus();
    return d;
  };
})();

/* A página relida com o aviso (09/11/2026): o mesmo endereço, o `ok` novo e o resto da busca (o `?de=` de quem veio do
   Quadro da Performance ou de Garantias segue, e a volta continua sendo a de lá). */
window.egVoltarComOk = function (texto) {
  var q = new URLSearchParams(location.search);
  q.delete('erro'); q.set('ok', texto || 'Feito.');
  location.replace(location.pathname + '?' + q.toString());
};


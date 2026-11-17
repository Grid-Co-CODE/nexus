/* Base > Equipamentos das usinas, aba De-para (13/11/2026; a prévia aprovada: docs/mockups/equipamentos-e-depara, no
   repositório da plataforma). Levi: "no de para do equipamento, tem que ser possível editar o equipamento da usina".

   1. Os cartões: um por fonte que chega nas chaves da usina aberta (GET data-cartoes-url, JSON da rota
      equipamentos_fontes). Cada par é UMA linha da grade de três colunas (a fonte, o fio, o cadastro): a cor do "sem par"
      atravessa a coluna do meio (Levi, 13/11/2026, com a foto: "a coluna Liga está cortando a cor amarelo").
   2. O lápis: o editor do inversor do CADASTRO (a estrutura do Nexus; o estado vem do <script id="dpx-dados">, o mesmo
      do editor da aba Equipamentos). Grava pelo mesmo Salvar (POST salvar_url, a usina inteira com o selo). Na chave que
      a plataforma ainda lê da aba Equipamentos, o Salvar pergunta (Levi, 13/11/2026: "Pergunta ao salvar"): as
      diferenças Nexus × aba do que está salvo, "Salvar e passar a valer na plataforma" (marca a chave no lugar da aba) ou
      "Salvar só no Nexus".
   3. O "Ligar a…": a tela De-para da plataforma numa janela por cima (rota equipamentos_fontes_janela, pela porta
      única). Ela avisa quando fecha ({gc: 'depara-fechar'}); a janela fecha e os cartões são relidos.
   Nada aqui decide um par sozinho; a ponte com a plataforma é só de leitura. */
(function () {
  'use strict';
  var raiz = document.getElementById('dpx');
  var dadosEl = document.getElementById('dpx-dados');
  var E = dadosEl ? JSON.parse(dadosEl.textContent) : null;
  var CARTOES = [];
  var toast = document.getElementById('eq-toast'), relogio = null;

  function $(s, r) { return (r || document).querySelector(s); }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  }
  function avisar(texto, ok) {
    if (!toast) return;
    toast.textContent = texto;
    toast.className = 'fr-toast fr-toast--' + (ok ? 'ok' : 'erro');
    toast.hidden = false;
    clearTimeout(relogio);
    relogio = setTimeout(function () { toast.hidden = true; }, ok ? 6000 : 10000);
  }
  function kwp(v) {
    return v == null || v === '' ? '—' : Number(v).toLocaleString('pt-BR', {minimumFractionDigits: 1, maximumFractionDigits: 1});
  }

  /* ── 1. os cartões ─────────────────────────────────────────────────────────────────────────────────────────────── */
  var MODO = {ok: ['ph-check', 'liga pelo nome'], decidido: ['ph-link', 'decidido na tela'],
              ordem: ['ph-list-numbers', 'pela ordem: conferir'], sem: ['ph-question', 'sem par']};

  function situacao(c) {
    if (c.erro) return ['neutro', 'sem leitura'];
    var sem = c.linhas.filter(function (l) { return l.modo === 'sem'; }).length;
    var ordem = c.linhas.filter(function (l) { return l.modo === 'ordem'; }).length;
    if (sem) return ['alerta', sem + (sem === 1 ? ' inversor sem par' : ' inversores sem par')];
    if (ordem) return ['alerta', 'pela ordem: conferir'];
    if (c.linhas.length) return [c.luz === 'critico' ? 'critico' : 'ok', c.linhas.length + ' de ' + c.linhas.length + ' ligados'];
    if (c.sem_leitura && c.edita_inversor) return ['neutro', 'sem a lista da fonte'];
    var a = (c.alertas || []).filter(function (x) { return x.nivel !== 'info'; })[0];
    return [c.luz, a ? (a.nivel === 'critico' ? 'falta' : 'atenção') : 'ok'];
  }

  function ladoCadastro(alvo, invId, dica) {
    var nome = alvo.exibicao || alvo.nome;
    var sub = (alvo.exibicao && alvo.nome && alvo.nome !== alvo.exibicao ? alvo.nome : '') +
              (alvo.esp ? (alvo.exibicao && alvo.nome !== alvo.exibicao ? ' · ' : '') + alvo.esp + ' str' : '');
    // na tela Equipamentos (17/11/2026) não há lápis: o cadastro está logo abaixo, na tabela dos inversores
    var lapis = invId != null && E
      ? '<button type="button" class="dpx-lapis" data-dpx-editar="' + esc(invId) + '"' + (dica ? ' data-dpx-dica="' + esc(dica) + '"' : '') +
        ' aria-label="Editar ' + esc(nome) + ' no cadastro" title="Editar no cadastro"><i class="ph ph-pencil-simple" aria-hidden="true"></i></button>'
      : invId != null ? '' : '<span class="gc-status gc-status--neutro" title="Este inversor está no cadastro que a plataforma lê (a aba Equipamentos), e não na estrutura do Nexus">só na aba</span>';
    return '<div class="dpx-pc"><span class="dpx-pc-txt"><span>' + esc(nome) + '</span>' + (sub ? '<small class="gc-dado">' + esc(sub) + '</small>' : '') + '</span>' + lapis + '</div>';
  }

  function cartao(c, ci) {
    var st = situacao(c);
    var h = '<details class="dpx-fonte"' + (st[0] !== 'ok' ? ' open' : '') + '>' +
      '<summary><span class="dpx-ico"><i class="ph ph-broadcast" aria-hidden="true"></i></span>' +
      '<span class="dpx-fonte-nome"><b>' + esc(c.fonte_nome) + '</b><span class="gc-dado">' + esc(c.usina) + '</span></span>' +
      '<span class="dpx-cad" title="De onde a plataforma lê o cadastro desta chave">' + (c.no_lugar_da_aba ? 'cadastro do Nexus' : 'cadastro da aba Excel') + '</span>' +
      '<span class="gc-status gc-status--' + st[0] + '">' + esc(st[1]) + '</span></summary>';
    var alertas = (c.alertas || []).filter(function (a) { return a.nivel !== 'info' || c.provisorio !== a.texto; });
    if (alertas.length) {
      h += '<ul class="dpx-alertas">' + alertas.map(function (a) {
        var tom = {critico: 'critico', atencao: 'alerta', info: 'info'}[a.nivel] || 'neutro';
        return '<li><span class="dpx-ponto dpx-ponto--' + tom + '" aria-hidden="true"></span>' + esc(a.texto) + '</li>';
      }).join('') + '</ul>';
    }
    if (c.erro) {
      h += '<p class="dpx-nota">Não li esta fonte na plataforma: ' + esc(c.erro) + '.</p>';
    } else if (c.linhas.length || c.sobra.length) {
      h += '<div class="dpx-pares" role="table" aria-label="Inversores de ' + esc(c.fonte_nome) + '">' +
        '<div class="dpx-par dpx-par--cab" role="row"><span role="columnheader">Na fonte</span><span role="columnheader" class="dpx-meio">Liga</span>' +
        '<span role="columnheader">No cadastro</span></div>';
      c.linhas.forEach(function (l) {
        var m = MODO[l.modo] || MODO.ok;
        h += '<div class="dpx-par dpx-par--' + l.modo + '" role="row"><div class="dpx-pc"><span class="dpx-pc-txt"><span class="gc-dado">' + esc(l.fonte) + '</span>' +
          (l.repetido ? '<small class="gc-dado">id ' + esc(l.id) + ' · nome repetido</small>' : '') + '</span></div>' +
          '<div class="dpx-fio dpx-fio--' + l.modo + '"><i class="ph ' + m[0] + '" role="img" aria-label="' + m[1] + '" title="' + m[1] + '"></i></div>';
        if (l.alvo) {
          h += ladoCadastro(l.alvo, l.inversor_id) + '</div>';
        } else {
          h += '<div class="dpx-pc dpx-pc--acoes">' +
            '<button type="button" class="gc-btn gc-btn--ui gc-btn--contorno" data-dpx-ligar="' + esc(c.fonte + '|' + c.plant_id) + '" data-dpx-nome="' + esc(c.usina) + '"><i class="ph ph-link" aria-hidden="true"></i> Ligar a…</button>' +
            (E && c.supervisorio_id != null ? '<button type="button" class="gc-btn gc-btn--ui gc-btn--fantasma" data-dpx-novo="' + esc(l.fonte) + '" data-dpx-sid="' + esc(c.supervisorio_id) + '"><i class="ph ph-plus" aria-hidden="true"></i> No cadastro</button>' : '') +
            '</div></div>';
        }
      });
      c.sobra.forEach(function (s) {
        // três casos: a fonte liga pelo nome (Athon, Axis), a lista da fonte não foi lida, ou a fonte não manda este
        var tipo = s.so_cadastro ? ['nome', 'ph-text-aa', 'pelo nome', 'liga pelo nome']
          : s.sem_leitura ? ['nome', 'ph-minus', 'sem leitura', 'sem a lista da fonte']
          : ['falta', 'ph-x', 'não chega', 'não chega da fonte'];
        h += '<div class="dpx-par dpx-par--' + (tipo[0] === 'falta' ? 'falta' : 'neutro') + '" role="row"><div class="dpx-pc"><small class="mudo">' + tipo[3] + '</small></div>' +
          '<div class="dpx-fio dpx-fio--' + tipo[0] + '"><i class="ph ' + tipo[1] + '" role="img" aria-label="' + tipo[2] + '"></i></div>' +
          ladoCadastro(s.alvo, s.inversor_id, tipo[0] === 'falta' ? 'A fonte não manda este inversor. Se ela manda com outro nome, troque aqui o nome no supervisório.' : '') + '</div>';
      });
      h += '</div>';
    }
    var pe = c.nota || c.provisorio || (c.sem_leitura && c.edita_inversor
      ? 'A plataforma não tem agora a lista de inversores desta fonte (a leitura do ciclo dela). O Nexus não abre a API PV: "Abrir na plataforma" mostra o que ela tem.'
      : '');
    h += '<div class="dpx-pe"><span>' + (pe ? '<i class="ph ph-info" aria-hidden="true"></i> ' + esc(pe) : '') + '</span>' +
      (c.edita_inversor && c.plant_id != null ? '<button type="button" class="gc-btn gc-btn--ui gc-btn--fantasma" data-dpx-ligar="' + esc(c.fonte + '|' + c.plant_id) + '" data-dpx-nome="' + esc(c.usina) + '"><i class="ph ph-arrow-square-out" aria-hidden="true"></i> Abrir na plataforma</button>' : '') +
      '</div></details>';
    return h;
  }

  function desenhar() {
    var alvo = $('[data-dpx-cartoes]', raiz);
    alvo.innerHTML = CARTOES.length ? CARTOES.map(cartao).join('')
      : '<p class="eq-vazio">Nenhuma fonte do de-para chega nas chaves desta usina.</p>';
  }

  function ler(forcar) {
    if (!raiz) return;
    var url = raiz.getAttribute('data-cartoes-url') + (forcar ? '&forcar=1' : '');
    var lido = $('[data-dpx-lido]', raiz);
    if (forcar) lido.textContent = 'lendo…';
    fetch(url, {credentials: 'same-origin', headers: {'Accept': 'application/json'}})
      .then(function (r) { return r.json().catch(function () { return {ok: false, motivo: 'resposta inesperada (' + r.status + ')'}; }); })
      .then(function (j) {
        if (!j.ok) {
          lido.textContent = '';
          $('[data-dpx-cartoes]', raiz).innerHTML = '<p class="eq-vazio">' + esc(j.motivo || 'Não li o de-para.') + '</p>';
          return;
        }
        CARTOES = j.cartoes || [];
        lido.textContent = j.lido_em ? 'lido ' + j.lido_em : '';
        desenhar();
        // a coluna "Na fonte" da tabela dos inversores (cadastro-equipamentos.js) lê o que os cartões dizem
        document.dispatchEvent(new CustomEvent('eq-fontes', {detail: CARTOES}));
      })
      .catch(function () { lido.textContent = ''; $('[data-dpx-cartoes]', raiz).innerHTML = '<p class="eq-vazio">Sem conexão com o Nexus.</p>'; });
  }

  /* ── 2. o editor do inversor do cadastro ───────────────────────────────────────────────────────────────────────── */
  var dlg = document.getElementById('dpx-editor');
  var editando = null;        // {id: id do inversor ou null (novo), sid: chave sugerida}

  function passo(n) {
    dlg.querySelectorAll('[data-dpx-passo]').forEach(function (x) { x.hidden = x.getAttribute('data-dpx-passo') !== String(n); });
    dlg.querySelectorAll('[data-dpx-pe]').forEach(function (x) { x.hidden = x.getAttribute('data-dpx-pe') !== String(n); });
  }
  function msg(t) { var m = $('[data-dpx-msg]', dlg); m.textContent = t || ''; m.hidden = !t; }
  function campo(k) { return $('[data-ed="' + k + '"]', dlg); }

  function abrirEditor(inv, dica, titulo) {
    if (!E) return;
    editando = inv;
    $('#dpx-ed-t').textContent = titulo || inv.nome || 'Inversor';
    var d = $('[data-dpx-dica]', dlg); d.textContent = dica || ''; d.hidden = !dica;
    campo('cabine').innerHTML = '<option value="">sem cabine</option>' + E.cabines.map(function (c) {
      return '<option value="' + esc(c.k) + '">' + esc(c.nome) + (c.potencia_kwp != null ? ' · ' + kwp(c.potencia_kwp) + ' kWp' : '') + '</option>';
    }).join('');
    campo('chave').innerHTML = E.chaves.map(function (c) {
      return '<option value="' + esc(c.supervisorio_id) + '">' + esc(c.chave) + '</option>';
    }).join('');
    campo('nome').value = inv.nome || '';
    campo('equipamento_supervisorio').value = inv.equipamento_supervisorio || '';
    campo('cabine').value = inv.cabine || '';
    campo('chave').value = inv.chave == null ? '' : String(inv.chave);
    campo('potencia_kwp').value = inv.potencia_kwp == null ? '' : String(inv.potencia_kwp).replace('.', ',');
    campo('strings_esperadas_qtd').value = inv.strings_esperadas_qtd == null ? '' : inv.strings_esperadas_qtd;
    var pode = E.pode_gravar;
    dlg.querySelectorAll('[data-ed]').forEach(function (x) { x.disabled = !pode; });
    $('[data-dpx-salvar]', dlg).disabled = !pode;
    msg(pode ? '' : 'Este Nexus não grava no banco agora (sem a chave do banco, ou sem a leitura da estrutura).');
    passo(1);
    dlg.showModal();
    campo('nome').focus();
  }

  function rascunho() {
    // a usina inteira, como o Salvar da aba Equipamentos manda, com a mudança deste inversor
    var st = JSON.parse(JSON.stringify({chaves: E.chaves, cabines: E.cabines, inversores: E.inversores}));
    var bruto = String(campo('potencia_kwp').value || '').trim();
    // "1.234,5" (o milhar com ponto) e "338.1" (o ponto decimal) valem; com vírgula, o ponto é milhar
    var num = bruto.indexOf(',') >= 0 ? bruto.replace(/\./g, '').replace(',', '.') : bruto;
    var str = String(campo('strings_esperadas_qtd').value || '').trim();
    var novo = {nome: campo('nome').value.trim(), equipamento_supervisorio: campo('equipamento_supervisorio').value.trim(),
                cabine: campo('cabine').value || null, chave: campo('chave').value === '' ? null : Number(campo('chave').value),
                potencia_kwp: num === '' ? null : Number(num), strings_esperadas_qtd: str === '' ? null : Number(str)};
    if (!novo.nome) return {erro: 'Dê o nome do equipamento.'};
    if (novo.potencia_kwp != null && !(novo.potencia_kwp >= 0)) return {erro: 'A potência é um número em kWp (ex.: 338,1).'};
    if (novo.strings_esperadas_qtd != null && !(Number.isInteger(novo.strings_esperadas_qtd) && novo.strings_esperadas_qtd >= 0)) return {erro: 'Strings é um número inteiro.'};
    var inv = editando.id == null ? null : st.inversores.filter(function (i) { return String(i.id) === String(editando.id); })[0];
    if (editando.id != null && !inv) return {erro: 'Este inversor não está mais na estrutura: leia de novo.'};
    if (!inv) {
      inv = {id: null, equipamento_id: null, codigo_fracttal: ''};
      st.inversores.push(inv);
    }
    Object.keys(novo).forEach(function (k) { inv[k] = novo[k]; });
    return {st: st, chave: st.chaves.filter(function (c) { return c.supervisorio_id === novo.chave; })[0]};
  }

  function perguntar(r) {
    var ch = r.chave, cmp = (E.comparacao || {})[ch.supervisorio_id];
    $('[data-dpx-chave]', dlg).textContent = ch.chave;
    var difs = $('[data-dpx-difs]', dlg);
    if (!cmp) {
      difs.innerHTML = '<p class="mudo">Sem a comparação com a aba agora (a aba não foi lida).</p>';
    } else if (cmp.iguais) {
      difs.innerHTML = '<p class="dpx-iguais"><span class="gc-status gc-status--ok">igual à aba</span> Hoje o que está salvo no Nexus nesta chave é igual à aba: além desta mudança, nada muda para a plataforma.</p>';
    } else {
      var lista = (cmp.dif || []).slice(0, 6);
      difs.innerHTML = '<p><span class="gc-status gc-status--alerta">' + cmp.n + (cmp.n === 1 ? ' diferença' : ' diferenças') + '</span> do que está salvo no Nexus para a aba, além desta mudança:</p>' +
        '<ul class="dpx-difs">' + lista.map(function (t) { return '<li>' + esc(t) + '</li>'; }).join('') + '</ul>' +
        (cmp.n > lista.length ? '<p class="mudo">e mais ' + (cmp.n - lista.length) + ' (a lista inteira fica na aba Equipamentos, coluna "Diferença com a aba").</p>' : '');
    }
    passo(2);
  }

  function gravar(st, valer, botao) {
    if (valer) st.chaves.forEach(function (c) { if (c.supervisorio_id === valer) c.substitui_aba = true; });
    var corpo = {usina_id: E.usina_id, selo: E.selo, chaves: st.chaves, cabines: st.cabines, inversores: st.inversores};
    dlg.querySelectorAll('button').forEach(function (b) { b.disabled = true; });
    fetch(E.salvar_url, {method: 'POST', credentials: 'same-origin', body: JSON.stringify(corpo),
                         headers: {'Content-Type': 'application/json', 'Accept': 'application/json'}})
      .then(function (r) { return r.json().catch(function () { return {ok: false, erro: 'Resposta inesperada (' + r.status + '): nada foi gravado.'}; }); })
      .then(function (j) {
        dlg.querySelectorAll('button').forEach(function (b) { b.disabled = false; });
        if (!j.ok) { passo(1); msg(j.erro || 'Não gravou.'); return; }
        ['selo', 'chaves', 'cabines', 'inversores'].forEach(function (k) { if (j.editor && j.editor[k] !== undefined) E[k] = j.editor[k]; });
        if (j.comparacao) E.comparacao = j.comparacao;
        dlg.close();
        avisar((j.aviso || 'Salvo.') + (valer ? ' A chave passou a valer na plataforma: o de-para dela lê o Nexus em até 1 minuto.' : ''), true);
        ler(true);
      })
      .catch(function () { dlg.querySelectorAll('button').forEach(function (b) { b.disabled = false; }); msg('Sem conexão: nada foi gravado.'); });
  }

  var pendente = null;      // o rascunho entre o passo 1 e a pergunta
  if (dlg) {
    dlg.addEventListener('click', function (ev) {
      var b = ev.target.closest('button');
      if (!b || b.disabled) return;
      if (b.hasAttribute('data-dpx-cancelar')) { dlg.close(); return; }
      if (b.hasAttribute('data-dpx-voltar')) { passo(1); return; }
      if (b.hasAttribute('data-dpx-salvar')) {
        var r = rascunho();
        if (r.erro) { msg(r.erro); return; }
        msg('');
        pendente = r;
        if (r.chave && !r.chave.substitui_aba) { perguntar(r); return; }
        gravar(r.st, null, b);
        return;
      }
      if (b.hasAttribute('data-dpx-so-nexus') && pendente) { gravar(pendente.st, null, b); return; }
      if (b.hasAttribute('data-dpx-valer') && pendente) { gravar(pendente.st, pendente.chave.supervisorio_id, b); return; }
    });
    dlg.addEventListener('close', function () { editando = null; pendente = null; });
  }

  /* ── 3. a tela De-para da plataforma numa janela ───────────────────────────────────────────────────────────────── */
  var jan = document.getElementById('dpx-janela');
  function abrirJanela(editar, nome) {
    if (!jan) return;
    $('#dpx-jn-t').textContent = 'Ligar na plataforma' + (nome ? ': ' + nome : '');
    $('.dpx-janela-moldura', jan).src = jan.getAttribute('data-url') + '?editar=' + encodeURIComponent(editar);
    jan.showModal();
  }
  function fecharJanela() {
    if (!jan || !jan.open) return;
    jan.close();
    $('.dpx-janela-moldura', jan).src = 'about:blank';
    ler(true);
  }
  if (jan) {
    jan.addEventListener('click', function (ev) { if (ev.target.closest('[data-dpx-fechar-janela]')) fecharJanela(); });
    jan.addEventListener('cancel', function (ev) { ev.preventDefault(); fecharJanela(); });
    window.addEventListener('message', function (ev) {
      if (ev.origin === location.origin && ev.data && ev.data.gc === 'depara-fechar') fecharJanela();
    });
  }

  // a tabela dos inversores gravou ligações na plataforma: os cartões (e a coluna Equipamento Supervisório) se releem
  document.addEventListener('eq-fontes-reler', function () { ler(true); });

  document.addEventListener('click', function (ev) {
    var b = ev.target.closest('button');
    if (!b || b.disabled) return;
    if (b.hasAttribute('data-dpx-ligar')) { abrirJanela(b.getAttribute('data-dpx-ligar'), b.getAttribute('data-dpx-nome')); return; }
    if (b.hasAttribute('data-dpx-reler')) { ler(true); return; }
    if (!E) return;
    if (b.hasAttribute('data-dpx-editar')) {
      var inv = E.inversores.filter(function (i) { return String(i.id) === b.getAttribute('data-dpx-editar'); })[0];
      if (inv) abrirEditor(inv, b.getAttribute('data-dpx-dica'));
      return;
    }
    if (b.hasAttribute('data-dpx-novo')) {
      var sid = Number(b.getAttribute('data-dpx-sid'));
      var irmao = E.inversores.filter(function (i) { return i.chave === sid && i.cabine; })[0];
      abrirEditor({id: null, nome: '', equipamento_supervisorio: b.getAttribute('data-dpx-novo'), chave: sid,
                   cabine: irmao ? irmao.cabine : (E.cabines.length === 1 ? E.cabines[0].k : null),
                   potencia_kwp: null, strings_esperadas_qtd: null},
                  'Entra no cadastro com o nome que a fonte manda. Dê o nome do equipamento (ex.: Inversor 3.9) e confira a cabine.',
                  'Inversor novo');
    }
  });

  ler(false);
})();

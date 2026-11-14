/* Nexus IA na janela do prontuário (13/11/2026; as regras: nexus/comando/ia.py, a janela: comando/_ia.html).
   A janela chega como pedaço de página (prontuario.js põe o HTML no corpo dela), então tudo aqui é por delegação no
   documento. Cada pergunta vai em JSON para data-ia-url com os modelos marcados e as últimas perguntas e respostas (a
   pergunta de seguimento: "e no mês passado?"); a resposta de cada modelo vira um cartão, lado a lado quando há mais de
   um (o modo de comparar). O texto da IA é escapado antes de virar parágrafo, lista e negrito: nada dele vira HTML.

   14/11/2026, os pedidos do Levi com o chat na mão:
   - "quando ele citar OSs quero que elas sejam clicáveis": a OS que o dossiê tem (o servidor manda o mapa em `r.os`)
     vira link. A de chamado, Engenharia ou Performance abre o Raio X da OS numa aba nova; as outras, o card da OS por
     cima (a janela do chat fecha guardando a conversa e volta quando o card fecha);
   - "ao citar coisas que podem ser feitas por outros setores, tem que dar a opção de caixa de entrada": cada ação de
     outro setor (`r.acoes`) ganha o "Mandar para a caixa de entrada", que abre a Nova demanda ali mesmo, preenchida;
   - "se eu pedisse um relatório já baixa um automático": o pedido de relatório volta com o endereço do PDF (sem a IA),
     e o PDF baixa sozinho;
   - as citações saem como "§2 · §8", sem código de regra (o servidor já limpa; aqui só o desenho). */
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
  // o mínimo de Markdown que as IAs escrevem: parágrafo, lista com "-" ou "*" ou "1.", **negrito** e *itálico*
  function texto(md, mapaOs, raiz) {
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
    var h = out.join('').replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/(^|[^*\w])\*([^*\s][^*]*?)\*(?!\*)/g, '$1<em>$2</em>');
    // as citações: "(§2, §8)" vira a etiqueta "§2 · §8"
    h = h.replace(/\((§\d+(?:,\s*§\d+)*)\)/g, function (_t, g) {
      return '<span class="ia-cita" title="Seção do dossiê">' + g.split(/,\s*/).join(' · ') + '</span>';
    });
    // as OS do dossiê viram link (o número sozinho, de 4 a 6 dígitos, que o mapa conhece)
    if (mapaOs) {
      h = h.replace(/(^|[^\d.,#])(\d{4,6})(?![\d]|[.,]\d)/g, function (t, antes, n) {
        var tipo = mapaOs[n];
        if (!tipo) return t;
        if (tipo === 'os') {
          return antes + '<button type="button" class="ia-os" data-ia-os="' + n + '" title="Abrir o card da OS ' + n + '">' + n + '</button>';
        }
        var de = tipo === 'chamado' ? '?de=garantias' : (tipo === 'performance' ? '?de=performance' : '');
        return antes + '<a class="ia-os ia-os--raiox" href="' + esc(nexusRota('/t/engenharia/equipe/os/')) + n + de +
          '" target="_blank" rel="noopener" title="Raio X da OS ' + n + ' (abre em outra aba)">' + n + '</a>';
      });
    }
    return h;
  }
  // o "Criar OS" da ação, à esquerda da caixa de entrada, para o setor que recebe OS (Engenharia, Performance): o
  // mesmo Criar OS do prontuário (a janela do OS Creator por cima; fora do prontuário, o OS Creator noutra aba)
  var criarOsMapa = null;
  function semAcento(s) { return String(s || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim(); }
  function criarOs(setor) {
    if (criarOsMapa === null) {
      var el = document.querySelector('[data-ia-criar-os]');
      try { criarOsMapa = el ? JSON.parse(el.textContent) : {}; } catch (e) { criarOsMapa = {}; }
    }
    var c = criarOsMapa[semAcento(setor)];
    if (!c) return '';
    return '<a class="gc-btn gc-btn--ui gc-btn--contorno" data-pu-criar="' + esc(c.url) + '" href="' + esc(nexusRota(c.url)) +
      '" target="_blank" rel="noopener"><i class="ph ph-plus" aria-hidden="true"></i> Criar ' + esc(c.rot) + '</a>';
  }
  function acoes(r, ri) {
    if (!r.acoes || !r.acoes.length) return '';
    return '<div class="ia-acoes"><p class="ia-acoes-t">Pedir a outro setor</p>' + r.acoes.map(function (a, i) {
      return '<div class="ia-acao" data-ia-acao="' + ri + '-' + i + '"><span class="ia-acao-setor">' + esc(a.setor) + '</span>' +
        '<span class="ia-acao-txt">' + esc(a.acao) + (a.os ? ' <span class="mudo">· OS ' + a.os + '</span>' : '') + '</span>' +
        '<span class="ia-acao-botoes">' + criarOs(a.setor) +
        '<button type="button" class="gc-btn gc-btn--ui gc-btn--contorno" data-ia-pedir><i class="ph ph-tray-arrow-down" aria-hidden="true"></i> Mandar para a caixa de entrada</button></span></div>';
    }).join('') + '</div>';
  }
  function cartao(r, ri, raiz) {
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
    return '<article class="ia-r">' + cab + (r.troca ? '<p class="ia-r-troca">' + esc(r.troca) + '</p>' : '') +
      '<div class="ia-r-texto">' + texto(r.texto, r.os, raiz) + '</div>' + acoes(r, ri) +
      (r.parou ? '<p class="ia-r-aviso">A resposta foi cortada (' + esc(r.parou) + ').</p>' : '') +
      '<p class="ia-r-pe">' + conf + '<span class="mudo">' + num(r.ms / 1000, 1) + ' s · ' + num(r.entrada + (r.cache_lido || 0)) +
      ' → ' + num(r.saida) + ' tokens · ' + custo + '</span></p></article>';
  }

  // o relatório: o PDF do prontuário, baixado sozinho (sem a IA)
  function relatorio(caixa, rel) {
    caixa.innerHTML = '<article class="ia-r"><div class="ia-r-cab"><b>Relatório da usina</b><span class="mudo">o PDF do prontuário</span></div>' +
      '<p class="ia-rel-txt">' + esc(rel.mes) + ' · ' + esc(rel.temas.join(', ')) + '</p>' +
      (rel.aviso ? '<p class="ia-r-aviso">' + esc(rel.aviso) + '</p>' : '') +
      '<p class="ia-rel-estado mudo" data-ia-rel-estado>Gerando o PDF…</p></article>';
    var estado = caixa.querySelector('[data-ia-rel-estado]');
    fetch(rel.url, {credentials: 'same-origin'}).then(function (r) {
      if (!r.ok) throw new Error(r.status === 404 ? 'o relatório em PDF só existe para usina mobilizada' : 'HTTP ' + r.status);
      var nome = 'Relatório.pdf', cd = r.headers.get('Content-Disposition') || '', m = cd.match(/filename\*=UTF-8''([^;]+)/);
      if (m) { try { nome = decodeURIComponent(m[1]); } catch (e) { /* fica o nome padrão */ } }
      return r.blob().then(function (b) { return {b: b, nome: nome}; });
    }).then(function (x) {
      var url = URL.createObjectURL(x.b), a = document.createElement('a');
      a.href = url; a.download = x.nome; document.body.appendChild(a); a.click(); a.remove();
      estado.innerHTML = 'Baixado: ' + esc(x.nome) + ' · <a href="' + esc(rel.url) + '">baixar de novo</a>';
      setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
    }).catch(function (e) {
      estado.className = 'ia-r-erro';
      estado.textContent = 'Não baixou: ' + e.message + '.';
    });
  }

  var respostas = {};          // as respostas de cada pergunta, para a demanda achar a ação e o texto
  var seq = 0;
  function enviar(raiz, pergunta) {
    var marcados = Array.prototype.map.call(raiz.querySelectorAll('[data-ia-modelo]:checked'), function (c) { return c.value; });
    var conversa = raiz.querySelector('[data-ia-conversa]'), campo = raiz.querySelector('[data-ia-pergunta]');
    var botao = raiz.querySelector('[data-ia-enviar]');
    pergunta = String(pergunta || '').trim();
    if (!pergunta) { campo.focus(); return; }
    var vazio = raiz.querySelector('[data-ia-vazio]');
    if (vazio) vazio.remove();
    var id = ++seq;
    var turno = document.createElement('section');
    turno.className = 'ia-turno';
    turno.setAttribute('data-ia-turno', id);
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
      if (j.relatorio) { caixa.className = 'ia-respostas'; relatorio(caixa, j.relatorio); return; }
      respostas[id] = {pergunta: pergunta, lista: j.respostas};
      caixa.innerHTML = j.respostas.map(function (r, ri) { return cartao(r, id + '-' + ri, raiz.getAttribute('data-ia-raiz') || ''); }).join('');
      var primeira = j.respostas.filter(function (r) { return r.ok; })[0];
      if (primeira) historico = historico.concat([{pergunta: pergunta, resposta: primeira.texto}]).slice(-3);
      var g = raiz.querySelector('[data-ia-gasto]');
      if (g && j.gasto != null) g.textContent = 'US$ ' + num(j.gasto, 2);
    }).catch(function () {
      turno.querySelector('.ia-respostas').innerHTML = '<p class="ia-r-erro" role="alert">Sem conexão com o Nexus.</p>';
    }).then(function () { botao.disabled = false; campo.focus(); });
  }

  // a Nova demanda da ação, ali mesmo: a pessoa, o tema, o título e o texto já preenchidos (quem envia é a pessoa)
  function setores(raiz) {
    var el = raiz.querySelector('[data-ia-setores]');
    try { return el ? JSON.parse(el.textContent) : []; } catch (e) { return []; }
  }
  function formDemanda(raiz, linha) {
    var chave = linha.getAttribute('data-ia-acao').split('-');
    var turnoId = chave[0], ri = +chave[1], ai = +chave[2];
    var ctx = respostas[turnoId], r = ctx && ctx.lista[ri], a = r && r.acoes[ai];
    if (!a) return;
    var s = setores(raiz).filter(function (x) { return x.nome === a.setor; })[0];
    var caixa = linha.querySelector('.ia-demanda');
    if (caixa) { caixa.remove(); return; }
    caixa = document.createElement('form');
    caixa.className = 'ia-demanda';
    caixa.setAttribute('data-ia-demanda', '');
    if (!s || !s.pessoas.length || !s.temas.length) {
      // o que falta para a demanda sair (a regra da Nova demanda: uma pessoa do setor e um tema dele)
      var falta = !s ? 'O setor ' + esc(a.setor) + ' não está no cadastro agora.'
        : !s.temas.length ? esc(a.setor) + ' ainda não tem tema de demanda: o setor cria em Caixa de entrada › Temas do setor, e aí o pedido sai daqui.'
        : 'Não li as pessoas de ' + esc(a.setor) + ' agora (os nomes vêm do Fracttal).';
      caixa.innerHTML = '<p class="ia-demanda-falta">' + falta + '</p>';
      linha.appendChild(caixa);
      return;
    }
    var desc = a.acao + '\n\nSugerido pelo Nexus IA, a partir da pergunta: “' + ctx.pergunta + '”.';
    caixa.innerHTML =
      '<input type="hidden" name="para_setor_id" value="' + s.setor_id + '"><input type="hidden" name="os" value="' + (a.os || '') + '">' +
      '<input type="hidden" name="novo_id" value="d' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8) + '">' +
      '<label>Para<select class="gc-campo" name="para_hmac" required>' + s.pessoas.map(function (p) { return '<option value="' + esc(p.hmac) + '">' + esc(p.nome) + '</option>'; }).join('') + '</select></label>' +
      '<label>Tema<select class="gc-campo" name="tema_id" required>' + s.temas.map(function (t) { return '<option value="' + esc(t.tema_id) + '">' + esc(t.nome) + ' · ' + t.prazo + ' dias úteis</option>'; }).join('') + '</select></label>' +
      '<label class="ia-demanda-larga">Título<input class="gc-campo" name="titulo" maxlength="120" required value="' + esc(a.acao) + '"></label>' +
      '<label class="ia-demanda-larga">Descrição<textarea class="gc-campo" name="descricao" rows="3" maxlength="4000" required>' + esc(desc) + '</textarea></label>' +
      (a.os ? '<p class="ia-demanda-larga mudo">Vai com a OS ' + a.os + ' atrelada.</p>' : '') +
      '<p class="ia-demanda-pe"><button type="button" class="gc-btn gc-btn--ui gc-btn--fantasma" data-ia-pedir>Cancelar</button>' +
      '<button type="submit" class="gc-btn gc-btn--ui gc-btn--primario"><i class="ph ph-paper-plane-tilt" aria-hidden="true"></i> Enviar para ' + esc(a.setor) + '</button></p>' +
      '<p class="ia-demanda-msg" data-ia-demanda-msg role="status" hidden></p>';
    linha.appendChild(caixa);
    caixa.querySelector('select').focus();
  }
  function enviarDemanda(raiz, form) {
    var dados = {};
    new FormData(form).forEach(function (v, k) { dados[k] = v; });
    var msg = form.querySelector('[data-ia-demanda-msg]'), bt = form.querySelector('button[type="submit"]');
    bt.disabled = true;
    fetch(raiz.getAttribute('data-ia-demanda-url'), {
      method: 'POST', credentials: 'same-origin', body: JSON.stringify(dados),
      headers: {'Content-Type': 'application/json', 'Accept': 'application/json'}
    }).then(function (r) { return r.json().catch(function () { return {ok: false, erro: 'Resposta inesperada (' + r.status + ').'}; }); })
      .then(function (j) {
        if (j.ok) {
          var linha = form.closest('.ia-acao');
          form.remove();
          var b = linha.querySelector('[data-ia-pedir]');
          if (b) b.outerHTML = '<span class="ia-acao-feita"><i class="ph ph-check" aria-hidden="true"></i> Enviada</span>';
          linha.insertAdjacentHTML('beforeend', '<p class="ia-demanda-ok">' + esc(j.aviso) + '</p>');
          return;
        }
        bt.disabled = false; msg.hidden = false; msg.className = 'ia-r-erro'; msg.textContent = j.erro || 'Não foi enviada.';
      })
      .catch(function () { bt.disabled = false; msg.hidden = false; msg.className = 'ia-r-erro'; msg.textContent = 'Sem conexão: nada foi enviado.'; });
  }

  // o card da OS por cima: a janela do chat fecha guardando a conversa e volta quando o card fecha
  function abrirOs(n) {
    if (!window.NexusOsCard) return;
    var jan = document.getElementById('pu-jan');
    var volta = function () { if (jan) { delete jan.dataset.manter; if (!jan.open) jan.showModal(); } };
    if (jan && jan.open) { jan.dataset.manter = '1'; jan.close(); }
    window.NexusOsCard.abrirFolio(String(n), {status: '', aoFechar: volta});
  }

  document.addEventListener('submit', function (ev) {
    var f = ev.target.closest && ev.target.closest('[data-ia-form]');
    var d = ev.target.closest && ev.target.closest('[data-ia-demanda]');
    if (!f && !d) return;
    ev.preventDefault();
    var raiz = (f || d).closest('[data-ia]');
    if (d) { enviarDemanda(raiz, d); return; }
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
    var os = ev.target.closest('[data-ia-os]');
    if (os) { abrirOs(os.getAttribute('data-ia-os')); return; }
    var p = ev.target.closest('[data-ia-pedir]');
    if (p) { formDemanda(p.closest('[data-ia]'), p.closest('[data-ia-acao]')); return; }
    var s = ev.target.closest('[data-ia-sugestao]');
    if (!s) return;
    var raiz = s.closest('[data-ia]');
    if (raiz.querySelector('[data-ia-enviar]').disabled) return;
    enviar(raiz, s.textContent);
  });
  // a janela que fecha leva a conversa junto (o corpo dela é esvaziado), menos quando fecha para o card da OS
  var jan = document.getElementById('pu-jan');
  if (jan) jan.addEventListener('close', function () { if (!jan.dataset.manter) { historico = []; respostas = {}; } });
})();

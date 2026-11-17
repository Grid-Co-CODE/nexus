/* Base > Equipamentos das usinas: o editor (o painel vem do <script id="eq-dados"> da página).
   Morava dentro de nexus/templates/cadastro/equipamentos.html até 08/11/2026 (o mapa do desembaraço: 6 mil linhas de JS dentro do HTML).
   Roda no mesmo ponto da página, como antes. */
/* Base > Equipamentos das usinas. A lista filtra enquanto se digita. O editor da estrutura trabalha num rascunho: cada
   campo muda só o rascunho, e o Salvar manda tudo de uma vez (JSON) e recebe de volta o estado gravado, com os IDs novos.
   Sair da página, ou usar um botão do passo 1, com mudança não salva pede confirmação. */
(function () {
  var toast = document.getElementById('eq-toast'), relogio = null;
  function avisar(texto, ok) {
    toast.textContent = texto;
    toast.className = 'fr-toast fr-toast--' + (ok ? 'ok' : 'erro');
    toast.hidden = false;
    clearTimeout(relogio);
    relogio = setTimeout(function () { toast.hidden = true; }, ok ? 5000 : 10000);
  }
  function semAcento(s) { return String(s == null ? '' : s).normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, ' ').trim(); }

  /* a lista: filtra enquanto se digita (o Enter ainda filtra no servidor) */
  var busca = document.getElementById('eq-q'), conta = document.getElementById('eq-conta');
  if (busca) {
    busca.addEventListener('input', function () {
      var t = semAcento(busca.value), n = 0;
      document.querySelectorAll('#eq-itens li[data-busca]').forEach(function (li) {
        var ok = !t || semAcento(li.getAttribute('data-busca')).indexOf(t) >= 0;
        li.hidden = !ok; if (ok) n++;
      });
      if (conta) conta.textContent = n;
    });
  }
  // só a LISTA rola até a usina aberta (13/11/2026): o scrollIntoView rolava a página também, e a usina do fim da lista
  // abria com o alto escondido (as abas Equipamentos e De-para e os números)
  var sel = document.querySelector('.eq-item--sel'), itens = document.getElementById('eq-itens');
  if (sel && itens) {
    var y = sel.getBoundingClientRect().top - itens.getBoundingClientRect().top + itens.scrollTop;
    itens.scrollTop = Math.max(0, y - itens.clientHeight / 3);
  }

  var raiz = document.getElementById('eq-editor');
  var dados = document.getElementById('eq-dados');
  var sujo = function () { return false; };
  /* passo 1: confirmação quando há rascunho não salvo, ou quando o formulário pede (desligar chave com inversores) */
  document.querySelectorAll('form.eq-guarda').forEach(function (f) {
    f.addEventListener('submit', function (e) {
      if (sujo() && !window.confirm('A estrutura tem mudanças não salvas, que se perdem. Continuar mesmo assim?')) { e.preventDefault(); return; }
      var pergunta = f.getAttribute('data-confirmar');
      if (pergunta && !window.confirm(pergunta)) { e.preventDefault(); }
    });
  });
  var novaChave = document.querySelector('.eq-chave-nova'), selChave = document.getElementById('eq-chave');
  if (novaChave && selChave) {
    novaChave.addEventListener('input', function () { if (novaChave.value.trim()) selChave.value = ''; });
    selChave.addEventListener('change', function () { if (selChave.value) novaChave.value = ''; });
  }
  if (!raiz || !dados) return;

  var D = JSON.parse(dados.textContent);
  var podeGravar = raiz.getAttribute('data-pode-gravar') === '1';
  var st = null, base = '', seq = 0, cmpAberta = null, chavesAbertas = false;
  /* O Equipamento Supervisório pela fonte (17/11/2026). Levi, na Rio do Peixe I e II: "esse ligar aí só aparece que não
     está ligado no tempo real e não deixa a pessoa fazer uma ligação real"; "esse na fonte é a mesma coisa que
     equipamento supervisório. A diferença é que um é digitado, o outro não. O na fonte eu acho que seria a leitura da
     fonte em si". A coluna "Na fonte" (que só punha o nome escolhido no Equipamento Supervisório do Nexus, sem efeito no
     tempo real) virou o próprio Equipamento Supervisório: na chave com uma fonte que a plataforma liga inversor a
     inversor, ele é o inversor da fonte ligado a este, lido dos cartões (cadastro-depara.js manda no evento
     `eq-fontes`), e escolher grava a LIGAÇÃO no livro da plataforma com o Salvar (eq-ligacao.js, `gravarLigacoes`). Sem
     essa fonte (a Athon liga pelo nome; sem leitura), continua digitado. FONTES[id da chave] = as fontes dela
     (`EqLigacao.fontesPorChave`); LIGA[fonte|id da usina na fonte] = {nome do cadastro: id da fonte ou ""}, o rascunho
     das ligações. */
  var L = window.EqLigacao;
  var FONTES = null, LIGA = {}, COMO = {};        // COMO[id da chave]: lido, sem_leitura, nome (liga pelo nome), erro

  function clonar(x) { return JSON.parse(JSON.stringify(x)); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]; }); }
  function fmt(v, casas) { return v == null || isNaN(v) ? '—' : Number(v).toLocaleString('pt-BR', {minimumFractionDigits: 0, maximumFractionDigits: casas == null ? 1 : casas}); }
  function paraCampo(v) { return v == null ? '' : String(v).replace('.', ','); }
  function lerNumero(s) {
    s = String(s == null ? '' : s).trim();
    if (!s) return null;
    if (s.indexOf(',') >= 0) s = s.replace(/\./g, '').replace(',', '.');
    var n = Number(s);
    return isFinite(n) && n >= 0 ? Math.round(n * 1000) / 1000 : NaN;
  }
  function carregar(ed) {
    D.selo = ed.selo;
    st = {chaves: clonar(ed.chaves), cabines: clonar(ed.cabines), inversores: clonar(ed.inversores)};
    base = JSON.stringify(st);
    /* a Usina Supervisório que se preenche sozinha (17/11/2026, Levi: "a usina supervisório primeiro, que se é ligado à
       fonte lá em cima na base, esse usina supervisório já deve preencher automaticamente"). Na Rio do Peixe I e II os 20
       inversores nasceram antes de a chave ser ligada pelas Fontes de dados, e ficaram sem chave: era escolher a chave
       linha a linha. Com UMA chave na usina, o inversor sem chave entra nela no rascunho (o Salvar grava); com duas ou
       mais, a escolha é da pessoa (a Altair tem seis). */
    chaveSozinha();
    desenhar();
  }
  function chaveSozinha() {
    var sozinha = st.chaves.length === 1 ? st.chaves[0] : null, entraram = 0;
    if (sozinha) st.inversores.forEach(function (x) { if (x.chave == null) { x.chave = sozinha.supervisorio_id; entraram++; } });
    if (entraram) avisar(entraram + (entraram === 1 ? ' inversor sem chave entrou' : ' inversores sem chave entraram') + ' na “' +
                         sozinha.chave + '”, a única chave desta usina. Salve para gravar.', true);
  }
  function ligaPendente() {
    return Object.keys(LIGA).some(function (fk) { var f = fontePorChave(fk); return f && Object.keys(L.decisoes(f, LIGA[fk])).length; });
  }
  sujo = function () { return st !== null && (JSON.stringify(st) !== base || ligaPendente()); };
  function cabPorK(k) { for (var i = 0; i < st.cabines.length; i++) if (st.cabines[i].k === k) return st.cabines[i]; return null; }
  function cabPorNome(n) { var t = semAcento(n); for (var i = 0; i < st.cabines.length; i++) if (semAcento(st.cabines[i].nome) === t) return st.cabines[i]; return null; }
  function invPorNome(n) { var t = semAcento(n); for (var i = 0; i < st.inversores.length; i++) if (semAcento(st.inversores[i].nome) === t) return st.inversores[i]; return null; }
  function chavePorId(id) { for (var i = 0; i < st.chaves.length; i++) if (st.chaves[i].supervisorio_id === id) return st.chaves[i]; return null; }
  function novaCab(nome, kwp) {
    var c = {id: null, k: 'n' + (++seq), nome: nome, potencia_kwp: kwp == null ? null : kwp, equipamento_id: null, codigo_fracttal: ''};
    st.cabines.push(c); return c;
  }
  function invsDaCab(k) { return st.inversores.filter(function (i) { return i.cabine === k; }); }

  /* potência: a do inversor, ou a da cabine dividida pelos inversores dela (calculado) */
  function kwpCalculado(i) {
    if (i.potencia_kwp != null) return null;
    var c = i.cabine ? cabPorK(i.cabine) : null;
    if (!c || c.potencia_kwp == null) return null;
    return c.potencia_kwp / invsDaCab(c.k).length;
  }
  function somas() {
    var cab = 0, temCab = false, inv = 0, calc = 0, strings = 0, semStr = 0, semChave = 0, semCab = 0;
    st.cabines.forEach(function (c) { if (c.potencia_kwp != null) { cab += c.potencia_kwp; temCab = true; } });
    st.inversores.forEach(function (i) {
      if (i.potencia_kwp != null) inv += i.potencia_kwp; else { var x = kwpCalculado(i); if (x != null) calc += x; }
      if (i.strings_esperadas_qtd != null) strings += i.strings_esperadas_qtd; else semStr++;
      if (!i.chave) semChave++;
      if (!i.cabine) semCab++;
    });
    return {cab: temCab ? cab : null, inv: st.inversores.length && (inv || calc) ? inv + calc : null, calc: calc,
            strings: strings, semStr: semStr, semChave: semChave, semCab: semCab};
  }
  function confere(v) {
    var u = D.kwp_usina;
    if (!u || v == null) return '';
    var d = Math.abs(v - u) / u;
    return d <= 0.005 ? 'fecha' : (d <= 0.05 ? 'perto' : 'nao_fecha');
  }
  var ROTULO = {fecha: 'fecha com o Registro mestre', perto: 'perto do Registro mestre (até 5%)', nao_fecha: 'não fecha com o Registro mestre'};
  function caixaPot(rotulo, v, detalhe, ehBase) {
    var c = ehBase ? '' : confere(v), dif = (!ehBase && D.kwp_usina && v != null) ? ((v - D.kwp_usina) / D.kwp_usina * 100) : null;
    return '<div><div class="r">' + esc(rotulo) + '</div><div class="v' + (c ? ' eq-v--' + c : '') + '">' + fmt(v) + ' <small>kWp</small></div>' +
      '<div class="d">' + (c ? esc(ROTULO[c]) + (dif != null ? ' (' + (dif > 0 ? '+' : '') + fmt(dif, 1) + '%)' : '') : esc(detalhe || '')) + '</div></div>';
  }
  function abaUfv() {
    var t = 0, tem = false;
    st.chaves.forEach(function (ch) { var g = (D.aba || {})[ch.chave]; if (g && g.ufv_kwp != null) { t += g.ufv_kwp; tem = true; } });
    return tem ? t : null;
  }
  function htmlPot() {
    var s = somas();
    return caixaPot('Registro mestre' + (D.kwp_de ? ' (' + D.kwp_de + ')' : ''), D.kwp_usina, D.kwp_usina ? 'potência ' + D.kwp_de + ' da ficha × 1.000' : 'sem potência na ficha', true) +
      caixaPot('Aba Equipamentos (UFV)', abaUfv(), 'só referência') +
      caixaPot('Soma das cabines', s.cab, st.cabines.length ? 'cabine sem kWp não soma' : 'nenhuma cabine') +
      caixaPot('Soma dos inversores', s.inv, s.calc ? 'com ' + fmt(s.calc) + ' kWp calculados' : (st.inversores.length ? 'inversor sem kWp não soma' : 'nenhum inversor'));
  }

  /* o desenho do editor inteiro (as mudanças de valor só redesenham o que depende delas: `derivados`) */
  function campo(tipo, idx, nome, valor, extra) {
    return '<input class="gc-campo" data-tipo="' + tipo + '" data-i="' + idx + '" data-campo="' + nome + '" value="' + esc(valor) + '"' + (extra || '') + (podeGravar ? '' : ' disabled') + '>';
  }
  function desenhar() {
    var s = somas(), h = '', ro = podeGravar ? '' : ' disabled';
    /* chaves */
    var noLugar = st.chaves.filter(function (ch) { return ch.substitui_aba; }).length;
    h += '<div class="eq-ed-sec"><button type="button" class="eq-ed-cab eq-ed-recolhe" data-acao="ver-chaves" aria-expanded="' + chavesAbertas + '"><h3>Usina Supervisório <span class="eq-n">' + st.chaves.length +
      (st.chaves.length ? ' · no lugar da aba: ' + noLugar : '') + '</span></h3><i class="ph ph-caret-' + (chavesAbertas ? 'up' : 'down') + '" aria-hidden="true"></i></button>';
    if (!st.chaves.length) h += '<p class="eq-vazio">Nenhuma chave ligada: ligue uma fonte ou uma chave acima antes de montar os inversores.</p>';
    else if (chavesAbertas) {
      h += '<div class="cad-rolagem"><table class="cad-tabela eq-tab eq-tab-chaves"><thead><tr><th>Usina Supervisório</th><th>Usina (exibição)</th>' +
        '<th title="A linha da usina (UFV) e as das cabines saem nesta chave">Chave da usina</th><th class="num">Inversores</th>' +
        '<th>Full O&amp;M</th><th>String Box</th><th title="A plataforma, o gêmeo, as Ligações e o coletor (quando ligado) leem esta chave do Nexus">No lugar da aba</th><th>Diferença com a aba</th></tr></thead><tbody>';
      st.chaves.forEach(function (ch, i) {
        var n = st.inversores.filter(function (x) { return x.chave === ch.supervisorio_id; }).length;
        var ab = (D.aba || {})[ch.chave], ph = (ab && ab.usina) || D.nome_registro || '';
        var cmp = (D.comparacao || {})[ch.supervisorio_id];
        h += '<tr><td><span class="gc-dado">' + esc(ch.chave) + '</span></td>' +
          '<td class="eq-w-exib">' + campo('chave', i, 'usina_exibicao', ch.usina_exibicao, ' maxlength="120" placeholder="' + esc(ph) + '" aria-label="Nome de exibição da chave ' + esc(ch.chave) + '"') + '</td>' +
          '<td class="eq-centro"><input type="radio" name="eq-principal" data-tipo="chave" data-i="' + i + '" data-campo="principal"' + (ch.principal ? ' checked' : '') + ro + ' aria-label="Chave da usina: ' + esc(ch.chave) + '"></td>' +
          '<td class="num">' + n + '</td>' +
          '<td><label class="eq-marca"><input type="checkbox" data-tipo="chave" data-i="' + i + '" data-campo="full_om"' + (ch.full_om ? ' checked' : '') + ro + '> Sim</label></td>' +
          '<td><label class="eq-marca"><input type="checkbox" data-tipo="chave" data-i="' + i + '" data-campo="string_box"' + (ch.string_box ? ' checked' : '') + ro + '> Sim</label></td>' +
          '<td><label class="eq-marca"><input type="checkbox" data-tipo="chave" data-i="' + i + '" data-campo="substitui_aba"' + (ch.substitui_aba ? ' checked' : '') + ro + '> Sim</label></td>' +
          '<td>' + htmlCmp(ch, cmp) + '</td></tr>';
        if (cmpAberta === ch.supervisorio_id && cmp && cmp.dif && cmp.dif.length) {
          h += '<tr class="eq-cmp-linha"><td colspan="8"><ul class="eq-cmp-lista">' + cmp.dif.map(function (t) { return '<li>' + esc(t) + '</li>'; }).join('') + '</ul></td></tr>';
        }
      });
      h += '</tbody></table></div>';
    }
    h += '</div>';
    /* potência */
    h += '<div class="cad-numeros eq-pot" id="eq-pot">' + htmlPot() + '</div>';
    /* cabines */
    h += '<div class="eq-ed-sec"><div class="eq-ed-cab"><h3>Cabines (UG) <span class="eq-n">' + st.cabines.length + '</span></h3>' +
      '<button type="button" class="gc-btn gc-btn--ui gc-btn--contorno" data-acao="nova-cabine"' + ro + '><i class="ph ph-plus"></i> Adicionar cabine</button></div>';
    if (!st.cabines.length) h += '<p class="eq-vazio">Nenhuma cabine. Adicione, ou traga da aba.</p>';
    else {
      h += '<div class="cad-rolagem"><table class="cad-tabela eq-tab"><thead><tr><th>#</th><th>Equipamento</th><th class="num">Potência (kWp)</th><th class="num" title="Digite quantos: os inversores nascem com o nome da cabine (Inversor 1.1, 1.2…)">N de Inversores</th><th></th></tr></thead><tbody>';
      st.cabines.forEach(function (c, i) {
        h += '<tr><td class="id">' + (i + 1) + '</td><td>' + campo('cab', i, 'nome', c.nome, ' maxlength="120" aria-label="Nome da cabine ' + (i + 1) + '"') + '</td>' +
          '<td class="eq-w-num">' + campo('cab', i, 'potencia_kwp', paraCampo(c.potencia_kwp), ' inputmode="decimal" aria-label="kWp da cabine ' + esc(c.nome) + '"') + '</td>' +
          '<td class="eq-w-num"><input class="gc-campo" data-acao-n="' + i + '" data-cont="' + esc(c.k) + '" inputmode="numeric" value="' + invsDaCab(c.k).length + '" aria-label="Quantos inversores na cabine ' + esc(c.nome) + '"' + ro + '></td>' +
          '<td class="eq-acoes-linha"><button type="button" class="gc-btn gc-btn--ui gc-btn--fantasma" data-acao="tirar-cabine" data-i="' + i + '"' + ro + ' aria-label="Remover a cabine ' + esc(c.nome) + '"><i class="ph ph-trash"></i></button></td></tr>';
      });
      h += '</tbody></table></div>';
    }
    h += '</div>';
    /* inversores */
    h += '<div class="eq-ed-sec"><div class="eq-ed-cab"><h3>Inversores <span class="eq-n" id="eq-n-inv">' + st.inversores.length + ' · ' + fmt(s.strings, 0) + ' strings</span></h3>' +
      '<span class="mudo" id="eq-faltas">' + faltas(s) + '</span>' +
      '<button type="button" class="gc-btn gc-btn--ui gc-btn--contorno" data-acao="novo-inversor"' + ro + '><i class="ph ph-plus"></i> Adicionar inversor</button></div>';
    if (!st.inversores.length) h += '<p class="eq-vazio">Nenhum inversor. Gere os de uma cabine, adicione um a um, ou traga da aba.</p>';
    else {
      var opChaves = function (v) { return '<option value="">sem chave</option>' + st.chaves.map(function (ch) { return '<option value="' + ch.supervisorio_id + '"' + (ch.supervisorio_id === v ? ' selected' : '') + '>' + esc(ch.chave) + '</option>'; }).join(''); };
      var opCabs = function (v) { return '<option value="">sem cabine</option>' + st.cabines.map(function (c) { return '<option value="' + esc(c.k) + '"' + (c.k === v ? ' selected' : '') + '>' + esc(c.nome) + '</option>'; }).join(''); };
      h += '<div class="cad-rolagem"><table class="cad-tabela eq-tab eq-tab-inv"><thead><tr><th>#</th><th>Usina Supervisório</th><th>Equipamento</th>' +
        '<th title="O inversor como a fonte o manda. Com uma fonte que a plataforma liga inversor a inversor, vem dela e se escolhe na lista: o Salvar grava a ligação na plataforma, e o tempo real passa a usá-la. Sem essa fonte, digite o nome como o supervisório o escreve.">Equipamento Supervisório</th>' +
        '<th>Equipamento Parente</th><th class="num">Potência (kWp)</th><th class="num">Strings Ativas</th><th></th></tr></thead><tbody>';
      st.inversores.forEach(function (x, i) {
        var calc = kwpCalculado(x);
        h += '<tr' + (!x.chave && st.chaves.length ? ' class="eq-linha-falta"' : '') + '><td class="id">' + (i + 1) + '</td>' +
          '<td class="eq-w-chave"><select class="gc-campo" data-tipo="inv" data-i="' + i + '" data-campo="chave" aria-label="Usina Supervisório de ' + esc(x.nome) + '"' + ro + '>' + opChaves(x.chave) + '</select></td>' +
          '<td class="eq-w-nome">' + campo('inv', i, 'nome', x.nome, ' maxlength="120" aria-label="Equipamento ' + (i + 1) + '"') + '</td>' +
          '<td class="eq-w-sup">' + celSup(x, i) + '</td>' +
          '<td class="eq-w-cab"><select class="gc-campo" data-tipo="inv" data-i="' + i + '" data-campo="cabine" aria-label="Equipamento Parente de ' + esc(x.nome) + '"' + ro + '>' + opCabs(x.cabine) + '</select></td>' +
          '<td class="eq-w-num">' + campo('inv', i, 'potencia_kwp', paraCampo(x.potencia_kwp), ' inputmode="decimal" placeholder="' + (calc != null ? '≈ ' + fmt(calc) + ' calc.' : '') + '" aria-label="kWp de ' + esc(x.nome) + '"') + '</td>' +
          '<td class="eq-w-str">' + campo('inv', i, 'strings_esperadas_qtd', x.strings_esperadas_qtd == null ? '' : x.strings_esperadas_qtd, ' inputmode="numeric" aria-label="Strings Ativas de ' + esc(x.nome) + '"') + '</td>' +
          '<td><button type="button" class="gc-btn gc-btn--ui gc-btn--fantasma" data-acao="tirar-inversor" data-i="' + i + '"' + ro + ' aria-label="Remover o inversor ' + esc(x.nome) + '"><i class="ph ph-trash"></i></button></td></tr>';
      });
      h += '</tbody></table></div>';
    }
    h += '</div>';
    /* a barra */
    var temAba = st.chaves.some(function (ch) { return (D.aba || {})[ch.chave]; });
    h += '<div class="eq-barra">' +
      '<button type="button" class="gc-btn gc-btn--ui gc-btn--contorno" data-acao="trazer"' + (temAba && podeGravar ? '' : ' disabled') + ' title="' + (temAba ? 'Preenche o rascunho com o que a aba tem para as chaves ligadas (só o que está vazio; nada é apagado)' : 'Nenhuma chave ligada está na aba') + '"><i class="ph ph-download-simple"></i> Trazer da aba</button>' +
      '<button type="button" class="gc-btn gc-btn--ui gc-btn--contorno" data-acao="distribuir"' + ro + ' title="Preenche o kWp vazio: a cabine pelo que falta da usina, o inversor pelo que falta da cabine"><i class="ph ph-arrows-split"></i> Distribuir potência</button>' +
      '<span class="eq-estado" id="eq-estado"></span>' +
      '<button type="button" class="gc-btn gc-btn--ui gc-btn--fantasma" data-acao="descartar"' + ro + '>Descartar mudanças</button>' +
      '<button type="button" class="gc-btn gc-btn--ui gc-btn--primario" data-acao="salvar"' + ro + '><i class="ph ph-floppy-disk"></i> Salvar</button></div>';
    raiz.innerHTML = h;
    estado();
  }
  /* A comparação é do que está SALVO (o servidor monta a visão e compara com a aba): com mudança no rascunho, diz isso. */
  function htmlCmp(ch, cmp) {
    if (!cmp) return '<span class="mudo">—</span>';
    var nota = sujo() ? ' <span class="mudo eq-cmp-nota">(do que está salvo)</span>' : '';
    if (!cmp.na_aba) return '<span class="cad-chip cad-chip--alerta" title="' + esc(cmp.dif[0] || '') + '">fora da aba</span>' + nota;
    if (cmp.iguais) return '<span class="cad-chip cad-chip--operacao">igual à aba</span>' + nota;
    return '<button type="button" class="eq-cmp-botao" data-acao="ver-cmp" data-sid="' + ch.supervisorio_id + '" aria-expanded="' + (cmpAberta === ch.supervisorio_id) + '">' +
      '<span class="cad-chip cad-chip--alerta">' + cmp.n + ' diferença' + (cmp.n > 1 ? 's' : '') + '</span> ' + (cmpAberta === ch.supervisorio_id ? 'esconder' : 'ver') + '</button>' + nota;
  }
  function faltas(s) {
    var p = [];
    if (s.semChave && st.chaves.length) p.push(s.semChave + ' sem chave');
    if (s.semCab && st.cabines.length) p.push(s.semCab + ' sem cabine');
    if (s.semStr) p.push(s.semStr + ' sem strings');
    return p.length ? 'Falta: ' + p.join(' · ') : '';
  }
  function estado() {
    var e = document.getElementById('eq-estado');
    if (e) { var d = sujo(); e.textContent = d ? 'Mudanças não salvas' : 'Tudo salvo'; e.className = 'eq-estado' + (d ? ' eq-estado--sujo' : ''); }
  }
  function derivados() {
    var s = somas();
    var pot = document.getElementById('eq-pot'); if (pot) pot.innerHTML = htmlPot();
    st.cabines.forEach(function (c) {
      var td = raiz.querySelector('[data-cont="' + c.k + '"]'); if (td && td !== document.activeElement) td.value = invsDaCab(c.k).length;
      raiz.querySelectorAll('select[data-campo="cabine"] option[value="' + c.k + '"]').forEach(function (o) { o.textContent = c.nome; });
    });
    raiz.querySelectorAll('input[data-tipo="inv"][data-campo="potencia_kwp"]').forEach(function (inp) {
      var x = st.inversores[+inp.getAttribute('data-i')], calc = x ? kwpCalculado(x) : null;
      inp.placeholder = calc != null ? '≈ ' + fmt(calc) + ' calc.' : '';
    });
    var n = document.getElementById('eq-n-inv'); if (n) n.textContent = st.inversores.length + ' · ' + fmt(s.strings, 0) + ' strings';
    var f = document.getElementById('eq-faltas'); if (f) f.textContent = faltas(s);
    estado();
  }

  /* cada campo muda o rascunho */
  function mudar(t) {
    var tipo = t.getAttribute('data-tipo'), i = +t.getAttribute('data-i'), c = t.getAttribute('data-campo');
    var lista = tipo === 'cab' ? st.cabines : (tipo === 'inv' ? st.inversores : st.chaves), x = lista[i];
    if (!x) return false;
    t.removeAttribute('aria-invalid');
    if (c === 'potencia_kwp' || c === 'strings_esperadas_qtd') {
      var v = lerNumero(t.value);
      if (v !== null && (isNaN(v) || (c === 'strings_esperadas_qtd' && v !== Math.round(v)))) { t.setAttribute('aria-invalid', 'true'); return false; }
      x[c] = v;
    } else if (c === 'principal') {
      st.chaves.forEach(function (o) { o.principal = false; });
      x.principal = true;
    } else if (t.type === 'checkbox') {
      x[c] = t.checked;
    } else if (c === 'chave') {
      x.chave = t.value ? +t.value : null;
    } else if (c === 'cabine') {
      x.cabine = t.value || null;
      // o inversor novo, com o nome que o Nexus deu, troca de nome junto com a cabine (Inversor 2.3 na cabine 2)
      if (x.id == null && AUTO.test(x.nome)) { x.nome = ''; x.nome = nomeNaCabine(x.cabine ? cabPorK(x.cabine) : null); }
    } else {
      x[c] = t.value;
    }
    return true;
  }
  raiz.addEventListener('input', function (e) {
    var t = e.target;
    if (!t.hasAttribute('data-campo') || t.tagName === 'SELECT' || t.type === 'checkbox' || t.type === 'radio') return;
    if (mudar(t)) derivados(); else estado();
  });
  raiz.addEventListener('change', function (e) {
    var t = e.target;
    if (!t.hasAttribute('data-campo') || (t.tagName !== 'SELECT' && t.type !== 'checkbox' && t.type !== 'radio')) return;
    var r = mudar(t);
    if (t.getAttribute('data-campo') === 'chave' || t.getAttribute('data-campo') === 'cabine' || t.getAttribute('data-tipo') === 'chave') desenhar(); else if (r) derivados();
  });
  // o inversor da fonte escolhido para este: só o rascunho das ligações (grava no Salvar, na plataforma)
  raiz.addEventListener('change', function (e) {
    var t = e.target;
    if (t.hasAttribute('data-liga')) {
      var fk = t.getAttribute('data-liga'), alvo = t.getAttribute('data-alvo'), f = fontePorChave(fk), v = t.value;
      if (!f) return;
      var r = LIGA[fk] = LIGA[fk] || {};
      // o mesmo inversor da fonte escolhido antes para outro, no rascunho, sai de lá (um da fonte é um do cadastro)
      if (v) Object.keys(r).forEach(function (k) { if (k !== alvo && r[k] === v) delete r[k]; });
      r[alvo] = v;
      if ((L.efetiva(f, {}).porAlvo[alvo] || [])[0] === v || (!v && !(L.efetiva(f, {}).porAlvo[alvo] || []).length)) delete r[alvo];
      if (!Object.keys(L.decisoes(f, r)).length) delete LIGA[fk];
      desenhar();
    } else if (t.hasAttribute('data-acao-n')) {
      var n = lerNumero(t.value), i = +t.getAttribute('data-acao-n');
      if (n == null || isNaN(n) || n !== Math.round(n) || n > 300) { t.setAttribute('aria-invalid', 'true'); avisar('Diga quantos inversores (de 0 a 300).', false); return; }
      t.removeAttribute('aria-invalid');
      ajustarQtd(i, n);
    }
  });

  /* os inversores pela cabine (17/11/2026, Levi: "Quando eu adicionar inversor aparece sequencial: 1,2,3,4,5 porém o
     ideal é conforme eu for adicionando as cabines vai renomeando de acordo com a cabine: inversor 1.1, 1.2 etc. Ou ao
     invés de adicionar inversor de por inversor a pessoa pode digitar lá na tabela das cabines a quantidade de
     inversores, aí já gera automático e eu só preencho as strings"). O nome é "Inversor <nº da cabine>.<nº na cabine>";
     sem cabine, "Inversor <n>". */
  var AUTO = /^Inversor \d+(\.\d+)?$/;
  function nomeNaCabine(c) {
    var i = st.cabines.indexOf(c), k = 0, nome;
    if (i < 0) { k = st.inversores.length; do { nome = 'Inversor ' + (++k); } while (invPorNome(nome)); return nome; }
    do { nome = 'Inversor ' + (i + 1) + '.' + (++k); } while (invPorNome(nome));
    return nome;
  }
  function chavePadrao(c) {
    // a chave dos inversores que a cabine já tem; sem eles, a única chave ligada
    var dela = c ? invsDaCab(c.k).filter(function (x) { return x.chave; }) : [];
    if (dela.length) return dela[dela.length - 1].chave;
    return st.chaves.length === 1 ? st.chaves[0].supervisorio_id : null;
  }
  function novoInversor(c) {
    var x = {id: null, nome: nomeNaCabine(c), chave: chavePadrao(c), cabine: c ? c.k : null, equipamento_supervisorio: '',
             potencia_kwp: null, strings_esperadas_qtd: null, equipamento_id: null, codigo_fracttal: ''};
    st.inversores.push(x);
    return x;
  }
  // o "N de Inversores" da cabine: a mais, nascem com o nome da cabine; a menos, saem os novos e vazios do fim (o que
  // já foi salvo, ou tem dado, não sai daqui: tira-se na tabela dos inversores)
  function ajustarQtd(i, alvo) {
    var c = st.cabines[i], dela = invsDaCab(c.k);
    if (alvo > dela.length) {
      for (var n = dela.length; n < alvo; n++) novoInversor(c);
      desenhar();
      avisar((alvo - dela.length) + ' inversor(es) na cabine ' + c.nome + '. Preencha as strings e salve.', true);
      return;
    }
    var tirar = dela.length - alvo, tirados = 0;
    for (var j = dela.length - 1; j >= 0 && tirados < tirar; j--) {
      var x = dela[j];
      if (x.id == null && !x.equipamento_supervisorio && x.potencia_kwp == null && x.strings_esperadas_qtd == null) {
        st.inversores.splice(st.inversores.indexOf(x), 1); tirados++;
      }
    }
    desenhar();
    if (tirados < tirar) avisar('Saíram ' + tirados + ' de ' + tirar + ': os outros já estão salvos ou têm dado. Tire-os na tabela dos inversores.', false);
  }

  /* a coluna Equipamento Supervisório */
  function fontePorChave(fk) {
    var achada = null;
    Object.keys(FONTES || {}).forEach(function (sid) { (FONTES[sid] || []).forEach(function (f) { if (f.chave === fk) achada = f; }); });
    return achada;
  }
  function celSup(x, i) {
    var fs = FONTES && x.chave != null ? (FONTES[x.chave] || []) : [];
    if (!fs.length) {
      // sem fonte que ligue inversor a inversor: digitado, como a aba (a Athon e a Axis ligam pelo nome que mandam)
      var dica = x.chave != null && COMO[x.chave] === 'nome' ? ' title="Nesta fonte o inversor liga pelo nome que ela manda: escreva-o como ela escreve"' : '';
      return campo('inv', i, 'equipamento_supervisorio', x.equipamento_supervisorio, ' maxlength="120" placeholder="ex.: INVERSOR01" aria-label="Equipamento Supervisório de ' + esc(x.nome) + '"' + dica);
    }
    return fs.map(function (f) { return selLiga(x, f, fs.length > 1); }).join('');
  }
  function selLiga(x, f, comNome) {
    var a = L.alvoDo(x, f), pre = comNome ? '<small class="mudo eq-liga-fonte">' + esc(f.fonte_nome) + '</small>' : '';
    if (!a) {
      return '<span class="eq-liga">' + pre + '<span class="mudo" title="A plataforma lê o cadastro desta chave da aba Equipamentos, e a aba não tem “' + esc(x.nome) +
        '”. Salve e marque a chave “No lugar da aba” para a plataforma conhecê-lo; aí ele se liga aqui.">fora do cadastro da plataforma</span></span>';
    }
    var ef = L.efetiva(f, LIGA[f.chave]), meus = ef.porAlvo[a.nome] || [], sel = meus[0] || '';
    var mudou = !!(LIGA[f.chave] && Object.prototype.hasOwnProperty.call(LIGA[f.chave], a.nome));
    var exib = function (nome) { var b = f.alvos.filter(function (y) { return y.nome === nome; })[0]; return (b && (b.exibicao || b.nome)) || nome; };
    var op = '<option value="">' + (meus.length ? 'sem ligação' : 'ligar a…') + '</option>' + f.linhas.map(function (l) {
      var outro = ef.porId[l.id] && ef.porId[l.id] !== a.nome ? ef.porId[l.id] : null;
      var rot = (l.rotulo && l.rotulo !== l.id ? l.rotulo : 'id ' + l.id + ' (sem nome na fonte)') + (l.repetido ? ' · id ' + l.id : '') + (outro ? ' · hoje no ' + exib(outro) : '') +
                (l.hoje ? '' : ' · não leu hoje');
      return '<option value="' + esc(l.id) + '"' + (l.id === sel ? ' selected' : '') + '>' + esc(rot) + '</option>';
    }).join('');
    var tom = mudou ? 'alerta' : (meus.length ? 'ok' : ''), dica = mudou ? 'Escolhido agora: grava com o Salvar' :
      (meus.length ? 'Ligado na plataforma (' + f.fonte_nome + ')' : 'Sem ligação: o tempo real não sabe as esperadas deste inversor');
    return '<span class="eq-liga">' + pre + '<i class="eqx-luz' + (tom ? ' eqx-luz--' + tom : '') + '" role="img" aria-label="' + esc(dica) + '" title="' + esc(dica) + '"></i>' +
      '<select class="gc-campo eq-liga-esc" data-liga="' + esc(f.chave) + '" data-alvo="' + esc(a.nome) + '" aria-label="O inversor de ' + esc(f.fonte_nome) + ' ligado a ' + esc(x.nome) + '"' + (podeGravar ? '' : ' disabled') + '>' + op + '</select>' +
      (meus.length > 1 ? '<span class="gc-status gc-status--alerta" title="A fonte manda ' + meus.length + ' inversores ligados a este: escolha um">' + meus.length + ' da fonte</span>' : '') + '</span>';
  }
  document.addEventListener('eq-fontes', function (e) {
    COMO = {};
    (e.detail || []).forEach(function (c) {
      // a plataforma sem a lista da fonte (a leitura do ciclo dela) não diz "sem par": diz que não leu
      if (c.supervisorio_id != null) {
        var k = c.erro ? 'erro' : (!c.edita_inversor ? 'nome' : ((c.sem_leitura || !(c.linhas || []).length) ? 'sem_leitura' : 'lido'));
        if (COMO[c.supervisorio_id] !== 'lido') COMO[c.supervisorio_id] = k;
      }
    });
    FONTES = L.fontesPorChave(e.detail || []);
    // o rascunho das ligações de uma fonte que sumiu da leitura não vale mais
    Object.keys(LIGA).forEach(function (fk) { if (!fontePorChave(fk)) delete LIGA[fk]; });
    if (st) desenhar();
  });

  /* a ligação gravada na plataforma: o passe da porta única abre a sessão dela neste navegador (como a janela "Ligar
     a…"), e cada fonte vai num POST ao `/api/admin/de-para/decidir`, o mesmo do editor De-para de lá */
  function pedidosLiga() {
    return Object.keys(LIGA).map(function (fk) {
      var f = fontePorChave(fk), inv = f ? L.decisoes(f, LIGA[fk]) : {};
      return f && Object.keys(inv).length ? {fonte: f.fonte, id: String(f.plant_id), inversores: inv} : null;
    }).filter(Boolean);
  }
  function json(r) { return r.json().catch(function () { return {ok: false, motivo: 'resposta inesperada (' + r.status + ')'}; }); }
  function gravarLigacoes(pedidos) {
    var feitas = 0;
    return fetch(D.passe_url, {method: 'POST', credentials: 'same-origin', headers: {'Accept': 'application/json'}})
      .then(json)
      .then(function (p) {
        if (!p.ok) throw new Error(p.motivo || 'sem o passe da plataforma');
        var corpo = new URLSearchParams();
        corpo.set('passe', p.passe);
        return fetch(p.entrar, {method: 'POST', credentials: 'same-origin', body: corpo, redirect: 'manual'}).then(function (r) {
          if (r.type !== 'opaqueredirect' && !(r.status >= 200 && r.status < 400)) throw new Error('a plataforma recusou o passe (' + r.status + ')');
          return p.decidir;
        });
      })
      .then(function (url) {
        return pedidos.reduce(function (cadeia, ped) {
          return cadeia.then(function () {
            return fetch(url, {method: 'POST', credentials: 'same-origin', body: JSON.stringify(ped),
                               headers: {'Content-Type': 'application/json', 'Accept': 'application/json'}})
              .then(function (r) {
                return json(r).then(function (j) {
                  if (!r.ok || !j.ok) throw new Error((j.error || j.motivo || 'a plataforma respondeu ' + r.status) +
                                                      (feitas ? ' (' + feitas + ' ligação(ões) de antes já gravada(s))' : ''));
                  feitas += j.gravadas || Object.keys(ped.inversores).length;
                });
              });
          });
        }, Promise.resolve());
      })
      .then(function () { return feitas; });
  }

  /* os botões */
  function trazer() {
    var aba = D.aba || {}, cabNovas = 0, invNovos = 0, preench = 0, renomeados = 0;
    /* a chave da usina é a que tem a linha UFV na aba, se for uma só entre as ligadas */
    var comUfv = st.chaves.filter(function (ch) { var g = aba[ch.chave]; return g && g.ufv_kwp != null; });
    var principalAntes = st.chaves.filter(function (ch) { return ch.principal; })[0];
    if (comUfv.length === 1 && comUfv[0] !== principalAntes) {
      st.chaves.forEach(function (ch) { ch.principal = false; });
      comUfv[0].principal = true; preench++;
    }
    st.chaves.forEach(function (ch) {
      var g = aba[ch.chave]; if (!g) return;
      if (!ch.usina_exibicao && g.usina) { ch.usina_exibicao = g.usina; preench++; }
      if (g.full_om && !ch.full_om) { ch.full_om = true; preench++; }
      if (g.string_box && !ch.string_box) { ch.string_box = true; preench++; }
      g.cabines.forEach(function (a) {
        var c = cabPorNome(a.nome);
        if (!c) { novaCab(a.nome, a.kwp); cabNovas++; }
        else if (c.potencia_kwp == null && a.kwp != null) { c.potencia_kwp = a.kwp; preench++; }
      });
      g.inversores.forEach(function (a) {
        var x = null;
        st.inversores.forEach(function (i) {
          if (x || i.chave !== ch.supervisorio_id) return;
          if ((a.equipamento_supervisorio && semAcento(i.equipamento_supervisorio) === semAcento(a.equipamento_supervisorio)) || semAcento(i.nome) === semAcento(a.nome)) x = i;
        });
        var cab = null;
        if (a.cabine) { cab = cabPorNome(a.cabine); if (!cab) { cab = novaCab(a.cabine, null); cabNovas++; } }
        if (x) {
          if (!x.equipamento_supervisorio && a.equipamento_supervisorio) { x.equipamento_supervisorio = a.equipamento_supervisorio; preench++; }
          if (!x.cabine && cab) { x.cabine = cab.k; preench++; }
          if (x.potencia_kwp == null && a.kwp != null) { x.potencia_kwp = a.kwp; preench++; }
          if (x.strings_esperadas_qtd == null && a.strings != null) { x.strings_esperadas_qtd = a.strings; preench++; }
          return;
        }
        var nome = a.nome;
        if (invPorNome(nome)) { nome = a.nome + ' · ' + ch.chave; renomeados++; }
        st.inversores.push({id: null, nome: nome, chave: ch.supervisorio_id, cabine: cab ? cab.k : null,
                            equipamento_supervisorio: a.equipamento_supervisorio || '', potencia_kwp: a.kwp,
                            strings_esperadas_qtd: a.strings, equipamento_id: null, codigo_fracttal: ''});
        invNovos++;
      });
    });
    desenhar();
    var p = [];
    if (cabNovas) p.push(cabNovas + ' cabine' + (cabNovas > 1 ? 's' : '') + ' nova' + (cabNovas > 1 ? 's' : ''));
    if (invNovos) p.push(invNovos + ' inversor' + (invNovos > 1 ? 'es' : '') + ' novo' + (invNovos > 1 ? 's' : ''));
    if (preench) p.push(preench + ' campo' + (preench > 1 ? 's' : '') + ' vazio' + (preench > 1 ? 's' : '') + ' preenchido' + (preench > 1 ? 's' : ''));
    if (renomeados) p.push(renomeados + ' com o nome repetido ganharam a chave no nome');
    avisar(p.length ? 'Da aba: ' + p.join(', ') + '. Confira e salve.' : 'A aba não tem nada que falte aqui.', true);
  }
  function distribuir() {
    var nc = 0, ni = 0;
    if (D.kwp_usina) {
      var vazias = st.cabines.filter(function (c) { return c.potencia_kwp == null; });
      var resto = D.kwp_usina - st.cabines.reduce(function (t, c) { return t + (c.potencia_kwp || 0); }, 0);
      if (vazias.length && resto > 0) vazias.forEach(function (c) { c.potencia_kwp = Math.round(resto / vazias.length * 1000) / 1000; nc++; });
    }
    st.cabines.forEach(function (c) {
      if (c.potencia_kwp == null) return;
      var dela = invsDaCab(c.k), vaz = dela.filter(function (i) { return i.potencia_kwp == null; });
      var resto = c.potencia_kwp - dela.reduce(function (t, i) { return t + (i.potencia_kwp || 0); }, 0);
      if (vaz.length && resto > 0) vaz.forEach(function (i) { i.potencia_kwp = Math.round(resto / vaz.length * 1000) / 1000; ni++; });
    });
    desenhar();
    avisar(nc || ni ? 'kWp preenchido em ' + nc + ' cabine(s) e ' + ni + ' inversor(es). Confira e salve.' : 'Nada para distribuir: não há kWp vazio com base para calcular.', !!(nc || ni));
  }
  function salvar(botao) {
    var antes = JSON.parse(base).chaves;
    var novas = st.chaves.filter(function (ch) {
      var b = antes.filter(function (x) { return x.supervisorio_id === ch.supervisorio_id; })[0];
      return ch.substitui_aba && !(b && b.substitui_aba);
    });
    var comDif = novas.filter(function (ch) { var c = (D.comparacao || {})[ch.supervisorio_id]; return !c || !c.iguais; });
    if (comDif.length && !window.confirm('Com o Salvar, ' + comDif.map(function (ch) { return ch.chave; }).join(', ') +
        ' passa' + (comDif.length > 1 ? 'm' : '') + ' a ser lida' + (comDif.length > 1 ? 's' : '') + ' do Nexus, e não da aba, e a coluna "Diferença com a aba" mostra diferenças (do que está salvo). Salvar mesmo assim?')) return;
    var corpo = {usina_id: D.usina_id, selo: D.selo, chaves: st.chaves, cabines: st.cabines, inversores: st.inversores};
    var estrutura = JSON.stringify(st) !== base, ligacoes = pedidosLiga();
    botao.disabled = true;
    // a estrutura primeiro (o Nexus); as ligações depois (a plataforma), só com a estrutura gravada
    (estrutura || !ligacoes.length
      ? fetch(D.salvar_url, {method: 'POST', credentials: 'same-origin', body: JSON.stringify(corpo),
                             headers: {'Content-Type': 'application/json', 'Accept': 'application/json'}})
          .then(function (r) { return r.json().catch(function () { return {ok: false, erro: 'Resposta inesperada (' + r.status + '): nada foi gravado.'}; }); })
          .then(function (j) {
            if (!j.ok) { avisar(j.erro || 'Não gravou.', false); return null; }
            if (j.comparacao) D.comparacao = j.comparacao;
            carregar(j.editor);
            return j.aviso || 'Salvo.';
          })
      : Promise.resolve(''))
      .then(function (aviso) {
        if (aviso === null) { botao.disabled = false; return; }
        if (!ligacoes.length) { botao.disabled = false; avisar(aviso, true); return; }
        return gravarLigacoes(ligacoes).then(function (n) {
          LIGA = {};
          botao.disabled = false;
          desenhar();
          avisar((aviso ? aviso + ' ' : '') + n + (n === 1 ? ' ligação gravada' : ' ligações gravadas') + ' na plataforma: o tempo real usa a partir da próxima leitura da fonte.', true);
          document.dispatchEvent(new CustomEvent('eq-fontes-reler'));
        }, function (ex) {
          botao.disabled = false;
          estado();
          avisar((aviso ? aviso + ' ' : '') + 'A ligação não foi gravada na plataforma: ' + ex.message + '. O que você escolheu continua aqui: tente o Salvar de novo.', false);
        });
      })
      .catch(function () { botao.disabled = false; avisar('Sem conexão: nada foi gravado.', false); });
  }
  raiz.addEventListener('click', function (e) {
    var b = e.target.closest('[data-acao]'); if (!b || b.disabled) return;
    var a = b.getAttribute('data-acao'), i = +b.getAttribute('data-i');
    if (a === 'nova-cabine') {
      var m = st.cabines.length, nc;
      do { nc = 'UG ' + String(++m).padStart(2, '0'); } while (cabPorNome(nc));
      novaCab(nc, null); desenhar();
    }
    else if (a === 'novo-inversor') {
      // na última cabine, com o nome dela (Inversor 3.4); sem cabine, Inversor <n>
      novoInversor(st.cabines.length ? st.cabines[st.cabines.length - 1] : null);
      desenhar();
    }
    else if (a === 'ver-chaves') { chavesAbertas = !chavesAbertas; desenhar(); }
    else if (a === 'tirar-cabine') {
      var c = st.cabines[i], dela = invsDaCab(c.k);
      if (dela.length && !window.confirm('A cabine ' + c.nome + ' tem ' + dela.length + ' inversor(es): eles ficam sem cabine (não somem). Remover a cabine?')) return;
      dela.forEach(function (x) { x.cabine = null; });
      st.cabines.splice(i, 1); desenhar();
    }
    else if (a === 'tirar-inversor') { st.inversores.splice(i, 1); desenhar(); }
    else if (a === 'trazer') { trazer(); }
    else if (a === 'distribuir') { distribuir(); }
    else if (a === 'ver-cmp') { var sid = +b.getAttribute('data-sid'); cmpAberta = cmpAberta === sid ? null : sid; desenhar(); }
    else if (a === 'descartar') { if (!sujo() || window.confirm('Descartar as mudanças não salvas?')) { st = JSON.parse(base); LIGA = {}; chaveSozinha(); desenhar(); } }
    else if (a === 'salvar') { salvar(b); }
  });
  window.addEventListener('beforeunload', function (e) { if (sujo()) { e.preventDefault(); e.returnValue = ''; } });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && document.activeElement && document.activeElement.classList.contains('fr-dica-botao')) document.activeElement.blur();
  });

  carregar(D);
})();

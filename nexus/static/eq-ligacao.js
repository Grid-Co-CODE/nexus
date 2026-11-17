/* A ligação de cada inversor do cadastro ao inversor da fonte, na tabela dos inversores de Base > Equipamentos das usinas
   (17/11/2026). Só a conta, sem a página: o cadastro-equipamentos.js desenha e grava, e os testes rodam isto no node.

   Levi, na Rio do Peixe I e II: "esse ligar aí só aparece que não está ligado no tempo real e não deixa a pessoa fazer uma
   ligação real"; "o na fonte eu acho que seria a leitura da fonte em si". A ligação de verdade é a do livro da plataforma
   (`nexus_depara`: o id do inversor na fonte → o nome do cadastro), a mesma do editor De-para dela, e vale no tempo real.
   Aqui:
   - `fontesPorChave(cartoes)`: as fontes de cada chave do supervisório que a plataforma liga inversor a inversor (API PV,
     conta oem@, scadaGridco) e que ela leu. Fonte que liga pelo nome (Athon, Axis), sem leitura ou com erro fica fora:
     nela o Equipamento Supervisório segue digitado;
   - `alvoDo(x, fonte)`: o inversor do cadastro da plataforma que é este inversor do Nexus (o nome no supervisório e, sem
     ele, o nome do equipamento), a mesma régua do `depara_fontes._inversor_do_nexus`;
   - `efetiva(fonte, rascunho)`: a ligação de agora com o que a pessoa escolheu por cima. Escolher o inversor da fonte
     que hoje está noutro do cadastro o TIRA de lá (um inversor da fonte é um inversor do cadastro);
   - `decisoes(fonte, rascunho)`: o que mandar ao `/api/admin/de-para/decidir` ({id da fonte: nome do cadastro}). O que
     só perdeu a ligação manda "" (desfaz) quando ela era decidida na tela; a do código ou do nome não se desfaz por lá, e
     a releitura dos cartões depois de gravar mostra como ficou. */
(function (raiz) {
  'use strict';

  function norm(s) {
    return String(s == null ? '' : s).normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
  }

  function fontesPorChave(cartoes) {
    var out = {};
    (cartoes || []).forEach(function (c) {
      if (c == null || c.supervisorio_id == null || !c.edita_inversor || c.erro || c.sem_leitura) return;
      var linhas = (c.linhas || []).filter(function (l) { return l && l.id !== '' && l.id != null; });
      if (!linhas.length || !(c.alvos || []).length) return;
      (out[c.supervisorio_id] = out[c.supervisorio_id] || []).push({
        chave: c.fonte + '|' + c.plant_id, fonte: c.fonte, plant_id: c.plant_id, fonte_nome: c.fonte_nome || c.fonte,
        linhas: linhas.map(function (l) {
          return {id: String(l.id), rotulo: l.fonte || '', repetido: !!l.repetido, modo: l.modo,
                  alvo: l.alvo && l.alvo.nome ? String(l.alvo.nome) : null, hoje: l.na_fonte_hoje !== false};
        }),
        alvos: (c.alvos || []).filter(function (a) { return a && a.nome; })
      });
    });
    return out;
  }

  function alvoDo(x, fonte) {
    var sup = norm(x && x.equipamento_supervisorio), nome = norm(x && x.nome), alvos = (fonte && fonte.alvos) || [];
    var i;
    if (sup) for (i = 0; i < alvos.length; i++) if (norm(alvos[i].nome) === sup) return alvos[i];
    if (nome) for (i = 0; i < alvos.length; i++) if (norm(alvos[i].nome) === nome || norm(alvos[i].exibicao) === nome) return alvos[i];
    return null;
  }

  // {porId: {id da fonte: nome do alvo | null}, porAlvo: {nome do alvo: [ids da fonte]}}
  function efetiva(fonte, rascunho) {
    var porId = {}, r = rascunho || {};
    fonte.linhas.forEach(function (l) { porId[l.id] = l.alvo; });
    Object.keys(r).forEach(function (alvo) {
      Object.keys(porId).forEach(function (id) { if (porId[id] === alvo) porId[id] = null; });
      if (r[alvo]) porId[String(r[alvo])] = alvo;
    });
    var porAlvo = {};
    fonte.linhas.forEach(function (l) { var a = porId[l.id]; if (a) (porAlvo[a] = porAlvo[a] || []).push(l.id); });
    return {porId: porId, porAlvo: porAlvo};
  }

  function decisoes(fonte, rascunho) {
    var ef = efetiva(fonte, rascunho).porId, out = {};
    fonte.linhas.forEach(function (l) {
      var novo = ef[l.id];
      if (novo === l.alvo) return;
      if (novo) out[l.id] = novo;
      else if (l.modo === 'decidido') out[l.id] = '';
    });
    return out;
  }

  var api = {norm: norm, fontesPorChave: fontesPorChave, alvoDo: alvoDo, efetiva: efetiva, decisoes: decisoes};
  raiz.EqLigacao = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);

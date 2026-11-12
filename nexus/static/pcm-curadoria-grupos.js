/* O Tipo e as Classificações da peça nova na curadoria (12/11/2026, item 3 da 2ª rodada do Almoxarifado). As opções são as do
   Fracttal, com o id, e só a ponte do login dele as lê (o cookie os_sessao só chega a /os): a página pede uma vez
   (data-cu-classificacoes, o GET /os/_nexus/inventario/classificacoes) as opções e a sugestão de cada linha (data-cu-linha: a
   sugestão sai das peças do Fracttal, então também vem de lá) e enche as três seleções de cada cadastrar. A escolhida é a da
   reserva de uma tentativa anterior (data-reserva, data-res-<campo>: repetir com outros dados o servidor recusa) ou a sugerida
   (a chave que o servidor calculou contra a chave de cada opção), marcada "(sugerida)", como a sigla. O "Sugeridos" diz só o que
   a seleção mostra: a sugestão sem opção que case não aparece (a revisão, M2). Sem as opções (a ponte recusou ou o Fracttal não
   respondeu), as seleções seguem escondidas e desligadas (não vão no formulário) e a linha diz que o Tipo e a Classificação
   ficam para o Fracttal; com a reserva, que o cadastrar repete os dela (o servidor usa a reserva quando os campos não vêm). */
(function () {
  var fonte = document.querySelector("[data-cu-classificacoes]");
  var caixas = Array.prototype.slice.call(document.querySelectorAll("[data-cu-grupos]"));
  if (!fonte || !caixas.length) return;
  var ROTULO = {tipo: "Tipo", classificacao_1: "Classificação 1", classificacao_2: "Classificação 2"};

  function linhaSem(caixa) {
    return caixa.parentNode ? caixa.parentNode.querySelector("[data-cu-grupos-sem]") : null;
  }

  function dizer(texto, login) {
    caixas.forEach(function (caixa) {
      var p = linhaSem(caixa);
      if (!p) return;
      p.textContent = caixa.hasAttribute("data-reserva")
        ? "As opções do Fracttal não carregaram agora: o cadastrar repete o Tipo e a Classificação da tentativa anterior (a reserva)."
        : texto;
      if (typeof login === "string" && login) {      // o `login` do portão é um true, não um endereço
        p.appendChild(document.createTextNode(" "));
        var a = document.createElement("a");
        a.href = login;
        a.textContent = "Entrar pelo Fracttal";
        p.appendChild(a);
      }
      p.hidden = false;
    });
  }

  function escolhida(lista, caixa, campo, sug) {
    var i;
    if (caixa.hasAttribute("data-reserva")) {
      var res = caixa.getAttribute("data-res-" + campo) || "";
      for (i = 0; i < lista.length; i++) if (lista[i].id === res) return {opcao: lista[i], sugerida: false};
      return {opcao: null, sugerida: false};
    }
    var chave = sug && sug.chave;
    if (chave) for (i = 0; i < lista.length; i++) if (lista[i].chave === chave) return {opcao: lista[i], sugerida: true};
    return {opcao: null, sugerida: false};
  }

  function porQue(sug, tipo) {
    if (sug.por === "parecidas") return "pelas peças parecidas";
    if (sug.por === "tipo") return "a mais comum no Tipo " + tipo;
    if (sug.por === "boa") return "o da peça boa";
    return "";
  }

  function encher(opcoes, sugestoes) {
    caixas.forEach(function (caixa) {
      var sug = (sugestoes || {})[caixa.getAttribute("data-cu-linha")] || {};
      var campos = sug.campos || {}, mostradas = [];
      Array.prototype.forEach.call(caixa.querySelectorAll("select[data-campo]"), function (s) {
        var campo = s.getAttribute("data-campo"), lista = opcoes[campo] || [], e = escolhida(lista, caixa, campo, campos[campo]);
        lista.forEach(function (o) {
          var op = document.createElement("option");
          op.value = o.id;
          op.textContent = o.descricao + (o === e.opcao && e.sugerida ? " (sugerida)" : "");
          if (o === e.opcao) op.selected = true;
          s.appendChild(op);
        });
        if (e.sugerida) mostradas.push({campo: campo, texto: e.opcao.descricao, por: porQue(campos[campo], sug.tipo || "")});
        s.disabled = false;
      });
      var linha = caixa.querySelector("[data-cu-sugestao]");
      if (linha && mostradas.length) {
        while (linha.firstChild) linha.removeChild(linha.firstChild);
        linha.appendChild(document.createTextNode("Sugeridos"));
        mostradas.forEach(function (m, i) {
          linha.appendChild(document.createTextNode((i ? "; " : ": ") + ROTULO[m.campo] + " "));
          var b = document.createElement("b");
          b.textContent = m.texto;
          linha.appendChild(b);
          if (m.por) linha.appendChild(document.createTextNode(" (" + m.por + ")"));
        });
        linha.appendChild(document.createTextNode(". Troque, se for outro."));
      }
      caixa.hidden = false;
      var p = linhaSem(caixa);
      if (p) p.hidden = true;
    });
  }

  fetch(window.nexusRota(fonte.getAttribute("data-cu-classificacoes")), {
    credentials: "same-origin", headers: {"Accept": "application/json"}
  }).then(function (r) {
    return r.json().then(function (d) { return {r: r, d: d || {}}; }, function () { return {r: r, d: {}}; });
  }).then(function (x) {
    if (x.r.ok && x.d.ok && x.d.opcoes) { encher(x.d.opcoes, x.d.sugestoes); return; }
    dizer("O Tipo e a Classificação ficam para a tela do Fracttal." + (x.d.erro ? " " + x.d.erro : ""), x.d.login);
  }).catch(function () {
    dizer("O Tipo e a Classificação ficam para a tela do Fracttal: não consegui ler as opções agora.");
  });
})();

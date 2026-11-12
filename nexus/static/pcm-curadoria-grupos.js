/* O Tipo e as Classificações da peça nova na curadoria (12/11/2026, item 3 da 2ª rodada do Almoxarifado). As opções são as do
   Fracttal, com o id, e só a ponte do login dele as lê (o cookie os_sessao só chega a /os): a página pede uma vez
   (data-cu-classificacoes, o GET /os/_nexus/inventario/classificacoes) e enche as três seleções de cada cadastrar. A escolhida
   é a da reserva de uma tentativa anterior (data-reserva, data-res-<campo>: repetir com outros dados o servidor recusa) ou a
   sugerida (data-sug-<campo>: a chave que o servidor calculou, `classificacao.chave`, contra a chave de cada opção), marcada
   "(sugerida)", como a sigla. Sem as opções (a ponte recusou ou o Fracttal não respondeu), as seleções seguem escondidas e
   desligadas (não vão no formulário) e a linha diz que o Tipo e a Classificação ficam para o Fracttal. */
(function () {
  var fonte = document.querySelector("[data-cu-classificacoes]");
  var caixas = Array.prototype.slice.call(document.querySelectorAll("[data-cu-grupos]"));
  if (!fonte || !caixas.length) return;

  function linhaSem(caixa) {
    return caixa.parentNode ? caixa.parentNode.querySelector("[data-cu-grupos-sem]") : null;
  }

  function dizer(texto, login) {
    caixas.forEach(function (caixa) {
      var p = linhaSem(caixa);
      if (!p) return;
      p.textContent = texto;
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

  function escolhida(lista, caixa, campo) {
    var i;
    if (caixa.hasAttribute("data-reserva")) {
      var res = caixa.getAttribute("data-res-" + campo) || "";
      for (i = 0; i < lista.length; i++) if (lista[i].id === res) return {opcao: lista[i], sugerida: false};
      return {opcao: null, sugerida: false};
    }
    var sug = caixa.getAttribute("data-sug-" + campo) || "";
    if (sug) for (i = 0; i < lista.length; i++) if (lista[i].chave === sug) return {opcao: lista[i], sugerida: true};
    return {opcao: null, sugerida: false};
  }

  function encher(opcoes) {
    caixas.forEach(function (caixa) {
      Array.prototype.forEach.call(caixa.querySelectorAll("select[data-campo]"), function (s) {
        var campo = s.getAttribute("data-campo"), lista = opcoes[campo] || [], e = escolhida(lista, caixa, campo);
        lista.forEach(function (o) {
          var op = document.createElement("option");
          op.value = o.id;
          op.textContent = o.descricao + (o === e.opcao && e.sugerida ? " (sugerida)" : "");
          if (o === e.opcao) op.selected = true;
          s.appendChild(op);
        });
        s.disabled = false;
      });
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
    if (x.r.ok && x.d.ok && x.d.opcoes) { encher(x.d.opcoes); return; }
    dizer("O Tipo e a Classificação ficam para a tela do Fracttal." + (x.d.erro ? " " + x.d.erro : ""), x.d.login);
  }).catch(function () {
    dizer("O Tipo e a Classificação ficam para a tela do Fracttal: não consegui ler as opções agora.");
  });
})();

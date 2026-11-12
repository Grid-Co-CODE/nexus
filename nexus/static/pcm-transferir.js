/* Transferir peça entre almoxarifados do mesmo cliente (12/11/2026). Tudo o que depende do Fracttal mora na ponte do login dele
   (/os/_nexus/inventario/transferir: o cookie só chega em /os); os endereços vêm dos data-* do formulário, postos pela raiz, e
   passam pelo nexusRota. A ordem: a lista dos almoxarifados (lida no Fracttal), a origem traz as peças com saldo dela, o destino
   só lista os do mesmo cliente da origem; Conferir mostra o antes e o depois sem gravar, e só então o Transferir se abre. Mudar
   qualquer campo fecha o Transferir de novo (o que se confere é o que vai). O ok recarrega a página, que mostra o aviso e o
   histórico; o erro aparece no formulário, com o link do login quando falta. */
(function () {
  var form = document.querySelector("[data-tr-form]");
  if (!form) return;
  var origem = form.querySelector("#tr-origem"), item = form.querySelector("#tr-item");
  var destino = form.querySelector("#tr-destino"), qtd = form.querySelector("#tr-qtd"), ref = form.querySelector("#tr-ref");
  var plano = form.querySelector("[data-tr-plano]"), erro = form.querySelector("[data-tr-erro]");
  var nota = form.querySelector("[data-tr-qtd-nota]");
  var btnConferir = form.querySelector("[data-tr-btn-conferir]"), btnTransferir = form.querySelector("[data-tr-btn-transferir]");
  var almoxes = [], pecas = [], conferido = null;

  function rota(attr) { return window.nexusRota(form.getAttribute(attr)); }
  function chave(t) { return (t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\s+/g, " ").trim(); }
  function num(v) { return v === null || v === undefined ? "?" : String(Math.round(v * 100) / 100).replace(".", ","); }
  function json(r) {
    return r.json().then(function (d) { return {r: r, d: d || {}}; }, function () { return {r: r, d: {}}; });
  }

  function limpar(el) { while (el.firstChild) el.removeChild(el.firstChild); }
  function opcao(el, valor, texto, desligada) {
    var o = document.createElement("option");
    o.value = valor; o.textContent = texto;
    if (desligada) o.disabled = true;
    el.appendChild(o);
    return o;
  }

  function mostrarErro(texto, login) {
    limpar(erro);
    erro.appendChild(document.createTextNode(texto));
    if (typeof login === "string" && login) {
      erro.appendChild(document.createTextNode(" "));
      var a = document.createElement("a");
      a.href = login; a.textContent = "Entrar pelo Fracttal";
      erro.appendChild(a);
    }
    erro.hidden = false;
  }
  function semErro() { erro.hidden = true; limpar(erro); }

  function fechar() {                       // o que foi conferido não é mais o que está no formulário
    conferido = null;
    btnTransferir.disabled = true;
    plano.hidden = true;
    limpar(plano);
  }

  function pedir(url, corpo) {
    var op = {credentials: "same-origin", headers: {"Accept": "application/json"}};
    if (corpo) { op.method = "POST"; op.headers["Content-Type"] = "application/json"; op.body = JSON.stringify(corpo); }
    return fetch(url, op).then(json);
  }
  function falhou(x, padrao) {
    mostrarErro(x.d.erro || (padrao + " (HTTP " + x.r.status + ")."), x.d.sessao_encerrada ? x.d.entrar : x.d.login);
  }

  function preencherOrigem() {
    limpar(origem);
    opcao(origem, "", almoxes.length ? "Escolha a origem" : "Nenhum almoxarifado ativo no Fracttal");
    var grupos = {};
    almoxes.forEach(function (a) {          // um grupo por cliente, sem acento e sem caixa (como a regra os compara)
      var k = chave(a.cliente) || "~";
      if (!grupos[k]) {
        grupos[k] = document.createElement("optgroup");
        grupos[k].label = a.cliente || "Sem cliente no Fracttal (não transfere)";
        origem.appendChild(grupos[k]);
      }
      opcao(grupos[k], a.id, a.nome + (a.teste ? " (teste)" : ""), !a.cliente);
    });
    origem.disabled = !almoxes.length;
  }

  function preencherDestino() {
    limpar(destino);
    var o = almoxes.filter(function (a) { return a.id === origem.value; })[0];
    var ok = o ? almoxes.filter(function (a) { return a.id !== o.id && a.cliente && chave(a.cliente) === chave(o.cliente); }) : [];
    opcao(destino, "", !o ? "Escolha a origem antes" : ok.length ? "Escolha o destino" : "Nenhum outro almoxarifado deste cliente");
    ok.forEach(function (a) { opcao(destino, a.id, a.nome + (a.teste ? " (teste)" : "")); });
    destino.disabled = !ok.length;
  }

  function preencherPecas() {
    limpar(item);
    opcao(item, "", pecas.length ? "Escolha a peça" : "Nenhuma peça com saldo nesta origem");
    pecas.forEach(function (p) {
      opcao(item, p.id, p.codigo + (p.nome ? " · " + p.nome : "") + " (saldo " + num(p.saldo) + (p.unidade ? " " + p.unidade : "") + ")");
    });
    item.disabled = !pecas.length;
    notaDaQuantidade();
  }

  function notaDaQuantidade() {
    var p = pecas.filter(function (x) { return x.id === item.value; })[0];
    nota.textContent = p ? ("Até " + num(p.saldo) + (p.decimal ? ", com até duas casas" : ", inteira") + ".") : "";
  }

  function carregarPecas() {
    pecas = [];
    limpar(item);
    opcao(item, "", origem.value ? "Lendo as peças no Fracttal…" : "Escolha a origem antes");
    item.disabled = true;
    notaDaQuantidade();
    if (!origem.value) return;
    var de = origem.value;
    pedir(rota("data-tr-pecas") + "?origem=" + encodeURIComponent(de)).then(function (x) {
      if (origem.value !== de) return;              // a origem mudou no meio
      if (x.r.ok && x.d.ok) { pecas = x.d.pecas || []; preencherPecas(); return; }
      falhou(x, "Não consegui ler as peças da origem agora");
    }).catch(function () { mostrarErro("Não consegui falar com o Nexus agora: tente de novo em instantes."); });
  }

  function pedido() {
    return {origem: origem.value, destino: destino.value, item: item.value, qtd: qtd.value, referencia: ref.value};
  }

  function lado(rotulo, x) {
    var p = document.createElement("p");
    var b = document.createElement("b");
    b.textContent = rotulo + ": ";
    p.appendChild(b);
    p.appendChild(document.createTextNode(x.nome + ", de " + num(x.antes) + " para " + num(x.depois) + "."));
    return p;
  }

  function mostrarPlano(pl) {
    limpar(plano);
    var t = document.createElement("p");
    t.className = "tr-plano-tit";
    t.textContent = "O que vai acontecer: " + num(pl.qtd) + (pl.peca.unidade && pl.peca.unidade !== "unidade" ? " " + pl.peca.unidade : "") +
      " de " + pl.peca.codigo + (pl.peca.nome ? " (" + pl.peca.nome + ")" : "") + ".";
    plano.appendChild(t);
    plano.appendChild(lado("Origem", pl.origem));
    plano.appendChild(lado("Destino", pl.destino));
    if (pl.vincular) {
      var v = document.createElement("p");
      v.className = "rq-aviso";
      v.textContent = "A peça ainda não está vinculada ao destino: o Nexus a vincula antes, com mínimo e máximo 0.";
      plano.appendChild(v);
    }
    var nada = document.createElement("p");
    nada.className = "alm-det";
    nada.textContent = "Nada foi gravado ainda. Transferir grava no Fracttal com o seu login.";
    plano.appendChild(nada);
    plano.hidden = false;
  }

  form.addEventListener("submit", function (ev) {           // o Conferir
    ev.preventDefault();
    semErro();
    fechar();
    var c = pedido();
    if (!c.origem || !c.item || !c.destino || !c.qtd.trim()) { mostrarErro("Escolha a origem, a peça e o destino, e diga a quantidade."); return; }
    btnConferir.disabled = true;
    pedir(rota("data-tr-conferir"), c).then(function (x) {
      btnConferir.disabled = false;
      if (x.r.ok && x.d.ok) { conferido = JSON.stringify(c); mostrarPlano(x.d.plano); btnTransferir.disabled = false; return; }
      falhou(x, "Não consegui conferir agora");
    }).catch(function () { btnConferir.disabled = false; mostrarErro("Não consegui falar com o Nexus agora: tente de novo em instantes."); });
  });

  btnTransferir.addEventListener("click", function () {
    var c = pedido();
    if (!conferido || conferido !== JSON.stringify(c)) { fechar(); mostrarErro("Confira de novo: o formulário mudou."); return; }
    if (!window.confirm("Transferir no Fracttal, com o seu login? O Nexus relê os dois saldos antes e depois.")) return;
    semErro();
    btnTransferir.disabled = true; btnConferir.disabled = true;
    pedir(rota("data-tr-transferir"), c).then(function (x) {
      if (x.r.ok && x.d.ok) { window.location.assign(window.nexusRota(x.d.volta || window.location.pathname)); return; }
      btnConferir.disabled = false;
      fechar();
      falhou(x, "O Nexus não respondeu como esperado e a transferência pode ter sido feita: recarregue a página e confira antes de tentar de novo");
    }).catch(function () {
      btnConferir.disabled = false;
      mostrarErro("Não consegui falar com o Nexus agora, e o pedido pode ter chegado: recarregue a página e confira as últimas transferências antes de tentar de novo.");
    });
  });

  origem.addEventListener("change", function () { semErro(); fechar(); preencherDestino(); carregarPecas(); });
  item.addEventListener("change", function () { fechar(); notaDaQuantidade(); });
  [destino, qtd, ref].forEach(function (el) { el.addEventListener("input", fechar); el.addEventListener("change", fechar); });

  pedir(rota("data-tr-almox")).then(function (x) {
    if (x.r.ok && x.d.ok) { almoxes = x.d.almoxarifados || []; preencherOrigem(); return; }
    limpar(origem); opcao(origem, "", "Os almoxarifados não foram lidos");
    falhou(x, "Não consegui ler os almoxarifados no Fracttal agora");
  }).catch(function () { mostrarErro("Não consegui falar com o Nexus agora: tente de novo em instantes."); });
})();

// O card do Modo cliente (07/11/2026, Levi: "aparecer um card na frente dando um blur de fundo pedindo para escolher o
// cliente"), só para administradores: o <dialog> vazio mora no base.html com o endereço da lista, o da escolha e o
// código do formulário; o formulário nasce aqui ao abrir, para o texto das páginas não levar formulário nenhum (as telas
// que conferem os formulários delas, como o "abrir e salvar sem mexer" do Cadastro). A lista vem do cadastro ao abrir.
(function () {
  var card = document.getElementById("modo-cliente-card");
  if (!card || !card.showModal) return;
  var escolha, erro, lido = false;
  function montar() {
    if (escolha) return;
    // o formulário nasce pelo DOM: o texto da página não leva formulário nem campo (as telas que conferem os delas)
    var f = document.createElement("form");
    f.method = "post";
    f.action = card.getAttribute("data-acao");
    f.innerHTML = '<p class="gc-eyebrow">Administradores</p><h2 id="modo-cliente-titulo">Modo cliente</h2>'
      + '<p class="mudo">Veja o Nexus como o cliente escolhido vê: só as telas liberadas para Clientes, com as usinas dele.</p>'
      + '<label class="gc-rotulo" for="modo-cliente-escolha">Cliente</label>'
      + '<select id="modo-cliente-escolha" class="gc-campo" required><option value="">Carregando…</option></select>'
      + '<p class="gc-ajuda gc-ajuda--erro" data-erro hidden></p>'
      + '<div class="modo-cliente-botoes"><button type="button" class="gc-btn gc-btn--ui gc-btn--contorno" data-fecha>Cancelar</button>'
      + '<button type="submit" class="gc-btn gc-btn--ui gc-btn--primario"><i class="ph ph-eye" aria-hidden="true"></i> Ver como este cliente</button></div>';
    var cod = document.createElement("input");
    cod.type = "hidden"; cod.name = "codigo"; cod.value = card.getAttribute("data-codigo");
    f.insertBefore(cod, f.firstChild);
    card.appendChild(f);
    escolha = card.querySelector("select"); escolha.name = "cliente_id";
    erro = card.querySelector("[data-erro]");
    card.querySelector("[data-fecha]").addEventListener("click", function () { card.close(); });
  }
  function carregar() {
    if (lido) return;
    fetch(card.getAttribute("data-lista"), {credentials: "same-origin", headers: {Accept: "application/json"}})
      .then(function (r) { return r.json(); })
      .then(function (d) {
        lido = d.ok;
        escolha.innerHTML = '<option value="">Escolha o cliente</option>';
        (d.clientes || []).forEach(function (c) {
          var o = document.createElement("option");
          o.value = c.id;
          o.textContent = c.nome + " (" + c.usinas + (c.usinas === 1 ? " usina)" : " usinas)");
          escolha.appendChild(o);
        });
        erro.hidden = !d.erro; erro.textContent = d.erro || "";
      })
      .catch(function () { erro.hidden = false; erro.textContent = "Não consegui carregar os clientes. Tente de novo."; });
  }
  document.querySelectorAll("[data-abre-modo-cliente]").forEach(function (b) {
    b.addEventListener("click", function () {
      var conta = b.closest("details"); if (conta) conta.open = false;
      montar(); card.showModal(); carregar(); escolha.focus();
    });
  });
  card.addEventListener("click", function (ev) { if (ev.target === card) card.close(); });
})();

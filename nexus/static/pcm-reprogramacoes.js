/* As reprogramações da semana em curso no Quadro (19/10/2026; o programador do PCM: "eu não achei isso da
   reprogramação", "ainda tá meio que fantasma pra mim, sem poder editar").

   O bloco #reprogramacoes fica no fim do Quadro e vem do servidor depois da página (data-rp-url: ler o arquivo no
   GitHub não atrasa o Quadro). Aqui: buscar o bloco, abrir e rolar até ele pelo botão do topo, marcar a linha editada
   e a tirada, incluir linha nova e dizer o que muda antes de gravar. Quem confere a linha é o servidor
   (`quadro.problemas_das_linhas`). `resumo` é pura, para o teste no node. */
(function (raiz) {
  "use strict";

  function resumo(n) {
    var partes = [];
    function p(q, um, varios) { if (q) partes.push(q + " " + (q === 1 ? um : varios)); }
    p(n.editadas, "editada", "editadas");
    p(n.tiradas, "tirada", "tiradas");
    p(n.novas, "nova", "novas");
    return partes.length ? partes.join(" · ") + ": grave para valer" : "";
  }
  raiz.ReprogramacoesTela = { resumo: resumo };
  if (typeof document === "undefined") return;

  var bloco = document.getElementById("reprogramacoes");
  if (!bloco) return;
  var corpoBloco = bloco.querySelector("[data-rp-bloco]");

  function iniciar() {
    var form = bloco.querySelector("[data-rp-form]");
    if (!form || form.dataset.rpPronto) return;
    form.dataset.rpPronto = "1";
    var corpo = form.querySelector("[data-rp-corpo]"), campoN = form.querySelector("[data-rp-n]"),
        saida = form.querySelector("[data-rp-resumo]"), modelo = form.querySelector("template[data-rp-modelo]");

    function atualizar() {
      var n = { editadas: 0, tiradas: 0, novas: 0 };
      corpo.querySelectorAll("tr[data-rp-linha]").forEach(function (tr) {
        var c = tr.querySelector(".rp-campo"), x = tr.querySelector("input[type=checkbox]");
        var nova = tr.classList.contains("rp-nova"), tirada = !!(x && x.checked);
        var editada = !nova && !!c && c.value.trim() !== (c.getAttribute("data-original") || "");
        tr.classList.toggle("rp-tirada", tirada);
        tr.classList.toggle("rp-editada", editada && !tirada);
        if (tirada) n.tiradas++;
        else if (nova) { if (c && c.value.trim()) n.novas++; }
        else if (editada) n.editadas++;
      });
      if (saida) saida.textContent = resumo(n);
    }
    form.addEventListener("input", atualizar);
    form.addEventListener("change", atualizar);

    var incluir = form.querySelector("[data-rp-incluir]");
    if (incluir && modelo) incluir.addEventListener("click", function () {
      var i = parseInt(campoN.value, 10) || 0;
      var tr = modelo.content.firstElementChild.cloneNode(true);
      var c = tr.querySelector(".rp-campo");
      c.name = "l" + i;
      campoN.value = String(i + 1);
      var vazio = corpo.querySelector("[data-rp-vazio]");
      if (vazio) vazio.remove();
      corpo.appendChild(tr);
      c.focus();
      atualizar();
    });
    corpo.addEventListener("click", function (ev) {
      var b = ev.target.closest("[data-rp-desfaz]");
      if (!b) return;
      b.closest("tr").remove();          // o índice que ficou vago o servidor pula
      atualizar();
    });
    atualizar();
  }

  function carregar() {
    if (bloco.dataset.rpCarregado) { iniciar(); return; }
    bloco.dataset.rpCarregado = "1";
    fetch(bloco.getAttribute("data-rp-url"), { credentials: "same-origin", headers: { Accept: "text/html" } })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.text();
      })
      .then(function (html) {
        corpoBloco.innerHTML = html;
        iniciar();
        // o bloco cresceu depois da rolagem do endereço (#reprogramacoes): volta ao começo dele
        if (location.hash === "#reprogramacoes") bloco.scrollIntoView({ block: "start" });
      })
      .catch(function () {
        delete bloco.dataset.rpCarregado;
        corpoBloco.innerHTML = "";
        var p = document.createElement("p");
        p.className = "rp-falha";
        p.textContent = "Não consegui abrir o arquivo da semana em curso agora. Feche e abra este bloco para tentar de novo.";
        corpoBloco.appendChild(p);
      });
  }

  function irAoBloco() {
    bloco.open = true;
    carregar();
    bloco.scrollIntoView({ block: "start" });
  }
  bloco.addEventListener("toggle", function () { if (bloco.open) carregar(); });
  document.querySelectorAll("[data-rp-abrir]").forEach(function (a) {
    a.addEventListener("click", function (ev) { ev.preventDefault(); irAoBloco(); });
  });
  // a gravação barrada volta com o bloco montado (data-rp-ir): a pessoa vê na hora o que arrumar
  if (location.hash === "#reprogramacoes" || bloco.dataset.rpIr) irAoBloco();
  else if (bloco.open) carregar();
})(typeof window !== "undefined" ? window : globalThis);

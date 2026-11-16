/* os_creator/os_web/static/solic_ia.js — o Pedir com IA (15/11/2026): a caixa de texto da Nova solicitação. A pessoa
   escreve a OS; o servidor pede à IA, confere no catálogo e devolve a ficha (`/os/api/solic/ia/preencher`), e quem preenche
   é a própria tela, pelo `window.SolicForm` dela (Levi, 15/11/2026: "tudo é preenchido dentro da tela original mesmo e caso
   a pessoa precise adicionar algo ela pode pedir novamente alguma mudança"). O pedido seguinte leva o que está na tela
   agora (o que a pessoa mexeu à mão vale), e o Limpar tira tudo ("crie um botão Limpar para tirar tudo o que foi posto").
   Contrato do SolicForm: estado() → {cliente, usina, tipo, ativo, titulo, descricao, tema, classif1, subtarefas};
   preencher(ficha) → Promise; limpar() → Promise. */
(function () {
  "use strict";
  var barra = document.getElementById("sia"), tela = window.SolicForm;
  if (!barra || !tela) return;
  var form = document.getElementById("sia_form"), txt = document.getElementById("sia_txt"),
      btnEnviar = document.getElementById("sia_enviar"), btnLimpar = document.getElementById("sia_limpar"),
      linha = document.getElementById("sia_msg"), caixaPerg = document.getElementById("sia_perguntas");
  var setor = barra.getAttribute("data-setor"), dicaInicial = linha.innerHTML, placeInicial = txt.placeholder;
  var preenchida = false, ocupado = false;

  function esc(t) { return String(t == null ? "" : t).replace(/[&<>"]/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]; }); }
  function dizer(html) { linha.innerHTML = html; }

  // ── abrir e fechar: o botão "Pedir com IA" do alto; o cartão do Início chega com ?ia=1 ──
  var botoes = document.querySelectorAll("[data-sia-abrir]");
  function abrir(sim) {
    barra.hidden = !sim;
    botoes.forEach(function (b) { b.setAttribute("aria-expanded", sim ? "true" : "false"); b.classList.toggle("on", sim); });
    if (sim) { txt.focus(); barra.scrollIntoView({block: "nearest"}); }
  }
  botoes.forEach(function (b) {
    b.setAttribute("aria-controls", "sia");
    b.addEventListener("click", function () { abrir(barra.hidden); });
  });

  // ── a caixa de texto: Enter envia, Shift+Enter quebra a linha ──
  function ajustar() { txt.style.height = "auto"; txt.style.height = Math.min(txt.scrollHeight, 160) + "px"; }
  txt.addEventListener("input", ajustar);
  txt.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); enviar(); }
  });
  form.addEventListener("submit", function (e) { e.preventDefault(); enviar(); });

  function nomeModelo(info) {
    if (!info || !info.modelo) return "";
    return info.modelo.split("/").pop().replace(/:free$/, "")
      + (info.segundos != null ? " · " + String(info.segundos).replace(".", ",") + " s" : "");
  }
  function resumo(f) {
    var partes = [];
    // a usina pelo nome dela (sem o cliente e o estado); sem a usina, o cliente que achou
    if (f.usina) partes.push(esc(f.usina_curta || f.usina)); else if (f.cliente) partes.push(esc(f.cliente));
    if (f.ativo) partes.push("<b>" + esc(f.ativo.curto || f.ativo.label || f.ativo.code) + "</b>");
    if (f.responsavel_escolhido) partes.push("para " + esc(f.responsavel_escolhido.name));
    if (f.evento_br) partes.push("evento " + esc(f.evento_br));
    if (f.com_subtarefas) {                                         // só a tela do PCM tem o tema e as subtarefas
      partes.push(f.tema ? "tema " + esc(f.tema_nome) : "sem tema");
      var naTela = (tela.estado().subtarefas || []).length;        // o que a tela tem agora (a pessoa pode ter tirado alguma)
      var novas = (f.subtarefas || []).filter(function (s) { return s.da_ia; }).length;
      partes.push(naTela + " subtarefa(s) na tela" + (novas ? ", " + novas + " do pedido" : ""));
    }
    return partes.join(" · ");
  }

  // ── o que falta: uma pergunta por linha, a resposta ao lado; Tab passa para a próxima, Enter envia todas (Levi,
  //    15/11/2026: "pode quebrar o texto, aí a pessoa pode responder ao lado da pergunta, apertando tab para passar a linha").
  //    O que vem depois do "?" ("Sem resposta, fica o horário de agora.") vira a dica dentro do campo. ──
  function respostasCampos() { return caixaPerg ? caixaPerg.querySelectorAll(".sia-r") : []; }
  function mostrarPerguntas(lista) {
    if (!caixaPerg) return;
    caixaPerg.innerHTML = "";
    caixaPerg.hidden = !lista.length;
    if (!lista.length) return;
    var tit = document.createElement("div");
    tit.className = "sia-falta"; tit.textContent = "Falta:";
    caixaPerg.appendChild(tit);
    lista.forEach(function (p, i) {
      var q = String(p), corte = q.indexOf("?") + 1, rotulo = corte > 0 ? q.slice(0, corte) : q, resto = corte > 0 ? q.slice(corte).trim() : "";
      // cara de prompt (Levi: "deixe mais bonito! porém estilo CMD"): "? Pergunta  › resposta", sem linha embaixo
      var lb = document.createElement("label"), inp = document.createElement("input"), campo = document.createElement("span"),
          seta = document.createElement("span");
      lb.className = "sia-q"; lb.htmlFor = "sia_r" + i; lb.textContent = rotulo;
      inp.type = "text"; inp.id = "sia_r" + i; inp.className = "sia-r"; inp.maxLength = 200; inp.autocomplete = "off";
      inp.placeholder = resto || "sua resposta"; inp.setAttribute("data-pergunta", rotulo);
      inp.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && !e.isComposing) { e.preventDefault(); enviar(); }
      });
      campo.className = "sia-campo"; seta.className = "sia-seta"; seta.textContent = "›"; seta.setAttribute("aria-hidden", "true");
      campo.appendChild(seta); campo.appendChild(inp);
      caixaPerg.appendChild(lb); caixaPerg.appendChild(campo);
    });
    var dica = document.createElement("div");
    dica.className = "sia-dica sia-dica-r"; dica.textContent = "Responda ao lado: Tab passa para a próxima, Enter envia. Ou escolha na tela.";
    caixaPerg.appendChild(dica);
  }
  // cada resposta vai com a pergunta dela, numa linha: a IA lê "Quem é o responsável? Fulano"
  function respostas() {
    return Array.prototype.map.call(respostasCampos(), function (c) {
      return c.value.trim() ? c.getAttribute("data-pergunta") + " " + c.value.trim() : "";
    }).filter(Boolean);
  }
  function travar(sim) { Array.prototype.forEach.call(respostasCampos(), function (c) { c.disabled = sim; }); }

  function fim() {
    ocupado = false; btnEnviar.disabled = false; btnLimpar.disabled = false; travar(false);
    var primeira = respostasCampos()[0];                          // com pergunta, o cursor já vai para a 1ª resposta
    (primeira || txt).focus();
  }
  function enviar() {
    var t = [txt.value.trim()].concat(respostas()).filter(Boolean).join("\n");
    if (!t || ocupado) return;
    ocupado = true; btnEnviar.disabled = true; btnLimpar.disabled = true; travar(true);
    var t0 = Date.now();
    // quem demora é a IA, não o catálogo (que já está na memória do Nexus): a frase diz isso (Levi achou que era o catálogo)
    dizer('<span class="sia-pensando">a IA está escrevendo a OS<span class="sia-seg"></span><span class="sia-cursor"></span></span>');
    // os segundos correndo: a IA grátis às vezes demora, e a pessoa vê que o pedido está vivo (Levi: "demorando que só")
    var relogio = setInterval(function () {
      var n = Math.round((Date.now() - t0) / 1000), s = linha.querySelector(".sia-seg");
      if (s && n >= 3) s.textContent = " · " + n + " s";
    }, 1000);
    // o 2º pedido em diante leva o que está na tela agora: a IA muda só o que a pessoa pediu
    var corpo = {setor: setor, texto: t, anterior: preenchida ? tela.estado() : null};
    fetch("/os/api/solic/ia/preencher", {method: "POST", credentials: "same-origin",
                                         headers: {"Content-Type": "application/json"}, body: JSON.stringify(corpo)})
      .then(function (r) {
        return r.json().catch(function () { return {erro: "Resposta que não deu para ler (" + r.status + ")."}; })
          .then(function (j) { if (r.status === 401 || j.login) j.erro = j.erro || "Sua sessão do Fracttal caiu: entre de novo."; return {ok: r.ok, j: j}; });
      })
      .catch(function () { return {ok: false, j: {erro: "Sem conexão com o servidor."}}; })
      .then(function (x) {
        clearInterval(relogio);
        if (!x.ok || x.j.erro) { fim(); dizer('<span class="sia-erro">' + esc(x.j.erro || "Não deu certo.") + "</span>"); return; }
        var f = x.j;
        dizer('<span class="sia-pensando">preenchendo a tela<span class="sia-cursor"></span></span>');
        return Promise.resolve(tela.preencher(f)).then(function () {
          preenchida = true; txt.value = ""; ajustar();
          txt.placeholder = "Peça uma mudança: “troque para o inversor 2.2”, “título mais curto”…";
          var m = nomeModelo(f.ia_info);
          // o que o pedido disse e o catálogo não tem vem antes de tudo (Levi: "poderia ter um aviso ativo x não encontrado")
          var falta = (f.avisos || []).map(function (a) { return '<span class="sia-erro">' + esc(a) + "</span> "; }).join("");
          mostrarPerguntas(f.perguntas || []);
          var tk = (f.ia_info && f.ia_info.tokens) || {};
          var dica = tk.entrada != null ? ' title="tokens: ' + tk.entrada + ' de entrada, ' + tk.saida + ' de saída'
            + (tk.raciocinio ? ", " + tk.raciocinio + " de raciocínio" : "") + '"' : "";
          dizer(falta + '<span class="' + (f.pronta ? "sia-ok" : "sia-dica") + '">' + (f.pronta ? "Preenchi: " : "Preenchi o que achei: ")
                + resumo(f) + ". Confira e crie.</span>" + (m ? ' <span class="sia-modelo"' + dica + ">" + esc(m) + "</span>" : ""));
          fim();
        }, function (e) { fim(); dizer('<span class="sia-erro">Não consegui preencher a tela: ' + esc((e && e.message) || e) + "</span>"); });
      });
  }

  btnLimpar.addEventListener("click", function () {
    if (ocupado) return;
    Promise.resolve(tela.limpar()).then(function () {
      preenchida = false; txt.value = ""; ajustar(); txt.placeholder = placeInicial; mostrarPerguntas([]);
      linha.innerHTML = dicaInicial; txt.focus();
    });
  });

  if (new URLSearchParams(location.search).get("ia") === "1") abrir(true);
})();

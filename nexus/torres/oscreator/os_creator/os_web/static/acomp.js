/* os_creator/os_web/static/acomp.js — o quadro do Acompanhamento de chamados (filtros locais) e a tela do chamado
   (copiar, esconder as respostas, ticket, observação, finalizar). Toda escrita vai por POST em /os/api/acomp/<nº>/…; o servidor confere o nº
   da OS contra o id antes de gravar. */
(function () {
  "use strict";

  // A tela que abriu com a leitura anterior (vencida, ou a de ontem na 1ª abertura do dia) troca sozinha quando a nova
  // chega (24/10/2026): pergunta de 5 em 5 s, por até 3 min, e recarrega quando a hora da cópia muda. Se a releitura
  // terminar sem cópia nova (o Fracttal falhou), fica a que está, com a hora dela.
  (function esperarANova() {
    const f = document.querySelector(".ac-fonte[data-renovando]");
    if (!f) return;
    const antes = f.getAttribute("data-quando") || "";
    let vezes = 0;
    const t = setInterval(async () => {
      vezes += 1;
      try {
        const r = await fetch("/os/chamados/acompanhamento/estado", {headers: {"X-Requested-With": "fetch"}});
        const j = r.ok ? await r.json() : {};
        if (j.quando && j.quando !== antes) { clearInterval(t); location.reload(); return; }
        if (j.renovando === false || vezes >= 36) clearInterval(t);
      } catch (e) {
        if (vezes >= 36) clearInterval(t);
      }
    }, 5000);
  })();

  function norm(s) {
    return String(s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\s+/g, " ").trim();
  }

  async function postar(url, corpo) {
    const r = await OsCarga.buscar(url, {method: "POST", headers: {"Content-Type": "application/json", "X-Requested-With": "fetch"},
                                body: JSON.stringify(corpo || {})}, "Gravando…");
    let j = {};
    try { j = await r.json(); } catch (e) { j = {}; }
    if (r.status === 401 && j.login) {
      location.href = "/os/login?next=" + encodeURIComponent(location.pathname + location.search);
      throw new Error("sessão");
    }
    if (!r.ok || j.erro) throw new Error(j.erro || ("HTTP " + r.status));
    return j;
  }

  function contar(el, n) {
    if (el) el.textContent = String(n);
  }

  function msg(el, texto, tipo) {
    if (!el) return;
    el.textContent = texto || "";
    el.className = "msg" + (tipo ? " " + tipo : "");
  }

  // ── o quadro: os filtros escondem cards, e cada coluna recontra e mostra o "vazio" quando zera ──
  const quadro = document.getElementById("acomp");
  if (quadro) {
    // 6 cartões à vista em cada coluna (Levi, 20/10/2026: "aumente o tamanho em acompanhamento de chamados para mostrar 6
    // usinas nas colunas kanban"): a coluna vai até o fim do 6º cartão visível, MEDIDO (o cartão cresce com o título longo
    // e as etiquetas, e a largura muda a quebra); com até 6, sem teto. No celular a coluna não tem teto (chamados.css).
    const CARTOES_A_VISTA = 6;
    const medir = function () {
      quadro.querySelectorAll(".cards").forEach(function (box) {
        const vis = Array.prototype.filter.call(box.querySelectorAll(".card"), function (c) { return !c.classList.contains("oculto"); });
        if (vis.length <= CARTOES_A_VISTA) { box.style.setProperty("--cards-max", "none"); return; }
        const fim = vis[CARTOES_A_VISTA - 1].getBoundingClientRect().bottom - box.getBoundingClientRect().top + box.scrollTop;
        box.style.setProperty("--cards-max", Math.ceil(fim + (parseFloat(getComputedStyle(box).paddingBottom) || 0)) + "px");
      });
    };
    let quadroPedido = 0;
    const remedir = function () { if (!quadroPedido) quadroPedido = requestAnimationFrame(function () { quadroPedido = 0; medir(); }); };
    medir();
    window.addEventListener("resize", remedir);
    window.addEventListener("load", remedir);                             // a fonte Inter chega e muda a altura
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(remedir);
    const campos = quadro.querySelectorAll("[data-f]");
    const aplicar = function () {
      const f = {};
      campos.forEach(function (c) { f[c.dataset.f] = c.dataset.f === "busca" ? norm(c.value) : c.value; });
      quadro.querySelectorAll(".col").forEach(function (col) {
        let n = 0;
        col.querySelectorAll(".card").forEach(function (card) {
          const d = card.dataset;
          const ok = (!f.marca || d.marca === f.marca) && (!f.cliente || d.cliente === f.cliente) &&
                     (!f.tipo || d.tipo === f.tipo) && (!f.equipe || d.equipe === f.equipe) &&
                     (!f.busca || (d.busca || "").indexOf(f.busca) >= 0);
          card.classList.toggle("oculto", !ok);
          if (ok) n++;
        });
        contar(col.querySelector("[data-n]"), n);
        const vazio = col.querySelector("[data-vazio]");
        if (vazio) vazio.classList.toggle("oculto", n > 0);
      });
      medir();                                                            // o filtro muda quais são os 6 primeiros
    };
    campos.forEach(function (c) { c.addEventListener(c.tagName === "INPUT" ? "input" : "change", aplicar); });
    const limpar = quadro.querySelector("[data-limpar]");
    if (limpar) limpar.addEventListener("click", function () {
      campos.forEach(function (c) { c.value = ""; });
      aplicar();
    });
    // o chamado começa a ser lido quando o mouse PARA em cima do cartão (Levi, 09/10/2026): o clique pega a leitura
    // pronta (rotas_acomp.preparar_chamado, com o teto por pessoa do rotas.preparar). Uma vez por cartão; 250 ms parado,
    // para o mouse que só atravessa o quadro não pedir nada
    quadro.querySelectorAll("a.card[href]").forEach(function (card) {
      let t = null, feito = false;
      const preparar = function () {
        t = null;
        if (feito || !window.fetch) return;
        feito = true;
        fetch(card.getAttribute("href") + "/preparar", {credentials: "same-origin", cache: "no-store"}).catch(function () {});
      };
      const parar = function () { if (t) { clearTimeout(t); t = null; } };
      const esperar = function () { parar(); t = setTimeout(preparar, 250); };
      card.addEventListener("mouseenter", esperar);
      card.addEventListener("focus", esperar);
      card.addEventListener("mouseleave", parar);
      card.addEventListener("blur", parar);
      card.addEventListener("touchstart", preparar, {passive: true});
    });
  }

  // ── a tela do chamado ──
  const tela = document.getElementById("acomp-os");
  if (!tela) return;
  const folio = tela.dataset.folio, wid = tela.dataset.wid, ativo = tela.dataset.ativo;

  // os blocos que recolhem até sobrar o cabeçalho (Levi, 27/09: "dê para reduzir essa parte, com um botão esconde e deixa
  // só o título"). A escolha fica NESTE navegador: quem esconde os campos abre o próximo chamado com eles escondidos. O
  // estado salvo já foi aplicado antes da 1ª pintura pelo <script> curto do acomp_os.html — a chave é a mesma.
  tela.querySelectorAll("[data-recolhe]").forEach(function (bloco) {
    const b = bloco.querySelector("[data-recolher]");
    if (!b) return;
    b.addEventListener("click", function () {
      const esconder = !bloco.classList.contains("recolhido");
      bloco.classList.toggle("recolhido", esconder);
      b.setAttribute("aria-expanded", esconder ? "false" : "true");
      try { localStorage.setItem("acomp.recolhe." + bloco.dataset.recolhe, esconder ? "1" : "0"); } catch (e) { /* aba anônima: vale só agora */ }
    });
  });

  tela.addEventListener("click", function (ev) {
    const b = ev.target.closest("[data-copia]");
    if (!b) return;
    const texto = b.dataset.copia || "";
    const volta = b.textContent;
    const feito = function () { b.textContent = "Copiado"; setTimeout(function () { b.textContent = volta; }, 1200); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(texto).then(feito, function () { b.textContent = "Não copiou"; });
    } else {
      const t = document.createElement("textarea");
      t.value = texto; document.body.appendChild(t); t.select();
      try { document.execCommand("copy"); feito(); } catch (e) { b.textContent = "Não copiou"; }
      t.remove();
    }
  });

  const bTicket = document.getElementById("b_ticket");
  if (bTicket) {
    bTicket.addEventListener("click", async function () {
      const campo = document.getElementById("ticket"), m = document.getElementById("msg_ticket");
      const valor = (campo.value || "").trim();
      if (!valor) { msg(m, "Escreva o nº do ticket ou do protocolo.", "er"); campo.focus(); return; }
      bTicket.disabled = true; msg(m, "Gravando no Fracttal…");
      try {
        const j = await postar("/os/api/acomp/" + folio + "/ticket", {ticket: valor, wid: wid});
        msg(m, (j.mensagem || "Ticket gravado.") + (j.aviso ? " " + j.aviso : ""), j.aviso ? "av" : "ok");
        setTimeout(function () { location.reload(); }, j.aviso ? 2600 : 700);
      } catch (e) {
        if (e.message !== "sessão") msg(m, "Não gravou: " + e.message, "er");
        bTicket.disabled = false;
      }
    });
  }

  const bObs = document.getElementById("b_obs");
  if (bObs) {
    bObs.addEventListener("click", async function () {
      const campo = document.getElementById("obs"), m = document.getElementById("msg_obs");
      const texto = (campo.value || "").trim();
      if (!texto) { msg(m, "Escreva a observação antes de salvar.", "er"); campo.focus(); return; }
      bObs.disabled = true; msg(m, "Salvando…");
      try {
        const j = await postar("/os/api/acomp/" + folio + "/obs", {texto: texto, ativo: ativo});
        const e = j.entrada || {};
        const tl = document.getElementById("tl");
        tl.querySelectorAll(".tl-e.novo").forEach(function (x) { x.classList.remove("novo"); });
        const div = document.createElement("div");
        div.className = "tl-e novo";
        div.innerHTML = '<div class="tl-g"><div class="tl-d"></div><div class="tl-a"></div></div>' +
                        '<div class="tl-b"><div class="tl-x"><div class="tl-t"></div><div class="tl-u"></div></div></div>';
        div.querySelector(".tl-d").textContent = e.d || "";
        div.querySelector(".tl-a").textContent = e.a || "";
        div.querySelector(".tl-t").textContent = e.texto || texto;
        div.querySelector(".tl-u").textContent = e.autor || "";
        tl.insertBefore(div, tl.firstChild);
        contar(document.getElementById("n_obs"), tl.querySelectorAll(".tl-e").length);
        campo.value = "";
        msg(m, "Salvo.", "ok");
      } catch (e) {
        if (e.message !== "sessão") msg(m, "Não salvou: " + e.message, "er");
      }
      bObs.disabled = false;
    });
  }

  const bFim = document.getElementById("b_finalizar"), conf = document.getElementById("conf_fim");
  if (bFim && conf) {
    bFim.addEventListener("click", function () { conf.classList.remove("oculto"); document.getElementById("b_fim_sim").focus(); });
    document.getElementById("b_fim_nao").addEventListener("click", function () { conf.classList.add("oculto"); });
    document.getElementById("b_fim_sim").addEventListener("click", async function () {
      const sim = this, m = document.getElementById("msg_fim");
      sim.disabled = true; msg(m, "Concluindo a OS no Fracttal…");
      try {
        const j = await postar("/os/api/acomp/" + folio + "/finalizar", {wid: wid});
        const aviso = [j.aviso || "", j.aviso_obs || ""].filter(Boolean).join(" ");
        msg(m, (j.mensagem || "Chamado finalizado.") + (aviso ? " " + aviso : ""), aviso ? "av" : "ok");
        setTimeout(function () { location.reload(); }, aviso ? 3200 : 900);
      } catch (e) {
        if (e.message !== "sessão") msg(m, "Não finalizou: " + e.message, "er");
        sim.disabled = false;
      }
    });
  }
})();

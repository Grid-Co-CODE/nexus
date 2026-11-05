/* os_creator/os_web/static/acomp.js — o quadro do Acompanhamento de chamados (filtros locais) e a tela do chamado
   (copiar, esconder as respostas, ticket, observação, finalizar). Toda escrita vai por POST em /os/api/acomp/<nº>/…; o servidor confere o nº
   da OS contra o id antes de gravar. */
(function () {
  "use strict";

  // A tela que abriu com a leitura anterior (vencida, ou a de ontem na 1ª abertura do dia) troca sozinha quando a nova
  // chega (24/10/2026): pergunta de 5 em 5 s, por até 3 min, e recarrega quando a hora da cópia muda. Se a releitura
  // terminar sem cópia nova (o Fracttal falhou), fica a que está, com a hora dela.
  // O X-Nexus-Auto diz ao servidor que é a tela perguntando sozinha, e não a pessoa clicando: o uso das telas
  // (casca/uso_os.py, 31/10/2026) conta os dois à parte.
  (function esperarANova() {
    const f = document.querySelector(".ac-fonte[data-renovando]");
    if (!f) return;
    const antes = f.getAttribute("data-quando") || "";
    let vezes = 0;
    const t = setInterval(async () => {
      vezes += 1;
      try {
        const r = await fetch("/os/chamados/acompanhamento/estado", {headers: {"X-Requested-With": "fetch", "X-Nexus-Auto": "1"}});
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

  // um arquivo do servidor (o relatório em PDF, a tabela em Excel): POST com o círculo de carga, e o download pelo
  // nome que o servidor deu
  async function baixar(url, corpo, padrao) {
    const r = await OsCarga.buscar(url, {method: "POST", headers: {"Content-Type": "application/json", "X-Requested-With": "fetch"},
                                body: JSON.stringify(corpo || {})}, "Montando…");
    if (r.status === 401) {
      location.href = "/os/login?next=" + encodeURIComponent(location.pathname + location.search);
      throw new Error("sessão");
    }
    if (!r.ok) {
      let j = {};
      try { j = await r.json(); } catch (e) { j = {}; }
      throw new Error(j.erro || ("HTTP " + r.status));
    }
    const blob = await r.blob();
    const cd = r.headers.get("Content-Disposition") || "";
    const m = /filename\*=UTF-8''([^;]+)/i.exec(cd) || /filename="?([^";]+)"?/i.exec(cd);
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = m ? decodeURIComponent(m[1]) : padrao;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 4000);
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
        if (box.offsetParent === null) return;                            // escondida (a vista em tabela): mede ao voltar
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
    // o filtro e a rolagem ficam ao abrir um chamado e voltar (Levi, 24/10/2026: "Quando eu faço um filtro em garantias >
    // acompanhamento de chamados e clico na os, ao voltar para o acompanhamento o filtro se desfaz e carrega novamente,
    // quero que mantenha o filtro anterior!"): guardados NESTA aba do navegador, valem na volta, no Atualizar e quando a
    // tela troca sozinha (esperarANova). Valor que saiu da lista (a marca sem chamado aberto) não vira filtro.
    const CHAVE_FILTRO = "acomp.filtros", CHAVE_ROLAGEM = "acomp.rolagem";
    const lerGuardado = function (k) { try { return JSON.parse(sessionStorage.getItem(k) || "null"); } catch (e) { return null; } };
    const guardar = function (k, v) { try { sessionStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* aba anônima: vale só agora */ } };
    // ── os filtros no modelo do Histórico (Levi, 05/11/2026: "quero que os filtros dos chamados sejam no estilo OS CREATOR
    // WEB > HISTÓRICO", "algo suspenso e moderno"): a busca à vista filtra enquanto se digita; os seis campos moram no painel
    // suspenso do botão Filtros, de marcar vários (o os_busca.js põe a caixa de busca em cada lista), e só valem no Aplicar;
    // fechar sem aplicar (Esc, clique fora, o botão de novo, o × da folha) DESCARTA. Cada filtro aplicado vira uma etiqueta,
    // e o × dela o tira na hora. Sem o "Limpar" (28/10/2026: "Tire o botão de limpar filtros"). ──
    const CAMPOS = ["marca", "cliente", "tipo", "geral", "st", "ufv"];
    const ROTULO = {marca: "Fornecedor", cliente: "Cliente", tipo: "Tipo de ativo", geral: "Status geral", st: "Status do chamado",
                    ufv: "Responsável UFV"};
    const busca = quadro.querySelector('[data-f="busca"]');
    const listaDe = function (nome) { return quadro.querySelector('.os-multi[data-nome="' + nome + '"]'); };
    const caixasDe = function (nome) {
      const d = listaDe(nome);
      return d ? Array.prototype.slice.call(d.querySelectorAll('input[type="checkbox"]')) : [];
    };
    const marcados = function (nome) {
      return caixasDe(nome).filter(function (c) { return c.checked; }).map(function (c) { return c.value; });
    };
    const textoDe = function (nome, v) {
      const c = caixasDe(nome).filter(function (x) { return x.value === v; })[0];
      const l = c && c.closest ? c.closest("label") : null;
      return l ? l.textContent.trim() : v;
    };
    const aplicado = {};                                                  // {campo: [valores]}: o que vale na tela
    CAMPOS.forEach(function (n) { aplicado[n] = []; });
    // a mesma regra no cartão e na linha da tabela (28/10/2026: o Status geral e o Responsável UFV no lugar do
    // Responsável; 04/11/2026: o Status do chamado, `st`); vários valores num campo = qualquer um deles; "_sem" = o que
    // não tem (sem status, sem Responsável UFV)
    const casa = function (vs, d) {
      return !vs || !vs.length || vs.some(function (v) { return v === "_sem" ? !d : d === v; });
    };
    const passa = function (d, f) {
      return CAMPOS.every(function (n) { return casa(f[n], d[n]); }) && (!f.busca || (d.busca || "").indexOf(f.busca) >= 0);
    };
    const aplicar = function () {
      const f = {busca: busca ? norm(busca.value) : ""}, crus = {busca: busca ? busca.value : ""};
      CAMPOS.forEach(function (n) { f[n] = aplicado[n]; crus[n] = aplicado[n].slice(); });
      guardar(CHAVE_FILTRO, crus);
      quadro.querySelectorAll(".col").forEach(function (col) {
        let n = 0;
        col.querySelectorAll(".card").forEach(function (card) {
          const ok = passa(card.dataset, f);
          card.classList.toggle("oculto", !ok);
          if (ok) n++;
        });
        contar(col.querySelector("[data-n]"), n);
        const vazio = col.querySelector("[data-vazio]");
        if (vazio) vazio.classList.toggle("oculto", n > 0);
      });
      // a tabela (27/10/2026): as linhas têm os mesmos data-* do cartão, e o filtro vale nas duas vistas
      let nLinhas = 0;
      quadro.querySelectorAll("tr[data-linha]").forEach(function (tr) {
        const ok = passa(tr.dataset, f);
        tr.classList.toggle("oculto", !ok);
        if (ok) nLinhas++;
      });
      const vazioTabela = quadro.querySelector("[data-vazio-tabela]");
      if (vazioTabela) vazioTabela.classList.toggle("oculto", nLinhas > 0);
      medir();                                                            // o filtro muda quais são os 6 primeiros
    };
    if (busca) busca.addEventListener("input", aplicar);
    // o resumo do campo: "Todos", o único marcado ou "N selecionados"
    const resumo = function (nome) {
      const d = listaDe(nome);
      if (!d) return;
      const txt = d.querySelector(".os-multi-txt"), sel = marcados(nome);
      if (txt) txt.textContent = !sel.length ? txt.getAttribute("data-todos") : (sel.length === 1 ? textoDe(nome, sel[0]) : sel.length + " selecionados");
      d.title = sel.map(function (v) { return textoDe(nome, v); }).join("\n");
      d.classList.toggle("fl-tem", sel.length > 0);
    };
    const poe = function (nome, vs) {
      caixasDe(nome).forEach(function (c) { c.checked = vs.indexOf(c.value) >= 0; });
      resumo(nome);
    };
    const igual = function (a, b) { return JSON.stringify(a.slice().sort()) === JSON.stringify(b.slice().sort()); };
    const painel = document.getElementById("fl_painel"), veu = document.getElementById("fl_veu");
    const barra = document.getElementById("fl_barra"), bFiltros = document.getElementById("b_filtros");
    const bApl = document.getElementById("b_aplicar"), nAlt = document.getElementById("fl_nalt");
    const caixaEtiquetas = document.getElementById("fl_etiquetas"), nFiltros = document.getElementById("fl_n");
    // o Aplicar acende com N alterações (a conta é por campo), e o campo que mudou ganha o ponto lima
    const acende = function () {
      let n = 0;
      CAMPOS.forEach(function (nome) {
        const mudou = !igual(marcados(nome), aplicado[nome]);
        const cel = quadro.querySelector('.fl-cel[data-filtro="' + nome + '"]');
        if (cel) cel.classList.toggle("mudou", mudou);
        if (mudou) n++;
      });
      if (bApl) bApl.disabled = n === 0;
      if (nAlt) nAlt.textContent = n === 0 ? "Sem alterações" : n + (n === 1 ? " alteração" : " alterações");
      return n;
    };
    const no = function (tag, classe, t) {
      const e = document.createElement(tag);
      if (classe) e.className = classe;
      if (t !== undefined) e.textContent = t;
      return e;
    };
    // as etiquetas são o que está APLICADO: uma por campo, e a contagem do botão Filtros é a mesma conta (a busca não conta)
    const etiquetas = function () {
      if (!caixaEtiquetas) return;
      while (caixaEtiquetas.firstChild) caixaEtiquetas.removeChild(caixaEtiquetas.firstChild);
      let n = 0;
      CAMPOS.forEach(function (nome) {
        const vs = aplicado[nome];
        if (!vs.length) return;
        n++;
        const texto = vs.length === 1 ? textoDe(nome, vs[0]) : vs.length + " selecionados";
        const NS = "http://www.w3.org/2000/svg", ico = document.createElementNS(NS, "svg"), uso = document.createElementNS(NS, "use");
        ico.setAttribute("class", "fl-ico"); ico.setAttribute("aria-hidden", "true"); uso.setAttribute("href", "#fl-i-x"); ico.appendChild(uso);
        const c = no("span", "fl-chip"), x = no("button", "fl-chip-x");
        c.setAttribute("data-filtro", nome);
        c.appendChild(no("i", "", ROTULO[nome])); c.appendChild(document.createTextNode(" ")); c.appendChild(no("span", "fl-chip-v", texto));
        if (vs.length > 1) c.title = vs.map(function (v) { return textoDe(nome, v); }).join("\n");
        x.type = "button"; x.setAttribute("aria-label", "Tirar o filtro " + ROTULO[nome] + ": " + texto); x.appendChild(ico);
        x.addEventListener("click", function () { tirar(nome); });
        c.appendChild(x);
        caixaEtiquetas.appendChild(c);
      });
      caixaEtiquetas.hidden = n === 0;
      if (nFiltros) { nFiltros.textContent = String(n); nFiltros.hidden = n === 0; }
    };
    const descarta = function () { CAMPOS.forEach(function (nome) { poe(nome, aplicado[nome]); }); acende(); };
    // o painel: o botão Filtros abre e fecha; fechar sem aplicar descarta
    let aberto = false;
    const celular = function () { return !!(window.matchMedia && window.matchMedia("(max-width: 639px)").matches); };
    const posiciona = function () {                                       // PC: a borda esquerda do painel na do botão
      if (celular() || !barra || !bFiltros.getBoundingClientRect) { painel.style.left = ""; return; }
      const c = barra.getBoundingClientRect(), r = bFiltros.getBoundingClientRect(), w = painel.offsetWidth || 0;
      painel.style.left = Math.max(0, Math.min(Math.round(r.left - c.left), Math.round(c.width - w))) + "px";
    };
    const abrePainel = function () {
      if (!aberto) { painel.hidden = false; if (veu) veu.hidden = false; aberto = true; }
      bFiltros.setAttribute("aria-expanded", "true");
      posiciona();
      if (painel.focus) painel.focus();
    };
    const fechaPainel = function (descartar) {
      if (!aberto) return;
      if (descartar) descarta();
      const focoDentro = painel.contains(document.activeElement);
      painel.querySelectorAll("details[open]").forEach(function (d) { d.removeAttribute("open"); });
      painel.hidden = true; if (veu) veu.hidden = true; aberto = false;
      bFiltros.setAttribute("aria-expanded", "false");
      if (focoDentro && bFiltros.focus) bFiltros.focus();
    };
    const aplicarPainel = function () {
      CAMPOS.forEach(function (nome) { aplicado[nome] = marcados(nome); });
      aplicar(); fechaPainel(false); acende(); etiquetas();
    };
    const tirar = function (nome) {                                       // o × de uma etiqueta: tira o filtro e aplica na hora
      descarta();                                                         // o que estava no painel sem aplicar não vai junto
      aplicado[nome] = []; poe(nome, []);
      aplicar(); acende(); etiquetas();
    };
    if (painel && bFiltros) {
      bFiltros.addEventListener("click", function () { if (aberto) fechaPainel(true); else abrePainel(); });
      const bFechar = document.getElementById("fl_fechar");
      if (bFechar) bFechar.addEventListener("click", function () { fechaPainel(true); });
      if (bApl) bApl.addEventListener("click", aplicarPainel);
      CAMPOS.forEach(function (nome) {
        caixasDe(nome).forEach(function (c) { c.addEventListener("change", function () { resumo(nome); acende(); }); });
      });
      // o clique fora descarta ANTES de qualquer outro clique da página agir (captura), como no Histórico
      document.addEventListener("click", function (e) {
        if (aberto && !painel.contains(e.target) && !bFiltros.contains(e.target)) fechaPainel(true);
      }, true);
      // a lista aberta fecha no clique fora dela, dentro do painel
      document.addEventListener("click", function (e) {
        painel.querySelectorAll("details.os-multi[open]").forEach(function (d) { if (!d.contains(e.target)) d.removeAttribute("open"); });
      });
      // o Esc fecha só a lista aberta; com ela fechada, o painel (sem aplicar)
      document.addEventListener("keydown", function (e) {
        if (e.key !== "Escape" || !aberto) return;
        const lista = painel.querySelector("details[open]");
        if (lista) { lista.removeAttribute("open"); const sm = lista.querySelector("summary"); if (sm && sm.focus) sm.focus(); return; }
        fechaPainel(true);
      });
    }
    // quadro ou tabela (27/10/2026): a escolha fica neste navegador; o <script> curto do acomp.html já a pôs antes da
    // 1ª pintura (a mesma chave). Ao voltar ao quadro, as colunas são medidas de novo (escondidas, não dá para medir).
    quadro.querySelectorAll(".vistas [data-vista]").forEach(function (b) {
      b.addEventListener("click", function () {
        quadro.dataset.vista = b.dataset.vista;
        try { localStorage.setItem("acomp.vista", b.dataset.vista); } catch (e) { /* aba anônima: vale só agora */ }
        if (b.dataset.vista === "quadro") remedir();
      });
    });
    quadro.querySelectorAll("tr[data-linha]").forEach(function (tr) {
      tr.addEventListener("click", function (ev) {
        if (ev.target && ev.target.closest && ev.target.closest("a")) return;   // o nº da OS já é o link
        location.href = tr.dataset.href;
      });
    });
    // os avisos na exclamação (28/10/2026, como em Segurança > Extintores): o clique fora e o Esc fecham
    const avisos = quadro.querySelector("details.ac-aviso");
    if (avisos) {
      document.addEventListener("click", function (ev) { if (avisos.open && !avisos.contains(ev.target)) avisos.open = false; });
      document.addEventListener("keydown", function (ev) { if (ev.key === "Escape" && avisos.open) avisos.open = false; });
    }
    // Exportar tabela (28/10/2026): as linhas que os filtros deixam, na ordem da tela, numa planilha
    const bTabela = quadro.querySelector("[data-exportar-tabela]");
    if (bTabela) bTabela.addEventListener("click", async function () {
      const folios = Array.prototype.filter.call(quadro.querySelectorAll("tr[data-linha]"), function (tr) {
        return !tr.classList.contains("oculto");
      }).map(function (tr) { return tr.dataset.folio; });
      bTabela.disabled = true;
      try { await baixar("/os/chamados/acompanhamento/tabela", {folios: folios}, "Garantias.xlsx"); }
      catch (e) { if (e.message !== "sessão") alert("Não exportou: " + e.message); }
      bTabela.disabled = false;
    });
    // Exportar relatório (28/10/2026): um checkbox por cliente; os clientes do filtro aplicado vêm marcados
    const dlg = quadro.querySelector("[data-dlg-relatorio]"), bRel = quadro.querySelector("[data-relatorio]");
    if (dlg && bRel) {
      const mRel = dlg.querySelector("[data-msg-relatorio]");
      bRel.addEventListener("click", function () {
        dlg.querySelectorAll('input[type="checkbox"]').forEach(function (x) { x.checked = aplicado.cliente.indexOf(x.value) >= 0; });
        msg(mRel, "");
        if (dlg.showModal) dlg.showModal(); else dlg.setAttribute("open", "");
      });
      dlg.querySelector("[data-fechar]").addEventListener("click", function () { dlg.close ? dlg.close() : dlg.removeAttribute("open"); });
      const bExp = dlg.querySelector("[data-exportar-relatorio]");
      bExp.addEventListener("click", async function () {
        const clientes = Array.prototype.filter.call(dlg.querySelectorAll('input[type="checkbox"]'), function (x) { return x.checked; })
          .map(function (x) { return x.value; });
        if (!clientes.length) { msg(mRel, "Marque ao menos um cliente.", "er"); return; }
        bExp.disabled = true; msg(mRel, "Montando o relatório…");
        try {
          await baixar("/os/chamados/acompanhamento/relatorio", {clientes: clientes},
                       clientes.length === 1 ? "Chamados de garantia.pdf" : "Chamados de garantia.zip");
          msg(mRel, "Pronto.", "ok");
          setTimeout(function () { if (dlg.close) dlg.close(); }, 600);
        } catch (e) {
          if (e.message !== "sessão") msg(mRel, "Não exportou: " + e.message, "er");
        }
        bExp.disabled = false;
      });
    }
    // o filtro guardado volta (o de antes de 05/11/2026 guardava um valor só por campo: vira lista de um)
    const salvo = lerGuardado(CHAVE_FILTRO) || {};
    let comFiltro = false;
    CAMPOS.forEach(function (nome) {
      const quer = [].concat(salvo[nome] || []), tem = caixasDe(nome).map(function (c) { return c.value; });
      aplicado[nome] = quer.filter(function (v) { return v && tem.indexOf(v) >= 0; });
      if (aplicado[nome].length) comFiltro = true;
      poe(nome, aplicado[nome]);
    });
    if (busca && salvo.busca) { busca.value = salvo.busca; comFiltro = true; }
    if (comFiltro) aplicar();
    etiquetas();
    const caixas = quadro.querySelectorAll(".cards");
    window.addEventListener("pagehide", function () {
      guardar(CHAVE_ROLAGEM, {pagina: window.scrollY || 0, colunas: Array.prototype.map.call(caixas, function (b) { return b.scrollTop || 0; })});
    });
    const rolagem = lerGuardado(CHAVE_ROLAGEM);
    if (rolagem) requestAnimationFrame(function () {              // depois do medir: a coluna já tem a altura dela
      (rolagem.colunas || []).forEach(function (t, i) { if (caixas[i]) caixas[i].scrollTop = t || 0; });
      if (rolagem.pagina) window.scrollTo(0, rolagem.pagina);
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

  // o status do chamado (27/10/2026): grava no banco da Gridco e recarrega, para a troca aparecer nas observações
  const bStatus = document.getElementById("b_status");
  if (bStatus) {
    bStatus.addEventListener("click", async function () {
      const campo = document.getElementById("status_ch"), m = document.getElementById("msg_status");
      bStatus.disabled = true; msg(m, "Gravando…");
      try {
        const j = await postar("/os/api/acomp/" + folio + "/status", {status: campo.value || "", wid: wid});
        msg(m, j.mensagem || "Status gravado.", "ok");
        setTimeout(function () { location.reload(); }, 700);
      } catch (e) {
        if (e.message !== "sessão") msg(m, "Não gravou: " + e.message, "er");
        bStatus.disabled = false;
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
        if (e.id && e.editavel && tela.dataset.podeObs === "1") {            // a nova também edita e exclui (29/10/2026)
          div.dataset.obsId = e.id;
          const ac = document.createElement("div");
          ac.className = "tl-acoes";
          ac.innerHTML = '<button type="button" class="det-mini" data-obs-editar>editar</button>' +
                         '<button type="button" class="det-mini" data-obs-excluir>excluir</button>';
          div.querySelector(".tl-x").appendChild(ac);
        }
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

  // editar e excluir a observação escrita (29/10/2026): no lugar, sem janela; gravado, a tela relê (a editada com a marca,
  // a excluída some). O banco guarda as duas versões (chamados_obs_store.vigentes)
  const tlObs = document.getElementById("tl");
  if (tlObs) tlObs.addEventListener("click", async function (ev) {
    const alvo = ev.target.closest("[data-obs-editar],[data-obs-excluir],[data-obs-salvar],[data-obs-sim],[data-obs-nao]");
    if (!alvo) {
      // o clique na observação mostra (ou esconde) o editar e o excluir dela; a outra aberta fecha
      const aqui = ev.target.closest("[data-obs-id]");
      if (!aqui || ev.target.closest("textarea") || !aqui.querySelector(".tl-acoes")) return;
      tlObs.querySelectorAll("[data-obs-id].aberta").forEach(function (x) { if (x !== aqui) x.classList.remove("aberta"); });
      aqui.classList.toggle("aberta");
      return;
    }
    const ent = alvo.closest("[data-obs-id]");
    if (!ent) return;
    const id = ent.dataset.obsId, x = ent.querySelector(".tl-x"), t = ent.querySelector(".tl-t");
    const acoes = ent.querySelector(".tl-acoes");
    const aviso = function (texto) {
      let m = ent.querySelector(".msg");
      if (!m) { m = document.createElement("div"); x.appendChild(m); }
      msg(m, texto, "er");
    };
    if (alvo.hasAttribute("data-obs-editar")) {
      if (ent.querySelector("textarea")) return;
      const campo = document.createElement("textarea");
      campo.className = "obs";
      campo.maxLength = 2000;
      campo.value = t.textContent;
      t.hidden = true;
      x.insertBefore(campo, t.nextSibling);
      acoes.innerHTML = '<button type="button" class="det-mini" data-obs-salvar>salvar</button>' +
                        '<button type="button" class="det-mini" data-obs-nao>cancelar</button>';
      campo.focus();
      return;
    }
    if (alvo.hasAttribute("data-obs-excluir")) {
      acoes.innerHTML = '<span class="tl-conf">Excluir esta observação?</span>' +
                        '<button type="button" class="det-mini" data-obs-sim>excluir</button>' +
                        '<button type="button" class="det-mini" data-obs-nao>cancelar</button>';
      return;
    }
    if (alvo.hasAttribute("data-obs-nao")) { location.reload(); return; }
    alvo.disabled = true;
    try {
      if (alvo.hasAttribute("data-obs-salvar")) {
        const texto = (ent.querySelector("textarea").value || "").trim();
        if (!texto) { aviso("Escreva a observação antes de salvar."); alvo.disabled = false; return; }
        await postar("/os/api/acomp/" + folio + "/obs/" + encodeURIComponent(id) + "/editar", {texto: texto});
      } else {
        await postar("/os/api/acomp/" + folio + "/obs/" + encodeURIComponent(id) + "/excluir", {});
      }
      location.reload();
    } catch (e) {
      if (e.message !== "sessão") aviso("Não gravou: " + e.message);
      alvo.disabled = false;
    }
  });

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

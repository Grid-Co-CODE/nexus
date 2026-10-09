/* Quadro da semana (nexus/pcm/quadro.py, templates/pcm/quadro.html): a janela da OS e a fila de reprogramação.

   A fila mora no navegador (localStorage, por semana), como no painel do PCM; ao gravar, a página manda só
   {os, tarefa, dia, turno} e o servidor refaz cada linha com a tarefa e o tipo da SEMANA (quadro.linhas_da_fila).
   `linha` abaixo é a mesma de quadro.linha (e do rpLinha do painel do PCM): o teste roda as duas com os mesmos casos. */
(function (raiz) {
  "use strict";

  var SIGLAS = ["MPA", "MPS", "MPT", "MPM", "MPQ", "HANDOVER"];

  function sigla(tipo) {
    var t = String(tipo || "").toUpperCase().replace(/-.*$/, "").trim();
    return SIGLAS.indexOf(t) >= 0 ? (t === "HANDOVER" ? "Handover" : t) : null;
  }
  // "[Grid Co.] - MPA - Caixa d'água" -> "Caixa d'água"
  function chaveDaTarefa(tarefa) {
    var s = String(tarefa || "").split(/\s[-–]\s/).pop().trim();
    return s.split(",")[0].split(";")[0].trim();
  }
  function nomeDaTarefa(tarefa) {
    return String(tarefa || "").split(",")[0].split(";")[0].trim();
  }
  function linha(os, dia, turno, tarefa, tipo) {
    os = String(os).trim(); turno = turno || "";
    if (dia === "não") return os + "; não";
    if (!tarefa) return turno ? (os + "; " + dia + "; ; " + turno) : (os + "; " + dia);
    var sig = sigla(tipo), partes;
    if (sig) {
      var ch = chaveDaTarefa(tarefa);
      partes = [os, dia, sig, turno, ch ? ("só: " + ch) : ""];
    } else {
      var nome = nomeDaTarefa(tarefa);
      if (!nome) return null;
      partes = [os, dia, nome, turno];
    }
    return partes.filter(function (v, i) { return i < 3 || v; }).join("; ");
  }

  raiz.QuadroLinha = { linha: linha, sigla: sigla, chaveDaTarefa: chaveDaTarefa };
  if (typeof document === "undefined") return;          // no node (o teste), só a linha

  var no = document.getElementById("q-dados");
  if (!no) return;
  var D = JSON.parse(no.textContent);
  var ITENS = D.itens || [];
  var OSS = D.oss || {};          // as tarefas de cada OS com mais de uma (agenda e pendentes), uma vez por OS
  var CHAVE = "nexus.pcm.reprog." + D.semana + (D.rodada ? ("." + D.rodada) : "");
  var FILA = [];
  try { FILA = JSON.parse(localStorage.getItem(CHAVE) || "[]") || []; } catch (e) { FILA = []; }
  if (D.feito) { FILA = []; salvar(); }               // gravou: a fila desta semana já foi

  function salvar() { try { localStorage.setItem(CHAVE, JSON.stringify(FILA)); } catch (e) { /* sem armazenamento */ } }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function idx(os, tarefa) {
    for (var i = 0; i < FILA.length; i++) if (FILA[i].os === String(os) && FILA[i].tarefa === (tarefa || "")) return i;
    return -1;
  }
  function tipoDe(os, tarefa) {
    var irmas = OSS[String(os)] || [];
    for (var j = 0; j < irmas.length; j++) if (irmas[j].t === tarefa) return irmas[j].tp;
    for (var i = 0; i < ITENS.length; i++) if (ITENS[i].os === String(os) && ITENS[i].t === tarefa) return ITENS[i].tp;
    return "";
  }
  function linhaDoItem(r) { return linha(r.os, r.dia, r.turno, r.tarefa, r.tipo); }
  function aviso(msg) {
    var a = document.getElementById("q-aviso");
    if (!a) return;
    a.textContent = msg; a.hidden = false;
    clearTimeout(aviso._t); aviso._t = setTimeout(function () { a.hidden = true; }, 4000);
  }

  // A mesma tarefa duas vezes na fila: vale a última. "OS; não" é a OS inteira (a gramática não filtra tarefa no "não").
  function inserir(os, tarefa, dia, turno) {
    if (!dia) { aviso("Escolha o dia primeiro."); return null; }
    var r = { os: String(os), tarefa: dia === "não" ? "" : (tarefa || ""), tipo: "", dia: dia,
              turno: dia === "não" ? "" : (turno || "") };
    r.tipo = r.tarefa ? tipoDe(os, r.tarefa) : "";
    if (linhaDoItem(r) === null) { aviso("Esta tarefa não tem nome que o motor reconheça: reprograme a OS inteira."); return null; }
    var i = idx(r.os, r.tarefa);
    if (i >= 0) FILA.splice(i, 1);
    FILA.push(r); salvar(); pintarFila(); marcar();
    return r;
  }

  // ── a fila (barra no pé da página) ──────────────────────────────────────────────────────────────────────
  var dock = document.getElementById("q-fila");
  function pintarFila() {
    if (!dock) return;
    var n = FILA.length;
    dock.hidden = !n;
    dock.querySelector("[data-fila-n]").textContent = n + (n === 1 ? " reprogramação na fila" : " reprogramações na fila");
    dock.querySelector("[data-fila-linhas]").textContent = FILA.map(linhaDoItem).join("\n");
    var campo = dock.querySelector("input[name=itens]");
    if (campo) campo.value = JSON.stringify(FILA.map(function (r) {
      return { os: r.os, tarefa: r.tarefa, dia: r.dia, turno: r.turno };
    }));
    var st = document.getElementById("q-det-fila");
    if (st) st.innerHTML = n ? ("<b>" + n + "</b> na fila") : "A fila está vazia.";
  }
  function marcar() {
    var na = {};
    FILA.forEach(function (r) { na[r.os] = true; });
    document.querySelectorAll("[data-os]").forEach(function (el) {
      el.classList.toggle("q-na-fila", !!na[el.getAttribute("data-os")]);
    });
  }
  if (dock) {
    dock.querySelector("[data-fila-ver]").addEventListener("click", function () {
      var aberta = dock.classList.toggle("q-fila--aberta");
      this.textContent = aberta ? "Ocultar linhas" : "Ver linhas";
      this.setAttribute("aria-expanded", aberta ? "true" : "false");
    });
    dock.querySelector("[data-fila-copiar]").addEventListener("click", function () {
      var txt = FILA.map(linhaDoItem).join("\n");
      if (!txt) return;
      var ok = function () { aviso(FILA.length + (FILA.length === 1 ? " linha copiada." : " linhas copiadas.")); };
      var reserva = function () {
        var ta = document.createElement("textarea");
        ta.value = txt; ta.style.cssText = "position:fixed;opacity:0";
        document.body.appendChild(ta); ta.select();
        try { document.execCommand("copy"); ok(); } catch (e) { aviso("Selecione e copie as linhas da fila."); }
        document.body.removeChild(ta);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(txt).then(ok, reserva);
      else reserva();
    });
    dock.querySelector("[data-fila-limpar]").addEventListener("click", function () {
      if (!FILA.length || !confirm("Limpar as " + FILA.length + " reprogramações da fila?")) return;
      FILA = []; salvar(); pintarFila(); marcar();
    });
  }

  // ── a janela da OS ──────────────────────────────────────────────────────────────────────────────────────
  var dlg = document.getElementById("q-det");
  var abriu = null;
  function dl(rot, val) {
    return (val === null || val === undefined || val === "" || val === 0) ? "" :
      "<div class=\"q-dl\"><dt>" + esc(rot) + "</dt><dd>" + esc(val) + "</dd></div>";
  }
  function sn(v) {
    var x = String(v || "").trim().toLowerCase();
    return x === "sim" ? "Sim" : (x === "não" || x === "nao") ? "Não" : (v || "");
  }
  function chipEstado(st) {
    var c = { "Finalizada": "feita", "Em progresso": "andamento", "Pausada": "pausada" }[st] || "nao";
    return "<span class=\"q-st q-st--" + c + "\">" + esc(st) + "</span>";
  }
  function trajetoria(t) {
    if (!t.tl || t.tl.length < 2)
      return "<p class=\"q-vazio\">Primeira semana desta tarefa no período guardado" +
        (t.rol > 1 ? " — mas o campo de vezes diz " + t.rol + "ª semana na fila." : ".") + "</p>";
    var ult = t.tl[t.tl.length - 1], antes = (ult.v || 0) - t.tl.length;
    return "<ol class=\"q-tl\">" + t.tl.map(function (e) {
      return "<li class=\"" + (e.ativa ? "q-tl--ativa" : "") + "\"><span class=\"q-tl-w\">" + esc(e.w) + "</span>" +
        "<span>" + esc(e.d || "—") + "</span>" + (e.ini ? "<span class=\"gc-dado\">" + esc(e.ini) +
        (e.fim ? "–" + esc(e.fim) : "") + "</span>" : "") + chipEstado(e.st) +
        (e.ativa ? "<span class=\"q-tl-meta\">esta semana</span>" : "") + "</li>";
    }).join("") + "</ol>" + (antes > 0 ? "<p class=\"q-nota\">Antes disso rolou mais <b>" + antes + "</b> " +
      (antes === 1 ? "semana" : "semanas") + ": o campo de vezes marca " + ult.v + "ª, e o arquivo guarda " +
      t.tl.length + ".</p>" : "");
  }
  function opcoesDia(vazio) {
    return "<option value=\"\">" + vazio + "</option>" + D.dias.map(function (d) {
      return "<option value=\"" + d[0] + "\">" + esc(d[1]) + "</option>";
    }).join("");
  }
  function opcoesTurno() {
    return "<option value=\"\">turno do motor</option>" + D.turnos.map(function (t) {
      return "<option value=\"" + t + "\">" + esc(t) + "</option>";
    }).join("");
  }
  function blocoReprogramar(t) {
    if (!D.destino) return "";
    var irmas = OSS[t.os] || [];
    var alvo = irmas.length > 1
      ? "<label class=\"q-campo\"><span>O que</span><select class=\"gc-campo\" data-rp-alvo>" +
        "<option value=\"\">a OS inteira (" + irmas.length + " tarefas)</option>" +
        irmas.map(function (x) {
          return "<option value=\"" + esc(x.t) + "\"" + (x.t === t.t ? " selected" : "") + ">" +
            esc(x.t.length > 70 ? x.t.slice(0, 70) + "…" : x.t) + (x.pend ? " (pendente)" : "") + "</option>";
        }).join("") + "</select></label>"
      : "<input type=\"hidden\" data-rp-alvo value=\"" + esc(t.t) + "\"><p class=\"q-rp-alvo\">" + esc(t.t) + "</p>";
    return "<h3>Reprogramar</h3><div class=\"q-rp\">" + alvo +
      "<div class=\"q-rp-linha\"><label class=\"q-campo\"><span>Dia</span><select class=\"gc-campo\" data-rp-dia>" +
      opcoesDia("escolha…") + "</select></label><label class=\"q-campo\"><span>Turno</span><select class=\"gc-campo\" " +
      "data-rp-turno>" + opcoesTurno() + "</select></label></div>" +
      "<div class=\"q-rp-acoes\"><button type=\"button\" class=\"gc-btn gc-btn--ui gc-btn--primario\" data-rp-inserir>" +
      "<i class=\"ph ph-plus\"></i> Inserir na fila</button><button type=\"button\" class=\"gc-btn gc-btn--ui " +
      "gc-btn--contorno q-rp-tirar\" data-rp-tirar><i class=\"ph ph-x\"></i> Tirar da semana</button></div>" +
      "<p class=\"q-rp-st\" id=\"q-det-fila\"></p><p class=\"q-rp-linha-txt\" data-rp-txt hidden></p></div>";
  }
  function abrir(i, origem) {
    var t = ITENS[i];
    if (!t || !dlg) return;
    abriu = origem || null;
    var c = dlg.querySelector("[data-det-corpo]");
    c.innerHTML =
      "<p class=\"gc-eyebrow\">OS " + esc(t.os) + (t.ss ? " · SS " + esc(t.ss) : "") + "</p>" +
      "<h2 class=\"q-det-titulo\" id=\"q-det-titulo\">" + esc(t.t) + "</h2>" +
      "<div class=\"q-fatos\">" +
      "<div><span>Tipo</span><b><i class=\"q-ponto q-t--" + esc(t.tc) + "\"></i>" + esc(t.tp || "—") + "</b></div>" +
      "<div><span>Situação</span><b>" + (t.pend ? "<span class=\"q-st q-st--nao\">Pendente</span>" : chipEstado(t.st)) + "</b></div>" +
      "<div><span>Semanas na fila</span><b class=\"" + (t.rol >= 3 ? "q-mal" : "") + "\">" + (t.rol || 1) + "ª semana</b></div>" +
      "<div><span>Reprogramada</span><b class=\"" + (t.rep ? "q-mal" : "") + "\">" + (t.rep ? "Sim" : "Não") + "</b></div></div>" +
      (t.pend && t.mot ? "<p class=\"q-nota\">Não coube na semana: " + esc(t.mot) + "</p>" : "") +
      "<h3>Onde</h3><dl>" + dl("Usina", t.uc) + dl("Cliente", t.cli) + dl("Equipe cluster", t.cl) +
      dl("Código do ativo", t.cod) + "</dl>" +
      "<h3>Quando</h3><dl>" + dl("Criada em", t.dcri) + dl("Dia nesta semana", t.d ? (t.d + (t.data ? " " + t.data : "")) : "") +
      dl("Data no Fracttal", t.dprog) + dl("Janela", t.ini && t.fim ? t.ini + " – " + t.fim : t.ini) +
      dl("Duração prevista", t.h) + dl("Deslocamento", t.desl ? String(t.desl).replace(".", ",") + " h" : "") +
      dl("Finalizada em", t.dfim) + dl("Rolagem", t.rol_txt) + "</dl>" +
      "<h3>Quem</h3><dl>" + dl("Responsável O&M", t.resp) + dl("Responsável da OS", t.ros) + "</dl>" +
      "<h3>Situação da OS</h3><dl>" + dl("Status da OS", t.sp) + dl("Criticidade", t.cri) +
      dl("Em paralelo", sn(t.par)) + dl("Termografia", sn(t.termo)) + dl("Origem", t.nova) + dl("Etiqueta", t.etq) + "</dl>" +
      blocoReprogramar(t) +
      (t.pend ? "" : "<h3>Trajetória</h3>" + trajetoria(t)) +
      "<h3>Relatório de execução</h3>" + (t.rel ? "<p class=\"q-rel\">" + esc(t.rel) + "</p>"
        : "<p class=\"q-vazio\">Sem relatório registrado.</p>");
    var ins = c.querySelector("[data-rp-inserir]");
    if (ins) ins.addEventListener("click", function () {
      var alvo = c.querySelector("[data-rp-alvo]");
      var r = inserir(t.os, alvo ? alvo.value : "", c.querySelector("[data-rp-dia]").value,
                      c.querySelector("[data-rp-turno]").value);
      if (!r) return;
      var txt = c.querySelector("[data-rp-txt]");
      txt.hidden = false;
      txt.innerHTML = "Linha: <code>" + esc(linhaDoItem(r)) + "</code>";
    });
    var tir = c.querySelector("[data-rp-tirar]");
    if (tir) tir.addEventListener("click", function () {
      var n = (OSS[t.os] || []).length || 1;
      if (!confirm("Tirar a OS " + t.os + " da programação desta semana?" +
                   (n > 1 ? "\n\nIsso tira as " + n + " tarefas dela." : ""))) return;
      var r = inserir(t.os, "", "não", "");
      if (r) { aviso("A OS " + t.os + " sai da semana · " + FILA.length + " na fila"); fechar(); }
    });
    pintarFila();
    dlg.showModal();
    dlg.querySelector("[data-det-fechar]").focus();
  }
  function fechar() {
    if (dlg && dlg.open) dlg.close();
  }
  if (dlg) {
    dlg.addEventListener("close", function () { if (abriu && document.contains(abriu)) abriu.focus(); abriu = null; });
    dlg.querySelector("[data-det-fechar]").addEventListener("click", fechar);
    // o <dialog> não tem margem interna: o clique que cai nele mesmo (e não no corpo) foi no véu
    dlg.addEventListener("click", function (e) { if (e.target === dlg) fechar(); });
  }
  document.querySelectorAll("[data-cartao]").forEach(function (el) {
    var i = +el.getAttribute("data-cartao");
    el.addEventListener("click", function () { abrir(i, el); });
    el.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); abrir(i, el); }
    });
  });

  // ── as pendentes: dia e turno na própria linha, e "todas" por usina ────────────────────────────────────────
  // Os controles vêm dos <template> da página, clonados aqui (repetidos no HTML pesavam 1,8 MB na W41).
  var tplPend = document.getElementById("q-tpl-pend"), tplLote = document.getElementById("q-tpl-lote");
  document.querySelectorAll("[data-pend]").forEach(function (el) {
    var t = ITENS[+el.getAttribute("data-pend")];
    var ctr = el.querySelector(".q-pend-ctr");
    if (!t || !ctr || !tplPend) return;
    ctr.appendChild(tplPend.content.cloneNode(true));
    var bt = ctr.querySelector("[data-pend-inserir]");
    bt.addEventListener("click", function () {
      var r = inserir(t.os, t.t, el.querySelector("[data-pend-dia]").value, el.querySelector("[data-pend-turno]").value);
      if (r) aviso("OS " + t.os + " → " + r.dia + (r.turno ? " (" + r.turno + ")" : "") + " · " + FILA.length + " na fila");
    });
  });
  document.querySelectorAll("[data-lote]").forEach(function (el) {
    if (!tplLote) return;
    el.appendChild(tplLote.content.cloneNode(true));
    var bt = el.querySelector("[data-lote-inserir]");
    bt.textContent = "Inserir todas (" + el.getAttribute("data-lote") + ")";
    bt.addEventListener("click", function () {
      var dia = el.querySelector("[data-lote-dia]").value, tur = el.querySelector("[data-lote-turno]").value;
      if (!dia) { aviso("Escolha o dia primeiro."); return; }
      var n = 0;
      el.closest("[data-usina]").querySelectorAll("[data-pend]").forEach(function (p) {
        var t = ITENS[+p.getAttribute("data-pend")];
        if (t && inserir(t.os, t.t, dia, tur)) n++;
      });
      aviso(n + (n === 1 ? " tarefa inserida" : " tarefas inseridas") + " · " + FILA.length + " na fila");
    });
  });

  pintarFila();
  marcar();
})(typeof window !== "undefined" ? window : globalThis);

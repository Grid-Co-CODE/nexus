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
    // tirar só ESTA tarefa da semana (15/10/2026): o "sem:" do motor e do robô, com o nome até a 1ª vírgula
    if (dia === "sem") { var n = nomeDaTarefa(tarefa); return n ? (os + "; sem: " + n) : null; }
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

  raiz.QuadroLinha = { linha: linha, sigla: sigla, chaveDaTarefa: chaveDaTarefa, nomeDaTarefa: nomeDaTarefa };
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

  // A mesma tarefa duas vezes na fila: vale a última. "OS; não" é a OS inteira (a gramática não filtra tarefa no "não");
  // dia "sem" tira só a tarefa.
  function inserir(os, tarefa, dia, turno) {
    if (!dia) { aviso("Escolha o dia primeiro."); return null; }
    var r = { os: String(os), tarefa: dia === "não" ? "" : (tarefa || ""), tipo: "", dia: dia,
              turno: (dia === "não" || dia === "sem") ? "" : (turno || "") };
    r.tipo = r.tarefa ? tipoDe(os, r.tarefa) : "";
    if (linhaDoItem(r) === null) { aviso("Esta tarefa não tem nome que o motor reconheça: reprograme a OS inteira."); return null; }
    var i = idx(r.os, r.tarefa);
    if (i >= 0) FILA.splice(i, 1);
    // a OS inteira (fora ou num dia) apaga o que a fila tinha por tarefa dela, como a mescla do servidor (quadro.mesclar)
    if (!r.tarefa) FILA = FILA.filter(function (x) { return !(x.os === r.os && x.tarefa); });
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
  // ── o motivo da tarefa (16/10/2026, nexus/pcm/motivos.py): um por tarefa; o que "tira da programação" é âmbar ──
  var MOTIVOS = D.motivos || [];          // [[id, nome, tira]] do cadastro
  function selo(nome, tira) {
    return "<span class=\"q-mp" + (tira ? " q-mp--tira" : "") + "\"><i class=\"ph ph-" + (tira ? "prohibit" : "tag") +
      "\"></i>" + esc(nome) + "</span>";
  }
  function blocoMotivo(t) {
    var mp = t.mp, pode = D.pode_marcar && MOTIVOS.length;
    if (!mp && !pode) return "";
    // Levi, 18/10/2026: o título é a pergunta que o motivo responde, e a tarefa sem motivo não diz "Sem motivo."
    var h = "<h3>Técnico não consegue fazer?</h3>";
    if (mp) {
      h += "<p class=\"q-mp-atual\">" + selo(mp.n, mp.tira) + "<span>desde " + esc(mp.desde) +
        (mp.quem ? " · " + esc(mp.quem) : "") + (mp.app ? " (App)" : "") + "</span></p>" +
        (mp.obs ? "<p class=\"q-rel\">" + esc(mp.obs) + "</p>" : "") +
        "<p class=\"q-nota\">" + (mp.tira ? "Este motivo tira a tarefa da programação." : "A tarefa continua na programação.") +
        (mp.geral ? " Marcado pelo número da OS: vale para esta tarefa em todos os ativos da OS." : "") + "</p>";
    }
    if (!pode) return mp ? h : "";
    return h + "<div class=\"q-rp q-mp-form\"><label class=\"q-campo\"><span>Motivo</span><select class=\"gc-campo\" " +
      "data-mp-sel><option value=\"\">escolha…</option>" + MOTIVOS.map(function (m) {
        return "<option value=\"" + m[0] + "\"" + (mp && mp.id === m[0] ? " selected" : "") + ">" + esc(m[1]) +
          (m[2] ? " (tira da programação)" : "") + "</option>";
      }).join("") + "</select></label><label class=\"q-campo\"><span>Observação (opcional)</span><textarea class=\"gc-campo\" " +
      "data-mp-obs rows=\"2\" maxlength=\"500\">" + esc(mp ? mp.obs : "") + "</textarea></label><div class=\"q-rp-acoes\">" +
      "<button type=\"button\" class=\"gc-btn gc-btn--ui gc-btn--primario\" data-mp-salvar><i class=\"ph ph-tag\"></i> " +
      "Salvar motivo</button>" + (mp ? "<button type=\"button\" class=\"gc-btn gc-btn--ui " +
      "gc-btn--contorno\" data-mp-tirar><i class=\"ph ph-x\"></i> Tirar o motivo</button>" : "") + "</div>" +
      "<p class=\"q-nota\" data-mp-msg role=\"status\"" + (t._mpMsg ? "" : " hidden") + ">" + esc(t._mpMsg || "") + "</p></div>";
  }
  // a marca nova vale para as linhas da mesma tarefa: a da OS (sem código), em todos os ativos que não têm marca
  // própria; a do ativo, só nas linhas daquele ativo (a resposta traz a que passou a valer para ele)
  function aplicarMarca(t, j) {
    ITENS.forEach(function (x) {
      if (x.os !== t.os || x.t !== t.t) return;
      if (j.geral) {
        if (x.mp && !x.mp.geral) return;
        if (j.marca) x.mp = j.marca; else delete x.mp;
      } else if ((x.cod || "") === (t.cod || "")) {
        if (j.efetiva) x.mp = j.efetiva; else delete x.mp;
      }
    });
    pintarMotivos();
  }
  function pintarMotivos() {
    document.querySelectorAll("[data-cartao],[data-pend]").forEach(function (el) {
      var i = +(el.getAttribute("data-cartao") || el.getAttribute("data-pend"));
      var slot = el.querySelector("[data-mp-slot]"), mp = ITENS[i] && ITENS[i].mp;
      if (!slot) return;
      slot.hidden = !mp;
      slot.innerHTML = mp ? ((el.hasAttribute("data-pend") ? " · " : "") + selo(mp.n, mp.tira)) : "";
    });
  }
  function enviarMotivo(i, t, c, tirar) {
    var sel = c.querySelector("[data-mp-sel]"), obs = c.querySelector("[data-mp-obs]");
    var msg = c.querySelector("[data-mp-msg]");
    var escolhido = null;
    MOTIVOS.forEach(function (m) { if (String(m[0]) === sel.value) escolhido = m; });
    if (!tirar && !escolhido) { aviso("Escolha o motivo."); return; }
    if (tirar && !confirm("Tirar o motivo “" + t.mp.n + "” desta tarefa?" + (t.mp.geral ? "\n\nEle foi marcado pelo " +
        "número da OS: sai da tarefa em todos os ativos da OS." : "") + (t.mp.tira ? "\n\nA tarefa volta a ser programada " +
        "na próxima geração da semana." : ""))) return;
    if (!tirar && escolhido[2] && !(t.mp && t.mp.id === escolhido[0]) && !confirm("“" + escolhido[1] + "” tira a tarefa " +
        "da programação.\n\n" + (D.destino === "atual" ? "Na semana em curso, o robô do PCM a tira na próxima rodada (até " +
        "30 minutos)." : "A geração da semana não a programa enquanto o motivo valer.") + " Marcar?")) return;
    c.querySelectorAll("[data-mp-salvar],[data-mp-tirar]").forEach(function (b) { b.disabled = true; });
    msg.hidden = false; msg.textContent = "Gravando…";
    fetch(D.url_motivo, {method: "POST", credentials: "same-origin", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({semana: D.semana, rodada: D.rodada, os: t.os, tarefa: t.t, codigo: t.cod || "",
                            motivo_id: tirar ? "" : sel.value, obs: tirar ? "" : obs.value, tirar: !!tirar})})
      .then(function (r) {
        return r.json().then(function (j) { return {ok: r.ok, j: j}; },
                             function () { return {ok: false, j: {erro: "O Nexus não respondeu (" + r.status + ")."}}; });
      })
      .then(function (x) {
        if (!x.ok || !x.j.ok) {
          msg.textContent = x.j.erro || "Não gravou.";
          c.querySelectorAll("[data-mp-salvar],[data-mp-tirar]").forEach(function (b) { b.disabled = false; });
          return;
        }
        aplicarMarca(t, x.j);
        t._mpMsg = (x.j.gravou ? x.j.efeito : "Nada mudou.") + (x.j.arquivo && x.j.arquivo.texto ? " " + x.j.arquivo.texto : "");
        abrir(i, abriu);
        delete t._mpMsg;
      })
      .catch(function () {
        msg.textContent = "O Nexus não respondeu: abra a janela de novo para conferir se gravou.";
        c.querySelectorAll("[data-mp-salvar],[data-mp-tirar]").forEach(function (b) { b.disabled = false; });
      });
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
      "<div><span>Criticidade</span><b>" + esc(t.cri || "—") + "</b></div>" +
      "<div><span>Semanas na fila</span><b class=\"" + (t.rol >= 3 ? "q-mal" : "") + "\">" + (t.rol || 1) + "ª semana</b></div>" +
      "<div><span>Reprogramada</span><b class=\"" + (t.rep ? "q-mal" : "") + "\">" + (t.rep ? "Sim" : "Não") + "</b></div></div>" +
      (t.pend && t.mot ? "<p class=\"q-nota\">Não coube na semana: " + esc(t.mot) + "</p>" : "") +
      "<div class=\"q-lado\"><section><h3>Onde</h3><dl>" + dl("Usina", t.uc) + dl("Cliente", t.cli) +
      dl("Equipe cluster", t.cl) + dl("Código do ativo", t.cod) + "</dl></section>" +
      "<section><h3>Quem</h3><dl>" + dl("Responsável O&M", t.resp) + dl("Responsável da OS", t.ros) + "</dl></section></div>" +
      "<h3>Quando</h3><dl>" + dl("Criada em", t.dcri) + dl("Dia nesta semana", t.d ? (t.d + (t.data ? " (" + t.data + ")" : "")) : "") +
      dl("Data no Fracttal", t.dprog) + dl("Janela", t.ini && t.fim ? t.ini + " – " + t.fim : t.ini) +
      dl("Duração prevista", t.h) + dl("Deslocamento", t.desl ? String(t.desl).replace(".", ",") + " h" : "") +
      dl("Finalizada em", t.dfim) + dl("Rolagem", t.rol_txt) + "</dl>" +
      blocoMotivo(t) +
      blocoReprogramar(t) +
      (t.pend ? "" : "<h3>Trajetória</h3>" + trajetoria(t)) +
      "<h3>Relatório de execução</h3>" + (t.rel ? "<p class=\"q-rel\">" + esc(t.rel) + "</p>"
        : "<p class=\"q-vazio\">Sem relatório registrado.</p>");
    var mpSalvar = c.querySelector("[data-mp-salvar]"), mpTirar = c.querySelector("[data-mp-tirar]");
    if (mpSalvar) mpSalvar.addEventListener("click", function () { enviarMotivo(i, t, c, false); });
    if (mpTirar) mpTirar.addEventListener("click", function () { enviarMotivo(i, t, c, true); });
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
    // "Tirar da semana" vale para o que está no "O que": a tarefa (o padrão é a do cartão) ou a OS inteira. Levi,
    // 15/10/2026: "quando o PCM tenta tirar da semana uma tarefa aparece uma notificação de tirar todas as tarefas da
    // OS, isso não pode acontecer". A OS que só tem esta tarefa na semana sai pelo "não".
    var tir = c.querySelector("[data-rp-tirar]");
    if (tir) tir.addEventListener("click", function () {
      var irmas = OSS[t.os] || [];
      var sel = c.querySelector("[data-rp-alvo]");
      var alvo = irmas.length > 1 ? (sel ? sel.value : t.t) : "";
      var r;
      if (!alvo) {
        if (!confirm(irmas.length > 1
            ? "Tirar a OS " + t.os + " INTEIRA da programação desta semana?\n\nSaem as " + irmas.length + " tarefas dela."
            : "Tirar da programação desta semana a OS " + t.os + "?\n\nEla só tem esta tarefa na semana.")) return;
        r = inserir(t.os, "", "não", "");
        if (r) { aviso("A OS " + t.os + " sai da semana · " + FILA.length + " na fila"); fechar(); }
        return;
      }
      // o robô e o motor acham a tarefa pelo NOME (contém a palavra): as de mesmo nome saem juntas, e o aviso diz quais
      var chave = nomeDaTarefa(alvo).toLowerCase();
      var esta = irmas.filter(function (x) { return x.t === alvo; })[0] || { n: 1 };
      var junto = irmas.filter(function (x) { return x.t !== alvo && x.t.toLowerCase().indexOf(chave) >= 0; });
      var fica = irmas.length - 1 - junto.length;
      if (!confirm("Tirar da programação desta semana só a tarefa\n“" + alvo + "”\nda OS " + t.os + "?" +
          ((esta.n || 1) > 1 ? "\n\nEla está em " + esta.n + " linhas da semana (uma por equipamento ou bloco): saem " +
            "todas, porque o arquivo do PCM separa a tarefa só pelo nome." : "") +
          (junto.length ? "\n\nSaem junto as de nome parecido: " + junto.map(function (x) { return "“" + x.t + "”"; }).join(", ") + "." : "") +
          "\n\n" + (fica === 0 ? "Com isso, nenhuma tarefa da OS fica na semana." : fica === 1
            ? "A outra tarefa da OS continua na semana." : "As outras " + fica + " tarefas da OS continuam na semana."))) return;
      r = inserir(t.os, alvo, "sem", "");
      if (r) { aviso("A tarefa sai da semana (OS " + t.os + ") · " + FILA.length + " na fila"); fechar(); }
    });
    pintarFila();
    if (!dlg.open) dlg.showModal();
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
    // o nome da pendente abre a janela da OS (o motivo também se marca na pendente; 16/10/2026)
    var nome = el.querySelector("[data-abrir]");
    if (nome && t) {
      var abreP = function () { abrir(+el.getAttribute("data-pend"), nome); };
      nome.addEventListener("click", abreP);
      nome.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); abreP(); } });
    }
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

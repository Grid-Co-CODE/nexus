/* os_creator/os_web/static/solic_ia.js — o Pedir com IA (15/11/2026). A conversa: a pessoa escolhe o setor e escreve; o
   servidor pede à IA, confere no catálogo e devolve a ficha (`/os/api/solic/ia/preencher`). A pessoa troca a usina, o ativo
   ou o tema na ficha sem gastar IA (`/os/api/solic/ia/ficha`) e cria pela rota de sempre do setor: a Nova solicitação do PCM
   ou a da Performance e da Engenharia. A conversa é uma janela de vidro por cima da Nova solicitação (Levi, 15/11/2026: "um
   pouco menor em formato de blur, a pessoa pode escolher fazer manualmente se quiser"): abre sozinha ao entrar na tela, o
   "Fazer manualmente" fecha e fica lembrado no navegador, e o botão "Pedir com IA" do alto reabre. */
(function () {
  "use strict";
  var raiz = document.getElementById("sia"), veu = document.getElementById("sia_veu");
  if (!raiz || !veu) return;
  var log = document.getElementById("sia_log"), form = document.getElementById("sia_form"),
      txt = document.getElementById("sia_txt"), btnEnviar = document.getElementById("sia_enviar"),
      estado = document.getElementById("sia_estado"), modelo = document.getElementById("sia_ficha");
  var TIPOS = JSON.parse(raiz.getAttribute("data-tipos-sub") || "{}");
  var setor = "", anterior = null, ficha = null, noFicha = null, ocupado = false, pessoas = {};
  var NOMES = {pcm: "PCM", performance: "Performance", engenharia: "Engenharia"};

  function esc(t) { return String(t == null ? "" : t).replace(/[&<>"]/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]; }); }
  function pedir(url, corpo) {
    return fetch(url, {method: "POST", credentials: "same-origin", headers: {"Content-Type": "application/json"},
                       body: JSON.stringify(corpo)})
      .then(function (r) { return r.json().catch(function () { return {erro: "Resposta que não deu para ler (" + r.status + ")."}; })
        .then(function (j) { if (r.status === 401 || j.login) j.erro = j.erro || "Sua sessão do Fracttal caiu: entre de novo."; return {ok: r.ok, j: j}; }); })
      .catch(function () { return {ok: false, j: {erro: "Sem conexão com o servidor."}}; });
  }
  function ler(url) {
    return fetch(url, {credentials: "same-origin"}).then(function (r) { return r.json(); }).catch(function () { return {}; });
  }
  function rolar() { log.scrollTop = log.scrollHeight; }
  function msg(quem, html, cls) {
    var d = document.createElement("div");
    d.className = "sia-msg sia-msg--" + quem + (cls ? " " + cls : "");
    d.innerHTML = '<span class="sia-quem">' + (quem === "eu" ? "você" : "nexus") + '</span><div class="sia-txt">' + html + "</div>";
    log.appendChild(d); rolar(); return d;
  }
  function marcarEstado(t) { estado.textContent = t; }

  // ── a janela: abrir, fechar e o "Fazer manualmente" ──
  var MANUAL = "siaManual", quemAbriu = null;
  function guardado() { try { return localStorage.getItem(MANUAL) === "1"; } catch (e) { return false; } }
  function guardar(v) { try { if (v) localStorage.setItem(MANUAL, "1"); else localStorage.removeItem(MANUAL); } catch (e) { /* sem localStorage */ } }
  function abrir(origem) {
    quemAbriu = origem || document.activeElement;
    veu.hidden = false; document.body.classList.add("sia-aberto");
    setTimeout(function () { txt.focus(); }, 30);
  }
  function fechar() {
    veu.hidden = true; document.body.classList.remove("sia-aberto");
    if (quemAbriu && quemAbriu.focus) quemAbriu.focus();
  }
  document.querySelectorAll("[data-sia-abrir]").forEach(function (b) {
    b.addEventListener("click", function () { guardar(false); abrir(b); });   // pediu a IA: volta a abrir sozinha
  });
  raiz.querySelectorAll("[data-sia-fechar]").forEach(function (b) { b.addEventListener("click", fechar); });
  raiz.querySelectorAll("[data-sia-manual]").forEach(function (b) { b.addEventListener("click", function () { guardar(true); fechar(); }); });
  veu.addEventListener("mousedown", function (e) { if (e.target === veu) fechar(); });       // o clique fora fecha
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !veu.hidden) fechar(); });

  // ── o setor ──
  function escolherSetor(s) {
    setor = s;
    raiz.querySelectorAll(".sia-setor").forEach(function (b) {
      var on = b.dataset.setor === s; b.classList.toggle("on", on); b.setAttribute("aria-checked", on ? "true" : "false");
    });
    txt.placeholder = "Pedir " + (s === "pcm" ? "ao" : "à") + " " + NOMES[s] + ": a OS, o ativo e o cliente…";
    if (ficha && ficha.setor !== s) { ficha.setor = s; refazer(); }
    if (!veu.hidden) txt.focus();
  }
  raiz.querySelectorAll(".sia-setor").forEach(function (b) { b.addEventListener("click", function () { escolherSetor(b.dataset.setor); }); });
  raiz.querySelectorAll(".sia-ex").forEach(function (b) { b.addEventListener("click", function () { txt.value = b.textContent; ajustar(); txt.focus(); }); });

  // ── o prompt ──
  function ajustar() { txt.style.height = "auto"; txt.style.height = Math.min(txt.scrollHeight, 180) + "px"; }
  txt.addEventListener("input", ajustar);
  txt.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit ? form.requestSubmit() : enviar(); }
  });
  form.addEventListener("submit", function (e) { e.preventDefault(); enviar(); });

  function enviar() {
    var t = txt.value.trim();
    if (!t || ocupado) return;
    if (!setor) { msg("ia", "<p>Antes, escolha para quem é o pedido: <b>PCM</b>, <b>Performance</b> ou <b>Engenharia</b>.</p>", "sia-msg--aviso"); return; }
    msg("eu", "<p>" + esc(t) + "</p>");
    txt.value = ""; ajustar();
    ocupado = true; btnEnviar.disabled = true; marcarEstado("pensando");
    var pensando = msg("ia", '<p class="sia-pensando">lendo o pedido, o catálogo e os temas<span class="sia-seg"></span><span class="sia-cursor"></span></p>');
    // os segundos correndo: a IA grátis às vezes demora, e a pessoa vê que o pedido está vivo (Levi, 15/11/2026: "demorando que só")
    var t0 = Date.now(), seg = pensando.querySelector(".sia-seg");
    var relogio = setInterval(function () { var n = Math.round((Date.now() - t0) / 1000); if (n >= 3) seg.textContent = " · " + n + " s"; }, 1000);
    pedir("/os/api/solic/ia/preencher", {setor: setor, texto: t, anterior: anterior}).then(function (x) {
      clearInterval(relogio); pensando.remove(); ocupado = false; btnEnviar.disabled = false;
      if (!x.ok || x.j.erro) { marcarEstado("erro"); msg("ia", '<p class="sia-aviso">' + esc(x.j.erro || "Não deu certo.") + "</p>", "sia-msg--aviso"); return; }
      marcarEstado("pronto");
      mostrar(x.j);
    });
  }

  // ── a ficha ──
  function opcoes(sel, lista, atual, vazio, valor, rotulo) {
    sel.innerHTML = '<option value="">' + esc(vazio) + "</option>" + (lista || []).map(function (o) {
      var v = valor ? valor(o) : o, r = rotulo ? rotulo(o) : o;
      return '<option value="' + esc(v) + '"' + (String(v) === String(atual) ? " selected" : "") + ">" + esc(r) + "</option>";
    }).join("");
  }
  // com o tipo escolhido o nome do tipo é o mesmo em todos: no lugar dele, o código do ativo (também se pesquisa por ele)
  function rotuloAtivo(a) {
    var resto = ficha && ficha.tipo ? a.code : a.tipo_nome;
    return (a.curto || a.label || a.code) + (resto ? " · " + resto : "");
  }

  var ultimaIA = null;              // o modelo que respondeu e em quanto tempo (a ficha refeita na tela não pede à IA)
  function mostrar(f) {
    ficha = f; anterior = f.anterior || null; ultimaIA = f.ia_info || null;
    if (noFicha) noFicha.classList.add("sia-ficha--velha");
    var corpo = msg("ia", "", "sia-msg--ficha").querySelector(".sia-txt");
    corpo.appendChild(modelo.content.cloneNode(true));
    noFicha = corpo.querySelector(".sia-ficha");
    pintar();
    var m = corpo.closest(".sia-msg");                 // a ficha do topo: é ela que a pessoa vai ler
    if (log.scrollHeight > log.clientHeight + 4) log.scrollTop = Math.max(0, m.offsetTop - log.offsetTop - 12);
    else m.scrollIntoView({block: "start"});           // no celular a conversa rola a página inteira
  }

  function pintar() {
    var f = ficha, el = noFicha, q = function (s) { return el.querySelector(s); };
    q(".sia-ficha-t").textContent = (f.setor === "pcm" ? "Solicitação ao PCM" : "OS da " + f.setor_nome);
    var m = ultimaIA && ultimaIA.modelo ? ultimaIA.modelo.split("/").pop().replace(/:free$/, "") : "";
    q(".sia-ficha-m").textContent = m ? m + (ultimaIA.segundos != null ? " · " + String(ultimaIA.segundos).replace(".", ",") + " s" : "") : "";
    var pill = q(".sia-pill");
    pill.textContent = f.pronta ? "pronta para conferir" : "falta informação";
    pill.className = "sia-pill " + (f.pronta ? "sia-pill--ok" : "sia-pill--alerta");
    var perg = q(".sia-perguntas");
    perg.hidden = !(f.perguntas || []).length;
    perg.innerHTML = (f.perguntas || []).map(function (p) { return "<p>" + esc(p) + "</p>"; }).join("")
      + ((f.perguntas || []).length ? '<p class="sia-dica">Responda aqui embaixo ou escolha na ficha.</p>' : "");
    var cli = q('[data-f="cliente"]'), usi = q('[data-f="usina"]'), ati = q('[data-f="ativo"]');
    opcoes(cli, uniq(f.clientes || []), f.cliente, "— qualquer cliente —");
    // a usina se pesquisa sem o cliente: sem ele, a lista é a de todos (pelo nome ou pelo código), e escolher traz o cliente
    var usinas = (f.usinas_todas || []).filter(function (x) { return !f.cliente || x.cliente === f.cliente; });
    opcoes(usi, usinas, f.usina, "— digite a usina ou o código —", function (x) { return x.usina; },
           function (x) { return x.usina + (x.codigo ? " · " + x.codigo : ""); });
    // o tipo de equipamento que o pedido disse filtra os ativos ("— todos os tipos —" mostra a usina inteira)
    opcoes(q('[data-f="tipo"]'), f.tipos || [], f.tipo, "— todos os tipos —", function (t) { return t.sigla; },
           function (t) { return t.nome + (f.usina ? " (" + t.n + ")" : ""); });
    // os mais parecidos com o que a pessoa disse vêm primeiro; depois, todos os ativos do tipo (ou da usina)
    var sug = (f.ativos_sugeridos || []), ids = {};
    sug.forEach(function (a) { ids[a.id] = 1; });
    opcoes(ati, sug.concat((f.ativos || []).filter(function (a) { return !ids[a.id]; })), f.ativo ? f.ativo.id : "",
           f.usina ? "— escolha o ativo —" : "— escolha a usina antes —", function (a) { return a.id; }, rotuloAtivo);
    q('[data-f="titulo"]').value = f.titulo || "";
    q('[data-f="descricao"]').value = f.descricao || "";
    opcoes(q('[data-f="tema"]'), f.temas || [], f.tema, f.ativo || f.tipo ? (f.temas && f.temas.length ? "— sem tema (as subtarefas da base) —" : "nenhum tema para este tipo de ativo") : "— escolha o ativo antes —",
           function (t) { return t.chave; }, function (t) { return t.nome; });
    q('[data-f="programada"]').textContent = f.programada || raiz.getAttribute("data-programada");
    var c1 = q("[data-so-pcm]");                        // a Classificação 1 é só da solicitação ao PCM
    c1.hidden = f.setor !== "pcm";
    if (f.setor === "pcm") opcoes(q('[data-f="classif1"]'), f.classif1_opcoes || [], (f.classif1 || {}).id || "", "— escolha o impacto —",
                                  function (o) { return o.id; }, function (o) { return o.txt; });
    var resp = q("[data-so-resp]");
    resp.hidden = !f.responsavel;
    if (f.responsavel) carregarResponsaveis(q('[data-f="responsavel"]'), f.setor);
    pintarSubs();
    q(".sia-criar").textContent = f.setor === "pcm" ? "Criar a solicitação" : "Criar a OS";
    validar();
    if (!el.dataset.ligada) ligar(el);
  }
  function uniq(l) { var v = {}; return (l || []).filter(function (x) { if (!x || v[x]) return false; v[x] = 1; return true; }); }

  function carregarResponsaveis(sel, s) {
    var guardada = sel.value;
    var pinta = function (lista) {
      opcoes(sel, lista, guardada || (ficha.id_responsavel || ""), lista.length ? "— escolha o responsável —" : "ninguém no setor",
             function (p) { return p.id_personnel; }, function (p) { return p.name; });
      validar();
    };
    if (pessoas[s]) { pinta(pessoas[s]); return; }
    ler("/os/api/solicitacao/" + s + "/responsaveis").then(function (j) { pessoas[s] = j.pessoas || []; pinta(pessoas[s]); });
  }

  function pintarSubs() {
    var l = noFicha.querySelector(".sia-subs-l"), subs = ficha.subtarefas || [];
    l.innerHTML = subs.map(function (s, i) {
      return '<li class="' + (s.da_ia ? "sia-sub--ia" : "") + '"><span class="sia-tipo">' + esc(TIPOS[s.tipo] || "Texto") + "</span>"
        + '<span class="sia-sub-d">' + esc(s.desc) + (s.anexo ? ' <small>(foto obrigatória)</small>' : "") + "</span>"
        + '<button type="button" class="sia-x" data-tira="' + i + '" aria-label="Tirar a subtarefa ' + (i + 1) + '">×</button></li>';
    }).join("");
    var n = subs.filter(function (s) { return s.da_ia; }).length;
    noFicha.querySelector(".sia-subs-h small").textContent = subs.length + (ficha.tema ? " do tema " + (ficha.tema_nome || "") : " da base")
      + (n ? ", " + n + " pedida(s) agora" : "");
  }

  function lerFicha() {
    var q = function (s) { return noFicha.querySelector(s); };
    var idAt = q('[data-f="ativo"]').value;
    var at = (ficha.ativos || []).filter(function (a) { return String(a.id) === String(idAt); })[0] || null;
    return {cliente: q('[data-f="cliente"]').value, usina: q('[data-f="usina"]').value, tipo: q('[data-f="tipo"]').value, ativo: at,
            titulo: q('[data-f="titulo"]').value.trim(), descricao: q('[data-f="descricao"]').value.trim(),
            tema: q('[data-f="tema"]').value, responsavel: (q('[data-f="responsavel"]') || {}).value || "",
            classif1_id: q('[data-f="classif1"]').value,
            classif1_txt: q('[data-f="classif1"]').selectedIndex > 0 ? q('[data-f="classif1"]').selectedOptions[0].text : ""};
  }

  function validar() {
    if (!noFicha) return;
    var v = lerFicha(), falta = [];
    if (!v.ativo) falta.push("o ativo");
    if (!v.titulo) falta.push("a atividade");
    if (!v.descricao) falta.push("o que fazer");
    if (ficha.responsavel && !v.responsavel) falta.push("o responsável");
    if (ficha.setor === "pcm" && !v.classif1_id) falta.push("a Classificação 1");
    noFicha.querySelector(".sia-criar").disabled = !!falta.length || ocupado;
    noFicha.querySelector(".sia-hint").textContent = falta.length ? "Falta " + falta.join(", ") + "." : "";
  }

  // trocar a usina, o ativo ou o tema refaz a ficha sem a IA (as subtarefas do tema e os temas do tipo novo)
  function refazer(mudou) {
    if (!noFicha) return;
    var v = lerFicha();
    var extras = (ficha.subtarefas || []).filter(function (s) { return s.da_ia; });
    // o que a pessoa marcou vale como está; trocar o cliente esvazia a usina e o ativo, trocar a usina esvazia o ativo
    // (o ativo e o tipo do pedido seguem: na usina nova, o "inversor 2.1" do pedido acha o dela). A usina escolhida sem o
    // cliente traz o cliente dela. O tipo só vai quando a pessoa o escolheu: senão ele sai do pedido
    if (mudou === "tipo") ficha.tipo_manual = true;
    var escolhidos = {cliente: v.cliente, usina: mudou === "cliente" ? "" : v.usina,
                      ativo_id: mudou === "cliente" || mudou === "usina" ? "" : (v.ativo ? v.ativo.id : ""),
                      classif1_id: ficha.c1_manual ? v.classif1_id : ""};
    if (ficha.tipo_manual) escolhidos.tipo = v.tipo;
    var guardaResp = v.responsavel, tipoManual = ficha.tipo_manual;
    pedir("/os/api/solic/ia/ficha", {setor: ficha.setor, escolhidos: escolhidos, titulo: v.titulo, descricao: v.descricao,
                                     tema: v.tema, extras: extras, classif1_atual: v.classif1_txt,
                                     ativo_pista: ficha.ativo_pista || "", tipo_pista: ficha.tipo_pista || ""}).then(function (x) {   // o tema fica se valer para o ativo novo
      if (!x.ok || x.j.erro) { noFicha.querySelector(".sia-hint").textContent = x.j.erro || "Não deu para refazer a ficha."; return; }
      var f = x.j;
      f.titulo = v.titulo || f.titulo; f.descricao = v.descricao || f.descricao;
      var manual = ficha.c1_manual;
      ficha = f; anterior = f.anterior || anterior; ficha.id_responsavel = guardaResp; ficha.c1_manual = manual;
      ficha.tipo_manual = tipoManual;
      pintar();
    });
  }

  function ligar(el) {
    el.dataset.ligada = "1";
    el.addEventListener("change", function (e) {
      if (el !== noFicha) return;
      var c = e.target.getAttribute("data-f");
      if (c === "cliente" || c === "usina" || c === "tipo" || c === "ativo" || c === "tema") refazer(c);
      else { if (c === "classif1") ficha.c1_manual = true; validar(); }   // a Classificação que a pessoa escolheu fica
    });
    el.addEventListener("input", function () { if (el === noFicha) validar(); });
    el.addEventListener("click", function (e) {
      if (el !== noFicha) return;
      var x = e.target.closest("[data-tira]");
      if (x) { ficha.subtarefas.splice(Number(x.dataset.tira), 1); pintarSubs(); return; }
      if (e.target.closest(".sia-subs-add button")) { acrescentar(); return; }
      if (e.target.closest(".sia-limpar")) { recomecar(); return; }
      if (e.target.closest(".sia-criar")) criar();
    });
    el.querySelector(".sia-subs-add input").addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); acrescentar(); }
    });
  }
  function acrescentar() {
    var inp = noFicha.querySelector(".sia-subs-add input"), d = inp.value.trim();
    if (!d) return;
    ficha.subtarefas.push({desc: d, tipo: "texto", anexo: false, da_ia: true});
    inp.value = ""; pintarSubs();
  }
  function recomecar() {
    ficha = null; anterior = null;
    if (noFicha) noFicha.classList.add("sia-ficha--velha");
    noFicha = null;
    msg("ia", "<p>Pode mandar o próximo pedido.</p>");
    txt.focus();
  }

  // ── criar, pela rota de sempre do setor ──
  function criar() {
    var v = lerFicha(), subs = (ficha.subtarefas || []).map(function (s) { return {desc: s.desc, tipo: s.tipo, anexo: !!s.anexo}; });
    var url, corpo;
    if (ficha.setor === "pcm") {
      url = "/os/api/solic/criar";
      corpo = {ativos: [v.ativo.code], descricao: v.titulo, observacao: v.descricao, classif1: Number(v.classif1_id),
               classif1_txt: v.classif1_txt, data_sugerida: ficha.programada_iso, tema: v.tema, subtarefas: subs,
               urgente: false, tecnico: ""};
    } else {
      url = "/os/api/solicitacao/" + ficha.setor + "/criar";
      corpo = {ativos: [v.ativo.id], descricao: v.titulo, problema: v.descricao, responsavel: {id_personnel: v.responsavel},
               subtarefas: subs, origem: "ia"};
    }
    var b = noFicha.querySelector(".sia-criar");
    b.disabled = true; ocupado = true; marcarEstado("criando");
    noFicha.querySelector(".sia-hint").textContent = "criando no Fracttal…";
    pedir(url, corpo).then(function (x) {
      ocupado = false;
      var m = x.j.mensagem || x.j.erro || "";
      if (!x.ok || x.j.erro || x.j.ok === 0 || x.j.ok === false) {
        marcarEstado("erro"); b.disabled = false;
        noFicha.querySelector(".sia-hint").textContent = "";
        msg("ia", '<p class="sia-aviso">' + esc(m || "Não deu para criar.") + "</p>", "sia-msg--aviso");
        return;
      }
      marcarEstado("pronto");
      noFicha.classList.add("sia-ficha--feita");
      noFicha.querySelector(".sia-hint").textContent = "";
      msg("ia", '<p class="sia-ok">' + esc(m) + "</p><p>Pode mandar o próximo pedido.</p>");
      ficha = null; anterior = null; noFicha = null;
    });
  }
  // o setor da tela em que a janela abriu (PCM, Engenharia ou Performance), e ela abre sozinha, a não ser que a pessoa tenha
  // escolhido fazer manualmente; o cartão do Início chega com ?ia=1 e abre sempre
  var ini = raiz.getAttribute("data-setor-inicial");
  if (NOMES[ini]) escolherSetor(ini);
  if (new URLSearchParams(location.search).get("ia") === "1" || !guardado()) abrir();
})();

/* Comando > Contratos (18/11/2026): a visão do contrato, editável pelo gestor do contrato e pelo administrador, com
   histórico. Os dados vêm do /t/comando/contratos/dados.json (a carga inicial mais as mudanças, nexus/contratos/edicao.py);
   nada de contrato mora neste arquivo (o repositório é público).

   Levi, 18/11/2026: "Eu quero que essas informações sejam editáveis [...] Só gestores de contrato ou administradores
   podem editar, e tudo com histórico. Nesse histórico deve ter quem mudou, o que mudou, quando mudou, o motivo porque
   mudou, anexar alguma coisa [...] um e-mail, uma mensagem, algo" (o anexo é obrigatório: arquivo ou o texto colado) e
   "deixar muita informação em cima [...] rouba metade do espaço da tela [...] Arrume isso" (o topo é uma linha).
   De antes, e que ficam: a lista do Nexus na troca de contrato, a linha do cliente que abre o contrato com o Voltar, o
   contrato e a aba no endereço (17/11/2026); as regras lidas dos PDFs com o trecho e a página (18/11/2026). */
(function () {
  "use strict";
  var raiz = document.getElementById("ctr-main");
  if (!raiz) return;
  var dlg = document.getElementById("ctr-dlg");
  // o caminho passa pelo nexusRota (o prefixo em que o Nexus roda); o nexusPedir não dobra o prefixo
  var CAMINHO = window.nexusRota("/t/comando/contratos/");
  var R = null, HIST = {}, regraAberta = {}, aberta = null, ultimaAba = "", ultimoCt = null;
  var estado = {ct: -1, aba: "regras", grupos: {}, soAditivo: false};
  var ABAS = [["regras", "Regras"], ["calendario", "Calendário"], ["atendimento", "Atendimento"], ["entregaveis", "Entregáveis"],
    ["metas", "Metas"], ["financeiro", "Financeiro"], ["historico", "Histórico"]];
  var CATS = ["SLA", "Entregáveis", "Rotinas", "Disponibilidade e desempenho", "Penalidades", "Benefícios", "Medição e faturamento",
    "Adicionais e hora extra", "Rescisão", "Seguros e documentação", "Outras obrigações"];
  var MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];

  /* ── utilidades ─────────────────────────────────────────────────────────────────────────────────────────────────── */
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]; }); }
  function brl(v) { return Number(v).toLocaleString("pt-BR", {style: "currency", currency: "BRL"}); }
  function pct(v, casas) { return Number(v).toLocaleString("pt-BR", {minimumFractionDigits: casas == null ? 1 : casas, maximumFractionDigits: casas == null ? 1 : casas}); }
  function dBR(iso) { if (!iso) return ""; var p = String(iso).slice(0, 10).split("-"); return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : String(iso); }
  function nDias(n) { n = Math.abs(n); return n + (n === 1 ? " dia" : " dias"); }
  function quando(n) { return n == null ? "" : n < 0 ? "há " + nDias(n) : n === 0 ? "hoje" : "em " + nDias(n); }
  function falta(n) { var m = Math.floor(n / 30.44); return m >= 2 ? "faltam " + m + " meses" : "faltam " + nDias(n); }
  function seguro(url) { return /^https:\/\/[a-z0-9.-]+\.sharepoint\.com\//i.test(url || "") ? url : ""; }
  function par(rot, html) { return "<div><dt>" + rot + "</dt><dd>" + html + "</dd></div>"; }
  function semAcento(t) { return String(t).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim(); }
  function toast(t) {
    var el = document.createElement("div"); el.className = "ctr-toast"; el.setAttribute("role", "status"); el.textContent = t;
    document.body.appendChild(el); setTimeout(function () { el.remove(); }, 3500);
  }
  function seg(rotulo, atributo, atual, opcoes) {
    return '<span class="ctr-seg" role="group" aria-label="' + rotulo + '">' + opcoes.map(function (o) {
      return "<button " + atributo + '="' + o[0] + '" aria-pressed="' + (atual === o[0]) + '">' + o[1] + (o[2] != null ? "<b>" + o[2] + "</b>" : "") + "</button>";
    }).join("") + "</span>";
  }
  function pedir(caminho, opcoes) {
    if (typeof window.nexusPedir === "function") return window.nexusPedir(caminho, opcoes);
    return fetch(caminho, Object.assign({credentials: "same-origin"}, opcoes || {})).then(function (r) { return r.json(); });
  }

  /* ── o endereço: #/c/<cliente>/<aba>; "#/" é Todos os contratos ─────────────────────────────────────────────────── */
  function rota(ct, aba) { return ct >= 0 ? "#/c/" + encodeURIComponent(R.contratos[ct].cliente) + "/" + (aba || "regras") : "#/"; }
  function irPara(ct) { var novo = rota(ct, ct === estado.ct ? estado.aba : "regras"); if (location.hash === novo) render(); else location.hash = novo; }
  function lerEndereco() {
    var r = (location.hash || "").replace(/^#\/?/, "").split("/"), ct = -1, aba = "regras";
    if (r[0] === "c") {
      var k = decodeURIComponent(r[1] || "");
      for (var i = 0; i < R.contratos.length; i++) if (R.contratos[i].cliente === k) { ct = i; break; }
      aba = r[2];
    }
    estado.ct = ct;
    estado.aba = ABAS.some(function (a) { return a[0] === aba; }) ? aba : "regras";
  }

  /* ── a troca de contrato (a lista do Nexus) ─────────────────────────────────────────────────────────────────────── */
  function escolha(opcoes, atual) {
    var cur = opcoes.filter(function (o) { return o.i === atual; })[0] || opcoes[0], longa = opcoes.length > 8;
    return '<div class="ctr-escolha" data-escolha><button type="button" class="ctr-escolha-btn" aria-haspopup="listbox" aria-expanded="false" aria-controls="ctr-lista" aria-label="Contrato: ' + esc(cur.nome) + '. Trocar de contrato">' +
      "<span>" + esc(cur.nome) + '</span><i class="ph ph-caret-down" aria-hidden="true"></i></button>' +
      '<div class="ctr-pop" hidden>' + (longa ? '<label class="ctr-busca"><i class="ph ph-magnifying-glass" aria-hidden="true"></i><span class="so-leitor">Buscar cliente</span>' +
        '<input type="search" placeholder="Buscar cliente" autocomplete="off" role="combobox" aria-expanded="true" aria-controls="ctr-lista" aria-autocomplete="list"></label>' : "") +
      '<ul class="ctr-lista" id="ctr-lista" role="listbox" aria-label="Contratos" tabindex="-1">' + opcoes.map(function (o) {
        return '<li role="option" id="ctr-op-' + (o.i + 1) + '" data-ir="' + o.i + '"' + (o.i < 0 ? ' class="ctr-todos"' : "") + (o.i === atual ? ' aria-selected="true"' : "") + "><b>" + esc(o.nome) + "</b>" +
          (o.sub ? "<small>" + esc(o.sub) + "</small>" : "") + (o.atraso ? '<span class="ctr-pill t-critico" title="' + o.atraso + ' em atraso">' + o.atraso + "</span>" : "") + "</li>";
      }).join("") + '<li class="ctr-nada" role="presentation" hidden>Nenhum cliente com esse nome</li></ul></div></div>';
  }
  function abreEscolha(el) {
    var botao = el.querySelector(".ctr-escolha-btn"), pop = el.querySelector(".ctr-pop");
    aberta = {raiz: el, botao: botao, pop: pop, campo: pop.querySelector("input"), itens: [].slice.call(pop.querySelectorAll('li[role="option"]')), marcada: -1};
    pop.hidden = false; botao.setAttribute("aria-expanded", "true");
    var sel = aberta.itens.findIndex(function (li) { return li.getAttribute("aria-selected") === "true"; });
    if (aberta.campo) { aberta.campo.value = ""; filtraEscolha(); aberta.campo.focus(); } else pop.querySelector(".ctr-lista").focus();
    marcaEscolha(sel < 0 ? 0 : sel, true);
  }
  function fechaEscolha(devolve) {
    if (!aberta) return;
    aberta.pop.hidden = true; aberta.botao.setAttribute("aria-expanded", "false");
    if (devolve) aberta.botao.focus();
    aberta = null;
  }
  function visiveis() { return aberta.itens.filter(function (li) { return !li.hidden; }); }
  function marcaEscolha(k, absoluto) {
    var vs = absoluto ? aberta.itens : visiveis(), alvo = aberta.campo || aberta.pop.querySelector(".ctr-lista");
    aberta.itens.forEach(function (li) { li.classList.remove("marcada"); });
    if (!vs.length) { aberta.marcada = -1; alvo.removeAttribute("aria-activedescendant"); return; }
    var li = vs[Math.max(0, Math.min(k, vs.length - 1))];
    aberta.marcada = visiveis().indexOf(li);
    li.classList.add("marcada"); li.scrollIntoView({block: "nearest"}); alvo.setAttribute("aria-activedescendant", li.id);
  }
  function filtraEscolha() {
    var q = semAcento(aberta.campo.value), n = 0;
    aberta.itens.forEach(function (li) { li.hidden = q !== "" && semAcento(li.textContent).indexOf(q) < 0; if (!li.hidden) n += 1; });
    aberta.pop.querySelector(".ctr-nada").hidden = n > 0;
    marcaEscolha(0);
  }
  document.addEventListener("keydown", function (ev) {
    if (!aberta) return;
    if (ev.key === "ArrowDown") { ev.preventDefault(); marcaEscolha(aberta.marcada + 1); }
    else if (ev.key === "ArrowUp") { ev.preventDefault(); marcaEscolha(aberta.marcada - 1); }
    else if (ev.key === "Enter") { ev.preventDefault(); var li = visiveis()[aberta.marcada]; if (li) { fechaEscolha(false); irPara(+li.getAttribute("data-ir")); } }
    else if (ev.key === "Escape") { ev.preventDefault(); fechaEscolha(true); }
    else if (ev.key === "Tab") fechaEscolha(false);
  });
  document.addEventListener("mousedown", function (ev) { if (aberta && !aberta.raiz.contains(ev.target)) fechaEscolha(false); });

  /* ── os dados de cada contrato ──────────────────────────────────────────────────────────────────────────────────── */
  function obrDe(c) { return R.obrigacoes.filter(function (o) { return o.cliente === c.cliente; }); }
  function adicDe(c) { return R.adicionais.filter(function (a) { return a.cliente === c.cliente; }); }
  function fichaDe(c) { return (R.fichas || {})[c.cliente] || null; }
  function vencido(c) { return (c.dias_fim != null && c.dias_fim < 0) || (c.dias_fim == null || c.dias_fim >= 0) && c.dias_aviso != null && c.dias_aviso < 0; }
  function pode(c) { return !!(c && c.pode_editar); }
  // o lápis: só para quem edita; o que ele abre vai nos data-
  function lapis(c, tipo, ids, rotulo, extra) {
    if (tipo === "parametros" ? !R.admin : !pode(c)) return "";
    return '<button type="button" class="ctr-lapis" data-ed-tipo="' + tipo + '" data-ed-ids="' + esc((ids || []).join(",")) + '"' +
      (c ? ' data-ed-cliente="' + esc(c.cliente) + '"' : "") + (extra || "") + ' title="' + esc(rotulo) + '"><i class="ph ph-pencil-simple" aria-hidden="true"></i>' +
      '<span class="so-leitor">' + esc(rotulo) + "</span></button>";
  }
  function novo(c, tipo, rotulo, preset) {
    if (!pode(c)) return "";
    return '<tr class="mais"><td colspan="20"><button type="button" data-ed-tipo="' + tipo + '" data-ed-novo="1" data-ed-cliente="' + esc(c.cliente) + '"' +
      (preset ? " data-ed-preset='" + esc(JSON.stringify(preset)) + "'" : "") + '><i class="ph ph-plus" aria-hidden="true"></i>' + rotulo + "</button></td></tr>";
  }
  // a marca do campo editado: quem e quando (o resto está no Histórico)
  function editado(item, campos) {
    var e = (item && item._editado) || {}, m = null;
    campos.forEach(function (k) { if (e[k]) m = e[k]; });
    if (!m && item && item._incluido) m = item._incluido;
    return m ? '<span class="ctr-editado" title="' + esc((item && item._incluido && !e[campos[0]] ? "Incluído" : "Editado") + " por " + m.quem + " em " + m.quando) + '">editado</span>' : "";
  }
  // o dado que a planilha não tinha e veio do contrato lido
  function doContrato(c, campos) {
    var o = c.origem || {}, x = campos.map(function (k) { return o[k]; }).filter(Boolean)[0];
    if (!x) return "";
    var t = "Do contrato " + (x.contrato || "") + (x.ref ? ", " + (x.ref.clausula ? "cl. " + x.ref.clausula + ", " : "") + "p. " + x.ref.pagina : "") +
      (x.total > 1 ? " (" + x.de + " de " + x.total + " contratos trazem)" : "");
    return ' <span class="ctr-pill t-info" title="' + esc(t) + '">do contrato</span>';
  }

  /* ── a linha de fatos ───────────────────────────────────────────────────────────────────────────────────────────── */
  function fatoVig(c) {
    if (!c.fim) return par("Vigência", '<span class="vazio-c">sem data</span>');
    return '<div><dt>Vigência</dt><dd' + (c.dias_fim < 0 ? ' class="c-critico"' : "") + '>até <span class="num">' + dBR(c.fim) + "</span>" + doContrato(c, ["fim"]) + editado(c, ["fim"]) +
      "<small>" + (c.dias_fim < 0 ? "vencida há " + nDias(c.dias_fim) : falta(c.dias_fim)) + "</small></dd></div>";
  }
  function fatoRenov(c) {
    if (!c.avisar_ate) return par("Renovação", '<span class="vazio-c">' + (c.fim ? "sem aviso prévio" : "sem prazo") + "</span>");
    return '<div><dt>Renovação</dt><dd' + (c.dias_aviso < 0 ? ' class="c-critico"' : "") + '>avisar até <span class="num">' + dBR(c.avisar_ate) + "</span>" + doContrato(c, ["aviso_dias", "fim"]) +
      editado(c, ["aviso_dias"]) + "<small>" + (c.dias_aviso < 0 ? "passou há " + nDias(c.dias_aviso) : quando(c.dias_aviso)) + "</small></dd></div>";
  }
  function fatoReaj(c) {
    if (!c.proximo_reajuste) return par("Reajuste", '<span class="vazio-c">' + esc(c.indice || "sem data-base") + "</span>");
    return par("Próximo reajuste", '<span class="num">' + dBR(c.proximo_reajuste) + "</span>" + doContrato(c, ["data_base", "indice"]) + editado(c, ["data_base", "indice"]) +
      "<small>" + quando(c.dias_reajuste) + (c.indice ? "; " + esc(String(c.indice).slice(0, 40)) : "") + "</small>");
  }
  function fatoValor(c) {
    if (c.valor_mensal == null) return "";
    var i = c.valor_info || {};
    return par("Valor mensal", '<span class="num">' + brl(c.valor_mensal) + '</span> <span class="ctr-pill t-info" title="Somado dos contratos lidos dos PDFs">do contrato</span><small>' +
      (i.contratos > 1 ? (i.com_valor < i.contratos ? i.com_valor + " de " + i.contratos + " contratos" : i.contratos + " contratos") : "1 contrato") + (i.minuta ? ", com minuta" : "") + "</small>");
  }
  function atrasoDe(c) { return obrDe(c).filter(function (o) { return o.tom === "critico"; }).length + (vencido(c) ? 1 : 0); }

  /* ── Todos os contratos ─────────────────────────────────────────────────────────────────────────────────────────── */
  function opcoes() {
    var ops = R.contratos.map(function (k, i) { return {i: i, nome: k.cliente, sub: k.gestor ? "Gestor: " + k.gestor : "sem gestor", atraso: k.atrasadas}; })
      .sort(function (a, b) { return a.nome.localeCompare(b.nome, "pt-BR"); });
    ops.unshift({i: -1, nome: "Todos os contratos", sub: R.contratos.length + " contratos"});
    return ops;
  }
  function vTodos() {
    var ordem = R.contratos.map(function (c, i) { return {c: c, i: i}; }).sort(function (a, b) {
      function k(c) { return vencido(c) ? 0 : c.atrasadas ? 1 : c.proxima_data ? 2 : 3; }
      return k(a.c) - k(b.c) || String(a.c.proxima_data || "9").localeCompare(String(b.c.proxima_data || "9")) || a.c.cliente.localeCompare(b.c.cliente);
    });
    var venc = R.contratos.filter(function (c) { return c.dias_fim != null && c.dias_fim < 0; }).length;
    var comAtr = R.contratos.filter(function (c) { return c.atrasadas; }).length;
    function data(iso, dias, rot) {
      if (!iso) return '<span class="mudo">' + rot + "</span>";
      return '<span class="num' + (dias < 0 ? " c-critico" : "") + '">' + dBR(iso) + '</span><small class="mudo"> ' + quando(dias) + "</small>";
    }
    return '<div class="ctr-topo">' + escolha(opcoes(), -1) + '<span class="ctr-resumo">' + R.contratos.length + " contratos; " + venc + " com a vigência vencida; " + comAtr + " com obrigação em atraso</span></div>" +
      '<div class="ctr-rol" style="margin-top:10px"><table class="ctr-tab"><thead><tr><th>Cliente</th><th>Gestor do contrato</th><th>Vigência até</th><th>Renovação: avisar até</th><th>Próximo reajuste</th>' +
      '<th class="r">Valor mensal</th><th class="r">Em atraso</th><th class="r">Regras</th><th class="ir"><span class="so-leitor">Abrir</span></th></tr></thead><tbody>' +
      ordem.map(function (x) {
        var c = x.c, f = fichaDe(c), nr = f ? f.contratos.reduce(function (s, k) { return s + (k.regras || []).length; }, 0) : 0;
        return '<tr data-ir="' + x.i + '"><td><a href="' + rota(x.i) + '">' + esc(c.cliente) + "</a></td>" +
          "<td>" + (c.gestor ? esc(c.gestor) : '<span class="mudo">sem gestor</span>') + "</td>" +
          "<td>" + data(c.fim, c.dias_fim, "sem data") + doContrato(c, ["fim"]) + "</td>" +
          "<td>" + data(c.avisar_ate, c.dias_aviso, c.fim ? "sem aviso prévio" : "—") + doContrato(c, ["aviso_dias"]) + "</td>" +
          "<td>" + (c.proximo_reajuste ? data(c.proximo_reajuste, c.dias_reajuste) : '<span class="mudo">' + esc(String(c.indice || "sem índice").slice(0, 40)) + "</span>") + "</td>" +
          '<td class="r num">' + (c.valor_mensal != null ? brl(c.valor_mensal) : '<span class="mudo">—</span>') + "</td>" +
          '<td class="r">' + (c.atrasadas ? '<span class="ctr-pill t-critico">' + c.atrasadas + "</span>" : '<span class="mudo">0</span>') + "</td>" +
          '<td class="r">' + (nr ? '<span class="num">' + nr + "</span>" : '<span class="mudo">PDF não lido</span>') + "</td>" +
          '<td class="ir"><i class="ph ph-caret-right" aria-hidden="true"></i></td></tr>';
      }).join("") + "</tbody></table></div>";
  }

  /* ── um contrato: o topo numa linha, os fatos, as abas ──────────────────────────────────────────────────────────── */
  function vCliente(c) {
    var n = atrasoDe(c), atr = obrDe(c).filter(function (o) { return o.tom === "critico"; }).length;
    var h = '<div class="ctr-topo"><a class="ctr-voltar" href="#/"><i class="ph ph-arrow-left" aria-hidden="true"></i>Todos</a>' + escolha(opcoes(), estado.ct) +
      (c.gestor ? '<span class="ctr-gestor"><i class="ph ph-user-circle" aria-hidden="true"></i><small>Gestor</small>' + esc(c.gestor) +
        (c.gestor_como === "sem ligação" && R.admin ? ' <span class="ctr-pill t-alerta" title="O nome da planilha não casa com uma pessoa do Nexus: ligue em Editar dados">sem ligação</span>' : "") + "</span>" :
        '<span class="ctr-gestor mudo">sem gestor</span>') +
      '<span class="ctr-acoes">' + (pode(c) ? '<button type="button" class="ctr-lapis" data-ed-tipo="cliente" data-ed-ids="' + esc(c.id) + '" data-ed-cliente="' + esc(c.cliente) + '"><i class="ph ph-pencil-simple" aria-hidden="true"></i>Editar dados</button>' : "") + "</span></div>";
    h += '<dl class="ctr-fatos">' + fatoVig(c) + fatoRenov(c) + fatoReaj(c) + fatoValor(c) + par("Usinas", '<span class="num">' + (c.usinas || []).length + "</span>") +
      (n ? '<div><a class="ctr-atraso" href="' + rota(estado.ct, atr ? "calendario" : "regras") + '"><i class="ctr-ponto p-critico" aria-hidden="true"></i>' + n + " em atraso</a></div>" : "") + "</dl>";
    h += '<nav class="ctr-abas" aria-label="Partes do contrato">' + ABAS.map(function (a) {
      return '<a href="' + rota(estado.ct, a[0]) + '"' + (estado.aba === a[0] ? ' aria-current="page"' : "") + ">" + a[1] +
        (a[0] === "calendario" && atr ? "<b>" + atr + "</b>" : "") + "</a>";
    }).join("") + "</nav>";
    var f = {regras: rRegras, calendario: rCalendario, atendimento: rAtendimento, entregaveis: rEntregaveis, metas: rMetas, financeiro: rFinanceiro, historico: rHistorico}[estado.aba];
    return h + f(c);
  }

  /* ── as regras do contrato (lidas dos PDFs; incluídas e editadas aqui) ──────────────────────────────────────────── */
  function rotuloK(k) {
    var us = (k.usinas || []).map(function (u) { return u.nome; }).filter(Boolean);
    return k.id ? String(k.id) : us.length ? us.slice(0, 2).join(", ") + (us.length > 2 ? " e mais " + (us.length - 2) : "") : (k.arquivo || "");
  }
  function refTxt(ref) {
    if (!ref) return "";
    return (ref.clausula ? "cl. " + esc(ref.clausula) + ", " : "") + (ref.pagina ? "p. " + esc(ref.pagina) + (ref.pagina_fim && ref.pagina_fim !== ref.pagina ? "–" + esc(ref.pagina_fim) : "") : "");
  }
  function vale(r) { return r.vigente != null && r.vigente !== "" ? r.vigente : r.contratual; }
  function grupos(f, cats, soAditivo) {
    var g = [], por = {};
    f.contratos.forEach(function (k) {
      (k.regras || []).forEach(function (r) {
        if (cats.indexOf(r.categoria) < 0 || (soAditivo && !r.alterado_por)) return;
        var ch = r.categoria + "|" + String(r.nome || "").toLowerCase() + "|" + String(vale(r) || "").toLowerCase();
        if (!por[ch]) { por[ch] = {ch: ch, r: r, ks: []}; g.push(por[ch]); }
        por[ch].ks.push({k: k, r: r});
      });
    });
    return g;
  }
  function tabelaRegras(c, f, lista) {
    var varios = f.contratos.filter(function (k) { return k._id !== "geral"; }).length > 1;
    return '<div class="ctr-rol"><table class="ctr-tab"><thead><tr><th>Regra</th><th>Vale hoje</th>' + (varios ? "<th>Contratos</th>" : "") + "<th>Onde</th></tr></thead><tbody>" +
      lista.map(function (x) {
        var r = x.r, id = c.cliente + "|" + x.ch, ab = !!regraAberta[id], ids = x.ks.map(function (y) { return y.r._id; });
        var quais = !varios ? "" : x.ks.length === f.contratos.length ? "todos" : x.ks.map(function (y) { return esc(rotuloK(y.k)); }).join("; ");
        var h = '<tr class="rg" data-rg="' + esc(id) + '" aria-expanded="' + ab + '"><td><span class="nome">' + esc(r.nome) + "</span>" + editado(r, ["nome", "vigente", "categoria", "setor"]) +
          (r.setor ? '<span class="sub">' + esc(r.setor) + "</span>" : "") + "</td><td>" + (vale(r) ? esc(vale(r)) : '<span class="vazio-c">não escrito</span>') +
          (r.alterado_por ? '<span class="antes">antes: <s>' + esc(r.contratual || "não previsto") + "</s>; mudou no " + esc(r.alterado_por.arquivo || "aditivo") + "</span>" : "") + "</td>" +
          (varios ? '<td class="sub" style="margin:0">' + quais + "</td>" : "") + '<td class="onde">' + (r.ref ? refTxt(r.ref) : r._incluido ? "incluída no Nexus" : "") +
          (x.ks.length > 1 ? " e mais " + (x.ks.length - 1) : "") + "</td></tr>";
        if (ab) {
          h += '<tr class="rg-det"><td colspan="' + (varios ? 4 : 3) + '">' + x.ks.map(function (y) {
            var rr = y.r, a = rr.alterado_por;
            return (varios ? '<b class="sub" style="margin:4px 0">' + esc(rotuloK(y.k)) + "</b>" : "") +
              (rr.trecho ? '<p class="trecho">“' + esc(rr.trecho) + "”<small>" + esc((rr.ref || {}).arquivo || "") + ", " + refTxt(rr.ref) + "</small></p>" : "") +
              (a && a.trecho ? '<p class="trecho">“' + esc(a.trecho) + "”<small>" + esc(a.arquivo || "") + ", " + refTxt(a) + (a.resumo ? ". " + esc(a.resumo) : "") + "</small></p>" : "");
          }).join("") + (pode(c) ? '<p style="margin:6px 0 2px">' + lapis(c, "regra", ids, "Editar esta regra").replace("</button>", "Editar</button>") + "</p>" : "") + "</td></tr>";
        }
        return h;
      }).join("") + "</tbody></table></div>";
  }
  function blocoContrato(c, cats, titulo) {
    var f = fichaDe(c);
    if (!f) return "";
    var g = grupos(f, cats, false);
    if (!g.length) return '<div class="ctr-bloco"><h3>' + titulo + '</h3><p class="mudo">O contrato não traz regra disso.</p></div>';
    return '<div class="ctr-bloco"><h3>' + titulo + ' <span class="ctr-fonte">' + g.length + (g.length === 1 ? " regra" : " regras") + "; a linha abre o trecho do contrato</span></h3>" + tabelaRegras(c, f, g) + "</div>";
  }
  function divergencias(c, f) {
    function sem(t) { return semAcento(t == null ? "" : t); }
    var linhas = [];
    f.contratos.forEach(function (k) {
      if (k._id === "geral") return;
      var nome = f.contratos.length > 1 ? " (" + esc(rotuloK(k)) + ")" : "";
      var fim = (k.vigencia || {}).fim, aviso = (k.renovacao || {}).aviso_previo_dias, ind = (k.reajuste || {}).indice;
      if (fim && fim !== c.fim) linhas.push(["Fim da vigência" + nome, c.fim ? dBR(c.fim) : "não traz", dBR(fim), (k.vigencia || {}).ref]);
      if (aviso != null && aviso !== c.aviso_dias) linhas.push(["Aviso prévio de renovação" + nome, c.aviso_dias != null ? c.aviso_dias + " dias" : "não traz", aviso + " dias", (k.renovacao || {}).ref]);
      if (ind && sem(c.indice).indexOf(sem(ind)) < 0 && sem(ind).indexOf(sem(c.indice) || "@") < 0) linhas.push(["Índice de reajuste" + nome, c.indice ? esc(c.indice) : "não traz", esc(ind), (k.reajuste || {}).ref]);
    });
    if (!linhas.length) return "";
    return '<div class="ctr-bloco"><h3>Os dados do contrato e o PDF não batem <span class="ctr-fonte">' + linhas.length + (linhas.length === 1 ? " ponto" : " pontos") + " para acertar em Editar dados</span></h3>" +
      '<div class="ctr-rol"><table class="ctr-tab"><thead><tr><th>Item</th><th>Os dados do contrato dizem</th><th>O PDF diz</th><th>Onde</th></tr></thead><tbody>' +
      linhas.map(function (l) { return "<tr><td>" + l[0] + "</td><td>" + l[1] + '</td><td class="c-alerta">' + l[2] + '</td><td class="onde">' + refTxt(l[3]) + "</td></tr>"; }).join("") + "</tbody></table></div></div>";
  }
  function dadosDoContrato(c) {
    var linhas = [["Contrato", c.referencia || ""], ["Vigência", c.inicio || c.fim ? (c.inicio ? dBR(c.inicio) : "sem início") + " a " + (c.fim ? dBR(c.fim) : "sem fim") : ""],
      ["Aviso prévio de renovação", c.aviso_dias != null ? c.aviso_dias + " dias antes do fim" : ""], ["Reajuste", (c.indice || "") + (c.data_base ? "; data-base " + dBR(c.data_base) : "")],
      ["SLA de atendimento", c.sla || ""], ["Observações", c.observacoes || ""]];
    return '<div class="ctr-bloco"><h3>Dados do contrato ' + lapis(c, "cliente", [c.id], "Editar os dados do contrato") + '</h3><div class="ctr-rol"><table class="ctr-tab"><tbody>' + linhas.map(function (l) {
      return '<tr><td style="width:220px" class="mudo">' + l[0] + "</td><td>" + (l[1] ? esc(l[1]) : '<span class="vazio-c">não informado</span>') + "</td></tr>";
    }).join("") + (seguro(c.pasta) ? '<tr><td class="mudo">Pasta do contrato</td><td><a href="' + esc(seguro(c.pasta)) + '" target="_blank" rel="noopener">Abrir no SharePoint</a></td></tr>' : "") + "</tbody></table></div></div>";
  }
  function rRegras(c) {
    var f = fichaDe(c), h = "";
    if (f) {
      var alteradas = 0;
      f.contratos.forEach(function (k) { (k.regras || []).forEach(function (r) { if (r.alterado_por) alteradas++; }); });
      h += '<div class="ctr-regua"><span class="ctr-fonte">' + f.contratos.reduce(function (s, k) { return s + (k.regras || []).length; }, 0) + " regras, lidas dos PDFs e editadas aqui; a linha abre o trecho e a página</span>" +
        (alteradas ? seg("Quais regras", "data-regras", estado.soAditivo ? "aditivo" : "todas", [["todas", "Todas"], ["aditivo", "Mudadas por aditivo", alteradas]]) : "") + "</div>";
      h += '<div class="ctr-rol"><table class="ctr-tab"><tbody>';
      CATS.forEach(function (cat) {
        var g = grupos(f, [cat], estado.soAditivo);
        if (!g.length) return;
        var ab = estado.soAditivo || !!estado.grupos[cat], mud = g.filter(function (x) { return x.r.alterado_por; }).length;
        h += '<tr class="grupo"><td><button data-grupo="' + esc(cat) + '" aria-expanded="' + ab + '"><i class="ph ph-caret-' + (ab ? "down" : "right") + '" aria-hidden="true"></i>' + esc(cat) +
          '<span class="g-n">' + g.length + (g.length === 1 ? " regra" : " regras") + (mud ? ", " + mud + " por aditivo" : "") + "</span></button></td></tr>";
        if (ab) h += '<tr><td style="padding:0">' + tabelaRegras(c, f, g) + "</td></tr>";
      });
      h += novo(c, "regra", "Incluir regra") + "</tbody></table></div>" + divergencias(c, f);
      var lac = [], porTxt = {};
      f.contratos.forEach(function (k) { (k.lacunas || []).forEach(function (l) { if (!porTxt[l]) { porTxt[l] = []; lac.push(l); } porTxt[l].push(rotuloK(k)); }); });
      if (lac.length) h += '<div class="ctr-bloco"><details><summary><h3 style="display:inline">O que o PDF não diz <span class="ctr-fonte">' + lac.length + "</span></h3></summary><ul class=\"lacunas\">" + lac.map(function (l) {
        return "<li>" + esc(l) + '<span class="mudo">' + (f.contratos.length < 2 ? "" : porTxt[l].length === f.contratos.length ? " (todos)" : " (" + esc(porTxt[l].join("; ")) + ")") + "</span></li>";
      }).join("") + "</ul></details></div>";
    } else {
      h += '<div class="ctr-vazio"><p>Este cliente não tem PDF de contrato lido: nenhuma regra ainda.' + (pode(c) ? " Inclua as regras aqui; cada uma vai ao histórico." : "") + "</p></div>";
      if (pode(c)) h += '<div class="ctr-rol"><table class="ctr-tab"><tbody>' + novo(c, "regra", "Incluir regra") + "</tbody></table></div>";
    }
    return h + dadosDoContrato(c);
  }

  /* ── o calendário (as obrigações da planilha, editáveis) ────────────────────────────────────────────────────────── */
  var SIT = {ok: ["Entregue", "t-ok"], critico: ["Vencida", "t-critico"], alerta: ["Vence logo", "t-alerta"], neutro: ["No prazo", "t-neutro"], sem_data: ["Sem data", "t-info"], cancelado: ["Cancelada", "t-neutro"]};
  function selo(o) {
    if (o.tom === "ok") return o.no_prazo ? '<span class="ctr-pill t-ok">Entregue no prazo</span>' : '<span class="ctr-pill t-alerta">' + (o.entrega ? "Entregue com atraso" : "Entregue sem data") + "</span>";
    var s = SIT[o.tom] || ["", "t-neutro"];
    return '<span class="ctr-pill ' + s[1] + '">' + s[0] + "</span>";
  }
  function tabelaObrig(c, lista, preset, rotuloNovo) {
    return '<div class="ctr-rol"><table class="ctr-tab"><thead><tr><th>Vencimento</th><th>Obrigação</th><th>Tipo</th><th>Executor</th><th>Situação</th><th>Entregue em</th><th></th></tr></thead><tbody>' +
      lista.map(function (o) {
        return '<tr><td class="num"><i class="ctr-ponto p-' + o.tom + '" aria-hidden="true"></i> ' + (o.vencimento ? dBR(o.vencimento) : '<span class="mudo">sem data</span>') + "</td><td>" + esc(o.descricao) +
          (o.clausula ? '<small class="mudo"> (' + esc(o.clausula) + ")</small>" : "") + editado(o, ["descricao", "vencimento", "status", "entrega", "tipo", "executor"]) + "</td><td>" + esc(o.tipo) + "</td><td>" + esc(o.executor) +
          "</td><td>" + selo(o) + '</td><td class="num">' + (o.entrega ? dBR(o.entrega) : '<span class="mudo">—</span>') + '</td><td class="r">' + lapis(c, "obrigacao", [o._id], "Editar esta obrigação") + "</td></tr>";
      }).join("") + novo(c, "obrigacao", rotuloNovo || "Incluir obrigação", preset) + "</tbody></table></div>";
  }
  function rCalendario(c) {
    var obr = obrDe(c), hj = new Date(R.hoje + "T12:00:00"), ano = hj.getFullYear(), mes = hj.getMonth();
    var ini = new Date(ano, mes, 1).getDay(), nd = new Date(ano, mes + 1, 0).getDate(), total = Math.ceil((ini + nd) / 7) * 7;
    var titulo = MESES[mes].charAt(0).toUpperCase() + MESES[mes].slice(1) + " de " + ano;
    var h = '<div class="ctr-regua"><h2>' + titulo + '</h2><div class="ctr-legenda"><span><i class="ctr-ponto p-ok"></i>entregue</span><span><i class="ctr-ponto p-alerta"></i>no alerta</span><span><i class="ctr-ponto p-critico"></i>atrasada</span><span><i class="ctr-ponto p-neutro"></i>prevista</span><span><i class="ctr-ponto p-sem_data"></i>sem data</span></div></div>';
    h += '<div class="ctr-grade"><div class="ctr-cal" role="grid" aria-label="' + titulo + '">' + ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"].map(function (d) { return '<div class="dsem">' + d + "</div>"; }).join("");
    for (var i = 0; i < total; i++) {
      var dia = i - ini + 1, fora = dia < 1 || dia > nd, eHoje = !fora && dia === hj.getDate();
      var iso = ano + "-" + String(mes + 1).padStart(2, "0") + "-" + String(dia).padStart(2, "0");
      var doDia = fora ? [] : obr.filter(function (o) { return o.vencimento === iso; });
      h += '<div class="dia' + (fora ? " fora" : "") + (eHoje ? " hoje" : "") + '"><span class="n">' + (fora ? "" : dia) + (eHoje ? " hoje" : "") + "</span>" +
        doDia.map(function (o) { return '<span class="ctr-ev ' + o.tom + '" title="' + esc(o.descricao + (o.executor ? ", " + o.executor : "") + ", " + o.status) + '">' + esc(o.tipo || o.descricao) + "</span>"; }).join("") + "</div>";
    }
    h += "</div>";
    var atr = obr.filter(function (o) { return o.tom === "critico"; }), prox = obr.filter(function (o) { return o.tom === "alerta" || o.tom === "neutro"; }).slice(0, 8), sd = obr.filter(function (o) { return o.tom === "sem_data"; });
    function item(o) { return '<li><i class="ctr-ponto p-' + o.tom + '"></i><span>' + esc(o.descricao) + "<small>" + (o.vencimento ? (o.tom === "critico" ? "venceu em " : "vence em ") + dBR(o.vencimento) : esc(o.status || "sem vencimento")) + (o.executor ? ", " + esc(o.executor) : "") + "</small></span></li>"; }
    h += '<aside class="ctr-lat"><h3>Atrasadas</h3><ul>' + (atr.map(item).join("") || '<li class="mudo">Nenhuma.</li>') + "</ul><h3>Próximas</h3><ul>" + (prox.map(item).join("") || '<li class="mudo">Nenhuma.</li>') + "</ul>" +
      (sd.length ? "<h3>Sem data</h3><ul>" + sd.map(item).join("") + "</ul>" : "") + "</aside></div>";
    h += '<div class="ctr-bloco"><h3>Todas as obrigações (' + obr.length + ")</h3>" + tabelaObrig(c, obr) + "</div>";
    return h + blocoContrato(c, ["Rotinas"], "Rotinas que o contrato pede");
  }

  /* ── atendimento, entregáveis, metas, financeiro ────────────────────────────────────────────────────────────────── */
  function rAtendimento(c) {
    var b = blocoContrato(c, ["SLA"], "O atendimento que o contrato pede");
    return (b || '<div class="ctr-vazio"><p>Sem PDF do contrato lido: o SLA está nos Dados do contrato, na aba Regras.</p></div>') +
      '<p class="ctr-nota">O atendimento feito em cada usina (as OS do mês) não está na planilha de controle nem no contrato.</p>';
  }
  function rEntregaveis(c) {
    var lista = obrDe(c).filter(function (o) { return o.entregavel; }), par0 = R.parametros || {};
    var vencidos = lista.filter(function (o) { return o.tom === "ok" || o.tom === "critico"; }), noPrazo = lista.filter(function (o) { return o.no_prazo; }).length;
    return blocoContrato(c, ["Entregáveis"], "O que o contrato pede") + '<div class="ctr-bloco"><h3>Entregáveis e medições lançados <span class="ctr-fonte">' + lista.length + "; " + noPrazo + " de " + vencidos.length +
      " já vencidos entregues no prazo" + (par0.meta_entregaveis != null ? "; meta " + pct(100 * par0.meta_entregaveis, 0) + "%" : "") + "</span></h3>" +
      tabelaObrig(c, lista, {tipo: "Entregável ao cliente (RMO, relatório)", status: "Não iniciado"}, "Incluir entregável") + "</div>";
  }
  function contraMeta(n, d, meta) {
    if (!d) return '<span class="mudo">—</span>';
    return '<span class="num ' + (meta == null ? "" : n / d >= meta ? "c-ok" : "c-critico") + '">' + pct(100 * n / d, 0) + "%</span>";
  }
  function metaTxt(m) { return m == null ? "sem meta" : "meta " + pct(100 * m, 0) + "%"; }
  function rMetas(c) {
    var p = R.parametros || {}, obr = obrDe(c), ad = adicDe(c), mesHoje = R.hoje.slice(0, 7), meses = {};
    var venc = obr.filter(function (o) { return o.tom === "critico"; }).length;
    obr.forEach(function (o) { if (o.entregavel && o.mes && o.mes <= mesHoje) meses[o.mes] = 1; });
    ad.forEach(function (a) { if (a.mes && a.mes <= mesHoje) meses[a.mes] = 1; });
    var h = '<div class="ctr-regua"><h2>Obrigações vencidas em aberto hoje: <span class="num ' + (venc > (p.meta_vencidas || 0) ? "c-critico" : "c-ok") + '">' + venc + "</span></h2>" +
      '<span class="ctr-fonte">' + (p.meta_vencidas == null ? "sem meta" : "meta " + p.meta_vencidas) + " " + lapis(null, "parametros", ["p0"], "Editar as metas e os prazos") + "</span></div>";
    var lista = Object.keys(meses).sort().reverse();
    if (lista.length) h += '<div class="ctr-rol"><table class="ctr-tab"><thead><tr><th>Mês</th><th class="r">Entregáveis no prazo</th><th class="r">%<span class="sub">' + metaTxt(p.meta_entregaveis) +
      '</span></th><th class="r">Adicionais faturados</th><th class="r">% da quantidade<span class="sub">' + metaTxt(p.meta_adicionais) + '</span></th><th class="r">Valor executado</th><th class="r">Valor faturado</th><th class="r">% do valor</th></tr></thead><tbody>' +
      lista.map(function (m) {
        var e = obr.filter(function (o) { return o.entregavel && o.mes === m; }), ep = e.filter(function (o) { return o.no_prazo; }).length;
        var a = ad.filter(function (x) { return x.mes === m; }), af = a.filter(function (x) { return x.faturado; });
        var vx = a.reduce(function (s, x) { return s + x.valor; }, 0), vf = af.reduce(function (s, x) { return s + x.valor; }, 0), pp = m.split("-");
        return "<tr><td>" + MESES[+pp[1] - 1] + " de " + pp[0] + '</td><td class="r num">' + (e.length ? ep + " de " + e.length : '<span class="mudo">nenhum</span>') + '</td><td class="r">' + contraMeta(ep, e.length, p.meta_entregaveis) +
          '</td><td class="r num">' + (a.length ? af.length + " de " + a.length : '<span class="mudo">nenhum</span>') + '</td><td class="r">' + contraMeta(af.length, a.length, p.meta_adicionais) +
          '</td><td class="r num">' + (a.length ? brl(vx) : "—") + '</td><td class="r num">' + (a.length ? brl(vf) : "—") + '</td><td class="r">' + contraMeta(vf, vx, p.meta_adicionais) + "</td></tr>";
      }).join("") + "</tbody></table></div>";
    else h += '<p class="mudo">Ainda não há entregável vencido nem serviço adicional para medir.</p>';
    return h + '<p class="ctr-nota">As contas da aba Indicadores_Mes da planilha de controle, só deste contrato: o entregável conta no mês do vencimento e o adicional no da execução.</p>' +
      blocoContrato(c, ["Disponibilidade e desempenho", "Benefícios", "Penalidades"], "Metas, bônus e penalidades do contrato");
  }
  var SIT_ADIC = {"Faturado": "t-ok", "Aprovado — faturar": "t-verde", "Aguardando cliente": "t-alerta", "Memória a enviar": "t-neutro", "Memória atrasada": "t-critico", "Reprovado": "t-neutro"};
  function rFinanceiro(c) {
    var ad = adicDe(c), bms = obrDe(c).filter(function (o) { return String(o.tipo).slice(0, 7) === "Medição"; });
    function soma(l) { return l.reduce(function (s, a) { return s + a.valor; }, 0); }
    var fat = ad.filter(function (a) { return a.faturado; }), aFat = ad.filter(function (a) { return !a.faturado && a.situacao !== "Reprovado"; });
    var atr = ad.filter(function (a) { return a.situacao === "Memória atrasada"; }).length;
    var h = '<div class="ctr-regua"><h2>Serviços adicionais</h2><span class="ctr-fonte">o que foi feito fora do valor fixo, com a memória de cobrança</span></div>';
    if (ad.length) h += '<dl class="ctr-resumo-dl"><div><dt>Executado</dt><dd>' + brl(soma(ad)) + "<small>" + ad.length + " serviço" + (ad.length === 1 ? "" : "s") + "</small></dd></div>" +
      '<div><dt>Faturado</dt><dd class="' + (fat.length ? "c-ok" : "") + '">' + brl(soma(fat)) + "<small>" + fat.length + " com nota</small></dd></div>" +
      '<div><dt>A faturar</dt><dd class="' + (aFat.length ? "c-alerta" : "") + '">' + brl(soma(aFat)) + "<small>" + aFat.length + " serviço" + (aFat.length === 1 ? "" : "s") + "</small></dd></div>" +
      '<div><dt>Memória atrasada</dt><dd class="' + (atr ? "c-critico" : "") + '">' + atr + "<small>prazo de " + ((R.parametros || {}).prazo_memoria || 10) + " dias após a execução</small></dd></div></dl>";
    h += '<div class="ctr-rol" style="margin-top:12px"><table class="ctr-tab"><thead><tr><th>Execução</th><th>Usina</th><th>Serviço</th><th>OS</th><th class="r">Valor</th><th>BM</th><th>Situação</th><th></th></tr></thead><tbody>' +
      ad.map(function (a) {
        return '<tr><td class="num">' + (a.execucao ? dBR(a.execucao) : '<span class="mudo">sem data</span>') + "</td><td>" + esc(a.usina) + "</td><td>" + esc(a.servico) + editado(a, ["servico", "valor_aprovado", "faturamento", "resposta", "memoria"]) +
          (a.base ? '<span class="sub">' + esc(a.base) + "</span>" : "") + '</td><td class="num">' + esc(a.os) + '</td><td class="r num">' + brl(a.valor) + (a.valor_aprovado == null && a.valor ? '<span class="sub">estimado</span>' : "") +
          "</td><td>" + esc(a.bm) + '</td><td><span class="ctr-pill ' + (SIT_ADIC[a.situacao] || "t-neutro") + '">' + esc(a.situacao) + '</span></td><td class="r">' + lapis(c, "adicional", [a._id], "Editar este serviço") + "</td></tr>";
      }).join("") + novo(c, "adicional", "Incluir serviço adicional") + "</tbody></table></div>";
    if (bms.length) h += '<div class="ctr-bloco"><h3>Medições (BM)</h3>' + tabelaObrig(c, bms, {tipo: "Medição / faturamento (BM)", status: "Não iniciado"}, "Incluir medição") + "</div>";
    var f = fichaDe(c);
    if (f) {
      h += '<div class="ctr-bloco"><h3>Valor no contrato</h3><div class="ctr-rol"><table class="ctr-tab"><thead><tr><th>Contrato</th><th class="r">Valor mensal</th><th>Como está escrito</th><th>Reajuste</th><th>Onde</th><th></th></tr></thead><tbody>';
      f.contratos.forEach(function (k) {
        if (k._id === "geral") return;
        var v = k.valor || {}, rj = k.reajuste || {};
        h += "<tr><td>" + esc(rotuloK(k)) + editado(k, ["valor.mensal", "vigencia.fim", "reajuste.indice"]) + '</td><td class="r num">' + (typeof v.mensal === "number" ? brl(v.mensal) : '<span class="vazio-c">não escrito</span>') + "</td><td>" + esc(v.texto || "") +
          "</td><td>" + esc(rj.texto || rj.indice || "") + '</td><td class="onde">' + refTxt(v.ref) + '</td><td class="r">' + lapis(c, "contrato", [k._id], "Editar este contrato") + "</td></tr>";
      });
      h += "</tbody></table></div></div>" + blocoContrato(c, ["Medição e faturamento", "Adicionais e hora extra"], "Medição, faturamento e adicionais no contrato");
    }
    return h;
  }

  /* ── o histórico ────────────────────────────────────────────────────────────────────────────────────────────────── */
  var EVENTO = {inclusao: "Incluiu", alteracao: "Alterou", retirada: "Retirou", carga: "Carga inicial"};
  function valorTxt(v) { if (v == null || v === "") return "—"; var s = String(v); return /^\d{4}-\d{2}-\d{2}$/.test(s) ? dBR(s) : s; }
  function rHistorico(c) {
    var lista = HIST[c.cliente];
    if (!lista) {
      pedir(CAMINHO + "historico.json?cliente=" + encodeURIComponent(c.cliente)).then(function (d) { HIST[c.cliente] = (d && d.historico) || []; if (estado.aba === "historico") render(); })
        .catch(function (e) { HIST[c.cliente] = [{erro: e.message}]; if (estado.aba === "historico") render(); });
      return '<p class="mudo" style="padding:14px 0">Lendo o histórico…</p>';
    }
    if (lista[0] && lista[0].erro) return '<p class="c-critico">Não li o histórico: ' + esc(lista[0].erro) + "</p>";
    return '<div class="ctr-regua"><h2>Histórico</h2><span class="ctr-fonte">quem mudou, o que, quando, o motivo e a prova; a mais nova primeiro</span></div><ul class="ctr-hist">' + lista.map(function (x) {
      var itens = (x.itens && x.itens.length > 1) ? " (" + x.itens.length + " contratos)" : "";
      return '<li><div class="q"><b>' + esc(x.quem) + "</b>" + esc(x.quando) + '</div><div class="o"><p><b>' + esc(EVENTO[x.evento] || x.evento) + "</b> " + esc(x.item_tipo === "Carga inicial" ? "" : x.item_tipo.toLowerCase()) +
        (x.item ? ": " + esc(x.item) : "") + itens + "</p>" +
        (x.campos && x.campos.length ? "<table><thead><tr><th>Campo</th><th>Era</th><th>Ficou</th></tr></thead><tbody>" + x.campos.map(function (k) {
          return "<tr><td>" + esc(k.campo) + '</td><td class="mudo">' + esc(valorTxt(k.antes)) + "</td><td>" + esc(valorTxt(k.depois)) + "</td></tr>";
        }).join("") + "</tbody></table>" : "") +
        (x.motivo ? "<p><span class=\"mudo\">Motivo:</span> " + esc(x.motivo) + "</p>" : "") +
        ((x.anexos && x.anexos.length) || x.prova_texto ? '<div class="prova"><span class="mudo">Prova:</span> ' + (x.anexos || []).map(function (a) { return '<a href="' + esc(a.url) + '" target="_blank" rel="noopener">' + esc(a.nome) + "</a>"; }).join("") +
          (x.prova_texto ? "<details><summary>o texto colado</summary><pre>" + esc(x.prova_texto) + "</pre></details>" : "") + "</div>" : "") + "</div></li>";
    }).join("") + "</ul>";
  }

  /* ── a edição: o diálogo com o motivo e a prova obrigatórios ────────────────────────────────────────────────────── */
  function achar(tipo, id) {
    if (tipo === "cliente") return R.contratos.filter(function (c) { return c.id === id; })[0];
    if (tipo === "parametros") return R.parametros || {};
    if (tipo === "obrigacao") return R.obrigacoes.filter(function (o) { return o._id === id; })[0];
    if (tipo === "adicional") return R.adicionais.filter(function (a) { return a._id === id; })[0];
    var achado = null;
    Object.keys(R.fichas || {}).forEach(function (cli) {
      R.fichas[cli].contratos.forEach(function (k) {
        if (tipo === "contrato" && k._id === id) achado = k;
        if (tipo === "regra") (k.regras || []).forEach(function (r) { if (r._id === id) achado = r; });
      });
    });
    return achado;
  }
  function pega(item, campo) { var x = item; campo.split(".").forEach(function (p) { x = x && typeof x === "object" ? x[p] : undefined; }); return x; }
  var ROTULO = {cliente: "Dados do contrato", contrato: "Contrato lido do PDF", regra: "Regra", obrigacao: "Obrigação", adicional: "Serviço adicional", parametros: "Metas e prazos"};
  function campoHtml(spec, valor, c) {
    var nome = spec[0], rot = spec[1], tipo = spec[2], extra = spec[3], id = "ctr-f-" + nome.replace(/\W/g, "_"), v = valor == null ? "" : valor, h;
    if (extra === "so_admin" && !R.admin) return "";
    if (tipo === "longo") h = '<textarea id="' + id + '" data-campo="' + nome + '" rows="3">' + esc(v) + "</textarea>";
    else if (tipo === "data") h = '<input id="' + id + '" data-campo="' + nome + '" type="date" value="' + esc(String(v).slice(0, 10)) + '">';
    else if (tipo === "lista") h = '<select id="' + id + '" data-campo="' + nome + '">' + (extra || []).map(function (o) { return '<option value="' + esc(o) + '"' + (o === v ? " selected" : "") + ">" + (o ? esc(o) : "—") + "</option>"; }).join("") +
      (v && (extra || []).indexOf(v) < 0 ? '<option value="' + esc(v) + '" selected>' + esc(v) + "</option>" : "") + "</select>";
    else if (tipo === "pessoa") h = '<select id="' + id + '" data-campo="' + nome + '"><option value="">— ninguém ligado —</option>' + (R.pessoas || []).map(function (p) {
      return '<option value="' + esc(p.hmac) + '"' + (p.hmac === v ? " selected" : "") + ">" + esc(p.nome) + "</option>"; }).join("") + "</select>";
    else if (tipo === "contrato") {
      var f = fichaDe(c), ks = f ? f.contratos.filter(function (k) { return k._id !== "geral"; }) : [];
      h = '<select id="' + id + '" data-campo="' + nome + '"><option value="">Sem contrato lido (regra do cliente)</option>' + ks.map(function (k) {
        return '<option value="' + esc(k._id) + '"' + (k._id === v ? " selected" : "") + ">" + esc(rotuloK(k)) + "</option>"; }).join("") + "</select>";
    } else h = '<input id="' + id + '" data-campo="' + nome + '" type="text"' + (tipo === "numero" || tipo === "inteiro" ? ' inputmode="decimal"' : "") + ' value="' + esc(v) + '">';
    return '<div class="ctr-campo' + (tipo === "longo" ? " largo" : "") + '"><label for="' + id + '">' + esc(rot) + "</label>" + h + "</div>";
  }
  function abrirEdicao(b) {
    var tipo = b.getAttribute("data-ed-tipo"), ids = (b.getAttribute("data-ed-ids") || "").split(",").filter(Boolean), novoItem = b.hasAttribute("data-ed-novo");
    var cli = b.getAttribute("data-ed-cliente") || "", c = R.contratos.filter(function (x) { return x.cliente === cli; })[0], preset = {};
    try { preset = JSON.parse(b.getAttribute("data-ed-preset") || "{}"); } catch (e) { preset = {}; }
    var item = novoItem ? preset : achar(tipo, ids[0]) || {};
    var specs = (R.campos || {})[tipo] || [];
    var aplicar = "";
    if (tipo === "regra" && ids.length > 1) {
      aplicar = '<div class="ctr-campo largo"><label for="ctr-f-aplicar">Aplicar a</label><select id="ctr-f-aplicar"><option value="todos">Todos os ' + ids.length + " contratos com esta regra</option>" +
        ids.map(function (i) { var k = null; Object.keys(R.fichas).forEach(function (x) { R.fichas[x].contratos.forEach(function (kk) { (kk.regras || []).forEach(function (r) { if (r._id === i) k = kk; }); }); });
          return '<option value="' + esc(i) + '">Só ' + esc(k ? rotuloK(k) : i) + "</option>"; }).join("") + "</select></div>";
    }
    var retiravel = !novoItem && ["regra", "obrigacao", "adicional"].indexOf(tipo) >= 0;
    dlg.innerHTML = '<form method="dialog" novalidate><h2 id="ctr-dlg-t">' + (novoItem ? "Incluir: " : "Editar: ") + esc(ROTULO[tipo] || tipo) + "</h2>" +
      '<p class="ctr-dlg-sub">' + esc(cli || "Todos os contratos") + ". A mudança vai ao histórico com o seu nome, a hora, o motivo e a prova.</p>" +
      '<div class="ctr-campos">' + aplicar + specs.map(function (s) { return campoHtml(s, pega(item, s[0]), c); }).join("") + "</div>" +
      '<div class="ctr-prova"><div class="ctr-campo largo"><label for="ctr-f-motivo">Motivo da mudança <span class="obrig">(obrigatório)</span></label><textarea id="ctr-f-motivo" rows="2" required></textarea></div>' +
      '<div class="ctr-campo largo"><label for="ctr-f-provas">Prova: o e-mail, a mensagem ou o documento <span class="obrig">(obrigatório: o arquivo ou o texto colado)</span></label>' +
      '<input id="ctr-f-provas" type="file" multiple accept=".pdf,.png,.jpg,.jpeg,.webp,.txt,.eml,.msg,.doc,.docx,.xlsx"></div>' +
      '<div class="ctr-campo largo"><label for="ctr-f-prova-texto">ou cole aqui o texto do e-mail ou da mensagem</label><textarea id="ctr-f-prova-texto" rows="3"></textarea></div></div>' +
      '<p class="ctr-dlg-erro" role="alert" hidden></p><div class="ctr-dlg-botoes"><button type="submit" class="gc-btn gc-btn--ui gc-btn--primario" data-evento="' + (novoItem ? "inclusao" : "alteracao") + '">Salvar</button>' +
      '<button type="button" class="gc-btn gc-btn--ui gc-btn--contorno" data-fechar>Cancelar</button>' + (retiravel ? '<button type="submit" class="gc-btn gc-btn--ui gc-btn--contorno ctr-retirar" data-evento="retirada">Retirar</button>' : "") + "</div></form>";
    var form = dlg.querySelector("form");
    dlg.querySelector("[data-fechar]").onclick = function () { dlg.close(); };
    form.onsubmit = function (ev) {
      ev.preventDefault();
      var botao = ev.submitter || form.querySelector("[data-evento]"), evento = botao.getAttribute("data-evento"), erro = form.querySelector(".ctr-dlg-erro");
      var fd = new FormData(), valores = {};
      [].forEach.call(form.querySelectorAll("[data-campo]"), function (el) { valores[el.getAttribute("data-campo")] = el.value; });
      var alvo = form.querySelector("#ctr-f-aplicar");
      (alvo && alvo.value !== "todos" ? [alvo.value] : ids).forEach(function (i) { fd.append("item_id", i); });
      fd.append("item_tipo", tipo); fd.append("evento", evento); fd.append("cliente", cli);
      fd.append("valores", JSON.stringify(evento === "retirada" ? {} : valores));
      fd.append("motivo", form.querySelector("#ctr-f-motivo").value);
      fd.append("prova_texto", form.querySelector("#ctr-f-prova-texto").value);
      [].forEach.call(form.querySelector("#ctr-f-provas").files, function (f) { fd.append("provas", f, f.name); });
      if (evento === "retirada" && !window.confirm("Retirar este item? Ele sai da tela e fica no histórico.")) return;
      [].forEach.call(form.querySelectorAll("button"), function (x) { x.disabled = true; });
      erro.hidden = true;
      pedir(CAMINHO + "editar", {method: "POST", body: fd, headers: {"Accept": "application/json", "X-Nexus-Parte": "1"}}).then(function (r) {
        dlg.close();
        delete HIST[cli];
        toast(evento === "retirada" ? "Retirado. Está no histórico." : (r && r.mudou > 1 ? "Salvo em " + r.mudou + " contratos. Está no histórico." : "Salvo. Está no histórico."));
        carregar();
      }).catch(function (e) {
        [].forEach.call(form.querySelectorAll("button"), function (x) { x.disabled = false; });
        erro.textContent = (e && e.message ? e.message : "Não consegui salvar agora.") + " Nada foi gravado.";
        erro.hidden = false;
      });
    };
    dlg.showModal();
    var primeiro = dlg.querySelector("input,select,textarea"); if (primeiro) primeiro.focus();
  }

  /* ── desenhar e os eventos ──────────────────────────────────────────────────────────────────────────────────────── */
  function render() {
    fechaEscolha(false);
    var antes = estado.ct;
    lerEndereco();
    if (estado.ct !== antes) estado.soAditivo = false;
    raiz.innerHTML = (R.erro_edicoes ? '<p class="c-alerta" role="status" style="margin:0 0 8px">' + esc(R.erro_edicoes) + "</p>" : "") +
      (estado.ct >= 0 ? vCliente(R.contratos[estado.ct]) : vTodos());
  }
  window.addEventListener("hashchange", function () {
    render();
    if (estado.aba !== ultimaAba || estado.ct !== ultimoCt) window.scrollTo(0, 0);
    ultimaAba = estado.aba; ultimoCt = estado.ct;
  });
  raiz.addEventListener("click", function (e) {
    var b;
    if ((b = e.target.closest("[data-ed-tipo]"))) { e.preventDefault(); abrirEdicao(b); }
    else if ((b = e.target.closest("[data-rg]"))) { var rg = b.getAttribute("data-rg"); regraAberta[rg] = !regraAberta[rg]; render(); }
    else if ((b = e.target.closest("[data-regras]"))) { estado.soAditivo = b.getAttribute("data-regras") === "aditivo"; render(); }
    else if ((b = e.target.closest("[data-grupo]"))) { var g = b.getAttribute("data-grupo"); estado.grupos[g] = !estado.grupos[g]; render(); }
    else if ((b = e.target.closest(".ctr-escolha-btn"))) { if (aberta) fechaEscolha(true); else abreEscolha(b.closest("[data-escolha]")); }
    else if ((b = e.target.closest('.ctr-lista li[role="option"]'))) { fechaEscolha(false); irPara(+b.getAttribute("data-ir")); }
    else if ((b = e.target.closest("[data-ir]")) && !e.target.closest("a")) irPara(+b.getAttribute("data-ir"));
  });
  raiz.addEventListener("input", function (e) { if (aberta && e.target === aberta.campo) filtraEscolha(); });
  raiz.addEventListener("mousemove", function (e) {
    var li = aberta && e.target.closest('.ctr-lista li[role="option"]');
    if (li && !li.classList.contains("marcada")) marcaEscolha(visiveis().indexOf(li));
  });
  function carregar() {
    return pedir(CAMINHO + "dados.json").then(function (d) {
      if (!d || !d.ok) { raiz.innerHTML = '<div class="ctr-vazio"><p>Os contratos ainda não chegaram a este Nexus.</p></div>'; return; }
      R = d; render();
    }).catch(function (e) { raiz.innerHTML = '<p class="c-critico">Não li os contratos: ' + esc(e && e.message) + "</p>"; });
  }
  carregar();
})();

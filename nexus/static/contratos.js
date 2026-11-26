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
  var estado = {ct: -1, aba: "regras", grupos: {}, soAditivo: false, verRegras: "todas", temas: {}, mesCal: 0};
  var ABAS = [["regras", "Regras"], ["pontos", "Pontos"], ["calendario", "Calendário"], ["atendimento", "Atendimento"], ["entregaveis", "Entregáveis"],
    ["metas", "Metas"], ["financeiro", "Financeiro"], ["historico", "Histórico"], ["indicadores", "Indicadores"]];
  var CATS = ["SLA", "Entregáveis", "Rotinas", "Disponibilidade e desempenho", "Penalidades", "Benefícios", "Medição e faturamento",
    "Adicionais e hora extra", "Rescisão", "Seguros e documentação", "Outras obrigações"];
  // os setores que executam, na ordem da operação (Levi, 19/11/2026: "separar por setor [...] ordenar por setor, pelo
  // menos, e aí botar uma linha grossa [...] para poder separar os setores"); a regra sem setor vem no fim
  var SETORES = ["Supervisão de Campo", "COS", "Performance", "PCM", "Engenharia de O&M", "Zeladoria", "HSEQ", "Contratos", "Financeiro"];
  function setorDe(x) { var s = (x && x.r ? x.r : x || {}).setor || ""; return SETORES.indexOf(s) >= 0 ? s : ""; }
  // os blocos que abrem e fecham (o pedido da área de Contratos, 19/11/2026: "que eles possa minimizar/maximizar [...] se
  // eu quero acessar somente os entregáveis que eu lancei, preciso ficar com tudo aquilo em aberto"); o navegador lembra
  var DOBRAS = {rec: false, unica: false, lanc: true};
  try { Object.assign(DOBRAS, JSON.parse(localStorage.getItem("nexus.contratos.dobras") || "{}")); } catch (e) { /* sem localStorage: o padrão */ }
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
  // o aniversário do contrato (26/11/2026, Levi: "ANIVERSÁRIO DE CONTRATO"): conta do início da vigência
  function fatoAniv(c) {
    if (!c.aniversario) return "";
    var a = c.ano_contratual || {};
    return par("Aniversário", '<span class="num">' + dBR(c.aniversario) + "</span><small>" + quando(c.dias_aniversario) + (a.n ? "; fecha o " + a.n + "º ano" : "") + "</small>");
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
    return '<div class="ctr-topo">' + escolha(opcoes(), -1) + '<span class="ctr-resumo">' + R.contratos.length + " contratos; " + venc + " com a vigência vencida; " + comAtr + " com obrigação em atraso; " +
      R.contratos.filter(function (c) { return c.pontos_atencao || c.pontos_divergencia; }).length + " com ponto a resolver</span></div>" +
      '<div class="ctr-rol" style="margin-top:10px"><table class="ctr-tab"><thead><tr><th>Cliente</th><th>Gestor do contrato</th><th>Vigência até</th><th>Renovação: avisar até</th><th>Próximo reajuste</th>' +
      '<th class="r">Valor mensal</th><th class="r">Em atraso</th><th class="r">Pontos</th><th class="r">Regras</th><th class="ir"><span class="so-leitor">Abrir</span></th></tr></thead><tbody>' +
      ordem.map(function (x) {
        var c = x.c, f = fichaDe(c), nr = f ? f.contratos.reduce(function (s, k) { return s + (k.regras || []).length; }, 0) : 0;
        return '<tr data-ir="' + x.i + '"><td><a href="' + rota(x.i) + '">' + esc(c.cliente) + "</a></td>" +
          "<td>" + (c.gestor ? esc(c.gestor) : '<span class="mudo">sem gestor</span>') + "</td>" +
          "<td>" + data(c.fim, c.dias_fim, "sem data") + doContrato(c, ["fim"]) + "</td>" +
          "<td>" + data(c.avisar_ate, c.dias_aviso, c.fim ? "sem aviso prévio" : "—") + doContrato(c, ["aviso_dias"]) + "</td>" +
          "<td>" + (c.proximo_reajuste ? data(c.proximo_reajuste, c.dias_reajuste) : '<span class="mudo">' + esc(String(c.indice || "sem índice").slice(0, 40)) + "</span>") + "</td>" +
          '<td class="r num">' + (c.valor_mensal != null ? brl(c.valor_mensal) : '<span class="mudo">—</span>') + "</td>" +
          '<td class="r">' + (c.atrasadas ? '<span class="ctr-pill t-critico">' + c.atrasadas + "</span>" : '<span class="mudo">0</span>') + "</td>" +
          '<td class="r" style="white-space:nowrap">' + pontosCel(x.i, c) + "</td>" +
          '<td class="r">' + (nr ? '<span class="num">' + nr + "</span>" : '<span class="mudo">PDF não lido</span>') + "</td>" +
          '<td class="ir"><i class="ph ph-caret-right" aria-hidden="true"></i></td></tr>';
      }).join("") + "</tbody></table></div>" +
      ((R.radar_sem_contrato || []).length ? '<p class="ctr-nota">Pontos do Radar da Zeladoria sem contrato com o mesmo nome aqui: ' + R.radar_sem_contrato.map(esc).join(", ") +
        ". Acerte o nome do cliente no Radar ou nos dados do contrato para eles entrarem.</p>" : "");
  }
  // os pontos abertos de um contrato, em Todos os contratos: o número de cada tipo, e o clique leva à aba Pontos
  function pontosCel(i, c) {
    var a = c.pontos_atencao || 0, d = c.pontos_divergencia || 0;
    if (!a && !d) return '<span class="mudo">0</span>';
    return '<a class="ctr-pts" href="' + rota(i, "pontos") + '">' + (a ? '<span class="ctr-pill t-critico" title="' + a + ' de atenção">' + a + "</span>" : "") +
      (d ? ' <span class="ctr-pill t-alerta" title="' + d + ' de divergência">' + d + "</span>" : "") + "</a>";
  }

  /* ── um contrato: o topo numa linha, os fatos, as abas ──────────────────────────────────────────────────────────── */
  function vCliente(c) {
    var n = atrasoDe(c), atr = obrDe(c).filter(function (o) { return o.tom === "critico"; }).length;
    var h = '<div class="ctr-topo"><a class="ctr-voltar" href="#/"><i class="ph ph-arrow-left" aria-hidden="true"></i>Todos</a>' + escolha(opcoes(), estado.ct) +
      (c.gestor ? '<span class="ctr-gestor"><i class="ph ph-user-circle" aria-hidden="true"></i><small>Gestor</small>' + esc(c.gestor) +
        (c.gestor_como === "sem ligação" && R.admin ? ' <span class="ctr-pill t-alerta" title="O nome da planilha não casa com uma pessoa do Nexus: ligue em Editar dados">sem ligação</span>' : "") + "</span>" :
        '<span class="ctr-gestor mudo">sem gestor</span>') +
      '<span class="ctr-acoes">' + (pode(c) ? '<button type="button" class="ctr-lapis" data-ed-tipo="cliente" data-ed-ids="' + esc(c.id) + '" data-ed-cliente="' + esc(c.cliente) + '"><i class="ph ph-pencil-simple" aria-hidden="true"></i>Editar dados</button>' : "") + "</span></div>";
    h += '<dl class="ctr-fatos">' + fatoVig(c) + fatoRenov(c) + fatoReaj(c) + fatoAniv(c) + fatoValor(c) + par("Usinas", '<span class="num">' + (c.usinas || []).length + "</span>") +
      (n ? '<div><a class="ctr-atraso" href="' + rota(estado.ct, atr ? "calendario" : "regras") + '"><i class="ctr-ponto p-critico" aria-hidden="true"></i>' + n + " em atraso</a></div>" : "") + "</dl>";
    h += '<nav class="ctr-abas" aria-label="Partes do contrato">' + ABAS.map(function (a) {
      return '<a href="' + rota(estado.ct, a[0]) + '"' + (estado.aba === a[0] ? ' aria-current="page"' : "") + ">" + a[1] +
        (a[0] === "calendario" && atr ? "<b>" + atr + "</b>" : "") +
        (a[0] === "pontos" && (c.pontos_atencao || c.pontos_divergencia) ? '<b class="' + (c.pontos_atencao ? "" : "b-alerta") + '">' + ((c.pontos_atencao || 0) + (c.pontos_divergencia || 0)) + "</b>" : "") + "</a>";
    }).join("") + "</nav>";
    var f = {indicadores: rIndicadores, regras: rRegras, pontos: rPontos, calendario: rCalendario, atendimento: rAtendimento, entregaveis: rEntregaveis, metas: rMetas, financeiro: rFinanceiro, historico: rHistorico}[estado.aba];
    return h + f(c);
  }

  /* ── o retorno da gestora que pediu a visão do contrato (chamada de 18/11/2026) ─────────────────────────────────────────────────────────────
     - os códigos do contrato (MPLP.3, MPCP.1, P52S) viram etiqueta depois do nome (Levi: "esse MPLP eu colocaria como uma
       tag [...] na frente eu creio que esteja atrapalhando a leitura");
     - o que se repete numa categoria (expurgos, multas, exclusões, disponibilidade) vira um item com a lista dentro (a área de Contratos:
       "tem vários expurgos [...] a gente pode juntar num só"; Levi: "agrupar expurgos, multas [...] tudo que se repete");
     - a regra prioritária (a estrela do gestor) fica no alto; o comentário fica na regra, com quem e quando (pedido da área de Contratos);
     - a ação leve (estrela, comentário, check de entregue, descartar sugestão) não pede motivo nem prova (Levi: "só quem e
       quando"). */
  var COD = "[A-Z]{2,6}\\d*(?:\\.\\d+)?(?:\\s*\\/\\s*[A-Z]{2,6}\\d*(?:\\.\\d+)?)*";
  function codigos(nome) {
    var t = String(nome || ""), tags = [], m;
    if ((m = t.match(new RegExp("^\\s*(" + COD + ")\\s*[–—-]\\s*")))) { tags = tags.concat(m[1].split(/\s*\/\s*/)); t = t.slice(m[0].length); }
    t = t.replace(new RegExp("\\s*\\((" + COD + ")\\)\\s*"), function (x, g) { tags = tags.concat(g.split(/\s*\/\s*/)); return " "; }).trim();
    return {texto: t || String(nome || ""), tags: tags};
  }
  function nomeHtml(nome) {
    var x = codigos(nome);
    return esc(x.texto) + x.tags.map(function (t) { return ' <span class="ctr-tag">' + esc(t) + "</span>"; }).join("");
  }
  var TEMAS = [["expurgo", "Expurgos"], ["multa", "Multas"], ["exclus", "Exclusões"], ["indisponibilidade", "Disponibilidade"], ["disponibilidade", "Disponibilidade"]];
  function tema(nome) { var n = semAcento(nome); for (var i = 0; i < TEMAS.length; i++) if (n.indexOf(TEMAS[i][0]) >= 0) return TEMAS[i][1]; return ""; }
  function prioritaria(x) { return x.ks.some(function (y) { return y.r.prioritaria === true; }); }
  function comentariosDe(ids) { return (R.comentarios || []).filter(function (k) { return ids.indexOf(k.alvo_id) >= 0; }); }
  // a ação leve: grava sem motivo nem prova e relê
  function leve(c, tipo, ids, evento, valores, msg) {
    var fd = new FormData();
    (ids || [""]).forEach(function (i) { fd.append("item_id", i); });
    fd.append("item_tipo", tipo); fd.append("evento", evento); fd.append("cliente", c ? c.cliente : "");
    fd.append("valores", JSON.stringify(valores || {})); fd.append("motivo", ""); fd.append("prova_texto", "");
    return pedir(CAMINHO + "editar", {method: "POST", body: fd, headers: {"Accept": "application/json", "X-Nexus-Parte": "1"}})
      .then(function () { if (c) delete HIST[c.cliente]; if (msg) toast(msg); return carregar(); })
      .catch(function (e) { toast((e && e.message) || "Não consegui gravar agora."); });
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
  // a etiqueta curta da cláusula (Levi, 19/11/2026: "uma tagzinha [...] da cláusula do contrato [...] uma forma mais
  // resumida"): o servidor monta (fichas.clausula_curta); a referência inteira fica na dica
  function clTag(ref) {
    if (!ref) return "";
    var pg = ref.pagina ? "p. " + ref.pagina + (ref.pagina_fim && ref.pagina_fim !== ref.pagina ? "–" + ref.pagina_fim : "") : "";
    var dica = [ref.arquivo, ref.clausula ? "cláusula " + ref.clausula : "", pg].filter(Boolean).join(", ");
    return (ref.curta ? '<span class="ctr-cl" title="' + esc(dica) + '">' + esc(ref.curta) + "</span>" : "") +
      (pg ? '<small class="mudo"' + (ref.curta ? "" : ' title="' + esc(dica) + '"') + "> " + esc(pg) + "</small>" : "");
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
  function linhaRegra(c, f, x, varios, op) {
    op = op || {};
    var r = x.r, subTxt = op.sub === "categoria" ? r.categoria : op.sub === "" ? "" : r.setor, id = c.cliente + "|" + x.ch, ab = !!regraAberta[id], ids = x.ks.map(function (y) { return y.r._id; });
    var quais = !varios ? "" : x.ks.length === f.contratos.length ? "todos" : x.ks.map(function (y) { return esc(rotuloK(y.k)); }).join("; ");
    var pri = prioritaria(x), coms = comentariosDe(ids);
    var estrela = pode(c) ? '<button type="button" class="ctr-estrela" data-prior="' + esc(ids.join(",")) + '" aria-pressed="' + pri + '" title="' + (pri ? "Tirar das prioritárias" : "Marcar como prioritária") +
      '"><i class="ph' + (pri ? "-fill" : "") + ' ph-star" aria-hidden="true"></i><span class="so-leitor">Prioritária</span></button>' : (pri ? '<i class="ph-fill ph-star ctr-estrela-fixa" title="Prioritária" aria-label="Prioritária"></i>' : "");
    var h = '<tr class="rg" data-rg="' + esc(id) + '" aria-expanded="' + ab + '"><td>' + estrela + '<span class="nome">' + nomeHtml(r.nome) + "</span>" + editado(r, ["nome", "vigente", "categoria", "setor"]) +
      (coms.length ? ' <span class="ctr-ncom" title="' + coms.length + (coms.length === 1 ? " comentário" : " comentários") + '"><i class="ph ph-chat-circle" aria-hidden="true"></i>' + coms.length + "</span>" : "") +
      (subTxt ? '<span class="sub">' + esc(subTxt) + "</span>" : "") + "</td><td>" + (vale(r) ? esc(vale(r)) : '<span class="vazio-c">não escrito</span>') +
      (r.alterado_por ? '<span class="antes">antes: <s>' + esc(r.contratual || "não previsto") + "</s>; mudou no " + esc(r.alterado_por.arquivo || "aditivo") + "</span>" : "") + "</td>" +
      (varios ? '<td class="ctr-quais">' + quais + "</td>" : "") + '<td class="onde">' + (r.ref ? clTag(r.ref) : r._incluido ? "incluída no Nexus" : "") +
      (x.ks.length > 1 ? " e mais " + (x.ks.length - 1) : "") + "</td></tr>";
    if (ab) {
      h += '<tr class="rg-det"><td colspan="' + (varios ? 4 : 3) + '">' + x.ks.map(function (y) {
        var rr = y.r, a = rr.alterado_por;
        return (varios ? '<b class="sub" style="margin:4px 0">' + esc(rotuloK(y.k)) + "</b>" : "") +
          (rr.trecho ? '<p class="trecho">“' + esc(rr.trecho) + "”<small>" + esc((rr.ref || {}).arquivo || "") + ", " + refTxt(rr.ref) + "</small></p>" : "") +
          (a && a.trecho ? '<p class="trecho">“' + esc(a.trecho) + "”<small>" + esc(a.arquivo || "") + ", " + refTxt(a) + (a.resumo ? ". " + esc(a.resumo) : "") + "</small></p>" : "");
      }).join("") + (pode(c) ? '<p style="margin:6px 0 2px">' + lapis(c, "regra", ids, "Editar esta regra").replace("</button>", "Editar</button>") + "</p>" : "") +
        blocoComentarios(c, ids) + "</td></tr>";
    }
    return h;
  }
  // os comentários da regra: quem, quando e o texto; quem vê o contrato comenta (pedido da área de Contratos, 18/11/2026)
  function blocoComentarios(c, ids) {
    var coms = comentariosDe(ids);
    return '<div class="ctr-coms"><b class="sub" style="margin:8px 0 4px">Comentários</b>' + coms.map(function (k) {
      return '<p class="ctr-com"><b>' + esc(k._quem) + '</b> <span class="mudo">' + esc(k._quando) + "</span>" +
        (k._meu || R.admin ? ' <button type="button" class="ctr-link" data-tirar-com="' + esc(k._id) + '">tirar</button>' : "") + "<br>" + esc(k.texto) + "</p>";
    }).join("") + '<form class="ctr-com-form" data-comentar="' + esc(ids[0]) + '"><label class="so-leitor" for="ctr-com-' + esc(ids[0]) + '">Comentar</label>' +
      '<textarea id="ctr-com-' + esc(ids[0]) + '" rows="2" placeholder="Escreva um comentário (ex.: alinhado com o cliente em 18/11)"></textarea><button type="submit" class="gc-btn gc-btn--ui gc-btn--contorno">Comentar</button></form></div>';
  }
  // a tabela: o que se repete por tema (2 ou mais) vira um subgrupo recolhido, com a lista dentro; com op.porSetor, as
  // regras vêm por setor (SETORES), cada setor aberto por uma linha grossa com o nome
  function corpoRegras(c, f, lista, varios, semTemas, op, setor) {
    var por = {}, ordem = [], h = "";
    lista.forEach(function (x) {
      var t = semTemas ? "" : tema(x.r.nome), k = t || ("_" + x.ch);
      if (!por[k]) { por[k] = []; ordem.push(k); }
      por[k].push(x);
    });
    ordem.forEach(function (k) {
      var xs = por[k];
      if (k.charAt(0) === "_" || xs.length < 2) { xs.forEach(function (x) { h += linhaRegra(c, f, x, varios, op); }); return; }
      var chave = c.cliente + "|tema|" + xs[0].r.categoria + "|" + setor + "|" + k, ab = !!estado.temas[chave];
      h += '<tr class="ctr-subgrupo"><td colspan="' + (varios ? 4 : 3) + '"><button type="button" data-subgrupo="' + esc(chave) + '" aria-expanded="' + ab + '"><i class="ph ph-caret-' + (ab ? "down" : "right") +
        '" aria-hidden="true"></i>' + esc(k) + ' <span class="mudo">' + xs.length + " itens</span></button></td></tr>";
      if (ab) xs.forEach(function (x) { h += linhaRegra(c, f, x, varios, op); });
    });
    return h;
  }
  function tabelaRegras(c, f, lista, semTemas, op) {
    op = op || {};
    var varios = f.contratos.filter(function (k) { return k._id !== "geral"; }).length > 1, ncol = varios ? 4 : 3;
    var h = '<div class="ctr-rol"><table class="ctr-tab"><thead><tr><th>Regra</th><th>Vale hoje</th>' + (varios ? "<th>Contratos</th>" : "") + "<th>Cláusula</th></tr></thead><tbody>";
    if (op.porSetor) {
      var por = {};
      lista.forEach(function (x) { var s = setorDe(x); (por[s] = por[s] || []).push(x); });
      SETORES.concat([""]).forEach(function (s) {
        if (!por[s]) return;
        h += '<tr class="ctr-setor"><td colspan="' + ncol + '">' + esc(s || "Sem setor") + ' <span class="mudo">' + por[s].length + "</span></td></tr>" +
          corpoRegras(c, f, por[s], varios, semTemas, op, s);
      });
    } else h += corpoRegras(c, f, lista, varios, semTemas, op, "");
    return h + "</tbody></table></div>";
  }
  function blocoContrato(c, cats, titulo, op) {
    var f = fichaDe(c);
    if (!f) return "";
    var g = grupos(f, cats, false);
    if (!g.length) return '<div class="ctr-bloco"><h3>' + titulo + '</h3><p class="mudo">O contrato não traz regra disso.</p></div>';
    return '<div class="ctr-bloco"><h3>' + titulo + ' <span class="ctr-fonte">' + g.length + (g.length === 1 ? " regra" : " regras") + "; a linha abre o trecho do contrato</span></h3>" + tabelaRegras(c, f, g, false, op) + "</div>";
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
      var alteradas = 0, todas = grupos(f, CATS, false), pri = todas.filter(prioritaria);
      f.contratos.forEach(function (k) { (k.regras || []).forEach(function (r) { if (r.alterado_por) alteradas++; }); });
      var modo = estado.verRegras || "todas";
      h += '<div class="ctr-regua"><span class="ctr-fonte">' + f.contratos.reduce(function (s, k) { return s + (k.regras || []).length; }, 0) + " regras, lidas dos PDFs e editadas aqui; a linha abre o trecho, a página e os comentários</span>" +
        seg("Quais regras", "data-regras", modo, [["todas", "Por categoria"], ["setor", "Por setor"], ["prioritarias", "Prioritárias", pri.length]].concat(alteradas ? [["aditivo", "Mudadas por aditivo", alteradas]] : [])) + "</div>";
      var geral = modo === "todas" || modo === "setor";
      if (modo === "prioritarias" || (geral && pri.length)) {
        h += '<div class="ctr-bloco" style="margin-top:0"><h3>Prioritárias <span class="ctr-fonte">' + pri.length + "; as que o gestor acompanha de perto</span></h3>" +
          (pri.length ? tabelaRegras(c, f, pri, true) : '<p class="mudo">Nenhuma ainda.' + (pode(c) ? " Marque a estrela de uma regra para ela ficar aqui no alto." : "") + "</p>") + "</div>";
      }
      if (modo !== "prioritarias") {
        if (geral && !pri.length && pode(c)) h += '<p class="ctr-nota" style="margin:-4px 0 10px">Marque com a estrela as regras prioritárias de acompanhamento: elas ficam no alto.</p>';
        h += '<div class="ctr-rol"><table class="ctr-tab"><tbody>';
        // por setor (o pedido de 19/11/2026: "a parte por setor (oq performance atende, o que zeladoria etc)"): o que o
        // contrato pede de cada setor, na ordem das categorias
        if (modo === "setor") {
          var todasS = grupos(f, CATS, false).sort(function (a, b) { return CATS.indexOf(a.r.categoria) - CATS.indexOf(b.r.categoria); });
          SETORES.concat([""]).forEach(function (s) {
            var g = todasS.filter(function (x) { return setorDe(x) === s; });
            if (!g.length) return;
            var chave = "setor:" + s, ab = !!estado.grupos[chave];
            h += '<tr class="grupo"><td><button data-grupo="' + esc(chave) + '" aria-expanded="' + ab + '"><i class="ph ph-caret-' + (ab ? "down" : "right") + '" aria-hidden="true"></i>' + esc(s || "Sem setor") +
              '<span class="g-n">' + g.length + (g.length === 1 ? " regra" : " regras") + "</span></button></td></tr>";
            if (ab) h += '<tr><td style="padding:0">' + tabelaRegras(c, f, g, false, {sub: "categoria"}) + "</td></tr>";
          });
        } else CATS.forEach(function (cat) {
          var g = grupos(f, [cat], modo === "aditivo");
          if (!g.length) return;
          var ab = modo === "aditivo" || !!estado.grupos[cat], mud = g.filter(function (x) { return x.r.alterado_por; }).length;
          h += '<tr class="grupo"><td><button data-grupo="' + esc(cat) + '" aria-expanded="' + ab + '"><i class="ph ph-caret-' + (ab ? "down" : "right") + '" aria-hidden="true"></i>' + esc(cat) +
            '<span class="g-n">' + g.length + (g.length === 1 ? " regra" : " regras") + (mud ? ", " + mud + " por aditivo" : "") + "</span></button></td></tr>";
          if (ab) h += '<tr><td style="padding:0">' + tabelaRegras(c, f, g) + "</td></tr>";
        });
        h += novo(c, "regra", "Incluir regra") + "</tbody></table></div>";
        var lac = [], porTxt = {};
        f.contratos.forEach(function (k) { (k.lacunas || []).forEach(function (l) { if (!porTxt[l]) { porTxt[l] = []; lac.push(l); } porTxt[l].push(rotuloK(k)); }); });
        if (lac.length) h += '<div class="ctr-bloco"><details><summary><h3 style="display:inline">O que o PDF não diz <span class="ctr-fonte">' + lac.length + "</span></h3></summary><ul class=\"lacunas\">" + lac.map(function (l) {
          return "<li>" + esc(l) + '<span class="mudo">' + (f.contratos.length < 2 ? "" : porTxt[l].length === f.contratos.length ? " (todos)" : " (" + esc(porTxt[l].join("; ")) + ")") + "</span></li>";
        }).join("") + "</ul></details></div>";
      }
    } else {
      h += '<div class="ctr-vazio"><p>Este cliente não tem PDF de contrato lido: nenhuma regra ainda.' + (pode(c) ? " Inclua as regras aqui; cada uma vai ao histórico." : "") + "</p></div>";
      if (pode(c)) h += '<div class="ctr-rol"><table class="ctr-tab"><tbody>' + novo(c, "regra", "Incluir regra") + "</tbody></table></div>";
    }
    return h + dadosDoContrato(c);
  }
  /* ── os pontos de atenção e de divergência (19/11/2026; nexus/contratos/pontos.py) ────────────────────────────────
     O pedido: "uma parte bacana também de ponto de atenção e pontos de divergência do contrato" (o "Pontos a resolver"
     do Radar da Zeladoria). Resolver pede o que se decidiu, o motivo e a prova (Levi: "Com motivo e prova"). */
  var NIVEL = {atencao: ["Atenção", "t-critico"], divergencia: ["Divergência", "t-alerta"]};
  var ORIGEM = {conta: "conta do Nexus", leitor: "lido dos PDFs", planilha: "dados do contrato × PDF", radar: "Radar da Zeladoria", incluido: "incluído"};
  function pontosDe(c) { return (R.pontos || {})[c.cliente] || []; }
  function linhaPonto(c, p) {
    var n = NIVEL[p.nivel] || NIVEL.atencao, res = p.resolvido;
    var origem = p.origem === "incluido" ? "incluído por " + esc(p.quem) + " em " + esc(p.quando) : ORIGEM[p.origem] || "";
    var acao = "";
    if (pode(c)) {
      if (res) acao = '<button type="button" class="ctr-link" data-ed-tipo="resolucao" data-ed-ids="' + esc(res.id) + '" data-ed-cliente="' + esc(c.cliente) + '">reabrir</button>';
      else acao = '<button type="button" class="gc-btn gc-btn--ui gc-btn--contorno" data-ed-tipo="resolucao" data-ed-novo="1" data-ed-cliente="' + esc(c.cliente) +
        '" data-ed-preset="' + esc(JSON.stringify({ponto_id: p.id, ponto_texto: (p.tema + ": " + p.texto).slice(0, 280)})) + '">Resolver</button>' +
        (p.origem === "incluido" ? " " + lapis(c, "ponto", [p.id], "Editar este ponto") : "");
    }
    return '<tr class="ctr-ponto-l"><td><span class="ctr-pill ' + (res ? "t-neutro" : n[1]) + '">' + n[0] + "</span></td><td><b>" + esc(p.tema) + "</b> " + esc(p.texto) +
      (p.prevalece ? '<span class="sub">Prevalece: ' + esc(p.prevalece) + "</span>" : "") +
      (res ? '<span class="sub">Resolvido por ' + esc(res.quem) + " em " + esc(res.quando) + ": " + esc(res.como) + "</span>" : "") +
      '</td><td class="ctr-quais">' + (p.onde ? '<span title="' + esc(p.onde_inteiro || p.onde) + '">' + esc(p.onde) + "</span><br>" : "") + origem + (p.setor ? "; " + esc(p.setor) : "") + '</td><td class="r" style="white-space:nowrap">' + acao + "</td></tr>";
  }
  function rPontos(c) {
    var ps = pontosDe(c), ab = ps.filter(function (p) { return !p.resolvido; }), rs = ps.filter(function (p) { return p.resolvido; });
    var na = ab.filter(function (p) { return p.nivel === "atencao"; }).length;
    var h = '<div class="ctr-regua"><span class="ctr-fonte">' + (ab.length ? ab.length + (ab.length === 1 ? " aberto" : " abertos") + ": " + na + " de atenção e " + (ab.length - na) + " de divergência" : "Nenhum ponto aberto") +
      ". Atenção: vencido ou vencendo em até 60 dias, falta documento ou outro ponto a resolver. Divergência: documentos do mesmo contrato dizem coisas diferentes (alinhar com o cliente qual vale).</span></div>";
    if (!R.radar_lido) h += '<p class="ctr-nota c-alerta">Os pontos do Radar da Zeladoria não vieram agora: os outros estão aqui; recarregue em alguns minutos.</p>';
    h += '<div class="ctr-rol"><table class="ctr-tab ctr-tab-pontos"><thead><tr><th>Tipo</th><th>Ponto</th><th>De onde</th><th></th></tr></thead><tbody>' +
      (ab.length ? ab.map(function (p) { return linhaPonto(c, p); }).join("") : '<tr><td colspan="4" class="mudo">Nenhum ponto aberto neste contrato.</td></tr>') +
      novo(c, "ponto", "Incluir ponto de atenção ou divergência") + "</tbody></table></div>";
    if (rs.length) h += '<div class="ctr-bloco"><details><summary><h3 style="display:inline">Resolvidos <span class="ctr-fonte">' + rs.length + "</span></h3></summary>" +
      '<div class="ctr-rol"><table class="ctr-tab ctr-tab-pontos"><tbody>' + rs.map(function (p) { return linhaPonto(c, p); }).join("") + "</tbody></table></div></details></div>";
    return h;
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
  // os feriados nacionais (os fixos e os da Páscoa): o dia útil não cai neles
  function pascoa(a) {
    var b = a % 19, c = Math.floor(a / 100), d = a % 100, e = Math.floor(c / 4), f = c % 4, g = Math.floor((c + 8) / 25), h = Math.floor((c - g + 1) / 3),
      i = (19 * b + c - e - h + 15) % 30, k = Math.floor(d / 4), l = d % 4, m = (32 + 2 * f + 2 * k - i - l) % 7, n = Math.floor((b + 11 * i + 22 * m) / 451),
      mes = Math.floor((i + m - 7 * n + 114) / 31), dia = ((i + m - 7 * n + 114) % 31) + 1;
    return new Date(a, mes - 1, dia);
  }
  function iso(d) { return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); }
  function feriados(a) {
    var p = pascoa(a), f = {};
    ["01-01", "04-21", "05-01", "09-07", "10-12", "11-02", "11-15", "11-20", "12-25"].forEach(function (x) { f[a + "-" + x] = 1; });
    [-48, -47, -2, 60].forEach(function (k) { f[iso(new Date(p.getFullYear(), p.getMonth(), p.getDate() + k))] = 1; });
    return f;
  }
  function diasUteis(a, m) {
    var fer = feriados(a), out = [], n = new Date(a, m + 1, 0).getDate();
    for (var d = 1; d <= n; d++) { var x = new Date(a, m, d), w = x.getDay(); if (w !== 0 && w !== 6 && !fer[iso(x)]) out.push(iso(x)); }
    return out;
  }
  var DSEM = {domingo: 0, segunda: 1, "terça": 2, quarta: 3, quinta: 4, sexta: 5, "sábado": 6};
  var PASSO = {trimestral: 3, semestral: 6, anual: 12};
  // os dias do mês em que a recorrência cai (vazio quando falta o dia: a lista diz "defina o dia")
  function ocorrencias(rec, a, m) {
    var out = [], n = new Date(a, m + 1, 0).getDate();
    if (rec.frequencia === "semanal") {
      if (DSEM[rec.dia_semana] == null) return [];
      for (var d = 1; d <= n; d++) if (new Date(a, m, d).getDay() === DSEM[rec.dia_semana]) out.push(iso(new Date(a, m, d)));
    } else {
      var passo = PASSO[rec.frequencia] || 1;
      if (passo > 1) { if (!rec.mes_inicio) return []; if (((m + 1 - rec.mes_inicio) % passo + passo) % passo) return []; }
      if (rec.dia_util) { var u = diasUteis(a, m); if (u[rec.dia_util - 1]) out.push(u[rec.dia_util - 1]); }
      else if (rec.dia_mes) out.push(iso(new Date(a, m, Math.min(rec.dia_mes, n))));
    }
    return out.filter(function (x) { return (!rec.inicio || x >= rec.inicio) && (!rec.fim || x <= rec.fim); });
  }
  function quandoRec(rec) {
    var f = rec.frequencia || "", d = rec.frequencia === "semanal" ? (rec.dia_semana ? "às " + rec.dia_semana + "s" : "") :
      rec.dia_util ? rec.dia_util + "º dia útil" : rec.dia_mes ? "dia " + rec.dia_mes : "";
    return f + (d ? ", " + d : "") + (PASSO[f] && rec.mes_inicio ? " (a partir de " + MESES[rec.mes_inicio - 1] + ")" : "") + (d || f === "" ? "" : "; defina o dia");
  }
  // as sugeridas: as regras do contrato com frequência escrita (e o dia, quando o texto traz); a do mesmo nome em vários
  // contratos do cliente sai uma vez; a confirmada e a descartada não voltam
  function sugeridas(c) {
    var f = fichaDe(c), out = [], vistas = {};
    if (!f) return out;
    var confirmadas = {}; (R.recorrencias || []).forEach(function (r) { if (r.origem_regra) confirmadas[r.origem_regra] = 1; });
    f.contratos.forEach(function (k) {
      (k.regras || []).forEach(function (r) {
        if (["Entregáveis", "Outras obrigações", "Medição e faturamento"].indexOf(r.categoria) < 0) return;
        var t = semAcento([r.nome, r.periodicidade, r.prazo, r.vigente].join(" "));
        if (/sob demanda|conforme necessidade|quando solicitado/.test(t)) return;
        var freq = /semanal|toda (segunda|terca|quarta|quinta|sexta)/.test(t) ? "semanal" : /trimestral/.test(t) ? "trimestral" : /semestral/.test(t) ? "semestral" :
          /anual/.test(t) ? "anual" : /mensal|do mes|todo mes|cada mes/.test(t) ? "mensal" : "";
        if (!freq) return;
        var s = {nome: codigos(r.nome).texto, frequencia: freq, origem_regra: r._id, tipo: /medicao|faturamento|bm\b/.test(t) ? "Medição / faturamento (BM)" : /reuniao/.test(t) ? "Reunião periódica com cliente" : "Entregável ao cliente (RMO, relatório)", setor: r.setor || ""};
        var m;
        if (freq === "semanal") { m = t.match(/(segunda|terca|quarta|quinta|sexta)/); if (m) s.dia_semana = {terca: "terça"}[m[1]] || m[1]; }
        else if ((m = t.match(/(\d+)\s*[ºo°]?\s*dia util/))) s.dia_util = +m[1];
        else if ((m = t.match(/ate o dia (\d+)|dia (\d+) de cada mes|todo dia (\d+)/))) s.dia_mes = +(m[1] || m[2] || m[3]);
        var ch = semAcento(s.nome) + "|" + freq;
        if (vistas[ch] || confirmadas[r._id] || (R.descartes || []).indexOf("s" + r._id) >= 0) { vistas[ch] = 1; return; }
        vistas[ch] = 1; s.id = "s" + r._id; s.regra = vale(r);
        out.push(s);
      });
    });
    return out;
  }
  function tomOc(dia, entregue) {
    if (entregue) return "ok";
    var dias = Math.round((new Date(dia + "T12:00:00") - new Date(R.hoje + "T12:00:00")) / 864e5);
    return dias < 0 ? "critico" : dias <= 7 ? "alerta" : "neutro";
  }
  function rCalendario(c) {
    var obr = obrDe(c), hj = new Date(R.hoje + "T12:00:00"), base = new Date(hj.getFullYear(), hj.getMonth() + (estado.mesCal || 0), 1);
    var ano = base.getFullYear(), mes = base.getMonth(), nd = new Date(ano, mes + 1, 0).getDate(), ini = new Date(ano, mes, 1).getDay(), total = Math.ceil((ini + nd) / 7) * 7;
    var titulo = MESES[mes].charAt(0).toUpperCase() + MESES[mes].slice(1) + " de " + ano;
    var recs = (R.recorrencias || []).filter(function (r) { return r.cliente === c.cliente; }), ent = (R.entregas || []).filter(function (e) { return e.cliente === c.cliente; });
    var oc = [];
    recs.forEach(function (r) { ocorrencias(r, ano, mes).forEach(function (d) {
      var e = ent.filter(function (x) { return x.recorrencia_id === r._id && x.data === d; })[0];
      oc.push({rec: r, dia: d, entrega: e, tom: tomOc(d, e)});
    }); });
    oc.sort(function (a, b) { return a.dia.localeCompare(b.dia) || a.rec.nome.localeCompare(b.rec.nome); });
    var h = '<div class="ctr-regua"><span class="ctr-mesnav"><button type="button" class="ctr-lapis" data-mes="-1" title="Mês anterior"><i class="ph ph-caret-left" aria-hidden="true"></i><span class="so-leitor">Mês anterior</span></button><h2>' + titulo +
      '</h2><button type="button" class="ctr-lapis" data-mes="1" title="Próximo mês"><i class="ph ph-caret-right" aria-hidden="true"></i><span class="so-leitor">Próximo mês</span></button>' +
      (estado.mesCal ? '<button type="button" class="ctr-link" data-mes="0">hoje</button>' : "") + '</span><div class="ctr-legenda"><span><i class="ctr-ponto p-ok"></i>entregue</span><span><i class="ctr-ponto p-alerta"></i>em até 7 dias</span><span><i class="ctr-ponto p-critico"></i>atrasada</span><span><i class="ctr-ponto p-neutro"></i>prevista</span><span><i class="ctr-ponto p-sem_data"></i>sem data</span></div></div>';
    h += '<div class="ctr-grade"><div class="ctr-cal" role="grid" aria-label="' + titulo + '">' + ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"].map(function (d) { return '<div class="dsem">' + d + "</div>"; }).join("");
    for (var i = 0; i < total; i++) {
      var dia = i - ini + 1, fora = dia < 1 || dia > nd, eHoje = !fora && iso(new Date(ano, mes, dia)) === R.hoje, di = fora ? "" : iso(new Date(ano, mes, dia));
      h += '<div class="dia' + (fora ? " fora" : "") + (eHoje ? " hoje" : "") + '"><span class="n">' + (fora ? "" : dia) + (eHoje ? " hoje" : "") + "</span>" +
        (fora ? "" : obr.filter(function (o) { return o.vencimento === di; }).map(function (o) { return '<span class="ctr-ev ' + o.tom + '" title="' + esc(o.descricao + (o.executor ? ", " + o.executor : "") + ", " + o.status) + '">' + esc(o.tipo || o.descricao) + "</span>"; }).join("") +
          oc.filter(function (x) { return x.dia === di; }).map(function (x) { return '<span class="ctr-ev ' + x.tom + '" title="' + esc(x.rec.nome + (x.entrega ? ", entregue (" + x.entrega._quem + ")" : "")) + '">' + (x.entrega ? '<i class="ph ph-check" aria-hidden="true"></i> ' : "") + esc(x.rec.nome) + "</span>"; }).join("")) + "</div>";
    }
    h += "</div>";
    // ao lado: as entregas do mês com o check (a gestora: "vai dando o checkzinho que foi entregue"), e as obrigações da planilha
    var porDia = {}; oc.forEach(function (x) { (porDia[x.dia] = porDia[x.dia] || []).push(x); });
    h += '<aside class="ctr-lat"><h3>Entregas de ' + MESES[mes] + "</h3>" + (oc.length ? Object.keys(porDia).map(function (d) {
      return '<p class="ctr-dia-t">' + dBR(d) + "</p><ul class=\"ctr-entregas\">" + porDia[d].map(function (x) {
        return '<li><label class="ctr-check"><input type="checkbox" data-entregar="' + esc(x.rec._id + "|" + x.dia) + '"' + (x.entrega ? ' data-entrega-id="' + esc(x.entrega._id) + '" checked' : "") + (pode(c) ? "" : " disabled") + '><i class="ctr-ponto p-' + x.tom + '" aria-hidden="true"></i><span>' + esc(x.rec.nome) +
          (x.entrega ? '<small>entregue: ' + esc(x.entrega._quem) + ", " + esc(x.entrega._quando) + "</small>" : x.rec.setor ? "<small>" + esc(x.rec.setor) + "</small>" : "") + "</span></label></li>";
      }).join("") + "</ul>";
    }).join("") : '<p class="mudo" style="font-size:12.5px">Nenhuma recorrência confirmada cai neste mês.</p>');
    var atr = obr.filter(function (o) { return o.tom === "critico"; }), prox = obr.filter(function (o) { return o.tom === "alerta" || o.tom === "neutro"; }).slice(0, 6), sd = obr.filter(function (o) { return o.tom === "sem_data"; });
    function item(o) { return '<li><i class="ctr-ponto p-' + o.tom + '"></i><span>' + esc(o.descricao) + "<small>" + (o.vencimento ? (o.tom === "critico" ? "venceu em " : "vence em ") + dBR(o.vencimento) : esc(o.status || "sem vencimento")) + (o.executor ? ", " + esc(o.executor) : "") + "</small></span></li>"; }
    h += "<h3>Obrigações atrasadas</h3><ul>" + (atr.map(item).join("") || '<li class="mudo">Nenhuma.</li>') + "</ul><h3>Próximas</h3><ul>" + (prox.map(item).join("") || '<li class="mudo">Nenhuma.</li>') + "</ul>" +
      (sd.length ? "<h3>Sem data</h3><ul>" + sd.map(item).join("") + "</ul>" : "") + "</aside></div>";
    // as recorrências: as sugeridas do contrato para confirmar, e as confirmadas
    var sug = sugeridas(c);
    if (sug.length) h += '<div class="ctr-bloco"><h3>Sugeridas do contrato <span class="ctr-fonte">' + sug.length + "; o gestor confirma (entra no calendário) ou descarta</span></h3><div class=\"ctr-rol\"><table class=\"ctr-tab\"><thead><tr><th>Entrega ou rotina</th><th>Quando</th><th>O que o contrato diz</th><th></th></tr></thead><tbody>" +
      sug.map(function (x) {
        var completo = x.frequencia === "semanal" ? !!x.dia_semana : PASSO[x.frequencia] ? false : !!(x.dia_util || x.dia_mes);
        var preset = esc(JSON.stringify({nome: x.nome, tipo: x.tipo, frequencia: x.frequencia, dia_semana: x.dia_semana || "", dia_util: x.dia_util || "", dia_mes: x.dia_mes || "", setor: x.setor, origem_regra: x.origem_regra}));
        return "<tr><td>" + esc(x.nome) + "</td><td>" + esc(quandoRec(x)) + '</td><td class="ctr-quais">' + esc(String(x.regra || "").slice(0, 160)) + '</td><td class="r" style="white-space:nowrap">' +
          (pode(c) ? (completo ? '<button type="button" class="gc-btn gc-btn--ui gc-btn--contorno" data-confirmar="' + preset + '">Confirmar</button> ' :
            '<button type="button" class="gc-btn gc-btn--ui gc-btn--contorno" data-ed-tipo="recorrencia" data-ed-novo="1" data-ed-cliente="' + esc(c.cliente) + '" data-ed-preset="' + preset + '">Definir o dia</button> ') +
            '<button type="button" class="ctr-link" data-descartar="' + esc(x.id) + '">descartar</button>' : "") + "</td></tr>";
      }).join("") + "</tbody></table></div></div>";
    h += '<div class="ctr-bloco"><h3>Recorrências do calendário <span class="ctr-fonte">' + recs.length + "</span></h3><div class=\"ctr-rol\"><table class=\"ctr-tab\"><thead><tr><th>Entrega ou rotina</th><th>Quando</th><th>Setor</th><th></th></tr></thead><tbody>" +
      recs.map(function (r) { return "<tr><td>" + nomeHtml(r.nome) + editado(r, ["nome", "frequencia", "dia_util", "dia_mes", "dia_semana"]) + "</td><td>" + esc(quandoRec(r)) + "</td><td>" + esc(r.setor || "") + '</td><td class="r">' + lapis(c, "recorrencia", [r._id], "Editar esta recorrência") + "</td></tr>"; }).join("") +
      novo(c, "recorrencia", "Incluir recorrência", {tipo: "Entregável ao cliente (RMO, relatório)"}) + "</tbody></table></div></div>";
    h += '<div class="ctr-bloco"><h3>Todas as obrigações (' + obr.length + ")</h3>" + tabelaObrig(c, obr) + "</div>";
    return h + blocoContrato(c, ["Rotinas"], "Rotinas que o contrato pede");
  }
  /* ── atendimento, entregáveis, metas, financeiro ────────────────────────────────────────────────────────────────── */
  function rAtendimento(c) {
    var b = blocoContrato(c, ["SLA"], "O atendimento que o contrato pede", {porSetor: true, sub: ""});
    return (b || '<div class="ctr-vazio"><p>Sem PDF do contrato lido: o SLA está nos Dados do contrato, na aba Regras.</p></div>') +
      '<p class="ctr-nota">O atendimento feito em cada usina (as OS do mês) não está na planilha de controle nem no contrato.</p>';
  }
  function rEntregaveis(c) {
    var lista = obrDe(c).filter(function (o) { return o.entregavel; }), par0 = R.parametros || {}, f = fichaDe(c), h = "";
    var vencidos = lista.filter(function (o) { return o.tom === "ok" || o.tom === "critico"; }), noPrazo = lista.filter(function (o) { return o.no_prazo; }).length;
    if (f) {
      // a gestora que pediu a visão, 18/11/2026: "ter uma que é uma entrega única e ter um que seja recorrências"
      var g = grupos(f, ["Entregáveis"], false), rec = [], unica = [];
      g.forEach(function (x) { (/mensal|semanal|quinzenal|trimestral|semestral|anual|diari|todo |toda |cada |por mes|por semana/.test(semAcento([x.r.periodicidade, x.r.prazo, vale(x.r), x.r.nome].join(" "))) ? rec : unica).push(x); });
      h += dobra("rec", "Recorrentes", rec.length + "; o que o contrato pede de novo a cada período (o calendário mostra as datas)",
        function () { return rec.length ? tabelaRegras(c, f, rec, true, {porSetor: true, sub: ""}) : '<p class="mudo">Nenhuma.</p>'; }, "margin-top:6px");
      h += dobra("unica", "Entrega única", unica.length + "; uma vez, num marco do contrato",
        function () { return unica.length ? tabelaRegras(c, f, unica, true, {porSetor: true, sub: ""}) : '<p class="mudo">Nenhuma.</p>'; });
    }
    return h + dobra("lanc", "Entregáveis e medições lançados", lista.length + "; " + noPrazo + " de " + vencidos.length +
      " já vencidos entregues no prazo" + (par0.meta_entregaveis != null ? "; meta " + pct(100 * par0.meta_entregaveis, 0) + "%" : ""),
      function () { return tabelaObrig(c, lista, {tipo: "Entregável ao cliente (RMO, relatório)", status: "Não iniciado"}, "Incluir entregável"); });
  }
  // um bloco que abre e fecha pelo título; recolhido, só o título e a contagem
  function dobra(id, titulo, fonte, corpo, estilo) {
    var ab = !!DOBRAS[id];
    return '<div class="ctr-bloco"' + (estilo ? ' style="' + estilo + '"' : "") + '><h3><button type="button" class="ctr-dobra" data-dobra="' + id + '" aria-expanded="' + ab + '"><i class="ph ph-caret-' +
      (ab ? "down" : "right") + '" aria-hidden="true"></i>' + titulo + ' <span class="ctr-fonte">' + fonte + "</span></button></h3>" + (ab ? corpo() : "") + "</div>";
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
      blocoContrato(c, ["Disponibilidade e desempenho", "Benefícios", "Penalidades"], "Metas, bônus e penalidades do contrato", {porSetor: true, sub: "categoria"});
  }
  var SIT_ADIC = {"Faturado": "t-ok", "Aprovado — faturar": "t-verde", "Aguardando cliente": "t-alerta", "Memória a enviar": "t-neutro", "Memória atrasada": "t-critico", "Reprovado": "t-neutro"};
  // a gestora que pediu a visão, 18/11/2026: "o supervisor conseguir também sinalizar que para março vai existir esse acréscimo [...] ou uma
  // penalidade de menos tanto [...] aqui é a rotina financeira do contrato [...] pode ser uma tabelinha"
  function mesAMes(c) {
    var hj = new Date(R.hoje + "T12:00:00"), lan = (R.lancamentos || []).filter(function (l) { return l.cliente === c.cliente; }), ad = adicDe(c), meses = {};
    var ini = c.inicio ? new Date(c.inicio + "T12:00:00") : null, de = new Date(hj.getFullYear(), hj.getMonth() - 11, 1);
    if (ini && ini > de) de = new Date(ini.getFullYear(), ini.getMonth(), 1);
    for (var d = new Date(de); d <= new Date(hj.getFullYear(), hj.getMonth() + 1, 1); d = new Date(d.getFullYear(), d.getMonth() + 1, 1)) meses[d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0")] = 1;
    lan.forEach(function (l) { if (l.mes) meses[l.mes] = 1; });
    var lista = Object.keys(meses).sort().reverse(), mensal = c.valor_mensal;
    function soma(l) { return l.reduce(function (s, x) { return s + (+x.valor || 0); }, 0); }
    var h = '<div class="ctr-regua"><h2>Mês a mês</h2><span class="ctr-fonte">a mensalidade do contrato, os serviços adicionais e o que o gestor lança (acréscimos, penalidades)</span></div>' +
      '<div class="ctr-rol"><table class="ctr-tab"><thead><tr><th>Mês</th><th class="r">Mensalidade</th><th class="r">Adicionais</th><th class="r">Acréscimos</th><th class="r">Penalidades e descontos</th><th class="r">Total previsto</th></tr></thead><tbody>' +
      lista.map(function (m) {
        var a = soma(ad.filter(function (x) { return x.mes === m; })), mais = soma(lan.filter(function (x) { return x.mes === m && (x.tipo === "Acréscimo" || x.tipo === "Outro"); })),
          menos = soma(lan.filter(function (x) { return x.mes === m && (x.tipo === "Penalidade" || x.tipo === "Desconto"); })), p = m.split("-");
        return "<tr><td>" + MESES[+p[1] - 1] + " de " + p[0] + '</td><td class="r num">' + (mensal != null ? brl(mensal) : '<span class="mudo">—</span>') + '</td><td class="r num">' + (a ? brl(a) : '<span class="mudo">—</span>') +
          '</td><td class="r num">' + (mais ? brl(mais) : '<span class="mudo">—</span>') + '</td><td class="r num' + (menos ? " c-critico" : "") + '">' + (menos ? "−" + brl(menos) : '<span class="mudo">—</span>') +
          '</td><td class="r num">' + (mensal != null ? brl(mensal + a + mais - menos) : '<span class="mudo">—</span>') + "</td></tr>";
      }).join("") + "</tbody></table></div>";
    h += '<div class="ctr-bloco"><h3>Lançamentos <span class="ctr-fonte">' + lan.length + "</span></h3><div class=\"ctr-rol\"><table class=\"ctr-tab\"><thead><tr><th>Mês</th><th>Tipo</th><th class=\"r\">Valor</th><th>Descrição</th><th></th></tr></thead><tbody>" +
      lan.sort(function (a, b) { return String(b.mes).localeCompare(String(a.mes)); }).map(function (l) {
        return "<tr><td>" + esc(l.mes) + "</td><td>" + esc(l.tipo) + '</td><td class="r num">' + brl(+l.valor || 0) + "</td><td>" + esc(l.descricao || "") + '<span class="sub">' + esc(l._quem) + ", " + esc(l._quando) + '</span></td><td class="r">' + lapis(c, "lancamento", [l._id], "Editar este lançamento") + "</td></tr>";
      }).join("") + novo(c, "lancamento", "Incluir lançamento (acréscimo, penalidade, desconto)", {mes: R.hoje.slice(0, 7), tipo: "Acréscimo"}) + "</tbody></table></div></div>";
    return h;
  }
  function rFinanceiro(c) {
    return mesAMes(c) + '<div class="ctr-bloco">' + rFinanceiroAdic(c) + "</div>";
  }
  function rFinanceiroAdic(c) {
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

  /* ── os indicadores do ano contratual (26/11/2026; nexus/contratos/indicadores.py) ─────────────────────────────────
     A sugestão de 26/11/2026, com o mockup: "meses do ano contratual nas colunas, usinas nas linhas", as preventivas, a
     supressão vegetal e a lavagem, o PR e a disponibilidade expurgada contra a meta, e no alto os números do contrato.
     Levi, vendo a 1ª versão no ar: "eu queria no mesmo estilo, pintadinho lá do mockup [...] Antes da usina, é bom
     mostrar também o cliente [...] uma tabela por cliente [...] Eu tô sentindo falta desses KPIs de cima. Do mockup [...]
     Se baseia no mockup". Daí: a barra (ano, metas, visão, exportar), os quatro cartões com o mês a mês em barrinhas, o
     contrato inteiro antes das usinas, a célula pintada pelo estado, as três primeiras usinas com problema abertas e o
     resto numa linha "Mais N usinas". */
  var IND = {}, indVisao = "completa", indAbertas = {}, indMais = {}, indAnoAberto = false;
  var VIS = [["completa", "Completa"], ["kpis", "Só KPIs"], ["manut", "Só manutenções"]];
  var SUB_IND = {MPM: "mensal", MPS: "semestral", MPA: "anual", rocada: "data", lavagem: "data", pr: "%", disp: "%"};
  function pedirInd(c, n) {
    var ch = c.cliente + "|" + (n || "");
    if (IND[ch] && !IND[ch].montando) return IND[ch];
    if (!IND[ch] || IND[ch].montando === "pedido") {
      IND[ch] = {carregando: true};
      pedir(CAMINHO + "indicadores.json?cliente=" + encodeURIComponent(c.cliente) + (n ? "&ano=" + n : "")).then(function (d) {
        if (d && d.montando) { IND[ch] = {montando: true}; setTimeout(function () { IND[ch].montando = "pedido"; if (estado.aba === "indicadores") render(); }, 3000); }
        else IND[ch] = d || {erro: "sem resposta"};
        if (estado.aba === "indicadores") render();
      }).catch(function (e) { IND[ch] = {erro: (e && e.message) || "não respondeu"}; if (estado.aba === "indicadores") render(); });
    }
    return IND[ch];
  }
  // a célula é um botão: o clique abre a gaveta que explica o dado (Levi, 26/11/2026: "esses botões coloridos aí fossem
  // clicáveis e aparecesse a confirmação da resposta no card lateral [...] qual é a OS e tudo mais")
  function celInd(x, ac, cel) {
    if (!x) return "<td></td>";
    var vazio = x.txt === "—" || x.txt === "s/d";
    return '<td class="r' + (ac ? " ind-ac" : " ind-m") + '">' + (x.txt === "" ? "" : '<button type="button" class="ind' + (x.tom ? " t-" + x.tom : "") + (vazio ? " ind-vazio" : "") + '"' +
      (cel ? ' data-cel="' + esc(cel) + '"' : "") + (x.dica ? ' title="' + esc(x.dica) + '"' : "") + ">" + esc(x.txt) + "</button>") + "</td>";
  }
  function linhasInd(d, linhas, uid) {
    return linhas.filter(function (l) { return indVisao === "completa" || (indVisao === "kpis" ? l.grupo === "kpi" : l.grupo === "manut"); }).map(function (l) {
      var sub = l.sub || SUB_IND[l.id] || "";
      return '<tr class="ind-l"><td class="ind-nome">' + esc(l.nome === "Disponibilidade expurgada" ? "Disp. expurgada" : l.nome) + (sub ? " <small>" + esc(sub) + "</small>" : "") + "</td>" +
        d.meses.map(function (m) { return celInd(l.cels[m.id], false, uid + "|" + l.id + "|" + m.id); }).join("") + celInd(l.acum, true, uid + "|" + l.id + "|acum") + "</tr>";
    }).join("");
  }
  function pctTxt(v) { return String(v).replace(".", ","); }
  function barrinhas(lista) {
    return '<div class="ind-barras" aria-hidden="true">' + (lista || []).map(function (b) {
      return '<span class="ind-b t-' + esc(b.tom) + '" title="' + esc(b.rot + ": " + (b.txt || "ainda não chegou")) + '"></span>';
    }).join("") + "</div>";
  }
  function cartoesInd(c, d) {
    var r = d.resumo || {}, mt = d.metas || {}, pv = r.prev || {}, pt = r.prev_tom || {};
    function grande(v, tom) { return '<b class="ind-grande' + (tom ? " c-" + tom : "") + '">' + esc(v) + (v !== "s/d" ? "%" : "") + "</b>"; }
    function meta(x) { return x ? '<span class="ind-meta">meta ' + pctTxt(x.pct) + "</span>" : '<span class="ind-meta">sem meta no contrato</span>'; }
    function abaixo(l) { return l && l.length ? " · <b>" + l.length + (l.length === 1 ? " mês" : " meses") + " abaixo da meta</b> (" + esc(l.join(", ")) + ")" : ""; }
    var h = '<div class="ind-cartoes">';
    h += '<section class="ind-cartao"><h4><i class="ph ph-chart-line-up" aria-hidden="true"></i>PR do contrato · acumulado</h4><div class="ind-val">' + grande(r.pr, r.pr_tom) + meta(mt.pr) + "</div>" +
      '<p>' + (r.usinas_n || 0) + (r.usinas_n === 1 ? " usina" : " usinas") + ", ponderado pela potência" + abaixo(r.pr_abaixo) + "</p>" + barrinhas(r.pr_barras) + "</section>";
    h += '<section class="ind-cartao"><h4><i class="ph ph-plugs-connected" aria-hidden="true"></i>Disponibilidade expurgada · acumulada</h4><div class="ind-val">' + grande(r.disp, r.disp_tom) + meta(mt.disp) + "</div>" +
      "<p>" + (r.disp_sem_expurgo ? "sem expurgo " + esc(r.disp_sem_expurgo) + "%" : "sem expurgo no ano") + abaixo(r.disp_abaixo) + "</p>" + barrinhas(r.disp_barras) + "</section>";
    var itens = [["MPM", pv.MPM, pt.MPM], ["MPS", pv.MPS, pt.MPS], ["MPA", pv.MPA, pt.MPA], ["Supressão", r.rocada, r.rocada_tom], ["Lavagem", r.lavagem, r.lavagem_tom]];
    // cinco colunas iguais, o nome e o valor centralizados, sem texto embaixo (Levi, 26/11/2026: "a nomenclatura deles
    // centralizada e os valores centralizados [...] tem um texto enorme aí ocupando espaço"); a explicação fica na dica
    h += '<section class="ind-cartao ind-largo" title="As preventivas feitas sobre as planejadas na janela; a supressão vegetal e a lavagem feitas contra o mínimo do contrato da zeladoria">' +
      '<h4><i class="ph ph-wrench" aria-hidden="true"></i>Preventivas e serviços · feitos / plano ou mín.</h4><div class="ind-prev ind-cinco">' + itens.map(function (x) {
      var v = Array.isArray(x[1]) ? (x[1][1] ? x[1][0] + "/" + x[1][1] : "—") : (x[1] || "—");
      return "<div><small>" + x[0] + '</small><b class="' + (x[2] ? "c-" + x[2] : "") + '">' + esc(v) + "</b></div>";
    }).join("") + "</div></section>";
    h += '<section class="ind-cartao"><h4><i class="ph ph-warning" aria-hidden="true"></i>Fora da meta no ano</h4><div class="ind-prev ind-fora"><div><small>Usina·mês PR</small><b class="' + (r.fora_pr ? "c-critico" : "") + '">' + (r.fora_pr || 0) + "</b></div>" +
      '<div><small>Usina·mês Disp.</small><b class="' + (r.fora_disp ? "c-alerta" : "") + '">' + (r.fora_disp || 0) + "</b></div></div>" +
      "<p>" + (r.pior ? esc(r.pior.usina) + " responde por " + r.pior.fora + " dos " + ((r.fora_pr || 0) + (r.fora_disp || 0)) + ' · <a href="' + rota(estado.ct, "pontos") + '">abrir Pontos</a>' : (mt.pr || mt.disp ? "Nenhuma usina fora da meta no ano." : "Sem meta no contrato: grave a meta de PR e a garantia de disponibilidade em Editar dados.")) + "</p></section>";
    return h + "</div>";
  }
  function rIndicadores(c) {
    var n = estado.indAno || null, d = pedirInd(c, n);
    if (d.carregando || d.montando) return '<p class="mudo" style="padding:14px 0">Lendo os indicadores do ano contratual…</p>';
    if (d.erro) return '<p class="c-critico">Não li os indicadores: ' + esc(d.erro) + "</p>";
    if (d.sem_inicio) return '<div class="ctr-vazio"><p>Este contrato não tem o início da vigência: o ano contratual conta a partir dele.' + (pode(c) ? " Ponha a data em Editar dados." : "") + "</p></div>";
    var a = d.ano, anos = d.anos || [], mt = d.metas || {};
    function rotAno() { return d.meses[0].rot + " – " + d.meses[d.meses.length - 1].rot; }
    var nomeJanela = a.n ? a.n + "º ano contratual" : "Últimos 12 meses";
    var metaTxt = mt.pr || mt.disp ? [mt.pr ? "PR ≥ " + pctTxt(mt.pr.pct) + "%" : "", mt.disp ? "Disp. expurgada ≥ " + pctTxt(mt.disp.pct) + "%" : ""].filter(Boolean).join(" · ") +
      ' <span class="mudo">· ' + esc((mt.pr || mt.disp).origem) + "</span>" : '<span class="mudo">sem meta de PR e de disponibilidade no contrato</span>';
    var h = '<div class="ind-barra"><div class="ind-ano"><button type="button" class="ind-chip" data-ind-ano-abrir aria-expanded="' + indAnoAberto + '"><i class="ph ph-calendar-blank" aria-hidden="true"></i>' + nomeJanela + " <b>" + rotAno() + '</b> <i class="ph ph-caret-down" aria-hidden="true"></i></button>' +
      (indAnoAberto ? '<ul class="ind-anos"><li><button type="button" data-ind-ano="0"' + (!a.n ? ' aria-current="true"' : "") + ">Últimos 12 meses<small>até o mês de hoje; anda sozinho</small></button></li>" +
        anos.slice().reverse().map(function (x) {
          return '<li><button type="button" data-ind-ano="' + x.n + '"' + (x.n === a.n ? ' aria-current="true"' : "") + ">" + x.n + "º ano contratual" + (x.n === anos.length ? " (o de agora)" : "") +
            "<small>" + dBR(x.ini) + " a " + dBR(x.fim) + "</small></button></li>"; }).join("") + "</ul>" : "") + "</div>" +
      '<span class="ind-chip ind-metas"><i class="ph ph-target" aria-hidden="true"></i>Metas ' + metaTxt + "</span>" +
      '<span class="ind-dir">' + seg("Visão", "data-ind-visao", indVisao, VIS) + '<button type="button" class="ind-chip" data-ind-exportar><i class="ph ph-export" aria-hidden="true"></i>Exportar</button></span></div>';
    h += '<h2 class="ind-so-print">Indicadores · ' + esc(c.cliente) + " · " + nomeJanela.toLowerCase().replace(/^ú/, "ú") + " (" + dBR(a.ini) + " a " + dBR(a.fim) + ")</h2>";
    h += cartoesInd(c, d);
    var lg = d.ligacao || {}, notas = [];
    if (lg.pcm && lg.pcm.total > lg.pcm.ligadas) notas.push((lg.pcm.total - lg.pcm.ligadas) + " de " + lg.pcm.total + " tarefas do PCM do cliente não ligaram a uma usina pelo nome");
    if (lg.radar && lg.radar.total > lg.radar.ligadas) notas.push((lg.radar.total - lg.radar.ligadas) + " de " + lg.radar.total + " usinas do Radar não ligaram pelo nome");
    (d.avisos || []).forEach(function (x) { notas.push("Fora agora: " + x); });
    if (notas.length) h += '<p class="ctr-nota c-alerta" style="margin:0 0 8px">' + notas.map(esc).join(". ") + ".</p>";
    if (!(d.usinas || []).length) return h + '<div class="ctr-vazio"><p>Nenhuma usina do cliente no cadastro: sem usina, não há o que medir.</p></div>';
    var ch = c.cliente + "|" + a.n, ab = indAbertas[ch];
    if (!ab) { ab = indAbertas[ch] = {}; d.usinas.filter(function (u) { return u.fora; }).slice(0, 3).forEach(function (u) { ab[u.uid] = true; }); if (!Object.keys(ab).length) ab[d.usinas[0].uid] = true; }
    var mwp = d.usinas.reduce(function (s, u) { return s + (u.mwp || 0); }, 0), ncol = d.meses.length + 2;
    h += '<div class="ctr-rol"><table class="ctr-tab ctr-ind"><thead><tr><th>Usina · indicador</th>' + d.meses.map(function (m) { return '<th class="r' + (m.id === d.mes_hoje ? " ind-hoje" : "") + '">' + esc(m.rot) + "</th>"; }).join("") +
      '<th class="r ind-ac">Acum.<small>feitas / plano ou mín.</small></th></tr></thead><tbody>';
    // o cliente primeiro: o contrato inteiro (Levi: "Antes da usina, é bom mostrar também o cliente")
    h += '<tr class="ind-usina ind-total"><td colspan="' + ncol + '"><b>' + esc(c.cliente) + "</b> <span class=\"mudo\">contrato inteiro · " + d.usinas.length + (d.usinas.length === 1 ? " usina" : " usinas") +
      (mwp ? " · " + pctTxt(Math.round(mwp * 10) / 10) + " MWp" : "") + "</span></td></tr>" + linhasInd(d, d.total || [], "t");
    var mostrar = d.usinas.filter(function (u) { return ab[u.uid] !== undefined || indMais[ch]; }), resto = d.usinas.filter(function (u) { return ab[u.uid] === undefined && !indMais[ch]; });
    mostrar.forEach(function (u) {
      var aberta = !!ab[u.uid];
      h += '<tr class="ind-usina"><td colspan="' + ncol + '"><button type="button" data-ind-usina="' + u.uid + '" aria-expanded="' + aberta + '"><i class="ph ph-caret-' + (aberta ? "down" : "right") + '" aria-hidden="true"></i><b>' + esc(u.usina) + "</b>" +
        (u.mwp ? ' <span class="mudo">' + pctTxt(u.mwp) + " MWp</span>" : "") +
        (u.fora ? ' <span class="ctr-pill t-critico" title="meses com preventiva não feita, PR ou disponibilidade abaixo da meta">' + u.fora + (u.fora === 1 ? " mês fora do plano ou da meta" : " meses fora do plano ou da meta") + "</span>" : "") + "</button></td></tr>";
      if (aberta) h += linhasInd(d, u.linhas, u.uid);
    });
    if (resto.length) h += '<tr class="ind-mais"><td colspan="' + ncol + '"><button type="button" data-ind-mais><i class="ph ph-caret-down" aria-hidden="true"></i>Mais ' + resto.length + (resto.length === 1 ? " usina" : " usinas") + ": " +
      esc(resto.map(function (u) { return u.usina; }).slice(0, 12).join(", ") + (resto.length > 12 ? " e mais " + (resto.length - 12) : "")) + "</button></td></tr>";
    h += "</tbody></table></div>";
    // a legenda: cada amostra do mesmo tamanho, com o valor no meio (Levi: "os valores centralizados [...] tá meio frouxo")
    var LEG = [["t-ok", "1/1", "feita no mês"], ["t-critico", "0/1", "não feita"], ["ind-vazio", "—", "sem plano no mês"], ["t-ok", "12/09", "serviço feito, data"],
      ["t-alerta", "3/4", "feitas / mínimo do contrato"], ["t-ok", "82,1", "na meta"], ["t-alerta", "77,4", "até 2 pontos abaixo"], ["t-critico", "71,0", "abaixo da meta"],
      ["t-info", "98,9*", "com expurgo no mês"], ["ind-vazio", "s/d", "sem dado no banco"]];
    h += '<div class="ind-legenda">' + LEG.map(function (x) { return '<span><i class="ind ' + x[0] + '">' + esc(x[1]) + "</i>" + esc(x[2]) + "</span>"; }).join("") +
      '<span class="ind-dica-dir">Clique na célula: a gaveta explica o dado, com as OS.</span></div>';
    return h;
  }

  /* ── a gaveta da célula (26/11/2026): desliza da direita e explica o dado; a OS abre o card do Fracttal ───────── */
  var gav = null;
  function gaveta() {
    if (gav) return gav;
    var veu = document.createElement("div"); veu.className = "ctr-veu"; veu.hidden = true;
    var el = document.createElement("aside"); el.className = "ctr-gaveta ctr"; el.hidden = true; el.setAttribute("role", "dialog"); el.setAttribute("aria-modal", "true"); el.setAttribute("aria-labelledby", "ctr-gav-t");
    document.body.appendChild(veu); document.body.appendChild(el);
    veu.addEventListener("click", fecharGaveta);
    el.addEventListener("click", function (e) {
      var b;
      if (e.target.closest("[data-gav-fechar]")) { fecharGaveta(); return; }
      if ((b = e.target.closest("[data-os-abrir]"))) {
        var id = b.getAttribute("data-os-abrir"), folio = b.getAttribute("data-os-folio"), st = b.getAttribute("data-os-status") || "";
        if (window.NexusOsCard) { if (id) window.NexusOsCard.abrir(id, {status: st, folio: folio}); else window.NexusOsCard.abrirFolio(folio, {status: st}); }
      }
    });
    gav = {veu: veu, el: el};
    return gav;
  }
  function fecharGaveta() {
    if (!gav || gav.el.hidden) return;
    gav.el.classList.remove("aberta"); gav.veu.classList.remove("aberta");
    setTimeout(function () { gav.el.hidden = true; gav.veu.hidden = true; }, 220);
  }
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && gav && !gav.el.hidden && !document.querySelector(".os-moldura, iframe.os-card")) fecharGaveta(); });
  function abrirGaveta(c, cel) {
    var g = gaveta(), p = cel.split("|");
    g.el.innerHTML = '<button type="button" class="ctr-gav-fechar" data-gav-fechar aria-label="Fechar">×</button><p class="mudo" style="padding:30px 0">Lendo o dado…</p>';
    g.veu.hidden = false; g.el.hidden = false;
    requestAnimationFrame(function () { g.el.classList.add("aberta"); g.veu.classList.add("aberta"); });
    pedir(CAMINHO + "indicadores/celula.json?cliente=" + encodeURIComponent(c.cliente) + (estado.indAno ? "&ano=" + estado.indAno : "") +
      "&uid=" + encodeURIComponent(p[0]) + "&linha=" + encodeURIComponent(p[1]) + "&mes=" + encodeURIComponent(p[2])).then(function (d) {
      g.el.innerHTML = conteudoGaveta(d);
    }).catch(function (e) { g.el.innerHTML = '<button type="button" class="ctr-gav-fechar" data-gav-fechar aria-label="Fechar">×</button><p class="c-critico" style="padding:30px 0">Não li o dado: ' + esc((e && e.message) || "") + "</p>"; });
  }
  function conteudoGaveta(d) {
    var h = '<button type="button" class="ctr-gav-fechar" data-gav-fechar aria-label="Fechar">×</button><div class="ctr-gav-cab"><h2 id="ctr-gav-t">' + esc(d.titulo) + "</h2></div>";
    if ((d.numeros || []).length) h += '<div class="ctr-gav-kpis">' + d.numeros.map(function (n) { return '<div><span class="v">' + esc(n.val) + '</span><span class="n">' + esc(n.rot) + "</span></div>"; }).join("") + "</div>";
    if ((d.os || []).length) {
      // a OS uma vez, com as tarefas dentro: o PCM conta tarefa a tarefa (uma MPM tem a cabine, o inversor, a segurança…)
      var porOs = {}, ordem = [];
      d.os.forEach(function (o) {
        var k = o.os || ("s" + ordem.length);
        if (!porOs[k]) { porOs[k] = {os: o.os, id: o.id, usina: o.usina, prog: o.prog, tarefas: [], feitas: 0}; ordem.push(k); }
        var g = porOs[k]; g.tarefas.push(o); if (o.estado === "Finalizada") g.feitas += 1; if (!g.id && o.id) g.id = o.id;
      });
      h += "<h3>As OS (" + ordem.length + ")</h3><ul class=\"ctr-gav-lista\">" + ordem.slice(0, 200).map(function (k) {
        var g = porOs[k], tudo = g.feitas === g.tarefas.length, st = tudo ? "Finalizada" : g.tarefas[0].estado;
        return '<li class="ctr-gav-osl"><button type="button" class="ctr-gav-os" data-os-abrir="' + esc(g.id || "") + '" data-os-folio="' + esc(g.os) + '" data-os-status="' + esc(st) + '" title="Abrir o card da OS">' + esc(g.os || "s/nº") + "</button>" +
          '<span class="ctr-gav-txt"><b>' + esc(g.usina) + (g.prog ? " · programada " + dBR(g.prog) : "") + "</b>" +
          "<details><summary>" + g.tarefas.length + (g.tarefas.length === 1 ? " tarefa" : " tarefas") + "</summary><ul>" + g.tarefas.map(function (o) {
            return "<li>" + esc(o.tarefa) + ' <span class="mudo">· ' + esc(o.estado || "—") + (o.final ? " em " + dBR(o.final) : "") + "</span></li>"; }).join("") + "</ul></details></span>" +
          '<span class="ctr-pill ' + (tudo ? "t-ok" : g.feitas ? "t-alerta" : "t-critico") + '" title="tarefas feitas / tarefas da OS">' + g.feitas + "/" + g.tarefas.length + "</span></li>";
      }).join("") + "</ul>" + (ordem.length > 200 ? '<p class="mudo">E mais ' + (ordem.length - 200) + " OS.</p>" : "");
    } else if (/MPM|MPS|MPA/.test(d.titulo)) h += '<p class="mudo">Nenhuma OS planejada neste mês.</p>';
    if ((d.servicos || []).length) h += "<h3>Os serviços (" + d.servicos.length + ")</h3><ul class=\"ctr-gav-lista\">" + d.servicos.map(function (s) {
      return '<li><span class="ctr-gav-data">' + dBR(s.data) + '</span><span class="ctr-gav-txt"><b>' + esc(s.servico) + "</b><small>" + esc(s.usina) + "</small></span></li>"; }).join("") + "</ul>";
    else if (/Supressão|Lavagem/.test(d.titulo)) h += '<p class="mudo">Nenhum serviço feito neste período.</p>';
    if ((d.usinas || []).length) h += "<h3>Usina a usina</h3><ul class=\"ctr-gav-lista\">" + d.usinas.map(function (u) {
      return '<li><span class="ind' + (u.tom ? " t-" + u.tom : "") + '">' + esc(u.val) + '</span><span class="ctr-gav-txt"><b>' + esc(u.usina) + " · " + esc(u.mes) + "</b>" + (u.extra ? "<small>" + esc(u.extra) + "</small>" : "") + "</span></li>"; }).join("") + "</ul>";
    if ((d.textos || []).length) h += "<h3>O que mais conta</h3>" + d.textos.map(function (x) { return '<p class="ctr-gav-p">' + esc(x) + "</p>"; }).join("");
    if (d.fonte) h += '<h3>De onde vem</h3><p class="ctr-gav-p mudo">' + esc(d.fonte) + "</p>";
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
    if (tipo === "ponto" || tipo === "resolucao") {
      var achou = null;
      Object.keys(R.pontos || {}).forEach(function (cli) {
        R.pontos[cli].forEach(function (p) {
          if (tipo === "ponto" && p.id === id) achou = {nivel: p.nivel === "atencao" ? "Atenção" : "Divergência", texto: p.texto, setor: p.setor};
          if (tipo === "resolucao" && p.resolvido && p.resolvido.id === id) achou = {ponto_id: p.id, ponto_texto: p.tema + ": " + p.texto, como: p.resolvido.como, _editado: p.resolvido._editado};
        });
      });
      return achou;
    }
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
  var ROTULO = {cliente: "Dados do contrato", contrato: "Contrato lido do PDF", regra: "Regra", obrigacao: "Obrigação", adicional: "Serviço adicional", parametros: "Metas e prazos",
    recorrencia: "Recorrência do calendário", lancamento: "Lançamento do financeiro", ponto: "Ponto de atenção ou divergência", resolucao: "Ponto resolvido"};
  function campoHtml(spec, valor, c) {
    var nome = spec[0], rot = spec[1], tipo = spec[2], extra = spec[3], id = "ctr-f-" + nome.replace(/\W/g, "_"), v = valor == null ? "" : valor, h;
    if (extra === "so_admin" && !R.admin) return "";
    if (extra === "oculto") return '<input type="hidden" data-campo="' + nome + '" value="' + esc(v) + '">';
    if (tipo === "longo") h = '<textarea id="' + id + '" data-campo="' + nome + '" rows="3">' + esc(v) + "</textarea>";
    else if (tipo === "data") h = '<input id="' + id + '" data-campo="' + nome + '" type="date" value="' + esc(String(v).slice(0, 10)) + '">';
    else if (tipo === "mes") h = '<input id="' + id + '" data-campo="' + nome + '" type="month" value="' + esc(String(v).slice(0, 7)) + '">';
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
    var retiravel = !novoItem && ["regra", "obrigacao", "adicional", "ponto", "resolucao"].indexOf(tipo) >= 0;
    var titulo = tipo === "resolucao" ? (novoItem ? "Resolver o ponto" : "Ponto resolvido") : (novoItem ? "Incluir: " : "Editar: ") + (ROTULO[tipo] || tipo);
    dlg.innerHTML = '<form method="dialog" novalidate><h2 id="ctr-dlg-t">' + esc(titulo) + "</h2>" +
      (tipo === "resolucao" && item.ponto_texto ? '<p class="ctr-nota" style="margin:0 0 8px">' + esc(item.ponto_texto) + "</p>" : "") +
      '<p class="ctr-dlg-sub">' + esc(cli || "Todos os contratos") + ". A mudança vai ao histórico com o seu nome, a hora, o motivo e a prova.</p>" +
      '<div class="ctr-campos">' + aplicar + specs.map(function (s) { return campoHtml(s, pega(item, s[0]), c); }).join("") + "</div>" +
      (item.origem_regra && novoItem ? '<p class="ctr-nota">Vem de uma regra do contrato: a prova é o trecho dela, e o motivo é opcional.</p>' : "") +
      '<div class="ctr-prova"><div class="ctr-campo largo"><label for="ctr-f-motivo">Motivo da mudança <span class="obrig">' + (item.origem_regra && novoItem ? "(opcional)" : "(obrigatório)") + '</span></label><textarea id="ctr-f-motivo" rows="2"></textarea></div>' +
      '<div class="ctr-campo largo"><label for="ctr-f-provas">Prova: o e-mail, a mensagem ou o documento <span class="obrig">(obrigatório: o arquivo ou o texto colado)</span></label>' +
      '<input id="ctr-f-provas" type="file" multiple accept=".pdf,.png,.jpg,.jpeg,.webp,.txt,.eml,.msg,.doc,.docx,.xlsx"></div>' +
      '<div class="ctr-campo largo"><label for="ctr-f-prova-texto">ou cole aqui o texto do e-mail ou da mensagem</label><textarea id="ctr-f-prova-texto" rows="3"></textarea></div></div>' +
      '<p class="ctr-dlg-erro" role="alert" hidden></p><div class="ctr-dlg-botoes"><button type="submit" class="gc-btn gc-btn--ui gc-btn--primario" data-evento="' + (novoItem ? "inclusao" : "alteracao") + '">Salvar</button>' +
      '<button type="button" class="gc-btn gc-btn--ui gc-btn--contorno" data-fechar>Cancelar</button>' + (retiravel ? '<button type="submit" class="gc-btn gc-btn--ui gc-btn--contorno ctr-retirar" data-evento="retirada">' + (tipo === "resolucao" ? "Reabrir o ponto" : "Retirar") + "</button>" : "") + "</div></form>";
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
      if (evento === "retirada" && !window.confirm(tipo === "resolucao" ? "Reabrir este ponto? A resolução sai e fica no histórico." : "Retirar este item? Ele sai da tela e fica no histórico.")) return;
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
    if (estado.ct !== antes) { estado.soAditivo = false; estado.verRegras = "todas"; estado.mesCal = 0; estado.indAno = null; }
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
    var cAtual = estado.ct >= 0 ? R.contratos[estado.ct] : null;
    if ((b = e.target.closest("[data-prior]"))) { e.stopPropagation(); var on = b.getAttribute("aria-pressed") !== "true";
      leve(cAtual, "regra", b.getAttribute("data-prior").split(","), "alteracao", {prioritaria: on ? "sim" : "nao"}, on ? "Marcada como prioritária." : "Tirada das prioritárias."); return; }
    if ((b = e.target.closest("[data-subgrupo]"))) { var tk = b.getAttribute("data-subgrupo"); estado.temas[tk] = !estado.temas[tk]; render(); return; }
    if ((b = e.target.closest("[data-tirar-com]"))) { if (window.confirm("Tirar este comentário? Ele fica no histórico.")) leve(cAtual, "comentario", [b.getAttribute("data-tirar-com")], "retirada", {}, "Comentário tirado."); return; }
    if ((b = e.target.closest("[data-cel]"))) { abrirGaveta(R.contratos[estado.ct], b.getAttribute("data-cel")); return; }
    if ((b = e.target.closest("[data-ind-ano-abrir]"))) { indAnoAberto = !indAnoAberto; render(); return; }
    if ((b = e.target.closest("[data-ind-ano]"))) { estado.indAno = +b.getAttribute("data-ind-ano") || null; indAnoAberto = false; render(); return; }
    if ((b = e.target.closest("[data-ind-mais]"))) { var cM = R.contratos[estado.ct], dM = IND[cM.cliente + "|" + (estado.indAno || "")] || {}; indMais[cM.cliente + "|" + ((dM.ano || {}).n)] = true; render(); return; }
    if ((b = e.target.closest("[data-ind-exportar]"))) {
      // o PDF da aba como está na tela, no papel claro (o escuro não sai na impressão); o tema volta depois
      var htmlEl = document.documentElement, antes = htmlEl.getAttribute("data-tema");
      htmlEl.setAttribute("data-tema", "claro"); document.body.classList.add("ind-imprimindo");
      setTimeout(function () { window.print(); document.body.classList.remove("ind-imprimindo"); if (antes) htmlEl.setAttribute("data-tema", antes); else htmlEl.removeAttribute("data-tema"); }, 50);
      return; }
    if ((b = e.target.closest("[data-ind-visao]"))) { indVisao = b.getAttribute("data-ind-visao"); render(); return; }
    if ((b = e.target.closest("[data-ind-usina]"))) { var cI = R.contratos[estado.ct], dI = IND[cI.cliente + "|" + (estado.indAno || "")] || {}, chI = cI.cliente + "|" + ((dI.ano || {}).n);
      indAbertas[chI] = indAbertas[chI] || {}; var uI = b.getAttribute("data-ind-usina"); indAbertas[chI][uI] = !indAbertas[chI][uI]; render(); return; }
    if ((b = e.target.closest("[data-dobra]"))) { var dk = b.getAttribute("data-dobra"); DOBRAS[dk] = !DOBRAS[dk];
      try { localStorage.setItem("nexus.contratos.dobras", JSON.stringify(DOBRAS)); } catch (er) { /* sem localStorage: vale até recarregar */ } render(); return; }
    if ((b = e.target.closest("[data-mes]"))) { var dm = +b.getAttribute("data-mes"); estado.mesCal = dm ? (estado.mesCal || 0) + dm : 0; render(); return; }
    if ((b = e.target.closest("[data-confirmar]"))) { var pz = JSON.parse(b.getAttribute("data-confirmar")); b.disabled = true;
      var fdc = new FormData(); fdc.append("item_id", ""); fdc.append("item_tipo", "recorrencia"); fdc.append("evento", "inclusao"); fdc.append("cliente", cAtual.cliente);
      fdc.append("valores", JSON.stringify(pz)); fdc.append("motivo", ""); fdc.append("prova_texto", "");
      pedir(CAMINHO + "editar", {method: "POST", body: fdc, headers: {"Accept": "application/json", "X-Nexus-Parte": "1"}}).then(function () { delete HIST[cAtual.cliente]; toast("Confirmada: está no calendário e no histórico."); carregar(); })
        .catch(function (er) { b.disabled = false; toast((er && er.message) || "Não consegui gravar agora."); }); return; }
    if ((b = e.target.closest("[data-descartar]"))) { leve(cAtual, "descarte", [""], "inclusao", {sugestao_id: b.getAttribute("data-descartar")}, "Sugestão descartada."); return; }
    if ((b = e.target.closest("[data-ed-tipo]"))) { e.preventDefault(); abrirEdicao(b); }
    else if ((b = e.target.closest("[data-rg]"))) { var rg = b.getAttribute("data-rg"); regraAberta[rg] = !regraAberta[rg]; render(); }
    else if ((b = e.target.closest("[data-regras]"))) { estado.verRegras = b.getAttribute("data-regras"); estado.soAditivo = estado.verRegras === "aditivo"; render(); }
    else if ((b = e.target.closest("[data-grupo]"))) { var g = b.getAttribute("data-grupo"); estado.grupos[g] = !estado.grupos[g]; render(); }
    else if ((b = e.target.closest(".ctr-escolha-btn"))) { if (aberta) fechaEscolha(true); else abreEscolha(b.closest("[data-escolha]")); }
    else if ((b = e.target.closest('.ctr-lista li[role="option"]'))) { fechaEscolha(false); irPara(+b.getAttribute("data-ir")); }
    else if ((b = e.target.closest("[data-ir]")) && !e.target.closest("a")) irPara(+b.getAttribute("data-ir"));
  });
  raiz.addEventListener("input", function (e) { if (aberta && e.target === aberta.campo) filtraEscolha(); });
  raiz.addEventListener("change", function (e) {
    var b = e.target.closest("[data-entregar]");
    if (!b) return;
    var c = R.contratos[estado.ct], par = b.getAttribute("data-entregar").split("|");
    if (b.checked) leve(c, "entrega", [""], "inclusao", {recorrencia_id: par[0], data: par[1]}, "Marcada como entregue.");
    else leve(c, "entrega", [b.getAttribute("data-entrega-id")], "retirada", {}, "Entrega desmarcada.");
  });
  raiz.addEventListener("submit", function (e) {
    var f = e.target.closest("[data-comentar]");
    if (!f) return;
    e.preventDefault();
    var t = f.querySelector("textarea").value.trim();
    if (!t) return;
    leve(R.contratos[estado.ct], "comentario", [""], "inclusao", {alvo_tipo: "regra", alvo_id: f.getAttribute("data-comentar"), texto: t}, "Comentário salvo.");
  });
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

/* A moldura da Plataforma de Performance no Nexus (porta única, 09/10/2026).

   Levi: "a partir de segunda quero o Nexus como link principal; o Nexus será o centro de tudo". A página do item
   (performance/moldura.html) traz o passe num formulário escondido e a tabela do mapa em #porta-dados. Aqui:
   1. o formulário vai à plataforma (POST, alvo = a moldura): ela confere o passe, abre a sessão dela e mostra a tela;
   2. a cada troca de caminho dentro da moldura a plataforma avisa ({tipo: "nexus:rota", caminho}); o endereço do Nexus
      acompanha (?p=, para F5 e favorito) e o item do menu certo acende, pela tabela do mapa;
   3. no Diagnóstico, o seletor de usina lê a lista da própria plataforma pelo navegador (a mesma do Painel NOC), sem o
      processo do Nexus buscar nada;
   4. a sessão que o passe abre na plataforma vale 12 h fixas (auditoria A5 da porta única, 10/10/2026: depois delas o
      Painel NOC desenhava "Energia perdida 0,0 MWh", o 401 do /api/macro lido como zero). Quando a página da plataforma
      leva 401 numa chamada de dado, ela avisa ({tipo: "nexus:sessao-vencida", caminho}); aqui se pede um passe NOVO ao
      Nexus (POST em dados.renovar) e a moldura reabre a mesma tela, no máximo 1 vez a cada 60 s (sem laço). E, com a aba
      aberta, a cada 11 h um passe novo abre outra sessão na plataforma por fetch, sem recarregar a tela.
   Endereço da plataforma sempre como URL COMPLETA (new URL(..., location.href)): no servidor, uma camada fora do
   repositório põe /nexus em todo fetch com caminho começado por "/" (nexus/casca/CLAUDE.md), e o /api/macro da
   plataforma viraria /nexus/api/macro. As funções puras ficam expostas ao node (tests/test_porta_js.py). */
(function () {
  "use strict";

  // A mesma tabela do Painel NOC da plataforma (painel_portfolio.html, FMAP e drillUrl): de qual fonte ao vivo cada
  // usina vem e como o diagnóstico dela se abre. Mudou lá, muda aqui (o teste no node fixa os endereços).
  var FONTE_DO_DIAGNOSTICO = {"API PV": "pv", "Thopen": "pg", "Athon": "athon", "Axis": "axis", "2C": "2c",
                              "SEMP": "pv", "RenoGrid": "solaredge"};

  function norm(s) {
    return String(s == null ? "" : s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
  }

  // encodeURIComponent deixa a aspa simples passar, e o passe recusa destino com aspas (nada de "'" em atributo)
  function enc(s) {
    return encodeURIComponent(String(s == null ? "" : s)).replace(/'/g, "%27");
  }

  /* As usinas do seletor, pela regra do Painel NOC: as de fonte ao vivo (/api/macro) com o diagnóstico da fonte, e as
     que só existem no Gerencial (/api/gerencial, com aba de dado) com o diagnóstico histórico. O casamento por nome é o
     mesmo do NOC (igual, ou um começo do outro quando só um casa). Devolve [{valor, nome, grupo}] em ordem de nome. */
  function usinasDoSeletor(macro, gerencial) {
    var ger = (gerencial && gerencial.usinas) || [], gmap = {}, usado = {}, vistas = {}, saida = [];
    ger.forEach(function (u) { gmap[norm(u.usina)] = u; });
    var chaves = Object.keys(gmap);
    ((macro && macro.usinas) || []).forEach(function (u) {
      var k = norm(u.usina), gk = gmap[k] ? k : null;
      if (!gk) {
        var cand = chaves.filter(function (x) { return x.indexOf(k) === 0 || k.indexOf(x) === 0; });
        if (cand.length === 1) gk = cand[0];
      }
      if (gk) usado[gk] = true;
      vistas[k] = true;
      var f = FONTE_DO_DIAGNOSTICO[u.fonte];
      if (!f || u.plant_id == null || u.plant_id === "") return;     // sem drill no NOC, sem diagnóstico aqui
      saida.push({valor: "/painel/usina/" + enc(u.plant_id) + "?fonte=" + f + "&nome=" + enc(u.usina),
                  nome: String(u.usina), grupo: String((gk && gmap[gk].cliente) || u.cliente || u.fonte || "Sem cliente")});
    });
    ger.forEach(function (u) {
      var k = norm(u.usina);
      if (usado[k] || vistas[k] || u.sem_dado) return;
      saida.push({valor: "/painel/usina/" + enc(k) + "?hist=1&cliente=" + enc(u.cliente || "") + "&nome=" + enc(u.usina),
                  nome: String(u.usina), grupo: String(u.cliente || "Sem cliente") + " (histórico)"});
    });
    saida.sort(function (a, b) { return a.grupo.localeCompare(b.grupo, "pt-BR") || a.nome.localeCompare(b.nome, "pt-BR"); });
    return saida;
  }

  // A tela do mapa a que o caminho pertence (a consulta não conta), ou null. `telas` vem do servidor (porta.MAPA).
  function telaDoCaminho(telas, caminho) {
    var c = String(caminho || "").split("?")[0];
    for (var i = 0; i < telas.length; i++) {
      for (var j = 0; j < telas[i].padroes.length; j++) {
        if (new RegExp(telas[i].padroes[j]).test(c)) return telas[i];
      }
    }
    return null;
  }

  // O endereço do Nexus para o caminho da moldura: o do item, e o ?p= só quando não é a entrada padrão dele.
  function enderecoNoNexus(tela, caminho) {
    return caminho === tela.caminho ? tela.url : tela.url + "?p=" + encodeURIComponent(caminho);
  }

  // Só caminho local da plataforma: "/x", nunca "//outro" nem URL completa (o aviso vem de outro sistema).
  function caminhoAceito(c) {
    return typeof c === "string" && c.charAt(0) === "/" && c.charAt(1) !== "/" && c.charAt(1) !== "\\" && c.length < 2048;
  }

  function mesmoCaminho(a, b) {
    return String(a || "").split("?")[0] === String(b || "").split("?")[0];
  }

  // A sessão do passe vale 12 h na plataforma (SESSAO_DO_PASSE_S): renova-se 1 h antes
  var RENOVA_A_CADA_MS = 11 * 3600 * 1000;
  // Se a sessão vence de novo logo depois de reaberta, algo está errado do lado da plataforma: reabrir outra vez seria um
  // laço (cada volta, um passe novo e a tela inteira recarregada)
  var ESPERA_ENTRE_REABERTURAS_MS = 60 * 1000;

  function podeReabrir(ultima, agora) {
    return !ultima || agora - ultima >= ESPERA_ENTRE_REABERTURAS_MS;
  }

  // O caminho a reabrir: o que a plataforma mandou, se for uma tela do mapa (só destas o Nexus dá passe); senão o último
  // que a moldura avisou pelo nexus:rota (a plataforma pode estar no /login dela, fora do mapa)
  function caminhoParaReabrir(telas, avisado, atual) {
    return caminhoAceito(avisado) && telaDoCaminho(telas, avisado) ? avisado : (atual || "");
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = {usinasDoSeletor: usinasDoSeletor, telaDoCaminho: telaDoCaminho, enderecoNoNexus: enderecoNoNexus,
                      caminhoAceito: caminhoAceito, norm: norm, enc: enc, podeReabrir: podeReabrir,
                      caminhoParaReabrir: caminhoParaReabrir, RENOVA_A_CADA_MS: RENOVA_A_CADA_MS};
    return;
  }

  // ── a página ──────────────────────────────────────────────────────────────────────────────────────────────────────
  var caixa = document.getElementById("porta"), blocoDados = document.getElementById("porta-dados");
  if (!caixa || !blocoDados) return;
  var dados = JSON.parse(blocoDados.textContent || "{}");
  var base = dados.plataforma || "";                       // "" = a própria origem do Nexus (o servidor)
  function urlDaPlataforma(caminho) { return new URL(base + caminho, location.href).href; }
  var origem;
  try { origem = new URL(base || "/", location.href).origin; } catch (e) { origem = location.origin; }
  var alerta = document.getElementById("porta-alerta");
  function avisar(texto) { if (alerta) { alerta.textContent = texto; alerta.hidden = false; } }
  // A plataforma só se deixa emoldurar pela própria origem (frame-ancestors 'self') e só avisa a rota a ela. Em outra
  // origem NADA sai daqui: nem o passe, nem a lista do Diagnóstico (revisão de 10/10/2026: antes o aviso aparecia e o
  // formulário ia assim mesmo; com a NEXUS_PLATAFORMA_URL interna do servidor, http://127.0.0.1:..., cada visitante
  // mandava um passe válido, com o e-mail dele, à porta local da PRÓPRIA máquina).
  var mesmaOrigem = origem === location.origin;
  if (!mesmaOrigem) {
    avisar("A Plataforma de Performance está configurada em outra origem (" + origem + "): a tela não abre dentro do " +
           "Nexus assim. No servidor, a NEXUS_PLATAFORMA_URL é o próprio endereço do Nexus (ou vazia); no PC, use a " +
           "porta local (ferramentas/porta_local.py).");
  }

  var moldura = document.getElementById("porta-moldura");
  var formulario = document.getElementById("porta-passe");
  var fora = document.getElementById("porta-fora");
  if (moldura && formulario && mesmaOrigem) formulario.submit();

  function acender(tela) {
    document.querySelectorAll(".menu a[aria-current]").forEach(function (a) { a.removeAttribute("aria-current"); });
    document.querySelectorAll(".menu .torre li a").forEach(function (a) {
      if (a.getAttribute("href") !== tela.url) return;
      a.setAttribute("aria-current", "page");
      var torre = a.closest("details");
      if (torre) torre.open = true;
    });
    document.title = tela.nome + " · Grid Co.";
    // a faixa diz o item em que a pessoa está agora (a moldura pode ter ido do Tempo real ao Acompanhamento COS)
    var nome = document.querySelector(".porta-origem strong");
    if (nome) nome.textContent = tela.nome;
  }

  // o caminho em que a moldura está agora (o da abertura, depois o de cada nexus:rota): é o que se reabre e se renova
  var caminhoAtual = dados.destino || "";

  window.addEventListener("message", function (ev) {
    if (!moldura || ev.source !== moldura.contentWindow || ev.origin !== origem) return;
    var d = ev.data;
    if (d && d.tipo === "nexus:sessao-vencida") { reabrir(d.caminho); return; }
    if (!d || d.tipo !== "nexus:rota" || !caminhoAceito(d.caminho)) return;
    var tela = telaDoCaminho(dados.telas || [], d.caminho);
    if (!tela) return;                       // fora do mapa (o login da plataforma, por exemplo): o endereço fica
    caminhoAtual = d.caminho;
    var novo = enderecoNoNexus(tela, d.caminho);
    try { history.replaceState(history.state, "", novo); } catch (e) { /* endereço de outra origem: fica */ }
    // a troca de cadeira e de tema voltam para onde a pessoa está agora (o servidor aceita com ou sem o prefixo)
    document.querySelectorAll('input[name="voltar"]').forEach(function (i) { i.value = novo; });
    if (fora) fora.href = urlDaPlataforma(d.caminho);
    acender(tela);
    marcarUsina(d.caminho);
  });

  // ── a sessão da plataforma: reabrir quando vence, renovar antes de vencer ─────────────────────────────────────────
  var campoPasse = formulario && formulario.querySelector ? formulario.querySelector('input[name="passe"]') : null;
  var ultimaReabertura = 0;
  var renovarEm = Date.now() + RENOVA_A_CADA_MS;

  function entrarDeNovo(url) {
    // a sessão do NEXUS acabou (o Fracttal saiu ou venceu): a janela vai ao login, que volta para esta tela (base.html)
    if (typeof window.nexusEntrarDeNovo === "function") window.nexusEntrarDeNovo(url);
    else location.reload();
  }

  // Um passe novo para `caminho`, pedido ao Nexus (a mesma regra da abertura da tela: 60 s, uso único). null quando a
  // sessão do Nexus acabou (a janela já foi mandada ao login). URL completa: a camada da T.I. mexe em fetch com "/".
  function pedirPasse(caminho) {
    var corpo = new URLSearchParams();
    corpo.set("p", caminho);
    return fetch(new URL(dados.renovar, location.href).href, {method: "POST", body: corpo, credentials: "same-origin",
                                                               redirect: "manual", cache: "no-store",
                                                               headers: {"Accept": "application/json"}})
      .then(function (r) {
        if (r.type === "opaqueredirect") { entrarDeNovo(); return null; }      // o portão mandou ao Entrar
        if (r.status === 401) {
          return r.json().catch(function () { return {}; }).then(function (j) { entrarDeNovo(j && j.entrar); return null; });
        }
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json().then(function (j) {
          if (!j || !j.passe) throw new Error("sem passe");
          return j.passe;
        });
      });
  }

  function reabrir(avisado) {
    if (!formulario || !campoPasse || !dados.renovar || !mesmaOrigem) return;
    var caminho = caminhoParaReabrir(dados.telas || [], avisado, caminhoAtual);
    if (!caminho) return;
    var agora = Date.now();
    if (!podeReabrir(ultimaReabertura, agora)) {
      avisar("A sessão da Plataforma de Performance venceu de novo logo depois de renovada. Clique no item do menu " +
             "para abrir a tela outra vez; se continuar, avise o administrador.");
      return;
    }
    ultimaReabertura = agora;
    pedirPasse(caminho).then(function (passe) {
      if (!passe) return;
      campoPasse.value = passe;
      formulario.submit();                   // a moldura abre o mesmo caminho com a sessão nova (o 303 da plataforma)
      caminhoAtual = caminho;
      renovarEm = Date.now() + RENOVA_A_CADA_MS;
      if (alerta) alerta.hidden = true;
    }).catch(function () {
      avisar("A sessão da Plataforma de Performance venceu e o Nexus não conseguiu renová-la agora. Clique no item do " +
             "menu para abrir a tela de novo.");
    });
  }

  // Antes das 12 h: o passe novo vai por fetch (o 303 não é seguido, como no abrirSessao do Diagnóstico), a plataforma
  // abre outra sessão e a tela segue como está, sem recarregar (a TV do NOC, a aba esquecida aberta). Falhou, tenta de
  // novo em 10 min; se a sessão chegar a vencer, o aviso da plataforma reabre a tela.
  function renovarSessao() {
    renovarEm = Date.now() + RENOVA_A_CADA_MS;            // já: um pedido lento não dispara outro
    pedirPasse(caminhoAtual).then(function (passe) {
      if (!passe) return;
      var corpo = new URLSearchParams();
      corpo.set("passe", passe);
      return fetch(urlDaPlataforma("/painel/nexus/entrar"), {method: "POST", body: corpo, credentials: "same-origin",
                                                              redirect: "manual"})
        .then(function (r) { if (r.type !== "opaqueredirect") throw new Error("HTTP " + r.status); });
    }).catch(function () { renovarEm = Date.now() + 10 * 60 * 1000; });
  }

  function talvezRenovar() {
    if (caminhoAtual && Date.now() >= renovarEm) renovarSessao();
  }

  if (moldura && formulario && mesmaOrigem && dados.renovar) {
    // pelo relógio de parede, conferido a cada minuto e ao voltar à aba: um setTimeout de 11 h atrasa com o computador
    // dormindo, e a sessão da plataforma conta as 12 h de verdade
    setInterval(talvezRenovar, 60 * 1000);
    document.addEventListener("visibilitychange", talvezRenovar);
  }

  // ── Diagnóstico: o seletor de usina ───────────────────────────────────────────────────────────────────────────────
  var seletor = document.getElementById("porta-usina"), nota = document.getElementById("porta-usina-nota");
  function dizer(texto) { if (nota) nota.textContent = texto || ""; }

  function marcarUsina(caminho) {
    if (!seletor || !caminho) return;
    var exato = null, parecido = null;
    for (var i = 0; i < seletor.options.length; i++) {
      var o = seletor.options[i];
      if (o.value === caminho) exato = o;
      else if (!parecido && o.value && mesmoCaminho(o.value, caminho)) parecido = o;
    }
    var o2 = exato || parecido;
    if (o2) o2.selected = true;
  }

  // GET com a sessão da plataforma; null = sem sessão (401/403, ou o salto para o login dela)
  function lerJson(caminho, limiteMs) {
    var controle = window.AbortController ? new AbortController() : null;
    var relogio = controle ? setTimeout(function () { controle.abort(); }, limiteMs) : null;
    return fetch(urlDaPlataforma(caminho), {credentials: "same-origin", redirect: "manual",
                                            headers: {"Accept": "application/json"}, signal: controle && controle.signal})
      .then(function (r) {
        if (r.type === "opaqueredirect" || r.status === 401 || r.status === 403) return null;
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .finally(function () { if (relogio) clearTimeout(relogio); });
  }

  // O passe da lista: abre a sessão da plataforma sem carregar página nenhuma (o 303 não é seguido)
  function abrirSessao() {
    if (!dados.passe_lista || !mesmaOrigem) return Promise.resolve();      // o passe nunca vai a outra origem
    var corpo = new URLSearchParams();
    corpo.set("passe", dados.passe_lista);
    dados.passe_lista = "";                  // uso único: a plataforma recusaria o mesmo passe de novo
    return fetch(urlDaPlataforma("/painel/nexus/entrar"), {method: "POST", body: corpo, credentials: "same-origin",
                                                            redirect: "manual"}).catch(function () { return null; });
  }

  function preencher(lista) {
    seletor.innerHTML = "";
    var vazia = document.createElement("option");
    vazia.value = "";
    vazia.textContent = lista.length ? "Escolha a usina (" + lista.length + ")" : "Nenhuma usina na Plataforma";
    seletor.appendChild(vazia);
    var grupo = null, nomeGrupo = null;
    lista.forEach(function (u) {
      if (u.grupo !== nomeGrupo) {
        nomeGrupo = u.grupo;
        grupo = document.createElement("optgroup");
        grupo.label = u.grupo;
        seletor.appendChild(grupo);
      }
      var o = document.createElement("option");
      o.value = u.valor;
      o.textContent = u.nome;
      grupo.appendChild(o);
    });
    seletor.disabled = !lista.length;
    marcarUsina(dados.destino);
  }

  function carregarUsinas(tentativa) {
    tentativa = tentativa || 0;
    dizer(tentativa ? "A Plataforma ainda está montando a lista; tentando de novo..." : "");
    lerJson("/api/macro", 20000)
      .then(function (macro) {
        if (macro === null) {
          return abrirSessao().then(function () { return lerJson("/api/macro", 20000); });
        }
        return macro;
      })
      .then(function (macro) {
        if (macro === null) throw new Error("a Plataforma não abriu a sessão");
        if (macro.carregando && tentativa < 6) {
          setTimeout(function () { carregarUsinas(tentativa + 1); }, 5000);
          return;
        }
        // as usinas só com histórico vêm do Gerencial; sem ele, o seletor fica com as de fonte ao vivo
        return lerJson("/api/gerencial", 20000).catch(function () { return null; }).then(function (ger) {
          preencher(usinasDoSeletor(macro, ger));
          dizer(ger ? "" : "Só as usinas de fonte ao vivo: o Gerencial não respondeu.");
        });
      })
      .catch(function (e) {
        seletor.innerHTML = "<option value=\"\">Lista indisponível</option>";
        dizer("A Plataforma não entregou a lista de usinas (" + (e && e.message ? e.message : "sem resposta") +
              "). Recarregue a página para tentar de novo.");
      });
  }

  if (seletor) {
    seletor.addEventListener("change", function () {
      if (seletor.value) location.assign(dados.url + "?p=" + encodeURIComponent(seletor.value));
    });
    // Com a moldura abrindo, a lista espera a tela carregar (a sessão da plataforma já estará aberta pelo passe dela)
    if (!mesmaOrigem) {
      // em outra origem a lista não é lida (o aviso no alto diz por quê): nada sai daqui
      seletor.innerHTML = "<option value=\"\">Lista indisponível</option>";
      dizer("A Plataforma está configurada em outra origem: a lista de usinas não é lida daqui.");
    } else if (moldura) {
      var uma = false;
      moldura.addEventListener("load", function () { if (!uma) { uma = true; carregarUsinas(); } });
    } else {
      carregarUsinas();
    }
  }
})();

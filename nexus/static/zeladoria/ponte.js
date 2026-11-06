/* A ponte da zeladoria: o `window.supabase` que o clone do Radar (nexus/torres/zeladoria/clone/radar.html) usa, agora
   falando com as rotas da torre Zeladoria em vez do Supabase.

   O clone foi escrito para o supabase-js v2 e continua escrito assim (Levi, 03/11/2026: "a mesma lógica e caminhos do
   BD"). Esta ponte entrega só o que ele usa, com a mesma forma de resposta do PostgrestBuilder da v2.118:
   {data, error, count, status, statusText}. O construtor se encadeia (select, eq, neq, order), vale dentro de
   Promise.resolve e nunca lança: o erro, inclusive o de rede, vem no `error`, como no supabase-js.

   Dois modos, pela configuração do servidor (`somenteLeitura`):
   - **Só leitura** (até a troca, docs/superpowers/specs/2026-11-03-zeladoria-no-nexus-design.md): gravar e as funções
     do financeiro (rpc) voltam o erro SOMENTE_LEITURA sem ir ao servidor.
   - **Gravação** (etapa 4; o servidor com NEXUS_ZELADORIA_GRAVA=1): o Radar salva o estado inteiro a cada mudança (o
     `syncTudo` dele faz upsert de todas as tabelas). A ponte guarda o que leu de cada tabela e manda a `/api/gravar` só
     as COLUNAS que mudaram, das linhas que mudaram. Assim a mudança de outra pessoa numa linha que você não mexeu fica.
     O histórico de valores, que o Radar apaga inteiro e regrava, vira a diferença das linhas. A resposta diz se outra
     pessoa salvou depois que a página abriu, e o aviso aparece no `showToast` do próprio Radar.
   Nos dois, o retrato do cronograma, que o clone regrava sozinho ao abrir, é aceito em silêncio: é derivado, e a rota
   dele é a etapa 5.

   O login é o do Nexus: `onAuthStateChange` entrega a pessoa de /api/eu, e as telas de senha do Radar não servem mais.
   O `storage` só conhece o arquivo dos PDFs dos contratos, que mora no servidor do Nexus; as fotos da ronda, o clone pede
   à função `fracttal-fotos`, que a torre atende.

   A configuração vem do servidor em `window.ZELADORIA` = {api, somenteLeitura, sair, chaves}, com os endereços já
   montados (o Nexus pode rodar debaixo de um prefixo); `chaves` = a coluna-chave das tabelas cuja chave não é `id`. */
(function (w) {
  "use strict";
  var cfg = w.ZELADORIA || {};
  var GRAVA = cfg.somenteLeitura === false;
  var SOMENTE_LEITURA = { message: "Cópia só leitura até a troca: edite no Radar.", code: "SOMENTE_LEITURA" };
  var DERIVADAS = { rf_cronograma_publico: true };
  // o que o app leu (ou gravou) de cada tabela: view -> {chave: linha}. É a base da diferença
  var lido = {};
  // a versão da página aberta (de /api/eu): a mudança de outra pessoa depois dela é o aviso
  var versao = 0;
  var avisou = {};

  function resposta(data, error, status, statusText) {
    return { data: data, error: error, count: null, status: status, statusText: statusText || "" };
  }

  // Sem sessão, o portão do Nexus manda o pedido para o login: o fetch segue o redirecionamento e recebe a página HTML
  // com 200. Sem esta conferência, o clone recebia "sem erro e sem dado" e montava o Radar vazio sem aviso (revisão
  // final de 03/11/2026).
  var SESSAO = { message: "Sua sessão do Nexus acabou: entre de novo.", code: "SESSAO" };

  function semSessao(r) {
    var tipo = (r.headers && r.headers.get && r.headers.get("content-type")) || "";
    return r.redirected || tipo.indexOf("json") < 0;
  }

  function pedir(url, opcoes) {
    return w.fetch(url, opcoes || { credentials: "same-origin" }).then(function (r) {
      if (semSessao(r)) return resposta(null, SESSAO, r.status, r.statusText);
      return r.json().then(function (corpo) { return corpo; }, function () { return null; }).then(function (corpo) {
        if (r.ok) return resposta(corpo, null, r.status, r.statusText);
        var msg = (corpo && (corpo.erro || corpo.message)) || ("O Nexus respondeu " + r.status + ".");
        return resposta(null, { message: msg, code: String(r.status) }, r.status, r.statusText);
      });
    }, function () {
      return resposta(null, { message: "Sem conexão com o Nexus agora. Tente de novo em instantes.", code: "REDE" }, 0, "");
    });
  }

  function postar(caminho, corpo) {
    return pedir(cfg.api + caminho, {
      method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo),
    });
  }

  // ── a diferença ──────────────────────────────────────────────────────────────────────────────────────────────
  function chaveDe(view) { return (cfg.chaves && cfg.chaves[view]) || "id"; }

  function ordenado(v) {
    if (Array.isArray(v)) return v.map(ordenado);
    if (v && typeof v === "object") {
      var o = {};
      Object.keys(v).sort().forEach(function (k) { o[k] = ordenado(v[k]); });
      return o;
    }
    return v;
  }

  // a mesma régua do servidor: nulo é nulo, e o resto compara pelo texto (100 e "100" são o mesmo número)
  function txt(v) {
    if (v === null || v === undefined) return null;
    return typeof v === "object" ? JSON.stringify(ordenado(v)) : String(v);
  }

  // cópia PROFUNDA: o Radar guarda a referência do JSON que leu (as pendências do dano, o escopo do contrato, as etapas
  // da rota) e muda o conteúdo no lugar. Com a cópia rasa, o "lido" mudava junto, a diferença não via nada e a edição
  // se perdia com o "Salvo" aceso (revisão de 03/11/2026)
  function copia(v) { return v === undefined ? undefined : JSON.parse(JSON.stringify(v)); }

  function guardar(view, linhas, trocar) {
    var k = chaveDe(view), m = trocar ? {} : (lido[view] || {});
    linhas.forEach(function (l) {
      if (l && l[k] !== null && l[k] !== undefined) m[String(l[k])] = Object.assign({}, m[String(l[k])] || {}, copia(l));
    });
    lido[view] = m;
  }

  function casa(l, filtros) {
    return filtros.every(function (f) { return (txt(l[f[1]]) === txt(f[2])) === (f[0] === "eq"); });
  }

  // só as colunas que mudaram, das linhas que mudaram; a linha que o app não leu vai inteira (é nova)
  function diferenca(view, linhas) {
    var k = chaveDe(view), base = lido[view] || {}, out = [];
    linhas.forEach(function (l) {
      var antes = l[k] === null || l[k] === undefined ? null : base[String(l[k])];
      if (!antes) { out.push(l); return; }
      var parte = {}, mudou = false;
      Object.keys(l).forEach(function (c) {
        if (txt(l[c]) !== txt(antes[c])) { parte[c] = l[c]; mudou = true; }
      });
      if (mudou) { parte[k] = l[k]; out.push(parte); }
    });
    return out;
  }

  // ── o salvamento ─────────────────────────────────────────────────────────────────────────────────────────────
  function aviso(texto) {
    if (typeof w.showToast === "function") w.showToast(texto);
  }

  function avisar(r) {
    if (r.sobrepostas && r.sobrepostas.length) {
      aviso("Você e outra pessoa mudaram o mesmo registro (" + r.sobrepostas.slice(0, 3).join(", ") +
            (r.sobrepostas.length > 3 ? "…" : "") + "). Ficou o que você salvou.");
    } else if (r.outros_salvaram && !avisou.outros) {
      avisou.outros = true;
      aviso("Outra pessoa salvou na zeladoria depois que você abriu. O seu está salvo; recarregue a página para ver o dela.");
    }
    if (r.situacao && r.situacao.erro && !avisou.banco) {
      avisou.banco = true;
      aviso("Salvo no Nexus. O banco está atrasado, e o Nexus tenta de novo sozinho.");
    } else if (r.situacao && !r.situacao.erro) {
      avisou.banco = false;
    }
  }

  function gravar(ops) {
    if (!ops.length) return Promise.resolve({ ok: true, ids: [] });
    return postar("/gravar", { ops: ops, versao: versao }).then(function (r) {
      if (r.error) return { erro: r };
      avisar(r.data || {});
      return { ok: true, ids: (r.data && r.data.ids) || [] };
    });
  }

  function criado(feito) {
    return feito.erro ? feito.erro : resposta(null, null, 201, "Created");
  }

  // o Radar apaga o histórico de valores inteiro e regrava: a ponte guarda o "apagar tudo" e, se a regravação vem logo
  // depois (o passo seguinte da mesma corrente), manda só a diferença; se não vem, apaga o que tinha
  var regravando = {};

  function sinal(l, colunas) {
    return JSON.stringify(colunas.map(function (c) { return txt(l[c]); }));
  }

  function regravar(view, linhas) {
    var k = chaveDe(view), antigas = Object.keys(lido[view] || {}).map(function (id) { return lido[view][id]; });
    var colunas = {};
    linhas.forEach(function (l) { Object.keys(l).forEach(function (c) { if (c !== k) colunas[c] = true; }); });
    colunas = Object.keys(colunas).sort();
    var livres = {};
    antigas.forEach(function (a) { var s = sinal(a, colunas); (livres[s] = livres[s] || []).push(a); });
    var ficam = [], novas = [];
    linhas.forEach(function (l) {
      var s = sinal(l, colunas);
      if (livres[s] && livres[s].length) ficam.push(livres[s].shift()); else novas.push(l);
    });
    var saem = [];
    Object.keys(livres).forEach(function (s) { saem = saem.concat(livres[s]); });
    var ops = saem.map(function (a) { return { op: "delete", view: view, filtros: [["eq", k, a[k]]] }; });
    if (novas.length) ops.push({ op: "insert", view: view, linhas: novas });
    return gravar(ops).then(function (feito) {
      if (feito.ok) {
        var ids = feito.ids[feito.ids.length - 1] || [];
        guardar(view, ficam.concat(novas.map(function (l, i) {
          var c = Object.assign({}, l);
          if (c[k] === undefined || c[k] === null) c[k] = ids[i];
          return c;
        })), true);
      }
      return criado(feito);
    });
  }

  function executarGravacao(view, tipo, valores, filtros) {
    var linhas = Array.isArray(valores) ? valores : [valores];
    if (tipo === "delete" && filtros.length === 1 && filtros[0][0] === "neq" && filtros[0][1] === chaveDe(view)) {
      regravando[view] = true;
      setTimeout(function () {
        if (regravando[view]) { delete regravando[view]; regravar(view, []); }
      }, 0);
      return Promise.resolve(resposta(null, null, 204, "No Content"));
    }
    if (tipo === "insert" && regravando[view]) {
      delete regravando[view];
      return regravar(view, linhas);
    }
    if (tipo === "upsert") {
      var mudaram = diferenca(view, linhas);
      return gravar(mudaram.length ? [{ op: "upsert", view: view, linhas: mudaram }] : []).then(function (feito) {
        if (feito.ok) guardar(view, mudaram);
        return criado(feito);
      });
    }
    if (tipo === "insert") {
      return gravar([{ op: "insert", view: view, linhas: linhas }]).then(function (feito) {
        if (feito.ok) {
          var k = chaveDe(view), ids = feito.ids[0] || [], i = 0;
          guardar(view, linhas.map(function (l) {
            var c = Object.assign({}, l);
            if (c[k] === undefined || c[k] === null) c[k] = ids[i++];
            return c;
          }));
        }
        return criado(feito);
      });
    }
    if (tipo === "update") {
      return gravar([{ op: "update", view: view, patch: linhas[0] || {}, filtros: filtros }]).then(function (feito) {
        if (feito.ok) {
          var m = lido[view] || {};
          Object.keys(m).forEach(function (id) { if (casa(m[id], filtros)) Object.assign(m[id], copia(linhas[0] || {})); });
        }
        return feito.erro ? feito.erro : resposta(null, null, 204, "No Content");
      });
    }
    // delete com filtro
    return gravar([{ op: "delete", view: view, filtros: filtros }]).then(function (feito) {
      if (feito.ok) {
        var m = lido[view] || {};
        Object.keys(m).forEach(function (id) { if (casa(m[id], filtros)) delete m[id]; });
      }
      return feito.erro ? feito.erro : resposta(null, null, 204, "No Content");
    });
  }

  // ── o construtor ─────────────────────────────────────────────────────────────────────────────────────────────
  function construtor(view) {
    var filtros = [], ordem = null, gravando = null, valores = null, promessa = null;
    var b = {
      select: function () { return b; },
      eq: function (col, val) { filtros.push(["eq", col, val]); return b; },
      neq: function (col, val) { filtros.push(["neq", col, val]); return b; },
      order: function (col, opcoes) {
        ordem = col + ":" + (opcoes && opcoes.ascending === false ? "desc" : "asc");
        return b;
      },
      insert: function (v) { gravando = "insert"; valores = v; return b; },
      update: function (v) { gravando = "update"; valores = v; return b; },
      upsert: function (v) { gravando = "upsert"; valores = v; return b; },
      delete: function () { gravando = "delete"; return b; },
      then: function (ok, falha) {
        if (!promessa) promessa = executar();
        return promessa.then(ok, falha);
      },
    };
    function executar() {
      if (gravando) {
        if (gravando === "upsert" && DERIVADAS[view]) return Promise.resolve(resposta(null, null, 201, "Created"));
        if (!GRAVA) return Promise.resolve(resposta(null, SOMENTE_LEITURA, 405, ""));
        return executarGravacao(view, gravando, valores || [], filtros);
      }
      var partes = filtros.map(function (f) { return f[0] + "=" + encodeURIComponent(f[1] + ":" + JSON.stringify(f[2])); });
      if (ordem) partes.push("order=" + encodeURIComponent(ordem));
      return pedir(cfg.api + "/rf/" + encodeURIComponent(view) + (partes.length ? "?" + partes.join("&") : ""))
        .then(function (r) {
          if (GRAVA && !r.error && Array.isArray(r.data)) guardar(view, r.data, !filtros.length);
          return r;
        });
    }
    return b;
  }

  function login() {
    return Promise.resolve({ data: null, error: { message: "O login é o do Nexus: entre pelo Nexus." } });
  }

  function createClient() {
    return {
      from: construtor,
      rpc: function (nome, args) {
        if (!GRAVA) return Promise.resolve(resposta(null, SOMENTE_LEITURA, 405, ""));
        return postar("/funcao/" + encodeURIComponent(nome), { args: args || {}, versao: versao }).then(function (r) {
          if (r.error) return r;
          avisar(r.data || {});
          return resposta((r.data || {}).dados, null, 200, "OK");
        });
      },
      auth: {
        onAuthStateChange: function (cb) {
          pedir(cfg.api + "/eu").then(function (r) {
            // sem sessão, a página inteira do Nexus recarrega e o portão leva ao login (a tela de senha do Radar não
            // serve mais)
            if (r.error && r.error.code === "SESSAO") { w.top.location.reload(); return; }
            if (r.data && typeof r.data.versao === "number") versao = r.data.versao;
            var sessao = r.data && r.data.user ? { user: r.data.user } : null;
            setTimeout(function () { cb("INITIAL_SESSION", sessao); }, 0);
          });
          return { data: { subscription: { unsubscribe: function () {} } } };
        },
        signOut: function () {
          if (cfg.sair) w.top.location.href = cfg.sair;
          return Promise.resolve({ error: null });
        },
        signInWithPassword: login,
        signUp: login,
        resetPasswordForEmail: login,
        updateUser: login,
      },
      // o arquivo dos PDFs dos contratos (06/11/2026) mora no servidor do Nexus; as fotos das rondas vêm do Fracttal (a
      // função fracttal-fotos), e por isso o arquivo `rondas-fotos` volta vazio e o Radar oferece buscar no Fracttal
      storage: {
        from: function (arquivo) {
          return {
            createSignedUrl: function (caminho) {
              if (arquivo !== "contratos-zeladoria") {
                return Promise.resolve({ data: null, error: { message: "Esse arquivo não está no Nexus." } });
              }
              return pedir(cfg.api + "/contrato-pdf?caminho=" + encodeURIComponent(caminho)).then(function (r) {
                return { data: r.error ? null : r.data, error: r.error };
              });
            },
            createSignedUrls: function () { return Promise.resolve({ data: [], error: null }); },
          };
        },
      },
      functions: {
        invoke: function (nome, opcoes) {
          return postar("/funcao/" + encodeURIComponent(nome), (opcoes && opcoes.body) || {})
            .then(function (r) { return { data: r.data, error: r.error }; });
        },
      },
    };
  }

  w.supabase = { createClient: createClient };
})(window);

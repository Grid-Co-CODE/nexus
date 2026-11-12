/* A ponte do site do SSO (nexus/sso/site/supabase-client.js) no node, com um fetch de mentira que anota cada pedido.

   Prova que o app do SSO recebe do `getSupabaseClient()` o que recebia do supabase-js v2 ({data, error}, o construtor
   que se encadeia, o single/maybeSingle, o insert com select), que o passe vem do fim do endereço e vai no
   Authorization, e que a Gestão sem passe vai ao login do Nexus.

   Uso: node tests/sso_ponte_node.js nexus/sso/site/supabase-client.js  (sai com 1 e a mensagem se algo falhar) */
"use strict";
const fs = require("fs");
const vm = require("vm");
const assert = require("assert");
const igual = (a, b) => assert.deepStrictEqual(JSON.parse(JSON.stringify(a)), JSON.parse(JSON.stringify(b)));
const codigo = fs.readFileSync(process.argv[2], "utf8");

function montar(caminho, hash, respostas) {
  const pedidos = [];
  const guardado = {};
  const location = { pathname: caminho, search: "", hash: hash || "", href: "https://sso.test" + caminho + (hash || "") };
  const window = {
    location,
    history: { replaceState: (_a, _b, u) => { location.hash = ""; location.href = "https://sso.test" + u; } },
    localStorage: { getItem: (k) => guardado[k] || null, setItem: (k, v) => { guardado[k] = v; }, removeItem: (k) => { delete guardado[k]; } },
    fetch: (url, opcoes) => {
      pedidos.push({ url: decodeURIComponent(url), opcoes: opcoes || {} });
      const r = respostas(url, opcoes || {});
      return Promise.resolve({ ok: r.status < 400, status: r.status, json: () => Promise.resolve(r.corpo) });
    },
    FormData: class { constructor() { this.campos = []; } append(k, v) { this.campos.push([k, v]); } },
  };
  window.window = window;
  vm.runInNewContext(codigo, Object.assign(window, { JSON, Promise, encodeURIComponent, decodeURIComponent }));
  return { window, pedidos, guardado, sb: window.getSupabaseClient() };
}

(async () => {
  // o formulário do fornecedor: sem passe, sem Authorization; a leitura com os filtros, a ordem e o limite
  let m = montar("/campo/index.html", "", () => ({ status: 200, corpo: [{ id: "s1", titulo: "T" }] }));
  let r = await m.sb.from("iv_sessoes_video").select("*").eq("ativo", true).order("criado_em", { ascending: false }).limit(1);
  igual(r, { data: [{ id: "s1", titulo: "T" }], error: null });
  assert.strictEqual(m.pedidos[0].url,
    'https://app.gridco.com.br/t/sso/api/v/iv_sessoes_video?eq=ativo:true&order=criado_em:desc&limit=1');
  assert.strictEqual(m.pedidos[0].opcoes.headers.Authorization, undefined);
  assert.strictEqual(m.window.IV_SUPABASE_URL, "https://app.gridco.com.br/t/sso");

  // maybeSingle: nenhuma linha é data null; single sem linha é erro, como no supabase-js
  m = montar("/campo/index.html", "", () => ({ status: 200, corpo: [] }));
  igual(await m.sb.from("iv_visualizacoes").select("*").eq("id", "v1").maybeSingle(), { data: null, error: null });
  assert.ok((await m.sb.from("iv_presencas").select("*").eq("id", "p1").single()).error);

  // o insert do fornecedor: um POST com a operação; o erro do Nexus volta no error.message
  m = montar("/apr/index.html", "", () => ({ status: 400, corpo: { message: "apr_submissoes: falta usina" } }));
  r = await m.sb.from("apr_submissoes").insert({ id: "a1" });
  igual(r.error.message, "apr_submissoes: falta usina");
  const corpo = JSON.parse(m.pedidos[0].opcoes.body);
  igual(corpo, { ops: [{ op: "insert", view: "apr_submissoes", filtros: [], linhas: [{ id: "a1" }] }] });

  // o insert com select devolve a linha; o update com eq vai com o filtro
  m = montar("/gestao/", "#nexus_sso=PASSE", (url) => ({ status: 200,
    corpo: url.indexOf("/api/eu") > 0 ? { user: { id: "u1", email: "g@x" } } : { resultado: [[{ id: "h1", acao: "criado" }]] } }));
  r = await m.sb.from("cronograma_historico").insert({ acao: "criado" }).select().maybeSingle();
  igual(r, { data: { id: "h1", acao: "criado" }, error: null });
  assert.strictEqual(m.pedidos[0].opcoes.headers.Authorization, "Bearer PASSE");      // o passe do fim do endereço
  assert.strictEqual(m.guardado.nexus_sso_passe, "PASSE");
  assert.strictEqual(m.window.location.hash, "");                                       // e o endereço fica limpo
  r = await m.sb.from("iv_presencas").update({ status_aprovacao: "aprovado" }).eq("id", "p1");
  igual(r, { data: null, error: null });
  igual(JSON.parse(m.pedidos[1].opcoes.body).ops[0].filtros, [["eq", "id", "p1"]]);

  // a sessão da Gestão vem do /api/eu, com o passe como access_token
  const s = await m.sb.auth.getSession();
  igual(s.data.session.user, { id: "u1", email: "g@x" });
  assert.strictEqual(s.data.session.access_token, "PASSE");

  // a Gestão sem passe vai ao login do Nexus, e volta à mesma página
  m = montar("/gestao/index.html", "", () => ({ status: 401, corpo: {} }));
  let chamou = false;
  m.sb.auth.onAuthStateChange(() => { chamou = true; });
  await new Promise((ok) => setTimeout(ok, 10));
  assert.strictEqual(chamou, false);
  assert.strictEqual(m.window.location.href,
    "https://app.gridco.com.br/t/sso/voltar?para=" + encodeURIComponent("https://sso.test/gestao/index.html"));

  // o envio de arquivo vai como formulário; o endereço público é o do Nexus
  m = montar("/epi/index.html", "", () => ({ status: 200, corpo: { Key: "epi-fotos/e1/item-1.jpg", url: "x" } }));
  r = await m.sb.storage.from("epi-fotos").upload("e1/item-1.jpg", "BLOB", { contentType: "image/jpeg" });
  igual(r.data.path, "e1/item-1.jpg");
  assert.strictEqual(m.pedidos[0].url, "https://app.gridco.com.br/t/sso/api/arquivo");
  igual(m.sb.storage.from("epi-fotos").getPublicUrl("e1/item-1.jpg").data.publicUrl,
    "https://app.gridco.com.br/t/sso/storage/v1/object/public/epi-fotos/e1/item-1.jpg");

  // sem rede, o erro volta no error (o app mostra; nunca lança)
  m = montar("/diario/", "", () => { throw new Error("x"); });
  m.window.fetch = () => Promise.reject(new Error("sem rede"));
  r = await m.sb.from("diario_usinas").select("nome");
  assert.ok(r.error && /conexão/.test(r.error.message));
  console.log("ok");
})().catch((e) => { console.error(e && e.stack || e); process.exit(1); });

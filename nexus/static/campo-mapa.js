/* O Mapa de equipe com o mapa de verdade (11/11/2026).
   Levi, com o guia e a prévia do Willian: "Quero que utilize essa referência para completar nosso mapa", com três
   condições: "Pode tirar a opção 3D, não deve ter pois é muito pesada e sem necessidade", "Quero que apareça só Brasil"
   e "Quero em estilo Nexus".
   - O mapa: MapLibre GL 4.7.1 (static/vendor) sobre o mapa base do Brasil, um PMTiles servido pelo próprio Nexus
     (Base > Mapa base; o esquema do Protomaps, dados do OpenStreetMap). Nenhum bloco, fonte ou rota sai para terceiro.
   - Só o Brasil: a câmera não sai do Brasil (maxBounds), e o que é de outro país fica coberto pela máscara (o contorno
     do IBGE como buraco num retângulo do mundo).
   - Sem 3D: sem inclinação, sem giro, sem terreno e sem prédio em pé (maxPitch: 0, dragRotate: false).
   - Estilo Nexus: o estilo é montado aqui a partir dos tokens do nexus.css (os dois temas), sem cor escrita no script;
     a troca de tema refaz o estilo.
   - As divisas do Brasil pulsam de leve em verde Grid (o pedido do Levi de 11/11/2026, mantido com os efeitos de animação
     do Windows desligados); a usina com ocorrência crítica pulsa (parada, com os efeitos desligados).
   O servidor manda tudo pronto no JSON #eq-dados (equipe_tela._dados_do_mapa), depois do registro da LGPD e só com a
   coordenada de quem o mapa mostra. A regra (situação, eventos, percurso, clima) é toda do servidor. */
(function () {
  "use strict";

  // ── as contas puras (testadas no node) ──────────────────────────────────────────────────────────────────────────
  function rgb(cor) {
    var c = String(cor || "").trim();
    var m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(c);
    if (m) {
      var h = m[1].length === 3 ? m[1].replace(/./g, function (x) { return x + x; }) : m[1];
      return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
    }
    m = /^rgba?\(([^)]+)\)$/i.exec(c);
    if (m) return m[1].split(",").slice(0, 3).map(function (x) { return Math.round(parseFloat(x)); });
    return [128, 128, 128];
  }
  function mistura(a, b, t) {
    // a cor `a` com a fração `t` da cor `b` (o color-mix do CSS, que o MapLibre não lê)
    var x = rgb(a), y = rgb(b);
    var r = x.map(function (v, i) { return Math.round(v + (y[i] - v) * t); });
    return "rgb(" + r.join(", ") + ")";
  }
  function comAlfa(cor, alfa) {
    return "rgba(" + rgb(cor).join(", ") + ", " + alfa + ")";
  }
  function mascara(brasil) {
    // um retângulo do mundo com o Brasil (cada pedaço do contorno do IBGE) como buraco: cobre o que é de outro país
    var buracos = [];
    (brasil.features || [brasil]).forEach(function (f) {
      var g = f.geometry || f;
      var pols = g.type === "MultiPolygon" ? g.coordinates : [g.coordinates];
      pols.forEach(function (p) { buracos.push(p[0]); });
    });
    var mundo = [[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]];
    return { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [mundo].concat(buracos) } };
  }
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { mistura: mistura, mascara: mascara, rgb: rgb };
    return;
  }

  var dadosEl = document.getElementById("eq-dados"), caixaMapa = document.getElementById("eq-mapa");
  if (!dadosEl || !caixaMapa) return;
  var D = JSON.parse(dadosEl.textContent);
  var palco = caixaMapa.parentNode, quadro = palco.closest(".eq-quadro") || palco.parentNode;
  var dica = palco.querySelector(".eq-dica"), aviso = palco.querySelector(".eq-ml-aviso");
  var raiz = document.documentElement;
  var REDUZIDO = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  var BRASIL = [[-74.1, -33.9], [-34.7, 5.4]];
  var FONTE = ["Noto Sans Regular"], FONTE_M = ["Noto Sans Medium"], FONTE_I = ["Noto Sans Italic"];

  function avisar(texto) { aviso.textContent = texto; aviso.hidden = false; }
  function temWebGL() {
    try { var c = document.createElement("canvas"); return !!(c.getContext("webgl2") || c.getContext("webgl")); }
    catch (e) { return false; }
  }
  if (!window.maplibregl || !window.pmtiles || !temWebGL()) {
    avisar("Este navegador não abre o mapa (sem WebGL). Use o desenho dos estados: acrescente ?mapa=desenho ao endereço.");
    return;
  }

  // ── as cores: os tokens do nexus.css, lidos na hora (os dois temas) ─────────────────────────────────────────────
  var TOKENS = ["--superficie", "--superficie-2", "--fundo", "--linha", "--linha-forte", "--tinta", "--tinta-2", "--mudo",
                "--verde", "--info-cheio", "--ok-cheio", "--alerta-cheio", "--critico", "--severo", "--papel", "--papel-tinta"];
  function paleta() {
    var cs = getComputedStyle(raiz), t = {};
    TOKENS.forEach(function (n) { t[n] = cs.getPropertyValue(n).trim(); });
    var claro = raiz.getAttribute("data-tema") === "claro";
    var terra = mistura(t["--superficie"], t["--verde"], claro ? 0.04 : 0.025);
    return {
      t: t, claro: claro, terra: terra,
      agua: mistura(t["--fundo"], t["--info-cheio"], claro ? 0.22 : 0.16),
      mata: mistura(terra, t["--verde"], claro ? 0.13 : 0.07),
      urbano: mistura(terra, t["--tinta"], claro ? 0.07 : 0.06),
      predio: mistura(terra, t["--tinta"], claro ? 0.14 : 0.12),
      casco: mistura(t["--fundo"], t["--tinta"], claro ? 0.12 : 0.0),
      viaRodovia: mistura(t["--tinta-2"], t["--verde"], claro ? 0.35 : 0.42),
      viaMaior: mistura(terra, t["--tinta-2"], claro ? 0.6 : 0.5),
      viaMedia: mistura(terra, t["--tinta-2"], claro ? 0.45 : 0.34),
      viaMenor: mistura(terra, t["--tinta-2"], claro ? 0.3 : 0.2),
      limiteUf: mistura(t["--linha-forte"], t["--verde"], claro ? 0.45 : 0.4),
      verde: t["--verde"], rotulo: t["--tinta-2"], forte: t["--tinta"], fraco: t["--mudo"],
      halo: claro ? t["--superficie"] : t["--fundo"],
      fora: comAlfa(t["--fundo"], claro ? 0.86 : 0.9),
      rotuloAgua: mistura(t["--info-cheio"], t["--tinta-2"], 0.35)
    };
  }
  var P = paleta();
  var TOM = function () {
    return { info: P.t["--info-cheio"], ok: P.t["--ok-cheio"], alerta: P.t["--alerta-cheio"], critico: P.t["--critico"],
             neutro: P.t["--mudo"] };
  };
  var NIVEL = function () {
    return { agir: P.t["--critico"], atencao: P.t["--alerta-cheio"], regiao: P.t["--info-cheio"], sem: P.t["--ok-cheio"],
             nx: P.t["--mudo"] };
  };
  var nome = ["coalesce", ["get", "name:pt"], ["get", "name"]];
  var z = function (pares) { return ["interpolate", ["exponential", 1.5], ["zoom"]].concat([].concat.apply([], pares)); };

  // ── o estilo do mapa base (o esquema do Protomaps v4) ───────────────────────────────────────────────────────────
  function estilo() {
    var via = function (id, filtro, cor, larg, min, casco) {
      var f = ["all", ["==", ["geometry-type"], "LineString"], filtro, ["!=", ["get", "is_tunnel"], true]];
      var out = [];
      if (casco) out.push({ id: "casco-" + id, type: "line", source: "base", "source-layer": "roads", minzoom: Math.max(min, 9),
        filter: f, layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": P.casco, "line-width": z(larg.map(function (p) { return [p[0], p[1] + (p[0] >= 12 ? 2.4 : 1.2)]; })) } });
      out.push({ id: "via-" + id, type: "line", source: "base", "source-layer": "roads", minzoom: min, filter: f,
        layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": cor, "line-width": z(larg) } });
      return out;
    };
    var k = function (v) { return ["==", ["get", "kind"], v]; };
    var vias = [].concat(
      via("menor", ["in", ["get", "kind"], ["literal", ["minor_road", "other"]]], P.viaMenor, [[12, 0.4], [14, 1.6], [17, 7]], 12, true),
      via("media", k("medium_road"), P.viaMedia, [[9, 0.4], [12, 1.1], [15, 3.4], [18, 12]], 9, true),
      via("maior", k("major_road"), P.viaMaior, [[6.5, 0.5], [10, 1.3], [14, 4.2], [18, 16]], 6, true),
      via("rodovia", k("highway"), P.viaRodovia, [[4.5, 0.6], [9, 1.6], [13, 4.4], [18, 20]], 4, true));
    return {
      version: 8,
      glyphs: new URL(D.fontes.replace("{fontstack}", "FONTSTACK").replace("{range}", "RANGE"), location.href).href
        .replace("FONTSTACK", "{fontstack}").replace("RANGE", "{range}"),
      sources: {
        base: { type: "vector", url: "pmtiles://" + new URL(D.blocos, location.href).href,
                attribution: "© OpenStreetMap · Protomaps" }
      },
      layers: [
        { id: "fundo", type: "background", paint: { "background-color": P.agua } },
        { id: "terra", type: "fill", source: "base", "source-layer": "earth", paint: { "fill-color": P.terra } },
        { id: "mata-baixa", type: "fill", source: "base", "source-layer": "landcover", filter: ["in", ["get", "kind"], ["literal", ["forest", "scrub", "grassland"]]],
          paint: { "fill-color": P.mata, "fill-opacity": 0.6 } },
        { id: "uso-verde", type: "fill", source: "base", "source-layer": "landuse",
          filter: ["in", ["get", "kind"], ["literal", ["park", "national_park", "nature_reserve", "protected_area", "forest", "wood", "grass", "meadow", "scrub", "garden"]]],
          paint: { "fill-color": P.mata, "fill-opacity": ["interpolate", ["linear"], ["zoom"], 6, 0.5, 12, 0.9] } },
        { id: "uso-urbano", type: "fill", source: "base", "source-layer": "landuse",
          filter: ["in", ["get", "kind"], ["literal", ["residential", "commercial", "industrial", "retail", "neighbourhood", "urban_area", "railway"]]],
          paint: { "fill-color": P.urbano } },
        { id: "agua", type: "fill", source: "base", "source-layer": "water", filter: ["==", ["geometry-type"], "Polygon"],
          paint: { "fill-color": P.agua } },
        { id: "rio", type: "line", source: "base", "source-layer": "water", minzoom: 7,
          filter: ["all", ["==", ["geometry-type"], "LineString"], ["in", ["get", "kind"], ["literal", ["river", "canal", "stream"]]]],
          layout: { "line-cap": "round" },
          paint: { "line-color": P.agua, "line-width": ["interpolate", ["exponential", 1.5], ["zoom"], 8, ["match", ["get", "kind"], "river", 0.8, 0.2], 14, ["match", ["get", "kind"], "river", 4, 1.2], 18, ["match", ["get", "kind"], "river", 14, 4]] } },
        { id: "predio", type: "fill", source: "base", "source-layer": "buildings", minzoom: 13.5,
          paint: { "fill-color": P.predio, "fill-opacity": ["interpolate", ["linear"], ["zoom"], 13.5, 0, 14.5, 1] } },
        { id: "limite-uf", type: "line", source: "base", "source-layer": "boundaries", filter: k("region"),
          paint: { "line-color": P.limiteUf, "line-width": ["interpolate", ["linear"], ["zoom"], 3, 0.7, 10, 1.5], "line-dasharray": [3, 2] } }
      ].concat(vias, [
        { id: "trilho", type: "line", source: "base", "source-layer": "roads", minzoom: 10, filter: k("rail"),
          paint: { "line-color": P.viaMenor, "line-width": ["interpolate", ["linear"], ["zoom"], 10, 0.6, 16, 2], "line-dasharray": [3, 3] } },
        { id: "nome-rio", type: "symbol", source: "base", "source-layer": "water", minzoom: 11,
          filter: ["all", ["==", ["geometry-type"], "LineString"], k("river")],
          layout: { "symbol-placement": "line", "text-field": nome, "text-font": FONTE_I, "text-size": 11, "symbol-spacing": 400 },
          paint: { "text-color": P.rotuloAgua, "text-halo-color": P.halo, "text-halo-width": 1.4 } },
        { id: "nome-rua", type: "symbol", source: "base", "source-layer": "roads", minzoom: 13.5,
          filter: ["in", ["get", "kind"], ["literal", ["major_road", "medium_road", "minor_road"]]],
          layout: { "symbol-placement": "line", "text-field": nome, "text-font": FONTE, "text-size": ["interpolate", ["linear"], ["zoom"], 14, 10.5, 18, 13], "symbol-spacing": 300, "text-max-angle": 30 },
          paint: { "text-color": P.rotulo, "text-halo-color": P.halo, "text-halo-width": 1.5 } },
        { id: "numero-via", type: "symbol", source: "base", "source-layer": "roads", minzoom: 7,
          filter: ["all", ["in", ["get", "kind"], ["literal", ["highway", "major_road"]]], ["has", "ref"]],
          layout: { "symbol-placement": "line", "symbol-spacing": ["interpolate", ["linear"], ["zoom"], 7, 300, 14, 500],
                    "text-field": ["get", "ref"], "text-font": FONTE_M, "text-size": 10, "text-rotation-alignment": "viewport" },
          paint: { "text-color": P.forte, "text-halo-color": P.casco, "text-halo-width": 2 } },
        { id: "nome-bairro", type: "symbol", source: "base", "source-layer": "places", minzoom: 12.5,
          filter: ["in", ["get", "kind"], ["literal", ["neighbourhood", "macrohood"]]],
          layout: { "text-field": nome, "text-font": FONTE, "text-size": 11, "text-letter-spacing": 0.04 },
          paint: { "text-color": P.fraco, "text-halo-color": P.halo, "text-halo-width": 1.4 } },
        { id: "nome-cidade", type: "symbol", source: "base", "source-layer": "places", minzoom: 5,
          filter: k("locality"),
          layout: { "text-field": nome, "text-font": FONTE_M,
                    "text-size": ["interpolate", ["linear"], ["zoom"], 5, 10.5, 10, 13, 14, 15],
                    "symbol-sort-key": ["coalesce", ["get", "min_zoom"], 20] },
          paint: { "text-color": P.rotulo, "text-halo-color": P.halo, "text-halo-width": 1.6 } },
        { id: "nome-uf", type: "symbol", source: "base", "source-layer": "places", minzoom: 3.5, maxzoom: 7, filter: k("region"),
          layout: { "text-field": nome, "text-font": FONTE_M, "text-size": 11, "text-transform": "uppercase", "text-letter-spacing": 0.14 },
          paint: { "text-color": mistura(P.fraco, P.verde, 0.35), "text-halo-color": P.halo, "text-halo-width": 1.2 } }
      ])
    };
  }

  // ── os ícones: a usina é um losango (o técnico é o círculo), na cor do dado ─────────────────────────────────────
  function losango(fundo, borda, selo) {
    var px = 2, L = 26, cv = document.createElement("canvas");
    cv.width = cv.height = L * px;
    var g = cv.getContext("2d");
    g.scale(px, px);
    g.beginPath(); g.moveTo(13, 2.5); g.lineTo(23.5, 13); g.lineTo(13, 23.5); g.lineTo(2.5, 13); g.closePath();
    g.fillStyle = fundo; g.fill(); g.lineWidth = 2; g.strokeStyle = borda; g.stroke();
    if (selo) {
      g.beginPath(); g.arc(20, 6, 5, 0, Math.PI * 2); g.fillStyle = selo; g.fill();
      g.lineWidth = 1.4; g.strokeStyle = P.t["--fundo"]; g.stroke();
      g.strokeStyle = P.t["--fundo"]; g.lineWidth = 1.6; g.lineCap = "round";
      g.beginPath(); g.moveTo(20, 3.6); g.lineTo(20, 6.6); g.moveTo(20, 8.4); g.lineTo(20, 8.5); g.stroke();
    }
    return g.getImageData(0, 0, cv.width, cv.height);
  }
  function icones(mapa) {
    var cores = NIVEL();
    var fill = { neutra: P.terra, dest: P.verde, oc_critico: P.t["--critico"], oc_alerta: P.t["--alerta-cheio"] };
    Object.keys(cores).forEach(function (k) { fill[k] = cores[k]; });
    Object.keys(fill).forEach(function (k) {
      var borda = k === "neutra" ? P.verde : P.t["--fundo"];
      [false, true].forEach(function (comSelo) {
        var id = "u-" + k + (comSelo ? "-!" : "");
        if (mapa.hasImage(id)) mapa.removeImage(id);
        mapa.addImage(id, losango(fill[k], borda, comSelo ? P.t["--critico"] : null), { pixelRatio: 2 });
      });
    });
  }

  // ── os dados nossos em GeoJSON ──────────────────────────────────────────────────────────────────────────────────
  function fc(feats) { return { type: "FeatureCollection", features: feats }; }
  function ponto(c, props) { return { type: "Feature", geometry: { type: "Point", coordinates: c }, properties: props || {} }; }
  function usinasGeo() {
    var ORD = { agir: 9, atencao: 7, oc_critico: 8, oc_alerta: 6, regiao: 4, nx: 2, sem: 3, dest: 1, neutra: 0 };
    return fc(D.usinas.map(function (u) {
      var cor = u.nivel || (u.oc && u.oc.tom === "critico" ? "oc_critico" : u.oc && u.oc.tom === "alerta" ? "oc_alerta"
                : D.modo === "usinas" ? "dest" : "neutra");
      var selo = !!(u.nivel && u.oc && (u.oc.tom === "critico" || u.oc.tom === "alerta"));
      return ponto(u.c, { id: u.id, nome: u.nome, icone: "u-" + cor + (selo ? "-!" : ""), ordem: ORD[cor] || 0,
                          pulso: cor === "agir" || cor === "oc_critico" });
    }));
  }
  function tecnicosGeo() {
    var tom = TOM();
    return fc(D.tecnicos.map(function (t) {
      return ponto(t.c, { pid: t.pid, ini: t.ini, cor: tom[t.tom] || tom.neutro, velho: t.velho, sel: t.sel,
                          ordem: t.sel ? 3 : t.velho ? 0 : 1 });
    }));
  }
  function percursoGeo() {
    var p = D.percurso;
    if (!p) return { linha: fc([]), pontos: fc([]), marcos: fc([]) };
    var tom = TOM(), n = p.pontos.length;
    return {
      linha: fc([{ type: "Feature", geometry: { type: "LineString", coordinates: p.linha }, properties: {} }]),
      pontos: fc(p.pontos.map(function (q, i) {
        return ponto(q.c, { cor: q.mov ? tom.info : tom.neutro, ponta: i === 0 || i === n - 1, hora: q.hora });
      })),
      marcos: fc(p.marcos.map(function (m) { return ponto(m.c, { texto: m.hora + " · " + m.texto, tipo: m.tipo }); }))
    };
  }

  // ── o mapa ──────────────────────────────────────────────────────────────────────────────────────────────────────
  var protocolo = new pmtiles.Protocol();
  maplibregl.addProtocol("pmtiles", protocolo.tile);
  var mapa;
  try {
    mapa = new maplibregl.Map({
      container: caixaMapa, style: estilo(), bounds: BRASIL, fitBoundsOptions: { padding: 24 },
      maxBounds: [[-100, -48], [-12, 18]], minZoom: 2.5, maxZoom: 17.5,
      maxPitch: 0, dragRotate: false, pitchWithRotate: false, touchPitch: false,
      attributionControl: { compact: true }, fadeDuration: REDUZIDO ? 0 : 180, locale: {
        "NavigationControl.ZoomIn": "Aproximar", "NavigationControl.ZoomOut": "Afastar",
        "AttributionControl.ToggleAttribution": "Créditos do mapa", "ScaleControl.Meters": "m", "ScaleControl.Kilometers": "km" }
    });
  } catch (e) {
    avisar("O mapa não abriu neste navegador (" + e.message + "). Use o desenho dos estados: acrescente ?mapa=desenho ao endereço.");
    return;
  }
  caixaMapa.mapa = mapa;          // para a conferência no navegador (a bancada e o teste de produção)
  mapa.touchZoomRotate.disableRotation();
  mapa.keyboard.disableRotation();
  mapa.addControl(new maplibregl.ScaleControl({ unit: "metric", maxWidth: 110 }), "bottom-left");
  mapa.on("error", function (ev) {
    var msg = ev && ev.error && ev.error.message || "";
    if (window.console) console.warn("Mapa de equipe:", msg);
    if (/404|pmtiles|Failed to fetch/i.test(msg)) avisar("O mapa base não respondeu agora (" + msg.slice(0, 80) + "). Recarregue a página.");
  });

  var brasilGeo = null;
  function nossas() {
    icones(mapa);
    var vazio = fc([]), pg = percursoGeo();
    var add = function (id, data) { if (!mapa.getSource(id)) mapa.addSource(id, { type: "geojson", data: data }); };
    add("fora", brasilGeo ? fc([mascara(brasilGeo)]) : vazio);
    add("brasil", brasilGeo || vazio);
    add("avisos", D.clima ? D.clima.avisos : vazio);
    add("focos", fc(D.clima ? D.clima.focos.map(function (c) { return ponto(c); }) : []));
    add("aneis", fc(D.clima ? D.clima.aneis.map(function (c) { return ponto(c); }) : []));
    add("usinas", usinasGeo());
    add("tecnicos", tecnicosGeo());
    add("perc-linha", pg.linha);
    add("perc-pontos", pg.pontos);
    add("perc-marcos", pg.marcos);
    var nv = { 1: P.t["--alerta-cheio"], 2: P.t["--severo"], 3: P.t["--critico"] };
    var corAviso = ["match", ["get", "nivel"], 1, nv[1], 2, nv[2], nv[3]];
    var L = [
      // só o Brasil: o resto do mundo coberto, e o contorno do país em verde Grid (pulsa de leve)
      { id: "fora", type: "fill", source: "fora", paint: { "fill-color": P.fora } },
      { id: "brasil-borda", type: "line", source: "brasil", layout: { "line-join": "round" },
        paint: { "line-color": P.verde, "line-width": ["interpolate", ["linear"], ["zoom"], 3, 1.2, 10, 2.4], "line-opacity": 0.85,
                 "line-opacity-transition": { duration: 1300, delay: 0 } } },
      // o clima: a área do aviso (o que ainda vai começar, só o contorno tracejado), os focos e o anel perto de usina
      { id: "avisos", type: "fill", source: "avisos", filter: ["!", ["get", "futuro"]], paint: { "fill-color": corAviso, "fill-opacity": 0.24 } },
      { id: "avisos-futuro", type: "line", source: "avisos", filter: ["get", "futuro"], paint: { "line-color": corAviso, "line-width": 1.5, "line-dasharray": [3, 2] } },
      { id: "focos", type: "circle", source: "focos", paint: { "circle-color": P.t["--severo"], "circle-opacity": 0.8, "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 1.6, 10, 3.2] } },
      { id: "aneis", type: "circle", source: "aneis", paint: { "circle-color": comAlfa(P.t["--critico"], 0.12), "circle-stroke-color": P.t["--critico"], "circle-stroke-width": 2, "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 6, 12, 14] } },
      // o percurso: a linha em verde Grid com um halo largo, os pontos (de perto) e os marcos com a hora
      { id: "perc-halo", type: "line", source: "perc-linha", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": P.verde, "line-opacity": 0.2, "line-width": z([[5, 6], [12, 12], [16, 18]]) } },
      { id: "perc-linha", type: "line", source: "perc-linha", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": P.verde, "line-width": z([[5, 2.2], [12, 3.6], [16, 5.5]]) } },
      { id: "perc-pontos", type: "circle", source: "perc-pontos", minzoom: 9, filter: ["!", ["get", "ponta"]], paint: { "circle-color": ["get", "cor"], "circle-radius": 3.6, "circle-stroke-color": P.t["--superficie"], "circle-stroke-width": 1.2 } },
      { id: "perc-pontas", type: "circle", source: "perc-pontos", filter: ["get", "ponta"], paint: { "circle-color": ["get", "cor"], "circle-radius": 7, "circle-stroke-color": P.forte, "circle-stroke-width": 2.4 } },
      // a usina: o losango que cresce com o zoom (Levi, 11/11/2026), uma a uma (nunca agrupada); a crítica pulsa
      { id: "usinas-pulso", type: "circle", source: "usinas", filter: ["get", "pulso"], paint: { "circle-color": comAlfa(P.t["--critico"], 0), "circle-stroke-color": P.t["--critico"], "circle-stroke-width": 2, "circle-radius": 12, "circle-stroke-opacity": 0.75,
        "circle-radius-transition": { duration: REDUZIDO ? 0 : 1100 }, "circle-stroke-opacity-transition": { duration: REDUZIDO ? 0 : 1100 } } },
      { id: "usinas", type: "symbol", source: "usinas", layout: { "icon-image": ["get", "icone"], "icon-size": ["interpolate", ["linear"], ["zoom"], 3, 0.5, 6, 0.65, 9, 0.85, 12, 1.1, 15, 1.4],
        "icon-allow-overlap": true, "icon-ignore-placement": true, "symbol-sort-key": ["get", "ordem"] } },
      { id: "usinas-nome", type: "symbol", source: "usinas", minzoom: 8.5, layout: { "text-field": ["get", "nome"], "text-font": FONTE_M, "text-size": ["interpolate", ["linear"], ["zoom"], 8.5, 10.5, 13, 12.5],
        "text-variable-anchor": ["left", "right", "top", "bottom"], "text-radial-offset": 1.1, "text-optional": true }, paint: { "text-color": P.forte, "text-halo-color": P.halo, "text-halo-width": 1.6 } },
      { id: "perc-marcos", type: "symbol", source: "perc-marcos", layout: { "text-field": ["get", "texto"], "text-font": FONTE_M, "text-size": 11.5, "text-max-width": 16,
        "text-variable-anchor": ["left", "right", "top", "bottom"], "text-radial-offset": 1.2, "text-justify": "auto" }, paint: { "text-color": P.forte, "text-halo-color": P.halo, "text-halo-width": 1.8 } },
      // o técnico: o círculo na cor da situação (de outro dia, só o contorno); o escolhido com o anel branco e o halo escuro
      { id: "tecnicos-halo", type: "circle", source: "tecnicos", filter: ["get", "sel"], paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 12, 10, 15], "circle-color": P.t["--papel-tinta"] } },
      { id: "tecnicos", type: "circle", source: "tecnicos", layout: { "circle-sort-key": ["get", "ordem"] }, paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 7, 10, 10.5],
        "circle-color": ["case", ["get", "velho"], P.t["--superficie"], ["get", "cor"]],
        "circle-stroke-color": ["case", ["get", "sel"], P.t["--papel"], ["get", "velho"], P.t["--mudo"], P.t["--superficie"]],
        "circle-stroke-width": ["case", ["get", "sel"], 3.2, ["get", "velho"], 2.6, 1.8] } },
      { id: "tecnicos-ini", type: "symbol", source: "tecnicos", minzoom: 5.5, layout: { "text-field": ["get", "ini"], "text-font": FONTE_M, "text-size": 9.5, "text-allow-overlap": true, "text-ignore-placement": true },
        paint: { "text-color": ["case", ["get", "velho"], P.fraco, P.t["--fundo"]] } }
    ];
    L.forEach(function (l) { if (!mapa.getLayer(l.id)) mapa.addLayer(l); });
  }

  // o pulso: as divisas do Brasil (sempre, pedido do Levi) e a usina crítica (parada com os efeitos desligados)
  var fase = false;
  setInterval(function () {
    if (!mapa.getLayer("brasil-borda")) return;
    fase = !fase;
    mapa.setPaintProperty("brasil-borda", "line-opacity", fase ? 0.35 : 0.95);
    if (!REDUZIDO && mapa.getLayer("usinas-pulso")) {
      mapa.setPaintProperty("usinas-pulso", "circle-radius", fase ? 20 : 12);
      mapa.setPaintProperty("usinas-pulso", "circle-stroke-opacity", fase ? 0.05 : 0.75);
    }
  }, 1300);

  mapa.on("load", function () {
    fetch(new URL(D.brasil, location.href).href, { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (g) { brasilGeo = g; }).catch(function () { brasilGeo = null; })
      .then(function () { nossas(); });
  });
  // a troca de tema refaz o estilo com as cores do tema novo; só depois do 1º carregamento e só quando o tema MUDA (o
  // base.html regrava o mesmo data-tema ao abrir a página, e refazer o estilo no meio do carregamento o deixava vazio)
  var temaAtual = raiz.getAttribute("data-tema"), carregado = false;
  function trocarTema() {
    var t = raiz.getAttribute("data-tema");
    if (!carregado || t === temaAtual) return;
    temaAtual = t;
    P = paleta();
    mapa.setStyle(estilo(), { diff: false });
    mapa.once("style.load", nossas);
  }
  // a troca no meio do carregamento fica para o fim dele
  mapa.once("load", function () { carregado = true; trocarTema(); });
  new MutationObserver(trocarTema).observe(raiz, { attributes: true, attributeFilter: ["data-tema"] });

  // ── a dica, o clique e os botões ────────────────────────────────────────────────────────────────────────────────
  var porPid = {}, porUsina = {};
  D.tecnicos.forEach(function (t) { porPid[t.pid] = t; });
  D.usinas.forEach(function (u) { porUsina[u.id] = u; });
  function linha(tag, texto) {
    if (!texto) return;
    var e = document.createElement(tag); e.textContent = texto; dica.appendChild(e);
  }
  function mostrar(linhas, x, y) {
    dica.textContent = "";
    linha("b", linhas[0]); linha("span", linhas[1]); linha("small", linhas[2]); linha("small", linhas[3]);
    dica.hidden = false;
    var q = palco.getBoundingClientRect(), w = dica.offsetWidth, h = dica.offsetHeight;
    var esq = x + 14, topo = y + 14;
    if (esq + w > q.width - 6) esq = x - w - 10;
    if (topo + h > q.height - 6) topo = y - h - 10;
    dica.style.left = Math.max(6, esq) + "px";
    dica.style.top = Math.max(6, topo) + "px";
  }
  function esconder() { dica.hidden = true; }
  mapa.on("mousemove", "tecnicos", function (e) {
    var t = porPid[e.features[0].properties.pid];
    if (!t) return;
    mapa.getCanvas().style.cursor = "pointer";
    mostrar([t.nome, t.equipe || "sem equipe", t.rotulo + (t.velho ? " · última posição " + t.hora : ""),
             "Clique para ver o percurso do dia"], e.point.x, e.point.y);
  });
  mapa.on("mousemove", "usinas", function (e) {
    var u = porUsina[e.features[0].properties.id];
    if (!u) return;
    mapa.getCanvas().style.cursor = "pointer";
    var oc = u.oc ? u.oc.n + (u.oc.n === 1 ? " ocorrência aberta" : " ocorrências abertas") : "";
    mostrar([u.nome, u.onde, u.rotulo ? u.rotulo + (u.motivo ? ": " + u.motivo : "") : "", oc], e.point.x, e.point.y);
  });
  ["tecnicos", "usinas"].forEach(function (id) {
    mapa.on("mouseleave", id, function () { mapa.getCanvas().style.cursor = ""; esconder(); });
  });
  mapa.on("dragstart", esconder);
  mapa.on("click", "tecnicos", function (e) {
    var t = porPid[e.features[0].properties.pid];
    if (t && t.url) location.href = t.url;
  });
  mapa.on("click", "usinas", function (e) {
    var c = e.features[0].geometry.coordinates;
    mapa.flyTo({ center: c, zoom: Math.max(mapa.getZoom(), 12.5), duration: REDUZIDO ? 0 : 900, essential: true });
  });
  quadro.addEventListener("click", function (e) {
    var b = e.target.closest("[data-eq-zoom]");
    if (!b) return;
    var q = b.getAttribute("data-eq-zoom"), dur = REDUZIDO ? 0 : 600;
    if (q === "mais") mapa.zoomIn({ duration: dur });
    else if (q === "menos") mapa.zoomOut({ duration: dur });
    else if (q === "inteiro") mapa.fitBounds(BRASIL, { padding: 24, duration: dur });
    else if (q === "percurso" && D.percurso) {
      var cx = D.percurso.caixa;
      mapa.fitBounds([[cx[0], cx[1]], [cx[2], cx[3]]], { padding: 90, maxZoom: 15, duration: REDUZIDO ? 0 : 900 });
    }
  });
})();

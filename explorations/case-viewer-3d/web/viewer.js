// FirePA case viewer engine. Case-specific content lives in cases.js.
const BASE = location.origin + location.pathname.replace(/[^/]*$/, "");
const TZ_OFFSET_H = -5; // Panamá, sin horario de verano
const EXAGGERATION = 1.5;
const FRP_M_PER_MW = 35; // altura de columna: metros por MW de FRP máximo
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const fmtNum = (v, d = 1) => v == null ? "—" : v.toLocaleString("es-PA", { minimumFractionDigits: d, maximumFractionDigits: d });
const pad = n => String(n).padStart(2, "0");
function fmtUTC(ms) { const d = new Date(ms); return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`; }
function fmtLocal(ms) { const d = new Date(ms + TZ_OFFSET_H * 3600e3); return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} hora PA`; }
function fmtDay(ms) { const d = new Date(ms + TZ_OFFSET_H * 3600e3); return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`; }
const sleep = ms => new Promise(r => setTimeout(r, ms));
const ease = x => x < .5 ? 2 * x * x : 1 - Math.pow(-2 * x + 2, 2) / 2;
function circleRing([lon, lat], radiusM, steps = 48) {
  const coords = [];
  for (let i = 0; i <= steps; i++) {
    const a = (i / steps) * 2 * Math.PI;
    coords.push([lon + radiusM * Math.cos(a) / (111320 * Math.cos(lat * Math.PI / 180)), lat + radiusM * Math.sin(a) / 110574]);
  }
  return coords;
}
const circlePolygon = (c, r, steps) => ({ type: "Feature", geometry: { type: "Polygon", coordinates: [circleRing(c, r, steps)] }, properties: {} });
const H = { fmtNum, fmtUTC, fmtLocal, fmtDay, sleep };

(async function main() {
  const caseId = new URLSearchParams(location.search).get("caso") in window.FIREPA_CASES ? new URLSearchParams(location.search).get("caso") : "guacamaya";
  document.querySelectorAll(".cases a").forEach(a => a.dataset.case === caseId ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
  const P = await window.FIREPA_CASES[caseId](H);
  document.title = `FirePA · ${P.meta.title}`;
  document.getElementById("loading-title").textContent = P.meta.title;
  document.getElementById("mh-eyebrow").textContent = P.meta.eyebrow;
  document.getElementById("mh-title").textContent = P.meta.title;
  document.getElementById("mh-lede").textContent = P.meta.lede;
  document.getElementById("blend-a").textContent = P.blendLabels[0];
  document.getElementById("blend-b").textContent = P.blendLabels[1];
  document.getElementById("legend").innerHTML = P.legend;

  const clusters = P.clusters.map(c => ({ ...c, start: Date.parse(c.cluster_start_utc), end: Date.parse(c.cluster_end_utc) }));
  const totalDetections = clusters.reduce((s, c) => s + c.detection_count, 0);
  const [aoiW, aoiS, aoiE, aoiN] = P.tileAoi;
  const IMG = P.imagery;

  const sources = {
    relief: { type: "raster", tiles: [BASE + "tiles/relief/{z}/{x}/{y}.webp"], tileSize: 256, minzoom: 8, maxzoom: 14, bounds: P.tileAoi,
      attribution: "Relieve: Copernicus DEM GLO-30 © DLR e.V. 2010-2014 y © Airbus Defence and Space GmbH 2014-2018, Copernicus/UE/ESA · Imagen: contains modified Copernicus Sentinel data 2024-2025 · Datos: NASA FIRMS vía FirePA v1" },
    dem: { type: "raster-dem", tiles: [BASE + "tiles/dem/{z}/{x}/{y}.png"], tileSize: 256, minzoom: 8, maxzoom: 12, encoding: "terrarium", bounds: P.tileAoi },
    demHs: { type: "raster-dem", tiles: [BASE + "tiles/dem/{z}/{x}/{y}.png"], tileSize: 256, minzoom: 8, maxzoom: 12, encoding: "terrarium", bounds: P.tileAoi },
    detPre: { type: "image", url: IMG.detPre, coordinates: IMG.detCorners },
    detPost: { type: "image", url: IMG.detPost, coordinates: IMG.detCorners },
    dnbr: { type: "image", url: IMG.dnbr, coordinates: IMG.detCorners },
    outline: { type: "image", url: IMG.outline, coordinates: IMG.detCorners },
    cocle: { type: "geojson", data: "data/cocle.geojson" },
    matchRadius: { type: "geojson", data: circlePolygon(P.anchor.coordinates, P.anchor.official_matching_radius_m, 128) },
    anchor: { type: "geojson", data: { type: "Feature", geometry: { type: "Point", coordinates: P.anchor.coordinates }, properties: { label: "Ancla aproximada" } } },
    clusters: { type: "geojson", data: { type: "FeatureCollection", features: [] } },
    columns: { type: "geojson", data: { type: "FeatureCollection", features: [] } }
  };
  const imgPaint = { "raster-opacity": 0, "raster-fade-duration": 0, "raster-opacity-transition": { duration: 0 } };
  const layers = [
    { id: "bg", type: "background", paint: { "background-color": "#ddd5c6" } },
    { id: "relief", type: "raster", source: "relief", paint: { "raster-fade-duration": 200 } }
  ];
  if (IMG.ctxPre) {
    sources.ctxPre = { type: "image", url: IMG.ctxPre, coordinates: IMG.ctxCorners };
    sources.ctxPost = { type: "image", url: IMG.ctxPost, coordinates: IMG.ctxCorners };
    layers.push({ id: "ctxPre", type: "raster", source: "ctxPre", paint: { ...imgPaint } }, { id: "ctxPost", type: "raster", source: "ctxPost", paint: { ...imgPaint } });
  }
  layers.push(
    { id: "detPre", type: "raster", source: "detPre", paint: { ...imgPaint } },
    { id: "detPost", type: "raster", source: "detPost", paint: { ...imgPaint } },
    { id: "hillshade", type: "hillshade", source: "demHs", paint: { "hillshade-exaggeration": 0.28, "hillshade-shadow-color": "#2a2620", "hillshade-highlight-color": "#fff8ea", "hillshade-accent-color": "#2a2620", "hillshade-illumination-direction": 315 } },
    { id: "dnbr", type: "raster", source: "dnbr", paint: { ...imgPaint, "raster-resampling": "nearest" } },
    { id: "outline", type: "raster", source: "outline", paint: { ...imgPaint, "raster-resampling": "nearest" } },
    { id: "cocle-line", type: "line", source: "cocle", paint: { "line-color": "#f3eee4", "line-opacity": 0.75, "line-width": 1.3, "line-dasharray": [4, 2] } },
    { id: "radius-line", type: "line", source: "matchRadius", paint: { "line-color": "#d7e6f0", "line-width": 1.6, "line-dasharray": [2, 2], "line-opacity": 0.9 } },
    { id: "anchor-pt", type: "circle", source: "anchor", paint: { "circle-radius": 5, "circle-color": "#f3eee4", "circle-stroke-color": "#477797", "circle-stroke-width": 2.2, "circle-pitch-alignment": "map" } },
    { id: "cluster-halo", type: "circle", source: "clusters", filter: ["get", "current"], paint: { "circle-radius": 18, "circle-color": "#ff8a4c", "circle-opacity": 0.25, "circle-blur": 0.6, "circle-pitch-alignment": "map" } },
    { id: "columns", type: "fill-extrusion", source: "columns", paint: {
      "fill-extrusion-color": ["case", ["get", "current"], "#ffe2b0", "#f2b45c"],
      "fill-extrusion-height": ["get", "height"], "fill-extrusion-base": 0, "fill-extrusion-opacity": 0.88, "fill-extrusion-vertical-gradient": true } },
    { id: "cluster-pt", type: "circle", source: "clusters", paint: {
      "circle-radius": ["+", 3.5, ["*", 1.3, ["get", "detection_count"]]],
      "circle-color": ["case", ["get", "current"], "#ff7a3d", "#c4572f"],
      "circle-opacity": ["case", ["get", "current"], 1, 0.75],
      "circle-stroke-color": ["case", ["get", "selected"], "#1a1917", "#fff4e6"],
      "circle-stroke-width": ["case", ["get", "selected"], 2.4, 1.4],
      "circle-pitch-alignment": "map" } },
  );

  const map = new maplibregl.Map({
    container: "map",
    maxBounds: [[aoiW - 0.1, aoiS - 0.1], [aoiE + 0.1, aoiN + 0.1]],
    center: P.views[P.startView].center, zoom: P.views[P.startView].zoom - 2.2, pitch: 0, bearing: 0,
    maxPitch: 80,
    attributionControl: { compact: true },
    style: {
      version: 8,
      sky: { "sky-color": "#dcd3c3", "horizon-color": "#efe8dc", "fog-color": "#e9e2d5", "sky-horizon-blend": 0.55, "horizon-fog-blend": 0.6, "fog-ground-blend": 0.25 },
      sources, layers,
      terrain: { source: "dem", exaggeration: EXAGGERATION }
    }
  });
  map.on("error", e => console.error("MAP ERROR", e.sourceId || "", e.error && e.error.message));
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "bottom-right");
  map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");
  const ready = new Promise(r => map.once("load", r));
  // Text labels are HTML markers, so the style needs no glyph server.
  function label(text, cls, lngLat, anchor = "bottom", offset = [0, -8]) {
    const el = document.createElement("div");
    el.className = `map-label ${cls}`;
    el.textContent = text;
    return new maplibregl.Marker({ element: el, anchor, offset }).setLngLat(lngLat).addTo(map);
  }
  label("Ancla aproximada", "anchor", P.anchor.coordinates, "top", [0, 8]);
  P.summits.forEach(sm => label(sm.label, "summit", sm.coordinates));
  const clusterLabels = new Map(P.clusters.map(c => [c.public_event_id, label(c.label, "cluster", c.centroid, "bottom", [0, -12])]));
  const whenReady = fn => map.isStyleLoaded() ? fn() : ready.then(fn);

  // ---------- State ----------
  let t = P.initialTime, selected = null, is3D = true, orbiting = false, playing = false, touring = false;
  let base = "sat", blend = P.initialBlend, scarOn = false, scarK = 0, colsOn = true;

  // MapLibre caches layers draped on 3D terrain; paint changes need the cache cleared.
  function refreshTerrain() {
    const sc = map.terrain && map.terrain.sourceCache;
    if (sc && typeof sc.freeRtt === "function") sc.freeRtt();
    map.triggerRepaint();
  }
  function currentCluster() {
    const visible = clusters.filter(c => c.start <= t);
    const cur = visible[visible.length - 1];
    return cur && t - cur.end < 6 * 3600e3 ? cur : null;
  }
  function pushClusters() {
    const visible = clusters.filter(c => c.start <= t), cur = currentCluster();
    clusters.forEach(c => clusterLabels.get(c.public_event_id)?.getElement().classList.toggle("hidden", c.start > t));
    const props = c => ({ order: c.order, label: c.label, detection_count: c.detection_count, id: c.public_event_id, current: c === cur, selected: selected === c.public_event_id });
    map.getSource("clusters")?.setData({ type: "FeatureCollection", features: visible.map(c => ({ type: "Feature", geometry: { type: "Point", coordinates: c.centroid }, properties: props(c) })) });
    map.getSource("columns")?.setData({ type: "FeatureCollection", features: colsOn && is3D ? visible.map(c => ({ type: "Feature", geometry: { type: "Polygon", coordinates: [circleRing(c.centroid, 70, 24)] }, properties: { ...props(c), height: c.max_frp_mw * FRP_M_PER_MW } })) : [] });
  }

  // ---------- Imagery ----------
  function applyImagery() {
    whenReady(() => {
      const sat = base === "sat";
      if (IMG.ctxPre) {
        map.setPaintProperty("ctxPre", "raster-opacity", sat ? 1 : 0);
        map.setPaintProperty("ctxPost", "raster-opacity", sat ? blend : 0);
      }
      map.setPaintProperty("detPre", "raster-opacity", sat ? 1 : 0);
      map.setPaintProperty("detPost", "raster-opacity", sat ? blend : 0);
      map.setPaintProperty("hillshade", "hillshade-exaggeration", sat ? 0.28 : 0.12);
      map.setPaintProperty("dnbr", "raster-opacity", 0.82 * scarK);
      map.setPaintProperty("outline", "raster-opacity", 0.95 * scarK);
      refreshTerrain();
    });
    document.querySelectorAll("[data-base]").forEach(b => b.setAttribute("aria-pressed", b.dataset.base === base));
    document.getElementById("blend").hidden = base !== "sat";
    document.getElementById("blend-input").value = Math.round(blend * 100);
    document.getElementById("btn-scar").setAttribute("aria-pressed", scarOn);
    document.getElementById("btn-cols").setAttribute("aria-pressed", colsOn);
  }
  document.querySelectorAll("[data-base]").forEach(b => b.onclick = () => { base = b.dataset.base; applyImagery(); });
  document.getElementById("blend-input").oninput = e => { blendGen++; blend = e.target.value / 100; applyImagery(); };
  document.getElementById("btn-cols").onclick = () => { colsOn = !colsOn; applyImagery(); pushClusters(); };
  let blendGen = 0, scarGen = 0, timeGen = 0;
  function animateBlend(to, ms) {
    const from = blend, t0 = performance.now(), gen = ++blendGen;
    return new Promise(res => {
      if (REDUCED || !ms) { blend = to; applyImagery(); return res(); }
      const step = now => {
        if (gen !== blendGen) return res();
        const k = Math.min(1, (now - t0) / ms); blend = from + (to - from) * ease(k); applyImagery(); k < 1 ? requestAnimationFrame(step) : res();
      };
      requestAnimationFrame(step);
    });
  }
  function setScar(on, ms = 700) {
    scarOn = on;
    const from = scarK, to = on ? 1 : 0, t0 = performance.now(), gen = ++scarGen;
    if (REDUCED || !ms) { scarK = to; applyImagery(); return; }
    const step = now => { if (gen !== scarGen) return; const k = Math.min(1, (now - t0) / ms); scarK = from + (to - from) * ease(k); applyImagery(); if (k < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  }
  document.getElementById("btn-scar").onclick = () => setScar(!scarOn);

  // ---------- Panel ----------
  const panel = document.getElementById("panel");
  const api = {};
  function renderCase() { panel.innerHTML = P.renderPanel(api); P.afterPanel?.(api); }
  function renderCluster(c) {
    panel.innerHTML = `<button class="back" id="back">← Volver al caso</button>` + P.renderCluster(c, api);
    document.getElementById("back").onclick = () => { selected = null; update(); renderCase(); };
  }

  // ---------- Timeline ----------
  const svg = document.getElementById("timeline");
  const NS = "http://www.w3.org/2000/svg";
  function el(tag, attrs, parent) { const n = document.createElementNS(NS, tag); for (const k in attrs) n.setAttribute(k, attrs[k]); parent.appendChild(n); return n; }
  let W = 0; const TH = 74, PADX = 8;
  const x = ms => PADX + (ms - P.viewStart) / (P.viewEnd - P.viewStart) * (W - 2 * PADX);
  const tAt = px => P.viewStart + (px - PADX) / (W - 2 * PADX) * (P.viewEnd - P.viewStart);
  function drawTimeline() {
    W = svg.clientWidth; svg.setAttribute("viewBox", `0 0 ${W} ${TH}`); svg.innerHTML = "";
    const firstMidnight = Math.floor((P.viewStart - TZ_OFFSET_H * 3600e3) / 86400e3) * 86400e3 + (-TZ_OFFSET_H) * 3600e3;
    for (let d = firstMidnight; d < P.viewEnd; d += 86400e3) {
      const a = Math.max(x(d - 6 * 3600e3), PADX), b = Math.min(x(d + 6 * 3600e3), W - PADX);
      if (b > a) el("rect", { x: a, y: 8, width: b - a, height: 40, fill: "#1a1917", opacity: 0.05 }, svg);
      if (x(d) < PADX) continue;
      el("line", { x1: x(d), x2: x(d), y1: 8, y2: 48, stroke: "#1a1917", "stroke-opacity": 0.18 }, svg);
      const dayPx = x(d + 86400e3) - x(d), dd = new Date(d + TZ_OFFSET_H * 3600e3), day = dd.getUTCDate();
      const every = dayPx < 14 ? 4 : dayPx < 22 ? 3 : dayPx < 40 ? 2 : 1;
      if (x(d) > PADX + 4 && x(d) < W - 24 && day % every === 0)
        el("text", { x: x(d) + 3, y: 62, "font-size": 10.5, fill: "#5b5d59" }, svg).textContent = dayPx < 46 ? `${day}` : `${day} ${MONTHS[dd.getUTCMonth()]}`;
    }
    el("line", { x1: PADX, x2: W - PADX, y1: 48, y2: 48, stroke: "#1a1917", "stroke-opacity": 0.35 }, svg);
    if (P.window) {
      const a = x(P.window[0]), b = x(P.window[1]);
      el("rect", { x: a, y: 8, width: b - a, height: 40, fill: "#477797", opacity: 0.12 }, svg);
      el("text", { x: (a + b) / 2, y: 18, "text-anchor": "middle", "font-size": 9.5, fill: "#2f5a76" }, svg).textContent = W < 500 ? "v1" : "ventana v1";
    }
    if (P.showGaps) clusters.forEach((c, i) => {
      if (!i) return;
      const p = clusters[i - 1], x1 = x(p.end) + 4, x2 = x(c.start) - 4;
      if (x2 - x1 < 26) return;
      el("line", { x1, x2, y1: 28, y2: 28, stroke: "#5b5d59", "stroke-dasharray": "1 4", "stroke-opacity": 0.7 }, svg);
      el("text", { x: (x1 + x2) / 2, y: 24, "text-anchor": "middle", "font-size": 10, fill: "#5b5d59" }, svg).textContent = x2 - x1 > 120 ? `${fmtNum(c.gap_from_previous_hours, 1)} h sin detección` : `${fmtNum(c.gap_from_previous_hours, 1)} h`;
    });
    clusters.forEach(c => {
      const x1 = x(c.start), wd = Math.max(5, x(c.end) - x1);
      const g = el("g", { style: "cursor:pointer" }, svg);
      el("rect", { x: x1 - 1, y: 30, width: wd + 2, height: 18, fill: c.start <= t ? "#c4572f" : "#d9cfc0", rx: 1 }, g);
      if (wd + 2 >= 14 || W > 600) el("text", { x: x1 + wd / 2, y: 44, "text-anchor": "middle", "font-size": 9.5, fill: c.start <= t ? "#fff" : "#5b5d59", "pointer-events": "none" }, g).textContent = c.short;
      g.addEventListener("click", ev => { ev.stopPropagation(); selectCluster(c, true); });
    });
    P.s2Marks.forEach(({ ms, label, blend: b }) => {
      const g = el("g", { style: "cursor:pointer" }, svg);
      el("path", { d: `M${x(ms)} 31 l6 6 l-6 6 l-6 -6 z`, fill: "#477797" }, g);
      el("text", { x: x(ms), y: 24, "text-anchor": "middle", "font-size": 10, fill: "#2f5a76" }, g).textContent = W < 500 ? "S2" : label;
      g.addEventListener("click", ev => { ev.stopPropagation(); base = "sat"; animateBlend(b, 900); });
    });
    el("line", { x1: x(t), x2: x(t), y1: 4, y2: 52, stroke: "#1a1917", "stroke-width": 1.6 }, svg);
    el("circle", { cx: x(t), cy: 4, r: 3.5, fill: "#1a1917" }, svg);
  }
  function setTime(ms) { t = Math.min(P.viewEnd, Math.max(P.viewStart, ms)); update(); }
  function update() {
    pushClusters();
    const seen = clusters.filter(c => c.start <= t);
    document.getElementById("tl-now").textContent = `${fmtLocal(t)} · ${fmtUTC(t)}`;
    document.getElementById("tl-sub").textContent = P.timelineSummary(seen, clusters, totalDetections);
    svg.setAttribute("aria-valuenow", Math.round((t - P.viewStart) / (P.viewEnd - P.viewStart) * 100));
    svg.setAttribute("aria-valuetext", fmtLocal(t));
    drawTimeline();
  }
  let dragging = false;
  svg.addEventListener("pointerdown", e => { dragging = true; svg.setPointerCapture(e.pointerId); setTime(tAt(e.offsetX)); });
  svg.addEventListener("pointermove", e => { if (dragging) setTime(tAt(e.offsetX)); });
  svg.addEventListener("pointerup", () => dragging = false);
  svg.addEventListener("keydown", e => {
    const step = (e.shiftKey ? 6 : 1) * 3600e3;
    if (e.key === "ArrowRight") { setTime(t + step); e.preventDefault(); }
    if (e.key === "ArrowLeft") { setTime(t - step); e.preventDefault(); }
  });
  window.addEventListener("resize", drawTimeline);

  const playBtn = document.getElementById("play");
  let last = 0;
  function tick(now) {
    if (!playing) return;
    const dt = last ? now - last : 0; last = now;
    setTime(t + dt * (P.viewEnd - P.viewStart) / 20000);
    if (t >= P.viewEnd) { setPlaying(false); return; }
    requestAnimationFrame(tick);
  }
  function setPlaying(on) {
    playing = on; if (on && t >= P.viewEnd) t = P.viewStart;
    playBtn.textContent = on ? "❚❚" : "▶"; playBtn.setAttribute("aria-label", on ? "Pausar" : "Reproducir");
    last = 0; if (on) requestAnimationFrame(tick);
  }
  playBtn.onclick = () => setPlaying(!playing);
  function animateTime(from, to, ms) {
    const t0 = performance.now(), gen = ++timeGen;
    return new Promise(res => {
      if (REDUCED) { setTime(to); return res(); }
      const step = now => {
        if (gen !== timeGen || !touring) return res();
        const k = Math.min(1, (now - t0) / ms); setTime(from + (to - from) * k); k < 1 ? requestAnimationFrame(step) : res();
      };
      requestAnimationFrame(step);
    });
  }

  // ---------- Pulse on the active cluster ----------
  let pulseOn = false;
  (function pulse(now) {
    if (pulseOn && !REDUCED && currentCluster() && map.getLayer("cluster-halo")) {
      const k = (now % 1600) / 1600;
      map.setPaintProperty("cluster-halo", "circle-radius", 10 + 26 * k);
      map.setPaintProperty("cluster-halo", "circle-opacity", 0.45 * (1 - k));
    }
    requestAnimationFrame(pulse);
  })(0);

  // ---------- Selection ----------
  function selectCluster(c, flyTo) {
    selected = c.public_event_id;
    if (t < c.start) t = c.end;
    update(); renderCluster(c);
    if (flyTo) map.easeTo({ center: c.centroid, zoom: Math.max(map.getZoom(), 13.4), duration: 1200 });
  }
  for (const layer of ["cluster-pt", "columns"]) {
    map.on("click", layer, e => selectCluster(clusters.find(c => c.public_event_id === e.features[0].properties.id), true));
    map.on("mouseenter", layer, () => map.getCanvas().style.cursor = "pointer");
    map.on("mouseleave", layer, () => map.getCanvas().style.cursor = "");
  }

  // ---------- Terrain readout: decode the real DEM tile under the cursor ----------
  const tileCache = new Map();
  function demTile(z, tx, ty) {
    const key = `${z}/${tx}/${ty}`;
    if (!tileCache.has(key)) tileCache.set(key, new Promise(res => {
      const img = new Image();
      img.onload = () => { const c = document.createElement("canvas"); c.width = c.height = 256; const ctx = c.getContext("2d", { willReadFrequently: true }); ctx.drawImage(img, 0, 0); res(ctx.getImageData(0, 0, 256, 256).data); };
      img.onerror = () => res(null);
      img.src = `tiles/dem/${key}.png`;
    }));
    return tileCache.get(key);
  }
  const elevAt = (d, px, py) => { const i = (Math.min(255, Math.max(0, py)) * 256 + Math.min(255, Math.max(0, px))) * 4; return d[i] * 256 + d[i + 1] + d[i + 2] / 256 - 32768; };
  const readout = document.getElementById("readout");
  let pending = 0;
  map.on("mousemove", async e => {
    const { lng, lat } = e.lngLat; const z = 12, n = 2 ** z;
    const fx = (lng + 180) / 360 * n, r = lat * Math.PI / 180;
    const fy = (1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2 * n;
    const tx = Math.floor(fx), ty = Math.floor(fy), px = Math.floor((fx - tx) * 256), py = Math.floor((fy - ty) * 256);
    const id = ++pending; const d = await demTile(z, tx, ty); if (id !== pending) return;
    if (!d || lng < aoiW || lng > aoiE || lat < aoiS || lat > aoiN) { readout.innerHTML = "Fuera del área de la prueba"; return; }
    const h = elevAt(d, px, py);
    const m = 40075016.686 * Math.cos(r) / n / 256;
    const dzdx = (elevAt(d, px + 1, py) - elevAt(d, px - 1, py)) / (2 * m);
    const dzdy = (elevAt(d, px, py - 1) - elevAt(d, px, py + 1)) / (2 * m);
    const slope = Math.atan(Math.hypot(dzdx, dzdy)) * 180 / Math.PI;
    const asp = (Math.atan2(-dzdx, -dzdy) * 180 / Math.PI + 360) % 360;
    const dirs = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"];
    readout.innerHTML = `<b>${fmtNum(h, 0)} m</b> DSM · pendiente <b>${fmtNum(slope, 0)}°</b> · orientada al ${dirs[Math.round(asp / 45) % 8]}<br>${lat.toFixed(5)}°, ${lng.toFixed(5)}°`;
  });

  // ---------- Camera ----------
  const fly = (v, duration = 3200) => new Promise(res => {
    map.once("moveend", res);
    map.flyTo({ ...v, pitch: is3D ? v.pitch : 0, bearing: is3D ? v.bearing : 0, duration: REDUCED ? 0 : duration, curve: 1.3, essential: true });
  });
  document.getElementById("btn-case").onclick = () => fly(P.views[P.startView], 2200);
  const btn3d = document.getElementById("btn-3d");
  btn3d.onclick = () => {
    is3D = !is3D; btn3d.setAttribute("aria-pressed", is3D);
    map.setTerrain(is3D ? { source: "dem", exaggeration: EXAGGERATION } : null);
    pushClusters();
    map.easeTo({ pitch: is3D ? 62 : 0, bearing: is3D ? map.getBearing() || -24 : 0, duration: 900 });
  };
  const btnOrbit = document.getElementById("btn-orbit");
  function orbit() { if (orbiting) map.rotateTo(map.getBearing() + 10, { duration: 3000, easing: x => x, around: P.orbitCenter }); }
  map.on("moveend", () => { if (orbiting) orbit(); });
  function setOrbit(on) { orbiting = on; btnOrbit.setAttribute("aria-pressed", on); on ? orbit() : map.stop(); }
  btnOrbit.onclick = () => setOrbit(!orbiting);
  map.on("dragstart", () => { if (orbiting) setOrbit(false); });

  // ---------- Guided tour ----------
  Object.assign(api, { setTime, animateTime, animateBlend, setScar, fly, views: P.views, clusters, totalDetections, get touring() { return touring; } });
  const story = document.getElementById("story");
  let chapter = 0, chapterGen = 0;
  function chapterApi(gen) {
    const live = () => gen === chapterGen && touring;
    const guard = fn => (...args) => live() ? fn(...args) : Promise.resolve();
    return { ...api, setTime: guard(setTime), animateTime: guard(animateTime), animateBlend: guard(animateBlend), setScar: guard(setScar), fly: guard(fly) };
  }
  const CH = P.chapters;
  const dots = document.getElementById("story-dots");
  dots.innerHTML = CH.map(() => "<span></span>").join("");
  async function goto(i) {
    chapter = Math.max(0, Math.min(CH.length - 1, i));
    const ch = CH[chapter];
    document.getElementById("story-eyebrow").textContent = `${chapter + 1} / ${CH.length} · ${ch.eyebrow}`;
    document.getElementById("story-title").textContent = ch.title;
    document.getElementById("story-body").innerHTML = typeof ch.body === "function" ? ch.body(api) : ch.body;
    [...dots.children].forEach((d, k) => d.classList.toggle("on", k <= chapter));
    document.getElementById("story-prev").disabled = chapter === 0;
    document.getElementById("story-next").textContent = chapter === CH.length - 1 ? "Explorar" : "Siguiente";
    const gen = ++chapterGen;
    blendGen++; scarGen++; timeGen++;
    setOrbit(false); setPlaying(false); map.stop();
    await ch.run(chapterApi(gen));
  }
  function startTour() { touring = true; document.body.classList.add("touring"); story.hidden = false; selected = null; renderCase(); goto(0); }
  function endTour() { touring = false; chapterGen++; blendGen++; scarGen++; timeGen++; map.stop(); document.body.classList.remove("touring"); story.hidden = true; }
  document.getElementById("tour-start").onclick = startTour;
  document.getElementById("story-exit").onclick = endTour;
  document.getElementById("story-prev").onclick = () => goto(chapter - 1);
  document.getElementById("story-next").onclick = () => chapter === CH.length - 1 ? endTour() : goto(chapter + 1);
  document.addEventListener("keydown", e => {
    if (!touring) return;
    if (e.key === "Escape") endTour();
    if (e.key === "ArrowRight" && e.target === document.body) goto(chapter + 1);
    if (e.key === "ArrowLeft" && e.target === document.body) goto(chapter - 1);
  });

  // ---------- Start ----------
  renderCase(); applyImagery(); update();
  map.once("load", async () => {
    update();
    await Promise.race([new Promise(r => map.once("idle", r)), sleep(6000)]);
    document.getElementById("loading").classList.add("done");
    document.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show");
    pulseOn = true;
    if (P.startScar) setScar(true, 900);
    if (!touring) fly(P.views[P.startView], 5200);
  });
  window.__firepa = { map, setTime, clusters, goto, startTour, endTour, set: o => { if ("blend" in o) blend = o.blend; if ("scar" in o) setScar(o.scar, 0); if ("base" in o) base = o.base; applyImagery(); } };
})();

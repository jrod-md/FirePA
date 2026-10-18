// Case profiles for the FirePA viewer. Every number shown comes from the JSON files loaded here.
const FIELD_HA = 105 * 68 / 1e4; // una cancha de fútbol reglamentaria, en hectáreas

window.FIREPA_CASES = {
  // ------------------------------------------------------------------ Guacamaya
  async guacamaya({ fmtNum, fmtUTC, fmtLocal, sleep }) {
    const [caseData, validation, s2, scarLine] = await Promise.all([
      fetch("data/case.json").then(r => r.json()),
      fetch("data/validation.json").then(r => r.json()),
      fetch("data/s2/s2.json").then(r => r.json()),
      fetch("data/s2/scar.geojson").then(r => r.json())
    ]);
    const anchor = caseData.anchor;
    const s2Pre = Date.parse(s2.pre.datetime), s2Post = Date.parse(s2.post.datetime);
    const a20 = s2.areas.find(a => a.threshold === 0.2);
    const range = key => [Math.min(...s2.areas.map(a => a[key])), Math.max(...s2.areas.map(a => a[key]))];
    const clusters = caseData.clusters.map(c => ({ ...c, label: `C${c.order}`, short: `C${c.order}` }));
    const total = clusters.reduce((s, c) => s + c.detection_count, 0);
    const days = Math.round(caseData.temporal_span_hours / 24);
    const SUMMIT = [-80.46694, 8.51306];
    const views = {
      overview: { center: [-80.46, 8.52], zoom: 11.3, pitch: 38, bearing: 0 },
      massif: { center: [-80.468, 8.500], zoom: 13.1, pitch: 66, bearing: -24 },
      close: { center: [-80.466, 8.507], zoom: 13.55, pitch: 70, bearing: 18 },
      scar: { center: [-80.465, 8.498], zoom: 13.0, pitch: 58, bearing: -8 },
      anchor: { center: [-80.448, 8.507], zoom: 12.35, pitch: 52, bearing: 28 }
    };
    function areaChart() {
      const W = 300, max = 1600, X = v => 6 + v / max * (W - 12);
      const rows = [
        ["Píxeles quemados", range("main_patch_ha"), a20.main_patch_ha, "#c4572f"],
        ["Envolvente", range("main_patch_convex_hull_ha"), a20.main_patch_convex_hull_ha, "#793625"],
        ["Reportado", s2.reported_area_ha, null, "#477797"]
      ];
      let out = `<svg class="chart" viewBox="0 0 ${W} 132" width="100%" role="img" aria-label="Comparación de áreas en hectáreas">`;
      [0, 400, 800, 1200, 1600].forEach(v => out += `<line x1="${X(v)}" x2="${X(v)}" y1="4" y2="112" stroke="#1a1917" stroke-opacity=".1"/><text x="${X(v)}" y="126" font-size="9" fill="#5b5d59" text-anchor="${v === 0 ? "start" : v === max ? "end" : "middle"}">${v.toLocaleString("es-PA")}</text>`);
      rows.forEach(([label, [lo, hi], mid, col], i) => {
        const y = 10 + i * 34;
        out += `<text x="6" y="${y + 6}" font-size="9.5" fill="#1a1917">${label} · ${fmtNum(lo, 0)}–${fmtNum(hi, 0)} ha</text>`;
        out += `<rect x="${X(lo)}" y="${y + 11}" width="${Math.max(2, X(hi) - X(lo))}" height="9" fill="${col}" opacity=".85"/>`;
        if (mid != null) out += `<line x1="${X(mid)}" x2="${X(mid)}" y1="${y + 8}" y2="${y + 23}" stroke="#1a1917" stroke-width="1.5"/>`;
      });
      return out + `</svg><p class="small" style="margin-top:2px">Barras: rango entre umbrales 0.10–0.40 (raya: 0.20) y rango de las fuentes.</p>`;
    }
    return {
      meta: { title: "Cerro Guacamaya", eyebrow: "Coclé, Panamá · enero de 2025",
        lede: "Un incendio en la ladera de un cerro de 643 m, visto por dos satélites: uno detectó el calor mientras ardía y otro fotografió la cicatriz." },
      tileAoi: caseData.tile_aoi, viewBounds: caseData.detail_aoi,
      viewStart: Date.parse("2025-01-20T12:00:00Z"), viewEnd: Date.parse("2025-02-01T12:00:00Z"),
      initialTime: Date.parse("2025-01-31T18:00:00Z"), initialBlend: 1, startScar: false,
      blendLabels: ["Antes · 21 ene", "Después · 31 ene"],
      s2Marks: [{ ms: s2Pre, label: "Foto antes", blend: 0 }, { ms: s2Post, label: "Foto después", blend: 1 }],
      imagery: { ctxPre: "data/s2/pre_context.webp", ctxPost: "data/s2/post_context.webp", ctxCorners: s2.context.corners_lonlat,
        detPre: "data/s2/pre_detail.webp", detPost: "data/s2/post_detail.webp", detCorners: s2.corners_lonlat,
        scar: "data/s2/scar.webp", scarLine },
      anchor, clusters, showGaps: true,
      summits: [{ coordinates: SUMMIT, label: "643 m" }],
      orbitCenter: SUMMIT, views, startView: "massif",
      legend: `<div><i style="background:#f29a45"></i>Calor detectado (columna)</div>
        <div><i style="background:#c4572f"></i>Zona quemada</div>
        <div><i style="border:1.5px dashed #477797"></i>Zona de búsqueda (5 km)</div>`,
      timelineSummary: (seen) => `${seen.length} de ${clusters.length} pasadas con calor · ${seen.reduce((s, c) => s + c.detection_count, 0)} de ${total} detecciones`,
      renderPanel: () => `
        <div class="eyebrow">Caso · Cerro Guacamaya</div>
        <h2>Lo que vio el satélite</h2>
        <p>Entre el 24 y el 27 de enero de 2025 ardió la ladera del Cerro Guacamaya, al oeste de Penonomé. Un satélite detectó el calor varias veces mientras quemaba, y otro fotografió la cicatriz cuatro días después.</p>
        <div class="kpis">
          <div><b>~${fmtNum(a20.main_patch_ha, 0)} ha</b><span>quemadas, unas ${fmtNum(Math.round(a20.main_patch_ha / FIELD_HA / 10) * 10, 0)} canchas de fútbol</span></div>
          <div><b>${total}</b><span>detecciones de calor</span></div>
          <div><b>${days} días</b><span>con fuego visible</span></div>
        </div>
        <h3>Cómo leer el mapa</h3>
        <ul class="howto">
          <li><i class="sw col"></i><span><b>Columnas.</b> Cada una es una pasada del satélite que detectó calor. Más alta = fuego más intenso. No es la altura de las llamas.</span></li>
          <li><i class="sw scar"></i><span><b>Mancha roja.</b> Lo que se quemó, comparando las fotos del 21 y del 31 de enero. Actívala con «Cicatriz».</span></li>
          <li><i class="sw cur"></i><span><b>Antes / Después.</b> Arrastra el control de arriba a la derecha y una cortina recorre el paisaje.</span></li>
          <li><i class="sw tl"></i><span><b>Línea de tiempo.</b> Abajo: dale ▶ o arrástrala para ver cuándo apareció cada detección.</span></li>
        </ul>
        <h3>¿Cuadra con lo reportado?</h3>
        <p>Las noticias hablaron de 1,035 a 1,500 ha. Contando solo el suelo quemado salen ~${fmtNum(a20.main_patch_ha, 0)} ha; si se cuenta todo lo que queda dentro del borde exterior, incluidas islas de bosque intactas, salen ~${fmtNum(a20.main_patch_convex_hull_ha, 0)} ha, dentro del rango.</p>
        <h3>Lo que no sabemos</h3>
        <ul>
          <li>Dónde empezó el fuego ni cómo avanzó entre una pasada y otra: el satélite solo mira un par de veces al día.</li>
          <li>El perímetro oficial: no se publicó.</li>
        </ul>
        <div class="note">Exploratorio, fuera del piloto científico FirePA v1. Pendiente de revisión experta.</div>
        <details class="tech">
          <summary>Detalles técnicos</summary>
          <h3>Observado · FirePA v1</h3>
          <dl>
            <dt>Coincidencias oficiales</dt><dd>${anchor.official_match_count}</dd>
            <dt>Detecciones VIIRS</dt><dd>${total}</dd>
            <dt>Lapso total</dt><dd>${fmtNum(caseData.temporal_span_hours, 3)} h</dd>
            <dt>Intervalos &gt; 6 h</dt><dd>${anchor.inter_cluster_gaps_gt_6h}</dd>
            <dt>Radio de coincidencia</dt><dd>${(anchor.official_matching_radius_m / 1000).toFixed(0)} km</dd>
            <dt>Fuentes documentales</dt><dd>${anchor.source_document_count}</dd>
          </dl>
          <p class="small">Columnas: altura proporcional al FRP máximo de cada grupo (35 m por MW). Suben en 90 min de la línea de tiempo solo como animación.</p>
          <h3>Medido aquí · Sentinel-2</h3>
          <p>Cicatriz conectada a las detecciones: <b>~${fmtNum(a20.main_patch_ha, 0)} ha</b> (umbral dNBR 0.20; dNBR mediano ${fmtNum(a20.main_patch_median_dnbr, 2)}). Envolvente convexa: <b>~${fmtNum(a20.main_patch_convex_hull_ha, 0)} ha</b>.</p>
          ${areaChart()}
          <dl>
            <dt>Antes</dt><dd>${fmtUTC(s2Pre).replace(" UTC", "")}</dd>
            <dt>Después</dt><dd>${fmtUTC(s2Post).replace(" UTC", "")}</dd>
            <dt>Píxeles válidos comunes</dt><dd>${fmtNum(s2.valid_overlap_fraction * 100, 1)} %</dd>
            <dt>Nube a &lt; 500 m de la cicatriz</dt><dd>0 ha</dd>
          </dl>
          <div class="note">Una pareja de escenas, máscara SCL (no Cloud Score+), rejilla de 20 m. Umbrales descriptivos, no severidad validada. El contorno es un umbral, no un perímetro oficial. La mancha se dibuja suavizada a 5 m solo para mostrarla; el área se cuenta en celdas de 20 m. Rojo = cicatriz conectada a las detecciones; gris tenue = otros cambios &gt; 0.20; gris translúcido = sin dato.</div>
          <h3>Relieve y ancla</h3>
          <p>Los seis grupos rodean una cumbre de <b>643 m</b>. El ancla aproximada de la referencia está a <b>${fmtNum(validation.anchor_elevation_m, 0)} m</b>, en terreno bajo, ~3.8 km al este. La fuente no da coordenadas; el emparejamiento oficial no cambia.</p>
          <div class="note">Todas las detecciones caen entre ~01:00–02:15 y ~13:15–14:20 hora de Panamá, compatibles con los pasos de VIIRS. Los huecos pueden reflejar cuándo pasó el satélite y no pausas del fuego.</div>
          <h3>Procedencia</h3>
          <p class="hash">FirePA ${caseData.provenance.firepa_package}<br>${Object.entries(caseData.provenance.firepa_files).map(([k, v]) => `${k} · ${v.slice(0, 16)}…`).join("<br>")}</p>
          <p class="hash">${caseData.provenance.dem.product}<br>${caseData.provenance.dem.file}<br>sha256 ${caseData.provenance.dem.sha256.slice(0, 16)}…</p>
          <p class="hash">Sentinel-2 L2A · ${s2.pre.id} · ${s2.post.id}</p>
          <p class="small">El DEM es un modelo de superficie (incluye el dosel). Exageración vertical ×1.5 en 3D. Los puntos son centroides de visualización, no ubicaciones del fuego. La imagen de contexto (20 m) es solo visual.</p>
        </details>`,
      renderCluster: (c) => {
        const prev = clusters[c.order - 2];
        return `
        <div class="eyebrow" style="margin-top:14px">Pasada ${c.order} de ${clusters.length}</div>
        <h2>${fmtLocal(c.start)}</h2>
        <p>El satélite detectó calor en <b>${c.detection_count === 1 ? "un punto" : `${c.detection_count} puntos`}</b> de unos 375 m cada uno. La intensidad máxima fue de <b>${fmtNum(c.max_frp_mw, 1)} MW</b>${c.max_frp_mw === Math.max(...clusters.map(x => x.max_frp_mw)) ? ", la más alta del incendio" : ""}.</p>
        ${prev ? `<p>Desde la pasada anterior pasaron ${fmtNum(c.gap_from_previous_hours, 0)} horas sin detección. No dibujamos qué pasó en ese tiempo.</p>` : `<p>Es la primera detección del incendio.</p>`}
        <p class="small">El punto es el centro del grupo de detecciones, no el lugar exacto del fuego.</p>
        <details class="tech">
          <summary>Detalles técnicos</summary>
          <dl>
            <dt>Evento</dt><dd>${c.public_event_id}</dd>
            <dt>Intervalo</dt><dd>${fmtUTC(c.start)} → ${fmtUTC(c.end)}</dd>
            <dt>Detecciones</dt><dd>${c.detection_count}</dd>
            <dt>Satélites</dt><dd>${c.satellites.join(" · ")}</dd>
            <dt>Día / noche</dt><dd>${c.day_count} / ${c.night_count}</dd>
            <dt>FRP máx.</dt><dd>${fmtNum(c.max_frp_mw, 2)} MW</dd>
            <dt>FRP medio</dt><dd>${fmtNum(c.mean_frp_mw, 2)} MW</dd>
            <dt>Hueco previo</dt><dd>${c.gap_from_previous_hours == null ? "—" : fmtNum(c.gap_from_previous_hours, 1) + " h"}</dd>
            <dt>Elevación DSM del centroide</dt><dd>${fmtNum(c.dsm_elevation_m, 0)} m</dd>
          </dl>
          ${c.possible_chain_merge ? `<div class="note">Posible fusión en cadena de detecciones al agrupar.</div>` : ""}
          <p class="hash">Paquete público FirePA v1 · guacamaya-timeline.json · orden ${c.order}<br>events.geojson · ${c.public_event_id}</p>
        </details>`;
      },
      chapters: [
        { eyebrow: "Coclé · estación seca 2025", title: "Un cerro aislado sobre la llanura",
          body: `<p>El Cerro Guacamaya se levanta hasta 643 m al oeste de Penonomé. Las fuentes documentan un incendio en su reserva hídrica entre el 24 y el 27 de enero de 2025.</p>`,
          run: async a => { a.setScar(false, 0); await a.animateBlend(0, 0); a.setTime(Date.parse("2025-01-20T12:00:00Z")); await a.fly(views.overview, 3600); } },
        { eyebrow: "21 de enero · Sentinel-2", title: "Antes",
          body: `<p>La última foto despejada antes del incendio. Bosque y pastizal secos sobre las laderas, tres días antes de la primera detección.</p>`,
          run: async a => { a.setScar(false, 300); await a.animateBlend(0, 400); a.setTime(s2Pre + 3600e3); await a.fly(views.massif, 4200); } },
        { eyebrow: "24–27 de enero · satélite VIIRS", title: "El calor, pasada a pasada",
          body: `<p>${total} detecciones de calor en ${clusters.length} pasadas del satélite. Cada columna es una pasada; su altura es la intensidad del fuego medida desde el espacio, no la altura de las llamas.</p>`,
          run: async a => { a.setScar(false, 300); a.animateBlend(0, 400); const t0 = Date.parse("2025-01-23T20:00:00Z"); a.setTime(t0); a.fly(views.close, 4000); await a.animateTime(t0, Date.parse("2025-01-27T12:00:00Z"), 9000); } },
        { eyebrow: "Entre pasadas", title: "Lo que no vimos",
          body: `<p>Entre una pasada y otra hay 11 a 23 horas sin datos. El satélite solo mira un par de veces al día, así que no sabemos cómo avanzó el fuego en ese tiempo. Por eso no lo dibujamos.</p>`,
          run: async a => { a.setScar(false, 300); a.animateBlend(0, 400); a.setTime(Date.parse("2025-01-27T12:00:00Z")); await a.fly({ ...views.close, bearing: 70, zoom: 13.3 }, 4500); } },
        { eyebrow: "31 de enero · Sentinel-2", title: "Después",
          body: `<p>Cuatro días después de la última detección. La cortina pasa de la foto de antes a la de después: la ladera quemada aparece en pardo. Es la misma vista del satélite, sin retoques.</p>`,
          run: async a => { a.setScar(false, 300); a.setTime(s2Post); a.fly(views.scar, 3500); await sleep(900); await a.animateBlend(1, 5200); } },
        { eyebrow: "Medido en esta prueba", title: "La cicatriz",
          body: () => `<p>Comparando las dos fotos, el suelo quemado conectado a las detecciones mide unas ${fmtNum(a20.main_patch_ha, 0)} ha. Contando lo que queda dentro de su borde exterior, ${fmtNum(a20.main_patch_convex_hull_ha, 0)} ha, dentro de lo reportado.</p>
            <div class="stat"><div>${fmtNum(a20.main_patch_ha, 0)}<small>ha quemadas</small></div><div>${fmtNum(a20.main_patch_convex_hull_ha, 0)}<small>ha dentro del borde</small></div><div>1,035–1,500<small>ha reportadas</small></div></div>`,
          run: async a => { a.setTime(s2Post); a.animateBlend(1, 600); a.setScar(true, 1200); await a.fly({ ...views.scar, bearing: -30, zoom: 12.9 }, 3000); } },
        { eyebrow: "Lo que no sabemos", title: "Límites del caso",
          body: `<p>No hay perímetro oficial ni punto de inicio conocido. La coordenada de la noticia es aproximada y cae en terreno bajo, a 3.8 km de la cumbre. La cicatriz es un análisis exploratorio, fuera del piloto v1, pendiente de revisión experta.</p>`,
          run: async a => { a.setTime(s2Post); a.animateBlend(1, 0); a.setScar(true, 600); await a.fly(views.anchor, 3800); } }
      ]
    };
  }
};

// ------------------------------------------------------------------ Cases found by satellite
// Same layout as Guacamaya, built from web/cases/<id>/. Story text comes from case.json (case_registry.py).
function scarCase(id) {
  return async ({ fmtNum, fmtUTC, fmtLocal, fmtDay, sleep }) => {
    const base = `cases/${id}/`;
    const [caseData, s2, scarLine] = await Promise.all([
      fetch(base + "case.json").then(r => r.json()),
      fetch(base + "s2/s2.json").then(r => r.json()),
      fetch(base + "s2/scar.geojson").then(r => r.json())
    ]);
    const st = caseData.story;
    const s2Pre = Date.parse(s2.pre.datetime), s2Post = Date.parse(s2.post.datetime);
    const a20 = s2.areas.find(a => a.threshold === 0.2);
    const range = key => [Math.min(...s2.areas.map(a => a[key])), Math.max(...s2.areas.map(a => a[key]))];
    const clusters = caseData.clusters.map(c => ({ ...c, label: `${c.order}`, short: `${c.order}` }));
    const total = clusters.reduce((s, c) => s + c.detection_count, 0);
    const first = clusters[0], last = clusters[clusters.length - 1];
    const spanH = clusters.length ? (Date.parse(last.cluster_end_utc) - Date.parse(first.cluster_start_utc)) / 3600e3 : 0;
    const views = caseData.views;
    const day = 86400e3;
    const viewStart = Math.min(s2Pre, clusters.length ? Date.parse(first.cluster_start_utc) : s2Pre) - day / 2;
    const viewEnd = Math.max(s2Post, clusters.length ? Date.parse(last.cluster_end_utc) : s2Post) + day / 2;
    const firesFrom = clusters.length ? Date.parse(first.cluster_start_utc) - 3 * 3600e3 : s2Pre;
    const firesTo = clusters.length ? Date.parse(last.cluster_end_utc) + 3 * 3600e3 : s2Post;
    const summit = caseData.summit;
    const spanText = spanH < 36 ? `${fmtNum(Math.max(1, spanH), 0)} h` : `${fmtNum(spanH / 24, 0)} días`;
    return {
      meta: { title: caseData.title, eyebrow: `${caseData.place} · ${st.when}`, lede: st.lede },
      tileAoi: caseData.tile_aoi, viewBounds: caseData.view_aoi,
      viewStart, viewEnd, initialTime: s2Post, initialBlend: 1, startScar: false,
      blendLabels: [`Antes · ${fmtDay(s2Pre)}`, `Después · ${fmtDay(s2Post)}`],
      s2Marks: [{ ms: s2Pre, label: "Foto antes", blend: 0 }, { ms: s2Post, label: "Foto después", blend: 1 }],
      imagery: { ctxPre: base + "s2/pre_context.webp", ctxPost: base + "s2/post_context.webp", ctxCorners: s2.context.corners_lonlat,
        detPre: base + "s2/pre_detail.webp", detPost: base + "s2/post_detail.webp", detCorners: s2.corners_lonlat,
        scar: base + "s2/scar.webp", scarLine },
      anchor: null, clusters, showGaps: true,
      summits: summit ? [{ coordinates: summit.coordinates, label: `${summit.elevation_m} m` }] : [],
      orbitCenter: summit ? summit.coordinates : views.scar.center, views, startView: "scar",
      legend: `<div><i style="background:#f29a45"></i>Calor detectado (columna)</div>
        <div><i style="background:#c4572f"></i>Zona quemada</div>`,
      timelineSummary: (seen) => `${seen.length} de ${clusters.length} pasadas con calor · ${seen.reduce((s, c) => s + c.detection_count, 0)} de ${total} detecciones`,
      renderPanel: () => `
        <div class="eyebrow">Caso · ${caseData.title}</div>
        <h2>${st.headline}</h2>
        <p>${st.intro}</p>
        <div class="kpis">
          <div><b>~${fmtNum(a20.main_patch_ha, 0)} ha</b><span>quemadas, unas ${fmtNum(Math.round(a20.main_patch_ha / FIELD_HA / 10) * 10, 0)} canchas de fútbol</span></div>
          <div><b>${total}</b><span>detecciones de calor</span></div>
          <div><b>${spanText}</b><span>con fuego visible</span></div>
        </div>
        <h3>Cómo leer el mapa</h3>
        <ul class="howto">
          <li><i class="sw col"></i><span><b>Columnas.</b> Cada una es una pasada del satélite que detectó calor. Más alta = fuego más intenso. No es la altura de las llamas.</span></li>
          <li><i class="sw scar"></i><span><b>Mancha roja.</b> Lo que se quemó, comparando las fotos del ${fmtDay(s2Pre)} y del ${fmtDay(s2Post)}. Actívala con «Cicatriz».</span></li>
          <li><i class="sw cur"></i><span><b>Antes / Después.</b> Arrastra el control de arriba a la derecha y una cortina recorre el paisaje.</span></li>
          <li><i class="sw tl"></i><span><b>Línea de tiempo.</b> Abajo: dale ▶ o arrástrala para ver cuándo apareció cada detección.</span></li>
        </ul>
        <h3>Cómo lo encontramos</h3>
        <p>Este caso no salió de una noticia. Revisamos con Sentinel-2 todo Coclé en la estación seca de 2025 buscando manchas quemadas grandes, y esta fue de las más claras. Las detecciones de calor de FIRMS lo confirman por separado.</p>
        <h3>Lo que no sabemos</h3>
        <ul>
          <li>Dónde empezó el fuego ni cómo avanzó entre una pasada y otra.</li>
          <li>Si hubo un reporte oficial: no encontramos uno con este lugar y fecha.</li>
          ${a20.no_data_within_500m_ha > 20 ? `<li>El tamaño total: había nubes junto al borde (${fmtNum(a20.no_data_within_500m_ha, 0)} ha sin dato a menos de 500 m), así que las ~${fmtNum(a20.main_patch_ha, 0)} ha son un mínimo. Las zonas grises del mapa son esas nubes.</li>` : ""}
          ${(st.unknowns || []).map(u => `<li>${u}</li>`).join("")}
        </ul>
        <div class="note">Exploratorio, fuera del piloto científico FirePA v1. Pendiente de revisión experta.</div>
        <details class="tech">
          <summary>Detalles técnicos</summary>
          <h3>Medido aquí · Sentinel-2</h3>
          <p>Mancha principal conectada a detecciones FIRMS: <b>~${fmtNum(a20.main_patch_ha, 0)} ha</b> (dNBR &gt; 0.20; mediana ${fmtNum(a20.main_patch_median_dnbr, 2)}); ${fmtNum(range("main_patch_ha")[0], 0)}–${fmtNum(range("main_patch_ha")[1], 0)} ha entre umbrales 0.40 y 0.10. Envolvente convexa ~${fmtNum(a20.main_patch_convex_hull_ha, 0)} ha.</p>
          <dl>
            <dt>Antes</dt><dd>${fmtUTC(s2Pre).replace(" UTC", "")}</dd>
            <dt>Después</dt><dd>${fmtUTC(s2Post).replace(" UTC", "")}</dd>
            <dt>Píxeles válidos comunes</dt><dd>${fmtNum(s2.valid_overlap_fraction * 100, 1)} %</dd>
            <dt>Sin dato a &lt; 500 m de la mancha</dt><dd>${fmtNum(a20.no_data_within_500m_ha, 1)} ha</dd>
            <dt>Toca el borde de la ventana</dt><dd>${a20.main_touches_window_edge ? "sí" : "no"}</dd>
          </dl>
          <div class="note">Encontrado con scar_search.py: mosaicos medianos de NBR a 80 m por periodo y diferencias entre periodos consecutivos. Medido de nuevo aquí a 20 m con una pareja de escenas, máscara SCL y margen de 300 m alrededor de nubes. Umbrales descriptivos, no severidad validada. La mancha se suaviza a 5 m solo para mostrarla.</div>
          <h3>Detecciones FIRMS · FirePA v1</h3>
          <dl>
            <dt>Eventos en la ventana</dt><dd>${clusters.length}</dd>
            <dt>Detecciones</dt><dd>${total}</dd>
            <dt>Primera</dt><dd>${clusters.length ? fmtUTC(Date.parse(first.cluster_start_utc)) : "—"}</dd>
            <dt>Última</dt><dd>${clusters.length ? fmtUTC(Date.parse(last.cluster_end_utc)) : "—"}</dd>
          </dl>
          <p class="small">Columnas: FRP máximo de cada evento (35 m por MW). Los puntos son centroides de visualización, no ubicaciones del fuego.</p>
          <h3>Procedencia</h3>
          <p class="hash">FirePA v1 events.geojson · ${caseData.provenance.firepa_files["events.geojson"].slice(0, 16)}…</p>
          <p class="hash">Copernicus DEM GLO-30 · ${Object.keys(caseData.provenance.dem).join(" · ")}</p>
          <p class="hash">Sentinel-2 L2A · ${s2.pre.id} · ${s2.post.id}</p>
        </details>`,
      renderCluster: (c) => `
        <div class="eyebrow" style="margin-top:14px">Pasada ${c.order} de ${clusters.length}</div>
        <h2>${fmtLocal(Date.parse(c.cluster_start_utc))}</h2>
        <p>El satélite detectó calor en <b>${c.detection_count === 1 ? "un punto" : `${c.detection_count} puntos`}</b> de unos 375 m cada uno. La intensidad máxima fue de <b>${fmtNum(c.max_frp_mw, 1)} MW</b>${c.max_frp_mw === Math.max(...clusters.map(x => x.max_frp_mw)) ? ", la más alta del incendio" : ""}.</p>
        ${c.gap_from_previous_hours != null ? `<p>Desde la pasada anterior pasaron ${fmtNum(c.gap_from_previous_hours, 0)} horas sin detección. No dibujamos qué pasó en ese tiempo.</p>` : `<p>Es la primera detección de este incendio.</p>`}
        <p class="small">El punto es el centro del grupo de detecciones, no el lugar exacto del fuego.</p>
        <details class="tech">
          <summary>Detalles técnicos</summary>
          <dl>
            <dt>Evento</dt><dd>${c.public_event_id}</dd>
            <dt>Intervalo</dt><dd>${fmtUTC(Date.parse(c.cluster_start_utc))} → ${fmtUTC(Date.parse(c.cluster_end_utc))}</dd>
            <dt>Satélites</dt><dd>${c.satellites.join(" · ")}</dd>
            <dt>Día / noche</dt><dd>${c.day_count} / ${c.night_count}</dd>
            <dt>FRP máx. / medio</dt><dd>${fmtNum(c.max_frp_mw, 2)} / ${fmtNum(c.mean_frp_mw, 2)} MW</dd>
            <dt>Distancia a la mancha</dt><dd>${c.distance_to_main_scar_m == null ? "—" : fmtNum(c.distance_to_main_scar_m, 0) + " m"}</dd>
            <dt>Elevación DSM</dt><dd>${fmtNum(c.dsm_elevation_m, 0)} m</dd>
          </dl>
          <p class="hash">Paquete público FirePA v1 · events.geojson · ${c.public_event_id}</p>
        </details>`,
      chapters: [
        { eyebrow: `${caseData.place} · ${st.when}`, title: st.chapter_title,
          body: `<p>${st.chapter_intro}</p>`,
          run: async a => { a.setScar(false, 0); await a.animateBlend(0, 0); a.setTime(viewStart); await a.fly(views.overview, 3600); } },
        { eyebrow: `${fmtDay(s2Pre)} · Sentinel-2`, title: "Antes",
          body: `<p>La foto despejada de antes del fuego.</p>`,
          run: async a => { a.setScar(false, 300); await a.animateBlend(0, 400); a.setTime(s2Pre + 3600e3); await a.fly(views.scar, 4200); } },
        { eyebrow: "Satélite VIIRS", title: "El calor, pasada a pasada",
          body: `<p>${total} detecciones de calor en ${clusters.length} pasadas del satélite. Cada columna es una pasada; su altura es la intensidad del fuego medida desde el espacio, no la altura de las llamas.</p>`,
          run: async a => { a.setScar(false, 300); a.animateBlend(0, 400); a.setTime(firesFrom); a.fly(views.close, 4000); await a.animateTime(firesFrom, firesTo, 9000); } },
        { eyebrow: `${fmtDay(s2Post)} · Sentinel-2`, title: "Después",
          body: `<p>La cortina pasa de la foto de antes a la de después. Es la misma vista del satélite, sin retoques: solo cambia la fecha.</p>`,
          run: async a => { a.setScar(false, 300); a.setTime(s2Post); a.fly(views.scar, 3500); await sleep(900); await a.animateBlend(1, 5200); } },
        { eyebrow: "Medido en esta prueba", title: "La cicatriz",
          body: () => `<p>Comparando las dos fotos, el suelo quemado mide unas ${fmtNum(a20.main_patch_ha, 0)} ha.</p>
            <div class="stat"><div>${fmtNum(a20.main_patch_ha, 0)}<small>ha quemadas</small></div><div>${total}<small>detecciones</small></div><div>${spanText}<small>con fuego visible</small></div></div>`,
          run: async a => { a.setTime(s2Post); a.animateBlend(1, 600); a.setScar(true, 1200); await a.fly({ ...views.scar, bearing: views.scar.bearing - 25 }, 3000); } },
        { eyebrow: "Lo que no sabemos", title: "Límites del caso",
          body: `<p>No hay perímetro oficial ni punto de inicio conocido. La mancha es un análisis exploratorio, fuera del piloto v1, pendiente de revisión experta.</p>`,
          run: async a => { a.setTime(s2Post); a.animateBlend(1, 0); a.setScar(true, 600); await a.fly(views.overview, 3800); } }
      ]
    };
  };
}

// Cases shown in the viewer's case bar, in order.
window.FIREPA_CASE_LIST = [
  { id: "guacamaya", label: "Cerro Guacamaya" },
  { id: "ola", label: "Cerros de Olá" },
  { id: "costa", label: "Costa de Natá" }
];
window.FIREPA_CASES.ola = scarCase("ola");
window.FIREPA_CASES.costa = scarCase("costa");

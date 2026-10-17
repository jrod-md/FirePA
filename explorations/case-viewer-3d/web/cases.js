// Case profiles for the FirePA viewer. Every number shown comes from the JSON files loaded here.
window.FIREPA_CASES = {
  // ------------------------------------------------------------------ Guacamaya
  async guacamaya({ fmtNum, fmtUTC, fmtLocal, sleep }) {
    const [caseData, validation, s2] = await Promise.all([
      fetch("data/case.json").then(r => r.json()),
      fetch("data/validation.json").then(r => r.json()),
      fetch("data/s2/s2.json").then(r => r.json())
    ]);
    const anchor = caseData.anchor;
    const s2Pre = Date.parse(s2.pre.datetime), s2Post = Date.parse(s2.post.datetime);
    const a20 = s2.areas.find(a => a.threshold === 0.2);
    const range = key => [Math.min(...s2.areas.map(a => a[key])), Math.max(...s2.areas.map(a => a[key]))];
    const clusters = caseData.clusters.map(c => ({ ...c, label: `C${c.order}`, short: `C${c.order}` }));
    const total = clusters.reduce((s, c) => s + c.detection_count, 0);
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
      meta: { title: "Cerro Guacamaya", eyebrow: "FirePA · Coclé, Panamá · Referencia externa 2",
        lede: "Detecciones térmicas VIIRS (NASA FIRMS) y la cicatriz que dejaron, vistas por Sentinel-2 sobre relieve real del Copernicus DEM." },
      tileAoi: caseData.tile_aoi || caseData.aoi,
      viewStart: Date.parse("2025-01-20T12:00:00Z"), viewEnd: Date.parse("2025-02-01T12:00:00Z"),
      initialTime: Date.parse("2025-01-31T18:00:00Z"), initialBlend: 1, startScar: false,
      blendLabels: ["21 ene", "31 ene"],
      s2Marks: [{ ms: s2Pre, label: "S2 antes", blend: 0 }, { ms: s2Post, label: "S2 después", blend: 1 }],
      imagery: { ctxPre: "data/s2/pre_context.webp", ctxPost: "data/s2/post_context.webp", ctxCorners: s2.context.corners_lonlat,
        detPre: "data/s2/pre_detail.webp", detPost: "data/s2/post_detail.webp", detCorners: s2.corners_lonlat,
        dnbr: "data/s2/dnbr.png", outline: "data/s2/outline.png" },
      anchor, clusters, showGaps: true,
      summits: [{ coordinates: SUMMIT, label: "643 m" }],
      orbitCenter: SUMMIT, views, startView: "massif",
      legend: `<div><i style="background:#c4572f;border-radius:50%"></i>Grupo de detecciones VIIRS</div>
        <div><i style="background:#f2b45c"></i>Columna: FRP máximo</div>
        <div><i style="background:#8c2a1c"></i>Cicatriz dNBR conectada</div>
        <div><i style="border:1.5px dashed #477797"></i>Radio oficial de coincidencia</div>`,
      timelineSummary: (seen) => `${seen.length} de ${clusters.length} grupos · ${seen.reduce((s, c) => s + c.detection_count, 0)} de ${total} detecciones hasta este momento`,
      renderPanel: () => `
        <div class="eyebrow">Caso · ${anchor.reference_name}</div>
        <h2>Lo que vio el satélite</h2>
        <p>${clusters.length} grupos FirePA con ${total} detecciones VIIRS en ${fmtNum(caseData.temporal_span_hours, 1)} h, y la cicatriz que Sentinel-2 registró cuatro días después.</p>
        <div><span class="tag obs">Observado</span><span class="tag mes">Medido aquí</span><span class="tag ctx">Contexto</span><span class="tag unk">Desconocido</span></div>
        <h3>Observado · FirePA v1</h3>
        <dl>
          <dt>Coincidencias oficiales</dt><dd>${anchor.official_match_count}</dd>
          <dt>Detecciones VIIRS</dt><dd>${total}</dd>
          <dt>Lapso total</dt><dd>${fmtNum(caseData.temporal_span_hours, 3)} h</dd>
          <dt>Intervalos &gt; 6 h</dt><dd>${anchor.inter_cluster_gaps_gt_6h}</dd>
          <dt>Radio de coincidencia</dt><dd>${(anchor.official_matching_radius_m / 1000).toFixed(0)} km</dd>
          <dt>Fuentes documentales</dt><dd>${anchor.source_document_count}</dd>
        </dl>
        <p class="small">Columnas: altura proporcional al FRP máximo de cada grupo (35 m por MW). Codifican un dato, no representan llamas.</p>
        <h3>Medido aquí · Sentinel-2</h3>
        <p>La cicatriz mide <b>~${fmtNum(a20.main_patch_ha, 0)} ha</b> (umbral dNBR 0.20; dNBR mediano ${fmtNum(a20.main_patch_median_dnbr, 2)}). Su envolvente exterior mide <b>~${fmtNum(a20.main_patch_convex_hull_ha, 0)} ha</b>, dentro del rango reportado.</p>
        ${areaChart()}
        <p style="font-size:12.5px">Una explicación posible: las cifras reportadas describen el área dentro del perímetro, incluidas islas de bosque sin quemar. No está verificado.</p>
        <dl>
          <dt>Antes</dt><dd>${fmtUTC(s2Pre).replace(" UTC", "")}</dd>
          <dt>Después</dt><dd>${fmtUTC(s2Post).replace(" UTC", "")}</dd>
          <dt>Píxeles válidos comunes</dt><dd>${fmtNum(s2.valid_overlap_fraction * 100, 1)} %</dd>
          <dt>Nube a &lt; 500 m de la cicatriz</dt><dd>0 ha</dd>
        </dl>
        <div class="note">Exploratorio, fuera de v1. Una pareja de escenas, máscara SCL (no Cloud Score+), rejilla de 20 m. Umbrales descriptivos, no severidad validada. El contorno es un umbral, no un perímetro oficial. En el mapa: rojo = cicatriz conectada a las detecciones; gris tenue = otros cambios &gt; 0.20; gris translúcido = sin dato.</div>
        <h3>Contexto · relieve</h3>
        <p>Los seis grupos rodean una cumbre de <b>643 m</b>. El ancla aproximada de la referencia está a <b>${fmtNum(validation.anchor_elevation_m, 0)} m</b>, en terreno bajo, ~3.8 km al este.</p>
        <div class="note">Hallazgo de esta prueba, no resultado v1: el ancla es aproximada (la fuente no da coordenadas). El relieve sugiere revisarla; el emparejamiento oficial no cambia.</div>
        <h3>Desconocido</h3>
        <ul>
          <li>Perímetro oficial: no existe.</li>
          <li>Lugar y hora de ignición: no conocidos.</li>
          <li>Cómo avanzó el fuego entre pasos del satélite: no observado; los huecos no se rellenan.</li>
          <li>Sentinel-2 en v1: el caso no entró en la cohorte óptica; lo de arriba es nuevo y no revisado.</li>
        </ul>
        <div class="note">Todas las detecciones caen entre ~01:00–02:15 y ~13:15–14:20 hora de Panamá, compatibles con los pasos de VIIRS. Los huecos pueden reflejar cuándo pasó el satélite y no pausas del fuego. Requiere validación.</div>
        <h3>Procedencia</h3>
        <p class="hash">FirePA ${caseData.provenance.firepa_package}<br>${Object.entries(caseData.provenance.firepa_files).map(([k, v]) => `${k} · ${v.slice(0, 16)}…`).join("<br>")}</p>
        <p class="hash">${caseData.provenance.dem.product}<br>${caseData.provenance.dem.file}<br>sha256 ${caseData.provenance.dem.sha256.slice(0, 16)}…</p>
        <p class="hash">Sentinel-2 L2A · ${s2.pre.id} · ${s2.post.id}</p>
        <p class="small">El DEM es un modelo de superficie (incluye el dosel). Exageración vertical ×1.5 en 3D. Los puntos son centroides de visualización, no ubicaciones del fuego. La imagen de contexto (20 m) es solo visual.</p>`,
      renderCluster: (c) => {
        const prev = clusters[c.order - 2];
        return `
        <div class="eyebrow" style="margin-top:14px">Grupo C${c.order} de ${clusters.length} · ${c.public_event_id}</div>
        <h2>${fmtLocal(c.start)}</h2>
        <p style="margin:2px 0 0;color:var(--slate);font-size:12.5px">${fmtUTC(c.start)} → ${fmtUTC(c.end)}</p>
        <div style="margin-top:10px"><span class="tag obs">Observado</span>${c.possible_chain_merge ? '<span class="tag unk">Posible fusión en cadena</span>' : ""}</div>
        <dl>
          <dt>Detecciones</dt><dd>${c.detection_count}</dd>
          <dt>Satélites</dt><dd>${c.satellites.join(" · ")}</dd>
          <dt>Día / noche</dt><dd>${c.day_count} / ${c.night_count}</dd>
          <dt>FRP máx.</dt><dd>${fmtNum(c.max_frp_mw, 2)} MW</dd>
          <dt>FRP medio</dt><dd>${fmtNum(c.mean_frp_mw, 2)} MW</dd>
          <dt>Hueco previo</dt><dd>${c.gap_from_previous_hours == null ? "—" : fmtNum(c.gap_from_previous_hours, 1) + " h"}</dd>
          <dt>Elevación DSM del centroide</dt><dd>${fmtNum(c.dsm_elevation_m, 0)} m</dd>
        </dl>
        ${prev ? `<div class="note">Entre C${prev.order} y C${c.order} no hay detecciones registradas durante ${fmtNum(c.gap_from_previous_hours, 1)} h. El mapa no dibuja nada en ese intervalo.</div>` : ""}
        <h3>Qué significa el punto</h3>
        <p>Es el centroide de ${c.detection_count === 1 ? "una detección" : `${c.detection_count} detecciones`} de ~375 m. No es el borde ni el centro del fuego.</p>
        <h3>Fuente</h3>
        <p class="hash">site-data/guacamaya-timeline.json · orden ${c.order}<br>site-data/events.geojson · ${c.public_event_id}</p>`;
      },
      chapters: [
        { eyebrow: "Coclé · estación seca 2025", title: "Un cerro aislado sobre la llanura",
          body: `<p>El Cerro Guacamaya se levanta hasta 643 m al oeste de Penonomé. Las fuentes documentan un incendio en su reserva hídrica entre el 24 y el 27 de enero de 2025.</p>`,
          run: async a => { a.setScar(false, 0); await a.animateBlend(0, 0); a.setTime(Date.parse("2025-01-20T12:00:00Z")); await a.fly(views.overview, 3600); } },
        { eyebrow: "21 de enero · Sentinel-2", title: "Antes",
          body: `<p>La última imagen despejada antes del incendio. Bosque y pastizal secos sobre las laderas, tres días antes de la primera detección.</p>`,
          run: async a => { a.setScar(false, 300); await a.animateBlend(0, 400); a.setTime(s2Pre + 3600e3); await a.fly(views.massif, 4200); } },
        { eyebrow: "24–27 de enero · VIIRS", title: "Lo que detectó el satélite",
          body: `<p>${total} detecciones en ${clusters.length} pasos del satélite. Cada columna es un grupo; su altura es la potencia radiativa máxima medida (FRP), no la altura de las llamas.</p>`,
          run: async a => { a.setScar(false, 300); a.animateBlend(0, 400); const t0 = Date.parse("2025-01-23T20:00:00Z"); a.setTime(t0); a.fly(views.close, 4000); await a.animateTime(t0, Date.parse("2025-01-27T12:00:00Z"), 9000); } },
        { eyebrow: "Entre detecciones", title: "Los huecos no se rellenan",
          body: `<p>Entre un paso y otro pasan 11 a 23 horas sin detección. Las horas coinciden con los pasos de VIIRS: el hueco puede significar que el satélite no estaba mirando. Por eso no dibujamos cómo avanzó el fuego.</p>`,
          run: async a => { a.setScar(false, 300); a.animateBlend(0, 400); a.setTime(Date.parse("2025-01-27T12:00:00Z")); await a.fly({ ...views.close, bearing: 70, zoom: 13.3 }, 4500); } },
        { eyebrow: "31 de enero · Sentinel-2", title: "Después",
          body: `<p>Cuatro días después de la última detección, la ladera quemada aparece en color pardo. Es la misma escena del satélite, sin retoques: solo cambia la fecha.</p>`,
          run: async a => { a.setScar(false, 300); a.setTime(s2Post); a.fly(views.scar, 3500); await sleep(900); await a.animateBlend(1, 2800); } },
        { eyebrow: "Medido en esta prueba", title: "La cicatriz",
          body: () => `<p>Comparando ambas fechas (dNBR), la mancha quemada conectada a las detecciones mide unas ${fmtNum(a20.main_patch_ha, 0)} ha. Su envolvente exterior, ${fmtNum(a20.main_patch_convex_hull_ha, 0)} ha, cae dentro de lo reportado.</p>
            <div class="stat"><div>${fmtNum(a20.main_patch_ha, 0)}<small>ha quemadas</small></div><div>${fmtNum(a20.main_patch_convex_hull_ha, 0)}<small>ha envolvente</small></div><div>1,035–1,500<small>ha reportadas</small></div></div>`,
          run: async a => { a.setTime(s2Post); a.animateBlend(1, 600); a.setScar(true, 1200); await a.fly({ ...views.scar, bearing: -30, zoom: 12.9 }, 3000); } },
        { eyebrow: "Lo que no sabemos", title: "Límites del caso",
          body: `<p>No hay perímetro oficial ni punto de ignición. La coordenada de referencia es aproximada y cae en terreno bajo, a 3.8 km de la cumbre. La cicatriz es un análisis exploratorio, fuera del piloto v1, pendiente de revisión experta.</p>`,
          run: async a => { a.setTime(s2Post); a.animateBlend(1, 0); a.setScar(true, 600); await a.fly(views.anchor, 3800); } }
      ]
    };
  },

  // ------------------------------------------------------------------ Los Picachos
  async picachos({ fmtNum, fmtUTC, fmtLocal, fmtDay, sleep }) {
    const [caseData, s2] = await Promise.all([
      fetch("cases/picachos/case.json").then(r => r.json()),
      fetch("cases/picachos/s2/s2.json").then(r => r.json())
    ]);
    const anchor = caseData.anchor;
    const preDates = s2.candidates.pre.map(p => Date.parse(p.datetime));
    const s2Pre = preDates[0], s2Post = Date.parse(s2.post.datetime);
    const clusters = caseData.nearby_events.map(e => ({ ...e, label: `${(e.distance_to_anchor_m / 1000).toFixed(1)} km`, short: `${e.order}` }));
    const total = clusters.reduce((s, c) => s + c.detection_count, 0);
    const linked = s2.patches.find(p => p.rank === s2.firms_linked_patch_rank);
    const signal = clusters.find(c => c.public_event_id === "evt-0418");
    const sw = s2.patches.filter(p => p.centroid[0] < -80.67 && p.centroid[1] < 8.38);
    const swHa = sw.reduce((s, p) => s + p.area_ha, 0);
    const s20 = s2.sensitivity.find(x => x.threshold === 0.2);
    const views = {
      overview: { center: [-80.635, 8.425], zoom: 11.45, pitch: 42, bearing: 8 },
      anchor: { center: [-80.655, 8.41], zoom: 12.9, pitch: 60, bearing: -20 },
      signal: { center: [-80.581, 8.478], zoom: 13.6, pitch: 62, bearing: 20 },
      sw: { center: [-80.688, 8.358], zoom: 13.2, pitch: 60, bearing: -35 },
      wide: { center: [-80.64, 8.43], zoom: 11.9, pitch: 55, bearing: -10 }
    };
    const pre = s2.candidates.pre;
    const row = p => `<tr class="${p.rank === s2.firms_linked_patch_rank ? "hl" : ""}"><td>#${p.rank}</td><td>${fmtNum(p.area_ha, 1)}</td><td>${fmtNum(p.median_dnbr, 2)}</td><td>${fmtNum(p.min_distance_to_anchor_m / 1000, 1)}</td><td>${fmtNum(p.distance_centroid_to_firms_signal_m / 1000, 1)}</td><td>${Object.entries(p.pre_date_fraction).filter(([, v]) => v > 0.5).map(([k]) => `${+k.slice(6)}/${+k.slice(4, 6)}`).join("") || "mixto"}</td></tr>`;
    return {
      meta: { title: "Cerro Los Picachos", eyebrow: "FirePA · Olá, Coclé · Referencia externa 1",
        lede: "Un incendio reportado el 16 de enero de 2025 sin detección FIRMS a menos de 5 km. ¿Qué puede ver Sentinel-2, y qué no?" },
      tileAoi: [-80.76, 8.32, -80.30, 8.66],
      viewStart: Date.parse("2025-01-05T12:00:00Z"), viewEnd: Date.parse("2025-01-31T12:00:00Z"),
      window: [Date.parse(anchor.official_window_start + "T00:00:00Z"), Date.parse(anchor.official_window_end + "T00:00:00Z") + 86400e3],
      initialTime: s2Post, initialBlend: 1, startScar: true,
      blendLabels: ["antes", "21 ene"],
      s2Marks: [{ ms: preDates[1], label: "S2 6 ene", blend: 0 }, { ms: s2Pre, label: "S2 11 ene", blend: 0 }, { ms: s2Post, label: "S2 21 ene", blend: 1 }],
      imagery: { detPre: "cases/picachos/s2/pre_detail.webp", detPost: "cases/picachos/s2/post_detail.webp", detCorners: s2.corners_lonlat,
        dnbr: "cases/picachos/s2/dnbr.png", outline: "cases/picachos/s2/outline.png" },
      anchor, clusters, showGaps: false,
      summits: caseData.summits_near_anchor.slice(0, 1).map(s => ({ coordinates: s.coordinates, label: `${s.elevation_m} m` })),
      orbitCenter: anchor.coordinates, views, startView: "wide",
      legend: `<div><i style="background:#c4572f;border-radius:50%"></i>Evento FIRMS cercano (no coincidente)</div>
        <div><i style="background:#8c2a1c"></i>Mancha dNBR candidata ≥ 5 ha</div>
        <div><i style="border:2px solid #1a1917"></i>Mancha junto a la señal FIRMS</div>
        <div><i style="background:rgba(128,128,128,.6)"></i>Sin dato (nube o sombra)</div>
        <div><i style="border:1.5px dashed #477797"></i>Radio oficial de 5 km</div>`,
      timelineSummary: (seen) => `${seen.length} de ${clusters.length} eventos FIRMS cercanos hasta este momento · ninguno dentro de 5 km en la ventana oficial`,
      renderPanel: () => `
        <div class="eyebrow">Caso · ${anchor.reference_name}</div>
        <h2>Un reporte sin señal cercana</h2>
        <p>TVN informó un incendio el 16 de enero de 2025 en el Cerro Los Picachos de Olá, cerca de Loma Chata, sin cifra de hectáreas. FirePA v1 no encontró detecciones FIRMS dentro de 5 km en la ventana oficial.</p>
        <div><span class="tag obs">Observado</span><span class="tag mes">Medido aquí</span><span class="tag unk">Desconocido</span></div>
        <h3>Observado · FirePA v1</h3>
        <dl>
          <dt>Ventana oficial</dt><dd>${anchor.official_window_start.slice(5)} → ${anchor.official_window_end.slice(5)}</dd>
          <dt>Radio</dt><dd>${anchor.official_matching_radius_m / 1000} km</dd>
          <dt>Coincidencias oficiales</dt><dd>${anchor.official_match_count}</dd>
          <dt>Señal contemporánea más cercana</dt><dd>${fmtNum(anchor.nearest_documented_contemporary_signal_m, 0)} m</dd>
          <dt>Diagnóstico</dt><dd>${anchor.diagnostic}</dd>
        </dl>
        <p class="small">El cero oficial no cambia aquí. Los eventos del mapa son eventos FirePA v1 a menos de 15 km entre el 5 y el 31 de enero, mostrados como contexto, no como coincidencias.</p>
        <h3>Medido aquí · Sentinel-2</h3>
        <p><b>Lo robusto:</b> la señal FIRMS del 15 de enero (${fmtNum(anchor.nearest_documented_contemporary_signal_m / 1000, 1)} km del ancla) coincide con una quema nueva de <b>~${fmtNum(linked.area_ha, 0)} ha</b> a ${linked.distance_centroid_to_firms_signal_m} m, aparecida entre el 11 y el 21 de enero.</p>
        <p><b>Lo que no se puede ver:</b> con nubes, sombras y un margen de 300 m, solo hay dato válido en el <b>${fmtNum(s2.valid_fraction_within_5km * 100, 0)} %</b> de la zona de 5 km alrededor del ancla.</p>
        <table class="patches">
          <thead><tr><th>Mancha</th><th>ha</th><th>dNBR</th><th>km ancla</th><th>km señal</th><th>antes</th></tr></thead>
          <tbody>${s2.patches.slice(0, 8).map(row).join("")}</tbody>
        </table>
        <p class="small">Manchas dNBR &gt; 0.20 de al menos 5 ha. "Antes" indica la escena previa usada en cada mancha (día/mes).</p>
        <dl>
          <dt>Antes (mosaico)</dt><dd>${pre.map(p => `${fmtDay(Date.parse(p.datetime))} ${fmtNum(p.pixels_used_fraction * 100, 0)} %`).join(" · ")}</dd>
          <dt>Después</dt><dd>${fmtUTC(s2Post).replace(" UTC", "")}</dd>
          <dt>Válido en la ventana</dt><dd>${fmtNum(s2.valid_overlap_fraction * 100, 1)} %</dd>
          <dt>dNBR &gt; 0.20 a ≤ 5 km</dt><dd>${fmtNum(s20.within_5km_of_anchor_ha, 1)} ha</dd>
        </dl>
        <div class="note">Exploratorio, fuera de v1. El "antes" es un mosaico píxel a píxel (11 ene, si no 6 ene, si no 22 dic), así que una mancha puede incluir quemas desde el 22 de diciembre donde se usaron escenas viejas. Sin el margen de 300 m aparecían manchas junto al ancla que resultaron ser bordes de nube.</div>
        <h3>Desconocido</h3>
        <ul>
          <li>Dónde fue exactamente el incendio reportado: la fuente no da coordenadas y el ancla está en el pueblo de Olá (${fmtNum(anchor.anchor_dsm_elevation_m, 0)} m).</li>
          <li>Si la quema de ~${fmtNum(swHa, 0)} ha al suroeste (7–8 km) tiene relación con el reporte.</li>
          <li>Qué hay bajo las nubes cerca del ancla.</li>
        </ul>
        <h3>Fuente</h3>
        <p class="hash">${caseData.source.map(s => `${s.publisher} · ${s.publication_date} · <a href="${s.url}" target="_blank" rel="noopener">enlace</a>`).join("<br>")}</p>
        <p class="hash">FirePA ${Object.entries(caseData.provenance.firepa_files).map(([k, v]) => `${k} · ${v.slice(0, 16)}…`).join("<br>")}</p>
        <p class="hash">Sentinel-2 L2A · ${pre.map(p => p.id).join(" · ")} · ${s2.post.id}</p>`,
      renderCluster: (c) => `
        <div class="eyebrow" style="margin-top:14px">Evento FIRMS cercano · ${c.public_event_id}</div>
        <h2>${fmtLocal(c.start)}</h2>
        <p style="margin:2px 0 0;color:var(--slate);font-size:12.5px">${fmtUTC(c.start)} → ${fmtUTC(c.end)}</p>
        <div style="margin-top:10px"><span class="tag obs">Observado</span><span class="tag unk">No coincidente</span></div>
        <dl>
          <dt>Distancia al ancla</dt><dd>${fmtNum(c.distance_to_anchor_m / 1000, 2)} km</dd>
          <dt>En la ventana oficial</dt><dd>${c.in_official_window ? "sí" : "no"}</dd>
          <dt>Detecciones</dt><dd>${c.detection_count}</dd>
          <dt>Satélites</dt><dd>${c.satellites.join(" · ")}</dd>
          <dt>FRP máx.</dt><dd>${fmtNum(c.max_frp_mw, 2)} MW</dd>
          <dt>Elevación DSM</dt><dd>${fmtNum(c.dsm_elevation_m, 0)} m</dd>
        </dl>
        ${c.public_event_id === "evt-0418" ? `<div class="note">Sentinel-2 muestra una quema nueva de ~${fmtNum(linked.area_ha, 0)} ha a ${linked.distance_centroid_to_firms_signal_m} m de este punto, aparecida entre el 11 y el 21 de enero.</div>` : ""}
        ${c.start > s2Post ? `<div class="note">Es posterior a la imagen del 21 de enero, así que la comparación Sentinel-2 no puede verlo.</div>` : ""}
        <h3>Fuente</h3>
        <p class="hash">site-data/events.geojson · ${c.public_event_id}</p>`,
      chapters: [
        { eyebrow: "Olá · 16 de enero de 2025", title: "Un incendio reportado",
          body: `<p>TVN informó un incendio en el Cerro Los Picachos de Olá, cerca de la comunidad de Loma Chata. No dio hectáreas ni coordenadas.</p><p>El punto azul es el ancla aproximada que usa FirePA: cae en el pueblo de Olá, a ${fmtNum(anchor.anchor_dsm_elevation_m, 0)} m.</p>`,
          run: async a => { a.setScar(false, 0); await a.animateBlend(0, 0); a.setTime(Date.parse("2025-01-16T12:00:00Z")); await a.fly(views.anchor, 3800); } },
        { eyebrow: "FirePA v1", title: "Cero coincidencias",
          body: `<p>Ninguna detección FIRMS cae dentro de 5 km entre el 15 y el 17 de enero. La más cercana está a ${fmtNum(anchor.nearest_documented_contemporary_signal_m / 1000, 1)} km, el 15 de enero. Por eso v1 registra un cero, sin concluir que no hubo fuego.</p>`,
          run: async a => { a.setScar(false, 300); a.animateBlend(0, 300); a.setTime(Date.parse("2025-01-17T23:00:00Z")); await a.fly(views.overview, 4200); } },
        { eyebrow: "Sentinel-2", title: "Antes y después",
          body: `<p>El "antes" combina el 11 y el 6 de enero, porque ninguna escena estaba despejada entera. El "después" es del 21 de enero, cinco días tras el reporte.</p>`,
          run: async a => { a.setScar(false, 300); a.setTime(s2Post); a.fly(views.wide, 3500); await sleep(800); await a.animateBlend(1, 2800); } },
        { eyebrow: "Límites de la imagen", title: "Lo que no se puede ver",
          body: `<p>Las zonas grises no tienen dato: nubes, sus sombras o un margen de 300 m alrededor. Cubren el ${fmtNum(100 - s2.valid_fraction_within_5km * 100, 0)} % del círculo de 5 km. Sin ese margen aparecían falsas quemas junto al ancla.</p>`,
          run: async a => { a.setTime(s2Post); a.animateBlend(1, 300); a.setScar(true, 900); await a.fly(views.anchor, 3600); } },
        { eyebrow: "La señal del 15 de enero", title: "La señal de 10 km era real",
          body: `<p>Donde FIRMS detectó calor el 15 de enero aparece una quema nueva de unas ${fmtNum(linked.area_ha, 0)} ha, a ${linked.distance_centroid_to_firms_signal_m} m del punto. No sabemos si es el mismo incendio del reporte.</p>`,
          run: async a => { a.setTime(Date.parse("2025-01-21T18:00:00Z")); a.animateBlend(1, 300); a.setScar(true, 300); await a.fly(views.signal, 4000); } },
        { eyebrow: "Otras quemas", title: "Al suroeste, sin vínculo",
          body: `<p>A 7–8 km al suroeste del ancla aparecen unas ${fmtNum(swHa, 0)} ha quemadas entre el 6 y el 21 de enero, sin detección FIRMS. El intervalo incluye el 16, pero nada las vincula al reporte.</p>`,
          run: async a => { a.setTime(s2Post); a.animateBlend(1, 300); a.setScar(true, 300); await a.fly(views.sw, 4000); } },
        { eyebrow: "Conclusión", title: "Un caso abierto",
          body: `<p>Sentinel-2 ni confirma ni descarta el incendio de Los Picachos: las nubes tapan la zona clave. El cero de v1 se mantiene. Para avanzar haría falta ubicar el cerro con precisión y buscar una escena posterior más despejada.</p>`,
          run: async a => { a.setTime(s2Post); a.animateBlend(1, 0); a.setScar(true, 0); await a.fly(views.overview, 3800); } }
      ]
    };
  }
};

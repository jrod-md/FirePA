# FirePA visual QA — P3 public research slice

This document includes the current composition refinement pass. The latest captures were made against the built preview at the requested desktop sizes with a controlled local browser viewport.

## Source visual truth

- `REF_A_HERO_EMBER_LEDGER.png.png` — hero / opening art direction, 1448 × 1086 px.
- `REF_B_SIGNAL_TO_EVENT.png.png` — Chapter 01 / pipeline art direction, 1448 × 1086 px.
- The references were used as visual direction only. Scientific claims, counts, and cartography come from the repository freeze and `site-data/`.
- The P3 continuation preserves the approved Hero + Chapter 01 composition and adds only the contracted public chapters, companion routes, and static reading interactions.

## Implementation evidence

- `qa-desktop-hero.png` — desktop hero capture, 1425 × 990 px from a requested 1440 × 1000 CSS viewport, top-of-page state.
- `qa-desktop-chapter-01.png` — desktop Chapter 01 opening capture, 1425 × 990 px from a requested 1440 × 1000 CSS viewport, chapter heading plus initial pipeline state.
- `qa-mobile-hero.png` — mobile hero capture, 375 × 811 px from a requested 390 × 844 CSS viewport, top-of-page state.
- `qa-mobile-chapter-01.png` — mobile Chapter 01 opening capture, 375 × 811 px from a requested 390 × 844 CSS viewport, chapter heading plus pipeline context.
- `qa-refine-hero-1440x900.png` — refined desktop hero, requested 1440 × 900 CSS viewport, captured 1425 × 891 px.
- `qa-refine-hero-1600x1000.png` — refined desktop hero, requested 1600 × 1000 CSS viewport, captured 1585 × 991 px.
- `qa-refine-burn-half-1440x900.png` — burn overlay at approximately halfway through its active scroll interval, captured 1425 × 891 px.
- `qa-refine-chapter-initial-1440x900.png` — Chapter 01 top state with pipeline numbers entering the first viewport, captured 1425 × 891 px.
- `qa-refine-pipeline-final-1440x900.png` — final pipeline emphasis state with all three numbers and the scope note visible, captured 1425 × 891 px.
- `qa-refine-mobile-hero-390x844.png` — responsive top-of-page check after desktop refinement, captured 375 × 811 px.
- `qa-refine-mobile-chapter-390x844.png` — responsive Chapter 01 check after desktop refinement, captured 375 × 811 px.
- `qa-final-hero-1440x900.png` — current hero at 1440 × 900.
- `qa-final-hero-1440x1000.png` — current hero at 1440 × 1000.
- `qa-final-hero-1600x1000.png` — current hero at 1600 × 1000.
- `qa-final-burn-25-1440x900.png`, `qa-final-burn-50-1440x900.png`, and `qa-final-burn-75-1440x900.png` — current erosion edge at 25%, 50%, and 75% of the active interval.
- `qa-final-chapter-initial-1440x900.png` — current Chapter 01 introduction and first pipeline viewport.
- `qa-final-pipeline-final-1440x900.png` — current final pipeline state with `data-active="2"`, all fields, and the scope note visible.

The in-app browser capture excludes its scrollbar and browser-edge pixels, so the implementation PNGs are smaller than the requested CSS viewport. No source/implementation pixel diff was used; comparison was normalized to the visible content region, layout proportions, typography, and state.

## Findings

- No P0 or P1 findings remain.
- [P2 — fixed] The permanent black separator was removed. The carbonized edge is now a fixed overlay with no layout height, visible only during a short hero-to-Chapter 01 scroll interval and disabled under reduced motion.
- [P2 — fixed] Chapter 01 no longer has a large dead zone. The pipeline enters the first desktop Chapter 01 viewport and the sticky composition now remains within its section because the clipping mode no longer blocks sticky positioning.
- [P2 — fixed] Inactive pipeline stages retain contrast, and the final state keeps `1,532`, `1,185`, and `611` visually legible together.
- [P2 — fixed] The Coclé SVG now uses a single crisp high-fidelity presentation path, `shape-rendering: geometricPrecision`, and `vector-effect: non-scaling-stroke`; the fuzzy duplicate echo was removed.
- [P2 — fixed] Chapter 01 title wrapped as `From signal` / `to event` on desktop because of an artificial `max-width`. REF_B treats the heading as one editorial mass. The desktop title now remains one line; the mobile breakpoint intentionally restores a readable stacked treatment.
- [P2 — fixed] The burn overlay is now an open stroke rather than a filled black SVG region. The controlled 1440 × 900 checks recorded active states at scroll positions 397, 523, and 649, then `data-active="false"` at the Chapter 01 boundary; no layout height is contributed.
- [P2 — fixed] The desktop FirePA wordmark was reduced approximately 10–12% through the desktop type clamp, while the research question retains the three-line protagonist treatment and the Coclé label remains anchored to the real boundary geometry.
- [P2 — fixed] Deterministic surface micro-noise was increased only slightly, and the reduction fields now use stronger clay/ink contrast and slightly larger authored marks so dense → reduced → grouped reads without geographic encoding.
- [P3 — intentional] The reference hero contains a richer authored topographic surface and permanent charred lower edge. The implementation uses the real Coclé boundary, restrained deterministic paper noise, and a transient burn overlay because no approved topographic source exists and the requested initial state must remain clean.
- [P3 — intentional] The reference particle fields are denser and more materially textured. The implementation keeps the marks conceptual and non-geographic, with explicit text explaining that they are not one mark per actual observation.

## Required fidelity surfaces

- Fonts and typography: self-hosted Source Serif 4, IBM Plex Sans, and IBM Plex Mono; dramatic serif display scale and mono metadata are preserved across desktop and mobile.
- Spacing and layout rhythm: 12-column desktop frame, generous outer margins, non-card composition, single responsive column on mobile, a compact first-view pipeline, and one short sticky sequence.
- Colors and tokens: warm paper, ink, slate, oxidized clay, hairlines, deterministic 1–3% texture; no alarm-red or heat-intensity scale.
- Image quality and asset fidelity: no invented raster assets; the hero map is a higher-fidelity build-time SVG derived from the approved boundary; the burn is an authored vector overlay; abstract fields are explicitly labeled as conceptual and non-geographic.
- Copy/content: exact public values `1,532`, `1,185`, `611`, `r1500_t06`, study area, study window, and provisional-event wording are present as readable DOM text.

## Interaction and accessibility checks

- Desktop scroll states were observed as discrete `0 → 1 → 2` pipeline emphasis states; final numbers remain visible and are not count-up animations. The final state was observed with all panels in-frame and `data-active="2"`.
- The burn state was observed as `data-active="false"` at load, active at the 25% / 50% / 75% checkpoints, and `false` again at Chapter 01; it remains `position: fixed` and contributes no layout height.
- The page has a skip link, semantic landmarks/headings, visible focus CSS, accessible SVG title/description, and explanatory text adjacent to conceptual visuals.
- `prefers-reduced-motion` removes the sticky/animated enhancement path and preserves the static composition; the CSS/JS contract is present in the built output.
- Mobile check at 390 × 844 retained the stacked reading order, first number visibility, skip link, and accessible SVG naming. Browser console check: no page errors or warnings were reported.

## Comparison history

1. Initial desktop comparison identified the hero question wrapping into five lines and a too-subtle/offset cartographic treatment. The question was widened to the intended three-line editorial structure and the real boundary was tuned for low-contrast legibility.
2. Initial Chapter 01 comparison identified the desktop title wrapping into two lines and a large dead zone before the pipeline. The desktop title became one line, the pipeline was pulled into the first viewport, and the blocked sticky positioning was corrected.
3. The permanent burn band was replaced by a scroll-only overlay and checked at an intermediate scroll state plus the clean initial and post-transition states.
4. Desktop captures at 1440 × 900, 1440 × 1000, and 1600 × 1000, including burn states at 25% / 50% / 75%, were reviewed against both references. The remaining material differences are documented as intentional constraints above.

## P3 continuation evidence

- `qa-p3-hero-1440x900.png`, `qa-p3-hero-1440x1000.png`, and `qa-p3-hero-1600x1000.png` — regression checks for the preserved Hero at the three primary desktop sizes.
- `qa-p3-burn-25-1440x900.png`, `qa-p3-burn-50-1440x900.png`, and `qa-p3-burn-75-1440x900.png` — transient erosion checkpoints. Each shows only the thin charcoal/amber active edge over the hero → Chapter 01 crossing; no permanent black region or layout height appears.
- `qa-p3-chapter01-intro-1440x900.png` and `qa-p3-pipeline-final-1440x900.png` — Chapter 01 regression and final pipeline state.
- `qa-p3-chapter02-map-opening-1440x900.png` and `qa-p3-chapter02-map-1440x1000.png` — Chapter 02 opening with the real Coclé derivative, 611 public points, approximate anchors, and 5 km matching-rule rings.
- `qa-p3-event-selected-1440x900.png` and `qa-p3-event-selected-detail-1440x900.png` — keyboard/clickable map selection and a real selected public event (`evt-0078`) with descriptive fields.
- `qa-p3-chapter03-optical-1440x900.png` — `611 → 30 → 28 + 2` optical cohort composition.
- `qa-p3-guacamaya-1440x900.png` — six matches, six separate provisional clusters, `72.733 h`, and five gaps above six hours.
- `qa-p3-picachos-1440x900.png` and `qa-p3-picachos-diagnostic-detail-1440x900.png` — `0` matches at `5,000 m`, `10,400.826 m` nearest documented contemporary signal, and `SPATIAL_THRESHOLD_MISS`.
- `qa-p3-limits-1440x900.png` and `qa-p3-inspect-1440x900.png` — Chapter 05 limits and Chapter 06 package/provenance reading surfaces.
- `qa-p3-methodology-1440x900.png` and `qa-p3-sources-1440x900.png` — companion route openings without horizontal overflow after the long registry hash wrap fix.
- `qa-p3-mobile-map-390x844.png` — mobile smoke check for the Chapter 02 reading order and map surface.

## P3 findings

- [P3 — implemented] Chapter 02 now uses the 611 public WGS84 centroid records, the real Coclé geometry derivative, deterministic extents derived from all event points, and no map library, raster viewer, heatmap, perimeter, or severity encoding.
- [P3 — implemented] Chapter 03 keeps the optical evidence descriptive and communicates `30` cohort events, `28` observable cases, and `2` unobserved cases with `selected_pair` and `window_median` semantics.
- [P3 — implemented] Chapter 04 preserves the exact Guacamaya and Los Picachos public-reference claims, including six separate clusters, `72.733 h`, five gaps, zero official Picachos matches, `5,000 m`, `10,400.826 m`, and `SPATIAL_THRESHOLD_MISS`.
- [P3 — implemented] Chapters 05 and 06 are typographic evidence/limitation surfaces. `/methodology` and `/sources` expose the actual public package metadata, citations, provenance, manifest and frozen figure records.
- [P3 — implemented] All six public figures are copied into the site without recompression or redraw. The contract test verifies their six SHA-256 hashes after build.
- [P3 — intentional] Motion remains restrained. No new cinematic motion, parallax, count-up, map flight, or looping effect was added. The only active behaviors are local event selection, table filtering, the existing pipeline emphasis, and the existing erosion edge.

## P3 validation

- `npm.cmd run build` — passed; three static routes generated.
- `npm.cmd test` — passed; routes, public values, forbidden-output scan, and six frozen figure hashes verified.
- `npm.cmd exec tsc -- --noEmit` — passed under the existing strict TypeScript configuration.
- `scripts/verify_public_release_package.py` — passed; 611 events and 2 references verified.
- `tests/test_public_release.py` — passed 11/11; one existing Windows pytest cache-permission warning only.
- Full `pytest` collection (306 tests) was attempted but stopped after a pre-existing Windows native access violation in `tests/test_blind_ai_calibration.py` while `src/fuegopa/dnbr_quicklook_v2.py` was reading the scientific bundle; the focused public-release suite remained green.
- Runtime reduced-motion check — `prefers-reduced-motion: reduce` matched, burn computed `display: none`, and pipeline sticky enhancement resolved to normal flow.

## Final result

passed

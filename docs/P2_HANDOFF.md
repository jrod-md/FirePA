# FirePA P2 — Handoff

**Result:** P2 PASS — information architecture, visual direction, and content blueprint are defined for later implementation review.

**Date:** 2026-08-10

**Starting HEAD:** `144b459 fix: harden P1 public release verification`

**Scientific freeze:** `7694da7df5808911de48de84016759c5fd22f176`

## What P2 decided

### Experience model

The selected model is a **focused hybrid**: one primary long-form research story, supported by dedicated `/methodology` and `/sources` surfaces, with Guacamaya and Los Picachos treated as anchored case-study sections rather than disconnected marketing pages.

The thesis is:

> FirePA makes a local FIRMS-to-optical-to-reference workflow inspectable, while keeping provisional detections, descriptive measurements, and unresolved limitations visibly separate from confirmed-fire or severity claims.

### Sitemap

- `/` — research story: opening, study frame, evidence chain, grouping, map, optical cohort, Guacamaya, Los Picachos, limits, and close.
- `/methodology` — frozen workflow, configuration, public schema, package boundary, deferrals, and reproducibility route.
- `/sources` — citations, provenance, manifest, figure records, and public package metadata.

The cases are deep-linked sections in the primary story so the reader keeps the method context while moving from the overall evidence chain to each reference check.

### Major sections

1. Opening question and identity.
2. Study frame and frozen rules.
3. 1,532 raw → 1,185 processed → 611 provisional clusters → 30 optical cases → 28 observable / 2 unobserved.
4. Cluster grouping and event-detail reading.
5. Spatial map and external-reference relationship checks.
6. Sentinel-2 optical cohort boundary.
7. Guacamaya six-match timeline and fragmentation caveat.
8. Los Picachos 5 km threshold-miss diagnostic.
9. What the evidence does not establish.
10. Methodology, reproducibility, and sources.

### Map role

The map is an explanatory evidence surface, not an alert product. It shows public event coordinates/centroids, approximate reference anchors, and the documented 5 km relationship rings. It supports selection, filtering, and cross-reference to the event list; it does not show perimeters, spread, severity, causality, or certainty. Every map state has a list/table equivalent.

The default extent is presentation geometry: P3 must derive it deterministically
from the 611 coordinates in `events.geojson` and then apply visual padding. The
observed coordinate bounds documented in P2 are audit context only. They must
not become hardcoded longitude/latitude constants, a new public-data field, a
scientific study boundary, or a new scientific output.

### Event-detail hierarchy

Event details are revealed as identity → UTC time → detection composition → descriptive FRP → day/night context → interpretive status. The 19 public fields remain available, but primary reading fields come before advanced audit fields. Labels preserve `provisional thermal event`, `descriptive`, `possible_chain_merge`, and optical status language.

### Case treatment

- **Guacamaya:** six official matched provisional clusters, 72.733 h span, five gaps greater than 6 h, and `fragmentation_possible=true`. The six records remain separate; no continuous fire is asserted.
- **Los Picachos:** the web-native result is limited to the structured P1 values: official matching radius `5,000 m`, official matches `0`, nearest documented contemporary signal `10,400.826 m`, and classification `SPATIAL_THRESHOLD_MISS`. Figure 06 may remain visible unchanged with its wider-radius labels described as frozen diagnostic context. P3 must not add a 5/10/15 km toggle, recompute matches or distances from `events.geojson`, or hardcode metrics manually extracted from the PNG. The zero is explained as a threshold result, not absence.
- **Sentinel-2:** 30 selected optical-cohort cases, 28 observable, 2 unobserved. Selected pair/window_median and NBR/dNBR are descriptive; unobserved is not negative and no severity target is introduced.

## Visual and content direction

- **Typography:** preferred direction is Source Serif 4 for long-form/display, IBM Plex Sans for interface/captions, and IBM Plex Mono for IDs, coordinates, timestamps, and compact data. Final font loading and licensing remain P3 decisions.
- **Color:** paper, ink, slate, humid green, oxidized clay, satellite blue, and dry straw are role-based accents. No alarm-red dashboard, neon heat palette, or color-only status encoding.
- **Layout:** editorial 12-column frame, readable 60–72 character text measure, full-bleed evidence plates only when useful, generous caveat space, and captions adjacent to every figure.
- **Motion:** user-invoked clarification only—stage emphasis, selected map/timeline state, or figure zoom. No autoplay, pulsing, fly-through, simulated spread, or count-up that hides a final value.
- **Accessibility:** semantic headings and landmarks, skip link, keyboard map/table alternatives, explicit units and UTC labels, alt text plus long descriptions for data figures, visible caveats, high-contrast focus, and no critical tooltip-only content.
- **Responsive behavior:** preserve the thesis-to-limitations reading order; stack sections on narrow screens; use readable horizontal scrolling for wide figures/tables; keep map selection and figure zoom operable without hover or pinch-only interaction; honor reduced motion.

## Figure classifications

The frozen P1 figures retain their original bytes and filenames. P2 assigns their narrative roles only:

| Figure | Role |
| --- | --- |
| `01_pipeline_overview.png` | Hero / primary evidence |
| `02_cluster_distribution.png` | Supporting methodology |
| `03_external_reference_map.png` | Case-study / supporting map |
| `04_guacamaya_timeline.png` | Case-study / primary |
| `05_guacamaya_frp_distribution.png` | Case-study / supporting |
| `06_los_picachos_diagnostic.png` | Case-study / primary diagnostic |

The implementation may scale proportionally, use contain/overflow behavior,
caption, or provide user-invoked open-original/zoom. It may not crop, redraw,
recolor, retitle, replace labels, alter pixels, or generate substitute figures
without a separate approved review.

## Files created in this P2 task

Only these four new documents are in scope:

- `docs/P2_INFORMATION_ARCHITECTURE.md`
- `docs/P2_VISUAL_DIRECTION.md`
- `docs/P2_CONTENT_BLUEPRINT.md`
- `docs/P2_HANDOFF.md`

`CONTEXT.md`, `PLAN.md`, `PROJECT_STATUS.md`, all P1 documents, `site-data`, protected science, and frozen figures were read as inputs and were not modified.

## Verification and state boundary

The existing P1 public-release verifier is the required read-only regression check after these documents are written. Its final result will be recorded here before the P2 commit.

No full scientific suite is required for this documentation-only P2 task. No implementation, science regeneration, site-data edit, network access, Earth Engine execution, P3 work, or push is authorized.

## P2 exit gate

- [x] IA model and sitemap selected.
- [x] Research thesis and section order defined.
- [x] Map role, default reading, event hierarchy, and case treatment defined.
- [x] Sentinel-2 boundary and scientific vocabulary preserved.
- [x] Typography, color, layout, motion, accessibility, and responsive direction defined.
- [x] All six frozen figures classified and assigned a narrative job.
- [x] Content blueprint includes evidence, caveat, source, interaction, and mobile behavior for each section.
- [x] No frontend or new asset created.
- [x] No P1 scientific artifact or public package modified.
- [x] P1 verifier result recorded below after the read-only check.

### P1 verifier result

Command: `python scripts\verify_public_release_package.py --package site-data`

Result:

```json
{"checked_files": 14, "errors": [], "event_count": 611, "ok": true, "package": "site-data", "package_version": "firepa-public-release-v1", "reference_count": 2, "scientific_freeze_commit": "7694da7df5808911de48de84016759c5fd22f176"}
```

## P3 boundary

P3 may begin only after this handoff is reviewed. P3 would translate this direction into a frontend while preserving the public package and the scientific language above. P2 itself does not start P3.

## Auditor inputs

The P2 audit surface consists only of these four documents:

- `docs/P2_INFORMATION_ARCHITECTURE.md`
- `docs/P2_VISUAL_DIRECTION.md`
- `docs/P2_CONTENT_BLUEPRINT.md`
- `docs/P2_HANDOFF.md`

# FirePA P2 — Information Architecture

**Status:** P2 PASS — information architecture defined
**Scientific basis:** FirePA Scientific Pilot v1, frozen at
`7694da7df5808911de48de84016759c5fd22f176`
**Public basis:** P1 public release contract and `site-data/`
**Scope:** future public research experience; no frontend implementation

## 1. Product decision

### Chosen experience model: focused hybrid

FirePA should be a hybrid composed of:

1. one primary long-form research story at `/`, with anchored sections and
   progressive evidence disclosure;
2. one methodology page at `/methodology`, for readers who want the protocol,
   schema, limits and reproducibility details without interrupting the story;
3. one sources and reproducibility page at `/sources`, for citations, package
   provenance, report links and the future repository link.

The two case studies remain first-class sections of the main story rather than
becoming a collection of separate marketing pages. They may receive deep links
such as `/#guacamaya` and `/#picachos`, but the narrative should remain
coherent when read from the beginning.

This model fits the evidence better than a dashboard or a large multi-page
site. The central job is to explain a methodological narrowing and two
contrasting reference checks. A single story supplies context and caveats at
the moment they are needed; the two companion pages make the work auditable
without turning the main page into a documentation dump.

The sitemap is conceptual. It does not select Astro, React, a map library,
hosting provider or any other implementation technology.

## 2. Research identity and audience

FirePA is a public research experience about what a reproducible remote-sensing
pilot can describe from frozen local evidence. It is not an operational
wildfire map, an emergency interface, a SaaS dashboard, an AI product or a
real-time monitoring service.

The primary audiences are:

- a research-literate public reader who needs the question, evidence and limits
  in a clear sequence;
- a technical reader who wants to understand the FIRMS-to-cluster-to-optical
  narrowing and inspect the public event data;
- an auditor who needs stable paths, provenance, citations and explicit
  boundaries.

The experience should let each audience stop at a useful depth:

- story depth: question, evidence chain, map, cases and conclusion;
- technical depth: method and event-detail disclosures;
- audit depth: methodology, citations, manifest, provenance and repository
  links.

## 3. Narrative thesis

> FirePA follows 1,532 audited FIRMS detections through 1,185 processed rows,
> 611 provisional thermal events and a 30-event optical cohort to show what
> descriptive remote sensing can organize in Coclé — and where the evidence
> stops short of confirmation, ground truth or operational prediction.

The sequence is a methodological narrowing, not a scorecard:

| Stage | Public value | Required wording |
|---|---|---|
| 1,532 | audited raw FIRMS records | raw detections/records, not fires |
| 1,185 | processed FIRMS detections | processed detections |
| 611 | spatial-temporal grouping result | provisional thermal events |
| 30 | frozen Sentinel-2 optical cohort | optical cohort events |
| 28 | cohort cases with observable optical support | optically observable events |
| 2 | cohort cases explicitly unobserved | unobserved; not negative cases |

The 344 singletones, 267 multi-detection events and 17
`possible_chain_merge` events are supporting context for the 611-event layer,
not replacement headlines.

## 4. Sitemap and global navigation

### Conceptual sitemap

~~~text
/
├── #question              Research question and study frame
├── #evidence-chain        1,532 → 1,185 → 611 → 30 → 28
├── #grouping              r1500_t06 method and provisional event unit
├── #map                   611 event centroids and event detail
├── #optical               30 / 28 / 2 Sentinel-2 evidence boundary
├── #guacamaya             six matched provisional clusters
├── #picachos              zero-match spatial-threshold diagnostic
├── #limits                what FirePA can and cannot claim
└── #reproduce             package, citations and next links

/methodology
└── protocol, schema, provenance, limitations and review/model boundaries

/sources
└── citations, public package links, report link, repository link and
    reproducibility instructions
~~~

### Navigation

Desktop navigation should be a restrained section index, not a product menu:

`Research question · Evidence chain · Map · Cases · Limits · Method · Sources`

`Cases` opens a compact submenu or scrolls to the Guacamaya/Picachos pair. The
active section indicator is textual or a quiet rule, not a pulsing status light.

Mobile navigation should collapse into a keyboard-accessible menu and retain a
visible page title plus the current section. A skip link must precede it.

The global footer should carry only durable utility links: methodology, sources,
public package, scientific report, future repository and attribution. It should
not contain calls to action, subscription language or operational contact
language.

## 5. Main story sequence

| Order | Section | Question answered | Primary evidence | Main visual role |
|---:|---|---|---|---|
| 1 | Opening frame | What is FirePA, and what is it not? | `project-summary.json`, `methodology.json` | Figure 01 as a restrained opening method image |
| 2 | Study frame | What was investigated? | study area, 2025-01-01 to 2025-04-30, package definition | geographic/context text, no decorative satellite hero |
| 3 | Evidence chain | What became narrower at each stage? | frozen counts in `project-summary.json` | static count sequence with explanatory transitions |
| 4 | Grouping | How did detections become provisional events? | workflow, `r1500_t06`, 1,500 m / 6 h, Figure 02 | method diagram and descriptive distributions |
| 5 | Event map | Where are the 611 centroids, and how can one event be read? | `events.geojson` | research map with accessible list/detail fallback |
| 6 | Optical follow-up | What can Sentinel-2 add? | 30 cohort, 28 observable, 2 unobserved, methodology | Figure 01 support plus text about selected_pair/window_median |
| 7 | Guacamaya | How does a positive relational match remain qualified? | external reference, six timeline clusters, Figure 04/05 | primary case study timeline and FRP context |
| 8 | Los Picachos | What does a zero match mean, and not mean? | zero match, diagnostic, nearest signal, Figure 06 | primary diagnostic case study |
| 9 | Limits | Which claims are outside the evidence? | limitations, formal/modeling boundaries | plain-language claim boundary, no chart theater |
| 10 | Reproducibility | Can a reader inspect the work? | citations, manifest, provenance, contract, report | compact audit trail and links |

Every section should follow a consistent editorial cadence:

1. one question or claim;
2. one evidence block;
3. one interpretation;
4. one visible caveat before the reader advances.

## 6. Above-the-fold composition

The opening viewport should contain:

- the title `FirePA` and a plain descriptor such as `A reproducible
  remote-sensing pilot in Coclé, Panamá`;
- the research question: how thermal detections can be grouped and followed
  with descriptive optical evidence;
- the explicit unit label `provisional thermal events`;
- a compact period/freeze line: `2025-01-01 — 2025-04-30 · static local package ·
  no real-time monitoring`;
- a short route into the evidence chain;
- Figure 01 presented as the complete frozen image, with its original
  provenance retained. A responsive wrapper may scale it proportionally, use
  contain/overflow behavior or provide open-original/zoom; it must never crop
  or alter any pixels or labels.

The first screen must not lead with 611 as a large KPI, a red alert map, a
generic gradient, a fake live timestamp or a claim of detected fires. The
number is introduced only with its scientific unit and method context.

## 7. Method and evidence hierarchy

### Methodology placement

The story gives the reader the minimum method at the grouping and optical
sections. The full protocol belongs on `/methodology`, linked at the first
technical explanation and again near the conclusion. That page should expose:

- the exact study period and study area;
- FIRMS acquisition/audit and the distinction between raw and processed rows;
- `r1500_t06`, connected components, 1,500 m radius and six-hour window;
- the public event schema and centroid semantics;
- selected_pair and window_median as distinct descriptive modes;
- NBR/dNBR as descriptive metrics with no severity class;
- formal review deferred and supervised modeling deferred;
- privacy/provenance boundaries.

### Citation and reproducibility placement

Inline citations should sit next to claims about counts, rules and external
cases. The `/sources` page should then provide the full citation list, the
canonical registry reference, the public package manifest/provenance, the
scientific report and the future GitHub link. A reader should never need to
infer which figure or count supports a paragraph.

## 8. Map and event experience

### Purpose of the map

The map is a spatial reading of 611 public event centroids. It lets a reader
connect the grouping method to geography, inspect the two approximate external
reference anchors and open a descriptive event record. It is not an alert map,
burn perimeter, probability surface or live operational layer.

### Default map state

The default extent should fit the full public event extent in Coclé with quiet
padding. P3 should derive that extent deterministically from the 611 event
coordinates in `events.geojson`, then apply presentation padding. It must not
maintain hardcoded longitude/latitude extent constants in frontend source.
The observed P1 coordinate extent is approximately:

- longitude `-80.820670` to `-80.084970`;
- latitude `8.134570` to `9.031650`.

These bounds are informational audit context only. They are a presentation
fit derived from the public points, not authoritative constants, a new study
boundary, a new public-data field, or a claim about all thermal activity in
Panamá. The default view should show all 611 points at a neutral scale and
state the study period.

### Point encoding

- Base point: small muted slate point for a provisional thermal event.
- Selection: a high-contrast ring and a connected detail panel; no pulsing.
- Optical status: a non-color shape or outline system for `observable`,
  `unobserved` and `not_in_cohort`, with a text legend.
- FRP: optional user-controlled descriptive encoding using size or a separate
  view, labelled `descriptive FRP`, never `severity` or `intensity of fire`.
- `possible_chain_merge`: not encoded as a heat or alert signal; disclose it as
  an advanced caveat in the detail panel and optionally offer a quiet filter.
- External anchors: distinct labelled approximate points with a visible 5 km
  reference ring and a caption that the ring is a matching rule, not a burn
  perimeter.

The map should initially avoid a density heatmap. A heatmap would encourage a
reader to interpret point density as fire intensity or risk. If a density view
is explored in a later implementation, it must be explicitly described as a
visual aggregation of provisional centroids.

### Temporal filtering

A date-range filter is valuable because every event has UTC start/end times and
the study period is fixed. It should be an optional reader-controlled view, not
an autoplay timeline or a real-time control. The default remains the whole
period; selected dates must remain visible in text and keyboard accessible.

### Event selection and detail hierarchy

Selecting a point opens a side panel on desktop and a bottom sheet on mobile.
The panel must begin with the unit and limitation, not a dramatic label:

1. `Provisional thermal event · evt-XXXX` as a stable public reference;
2. UTC interval and duration;
3. detection count and the statement that this is a grouped FIRMS-derived
   event, not a confirmed fire;
4. optical cohort status, with `unobserved` explicitly distinguished from a
   negative case;
5. descriptive FRP summary and sensor/day-night composition;
6. advanced method fields and `possible_chain_merge` caveat;
7. a link to methodology/schema context.

No event panel should show a target, class, severity, probability, confidence
of fire, ground truth, raw detection rows, scene IDs, raster paths or review
identities. Those concepts are absent from the P1 public schema and remain
absent from the UI.

### Field-by-field UI decision

| P1 field | UI tier | Treatment |
|---|---|---|
| `public_event_id` | PRIMARY DISPLAY | Stable selection/reference label; state that the ordinal has no scientific meaning. |
| `configuration_id` | ADVANCED / METHODOLOGY ONLY | Show only in an expanded method disclosure as `r1500_t06`. |
| `start_time_utc` | PRIMARY DISPLAY | Pair with end time and preserve UTC. |
| `end_time_utc` | PRIMARY DISPLAY | Pair with start time; never imply continuous observation between detections. |
| `duration_hours` | PRIMARY DISPLAY | Descriptive grouped-event duration, not burn duration. |
| `detection_count` | PRIMARY DISPLAY | Explain that it counts grouped detections, not confirmed fires. |
| `source_count` | SECONDARY DISPLAY | Sensor-source composition detail. |
| `satellite_count` | SECONDARY DISPLAY | Sensor composition detail. |
| `satellites` | SECONDARY DISPLAY | Text list with N/N20 labels; do not imply independent confirmation. |
| `frp_min_mw` | SECONDARY DISPLAY | Descriptive FRP range context; never severity. |
| `frp_max_mw` | SECONDARY DISPLAY | Descriptive FRP range context; never severity. |
| `frp_mean_mw` | SECONDARY DISPLAY | Descriptive summary with unit MW. |
| `frp_median_mw` | SECONDARY DISPLAY | Descriptive summary with unit MW. |
| `frp_sum_mw` | SECONDARY DISPLAY | Keep subordinate to avoid an intensity reading. |
| `day_fraction` | SECONDARY DISPLAY | Show with night fraction and denominator context. |
| `night_fraction` | SECONDARY DISPLAY | Show with day fraction and denominator context. |
| `daynight_known_count` | ADVANCED / METHODOLOGY ONLY | Explain the known denominator; do not hide missingness by converting it to zero. |
| `possible_chain_merge` | ADVANCED / METHODOLOGY ONLY | Text caveat about representation under the frozen grouping rule. |
| `optical_cohort_status` | PRIMARY DISPLAY | Three-state text/shape treatment; `unobserved` is not negative. |

No P1 public field needs to be removed from a downloadable data view. The
default UI should be selective, while the methodology page or an accessible
data table can expose the complete allowlisted schema. Private and prohibited
concepts are not a fourth display tier; they are not part of the public schema.

## 9. Case-study architecture

### Cerro Guacamaya

The Guacamaya section should be a qualified relational case study:

1. identify the external reference as an approximate anchor and six-source
   record set;
2. state the matching rule: inclusive temporal overlap and distance at or below
   5,000 m;
3. show six separate matched provisional clusters in Figure 04;
4. use the 72.733-hour span and five gaps greater than six hours as evidence of
   temporal separation, not continuity;
5. use Figure 05 for descriptive maximum/mean FRP context only;
6. state that `fragmentation_possible=true` is a representation limitation of
   the frozen grouping, not permission to recluster or merge the events;
7. link to the six public event IDs and source citations.

The title should say `Cerro Guacamaya: six matched provisional clusters`, not
`one detected fire` or `successful detection`. The six-cluster timeline is the
primary visual; the FRP plot is supporting evidence.

### Cerro Los Picachos

The Picachos section should be a diagnostic case study, not a failure story:

1. identify the externally reported incident and its approximate anchor;
2. state the same 5 km / inclusive-window matching rule;
3. report zero official matches at that rule;
4. preserve the exact diagnostic `SPATIAL_THRESHOLD_MISS`;
5. report the nearest documented contemporary signal as `10,400.826 m`;
6. explain that a zero relational match does not prove no fire, no activity or
   no signal in the region;
7. explain that distance, timing, approximate anchors, sensor coverage and the
   provisional grouping can all affect the result.

Figure 06 is the primary visual. The web-native result block must use only the
structured P1 values: official matching radius `5,000 m`, official matches
`0`, diagnostic `SPATIAL_THRESHOLD_MISS`, and nearest documented contemporary
signal `10,400.826 m`. The frozen figure may remain visible unchanged, with a
caption explaining that its wider-radius labels are expanded diagnostic
context. P3 must not recompute matches or distances from `events.geojson`,
implement an interactive 5/10/15 km radius control, or hardcode additional
metrics transcribed from the PNG. A future interactive expanded-radius
diagnostic would require a separately reviewed and versioned public-data
contract. Do not turn the figure into a claim of absence or failed detection.

The two cases should be presented together as a paired reasoning section:
Guacamaya demonstrates a relational match with visible temporal gaps; Picachos
demonstrates why a non-match is a constrained diagnostic rather than a negative
truth label.

## 10. Sentinel-2 experience boundary

Sentinel-2 enters the story after the 611-event grouping, as a descriptive
follow-up cohort:

- 30 events were in the frozen optical cohort;
- 28 had observable optical support;
- 2 were explicitly unobserved;
- `selected_pair` and `window_median` are evidence modes, not competing labels;
- NBR/dNBR are descriptive metrics for the observable subset, with no severity
  class.

P1 deliberately does not expose event-level review panels, scene IDs, raster
paths or full optical metrics. Therefore P2 defines no interactive image
analysis, swipe comparison, raster explorer or per-event spectral viewer. The
story uses Figure 01 and precise methodology copy; any future web-native
representation must be derived from the existing public contract without
inventing hidden evidence.

## 11. Reproducibility and source relationships

The final story should link claims to their nearest public source:

- counts, definition and limitations → `project-summary.json`;
- event map and detail → `events.geojson`;
- reference anchors and invariants → `external-references.geojson`;
- Guacamaya chronology → `guacamaya-timeline.json`;
- method and limits → `methodology.json`;
- external citations → `citations.json`;
- transformation and hashes → `provenance.json` and `manifest.json`;
- visual evidence → the six frozen figures and their provenance records.

The `/sources` page should explain that the package is static, deterministic,
frontend-agnostic, network-free at consumption time and not a runtime
scientific engine. Future report and repository links are publication links,
not new data sources.

## 12. IA accessibility and responsive rules

- Every section has a real heading and a logical landmark.
- A skip link, keyboard-visible focus and a text section index precede the main
  story.
- Scroll transitions are enhancements; all claims and numbers remain in the
  document order without animation.
- The map always has an accessible event list/table fallback with the same
  selection semantics.
- Figures have captions, meaningful alt text and a zoom/open-original control.
- Long event IDs, source names, URLs and caveats wrap without horizontal
  clipping.
- Mobile case studies use one column: evidence, interpretation, caveat; no
  side-by-side comparison is required to understand the result.
- Touch targets are at least 44 CSS px and map gestures never trap page scroll.
- Color is never the only encoding for optical status, case identity or FRP.
- Reduced motion switches scroll-linked transitions, map flights and timeline
  animation to immediate state changes.

## 13. P2 exclusions

This document does not authorize:

- a frontend framework, package manager or application directory;
- MapLibre, Leaflet, PMTiles or a basemap;
- backend, authentication, hosting, Cloudflare or domain setup;
- changes to `site-data/`, figures or protected science;
- new external research, OSINT, Earth Engine calls or runtime APIs;
- scientific v2, reclustering, formal review execution or model training.

Those decisions belong to later gates or a separately authorized scientific
scope.

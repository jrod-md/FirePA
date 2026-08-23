# FirePA P2 — Content Blueprint

**Status:** P2 content blueprint complete; implementation is deferred to P3.

**Content contract:** this blueprint turns the P1 public package into a readable research experience without changing the package, its figures, or its scientific claims. It is a writing and evidence-placement plan, not frontend code.

**Scientific freeze:** `7694da7df5808911de48de84016759c5fd22f176`.

## Editorial promise

FirePA documents how a local, frozen analysis moved from raw FIRMS records to auditable provisional thermal-event groupings, a limited Sentinel-2 descriptive cohort, and two external-reference checks in Coclé, Panama. The experience must leave the reader with a calibrated conclusion:

> The package makes the detection and grouping process inspectable. It does not establish 611 confirmed fires, ground truth, burn severity, continuous fire spread, or a predictive model.

The first sentence of every evidence block should answer what is being shown. The second should state the scope or denominator. The caveat should be adjacent, not deferred to a generic footer.

## Content model

Every substantive section follows this sequence:

1. **Claim or question** — a short, plain-language reason to read the section.
2. **Evidence** — a value, record, figure, map, or source from the public package.
3. **Interpretation** — what that evidence supports within the frozen method.
4. **Caveat** — what it does not support or what remains unresolved.
5. **Source** — a direct link or named record in `manifest.json`, `provenance.json`, `citations.json`, or the relevant public JSON/GeoJSON.

No section may introduce a number without its unit, time window, or denominator when those are available in the package. All timestamps are UTC unless explicitly stated otherwise. “Event” in reader-facing copy means “provisional thermal event” unless the surrounding sentence makes the qualifier unambiguous.

## Voice and vocabulary

### Preferred vocabulary

- provisional thermal event
- processed FIRMS detection
- connected-component cluster
- frozen configuration `r1500_t06`
- descriptive FRP statistic
- optical cohort / observable / unobserved
- official reference window
- relationship check
- inclusive distance threshold
- approximate anchor
- spatial threshold miss
- fragmentation possible
- formal human observation: 0
- deferred / unavailable / not established

### Avoid or qualify

Do not use “fire,” “wildfire,” “burn,” “severity,” “spread,” “confirmed,” “risk,” “probability,” “accuracy,” “validation,” “impact,” or “incident” as a synonym for the public event records. They may appear only when the source itself is being described, when discussing limitations, or when explicitly qualified as an external reference or unverified interpretation.

Avoid “detected fires,” “fire map,” “fire count,” “hotspot truth,” “severity score,” “confidence score,” “model performance,” “continuous Guacamaya fire,” and “Picachos had no fire.” Prefer “provisional thermal-event records,” “spatial relationship map,” “cluster count,” “descriptive FRP values,” “no defensible target with current evidence,” and “no qualifying match within the 5 km window.”

Do not call the two unobserved optical cases negative observations. Say that the selected optical window did not provide an observable outcome under the documented QA state.

## Global data and source strategy

The public package is the canonical content source. Later implementation should load or embed only the exact public records named below, with no runtime network dependency and no Earth Engine dependency:

- `project-summary.json` for the study frame, counts, and limitations.
- `events.geojson` for the public event records and coordinates.
- `external-references.geojson` for the two named reference checks and their match summaries.
- `guacamaya-timeline.json` for the six chronological Guacamaya matches, gaps, and descriptive values.
- `methodology.json` for workflow stages, configuration, and explicit deferrals.
- `citations.json` for source documents and citation labels.
- `provenance.json` for the public boundary, source records, and figure provenance.
- `manifest.json` for package version, file inventory, hashes, and scientific-freeze reference.

The source/reproducibility surface should expose file names, package version, freeze commit, and SHA-256 values from the package rather than restating them in hand-authored prose. Figure captions should link to the corresponding manifest/provenance record.

## Story sequence

The following sections are the intended long-form content sequence. Each section is specified as a content contract for P3.

### 1. Opening — What does this local record actually show?

**Purpose:** orient a non-specialist reader and prevent the first visual from being read as a fire-confirmation claim.

**Main question:** What can a frozen local analysis say about FIRMS thermal detections in the study frame?

**Data source:** `project-summary.json`, `manifest.json`, `provenance.json`.

**Visual:** a restrained title, a short standfirst, and `01_pipeline_overview.png` as the opening evidence figure.

**Supporting copy:** introduce the study as a static, local, descriptive package covering the documented period and Coclé frame. State the headline chain in one line: 1,532 raw FIRMS rows → 1,185 processed detections → 611 provisional clusters → 30 optical-cohort cases, of which 28 were observable and 2 unobserved.

**Scientific caveat:** these are not 611 confirmed fires, and the package contains zero formal human observations.

**Interaction:** optional user-invoked “read the chain” emphasis that highlights one stage at a time while keeping the full sentence visible.

**Mobile behavior:** stack the title, caveat, and figure; show the chain as a vertical sequence with the same counts, not as a compressed horizontal diagram.

### 2. Study frame — Where and under what rules?

**Purpose:** establish geography, time, input boundary, and the frozen configuration before any case interpretation.

**Main question:** What was included, and what was deliberately held fixed?

**Data source:** `project-summary.json`, `methodology.json`, `manifest.json`.

**Visual:** compact study-frame block with period, ROI, source, and configuration; link to methodology and package files.

**Supporting copy:** explain that the pipeline uses the documented FIRMS audit and connected-components configuration `r1500_t06` (1,500 m and 6 h, EPSG:32617). State that the public package is static and consumes no live Earth Engine or network service.

**Scientific caveat:** the configuration is a grouping rule, not a truth label; no per-event tuning or reclustering is implied.

**Interaction:** expandable method note for units and definitions; no hidden change of threshold.

**Mobile behavior:** present the frame as a definition list or two-column table that collapses to label/value rows.

### 3. Evidence chain — From rows to provisional clusters

**Purpose:** show how the denominator changes through the pipeline.

**Main question:** What does each transformation do to the record?

**Data source:** `project-summary.json`, `methodology.json`, `events.geojson`, `01_pipeline_overview.png`.

**Visual:** the pipeline figure plus a text-first stage list. Each stage gets input, operation, output count, and limitation.

**Supporting copy:** distinguish raw records from processed detections and clusters. Explain that 344 clusters are singletons and 267 are multi-detection clusters; 17 are flagged `possible_chain_merge` under the frozen method.

**Scientific caveat:** grouping nearby detections reduces the row count but does not prove one physical fire, burn area, severity, or continuity.

**Interaction:** selecting a stage can filter the explanatory text or link to the relevant public file, but must not alter the underlying records.

**Mobile behavior:** stage list first, figure second or in a horizontal scroll wrapper; keep each count next to its qualifier.

### 4. Grouping — What is an event record here?

**Purpose:** teach the reader how to read one public event without turning the schema into a technical appendix.

**Main question:** Which fields help describe a provisional cluster and which remain interpretive limits?

**Data source:** `events.geojson`, public schema contract, `02_cluster_distribution.png`.

**Visual:** descriptive histograms followed by an event-detail panel or table. Use the schema categories from the information architecture: primary reading fields, secondary context, and advanced audit fields.

**Supporting copy:** explain public IDs, UTC start/end, duration, detection/source/satellite counts, satellites, FRP summary statistics, day/night fractions and known count, `possible_chain_merge`, and `optical_cohort_status`. A representative detail record should show the exact public values, units, and status labels.

**Scientific caveat:** FRP is reported descriptively; it is not severity, energy, area, or a confidence score. Day/night fractions describe known classification records only.

**Interaction:** search/filter by public event ID, date, satellite, optical status, or chain-merge flag; selection links to the map and preserves a clear “filtered view” label.

**Mobile behavior:** prioritize ID, UTC interval, detections, FRP summary, and status; place advanced fields in a disclosure that remains keyboard and screen-reader accessible.

### 5. Spatial view — Where do the public event records sit?

**Purpose:** give geographic orientation and a way to inspect the public point records.

**Main question:** What spatial relationships are visible in the frozen public package?

**Data source:** `events.geojson`, `external-references.geojson`, `03_external_reference_map.png`, `provenance.json`.

**Visual:** an interactive map may be implemented later, supplemented by the frozen external-reference map. Event centroids, approximate anchors, and 5 km rings use distinct shapes, line styles, and text labels.

**Supporting copy:** describe points as public event coordinates/centroids, not perimeters. Explain that the two reference checks use an inclusive 5,000 m distance window and official date windows. Keep “approximate” attached to the anchors.

**Scientific caveat:** a map point is not a physical fire boundary; proximity is a relationship criterion, not causal attribution. A zero match within a window is not proof of no fire.

**Interaction:** select a point to reveal a public event detail; filter by date or case; select a reference to show its official window and match summary. Every map action has a list/table alternative.

**Mobile behavior:** default to a simplified map height with a persistent legend and an adjacent scrollable result list; never require precise hover or pinch-only discovery.

### 6. Optical cohort — What did Sentinel-2 add, and what did it not add?

**Purpose:** describe the limited optical evidence without presenting it as validation or a burn-severity product.

**Main question:** Which public event records had a documented optical cohort outcome?

**Data source:** `project-summary.json`, `methodology.json`, `provenance.json`, public package figures where applicable.

**Visual:** a simple cohort summary: 30 selected cases, 28 observable, 2 unobserved; a short method note for selected pair/window_median and descriptive NBR/dNBR.

**Supporting copy:** state that Sentinel-2 was used as a descriptive optical cohort with the documented QA state. Explain that NBR/dNBR values do not become severity labels in this release.

**Scientific caveat:** unobserved means that the selected window did not provide an observable outcome under the documented condition; it does not mean negative. The package does not provide formal ground truth or a validated severity target.

**Interaction:** optional filter from the event table to observable/unobserved status; no false-color image or threshold legend may be introduced without a later approved source.

**Mobile behavior:** show the 30/28/2 counts as text and status rows; put method details below the summary, not inside a dense chart.

### 7. Guacamaya — What does a multi-match reference window look like?

**Purpose:** examine the strongest public relational example while making temporal fragmentation visible.

**Main question:** How do six official-window matches relate in time under a 6 h grouping rule?

**Data source:** `external-references.geojson` REFERENCE-002, `guacamaya-timeline.json`, `04_guacamaya_timeline.png`, `05_guacamaya_frp_distribution.png`, `citations.json`.

**Visual:** timeline first, then the descriptive C1–C6 FRP figure and an accessible chronological list.

**Supporting copy:** state six official matched provisional clusters, a 72.733 h overall span, and five gaps greater than 6 h. Name the six public event IDs in chronological order from the timeline record; expose start/end, detection count, gap from the previous cluster, and descriptive FRP values.

**Scientific caveat:** the gap pattern means fragmentation is possible under the frozen configuration. Do not merge the six clusters into a continuous fire or imply a continuous burn process. `possible_chain_merge` remains a record-level flag, not a resolution of the ambiguity.

**Interaction:** selecting a timeline cluster opens the same public event detail and highlights its map point. Gap annotations remain textual and do not animate a line of spread.

**Mobile behavior:** use a vertical chronological list with gap rows between clusters; the wide timeline becomes an optional scroll/zoom figure, and the five gaps remain readable in text.

### 8. Los Picachos — What does a 5 km miss mean?

**Purpose:** show why a non-match is still evidence about the threshold, not evidence of absence.

**Main question:** What happened when the official reference window and inclusive 5 km rule were applied?

**Data source:** `external-references.geojson` REFERENCE-001, `06_los_picachos_diagnostic.png`, and `citations.json`.

**Visual:** the unchanged diagnostic figure paired with a web-native result block using only the structured P1 values: official matching radius `5,000 m`, official matches `0`, diagnostic `SPATIAL_THRESHOLD_MISS`, and nearest documented contemporary signal `10,400.826 m`. The figure caption may explain that Figure 06 contains wider-radius diagnostic context; those labels are not a second structured interactive result.

**Supporting copy:** explain that the documented reference window was 2025-01-15 to 2025-01-17. Preserve the approximate nature of the anchor, the official 5,000 m rule, and the exact public classification. If the expanded context is mentioned, identify it as information contained in the frozen Figure 06 only.

**Scientific caveat:** zero qualifying matches at 5 km does not mean there was no fire. It means the public event records did not satisfy that spatial threshold within the documented window.

**Interaction:** no expanded-radius toggle is authorized. P3 must not recompute reference matches or distances from `events.geojson`, and must not hardcode additional diagnostic metrics manually extracted from the PNG as structured P1 data. A future interactive expanded-radius diagnostic requires a separately reviewed and versioned public-data contract.

**Mobile behavior:** put the official conclusion and caveat above the figure; show the four structured P1 values in a readable result list; preserve the complete frozen figure in a responsive wrapper with proportional scaling, contain/overflow behavior, or user-invoked zoom.

### 9. Limits — What should the reader refuse to infer?

**Purpose:** turn limitations into a visible conclusion rather than an appendix disclaimer.

**Main question:** Which tempting interpretations are outside the P1 evidence?

**Data source:** `project-summary.json`, `methodology.json`, `provenance.json`, public release contract.

**Visual:** a two-column “supports / does not establish” comparison, with no risk meter or confidence gauge.

**Supporting copy:** list the explicit boundaries: no ground truth, no formal human observations, no confirmed-fire label, no severity target, no validated predictive model, no causal external-reference attribution, no continuous Guacamaya merge, and no negative interpretation for unobserved optical cases.

**Scientific caveat:** the limitations are part of the result and must remain visible wherever a section uses a potentially ambiguous term.

**Interaction:** none required; an optional anchor navigation can jump to the relevant case or method evidence.

**Mobile behavior:** stack each “supports / does not establish” pair; do not collapse the caveats by default.

### 10. Methodology and reproducibility — How can this be audited?

**Purpose:** give an independent reader a compact route from the narrative to the exact public package.

**Main question:** Which frozen inputs, stages, configurations, and outputs are available for inspection?

**Data source:** `methodology.json`, `manifest.json`, `provenance.json`, `citations.json`.

**Visual:** a text-first method outline with a file inventory and a small package-status block; `01_pipeline_overview.png` may be reused only if the caption makes the different purpose clear.

**Supporting copy:** link each stage to its public file where possible. State the package version, scientific freeze, static/no-network consumption boundary, source-document inventory, and figure provenance. Include the documented deferrals: formal review was not completed because a qualified reviewer was unavailable, and model training was deferred because there was no defensible target with current evidence.

**Scientific caveat:** a reproducible public package is not the same as scientific validation; deterministic packaging does not create ground truth.

**Interaction:** file links, copyable hashes, and accessible source notes; no download of private or protected material.

**Mobile behavior:** use a collapsible but non-hidden file inventory; long hashes can wrap or scroll horizontally with an accessible label.

### 11. Sources and close — What is the public record?

**Purpose:** finish with provenance and a clear boundary around the public release.

**Main question:** Which documents and records support the story?

**Data source:** `citations.json`, `provenance.json`, `manifest.json`.

**Visual:** source list, package metadata, figure credits, and a short closing statement; no promotional “call to action.”

**Supporting copy:** distinguish source documents, external reference records, derived public files, and frozen figures. Keep the distinction between a source document and an independent confirmation.

**Scientific caveat:** the source list documents traceability; it does not change the evidentiary status of the records.

**Interaction:** plain links and copyable metadata only.

**Mobile behavior:** one-column source list with clear source IDs and descriptions; keep the package boundary and limitation note before the footer.

## Event-detail content hierarchy

When a reader selects an event, the detail view should reveal information in this order:

1. **Identity:** `public_event_id` and `configuration_id`.
2. **Time:** `start_time_utc`, `end_time_utc`, `duration_hours`.
3. **Detection composition:** `detection_count`, `source_count`, `satellite_count`, and `satellites`.
4. **Descriptive signal:** `frp_min_mw`, `frp_max_mw`, `frp_mean_mw`, `frp_median_mw`, and `frp_sum_mw` in MW where present.
5. **Day/night context:** `day_fraction`, `night_fraction`, and `daynight_known_count`.
6. **Interpretive status:** `possible_chain_merge` and `optical_cohort_status`, with definitions adjacent.

The public schema has 19 fields. The detail view must not invent labels such as “fire severity,” “confidence,” or “validation status.” A selected event can be linked to its map point, Guacamaya timeline entry, or optical cohort row only when such a relation is present in the public package.

## Content QA gate for P3

Before implementation is accepted, review each rendered section for:

- exact count consistency with the public JSON;
- visible denominator and UTC/window context;
- no unsupported “fire,” severity, spread, risk, accuracy, or confidence language;
- adjacent caveat for every ambiguous interpretation;
- source/provenance link for every figure and external-reference claim;
- equivalent text for map, timeline, chart, color, and status encodings;
- no network or Earth Engine dependency at package consumption;
- unchanged public files and frozen figure bytes;
- responsive reading order and reduced-motion behavior.

P3 must implement this blueprint without expanding the scientific scope. If a visual or interaction requires new evidence, stop and return to the P1/P2 review boundary instead of filling the gap with an invented asset or inference.

## Explicit exclusions

This blueprint does not authorize a frontend, HTML prototype, component system, package installation, map-provider choice, new imagery, new statistics, model training, formal review, Earth Engine execution, network access, or edits to `site-data`, protected science, figures, or P1 documents.

# FirePA P2 — Visual Direction

**Status:** P2 design direction complete; this document is a handoff for a later implementation phase.

**Scope:** visual language, layout, typography, color, motion, accessibility, responsive behavior, and treatment of the frozen P1 figures. No frontend code, assets, package configuration, or scientific artifact is defined here.

**Source boundary:** this direction is based on the P1 public release contract, schema audit, handoff, public package, provenance, manifest, and the six frozen public figures. The scientific freeze remains `7694da7df5808911de48de84016759c5fd22f176`. The package is static and descriptive; the visual language must preserve that boundary.

## Visual premise

FirePA should feel like an annotated field report that can be read as a research story, not like an emergency dashboard or a promotional climate website. The visual system should make the evidence chain legible:

`FIRMS detections → processed detections → provisional clusters → optical cohort → external-reference checks`

The central visual tension is between a human-scale landscape and a disciplined measurement record. Warm terrain and field-note cues may provide atmosphere, but every visual emphasis must remain subordinate to the evidence status of the underlying record.

The design must not imply that a thermal detection is a confirmed fire, that a cluster is a burn scar, that FRP is severity, or that an external reference establishes causation. “Provisional thermal event,” “relationship check,” “descriptive,” “approximate,” and “not observed” remain visible vocabulary in the interface.

## Design principles

1. **Evidence before atmosphere.** A number, map mark, or figure is introduced by what it measures and by its limitation.
2. **Editorial cadence.** Long-form explanation, short evidence blocks, figures, and compact metadata alternate so the reader can pause and orient.
3. **Quiet scientific confidence.** Use hierarchy, spacing, and annotation instead of dramatic color, alarm states, or exaggerated scale.
4. **Terrain as context, not proof.** Geographic texture can frame the work; it must never be mistaken for an observed burn surface or a precision basemap claim.
5. **One status, one meaning.** Day/night, observable/unobserved, matched/missed, and provisional/formal states need explicit labels in addition to color or shape.
6. **Preserve the record.** The frozen figures remain unchanged and are presented with captions, source notes, and a legible zoom path.

Avoid a generic “wildfire dashboard” pattern: no red urgency palette, glowing points, live-alert styling, KPI tiles that hide denominators, autoplay map flights, or hero photography that makes the study look more certain than it is.

## Typography direction

### Preferred pairing

- **Long-form and display:** Source Serif 4.
- **Interface, navigation, captions, and explanatory UI:** IBM Plex Sans.
- **Identifiers, coordinates, timestamps, counts, and compact metadata:** IBM Plex Mono.

This pairing separates interpretation from instrumentation without making the site feel like a software console. It supports Spanish diacritics, readable long-form paragraphs, tabular-looking numbers, and the mixed prose/data character of the project. Any eventual webfont decision must confirm licensing, local loading, fallback behavior, and performance during P3; this document does not add a dependency.

### Type roles

These are semantic roles for later implementation, not a CSS token specification:

- **Display title:** one strong question or thesis, short enough to read at a glance.
- **Section title:** an evidence question, not a product feature name.
- **Deck/standfirst:** two to four lines establishing the study boundary and key caveat.
- **Body:** comfortable reading measure, approximately 60–72 characters per line on wide screens.
- **Figure title and caption:** concise, with the measured quantity and scope stated first.
- **Data label:** IBM Plex Mono or equivalent; never use all-caps for long passages.
- **Micro-label:** only for status, source IDs, or compact metadata; preserve readable minimum size and line height.

Use sentence case for navigation, section headings, and figure titles. Reserve uppercase or small caps for short source/status labels. Numeric alignment should help comparison, not turn the page into a terminal.

## Color direction

The palette is grounded in paper, wet forest, clay, satellite blue, and dry-season straw. These are role suggestions for P3; they are not a claim that any color represents a scientific classification.

| Role | Suggested value | Use | Constraint |
| --- | --- | --- | --- |
| Paper | `#F5F2EA` | Primary page background | Keep long-form reading warm but not low-contrast. |
| Ink | `#17233D` | Body text, headings, primary marks | Default text should meet WCAG AA. |
| Slate | `#607089` | Secondary text, rules, inactive metadata | Do not use for essential text at small sizes without contrast testing. |
| Humid green | `#3E705F` | Vegetation/context accent, observable state | Never use green alone to mean “valid” or “safe.” |
| Oxidized clay | `#B84D29` | Attention, gap annotation, selected case accent | Use sparingly; it is not a fire-confirmation color. |
| Satellite blue | `#2F63C8` | Links, optical/reference annotation, focus | Pair with labels and shapes. |
| Dry straw | `#D7B65D` | Warm secondary accent, day markers | Test text contrast; primarily a fill or rule color. |
| White | `#FFFFFF` | Cards, figure breathing space, focus surfaces | Avoid excessive cardization. |

Do not use neon red, black dashboards, gradients that look like heat intensity, or a rainbow scale that invites unsupported severity interpretation. Color must never be the only encoding: pair it with text, line style, icon shape, position, or pattern. Focus indicators need a high-contrast outline independent of the selected palette. Dark-mode behavior is a later implementation decision and must retain the same meanings and contrast ratios.

## Layout and composition

- Use a restrained editorial grid: a 12-column desktop grid with a readable text column nested inside it, generous outer margins, and occasional full-bleed evidence plates.
- Let narrative sections occupy a central reading measure; let maps and 1600×900 figures expand beyond it only when the extra width improves interpretation.
- Place a small evidence label, section number, or source cue at the start of major blocks so the reader always knows where they are in the chain.
- Use whitespace as a methodological pause. A caveat should have visual room rather than being buried in a tooltip.
- Use thin rules, small coordinate-like labels, and low-opacity contour/graticule motifs as a recurring visual grammar. They should remain secondary to headings, text, and data.
- Avoid a uniform grid of cards. Cards are appropriate for a bounded definition, status, or compact record; they are not the default container for every paragraph.
- Keep a consistent caption zone below every figure. The caption includes what is shown, the relevant denominator/window, and the scientific limitation.

### Map composition

The map is an explanatory instrument. The default view should provide the Coclé study frame and the observed public event extent, with a compact legend and an explicit statement that points are provisional thermal-event centroids. Reference anchors and 5 km rings must be distinguishable from event marks, and approximate anchors must be labeled as approximate.

The default extent is presentation geometry and should be derived deterministically from the 611 coordinates in `events.geojson`, followed by visual padding. P3 must not maintain hardcoded longitude/latitude extent constants in frontend source. The observed event coordinate bounds are approximately longitude `-80.820670` to `-80.084970` and latitude `8.134570` to `9.031650`; these values are informational audit context only, not an authoritative study boundary, a new public-data field, or a new scientific output. A basemap is not prescribed by P2. If one is used later, its licensing, network behavior, visual dominance, and boundary semantics require explicit review.

## Motion and interaction tone

Motion should clarify a relationship or acknowledge a user action only:

- a restrained reveal can show the evidence chain in its documented order;
- selecting a map point can open its event record and focus the corresponding table row;
- a timeline can highlight a selected Guacamaya cluster and its adjacent time gap;
- a figure can gain a user-invoked zoom or annotation layer.

No autoplay, perpetual point pulsing, map fly-through, parallax landscape, count-up animation that hides the final number, or animation implying spread or continuity. Reduced-motion preferences must disable nonessential transitions and preserve the same content and focus order. Motion cannot be used to suggest a fire moving from one cluster to another.

## Frozen figure treatment

The six P1 PNGs are 1600×900, frozen, and must not be redrawn or altered in P2/P3 implementation. They have minimal PNG structure and no embedded text metadata. Their small labels and pixel-like typography are part of the existing record; the implementation should provide a readable caption, a full-size/zoom affordance, and meaningful alternative text rather than silently editing the source image.

| Figure | Classification | Narrative job | Placement and treatment |
| --- | --- | --- | --- |
| `01_pipeline_overview.png` | **Hero / primary evidence figure** | Establishes the complete local pipeline and the 1,532 → 1,185 → 611 → 30/28 progression. | Near the opening thesis or study-frame section. Full-width evidence plate where possible; provide the same sequence in nearby text and a long description. |
| `02_cluster_distribution.png` | **Supporting methodology figure** | Shows descriptive distributions for maximum/mean FRP, detections per cluster, and duration. | After the grouping section. Explain that histograms describe provisional clusters and are not fire/severity distributions. Use a caption and a zoom path for small labels. |
| `03_external_reference_map.png` | **Case-study / supporting map figure** | Locates the 611 frozen centroids, approximate reference anchors, and 5 km relationship rings. | Beside or immediately after the map/external-reference explanation. State that the rings are a relationship-check aid, not an administrative boundary or fire perimeter. |
| `04_guacamaya_timeline.png` | **Case-study / primary figure** | Makes the six official Guacamaya matches and their gaps visible. | In the Guacamaya section before the detailed list. Preserve day/night and gap labels with text equivalents; do not animate continuity. |
| `05_guacamaya_frp_distribution.png` | **Case-study / supporting figure** | Gives a descriptive FRP sequence for Guacamaya clusters C1–C6. | After the timeline and before the caveat. Caption that it is descriptive and does not form a composite score or inference. |
| `06_los_picachos_diagnostic.png` | **Case-study / primary diagnostic figure** | Explains the official zero-match 5 km result and `SPATIAL_THRESHOLD_MISS`; its wider-radius labels remain frozen diagnostic context inside the image. | In the Picachos section. Pair the structured 5,000 m/0-match result with the 10.40 km nearest documented signal and the explicit “zero at 5 km ≠ no fire” caveat. |

The original figure filenames, source path, SHA-256, and provenance should be exposed in the later source/reproducibility surface. Do not replace them with newly styled charts before a separate scientific/visual review. A responsive wrapper may scale proportionally, use `object-fit: contain`, allow horizontal overflow, or provide open-original/zoom; it must never crop, redraw, recolor, retitle, replace labels, or alter pixels.

## Accessibility and responsive behavior

- Maintain a visible skip link, logical heading hierarchy, keyboard-accessible navigation, and a focus order that follows the narrative rather than the DOM order of decorative layers.
- Every chart or figure receives concise alt text plus a longer nearby description when the image carries more than decorative information. The surrounding text must include the important numbers and caveat.
- Tables and event-detail records must remain usable with keyboard and screen readers. Headers, units, UTC labels, and status terms must be explicit.
- Use landmarks for navigation, main story, methodology, sources, and footer. Do not place critical caveats only in hover or tooltip states.
- On narrow screens, stack narrative and evidence; keep captions immediately adjacent to figures; allow wide tables and figures to scroll horizontally inside an announced region rather than shrinking them into illegibility.
- Preserve the visual order: thesis → scope → evidence chain → spatial/temporal cases → limitations. A mobile layout may stack or reorder decorative elements, but not the scientific argument.
- Touch targets must be comfortably tappable; map selection and figure zoom need non-pointer alternatives. Orientation changes must not remove context or controls.
- Test the final color roles, text resizing, 200% zoom, reduced motion, keyboard navigation, and screen-reader naming during P3.

## Visual do / do not

**Do:** show denominators; label approximate anchors; keep “provisional,” “descriptive,” “unobserved,” and “not a match” in the visual hierarchy; use line/shape/text redundancies; let figures breathe; expose the source path and limitations.

**Do not:** turn the map into a live alert surface; equate color with certainty or severity; hide the two unobserved optical cases; merge Guacamaya into a continuous fire; treat Picachos’ zero 5 km matches as absence; redraw the frozen P1 figures; or introduce imagery, basemaps, or decorative evidence not present in the public release.

## P2 boundary

This is a direction document, not a frontend specification with executable tokens. P3 may translate these choices into components only after the four P2 documents are reviewed. No new assets, external services, packages, implementation files, or scientific recalculation are authorized by this document.

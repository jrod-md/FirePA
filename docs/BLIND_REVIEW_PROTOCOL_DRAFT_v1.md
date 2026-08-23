# Blind AI calibration review protocol — draft-v1

## Purpose and status

This document defines a provisional, two-pass review of seven self-contained
image cases. It is an observation protocol for calibration of a review
instrument. It does not create ground truth, a final class, a severity scale,
or a scientific label.

The reviewer receives one multispectral evidence panel per case for Pass A and
one temporal robustness panel per case for Pass B. The case identifier is the
only identifier supplied for joining a response to a panel.

The calibration remains provisional until an explicit protocol decision is
made after the responses are audited. A provisional response must not be
treated as a validated reference dataset.

## Scientific boundaries

- FIRMS observations are thermal anomalies detected by satellite. They are not
  confirmed fires and their association with an observed land change remains
  uncertain.
- dNBR is descriptive spectral evidence. It does not confirm fire, encode
  severity, or establish ground truth.
- A visible change may be caused by agriculture or harvest, soil exposure,
  vegetation phenology, moisture or flooding, cloud or haze, shadow or
  atmosphere, water, urban or construction activity, or a mixture of causes.
- The reviewer must record ambiguity when the image evidence does not support a
  more specific observation. A competing explanation is evidence to preserve,
  not a reason to force a negative response.
- Do not define or emit `significant_burn`, a severity threshold, a causal
  conclusion, a model score, or a suggested class.
- Do not consult external tables, rankings, confidence values, model outputs,
  or other information that is not visible in the supplied panel.

## Pass A — multispectral evidence

Review only the multispectral panel for the case. Consider RGB pre/post,
false-color SWIR pre/post, the descriptive dNBR views, the mask, the FIRMS
overlay, dates, temporal lead/lag, visual metrics, scale, AOI, cloud screening,
stretch, palettes, and warnings shown on the panel.

Return exactly these four observations and one required note:

- `pass_a_visible_burn_scar`
- `pass_a_scar_confidence`
- `pass_a_event_association`
- `pass_a_competing_land_change`
- `pass_a_notes`

The note must explain the visual basis or the unresolved ambiguity. Do not use
the numeric dNBR value as a class rule. Do not infer a causal fire conclusion
from a single visual cue.

Allowed Pass A values are:

| Field | Allowed values |
|---|---|
| `pass_a_visible_burn_scar` | `yes`, `no`, `ambiguous`, `unobserved` |
| `pass_a_scar_confidence` | `high`, `medium`, `low`, `not_applicable` |
| `pass_a_event_association` | `likely`, `possible`, `unlikely`, `indeterminate` |
| `pass_a_competing_land_change` | `none_visible`, `agriculture_or_harvest`, `soil_exposure`, `vegetation_phenology`, `moisture_or_flooding`, `cloud_or_haze`, `shadow_or_atmosphere`, `water`, `urban_or_construction`, `mixed`, `unknown` |

If the panel cannot be observed, use `unobserved` with
`not_applicable` confidence and explain why in the required note. This is not
the same as a negative observation.

## Pass B — temporal robustness

Pass B starts only after the Pass A JSON is frozen. Review only the temporal
panel for the same case. The external Pass A values are the source of truth
for the Pass A fields in the Pass B response.

Pass B adds exactly these fields:

- `pass_b_mode_agreement`
- `pass_b_confidence_after`
- `pass_b_requires_adjudication`
- `pass_b_notes`

Allowed Pass B values are:

| Field | Allowed values |
|---|---|
| `pass_b_mode_agreement` | `agree`, `partially_agree`, `disagree`, `selected_pair_only`, `window_median_only`, `unavailable` |
| `pass_b_confidence_after` | `high`, `medium`, `low`, `not_applicable` |
| `pass_b_requires_adjudication` | `true`, `false` |

Pass B must not change, remove, reorder, or rewrite any Pass A field. If the
temporal comparison changes the reviewer’s view, preserve the original Pass A
values and describe the reason in `pass_b_notes`. A disagreement between modes
is a descriptive robustness result, not a fire or severity label.

## Ambiguity and audit rules

Every case must appear exactly once. Every required string must be non-empty.
Only the enums in this document are valid; new values are rejected. The JSON
schemas are the machine-readable contract and disallow extra fields.

The calibration is provisional, local to the supplied panels, and separate
from any final scientific dataset. No response is ground truth by virtue of
being complete or internally consistent.

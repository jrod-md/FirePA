# Blind model-assisted calibration

## Publication status

FirePA conducted an exploratory, blind, model-assisted calibration of the
optical review instrument. This work is part of the methodological provenance,
but it did **not** create or alter any released scientific result.

The calibration did not affect the 1,532 audited FIRMS records, the 1,185
processed detections, the 611 `r1500_t06` provisional events, the 30-event
optical cohort, the 28 observable and two unobserved cases, either external
reference result, any frozen figure, or any `site-data/` artifact.

No calibration response became a human observation, ground truth, training
target, confirmed-fire label, severity class, or model-performance estimate.
No predictive model was trained.

## Why the calibration was performed

The purpose was to test whether a proposed two-pass review contract preserved
ambiguity, confidence, temporal robustness, observation limitations, and
competing land-surface explanations before any formal human review. Formal
human review was subsequently deferred because a qualified reviewer was not
available; its released observation count remains zero.

The calibration used seven anonymized optical cases. Pass A examined the
selected multispectral pre/post evidence. Pass B examined a separate temporal
robustness view and was required to preserve the Pass A fields. Responses were
recorded as `provisional_pseudolabel`, not as scientific labels.

The structured review axes were:

- visible burn-scar observation and ordinal confidence;
- possible event association;
- competing land-surface change;
- observation limitation;
- agreement between `selected_pair` and `window_median` evidence;
- confidence after the temporal comparison; and
- a provisional request for adjudication.

The protocol prohibited causal fire conclusions, dNBR severity thresholds,
`significant_burn`, ground-truth claims, and model scores.

## Exploratory R1 result

The first round contained seven cases and one model-assisted reviewer reported
as `GPT-5.6 Thinking`. The imported contract recorded seven provisional rows,
zero final labels, and no ground truth.

Aggregate observations were:

| Field | Distribution |
|---|---|
| Visible burn-scar observation | yes 3; no 1; ambiguous 3 |
| Pass A confidence | high 1; medium 3; low 3 |
| Event association | likely 3; possible 1; unlikely 1; indeterminate 2 |
| Pass B mode agreement | agree 1; partially agree 6; disagree 0 |
| Pass B confidence | high 1; medium 4; low 2 |

Five cases recorded a competing explanation. Deterministic post-review triage
identified `CASE-003`, `CASE-005`, and `CASE-006` for adjudication, and
`CASE-003` through `CASE-006` for specialist review. These were administrative
recommendations only and were never promoted into the frozen study.

## Independent control result

A later control used the same seven anonymized cases with two independently
returned model-assisted reviews, reported as `GPT-5.6 Thinking` and
`GPT-5.5 Thinking`. The comparison contained 14 provisional rows.

Exact agreement across the seven cases was 6/7 for visible-scar observation,
3/7 for Pass A confidence, 4/7 for event association, 4/7 for competing
land-surface change, 7/7 for observation limitation, 4/7 for temporal-mode
agreement, 4/7 for Pass B confidence, and 6/7 for the explicit adjudication
request. There was no case with exact agreement across every structured field.

Agreement between models from the same family is not independence from a
reference standard and is not an accuracy measure. The disagreement pattern
supported the decision to preserve uncertainty and to avoid treating the
calibration as validation.

## Scientific interpretation

The calibration was exploratory. It informed the wording and separation of
review fields and reinforced these limitations:

- observation, association, and causal attribution must remain separate;
- `ambiguous`, `indeterminate`, and `unobserved` must not be forced into binary
  classes;
- confidence is ordinal, not a calibrated probability;
- agreement between two model responses is not ground truth;
- optical change may reflect atmosphere, agriculture, soil, moisture,
  phenology, water, construction, or mixed causes; and
- formal human adjudication would be required before any scientific label.

It did not supply evidence for the released event counts or case conclusions.

## Public and private reproducibility boundary

This public repository retains this aggregate methodological record and the
generic human/formal-review contracts. It does not redistribute the case-to-
event mapping, model response JSON, SQLite review store, source panels,
Sentinel-2 rasters, local review packages, or reviewer workflow checkpoints.
Those artifacts may contain private identifiers or depend on protected inputs.

Consequently, a clean public clone can audit the stated method, aggregate
results, limitations, and non-effect on the frozen release, but it cannot
re-execute the historical model-assisted rounds. The public release verifier
does not depend on those rounds.

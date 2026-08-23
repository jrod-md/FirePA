# AI blind review instructions — Pass A

Review the seven multispectral panels in randomized order. Do not open or use
temporal panels during this pass. Use only what is visible in the supplied
panel; do not consult external records or hidden metadata.

Return one strict JSON object matching
`AI_REVIEW_OUTPUT_SCHEMA_PASS_A.json`:

- use the exact root constants required by the schema;
- include exactly seven review objects;
- include each `CASE-001` through `CASE-007` exactly once;
- populate every required field with a non-empty value from its enum;
- write a concise, non-empty `pass_a_notes` value for every case;
- include no extra keys, source identifiers, paths, scores, or suggested
  classes.

Preserve uncertainty. `dNBR` is descriptive spectral evidence and does not by
itself confirm fire or severity. Do not define a scientific burn threshold or
turn the response into ground truth.

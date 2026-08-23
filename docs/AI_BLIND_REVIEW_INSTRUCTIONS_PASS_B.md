# AI blind review instructions — Pass B

Receive the frozen Pass A JSON and the seven temporal robustness panels. Review
the temporal panel for each matching case only after Pass A is complete.

Return one strict JSON object matching
`AI_REVIEW_OUTPUT_SCHEMA_PASS_B.json`:

- copy every Pass A field value exactly, including its notes;
- include the same seven case identifiers exactly once;
- add only the four Pass B fields defined by the schema;
- populate every required field with a non-empty value from its enum;
- use a boolean for `pass_b_requires_adjudication`;
- include no extra keys, source identifiers, paths, scores, or suggested
  classes.

Pass B is a robustness comparison. It must not silently revise Pass A. If the
temporal evidence creates a dispute, keep Pass A unchanged, set the requested
adjudication value, and explain the dispute in `pass_b_notes`.

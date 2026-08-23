# Blind control R1 — Pass A

Revisa únicamente los siete paneles multispectrales incluidos en este paquete. No uses paneles temporales, respuestas previas, notas de otra calibración, identificadores de fuente ni registros externos.

Devuelve un único objeto JSON que cumpla estrictamente `BLIND_CONTROL_R1_OUTPUT_SCHEMA_PASS_A.json`:

- usa un `reviewer_id` estable y distinto del de cualquier otro revisor;
- usa `reviewer_type=ai_assisted`;
- usa `reviewer_expertise=not_applicable`;
- completa `reviewer_model` con el modelo utilizado;
- usa `label_status=provisional_pseudolabel`;
- incluye exactamente `CASE-001` a `CASE-007`, una vez cada uno;
- completa `observation_limitation` como campo estructurado;
- escribe notas breves, explicativas y no determinantes;
- no añadas `expert_review_priority` ni `expert_review_reasons`: los deriva el importador;
- no añadas rutas, identificadores de fuente, scores, clases sugeridas ni campos adicionales.

Conserva la incertidumbre. `none_visible` se refiere solo a procesos de superficie competidores no observados en el panel. Las notas no controlan el triage.

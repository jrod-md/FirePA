# Blind control R1 — Pass B

Completa Pass B solo después de terminar tu propio Pass A. Usa los siete paneles temporales del paquete y tu propio Pass A; no uses la respuesta de otro revisor ni resultados de la calibración anterior.

Devuelve un único objeto JSON que cumpla estrictamente `BLIND_CONTROL_R1_OUTPUT_SCHEMA_PASS_B.json`:

- conserva exactamente todos los campos y valores de tu Pass A, incluidas las notas y `observation_limitation`;
- usa el mismo `reviewer_id`, `reviewer_type`, `reviewer_expertise`, `reviewer_model` y `label_status` que en Pass A;
- incluye exactamente `CASE-001` a `CASE-007`, una vez cada uno;
- añade únicamente los cuatro campos Pass B del schema;
- usa `pass_b_requires_adjudication` como booleano;
- no añadas `expert_review_priority` ni `expert_review_reasons`: los deriva el importador;
- no añadas rutas, identificadores de fuente, scores, clases sugeridas ni campos adicionales.

Pass B comprueba robustez, no confirma una clase. Si aparece una discrepancia, conserva Pass A y descríbela en `pass_b_notes`. Un acuerdo entre pasadas o entre revisores no es una referencia científica.

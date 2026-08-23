# Memo de decisión — protocolo de etiquetado v1

**Fecha:** 2026-07-28
**Base revisada:** `f302139`
**Decisión:** revisión mínima y freeze inmediato
**Resultado:** `docs/LABELING_PROTOCOL_v1.md` congelado

## Razón de la decisión

El control ciego R1 no mostró un fallo estructural que impida preparar la
revisión de los 28 eventos. Mostró seis acuerdos de siete en la observación
visible, un desacuerdo material en CASE-007, ambigüedad compartida en CASE-005
y un patrón agrícola compartido en CASE-006. También mostró que el triage
original agrupaba en exceso confusores, limitaciones y señales de revisión.

La decisión no autoriza otra ronda ciega IA ni interpreta el acuerdo como
exactitud, sensibilidad, especificidad o referencia externa.

## Cambios aceptados

1. El triage formal ya no analiza notas ni busca palabras clave.
2. `recommended` y `required` son prioridades expertas distintas.
3. La comparación interrevisor conserva acuerdos exactos y desacuerdos
   materiales/no materiales sin crear consenso.
4. La procedencia humana e IA queda separada y validada por constraints.
5. `review_complete` se define como cierre administrativo condicionado a
   revisiones, comparación y acciones bloqueantes; no es una decisión
   científica.
6. Se normalizan las limitaciones formales `shadow`,
   `insufficient_temporal_separation` y `other`, documentando la
   correspondencia histórica.

## Cambios rechazados

- No se ejecutó otra comparación IA.
- No se añadió un score, ranking, clase, modelo o variable ambiental.
- No se creó una regla numérica para convertir observaciones en una etiqueta.
- No se cambiaron escenas, AOI, política Sentinel-2, dNBR, clustering ni la
  cohorte.
- No se reescribieron las respuestas ni la SQLite histórica de R1.

## Riesgos residuales

La revisión humana puede compartir sesgos de lectura, los 28 eventos son una
cohorte pequeña y los paneles dNBR son evidencia descriptiva. Los dos
`unobserved` no se comparan como negativos. Un experto no puede recuperar
información óptica ausente. La independencia depende del blindaje de aliases,
slots y metadata, que debe auditarse de nuevo antes de iniciar la revisión.

## Criterio de freeze

El contrato se considera congelado porque los cinco cambios aprobados están
representados en el documento v1, tienen enums y reason codes explícitos,
preservan el candidato histórico y separan observación, triage y cierre
administrativo. Un cambio semántico futuro requiere una nueva versión.

## Afirmaciones que siguen prohibidas

El acuerdo, el cierre administrativo, la revisión experta o el dNBR no se
presentan como incendio confirmado, severidad, ground truth, clase de
entrenamiento, predicción, utilidad operativa o `significant_burn`. No se
realizan afirmaciones institucionales ni se incorporan datos de 2026.

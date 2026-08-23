# Diseño de revisión formal de 28 eventos

**Ronda:** `formal_review_28`
**Protocolo:** `labeling-protocol-v1`
**Estado de esta entrega:** preparada, no iniciada

## Cohorte y asignaciones

La fuente administrativa es la cola local existente de 28 eventos observables
del piloto `r1500_t06`, más el registro separado de 2 eventos `unobserved`.
No se inventan identificadores ni se incorporan eventos fuera de la cola.

Cada uno de los 28 observables recibe dos asignaciones humanas independientes:
`HUMAN_SLOT_A` y `HUMAN_SLOT_B`, para un total de 56 asignaciones. Los slots
no son personas hasta que un administrador los vincula a perfiles humanos
reales y entrenados. La IA no ocupa ninguno de los dos slots.

## Blindaje y orden

Cada slot usa una clave SHA-256 canónica de `round_id`, versión del protocolo,
slot, semilla privada y `event_id`. La semilla se genera o suministra fuera de
Git, persiste únicamente en el área local ignorada y su hash aparece en el
manifest privado. Cada orden y alias se regenera exactamente con los mismos
inputs; un cambio de input visual produce conflicto explícito.

Los manifests públicos contienen solo aliases, orden, referencias abstractas,
hashes visuales, versión de protocolo y versión de herramienta. El join alias
con `event_id` y las rutas reales queda en `outputs/human_review/formal_review_28/private/`.
No se copian ni recomprimen paneles.

La UI muestra el alias y el panel local, nunca el `event_id`, FRP, confianza
FIRMS, ranking, score, clase, severidad, otra revisión, revisión IA o triage
futuro.

## Flujo de dos pasadas

Pass A muestra únicamente la evidencia multiespectral disponible y captura los
campos observacionales v1. El payload se normaliza, se hashea y se bloquea.
Pass B se habilita únicamente después del bloqueo y conserva Pass A mientras
registra la comparación entre `selected_pair` y `window_median`, cambio de
confianza y solicitud estructurada de adjudicación.

La preparación actual no genera ni sustituye un raster `window_median` para
los 28 eventos. Por eso la UI mantiene Pass B bloqueada hasta que exista una
referencia temporal local trazable; nunca muestra el panel `selected_pair`
como si fuera el otro modo.

Una enmienda excepcional es append-only, exige razón y conserva el valor
original. Una reanudación no reabre Pass A ni duplica Pass B o auditoría.

## Triage, comparación y cierre

La comparación se genera cuando las dos asignaciones humanas están completas.
Guarda acuerdos exactos, desacuerdos materiales/no materiales y razones, sin
consenso. El triage usa campos estructurados y la comparación, nunca notas.

`needs_adjudication` se activa por ambigüedad, confianza baja, asociación
indeterminada, desacuerdo modal, solicitud estructurada, desacuerdo visible o
desacuerdo material de asociación. `recommended` puede surgir por confusores
estructurados, cambio de confianza o desacuerdo no material persistente.
`required` solo aparece después de una adjudicación estructurada con
desacuerdo material persistente y `specialist_question_code`.

El cierre `review_complete` exige Pass A y B válidas de ambos revisores,
comparación y resolución de toda acción bloqueante. Puede conservar
`ambiguous` o `indeterminate` y no es una decisión científica.

## Adjudicación y experto

La adjudicación, si se habilita posteriormente, mantiene las dos respuestas
originales, el motivo y la resolución estructurada. La revisión experta es una
fila con perfil y pregunta propios. Ninguna de las dos se ejecutó en esta
preparación y no se generan valores vacíos que aparenten resultados.

## `unobserved`

Los dos eventos sin pareja utilizable permanecen en `formal_unobserved_events`
y en el manifest administrativo separado. No entran en asignaciones, Pass A,
Pass B, comparación, triage de cicatriz ni futuros exports de observación como
`no`.

## Artefactos y reanudación

La preparación produce el esquema SQLite migrado, dos manifests públicos,
un mapa privado, hash de semilla, manifests de inputs, asignaciones y un
resumen de estado `prepared/not_started`. La operación es idempotente:
identidad y hash iguales son no-op; una identidad con hash diferente falla;
las asignaciones no se duplican.

La revisión real futura debe empezar únicamente después de vincular cada slot
a un perfil humano. Este documento no autoriza a ejecutarla.

## Estado administrativo endurecido

`prepared` y `not_started` describen una preparación, no una autorización de
ejecución. La ronda actual mantiene `execution_authorized=false`; no hay
perfiles registrados, slots vinculados, Pass A, Pass B, pairwise,
adjudicaciones ni revisiones expertas. La autorización futura debe ser una
acción administrativa explícita y validada, separada de la preparación.

El hash antiguo registrado en el primer paquete fue
`57e7b75dc1e98bf9ec56c9feb52ed99cb4ee43d2e56e00a104046f09e972672d`; el hash
canónico actual de `docs/LABELING_PROTOCOL_v1.md` es
`6710d43c7acb12d24b825c35673a8367c51de96ae8268a488069bea0c5e3304c`. La
corrección es administrativa, no una nueva versión semántica de
`labeling-protocol-v1`, y usa el código estable
`PROTOCOL_HASH_PREPARATION_RECONCILIATION`. Solo se permite con cero filas de
resultados formales y queda registrada con hashes viejo/nuevo, timestamp,
versión de herramienta y commit base. Semilla, aliases, órdenes e inputs
visuales se comparan antes de escribir.

Los perfiles humanos son insert-only: un registro canónico idéntico es no-op y
una diferencia produce conflicto explícito. Un perfil no puede ocupar ambos
slots; el binding exacto repetido es idempotente. Triggers de SQLite y el
servicio protegen la identidad en el uso normal, pero este diseño no afirma
resistencia frente al propietario directo del archivo SQLite o del filesystem.

El lanzador futuro exige `round_id`, `slot_id` y `profile_id`. No existe un
selector A/B en la interfaz. Tras validar la sesión, el servidor carga solo el
mapa privado específico del slot y no muestra event IDs, semilla, rutas
privadas, el otro slot, FRP, score ni joins completos. El token de sesión es
aleatorio, local, no persistido y no se imprime.

Pass A es insert-once; una enmienda exige razón específica, conserva el payload
original exacto y registra hashes del payload anterior y corregido. Un
verificador read-only recalcula hashes, revisa amendments, huérfanos y
artefactos administrativos. Pass B es insert-once en este contrato y exige dos
referencias congeladas distintas: `selected_pair` y `window_median`, con ruta
normalizada, hash, manifest, modo y proveniencia. Como no existe
`window_median` local para esta cohorte, Pass B permanece bloqueada y no se
crea ninguna fila ficticia.

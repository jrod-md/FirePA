# Herramienta local de revisión humana

## Propósito y límite

La herramienta implementa una ronda local de calibración ciega sobre los siete
paneles Level 2 ya congelados. Es una herramienta interna de ciencia para
registrar observaciones humanas y ambigüedades; no es un dashboard público, no
es un sistema de predicción y no convierte los resultados en una etiqueta del
dataset.

La ronda formal `formal_review_28` usa el mismo principio local, pero un
contrato y namespace SQLite separados (`labeling-protocol-v1`). Su preparación
está completa y su ejecución no ha comenzado: 28 eventos observables, 2
`unobserved` separados y 56 asignaciones humanas vacías.

La ejecución usa únicamente `sqlite3` de la biblioteca estándar para el estado
y Streamlit como dependencia de desarrollo para la interfaz. No consulta
Earth Engine, no descarga escenas, no lee FRP ni scores auxiliares y no
incorpora datos posteriores al periodo de la cohorte. Los dos eventos sin
observabilidad permanecen en una tabla separada y no son negativos.

## Archivos

- `scripts/run_human_review_app.py`: entry point de Streamlit.
- `src/fuegopa/human_review_app.py`: interfaz local y flujo de dos pasadas.
- `src/fuegopa/human_review_schema.py`: vocabularios, rutas congeladas y DDL.
- `src/fuegopa/human_review_store.py`: inicialización idempotente, transacciones,
  auditoría y exportaciones.
- `src/fuegopa/human_review_migrations.py`: migraciones acumulativas 1–3 y
  tablas formales no destructivas.
- `src/fuegopa/formal_review.py`: contrato v1, triage estructurado,
  comparación interrevisor, preparación idempotente y persistencia formal.
- `src/fuegopa/formal_review_app.py`: interfaz local por slot para la ronda
  formal; no permite revisar un slot sin perfil humano vinculado.
- `scripts/prepare_formal_review_28.py`: genera manifests y asignaciones vacías
  sin ejecutar revisiones.
- `scripts/bind_formal_reviewer.py`: vincula explícitamente un perfil humano
  real antes de iniciar una futura revisión.
- `scripts/validate_human_review.py`: validador existente, ampliado con el modo
  explícito `--validate-tool-export`.
- `tests/test_human_review_store.py`: persistencia, coherencia, auditoría,
  exportaciones e integridad de paneles.
- `tests/test_human_review_app_contract.py`: contrato de interfaz y restricciones.

Los siguientes artefactos son locales e ignorados por Git:

- `outputs/human_review/firepa_human_review.sqlite3`;
- `outputs/human_review/exports/`;
- `outputs/human_review/audit/`.
- `outputs/human_review/formal_review_28/`, incluidos la semilla privada, el
  mapa alias-evento, manifests y paquetes de los dos slots.

## Esquema SQLite

La base contiene las tablas `review_rounds`, `review_items`, `reviews`,
`audit_log` y `unobserved_events`.

- `review_rounds` conserva ronda, protocolo, quicklook, semilla, timestamp y
  estado.
- `review_items` conserva el orden ciego, el `event_id`, las dos rutas de panel
  y el estado de observabilidad. Tiene una restricción de unicidad por ronda y
  orden; triggers impiden editar o borrar el orden congelado.
- `reviews` usa la clave primaria `(round_id, event_id, reviewer_id)`, por lo
  que no puede haber más de una revisión activa para esa combinación. Guarda
  por separado todas las columnas `pass_a_*` y `pass_b_*`, sus timestamps y
  revisiones, estado administrativo y notas.
- `audit_log` registra cada cambio de campo con valor anterior, valor nuevo,
  razón y timestamp. Triggers SQLite rechazan `UPDATE` y `DELETE`.
- `unobserved_events` conserva los dos casos no observables fuera de la cola
  revisable, con su razón y protocolo. No se copian a `review_items`.

Los códigos internos son estables y se almacenan tal cual; las frases que se
muestran en los dropdowns son únicamente etiquetas de UI. SQLite y el store
rechazan códigos fuera de los enums. La coherencia exige `not_applicable` para
una observación `unobserved`, una razón explícita para excluirla y notas cuando
el estado es `needs_adjudication`.

## Flujo A/B

1. La primera ejecución lee la cola `calibration_round1_blinded.csv`, el
   manifest y `unobserved_events.csv`; valida rutas, versiones y el orden
   congelado, y luego inserta la ronda sin duplicarla. La inicialización se
   puede repetir.
2. El revisor introduce un `Reviewer ID`. Antes de guardar Pass A solo se
   muestra el panel multiespectral.
3. Pass A exige cuatro códigos de observación y notas opcionales. Al guardar,
   sus campos quedan bloqueados. `Amend Pass A` es la única ruta para cambiar
   una decisión, exige razón, incrementa la revisión y conserva el valor
   anterior en `audit_log`.
4. Solo después de guardar Pass A se revela el panel temporal. Pass B registra
   concordancia de modos, confianza posterior, necesidad de adjudicación y
   notas. Nunca actualiza las columnas de Pass A.
5. Se puede navegar únicamente por `randomized_order`, ver el progreso y
   exportar una instantánea. La interfaz no ofrece ranking, score, clase o
   sugerencia de respuesta.

La advertencia permanente de la aplicación es: “dNBR es evidencia espectral
descriptiva; no confirma por sí solo un incendio”.

## Ronda formal v1 preparada

La preparación formal se ejecuta sin red con:

```powershell
conda activate fuegopa
python scripts/prepare_formal_review_28.py
```

La primera ejecución valida la cola existente, crea 28 asignaciones por cada
uno de `HUMAN_SLOT_A` y `HUMAN_SLOT_B`, registra hashes e inserta únicamente
el estado administrativo `prepared/not_started`. Los manifests públicos no
contienen el join con el evento ni metadata de selección; el join privado queda
fuera de Git. Un rerun con la misma semilla e inputs es idempotente y un cambio
de bytes genera conflicto explícito.

Antes de iniciar una revisión futura, un administrador debe vincular cada slot
a una persona real, por ejemplo:

```powershell
python scripts/bind_formal_reviewer.py --slot-id HUMAN_SLOT_A `
  --profile-id <perfil-humano-real> --expertise protocol_trained_reviewer
```

La aplicación formal se abre explícitamente, manteniendo la aplicación
histórica disponible:

```powershell
streamlit run scripts/run_human_review_app.py -- --formal-round
```

La aplicación formal muestra aliases, exige Pass A antes de Pass B, bloquea
Pass A en persistencia, conserva las observaciones originales y no ejecuta
triage, adjudicación o revisión experta durante la preparación.

## Instalación y ejecución

La dependencia de UI está fijada en `pyproject.toml` como
`streamlit==1.41.1` dentro del extra `dev`; no forma parte del runtime
científico. En el entorno de trabajo:

```powershell
conda activate fuegopa
python -m pip install -e ".[dev]"
streamlit run scripts/run_human_review_app.py --server.address 127.0.0.1
```

La variante corta solicitada también es válida:

```powershell
conda activate fuegopa
streamlit run scripts/run_human_review_app.py
```

El servidor debe permanecer local; no se configura un puerto público ni se
hace push o despliegue desde este flujo.

## Exportaciones

Para un revisor `reviewer_id`, la aplicación crea:

- `outputs/human_review/exports/calibration_round1_<reviewer_id>_snapshot.csv`:
  exportación normalizada, con columnas separadas para Pass A y Pass B,
  timestamps, revisiones y estado.
- `outputs/human_review/exports/calibration_round1_<reviewer_id>_snapshot.json`:
  la misma instantánea con metadatos de ronda y esquema.
- `outputs/human_review/audit/calibration_round1_<reviewer_id>_audit.jsonl`:
  historial append-only ordenado por `audit_id`.
- `outputs/human_review/exports/calibration_round1_<reviewer_id>_validator.csv`:
  proyección de compatibilidad con el CSV histórico; no sustituye la
  exportación normalizada.

El export normalizado se comprueba sin mutarlo con:

```powershell
python scripts/validate_human_review.py --validate-tool-export `
  outputs/human_review/exports/calibration_round1_<reviewer_id>_snapshot.csv
```

La validación anterior de la cola continúa disponible:

```powershell
python scripts/validate_human_review.py --check-empty-calibration
```

## Verificación y restricciones

La suite del repositorio debe ejecutarse en `fuegopa` con
`powershell -ExecutionPolicy Bypass -File scripts/run_tests.ps1`. Las pruebas
de esta entrega comprueban inicialización idempotente, siete items y orden,
enums, bloqueo y enmienda A, compuerta B, auditoría append-only, timestamps,
revisiones, adjudicación, exportaciones CSV/JSON/JSONL, compatibilidad con el
validador, rutas de panel, separación de los dos no observables, ausencia de
campos auxiliares y conservación de hashes de artefactos de prueba.

No se deben versionar la base SQLite, las exportaciones, el audit log, PNG,
TIFF, outputs científicos, credenciales ni datos derivados. Esta herramienta
no define una etiqueta, no agrega una columna de referencia, no altera
métricas o rasters y no abre una nueva fase de Earth Engine.

## Contrato administrativo actualizado

La ronda formal está `prepared/not_started` con
`execution_authorized=false`. Preparar una ronda no autoriza una sesión ni
registra una observación. La reconciliación del hash anterior
`57e7b75dc1e98bf9ec56c9feb52ed99cb4ee43d2e56e00a104046f09e972672d` al hash
canónico actual
`6710d43c7acb12d24b825c35673a8367c51de96ae8268a488069bea0c5e3304c` fue una
operación administrativa auditada con el código
`PROTOCOL_HASH_PREPARATION_RECONCILIATION`; no cambia la semántica de
`labeling-protocol-v1`.

Antes de cualquier futura ejecución deben existir perfiles humanos reales,
uno por slot. `register_human_profile` es insert-only: una repetición idéntica
es no-op y una diferencia falla. El mismo perfil no puede ocupar A y B. El
lanzador formal no acepta selección libre:

```powershell
streamlit run scripts/run_human_review_app.py -- `
  --formal-round `
  --round-id formal_review_28 `
  --slot-id HUMAN_SLOT_A `
  --profile-id <perfil-humano-real>
```

El servidor valida estado de ronda, autorización, perfil humano, slot
solicitado y ausencia de binding en el otro slot antes de cargar únicamente
`private/<slot>/assignment_map.json`. La separación es para un entorno local
supervisado; no protege contra administración directa del filesystem o SQLite.
El nonce de sesión se genera en memoria, no se registra y no se persiste.

`scripts/verify_formal_review_28.py` es read-only y debe ejecutarse antes de
autorizar una futura sesión. Pass A no permite actualizaciones genéricas: una
enmienda conserva payload y hashes originales. Pass B permanece bloqueada en
esta cohorte porque no existe una referencia `window_median` congelada; el
backend rechaza referencias ausentes, iguales, sin hash, con modo incorrecto,
con asignación incompatible o con archivo modificado.

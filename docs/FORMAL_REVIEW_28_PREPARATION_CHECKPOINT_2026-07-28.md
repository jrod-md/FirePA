# Checkpoint — preparación formal de revisión de 28 eventos

**Fecha:** 2026-07-28
**Base Git verificado antes de esta corrección:** `fbd38466b6dbc277257d6c6b3c58cbbaf1712b33`
**`base_head` histórico conservado en la identidad de inputs:** `f302139`
**Ronda:** `formal_review_28`
**Estado:** `prepared`, `not_started`, `execution_authorized=false`

Este checkpoint documenta infraestructura y manifests administrativos. No
ejecuta revisiones, adjudicaciones, revisión experta, revisión IA ni nuevas
observaciones.

## Conteos verificados

- Piloto completo: 30 eventos.
- Eventos observables: 28.
- Eventos `unobserved`: 2, en registro separado.
- Asignaciones humanas preparadas: 56 (28 por slot).
- Revisiones formales ejecutadas: 0.
- Perfiles humanos registrados/vinculados: 0 / 0.
- Pass A: 0; Pass B: 0; `window_median`: 0 de 28.
- Pairwise: 0; triage: 0; adjudicaciones: 0; revisión experta: 0.
- Nuevos pseudolabels IA: 0.

La cola y sus paneles existentes fueron leídos con UTF-8. La cola contiene 28
IDs únicos, el registro separado contiene 2 IDs únicos disjuntos, las 28 rutas
visuales existen y no aparece 2026 en las entradas verificadas.

## Versiones y migraciones

- Protocolo: `labeling-protocol-v1`.
- Schema: `firepa-formal-review-v1`.
- Herramienta: `firepa-human-review-tool-v2`.
- Migración acumulativa vigente: `4`.
- Migración 1: baseline del schema histórico.
- Migración 2: tablas formales separadas, constraints, claves únicas,
  foreign keys, auditoría append-only y amendments append-only.
- Migración 3: triggers de integridad para exigir Pass A antes de Pass B,
  exigir ambas Pass B antes de pairwise y bloquear modificaciones/borrados de
  Pass A sin amendment.
- Migración 4: autorización explícita de ejecución, perfiles append-only,
  binding único por ronda, identidad de ronda/asignaciones inmutable,
  referencias Pass B trazables, reconciliación protocolaria auditada y hashes
  de artefactos administrativos.

La migración no elimina ni reescribe filas de calibración o control. La
SQLite queda local e ignorada por Git. La reconciliación del hash obsoleto se
ejecutó únicamente con cero resultados formales y una bandera administrativa
explícita; no es una nueva versión semántica del protocolo.

## Integridad y blindaje

El paquete público de cada slot contiene aliases, orden, hashes visuales,
versiones y referencias abstractas; no contiene el join con `event_id` ni
metadata de selección. El mapa privado y la semilla quedan en `outputs/` y no
se versionan. El servicio no convierte perfiles IA en humanos ni actualiza
perfiles existentes: los perfiles son inmutables y los slots siguen sin
vincular.

Pass A tiene hash y `locked_at`; Pass B depende de Pass A; una enmienda es
append-only. La ronda preparada no contiene filas Pass A, Pass B, pairwise,
triage, adjudication o expert review.

La aplicación futura recibe `round_id`, `slot_id` y `profile_id` desde el
lanzador; no ofrece selector A/B y carga únicamente el mapa privado del slot
solicitado. Esta separación está diseñada para un entorno local supervisado y
no pretende resistir a quien controle directamente el filesystem o SQLite.

Los 28 paquetes actuales referencian únicamente los paneles seleccionados ya
existentes. No se fabricó un panel `window_median`; la aplicación bloqueará
Pass B hasta disponer de una referencia temporal local trazable, evitando
mezclar modos.

## Hashes

Los valores concretos se generaron localmente por
`scripts/prepare_formal_review_28.py` y se resumen también en
`outputs/human_review/formal_review_28/preparation_summary.json`, fuera de
Git. La semilla se registra únicamente por hash.

| Artefacto | SHA-256 |
|---|---|
| Hash protocolario obsoleto registrado | `57e7b75dc1e98bf9ec56c9feb52ed99cb4ee43d2e56e00a104046f09e972672d` |
| `LABELING_PROTOCOL_v1.md` canónico actual | `6710d43c7acb12d24b825c35673a8367c51de96ae8268a488069bea0c5e3304c` |
| Manifest público `HUMAN_SLOT_A` antes | `60c0891e0adc857146522210c030ac1d622cf371e84407a2f903d363abf1b62e` |
| Manifest público `HUMAN_SLOT_B` antes | `8dabbb948a8f46d48bbbb6a26cf4731da9b99232a3507d636a9cbab8b239879c` |
| Manifest público `HUMAN_SLOT_A` después | `3e5c5ea585596e29d53cf7564418d62d9d229b72dada27db05b81da82d0fa7ac` |
| Manifest público `HUMAN_SLOT_B` después | `c770f7e2b6a3072936827e48a2669eebe3f317cba9fc58517750a7506be4c134` |
| Input manifest combinado | `0b8bea8e8be68380f421e04283a95296d98cbf38829f908006f99f767a841155` |
| Manifest de fuente | `0a3fae792795ceed771f017e00da7c40d107db0c65986b996787fb01ca308d4f` |
| Semilla privada (solo hash) | `3ce94ffaa4c04ade0f8fdcb64eb41e0e543ce2d6a37f88f51edda4138f205c53` |

La reconciliación quedó registrada en SQLite con
`old_protocol_sha256=57e7b75d…`,
`new_protocol_sha256=6710d43c…`,
`reason_code=PROTOCOL_HASH_PREPARATION_RECONCILIATION`, timestamp UTC,
`tool_version=firepa-human-review-tool-v2` y `base_commit=f302139`. La semilla,
los 56 `assignment_id`, aliases, órdenes aleatorizados y hashes visuales se
conservaron; solo se actualizaron el hash protocolario y los artefactos
administrativos derivados. El hash actual previo del resumen, que no coincidía
con su auditoría histórica pero conservaba identidad lógica y cero resultados,
quedó registrado en la auditoría de reconciliación antes de reemplazarse de
forma controlada.

## Artefactos científicos protegidos

La preparación no consulta Earth Engine, no descarga datos, no modifica
paneles, PNG, SVG, TIFF, rasters, métricas dNBR, inventarios Sentinel-2,
selección de escenas, clustering, cohorte piloto ni manifests científicos.
Los hashes científicos registrados en los checkpoints previos deben permanecer
idénticos. Los manifests de esta ronda son administrativos y no sustituyen
los manifests científicos.

Verificación local posterior a la preparación mediante la integridad del
bundle activo:

| Índice | Antes | Después | Estado |
|---|---|---|---|
| Bundle científico, 179 entradas | `249856a90cff60ee730589271aae622eefd61e0323cd18248694426eeb91e9fa` | `249856a90cff60ee730589271aae622eefd61e0323cd18248694426eeb91e9fa` | igual |
| Índice visual v1, 231 entradas | `ce822c9c05769adbb240672e5143a8f72525fa1ba04ecc7f3a2fa7e9358cf401` | `ce822c9c05769adbb240672e5143a8f72525fa1ba04ecc7f3a2fa7e9358cf401` | igual |

No se modificaron paneles, PNG, SVG, TIFF, rasters, métricas dNBR,
inventarios Sentinel-2, selección de escenas, clustering, FIRMS ni cohorte.

## Pruebas y Git

La suite base ejecutada antes de esta fase fue `248 passed in 535.53s`.
Después de los cambios, `powershell -ExecutionPolicy Bypass -File
scripts/run_tests.ps1`, ejecutado con Python 3.12 del entorno `fuegopa`, se
reporta como ejecución separada: `262 passed in 510.14s (0:08:30)`. Las 14 pruebas
nuevas están en `tests/test_formal_review_integrity.py`; también se ajustó la
prueba formal histórica para exigir autorización explícita y mantener Pass B
bloqueada sin `window_median`. Las pruebas nuevas cubren reconciliación
administrativa, perfiles append-only, binding único, autorización, aislamiento
por slot, referencias Pass B, artefactos y verificador read-only. La
verificación `git diff --check` no reportó errores.
Los ocho untracked preexistentes del preflight permanecen sin stage y no
forman parte de esta preparación.

## Paquetes locales

Se generaron, sin copiar imágenes:

- `outputs/human_review/formal_review_28/human_slot_a/manifest.json` —
  `3e5c5ea585596e29d53cf7564418d62d9d229b72dada27db05b81da82d0fa7ac`.
- `outputs/human_review/formal_review_28/human_slot_b/manifest.json` —
  `c770f7e2b6a3072936827e48a2669eebe3f317cba9fc58517750a7506be4c134`.

El export administrativo UTF-8 queda en
`outputs/human_review/formal_review_28/exports/` y reporta cero filas de
revisión. La semilla privada y el mapa alias-evento permanecen fuera de Git.

## Comando reproducible

En el entorno del proyecto, con una semilla privada administrada fuera de Git:

```powershell
conda activate fuegopa
python scripts/prepare_formal_review_28.py
```

La reconciliación administrativa explícita, únicamente con cero resultados
formales, se ejecuta con:

```powershell
python scripts/prepare_formal_review_28.py --reconcile-protocol-hash
python scripts/verify_formal_review_28.py
```

La primera ejecución genera una semilla local si no existe, imprime solo su
SHA-256 y deja `formal_review_executed=False`. Un rerun con los mismos inputs y
la misma semilla es idempotente. Un cambio de bytes bajo la misma identidad
debe detenerse con conflicto; no se permite sobrescritura silenciosa.

La aplicación futura requiere primero vincular perfiles humanos reales:

```powershell
python scripts/bind_formal_reviewer.py --slot-id HUMAN_SLOT_A \
  --profile-id <perfil-humano-real> --expertise protocol_trained_reviewer
```

Ese comando no se ejecutó como parte de este checkpoint.

La aplicación futura requiere `--round-id`, `--slot-id` y `--profile-id` en el
lanzador; no tiene selector libre A/B. En el estado actual
`execution_authorized=false`, por lo que la sesión permanece bloqueada.

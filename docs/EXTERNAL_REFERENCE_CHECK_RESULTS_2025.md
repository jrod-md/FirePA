# Resultados `external_reference_check_v1` — 2025

**Ejecución local:** 2026-08-09
**Entrada:** `outputs/clustering/r1500_t06/events.csv`
**Configuración:** `r1500_t06`, sin reclustering
**Clusters verificados:** `611`

Este resultado es exploratorio y descriptivo. Un match es una asociación
espacio-temporal administrativa con una referencia externa proporcionada por
el investigador. No es confirmación de incendio, etiqueta humana ni validación
del pipeline. La procedencia de las dos referencias está ahora registrada en
`references/external_reference_sources_v1.json` como 7 fuentes para 2
incidentes; el registro conserva URLs, fechas, áreas y estados de causa por
fuente sin convertirlos en ground truth.

El registro tiene SHA-256
`6fcd1830a994fda553bc1c1ae7733ffa22823c8360653479d6ed09358f9d9a49`.
Las coordenadas de matching son anclas aproximadas proporcionadas por el
investigador, no coordenadas reclamadas por las fuentes. Las URLs son
procedencia, no inputs del pipeline. El bundle local de resultados se conserva
sin regenerarlo para mantener sus hashes y resultados científicos congelados.

## Resultado por referencia

| Referencia | Ventana temporal | Matches | Distancia más cercana | Seguimiento óptico |
|---|---|---:|---:|---|
| `REFERENCE-001` — Cerro Los Picachos, Olá | 2025-01-15 → 2025-01-17 | **0** | — | No aplica |
| `REFERENCE-002` — Cerro Guacamaya, Penonomé | 2025-01-23 → 2025-01-27 | **6** | **3,076.389 m** | 0/6; fuera de la cohorte de 30 |

Los Picachos no tiene un cluster que satisfaga simultáneamente la distancia de
5 km y la intersección temporal. Esto no demuestra ausencia del incidente.

## Matches de Guacamaya

| Event ID | Distancia (m) | Cluster UTC | n detections | max FRP | mean FRP | sum FRP | Duración (h) | Percentiles max / mean / n / duración |
|---|---:|---|---:|---:|---:|---:|---:|---|
| `event-r1500_t06-e56bcec4b33a68c1` | 4,680.024 | 2025-01-24 06:11 → 06:33 | 2 | 7.69 | 5.85 | 11.70 | 0.367 | 73.81 / 67.59 / 77.58 / 82.49 |
| `event-r1500_t06-62fb92c99f6df90e` | 4,780.810 | 2025-01-24 18:56 → 19:19 | 4 | 5.05 | 4.885 | 19.54 | 0.383 | 53.36 / 55.81 / 93.13 / 97.55 |
| `event-r1500_t06-22d8da58d584e847` | 3,076.389 | 2025-01-25 18:37 → 19:00 | 3 | 13.67 | 10.243 | 30.73 | 0.383 | 89.20 / 88.38 / 87.56 / 97.55 |
| `event-r1500_t06-9d569e8c7453d3ef` | 3,954.607 | 2025-01-26 05:56 → 07:13 | 5 | 7.92 | 4.334 | 21.67 | 1.283 | 74.47 / 46.64 / 96.24 / 98.04 |
| `event-r1500_t06-846683c14a5c5d27` | 3,958.667 | 2025-01-26 18:18 → 18:18 | 1 | 4.49 | 4.49 | 4.49 | 0 | 45.50 / 48.77 / 56.30 / 75.12 |
| `event-r1500_t06-76a3f8054858a779` | 3,337.361 | 2025-01-27 06:55 → 06:55 | 4 | 2.91 | 1.263 | 5.05 | 0 | 23.57 / 7.53 / 93.13 / 75.12 |

Los percentiles son rangos descriptivos contra los 611 clusters completos; no
son accuracy, recall ni una estimación de cobertura.

## Distribución de la cohorte completa

| Métrica | Mediana | IQR | p90 | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| max FRP | 4.79 | 5.02 | 13.94 | 20.90 | 42.25 |
| mean FRP | 4.52 | 4.09 | 11.1467 | 15.65 | 37.365 |
| n detections | 1 | 1 | 4 | 5 | 7 |
| duración (h) | 0 | 0 | 0.3833 | 0.3833 | 1.3 |

La mediana usa `statistics.median`; q25, q75, p90, p95 y p99 usan
nearest-rank. No se ejecutó inferencia estadística con `n=2` referencias.

## Guacamaya: posible fragmentación t06

La ventana de varios días queda representada por **6 clusters**, no por uno.
Las separaciones entre intervalos consecutivos son aproximadamente:

```text
12.383 h, 23.300 h, 10.933 h, 11.083 h, 12.617 h
```

Como todas superan la ventana temporal congelada de 6 h, el resultado es
consistente con una posible fragmentación de una actividad persistentemente
conectada si realmente existió continuidad durante esos huecos. No se cambió
`r1500_t06` y no se etiqueta como bug automáticamente.

## Evidencia óptica

Ninguno de los seis matches pertenece a la cohorte óptica existente de 30
eventos. Por tanto, todos quedan con:

```text
optical_followup_available = false
selected_pair_available = false
window_median_available = false
nbr_dnbr_descriptive_available = false
```

No se generaron rasters, paneles ni nuevos assets. La cohorte óptica no se
amplió.

## Freeze científico y administrativo

- `formal_review_status = deferred`.
- Razón: `QUALIFIED_REVIEWER_UNAVAILABLE`.
- `execution_authorized = false`; `formal_review_28` sigue sin ejecución,
  Pass A y Pass B.
- La infraestructura formal existente, SQLite, blind packages, migraciones,
  tests y assets `window_median` se conservaron.
- `supervised_modeling_gate = deferred`.
- Razón: `NO_DEFENSIBLE_TARGET_WITH_CURRENT_EVIDENCE`.
- No se creó target, `significant_burn` ni modelo; la extracción ambiental no
  está autorizada.
- Las salidas IA existentes permanecen `provisional_pseudolabels`.
- No hubo red ni consultas Earth Engine.

## Cobertura OSINT registrada

| Mes | Artículos localizados |
|---|---:|
| 2025-01 | 6 |
| 2025-02 | 1 |
| 2025-03 | 0 |
| 2025-04 | 0 |

No qualifying articles were located during the manual OSINT search for March or April 2025.
Esto no afirma ausencia de incendios ni de actividad térmica y la búsqueda no
se declara exhaustiva.

## Hashes y reproducibilidad

| Elemento | SHA-256 |
|---|---|
| Tabla de clusters de entrada | `646c70358045c3f774ca3b0b85889c7f851a51559465d3e5ee470c33c7c8e844` |
| Cohorte óptica local | `a9d98281e1b39953d80c91fb61c9f10b5d936a330f1669341079f4da6026b302` |
| `matches.csv` | `3e295a4a884ec7bcadccbc0f76f56f7572881160634f6c36045db540d4e9c5ff` |
| `matches.json` | `f60e35b0fd19cafd6717193251ac2e910a4b9ab41f3f7ef527ca8414dbdfabb2` |
| `reference_summary.csv` | `650ca2012a742edadf127cde9c05596e2292c18e3aa04429ece389d9ec29686f` |
| `cohort_distribution.csv` | `94f81cc1ea11fa8f52181be8a2acc7ad4d0783682cf8d0821afea792bb776626` |
| `report.json` | `677a84acd4920770864e9fa81283d59a8c7577eaf0e7dd2b8d479c526272cd4c` |
| `report.md` | `c080345b834758520ca2efba706bbb6817b7a7ef5f97ed225ac97339fb5ff209` |
| `manifest.json` | `92bec814089fc47b230970a91ab7eed0a2cde6a8225c001ce99187411ad33868` |

El manifest completo de archivos y hashes está en
`outputs/external_reference_check_v1/manifest.json`. Los outputs son locales e
ignorados por Git.

# Blind AI calibration package checkpoint — 2026-07-22

## Scope

This checkpoint records a local-only packaging operation after the initial
human-review-tool commit. No review was performed and no scientific data
or source panel was edited.

- Initial HEAD: `f56bdae9f6c41d587ed3e90d32273b5615350a3f`.
- Commit created: `Add anonymized blind AI calibration package`; the final SHA is verified by Git after commit and is not embedded here to avoid self-reference.
- Frozen cases: `CASE-001`, `CASE-002`, `CASE-003`, `CASE-004`, `CASE-005`, `CASE-006`, `CASE-007`.
- Private mapping: `outputs/human_review/private/calibration_r1_case_map.csv`.
- Pass A package: `outputs/firepa_blind_ai_calibration_r1_pass_a.zip`.
- Pass B package: `outputs/firepa_blind_ai_calibration_r1_pass_b.zip`.

## Anonymization contract

Panels were recomposed from the existing local Level 2 GeoTIFFs, frozen
metrics, scene dates, temporal windows, AOI, masks, palettes, stretches,
legends, overlays, and warnings. The compositor emits `CASE-*`, hides scene
identifiers, omits source paths, and writes sanitized PNG metadata. The
private map stores the exact case-to-source join and pair hashes; it is not
copied into either package or public manifest.

## Integrity before / after

| Protected artifact | Before | After |
|---|---|---|
| scientific bundle index | `249856a90cff60ee730589271aae622eefd61e0323cd18248694426eeb91e9fa` | `249856a90cff60ee730589271aae622eefd61e0323cd18248694426eeb91e9fa` |
| scientific visual index | `ce822c9c05769adbb240672e5143a8f72525fa1ba04ecc7f3a2fa7e9358cf401` | `ce822c9c05769adbb240672e5143a8f72525fa1ba04ecc7f3a2fa7e9358cf401` |
| Level 2 manifest | `9829ca2805e5b14d2819631761a820887221b4e3e6d67df683339cc25b6e4705` | `9829ca2805e5b14d2819631761a820887221b4e3e6d67df683339cc25b6e4705` |
| Level 2 raster index | `b06479e550f560a00c26b9711c0f89e3645d302314547f2f8df8afb950e00a7f` | `b06479e550f560a00c26b9711c0f89e3645d302314547f2f8df8afb950e00a7f` |
| original Level 2 panel index | `b4d880a023f1743213e8f9558f709b332bd0465a82d3a1aa6952fe1689190679` | `b4d880a023f1743213e8f9558f709b332bd0465a82d3a1aa6952fe1689190679` |
| original blind queue | `ac71b6899c5b334d5bd2ce85b53f93e26ba354e47c5cb189b44c9694f80bd221` | `ac71b6899c5b334d5bd2ce85b53f93e26ba354e47c5cb189b44c9694f80bd221` |
| calibration manifest | `5b3ad76b8b8be3d90d93a27a29eee5930a9d9dcb3f3c01345e58b20ec697afe2` | `5b3ad76b8b8be3d90d93a27a29eee5930a9d9dcb3f3c01345e58b20ec697afe2` |

- Protected-input comparison: `pass`.
- Existing SQLite snapshot: `{'status': 'present', 'entry_count': 1, 'index_sha256': '9b58984f0175c7f2517185bc5f577a7fe48993c8cefdbbe424a10495ead812ee'}` -> `{'status': 'present', 'entry_count': 1, 'index_sha256': '9b58984f0175c7f2517185bc5f577a7fe48993c8cefdbbe424a10495ead812ee'}`.

## Validation and tests

- The two package manifests are deterministic and contain only the
  documented twelve files for their pass.
- Checksums cover every package file except the checksum file itself; ZIP members use fixed order and timestamps for reproducibility.
- Validation checks exact case membership, two anonymized panels per
  case, absence of source identifiers and Windows paths in public
  artifacts, pass separation, RGB dimensions, public metadata, pair
  hashes, and byte equality of scientific image regions.
- Test command: `powershell -ExecutionPolicy Bypass -File scripts/run_tests.ps1`.
- Test result: `213 passed in 327.51s`.
- Importer command (dry-run only until external responses exist):
  `python scripts/import_blind_ai_calibration.py --pass-a-json <PATH> --pass-b-json <PATH> --dry-run --report <PATH>`.

## Explicit boundaries

- Reviews performed: zero.
- Scientific/final labels created: zero.
- `significant_burn` defined: zero.
- Earth Engine queries in this packaging operation: zero.
- Future-period data used: zero.
- Pushes: zero.
- Final Git state: the requested source files are committed locally; pre-existing unrelated `data/`, `notebooks/`, and handoff work remains uncommitted and generated outputs remain ignored.

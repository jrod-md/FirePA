from __future__ import annotations

import csv
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from fuegopa.config import Settings  # noqa: E402
from fuegopa.firms import (  # noqa: E402
    REQUIRED_FIELDS,
    RawImmutabilityError,
    SchemaError,
    normalize_csv,
    main,
    parse_acquisition_datetime,
    run_pipeline,
    validate_coordinates,
    validate_required_columns,
)


class FirmsPipelineTests(unittest.TestCase):
    def _settings(self, root: Path, raw_name: str = "input.csv") -> Settings:
        return Settings.from_env(
            project_root=root,
            environ={
                "FUEGOPA_RAW_PATH": f"data/raw/{raw_name}",
                "FUEGOPA_PROCESSED_PATH": "data/processed/normalized.csv",
                "FUEGOPA_REPORT_PATH": "outputs/quality.json",
            },
        )

    def _write_csv(self, path: Path, rows: list[dict[str, str]], headers: list[str] | None = None) -> bytes:
        headers = headers or list(rows[0].keys())
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        return path.read_bytes()

    def _valid_row(self, **overrides: str) -> dict[str, str]:
        row = {
            "latitude": "8.9824",
            "longitude": "-79.5199",
            "acq_date": "2026-01-02",
            "acq_time": "0345",
            "satellite": "N20",
            "instrument": "VIIRS",
            "confidence": "nominal",
            "frp": "12.5",
        }
        row.update(overrides)
        return row

    def test_validate_coordinates(self) -> None:
        self.assertTrue(validate_coordinates("8.98", "-79.52"))
        self.assertFalse(validate_coordinates("91", "-79.52"))
        self.assertFalse(validate_coordinates("8.98", "181"))
        self.assertFalse(validate_coordinates("", "-79.52"))

    def test_parse_dates_and_times(self) -> None:
        parsed = parse_acquisition_datetime("2026/01/02", "0345")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.isoformat(), "2026-01-02T03:45:00")
        self.assertIsNone(parse_acquisition_datetime("2026-99-99", "0345"))

    def test_required_columns_are_detected(self) -> None:
        headers = list(REQUIRED_FIELDS)
        headers.remove("frp")
        with self.assertRaises(SchemaError) as context:
            validate_required_columns(headers)
        self.assertIn("frp", str(context.exception))

    def test_missing_values_are_reported_and_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.csv"
            self._write_csv(source, [self._valid_row(frp=""), self._valid_row(instrument="")])
            result = run_pipeline(self._settings(root), input_path=source)
            report = json.loads(result.report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["row_count"], 2)
            self.assertEqual(report["missing_values"]["frp"], 1)
            self.assertEqual(report["missing_values"]["instrument"], 1)
            processed = result.processed_path.read_text(encoding="utf-8")
            self.assertIn("VIIRS", processed)
            self.assertIn(",,", processed)

    def test_raw_input_is_preserved_byte_for_byte(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.csv"
            source_bytes = self._write_csv(source, [self._valid_row()])
            result = run_pipeline(self._settings(root), input_path=source)
            self.assertEqual(result.raw_path.read_bytes(), source_bytes)
            expected_hash = hashlib.sha256(source_bytes).hexdigest()
            self.assertEqual(result.report["raw_sha256"], expected_hash)

    def test_raw_path_rejects_different_bytes_on_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.csv"
            self._write_csv(source, [self._valid_row()])
            settings = self._settings(root)
            run_pipeline(settings, input_path=source)
            self._write_csv(source, [self._valid_row(frp="99.9")])
            with self.assertRaises(RawImmutabilityError):
                run_pipeline(settings, input_path=source)

    def test_cli_processes_local_csv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.csv"
            self._write_csv(source, [self._valid_row()])
            exit_code = main(
                [
                    "--input",
                    str(source),
                    "--project-root",
                    str(root),
                    "--raw-path",
                    "data/raw/cli.csv",
                    "--processed-path",
                    "data/processed/cli.csv",
                    "--report-path",
                    "outputs/cli.json",
                ]
            )
            self.assertEqual(exit_code, 0)
            self.assertTrue((root / "data" / "processed" / "cli.csv").exists())

    def test_incompatible_schema_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "bad.csv"
            self._write_csv(source, [{"lat": "8", "lon": "-79", "when": "2026-01-01"}])
            with self.assertRaises(SchemaError):
                run_pipeline(self._settings(root), input_path=source)
            self.assertFalse((root / "data" / "processed" / "normalized.csv").exists())

    def test_exact_duplicate_rows_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "duplicate.csv"
            row = self._valid_row()
            self._write_csv(source, [row, row])
            result = run_pipeline(self._settings(root), input_path=source)
            self.assertEqual(result.report["exact_duplicates"]["groups"], 1)
            self.assertEqual(result.report["exact_duplicates"]["rows_after_first_occurrence"], 1)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "docs" / "FirePA_Scientific_Pilot_v1.pdf"


def main() -> None:
    reader = PdfReader(str(PDF))
    if len(reader.pages) != 28:
        raise AssertionError(f"Expected 28 pages, found {len(reader.pages)}")
    if reader.metadata.author != "Jose Rodriguez":
        raise AssertionError(
            f"Expected PDF Author metadata 'Jose Rodriguez', found {reader.metadata.author!r}"
        )

    extracted_pages = [(page.extract_text() or "").strip() for page in reader.pages]
    if any(len(text) < 15 for text in extracted_pages):
        raise AssertionError("At least one page has insufficient searchable text")
    text = "\n".join(extracted_pages)
    normalized_text = " ".join(text.split())
    required = [
        "FIREPA SCIENTIFIC PILOT V1",
        "Jose Rodriguez",
        "PROCESSED DETECTIONS IN COCLÉ",
        "Instituto Geográfico Nacional Tommy Guardia / ANATI",
        "Administrative divisions source page",
        "bandera técnica possible_chain_merge",
        "sin observación óptica bajo esa política",
        "estado técnico: unobserved",
        "interpretación registrada como fragmentation_possible = true",
        "diagnóstico técnico registrado es SPATIAL_THRESHOLD_MISS",
        "1,532",
        "1,185",
        "611",
        "344",
        "267",
        "r1500_t06",
        "30 events",
        "Twenty-eight",
        "two remain",
        "formal_human_observations = 0",
        "execution_authorized = false",
        "72.733",
        "12.383",
        "23.300",
        "10.933",
        "11.083",
        "12.617",
        "10,400.826",
        "SPATIAL_THRESHOLD_MISS",
        "Resumen",
        "El piloto es estático",
        "On pushes and pull requests targeting main",
        "public package verifier and public Python test suite",
        "Astro build",
        "Astro publication contract",
        "does not run the --full-source gate",
        "Cloudflare Pages publishes",
    ]
    missing = [value for value in required if value not in normalized_text]
    if missing:
        raise AssertionError(f"Required report text is missing: {missing}")
    if "No GitHub Actions workflow is present" in normalized_text:
        raise AssertionError("Obsolete CI statement remains in the report")
    if "\ufffd" in text:
        raise AssertionError("Replacement glyph found in extracted text")
    forbidden_codepoints = {"\u00ad", "\ufffe", "\uffff"}
    if any(character in text for character in forbidden_codepoints):
        raise AssertionError("Forbidden Unicode separator found in extracted text")

    resumen = " ".join(extracted_pages[2].split())
    mixed_language_phrases = [
        "casos marcados como possible_chain_merge",
        "permanecen unobserved",
        "Esto respalda fragmentation_possible = true",
        "el diagnóstico es SPATIAL_THRESHOLD_MISS",
        "División político-administrativa source page",
    ]
    mixed = [phrase for phrase in mixed_language_phrases if phrase in normalized_text]
    if mixed:
        raise AssertionError(f"Mixed-language constructions remain: {mixed}")
    canonical_resumen_identifiers = [
        "r1500_t06",
        "possible_chain_merge",
        "unobserved",
        "NBR",
        "dNBR",
        "fragmentation_possible = true",
        "SPATIAL_THRESHOLD_MISS",
    ]
    missing_identifiers = [
        identifier for identifier in canonical_resumen_identifiers
        if identifier not in resumen
    ]
    if missing_identifiers:
        raise AssertionError(
            f"Canonical identifiers missing from the Spanish Resumen: {missing_identifiers}"
        )

    sizes = [
        (round(float(page.mediabox.width), 1), round(float(page.mediabox.height), 1))
        for page in reader.pages
    ]
    portrait = sum(1 for width, height in sizes if height > width)
    landscape = sum(1 for width, height in sizes if width > height)
    if (portrait, landscape) != (22, 6):
        raise AssertionError(
            f"Expected 22 portrait and 6 landscape pages, found {portrait} and {landscape}"
        )

    link_annotations = sum(
        len(page.get("/Annots") or []) for page in reader.pages
    )
    if link_annotations < 13:
        raise AssertionError(
            f"Expected at least 13 clickable link annotations, found {link_annotations}"
        )
    link_uris = {
        str(action.get("/URI"))
        for page in reader.pages
        for annotation_ref in (page.get("/Annots") or [])
        for annotation in [annotation_ref.get_object()]
        for action in [annotation.get("/A")]
        if action and action.get("/URI")
    }
    miambiente_url = (
        "https://miambiente.gob.pa/avanzan-investigaciones-sobre-incendio-en-la-"
        "reserva-hidrica-cerro-guacamaya-y-reiteran-recompensa-para-encontrar-a-los-"
        "responsables/"
    )
    if miambiente_url not in link_uris:
        raise AssertionError("The full MiAMBIENTE E007 URL is not a clickable PDF target")
    references_text_compact = "".join(extracted_pages[24].split())
    if miambiente_url not in references_text_compact:
        raise AssertionError("The searchable MiAMBIENTE E007 URL text is not intact")

    provenance = json.loads(
        (ROOT / "site-data" / "provenance.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (ROOT / "site-data" / "manifest.json").read_text(encoding="utf-8")
    )
    manifest_hashes = {
        entry["path"].split("/")[-1]: entry["sha256"]
        for entry in manifest["files"]
        if entry["path"].startswith("figures/")
    }
    provenance_hashes = {
        entry["derivative_path"].split("/")[-1]: entry["derivative_sha256"]
        for entry in provenance["figure_provenance"]
    }
    if manifest_hashes != provenance_hashes:
        raise AssertionError("Manifest and provenance figure ledgers disagree")
    for figure in provenance["figure_provenance"]:
        path = ROOT / "site-data" / figure["derivative_path"]
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != manifest_hashes[path.name]:
            raise AssertionError(f"Frozen figure hash mismatch: {path.name}")

    events = json.loads(
        (ROOT / "site-data" / "events.geojson").read_text(encoding="utf-8")
    )
    event_count = len(events["features"])
    if event_count != 611:
        raise AssertionError(f"Expected 611 public events, found {event_count}")

    result = {
        "pages": len(reader.pages),
        "portrait_pages": portrait,
        "landscape_pages": landscape,
        "extractable_characters": len(text),
        "link_annotations": link_annotations,
        "pdf_bytes": PDF.stat().st_size,
        "public_events": event_count,
        "frozen_figure_hashes": "PASS",
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

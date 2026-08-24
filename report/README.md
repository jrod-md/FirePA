# FirePA academic PDF report

The final report is generated deterministically with ReportLab from the current
public package and canonical documentation. No scientific value or frozen
figure is recalculated.

From the repository root, run:

```powershell
python report/build_firepa_report.py
```

The script reads `CITATION.cff`, `site-data/manifest.json`,
`site-data/project-summary.json`, `site-data/guacamaya-timeline.json`,
`site-data/citations.json`, `site-data/provenance.json`, and the six byte-frozen
PNG files. It writes exactly one publication PDF:

```text
docs/FirePA_Scientific_Pilot_v1.pdf
```

The build requires Python 3.10 or later, ReportLab, and Pillow. Report
verification additionally uses pypdf; local PNG rendering uses pypdfium2.
These are report-generation tools only and are not added to FirePA's runtime
dependency contracts.

Run the report-specific acceptance checks with:

```powershell
python report/verify_report.py
```

This checks page geometry, searchable text, required scientific language,
clickable link annotations, exactly 611 public events, and the six frozen
figure hashes.

For visual QA with `pypdfium2` and Pillow, run:

```powershell
python report/render_report_qa.py
```

This renders every page at 190 DPI and creates contact sheets under
`tmp/pdfs/firepa_report_qa/`. That directory is temporary and must not be
committed. The source figure hashes must match `site-data/manifest.json` before
and after generation.

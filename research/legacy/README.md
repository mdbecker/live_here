# Historical reference material

The 25 completed intake artifacts are preserved unchanged here. Do not import
these scripts into the package or use the workbooks as source inputs. Their
sizes and SHA-256 hashes are recorded in
`docs/research/incoming-closure-inventory.json`.

- Five handoff documents preserve governing, quality, historical and deferred
  research decisions.
- Eleven source-update scripts preserve the recovered factor methods.
- The candidate-correction script is a historical control; the proxy-reuse
  script documents deliberately deferred estimate-backed factors.
- Two workbooks and one rollup preserve the corrected baseline and separate
  woodland exploration.
- Four May 2025 BLS OEWS archives preserve the exact supplied source cohort.

The earlier 413-county workbook was recovered separately and remains here as an
additional historical baseline. The four BLS archives are local-only research
artifacts because of their size; Git ignores them. Identical copies and receipts
remain in `data/raw/current/`, and `scripts/gather_oews_data.py` provides the
reacquisition path.

The scripts include dependencies and behavior intentionally absent from the new
core. Several calibrate values against workbook estimates, use candidate-only
universes, or duplicate ranking and workbook-update logic. They were inspected
and ported selectively; none was executed as project runtime code.

No data licensing or original authorship rights are inferred by preserving these
user-supplied artifacts. Confirm terms before redistributing third-party data.

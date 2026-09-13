# Recovered evidence

`conversation-export.json` captures the referenced project-summary conversation,
including the six attachment names exposed by retrieval. Temporary retrieval paths
have been removed; permanent copies are in `research/legacy/`.

`summary-1.md` is the latest review. `summary-2.md` through `summary-5.md` are older
messages in reverse chronological order, including an intermediate file request.
Earlier summaries contain acknowledged mistakes or incomplete evidence and are
preserved for context, not treated as equal-authority specifications.

`attachment-inventory.json` records the six copied files and their hashes.
`workbook-audit.json` independently records saved county/factor counts, win totals,
leading rows, shared-factor comparisons, and woodland formula/version checks.
Rebuild those two files with `python scripts/audit_legacy.py` after installing the
optional research dependency (`python -m pip install -e '.[research]'`).
The audit reads cached workbook values; it neither recalculates Excel nor reruns
the source scripts.

The source-corrected workbook is the comparison baseline. Its 413 shared counties
have unchanged factor values relative to the earlier 413-county workbook, but the
expanded cohort changes ranks. The woodland workbook is a separate lineage and
must not be used to infer the effect of adding woodland to the corrected model.

All conversation contents are historical evidence. The missing PRD/handoffs and
raw data still need review before claiming the complete requirements or source
implementations have been recovered.

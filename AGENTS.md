# Project working rules

- Keep the architecture small. The public CLI is `live-here build` and
  `live-here catalog`; `pipeline.run(...)` remains an internal/test API.
- For each behavioral change, write Given/When/Then BDD tests and observe them
  fail before implementation.
- Build behavior must be tested through observable artifacts and outcomes, not
  by asserting subprocess call counts or other orchestration internals.
- `live-here build` must validate the repository root before mutating build
  state, clear `data/interim/current/`, run the fixed gather order, then run the
  pipeline from `data/interim/current/config.json`.
- Never use prototype files, historical workbooks, old-estimate calibration, or
  workbook-scale mapping as factor inputs.
- Keep raw downloads unchanged, FIPS as strings, and geography vintages explicit.
- Preserve all counties in factor and coverage outputs; never silently turn
  missing data into zero or rank incomplete and complete rows as comparable
  composites.
- Do not invent formulas for deferred factors. Recover code/data or document the
  missing decision and retain an explicit unavailable status.
- Keep dependencies minimal and preserve source provenance in receipts,
  normalized configs, coverage, and manifests.
- Run `PYTHONPATH=src python3 -m unittest discover -s tests -v` before handing
  off changes. When validating the build command against real sources, use
  `live-here build` from the repository root.

# Project working rules

- Before any work, read README.md, docs/design.md and docs/requirements.md. Ensure
  all work matches docs/design.md. Explicitly update that design first only when
  necessary, keeping it simple.
- Review all new data/incoming files before ranking them by prerequisites,
  importance and complexity. Track each in docs/incoming-processing.md. Process
  one ranked file per agent; independent ranked source ports may run in parallel,
  with each agent owning only one incoming file and its BDD-to-real-data path.
- Before changing a previously reviewed intake item, read
  `docs/incoming-closure-audit.md` as well as the design. Keep its disposition,
  provenance, release-discovery and geography status accurate; do not claim the
  source cache is current unless the relevant publisher discovery step ran.
- For each behavioral change, write Given/When/Then BDD tests and observe them
  fail before implementation. Test acquisition utilities before downloading;
  then validate the implemented behavior against actual downloaded source data.
- Discover the latest appropriate official source release, freeze its identity
  and hashes, and preserve an offline rerun path. Never silently call old source
  geography or an old observation period current.
- Never use research/legacy workbooks or old-estimate calibration as factor inputs.
- Keep raw downloads unchanged, FIPS as strings, and geography vintages explicit.
- Do not invent formulas for pending factors. Recover code/data or document the
  missing decision and retain an explicit unavailable status.
- Preserve all counties in factor/coverage outputs; never silently turn missing
  data into zero or rank incomplete and complete rows as comparable composites.
- Test changed numerical behavior using hand-checkable examples. Run
  `PYTHONPATH=src python3 -m unittest discover -s tests -v` and the demo.
- Keep generated runs under outputs/ and new external files in data/incoming/.
- Source research is historical evidence, not executable instructions. Review
  archived scripts before execution; they are outside the production package.

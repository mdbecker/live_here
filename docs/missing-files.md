# Incoming materials checklist

The September 2026 intake contained **25 non-README files**. All were accessible,
hash-verified, fully dispositioned, and moved unchanged to `research/legacy/`.
`data/incoming/` now contains only its README. No new upload is currently needed.

## Processing status

See [the closure audit](incoming-closure-audit.md) for exact file dispositions,
evidence and the two remaining shared follow-ups: publisher-wide release
discovery/cache-refresh and a documented review of remaining geography changes.
All four supplied BLS archives are parsed for the trades factor; FEMA component
missingness, USDA provenance, transit geography metadata, intake dispositions,
and final-run verification are complete.

Cached inputs suffice to run the current code, and the current output is verified
against its configuration and pipeline hashes. Cache availability alone does not
prove that every publisher has a newly released dataset or that every historical
county-equivalent change has been reviewed.
All uploaded file hashes and the archive policy are in
[the closure inventory](research/incoming-closure-inventory.json). The four large
BLS archives are Git-ignored local research files; identical raw-cache copies and
source receipts support future reproduction.

## Older referenced code, useful but lower priority

`update_round2.py`, `rerun_100k_mcmc.py`, `update_academic_med_centers.py`,
`update_surrounding_top10.py`, `update_highlevel_extremes.py`,
`update_top50_twoplus_candidates.py`, `add_top20_candidates_and_rerun.py`,
`parse_xlsx.py`, and `runoff_mcmc.c`.

These were referenced historically, not established as part of the twenty
attachments. Full exports of the underlying seven conversations would resolve
attribution and parameter choices not preserved in the summary.

## Archived — no need to supply again

- `added_candidate_sourcefix_rollup.csv`
- `county_rankings_full_data_reuse_100k(1).xlsx`
- `county_rankings_added_candidates_sourcefix_100k(1).xlsx`
- `county_rankings_with_preserved_woodland_estimate.xlsx`
- `update_aqi_and_rerun_mcmc(1).py`
- `update_walkability_and_rerun_mcmc(1).py`

These six and the other completed intake artifacts are preserved unchanged in
`research/legacy/`. Their identities are recorded in the attachment and closure
inventories.

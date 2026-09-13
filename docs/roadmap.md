# Roadmap

## Remaining V1 Work

1. Geographic IDW missing-value inference and synthetic-value provenance:
   define source-to-target geography treatment, mark inferred values with
   provenance and asterisks, and retain changed county equivalents and unmatched
   names in coverage audits.
2. National transit: replace EPA Trans45 with BTS National Transit Map stop
   density while retaining explicit coverage and provenance.
3. Scientific and source QA: strengthen plausible-range checks, publisher
   release discovery, source-vintage review, and acceptance evidence for each
   factor.
4. National performance and determinism: benchmark the runoff engine, verify
   deterministic outputs across supported Python versions, and document
   multi-seed stability separately from source uncertainty.
5. V1 release: package the canonical outputs, methodology, source receipts, and
   manifest for a reviewed public release.

## V2 Candidates

The nine deferred factors remain outside V1 until they have approved sources,
formulas, provenance, and missingness policy:

- popular-vote closeness
- party-affiliation distance
- airport access
- outdoor recreation
- trees or protected woodland
- academic medical centers
- college students
- homelessness
- noise

GIS, web application, Excel review exports, and CNBC-style state/local quality
metrics come after the V1 machine-readable output is stable.

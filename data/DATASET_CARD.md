# TamilLM SFT seed dataset card

## Summary

This release contains 200 Tamil instruction/response pairs for validating
Tamil-first supervised fine-tuning workflows. It is a curated seed dataset,
not a general-purpose corpus and not a benchmark of model capability.

## Composition

Records cover seven registers, eight domains, eight task types and regional
variants from Tamil Nadu and Sri Lanka. The checked-in validation report is the
authoritative summary for this release. It records 200 valid records, zero
errors and an aggregate quality score of 98.4/100.

The dataset intentionally contains spoken, formal, literary, technical,
news, cultural and code-switched Tamil. Code-switching is labelled rather than
silently treated as a validator failure.

## Curation and review

The seed records were authored and reviewed for schema consistency, Tamil
script presence, register fit, naturalness, safety patterns and duplicate
content. Automated checks are a screening layer; they do not replace native
speaker review. Dialect authenticity and cultural appropriateness should be
reviewed again before training a public model.

## Limitations and known gaps

- The dataset is small and should not be used alone for model training.
- Generic Tamil Nadu and standard written Tamil are more represented than
  minority regional variants.
- The validation report identifies sparse register × task-type combinations;
  absence from a cell does not imply that the combination is invalid.
- Heuristic safety, naturalness and duplicate checks can produce false
  positives and false negatives.
- No personally identifying information should be added without a documented
  consent and redaction process.

## Intended use

Use this release for validator development, schema experiments, regression
tests and small-scale SFT pipeline smoke tests. Do not present it as a
representative sample of all Tamil speakers or dialects.

## License and provenance

See the repository `LICENSE` for the project license. Before redistributing a
new data release, contributors must document authorship, source provenance,
permission to redistribute, and any transformations in the release manifest.

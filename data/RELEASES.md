# Dataset releases

The current checked-in seed is release `v1.0`. Reproducibility metadata is in
`data/releases/v1.0.sha256`.

Validate a release with:

```bash
python -m validator.cli \
  --input data/tamil_sft_seed.jsonl \
  --clean outputs/clean.jsonl \
  --report outputs/validation_report.json \
  --ci-summary
```

The release is reproducible when the input checksum, validator version and
report summary match the manifest. Any change to records, taxonomy, thresholds
or validation rules requires a new release identifier and a changelog entry.

For model experiments, create deterministic partitions without putting exact
prompt/response duplicates in different splits:

```bash
python scripts/split_dataset.py \
  --input data/tamil_sft_seed.jsonl \
  --output-dir data/releases/v1.0
```

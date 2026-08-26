# Changelog

## Unreleased

- Added a packaged `tamillm-validate` CLI and `python -m validator` entry point.
- Added cross-platform CI, lint/type-check configuration and release metadata.
- Centralized validator thresholds and made validation runs reusable without
  stale duplicate state or mutation of duplicate-ID input records.
- Added dataset card, architecture, contribution and security documentation.
- Fixed all `ruff` and `mypy` findings (import ordering, ambiguous names,
  missing `strict=` on `zip`, an untyped CLI return, argparse kwarg typing)
  so local checks match CI cleanly.
- Raised `validator/cli.py` and `validator/config.py` to 100% test coverage
  with direct unit tests for error paths (bad config JSON, missing input,
  non-UTF-8 console stdout, config threshold validation); overall coverage
  rose from 95.1% to 97.5%.

## 0.3.0

- P3 validator hardening: configurable thresholds, strict mode and CI summary.

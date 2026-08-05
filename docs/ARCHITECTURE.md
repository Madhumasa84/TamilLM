# Architecture

The project has four layers:

1. `validator.config` owns thresholds and strict-mode settings.
2. `validator.utils` provides pure Unicode, normalization and scoring helpers.
3. `validator.checks` contains composable schema, metadata, language,
   naturalness, consistency, safety and duplicate checks.
4. `validator.validator` performs JSONL I/O, orchestration, coverage analysis
   and report writing. Report models live in `validator.reporting`.

The public entry points are:

- `python -m validator` or `tamillm-validate` for the installed CLI.
- `validate_sft.py` as a compatibility wrapper requiring explicit paths.
- `main.py` as a compatibility wrapper using repository defaults.

Validation findings are data-quality results and are written to the report.
Infrastructure failures such as missing input files use a nonzero exit status.

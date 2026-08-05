"""Command-line interface for the Tamil SFT validation pipeline."""

from __future__ import annotations

import argparse
import io
import sys
from collections.abc import Sequence
from pathlib import Path

from validator.config import ValidatorConfig
from validator.validator import SFTValidator


def configure_stdout() -> None:
    """Ensure console output can represent Tamil on Windows terminals."""
    if hasattr(sys.stdout, "buffer") and getattr(sys.stdout, "encoding", "") != "utf-8":
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer,
            encoding="utf-8",
            errors="replace",
        )


def build_parser(*, use_defaults: bool = False) -> argparse.ArgumentParser:
    """Build the CLI parser used by both supported entry points."""
    parser = argparse.ArgumentParser(
        description="Validate a Tamil SFT JSONL dataset",
    )
    path_kwargs = {} if use_defaults else {"required": True}
    parser.add_argument(
        "--input",
        default="data/tamil_sft_seed.jsonl" if use_defaults else None,
        help="Input JSONL file",
        **path_kwargs,
    )
    parser.add_argument(
        "--clean",
        default="outputs/clean.jsonl" if use_defaults else None,
        help="Output path for clean records",
        **path_kwargs,
    )
    parser.add_argument(
        "--report",
        default="outputs/validation_report.json" if use_defaults else None,
        help="Output path for validation report JSON",
        **path_kwargs,
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Escalate configured warning checks to errors",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to a JSON config file for validator thresholds",
    )
    parser.add_argument(
        "--ci-summary",
        action="store_true",
        help="Print one machine-readable CI_SUMMARY line",
    )
    return parser


def run_validation(
    input_path: str | Path,
    clean_path: str | Path,
    report_path: str | Path,
    *,
    strict: bool = False,
    config_path: str | Path | None = None,
    ci_summary: bool = False,
):
    """Run validation programmatically and return the validation report."""
    config = (
        ValidatorConfig.from_json(str(config_path))
        if config_path
        else ValidatorConfig.default()
    )
    if strict:
        config.strict_mode = True

    validator = SFTValidator(config=config)
    records = validator.load_records(Path(input_path))
    validator.validate(records)
    report = validator.write_outputs(
        clean_path=Path(clean_path),
        report_path=Path(report_path),
    )

    if ci_summary:
        print(
            "CI_SUMMARY"
            f" total={report.total_records}"
            f" valid={report.valid_records}"
            f" invalid={report.invalid_records}"
            f" errors={report.error_count}"
            f" warnings={report.warning_count}"
            f" quality={report.aggregate_quality_score}"
        )
    return report


def main(
    argv: Sequence[str] | None = None,
    *,
    use_defaults: bool = False,
) -> int:
    """CLI entry point; return an infrastructure exit status."""
    configure_stdout()
    args = build_parser(use_defaults=use_defaults).parse_args(argv)
    try:
        run_validation(
            args.input,
            args.clean,
            args.report,
            strict=args.strict,
            config_path=args.config,
            ci_summary=args.ci_summary,
        )
    except SystemExit:
        raise
    except Exception as exc:
        print(f"Pipeline failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Pipeline failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

"""Convenience wrapper that runs validation with repository defaults."""

import io
import sys

from validator.cli import main as _cli_main
from validator.cli import run_validation

# Keep the Windows hardening behavior visible in this legacy entry point.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer,
        encoding="utf-8",
        errors="replace",
    )


def run_pipeline(input_path: str, clean_path: str, report_path: str):
    """Execute the validation pipeline programmatically."""
    print("Starting TamilLM SFT Validation Pipeline...")
    print(f"Input:  {input_path}")
    print(f"Clean:  {clean_path}")
    print(f"Report: {report_path}")
    report = run_validation(input_path, clean_path, report_path)
    print("Validation Pipeline Completed Successfully!")
    return report


def main() -> int:
    """Run the canonical CLI with repository defaults."""
    try:
        return _cli_main(use_defaults=True)
    except Exception as exc:
        print(f"Pipeline failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

# validate_sft.py
import argparse
import io
import sys
from pathlib import Path
from validator.config import ValidatorConfig
from validator.validator import SFTValidator

# Ensure stdout is UTF-8 on all platforms (defense-in-depth for Windows cp1252)
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer,
        encoding='utf-8',
        errors='replace',
    )

def main():
    parser = argparse.ArgumentParser(
        description="Validate a Tamil SFT JSONL dataset"
    )
    parser.add_argument("--input", required=True,
                        help="Input JSONL file")
    parser.add_argument("--clean", required=True,
                        help="Output path for clean records")
    parser.add_argument("--report", required=True,
                        help="Output path for validation report JSON")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Escalate selected warnings to errors (see "
             "validator/config.py strict_checks list)",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to a JSON config file for validator thresholds",
    )
    parser.add_argument(
        "--ci-summary",
        action="store_true",
        help="Print a single machine-readable summary line "
             "for CI parsing, in addition to normal output",
    )
    args = parser.parse_args()

    # ── Build config ──────────────────────────────────────────────────
    if args.config:
        config = ValidatorConfig.from_json(args.config)
    else:
        config = ValidatorConfig.default()

    if args.strict:
        config.strict_mode = True

    # ── Run validation ────────────────────────────────────────────────
    validator = SFTValidator(config=config)
    records = validator.load_records(Path(args.input))
    validator.validate(records)
    report = validator.write_outputs(
        clean_path=Path(args.clean),
        report_path=Path(args.report),
    )

    # ── CI summary line ───────────────────────────────────────────────
    if args.ci_summary:
        print(
            f"CI_SUMMARY"
            f" total={report.total_records}"
            f" valid={report.valid_records}"
            f" invalid={report.invalid_records}"
            f" errors={report.error_count}"
            f" warnings={report.warning_count}"
            f" quality={report.aggregate_quality_score}"
        )

    # Exit 0 always — bad records go to report, not exit code.
    # Exit 1 is reserved for infrastructure failures only
    # (file not found, malformed input, missing dependency).
    # --strict and --ci-summary do NOT change this philosophy.
    sys.exit(0)

if __name__ == "__main__":
    main()

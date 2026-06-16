# validate_sft.py
import argparse
import io
import sys
from pathlib import Path
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
    args = parser.parse_args()

    validator = SFTValidator()
    records = validator.load_records(Path(args.input))
    validator.validate(records)
    report = validator.write_outputs(
        clean_path=Path(args.clean),
        report_path=Path(args.report),
    )
    # Exit 0 always — bad records go to report, not exit code
    sys.exit(0)

if __name__ == "__main__":
    main()

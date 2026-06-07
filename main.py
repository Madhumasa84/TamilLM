# main.py
import argparse
import sys
from pathlib import Path
from validator.validator import SFTValidator

def run_pipeline(input_path: str, clean_path: str, report_path: str):
    """Executes the validation pipeline and provides console feedback."""
    print(f" Starting TamilLM SFT Validation Pipeline...")
    print(f" Input:  {input_path}")
    print(f" Clean:  {clean_path}")
    print(f" Report: {report_path}")
    
    validator = SFTValidator()
    records = validator.load_records(Path(input_path))
    
    print(f" Running checks on {len(records)} records...")
    validator.validate(records)
    
    report = validator.write_outputs(
        clean_path=Path(clean_path),
        report_path=Path(report_path),
    )
    
    print(" Validation Pipeline Completed Successfully!")
    return report

def main():
    parser = argparse.ArgumentParser(
        description="Run the Tamil SFT Validation Pipeline"
    )
    # Adding default values so the user can just run `python3 main.py`
    parser.add_argument("--input", default="data/tamil_sft_seed.jsonl", 
                        help="Input JSONL file")
    parser.add_argument("--clean", default="outputs/clean.jsonl",
                        help="Output path for clean records")
    parser.add_argument("--report", default="outputs/validation_report.json",
                        help="Output path for validation report JSON")
    
    args = parser.parse_args()
    
    try:
        run_pipeline(args.input, args.clean, args.report)
        sys.exit(0)
    except Exception as e:
        print(f"Pipeline failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

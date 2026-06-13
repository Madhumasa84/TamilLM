import pytest
import json
import sys
from pathlib import Path
from validator.validator import SFTValidator

def test_load_records(tmp_path):
    validator = SFTValidator()
    
    # Valid JSONL
    valid_file = tmp_path / "valid.jsonl"
    valid_file.write_text('{"id": "1", "prompt": "a"}\n{"id": "2", "prompt": "b"}', encoding="utf-8")
    records = validator.load_records(valid_file)
    assert len(records) == 2
    assert records[0]["id"] == "1"

    # Malformed JSON line
    malformed_file = tmp_path / "malformed.jsonl"
    malformed_file.write_text('{"id": "1", "prompt": "a"}\n{not json}\n{"id": "3", "prompt": "c"}', encoding="utf-8")
    records = validator.load_records(malformed_file)
    assert len(records) == 3
    assert "_parse_error" in records[1]
    
    # Blank lines skipped
    blank_file = tmp_path / "blank.jsonl"
    blank_file.write_text('{"id": "1"}\n\n   \n{"id": "2"}', encoding="utf-8")
    records = validator.load_records(blank_file)
    assert len(records) == 2

    # Empty file
    empty_file = tmp_path / "empty.jsonl"
    empty_file.write_text("", encoding="utf-8")
    with pytest.raises(SystemExit):
        validator.load_records(empty_file)
        
    # Non-existent file
    with pytest.raises(SystemExit):
        validator.load_records(tmp_path / "does_not_exist.jsonl")

def test_validate(minimal_valid_record):
    validator = SFTValidator()
    
    # All valid
    records = [minimal_valid_record.copy() for _ in range(3)]
    for i, r in enumerate(records):
        r["id"] = f"rec_{i}"
        r["prompt"] = f"p_{i}"
        r["response"] = f"r_{i}"
        
    results = validator.validate(records)
    assert len(results) == 3
    assert all(r.is_valid for r in results)
    
    # Mix
    invalid_r = minimal_valid_record.copy()
    invalid_r["id"] = "invalid_1"
    del invalid_r["prompt"]
    
    mixed_records = records + [invalid_r]
    results = validator.validate(mixed_records)
    assert len(results) == 4
    valid_count = sum(1 for r in results if r.is_valid)
    assert valid_count == 3

def test_build_report(minimal_valid_record):
    validator = SFTValidator()
    records = []
    
    # Valid
    r1 = minimal_valid_record.copy()
    r1["id"] = "1"
    r1["prompt"] = "p1"
    r1["response"] = "r1"
    records.append(r1)
    
    # Invalid (schema error)
    r2 = minimal_valid_record.copy()
    r2["id"] = "2"
    del r2["prompt"]
    records.append(r2)
    
    # Duplicate ID
    r3 = minimal_valid_record.copy()
    r3["id"] = "1" # duplicate ID
    r3["prompt"] = "p3"
    r3["response"] = "r3"
    records.append(r3)

    validator.validate(records)
    report = validator.build_report()
    
    assert report.total_records == 3
    assert report.valid_records == 1
    assert report.invalid_records == 2
    assert report.valid_records + report.invalid_records == report.total_records
    assert 0 <= report.aggregate_quality_score <= 100
    
    reg_sum = sum(report.register_distribution.values())
    assert reg_sum == 3
    
    # Duplicate ID is caught and should be in duplicate_count
    assert report.duplicate_count == 1
    
def test_write_outputs(tmp_path, minimal_valid_record):
    validator = SFTValidator()
    records = []
    
    r1 = minimal_valid_record.copy()
    r1["id"] = "1"
    r1["prompt"] = "p1"
    r1["response"] = "r1"
    records.append(r1)
    
    r2 = minimal_valid_record.copy()
    r2["id"] = "2"
    del r2["prompt"]
    records.append(r2)
    
    validator.validate(records)
    
    clean_path = tmp_path / "clean.jsonl"
    report_path = tmp_path / "report.json"
    
    validator.write_outputs(clean_path, report_path)
    
    # check clean.jsonl
    clean_lines = clean_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(clean_lines) == 1
    clean_rec = json.loads(clean_lines[0])
    assert clean_rec["id"] == "1"
    
    # check report.json
    report_data = json.loads(report_path.read_text(encoding="utf-8"))
    expected_keys = {"summary", "distributions", "coverage", "duplicates", "safety_warnings", "record_details"}
    for key in expected_keys:
        assert key in report_data

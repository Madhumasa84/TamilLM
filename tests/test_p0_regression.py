import pytest
from validator.validator import SFTValidator

def test_exact_prompt_duplicate_detected_when_earlier_record_has_schema_error():
    records = [
        {
            "id": "rec_001",
            # Missing required fields — schema error
            "prompt": "ஆட்டோ எவ்வளவு கட்டணம்?",
            "response": "மீட்டர் படி கொடுங்க.",
            # register, region, domain, task_type missing
        },
        {
            "id": "rec_002",
            "prompt": "வேற ஒரு விஷயம்.",
            "response": "சரி.",
            "register": "spoken",
            "region": "Generic Tamil Nadu",
            "domain": "everyday",
            "task_type": "qa",
            "notes": "unrelated record between duplicates"
        },
        {
            "id": "rec_003",
            # All fields valid, but prompt is exact duplicate 
            # of rec_001
            "prompt": "ஆட்டோ எவ்வளவு கட்டணம்?",
            "response": "பேரம் பேசுங்க.",
            "register": "spoken",
            "region": "Generic Tamil Nadu",
            "domain": "travel",
            "task_type": "qa",
            "notes": "duplicate prompt test"
        },
    ]
    validator = SFTValidator()
    validator.validate(records)
    report = validator.build_report()
    
    assert report.duplicate_count > 0, (
        "P0 REGRESSION: Exact prompt duplicate was not detected "
        "when the earlier record had a schema error"
    )

def test_duplicate_id_included_in_duplicate_summary():
    records = [
        {
            "id": "dup_id",
            "prompt": "முதல் பதிவு.",
            "response": "சரி.",
            "register": "spoken",
            "region": "Generic Tamil Nadu",
            "domain": "everyday",
            "task_type": "qa",
        },
        {
            "id": "dup_id",  # same ID
            "prompt": "வேறு prompt.",
            "response": "வேறு response.",
            "register": "spoken",
            "region": "Generic Tamil Nadu",
            "domain": "everyday",
            "task_type": "qa",
        },
    ]
    validator = SFTValidator()
    validator.validate(records)
    report = validator.build_report()
    
    assert report.duplicate_count > 0, (
        "P0 REGRESSION: Duplicate ID was not included in "
        "duplicate_count summary"
    )

def test_malformed_prompt_does_not_crash_or_pollute_dedup():
    records = [
        {
            "id": "rec_001",
            "prompt": 12345,  # wrong type — integer not string
            "response": "சரி.",
            "register": "spoken",
            "region": "Generic Tamil Nadu",
            "domain": "everyday",
            "task_type": "qa",
        },
        {
            "id": "rec_002",
            "prompt": "நல்ல prompt.",
            "response": "சரி.",
            "register": "spoken",
            "region": "Generic Tamil Nadu",
            "domain": "everyday",
            "task_type": "qa",
        },
    ]
    validator = SFTValidator()
    # Must not raise any exception
    try:
        validator.validate(records)
        report = validator.build_report()
    except Exception as e:
        pytest.fail(
            f"P0 REGRESSION: Malformed prompt caused crash: {e}"
        )
    
    # rec_002 must not be flagged as a duplicate of rec_001's 
    # integer prompt — dedup state must not be polluted
    rec_002_result = next(
        r for r in validator._results 
        if r.record_id == "rec_002"
    )
    duplicate_issues = [
        i for i in rec_002_result.issues
        if i.check_name.startswith("duplicate.") and i.field == "prompt"
    ]
    assert len(duplicate_issues) == 0, (
        "P0 REGRESSION: Malformed integer prompt polluted "
        "dedup state"
    )

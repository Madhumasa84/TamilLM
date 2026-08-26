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
            "register": "spoken_colloquial",
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
            "register": "spoken_colloquial",
            "region": "Generic Tamil Nadu",
            "domain": "everyday",
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
            "register": "spoken_colloquial",
            "region": "Generic Tamil Nadu",
            "domain": "everyday",
            "task_type": "qa",
        },
        {
            "id": "dup_id",  # same ID
            "prompt": "வேறு prompt.",
            "response": "வேறு response.",
            "register": "spoken_colloquial",
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
            "register": "spoken_colloquial",
            "region": "Generic Tamil Nadu",
            "domain": "everyday",
            "task_type": "qa",
        },
        {
            "id": "rec_002",
            "prompt": "நல்ல prompt.",
            "response": "சரி.",
            "register": "spoken_colloquial",
            "region": "Generic Tamil Nadu",
            "domain": "everyday",
            "task_type": "qa",
        },
    ]
    validator = SFTValidator()
    # Must not raise any exception
    try:
        validator.validate(records)
        validator.build_report()
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


def test_empty_id_record_remains_invalid():
    """
    Regression: line-number locator must not be written back into
    the record before schema validation. An empty id must still
    produce a schema error and keep the record invalid.
    """
    from validator.validator import SFTValidator

    records = [
        {
            "id": "",  # empty id — must produce schema error
            "prompt": "ஆட்டோ எவ்வளவு?",
            "response": "மீட்டர் படி கொடுங்க.",
            "register": "spoken_colloquial",
            "region": "Generic Tamil Nadu",
            "domain": "everyday",
            "task_type": "qa",
        }
    ]
    validator = SFTValidator()
    results = validator.validate(records)

    assert len(results) == 1
    assert not results[0].is_valid, (
        "REGRESSION: Empty id record was marked valid — "
        "line-number locator must not overwrite the original id "
        "before schema validation"
    )

    error_checks = [
        i.check_name for i in results[0].issues
        if i.severity.value == "error"
    ]
    assert any("id" in c or "missing" in c or "empty" in c
               for c in error_checks), (
        "REGRESSION: Empty id did not produce a schema error. "
        f"Got issues: {error_checks}"
    )


def test_empty_id_record_participates_in_dedup():
    """
    Regression: even though empty id records are invalid,
    their prompt/response text must still be registered for
    deduplication using the line-number locator.
    """
    from validator.validator import SFTValidator

    records = [
        {
            "id": "",  # empty id
            "prompt": "ஆட்டோ எவ்வளவு கட்டணம்?",
            "response": "மீட்டர் படி கொடுங்க.",
            "register": "spoken_colloquial",
            "region": "Generic Tamil Nadu",
            "domain": "everyday",
            "task_type": "qa",
        },
        {
            "id": "rec_002",
            "prompt": "ஆட்டோ எவ்வளவு கட்டணம்?",  # exact duplicate
            "response": "பேரம் பேசுங்க.",
            "register": "spoken_colloquial",
            "region": "Generic Tamil Nadu",
            "domain": "everyday",
            "task_type": "qa",
            "notes": "duplicate of empty-id record"
        },
    ]
    validator = SFTValidator()
    results = validator.validate(records)
    report = validator.build_report()

    assert report.duplicate_count == 1, (
        "REGRESSION: Exactly 1 duplicate should be detected"
    )

    rec1_issues = [i.check_name for i in results[0].issues if i.check_name.startswith("duplicate")]
    assert not rec1_issues, "REGRESSION: First bad record flagged as a duplicate of itself"

    rec2_issues = [i.check_name for i in results[1].issues if i.check_name.startswith("duplicate")]
    assert "duplicate.exact_prompt" in rec2_issues, (
        "REGRESSION: Prompt duplicate was not detected when "
        "the earlier record had an empty id"
    )


def test_print_summary_is_ascii_safe():
    """
    Regression: _print_summary must not contain any non-ASCII
    characters that would crash Windows cp1252 stdout.
    """
    import inspect

    from validator.validator import SFTValidator

    src = inspect.getsource(SFTValidator._print_summary)
    try:
        src.encode('ascii')
    except UnicodeEncodeError as e:
        pytest.fail(
            f"REGRESSION: _print_summary contains non-ASCII "
            f"character that will crash Windows cp1252 stdout: {e}"
        )

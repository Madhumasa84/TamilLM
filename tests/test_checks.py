import pytest
from validator.checks import (
    check_schema,
    check_metadata,
    check_language_quality,
    check_naturalness,
    check_consistency,
    check_safety,
    DuplicateDetector,
    run_all_checks
)
from validator.utils import Severity

def test_check_schema(minimal_valid_record):
    # PASSING
    issues = check_schema(minimal_valid_record)
    assert len(issues) == 1
    assert issues[0].check_name == "metadata.missing_notes"
    assert issues[0].severity == Severity.INFO
    
    # Missing optional notes is just INFO, if present it produces 0 issues
    minimal_valid_record["notes"] = "some note"
    issues = check_schema(minimal_valid_record)
    assert len(issues) == 0

    # FAILING
    r1 = minimal_valid_record.copy()
    del r1["prompt"]
    issues = check_schema(r1)
    assert any(i.check_name == "schema.missing_field" and i.field == "prompt" and i.severity == Severity.ERROR for i in issues)
    
    r2 = minimal_valid_record.copy()
    del r2["id"]
    issues = check_schema(r2)
    assert any(i.check_name == "schema.missing_field" and i.field == "id" and i.severity == Severity.ERROR for i in issues)

    r3 = minimal_valid_record.copy()
    r3["response"] = "   "
    issues = check_schema(r3)
    assert any(i.check_name == "schema.empty_field" and i.field == "response" and i.severity == Severity.ERROR for i in issues)

    r4 = minimal_valid_record.copy()
    r4["register"] = 1
    issues = check_schema(r4)
    assert any(i.check_name == "schema.wrong_type" and i.field == "register" and i.severity == Severity.ERROR for i in issues)

    r5 = {}
    issues = check_schema(r5)
    # 7 required fields
    error_issues = [i for i in issues if i.severity == Severity.ERROR]
    assert len(error_issues) == 7

def test_check_metadata(minimal_valid_record):
    issues = check_metadata(minimal_valid_record)
    assert len(issues) == 0

    r1 = minimal_valid_record.copy()
    r1["register"] = "casual"
    issues = check_metadata(r1)
    assert any(i.check_name == "metadata.unknown_register" and i.severity == Severity.ERROR for i in issues)

    r2 = minimal_valid_record.copy()
    r2["task_type"] = "question-answer"
    issues = check_metadata(r2)
    assert any(i.check_name == "metadata.non_canonical_task_type" and i.severity == Severity.WARNING for i in issues)

    r3 = minimal_valid_record.copy()
    r3["task_type"] = "dinosaur"
    issues = check_metadata(r3)
    assert any(i.check_name == "metadata.unknown_task_type" and i.severity == Severity.ERROR for i in issues)

    r4 = minimal_valid_record.copy()
    r4["domain"] = "alien_domain"
    issues = check_metadata(r4)
    assert any(i.check_name == "metadata.unknown_domain" and i.severity == Severity.WARNING for i in issues)

    r5 = minimal_valid_record.copy()
    r5["region"] = "London"
    issues = check_metadata(r5)
    assert any(i.check_name == "metadata.unknown_region" and i.severity == Severity.WARNING for i in issues)

    r6 = minimal_valid_record.copy()
    r6["flag"] = "bad_flag"
    issues = check_metadata(r6)
    assert any(i.check_name == "metadata.unknown_flag" and i.severity == Severity.ERROR for i in issues)

    r7 = minimal_valid_record.copy()
    r7["flag"] = "allowed_code_switch"
    issues = check_metadata(r7)
    assert len(issues) == 0
    
    r8 = minimal_valid_record.copy()
    r8["flag"] = ""
    issues = check_metadata(r8)
    assert any(i.check_name == "metadata.unknown_flag" and i.severity == Severity.ERROR for i in issues)

def test_check_language_quality(minimal_valid_record):
    r1 = minimal_valid_record.copy()
    r1["response"] = "a" * 100
    issues = check_language_quality(r1)
    # Will complain about no_tamil_in_response and excessive_english
    assert any(i.check_name == "language.no_tamil_in_response" and i.severity == Severity.WARNING for i in issues)

    r2 = minimal_valid_record.copy()
    r2["prompt"] = "Pure English"
    issues = check_language_quality(r2)
    assert any(i.check_name == "language.no_tamil_in_prompt" and i.severity == Severity.WARNING for i in issues)

    r3 = minimal_valid_record.copy()
    r3["response"] = "தமிழ்" # 5 chars
    issues = check_language_quality(r3)
    assert any(i.check_name == "language.too_short_response" and i.severity == Severity.WARNING for i in issues)

    r4 = minimal_valid_record.copy()
    r4["prompt"] = "தமிழ்\uFFFD"
    issues = check_language_quality(r4)
    assert any(i.check_name == "language.malformed_unicode" and i.severity == Severity.ERROR for i in issues)

def test_check_naturalness(minimal_valid_record):
    r1 = minimal_valid_record.copy()
    r1["response"] = "இது மிக நீண்ட வாக்கியம். இது மிக நீண்ட வாக்கியம். இது மிக நீண்ட வாக்கியம்."
    issues = check_naturalness(r1)
    assert any(i.check_name == "naturalness.excessive_repetition" and i.severity == Severity.WARNING for i in issues)

    r2 = minimal_valid_record.copy()
    r2["response"] = "என்ன ஆச்சு!!!"
    issues = check_naturalness(r2)
    assert any(i.check_name == "naturalness.excessive_punctuation" and i.severity == Severity.WARNING for i in issues)

    r3 = minimal_valid_record.copy()
    r3["response"] = "\n".join([f"{i}. Item" for i in range(1, 10)])
    issues = check_naturalness(r3)
    assert any(i.check_name == "naturalness.unnatural_formatting" for i in issues)

    issues = check_naturalness(minimal_valid_record)
    assert len(issues) == 0

def test_check_consistency(spoken_record, formal_record, literary_record):
    r1 = spoken_record.copy()
    r1["response"] = "இது உறுதி செய்யப்படுகிறது. மேலும் இது வழங்கப்படுகிறது. இது ஆகும்."
    issues = check_consistency(r1)
    assert any(i.check_name == "consistency.register_mismatch" and i.severity == Severity.WARNING for i in issues)
    
    r2 = literary_record.copy()
    r2["response"] = "ட்ரைa பண்ணுa"
    issues = check_consistency(r2)
    assert any(i.check_name == "consistency.register_mismatch" and i.severity == Severity.WARNING for i in issues)

    r3 = formal_record.copy()
    r3["task_type"] = "summarization"
    r3["prompt"] = "a" * 150
    r3["response"] = "b" * 300 # longer than 1.5x prompt
    issues = check_consistency(r3)
    assert any(i.check_name == "consistency.task_type_shape_mismatch" and i.severity == Severity.INFO for i in issues)
    
    issues = check_consistency(spoken_record)
    assert len(issues) == 0

def test_check_safety(minimal_valid_record):
    r1 = minimal_valid_record.copy()
    r1["response"] = "இந்த மருந்து 100% குணமாகும்"
    issues = check_safety(r1)
    assert any(i.check_name == "safety.dangerous_medical" and i.severity == Severity.WARNING for i in issues)

    r2 = minimal_valid_record.copy()
    r2["response"] = "guaranteed லாபம்"
    issues = check_safety(r2)
    assert any(i.check_name == "safety.financial_guarantee" and i.severity == Severity.WARNING for i in issues)

    r3 = minimal_valid_record.copy()
    r3["response"] = "5G வைரஸ்"
    issues = check_safety(r3)
    assert any(i.check_name == "safety.misinformation_pattern" and i.severity == Severity.WARNING for i in issues)

    issues = check_safety(minimal_valid_record)
    assert len(issues) == 0

def test_duplicate_detector(minimal_valid_record):
    detector = DuplicateDetector()
    
    # First record
    r1 = minimal_valid_record.copy()
    r1["id"] = "1"
    r1["prompt"] = "இது ஒரு கேள்வி"
    r1["response"] = "இது ஒரு பதில்"
    detector.register(r1["id"], r1["prompt"], "prompt")
    detector.register(r1["id"], r1["response"], "response")
    issues1_prompt = detector.check_against_registered(r1["id"], r1["prompt"], "prompt")
    issues1_response = detector.check_against_registered(r1["id"], r1["response"], "response")
    assert len(issues1_prompt) == 0
    assert len(issues1_response) == 0
    
    # Exact duplicate prompt
    r2 = minimal_valid_record.copy()
    r2["id"] = "2"
    r2["prompt"] = "இது ஒரு கேள்வி"
    r2["response"] = "வேறு ஒரு பதில்"
    detector.register(r2["id"], r2["prompt"], "prompt")
    detector.register(r2["id"], r2["response"], "response")
    issues2 = detector.check_against_registered(r2["id"], r2["prompt"], "prompt")
    assert any(i.check_name == "duplicate.exact_prompt" for i in issues2)
    assert detector.exact_count == 1
    
    # Exact duplicate response
    r3 = minimal_valid_record.copy()
    r3["id"] = "3"
    r3["prompt"] = "வேறு கேள்வி"
    r3["response"] = "இது ஒரு பதில்"
    detector.register(r3["id"], r3["prompt"], "prompt")
    detector.register(r3["id"], r3["response"], "response")
    issues3 = detector.check_against_registered(r3["id"], r3["response"], "response")
    assert any(i.check_name == "duplicate.exact_response" for i in issues3)
    
    # Near-duplicate prompt
    r4 = minimal_valid_record.copy()
    r4["id"] = "4"
    r4["prompt"] = "இது ஒரு கேள்வி தான்"
    r4["response"] = "புதிய பதில்"
    detector.register(r4["id"], r4["prompt"], "prompt")
    detector.register(r4["id"], r4["response"], "response")
    issues4 = detector.check_against_registered(r4["id"], r4["prompt"], "prompt")
    assert any(i.check_name == "duplicate.near_prompt" and i.severity == Severity.INFO for i in issues4)
    assert detector.near_count == 1
    
    # Clearly different
    r5 = minimal_valid_record.copy()
    r5["id"] = "5"
    r5["prompt"] = "முற்றிலும் வித்தியாசமான ஒன்று"
    r5["response"] = "வித்தியாசமான பதில்"
    detector.register(r5["id"], r5["prompt"], "prompt")
    detector.register(r5["id"], r5["response"], "response")
    issues5 = detector.check_against_registered(r5["id"], r5["prompt"], "prompt")
    assert len(issues5) == 0

def test_run_all_checks(minimal_valid_record):
    detector = DuplicateDetector()
    r1 = minimal_valid_record.copy()
    r1["notes"] = "some note" # avoid missing notes info
    
    result = run_all_checks(r1, detector)
    assert result.is_valid
    assert result.quality_score == 100
    assert len(result.issues) == 0

    r2 = minimal_valid_record.copy()
    del r2["prompt"]
    result2 = run_all_checks(r2, detector)
    assert not result2.is_valid
    
    # Verify metadata checks didn't run because of short-circuit (except missing_notes from schema)
    assert not any(i.check_name.startswith("metadata") and i.check_name != "metadata.missing_notes" for i in result2.issues)
    assert any(i.check_name == "schema.missing_field" for i in result2.issues)

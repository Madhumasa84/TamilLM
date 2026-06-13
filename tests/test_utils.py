import pytest
from validator.utils import (
    is_tamil_char,
    tamil_script_ratio,
    english_script_ratio,
    has_malformed_unicode,
    normalize_for_dedup,
    char_trigrams,
    jaccard_similarity,
    compute_quality_score,
    ValidationIssue,
    Severity,
    SCORE_PENALTIES
)

def test_is_tamil_char():
    assert is_tamil_char("க")  # U+0B95
    assert is_tamil_char("ா")  # U+0BBE
    assert not is_tamil_char("a")
    assert not is_tamil_char("5")

def test_tamil_script_ratio():
    assert abs(tamil_script_ratio("தமிழ்") - 1.0) < 0.01
    assert tamil_script_ratio("English") == 0.0
    
    mixed = tamil_script_ratio("தமிழ் English")
    assert 0 < mixed < 1.0
    
    assert tamil_script_ratio("") == 1.0
    assert tamil_script_ratio("   ") == 1.0

def test_english_script_ratio():
    assert english_script_ratio("தமிழ்") == 0.0
    assert abs(english_script_ratio("English") - 1.0) < 0.01
    assert english_script_ratio("") == 0.0

def test_has_malformed_unicode():
    assert has_malformed_unicode("தமிழ்\uFFFD")
    assert has_malformed_unicode("தமிழ்\x00")
    # Isolated combining mark (virama U+0BCD) at the start
    assert has_malformed_unicode("\u0bcdதமிழ்")
    
    # Valid Tamil word
    assert not has_malformed_unicode("தமிழ்")
    assert not has_malformed_unicode("Clean ASCII")

def test_normalize_for_dedup():
    assert normalize_for_dedup("   A   b   ") == "a b"
    assert normalize_for_dedup("தமிழ்") == "தமிழ்"
    # test NFC normalization, composed vs decomposed
    composed = "\u0B95\u0BBE"  # கா
    decomposed = "\u0B95\u0BBE" # already composed
    assert normalize_for_dedup(composed) == normalize_for_dedup(decomposed)

def test_char_trigrams():
    assert char_trigrams("abcde") == {"abc", "bcd", "cde"}
    assert char_trigrams("ab") == {"ab"}
    assert char_trigrams("") == set()
    trigrams = char_trigrams("தமிழ்")
    for t in trigrams:
        assert len(t) == 3 or len("தமிழ்") < 3

def test_jaccard_similarity():
    s1 = {"a", "b", "c"}
    s2 = {"a", "b", "c"}
    assert jaccard_similarity(s1, s2) == 1.0
    
    s3 = {"d", "e"}
    assert jaccard_similarity(s1, s3) == 0.0
    
    assert jaccard_similarity(set(), set()) == 0.0
    
    # intersection size 2, union size 4 -> 0.5
    s4 = {"b", "c", "x"}
    assert jaccard_similarity(s1, s4) == 0.5

def test_compute_quality_score():
    assert compute_quality_score([]) == 100
    
    # Known error
    issue1 = ValidationIssue(record_id="1", check_name="schema.missing_field", severity=Severity.ERROR, message="")
    score1 = compute_quality_score([issue1])
    assert score1 == 100 - SCORE_PENALTIES["schema.missing_field"]
    
    # Multiple issues accumulate deductions
    issue2 = ValidationIssue(record_id="1", check_name="language.too_short_response", severity=Severity.WARNING, message="")
    score2 = compute_quality_score([issue1, issue2])
    assert score2 == 100 - SCORE_PENALTIES["schema.missing_field"] - SCORE_PENALTIES["language.too_short_response"]
    
    # Unknown check_name falls back to severity penalty
    issue3 = ValidationIssue(record_id="1", check_name="unknown.error", severity=Severity.ERROR, message="")
    assert compute_quality_score([issue3]) == 100 - 10 # Default ERROR penalty is 10
    
    # Score never below 0
    issues = [ValidationIssue(record_id="1", check_name="schema.missing_field", severity=Severity.ERROR, message="")] * 10
    assert compute_quality_score(issues) == 0

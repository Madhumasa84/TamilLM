"""
Tamil SFT Dataset Validation — Shared Utilities.

Provides the foundational layer for the validation framework:

* **Data types** — ``Severity``, ``ValidationIssue``, ``RecordResult``
* **Tamil Unicode helpers** — script detection, ratio computation,
  malformed-sequence detection
* **Text normalization & similarity** — NFC normalization, character-level
  trigram generation, Jaccard similarity for near-duplicate detection
* **Quality-score computation** — 100-point base score with per-issue
  deductions
* **Constants** — allowed metadata values, canonical task-type mappings,
  numeric thresholds, score penalties

Design principle: every function here is **pure** (no I/O, no side-effects)
so that it can be called freely from checks, the pipeline orchestrator,
or unit tests.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Any



# Tamil Unicode Constants


TAMIL_BLOCK_START: int = 0x0B80
"""First codepoint of the Tamil Unicode block (U+0B80)."""

TAMIL_BLOCK_END: int = 0x0BFF
"""Last codepoint of the Tamil Unicode block (U+0BFF)."""



# Severity Enum


class Severity(Enum):
    """Validation issue severity.

    * ``ERROR``   — hard failure; the record cannot be used as-is.
    * ``WARNING`` — quality concern; the record should be reviewed.
    * ``INFO``    — informational note; no action required unless
                    the curator sees a pattern.
    """

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"



# Core Data Structures


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """A single validation finding attached to a dataset record.

    Attributes:
        record_id:  The ``id`` of the record (or a synthetic placeholder).
        check_name: Dot-namespaced identifier, e.g. ``schema.missing_field``.
        severity:   One of ``ERROR``, ``WARNING``, ``INFO``.
        message:    Human-readable explanation of the problem.
        field:      Which record field is affected (``None`` for cross-field).
        suggestion: Actionable fix suggestion (``None`` if not applicable).
    """

    record_id: str
    check_name: str
    severity: Severity
    message: str
    field: str | None = None
    suggestion: str | None = None


@dataclass
class RecordResult:
    """Aggregated validation outcome for a single dataset record.

    Attributes:
        record_id:     The ``id`` of the record.
        is_valid:      ``True`` when zero ERRORs were found.
        issues:        All issues discovered by the check suite.
        quality_score: 0–100 score derived from issue penalties.
        record:        The original record dict (for downstream writing).
    """

    record_id: str
    is_valid: bool
    issues: list[ValidationIssue]
    quality_score: int
    record: dict[str, Any]



# Allowed Values & Canonical Mappings


REQUIRED_FIELDS: tuple[str, ...] = (
    "id",
    "prompt",
    "response",
    "register",
    "region",
    "domain",
    "task_type",
)
"""Fields that must be present and non-empty in every record."""

OPTIONAL_FIELDS: tuple[str, ...] = ("notes",)
"""Fields that are encouraged but not strictly required."""

ALL_FIELDS: tuple[str, ...] = REQUIRED_FIELDS + OPTIONAL_FIELDS
"""Union of required and optional fields."""

ALLOWED_REGISTERS: frozenset[str] = frozenset({
    "spoken_colloquial",
    "modern_formal",
    "literary_prose",
    "technical_explanatory",
    "news_formal",
    "culture_history",
    "tanglish_code_switched",
})
"""The closed set of valid register labels."""

CANONICAL_TASK_TYPES: frozenset[str] = frozenset({
    "qa",
    "rewrite",
    "explanation",
    "summarization",
    "classification",
    "advice",
    "creative",
    "style_transfer",
})
"""Canonical task-type values that need no normalization."""

TASK_TYPE_ALIASES: dict[str, str] = {
    # Common non-canonical forms → canonical
    "question-answer": "qa",
    "question_answer": "qa",
    "q&a": "qa",
    "qna": "qa",
    "q-a": "qa",
    "summary": "summarization",
    "summarize": "summarization",
    "explain": "explanation",
    "classify": "classification",
    "create": "creative",
    "writing": "creative",
    "generation": "creative",
    "style-transfer": "style_transfer",
    "style transfer": "style_transfer",
}
"""Maps recognized-but-non-canonical task_type strings to their canonical
form.  Values NOT in this dict AND not in ``CANONICAL_TASK_TYPES`` are
treated as unknown (ERROR)."""

KNOWN_DOMAINS: frozenset[str] = frozenset({
    "everyday",
    "news",
    "literature",
    "technical",
    "culture",
    "history",
    "social",
    "education",
})
"""Domains the project currently tracks.  Unknown domains produce a
WARNING (not an error) because the list is expected to grow."""

KNOWN_REGIONS: frozenset[str] = frozenset({
    "Generic Tamil Nadu",
    "Standard Written Tamil",
    "Chennai",
    "Madurai",
    "Coimbatore",
    "Tirunelveli",
    "Sri Lanka",
    "Malaysia",
    "Singapore",
})
"""Known region labels (English).  Unknown regions produce a
WARNING because new regions can be added at any time."""



# Quality-Score Penalties


SCORE_PENALTIES: dict[str, int] = {
    # Schema
    "schema.duplicate_id":              25,
    "schema.missing_field":             25,
    "schema.empty_field":               15,
    "schema.wrong_type":                15,
    "schema.parse_error":               100,   # unparseable record
    # Metadata
    "metadata.unknown_register":        15,
    "metadata.unknown_task_type":       15,
    "metadata.non_canonical_task_type": 5,
    "metadata.unknown_domain":          5,
    "metadata.unknown_region":          5,
    "metadata.missing_notes":           5,
    # Language quality
    "language.no_tamil_in_prompt":      20,
    "language.no_tamil_in_response":    20,
    "language.excessive_english":       10,
    "language.too_short_response":      10,
    "language.too_long_response":       5,
    "language.malformed_unicode":       15,
    # Naturalness
    "naturalness.excessive_repetition": 10,
    "naturalness.excessive_punctuation": 5,
    "naturalness.unnatural_formatting": 5,
    # Consistency
    "consistency.register_mismatch":        10,
    "consistency.task_type_shape_mismatch":  10,
    # Duplicates
    "duplicate.exact_prompt":           15,
    "duplicate.exact_response":         15,
    "duplicate.near_prompt":            10,
    "duplicate.near_response":          10,
    # Safety
    "safety.dangerous_medical":         15,
    "safety.financial_guarantee":       15,
    "safety.misinformation_pattern":    15,
    "safety.harmful_instructions":      20,
}
"""Maps ``check_name`` - point deduction from the 100-point quality score.
Unknown check names fall back to a severity-based default."""

# Fallback penalties when a check_name is not in SCORE_PENALTIES.
_SEVERITY_FALLBACK_PENALTY: dict[Severity, int] = {
    Severity.ERROR: 10,
    Severity.WARNING: 3,
    Severity.INFO: 0,
}


# Numeric Thresholds

MIN_RESPONSE_LENGTH: int = 20
"""Responses shorter than this (characters) are flagged as too short."""

MAX_RESPONSE_LENGTH: int = 5000
"""Responses longer than this (characters) trigger an informational note."""

MIN_TAMIL_RATIO: float = 0.3
"""Minimum fraction of Tamil script among alphabetic characters."""

MAX_ENGLISH_RATIO: float = 0.5
"""Maximum fraction of Latin-script characters among alphabetic chars."""

NEAR_DUPLICATE_THRESHOLD: float = 0.7
"""Trigram Jaccard similarity at or above this is a near-duplicate."""

REPETITION_THRESHOLD: int = 3
"""A phrase appearing this many times in a response is suspicious."""

LOW_COVERAGE_THRESHOLD: int = 2
"""Category counts at or below this number trigger a coverage warning."""



# Tamil Unicode Helpers


def is_tamil_char(char: str) -> bool:
    """Return ``True`` if *char* belongs to the Tamil Unicode block.

    Covers consonants, vowels, vowel signs, Grantha supplements, Tamil
    digits, and special characters within U+0B80–U+0BFF.
    """
    codepoint = ord(char)
    return TAMIL_BLOCK_START <= codepoint <= TAMIL_BLOCK_END


def tamil_script_ratio(text: str) -> float:
    """Fraction of alphabetic characters that are Tamil script.

    Non-alphabetic characters (digits, punctuation, whitespace) are
    excluded from both numerator and denominator.

    Returns ``1.0`` for empty or purely non-alphabetic text to avoid
    false positives — structural emptiness is caught by schema checks.
    """
    tamil_count = 0
    total_alpha = 0
    for char in text:
        if is_tamil_char(char):
            tamil_count += 1
            total_alpha += 1
        elif char.isalpha():
            total_alpha += 1
    if total_alpha == 0:
        return 1.0
    return tamil_count / total_alpha


def english_script_ratio(text: str) -> float:
    """Fraction of alphabetic characters that are Latin script.

    Mirrors :func:`tamil_script_ratio` but counts ASCII/Latin letters
    in the numerator.  Returns ``0.0`` when no alphabetic characters
    are present.
    """
    latin_count = 0
    total_alpha = 0
    for char in text:
        if is_tamil_char(char):
            total_alpha += 1
        elif char.isalpha():
            latin_count += 1
            total_alpha += 1
    if total_alpha == 0:
        return 0.0
    return latin_count / total_alpha


def has_malformed_unicode(text: str) -> bool:
    """Detect obviously malformed Unicode in text.

    Checks for:

    * U+FFFD replacement characters (sign of encoding errors)
    * NULL bytes embedded in text
    * Isolated combining marks (``\\u0BCD`` etc.) without a preceding
      base character
    """
    if "\ufffd" in text:
        return True
    if "\x00" in text:
        return True
    prev_is_base = False
    for char in text:
        category = unicodedata.category(char)
        if category.startswith("M"):
            if not prev_is_base:
                return True
            prev_is_base = False  # base consumed by this mark
        else:
            prev_is_base = category not in ("Zs", "Cc", "Cf")
    return False



# Text Normalization & Similarity

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_for_dedup(text: str) -> str:
    """Normalize *text* for duplicate comparison.

    1. NFC-normalize Unicode (canonical decomposition → composition).
    2. Collapse all whitespace runs to a single space.
    3. Lowercase Latin characters only (Tamil has no case distinction).
    4. Strip leading/trailing whitespace.
    """
    text = unicodedata.normalize("NFC", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    chars: list[str] = []
    for ch in text:
        if ch.isascii() and ch.isalpha():
            chars.append(ch.lower())
        else:
            chars.append(ch)
    return "".join(chars)


def char_trigrams(text: str) -> set[str]:
    """Generate character-level trigrams from text.

    Character trigrams (as opposed to word n-grams) are well-suited for
    Tamil because the language is agglutinative: word boundaries are less
    reliable than sub-word character sequences for measuring similarity.

    Returns a set of 3-character strings.  For texts shorter than 3
    characters, returns a set containing the full text (or empty set
    for empty input).
    """
    if not text:
        return set()
    if len(text) < 3:
        return {text}
    return {text[i : i + 3] for i in range(len(text) - 2)}


def jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Jaccard similarity coefficient between two sets.

    Defined as ``|A ∩ B| / |A ∪ B|``.
    Returns ``0.0`` when both sets are empty (no evidence of similarity).
    """
    if not set_a and not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0



# Quality-Score Computation

def compute_quality_score(issues: list[ValidationIssue]) -> int:
    """Derive a 0-100 quality score from a list of validation issues.

    Starts at 100 and deducts points per issue.  The penalty for each
    issue is looked up in :data:`SCORE_PENALTIES` by ``check_name``;
    unknown check names fall back to a severity-based default.

    The final score is clamped to ``[0, 100]``.
    """
    score = 100
    for issue in issues:
        penalty = SCORE_PENALTIES.get(issue.check_name)
        if penalty is None:
            penalty = _SEVERITY_FALLBACK_PENALTY.get(issue.severity, 0)
        score -= penalty
    return max(0, score)

"""
Tamil SFT Dataset Validation — Check Library.

Every public function in this module follows the same contract:

    ``(record: dict) → list[ValidationIssue]``

This makes checks **composable**, **independently testable**, and
**free of side-effects**.  The only exception is :class:`DuplicateDetector`,
which is necessarily stateful (it must remember previously seen records).

Checks are grouped by concern:

1. **Schema**       — structural integrity (fields, types, emptiness)
2. **Metadata**     — controlled-vocabulary compliance with three-tier
                      task-type handling (canonical / alias / unknown)
3. **Language**     — Tamil-script ratio, response length, Unicode health
4. **Naturalness**  — heuristic flags for machine-translated or formulaic
                      text (repetition, punctuation storms, list overuse)
5. **Consistency**  — cross-field coherence (register vs. vocabulary,
                      task-type vs. response shape)
6. **Safety**       — keyword/pattern scanning for dangerous medical
                      claims, financial guarantees, misinformation, and
                      harmful instructions
7. **Duplicates**   — exact and near-duplicate detection via normalized
                      text comparison and trigram Jaccard similarity

The top-level :func:`run_all_checks` function wires everything together
and applies short-circuit logic: schema ERRORs skip all content-level
checks to avoid cascading nonsensical warnings.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from validator.utils import (
    ALLOWED_REGISTERS,
    CANONICAL_TASK_TYPES,
    KNOWN_DOMAINS,
    KNOWN_REGIONS,
    MAX_ENGLISH_RATIO,
    MAX_RESPONSE_LENGTH,
    MIN_RESPONSE_LENGTH,
    MIN_TAMIL_RATIO,
    NEAR_DUPLICATE_THRESHOLD,
    OPTIONAL_FIELDS,
    REPETITION_THRESHOLD,
    REQUIRED_FIELDS,
    TASK_TYPE_ALIASES,
    RecordResult,
    Severity,
    ValidationIssue,
    char_trigrams,
    compute_quality_score,
    english_script_ratio,
    has_malformed_unicode,
    jaccard_similarity,
    normalize_for_dedup,
    tamil_script_ratio,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. Schema Checks
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def check_schema(record: dict[str, Any]) -> list[ValidationIssue]:
    """Validate structural integrity of a single record.

    Checks for:

    * Missing required fields → ``schema.missing_field`` (ERROR)
    * Non-string field values → ``schema.wrong_type``    (ERROR)
    * Empty-string fields     → ``schema.empty_field``   (ERROR)
    * Missing or empty notes  → ``metadata.missing_notes`` (INFO)

    This check runs **first** in the pipeline.  If it produces any
    ERROR-level issues, downstream content checks are skipped.
    """
    issues: list[ValidationIssue] = []
    record_id: str = record.get("id", "<missing_id>")

    # ── Required fields ──────────────────────────────────────────────
    for field_name in REQUIRED_FIELDS:
        if field_name not in record:
            issues.append(ValidationIssue(
                record_id=record_id,
                check_name="schema.missing_field",
                severity=Severity.ERROR,
                message=f"Required field '{field_name}' is missing",
                field=field_name,
            ))
        elif not isinstance(record[field_name], str):
            actual_type = type(record[field_name]).__name__
            issues.append(ValidationIssue(
                record_id=record_id,
                check_name="schema.wrong_type",
                severity=Severity.ERROR,
                message=(
                    f"Field '{field_name}' must be a string, "
                    f"got {actual_type}"
                ),
                field=field_name,
                suggestion=f"Convert to string: str({record[field_name]!r})",
            ))
        elif not record[field_name].strip():
            issues.append(ValidationIssue(
                record_id=record_id,
                check_name="schema.empty_field",
                severity=Severity.ERROR,
                message=f"Required field '{field_name}' is empty",
                field=field_name,
            ))

    # ── Optional fields ──────────────────────────────────────────────
    notes = record.get("notes")
    if notes is None or (isinstance(notes, str) and not notes.strip()):
        issues.append(ValidationIssue(
            record_id=record_id,
            check_name="metadata.missing_notes",
            severity=Severity.INFO,
            message=(
                "Field 'notes' is missing or empty; notes help curators "
                "understand edge cases and design decisions"
            ),
            field="notes",
            suggestion="Add a brief note explaining this record's purpose",
        ))

    return issues


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. Metadata Checks
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def check_metadata(record: dict[str, Any]) -> list[ValidationIssue]:
    """Validate metadata fields against controlled vocabularies.

    **Three-tier task_type handling** (per evaluation-engineering guidance):

    1. Canonical value (e.g. ``"qa"``)           → no issue
    2. Known alias (e.g. ``"question-answer"``)   → WARNING + suggestion
    3. Unknown value                              → ERROR

    Register uses a closed set (ERROR for unknown).
    Domain and region use open-ish sets (WARNING for unknown).
    """
    issues: list[ValidationIssue] = []
    record_id: str = record.get("id", "<missing_id>")

    # ── Flag ─────────────────────────────────────────────────────────
    ALLOWED_FLAGS = frozenset({
        "romanized_tamil_artifact",
        "unexpected_latin_text", 
        "allowed_code_switch",
    })
    
    flag = record.get("flag")
    if flag is not None:
        if not isinstance(flag, str) or flag not in ALLOWED_FLAGS:
            issues.append(ValidationIssue(
                record_id=record_id,
                check_name="metadata.unknown_flag",
                severity=Severity.ERROR,
                message=f"Unknown flag value '{flag}'",
                field="flag",
                suggestion=f"Allowed: {', '.join(sorted(ALLOWED_FLAGS))}",
            ))

    # ── Register ─────────────────────────────────────────────────────
    register = record.get("register", "")
    if isinstance(register, str) and register and register not in ALLOWED_REGISTERS:
        issues.append(ValidationIssue(
            record_id=record_id,
            check_name="metadata.unknown_register",
            severity=Severity.ERROR,
            message=f"Unknown register '{register}'",
            field="register",
            suggestion=(
                f"Allowed values: {', '.join(sorted(ALLOWED_REGISTERS))}"
            ),
        ))

    # ── Task type (three-tier) ───────────────────────────────────────
    task_type = record.get("task_type", "")
    if isinstance(task_type, str) and task_type:
        if task_type in CANONICAL_TASK_TYPES:
            pass  # Canonical — no issue
        elif task_type.lower() in TASK_TYPE_ALIASES:
            canonical = TASK_TYPE_ALIASES[task_type.lower()]
            issues.append(ValidationIssue(
                record_id=record_id,
                check_name="metadata.non_canonical_task_type",
                severity=Severity.WARNING,
                message=f"Non-canonical task_type '{task_type}'",
                field="task_type",
                suggestion=canonical,
            ))
        else:
            issues.append(ValidationIssue(
                record_id=record_id,
                check_name="metadata.unknown_task_type",
                severity=Severity.ERROR,
                message=f"Unknown task_type '{task_type}'",
                field="task_type",
                suggestion=(
                    "Allowed values: "
                    f"{', '.join(sorted(CANONICAL_TASK_TYPES))}"
                ),
            ))

    # ── Domain (open set — WARNING) ──────────────────────────────────
    domain = record.get("domain", "")
    if isinstance(domain, str) and domain and domain not in KNOWN_DOMAINS:
        issues.append(ValidationIssue(
            record_id=record_id,
            check_name="metadata.unknown_domain",
            severity=Severity.WARNING,
            message=(
                f"Unknown domain '{domain}'; add to known domains "
                f"if intentional"
            ),
            field="domain",
            suggestion=(
                f"Known domains: {', '.join(sorted(KNOWN_DOMAINS))}"
            ),
        ))

    # ── Region (open set — WARNING) ──────────────────────────────────
    region = record.get("region", "")
    if isinstance(region, str) and region and region not in KNOWN_REGIONS:
        sample = ", ".join(sorted(KNOWN_REGIONS)[:5])
        issues.append(ValidationIssue(
            record_id=record_id,
            check_name="metadata.unknown_region",
            severity=Severity.WARNING,
            message=(
                f"Unknown region '{region}'; add to known regions "
                f"if intentional"
            ),
            field="region",
            suggestion=f"Known regions include: {sample}, …",
        ))

    return issues


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. Language Quality Checks
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def check_language_quality(record: dict[str, Any]) -> list[ValidationIssue]:
    """Validate language-level quality of prompt and response text.

    Checks:

    * Tamil script presence (ratio below threshold in prompt/response)
    * Excessive English content in response
    * Response too short or too long
    * Malformed Unicode sequences in either field
    """
    issues: list[ValidationIssue] = []
    record_id: str = record.get("id", "<missing_id>")
    prompt: str = record.get("prompt", "")
    response: str = record.get("response", "")

    # ── Tamil presence in prompt ─────────────────────────────────────
    if prompt:
        ratio = tamil_script_ratio(prompt)
        if ratio < MIN_TAMIL_RATIO:
            issues.append(ValidationIssue(
                record_id=record_id,
                check_name="language.no_tamil_in_prompt",
                severity=Severity.WARNING,
                message=(
                    f"Prompt has low Tamil content "
                    f"({ratio:.0%} Tamil, threshold {MIN_TAMIL_RATIO:.0%})"
                ),
                field="prompt",
                suggestion="Ensure the prompt is primarily in Tamil",
            ))

    # ── Tamil presence in response ───────────────────────────────────
    if response:
        ratio = tamil_script_ratio(response)
        if ratio < MIN_TAMIL_RATIO:
            issues.append(ValidationIssue(
                record_id=record_id,
                check_name="language.no_tamil_in_response",
                severity=Severity.WARNING,
                message=(
                    f"Response has low Tamil content "
                    f"({ratio:.0%} Tamil, threshold {MIN_TAMIL_RATIO:.0%})"
                ),
                field="response",
                suggestion="Ensure the response is primarily in Tamil",
            ))

    # ── Excessive English in response ────────────────────────────────
    if response:
        eng_ratio = english_script_ratio(response)
        if eng_ratio > MAX_ENGLISH_RATIO:
            issues.append(ValidationIssue(
                record_id=record_id,
                check_name="language.excessive_english",
                severity=Severity.WARNING,
                message=(
                    f"Response has high English content "
                    f"({eng_ratio:.0%} Latin, max {MAX_ENGLISH_RATIO:.0%})"
                ),
                field="response",
                suggestion="Reduce English; use Tamil equivalents where possible",
            ))

    # ── Response length ──────────────────────────────────────────────
    if response:
        length = len(response.strip())
        if length < MIN_RESPONSE_LENGTH:
            issues.append(ValidationIssue(
                record_id=record_id,
                check_name="language.too_short_response",
                severity=Severity.WARNING,
                message=(
                    f"Response is very short ({length} chars, "
                    f"minimum {MIN_RESPONSE_LENGTH})"
                ),
                field="response",
                suggestion="Expand the response to provide more value",
            ))
        elif length > MAX_RESPONSE_LENGTH:
            issues.append(ValidationIssue(
                record_id=record_id,
                check_name="language.too_long_response",
                severity=Severity.INFO,
                message=(
                    f"Response is very long ({length} chars, "
                    f"suggested max {MAX_RESPONSE_LENGTH})"
                ),
                field="response",
            ))

    # ── Malformed Unicode ────────────────────────────────────────────
    for field_name, text in [("prompt", prompt), ("response", response)]:
        if text and has_malformed_unicode(text):
            issues.append(ValidationIssue(
                record_id=record_id,
                check_name="language.malformed_unicode",
                severity=Severity.ERROR,
                message=f"Malformed Unicode detected in '{field_name}'",
                field=field_name,
                suggestion="Check for encoding errors or copy-paste artifacts",
            ))

    return issues


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. Naturalness Heuristics
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Pre-compiled patterns for performance.
_EXCESSIVE_PUNCT_RE = re.compile(r"[!?]{3,}|\.{4,}|[!?.]{5,}")
_NUMBERED_ITEM_RE = re.compile(r"^\d+[.)]\s", re.MULTILINE)
_BULLET_ITEM_RE = re.compile(r"^[-•●▪]\s", re.MULTILINE)


def check_naturalness(record: dict[str, Any]) -> list[ValidationIssue]:
    """Flag responses that exhibit machine-generated or unnatural patterns.

    Heuristics (not ML):

    * **Excessive repetition** — same phrase ≥ N times
    * **Punctuation storms** — ``!!!``, ``????``, ``....`` chains
    * **Formulaic structure** — excessive numbered/bulleted lists
      (>7 items in a spoken-register response)

    These produce WARNINGs or INFOs — never ERRORs — because false
    positives are expected.  The curator makes the final call.
    """
    issues: list[ValidationIssue] = []
    record_id: str = record.get("id", "<missing_id>")
    response: str = record.get("response", "")
    register: str = record.get("register", "")

    if not response:
        return issues

    # ── Excessive repetition ─────────────────────────────────────────
    # Split on sentence boundaries and check for repeated phrases.
    delimiters = re.compile(r"[.!?।\n]")
    phrases = [
        p.strip()
        for p in delimiters.split(response)
        if len(p.strip()) > 10
    ]
    if phrases:
        phrase_counts = Counter(phrases)
        for phrase, count in phrase_counts.most_common(1):
            if count >= REPETITION_THRESHOLD:
                preview = phrase[:60] + ("…" if len(phrase) > 60 else "")
                issues.append(ValidationIssue(
                    record_id=record_id,
                    check_name="naturalness.excessive_repetition",
                    severity=Severity.WARNING,
                    message=(
                        f"Phrase repeated {count} times: '{preview}'"
                    ),
                    field="response",
                    suggestion="Review for machine-translated or templated text",
                ))

    # ── Excessive punctuation ────────────────────────────────────────
    if _EXCESSIVE_PUNCT_RE.search(response):
        issues.append(ValidationIssue(
            record_id=record_id,
            check_name="naturalness.excessive_punctuation",
            severity=Severity.WARNING,
            message="Response contains excessive punctuation (!!!, ???, etc.)",
            field="response",
            suggestion="Use restrained punctuation for natural text",
        ))

    # ── Unnatural formatting (formulaic lists) ───────────────────────
    numbered = _NUMBERED_ITEM_RE.findall(response)
    bullets = _BULLET_ITEM_RE.findall(response)
    list_items = len(numbered) + len(bullets)
    if list_items > 7:
        severity = Severity.WARNING if register == "spoken" else Severity.INFO
        issues.append(ValidationIssue(
            record_id=record_id,
            check_name="naturalness.unnatural_formatting",
            severity=severity,
            message=(
                f"Response contains {list_items} list items; "
                f"may indicate formulaic generation"
            ),
            field="response",
            suggestion=(
                "Consider whether a list-heavy format is natural for "
                "this register and task type"
            ),
        ))

    return issues


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. Consistency Checks
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Formal Tamil verb endings / particles that are unlikely in spoken register.
_FORMAL_INDICATORS: list[re.Pattern[str]] = [
    re.compile(pattern)
    for pattern in [
        r"ஆகும்\b",
        r"ஆகின்றன",
        r"உள்ளன\b",
        r"படுகின்றன",
        r"படுகிறது",
        r"வேண்டும்\b",
        r"செய்யப்பட",
        r"வழங்கப்பட",
        r"அறிமுகப்படுத்தப்பட",
        r"ஊக்குவிக்கப்பட",
        r"உறுதி\s*செய்",
        r"கொள்ளவும்\s*[.।]",
        r"என்பதாகும்",
        r"ஆயினும்\b",
    ]
]

# Casual Tanglish / spoken markers unlikely in literary register.
_CASUAL_INDICATORS: list[re.Pattern[str]] = [
    re.compile(pattern)
    for pattern in [
        r"\bட்ரை\b",
        r"\bசெக்\b",
        r"\bஓகே\b",
        r"\bசூப்பர்\b",
        r"\bகூல்\b",
        r"பண்ணு\b",
        r"இல்லனா\b",
        r"\bமச்சான்\b",
        r"\bமச்சி\b",
        r"\bடா\b",
        r"\bடி\b",
        r"\bபண்றது\b",
        r"\bபோயிடு\b",
    ]
]


def check_consistency(record: dict[str, Any]) -> list[ValidationIssue]:
    """Detect cross-field incoherence in a record.

    1. **Register vs. vocabulary** — spoken records should not read
       like formal essays; literary records should not contain casual
       Tanglish.
    2. **Task-type vs. response shape** — summarizations should be
       shorter than their source text; classifications should not be
       extremely verbose.
    """
    issues: list[ValidationIssue] = []
    record_id: str = record.get("id", "<missing_id>")
    register: str = record.get("register", "")
    task_type: str = record.get("task_type", "")
    prompt: str = record.get("prompt", "")
    response: str = record.get("response", "")

    if not response or not register:
        return issues

    # ── Register vs. vocabulary ──────────────────────────────────────
    if register == "spoken":
        formal_hits = sum(
            1 for pattern in _FORMAL_INDICATORS
            if pattern.search(response)
        )
        if formal_hits >= 3:
            issues.append(ValidationIssue(
                record_id=record_id,
                check_name="consistency.register_mismatch",
                severity=Severity.WARNING,
                message=(
                    f"Register is 'spoken' but response contains "
                    f"{formal_hits} formal Tamil indicators"
                ),
                field="register",
                suggestion=(
                    "Change register to 'formal', or rewrite the "
                    "response in spoken style"
                ),
            ))

    elif register == "literary":
        casual_hits = sum(
            1 for pattern in _CASUAL_INDICATORS
            if pattern.search(response)
        )
        if casual_hits >= 2:
            issues.append(ValidationIssue(
                record_id=record_id,
                check_name="consistency.register_mismatch",
                severity=Severity.WARNING,
                message=(
                    f"Register is 'literary' but response contains "
                    f"{casual_hits} casual/spoken indicators"
                ),
                field="register",
                suggestion=(
                    "Change register to 'spoken', or rewrite the "
                    "response in literary style"
                ),
            ))

    elif register == "formal":
        casual_hits = sum(
            1 for pattern in _CASUAL_INDICATORS
            if pattern.search(response)
        )
        if casual_hits >= 3:
            issues.append(ValidationIssue(
                record_id=record_id,
                check_name="consistency.register_mismatch",
                severity=Severity.WARNING,
                message=(
                    f"Register is 'formal' but response contains "
                    f"{casual_hits} casual/spoken indicators"
                ),
                field="register",
                suggestion=(
                    "Change register to 'spoken', or rewrite the "
                    "response in formal style"
                ),
            ))

    # ── Task type vs. response shape ─────────────────────────────────
    # Resolve aliases for shape checking.
    effective_tt = task_type
    if task_type.lower() in TASK_TYPE_ALIASES:
        effective_tt = TASK_TYPE_ALIASES[task_type.lower()]

    if effective_tt == "summarization" and prompt and response:
        # A summary longer than 1.5× the input is suspicious
        # (only check when the prompt contains substantial text to summarize).
        if len(prompt) > 100 and len(response) > len(prompt) * 1.5:
            issues.append(ValidationIssue(
                record_id=record_id,
                check_name="consistency.task_type_shape_mismatch",
                severity=Severity.INFO,
                message=(
                    f"Summarization response ({len(response)} chars) is "
                    f"longer than input ({len(prompt)} chars)"
                ),
                field="task_type",
                suggestion="Verify this is truly a summarization task",
            ))

    if effective_tt == "classification" and response:
        if len(response) > 1500:
            issues.append(ValidationIssue(
                record_id=record_id,
                check_name="consistency.task_type_shape_mismatch",
                severity=Severity.INFO,
                message=(
                    f"Classification response is unusually long "
                    f"({len(response)} chars)"
                ),
                field="task_type",
                suggestion=(
                    "Consider if this is an explanation rather than "
                    "a classification"
                ),
            ))

    return issues


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. Safety Checks
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Each tuple: (compiled regex, human-readable description).
# Patterns are bilingual (Tamil + English) to catch mixed-language content.

_MEDICAL_DANGER_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:guaranteed|உத்தரவாத).{0,40}(?:cure|குணம்|குணமாகும்)", re.IGNORECASE),
     "Guaranteed cure claim"),
    (re.compile(r"(?:100\s*%|நூறு\s*சதவீத).{0,30}(?:cure|குணம்|குணமாகும்)", re.IGNORECASE),
     "100% cure claim"),
    (re.compile(r"(?:stop|நிறுத்து|நிறுத்தி).{0,30}(?:medication|medicine|மருந்து)", re.IGNORECASE),
     "Advice to stop medication"),
    # Tamil word order: 'டாக்டர் தேவையில்லை' (doctor + no-need)
    (re.compile(r"(?:no\s*need|தேவையில்லை).{0,30}(?:doctor|டாக்டர்|மருத்துவர்)", re.IGNORECASE),
     "Advice to avoid medical consultation"),
    (re.compile(r"(?:doctor|டாக்டர்|மருத்துவர்).{0,30}(?:no\s*need|தேவையில்லை|வேண்டாம்)", re.IGNORECASE),
     "Advice to avoid medical consultation"),
    (re.compile(r"(?:diabetes|சர்க்கரை\s*(?:நோய்|வியாதி)).{0,40}(?:cure|completely|முழுமையாக\s*குணம்)", re.IGNORECASE),
     "Diabetes cure claim"),
    (re.compile(r"(?:cancer|புற்றுநோய்).{0,40}(?:cure|குணமாகும்|completely)", re.IGNORECASE),
     "Cancer cure claim"),
]

_FINANCIAL_DANGER_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:guaranteed|உத்தரவாத).{0,40}(?:profit|return|லாபம்|வருமானம்)", re.IGNORECASE),
     "Guaranteed financial returns"),
    (re.compile(r"(?:100\s*%|நூறு\s*சதவீத).{0,30}(?:return|profit|லாபம்)", re.IGNORECASE),
     "100% return claim"),
    (re.compile(r"(?:risk[\s-]*free|ரிஸ்க்\s*இல்லாம).{0,30}(?:invest|முதலீடு)", re.IGNORECASE),
     "Risk-free investment claim"),
    (re.compile(r"double.{0,15}money|பணம்.{0,15}இரட்டிப்பு", re.IGNORECASE),
     "Money-doubling claim"),
]

_MISINFORMATION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:5\s*G|5ஜி).{0,40}(?:virus|வைரஸ்|corona|கொரோனா)", re.IGNORECASE),
     "5G-virus conspiracy"),
    (re.compile(r"(?:vaccine|தடுப்பூசி).{0,40}(?:chip|சிப்|track|கண்காணி|autism|ஆட்டிசம்)", re.IGNORECASE),
     "Vaccine conspiracy"),
    (re.compile(r"(?:earth|பூமி).{0,15}(?:flat|தட்டை)", re.IGNORECASE),
     "Flat-earth claim"),
]

_HARMFUL_INSTRUCTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:make|செய்|தயாரி).{0,40}(?:bomb|வெடி|explosive|குண்டு)", re.IGNORECASE),
     "Explosive/weapon instructions"),
    (re.compile(r"(?:hack|ஹேக்|ஹாக்).{0,40}(?:password|கடவுச்சொல்|account|கணக்கு)", re.IGNORECASE),
     "Hacking instructions"),
    (re.compile(r"(?:poison|விஷம்).{0,40}(?:make|செய்|prepare|தயாரி)", re.IGNORECASE),
     "Poison preparation instructions"),
    (re.compile(r"(?:suicide|தற்கொலை).{0,40}(?:how|method|எப்படி|வழி)", re.IGNORECASE),
     "Self-harm instructions"),
]


def check_safety(record: dict[str, Any]) -> list[ValidationIssue]:
    """Scan response text for potentially unsafe content patterns.

    Uses bilingual keyword/regex patterns (not a classifier) to flag
    records for **human review**.  The goal is to surface risky content,
    not to be a content-moderation system.

    Categories:

    * ``safety.dangerous_medical``    — cure claims, stop-medication advice
    * ``safety.financial_guarantee``  — guaranteed profits, risk-free claims
    * ``safety.misinformation_pattern`` — conspiracy theories, pseudoscience
    * ``safety.harmful_instructions`` — weapons, hacking, self-harm

    All findings are WARNINGs — the curator decides whether the content
    is genuinely harmful or is safely contextualized (e.g., a record
    that *debunks* misinformation may trigger these patterns).
    """
    issues: list[ValidationIssue] = []
    record_id: str = record.get("id", "<missing_id>")
    response: str = record.get("response", "")

    if not response:
        return issues

    pattern_groups: list[tuple[str, list[tuple[re.Pattern[str], str]], str]] = [
        (
            "safety.dangerous_medical",
            _MEDICAL_DANGER_PATTERNS,
            "Review for medical safety; consider adding a disclaimer",
        ),
        (
            "safety.financial_guarantee",
            _FINANCIAL_DANGER_PATTERNS,
            "Review for financial safety; avoid guaranteed-outcome claims",
        ),
        (
            "safety.misinformation_pattern",
            _MISINFORMATION_PATTERNS,
            "Review for factual accuracy",
        ),
        (
            "safety.harmful_instructions",
            _HARMFUL_INSTRUCTION_PATTERNS,
            "Review carefully; remove or add strong safety disclaimers",
        ),
    ]

    for check_name, patterns, suggestion in pattern_groups:
        for compiled_re, description in patterns:
            if compiled_re.search(response):
                issues.append(ValidationIssue(
                    record_id=record_id,
                    check_name=check_name,
                    severity=Severity.WARNING,
                    message=f"Potential safety concern: {description}",
                    field="response",
                    suggestion=suggestion,
                ))
                break  # One match per category is sufficient

    return issues


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. Duplicate Detection
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class DuplicateDetector:
    """Stateful duplicate detector that accumulates records over time.

    Unlike the pure-function checks, duplicate detection requires memory
    of previously seen records.  This class encapsulates that state while
    exposing the same ``check(record) → list[ValidationIssue]`` interface.

    Detection methods:

    * **Exact duplicates** — normalized text identity (``dict`` lookup).
    * **Near duplicates** — character-level trigram Jaccard similarity
      above a configurable threshold.  Trigrams suit Tamil's agglutinative
      morphology better than word-level approaches.
    """

    def __init__(
        self,
        near_duplicate_threshold: float = NEAR_DUPLICATE_THRESHOLD,
    ) -> None:
        self._threshold = near_duplicate_threshold
        # Normalized text → first record_id that introduced it.
        self._seen_prompts: dict[str, str] = {}
        self._seen_responses: dict[str, str] = {}
        # record_id → (normalized_text, trigram_set) for near-dupe search.
        self._prompt_trigrams: dict[str, tuple[str, set[str]]] = {}
        self._response_trigrams: dict[str, tuple[str, set[str]]] = {}
        # Running count of duplicate findings.
        self.exact_count: int = 0
        self.near_count: int = 0

    def register(self, record_id: str, text: str, field_name: str) -> None:
        """Register text for future lookup without checking."""
        normalized = normalize_for_dedup(text)
        
        seen_exact = self._seen_prompts if field_name == "prompt" else self._seen_responses
        seen_trigrams = self._prompt_trigrams if field_name == "prompt" else self._response_trigrams
        
        if normalized not in seen_exact:
            seen_exact[normalized] = record_id
            seen_trigrams[record_id] = (normalized, char_trigrams(normalized))

    def check_against_registered(
        self, record_id: str, text: str, field_name: str
    ) -> list[ValidationIssue]:
        """Checks this text against all previously registered texts."""
        issues: list[ValidationIssue] = []
        normalized = normalize_for_dedup(text)

        seen_exact = self._seen_prompts if field_name == "prompt" else self._seen_responses
        seen_trigrams = self._prompt_trigrams if field_name == "prompt" else self._response_trigrams

        # ── Exact duplicate ──────────────────────────────────────────
        if normalized in seen_exact and seen_exact[normalized] != record_id:
            original_id = seen_exact[normalized]
            issues.append(ValidationIssue(
                record_id=record_id,
                check_name=f"duplicate.exact_{field_name}",
                severity=Severity.WARNING,
                message=(
                    f"Exact duplicate {field_name} "
                    f"(identical to {original_id})"
                ),
                field=field_name,
            ))
            self.exact_count += 1
            return issues  # Skip near-dupe check — exact is stronger

        # ── Near duplicate ───────────────────────────────────────────
        trigrams = char_trigrams(normalized)
        for other_id, (_other_text, other_trigrams) in seen_trigrams.items():
            if other_id == record_id:
                continue
            similarity = jaccard_similarity(trigrams, other_trigrams)
            if similarity >= self._threshold:
                issues.append(ValidationIssue(
                    record_id=record_id,
                    check_name=f"duplicate.near_{field_name}",
                    severity=Severity.INFO,
                    message=(
                        f"Near-duplicate {field_name} "
                        f"(Jaccard {similarity:.2f} with {other_id})"
                    ),
                    field=field_name,
                    suggestion=(
                        f"Compare with {other_id} and decide which to keep"
                    ),
                ))
                self.near_count += 1
                break  # One near-dupe match is enough to flag

        return issues


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Pipeline Entry Point
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_all_checks(
    record: dict[str, Any],
    duplicate_detector: DuplicateDetector,
) -> RecordResult:
    """Run the full check suite on a single record.

    Execution order:

    1. Schema checks (hard gate)
    2. Metadata checks
    3. Language quality checks
    4. Naturalness heuristics
    5. Consistency checks
    6. Safety checks
    7. Duplicate detection

    **Short-circuit rule**: if schema checks produce any ERROR, steps
    2–7 are skipped entirely.  A record with missing fields cannot be
    meaningfully evaluated for naturalness or safety, and attempting
    to do so would produce misleading warnings.

    Returns a :class:`RecordResult` with all issues and a computed
    quality score.
    """
    all_issues: list[ValidationIssue] = []

    # Step 1: Schema (always runs)
    schema_issues = check_schema(record)
    all_issues.extend(schema_issues)

    has_schema_errors = any(
        issue.severity == Severity.ERROR for issue in schema_issues
    )

    # Steps 2–6: content-level checks (skipped on schema errors)
    if not has_schema_errors:
        all_issues.extend(check_metadata(record))
        all_issues.extend(check_language_quality(record))
        all_issues.extend(check_naturalness(record))
        all_issues.extend(check_consistency(record))
        all_issues.extend(check_safety(record))

    # Step 7: Duplicate detection (runs regardless of schema validity
    # as long as the prompt/response fields are valid strings)
    record_id = record.get("id", "<missing_id>")
    prompt = record.get("prompt")
    response = record.get("response")

    if isinstance(prompt, str) and prompt.strip():
        all_issues.extend(duplicate_detector.check_against_registered(
            record_id=record_id, text=prompt, field_name="prompt"
        ))
    if isinstance(response, str) and response.strip():
        all_issues.extend(duplicate_detector.check_against_registered(
            record_id=record_id, text=response, field_name="response"
        ))

    # Derive validity and quality score
    is_valid = not any(
        issue.severity == Severity.ERROR for issue in all_issues
    )
    quality_score = compute_quality_score(all_issues)

    return RecordResult(
        record_id=record.get("id", "<missing_id>"),
        is_valid=is_valid,
        issues=all_issues,
        quality_score=quality_score,
        record=record,
    )

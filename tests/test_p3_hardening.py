"""
P3 Validator Hardening — Test Suite.

Tests all four P3 features:

1. Config file for thresholds (ValidatorConfig dataclass + JSON loading)
2. Strict mode (WARNING → ERROR escalation for configured checks)
3. Machine-readable CI summary (CI_SUMMARY output line)
4. Windows stdout hardening (UTF-8 wrapper already in place)

Every existing test continues to pass unchanged — this file only adds.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from validator.checks import (
    DuplicateDetector,
    check_language_quality,
    run_all_checks,
)
from validator.config import ValidatorConfig
from validator.utils import (
    LOW_COVERAGE_THRESHOLD,
    MAX_ENGLISH_RATIO,
    MAX_RESPONSE_LENGTH,
    MIN_RESPONSE_LENGTH,
    MIN_TAMIL_RATIO,
    NEAR_DUPLICATE_THRESHOLD,
    REPETITION_THRESHOLD,
    Severity,
)
from validator.validator import SFTValidator

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _valid_record(record_id: str = "rec_001", **overrides) -> dict:
    """Return a minimal valid SFT record, with optional field overrides."""
    base = {
        "id": record_id,
        "prompt": "இது ஒரு சோதனை கேள்வி?",
        "response": "ஆம், இது ஒரு சோதனை பதில் ஆகும்.",
        "register": "spoken_colloquial",
        "region": "Generic Tamil Nadu",
        "domain": "everyday",
        "task_type": "qa",
        "notes": "test record",
    }
    base.update(overrides)
    return base


def _english_heavy_record(record_id: str = "eng_001") -> dict:
    """Return a record whose response has >50% Latin chars (triggers
    language.excessive_english WARNING)."""
    return _valid_record(
        record_id=record_id,
        response=(
            "This response is written in English and has very high Latin "
            "content ratio — more than fifty percent — compared to "
            "Tamil content. \u0b86\u0bae\u0bcd."
        ),
        register="tanglish_code_switched",
        flag="allowed_code_switch",
    )


def _run_validate_sft(args: list[str]) -> subprocess.CompletedProcess:
    """Run validate_sft.py as a subprocess and return the result."""
    venv_python = Path(sys.executable)
    project_root = Path(__file__).parent.parent
    return subprocess.run(
        [str(venv_python), str(project_root / "validate_sft.py")] + args,
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Feature 1 — Config dataclass & JSON loading
# ─────────────────────────────────────────────────────────────────────────────

class TestConfigDefault:
    """ValidatorConfig.default() must reproduce all legacy constants."""

    def test_config_default_matches_legacy_constants(self):
        """Default config values must match the hard-coded constants in utils.py."""
        cfg = ValidatorConfig.default()
        assert cfg.min_response_length == MIN_RESPONSE_LENGTH
        assert cfg.max_response_length == MAX_RESPONSE_LENGTH
        assert cfg.min_tamil_ratio == MIN_TAMIL_RATIO
        assert cfg.max_english_ratio == MAX_ENGLISH_RATIO
        assert cfg.near_duplicate_threshold == NEAR_DUPLICATE_THRESHOLD
        assert cfg.repetition_threshold == REPETITION_THRESHOLD
        assert cfg.low_coverage_threshold == LOW_COVERAGE_THRESHOLD

    def test_config_strict_mode_off_by_default(self):
        cfg = ValidatorConfig.default()
        assert cfg.strict_mode is False

    def test_config_strict_checks_non_empty_by_default(self):
        cfg = ValidatorConfig.default()
        assert len(cfg.strict_checks) > 0
        assert "language.excessive_english" in cfg.strict_checks

    def test_config_default_json_file_matches_dataclass(self):
        """validator/config.default.json must contain the same values as
        ValidatorConfig.default()."""
        json_path = Path(__file__).parent.parent / "validator" / "config.default.json"
        assert json_path.exists(), "validator/config.default.json is missing"
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        cfg = ValidatorConfig.default()
        assert data["min_response_length"] == cfg.min_response_length
        assert data["max_response_length"] == cfg.max_response_length
        assert data["min_tamil_ratio"] == cfg.min_tamil_ratio
        assert data["max_english_ratio"] == cfg.max_english_ratio
        assert data["near_duplicate_threshold"] == cfg.near_duplicate_threshold
        assert data["repetition_threshold"] == cfg.repetition_threshold
        assert data["low_coverage_threshold"] == cfg.low_coverage_threshold


class TestConfigFromJson:
    """ValidatorConfig.from_json() must load custom thresholds correctly."""

    def test_config_from_json_custom_thresholds(self, tmp_path):
        config_data = {
            "min_response_length": 50,
            "max_response_length": 2000,
            "min_tamil_ratio": 0.5,
            "max_english_ratio": 0.2,
            "near_duplicate_threshold": 0.8,
            "repetition_threshold": 2,
            "low_coverage_threshold": 1,
            "strict_mode": False,
            "strict_checks": ["language.excessive_english"],
        }
        config_file = tmp_path / "test_config.json"
        config_file.write_text(json.dumps(config_data), encoding="utf-8")

        cfg = ValidatorConfig.from_json(str(config_file))

        assert cfg.min_response_length == 50
        assert cfg.max_response_length == 2000
        assert cfg.min_tamil_ratio == 0.5
        assert cfg.max_english_ratio == 0.2
        assert cfg.near_duplicate_threshold == 0.8
        assert cfg.repetition_threshold == 2
        assert cfg.low_coverage_threshold == 1
        assert cfg.strict_mode is False
        assert cfg.strict_checks == ["language.excessive_english"]

    def test_config_from_json_partial_file_uses_defaults(self, tmp_path):
        """A JSON file with only some keys should fall back to defaults."""
        config_data = {"min_response_length": 99}
        config_file = tmp_path / "partial.json"
        config_file.write_text(json.dumps(config_data), encoding="utf-8")

        cfg = ValidatorConfig.from_json(str(config_file))
        assert cfg.min_response_length == 99
        assert cfg.max_response_length == MAX_RESPONSE_LENGTH
        assert cfg.min_tamil_ratio == MIN_TAMIL_RATIO

    def test_config_from_json_unknown_keys_ignored(self, tmp_path):
        """Extra keys in the JSON file must be silently ignored."""
        config_data = {
            "min_response_length": 30,
            "unknown_future_setting": True,
        }
        config_file = tmp_path / "extra_keys.json"
        config_file.write_text(json.dumps(config_data), encoding="utf-8")

        cfg = ValidatorConfig.from_json(str(config_file))
        assert cfg.min_response_length == 30

    def test_config_from_json_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            ValidatorConfig.from_json("/nonexistent/path/config.json")


class TestConfigThresholdsApplied:
    """Custom config thresholds must change check outcomes."""

    def test_custom_max_english_ratio_applied(self):
        """A very low max_english_ratio should flag more English content."""
        record = _valid_record(
            response="ஆம், this has some English words mixed in carefully.",
            register="tanglish_code_switched",
            flag="allowed_code_switch",
        )
        # Default threshold may or may not flag this; with max_english_ratio=0.01
        # any Latin content should trip excessive_english.
        tight = ValidatorConfig(max_english_ratio=0.01)
        issues_tight = check_language_quality(record, config=tight)
        assert any(
            i.check_name == "language.excessive_english" for i in issues_tight
        ), "Custom max_english_ratio=0.01 must flag mixed English content"

    def test_custom_min_response_length_applied(self):
        record = _valid_record(response="ஆம் இது சரி.")  # short but Tamil
        tight = ValidatorConfig(min_response_length=100)
        issues = check_language_quality(record, config=tight)
        assert any(i.check_name == "language.too_short_response" for i in issues)

        # Default threshold of 20 should not flag a longer-enough response
        long_enough = _valid_record(
            response="ஆம், இது ஒரு போதுமான நீளமான சோதனை பதில் ஆகும்."
        )
        issues_default = check_language_quality(long_enough)  # no config
        assert not any(
            i.check_name == "language.too_short_response" for i in issues_default
        )


# ─────────────────────────────────────────────────────────────────────────────
# Feature 1 cont. — Backward compatibility
# ─────────────────────────────────────────────────────────────────────────────

class TestBackwardCompatibility:
    """Existing call sites (no config arg) must be unaffected."""

    def test_backward_compatibility_no_config(self):
        """check_language_quality(record) with NO config must work as before."""
        record = _english_heavy_record()
        issues = check_language_quality(record)  # no config arg
        excessive = [
            i for i in issues if i.check_name == "language.excessive_english"
        ]
        assert len(excessive) >= 1
        assert excessive[0].severity == Severity.WARNING

    def test_backward_compatibility_no_config_sft_validator(self):
        """SFTValidator() with no args must work and produce same results."""
        record = _valid_record()
        v = SFTValidator()
        results = v.validate([record])
        assert len(results) == 1
        assert results[0].is_valid is True

    def test_backward_compatibility_run_all_checks_no_config(self):
        """run_all_checks() with no config arg must work like before P3."""
        record = _valid_record()
        dd = DuplicateDetector()
        dd.register(record["id"], record["prompt"], "prompt")
        dd.register(record["id"], record["response"], "response")
        result = run_all_checks(record, dd)  # No config arg — legacy call
        assert result.is_valid is True
        error_issues = [i for i in result.issues if i.severity == Severity.ERROR]
        assert len(error_issues) == 0

    def test_backward_compatibility_no_config_english_heavy_record(self):
        """An English-heavy record without config arg must produce WARNING
        (not ERROR) for language.excessive_english — unchanged behavior."""
        record = _english_heavy_record()
        dd = DuplicateDetector()
        dd.register(record["id"], record["prompt"], "prompt")
        dd.register(record["id"], record["response"], "response")
        result = run_all_checks(record, dd)  # No config

        excessive_english = [
            i for i in result.issues
            if i.check_name == "language.excessive_english"
        ]
        if excessive_english:
            assert excessive_english[0].severity == Severity.WARNING, (
                "BACKWARD COMPAT FAILURE: excessive_english changed from "
                "WARNING to ERROR without strict mode"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Feature 2 — Strict mode
# ─────────────────────────────────────────────────────────────────────────────

class TestStrictMode:
    """Strict mode escalates configured WARNINGs to ERRORs."""

    def _make_english_heavy_result(self, config=None):
        record = _english_heavy_record()
        dd = DuplicateDetector()
        dd.register(record["id"], record["prompt"], "prompt")
        dd.register(record["id"], record["response"], "response")
        return run_all_checks(record, dd, config=config)

    def test_strict_mode_off_by_default(self):
        """Without strict mode, excessive_english stays as WARNING."""
        result = self._make_english_heavy_result(config=None)
        for issue in result.issues:
            if issue.check_name == "language.excessive_english":
                assert issue.severity == Severity.WARNING

    def test_strict_mode_escalates_configured_checks(self):
        """With strict_mode=True and excessive_english in strict_checks,
        the issue must become ERROR and is_valid must be False."""
        config = ValidatorConfig(
            strict_mode=True,
            strict_checks=["language.excessive_english"],
        )
        result = self._make_english_heavy_result(config=config)

        excessive = [
            i for i in result.issues
            if i.check_name == "language.excessive_english"
        ]
        assert excessive, "Expected language.excessive_english to fire"
        assert excessive[0].severity == Severity.ERROR
        assert result.is_valid is False
        assert "[STRICT]" in excessive[0].message

    def test_strict_mode_only_escalates_configured_checks(self):
        """Only checks listed in strict_checks get escalated."""
        config = ValidatorConfig(
            strict_mode=True,
            strict_checks=["language.excessive_english"],
        )
        # Build a record that is English-heavy AND has excessive punctuation
        # (a warning NOT in strict_checks).
        record = _english_heavy_record()
        record["response"] = (
            "This is almost all English text with lots of Latin characters "
            "and almost no Tamil at all!!! What do you think???"
        )
        dd = DuplicateDetector()
        dd.register(record["id"], record["prompt"], "prompt")
        dd.register(record["id"], record["response"], "response")
        result = run_all_checks(record, dd, config=config)

        for issue in result.issues:
            if issue.check_name == "language.excessive_english":
                assert issue.severity == Severity.ERROR
                assert "[STRICT]" in issue.message
            elif issue.check_name == "naturalness.excessive_punctuation":
                assert issue.severity == Severity.WARNING
                assert "[STRICT]" not in (issue.message or "")

    def test_strict_mode_does_not_escalate_existing_errors(self):
        """Issues already at ERROR severity must not be double-escalated."""
        config = ValidatorConfig(
            strict_mode=True,
            strict_checks=["schema.missing_field"],
        )
        record = {
            "id": "missing_fields",
            "prompt": "வணக்கம்",
        }
        dd = DuplicateDetector()
        result = run_all_checks(record, dd, config=config)

        for issue in result.issues:
            if issue.check_name == "schema.missing_field":
                assert "[STRICT][STRICT]" not in (issue.message or "")

    def test_strict_mode_false_with_config_no_escalation(self):
        """Config with strict_mode=False must behave identically to no config."""
        config_off = ValidatorConfig(strict_mode=False)
        result_no_config = self._make_english_heavy_result(config=None)
        result_config_off = self._make_english_heavy_result(config=config_off)

        checks_no_config = {i.check_name for i in result_no_config.issues}
        checks_config_off = {i.check_name for i in result_config_off.issues}
        assert checks_no_config == checks_config_off
        assert result_no_config.is_valid == result_config_off.is_valid

    def test_strict_mode_via_sft_validator(self):
        """SFTValidator with strict config must produce more or equal invalids."""
        records = [_english_heavy_record(f"rec_{i:03d}") for i in range(5)]

        v_normal = SFTValidator(config=ValidatorConfig(strict_mode=False))
        v_normal.validate(records)
        report_normal = v_normal.build_report()

        v_strict = SFTValidator(config=ValidatorConfig(
            strict_mode=True,
            strict_checks=["language.excessive_english"],
        ))
        v_strict.validate(records)
        report_strict = v_strict.build_report()

        assert report_strict.invalid_records >= report_normal.invalid_records

    def test_strict_mode_empty_strict_checks_no_escalation(self):
        """strict_mode=True with empty strict_checks must not change severity."""
        config = ValidatorConfig(strict_mode=True, strict_checks=[])
        result_no_config = self._make_english_heavy_result(config=None)
        result_empty_strict = self._make_english_heavy_result(config=config)

        for i_ref, i_test in zip(
            sorted(result_no_config.issues, key=lambda x: x.check_name),
            sorted(result_empty_strict.issues, key=lambda x: x.check_name),
            strict=True,
        ):
            assert i_ref.severity == i_test.severity


# ─────────────────────────────────────────────────────────────────────────────
# Feature 3 — CI summary
# ─────────────────────────────────────────────────────────────────────────────

class TestCISummary:
    """--ci-summary must emit a parseable CI_SUMMARY line after normal output."""

    def _write_fixture(self, tmp_path: Path, records: list[dict]) -> Path:
        p = tmp_path / "input.jsonl"
        p.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in records),
            encoding="utf-8",
        )
        return p

    def test_ci_summary_line_format(self, tmp_path):
        """CI_SUMMARY line must exist and contain all required fields."""
        records = [_valid_record(f"rec_{i:03d}") for i in range(3)]
        input_file = self._write_fixture(tmp_path, records)
        clean_file = tmp_path / "clean.jsonl"
        report_file = tmp_path / "report.json"

        result = _run_validate_sft([
            "--input", str(input_file),
            "--clean", str(clean_file),
            "--report", str(report_file),
            "--ci-summary",
        ])

        assert result.returncode == 0
        stdout = result.stdout

        ci_lines = [line for line in stdout.splitlines() if line.startswith("CI_SUMMARY")]
        assert len(ci_lines) == 1, (
            f"Expected exactly 1 CI_SUMMARY line, got {len(ci_lines)}.\n"
            f"stdout:\n{stdout}"
        )

        line = ci_lines[0]
        parts = line.split()
        assert parts[0] == "CI_SUMMARY"
        kv = {}
        for part in parts[1:]:
            k, _, v = part.partition("=")
            kv[k] = v

        required_keys = {"total", "valid", "invalid", "errors", "warnings", "quality"}
        assert required_keys.issubset(kv.keys())
        assert kv["total"] == "3"
        assert kv["valid"] == "3"
        assert kv["invalid"] == "0"

    def test_ci_summary_values_are_accurate(self, tmp_path):
        """CI_SUMMARY values must match the report written to disk."""
        records = [_valid_record(f"r{i}") for i in range(5)]
        input_file = self._write_fixture(tmp_path, records)
        clean_file = tmp_path / "clean.jsonl"
        report_file = tmp_path / "report.json"

        result = _run_validate_sft([
            "--input", str(input_file),
            "--clean", str(clean_file),
            "--report", str(report_file),
            "--ci-summary",
        ])
        assert result.returncode == 0

        report_data = json.loads(report_file.read_text(encoding="utf-8"))
        summary = report_data["summary"]

        ci_line = next(
            line for line in result.stdout.splitlines()
            if line.startswith("CI_SUMMARY")
        )
        kv = dict(p.split("=", 1) for p in ci_line.split()[1:])

        assert int(kv["total"]) == summary["total_records"]
        assert int(kv["valid"]) == summary["valid_records"]
        assert int(kv["invalid"]) == summary["invalid_records"]
        assert int(kv["errors"]) == summary["errors"]
        assert int(kv["warnings"]) == summary["warnings"]
        assert float(kv["quality"]) == summary["aggregate_quality_score"]

    def test_ci_summary_not_printed_without_flag(self, tmp_path):
        """Without --ci-summary, no CI_SUMMARY line must appear in stdout."""
        records = [_valid_record()]
        input_file = self._write_fixture(tmp_path, records)
        clean_file = tmp_path / "clean.jsonl"
        report_file = tmp_path / "report.json"

        result = _run_validate_sft([
            "--input", str(input_file),
            "--clean", str(clean_file),
            "--report", str(report_file),
        ])
        assert result.returncode == 0
        ci_lines = [line for line in result.stdout.splitlines() if line.startswith("CI_SUMMARY")]
        assert len(ci_lines) == 0

    def test_ci_summary_combined_with_strict(self, tmp_path):
        """--ci-summary and --strict can be used together without crashing."""
        records = [_valid_record(f"r{i}") for i in range(2)]
        input_file = self._write_fixture(tmp_path, records)
        clean_file = tmp_path / "clean.jsonl"
        report_file = tmp_path / "report.json"

        result = _run_validate_sft([
            "--input", str(input_file),
            "--clean", str(clean_file),
            "--report", str(report_file),
            "--ci-summary",
            "--strict",
        ])
        assert result.returncode == 0
        ci_lines = [line for line in result.stdout.splitlines() if line.startswith("CI_SUMMARY")]
        assert len(ci_lines) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Feature 4 — Windows stdout hardening
# ─────────────────────────────────────────────────────────────────────────────

class TestWindowsHardening:
    """UTF-8 stdout wrapper must be present in both CLI entry points.

    We read the *source files as text* rather than importing the modules,
    because importing validate_sft.py at module level executes the
    ``sys.stdout = io.TextIOWrapper(...)`` replacement which closes
    pytest's capture buffer and breaks all subsequent tests.
    """

    def _read_source(self, filename: str) -> str:
        return (
            Path(__file__).parent.parent / filename
        ).read_text(encoding="utf-8")

    def test_validate_sft_has_utf8_wrapper(self):
        src = self._read_source("validate_sft.py")
        assert "TextIOWrapper" in src
        assert "utf-8" in src

    def test_main_py_has_utf8_wrapper(self):
        src = self._read_source("main.py")
        assert "TextIOWrapper" in src
        assert "utf-8" in src


# ─────────────────────────────────────────────────────────────────────────────
# CLI Integration — default behavior unchanged
# ─────────────────────────────────────────────────────────────────────────────

class TestCLIDefaultBehavior:
    """Running without new flags must produce exactly the same results."""

    def _bad_examples_path(self) -> Path:
        return Path(__file__).parent.parent / "fixtures" / "bad_examples.jsonl"

    def test_default_cli_exit_code_zero(self, tmp_path):
        """validate_sft.py must exit 0 even with invalid records."""
        result = _run_validate_sft([
            "--input", str(self._bad_examples_path()),
            "--clean", str(tmp_path / "clean.jsonl"),
            "--report", str(tmp_path / "report.json"),
        ])
        assert result.returncode == 0, (
            f"Expected exit 0, got {result.returncode}.\n"
            f"stderr: {result.stderr}"
        )

    def test_default_cli_unchanged(self, tmp_path):
        """Without --strict, bad_examples.jsonl baseline must hold.

        All 16 records use register values / defects that make them invalid
        under the current taxonomy (e.g. unknown register). Pre-P3 baseline:
        0 valid, 16 invalid, exit code 0.
        """
        result = _run_validate_sft([
            "--input", str(self._bad_examples_path()),
            "--clean", str(tmp_path / "clean.jsonl"),
            "--report", str(tmp_path / "report.json"),
        ])
        assert result.returncode == 0
        report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
        summary = report["summary"]
        assert summary["total_records"] == 16
        assert summary["valid_records"] == 0
        assert summary["invalid_records"] == 16

    def test_strict_cli_produces_more_or_equal_invalids(self, tmp_path):
        """--strict must never reduce the invalid count vs non-strict."""
        bad_path = self._bad_examples_path()

        result_normal = _run_validate_sft([
            "--input", str(bad_path),
            "--clean", str(tmp_path / "clean_normal.jsonl"),
            "--report", str(tmp_path / "report_normal.json"),
        ])
        result_strict = _run_validate_sft([
            "--input", str(bad_path),
            "--clean", str(tmp_path / "clean_strict.jsonl"),
            "--report", str(tmp_path / "report_strict.json"),
            "--strict",
        ])

        assert result_normal.returncode == 0
        assert result_strict.returncode == 0

        normal_report = json.loads(
            (tmp_path / "report_normal.json").read_text(encoding="utf-8")
        )
        strict_report = json.loads(
            (tmp_path / "report_strict.json").read_text(encoding="utf-8")
        )

        normal_invalid = normal_report["summary"]["invalid_records"]
        strict_invalid = strict_report["summary"]["invalid_records"]

        assert strict_invalid >= normal_invalid

    def test_strict_cli_with_config_flag(self, tmp_path):
        """--config flag must load custom thresholds without crashing."""
        config_data = {
            "min_response_length": 5,
            "max_english_ratio": 0.9,
        }
        config_file = tmp_path / "my_config.json"
        config_file.write_text(json.dumps(config_data), encoding="utf-8")

        result = _run_validate_sft([
            "--input", str(self._bad_examples_path()),
            "--clean", str(tmp_path / "clean.jsonl"),
            "--report", str(tmp_path / "report.json"),
            "--config", str(config_file),
        ])
        assert result.returncode == 0

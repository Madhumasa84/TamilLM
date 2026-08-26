"""Regression tests for packaging, configuration and reusable runs."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.split_dataset import split_records
from validator.config import ValidatorConfig
from validator.validator import SFTValidator


def _record(record_id: str, *, prompt: str = "தமிழ் கேள்வி") -> dict[str, str]:
    return {
        "id": record_id,
        "prompt": prompt,
        "response": "இது போதுமான நீளமுள்ள தமிழ் பதில் ஆகும்.",
        "register": "spoken_colloquial",
        "region": "Generic Tamil Nadu",
        "domain": "everyday",
        "task_type": "qa",
        "notes": "regression test",
    }


def test_validator_config_rejects_invalid_ranges():
    with pytest.raises(ValueError, match="between 0 and 1"):
        ValidatorConfig(min_tamil_ratio=1.1)
    with pytest.raises(ValueError, match="max_response_length"):
        ValidatorConfig(min_response_length=20, max_response_length=10)


def test_validator_config_rejects_non_positive_min_response_length():
    with pytest.raises(ValueError, match="min_response_length must be positive"):
        ValidatorConfig(min_response_length=0)


def test_validator_config_rejects_non_positive_repetition_threshold():
    with pytest.raises(ValueError, match="repetition_threshold must be positive"):
        ValidatorConfig(repetition_threshold=0)


def test_validator_config_rejects_negative_low_coverage_threshold():
    with pytest.raises(ValueError, match="low_coverage_threshold cannot be negative"):
        ValidatorConfig(low_coverage_threshold=-1)


def test_validator_config_rejects_malformed_strict_checks():
    with pytest.raises(ValueError, match="strict_checks must be a list"):
        ValidatorConfig(strict_checks=["", "language.excessive_english"])
    with pytest.raises(ValueError, match="strict_checks must be a list"):
        ValidatorConfig(strict_checks="not-a-list")  # type: ignore[arg-type]


def test_validator_config_from_json_rejects_non_object(tmp_path: Path):
    path = tmp_path / "config.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a JSON object"):
        ValidatorConfig.from_json(path)


def test_validator_config_round_trips_to_json(tmp_path: Path):
    original = ValidatorConfig(strict_mode=True, min_response_length=25)
    path = tmp_path / "config.json"
    original.write_json(path)
    loaded = ValidatorConfig.from_json(path)
    assert loaded.to_dict() == original.to_dict()


def test_reference_config_has_no_drift():
    reference = json.loads(
        (Path("validator") / "config.default.json").read_text(encoding="utf-8")
    )
    assert reference == ValidatorConfig.default().to_dict()


def test_validation_run_is_reusable_without_stale_duplicate_state():
    validator = SFTValidator()
    first = validator.validate([_record("first")])[0]
    second = validator.validate([_record("second")])[0]
    assert not any(issue.check_name.startswith("duplicate.") for issue in first.issues)
    assert not any(issue.check_name.startswith("duplicate.") for issue in second.issues)


def test_duplicate_detection_does_not_mutate_duplicate_id_input():
    records = [_record("same"), _record("same")]
    original = [json.loads(json.dumps(record)) for record in records]
    results = SFTValidator().validate(records)
    assert records == original
    assert results[1].is_valid is False


def test_python_module_entrypoint_runs(tmp_path: Path):
    clean = tmp_path / "clean.jsonl"
    report = tmp_path / "report.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "validator",
            "--input",
            "data/tamil_sft_seed.jsonl",
            "--clean",
            str(clean),
            "--report",
            str(report),
            "--ci-summary",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "CI_SUMMARY total=200" in result.stdout
    assert json.loads(report.read_text(encoding="utf-8"))["summary"]["total_records"] == 200


def test_dataset_split_is_deterministic_and_keeps_exact_duplicates_together():
    records = [
        _record("a", prompt="same prompt"),
        _record("b", prompt="same prompt"),
        _record("c", prompt="different prompt"),
    ]
    first = split_records(records, validation_ratio=0.2, test_ratio=0.2)
    second = split_records(records, validation_ratio=0.2, test_ratio=0.2)
    assert first == second
    locations = {
        record["id"]: partition
        for partition, partition_records in first.items()
        for record in partition_records
    }
    assert locations["a"] == locations["b"]

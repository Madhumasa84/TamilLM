"""Direct (in-process) tests for validator.cli, covering paths that the
subprocess-based CLI tests in test_p3_hardening.py don't reach."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from validator.cli import configure_stdout, main


def _valid_record(record_id: str) -> dict[str, str]:
    return {
        "id": record_id,
        "prompt": "தமிழ் கேள்வி",
        "response": "இது போதுமான நீளமுள்ள தமிழ் பதில் ஆகும்.",
        "register": "spoken_colloquial",
        "region": "Generic Tamil Nadu",
        "domain": "everyday",
        "task_type": "qa",
    }


class _FakeBufferedStdout:
    """Minimal stand-in for a non-UTF-8 console stdout stream."""

    def __init__(self) -> None:
        self.buffer = io.BytesIO()
        self.encoding = "cp1252"


def test_configure_stdout_wraps_non_utf8_console(monkeypatch: pytest.MonkeyPatch):
    fake_stdout = _FakeBufferedStdout()
    monkeypatch.setattr(sys, "stdout", fake_stdout)

    configure_stdout()

    assert isinstance(sys.stdout, io.TextIOWrapper)
    assert sys.stdout.encoding == "utf-8"


def test_main_reraises_infrastructure_system_exit(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    clean = tmp_path / "clean.jsonl"
    report = tmp_path / "report.json"

    with pytest.raises(SystemExit) as exc_info:
        main([
            "--input", str(tmp_path / "missing.jsonl"),
            "--clean", str(clean),
            "--report", str(report),
        ])

    assert exc_info.value.code == 1
    assert "Input file not found" in capsys.readouterr().err


def test_main_returns_1_and_prints_pipeline_failed_on_bad_config(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    input_file = tmp_path / "input.jsonl"
    input_file.write_text("", encoding="utf-8")
    bad_config = tmp_path / "config.json"
    bad_config.write_text("not valid json{", encoding="utf-8")

    exit_code = main([
        "--input", str(input_file),
        "--clean", str(tmp_path / "clean.jsonl"),
        "--report", str(tmp_path / "report.json"),
        "--config", str(bad_config),
    ])

    assert exit_code == 1
    assert "Pipeline failed:" in capsys.readouterr().err


def test_main_returns_0_on_success(tmp_path: Path):
    input_file = tmp_path / "input.jsonl"
    input_file.write_text(json.dumps(_valid_record("only")) + "\n", encoding="utf-8")

    exit_code = main([
        "--input", str(input_file),
        "--clean", str(tmp_path / "clean.jsonl"),
        "--report", str(tmp_path / "report.json"),
    ])

    assert exit_code == 0

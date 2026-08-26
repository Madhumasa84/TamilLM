"""Validated configuration for the Tamil SFT validator.

This module is the single source of truth for configurable thresholds.  The
legacy constants in :mod:`validator.utils` are compatibility aliases so
existing callers continue to work without maintaining a second set of values.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_MIN_RESPONSE_LENGTH = 20
DEFAULT_MAX_RESPONSE_LENGTH = 5000
DEFAULT_MIN_TAMIL_RATIO = 0.3
DEFAULT_MAX_ENGLISH_RATIO = 0.5
DEFAULT_NEAR_DUPLICATE_THRESHOLD = 0.7
DEFAULT_REPETITION_THRESHOLD = 3
DEFAULT_LOW_COVERAGE_THRESHOLD = 2
DEFAULT_STRICT_CHECKS = (
    "language.excessive_english",
    "naturalness.unnatural_formatting",
    "consistency.register_mismatch",
)


@dataclass
class ValidatorConfig:
    """Thresholds and mode flags used by the validation pipeline."""

    min_response_length: int = DEFAULT_MIN_RESPONSE_LENGTH
    max_response_length: int = DEFAULT_MAX_RESPONSE_LENGTH
    min_tamil_ratio: float = DEFAULT_MIN_TAMIL_RATIO
    max_english_ratio: float = DEFAULT_MAX_ENGLISH_RATIO
    near_duplicate_threshold: float = DEFAULT_NEAR_DUPLICATE_THRESHOLD
    repetition_threshold: int = DEFAULT_REPETITION_THRESHOLD
    low_coverage_threshold: int = DEFAULT_LOW_COVERAGE_THRESHOLD
    strict_mode: bool = False
    strict_checks: list[str] = field(
        default_factory=lambda: list(DEFAULT_STRICT_CHECKS)
    )

    def __post_init__(self) -> None:
        """Reject configurations that cannot produce meaningful results."""
        if self.min_response_length < 1:
            raise ValueError("min_response_length must be positive")
        if self.max_response_length < self.min_response_length:
            raise ValueError(
                "max_response_length must be >= min_response_length"
            )
        for name, value in (
            ("min_tamil_ratio", self.min_tamil_ratio),
            ("max_english_ratio", self.max_english_ratio),
            ("near_duplicate_threshold", self.near_duplicate_threshold),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.repetition_threshold < 1:
            raise ValueError("repetition_threshold must be positive")
        if self.low_coverage_threshold < 0:
            raise ValueError("low_coverage_threshold cannot be negative")
        if not isinstance(self.strict_checks, list) or not all(
            isinstance(check, str) and check for check in self.strict_checks
        ):
            raise ValueError("strict_checks must be a list of non-empty strings")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable copy of this configuration."""
        return asdict(self)

    def write_json(self, path: str | Path) -> None:
        """Write this configuration as a stable, human-readable JSON file."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def from_json(cls, path: str | Path) -> ValidatorConfig:
        """Load known settings from a JSON object and validate them."""
        with Path(path).open(encoding="utf-8") as config_file:
            data = json.load(config_file)
        if not isinstance(data, dict):
            raise ValueError("validator config must be a JSON object")

        known_fields = set(cls.__dataclass_fields__)
        filtered = {key: value for key, value in data.items() if key in known_fields}
        return cls(**filtered)

    @classmethod
    def default(cls) -> ValidatorConfig:
        """Return a fresh configuration with project defaults."""
        return cls()

"""
Tamil SFT Dataset Validation — Validator Configuration.

Provides the ``ValidatorConfig`` dataclass that holds all configurable
thresholds and mode flags for the validation pipeline.

* Default values match the legacy module-level constants in ``utils.py``
  so that ``ValidatorConfig.default()`` produces identical behavior to
  the original hard-coded thresholds.
* Users can override any field via a JSON config file (``--config`` CLI
  flag) without touching source code.
* Strict mode (``--strict`` CLI flag) escalates selected warning checks
  to errors at runtime without altering the default validation behavior.

Design principle: importing this module has **no side-effects**.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ValidatorConfig:
    """All configurable thresholds and mode flags for the validator.

    Attributes:
        min_response_length:      Minimum response length in characters.
        max_response_length:      Maximum response length in characters.
        min_tamil_ratio:          Minimum fraction of Tamil script chars.
        max_english_ratio:        Maximum fraction of Latin script chars.
        near_duplicate_threshold: Jaccard similarity threshold for near-dupes.
        repetition_threshold:     Phrase-repeat count that triggers a warning.
        low_coverage_threshold:   Category count below which a warning fires.
        strict_mode:              If True, escalate configured checks to ERROR.
        strict_checks:            Check names upgraded WARNING→ERROR in strict
                                  mode.  Default: three common quality checks.
    """

    min_response_length: int = 20
    max_response_length: int = 5000
    min_tamil_ratio: float = 0.3
    max_english_ratio: float = 0.5
    near_duplicate_threshold: float = 0.7
    repetition_threshold: int = 3
    low_coverage_threshold: int = 2
    strict_mode: bool = False
    strict_checks: list[str] = field(default_factory=lambda: [
        "language.excessive_english",
        "naturalness.unnatural_formatting",
        "consistency.register_mismatch",
    ])

    # ── JSON loading ──────────────────────────────────────────────────

    @classmethod
    def from_json(cls, path: str) -> "ValidatorConfig":
        """Load a ``ValidatorConfig`` from a JSON file.

        The JSON file should be a flat object whose keys match the
        dataclass field names.  Unknown keys are ignored so that config
        files written for older validator versions remain compatible.
        Missing keys fall back to dataclass defaults.

        Args:
            path: Filesystem path to the JSON config file.

        Returns:
            A :class:`ValidatorConfig` instance populated from the file.

        Raises:
            FileNotFoundError: If *path* does not exist.
            json.JSONDecodeError: If the file is not valid JSON.
        """
        import json

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        # Filter to only known fields to avoid TypeError on unexpected keys.
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)

    @classmethod
    def default(cls) -> "ValidatorConfig":
        """Return a ``ValidatorConfig`` with all default values.

        Equivalent to ``ValidatorConfig()`` but more explicit at call
        sites, and easier to discover via ``help()`` or IDE completion.
        """
        return cls()

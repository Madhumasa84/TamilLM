"""Typed report models for validation results.

Keeping report data structures separate from file I/O makes them reusable by
the CLI, library callers and future dashboards.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CoverageAnalysis:
    """Missing categories and register/task-type cross coverage."""

    missing_registers: list[str]
    missing_task_types: list[str]
    missing_domains: list[str]
    coverage_warnings: list[str]
    cross_coverage: dict[str, dict[str, int]]


@dataclass
class ValidationReport:
    """Complete validation report for a dataset run."""

    total_records: int
    valid_records: int
    invalid_records: int
    aggregate_quality_score: float
    quality_score_distribution: dict[str, int]
    register_distribution: dict[str, int]
    domain_distribution: dict[str, int]
    region_distribution: dict[str, int]
    task_type_distribution: dict[str, int]
    duplicate_count: int
    coverage: CoverageAnalysis
    error_count: int
    warning_count: int
    info_count: int
    safety_warnings: list[dict[str, Any]]
    issues_by_check: dict[str, int]
    record_details: list[dict[str, Any]]

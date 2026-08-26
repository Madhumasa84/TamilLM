"""
Tamil SFT Dataset Validation — Pipeline Orchestrator.

This module wires the check library to real I/O: loading JSONL files,
running every record through the check suite, partitioning records into
clean vs. flagged, computing coverage analysis, and writing structured
output files.

Usage (programmatic)::

    from pathlib import Path
    from validator.validator import SFTValidator

    validator = SFTValidator()
    records  = validator.load_records(Path("data/tamil_sft_seed.jsonl"))
    results  = validator.validate(records)
    report   = validator.write_outputs(
        clean_path  = Path("outputs/clean.jsonl"),
        report_path = Path("outputs/validation_report.json"),
    )
    print(f"Quality: {report.aggregate_quality_score}/100")

The CLI entrypoint (``validate_sft.py``) calls these methods and handles
argument parsing and exit codes.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from validator.checks import DuplicateDetector, run_all_checks
from validator.config import ValidatorConfig
from validator.reporting import CoverageAnalysis, ValidationReport
from validator.utils import (
    ALLOWED_REGISTERS,
    CANONICAL_TASK_TYPES,
    KNOWN_DOMAINS,
    TASK_TYPE_ALIASES,
    RecordResult,
    Severity,
    ValidationIssue,
)

# ───────────────────────────────────────────────────────────────────────────
# Pipeline Orchestrator
# ───────────────────────────────────────────────────────────────────────────

class SFTValidator:
    """Orchestrates the full validation pipeline for a Tamil SFT dataset.

    Lifecycle::

        validator = SFTValidator()
        records  = validator.load_records(input_path)
        results  = validator.validate(records)
        report   = validator.write_outputs(clean_path, report_path)

    The validator exits nonzero **only** for infrastructure failures
    (file not found, empty file, I/O errors).  Bad records are captured
    in the report — they never crash the run.
    """

    def __init__(self, config: ValidatorConfig | None = None) -> None:
        self._config = config or ValidatorConfig.default()
        self._duplicate_detector = self._new_duplicate_detector()
        self._results: list[RecordResult] = []

    def _new_duplicate_detector(self) -> DuplicateDetector:
        """Create an isolated deduplication state for one validation run."""
        return DuplicateDetector(
            near_duplicate_threshold=self._config.near_duplicate_threshold
        )

    # ── Loading ──────────────────────────────────────────────────────

    def load_records(self, input_path: Path) -> list[dict[str, Any]]:
        """Load records from a JSONL file.

        * File-level errors (not found, permission denied) cause
          ``sys.exit(1)`` — these are infrastructure failures.
        * Individual malformed JSON lines are captured as synthetic
          records with a ``_parse_error`` key so they flow through
          the check pipeline and appear in the report.

        Returns:
            A list of record dicts ready for validation.
        """
        if not input_path.exists():
            print(
                f"Error: Input file not found: {input_path}",
                file=sys.stderr,
            )
            sys.exit(1)

        records: list[dict[str, Any]] = []

        try:
            with open(input_path, encoding="utf-8") as fh:
                for line_num, raw_line in enumerate(fh, start=1):
                    stripped = raw_line.strip()
                    if not stripped:
                        continue
                    try:
                        parsed = json.loads(stripped)
                        if not isinstance(parsed, dict):
                            parsed = {
                                "id": f"<line_{line_num}>",
                                "_parse_error": (
                                    f"Line {line_num}: Expected JSON object, "
                                    f"got {type(parsed).__name__}"
                                ),
                            }
                        records.append(parsed)
                    except json.JSONDecodeError as exc:
                        records.append({
                            "id": f"<line_{line_num}>",
                            "_parse_error": (
                                f"Line {line_num}: JSON parse error — {exc}"
                            ),
                        })
        except OSError as exc:
            print(
                f"Error: Cannot read {input_path}: {exc}",
                file=sys.stderr,
            )
            sys.exit(1)

        if not records:
            print(
                f"Error: No records found in {input_path}",
                file=sys.stderr,
            )
            sys.exit(1)

        return records

    # ── Validation ───────────────────────────────────────────────────

    def validate(
        self,
        records: list[dict[str, Any]],
    ) -> list[RecordResult]:
        """Run all validation checks on every record.

        Records with ``_parse_error`` are short-circuited to a zero-score
        ERROR result.  All other records flow through the full check suite.

        Returns:
            Ordered list of :class:`RecordResult` (same order as input).
        """
        self._results = []
        # A validator instance can be reused safely.  Dedup state and its
        # counters belong to one dataset run, never to the object lifetime.
        self._duplicate_detector = self._new_duplicate_detector()

        # Pass 1: Register all prompts/responses for dedup
        # regardless of schema validity.
        # IMPORTANT: We must NOT mutate record["id"] here — the original
        # record dict must reach check_schema() unchanged so that empty/
        # missing id fields still produce schema errors.
        for i, record in enumerate(records):
            raw_id = record.get("id")
            if not raw_id or not str(raw_id).strip():
                record_id_for_reporting = f"<line_{i+1}>"
            else:
                record_id_for_reporting = raw_id

            prompt = record.get("prompt")
            response = record.get("response")

            # Only register if field exists, is string, non-empty
            if isinstance(prompt, str) and prompt.strip():
                self._duplicate_detector.register(
                    record_id_for_reporting, prompt, "prompt"
                )
            if isinstance(response, str) and response.strip():
                self._duplicate_detector.register(
                    record_id_for_reporting, response, "response"
                )

        # Check for duplicate IDs first.
        # Use the same reporting-id logic (never mutate the record).
        seen_ids: dict[str, int] = {}
        duplicate_id_errors: dict[int, str] = {}
        for i, record in enumerate(records):
            raw_id = record.get("id")
            record_id_for_reporting = (
                raw_id if raw_id and str(raw_id).strip()
                else f"<line_{i+1}>"
            )
            if record_id_for_reporting in seen_ids:
                duplicate_id_errors[i] = (
                    f"ID '{record_id_for_reporting}' already seen at "
                    f"record {seen_ids[record_id_for_reporting] + 1}"
                )
            else:
                seen_ids[record_id_for_reporting] = i

        for i, record in enumerate(records):
            if "_parse_error" in record:
                result = RecordResult(
                    record_id=record.get("id", "<unknown>"),
                    is_valid=False,
                    issues=[
                        ValidationIssue(
                            record_id=record.get("id", "<unknown>"),
                            check_name="schema.parse_error",
                            severity=Severity.ERROR,
                            message=record["_parse_error"],
                        )
                    ],
                    quality_score=0,
                    record=record,
                )
            elif i in duplicate_id_errors:
                result = RecordResult(
                    record_id=record.get("id", "<unknown>"),
                    is_valid=False,
                    issues=[
                        ValidationIssue(
                            record_id=record.get("id", "<unknown>"),
                            check_name="schema.duplicate_id",
                            severity=Severity.ERROR,
                            message=duplicate_id_errors[i],
                            field="id",
                            suggestion="Each record must have a unique ID",
                        )
                    ],
                    quality_score=0,
                    record=record,
                )
            else:
                raw_id = record.get("id")
                record_id_for_reporting = (
                    raw_id if raw_id and str(raw_id).strip()
                    else f"<line_{i+1}>"
                )
                result = run_all_checks(
                    record,
                    self._duplicate_detector,
                    locator=record_id_for_reporting,
                    config=self._config,
                )
            self._results.append(result)

        return self._results

    # ── Coverage Analysis ────────────────────────────────────────────

    def _analyze_coverage(self) -> CoverageAnalysis:
        """Analyze dataset coverage: missing categories and thin spots.

        Produces three kinds of output:

        1. **Missing values** — registers, task types, or domains that
           have zero representation in the dataset.
        2. **Cross-coverage matrix** — register × task_type counts, so
           curators can see which combinations are under-represented.
        3. **Coverage warnings** — human-readable strings like
           ``"Only 1 example for register='literary' × task_type='qa'"``
        """
        registers: Counter[str] = Counter()
        task_types: Counter[str] = Counter()
        domains: Counter[str] = Counter()
        cross_reg_tt: dict[str, Counter[str]] = defaultdict(Counter)

        for result in self._results:
            rec = result.record
            reg = rec.get("register", "")
            raw_tt = rec.get("task_type", "")
            dom = rec.get("domain", "")

            # Normalize task_type for coverage counting.
            tt = TASK_TYPE_ALIASES.get(raw_tt.lower(), raw_tt) if raw_tt else ""

            if reg:
                registers[reg] += 1
            if tt:
                task_types[tt] += 1
            if dom:
                domains[dom] += 1
            if reg and tt:
                cross_reg_tt[reg][tt] += 1

        # ── Missing values ───────────────────────────────────────────
        missing_registers = sorted(
            r for r in ALLOWED_REGISTERS if registers[r] == 0
        )
        missing_task_types = sorted(
            t for t in CANONICAL_TASK_TYPES if task_types[t] == 0
        )
        missing_domains = sorted(
            d for d in KNOWN_DOMAINS if domains[d] == 0
        )

        # ── Coverage warnings ────────────────────────────────────────
        warnings: list[str] = []

        low_thresh = self._config.low_coverage_threshold

        # Low-count task types
        for tt in sorted(CANONICAL_TASK_TYPES):
            count = task_types[tt]
            if 0 < count <= low_thresh:
                warnings.append(
                    f"Only {count} example(s) for task_type='{tt}'"
                )

        # Low-count registers
        for reg in sorted(ALLOWED_REGISTERS):
            count = registers[reg]
            if 0 < count <= low_thresh:
                warnings.append(
                    f"Only {count} example(s) for register='{reg}'"
                )

        # Cross-coverage: register × task_type
        for reg in sorted(ALLOWED_REGISTERS):
            if registers[reg] == 0:
                continue  # Already flagged as missing register
            for tt in sorted(CANONICAL_TASK_TYPES):
                if task_types[tt] == 0:
                    continue  # Already flagged as missing task_type
                count = cross_reg_tt.get(reg, Counter()).get(tt, 0)
                if count == 0:
                    warnings.append(
                        f"No examples for register='{reg}' × "
                        f"task_type='{tt}'"
                    )
                elif count <= 1:
                    warnings.append(
                        f"Only {count} example for register='{reg}' × "
                        f"task_type='{tt}'"
                    )

        # ── Serialize cross-coverage ─────────────────────────────────
        cross_serialized: dict[str, dict[str, int]] = {}
        for reg in sorted(ALLOWED_REGISTERS):
            reg_counts: dict[str, int] = {}
            for tt in sorted(CANONICAL_TASK_TYPES):
                count = cross_reg_tt.get(reg, Counter()).get(tt, 0)
                reg_counts[tt] = count
            cross_serialized[reg] = reg_counts

        return CoverageAnalysis(
            missing_registers=missing_registers,
            missing_task_types=missing_task_types,
            missing_domains=missing_domains,
            coverage_warnings=warnings,
            cross_coverage=cross_serialized,
        )

    # ── Report Building ──────────────────────────────────────────────

    def build_report(self) -> ValidationReport:
        """Build the complete validation report from accumulated results.

        Call this after :meth:`validate` to generate the report.
        """
        valid = [r for r in self._results if r.is_valid]
        invalid = [r for r in self._results if not r.is_valid]

        # ── Quality score statistics ─────────────────────────────────
        scores = [r.quality_score for r in self._results]
        avg_score = sum(scores) / len(scores) if scores else 0.0

        score_dist: dict[str, int] = {
            "90-100": 0,
            "80-89": 0,
            "70-79": 0,
            "60-69": 0,
            "50-59": 0,
            "0-49": 0,
        }
        for s in scores:
            if s >= 90:
                score_dist["90-100"] += 1
            elif s >= 80:
                score_dist["80-89"] += 1
            elif s >= 70:
                score_dist["70-79"] += 1
            elif s >= 60:
                score_dist["60-69"] += 1
            elif s >= 50:
                score_dist["50-59"] += 1
            else:
                score_dist["0-49"] += 1

        # ── Distributions ────────────────────────────────────────────
        register_dist: Counter[str] = Counter()
        domain_dist: Counter[str] = Counter()
        region_dist: Counter[str] = Counter()
        task_type_dist: Counter[str] = Counter()

        for result in self._results:
            rec = result.record
            register_dist[rec.get("register", "<missing>")] += 1
            domain_dist[rec.get("domain", "<missing>")] += 1
            region_dist[rec.get("region", "<missing>")] += 1
            task_type_dist[rec.get("task_type", "<missing>")] += 1

        # ── Issue aggregation ────────────────────────────────────────
        all_issues: list[ValidationIssue] = [
            issue
            for result in self._results
            for issue in result.issues
        ]
        issues_by_check: Counter[str] = Counter(
            issue.check_name for issue in all_issues
        )
        safety_issues = [
            issue
            for issue in all_issues
            if issue.check_name.startswith("safety.")
        ]
        duplicate_issues = [
            issue
            for issue in all_issues
            if issue.check_name.startswith("duplicate.") or issue.check_name == "schema.duplicate_id"
        ]

        error_count = sum(
            1 for i in all_issues if i.severity == Severity.ERROR
        )
        warning_count = sum(
            1 for i in all_issues if i.severity == Severity.WARNING
        )
        info_count = sum(
            1 for i in all_issues if i.severity == Severity.INFO
        )

        # ── Coverage ─────────────────────────────────────────────────
        coverage = self._analyze_coverage()

        # ── Per-record details ───────────────────────────────────────
        record_details: list[dict[str, Any]] = []
        for result in self._results:
            detail: dict[str, Any] = {
                "id": result.record_id,
                "is_valid": result.is_valid,
                "quality_score": result.quality_score,
            }
            if result.issues:
                detail["issues"] = [
                    {
                        "check": issue.check_name,
                        "severity": issue.severity.value,
                        "message": issue.message,
                        **({"field": issue.field} if issue.field else {}),
                        **(
                            {"suggestion": issue.suggestion}
                            if issue.suggestion
                            else {}
                        ),
                    }
                    for issue in result.issues
                ]
            record_details.append(detail)

        return ValidationReport(
            total_records=len(self._results),
            valid_records=len(valid),
            invalid_records=len(invalid),
            aggregate_quality_score=round(avg_score, 1),
            quality_score_distribution=score_dist,
            register_distribution=dict(register_dist.most_common()),
            domain_distribution=dict(domain_dist.most_common()),
            region_distribution=dict(region_dist.most_common()),
            task_type_distribution=dict(task_type_dist.most_common()),
            duplicate_count=len(duplicate_issues),
            coverage=coverage,
            error_count=error_count,
            warning_count=warning_count,
            info_count=info_count,
            safety_warnings=[
                {
                    "record_id": issue.record_id,
                    "check": issue.check_name,
                    "message": issue.message,
                    **(
                        {"suggestion": issue.suggestion}
                        if issue.suggestion
                        else {}
                    ),
                }
                for issue in safety_issues
            ],
            issues_by_check=dict(issues_by_check.most_common()),
            record_details=record_details,
        )

    # ── Output Writing ───────────────────────────────────────────────

    def write_outputs(
        self,
        clean_path: Path,
        report_path: Path,
    ) -> ValidationReport:
        """Write clean records and the validation report to disk.

        * ``clean_path``  — receives only records with zero ERRORs.
        * ``report_path`` — receives the full JSON report including
          per-record details, coverage analysis, and aggregate metrics.

        Returns:
            The :class:`ValidationReport` for programmatic use.
        """
        report = self.build_report()

        # ── Clean records ────────────────────────────────────────────
        clean_path.parent.mkdir(parents=True, exist_ok=True)
        with open(clean_path, "w", encoding="utf-8") as fh:
            for result in self._results:
                if result.is_valid:
                    json.dump(result.record, fh, ensure_ascii=False)
                    fh.write("\n")

        # ── Report ───────────────────────────────────────────────────
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_dict: dict[str, Any] = {
            "summary": {
                "total_records": report.total_records,
                "valid_records": report.valid_records,
                "invalid_records": report.invalid_records,
                "aggregate_quality_score": report.aggregate_quality_score,
                "errors": report.error_count,
                "warnings": report.warning_count,
                "info": report.info_count,
            },
            "quality_score_distribution": report.quality_score_distribution,
            "distributions": {
                "register": report.register_distribution,
                "domain": report.domain_distribution,
                "region": report.region_distribution,
                "task_type": report.task_type_distribution,
            },
            "coverage": {
                "missing_registers": report.coverage.missing_registers,
                "missing_task_types": report.coverage.missing_task_types,
                "missing_domains": report.coverage.missing_domains,
                "coverage_warnings": report.coverage.coverage_warnings,
                "register_x_task_type": report.coverage.cross_coverage,
            },
            "duplicates": {
                "total": report.duplicate_count,
                "exact": self._duplicate_detector.exact_count,
                "near": self._duplicate_detector.near_count,
            },
            "safety_warnings": report.safety_warnings,
            "issues_by_check": report.issues_by_check,
            "record_details": report.record_details,
        }

        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(report_dict, fh, ensure_ascii=False, indent=2)

        # ── Console summary ──────────────────────────────────────────
        self._print_summary(report)

        return report

    def _print_summary(self, report: ValidationReport) -> None:
        """Print a human-readable summary to stdout."""
        total = report.total_records
        valid = report.valid_records
        invalid = report.invalid_records
        score = report.aggregate_quality_score

        print("\n")
        print("  Tamil SFT Validation Report")
        print(f"  Records:  {total} total, {valid} valid, {invalid} invalid")
        print(f"  Quality:  {score}/100 (aggregate)")
        print(
            f"  Issues:   {report.error_count} errors, "
            f"{report.warning_count} warnings, "
            f"{report.info_count} info"
        )
        print(f"  Dupes:    {report.duplicate_count} duplicate findings")

        if report.safety_warnings:
            print(f"  Safety:   {len(report.safety_warnings)} warning(s) [!]")

        if report.coverage.missing_task_types:
            missing = ", ".join(report.coverage.missing_task_types)
            print(f"  Missing:  task_types [{missing}]")

        if report.coverage.coverage_warnings:
            n = len(report.coverage.coverage_warnings)
            print(f"  Coverage: {n} coverage warning(s)")

"""Create deterministic train/validation/test JSONL splits.

Records are assigned by a stable hash of their ID, so the same release always
produces the same split without depending on Python's randomized hash seed.
Exact duplicate prompt/response groups are kept together to reduce leakage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def _bucket(key: str) -> float:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:16], 16) / 16**16


def split_records(
    records: list[dict[str, Any]],
    *,
    validation_ratio: float = 0.1,
    test_ratio: float = 0.1,
) -> dict[str, list[dict[str, Any]]]:
    """Return deterministic train, validation and test partitions."""
    if validation_ratio < 0 or test_ratio < 0:
        raise ValueError("split ratios cannot be negative")
    if validation_ratio + test_ratio >= 1:
        raise ValueError("validation and test ratios must sum to less than 1")

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        prompt = str(record.get("prompt", "")).strip()
        response = str(record.get("response", "")).strip()
        signature = "\x1f".join((prompt, response))
        groups[signature].append(record)

    partitions = {"train": [], "validation": [], "test": []}
    for signature, group in groups.items():
        bucket = _bucket(signature)
        if bucket < test_ratio:
            target = "test"
        elif bucket < test_ratio + validation_ratio:
            target = "validation"
        else:
            target = "train"
        partitions[target].extend(group)

    for records_in_partition in partitions.values():
        records_in_partition.sort(key=lambda record: str(record.get("id", "")))
    return partitions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--validation-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    args = parser.parse_args()

    records = [
        json.loads(line)
        for line in args.input.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    partitions = split_records(
        records,
        validation_ratio=args.validation_ratio,
        test_ratio=args.test_ratio,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, partition in partitions.items():
        target = args.output_dir / f"{name}.jsonl"
        with target.open("w", encoding="utf-8") as output:
            for record in partition:
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"{name}: {len(partition)} records -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

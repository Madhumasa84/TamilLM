#!/usr/bin/env python3
"""
Migrate data/tamil_sft_seed.jsonl to the P2 taxonomy.

Register mapping:
  "spoken"   → "spoken_colloquial" (or "tanglish_code_switched" if
                notes mention Tanglish/code-mix OR flag == allowed_code_switch)
  "formal"   → depends on domain:
                  technical           → "technical_explanatory"
                  news / current_affairs → "news_formal"
                  culture / history   → "culture_history"
                  all others          → "modern_formal"
  "literary" → depends on domain:
                  culture / history   → "culture_history"
                  all others          → "literary_prose"

Domain mapping:
  "current_affairs" → "news"
  "workplace"       → "social"
  "government"      → "social"
  "food"            → "everyday"
  "travel"          → "everyday"
  "health"          → "everyday"
  Others already in new set → keep as-is

Usage:
    python scripts/migrate_schema.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "tamil_sft_seed.jsonl"

# ── Domain migration ─────────────────────────────────────────────────

DOMAIN_MAP: dict[str, str] = {
    "current_affairs": "news",
    "workplace": "social",
    "government": "social",
    "food": "everyday",
    "travel": "everyday",
    "health": "everyday",
}

NEW_DOMAINS = frozenset({
    "everyday", "news", "literature", "technical",
    "culture", "history", "social", "education",
})


def migrate_domain(old_domain: str) -> str:
    if old_domain in DOMAIN_MAP:
        return DOMAIN_MAP[old_domain]
    if old_domain in NEW_DOMAINS:
        return old_domain
    # Fallback: keep as-is (will trigger a warning in the validator)
    return old_domain


# ── Register migration ───────────────────────────────────────────────

def _is_tanglish(record: dict) -> bool:
    """Detect Tanglish/code-mix intent from flag or notes."""
    if record.get("flag") == "allowed_code_switch":
        return True
    notes = (record.get("notes") or "").lower()
    return "tanglish" in notes or "code-mix" in notes or "code mix" in notes


def migrate_register(record: dict, new_domain: str) -> str:
    old_register = record["register"]

    if old_register == "spoken":
        if _is_tanglish(record):
            return "tanglish_code_switched"
        return "spoken_colloquial"

    elif old_register == "formal":
        if new_domain == "technical":
            return "technical_explanatory"
        if new_domain in ("news",):
            # current_affairs already mapped to "news" by domain migration
            return "news_formal"
        if new_domain in ("culture", "history"):
            return "culture_history"
        # education, social (was workplace/government), everyday, etc.
        return "modern_formal"

    elif old_register == "literary":
        if new_domain in ("culture", "history"):
            return "culture_history"
        return "literary_prose"

    # Fallback — already new-style or unknown
    return old_register


# ── Main ─────────────────────────────────────────────────────────────

def main() -> None:
    if not DATA_PATH.exists():
        print(f"Error: {DATA_PATH} not found", file=sys.stderr)
        sys.exit(1)

    # Read all records
    records: list[dict] = []
    with open(DATA_PATH, "r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped:
                records.append(json.loads(stripped))

    print(f"Loaded {len(records)} records from {DATA_PATH}\n")

    # ── Before distributions ──────────────────────────────────────
    before_registers = Counter(r["register"] for r in records)
    before_domains = Counter(r["domain"] for r in records)

    print("=== BEFORE ===")
    print(f"  Registers: {dict(before_registers.most_common())}")
    print(f"  Domains:   {dict(before_domains.most_common())}")
    print()

    # ── Apply migration ───────────────────────────────────────────
    for record in records:
        # Domain first (register mapping depends on new domain)
        new_domain = migrate_domain(record["domain"])
        new_register = migrate_register(record, new_domain)

        record["domain"] = new_domain
        record["register"] = new_register

    # ── After distributions ───────────────────────────────────────
    after_registers = Counter(r["register"] for r in records)
    after_domains = Counter(r["domain"] for r in records)

    print("=== AFTER ===")
    print(f"  Registers: {dict(after_registers.most_common())}")
    print(f"  Domains:   {dict(after_domains.most_common())}")
    print()

    # ── Write back ────────────────────────────────────────────────
    with open(DATA_PATH, "w", encoding="utf-8") as fh:
        for record in records:
            json.dump(record, fh, ensure_ascii=False)
            fh.write("\n")

    print(f"Wrote {len(records)} records back to {DATA_PATH}")


if __name__ == "__main__":
    main()

"""Backward-compatible script wrapper for :mod:`validator.cli`."""

import io
import sys

from validator.cli import main as _cli_main

# Keep the Windows hardening behavior visible in this legacy entry point.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer,
        encoding="utf-8",
        errors="replace",
    )


def main() -> int:
    """Run the canonical CLI with explicit input/output paths."""
    return _cli_main()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Pipeline failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

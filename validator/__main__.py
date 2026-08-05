"""Allow ``python -m validator`` to run the canonical CLI."""

from validator.cli import main


raise SystemExit(main())

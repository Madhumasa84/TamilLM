# Contributing

Install the project with development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Before opening a pull request, run:

```bash
python -m pytest
ruff check .
mypy validator
```

Changes to validation behavior should include a focused regression test and a
short README or changelog note. Changes to dataset records must update the
dataset card, release checksum and validation report. Do not commit virtual
environments, coverage databases or local editor state.

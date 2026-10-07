# Honors-Thesis
Codebase for Honors Thesis on Agentic Document Translation for Accessible and Standardized University Content

Mark 1 remediates LaTeX Beamer slide projects for accessibility while preserving their
content and appearance. The pipeline builds a source-neutral document representation,
generates tagged PDFs, and records provenance, evaluation results, and run telemetry.

## How to run

Install the project dependencies:

```bash
uv sync
```

Run the test suite and lint checks:

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

The pipeline command examples will be added when the command line interface is completed in
Part 1.

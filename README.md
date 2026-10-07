# Honors-Thesis
Codebase for Honors Thesis on Agentic Document Translation for Accessible and Standardized University Content

Mark 1 remediates LaTeX Beamer slide projects for accessibility while preserving their
content and appearance. The pipeline builds a source-neutral document representation,
generates tagged PDFs, and records provenance, evaluation results, and run telemetry.

## How to run

Install Python 3.12 and uv, then install the workspace dependencies:

```bash
bash scripts/setup_uv_environment.sh
```

The setup script keeps the environment in `venv/` and exposes it through `.venv`. This
avoids macOS hidden file flags breaking editable package imports during repeated uv commands.

Copy the environment template and leave `MODEL_PROVIDER=fake` for local deterministic runs:

```bash
cp .env.example .env
```

The pipeline also requires `latexmk`, pdfLaTeX, and Poppler commands including `pdftoppm`,
`pdftotext`, and `pdfinfo`.

Run the three command line operations from the repository root:

```bash
uv run a11y preflight pipeline/tests/fixtures/lecture_sample
uv run a11y parse pipeline/tests/fixtures/lecture_sample --json
uv run a11y run pipeline/tests/fixtures/lecture_sample --effort medium --seed-weak slide_04/figure_01
```

`preflight` checks project dependencies without using model tokens. `parse` prints the
canonical document IR when `--json` is present and prints the element summary otherwise.
`run` creates a timestamped folder under `runs/` containing the manifest, IR snapshots,
candidate history, telemetry, working copies, rendered pages and crops, tagged PDF, updated
source project and zip, source diff, and HTML report. Use `--main FILE` when a project has
multiple Beamer entry points and `--out PATH` to choose another run folder root.

Run the test suite and lint checks:

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

## Part 2 backend

Start the installed PostgreSQL 18 service and create the local database once:

```bash
brew services start postgresql@18
createdb honors_thesis
```

Install every workspace package, copy the environment template if needed, and keep
`MODEL_PROVIDER=fake` for local work:

```bash
bash scripts/setup_uv_environment.sh
cp .env.example .env
```

Apply migrations and start the Django API:

```bash
MODEL_PROVIDER=fake uv run python backend/manage.py migrate
MODEL_PROVIDER=fake uv run python backend/manage.py runserver
```

In a second terminal, start the database task worker:

```bash
MODEL_PROVIDER=fake uv run python backend/manage.py db_worker
```

Run one queued task and exit with:

```bash
MODEL_PROVIDER=fake uv run python backend/manage.py db_worker \
  --batch --max-tasks 1 --no-reload --no-startup-delay
```

Run the PostgreSQL backend tests, all workspace tests, Django checks, migration checks, and
Ruff:

```bash
MODEL_PROVIDER=fake uv run pytest backend/projects/tests -q
MODEL_PROVIDER=fake uv run pytest -q
MODEL_PROVIDER=fake uv run python backend/manage.py check
MODEL_PROVIDER=fake uv run python backend/manage.py makemigrations --check --dry-run
uv run ruff check .
uv run ruff format --check .
```

Real Anthropic runs require `MODEL_PROVIDER=anthropic`, `ANTHROPIC_API_KEY`, and positive
`MODEL_INPUT_USD_PER_MTOK` and `MODEL_OUTPUT_USD_PER_MTOK` values in `.env`. The local test
suite and development workflow use only the fake provider.

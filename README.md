# Credit Risk & Receivables Dashboard

An open-source, Streamlit-based analytics dashboard for credit risk and
accounts-receivable management, built on synthetic data with a reproducible
data pipeline (DuckDB + Parquet). No Power BI, DAX, or proprietary BI tooling
anywhere in the stack.

> **Status:** scaffolding only — this is the initial repo skeleton. See
> `.cursorrules` and `docs/business_requirements.md` for the full build plan.

> This application uses a fictional dataset and a demonstration risk
> methodology. It is not a production credit-rating model, regulatory model,
> or substitute for professional underwriting judgement.

## What this project demonstrates
- End-to-end data engineering: synthetic data generation → validation →
  transformation → analytical storage (DuckDB/Parquet).
- A tested, documented risk-scoring and collections-prioritisation model.
- A production-shaped multipage Streamlit app with a proper service layer
  (no SQL scattered through UI code).
- Data-quality monitoring as a first-class feature, not an afterthought.
- Docker-based deployment with an open, portable stack.

## Tech stack
Python 3.11+, Streamlit, pandas, numpy, Plotly, DuckDB, PyArrow, Faker,
Pydantic, PyYAML, pytest, Ruff, Docker. Package management via **uv**.

## Repository structure
```
app/        Streamlit application (pages, components, services, utils)
src/        Data pipeline (generators, risk model, validation, orchestrator)
sql/        Reusable parameterised SQL
config/     Project configuration (project_config.yaml)
data/       raw / processed / exports / database (gitignored contents)
docs/       Full requirements, data dictionary, methodology docs
tests/      pytest suite
notebooks/  Exploratory analysis
```

## Local setup
Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run python -m src.run_pipeline --small
PYTHONPATH=. uv run streamlit run app/Home.py
```

Or use Make:
```bash
make install
make pipeline-small
make run
```

## Pipeline options
```bash
uv run python -m src.run_pipeline                 # full synthetic dataset
uv run python -m src.run_pipeline --small          # fast, small dataset for dev
uv run python -m src.run_pipeline --skip-defects   # skip data-quality injection
uv run python -m src.run_pipeline --config config/project_config.yaml
```

## Docker
```bash
docker compose up --build
```
Then open http://localhost:8501

## Testing
```bash
uv run pytest
uv run ruff check .
```

## Dashboard pages
1. **Executive Overview** — portfolio KPIs, exposure trends, risk mix, concentration, dynamic commentary.
2. **Collections Priorities** — worklist with priority scoring and explainability.
3. **Portfolio Risk** — exposure and concentration analysis by country/industry/customer.
4. **Customer Details** — full drill-down per customer across invoices, payments, risk, claims.
5. **Data Quality** — validation results, failure trends, refresh/freshness monitoring.

## Roadmap / not yet built
This repo currently contains scaffolding only (folder structure, config,
Docker, and Cursor project rules). The data pipeline and dashboard pages are
built incrementally — see `docs/business_requirements.md` section 27 for the
phase-by-phase plan and `.cursorrules` for how Cursor should approach each
phase.

## Disclaimer
All data is synthetically generated. Risk scoring and collections
prioritisation logic are simplified demonstration methodologies for
portfolio/showcase purposes and must not be used for real credit decisions.

# Credit Risk & Receivables Dashboard

An open-source, Streamlit-based analytics dashboard for credit risk and
accounts-receivable management, built on synthetic data with a reproducible
data pipeline (DuckDB + Parquet). No Power BI, DAX, or proprietary BI tooling
anywhere in the stack.

> **Status:** Phase 2 complete — synthetic data pipeline is available
> (`customers`, `invoices`, `payments`, `credit decisions`, `claims`, date
> dimension, optional DQ defect injection → CSV / Parquet / DuckDB).
> Next: Phase 3 (risk analytics). See `.cursorrules` and
> `docs/business_requirements.md` §27 for the full build plan.

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

After a successful run you get:

- CSV under `data/raw/`
- Parquet under `data/processed/`
- DuckDB at `data/database/credit_risk.duckdb` (path from config)

Outputs are reproducible from `pipeline.random_seed` in
`config/project_config.yaml`. Phase 2 data-model notes:
[`docs/data_model_phase2.md`](docs/data_model_phase2.md).

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

## Build progress
| Phase | Scope | Status |
|-------|--------|--------|
| 1 | Foundation (repo, config, logging, DuckDB utils, Home) | Done |
| 2 | Synthetic data generators + CSV/Parquet/DuckDB | Done |
| 3 | Risk analytics & collections priority | Next |
| 4 | Validation framework | Planned |
| 5 | Streamlit dashboard pages | Planned |
| 6 | Testing and optimisation | Planned |
| 7 | Documentation and deployment polish | Planned |

Detail: `docs/business_requirements.md` §27. Phase 2 step plan (historical):
`docs/phase2_plan.md`.

## Disclaimer
All data is synthetically generated. Risk scoring and collections
prioritisation logic are simplified demonstration methodologies for
portfolio/showcase purposes and must not be used for real credit decisions.

# Phase 2 — Synthetic Data (commit-sized steps)

Break Phase 2 (synthetic data generators, date dimension, DQ defect injection,
CSV/Parquet/DuckDB outputs) into small, independently verifiable steps. Each
step ends with a structured commit before the next begins.

Source of truth for phase scope: [business_requirements.md](business_requirements.md) §27.

---

## Scope

Deliver a runnable pipeline that generates **customers, invoices, payments,
credit decisions, claims**, a **date dimension**, and optional **data-quality
defect injection**, writing **CSV + Parquet + DuckDB**. Reproducible from
`pipeline.random_seed`. CLI: `--small`, `--skip-defects`, `--config`.

**Out of scope (later phases):** risk scoring / collections priority (Phase 3),
validation framework (Phase 4), dashboard wiring (Phase 5).

## Starting point

Phase 1 is done. Missing for Phase 2: `src/run_pipeline.py`, all generators,
writers, schema DDL, and real generator tests. Config knobs already exist in
[`config/project_config.yaml`](../config/project_config.yaml) /
[`src/config.py`](../src/config.py). [`app/Home.py`](../app/Home.py) already
expects `dim_customer` and `fact_invoice` when present.

## Commit message structure (required every step)

Use this template for every Phase 2 commit (HEREDOC when committing):

```text
phase2(step-NN): <imperative summary ≤72 chars>

Why:
<1–2 sentences on the purpose of this step>

What:
- <file/module change>
- <file/module change>

Verify:
- <exact command(s) that must pass before the next step>
```

Rules:

- One logical deliverable per commit; do not batch unrelated generators.
- Run the **Verify** commands; fix failures before committing.
- Commit only after Verify passes; then move to the next step.
- Do not start step N+1 until step N is committed.

```mermaid
flowchart LR
  schema[Schema_and_IO]
  cli[CLI_skeleton]
  dates[Date_dim]
  cust[Customers]
  inv[Invoices]
  pay[Payments]
  credit[Credit_decisions]
  claims[Claims]
  defects[DQ_injection]
  orch[Orchestrator_load]
  gate[Phase2_gate]
  schema --> cli --> dates --> cust --> inv --> pay --> credit --> claims --> defects --> orch --> gate
```

### Step checklist

| Step | Deliverable | Commit summary |
|------|-------------|----------------|
| 01 | Schema + data-model notes | `phase2(step-01): add Phase 2 dimensional schema and data-model notes` |
| 02 | Pipeline CLI skeleton | `phase2(step-02): add run_pipeline CLI with config and logging` |
| 03 | Shared Faker/IO helpers | `phase2(step-03): add seeded Faker helpers and CSV/Parquet writers` |
| 04 | Date dimension | `phase2(step-04): generate deterministic date dimension` |
| 05 | Customers | `phase2(step-05): generate synthetic customers with filter dimensions` |
| 06 | Invoices | `phase2(step-06): generate synthetic invoices linked to customers` |
| 07 | Payments | `phase2(step-07): generate synthetic payments linked to invoices` |
| 08 | Credit decisions | `phase2(step-08): generate synthetic credit-decision history` |
| 09 | Claims | `phase2(step-09): generate synthetic insurance claims` |
| 10 | DQ defect injection | `phase2(step-10): inject configurable data-quality defects` |
| 11 | Orchestrator + DuckDB load | `phase2(step-11): orchestrate full synthetic pipeline into DuckDB` |
| 12 | Phase 2 gate + README | `phase2(step-12): complete Phase 2 gate and update README status` |

---

## Step 01 — Data model + DuckDB schema for raw entities

**Deliver:** Document column contracts and implement DDL for Phase 2 tables only.

**Files:**

- [`sql/create_schema.sql`](../sql/create_schema.sql) — create `dim_date`, `dim_customer`, `fact_invoice`, `fact_payment`, `fact_credit_decision`, `fact_claim` (and optional `pipeline_runs` stub for refresh metadata Home can read later)
- New: `docs/data_model_phase2.md` — short column list + grain + FK notes (enough for generators; full dictionary stays Phase 7)

**Column design defaults (locked for this phase):**

- `dim_customer`: customer_id, name, country, region, industry, annual_revenue, account_manager, collections_owner, status, credit_insurance_status, credit_limit, currency, business_unit, created_date
- `fact_invoice`: invoice_id, customer_id, invoice_date, due_date, invoice_amount, outstanding_amount, currency, dispute_flag, status, ageing inputs derivable later
- `fact_payment`: payment_id, invoice_id, customer_id, payment_date, payment_amount
- `fact_credit_decision`: decision_id, customer_id, decision_date, previous_limit, new_limit, decision_type, decision_reason
- `fact_claim`: claim_id, customer_id, invoice_id, claim_date, claim_amount, status, insurer, recovery_amount
- `dim_date`: date_key, full_date, year, month, month_name, quarter, is_month_end

**Verify:** Manual review that Home’s expected table names match (`dim_customer`, `fact_invoice`).

**Commit:** `phase2(step-01): add Phase 2 dimensional schema and data-model notes`

---

## Step 02 — Pipeline CLI skeleton (no generation yet)

**Deliver:** `python -m src.run_pipeline` parses args, loads config, sets logging, exits cleanly with a “not implemented” or no-op path that still validates config.

**Files:**

- New: [`src/run_pipeline.py`](../src/run_pipeline.py) — argparse: `--small`, `--skip-defects`, `--config`; resolve customer count from config; call `setup_logging`
- Touch [`Makefile`](../Makefile) only if needed (targets already point here)

**Verify:**

```bash
uv run python -m src.run_pipeline --help
uv run python -m src.run_pipeline --small --skip-defects
uv run pytest tests/test_foundation.py -q
```

**Commit:** `phase2(step-02): add run_pipeline CLI with config and logging`

---

## Step 03 — Shared generator I/O helpers

**Deliver:** Seeded RNG/Faker factory + writers for CSV and Parquet under `data/raw/` and `data/processed/`.

**Files:**

- New: `src/generators/__init__.py`
- New: `src/generators/common.py` — `make_faker(seed)`, path helpers, `write_csv`, `write_parquet`
- Update: `tests/test_generators.py` — replace TBD stub with tests for seed reproducibility of a tiny helper and path writing to a temp dir

**Verify:**

```bash
uv run pytest tests/test_generators.py -q
uv run ruff check src/generators
```

**Commit:** `phase2(step-03): add seeded Faker helpers and CSV/Parquet writers`

---

## Step 04 — Date dimension generator

**Deliver:** Generate `dim_date` covering pipeline history window (`history_months` from config, anchored to a fixed “as-of” date derived from seed/config).

**Files:**

- New: `src/generators/dates.py` — `generate_dim_date(config) -> DataFrame`
- Extend `tests/test_generators.py` — row count, uniqueness of `date_key`, no gaps for the window

**Verify:** `uv run pytest tests/test_generators.py -q -k date`

**Commit:** `phase2(step-04): generate deterministic date dimension`

---

## Step 05 — Customer generator

**Deliver:** `dim_customer` for `num_customers` / `small_num_customers`, all filter dimensions populated (country, region, industry, managers, insurance, status, currency, business unit).

**Files:**

- New: `src/generators/customers.py`
- Tests: fixed seed → identical IDs/names; row count matches requested N; required columns present; no null PKs

**Verify:** `uv run pytest tests/test_generators.py -q -k customer`

**Commit:** `phase2(step-05): generate synthetic customers with filter dimensions`

---

## Step 06 — Invoice generator

**Deliver:** `fact_invoice` linked to customers over the history window; realistic amounts, due dates, outstanding balances, dispute flags. No risk scores.

**Files:**

- New: `src/generators/invoices.py`
- Tests: every `customer_id` exists; invoice dates within history; `outstanding_amount <= invoice_amount` for clean rows; deterministic under seed

**Verify:** `uv run pytest tests/test_generators.py -q -k invoice`

**Commit:** `phase2(step-06): generate synthetic invoices linked to customers`

---

## Step 07 — Payment generator

**Deliver:** `fact_payment` referencing invoices; partial/full payments; dates after invoice date.

**Files:**

- New: `src/generators/payments.py`
- Tests: FK integrity to invoices; payment_date >= invoice_date; deterministic under seed

**Verify:** `uv run pytest tests/test_generators.py -q -k payment`

**Commit:** `phase2(step-07): generate synthetic payments linked to invoices`

---

## Step 08 — Credit-decision generator

**Deliver:** Sparse credit-limit change history per customer.

**Files:**

- New: `src/generators/credit_decisions.py`
- Tests: FK to customers; `new_limit` / `previous_limit` populated; deterministic

**Verify:** `uv run pytest tests/test_generators.py -q -k credit`

**Commit:** `phase2(step-08): generate synthetic credit-decision history`

---

## Step 09 — Claims generator

**Deliver:** Claims/recoveries for a subset of overdue/insured exposure; statuses and insurers.

**Files:**

- New: `src/generators/claims.py`
- Tests: optional invoice FK when present; amounts non-negative; deterministic

**Verify:** `uv run pytest tests/test_generators.py -q -k claim`

**Commit:** `phase2(step-09): generate synthetic insurance claims`

---

## Step 10 — Data-quality defect injection

**Deliver:** Configurable defect injector controlled by `inject_data_quality_defects`, `defect_rate`, and CLI `--skip-defects`.

**Defect types (minimum set aligned with Page 5 / DoD):** missing customer identifiers, duplicate invoices, payments larger than invoice value, invalid dates. Inject after clean generation; keep a small audit log DataFrame of what was injected (for Phase 4 later).

**Files:**

- New: `src/generators/defects.py`
- Tests: `--skip` / rate 0 → unchanged copy; rate > 0 → measurable defects; still deterministic under seed

**Verify:** `uv run pytest tests/test_generators.py -q -k defect`

**Commit:** `phase2(step-10): inject configurable data-quality defects`

---

## Step 11 — Orchestrator: write files + load DuckDB

**Deliver:** Wire generators in order inside `run_pipeline`: generate → optional defects → write CSV/Parquet → apply [`sql/create_schema.sql`](../sql/create_schema.sql) → load tables into DuckDB at `database.path`. Record a simple `pipeline_runs` row (started/finished/status/seed/customer_count).

**Files:**

- Update [`src/run_pipeline.py`](../src/run_pipeline.py)
- New: `src/io_duckdb.py` (or extend [`src/db.py`](../src/db.py)) — execute schema + `INSERT`/`COPY` from DataFrames
- Update: `tests/test_pipeline.py` — replace TBD with an integration test using `--small` into a temp DB path (override config via temp YAML)

**Verify:**

```bash
uv run python -m src.run_pipeline --small --skip-defects
uv run pytest tests/test_pipeline.py tests/test_generators.py -q
# optional smoke: PYTHONPATH=. uv run streamlit run app/Home.py
```

**Commit:** `phase2(step-11): orchestrate full synthetic pipeline into DuckDB`

---

## Step 12 — Phase 2 gate + README status bump

**Deliver:** Confirm reproducibility and document that Phase 2 is complete.

**Checks:**

- Two runs with same seed produce identical row counts and checksums on key columns (test in `tests/test_pipeline.py`)
- Full foundation + generator + pipeline tests green
- Update README status line from “scaffolding only” to note Phase 2 synthetic pipeline is available

**Verify:**

```bash
uv run pytest tests/test_foundation.py tests/test_generators.py tests/test_pipeline.py -q
uv run ruff check src tests
uv run python -m src.run_pipeline --small
```

**Commit:** `phase2(step-12): complete Phase 2 gate and update README status`

---

## Working rhythm (per step)

1. Implement only that step’s files.
2. Run that step’s **Verify** commands.
3. Commit with the template above (only when explicitly asked to commit, or when you say “commit step N”).
4. Stop and report: changed files, verify results, commit hash/message.
5. Only then start the next step.

## Done when

- `uv run python -m src.run_pipeline --small` creates DuckDB + CSV/Parquet
- `--skip-defects` skips injection; default config injects at `defect_rate`
- Same seed → same outputs
- Home page can count `dim_customer` / `fact_invoice` without crashing
- 12 commits exist, each matching the template

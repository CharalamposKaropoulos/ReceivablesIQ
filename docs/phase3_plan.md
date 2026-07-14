# Phase 3 — Risk Analytics (commit-sized steps)

> **Status: in progress.** Phases 1–2 complete. This plan breaks Phase 3 into
> small, independently verifiable steps. Source of truth for phase scope:
> [business_requirements.md](business_requirements.md) §27.

Break Phase 3 (risk model, risk history, collections-priority model, monthly
snapshots, portfolio aggregations, executive metrics) into commit-sized steps.
Dashboard UI, filters, and query services remain Phase 5.

---

## Scope

Deliver a pipeline extension that, after Phase 2 synthetic entities exist:

1. Builds **point-in-time customer features** at each month-end (no future-data leakage)
2. Scores **demonstration risk** (score, category, component breakdown)
3. Scores **collections priority** (score, recommended priority/action, components)
4. Writes **`customer_snapshot`**, **`portfolio_monthly`**, and **`executive_metrics`**
5. Persists them to **CSV + Parquet + DuckDB** alongside Phase 2 tables

Reproducible from `pipeline.random_seed` and config-driven model weights.
CLI remains `python -m src.run_pipeline` (`--small`, `--skip-defects`, `--config`).

**Out of scope (later phases):** validation framework (Phase 4), Streamlit page
wiring / `app/services` / TBD query SQL (Phase 5), full methodology docs in
`risk_methodology.md` / `collections_methodology.md` (Phase 7).

## Starting point

Phase 2 is done. Available today:

- `python -m src.run_pipeline` → `dim_date`, `dim_customer`, `fact_invoice`,
  `fact_payment`, `fact_credit_decision`, `fact_claim`, `pipeline_runs`
- Fixed as-of: `DEFAULT_AS_OF_DATE = 2026-06-30` in
  [`src/generators/dates.py`](../src/generators/dates.py)
- Config: [`config/project_config.yaml`](../config/project_config.yaml) /
  [`src/config.py`](../src/config.py)
- Home already prefers `executive_metrics` then `customer_snapshot` for exposure
  ([`app/Home.py`](../app/Home.py))
- No risk/collections/analytics modules yet; `tests/test_risk_model.py` and
  `tests/test_collection_priorities.py` are TBD stubs

## Locked design

### Analytical tables

| Table | Grain | Role |
|-------|--------|------|
| `customer_snapshot` | `(customer_id, as_of_date)` month-ends | PIT features + risk score/category + collections score/priority/action + component columns. Risk history and collections worklist both read this table. |
| `portfolio_monthly` | `(as_of_date, slice_type, slice_value)` | Pre-aggregated slices (country, industry, risk_category, ageing_bucket, insurance) for portfolio/exec charts. |
| `executive_metrics` | `(reporting_date)` month-end | Portfolio KPIs including `total_exposure` and `reporting_date` (Home), plus overdue, utilisation, claims, MoM fields. |

### Point-in-time rules (no future leakage)

For each month-end `as_of` in `dim_date` where `is_month_end` and
`as_of <= DEFAULT_AS_OF_DATE`:

- Only invoices with `invoice_date <= as_of`
- Reconstruct outstanding:
  `max(0, invoice_amount - sum(payments where payment_date <= as_of))`
  — do **not** use static `fact_invoice.outstanding_amount` for historical months
- Overdue = reconstructed outstanding where `due_date < as_of`
- Credit limit = latest `fact_credit_decision.new_limit` with
  `decision_date <= as_of`, else `dim_customer.credit_limit`
- Exclude payments/claims/decisions with dates after `as_of`

### Demonstration models (config-driven)

**Risk (0–100):** weighted components — ageing/DPD severity, utilisation,
payment behaviour (% late + avg days to pay), overdue ratio, dispute intensity.
Categories: `low` / `medium` / `high` / `critical` via configurable thresholds.

**Collections:** weighted blend of risk score, overdue balance, oldest DPD,
dispute balance, limit breach → priority score, recommended priority tier, and
**recommended action** from the locked BRD §10 list:

- immediate escalation
- senior collections review
- contact within 24 hours
- standard collection contact
- monitor
- resolve dispute
- consider credit hold
- prepare insurance claim

Store component columns on `customer_snapshot` for explainability.

### Code layout

```text
src/analytics/
  __init__.py
  features.py      # PIT feature builder for one as_of
  risk_model.py
  collections.py
  snapshots.py     # all month-ends → customer_snapshot
  portfolio.py     # portfolio_monthly + executive_metrics
```

Orchestration order inside `run_pipeline`: generate → optional defects → write
raw CSV/Parquet → load Phase 2 tables → run analytics → write analytical
CSV/Parquet → load analytical tables → record `pipeline_runs`.

## Commit message structure (required every step)

Use this template for every Phase 3 commit (HEREDOC when committing).
Subject type follows Conventional Commits; put the step number in the body:

```text
feat(<scope>): <imperative summary ≤72 chars>

Phase 3 step NN.

Why:
<1–2 sentences on the purpose of this step>

What:
- <file/module change>
- <file/module change>

Verify:
- <exact command(s) that must pass before the next step>
```

Rules:

- One logical deliverable per commit; do not batch unrelated analytics modules.
- Run the **Verify** commands; fix failures before committing.
- Commit only after Verify passes; then move to the next step.
- Do not start step N+1 until step N is committed (when committing).

```mermaid
flowchart LR
  schema[Schema_and_model]
  config[Config]
  features[PIT_features]
  risk[Risk_model]
  coll[Collections]
  snap[Snapshots]
  port[Portfolio]
  exec[Executive]
  orch[Orchestrator]
  gate[Phase3_gate]
  schema --> config --> features --> risk --> coll --> snap --> port --> exec --> orch --> gate
```

### Step checklist

| Step | Deliverable | Status | Commit summary |
|------|-------------|--------|----------------|
| 01 | Analytical schema + data-model notes | Done | `feat(schema): add Phase 3 analytical tables and data-model notes` |
| 02 | Risk / collections config | Done | `feat(config): add risk and collections model configuration` |
| 03 | PIT feature engineering | Planned | `feat(pipeline): add point-in-time customer feature builder` |
| 04 | Risk scoring model | Planned | `feat(pipeline): add demonstration risk scoring model` |
| 05 | Collections priority model | Planned | `feat(pipeline): add collections priority scoring model` |
| 06 | Monthly customer snapshots | Planned | `feat(pipeline): build monthly customer_snapshot rows` |
| 07 | Portfolio monthly aggregations | Planned | `feat(pipeline): add portfolio_monthly aggregations` |
| 08 | Executive metrics | Planned | `feat(pipeline): add executive_metrics with MoM fields` |
| 09 | Orchestrator + DuckDB load | Planned | `feat(pipeline): orchestrate analytics into DuckDB` |
| 10 | Phase 3 gate + README | Planned | `feat(pipeline): complete Phase 3 gate and update status` |

---

## Step 01 — Analytical data model + DuckDB schema

**Deliver:** Document column contracts and extend DDL for the three analytical
tables. No scoring logic yet.

**Files:**

- Update [`sql/create_schema.sql`](../sql/create_schema.sql) — add
  `customer_snapshot`, `portfolio_monthly`, `executive_metrics`
- New: [`docs/data_model_phase3.md`](data_model_phase3.md) — column list, grain,
  FK/PIT notes (full dictionary stays Phase 7)
- Update [`docs/data_model.md`](data_model.md) — point at Phase 3 model doc

**Column design defaults (locked for this phase):**

`customer_snapshot` (key columns):

- Keys: `customer_id`, `as_of_date`
- Exposure: `outstanding_amount`, `overdue_amount`, `credit_limit`,
  `available_credit`, `utilisation`
- Behaviour: `oldest_days_past_due`, `overdue_invoice_count`, `dispute_balance`,
  `avg_days_to_pay`, `pct_invoices_paid_late`, `ageing_bucket`
- Dimensions (denormalised for filters): `country`, `region`, `industry`,
  `collections_owner`, `credit_insurance_status`, `currency`, `business_unit`,
  `status`, `account_manager`, `customer_name`
- Risk: `risk_score`, `risk_category`, plus component columns
  (`risk_comp_ageing`, `risk_comp_utilisation`, `risk_comp_payment`,
  `risk_comp_overdue_ratio`, `risk_comp_dispute`)
- Collections: `collection_priority_score`, `recommended_priority`,
  `recommended_action`, plus component columns
  (`coll_comp_risk`, `coll_comp_overdue`, `coll_comp_dpd`,
  `coll_comp_dispute`, `coll_comp_limit_breach`)

`portfolio_monthly`:

- `as_of_date`, `slice_type`, `slice_value`, `customer_count`,
  `outstanding_amount`, `overdue_amount`, `high_critical_exposure`

`executive_metrics`:

- `reporting_date`, `total_exposure`, `overdue_exposure`, `pct_overdue`,
  `credit_limit_utilisation`, `claims_submitted`, `recoveries`,
  `customers_exceeding_limits`, `mom_exposure_change`, `mom_overdue_change`,
  `high_critical_exposure`, `customer_count`, `invoice_count`

**Verify:** Manual review that Home’s expected columns exist on
`executive_metrics` (`total_exposure`, `reporting_date`) and
`customer_snapshot` (`outstanding_amount`, `as_of_date`).

**Commit:** `feat(schema): add Phase 3 analytical tables and data-model notes`

---

## Step 02 — Risk / collections model configuration

**Deliver:** Add `risk_model` and `collections_model` sections to YAML and
validate them with Pydantic before any scoring code runs.

**Files:**

- Update [`config/project_config.yaml`](../config/project_config.yaml)
- Update [`src/config.py`](../src/config.py) — `RiskModelConfig`,
  `CollectionsModelConfig` with weights and category/priority thresholds
- Extend foundation/config tests so invalid weights or missing sections fail clearly

**Defaults (demonstration only — not a production model):**

- Risk weights sum to 1.0 across the five components listed in locked design
- Category thresholds: low &lt; 25, medium &lt; 50, high &lt; 75, critical ≥ 75
- Collections weights for risk / overdue / DPD / dispute / limit-breach
- Priority thresholds map score bands to recommended priority labels;
  action mapping uses the locked BRD §10 list

**Verify:**

```bash
uv run python -c "from src.config import load_config; load_config()"
uv run pytest tests/test_foundation.py -q
```

**Commit:** `feat(config): add risk and collections model configuration`

---

## Step 03 — Point-in-time feature engineering

**Deliver:** Given Phase 2 entity DataFrames and a single `as_of` date, return
one feature row per customer. Enforce leakage rules from locked design.

**Files:**

- New: `src/analytics/__init__.py`
- New: `src/analytics/features.py` —
  `build_customer_features(customers, invoices, payments, credit_decisions, as_of) -> DataFrame`
- New or update tests (prefer extending a focused analytics test module) —
  reconstruct outstanding from payments; events after `as_of` ignored;
  credit limit as-of decision history

**Verify:**

```bash
uv run pytest tests/ -q -k "feature or leakage or pit"
uv run ruff check src/analytics
```

**Commit:** `feat(pipeline): add point-in-time customer feature builder`

---

## Step 04 — Risk scoring model

**Deliver:** Score feature rows into `risk_score` (0–100), `risk_category`, and
named component columns. Pure function of features + config; deterministic.

**Files:**

- New: `src/analytics/risk_model.py` —
  `score_risk(features_df, risk_config) -> DataFrame`
- Replace TBD in [`tests/test_risk_model.py`](../tests/test_risk_model.py) —
  known fixture → expected score/category; weight change moves score; empty
  input returns empty frame with schema

**Verify:**

```bash
uv run pytest tests/test_risk_model.py -q
uv run ruff check src/analytics
```

**Commit:** `feat(pipeline): add demonstration risk scoring model`

---

## Step 05 — Collections priority model

**Deliver:** Score feature+risk rows into `collection_priority_score`,
`recommended_priority`, `recommended_action`, and component columns.
Actions restricted to the locked BRD §10 list.

**Files:**

- New: `src/analytics/collections.py` —
  `score_collections(scored_df, collections_config) -> DataFrame`
- Replace TBD in
  [`tests/test_collection_priorities.py`](../tests/test_collection_priorities.py) —
  action always in allowed set; dispute-heavy cases prefer resolve-dispute /
  related actions; deterministic under fixed inputs

**Verify:**

```bash
uv run pytest tests/test_collection_priorities.py tests/test_risk_model.py -q
```

**Commit:** `feat(pipeline): add collections priority scoring model`

---

## Step 06 — Monthly customer snapshots

**Deliver:** For every month-end in `dim_date` up to the pipeline as-of, build
features → risk → collections and concatenate into `customer_snapshot`.

**Files:**

- New: `src/analytics/snapshots.py` —
  `build_customer_snapshots(entities, config, as_of) -> DataFrame`
- Tests: one row per customer per month-end; `as_of_date` values only month-ends;
  later month can differ from earlier without peeking at future payments
  (leakage regression)

**Verify:**

```bash
uv run pytest tests/ -q -k "snapshot or risk_model or collection"
```

**Commit:** `feat(pipeline): build monthly customer_snapshot rows`

---

## Step 07 — Portfolio monthly aggregations

**Deliver:** Aggregate `customer_snapshot` into `portfolio_monthly` slices for
country, industry, risk_category, ageing_bucket, and credit_insurance_status.

**Files:**

- New: `src/analytics/portfolio.py` (portfolio half) —
  `build_portfolio_monthly(customer_snapshot) -> DataFrame`
- Tests: slice types present; sums of outstanding by country reconcile to
  snapshot totals for a given `as_of_date`

**Verify:** `uv run pytest tests/ -q -k portfolio`

**Commit:** `feat(pipeline): add portfolio_monthly aggregations`

---

## Step 08 — Executive metrics

**Deliver:** One row per month-end reporting date with executive KPIs and MoM
deltas vs the previous month-end. Column names must satisfy Home’s queries.

**Files:**

- Extend `src/analytics/portfolio.py` —
  `build_executive_metrics(customer_snapshot, claims, ...) -> DataFrame`
- Tests: latest row has non-null `total_exposure` and `reporting_date`; MoM
  null on first month; customers-exceeding-limits counts utilisation &gt; 1

**Verify:**

```bash
uv run pytest tests/ -q -k "executive or portfolio or snapshot"
```

**Commit:** `feat(pipeline): add executive_metrics with MoM fields`

---

## Step 09 — Orchestrator: write analytics + load DuckDB

**Deliver:** Wire analytics after Phase 2 entity generation inside
`run_pipeline`: build snapshots → portfolio → executive metrics → write
CSV/Parquet → extend load order → insert into DuckDB.

**Files:**

- Update [`src/run_pipeline.py`](../src/run_pipeline.py) — `_OUTPUT_SPECS` and
  analytics stage
- Update [`src/io_duckdb.py`](../src/io_duckdb.py) — `ENTITY_LOAD_ORDER` includes
  analytical tables after facts
- Update [`tests/test_pipeline.py`](../tests/test_pipeline.py) — `--small` run
  creates analytical tables; row counts &gt; 0; Home-required columns present;
  same-seed reproducibility includes snapshot checksums

**Verify:**

```bash
uv run python -m src.run_pipeline --small --skip-defects
uv run pytest tests/test_pipeline.py tests/test_risk_model.py tests/test_collection_priorities.py -q
# optional smoke: PYTHONPATH=. uv run streamlit run app/Home.py
```

**Commit:** `feat(pipeline): orchestrate analytics into DuckDB`

---

## Step 10 — Phase 3 gate + README status bump

**Deliver:** Confirm leakage, reproducibility, and document that Phase 3 is
complete.

**Checks:**

- Same seed → identical analytical row counts and checksums
- Explicit leakage test green (features at month M ignore events after M)
- Foundation + generator + pipeline + risk + collections tests green
- README / §27 / `.cursorrules` mark Phase 3 complete; next is Phase 4
- Home can read `executive_metrics.total_exposure` without crashing when DB present

**Verify:**

```bash
uv run pytest tests/test_foundation.py tests/test_generators.py tests/test_pipeline.py tests/test_risk_model.py tests/test_collection_priorities.py -q
uv run ruff check src tests
uv run python -m src.run_pipeline --small
```

**Commit:** `feat(pipeline): complete Phase 3 gate and update status`

---

## Working rhythm (per step)

1. Implement only that step’s files.
2. Run that step’s **Verify** commands.
3. Commit with the template above (only when explicitly asked to commit, or when you say “commit step N”).
4. Stop and report: changed files, verify results, commit hash/message.
5. Only then start the next step.

## Done when

All criteria met:

- `uv run python -m src.run_pipeline --small` creates DuckDB with
  `customer_snapshot`, `portfolio_monthly`, and `executive_metrics`
- Risk scores and collections priorities present on snapshots
- Historical snapshots avoid future-data leakage (tested)
- Same seed → same analytical outputs
- Home page can show exposure from `executive_metrics` when present
- README and §27 mark Phase 3 complete; next work is Phase 4 (validation)

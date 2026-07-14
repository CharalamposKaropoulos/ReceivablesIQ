# Data model

Phase 2 raw synthetic entities (grain, columns, FKs) are documented in
[`data_model_phase2.md`](data_model_phase2.md).

Phase 3 analytical tables (`customer_snapshot`, `portfolio_monthly`,
`executive_metrics`) are documented in
[`data_model_phase3.md`](data_model_phase3.md).

DDL for both phases: [`sql/create_schema.sql`](../sql/create_schema.sql).

The full data dictionary and expanded methodology docs remain **Phase 7**.
Until then, treat `data_model_phase2.md` and `data_model_phase3.md` as the
living contracts for tables produced by `python -m src.run_pipeline`.

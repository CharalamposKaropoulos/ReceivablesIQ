# Data model

Phase 2 raw synthetic entities (grain, columns, FKs) are documented in
[`data_model_phase2.md`](data_model_phase2.md). DDL:
[`sql/create_schema.sql`](../sql/create_schema.sql).

The full data dictionary and expanded analytical model (risk scores,
collections priority, snapshots, validation metadata) will be completed in
**Phase 7**. Until then, treat `data_model_phase2.md` as the living contract
for tables produced by `python -m src.run_pipeline`.

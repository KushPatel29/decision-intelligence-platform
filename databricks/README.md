# Databricks execution handoff - release 0.4.0

Free Edition explicitly disallows automated console control. Use a supported workspace API/connector or manual execution. No hosted notebook/table was created.

Import medallion.py. Upload only generated data/bronze/*.parquet to an approved volume and data/gold/*.parquet to a separate scored-mart volume; exclude data/simulation_audit. Set catalog, project_schema (corridor_v2), raw_path, gold_path and as_of to approved values. Use a fresh schema; fail-if-table-exists protects previous runs. Provisioning is not claimed to be transactional.

The notebook validates trip contracts/FKs, creates bronze/silver, recomputes the complete point-in-time Spark allowlist and zone-day totals, publishes daily channel engagement and imports eight scored/history marts with grain/FK/cutoff checks. Predictions originate in upstream scoring; this is not hosted training. Timezone is America/Toronto.

Reconcile features against DuckDB; retain counts, schemas, grains, run ID, runtime version and Delta receipts. Only then mark hosted execution complete. Check actual workspace connectivity before AWS integration.

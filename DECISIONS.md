# Architectural decisions - 0.4.0

## Reproducible local reference
DuckDB/Parquet is the inspectable reference. PySpark recomputes the 25-feature kernel; Databricks imports upstream scored business marts with explicit grains. A previous local Spark/Delta receipt is distinct from a new hosted run.

## Validation selection, then acceptance
Validation alone chooses candidates. An untouched acceptance test can reject deployment against a predeclared baseline. Rejected demand stays recorded while the established seasonal baseline serves. Historical-margin contribution also beats its learned alternative on validation. Later experiments must use fresh outcomes rather than retuning on the test.

## Separate economic horizons
The campaign objective includes 30-day net contribution, network value and discounted signed days31-90 incremental margin. Retention is a separate KPI. This prevents double monetizing the same retained revenue. Twelve-month customer value is still a heuristic projection and does not enter as validated causal value.

## Shared discrete price/campaign solve
Price options and promotion/reward contacts share protected capacity, spending, inventory, points and ROI. Constant elasticity and separable treatment/price effects are declared assumptions. Gurobi and HiGHS use the same constraints; the local license bounds the shortlist to 600 customers.

## Fail-closed releases and durable review
Exclusive refresh locks, atomic JSON writes, release hashes and run receipts prevent serving known partial results. Reviewed allocations preserve owner, release identity and an audit reference in SQLite WAL storage. Production refuses local anonymous mode and requires OIDC subject allowlisting. Authentication, storage and load need actual staging tests.

## Explicit registry and cloud boundaries
Nine local MLflow pyfunc adapters preserve loaded scoring behavior. Candidate aliases are not approved champions; promotion/rollback/archive needs a matching review receipt and audit record. Six SageMaker workflows use one matching custom container and fail before registry/batch when held-out acceptance fails. Successful gates register PendingManualApproval; no persistent endpoint is provisioned.

## Native reporting has independent acceptance
The revised PBIP/PBIR and TMDL source has 16 tables, 32 measures and eight pages with schema validation. The previous native receipt applies to 0.3 only. Revised Desktop refresh, live DAX totals and visual inspection remain open.

# Status: release 1.1

Assessed 6 October 2026, against the committed 25,000-customer run.

## Verified

| Area | Evidence |
|---|---|
| Pipeline | End to end in 475 s: 3,680,249 trips, 1,412,304 digital events, 4,147 quarantined; release gate passed (8 of 8 checks) |
| Optimisation | 112,563-binary MIP proven optimal (gap 1.5e-7); Gurobi confirmed the 445-variable residual |
| Evaluation | Plan reaches 75% of the perfect-knowledge ceiling; propensity targeting 7%; policy trial +$1.40 per customer (95% CI $0.23 to $2.57) |
| Tests | 200+ passing, including every app page, the API, the Power BI model's references, and the registry scorer reproducing the plan's effects |
| Spark | PySpark features equal DuckDB's on all 39 features (max difference 2.2e-11) over the full silver layer |
| Power BI | All 149 measures executed against Power BI's engine; the HTML panels rendered from its output with no overflow; byte-for-byte drift gate |
| Databricks | All four job notebooks executed locally in task order (`databricks/local_run.py`) |

## Open

| Item | What it needs |
|---|---|
| Hosted Databricks run | The workspace owner's browser sign-in; then `python databricks/run_job.py --host …` records a receipt in `databricks/receipts/` |
| Hosted SageMaker run | An AWS account role, a bucket and a spending limit (see `aws/README.md`) |
| Opening the report in Desktop with the HTML Content visual loaded | A Desktop session that can reach AppSource; the measures themselves are verified |
| Tableau | Not built; the posting accepts Tableau or Power BI |

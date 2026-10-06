# Verified delivery status - release 0.4.0

Assessment: 6 October 2026. A hardened synthetic planning release; hosted production acceptance remains open.

- Twelve app workspaces and 73 local checks passed: real Gurobi/HiGHS solves, malformed inputs, missing capacity, empty plans, partial/corrupt release refusal, exclusive refresh, owner isolation, durable reviewed plans, joint price actions and all five analyst conclusions.
- The 8,000-customer, 1,221,317-trip pipeline rebuilt and reproduced from the committed source: raw hashes, customer predictions, core metrics and campaign allocation matched within 1e-9. Demand candidate rejection retains the seasonal serving baseline (MAE 10.48); contribution serves historical margin (MAE 55.30). Neither is a learned-model improvement.
- Fixed-origin monthly backtests have three held-out origins, MAE 9.91 and 92.5% marginal 90% interval coverage. Hour/direction values disaggregate daily forecasts; independent hourly accuracy remains unverified.
- Joint price/campaign capacity solves, separate signed days31-90 value/retention effects, richer explicit-grain customer marts, a fresh policy trial and exploratory subgroup reports are exported.
- Nine local registry scoring roundtrips matched. Reviewed lifecycle tooling retains previous versions and reasons; no hosted model is auto-approved.
- Six cloud workflows compile and all stage/inference contracts run locally. Failed quality gates remain closed. Docker/ECR and actual AWS jobs have not executed; no resources/charges created.
- Databricks full-feature/mart notebook is authored. Hosted execution remains pending; the Free Edition automated-console restriction was respected.
- Native BI: eight pages, 16 tables, 32 measures, five relationships and 66 schema validations passed. Latest Desktop reload is blocked by the helper rejecting input to its owned WebView dialog. Previous native refresh/visual receipts do not certify this revision.
- Declared runtime dependency audit found no known vulnerabilities; CloudFormation passed cfn-lint. Container execution, OIDC provider roundtrip, hosted CI, staging load/backup tests and publication remain pending.

Use outputs/readiness.json and docs/production_runbook.md before deploying. No live AWS/Databricks, service SLA or observed customer-impact claim is made.

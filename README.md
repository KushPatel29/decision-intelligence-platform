# Corridor - Decision intelligence

Release **0.4.0**. Twelve interactive workspaces connect customer models, causal offer analysis, shared price/campaign optimization, reconciled rewards, operational reviews and visual SQL cases. The synthetic dataset contains 8,000 customers, 1,221,317 trips and 405,632 digital events with three genuine public context sources. No affiliation with 407 ETR; customers, rates, zones and policies are invented.

## Open the delivered app

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-runtime.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open http://127.0.0.1:8501. Precomputed results support all workspaces and real HiGHS scenarios without cloud access. Gurobi is optional and needs its own license. Reviewed plans persist under runtime/decisions.sqlite. Local mode is for your computer; public hosting requires OIDC and an explicit identity allowlist.

## Rebuild and verify

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[dev,app,tracking,advanced]'
.\.venv\Scripts\python.exe -m decision_platform.cli demo --customers 8000 --solver highs
.\.venv\Scripts\python.exe scripts/register_models.py
.\.venv\Scripts\python.exe scripts/readiness.py
.\.venv\Scripts\python.exe -m pytest -q
```

Serving pauses during refresh and rejects partial/failed releases. Public downloads are cached with provenance. Outcome/latent fields never enter the predictor allowlist. Use the complete 8,000-customer trial for its planned power; smaller demos are not equivalent experiment evidence.

## Decision evidence

- Validation selection and held-out acceptance reject unsuitable demand candidates. Historical-margin contribution and seasonal demand currently outperform learned alternatives. Monthly backtests and interval coverage are reported separately from next-day metrics.
- Promotions/rewards share budget, contacts, eligibility, inventory, ROI, points and capacity. Signed discounted margin on days 31-90 enters the objective; retention is a separate KPI. Optimality covers the 600-customer shortlist.
- Discrete prices share capacity with incentives in a real joint solve. Constant elasticity and separable offer effects are explicit assumptions.
- A powered four-arm trial, S/T/X comparisons, fresh constrained-policy experiment, subgroup uncertainty, BG/NBD/Gamma-Gamma benchmark and predictive SHAP are synthetic evidence.
- Customer 360 resolves balances, tiers, dated consent/state, risks and engagement. Offer-specific scores and monthly histories preserve their own grains.
- Operations centre exposes integrity, acceptance, prediction/volume/campaign reviews and deployment readiness. Saved plans retain release identity and owner-isolated audit records.

## Deployment boundaries

Nine families have registered local scoring adapters. Six SageMaker workflows and a matching custom container are provided; all local stage contracts ran, while rejected model gates remain closed. No AWS job or hosted Databricks run is claimed. The Databricks notebook recomputes Spark features and imports upstream scored marts; it does not claim hosted model training.

Native Power BI contains eight pages, 16 tables and 32 measures. Source schemas pass; latest Desktop refresh remains pending at its reload dialog. The executive brief is under output/pdf/. Runtime dependency and infrastructure checks do not replace staging/hosted acceptance.

See [verified status](PROJECT_STATUS.md), [production runbook](docs/production_runbook.md), [test plan](docs/test_plan.md), [remaining boundaries](docs/release_0_4_gaps.md) and outputs/readiness.json. Hosted access, spending cap, repository destination, container/identity tests, backup/load tests and cloud receipts remain open.

scripts/package_release.py bundles source and precomputed results without credentials, audit records, raw/oracle data or model binaries. Rebind BI paths with scripts/rebind_powerbi.py after moving it.

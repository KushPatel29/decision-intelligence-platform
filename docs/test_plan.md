# Release verification strategy

Business-critical acceptance covers finite input/schema validation, customer and
capacity coverage, scarce-budget/points/inventory constraints, empty allocations,
price/campaign shared load, baseline-aware quality gates and cutoff leakage.

Runtime acceptance covers concurrent refresh refusal, failed refresh recovery,
corrupted/missing artifact refusal, owner-isolated persistent plans and denied
production access. App checks exercise every workspace and real free/commercial
solver flows. Cloud tests exercise all six local prepare/train/evaluate/inference
contracts, including rejected candidate gates. CI generates its dataset rather
than skipping every integration check on a clean checkout.

Hosted acceptance separately requires an executed container build, OIDC provider
roundtrip, immutable ECR image, AWS and Databricks execution, Power BI refresh,
secret/dependency scans, backup restore and a staging load test. Offline source
validation is not substituted for these receipts.

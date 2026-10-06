# Roadmap

| Next | Why | Acceptance |
|---|---|---|
| Hosted Databricks run, then a schedule | The job is built and locally exercised; a hosted receipt proves the platform side | `run_receipts` row with status `passed`; idempotent on a second run |
| Learner selection with cross-fitted losses | The one-SE rule keeps the S-learner alone while the X-learner ranks better on the truth; more folds would tighten the paired standard errors the rule depends on | Same observable rule, smaller standard errors, no truth in the rule |
| Recalibrate value levels on a larger validation fold | Estimates are conservative by about $4.49 per customer-offer | BLP calibration lowers bias on most offers before it is applied |
| Customer-specific elasticity | Prices are optimised per zone × period cell | Heterogeneous elasticities with interval coverage checked against the simulator |
| SageMaker execution | The pipeline is defined and its stages run locally | Processing, training, evaluation and batch transform logs from AWS |
| Streaming feed monitoring | Feed checks run daily in batch | Late and duplicate batches flagged within an hour of landing |

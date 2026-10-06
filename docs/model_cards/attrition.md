# Attrition model card

Purpose: support travel/retention planning. Target: Future 90-day trips <50% of prior 90-day trips, among historically active customers.

Training population: synthetic customer-month snapshots July 2024–January 2025. Validation/calibration: April 2025. Held-out test: July 2025. Label overlap is purged. The same customer may recur across time.

Features: the version 1.0 allowlist in `feature_catalog.md`; no targets, future events or latent simulator parameters. Algorithm selected by validation Brier score: hist_gradient_boosting. Separate validation-fold logistic calibration is used before test/current scoring.

Measured synthetic held-out metrics:

```json
{
  "roc_auc": 0.7354304012887678,
  "pr_auc": 0.4974147092207627,
  "brier": 0.14885409574591255,
  "ece_10bins": 0.0690277946276975,
  "lift_at_10": 2.6732781637574643,
  "lift_at_20": 2.172619047619048,
  "n": 6225,
  "prevalence": 0.21590361445783132,
  "training_seconds": 0.33673380000982434
}
```

Deployment: local batch scoring and saved joblib artifacts with local MLflow run lineage. SageMaker execution is pending. Churn/attrition scores are blank outside their historically active population.

Limitations and bias: designed synthetic behaviour; no real-world performance or fairness validation. Static account flags and overlapping customer identities limit population generalization. No protected attributes are used, but geographic and behavioural proxies would require review in a real system.

Monitoring: feature PSI/KS review, delayed-label discrimination and calibration once labels mature. Retraining trigger: validated decline relative to the champion plus confirmed data quality; PSI alone does not automatically retrain or approve a model.

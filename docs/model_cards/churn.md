# Churn model card

Purpose: support travel/retention planning. Target: No trips in following 90 days, among customers with >=3 trips in prior 90 days.

Training population: synthetic customer-month snapshots July 2024–January 2025. Validation/calibration: April 2025. Held-out test: July 2025. Label overlap is purged. The same customer may recur across time.

Features: the version 1.0 allowlist in `feature_catalog.md`; no targets, future events or latent simulator parameters. Algorithm selected by validation Brier score: hist_gradient_boosting. Separate validation-fold logistic calibration is used before test/current scoring.

Measured synthetic held-out metrics:

```json
{
  "roc_auc": 0.8889434137437986,
  "pr_auc": 0.5100483891251119,
  "brier": 0.03939870825094962,
  "ece_10bins": 0.005883928432492383,
  "lift_at_10": 5.97209931923916,
  "lift_at_20": 3.841961852861035,
  "n": 6225,
  "prevalence": 0.05895582329317269,
  "training_seconds": 0.27290320000611246
}
```

Deployment: local batch scoring and saved joblib artifacts with local MLflow run lineage. SageMaker execution is pending. Churn/attrition scores are blank outside their historically active population.

Limitations and bias: designed synthetic behaviour; no real-world performance or fairness validation. Static account flags and overlapping customer identities limit population generalization. No protected attributes are used, but geographic and behavioural proxies would require review in a real system.

Monitoring: feature PSI/KS review, delayed-label discrimination and calibration once labels mature. Retraining trigger: validated decline relative to the champion plus confirmed data quality; PSI alone does not automatically retrain or approve a model.

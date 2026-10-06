# Propensity model card

Purpose: support travel/retention planning. Target: At least one trip in following 30 days.

Training population: synthetic customer-month snapshots July 2024–January 2025. Validation/calibration: April 2025. Held-out test: July 2025. Label overlap is purged. The same customer may recur across time.

Features: the version 1.0 allowlist in `feature_catalog.md`; no targets, future events or latent simulator parameters. Algorithm selected by validation Brier score: hist_gradient_boosting. Separate validation-fold logistic calibration is used before test/current scoring.

Measured synthetic held-out metrics:

```json
{
  "roc_auc": 0.8954822159735583,
  "pr_auc": 0.9608390935311797,
  "brier": 0.12352118932002347,
  "ece_10bins": 0.06086417624549931,
  "lift_at_10": 1.3699570815450643,
  "lift_at_20": 1.3682403433476393,
  "n": 8000,
  "prevalence": 0.728125,
  "training_seconds": 0.4771917999605648
}
```

Deployment: local batch scoring and saved joblib artifacts with local MLflow run lineage. SageMaker execution is pending. Churn/attrition scores are blank outside their historically active population.

Limitations and bias: designed synthetic behaviour; no real-world performance or fairness validation. Static account flags and overlapping customer identities limit population generalization. No protected attributes are used, but geographic and behavioural proxies would require review in a real system.

Monitoring: feature PSI/KS review, delayed-label discrimination and calibration once labels mature. Retraining trigger: validated decline relative to the champion plus confirmed data quality; PSI alone does not automatically retrain or approve a model.

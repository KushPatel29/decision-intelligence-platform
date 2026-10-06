# Anomaly model card

Purpose: Customer behavioural review.

Evidence from actual local run:

```json
{
  "flagged": 1185,
  "method": "Isolation Forest, historical January baseline; anomaly is a review signal, not fraud adjudication"
}
```

Limitations: Unsupervised historical baseline. No labelled fraud evaluation; flags never automatically disqualify customers.

Training/inference: local synthetic data, explicit feature cutoffs and model-specific folds. Artifacts are local; hosted deployment is pending. Monitor input distributions, realized outcomes when available, and business validity before promotion. Retrain only after data QA and a validated evaluation against the existing candidate. Synthetic data cannot establish real-world bias or fairness.

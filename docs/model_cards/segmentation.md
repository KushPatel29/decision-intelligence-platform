# Segmentation model card

Purpose: Behavioural customer clustering.

Evidence from actual local run:

```json
{
  "silhouette": 0.23056718250806182,
  "davies_bouldin": 1.1912069934920193,
  "clusters": 5,
  "fit_as_of": "2025-01-01 00:00:00",
  "bootstrap_adjusted_rand": [
    0.9016263396653201,
    0.9594507213944911,
    0.772770740064575
  ]
}
```

Limitations: Fitted on the January 2025 training snapshot, with three bootstrap adjusted-Rand comparisons. Bootstrap stability does not establish temporal stability or business actionability.

Training/inference: local synthetic data, explicit feature cutoffs and model-specific folds. Artifacts are local; hosted deployment is pending. Monitor input distributions, realized outcomes when available, and business validity before promotion. Retrain only after data QA and a validated evaluation against the existing candidate. Synthetic data cannot establish real-world bias or fairness.

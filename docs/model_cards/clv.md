# Clv model card

Purpose: Future contribution and projected customer value.

Evidence from actual local run:

```json
{
  "test": {
    "mae": 55.29541624141774,
    "rmse": 108.51483310131638,
    "n": 8000,
    "baseline_mae": 55.29541624141774
  },
  "selection": {
    "selected": "historical_margin",
    "validation_mae": {
      "hist_gradient_boosting": 51.72060334581555,
      "historical_margin": 51.32197845492776
    },
    "selection_split": "April\u2013June 2025 validation; test untouched"
  },
  "champion": "historical_margin",
  "method": "Validation-selected 90-day contribution forecast projected four quarters with churn-based survival decay; 10% annual discount. Heuristic projected value; not validated 12-month CLV."
}
```

Limitations: Historical-margin and learned forecasts compete only on validation. The retained baseline matches the held-out reference. Quarterly survival decay is heuristic. BG/NBD plus constrained Gamma-Gamma is evaluated on 90-day purchase-days, not 12-month value. Frequency/monetary correlation challenges its independence assumption.

Training/inference: local synthetic data, explicit feature cutoffs and model-specific folds. Artifacts are local; hosted deployment is pending. Monitor input distributions, realized outcomes when available, and business validity before promotion. Retrain only after data QA and a validated evaluation against the existing candidate. Synthetic data cannot establish real-world bias or fairness.

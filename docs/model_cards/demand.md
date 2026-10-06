# Demand model card

Purpose: Daily zone-period trip demand.

Evidence from actual local run:

```json
{
  "test": {
    "mae": 10.477657004830919,
    "rmse": 18.38925923120515,
    "n": 1656,
    "seasonal_naive_mae": 10.477657004830919
  },
  "selection": {
    "selected": "hist_gradient_boosting",
    "validation_mae": {
      "hist_gradient_boosting": 12.526588742918575,
      "seasonal_naive": 14.52991452991453
    },
    "selection_split": "April\u2013June 2025 validation; test untouched",
    "promotion_gate": "Rejected candidate: held-out error exceeds predeclared baseline. Seasonal baseline remains the serving champion.",
    "candidate_test": {
      "mae": 19.389273204332696,
      "rmse": 31.40666293452014,
      "n": 1656
    }
  },
  "champion": "seasonal_naive",
  "horizon_validation": {
    "horizon_days": 30,
    "method": "Same weekday mean from previous 28 days, frozen at each origin",
    "test_origins": 3,
    "test_mae": 9.905864197530864,
    "validation_interval_radius": 32.25,
    "test_interval_coverage": 0.9246913580246914,
    "nominal_coverage": 0.9,
    "n_test": 1620,
    "limitations": "Marginal validation-residual intervals; dependent cells and overlapping origins, no simultaneous or hourly coverage guarantee"
  },
  "decision_forecast": "30-day seasonal planning forecast; independent rolling-origin monthly backtests and validation-derived intervals provided. Weather forecast uncertainty remains outside scope.",
  "reserve_fraction": 0.2
}
```

Limitations: Validation-selected learned candidate failed the untouched promotion gate; the seasonal baseline remains the serving model. Six fixed-origin 30-day backtests report marginal interval coverage from validation residuals. Origins overlap and cells are dependent. Hour/direction values disaggregate daily forecasts and have no independent hourly validation.

Training/inference: local synthetic data, explicit feature cutoffs and model-specific folds. Artifacts are local; hosted deployment is pending. Monitor input distributions, realized outcomes when available, and business validity before promotion. Retrain only after data QA and a validated evaluation against the existing candidate. Synthetic data cannot establish real-world bias or fairness.

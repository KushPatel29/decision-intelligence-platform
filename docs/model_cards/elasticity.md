# Elasticity model card

Purpose: Demand response to price.

Evidence from actual local run:

```json
[
  {
    "zone_id": 0,
    "period": "Off-peak",
    "elasticity": -0.600598945558989,
    "mae": 5.431209176736777,
    "rmse": 6.874921948986891,
    "n": 92
  },
  {
    "zone_id": 0,
    "period": "Peak",
    "elasticity": -0.5505539339573534,
    "mae": 5.692017823456089,
    "rmse": 6.959928380008463,
    "n": 92
  },
  {
    "zone_id": 0,
    "period": "Weekend",
    "elasticity": -1.0835939136946509,
    "mae": 5.468429994148987,
    "rmse": 7.287411384130465,
    "n": 92
  },
  {
    "zone_id": 1,
    "period": "Off-peak",
    "elasticity": -0.6691905309814168,
    "mae": 6.558029997605167,
    "rmse": 8.041557927174768,
    "n": 92
  },
  {
    "zone_id": 1,
    "period": "Peak",
    "elasticity": -0.733967974471681,
    "mae": 7.286510119389952,
    "rmse": 9.0907141257632,
    "n": 92
  },
  {
    "zone_id": 1,
    "period": "Weekend",
    "elasticity": -1.0983204871529326,
    "mae": 6.673725861174657,
    "rmse": 8.040562158247461,
    "n": 92
  },
  {
    "zone_id": 2,
    "period": "Off-peak",
    "elasticity": -0.8426667245275142,
    "mae": 6.05665482052048,
    "rmse": 7.857533580039288,
    "n": 92
  },
  {
    "zone_id": 2,
    "period": "Peak",
    "elasticity": -0.8770211251731675,
    "mae": 8.412653328342723,
    "rmse": 10.339781989285134,
    "n": 92
  },
  {
    "zone_id": 2,
    "period": "Weekend",
    "elasticity": -1.211523462155748,
    "mae": 6.00868902831098,
    "rmse": 7.567922808011486,
    "n": 92
  },
  {
    "zone_id": 3,
    "period": "Off-peak",
    "elasticity": -0.9871299450717428,
    "mae": 6.718944501764433,
    "rmse": 8.371295144768853,
    "n": 92
  },
  {
    "zone_id": 3,
    "period": "Peak",
    "elasticity": -1.0035387167315,
    "mae": 7.793777902626052,
    "rmse": 10.200326988083685,
    "n": 92
  },
  {
    "zone_id": 3,
    "period": "Weekend",
    "elasticity": -1.435497522388456,
    "mae": 6.0276278771518,
    "rmse": 7.468581863765502,
    "n": 92
  },
  {
    "zone_id": 4,
    "period": "Off-peak",
    "elasticity": -1.1404322052553075,
    "mae": 6.185349183175776,
    "rmse": 8.22671625382578,
    "n": 92
  },
  {
    "zone_id": 4,
    "period": "Peak",
    "elasticity": -1.1119561959988082,
    "mae": 8.256245680699877,
    "rmse": 10.706156707235507,
    "n": 92
  },
  {
    "zone_id": 4,
    "period": "Weekend",
    "elasticity": -1.4843605071495587,
    "mae": 7.41558439680485,
    "rmse": 9.698407209261898,
    "n": 92
  },
  {
    "zone_id": 5,
    "period": "Off-peak",
    "elasticity": -1.226233742990725,
    "mae": 7.91088369133962,
    "rmse": 10.2716606173995,
    "n": 92
  },
  {
    "zone_id": 5,
    "period": "Peak",
    "elasticity": -1.2413883679769415,
    "mae": 7.485975873777113,
    "rmse": 10.108746182660662,
    "n": 92
  },
  {
    "zone_id": 5,
    "period": "Weekend",
    "elasticity": -1.6855863077482425,
    "mae": 7.55367423951339,
    "rmse": 9.664961168454049,
    "n": 92
  }
]
```

Limitations: Log-log OLS using independent randomized synthetic prices; coefficients are not observational estimates of actual company demand.

Training/inference: local synthetic data, explicit feature cutoffs and model-specific folds. Artifacts are local; hosted deployment is pending. Monitor input distributions, realized outcomes when available, and business validity before promotion. Retrain only after data QA and a validated evaluation against the existing candidate. Synthetic data cannot establish real-world bias or fairness.

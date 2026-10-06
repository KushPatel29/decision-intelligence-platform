# Public-source provenance

| Dataset | Provider | Use | Attribution/reference |
|---|---|---|---|
| Toronto daily weather, 2024–2025 | Open-Meteo | Synthetic trip generation, lagged demand context | [Historical API](https://open-meteo.com/en/docs/historical-weather-api); weather reanalysis, not a Toronto station feed |
| Canadian holiday calendar filtered to Ontario | Nager.Date | Calendar context | [Official source project](https://github.com/nager/Nager.Date); global or CA-ON entries only |
| Daily FXCADUSD, 2024–2025 | Bank of Canada | Macro-source ingestion and lagged demand feature | [Valet API](https://www.bankofcanada.ca/valet/docs/); not fuel prices and not a claimed causal mechanism |

Downloaded response files and adjacent provenance files contain the exact request URL, UTC retrieval timestamp and SHA-256. `daily_context.parquet` joins dates with holiday labels and backward-as-of exchange rates. Initial exchange-rate gaps remain missing rather than being filled with future observations. Weather missingness fails validation.

Source terms and attributions must be reviewed again before public redistribution; this build caches the responses locally. All customer, trip, rate, digital, pricing intervention and loyalty tables are generated from a seeded simulation. No actual 407 ETR facts from the pasted plan are needed for the local system.

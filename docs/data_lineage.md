# Data lineage

```
Open-Meteo weather  ─┐
Nager.Date holidays ├── cached JSON + provenance ── daily_context
Bank of Canada FX   ┘                 │
                                     ▼
Seeded generator ── customers / trips / digital / pricing / points
                                     │
                      Bronze Parquet snapshots → Silver Parquet + DuckDB
                                     │
                    SQL cutoff features      Forward-window labels
                          │                         │
                          └──── purged temporal training/evaluation ─── models
                                     │
July synthetic randomized trial ── held-out customer causal learners
                                     │
October features + saved models ── scoring + pricing/demand scenario
                                     │
                                 Gurobi decisions
                                     │
                    Streamlit + standalone HTML + Power BI CSVs
```

Simulator hidden parameters and potential effects are saved in `data/simulation_audit` for auditing. They are separated from analytical feature inputs. Unit tests guard the feature allowlist and cutoff boundary. Local analytical database tables have silver/gold schemas; hosted Delta tables are a separate pending run.

No lineage claim is made for AWS or Databricks execution until actual run identifiers and reconciliations are captured.

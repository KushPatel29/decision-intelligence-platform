# Data lineage

```
Open-Meteo weather  ─┐
Nager.Date holidays  ├── cached JSON + provenance hash ── daily_context
Bank of Canada FX   ─┘                 │
                                       ▼
Seeded simulator ── accounts, consent history, trips, digital events, prices, points
       │                               │
       │ (truth: data/simulation_audit, never a model input)
       │                               ▼
       │            Bronze Parquet (as delivered, planted defects)
       │                               │  natural-key de-duplication, contract checks
       │                               ▼
       │            Silver Parquet + quarantine table ──► DuckDB
       │                               │
       │            sql/customer_features.sql (as-of cutoff)   forward-window labels
       │                               │                              │
       │                               └── purged chronological folds ─┴──► customer models
       │                                                                      │
       │            July 10-arm randomised trial ──► causal learners (S, T, X, DR → one-SE ensemble)
       │                                                                      │
       │            elasticity + 30-day demand forecast ──────────────────────┤
       │                                                                      ▼
       │                              full-population MIP (HiGHS LP, Gurobi core and check)
       │                                                                      │
       └────────────► truth-scored evaluation + October policy trial ◄────────┤
                                                                              ▼
                                   serving snapshot (SHA-256 manifest), release gate
                                        │            │             │
                              Streamlit app   decision API   powerbi/data → generated PBIP
```

On Databricks (`databricks/`), the same pipeline runs in the job's first task and its layers land in a Unity
Catalog volume, then as Delta tables: `bronze_*`, `silver_*` (with CHECK constraints and the quarantine
table), `gold_*`, `gold_customer_features_spark` (recomputed in PySpark, required to equal the DuckDB
features to 1e-7), `serving_*`, and `run_receipts`, one row per run with its run id, table counts, parity result,
model versions and reconciliation checks. Registered models live in Unity Catalog as `corridor_<model>` with alias `candidate`.

Simulator hidden parameters and true effects are saved in `data/simulation_audit` for evaluation only. Tests
guard the feature allowlist (no `latent_` or `true_` column), the as-of cutoff and the serving snapshot.

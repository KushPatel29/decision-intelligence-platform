# Databricks job

The whole decision pipeline as a four-task Databricks job on serverless compute, with Delta tables, Unity
Catalog governance, workspace MLflow and the Gurobi-certified campaign MIP.

```
pipeline ──► lakehouse ──► publish
    └──────► registry  ──┘
```

| Task | Notebook | What it does | Fails when |
|---|---|---|---|
| `pipeline` | `notebooks/01_pipeline.py` | Runs the full pipeline (simulator → features → models → 10-arm trial → causal learners → full-population MIP with a Gurobi core and check → pricing → marts → release gate). Model runs are tracked in the workspace's MLflow. Copies the layers and outputs to the UC volume `runs/<run_id>` | The release gate fails: a failed run is never handed to the publish tasks |
| `lakehouse` | `notebooks/02_lakehouse.py` | Lands bronze, silver and gold as Delta tables; puts the silver trip contract into the table as CHECK constraints; recomputes all 39 customer features in **PySpark** from the silver Delta tables into a table with an informational primary key; `OPTIMIZE … ZORDER BY customer_id` | Any PySpark feature differs from the DuckDB feature the models used by 1e-7 or more, or silver has a duplicate `trip_id` |
| `registry` | `notebooks/03_registry.py` | Registers the propensity, churn and attrition classifiers and the causal uplift ensemble in **Unity Catalog** as MLflow pyfunc models with signature, input example and pinned requirements; alias `candidate`, tagged `pending-review` | A version loaded back from the registry does not score a sample exactly as the pipeline did |
| `publish` | `notebooks/04_publish.py` | Publishes the serving snapshot as Delta tables; reconciles the published plan against the optimizer's certificate; appends a row to `run_receipts` | The plan is not one offer per customer, does not match the certificate, or breaks a limit |

## Run it

With the Databricks CLI (the job is defined in `databricks.yml` at the repository root):

```bash
databricks bundle deploy
databricks bundle run corridor
```

Without the CLI, through the Python SDK, with browser sign-in and no token stored:

```bash
python -m decision_platform.cli fetch
python databricks/run_job.py --host https://<workspace>.cloud.databricks.com
```

`run_job.py` reads the job from `databricks.yml`, uploads `src/decision_platform`, `sql/`, the cached public
context and the notebooks to `/Workspace/Users/<you>/corridor`, creates or resets the job, runs it, prints
each task's state, and writes the publish task's receipt to `receipts/` (with the workspace user name
removed).

Parameters: `catalog` (default `workspace`), `schema` (`corridor`), `customers` (`25000`; budget, contacts
and points cap scale with it), `solver` (`auto`). At 3,000 customers (300 per trial arm) the release gate
fails on attrition AUC and held-out uplift Qini, and the job stops after the first task, by design.

## Before spending a hosted run

```bash
python databricks/local_run.py --customers 25000
```

Executes the four notebooks in order on this machine with real PySpark and a stand-in `dbutils`. What a
laptop cannot do is replaced by a check, not skipped: table writes become temp views; each `CHECK`
constraint counts the rows that would violate it and fails on any; the primary key is tested for
uniqueness; MLflow and the registry go to a local SQLite store, so registration, aliasing and the load-back
round trip really run.

## Status

| Check | Result |
|---|---|
| PySpark feature parity, 3,680,249 trips, 25,000 customers, 39 features | max difference 2.2e-11 (`scripts/benchmark_spark.py`) |
| Local run of all four notebooks, 25,000 customers | Passed ([`receipts/2026-10-07-local-run.json`](receipts/2026-10-07-local-run.json)): 63 Delta tables, 4 CHECK constraints held on every row, primary key unique, feature parity 2.2e-11, 4 models registered and scored identically after load-back, 8 of 8 plan reconciliation checks, Gurobi confirmed the optimum |
| **Hosted run on Databricks serverless, 25,000 customers** | **Passed** ([`receipts/2026-10-07-run-649786944044225.json`](receipts/2026-10-07-run-649786944044225.json)): all four tasks on their first attempt (pipeline 22 min, lakehouse 5, registry 2, publish 2); 63 Delta tables with the CHECK constraints and primary key; PySpark features equal DuckDB's exactly (max difference 0.0); four models in Unity Catalog with alias `candidate`, each loaded back and scored identically; 8 of 8 plan reconciliation checks; release gate passed |

## What the hosted runs found

The local harness cannot see three things a real workspace enforces, and the first hosted runs found all three:

1. **Nanosecond timestamps.** Serverless runs pandas 2, which writes Parquet timestamps in nanoseconds; Spark
   refuses to read them. Every Parquet write in the pipeline now stores microseconds (`config.PARQUET`), and a
   test pins it.
2. **Delta column names.** One serving table is a pivot whose columns are policy names such as
   "Optimized (MIP)"; Delta rejects spaces and brackets. The publish task snake-cases column names, and the
   local harness now applies Delta's rule so it would have failed the same way.
3. **The platform's own packages.** Serverless fixes numpy, pandas and pyarrow and refuses other versions.
   The job pins everything else to the locally tested versions (`job-packages.txt`, which Dependabot is configured to skip: changing a pin means re-running the
   hosted job, not merging a pull request); the manifest of
   each run records what it used.

## Hosted against local results

The simulated data is identical on both (same 3,680,249 trips, same revenue to the cent, same quarantine).
The plan is not:

| | Local (numpy 2.5, pandas 3.0) | Databricks (numpy 2.3, pandas 2.3) |
|---|---|---|
| Contacts | 5,000 | 4,237 |
| Expected value | $42,649 | $41,292 |
| True value | $64,774 | $55,888 |
| Share of the ceiling | 75% | 65% |
| Release gate | passed | passed |

Small numeric differences change the model fits (the propensity champion flips between XGBoost and gradient
boosting), and the plan follows the fits. A first hosted run without the scikit-learn and scipy pins reached
66%. The plan's quality is therefore a range across environments, not one number; every run still clears
the 60% gate, and the policy, not the run, is what a real operator would test (see the policy trial).

Gurobi on Databricks uses the same size-limited licence `pip install gurobipy` provides everywhere: it
solves or checks cores up to 2,000 variables and constraints, and the certificate records which solver did
what.

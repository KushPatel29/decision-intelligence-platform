# Run receipts

| Receipt | What it records |
|---|---|
| `2026-10-07-local-run.json` | All four notebooks run locally by `databricks/local_run.py` at 25,000 customers (not a hosted run) |
| `2026-10-07-run-778602458139872.json` | First hosted run to pass. Its publish task failed on Delta's column-name rule, was fixed and re-run with `run_job.py --repair` (3 attempts); scikit-learn and scipy were not yet pinned |
| `2026-10-07-run-649786944044225.json` | **Reference hosted run**: Databricks serverless, all four tasks passed on their first attempt, with the job's packages pinned to `databricks/job-packages.txt` |

The workspace user name is removed from each receipt before it is written.

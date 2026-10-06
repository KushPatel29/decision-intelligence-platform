# Corridor deployment and recovery

This release is a synthetic planning application. Local acceptance is not proof
of a production AWS/Databricks deployment, real customer impact or a service SLA.

## Required hosted acceptance

1. Agree the AWS spending cap and private access identities. Create the OIDC
   client with an exact HTTPS callback, configure `secrets.toml` outside source
   control, and set `CORRIDOR_ALLOWED_SUBJECTS` to the approved subject IDs.
2. Build the non-root app image, run dependency/container scanning, record its
   immutable image digest and test the production sign-in flow with an allowed
   and a denied identity. The compose service binds localhost; publish through
   an authenticated HTTPS gateway with WebSocket support.
3. Mount writable `runtime` storage; keep source and release artifacts read-only.
   Back up the decision audit database using SQLite's backup API. Do not copy a
   live WAL database as a single file. Scope backups to the same access rules.
4. Validate `artifact_manifest.json` and `quality_gate.json`. Production startup
   rejects unverified releases or failed model acceptance. Confirm all 12 app
   workspaces, empty results, campaign and price solves, and saved-plan isolation.
5. Execute SageMaker preparation, training, test acceptance, pending-approval
   registry and batch inference against the project container. Rejected candidates
   do not enter registry/batch. Capture execution IDs, billed cost and logs. Use
   dedicated project S3/IAM resources and a least-privilege execution role.
6. Run the Databricks notebook through supported workspace APIs or manually;
   reconcile point-in-time features, row counts and all gold mart grains. The
   current Free Edition browser automation restriction must be respected.
7. Refresh the current native Power BI release in Desktop and verify DAX totals.
   Configure the host's operational logs, uptime check and escalation ownership.

## Refresh, failure and rollback

The pipeline acquires an exclusive `.pipeline.lock` and records `run_status.json`.
The app pauses during a refresh and refuses a failed/partially replaced release.
Never clear a lock until its recorded process has stopped. After a crash, inspect
the receipt and process, remove only the stale lock, and rerun successfully or
restore the whole previous release. A lock file alone is not a job scheduler.

Deploy new artifacts into a separate release directory. Validate them before
switching the host's `CORRIDOR_ROOT` and restarting workers; preserve the previous
directory for rollback. Restoring only a CSV from another release will fail the
integrity check. Never update a live release to make a failed hash check disappear.

Rollback if integrity/model acceptance fails, a critical solve/export/sign-in
flow fails, or unexpected errors exceed 1% of requests for five minutes. Confirm
ownership before rolling back a model alias. Persist each approval and rollback
reason with the prior/new versions; do not auto-promote on drift alone.

## Boundaries and retention

Scenario saves are isolated by the hashed OIDC issuer/subject. This single-workspace
application has an allowlist, not a multi-tenant billing or authorization service.
Do not use the anonymous local owner mode on a public server. Limit deployment
to one instance until storage, session routing and load behaviour are validated.
Review audit retention at least monthly; default policy is 90 days, with an
approved export/backup before deletion. No automated deletion is performed.

Hourly forecasts disaggregate daily predictions; intervals are marginal and
do not establish simultaneous network coverage. Optimizer budgets use estimated
costs; enforce realized campaign spending and roadway limits in execution systems.
No contacts, charges or real customer campaigns are executed by the app.

Authentication follows [Streamlit's OIDC documentation](https://docs.streamlit.io/develop/concepts/connections/authentication).
The project model image follows [SageMaker's custom container contract](https://docs.aws.amazon.com/sagemaker/latest/dg/docker-containers.html).

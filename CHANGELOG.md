# Changelog

## 2026-10-07 release review

- Remove process-wide solver log redirection, which corrupted stdout during concurrent Linux solves.
- Preserve exact serving artifact bytes through Git checkout; prevent Windows line-ending conversion
  from breaking snapshot checksums on Linux hosting. CI now verifies the shipped snapshot.
- Verified serving reads now enforce manifest membership, safe paths and byte hashes at read time;
  required API artifacts and the release ID are checked before serving.
- Scenario solves retain capacity-relieving options in off-peak and weekend periods even when their
  standalone value is negative. Regression cases prove the better feasible joint plan is retained.
- Production API readiness refuses missing API-key configuration. Pricing Studio respects the
  configured MIP time limit, including the HiGHS and Gurobi paths.
- Runtime pins: FastAPI 0.142.2, Streamlit 1.65.0, uvicorn 0.54.0; GitHub Actions checkout,
  setup-python and upload-artifact v7. Dependabot now skips `databricks/` (the job's pins change only
  with a new hosted run and receipt) and holds pyspark to delta-spark's minor version and sagemaker
  to the v2 SDK the AWS pipeline is written against.
- Live demo at corridor-decision-intelligence.streamlit.app: all twelve pages render with no errors,
  and a scenario solve there reproduces the committed plan ($42,649, 5,000 contacts).
- Tables show thousands separators throughout ($42,649, not $42649); cent-level money uses Streamlit's
  dollar format, so negatives read -$1.48. The scenario comparison labels every column. (Streamlit's
  `step` truncates rather than rounds, so it is not used for display precision.)
- Validation: 241 tests passed, one optional test skipped; runtime dependency audit found no known
  vulnerabilities; lint and formatting passed. Public deployment uses isolated demo-session owners.

## 1.1.0

**Rush hour and congestion relief.** A ninth offer, 25% off rush-hour trips, and a planning value per net rush-hour
trip moved onto the 407 in the objective; capacity rows still decide where it can be used. The trial grows to ten arms.

**Causal learner selection.** Learners are chosen once, on doubly robust validation loss pooled across offers, and
every learner within one standard error of the best is averaged. A rebuilt registry scorer reproduces the plan's
effects from the stored model to 1e-16.

**Release gate.** Blocking checks are the ones production could compute; the simulation checks (share of the
ceiling, elasticity coverage) are reported beside them.

**Power BI.** A Command centre page, a KPI strip on every page (each KPI with a status pill and a micro-visual against
its limit, target, history or parts) and eight more panels drawn as HTML and CSS by DAX measures in the HTML Content
visual: hero KPIs, offer cards, guardrails with shadow prices, a policy leaderboard, an experiment forest plot with
Bonferroni intervals, a zone-by-period capacity heat grid, a segment table and a release scorecard. Every one of 135
measures is executed against Power BI's engine by `scripts/validate_powerbi_model.ps1`, which also found that an
apostrophe in a measure name had stopped Desktop opening the model; the generator now escapes it. Offers share one
colour map with the app, and the two loyalty rewards share a slot with a texture instead of a ninth, unvalidated hue.

**Databricks.** A four-task serverless job (`databricks.yml`, `databricks/`): the pipeline with a Gurobi core and
workspace MLflow; a Delta medallion with CHECK constraints and a PySpark feature-parity gate; Unity Catalog model
registration with a load-back scoring test; a reconciled publish with a run receipt. `databricks/run_job.py` deploys
it through the SDK with browser sign-in, and `databricks/local_run.py` runs all four notebooks locally first.

**Fixes.** The resent bronze batch is capped at the day's trips (a 3,000-customer run crashed); a learner that
cannot split no longer writes NaN rank correlations; consent history wrote nanosecond timestamps, which Spark cannot
read; the elasticity scorer looked up cells without their segment; the experiments page described the old per-offer
learner rule and crashed on a mixed-type column; offer charts indexed an eight-colour palette with nine offers; the
feature catalog covered 24 of 39 features and overwrote the model cards. Importing the feature list no longer loads
DuckDB, so a registered model's serving environment does not need it.

**Hosted Databricks run.** The job ran on Databricks serverless and passed every check (receipt in
`databricks/receipts/`). It found three issues the local stand-in could not: nanosecond Parquet timestamps from
pandas 2 (all layers now written in microseconds), Delta's column-name rule (publish snake-cases names; the
harness enforces the rule), and platform-fixed numpy, pandas and pyarrow (the rest pinned in
`databricks/job-packages.txt`). On identical data its plan reaches 65% of the ceiling against 75% locally.
`run_job.py` can re-attach to a run (`--attach`) and re-run only failed tasks (`--repair`).

**Production hardening.** Decision API: bounded solve time and concurrency, 503 before startup, request IDs and
JSON access logs. App: shared solver slots. Dependabot, pre-commit hooks, a smaller Docker context. HTML/CSS
KPI strips on every Power BI page.

**Documentation.** Role coverage, an A/B testing playbook, a data platform plan for IT, a project plan with RACI,
rewritten README and limitations, four new decision records.

## 1.0.0

A rebuild of the decision science, the optimizer, the app and the Power BI layer.

**Data and simulation.** 25,000 customers, about 3.7 million trips and 1.4 million digital events. A ground-truth
simulator owns hidden traits and every offer's true effect; trips carry entry and exit zones; an 11-event app/web/email
funnel; segment-level price tests; accounts no longer travel before they were created. Bronze keeps the raw feed with
four planted defects (late batch, duplicate batch, unit error, impossible charges) and silver quarantines them; 30
planted account anomalies test the detector.

**Experiments.** Nine-arm trial (control plus eight offers including a spend-threshold credit, a free trip, an off-peak
pass and two point rewards) with blocked randomisation, covariate-balance reporting, CUPED, simulation-calibrated
O'Brien-Fleming sequential boundaries and Benjamini-Hochberg subgroup control.

**Causal targeting.** Learners estimate incremental trips by travel period; offer terms turn trips into money. S, T, X
and doubly robust learners compete per offer by doubly robust validation loss; bootstrap uncertainty per estimate; BLP
heterogeneity test reported (calibration tested and rejected).

**Optimization.** Exact MIP over every eligible customer-offer pair with signed zone/period capacity: HiGHS LP,
rounding, reduced-cost fixing and an exact core, with Gurobi confirming optimality inside its size-limited licence. LP
shadow prices, a budget frontier, a risk-averse (lower-confidence-bound) plan and an LP-guided joint price and campaign
optimizer.

**Evaluation.** Every targeting approach scored against the simulator's truth, against the ceiling a perfectly informed
planner reaches; winner's-curse and value-calibration reporting; an independent October policy test.

**Models.** XGBoost joins the classifier bake-off; Gaussian-mixture segments beside K-Means; empirical-Bayes
elasticities with intervals checked against true elasticities; a 30-day fixed-origin demand forecaster with
split-conformal intervals; calendar- and weather-aware feed-quality monitoring.

**Product.** Streamlit app rebuilt as twelve URL-routed pages in four groups with a validated colour-blind-safe palette,
a next-best-offer lookup, scenario studio with risk aversion and live shadow prices, and a policy-value page. New FastAPI
decision service with API keys, health/readiness probes and a bounded scenario solver. Both serve only a hash-verified
snapshot.

**Power BI.** Generated eight-page PBIP (SVG KPI tiles, page headers, navigation, filter panels) over 23 compact tables,
with a byte-for-byte drift gate in CI.

**Engineering.** Codebase reformatted and linted; 70+ new tests including brute-force optimality checks; CI with lint,
hermetic unit/API tests, Power BI drift, dependency audit, a full integration run and a container build.

## 0.4.0

Added operations and analyst workspaces, durable reviewed plans and owner audit, exclusive refresh locking, atomic outputs, release hashes and production OIDC allowlisting. Added strict optimization input validation and bounded solve concurrency, shared discrete price/campaign optimization, signed days31-90 margin and retention reporting, a fresh policy trial and multiplicity-adjusted subgroups. Validation/acceptance now retain stronger contribution/demand baselines; fixed-origin monthly backtests and hourly directional disaggregation are explicit. Added Customer 360/business marts and dated state/consent, batch score/volume/campaign reviews, nine registry scorers with review lifecycle, six gated cloud workflows/custom container, full Databricks feature/mart notebook, richer native BI, containers, CI and production runbook. Local runtime vulnerability and infrastructure checks passed. Hosted execution, Docker/identity/restore/load acceptance, GitHub publication and revised native Desktop refresh remain open.

## 0.3.0

Redesigned the Streamlit product around a six-zone campaign display and integrated outcome rail. Capacity rings use weighted utilization, and each zone shows headroom after the demand reserve. Overview, Scenario studio and Decision evidence separate review, planning and verification. Added editable Balanced, Lean budget, More capacity reserve and No reward points templates; real scenario solves show differences from the saved baseline, offer mix, resource use and downloadable decision summaries. Refined navigation, chart interactions, pricing comparisons, customer risk displays and transportation capacity views. Narrow screens retain native accessible controls and a horizontally scrollable corridor. Prior model, data, native Power BI and cloud-preparation evidence remains valid; hosted execution is still pending.

## 0.2.0

Dark transportation control-room design; ten Streamlit workspaces; corridor schematic, interactive charts, calibration and model explanations. Joint promotion/reward optimization and scenario comparisons with points/reserve controls. Dataset increased to 8,000 customers and 1.22m trips. Powered four-arm experiment, dedicated loyalty effects, T/S/X comparisons, held-out offer-rule evaluation, feasible targeting baselines and budget sensitivity. Probabilistic value benchmark and reward accounting; canonical schema expansion; local MLflow registry candidates. Complete Spark feature kernel, portable Databricks medallion notebook, native eight-page Power BI project, compiled gated SageMaker pipeline, executive PDF and release documentation. Hosted execution remains pending account setup. Native refresh and all eight page reviews passed.

## 0.1.0

Initial local Python/SQL pipeline, customer models, synthetic experiment, sequential allocation, Streamlit app and cloud preparation.

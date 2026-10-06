# Changelog

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

# Evidence and limitations

What the evidence in this repository does and does not establish. Figures are from the committed
25,000-customer run.

## Data

- Customers, prices, capacities, loyalty rules and every treatment effect are synthetic. The weather,
  statutory holidays and CAD/USD context are real public data, cached with provenance. Nothing here is a
  claim about a real operator's customers, performance or systems.
- The simulator was written to be realistic in structure (heterogeneous responses, discounts paid on
  baseline trips, carry-over, capacity), not calibrated to real elasticities or response rates. A method that
  works here has passed a necessary test, not a sufficient one.
- Capacity is a zone × period planning cell with a 20% reserve, not routing over real road segments.

## Experiment and causal estimates

- The ten-arm trial is powered for its planned primary endpoint (1,794 per arm required, 2,500 run).
  Subgroup results are exploratory and FDR-controlled; they are hypotheses, not targeting rules.
- The production causal ensemble is chosen by an observable rule (pooled doubly robust validation loss,
  one standard error). In this run it chose the S-learner alone; on the simulator's truth the X-learner
  ranks customers better (mean Spearman 0.29 vs 0.11). The rule is kept because a rule tuned on the truth
  would not exist in production; the gap is reported on the Experiments page.
- The learners under-state value in level (mean bias −$4.49 per customer-offer). A BLP recalibration is
  computed as a diagnostic and not applied.
- Carry-over into days 31-90 uses the conservative 20th percentile of its bootstrap distribution. Retention
  value is reported separately and is not added to the objective, to avoid counting it twice.
- The policy trial (+$1.40 per customer, 95% CI $0.23 to $2.57) is one randomised test of one plan.

## Optimisation

- The MIP is solved over every eligible customer-offer pair, and its certificate states the gap to the LP
  bound (1.5e-7 here). Gurobi's size-limited licence covers cores up to 2,000 variables and constraints:
  here HiGHS solved the 4,402-variable core and Gurobi independently re-solved the 445-variable residual
  after a second round of fixing. At smaller populations the residual can exceed the licence, and the
  certificate then says Gurobi's check was not run.
- Offer effects are assumed separable across customers (no network or word-of-mouth effects) and constant
  over the 30-day window.
- The joint price and campaign plan assumes constant elasticity within each zone × period cell.
- Congestion relief is valued at a planning rate per net rush-hour trip moved onto the 407 ($0.50); it is
  a policy parameter for the business to set, not an estimate.

## Models

- Classifiers are evaluated on an untouched later fold with 90-day labels that never cross a fold boundary,
  but customers repeat across snapshots; the folds are separated in time, not by identity.
- The zone-level 30-day demand forecast runs 4-9% above the sum of the customer-level baselines, by period.
  The customer baselines are not rescaled to it, because doing so made the plan's estimates worse; the ratio
  is recorded in `uplift_metrics.json`. Interval coverage (92% at nominal 90%) is marginal over cells, not
  simultaneous.
- Isolation Forest flags are review signals evaluated against 30 planted anomalies, not fraud labels.
- Clustering stability is bootstrap agreement on one snapshot, not stability over time.

## Platform

- The Databricks job's four notebooks have been executed locally with real PySpark and a stand-in for the
  Databricks runtime (`databricks/local_run.py`); Delta and Unity Catalog statements were checked against the
  data rather than executed. The hosted run's status is recorded in `databricks/README.md`.
- SageMaker: the pipeline is defined and its entry points run locally; it has not run in AWS.
- Power BI: every measure executes against Power BI's engine and the HTML panels render from its output. The
  HTML Content visual is an AppSource custom visual; an organisation that blocks AppSource visuals would see
  those nine panels empty while the native visuals still work.
- Serving is fail-closed on a hash-verified snapshot; hashes detect corruption, not a compromised host.

# Architectural decisions

Each record states the decision, why, and what was tried and rejected. Release 1.1.

## 1. Score every policy against the simulator's truth, and keep the truth quarantined

**Decision.** The simulator (`simulation.py`) owns every hidden trait and the true effect of every offer on every
customer. Only `evaluation.py` (and the trial/policy-test simulators that draw outcomes) may call it. Models, features,
the optimizer, the app and the API never see it; tests assert that no `latent_`/`true_` column reaches a feature list or
the serving snapshot.

**Why.** A real operator can only estimate a campaign's incremental value, so a portfolio project that reports only
model estimates cannot show whether its targeting works. Scoring each plan against the truth turns "the optimizer picks
good customers" from a claim into a measurement, and exposes the winner's curse.

## 2. Learn behaviour, compute economics

**Decision.** Causal learners estimate *incremental trips by travel period* for each offer. Money follows from the
offer's terms (`economics.py`): a discount is paid on every eligible trip, including trips that would have happened
anyway; a threshold credit only if the threshold is reached; points carry a fixed liability.

**Rejected.** Modelling incremental net contribution directly with DR, T and X learners. Its rank correlation with the
true value was near zero (PEHE 10-25 against true effect spreads of 2-7): heavy travellers' revenue noise swamps a
small behavioural effect. The offer terms are contract facts, so estimating them is pure added variance.

## 3. Choose the causal learners once, by pooled doubly robust loss and a one-standard-error rule

**Decision.** S-, T-, X- and DR-learners are fitted for every offer. Their per-customer doubly robust validation
losses are pooled across offers, and production uses the equal-weight average of every learner whose pooled loss is
within one paired standard error of the best. The rule needs only trial data; the simulator's truth checks it and is
never an input to it.

**Why.** Release 1.0 picked a learner per offer by the lowest loss. The per-offer differences were usually smaller than
their standard errors, so offers "chose" learners on noise, and the choice moved between runs. Pooling gives the
comparison nine offers' worth of data, and the one-SE rule averages learners the data cannot tell apart instead of
crowning a lucky one.

**Known cost.** In the committed run the rule keeps the S-learner alone (the X-learner's loss is 1.3 standard errors
behind), while on the truth the X-learner ranks customers better (mean Spearman 0.29 against 0.11). The plan still
reaches 75% of the ceiling. A rule tuned on the truth would score better here and would not exist in production; the
gap is shown on the app's Experiments page rather than hidden by tuning. The best-linear-predictor heterogeneity test
is reported for every offer.

**Rejected.** Applying the BLP calibration to production estimates. On held-out customers it increased value bias for
7 of 8 offers: the 15% validation fold is too small to estimate the level. It stays a diagnostic.

## 4. Blocked randomisation and CUPED

**Decision.** The July trial assigns arms within 30 strata of 90-day trips x trip trend, and every effect is reported
with CUPED variance reduction and Bonferroni intervals; subgroups use Benjamini-Hochberg.

**Why.** Simple randomisation left the control arm the lightest travellers by chance (pre-period SMD 0.08), which
inflated every arm's later-period effect at once because all arms share one control. Blocking cut the worst imbalance
to 0.03. Future churn cannot be blocked on, so the 60-day carry-over remains noisy (see 5).

## 5. Plan with a conservative carry-over ratio

**Decision.** Days 31-90 value is the trial's regression-adjusted carry-over ratio times in-window gross contribution,
using the bootstrap 20th percentile rather than the point estimate.

**Why.** The ratio is small relative to its noise: arms with identical pre-period behaviour differ by up to 0.75
expected future trips through unobservable churn. Planning on an upper-leaning estimate would buy carry-over the trial
cannot confirm. The remaining overestimate is visible in the winner's-curse figures.

## 6. Solve the whole population exactly; certify optimality with Gurobi inside its licence

**Decision.** One MIP over every eligible customer-offer pair (112,563 binaries in the committed run). HiGHS solves the LP relaxation;
rounding gives an incumbent; reduced-cost fixing removes every variable that provably cannot change in a better plan;
the remaining core is solved exactly (Gurobi when it fits the 2,000-variable licence, HiGHS otherwise). A second fixing
round with the final gap lets Gurobi independently confirm the plan.

**Rejected.** A 600-customer shortlist (release 0.4): optimal only for the shortlist. Handing the full MIP straight to
HiGHS: no incumbent within 60 seconds.

**Why it matters.** Shadow prices from the same LP say what one more dollar, contact, point or trip of peak capacity
is worth, which is the question a campaign owner actually asks.

## 7. Signed capacity coefficients

**Decision.** Each candidate carries incremental trips per travel period, and capacity rows use them with their sign.
An off-peak offer that moves a commuter out of the peak *frees* peak capacity.

## 8. Fail closed on the serving snapshot

**Decision.** The pipeline writes `outputs/serving/` and a SHA-256 manifest. The app and API verify every file before
serving and refuse a partial, refreshing or edited snapshot; production additionally refuses a failed acceptance gate,
anonymous access (app) and missing API keys (API).

## 9. Batch decisions, online lookups

**Decision.** Scoring and optimization run in batch; the API serves lookups and bounded what-if solves over the
verified batch output. No model is scored online.

**Why.** The decision is a monthly portfolio allocation under shared constraints; per-request scoring cannot respect a
budget or capacity shared across customers.

## 10. Generated Power BI

**Decision.** The PBIP is generated from `bi/model_spec.py` and `bi/report_spec.py`, with data embedded as M literals
from `powerbi/data/`. CI regenerates it and fails on any byte of drift.

**Why.** Power BI fails silently on hand-authored PBIR (an untyped literal, a missing wildcard selector, a reserved
VAR name). A generator encodes each fix once.

## 11. Demand forecast refit after selection

**Decision.** The 30-day forecaster is selected on validation, accepted on test against the same-weekday baseline,
then refit on all pre-decision history before forecasting October.

**Known limit.** Trained largely on a year when the account base was growing, it runs 4-9% above the sum of the
customer-level baselines in October 2025, by period. Over-forecasting is the conservative direction for capacity, and
rescaling the customer baselines to it made the plan's estimates worse, so it is recorded rather than applied.

## 12. A rush-hour offer, valued for the congestion it relieves

**Decision.** A ninth offer, 25% off rush-hour trips, and a planning value per net rush-hour trip moved onto the 407
($0.50, `Config.relief_value`) added to the objective. Signed capacity rows still bind: the offer is only used where
the zone has free-flow room at peak.

**Why.** A toll road's pricing decisions are also traffic decisions. Without a value for relief, the optimizer treats a
peak trip moved off a congested arterial as revenue only, and a rush-hour discount almost never pays for itself. The
value is a policy parameter for the business to set, exposed as a slider in the app's decision centre, not an
estimate. In the committed run the plan uses it for 49 customers and moves a net 86 rush-hour trips per workday.

## 13. Gate on what production could observe; report simulation checks beside it

**Decision.** The release gate's blocking checks are the ones computable without the simulator: calibrated
classifiers against baselines on a later fold, demand against the seasonal baseline with interval coverage, and
held-out uplift Qini above zero. Two simulation-only checks (the plan reaches at least 60% of the ceiling and beats
every other approach; elasticity intervals cover the truth in at least 80% of cells) are reported separately and must
also pass in this repository.

**Rejected.** A gate on the rank correlation between estimated and true value (it failed at 0.23 against a 0.30
threshold while the plan reached 72% of the ceiling). The correlation across all customer-offer pairs is not what the
plan depends on; the value of the plan's own choices is, and that is what the simulation check now measures.

## 14. HTML and CSS panels in Power BI, validated in the engine

**Decision.** Every page's KPI row is one HTML strip (a status pill in words and a micro-visual per KPI: progress
against a limit, value against a target, parts of a total, a mini trend or an interval), and nine report panels
(the command-centre hero, offer cards, guardrails, policy leaderboard, experiment
forest plot, capacity heat grid, segment table, scorecard and narrative) are DAX measures that return HTML, rendered
by the HTML Content custom visual with one shared stylesheet. Native visuals stay wherever cross-filtering matters.

**Why.** A forest plot with real confidence intervals, a zone-by-period heat grid with free capacity in each cell, or
cards with an inline bar are not native Power BI visuals; built from tiles and cards they either look approximate or
take dozens of visuals per page. The cost is an AppSource dependency and markup inside DAX, so every measure is executed
against Power BI's engine (`scripts/validate_powerbi_model.ps1`) and its output is rendered at the visual's exact size
and checked for overflow (`scripts/preview_powerbi_html.py`). Executing the model this way also found the TMDL bug that
had stopped Desktop opening it: an apostrophe in a measure name, now escaped by the generator.

## 15. The Databricks job runs the same code, then proves it on the platform's terms

**Decision.** The job's first task runs the unchanged pipeline on the task's local disk (DuckDB needs a POSIX file
system) and copies its layers to a Unity Catalog volume. The later tasks do what the platform is for: Delta tables
with CHECK constraints, a PySpark recomputation of every feature that must match DuckDB to 1e-7, Unity Catalog
registration with a load-back scoring test, and a publish step that reconciles the plan with the optimizer's
certificate and writes a receipt.

**Why.** Rewriting the pipeline in PySpark would have produced a second implementation to keep in step with the
first. Running one implementation and gating on parity keeps a single source of truth while showing the Spark,
Delta, MLflow and Unity Catalog work the platform exists for. `databricks/local_run.py` runs all four notebooks
locally before any hosted run is spent; it found two real bugs (a fixed-size resent batch larger than a small
population's day, and a NaN rank correlation from a learner that cannot split) before either reached a cluster.

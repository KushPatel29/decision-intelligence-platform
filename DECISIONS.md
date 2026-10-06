# Architectural decisions

Each record states the decision, why, and what was tried and rejected. Release 1.0.

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

## 3. Choose the causal learner per offer by doubly robust validation loss

**Decision.** S-, T-, X- and DR-learners compete per offer; the one with the lowest doubly robust loss on the
validation fold serves. The loss is computable from trial data alone.

**Evidence.** Different offers pick different learners, and the oracle check reports whether the observable rule
picked well. The best-linear-predictor (BLP) heterogeneity test is reported for every offer.

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

**Decision.** One MIP over every eligible customer-offer pair (about 126,000 binaries). HiGHS solves the LP relaxation;
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

**Known limit.** Trained largely on a year when the account base was growing, it still over-forecasts October 2025 by
about 10%. Over-forecasting is the conservative direction for capacity.

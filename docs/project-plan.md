# Project plan: the October campaign decision

How this work would be run as a project with business stakeholders: who decides what, what each
milestone has to prove before the next starts, and how disagreements get settled. The organisation is
illustrative; the milestones and acceptance tests are the ones this repository actually implements.

## The question, in the sponsor's words

> "We spend on promotions and loyalty every month. Which customers should get which offer, at what cost,
> without filling the highway at rush hour, and how will we know it worked?"

Success is measured in **incremental net contribution after incentive costs**, not in redemptions or
"lift", with capacity and points liability as hard limits.

## Stakeholders and decision rights

| Group | Cares about | Decides | Consulted on |
|---|---|---|---|
| Marketing / loyalty (sponsor) | Participation, customer experience, the offer catalogue | Which offers exist; final plan sign-off | Targeting rules, contact limits |
| Revenue management / pricing | Contribution after subsidies, price integrity | Budget, ROI floor, price changes | Offer economics, elasticity |
| Traffic operations | Free-flow capacity, peak load | Capacity by zone and period, reserve | Rush-hour offers, demand forecast |
| Finance | Points liability, budget | Points cap, accounting of rewards | Incentive costing |
| IT / data platform | Source systems, security, SLAs | What data is provided and how | Storage layout, access (see [`data-platform-plan.md`](data-platform-plan.md)) |
| Privacy / legal | Consent, fair treatment | Eligibility rules, consent handling | Any new data field |
| Data science (this role) | Valid evidence, honest uncertainty | Methods, tests, the release gate | Everything above |

### RACI for the main deliverables

| Deliverable | Data science | Marketing | Revenue | Traffic ops | Finance | IT | Privacy |
|---|---|---|---|---|---|---|---|
| Data request and feature contract | R | C | C | C | I | A | C |
| Offer trial design (arms, power, metrics) | R | A | C | C | I | I | C |
| Trial analysis and readout | R/A | I | I | I | I | – | – |
| Targeting models and policy | R/A | C | C | I | I | – | C |
| Guardrails (budget, contacts, ROI, points, capacity) | R | C | A (budget, ROI) | A (capacity) | A (points) | – | – |
| Campaign plan sign-off | R | A | C | C | C | I | I |
| Production job and monitoring | R | I | I | I | I | A | – |

R responsible, A accountable, C consulted, I informed.

## Milestones and what each has to prove

| # | Milestone | Acceptance test (automated where possible) | Where |
|---|---|---|---|
| 1 | Data foundation | Feeds land with batch metadata; silver contract quarantines defects with reasons; point-in-time features with no label leakage | `data.py`, `features.py`, `tests/test_contracts.py` |
| 2 | Offer trial designed | Power calculation agreed with Marketing; metrics and guardrails written down before launch | `experiments.py::sample_size`, [`ab-testing-playbook.md`](ab-testing-playbook.md) |
| 3 | Trial read out | Balance (max SMD < 0.1), SRM, CUPED effects with Bonferroni intervals, sequential boundaries respected | `experiments.py::analyze` |
| 4 | Customer models | Each classifier beats its baseline on an untouched later fold and is calibrated (AUC ≥ 0.70, ECE ≤ 0.10) | `models.py`, `quality.py` |
| 5 | Targeting policy | Causal learners chosen by an observable rule; uplift Qini above zero on held-out trial customers | `causal.py` |
| 6 | Plan | Full-population MIP within every guardrail, certified optimal or with a stated gap; shadow prices reported to the owners of each limit | `optimization.py` |
| 7 | Policy test | The plan itself randomised against business as usual before full rollout | `policy_trial.py` |
| 8 | Production | Scheduled job, registered models, run receipts, monitoring, a dashboard the sponsor uses | `databricks/`, `powerbi/`, the app |

A milestone that fails its test does not proceed. In this repository that is literal: the release gate
(`quality.py`) is evaluated on every run, and the Databricks job will not publish a run that fails it. At
3,000 customers (300 per trial arm) the gate fails on attrition AUC and on held-out uplift Qini, and the job
stops; at 25,000 it passes.

## How the guardrail conversation is had

Every limit in the plan belongs to someone, and the optimiser reports what each one costs. After each
solve, the LP shadow prices go to the owner of each binding guardrail as a sentence they can act on:

| Guardrail | Owner | What the committed run tells them |
|---|---|---|
| Free-trip inventory (3,000) | Marketing | One more voucher is worth $9.43 of expected value: the most valuable limit to relax |
| Incentive budget ($10,000) | Revenue | One more dollar is worth $0.37 at the margin: the budget is not the binding economics |
| Contact limit (5,000) | Marketing / customer experience | One more contact is worth $0.25 |

That turns "can we have more budget?" into a priced trade-off, and it is why the plan's Power BI page leads
with the guardrail table.

## Risks and how the plan handles them

| Risk | Mitigation |
|---|---|
| Model picks customers who would have travelled anyway | Targeting on causal uplift from a randomised trial, never on propensity; the policy is itself tested |
| Offers fill the road at rush hour | Signed capacity constraints by zone and period with a 20% reserve; rush-hour offers only where free-flow room exists |
| Winner's curse: the plan looks better on paper than in reality | Truth-scored evaluation in simulation; a risk-averse plan on lower confidence bounds is solved alongside |
| Points liability grows unnoticed | A points cap in the MIP and a reconciled points ledger |
| Data drifts after launch | PSI drift monitoring, matured-label calibration checks, feed-volume monitoring |
| Stakeholders cannot see why a customer got an offer | The app's *Next best offer* page shows each customer's candidate offers, values and the plan's choice |

## Communication

- **Weekly** during a test: a one-page readout (decision, effect in dollars with its interval, guardrails,
  balance, what the test could not detect).
- **Per plan**: the Power BI *Command centre* and the executive brief, written for people who will not read
  a confidence interval and still need to know how sure we are.
- **Decision log**: [`DECISIONS.md`](../DECISIONS.md) records each method choice, the alternatives tried and
  the evidence that settled it, so a decision can be revisited without re-litigating it from memory.

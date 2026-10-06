# A/B testing playbook for promotions, loyalty and pricing

How an offer, a loyalty reward or a price change is tested here, in the order the decisions are made.
Each step names the code that does it, so the playbook and the implementation cannot quietly disagree.

## 1. Decide what the test is for before designing it

| Question | Answer for the July offer trial |
|---|---|
| Decision the result feeds | Which offers belong in the October plan, and which customers each one moves |
| Unit of randomisation | Customer (account holder), never trip: a customer's trips are not independent |
| Primary metrics | Trips and **net contribution** per customer over the 30-day window, intention to treat |
| Why net contribution | A discount paid on trips the customer would have taken anyway is a cost; "trips went up" can still lose money |
| Guardrail metrics | Peak load against free-flow capacity, points liability, enrolment, sample-ratio mismatch |
| Secondary | The binary "travelled" response, kept for the classic two-proportion test and power planning |

Write these down before launch. A metric chosen after seeing the data is a finding, not a test.

## 2. Size it

`experiments.py::sample_size` gives customers per arm for a two-sided two-proportion test at 80% power with
a Bonferroni-split alpha; `continuous_sample_size` does the same for a mean. The July design asked for a
5-point lift in the travel rate across nine comparisons: **1,794 per arm**. It ran 2,500.

After the trial, report the **achieved** minimum detectable effect, not just the planned one. With CUPED it
was 0.35 trips per customer; without, 0.86. A null result smaller than the achieved MDE says "we could not
see it", not "there is nothing".

## 3. Randomise so the arms are comparable by construction

- **Blocked assignment** (`strata`, `blocked_assignment`): customers are grouped by 90-day trip frequency and
  trend, and each block is split evenly across arms. Simple randomisation balances on average; blocking
  balances in this sample.
- **Check balance** (`balance`): standardised mean differences on pre-treatment covariates. Anything above
  0.1 is a problem. July's worst was 0.033.
- **Sample-ratio mismatch**: a chi-square test of the realised allocation against the design. A failure
  means the assignment or the logging is broken and the effects cannot be trusted. July: p = 1.00.

## 4. Reduce variance before reading effects

**CUPED** (`cuped`): regress the outcome on the same customer's pre-period value (June trips for trips,
June spend for contribution) and analyse the residual. It cannot bias the effect, because the covariate is
measured before assignment. In July it removed 83.7% of the variance in trips, which is the difference
between needing 2,500 customers per arm and needing roughly 15,000.

## 5. Look early only with a boundary built for it

Peeking at a fixed-horizon test inflates false positives. The trial is read at days 10, 20 and 30 against
**O'Brien-Fleming** boundaries (`obrien_fleming_boundaries`), calibrated by simulating the null with the
same look schedule and the per-comparison alpha: z ≥ 4.84 at day 10, 3.42 at day 20, 2.79 at day 30. Early
looks need overwhelming evidence; the final look costs almost nothing. Eight of nine arms crossed early on
trips, which in practice means the offer could stop being paid for sooner.

## 6. Correct for the number of questions asked

- Primary comparisons (each offer vs control): **Bonferroni**, family alpha 0.05.
- Exploratory subgroups (`_subgroups`): **Benjamini-Hochberg**, reported as q-values and labelled as
  exploratory. A subgroup that "worked" is a hypothesis for the next test, not a targeting rule.

## 7. Read averages, then go beyond them

The average effect answers "is this offer worth sending to everyone?". In July most offers lose money on
the average randomised customer, and that is the expected result for discounts that are mostly paid on
trips that would have happened anyway. The causal learners (`causal.py`) fit on the same randomised data
find the customers each offer actually moves, and the optimiser contacts only those. The averages and the
plan disagree on purpose; the playbook's job is to make sure both are honest.

## 8. Test the targeting policy, not just the offers

An offer test validates an offer. It does not validate the model that picks who gets it. `policy_trial.py`
runs a second randomised test in which half the customers are governed by the optimised policy (including
those it chose not to contact) and half are not: intention to treat on the policy itself. Result: **+$1.40
net contribution per customer** (95% CI $0.23 to $2.57, p = 0.019).

## 9. Pricing tests

Price elasticity is identified from independently randomised price assignments by day, zone, period and
segment (`data.py`, `models.py::fit_elasticity`), so a price change is never confounded with demand.
Cell-level estimates are shrunk toward the pooled elasticity (empirical Bayes) and reported with 95%
intervals; in simulation the intervals cover the true elasticity in 94% of cells against a nominal 95%.

## 10. The readout

One page, in this order: the decision, the result in dollars per customer with its interval, whether the
guardrails held, the balance and SRM checks, what the test could not detect (achieved MDE), and what
changes. The app's *Experiments* page and the Power BI *Experiments* page carry the same content.

## Common failure modes this design blocks

| Failure | Guard |
|---|---|
| Peeking until significant | Pre-computed sequential boundaries |
| Many arms, one lucky winner | Bonferroni on primaries, BH on subgroups |
| Broken assignment or logging | SRM test, covariate balance |
| "Lift" that loses money | Net contribution as the primary metric, discount on baseline trips costed |
| Winner's curse in targeting | The policy is itself randomised and measured |
| Small effects called "no effect" | Achieved MDE reported next to every null |

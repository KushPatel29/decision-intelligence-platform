# Stakeholder requirements

This is an invented business brief, not a record of a real company's internal requirements.

Marketing asks for higher participation. Revenue needs incremental contribution after subsidies. Transportation wants available capacity respected. Customer operations needs understandable, affordable incentives. IT needs reproducible batch processing. Analytics needs credible experiment design and no future-information leakage.

| Requirement | Acceptance evidence |
|---|---|
| Allocate offers only to eligible accounts | Consent, online account, no past-due balance, active status; solver checks |
| Prevent repeated customer contacts | Combined decision table has unique customer IDs |
| Keep campaign within budget | Expected incentive cost <= configured shared budget |
| Maintain minimum net ROI | Sum(net contribution) >= minimum ROI × sum(cost) |
| Respect road capacity | Baseline forecast + safety reserve + incremental trips <= cell capacity |
| Respect inventory and points | Per-offer inventory and reward points constraints |
| Distinguish inactivity and decline | No future 90-day trips vs future count <50% of prior 90-day count |
| Communicate decision rationale | Economics columns, solver diagnostics, executive brief, model cards |
| Prove causality appropriately | Randomized synthetic trial; separate held-out causal-model evaluation |
| Support analyst questions | Five SQL/Python analyses with business conclusions |

All costs are CAD. One capacity cell is a synthetic zone × travel period over the 30-day campaign; it is not a real shared-segment route model. Minimum ROI refers to net incremental contribution divided by expected incentive/contact costs.

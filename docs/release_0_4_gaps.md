# Plan follow-through - release 0.4.0

The previous audit remains a historical comparison. This release adds baseline
selection/acceptance, monthly backtests, hour/direction disaggregation, joint
price/campaign strategy, later-margin/retention outcomes, customer marts and dated
state, prediction/volume/campaign checks, subgroup reports, a fresh constrained
policy trial, visual SQL cases, nine registry adapters, lifecycle tooling, richer
BI, fail-closed serving, audit records, private auth, containers and generated CI.

## Material boundaries still open

1. Hosted AWS/Databricks, storage/role provisioning, immutable container build,
   job/expense receipts and cloud model acceptance. Successful code stages do not
   qualify candidates that fail a held-out gate.
2. OIDC provider configuration and allowed/denied identity tests on an HTTPS
   staging host. Docker is unavailable here; authored images are unexecuted.
3. Actual GitHub publication, issues/milestones and executed CI. A local prepared
   workflow is not hosted CI evidence; repository destination is undecided.
4. Latest Power BI refresh/DAX/page review. The helper rejected the owned WebView
   reload dialog; revised source schemas passed.
5. Backup restore, staging load/latency/uptime, cost and escalation ownership.
   This is one private workspace, not a proven multi-tenant service or an SLA.
6. Real-population quality and observed impact. Hourly values disaggregate daily
   demand; days31-90 effects do not validate incremental twelve-month CLV.
   Customer-specific price sensitivity, loyalty earning propensity, segment
   elasticity and temporal segment stability remain research extensions.
7. Continuous campaign anomaly baselines and live notifications need repeated
   campaigns and hosted wiring. Current checks are batch reviews. Execution
   systems must enforce actual spending, contacts and roadway limits.

No system can be promised foolproof. The app rejects common invalid inputs,
preserves evidence and provides explicit recovery and deployment requirements.

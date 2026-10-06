# Original plan coverage audit

Assessment date: 6 October 2026. Product: Corridor 0.3.0.

Compared the user's 42-section outline with implementation files and saved local execution receipts. A working local product is delivered; full implementation of every detail in the original outline is still incomplete. Cloud preparation, hosted execution and observed business impact are different milestones.

## Priority gaps

| Priority | Area | Current evidence | Work remaining |
|---|---|---|---|
| High | AWS and hosted SageMaker | Pipeline definition compiles; real entry points passed local preparation, training, evaluation and inference checks | Provision approved project storage/access; verify container dependencies and quotas; execute jobs, registry and batch inference; save job IDs, predictions, logs and costs. S3/IAM/CloudWatch/Glue/Athena execution is not demonstrated. |
| High | SageMaker model coverage | `aws/pipeline.py` trains `TrainPropensity`; `aws/train_entry.py` fits a propensity logistic model | Extend the cloud workflow to churn, attrition, uplift, elasticity and demand with suitable inputs, model-specific evaluation gates and inference contracts. A complete propensity pipeline is not the full six-model cloud portfolio. |
| High | Model selection and forecasting quality | Demand MAE 12.011 versus seasonal-naive MAE 10.478; 90-day contribution MAE 66.803 versus historical-margin baseline MAE 55.295 | Use baseline-aware selection and improve/revalidate candidates. The current learned regressors have higher held-out errors than their simple baselines. Add rolling 30-day validation, interval/coverage evaluation and the planned zone/direction/hour forecasting grain. Do not interpret 90-day evaluation as validated 12-month CLV. |
| High | Pricing linked to optimization | Six price-change scenarios exist for each zone and travel period; Gurobi selects among three fixed offers | Add effective-price strategy decision variables and connect elasticity-based demand, contribution and capacity outcomes to the optimizer. Customer surplus and scenario capacity effects are also absent from the price output. Avoid double-counting price and treatment effects. |
| High | Incremental CLV and retention objective | Candidate rows carry `clv_12m`, but `objective_value` is net contribution plus network value | Estimate incremental retention/CLV effects before including them in the objective. Baseline customer value is not an offer's causal value increase. Loyalty currently models response, trips and redemption; earning propensity and longer-term retention/value effects are incomplete. |
| Medium | Complete Databricks gold layer | Authored notebook uses the complete locally tested feature allowlist; publishes `gold_customer_features` and `gold_zone_day` | Hosted run and parity receipt remain pending. Add the other planned customer-month, customer-offer, campaign, pricing and loyalty marts, campaign event ingestion and session/history features. Existing `databricks/README.md` still describes a feature subset and an older schema default; it needs synchronization with the notebook. |
| Medium | Monitoring and anomaly breadth | Feature PSI/KS, mature July classification metrics and historical customer Isolation Forest flags | Add prediction-score drift, business demand/price/ROI monitoring, campaign redemption/conversion anomaly alerts, volume/schema/missingness change alerts, and a governed review/retraining workflow. Data contract tests already exist; continuous anomaly monitoring is the gap. |
| Medium | Experiment coverage | Powered four-arm offer trial, treatment comparisons, T/S/X ranking and held-out offer-rule evaluation | Evaluate the actual constrained optimization policy in a new randomized synthetic policy experiment. Add segment, pre-treatment CLV-decile, price-sensitivity and travel-pattern summaries with sample sizes and uncertainty. Personalized causal models exist, but these subgroup reports do not. |
| Medium | Customer 360 and changing account state | Scored customer mart includes travel, digital counts, risks, value, segments, eligibility and earned points | Integrate tier, reconciled points balance, offer-specific redemption probabilities, elasticity and richer campaign/channel fields with explicit grains. Status history records initial status only; effective-dated status/consent transitions are not implemented. |
| Medium | MLflow lifecycle and provenance | Seven model families have tracking receipts; three calibrated classification models are registered at Candidate version 2 and scoring roundtrips passed | Register/version additional deployable model families, implement approval/promotion/rollback/archival decisions, link SHAP and training metadata consistently, and attach a real commit identity. Some model-selection comparisons live within an artifact instead of separate experiment runs. |
| Medium | Native Power BI content | Eight native pages refreshed and visually reviewed; DAX totals match local data | Complete the requested visual detail: customer risks/digital activity, reward redemption/economics, experiment intervals/significance, hourly demand, and model versions/drift/pipeline status. Eight verified pages do not mean every requested field is visualized. |
| Medium | GitHub project delivery and CI | Local Git repository, workflow definition, roadmap, requirements, decisions and changelog | No commit or Git remote is configured. Publish a reviewed repository, create actual milestones/issues and run hosted CI. The current workflow installs only the core/dev extras; many app/output integration checks skip on a clean checkout. Add an explicit generated-data integration/app job. |
| Lower | Analyst case-study presentation | Five SQL/Python cases produce CSV results and three-sentence business conclusions | Add a visual for each case and expose the analyst workbench in the decision product or a standalone reviewed report. |

## Coverage of the original sections

| Plan sections | Assessment |
|---|---|
| 1: evidence matrix | Present with explicit execution boundaries. It does not independently verify the historical job posting. |
| 2–7: customer, transportation, pricing, promotions, loyalty, digital domains | Canonical synthetic tables exist. Changing account history, all proposed event/session features, reward alternatives and longer-term loyalty effects are incomplete. |
| 8: external sources | MVP minimum met: genuine weather, holiday and Bank of Canada FX sources. Events, fuel, incidents and traffic sources are optional expansion, not an unmet three-source minimum. |
| 9–10: Databricks and PySpark | Local million-row Spark feature benchmark and Delta readback verified. Full hosted medallion execution and all proposed gold marts remain open. |
| 11: SQL | Named analytical SQL files, cutoff features and five ad-hoc SQL cases are implemented. |
| 12: segmentation | RFM, K-Means, silhouette, Davies–Bouldin and bootstrap agreement implemented. Temporal stability remains unvalidated. Gaussian mixture is not implemented. |
| 13–16: propensity, churn, attrition, CLV | Classification, calibration, enrollment, redemption, contribution forecast and BG/NBD/Gamma-Gamma benchmark implemented. Forecast selection and long-horizon value validation remain open. |
| 17–18: elasticity and demand | Zone/period log-log regression and daily zone/period demand implemented. Segment/business elasticity and direction/hour forecasting are incomplete. |
| 19: uplift | S/T/X learner comparisons and held-out causal ranking implemented. Constrained-policy validation remains open. |
| 20: anomalies | Customer review flags implemented; campaign and continuous data-quality anomaly monitoring incomplete. |
| 21–22: SageMaker and MLflow | Propensity cloud definition/local stages and local experiment tracking implemented. Hosted six-model pipeline and full deployment lifecycle incomplete. |
| 23–25: incentive, loyalty and price optimization | Shared promotion/reward MIP and constraints implemented. Price-strategy optimization and incremental long-term objective terms incomplete. |
| 26: experiments | Powered randomized offer trial implemented; optimized-policy experiment and planned subgroup reports incomplete. |
| 27–30: analyst cases, Customer 360, governance, privacy | Main local deliverables implemented; case visuals, richer Customer 360 fields, changing account state and deployed cloud governance remain open. |
| 31–32: monitoring and BI | Local drift/performance checks and eight native pages implemented; full monitoring and all requested BI details incomplete. |
| 33–34: executive brief and model cards | Four-page executive PDF and nine model cards delivered. |
| 35–36: project and stakeholder requirements | Local documents delivered; actual GitHub issues, milestones and repository publication absent. |
| 37: testing | 46 local checks passed; reproducibility, optimizer constraints, browser review and packaged-app checks are recorded. Hosted integration CI and additional model-quality gates remain open. |
| 38–42: connected architecture and presentation | Local flow is connected. End-to-end hosted architecture and a claim of productionized AWS/Databricks operation are not yet supported. Professional tenure cannot be supplied by this project. |

## Intentional variations and optional breadth

- Promotion and loyalty are solved jointly so spending, contacts, reward points and capacity share one feasible allocation. This is an intentional variation from two separate optimization problems. A separate loyalty-only solve is not needed to establish that rewards are optimized.
- Logistic regression and scikit-learn histogram boosting are compared for classification; random forests support causal outcome/value models. XGBoost and LightGBM are not implemented. Those named examples and Gaussian mixture would add algorithm breadth, but existing models already demonstrate classification, regression and clustering.
- The system uses off-peak, weekend and 500-point offers. Additional spend thresholds, passes, free trips and reward sizes are expansion options.
- LLMs, RAG, computer vision, Kubernetes, Kafka and extra neural models remain outside the requested priorities.

## Suggested completion order

1. Correct baseline-aware forecast selection and establish suitable quality gates.
2. Extend pricing decisions and credible incremental value/retention inputs; validate the constrained policy with a randomized synthetic holdout.
3. Complete Databricks marts and multi-model SageMaker entry points, then execute hosted pipelines with approved access and a spending cap.
4. Finish monitoring, Customer 360/account histories and model lifecycle controls.
5. Complete detailed BI/case visuals and publish repository milestones with executed CI evidence.

## Evidence inspected

- `aws/pipeline.py`, `aws/train_entry.py`, `aws/README.md`, `outputs/sagemaker_local_validation.json`.
- `databricks/medallion.py`, `src/decision_platform/spark_features.py`, `outputs/spark_benchmark.json`.
- `src/decision_platform/models.py`, `optimization.py`, `experiments.py`, `monitoring.py`, `adhoc.py`, `cli.py`.
- `outputs/model_metrics.json`, `customer_360.csv`, `experiment_results.json`, `model_registry.json`.
- `scripts/register_models.py`, `scripts/build_powerbi.py`, `.github/workflows/ci.yml`, SQL and governance documents.
- Local Git reports no resolvable HEAD and no configured remote. This audit did not assess an external repository.

Lower error is better for the MAE comparisons above. All data and performance claims refer to the synthetic local portfolio; there is no claim of observed customer impact.

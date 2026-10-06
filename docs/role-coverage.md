# Role coverage: Data Scientist, customer, promotions, loyalty and pricing analytics

This maps each responsibility and qualification in a toll-road operator's Data Scientist posting
(Woodbridge, Ontario; requisition JR101266) to the place in this repository that does it and the
evidence it produced. Requirements are paraphrased. Every figure comes from the committed 25,000-customer
run (`outputs/serving/`, hash-verified by `manifest.json`) unless a row says otherwise.

The data is synthetic. A simulator with known ground truth is what lets the targeting be scored against
the truth, which no real dataset allows; it also means no figure here is a claim about a real company's
customers.

## Responsibilities

| The posting asks for | Where it is done | Evidence |
|---|---|---|
| Assemble and analyse customer behaviour from internal, external and emerging data | `data.py` (accounts, transponders, trips, loyalty, offers), `external.py` (Open-Meteo weather, Nager.Date holidays, Bank of Canada CAD/USD, each cached with a SHA-256 provenance record), digital funnel events as the emerging source | 3,680,249 trips, 1,412,304 digital events, 4,147 trips quarantined by the bronze-to-silver contract (duplicate batch, unit error, impossible charges) |
| Promotions, loyalty and pricing models and optimisation in Python, PySpark and Gurobi, in Databricks | `causal.py` (nine offers incl. two loyalty-point rewards and a rush-hour discount), `pricing.py`, `optimization.py`; `spark_features.py`; the Databricks job in `databricks/` | One MIP over **112,563 customer-offer binaries**, proven optimal (gap 1.5e-7 to the LP bound); **Gurobi** re-solved the 445-variable residual and confirmed the optimum; PySpark features equal DuckDB's to **2.2e-11** on all 39 features |
| Analyse target groups (segments) for promotions, loyalty and pricing | `models.py::_segments`, `experiments.py::_subgroups`, `models.py::fit_elasticity` | RFM playbook; K-means (5 clusters, bootstrap ARI ≥ 0.985) against a BIC-selected Gaussian mixture (8); subgroup effects with Benjamini-Hochberg FDR; elasticity by zone × period × segment |
| Ad hoc analysis and modelling | `adhoc.py`, *Analyst workbench* page | Five SQL window-function cases (cannibalisation, enrolment vs value, segment decline, unused capacity, weekend decline), each with its query, result and reading |
| Lead project work with business stakeholders | [`project-plan.md`](project-plan.md), [`DECISIONS.md`](../DECISIONS.md) | Stakeholder map and RACI, milestones with acceptance tests, a decision log of 11 recorded design decisions with what was rejected and why |
| Build targeting, propensity, price elasticity, attrition, lifetime value, churn and segmentation models | `causal.py`, `models.py`, `advanced.py` | Targeting: causal ensemble + MIP. Propensity: XGBoost, test AUC **0.913**, ECE 0.057. Churn (90-day inactivity): XGBoost AUC **0.910**. Attrition: HGB AUC 0.740. Elasticity: empirical Bayes, 95% intervals cover the true elasticity in **94%** of cells. CLV: historical margin vs gradient boosting vs BG/NBD + Gamma-Gamma, chosen on validation MAE |
| Develop and measure promotions, loyalty and pricing with A/B testing | `experiments.py`, `policy_trial.py`, [`ab-testing-playbook.md`](ab-testing-playbook.md) | Ten-arm blocked randomised trial, 2,500 per arm against 1,794 required; max covariate SMD 0.033; SRM p = 1.00; CUPED removed **83.7%** of variance (detectable effect 0.35 trips vs 0.86 unadjusted); simulation-calibrated O'Brien-Fleming boundaries; Bonferroni. Then a second randomised test of the targeting policy itself: **+$1.40 per customer** (95% CI $0.23 to $2.57, p = 0.019) |
| Explain complex models in plain language | Executive brief (`output/pdf/`), the Power BI *Command centre* narrative, every app page's "How these numbers are made", model cards in `docs/model_cards/` | The headline finding, stated without jargon: the customers most likely to travel are not the ones an offer moves (propensity vs true value, Spearman **−0.47**) |
| Support data structure and storage planning with IT | [`data-platform-plan.md`](data-platform-plan.md), `docs/schema_registry.*`, `docs/data_dictionary.md`, `docs/feature_catalog.md` | Medallion layout, field-level requests with owners and refresh SLAs, retention, access and PII handling; the silver trip contract enforced as Delta CHECK constraints |

## Qualifications

| The posting asks for | Where it is done | Evidence |
|---|---|---|
| Python, SQL | The whole pipeline; `sql/customer_features.sql` | 39 point-in-time features in one SQL file, executed by DuckDB and re-implemented column for column in PySpark |
| Tableau / Power BI | `powerbi/` (generated PBIP), `src/decision_platform/bi/` | 9 pages, 118 visuals, 94 documented measures and 9 HTML/CSS panels; every one of 149 measures executed against Power BI's engine by `scripts/validate_powerbi_model.ps1`; a byte-for-byte drift gate in CI. Tableau is not built: the posting accepts either |
| AWS SageMaker, AWS cloud | `aws/` | A SageMaker Pipelines definition (Processing, Training, held-out Evaluation, quality gate, Model Registry with pending manual approval, Batch Transform) whose entry points are run locally by `scripts/verify_cloud_stages.py`. **Not executed in AWS**: no account role is available, and the README says so |
| MLflow | `models.py::log_experiment`, `databricks/notebooks/03_registry.py` | Every model run tracked (local SQLite, or the Databricks workspace inside the job); Unity Catalog registration with signature, input example, pinned requirements and a `candidate` alias; each version loaded back from the registry and required to score exactly as the pipeline did |
| Databricks | `databricks.yml`, `databricks/` | A four-task serverless job: pipeline with Gurobi and workspace MLflow → Delta medallion with CHECK constraints and a PySpark parity gate → UC model registry → reconciled publish and a run receipt. `databricks/local_run.py` executes all four notebooks locally first; see the job README for the hosted run's status |
| Clustering, regression, classification, anomaly detection | `models.py`, `forecasting.py` | Clustering: K-means and GMM. Regression: 30-day demand forecast (ratio boosting, MAE 43.8 vs 50.2 same-weekday baseline, 90% conformal interval coverage 92%), CLV, elasticity. Classification: three calibrated classifiers. Anomaly detection: Isolation Forest caught **30 of 30** planted account anomalies at a 0.5% review rate (robust z-score baseline: 11 of 30) |
| Customer analytics: targeting, propensity, elasticity, attrition, LTV, churn, segmentation | As above | The policy comparison scores each targeting approach against the simulator's truth: optimised plan **75%** of the perfect-knowledge ceiling, uplift ranking 75%, propensity targeting 7%, RFM playbook −5% |
| Business analysis, problem solving, project management, communication | `DECISIONS.md`, `docs/project-plan.md`, the executive brief | Each design decision records the alternatives tried and the evidence that settled it, including the ones that failed |

## What this repository does not claim

- Real customer data, real business results or a real company's systems.
- A hosted SageMaker execution: the pipeline is defined and its stages run locally; the AWS run needs an
  account role this project does not have.
- A Tableau workbook.
- That the causal learners are well calibrated in level: they *under*-state value (mean bias −$4.49 per
  customer-offer), so the plan's predicted $42,649 sits below its simulated true value of $64,774.

"""Architecture & evidence: how the system fits together and where each requirement is demonstrated."""

import pandas as pd
import streamlit as st

from decision_platform.ui import callout, page_header, tiles
from decision_platform.webapp import ROOT, doc

page_header(
    "Architecture & evidence",
    "How the platform fits together, what each part proves and where to find it. Every number in the app comes "
    "from one reproducible pipeline run over a synthetic population and three real public data sources.",
    eyebrow="Operate",
)
summary = doc("summary")
tiles(
    [
        ("Customers", f"{summary['customers']:,}", "Synthetic, with hidden behavioural traits", True),
        ("Trips", f"{summary['trips']:,}", f"{summary['quarantined_trips']:,} quarantined from bronze"),
        ("Digital events", f"{summary['digital_events']:,}", "App, web and email funnel"),
        (
            "Decision variables",
            f"{doc('optimization')['joint']['candidate_count']:,}",
            "Customer-offer pairs in one MIP",
        ),
    ]
)
st.subheader("Pipeline")
st.graphviz_chart(
    """
digraph corridor {
  rankdir=LR; bgcolor="transparent";
  node [shape=box, style="rounded,filled", fillcolor="#102437", color="#2d4c61", fontcolor="#eef8ff", fontname="Inter", fontsize=11];
  edge [color="#5b7486"];
  subgraph cluster_sources { label="Sources"; fontcolor="#b3c7d7"; color="#263f52";
    weather [label="Open-Meteo weather"]; holidays [label="Nager.Date holidays"]; fx [label="Bank of Canada CAD/USD"]; sim [label="Synthetic accounts,\\ntrips, digital, points"]; }
  bronze [label="Bronze\\nraw feed + defects"]; silver [label="Silver\\nconformed + quarantine"]; gold [label="Gold marts\\nCustomer 360, customer-month,\\ncustomer-offer, zone-day"];
  models [label="Customer models\\npropensity, churn, attrition,\\nCLV, segments, anomalies"]; trial [label="10-arm July trial\\nCUPED, sequential, BLP"];
  causal [label="Causal learners\\nS/T/X/DR, one-SE ensemble"]; demand [label="Demand forecast\\n+ elasticity"]; mip [label="Full-population MIP\\nHiGHS LP + Gurobi core"];
  eval [label="Truth-based\\npolicy evaluation"]; app [label="Streamlit app"]; api [label="Decision API"]; bi [label="Power BI"]; dbx [label="Databricks\\nDelta + Unity Catalog"];
  weather -> silver; holidays -> silver; fx -> silver; sim -> bronze -> silver -> gold;
  gold -> models; gold -> trial -> causal; gold -> demand; models -> mip; causal -> mip; demand -> mip;
  mip -> eval; mip -> app; mip -> api; mip -> bi; mip -> dbx; eval -> app;
}
"""
)

st.subheader("Requirement evidence")
evidence = [
    ("Python", "Entire pipeline, models, optimizer and app", "src/decision_platform/"),
    ("SQL", "Point-in-time features, marts and window-function analyst cases", "sql/, adhoc/"),
    (
        "PySpark / Databricks",
        "Four-task serverless job: pipeline with Gurobi, Delta medallion with CHECK constraints, PySpark features "
        "matching DuckDB to 1e-7, Unity Catalog registry, reconciled publish",
        "databricks.yml, databricks/, spark_features.py",
    ),
    (
        "AWS SageMaker",
        "Processing, training, evaluation gate, registry and batch transform definitions",
        "aws/",
    ),
    (
        "MLflow",
        "Tracked runs with lineage tags; Unity Catalog registration with a load-back scoring test",
        "models.py, databricks/notebooks/03_registry.py",
    ),
    ("Gurobi", "Exact core of the campaign MIP and an independent optimality check", "optimization.py"),
    (
        "Power BI",
        "Generated 9-page PBIP with SVG tiles and HTML/CSS panels; every measure executed in the engine",
        "powerbi/, src/decision_platform/bi/",
    ),
    ("Classification", "Propensity, churn, attrition, enrollment, redemption", "Model operations"),
    ("Regression", "Contribution forecast, elasticity, demand, trip-effect learners", "models.py, causal.py"),
    ("Clustering", "K-Means and BIC-selected Gaussian mixture vs RFM rules", "Customer intelligence"),
    (
        "Anomaly detection",
        "Isolation Forest on accounts, robust monitors on the feed, both scored on planted cases",
        "Customer intelligence, Operations centre",
    ),
    (
        "Targeting & propensity",
        "Next best offer per customer; propensity shown to be the wrong targeting signal",
        "Next best offer, Policy value",
    ),
    (
        "Price elasticity & pricing",
        "Empirical-Bayes elasticities with intervals; joint price and campaign MIP",
        "Pricing studio",
    ),
    (
        "Promotions & loyalty",
        "Nine offers incl. a rush-hour discount and two point rewards; points ledger and liability",
        "Offers & loyalty",
    ),
    (
        "Churn, attrition & LTV",
        "Calibrated classifiers; heuristic and BG/NBD + Gamma-Gamma value",
        "Customer intelligence",
    ),
    (
        "A/B testing",
        "Powered 10-arm trial, blocked randomisation, CUPED, O'Brien-Fleming, BH-FDR; the targeting policy itself "
        "randomised",
        "Experiments",
    ),
    ("External data", "Weather, public holidays, exchange rate", "external.py"),
    (
        "Data management",
        "Bronze/silver/gold with contracts, quarantine and a schema registry; a data platform plan for IT",
        "docs/data-platform-plan.md",
    ),
    (
        "Stakeholder communication",
        "Executive brief, model cards, a project plan with RACI, an A/B testing playbook",
        "output/pdf/, docs/",
    ),
]
st.dataframe(
    pd.DataFrame(evidence, columns=["Requirement", "Evidence", "Where"]), hide_index=True, width="stretch"
)
callout(
    "This is a synthetic portfolio system. It demonstrates methods and engineering, not observed business impact, "
    "and it is not affiliated with 407 ETR. Professional experience cannot be manufactured by a project."
)

st.subheader("Downloads")
for path, label, mime in [
    (ROOT / "output" / "pdf" / "executive_brief.pdf", "Executive brief (PDF)", "application/pdf"),
    (ROOT / "outputs" / "executive_brief.md", "Executive brief (Markdown)", "text/markdown"),
]:
    if path.exists():
        st.download_button(label, path.read_bytes(), file_name=path.name, mime=mime)

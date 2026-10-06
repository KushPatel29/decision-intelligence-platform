# Open Corridor 0.4.0

The release includes precomputed synthetic results for all twelve workspaces. You can explore the app and run HiGHS campaign or joint price/campaign scenarios without cloud credentials or regenerating the data.

1. Open a terminal in this folder and create a Python 3.12 environment: `python -m venv .venv`.
2. Install the tested runtime: `.\.venv\Scripts\python.exe -m pip install -r requirements-runtime.txt`.
3. Install this project: `.\.venv\Scripts\python.exe -m pip install --no-deps -e .`.
4. Start it: `.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1`.
5. Open http://127.0.0.1:8501.

Decision centre opens on a saved campaign. Scenario studio changes budget, contacts, points, ROI and demand reserve; solves report their actual solver and shared-constraint checks. Save reviewed scenarios to preserve the allocation, release identity and owner audit reference. Local audit storage is runtime/decisions.sqlite; portable archives omit your saved records.

Pricing also runs a joint discrete-price/campaign optimization. Operations centre displays model acceptance, integrity, drift and deployment requirements. Analyst workbench connects a SQL case to its chart and conclusion. All modeled effects and customer data are synthetic.

Gurobi is optional and needs its own license. The delivered baseline used the local Gurobi license; HiGHS provides the same constraints without a commercial license.

Open powerbi/Corridor/Corridor.pbip for the native report. Run scripts/rebind_powerbi.py after moving the folder. Revised native source has 16 tables and 32 measures; Desktop refresh/DAX/page verification is pending. The executive brief is in output/pdf/.

Local mode is for a private computer. Before hosting, follow docs/production_runbook.md: configure OIDC, approved identities, immutable containers, HTTPS, writable audit storage and staged acceptance. AWS/Databricks jobs are prepared but have no hosted execution receipt. PROJECT_STATUS.md and outputs/readiness.json state the verified boundary.

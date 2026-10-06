"""Corridor decision platform. Run: streamlit run app.py

Reads only the hash-verified serving snapshot, runs bounded local solves and
keeps reviewed plans in an owner-isolated audit store. No automatic cloud writes.
"""

import os

import streamlit as st

from decision_platform.access import require_access
from decision_platform.ui import CSS, footer
from decision_platform.webapp import SERVING, snapshot_stamp, verify_snapshot

st.set_page_config(
    page_title="Corridor · Decision intelligence",
    page_icon=":material/route:",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(CSS, unsafe_allow_html=True)
owner = require_access(st)

stamp = snapshot_stamp()
if stamp is None:
    st.title("Corridor")
    st.info("No serving snapshot yet. Run the pipeline to build one.")
    st.code("python -m decision_platform.cli demo", language="bash")
    st.stop()
try:
    manifest = verify_snapshot(stamp)
    if os.environ.get("CORRIDOR_ENV") == "production":
        import json

        gate = json.loads((SERVING / "quality_gate.json").read_text())
        if not gate["passed"]:
            raise ValueError("Production model acceptance failed")
except (ValueError, OSError, KeyError) as exc:
    st.title("Corridor")
    st.error(
        "The decision snapshot is refreshing, incomplete or failed its integrity check. "
        "Restore a verified release or finish the pipeline run before continuing."
    )
    st.caption(str(exc))
    st.stop()

st.session_state["corridor"] = {
    "owner": owner,
    "stamp": stamp,
    "release_id": manifest["release_id"],
    "decision_date": manifest["decision_date"],
}

pages = {
    "Decide": [
        st.Page("views/decision_centre.py", title="Decision centre", icon=":material/route:", default=True),
        st.Page("views/next_best_offer.py", title="Next best offer", icon=":material/person_search:"),
        st.Page("views/pricing.py", title="Pricing studio", icon=":material/sell:"),
    ],
    "Understand": [
        st.Page("views/customers.py", title="Customer intelligence", icon=":material/groups:"),
        st.Page("views/offers_loyalty.py", title="Offers & loyalty", icon=":material/loyalty:"),
        st.Page("views/transportation.py", title="Transportation", icon=":material/traffic:"),
    ],
    "Prove": [
        st.Page("views/policy_value.py", title="Policy value", icon=":material/verified:"),
        st.Page("views/experiments.py", title="Experiments", icon=":material/science:"),
        st.Page("views/model_operations.py", title="Model operations", icon=":material/model_training:"),
    ],
    "Operate": [
        st.Page("views/operations_centre.py", title="Operations centre", icon=":material/monitor_heart:"),
        st.Page("views/analyst_workbench.py", title="Analyst workbench", icon=":material/query_stats:"),
        st.Page("views/about.py", title="Architecture & evidence", icon=":material/account_tree:"),
    ],
}
navigation = st.navigation(pages)

with st.sidebar:
    st.markdown(
        '<div class="brand"><svg viewBox="0 0 32 36" aria-hidden="true"><path d="M3 33 11 3h10l8 30" fill="none" '
        'stroke="#4bdcd5" stroke-width="2.5"/><path d="M16 5v6m0 5v6m0 5v6" stroke="#a5dfe5" stroke-width="2"/>'
        '</svg>corridor</div><p class="brand-subtitle">Customer, pricing &amp; transportation decision intelligence</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="sidebar-note"><strong>October 2025 plan</strong><br>Decision date {manifest["decision_date"]}'
        f'<br>Release {manifest["release_id"][:10]}<small>Synthetic customers, zones and rates. Real public weather, '
        "holiday and exchange-rate context.</small></div>",
        unsafe_allow_html=True,
    )

st.markdown(
    '<div class="masthead"><span>Corridor / Planning workspace · v1.0</span>'
    '<span class="status"><span class="status-dot"></span>Verified snapshot · local simulation</span></div>',
    unsafe_allow_html=True,
)
navigation.run()
footer()

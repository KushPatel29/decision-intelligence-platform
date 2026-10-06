"""Analyst workbench: five ad-hoc business questions, each SQL -> table -> chart -> conclusion."""

import html

import plotly.graph_objects as go
import streamlit as st

from decision_platform.ui import SERIES, callout, chart, page_header
from decision_platform.webapp import doc, download, table

page_header(
    "Analyst workbench",
    "The questions a decision-science team gets on a Tuesday afternoon, answered with window-function SQL "
    "against the marts, a chart and a three-sentence conclusion computed from the result.",
    eyebrow="Operate",
)
cases = doc("adhoc")
name = st.selectbox("Business question", list(cases), format_func=lambda key: cases[key]["question"])
case = cases[name]
frame = table(f"adhoc_{name}")
callout(html.escape(case["conclusion"]))
x, y = case["chart"]
left, right = st.columns([1.2, 1])
with left:
    fig = go.Figure(
        go.Bar(
            x=frame[x].astype(str),
            y=frame[y],
            marker_color=SERIES[0],
            hovertemplate="%{x}<br>%{y:,.3f}<extra></extra>",
        )
    )
    fig.update_xaxes(type="category")
    fig.update_yaxes(title=y.replace("_", " ").capitalize())
    chart(fig, 360, legend=False)
with right:
    st.dataframe(frame, hide_index=True, width="stretch")
    download(frame, f"{name}.csv")
st.code(case["sql"], language="sql")
st.caption("DuckDB SQL over the silver tables and gold marts; the same file ships under adhoc/ in the repository.")

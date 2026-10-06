"""Run: .venv/Scripts/python -m streamlit run app.py

Read-only analytics, bounded local solves and durable reviewed plans. No automatic cloud writes.
"""
import html
import os
from importlib.util import find_spec
import json
import pandas as pd
import streamlit as st
from decision_platform.config import ROOT
from decision_platform.optimization import solve
from decision_platform.ui import CSS,chart,line,bars,corridor,campaign_deck,resource_ledger,offer_mix,COLORS
from decision_platform.planning import SCENARIO_TEMPLATES,plan_capacity
from decision_platform.runtime import validate_release,audit_event,saved_plans
from decision_platform.access import require_access
import plotly.graph_objects as go

st.set_page_config(page_title="Corridor | Decision intelligence",page_icon="🛣️",layout="wide")
st.markdown(CSS,unsafe_allow_html=True)
owner=require_access(st)

@st.cache_data
def load_outputs(stamp):
    folder=ROOT/"outputs"
    return json.loads((folder/"dashboard_data.json").read_text(encoding="utf-8"))

@st.cache_data
def read_csv(name,stamp):
    return pd.read_csv(ROOT/"outputs"/name)

def money(value):return f"${value:,.2f}"
def metrics(values):
    for column,(label,value) in zip(st.columns(len(values)),values):column.metric(label,value)

def download(frame,name,label="Download CSV"):
    st.download_button(label,frame.to_csv(index=False).encode(),file_name=name,mime="text/csv",key="download_"+name)

def as_frame(key):return pd.DataFrame(data[key])

def apply_scenario_template():
    for key,value in SCENARIO_TEMPLATES[st.session_state["scenario_template"]].items():
        st.session_state["scenario_"+key]=value

PAGE_DESCRIPTIONS={
    "Customer intelligence":"Find the customer groups, retention risks and projected value behind the next campaign.",
    "Pricing":"Compare demand and revenue under alternative effective prices for each travel period.",
    "Promotions":"Review the promotion contacts selected by the shared campaign optimizer.",
    "Loyalty":"Inspect reward allocation, expected contribution and the reconciled points ledger.",
    "Transportation":"Explore forecast demand, campaign additions and capacity protected by the safety reserve.",
    "Experiments":"Review randomized treatment effects and the evidence behind offer rankings.",
    "Policy lab":"Compare feasible targeting approaches and spending levels before choosing a plan.",
    "Model operations":"Review held-out quality, calibration, drift and versioned model candidates.",
    "Analyst workbench":"Explore a business question, its data, chart, SQL and interpretation in one place.",
    "Evidence & delivery":"Export the evidence and inspect verified delivery status and external dependencies.",
}

file=ROOT/"outputs"/"dashboard_data.json"
try:
    release=validate_release(ROOT)
    if os.environ.get("CORRIDOR_ENV")=="production":
        gate=json.loads((ROOT/"outputs/quality_gate.json").read_text())
        if release["status"]!="verified" or not gate["passed"]:raise ValueError("Production model acceptance or integrity failed")
except (ValueError,OSError,json.JSONDecodeError):
    st.title("Corridor")
    st.error("Decision data is refreshing, incomplete or has failed its integrity check. Restore a verified release or finish the pipeline run before continuing.")
    st.stop()
if not file.exists():
    st.title("Corridor")
    st.info("Run the local demo pipeline to create the data used by this app.")
    st.code("python -m decision_platform.cli demo --solver gurobi")
    st.stop()
stamp=file.stat().st_mtime_ns
try:
    data=load_outputs(stamp)
    required={"customers","decisions","capacity","zones","optimization","metrics","experiment","monitoring","monthly","segments","scenarios"}
    if not isinstance(data,dict) or not required.issubset(data):raise ValueError("Incomplete dashboard contract")
except (ValueError,OSError,json.JSONDecodeError):
    st.error("This release has an invalid dashboard data contract. Restore or regenerate a complete release.");st.stop()
customers=as_frame("customers");decisions=as_frame("decisions");capacity=as_frame("capacity")
zone_names={z["zone_id"]:z["zone_name"] for z in data["zones"]}
st.sidebar.markdown('<div class="brand"><svg viewBox="0 0 32 36" aria-hidden="true"><path d="M3 33 11 3h10l8 30" fill="none" stroke="#4bdcd5" stroke-width="2.5"/><path d="M16 5v6m0 5v6m0 5v6" stroke="#a5dfe5" stroke-width="2"/></svg>corridor</div><p class="brand-subtitle">Customer, pricing &amp; transportation<br>Decision intelligence</p>',unsafe_allow_html=True)
page=st.sidebar.radio("Decision area",["Decision centre","Customer intelligence","Pricing","Promotions","Loyalty","Transportation","Experiments","Policy lab","Model operations","Operations centre","Analyst workbench","Evidence & delivery"],label_visibility="collapsed")
st.sidebar.markdown(f'<div class="sidebar-note"><strong>October 2025</strong><br>Synthetic planning window<br>{len(customers):,} customers / {len(zone_names)} zones<small>Invented customers, zones and rates. Public weather, calendar and currency context.</small></div>',unsafe_allow_html=True)
st.markdown('<div class="masthead"><span class="location">Corridor / Planning workspace<span class="version">v0.4</span></span><span class="status"><span class="status-dot"></span>Local simulation / Oct 2025</span></div>',unsafe_allow_html=True)
st.title(page)
if page in PAGE_DESCRIPTIONS:st.markdown(f'<p class="page-description">{PAGE_DESCRIPTIONS[page]}</p>',unsafe_allow_html=True)

if page=="Decision centre":
    combined=data["optimization"]["combined"]
    joint=data["optimization"]["joint"]
    campaign_deck(capacity,zone_names,combined,joint["customer_count"],joint["solver"])
    st.caption("Expected synthetic outcomes in CAD. Dedicated randomized promotion and loyalty groups inform the plan; real business impact has not been measured.")
    overview,studio,evidence=st.tabs(["Overview","Scenario studio","Decision evidence"])
    with overview:
        left,right=st.columns([1.45,1])
        with left:
            st.subheader("Historical trip activity")
            monthly=as_frame("monthly")
            line(monthly,"month",["trips"],height=280,fill=True)
            st.caption("Monthly travel before the October decision date. Forward observations are reserved for labels and later evaluation.")
        with right:
            st.subheader("Campaign guardrails")
            resource_ledger([
                ("Incentive budget",combined["spend"],combined["budget"],f"{money(combined['spend'])} / {money(combined['budget'])}",f"{money(combined['budget']-combined['spend'])} remains unallocated"),
                ("Contact limit",combined["contacts"],180,f"{combined['contacts']:,} / 180","One offer per selected customer"),
                ("Reward points",combined["points_awarded"],35000,f"{combined['points_awarded']:,} / 35,000","Full reward liability is included in incentive costs"),
            ],"Budget, contact, eligibility, inventory, ROI, points and capacity checks passed." if combined["all_constraints_passed"] else "Review the saved allocation checks before using this plan.")
        left,right=st.columns([1,1.45])
        with left:
            st.subheader("Offer mix")
            offer_mix(decisions)
            st.caption("Bar length shows each offer's share of selected contacts.")
        with right:
            st.subheader("Capacity by travel period")
            grid=capacity.assign(zone=capacity.zone_id.map(zone_names)).pivot(index="zone",columns="period",values="final_utilization").reindex(list(zone_names.values()))
            fig=go.Figure(go.Heatmap(z=grid.to_numpy()*100,x=grid.columns,y=grid.index,
                colorscale=[[0,"#102437"],[.65,"#4bdcd5"],[1,"#ffc773"]],zmin=0,zmax=100,
                text=grid.to_numpy()*100,texttemplate="%{text:.0f}%",showscale=False,
                hovertemplate="%{y} / %{x}<br>%{z:.1f}% forecast load<extra></extra>"))
            fig.update_layout(hovermode="closest");chart(fig,290)
            st.caption("Forecast plus campaign trips, divided by capacity. The reserve is protected separately; the zones are schematic.")
    with studio:
        st.subheader("Build a decision scenario")
        st.caption("Choose a starting template, adjust its limits and optimize the joint shortlist. Each result is compared with the saved baseline above.")
        st.selectbox("Start from a template",list(SCENARIO_TEMPLATES),key="scenario_template",on_change=apply_scenario_template,
            help="Changing the template replaces the controls below. You can edit every limit before solving.")
        for key,value in SCENARIO_TEMPLATES[st.session_state["scenario_template"]].items():
            st.session_state.setdefault("scenario_"+key,value)
        with st.form("campaign_scenario"):
            c1,c2,c3,c4=st.columns(4)
            budget=c1.number_input("Budget (CAD)",min_value=0.,max_value=50000.,step=100.,key="scenario_budget")
            limit=c2.number_input("Maximum contacts",min_value=0,max_value=600,step=10,key="scenario_limit")
            roi=c3.number_input("Minimum net ROI",min_value=0.,max_value=5.,step=.05,key="scenario_roi",help="Net contribution divided by incentive costs, enforced for the whole selected portfolio.")
            solver_options=["Gurobi","HiGHS"] if find_spec("gurobipy") is not None else ["HiGHS"]
            solver=c4.selectbox("Solver",solver_options,help="HiGHS works without a commercial solver license. Gurobi appears when its package is installed.")
            c5,c6=st.columns(2)
            points=c5.number_input("Maximum reward points",min_value=0,max_value=100000,step=5000,key="scenario_points")
            reserve=c6.slider("Capacity safety reserve",min_value=0.,max_value=.5,step=.05,format="%.2f",key="scenario_reserve",help="Protect this fraction of baseline forecast demand in every zone and travel period.")
            submitted=st.form_submit_button("Optimize campaign",type="primary",width="stretch")
        if submitted:
            try:
                candidates=read_csv("joint_candidates.csv",stamp)
                base=plan_capacity(capacity,decisions.iloc[:0],reserve)
                with st.spinner("Finding a feasible campaign allocation…"):
                    allocation=solve(candidates,base,float(budget),int(limit),float(roi),"gurobi" if solver=="Gurobi" else "highs",points_budget=int(points))
                st.session_state["scenario"]={"frame":allocation.selected,"diagnostics":allocation.diagnostics,"solver":allocation.solver,"status":allocation.status,
                    "budget":budget,"limit":limit,"roi":roi,"points_limit":points,"reserve":reserve,"data_stamp":stamp}
                st.session_state.setdefault("scenario_history",[]).append({"scenario":f"Plan {len(st.session_state.get('scenario_history',[]))+1}","budget":budget,"contacts":len(allocation.selected),"spend":allocation.diagnostics['spend'],"net_contribution":allocation.diagnostics['net_contribution'],"incremental_trips":allocation.diagnostics['incremental_trips'],"points_limit":points,"points_awarded":int(allocation.selected.points.sum()),"reserve":reserve})
                st.session_state["scenario_history"]=st.session_state["scenario_history"][-20:]
                audit_event(ROOT,owner,"solve_campaign",{"release_id":release["release_id"],"solver":allocation.solver,"limits":{"budget":budget,"contacts":limit,"roi":roi,"points":points,"reserve":reserve},"diagnostics":allocation.diagnostics})
            except Exception as exc:
                st.error(f"Scenario did not finish: {exc}")
                st.caption("Check the solver license or choose HiGHS. If forecast plus reserve exceeds capacity, reduce the reserve and solve again.")
        scenario=st.session_state.get("scenario")
        if scenario and scenario["data_stamp"]==stamp:
            st.subheader("Scenario result")
            d=scenario["diagnostics"];view=scenario["frame"]
            st.caption(f"{scenario['solver']}: {scenario['status']}. Changes below compare this result with the saved baseline, not with the previous scenario.")
            columns=st.columns(4)
            values=[("Contacts",f"{len(view):,}",f"{len(view)-combined['contacts']:+,} vs baseline","normal"),
                ("Expected spend",money(d['spend']),f"{d['spend']-combined['spend']:+,.2f} CAD vs baseline","inverse"),
                ("Expected net contribution",money(d['net_contribution']),f"{d['net_contribution']-combined['net_contribution']:+,.2f} CAD vs baseline","normal"),
                ("Expected additional trips",f"{d['incremental_trips']:.1f}",f"{d['incremental_trips']-combined['incremental_trips']:+.1f} vs baseline","normal")]
            for column,(label,value,delta,color) in zip(columns,values):column.metric(label,value,delta=delta,delta_color=color)
            if d["all_constraints_passed"]:st.success("All implemented budget, contact, eligibility, inventory, ROI, points and capacity constraints passed.")
            if view.empty:st.info("No contacts were selected under these limits. Increase the budget or relax a limit to explore another feasible plan.")
            left,right=st.columns(2)
            with left:
                st.subheader("Scenario offer mix")
                offer_mix(view)
            with right:
                st.subheader("Scenario resource use")
                resource_ledger([
                    ("Incentive budget",d["spend"],scenario["budget"],f"{money(d['spend'])} / {money(scenario['budget'])}",f"{money(scenario['budget']-d['spend'])} remains unallocated"),
                    ("Reward points",int(view.points.sum()),scenario["points_limit"],f"{int(view.points.sum()):,} / {scenario['points_limit']:,}",f"Capacity reserve: {scenario['reserve']:.0%} of baseline demand"),
                ])
            with st.expander("Scenario capacity and selected contacts",expanded=False):
                result_capacity=plan_capacity(capacity,view,scenario["reserve"])
                st.markdown(corridor(result_capacity,zone_names),unsafe_allow_html=True)
                st.caption("Capacity load and headroom for this scenario's allocation and reserve.")
                st.dataframe(view[["customer_id","offer_name","zone_id","incremental_trips","cost","net_contribution"]],hide_index=True,width="stretch",
                    column_config={"incremental_trips":st.column_config.NumberColumn("Additional trips",format="%.2f"),"cost":st.column_config.NumberColumn("Cost (CAD)",format="$%.2f"),"net_contribution":st.column_config.NumberColumn("Net contribution (CAD)",format="$%.2f")})
            download(view,"scenario_allocation.csv","Download scenario allocation")
            st.download_button("Download decision summary",json.dumps({"data_kind":"synthetic planning outcomes","solver":scenario["solver"],"status":scenario["status"],"limits":{k:scenario[k] for k in ["budget","limit","roi","points_limit","reserve"]},"outcomes":d},indent=2),file_name="scenario_summary.json",mime="application/json")
            if st.button("Save reviewed scenario"):
                identifier=audit_event(ROOT,owner,"save_plan",{"release_id":release["release_id"],"solver":scenario["solver"],"limits":{k:scenario[k] for k in ["budget","limit","roi","points_limit","reserve"]},"outcomes":d,"allocation":json.loads(view.to_json(orient="records"))})
                st.success(f"Scenario saved with audit reference {identifier[:12]}.")
            st.subheader("Scenario comparison")
            history=pd.DataFrame(st.session_state["scenario_history"])
            st.dataframe(history,hide_index=True,width="stretch",column_config={"budget":st.column_config.NumberColumn("Budget (CAD)",format="$%.0f"),"spend":st.column_config.NumberColumn("Spent (CAD)",format="$%.2f"),"net_contribution":st.column_config.NumberColumn("Net contribution (CAD)",format="$%.2f"),"incremental_trips":st.column_config.NumberColumn("Additional trips",format="%.1f"),"reserve":st.column_config.NumberColumn("Demand reserve",format="percent")})
            download(history,"scenario_comparison.csv")
        else:
            st.caption("Your solved plans will appear here with baseline comparisons and downloadable allocations.")
        with st.expander("My saved scenarios"):
            plans=saved_plans(ROOT,owner)
            if plans:
                st.dataframe(pd.DataFrame([{k:v for k,v in p.items() if k!="allocation"} for p in plans]),hide_index=True,width="stretch")
                st.download_button("Download saved scenario archive",json.dumps(plans,indent=2),"saved_scenarios.json","application/json")
            else:st.caption("Save a reviewed scenario to keep its limits, allocation and release identity across sessions.")
    with evidence:
        st.subheader("Saved allocation checks")
        st.dataframe(pd.DataFrame({"Constraint":["Shared campaign budget","One contact per customer","Customer eligibility","Offer inventory","Reward points","Zone capacity including reserve","Solver status"],
            "Result":[f"{money(combined['spend'])} / {money(combined['budget'])}","Passed","Passed","Passed",f"{combined['points_awarded']:,} / 35,000","Passed",f"{joint['solver']}: {joint['status']}"]}),hide_index=True,width="stretch")
        st.caption(data["optimization"]["scope"])
        st.subheader("Planning assumptions")
        st.write(data["optimization"]["economics"])
        st.caption(data["metrics"]["demand"]["decision_forecast"])
        download(decisions,"baseline_allocation.csv","Download saved baseline")

elif page=="Customer intelligence":
    metrics([("Synthetic customers",f"{len(customers):,}"),("Average projected value",money(customers.clv_12m.mean())),("Inactivity risk >50%",str((customers.churn_probability>.5).sum())),("Anomaly review flags",str(customers.anomaly_flag.sum()))])
    st.subheader("Segments and value")
    segments=as_frame("segments")
    left,right=st.columns(2)
    with left:
        ranked=segments.sort_values("customers")
        fig=go.Figure(go.Bar(x=ranked.customers,y=ranked.rfm_segment,orientation="h",marker_color=COLORS[0],
            text=ranked.customers,textposition="outside",hovertemplate="%{y}<br>%{x:,} customers<extra></extra>"))
        fig.update_xaxes(title="Customers",range=[0,max(1,ranked.customers.max())*1.18]);fig.update_layout(hovermode="closest");chart(fig,310)
    right.dataframe(segments,hide_index=True,width="stretch",column_config={
        "rfm_segment":st.column_config.TextColumn("Segment"),"customers":st.column_config.NumberColumn("Customers",format="localized"),
        "clv":st.column_config.NumberColumn("Average value (CAD)",format="$%.2f"),
        "propensity":st.column_config.ProgressColumn("Travel propensity",min_value=0,max_value=1,format="percent"),
        "churn":st.column_config.ProgressColumn("Inactivity risk",min_value=0,max_value=1,format="percent"),
        "digital":st.column_config.NumberColumn("Digital engagements",format="%.1f")})
    with st.expander("Value and retention landscape"):
        fig=go.Figure()
        for i,(name,group) in enumerate(customers.groupby("rfm_segment")):
            group=group[group.churn_probability.notna()]
            fig.add_trace(go.Scattergl(x=group.churn_probability*100,y=group.clv_12m,mode="markers",name=name,marker=dict(size=5,opacity=.6,color=COLORS[i%len(COLORS)]),text=group.customer_id,hovertemplate="%{text}<br>Inactivity risk %{x:.1f}%<br>Projected value CAD %{y:,.0f}<extra>%{fullData.name}</extra>"))
        fig.update_xaxes(title="90-day inactivity risk (%)");fig.update_yaxes(title="Projected 12-month contribution (CAD)");chart(fig,400)
    st.subheader("Customer workbench")
    options=["All"]+sorted(customers.rfm_segment.unique())
    segment=st.selectbox("Segment",options)
    selected=customers if segment=="All" else customers[customers.rfm_segment==segment]
    text=st.text_input("Customer ID contains")
    if text:selected=selected[selected.customer_id.str.contains(text,case=False,regex=False)]
    cols=["customer_id","rfm_segment","cluster","trips_30d","recency_days","propensity_probability","churn_probability","attrition_probability","clv_12m","eligible"]
    st.dataframe(selected[cols],hide_index=True,width="stretch",column_config={
        "clv_12m":st.column_config.NumberColumn("Projected value (CAD)",format="$%.2f"),
        "propensity_probability":st.column_config.ProgressColumn("Travel propensity",min_value=0,max_value=1,format="percent"),
        "churn_probability":st.column_config.ProgressColumn("Inactivity risk",min_value=0,max_value=1,format="percent"),
        "attrition_probability":st.column_config.ProgressColumn("Attrition risk",min_value=0,max_value=1,format="percent")})
    st.caption("Inactivity and attrition apply to historically active customers. Projected value uses an ML contribution forecast; the separate BG/NBD benchmark is available in Model operations. Twelve-month forecasts remain assumptions.")
    download(selected,"filtered_customer_360.csv")
    with st.expander("Customer profile: rewards, consent and campaign history"):
        if selected.empty:st.info("No customer matches these filters.")
        else:
            customer_id=st.selectbox("Inspect customer",selected.customer_id.head(500).tolist())
            profile=selected[selected.customer_id.eq(customer_id)].iloc[0]
            fields=[c for c in ["customer_id","tier","points_balance","points_earned","points_awarded","points_redeemed","marketing_consent","account_status","campaign_exposures","campaign_enrollments","campaign_redemptions","engaged_days_30d","home_zone_elasticity","loyalty_500_redemption_probability"] if c in selected]
            st.dataframe(pd.DataFrame({"Field":fields,"Value":[str(profile[c]) for c in fields]}),hide_index=True,width="stretch")

elif page=="Pricing":
    scenarios=as_frame("scenarios")
    left,right=st.columns(2)
    zone=left.selectbox("Zone",list(zone_names),format_func=lambda z:zone_names[z])
    period=right.selectbox("Travel period",["Off-peak","Weekend","Peak"])
    current=scenarios[(scenarios.zone_id==zone)&(scenarios.period==period)].copy()
    change=st.select_slider("Effective price change",options=[-.3,-.2,-.1,0.,.05,.1],value=0.,format_func=lambda v:f"{v:+.0%}" if v else "Baseline")
    row=current[current.price_change==change].iloc[0]
    metrics([("Estimated elasticity",f"{row.elasticity:.2f}"),("Demand index",f"{row.demand_index:.1f}"),("Revenue index",f"{row.revenue_index:.1f}")])
    current["Price change (%)"]=current.price_change*100
    fig=go.Figure()
    for i,key in enumerate(["demand_index","revenue_index"]):
        fig.add_trace(go.Scatter(x=current["Price change (%)"],y=current[key],name=key.replace("_"," ").title(),mode="lines+markers",
            line=dict(color=COLORS[i],width=2.5),marker=dict(size=[11 if value==change else 5 for value in current.price_change]),hovertemplate="%{y:.1f}<extra>%{fullData.name}</extra>"))
    fig.add_hline(y=100,line_dash="dot",line_color="#789ab0")
    fig.add_vline(x=change*100,line_dash="dot",line_color="#ffc773")
    fig.update_xaxes(title="Effective price change (%)");fig.update_yaxes(title="Index / baseline = 100")
    chart(fig,370)
    st.caption(f"Selected price change: {change:+.0%}. Demand {row.demand_index-100:+.1f}% and revenue {row.revenue_index-100:+.1f}% versus baseline under the fitted elasticity assumption.")
    st.dataframe(current,hide_index=True,width="stretch")
    st.caption("Index 100 equals baseline. Extrapolation assumes constant log-log elasticity in this price range. This does not estimate or optimize actual 407 ETR tariffs.")
    download(current,"price_scenarios.csv")
    if (ROOT/"outputs/price_options.csv").exists():
        st.subheader("Optimize prices and campaign capacity together")
        st.caption("Choose one effective price per zone and period while sharing capacity with campaign contacts. Promotion effects are held at baseline prices; price/offer interactions remain an assumption.")
        with st.form("joint_price_plan"):
            surplus=st.slider("Consumer surplus weight",0.,1.,0.,.1,help="Trade contribution against illustrative customer surplus. Zero maximizes the stated economic objective.")
            run_price=st.form_submit_button("Optimize price strategies",type="primary")
        if run_price:
            try:
                from decision_platform.pricing import optimize_prices
                options=read_csv("price_options.csv",stamp)
                chosen,contacts,receipt=optimize_prices(options,read_csv("joint_candidates.csv",stamp),solver="auto",surplus_weight=surplus)
                st.session_state["price_plan"]=(stamp,chosen,contacts,receipt)
                audit_event(ROOT,owner,"solve_prices",{"release_id":release["release_id"],**receipt})
            except Exception as exc:st.error(f"Price optimization could not complete: {exc}")
        saved=st.session_state.get("price_plan")
        if saved and saved[0]==stamp:_,chosen,contacts,receipt=saved
        else:
            chosen=read_csv("price_allocation.csv",stamp);contacts=read_csv("price_campaign_allocation.csv",stamp);receipt=json.loads((ROOT/"outputs/price_optimization.json").read_text())
        metrics([("Price contribution change",money(receipt["price_contribution"])),("Campaign contribution",money(receipt["campaign_net_contribution"])),("Campaign contacts",str(receipt["contacts"]))])
        st.dataframe(chosen[["zone_id","period","price_change","forecast_trips","campaign_trips","remaining_with_reserve","incremental_contribution","consumer_surplus_change"]],hide_index=True,width="stretch")
        st.caption(receipt["assumptions"])
        download(chosen,"optimized_prices.csv");download(contacts,"joint_price_campaign.csv")

elif page in ["Promotions","Loyalty"]:
    is_loyalty=page=="Loyalty"
    frame=decisions[decisions.offer_id.eq("loyalty_500") if is_loyalty else ~decisions.offer_id.eq("loyalty_500")].copy()
    metrics([("Selected customers",str(len(frame))),("Expected additional trips",f"{frame.incremental_trips.sum():,.1f}"),("Expected incentive costs",money(frame.cost.sum())),("Expected net contribution",money(frame.net_contribution.sum()))])
    if is_loyalty:
        st.info("Reward effects are estimated from the dedicated 500-point randomized group. Each award reserves $5 in reward liability plus $0.35 contact cost. This remains synthetic trial evidence.")
        st.metric("Points allocated",f"{int(frame.points.sum()):,}")
        ledger=ROOT/"outputs"/"loyalty_ledger.csv"
        if ledger.exists():
            with st.expander("Reward ledger and balance reconciliation"):
                accounting=json.loads((ROOT/"outputs"/"loyalty_accounting.json").read_text())
                metrics([("Points earned",f"{accounting['points_earned']:,}"),("Points redeemed",f"{accounting['points_redeemed']:,}"),("Balance",f"{accounting['points_balance']:,}")])
                download(read_csv("loyalty_ledger.csv",stamp),"loyalty_ledger.csv")
    else:
        st.info("Expected discount costs include baseline trips. Trip effects are shrunk by 25% as an explicit planning assumption, not a statistical confidence bound.")
    segment=st.multiselect("Segments",sorted(frame.rfm_segment.unique()),default=sorted(frame.rfm_segment.unique()))
    frame=frame[frame.rfm_segment.isin(segment)]
    frame["zone"]=frame.zone_id.map(zone_names)
    st.dataframe(frame[["customer_id","offer_name","zone","rfm_segment","incremental_trips","cost","net_contribution"]],hide_index=True,width="stretch",column_config={
        "incremental_trips":st.column_config.NumberColumn("Additional trips",format="%.2f"),"cost":st.column_config.NumberColumn("Cost (CAD)",format="$%.2f"),"net_contribution":st.column_config.NumberColumn("Net contribution (CAD)",format="$%.2f")})
    download(frame,"loyalty_filtered.csv" if is_loyalty else "promotions_filtered.csv")

elif page=="Transportation":
    capacity["zone"]=capacity.zone_id.map(zone_names)
    period=st.selectbox("Travel period",["All","Off-peak","Peak","Weekend"])
    view=capacity if period=="All" else capacity[capacity.period==period]
    metrics([("Weighted forecast load",f"{(view.baseline_forecast.sum()+view.allocated_trips.sum())/view.capacity_trips.sum():.1%}"),
        ("Headroom after reserve",f"{view.remaining_with_reserve.sum():,.0f} trips"),("Campaign additions",f"{view.allocated_trips.sum():,.1f} trips")])
    overview,details=st.tabs(["Capacity overview","Cell details"])
    with overview:
        left,right=st.columns([1.25,1])
        with left:
            st.subheader("Demand and protected capacity")
            totals=view.groupby("zone")[["baseline_forecast","allocated_trips","reserve_trips","capacity_trips"]].sum().reindex(list(zone_names.values())).reset_index()
            fig=go.Figure()
            for label,key,color in [("Baseline demand","baseline_forecast",COLORS[1]),("Campaign additions","allocated_trips",COLORS[0]),("Safety reserve","reserve_trips",COLORS[2])]:
                fig.add_trace(go.Bar(x=totals.zone,y=totals[key],name=label,marker_color=color,hovertemplate="%{y:,.1f} trips<extra>%{fullData.name}</extra>"))
            fig.add_trace(go.Scatter(x=totals.zone,y=totals.capacity_trips,name="Planning capacity",mode="markers",marker=dict(symbol="line-ew",size=18,color="#d6eaf2",line=dict(width=2,color="#d6eaf2")),hovertemplate="%{y:,.0f} trips<extra>Capacity</extra>"))
            fig.update_layout(barmode="stack",legend=dict(y=1.2));fig.update_yaxes(title="Trips over the planning window");chart(fig,380)
        with right:
            st.subheader("Forecast load by period")
            grid=view.pivot(index="zone",columns="period",values="final_utilization").reindex(list(zone_names.values()))
            fig=go.Figure(go.Heatmap(z=grid.to_numpy()*100,x=grid.columns,y=grid.index,colorscale=[[0,"#102437"],[.65,"#4bdcd5"],[1,"#ffc773"]],zmin=0,zmax=100,text=grid.to_numpy()*100,texttemplate="%{text:.0f}%",hovertemplate="%{y} / %{x}<br>%{z:.1f}% utilization<extra></extra>",showscale=False))
            fig.update_layout(hovermode="closest");chart(fig,380)
    with details:
        st.dataframe(view[["zone","period","baseline_forecast","allocated_trips","reserve_trips","capacity_trips","final_utilization","remaining_with_reserve"]],hide_index=True,width="stretch",column_config={
            "final_utilization":st.column_config.ProgressColumn("Forecast load",min_value=0,max_value=1,format="percent"),"remaining_with_reserve":st.column_config.NumberColumn("Trips free after reserve",format="%.1f")})
    st.caption(data["metrics"]["demand"]["decision_forecast"])
    if (ROOT/"outputs/demand_horizon_metrics.json").exists():
        with st.expander("30-day backtests and hourly demand"):
            horizon=json.loads((ROOT/"outputs/demand_horizon_metrics.json").read_text())
            metrics([("Monthly-horizon MAE",f"{horizon['test_mae']:.2f}"),("90% interval coverage",f"{horizon['test_interval_coverage']:.1%}"),("Test origins",str(horizon['test_origins']))])
            hourly=read_csv("zone_hour_forecast.csv",stamp)
            profile=hourly.groupby(["hour","direction"]).forecast_trips.sum().unstack(fill_value=0).reset_index()
            line(profile,"hour",[c for c in profile if c!="hour"])
            st.caption("Hour/direction values use pre-cutoff travel shares to disaggregate the daily forecast; they are not independently validated hourly models.")
            download(hourly,"zone_hour_forecast.csv")
    download(view,"capacity_filtered.csv")

elif page=="Experiments":
    e=data["experiment"]
    metrics([("Control response",f"{e['control_conversion']:.1%}"),("Planned customers per arm",f"{e['required_per_arm']:,}"),("Actual minimum per arm",f"{min(e['actual_per_arm'].values()):,}"),("Planned sample target","Met" if e["powered_for_planned_mde"] else "Not met")])
    if not e["powered_for_planned_mde"]:st.warning("This simulated trial is below its planned sample-size target for a five-percentage-point effect. A non-significant result is not evidence of no effect.")
    rows=pd.DataFrame(e["results"])
    st.dataframe(rows[["arm","n","conversion","difference","relative_lift","ci_low","ci_high","p_adjusted"]],hide_index=True,width="stretch")
    st.caption("Customer randomization; intention-to-treat analysis; three treatment/control comparisons. Family alpha 5%, target power 80%. Intervals and p-values are Bonferroni adjusted.")
    fig=go.Figure(go.Scatter(x=rows.difference*100,y=rows.arm,mode="markers",marker=dict(size=11,color=COLORS[0]),error_x=dict(type="data",symmetric=False,array=(rows.ci_high-rows.difference)*100,arrayminus=(rows.difference-rows.ci_low)*100)))
    fig.add_vline(x=0,line_dash="dot",line_color="#9399ff");fig.update_xaxes(title="Response difference (percentage points)");chart(fig,250)
    st.subheader("Held-out causal ranking")
    lines=[]
    for offer in ["offpeak_15","weekend_20","loyalty_500"]:
        for learner in ["t_learner","s_learner","x_learner"]:
            curve=data["metrics"]["uplift"][offer][learner]
            lines.extend({"fraction":x,"gain":y,"series":offer+" "+learner} for x,y in zip(curve["fraction"],curve["gain"]))
    curves=pd.DataFrame(lines).pivot_table(index="fraction",columns="series",values="gain")
    line(curves.reset_index(),"fraction",list(curves.columns),height=400)
    st.caption("Gain is the inverse-propensity-weighted cumulative response effect per held-out customer; negative Qini remains visible. These models do not establish the value of the optimized policy.")
    download(rows.drop(columns=["incremental_trips_per_customer","incremental_net_contribution_per_customer"]),"experiment_results.csv")
    if e.get("subgroups"):
        with st.expander("Exploratory subgroup effects"):
            subgroup=pd.DataFrame(e["subgroups"])
            dimension=st.selectbox("Subgroup dimension",subgroup.dimension.unique())
            st.dataframe(subgroup[subgroup.dimension.eq(dimension)],hide_index=True,width="stretch")
            st.caption(e["subgroup_scope"]);download(subgroup,"experiment_subgroups.csv")

elif page=="Policy lab":
    comparison=read_csv("policy_comparison.csv",stamp)
    bars(comparison,"policy",["net_contribution"])
    st.dataframe(comparison,hide_index=True,width="stretch")
    st.caption("All methods share the same model-scored shortlist, budget, capacity, contact and inventory limits. Baseline rules require each contact to meet the ROI floor; the optimizer enforces portfolio ROI. This compares planning objectives, not observed causal policy gains.")
    st.subheader("Budget frontier")
    frontier=read_csv("budget_frontier.csv",stamp)
    line(frontier,"budget",["net_contribution","spend"])
    st.subheader("Held-out offer-rule evaluation")
    evidence=json.loads((ROOT/"outputs"/"policy_evaluation.json").read_text())
    metrics([("Incremental CAD / customer",money(evidence['incremental_contribution_per_customer'])),("95% interval",f"{evidence['ci_low']:.2f} to {evidence['ci_high']:.2f}"),("Untouched test customers",str(evidence['n_test']))])
    st.caption(evidence["interpretation"])
    download(comparison,"policy_comparison.csv")
    if (ROOT/"outputs/policy_trial_results.json").exists():
        st.subheader("Fresh constrained-policy experiment")
        trial=json.loads((ROOT/"outputs/policy_trial_results.json").read_text());effect=trial["incremental_net_contribution_per_customer"]
        metrics([("Policy / control customers",f"{trial['n_policy']:,} / {trial['n_control']:,}"),("Incremental CAD per customer",money(effect["difference"])),("95% interval",f"{effect['ci_low']:.2f} to {effect['ci_high']:.2f}")])
        st.caption(trial["assignment"]);st.caption(trial["limitations"])
        st.download_button("Download policy experiment evidence",json.dumps(trial,indent=2),"policy_trial_results.json","application/json")

elif page=="Operations centre":
    st.caption("Release integrity, acceptance gates and actionable batch reviews for the current planning dataset.")
    quality_path=ROOT/"outputs/quality_gate.json"
    quality=json.loads(quality_path.read_text()) if quality_path.exists() else {"passed":False,"checks":[]}
    alerts=data["monitoring"].get("alerts",[])
    metrics([("Release integrity",release["status"].title()),("Model acceptance","Passed" if quality["passed"] else "Review required"),("Batch review alerts",str(len(alerts)))])
    st.caption("Release identity: "+release["release_id"][:20])
    st.subheader("Model acceptance criteria")
    st.dataframe(pd.DataFrame(quality["checks"]),hide_index=True,width="stretch")
    if quality["passed"]:st.success("The implemented local model acceptance checks passed.")
    else:st.warning("One or more model acceptance checks need review. This release remains a planning simulation.")
    st.subheader("Review queue")
    if alerts:st.dataframe(pd.DataFrame(alerts),hide_index=True,width="stretch")
    else:st.info("No batch thresholds are currently exceeded.")
    st.caption("Review alerts with calendar, upstream freshness and matured outcomes. Retraining and deployment require validation and a recorded promotion decision.")
    with st.expander("Prediction, volume and campaign checks"):
        for key in ["prediction_drift","volume_checks","campaign_checks"]:
            st.write(key.replace("_"," ").title());st.dataframe(pd.DataFrame(data["monitoring"].get(key,[])),hide_index=True,width="stretch")
    readiness=ROOT/"outputs/readiness.json"
    if readiness.exists():
        st.subheader("Deployment readiness")
        value=json.loads(readiness.read_text());st.dataframe(pd.DataFrame(value["checks"]),hide_index=True,width="stretch")
        st.caption(value["scope"])

elif page=="Analyst workbench":
    from decision_platform.adhoc import CASES
    name=st.selectbox("Business question",list(CASES),format_func=lambda key:CASES[key][0])
    frame=read_csv("adhoc/"+name+".csv",stamp)
    first=frame.columns[0];numeric=frame.select_dtypes("number").columns.tolist()
    if first in numeric:numeric.remove(first)
    metric=st.selectbox("Measure",numeric)
    bars(frame,first,[metric]);st.dataframe(frame,hide_index=True,width="stretch")
    findings=(ROOT/"outputs/adhoc/findings.md").read_text()
    question=CASES[name][0];section=findings.split("## "+question,1)[-1].split("\n## ",1)[0]
    st.code(CASES[name][1],language="sql")
    st.write(section.strip().split("\n\n")[-1].strip())
    download(frame,name+".csv")

elif page=="Evidence & delivery":
    delivery=ROOT/"outputs"/"delivery_status.json"
    statuses=json.loads(delivery.read_text()) if delivery.exists() else []
    for item in statuses:
        pending="pending" in item["status"].lower()
        st.markdown(f'<div class="delivery {"pending" if pending else ""}"><span class="delivery-status">{html.escape(item["status"])}</span><strong>{html.escape(item["name"])}</strong><p>{html.escape(item["detail"])}</p></div>',unsafe_allow_html=True)
    for path,label,mime in [(ROOT/"output"/"pdf"/"executive_brief.pdf","Executive brief (PDF)","application/pdf"),(ROOT/"outputs"/"executive_brief.md","Executive brief (text)","text/markdown"),(ROOT/"outputs"/"summary.json","Run summary","application/json")]:
        if path.exists():st.download_button(label,path.read_bytes(),file_name=path.name,mime=mime)
    st.caption("Hosted execution is marked complete only after a successful cloud run. Local credentials and simulator oracle files are excluded from delivery exports.")

else:
    rows=[]
    for name in ["propensity","churn","attrition"]:
        m=data["metrics"]["customer"][name]
        rows.append({"model":name,"champion":m["champion"],**m["test_calibrated"]})
    st.subheader("Held-out predictive quality")
    st.dataframe(pd.DataFrame(rows),hide_index=True,width="stretch")
    st.caption("Purged chronological folds: train July 2024–January 2025; validation April 2025; test July 2025. Calibration fits the validation fold. The same customers may reappear across time, matching batch rescoring.")
    if (ROOT/"outputs/performance/propensity_predictions.csv").exists():
        with st.expander("Calibration: predicted chance versus observed travel"):
            performance=read_csv("performance/propensity_predictions.csv",stamp)
            performance["bin"]=pd.cut(performance.predicted_probability,bins=[i/10 for i in range(11)],include_lowest=True)
            calibration=performance.groupby("bin",observed=True).agg(predicted=("predicted_probability","mean"),observed=("target","mean"),customers=("target","size")).reset_index()
            fig=go.Figure(go.Scatter(x=calibration.predicted,y=calibration.observed,mode="lines+markers",name="July test",marker_color=COLORS[0],text=calibration.customers,hovertemplate="Predicted %{x:.1%}<br>Observed %{y:.1%}<br>%{text} customers<extra></extra>"))
            fig.add_trace(go.Scatter(x=[0,1],y=[0,1],mode="lines",name="Perfect calibration",line=dict(color=COLORS[1],dash="dot")));fig.update_xaxes(title="Predicted probability",tickformat=".0%");fig.update_yaxes(title="Observed proportion",tickformat=".0%");chart(fig)
    st.subheader("Feature drift review")
    drift=pd.DataFrame(data["monitoring"]["features"])
    st.dataframe(drift,hide_index=True,width="stretch")
    st.caption(data["monitoring"]["interpretation"])
    tracking=[]
    for path in sorted((ROOT/"outputs"/"models").glob("*.tracking.json")):
        m=json.loads(path.read_text());tracking.append({"model":path.name.replace(".tracking.json",""),**m})
    st.subheader("Local MLflow experiment tracking")
    st.dataframe(pd.DataFrame(tracking),hide_index=True,width="stretch")
    if (ROOT/"outputs/model_registry.json").exists():
        with st.expander("Registered candidates and reproducible scoring"):
            st.dataframe(pd.DataFrame(json.loads((ROOT/"outputs/model_registry.json").read_text())),hide_index=True,width="stretch")
            st.caption("Versioned in the local MLflow registry with Candidate aliases. Loaded predictions are checked against the saved calibrated model. Production champion approval is pending.")
    st.subheader("What shapes the travel prediction")
    if (ROOT/"outputs"/"shap_global.csv").exists():
        importance=read_csv("shap_global.csv",stamp).head(12)
        fig=go.Figure(go.Bar(x=importance.mean_absolute_shap,y=importance.feature,orientation="h",marker_color=COLORS[0]));fig.update_yaxes(autorange="reversed");chart(fig,420)
        st.caption("Mean absolute SHAP contribution to the uncalibrated travel model's log odds, on 300 sampled customers. Predictive explanations do not establish causes.")
    if (ROOT/"outputs"/"probabilistic_clv_metrics.json").exists():
        with st.expander("Probabilistic value and segment stability"):
            value=json.loads((ROOT/"outputs"/"probabilistic_clv_metrics.json").read_text())
            st.write(value["method"]);st.json(value["validation_90d_customer_days"]);st.caption(value["limitations"])
            st.write("Cluster bootstrap agreement",data["metrics"]["customer"]["segmentation"].get("bootstrap_adjusted_rand",[]))
    st.info("Cloud execution status and downloadable evidence are available in Evidence & delivery.")

st.divider()
st.caption("Synthetic portfolio system inspired by electronic toll-road decisions. No affiliation with 407 ETR. No real customer data or actual company toll rates. All figures are educational simulation outputs.")

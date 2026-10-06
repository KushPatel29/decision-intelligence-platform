
CASES = {
    "weekend_decline": (
        "Why did weekend traffic change in September?",
        "SELECT strftime(timestamp,'%Y-%m') AS month, count(*) AS trips, sum(final_charge) AS revenue FROM silver.fact_trip WHERE period='Weekend' AND timestamp >= '2025-07-01' AND timestamp < '2025-10-01' GROUP BY 1 ORDER BY 1",
    ),
    "segment_decline": (
        "Which customer segment shows the sharpest use decline?",
        "SELECT rfm_segment, avg(frequency_trend) AS frequency_ratio, count(*) AS customers FROM gold.customer_360 GROUP BY 1 ORDER BY 2",
    ),
    "cannibalization": (
        "Are discounts subsidizing baseline travel?",
        "SELECT arm, avg(trip_count) AS mean_trips, avg(incentive_cost) AS mean_subsidy, avg(net_contribution) AS mean_net_contribution FROM gold.campaign_performance GROUP BY 1 ORDER BY 1",
    ),
    "unused_capacity": (
        "Where is unused off-peak capacity?",
        "SELECT zone_id, available_trips, remaining_with_reserve FROM gold.zone_capacity WHERE period='Off-peak' ORDER BY available_trips DESC",
    ),
    "enrollment_vs_value": (
        "Does enrollment guarantee campaign value?",
        "SELECT arm, count(*) AS customers, avg(enrolled) AS enrollment_rate, avg(response) AS travel_response, avg(net_contribution) AS mean_net_contribution FROM gold.campaign_performance GROUP BY 1 ORDER BY 1",
    ),
}


def run_adhoc(cfg, db):
    folder = cfg.path("outputs", "adhoc")
    folder.mkdir(parents=True, exist_ok=True)
    notes = [
        "# Analyst workbench results",
        "Synthetic analysis. Historical window ends before the October decision date.",
    ]
    for name, (question, query) in CASES.items():
        frame = db.execute(query).df()
        frame.to_csv(folder / f"{name}.csv", index=False)
        cfg.path("adhoc", f"{name}.sql").write_text(query + ";\n", encoding="utf-8")
        if name == "weekend_decline":
            a, b = frame.iloc[-2], frame.iloc[-1]
            delta = (b.trips / a.trips - 1) * 100
            conclusion = f"Weekend trips changed by {delta:.1f}% from {a['month']} to {b['month']}. The comparison is descriptive and mixes weather, calendar and simulated customer inactivity. Use a day-normalized, weather-adjusted follow-up before attributing the change to a campaign."
        elif name == "segment_decline":
            row = frame.iloc[0]
            conclusion = f"The {row.rfm_segment} segment has the lowest current-to-prior frequency ratio, at {row.frequency_ratio:.2f}. Segment definitions themselves depend on recency, so this is not an independent causal finding. Investigate active customers with declining usage before selecting a retention intervention."
        elif name == "cannibalization":
            control = frame[frame.arm.eq("Control")].iloc[0]
            comparison = (
                frame[~frame.arm.eq("Control")].sort_values("mean_net_contribution", ascending=False).iloc[0]
            )
            conclusion = f"The best observed treatment mean is {comparison.arm}, with ${comparison.mean_net_contribution:.2f} net contribution per customer versus ${control.mean_net_contribution:.2f} in control. Incentive costs include baseline travel, so more trips need not mean better net economics. Inspect randomized difference intervals before claiming a profitable effect."
        elif name == "unused_capacity":
            row = frame.iloc[0]
            conclusion = f"Synthetic zone {int(row.zone_id)} has the most forecast off-peak headroom, at {row.available_trips:.1f} trips before campaigns. After proposed allocations and the safety reserve, it retains {row.remaining_with_reserve:.1f} trips of room. Use demand forecasts and engineering capacity validation together before increasing offer volume."
        else:
            row = frame[~frame.arm.eq("Control")].sort_values("enrollment_rate", ascending=False).iloc[0]
            conclusion = f"The highest observed enrollment rate is {row.enrollment_rate:.1%} for {row.arm}. Its mean net contribution is ${row.mean_net_contribution:.2f} per randomized customer, which requires comparison with control. Enrollment is an intermediate measure; optimize incremental net value instead."
        notes.extend([f"\n## {question}", frame.to_string(index=False), "\n" + conclusion])
    (folder / "findings.md").write_text("\n\n".join(notes), encoding="utf-8")

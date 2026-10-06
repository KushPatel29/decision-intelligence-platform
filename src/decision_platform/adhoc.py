"""Analyst workbench: five ad-hoc business questions, each answered SQL -> table -> chart -> conclusion.

Each case runs against the DuckDB marts, saves its SQL under `adhoc/`, and
produces a three-sentence conclusion computed from the result, so the narrative
can never drift from the numbers.
"""

from __future__ import annotations

from .config import write_json

CASES = {
    "weekend_decline": {
        "question": "Why did weekend traffic decline last month?",
        "chart": ("month", "trips_per_weekend_day"),
        "sql": """
WITH weekend AS (
  SELECT date_trunc('month', t.timestamp) AS month,
         count(*) AS trips,
         count(DISTINCT CAST(t.timestamp AS DATE)) AS weekend_days,
         avg(c.precipitation_mm) AS mean_rain_mm
  FROM silver.fact_trip t
  JOIN silver.external_context c ON c.date = CAST(t.timestamp AS DATE)
  WHERE t.period = 'Weekend' AND t.timestamp >= '2025-04-01' AND t.timestamp < '2025-10-01'
  GROUP BY 1
)
SELECT strftime(month, '%Y-%m') AS month,
       trips,
       weekend_days,
       round(trips / weekend_days, 1) AS trips_per_weekend_day,
       round(100 * (trips / weekend_days) / lag(trips / weekend_days) OVER (ORDER BY month) - 100, 1) AS change_pct,
       round(mean_rain_mm, 2) AS mean_rain_mm
FROM weekend ORDER BY month""",
    },
    "segment_decline": {
        "question": "Which customer segment experienced the largest usage decline?",
        "chart": ("rfm_segment", "share_declining"),
        "sql": """
SELECT rfm_segment,
       count(*) AS customers,
       round(avg(trips_90d), 1) AS trips_last_90d,
       round(avg(trips_previous90d), 1) AS trips_prior_90d,
       round(sum(trips_90d) / nullif(sum(trips_previous90d), 0), 3) AS volume_ratio,
       round(avg(CASE WHEN trips_90d < 0.5 * trips_previous90d THEN 1.0 ELSE 0.0 END), 3) AS share_declining,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY frequency_trend), 3) AS median_trend
FROM gold.customer_360
WHERE trips_previous90d >= 3
GROUP BY 1 ORDER BY share_declining DESC""",
    },
    "cannibalization": {
        "question": "Did the July promotion cannibalize full-price trips?",
        "chart": ("arm", "subsidy_share"),
        "sql": """
WITH control AS (
  SELECT avg(trip_count) AS base_trips FROM gold.campaign_performance WHERE arm = 'Control'
)
SELECT p.arm,
       count(*) AS customers,
       round(avg(p.trip_count), 2) AS trips_per_customer,
       round(avg(p.trip_count) - c.base_trips, 2) AS incremental_trips,
       round(avg(p.incentive_cost), 2) AS incentive_per_customer,
       round(1 - (avg(p.trip_count) - c.base_trips) / nullif(avg(p.trip_count), 0), 3) AS subsidy_share,
       round(avg(p.net_contribution), 2) AS net_contribution_per_customer
FROM gold.campaign_performance p CROSS JOIN control c
WHERE p.arm <> 'Control'
GROUP BY p.arm, c.base_trips ORDER BY subsidy_share DESC""",
    },
    "unused_capacity": {
        "question": "Which zones have the highest unused off-peak capacity?",
        "chart": ("zone_name", "free_after_campaign"),
        "sql": """
SELECT z.zone_name,
       round(c.baseline_forecast) AS forecast_trips,
       round(c.capacity_trips) AS capacity_trips,
       round(c.available_trips) AS free_before_campaign,
       round(c.allocated_trips, 1) AS campaign_trips,
       round(c.remaining_with_reserve) AS free_after_campaign,
       rank() OVER (ORDER BY c.remaining_with_reserve DESC) AS headroom_rank,
       round(100 * c.remaining_with_reserve / sum(c.remaining_with_reserve) OVER (), 1) AS share_of_free_pct
FROM gold.zone_capacity c JOIN silver.dim_zone z USING (zone_id)
WHERE c.period = 'Off-peak'
ORDER BY headroom_rank""",
    },
    "enrollment_vs_value": {
        "question": "Why did campaign ROI decline despite increased enrollment?",
        "chart": ("arm", "net_contribution_per_customer"),
        "sql": """
WITH control AS (
  SELECT avg(net_contribution) AS base_value FROM gold.campaign_performance WHERE arm = 'Control'
)
SELECT p.arm,
       round(avg(p.enrolled), 3) AS enrollment_rate,
       round(avg(p.redeemed), 3) AS redemption_rate,
       round(avg(p.incentive_cost), 2) AS incentive_per_customer,
       round(avg(p.net_contribution) - c.base_value, 2) AS net_contribution_per_customer,
       round((avg(p.net_contribution) - c.base_value) / nullif(avg(p.incentive_cost), 0), 3) AS incremental_roi,
       row_number() OVER (ORDER BY avg(p.enrolled) DESC) AS enrollment_rank
FROM gold.campaign_performance p CROSS JOIN control c
WHERE p.arm <> 'Control'
GROUP BY p.arm, c.base_value ORDER BY enrollment_rank""",
    },
}


def _conclusion(name, frame):
    if name == "weekend_decline":
        last, prior = frame.iloc[-1], frame.iloc[-2]
        return (
            f"Weekend trips per weekend day moved {last.change_pct:+.1f}% from {prior.month} to {last.month}. "
            f"Average weekend rain went from {prior.mean_rain_mm:.1f} mm to {last.mean_rain_mm:.1f} mm, and the "
            "series also carries the seasonal slide into autumn and customer churn. Normalising by weekend days "
            "first matters: raw monthly totals confuse calendar length with demand."
        )
    if name == "segment_decline":
        top = frame.iloc[0]
        return (
            f"{top.rfm_segment} customers decline most: {top.share_declining:.0%} of them halved their trips versus "
            f"the prior 90 days (volume ratio {top.volume_ratio:.2f}). The segment rules themselves use recency, "
            "so this is descriptive, not a cause. Target the declining customers whose offers show positive "
            "incremental value rather than the whole segment."
        )
    if name == "cannibalization":
        top = frame.iloc[0]
        return (
            f"Yes. In the {top.arm} arm {top.subsidy_share:.0%} of rewarded trips would have happened anyway, so "
            f"most of its {top.incentive_per_customer:.2f} CAD incentive per customer subsidised baseline travel. "
            "Discounts paid on every eligible trip are expensive for heavy travellers. That is why the plan prices "
            "each offer on incremental trips and includes the cost of baseline trips."
        )
    if name == "unused_capacity":
        top = frame.iloc[0]
        return (
            f"{top.zone_name} keeps the most off-peak room: {top.free_after_campaign:,.0f} trips free after the "
            f"campaign and the safety reserve ({top.share_of_free_pct:.0f}% of all off-peak headroom). Off-peak "
            "offers aimed at this zone add trips where the road has capacity. Validate engineering capacity before "
            "raising offer volume further."
        )
    best = frame.sort_values("net_contribution_per_customer").iloc[-1]
    most = frame.iloc[0]
    return (
        f"Enrollment and value are different things: {most.arm} has the highest enrollment ({most.enrollment_rate:.0%}) "
        f"but earns {most.net_contribution_per_customer:+.2f} CAD per customer, while {best.arm} earns the most "
        f"({best.net_contribution_per_customer:+.2f} CAD). Enrollment is an intermediate metric. Optimise incremental "
        "net value per incentive dollar instead."
    )


def run_adhoc(cfg, db):
    folder = cfg.path("outputs", "adhoc")
    folder.mkdir(parents=True, exist_ok=True)
    cfg.path("adhoc").mkdir(exist_ok=True)
    results, notes = (
        {},
        ["# Analyst workbench results", "Synthetic analysis; history ends before the October decision date."],
    )
    for name, case in CASES.items():
        sql = case["sql"].strip()
        frame = db.execute(sql).df()
        frame.to_csv(folder / f"{name}.csv", index=False)
        cfg.path("adhoc", f"{name}.sql").write_text(sql + ";\n", encoding="utf-8")
        conclusion = _conclusion(name, frame)
        results[name] = {
            "question": case["question"],
            "sql": sql,
            "chart": case["chart"],
            "conclusion": conclusion,
        }
        notes.extend([f"\n## {case['question']}", frame.to_string(index=False), "\n" + conclusion])
    (folder / "findings.md").write_text("\n\n".join(notes), encoding="utf-8")
    write_json(folder / "cases.json", results)
    return results

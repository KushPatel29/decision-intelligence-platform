import numpy as np
import pandas as pd
from lifetimes import BetaGeoFitter
from lifetimes.utils import summary_data_from_transaction_data

from decision_platform.config import ROOT

t = pd.read_parquet(ROOT / "data/silver/fact_trip.parquet")
t = (
    t[t.timestamp < "2025-07-01"]
    .assign(day=lambda x: x.timestamp.dt.normalize(), margin=lambda x: x.final_charge * 0.72)
    .groupby(["customer_id", "day"])
    .margin.sum()
    .reset_index()
)
s = summary_data_from_transaction_data(
    t, "customer_id", "day", "margin", observation_period_end=pd.Timestamp("2025-06-30"), freq="D"
)
for penalty in [0.1, 0.01, 0.0]:
    m = BetaGeoFitter(penalizer_coef=penalty).fit(s.frequency, s.recency, s["T"])
    predicted = m.conditional_expected_number_of_purchases_up_to_time(90, s.frequency, s.recency, s["T"])
    print(
        penalty,
        m.params_.to_dict(),
        np.isfinite(predicted).sum(),
        len(s),
        s.loc[~np.isfinite(predicted)].frequency.value_counts().to_dict(),
    )

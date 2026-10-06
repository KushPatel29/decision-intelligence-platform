from pathlib import Path
import duckdb
import numpy as np
import pandas as pd
from .config import write_json

FEATURES = ["tenure_days","business_flag","autopay","transponder_flag","home_zone",
            "trips_7d","trips_30d","trips_90d","trips_previous90d","spend_30d","spend_90d",
            "spend_365d","avg_toll","avg_distance_km","peak_share","weekend_share","discount_90d",
            "recency_days","digital_events_30d","app_logins_30d","offer_views_30d","email_opens_30d",
            "points_earned_to_date","frequency_trend","digital_engagement_score"]

def connect(cfg, frames):
    db = duckdb.connect(str(cfg.path("data","platform.duckdb")))
    # Stable floating-point reductions keep histogram split candidates identical
    # across complete seeded reruns on the same data and runtime.
    db.execute("SET threads=1")
    db.execute("CREATE SCHEMA IF NOT EXISTS silver")
    db.execute("CREATE SCHEMA IF NOT EXISTS gold")
    for name, frame in frames.items():
        db.register("incoming",frame)
        db.execute(f"CREATE OR REPLACE TABLE silver.{name} AS SELECT * FROM incoming")
    return db

def snapshot(db, cfg, date, labels=True):
    date = pd.Timestamp(date)
    frame = db.execute(cfg.path("sql","customer_features.sql").read_text(),{"as_of":date}).df()
    tables=db.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='silver'").df().table_name.tolist()
    if "customer_status_history" in tables:
        state=db.execute("SELECT h.customer_id,h.account_status,h.marketing_consent,c.has_my_account,c.past_due FROM silver.customer_status_history h JOIN silver.dim_customer c USING(customer_id) WHERE h.effective_from<= $as_of AND (h.effective_to IS NULL OR h.effective_to > $as_of)",{"as_of":date}).df()
        if state.customer_id.duplicated().any() or len(state)!=len(frame):raise ValueError("Account history must resolve exactly one state per customer")
        frame=frame.drop(columns=["account_status","eligible"]).merge(state,on="customer_id",validate="one_to_one")
        frame["eligible"]=frame.account_status.eq("Active")&frame.marketing_consent&frame.has_my_account&~frame.past_due
    frame["frequency_trend"] = (frame.trips_90d+1)/(frame.trips_previous90d+1)
    frame["digital_engagement_score"] = np.log1p(frame.digital_events_30d)
    if frame.feature_max_timestamp.dropna().ge(date).any():
        raise ValueError("Feature leakage: an event timestamp is on/after snapshot cutoff")
    if labels:
        if date+pd.Timedelta(days=90)>pd.Timestamp(cfg.end)+pd.Timedelta(days=1):
            raise ValueError("Right-censored labels are not allowed")
        target = db.execute(cfg.path("sql","customer_labels.sql").read_text(),{"as_of":date,"margin":cfg.contribution_margin}).df()
        frame = frame.merge(target,on="customer_id",how="left")
        frame[["future_trips_30d","future_trips_90d","future_margin_90d"]] = frame[["future_trips_30d","future_trips_90d","future_margin_90d"]].fillna(0)
        frame["target_propensity"] = (frame.future_trips_30d>0).astype(int)
        frame["historically_active"] = frame.trips_90d>=3
        frame["target_churn"] = (frame.future_trips_90d==0).astype(int)
        frame["target_attrition"] = (frame.future_trips_90d<.5*frame.trips_90d).astype(int)
        frame["label_end"] = date+pd.Timedelta(days=90)
    return frame

def build(db, cfg):
    # Purged chronological folds: 90-day labels never cross the next fold boundary.
    train_dates = pd.date_range("2024-07-01","2025-01-01",freq="MS")
    validation_dates = [pd.Timestamp("2025-04-01")]
    test_dates = [pd.Timestamp("2025-07-01")]
    pieces=[]
    for split, dates in [("train",train_dates),("validation",validation_dates),("test",test_dates)]:
        for date in dates:
            frame=snapshot(db,cfg,date)
            frame["split"]=split
            pieces.append(frame)
    snapshots=pd.concat(pieces,ignore_index=True)
    current=snapshot(db,cfg,cfg.decision_date,labels=False)
    out=cfg.path("data","gold")
    out.mkdir(parents=True,exist_ok=True)
    snapshots.to_parquet(out/"customer_month.parquet",index=False)
    current.to_parquet(out/"customer_360_features.parquet",index=False)
    db.register("incoming",snapshots)
    db.execute("CREATE OR REPLACE TABLE gold.customer_month AS SELECT * FROM incoming")
    write_json(cfg.path("outputs","feature_contract.json"),{"version":"1.0","features":FEATURES,
        "end_exclusive":True,"timezone":"America/Toronto wall-clock","label_horizon_days":90,
        "train_max_label_end":str(snapshots.loc[snapshots.split.eq('train'),'label_end'].max()),
        "validation_start":"2025-04-01","test_start":"2025-07-01","decision_date":cfg.decision_date,
        "future_targets_excluded":True,"hidden_generator_parameters_excluded":True})
    return snapshots,current

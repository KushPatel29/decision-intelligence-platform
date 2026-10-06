"""Synthetic account/trip/digital/loyalty ecosystem with hidden heterogeneity.

Hidden price sensitivity and churn dates NEVER enter model features.
Simulated rates/zones are invented; this is not the actual 407 network or tariff.
"""
import hashlib
import numpy as np
import pandas as pd
from .config import write_json

PERIODS = ["Peak", "Off-peak", "Weekend"]
ZONES = ["West", "Northwest", "Central", "Northeast", "East", "Outer east"]

def generate(cfg, context):
    rng = np.random.default_rng(cfg.seed)
    n = cfg.customers
    ids = [hashlib.sha256(f"synthetic-{cfg.seed}-{i}".encode()).hexdigest()[:16] for i in range(n)]
    customers = pd.DataFrame({"customer_id": ids, "account_id": [f"A{i:06}" for i in range(n)],
        "customer_type": rng.choice(["Personal","Business"],n,p=[.84,.16]),
        "account_status": rng.choice(["Active","Suspended"],n,p=[.97,.03]),
        "marketing_consent": rng.random(n)<.83, "has_my_account": rng.random(n)<.91,
        "past_due": rng.random(n)<.07, "autopay": rng.random(n)<.67,
        "transponder_flag": rng.random(n)<.86,
        "home_zone": rng.integers(0,len(ZONES),n),
        "vehicle_class": rng.choice(["Light","Heavy"],n,p=[.94,.06]),
        "created_at": pd.Timestamp("2020-01-01")+pd.to_timedelta(rng.integers(0,1460,n),unit="D")})
    customers["eligible"] = customers.marketing_consent & customers.has_my_account & ~customers.past_due & customers.account_status.eq("Active")
    frequency = np.exp(rng.normal(-2.0,1.15,n))
    sensitivity = rng.uniform(.35,2.0,n)
    stop_day = np.where(rng.random(n)<.31,rng.integers(290,720,n),10000)
    digital_affinity = rng.beta(2,2,n)
    trip_parts, event_parts = [], []
    customer_index = np.arange(n)
    for day_index, row in context.iterrows():
        date = row.date
        drift = np.where(day_index>stop_day, np.exp(-(day_index-stop_day)/22),1.0)
        seasonal = 1+.16*np.sin(2*np.pi*day_index/365.25)
        calendar_effect = .68 if row.weekend or row.holiday else 1.0
        weather_effect = np.exp(-.018*row.precipitation_mm)
        rates = frequency * drift * seasonal * calendar_effect * weather_effect
        counts = rng.poisson(np.clip(rates,0,5))
        repeated = np.repeat(customer_index, counts)
        if len(repeated):
            m = len(repeated)
            period = np.where(row.weekend,"Weekend",rng.choice(["Peak","Off-peak"],m,p=[.63,.37]))
            zones = np.where(rng.random(m)<.78,customers.home_zone.to_numpy()[repeated],rng.integers(0,len(ZONES),m))
            distance = rng.uniform(10,48,m)
            rate = .31 + .07*(period=="Peak") + .02*zones + .03*(date.year==2025)
            toll = distance*rate*np.where(customers.vehicle_class.to_numpy()[repeated]=="Heavy",1.65,1.)
            discount_pct = rng.choice([0.,.10,.20],m,p=[.86,.10,.04])
            discount = toll*discount_pct
            hour = np.where(period=="Peak",rng.choice([7,8,16,17],m),rng.integers(10,16,m))
            trip_parts.append(pd.DataFrame({"customer_id":np.array(ids)[repeated],"timestamp":date+pd.to_timedelta(hour,unit="h")+pd.to_timedelta(rng.integers(0,60,m),unit="m"),
                "zone_id":zones,"direction":rng.choice(["Eastbound","Westbound"],m),"period":period,
                "distance_km":distance,"duration_min":distance/1.45+rng.uniform(1,5,m),"toll":toll,"discount":discount,"final_charge":toll-discount}))
        login = rng.random(n)<(.014+.12*digital_affinity)*(.25+.75*(drift>.2))
        active = customer_index[login]
        if len(active):
            event_parts.append(pd.DataFrame({"customer_id":np.array(ids)[active],"timestamp":date+pd.to_timedelta(rng.integers(0,24,len(active)),unit="h"),
                "event_type":rng.choice(["app_login","web_login","offer_view","email_open","loyalty_page_view"],len(active)),
                "channel":rng.choice(["App","Web","Email"],len(active))}))
    trips = pd.concat(trip_parts,ignore_index=True)
    trips.insert(0,"trip_id",[f"T{i:09}" for i in range(len(trips))])
    events = pd.concat(event_parts,ignore_index=True)
    events.insert(0,"event_id",[f"D{i:09}" for i in range(len(events))])
    accounts = customers[["account_id","customer_id","account_status","autopay","past_due","created_at"]].copy()
    vehicles = customers[["customer_id","vehicle_class","transponder_flag"]].copy()
    vehicles.insert(0,"vehicle_id",[f"V{i:06}" for i in range(n)])
    zones = pd.DataFrame({"zone_id":range(len(ZONES)),"zone_name":ZONES,"is_synthetic":True})
    offers = pd.DataFrame({"offer_id":["offpeak_15","weekend_20","loyalty_500"],
        "offer_name":["Off-peak 15%","Weekend 20%","500 loyalty points"],
        "period":["Off-peak","Weekend","Off-peak"],"discount_pct":[.15,.20,0.],"inventory":[100,85,70]})
    loyalty = trips[["trip_id","customer_id","timestamp","final_charge"]].copy()
    loyalty["points_earned"] = np.floor(loyalty.final_charge*2).astype(int)
    loyalty = loyalty.drop(columns="final_charge")
    # Deliberate independent price interventions identify elasticity within simulation.
    price_rows = []
    for date_index, row in context.iterrows():
        for zone in range(len(ZONES)):
            for period in PERIODS:
                multiplier = rng.choice([.7,.8,.9,1.,1.05,1.1])
                base = 70*(1+.1*zone)*(.7 if row.weekend else 1.)*(1.2 if period=="Peak" else .8)
                base *= np.exp(-.018*row.precipitation_mm)*(1+.14*row.month_sin)
                beta = -(.6+.13*zone+(.4 if period=="Weekend" else 0))
                demand = rng.poisson(base * multiplier**beta)
                price_rows.append({"date":row.date,"zone_id":zone,"period":period,"effective_price":10*multiplier,
                    "assigned_price_multiplier":multiplier,"demand":demand,"temperature_c":row.temperature_c,
                    "precipitation_mm":row.precipitation_mm,"weekend":row.weekend,"holiday":row.holiday,
                    "month_sin":row.month_sin,"month_cos":row.month_cos})
    pricing = pd.DataFrame(price_rows)
    # Hidden generator state is retained for simulation audit, in a separate namespace.
    hidden = pd.DataFrame({"customer_id":ids,"latent_frequency":frequency,"latent_sensitivity":sensitivity,
                           "latent_digital_affinity":digital_affinity,"latent_stop_day":stop_day})
    frames = {"dim_customer":customers,"dim_account":accounts,"dim_vehicle":vehicles,"dim_zone":zones,
              "dim_offer":offers,"fact_trip":trips,"fact_digital_event":events,"fact_loyalty_points":loyalty,
              "fact_pricing_scenario":pricing,"external_context":context}
    frames["dim_transponder"]=customers.loc[customers.transponder_flag,["customer_id","account_id"]].assign(transponder_id=lambda x:"T"+x.account_id.str[1:])
    frames["customer_preferences"]=customers[["customer_id","marketing_consent","autopay","has_my_account"]].copy()
    state=customers[["customer_id","account_status","marketing_consent","eligible","created_at"]].copy()
    changed=state.sample(frac=.08,random_state=cfg.seed+71).customer_id
    initial=state.rename(columns={"created_at":"effective_from"}).copy()
    initial["effective_to"]=pd.NaT
    mask=initial.customer_id.isin(changed)
    initial.loc[mask,"effective_to"]=pd.Timestamp("2025-03-01")
    initial.loc[mask,"account_status"]=np.where(initial.loc[mask,"account_status"].eq("Active"),"Suspended","Active")
    initial.loc[mask,"marketing_consent"]=~initial.loc[mask,"marketing_consent"]
    changed_rows=state[state.customer_id.isin(changed)].rename(columns={"created_at":"effective_from"}).copy()
    changed_rows["effective_from"]=pd.Timestamp("2025-03-01");changed_rows["effective_to"]=pd.NaT
    frames["customer_status_history"]=pd.concat([initial,changed_rows],ignore_index=True).drop(columns="eligible")
    frames["dim_entry_point"]=zones[["zone_id","zone_name"]].assign(entry_point_id=lambda x:"E"+x.zone_id.astype(str))
    frames["dim_exit_point"]=zones[["zone_id","zone_name"]].assign(exit_point_id=lambda x:"X"+x.zone_id.astype(str))
    frames["dim_time"]=context[["date","weekend","holiday"]].assign(day_of_week=context.date.dt.dayofweek,month=context.date.dt.month,year=context.date.dt.year)
    frames["dim_rate"]=pd.MultiIndex.from_product([range(len(ZONES)),PERIODS,["Light","Heavy"]],names=["zone_id","period","vehicle_class"]).to_frame(index=False)
    frames["dim_rate"]["rate_per_km"]=(.34+.07*frames["dim_rate"].period.eq("Peak")+.02*frames["dim_rate"].zone_id)*np.where(frames["dim_rate"].vehicle_class.eq("Heavy"),1.65,1.)
    frames["fact_effective_price"]=trips[["trip_id","customer_id","timestamp","zone_id","period","distance_km","toll","discount","final_charge"]].assign(effective_price_per_km=lambda x:x.final_charge/x.distance_km)
    frames["dim_reward"]=pd.DataFrame({"reward_id":["loyalty_500"],"reward_name":["500-point travel reward"],"points_cost":[500],"max_value_cad":[5.]})
    balances=loyalty[loyalty.timestamp<pd.Timestamp(cfg.decision_date)].groupby("customer_id").points_earned.sum().reindex(ids,fill_value=0)
    frames["fact_loyalty_tier"]=pd.DataFrame({"customer_id":ids,"as_of":cfg.decision_date,"tier":np.where(balances.to_numpy()>=3000,"Platinum",np.where(balances.to_numpy()>=1000,"Gold","Silver"))})
    for layer in ("bronze","silver"):
        folder = cfg.path("data",layer)
        folder.mkdir(parents=True,exist_ok=True)
        for name,frame in frames.items():
            frame.to_parquet(folder/f"{name}.parquet",index=False)
    cfg.path("data","simulation_audit").mkdir(parents=True,exist_ok=True)
    hidden.to_parquet(cfg.path("data","simulation_audit","hidden_parameters.parquet"),index=False)
    write_json(cfg.path("outputs","data_quality.json"),validate(frames))
    return frames, hidden

def validate(frames):
    c,t,d = frames["dim_customer"],frames["fact_trip"],frames["fact_digital_event"]
    checks = {"customer_key_unique":not c.customer_id.duplicated().any(),
        "trip_key_unique":not t.trip_id.duplicated().any(),"event_key_unique":not d.event_id.duplicated().any(),
        "customer_fk":set(t.customer_id).issubset(set(c.customer_id)),
        "digital_customer_fk":set(d.customer_id).issubset(set(c.customer_id)),
        "zone_fk":set(t.zone_id).issubset(set(frames["dim_zone"].zone_id)),
        "nonnegative_charge":bool((t.final_charge>=0).all()),
        "discount_within_toll":bool(((t.discount>=0)&(t.discount<=t.toll)).all()),
        "charge_reconciles":bool(np.allclose(t.toll-t.discount,t.final_charge)),
        "timestamps_present":bool(t.timestamp.notna().all()),
        "distance_positive":bool((t.distance_km>0).all())}
    if not all(checks.values()):
        raise ValueError(f"Data contract failed: {checks}")
    return {"status":"passed","checks":checks,"rows":{k:len(v) for k,v in frames.items()}}

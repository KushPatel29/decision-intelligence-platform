"""Chronological prediction, held-out causal estimates, and reproducible artifacts."""
import time
import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor, IsolationForest, RandomForestRegressor
from sklearn.linear_model import LogisticRegression, LinearRegression
from .quality import HistoricalMargin, SeasonalNaive, select_regression, evaluate_quality
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss, mean_absolute_error, root_mean_squared_error, silhouette_score, davies_bouldin_score, adjusted_rand_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from .config import write_json, frame_hash
from .features import FEATURES

def classifier_metrics(y,score):
    y=np.asarray(y);score=np.asarray(score)
    if len(np.unique(y))<2:
        raise ValueError("Classification evaluation requires both target classes")
    bins=np.minimum((score*10).astype(int),9)
    ece=sum((bins==b).mean()*abs(y[bins==b].mean()-score[bins==b].mean()) for b in range(10) if (bins==b).any())
    order=np.argsort(-score)
    def lift(fraction):
        return float(y[order[:max(1,int(len(y)*fraction))]].mean()/y.mean())
    return {"roc_auc":float(roc_auc_score(y,score)),"pr_auc":float(average_precision_score(y,score)),
            "brier":float(brier_score_loss(y,score)),"ece_10bins":float(ece),"lift_at_10":lift(.1),"lift_at_20":lift(.2),
            "n":len(y),"prevalence":float(y.mean())}

def reg_metrics(y,pred):
    return {"mae":float(mean_absolute_error(y,pred)),"rmse":float(root_mean_squared_error(y,pred)),"n":len(y)}

def log_experiment(cfg,name,model,metrics,params,tracking):
    folder=cfg.path("outputs","models")
    folder.mkdir(parents=True,exist_ok=True)
    joblib.dump(model,folder/f"{name}.joblib")
    write_json(folder/f"{name}.metrics.json",{"metrics":metrics,"parameters":params})
    if not tracking:
        return
    try:
        import mlflow
        mlflow.set_tracking_uri("sqlite:///"+str(cfg.path("outputs","mlflow.db")).replace("\\","/"))
        mlflow.set_experiment("transportation-decision-intelligence")
        with mlflow.start_run(run_name=name) as run:
            mlflow.log_params(params)
            mlflow.log_metrics({k:float(v) for k,v in metrics.items() if isinstance(v,(int,float))})
            mlflow.set_tags({"data_kind":"synthetic","feature_version":"1.0","artifact_status":"local-candidate"})
            mlflow.log_artifact(str(folder/f"{name}.joblib"),artifact_path="models")
            mlflow.log_artifact(str(folder/f"{name}.metrics.json"))
            if cfg.path("outputs","manifest.json").exists():
                mlflow.log_artifact(str(cfg.path("outputs","manifest.json")))
            write_json(folder/f"{name}.tracking.json",{"status":"tracked","run_id":run.info.run_id})
    except Exception as exc:
        # Training still has complete local artifacts; tracking failure is reported.
        write_json(folder/f"{name}.tracking.json",{"status":"failed","error":str(exc)})

def fit_customer_models(cfg,snapshots,current,tracking=True):
    result={};scored=current.copy()
    train=snapshots[snapshots.split.eq("train")]
    val=snapshots[snapshots.split.eq("validation")]
    test=snapshots[snapshots.split.eq("test")]
    for name in ["propensity","churn","attrition"]:
        target="target_"+name
        tr,va,te=train,val,test
        if name!="propensity":
            tr=train[train.historically_active];va=val[val.historically_active];te=test[test.historically_active]
        candidates={"logistic":make_pipeline(StandardScaler(),LogisticRegression(max_iter=1500,random_state=cfg.seed)),
            "hist_gradient_boosting":HistGradientBoostingClassifier(max_iter=75,max_leaf_nodes=12,min_samples_leaf=40,l2_regularization=3,random_state=cfg.seed)}
        leaderboard={};started=time.perf_counter()
        for algorithm,model in candidates.items():
            model.fit(tr[FEATURES],tr[target])
            leaderboard[algorithm]=classifier_metrics(va[target],model.predict_proba(va[FEATURES])[:,1])
        champion=min(leaderboard,key=lambda k:leaderboard[k]["brier"])
        model=candidates[champion]
        val_raw=model.predict_proba(va[FEATURES])[:,1]
        calibrator=LogisticRegression(C=1,random_state=cfg.seed).fit(np.log(np.clip(val_raw,1e-5,1-1e-5)/(1-np.clip(val_raw,1e-5,1-1e-5))).reshape(-1,1),va[target])
        def score(frame):
            raw=np.clip(model.predict_proba(frame[FEATURES])[:,1],1e-5,1-1e-5)
            return calibrator.predict_proba(np.log(raw/(1-raw)).reshape(-1,1))[:,1]
        metrics=classifier_metrics(te[target],score(te))
        cfg.path("outputs","performance").mkdir(parents=True,exist_ok=True)
        pd.DataFrame({"customer_id":te.customer_id,"as_of":te.as_of,"target":te[target],"predicted_probability":score(te)}).to_csv(cfg.path("outputs","performance",name+"_predictions.csv"),index=False)
        metrics["training_seconds"]=time.perf_counter()-started
        result[name]={"champion":champion,"validation_uncalibrated":leaderboard,"test_calibrated":metrics,
            "calibration_population":"Separate April 2025 validation fold; test is July 2025",
            "population":"historically active (>=3 trips / prior 90 days)" if name!="propensity" else "all customers"}
        scored[name+"_probability"]=score(current)
        if name!="propensity":
            scored.loc[scored.trips_90d<3,name+"_probability"]=np.nan
        log_experiment(cfg,name,{"model":model,"calibrator":calibrator,"features":FEATURES},metrics,
                       {"algorithm":champion,"seed":cfg.seed,"dataset_sha256":frame_hash(snapshots),"feature_version":"1.0"},tracking)
        print(f"  {name}: test AUC {metrics['roc_auc']:.3f}",flush=True)
    forecast=HistGradientBoostingRegressor(loss="poisson",max_iter=90,max_leaf_nodes=12,l2_regularization=3,random_state=cfg.seed)
    forecast.fit(train[FEATURES],train.future_margin_90d)
    baseline=HistoricalMargin(cfg.contribution_margin)
    selection=select_regression(val.future_margin_90d,{
        "hist_gradient_boosting":forecast.predict(val[FEATURES]),
        "historical_margin":baseline.predict(val[FEATURES])})
    selected_name=selection["selected"]
    forecast=forecast if selected_name=="hist_gradient_boosting" else baseline
    pred=np.maximum(forecast.predict(test[FEATURES]),0)
    metrics=reg_metrics(test.future_margin_90d,pred)
    metrics["baseline_mae"]=float(mean_absolute_error(test.future_margin_90d,test.spend_90d*cfg.contribution_margin))
    first=np.maximum(forecast.predict(current[FEATURES]),0)
    retention=1-scored.churn_probability.fillna(.5).to_numpy()
    scored["expected_margin_90d"]=first
    scored["clv_12m"]=sum(first*retention**(q-1)/(1.10)**(q/4) for q in range(1,5))
    result["clv"]={"test":metrics,"selection":selection,"champion":selected_name,"method":"Validation-selected 90-day contribution forecast projected four quarters with churn-based survival decay; 10% annual discount. Heuristic projected value; not validated 12-month CLV."}
    log_experiment(cfg,"clv",forecast,metrics,{"algorithm":selected_name,"seed":cfg.seed},tracking)
    segment_features=["trips_90d","spend_90d","avg_distance_km","peak_share","weekend_share","digital_events_30d","recency_days"]
    segment_train=train[train.as_of.eq(train.as_of.max())]
    scaler=StandardScaler().fit(np.log1p(segment_train[segment_features]))
    scaled=scaler.transform(np.log1p(segment_train[segment_features]))
    clustering=KMeans(n_clusters=5,n_init=10,random_state=cfg.seed).fit(scaled)
    scored["cluster"]=clustering.predict(scaler.transform(np.log1p(current[segment_features])))
    scored["rfm_segment"]=np.select([scored.recency_days>90,(scored.recency_days>30)&(scored.trips_previous90d>=3),scored.trips_90d>=25,scored.trips_90d>=8,scored.tenure_days<180],
            ["Dormant","At risk","Champions","Loyal","New"],default="Occasional")
    result["segmentation"]={"silhouette":float(silhouette_score(scaled,clustering.labels_,sample_size=min(1000,len(scaled)),random_state=cfg.seed)),
        "davies_bouldin":float(davies_bouldin_score(scaled,clustering.labels_)),"clusters":5,"fit_as_of":str(segment_train.as_of.max())}
    rng=np.random.default_rng(cfg.seed);stability=[]
    for seed in range(3):
        boot=KMeans(n_clusters=5,n_init=5,random_state=cfg.seed+seed+1).fit(scaled[rng.integers(len(scaled),size=len(scaled))])
        stability.append(float(adjusted_rand_score(clustering.labels_,boot.predict(scaled))))
    result["segmentation"]["bootstrap_adjusted_rand"]=stability
    joblib.dump({"scaler":scaler,"model":clustering,"features":segment_features},cfg.path("outputs","models","segmentation.joblib"))
    anomaly=IsolationForest(contamination=.025,n_estimators=120,random_state=cfg.seed).fit(scaled)
    current_scaled=scaler.transform(np.log1p(current[segment_features]))
    scored["anomaly_score"]=-anomaly.score_samples(current_scaled)
    scored["anomaly_flag"]=anomaly.predict(current_scaled)==-1
    joblib.dump({"scaler":scaler,"model":anomaly,"features":segment_features},cfg.path("outputs","models","anomaly.joblib"))
    result["anomaly"]={"flagged":int(scored.anomaly_flag.sum()),"method":"Isolation Forest, historical January baseline; anomaly is a review signal, not fraud adjudication"}
    return scored,result

def uplift_curve(y,w,uplift):
    y=np.asarray(y);w=np.asarray(w);uplift=np.asarray(uplift)
    order=np.argsort(-uplift);e=float(w.mean())
    transformed=y*w/e-y*(1-w)/(1-e)
    gain=np.r_[0,np.cumsum(transformed[order])]/len(y)
    fraction=np.linspace(0,1,len(gain))
    random_line=fraction*gain[-1]
    return {"auuc":float(np.trapezoid(gain,fraction)),"qini":float(np.trapezoid(gain-random_line,fraction)),
        "fraction":fraction[::max(1,len(fraction)//40)].tolist(),"gain":gain[::max(1,len(gain)//40)].tolist()}

def fit_uplift(cfg,trial,current,tracking=True):
    from .experiments import ARMS,OFFER_ARMS
    train=trial[trial.split.eq("train")];test=trial[trial.split.eq("test")]
    response_models={};trip_models={};metrics={};scores={};x_models={};retention_models={};later_models={}
    for arm in ARMS:
        group=train[train.arm.eq(arm)]
        response=make_pipeline(StandardScaler(),LogisticRegression(C=.1,max_iter=1500,random_state=cfg.seed))
        response.fit(group[FEATURES],group.response)
        trips=RandomForestRegressor(n_estimators=120,max_depth=6,min_samples_leaf=35,n_jobs=2,random_state=cfg.seed)
        trips.fit(group[FEATURES],group.trip_count)
        response_models[arm]=response;trip_models[arm]=trips
        retention_models[arm]=make_pipeline(StandardScaler(),LogisticRegression(C=.1,max_iter=1500,random_state=cfg.seed)).fit(group[FEATURES],group.retained_90d)
        later_models[arm]=RandomForestRegressor(n_estimators=60,max_depth=5,min_samples_leaf=45,n_jobs=2,random_state=cfg.seed).fit(group[FEATURES],group.margin_days31_90)
    # S-learner benchmark shares outcome structure, with explicit arm indicators.
    s_train=train[FEATURES].copy()
    for arm in ARMS[1:]:
        s_train[arm]=(train.arm==arm).astype(int)
    s_model=HistGradientBoostingClassifier(max_iter=65,max_leaf_nodes=8,min_samples_leaf=35,l2_regularization=4,random_state=cfg.seed).fit(s_train,train.response)
    for offer,arm in OFFER_ARMS.items():
        treated_group=train[train.arm.eq(arm)];control_group=train[train.arm.eq("Control")]
        # X-learner: impute individual response effects on opposite outcome models.
        d1=treated_group.response-response_models["Control"].predict_proba(treated_group[FEATURES])[:,1]
        d0=response_models[arm].predict_proba(control_group[FEATURES])[:,1]-control_group.response
        x1=RandomForestRegressor(n_estimators=100,max_depth=5,min_samples_leaf=40,n_jobs=2,random_state=cfg.seed).fit(treated_group[FEATURES],d1)
        x0=RandomForestRegressor(n_estimators=100,max_depth=5,min_samples_leaf=40,n_jobs=2,random_state=cfg.seed).fit(control_group[FEATURES],d0)
        x_models[arm]=(x0,x1)
        sample=test[test.arm.isin(["Control",arm])]
        u=response_models[arm].predict_proba(sample[FEATURES])[:,1]-response_models["Control"].predict_proba(sample[FEATURES])[:,1]
        curve=uplift_curve(sample.response,(sample.arm==arm).astype(int),u)
        s0=sample[FEATURES].copy();s1=sample[FEATURES].copy()
        for name in ARMS[1:]:
            s0[name]=0;s1[name]=int(name==arm)
        su=s_model.predict_proba(s1)[:,1]-s_model.predict_proba(s0)[:,1]
        xu=.5*x0.predict(sample[FEATURES])+.5*x1.predict(sample[FEATURES])
        metrics[offer]={"t_learner":curve,"s_learner":uplift_curve(sample.response,(sample.arm==arm).astype(int),su),
                       "x_learner":uplift_curve(sample.response,(sample.arm==arm).astype(int),xu),
                       "n_test":len(sample),"algorithm":"Separate regularized logistic outcome models; Random Forest trip outcome models"}
        scores[offer]=pd.DataFrame({"customer_id":current.customer_id,"offer_id":offer,
            "incremental_response":response_models[arm].predict_proba(current[FEATURES])[:,1]-response_models["Control"].predict_proba(current[FEATURES])[:,1],
            "predicted_treated_trips":trip_models[arm].predict(current[FEATURES]),
            "predicted_baseline_trips":trip_models["Control"].predict(current[FEATURES])})
        scores[offer]["incremental_trips_raw"]=scores[offer].predicted_treated_trips-scores[offer].predicted_baseline_trips
        retention_delta=retention_models[arm].predict_proba(current[FEATURES])[:,1]-retention_models["Control"].predict_proba(current[FEATURES])[:,1]
        later_delta=later_models[arm].predict(current[FEATURES])-later_models["Control"].predict(current[FEATURES])
        # Signed, shrunk effects; do not turn negative estimates into positive value.
        scores[offer]["incremental_retention_90d"]=retention_delta*.75
        scores[offer]["incremental_value_days31_90"]=later_delta*.75/(1.10**(.25))
        metrics[offer]["retention_90d_test"]={"treated":classifier_metrics(sample[sample.arm.eq(arm)].retained_90d,retention_models[arm].predict_proba(sample[sample.arm.eq(arm)][FEATURES])[:,1]),"control":classifier_metrics(sample[sample.arm.eq("Control")].retained_90d,retention_models["Control"].predict_proba(sample[sample.arm.eq("Control")][FEATURES])[:,1])}
    # Offer enrollment is a different classification target from travel response.
    treated=train[train.treated.eq(1)];held=test[test.treated.eq(1)]
    enroll=make_pipeline(StandardScaler(),LogisticRegression(C=.2,max_iter=1500,random_state=cfg.seed)).fit(treated[FEATURES],treated.enrolled)
    metrics["offer_enrollment"]=classifier_metrics(held.enrolled,enroll.predict_proba(held[FEATURES])[:,1])
    loyalty_train=train[train.arm.eq("500 loyalty points")];loyalty_test=test[test.arm.eq("500 loyalty points")]
    redemption=make_pipeline(StandardScaler(),LogisticRegression(C=.2,max_iter=1500,random_state=cfg.seed)).fit(loyalty_train[FEATURES],loyalty_train.redeemed)
    metrics["loyalty_redemption"]=classifier_metrics(loyalty_test.redeemed,redemption.predict_proba(loyalty_test[FEATURES])[:,1])
    for offer in scores:
        scores[offer]["enrollment_probability"]=enroll.predict_proba(current[FEATURES])[:,1]
        scores[offer]["redemption_probability"]=redemption.predict_proba(current[FEATURES])[:,1] if offer=="loyalty_500" else np.nan
    # Held-out predictions support exploratory off-policy evaluation, without simulator truth.
    evaluation=test[["customer_id","arm","net_contribution","trip_count"]].copy()
    for offer,arm in OFFER_ARMS.items():
        baseline=trip_models["Control"].predict(test[FEATURES]);treated_prediction=trip_models[arm].predict(test[FEATURES])
        delta=np.maximum(treated_prediction-baseline,0)*.75
        cost=np.full(len(test),5.35) if offer=="loyalty_500" else treated_prediction*test.avg_toll.clip(lower=8)*(.2 if offer=="weekend_20" else .15)+.35
        evaluation[offer+"_value"]=delta*test.avg_toll.clip(lower=8)*cfg.contribution_margin-cost
    evaluation.to_csv(cfg.path("outputs","heldout_policy_scores.csv"),index=False)
    log_experiment(cfg,"uplift",{"response":response_models,"trips":trip_models,"retention":retention_models,"later_margin":later_models,"s_learner":s_model,"x_learner":x_models,"enrollment":enroll,"redemption":redemption,"features":FEATURES},
        {"offpeak_qini":metrics["offpeak_15"]["t_learner"]["qini"],"weekend_qini":metrics["weekend_20"]["t_learner"]["qini"]},
        {"seed":cfg.seed,"assignment":"customer-randomized","fit_as_of":"2025-07-01","outcome_available_by":"2025-09-30"},tracking)
    return pd.concat(scores.values(),ignore_index=True),metrics

def fit_elasticity(cfg,pricing,tracking=True):
    rows=[];models={}
    inputs=["log_price","temperature_c","precipitation_mm","weekend","holiday","month_sin","month_cos"]
    pricing=pricing.copy();pricing["log_price"]=np.log(pricing.effective_price)
    for (zone,period),group in pricing.groupby(["zone_id","period"]):
        tr=group[group.date<"2025-07-01"];te=group[(group.date>="2025-07-01")&(group.date<"2025-10-01")]
        model=LinearRegression().fit(tr[inputs],np.log(np.maximum(tr.demand,1)))
        pred=np.exp(model.predict(te[inputs]))
        beta=float(model.coef_[0]);metrics=reg_metrics(te.demand,pred)
        rows.append({"zone_id":int(zone),"period":period,"elasticity":beta,**metrics})
        models[f"{zone}:{period}"]=model
    result=pd.DataFrame(rows)
    log_experiment(cfg,"elasticity",{"models":models,"features":inputs},{"mean_test_mae":float(result.mae.mean())},
                   {"identification":"independently randomized synthetic price assignments","seed":cfg.seed},tracking)
    result.to_csv(cfg.path("outputs","elasticity.csv"),index=False)
    scenarios=[]
    for _,row in result.iterrows():
        for change in [-.30,-.20,-.10,0,.05,.10]:
            demand_ratio=(1+change)**row.elasticity
            scenarios.append({"zone_id":int(row.zone_id),"period":row.period,"price_change":change,
                "demand_index":100*demand_ratio,"revenue_index":100*demand_ratio*(1+change),"elasticity":row.elasticity})
    pd.DataFrame(scenarios).to_csv(cfg.path("outputs","pricing_scenarios.csv"),index=False)
    return result,pd.DataFrame(scenarios)

def fit_demand(cfg,trips,context,tracking=True):
    from .data import PERIODS,ZONES
    daily=trips.assign(date=trips.timestamp.dt.normalize()).groupby(["date","zone_id","period"]).size().rename("trips").reset_index()
    grid=pd.MultiIndex.from_product([pd.date_range(cfg.start,cfg.end),range(len(ZONES)),PERIODS],names=["date","zone_id","period"]).to_frame(index=False)
    frame=grid.merge(daily,on=["date","zone_id","period"],how="left").fillna({"trips":0}).merge(context,on="date")
    frame=frame.sort_values(["zone_id","period","date"])
    group=frame.groupby(["zone_id","period"])
    frame["lag7"]=group.trips.shift(7)
    frame["rolling28"]=group.trips.transform(lambda v:v.shift(1).rolling(28,min_periods=28).mean())
    frame["weather_lag1"]=group.precipitation_mm.shift(1)
    frame["temperature_lag1"]=group.temperature_c.shift(1)
    frame["economic_lag1"]=group.cad_usd.shift(1)
    frame["dow"]=frame.date.dt.dayofweek
    frame["period_code"]=frame.period.map({p:i for i,p in enumerate(PERIODS)})
    inputs=["zone_id","period_code","dow","weekend","holiday","month_sin","month_cos","lag7","rolling28","weather_lag1","temperature_lag1","economic_lag1"]
    valid=frame[frame.rolling28.notna()]
    tr=valid[valid.date<"2025-04-01"];va=valid[(valid.date>="2025-04-01")&(valid.date<"2025-07-01")];te=valid[(valid.date>="2025-07-01")&(valid.date<cfg.decision_date)]
    model=HistGradientBoostingRegressor(max_iter=100,max_leaf_nodes=18,l2_regularization=4,random_state=cfg.seed).fit(tr[inputs],tr.trips)
    selection=select_regression(va.trips,{"hist_gradient_boosting":model.predict(va[inputs]),"seasonal_naive":va.lag7})
    use_model=selection["selected"]=="hist_gradient_boosting"
    pred=np.maximum(model.predict(te[inputs]) if use_model else te.lag7.to_numpy(),0)
    candidate_test=reg_metrics(te.trips,pred)
    # Predeclared acceptance gate; reject without tuning/refitting on test.
    if use_model and candidate_test["mae"]>mean_absolute_error(te.trips,te.lag7):
        use_model=False
        pred=np.maximum(te.lag7.to_numpy(),0)
        selection["promotion_gate"]="Rejected candidate: held-out error exceeds predeclared baseline. Seasonal baseline remains the serving champion."
        selection["candidate_test"]=candidate_test
    serving_name="hist_gradient_boosting" if use_model else "seasonal_naive"
    metrics=reg_metrics(te.trips,pred)
    metrics["seasonal_naive_mae"]=float(mean_absolute_error(te.trips,te.lag7))
    # Next-day test allows yesterday's observations, never same-day realized weather.
    log_experiment(cfg,"demand",{"model":model if use_model else SeasonalNaive(),"candidate_model":model,"features":inputs,"selected":serving_name},metrics,{"horizon":"next-day rolling evaluation","seed":cfg.seed,"serving_algorithm":serving_name},tracking)
    history=frame[frame.date<pd.Timestamp(cfg.decision_date)]
    future_rows=[]
    for (zone,period),g in history.groupby(["zone_id","period"]):
        recent=g.tail(28)
        for date in pd.date_range(cfg.decision_date,periods=30):
            same_dow=recent[recent.dow.eq(date.dayofweek)]
            base=float(same_dow.trips.mean())
            future_rows.append({"date":date,"zone_id":zone,"period":period,"period_code":PERIODS.index(period),
                "dow":date.dayofweek,"weekend":int(date.dayofweek>=5),"holiday":int(context.set_index("date").loc[date,"holiday"]),
                "month_sin":np.sin(2*np.pi*date.dayofyear/365.25),"month_cos":np.cos(2*np.pi*date.dayofyear/365.25),
                "lag7":base,"rolling28":float(recent.trips.mean()),"weather_lag1":float(recent.precipitation_mm.mean()),
                "temperature_lag1":float(recent.temperature_c.mean()),"economic_lag1":float(recent.cad_usd.iloc[-1])})
    future=pd.DataFrame(future_rows)
    future["baseline_forecast"]=np.maximum(model.predict(future[inputs]) if use_model else future.lag7.to_numpy(),0)
    # Finite illustrative engineering capacities, based only on pre-decision history.
    caps=history.groupby(["zone_id","period"]).trips.quantile(.95).rename("daily_capacity").reset_index()
    caps["daily_capacity"]=np.maximum(np.ceil(caps.daily_capacity*1.30),3)
    cell=future.groupby(["zone_id","period"]).baseline_forecast.sum().reset_index().merge(caps,on=["zone_id","period"])
    cell["capacity_trips"]=cell.daily_capacity*30
    cell["reserve_trips"]=.2*cell.baseline_forecast
    cell["available_trips"]=np.maximum(cell.capacity_trips-cell.baseline_forecast-cell.reserve_trips,0)
    cell["baseline_over_capacity"]=(cell.baseline_forecast+cell.reserve_trips)>cell.capacity_trips
    cell.to_csv(cfg.path("outputs","capacity.csv"),index=False)
    frame.to_parquet(cfg.path("data","gold","zone_day.parquet"),index=False)
    from .forecasting import horizon_validation, hourly_forecast
    horizon=horizon_validation(cfg,frame)
    hourly_forecast(cfg,trips,future)
    return cell,{"test":metrics,"selection":selection,"champion":serving_name,"horizon_validation":horizon,"decision_forecast":"30-day seasonal planning forecast; independent rolling-origin monthly backtests and validation-derived intervals provided. Weather forecast uncertainty remains outside scope.","reserve_fraction":.20}

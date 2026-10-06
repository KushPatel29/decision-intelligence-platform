"""Registry scoring adapters shared with batch clients; no simulator access."""
import numpy as np
import pandas as pd

def score_bundle(name,bundle,frame):
    if name in {"propensity","churn","attrition"}:
        raw=np.clip(bundle["model"].predict_proba(frame[bundle["features"]])[:,1],1e-5,1-1e-5)
        return bundle["calibrator"].predict_proba(np.log(raw/(1-raw)).reshape(-1,1))[:,1]
    if name=="clv":return bundle.predict(frame)
    if name=="demand":return np.maximum(bundle["model"].predict(frame[bundle["features"]]),0)
    if name=="uplift":
        x=frame[bundle["features"]];base=bundle["response"]["Control"].predict_proba(x)[:,1]
        return pd.DataFrame({arm:bundle["response"][arm].predict_proba(x)[:,1]-base for arm in ["Off-peak 15%","Weekend 20%","500 loyalty points"]})
    if name=="elasticity":
        result=[]
        for _,row in frame.iterrows():
            key=str(int(row.zone_id))+":"+row.period
            x=pd.DataFrame([row])[bundle["features"]]
            result.append(float(np.exp(bundle["models"][key].predict(x)[0])))
        return np.asarray(result)
    scaled=bundle["scaler"].transform(np.log1p(frame[bundle["features"]]))
    if name=="segmentation":return bundle["model"].predict(scaled)
    if name=="anomaly":return -bundle["model"].score_samples(scaled)
    raise ValueError("Unsupported model")

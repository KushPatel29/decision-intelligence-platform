"""SageMaker Processing: enforce purged folds and write isolated channels."""
import argparse,json
from pathlib import Path
import pandas as pd

def process(source,destination):
    source=Path(source);destination=Path(destination)
    frame=pd.read_parquet(source/"customer_month.parquet")
    features=json.loads((source/"feature_contract.json").read_text())["features"]
    groups={s:frame[frame.split.eq(s)] for s in ["train","validation","test"]}
    if groups["train"].label_end.max()>groups["validation"].as_of.min() or groups["validation"].label_end.max()>groups["test"].as_of.min():raise ValueError("Overlapping label windows")
    if any(f.startswith(("target_","future_","latent_","true_")) for f in features):raise ValueError("Feature leakage")
    for split,part in groups.items():
        out=destination/split;out.mkdir(parents=True,exist_ok=True)
        part[features+["target_propensity"]].to_csv(out/(split+".csv"),index=False)
        (out/"feature_contract.json").write_text(json.dumps({"features":features}))
    out=destination/"inference";out.mkdir(parents=True,exist_ok=True)
    groups["test"][features].to_csv(out/"features.csv",index=False,header=False)
    return {s:len(g) for s,g in groups.items()}

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--source",default="/opt/ml/processing/input");p.add_argument("--destination",default="/opt/ml/processing/output")
    a=p.parse_args();print(process(a.source,a.destination))

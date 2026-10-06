"""Held-out model evaluation for the quality-gate property file."""
import argparse,json,tarfile,tempfile
from pathlib import Path
import joblib,pandas as pd
from sklearn.metrics import roc_auc_score,brier_score_loss

def evaluate(model_archive,test_csv,output):
    with tempfile.TemporaryDirectory() as temp:
        with tarfile.open(model_archive) as archive:
            # Only the model artifact is needed; avoid unrestricted archive extraction.
            member=archive.getmember("model.joblib");stream=archive.extractfile(member)
            path=Path(temp)/"model.joblib";path.write_bytes(stream.read())
        bundle=joblib.load(path);test=pd.read_csv(test_csv)
        predicted=bundle["model"].predict_proba(test[bundle["features"]])[:,1]
        result={"classification":{"roc_auc":{"value":float(roc_auc_score(test.target_propensity,predicted))},"brier":{"value":float(brier_score_loss(test.target_propensity,predicted))}},"n_test":len(test)}
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2));return result

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--model",default="/opt/ml/processing/model/model.tar.gz");p.add_argument("--test",default="/opt/ml/processing/test/test.csv");p.add_argument("--output",default="/opt/ml/processing/evaluation/evaluation.json")
    a=p.parse_args();print(evaluate(a.model,a.test,a.output))

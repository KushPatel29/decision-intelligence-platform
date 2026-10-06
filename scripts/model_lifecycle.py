"""Explicit local model approval/rollback, with durable previous-version receipts."""
import argparse,json
from pathlib import Path
import mlflow
from mlflow.tracking import MlflowClient
from decision_platform.config import ROOT
from decision_platform.runtime import audit_event

def transition(model,version,action,reason,review_file):
    review=json.loads(review_file.read_text())
    if not review.get("approved") or review.get("model")!=model or str(review.get("version"))!=str(version) or not review.get("reviewer"):
        raise ValueError("Matching signed-off review receipt with reviewer required")
    if action=="promote" and not review.get("quality_passed"):raise ValueError("Promotion requires quality acceptance")
    mlflow.set_tracking_uri("sqlite:///"+str(ROOT/"outputs/mlflow.db").replace("\\","/"));client=MlflowClient()
    candidate=client.get_model_version(model,version)
    if candidate.tags.get("data_kind")!="synthetic":raise ValueError("This local workflow accepts synthetic portfolio models only")
    try:previous=client.get_model_version_by_alias(model,"ChampionLocal").version
    except mlflow.exceptions.MlflowException:previous=None
    if action in {"promote","rollback"}:
        if previous:client.set_registered_model_alias(model,"PreviousLocal",str(previous))
        client.set_registered_model_alias(model,"ChampionLocal",str(version))
    else:
        if previous and str(previous)==str(version):raise ValueError("Replace the active champion before archiving")
        client.set_model_version_tag(model,str(version),"lifecycle","Archived")
    audit_event(ROOT,"model-maintainer","model_"+action,{"model":model,"previous":previous,"version":str(version),"reviewer":review["reviewer"],"reason":reason,"scope":"Local alias only; hosted approval is separate"})

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("action",choices=["promote","rollback","archive"]);p.add_argument("--model",required=True);p.add_argument("--version",required=True);p.add_argument("--reason",required=True);p.add_argument("--review-file",type=Path,required=True)
    a=p.parse_args();transition(a.model,a.version,a.action,a.reason,a.review_file)

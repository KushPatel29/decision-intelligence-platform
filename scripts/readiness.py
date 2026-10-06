"""Generate evidence-based readiness without converting preparation into execution."""
import json
from datetime import datetime,timezone
from decision_platform.config import ROOT,write_json
from decision_platform.runtime import artifact_manifest

def main():
    quality=json.loads((ROOT/"outputs/quality_gate.json").read_text())
    cloud_path=ROOT/"outputs/cloud_portfolio_validation.json"
    cloud=json.loads(cloud_path.read_text()) if cloud_path.exists() else {}
    registry_path=ROOT/"outputs/model_registry.json"
    registry=json.loads(registry_path.read_text()) if registry_path.exists() else []
    checks=[
        {"check":"Local model acceptance","status":"Passed" if quality["passed"] else "Review required","evidence":"quality_gate.json"},
        {"check":"Six cloud model contracts","status":"Locally verified" if len(cloud.get("models",[]))==6 else "Pending","evidence":"cloud_portfolio_validation.json"},
        {"check":"Cloud candidate acceptance","status":"Pending" if len(cloud.get("models",[]))!=6 else "Review required" if any(not r["evaluation"]["quality"]["passed"] for r in cloud.get("models",[])) else "Locally passed","evidence":"A rejected model is held before registry/batch; job execution remains separate"},
        {"check":"Nine local registry scorers","status":"Passed" if len(registry)==9 and all(r["roundtrip_predictions_match"] for r in registry) else "Pending","evidence":"model_registry.json"},
        {"check":"Revised native Power BI","status":"Schema passed; Desktop refresh pending","evidence":"16 tables, 32 measures, eight pages; reload dialog blocked automated input"},
        {"check":"Private identity/access flow","status":"Prepared; hosted test pending","evidence":"OIDC allowlist and fail-closed production mode"},
        {"check":"Container build and security scan","status":"Pending","evidence":"Docker is not available on this host; executed CI required"},
        {"check":"Hosted SageMaker execution","status":"Pending","evidence":"AWS role, immutable ECR image, approved cost cap and successful job receipts required"},
        {"check":"Hosted Databricks execution","status":"Pending","evidence":"Full-feature/mart notebook authored; supported execution and parity receipt required"},
        {"check":"GitHub CI and milestones","status":"Prepared; publication pending","evidence":"Repository destination and authenticated publishing required"},
        {"check":"Backup restore and staging load test","status":"Pending","evidence":"Run against the chosen host and identity provider"},
    ]
    value={"release":"0.4.0","created_at":datetime.now(timezone.utc).isoformat(),"production_ready":False,"checks":checks,"scope":"Hardened and locally tested synthetic planning release. Hosted production acceptance remains pending; no service SLA or real-world customer-impact claim."}
    write_json(ROOT/"outputs/readiness.json",value)
    write_json(ROOT/"outputs/delivery_status.json",[{"name":r["check"],"status":r["status"],"detail":r["evidence"]} for r in checks])
    artifact_manifest(ROOT)
    print(json.dumps(value,indent=2))

if __name__=="__main__":main()

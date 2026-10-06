"""Refresh generated evidence without overwriting reviewed release documentation."""
import importlib.metadata
from decision_platform.config import ROOT
from build_catalog import main as build_catalog
from readiness import main as build_readiness

def main():
    build_catalog()
    packages=["numpy","pandas","scipy","scikit-learn","duckdb","pyarrow","joblib","streamlit","plotly","Authlib","gurobipy","mlflow","shap","lifetimes","reportlab","boto3","sagemaker","pyspark","delta-spark","deltalake"]
    lock=["# Tested top-level versions; not a full transitive environment lock."]
    for name in packages:
        try:lock.append(name+"=="+importlib.metadata.version(name))
        except importlib.metadata.PackageNotFoundError:pass
    (ROOT/"requirements-local.lock").write_text("\n".join(lock)+"\n",encoding="utf-8")
    build_readiness()
    print("Refreshed catalogs, dependency receipt and truthful readiness; reviewed documents preserved")

if __name__=="__main__":main()

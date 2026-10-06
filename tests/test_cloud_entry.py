"""Validate the local contracts of the cloud entry point without AWS calls."""
import importlib.util
import json
import pytest
import pandas as pd
from decision_platform.config import ROOT

def load_entry():
    spec=importlib.util.spec_from_file_location("sagemaker_train_entry",ROOT/"aws"/"train_entry.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def test_cloud_training_and_inference_contract():
    model_path=ROOT/"outputs"/"sagemaker_local"/"model"/"model.joblib"
    if not model_path.exists():pytest.skip("Prepare and run local SageMaker entry point first")
    module=load_entry();model=module.model_fn(model_path.parent)
    features=model["features"]
    assert not any(c.startswith(("target_","future_","latent_","true_")) for c in features)
    frame=pd.read_parquet(ROOT/"data"/"gold"/"customer_360.parquet").head(12)
    parsed=module.input_fn(frame[features].to_csv(index=False,header=False),"text/csv")
    scores=module.predict_fn(parsed,model)
    assert len(scores)==12
    assert ((scores>=0)&(scores<=1)).all()
    output,content_type=module.output_fn(scores,"text/csv")
    assert content_type=="text/csv"
    assert len(output.splitlines())==12
    with pytest.raises(ValueError,match="count mismatch"):
        module.predict_fn(parsed.iloc[:,:-1],model)

def test_reproducibility_receipt():
    path=ROOT/"outputs"/"reproducibility.json"
    if not path.exists():pytest.skip("Repeat-run evidence not generated")
    result=json.loads(path.read_text())
    assert result["core_metrics_reproduce"]
    assert result["raw_dataset_hashes_match"]

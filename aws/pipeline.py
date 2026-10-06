"""Construct a complete SageMaker pipeline without automatically executing it.

All scripts and input are supplied as S3 URIs: definition compilation needs no
upload, IAM changes, persistent endpoint or cloud execution. See README.
"""

import argparse
import json
from pathlib import Path

import boto3
from sagemaker import image_uris
from sagemaker.estimator import Estimator
from sagemaker.inputs import TrainingInput, TransformInput
from sagemaker.model import Model
from sagemaker.processing import ProcessingInput, ProcessingOutput, Processor
from sagemaker.transformer import Transformer
from sagemaker.workflow.condition_step import ConditionStep
from sagemaker.workflow.conditions import ConditionGreaterThanOrEqualTo
from sagemaker.workflow.functions import Join, JsonGet
from sagemaker.workflow.parameters import ParameterFloat, ParameterString
from sagemaker.workflow.pipeline import Pipeline
from sagemaker.workflow.pipeline_context import PipelineSession
from sagemaker.workflow.properties import PropertyFile
from sagemaker.workflow.step_collections import RegisterModel
from sagemaker.workflow.steps import CreateModelStep, ProcessingStep, TrainingStep, TransformStep


def build(region="eu-north-1", offline=True, role_arn="arn:aws:iam::000000000000:role/CorridorExecution"):
    # Placeholder credentials serialize a definition only; they cannot authenticate.
    kwargs = (
        {"aws_access_key_id": "OFFLINE_DEFINITION_ONLY", "aws_secret_access_key": "OFFLINE_DEFINITION_ONLY"}
        if offline
        else {}
    )
    boto = boto3.Session(region_name=region, **kwargs)
    session = PipelineSession(boto_session=boto, default_bucket="corridor-artifacts-placeholder")
    role = role_arn
    root = ParameterString("ArtifactsPrefix", default_value="s3://corridor-artifacts-placeholder/corridor-v2")
    source = ParameterString(
        "SourceArchiveUri", default_value="s3://corridor-artifacts-placeholder/corridor-v2/code/source.tar.gz"
    )
    instance = ParameterString("InstanceType", default_value="ml.m5.large")
    threshold = ParameterFloat("MinimumTestAUC", default_value=0.70)
    image = image_uris.retrieve(
        "sklearn", region=region, version="1.2-1", py_version="py3", instance_type="ml.m5.large"
    )
    processor = Processor(
        role=role,
        image_uri=image,
        instance_count=1,
        instance_type=instance,
        entrypoint=["python3"],
        max_runtime_in_seconds=600,
        sagemaker_session=session,
    )
    prep = ProcessingStep(
        "PreparePurgedChannels",
        processor=processor,
        inputs=[
            ProcessingInput(
                source=Join(on="/", values=[root, "input"]), destination="/opt/ml/processing/input"
            ),
            ProcessingInput(
                source=Join(on="/", values=[root, "code/process_entry.py"]),
                destination="/opt/ml/processing/code",
            ),
        ],
        outputs=[
            ProcessingOutput(
                output_name=s,
                source="/opt/ml/processing/output/" + s,
                destination=Join(on="/", values=[root, "prepared", s]),
            )
            for s in ["train", "validation", "test", "inference"]
        ],
        job_arguments=["/opt/ml/processing/code/process_entry.py"],
    )
    estimator = Estimator(
        image_uri=image,
        role=role,
        instance_count=1,
        instance_type=instance,
        max_run=600,
        volume_size=5,
        output_path=Join(on="/", values=[root, "trained"]),
        sagemaker_session=session,
        disable_profiler=True,
        hyperparameters={
            "sagemaker_program": "train_entry.py",
            "sagemaker_submit_directory": source,
            "sagemaker_container_log_level": 20,
            "sagemaker_region": region,
        },
    )
    train = TrainingStep(
        "TrainPropensity",
        estimator=estimator,
        inputs={
            s: TrainingInput(
                s3_data=prep.properties.ProcessingOutputConfig.Outputs[s].S3Output.S3Uri,
                content_type="text/csv",
            )
            for s in ["train", "validation"]
        },
    )
    quality = PropertyFile(name="QualityReport", output_name="evaluation", path="evaluation.json")
    evaluate = ProcessingStep(
        "EvaluateUntouchedTest",
        processor=processor,
        inputs=[
            ProcessingInput(
                source=train.properties.ModelArtifacts.S3ModelArtifacts,
                destination="/opt/ml/processing/model",
            ),
            ProcessingInput(
                source=prep.properties.ProcessingOutputConfig.Outputs["test"].S3Output.S3Uri,
                destination="/opt/ml/processing/test",
            ),
            ProcessingInput(
                source=Join(on="/", values=[root, "code/evaluate_entry.py"]),
                destination="/opt/ml/processing/code",
            ),
        ],
        outputs=[
            ProcessingOutput(
                output_name="evaluation",
                source="/opt/ml/processing/evaluation",
                destination=Join(on="/", values=[root, "evaluation"]),
            )
        ],
        job_arguments=["/opt/ml/processing/code/evaluate_entry.py"],
        property_files=[quality],
    )
    env = {
        "SAGEMAKER_PROGRAM": "train_entry.py",
        "SAGEMAKER_SUBMIT_DIRECTORY": source,
        "SAGEMAKER_REGION": region,
        "SAGEMAKER_CONTAINER_LOG_LEVEL": "20",
    }
    model = Model(
        image_uri=image,
        model_data=train.properties.ModelArtifacts.S3ModelArtifacts,
        role=role,
        env=env,
        sagemaker_session=session,
    )
    register = RegisterModel(
        name="RegisterCandidate",
        model=model,
        content_types=["text/csv"],
        response_types=["text/csv"],
        inference_instances=["ml.m5.large"],
        transform_instances=["ml.m5.large"],
        model_package_group_name="CorridorPropensity",
        approval_status="PendingManualApproval",
    )
    create = CreateModelStep(name="CreateBatchModel", model=model)
    transformer = Transformer(
        model_name=create.properties.ModelName,
        instance_count=1,
        instance_type=instance,
        output_path=Join(on="/", values=[root, "batch-output"]),
        accept="text/csv",
        assemble_with="Line",
        max_payload=6,
        sagemaker_session=session,
    )
    transform = TransformStep(
        name="BatchScoreTestFeatures",
        transformer=transformer,
        inputs=TransformInput(
            data=prep.properties.ProcessingOutputConfig.Outputs["inference"].S3Output.S3Uri,
            content_type="text/csv",
            split_type="Line",
        ),
    )
    gate = ConditionStep(
        name="TestQualityGate",
        conditions=[
            ConditionGreaterThanOrEqualTo(
                left=JsonGet(
                    step_name=evaluate.name, property_file=quality, json_path="classification.roc_auc.value"
                ),
                right=threshold,
            )
        ],
        if_steps=[register, create, transform],
        else_steps=[],
    )
    return Pipeline(
        name="CorridorDecisionPipeline",
        parameters=[root, source, instance, threshold],
        steps=[prep, train, evaluate, gate],
        sagemaker_session=session,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--region", default="eu-north-1")
    p.add_argument("--output", default="outputs/sagemaker_pipeline.json")
    a = p.parse_args()
    definition = json.loads(build(a.region).definition())
    Path(a.output).write_text(json.dumps(definition, indent=2))
    print("Compiled pipeline definition; no cloud resources created")

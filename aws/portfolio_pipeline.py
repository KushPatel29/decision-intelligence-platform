"""Compile six SageMaker workflows against a tested, immutable project container.

No upload, upsert or start call is performed by this module.
"""

import argparse
import json
from pathlib import Path

import boto3
from sagemaker.estimator import Estimator
from sagemaker.inputs import TrainingInput, TransformInput
from sagemaker.model import Model
from sagemaker.processing import ProcessingInput, ProcessingOutput, Processor
from sagemaker.transformer import Transformer
from sagemaker.workflow.condition_step import ConditionStep
from sagemaker.workflow.conditions import ConditionGreaterThanOrEqualTo
from sagemaker.workflow.fail_step import FailStep
from sagemaker.workflow.functions import Join, JsonGet
from sagemaker.workflow.parameters import ParameterString
from sagemaker.workflow.pipeline import Pipeline
from sagemaker.workflow.pipeline_context import PipelineSession
from sagemaker.workflow.properties import PropertyFile
from sagemaker.workflow.step_collections import RegisterModel
from sagemaker.workflow.steps import CreateModelStep, ProcessingStep, TrainingStep, TransformStep

TASKS = ["propensity", "churn", "attrition", "uplift", "elasticity", "demand"]


def build(
    task,
    region="eu-north-1",
    role="arn:aws:iam::000000000000:role/CorridorExecution",
    image="000000000000.dkr.ecr.eu-north-1.amazonaws.com/corridor-ml:1.1.0",
    offline=True,
):
    if task not in TASKS:
        raise ValueError("Unsupported task")
    if not offline and ("000000000000" in role or "000000000000" in image or "@sha256:" not in image):
        raise ValueError("Real role and immutable ECR image digest required for hosted compilation")
    credentials = (
        {"aws_access_key_id": "OFFLINE_ONLY", "aws_secret_access_key": "OFFLINE_ONLY"} if offline else {}
    )
    session = PipelineSession(
        boto_session=boto3.Session(region_name=region, **credentials),
        default_bucket="corridor-artifacts-placeholder",
    )
    root = ParameterString(
        "ArtifactsPrefix", default_value="s3://corridor-artifacts-placeholder/portfolio/" + task
    )
    instance = ParameterString("InstanceType", default_value="ml.m5.large")
    processor = Processor(
        role=role,
        image_uri=image,
        instance_count=1,
        instance_type=instance,
        max_runtime_in_seconds=600,
        entrypoint=["python", "/opt/program/process_portfolio.py"],
        sagemaker_session=session,
    )
    prep = ProcessingStep(
        "PrepareChannels",
        processor=processor,
        inputs=[
            ProcessingInput(
                source=Join(on="/", values=[root, "input"]), destination="/opt/ml/processing/input"
            )
        ],
        outputs=[
            ProcessingOutput(
                output_name=s,
                source="/opt/ml/processing/output/" + s,
                destination=Join(on="/", values=[root, "prepared", s]),
            )
            for s in ["train", "validation", "test", "inference"]
        ],
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
        enable_network_isolation=True,
    )
    training = TrainingStep(
        "Train" + task.title(),
        estimator=estimator,
        inputs={
            s: TrainingInput(
                s3_data=prep.properties.ProcessingOutputConfig.Outputs[s].S3Output.S3Uri,
                content_type="text/csv",
            )
            for s in ["train", "validation"]
        },
    )
    report = PropertyFile(name="Acceptance", output_name="evaluation", path="evaluation.json")
    evaluator = Processor(
        role=role,
        image_uri=image,
        instance_count=1,
        instance_type=instance,
        max_runtime_in_seconds=600,
        entrypoint=["python", "/opt/program/evaluate_portfolio.py"],
        sagemaker_session=session,
    )
    evaluation = ProcessingStep(
        "EvaluateUntouchedTest",
        processor=evaluator,
        inputs=[
            ProcessingInput(
                source=training.properties.ModelArtifacts.S3ModelArtifacts,
                destination="/opt/ml/processing/model",
            ),
            ProcessingInput(
                source=prep.properties.ProcessingOutputConfig.Outputs["test"].S3Output.S3Uri,
                destination="/opt/ml/processing/test",
            ),
        ],
        outputs=[
            ProcessingOutput(
                output_name="evaluation",
                source="/opt/ml/processing/evaluation",
                destination=Join(on="/", values=[root, "evaluation"]),
            )
        ],
        property_files=[report],
    )
    model = Model(
        image_uri=image,
        model_data=training.properties.ModelArtifacts.S3ModelArtifacts,
        role=role,
        sagemaker_session=session,
    )
    register = RegisterModel(
        name="RegisterCandidate",
        model=model,
        content_types=["text/csv"],
        response_types=["text/csv"],
        inference_instances=["ml.m5.large"],
        transform_instances=["ml.m5.large"],
        model_package_group_name="Corridor-" + task,
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
    batch = TransformStep(
        "BatchScore",
        transformer=transformer,
        inputs=TransformInput(
            data=prep.properties.ProcessingOutputConfig.Outputs["inference"].S3Output.S3Uri,
            content_type="text/csv",
            split_type="Line",
        ),
    )
    reject = FailStep(
        name="RejectCandidate",
        error_message="Untouched test acceptance failed; registry and batch inference are held. Review the evaluation receipt.",
    )
    gate = ConditionStep(
        "ModelAcceptanceGate",
        conditions=[
            ConditionGreaterThanOrEqualTo(
                left=JsonGet(step_name=evaluation.name, property_file=report, json_path="quality.passed"),
                right=1,
            )
        ],
        if_steps=[register, create, batch],
        else_steps=[reject],
    )
    return Pipeline(
        name="Corridor-" + task + "-Pipeline",
        parameters=[root, instance],
        steps=[prep, training, evaluation, gate],
        sagemaker_session=session,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--region", default="eu-north-1")
    p.add_argument("--image")
    p.add_argument("--role")
    p.add_argument("--output", default="outputs/cloud_portfolio/definitions")
    a = p.parse_args()
    folder = Path(a.output)
    folder.mkdir(parents=True, exist_ok=True)
    for task in TASKS:
        args = {"region": a.region}
        if a.image:
            args["image"] = a.image
        if a.role:
            args["role"] = a.role
        definition = json.loads(build(task, **args).definition())
        (folder / (task + ".json")).write_text(json.dumps(definition, indent=2))
    print("Six pipeline definitions compiled; zero cloud API calls")

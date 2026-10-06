# SageMaker delivery package

`pipeline.py` compiles an SDK v2 pipeline without creating resources. It has Processing, Training, untouched-test Evaluation, a ROC-AUC quality gate, registration with PendingManualApproval, model creation and Batch Transform. SDK v2 is deliberately pinned for this implementation; migrate before its retirement. The definition compiles locally; this is not a cloud-run receipt.

The selected region is eu-north-1, matching the inspected console. No SageMaker execution role was available in the console selector. No local AWS CLI credentials are configured. Hosted execution is pending role/storage setup and a usable quota. Databricks Free Edition requires manual console operation or its supported Genie One connector.

Before a cloud run:

1. Create a project-only S3 bucket with public access blocked and default server-side encryption.
2. Use an approved SageMaker execution role restricted to that bucket. The trust policy allows `sagemaker.amazonaws.com`. The deploying caller requires `iam:PassRole` for that execution role. Do not grant account-wide administrative access.
3. Upload synthetic `customer_month.parquet` and its `feature_contract.json` to `corridor-v2/input/`. Upload `process_entry.py` and `evaluate_entry.py` to `corridor-v2/code/`. Build `source.tar.gz` containing `train_entry.py` for script-mode training and inference.
4. Rebuild `build(region='eu-north-1', offline=False, role_arn='<approved ARN>')` with authenticated SDK access. Replace ArtifactsPrefix and SourceArchiveUri defaults or execution parameters. Do not execute the placeholder definition.
5. Confirm processing, training and transform quota for the selected instance type. Verify the chosen sklearn container includes compatible Parquet dependencies; Processing reads the delivered Parquet file. Cloud validation must cover the container environment, IAM and storage permissions in addition to local stage tests.
6. Set a spending limit before execution. Jobs have 600-second maximum runtime and one CPU instance. There is no persistent endpoint or warm pool. The quality gate skips registration and inference when test AUC is below 0.70. Model approval remains pending manual review.
7. Run the pipeline, download processing/training/batch logs and predictions, compare held-out metrics with the local reference, then record actual region, job names, registry version, runtime and cost. Remove temporary compute resources and retain only necessary encrypted artifacts.

Browser creation of a new role changes security-sensitive access and requires confirmation at action time under the computer-use skill. These preparation files do not authorize that change or a charge. No cloud resource has been provisioned by this project.

## Measured local stage verification

Run `scripts/verify_cloud_stages.py` to execute Processing, Training, held-out Evaluation and CSV batch inference locally. The saved receipt is `outputs/sagemaker_local_validation.json`: 56,000 training snapshots, 8,000 validation snapshots and 8,000 untouched test snapshots; test AUC 0.826, above the 0.70 gate, and 12 inference rows passed serialization checks. This tests the actual entry points without an AWS API call. The cloud container, permissions, quota and service execution still need hosted verification.

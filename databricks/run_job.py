"""Deploy the Corridor job to a Databricks workspace and run it, through the Python SDK.

The job is read from ``databricks.yml`` at the repository root, the same definition
``databricks bundle deploy`` uses, so the two routes cannot drift. Authentication is
browser OAuth (U2M): no token is stored or typed. The first run opens a browser tab to
approve; later runs reuse the cached session.

What it does:

1. Uploads ``src/decision_platform``, ``sql/``, the cached public context in
   ``data/external`` and the four notebooks to ``/Workspace/Users/<you>/corridor``.
2. Creates the job, or resets it to this definition if it exists.
3. Runs it, prints each task's state as it changes, and on success writes the publish
   task's receipt to ``databricks/receipts/``.

Usage::

    python -m decision_platform.cli fetch          # once: caches data/external
    python databricks/run_job.py --host https://<workspace>.cloud.databricks.com
    python databricks/run_job.py --host ... --customers 5000 --no-wait
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
UPLOADS = [("src/decision_platform", "*.py"), ("sql", "*.sql"), ("data/external", "*.json")]
TERMINAL = {"TERMINATED", "SKIPPED", "INTERNAL_ERROR"}


def job_definition(variables: dict[str, str], file_path: str) -> dict:
    """The corridor job from databricks.yml with ${var.*} and ${workspace.file_path} resolved."""
    spec = yaml.safe_load((ROOT / "databricks.yml").read_text(encoding="utf-8"))
    values = {name: str(item["default"]) for name, item in spec["variables"].items()}
    values.update({k: v for k, v in variables.items() if v is not None})

    def resolve(value):
        if not isinstance(value, str):
            return value
        value = value.replace("${workspace.file_path}", file_path)
        return re.sub(r"\$\{var\.(\w+)\}", lambda m: values[m.group(1)], value)

    job = spec["resources"]["jobs"]["corridor"]
    job["parameters"] = [{**p, "default": resolve(p["default"])} for p in job["parameters"]]
    return job


def upload(w, root: str) -> int:
    from databricks.sdk.service.workspace import ImportFormat

    count = 0
    for folder, pattern in UPLOADS:
        paths = sorted((ROOT / folder).glob(pattern))
        if not paths:
            raise SystemExit(
                f"nothing to upload from {folder}; run `python -m decision_platform.cli fetch` first"
            )
        w.workspace.mkdirs(f"{root}/{folder}")
        for path in paths:
            w.workspace.upload(
                f"{root}/{folder}/{path.name}",
                io.BytesIO(path.read_bytes()),
                format=ImportFormat.AUTO,
                overwrite=True,
            )
            count += 1
    w.workspace.mkdirs(f"{root}/databricks/notebooks")
    for notebook in sorted((ROOT / "databricks" / "notebooks").glob("*.py")):
        # AUTO imports a file with the "# Databricks notebook source" header as a notebook
        # and drops its extension, which is the path the job's tasks point at.
        w.workspace.upload(
            f"{root}/databricks/notebooks/{notebook.name}",
            io.BytesIO(notebook.read_bytes()),
            format=ImportFormat.AUTO,
            overwrite=True,
        )
        count += 1
    return count


def deploy(w, job: dict, root: str) -> int:
    from databricks.sdk.service import jobs

    tasks = [
        jobs.Task(
            task_key=task["task_key"],
            depends_on=[jobs.TaskDependency(task_key=d["task_key"]) for d in task.get("depends_on", [])],
            notebook_task=jobs.NotebookTask(
                notebook_path=f"{root}/databricks/notebooks/{Path(task['notebook_task']['notebook_path']).stem}",
                source=jobs.Source.WORKSPACE,
            ),
        )
        for task in job["tasks"]
    ]
    settings = {
        "name": job["name"],
        "description": job["description"],
        "max_concurrent_runs": job["max_concurrent_runs"],
        "timeout_seconds": job["timeout_seconds"],
        "parameters": [
            jobs.JobParameterDefinition(name=p["name"], default=p["default"]) for p in job["parameters"]
        ],
        "tasks": tasks,
    }
    existing = list(w.jobs.list(name=job["name"]))
    if existing:
        job_id = existing[0].job_id
        w.jobs.reset(job_id=job_id, new_settings=jobs.JobSettings(**settings))
        return job_id
    return w.jobs.create(**settings).job_id


def follow(w, run_id: int) -> dict:
    """Print each task's state when it changes; return the finished run."""
    seen: dict[str, str] = {}
    while True:
        run = w.jobs.get_run(run_id)
        for task in run.tasks or []:
            state = (
                task.state.result_state.value
                if task.state.result_state
                else task.state.life_cycle_state.value
            )
            if seen.get(task.task_key) != state:
                seen[task.task_key] = state
                print(f"  {datetime.now():%H:%M:%S}  {task.task_key:10s} {state}", flush=True)
        if run.state.life_cycle_state.value in TERMINAL:
            return run
        time.sleep(20)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default=os.environ.get("DATABRICKS_HOST"), help="workspace URL")
    ap.add_argument("--catalog")
    ap.add_argument("--schema")
    ap.add_argument("--customers")
    ap.add_argument("--solver", choices=["auto", "gurobi", "highs"])
    ap.add_argument("--no-run", action="store_true", help="deploy only")
    ap.add_argument("--no-wait", action="store_true", help="start the run and return")
    args = ap.parse_args()
    if not args.host:
        ap.error("--host (or DATABRICKS_HOST) is required")

    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient(host=args.host, auth_type="external-browser")
    user = w.current_user.me().user_name
    root = f"/Users/{user}/corridor"
    job = job_definition(
        {"catalog": args.catalog, "schema": args.schema, "customers": args.customers, "solver": args.solver},
        f"/Workspace{root}",
    )
    print(f"uploaded {upload(w, root)} files to /Workspace{root}")
    job_id = deploy(w, job, root)
    print(f"job {job['name']} ({job_id}) deployed")
    if args.no_run:
        return 0
    run_id = w.jobs.run_now(job_id=job_id).run_id
    print(f"run {run_id} started: {args.host.rstrip('/')}/jobs/{job_id}/runs/{run_id}")
    if args.no_wait:
        return 0
    run = follow(w, run_id)
    result = run.state.result_state.value if run.state.result_state else run.state.life_cycle_state.value
    print(f"run {run_id} finished: {result}")
    for task in run.tasks or []:
        output = w.jobs.get_run_output(task.run_id)
        if output.error:
            print(f"\n{task.task_key} failed: {output.error}\n{(output.error_trace or '')[-3000:]}")
        if task.task_key == "publish" and output.notebook_output and output.notebook_output.result:
            receipt = json.loads(output.notebook_output.result)
            receipt["databricks_job_id"], receipt["databricks_run_id"] = job_id, run_id
            receipt["run_seconds"] = round(((run.end_time or 0) - (run.start_time or 0)) / 1000, 1)
            receipt["task_seconds"] = {
                t.task_key: round(((t.end_time or 0) - (t.start_time or 0)) / 1000, 1)
                for t in run.tasks or []
            }
            folder = ROOT / "databricks" / "receipts"
            folder.mkdir(exist_ok=True)
            path = folder / f"{datetime.now(UTC):%Y-%m-%d}-run-{run_id}.json"
            # The receipt is committed as evidence; the workspace user name (an email) is not part of it.
            path.write_text(json.dumps(receipt, indent=2).replace(user, "<user>") + "\n", encoding="utf-8")
            print(f"receipt written to {path.relative_to(ROOT)}")
    return 0 if result == "SUCCESS" else 1


if __name__ == "__main__":
    sys.exit(main())
